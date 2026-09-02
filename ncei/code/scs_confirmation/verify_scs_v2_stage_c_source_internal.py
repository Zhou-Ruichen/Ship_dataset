#!/usr/bin/env python3
"""Verify future Stage C source-internal tables without opening sealed sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import pandas as pd

from ncei.code.scs_confirmation.scs_v2_stage_c1_contract import cell_assignment, source_object_id


FIVE_LEVEL_STATUS = {
    "known",
    "officially_unknown",
    "not_recoverable",
    "inferred_from_filename",
    "verified_from_source_metadata",
}
PRIMARY_KEYS = {
    "source_object_processing": ["source_object_id"],
    "sounding_lineage": ["source_object_id", "parser_ping_index", "beam_index"],
    "cell_cruise_contributors": ["cell_id", "official_cruise_id", "source_object_id"],
    "cell_cruise_candidates": ["cell_id", "official_cruise_id"],
    "field_recovery_ledger": ["official_cruise_id", "source_object_id", "field_name"],
}
REQUIRED_TABLE_FILES = {name: f"{name}.parquet" for name in PRIMARY_KEYS}


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _require_columns(frame: pd.DataFrame, columns: list[str], table: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise AssertionError(f"{table} missing columns: {missing}")


def _require_unique(frame: pd.DataFrame, key: list[str], table: str) -> None:
    _require_columns(frame, key, table)
    if frame[key].isna().any(axis=None) or frame.duplicated(key).any():
        raise AssertionError(f"{table} primary key is null or duplicated: {key}")


def _verify_status_columns(frame: pd.DataFrame, table: str) -> int:
    checked = 0
    for column in frame.columns:
        if not column.endswith("_status"):
            continue
        values = set(frame[column].dropna().astype(str))
        if not values <= FIVE_LEVEL_STATUS:
            raise AssertionError(f"{table}.{column} has invalid statuses: {sorted(values - FIVE_LEVEL_STATUS)}")
        checked += 1
    return checked


def verify_tables(tables: dict[str, pd.DataFrame]) -> dict[str, Any]:
    if set(tables) != set(PRIMARY_KEYS):
        raise AssertionError(f"Stage C table set mismatch: {sorted(tables)}")
    for name, key in PRIMARY_KEYS.items():
        _require_unique(tables[name], key, name)

    objects = tables["source_object_processing"]
    object_columns = [
        "acquisition_run_id",
        "source_object_id",
        "source_object_relative_path",
        "source_object_sha256",
        "official_cruise_id",
    ]
    _require_columns(objects, object_columns, "source_object_processing")
    expected_ids = [
        source_object_id(run_id, relative_path)
        for run_id, relative_path in zip(objects["acquisition_run_id"], objects["source_object_relative_path"])
    ]
    if objects["source_object_id"].astype(str).tolist() != expected_ids:
        raise AssertionError("source_object_id does not close to acquisition_run_id plus relative path")
    if not objects["source_object_sha256"].astype(str).str.fullmatch(r"[0-9a-f]{64}").all():
        raise AssertionError("source_object_sha256 format mismatch")

    soundings = tables["sounding_lineage"]
    sounding_columns = [
        "source_object_id",
        "source_object_relative_path",
        "source_object_sha256",
        "official_cruise_id",
        "parser_ping_index",
        "native_ping_counter",
        "beam_index",
        "lon_deg",
        "lat_deg",
        "parser_depth_value",
        "depth_m_positive_down",
        "elev_m",
        "native_quality_state",
        "qc_eligible_for_cell",
        "lon_bin",
        "lat_bin",
        "cell_id",
        "held_out",
        "use_for_training",
        "use_for_tuning",
        "use_for_threshold_selection",
        "role_v2_h",
        "role_v2_w",
        "confirmation_role_eligible",
    ]
    _require_columns(soundings, sounding_columns, "sounding_lineage")
    object_projection = objects[
        ["source_object_id", "source_object_relative_path", "source_object_sha256", "official_cruise_id"]
    ].rename(columns={column: f"object_{column}" for column in ("source_object_relative_path", "source_object_sha256", "official_cruise_id")})
    joined = soundings.merge(object_projection, on="source_object_id", how="left", validate="many_to_one", indicator=True)
    if not (joined["_merge"] == "both").all():
        raise AssertionError("sounding references unknown source_object_id")
    for column in ("source_object_relative_path", "source_object_sha256", "official_cruise_id"):
        if not (joined[column].astype(str) == joined[f"object_{column}"].astype(str)).all():
            raise AssertionError(f"sounding/object mismatch for {column}")

    qualities = set(soundings["native_quality_state"].astype(str))
    if not qualities <= {"good", "flagged", "null"}:
        raise AssertionError(f"invalid native quality states: {sorted(qualities)}")
    nongood = soundings["native_quality_state"] != "good"
    if soundings.loc[nongood, "depth_m_positive_down"].notna().any():
        raise AssertionError("flagged/null sounding populated eligible depth")

    eligible = soundings["qc_eligible_for_cell"].fillna(False).astype(bool)
    for index, row in soundings.loc[eligible].iterrows():
        depth = float(row["depth_m_positive_down"])
        if not math.isfinite(depth) or depth <= 0.0 or depth > 12_000.0:
            raise AssertionError(f"eligible depth invalid at row {index}")
        if float(row["elev_m"]) != -depth:
            raise AssertionError(f"elevation identity failed at row {index}")
        lon_bin, lat_bin, cell_id = cell_assignment(float(row["lon_deg"]), float(row["lat_deg"]))
        if (int(row["lon_bin"]), int(row["lat_bin"]), str(row["cell_id"])) != (lon_bin, lat_bin, cell_id):
            raise AssertionError(f"cell assignment mismatch at row {index}")

    if not soundings["held_out"].fillna(False).astype(bool).all():
        raise AssertionError("all soundings must remain held out")
    for column in ("use_for_training", "use_for_tuning", "use_for_threshold_selection", "confirmation_role_eligible"):
        if soundings[column].fillna(False).astype(bool).any():
            raise AssertionError(f"forbidden role flag is true: {column}")
    if set(soundings["role_v2_h"].astype(str)) != {"held_out_candidate_mrar_out"}:
        raise AssertionError("v2-H role mismatch")
    if set(soundings["role_v2_w"].astype(str)) != {"blocked_source_independence_unknown"}:
        raise AssertionError("v2-W role mismatch")

    contributors = tables["cell_cruise_contributors"]
    _require_columns(
        contributors,
        ["source_object_id", "source_object_relative_path", "source_object_sha256", "official_cruise_id"],
        "cell_cruise_contributors",
    )
    contributor_join = contributors.merge(
        object_projection, on="source_object_id", how="left", validate="many_to_one", indicator=True
    )
    if not (contributor_join["_merge"] == "both").all():
        raise AssertionError("contributor references unknown source_object_id")
    for column in ("source_object_relative_path", "source_object_sha256", "official_cruise_id"):
        if not (contributor_join[column].astype(str) == contributor_join[f"object_{column}"].astype(str)).all():
            raise AssertionError(f"contributor/object mismatch for {column}")

    ledger = tables["field_recovery_ledger"]
    _require_columns(ledger, ["source_object_id", "source_object_relative_path", "source_object_sha256"], "field_recovery_ledger")
    ledger_join = ledger.merge(
        objects[["source_object_id", "source_object_relative_path", "source_object_sha256"]].rename(
            columns={column: f"object_{column}" for column in ("source_object_relative_path", "source_object_sha256")}
        ),
        on="source_object_id",
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    if not (ledger_join["_merge"] == "both").all():
        raise AssertionError("field ledger references unknown source_object_id")
    for column in ("source_object_relative_path", "source_object_sha256"):
        if not (ledger_join[column].astype(str) == ledger_join[f"object_{column}"].astype(str)).all():
            raise AssertionError(f"field ledger/object mismatch for {column}")

    status_columns_checked = sum(_verify_status_columns(frame, name) for name, frame in tables.items())
    return {
        "status": "pass",
        "table_count": len(tables),
        "source_object_count": len(objects),
        "sounding_count": len(soundings),
        "status_columns_checked": status_columns_checked,
        "source_object_id_formula_closed": True,
        "source_object_sha256_used_as_identity": False,
    }


def atomic_json(value: Any, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def verify_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    verification_path = run_dir / "verification.json"
    if verification_path.exists():
        raise FileExistsError(f"immutable verification already exists: {verification_path}")
    tables = {name: pd.read_parquet(run_dir / filename) for name, filename in REQUIRED_TABLE_FILES.items()}
    result = verify_tables(tables)
    result.update(
        {
            "schema_version": 2,
            "stage": "C_source_internal_candidate_processing",
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
