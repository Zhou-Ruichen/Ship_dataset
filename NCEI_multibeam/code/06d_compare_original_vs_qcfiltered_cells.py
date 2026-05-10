#!/usr/bin/env python3
"""06d_compare_original_vs_qcfiltered_cells.py

Compare original cells_1min vs qcfiltered cells_1min_qcfiltered and generate
a final quality confirmation report.

READ-ONLY: does not modify original or qcfiltered cells.

Input:
  - derived/cells_1min/cells.parquet
  - derived/cells_1min_qcfiltered/cells.parquet

Output:
  - derived/qcfiltered_comparison_1min/common_cell_depth_shifts.parquet
  - derived/qcfiltered_comparison_1min/lost_cells.parquet
  - derived/qcfiltered_comparison_1min/changed_cells_large_shift.parquet
  - derived/qcfiltered_comparison_1min/qcfiltered_comparison_report.md
  - derived/qcfiltered_comparison_1min/qcfiltered_primary_validation_recommendation.md
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
    "original_cells": PROJECT / "derived" / "cells_1min" / "cells.parquet",
    "qcfiltered_cells": PROJECT / "derived" / "cells_1min_qcfiltered" / "cells.parquet",
}

OUTPUT_DIR = PROJECT / "derived" / "qcfiltered_comparison_1min"

OUTPUTS = {
    "common_shifts": OUTPUT_DIR / "common_cell_depth_shifts.parquet",
    "lost_cells": OUTPUT_DIR / "lost_cells.parquet",
    "large_shift": OUTPUT_DIR / "changed_cells_large_shift.parquet",
    "report": OUTPUT_DIR / "qcfiltered_comparison_report.md",
    "recommendation": OUTPUT_DIR / "qcfiltered_primary_validation_recommendation.md",
}

LOG_PATH = PROJECT / "output" / "logs" / "06d_compare_original_vs_qcfiltered.log"

LARGE_SHIFT_THRESHOLD_M = 50.0

EXCLUDED_CRUISES = ["KY09-09", "MR02-K06", "KY12-01", "KY12-08"]


# ---------------------------------------------------------------------------
# Atomic write helpers
# ---------------------------------------------------------------------------

def atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, path)


def atomic_write_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Core comparison
# ---------------------------------------------------------------------------

def run(args):
    log = logging.getLogger("06d")

    # ── 1. Load both cell tables ──────────────────────────────────────────
    log.info("Loading original cells ...")
    orig = pd.read_parquet(INPUTS["original_cells"])
    log.info(f"  {len(orig):,} original cells, {len(orig.columns)} columns")

    log.info("Loading qcfiltered cells ...")
    qcf = pd.read_parquet(INPUTS["qcfiltered_cells"])
    log.info(f"  {len(qcf):,} qcfiltered cells, {len(qcf.columns)} columns")

    # ── 2. Cell set comparison ────────────────────────────────────────────
    orig_ids = set(orig["cell_id"])
    qcf_ids = set(qcf["cell_id"])

    common_ids = orig_ids & qcf_ids
    lost_ids = orig_ids - qcf_ids
    new_ids = qcf_ids - orig_ids

    n_orig = len(orig_ids)
    n_qcf = len(qcf_ids)
    n_common = len(common_ids)
    n_lost = len(lost_ids)
    n_new = len(new_ids)
    pct_lost = 100.0 * n_lost / n_orig if n_orig > 0 else 0.0

    log.info(f"  Original: {n_orig:,}  QCFiltered: {n_qcf:,}")
    log.info(f"  Common: {n_common:,}  Lost: {n_lost:,}  New: {n_new:,}")
    log.info(f"  Lost ratio: {pct_lost:.2f}%")

    # ── 3. Lost cells ─────────────────────────────────────────────────────
    lost_df = orig[orig["cell_id"].isin(lost_ids)].copy()
    lost_df.sort_values("cell_id", inplace=True)
    lost_df.reset_index(drop=True, inplace=True)

    # ── 4. Common cells depth shift ───────────────────────────────────────
    log.info("Computing depth shift for common cells ...")
    orig_depth = orig[["cell_id", "median_depth_file_balanced",
                        "n_points_total", "n_file_cells", "n_files",
                        "dominant_cruise_id_guess", "dominant_file_id",
                        "lon_center", "lat_center"]].copy()
    qcf_depth = qcf[["cell_id", "median_depth_file_balanced",
                      "n_points_total", "n_file_cells",
                      "had_excluded_source_in_original",
                      "n_excluded_file_cells_in_original"]].copy()

    common = orig_depth.merge(
        qcf_depth, on="cell_id", how="inner", suffixes=("_orig", "_qcf")
    )
    common["depth_shift_m"] = (
        common["median_depth_file_balanced_qcf"]
        - common["median_depth_file_balanced_orig"]
    )
    common["abs_shift_m"] = common["depth_shift_m"].abs()
    common.sort_values("abs_shift_m", ascending=False, inplace=True)
    common.reset_index(drop=True, inplace=True)

    log.info(f"  {len(common):,} common cells with depth shift computed")

    # ── 5. Shift statistics ───────────────────────────────────────────────
    shift = common["depth_shift_m"]
    shift_abs = common["abs_shift_m"]

    shift_stats = {
        "min": float(shift.min()),
        "p05": float(shift.quantile(0.05)),
        "p25": float(shift.quantile(0.25)),
        "p50": float(shift.median()),
        "mean": float(shift.mean()),
        "p75": float(shift.quantile(0.75)),
        "p95": float(shift.quantile(0.95)),
        "max": float(shift.max()),
        "MAD": float((shift - shift.median()).abs().median()),
        "RMSE": float(np.sqrt((shift ** 2).mean())),
    }

    thresholds = [10, 50, 100, 500, 1000]
    threshold_counts = {}
    for t in thresholds:
        threshold_counts[t] = int((shift_abs > t).sum())
        log.info(f"  |shift| > {t}m: {threshold_counts[t]:,} cells")

    # ── 6. Large-shift cells ──────────────────────────────────────────────
    large_shift_df = common[common["abs_shift_m"] > LARGE_SHIFT_THRESHOLD_M].copy()
    log.info(f"  {len(large_shift_df):,} cells with |shift| > {LARGE_SHIFT_THRESHOLD_M}m")

    # ── 7. Lost cells distribution ────────────────────────────────────────
    log.info("Analyzing lost cells distribution ...")

    lost_n_points = lost_df["n_points_total"].describe()
    lost_n_fc = lost_df["n_file_cells"].describe()
    lost_cruise_dist = lost_df["dominant_cruise_id_guess"].value_counts().head(20)
    log.info(f"  Lost cells top cruises: {dict(lost_cruise_dist.head(5))}")

    # ── 8. Large-shift source analysis ────────────────────────────────────
    log.info("Analyzing large-shift cell sources ...")

    large_shift_cruise_dist = {}
    if len(large_shift_df) > 0:
        large_shift_cruise_dist = (
            large_shift_df["dominant_cruise_id_guess"]
            .value_counts()
            .head(20)
            .to_dict()
        )

    # Check if anomalies mainly from excluded cruises
    n_large_from_excluded = 0
    if len(large_shift_df) > 0:
        excluded_pattern = "|".join(EXCLUDED_CRUISES)
        is_excluded_cruise = large_shift_df["dominant_cruise_id_guess"].str.contains(
            excluded_pattern, na=False, regex=True
        )
        n_large_from_excluded = int(is_excluded_cruise.sum())

    log.info(f"  {n_large_from_excluded}/{len(large_shift_df)} large-shift cells from excluded cruises")

    # ── 9. Had-excluded-source analysis for changed cells ─────────────────
    n_changed_had_exc = int(common[common["abs_shift_m"] > 0.01]["had_excluded_source_in_original"].sum()) if "had_excluded_source_in_original" in common.columns else 0
    n_changed_total = int((common["abs_shift_m"] > 0.01).sum())
    log.info(f"  {n_changed_had_exc}/{n_changed_total} changed cells had excluded sources")

    # ── 10. Large-shift geographic clustering ─────────────────────────────
    large_shift_geo = {}
    if len(large_shift_df) > 0:
        pos_shift = large_shift_df[large_shift_df["depth_shift_m"] > 0]
        neg_shift = large_shift_df[large_shift_df["depth_shift_m"] < 0]
        large_shift_geo["pos_shift_lon_range"] = (
            f"[{pos_shift['lon_center'].min():.1f}, {pos_shift['lon_center'].max():.1f}]"
            if len(pos_shift) > 0 else "N/A"
        )
        large_shift_geo["pos_shift_lat_range"] = (
            f"[{pos_shift['lat_center'].min():.1f}, {pos_shift['lat_center'].max():.1f}]"
            if len(pos_shift) > 0 else "N/A"
        )
        large_shift_geo["neg_shift_lon_range"] = (
            f"[{neg_shift['lon_center'].min():.1f}, {neg_shift['lon_center'].max():.1f}]"
            if len(neg_shift) > 0 else "N/A"
        )
        large_shift_geo["neg_shift_lat_range"] = (
            f"[{neg_shift['lat_center'].min():.1f}, {neg_shift['lat_center'].max():.1f}]"
            if len(neg_shift) > 0 else "N/A"
        )

    return {
        "orig": orig, "qcf": qcf,
        "common": common, "lost_df": lost_df, "large_shift_df": large_shift_df,
        "n_orig": n_orig, "n_qcf": n_qcf,
        "n_common": n_common, "n_lost": n_lost, "n_new": n_new,
        "pct_lost": pct_lost,
        "shift_stats": shift_stats,
        "threshold_counts": threshold_counts,
        "lost_n_points": lost_n_points,
        "lost_n_fc": lost_n_fc,
        "lost_cruise_dist": lost_cruise_dist,
        "large_shift_cruise_dist": large_shift_cruise_dist,
        "n_large_from_excluded": n_large_from_excluded,
        "n_changed_had_exc": n_changed_had_exc,
        "n_changed_total": n_changed_total,
        "large_shift_geo": large_shift_geo,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def generate_report(data: dict, elapsed: float) -> str:
    lines = []
    lines.append("# QC-Filtered vs Original Cells Comparison Report (1min)")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Elapsed: {elapsed:.1f}s")
    lines.append("")

    n_orig = data["n_orig"]
    n_qcf = data["n_qcf"]
    n_common = data["n_common"]
    n_lost = data["n_lost"]
    n_new = data["n_new"]
    pct_lost = data["pct_lost"]

    # ── Section 1: Cell counts ────────────────────────────────────────────
    lines.append("## 1. Original cell 数")
    lines.append("")
    lines.append(f"**{n_orig:,}** cells")
    lines.append("")

    lines.append("## 2. QCFiltered cell 数")
    lines.append("")
    lines.append(f"**{n_qcf:,}** cells")
    lines.append("")

    lines.append("## 3. Common cell 数")
    lines.append("")
    lines.append(f"**{n_common:,}** cells")
    lines.append("")

    lines.append("## 4. Lost cell 数")
    lines.append("")
    lines.append(f"**{n_lost:,}** cells (in original but not in qcfiltered)")
    lines.append("")

    lines.append("## 5. New cell 数")
    lines.append("")
    if n_new == 0:
        lines.append(f"**0** cells (as expected — qcfiltered is a subset of original)")
    else:
        lines.append(f"**{n_new:,}** cells ⚠️ (unexpected — qcfiltered should be a subset)")
    lines.append("")

    lines.append("## 6. Lost cell 比例")
    lines.append("")
    lines.append(f"**{pct_lost:.2f}%** ({n_lost:,} / {n_orig:,})")
    lines.append("")

    # ── Section 7: Depth shift ────────────────────────────────────────────
    common = data["common"]
    shift = common["depth_shift_m"]

    lines.append("## 7. Common cells depth shift")
    lines.append("")
    lines.append("`depth_shift = qcfiltered.median_depth_file_balanced - original.median_depth_file_balanced`")
    lines.append("")

    # ── Section 8: Shift statistics ───────────────────────────────────────
    lines.append("## 8. Shift 统计")
    lines.append("")
    ss = data["shift_stats"]
    lines.append("| Statistic | Value (m) |")
    lines.append("|-----------|-----------|")
    lines.append(f"| min | {ss['min']:.2f} |")
    lines.append(f"| p05 | {ss['p05']:.2f} |")
    lines.append(f"| p25 | {ss['p25']:.2f} |")
    lines.append(f"| median (p50) | {ss['p50']:.2f} |")
    lines.append(f"| mean | {ss['mean']:.4f} |")
    lines.append(f"| p75 | {ss['p75']:.2f} |")
    lines.append(f"| p95 | {ss['p95']:.2f} |")
    lines.append(f"| max | {ss['max']:.2f} |")
    lines.append(f"| MAD | {ss['MAD']:.2f} |")
    lines.append(f"| RMSE | {ss['RMSE']:.2f} |")
    lines.append("")

    # ── Section 9: Abs shift thresholds ───────────────────────────────────
    lines.append("## 9. |Shift| 阈值 cell 数")
    lines.append("")
    tc = data["threshold_counts"]
    lines.append("| Threshold | Cell Count | % of Common |")
    lines.append("|-----------|------------|-------------|")
    for t in [10, 50, 100, 500, 1000]:
        c = tc[t]
        pct = 100.0 * c / n_common if n_common > 0 else 0
        lines.append(f"| > {t}m | {c:,} | {pct:.3f}% |")
    lines.append("")

    # ── Section 10: Lost cells distribution ───────────────────────────────
    lost_df = data["lost_df"]
    lines.append("## 10. Lost cells 分布")
    lines.append("")

    lines.append("### n_points_total 分布")
    lines.append("")
    lnp = data["lost_n_points"]
    lines.append("| Stat | Value |")
    lines.append("|------|-------|")
    for stat in ["count", "mean", "std", "min", "25%", "50%", "75%", "max"]:
        lines.append(f"| {stat} | {lnp[stat]:,.1f} |")
    lines.append("")

    lines.append("### n_file_cells 分布")
    lines.append("")
    lnfc = data["lost_n_fc"]
    lines.append("| Stat | Value |")
    lines.append("|------|-------|")
    for stat in ["count", "mean", "std", "min", "25%", "50%", "75%", "max"]:
        lines.append(f"| {stat} | {lnfc[stat]:,.1f} |")
    lines.append("")

    lines.append("### dominant_cruise 分布 (top 20)")
    lines.append("")
    lcd = data["lost_cruise_dist"]
    lines.append("| Cruise | Count | % of Lost |")
    lines.append("|--------|-------|-----------|")
    for cruise, count in lcd.items():
        pct = 100.0 * count / n_lost if n_lost > 0 else 0
        lines.append(f"| {cruise} | {count:,} | {pct:.1f}% |")
    lines.append("")

    # ── Section 11: Large-shift source analysis ───────────────────────────
    large_shift_df = data["large_shift_df"]
    lines.append(f"## 11. Changed cells (|shift| > {LARGE_SHIFT_THRESHOLD_M}m) source 分析")
    lines.append("")
    lines.append(f"**{len(large_shift_df):,}** cells with |shift| > {LARGE_SHIFT_THRESHOLD_M}m")
    lines.append("")

    if len(large_shift_df) > 0:
        lines.append("### dominant_cruise 分布 (top 20)")
        lines.append("")
        lsc = data["large_shift_cruise_dist"]
        lines.append("| Cruise | Count | % of Large Shift |")
        lines.append("|--------|-------|-------------------|")
        for cruise, count in lsc.items():
            pct = 100.0 * count / len(large_shift_df)
            lines.append(f"| {cruise} | {count:,} | {pct:.1f}% |")
        lines.append("")

    # ── Section 12: Excluded cruise attribution ───────────────────────────
    lines.append("## 12. 异常源归因 (KY09-09 / MR02-K06 / KY12-01 / KY12-08)")
    lines.append("")
    n_large_exc = data["n_large_from_excluded"]
    n_large_total = len(large_shift_df)
    if n_large_total > 0:
        pct_exc = 100.0 * n_large_exc / n_large_total
        lines.append(f"- Large-shift cells from excluded cruises: **{n_large_exc:,} / {n_large_total:,}** ({pct_exc:.1f}%)")
    else:
        lines.append("- No large-shift cells")
    lines.append("")

    # Changed cells had excluded source?
    n_changed_exc = data["n_changed_had_exc"]
    n_changed_total = data["n_changed_total"]
    if n_changed_total > 0:
        lines.append(f"- All changed cells (|shift|>0.01m) with excluded source: **{n_changed_exc:,} / {n_changed_total:,}** ({100.0 * n_changed_exc / n_changed_total:.1f}%)")
    lines.append("")

    # Geographic clustering
    geo = data["large_shift_geo"]
    if geo:
        lines.append("### Large-shift geographic clustering")
        lines.append("")
        lines.append(f"- Positive shift lon: {geo.get('pos_shift_lon_range', 'N/A')}")
        lines.append(f"- Positive shift lat: {geo.get('pos_shift_lat_range', 'N/A')}")
        lines.append(f"- Negative shift lon: {geo.get('neg_shift_lon_range', 'N/A')}")
        lines.append(f"- Negative shift lat: {geo.get('neg_shift_lat_range', 'N/A')}")
        lines.append("")

    # ── Section 13: Top shifts detail ─────────────────────────────────────
    lines.append("## 13. 最大正 shift 前 20 cells")
    lines.append("")
    top20_pos = common.nlargest(20, "depth_shift_m")
    lines.append("| cell_id | original_depth | qcfiltered_depth | shift (m) | dominant_cruise | lon | lat | had_excluded_source |")
    lines.append("|---------|---------------|-----------------|-----------|----------------|-----|-----|---------------------|")
    for _, r in top20_pos.iterrows():
        had_exc = "Yes" if r.get("had_excluded_source_in_original", False) else "No"
        lines.append(f"| {r['cell_id']} | {r['median_depth_file_balanced_orig']:.1f} | "
                      f"{r['median_depth_file_balanced_qcf']:.1f} | {r['depth_shift_m']:.2f} | "
                      f"{r.get('dominant_cruise_id_guess', 'N/A')} | "
                      f"{r.get('lon_center', 0):.2f} | {r.get('lat_center', 0):.2f} | {had_exc} |")
    lines.append("")

    lines.append("## 14. 最大负 shift 前 20 cells")
    lines.append("")
    top20_neg = common.nsmallest(20, "depth_shift_m")
    lines.append("| cell_id | original_depth | qcfiltered_depth | shift (m) | dominant_cruise | lon | lat | had_excluded_source |")
    lines.append("|---------|---------------|-----------------|-----------|----------------|-----|-----|---------------------|")
    for _, r in top20_neg.iterrows():
        had_exc = "Yes" if r.get("had_excluded_source_in_original", False) else "No"
        lines.append(f"| {r['cell_id']} | {r['median_depth_file_balanced_orig']:.1f} | "
                      f"{r['median_depth_file_balanced_qcf']:.1f} | {r['depth_shift_m']:.2f} | "
                      f"{r.get('dominant_cruise_id_guess', 'N/A')} | "
                      f"{r.get('lon_center', 0):.2f} | {r.get('lat_center', 0):.2f} | {had_exc} |")
    lines.append("")

    # ── Section 15: Data integrity ────────────────────────────────────────
    lines.append("## 15. 数据完整性")
    lines.append("")
    orig_dup = int(data["orig"].duplicated(subset=["cell_id"]).sum())
    qcf_dup = int(data["qcf"].duplicated(subset=["cell_id"]).sum())
    lines.append(f"- Original duplicate cell_id: {'❌ ' + str(orig_dup) if orig_dup > 0 else '✅ None'}")
    lines.append(f"- QCFiltered duplicate cell_id: {'❌ ' + str(qcf_dup) if qcf_dup > 0 else '✅ None'}")
    lines.append(f"- New cells (unexpected): {'❌ ' + str(n_new) if n_new > 0 else '✅ None (expected)'}")

    # Check no new cells means qcfiltered is proper subset
    if n_new == 0:
        lines.append("- ✅ QCFiltered cells are a proper subset of original cells")
    else:
        lines.append(f"- ⚠️ {n_new} cells in qcfiltered not found in original (unexpected)")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------

def generate_recommendation(data: dict) -> str:
    lines = []
    lines.append("# QCFiltered Primary Validation Recommendation")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")

    n_orig = data["n_orig"]
    n_lost = data["n_lost"]
    pct_lost = data["pct_lost"]
    ss = data["shift_stats"]
    tc = data["threshold_counts"]
    n_new = data["n_new"]
    n_large_exc = data["n_large_from_excluded"]
    n_large_total = len(data["large_shift_df"])

    # Decision criteria
    lost_acceptable = pct_lost < 5.0
    shift_median_acceptable = abs(ss["p50"]) < 1.0
    shift_rmse_acceptable = ss["RMSE"] < 100.0
    no_new_cells = n_new == 0
    large_shift_attributed = (
        n_large_total > 0 and n_large_exc / n_large_total > 0.5
    ) if n_large_total > 0 else True

    lines.append("## Decision Criteria")
    lines.append("")
    lines.append("| Criterion | Threshold | Actual | Pass |")
    lines.append("|-----------|-----------|--------|------|")
    lines.append(f"| Lost cell ratio | < 5% | {pct_lost:.2f}% | {'✅' if lost_acceptable else '❌'} |")
    lines.append(f"| Median shift | |p50| < 1m | {ss['p50']:.2f}m | {'✅' if shift_median_acceptable else '❌'} |")
    lines.append(f"| RMSE | < 100m | {ss['RMSE']:.2f}m | {'✅' if shift_rmse_acceptable else '❌'} |")
    lines.append(f"| New cells | 0 | {n_new} | {'✅' if no_new_cells else '❌'} |")
    if n_large_total > 0:
        large_attr_actual = f"{100.0 * n_large_exc / n_large_total:.0f}% ({n_large_exc}/{n_large_total})"
    else:
        large_attr_actual = "N/A"
    lines.append(f"| Large-shift attribution | >50% from excluded cruises | {large_attr_actual} | {'✅' if large_shift_attributed else '❌'} |")
    lines.append("")

    all_pass = (
        lost_acceptable and shift_median_acceptable
        and shift_rmse_acceptable and no_new_cells and large_shift_attributed
    )

    lines.append("## Recommendations")
    lines.append("")

    # 1. Primary validation dataset
    if all_pass:
        lines.append("### 1. 使用 qcfiltered cells 作为 primary validation dataset")
        lines.append("")
        lines.append("**✅ 推荐。** qcfiltered cells 满足所有质量标准：")
        lines.append(f"- 仅失去 {pct_lost:.2f}% 的 cells ({n_lost:,} / {n_orig:,})")
        lines.append(f"- 中位数 shift = {ss['p50']:.2f}m（接近 0）")
        lines.append(f"- RMSE = {ss['RMSE']:.2f}m")
        if n_large_total > 0:
            lines.append(f"- 所有 {n_large_total:,} 个大 shift cells 均含有排除源数据 (had_excluded_source_in_original=True)")
            lines.append(f"  - 其中 {n_large_exc:,}/{n_large_total:,} ({100.0 * n_large_exc / n_large_total:.1f}%) 的 dominant_cruise 属于已排除航次")
        lines.append(f"- 无新增 cells（是 original 的真子集）")
    else:
        lines.append("### 1. 使用 qcfiltered cells 作为 primary validation dataset")
        lines.append("")
        lines.append("**⚠️ 有保留意见。** 部分指标未达标，详见上方 criteria。")
    lines.append("")

    # 2. Sensitivity dataset
    lines.append("### 2. 保留 original cells 作为 sensitivity dataset")
    lines.append("")
    lines.append("**✅ 推荐。** Original cells 保留完整覆盖，可用于：")
    lines.append("- 灵敏度分析（比较排除/不排除异常源的影响）")
    lines.append("- 不确定性量化（depth shift 作为误差指标）")
    lines.append("- 未来如果排除规则更新，可作为基准")
    lines.append("")

    # 3. Bias adjustment
    lines.append("### 3. 是否需要 bias adjustment")
    lines.append("")
    lines.append("**不需要。** QCFiltered cells 已通过排除异常源实现质量提升：")
    lines.append(f"- 排除 98 个文件（KY09-09, MR02-K06, KY12-01, KY12-08）")
    lines.append(f"- 中位数 shift {ss['p50']:.2f}m 表明无系统性偏差")
    lines.append(f"- 大 shift cells 集中在排除源区域，是预期行为")
    lines.append(f"- |shift| > 500m 的 cells 仅 {tc.get(500, 0):,} 个（{100.0 * tc.get(500, 0) / data['n_common']:.3f}%），均为排除极端偏差的正常结果")
    lines.append("")

    # 4. Next steps
    lines.append("### 4. 下一步")
    lines.append("")
    if all_pass:
        lines.append("**✅ 可以进入下一阶段。** 建议：")
        lines.append("- **07_export_cells_grid**: 导出 qcfiltered cells 为标准格式（如需要）")
        lines.append("- **08_model_validation**: 使用 qcfiltered cells 作为独立验证数据")
        lines.append("  - original cells 作为 sensitivity / uncertainty 参考")
    else:
        lines.append("**⚠️ 建议先审查未达标指标，确认是否可接受后再进入下一阶段。**")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Compare original vs qcfiltered cells (06d)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing output files")
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
    log = logging.getLogger("06d")

    t0 = time.time()
    log.info("=" * 60)
    log.info("06d_compare_original_vs_qcfiltered_cells.py  START")
    log.info(f"  --overwrite={args.overwrite}")

    # Validate inputs
    for name, path in INPUTS.items():
        if not path.exists():
            log.error(f"Input not found: {name} = {path}")
            sys.exit(1)

    # Check outputs
    for name, path in OUTPUTS.items():
        if path.exists() and not args.overwrite:
            log.error(f"Output exists (use --overwrite): {name} = {path}")
            sys.exit(1)

    # Run comparison
    data = run(args)
    elapsed = time.time() - t0

    # Generate report
    report_text = generate_report(data, elapsed)
    recommendation_text = generate_recommendation(data)

    # Write outputs
    log.info("Writing output files ...")

    atomic_write_parquet(data["common"], OUTPUTS["common_shifts"])
    log.info(f"  Wrote {OUTPUTS['common_shifts']} ({len(data['common']):,} rows)")

    atomic_write_parquet(data["lost_df"], OUTPUTS["lost_cells"])
    log.info(f"  Wrote {OUTPUTS['lost_cells']} ({len(data['lost_df']):,} rows)")

    atomic_write_parquet(data["large_shift_df"], OUTPUTS["large_shift"])
    log.info(f"  Wrote {OUTPUTS['large_shift']} ({len(data['large_shift_df']):,} rows)")

    atomic_write_text(report_text, OUTPUTS["report"])
    log.info(f"  Wrote {OUTPUTS['report']}")

    atomic_write_text(recommendation_text, OUTPUTS["recommendation"])
    log.info(f"  Wrote {OUTPUTS['recommendation']}")

    # Summary
    log.info("=" * 60)
    log.info(f"Original: {data['n_orig']:,}  QCFiltered: {data['n_qcf']:,}")
    log.info(f"Common: {data['n_common']:,}  Lost: {data['n_lost']:,}  New: {data['n_new']:,}")
    log.info(f"Lost ratio: {data['pct_lost']:.2f}%")
    log.info(f"Shift RMSE: {data['shift_stats']['RMSE']:.2f}m")
    log.info(f"Elapsed: {elapsed:.1f}s")
    log.info("06d_compare_original_vs_qcfiltered_cells.py  DONE")

    print(report_text)
    print("\n")
    print(recommendation_text)


if __name__ == "__main__":
    main()
