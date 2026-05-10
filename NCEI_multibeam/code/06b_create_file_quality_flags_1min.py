#!/usr/bin/env python3
"""06b_create_file_quality_flags_1min.py

Generate file-level quality flags for all 5,083 processed multibeam files,
based on the extreme bias investigation results from 06a.

Input:
  - manifests/file_manifest_points_raw.parquet  (file metadata)
  - manifests/file_cells_manifest_1min.parquet  (file-cell counts)
  - derived/extreme_bias_investigation_1min/recommended_quality_actions.tsv
  - derived/extreme_bias_investigation_1min/candidate_file_audit.parquet
  - derived/extreme_bias_investigation_1min/candidate_cruise_audit.parquet
  - derived/extreme_bias_investigation_1min/affected_cells_by_candidate.parquet

Output:
  - manifests/file_quality_flags_1min.parquet
  - manifests/file_quality_flags_1min.tsv
  - docs/file_quality_flags_1min_report.md

Does NOT modify any existing data. Read-only on all inputs.
"""

import argparse
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT = Path(__file__).resolve().parent.parent

INPUTS = {
    "file_manifest": PROJECT / "manifests" / "file_manifest_points_raw.parquet",
    "file_cells_manifest": PROJECT / "manifests" / "file_cells_manifest_1min.parquet",
    "quality_actions": PROJECT / "derived" / "extreme_bias_investigation_1min" / "recommended_quality_actions.tsv",
    "file_audit": PROJECT / "derived" / "extreme_bias_investigation_1min" / "candidate_file_audit.parquet",
    "cruise_audit": PROJECT / "derived" / "extreme_bias_investigation_1min" / "candidate_cruise_audit.parquet",
    "affected_cells": PROJECT / "derived" / "extreme_bias_investigation_1min" / "affected_cells_by_candidate.parquet",
}

OUTPUTS = {
    "flags_parquet": PROJECT / "manifests" / "file_quality_flags_1min.parquet",
    "flags_tsv": PROJECT / "manifests" / "file_quality_flags_1min.tsv",
    "report": PROJECT / "docs" / "file_quality_flags_1min_report.md",
}

LOG_PATH = PROJECT / "output" / "logs" / "06b_create_file_quality_flags_1min.log"
ERROR_PATH = PROJECT / "output" / "logs" / "06b_file_quality_flags_errors.tsv"

# Flag priority (higher index = higher priority)
FLAG_PRIORITY = {"keep": 0, "high_variance_review": 1, "review": 2, "exclude": 3}

# Hardcoded exclude rules from spec
EXCLUDE_RULES = [
    {
        "match": "cruise",
        "cruise_id_guess": "KY09-09",
        "quality_flag": "exclude",
        "exclude_from_primary_cells": True,
        "flag_reason": "extreme_cruise_bias_KY09_09",
    },
    {
        "match": "cruise",
        "cruise_id_guess": "MR02-K06",
        "quality_flag": "exclude",
        "exclude_from_primary_cells": True,
        "flag_reason": "extreme_cruise_bias_MR02_K06",
    },
    {
        "match": "cruise",
        "cruise_id_guess": "KY12-01",
        "quality_flag": "exclude",
        "exclude_from_primary_cells": True,
        "flag_reason": "extreme_cruise_bias_KY12_01",
    },
    {
        "match": "file_pattern",
        "cruise_contains": "KY12-08",
        "filename_contains": "20120614",
        "quality_flag": "exclude",
        "exclude_from_primary_cells": True,
        "flag_reason": "extreme_file_bias_KY12_08_20120614",
    },
    {
        "match": "file_pattern",
        "cruise_contains": "KY12-08",
        "filename_contains": "20120607",
        "quality_flag": "exclude",
        "exclude_from_primary_cells": True,
        "flag_reason": "extreme_file_bias_KY12_08_20120607",
    },
]


# ---------------------------------------------------------------------------
# Atomic write helpers
# ---------------------------------------------------------------------------

def atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    """Write parquet to .tmp then rename atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, path)


def atomic_write_tsv(df: pd.DataFrame, path: Path) -> None:
    """Write TSV to .tmp then rename atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, path)


def atomic_write_text(text: str, path: Path) -> None:
    """Write text to .tmp then rename atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def apply_flag(flags_df: pd.DataFrame, mask: pd.Series,
               quality_flag: str, flag_reason: str, flag_source: str,
               exclude_from_primary_cells: bool = False) -> None:
    """Apply a quality flag to rows matching mask, respecting priority."""
    target_priority = FLAG_PRIORITY[quality_flag]
    # Only upgrade (never downgrade)
    upgrade_mask = mask & (
        flags_df["_flag_priority"] < target_priority
    )
    n_applied = upgrade_mask.sum()
    flags_df.loc[upgrade_mask, "quality_flag"] = quality_flag
    flags_df.loc[upgrade_mask, "exclude_from_primary_cells"] = exclude_from_primary_cells
    flags_df.loc[upgrade_mask, "flag_reason"] = flag_reason
    flags_df.loc[upgrade_mask, "flag_source"] = flag_source
    flags_df.loc[upgrade_mask, "_flag_priority"] = target_priority
    return n_applied


def build_quality_flags(args) -> pd.DataFrame:
    """Build the quality flags table from all inputs."""

    log = logging.getLogger("06b")
    errors = []

    # ── 1. Load manifests ──────────────────────────────────────────────
    log.info("Loading file_cells_manifest_1min (authoritative 5,083 files) ...")
    fcm = pd.read_parquet(INPUTS["file_cells_manifest"])
    log.info(f"  {len(fcm)} files in file_cells_manifest")

    log.info("Loading file_manifest_points_raw for metadata ...")
    fm = pd.read_parquet(INPUTS["file_manifest"])

    # ── 2. Load quality actions from 06a ──────────────────────────────
    log.info("Loading recommended_quality_actions ...")
    qa = pd.read_csv(INPUTS["quality_actions"], sep="\t")

    # ── 3. Load file audit for residual stats ─────────────────────────
    log.info("Loading candidate_file_audit ...")
    fa = pd.read_parquet(INPUTS["file_audit"])
    residual_cols = [
        "file_id",
        "residual_other_cruise_median", "residual_other_cruise_mad", "residual_other_cruise_rmse",
        "residual_other_file_median", "residual_other_file_mad", "residual_other_file_rmse",
        "recommended_action", "action_reason",
    ]
    fa_subset = fa[residual_cols].copy()
    fa_subset.rename(columns={
        "recommended_action": "recommended_action_from_06a",
        "action_reason": "action_reason_from_06a",
    }, inplace=True)

    # ── 4. Build base flags table from file_cells_manifest ────────────
    # file_cells_manifest is the authoritative source (exactly 5,083 files)
    # that passed through the full pipeline (02a curation → 02 → 03 → 04a)
    log.info("Building base flags table from file_cells_manifest ...")
    fm_meta = fm[fm["used_for_points"]][
        ["file_id", "cruise_id_guess", "subzip_id", "relative_path",
         "track_kind", "data_layout", "line_count"]
    ].copy()

    flags = fcm[["file_id"]].copy()
    flags = flags.merge(fm_meta, on="file_id", how="left")
    flags.rename(columns={"relative_path": "source_file"}, inplace=True)

    flags["n_file_cells"] = fcm["n_cells"].values
    flags["n_points_total"] = fcm["n_points_total"].values

    # Initialize flag columns
    flags["quality_flag"] = "keep"
    flags["exclude_from_primary_cells"] = False
    flags["flag_reason"] = ""
    flags["flag_source"] = ""
    flags["_flag_priority"] = 0  # internal tracking

    # Merge residual stats from 06a file audit (only for files that were candidates)
    flags = flags.merge(fa_subset, on="file_id", how="left")

    # ── 5b. Populate recommended_action_from_06a for cruise-level actions ─
    # The file audit merge above covers files that were individually audited.
    # For files flagged via cruise-level 06a actions (but not individually audited),
    # fill recommended_action_from_06a from the cruise-level QA entry.
    qa_cruise = qa[qa["candidate_type"] == "cruise"][["candidate_id", "recommended_action", "action_reason"]]
    for _, qa_row in qa_cruise.iterrows():
        cruise = qa_row["candidate_id"]
        action = qa_row["recommended_action"]
        reason = qa_row["action_reason"]
        cruise_mask = (flags["cruise_id_guess"] == cruise) & flags["recommended_action_from_06a"].isna()
        flags.loc[cruise_mask, "recommended_action_from_06a"] = action
        flags.loc[cruise_mask, "action_reason_from_06a"] = reason

    # ── 6. Apply hardcoded exclude rules ──────────────────────────────
    log.info("Applying hardcoded exclude rules ...")
    for rule in EXCLUDE_RULES:
        if rule["match"] == "cruise":
            mask = flags["cruise_id_guess"] == rule["cruise_id_guess"]
            n = apply_flag(flags, mask,
                          rule["quality_flag"], rule["flag_reason"],
                          f"hardcoded_cruise:{rule['cruise_id_guess']}",
                          rule["exclude_from_primary_cells"])
            log.info(f"  Exclude cruise {rule['cruise_id_guess']}: {n} files")
        elif rule["match"] == "file_pattern":
            cruise_mask = flags["cruise_id_guess"].str.contains(
                rule["cruise_contains"], na=False)
            file_mask = flags["file_id"].str.contains(
                rule["filename_contains"], na=False)
            mask = cruise_mask & file_mask
            n = apply_flag(flags, mask,
                          rule["quality_flag"], rule["flag_reason"],
                          f"hardcoded_file:{rule['flag_reason']}",
                          rule["exclude_from_primary_cells"])
            log.info(f"  Exclude file pattern {rule['flag_reason']}: {n} files")

    # ── 7. Apply review_candidate from 06a ────────────────────────────
    log.info("Applying review_candidate actions from 06a ...")
    review_actions = qa[qa["recommended_action"] == "review_candidate"]
    n_review_files = 0
    n_review_cruises = 0
    for _, row in review_actions.iterrows():
        if row["candidate_type"] == "file":
            mask = flags["file_id"] == row["candidate_id"]
            n = apply_flag(flags, mask,
                          "review", "review_candidate_overlap_bias",
                          f"06a_file:{row['candidate_id']}")
            n_review_files += n
        elif row["candidate_type"] == "cruise":
            mask = flags["cruise_id_guess"] == row["candidate_id"]
            n = apply_flag(flags, mask,
                          "review", "review_candidate_overlap_bias",
                          f"06a_cruise:{row['candidate_id']}")
            n_review_cruises += n
        else:
            errors.append({
                "error_type": "unknown_candidate_type",
                "candidate_type": row["candidate_type"],
                "candidate_id": row["candidate_id"],
                "recommended_action": row["recommended_action"],
                "detail": f"Unknown candidate_type: {row['candidate_type']}",
            })
    log.info(f"  Review from file actions: {n_review_files} files")
    log.info(f"  Review from cruise actions: {n_review_cruises} files")

    # ── 8. Apply high_variance_review from 06a ────────────────────────
    log.info("Applying high_variance_review actions from 06a ...")
    hv_actions = qa[qa["recommended_action"] == "high_variance_review"]
    n_hv_files = 0
    n_hv_cruises = 0
    for _, row in hv_actions.iterrows():
        if row["candidate_type"] == "file":
            mask = flags["file_id"] == row["candidate_id"]
            n = apply_flag(flags, mask,
                          "high_variance_review", "high_variance_overlap_scatter",
                          f"06a_file:{row['candidate_id']}")
            n_hv_files += n
        elif row["candidate_type"] == "cruise":
            mask = flags["cruise_id_guess"] == row["candidate_id"]
            n = apply_flag(flags, mask,
                          "high_variance_review", "high_variance_overlap_scatter",
                          f"06a_cruise:{row['candidate_id']}")
            n_hv_cruises += n
        else:
            errors.append({
                "error_type": "unknown_candidate_type",
                "candidate_type": row["candidate_type"],
                "candidate_id": row["candidate_id"],
                "recommended_action": row["recommended_action"],
                "detail": f"Unknown candidate_type: {row['candidate_type']}",
            })
    log.info(f"  High-variance from file actions: {n_hv_files} files")
    log.info(f"  High-variance from cruise actions: {n_hv_cruises} files")

    # ── 9. Apply keep from 06a (just fill recommended_action_from_06a) ─
    # For files in 06a audit that are 'keep', update recommended_action_from_06a
    # Already handled via merge above

    # ── 10. Check for unmatched 06a actions ────────────────────────────
    log.info("Checking for unmatched 06a file actions ...")
    # File-level actions: all file_ids in qa should match our flags
    qa_files = qa[qa["candidate_type"] == "file"]["candidate_id"].unique()
    unmatched_files = set(qa_files) - set(flags["file_id"].unique())
    for uf in unmatched_files:
        errors.append({
            "error_type": "unmatched_file",
            "candidate_type": "file",
            "candidate_id": uf,
            "recommended_action": qa.loc[
                qa["candidate_id"] == uf, "recommended_action"
            ].iloc[0] if len(qa[qa["candidate_id"] == uf]) > 0 else "unknown",
            "detail": f"File '{uf}' from 06a not found in file_cells_manifest_1min",
        })
    if unmatched_files:
        log.warning(f"  {len(unmatched_files)} unmatched file actions: {unmatched_files}")

    # Cruise-level actions: all cruise_ids in qa should exist
    qa_cruises = qa[qa["candidate_type"] == "cruise"]["candidate_id"].unique()
    unmatched_cruises = set(qa_cruises) - set(flags["cruise_id_guess"].unique())
    for uc in unmatched_cruises:
        errors.append({
            "error_type": "unmatched_cruise",
            "candidate_type": "cruise",
            "candidate_id": uc,
            "recommended_action": qa.loc[
                qa["candidate_id"] == uc, "recommended_action"
            ].iloc[0] if len(qa[qa["candidate_id"] == uc]) > 0 else "unknown",
            "detail": f"Cruise '{uc}' from 06a has no files in file_cells_manifest_1min",
        })
    if unmatched_cruises:
        log.warning(f"  {len(unmatched_cruises)} unmatched cruise actions: {unmatched_cruises}")

    # ── 11. Validate ──────────────────────────────────────────────────
    log.info("Validating ...")
    n_missing_flag = flags["quality_flag"].isna().sum()
    if n_missing_flag > 0:
        errors.append({
            "error_type": "missing_quality_flag",
            "candidate_type": "N/A",
            "candidate_id": "N/A",
            "recommended_action": "N/A",
            "detail": f"{n_missing_flag} files have missing quality_flag",
        })
        log.error(f"  {n_missing_flag} files with missing quality_flag!")

    # Check for conflicting flags (same file_id, multiple flags)
    # This shouldn't happen since we use priority-based single-flag assignment
    n_dup = flags.duplicated(subset=["file_id"], keep=False).sum()
    if n_dup > 0:
        errors.append({
            "error_type": "duplicate_file_id",
            "candidate_type": "N/A",
            "candidate_id": "N/A",
            "recommended_action": "N/A",
            "detail": f"{n_dup} duplicate file_id rows found",
        })
        log.error(f"  {n_dup} duplicate file_id rows!")

    # ── 12. Final columns ─────────────────────────────────────────────
    # Drop internal priority column
    flags.drop(columns=["_flag_priority"], inplace=True)

    # Ensure column order
    output_cols = [
        "file_id", "cruise_id_guess", "subzip_id", "source_file",
        "track_kind", "data_layout", "line_count",
        "n_file_cells", "n_points_total",
        "quality_flag", "exclude_from_primary_cells",
        "flag_reason", "flag_source",
        "residual_other_cruise_median", "residual_other_cruise_mad", "residual_other_cruise_rmse",
        "residual_other_file_median", "residual_other_file_mad", "residual_other_file_rmse",
        "recommended_action_from_06a",
    ]
    # Add action_reason_from_06a if it exists
    if "action_reason_from_06a" in flags.columns:
        output_cols.append("action_reason_from_06a")

    flags = flags[[c for c in output_cols if c in flags.columns]].copy()

    # Sort by quality_flag (exclude first), then file_id
    flag_order = {"exclude": 0, "review": 1, "high_variance_review": 2, "keep": 3}
    flags["_sort"] = flags["quality_flag"].map(flag_order)
    flags.sort_values(["_sort", "file_id"], inplace=True)
    flags.drop(columns=["_sort"], inplace=True)
    flags.reset_index(drop=True, inplace=True)

    return flags, errors


def generate_report(flags: pd.DataFrame, errors: list, elapsed: float) -> str:
    """Generate markdown report."""

    flag_counts = flags["quality_flag"].value_counts()
    exclude_mask = flags["quality_flag"] == "exclude"
    review_mask = flags["quality_flag"] == "review"
    hv_mask = flags["quality_flag"] == "high_variance_review"
    keep_mask = flags["quality_flag"] == "keep"

    n_total = len(flags)
    n_exclude = exclude_mask.sum()
    n_review = review_mask.sum()
    n_hv = hv_mask.sum()
    n_keep = keep_mask.sum()
    n_exclude_primary = flags["exclude_from_primary_cells"].sum()

    # Exclude stats
    exc_line_count = int(flags.loc[exclude_mask, "line_count"].sum())
    exc_file_cells = int(flags.loc[exclude_mask, "n_file_cells"].sum())
    exc_points = int(flags.loc[exclude_mask, "n_points_total"].sum())

    # Total stats
    total_line_count = int(flags["line_count"].sum())
    total_file_cells = int(flags["n_file_cells"].sum())
    total_points = int(flags["n_points_total"].sum())

    # Remaining stats
    rem_files = n_total - n_exclude
    rem_file_cells = total_file_cells - exc_file_cells
    rem_points = total_points - exc_points

    # Exclude cruise/file lists
    exc_cruises = sorted(flags.loc[exclude_mask, "cruise_id_guess"].unique())
    exc_files = sorted(flags.loc[exclude_mask, "file_id"].unique())

    # Review stats
    review_cruises = sorted(flags.loc[review_mask, "cruise_id_guess"].unique())
    hv_cruises = sorted(flags.loc[hv_mask, "cruise_id_guess"].unique())

    # Validation
    n_missing = flags["quality_flag"].isna().sum()
    n_dup = flags.duplicated(subset=["file_id"], keep=False).sum()

    # Build report
    lines = []
    lines.append("# File Quality Flags Report (1min)")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Elapsed: {elapsed:.1f}s")
    lines.append("")

    # Section 1
    lines.append("## 1. Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total file_id count | **{n_total}** |")
    lines.append(f"| Expected file count | 5,083 |")
    lines.append(f"| Match | {'✅ Yes' if n_total == 5083 else '❌ No (' + str(n_total) + ')'} |")
    lines.append("")

    # Section 2
    lines.append("## 2. Quality Flag Distribution")
    lines.append("")
    lines.append(f"| Flag | Count | % |")
    lines.append(f"|------|-------|---|")
    for flag_name in ["exclude", "review", "high_variance_review", "keep"]:
        n = flag_counts.get(flag_name, 0)
        pct = 100.0 * n / n_total if n_total > 0 else 0
        lines.append(f"| {flag_name} | {n} | {pct:.1f}% |")
    lines.append(f"| **Total** | **{n_total}** | **100%** |")
    lines.append("")

    # Section 3
    lines.append(f"## 3. exclude_from_primary_cells=True")
    lines.append("")
    lines.append(f"**{n_exclude_primary} files** marked for exclusion from primary cells.")
    lines.append("")

    # Section 4
    lines.append("## 4. Exclude Cruise List")
    lines.append("")
    for c in exc_cruises:
        n_files = (flags.loc[exclude_mask, "cruise_id_guess"] == c).sum()
        lines.append(f"- **{c}**: {n_files} files")
    lines.append("")

    # Section 5
    lines.append("## 5. Exclude File List")
    lines.append("")
    for f in exc_files:
        row = flags[flags["file_id"] == f].iloc[0]
        lines.append(f"- `{f}` (cruise={row['cruise_id_guess']}, reason={row['flag_reason']})")
    lines.append("")

    # Section 6
    lines.append("## 6. Review Files")
    lines.append("")
    lines.append(f"**{n_review} files** flagged as review.")
    lines.append(f"Review cruises: {', '.join(review_cruises) if review_cruises else 'none'}")
    lines.append("")

    # Section 7
    lines.append("## 7. High-Variance Review Files")
    lines.append("")
    lines.append(f"**{n_hv} files** flagged as high_variance_review.")
    lines.append(f"HV cruises: {', '.join(hv_cruises) if hv_cruises else 'none'}")
    lines.append("")

    # Section 8
    lines.append("## 8. Exclude Impact")
    lines.append("")
    lines.append(f"| Metric | Excluded | Total | Remaining |")
    lines.append(f"|--------|----------|-------|-----------|")
    lines.append(f"| Files | {n_exclude} | {n_total} | {rem_files} |")
    lines.append(f"| Lines (raw) | {exc_line_count:,} | {total_line_count:,} | {total_line_count - exc_line_count:,} |")
    lines.append(f"| File-cells | {exc_file_cells:,} | {total_file_cells:,} | {rem_file_cells:,} |")
    lines.append(f"| Points (QC) | {exc_points:,} | {total_points:,} | {rem_points:,} |")
    lines.append("")

    # Section 9
    lines.append("## 9. Excluded Total line_count")
    lines.append("")
    lines.append(f"**{exc_line_count:,}** raw lines excluded.")
    lines.append("")

    # Section 10
    lines.append("## 10. Excluded Total file-cell count")
    lines.append("")
    lines.append(f"**{exc_file_cells:,}** file-cells excluded.")
    lines.append("")

    # Section 11
    lines.append("## 11. Excluded Total n_points_total")
    lines.append("")
    lines.append(f"**{exc_points:,}** QC-passed points excluded.")
    lines.append("")

    # Section 12
    lines.append("## 12. Remaining After Exclusion")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Remaining files | {rem_files} |")
    lines.append(f"| Remaining file-cells | {rem_file_cells:,} |")
    lines.append(f"| Remaining points | {rem_points:,} |")
    lines.append("")

    # Section 13
    lines.append("## 13. Remaining Points / Cells / File-cells")
    lines.append("")
    lines.append(f"After excluding {n_exclude} files ({n_exclude_primary} with exclude_from_primary_cells=True):")
    lines.append(f"- Files: {n_total} → {rem_files} (-{n_exclude})")
    lines.append(f"- File-cells: {total_file_cells:,} → {rem_file_cells:,} (-{exc_file_cells:,})")
    lines.append(f"- Points: {total_points:,} → {rem_points:,} (-{exc_points:,})")
    lines.append("")

    # Section 14
    lines.append("## 14. 是否存在 quality_flag 缺失")
    lines.append("")
    lines.append(f"- quality_flag missing: {'❌ Yes (' + str(n_missing) + ')' if n_missing > 0 else '✅ None'}")
    lines.append("")

    # Section 15
    lines.append("## 15. 是否存在同一 file_id 多个冲突标记")
    lines.append("")
    lines.append(f"- Duplicate file_id rows: {'❌ Yes (' + str(n_dup) + ')' if n_dup > 0 else '✅ None'}")
    lines.append(f"- Conflicting quality_flag on same file_id: ✅ Impossible (priority-based single assignment)")
    lines.append("")

    # Section 16
    lines.append("## 16. 结论：是否可以进入 06c 重建 qcfiltered cells")
    lines.append("")
    can_proceed = (n_total == 5083 and n_missing == 0 and n_dup == 0)
    if can_proceed:
        lines.append("✅ **可以进入 06c 重建 qcfiltered cells。**")
        lines.append(f"- 排除 {n_exclude} 个文件 ({exc_points:,} 点, {exc_file_cells:,} file-cells)")
        lines.append(f"- 剩余 {rem_files} 个文件 ({rem_points:,} 点, {rem_file_cells:,} file-cells)")
        if errors:
            lines.append(f"- ⚠️ {len(errors)} unmatched 06a actions (see error TSV)")
    else:
        lines.append("❌ **存在问题，暂不建议进入 06c。**")
        if n_total != 5083:
            lines.append(f"- 文件数不等于 5,083 (实际 {n_total})")
        if n_missing > 0:
            lines.append(f"- 存在 {n_missing} 个缺失 quality_flag")
        if n_dup > 0:
            lines.append(f"- 存在 {n_dup} 个重复 file_id")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate file-level quality flags for multibeam files")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing output files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute flags but do not write output")
    args = parser.parse_args()

    # Setup logging
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    log = logging.getLogger("06b")

    t0 = time.time()
    log.info("=" * 60)
    log.info("06b_create_file_quality_flags_1min.py  START")
    log.info(f"  --overwrite={args.overwrite}  --dry-run={args.dry_run}")

    # Validate inputs
    for name, path in INPUTS.items():
        if not path.exists():
            log.error(f"Input not found: {name} = {path}")
            sys.exit(1)
        log.info(f"  Input: {name} = {path}")

    # Check outputs
    for name, path in OUTPUTS.items():
        if path.exists() and not args.overwrite:
            log.error(f"Output exists (use --overwrite): {name} = {path}")
            sys.exit(1)
        log.info(f"  Output: {name} = {path}")

    # Build flags
    flags, errors = build_quality_flags(args)
    elapsed = time.time() - t0
    log.info(f"Built quality flags: {len(flags)} rows in {elapsed:.1f}s")

    # Generate report
    report = generate_report(flags, errors, elapsed)
    log.info("Generated report")

    # Write outputs
    if not args.dry_run:
        log.info("Writing output files ...")

        # Write parquet
        atomic_write_parquet(flags, OUTPUTS["flags_parquet"])
        log.info(f"  Wrote {OUTPUTS['flags_parquet']}")

        # Write TSV
        atomic_write_tsv(flags, OUTPUTS["flags_tsv"])
        log.info(f"  Wrote {OUTPUTS['flags_tsv']}")

        # Write report
        atomic_write_text(report, OUTPUTS["report"])
        log.info(f"  Wrote {OUTPUTS['report']}")

        # Write error TSV
        if errors:
            err_df = pd.DataFrame(errors)
            atomic_write_tsv(err_df, ERROR_PATH)
            log.info(f"  Wrote {len(errors)} errors to {ERROR_PATH}")
        else:
            # Write empty error file
            err_df = pd.DataFrame(columns=["error_type", "candidate_type",
                                            "candidate_id", "recommended_action",
                                            "detail"])
            atomic_write_tsv(err_df, ERROR_PATH)
            log.info(f"  Wrote empty error file to {ERROR_PATH}")
    else:
        log.info("DRY RUN - not writing output files")

    # Summary to log
    log.info("=" * 60)
    log.info(f"Total files: {len(flags)}")
    log.info(f"Flag distribution: {flags['quality_flag'].value_counts().to_dict()}")
    log.info(f"Exclude from primary cells: {flags['exclude_from_primary_cells'].sum()}")
    log.info(f"Errors: {len(errors)}")
    log.info(f"Elapsed: {elapsed:.1f}s")
    log.info("06b_create_file_quality_flags_1min.py  DONE")

    # Print report to stdout as well
    print(report)


if __name__ == "__main__":
    main()
