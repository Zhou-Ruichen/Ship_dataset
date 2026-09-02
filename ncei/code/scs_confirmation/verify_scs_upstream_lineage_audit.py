#!/usr/bin/env python3
"""Independently verify persisted SCS lineage-audit artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


EXPECTED_CELL_COUNT = 174_965
EXPECTED_SOURCE_COUNTS = {"mrar": 165_966, "jamstec": 8_999}
EXPECTED_EXTERNAL_GROUPS = 12
FIELD_STATUSES = {
    "known",
    "officially_unknown",
    "not_recoverable",
    "inferred_from_filename",
    "verified_from_source_metadata",
}
IDENTITY_STATES = {
    "official_exact", "official_leg_ambiguous", "filename_only", "unresolved",
}
REPLAY_ATOL_M = 1e-9


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(value: Any, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def check_status_pairs(frame: pd.DataFrame, key_columns: set[str], name: str) -> dict[str, Any]:
    values = [column for column in frame.columns if not column.endswith("_status") and column not in key_columns]
    missing = sorted(column for column in values if f"{column}_status" not in frame.columns)
    invalid: dict[str, list[str]] = {}
    for column in frame.columns:
        if column.endswith("_status"):
            unexpected = sorted(set(frame[column].dropna().astype(str)) - FIELD_STATUSES)
            if unexpected:
                invalid[column] = unexpected
    if missing or invalid:
        raise AssertionError(f"{name} five-level status failure: missing={missing}, invalid={invalid}")
    return {"value_columns": len(values), "status_columns": sum(column.endswith("_status") for column in frame.columns)}


def verify(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "audit_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("downstream_model_error_read") is not False:
        raise AssertionError("manifest does not assert downstream_model_error_read=false")
    if set(manifest["field_statuses"]) != FIELD_STATUSES:
        raise AssertionError("manifest five-level vocabulary drift")
    if set(manifest["identity_states"]) != IDENTITY_STATES:
        raise AssertionError("manifest identity vocabulary drift")

    input_hash_checks = {}
    for role, record in manifest["inputs"].items():
        actual = sha256_file(Path(record["path"]))
        input_hash_checks[role] = actual == record["sha256"]
        if not input_hash_checks[role]:
            raise AssertionError(f"frozen input hash drift after audit: {role}")

    output_hash_checks = {}
    for role, record in manifest["outputs"].items():
        path = Path(record["path"])
        if path.parent != run_dir:
            raise AssertionError(f"output escaped immutable run directory: {role}")
        actual = sha256_file(path)
        output_hash_checks[role] = actual == record["sha256"]
        if not output_hash_checks[role]:
            raise AssertionError(f"output hash mismatch: {role}")

    lineage = pd.read_parquet(run_dir / "cell_lineage.parquet")
    replay = pd.read_parquet(run_dir / "raw_to_cell_replay.parquet")
    identity = pd.read_csv(run_dir / "source_identity_ledger.csv")
    vertical = pd.read_csv(run_dir / "vertical_datum_ledger.csv")
    recorded_diff = json.loads((run_dir / "diff_summary.json").read_text(encoding="utf-8"))

    if len(lineage) != EXPECTED_CELL_COUNT or lineage["canonical_cell_id"].nunique() != EXPECTED_CELL_COUNT:
        raise AssertionError("cell_lineage row/key closure failed")
    if lineage["source_provider"].value_counts().to_dict() != EXPECTED_SOURCE_COUNTS:
        raise AssertionError("cell_lineage source closure failed")
    if len(replay) != EXPECTED_CELL_COUNT or replay["canonical_cell_id"].nunique() != EXPECTED_CELL_COUNT:
        raise AssertionError("raw_to_cell_replay row/key closure failed")
    if set(lineage["canonical_cell_id"]) != set(replay["canonical_cell_id"]):
        raise AssertionError("lineage/replay cell key mismatch")
    if len(identity) != EXPECTED_EXTERNAL_GROUPS or identity["cruise_id_candidate"].nunique() != EXPECTED_EXTERNAL_GROUPS:
        raise AssertionError("identity ledger group closure failed")
    invalid_states = set(identity["identity_state"]) - IDENTITY_STATES
    if invalid_states:
        raise AssertionError(f"invalid identity states: {sorted(invalid_states)}")
    if len(vertical) != 20:
        raise AssertionError(f"vertical ledger expected 20 represented source/cruise rows, found {len(vertical)}")

    status_checks = {
        "cell_lineage": check_status_pairs(lineage, {"canonical_cell_id"}, "cell_lineage"),
        "source_identity_ledger": check_status_pairs(identity, set(), "source_identity_ledger"),
        "vertical_datum_ledger": check_status_pairs(vertical, set(), "vertical_datum_ledger"),
        "raw_to_cell_replay": check_status_pairs(replay, {"canonical_cell_id"}, "raw_to_cell_replay"),
    }

    abs_diff = np.abs(replay["replayed_depth_m"].to_numpy() - replay["frozen_depth_m"].to_numpy())
    persisted_abs = replay["absolute_diff_m"].to_numpy()
    if not np.allclose(abs_diff, persisted_abs, rtol=0, atol=1e-12):
        raise AssertionError("persisted replay absolute differences do not recompute")
    recomputed = {
        "cell_count": len(replay),
        "exact_count_at_1e-9_m": int((abs_diff <= REPLAY_ATOL_M).sum()),
        "different_count_at_1e-9_m": int((abs_diff > REPLAY_ATOL_M).sum()),
        "max_abs_diff_m": float(abs_diff.max()),
        "median_abs_diff_m": float(np.median(abs_diff)),
    }
    for key, value in recomputed.items():
        if recorded_diff[key] != value:
            raise AssertionError(f"diff_summary mismatch for {key}: {recorded_diff[key]} != {value}")

    if not lineage["lineage_class"].eq("exact_raw_row_lineage").all():
        raise AssertionError("some cell lacks exact raw row lineage")
    if not replay["replay_result"].isin(["exact", "different"]).all():
        raise AssertionError("invalid operational replay status")

    return {
        "status": "pass",
        "run_dir": str(run_dir),
        "manifest_sha256": sha256_file(manifest_path),
        "input_hash_checks": input_hash_checks,
        "output_hash_checks": output_hash_checks,
        "cell_count": len(lineage),
        "source_counts": lineage["source_provider"].value_counts().to_dict(),
        "identity_state_counts": identity["identity_state"].value_counts().to_dict(),
        "vertical_ledger_rows": len(vertical),
        "recomputed_diff": recomputed,
        "status_pair_checks": status_checks,
    }


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
