#!/usr/bin/env python3
"""
07_aggregate_file_cells_1min.py

Step 04A — Per-file 1-arcmin cell aggregation for the NCEI branches
(singlebeam, multibeam_ncei, regional_mrar).

For each primary or regional bathymetry entry (driven by the Step 03B
supplementary manifest, never by filesystem globbing), read the
corresponding `points_checked/*.parquet`, filter on
`point_check_pass_basic`, bin lon/lat into 1-arcmin cells
(`cell_size = 1/60°`), and aggregate per-(track, cell) statistics.

This step does NOT merge across tracks. Cross-track merge is Step 04B
and is explicitly out of scope here. No A/B/C tiers are defined. No
combined sb+mb+mrar table is produced.

Inputs (read-only):
  - ncei/manifests/bathymetry_entry_manifest_supplementary.parquet (Step 03B; 7,403 x 26)
  - ncei/manifests/intersect_divergence_audit.parquet              (Step 03B; 1,850 rows)
  - ncei/derived/singlebeam/points_checked/<id>__{nc,xyz}.parquet  (primary sb)
  - ncei/derived/multibeam/points_checked/<id>__xyz.parquet        (primary mb)
  - ncei/derived/regional_mrar/points_checked/bathymetry_points.parquet (M.rar)

Branch derivation (NOT a column in the supplementary manifest):
  - `singlebeam`      : use_for_primary_bathymetry & instrument_class_pred == 'singlebeam'  → 5,365
  - `multibeam_ncei`  : use_for_primary_bathymetry & instrument_class_pred == 'multibeam'   → 17
  - `regional_mrar`   : source_priority == 'regional'                                       → 3

Outputs (full mode):
  - ncei/derived/singlebeam/file_cells_1min/<track_id>__<source>.parquet  (5,365 files)
  - ncei/derived/multibeam/file_cells_1min/<track_id>__xyz.parquet        (17 files)
  - ncei/derived/regional_mrar/file_cells_1min/<track_id>.parquet         (3 files)
  - ncei/manifests/file_cells_1min_manifest.parquet
  - ncei/manifests/file_cells_1min_manifest.tsv
  - ncei/docs/step04a_file_cells_1min_report.md
  - ncei/output/logs/07_aggregate_file_cells_1min.log
  - ncei/output/logs/07_aggregate_file_cells_1min_errors.tsv

Outputs (sample/test100): manifest/report/log/errors suffixed with
`_<run-label>`; per-(track, cell) parquets always use canonical filenames
so re-runs simply overwrite under --overwrite.

Cell-id convention (per `.trellis/spec/backend/data-contracts.md` +
`pipeline-design-decisions.md` §4 + JAMSTEC `04a_make_multibeam_file_cells.py`):
  lon_bin = floor((lon + 180) * 60)   # range [0, 21600]
  lat_bin = floor((lat + 90)  * 60)   # range [0, 10800]
  cell_id = f"1min_{lat_bin}_{lon_bin}"
  lon_center = -180 + (lon_bin + 0.5) / 60
  lat_center =  -90 + (lat_bin + 0.5) / 60
The `cell_id` string format is load-bearing: Step 04B + downstream
JAMSTEC validation cells join by `cell_id` exact-match (per
`data-contracts.md` "Cell-id formula MUST match exactly").

Usage:
    python ncei/code/07_aggregate_file_cells_1min.py --help
    python ncei/code/07_aggregate_file_cells_1min.py --run-label sample
    python ncei/code/07_aggregate_file_cells_1min.py --run-label test100 --limit-files 100
    python ncei/code/07_aggregate_file_cells_1min.py --run-label full --confirm-full --overwrite

Always run from repo root (`/mnt/data2/00-Data/ship`) per the project's
"run from repo root" convention.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent          # ncei/
REPO_ROOT = ROOT_DIR.parent           # ship/

MANIFEST_DIR = ROOT_DIR / "manifests"
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"

DERIVED_SB_CHK = ROOT_DIR / "derived" / "singlebeam" / "points_checked"
DERIVED_MB_CHK = ROOT_DIR / "derived" / "multibeam" / "points_checked"
DERIVED_REG_CHK = ROOT_DIR / "derived" / "regional_mrar" / "points_checked"

OUT_SB_DIR = ROOT_DIR / "derived" / "singlebeam" / "file_cells_1min"
OUT_MB_DIR = ROOT_DIR / "derived" / "multibeam" / "file_cells_1min"
OUT_REG_DIR = ROOT_DIR / "derived" / "regional_mrar" / "file_cells_1min"

SUPPLEMENTARY_MANIFEST = MANIFEST_DIR / "bathymetry_entry_manifest_supplementary.parquet"
DIVERGENCE_AUDIT = MANIFEST_DIR / "intersect_divergence_audit.parquet"

VALID_RUN_LABELS = ("sample", "test100", "full")
AGGREGATION_VERSION = "ncei_cells_v0.1.0"

# Per-PRD 1-arcmin = 1/60°.
CELL_SIZE_DEG = 1.0 / 60.0

# Per-branch expected primary/regional file counts (per Step 04 audit doc).
EXPECTED_SINGLEBEAM_FILES = 5_365
EXPECTED_MULTIBEAM_FILES = 17
EXPECTED_REGIONAL_QUADRANTS = 3

# Force a per-track manual-review flag for these explicit tracks.
# `f-10-89-cp` per Step 04 audit doc §1.4 (worst-quality primary track,
# but post-quality-check valid 1,413 points are real bathymetry; flag
# so downstream tier calibration can demote without re-deriving the
# audit signal).
EXPLICIT_REVIEW_TRACK_IDS = frozenset({"f-10-89-cp"})

# Streaming batch size for the M.rar combined parquet (~38M rows/quadrant,
# 113M total). Matches the 05/06 streaming convention.
MRAR_BATCH_SIZE = 500_000

# Canonical output column order. Add-only contract: never remove, never
# rename. Matches the brief verbatim.
OUTPUT_COLUMNS: list[str] = [
    "track_id",
    "source_type",
    "source_completeness",
    "instrument_class_pred",
    "branch",
    "cell_id",
    "lon_bin",
    "lat_bin",
    "lon_center",
    "lat_center",
    "n_points_pass",
    "n_unique_triples",
    "duplicate_ratio",
    "median_depth_m",
    "mean_depth_m",
    "std_depth_m",
    "min_depth_m",
    "max_depth_m",
    "range_depth_m",
    "iqr_depth_m",
    "manual_review_flag",
    "median_depth_m_all_points",
    "median_depth_m_unique_triples",
]

# Top-level manifest column order.
MANIFEST_COLUMNS: list[str] = [
    "track_id",
    "branch",
    "source_type",
    "instrument_class_pred",
    "input_path",
    "output_path",
    "n_cells",
    "n_points_pass_total",
    "n_unique_triples_total",
    "duplicate_ratio_overall",
    "manual_review_flag",
    "runtime_seconds",
    "aggregation_version",
]


# ---------------------------------------------------------------------------
# Paths / atomic writes / logging (mirrors 05/06 conventions)
# ---------------------------------------------------------------------------
def get_output_paths(run_label: str) -> dict[str, Path]:
    suffix = "" if run_label == "full" else f"_{run_label}"
    return {
        "manifest_pq": MANIFEST_DIR / f"file_cells_1min_manifest{suffix}.parquet",
        "manifest_tsv": MANIFEST_DIR / f"file_cells_1min_manifest{suffix}.tsv",
        "report_md": DOCS_DIR / f"step04a_file_cells_1min_report{suffix}.md",
        "log": LOG_DIR / f"07_aggregate_file_cells_1min{suffix}.log",
        "errors_tsv": LOG_DIR / f"07_aggregate_file_cells_1min_errors{suffix}.tsv",
    }


def atomic_write_parquet(df: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    df.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, target)


def atomic_write_tsv(df: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, target)


def atomic_write_text(text: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)


def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ncei_file_cells_1min")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s")
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(levelname)-8s %(message)s"))
    logger.addHandler(ch)
    return logger


# ---------------------------------------------------------------------------
# Branch / output-path derivation
# ---------------------------------------------------------------------------
def derive_branch(row: pd.Series) -> str:
    """Map a manifest row to one of the three Step 04A branches.

    The supplementary manifest does NOT have a `branch` column; routing is
    derived deterministically from `source_priority` + `instrument_class_pred`.
    """
    sp = row["source_priority"]
    if sp == "regional":
        return "regional_mrar"
    if sp == "primary":
        if row["instrument_class_pred"] == "multibeam":
            return "multibeam_ncei"
        return "singlebeam"
    raise ValueError(f"unexpected source_priority {sp!r} for Step 04A workload")


def derive_source_tag(input_path: str) -> str:
    """Extract `nc` / `xyz` source tag from a points_checked filename.

    For M.rar the input path points to the shared
    `bathymetry_points.parquet`; the tag is the empty string (caller
    composes output filenames from track_id only).
    """
    base = Path(input_path).name
    if base.endswith("__nc.parquet"):
        return "nc"
    if base.endswith("__xyz.parquet"):
        return "xyz"
    if base == "bathymetry_points.parquet":
        return ""
    raise ValueError(f"cannot derive source tag from {input_path!r}")


def compose_output_path(branch: str, track_id: str, source_tag: str) -> Path:
    """Build the per-(track, cell) output parquet path."""
    if branch == "singlebeam":
        return OUT_SB_DIR / f"{track_id}__{source_tag}.parquet"
    if branch == "multibeam_ncei":
        # multibeam_ncei comes from xyz only — but parameterize via tag
        # to keep the function single-purpose.
        return OUT_MB_DIR / f"{track_id}__{source_tag}.parquet"
    if branch == "regional_mrar":
        return OUT_REG_DIR / f"{track_id}.parquet"
    raise ValueError(f"unknown branch {branch!r}")


def repo_path(rel_path: str) -> Path:
    """Resolve a repo-root-relative path string to a Path (absolute)."""
    return REPO_ROOT / rel_path


# ---------------------------------------------------------------------------
# Cell aggregation
# ---------------------------------------------------------------------------
# Per `.trellis/spec/backend/pipeline-design-decisions.md` §4 + the
# `data-contracts.md` File-cell table contract:
#
#   lon_bin = floor((lon + 180) / cell_deg)   → range [0, 21600]
#   lat_bin = floor((lat + 90)  / cell_deg)   → range [0, 10800]
#   cell_id = f"1min_{lat_bin}_{lon_bin}"
#   lon_center = -180 + (lon_bin + 0.5) * cell_deg
#   lat_center =  -90 + (lat_bin + 0.5) * cell_deg
#
# JAMSTEC `jamstec/multibeam/code/04a_make_multibeam_file_cells.py`
# follows the same convention so the NCEI outputs remain string-joinable
# with the existing `primary_ship_validation_cells_1min` parquet
# (`ncei/docs/step04_aggregation_design_audit.md` §4.1 explicit note).
#
# Integer cell-key packing: both bins are already non-negative; multiply
# lat by the lon bin span (21,601 to leave room for the +180° endpoint
# rounding edge) and add lon. Round-trips losslessly.
_LON_BIN_SPAN = 21_601  # 360 * 60 + 1 (allow inclusive upper bound)


def _encode_cell_key(lon_bin: np.ndarray, lat_bin: np.ndarray) -> np.ndarray:
    return lat_bin.astype(np.int64) * _LON_BIN_SPAN + lon_bin.astype(np.int64)


def _decode_cell_key(key: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lat_bin = (key // _LON_BIN_SPAN).astype(np.int64)
    lon_bin = (key % _LON_BIN_SPAN).astype(np.int64)
    return lon_bin, lat_bin


def aggregate_points(points: pd.DataFrame) -> pd.DataFrame:
    """Bin lon/lat into 1-arcmin cells and aggregate per cell.

    Input must already be filtered to pass-basic rows and contain
    columns lon, lat, depth_m_positive_down. Returns a DataFrame with
    `cell_id` (string) plus per-cell stats.

    Performance: keyed on a packed int64 `cell_key` rather than the
    string `cell_id` until the very end. This matters at the M.rar
    scale (~38M rows / ~9M cells per quadrant) where a string-keyed
    pandas groupby is ~2 orders of magnitude slower than an
    integer-keyed one (the limiting factor for a same-mount run is
    cell_id formatting, not the underlying aggregation).

    Duplicate-triple counting follows the same convention as
    `06_supplementary_quality_check.py` Check B (verbatim):
    pandas `DataFrame.duplicated(keep='first')` over the raw
    `(lon, lat, depth_m_positive_down)` triple with exact float
    equality — no rounding, no snapping. Per-cell scoping is achieved
    by including `cell_key` as the leading column of the dedup key so
    triples in different cells are counted independently.
    """
    empty_cols = [
        "cell_id",
        "lon_bin",
        "lat_bin",
        "lon_center",
        "lat_center",
        "n_points_pass",
        "n_unique_triples",
        "duplicate_ratio",
        "median_depth_m",
        "mean_depth_m",
        "std_depth_m",
        "min_depth_m",
        "max_depth_m",
        "range_depth_m",
        "iqr_depth_m",
        "median_depth_m_all_points",
        "median_depth_m_unique_triples",
    ]
    if points.empty:
        return pd.DataFrame(columns=empty_cols)

    lon = points["lon"].to_numpy(dtype=np.float64)
    lat = points["lat"].to_numpy(dtype=np.float64)
    depth = points["depth_m_positive_down"].to_numpy(dtype=np.float64)

    # ----- 1-arcmin binning (spec-canonical: +180/+90 offset, non-negative) -----
    # The points have already passed Step 03A's valid_lon/valid_lat
    # checks; this is just deterministic binning.
    lon_bin = np.floor((lon + 180.0) * 60.0).astype(np.int64)
    lat_bin = np.floor((lat + 90.0) * 60.0).astype(np.int64)
    cell_key = _encode_cell_key(lon_bin, lat_bin)

    # ----- Vectorized depth stats per cell, keyed by int cell_key -----
    base_df = pd.DataFrame(
        {"cell_key": cell_key, "depth": depth}
    )
    g_basic = base_df.groupby("cell_key", sort=False)["depth"]
    stats = g_basic.agg(
        n_points_pass="size",
        median_depth_m="median",
        mean_depth_m="mean",
        std_depth_m=lambda s: s.std(ddof=1) if len(s) > 1 else float("nan"),
        min_depth_m="min",
        max_depth_m="max",
    )
    # Quantile in one pass; pandas returns a MultiIndex (cell_key, q).
    qres = g_basic.quantile([0.25, 0.75]).unstack(level=-1)
    qres.columns = ["q25_depth_m", "q75_depth_m"]
    iqr = qres["q75_depth_m"] - qres["q25_depth_m"]

    # ----- Per-cell duplicate-triple counting (single pass) -----
    # Per-cell scoping via cell_key in the dedup key: identical
    # (lon, lat, depth) in two different cells stay as separate unique
    # triples; only an exact repeat within the same cell counts as a
    # duplicate.
    triples = pd.DataFrame(
        {"cell_key": cell_key, "lon": lon, "lat": lat, "depth": depth}
    )
    dup_mask = triples.duplicated(
        subset=["cell_key", "lon", "lat", "depth"], keep="first"
    )
    unique_df = triples.loc[~dup_mask]
    n_unique_per_cell = unique_df.groupby("cell_key", sort=False).size()
    median_unique_per_cell = (
        unique_df.groupby("cell_key", sort=False)["depth"].median()
    )

    # ----- Assemble per-cell row table -----
    cell_keys = stats.index.to_numpy(dtype=np.int64)
    n_points_pass = stats["n_points_pass"].to_numpy(dtype=np.int64)
    n_unique = (
        n_unique_per_cell.reindex(stats.index).fillna(0).to_numpy(dtype=np.int64)
    )
    median_unique = (
        median_unique_per_cell.reindex(stats.index).to_numpy(dtype=np.float64)
    )

    lon_bin_g, lat_bin_g = _decode_cell_key(cell_keys)
    median_d = stats["median_depth_m"].to_numpy(dtype=np.float64)
    out = pd.DataFrame(
        {
            "cell_key": cell_keys,
            "lon_bin": lon_bin_g,
            "lat_bin": lat_bin_g,
            "lon_center": -180.0 + (lon_bin_g + 0.5) / 60.0,
            "lat_center": -90.0 + (lat_bin_g + 0.5) / 60.0,
            "n_points_pass": n_points_pass,
            "n_unique_triples": n_unique,
            "duplicate_ratio": np.where(
                n_points_pass > 0, 1.0 - n_unique / n_points_pass, 0.0
            ),
            "median_depth_m": median_d,
            "mean_depth_m": stats["mean_depth_m"].to_numpy(dtype=np.float64),
            "std_depth_m": stats["std_depth_m"].to_numpy(dtype=np.float64),
            "min_depth_m": stats["min_depth_m"].to_numpy(dtype=np.float64),
            "max_depth_m": stats["max_depth_m"].to_numpy(dtype=np.float64),
            "iqr_depth_m": iqr.reindex(stats.index).to_numpy(dtype=np.float64),
            "median_depth_m_all_points": median_d,
            "median_depth_m_unique_triples": median_unique,
        }
    )
    out["range_depth_m"] = out["max_depth_m"] - out["min_depth_m"]

    # Compose the string cell_id once on the cell-level table (NOT on the
    # 38M-row M.rar input). Format: f"1min_{lat_bin}_{lon_bin}" per
    # `data-contracts.md` (cell-id formula MUST match exactly so Step 04b
    # / downstream JAMSTEC joins succeed).
    out["cell_id"] = (
        "1min_"
        + out["lat_bin"].astype(str)
        + "_"
        + out["lon_bin"].astype(str)
    )

    # Sort by cell_id string for deterministic file ordering.
    out = out.drop(columns=["cell_key"]).sort_values("cell_id").reset_index(drop=True)
    # Reorder to canonical preview order; downstream `attach_constant_cols`
    # will pull only OUTPUT_COLUMNS in the contract order.
    return out[
        [
            "cell_id",
            "lon_bin",
            "lat_bin",
            "lon_center",
            "lat_center",
            "n_points_pass",
            "n_unique_triples",
            "duplicate_ratio",
            "median_depth_m",
            "mean_depth_m",
            "std_depth_m",
            "min_depth_m",
            "max_depth_m",
            "range_depth_m",
            "iqr_depth_m",
            "median_depth_m_all_points",
            "median_depth_m_unique_triples",
        ]
    ]


def attach_constant_cols(
    cell_df: pd.DataFrame,
    *,
    track_id: str,
    source_type: str,
    source_completeness: str,
    instrument_class_pred: str,
    branch: str,
    manual_review_flag: bool,
) -> pd.DataFrame:
    """Add the constant identification columns and order to the brief schema."""
    df = cell_df.copy()
    df["track_id"] = str(track_id)
    df["source_type"] = str(source_type)
    df["source_completeness"] = str(source_completeness)
    df["instrument_class_pred"] = str(instrument_class_pred)
    df["branch"] = str(branch)
    df["manual_review_flag"] = bool(manual_review_flag)

    # Reorder to match OUTPUT_COLUMNS.
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"missing required output column: {col}")
    df = df[OUTPUT_COLUMNS]
    return df


# ---------------------------------------------------------------------------
# Per-input drivers (singlebeam / multibeam_ncei = per-track; regional_mrar = per-quadrant)
# ---------------------------------------------------------------------------
def aggregate_track_file(
    *,
    input_path: Path,
    output_path: Path,
    track_id: str,
    source_type: str,
    source_completeness: str,
    instrument_class_pred: str,
    branch: str,
    manual_review_flag: bool,
    overwrite: bool,
) -> dict:
    """Aggregate one per-track points_checked parquet (sb/mb branches)."""
    if not input_path.exists():
        raise FileNotFoundError(f"input parquet not found: {input_path}")
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"output exists; pass --overwrite to replace: {output_path}"
        )

    start = datetime.now()
    df = pd.read_parquet(
        input_path,
        columns=[
            "lon",
            "lat",
            "depth_m_positive_down",
            "point_check_pass_basic",
        ],
    )
    pass_mask = df["point_check_pass_basic"].to_numpy(dtype=bool)
    valid = df.loc[pass_mask, ["lon", "lat", "depth_m_positive_down"]]

    cell_df = aggregate_points(valid)
    out_df = attach_constant_cols(
        cell_df,
        track_id=track_id,
        source_type=source_type,
        source_completeness=source_completeness,
        instrument_class_pred=instrument_class_pred,
        branch=branch,
        manual_review_flag=manual_review_flag,
    )
    atomic_write_parquet(out_df, output_path)

    elapsed = (datetime.now() - start).total_seconds()
    n_cells = int(len(out_df))
    n_points_total = int(out_df["n_points_pass"].sum()) if n_cells else 0
    n_unique_total = int(out_df["n_unique_triples"].sum()) if n_cells else 0
    overall_dup = (
        0.0
        if n_points_total == 0
        else 1.0 - n_unique_total / n_points_total
    )
    return {
        "track_id": track_id,
        "branch": branch,
        "source_type": source_type,
        "instrument_class_pred": instrument_class_pred,
        "input_path": str(input_path.relative_to(REPO_ROOT)),
        "output_path": str(output_path.relative_to(REPO_ROOT)),
        "n_cells": n_cells,
        "n_points_pass_total": n_points_total,
        "n_unique_triples_total": n_unique_total,
        "duplicate_ratio_overall": float(overall_dup),
        "manual_review_flag": bool(manual_review_flag),
        "runtime_seconds": float(elapsed),
        "aggregation_version": AGGREGATION_VERSION,
    }


def aggregate_mrar(
    *,
    entries: pd.DataFrame,
    overwrite: bool,
    logger: logging.Logger,
) -> list[dict]:
    """Stream the M.rar combined parquet and write ONE output per quadrant.

    Partitioning by the in-parquet `track_id` column (NOT by file). All 3
    quadrant rows in `entries` point at the same `input_path` shared
    parquet; we read it once and split in-memory.

    Approach: accumulate per-quadrant DataFrames of (lon, lat, depth)
    pass-basic rows across all batches, then run the same
    `aggregate_points` per quadrant. M.rar per-quadrant point counts are
    ~25–50M; each (lon, lat, depth) DataFrame is ~600MB at 25M float64 ×
    3 cols, ~1.2GB for the worst 50M quadrant. Acceptable for a
    machine with ~30+GB free (`/mnt/data2` host) and avoids the
    streaming-groupby complexity of multi-batch aggregation that would
    re-sort cell_id keys across batches.
    """
    if entries.empty:
        return []

    # All 3 rows should point at the same Step-03A output parquet
    # (`points_checked/bathymetry_points.parquet`); assert that.
    # Reading from `points_checked/` is mandatory per the Step 04A
    # brief (the PR-F raw `archive/zhoushuai_processed_M/bathymetry_points.parquet`
    # is explicitly rejected — that one has not been point-checked).
    checked_paths = entries["output_path"].astype(str).unique().tolist()
    if len(checked_paths) != 1:
        raise ValueError(
            f"regional_mrar entries do not share a single output_path: {checked_paths}"
        )
    checked_rel = checked_paths[0]
    if "/points_checked/" not in checked_rel:
        raise ValueError(
            f"regional_mrar output_path must point at points_checked/: {checked_rel}"
        )
    input_path = repo_path(checked_rel)
    if not input_path.exists():
        raise FileNotFoundError(f"M.rar points_checked parquet not found: {input_path}")

    # Pre-check each output exists / overwrite.
    quadrant_meta: dict[str, dict] = {}
    for _, e in entries.iterrows():
        tid = str(e["track_id"])
        out_path = compose_output_path("regional_mrar", tid, "")
        if out_path.exists() and not overwrite:
            raise FileExistsError(
                f"output exists; pass --overwrite to replace: {out_path}"
            )
        quadrant_meta[tid] = {
            "entry": e,
            "output_path": out_path,
            "lon": [],
            "lat": [],
            "depth": [],
            "n_total_pass": 0,
        }

    pf = pq.ParquetFile(input_path)
    selected_ids = set(quadrant_meta.keys())
    n_batches = 0
    n_rows_total = 0
    start_stream = datetime.now()
    for batch in pf.iter_batches(
        batch_size=MRAR_BATCH_SIZE,
        columns=[
            "track_id",
            "lon",
            "lat",
            "depth_m_positive_down",
            "point_check_pass_basic",
        ],
    ):
        n_batches += 1
        bdf = batch.to_pandas()
        n_rows_total += len(bdf)
        if bdf.empty:
            continue

        # Apply pass-basic + selected-track filter in pyarrow-friendly order.
        bdf = bdf[bdf["point_check_pass_basic"].astype(bool)]
        if bdf.empty:
            continue
        for tid, sub in bdf.groupby("track_id", sort=False):
            tid_str = str(tid)
            if tid_str not in selected_ids:
                continue
            meta = quadrant_meta[tid_str]
            meta["lon"].append(sub["lon"].to_numpy(dtype=np.float64))
            meta["lat"].append(sub["lat"].to_numpy(dtype=np.float64))
            meta["depth"].append(sub["depth_m_positive_down"].to_numpy(dtype=np.float64))
            meta["n_total_pass"] += int(len(sub))

        if n_batches % 20 == 0 or n_batches == 1:
            logger.info(
                "  mrar batch %d: cum_rows_read=%d", n_batches, n_rows_total
            )
    stream_elapsed = (datetime.now() - start_stream).total_seconds()
    logger.info(
        "  mrar streaming done: %d batches, %d rows, %.1fs",
        n_batches,
        n_rows_total,
        stream_elapsed,
    )

    results: list[dict] = []
    for tid, meta in quadrant_meta.items():
        entry = meta["entry"]
        agg_start = datetime.now()
        if meta["n_total_pass"] == 0:
            valid_df = pd.DataFrame(columns=["lon", "lat", "depth_m_positive_down"])
        else:
            valid_df = pd.DataFrame(
                {
                    "lon": np.concatenate(meta["lon"]),
                    "lat": np.concatenate(meta["lat"]),
                    "depth_m_positive_down": np.concatenate(meta["depth"]),
                }
            )
        # Free the per-batch lists ASAP — the concat made a copy.
        meta["lon"].clear()
        meta["lat"].clear()
        meta["depth"].clear()

        cell_df = aggregate_points(valid_df)
        mrf = derive_manual_review_flag(entry)
        out_df = attach_constant_cols(
            cell_df,
            track_id=tid,
            source_type=str(entry["source_type"]),
            source_completeness=str(entry["source_completeness"]),
            instrument_class_pred=str(entry["instrument_class_pred"]),
            branch="regional_mrar",
            manual_review_flag=mrf,
        )
        atomic_write_parquet(out_df, meta["output_path"])

        n_cells = int(len(out_df))
        n_points_total = int(out_df["n_points_pass"].sum()) if n_cells else 0
        n_unique_total = int(out_df["n_unique_triples"].sum()) if n_cells else 0
        overall_dup = (
            0.0
            if n_points_total == 0
            else 1.0 - n_unique_total / n_points_total
        )
        elapsed = (datetime.now() - agg_start).total_seconds()
        # Charge the streaming wall time to the first quadrant only so
        # the manifest reflects total Step-04A work for the corpus.
        # (Simpler: spread evenly.) We pick "spread evenly" so the
        # manifest stays additive without per-row gymnastics.
        share = stream_elapsed / max(1, len(quadrant_meta))
        results.append(
            {
                "track_id": tid,
                "branch": "regional_mrar",
                "source_type": str(entry["source_type"]),
                "instrument_class_pred": str(entry["instrument_class_pred"]),
                "input_path": str(input_path.relative_to(REPO_ROOT)),
                "output_path": str(meta["output_path"].relative_to(REPO_ROOT)),
                "n_cells": n_cells,
                "n_points_pass_total": n_points_total,
                "n_unique_triples_total": n_unique_total,
                "duplicate_ratio_overall": float(overall_dup),
                "manual_review_flag": bool(mrf),
                "runtime_seconds": float(elapsed + share),
                "aggregation_version": AGGREGATION_VERSION,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Manual-review flag derivation
# ---------------------------------------------------------------------------
def load_bbox_only_divergent_track_ids(audit_path: Path) -> set[str]:
    """The 96 intersect pairs whose only divergence is bbox-shape
    (count-ratio + depth-ratio both within bounds). These warrant manual
    review of the nc-side aggregation but do not invalidate it.
    """
    if not audit_path.exists():
        return set()
    d = pd.read_parquet(audit_path)
    if d.empty:
        return set()
    bbox_only = d[
        (d["bbox_overlap_jaccard"] < 0.5)
        & (d["valid_count_ratio"].between(0.5, 2.0, inclusive="both"))
        & (d["depth_med_ratio"].between(0.5, 2.0, inclusive="both"))
    ]
    return set(bbox_only["track_id"].astype(str).tolist())


# Module-level holders populated in `main()`; helpers read them so that
# `aggregate_track_file` doesn't need to plumb extra state through its
# call sites.
_BBOX_ONLY_REVIEW_IDS: set[str] = set()


def derive_manual_review_flag(row: pd.Series) -> bool:
    """Compute the per-row manual-review flag.

    True when ANY of:
      (a) `depth_anomaly_flag` is true on the row (per Step 03A);
      (b) the track_id is in the 96 bbox-only divergent intersect pairs;
      (c) the track_id is in the explicit review list (currently
          `f-10-89-cp` per Step 04 audit §1.4).
    """
    tid = str(row["track_id"])
    if bool(row.get("depth_anomaly_flag", False)):
        return True
    if tid in _BBOX_ONLY_REVIEW_IDS:
        return True
    if tid in EXPLICIT_REVIEW_TRACK_IDS:
        return True
    return False


# ---------------------------------------------------------------------------
# Workload selection
# ---------------------------------------------------------------------------
def select_workload(
    *,
    supp_df: pd.DataFrame,
    run_label: str,
    limit_files: Optional[int],
    logger: logging.Logger,
) -> pd.DataFrame:
    """Filter the supplementary manifest down to one row per Step 04A
    input.

    Discipline (per Step 04 audit doc §6 guardrail 1):
      - drop the supplementary / skip rows (only primary + regional run)
      - de-duplicate by `output_path` (M.rar has 3 rows sharing 1 path,
        but we keep all 3 because per-quadrant aggregation needs the
        track_id distinction; we drop_duplicates only on actual file
        duplicates within sb/mb)
    """
    work = supp_df[
        supp_df["source_priority"].isin(["primary", "regional"])
    ].copy()

    # For sb/mb branches, output_path uniquely identifies the per-track
    # input file. For regional, the 3 rows intentionally share an
    # input_path (one file, 3 quadrants); keep all 3.
    work_sb_mb = (
        work[work["source_priority"] == "primary"]
        .drop_duplicates("output_path")
        .copy()
    )
    work_reg = work[work["source_priority"] == "regional"].copy()
    work = pd.concat([work_sb_mb, work_reg], ignore_index=True)

    # Derive branch up-front so sample stratification is cheap.
    work["branch"] = work.apply(derive_branch, axis=1)
    work = work.sort_values(["branch", "track_id"]).reset_index(drop=True)

    if run_label == "full":
        return work

    if run_label == "test100":
        if limit_files is None or limit_files <= 0:
            raise ValueError("test100 mode requires --limit-files > 0")
        return work.head(limit_files).reset_index(drop=True)

    # sample mode: 5 per branch, always include all 3 regional quadrants.
    parts: list[pd.DataFrame] = []
    for br, n_take in (
        ("singlebeam", 5),
        ("multibeam_ncei", 5),
        ("regional_mrar", 3),
    ):
        pool = work[work["branch"] == br]
        if len(pool) == 0:
            continue
        k = min(n_take, len(pool))
        # Deterministic selection: take the first k after the canonical sort.
        parts.append(pool.head(k))
    sampled = pd.concat(parts, ignore_index=True)
    logger.info("Sample workload: %d entries", len(sampled))
    return sampled


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def markdown_table(df: pd.DataFrame, max_rows: int = 30) -> list[str]:
    if df is None or len(df) == 0:
        return ["_None_", ""]
    preview = df.head(max_rows).copy()
    cols = list(preview.columns)
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for _, row in preview.iterrows():
        vals = []
        for col in cols:
            val = row[col]
            if isinstance(val, float):
                vals.append(f"{val:.4f}" if np.isfinite(val) else "")
            elif pd.isna(val):
                vals.append("")
            else:
                vals.append(str(val))
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    return lines


def make_report(
    *,
    manifest_df: pd.DataFrame,
    run_label: str,
    elapsed_s: float,
    n_processed: int,
    n_errors: int,
    paths: dict[str, Path],
    workload_expected: dict[str, int],
    workload_observed: dict[str, int],
) -> str:
    lines: list[str] = []
    lines.append("# NCEI Step 04A — Per-file 1-arcmin Cell Aggregation Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Run label: `{run_label}`")
    lines.append(f"Aggregation version: `{AGGREGATION_VERSION}`")
    lines.append(f"Cell size: 1 arc-minute (1/60°)")
    lines.append(f"Elapsed: {elapsed_s:.1f}s")
    lines.append(f"Inputs processed: {n_processed:,}")
    lines.append(f"Errors: {n_errors:,}")
    lines.append("")

    # ---- branch totals ----
    lines.append("## 1. Per-branch totals")
    lines.append("")
    if len(manifest_df):
        roll = (
            manifest_df.groupby("branch")
            .agg(
                files=("track_id", "size"),
                cells=("n_cells", "sum"),
                pass_points=("n_points_pass_total", "sum"),
                unique_triples=("n_unique_triples_total", "sum"),
                avg_runtime_s=("runtime_seconds", "mean"),
                manual_review=("manual_review_flag", "sum"),
            )
            .reset_index()
        )
        roll["overall_dup_ratio"] = np.where(
            roll["pass_points"] > 0,
            1.0 - roll["unique_triples"] / roll["pass_points"],
            0.0,
        )
        lines.extend(markdown_table(roll))
    else:
        lines.append("_No inputs processed._")
        lines.append("")

    # ---- expected vs observed (sample-/test100-aware) ----
    lines.append("## 2. Expected vs observed workload per branch")
    lines.append("")
    rows = []
    for br in ("singlebeam", "multibeam_ncei", "regional_mrar"):
        rows.append(
            {
                "branch": br,
                "expected": workload_expected.get(br, 0),
                "observed": workload_observed.get(br, 0),
                "ok": workload_expected.get(br, 0) == workload_observed.get(br, 0),
            }
        )
    lines.extend(markdown_table(pd.DataFrame(rows)))

    # ---- dup_ratio distribution per branch ----
    lines.append("## 3. duplicate_ratio_overall distribution per branch")
    lines.append("")
    if len(manifest_df):
        rows = []
        for br, sub in manifest_df.groupby("branch"):
            q = sub["duplicate_ratio_overall"].quantile([0.0, 0.25, 0.5, 0.75, 0.9, 0.99, 1.0])
            rows.append(
                {
                    "branch": br,
                    "files": int(len(sub)),
                    "p0": float(q.iloc[0]),
                    "p25": float(q.iloc[1]),
                    "p50": float(q.iloc[2]),
                    "p75": float(q.iloc[3]),
                    "p90": float(q.iloc[4]),
                    "p99": float(q.iloc[5]),
                    "max": float(q.iloc[6]),
                }
            )
        lines.extend(markdown_table(pd.DataFrame(rows)))
    else:
        lines.append("_No inputs processed._")
        lines.append("")

    # ---- manual_review_flag summary ----
    lines.append("## 4. manual_review_flag tracks (informational; not excluded)")
    lines.append("")
    if len(manifest_df):
        flagged = manifest_df[manifest_df["manual_review_flag"]].sort_values(
            ["branch", "track_id"]
        )
        lines.append(f"Total flagged: {len(flagged):,}")
        lines.append("")
        if len(flagged):
            lines.extend(
                markdown_table(
                    flagged[
                        [
                            "track_id",
                            "branch",
                            "source_type",
                            "n_cells",
                            "n_points_pass_total",
                            "duplicate_ratio_overall",
                        ]
                    ]
                )
            )
    else:
        lines.append("_No inputs processed._")
        lines.append("")

    # ---- top dup_ratio cases per branch ----
    lines.append("## 5. Highest duplicate_ratio_overall files per branch (top 10)")
    lines.append("")
    if len(manifest_df):
        for br, sub in manifest_df.groupby("branch"):
            lines.append(f"### {br}")
            lines.append("")
            top = sub.sort_values("duplicate_ratio_overall", ascending=False).head(10)
            lines.extend(
                markdown_table(
                    top[
                        [
                            "track_id",
                            "n_cells",
                            "n_points_pass_total",
                            "n_unique_triples_total",
                            "duplicate_ratio_overall",
                        ]
                    ]
                )
            )

    # ---- output paths ----
    lines.append("## 6. Output paths")
    lines.append("")
    path_rows = [
        {"kind": "manifest (parquet)", "path": str(paths["manifest_pq"].relative_to(REPO_ROOT))},
        {"kind": "manifest (tsv)", "path": str(paths["manifest_tsv"].relative_to(REPO_ROOT))},
        {"kind": "report (this file)", "path": str(paths["report_md"].relative_to(REPO_ROOT))},
        {"kind": "singlebeam file_cells dir", "path": str(OUT_SB_DIR.relative_to(REPO_ROOT))},
        {"kind": "multibeam_ncei file_cells dir", "path": str(OUT_MB_DIR.relative_to(REPO_ROOT))},
        {"kind": "regional_mrar file_cells dir", "path": str(OUT_REG_DIR.relative_to(REPO_ROOT))},
    ]
    lines.extend(markdown_table(pd.DataFrame(path_rows)))

    # ---- cross-link ----
    lines.append("## 7. References")
    lines.append("")
    lines.append("- Design audit: `ncei/docs/step04_aggregation_design_audit.md`")
    lines.append("- Step 03A output: `ncei/manifests/bathymetry_entry_manifest.parquet`")
    lines.append("- Step 03B supplement: `ncei/manifests/bathymetry_entry_manifest_supplementary.parquet`")
    lines.append(
        "- Duplicate-triple convention: `pd.DataFrame({'lon','lat','depth'}).duplicated(keep='first')` "
        "with exact float equality — same as `06_supplementary_quality_check.py` Check B."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Step 04A — Per-file 1-arcmin cell aggregation for NCEI "
            "singlebeam, multibeam_ncei, and regional_mrar branches. "
            "Run from repo root (/mnt/data2/00-Data/ship)."
        )
    )
    parser.add_argument("--run-label", choices=VALID_RUN_LABELS, default="sample")
    parser.add_argument(
        "--limit-files",
        type=int,
        default=None,
        help="First N work-eligible entries (after canonical sort) to process "
        "(required for test100 mode; otherwise ignored)",
    )
    parser.add_argument(
        "--confirm-full",
        action="store_true",
        help="Required when --run-label=full",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing per-(track, cell) outputs + manifest + report",
    )
    parser.add_argument(
        "--supplementary-manifest",
        type=Path,
        default=SUPPLEMENTARY_MANIFEST,
        help="Path to bathymetry_entry_manifest_supplementary.parquet",
    )
    parser.add_argument(
        "--divergence-audit",
        type=Path,
        default=DIVERGENCE_AUDIT,
        help="Path to intersect_divergence_audit.parquet (for bbox-only review tracks)",
    )
    args = parser.parse_args()

    paths = get_output_paths(args.run_label)
    logger = setup_logging(paths["log"])
    t0 = datetime.now()

    logger.info("=" * 60)
    logger.info("07_aggregate_file_cells_1min.py START")
    logger.info("Args: %s", vars(args))
    logger.info("Aggregation version: %s", AGGREGATION_VERSION)

    # Validate input manifests.
    if not args.supplementary_manifest.exists():
        logger.error("ABORTED: missing supplementary manifest %s", args.supplementary_manifest)
        return 2
    if not args.divergence_audit.exists():
        logger.warning(
            "intersect_divergence_audit.parquet not found at %s — bbox-only "
            "review tracks will be empty (only depth_anomaly_flag + "
            "explicit list will trigger manual_review_flag)",
            args.divergence_audit,
        )

    supp_df = pd.read_parquet(args.supplementary_manifest)
    logger.info("Loaded supplementary manifest: %d rows", len(supp_df))

    # Populate module-level state for manual_review_flag derivation.
    global _BBOX_ONLY_REVIEW_IDS
    _BBOX_ONLY_REVIEW_IDS = load_bbox_only_divergent_track_ids(args.divergence_audit)
    logger.info(
        "Loaded %d bbox-only divergent intersect track_ids for review-flag derivation",
        len(_BBOX_ONLY_REVIEW_IDS),
    )

    # Run-label gating.
    if args.run_label == "full" and not args.confirm_full:
        logger.error("ABORTED: --run-label=full requires --confirm-full")
        return 2
    if args.run_label == "test100" and (args.limit_files is None or args.limit_files <= 0):
        logger.error("ABORTED: test100 mode requires --limit-files > 0")
        return 2

    # Select work.
    work = select_workload(
        supp_df=supp_df,
        run_label=args.run_label,
        limit_files=args.limit_files,
        logger=logger,
    )
    workload_observed = work["branch"].value_counts().to_dict()
    logger.info("Workload (post-filter): %d entries; per-branch: %s", len(work), workload_observed)

    # Assert full-mode candidate counts match the audit doc's expected
    # breakdown — this is the loud-fail guardrail the brief asks for.
    if args.run_label == "full":
        if workload_observed.get("singlebeam", 0) != EXPECTED_SINGLEBEAM_FILES:
            logger.error(
                "ABORTED: full-mode singlebeam expected %d; got %d",
                EXPECTED_SINGLEBEAM_FILES,
                workload_observed.get("singlebeam", 0),
            )
            return 3
        if workload_observed.get("multibeam_ncei", 0) != EXPECTED_MULTIBEAM_FILES:
            logger.error(
                "ABORTED: full-mode multibeam_ncei expected %d; got %d",
                EXPECTED_MULTIBEAM_FILES,
                workload_observed.get("multibeam_ncei", 0),
            )
            return 3
        if workload_observed.get("regional_mrar", 0) != EXPECTED_REGIONAL_QUADRANTS:
            logger.error(
                "ABORTED: full-mode regional_mrar expected %d; got %d",
                EXPECTED_REGIONAL_QUADRANTS,
                workload_observed.get("regional_mrar", 0),
            )
            return 3

    # Output-exists gate at the top-level outputs (per-track outputs are
    # gated individually inside the per-input functions).
    top_outputs = [paths["manifest_pq"], paths["manifest_tsv"], paths["report_md"]]
    if not args.overwrite:
        existing = [p for p in top_outputs if p.exists()]
        if existing:
            logger.error(
                "ABORTED: outputs exist; use --overwrite. Existing: %s", existing
            )
            return 2

    # Ensure per-branch output dirs exist before we start processing.
    for d in (OUT_SB_DIR, OUT_MB_DIR, OUT_REG_DIR):
        d.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[dict] = []
    errors: list[dict] = []

    # ---- Per-track sb/mb work first (cheap, parallelizable per file) ----
    # Per Step 04A brief: read from `points_checked/*.parquet`, never
    # from `points_raw/`. In the supplementary manifest, that path lives
    # in the `output_path` column (Step 03A's output = Step 04A's input).
    # The `input_path` column is Step 03A's *raw* input and is rejected
    # by design (would skip the per-point quality filter).
    track_work = work[work["branch"].isin(["singlebeam", "multibeam_ncei"])].reset_index(drop=True)
    n_tracks = len(track_work)
    logger.info("Per-track aggregation: %d entries", n_tracks)

    for i, (_, row) in enumerate(track_work.iterrows()):
        track_id = str(row["track_id"])
        checked_rel = str(row["output_path"]) if pd.notna(row["output_path"]) else ""
        if not checked_rel:
            errors.append(
                {
                    "track_id": track_id,
                    "branch": row["branch"],
                    "error": "missing output_path (Step 03A points_checked path)",
                }
            )
            continue
        if "/points_raw/" in checked_rel:
            errors.append(
                {
                    "track_id": track_id,
                    "branch": row["branch"],
                    "error": f"refuses to read points_raw: {checked_rel}",
                }
            )
            continue
        checked_abs = repo_path(checked_rel)
        try:
            source_tag = derive_source_tag(checked_rel)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "track_id": track_id,
                    "branch": row["branch"],
                    "error": f"source_tag: {exc!r}",
                }
            )
            continue

        out_path = compose_output_path(row["branch"], track_id, source_tag)
        mrf = derive_manual_review_flag(row)

        if i == 0 or (i + 1) % 200 == 0 or (i + 1) == n_tracks:
            logger.info(
                "Per-track %d/%d: %s [%s] mrf=%s",
                i + 1,
                n_tracks,
                track_id,
                row["branch"],
                mrf,
            )
        try:
            res = aggregate_track_file(
                input_path=checked_abs,
                output_path=out_path,
                track_id=track_id,
                source_type=str(row["source_type"]),
                source_completeness=str(row["source_completeness"]),
                instrument_class_pred=str(row["instrument_class_pred"]),
                branch=str(row["branch"]),
                manual_review_flag=mrf,
                overwrite=args.overwrite,
            )
            manifest_rows.append(res)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error aggregating %s", track_id)
            errors.append(
                {
                    "track_id": track_id,
                    "branch": row["branch"],
                    "input_path": checked_rel,
                    "error": repr(exc),
                }
            )

    # ---- Regional M.rar: one streaming pass over the shared parquet ----
    mrar_work = work[work["branch"] == "regional_mrar"].reset_index(drop=True)
    if len(mrar_work):
        logger.info("Regional M.rar aggregation: %d quadrants", len(mrar_work))
        try:
            mrar_results = aggregate_mrar(
                entries=mrar_work,
                overwrite=args.overwrite,
                logger=logger,
            )
            manifest_rows.extend(mrar_results)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Regional M.rar aggregation failed")
            errors.append(
                {
                    "track_id": "<mrar_combined>",
                    "branch": "regional_mrar",
                    "error": repr(exc),
                }
            )

    # ---- Build manifest DF + run cross-checks ----
    if manifest_rows:
        manifest_df = pd.DataFrame(manifest_rows)
        for col in MANIFEST_COLUMNS:
            if col not in manifest_df.columns:
                manifest_df[col] = pd.NA
        manifest_df = manifest_df[MANIFEST_COLUMNS]
        manifest_df = manifest_df.sort_values(["branch", "track_id"]).reset_index(drop=True)
    else:
        manifest_df = pd.DataFrame(columns=MANIFEST_COLUMNS)

    # ---- Self-report sanity checks (per brief) ----
    # 1. Per-branch candidate count matches expected (full mode).
    workload_expected = {
        "singlebeam": EXPECTED_SINGLEBEAM_FILES if args.run_label == "full" else workload_observed.get("singlebeam", 0),
        "multibeam_ncei": EXPECTED_MULTIBEAM_FILES if args.run_label == "full" else workload_observed.get("multibeam_ncei", 0),
        "regional_mrar": EXPECTED_REGIONAL_QUADRANTS if args.run_label == "full" else workload_observed.get("regional_mrar", 0),
    }
    if args.run_label == "full":
        for br, expected in workload_expected.items():
            observed = workload_observed.get(br, 0)
            if observed != expected:
                logger.error(
                    "Branch count mismatch: %s expected %d, observed %d",
                    br,
                    expected,
                    observed,
                )

    # 2. No intersect xyz leaked into singlebeam output. Output filenames
    # for singlebeam include `__nc.parquet` (1,850 intersect nc-primary)
    # or `__xyz.parquet` (xyz_only). The supplementary 1,850 intersect
    # xyz rows are NEVER fed to Step 04A (filtered by source_priority).
    intersect_xyz_in_sb = manifest_df[
        (manifest_df["branch"] == "singlebeam")
        & (manifest_df["source_type"] == "ncei_xyz")
        & (manifest_df["output_path"].str.endswith("__xyz.parquet"))
        & (
            manifest_df["track_id"].isin(
                supp_df.loc[
                    (supp_df["source_completeness"] == "nc_xyz_intersect")
                    & (supp_df["source_type"] == "ncei_xyz")
                    & (supp_df["source_priority"] == "supplementary"),
                    "track_id",
                ]
            )
        )
    ]
    if len(intersect_xyz_in_sb):
        logger.error(
            "Intersect-xyz leakage into singlebeam: %d outputs", len(intersect_xyz_in_sb)
        )
    logger.info("Intersect-xyz leakage check: 0 violations (expected) — observed=%d",
                len(intersect_xyz_in_sb))

    # 3. multibeam branch: substantial fraction of cells dup_ratio > 0.5.
    mb_manifest = manifest_df[manifest_df["branch"] == "multibeam_ncei"]
    if len(mb_manifest):
        frac_high_dup = float(
            (mb_manifest["duplicate_ratio_overall"] > 0.5).sum() / len(mb_manifest)
        )
        logger.info(
            "Multibeam files with overall_dup_ratio>0.5: %.1f%% (%d of %d)",
            100.0 * frac_high_dup,
            int((mb_manifest["duplicate_ratio_overall"] > 0.5).sum()),
            len(mb_manifest),
        )

    # 4. f-10-89-cp in singlebeam output with manual_review_flag=True.
    f10 = manifest_df[manifest_df["track_id"] == "f-10-89-cp"]
    if len(f10):
        f10_row = f10.iloc[0]
        logger.info(
            "f-10-89-cp: branch=%s, manual_review_flag=%s, n_cells=%d",
            f10_row["branch"],
            bool(f10_row["manual_review_flag"]),
            int(f10_row["n_cells"]),
        )
    elif args.run_label == "full":
        logger.error("f-10-89-cp missing from full-mode singlebeam output")

    elapsed_s = (datetime.now() - t0).total_seconds()

    # ---- Write outputs ----
    atomic_write_parquet(manifest_df, paths["manifest_pq"])
    # TSV: full export for full runs; first 1,000 for partial (matches 05/06 style).
    tsv_df = manifest_df if args.run_label == "full" else manifest_df.head(1000).copy()
    atomic_write_tsv(tsv_df, paths["manifest_tsv"])

    report_text = make_report(
        manifest_df=manifest_df,
        run_label=args.run_label,
        elapsed_s=elapsed_s,
        n_processed=len(manifest_df),
        n_errors=len(errors),
        paths=paths,
        workload_expected=workload_expected,
        workload_observed=workload_observed,
    )
    atomic_write_text(report_text, paths["report_md"])

    atomic_write_tsv(pd.DataFrame(errors), paths["errors_tsv"])

    logger.info("Wrote %s (%d rows)", paths["manifest_pq"], len(manifest_df))
    logger.info("Wrote %s", paths["manifest_tsv"])
    logger.info("Wrote %s", paths["report_md"])
    logger.info("Errors: %d", len(errors))
    logger.info("Elapsed: %.1fs", elapsed_s)
    logger.info("07_aggregate_file_cells_1min.py DONE")

    print(f"Inputs processed: {len(manifest_df):,}")
    print(f"Per-branch processed: {manifest_df['branch'].value_counts().to_dict()}")
    print(f"Errors: {len(errors):,}")
    print(f"Manifest: {paths['manifest_pq']}")
    print(f"Report:   {paths['report_md']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
