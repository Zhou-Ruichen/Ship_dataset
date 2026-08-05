#!/usr/bin/env python3
"""Independently verify an SCS sealed-confirmation Stage A receipt.

Purpose
-------
Recompute Stage A schema, hash, exposure, selection, MRAR, and no-access gates
from persisted metadata artifacts. This verifier does not import the producer,
contact official services, or access candidate archives.

Reads
-----
One immutable Stage A discovery run.

Writes
------
``verification.json`` in that run, only when every check passes.

Usage
-----
Run from the repository root::

    python ncei/code/verify_scs_v2_sealed_confirmation.py \
      --run-dir ncei/derived/scs_v2_sealed_confirmation/discovery/<RUN_ID>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
FIELD_STATUSES = {
    "known",
    "officially_unknown",
    "not_recoverable",
    "inferred_from_filename",
    "verified_from_source_metadata",
}
REQUIRED_CANDIDATE_COLUMNS = {
    "official_cruise_id", "archive", "date", "instrument", "bbox",
    "file_count", "available_fields", "vertical_datum_status",
    "overlap_with_current_19", "overlap_with_exposed_12",
    "possible_MRAR_overlap", "ever_read_by_repo", "sealed_status",
    "exclusion_reason", "geometry_intersects_scs", "geometry_basis",
    "scs_track_length_km",
}
REQUIRED_OUTPUTS = {
    "candidate_registry": "candidate_registry.parquet",
    "exposure_registry": "exposure_registry.parquet",
    "repository_file_inventory": "repository_file_inventory.tsv",
    "metadata_evidence_registry": "metadata_evidence_registry.tsv",
    "query_command_ledger": "query_command_ledger.jsonl",
    "negative_result_ledger": "negative_result_ledger.tsv",
    "mrar_bounded_followup": "mrar_bounded_followup.tsv",
    "preseal_lock": "preseal_lock.json",
    "audit_report": "audit_report.md",
}
FORBIDDEN_QUERY_ROLES = {"candidate_archive", "candidate_archive_member", "candidate_sounding"}
FORBIDDEN_OUTPUT_TOKENS = {
    "cell_depth", "corrected_depth", "crossover", "gebco", "model_residual",
    "pinn", "prediction", "product_residual", "sounding_depth",
}


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def normalize_cruise_id(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = re.sub(r"_MULTIBEAM$", "", text)
    return re.sub(r"[^A-Z0-9]+", "-", text).strip("-")


def cruise_aliases(value: Any) -> set[str]:
    normalized = normalize_cruise_id(value)
    if not normalized:
        return set()
    return {alias for alias in {normalized, re.sub(r"-LEG-?\d+$", "", normalized)} if alias}


def inventory_identity_paths(inventory: pd.DataFrame, cruise_id: str) -> list[str]:
    aliases = cruise_aliases(cruise_id)
    paths = []
    for path in inventory["relative_path"].astype(str):
        normalized_path = normalize_cruise_id(path)
        if any(re.search(rf"(?:^|-){re.escape(alias)}(?:-|$)", normalized_path) for alias in aliases):
            paths.append(path)
    return paths


def candidate_rank_key(row: Any) -> tuple[Any, ...]:
    fields = json.loads(row.available_fields)
    field_count = sum(value == "verified_from_source_metadata" for value in fields.values())
    metadata_complete = sum(
        value not in (None, "") and not pd.isna(value)
        for value in (row.date, row.instrument, row.bbox, row.archive, row.file_count, row.license)
    )
    mrar_order = {"false": 0, "unknown": 1, "true": 2}.get(row.possible_MRAR_overlap, 1)
    return (
        mrar_order,
        -float(row.scs_track_length_km),
        0 if bool(row.raw_archive_documented) else 1,
        -field_count,
        0 if bool(row.vertical_datum) else 1,
        -metadata_complete,
        normalize_cruise_id(row.official_cruise_id),
    )


def clip_segment_to_area(
    first: tuple[float, float],
    second: tuple[float, float],
    area: dict[str, float],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    x1, y1 = first
    x2, y2 = second
    while x2 - x1 > 180.0:
        x2 -= 360.0
    while x2 - x1 < -180.0:
        x2 += 360.0
    for shift in (-360.0, 0.0, 360.0):
        xmin = area["xmin"] + shift
        xmax = math.nextafter(area["xmax"] + shift, float("-inf"))
        ymin = area["ymin"]
        ymax = math.nextafter(area["ymax"], float("-inf"))
        dx, dy = x2 - x1, y2 - y1
        lower, upper = 0.0, 1.0
        accepted = True
        for pi, qi in zip((-dx, dx, -dy, dy), (x1 - xmin, xmax - x1, y1 - ymin, ymax - y1)):
            if pi == 0.0:
                if qi < 0.0:
                    accepted = False
                    break
                continue
            ratio = qi / pi
            if pi < 0.0:
                lower = max(lower, ratio)
            else:
                upper = min(upper, ratio)
            if lower > upper:
                accepted = False
                break
        if accepted:
            return (
                (x1 + lower * dx - shift, y1 + lower * dy),
                (x1 + upper * dx - shift, y1 + upper * dy),
            )
    return None


def segment_intersects_area(first: tuple[float, float], second: tuple[float, float], area: dict[str, float]) -> bool:
    return clip_segment_to_area(first, second, area) is not None


def haversine_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, first)
    lon2, lat2 = map(math.radians, second)
    dlon, dlat = lon2 - lon1, lat2 - lat1
    value = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    return 6371.0088 * 2.0 * math.asin(min(1.0, math.sqrt(value)))


def geometry_track_length_in_area_km(geometry: dict[str, Any], area: dict[str, float]) -> float:
    total = 0.0
    for key in ("paths", "rings"):
        for part in geometry.get(key, []) or []:
            points = [(float(point[0]), float(point[1])) for point in part if len(point) >= 2]
            for first, second in zip(points, points[1:]):
                clipped = clip_segment_to_area(first, second, area)
                if clipped is not None:
                    total += haversine_km(*clipped)
    return total


def geometry_intersects_area(geometry: dict[str, Any], area: dict[str, float]) -> bool:
    for key in ("paths", "rings"):
        for part in geometry.get(key, []) or []:
            points = [(float(point[0]), float(point[1])) for point in part if len(point) >= 2]
            if any(segment_intersects_area(first, second, area) for first, second in zip(points, points[1:])):
                return True
            if len(points) == 1 and segment_intersects_area(points[0], points[0], area):
                return True
    for point in geometry.get("points", []) or []:
        if len(point) >= 2:
            value = (float(point[0]), float(point[1]))
            if segment_intersects_area(value, value, area):
                return True
    if "x" in geometry and "y" in geometry:
        value = (float(geometry["x"]), float(geometry["y"]))
        return segment_intersects_area(value, value, area)
    return False


def official_geometry_results(evidence: pd.DataFrame, area: dict[str, float]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    spatial = evidence[evidence["role"].eq("ncei_arcgis_spatial_query")]
    if spatial.empty:
        raise AssertionError("metadata evidence lacks NCEI spatial query response")
    for path in spatial["path"]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        for feature in payload.get("features", []):
            survey_id = normalize_cruise_id((feature.get("attributes") or {}).get("SURVEY_ID"))
            if not survey_id:
                continue
            geometry = feature.get("geometry") or {}
            record = results.setdefault(survey_id, {"intersects": False, "track_length_km": 0.0})
            record["intersects"] = record["intersects"] or geometry_intersects_area(geometry, area)
            record["track_length_km"] += geometry_track_length_in_area_km(geometry, area)
    return results


def atomic_json(value: Any, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def dataframe_schema(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{"name": column, "dtype": str(frame[column].dtype), "nullable": bool(frame[column].isna().any())} for column in frame.columns]


def check_status_pairs(frame: pd.DataFrame, name: str) -> dict[str, int]:
    missing = []
    invalid: dict[str, list[str]] = {}
    status_columns = {
        column for column in frame.columns
        if column.endswith("_status") and column.removesuffix("_status") in frame.columns
    }
    for column in frame.columns:
        if column in status_columns:
            unexpected = sorted(set(frame[column].dropna().astype(str)) - FIELD_STATUSES)
            if unexpected:
                invalid[column] = unexpected
        elif f"{column}_status" not in frame.columns:
            missing.append(column)
    if missing or invalid:
        raise AssertionError(f"{name} five-level status failure: missing={missing}, invalid={invalid}")
    return {
        "value_columns": len(frame.columns) - len(status_columns),
        "status_columns": len(status_columns),
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise AssertionError(f"invalid JSONL line {line_number}: {error}") from error
    return rows


def verify_manifest(run_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("stage") != "A_metadata_only":
        raise AssertionError("manifest stage is not A_metadata_only")
    if set(manifest.get("field_statuses", [])) != FIELD_STATUSES:
        raise AssertionError("manifest factual status vocabulary drift")
    if manifest.get("selection_policy", {}).get("minimum_required") != 0:
        raise AssertionError("zero-candidate outcome is not permitted by manifest")
    if manifest.get("selection_policy", {}).get("maximum_selected") > 5:
        raise AssertionError("manifest permits more than five selected candidates")
    guards = manifest.get("prohibited_actions", {})
    expected_guards = {
        "stage_b_authorized": False,
        "candidate_archive_download_count": 0,
        "candidate_archive_enumeration_count": 0,
        "candidate_depth_read": False,
        "cell_generation_count": 0,
        "reference_or_model_comparison_count": 0,
        "ggm_run_count": 0,
        "pinn_run_count": 0,
    }
    if guards != expected_guards:
        raise AssertionError(f"Stage A prohibited-action guard mismatch: {guards}")
    if manifest.get("stage_b_requires_separate_user_approval") is not True:
        raise AssertionError("manifest does not retain separate Stage B approval gate")

    input_checks = {}
    for role, record in manifest["inputs"].items():
        path = Path(record["path"])
        actual = sha256_file(path)
        input_checks[role] = actual == record["sha256"]
        if not input_checks[role]:
            raise AssertionError(f"frozen input hash drift: {role}")

    output_checks = {}
    for role, filename in REQUIRED_OUTPUTS.items():
        record = manifest["outputs"].get(role)
        if record is None:
            raise AssertionError(f"manifest missing output role: {role}")
        path = run_dir / filename
        if Path(record["path"]).resolve() != path.resolve():
            raise AssertionError(f"manifest output path mismatch: {role}")
        actual = sha256_file(path)
        output_checks[role] = actual == record["sha256"]
        if not output_checks[role]:
            raise AssertionError(f"output hash mismatch: {role}")
    evidence_checks = {}
    for evidence_id, record in manifest.get("metadata_evidence", {}).items():
        path = Path(record["path"])
        if path.parent.resolve() != (run_dir / "metadata_evidence").resolve():
            raise AssertionError(f"metadata evidence escaped run directory: {evidence_id}")
        actual = sha256_file(path)
        evidence_checks[evidence_id] = actual == record["sha256"]
        if not evidence_checks[evidence_id]:
            raise AssertionError(f"metadata evidence hash mismatch: {evidence_id}")
    return {"inputs": input_checks, "outputs": output_checks, "metadata_evidence": evidence_checks}


def verify_candidate_registry(
    candidate: pd.DataFrame,
    exposure: pd.DataFrame,
    file_inventory: pd.DataFrame,
    geometry_results: dict[str, dict[str, Any]],
    preseal: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    missing = sorted(REQUIRED_CANDIDATE_COLUMNS - set(candidate.columns))
    if missing:
        raise AssertionError(f"candidate registry missing columns: {missing}")
    status_check = check_status_pairs(candidate, "candidate_registry")
    if candidate["official_cruise_id"].duplicated().any():
        duplicated = candidate.loc[candidate["official_cruise_id"].duplicated(), "official_cruise_id"].tolist()
        raise AssertionError(f"duplicate candidate cruise IDs: {duplicated[:10]}")
    recomputed_geometry = candidate["official_cruise_id"].map(
        lambda value: geometry_results.get(normalize_cruise_id(value), {}).get("intersects", False)
    )
    if not recomputed_geometry.equals(candidate["geometry_intersects_scs"].astype(bool)):
        raise AssertionError("candidate official polyline/SCS intersection mismatch")
    if not candidate.loc[candidate["sealed_status"].eq("selected_unsealed"), "geometry_intersects_scs"].all():
        raise AssertionError("selected candidate official polyline does not intersect SCS")
    if not candidate["geometry_basis"].eq("official_polyline_segment_intersection").all():
        raise AssertionError("candidate geometry basis drift")
    recomputed_lengths = candidate["official_cruise_id"].map(
        lambda value: float(geometry_results.get(normalize_cruise_id(value), {}).get("track_length_km", 0.0))
    )
    if ((recomputed_lengths - candidate["scs_track_length_km"].astype(float)).abs() > 1e-9).any():
        raise AssertionError("candidate SCS track-length metadata mismatch")
    for column in ("overlap_with_current_19", "overlap_with_exposed_12", "possible_MRAR_overlap", "ever_read_by_repo"):
        invalid = set(candidate[column].astype(str)) - {"true", "false", "unknown"}
        if invalid:
            raise AssertionError(f"invalid tri-state in {column}: {sorted(invalid)}")
    invalid_sealed = set(candidate["sealed_status"].astype(str)) - {"excluded", "selected_unsealed"}
    if invalid_sealed:
        raise AssertionError(f"invalid sealed_status: {sorted(invalid_sealed)}")

    current_ids = set(exposure.loc[exposure["exposure_class"].eq("current_19"), "official_cruise_id"].astype(str))
    exposed_ids = set(exposure.loc[exposure["exposure_class"].eq("exposed_12"), "official_cruise_id"].astype(str))
    if len(current_ids) != 19 or len(exposed_ids) != 12 or not exposed_ids.issubset(current_ids):
        raise AssertionError("exposure registry 19/12 closure failed")
    if set(file_inventory.columns) != {"repository", "relative_path"}:
        raise AssertionError("repository file inventory schema drift")
    filesystem_hit_candidates = 0
    for row in candidate.itertuples(index=False):
        paths = inventory_identity_paths(file_inventory, row.official_cruise_id)
        if not paths:
            continue
        filesystem_hit_candidates += 1
        if row.ever_read_by_repo != "true" or row.sealed_status != "excluded":
            raise AssertionError(
                f"filesystem-exposed candidate not excluded: {row.official_cruise_id}"
            )
    recomputed_current = candidate["official_cruise_id"].isin(current_ids).map({True: "true", False: "false"})
    recomputed_exposed = candidate["official_cruise_id"].isin(exposed_ids).map({True: "true", False: "false"})
    # Exact IDs must close. Conservative alias matches may add true rows, but
    # can never turn an exact match false.
    if (candidate.loc[recomputed_current.eq("true"), "overlap_with_current_19"] != "true").any():
        raise AssertionError("exact current-19 overlap was not marked true")
    if (candidate.loc[recomputed_exposed.eq("true"), "overlap_with_exposed_12"] != "true").any():
        raise AssertionError("exact exposed-12 overlap was not marked true")

    selected = candidate[candidate["sealed_status"].eq("selected_unsealed")].sort_values("selection_rank")
    if len(selected) > 5:
        raise AssertionError("more than five candidates selected")
    if selected["selection_rank"].tolist() != list(range(1, len(selected) + 1)):
        raise AssertionError("selected ranks are not contiguous")
    qualified = candidate[candidate["exclusion_reason"].isin(["", "selection_limit_reached"])]
    recomputed_rank = [
        row.official_cruise_id
        for row in sorted(qualified.itertuples(index=False), key=candidate_rank_key)[:5]
    ]
    if recomputed_rank != selected["official_cruise_id"].astype(str).tolist():
        raise AssertionError("metadata-only candidate rank/selection mismatch")
    for column in ("overlap_with_current_19", "overlap_with_exposed_12", "ever_read_by_repo"):
        if not selected[column].eq("false").all():
            raise AssertionError(f"selected candidate has non-false {column}")
    if not selected["exclusion_reason"].eq("").all():
        raise AssertionError("selected candidate has exclusion reason")
    if not selected["candidate_qualification"].eq("qualified_for_stage_b_review").all():
        raise AssertionError("selected candidate qualification drift")
    if not selected.loc[selected["confirmation_role_eligible"], "possible_MRAR_overlap"].eq("false").all():
        raise AssertionError("confirmation-role eligible candidate lacks MRAR non-overlap")
    if preseal.get("stage_b_authorized") is not False:
        raise AssertionError("preseal lock authorizes Stage B")
    if preseal.get("candidate_archive_download_count") != 0 or preseal.get("candidate_archive_enumeration_count") != 0:
        raise AssertionError("preseal lock records candidate archive access")
    if preseal.get("candidate_depth_read") is not False or preseal.get("cell_generation_count") != 0 or preseal.get("reference_or_model_comparison_count") != 0:
        raise AssertionError("preseal lock records a prohibited computation")
    if preseal.get("selected_count") != len(selected):
        raise AssertionError("preseal selected count mismatch")
    if preseal.get("candidate_registry_sha256") != manifest["outputs"]["candidate_registry"]["sha256"]:
        raise AssertionError("preseal candidate registry hash mismatch")
    locked_ids = [item["official_cruise_id"] for item in preseal.get("selected_candidates", [])]
    if locked_ids != selected["official_cruise_id"].astype(str).tolist():
        raise AssertionError("preseal candidate ID/order mismatch")
    counts = manifest["candidate_counts"]
    expected_counts = {
        "official_records": len(candidate),
        "detail_evaluated": int(candidate["source_metadata_sha256"].ne("").sum()),
        "selected_unsealed": len(selected),
        "confirmation_role_eligible": int(selected["confirmation_role_eligible"].sum()),
        "excluded": int(candidate["sealed_status"].eq("excluded").sum()),
    }
    if counts != expected_counts:
        raise AssertionError(f"manifest candidate counts mismatch: {counts} != {expected_counts}")
    return {
        "row_count": len(candidate),
        "selected_unsealed": len(selected),
        "confirmation_role_eligible": int(selected["confirmation_role_eligible"].sum()),
        "status_pairs": status_check,
        "selected_ids": selected["official_cruise_id"].astype(str).tolist(),
        "filesystem_hit_candidates": filesystem_hit_candidates,
    }


def verify_queries(rows: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    if not rows:
        raise AssertionError("query command ledger is empty")
    archive_requests = []
    for row in rows:
        if row.get("request_role") in FORBIDDEN_QUERY_ROLES or row.get("candidate_archive_requested") is not False:
            archive_requests.append(row)
    if archive_requests:
        raise AssertionError("query ledger contains candidate archive/sounding access")
    metadata_gets = [row for row in rows if row.get("operation") == "official_metadata_get"]
    if not metadata_gets:
        raise AssertionError("no official metadata queries recorded")
    if any(row.get("method") != "GET" for row in metadata_gets):
        raise AssertionError("official metadata query used a non-GET method")
    if manifest["prohibited_actions"]["candidate_archive_download_count"] != 0:
        raise AssertionError("manifest archive download count is not zero")
    return {
        "row_count": len(rows),
        "official_metadata_gets": len(metadata_gets),
        "repository_identity_operations": sum(row.get("operation") == "repository_identity_audit" for row in rows),
        "candidate_archive_requests": 0,
    }


def verify_mrar(frame: pd.DataFrame, manifest: dict[str, Any]) -> dict[str, Any]:
    status_check = check_status_pairs(frame, "mrar_bounded_followup")
    if frame.empty or frame.iloc[-1]["check_id"] != "terminal":
        raise AssertionError("MRAR bounded follow-up lacks terminal row")
    terminal = frame.iloc[-1]
    if bool(terminal["direct_evidence_found"]):
        raise AssertionError("MRAR direct evidence was claimed; manual review required")
    if terminal["identity_status"] != "not_recoverable" or terminal["source_independence"] != "unknown":
        raise AssertionError("MRAR evidence ceiling was improperly upgraded")
    expected = {"identity_status": "not_recoverable", "source_independence": "unknown"}
    if manifest.get("mrar_terminal") != expected:
        raise AssertionError("manifest MRAR terminal mismatch")
    return {"row_count": len(frame), "terminal": expected, "status_pairs": status_check}


def verify_no_prohibited_outputs(run_dir: Path, candidate: pd.DataFrame) -> dict[str, Any]:
    forbidden_paths = []
    for path in run_dir.rglob("*"):
        if not path.is_file():
            continue
        lowered = path.name.lower()
        if any(token in lowered for token in FORBIDDEN_OUTPUT_TOKENS):
            forbidden_paths.append(str(path))
    if forbidden_paths:
        raise AssertionError(f"prohibited Stage A output paths: {forbidden_paths}")
    forbidden_columns = sorted(column for column in candidate.columns if any(token in column.lower() for token in FORBIDDEN_OUTPUT_TOKENS))
    if forbidden_columns:
        raise AssertionError(f"prohibited Stage A output columns: {forbidden_columns}")
    archive_like = []
    evidence_dir = run_dir / "metadata_evidence"
    for path in evidence_dir.iterdir():
        if path.suffix.lower() in {".7z", ".dat", ".gz", ".kmall", ".nc", ".rar", ".s7k", ".tar", ".tgz", ".xyz", ".zip"}:
            archive_like.append(str(path))
    if archive_like:
        raise AssertionError(f"archive-like evidence files found in Stage A: {archive_like}")
    return {"forbidden_paths": 0, "forbidden_columns": 0, "archive_like_files": 0}


def verify(run_dir: Path) -> dict[str, Any]:
    if Path.cwd().resolve() != REPO_ROOT:
        raise AssertionError(f"run verifier from repository root: {REPO_ROOT}")
    verification_path = run_dir / "verification.json"
    if verification_path.exists():
        raise FileExistsError(f"verification receipt already exists: {verification_path}")
    manifest_path = run_dir / "audit_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hash_checks = verify_manifest(run_dir, manifest)
    candidate = pd.read_parquet(run_dir / "candidate_registry.parquet")
    exposure = pd.read_parquet(run_dir / "exposure_registry.parquet")
    file_inventory = pd.read_csv(run_dir / "repository_file_inventory.tsv", sep="\t", keep_default_na=False)
    evidence = pd.read_csv(run_dir / "metadata_evidence_registry.tsv", sep="\t", keep_default_na=False)
    negatives = pd.read_csv(run_dir / "negative_result_ledger.tsv", sep="\t", keep_default_na=False)
    mrar = pd.read_csv(run_dir / "mrar_bounded_followup.tsv", sep="\t", keep_default_na=False)
    preseal = json.loads((run_dir / "preseal_lock.json").read_text(encoding="utf-8"))
    queries = read_jsonl(run_dir / "query_command_ledger.jsonl")
    geometry_results = official_geometry_results(evidence, manifest["study_area"])
    for row in evidence.itertuples(index=False):
        path = Path(row.path)
        if path.parent.resolve() != (run_dir / "metadata_evidence").resolve() or not path.is_file():
            raise AssertionError(f"metadata evidence registry path is not immutable/existing: {path}")
        manifest_record = manifest["metadata_evidence"].get(row.evidence_id)
        if manifest_record is None or Path(manifest_record["path"]).resolve() != path.resolve():
            raise AssertionError(f"metadata evidence registry/manifest path mismatch: {row.evidence_id}")
    for row in queries:
        if row.get("response_path"):
            response_path = Path(row["response_path"])
            if response_path.parent.resolve() != (run_dir / "metadata_evidence").resolve() or not response_path.is_file():
                raise AssertionError(f"query ledger response path is not immutable/existing: {response_path}")

    for role, frame in {
        "candidate_registry": candidate,
        "exposure_registry": exposure,
        "repository_file_inventory": file_inventory,
        "metadata_evidence_registry": evidence,
        "negative_result_ledger": negatives,
        "mrar_bounded_followup": mrar,
    }.items():
        recorded = manifest["outputs"][role]
        if recorded["row_count"] != len(frame):
            raise AssertionError(f"manifest row count mismatch: {role}")
        if "schema" in recorded and recorded["schema"] != dataframe_schema(frame):
            raise AssertionError(f"manifest schema mismatch: {role}")
    if len(queries) != manifest["outputs"]["query_command_ledger"]["row_count"]:
        raise AssertionError("manifest query ledger row count mismatch")

    result = {
        "status": "pass",
        "stage": "A_metadata_only",
        "run_dir": str(run_dir.resolve()),
        "manifest_sha256": sha256_file(manifest_path),
        "hash_checks": hash_checks,
        "candidate_registry": verify_candidate_registry(
            candidate, exposure, file_inventory, geometry_results, preseal, manifest
        ),
        "query_ledger": verify_queries(queries, manifest),
        "mrar": verify_mrar(mrar, manifest),
        "prohibited_output_checks": verify_no_prohibited_outputs(run_dir, candidate),
        "metadata_evidence_rows": len(evidence),
        "negative_result_rows": len(negatives),
        "stage_b_authorized": False,
        "candidate_archive_download_count": 0,
        "candidate_archive_enumeration_count": 0,
        "candidate_depth_read": False,
        "cell_generation_count": 0,
        "reference_or_model_comparison_count": 0,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    result = verify(run_dir)
    verification_path = run_dir / "verification.json"
    atomic_json(result, verification_path)
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"verification_sha256={sha256_file(verification_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
