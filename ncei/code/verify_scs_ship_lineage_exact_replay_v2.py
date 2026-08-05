#!/usr/bin/env python3
"""Independently verify an immutable SCS lineage/exact-replay v2 run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
FIELD_STATUSES = (
    "known",
    "officially_unknown",
    "not_recoverable",
    "inferred_from_filename",
    "verified_from_source_metadata",
)
REQUIRED_BEFORE_VERIFICATION = {
    "source_artifact_inventory.tsv",
    "mrar_identity_ledger.tsv",
    "jamstec_file_capabilities.tsv",
    "raw_point_contributions.parquet",
    "file_cell_contributors.parquet",
    "cell_official_cruise_contributors.parquet",
    "exact_cell_replay.parquet",
    "legacy_52_replay_differences.parquet",
    "multi_file_cell_summary.parquet",
    "multi_file_contributor_details.parquet",
    "replay_invariance.tsv",
    "factual_status_counts.tsv",
    "audit_report.md",
    "audit_manifest.json",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_status_pairs(frame: pd.DataFrame, key_columns: set[str], name: str) -> None:
    values = [
        column for column in frame.columns
        if column not in key_columns and not column.endswith("_status")
    ]
    missing = [column for column in values if f"{column}_status" not in frame.columns]
    require(not missing, f"{name} factual fields missing paired statuses: {missing}")
    for column in frame.columns:
        if column.endswith("_status"):
            invalid = set(frame[column].dropna().astype(str)) - set(FIELD_STATUSES)
            require(not invalid, f"{name} invalid statuses in {column}: {sorted(invalid)}")


def grouped_nmad(
    frame: pd.DataFrame,
    group_columns: str | list[str],
    value_column: str,
) -> pd.Series:
    columns = [group_columns] if isinstance(group_columns, str) else group_columns
    medians = frame.groupby(columns, sort=False, observed=True)[value_column].transform("median")
    work = frame[columns].copy()
    work["_deviation"] = (frame[value_column] - medians).abs()
    grouped = work.groupby(columns, sort=False, observed=True)["_deviation"]
    result = grouped.median() * 1.4826
    counts = grouped.count()
    result[counts < 2] = np.nan
    return result


def compress_ranges(values: np.ndarray) -> list[list[int]]:
    ordered = np.unique(values.astype(np.int64))
    if ordered.size == 0:
        return []
    starts = np.r_[True, np.diff(ordered) != 1]
    ends = np.r_[np.diff(ordered) != 1, True]
    return [[int(start), int(end)] for start, end in zip(ordered[starts], ordered[ends])]


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def canonical_frame_digest(
    frame: pd.DataFrame,
    sort_columns: list[str],
    value_columns: list[str],
) -> str:
    canonical = frame[value_columns].sort_values(sort_columns, kind="stable").reset_index(drop=True)
    row_hashes = pd.util.hash_pandas_object(canonical, index=False, categorize=True).to_numpy(dtype=np.uint64)
    digest = hashlib.sha256()
    digest.update("\0".join(value_columns).encode("utf-8"))
    digest.update(row_hashes.astype("<u8", copy=False).tobytes())
    return digest.hexdigest()


def compare_columns(
    observed: pd.DataFrame,
    expected: pd.DataFrame,
    keys: list[str],
    columns: list[str],
    name: str,
) -> None:
    left = observed[keys + columns].sort_values(keys).reset_index(drop=True)
    right = expected[keys + columns].sort_values(keys).reset_index(drop=True)
    require(len(left) == len(right), f"{name} row-count mismatch")
    for key in keys:
        require(left[key].equals(right[key]), f"{name} key mismatch: {key}")
    for column in columns:
        if pd.api.types.is_numeric_dtype(left[column]) and pd.api.types.is_numeric_dtype(right[column]):
            a = left[column].to_numpy(dtype=np.float64)
            b = right[column].to_numpy(dtype=np.float64)
            equal = (a == b) | (np.isnan(a) & np.isnan(b))
            require(bool(equal.all()), f"{name} numeric mismatch: {column}")
        else:
            equal = left[column].fillna("<NULL>").astype(str).eq(right[column].fillna("<NULL>").astype(str))
            require(bool(equal.all()), f"{name} value mismatch: {column}")


def build_status_counts(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for artifact, frame in sorted(frames.items()):
        for status_column in sorted(column for column in frame.columns if column.endswith("_status")):
            field = status_column[:-7]
            counts = frame[status_column].value_counts(dropna=False).to_dict()
            for status in FIELD_STATUSES:
                rows.append({
                    "artifact": artifact,
                    "field": field,
                    "factual_status": status,
                    "count": int(counts.get(status, 0)),
                })
    return pd.DataFrame(rows)


def verify_manifest(run_dir: Path, manifest: dict[str, Any]) -> list[str]:
    checks = []
    require(manifest["run_id"] == run_dir.name, "manifest run ID mismatch")
    config_path = resolve(manifest["config_path"])
    require(sha256_file(config_path) == manifest["config_sha256"], "config SHA mismatch")
    checks.append("config_sha256")
    for name in ("producer", "verifier"):
        record = manifest["software"][name]
        require(sha256_file(resolve(record["path"])) == record["sha256"], f"software SHA mismatch: {name}")
    checks.append("software_sha256")
    for name, record in manifest["inputs"].items():
        path = resolve(record["path"])
        require(path.is_file(), f"manifest input missing: {name}")
        require(sha256_file(path) == record["sha256"], f"manifest input SHA mismatch: {name}")
        require(path.stat().st_size == int(record["bytes"]), f"manifest input size mismatch: {name}")
    checks.append("input_sha256_and_size")
    for name, record in manifest["raw_sources"].items():
        path = resolve(record["path"])
        require(path.is_file(), f"raw source missing: {name}")
        require(sha256_file(path) == record["sha256"], f"raw source SHA mismatch: {name}")
        require(path.stat().st_size == int(record["bytes"]), f"raw source size mismatch: {name}")
    checks.append("raw_source_sha256_and_size")
    names = {record["path"] for record in manifest["outputs"]}
    require(names == REQUIRED_BEFORE_VERIFICATION - {"audit_manifest.json"}, "manifest output inventory mismatch")
    for record in manifest["outputs"]:
        path = run_dir / record["path"]
        require(path.is_file(), f"output missing: {path.name}")
        require(sha256_file(path) == record["sha256"], f"output SHA mismatch: {path.name}")
        require(path.stat().st_size == int(record["bytes"]), f"output size mismatch: {path.name}")
        if path.suffix == ".parquet":
            require(pq.ParquetFile(path).metadata.num_rows == int(record["rows"]), f"output row mismatch: {path.name}")
    checks.append("output_sha256_size_rows")
    require(manifest["downstream_model_error_read"] is False, "manifest claims downstream model-error read")
    require(manifest["gebco_or_product_consensus_value_read"] is False, "manifest claims product value read")
    require(manifest["correction_or_data_role_decision_made"] is False, "manifest claims correction/role decision")
    checks.append("scientific_boundary_flags")
    return checks


def recompute_file_cells(raw: pd.DataFrame) -> pd.DataFrame:
    keys = ["canonical_cell_id", "file_id"]
    grouped = raw.groupby(keys, sort=True, observed=True)
    frame = grouped.agg(
        raw_point_count=("depth_m_positive_down", "size"),
        exact_median_m=("depth_m_positive_down", "median"),
        min_depth_m=("depth_m_positive_down", "min"),
        max_depth_m=("depth_m_positive_down", "max"),
    ).reset_index()
    frame["within_file_nmad_m"] = grouped_nmad(raw, keys, "depth_m_positive_down").reindex(
        pd.MultiIndex.from_frame(frame[keys])
    ).to_numpy()
    frame["depth_range_m"] = frame["max_depth_m"] - frame["min_depth_m"]
    ranges = grouped["raw_row_id"].agg(lambda values: stable_json([{
        "raw_file": str(raw.loc[values.index[0], "raw_file"]),
        "ranges_0_based_inclusive": compress_ranges(values.to_numpy()),
    }]))
    frame["raw_row_ranges_json"] = ranges.reindex(pd.MultiIndex.from_frame(frame[keys])).to_numpy()
    return frame


def recompute_cruise_cells(raw: pd.DataFrame) -> pd.DataFrame:
    keys = ["canonical_cell_id", "contributor_group_key"]
    grouped = raw.groupby(keys, sort=True, observed=True)
    frame = grouped.agg(
        raw_point_count=("depth_m_positive_down", "size"),
        raw_file_count=("file_id", "nunique"),
        exact_median_m=("depth_m_positive_down", "median"),
        min_depth_m=("depth_m_positive_down", "min"),
        max_depth_m=("depth_m_positive_down", "max"),
    ).reset_index()
    frame["within_cruise_nmad_m"] = grouped_nmad(raw, keys, "depth_m_positive_down").reindex(
        pd.MultiIndex.from_frame(frame[keys])
    ).to_numpy()
    frame["depth_range_m"] = frame["max_depth_m"] - frame["min_depth_m"]
    return frame


def recompute_cells(raw: pd.DataFrame, file_cells: pd.DataFrame, cruise_cells: pd.DataFrame) -> pd.DataFrame:
    grouped = raw.groupby("canonical_cell_id", sort=True, observed=True)
    frame = grouped.agg(
        raw_point_count=("depth_m_positive_down", "size"),
        exact_pooled_point_median_m=("depth_m_positive_down", "median"),
        min_depth_m=("depth_m_positive_down", "min"),
        max_depth_m=("depth_m_positive_down", "max"),
    ).reset_index()
    frame["exact_pooled_point_nmad_m"] = grouped_nmad(raw, "canonical_cell_id", "depth_m_positive_down").reindex(
        frame["canonical_cell_id"]
    ).to_numpy()
    frame["raw_depth_range_m"] = frame["max_depth_m"] - frame["min_depth_m"]
    files = file_cells.groupby("canonical_cell_id", sort=True).agg(
        raw_file_count=("file_id", "size"),
        exact_file_balanced_median_m=("exact_median_m", "median"),
    ).reset_index()
    frame = frame.merge(files, on="canonical_cell_id", validate="one_to_one")
    official = cruise_cells[cruise_cells["official_cruise_id"].notna()]
    cruises = official.groupby("canonical_cell_id", sort=True).agg(
        official_cruise_count=("official_cruise_id", "nunique"),
        exact_cruise_balanced_median_m=("exact_median_m", "median"),
    ).reset_index()
    frame = frame.merge(cruises, on="canonical_cell_id", how="left", validate="one_to_one")
    frame["official_cruise_count"] = frame["official_cruise_count"].fillna(0).astype(np.int64)
    return frame


def verify_run(run_dir: Path) -> dict[str, Any]:
    require(run_dir.is_dir(), f"run directory missing: {run_dir}")
    present = {path.name for path in run_dir.iterdir()}
    missing = REQUIRED_BEFORE_VERIFICATION - present
    require(not missing, f"required outputs missing: {sorted(missing)}")
    manifest_path = run_dir / "audit_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checks = verify_manifest(run_dir, manifest)
    config = yaml.safe_load(resolve(manifest["config_path"]).read_text(encoding="utf-8"))
    expected = config["expected"]

    inventory = pd.read_csv(run_dir / "source_artifact_inventory.tsv", sep="\t")
    identity = pd.read_csv(run_dir / "mrar_identity_ledger.tsv", sep="\t")
    capabilities = pd.read_csv(run_dir / "jamstec_file_capabilities.tsv", sep="\t")
    raw = pd.read_parquet(run_dir / "raw_point_contributions.parquet")
    file_cells = pd.read_parquet(run_dir / "file_cell_contributors.parquet")
    cruise_cells = pd.read_parquet(run_dir / "cell_official_cruise_contributors.parquet")
    exact = pd.read_parquet(run_dir / "exact_cell_replay.parquet")
    legacy = pd.read_parquet(run_dir / "legacy_52_replay_differences.parquet")
    multi = pd.read_parquet(run_dir / "multi_file_cell_summary.parquet")
    multi_details = pd.read_parquet(run_dir / "multi_file_contributor_details.parquet")
    invariance = pd.read_csv(run_dir / "replay_invariance.tsv", sep="\t")
    status_counts = pd.read_csv(run_dir / "factual_status_counts.tsv", sep="\t")
    frames = {
        "source_artifact_inventory.tsv": inventory,
        "mrar_identity_ledger.tsv": identity,
        "jamstec_file_capabilities.tsv": capabilities,
        "raw_point_contributions.parquet": raw,
        "file_cell_contributors.parquet": file_cells,
        "cell_official_cruise_contributors.parquet": cruise_cells,
        "exact_cell_replay.parquet": exact,
        "legacy_52_replay_differences.parquet": legacy,
        "multi_file_cell_summary.parquet": multi,
        "multi_file_contributor_details.parquet": multi_details,
        "replay_invariance.tsv": invariance,
    }
    for name, frame in frames.items():
        key = {"canonical_cell_id"} if "canonical_cell_id" in frame else {frame.columns[0]}
        validate_status_pairs(frame, key, name)
        forbidden = [str(token).lower() for token in config["output_guards"]["forbidden_column_tokens"]]
        violations = [column for column in frame if any(token in column.lower() for token in forbidden)]
        require(not violations, f"forbidden columns in {name}: {violations}")
    checks.append("schemas_and_five_level_status_pairs")

    require(len(raw) == int(expected["jamstec_raw_point_count"]) + int(expected["mrar_raw_point_count"]), "raw point row closure")
    require(raw["canonical_cell_id"].nunique() == int(expected["cell_count"]), "raw point cell closure")
    require(not raw.duplicated(["file_id", "raw_row_id"]).any(), "duplicate physical raw rows")
    require(raw["source_provider"].value_counts().to_dict() == {
        "jamstec": int(expected["jamstec_raw_point_count"]),
        "mrar": int(expected["mrar_raw_point_count"]),
    }, "raw point provider closure")
    checks.append("raw_point_key_and_count_closure")

    recomputed_file = recompute_file_cells(raw)
    compare_columns(file_cells, recomputed_file, ["canonical_cell_id", "file_id"], [
        "raw_point_count", "exact_median_m", "within_file_nmad_m", "min_depth_m",
        "max_depth_m", "depth_range_m", "raw_row_ranges_json",
    ], "file-cell recomputation")
    recomputed_cruise = recompute_cruise_cells(raw)
    compare_columns(cruise_cells, recomputed_cruise, ["canonical_cell_id", "contributor_group_key"], [
        "raw_point_count", "raw_file_count", "exact_median_m", "within_cruise_nmad_m",
        "min_depth_m", "max_depth_m", "depth_range_m",
    ], "cruise-cell recomputation")
    recomputed_cell = recompute_cells(raw, file_cells, cruise_cells)
    compare_columns(exact, recomputed_cell, ["canonical_cell_id"], [
        "raw_point_count", "raw_file_count", "official_cruise_count",
        "exact_pooled_point_median_m", "exact_pooled_point_nmad_m",
        "exact_file_balanced_median_m", "exact_cruise_balanced_median_m",
        "min_depth_m", "max_depth_m", "raw_depth_range_m",
    ], "cell replay recomputation")
    checks.append("raw_to_file_cruise_cell_exact_arithmetic")

    require(len(exact) == int(expected["cell_count"]), "exact replay cell count")
    require(len(legacy) == int(expected["historical_difference_count"]), "legacy 52 count")
    require(len(multi) == int(expected["multi_file_count"]), "multi-file count")
    require(int(multi["is_multi_cruise"].sum()) == int(expected["multi_cruise_count"]), "multi-cruise count")
    require(int(multi["frozen_aggregation_conflict_membership"].sum()) == int(expected["aggregation_conflict_count"]), "nine conflict count")
    require(set(multi_details["canonical_cell_id"]) == set(multi["canonical_cell_id"]), "multi-file contributor membership")
    checks.append("focused_52_2658_2472_9_closures")

    require(len(capabilities) == int(expected["jamstec_file_count"]), "58-file capability count")
    require(capabilities["file_id"].nunique() == int(expected["jamstec_file_count"]), "58-file capability key")
    for column in [
        "has_row_date", "has_row_time", "has_row_line_id", "has_row_navigation_record",
        "has_row_beam_id", "has_row_heading", "has_row_sonar_index", "has_row_quality_flag",
        "chronological_order_proven", "ping_order_proven",
    ]:
        require(not capabilities[column].astype(bool).any(), f"unsubstantiated JAMSTEC capability: {column}")
    require(capabilities["column_count"].eq(3).all(), "JAMSTEC column-count drift")
    require(capabilities["row_order_semantics"].eq("raw_record_order_only").all(), "row-order ceiling drift")
    require(capabilities["official_cruise_id"].nunique() == int(expected["jamstec_official_cruise_count"]), "official cruise count")
    checks.append("jamstec_58_file_capability_ceiling")

    require(identity["identity_status"].eq("not_recoverable").all(), "MRAR identity status drift")
    require(identity["source_independence"].eq("unknown").all(), "MRAR source independence drift")
    require(identity.loc[identity["claim_id"].eq("riam_uehara_tscs_association"), "value"].eq("no_direct_artifact_link").all(), "RIAM hypothesis result drift")
    checks.append("mrar_identity_terminal_state")

    require(len(invariance) == len(config["execution_variants"]), "invariance variant count")
    require(invariance["value_mismatch_count"].eq(0).all(), "invariance mismatch")
    require(invariance["maximum_absolute_numeric_difference_m"].eq(0).all(), "invariance numeric difference")
    for column in ["raw_point_canonical_sha256", "file_cell_canonical_sha256", "cell_replay_canonical_sha256"]:
        require(invariance[column].nunique() == 1, f"invariance digest mismatch: {column}")
    point_columns = [
        "canonical_cell_id", "source_provider", "file_id", "official_cruise_id",
        "contributor_group_key", "raw_file", "raw_row_id", "lon", "lat",
        "depth_m_positive_down",
    ]
    persisted_point_digest = canonical_frame_digest(raw, ["canonical_cell_id", "file_id", "raw_row_id"], point_columns)
    require(persisted_point_digest == invariance["raw_point_canonical_sha256"].iloc[0], "persisted raw-point canonical digest")
    checks.append("three_variant_and_persisted_digest_invariance")

    recomputed_status = build_status_counts(frames)
    compare_columns(status_counts, recomputed_status, ["artifact", "field", "factual_status"], ["count"], "factual status census")
    aggregate = status_counts.groupby("factual_status")["count"].sum()
    require(set(aggregate.index) == set(FIELD_STATUSES), "five-level aggregate missing explicit status")
    checks.append("factual_status_census")

    for row in inventory.itertuples(index=False):
        path = Path(row.path)
        require(path.is_file(), f"inventory path missing: {row.artifact_id}")
        require(path.stat().st_size == int(row.bytes), f"inventory size mismatch: {row.artifact_id}")
        require(sha256_file(path) == row.sha256, f"inventory SHA mismatch: {row.artifact_id}")
    checks.append("source_artifact_inventory_sha256")

    return {
        "status": "pass",
        "run_id": run_dir.name,
        "verified_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": sha256_file(manifest_path),
        "checks": checks,
        "counts": {
            "cells": len(exact),
            "raw_point_contributions": len(raw),
            "file_cell_contributors": len(file_cells),
            "cell_cruise_contributors": len(cruise_cells),
            "legacy_replay_differences": len(legacy),
            "multi_file_cells": len(multi),
            "multi_cruise_cells": int(multi["is_multi_cruise"].sum()),
            "aggregation_conflict_cells": int(multi["frozen_aggregation_conflict_membership"].sum()),
            "jamstec_capability_files": len(capabilities),
        },
        "factual_status_totals": {status: int(aggregate.get(status, 0)) for status in FIELD_STATUSES},
        "raw_point_canonical_sha256": persisted_point_digest,
    }


def atomic_write_json(value: dict[str, Any], path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    if Path.cwd().resolve() != REPO_ROOT:
        raise SystemExit(f"ERROR: run from repository root: {REPO_ROOT}")
    run_dir = resolve(args.run_dir).resolve()
    result = verify_run(run_dir)
    path = run_dir / "verification.json"
    if path.exists():
        raise FileExistsError(f"verification receipt already exists: {path}")
    atomic_write_json(result, path)
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"verification_sha256={sha256_file(path)}")


if __name__ == "__main__":
    main()
