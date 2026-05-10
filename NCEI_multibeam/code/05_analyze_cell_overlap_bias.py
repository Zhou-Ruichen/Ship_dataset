#!/usr/bin/env python3
"""
05_analyze_cell_overlap_bias.py

Diagnose overlap / bias between file-level cells and merged global cells.

For every overlap cell (n_file_cells > 1 in cells.parquet), computes per-file-cell
residuals against the file-balanced median, then aggregates residuals by file,
cruise, subzip, and cell to identify systematic biases.

Reads:
  - derived/file_cells_1min/*.parquet             (from 04a)
  - derived/cells_1min/cells.parquet               (from 04b)
  - manifests/file_cells_manifest_1min.parquet      (from 04a)
  - manifests/cells_manifest_1min.parquet           (from 04b)

Writes (full mode, cell-size=1min):
  - derived/overlap_bias_1min/overlap_file_cell_residuals.parquet
  - derived/overlap_bias_1min/file_bias_summary.parquet + .tsv
  - derived/overlap_bias_1min/cruise_bias_summary.parquet + .tsv
  - derived/overlap_bias_1min/subzip_bias_summary.parquet + .tsv
  - derived/overlap_bias_1min/suspicious_files.tsv
  - derived/overlap_bias_1min/suspicious_cruises.tsv
  - derived/overlap_bias_1min/suspicious_cells.parquet + .tsv
  - derived/overlap_bias_1min/overlap_bias_report.md
  - output/logs/05_analyze_cell_overlap_bias_full.log
  - output/logs/05_overlap_bias_errors_full.tsv

Usage:
    # Sample: 50 random file-cell files
    python 05_analyze_cell_overlap_bias.py --run-label sample --sample-n-files 50 --overwrite

    # Test100
    python 05_analyze_cell_overlap_bias.py --run-label test100 --limit-files 100 --overwrite

    # Full run
    python 05_analyze_cell_overlap_bias.py --run-label full --confirm-full --overwrite

    # Estimate only
    python 05_analyze_cell_overlap_bias.py --run-label full --confirm-full --estimate-only
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent

FC_DIR = ROOT_DIR / "derived" / "file_cells_1min"
CELLS_PQ = ROOT_DIR / "derived" / "cells_1min" / "cells.parquet"
FC_MANIFEST_PQ = ROOT_DIR / "manifests" / "file_cells_manifest_1min.parquet"
CELLS_MANIFEST_PQ = ROOT_DIR / "manifests" / "cells_manifest_1min.parquet"

LOG_DIR = ROOT_DIR / "output" / "logs"

VALID_RUN_LABELS = ("sample", "test100", "full")
VALID_CELL_SIZES = ("1min",)

CELL_SIZES = {
    "1min": 1.0 / 60.0,
}

# Suspicious thresholds (diagnostic only — no data removal)
SUSPICIOUS_FILE_MIN_OVERLAP = 50
SUSPICIOUS_ABS_MEDIAN_THRESH = 20.0
SUSPICIOUS_MAD_THRESH = 20.0
SUSPICIOUS_RMSE_THRESH = 50.0
SUSPICIOUS_ABS_P95_THRESH = 100.0

SUSPICIOUS_CELL_RANGE_THRESH = 100.0
SUSPICIOUS_CELL_IQR_THRESH = 50.0
SUSPICIOUS_CELL_MAX_ABS_THRESH = 100.0


def get_output_paths(run_label: str, cell_size: str):
    """Return dict of output paths for given run_label and cell_size."""
    derived = ROOT_DIR / "derived"
    docs = ROOT_DIR / "docs"
    cs = cell_size

    if run_label == "full":
        out_dir = derived / f"overlap_bias_{cs}"
        residuals_name = "overlap_file_cell_residuals.parquet"
    else:
        out_dir = derived / f"overlap_bias_{cs}_{run_label}"
        residuals_name = f"overlap_file_cell_residuals_{run_label}.parquet"

    return {
        "out_dir": out_dir,
        "residuals_pq": out_dir / residuals_name,
        "file_bias_pq": out_dir / "file_bias_summary.parquet",
        "file_bias_tsv": out_dir / "file_bias_summary.tsv",
        "cruise_bias_pq": out_dir / "cruise_bias_summary.parquet",
        "cruise_bias_tsv": out_dir / "cruise_bias_summary.tsv",
        "subzip_bias_pq": out_dir / "subzip_bias_summary.parquet",
        "subzip_bias_tsv": out_dir / "subzip_bias_summary.tsv",
        "suspicious_files_tsv": out_dir / "suspicious_files.tsv",
        "suspicious_cruises_tsv": out_dir / "suspicious_cruises.tsv",
        "suspicious_cells_pq": out_dir / "suspicious_cells.parquet",
        "suspicious_cells_tsv": out_dir / "suspicious_cells.tsv",
        "report_path": out_dir / "overlap_bias_report.md",
    }


def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("overlap_bias")
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


def atomic_write_parquet(df: pd.DataFrame, target: Path, logger: logging.Logger):
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    logger.info(f"  Wrote temp: {tmp.name} ({len(df):,} rows)")
    os.replace(tmp, target)
    logger.info(f"  Renamed to: {target.name}")


def atomic_write_tsv(df: pd.DataFrame, target: Path, logger: logging.Logger):
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tsv.tmp")
    df.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, target)
    logger.info(f"  Wrote TSV: {target.name}")


def write_errors_tsv(errors: list[dict], errors_path: Path, logger: logging.Logger):
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = errors_path.with_suffix(".tsv.tmp")
    if not errors:
        pd.DataFrame().to_csv(tmp, sep="\t", index=False)
        os.replace(tmp, errors_path)
        logger.info(f"Wrote empty errors TSV (0 errors): {errors_path.name}")
        return
    df_err = pd.DataFrame(errors)
    df_err.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, errors_path)
    logger.info(f"Wrote {len(errors)} errors to {errors_path}")


def read_file_cells(
    manifest_ok: pd.DataFrame,
    logger: logging.Logger,
) -> tuple[pd.DataFrame, list[dict]]:
    """Read file-cell parquets listed in manifest_ok.

    Returns (concatenated DataFrame, list of error dicts).
    """
    all_dfs = []
    errors = []
    total_rows = 0

    for idx, (_, row) in enumerate(manifest_ok.iterrows()):
        file_id = row["file_id"]
        fc_path = ROOT_DIR / row["output_path"]

        try:
            if not fc_path.exists():
                errors.append({
                    "file_id": file_id,
                    "error": f"file not found: {fc_path}",
                })
                logger.warning(f"  SKIP (not found): {fc_path}")
                continue

            df = pd.read_parquet(fc_path)
            all_dfs.append(df)
            total_rows += len(df)

            if (idx + 1) % 500 == 0:
                logger.info(f"  Read {idx + 1}/{len(manifest_ok)} files, {total_rows:,} file-cell rows")

        except Exception as e:
            errors.append({
                "file_id": file_id,
                "error": str(e),
            })
            logger.error(f"  ERROR reading {fc_path}: {e}")

    logger.info(f"  Read complete: {len(all_dfs)}/{len(manifest_ok)} files, {total_rows:,} file-cell rows")

    if not all_dfs:
        return pd.DataFrame(), errors

    fc = pd.concat(all_dfs, ignore_index=True)
    logger.info(f"  Concatenated DataFrame: {len(fc):,} rows x {len(fc.columns)} columns")

    return fc, errors


def compute_residuals(
    fc: pd.DataFrame,
    cells: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """Join file-cells with overlap cells and compute residuals.

    Only processes cells where n_file_cells > 1.
    """
    overlap_cell_ids = set(cells.loc[cells["n_file_cells"] > 1, "cell_id"])
    logger.info(f"  Overlap cells: {len(overlap_cell_ids):,}")

    fc_overlap = fc[fc["cell_id"].isin(overlap_cell_ids)].copy()
    logger.info(f"  Overlap file-cell rows: {len(fc_overlap):,}")

    multi_cruise_ids = set(cells.loc[cells["n_cruises_guess"] > 1, "cell_id"])
    fc_overlap["is_multi_cruise"] = fc_overlap["cell_id"].isin(multi_cruise_ids)

    cell_ref = cells.loc[
        cells["cell_id"].isin(overlap_cell_ids),
        ["cell_id", "median_depth_file_balanced", "median_elev_file_balanced",
         "n_file_cells", "n_cruises_guess"],
    ].copy()

    merged = fc_overlap.merge(cell_ref, on="cell_id", how="left")

    merged["residual_depth_m"] = (
        merged["median_depth_m_positive_down"] - merged["median_depth_file_balanced"]
    )
    merged["residual_elev_m"] = (
        merged["median_elev_m"] - merged["median_elev_file_balanced"]
    )

    logger.info(f"  Residuals computed: {len(merged):,} rows")

    return merged


def _bias_agg_dict():
    return {
        "n_overlap_file_cells": ("residual_depth_m", "size"),
        "n_overlap_cruises": ("cruise_id_guess", "nunique"),
        "n_points_total_overlap": ("n_points", "sum"),
        "residual_depth_m_median": ("residual_depth_m", lambda x: x.median()),
        "residual_depth_m_mean": ("residual_depth_m", "mean"),
        "residual_depth_m_std": ("residual_depth_m", "std"),
        "residual_depth_m_mad": ("residual_depth_m", lambda x: (x - x.median()).abs().median()),
        "residual_depth_m_iqr": ("residual_depth_m", lambda x: x.quantile(0.75) - x.quantile(0.25)),
        "residual_depth_m_rmse": ("residual_depth_m", lambda x: np.sqrt((x ** 2).mean())),
        "residual_depth_m_p05": ("residual_depth_m", lambda x: x.quantile(0.05)),
        "residual_depth_m_p95": ("residual_depth_m", lambda x: x.quantile(0.95)),
        "abs_residual_depth_m_median": ("residual_depth_m", lambda x: x.abs().median()),
        "abs_residual_depth_m_p95": ("residual_depth_m", lambda x: x.abs().quantile(0.95)),
        "max_abs_residual_depth_m": ("residual_depth_m", lambda x: x.abs().max()),
    }


def aggregate_bias_by_group(
    residuals: pd.DataFrame,
    group_col: str,
    logger: logging.Logger,
) -> pd.DataFrame:
    """Aggregate residual statistics by a grouping column (file_id, cruise_id_guess, subzip_id)."""
    logger.info(f"  Aggregating bias by {group_col}...")

    grouped = residuals.groupby(group_col)
    agg_dict = _bias_agg_dict()

    # Use named aggregation via agg with tuples
    result = grouped.agg(**agg_dict).reset_index()

    result["residual_depth_m_std"] = result["residual_depth_m_std"].fillna(0.0)

    logger.info(f"  {group_col}: {len(result):,} groups")
    return result


def compute_cell_residuals(
    residuals: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """Compute per-cell residual statistics."""
    logger.info("  Aggregating cell-level residuals...")

    grouped = residuals.groupby("cell_id")

    def safe_std(x):
        return x.std() if len(x) > 1 else 0.0

    cell_stats = grouped.agg(
        n_file_cells=("residual_depth_m", "size"),
        n_cruises_guess=("cruise_id_guess", "nunique"),
        residual_depth_range=("residual_depth_m", lambda x: x.max() - x.min()),
        residual_depth_iqr=("residual_depth_m", lambda x: x.quantile(0.75) - x.quantile(0.25)),
        residual_depth_std=("residual_depth_m", safe_std),
        max_abs_file_residual_depth=("residual_depth_m", lambda x: x.abs().max()),
    ).reset_index()

    cell_stats["has_large_disagreement"] = (
        (cell_stats["residual_depth_range"] >= SUSPICIOUS_CELL_RANGE_THRESH)
        | (cell_stats["residual_depth_iqr"] >= SUSPICIOUS_CELL_IQR_THRESH)
        | (cell_stats["max_abs_file_residual_depth"] >= SUSPICIOUS_CELL_MAX_ABS_THRESH)
    )

    logger.info(f"  Cell residuals: {len(cell_stats):,} cells")
    logger.info(f"  Cells with large disagreement: {int(cell_stats['has_large_disagreement'].sum()):,}")

    return cell_stats


def flag_suspicious_files(file_bias: pd.DataFrame) -> pd.DataFrame:
    """Flag files with systematic bias using diagnostic thresholds."""
    has_min_overlap = file_bias["n_overlap_file_cells"] >= SUSPICIOUS_FILE_MIN_OVERLAP

    any_bias = (
        (file_bias["residual_depth_m_median"].abs() >= SUSPICIOUS_ABS_MEDIAN_THRESH)
        | (file_bias["residual_depth_m_mad"].abs() >= SUSPICIOUS_MAD_THRESH)
        | (file_bias["residual_depth_m_rmse"] >= SUSPICIOUS_RMSE_THRESH)
        | (file_bias["abs_residual_depth_m_p95"] >= SUSPICIOUS_ABS_P95_THRESH)
    )

    suspicious = file_bias[has_min_overlap & any_bias].copy()
    return suspicious


def flag_suspicious_cruises(cruise_bias: pd.DataFrame) -> pd.DataFrame:
    """Flag cruises with systematic bias using diagnostic thresholds."""
    has_min_overlap = cruise_bias["n_overlap_file_cells"] >= SUSPICIOUS_FILE_MIN_OVERLAP

    any_bias = (
        (cruise_bias["residual_depth_m_median"].abs() >= SUSPICIOUS_ABS_MEDIAN_THRESH)
        | (cruise_bias["residual_depth_m_mad"].abs() >= SUSPICIOUS_MAD_THRESH)
        | (cruise_bias["residual_depth_m_rmse"] >= SUSPICIOUS_RMSE_THRESH)
        | (cruise_bias["abs_residual_depth_m_p95"] >= SUSPICIOUS_ABS_P95_THRESH)
    )

    suspicious = cruise_bias[has_min_overlap & any_bias].copy()
    return suspicious


def flag_suspicious_cells(cell_stats: pd.DataFrame) -> pd.DataFrame:
    """Flag cells with large internal disagreement."""
    suspicious = cell_stats[
        (cell_stats["n_file_cells"] > 1)
        & (
            (cell_stats["residual_depth_range"] >= SUSPICIOUS_CELL_RANGE_THRESH)
            | (cell_stats["residual_depth_iqr"] >= SUSPICIOUS_CELL_IQR_THRESH)
            | (cell_stats["max_abs_file_residual_depth"] >= SUSPICIOUS_CELL_MAX_ABS_THRESH)
        )
    ].copy()
    return suspicious


def write_report(
    report_path: Path,
    residuals: pd.DataFrame,
    file_bias: pd.DataFrame,
    cruise_bias: pd.DataFrame,
    subzip_bias: pd.DataFrame,
    suspicious_files: pd.DataFrame,
    suspicious_cruises: pd.DataFrame,
    suspicious_cells: pd.DataFrame,
    n_fc_files: int,
    n_total_fc_rows: int,
    n_overlap_fc_rows: int,
    n_overlap_cells: int,
    n_multi_cruise_cells: int,
    n_read_errors: int,
    run_label: str,
    cell_size: str,
    elapsed_s: float,
    logger: logging.Logger,
):
    lines = [
        f"# Overlap Bias Analysis Report — {run_label} ({cell_size})",
        f"",
        f"Generated: {datetime.now().isoformat()}",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Cell size | {cell_size} ({CELL_SIZES[cell_size]:.6f} deg) |",
        f"| Input file-cell files | {n_fc_files} |",
        f"| Input file-cell rows | {n_total_fc_rows:,} |",
        f"| Read errors | {n_read_errors} |",
        f"| Overlap file-cell rows | {n_overlap_fc_rows:,} |",
        f"| Overlap cells | {n_overlap_cells:,} |",
        f"| Multi-cruise overlap cells | {n_multi_cruise_cells:,} |",
        f"| Elapsed | {elapsed_s:.1f}s |",
        f"| Backend | pandas |",
        f"",
    ]

    if len(residuals) > 0:
        rd = residuals["residual_depth_m"]
        lines.append(f"## Residual depth statistics (all overlap file-cells)")
        lines.append(f"")
        lines.append(f"| Stat | Value |")
        lines.append(f"|------|-------|")
        lines.append(f"| count | {len(rd):,} |")
        lines.append(f"| min | {float(rd.min()):.4f} m |")
        lines.append(f"| p05 | {float(rd.quantile(0.05)):.4f} m |")
        lines.append(f"| p25 | {float(rd.quantile(0.25)):.4f} m |")
        lines.append(f"| median | {float(rd.median()):.4f} m |")
        lines.append(f"| p75 | {float(rd.quantile(0.75)):.4f} m |")
        lines.append(f"| p95 | {float(rd.quantile(0.95)):.4f} m |")
        lines.append(f"| max | {float(rd.max()):.4f} m |")
        lines.append(f"| mean | {float(rd.mean()):.4f} m |")
        lines.append(f"| std | {float(rd.std()):.4f} m |")
        mad = (rd - rd.median()).abs().median()
        lines.append(f"| MAD | {mad:.4f} m |")
        lines.append(f"")

        # Check residual_elev ≈ -residual_depth
        re = residuals["residual_elev_m"]
        diff = (re + rd).abs()
        max_diff = float(diff.max())
        mean_diff = float(diff.mean())
        lines.append(f"## Residual consistency check")
        lines.append(f"")
        lines.append(f"| Check | Result |")
        lines.append(f"|-------|--------|")
        lines.append(f"| residual_elev_m + residual_depth_m | should ≈ 0 |")
        lines.append(f"| max |diff| | {max_diff:.6e} |")
        lines.append(f"| mean |diff| | {mean_diff:.6e} |")
        lines.append(f"| Consistent? | {'YES' if max_diff < 1e-6 else 'NO — INVESTIGATE'} |")
        lines.append(f"")

    if len(file_bias) > 0:
        lines.append(f"## File bias summary")
        lines.append(f"")
        lines.append(f"| Stat | Value |")
        lines.append(f"|------|-------|")
        lines.append(f"| Total files with overlap | {len(file_bias):,} |")
        lines.append(f"| Suspicious files | {len(suspicious_files):,} |")
        lines.append(f"")
        if len(file_bias) >= 5:
            lines.append(f"### Top 10 files by |median residual|")
            lines.append(f"")
            top = file_bias.nlargest(10, "abs_residual_depth_m_median")
            lines.append(f"| file_id | n_overlap | median_res | mad | rmse | p95_abs |")
            lines.append(f"|---------|-----------|------------|-----|------|---------|")
            for _, r in top.iterrows():
                fid = r["file_id"][:50] + "..." if len(str(r["file_id"])) > 50 else r["file_id"]
                lines.append(
                    f"| {fid} | {int(r['n_overlap_file_cells'])} | "
                    f"{r['residual_depth_m_median']:.2f} | "
                    f"{r['residual_depth_m_mad']:.2f} | "
                    f"{r['residual_depth_m_rmse']:.2f} | "
                    f"{r['abs_residual_depth_m_p95']:.2f} |"
                )
            lines.append(f"")

    if len(cruise_bias) > 0:
        lines.append(f"## Cruise bias summary")
        lines.append(f"")
        lines.append(f"| Stat | Value |")
        lines.append(f"|------|-------|")
        lines.append(f"| Total cruises with overlap | {len(cruise_bias):,} |")
        lines.append(f"| Suspicious cruises | {len(suspicious_cruises):,} |")
        lines.append(f"")
        if len(cruise_bias) >= 5:
            lines.append(f"### Top 10 cruises by |median residual|")
            lines.append(f"")
            top = cruise_bias.nlargest(10, "abs_residual_depth_m_median")
            lines.append(f"| cruise_id_guess | n_overlap | median_res | mad | rmse | p95_abs |")
            lines.append(f"|------------------|-----------|------------|-----|------|---------|")
            for _, r in top.iterrows():
                cid = str(r["cruise_id_guess"])[:40]
                lines.append(
                    f"| {cid} | {int(r['n_overlap_file_cells'])} | "
                    f"{r['residual_depth_m_median']:.2f} | "
                    f"{r['residual_depth_m_mad']:.2f} | "
                    f"{r['residual_depth_m_rmse']:.2f} | "
                    f"{r['abs_residual_depth_m_p95']:.2f} |"
                )
            lines.append(f"")

    if len(subzip_bias) > 0:
        lines.append(f"## Subzip bias summary")
        lines.append(f"")
        lines.append(f"| Stat | Value |")
        lines.append(f"|------|-------|")
        lines.append(f"| Total subzips with overlap | {len(subzip_bias):,} |")
        lines.append(f"")

    lines.append(f"## Suspicious counts")
    lines.append(f"")
    lines.append(f"| Category | Count |")
    lines.append(f"|----------|-------|")
    lines.append(f"| Suspicious files | {len(suspicious_files):,} |")
    lines.append(f"| Suspicious cruises | {len(suspicious_cruises):,} |")
    lines.append(f"| Suspicious cells | {len(suspicious_cells):,} |")
    lines.append(f"")

    lines.append(f"## Thresholds used (diagnostic only — no data removed)")
    lines.append(f"")
    lines.append(f"| Threshold | Value |")
    lines.append(f"|-----------|-------|")
    lines.append(f"| min overlap file-cells (file/cruise) | {SUSPICIOUS_FILE_MIN_OVERLAP} |")
    lines.append(f"| |median residual| (file/cruise) | {SUSPICIOUS_ABS_MEDIAN_THRESH} m |")
    lines.append(f"| MAD (file/cruise) | {SUSPICIOUS_MAD_THRESH} m |")
    lines.append(f"| RMSE (file/cruise) | {SUSPICIOUS_RMSE_THRESH} m |")
    lines.append(f"| |residual| p95 (file/cruise) | {SUSPICIOUS_ABS_P95_THRESH} m |")
    lines.append(f"| cell residual range | {SUSPICIOUS_CELL_RANGE_THRESH} m |")
    lines.append(f"| cell residual IQR | {SUSPICIOUS_CELL_IQR_THRESH} m |")
    lines.append(f"| cell max |residual| | {SUSPICIOUS_CELL_MAX_ABS_THRESH} m |")
    lines.append(f"")

    content = "\n".join(lines)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = report_path.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, report_path)
    logger.info(f"Report written to {report_path}")


def estimate_only(
    manifest_ok: pd.DataFrame,
    cells: pd.DataFrame,
    output_dir: Path,
    cell_size: str,
    logger: logging.Logger,
):
    n_files = len(manifest_ok)
    total_fc_rows = int(manifest_ok["n_cells"].sum()) if "n_cells" in manifest_ok.columns else 0
    total_points = int(manifest_ok["n_points_total"].sum()) if "n_points_total" in manifest_ok.columns else 0

    n_overlap_cells = int((cells["n_file_cells"] > 1).sum())
    # Estimate overlap file-cell rows from cells
    overlap_fc = cells[cells["n_file_cells"] > 1]
    est_overlap_fc_rows = int(overlap_fc["n_file_cells"].sum()) if len(overlap_fc) > 0 else 0

    # But if sample/test100, overlap cells will be subset
    est_residuals_rows = est_overlap_fc_rows
    est_bytes_per_residual_row = 300
    est_residuals_mb = est_residuals_rows * est_bytes_per_residual_row / 1e6

    cell_deg = CELL_SIZES[cell_size]

    logger.info(f"Output dir would be: {output_dir}")
    logger.info(f"Input file-cell files: {n_files}")
    logger.info(f"Input file-cell rows: {total_fc_rows:,}")
    logger.info(f"Total cells: {len(cells):,}")
    logger.info(f"Overlap cells (n_file_cells>1): {n_overlap_cells:,}")
    logger.info(f"Est. overlap file-cell rows: ~{est_overlap_fc_rows:,}")
    logger.info(f"Est. residuals output: ~{est_residuals_mb:.1f} MB")

    print(f"\n{'=' * 60}")
    print(f"  ESTIMATE ONLY (no files written)")
    print(f"  cell_size:              {cell_size} ({cell_deg:.6f} deg)")
    print(f"  run_label target dir:   {output_dir}")
    print(f"  Input file-cell files:  {n_files}")
    print(f"  Input file-cell rows:   {total_fc_rows:,}")
    print(f"  Total cells:            {len(cells):,}")
    print(f"  Overlap cells:          {n_overlap_cells:,}")
    print(f"  Est. overlap fc rows:   ~{est_overlap_fc_rows:,}")
    print(f"  Est. residuals output:  ~{est_residuals_mb:.1f} MB")
    print(f"{'=' * 60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze overlap/bias between file-level cells and merged global cells.",
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
        help="Randomly sample N file-cell files from manifest.",
    )
    parser.add_argument(
        "--limit-files", type=int, default=None,
        help="Process only first N file-cell files.",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing output files.",
    )
    parser.add_argument(
        "--estimate-only", action="store_true",
        help="Print estimates and exit. No files written.",
    )
    args = parser.parse_args()

    run_label = args.run_label
    cell_size = args.cell_size
    cell_deg = CELL_SIZES[cell_size]

    log_path = LOG_DIR / f"05_analyze_cell_overlap_bias_{run_label}.log"
    errors_tsv = LOG_DIR / f"05_overlap_bias_errors_{run_label}.tsv"

    logger = setup_logging(log_path)
    logger.info("=" * 60)
    logger.info("Starting 05_analyze_cell_overlap_bias.py")
    logger.info(f"Args: {vars(args)}")

    # Safety gate
    if run_label == "full" and not args.confirm_full:
        msg = "ABORTED: --run-label=full requires --confirm-full."
        logger.error(msg)
        print(f"ERROR: {msg}")
        sys.exit(1)

    # Load cells.parquet (always the full version — reference product)
    if not CELLS_PQ.exists():
        logger.error(f"cells.parquet not found: {CELLS_PQ}")
        print(f"ERROR: cells.parquet not found: {CELLS_PQ}")
        sys.exit(1)

    cells = pd.read_parquet(CELLS_PQ)
    logger.info(f"Loaded cells.parquet: {len(cells):,} rows")

    # For sample/test100: we need to know which file_ids are in scope
    # to properly subset file-cells and recompute overlap
    if not FC_MANIFEST_PQ.exists():
        logger.error(f"file_cells_manifest not found: {FC_MANIFEST_PQ}")
        print(f"ERROR: file_cells_manifest not found: {FC_MANIFEST_PQ}")
        sys.exit(1)

    fc_manifest = pd.read_parquet(FC_MANIFEST_PQ)
    fc_manifest = fc_manifest[fc_manifest["status"] == "ok"].copy()
    logger.info(f"Loaded file_cells_manifest: {len(fc_manifest)} ok files")

    # Select files to process
    to_process = fc_manifest.copy()

    if args.sample_n_files is not None:
        n = min(args.sample_n_files, len(to_process))
        to_process = to_process.sample(n=n, random_state=42)
        logger.info(f"Sampled {n} file-cell files")

    if args.limit_files is not None:
        to_process = to_process.head(args.limit_files)
        logger.info(f"Limited to first {len(to_process)} file-cell files")

    if len(to_process) == 0:
        logger.info("No files to process.")
        print("No files to process.")
        return

    # Resolve output paths
    paths = get_output_paths(run_label, cell_size)

    # Config summary
    summary = (
        f"\n{'=' * 60}\n"
        f"  CONFIG SUMMARY\n"
        f"{'=' * 60}\n"
        f"  cells_parquet:        {CELLS_PQ}\n"
        f"  fc_manifest:          {FC_MANIFEST_PQ}\n"
        f"  total ok files:       {len(fc_manifest)}\n"
        f"  selected files:       {len(to_process)}\n"
        f"  cell_size:            {cell_size} ({cell_deg:.6f} deg)\n"
        f"  run_label:            {run_label}\n"
        f"  output_dir:           {paths['out_dir']}\n"
        f"  confirm_full:         {args.confirm_full}\n"
        f"  estimate_only:        {args.estimate_only}\n"
        f"  backend:              pandas\n"
        f"{'=' * 60}"
    )
    logger.info(summary)
    print(summary)

    if args.estimate_only:
        estimate_only(to_process, cells, paths["out_dir"], cell_size, logger)
        return

    # Check overwrite
    if not args.overwrite and paths["residuals_pq"].exists():
        msg = f"Output already exists: {paths['residuals_pq']}. Use --overwrite to replace."
        logger.error(msg)
        print(f"ERROR: {msg}")
        sys.exit(1)

    t_start = datetime.now()

    # Step 1: Read file-cell parquets
    logger.info("Step 1: Reading file-cell parquets...")
    fc, read_errors = read_file_cells(to_process, logger)

    if len(fc) == 0:
        logger.error("No file-cell data read. Aborting.")
        print("ERROR: No file-cell data read.")
        write_errors_tsv(read_errors, errors_tsv, logger)
        return

    n_total_fc_rows = len(fc)
    logger.info(f"Input: {n_total_fc_rows:,} file-cell rows from {len(to_process)} files")

    # Step 2: Determine overlap cells
    logger.info("Step 2: Identifying overlap cells...")

    if run_label == "full":
        cells_ref = cells
    else:
        # For sample/test100: reference cells.parquet for file-balanced median,
        # but only for cells present in our selected file-cells.
        # Overlap is still defined by cells.n_file_cells > 1 from the global product.
        sample_cell_ids = set(fc["cell_id"].unique())
        cells_ref = cells[cells["cell_id"].isin(sample_cell_ids)].copy()
        logger.info(
            f"  Sample/test mode: {len(sample_cell_ids):,} unique cells in sample, "
            f"referencing cells.parquet for overlap (n_file_cells > 1)"
        )

    # Step 3: Compute residuals
    logger.info("Step 3: Computing residuals...")
    residuals = compute_residuals(fc, cells_ref, logger)

    if len(residuals) == 0:
        logger.warning("No overlap file-cells found. Writing empty outputs.")
        # Write empty outputs
        paths["out_dir"].mkdir(parents=True, exist_ok=True)
        empty_df = pd.DataFrame()
        for key in ["residuals_pq", "file_bias_pq", "cruise_bias_pq", "subzip_bias_pq",
                     "suspicious_cells_pq"]:
            p = paths[key]
            tmp = p.with_suffix(".parquet.tmp")
            empty_df.to_parquet(tmp, index=False)
            os.replace(tmp, p)
        for key in ["file_bias_tsv", "cruise_bias_tsv", "subzip_bias_tsv",
                     "suspicious_files_tsv", "suspicious_cruises_tsv", "suspicious_cells_tsv"]:
            p = paths[key]
            tmp = p.with_suffix(".tsv.tmp")
            empty_df.to_csv(tmp, sep="\t", index=False)
            os.replace(tmp, p)
        write_errors_tsv(read_errors, errors_tsv, logger)
        logger.info("Done (empty outputs).")
        return

    n_overlap_fc_rows = len(residuals)
    overlap_cell_ids = set(residuals["cell_id"].unique())
    n_overlap_cells = len(overlap_cell_ids)
    n_multi_cruise = int(residuals.groupby("cell_id")["is_multi_cruise"].first().sum())

    logger.info(f"  Overlap file-cell rows: {n_overlap_fc_rows:,}")
    logger.info(f"  Overlap cells: {n_overlap_cells:,}")
    logger.info(f"  Multi-cruise overlap cells: {n_multi_cruise:,}")

    # Step 4: Aggregate by file
    logger.info("Step 4: Aggregating bias by file...")
    file_bias = aggregate_bias_by_group(residuals, "file_id", logger)

    # Step 5: Aggregate by cruise
    logger.info("Step 5: Aggregating bias by cruise...")
    cruise_bias = aggregate_bias_by_group(residuals, "cruise_id_guess", logger)

    # Step 6: Aggregate by subzip
    logger.info("Step 6: Aggregating bias by subzip...")
    subzip_bias = aggregate_bias_by_group(residuals, "subzip_id", logger)

    # Step 7: Cell-level residuals
    logger.info("Step 7: Computing cell-level residuals...")
    cell_stats = compute_cell_residuals(residuals, logger)

    # Step 8: Flag suspicious
    logger.info("Step 8: Flagging suspicious files/cruises/cells...")
    suspicious_files = flag_suspicious_files(file_bias)
    suspicious_cruises = flag_suspicious_cruises(cruise_bias)
    suspicious_cells = flag_suspicious_cells(cell_stats)

    logger.info(f"  Suspicious files: {len(suspicious_files):,}")
    logger.info(f"  Suspicious cruises: {len(suspicious_cruises):,}")
    logger.info(f"  Suspicious cells: {len(suspicious_cells):,}")

    # Step 9: Write outputs
    logger.info("Step 9: Writing outputs...")
    paths["out_dir"].mkdir(parents=True, exist_ok=True)

    # Select output columns for residuals
    residual_cols = [
        "cell_id", "file_id", "subzip_id", "cruise_id_guess",
        "median_depth_m_positive_down", "median_elev_m",
        "median_depth_file_balanced", "median_elev_file_balanced",
        "residual_depth_m", "residual_elev_m",
        "is_multi_cruise", "n_points",
    ]
    # Only include columns that exist
    out_residual_cols = [c for c in residual_cols if c in residuals.columns]
    residuals_out = residuals[out_residual_cols].copy()
    atomic_write_parquet(residuals_out, paths["residuals_pq"], logger)

    atomic_write_parquet(file_bias, paths["file_bias_pq"], logger)
    atomic_write_tsv(file_bias, paths["file_bias_tsv"], logger)

    atomic_write_parquet(cruise_bias, paths["cruise_bias_pq"], logger)
    atomic_write_tsv(cruise_bias, paths["cruise_bias_tsv"], logger)

    atomic_write_parquet(subzip_bias, paths["subzip_bias_pq"], logger)
    atomic_write_tsv(subzip_bias, paths["subzip_bias_tsv"], logger)

    atomic_write_tsv(suspicious_files, paths["suspicious_files_tsv"], logger)
    logger.info(f"  Suspicious files: {len(suspicious_files):,}")

    atomic_write_tsv(suspicious_cruises, paths["suspicious_cruises_tsv"], logger)
    logger.info(f"  Suspicious cruises: {len(suspicious_cruises):,}")

    atomic_write_parquet(suspicious_cells, paths["suspicious_cells_pq"], logger)
    atomic_write_tsv(suspicious_cells, paths["suspicious_cells_tsv"], logger)

    write_errors_tsv(read_errors, errors_tsv, logger)

    t_end = datetime.now()
    elapsed_s = (t_end - t_start).total_seconds()

    # Step 10: Write report
    logger.info("Step 10: Writing report...")
    write_report(
        report_path=paths["report_path"],
        residuals=residuals,
        file_bias=file_bias,
        cruise_bias=cruise_bias,
        subzip_bias=subzip_bias,
        suspicious_files=suspicious_files,
        suspicious_cruises=suspicious_cruises,
        suspicious_cells=suspicious_cells,
        n_fc_files=len(to_process),
        n_total_fc_rows=n_total_fc_rows,
        n_overlap_fc_rows=n_overlap_fc_rows,
        n_overlap_cells=n_overlap_cells,
        n_multi_cruise_cells=n_multi_cruise,
        n_read_errors=len(read_errors),
        run_label=run_label,
        cell_size=cell_size,
        elapsed_s=elapsed_s,
        logger=logger,
    )

    # Final summary
    rd = residuals["residual_depth_m"]
    re = residuals["residual_elev_m"]
    elev_check = float((re + rd).abs().max())

    report = f"""
{'=' * 60}
  RUN REPORT — 05_analyze_cell_overlap_bias.py
{'=' * 60}
  run_label:               {run_label}
  cell_size:               {cell_size} ({cell_deg:.6f} deg)
  output_dir:              {paths['out_dir']}

  Input file-cell files:   {len(to_process)}
  Input file-cell rows:    {n_total_fc_rows:,}
  Read errors:             {len(read_errors)}

  Overlap file-cell rows:  {n_overlap_fc_rows:,}
  Overlap cells:           {n_overlap_cells:,}
  Multi-cruise overlap:    {n_multi_cruise:,}

  residual_depth_m:
    min:     {float(rd.min()):.4f}
    median:  {float(rd.median()):.4f}
    MAD:     {float((rd - rd.median()).abs().median()):.4f}
    p95:     {float(rd.quantile(0.95)):.4f}
    max:     {float(rd.max()):.4f}

  file_bias_summary rows:     {len(file_bias):,}
  cruise_bias_summary rows:   {len(cruise_bias):,}
  subzip_bias_summary rows:   {len(subzip_bias):,}

  suspicious_files:           {len(suspicious_files):,}
  suspicious_cruises:         {len(suspicious_cruises):,}
  suspicious_cells:           {len(suspicious_cells):,}

  residual_elev ≈ -residual_depth:  max |elev + depth| = {elev_check:.2e}

  Elapsed:                 {elapsed_s:.1f}s
  Backend:                 pandas
{'=' * 60}
"""
    logger.info(report)
    print(report)


if __name__ == "__main__":
    main()
