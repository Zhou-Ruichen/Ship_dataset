#!/usr/bin/env python3
"""Freeze Phase B inputs and common-cell identity before any depth read."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

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
EXPECTED_COMMON_CELLS = 2_244
TN352 = "TN352"
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


def assert_common_cell_count(observed: int, expected: int = EXPECTED_COMMON_CELLS) -> None:
    require(observed == expected, f"common-cell gate failed: {observed} != {expected}")


def validate_cell_row(row: dict[str, Any], source: str) -> None:
    lon_bin, lat_bin, cell_id, lon_center, lat_center = one_min_cell(
        float(row["lon_center"]), float(row["lat_center"])
    )
    require(str(row["cell_id"]) == cell_id, f"{source} cell ID formula differs: {row['cell_id']}")
    require(int(row["lon_bin"]) == lon_bin and int(row["lat_bin"]) == lat_bin, f"{source} bin formula differs: {cell_id}")
    require(abs(float(row["lon_center"]) - lon_center) <= 1.0e-12, f"{source} longitude center differs: {cell_id}")
    require(abs(float(row["lat_center"]) - lat_center) <= 1.0e-12, f"{source} latitude center differs: {cell_id}")


def build_common_cohort() -> list[dict[str, Any]]:
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
    common_ids = sorted(
        set(tn_by_cell) & set(mrar_by_cell),
        key=lambda value: (int(value.split("_")[1]), int(value.split("_")[2])),
    )
    assert_common_cell_count(len(common_ids))
    output = []
    for cell_id in common_ids:
        tn_row = tn_by_cell[cell_id]
        mrar_row = mrar_by_cell[cell_id]
        require(int(tn_row["lon_bin"]) == int(mrar_row["lon_bin"]), f"source longitude bin differs: {cell_id}")
        require(int(tn_row["lat_bin"]) == int(mrar_row["lat_bin"]), f"source latitude bin differs: {cell_id}")
        require(float(tn_row["lon_center"]) == float(mrar_row["lon_center"]), f"source longitude center differs: {cell_id}")
        require(float(tn_row["lat_center"]) == float(mrar_row["lat_center"]), f"source latitude center differs: {cell_id}")
        output.append(
            {
                "cell_id": cell_id,
                "lon_bin": int(tn_row["lon_bin"]),
                "lat_bin": int(tn_row["lat_bin"]),
                "lon_center": float(tn_row["lon_center"]),
                "lat_center": float(tn_row["lat_center"]),
                "tn352_official_cruise_id": TN352,
                "tn352_n_source_objects": int(tn_row["n_source_objects"]),
                "tn352_n_qc_eligible": int(tn_row["n_qc_eligible"]),
                "tn352_n_unique_parser_pings": int(tn_row["n_unique_parser_pings"]),
                "mrar_source_provider": str(mrar_row["source_provider"]),
                "mrar_branch": str(mrar_row["branch"]),
                "mrar_branch_role": str(mrar_row["branch_role"]),
                "mrar_n_points_pass_total": int(mrar_row["n_points_pass_total"]),
                "mrar_n_tracks": int(mrar_row["n_tracks"]),
                "mrar_dominant_file_id": str(mrar_row["dominant_file_id"]),
                "mrar_source_dataset": str(mrar_row["source_dataset"]),
            }
        )
    return output


def input_records(run_dir: Path) -> dict[str, dict[str, Any]]:
    phase_a = run_dir / "phase_a"
    return {
        "phase_a_manifest": path_record(phase_a / "audit_manifest.json"),
        "phase_a_verification": path_record(phase_a / "verification.json"),
        "stage_c_sounding_lineage": path_record(STAGE_C_ROOT / "sounding_lineage.parquet", with_schema=True),
        "stage_c_candidate_labels": path_record(STAGE_C_ROOT / "cell_cruise_candidates.parquet", with_schema=True),
        "mrar_checked_points": path_record(MRAR_POINTS_PATH, with_schema=True),
        "mrar_cell_labels": tree_record(MRAR_CELLS_PATH, with_schema=True),
        "source_protocol": path_record(PROTOCOL_PATH),
        "freeze_code": path_record(Path(__file__)),
        "support_code": path_record(REPO_ROOT / "ncei/code/scs_tn352_support.py"),
        "support_producer": path_record(REPO_ROOT / "ncei/code/audit_scs_tn352_mrar_support.py"),
        "support_verifier": path_record(REPO_ROOT / "ncei/code/verify_scs_tn352_mrar_support_audit.py"),
    }


def freeze(run_dir: Path) -> Path:
    run_dir = run_dir.resolve()
    require(run_dir.parent == (REPO_ROOT / "ncei/derived/scs_tn352_processing_and_support_audit").resolve(), "run directory outside audit root")
    phase_a = run_dir / "phase_a"
    phase_b = run_dir / "phase_b"
    failed_root = run_dir.parent / f"{run_dir.name}.failed" / "phase_b"
    require(phase_a.is_dir(), "Phase A directory missing")
    require(not phase_b.exists(), "Phase B already exists")
    require(not failed_root.exists(), "Phase B failed directory already exists")
    phase_a_verification = read_json(phase_a / "verification.json")
    require(phase_a_verification["status"] == "pass", "Phase A verification is not pass")
    require(phase_a_verification["depth_difference_with_mrar_read_count"] == 0, "Phase A read MRAR depth differences")
    require(sha256_file(phase_a / "audit_manifest.json") == phase_a_verification["audit_manifest_sha256"], "Phase A manifest hash differs")
    task = read_json(TASK_ROOT / "task.json")
    require(task["status"] == "in_progress", "Trellis task is not in progress")
    require(sha256_file(PROTOCOL_PATH) == EXPECTED_PROTOCOL_SHA256, "source protocol hash drift")
    temp = Path(tempfile.mkdtemp(prefix=".phase_b.freeze-", dir=run_dir))
    try:
        source_protocol = yaml.safe_load(PROTOCOL_PATH.read_text(encoding="utf-8"))
        require(source_protocol["status"] == "proposed_pending_user_review", "source protocol status differs")
        source_protocol["status"] = "approved_frozen"
        source_protocol["activation_evidence"] = {
            "trellis_task_status": task["status"],
            "planning_commit": "88d88ea85e07ed6b8e564dc70851c9286fc976bc",
            "source_protocol_sha256": EXPECTED_PROTOCOL_SHA256,
            "phase_a_verification_sha256": sha256_file(phase_a / "verification.json"),
            "user_authorization": "task start authorized before Phase A and Phase B execution",
        }
        write_json(temp / "frozen_protocol.json", source_protocol)
        inputs = input_records(run_dir)
        cohort_rows = build_common_cohort()
        cohort_schema = pa.schema(
            [
                ("cell_id", pa.string()),
                ("lon_bin", pa.int64()),
                ("lat_bin", pa.int64()),
                ("lon_center", pa.float64()),
                ("lat_center", pa.float64()),
                ("tn352_official_cruise_id", pa.string()),
                ("tn352_n_source_objects", pa.int64()),
                ("tn352_n_qc_eligible", pa.int64()),
                ("tn352_n_unique_parser_pings", pa.int64()),
                ("mrar_source_provider", pa.string()),
                ("mrar_branch", pa.string()),
                ("mrar_branch_role", pa.string()),
                ("mrar_n_points_pass_total", pa.int64()),
                ("mrar_n_tracks", pa.int64()),
                ("mrar_dominant_file_id", pa.string()),
                ("mrar_source_dataset", pa.string()),
            ]
        )
        cohort_path = temp / "common_cell_cohort.parquet"
        pq.write_table(pa.Table.from_pylist(cohort_rows, schema=cohort_schema), cohort_path, compression="zstd")
        protocol_hash = sha256_file(temp / "frozen_protocol.json")
        cohort_hash = sha256_file(cohort_path)
        lock = {
            "schema_version": 1,
            "run_id": run_dir.name,
            "phase": "phase_b_freeze",
            "status": "frozen_before_depth_access",
            "output_role": "development_only_not_confirmation",
            "phase_a_verification_status": "pass",
            "frozen_protocol_sha256": protocol_hash,
            "common_cell_cohort": {
                "path": str((phase_b / "common_cell_cohort.parquet").resolve()),
                "rows": len(cohort_rows),
                "unique_cell_ids": len({row["cell_id"] for row in cohort_rows}),
                "sha256": cohort_hash,
                "schema": str(cohort_schema),
            },
            "inputs": inputs,
            "columns_read_before_depth_access": {
                "stage_c_candidate_labels": NON_DEPTH_STAGE_C_COLUMNS,
                "mrar_cell_labels": NON_DEPTH_MRAR_COLUMNS,
                "stage_c_sounding_lineage": [],
                "mrar_checked_points": [],
            },
            "depth_value_columns_read_before_lock": [],
            "depth_difference_columns_read_before_lock": [],
            "access_order_completed": [
                "verify_phase_a",
                "copy_and_hash_protocol",
                "hash_inputs_and_schemas",
                "read_non_depth_cell_identity_and_geometry",
                "write_and_hash_common_cell_cohort",
                "assert_expected_cell_count",
            ],
            "expected_common_cell_count": EXPECTED_COMMON_CELLS,
            "observed_common_cell_count": len(cohort_rows),
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
            "common_cell_count": len(cohort_rows),
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
            "depth_value_columns_read": [],
            "depth_difference_columns_read": [],
        }
        write_json(temp / "freeze_failure_receipt.json", failure)
        failed_root.parent.mkdir(parents=True, exist_ok=True)
        os.rename(temp, failed_root)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    print(freeze(args.run_dir))


if __name__ == "__main__":
    main()
