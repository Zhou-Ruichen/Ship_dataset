#!/usr/bin/env python3
"""
04a_make_multibeam_file_cells.py

Aggregate QC-passed points into file-level cell statistics.

For each input points_qc parquet file, computes cell-level statistics
at a given resolution (default: 1 arc-minute = 1/60 degree). Only
qc_pass_basic=True rows are used. Each output row represents one
(file_id, cell_id) combination.

Reads:
  - derived/points_qc/*.parquet                        (from 03)
  - manifests/points_qc_manifest.parquet               (from 03)
  - manifests/file_manifest_points_raw.parquet          (from 02a, for metadata)

Writes (full mode, cell-size=1min):
  - derived/file_cells_1min/<file_id>.parquet
  - manifests/file_cells_manifest_1min.parquet + .tsv
  - docs/file_cells_report_1min.md
  - output/logs/04a_make_multibeam_file_cells_full.log
  - output/logs/04a_file_cells_errors_full.tsv

Cell definition:
  1min: cell_deg = 1/60
  lon_bin = floor((lon + 180) / cell_deg)
  lat_bin = floor((lat + 90) / cell_deg)
  cell_id = f"1min_{lat_bin}_{lon_bin}"
  lon_center = -180 + (lon_bin + 0.5) * cell_deg
  lat_center = -90 + (lat_bin + 0.5) * cell_deg

Usage:
    # Sample: 5 random files
    python 04a_make_multibeam_file_cells.py --run-label sample --cell-size 1min --sample-n-files 5 --overwrite

    # Test100
    python 04a_make_multibeam_file_cells.py --run-label test100 --cell-size 1min --limit-files 100 --overwrite

    # Full run
    python 04a_make_multibeam_file_cells.py --run-label full --cell-size 1min --confirm-full --overwrite

    # Estimate only
    python 04a_make_multibeam_file_cells.py --run-label full --cell-size 1min --confirm-full --estimate-only

    # Specific file
    python 04a_make_multibeam_file_cells.py --run-label sample --cell-size 1min --file-id "MR03-K02_bathymetry_dmo::20030527.dat" --overwrite
"""

import argparse
import logging
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent

POINTS_QC_DIR = ROOT_DIR / "derived" / "points_qc"
QC_MANIFEST_PQ = ROOT_DIR / "manifests" / "points_qc_manifest.parquet"
FILE_MANIFEST_PQ = ROOT_DIR / "manifests" / "file_manifest_points_raw.parquet"

LOG_DIR = ROOT_DIR / "output" / "logs"

VALID_RUN_LABELS = ("sample", "test100", "full")
VALID_CELL_SIZES = ("1min",)
DEFAULT_CHUNK_SIZE = 1_000_000

CELL_SIZES = {
    "1min": 1.0 / 60.0,
}


def get_run_paths(run_label: str, cell_size: str):
    derived = ROOT_DIR / "derived"
    manifests = ROOT_DIR / "manifests"
    docs = ROOT_DIR / "docs"
    cs = cell_size
    if run_label == "full":
        return (
            derived / f"file_cells_{cs}",
            manifests / f"file_cells_manifest_{cs}.parquet",
            manifests / f"file_cells_manifest_{cs}.tsv",
            docs / f"file_cells_report_{cs}.md",
        )
    suffix = run_label
    return (
        derived / f"file_cells_{cs}_{suffix}",
        manifests / f"file_cells_manifest_{cs}_{suffix}.parquet",
        manifests / f"file_cells_manifest_{cs}_{suffix}.tsv",
        docs / f"file_cells_report_{cs}_{suffix}.md",
    )


def file_id_to_parquet_name(file_id: str) -> str:
    safe = file_id.replace("::", "__").replace("/", "__")
    if safe.endswith(".dat"):
        safe = safe[:-4]
    return safe + ".parquet"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("file_cells")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s %(message)s"))
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(levelname)-8s %(message)s"))
    logger.addHandler(ch)
    return logger


# ---------------------------------------------------------------------------
# Cell binning
# ---------------------------------------------------------------------------
def compute_cell_bins(lon: np.ndarray, lat: np.ndarray, cell_deg: float):
    lon_bin = np.floor((lon + 180.0) / cell_deg).astype(np.int32)
    lat_bin = np.floor((lat + 90.0) / cell_deg).astype(np.int32)
    return lon_bin, lat_bin


def cell_id_from_bins(lat_bin: np.ndarray, lon_bin: np.ndarray, cell_size: str) -> np.ndarray:
    # Vectorized string construction
    return np.char.add(
        np.char.add(
            np.char.add(f"{cell_size}_", lat_bin.astype(str)),
            "_"
        ),
        lon_bin.astype(str),
    )


def lon_center_from_bin(lon_bin: np.ndarray, cell_deg: float) -> np.ndarray:
    return -180.0 + (lon_bin.astype(np.float64) + 0.5) * cell_deg


def lat_center_from_bin(lat_bin: np.ndarray, cell_deg: float) -> np.ndarray:
    return -90.0 + (lat_bin.astype(np.float64) + 0.5) * cell_deg


# ---------------------------------------------------------------------------
# Aggregate chunk into cell groups
# ---------------------------------------------------------------------------
def aggregate_chunk(
    chunk: pd.DataFrame,
    cell_deg: float,
    cell_size: str,
) -> pd.DataFrame:
    """Aggregate a chunk of qc-passed points into cell-level stats.

    Returns DataFrame with one row per (file_id, cell_id).
    """
    # Filter to qc_pass_basic only
    mask = chunk["qc_pass_basic"] == True  # noqa: E712
    df = chunk.loc[mask].copy()

    if len(df) == 0:
        return pd.DataFrame()

    lon = df["lon"].values
    lat = df["lat"].values
    depth = df["depth_m_positive_down"].values
    elev = df["elev_m"].values

    lon_bin, lat_bin = compute_cell_bins(lon, lat, cell_deg)
    df["lon_bin"] = lon_bin
    df["lat_bin"] = lat_bin
    df["cell_id"] = cell_id_from_bins(lat_bin, lon_bin, cell_size)
    df["lon_center"] = lon_center_from_bin(lon_bin, cell_deg)
    df["lat_center"] = lat_center_from_bin(lat_bin, cell_deg)

    # Count non-null date_raw, time_raw, sonar_idx
    df["has_date"] = df["date_raw"].notna().astype(np.int32)
    df["has_time"] = df["time_raw"].notna().astype(np.int32)
    df["has_sonar"] = df["sonar_idx"].notna().astype(np.int32)

    # Group by cell
    grouped = df.groupby(["cell_id", "lon_bin", "lat_bin", "lon_center", "lat_center"])

    agg = grouped.agg(
        n_points=("depth_m_positive_down", "size"),
        median_depth_m_positive_down=("depth_m_positive_down", "median"),
        mean_depth_m_positive_down=("depth_m_positive_down", "mean"),
        std_depth_m=("depth_m_positive_down", "std"),
        min_depth_m=("depth_m_positive_down", "min"),
        max_depth_m=("depth_m_positive_down", "max"),
        q25_depth_m=("depth_m_positive_down", lambda x: x.quantile(0.25)),
        q75_depth_m=("depth_m_positive_down", lambda x: x.quantile(0.75)),
        mean_elev_m=("elev_m", "mean"),
        n_date_nonnull=("has_date", "sum"),
        n_time_nonnull=("has_time", "sum"),
        n_sonar_idx_nonnull=("has_sonar", "sum"),
    )

    # Reset index to get cell_id, lon_bin, lat_bin, lon_center, lat_center as columns
    agg = agg.reset_index()

    # Derive remaining columns
    agg["median_elev_m"] = -agg["median_depth_m_positive_down"]
    agg["iqr_depth_m"] = agg["q75_depth_m"] - agg["q25_depth_m"]
    agg["cell_size"] = cell_size

    # Fill NaN std (single-point cells)
    agg["std_depth_m"] = agg["std_depth_m"].fillna(0.0)

    return agg


# ---------------------------------------------------------------------------
# Process a single file
# ---------------------------------------------------------------------------
def process_file(
    file_id: str,
    input_path: Path,
    output_dir: Path,
    cell_deg: float,
    cell_size: str,
    chunk_size: int,
    overwrite: bool,
    file_meta: dict,
    logger: logging.Logger,
) -> dict:
    safe_name = file_id_to_parquet_name(file_id)
    out_path = output_dir / safe_name

    if not overwrite and out_path.exists():
        return {
            "file_id": file_id,
            "input_path": str(input_path.relative_to(ROOT_DIR)),
            "output_path": str(out_path.relative_to(ROOT_DIR)),
            "rows_read": -1,
            "rows_used": -1,
            "n_cells": -1,
            "n_points_total": -1,
            "n_points_min": None,
            "n_points_max": None,
            "n_points_mean": None,
            "median_depth_min": None,
            "median_depth_max": None,
            "status": "skipped_exists",
            "notes": "",
        }

    if not input_path.exists():
        return {
            "file_id": file_id,
            "input_path": str(input_path),
            "output_path": "",
            "rows_read": 0, "rows_used": 0, "n_cells": 0,
            "n_points_total": 0, "n_points_min": None, "n_points_max": None,
            "n_points_mean": None, "median_depth_min": None, "median_depth_max": None,
            "status": "error",
            "notes": f"input not found: {input_path}",
        }

    logger.info(f"  Processing: {safe_name}")

    tmp_path = out_path.with_suffix(".parquet.tmp")
    output_dir.mkdir(parents=True, exist_ok=True)

    total_read = 0
    total_used = 0
    all_cell_dfs = []

    try:
        pf = pq.ParquetFile(str(input_path))
        for batch in pf.iter_batches(batch_size=chunk_size):
            chunk_df = batch.to_pandas()
            n_read = len(chunk_df)
            total_read += n_read

            n_pass = int(chunk_df["qc_pass_basic"].sum())
            total_used += n_pass

            if n_pass == 0:
                continue

            cell_df = aggregate_chunk(chunk_df, cell_deg, cell_size)
            if len(cell_df) > 0:
                all_cell_dfs.append(cell_df)

        if len(all_cell_dfs) == 0:
            if tmp_path.exists():
                tmp_path.unlink()
            return {
                "file_id": file_id,
                "input_path": str(input_path.relative_to(ROOT_DIR)),
                "output_path": "",
                "rows_read": total_read, "rows_used": 0, "n_cells": 0,
                "n_points_total": 0, "n_points_min": None, "n_points_max": None,
                "n_points_mean": None, "median_depth_min": None, "median_depth_max": None,
                "status": "empty_output",
                "notes": "no qc_pass_basic rows",
            }

        # Merge all chunk-level cell aggregations
        # Since chunks from the same file may overlap on cells, we need to
        # re-aggregate across chunks. For most stats we need the raw points,
        # but since we already aggregated per-chunk, we combine by summing
        # n_points and computing weighted averages / re-computing medians.
        # However, for correctness with large files that span many cells,
        # we re-group the per-chunk results.
        combined = _combine_chunk_cells(all_cell_dfs, cell_deg, cell_size)

        if len(combined) == 0:
            if tmp_path.exists():
                tmp_path.unlink()
            return {
                "file_id": file_id,
                "input_path": str(input_path.relative_to(ROOT_DIR)),
                "output_path": "",
                "rows_read": total_read, "rows_used": total_used, "n_cells": 0,
                "n_points_total": 0, "n_points_min": None, "n_points_max": None,
                "n_points_mean": None, "median_depth_min": None, "median_depth_max": None,
                "status": "empty_output",
                "notes": "no cells after combining",
            }

        # Add file metadata columns
        combined["file_id"] = file_id
        combined["source_file"] = file_id
        combined["subzip_id"] = file_meta.get("subzip_id", "")
        combined["cruise_id_guess"] = file_meta.get("cruise_id_guess", "")
        combined["track_kind"] = file_meta.get("track_kind", "")
        combined["data_layout"] = file_meta.get("data_layout", "")
        combined["cell_size"] = cell_size
        combined["source_dataset"] = "NCEI_multibeam"

        # Reorder columns to match spec
        output_cols = [
            "cell_id", "cell_size", "lon_bin", "lat_bin", "lon_center", "lat_center",
            "file_id", "source_file", "subzip_id", "cruise_id_guess", "track_kind",
            "data_layout",
            "median_depth_m_positive_down", "median_elev_m",
            "mean_depth_m_positive_down", "mean_elev_m",
            "std_depth_m", "min_depth_m", "max_depth_m",
            "q25_depth_m", "q75_depth_m", "iqr_depth_m",
            "n_points",
            "n_date_nonnull", "n_time_nonnull", "n_sonar_idx_nonnull",
            "source_dataset",
        ]
        combined = combined[output_cols]

        # Write output parquet (atomic)
        combined.to_parquet(tmp_path, index=False)
        os.replace(tmp_path, out_path)

        n_cells = len(combined)
        n_pts = int(combined["n_points"].sum())
        logger.info(
            f"    -> {safe_name}: {n_cells:,} cells, {n_pts:,} points from {total_used:,} used"
        )

        return {
            "file_id": file_id,
            "input_path": str(input_path.relative_to(ROOT_DIR)),
            "output_path": str(out_path.relative_to(ROOT_DIR)),
            "rows_read": total_read,
            "rows_used": total_used,
            "n_cells": n_cells,
            "n_points_total": n_pts,
            "n_points_min": int(combined["n_points"].min()),
            "n_points_max": int(combined["n_points"].max()),
            "n_points_mean": float(combined["n_points"].mean()),
            "median_depth_min": float(combined["median_depth_m_positive_down"].min()),
            "median_depth_max": float(combined["median_depth_m_positive_down"].max()),
            "status": "ok",
            "notes": "",
        }

    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        logger.error(f"  ERROR processing {safe_name}: {e}")
        return {
            "file_id": file_id,
            "input_path": str(input_path.relative_to(ROOT_DIR)) if input_path.exists() else str(input_path),
            "output_path": "",
            "rows_read": total_read,
            "rows_used": total_used,
            "n_cells": 0,
            "n_points_total": 0,
            "n_points_min": None, "n_points_max": None,
            "n_points_mean": None, "median_depth_min": None, "median_depth_max": None,
            "status": "error",
            "notes": str(e),
        }


def _combine_chunk_cells(
    chunk_cells: list[pd.DataFrame],
    cell_deg: float,
    cell_size: str,
) -> pd.DataFrame:
    """Combine per-chunk cell aggregations into a single file-level result.

    Since each chunk is independently aggregated, cells may appear in multiple
    chunks. We re-group by cell_id and combine:
    - n_points: sum
    - median: approximate from weighted mean of chunk medians (acceptable for
      file-level stats; exact would require re-reading all points)
    - mean: weighted average
    - std: approximate from combined statistics
    - min/max: global min/max
    - q25/q75: approximate
    - n_date_nonnull etc: sum

    For this file-level aggregation, we use a pragmatic approach: group the
    already-aggregated chunk results by cell_id and compute combined statistics.
    """
    if len(chunk_cells) == 1:
        return chunk_cells[0]

    combined = pd.concat(chunk_cells, ignore_index=True)

    if len(combined) == 0:
        return combined

    # Group by cell_id (the unique cell identifier)
    grouped = combined.groupby("cell_id")

    result_rows = []
    for cell_id, group in grouped:
        # All rows in group share the same lon_bin, lat_bin, lon_center, lat_center
        row = {
            "cell_id": cell_id,
            "lon_bin": group["lon_bin"].iloc[0],
            "lat_bin": group["lat_bin"].iloc[0],
            "lon_center": group["lon_center"].iloc[0],
            "lat_center": group["lat_center"].iloc[0],
        }

        total_n = int(group["n_points"].sum())
        row["n_points"] = total_n

        # Weighted mean depth
        weights = group["n_points"].values.astype(np.float64)
        w_sum = weights.sum()
        if w_sum > 0:
            row["mean_depth_m_positive_down"] = float(
                (group["mean_depth_m_positive_down"].values * weights).sum() / w_sum
            )
            row["mean_elev_m"] = float(
                (group["mean_elev_m"].values * weights).sum() / w_sum
            )
        else:
            row["mean_depth_m_positive_down"] = float(group["mean_depth_m_positive_down"].iloc[0])
            row["mean_elev_m"] = float(group["mean_elev_m"].iloc[0])

        # Median: weighted median of chunk medians (approximation)
        row["median_depth_m_positive_down"] = float(
            np.average(group["median_depth_m_positive_down"].values, weights=weights)
        )
        row["median_elev_m"] = -row["median_depth_m_positive_down"]

        # Min/max
        row["min_depth_m"] = float(group["min_depth_m"].min())
        row["max_depth_m"] = float(group["max_depth_m"].max())

        # Std: approximate using pooled variance
        # Var pooled = sum(n_i * var_i) / N + between-group variance
        # Simplification: use weighted std of chunk means + within-chunk variance
        if len(group) == 1:
            row["std_depth_m"] = float(group["std_depth_m"].iloc[0]) if total_n > 1 else 0.0
        else:
            # Weighted variance of means
            means = group["mean_depth_m_positive_down"].values
            weighted_mean = row["mean_depth_m_positive_down"]
            var_of_means = float(
                np.sum(weights * (means - weighted_mean) ** 2) / w_sum
            )
            # Average within-chunk variance
            avg_var = float(
                np.sum(weights * group["std_depth_m"].values ** 2) / w_sum
            )
            row["std_depth_m"] = float(np.sqrt(var_of_means + avg_var))

        # q25/q75: approximate as weighted average of chunk q25/q75
        if w_sum > 0:
            row["q25_depth_m"] = float(
                np.average(group["q25_depth_m"].values, weights=weights)
            )
            row["q75_depth_m"] = float(
                np.average(group["q75_depth_m"].values, weights=weights)
            )
        else:
            row["q25_depth_m"] = float(group["q25_depth_m"].iloc[0])
            row["q75_depth_m"] = float(group["q75_depth_m"].iloc[0])
        row["iqr_depth_m"] = row["q75_depth_m"] - row["q25_depth_m"]

        # Count non-nulls
        row["n_date_nonnull"] = int(group["n_date_nonnull"].sum())
        row["n_time_nonnull"] = int(group["n_time_nonnull"].sum())
        row["n_sonar_idx_nonnull"] = int(group["n_sonar_idx_nonnull"].sum())

        result_rows.append(row)

    return pd.DataFrame(result_rows)


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------
def atomic_write_df(df: pd.DataFrame, target_parquet: Path, target_tsv: Path,
                    logger: logging.Logger):
    target_parquet.parent.mkdir(parents=True, exist_ok=True)
    tmp_pq = target_parquet.with_suffix(".parquet.tmp")
    tmp_tsv = target_tsv.with_suffix(".tsv.tmp")
    df.to_parquet(tmp_pq, index=False)
    logger.info(f"Wrote temp parquet: {tmp_pq}")
    df.to_csv(tmp_tsv, sep="\t", index=False)
    logger.info(f"Wrote temp tsv: {tmp_tsv}")
    os.replace(tmp_pq, target_parquet)
    os.replace(tmp_tsv, target_tsv)
    logger.info(f"Renamed to final: {target_parquet.name}, {target_tsv.name}")


def write_errors_tsv(errors: list[dict], errors_path: Path, logger: logging.Logger):
    if not errors:
        return
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    df_err = pd.DataFrame(errors)
    df_err.to_csv(errors_path, sep="\t", index=False)
    logger.info(f"Wrote {len(errors)} errors to {errors_path}")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def write_report(
    report_path: Path,
    manifest_df: pd.DataFrame,
    run_label: str,
    cell_size: str,
    elapsed_s: float,
    logger: logging.Logger,
):
    n_ok = int((manifest_df["status"] == "ok").sum())
    n_skip = int((manifest_df["status"] == "skipped_exists").sum())
    n_err = int((manifest_df["status"] == "error").sum())

    ok = manifest_df[manifest_df["status"] == "ok"]
    total_rows_read = int(ok["rows_read"].sum()) if len(ok) > 0 else 0
    total_rows_used = int(ok["rows_used"].sum()) if len(ok) > 0 else 0
    total_cells = int(ok["n_cells"].sum()) if len(ok) > 0 else 0
    total_points = int(ok["n_points_total"].sum()) if len(ok) > 0 else 0

    cell_deg = CELL_SIZES[cell_size]

    lines = [
        f"# File Cells Report — {run_label} ({cell_size})",
        f"",
        f"Generated: {datetime.now().isoformat()}",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Cell size | {cell_size} ({cell_deg:.6f} deg) |",
        f"| Files processed | {n_ok} ok, {n_skip} skipped, {n_err} errors |",
        f"| Total rows read | {total_rows_read:,} |",
        f"| Total qc_pass rows used | {total_rows_used:,} |",
        f"| Total file-cell rows | {total_cells:,} |",
        f"| Total points in cells | {total_points:,} |",
        f"| Elapsed | {elapsed_s:.1f}s |",
        f"",
    ]

    if len(ok) > 0:
        lines.append(f"## Per-file cell count distribution")
        lines.append(f"")
        lines.append(f"| Stat | Value |")
        lines.append(f"|------|-------|")
        lines.append(f"| Min cells per file | {int(ok['n_cells'].min()):,} |")
        lines.append(f"| Max cells per file | {int(ok['n_cells'].max()):,} |")
        lines.append(f"| Mean cells per file | {ok['n_cells'].mean():.1f} |")
        lines.append(f"| Median cells per file | {ok['n_cells'].median():.1f} |")
        lines.append(f"")

        lines.append(f"## n_points per cell distribution (across all files)")
        lines.append(f"")
        all_npts_min = int(ok["n_points_min"].min())
        all_npts_max = int(ok["n_points_max"].max())
        all_npts_mean = float(ok["n_points_mean"].mean())
        lines.append(f"| Stat | Value |")
        lines.append(f"|------|-------|")
        lines.append(f"| Min n_points (per cell) | {all_npts_min:,} |")
        lines.append(f"| Max n_points (per cell) | {all_npts_max:,} |")
        lines.append(f"| Mean n_points (per cell, avg of file means) | {all_npts_mean:.1f} |")
        lines.append(f"")

        lines.append(f"## Depth statistics range")
        lines.append(f"")
        lines.append(f"| Stat | Value |")
        lines.append(f"|------|-------|")
        lines.append(f"| median_depth min | {float(ok['median_depth_min'].min()):.1f} m |")
        lines.append(f"| median_depth max | {float(ok['median_depth_max'].max()):.1f} m |")
        lines.append(f"")

    content = "\n".join(lines)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(content, encoding="utf-8")
    logger.info(f"Report written to {report_path}")


# ---------------------------------------------------------------------------
# Estimate only
# ---------------------------------------------------------------------------
def estimate_only(
    qc_manifest: pd.DataFrame,
    file_manifest: pd.DataFrame,
    output_dir: Path,
    cell_size: str,
    logger: logging.Logger,
):
    ok = qc_manifest[qc_manifest["status"] == "ok"]
    total_rows = int(ok["rows_written"].sum())
    n_files = len(ok)

    # Estimate cells per file based on typical spatial coverage
    # A typical multibeam file covers ~0.5-5 degree swath
    # At 1min resolution, that's ~30x30 to 300x300 cells = 900 to 90000 cells
    # Conservative estimate: ~5000 cells per file
    est_cells_per_file = 5000
    est_total_cells = n_files * est_cells_per_file
    est_bytes_per_cell_row = 300  # ~300 bytes per cell row with all stats
    est_output_gb = est_total_cells * est_bytes_per_cell_row / 1e9

    logger.info(f"Output dir would be: {output_dir}")
    logger.info(f"Files: {n_files}")
    logger.info(f"Total input rows: {total_rows:,}")
    logger.info(f"Est. cells per file: ~{est_cells_per_file:,}")
    logger.info(f"Est. total cell rows: ~{est_total_cells:,}")
    logger.info(f"Est. output size: ~{est_output_gb:.2f} GB")

    print(f"\n{'='*60}")
    print(f"  ESTIMATE ONLY (no files written)")
    print(f"  cell_size:           {cell_size}")
    print(f"  run_label target dir: {output_dir}")
    print(f"  Input files:         {n_files}")
    print(f"  Input rows:          {total_rows:,}")
    print(f"  Est. total cells:    ~{est_total_cells:,}")
    print(f"  Est. output size:    ~{est_output_gb:.2f} GB")
    print(f"  Est. bytes/cell_row: ~{est_bytes_per_cell_row}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Aggregate QC-passed points into file-level cell statistics.",
    )
    parser.add_argument(
        "--run-label", type=str, default="sample",
        choices=VALID_RUN_LABELS,
        help="Run label: sample (default), test100, full.",
    )
    parser.add_argument(
        "--cell-size", type=str, default="1min",
        choices=VALID_CELL_SIZES,
        help="Cell size: 1min (default).",
    )
    parser.add_argument(
        "--confirm-full", action="store_true",
        help="Required when --run-label=full.",
    )
    parser.add_argument(
        "--sample-n-files", type=int, default=None,
        help="Randomly sample N files from points_qc.",
    )
    parser.add_argument(
        "--limit-files", type=int, default=None,
        help="Process only first N files.",
    )
    parser.add_argument(
        "--file-id", type=str, nargs="*", default=None,
        help="Process specific file_id(s).",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing output files.",
    )
    parser.add_argument(
        "--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
        help=f"Rows per batch when reading parquet (default: {DEFAULT_CHUNK_SIZE}).",
    )
    parser.add_argument(
        "--estimate-only", action="store_true",
        help="Print estimates and exit. No files written.",
    )
    args = parser.parse_args()

    run_label = args.run_label
    cell_size = args.cell_size
    cell_deg = CELL_SIZES[cell_size]

    log_suffix = run_label
    log_path = LOG_DIR / f"04a_make_multibeam_file_cells_{log_suffix}.log"
    errors_tsv = LOG_DIR / f"04a_file_cells_errors_{log_suffix}.tsv"

    logger = setup_logging(log_path)
    logger.info("=" * 60)
    logger.info("Starting 04a_make_multibeam_file_cells.py")
    logger.info(f"Args: {vars(args)}")

    # Safety gate
    if run_label == "full" and not args.confirm_full:
        msg = "ABORTED: --run-label=full requires --confirm-full."
        logger.error(msg)
        print(f"ERROR: {msg}")
        sys.exit(1)

    # Load QC manifest
    if not QC_MANIFEST_PQ.exists():
        logger.error(f"points_qc_manifest not found: {QC_MANIFEST_PQ}")
        print(f"ERROR: points_qc_manifest not found: {QC_MANIFEST_PQ}")
        sys.exit(1)

    qc_manifest = pd.read_parquet(QC_MANIFEST_PQ)
    qc_manifest = qc_manifest[qc_manifest["status"] == "ok"].copy()
    logger.info(f"Loaded points_qc_manifest: {len(qc_manifest)} ok files")

    # Load file manifest for metadata join
    file_manifest = None
    if FILE_MANIFEST_PQ.exists():
        file_manifest = pd.read_parquet(FILE_MANIFEST_PQ)
        logger.info(f"Loaded file_manifest_points_raw: {len(file_manifest)} rows")
    else:
        logger.warning(f"file_manifest_points_raw not found: {FILE_MANIFEST_PQ}")

    # Resolve output paths
    output_dir, manifest_pq, manifest_tsv, report_path = get_run_paths(run_label, cell_size)

    # Select files to process
    to_process = qc_manifest.copy()

    if args.file_id:
        to_process = to_process[to_process["file_id"].isin(args.file_id)]
    elif args.sample_n_files is not None:
        n = min(args.sample_n_files, len(to_process))
        to_process = to_process.sample(n=n, random_state=42)

    if args.limit_files is not None:
        to_process = to_process.head(args.limit_files)

    if len(to_process) == 0:
        logger.info("No files to process.")
        print("No files to process.")
        return

    # Build file_id -> metadata lookup
    file_meta_map = {}
    if file_manifest is not None:
        for _, row in file_manifest.iterrows():
            file_meta_map[row["file_id"]] = {
                "subzip_id": row.get("subzip_id", ""),
                "cruise_id_guess": row.get("cruise_id_guess", ""),
                "track_kind": row.get("track_kind", ""),
                "data_layout": row.get("data_layout", ""),
            }

    # Config summary
    summary = (
        f"\n{'='*60}\n"
        f"  CONFIG SUMMARY\n"
        f"{'='*60}\n"
        f"  input_dir:            {POINTS_QC_DIR}\n"
        f"  qc_manifest:          {QC_MANIFEST_PQ}\n"
        f"  file_manifest:        {FILE_MANIFEST_PQ}\n"
        f"  total ok files:       {len(qc_manifest)}\n"
        f"  selected files:       {len(to_process)}\n"
        f"  cell_size:            {cell_size} ({cell_deg:.6f} deg)\n"
        f"  run_label:            {run_label}\n"
        f"  output_dir:           {output_dir}\n"
        f"  confirm_full:         {args.confirm_full}\n"
        f"  estimate_only:        {args.estimate_only}\n"
        f"  backend:              pandas + pyarrow\n"
        f"{'='*60}"
    )
    logger.info(summary)
    print(summary)

    if args.estimate_only:
        estimate_only(qc_manifest, file_manifest, output_dir, cell_size, logger)
        return

    logger.info(f"Files to process: {len(to_process)}")

    # Process files
    manifest_entries = []
    errors = []
    t_start = datetime.now()

    for idx, (_, row) in enumerate(to_process.iterrows()):
        if idx % 100 == 0 and idx > 0:
            logger.info(f"  Progress: {idx}/{len(to_process)}")

        file_id = row["file_id"]
        pq_name = file_id_to_parquet_name(file_id)
        input_path = POINTS_QC_DIR / pq_name

        meta = file_meta_map.get(file_id, {
            "subzip_id": "",
            "cruise_id_guess": "",
            "track_kind": "",
            "data_layout": "",
        })

        result = process_file(
            file_id=file_id,
            input_path=input_path,
            output_dir=output_dir,
            cell_deg=cell_deg,
            cell_size=cell_size,
            chunk_size=args.chunk_size,
            overwrite=args.overwrite,
            file_meta=meta,
            logger=logger,
        )
        manifest_entries.append(result)
        if result["status"] == "error":
            errors.append(result)

    t_end = datetime.now()
    elapsed_s = (t_end - t_start).total_seconds()

    # Write manifest
    manifest_df = pd.DataFrame(manifest_entries)
    atomic_write_df(manifest_df, manifest_pq, manifest_tsv, logger)
    write_errors_tsv(errors, errors_tsv, logger)

    # Write report
    write_report(report_path, manifest_df, run_label, cell_size, elapsed_s, logger)

    # Summary
    ok_entries = [e for e in manifest_entries if e["status"] == "ok"]
    n_ok = len(ok_entries)
    n_skip = sum(1 for e in manifest_entries if e["status"] == "skipped_exists")
    n_err = sum(1 for e in manifest_entries if e["status"] == "error")
    total_rows_read = sum(e["rows_read"] for e in ok_entries if isinstance(e["rows_read"], (int, float)))
    total_rows_used = sum(e["rows_used"] for e in ok_entries if isinstance(e["rows_used"], (int, float)))
    total_cells = sum(e["n_cells"] for e in ok_entries if isinstance(e["n_cells"], (int, float)))
    total_points = sum(e["n_points_total"] for e in ok_entries if isinstance(e["n_points_total"], (int, float)))

    # Output size
    output_bytes = 0
    if output_dir.exists():
        for f in output_dir.glob("*.parquet"):
            output_bytes += f.stat().st_size

    bytes_per_cell_row = output_bytes / total_cells if total_cells > 0 else 0
    rows_per_sec = total_rows_read / elapsed_s if elapsed_s > 0 else 0

    report = f"""
{'='*60}
  RUN REPORT — 04a_make_multibeam_file_cells.py
{'='*60}
  run_label:           {run_label}
  cell_size:           {cell_size} ({cell_deg:.6f} deg)
  output_dir:          {output_dir}
  manifest:            {manifest_pq}
  files_processed:     {n_ok} ok, {n_skip} skipped, {n_err} errors
  rows_read:           {total_rows_read:,}
  rows_used (qc_pass): {total_rows_used:,}
  file-cell rows:      {total_cells:,}
  total points:        {total_points:,}
  output_size:         {output_bytes / 1e6:.1f} MB
  bytes_per_cell_row:  {bytes_per_cell_row:.1f}
  elapsed:             {elapsed_s:.1f}s
  rows/sec:            {rows_per_sec:,.0f}
  error_files:         {n_err}
  backend:             pandas + pyarrow
{'='*60}
"""
    logger.info(report)
    print(report)


if __name__ == "__main__":
    main()
