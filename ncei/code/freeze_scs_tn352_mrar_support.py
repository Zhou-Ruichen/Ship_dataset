#!/usr/bin/env python3
"""Freeze Phase B inputs and common-cell identity before any depth read."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import yaml

from ncei.code.scs_tn352_audit_common import (
    MRAR_CELLS_PATH,
    MRAR_POINTS_PATH,
    PROTOCOL_PATH,
    REPO_ROOT,
    STAGE_C_ROOT,
    TASK_ROOT,
    one_min_cell,
    path_record,
    read_json,
    require,
    sha256_file,
    tree_record,
    write_json,
)


EXPECTED_PROTOCOL_SHA256 = "f6aeda56757964b601482825b71690b04d1e3799351e4246febad54e569bb0a0"
COHORT_AMENDMENT_PATH = TASK_ROOT / "research/support-protocol-v1-cohort-amendment.yaml"
EXPECTED_COHORT_AMENDMENT_SHA256 = "b2d375382a5c1d2a9ef56f8c54a3e17d12902ac61eb5ea2c51d035fb295b2045"
FROZEN_ASSIGNMENTS_PATH = Path(
    "/mnt/data2/06-Projects/12-ggm_scs/.trellis/tasks/archive/2026-08/"
    "08-09-scs-new-data-literature-random-interpolation/research/runs/preflight/"
    "20260809T_context_v3_preflight/paired_split_assignments.parquet"
)
EXPECTED_FROZEN_ASSIGNMENTS_SHA256 = "c7c3aacc0a33d680e3800162220e720776a8c475247562b9315a5588656d5efb"
EXPECTED_COMMON_CELLS = 2_244
EXPECTED_RAW_SUPPORT_COMMON_CELLS = 2_367
EXPECTED_RAW_SUPPORT_ONLY_CELLS = 123
EXPECTED_TN352_WITHOUT_RAW_SUPPORT_CELLS = 1
TN352 = "TN352"
FROZEN_ASSIGNMENT_COLUMNS = [
    "split",
    "cell_id",
    "sorted_input_index",
    "permutation_position",
    "role",
]
NON_DEPTH_STAGE_C_COLUMNS = [
    "cell_id",
    "lon_bin",
    "lat_bin",
    "lon_center",
    "lat_center",
    "official_cruise_id",
    "n_source_objects",
    "n_qc_eligible",
    "n_unique_parser_pings",
    "aggregation_basis",
]
NON_DEPTH_MRAR_COLUMNS = [
    "cell_id",
    "lon_bin",
    "lat_bin",
    "lon_center",
    "lat_center",
    "source_provider",
    "branch",
    "branch_role",
    "n_points_pass_total",
    "n_tracks",
    "dominant_file_id",
    "source_dataset",
]
NON_DEPTH_MRAR_POINT_COLUMNS = ["lon", "lat", "point_check_pass_basic"]


def assert_common_cell_count(observed: int, expected: int = EXPECTED_COMMON_CELLS) -> None:
    require(observed == expected, f"common-cell gate failed: {observed} != {expected}")


def cell_sort_key(cell_id: str) -> tuple[int, int]:
    prefix, lat_bin, lon_bin = cell_id.split("_")
    require(prefix == "1min", f"invalid cell ID prefix: {cell_id}")
    return int(lat_bin), int(lon_bin)


def compare_cell_id_sets(
    frozen_cell_ids: list[str],
    tn352_cell_ids: set[str],
    mrar_raw_support_cell_ids: set[str],
    *,
    expected_frozen_count: int = EXPECTED_COMMON_CELLS,
) -> dict[str, list[str]]:
    frozen = set(frozen_cell_ids)
    assert_common_cell_count(len(frozen_cell_ids), expected_frozen_count)
    require(len(frozen) == len(frozen_cell_ids), "frozen assignment cell IDs are not unique")
    for cell_id in frozen | tn352_cell_ids | mrar_raw_support_cell_ids:
        cell_sort_key(cell_id)
    raw_support_common = tn352_cell_ids & mrar_raw_support_cell_ids
    return {
        "frozen_scalar_pair": sorted(frozen, key=cell_sort_key),
        "frozen_missing_tn352": sorted(frozen - tn352_cell_ids, key=cell_sort_key),
        "frozen_missing_raw_support": sorted(frozen - raw_support_common, key=cell_sort_key),
        "raw_support_common": sorted(raw_support_common, key=cell_sort_key),
        "raw_support_only_not_in_frozen_scalar_pair": sorted(raw_support_common - frozen, key=cell_sort_key),
        "tn352_without_mrar_raw_support": sorted(tn352_cell_ids - mrar_raw_support_cell_ids, key=cell_sort_key),
    }


def validate_cell_row(row: dict[str, Any], source: str) -> None:
    lon_bin, lat_bin, cell_id, lon_center, lat_center = one_min_cell(
        float(row["lon_center"]), float(row["lat_center"])
    )
    require(str(row["cell_id"]) == cell_id, f"{source} cell ID formula differs: {row['cell_id']}")
    require(int(row["lon_bin"]) == lon_bin and int(row["lat_bin"]) == lat_bin, f"{source} bin formula differs: {cell_id}")
    require(abs(float(row["lon_center"]) - lon_center) <= 1.0e-12, f"{source} longitude center differs: {cell_id}")
    require(abs(float(row["lat_center"]) - lat_center) <= 1.0e-12, f"{source} latitude center differs: {cell_id}")


def validate_matching_cell_rows(tn352_row: dict[str, Any], mrar_row: dict[str, Any]) -> None:
    cell_id = str(tn352_row["cell_id"])
    require(int(tn352_row["lon_bin"]) == int(mrar_row["lon_bin"]), f"source longitude bin differs: {cell_id}")
    require(int(tn352_row["lat_bin"]) == int(mrar_row["lat_bin"]), f"source latitude bin differs: {cell_id}")
    require(
        abs(float(tn352_row["lon_center"]) - float(mrar_row["lon_center"])) <= 1.0e-12,
        f"source longitude center differs: {cell_id}",
    )
    require(
        abs(float(tn352_row["lat_center"]) - float(mrar_row["lat_center"])) <= 1.0e-12,
        f"source latitude center differs: {cell_id}",
    )


def read_frozen_assignments() -> list[dict[str, Any]]:
    require(
        sha256_file(FROZEN_ASSIGNMENTS_PATH) == EXPECTED_FROZEN_ASSIGNMENTS_SHA256,
        "frozen assignment hash drift",
    )
    rows = pq.read_table(FROZEN_ASSIGNMENTS_PATH, columns=FROZEN_ASSIGNMENT_COLUMNS).to_pylist()
    assert_common_cell_count(len(rows))
    require(len({str(row["cell_id"]) for row in rows}) == len(rows), "frozen assignment cell IDs are not unique")
    require({str(row["split"]) for row in rows} == {"paired"}, "frozen assignment split differs")
    require({str(row["role"]) for row in rows} <= {"control", "check"}, "frozen assignment role differs")
    expected_indices = set(range(len(rows)))
    require({int(row["sorted_input_index"]) for row in rows} == expected_indices, "sorted input indices differ")
    require({int(row["permutation_position"]) for row in rows} == expected_indices, "permutation positions differ")
    return rows


def read_mrar_raw_support_cell_ids() -> set[str]:
    dataset = ds.dataset(MRAR_POINTS_PATH, format="parquet")
    raw_filter = (
        ds.field("point_check_pass_basic")
        & (ds.field("lon") >= 105.0)
        & (ds.field("lon") < 125.0)
        & (ds.field("lat") >= 0.0)
        & (ds.field("lat") < 25.0)
    )
    table = dataset.to_table(columns=["lon", "lat"], filter=raw_filter)
    lon = table.column("lon").to_numpy(zero_copy_only=False)
    lat = table.column("lat").to_numpy(zero_copy_only=False)
    require(np.all(np.isfinite(lon) & np.isfinite(lat)), "MRAR raw-support coordinates are non-finite")
    lon_bin = np.floor((lon + 180.0) * 60.0).astype(np.int64)
    lat_bin = np.floor((lat + 90.0) * 60.0).astype(np.int64)
    return {f"1min_{lat_value}_{lon_value}" for lon_value, lat_value in zip(lon_bin, lat_bin)}


def build_cell_id_audit() -> tuple[
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
]:
    assignments = read_frozen_assignments()
    tn_table = pq.read_table(
        STAGE_C_ROOT / "cell_cruise_candidates.parquet",
        columns=NON_DEPTH_STAGE_C_COLUMNS,
        filters=[("official_cruise_id", "=", TN352)],
    )
    tn_rows = [
        row
        for row in tn_table.to_pylist()
        if 105.0 <= float(row["lon_center"]) < 125.0 and 0.0 <= float(row["lat_center"]) < 25.0
    ]
    require(len(tn_rows) == 2_368, "TN352 SCS candidate count differs before cohort join")
    require(len({row["cell_id"] for row in tn_rows}) == len(tn_rows), "TN352 SCS cell IDs are not unique")
    for row in tn_rows:
        validate_cell_row(row, "TN352")
        require(
            row["aggregation_basis"] == "individual_qc_eligible_beams_exact",
            f"TN352 aggregation basis differs: {row['cell_id']}",
        )
    mrar_dataset = ds.dataset(MRAR_CELLS_PATH, format="parquet", partitioning="hive")
    mrar_filter = (
        (ds.field("lon_center") >= 105.0)
        & (ds.field("lon_center") < 125.0)
        & (ds.field("lat_center") >= 0.0)
        & (ds.field("lat_center") < 25.0)
    )
    mrar_rows = mrar_dataset.to_table(columns=NON_DEPTH_MRAR_COLUMNS, filter=mrar_filter).to_pylist()
    require(len({row["cell_id"] for row in mrar_rows}) == len(mrar_rows), "MRAR SCS cell IDs are not unique")
    for row in mrar_rows:
        validate_cell_row(row, "MRAR")
        require(row["source_provider"] == "mrar", f"MRAR provider differs: {row['cell_id']}")
        require(row["branch"] == "regional_mrar", f"MRAR branch differs: {row['cell_id']}")
        require(row["branch_role"] == "regional_experiment", f"MRAR role differs: {row['cell_id']}")
    tn_by_cell = {str(row["cell_id"]): row for row in tn_rows}
    mrar_by_cell = {str(row["cell_id"]): row for row in mrar_rows}
    mrar_raw_support_ids = read_mrar_raw_support_cell_ids()
    comparison_sets = compare_cell_id_sets(
        [str(row["cell_id"]) for row in assignments],
        set(tn_by_cell),
        mrar_raw_support_ids,
    )
    comparison = {
        "schema_version": 1,
        "status": "pass"
        if not comparison_sets["frozen_missing_tn352"] and not comparison_sets["frozen_missing_raw_support"]
        else "fail",
        "selection_basis": "cell_id_only_before_depth_access",
        "frozen_assignment_path": str(FROZEN_ASSIGNMENTS_PATH),
        "frozen_assignment_sha256": EXPECTED_FROZEN_ASSIGNMENTS_SHA256,
        "counts": {name: len(values) for name, values in comparison_sets.items()},
        "cell_ids": comparison_sets,
        "depth_value_columns_read": [],
        "depth_difference_columns_read": [],
    }
    all_ids = sorted(set(tn_by_cell) | set(comparison_sets["frozen_scalar_pair"]), key=cell_sort_key)
    frozen_ids = set(comparison_sets["frozen_scalar_pair"])
    raw_support_ids = set(comparison_sets["raw_support_common"])
    status_rows = []
    for cell_id in all_ids:
        in_frozen = cell_id in frozen_ids
        in_tn352 = cell_id in tn_by_cell
        in_raw_support = cell_id in raw_support_ids
        if in_frozen and not in_tn352:
            status = "frozen_scalar_pair_missing_tn352"
        elif in_frozen and not in_raw_support:
            status = "frozen_scalar_pair_missing_mrar_raw_support"
        elif in_frozen:
            status = "frozen_scalar_pair"
        elif in_raw_support:
            status = "raw_support_only_not_in_frozen_scalar_pair"
        else:
            status = "tn352_without_mrar_raw_support"
        status_rows.append(
            {
                "cell_id": cell_id,
                "in_frozen_scalar_pair": in_frozen,
                "in_tn352_candidate": in_tn352,
                "in_mrar_raw_support": in_raw_support,
                "analysis_status": status,
                "included_in_phase_b": status == "frozen_scalar_pair",
            }
        )
    return assignments, tn_by_cell, mrar_by_cell, comparison, status_rows


def build_common_cohort(
    assignments: list[dict[str, Any]],
    tn_by_cell: dict[str, dict[str, Any]],
    mrar_by_cell: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    assignment_by_cell = {str(row["cell_id"]): row for row in assignments}
    output = []
    for cell_id in sorted(assignment_by_cell, key=cell_sort_key):
        require(cell_id in tn_by_cell, f"frozen cell absent from TN352 candidates: {cell_id}")
        require(cell_id in mrar_by_cell, f"frozen cell absent from MRAR labels: {cell_id}")
        assignment = assignment_by_cell[cell_id]
        tn_row = tn_by_cell[cell_id]
        mrar_row = mrar_by_cell[cell_id]
        validate_matching_cell_rows(tn_row, mrar_row)
        output.append(
            {
                "cell_id": cell_id,
                "lon_bin": int(tn_row["lon_bin"]),
                "lat_bin": int(tn_row["lat_bin"]),
                "lon_center": float(tn_row["lon_center"]),
                "lat_center": float(tn_row["lat_center"]),
                "tn352_official_cruise_id": TN352,
                "tn352_n_source_objects_all_soundings": int(tn_row["n_source_objects"]),
                "tn352_n_qc_eligible": int(tn_row["n_qc_eligible"]),
                "tn352_n_unique_parser_pings": int(tn_row["n_unique_parser_pings"]),
                "mrar_source_provider": str(mrar_row["source_provider"]),
                "mrar_branch": str(mrar_row["branch"]),
                "mrar_branch_role": str(mrar_row["branch_role"]),
                "mrar_n_points_pass_total": int(mrar_row["n_points_pass_total"]),
                "mrar_n_tracks": int(mrar_row["n_tracks"]),
                "mrar_dominant_file_id": str(mrar_row["dominant_file_id"]),
                "mrar_source_dataset": str(mrar_row["source_dataset"]),
                "frozen_split": str(assignment["split"]),
                "frozen_role": str(assignment["role"]),
                "frozen_sorted_input_index": int(assignment["sorted_input_index"]),
                "frozen_permutation_position": int(assignment["permutation_position"]),
            }
        )
    return output


def input_records(phase_a: Path) -> dict[str, dict[str, Any]]:
    return {
        "phase_a_manifest": path_record(phase_a / "audit_manifest.json"),
        "phase_a_verification": path_record(phase_a / "verification.json"),
        "frozen_scalar_pair_assignments": path_record(FROZEN_ASSIGNMENTS_PATH, with_schema=True),
        "stage_c_sounding_lineage": path_record(STAGE_C_ROOT / "sounding_lineage.parquet", with_schema=True),
        "stage_c_candidate_labels": path_record(STAGE_C_ROOT / "cell_cruise_candidates.parquet", with_schema=True),
        "mrar_checked_points": path_record(MRAR_POINTS_PATH, with_schema=True),
        "mrar_cell_labels": tree_record(MRAR_CELLS_PATH, with_schema=True),
        "source_protocol": path_record(PROTOCOL_PATH),
        "cohort_amendment": path_record(COHORT_AMENDMENT_PATH),
        "freeze_code": path_record(Path(__file__)),
        "support_code": path_record(REPO_ROOT / "ncei/code/scs_tn352_support.py"),
        "support_producer": path_record(REPO_ROOT / "ncei/code/audit_scs_tn352_mrar_support.py"),
        "support_verifier": path_record(REPO_ROOT / "ncei/code/verify_scs_tn352_mrar_support_audit.py"),
    }


def freeze(run_dir: Path, phase_a: Path) -> Path:
    run_dir = run_dir.resolve()
    phase_a = phase_a.resolve()
    require(run_dir.parent == (REPO_ROOT / "ncei/derived/scs_tn352_processing_and_support_audit").resolve(), "run directory outside audit root")
    phase_b = run_dir / "phase_b"
    failed_root = run_dir.parent / f"{run_dir.name}.failed" / "phase_b"
    require(phase_a.is_dir(), "Phase A directory missing")
    require(not phase_b.exists(), "Phase B already exists")
    require(not failed_root.exists(), "Phase B failed directory already exists")
    phase_a_verification = read_json(phase_a / "verification.json")
    require(phase_a_verification["status"] == "pass", "Phase A verification is not pass")
    require(phase_a_verification["run_id"] == "20260809T174007Z", "Phase A accepted run differs")
    require(phase_a_verification["depth_difference_with_mrar_read_count"] == 0, "Phase A read MRAR depth differences")
    require(sha256_file(phase_a / "audit_manifest.json") == phase_a_verification["audit_manifest_sha256"], "Phase A manifest hash differs")
    task = read_json(TASK_ROOT / "task.json")
    require(task["status"] == "in_progress", "Trellis task is not in progress")
    require(sha256_file(PROTOCOL_PATH) == EXPECTED_PROTOCOL_SHA256, "source protocol hash drift")
    require(
        sha256_file(COHORT_AMENDMENT_PATH) == EXPECTED_COHORT_AMENDMENT_SHA256,
        "cohort amendment hash drift",
    )
    temp = Path(tempfile.mkdtemp(prefix=".phase_b.freeze-", dir=run_dir))
    comparison: dict[str, Any] | None = None
    try:
        source_protocol = yaml.safe_load(PROTOCOL_PATH.read_text(encoding="utf-8"))
        cohort_amendment = yaml.safe_load(COHORT_AMENDMENT_PATH.read_text(encoding="utf-8"))
        require(source_protocol["status"] == "proposed_pending_user_review", "source protocol status differs")
        require(cohort_amendment["status"] == "approved_by_user", "cohort amendment is not approved")
        require(
            cohort_amendment["frozen_assignment"]["sha256"] == EXPECTED_FROZEN_ASSIGNMENTS_SHA256,
            "cohort amendment assignment hash differs",
        )
        source_protocol["protocol_id"] = "tn352_mrar_support_v1_frozen_scalar_pair"
        source_protocol["status"] = "approved_frozen"
        source_protocol["cohort"]["frozen_assignment"] = cohort_amendment["frozen_assignment"]
        source_protocol["cohort"]["provenance"] = cohort_amendment["provenance"]
        source_protocol["cohort"]["current_raw_support_gate"] = cohort_amendment["current_raw_support_gate"]
        source_protocol["cohort"]["analysis_set"] = "all_cell_ids_in_frozen_assignment"
        source_protocol["cohort"]["raw_support_only_action"] = "record_and_exclude_from_source_difference_analysis"
        source_protocol["activation_evidence"] = {
            "trellis_task_status": task["status"],
            "planning_commit": "88d88ea85e07ed6b8e564dc70851c9286fc976bc",
            "source_protocol_sha256": EXPECTED_PROTOCOL_SHA256,
            "cohort_amendment_sha256": EXPECTED_COHORT_AMENDMENT_SHA256,
            "frozen_assignment_sha256": EXPECTED_FROZEN_ASSIGNMENTS_SHA256,
            "phase_a_verification_sha256": sha256_file(phase_a / "verification.json"),
            "user_authorization": "2026-08-10: use all 2,244 supplied cell IDs if fully contained in current MRAR raw support",
        }
        write_json(temp / "frozen_protocol.json", source_protocol)
        inputs = input_records(phase_a)
        assignments, tn_by_cell, mrar_by_cell, comparison, status_rows = build_cell_id_audit()
        write_json(temp / "cell_id_comparison.json", comparison)
        status_schema = pa.schema(
            [
                ("cell_id", pa.string()),
                ("in_frozen_scalar_pair", pa.bool_()),
                ("in_tn352_candidate", pa.bool_()),
                ("in_mrar_raw_support", pa.bool_()),
                ("analysis_status", pa.string()),
                ("included_in_phase_b", pa.bool_()),
            ]
        )
        status_path = temp / "phase_b_cell_id_status.parquet"
        pq.write_table(pa.Table.from_pylist(status_rows, schema=status_schema), status_path, compression="zstd")
        missing_tn352 = comparison["cell_ids"]["frozen_missing_tn352"]
        missing_raw_support = comparison["cell_ids"]["frozen_missing_raw_support"]
        require(
            not missing_tn352 and not missing_raw_support,
            f"frozen cohort gate failed: missing_tn352={missing_tn352}; missing_raw_support={missing_raw_support}",
        )
        require(
            comparison["counts"]["raw_support_common"] == EXPECTED_RAW_SUPPORT_COMMON_CELLS,
            "current raw-support common-cell count differs",
        )
        require(
            comparison["counts"]["raw_support_only_not_in_frozen_scalar_pair"] == EXPECTED_RAW_SUPPORT_ONLY_CELLS,
            "raw-support-only cell count differs",
        )
        require(
            comparison["counts"]["tn352_without_mrar_raw_support"] == EXPECTED_TN352_WITHOUT_RAW_SUPPORT_CELLS,
            "TN352-without-raw-support cell count differs",
        )
        cohort_rows = build_common_cohort(assignments, tn_by_cell, mrar_by_cell)
        assert_common_cell_count(len(cohort_rows))
        cohort_schema = pa.schema(
            [
                ("cell_id", pa.string()),
                ("lon_bin", pa.int64()),
                ("lat_bin", pa.int64()),
                ("lon_center", pa.float64()),
                ("lat_center", pa.float64()),
                ("tn352_official_cruise_id", pa.string()),
                ("tn352_n_source_objects_all_soundings", pa.int64()),
                ("tn352_n_qc_eligible", pa.int64()),
                ("tn352_n_unique_parser_pings", pa.int64()),
                ("mrar_source_provider", pa.string()),
                ("mrar_branch", pa.string()),
                ("mrar_branch_role", pa.string()),
                ("mrar_n_points_pass_total", pa.int64()),
                ("mrar_n_tracks", pa.int64()),
                ("mrar_dominant_file_id", pa.string()),
                ("mrar_source_dataset", pa.string()),
                ("frozen_split", pa.string()),
                ("frozen_role", pa.string()),
                ("frozen_sorted_input_index", pa.int64()),
                ("frozen_permutation_position", pa.int64()),
            ]
        )
        cohort_path = temp / "common_cell_cohort.parquet"
        pq.write_table(pa.Table.from_pylist(cohort_rows, schema=cohort_schema), cohort_path, compression="zstd")
        protocol_hash = sha256_file(temp / "frozen_protocol.json")
        cohort_hash = sha256_file(cohort_path)
        comparison_hash = sha256_file(temp / "cell_id_comparison.json")
        status_hash = sha256_file(status_path)
        lock = {
            "schema_version": 2,
            "run_id": run_dir.name,
            "phase": "phase_b_freeze",
            "status": "frozen_before_depth_access",
            "output_role": "development_only_not_confirmation",
            "phase_a_verification_status": "pass",
            "phase_a_path": str(phase_a),
            "command": sys.argv,
            "cwd": str(Path.cwd()),
            "runtime_environment": {
                "python": sys.version,
                "platform": platform.platform(),
                "numpy": np.__version__,
                "pyarrow": pa.__version__,
                "pyyaml": yaml.__version__,
            },
            "random_seed": "not_applicable_deterministic_geometry",
            "frozen_protocol_sha256": protocol_hash,
            "common_cell_cohort": {
                "path": str((phase_b / "common_cell_cohort.parquet").resolve()),
                "rows": len(cohort_rows),
                "unique_cell_ids": len({row["cell_id"] for row in cohort_rows}),
                "sha256": cohort_hash,
                "schema": str(cohort_schema),
            },
            "cell_id_comparison": {
                "path": str((phase_b / "cell_id_comparison.json").resolve()),
                "sha256": comparison_hash,
                "status": comparison["status"],
                "counts": comparison["counts"],
            },
            "phase_b_cell_id_status": {
                "path": str((phase_b / "phase_b_cell_id_status.parquet").resolve()),
                "rows": len(status_rows),
                "sha256": status_hash,
                "schema": str(status_schema),
            },
            "inputs": inputs,
            "columns_read_before_depth_access": {
                "frozen_scalar_pair_assignments": FROZEN_ASSIGNMENT_COLUMNS,
                "stage_c_candidate_labels": NON_DEPTH_STAGE_C_COLUMNS,
                "mrar_cell_labels": NON_DEPTH_MRAR_COLUMNS,
                "stage_c_sounding_lineage": [],
                "mrar_checked_points": NON_DEPTH_MRAR_POINT_COLUMNS,
            },
            "depth_value_columns_read_before_lock": [],
            "depth_difference_columns_read_before_lock": [],
            "access_order_completed": [
                "verify_phase_a",
                "copy_and_hash_protocol",
                "hash_inputs_and_schemas",
                "read_frozen_assignment_cell_ids",
                "read_non_depth_tn352_and_mrar_raw_support_identity",
                "write_and_hash_cell_id_comparison",
                "assert_frozen_subset_of_current_raw_support",
                "write_and_hash_common_cell_cohort",
                "assert_expected_cell_count",
            ],
            "expected_common_cell_count": EXPECTED_COMMON_CELLS,
            "observed_common_cell_count": len(cohort_rows),
            "raw_support_only_status": "raw_support_only_not_in_frozen_scalar_pair",
            "count_gate_status": "pass",
        }
        write_json(temp / "input_lock.json", lock)
        receipt = {
            "schema_version": 1,
            "run_id": run_dir.name,
            "status": "pass",
            "process_boundary": "freeze_completed_without_depth_access",
            "frozen_protocol_sha256": protocol_hash,
            "input_lock_sha256": sha256_file(temp / "input_lock.json"),
            "common_cell_cohort_sha256": cohort_hash,
            "cell_id_comparison_sha256": comparison_hash,
            "phase_b_cell_id_status_sha256": status_hash,
            "common_cell_count": len(cohort_rows),
            "raw_support_common_cell_count": comparison["counts"]["raw_support_common"],
            "raw_support_only_cell_count": comparison["counts"]["raw_support_only_not_in_frozen_scalar_pair"],
            "tn352_without_mrar_raw_support_cell_ids": comparison["cell_ids"]["tn352_without_mrar_raw_support"],
            "depth_value_columns_read": [],
            "depth_difference_columns_read": [],
            "sealed_or_sidecar_body_reads": 0,
            "GGM_PINN_GEBCO_model_product_operations": 0,
        }
        write_json(temp / "freeze_receipt.json", receipt)
        os.rename(temp, phase_b)
        return phase_b
    except Exception as error:
        failure = {
            "schema_version": 1,
            "run_id": run_dir.name,
            "status": "fail",
            "error_type": type(error).__name__,
            "error": str(error),
            "cell_id_comparison": comparison,
            "depth_value_columns_read": [],
            "depth_difference_columns_read": [],
            "GGM_PINN_GEBCO_model_product_operations": 0,
        }
        write_json(temp / "freeze_failure_receipt.json", failure)
        failed_root.parent.mkdir(parents=True, exist_ok=True)
        os.rename(temp, failed_root)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--phase-a-dir", required=True, type=Path)
    args = parser.parse_args()
    print(freeze(args.run_dir, args.phase_a_dir))


if __name__ == "__main__":
    main()
