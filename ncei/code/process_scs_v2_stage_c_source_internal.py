#!/usr/bin/env python3
"""Authorized source-internal Stage C processing for the sealed cruise set."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ncei.code.scs_v2_stage_c1_contract import cell_assignment, cell_center
from ncei.code.scs_v2_stage_c_processing import (
    FIELD_NAMES,
    PASS_STATUS,
    PARSER_FAILURE_STATUS,
    RAW_SCHEMA,
    SIDECAR_STATUS,
    TIME_FAILURE_STATUS,
    ParquetAppender,
    aggregate_stats,
    canonical_authorization_receipt_sha256,
    canonical_sha256,
    datetime_from_us,
    load_output_schemas,
    ping_review_codes,
    query_depths,
    safe_processing_run_id,
    sha256_file,
    source_field_ledger,
    source_object_id,
    source_processing_row,
    STAGE_C2_1_READINESS_ROOT,
    STAGE_C2_1_TEMPLATE_PATH,
    sounding_batch_table,
    _raw_from_object,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SEALED_ROOT = REPO_ROOT / "ncei/archive/scs_v2_sealed_confirmation/20260805T230449Z"
STAGE_C_ROOT = REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/stage_c"
READINESS_ROOT = STAGE_C2_1_READINESS_ROOT
SCHEMA_PATH = REPO_ROOT / ".trellis/tasks/08-06-scs-v2-stage-c0-source-internal-planning/research/stage-c01-output-schema.yaml"
PROCESSING_FORMATS = {".mb58.gz"}
SIDECAR_FORMATS = {".fnv", ".inf", ".fbt"}
PRIMARY_IDS = ["EQT20210702", "EQT190012", "EQT180002", "TN352"]
ACQUISITION_RUN_ID = "20260805T230449Z"
MBSYSTEM_VERSION = "5.8.3beta16"
MBSYSTEM_COMMIT = "1d9a52ce076c3c3c5f0150b9bcaa30fa108c7422"
ENVIRONMENT_ROOT = REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/environments/mbsystem-5.8.3beta16-1d9a52ce"
GZIP = ENVIRONMENT_ROOT / "bin/gzip"
MBINFO = ENVIRONMENT_ROOT / "build/mbsystem/src/utilities/mbinfo"
MBLIST = ENVIRONMENT_ROOT / "build/mbsystem/src/utilities/mblist"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(value: Any, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_active_authorization(receipt_path: Path, processing_run_id: str) -> dict[str, Any]:
    receipt = load_json(receipt_path)
    require(receipt["stage_c_authorized"] is True, "Stage C authorization is inactive")
    require(receipt["processing_run_id"] == processing_run_id, "processing run ID mismatch")
    require(receipt["acquisition_run_id"] == ACQUISITION_RUN_ID, "acquisition run mismatch")
    require(receipt["immutable_primary_cruise_ids"] == PRIMARY_IDS, "cruise order mismatch")
    require(receipt["fixed_output_root"] == str(STAGE_C_ROOT.resolve()), "fixed output root mismatch")
    require(receipt["sealed_archive_manifest_sha256"] == "9fafb163a6fe2818d96a0c9bb0ed49afc98a8b0850979d5783b1882139702f94", "Stage B manifest binding mismatch")
    require(receipt["stage_b_verification_sha256"] == "d0d868f560c628bd24d1d52d399c7ed9d03af337be72967a874a5c26db7c2e86", "Stage B verification binding mismatch")
    require(receipt["stage_c1a_readiness_manifest_sha256"] == sha256_file(READINESS_ROOT / "audit_manifest.json"), "C1a manifest binding mismatch")
    require(receipt["stage_c1a_readiness_verification_sha256"] == sha256_file(READINESS_ROOT / "verification.json"), "C1a verification binding mismatch")
    require(receipt["authorization_template_sha256"] == sha256_file(STAGE_C2_1_TEMPLATE_PATH), "C2.1 authorization template mismatch")
    require(receipt["parser_environment_digest"] == load_json(READINESS_ROOT / "environment_lock.json")["environment_digest"], "environment digest mismatch")
    for key in (
        "gebco_or_product_comparison_authorized",
        "model_comparison_authorized",
        "mrar_merge_authorized",
        "cross_cruise_aggregation_authorized",
        "datum_or_bias_fit_authorized",
        "confirmation_role_promotion_authorized",
        "confirmation_role_eligible",
    ):
        require(receipt.get(key) is False, f"authorization enables prohibited action: {key}")
    require(sha256_file(REPO_ROOT / "ncei/code/process_scs_v2_stage_c_source_internal.py") == receipt["processor_sha256"], "processor hash mismatch")
    require(sha256_file(REPO_ROOT / "ncei/code/verify_scs_v2_stage_c_processing.py") == receipt["verifier_sha256"], "verifier hash mismatch")
    require(sha256_file(REPO_ROOT / "ncei/code/scs_v2_stage_c_processing.py") == receipt["processing_helper_sha256"], "processing helper hash mismatch")
    require(canonical_authorization_receipt_sha256(receipt) == receipt["authorization_receipt_sha256"], "authorization receipt canonical hash mismatch")
    return receipt


def load_manifest() -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    manifest_path = SEALED_ROOT / "sealed_archive_manifest.parquet"
    require(sha256_file(manifest_path) == "9fafb163a6fe2818d96a0c9bb0ed49afc98a8b0850979d5783b1882139702f94", "sealed archive manifest hash mismatch")
    manifest = pd.read_parquet(manifest_path)
    require(len(manifest) == 768, "manifest object count mismatch")
    require(int(manifest["bytes"].sum()) == 9_626_893_507, "manifest byte total mismatch")
    require(manifest["official_cruise_id"].drop_duplicates().tolist() == PRIMARY_IDS, "manifest cruise order mismatch")
    require(set(manifest["format"]) == {".mb58.gz", ".fnv", ".inf", ".fbt"}, "manifest format set mismatch")
    require((manifest["content_parsed"] == False).all(), "Stage B content_parsed is not false")
    require(manifest["expected_last_modified"].notna().all(), "Stage B Last-Modified binding missing")
    require(manifest["expected_last_modified"].astype(str).str.strip().ne("").all(), "Stage B Last-Modified binding empty")
    verification = load_json(SEALED_ROOT / "verification.json")
    require(sha256_file(SEALED_ROOT / "verification.json") == "d0d868f560c628bd24d1d52d399c7ed9d03af337be72967a874a5c26db7c2e86", "Stage B verification hash mismatch")
    require(verification["status"] == "pass" and verification["checks"]["content_parsed"] is False, "Stage B verification is not sealed pass")
    access = load_json(SEALED_ROOT / "access_lock.json")
    require(sha256_file(SEALED_ROOT / "access_lock.json") == "75c290a9b4f17ed2b529a372417f4fd18770c08cf66836c07ddde3bb90e00a6f", "Stage B access lock hash mismatch")
    return manifest.sort_values("relative_path").reset_index(drop=True), verification, access


def append_command(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def run_command(argv: list[str], *, stdout_path: Path | None, stderr_path: Path, ledger_path: Path, object_id: str, role: str) -> subprocess.CompletedProcess[str]:
    if stdout_path is None:
        completed = subprocess.run(argv, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
        stdout_bytes = completed.stdout.encode()
        stderr_bytes = completed.stderr.encode()
    else:
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            completed_raw = subprocess.run(argv, cwd=REPO_ROOT, stdout=stdout_handle, stderr=stderr_handle, check=False)
        stdout_bytes = stdout_path.read_bytes()
        stderr_bytes = stderr_path.read_bytes()
        completed = subprocess.CompletedProcess(argv, completed_raw.returncode, stdout_bytes.decode("utf-8", "replace"), stderr_bytes.decode("utf-8", "replace"))
    append_command(
        ledger_path,
        {
            "object_id": object_id,
            "role": role,
            "argv": argv,
            "argv_sha256": canonical_sha256(argv),
            "returncode": completed.returncode,
            "stdout_sha256": __import__("hashlib").sha256(stdout_bytes).hexdigest(),
            "stderr_sha256": __import__("hashlib").sha256(stderr_bytes).hexdigest(),
        },
    )
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {argv!r}")
    return completed


def empty_aggregation_db(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE eligible (cell_id TEXT NOT NULL, cruise_id TEXT NOT NULL, source_object_id TEXT NOT NULL, parser_ping_index INTEGER NOT NULL, depth REAL NOT NULL, epoch_us INTEGER NOT NULL)"
    )
    connection.execute("CREATE INDEX eligible_group ON eligible(cell_id, cruise_id, source_object_id, depth)")
    connection.execute("CREATE INDEX eligible_candidate ON eligible(cell_id, cruise_id, depth)")
    return connection


def update_counts(counts: dict[tuple[str, str, str], dict[str, Any]], row: dict[str, Any]) -> None:
    cell_id = row["cell_id"]
    if cell_id is None:
        return
    key = (str(cell_id), str(row["official_cruise_id"]), str(row["source_object_id"]))
    item = counts.setdefault(
        key,
        {
            "n_soundings_all": 0,
            "n_native_good": 0,
            "n_native_flagged": 0,
            "n_native_null": 0,
            "n_qc_eligible": 0,
            "n_review": 0,
            "time_start_us": None,
            "time_end_us": None,
        },
    )
    item["n_soundings_all"] += 1
    item[f"n_native_{row['native_quality_state']}"] += 1
    if row["qc_eligible_for_cell"]:
        item["n_qc_eligible"] += 1
    if row["qc_review_codes"]:
        item["n_review"] += 1
    epoch_us = int(pd.Timestamp(row["time_utc"]).value // 1_000)
    item["time_start_us"] = epoch_us if item["time_start_us"] is None else min(item["time_start_us"], epoch_us)
    item["time_end_us"] = epoch_us if item["time_end_us"] is None else max(item["time_end_us"], epoch_us)


def update_counts_from_batch(counts: dict[tuple[str, str, str], dict[str, Any]], data: dict[str, list[Any]]) -> None:
    summary = pd.DataFrame(
        {
            "cell_id": data["cell_id"],
            "native_quality_state": data["native_quality_state"],
            "qc_eligible_for_cell": data["qc_eligible_for_cell"],
            "n_review": [bool(value) for value in data["qc_review_codes"]],
            "epoch_us": [int(pd.Timestamp(value).value // 1_000) for value in data["time_utc"]],
        }
    )
    summary = summary[summary["cell_id"].notna()]
    for cell_id, group in summary.groupby("cell_id", sort=False):
        key = (str(cell_id), str(data["official_cruise_id"][0]), str(data["source_object_id"][0]))
        item = counts.setdefault(
            key,
            {
                "n_soundings_all": 0,
                "n_native_good": 0,
                "n_native_flagged": 0,
                "n_native_null": 0,
                "n_qc_eligible": 0,
                "n_review": 0,
                "time_start_us": None,
                "time_end_us": None,
            },
        )
        quality_counts = group["native_quality_state"].value_counts()
        item["n_soundings_all"] += len(group)
        for quality in ("good", "flagged", "null"):
            item[f"n_native_{quality}"] += int(quality_counts.get(quality, 0))
        item["n_qc_eligible"] += int(group["qc_eligible_for_cell"].sum())
        item["n_review"] += int(group["n_review"].sum())
        start_us = int(group["epoch_us"].min())
        end_us = int(group["epoch_us"].max())
        item["time_start_us"] = start_us if item["time_start_us"] is None else min(item["time_start_us"], start_us)
        item["time_end_us"] = end_us if item["time_end_us"] is None else max(item["time_end_us"], end_us)


def process_one_mb58(
    object_record: dict[str, Any],
    *,
    processing_run_id: str,
    temp_dir: Path,
    schemas: dict[str, pa.Schema],
    global_sounding: ParquetAppender,
    database: sqlite3.Connection,
    counts: dict[tuple[str, str, str], dict[str, Any]],
    ledger_path: Path,
    command_ledger_path: Path,
    receipt: dict[str, Any],
    closure_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    relative = str(object_record["relative_path"])
    object_id = source_object_id(ACQUISITION_RUN_ID, relative)
    sealed_path = (SEALED_ROOT / relative).resolve()
    require(str(sealed_path).startswith(str(SEALED_ROOT.resolve()) + os.sep), "sealed path escaped root")
    require(sealed_path.is_file(), f"sealed object missing: {sealed_path}")
    require(sealed_path.stat().st_size == int(object_record["bytes"]), "sealed object byte mismatch before read")
    pre_hash = sha256_file(sealed_path)
    require(pre_hash == str(object_record["sha256"]), "sealed object SHA mismatch before read")
    object_index = __import__("hashlib").sha256(object_id.encode("utf-8")).hexdigest()[:16]
    work = temp_dir / "objects" / object_index
    work.mkdir(parents=True, exist_ok=True)
    decompressed = work / "input.mb58"
    u3 = work / "all_u3.tsv"
    u0 = work / "good_u0.tsv"
    mbinfo_path = work / "mbinfo.json"
    stderr_path = work / "command.stderr"
    gzip_argv = [str(GZIP), "-dc", "--", str(sealed_path)]
    run_command(gzip_argv, stdout_path=decompressed, stderr_path=stderr_path, ledger_path=command_ledger_path, object_id=object_id, role="decompression")
    decompressed_hash = sha256_file(decompressed)
    mbinfo_argv = [str(MBINFO), f"-I{decompressed}", "-F58", "-X1"]
    mbinfo_completed = run_command(mbinfo_argv, stdout_path=None, stderr_path=work / "mbinfo.stderr", ledger_path=command_ledger_path, object_id=object_id, role="mbinfo")
    mbinfo_path.write_text(mbinfo_completed.stdout, encoding="utf-8")
    u3_argv = [str(MBLIST), f"-I{decompressed}", "-F58", "-P1", "-L0", "-MA", "-U3", "-OMN#XYzH", f"-X{u3}"]
    u0_argv = [str(MBLIST), f"-I{decompressed}", "-F58", "-P1", "-L0", "-MA", "-U0", "-OMN#XYzH", f"-X{u0}"]
    run_command(u3_argv, stdout_path=None, stderr_path=work / "u3.stderr", ledger_path=command_ledger_path, object_id=object_id, role="mblist_u3")
    run_command(u0_argv, stdout_path=None, stderr_path=work / "u0.stderr", ledger_path=command_ledger_path, object_id=object_id, role="mblist_u0")
    command_hash = canonical_sha256([mbinfo_argv, u3_argv, u0_argv])
    raw_path = work / "raw_joined.parquet"
    try:
        total_rows, good_rows, error_code, error_detail = _raw_from_object(object_id, u3, u0, work / "u0.sqlite", raw_path)
        if error_code:
            time_failure = error_code in {"TIME_UTC_MISSING", "TIME_UTC_INVALID"}
            parse_status = TIME_FAILURE_STATUS if time_failure else PARSER_FAILURE_STATUS
            row = source_processing_row(
                processing_run_id,
                ACQUISITION_RUN_ID,
                object_record,
                object_id,
                body_read_authorized=True,
                body_read_performed=True,
                parser_name="MB-System",
                parser_version=MBSYSTEM_VERSION,
                parser_source_commit=MBSYSTEM_COMMIT,
                parser_environment_digest=receipt["parser_environment_digest"],
                command_sha256=command_hash,
                decompressed_sha256=decompressed_hash,
                parse_status=parse_status,
                parsed_row_count=0,
                error_code=error_code,
                error_detail=error_detail,
            )
            ledger_rows = source_field_ledger(
                str(object_record["official_cruise_id"]),
                object_id,
                relative,
                str(object_record["sha256"]),
                command_hash,
                parsed=False,
                time_failure=time_failure,
                parser_failure=not time_failure,
            )
            return row, ledger_rows
        review_by_ping = ping_review_codes(raw_path)
        object_stage = work / "sounding.parquet"
        stage_writer = ParquetAppender(object_stage, schemas["sounding_lineage.parquet"])
        eligible_rows: list[tuple[Any, ...]] = []
        for arrow_batch in pq.ParquetFile(raw_path).iter_batches(batch_size=50_000):
            table = sounding_batch_table(
                arrow_batch,
                processing_run_id,
                ACQUISITION_RUN_ID,
                object_record,
                receipt["parser_environment_digest"],
                command_hash,
                review_by_ping,
                schemas["sounding_lineage.parquet"],
            )
            stage_writer.append_table(table)
            data = table.to_pydict()
            update_counts_from_batch(counts, data)
            eligible_rows.extend(
                (
                    data["cell_id"][index],
                    data["official_cruise_id"][index],
                    data["source_object_id"][index],
                    int(data["parser_ping_index"][index]),
                    float(data["depth_m_positive_down"][index]),
                    int(pd.Timestamp(data["time_utc"][index]).value // 1_000),
                )
                for index, eligible in enumerate(data["qc_eligible_for_cell"])
                if eligible
            )
            if len(eligible_rows) >= 50_000:
                database.executemany("INSERT INTO eligible(cell_id,cruise_id,source_object_id,parser_ping_index,depth,epoch_us) VALUES (?,?,?,?,?,?)", eligible_rows)
                eligible_rows.clear()
        if eligible_rows:
            database.executemany("INSERT INTO eligible(cell_id,cruise_id,source_object_id,parser_ping_index,depth,epoch_us) VALUES (?,?,?,?,?,?)", eligible_rows)
        database.commit()
        stage_writer.close()
        for arrow_batch in pq.ParquetFile(object_stage).iter_batches(batch_size=50_000):
            global_sounding.append_table(arrow_batch)
        row = source_processing_row(
            processing_run_id,
            ACQUISITION_RUN_ID,
            object_record,
            object_id,
            body_read_authorized=True,
            body_read_performed=True,
            parser_name="MB-System",
            parser_version=MBSYSTEM_VERSION,
            parser_source_commit=MBSYSTEM_COMMIT,
            parser_environment_digest=receipt["parser_environment_digest"],
            command_sha256=command_hash,
            decompressed_sha256=decompressed_hash,
            parse_status=PASS_STATUS,
            parsed_row_count=total_rows,
            error_code=None,
            error_detail=None,
        )
        ledger_rows = source_field_ledger(str(object_record["official_cruise_id"]), object_id, relative, str(object_record["sha256"]), command_hash, parsed=True)
        return row, ledger_rows
    finally:
        post_hash = sha256_file(sealed_path)
        require(post_hash == pre_hash and sealed_path.stat().st_size == int(object_record["bytes"]), "sealed object changed during processing")
        closure_rows.append(
            {
                "source_object_id": object_id,
                "official_cruise_id": str(object_record["official_cruise_id"]),
                "source_object_relative_path": relative,
                "source_object_format": str(object_record["format"]),
                "source_object_role": str(object_record["source_object_role"]),
                "manifest_bytes": int(object_record["bytes"]),
                "manifest_sha256": str(object_record["sha256"]),
                "pre_read_bytes": int(sealed_path.stat().st_size),
                "pre_read_sha256": pre_hash,
                "post_read_bytes": int(sealed_path.stat().st_size),
                "post_read_sha256": post_hash,
                "body_read_authorized": True,
                "body_read_performed": True,
                "closure_status": "pass",
                "error": None,
            }
        )
        shutil.rmtree(work, ignore_errors=True)


def sidecar_rows(processing_run_id: str, object_record: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    relative = str(object_record["relative_path"])
    object_id = source_object_id(ACQUISITION_RUN_ID, relative)
    row = source_processing_row(
        processing_run_id,
        ACQUISITION_RUN_ID,
        object_record,
        object_id,
        body_read_authorized=False,
        body_read_performed=False,
        parser_name=None,
        parser_version=None,
        parser_source_commit=None,
        parser_environment_digest=None,
        command_sha256=None,
        decompressed_sha256=None,
        parse_status=SIDECAR_STATUS,
        parsed_row_count=0,
        error_code=None,
        error_detail="sidecar body not read under initial Stage C role contract",
    )
    ledger = source_field_ledger(str(object_record["official_cruise_id"]), object_id, relative, str(object_record["sha256"]), str(object_record["sha256"]), parsed=False)
    closure = {
        "source_object_id": object_id,
        "official_cruise_id": str(object_record["official_cruise_id"]),
        "source_object_relative_path": relative,
        "source_object_format": str(object_record["format"]),
        "source_object_role": str(object_record["source_object_role"]),
        "manifest_bytes": int(object_record["bytes"]),
        "manifest_sha256": str(object_record["sha256"]),
        "pre_read_bytes": None,
        "pre_read_sha256": None,
        "post_read_bytes": None,
        "post_read_sha256": None,
        "body_read_authorized": False,
        "body_read_performed": False,
        "closure_status": "manifest_bound_not_read" if str(object_record["format"]) != ".fbt" else "forbidden_not_read",
        "error": None,
    }
    return row, ledger, closure


def aggregate_outputs(
    processing_run_id: str,
    schemas: dict[str, pa.Schema],
    database: sqlite3.Connection,
    counts: dict[tuple[str, str, str], dict[str, Any]],
    contributor_path: Path,
    candidate_path: Path,
) -> tuple[int, int]:
    contributor_writer = ParquetAppender(contributor_path, schemas["cell_cruise_contributors.parquet"])
    contributor_rows: list[dict[str, Any]] = []
    for (cell_id, cruise_id, object_id), count in sorted(counts.items()):
        values = query_depths(database, cell_id, cruise_id, object_id)
        stats = aggregate_stats(values)
        relative = database.execute("SELECT source_object_relative_path FROM object_map WHERE source_object_id=?", (object_id,)).fetchone()[0]
        sha = database.execute("SELECT source_object_sha256 FROM object_map WHERE source_object_id=?", (object_id,)).fetchone()[0]
        contributor_rows.append(
            {
                "processing_run_id": processing_run_id,
                "cell_id": cell_id,
                "official_cruise_id": cruise_id,
                "source_object_id": object_id,
                "source_object_relative_path": relative,
                "source_object_sha256": sha,
                "n_soundings_all": count["n_soundings_all"],
                "n_native_good": count["n_native_good"],
                "n_native_flagged": count["n_native_flagged"],
                "n_native_null": count["n_native_null"],
                "n_qc_eligible": count["n_qc_eligible"],
                "n_review": count["n_review"],
                "median_depth_m_positive_down_exact": stats["median"],
                "nmad_depth_m_exact": stats["nmad"],
                "vertical_datum": None,
                "vertical_datum_status": "officially_unknown",
            }
        )
    contributor_writer.append(contributor_rows)
    contributor_writer.close()
    candidate_writer = ParquetAppender(candidate_path, schemas["cell_cruise_candidates.parquet"])
    candidate_rows: list[dict[str, Any]] = []
    grouped = sorted({(cell_id, cruise_id) for cell_id, cruise_id, _object_id in counts})
    for cell_id, cruise_id in grouped:
        contributor_group = [(key, value) for key, value in counts.items() if key[0] == cell_id and key[1] == cruise_id]
        eligible_count = sum(value["n_qc_eligible"] for _key, value in contributor_group)
        if eligible_count == 0:
            continue
        values = query_depths(database, cell_id, cruise_id)
        stats = aggregate_stats(values)
        lat_bin = int(cell_id.split("_")[1])
        lon_bin = int(cell_id.split("_")[2])
        lon_center, lat_center = cell_center(lon_bin, lat_bin)
        times = database.execute("SELECT MIN(epoch_us),MAX(epoch_us) FROM eligible WHERE cell_id=? AND cruise_id=?", (cell_id, cruise_id)).fetchone()
        unique_pings = database.execute("SELECT COUNT(DISTINCT source_object_id || ':' || parser_ping_index) FROM eligible WHERE cell_id=? AND cruise_id=?", (cell_id, cruise_id)).fetchone()[0]
        totals = {name: sum(value[name] for _key, value in contributor_group) for name in ("n_soundings_all", "n_native_good", "n_native_flagged", "n_native_null", "n_qc_eligible", "n_review")}
        candidate_rows.append(
            {
                "processing_run_id": processing_run_id,
                "cell_id": cell_id,
                "lon_bin": lon_bin,
                "lat_bin": lat_bin,
                "lon_center": lon_center,
                "lat_center": lat_center,
                "official_cruise_id": cruise_id,
                "official_cruise_id_status": "verified_from_source_metadata",
                "n_source_objects": len(contributor_group),
                **totals,
                "n_unique_parser_pings": int(unique_pings),
                "time_start_utc": datetime_from_us(int(times[0])) if times[0] is not None else None,
                "time_end_utc": datetime_from_us(int(times[1])) if times[1] is not None else None,
                "time_coverage_status": "known",
                "median_depth_m_positive_down_exact": stats["median"],
                "mean_depth_m_positive_down_exact": stats["mean"],
                "nmad_depth_m_exact": stats["nmad"],
                "q25_depth_m_exact": stats["q25"],
                "q75_depth_m_exact": stats["q75"],
                "min_depth_m": stats["min"],
                "max_depth_m": stats["max"],
                "range_depth_m": stats["range"],
                "aggregation_basis": "individual_qc_eligible_beams_exact",
                "vertical_datum": None,
                "vertical_datum_status": "officially_unknown",
                "held_out": True,
                "use_for_training": False,
                "use_for_tuning": False,
                "use_for_threshold_selection": False,
                "role_v2_h": "held_out_candidate_mrar_out",
                "role_v2_w": "blocked_source_independence_unknown",
                "confirmation_role_eligible": False,
            }
        )
    candidate_writer.append(candidate_rows)
    candidate_writer.close()
    return len(contributor_rows), len(candidate_rows)


def run_processing(receipt_path: Path, processing_run_id: str) -> Path:
    processing_run_id = safe_processing_run_id(processing_run_id)
    receipt = validate_active_authorization(receipt_path.resolve(), processing_run_id)
    manifest, _verification, _access = load_manifest()
    final_dir = STAGE_C_ROOT / processing_run_id
    require(not final_dir.exists(), "processing run already exists")
    STAGE_C_ROOT.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{processing_run_id}.tmp-", dir=STAGE_C_ROOT))
    try:
        (temp_dir / "logs").mkdir()
        (temp_dir / "parser").mkdir()
        (temp_dir / "decompressed").mkdir()
        shutil.copy2(receipt_path, temp_dir / "authorization_receipt.json")
        command_ledger_path = temp_dir / "command_ledger.jsonl"
        command_ledger_path.write_text("", encoding="utf-8")
        schemas = load_output_schemas(SCHEMA_PATH)
        global_sounding = ParquetAppender(temp_dir / "sounding_lineage.parquet", schemas["sounding_lineage.parquet"])
        processing_rows: list[dict[str, Any]] = []
        ledger_rows: list[dict[str, Any]] = []
        closure_rows: list[dict[str, Any]] = []
        counts: dict[tuple[str, str, str], dict[str, Any]] = {}
        database = empty_aggregation_db(temp_dir / "aggregation.sqlite")
        database.execute("CREATE TABLE object_map(source_object_id TEXT PRIMARY KEY, source_object_relative_path TEXT, source_object_sha256 TEXT)")
        body_read_count = 0
        decompression_count = 0
        failed_time_count = 0
        failed_parser_count = 0
        try:
            for object_record in manifest.to_dict(orient="records"):
                object_id = source_object_id(ACQUISITION_RUN_ID, str(object_record["relative_path"]))
                database.execute("INSERT INTO object_map VALUES (?,?,?)", (object_id, str(object_record["relative_path"]), str(object_record["sha256"])))
                if str(object_record["format"]) in PROCESSING_FORMATS:
                    body_read_count += 1
                    decompression_count += 1
                    row, object_ledger = process_one_mb58(
                        object_record,
                        processing_run_id=processing_run_id,
                        temp_dir=temp_dir,
                        schemas=schemas,
                        global_sounding=global_sounding,
                        database=database,
                        counts=counts,
                        ledger_path=temp_dir / "command_ledger.jsonl",
                        command_ledger_path=command_ledger_path,
                        receipt=receipt,
                        closure_rows=closure_rows,
                    )
                    processing_rows.append(row)
                    ledger_rows.extend(object_ledger)
                    if row["parse_status"] == TIME_FAILURE_STATUS:
                        failed_time_count += 1
                    elif row["parse_status"] != PASS_STATUS:
                        failed_parser_count += 1
                else:
                    row, object_ledger, closure = sidecar_rows(processing_run_id, object_record)
                    processing_rows.append(row)
                    ledger_rows.extend(object_ledger)
                    closure_rows.append(closure)
            database.commit()
            global_sounding.close()
            processing_writer = ParquetAppender(temp_dir / "source_object_processing.parquet", schemas["source_object_processing.parquet"])
            processing_writer.append(processing_rows)
            processing_writer.close()
            ledger_writer = ParquetAppender(temp_dir / "field_recovery_ledger.parquet", schemas["field_recovery_ledger.parquet"])
            ledger_writer.append(ledger_rows)
            ledger_writer.close()
            contributor_count, candidate_count = aggregate_outputs(
                processing_run_id,
                schemas,
                database,
                counts,
                temp_dir / "cell_cruise_contributors.parquet",
                temp_dir / "cell_cruise_candidates.parquet",
            )
        finally:
            database.close()

        closure_schema = pa.schema(
            [
                ("source_object_id", pa.string()),
                ("official_cruise_id", pa.string()),
                ("source_object_relative_path", pa.string()),
                ("source_object_format", pa.string()),
                ("source_object_role", pa.string()),
                ("manifest_bytes", pa.int64()),
                ("manifest_sha256", pa.string()),
                ("pre_read_bytes", pa.int64()),
                ("pre_read_sha256", pa.string()),
                ("post_read_bytes", pa.int64()),
                ("post_read_sha256", pa.string()),
                ("body_read_authorized", pa.bool_()),
                ("body_read_performed", pa.bool_()),
                ("closure_status", pa.string()),
                ("error", pa.string()),
            ]
        )
        closure_writer = ParquetAppender(temp_dir / "object_access_closure.parquet", closure_schema)
        closure_writer.append(closure_rows)
        closure_writer.close()
        shutil.copy2(READINESS_ROOT / "environment_lock.json", temp_dir / "environment.json")
        shutil.copy2(READINESS_ROOT / "fixture_verification.json", temp_dir / "fixture_verification.json")
        qc_summary = temp_dir / "qc_summary.tsv"
        with qc_summary.open("w", encoding="utf-8") as handle:
            handle.write("metric\tvalue\n")
            handle.write(f"sounding_rows\t{int(global_sounding.row_count)}\n")
            handle.write(f"contributor_rows\t{int(contributor_count)}\n")
            handle.write(f"candidate_rows\t{int(candidate_count)}\n")
            handle.write(f"failed_invalid_time_objects\t{int(failed_time_count)}\n")
            handle.write(f"failed_parser_contract_objects\t{int(failed_parser_count)}\n")
            handle.write("external_reference_inputs\t0\n")
        (temp_dir / "audit_report.md").write_text(
            "# Stage C source-internal processing\n\n"
            "This run contains source-derived lineage and per-cruise QC outputs only.\n"
            "No outside archive or cross-cruise operation was executed.\n",
            encoding="utf-8",
        )
        access_ledger = {
            "schema_version": 2,
            "stage": "C_source_internal_candidate_processing",
            "stage_b_objects_root_opened": True,
            "sealed_object_body_read_count": body_read_count,
            "decompression_count": decompression_count,
            "mb58_body_read_count": body_read_count,
            "fnv_body_read_count": 0,
            "inf_body_read_count": 0,
            "fbt_body_read_count": 0,
            "candidate_sounding_row_count": int(global_sounding.row_count),
            "candidate_cell_cruise_contributor_row_count": contributor_count,
            "candidate_cell_row_count": candidate_count,
            "failed_invalid_time_object_count": failed_time_count,
            "failed_parser_contract_object_count": failed_parser_count,
            "external_product_or_model_reference_count": 0,
            "mrar_merge_count": 0,
            "cross_cruise_aggregation_count": 0,
            "datum_or_bias_fit_count": 0,
            "confirmation_role_eligible": False,
        }
        atomic_json(access_ledger, temp_dir / "access_lock.json")
        output_files = [
            "authorization_receipt.json",
            "source_object_processing.parquet",
            "sounding_lineage.parquet",
            "cell_cruise_contributors.parquet",
            "cell_cruise_candidates.parquet",
            "field_recovery_ledger.parquet",
            "object_access_closure.parquet",
            "aggregation.sqlite",
            "environment.json",
            "fixture_verification.json",
            "qc_summary.tsv",
            "audit_report.md",
            "command_ledger.jsonl",
            "access_lock.json",
        ]
        outputs = {
            name: {
                "path": str((final_dir / name).resolve()),
                "bytes": (temp_dir / name).stat().st_size,
                "sha256": sha256_file(temp_dir / name),
                "rows": int(pq.ParquetFile(temp_dir / name).metadata.num_rows) if name.endswith(".parquet") else None,
            }
            for name in output_files
        }
        audit = {
            "schema_version": 1,
            "stage": "C_source_internal_candidate_processing",
            "status": "processed_pending_independent_verification",
            "processing_run_id": processing_run_id,
            "acquisition_run_id": ACQUISITION_RUN_ID,
            "authorization_receipt_sha256": sha256_file(temp_dir / "authorization_receipt.json"),
            "sealed_archive_manifest_sha256": receipt["sealed_archive_manifest_sha256"],
            "stage_b_verification_sha256": receipt["stage_b_verification_sha256"],
            "stage_c1a_readiness_manifest_sha256": receipt["stage_c1a_readiness_manifest_sha256"],
            "stage_c1a_readiness_verification_sha256": receipt["stage_c1a_readiness_verification_sha256"],
            "parser_environment_digest": receipt["parser_environment_digest"],
            "primary_cruise_ids": PRIMARY_IDS,
            "output_files": outputs,
            "body_read_scope": {".mb58.gz": body_read_count, ".fnv": 0, ".inf": 0, ".fbt": 0},
            "external_product_or_model_inputs": [],
            "confirmation_role_eligible": False,
            "access_summary": access_ledger,
        }
        atomic_json(audit, temp_dir / "audit_manifest.json")
        os.replace(temp_dir, final_dir)
        return final_dir
    except BaseException as error:
        failure = {
            "schema_version": 1,
            "stage": "C_source_internal_candidate_processing",
            "status": "failed_processing",
            "processing_run_id": processing_run_id,
            "error_type": type(error).__name__,
            "error": str(error),
            "body_read_scope": {
                ".mb58.gz": int(locals().get("body_read_count", 0)),
                ".fnv": 0,
                ".inf": 0,
                ".fbt": 0,
            },
            "decompression_count": int(locals().get("decompression_count", 0)),
            "completed_source_object_count": len(locals().get("processing_rows", [])),
            "completed_closure_count": len(locals().get("closure_rows", [])),
            "stage_c_authorized": True,
            "confirmation_role_eligible": False,
            "sealed_source_modified": False,
            "retry_requires_new_processing_run": True,
        }
        try:
            atomic_json(failure, temp_dir / "failure_receipt.json")
            os.replace(temp_dir, final_dir)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization-receipt", required=True, type=Path)
    parser.add_argument("--processing-run-id", required=True)
    parser.add_argument("--confirm-stage-c", action="store_true")
    args = parser.parse_args()
    if not args.confirm_stage_c:
        print("ERROR: --confirm-stage-c is required", file=sys.stderr)
        return 2
    run_dir = run_processing(args.authorization_receipt, args.processing_run_id)
    print(json.dumps({"status": "processed_pending_independent_verification", "run_dir": str(run_dir)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
