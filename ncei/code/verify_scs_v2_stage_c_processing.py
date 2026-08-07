#!/usr/bin/env python3
"""Independently verify a source-internal Stage C run without opening sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE_C_ROOT = REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/stage_c"
SEALED_ROOT = REPO_ROOT / "ncei/archive/scs_v2_sealed_confirmation/20260805T230449Z"
READINESS_ROOT = REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/stage_c_readiness/20260806T093740Z"
SCHEMA_PATH = REPO_ROOT / ".trellis/tasks/08-06-scs-v2-stage-c0-source-internal-planning/research/stage-c01-output-schema.yaml"
PROCESSOR_PATH = REPO_ROOT / "ncei/code/process_scs_v2_stage_c_source_internal.py"
HELPER_PATH = REPO_ROOT / "ncei/code/scs_v2_stage_c_processing.py"
VERIFIER_PATH = REPO_ROOT / "ncei/code/verify_scs_v2_stage_c_processing.py"
PRIMARY_IDS = ["EQT20210702", "EQT190012", "EQT180002", "TN352"]
ACQUISITION_RUN_ID = "20260805T230449Z"
MANIFEST_SHA256 = "9fafb163a6fe2818d96a0c9bb0ed49afc98a8b0850979d5783b1882139702f94"
STAGE_B_VERIFICATION_SHA256 = "d0d868f560c628bd24d1d52d399c7ed9d03af337be72967a874a5c26db7c2e86"
STAGE_B_ACCESS_LOCK_SHA256 = "75c290a9b4f17ed2b529a372417f4fd18770c08cf66836c07ddde3bb90e00a6f"
C1A_MANIFEST_SHA256 = "c260960dc4999f08bad710b7d2f6111acd90087a158eb661957f01280bc89615"
C1A_VERIFICATION_SHA256 = "9f3464bfa3f1a90d319761b543bb5488d0d5c154bfc6837b23a278d53558c717"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
FORMATS = {".mb58.gz", ".fnv", ".inf", ".fbt"}
PROCESSING_FORMATS = {".mb58.gz"}
SIDECAR_FORMATS = {".fnv", ".inf", ".fbt"}
FIVE_LEVEL_STATUS = {
    "known",
    "officially_unknown",
    "not_recoverable",
    "inferred_from_filename",
    "verified_from_source_metadata",
}
TABLE_KEYS = {
    "source_object_processing.parquet": ["source_object_id"],
    "sounding_lineage.parquet": ["source_object_id", "parser_ping_index", "beam_index"],
    "cell_cruise_contributors.parquet": ["cell_id", "official_cruise_id", "source_object_id"],
    "cell_cruise_candidates.parquet": ["cell_id", "official_cruise_id"],
    "field_recovery_ledger.parquet": ["official_cruise_id", "source_object_id", "field_name"],
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_authorization_receipt_sha256(value: dict[str, Any]) -> str:
    payload = dict(value)
    payload.pop("authorization_receipt_sha256", None)
    return hashlib.sha256(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def arrow_type(type_name: str) -> pa.DataType:
    if type_name == "string":
        return pa.string()
    if type_name == "int64":
        return pa.int64()
    if type_name == "int32":
        return pa.int32()
    if type_name == "float64":
        return pa.float64()
    if type_name == "bool":
        return pa.bool_()
    if type_name == "list_string":
        return pa.list_(pa.string())
    if type_name == "timestamp_us_UTC":
        return pa.timestamp("us", tz="UTC")
    raise ValueError(f"unsupported output schema type: {type_name}")


def expected_schemas() -> dict[str, pa.Schema]:
    spec = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    return {
        table_name: pa.schema(
            [
                pa.field(field["name"], arrow_type(field["type"]), nullable=bool(field["nullable"]))
                for field in table_spec["fields"]
            ]
        )
        for table_name, table_spec in spec["tables"].items()
    }


def verify_schema(path: Path, expected: pa.Schema) -> None:
    actual = pq.read_schema(path)
    require(actual.names == expected.names, f"schema columns mismatch: {path.name}")
    for actual_field, expected_field in zip(actual, expected):
        require(actual_field.type.equals(expected_field.type), f"schema type mismatch: {path.name}.{expected_field.name}")
        require(actual_field.nullable == expected_field.nullable, f"schema nullability mismatch: {path.name}.{expected_field.name}")


def normalize_lon(value: float) -> float:
    return ((float(value) + 180.0) % 360.0) - 180.0


def cell_assignment(lon: float, lat: float) -> tuple[int, int, str]:
    lon = normalize_lon(lon)
    require(math.isfinite(lat) and -90.0 <= lat <= 90.0, "latitude outside frozen range")
    lon_bin = math.floor((lon + 180.0) * 60.0)
    lat_bin = math.floor((lat + 90.0) * 60.0)
    return lon_bin, lat_bin, f"1min_{lat_bin}_{lon_bin}"


def cell_center(lon_bin: int, lat_bin: int) -> tuple[float, float]:
    return -180.0 + (lon_bin + 0.5) / 60.0, -90.0 + (lat_bin + 0.5) / 60.0


def nmad(values: list[float]) -> float | None:
    if not values:
        return None
    median = statistics.median(values)
    return float(1.4826 * statistics.median([abs(value - median) for value in values]))


def aggregate(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"median": None, "mean": None, "nmad": None, "q25": None, "q75": None, "min": None, "max": None, "range": None}
    return {
        "median": float(statistics.median(values)),
        "mean": float(statistics.fmean(values)),
        "nmad": nmad(values),
        "q25": float(np.quantile(np.asarray(values, dtype=np.float64), 0.25, method="linear")),
        "q75": float(np.quantile(np.asarray(values, dtype=np.float64), 0.75, method="linear")),
        "min": float(min(values)),
        "max": float(max(values)),
        "range": float(max(values) - min(values)),
    }


def close_number(actual: Any, expected: Any) -> bool:
    # pandas reads parquet float nulls as NaN; treat NaN as null so producer's
    # None-valued stats round-trip correctly through the pandas read path.
    def is_null(value: Any) -> bool:
        return value is None or (isinstance(value, float) and math.isnan(value))
    if is_null(actual) or is_null(expected):
        return is_null(actual) and is_null(expected)
    return math.isclose(float(actual), float(expected), rel_tol=1e-12, abs_tol=1e-9)


def eligible_token(cell: str, cruise: str, object_id: str, ping: int, depth: float, epoch_us: int) -> bytes:
    return (json.dumps([cell, cruise, object_id, int(ping), float(depth), int(epoch_us)], separators=(",", ":")) + "\n").encode("utf-8")


def verify_manifest_metadata() -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    manifest_path = SEALED_ROOT / "sealed_archive_manifest.parquet"
    require(sha256_file(manifest_path) == MANIFEST_SHA256, "Stage B manifest hash mismatch")
    manifest = pd.read_parquet(manifest_path)
    require(len(manifest) == 768, "Stage B manifest count mismatch")
    require(int(manifest["bytes"].sum()) == 9_626_893_507, "Stage B manifest byte total mismatch")
    require(manifest["official_cruise_id"].drop_duplicates().tolist() == PRIMARY_IDS, "Stage B cruise order mismatch")
    require(set(manifest["format"]) == FORMATS, "Stage B format set mismatch")
    require((manifest["content_parsed"] == False).all(), "Stage B content parsed flag changed")
    require(manifest["expected_last_modified"].notna().all(), "Stage B Last-Modified missing")
    verification_path = SEALED_ROOT / "verification.json"
    access_path = SEALED_ROOT / "access_lock.json"
    require(sha256_file(verification_path) == STAGE_B_VERIFICATION_SHA256, "Stage B verification hash mismatch")
    require(sha256_file(access_path) == STAGE_B_ACCESS_LOCK_SHA256, "Stage B access lock hash mismatch")
    verification = load_json(verification_path)
    access = load_json(access_path)
    require(verification["status"] == "pass" and verification["checks"]["content_parsed"] is False, "Stage B is not sealed pass")
    return manifest.sort_values("relative_path").reset_index(drop=True), verification, access


def compare_row(actual: dict[str, Any], expected: dict[str, Any], fields: Iterable[str], context: str) -> None:
    for field in fields:
        left, right = actual.get(field), expected.get(field)
        if isinstance(right, float):
            require(close_number(left, right), f"{context}: {field} mismatch")
        else:
            require(left == right, f"{context}: {field} mismatch: {left!r} != {right!r}")


def verify_object_tables(run_dir: Path, manifest: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, dict[str, Any]]]:
    schemas = expected_schemas()
    for filename in TABLE_KEYS:
        verify_schema(run_dir / filename, schemas[filename])
    objects = pd.read_parquet(run_dir / "source_object_processing.parquet")
    contributors = pd.read_parquet(run_dir / "cell_cruise_contributors.parquet")
    candidates = pd.read_parquet(run_dir / "cell_cruise_candidates.parquet")
    ledger = pd.read_parquet(run_dir / "field_recovery_ledger.parquet")
    closure = pd.read_parquet(run_dir / "object_access_closure.parquet")
    require(len(objects) == len(manifest) == 768, "source object count mismatch")
    require(len(closure) == 768, "object access closure count mismatch")
    require(len(ledger) == 768 * 12, "field ledger row count mismatch")
    for filename, key in TABLE_KEYS.items():
        frame = {"source_object_processing.parquet": objects, "sounding_lineage.parquet": None, "cell_cruise_contributors.parquet": contributors, "cell_cruise_candidates.parquet": candidates, "field_recovery_ledger.parquet": ledger}[filename]
        if frame is None:
            continue
        require(not frame[key].isna().any(axis=None), f"{filename} key contains null")
        require(not frame.duplicated(key).any(), f"{filename} key is duplicated")
    expected_objects: dict[str, dict[str, Any]] = {}
    for record in manifest.to_dict(orient="records"):
        relative = str(record["relative_path"])
        object_id = f"{ACQUISITION_RUN_ID}/{relative}"
        expected_objects[object_id] = record
    require(objects["source_object_id"].astype(str).tolist() == list(expected_objects), "source object order or identity mismatch")
    for row in objects.to_dict(orient="records"):
        object_id = str(row["source_object_id"])
        record = expected_objects[object_id]
        require(row["acquisition_run_id"] == ACQUISITION_RUN_ID, f"{object_id}: acquisition ID mismatch")
        require(row["source_object_identity_basis"] == "acquisition_run_id + '/' + canonical_source_object_relative_path", f"{object_id}: identity basis mismatch")
        require(re.fullmatch(r"[0-9a-f]{64}", str(row["source_object_sha256"])) is not None, f"{object_id}: content hash format")
        compare_row(row, {"source_object_relative_path": record["relative_path"], "source_object_sha256": record["sha256"], "official_cruise_id": record["official_cruise_id"], "source_object_filename": record["filename"], "source_object_role": record["source_object_role"], "source_object_format": record["format"], "source_object_bytes": int(record["bytes"])}, ["source_object_relative_path", "source_object_sha256", "official_cruise_id", "source_object_filename", "source_object_role", "source_object_format", "source_object_bytes"], object_id)
        fmt = str(record["format"])
        if fmt == ".mb58.gz":
            require(row["body_read_authorized"] is True and row["body_read_performed"] is True, f"{object_id}: primary body flags")
            require(row["parser_name"] == "MB-System" and row["parser_version"] == "5.8.3beta16", f"{object_id}: parser identity")
            require(row["parse_status"] in {"pass", "failed_invalid_or_missing_time", "failed_parser_contract"}, f"{object_id}: parse status")
            if row["parse_status"] == "pass":
                require(int(row["parsed_row_count"]) >= 0, f"{object_id}: parsed row count")
            else:
                require(int(row["parsed_row_count"]) == 0 and row["error_code"], f"{object_id}: failed parser closure")
        else:
            require(fmt in SIDECAR_FORMATS, f"{object_id}: unexpected sidecar format")
            require(row["body_read_authorized"] is False and row["body_read_performed"] is False, f"{object_id}: sidecar body was read")
            require(row["parse_status"] == "not_applicable_sidecar", f"{object_id}: sidecar status")
            require(int(row["parsed_row_count"]) == 0, f"{object_id}: sidecar parsed count")
        require(row["official_cruise_id_status"] == "verified_from_source_metadata", f"{object_id}: cruise status")
        for field in row:
            if field.endswith("_status") and field != "parse_status":
                require(row[field] in FIVE_LEVEL_STATUS, f"{object_id}: invalid status {field}")
    require(closure["source_object_id"].astype(str).tolist() == objects["source_object_id"].astype(str).tolist(), "closure order mismatch")
    for row in closure.to_dict(orient="records"):
        object_id = str(row["source_object_id"])
        record = expected_objects[object_id]
        fmt = str(record["format"])
        require(row["manifest_bytes"] == int(record["bytes"]) and row["manifest_sha256"] == record["sha256"], f"{object_id}: closure manifest mismatch")
        if fmt == ".mb58.gz":
            require(row["body_read_authorized"] is True and row["body_read_performed"] is True, f"{object_id}: primary closure flags")
            require(row["closure_status"] == "pass", f"{object_id}: primary closure status")
            require(row["pre_read_bytes"] == row["post_read_bytes"] == int(record["bytes"]), f"{object_id}: closure bytes")
            require(row["pre_read_sha256"] == row["post_read_sha256"] == record["sha256"], f"{object_id}: closure SHA")
        elif fmt == ".fbt":
            require(row["closure_status"] == "forbidden_not_read", f"{object_id}: FBT was not kept closed")
            require(row["body_read_authorized"] is False and row["body_read_performed"] is False, f"{object_id}: FBT flags")
        else:
            require(row["closure_status"] == "manifest_bound_not_read", f"{object_id}: sidecar closure status")
            require(row["body_read_authorized"] is False and row["body_read_performed"] is False, f"{object_id}: sidecar flags")
    field_names = {"time_utc", "line_id", "native_ping_id", "native_beam_id", "longitude", "latitude", "heading", "native_quality", "native_quality_code", "horizontal_datum", "vertical_datum", "depth"}
    require(set(ledger["field_name"]) == field_names, "field ledger field set mismatch")
    for row in ledger.to_dict(orient="records"):
        record = expected_objects[str(row["source_object_id"])]
        require(row["source_object_relative_path"] == record["relative_path"] and row["source_object_sha256"] == record["sha256"], "field ledger object binding mismatch")
        require(row["field_status"] in FIVE_LEVEL_STATUS, "field ledger status invalid")
        if str(record["format"]) == ".mb58.gz" and row["field_name"] in {"time_utc", "longitude", "latitude", "heading", "native_quality", "depth"}:
            if row["field_status"] != "known" and row["evidence_kind"] not in {"parser_preflight_failure", "parser_contract_failure"}:
                raise AssertionError(f"primary parser field status mismatch: {row}")
    return objects, contributors, candidates, ledger, expected_objects


def verify_soundings(run_dir: Path, objects: pd.DataFrame, expected_objects: dict[str, dict[str, Any]]) -> tuple[dict[tuple[str, str, str], dict[str, Any]], int, str, dict[str, int]]:
    path = run_dir / "sounding_lineage.parquet"
    object_info = {str(row["source_object_id"]): row for row in objects.to_dict(orient="records")}
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    object_rows: defaultdict[str, int] = defaultdict(int)
    last_key: dict[str, tuple[int, int]] = {}
    last_ping: dict[str, int] = {}
    eligible_count = 0
    digest = hashlib.sha256()
    review_count = 0
    for batch in pq.ParquetFile(path).iter_batches(batch_size=50_000):
        for row in batch.to_pylist():
            object_id = str(row["source_object_id"])
            require(object_id in object_info, f"sounding references unknown object: {object_id}")
            obj = object_info[object_id]
            require(row["source_object_relative_path"] == obj["source_object_relative_path"], "sounding path binding mismatch")
            require(row["source_object_sha256"] == obj["source_object_sha256"], "sounding content binding mismatch")
            require(row["official_cruise_id"] == obj["official_cruise_id"], "sounding cruise binding mismatch")
            require(row["time_utc"] is not None and row["time_utc_status"] == "known", "sounding time contract failure")
            require(row["processing_run_id"] == run_dir.name and row["acquisition_run_id"] == ACQUISITION_RUN_ID, "sounding run binding mismatch")
            ping = int(row["parser_ping_index"])
            beam = int(row["beam_index"])
            require(ping >= 0 and beam >= 0, "negative parser or beam key")
            pair = (ping, beam)
            if object_id in last_key:
                require(pair != last_key[object_id], "duplicate sounding primary key")
                require(ping >= last_ping[object_id], "parser ping order regressed")
            last_key[object_id] = pair
            last_ping[object_id] = ping
            require(row["native_quality_state"] in {"good", "flagged", "null"}, "invalid native quality state")
            lon = float(row["lon_deg"])
            lat = float(row["lat_deg"])
            nav_ok = math.isfinite(lon) and -180.0 <= lon < 180.0 and math.isfinite(lat) and -90.0 <= lat <= 90.0
            depth = row["depth_m_positive_down"]
            depth_ok = depth is not None and math.isfinite(float(depth)) and 0.0 < float(depth) <= 12_000.0
            expected_hard = row["native_quality_state"] == "good" and nav_ok and depth_ok
            require(bool(row["qc_hard_pass"]) == expected_hard, "hard QC flag mismatch")
            require(bool(row["qc_eligible_for_cell"]) == expected_hard, "cell eligibility mismatch")
            if row["native_quality_state"] != "good":
                require(depth is None and row["elev_m"] is None, "non-good sounding has depth")
            if depth is not None:
                require(close_number(row["elev_m"], -float(depth)), "positive-down elevation identity failed")
            if nav_ok:
                lon_bin, lat_bin, cell_id = cell_assignment(lon, lat)
                require((row["lon_bin"], row["lat_bin"], row["cell_id"]) == (lon_bin, lat_bin, cell_id), "cell assignment mismatch")
            else:
                require(row["lon_bin"] is None and row["lat_bin"] is None and row["cell_id"] is None, "invalid navigation assigned to cell")
            require(bool(row["held_out"]) and not bool(row["use_for_training"]) and not bool(row["use_for_tuning"]) and not bool(row["use_for_threshold_selection"]), "held-out role flags changed")
            require(row["role_v2_h"] == "held_out_candidate_mrar_out" and row["role_v2_w"] == "blocked_source_independence_unknown", "role branch changed")
            require(row["confirmation_role_eligible"] is False, "confirmation role promoted")
            require(row["parser_name"] == "MB-System" and row["parser_version"] == "5.8.3beta16", "parser binding changed")
            require(row["parser_source_commit"] == "1d9a52ce076c3c3c5f0150b9bcaa30fa108c7422", "parser source commit changed")
            require(row["depth_unit"] == "m" and row["depth_direction"] == "positive_down", "depth unit contract changed")
            review_codes = row["qc_review_codes"] or []
            require(review_codes == sorted(review_codes), "review codes are not canonical")
            review_count += bool(review_codes)
            object_rows[object_id] += 1
            if row["cell_id"] is not None:
                key = (str(row["cell_id"]), str(row["official_cruise_id"]), object_id)
                state = groups.setdefault(key, {"n_soundings_all": 0, "n_native_good": 0, "n_native_flagged": 0, "n_native_null": 0, "n_qc_eligible": 0, "n_review": 0, "time_start": None, "time_end": None})
                state["n_soundings_all"] += 1
                state[f"n_native_{row['native_quality_state']}"] += 1
                state["n_qc_eligible"] += bool(row["qc_eligible_for_cell"])
                state["n_review"] += bool(review_codes)
                epoch_us = int(pd.Timestamp(row["time_utc"]).value // 1_000)
                state["time_start"] = epoch_us if state["time_start"] is None else min(state["time_start"], epoch_us)
                state["time_end"] = epoch_us if state["time_end"] is None else max(state["time_end"], epoch_us)
                if row["qc_eligible_for_cell"]:
                    eligible_count += 1
                    digest.update(eligible_token(str(row["cell_id"]), str(row["official_cruise_id"]), object_id, ping, float(depth), epoch_us))
    expected_count = sum(int(row["parsed_row_count"]) for row in objects.to_dict(orient="records") if row["parse_status"] == "pass")
    require(sum(object_rows.values()) == expected_count, "sounding count does not close to processing table")
    return groups, eligible_count, digest.hexdigest(), {"sounding_rows": sum(object_rows.values()), "reviewed_rows": review_count}


def stats_by_group(database: sqlite3.Connection, *, per_object: bool) -> dict[tuple[str, ...], dict[str, Any]]:
    columns = "cell_id,cruise_id,source_object_id,depth" if per_object else "cell_id,cruise_id,depth"
    order = "cell_id,cruise_id,source_object_id,depth" if per_object else "cell_id,cruise_id,depth"
    result: dict[tuple[str, ...], dict[str, Any]] = {}
    current_key: tuple[str, ...] | None = None
    values: list[float] = []
    for row in database.execute(f"SELECT {columns} FROM eligible ORDER BY {order}"):
        key = tuple(str(value) for value in row[:-1])
        if key != current_key:
            if current_key is not None:
                result[current_key] = aggregate(values)
            current_key = key
            values = []
        values.append(float(row[-1]))
    if current_key is not None:
        result[current_key] = aggregate(values)
    return result


def compare_aggregate_tables(run_dir: Path, contributors: pd.DataFrame, candidates: pd.DataFrame, groups: dict[tuple[str, str, str], dict[str, Any]], database: sqlite3.Connection) -> dict[str, int]:
    contributor_stats = stats_by_group(database, per_object=True)
    expected_contributor_keys = set(groups)
    actual_contributor_keys = {(str(row.cell_id), str(row.official_cruise_id), str(row.source_object_id)) for row in contributors.itertuples()}
    require(actual_contributor_keys == expected_contributor_keys, "contributor key set mismatch")
    for row in contributors.to_dict(orient="records"):
        key = (str(row["cell_id"]), str(row["official_cruise_id"]), str(row["source_object_id"]))
        state = groups[key]
        for field in ("n_soundings_all", "n_native_good", "n_native_flagged", "n_native_null", "n_qc_eligible", "n_review"):
            require(int(row[field]) == int(state[field]), f"contributor {key}: {field} mismatch")
        stats = contributor_stats.get(key)
        require((stats is None and state["n_qc_eligible"] == 0) or stats is not None, f"contributor {key}: database group mismatch")
        stats = stats or {"median": None, "nmad": None}
        require(close_number(row["median_depth_m_positive_down_exact"], stats["median"]), f"contributor {key}: median mismatch")
        require(close_number(row["nmad_depth_m_exact"], stats["nmad"]), f"contributor {key}: NMAD mismatch")
        require(row["vertical_datum"] is None and row["vertical_datum_status"] == "officially_unknown", f"contributor {key}: datum status")
    candidate_stats = stats_by_group(database, per_object=False)
    expected_candidate_keys = set()
    for cell, cruise, object_id in groups:
        if groups[(cell, cruise, object_id)]["n_qc_eligible"]:
            expected_candidate_keys.add((cell, cruise))
    actual_candidate_keys = {(str(row.cell_id), str(row.official_cruise_id)) for row in candidates.itertuples()}
    require(actual_candidate_keys == expected_candidate_keys, "candidate key set mismatch")
    contributor_by_candidate: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in contributors.to_dict(orient="records"):
        contributor_by_candidate[(str(row["cell_id"]), str(row["official_cruise_id"]))].append(row)
    for row in candidates.to_dict(orient="records"):
        key = (str(row["cell_id"]), str(row["official_cruise_id"]))
        lat_bin = int(str(row["cell_id"]).split("_")[1])
        lon_bin = int(str(row["cell_id"]).split("_")[2])
        lon_center, lat_center = cell_center(lon_bin, lat_bin)
        require((int(row["lon_bin"]), int(row["lat_bin"]), close_number(row["lon_center"], lon_center), close_number(row["lat_center"], lat_center)) == (lon_bin, lat_bin, True, True), f"candidate {key}: cell center")
        source_rows = contributor_by_candidate[key]
        totals = {field: sum(int(item[field]) for item in source_rows) for field in ("n_soundings_all", "n_native_good", "n_native_flagged", "n_native_null", "n_qc_eligible", "n_review")}
        for field, value in totals.items():
            require(int(row[field]) == value, f"candidate {key}: {field} mismatch")
        require(int(row["n_source_objects"]) == len(source_rows), f"candidate {key}: source object count")
        stats = candidate_stats[key]
        for field in ("median_depth_m_positive_down_exact", "mean_depth_m_positive_down_exact", "nmad_depth_m_exact", "q25_depth_m_exact", "q75_depth_m_exact", "min_depth_m", "max_depth_m", "range_depth_m"):
            stat_name = {"median_depth_m_positive_down_exact": "median", "mean_depth_m_positive_down_exact": "mean", "nmad_depth_m_exact": "nmad", "q25_depth_m_exact": "q25", "q75_depth_m_exact": "q75", "min_depth_m": "min", "max_depth_m": "max", "range_depth_m": "range"}[field]
            require(close_number(row[field], stats[stat_name]), f"candidate {key}: {field} mismatch")
        db_times = database.execute("SELECT MIN(epoch_us), MAX(epoch_us), COUNT(DISTINCT source_object_id || ':' || parser_ping_index) FROM eligible WHERE cell_id=? AND cruise_id=?", key).fetchone()
        require(int(row["n_unique_parser_pings"]) == int(db_times[2]), f"candidate {key}: unique ping count")
        require(row["time_start_utc"] is not None and row["time_end_utc"] is not None, f"candidate {key}: time coverage")
        require(int(pd.Timestamp(row["time_start_utc"]).value // 1_000) == int(db_times[0]) and int(pd.Timestamp(row["time_end_utc"]).value // 1_000) == int(db_times[1]), f"candidate {key}: time bounds")
        require(row["aggregation_basis"] == "individual_qc_eligible_beams_exact", f"candidate {key}: aggregation basis")
        require(bool(row["held_out"]) and not bool(row["use_for_training"]) and not bool(row["use_for_tuning"]) and not bool(row["use_for_threshold_selection"]), f"candidate {key}: role flags")
        require(row["role_v2_h"] == "held_out_candidate_mrar_out" and row["role_v2_w"] == "blocked_source_independence_unknown" and row["confirmation_role_eligible"] is False, f"candidate {key}: role branch")
        require(row["vertical_datum"] is None and row["vertical_datum_status"] == "officially_unknown", f"candidate {key}: datum status")
    return {"contributor_rows": len(contributors), "candidate_rows": len(candidates), "contributor_groups": len(contributor_stats), "candidate_groups": len(candidate_stats)}


def verify_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    require(run_dir.parent == STAGE_C_ROOT.resolve(), "run is outside fixed Stage C root")
    require(RUN_ID_RE.fullmatch(run_dir.name) is not None and ".." not in run_dir.name, "unsafe processing run ID")
    verification_path = run_dir / "verification.json"
    require(not verification_path.exists(), "verification already exists; run is immutable")
    audit = load_json(run_dir / "audit_manifest.json")
    receipt = load_json(run_dir / "authorization_receipt.json")
    require(audit["status"] == "processed_pending_independent_verification", "producer run is not pending verification")
    require(audit["processing_run_id"] == run_dir.name and receipt["processing_run_id"] == run_dir.name, "run ID mismatch")
    require(receipt["stage_c_authorized"] is True and receipt["confirmation_role_eligible"] is False, "authorization role mismatch")
    require(canonical_authorization_receipt_sha256(receipt) == receipt["authorization_receipt_sha256"], "authorization canonical hash mismatch")
    require(sha256_file(PROCESSOR_PATH) == receipt["processor_sha256"], "processor hash binding mismatch")
    require(sha256_file(HELPER_PATH) == receipt["processing_helper_sha256"], "helper hash binding mismatch")
    require(sha256_file(VERIFIER_PATH) == receipt["verifier_sha256"], "verifier hash binding mismatch")
    require(receipt["fixed_output_root"] == str(STAGE_C_ROOT.resolve()), "output root binding mismatch")
    require(receipt["acquisition_run_id"] == ACQUISITION_RUN_ID and receipt["immutable_primary_cruise_ids"] == PRIMARY_IDS, "input identity binding mismatch")
    require(receipt["sealed_archive_manifest_sha256"] == MANIFEST_SHA256 and receipt["stage_b_verification_sha256"] == STAGE_B_VERIFICATION_SHA256, "Stage B binding mismatch")
    require(receipt["stage_c1a_readiness_manifest_sha256"] == C1A_MANIFEST_SHA256 and receipt["stage_c1a_readiness_verification_sha256"] == C1A_VERIFICATION_SHA256, "C1a binding mismatch")
    for flag in ("gebco_or_product_comparison_authorized", "model_comparison_authorized", "mrar_merge_authorized", "cross_cruise_aggregation_authorized", "datum_or_bias_fit_authorized", "confirmation_role_promotion_authorized"):
        require(receipt.get(flag) is False, f"prohibited authorization flag enabled: {flag}")
    manifest, _stage_b_verification, _stage_b_access = verify_manifest_metadata()
    require(audit["sealed_archive_manifest_sha256"] == MANIFEST_SHA256 and audit["stage_b_verification_sha256"] == STAGE_B_VERIFICATION_SHA256, "audit input binding mismatch")
    for filename, descriptor in audit["output_files"].items():
        path = run_dir / filename
        require(path.is_file(), f"audit output missing: {filename}")
        require(int(descriptor["bytes"]) == path.stat().st_size and descriptor["sha256"] == sha256_file(path), f"audit output hash mismatch: {filename}")
    objects, contributors, candidates, _ledger, expected_objects = verify_object_tables(run_dir, manifest)
    groups, eligible_count, sounding_digest, sounding_counts = verify_soundings(run_dir, objects, expected_objects)
    access = load_json(run_dir / "access_lock.json")
    require(access["sealed_object_body_read_count"] == 192 and access["decompression_count"] == 192, "body/decompression count mismatch")
    require(access["mb58_body_read_count"] == 192 and access["fnv_body_read_count"] == 0 and access["inf_body_read_count"] == 0 and access["fbt_body_read_count"] == 0, "sidecar body access mismatch")
    require(access["candidate_sounding_row_count"] == sounding_counts["sounding_rows"] and access["candidate_cell_cruise_contributor_row_count"] == len(contributors) and access["candidate_cell_row_count"] == len(candidates), "access row counts mismatch")
    require(access["external_product_or_model_reference_count"] == 0 and access["mrar_merge_count"] == 0 and access["cross_cruise_aggregation_count"] == 0 and access["datum_or_bias_fit_count"] == 0 and access["confirmation_role_eligible"] is False, "access policy counters changed")
    database_path = run_dir / "aggregation.sqlite"
    database = sqlite3.connect(database_path)
    try:
        db_count = int(database.execute("SELECT COUNT(*) FROM eligible").fetchone()[0])
        require(db_count == eligible_count, "eligible database count mismatch")
        db_digest = hashlib.sha256()
        for row in database.execute("SELECT cell_id,cruise_id,source_object_id,parser_ping_index,depth,epoch_us FROM eligible ORDER BY rowid"):
            db_digest.update(eligible_token(str(row[0]), str(row[1]), str(row[2]), int(row[3]), float(row[4]), int(row[5])))
        require(db_digest.hexdigest() == sounding_digest, "eligible sounding/database digest mismatch")
        aggregate_counts = compare_aggregate_tables(run_dir, contributors, candidates, groups, database)
    finally:
        database.close()
    command_lines = [json.loads(line) for line in (run_dir / "command_ledger.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    require(len(command_lines) == 192 * 4, "command ledger count mismatch")
    require(set(item["role"] for item in command_lines) == {"decompression", "mbinfo", "mblist_u3", "mblist_u0"}, "command ledger role set mismatch")
    result = {
        "schema_version": 3,
        "status": "pass",
        "stage": "C_source_internal_candidate_processing",
        "run_dir": str(run_dir),
        "authorization_receipt_canonical_sha256": receipt["authorization_receipt_sha256"],
        "authorization_receipt_file_sha256": sha256_file(run_dir / "authorization_receipt.json"),
        "sealed_archive_manifest_sha256": MANIFEST_SHA256,
        "stage_b_verification_sha256": STAGE_B_VERIFICATION_SHA256,
        "stage_c1a_readiness_manifest_sha256": C1A_MANIFEST_SHA256,
        "stage_c1a_readiness_verification_sha256": C1A_VERIFICATION_SHA256,
        "source_object_count": len(objects),
        "sounding_row_count": sounding_counts["sounding_rows"],
        "eligible_sounding_row_count": eligible_count,
        "contributor_row_count": len(contributors),
        "candidate_row_count": len(candidates),
        "failed_invalid_time_object_count": int((objects["parse_status"] == "failed_invalid_or_missing_time").sum()),
        "failed_parser_contract_object_count": int((objects["parse_status"] == "failed_parser_contract").sum()),
        "reviewed_sounding_row_count": sounding_counts["reviewed_rows"],
        "sealed_object_body_read_count": access["sealed_object_body_read_count"],
        "archive_decompression_count": access["decompression_count"],
        "sidecar_body_read_counts": {".fnv": 0, ".inf": 0, ".fbt": 0},
        "output_table_sha256": {filename: sha256_file(run_dir / filename) for filename in TABLE_KEYS},
        "aggregate_checks": aggregate_counts,
        "independent_verifier_opened_sealed_body": False,
        "parser_invocation_count": 0,
        "external_product_or_model_reference_count": 0,
        "mrar_merge_count": 0,
        "cross_cruise_aggregation_count": 0,
        "datum_or_bias_fit_count": 0,
        "content_parsed": True,
        "role_v2_h": "held_out_candidate_mrar_out",
        "role_v2_w": "blocked_source_independence_unknown",
        "confirmation_role_eligible": False,
        "stage_c_authorized": True,
        "stage_d_confirmation_evaluation_authorized": False,
    }
    verification_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    result = verify_run(parser.parse_args().run_dir)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
