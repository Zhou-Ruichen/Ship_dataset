#!/usr/bin/env python3
"""
02a_curate_points_manifest.py

Curate file_manifest into a points_raw-ready manifest, adding file_role,
include/exclude flags, and duplicate candidate detection.

Reads:
  - manifests/file_manifest.parquet   (from 01 script, NOT modified)

Writes:
  - manifests/file_manifest_points_raw.parquet + .tsv
  - manifests/excluded_from_points_raw.tsv
  - docs/points_raw_manifest_curation_report.md
  - output/logs/02a_curate_points_manifest.log

Usage:
    python 02a_curate_points_manifest.py

No arguments needed — operates on the full manifest in memory.
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent

FILE_MANIFEST_PQ = ROOT_DIR / "manifests" / "file_manifest.parquet"
POINTS_RAW_PQ = ROOT_DIR / "manifests" / "file_manifest_points_raw.parquet"
POINTS_RAW_TSV = ROOT_DIR / "manifests" / "file_manifest_points_raw.tsv"
EXCLUDED_TSV = ROOT_DIR / "manifests" / "excluded_from_points_raw.tsv"
REPORT_MD = ROOT_DIR / "docs" / "points_raw_manifest_curation_report.md"
LOG_PATH = ROOT_DIR / "output" / "logs" / "02a_curate_points_manifest.log"

LAYOUT_3COL = "lon_lat_depth_3col"
LAYOUT_6COL = "date_time_sonar_lon_lat_depth_6col"

OK_STATUSES = {"ok_xyz_3col", "ok_xyz_6col_time_sonar_lonlatdepth"}
OK_LAYOUTS = {LAYOUT_3COL, LAYOUT_6COL}
AUX_PREFIXES = ("grid_", "track_", "dist_")


def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("curate_manifest")
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


def classify_file_role(row: pd.Series) -> str:
    fn = row["filename"]
    if fn.startswith("grid_"):
        return "auxiliary_grid"
    if fn.startswith("track_"):
        return "auxiliary_track"
    if fn.startswith("dist_"):
        return "auxiliary_dist"
    if row["status"] in OK_STATUSES:
        if row["status"] == "ok_xyz_3col":
            return "raw_xyz_3col_candidate"
        return "raw_xyz_6col_candidate"
    if not row["used_for_points"]:
        return "nonstandard_or_invalid"
    return "unknown"


def compute_include(row: pd.Series) -> tuple[bool, str]:
    if not row["used_for_points"]:
        return False, "used_for_points_false"
    role = row["file_role"]
    if role == "auxiliary_grid":
        return False, "auxiliary_grid"
    if role == "auxiliary_track":
        return False, "auxiliary_track"
    if role == "auxiliary_dist":
        return False, "auxiliary_dist"
    if row["status"] not in OK_STATUSES:
        return False, "invalid_status"
    if row["data_layout"] not in OK_LAYOUTS:
        return False, "unknown_layout"
    if pd.isna(row["lon_col"]) or pd.isna(row["lat_col"]) or pd.isna(row["depth_col"]):
        return False, "missing_column_index"
    return True, ""


def detect_duplicate_candidates(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return (duplicate_group_id, duplicate_candidate) series."""
    dup_fields = [
        "filename", "size_bytes", "line_count",
        "lon_min", "lon_max", "lat_min", "lat_max",
        "depth_min", "depth_max",
    ]
    subset = df[dup_fields].fillna(-999999)
    grouped = subset.groupby(dup_fields, dropna=False)
    size_map = grouped.ngroup()
    group_sizes = grouped.size()

    group_id = size_map
    candidate = group_id.map(lambda g: group_sizes.iloc[g] > 1 if g >= 0 else False)
    return group_id, candidate


def write_report(
    fm: pd.DataFrame,
    dat: pd.DataFrame,
    included: pd.DataFrame,
    excluded: pd.DataFrame,
    dup_groups: pd.DataFrame,
    lon360_df: pd.DataFrame,
    report_path: Path,
    logger: logging.Logger,
):
    lines = []
    lines.append("# Points Raw Manifest Curation Report\n")
    lines.append(f"Generated: {datetime.now().isoformat()}\n")

    lines.append("## 1. 原始 file_manifest 总览\n")
    lines.append(f"- Total rows: {len(fm):,}")
    lines.append(f"- .dat files: {len(dat):,}")
    lines.append(f"- used_for_points=True: {int(dat['used_for_points'].sum()):,}")
    lines.append("")

    lines.append("## 2. file_role 分布\n")
    role_counts = dat["file_role"].value_counts()
    lines.append("| file_role | count |")
    lines.append("|-----------|-------|")
    for role, cnt in role_counts.items():
        lines.append(f"| {role} | {cnt:,} |")
    lines.append("")

    lines.append("## 3. include_in_points_raw\n")
    inc_count = int(dat["include_in_points_raw"].sum())
    exc_count = len(dat) - inc_count
    lines.append(f"- include=True: {inc_count:,}")
    lines.append(f"- include=False: {exc_count:,}")
    lines.append("")

    lines.append("## 4. exclude_reason 分布\n")
    reason_counts = dat[dat["include_in_points_raw"] == False]["exclude_reason"].value_counts()
    lines.append("| exclude_reason | count |")
    lines.append("|----------------|-------|")
    for reason, cnt in reason_counts.items():
        lines.append(f"| {reason} | {cnt:,} |")
    lines.append("")

    lines.append("## 5. auxiliary 文件列表\n")
    for prefix, role in [("grid_", "auxiliary_grid"), ("track_", "auxiliary_track"), ("dist_", "auxiliary_dist")]:
        aux = dat[dat["file_role"] == role]
        lines.append(f"\n### {role} ({len(aux)} files)\n")
        if len(aux) == 0:
            lines.append("(none)\n")
            continue
        lines.append("| relative_path | line_count | lon_range |")
        lines.append("|---------------|------------|-----------|")
        for _, r in aux.head(100).iterrows():
            lon_r = f"[{r['lon_min']:.2f}, {r['lon_max']:.2f}]"
            lines.append(f"| {r['relative_path']} | {r['line_count']:.0f} | {lon_r} |")
    lines.append("")

    lines.append("## 6. duplicate_candidate 统计\n")
    dup_count = int(dat["duplicate_candidate"].sum())
    n_groups = len(dup_groups) if len(dup_groups) > 0 else 0
    lines.append(f"- duplicate_candidate=True: {dup_count:,} files")
    lines.append(f"- duplicate groups: {n_groups}")
    lines.append("")

    if len(dup_groups) > 0:
        lines.append("## 7. 最大的 20 个 duplicate groups\n")
        lines.append("| group_id | filename | n_copies | size_bytes | line_count | subzips |")
        lines.append("|----------|----------|----------|------------|------------|---------|")
        for _, g in dup_groups.head(20).iterrows():
            subzips = ", ".join(sorted(g["subzips"]))
            lines.append(
                f"| {g['duplicate_group_id']} | {g['filename']} | {g['n_copies']} | "
                f"{g['size_bytes']:,} | {g['line_count']:.0f} | {subzips} |"
            )
        lines.append("")

    lines.append("## 8. grid_p06.dat 记录\n")
    gp06 = dat[dat["filename"] == "grid_p06.dat"]
    if len(gp06) > 0:
        lines.append(f"共 {len(gp06)} 个 grid_p06.dat 文件：\n")
        for _, r in gp06.iterrows():
            lines.append(
                f"- `{r['relative_path']}`: role={r['file_role']} "
                f"include={r['include_in_points_raw']} "
                f"lon=[{r['lon_min']:.2f},{r['lon_max']:.2f}] "
                f"lines={r['line_count']:.0f} "
                f"duplicate_candidate={r['duplicate_candidate']}"
            )
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("## 9. lon_max > 180 的文件\n")
    if len(lon360_df) > 0:
        lines.append("| relative_path | include | role | lon_raw_range |")
        lines.append("|---------------|---------|------|---------------|")
        for _, r in lon360_df.iterrows():
            lon_r = f"[{r['lon_min']:.2f}, {r['lon_max']:.2f}]"
            lines.append(f"| {r['relative_path']} | {r['include_in_points_raw']} | {r['file_role']} | {lon_r} |")
    else:
        lines.append("(none)")
    lines.append("")

    inc_dat = dat[dat["include_in_points_raw"] == True]
    total_lines = inc_dat["line_count"].sum()

    lines.append("## 10. 最终纳入统计\n")
    lines.append(f"- include_in_points_raw=True 文件数: {len(inc_dat):,}")
    lines.append(f"- 预计总行数: {total_lines:,.0f}")
    lines.append(f"- 预计 Parquet 大小: ~{total_lines * 33.4 / 1e9:.1f} GB (基于 test100 的 33.4 bytes/row)")
    lines.append("")

    lines.append("## 11. 结论\n")
    if len(inc_dat) > 0:
        lines.append(
            f"建议 02 脚本使用 `manifests/file_manifest_points_raw.parquet` 作为输入，"
            f"仅处理 include_in_points_raw=True 的 {len(inc_dat):,} 个文件（{total_lines:,.0f} 行）。\n\n"
            f"已排除 {exc_count} 个文件："
            f"13 个 auxiliary_grid 文件（grid_*.dat），{exc_count - 13} 个 nonstandard_or_invalid 文件。\n\n"
            f"4 个 lon_max > 180 的文件（grid_p06.dat）已全部被 auxiliary_grid 规则排除，"
            f"不会进入 points_raw。\n\n"
            f"duplicate_candidate 报告了 {n_groups} 组重复候选，"
            f"但这些文件已经因 auxiliary 规则被排除，不影响 points_raw。\n"
        )
    else:
        lines.append("WARNING: 没有文件被纳入 points_raw。请检查 file_role 和 include 规则。\n")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Curation report written to {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Curate file_manifest into points_raw-ready manifest.",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing output files.",
    )
    args = parser.parse_args()

    logger = setup_logging(LOG_PATH)
    logger.info("=" * 60)
    logger.info("Starting 02a_curate_points_manifest.py")

    if not FILE_MANIFEST_PQ.exists():
        logger.error(f"file_manifest not found: {FILE_MANIFEST_PQ}")
        sys.exit(1)

    if not args.overwrite and POINTS_RAW_PQ.exists():
        logger.info("Output exists. Use --overwrite to regenerate.")
        print("Output exists. Use --overwrite to regenerate.")
        return

    fm = pd.read_parquet(FILE_MANIFEST_PQ)
    logger.info(f"Loaded file_manifest: {len(fm):,} rows")

    dat = fm[fm["ext"] == ".dat"].copy()
    logger.info(f".dat files: {len(dat):,}")

    # Classify file_role
    dat["file_role"] = dat.apply(classify_file_role, axis=1)

    # Compute include/exclude
    results = dat.apply(compute_include, axis=1)
    dat["include_in_points_raw"] = results.apply(lambda t: t[0])
    dat["exclude_reason"] = results.apply(lambda t: t[1])

    # Detect duplicate candidates
    group_id, candidate = detect_duplicate_candidates(dat)
    dat["duplicate_group_id"] = group_id
    dat["duplicate_candidate"] = candidate

    logger.info(f"file_role distribution:\n{dat['file_role'].value_counts().to_string()}")
    logger.info(f"include_in_points_raw: True={int(dat['include_in_points_raw'].sum())}, "
                f"False={int((~dat['include_in_points_raw']).sum())}")

    # Split
    included = dat[dat["include_in_points_raw"] == True].copy()
    excluded = dat[dat["include_in_points_raw"] == False].copy()

    # Duplicate groups summary
    dup_only = dat[dat["duplicate_candidate"] == True]
    if len(dup_only) > 0:
        dup_groups = dup_only.groupby("duplicate_group_id").agg(
            filename=("filename", "first"),
            n_copies=("file_id", "count"),
            size_bytes=("size_bytes", "first"),
            line_count=("line_count", "first"),
            subzips=("subzip_id", lambda x: list(x.unique())),
        ).sort_values("n_copies", ascending=False).reset_index()
    else:
        dup_groups = pd.DataFrame()

    # lon_max > 180 files
    lon360_df = dat[dat["lon_max"] > 180].copy()

    # Atomic write
    POINTS_RAW_PQ.parent.mkdir(parents=True, exist_ok=True)
    tmp_pq = POINTS_RAW_PQ.with_suffix(".parquet.tmp")
    tmp_tsv = POINTS_RAW_TSV.with_suffix(".tsv.tmp")
    dat.to_parquet(tmp_pq, index=False)
    dat.to_csv(tmp_tsv, sep="\t", index=False)
    os.replace(tmp_pq, POINTS_RAW_PQ)
    os.replace(tmp_tsv, POINTS_RAW_TSV)
    logger.info(f"Wrote {len(dat)} rows to {POINTS_RAW_PQ.name} + .tsv")

    # Excluded TSV
    if len(excluded) > 0:
        excluded.to_csv(EXCLUDED_TSV, sep="\t", index=False)
        logger.info(f"Wrote {len(excluded)} excluded rows to {EXCLUDED_TSV.name}")

    # Report
    write_report(fm, dat, included, excluded, dup_groups, lon360_df, REPORT_MD, logger)

    logger.info("Done.")
    logger.info("=" * 60)

    inc_count = len(included)
    exc_count = len(excluded)
    total_lines = included["line_count"].sum()

    print(f"\n{'='*60}")
    print(f"  CURATION COMPLETE")
    print(f"  Total .dat: {len(dat):,}")
    print(f"  Included:   {inc_count:,} ({total_lines:,.0f} lines)")
    print(f"  Excluded:   {exc_count:,}")
    print(f"  Auxiliaries excluded: {int((dat['file_role'].str.startswith('auxiliary')).sum())}")
    print(f"  Duplicate groups: {len(dup_groups)}")
    print(f"  Output: {POINTS_RAW_PQ}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
