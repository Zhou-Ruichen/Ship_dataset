#!/usr/bin/env python3
"""07_prepare_primary_validation_cells_1min.py

Generate cell-level shipborne validation tables for model validation.

Primary table: qcfiltered cells with quality tier and validation weight.
Sensitivity table: original cells for sensitivity analysis.

READ-ONLY: does not modify any existing data.

Input:
  - derived/cells_1min_qcfiltered/cells.parquet
  - derived/cells_1min/cells.parquet
  - derived/qcfiltered_comparison_1min/common_cell_depth_shifts.parquet
  - derived/qcfiltered_comparison_1min/lost_cells.parquet

Output:
  - derived/validation_cells_1min/primary_ship_validation_cells_1min.parquet
  - derived/validation_cells_1min/primary_ship_validation_cells_1min.tsv
  - derived/validation_cells_1min/sensitivity_original_ship_cells_1min.parquet
  - derived/validation_cells_1min/validation_cells_1min_summary.parquet
  - derived/validation_cells_1min/validation_cells_1min_report.md
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
    "qcfiltered_cells": PROJECT / "derived" / "cells_1min_qcfiltered" / "cells.parquet",
    "original_cells": PROJECT / "derived" / "cells_1min" / "cells.parquet",
    "common_shifts": PROJECT / "derived" / "qcfiltered_comparison_1min" / "common_cell_depth_shifts.parquet",
    "lost_cells": PROJECT / "derived" / "qcfiltered_comparison_1min" / "lost_cells.parquet",
}

OUTPUT_DIR = PROJECT / "derived" / "validation_cells_1min"

OUTPUTS = {
    "primary_parquet": OUTPUT_DIR / "primary_ship_validation_cells_1min.parquet",
    "primary_tsv": OUTPUT_DIR / "primary_ship_validation_cells_1min.tsv",
    "sensitivity_parquet": OUTPUT_DIR / "sensitivity_original_ship_cells_1min.parquet",
    "summary_parquet": OUTPUT_DIR / "validation_cells_1min_summary.parquet",
    "report": OUTPUT_DIR / "validation_cells_1min_report.md",
}

LOG_PATH = PROJECT / "output" / "logs" / "07_prepare_primary_validation_cells_1min.log"

TSV_MAX_ROWS = 10000


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
# Quality tier classification
# ---------------------------------------------------------------------------

def classify_tier(row):
    """A_tier: multi-cruise, multi-file-cell, low spread, sufficient points."""
    if (
        row["n_cruises_guess"] >= 2
        and row["n_file_cells"] >= 2
        and row["iqr_depth_between_file_cells"] <= 50
        and row["n_points_total"] >= 100
    ):
        return "A_tier"
    if (
        row["n_points_total"] >= 50
        and row["range_depth_file_cell"] <= 500
    ):
        return "B_tier"
    return "C_tier"


TIER_WEIGHT = {"A_tier": 1.0, "B_tier": 0.7, "C_tier": 0.4}


# ---------------------------------------------------------------------------
# Core flow
# ---------------------------------------------------------------------------

def run(args):
    log = logging.getLogger("07")

    # ── 1. Load qcfiltered cells ─────────────────────────────────────────
    log.info("Loading qcfiltered cells ...")
    qcf = pd.read_parquet(INPUTS["qcfiltered_cells"])
    log.info(f"  {len(qcf):,} qcfiltered cells")

    # ── 2. Build primary validation table ─────────────────────────────────
    log.info("Building primary validation table ...")
    primary = qcf[[
        "cell_id", "cell_size", "lon_bin", "lat_bin",
        "lon_center", "lat_center",
        "median_depth_file_balanced", "median_elev_file_balanced",
        "mean_depth_file_balanced", "mean_elev_file_balanced",
        "weighted_mean_depth_point_weighted", "weighted_mean_elev_point_weighted",
        "n_points_total", "n_file_cells", "n_files", "n_cruises_guess", "n_subzips",
        "std_depth_between_file_cells",
        "iqr_depth_between_file_cells",
        "range_depth_file_cell",
        "min_depth_file_cell", "max_depth_file_cell",
        "dominant_file_id", "dominant_cruise_id_guess",
        "dominant_track_kind", "dominant_data_layout",
        "source_dataset",
        "qcfiltered", "quality_filter_version",
        "n_excluded_file_cells_in_original", "n_excluded_points_in_original",
        "had_excluded_source_in_original",
    ]].copy()

    primary.rename(columns={
        "median_depth_file_balanced": "ship_depth_source",
        "median_elev_file_balanced": "ship_elev_source",
    }, inplace=True)

    primary["ship_depth_m"] = primary["ship_depth_source"]
    primary["ship_elev_m"] = primary["ship_elev_source"]

    # ── 3. Quality tier classification ────────────────────────────────────
    log.info("Classifying quality tiers ...")

    is_a = (
        (primary["n_cruises_guess"] >= 2)
        & (primary["n_file_cells"] >= 2)
        & (primary["iqr_depth_between_file_cells"] <= 50)
        & (primary["n_points_total"] >= 100)
    )
    is_b = (
        ~is_a
        & (primary["n_points_total"] >= 50)
        & (primary["range_depth_file_cell"] <= 500)
    )
    is_c = ~is_a & ~is_b

    primary["quality_tier"] = "C_tier"
    primary.loc[is_b, "quality_tier"] = "B_tier"
    primary.loc[is_a, "quality_tier"] = "A_tier"

    primary["validation_weight"] = primary["quality_tier"].map(TIER_WEIGHT)
    primary["use_for_primary_validation"] = True
    primary["use_for_sensitivity_validation"] = False

    tier_counts = primary["quality_tier"].value_counts()
    log.info(f"  A_tier: {tier_counts.get('A_tier', 0):,}")
    log.info(f"  B_tier: {tier_counts.get('B_tier', 0):,}")
    log.info(f"  C_tier: {tier_counts.get('C_tier', 0):,}")

    # ── 4. Final column order ─────────────────────────────────────────────
    primary_cols = [
        "cell_id", "cell_size", "lon_bin", "lat_bin", "lon_center", "lat_center",
        "ship_depth_m", "ship_elev_m",
        "ship_depth_source", "ship_elev_source",
        "n_points_total", "n_file_cells", "n_files", "n_cruises_guess", "n_subzips",
        "dominant_file_id", "dominant_cruise_id_guess",
        "dominant_track_kind", "dominant_data_layout",
        "std_depth_between_file_cells",
        "iqr_depth_between_file_cells",
        "range_depth_file_cell",
        "weighted_mean_depth_point_weighted",
        "weighted_mean_elev_point_weighted",
        "min_depth_file_cell", "max_depth_file_cell",
        "mean_depth_file_balanced", "mean_elev_file_balanced",
        "quality_tier", "validation_weight",
        "use_for_primary_validation", "use_for_sensitivity_validation",
        "qcfiltered", "quality_filter_version",
        "source_dataset",
        "n_excluded_file_cells_in_original", "n_excluded_points_in_original",
        "had_excluded_source_in_original",
    ]
    primary = primary[[c for c in primary_cols if c in primary.columns]].copy()
    primary.sort_values("cell_id", inplace=True)
    primary.reset_index(drop=True, inplace=True)

    # ── 5. Build sensitivity table from original cells ────────────────────
    log.info("Building sensitivity table from original cells ...")
    orig = pd.read_parquet(INPUTS["original_cells"])
    log.info(f"  {len(orig):,} original cells")

    sens = orig[[
        "cell_id", "cell_size", "lon_bin", "lat_bin",
        "lon_center", "lat_center",
        "median_depth_file_balanced", "median_elev_file_balanced",
        "n_points_total", "n_file_cells", "n_files", "n_cruises_guess", "n_subzips",
        "std_depth_between_file_cells",
        "iqr_depth_between_file_cells",
        "range_depth_file_cell",
        "weighted_mean_depth_point_weighted", "weighted_mean_elev_point_weighted",
        "min_depth_file_cell", "max_depth_file_cell",
        "dominant_file_id", "dominant_cruise_id_guess",
        "dominant_track_kind", "dominant_data_layout",
        "source_dataset",
    ]].copy()

    sens.rename(columns={
        "median_depth_file_balanced": "ship_depth_source",
        "median_elev_file_balanced": "ship_elev_source",
    }, inplace=True)
    sens["ship_depth_m"] = sens["ship_depth_source"]
    sens["ship_elev_m"] = sens["ship_elev_source"]

    sens["quality_tier"] = "original"
    sens["validation_weight"] = 0.0
    sens["use_for_primary_validation"] = False
    sens["use_for_sensitivity_validation"] = True
    sens["qcfiltered"] = False
    sens["quality_filter_version"] = "original_unfiltered"

    sens_cols = [
        "cell_id", "cell_size", "lon_bin", "lat_bin", "lon_center", "lat_center",
        "ship_depth_m", "ship_elev_m",
        "ship_depth_source", "ship_elev_source",
        "n_points_total", "n_file_cells", "n_files", "n_cruises_guess", "n_subzips",
        "dominant_file_id", "dominant_cruise_id_guess",
        "dominant_track_kind", "dominant_data_layout",
        "std_depth_between_file_cells",
        "iqr_depth_between_file_cells",
        "range_depth_file_cell",
        "weighted_mean_depth_point_weighted",
        "weighted_mean_elev_point_weighted",
        "min_depth_file_cell", "max_depth_file_cell",
        "quality_tier", "validation_weight",
        "use_for_primary_validation", "use_for_sensitivity_validation",
        "qcfiltered", "quality_filter_version",
        "source_dataset",
    ]
    sens = sens[[c for c in sens_cols if c in sens.columns]].copy()
    sens.sort_values("cell_id", inplace=True)
    sens.reset_index(drop=True, inplace=True)

    # ── 6. Load comparison data for reporting ─────────────────────────────
    log.info("Loading comparison data ...")
    common_shifts = pd.read_parquet(INPUTS["common_shifts"])
    lost = pd.read_parquet(INPUTS["lost_cells"])

    return {
        "primary": primary, "sens": sens,
        "common_shifts": common_shifts, "lost": lost,
        "tier_counts": tier_counts,
    }


# ---------------------------------------------------------------------------
# Summary parquet
# ---------------------------------------------------------------------------

def build_summary(primary: pd.DataFrame, sens: pd.DataFrame,
                  tier_counts: pd.Series) -> pd.DataFrame:
    rows = []

    rows.append({"metric": "primary_cells", "value": len(primary)})
    rows.append({"metric": "sensitivity_cells", "value": len(sens)})

    for tier in ["A_tier", "B_tier", "C_tier"]:
        rows.append({"metric": f"primary_{tier}_count",
                      "value": int(tier_counts.get(tier, 0))})

    common_ids = set(primary["cell_id"]) & set(sens["cell_id"])
    lost_ids = set(sens["cell_id"]) - set(primary["cell_id"])
    rows.append({"metric": "common_cells", "value": len(common_ids)})
    rows.append({"metric": "lost_cells", "value": len(lost_ids)})
    rows.append({"metric": "lost_ratio_pct",
                  "value": round(100.0 * len(lost_ids) / len(sens), 4) if len(sens) > 0 else 0})

    rows.append({"metric": "primary_depth_min_m",
                  "value": round(float(primary["ship_depth_m"].min()), 2)})
    rows.append({"metric": "primary_depth_max_m",
                      "value": round(float(primary["ship_depth_m"].max()), 2)})
    rows.append({"metric": "primary_elev_min_m",
                  "value": round(float(primary["ship_elev_m"].min()), 2)})
    rows.append({"metric": "primary_elev_max_m",
                  "value": round(float(primary["ship_elev_m"].max()), 2)})

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def generate_report(data: dict, summary: pd.DataFrame, elapsed: float) -> str:
    lines = []
    lines.append("# Validation Cells Report (1min)")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Elapsed: {elapsed:.1f}s")
    lines.append("")

    primary = data["primary"]
    sens = data["sens"]
    tc = data["tier_counts"]
    common_shifts = data["common_shifts"]
    lost = data["lost"]

    n_primary = len(primary)
    n_sens = len(sens)
    n_lost = len(lost)
    pct_lost = 100.0 * n_lost / n_sens if n_sens > 0 else 0

    # ── Section 1 ─────────────────────────────────────────────────────────
    lines.append("## 1. Primary validation cell 数")
    lines.append("")
    lines.append(f"**{n_primary:,}** cells (qcfiltered)")
    lines.append("")

    # ── Section 2 ─────────────────────────────────────────────────────────
    lines.append("## 2. Original cell 数")
    lines.append("")
    lines.append(f"**{n_sens:,}** cells")
    lines.append("")

    # ── Section 3 ─────────────────────────────────────────────────────────
    lines.append("## 3. Lost cell 数和比例")
    lines.append("")
    lines.append(f"**{n_lost:,}** cells lost ({pct_lost:.2f}%)")
    lines.append("")

    # ── Section 4 ─────────────────────────────────────────────────────────
    lines.append("## 4. Quality tier 分布")
    lines.append("")
    lines.append("| Tier | Count | % of Primary | Validation Weight |")
    lines.append("|------|-------|-------------|-------------------|")
    for tier in ["A_tier", "B_tier", "C_tier"]:
        c = int(tc.get(tier, 0))
        pct = 100.0 * c / n_primary if n_primary > 0 else 0
        lines.append(f"| {tier} | {c:,} | {pct:.1f}% | {TIER_WEIGHT[tier]} |")
    lines.append("")

    # ── Section 5 ─────────────────────────────────────────────────────────
    lines.append("## 5. n_points_total 分布")
    lines.append("")
    pts_desc = primary["n_points_total"].describe()
    lines.append("| Stat | Primary | A_tier | B_tier | C_tier |")
    lines.append("|------|---------|--------|--------|--------|")
    for stat in ["count", "mean", "std", "min", "25%", "50%", "75%", "max"]:
        vals = [f"{pts_desc[stat]:,.1f}"]
        for tier in ["A_tier", "B_tier", "C_tier"]:
            tier_data = primary[primary["quality_tier"] == tier]["n_points_total"]
            if len(tier_data) > 0:
                vals.append(f"{tier_data.describe()[stat]:,.1f}")
            else:
                vals.append("0")
        lines.append(f"| {stat} | {' | '.join(vals)} |")
    lines.append("")

    # ── Section 6 ─────────────────────────────────────────────────────────
    lines.append("## 6. n_file_cells 分布")
    lines.append("")
    fc_desc = primary["n_file_cells"].describe()
    lines.append("| Stat | Primary | A_tier | B_tier | C_tier |")
    lines.append("|------|---------|--------|--------|--------|")
    for stat in ["count", "mean", "std", "min", "25%", "50%", "75%", "max"]:
        vals = [f"{fc_desc[stat]:,.1f}"]
        for tier in ["A_tier", "B_tier", "C_tier"]:
            tier_data = primary[primary["quality_tier"] == tier]["n_file_cells"]
            if len(tier_data) > 0:
                vals.append(f"{tier_data.describe()[stat]:,.1f}")
            else:
                vals.append("0")
        lines.append(f"| {stat} | {' | '.join(vals)} |")
    lines.append("")

    # ── Section 7 ─────────────────────────────────────────────────────────
    lines.append("## 7. n_cruises_guess 分布")
    lines.append("")
    cruise_dist = primary["n_cruises_guess"].value_counts().sort_index()
    lines.append("| n_cruises_guess | Count | % |")
    lines.append("|----------------|-------|---|")
    for n_cruise, count in cruise_dist.items():
        pct = 100.0 * count / n_primary
        lines.append(f"| {n_cruise} | {count:,} | {pct:.1f}% |")
    lines.append("")

    # ── Section 8 ─────────────────────────────────────────────────────────
    lines.append("## 8. Depth / Elevation 范围")
    lines.append("")
    lines.append("| Metric | Min | Max | Mean | Median |")
    lines.append("|--------|-----|-----|------|--------|")
    for col, label in [("ship_depth_m", "Depth (m)"), ("ship_elev_m", "Elevation (m)")]:
        lines.append(f"| {label} | {primary[col].min():.1f} | {primary[col].max():.1f} | "
                      f"{primary[col].mean():.1f} | {primary[col].median():.1f} |")
    lines.append("")

    # ── Section 9 ─────────────────────────────────────────────────────────
    n_overlap = int(primary["n_file_cells"].gt(1).sum())
    pct_overlap = 100.0 * n_overlap / n_primary if n_primary > 0 else 0
    lines.append("## 9. Overlap cell 比例")
    lines.append("")
    lines.append(f"**{n_overlap:,}** cells with n_file_cells > 1 ({pct_overlap:.1f}%)")
    lines.append("")

    # ── Section 10 ────────────────────────────────────────────────────────
    lines.append("## 10. A/B/C tier 空间覆盖和深度分布")
    lines.append("")
    for tier in ["A_tier", "B_tier", "C_tier"]:
        t = primary[primary["quality_tier"] == tier]
        if len(t) == 0:
            continue
        lines.append(f"### {tier} ({len(t):,} cells)")
        lines.append("")
        lines.append(f"- Lon range: [{t['lon_center'].min():.2f}, {t['lon_center'].max():.2f}]")
        lines.append(f"- Lat range: [{t['lat_center'].min():.2f}, {t['lat_center'].max():.2f}]")
        lines.append(f"- Depth range: [{t['ship_depth_m'].min():.1f}, {t['ship_depth_m'].max():.1f}]")
        lines.append(f"- Depth median: {t['ship_depth_m'].median():.1f}m")
        lines.append(f"- n_file_cells median: {t['n_file_cells'].median():.0f}")
        lines.append(f"- n_cruises_guess >= 2: {int((t['n_cruises_guess'] >= 2).sum()):,} ({100.0 * (t['n_cruises_guess'] >= 2).mean():.1f}%)")
        lines.append("")

    # ── Section 11 ────────────────────────────────────────────────────────
    lines.append("## 11. 下游验证使用建议")
    lines.append("")
    lines.append("### 主结果")
    lines.append("- 使用 **all qcfiltered cells** (`use_for_primary_validation=True`)")
    lines.append(f"- 共 {n_primary:,} cells")
    lines.append("")
    lines.append("### 分层分析")
    lines.append("- 同时按 **quality_tier** 分层 (A/B/C)，使用 `validation_weight` 加权")
    lines.append(f"  - A_tier: {int(tc.get('A_tier', 0)):,} cells (weight=1.0) — 高置信度")
    lines.append(f"  - B_tier: {int(tc.get('B_tier', 0)):,} cells (weight=0.7) — 中等置信度")
    lines.append(f"  - C_tier: {int(tc.get('C_tier', 0)):,} cells (weight=0.4) — 低置信度但保留")
    lines.append("")
    lines.append("### 灵敏度测试")
    lines.append("- 使用 **original cells** (`use_for_sensitivity_validation=True`)")
    lines.append(f"- 共 {n_sens:,} cells，包含被排除的异常源")
    lines.append("- 比较使用 qcfiltered vs original cells 的验证结果差异")
    lines.append("")

    # ── Section 12 ────────────────────────────────────────────────────────
    lines.append("## 12. 是否可以进入 08_validate_gridded_products_against_ship_cells.py")
    lines.append("")
    lines.append("**✅ 可以。** Primary validation table 已就绪：")
    lines.append(f"- {n_primary:,} primary validation cells")
    lines.append(f"- {n_sens:,} sensitivity cells")
    lines.append(f"- Quality tier 分层完成 (A={int(tc.get('A_tier', 0)):,}, B={int(tc.get('B_tier', 0)):,}, C={int(tc.get('C_tier', 0)):,})")
    lines.append(f"- Validation weight 分配完成")
    lines.append(f"- Ship depth/elevation 字段已标准化")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Prepare primary validation cells (07)")
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
    log = logging.getLogger("07")

    t0 = time.time()
    log.info("=" * 60)
    log.info("07_prepare_primary_validation_cells_1min.py  START")
    log.info(f"  --overwrite={args.overwrite}")

    for name, path in INPUTS.items():
        if not path.exists():
            log.error(f"Input not found: {name} = {path}")
            sys.exit(1)

    for name, path in OUTPUTS.items():
        if path.exists() and not args.overwrite:
            log.error(f"Output exists (use --overwrite): {name} = {path}")
            sys.exit(1)

    data = run(args)
    elapsed = time.time() - t0

    primary = data["primary"]
    sens = data["sens"]
    tc = data["tier_counts"]

    summary = build_summary(primary, sens, tc)
    report_text = generate_report(data, summary, elapsed)

    # ── Write outputs ─────────────────────────────────────────────────────
    log.info("Writing output files ...")

    atomic_write_parquet(primary, OUTPUTS["primary_parquet"])
    log.info(f"  Wrote {OUTPUTS['primary_parquet']} ({len(primary):,} rows)")

    tsv_df = primary.head(TSV_MAX_ROWS)
    atomic_write_tsv(tsv_df, OUTPUTS["primary_tsv"])
    log.info(f"  Wrote {OUTPUTS['primary_tsv']} ({len(tsv_df)} rows, preview)")

    atomic_write_parquet(sens, OUTPUTS["sensitivity_parquet"])
    log.info(f"  Wrote {OUTPUTS['sensitivity_parquet']} ({len(sens):,} rows)")

    atomic_write_parquet(summary, OUTPUTS["summary_parquet"])
    log.info(f"  Wrote {OUTPUTS['summary_parquet']}")

    atomic_write_text(report_text, OUTPUTS["report"])
    log.info(f"  Wrote {OUTPUTS['report']}")

    log.info("=" * 60)
    log.info(f"Primary: {len(primary):,}  Sensitivity: {len(sens):,}")
    log.info(f"  A_tier: {int(tc.get('A_tier', 0)):,}  "
             f"B_tier: {int(tc.get('B_tier', 0)):,}  "
             f"C_tier: {int(tc.get('C_tier', 0)):,}")
    log.info(f"Elapsed: {elapsed:.1f}s")
    log.info("07_prepare_primary_validation_cells_1min.py  DONE")

    print(report_text)


if __name__ == "__main__":
    main()
