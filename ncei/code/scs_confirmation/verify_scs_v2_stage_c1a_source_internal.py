#!/usr/bin/env python3
"""Verify the Stage C.1a object-level atomic time contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from ncei.code.scs_confirmation.scs_v2_stage_c1a_contract import PASS_STATUS, TIME_FAILURE_STATUS
from ncei.code.scs_confirmation.verify_scs_v2_stage_c_source_internal import (
    REQUIRED_TABLE_FILES,
    atomic_json,
    sha256_file,
    verify_tables as verify_c1_tables,
)


def _require_columns(frame: pd.DataFrame, columns: list[str], table: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise AssertionError(f"{table} missing C1a columns: {missing}")


def verify_tables(tables: dict[str, pd.DataFrame]) -> dict[str, Any]:
    objects = tables["source_object_processing"]
    base_tables = dict(tables)
    base_tables["source_object_processing"] = objects.drop(columns=["parse_status"], errors="ignore")
    result = verify_c1_tables(base_tables)
    soundings = tables["sounding_lineage"]
    contributors = tables["cell_cruise_contributors"]
    ledger = tables["field_recovery_ledger"]

    _require_columns(objects, ["parse_status", "parsed_row_count", "error_code"], "source_object_processing")
    _require_columns(soundings, ["time_utc", "time_utc_status"], "sounding_lineage")
    _require_columns(ledger, ["field_available", "field_status", "evidence_kind"], "field_recovery_ledger")
    if soundings["time_utc"].isna().any():
        raise AssertionError("C1a forbids nullable time in emitted sounding rows")
    allowed_parse_statuses = {PASS_STATUS, TIME_FAILURE_STATUS, "failed_parser_contract", "not_applicable_sidecar"}
    parse_statuses = set(objects["parse_status"].astype(str))
    if not parse_statuses <= allowed_parse_statuses:
        raise AssertionError(f"invalid source object parse_status: {sorted(parse_statuses - allowed_parse_statuses)}")

    failed = objects[objects["parse_status"] == TIME_FAILURE_STATUS]
    failed_ids = set(failed["source_object_id"].astype(str))
    if not (failed["parsed_row_count"] == 0).all():
        raise AssertionError("invalid-time object has nonzero parsed_row_count")
    if failed["error_code"].isna().any():
        raise AssertionError("invalid-time object lacks error_code")
    if set(soundings["source_object_id"].astype(str)) & failed_ids:
        raise AssertionError("invalid-time object emitted sounding rows")
    if set(contributors["source_object_id"].astype(str)) & failed_ids:
        raise AssertionError("invalid-time object emitted contributor rows")

    for object_id in failed_ids:
        rows = ledger[
            (ledger["source_object_id"].astype(str) == object_id)
            & (ledger["field_name"].astype(str) == "time_utc")
        ]
        if len(rows) != 1:
            raise AssertionError("invalid-time object must have one time_utc ledger row")
        row = rows.iloc[0]
        if bool(row["field_available"]):
            raise AssertionError("invalid-time ledger marks time_utc available")
        if str(row["field_status"]) != "known":
            raise AssertionError("invalid-time ledger status must be known")
        if str(row["evidence_kind"]) != "parser_preflight_failure":
            raise AssertionError("invalid-time ledger evidence kind mismatch")

    object_status = objects.set_index("source_object_id")["parse_status"].astype(str)
    for object_id, frame in soundings.groupby("source_object_id", sort=False):
        if object_status.loc[object_id] != PASS_STATUS:
            raise AssertionError("emitted sounding belongs to a non-pass object")
        ping_ordinals: dict[tuple[object, int], int] = {}
        for row in frame.itertuples(index=False):
            ping_key = (row.time_utc, int(row.native_ping_counter))
            expected = ping_ordinals.setdefault(ping_key, len(ping_ordinals))
            if int(row.parser_ping_index) != expected:
                raise AssertionError("parser_ping_index does not follow valid time and native ping order")

    pass_ids = set(objects.loc[objects["parse_status"] == PASS_STATUS, "source_object_id"].astype(str))
    parsed_counts = soundings.groupby("source_object_id").size().to_dict()
    for row in objects[objects["source_object_id"].astype(str).isin(pass_ids)].itertuples(index=False):
        if int(row.parsed_row_count) != int(parsed_counts.get(row.source_object_id, 0)):
            raise AssertionError("pass object parsed_row_count does not equal emitted sounding rows")

    result.update(
        {
            "stage_c1a_time_contract": "pass",
            "time_utc_nullable_in_emitted_soundings": False,
            "invalid_time_policy": "abort_source_object_atomically",
            "invalid_time_object_count": len(failed_ids),
            "invalid_time_sounding_count": 0,
            "invalid_time_contributor_count": 0,
            "parser_ping_index_requires_valid_time": True,
        }
    )
    return result


def verify_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    verification_path = run_dir / "verification.json"
    if verification_path.exists():
        raise FileExistsError(f"immutable verification already exists: {verification_path}")
    tables = {name: pd.read_parquet(run_dir / filename) for name, filename in REQUIRED_TABLE_FILES.items()}
    result = verify_tables(tables)
    result.update(
        {
            "schema_version": 3,
            "stage": "C1a_source_internal_candidate_processing",
            "run_dir": str(run_dir),
            "content_or_source_parser_imported": False,
            "table_sha256": {
                name: sha256_file(run_dir / filename) for name, filename in REQUIRED_TABLE_FILES.items()
            },
        }
    )
    atomic_json(result, verification_path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    result = verify_run(parser.parse_args().run_dir)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
