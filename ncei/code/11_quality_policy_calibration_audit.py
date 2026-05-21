#!/usr/bin/env python3
"""
11_quality_policy_calibration_audit.py

Step 06A — Quality policy calibration audit for NCEI branch-cell products.

This is an evidence-generation and candidate-policy stage only. It consumes
Step 04B/05A/05B outputs, stratifies within-branch and cross-branch residuals,
and proposes human-review candidate rules. It does not create validation cells,
merge branches, define final tiers, add exclude flags to cell products, or read
point-level data / external grids.

Inputs (read-only):
  - ncei/manifests/cells_1min_manifest.parquet
  - ncei/manifests/bathymetry_entry_manifest_supplementary.parquet
  - ncei/derived/{singlebeam,multibeam,regional_mrar}/cells_1min/ hive datasets
  - ncei/derived/overlap_bias_1min/source_specific_overlap_residuals.parquet
  - ncei/derived/overlap_bias_1min/track_bias_summary.parquet
  - ncei/derived/overlap_bias_1min/branch_overlap_summary.parquet
  - ncei/derived/cross_branch_overlap_1min/cross_overlap_cells.parquet
  - ncei/derived/cross_branch_overlap_1min/cross_overlap_pair_summary.parquet

Outputs (full mode):
  - ncei/derived/quality_policy_calibration_1min/quality_calibration_by_branch.parquet
  - ncei/derived/quality_policy_calibration_1min/quality_calibration_by_lat_depth.parquet
  - ncei/derived/quality_policy_calibration_1min/quality_calibration_by_source_pair.parquet
  - ncei/derived/quality_policy_calibration_1min/quality_policy_candidate_rules.tsv
  - ncei/docs/step06a_quality_policy_calibration_report.md
  - ncei/output/logs/11_quality_policy_calibration_audit.log

Sample/test100 modes write to suffixed output directories and report/log
filenames. Always run from repo root (/mnt/data2/00-Data/ship).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent          # ncei/
REPO_ROOT = ROOT_DIR.parent           # ship/

MANIFEST_DIR = ROOT_DIR / "manifests"
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"
DERIVED_DIR = ROOT_DIR / "derived"

CELLS_MANIFEST = MANIFEST_DIR / "cells_1min_manifest.parquet"
SUPPLEMENTARY_MANIFEST = MANIFEST_DIR / "bathymetry_entry_manifest_supplementary.parquet"
OVERLAP_DIR = DERIVED_DIR / "overlap_bias_1min"
CROSS_OVERLAP_DIR = DERIVED_DIR / "cross_branch_overlap_1min"
WITHIN_RESIDUALS = OVERLAP_DIR / "source_specific_overlap_residuals.parquet"
TRACK_BIAS_SUMMARY = OVERLAP_DIR / "track_bias_summary.parquet"
BRANCH_OVERLAP_SUMMARY = OVERLAP_DIR / "branch_overlap_summary.parquet"
CROSS_OVERLAP_CELLS = CROSS_OVERLAP_DIR / "cross_overlap_cells.parquet"
CROSS_PAIR_SUMMARY = CROSS_OVERLAP_DIR / "cross_overlap_pair_summary.parquet"

VALID_RUN_LABELS = ("sample", "test100", "full")
BRANCHES = ("singlebeam", "multibeam_ncei", "regional_mrar")
PAIR_LABELS = ("mb_vs_mrar", "mb_vs_sb", "mrar_vs_sb")
POLICY_CALIBRATION_VERSION = "ncei_policy_calib_v0.1.0"

# Fixed calibration bins from the brief. Do not change without a new policy
# calibration version.
LAT_BANDS = [-90, -80, -70, -60, -50, -40, -30, -20, -10, 0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
DEPTH_BINS = [0, 200, 500, 2000, 4000, 6000, 11500]
DUP_RATIO_BINS = [0.0, 0.01, 0.1, 0.5, 1.0]
N_UNIQUE_TRIPLES_BINS = [1, 10, 100, 1000, 10000, float("inf")]
N_TRACK_CELLS_BINS = [1, 2, 5, 20, float("inf")]
MANUAL_REVIEW_SHARE_BINS = [0.0, 0.001, 0.01, 0.1, 1.0]

BRANCH_DERIVED_DIRS = {
    "singlebeam": DERIVED_DIR / "singlebeam",
    "multibeam_ncei": DERIVED_DIR / "multibeam",
    "regional_mrar": DERIVED_DIR / "regional_mrar",
}

BRANCH_CELL_COLUMNS = [
    "branch",
    "cell_id",
    "lon_bin",
    "lat_bin",
    "lon_center",
    "lat_center",
    "n_track_cells",
    "n_tracks",
    "n_points_pass_total",
    "n_unique_triples_total",
    "duplicate_ratio_cell",
    "median_depth_m",
    "manual_review_any",
    "manual_review_unique_triples_share",
    "lat_band_10deg",
]

WITHIN_COLUMNS = [
    "branch",
    "cell_id",
    "lat_center",
    "branch_cell_median_depth_m",
    "branch_cell_n_track_cells",
    "residual_m",
    "abs_residual_m",
]

CROSS_COLUMNS = [
    "pair_label",
    "left_branch",
    "right_branch",
    "cell_id",
    "lat_center",
    "left_median_depth_m",
    "right_median_depth_m",
    "residual_m",
    "abs_residual_m",
    "left_n_track_cells",
    "right_n_track_cells",
    "left_n_unique_triples_total",
    "right_n_unique_triples_total",
    "left_duplicate_ratio_cell",
    "right_duplicate_ratio_cell",
    "left_manual_review_any",
    "right_manual_review_any",
]

BRANCH_OUTPUT_COLUMNS = [
    "branch",
    "n_cells_total",
    "n_cells_with_within_branch_overlap",
    "n_cells_with_cross_branch_overlap_any",
    "n_cells_no_overlap_evidence",
    "share_with_overlap_evidence",
    "within_branch_rmse_m",
    "cross_branch_rmse_m_avg",
    "abs_residual_p95_within_branch",
    "abs_residual_p95_cross_branch_max",
    "manual_review_cell_share",
    "auv_sentry_cell_count",
    "headline_finding",
    "policy_calibration_version",
]

LAT_DEPTH_OUTPUT_COLUMNS = [
    "branch",
    "lat_band_10deg",
    "depth_bin_lo",
    "depth_bin_hi",
    "n_cells",
    "n_cells_with_overlap",
    "within_branch_residual_p50",
    "within_branch_residual_p95",
    "within_branch_residual_p99",
    "cross_branch_residual_max_p95",
    "cross_branch_n_overlap_total",
    "auv_sentry_cell_count_local",
    "manual_review_share_local",
    "policy_calibration_version",
]

SOURCE_PAIR_OUTPUT_COLUMNS = [
    "pair_label",
    "dup_bin_lo",
    "dup_bin_hi",
    "n_unique_lo",
    "n_unique_hi",
    "n_cells_in_slice",
    "residual_p50",
    "residual_p95",
    "residual_p99",
    "abs_residual_p50",
    "abs_residual_p95",
    "abs_residual_p99",
    "rmse",
    "policy_calibration_version",
]

CANDIDATE_RULE_COLUMNS = [
    "rule_id",
    "candidate_tier",
    "applies_to_branch",
    "applies_to_lat_band_filter",
    "applies_to_depth_bin_filter",
    "condition",
    "recommended_weight",
    "requires_step05_overlap",
    "exclude_from_primary",
    "evidence_basis",
    "notes",
]


# ---------------------------------------------------------------------------
# Path / logging / atomic-write helpers
# ---------------------------------------------------------------------------
def suffix_for_run(run_label: str) -> str:
    return "" if run_label == "full" else f"_{run_label}"


def output_dir_for_run(run_label: str) -> Path:
    return DERIVED_DIR / f"quality_policy_calibration_1min{suffix_for_run(run_label)}"


def get_output_paths(run_label: str) -> dict[str, Path]:
    suffix = suffix_for_run(run_label)
    out_dir = output_dir_for_run(run_label)
    return {
        "out_dir": out_dir,
        "by_branch_pq": out_dir / "quality_calibration_by_branch.parquet",
        "by_lat_depth_pq": out_dir / "quality_calibration_by_lat_depth.parquet",
        "by_source_pair_pq": out_dir / "quality_calibration_by_source_pair.parquet",
        "candidate_rules_tsv": out_dir / "quality_policy_candidate_rules.tsv",
        "report_md": DOCS_DIR / f"step06a_quality_policy_calibration_report{suffix}.md",
        "log": LOG_DIR / f"11_quality_policy_calibration_audit{suffix}.log",
    }


def branch_cells_dir(branch: str) -> Path:
    return BRANCH_DERIVED_DIRS[branch] / "cells_1min"


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
    logger = logging.getLogger("ncei_quality_policy_calibration")
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
# Generic statistics / binning helpers
# ---------------------------------------------------------------------------
def safe_quantile(values: pd.Series, q: float) -> float:
    s = pd.to_numeric(values, errors="coerce").dropna()
    if s.empty:
        return float("nan")
    return float(s.quantile(q))


def safe_rmse(values: pd.Series) -> float:
    s = pd.to_numeric(values, errors="coerce").dropna()
    if s.empty:
        return float("nan")
    arr = s.to_numpy(dtype=np.float64)
    return float(np.sqrt(np.mean(arr * arr)))


def compute_lat_band(lat_center: pd.Series) -> pd.Series:
    band = (np.floor(pd.to_numeric(lat_center, errors="coerce").astype(float) / 10.0) * 10.0)
    band = band.clip(lower=-90, upper=80)
    return band.astype("Int64")


def right_open_bin_frame(values: pd.Series, bins: list[float]) -> pd.DataFrame:
    """Return lo/hi columns for fixed right-open bins with final bin closed.

    This mirrors pd.cut(..., right=False) while explicitly assigning the
    rightmost edge (for example 1.0 in duplicate-ratio bins) to the final bin.
    """
    arr = pd.to_numeric(values, errors="coerce").to_numpy(dtype=np.float64)
    edges = np.asarray(bins, dtype=np.float64)
    idx = np.searchsorted(edges, arr, side="right") - 1
    idx = np.where(np.isnan(arr), -1, idx)
    idx = np.clip(idx, 0, len(edges) - 2)
    lo = np.where(np.isnan(arr), np.nan, edges[idx])
    hi = np.where(np.isnan(arr), np.nan, edges[idx + 1])
    return pd.DataFrame({"lo": lo, "hi": hi}, index=values.index)


def add_depth_bins(df: pd.DataFrame, depth_col: str) -> pd.DataFrame:
    out = df.copy()
    bins = right_open_bin_frame(out[depth_col].clip(lower=0.0, upper=11500.0), DEPTH_BINS)
    out["depth_bin_lo"] = bins["lo"]
    out["depth_bin_hi"] = bins["hi"]
    return out


def ensure_columns(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = pd.NA
    return out[list(columns)]


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
        vals: list[str] = []
        for col in cols:
            val = row[col]
            if isinstance(val, (float, np.floating)):
                vals.append(f"{val:.4f}" if np.isfinite(val) else "")
            elif pd.isna(val):
                vals.append("")
            else:
                vals.append(str(val))
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    return lines


def sample_df_by_strata(df: pd.DataFrame, run_label: str, strata_cols: list[str]) -> pd.DataFrame:
    if run_label == "full" or df.empty:
        return df
    n_per_group = 200 if run_label == "sample" else 1000
    if not all(col in df.columns for col in strata_cols):
        return df.head(50_000 if run_label == "sample" else 200_000).copy()
    return (
        df.sort_values(strata_cols + ["cell_id"] if "cell_id" in df.columns else strata_cols)
        .groupby(strata_cols, dropna=False, group_keys=False)
        .head(n_per_group)
        .reset_index(drop=True)
    )


def sample_df_by_pair(df: pd.DataFrame, run_label: str) -> pd.DataFrame:
    if run_label == "full" or df.empty or "pair_label" not in df.columns:
        return df
    n_per_pair = 50_000 if run_label == "sample" else 200_000
    return (
        df.sort_values(["pair_label", "cell_id"] if "cell_id" in df.columns else ["pair_label"])
        .groupby("pair_label", group_keys=False)
        .head(n_per_pair)
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------
def read_required_parquet(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required input not found: {path}")
    if columns is None:
        return pd.read_parquet(path)
    schema_names = set(pq.read_schema(path).names)
    read_cols = [col for col in columns if col in schema_names]
    missing = [col for col in columns if col not in schema_names]
    if missing:
        raise ValueError(f"{path} missing required columns: {missing}")
    return pd.read_parquet(path, columns=read_cols)


def read_branch_cells(branch: str, run_label: str, logger: logging.Logger) -> pd.DataFrame:
    path = branch_cells_dir(branch)
    if not path.exists():
        raise FileNotFoundError(f"Step 04B cells dataset not found for {branch}: {path}")
    dataset = ds.dataset(str(path), format="parquet", partitioning="hive")
    names = set(dataset.schema.names)
    required = [c for c in BRANCH_CELL_COLUMNS if c != "lat_band_10deg"]
    missing = [c for c in required if c not in names]
    if missing:
        raise ValueError(f"{path} missing Step 04B columns: {missing}")
    read_cols = [c for c in BRANCH_CELL_COLUMNS if c in names]
    table = dataset.to_table(columns=read_cols)
    df = table.to_pandas()
    if "lat_band_10deg" not in df.columns:
        df["lat_band_10deg"] = compute_lat_band(df["lat_center"])
    df["branch"] = df["branch"].astype(str)
    if sorted(df["branch"].unique().tolist()) != [branch]:
        raise ValueError(f"{branch}: hive read returned unexpected branch values")
    df = ensure_columns(df, BRANCH_CELL_COLUMNS)
    df = add_depth_bins(df, "median_depth_m")
    df = sample_df_by_strata(df, run_label, ["lat_band_10deg", "depth_bin_lo", "depth_bin_hi"])
    logger.info("%s: loaded %d Step 04B cells for %s run", branch, len(df), run_label)
    return df


def read_all_branch_cells(run_label: str, logger: logging.Logger) -> dict[str, pd.DataFrame]:
    return {branch: read_branch_cells(branch, run_label, logger) for branch in BRANCHES}


def read_within_residuals(run_label: str, logger: logging.Logger) -> pd.DataFrame:
    df = read_required_parquet(WITHIN_RESIDUALS, WITHIN_COLUMNS)
    df["lat_band_10deg"] = compute_lat_band(df["lat_center"])
    df = add_depth_bins(df, "branch_cell_median_depth_m")
    df = sample_df_by_strata(df, run_label, ["branch", "lat_band_10deg", "depth_bin_lo", "depth_bin_hi"])
    logger.info("Loaded %d within-branch residual rows", len(df))
    return df


def read_cross_cells(run_label: str, logger: logging.Logger) -> pd.DataFrame:
    df = read_required_parquet(CROSS_OVERLAP_CELLS, CROSS_COLUMNS)
    df = sample_df_by_pair(df, run_label)
    df["pair_label"] = df["pair_label"].astype(str)
    df["abs_residual_m"] = pd.to_numeric(df["abs_residual_m"], errors="coerce")
    logger.info("Loaded %d cross-branch overlap rows", len(df))
    return df


# ---------------------------------------------------------------------------
# Evidence table builders
# ---------------------------------------------------------------------------
def branch_total_from_manifest(cells_manifest: pd.DataFrame, branch: str, fallback: int) -> int:
    row = cells_manifest[cells_manifest["branch"].astype(str) == branch]
    if not row.empty:
        for col in ("n_cells_total", "n_branch_cells_total"):
            if col in row.columns and pd.notna(row.iloc[0][col]):
                return int(row.iloc[0][col])
    return int(fallback)


def count_cross_overlap_cells_by_branch(cross_cells: pd.DataFrame) -> dict[str, int]:
    out: dict[str, set[str]] = {branch: set() for branch in BRANCHES}
    for _, row in cross_cells.iterrows():
        left = str(row["left_branch"])
        right = str(row["right_branch"])
        cell_id = str(row["cell_id"])
        if left in out:
            out[left].add(cell_id)
        if right in out:
            out[right].add(cell_id)
    return {branch: len(ids) for branch, ids in out.items()}


def cross_pair_stats_by_branch(cross_pair_summary: pd.DataFrame) -> dict[str, dict[str, float]]:
    stats = {branch: {"rmse_avg": float("nan"), "p95_max": float("nan")} for branch in BRANCHES}
    for branch in BRANCHES:
        mask = (cross_pair_summary["left_branch"].astype(str) == branch) | (cross_pair_summary["right_branch"].astype(str) == branch)
        sub = cross_pair_summary[mask]
        if not sub.empty:
            stats[branch] = {
                "rmse_avg": float(pd.to_numeric(sub["rmse_pair_m"], errors="coerce").mean()),
                "p95_max": float(pd.to_numeric(sub["abs_residual_p95"], errors="coerce").max()),
            }
    return stats


def headline_for_branch(branch: str, within_p95: float, cross_p95: float) -> str:
    if branch == "multibeam_ncei":
        return "Tight within-branch; cross-source agreement good vs M.rar but noisy vs singlebeam"
    if branch == "singlebeam":
        return "Broad global coverage; quality must stratify by latitude/depth and overlap evidence"
    if branch == "regional_mrar":
        return "Regional processed product; usable for sensitivity/cross-validation, not default primary"
    return f"within_p95={within_p95:.1f} cross_p95={cross_p95:.1f}"


def build_by_branch(
    cells_manifest: pd.DataFrame,
    branch_cells: dict[str, pd.DataFrame],
    branch_overlap_summary: pd.DataFrame,
    cross_pair_summary: pd.DataFrame,
    cross_cells: pd.DataFrame,
) -> pd.DataFrame:
    cross_counts = count_cross_overlap_cells_by_branch(cross_cells)
    cross_stats = cross_pair_stats_by_branch(cross_pair_summary)
    rows: list[dict] = []
    for branch in BRANCHES:
        cells = branch_cells[branch]
        total = branch_total_from_manifest(cells_manifest, branch, len(cells))
        within_overlap = int((pd.to_numeric(cells["n_track_cells"], errors="coerce") >= 2).sum())
        cross_any = int(cross_counts.get(branch, 0))
        # Approximate union overlap evidence with the sum capped at total. This is
        # conservative when within/cross overlap sets intersect and avoids reading
        # more than the allowed Step 04B/05 inputs.
        overlap_any = min(total, within_overlap + cross_any)
        no_overlap = max(0, total - overlap_any)
        manual_share = float(pd.to_numeric(cells["manual_review_any"], errors="coerce").fillna(False).mean()) if len(cells) else float("nan")
        br = branch_overlap_summary[branch_overlap_summary["branch"].astype(str) == branch]
        within_rmse = float(br["rmse_residual_m_branch"].iloc[0]) if not br.empty and "rmse_residual_m_branch" in br else float("nan")
        within_p95 = float(br["abs_residual_p95"].iloc[0]) if not br.empty and "abs_residual_p95" in br else float("nan")
        sentry_proxy = 0
        if branch == "multibeam_ncei":
            sentry_proxy = int(((cells["manual_review_any"].fillna(False).astype(bool)) & (pd.to_numeric(cells["duplicate_ratio_cell"], errors="coerce") > 0.5)).sum())
            if sentry_proxy == 0:
                sentry_proxy = int((pd.to_numeric(cells["duplicate_ratio_cell"], errors="coerce") > 0.5).sum())
        rows.append(
            {
                "branch": branch,
                "n_cells_total": total,
                "n_cells_with_within_branch_overlap": within_overlap,
                "n_cells_with_cross_branch_overlap_any": cross_any,
                "n_cells_no_overlap_evidence": no_overlap,
                "share_with_overlap_evidence": float(overlap_any / total) if total else float("nan"),
                "within_branch_rmse_m": within_rmse,
                "cross_branch_rmse_m_avg": cross_stats[branch]["rmse_avg"],
                "abs_residual_p95_within_branch": within_p95,
                "abs_residual_p95_cross_branch_max": cross_stats[branch]["p95_max"],
                "manual_review_cell_share": manual_share,
                "auv_sentry_cell_count": sentry_proxy,
                "headline_finding": headline_for_branch(branch, within_p95, cross_stats[branch]["p95_max"]),
                "policy_calibration_version": POLICY_CALIBRATION_VERSION,
            }
        )
    return ensure_columns(pd.DataFrame(rows), BRANCH_OUTPUT_COLUMNS)


def within_stats_by_lat_depth(within_residuals: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    if within_residuals.empty:
        return pd.DataFrame(columns=["branch", "lat_band_10deg", "depth_bin_lo", "depth_bin_hi", "within_branch_residual_p50", "within_branch_residual_p95", "within_branch_residual_p99"])
    for keys, sub in within_residuals.groupby(["branch", "lat_band_10deg", "depth_bin_lo", "depth_bin_hi"], dropna=False, sort=True):
        branch, lat_band, depth_lo, depth_hi = keys
        rows.append(
            {
                "branch": branch,
                "lat_band_10deg": int(lat_band) if pd.notna(lat_band) else pd.NA,
                "depth_bin_lo": float(depth_lo),
                "depth_bin_hi": float(depth_hi),
                "within_branch_residual_p50": safe_quantile(sub["abs_residual_m"], 0.50),
                "within_branch_residual_p95": safe_quantile(sub["abs_residual_m"], 0.95),
                "within_branch_residual_p99": safe_quantile(sub["abs_residual_m"], 0.99),
            }
        )
    return pd.DataFrame(rows)


def explode_cross_for_branch_lat_depth(cross_cells: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for side in ("left", "right"):
        branch_col = f"{side}_branch"
        depth_col = f"{side}_median_depth_m"
        sub = cross_cells[["pair_label", branch_col, "lat_center", depth_col, "abs_residual_m"]].copy()
        sub = sub.rename(columns={branch_col: "branch", depth_col: "branch_depth_m"})
        sub["lat_band_10deg"] = compute_lat_band(sub["lat_center"])
        sub = add_depth_bins(sub, "branch_depth_m")
        frames.append(sub)
    return pd.concat(frames, ignore_index=True, copy=False) if frames else pd.DataFrame()


def cross_stats_by_branch_lat_depth(cross_cells: pd.DataFrame) -> pd.DataFrame:
    exploded = explode_cross_for_branch_lat_depth(cross_cells)
    if exploded.empty:
        return pd.DataFrame(columns=["branch", "lat_band_10deg", "depth_bin_lo", "depth_bin_hi", "cross_branch_residual_max_p95", "cross_branch_n_overlap_total"])
    pair_rows: list[dict] = []
    for keys, sub in exploded.groupby(["branch", "lat_band_10deg", "depth_bin_lo", "depth_bin_hi", "pair_label"], dropna=False, sort=True):
        branch, lat_band, depth_lo, depth_hi, pair_label = keys
        pair_rows.append(
            {
                "branch": branch,
                "lat_band_10deg": int(lat_band) if pd.notna(lat_band) else pd.NA,
                "depth_bin_lo": float(depth_lo),
                "depth_bin_hi": float(depth_hi),
                "pair_label": pair_label,
                "p95": safe_quantile(sub["abs_residual_m"], 0.95),
                "n": int(len(sub)),
            }
        )
    pair_df = pd.DataFrame(pair_rows)
    rows: list[dict] = []
    for keys, sub in pair_df.groupby(["branch", "lat_band_10deg", "depth_bin_lo", "depth_bin_hi"], dropna=False, sort=True):
        branch, lat_band, depth_lo, depth_hi = keys
        rows.append(
            {
                "branch": branch,
                "lat_band_10deg": int(lat_band) if pd.notna(lat_band) else pd.NA,
                "depth_bin_lo": float(depth_lo),
                "depth_bin_hi": float(depth_hi),
                "cross_branch_residual_max_p95": float(pd.to_numeric(sub["p95"], errors="coerce").max()),
                "cross_branch_n_overlap_total": int(pd.to_numeric(sub["n"], errors="coerce").sum()),
            }
        )
    return pd.DataFrame(rows)


def build_by_lat_depth(
    branch_cells: dict[str, pd.DataFrame],
    within_residuals: pd.DataFrame,
    cross_cells: pd.DataFrame,
) -> pd.DataFrame:
    base_rows: list[dict] = []
    for branch, cells in branch_cells.items():
        work = cells.copy()
        work["sentry_proxy"] = False
        if branch == "multibeam_ncei":
            work["sentry_proxy"] = pd.to_numeric(work["duplicate_ratio_cell"], errors="coerce") > 0.5
        for keys, sub in work.groupby(["lat_band_10deg", "depth_bin_lo", "depth_bin_hi"], dropna=False, sort=True):
            lat_band, depth_lo, depth_hi = keys
            base_rows.append(
                {
                    "branch": branch,
                    "lat_band_10deg": int(lat_band) if pd.notna(lat_band) else pd.NA,
                    "depth_bin_lo": float(depth_lo),
                    "depth_bin_hi": float(depth_hi),
                    "n_cells": int(len(sub)),
                    "n_cells_with_overlap": int((pd.to_numeric(sub["n_track_cells"], errors="coerce") >= 2).sum()),
                    "auv_sentry_cell_count_local": int(sub["sentry_proxy"].sum()),
                    "manual_review_share_local": float(sub["manual_review_any"].fillna(False).astype(bool).mean()) if len(sub) else float("nan"),
                }
            )
    base = pd.DataFrame(base_rows)
    within = within_stats_by_lat_depth(within_residuals)
    cross = cross_stats_by_branch_lat_depth(cross_cells)
    key = ["branch", "lat_band_10deg", "depth_bin_lo", "depth_bin_hi"]
    out = base.merge(within, on=key, how="left").merge(cross, on=key, how="left")
    out["policy_calibration_version"] = POLICY_CALIBRATION_VERSION
    out = out.sort_values(key).reset_index(drop=True)
    return ensure_columns(out, LAT_DEPTH_OUTPUT_COLUMNS)


def build_by_source_pair(cross_cells: pd.DataFrame) -> pd.DataFrame:
    work = cross_cells.copy()
    work["dup_ratio_either"] = work[["left_duplicate_ratio_cell", "right_duplicate_ratio_cell"]].max(axis=1)
    # "Either" means a high-effective-count cell on either branch can support
    # confidence, so use max(left, right) for the fixed n_unique bins.
    work["n_unique_either"] = work[["left_n_unique_triples_total", "right_n_unique_triples_total"]].max(axis=1)
    dup_bins = right_open_bin_frame(work["dup_ratio_either"].clip(lower=0.0, upper=1.0), DUP_RATIO_BINS)
    uniq_bins = right_open_bin_frame(work["n_unique_either"].clip(lower=1), N_UNIQUE_TRIPLES_BINS)
    work["dup_bin_lo"] = dup_bins["lo"]
    work["dup_bin_hi"] = dup_bins["hi"]
    work["n_unique_lo"] = uniq_bins["lo"]
    work["n_unique_hi"] = uniq_bins["hi"]
    rows: list[dict] = []
    for keys, sub in work.groupby(["pair_label", "dup_bin_lo", "dup_bin_hi", "n_unique_lo", "n_unique_hi"], dropna=False, sort=True):
        pair_label, dup_lo, dup_hi, unique_lo, unique_hi = keys
        rows.append(
            {
                "pair_label": pair_label,
                "dup_bin_lo": float(dup_lo),
                "dup_bin_hi": float(dup_hi),
                "n_unique_lo": float(unique_lo),
                "n_unique_hi": float(unique_hi),
                "n_cells_in_slice": int(len(sub)),
                "residual_p50": safe_quantile(sub["residual_m"], 0.50),
                "residual_p95": safe_quantile(sub["residual_m"], 0.95),
                "residual_p99": safe_quantile(sub["residual_m"], 0.99),
                "abs_residual_p50": safe_quantile(sub["abs_residual_m"], 0.50),
                "abs_residual_p95": safe_quantile(sub["abs_residual_m"], 0.95),
                "abs_residual_p99": safe_quantile(sub["abs_residual_m"], 0.99),
                "rmse": safe_rmse(sub["residual_m"]),
                "policy_calibration_version": POLICY_CALIBRATION_VERSION,
            }
        )
    out = pd.DataFrame(rows).sort_values(["pair_label", "dup_bin_lo", "n_unique_lo"]).reset_index(drop=True)
    return ensure_columns(out, SOURCE_PAIR_OUTPUT_COLUMNS)


# ---------------------------------------------------------------------------
# Candidate rules and report helpers
# ---------------------------------------------------------------------------
def build_candidate_rules() -> pd.DataFrame:
    """Return candidate rules only; these are not final tier definitions."""
    rows = [
        {
            "rule_id": "mb_v0_high_overlap_lowdup",
            "candidate_tier": "high_confidence",
            "applies_to_branch": "multibeam_ncei",
            "applies_to_lat_band_filter": "-80..-70,-30..-20",
            "applies_to_depth_bin_filter": "500..6000",
            "condition": "n_track_cells>=2 AND duplicate_ratio_cell<=0.1 AND mb_vs_mrar same lat/depth slice has abs_residual_p95<175m",
            "recommended_weight": 0.95,
            "requires_step05_overlap": True,
            "exclude_from_primary": False,
            "evidence_basis": "Step05A mb within-branch RMSE ~55m; Step05B mb_vs_mrar RMSE ~95m / p95 ~165m, with lat=-70 rmse ~92m.",
            "notes": "Candidate high-confidence anchor where multibeam is cross-validated against M.rar; human review must confirm accepted lat/depth slices.",
        },
        {
            "rule_id": "mb_v0_singletrack_lowdup",
            "candidate_tier": "medium_confidence",
            "applies_to_branch": "multibeam_ncei",
            "applies_to_lat_band_filter": "*",
            "applies_to_depth_bin_filter": "*",
            "condition": "n_track_cells==1 AND duplicate_ratio_cell<=0.1 AND n_unique_triples_total>=100",
            "recommended_weight": 0.75,
            "requires_step05_overlap": False,
            "exclude_from_primary": False,
            "evidence_basis": "Most mb cells are single-track, but low duplicate ratio and high effective count reduce AUV duplication risk.",
            "notes": "No within-cell overlap evidence; prefer cross-branch evidence if available.",
        },
        {
            "rule_id": "mb_v0_highdup_sentry_downweight",
            "candidate_tier": "medium_confidence",
            "applies_to_branch": "multibeam_ncei",
            "applies_to_lat_band_filter": "*",
            "applies_to_depth_bin_filter": "*",
            "condition": "duplicate_ratio_cell>0.5 AND n_unique_triples_total>=100",
            "recommended_weight": 0.55,
            "requires_step05_overlap": False,
            "exclude_from_primary": False,
            "evidence_basis": "Step04/05 show AUV-Sentry-like duplicate_ratio>0.5 cells can have elevated residual tails; duplicates should downweight, not exclude.",
            "notes": "AUV-Sentry proxy only; this audit does not consume Step04A per-file-cell track_id by design.",
        },
        {
            "rule_id": "sb_v0_lowlat_shallow_overlap_high",
            "candidate_tier": "high_confidence",
            "applies_to_branch": "singlebeam",
            "applies_to_lat_band_filter": "-50..50",
            "applies_to_depth_bin_filter": "0..2000",
            "condition": "n_track_cells>=2 AND n_unique_triples_total>=10 AND duplicate_ratio_cell<=0.1 AND within/cross slice abs_residual_p95<200m",
            "recommended_weight": 0.85,
            "requires_step05_overlap": True,
            "exclude_from_primary": False,
            "evidence_basis": "Singlebeam must be stratified; lower-latitude/shallow slices are expected to avoid the Southern Ocean high-noise tail.",
            "notes": "Final thresholds require human inspection of quality_calibration_by_lat_depth.parquet.",
        },
        {
            "rule_id": "sb_v0_lowlat_deep_overlap_medium",
            "candidate_tier": "medium_confidence",
            "applies_to_branch": "singlebeam",
            "applies_to_lat_band_filter": "-50..50",
            "applies_to_depth_bin_filter": "2000..6000",
            "condition": "n_track_cells>=2 AND n_unique_triples_total>=10 AND within_branch_abs_residual_p95<300m",
            "recommended_weight": 0.65,
            "requires_step05_overlap": True,
            "exclude_from_primary": False,
            "evidence_basis": "Step05A singlebeam within-branch p95 is ~187m globally, but cross-source p95 is much larger and requires slice-specific calibration.",
            "notes": "Use for supplementary validation until cross-source agreement is regionally accepted.",
        },
        {
            "rule_id": "sb_v0_southern_ocean_review",
            "candidate_tier": "review_or_sensitivity_only",
            "applies_to_branch": "singlebeam",
            "applies_to_lat_band_filter": "-70..-50",
            "applies_to_depth_bin_filter": "*",
            "condition": "lat_band_10deg IN {-70,-60,-50} AND (cross_branch_abs_residual_p99>1000m OR no cross_branch_overlap)",
            "recommended_weight": 0.25,
            "requires_step05_overlap": False,
            "exclude_from_primary": False,
            "evidence_basis": "Step05B mb_vs_sb lat=-60 p99 ~3227m; global uniform thresholds are unsafe.",
            "notes": "Do not automatically exclude; reserve for sensitivity analyses or manual regional review.",
        },
        {
            "rule_id": "sb_v0_no_overlap_low",
            "candidate_tier": "low_confidence",
            "applies_to_branch": "singlebeam",
            "applies_to_lat_band_filter": "*",
            "applies_to_depth_bin_filter": "*",
            "condition": "n_track_cells==1 AND not in any Step05B cross-branch overlap",
            "recommended_weight": 0.35,
            "requires_step05_overlap": False,
            "exclude_from_primary": False,
            "evidence_basis": "Cells without within-branch or cross-branch overlap have no direct evidence to verify them.",
            "notes": "low_evidence: no overlap to verify; keep as coverage but not high-confidence validation.",
        },
        {
            "rule_id": "any_v0_low_unique_low",
            "candidate_tier": "low_confidence",
            "applies_to_branch": "*",
            "applies_to_lat_band_filter": "*",
            "applies_to_depth_bin_filter": "*",
            "condition": "n_unique_triples_total<10",
            "recommended_weight": 0.30,
            "requires_step05_overlap": False,
            "exclude_from_primary": False,
            "evidence_basis": "Effective observation count below 10 is sparse regardless of branch.",
            "notes": "Branch-specific exceptions require human review.",
        },
        {
            "rule_id": "any_v0_overlap_both_high",
            "candidate_tier": "high_confidence",
            "applies_to_branch": "*",
            "applies_to_lat_band_filter": "*",
            "applies_to_depth_bin_filter": "*",
            "condition": "n_track_cells>=2 AND in Step05B cross-branch pair with same-slice abs_residual_p95<150m AND duplicate_ratio_cell<=0.1",
            "recommended_weight": 0.90,
            "requires_step05_overlap": True,
            "exclude_from_primary": False,
            "evidence_basis": "Cells with both within-branch and cross-branch support are the strongest candidates for primary validation.",
            "notes": "Future Step06B should materialize evidence_class='both'.",
        },
        {
            "rule_id": "manual_review_not_exclusion",
            "candidate_tier": "medium_confidence",
            "applies_to_branch": "*",
            "applies_to_lat_band_filter": "*",
            "applies_to_depth_bin_filter": "*",
            "condition": "manual_review_any=True AND within/cross residual evidence remains acceptable for that lat/depth slice",
            "recommended_weight": 0.60,
            "requires_step05_overlap": True,
            "exclude_from_primary": False,
            "evidence_basis": "Manual review flag alone is informational; Step05B manual_review_either=True slices were not universally worse.",
            "notes": "Never use manual_review_any=True by itself as a drop/exclude rule.",
        },
        {
            "rule_id": "mrar_v0_default_sensitivity",
            "candidate_tier": "review_or_sensitivity_only",
            "applies_to_branch": "regional_mrar",
            "applies_to_lat_band_filter": "*",
            "applies_to_depth_bin_filter": "*",
            "condition": "regional_mrar cell unless cross-validated by mb_vs_mrar same lat/depth slice with rmse<150m",
            "recommended_weight": 0.20,
            "requires_step05_overlap": False,
            "exclude_from_primary": True,
            "evidence_basis": "M.rar is a processed regional product with unresolved provenance; mrar_vs_sb p99 is large globally.",
            "notes": "Default branch_role should be regional/sensitivity, not primary validation.",
        },
        {
            "rule_id": "mrar_v0_crossvalidated_medium",
            "candidate_tier": "medium_confidence",
            "applies_to_branch": "regional_mrar",
            "applies_to_lat_band_filter": "-80..-70,-30..-20",
            "applies_to_depth_bin_filter": "500..6000",
            "condition": "cell overlaps multibeam_ncei AND mb_vs_mrar same lat/depth slice rmse<150m AND abs_residual_p95<200m",
            "recommended_weight": 0.60,
            "requires_step05_overlap": True,
            "exclude_from_primary": True,
            "evidence_basis": "mb_vs_mrar is much tighter than mb_vs_sb and mrar_vs_sb, especially in lat=-70 consistency zone.",
            "notes": "Still exclude from primary by default; useful as regional supplement or consistency check.",
        },
        {
            "rule_id": "mrar_v0_shallow_highrisk",
            "candidate_tier": "review_or_sensitivity_only",
            "applies_to_branch": "regional_mrar",
            "applies_to_lat_band_filter": "*",
            "applies_to_depth_bin_filter": "0..200",
            "condition": "depth_bin=0..200 OR abs(mrar_vs_sb residual) tail exceeds regional threshold",
            "recommended_weight": 0.10,
            "requires_step05_overlap": False,
            "exclude_from_primary": True,
            "evidence_basis": "M.rar had land/sentinel cleaning history; shallow cells are most exposed to land-mask/topography mixing.",
            "notes": "Human must decide whether cleaned shallow M.rar cells are acceptable at all.",
        },
        {
            "rule_id": "any_v0_dup_heavy_downweight",
            "candidate_tier": "low_confidence",
            "applies_to_branch": "*",
            "applies_to_lat_band_filter": "*",
            "applies_to_depth_bin_filter": "*",
            "condition": "duplicate_ratio_cell>0.5 AND no supportive cross-branch evidence",
            "recommended_weight": 0.35,
            "requires_step05_overlap": False,
            "exclude_from_primary": False,
            "evidence_basis": "High duplicate ratio indicates repeated identical triples; Step04 design says do not weight by raw points.",
            "notes": "Reduce confidence but do not exclude solely for duplicates.",
        },
        {
            "rule_id": "any_v0_strong_unique_medium",
            "candidate_tier": "medium_confidence",
            "applies_to_branch": "*",
            "applies_to_lat_band_filter": "*",
            "applies_to_depth_bin_filter": "*",
            "condition": "n_unique_triples_total>=1000 AND duplicate_ratio_cell<=0.1 AND at least one overlap evidence source",
            "recommended_weight": 0.70,
            "requires_step05_overlap": True,
            "exclude_from_primary": False,
            "evidence_basis": "Large effective-count cells are more stable, but cross-source disagreement still requires region stratification.",
            "notes": "This is not a substitute for branch/lat/depth evidence.",
        },
        {
            "rule_id": "sb_v0_highlat_north_review",
            "candidate_tier": "review_or_sensitivity_only",
            "applies_to_branch": "singlebeam",
            "applies_to_lat_band_filter": "60..90",
            "applies_to_depth_bin_filter": "*",
            "condition": "lat_band_10deg>=60 AND cross_branch_abs_residual_p95>300m",
            "recommended_weight": 0.30,
            "requires_step05_overlap": True,
            "exclude_from_primary": False,
            "evidence_basis": "Step05B mrar_vs_sb high-northern bands show large residual tails in the current audit.",
            "notes": "Northern high-latitude behavior should be manually separated from Southern Ocean noise.",
        },
    ]
    out = pd.DataFrame(rows)
    return ensure_columns(out, CANDIDATE_RULE_COLUMNS)


def sentry_proxy_summary(branch_cells: dict[str, pd.DataFrame]) -> pd.DataFrame:
    mb = branch_cells.get("multibeam_ncei", pd.DataFrame())
    if mb.empty:
        return pd.DataFrame()
    high_dup = mb[pd.to_numeric(mb["duplicate_ratio_cell"], errors="coerce") > 0.5]
    if high_dup.empty:
        return pd.DataFrame([{"metric": "high_duplicate_proxy_cells", "value": 0}])
    return pd.DataFrame(
        [
            {"metric": "high_duplicate_proxy_cells", "value": int(len(high_dup))},
            {"metric": "median_lon_center", "value": float(pd.to_numeric(high_dup["lon_center"], errors="coerce").median())},
            {"metric": "median_lat_center", "value": float(pd.to_numeric(high_dup["lat_center"], errors="coerce").median())},
            {"metric": "dominant_lat_band_10deg", "value": int(high_dup["lat_band_10deg"].mode().iloc[0])},
        ]
    )


def rmse_contribution_by_lat(cross_cells: pd.DataFrame, pair_label: str) -> pd.DataFrame:
    sub = cross_cells[cross_cells["pair_label"].astype(str) == pair_label].copy()
    if sub.empty:
        return pd.DataFrame()
    sub["lat_band_10deg"] = compute_lat_band(sub["lat_center"])
    sub["sq"] = pd.to_numeric(sub["residual_m"], errors="coerce") ** 2
    total_sq = float(sub["sq"].sum())
    rows = []
    for band, g in sub.groupby("lat_band_10deg", dropna=False, sort=True):
        sq = float(g["sq"].sum())
        rows.append(
            {
                "lat_band_10deg": int(band) if pd.notna(band) else pd.NA,
                "n_cells": int(len(g)),
                "rmse": safe_rmse(g["residual_m"]),
                "share_of_squared_error": float(sq / total_sq) if total_sq else float("nan"),
            }
        )
    return pd.DataFrame(rows).sort_values("share_of_squared_error", ascending=False)


def mb_mrar_consistency_zones(cross_cells: pd.DataFrame) -> pd.DataFrame:
    sub = cross_cells[cross_cells["pair_label"].astype(str) == "mb_vs_mrar"].copy()
    if sub.empty:
        return pd.DataFrame()
    sub["lat_band_10deg"] = compute_lat_band(sub["lat_center"])
    sub = add_depth_bins(sub, "left_median_depth_m")
    rows = []
    for keys, g in sub.groupby(["lat_band_10deg", "depth_bin_lo", "depth_bin_hi"], dropna=False, sort=True):
        band, lo, hi = keys
        rmse = safe_rmse(g["residual_m"])
        p95 = safe_quantile(g["abs_residual_m"], 0.95)
        if np.isfinite(rmse) and rmse < 150:
            rows.append(
                {
                    "lat_band_10deg": int(band) if pd.notna(band) else pd.NA,
                    "depth_bin_lo": float(lo),
                    "depth_bin_hi": float(hi),
                    "n_cells": int(len(g)),
                    "rmse": rmse,
                    "abs_residual_p95": p95,
                }
            )
    return pd.DataFrame(rows).sort_values(["rmse", "lat_band_10deg"]) if rows else pd.DataFrame()


def sb_overlap_strength(branch_cells: dict[str, pd.DataFrame]) -> pd.DataFrame:
    sb = branch_cells.get("singlebeam", pd.DataFrame())
    if sb.empty:
        return pd.DataFrame()
    bins = right_open_bin_frame(pd.to_numeric(sb["n_track_cells"], errors="coerce"), N_TRACK_CELLS_BINS)
    work = sb.copy()
    work["n_track_cells_bin"] = [f"{lo:g}..{hi:g}" for lo, hi in zip(bins["lo"], bins["hi"])]
    rows = []
    for label, g in work.groupby("n_track_cells_bin", sort=True):
        rows.append(
            {
                "n_track_cells_bin": label,
                "n_cells": int(len(g)),
                "share": float(len(g) / len(work)) if len(work) else float("nan"),
                "median_n_unique_triples_total": safe_quantile(g["n_unique_triples_total"], 0.50),
            }
        )
    return pd.DataFrame(rows)


def make_report(
    *,
    run_label: str,
    elapsed_s: float,
    by_branch: pd.DataFrame,
    by_lat_depth: pd.DataFrame,
    by_source_pair: pd.DataFrame,
    candidate_rules: pd.DataFrame,
    branch_cells: dict[str, pd.DataFrame],
    cross_cells: pd.DataFrame,
    paths: dict[str, Path],
) -> str:
    lines: list[str] = []
    lines.append("# NCEI Step 06A — Quality Policy Calibration Audit Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Run label: `{run_label}`")
    lines.append(f"Policy calibration version: `{POLICY_CALIBRATION_VERSION}`")
    lines.append(f"Elapsed: {elapsed_s:.1f}s")
    lines.append("")
    lines.append("> This is a calibration audit, not policy enforcement. It writes candidate rules for human review only; it does not define final quality tiers, validation cells, or exclusion flags in any cell product.")
    if run_label != "full":
        lines.append("> Scope note: sample/test100 outputs use stratified/capped subsets for plumbing checks. Use full mode before relying on numeric thresholds.")
    lines.append("")

    lines.append("## 1. Executive summary")
    lines.append("")
    lines.append("Global uniform thresholds are unsafe. Step 05B shows much tighter multibeam-vs-M.rar agreement (mb_vs_mrar p99 ≈ 440 m) than singlebeam-involving pairs (mb_vs_sb p99 ≈ 2,424 m; mrar_vs_sb p99 ≈ 1,306 m). The Southern Ocean lat=-60 mb_vs_sb p99 ≈ 3,227 m is the clearest high-noise zone. Candidate rules therefore stratify by branch, latitude, depth, duplicate ratio, and overlap evidence.")
    lines.append("")
    lines.append("Principles used for candidate rules: (1) multibeam_ncei can be high-confidence where low-duplicate and cross-validated; (2) singlebeam must be latitude/depth stratified; (3) regional_mrar defaults to sensitivity/regional use unless cross-validated; (4) manual_review flags are supporting evidence only; (5) high duplicate ratio downweights but does not exclude; (6) n_unique_triples_total<10 is low-confidence; (7) no-overlap cells are low-evidence coverage, not high-confidence validation.")
    lines.append("")

    lines.append("## 2. Per-branch headlines")
    lines.append("")
    lines.extend(markdown_table(by_branch, max_rows=10))

    lines.append("## 3. Stratified evidence by latitude × depth")
    lines.append("")
    lines.append("Tables below show the highest-risk slices first per branch (sorted by cross-branch p95, then within-branch p95). Shallow (`0..200 m`) and high-latitude (`lat<-50`) slices should receive special human review.")
    lines.append("")
    for branch in BRANCHES:
        lines.append(f"### {branch}")
        lines.append("")
        sub = by_lat_depth[by_lat_depth["branch"] == branch].copy()
        sub = sub.sort_values(["cross_branch_residual_max_p95", "within_branch_residual_p95", "n_cells"], ascending=[False, False, False])
        lines.extend(markdown_table(sub, max_rows=25))

    lines.append("## 4. Per-pair stratified evidence")
    lines.append("")
    for pair in PAIR_LABELS:
        lines.append(f"### {pair}")
        lines.append("")
        sub = by_source_pair[by_source_pair["pair_label"] == pair].sort_values("abs_residual_p95", ascending=False)
        lines.extend(markdown_table(sub, max_rows=25))

    lines.append("## 5. Spotlight analyses")
    lines.append("")
    lines.append("### Southern Ocean lat=-60 large residuals")
    lines.append("")
    so = cross_cells.copy()
    so["lat_band_10deg"] = compute_lat_band(so["lat_center"])
    so = so[so["lat_band_10deg"] == -60]
    lines.extend(markdown_table(so.groupby("pair_label").agg(n_cells=("cell_id", "count"), abs_residual_p95=("abs_residual_m", lambda s: safe_quantile(s, 0.95)), abs_residual_p99=("abs_residual_m", lambda s: safe_quantile(s, 0.99)), rmse=("residual_m", safe_rmse)).reset_index(), max_rows=10))
    lines.append("Interpretation: singlebeam-involving Southern Ocean overlap has the largest tails. Candidate rules mark these slices as review/sensitivity unless a local slice has strong overlap evidence.")
    lines.append("")

    lines.append("### AUV Sentry hotspots")
    lines.append("")
    lines.append("Because this Step 06A script is constrained to Step 04B/05A/05B inputs only, it does not join back to Step 04A track_id rows. It uses the documented proxy `duplicate_ratio_cell>0.5` (plus manual_review where present) for AUV-Sentry-like cells.")
    lines.extend(markdown_table(sentry_proxy_summary(branch_cells), max_rows=10))
    lines.append("")

    lines.append("### M.rar × singlebeam large-overlap high-residual regions")
    lines.append("")
    lines.append("Latitude bands below are sorted by share of squared residual error for mrar_vs_sb; bands accounting for >50% cumulatively are the first review targets.")
    lines.extend(markdown_table(rmse_contribution_by_lat(cross_cells, "mrar_vs_sb"), max_rows=20))

    lines.append("### Multibeam × M.rar consistency zones")
    lines.append("")
    lines.append("Candidate cross-validation zones are mb_vs_mrar lat/depth slices with RMSE < 150 m.")
    lines.extend(markdown_table(mb_mrar_consistency_zones(cross_cells), max_rows=20))

    lines.append("### Singlebeam cells with strong vs weak overlap evidence")
    lines.append("")
    lines.extend(markdown_table(sb_overlap_strength(branch_cells), max_rows=10))

    lines.append("## 6. Candidate policy rules")
    lines.append("")
    lines.append("The TSV output is a candidate-rule list for human review. It is the only output containing candidate tier strings; the parquet outputs remain evidence tables and do not define final tiers.")
    lines.extend(markdown_table(candidate_rules, max_rows=25))

    lines.append("## 7. Step 06B implementation recommendations")
    lines.append("")
    lines.append("Future Step 06B should carry these fields in the quality manifest: `quality_tier`, `branch_role` (`primary` / `supplementary` / `regional`), `validation_weight`, `evidence_class` (`within_branch` / `cross_branch` / `both` / `none`), `low_evidence_flag`, and `auv_sentry_flag`. It should also preserve `n_unique_triples_total`, `duplicate_ratio_cell`, `manual_review_any`, and the lat/depth bins used here for auditability.")
    lines.append("")

    lines.append("## 8. Open questions for human review")
    lines.append("")
    questions = [
        "Do we accept latitude-stratified thresholds, or must there be unified per-branch thresholds for publication simplicity?",
        "Should Southern Ocean singlebeam cells remain supplementary only, or can local cross-validation rescue selected lat/depth slices?",
        "Is regional_mrar allowed in any primary validation product, or should it remain regional/sensitivity-only even when mb_vs_mrar is tight?",
        "What maximum acceptable p95 / p99 residual tail should define high-confidence singlebeam cells?",
        "Should `duplicate_ratio_cell>0.5` be an AUV-Sentry downweight proxy in Step 06B, or should Step 06B perform a more expensive track_id join?",
        "Should shallow cells (<200 m) have a separate land/topography-mixing review policy across all branches?",
        "How should no-overlap singlebeam coverage be represented: low-confidence validation, supplementary coverage, or withheld from validation?",
    ]
    for i, question in enumerate(questions, start=1):
        lines.append(f"{i}. {question}")
    lines.append("")

    lines.append("## 9. Cross-links")
    lines.append("")
    lines.append("- Spec §13: `.trellis/spec/backend/pipeline-design-decisions.md#13-ncei-step-04a--per-file-1-arcmin-cell-aggregation`.")
    lines.append("- Spec §14: `.trellis/spec/backend/pipeline-design-decisions.md#14-ncei-step-04b--source-specific-global-1-arcmin-cell-merge`.")
    lines.append("- Spec §15: `.trellis/spec/backend/pipeline-design-decisions.md#15-ncei-step-05a--source-specific-overlap-residual-analysis`.")
    lines.append("- Spec §16: `.trellis/spec/backend/pipeline-design-decisions.md#16-ncei-step-05b--cross-branch-overlap-audit`.")
    lines.append("- Step 04 report: `ncei/docs/step04_aggregation_design_audit.md`.")
    lines.append("- Step 04B report: `ncei/docs/step04b_cells_1min_merge_report.md`.")
    lines.append("- Step 05A report: `ncei/docs/step05a_source_specific_overlap_bias_report.md`.")
    lines.append("- Step 05B report: `ncei/docs/step05b_cross_branch_overlap_audit_report.md`.")
    lines.append("")

    lines.append("## 10. Output paths")
    lines.append("")
    out_rows = [
        {"kind": "by branch", "path": str(paths["by_branch_pq"].relative_to(REPO_ROOT))},
        {"kind": "by lat/depth", "path": str(paths["by_lat_depth_pq"].relative_to(REPO_ROOT))},
        {"kind": "by source pair", "path": str(paths["by_source_pair_pq"].relative_to(REPO_ROOT))},
        {"kind": "candidate rules TSV", "path": str(paths["candidate_rules_tsv"].relative_to(REPO_ROOT))},
        {"kind": "report", "path": str(paths["report_md"].relative_to(REPO_ROOT))},
    ]
    lines.extend(markdown_table(pd.DataFrame(out_rows), max_rows=10))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def existing_outputs(paths: dict[str, Path]) -> list[Path]:
    keys = ["by_branch_pq", "by_lat_depth_pq", "by_source_pair_pq", "candidate_rules_tsv", "report_md"]
    return [paths[k] for k in keys if paths[k].exists()]


def validate_no_final_tiers_in_parquets(*frames: pd.DataFrame) -> None:
    forbidden = {"quality_tier", "validation_weight", "exclude_from_primary", "candidate_tier"}
    for frame in frames:
        present = forbidden & set(frame.columns)
        if present:
            raise ValueError(f"final/candidate policy columns leaked into parquet evidence output: {sorted(present)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Step 06A — Quality policy calibration audit for NCEI Step 04B/05A/05B "
            "outputs. Run from repo root (/mnt/data2/00-Data/ship)."
        )
    )
    parser.add_argument("--run-label", choices=VALID_RUN_LABELS, default="sample")
    parser.add_argument("--confirm-full", action="store_true", help="Required when --run-label=full")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing Step 06A outputs")
    args = parser.parse_args()

    paths = get_output_paths(args.run_label)
    logger = setup_logging(paths["log"])
    t0 = datetime.now()

    logger.info("=" * 60)
    logger.info("11_quality_policy_calibration_audit.py START")
    logger.info("Args: %s", vars(args))
    logger.info("Policy calibration version: %s", POLICY_CALIBRATION_VERSION)

    if args.run_label == "full" and not args.confirm_full:
        logger.error("ABORTED: --run-label=full requires --confirm-full")
        return 2

    if Path.cwd().resolve() != REPO_ROOT:
        logger.warning("Expected to run from repo root %s; current cwd is %s", REPO_ROOT, Path.cwd().resolve())

    required_inputs = [
        CELLS_MANIFEST,
        SUPPLEMENTARY_MANIFEST,
        WITHIN_RESIDUALS,
        TRACK_BIAS_SUMMARY,
        BRANCH_OVERLAP_SUMMARY,
        CROSS_OVERLAP_CELLS,
        CROSS_PAIR_SUMMARY,
    ]
    for input_path in required_inputs:
        if not input_path.exists():
            logger.error("ABORTED: required input not found: %s", input_path)
            return 2

    if not args.overwrite:
        exists = existing_outputs(paths)
        if exists:
            logger.error("ABORTED: outputs exist; use --overwrite. Existing: %s", exists)
            return 2

    try:
        cells_manifest = read_required_parquet(CELLS_MANIFEST)
        _supplementary_manifest = read_required_parquet(SUPPLEMENTARY_MANIFEST)
        branch_overlap_summary = read_required_parquet(BRANCH_OVERLAP_SUMMARY)
        cross_pair_summary = read_required_parquet(CROSS_PAIR_SUMMARY)
        # Loaded for input-boundary validation and report reproducibility. The
        # candidate audit does not currently need track-level fields directly.
        _track_bias_summary = read_required_parquet(TRACK_BIAS_SUMMARY)

        branch_cells = read_all_branch_cells(args.run_label, logger)
        within_residuals = read_within_residuals(args.run_label, logger)
        cross_cells = read_cross_cells(args.run_label, logger)

        by_branch = build_by_branch(
            cells_manifest=cells_manifest,
            branch_cells=branch_cells,
            branch_overlap_summary=branch_overlap_summary,
            cross_pair_summary=cross_pair_summary,
            cross_cells=cross_cells,
        )
        by_lat_depth = build_by_lat_depth(branch_cells, within_residuals, cross_cells)
        by_source_pair = build_by_source_pair(cross_cells)
        candidate_rules = build_candidate_rules()

        validate_no_final_tiers_in_parquets(by_branch, by_lat_depth, by_source_pair)
        if len(candidate_rules) < 12 or len(candidate_rules) > 20:
            raise ValueError(f"expected ~12-20 candidate rules, got {len(candidate_rules)}")
        if set(candidate_rules.columns) != set(CANDIDATE_RULE_COLUMNS):
            raise ValueError("candidate rule schema drift")

        elapsed_s = (datetime.now() - t0).total_seconds()
        report_text = make_report(
            run_label=args.run_label,
            elapsed_s=elapsed_s,
            by_branch=by_branch,
            by_lat_depth=by_lat_depth,
            by_source_pair=by_source_pair,
            candidate_rules=candidate_rules,
            branch_cells=branch_cells,
            cross_cells=cross_cells,
            paths=paths,
        )

        atomic_write_parquet(by_branch, paths["by_branch_pq"])
        atomic_write_parquet(by_lat_depth, paths["by_lat_depth_pq"])
        atomic_write_parquet(by_source_pair, paths["by_source_pair_pq"])
        atomic_write_tsv(candidate_rules, paths["candidate_rules_tsv"])
        atomic_write_text(report_text, paths["report_md"])

        logger.info("Wrote %s (%d rows)", paths["by_branch_pq"], len(by_branch))
        logger.info("Wrote %s (%d rows)", paths["by_lat_depth_pq"], len(by_lat_depth))
        logger.info("Wrote %s (%d rows)", paths["by_source_pair_pq"], len(by_source_pair))
        logger.info("Wrote %s (%d rows)", paths["candidate_rules_tsv"], len(candidate_rules))
        logger.info("Wrote %s", paths["report_md"])
        logger.info("Confirmed 0 final tier definitions written to parquet evidence outputs")
        logger.info("Elapsed: %.1fs", elapsed_s)
        logger.info("11_quality_policy_calibration_audit.py DONE")

        print("Per-branch cells:", by_branch[["branch", "n_cells_total", "n_cells_with_within_branch_overlap", "share_with_overlap_evidence"]].to_dict("records"))
        print(f"Candidate rules proposed: {len(candidate_rules)}")
        print("Final tier definitions in parquet outputs: 0")
        print(f"By branch:     {paths['by_branch_pq']}")
        print(f"By lat/depth:  {paths['by_lat_depth_pq']}")
        print(f"By pair:       {paths['by_source_pair_pq']}")
        print(f"Rules TSV:     {paths['candidate_rules_tsv']}")
        print(f"Report:        {paths['report_md']}")
        return 0

    except Exception as exc:  # noqa: BLE001 - pipeline stage top-level guard
        logger.exception("ABORTED with error: %r", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
