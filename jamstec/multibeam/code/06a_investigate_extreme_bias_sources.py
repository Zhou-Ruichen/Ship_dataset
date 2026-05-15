#!/usr/bin/env python3
"""
06a_investigate_extreme_bias_sources.py

Investigate extreme bias sources identified by 05_analyze_cell_overlap_bias.py.

For candidate files/cruises with large residuals, computes three types of residuals:
  A. residual_to_all_cell_median (vs cells.median_depth_file_balanced)
  B. residual_to_other_cruise_median (vs median of other-cruise file-cells in same cell)
  C. residual_to_other_file_median (vs median of other-file file-cells in same cell)

Produces per-file and per-cruise audit summaries, recommended quality actions,
and affected-cell impact analysis.

Reads:
  - derived/file_cells_1min/*.parquet             (from 04a)
  - derived/cells_1min/cells.parquet               (from 04b)
  - derived/overlap_bias_1min/file_bias_summary.parquet   (from 05)
  - derived/overlap_bias_1min/cruise_bias_summary.parquet (from 05)

Writes (full mode, cell-size=1min):
  - derived/extreme_bias_investigation_1min/candidate_source_residuals.parquet
  - derived/extreme_bias_investigation_1min/candidate_file_audit.parquet + .tsv
  - derived/extreme_bias_investigation_1min/candidate_cruise_audit.parquet + .tsv
  - derived/extreme_bias_investigation_1min/affected_cells_by_candidate.parquet + .tsv
  - derived/extreme_bias_investigation_1min/recommended_quality_actions.tsv
  - derived/extreme_bias_investigation_1min/extreme_bias_investigation_report.md

Usage:
    python 06a_investigate_extreme_bias_sources.py --run-label sample --overwrite
    python 06a_investigate_extreme_bias_sources.py --run-label full --confirm-full --overwrite
    python 06a_investigate_extreme_bias_sources.py --run-label full --confirm-full --estimate-only
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
FILE_BIAS_PQ = ROOT_DIR / "derived" / "overlap_bias_1min" / "file_bias_summary.parquet"
CRUISE_BIAS_PQ = ROOT_DIR / "derived" / "overlap_bias_1min" / "cruise_bias_summary.parquet"

LOG_DIR = ROOT_DIR / "output" / "logs"

VALID_RUN_LABELS = ("sample", "full")
CELL_SIZES = {"1min": 1.0 / 60.0}

EXCLUDE_MIN_OVERLAP = 50
EXCLUDE_ABS_MEDIAN = 500.0
REVIEW_ABS_MEDIAN_LOW = 50.0
REVIEW_ABS_MEDIAN_HIGH = 500.0
HIGH_VARIANCE_RMSE = 500.0

FC_READ_COLUMNS = [
    "cell_id", "lon_center", "lat_center",
    "file_id", "subzip_id", "cruise_id_guess", "track_kind", "data_layout",
    "median_depth_m_positive_down", "n_points",
]


def get_output_paths(run_label: str, cell_size: str) -> dict:
    derived = ROOT_DIR / "derived"
    if run_label == "full":
        out_dir = derived / f"extreme_bias_investigation_{cell_size}"
    else:
        out_dir = derived / f"extreme_bias_investigation_{cell_size}_{run_label}"
    return {
        "out_dir": out_dir,
        "residuals_pq": out_dir / "candidate_source_residuals.parquet",
        "file_audit_pq": out_dir / "candidate_file_audit.parquet",
        "file_audit_tsv": out_dir / "candidate_file_audit.tsv",
        "cruise_audit_pq": out_dir / "candidate_cruise_audit.parquet",
        "cruise_audit_tsv": out_dir / "candidate_cruise_audit.tsv",
        "affected_pq": out_dir / "affected_cells_by_candidate.parquet",
        "affected_tsv": out_dir / "affected_cells_by_candidate.tsv",
        "actions_tsv": out_dir / "recommended_quality_actions.tsv",
        "report_path": out_dir / "extreme_bias_investigation_report.md",
    }


def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("extreme_bias")
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


def read_file_cells(manifest_ok: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    all_dfs = []
    errors = []
    total_rows = 0
    for idx, (_, row) in enumerate(manifest_ok.iterrows()):
        fc_path = ROOT_DIR / row["output_path"]
        try:
            if not fc_path.exists():
                errors.append({"file_id": row["file_id"], "error": f"not found: {fc_path}"})
                continue
            df = pd.read_parquet(fc_path, columns=FC_READ_COLUMNS)
            all_dfs.append(df)
            total_rows += len(df)
            if (idx + 1) % 500 == 0:
                logger.info(f"  Read {idx + 1}/{len(manifest_ok)} files, {total_rows:,} rows")
        except Exception as e:
            errors.append({"file_id": row["file_id"], "error": str(e)})
            logger.error(f"  ERROR reading {fc_path}: {e}")
    logger.info(f"  Read complete: {len(all_dfs)}/{len(manifest_ok)} files, {total_rows:,} rows")
    if not all_dfs:
        return pd.DataFrame(), errors
    fc = pd.concat(all_dfs, ignore_index=True)
    return fc, errors


def select_candidates(
    file_bias: pd.DataFrame,
    cruise_bias: pd.DataFrame,
    run_label: str,
    logger: logging.Logger,
) -> tuple[set[str], set[str]]:
    candidate_file_ids = set()
    candidate_cruise_ids = set()

    # Always: KY09-09 cruise
    candidate_cruise_ids.add("KY09-09")

    # Always: KY12-08 and 20120614 file
    ky12_mask = (
        file_bias["file_id"].str.contains("KY12-08", na=False)
        & file_bias["file_id"].str.contains("20120614", na=False)
    )
    candidate_file_ids.update(file_bias.loc[ky12_mask, "file_id"])

    n_top = 5 if run_label == "sample" else 30

    # Top files by abs(median)
    fb = file_bias.copy()
    fb["_abs_med"] = fb["residual_depth_m_median"].abs()
    candidate_file_ids.update(fb.nlargest(n_top, "_abs_med")["file_id"])

    # Top cruises by abs(median)
    cb = cruise_bias.copy()
    cb["_abs_med"] = cb["residual_depth_m_median"].abs()
    candidate_cruise_ids.update(cb.nlargest(n_top, "_abs_med")["cruise_id_guess"])

    # Top files/cruises by RMSE (both sample and full)
    candidate_file_ids.update(fb.nlargest(n_top, "residual_depth_m_rmse")["file_id"])
    candidate_cruise_ids.update(cb.nlargest(n_top, "residual_depth_m_rmse")["cruise_id_guess"])

    logger.info(f"  Candidate files: {len(candidate_file_ids)}")
    logger.info(f"  Candidate cruises: {len(candidate_cruise_ids)}")
    return candidate_file_ids, candidate_cruise_ids


def compute_residuals(
    candidate_fc: pd.DataFrame,
    all_fc: pd.DataFrame,
    cells: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """Compute residual A, B, C for candidate file-cells."""
    logger.info(f"  Computing residuals for {len(candidate_fc):,} candidate file-cells...")

    # A: residual to all cell median
    cell_ref = cells[["cell_id", "median_depth_file_balanced"]].copy()
    work = candidate_fc.reset_index(drop=True).copy()
    merged = work.merge(cell_ref, on="cell_id", how="left")
    merged["residual_to_all_cell_median"] = (
        merged["median_depth_m_positive_down"] - merged["median_depth_file_balanced"]
    )

    # B & C: need all file-cells in candidate cells
    candidate_cell_ids = set(work["cell_id"].unique())
    fc_in_cells = all_fc[all_fc["cell_id"].isin(candidate_cell_ids)].copy()
    logger.info(f"  File-cells in candidate cells: {len(fc_in_cells):,}")

    # Build lookup: cell_id -> DataFrame of file-cells
    cell_groups = {cid: group for cid, group in fc_in_cells.groupby("cell_id")}

    # Build candidate lookup: cell_id -> list of (position, cruise, file, depth)
    cand_by_cell: dict[str, list] = {}
    for pos in range(len(work)):
        row = work.iloc[pos]
        cid = row["cell_id"]
        if cid not in cand_by_cell:
            cand_by_cell[cid] = []
        cand_by_cell[cid].append(
            (pos, row["cruise_id_guess"], row["file_id"], row["median_depth_m_positive_down"])
        )

    other_cruise_resid = np.full(len(merged), np.nan)
    other_file_resid = np.full(len(merged), np.nan)

    processed = 0
    for cell_id, cand_list in cand_by_cell.items():
        if cell_id not in cell_groups:
            continue
        cell_fc = cell_groups[cell_id]
        all_depths = cell_fc["median_depth_m_positive_down"].values
        all_cruises = cell_fc["cruise_id_guess"].values
        all_files = cell_fc["file_id"].values

        for cand_pos, own_cruise, own_file, own_depth in cand_list:
            # Other cruise median
            other_cruise_mask = all_cruises != own_cruise
            if other_cruise_mask.any():
                ref_med = np.median(all_depths[other_cruise_mask])
                other_cruise_resid[cand_pos] = own_depth - ref_med

            # Other file median
            other_file_mask = all_files != own_file
            if other_file_mask.any():
                ref_med = np.median(all_depths[other_file_mask])
                other_file_resid[cand_pos] = own_depth - ref_med

        processed += 1
        if processed % 5000 == 0:
            logger.info(f"    Processed {processed}/{len(cand_by_cell)} cells")

    merged["residual_to_other_cruise_median"] = other_cruise_resid
    merged["residual_to_other_file_median"] = other_file_resid

    logger.info(f"  Residuals computed: {len(merged):,} rows")
    n_b = int(pd.notna(other_cruise_resid).sum())
    n_c = int(pd.notna(other_file_resid).sum())
    logger.info(f"  Non-null B residuals: {n_b:,}, C residuals: {n_c:,}")

    return merged


def _residual_stats(series: pd.Series, prefix: str) -> dict:
    """Compute median, MAD, RMSE for a residual series."""
    s = series.dropna()
    if len(s) == 0:
        return {
            f"{prefix}_median": np.nan,
            f"{prefix}_mad": np.nan,
            f"{prefix}_rmse": np.nan,
            f"{prefix}_p05": np.nan,
            f"{prefix}_p95": np.nan,
        }
    med = s.median()
    return {
        f"{prefix}_median": med,
        f"{prefix}_mad": (s - med).abs().median(),
        f"{prefix}_rmse": float(np.sqrt((s**2).mean())),
        f"{prefix}_p05": s.quantile(0.05),
        f"{prefix}_p95": s.quantile(0.95),
    }


def aggregate_file_audit(
    residuals_df: pd.DataFrame, all_fc: pd.DataFrame, cells: pd.DataFrame, logger: logging.Logger,
) -> pd.DataFrame:
    """Aggregate residuals per candidate file."""
    logger.info("  Aggregating file audit...")
    # Pre-compute overlap cell set from cells.parquet
    overlap_cell_set = set(cells.loc[cells["n_file_cells"] > 1, "cell_id"])
    results = []

    for file_id, group in residuals_df.groupby("file_id"):
        all_file_fc = all_fc[all_fc["file_id"] == file_id]
        first = group.iloc[0]

        file_cell_ids = set(all_file_fc["cell_id"])
        n_total = len(all_file_fc)
        n_points = int(all_file_fc["n_points"].sum())
        n_overlap = len(file_cell_ids & overlap_cell_set)
        n_other_cruise = int(group["residual_to_other_cruise_median"].notna().sum())
        n_other_file = int(group["residual_to_other_file_median"].notna().sum())
        n_single = n_total - n_overlap

        row = {
            "file_id": file_id,
            "cruise_id_guess": first["cruise_id_guess"],
            "subzip_id": first["subzip_id"],
            "track_kind": first["track_kind"],
            "data_layout": first["data_layout"],
            "n_total_file_cells": n_total,
            "n_overlap_file_cells": n_overlap,
            "n_other_cruise_overlap_cells": n_other_cruise,
            "n_other_file_overlap_cells": n_other_file,
            "n_single_source_cells": n_single,
            "n_points_total": n_points,
        }
        row.update(_residual_stats(group["residual_to_all_cell_median"], "residual_all"))
        row.update(_residual_stats(group["residual_to_other_cruise_median"], "residual_other_cruise"))
        row.update(_residual_stats(group["residual_to_other_file_median"], "residual_other_file"))
        row["lon_min"] = float(all_file_fc["lon_center"].min())
        row["lon_max"] = float(all_file_fc["lon_center"].max())
        row["lat_min"] = float(all_file_fc["lat_center"].min())
        row["lat_max"] = float(all_file_fc["lat_center"].max())
        row["depth_min"] = float(all_file_fc["median_depth_m_positive_down"].min())
        row["depth_max"] = float(all_file_fc["median_depth_m_positive_down"].max())

        results.append(row)

    df = pd.DataFrame(results)
    logger.info(f"  File audit: {len(df)} files")
    return df


def aggregate_cruise_audit(
    residuals_df: pd.DataFrame, all_fc: pd.DataFrame, cells: pd.DataFrame, logger: logging.Logger,
) -> pd.DataFrame:
    """Aggregate residuals per candidate cruise."""
    logger.info("  Aggregating cruise audit...")
    overlap_cell_set = set(cells.loc[cells["n_file_cells"] > 1, "cell_id"])
    results = []

    for cruise_id, group in residuals_df.groupby("cruise_id_guess"):
        all_cruise_fc = all_fc[all_fc["cruise_id_guess"] == cruise_id]

        cruise_cell_ids = set(all_cruise_fc["cell_id"])
        n_total = len(all_cruise_fc)
        n_points = int(all_cruise_fc["n_points"].sum())
        n_overlap = len(cruise_cell_ids & overlap_cell_set)
        n_other_cruise = int(group["residual_to_other_cruise_median"].notna().sum())
        n_other_file = int(group["residual_to_other_file_median"].notna().sum())
        n_single = n_total - n_overlap

        row = {
            "cruise_id_guess": cruise_id,
            "n_total_file_cells": n_total,
            "n_overlap_file_cells": n_overlap,
            "n_other_cruise_overlap_cells": n_other_cruise,
            "n_other_file_overlap_cells": n_other_file,
            "n_single_source_cells": n_single,
            "n_points_total": n_points,
        }
        row.update(_residual_stats(group["residual_to_all_cell_median"], "residual_all"))
        row.update(_residual_stats(group["residual_to_other_cruise_median"], "residual_other_cruise"))
        row.update(_residual_stats(group["residual_to_other_file_median"], "residual_other_file"))
        row["lon_min"] = float(all_cruise_fc["lon_center"].min())
        row["lon_max"] = float(all_cruise_fc["lon_center"].max())
        row["lat_min"] = float(all_cruise_fc["lat_center"].min())
        row["lat_max"] = float(all_cruise_fc["lat_center"].max())
        row["depth_min"] = float(all_cruise_fc["median_depth_m_positive_down"].min())
        row["depth_max"] = float(all_cruise_fc["median_depth_m_positive_down"].max())

        results.append(row)

    df = pd.DataFrame(results)
    logger.info(f"  Cruise audit: {len(df)} cruises")
    return df


def _classify_action(
    n_other_cruise: float,
    other_cruise_med: float,
    other_cruise_rmse: float,
    candidate_id: str,
    candidate_type: str,
    other_file_med: float = None,
) -> tuple[str, str]:
    """Classify recommended action for a candidate."""
    is_ky09 = candidate_type == "cruise" and candidate_id == "KY09-09"
    is_ky12 = candidate_type == "file" and "KY12-08" in str(candidate_id) and "20120614" in str(candidate_id)

    # Special: KY12-08::20120614 uses other_file_median
    if is_ky12 and pd.notna(other_file_med):
        if abs(other_file_med) >= EXCLUDE_ABS_MEDIAN:
            return "exclude_candidate", f"KY12-08::20120614: abs(other_file_median)={abs(other_file_med):.1f}m >= {EXCLUDE_ABS_MEDIAN}m"
        if abs(other_file_med) >= REVIEW_ABS_MEDIAN_LOW:
            return "review_candidate", f"KY12-08::20120614: abs(other_file_median)={abs(other_file_med):.1f}m in [{REVIEW_ABS_MEDIAN_LOW},{REVIEW_ABS_MEDIAN_HIGH})m"

    if pd.isna(other_cruise_med):
        return "keep", "insufficient overlap data for classification"

    abs_med = abs(other_cruise_med)

    if is_ky09 and abs_med > EXCLUDE_ABS_MEDIAN:
        return "exclude_candidate", f"KY09-09: abs(other_cruise_median)={abs_med:.1f}m > {EXCLUDE_ABS_MEDIAN}m"

    if n_other_cruise >= EXCLUDE_MIN_OVERLAP and abs_med >= EXCLUDE_ABS_MEDIAN:
        return "exclude_candidate", f"n_other_cruise={int(n_other_cruise)}, abs(median)={abs_med:.1f}m >= {EXCLUDE_ABS_MEDIAN}m"

    if n_other_cruise >= EXCLUDE_MIN_OVERLAP and REVIEW_ABS_MEDIAN_LOW <= abs_med < REVIEW_ABS_MEDIAN_HIGH:
        return "review_candidate", f"n_other_cruise={int(n_other_cruise)}, abs(median)={abs_med:.1f}m in [{REVIEW_ABS_MEDIAN_LOW},{REVIEW_ABS_MEDIAN_HIGH})m"

    if abs_med < REVIEW_ABS_MEDIAN_LOW and pd.notna(other_cruise_rmse) and other_cruise_rmse >= HIGH_VARIANCE_RMSE:
        return "high_variance_review", f"median={other_cruise_med:.1f}m < {REVIEW_ABS_MEDIAN_LOW}m, RMSE={other_cruise_rmse:.1f}m >= {HIGH_VARIANCE_RMSE}m"

    return "keep", "no significant bias or variance detected"


def apply_recommendations(
    file_audit: pd.DataFrame, cruise_audit: pd.DataFrame, logger: logging.Logger,
) -> pd.DataFrame:
    """Apply action classification to file and cruise audits. Returns combined actions TSV."""
    actions = []

    for _, row in file_audit.iterrows():
        action, reason = _classify_action(
            n_other_cruise=row.get("n_other_cruise_overlap_cells", 0),
            other_cruise_med=row.get("residual_other_cruise_median", np.nan),
            other_cruise_rmse=row.get("residual_other_cruise_rmse", np.nan),
            candidate_id=row["file_id"],
            candidate_type="file",
            other_file_med=row.get("residual_other_file_median", np.nan),
        )
        file_audit.loc[row.name, "recommended_action"] = action
        file_audit.loc[row.name, "action_reason"] = reason
        actions.append({
            "candidate_type": "file",
            "candidate_id": row["file_id"],
            "cruise_id_guess": row.get("cruise_id_guess", ""),
            "recommended_action": action,
            "action_reason": reason,
        })

    for _, row in cruise_audit.iterrows():
        action, reason = _classify_action(
            n_other_cruise=row.get("n_other_cruise_overlap_cells", 0),
            other_cruise_med=row.get("residual_other_cruise_median", np.nan),
            other_cruise_rmse=row.get("residual_other_cruise_rmse", np.nan),
            candidate_id=row["cruise_id_guess"],
            candidate_type="cruise",
        )
        cruise_audit.loc[row.name, "recommended_action"] = action
        cruise_audit.loc[row.name, "action_reason"] = reason
        actions.append({
            "candidate_type": "cruise",
            "candidate_id": row["cruise_id_guess"],
            "cruise_id_guess": row["cruise_id_guess"],
            "recommended_action": action,
            "action_reason": reason,
        })

    actions_df = pd.DataFrame(actions)
    logger.info(f"  Actions: {dict(actions_df['recommended_action'].value_counts())}")
    return actions_df


def compute_affected_cells(
    candidate_fc: pd.DataFrame,
    all_fc: pd.DataFrame,
    cells: pd.DataFrame,
    file_audit: pd.DataFrame,
    cruise_audit: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """Compute affected cells for exclude/review candidates."""
    logger.info("  Computing affected cells...")

    # Get candidates that are exclude or review
    action_files = set(
        file_audit.loc[
            file_audit["recommended_action"].isin(["exclude_candidate", "review_candidate"]),
            "file_id",
        ]
    )
    action_cruises = set(
        cruise_audit.loc[
            cruise_audit["recommended_action"].isin(["exclude_candidate", "review_candidate"]),
            "cruise_id_guess",
        ]
    )

    if not action_files and not action_cruises:
        logger.info("  No exclude/review candidates — no affected cells to compute.")
        return pd.DataFrame()

    results = []

    # Per file
    for fid in action_files:
        file_fc = all_fc[all_fc["file_id"] == fid]
        file_cells = set(file_fc["cell_id"])
        cells_info = cells[cells["cell_id"].isin(file_cells)]

        n_total = len(file_cells)
        n_overlap = int((cells_info["n_file_cells"] > 1).sum())
        n_single = int((cells_info["n_file_cells"] == 1).sum())
        n_multi_cruise = int((cells_info["n_cruises_guess"] > 1).sum())
        n_pts = int(file_fc["n_points"].sum())
        n_lost = n_single
        n_retained = n_total - n_lost

        results.append({
            "candidate_type": "file",
            "candidate_id": fid,
            "n_cells_total": n_total,
            "n_cells_overlap": n_overlap,
            "n_cells_single_source": n_single,
            "n_cells_multi_cruise": n_multi_cruise,
            "n_points_total": n_pts,
            "n_cells_lost_all_coverage": n_lost,
            "n_cells_retained_coverage": n_retained,
        })

    # Per cruise
    for cid in action_cruises:
        cruise_fc = all_fc[all_fc["cruise_id_guess"] == cid]
        cruise_cells = set(cruise_fc["cell_id"])
        cells_info = cells[cells["cell_id"].isin(cruise_cells)]

        n_total = len(cruise_cells)
        n_overlap = int((cells_info["n_file_cells"] > 1).sum())
        n_single = int((cells_info["n_file_cells"] == 1).sum())
        n_multi_cruise = int((cells_info["n_cruises_guess"] > 1).sum())
        n_pts = int(cruise_fc["n_points"].sum())

        # For cruise exclusion: a cell loses coverage if this was the only cruise
        # Vectorized: count cruises per cell from all_fc, then check cells
        # where this cruise is the only one
        cruise_cell_fc = all_fc[all_fc["cell_id"].isin(cruise_cells)]
        cruises_per_cell = cruise_cell_fc.groupby("cell_id")["cruise_id_guess"].nunique()
        single_cruise_cell_ids = set(cruises_per_cell[cruises_per_cell <= 1].index)
        # Among single-cruise cells, check which ones have ONLY this cruise
        if single_cruise_cell_ids:
            single_fc = all_fc[all_fc["cell_id"].isin(single_cruise_cell_ids)]
            unique_cruises = single_fc.groupby("cell_id")["cruise_id_guess"].agg(lambda x: set(x))
            n_lost = int((unique_cruises == {cid}).sum())
        else:
            n_lost = 0
        n_retained = n_total - n_lost

        results.append({
            "candidate_type": "cruise",
            "candidate_id": cid,
            "n_cells_total": n_total,
            "n_cells_overlap": n_overlap,
            "n_cells_single_source": n_single,
            "n_cells_multi_cruise": n_multi_cruise,
            "n_points_total": n_pts,
            "n_cells_lost_all_coverage": n_lost,
            "n_cells_retained_coverage": n_retained,
        })

    df = pd.DataFrame(results)
    logger.info(f"  Affected cells computed for {len(df)} candidates")
    return df


def write_report(
    report_path: Path,
    file_audit: pd.DataFrame,
    cruise_audit: pd.DataFrame,
    actions_df: pd.DataFrame,
    affected_df: pd.DataFrame,
    n_candidate_files: int,
    n_candidate_cruises: int,
    n_candidate_fc_rows: int,
    run_label: str,
    elapsed_s: float,
    logger: logging.Logger,
):
    lines = [
        f"# Extreme Bias Investigation Report — {run_label} (1min)",
        f"",
        f"Generated: {datetime.now().isoformat()}",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Candidate files | {n_candidate_files} |",
        f"| Candidate cruises | {n_candidate_cruises} |",
        f"| Candidate file-cell rows | {n_candidate_fc_rows:,} |",
        f"| Elapsed | {elapsed_s:.1f}s |",
        f"| Backend | pandas |",
        f"",
    ]

    if len(actions_df) > 0:
        lines.append(f"## Recommended actions")
        lines.append(f"")
        vc = actions_df["recommended_action"].value_counts()
        for action, count in vc.items():
            lines.append(f"- {action}: {count}")
        lines.append(f"")

    if len(file_audit) > 0:
        lines.append(f"## File audit highlights")
        lines.append(f"")
        for _, r in file_audit.head(20).iterrows():
            fid = str(r["file_id"])[:60]
            lines.append(
                f"- {fid}: action={r.get('recommended_action', 'N/A')}, "
                f"other_cruise_med={r.get('residual_other_cruise_median', float('nan')):.1f}m, "
                f"other_file_med={r.get('residual_other_file_median', float('nan')):.1f}m, "
                f"n_overlap={int(r.get('n_overlap_file_cells', 0))}"
            )
        lines.append(f"")

    if len(cruise_audit) > 0:
        lines.append(f"## Cruise audit highlights")
        lines.append(f"")
        for _, r in cruise_audit.iterrows():
            cid = str(r["cruise_id_guess"])
            lines.append(
                f"- {cid}: action={r.get('recommended_action', 'N/A')}, "
                f"other_cruise_med={r.get('residual_other_cruise_median', float('nan')):.1f}m, "
                f"n_overlap={int(r.get('n_overlap_file_cells', 0))}"
            )
        lines.append(f"")

    if len(affected_df) > 0:
        lines.append(f"## Affected cells (exclude/review candidates)")
        lines.append(f"")
        lines.append(f"| candidate_type | candidate_id | n_cells_total | n_lost_all | n_retained |")
        lines.append(f"|----------------|--------------|---------------|------------|------------|")
        for _, r in affected_df.iterrows():
            cid = str(r["candidate_id"])[:50]
            lines.append(
                f"| {r['candidate_type']} | {cid} | {int(r['n_cells_total']):,} | "
                f"{int(r['n_cells_lost_all_coverage']):,} | {int(r['n_cells_retained_coverage']):,} |"
            )
        lines.append(f"")

    lines.append(f"## Thresholds")
    lines.append(f"")
    lines.append(f"| Threshold | Value |")
    lines.append(f"|-----------|-------|")
    lines.append(f"| exclude: min other-cruise overlap | {EXCLUDE_MIN_OVERLAP} |")
    lines.append(f"| exclude: abs(other_cruise_median) | >= {EXCLUDE_ABS_MEDIAN} m |")
    lines.append(f"| review: abs(other_cruise_median) | [{REVIEW_ABS_MEDIAN_LOW}, {REVIEW_ABS_MEDIAN_HIGH}) m |")
    lines.append(f"| high_variance: RMSE | >= {HIGH_VARIANCE_RMSE} m |")
    lines.append(f"")

    content = "\n".join(lines)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = report_path.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, report_path)
    logger.info(f"Report written to {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Investigate extreme bias sources from 05 overlap/bias analysis.",
    )
    parser.add_argument("--run-label", type=str, default="sample", choices=VALID_RUN_LABELS)
    parser.add_argument("--cell-size", type=str, default="1min", choices=["1min"])
    parser.add_argument("--confirm-full", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--estimate-only", action="store_true")
    args = parser.parse_args()

    run_label = args.run_label
    cell_size = args.cell_size

    log_path = LOG_DIR / f"06a_investigate_extreme_bias_sources_{run_label}.log"
    errors_tsv = LOG_DIR / f"06a_extreme_bias_errors_{run_label}.tsv"

    logger = setup_logging(log_path)
    logger.info("=" * 60)
    logger.info("Starting 06a_investigate_extreme_bias_sources.py")
    logger.info(f"Args: {vars(args)}")

    if run_label == "full" and not args.confirm_full:
        msg = "ABORTED: --run-label=full requires --confirm-full."
        logger.error(msg)
        print(f"ERROR: {msg}")
        sys.exit(1)

    # Load inputs
    logger.info("Loading inputs...")
    if not FILE_BIAS_PQ.exists():
        logger.error(f"file_bias_summary not found: {FILE_BIAS_PQ}")
        sys.exit(1)
    if not CRUISE_BIAS_PQ.exists():
        logger.error(f"cruise_bias_summary not found: {CRUISE_BIAS_PQ}")
        sys.exit(1)
    if not CELLS_PQ.exists():
        logger.error(f"cells.parquet not found: {CELLS_PQ}")
        sys.exit(1)

    file_bias = pd.read_parquet(FILE_BIAS_PQ)
    cruise_bias = pd.read_parquet(CRUISE_BIAS_PQ)
    cells = pd.read_parquet(CELLS_PQ)
    logger.info(f"  file_bias: {len(file_bias)} rows")
    logger.info(f"  cruise_bias: {len(cruise_bias)} rows")
    logger.info(f"  cells: {len(cells):,} rows")

    # Select candidates
    logger.info("Selecting candidates...")
    candidate_file_ids, candidate_cruise_ids = select_candidates(
        file_bias, cruise_bias, run_label, logger,
    )

    paths = get_output_paths(run_label, cell_size)

    summary = (
        f"\n{'=' * 60}\n"
        f"  CONFIG SUMMARY\n"
        f"{'=' * 60}\n"
        f"  run_label:            {run_label}\n"
        f"  candidate files:      {len(candidate_file_ids)}\n"
        f"  candidate cruises:    {len(candidate_cruise_ids)}\n"
        f"  output_dir:           {paths['out_dir']}\n"
        f"  confirm_full:         {args.confirm_full}\n"
        f"  estimate_only:        {args.estimate_only}\n"
        f"  backend:              pandas\n"
        f"{'=' * 60}"
    )
    logger.info(summary)
    print(summary)

    if args.estimate_only:
        logger.info("ESTIMATE ONLY — no files written.")
        print("ESTIMATE ONLY — no files written.")
        return

    if not args.overwrite and paths["residuals_pq"].exists():
        msg = f"Output exists: {paths['residuals_pq']}. Use --overwrite."
        logger.error(msg)
        print(f"ERROR: {msg}")
        sys.exit(1)

    t_start = datetime.now()

    # Read all file-cells
    logger.info("Reading file-cell parquets...")
    fc_manifest = pd.read_parquet(FC_MANIFEST_PQ)
    fc_manifest = fc_manifest[fc_manifest["status"] == "ok"].copy()
    all_fc, read_errors = read_file_cells(fc_manifest, logger)

    if len(all_fc) == 0:
        logger.error("No file-cell data read.")
        write_errors_tsv(read_errors, errors_tsv, logger)
        return

    # Filter to candidate file-cells
    logger.info("Filtering to candidate file-cells...")
    candidate_fc = all_fc[
        all_fc["file_id"].isin(candidate_file_ids)
        | all_fc["cruise_id_guess"].isin(candidate_cruise_ids)
    ].copy()
    logger.info(f"  Candidate file-cells: {len(candidate_fc):,}")

    # Compute residuals
    logger.info("Computing residuals...")
    residuals_df = compute_residuals(candidate_fc, all_fc, cells, logger)

    # Aggregate
    file_audit = aggregate_file_audit(residuals_df, all_fc, cells, logger)
    cruise_audit = aggregate_cruise_audit(residuals_df, all_fc, cells, logger)

    # Recommend actions
    logger.info("Recommending actions...")
    actions_df = apply_recommendations(file_audit, cruise_audit, logger)

    # Affected cells
    affected_df = compute_affected_cells(
        candidate_fc, all_fc, cells, file_audit, cruise_audit, logger,
    )

    # Write outputs
    logger.info("Writing outputs...")
    paths["out_dir"].mkdir(parents=True, exist_ok=True)

    # Residuals output columns
    res_cols = [
        "cell_id", "lon_center", "lat_center",
        "file_id", "subzip_id", "cruise_id_guess",
        "median_depth_m_positive_down", "median_depth_file_balanced",
        "residual_to_all_cell_median",
        "residual_to_other_cruise_median",
        "residual_to_other_file_median",
        "n_points",
    ]
    res_cols = [c for c in res_cols if c in residuals_df.columns]
    atomic_write_parquet(residuals_df[res_cols], paths["residuals_pq"], logger)

    atomic_write_parquet(file_audit, paths["file_audit_pq"], logger)
    atomic_write_tsv(file_audit, paths["file_audit_tsv"], logger)

    atomic_write_parquet(cruise_audit, paths["cruise_audit_pq"], logger)
    atomic_write_tsv(cruise_audit, paths["cruise_audit_tsv"], logger)

    if len(affected_df) > 0:
        atomic_write_parquet(affected_df, paths["affected_pq"], logger)
        atomic_write_tsv(affected_df, paths["affected_tsv"], logger)
    else:
        empty = pd.DataFrame()
        atomic_write_parquet(empty, paths["affected_pq"], logger)
        atomic_write_tsv(empty, paths["affected_tsv"], logger)

    atomic_write_tsv(actions_df, paths["actions_tsv"], logger)
    write_errors_tsv(read_errors, errors_tsv, logger)

    t_end = datetime.now()
    elapsed_s = (t_end - t_start).total_seconds()

    # Report
    write_report(
        paths["report_path"], file_audit, cruise_audit, actions_df, affected_df,
        len(candidate_file_ids), len(candidate_cruise_ids), len(candidate_fc),
        run_label, elapsed_s, logger,
    )

    # Final summary
    report = f"""
{'=' * 60}
  RUN REPORT — 06a_investigate_extreme_bias_sources.py
{'=' * 60}
  run_label:               {run_label}
  candidate files:         {len(candidate_file_ids)}
  candidate cruises:       {len(candidate_cruise_ids)}
  candidate fc rows:       {len(candidate_fc):,}

  file_audit rows:         {len(file_audit)}
  cruise_audit rows:       {len(cruise_audit)}

  Actions:
"""
    if len(actions_df) > 0:
        for action, count in actions_df["recommended_action"].value_counts().items():
            report += f"    {action}: {count}\n"

    if len(affected_df) > 0:
        total_lost = int(affected_df["n_cells_lost_all_coverage"].sum())
        total_retained = int(affected_df["n_cells_retained_coverage"].sum())
        report += f"""
  Affected cells (exclude/review):
    total cells:    {int(affected_df['n_cells_total'].sum()):,}
    lost coverage:  {total_lost:,}
    retained:       {total_retained:,}
"""

    report += f"""
  Elapsed:                 {elapsed_s:.1f}s
  Backend:                 pandas
{'=' * 60}
"""
    logger.info(report)
    print(report)


if __name__ == "__main__":
    main()
