#!/usr/bin/env python3
"""06c_rebuild_cells_1min_qcfiltered.py

Rebuild global cell-level bathymetry from file_cells_1min, excluding files
flagged with exclude_from_primary_cells=True in file_quality_flags_1min.

The merge logic is identical to 04b_merge_multibeam_cells.py.

Input:
  - derived/file_cells_1min/*.parquet
  - manifests/file_cells_manifest_1min.parquet
  - manifests/file_quality_flags_1min.parquet

Output:
  - derived/cells_1min_qcfiltered/cells.parquet
  - manifests/cells_manifest_1min_qcfiltered.parquet
  - manifests/cells_manifest_1min_qcfiltered.tsv
  - docs/cells_report_1min_qcfiltered.md
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent

INPUTS = {
    "fc_dir": PROJECT / "derived" / "file_cells_1min",
    "fc_manifest": PROJECT / "manifests" / "file_cells_manifest_1min.parquet",
    "quality_flags": PROJECT / "manifests" / "file_quality_flags_1min.parquet",
    "original_cells": PROJECT / "derived" / "cells_1min" / "cells.parquet",
}

OUTPUTS = {
    "cells_parquet": PROJECT / "derived" / "cells_1min_qcfiltered" / "cells.parquet",
    "manifest_parquet": PROJECT / "manifests" / "cells_manifest_1min_qcfiltered.parquet",
    "manifest_tsv": PROJECT / "manifests" / "cells_manifest_1min_qcfiltered.tsv",
    "report": PROJECT / "docs" / "cells_report_1min_qcfiltered.md",
}

LOG_PATH = PROJECT / "output" / "logs" / "06c_rebuild_cells_1min_qcfiltered.log"
ERROR_PATH = PROJECT / "output" / "logs" / "06c_rebuild_cells_errors.tsv"


# ---------------------------------------------------------------------------
# Atomic write helpers
# ---------------------------------------------------------------------------

def atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, path)


def atomic_write_tsv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, path)


def atomic_write_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Merge logic (identical to 04b_merge_multibeam_cells.py)
# ---------------------------------------------------------------------------

def merge_cells(fc: pd.DataFrame) -> pd.DataFrame:
    """Merge file-cells into global cells. Each output row = one unique cell_id."""
    if len(fc) == 0:
        return pd.DataFrame()

    fc["_weighted_depth"] = fc["mean_depth_m_positive_down"].values * fc["n_points"].values
    is_3col = (fc["data_layout"] == "lon_lat_depth_3col").astype(np.int32)
    is_6col = (fc["data_layout"] == "lon_lat_depth_time_sonar_6col").astype(np.int32)

    agg = fc.groupby("cell_id").agg(
        lon_bin=("lon_bin", "first"),
        lat_bin=("lat_bin", "first"),
        lon_center=("lon_center", "first"),
        lat_center=("lat_center", "first"),
        n_points_total=("n_points", "sum"),
        n_files=("file_id", "nunique"),
        n_cruises_guess=("cruise_id_guess", "nunique"),
        n_subzips=("subzip_id", "nunique"),
        _sum_weighted_depth=("_weighted_depth", "sum"),
        _median_depth=("median_depth_m_positive_down", "median"),
        _mean_depth=("median_depth_m_positive_down", "mean"),
        _std_depth=("median_depth_m_positive_down", "std"),
        _min_depth_file_cell=("min_depth_m", "min"),
        _max_depth_file_cell=("max_depth_m", "max"),
    )

    agg["n_file_cells"] = fc.groupby("cell_id").size()

    q25 = fc.groupby("cell_id")["median_depth_m_positive_down"].quantile(0.25)
    q75 = fc.groupby("cell_id")["median_depth_m_positive_down"].quantile(0.75)
    agg["_q25_depth"] = q25
    agg["_q75_depth"] = q75

    agg["n_3col_file_cells"] = is_3col.groupby(fc["cell_id"]).sum().astype(np.int32)
    agg["n_6col_file_cells"] = is_6col.groupby(fc["cell_id"]).sum().astype(np.int32)

    dominant_idx = fc.groupby("cell_id")["n_points"].idxmax()
    dominant = fc.loc[dominant_idx, ["cell_id", "file_id", "cruise_id_guess",
                                     "track_kind", "data_layout"]].copy()
    dominant.columns = ["cell_id", "dominant_file_id", "dominant_cruise_id_guess",
                        "dominant_track_kind", "dominant_data_layout"]

    result = agg.reset_index().merge(dominant, on="cell_id", how="left")

    result["cell_size"] = "1min"
    result["median_depth_file_balanced"] = result["_median_depth"]
    result["median_elev_file_balanced"] = -result["median_depth_file_balanced"]
    result["mean_depth_file_balanced"] = result["_mean_depth"]
    result["mean_elev_file_balanced"] = -result["mean_depth_file_balanced"]

    result["weighted_mean_depth_point_weighted"] = (
        result["_sum_weighted_depth"] / result["n_points_total"]
    )
    result["weighted_mean_elev_point_weighted"] = -result["weighted_mean_depth_point_weighted"]

    result["std_depth_between_file_cells"] = result["_std_depth"].fillna(0.0)
    result["q25_depth_between_file_cells"] = result["_q25_depth"]
    result["q75_depth_between_file_cells"] = result["_q75_depth"]
    result["iqr_depth_between_file_cells"] = result["_q75_depth"] - result["_q25_depth"]

    result["min_depth_file_cell"] = result["_min_depth_file_cell"]
    result["max_depth_file_cell"] = result["_max_depth_file_cell"]
    result["range_depth_file_cell"] = result["_max_depth_file_cell"] - result["_min_depth_file_cell"]

    result["source_dataset"] = "NCEI_multibeam"

    # New qcfiltered fields
    result["qcfiltered"] = True
    result["quality_filter_version"] = "v1_extreme_bias_exclusion"

    # n_excluded_file_cells_in_original and related fields will be filled after
    # comparing with original cells (done in main flow)

    output_cols = [
        "cell_id", "cell_size", "lon_bin", "lat_bin", "lon_center", "lat_center",
        "median_depth_file_balanced", "median_elev_file_balanced",
        "mean_depth_file_balanced", "mean_elev_file_balanced",
        "weighted_mean_depth_point_weighted", "weighted_mean_elev_point_weighted",
        "std_depth_between_file_cells",
        "q25_depth_between_file_cells", "q75_depth_between_file_cells",
        "iqr_depth_between_file_cells",
        "min_depth_file_cell", "max_depth_file_cell", "range_depth_file_cell",
        "n_points_total", "n_file_cells", "n_files", "n_cruises_guess", "n_subzips",
        "n_3col_file_cells", "n_6col_file_cells",
        "dominant_file_id", "dominant_cruise_id_guess",
        "dominant_track_kind", "dominant_data_layout",
        "source_dataset",
        "qcfiltered", "quality_filter_version",
    ]
    result = result[output_cols]
    return result


# ---------------------------------------------------------------------------
# Core flow
# ---------------------------------------------------------------------------

def run(args):
    log = logging.getLogger("06c")
    errors = []

    # ── 1. Load quality flags and determine excluded files ─────────────
    log.info("Loading file_quality_flags_1min ...")
    qf = pd.read_parquet(INPUTS["quality_flags"])
    excluded_file_ids = set(qf.loc[qf["exclude_from_primary_cells"], "file_id"])
    log.info(f"  {len(excluded_file_ids)} files marked exclude_from_primary_cells=True")

    # ── 2. Load file_cells_manifest ───────────────────────────────────
    log.info("Loading file_cells_manifest_1min ...")
    fcm = pd.read_parquet(INPUTS["fc_manifest"])
    log.info(f"  {len(fcm)} total files in manifest")

    # Split into included/excluded
    fcm_included = fcm[~fcm["file_id"].isin(excluded_file_ids)].copy()
    fcm_excluded = fcm[fcm["file_id"].isin(excluded_file_ids)].copy()
    log.info(f"  {len(fcm_included)} included, {len(fcm_excluded)} excluded")

    if args.estimate_only:
        log.info("ESTIMATE ONLY — not reading file-cell data")
        print(f"\n=== ESTIMATE ===")
        print(f"Total file-cell files: {len(fcm)}")
        print(f"Excluded files: {len(fcm_excluded)}")
        print(f"Included files: {len(fcm_included)}")
        print(f"Excluded file-cell rows: {fcm_excluded['n_cells'].sum():,}")
        print(f"Included file-cell rows: {fcm_included['n_cells'].sum():,}")
        print(f"Excluded points: {fcm_excluded['n_points_total'].sum():,}")
        print(f"Included points: {fcm_included['n_points_total'].sum():,}")
        return

    # ── 3. Read included file-cell parquets ────────────────────────────
    log.info("Reading included file-cell parquets ...")
    all_dfs = []
    total_rows = 0
    read_errors = 0

    for idx, (_, row) in enumerate(fcm_included.iterrows()):
        file_id = row["file_id"]
        fc_path = PROJECT / row["output_path"]

        try:
            if not fc_path.exists():
                read_errors += 1
                errors.append({"file_id": file_id, "error": f"not found: {fc_path}"})
                log.warning(f"  SKIP (not found): {fc_path}")
                continue

            df = pd.read_parquet(fc_path)
            all_dfs.append(df)
            total_rows += len(df)

            if (idx + 1) % 500 == 0:
                log.info(f"  Read {idx + 1}/{len(fcm_included)} files, {total_rows:,} file-cell rows")

        except Exception as e:
            read_errors += 1
            errors.append({"file_id": file_id, "error": str(e)})
            log.error(f"  ERROR reading {fc_path}: {e}")

    log.info(f"  Read complete: {len(all_dfs)}/{len(fcm_included)} files, {total_rows:,} file-cell rows, {read_errors} errors")

    if not all_dfs:
        log.error("No file-cell data read — aborting")
        return

    fc = pd.concat(all_dfs, ignore_index=True)
    log.info(f"  Concatenated: {len(fc):,} rows x {len(fc.columns)} columns")

    # ── 4. Merge into global cells ─────────────────────────────────────
    log.info("Merging file-cells into global cells ...")
    t_merge_start = time.time()
    result = merge_cells(fc)
    t_merge = time.time() - t_merge_start
    log.info(f"  Merged into {len(result):,} unique cells in {t_merge:.1f}s")

    # ── 5. Load original cells for comparison ──────────────────────────
    log.info("Loading original cells for comparison ...")
    original = pd.read_parquet(INPUTS["original_cells"])
    log.info(f"  Original cells: {len(original):,}")

    # ── 6. Compute excluded-source tracking fields ─────────────────────
    log.info("Computing excluded-source tracking fields ...")

    # File-cells from excluded files (need to read excluded FC data)
    # For efficiency, compute from manifest rather than reading all excluded files
    # We need: for each cell_id, how many file-cells were from excluded files
    excluded_fc_cells = set()
    excluded_points_by_cell = {}
    excluded_fc_count_by_cell = {}
    exc_total_rows = 0

    log.info(f"  Reading {len(fcm_excluded)} excluded file-cell files for tracking ...")
    for _, row in fcm_excluded.iterrows():
        fc_path = PROJECT / row["output_path"]
        if not fc_path.exists():
            errors.append({"file_id": row["file_id"], "error": f"excluded file not found: {fc_path}"})
            continue
        try:
            df_exc = pd.read_parquet(fc_path, columns=["cell_id", "n_points"])
            exc_total_rows += len(df_exc)
            for cell_id, pts in zip(df_exc["cell_id"], df_exc["n_points"]):
                excluded_fc_cells.add(cell_id)
                excluded_points_by_cell[cell_id] = excluded_points_by_cell.get(cell_id, 0) + pts
                excluded_fc_count_by_cell[cell_id] = excluded_fc_count_by_cell.get(cell_id, 0) + 1
        except Exception as e:
            errors.append({"file_id": row["file_id"], "error": f"excluded file read error: {e}"})

    log.info(f"  {len(excluded_fc_cells)} cells had excluded sources, {exc_total_rows} excluded file-cells")

    # Map tracking fields
    result_cell_ids = set(result["cell_id"])
    original_cell_ids = set(original["cell_id"])

    # Cells in original but not in qcfiltered (lost all coverage)
    lost_cells = original_cell_ids - result_cell_ids
    log.info(f"  Lost cells (all coverage removed): {len(lost_cells):,}")

    # Build tracking columns using vectorized mapping
    result["n_excluded_file_cells_in_original"] = result["cell_id"].map(
        excluded_fc_count_by_cell).fillna(0).astype(int)
    result["n_excluded_points_in_original"] = result["cell_id"].map(
        excluded_points_by_cell).fillna(0).astype(int)
    result["had_excluded_source_in_original"] = result["cell_id"].isin(excluded_fc_cells)

    # ── 7. Final column order ──────────────────────────────────────────
    final_cols = [
        "cell_id", "cell_size", "lon_bin", "lat_bin", "lon_center", "lat_center",
        "median_depth_file_balanced", "median_elev_file_balanced",
        "mean_depth_file_balanced", "mean_elev_file_balanced",
        "weighted_mean_depth_point_weighted", "weighted_mean_elev_point_weighted",
        "std_depth_between_file_cells",
        "q25_depth_between_file_cells", "q75_depth_between_file_cells",
        "iqr_depth_between_file_cells",
        "min_depth_file_cell", "max_depth_file_cell", "range_depth_file_cell",
        "n_points_total", "n_file_cells", "n_files", "n_cruises_guess", "n_subzips",
        "n_3col_file_cells", "n_6col_file_cells",
        "dominant_file_id", "dominant_cruise_id_guess",
        "dominant_track_kind", "dominant_data_layout",
        "source_dataset",
        "qcfiltered", "quality_filter_version",
        "n_excluded_file_cells_in_original", "n_excluded_points_in_original",
        "had_excluded_source_in_original",
    ]
    result = result[[c for c in final_cols if c in result.columns]].copy()
    result.sort_values("cell_id", inplace=True)
    result.reset_index(drop=True, inplace=True)

    return result, original, lost_cells, excluded_fc_cells, excluded_points_by_cell, fcm_included, fcm_excluded, errors, read_errors


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def generate_report(
    result: pd.DataFrame,
    original: pd.DataFrame,
    lost_cells: set,
    excluded_fc_cells: set,
    excluded_points_by_cell: dict,
    fcm_included: pd.DataFrame,
    fcm_excluded: pd.DataFrame,
    errors: list,
    read_errors: int,
    elapsed: float,
) -> str:
    lines = []
    lines.append("# QC-Filtered Cells Report (1min)")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Elapsed: {elapsed:.1f}s")
    lines.append("")

    n_orig = len(original)
    n_qcf = len(result)
    n_lost = len(lost_cells)
    pct_lost = 100.0 * n_lost / n_orig if n_orig > 0 else 0

    orig_points = int(original["n_points_total"].sum())
    qcf_points = int(result["n_points_total"].sum())
    excluded_points = orig_points - qcf_points

    orig_fc = int(original["n_file_cells"].sum())
    qcf_fc = int(result["n_file_cells"].sum())
    excluded_fc = orig_fc - qcf_fc

    n_had_exc = int(result["had_excluded_source_in_original"].sum())
    n_had_exc_total = len(excluded_fc_cells)  # all original cells with excluded sources (retained + lost)
    n_still_covered = int(result[result["had_excluded_source_in_original"]].shape[0])

    # 1. 原始 cells 数
    lines.append("## 1. 原始 cells_1min cell 数")
    lines.append("")
    lines.append(f"**{n_orig:,}** cells")
    lines.append("")

    # 2. qcfiltered cell 数
    lines.append("## 2. qcfiltered cell 数")
    lines.append("")
    lines.append(f"**{n_qcf:,}** cells")
    lines.append("")

    # 3. lost cell 数
    lines.append("## 3. lost cell 数")
    lines.append("")
    lines.append(f"**{n_lost:,}** cells lost all coverage")
    lines.append("")

    # 4. lost cell 比例
    lines.append("## 4. lost cell 比例")
    lines.append("")
    lines.append(f"**{pct_lost:.2f}%** ({n_lost:,} / {n_orig:,})")
    lines.append("")

    # 5. 原始 n_points_total 总和
    lines.append("## 5. 原始 n_points_total 总和")
    lines.append("")
    lines.append(f"**{orig_points:,}** points")
    lines.append("")

    # 6. qcfiltered n_points_total 总和
    lines.append("## 6. qcfiltered n_points_total 总和")
    lines.append("")
    lines.append(f"**{qcf_points:,}** points")
    lines.append("")

    # 7. 排除 points 数
    lines.append("## 7. 排除 points 数")
    lines.append("")
    lines.append(f"**{excluded_points:,}** points removed ({100.0 * excluded_points / orig_points:.2f}%)")
    lines.append("")

    # 8. 原始 file-cell 总行数
    lines.append("## 8. 原始 file-cell 总行数")
    lines.append("")
    lines.append(f"**{orig_fc:,}** file-cells")
    lines.append("")

    # 9. qcfiltered file-cell 总行数
    lines.append("## 9. qcfiltered file-cell 总行数")
    lines.append("")
    lines.append(f"**{qcf_fc:,}** file-cells")
    lines.append("")

    # 10. 排除 file-cell 数
    lines.append("## 10. 排除 file-cell 数")
    lines.append("")
    lines.append(f"**{excluded_fc:,}** file-cells removed ({100.0 * excluded_fc / orig_fc:.2f}%)")
    lines.append("")

    # 11. had_excluded_source_in_original=True 的 cell 数
    lines.append("## 11. had_excluded_source_in_original=True 的 cell 数")
    lines.append("")
    lines.append(f"**{n_had_exc_total:,}** cells had at least one excluded source in original")
    lines.append(f"  - {n_had_exc:,} retained cells with excluded sources")
    lines.append(f"  - {n_lost - (n_lost - n_had_exc_total + n_had_exc):,} lost cells that had only excluded sources")
    lines.append("")

    # 12. 排除后仍有覆盖的 cell 数
    lines.append("## 12. 排除后仍有覆盖的 cell 数")
    lines.append("")
    lines.append(f"**{n_still_covered:,}** cells with excluded sources still have coverage")
    lines.append("")

    # 13. 排除后失去全部覆盖的 cell 数
    lines.append("## 13. 排除后失去全部覆盖的 cell 数")
    lines.append("")
    lines.append(f"**{n_lost:,}** cells lost all coverage")
    lines.append("")

    # 14-15: Depth shift analysis
    lines.append("## 14. median_depth_file_balanced 改变的 cell 数")
    lines.append("")
    merged = original[["cell_id", "median_depth_file_balanced"]].merge(
        result[["cell_id", "median_depth_file_balanced"]].rename(
            columns={"median_depth_file_balanced": "qcf_median_depth"}),
        on="cell_id", how="inner"
    )
    merged["shift"] = merged["qcf_median_depth"] - merged["median_depth_file_balanced"]
    n_changed = int((merged["shift"].abs() > 0.01).sum())
    lines.append(f"**{n_changed:,}** cells with |shift| > 0.01m (out of {len(merged):,} common cells)")
    lines.append("")

    # 15. depth shift 统计
    lines.append("## 15. depth shift 统计")
    lines.append("")
    shift = merged["shift"]
    shift_abs = shift.abs()
    mad = float((shift - shift.median()).abs().median())

    lines.append("qcfiltered.median_depth - original.median_depth:")
    lines.append("")
    lines.append("| Stat | Value (m) |")
    lines.append("|------|-----------|")
    lines.append(f"| min | {float(shift.min()):.2f} |")
    lines.append(f"| p05 | {float(shift.quantile(0.05)):.2f} |")
    lines.append(f"| p50 (median) | {float(shift.quantile(0.50)):.2f} |")
    lines.append(f"| p95 | {float(shift.quantile(0.95)):.2f} |")
    lines.append(f"| max | {float(shift.max()):.2f} |")
    lines.append(f"| MAD | {mad:.2f} |")
    lines.append(f"| RMSE | {float(np.sqrt((shift**2).mean())):.2f} |")
    lines.append(f"| mean | {float(shift.mean()):.4f} |")
    lines.append("")

    # 16. 最大 depth shift 前 50 个 cell
    lines.append("## 16. 最大 depth shift 前 50 个 cell")
    lines.append("")
    top50 = merged.nlargest(50, "shift")
    lines.append("| cell_id | original_depth | qcfiltered_depth | shift (m) |")
    lines.append("|---------|---------------|-----------------|-----------|")
    for _, r in top50.iterrows():
        lines.append(f"| {r['cell_id']} | {r['median_depth_file_balanced']:.1f} | {r['qcf_median_depth']:.1f} | {r['shift']:.2f} |")
    lines.append("")

    # Also bottom 10 (largest negative shifts)
    lines.append("### 最大负 shift (最浅) 前 10:")
    lines.append("")
    bot10 = merged.nsmallest(10, "shift")
    lines.append("| cell_id | original_depth | qcfiltered_depth | shift (m) |")
    lines.append("|---------|---------------|-----------------|-----------|")
    for _, r in bot10.iterrows():
        lines.append(f"| {r['cell_id']} | {r['median_depth_file_balanced']:.1f} | {r['qcf_median_depth']:.1f} | {r['shift']:.2f} |")
    lines.append("")

    # 17. 是否存在重复 cell_id
    lines.append("## 17. 是否存在重复 cell_id")
    lines.append("")
    n_dup = int(result.duplicated(subset=["cell_id"]).sum())
    lines.append(f"{'❌ Yes (' + str(n_dup) + ')' if n_dup > 0 else '✅ None'}")
    lines.append("")

    # 18. 是否存在 NaN/inf
    lines.append("## 18. 是否存在 NaN/inf")
    lines.append("")
    numeric_cols = result.select_dtypes(include=[np.number]).columns
    n_nan = int(result[numeric_cols].isna().sum().sum())
    n_inf = int(np.isinf(result[numeric_cols].values).sum())
    lines.append(f"- NaN values: {'❌ ' + str(n_nan) if n_nan > 0 else '✅ None'}")
    lines.append(f"- Inf values: {'❌ ' + str(n_inf) if n_inf > 0 else '✅ None'}")
    lines.append("")

    # 19. 结论
    lines.append("## 19. 结论：qcfiltered cells 是否可信")
    lines.append("")
    can_proceed = (n_dup == 0 and n_inf == 0)
    if can_proceed:
        lines.append("✅ **qcfiltered cells 可信，可以作为 primary validation cell product。**")
        lines.append(f"- 排除 {len(fcm_excluded)} 个文件，保留 {len(fcm_included)} 个文件")
        lines.append(f"- 原始 {n_orig:,} cells → qcfiltered {n_qcf:,} cells (失去 {n_lost:,}, {pct_lost:.2f}%)")
        lines.append(f"- {n_changed:,} cells 的 median_depth 发生变化")
        lines.append(f"- 最大正 shift: {float(shift.max()):.2f}m, 最大负 shift: {float(shift.min()):.2f}m")
        if errors:
            lines.append(f"- ⚠️ {read_errors} read errors (see error TSV)")
    else:
        lines.append("❌ **存在问题，不建议作为 primary product。**")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Rebuild qcfiltered cells from file_cells_1min")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing output files")
    parser.add_argument("--estimate-only", action="store_true",
                        help="Only estimate, do not process")
    args = parser.parse_args()

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    log = logging.getLogger("06c")

    t0 = time.time()
    log.info("=" * 60)
    log.info("06c_rebuild_cells_1min_qcfiltered.py  START")
    log.info(f"  --overwrite={args.overwrite}  --estimate-only={args.estimate_only}")

    # Validate inputs
    for name, path in INPUTS.items():
        if not path.exists():
            log.error(f"Input not found: {name} = {path}")
            sys.exit(1)

    # Check outputs
    if not args.estimate_only:
        for name, path in OUTPUTS.items():
            if path.exists() and not args.overwrite:
                log.error(f"Output exists (use --overwrite): {name} = {path}")
                sys.exit(1)

    result = run(args)
    if result is None:
        if args.estimate_only:
            log.info("06c  ESTIMATE ONLY DONE")
            return
        else:
            log.error("run() returned None — aborting")
            sys.exit(1)

    cells, original, lost_cells, excluded_fc_cells, excluded_points_by_cell, fcm_included, fcm_excluded, errors, read_errors = result
    elapsed = time.time() - t0

    # Generate report
    report_text = generate_report(
        cells, original, lost_cells, excluded_fc_cells, excluded_points_by_cell,
        fcm_included, fcm_excluded, errors, read_errors, elapsed)

    # Write outputs
    log.info("Writing output files ...")
    atomic_write_parquet(cells, OUTPUTS["cells_parquet"])
    log.info(f"  Wrote {OUTPUTS['cells_parquet']}")

    # Manifest
    manifest = pd.DataFrame([{
        "output_path": str(OUTPUTS["cells_parquet"].relative_to(PROJECT)),
        "n_cells": len(cells),
        "n_points_total": int(cells["n_points_total"].sum()),
        "n_excluded_files": len(fcm_excluded),
        "n_included_files": len(fcm_included),
        "quality_filter_version": "v1_extreme_bias_exclusion",
        "status": "ok",
    }])
    atomic_write_parquet(manifest, OUTPUTS["manifest_parquet"])
    atomic_write_tsv(manifest, OUTPUTS["manifest_tsv"])
    log.info(f"  Wrote manifest")

    atomic_write_text(report_text, OUTPUTS["report"])
    log.info(f"  Wrote report")

    # Write error TSV
    if errors:
        err_df = pd.DataFrame(errors)
        atomic_write_tsv(err_df, ERROR_PATH)
        log.info(f"  Wrote {len(errors)} errors to {ERROR_PATH}")
    else:
        err_df = pd.DataFrame(columns=["file_id", "error"])
        atomic_write_tsv(err_df, ERROR_PATH)

    # Summary
    log.info("=" * 60)
    log.info(f"Original cells: {len(original):,}")
    log.info(f"QC-filtered cells: {len(cells):,}")
    log.info(f"Lost cells: {len(lost_cells):,}")
    log.info(f"Read errors: {read_errors}")
    log.info(f"Elapsed: {elapsed:.1f}s")
    log.info("06c_rebuild_cells_1min_qcfiltered.py  DONE")

    print(report_text)


if __name__ == "__main__":
    main()
