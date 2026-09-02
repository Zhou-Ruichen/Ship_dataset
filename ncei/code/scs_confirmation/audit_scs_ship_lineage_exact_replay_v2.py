#!/usr/bin/env python3
"""Produce immutable MRAR/JAMSTEC lineage and exact-replay evidence for SCS.

Reads:
  - ncei/configs/scs_ship_lineage_exact_replay_v2.yaml
  - frozen SCS lineage/preflight receipts declared by that config
  - exactly the physical MRAR/JAMSTEC source files contributing to the cohort

Writes (full mode):
  - ncei/derived/scs_ship_qc_v2_preflight/lineage/<RUN_ID>/

Usage (run from repository root):
    python ncei/code/scs_confirmation/audit_scs_ship_lineage_exact_replay_v2.py \
      --config ncei/configs/scs_ship_lineage_exact_replay_v2.yaml --estimate-only
    python ncei/code/scs_confirmation/audit_scs_ship_lineage_exact_replay_v2.py \
      --config ncei/configs/scs_ship_lineage_exact_replay_v2.yaml \
      --run-id YYYYMMDDTHHMMSSZ --confirm-audit
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.util
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
JAM_ROOT = REPO_ROOT / "jamstec/multibeam"
NCEI_ROOT = REPO_ROOT / "ncei"
_UPSTREAM_PATH = NCEI_ROOT / "code/scs_confirmation/audit_scs_upstream_lineage.py"
_UPSTREAM_SPEC = importlib.util.spec_from_file_location("scs_upstream_lineage_v1", _UPSTREAM_PATH)
if _UPSTREAM_SPEC is None or _UPSTREAM_SPEC.loader is None:
    raise RuntimeError(f"cannot load existing lineage helpers: {_UPSTREAM_PATH}")
_UPSTREAM = importlib.util.module_from_spec(_UPSTREAM_SPEC)
_UPSTREAM_SPEC.loader.exec_module(_UPSTREAM)
cell_ids = _UPSTREAM.cell_ids
compress_ranges = _UPSTREAM.compress_ranges
load_official_metadata = _UPSTREAM.load_official_metadata
normalize_lon = _UPSTREAM.normalize_lon
normalize_mrar_lon = _UPSTREAM.normalize_mrar_lon
sha256_file = _UPSTREAM.sha256_file
stable_json = _UPSTREAM.stable_json
RUN_ID_RE = __import__("re").compile(r"\d{8}T\d{6}Z")
FIELD_STATUSES = (
    "known",
    "officially_unknown",
    "not_recoverable",
    "inferred_from_filename",
    "verified_from_source_metadata",
)
RAW_POINT_VALUE_COLUMNS = [
    "canonical_cell_id",
    "source_provider",
    "file_id",
    "official_cruise_id",
    "contributor_group_key",
    "raw_file",
    "raw_row_id",
    "lon",
    "lat",
    "depth_m_positive_down",
]
REQUIRED_OUTPUTS = (
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
)

LOGGER = logging.getLogger("scs_ship_lineage_exact_replay_v2")


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def relative_or_absolute(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def exact_stats(values: Iterable[float]) -> dict[str, float | int]:
    array = np.asarray(list(values), dtype=np.float64)
    array = array[np.isfinite(array)]
    if array.size == 0:
        raise ValueError("exact statistics require at least one finite value")
    median = float(np.median(array))
    return {
        "point_count": int(array.size),
        "median_m": median,
        "nmad_m": float(1.4826 * np.median(np.abs(array - median))) if array.size >= 2 else float("nan"),
        "min_m": float(array.min()),
        "max_m": float(array.max()),
        "range_m": float(array.max() - array.min()),
    }


def grouped_nmad_multi(
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


def add_status_pairs(
    frame: pd.DataFrame,
    key_columns: set[str],
    overrides: dict[str, Any] | None = None,
) -> pd.DataFrame:
    result = frame.copy()
    overrides = overrides or {}
    for column in list(result.columns):
        if column in key_columns or column.endswith("_status"):
            continue
        status_column = f"{column}_status"
        if status_column in result.columns:
            continue
        value = overrides.get(column, "known")
        result[status_column] = value(result) if callable(value) else value
    validate_status_pairs(result, key_columns)
    return result


def add_raw_point_statuses(points: pd.DataFrame) -> pd.DataFrame:
    return add_status_pairs(
        points,
        {"canonical_cell_id"},
        {
            "official_cruise_id": lambda frame: np.where(
                frame["source_provider"].eq("jamstec"),
                "verified_from_source_metadata",
                "not_recoverable",
            ),
        },
    )


def validate_status_pairs(frame: pd.DataFrame, key_columns: set[str]) -> None:
    values = [
        column for column in frame.columns
        if column not in key_columns and not column.endswith("_status")
    ]
    missing = [column for column in values if f"{column}_status" not in frame.columns]
    if missing:
        raise ValueError(f"factual fields missing paired statuses: {missing}")
    allowed = set(FIELD_STATUSES)
    for column in frame.columns:
        if not column.endswith("_status"):
            continue
        invalid = set(frame[column].dropna().astype(str)) - allowed
        if invalid:
            raise ValueError(f"invalid factual status in {column}: {sorted(invalid)}")


def validate_output_schema(frame: pd.DataFrame, forbidden_tokens: list[str]) -> None:
    forbidden = [token.lower() for token in forbidden_tokens]
    violations = [
        column for column in frame.columns
        if any(token in column.lower() for token in forbidden)
    ]
    if violations:
        raise ValueError(f"forbidden output columns: {violations}")


def validate_output_path(path: Path, forbidden_tokens: list[str]) -> None:
    lowered = str(path).lower()
    violations = [token for token in forbidden_tokens if token.lower() in lowered]
    if violations:
        raise ValueError(f"forbidden output path tokens {violations}: {path}")


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


def build_factual_status_counts(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
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


def _processing_values(provider: pd.Series) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    jam = provider.eq("jamstec")
    observed = np.where(jam, "processed_three_column_bathymetry_export", "processed_quadrant_point_bundle")
    observed_status = np.full(len(provider), "known", dtype=object)
    upstream = np.full(len(provider), "unknown", dtype=object)
    upstream_status = np.where(jam, "officially_unknown", "not_recoverable")
    return observed, observed_status, upstream, upstream_status


def _vertical_for(provider: str, cruise_id: Any, lookup: dict[str, dict[str, str]]) -> tuple[str, str]:
    key = str(cruise_id) if provider == "jamstec" and pd.notna(cruise_id) else "mrar_0-180E-0-85N.txt"
    record = lookup.get(key)
    if record:
        return str(record["vertical_datum"]), str(record["vertical_datum_status"])
    return ("unknown", "officially_unknown") if provider == "jamstec" else ("unknown", "not_recoverable")


def _range_json_by_file(group: pd.DataFrame) -> str:
    records = []
    for raw_file, rows in group.groupby("raw_file", sort=True):
        records.append({
            "raw_file": str(raw_file),
            "ranges_0_based_inclusive": compress_ranges(rows["raw_row_id"].to_numpy(dtype=np.int64)),
        })
    return stable_json(records)


def build_file_cell_contributors(
    points: pd.DataFrame,
    vertical_lookup: dict[str, dict[str, str]],
) -> pd.DataFrame:
    keys = ["canonical_cell_id", "file_id"]
    grouped = points.groupby(keys, sort=True, observed=True)
    result = grouped.agg(
        source_provider=("source_provider", "first"),
        official_cruise_id=("official_cruise_id", "first"),
        contributor_group_key=("contributor_group_key", "first"),
        raw_file=("raw_file", "first"),
        raw_point_count=("depth_m_positive_down", "size"),
        exact_median_m=("depth_m_positive_down", "median"),
        min_depth_m=("depth_m_positive_down", "min"),
        max_depth_m=("depth_m_positive_down", "max"),
    ).reset_index()
    result["within_file_nmad_m"] = grouped_nmad_multi(
        points, keys, "depth_m_positive_down"
    ).reindex(pd.MultiIndex.from_frame(result[keys])).to_numpy()
    result["depth_range_m"] = result["max_depth_m"] - result["min_depth_m"]
    range_map = grouped.apply(_range_json_by_file, include_groups=False)
    result["raw_row_ranges_json"] = range_map.reindex(pd.MultiIndex.from_frame(result[keys])).to_numpy()
    vertical = [
        _vertical_for(str(row.source_provider), row.official_cruise_id, vertical_lookup)
        for row in result.itertuples(index=False)
    ]
    result["vertical_datum"] = [item[0] for item in vertical]
    result["vertical_datum_status"] = [item[1] for item in vertical]
    observed, observed_status, upstream, upstream_status = _processing_values(result["source_provider"])
    result["observed_processing_level"] = observed
    result["observed_processing_level_status"] = observed_status
    result["upstream_processing_level"] = upstream
    result["upstream_processing_level_status"] = upstream_status
    overrides = {
        "official_cruise_id": lambda frame: np.where(
            frame["source_provider"].eq("jamstec"),
            "verified_from_source_metadata",
            "not_recoverable",
        ),
        "within_file_nmad_m": lambda frame: np.where(
            frame["within_file_nmad_m"].notna(), "known", "not_recoverable"
        ),
    }
    result = add_status_pairs(result, {"canonical_cell_id"}, overrides)
    return result.sort_values(keys).reset_index(drop=True)


def build_cell_cruise_contributors(
    points: pd.DataFrame,
    vertical_lookup: dict[str, dict[str, str]],
    file_cells: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if file_cells is None:
        file_cells = build_file_cell_contributors(points, vertical_lookup)
    keys = ["canonical_cell_id", "contributor_group_key"]
    grouped = points.groupby(keys, sort=True, observed=True)
    result = grouped.agg(
        source_provider=("source_provider", "first"),
        official_cruise_id=("official_cruise_id", "first"),
        raw_point_count=("depth_m_positive_down", "size"),
        raw_file_count=("file_id", "nunique"),
        exact_median_m=("depth_m_positive_down", "median"),
        min_depth_m=("depth_m_positive_down", "min"),
        max_depth_m=("depth_m_positive_down", "max"),
    ).reset_index()
    result["within_cruise_nmad_m"] = grouped_nmad_multi(
        points, keys, "depth_m_positive_down"
    ).reindex(pd.MultiIndex.from_frame(result[keys])).to_numpy()
    result["depth_range_m"] = result["max_depth_m"] - result["min_depth_m"]

    details = file_cells.groupby(keys, sort=True, observed=True).apply(
        lambda group: stable_json([
            {
                "file_id": str(row.file_id),
                "raw_file": str(row.raw_file),
                "raw_row_ranges_0_based_inclusive": json.loads(row.raw_row_ranges_json)[0]["ranges_0_based_inclusive"],
                "raw_point_count": int(row.raw_point_count),
            }
            for row in group.sort_values("file_id").itertuples(index=False)
        ]),
        include_groups=False,
    )
    result["source_file_rows_json"] = details.reindex(pd.MultiIndex.from_frame(result[keys])).to_numpy()
    vertical = [
        _vertical_for(str(row.source_provider), row.official_cruise_id, vertical_lookup)
        for row in result.itertuples(index=False)
    ]
    result["vertical_datum"] = [item[0] for item in vertical]
    result["vertical_datum_status"] = [item[1] for item in vertical]
    observed, observed_status, upstream, upstream_status = _processing_values(result["source_provider"])
    result["observed_processing_level"] = observed
    result["observed_processing_level_status"] = observed_status
    result["upstream_processing_level"] = upstream
    result["upstream_processing_level_status"] = upstream_status
    overrides = {
        "official_cruise_id": lambda frame: np.where(
            frame["source_provider"].eq("jamstec"),
            "verified_from_source_metadata",
            "not_recoverable",
        ),
        "within_cruise_nmad_m": lambda frame: np.where(
            frame["within_cruise_nmad_m"].notna(), "known", "not_recoverable"
        ),
    }
    result = add_status_pairs(result, {"canonical_cell_id"}, overrides)
    return result.sort_values(keys).reset_index(drop=True)


def build_exact_cell_replay(
    points: pd.DataFrame,
    file_cells: pd.DataFrame,
    cruise_cells: pd.DataFrame,
    history: pd.DataFrame,
) -> pd.DataFrame:
    grouped = points.groupby("canonical_cell_id", sort=True, observed=True)
    result = grouped.agg(
        source_provider=("source_provider", "first"),
        raw_point_count=("depth_m_positive_down", "size"),
        exact_pooled_point_median_m=("depth_m_positive_down", "median"),
        min_depth_m=("depth_m_positive_down", "min"),
        max_depth_m=("depth_m_positive_down", "max"),
    ).reset_index()
    result["exact_pooled_point_nmad_m"] = grouped_nmad_multi(
        points, "canonical_cell_id", "depth_m_positive_down"
    ).reindex(result["canonical_cell_id"]).to_numpy()
    result["raw_depth_range_m"] = result["max_depth_m"] - result["min_depth_m"]

    files = file_cells.groupby("canonical_cell_id", sort=True, observed=True).agg(
        raw_file_count=("file_id", "size"),
        exact_file_balanced_median_m=("exact_median_m", "median"),
        between_file_nmad_m=("exact_median_m", lambda values: exact_stats(values)["nmad_m"]),
    ).reset_index()
    result = result.merge(files, on="canonical_cell_id", validate="one_to_one")

    official = cruise_cells[cruise_cells["official_cruise_id"].notna()]
    cruises = official.groupby("canonical_cell_id", sort=True, observed=True).agg(
        official_cruise_count=("official_cruise_id", "nunique"),
        exact_cruise_balanced_median_m=("exact_median_m", "median"),
        between_cruise_nmad_m=("exact_median_m", lambda values: exact_stats(values)["nmad_m"]),
    ).reset_index()
    result = result.merge(cruises, on="canonical_cell_id", how="left", validate="one_to_one")
    result["official_cruise_count"] = result["official_cruise_count"].fillna(0).astype(np.int64)

    history_columns = [
        "canonical_cell_id", "source_provider", "frozen_depth_m", "replayed_depth_m",
        "signed_diff_m", "replay_result",
    ]
    historical = history[history_columns].rename(columns={
        "source_provider": "historical_source_provider",
        "replayed_depth_m": "historical_exact_file_balanced_median_m",
        "signed_diff_m": "historical_exact_minus_frozen_m",
        "replay_result": "historical_replay_result",
    })
    result = result.merge(historical, on="canonical_cell_id", validate="one_to_one")
    if not result["source_provider"].equals(result["historical_source_provider"]):
        raise ValueError("historical/current source-provider mismatch")
    result = result.drop(columns="historical_source_provider")
    result["pooled_point_minus_frozen_m"] = result["exact_pooled_point_median_m"] - result["frozen_depth_m"]
    result["file_balanced_minus_frozen_m"] = result["exact_file_balanced_median_m"] - result["frozen_depth_m"]
    result["cruise_balanced_minus_frozen_m"] = result["exact_cruise_balanced_median_m"] - result["frozen_depth_m"]
    result["exact_pooled_method"] = "median_of_all_qc_passed_raw_points"
    result["exact_file_balanced_method"] = "median_of_exact_file_cell_raw_point_medians"
    result["exact_cruise_balanced_method"] = np.where(
        result["source_provider"].eq("jamstec"),
        "median_of_exact_official_cruise_cell_raw_point_medians",
        "not_defined_without_recoverable_cruise_identity",
    )
    result["diagnostic_only"] = True
    overrides = {
        "official_cruise_count": lambda frame: np.where(
            frame["source_provider"].eq("jamstec"),
            "verified_from_source_metadata",
            "not_recoverable",
        ),
        "exact_cruise_balanced_median_m": lambda frame: np.where(
            frame["exact_cruise_balanced_median_m"].notna(),
            "known",
            "not_recoverable",
        ),
        "between_cruise_nmad_m": lambda frame: np.where(
            frame["between_cruise_nmad_m"].notna(), "known", "not_recoverable"
        ),
        "cruise_balanced_minus_frozen_m": lambda frame: np.where(
            frame["cruise_balanced_minus_frozen_m"].notna(), "known", "not_recoverable"
        ),
        "exact_pooled_point_nmad_m": lambda frame: np.where(
            frame["exact_pooled_point_nmad_m"].notna(), "known", "not_recoverable"
        ),
        "between_file_nmad_m": lambda frame: np.where(
            frame["between_file_nmad_m"].notna(), "known", "not_recoverable"
        ),
    }
    result = add_status_pairs(result, {"canonical_cell_id"}, overrides)
    return result.sort_values("canonical_cell_id").reset_index(drop=True)


def load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    required = {
        "schema_version", "inputs", "mrar_artifacts", "mrar_identity_search",
        "output_root", "execution_variants", "expected",
        "factual_status_vocabulary", "output_guards",
    }
    missing = required - set(config)
    if missing:
        raise ValueError(f"config missing required keys: {sorted(missing)}")
    if tuple(config["factual_status_vocabulary"]) != FIELD_STATUSES:
        raise ValueError("five-level factual status vocabulary/order drift")
    if len(config["execution_variants"]) < 3:
        raise ValueError("at least three execution variants are required")
    return config


def validate_frozen_files(config: dict[str, Any]) -> tuple[dict[str, Path], dict[str, dict[str, Any]]]:
    paths: dict[str, Path] = {}
    records: dict[str, dict[str, Any]] = {}
    declared = list(config["inputs"].items()) + [
        (f"mrar_artifact_{index:02d}", item)
        for index, item in enumerate(config["mrar_artifacts"], start=1)
    ]
    for name, item in declared:
        path = resolve_repo_path(item["path"]).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"missing frozen input {name}: {path}")
        observed = sha256_file(path)
        if observed != str(item["sha256"]):
            raise ValueError(f"input SHA256 drift for {name}: {observed} != {item['sha256']}")
        paths[name] = path
        records[name] = {
            "path": relative_or_absolute(path),
            "sha256": observed,
            "bytes": path.stat().st_size,
        }
    verification = json.loads(paths["preflight_verification"].read_text(encoding="utf-8"))
    if verification.get("status") != "pass":
        raise ValueError("frozen preflight verification is not pass")
    manifest = json.loads(paths["preflight_manifest"].read_text(encoding="utf-8"))
    candidate_records = [item for item in manifest.get("outputs", []) if item.get("path") == "candidate_cells.parquet"]
    if len(candidate_records) != 1 or candidate_records[0]["sha256"] != config["inputs"]["preflight_candidates"]["sha256"]:
        raise ValueError("preflight candidate receipt mismatch")
    return paths, records


def load_frozen_tables(
    paths: dict[str, Path],
    config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, set[str]]:
    lineage = pd.read_parquet(paths["cell_lineage"])
    history = pd.read_parquet(paths["historical_replay"])
    vertical = pd.read_csv(paths["vertical_datum_ledger"])
    manifest = pd.read_parquet(paths["jamstec_file_manifest"])
    allowed = list(config["inputs"]["preflight_candidates"]["allowed_columns"])
    candidates = pd.read_parquet(paths["preflight_candidates"], columns=allowed)
    expected = config["expected"]
    if len(lineage) != int(expected["cell_count"]) or lineage["canonical_cell_id"].nunique() != int(expected["cell_count"]):
        raise ValueError("lineage cell closure drift")
    if lineage["source_provider"].value_counts().to_dict() != {
        key: int(value) for key, value in expected["provider_counts"].items()
    }:
        raise ValueError("lineage source closure drift")
    if set(lineage["canonical_cell_id"]) != set(history["canonical_cell_id"]):
        raise ValueError("lineage/history key mismatch")
    if int(history["replay_result"].eq("different").sum()) != int(expected["historical_difference_count"]):
        raise ValueError("historical 52-cell closure drift")
    conflict_ids = set(
        candidates.loc[candidates["interpretation_state"].eq("aggregation_conflict"), "canonical_cell_id"].astype(str)
    )
    if len(conflict_ids) != int(expected["aggregation_conflict_count"]):
        raise ValueError("frozen nine-cell aggregation-conflict closure drift")
    if vertical["source_cruise"].duplicated().any():
        raise ValueError("vertical ledger source_cruise is not unique")
    return lineage, history, vertical, manifest, conflict_ids


def extract_raw_expectations(lineage: pd.DataFrame) -> tuple[dict[str, str], set[str], set[str]]:
    hashes: dict[str, str] = {}
    for value in lineage["raw_file_sha256_json"]:
        for path, digest in json.loads(value).items():
            if path in hashes and hashes[path] != digest:
                raise ValueError(f"conflicting raw hash lineage: {path}")
            hashes[path] = str(digest)
    jam_targets = set(lineage.loc[lineage["source_provider"].eq("jamstec"), "canonical_cell_id"].astype(str))
    mrar_targets = set(lineage.loc[lineage["source_provider"].eq("mrar"), "canonical_cell_id"].astype(str))
    return hashes, jam_targets, mrar_targets


def validate_raw_sources(expected_hashes: dict[str, str]) -> dict[str, dict[str, Any]]:
    records = {}
    for raw_file, expected in sorted(expected_hashes.items()):
        path = resolve_repo_path(raw_file).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"missing lineage raw source: {path}")
        observed = sha256_file(path)
        if observed != expected:
            raise ValueError(f"lineage raw source SHA drift: {raw_file}")
        records[raw_file] = {"path": raw_file, "sha256": observed, "bytes": path.stat().st_size}
    return records


def discover_jamstec_metadata(
    lineage: pd.DataFrame,
    manifest: pd.DataFrame,
    expected_file_count: int,
) -> pd.DataFrame:
    prefix = "jamstec/multibeam/raw/dat_by_subzip/"
    raw_files = sorted({
        path
        for value in lineage.loc[lineage["source_provider"].eq("jamstec"), "raw_files_json"]
        for path in json.loads(value)
    })
    if any(not path.startswith(prefix) for path in raw_files):
        raise ValueError("unexpected JAMSTEC raw path outside canonical root")
    relative_paths = {path[len(prefix):] for path in raw_files}
    used = manifest[manifest["relative_path"].isin(relative_paths)].copy()
    if len(used) != expected_file_count or used["relative_path"].nunique() != expected_file_count:
        raise ValueError("58-file exact relative-path join closure failed")
    if set(used["relative_path"]) != relative_paths:
        raise ValueError("JAMSTEC relative-path membership drift")
    if used["file_id"].duplicated().any():
        raise ValueError("JAMSTEC contributor file_id is not unique")
    return used.sort_values("file_id").reset_index(drop=True)


def _scan_jamstec_file(
    meta: Any,
    target_ids: set[str],
    batch_rows: int,
    official: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = JAM_ROOT / "raw/dat_by_subzip" / str(meta.relative_path)
    selected: list[pd.DataFrame] = []
    row_offset = 0
    observed_columns: set[int] = set()
    for chunk in pd.read_csv(
        path, sep=r"\s+", header=None, chunksize=batch_rows, engine="c", dtype=np.float64
    ):
        observed_columns.add(int(chunk.shape[1]))
        if chunk.shape[1] != 3:
            raise ValueError(f"JAMSTEC contributor is not exactly three columns: {path}")
        n_rows = len(chunk)
        lon = normalize_lon(chunk.iloc[:, 0].to_numpy(dtype=np.float64))
        lat = chunk.iloc[:, 1].to_numpy(dtype=np.float64)
        depth = chunk.iloc[:, 2].to_numpy(dtype=np.float64)
        qc = (
            np.isfinite(lon) & np.isfinite(lat) & np.isfinite(depth)
            & (lon >= -180.0) & (lon < 180.0)
            & (lat >= -90.0) & (lat <= 90.0)
            & (depth > 0.0) & (depth <= 12_000.0)
        )
        ids = np.full(n_rows, "", dtype=object)
        ids[qc] = cell_ids(lon[qc], lat[qc])
        keep = qc & pd.Index(ids).isin(target_ids)
        if keep.any():
            selected.append(pd.DataFrame({
                "canonical_cell_id": ids[keep],
                "source_provider": "jamstec",
                "file_id": str(meta.file_id),
                "official_cruise_id": str(official["cruise_id"]),
                "contributor_group_key": "official_cruise:" + str(official["cruise_id"]),
                "raw_file": str(path.relative_to(REPO_ROOT)),
                "raw_row_id": np.arange(row_offset, row_offset + n_rows, dtype=np.int64)[keep],
                "lon": lon[keep],
                "lat": lat[keep],
                "depth_m_positive_down": depth[keep],
            }))
        row_offset += n_rows
    if row_offset != int(meta.line_count):
        raise ValueError(f"JAMSTEC raw line-count drift for {meta.file_id}: {row_offset} != {meta.line_count}")
    if not selected:
        raise ValueError(f"JAMSTEC contributor has no frozen-cohort points: {meta.file_id}")
    points = pd.concat(selected, ignore_index=True)
    return points, {
        "file_id": str(meta.file_id),
        "raw_file": str(path.relative_to(REPO_ROOT)),
        "line_count": row_offset,
        "observed_column_counts": sorted(observed_columns),
        "selected_point_count": len(points),
    }


def _ordered_metadata(metadata: pd.DataFrame, order: str, seed: int) -> list[Any]:
    rows = list(metadata.sort_values("file_id").itertuples(index=False))
    if order == "ascending":
        return rows
    if order == "descending":
        return list(reversed(rows))
    if order == "seeded":
        indices = np.random.default_rng(seed).permutation(len(rows))
        return [rows[int(index)] for index in indices]
    raise ValueError(f"unsupported file order: {order}")


def scan_jamstec_variant(
    metadata: pd.DataFrame,
    target_ids: set[str],
    official: dict[str, dict[str, Any]],
    batch_rows: int,
    file_order: str,
    workers: int,
    seed: int,
) -> tuple[list[pd.DataFrame], dict[str, dict[str, Any]]]:
    ordered = _ordered_metadata(metadata, file_order, seed)
    frames: dict[str, pd.DataFrame] = {}
    stats: dict[str, dict[str, Any]] = {}

    def run(meta: Any) -> tuple[str, pd.DataFrame, dict[str, Any]]:
        frame, record = _scan_jamstec_file(meta, target_ids, batch_rows, official[str(meta.subzip_id)])
        return str(meta.file_id), frame, record

    if workers == 1:
        for position, meta in enumerate(ordered, start=1):
            file_id, frame, record = run(meta)
            frames[file_id] = frame
            stats[file_id] = record
            LOGGER.info("JAMSTEC %d/%d %s selected=%d", position, len(ordered), file_id, len(frame))
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(run, meta): str(meta.file_id) for meta in ordered}
            completed = 0
            for future in as_completed(futures):
                file_id, frame, record = future.result()
                frames[file_id] = frame
                stats[file_id] = record
                completed += 1
                LOGGER.info("JAMSTEC %d/%d %s selected=%d", completed, len(ordered), file_id, len(frame))
    return [frames[str(meta.file_id)] for meta in ordered], stats


def scan_mrar_points(target_ids: set[str], batch_rows: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = NCEI_ROOT / "archive/zhoushuai_processed_M/0-180E-0-85N.txt"
    selected: list[pd.DataFrame] = []
    row_offset = 0
    for chunk_number, chunk in enumerate(pd.read_csv(
        path,
        sep="\t",
        header=None,
        usecols=[0, 1, 2],
        names=["lon_raw", "lat_raw", "depth_raw"],
        chunksize=batch_rows,
        engine="c",
        dtype=np.float64,
    ), start=1):
        n_rows = len(chunk)
        lon = normalize_mrar_lon(chunk["lon_raw"].to_numpy(dtype=np.float64))
        lat = chunk["lat_raw"].to_numpy(dtype=np.float64)
        depth = -chunk["depth_raw"].to_numpy(dtype=np.float64)
        qc = (
            np.isfinite(lon) & np.isfinite(lat) & np.isfinite(depth)
            & (lon >= -180.0) & (lon < 180.0)
            & (lat >= -90.0) & (lat <= 90.0)
            & (depth > 0.0) & (depth <= 11_500.0)
        )
        ids = np.full(n_rows, "", dtype=object)
        ids[qc] = cell_ids(lon[qc], lat[qc])
        keep = qc & pd.Index(ids).isin(target_ids)
        if keep.any():
            selected.append(pd.DataFrame({
                "canonical_cell_id": ids[keep],
                "source_provider": "mrar",
                "file_id": "mrar_0-180E-0-85N.txt",
                "official_cruise_id": None,
                "contributor_group_key": "unresolved_source:mrar",
                "raw_file": str(path.relative_to(REPO_ROOT)),
                "raw_row_id": np.arange(row_offset, row_offset + n_rows, dtype=np.int64)[keep],
                "lon": lon[keep],
                "lat": lat[keep],
                "depth_m_positive_down": depth[keep],
            }))
        row_offset += n_rows
        LOGGER.info("MRAR chunk %d scanned=%d", chunk_number, row_offset)
    points = pd.concat(selected, ignore_index=True)
    if set(points["canonical_cell_id"]) != target_ids:
        raise ValueError("MRAR raw replay cell closure failed")
    return points, {
        "file_id": "mrar_0-180E-0-85N.txt",
        "raw_file": str(path.relative_to(REPO_ROOT)),
        "line_count": row_offset,
        "observed_column_counts": [3],
        "selected_point_count": len(points),
    }


def scan_variant(
    metadata: pd.DataFrame,
    jam_targets: set[str],
    mrar_targets: set[str],
    official: dict[str, dict[str, Any]],
    variant: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    jam_frames, stats = scan_jamstec_variant(
        metadata,
        jam_targets,
        official,
        int(variant["batch_rows"]),
        str(variant["file_order"]),
        int(variant["workers"]),
        int(variant["seed"]),
    )
    mrar, mrar_stats = scan_mrar_points(mrar_targets, int(variant["batch_rows"]))
    stats[mrar_stats["file_id"]] = mrar_stats
    points = pd.concat([*jam_frames, mrar], ignore_index=True)
    return points, stats


def validate_raw_point_closure(
    points: pd.DataFrame,
    lineage: pd.DataFrame,
    expected: dict[str, Any],
) -> None:
    if points.duplicated(["file_id", "raw_row_id"]).any():
        raise ValueError("duplicate physical raw row in selected point contributions")
    if points["canonical_cell_id"].nunique() != int(expected["cell_count"]):
        raise ValueError("raw-point cell closure drift")
    counts = points["source_provider"].value_counts().to_dict()
    expected_points = {
        "jamstec": int(expected["jamstec_raw_point_count"]),
        "mrar": int(expected["mrar_raw_point_count"]),
    }
    if counts != expected_points:
        raise ValueError(f"raw-point source count drift: {counts} != {expected_points}")
    observed = points.groupby("canonical_cell_id").size().rename("observed")
    frozen = lineage.set_index("canonical_cell_id")["raw_point_count"].rename("frozen")
    joined = frozen.to_frame().join(observed, how="outer")
    if not joined["frozen"].equals(joined["observed"]):
        raise ValueError("per-cell raw point count differs from frozen lineage")


def _schema_json(path: Path) -> tuple[str, int | None]:
    if path.suffix == ".parquet":
        parquet = pq.ParquetFile(path)
        schema = [{"name": field.name, "type": str(field.type)} for field in parquet.schema_arrow]
        return stable_json(schema), int(parquet.metadata.num_rows)
    return stable_json([]), None


def _count_lines(path: Path) -> int:
    count = 0
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            count += chunk.count(b"\n")
    return count


def _rar_members(path: Path) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["7z", "l", "-slt", str(path)], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    members = []
    for block in result.stdout.split("\n\n"):
        values = {}
        for line in block.splitlines():
            if " = " in line:
                key, value = line.split(" = ", 1)
                values[key.strip()] = value.strip()
        member = values.get("Path", "")
        if member.startswith("M/") and member.endswith(".txt"):
            members.append({
                "path": member,
                "size_bytes": int(values["Size"]),
                "modified": values.get("Modified"),
                "method": values.get("Method"),
            })
    if len(members) != 3:
        raise ValueError(f"expected three M.rar text members, found {len(members)}")
    return sorted(members, key=lambda item: item["path"])


def _inventory_row(
    artifact_id: str,
    role: str,
    path: Path,
    version: str,
    version_status: str,
    row_count: int | None,
    schema_json: str,
    archive_members_json: str,
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "artifact_role": role,
        "path": str(path.resolve()),
        "repository_relative_path": relative_or_absolute(path),
        "artifact_version": version,
        "bytes": path.stat().st_size,
        "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "sha256": sha256_file(path),
        "row_count": row_count,
        "schema_json": schema_json,
        "archive_members_json": archive_members_json,
        "artifact_role_status": "known",
        "path_status": "known",
        "repository_relative_path_status": "known",
        "artifact_version_status": version_status,
        "bytes_status": "known",
        "mtime_utc_status": "known",
        "sha256_status": "known",
        "row_count_status": "known" if row_count is not None else "not_recoverable",
        "schema_json_status": "known" if schema_json != "[]" else "not_recoverable",
        "archive_members_json_status": "known" if archive_members_json != "[]" else "not_recoverable",
    }


def build_source_inventory(
    config: dict[str, Any],
    metadata: pd.DataFrame,
    official: dict[str, dict[str, Any]],
    scan_stats: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    rar_members = stable_json(_rar_members(resolve_repo_path(config["mrar_artifacts"][0]["path"])))
    for index, item in enumerate(config["mrar_artifacts"], start=1):
        path = resolve_repo_path(item["path"])
        schema_json, parquet_rows = _schema_json(path)
        row_count = parquet_rows
        if path.suffix == ".txt":
            row_count = _count_lines(path)
            if row_count != int(item["expected_rows"]):
                raise ValueError(f"MRAR extracted row-count drift: {path}")
            schema_json = stable_json([
                {"name": "longitude", "type": "float64"},
                {"name": "latitude", "type": "float64"},
                {"name": "depth_negative_down_m", "type": "float64"},
            ])
        if "expected_rows" in item and row_count != int(item["expected_rows"]):
            raise ValueError(f"MRAR artifact row-count drift: {path}")
        rows.append(_inventory_row(
            f"mrar_{index:02d}", str(item["role"]), path,
            str(item["version"]), str(item["version_status"]), row_count,
            schema_json, rar_members if path.name == "M.rar" else stable_json([]),
        ))

    manifest_path = JAM_ROOT / "manifests/file_manifest_points_raw.parquet"
    manifest_schema, manifest_rows = _schema_json(manifest_path)
    rows.append(_inventory_row(
        "jamstec_manifest", "contributor_manifest", manifest_path,
        "current_frozen_bytes", "known", manifest_rows, manifest_schema, stable_json([]),
    ))
    for position, meta in enumerate(metadata.sort_values("file_id").itertuples(index=False), start=1):
        path = JAM_ROOT / "raw/dat_by_subzip" / str(meta.relative_path)
        stat = scan_stats[str(meta.file_id)]
        rows.append(_inventory_row(
            f"jamstec_raw_{position:02d}", "contributing_processed_bathymetry_file", path,
            "unversioned_processed_export", "officially_unknown", int(stat["line_count"]),
            stable_json([
                {"name": "longitude", "type": "float64"},
                {"name": "latitude", "type": "float64"},
                {"name": "depth_positive_down_m", "type": "float64"},
            ]), stable_json([]),
        ))
    for position, record in enumerate(sorted(official.values(), key=lambda item: item["pdf_path"]), start=1):
        path = resolve_repo_path(record["pdf_path"])
        rows.append(_inventory_row(
            f"jamstec_official_{position:02d}", "official_cruise_bathymetry_metadata", path,
            "unversioned_official_pdf", "verified_from_source_metadata", None,
            stable_json([]), stable_json([]),
        ))
    inventory = pd.DataFrame(rows).sort_values("artifact_id").reset_index(drop=True)
    validate_status_pairs(inventory, {"artifact_id"})
    return inventory


def build_mrar_identity_ledger(config: dict[str, Any]) -> pd.DataFrame:
    search = config["mrar_identity_search"]
    source_path = resolve_repo_path("ncei/archive/zhoushuai_processed_M/SOURCE.md")
    archive_path = resolve_repo_path("ncei/archive/zhoushuai_processed_M/M.rar")
    common = {
        "identity_status": str(search["identity_status"]),
        "identity_status_status": "known",
        "source_independence": str(search["source_independence"]),
        "source_independence_status": "not_recoverable",
        "search_stop_rule": str(search["stop_rule"]),
        "search_stop_rule_status": "known",
        "search_completed_utc": str(search["completed_utc"]),
        "search_completed_utc_status": "known",
    }
    rows = [
        {
            "claim_id": "mrar_name_expansion",
            "claim": "Expansion of MRAR or M.rar",
            "value": "unknown",
            "evidence_summary": "No expansion is present in archive metadata, filenames, local provenance records, or retained README because no README accompanied delivery.",
            "evidence_paths_json": stable_json([relative_or_absolute(archive_path), relative_or_absolute(source_path)]),
            "official_urls_json": stable_json([]),
            "geometry_comparison": "not_applicable",
            "conclusion": "not_recoverable",
            **common,
        },
        {
            "claim_id": "delivery_source",
            "claim": "Retained delivery source",
            "value": "Zhou Shuai handoff via /mnt/data2/00-Data/tmp/ on 2026-05-15",
            "evidence_summary": "Recorded directly in the repository provenance document; no upstream README was delivered.",
            "evidence_paths_json": stable_json([relative_or_absolute(source_path)]),
            "official_urls_json": stable_json([]),
            "geometry_comparison": "not_applicable",
            "conclusion": "known_delivery_chain_only",
            **common,
        },
        {
            "claim_id": "pre_delivery_processing_level",
            "claim": "Processing level before local cleaning",
            "value": "unknown",
            "evidence_summary": "The earliest retained bytes are already a three-file quadrant-partitioned processed point bundle; the producer, filters, decimation, and source cruises are absent.",
            "evidence_paths_json": stable_json([relative_or_absolute(archive_path), relative_or_absolute(source_path)]),
            "official_urls_json": stable_json([]),
            "geometry_comparison": "processed_file_structure_observed",
            "conclusion": "not_recoverable",
            **common,
        },
        {
            "claim_id": "riam_uehara_tscs_association",
            "claim": "M.rar association with RIAM Uehara Tscs",
            "value": "no_direct_artifact_link",
            "evidence_summary": str(search["finding"]),
            "evidence_paths_json": stable_json([relative_or_absolute(archive_path), relative_or_absolute(source_path)]),
            "official_urls_json": stable_json(list(search["official_urls"])),
            "geometry_comparison": str(search["geometry_result"]),
            "conclusion": "hypothesis_unverified_and_search_closed",
            **common,
        },
        {
            "claim_id": "source_independence",
            "claim": "Independence from downstream reference/evaluation sources",
            "value": "unknown",
            "evidence_summary": "Cruise identity and upstream source membership cannot be reconstructed, so source overlap or independence cannot be established.",
            "evidence_paths_json": stable_json([relative_or_absolute(source_path)]),
            "official_urls_json": stable_json([]),
            "geometry_comparison": "insufficient_for_independence",
            "conclusion": "unknown",
            **common,
        },
    ]
    frame = pd.DataFrame(rows)
    overrides = {
        "claim": "known",
        "value": lambda df: np.where(
            df["claim_id"].eq("delivery_source"), "known", "not_recoverable"
        ),
        "evidence_summary": "known",
        "evidence_paths_json": "known",
        "official_urls_json": lambda df: np.where(
            df["claim_id"].eq("riam_uehara_tscs_association"),
            "verified_from_source_metadata",
            "not_recoverable",
        ),
        "geometry_comparison": lambda df: np.where(
            df["geometry_comparison"].eq("not_applicable"), "not_recoverable", "known"
        ),
        "conclusion": "known",
    }
    return add_status_pairs(frame, {"claim_id"}, overrides)


def build_jamstec_capabilities(
    metadata: pd.DataFrame,
    official: dict[str, dict[str, Any]],
    vertical_lookup: dict[str, dict[str, str]],
    scan_stats: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    rows = []
    for meta in metadata.sort_values("file_id").itertuples(index=False):
        official_record = official[str(meta.subzip_id)]
        raw_path = JAM_ROOT / "raw/dat_by_subzip" / str(meta.relative_path)
        stat = scan_stats[str(meta.file_id)]
        datum, datum_status = _vertical_for("jamstec", official_record["cruise_id"], vertical_lookup)
        rows.append({
            "file_id": str(meta.file_id),
            "relative_path": str(meta.relative_path),
            "raw_file": str(raw_path.relative_to(REPO_ROOT)),
            "raw_file_sha256": sha256_file(raw_path),
            "size_bytes": raw_path.stat().st_size,
            "line_count": int(stat["line_count"]),
            "manifest_line_count": int(meta.line_count),
            "format": "headerless_ascii_whitespace_xyz",
            "column_count": 3,
            "data_layout": str(meta.data_layout),
            "observed_processing_level": "processed_three_column_bathymetry_export",
            "upstream_processing_level": "unknown",
            "has_row_longitude": True,
            "has_row_latitude": True,
            "has_row_depth": True,
            "has_row_date": False,
            "has_row_time": False,
            "has_row_line_id": False,
            "has_row_navigation_record": False,
            "coordinate_provenance": "unknown",
            "has_row_beam_id": False,
            "has_row_heading": False,
            "has_row_sonar_index": False,
            "has_row_quality_flag": False,
            "row_order_semantics": "raw_record_order_only",
            "chronological_order_proven": False,
            "ping_order_proven": False,
            "official_cruise_id": str(official_record["cruise_id"]),
            "official_period": str(official_record["period"]),
            "official_sonar": str(official_record["sonar"]),
            "vertical_datum": datum,
            "source_metadata_path": str(official_record["pdf_path"]),
            "source_metadata_sha256": str(official_record["pdf_sha256"]),
            "relative_path_status": "known",
            "raw_file_status": "known",
            "raw_file_sha256_status": "known",
            "size_bytes_status": "known",
            "line_count_status": "known",
            "manifest_line_count_status": "known",
            "format_status": "known",
            "column_count_status": "known",
            "data_layout_status": "known",
            "observed_processing_level_status": "known",
            "upstream_processing_level_status": "officially_unknown",
            "has_row_longitude_status": "known",
            "has_row_latitude_status": "known",
            "has_row_depth_status": "known",
            "has_row_date_status": "known",
            "has_row_time_status": "known",
            "has_row_line_id_status": "known",
            "has_row_navigation_record_status": "known",
            "coordinate_provenance_status": "officially_unknown",
            "has_row_beam_id_status": "known",
            "has_row_heading_status": "known",
            "has_row_sonar_index_status": "known",
            "has_row_quality_flag_status": "known",
            "row_order_semantics_status": "known",
            "chronological_order_proven_status": "known",
            "ping_order_proven_status": "known",
            "official_cruise_id_status": "verified_from_source_metadata",
            "official_period_status": "verified_from_source_metadata",
            "official_sonar_status": "verified_from_source_metadata",
            "vertical_datum_status": datum_status,
            "source_metadata_path_status": "known",
            "source_metadata_sha256_status": "known",
        })
    frame = pd.DataFrame(rows)
    validate_status_pairs(frame, {"file_id"})
    return frame.sort_values("file_id").reset_index(drop=True)


def _cell_contributor_json(file_cells: pd.DataFrame) -> pd.Series:
    return file_cells.groupby("canonical_cell_id", sort=True).apply(
        lambda group: stable_json([
            {
                "file_id": str(row.file_id),
                "official_cruise_id": None if pd.isna(row.official_cruise_id) else str(row.official_cruise_id),
                "raw_file": str(row.raw_file),
                "raw_row_ranges_0_based_inclusive": json.loads(row.raw_row_ranges_json)[0]["ranges_0_based_inclusive"],
                "raw_point_count": int(row.raw_point_count),
                "exact_file_cell_median_m": float(row.exact_median_m),
            }
            for row in group.sort_values("file_id").itertuples(index=False)
        ]),
        include_groups=False,
    )


def build_focused_outputs(
    exact_replay: pd.DataFrame,
    file_cells: pd.DataFrame,
    conflict_ids: set[str],
    expected: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    contributors_json = _cell_contributor_json(file_cells)
    legacy = exact_replay[exact_replay["historical_replay_result"].eq("different")].copy()
    legacy["contributor_records_json"] = legacy["canonical_cell_id"].map(contributors_json)
    legacy["contributor_records_json_status"] = "known"
    if len(legacy) != int(expected["historical_difference_count"]):
        raise ValueError("legacy replay-difference closure drift")

    multi = exact_replay[exact_replay["raw_file_count"].gt(1)].copy()
    multi["is_multi_cruise"] = multi["official_cruise_count"].gt(1)
    multi["frozen_aggregation_conflict_membership"] = multi["canonical_cell_id"].isin(conflict_ids)
    multi = add_status_pairs(
        multi[[
            column for column in multi.columns if not column.endswith("_status")
        ]],
        {"canonical_cell_id"},
        {
            "official_cruise_count": "verified_from_source_metadata",
            "exact_cruise_balanced_median_m": lambda frame: np.where(
                frame["exact_cruise_balanced_median_m"].notna(), "known", "not_recoverable"
            ),
            "between_cruise_nmad_m": lambda frame: np.where(
                frame["between_cruise_nmad_m"].notna(), "known", "not_recoverable"
            ),
            "cruise_balanced_minus_frozen_m": lambda frame: np.where(
                frame["cruise_balanced_minus_frozen_m"].notna(), "known", "not_recoverable"
            ),
            "exact_pooled_point_nmad_m": lambda frame: np.where(
                frame["exact_pooled_point_nmad_m"].notna(), "known", "not_recoverable"
            ),
            "between_file_nmad_m": lambda frame: np.where(
                frame["between_file_nmad_m"].notna(), "known", "not_recoverable"
            ),
        },
    )
    if len(multi) != int(expected["multi_file_count"]):
        raise ValueError("multi-file cell closure drift")
    if int(multi["is_multi_cruise"].sum()) != int(expected["multi_cruise_count"]):
        raise ValueError("multi-cruise cell closure drift")
    if int(multi["frozen_aggregation_conflict_membership"].sum()) != int(expected["aggregation_conflict_count"]):
        raise ValueError("nine-cell aggregation-conflict membership drift")
    details = file_cells[file_cells["canonical_cell_id"].isin(set(multi["canonical_cell_id"]))].copy()
    return (
        legacy.sort_values("canonical_cell_id").reset_index(drop=True),
        multi.sort_values("canonical_cell_id").reset_index(drop=True),
        details.sort_values(["canonical_cell_id", "file_id"]).reset_index(drop=True),
    )


def _compare_frames(
    baseline: pd.DataFrame,
    candidate: pd.DataFrame,
    sort_columns: list[str],
    value_columns: list[str],
) -> tuple[int, float]:
    left = baseline[value_columns].sort_values(sort_columns).reset_index(drop=True)
    right = candidate[value_columns].sort_values(sort_columns).reset_index(drop=True)
    if len(left) != len(right):
        return abs(len(left) - len(right)), float("inf")
    mismatches = 0
    max_abs = 0.0
    for column in value_columns:
        if pd.api.types.is_numeric_dtype(left[column]):
            left_values = left[column].to_numpy(dtype=np.float64)
            right_values = right[column].to_numpy(dtype=np.float64)
            equal = (left_values == right_values) | (np.isnan(left_values) & np.isnan(right_values))
            mismatches += int((~equal).sum())
            finite = np.isfinite(left_values) & np.isfinite(right_values)
            if finite.any():
                max_abs = max(max_abs, float(np.max(np.abs(left_values[finite] - right_values[finite]))))
        else:
            equal = left[column].fillna("<NULL>").astype(str).eq(right[column].fillna("<NULL>").astype(str))
            mismatches += int((~equal).sum())
    return mismatches, max_abs


def build_variant_products(
    points: pd.DataFrame,
    vertical_lookup: dict[str, dict[str, str]],
    history: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    file_cells = build_file_cell_contributors(points, vertical_lookup)
    cruise_cells = build_cell_cruise_contributors(points, vertical_lookup, file_cells)
    replay = build_exact_cell_replay(points, file_cells, cruise_cells, history)
    return file_cells, cruise_cells, replay


def build_invariance(
    config: dict[str, Any],
    metadata: pd.DataFrame,
    jam_targets: set[str],
    mrar_targets: set[str],
    official: dict[str, dict[str, Any]],
    vertical_lookup: dict[str, dict[str, str]],
    history: pd.DataFrame,
    baseline_points: pd.DataFrame,
    baseline_file_cells: pd.DataFrame,
    baseline_cruise_cells: pd.DataFrame,
    baseline_replay: pd.DataFrame,
) -> pd.DataFrame:
    point_columns = RAW_POINT_VALUE_COLUMNS
    file_columns = [
        "canonical_cell_id", "file_id", "raw_point_count", "exact_median_m",
        "within_file_nmad_m", "min_depth_m", "max_depth_m", "depth_range_m",
        "raw_row_ranges_json",
    ]
    replay_columns = [
        "canonical_cell_id", "raw_point_count", "raw_file_count", "official_cruise_count",
        "exact_pooled_point_median_m", "exact_file_balanced_median_m",
        "exact_cruise_balanced_median_m", "between_file_nmad_m", "between_cruise_nmad_m",
    ]
    baseline_digests = {
        "raw_point": canonical_frame_digest(baseline_points, ["canonical_cell_id", "file_id", "raw_row_id"], point_columns),
        "file_cell": canonical_frame_digest(baseline_file_cells, ["canonical_cell_id", "file_id"], file_columns),
        "cell_replay": canonical_frame_digest(baseline_replay, ["canonical_cell_id"], replay_columns),
    }
    rows = []
    for index, variant in enumerate(config["execution_variants"]):
        if index == 0:
            points = baseline_points
            file_cells = baseline_file_cells
            cruise_cells = baseline_cruise_cells
            replay = baseline_replay
        else:
            points, _ = scan_variant(metadata, jam_targets, mrar_targets, official, variant)
            file_cells, cruise_cells, replay = build_variant_products(points, vertical_lookup, history)
        digests = {
            "raw_point": canonical_frame_digest(points, ["canonical_cell_id", "file_id", "raw_row_id"], point_columns),
            "file_cell": canonical_frame_digest(file_cells, ["canonical_cell_id", "file_id"], file_columns),
            "cell_replay": canonical_frame_digest(replay, ["canonical_cell_id"], replay_columns),
        }
        point_mismatch = 0 if digests["raw_point"] == baseline_digests["raw_point"] else len(points)
        file_mismatch, file_max = _compare_frames(
            baseline_file_cells, file_cells, ["canonical_cell_id", "file_id"], file_columns
        )
        replay_mismatch, replay_max = _compare_frames(
            baseline_replay, replay, ["canonical_cell_id"], replay_columns
        )
        total_mismatch = point_mismatch + file_mismatch + replay_mismatch
        rows.append({
            "variant_name": str(variant["name"]),
            "batch_rows": int(variant["batch_rows"]),
            "file_order": str(variant["file_order"]),
            "worker_count": int(variant["workers"]),
            "seed": int(variant["seed"]),
            "raw_point_rows": len(points),
            "file_cell_rows": len(file_cells),
            "cell_cruise_rows": len(cruise_cells),
            "cell_replay_rows": len(replay),
            "raw_point_canonical_sha256": digests["raw_point"],
            "file_cell_canonical_sha256": digests["file_cell"],
            "cell_replay_canonical_sha256": digests["cell_replay"],
            "value_mismatch_count": total_mismatch,
            "maximum_absolute_numeric_difference_m": max(file_max, replay_max),
        })
        if total_mismatch != 0 or digests != baseline_digests:
            raise ValueError(f"execution invariance failed for variant {variant['name']}")
        if index > 0:
            del points, file_cells, cruise_cells, replay
            gc.collect()
    return add_status_pairs(pd.DataFrame(rows), {"variant_name"})


def dataframe_schema(frame: pd.DataFrame) -> list[dict[str, str]]:
    return [{"name": str(column), "dtype": str(dtype)} for column, dtype in frame.dtypes.items()]


def atomic_write_parquet(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False, compression="snappy")
    os.replace(temporary, path)


def atomic_write_tsv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, sep="\t", index=False)
    os.replace(temporary, path)


def atomic_write_text(text: str, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def render_report(
    run_id: str,
    frames: dict[str, pd.DataFrame],
    status_counts: pd.DataFrame,
) -> str:
    replay = frames["exact_cell_replay.parquet"]
    multi = frames["multi_file_cell_summary.parquet"]
    aggregate = status_counts.groupby("factual_status")["count"].sum().to_dict()
    return "\n".join([
        "# SCS MRAR/JAMSTEC lineage supplement and exact replay v2",
        "",
        f"Run ID: `{run_id}`",
        "",
        "This package is lineage and exact-replay evidence only. It does not correct,",
        "remove, weight, or assign a data-use role to any sounding or cell.",
        "",
        "## Closure",
        "",
        f"- frozen cells: {len(replay):,}",
        f"- retained raw point contributions: {len(frames['raw_point_contributions.parquet']):,}",
        f"- exact file-cell contributors: {len(frames['file_cell_contributors.parquet']):,}",
        f"- cell x contributor-group rows: {len(frames['cell_official_cruise_contributors.parquet']):,}",
        f"- historical replay differences: {len(frames['legacy_52_replay_differences.parquet']):,}",
        f"- multi-file cells: {len(multi):,}",
        f"- multi-cruise cells: {int(multi['is_multi_cruise'].sum()):,}",
        f"- frozen aggregation-conflict members: {int(multi['frozen_aggregation_conflict_membership'].sum()):,}",
        "",
        "## Identity and field ceilings",
        "",
        "MRAR identity is not recoverable and source independence is unknown. The",
        "bounded RIAM/Uehara Tscs hypothesis check found related SCS bathymetry research",
        "but no direct artifact link. All 58 JAMSTEC contributors are headerless",
        "three-column processed bathymetry files; chronological/ping order and row-level",
        "time, line, navigation record, beam, heading, sonar index, and quality flags are",
        "not present in the files.",
        "",
        "## Five-level factual status totals",
        "",
        *[f"- `{status}`: {int(aggregate.get(status, 0)):,}" for status in FIELD_STATUSES],
        "",
        "Pooled-point, exact file-balanced, and exact official-cruise-balanced medians",
        "remain diagnostic alternatives. No final aggregation estimator is selected.",
        "",
    ])


def write_outputs(
    temp_dir: Path,
    frames: dict[str, pd.DataFrame],
    config: dict[str, Any],
    config_path: Path,
    input_records: dict[str, dict[str, Any]],
    raw_source_records: dict[str, dict[str, Any]],
    run_id: str,
) -> None:
    forbidden_columns = list(config["output_guards"]["forbidden_column_tokens"])
    forbidden_paths = list(config["output_guards"]["forbidden_output_path_tokens"])
    for name, frame in frames.items():
        validate_output_schema(frame, forbidden_columns)
        validate_output_path(Path(name), forbidden_paths)
        if name.endswith(".parquet"):
            atomic_write_parquet(frame, temp_dir / name)
        elif name.endswith(".tsv"):
            atomic_write_tsv(frame, temp_dir / name)
        else:
            raise ValueError(f"unsupported frame output: {name}")
    report = render_report(run_id, frames, frames["factual_status_counts.tsv"])
    atomic_write_text(report, temp_dir / "audit_report.md")

    inventory = []
    for path in sorted(temp_dir.iterdir()):
        if path.name == "audit_manifest.json":
            continue
        if path.suffix == ".parquet":
            parquet = pq.ParquetFile(path)
            rows = int(parquet.metadata.num_rows)
            schema = [{"name": field.name, "type": str(field.type)} for field in parquet.schema_arrow]
        elif path.suffix == ".tsv":
            frame = frames[path.name]
            rows = len(frame)
            schema = dataframe_schema(frame)
        else:
            rows = len(path.read_text(encoding="utf-8").splitlines())
            schema = [{"name": "text_line", "type": "utf8"}]
        inventory.append({
            "path": path.name,
            "absolute_path": str((resolve_repo_path(config["output_root"]) / run_id / path.name).resolve()),
            "rows": rows,
            "schema": schema,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    producer = Path(__file__).resolve()
    verifier = REPO_ROOT / "ncei/code/scs_confirmation/verify_scs_ship_lineage_exact_replay_v2.py"
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scientific_use": "lineage_and_exact_replay_evidence_only",
        "config_path": str(config_path.relative_to(REPO_ROOT)),
        "config_sha256": sha256_file(config_path),
        "command": sys.argv,
        "working_directory": str(Path.cwd()),
        "inputs": input_records,
        "raw_sources": raw_source_records,
        "execution_variants": config["execution_variants"],
        "factual_status_vocabulary": list(FIELD_STATUSES),
        "downstream_model_error_read": False,
        "gebco_or_product_consensus_value_read": False,
        "correction_or_data_role_decision_made": False,
        "software": {
            "producer": {"path": str(producer.relative_to(REPO_ROOT)), "sha256": sha256_file(producer)},
            "verifier": {"path": str(verifier.relative_to(REPO_ROOT)), "sha256": sha256_file(verifier)},
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "pyarrow": __import__("pyarrow").__version__,
        },
        "outputs": inventory,
        "unresolved_downstream_decisions": [
            "final_v2_representative_depth_estimator",
            "MRAR_data_use_given_unknown_independence",
            "multi_cruise_disagreement_policy",
            "whether_source_data_with_time_line_ping_and_datum_can_be_obtained",
        ],
    }
    atomic_write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", temp_dir / "audit_manifest.json")


def prepare(config: dict[str, Any]) -> dict[str, Any]:
    paths, input_records = validate_frozen_files(config)
    lineage, history, vertical, manifest, conflict_ids = load_frozen_tables(paths, config)
    raw_hashes, jam_targets, mrar_targets = extract_raw_expectations(lineage)
    raw_source_records = validate_raw_sources(raw_hashes)
    metadata = discover_jamstec_metadata(lineage, manifest, int(config["expected"]["jamstec_file_count"]))
    official = load_official_metadata(metadata)
    official_cruises = {str(item["cruise_id"]) for item in official.values()}
    if len(official_cruises) != int(config["expected"]["jamstec_official_cruise_count"]):
        raise ValueError("official JAMSTEC cruise closure drift")
    vertical_lookup = vertical.set_index("source_cruise")[["vertical_datum", "vertical_datum_status"]].to_dict("index")
    return {
        "paths": paths,
        "input_records": input_records,
        "lineage": lineage,
        "history": history,
        "vertical_lookup": vertical_lookup,
        "conflict_ids": conflict_ids,
        "raw_source_records": raw_source_records,
        "metadata": metadata,
        "official": official,
        "jam_targets": jam_targets,
        "mrar_targets": mrar_targets,
    }


def estimate(config: dict[str, Any]) -> dict[str, Any]:
    prepared = prepare(config)
    return {
        "status": "estimate_only",
        "cell_count": len(prepared["lineage"]),
        "jamstec_contributor_file_count": len(prepared["metadata"]),
        "official_cruise_count": len({item["cruise_id"] for item in prepared["official"].values()}),
        "raw_source_file_count": len(prepared["raw_source_records"]),
        "execution_variant_count": len(config["execution_variants"]),
        "aggregation_conflict_id_count": len(prepared["conflict_ids"]),
        "output_created": False,
    }


def run_full(config: dict[str, Any], config_path: Path, run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run ID must use UTC YYYYMMDDTHHMMSSZ")
    prepared = prepare(config)
    output_root = resolve_repo_path(config["output_root"])
    final_dir = output_root / run_id
    temp_dir = output_root / f".{run_id}.tmp-{os.getpid()}"
    if final_dir.exists() or temp_dir.exists():
        raise FileExistsError(f"immutable run path already exists: {final_dir}")
    validate_output_path(final_dir.relative_to(REPO_ROOT), config["output_guards"]["forbidden_output_path_tokens"])
    output_root.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir()
    try:
        baseline_variant = config["execution_variants"][0]
        points, scan_stats = scan_variant(
            prepared["metadata"], prepared["jam_targets"], prepared["mrar_targets"],
            prepared["official"], baseline_variant,
        )
        validate_raw_point_closure(points, prepared["lineage"], config["expected"])
        file_cells, cruise_cells, exact_replay = build_variant_products(
            points, prepared["vertical_lookup"], prepared["history"]
        )
        if not np.array_equal(
            exact_replay["exact_file_balanced_median_m"].to_numpy(),
            exact_replay["historical_exact_file_balanced_median_m"].to_numpy(),
            equal_nan=True,
        ):
            raise ValueError("new exact file-balanced replay differs from prior exact replay")
        legacy, multi, multi_details = build_focused_outputs(
            exact_replay, file_cells, prepared["conflict_ids"], config["expected"]
        )
        invariance = build_invariance(
            config, prepared["metadata"], prepared["jam_targets"], prepared["mrar_targets"],
            prepared["official"], prepared["vertical_lookup"], prepared["history"],
            points, file_cells, cruise_cells, exact_replay,
        )
        inventory = build_source_inventory(config, prepared["metadata"], prepared["official"], scan_stats)
        identity = build_mrar_identity_ledger(config)
        capabilities = build_jamstec_capabilities(
            prepared["metadata"], prepared["official"], prepared["vertical_lookup"], scan_stats
        )
        points = points.sort_values(["canonical_cell_id", "file_id", "raw_row_id"], kind="stable").reset_index(drop=True)
        raw_points = add_raw_point_statuses(points)
        status_frames = {
            "source_artifact_inventory.tsv": inventory,
            "mrar_identity_ledger.tsv": identity,
            "jamstec_file_capabilities.tsv": capabilities,
            "raw_point_contributions.parquet": raw_points,
            "file_cell_contributors.parquet": file_cells,
            "cell_official_cruise_contributors.parquet": cruise_cells,
            "exact_cell_replay.parquet": exact_replay,
            "legacy_52_replay_differences.parquet": legacy,
            "multi_file_cell_summary.parquet": multi,
            "multi_file_contributor_details.parquet": multi_details,
            "replay_invariance.tsv": invariance,
        }
        for name, frame in status_frames.items():
            validate_status_pairs(frame, {"canonical_cell_id"} if "canonical_cell_id" in frame else {frame.columns[0]})
        status_counts = build_factual_status_counts(status_frames)
        frames = {**status_frames, "factual_status_counts.tsv": status_counts}
        write_outputs(
            temp_dir, frames, config, config_path, prepared["input_records"],
            prepared["raw_source_records"], run_id,
        )
        os.replace(temp_dir, final_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    return final_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--estimate-only", action="store_true")
    parser.add_argument("--confirm-audit", action="store_true")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    if Path.cwd().resolve() != REPO_ROOT:
        raise SystemExit(f"ERROR: run from repository root: {REPO_ROOT}")
    config_path = resolve_repo_path(args.config).resolve()
    config = load_config(config_path)
    if args.estimate_only:
        if args.run_id or args.confirm_audit:
            raise SystemExit("ERROR: --estimate-only cannot be combined with full-run flags")
        print(json.dumps(estimate(config), indent=2, sort_keys=True))
        return
    if not args.confirm_audit or not args.run_id:
        raise SystemExit("ERROR: full run requires --run-id and --confirm-audit")
    run_dir = run_full(config, config_path, args.run_id)
    print(f"Audit run: {run_dir.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
