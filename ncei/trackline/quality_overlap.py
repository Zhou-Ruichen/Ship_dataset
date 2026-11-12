"""Within-branch residuals and cross-branch depth comparisons."""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent          # ncei/
REPO_ROOT = ROOT_DIR.parent           # ship/

from _common.file_io import atomic_write_parquet, atomic_write_text, atomic_write_tsv
from _common.script_utils import ensure_columns, markdown_table, setup_logging

from .quality_inputs import BRANCHES, branch_cells_dir, read_parquet_schema, repo_path
from .run_labels import suffix_for_run

MANIFEST_DIR = ROOT_DIR / "manifests"
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"
DERIVED_DIR = ROOT_DIR / "derived"

FILE_CELLS_MANIFEST = MANIFEST_DIR / "file_cells_1min_manifest.parquet"
CELLS_MANIFEST = MANIFEST_DIR / "cells_1min_manifest.parquet"

VALID_RUN_LABELS = ("sample", "test100", "full")
OVERLAP_VERSION = "ncei_overlap_v0.1.0"

EXPECTED_PAIR_LABELS = {"mb_vs_mrar", "mb_vs_sb", "mrar_vs_sb"}
CROSS_OVERLAP_VERSION = "ncei_cross_overlap_v0.1.0"
STREAMING_ROW_THRESHOLD = 5_000_000

# Fixed canonical pair ordering. The left/right ordering makes the
# residual sign unambiguous: residual_m = left - right.
PAIR_SPECS = [
    ("mb_vs_mrar", "multibeam_ncei", "regional_mrar"),
    ("mb_vs_sb", "multibeam_ncei", "singlebeam"),
    ("mrar_vs_sb", "regional_mrar", "singlebeam"),
]

CROSS_BRANCH_CELL_COLUMNS = [
    "branch",
    "cell_id",
    "lon_bin",
    "lat_bin",
    "lon_center",
    "lat_center",
    "n_track_cells",
    "n_tracks",
    "n_unique_triples_total",
    "duplicate_ratio_cell",
    "median_depth_m",
    "manual_review_any",
    "iqr_of_track_medians",
]

INTERNAL_BRANCH_CELL_COLUMNS = CROSS_BRANCH_CELL_COLUMNS + ["lat_band_10deg"]

CROSS_CELL_COLUMNS = [
    "pair_label",
    "left_branch",
    "right_branch",
    "cell_id",
    "lon_bin",
    "lat_bin",
    "lon_center",
    "lat_center",
    "left_median_depth_m",
    "right_median_depth_m",
    "residual_m",
    "abs_residual_m",
    "left_n_track_cells",
    "right_n_track_cells",
    "left_n_tracks",
    "right_n_tracks",
    "left_n_unique_triples_total",
    "right_n_unique_triples_total",
    "left_duplicate_ratio_cell",
    "right_duplicate_ratio_cell",
    "left_manual_review_any",
    "right_manual_review_any",
    "left_iqr_of_track_medians",
    "right_iqr_of_track_medians",
    "cross_analysis_version",
]

PAIR_SUMMARY_COLUMNS = [
    "pair_label",
    "left_branch",
    "right_branch",
    "n_left_cells_total",
    "n_right_cells_total",
    "n_overlap_cells",
    "overlap_share_of_left",
    "overlap_share_of_right",
    "residual_p01",
    "residual_p05",
    "residual_p25",
    "residual_p50",
    "residual_p75",
    "residual_p95",
    "residual_p99",
    "abs_residual_p50",
    "abs_residual_p95",
    "abs_residual_p99",
    "rmse_pair_m",
    "n_overlap_both_flagged",
    "n_overlap_either_flagged",
    "cross_analysis_version",
    "runtime_seconds",
]

CROSS_BREAKDOWN_COLUMNS = [
    "breakdown_type",
    "pair_label",
    "group_value",
    "n_overlap_cells",
    "residual_p50",
    "abs_residual_p50",
    "abs_residual_p95",
    "abs_residual_p99",
    "rmse",
]

# Audit-time estimates from ncei/docs/step04_aggregation_design_audit.md.
AUDIT_OVERLAP_ESTIMATES = {
    "mb_vs_mrar": 4_015,
    "mb_vs_sb": 4_127,
    "mrar_vs_sb": 1_888_543,
}


REQUIRED_FILE_CELL_COLUMNS = [
    "branch",
    "cell_id",
    "lon_bin",
    "lat_bin",
    "lon_center",
    "lat_center",
    "track_id",
    "source_type",
    "source_completeness",
    "instrument_class_pred",
    "manual_review_flag",
    "n_points_pass",
    "n_unique_triples",
    "duplicate_ratio",
    "median_depth_m",
]

SOURCE_BRANCH_CELL_COLUMNS = [
    "branch",
    "cell_id",
    "lon_bin",
    "lat_bin",
    "lon_center",
    "lat_center",
    "n_track_cells",
    "median_depth_m",
    "duplicate_ratio_cell",
    "manual_review_any",
]

RESIDUAL_COLUMNS = [
    "branch",
    "cell_id",
    "lon_bin",
    "lat_bin",
    "lon_center",
    "lat_center",
    "track_id",
    "source_type",
    "source_completeness",
    "instrument_class_pred",
    "manual_review_flag",
    "n_points_pass",
    "n_unique_triples",
    "duplicate_ratio",
    "track_cell_median_depth_m",
    "branch_cell_median_depth_m",
    "branch_cell_n_track_cells",
    "branch_cell_duplicate_ratio_cell",
    "branch_cell_manual_review_any",
    "residual_m",
    "abs_residual_m",
    "analysis_version",
]

TRACK_SUMMARY_COLUMNS = [
    "branch",
    "track_id",
    "source_type",
    "source_completeness",
    "instrument_class_pred",
    "manual_review_flag",
    "manual_review_reasons",
    "n_overlap_cells",
    "n_unique_triples_total",
    "median_residual_m",
    "mean_residual_m",
    "mad_residual_m",
    "iqr_residual_m",
    "rmse_residual_m",
    "p95_abs_residual_m",
    "max_abs_residual_m",
    "duplicate_ratio_summary",
    "manual_review_cell_share",
    "analysis_version",
]

BRANCH_SUMMARY_COLUMNS = [
    "branch",
    "n_branch_cells_total",
    "n_overlap_cells",
    "overlap_share",
    "n_overlap_track_cell_rows",
    "residual_p01",
    "residual_p05",
    "residual_p25",
    "residual_p50",
    "residual_p75",
    "residual_p95",
    "residual_p99",
    "abs_residual_p50",
    "abs_residual_p95",
    "abs_residual_p99",
    "rmse_residual_m_branch",
    "analysis_version",
    "runtime_seconds",
]

MANUAL_REVIEW_SUMMARY_COLUMNS = [
    "branch",
    "manual_review_flag",
    "n_track_cells",
    "n_overlap_rows",
    "residual_p50",
    "abs_residual_p50",
    "abs_residual_p95",
    "abs_residual_p99",
    "rmse",
]

SOURCE_BREAKDOWN_COLUMNS = [
    "breakdown_type",
    "branch",
    "group_value",
    "n_track_cells",
    "n_overlap_rows",
    "residual_p50",
    "abs_residual_p50",
    "abs_residual_p95",
    "abs_residual_p99",
    "rmse",
]

DUPLICATE_RATIO_BINS = [0.0, 0.01, 0.1, 0.5, 1.0]
SOURCE_DUPLICATE_RATIO_BIN_LABELS = ["[0,0.01)", "[0.01,0.1)", "[0.1,0.5)", "[0.5,1.0]"]
CROSS_DUPLICATE_RATIO_BIN_LABELS = ["[0, 0.01)", "[0.01, 0.1)", "[0.1, 0.5)", "[0.5, 1.0]"]
FALLBACK_REVIEW_REASON = "step03b_flag"


# ---------------------------------------------------------------------------
# Path / logging / atomic-write helpers
# ---------------------------------------------------------------------------
def source_overlap_dir(run_label: str) -> Path:
    return DERIVED_DIR / f"overlap_bias_1min{suffix_for_run(run_label)}"


def source_overlap_paths(run_label: str) -> dict[str, Path]:
    suffix = suffix_for_run(run_label)
    out_dir = source_overlap_dir(run_label)
    return {
        "out_dir": out_dir,
        "residuals_pq": out_dir / "source_specific_overlap_residuals.parquet",
        "track_summary_pq": out_dir / "track_bias_summary.parquet",
        "branch_summary_pq": out_dir / "branch_overlap_summary.parquet",
        "breakdowns_tsv": out_dir / "branch_overlap_breakdowns.tsv",
        "manual_review_tsv": out_dir / "manual_review_overlap_summary.tsv",
        "report_md": DOCS_DIR / f"step05a_source_specific_overlap_bias_report{suffix}.md",
        "log": LOG_DIR / f"09_source_specific_overlap_residuals{suffix}.log",
    }


# ---------------------------------------------------------------------------
# Generic statistics helpers
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


def safe_mad(values: pd.Series) -> float:
    s = pd.to_numeric(values, errors="coerce").dropna()
    if s.empty:
        return float("nan")
    med = float(s.median())
    return float((s - med).abs().median())


def summarize_residual_distribution(sub: pd.DataFrame) -> dict[str, float | int]:
    if sub.empty:
        return {
            "n_track_cells": 0,
            "n_overlap_rows": 0,
            "residual_p50": float("nan"),
            "abs_residual_p50": float("nan"),
            "abs_residual_p95": float("nan"),
            "abs_residual_p99": float("nan"),
            "rmse": float("nan"),
        }
    return {
        "n_track_cells": int(len(sub)),
        "n_overlap_rows": int(len(sub)),
        "residual_p50": safe_quantile(sub["residual_m"], 0.50),
        "abs_residual_p50": safe_quantile(sub["abs_residual_m"], 0.50),
        "abs_residual_p95": safe_quantile(sub["abs_residual_m"], 0.95),
        "abs_residual_p99": safe_quantile(sub["abs_residual_m"], 0.99),
        "rmse": safe_rmse(sub["residual_m"]),
    }


def coerce_common_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    int_cols = [
        "lon_bin",
        "lat_bin",
        "n_points_pass",
        "n_unique_triples",
        "branch_cell_n_track_cells",
    ]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="raise").astype("int64")
    for col in ("manual_review_flag", "branch_cell_manual_review_any"):
        if col in df.columns:
            df[col] = df[col].fillna(False).astype(bool)
    return df


# ---------------------------------------------------------------------------
# Input selection / loading
# ---------------------------------------------------------------------------
def select_file_cell_manifest_rows(
    manifest: pd.DataFrame,
    *,
    run_label: str,
    limit_files_per_branch: int | None,
    logger: logging.Logger,
) -> pd.DataFrame:
    missing = {"branch", "track_id", "output_path"} - set(manifest.columns)
    if missing:
        raise ValueError(f"file-cell manifest missing required columns: {sorted(missing)}")

    work = manifest[manifest["branch"].isin(BRANCHES)].copy()
    work = work.sort_values(["branch", "track_id", "output_path"]).reset_index(drop=True)
    if run_label == "full":
        return work

    if limit_files_per_branch is not None and limit_files_per_branch <= 0:
        raise ValueError("--limit-files-per-branch must be positive when provided")
    default_limit = 50 if run_label == "sample" else 100
    n_take = limit_files_per_branch if limit_files_per_branch is not None else default_limit

    parts: list[pd.DataFrame] = []
    for branch in BRANCHES:
        pool = work[work["branch"] == branch]
        if branch == "regional_mrar":
            parts.append(pool)
        else:
            parts.append(pool.head(min(n_take, len(pool))))
    selected = pd.concat(parts, ignore_index=True) if parts else work.head(0).copy()
    logger.info(
        "%s workload selected with limit_files_per_branch=%s: %s",
        run_label,
        n_take,
        selected["branch"].value_counts().to_dict(),
    )
    return selected


def select_branches(cells_manifest: pd.DataFrame) -> list[str]:
    if "branch" not in cells_manifest.columns:
        raise ValueError("cells_1min manifest missing required column: branch")
    branches = [b for b in BRANCHES if b in set(cells_manifest["branch"].astype(str))]
    missing = [b for b in BRANCHES if b not in branches]
    if missing:
        raise ValueError(f"cells_1min manifest missing expected branches: {missing}")
    return branches


def read_branch_overlap_cells(branch: str, logger: logging.Logger) -> pd.DataFrame:
    """Read Step 04B cells for one branch, filtered to n_track_cells>=2."""
    path = branch_cells_dir(branch, DERIVED_DIR)
    if not path.exists():
        raise FileNotFoundError(f"Step 04B cells dataset not found for {branch}: {path}")

    dataset = ds.dataset(str(path), format="parquet", partitioning="hive")
    names = set(dataset.schema.names)
    missing = [c for c in SOURCE_BRANCH_CELL_COLUMNS if c not in names]
    if missing:
        raise ValueError(f"{path} missing Step 04B columns: {missing}")

    table = dataset.to_table(
        columns=SOURCE_BRANCH_CELL_COLUMNS,
        filter=ds.field("n_track_cells") >= 2,
    )
    df = table.to_pandas()
    if df.empty:
        logger.info("%s: no Step 04B cells with n_track_cells>=2", branch)
        return df

    df["branch"] = df["branch"].astype(str)
    branch_values = sorted(df["branch"].unique().tolist())
    if branch_values != [branch]:
        raise ValueError(f"{branch}: Step 04B hive read returned cross-branch rows: {branch_values}")
    if (pd.to_numeric(df["n_track_cells"], errors="coerce") < 2).any():
        raise ValueError(f"{branch}: n_track_cells<2 leaked into overlap-cell table")

    df = df.rename(
        columns={
            "median_depth_m": "branch_cell_median_depth_m",
            "n_track_cells": "branch_cell_n_track_cells",
            "duplicate_ratio_cell": "branch_cell_duplicate_ratio_cell",
            "manual_review_any": "branch_cell_manual_review_any",
        }
    )
    df = coerce_common_dtypes(df)
    logger.info("%s: loaded %d overlap branch cells (n_track_cells>=2)", branch, len(df))
    return df


def read_selected_file_cells(
    branch: str,
    manifest_rows: pd.DataFrame,
    overlap_cell_ids: set[str],
    logger: logging.Logger,
) -> pd.DataFrame:
    """Read selected Step 04A per-file-cell parquets for one branch.

    The manifest drives the file list. A per-file cell_id prefilter keeps
    memory bounded while preserving the mandated Step 04A-only input rule.

    Performance note: a Python `set` is passed in for clarity at the call
    site, but pandas' `isin(set)` against 2M+ elements is ~6× slower than
    `isin(Index)` because the set is re-converted internally per call. We
    materialize a single `pd.Index` once and reuse it across all files.
    """
    frames: list[pd.DataFrame] = []
    n_files = len(manifest_rows)
    overlap_cell_index = pd.Index(list(overlap_cell_ids)) if overlap_cell_ids else pd.Index([])
    for i, (_, manifest_row) in enumerate(manifest_rows.iterrows(), start=1):
        rel = str(manifest_row["output_path"])
        path = repo_path(rel)
        if not path.exists():
            raise FileNotFoundError(f"per-file-cell parquet not found: {path}")

        schema_cols = read_parquet_schema(path)
        missing = [c for c in REQUIRED_FILE_CELL_COLUMNS if c not in schema_cols]
        if missing:
            raise ValueError(f"{path} missing required Step 04A columns: {missing}")

        df = pd.read_parquet(path, columns=REQUIRED_FILE_CELL_COLUMNS)
        if not df.empty and len(overlap_cell_index):
            df = df[df["cell_id"].isin(overlap_cell_index)]
        if not df.empty:
            frames.append(df)

        if i == 1 or i % 250 == 0 or i == n_files:
            logger.info(
                "  %s loaded %d/%d per-file-cell parquets; retained_frames=%d",
                branch,
                i,
                n_files,
                len(frames),
            )

    if not frames:
        return pd.DataFrame(columns=REQUIRED_FILE_CELL_COLUMNS)

    out = pd.concat(frames, ignore_index=True, copy=False)
    out["branch"] = out["branch"].astype(str)
    branch_values = sorted(out["branch"].unique().tolist())
    if branch_values != [branch]:
        raise ValueError(f"{branch}: Step 04A file-cell read returned cross-branch rows: {branch_values}")
    out["manual_review_flag"] = out["manual_review_flag"].fillna(False).astype(bool)
    return out


def branch_cell_total(cells_manifest: pd.DataFrame, branch: str) -> int:
    row = cells_manifest[cells_manifest["branch"].astype(str) == branch]
    if row.empty:
        raise ValueError(f"cells manifest has no row for {branch}")
    for col in ("n_cells_total", "n_branch_cells_total"):
        if col in row.columns and pd.notna(row.iloc[0][col]):
            return int(row.iloc[0][col])
    dataset = ds.dataset(str(branch_cells_dir(branch, DERIVED_DIR)), format="parquet", partitioning="hive")
    return int(dataset.count_rows())


# ---------------------------------------------------------------------------
# Residual generation and summaries
# ---------------------------------------------------------------------------
def make_branch_residuals(
    branch: str,
    file_cells: pd.DataFrame,
    branch_cells: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    if branch_cells.empty or file_cells.empty:
        return pd.DataFrame(columns=RESIDUAL_COLUMNS)

    left = file_cells.rename(columns={"median_depth_m": "track_cell_median_depth_m"})
    join_cols = ["branch", "cell_id", "lon_bin", "lat_bin"]
    right_cols = [
        "branch",
        "cell_id",
        "lon_bin",
        "lat_bin",
        "branch_cell_median_depth_m",
        "branch_cell_n_track_cells",
        "branch_cell_duplicate_ratio_cell",
        "branch_cell_manual_review_any",
    ]
    joined = left.merge(branch_cells[right_cols], on=join_cols, how="inner", validate="many_to_one")

    if joined.empty:
        logger.warning("%s: no residual rows after join", branch)
        return pd.DataFrame(columns=RESIDUAL_COLUMNS)

    branch_values = sorted(joined["branch"].astype(str).unique().tolist())
    if branch_values != [branch]:
        raise ValueError(f"{branch}: cross-branch rows after residual join: {branch_values}")
    if (pd.to_numeric(joined["branch_cell_n_track_cells"], errors="coerce") < 2).any():
        raise ValueError(f"{branch}: single-track cells entered residual analysis")

    joined["residual_m"] = joined["track_cell_median_depth_m"] - joined["branch_cell_median_depth_m"]
    joined["abs_residual_m"] = joined["residual_m"].abs()
    joined["analysis_version"] = OVERLAP_VERSION

    # Use branch-cell geometry in the final output to make the right side
    # of the join visibly authoritative after validating bins/cell_id.
    geom_cols = ["branch", "cell_id", "lon_bin", "lat_bin", "lon_center", "lat_center"]
    branch_geom = branch_cells[geom_cols].drop_duplicates(["branch", "cell_id", "lon_bin", "lat_bin"])
    joined = joined.drop(columns=["lon_center", "lat_center"]).merge(
        branch_geom,
        on=["branch", "cell_id", "lon_bin", "lat_bin"],
        how="left",
        validate="many_to_one",
    )

    joined = coerce_common_dtypes(joined)
    joined = joined[RESIDUAL_COLUMNS].sort_values(["branch", "cell_id", "track_id"]).reset_index(drop=True)

    # Exact spot-check requested by the brief. residual_m was assigned by
    # the same subtraction, so equality should be bit-exact for sampled rows.
    sample = joined.head(min(1000, len(joined)))
    if not (sample["residual_m"] == (sample["track_cell_median_depth_m"] - sample["branch_cell_median_depth_m"])).all():
        raise ValueError(f"{branch}: residual_m spot-check failed")
    logger.info(
        "%s: residual join produced %d rows; residual spot-check OK; single-track-cell leakage=0",
        branch,
        len(joined),
    )
    return joined


def summarize_tracks(residuals: pd.DataFrame) -> pd.DataFrame:
    if residuals.empty:
        return pd.DataFrame(columns=TRACK_SUMMARY_COLUMNS)

    rows: list[dict] = []
    group_cols = ["branch", "track_id", "source_type", "source_completeness", "instrument_class_pred"]
    for keys, sub in residuals.groupby(group_cols, sort=True):
        branch, track_id, source_type, source_completeness, instrument_class_pred = keys
        med = float(sub["residual_m"].median())
        q75 = safe_quantile(sub["residual_m"], 0.75)
        q25 = safe_quantile(sub["residual_m"], 0.25)
        n_points = float(pd.to_numeric(sub["n_points_pass"], errors="coerce").sum())
        n_unique = float(pd.to_numeric(sub["n_unique_triples"], errors="coerce").sum())
        manual_flag = bool(sub["manual_review_flag"].any())
        rows.append(
            {
                "branch": branch,
                "track_id": track_id,
                "source_type": source_type,
                "source_completeness": source_completeness,
                "instrument_class_pred": instrument_class_pred,
                "manual_review_flag": manual_flag,
                "manual_review_reasons": FALLBACK_REVIEW_REASON if manual_flag else "",
                "n_overlap_cells": int(sub[["branch", "cell_id"]].drop_duplicates().shape[0]),
                "n_unique_triples_total": int(n_unique),
                "median_residual_m": med,
                "mean_residual_m": float(sub["residual_m"].mean()),
                "mad_residual_m": safe_mad(sub["residual_m"]),
                "iqr_residual_m": float(q75 - q25) if np.isfinite(q75) and np.isfinite(q25) else float("nan"),
                "rmse_residual_m": safe_rmse(sub["residual_m"]),
                "p95_abs_residual_m": safe_quantile(sub["abs_residual_m"], 0.95),
                "max_abs_residual_m": float(sub["abs_residual_m"].max()),
                "duplicate_ratio_summary": float(1.0 - n_unique / n_points) if n_points > 0 else float("nan"),
                "manual_review_cell_share": float(sub["branch_cell_manual_review_any"].mean()) if len(sub) else float("nan"),
                "analysis_version": OVERLAP_VERSION,
            }
        )
    out = pd.DataFrame(rows)
    return out[TRACK_SUMMARY_COLUMNS].sort_values(["branch", "p95_abs_residual_m"], ascending=[True, False]).reset_index(drop=True)


def summarize_branch(
    branch: str,
    residuals: pd.DataFrame,
    *,
    n_branch_cells_total: int,
    n_overlap_cells: int,
    runtime_seconds: float,
) -> dict:
    overlap_share = float(n_overlap_cells / n_branch_cells_total) if n_branch_cells_total else float("nan")
    row = {
        "branch": branch,
        "n_branch_cells_total": int(n_branch_cells_total),
        "n_overlap_cells": int(n_overlap_cells),
        "overlap_share": overlap_share,
        "n_overlap_track_cell_rows": int(len(residuals)),
        "residual_p01": safe_quantile(residuals["residual_m"] if not residuals.empty else pd.Series(dtype=float), 0.01),
        "residual_p05": safe_quantile(residuals["residual_m"] if not residuals.empty else pd.Series(dtype=float), 0.05),
        "residual_p25": safe_quantile(residuals["residual_m"] if not residuals.empty else pd.Series(dtype=float), 0.25),
        "residual_p50": safe_quantile(residuals["residual_m"] if not residuals.empty else pd.Series(dtype=float), 0.50),
        "residual_p75": safe_quantile(residuals["residual_m"] if not residuals.empty else pd.Series(dtype=float), 0.75),
        "residual_p95": safe_quantile(residuals["residual_m"] if not residuals.empty else pd.Series(dtype=float), 0.95),
        "residual_p99": safe_quantile(residuals["residual_m"] if not residuals.empty else pd.Series(dtype=float), 0.99),
        "abs_residual_p50": safe_quantile(residuals["abs_residual_m"] if not residuals.empty else pd.Series(dtype=float), 0.50),
        "abs_residual_p95": safe_quantile(residuals["abs_residual_m"] if not residuals.empty else pd.Series(dtype=float), 0.95),
        "abs_residual_p99": safe_quantile(residuals["abs_residual_m"] if not residuals.empty else pd.Series(dtype=float), 0.99),
        "rmse_residual_m_branch": safe_rmse(residuals["residual_m"] if not residuals.empty else pd.Series(dtype=float)),
        "analysis_version": OVERLAP_VERSION,
        "runtime_seconds": float(runtime_seconds),
    }
    return row


def source_build_breakdowns(residuals: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    manual_rows: list[dict] = []
    breakdown_rows: list[dict] = []

    for branch in BRANCHES:
        bdf = residuals[residuals["branch"] == branch]

        for flag in (False, True):
            sub = bdf[bdf["manual_review_flag"] == flag]
            stats = summarize_residual_distribution(sub)
            row = {"branch": branch, "manual_review_flag": bool(flag), **stats}
            manual_rows.append(row)
            breakdown_rows.append(
                {
                    "breakdown_type": "manual_review_flag",
                    "branch": branch,
                    "group_value": str(bool(flag)),
                    **stats,
                }
            )

        for source_type, sub in bdf.groupby("source_type", dropna=False, sort=True):
            breakdown_rows.append(
                {
                    "breakdown_type": "source_type",
                    "branch": branch,
                    "group_value": str(source_type),
                    **summarize_residual_distribution(sub),
                }
            )

        if bdf.empty:
            for label in SOURCE_DUPLICATE_RATIO_BIN_LABELS:
                breakdown_rows.append(
                    {
                        "breakdown_type": "duplicate_ratio_cell_bin",
                        "branch": branch,
                        "group_value": label,
                        **summarize_residual_distribution(bdf),
                    }
                )
        else:
            bins = pd.cut(
                bdf["branch_cell_duplicate_ratio_cell"].clip(lower=0.0, upper=1.0),
                bins=DUPLICATE_RATIO_BINS,
                labels=SOURCE_DUPLICATE_RATIO_BIN_LABELS,
                include_lowest=True,
                right=False,
            )
            # Include the right edge value 1.0 in the last bin.
            bins = bins.astype(object)
            bins[bdf["branch_cell_duplicate_ratio_cell"] >= 0.5] = "[0.5,1.0]"
            for label in SOURCE_DUPLICATE_RATIO_BIN_LABELS:
                sub = bdf[bins == label]
                breakdown_rows.append(
                    {
                        "breakdown_type": "duplicate_ratio_cell_bin",
                        "branch": branch,
                        "group_value": label,
                        **summarize_residual_distribution(sub),
                    }
                )

    manual_df = pd.DataFrame(manual_rows)
    for col in MANUAL_REVIEW_SUMMARY_COLUMNS:
        if col not in manual_df.columns:
            manual_df[col] = pd.NA
    manual_df = manual_df[MANUAL_REVIEW_SUMMARY_COLUMNS]

    breakdown_df = pd.DataFrame(breakdown_rows)
    for col in SOURCE_BREAKDOWN_COLUMNS:
        if col not in breakdown_df.columns:
            breakdown_df[col] = pd.NA
    breakdown_df = breakdown_df[SOURCE_BREAKDOWN_COLUMNS]
    return manual_df, breakdown_df


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def source_make_report(
    *,
    run_label: str,
    elapsed_s: float,
    branch_summary: pd.DataFrame,
    track_summary: pd.DataFrame,
    breakdowns: pd.DataFrame,
    manual_review_summary: pd.DataFrame,
    residuals: pd.DataFrame,
    paths: dict[str, Path],
    input_counts: dict[str, int],
) -> str:
    lines: list[str] = []
    lines.append("# NCEI Step 05A — Source-specific Overlap Bias Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Run label: `{run_label}`")
    lines.append(f"Analysis version: `{OVERLAP_VERSION}`")
    lines.append(f"Elapsed: {elapsed_s:.1f}s")
    lines.append("")
    lines.append("> Residual definition: `residual_m = track_cell_median_depth_m - branch_cell_median_depth_m`.")
    lines.append("> Only cells with `n_track_cells >= 2` enter this analysis; single-track cells have residual 0 by construction and are excluded.")
    lines.append("> This is source-specific only: no branch is merged with another branch, no validation tiers are defined, and no external grid product is read.")
    lines.append("")

    lines.append("## 1. Per-branch headline numbers")
    lines.append("")
    if run_label != "full":
        lines.append(
            f"> Scope note ({run_label}): `n_branch_cells_total`, `n_overlap_cells`, and `overlap_share` "
            f"are computed against the full Step 04B branch output (see `cells_1min_manifest.parquet`). "
            f"`n_overlap_track_cell_rows` and the residual-percentile / RMSE columns reflect only the "
            f"sampled Step 04A file-cell inputs (see §10 for selected file counts per branch)."
        )
        lines.append("")
    headline_cols = [
        "branch",
        "n_branch_cells_total",
        "n_overlap_cells",
        "overlap_share",
        "n_overlap_track_cell_rows",
        "residual_p05",
        "residual_p50",
        "residual_p95",
        "abs_residual_p50",
        "abs_residual_p95",
        "rmse_residual_m_branch",
    ]
    lines.extend(markdown_table(branch_summary[headline_cols]))

    lines.append("## 2. Residual distribution by source_type per branch")
    lines.append("")
    source_breakdown = breakdowns[breakdowns["breakdown_type"] == "source_type"]
    lines.extend(markdown_table(source_breakdown, max_rows=100))

    lines.append("## 3. Residual distribution by manual_review_flag per branch")
    lines.append("")
    lines.extend(markdown_table(manual_review_summary, max_rows=20))

    lines.append("## 4. Residual distribution by duplicate_ratio_cell bins per branch")
    lines.append("")
    dup_breakdown = breakdowns[breakdowns["breakdown_type"] == "duplicate_ratio_cell_bin"]
    lines.extend(markdown_table(dup_breakdown, max_rows=100))

    lines.append("## 5. Top-20 tracks by p95_abs_residual_m per branch")
    lines.append("")
    for branch in BRANCHES:
        lines.append(f"### {branch}")
        lines.append("")
        cols = [
            "branch",
            "track_id",
            "source_type",
            "source_completeness",
            "manual_review_flag",
            "n_overlap_cells",
            "median_residual_m",
            "p95_abs_residual_m",
            "max_abs_residual_m",
            "duplicate_ratio_summary",
        ]
        top = track_summary[track_summary["branch"] == branch].sort_values(
            "p95_abs_residual_m", ascending=False
        )[cols].head(20)
        lines.extend(markdown_table(top, max_rows=20))

    lines.append("## 6. AUV Sentry deep-dive (multibeam_ncei)")
    lines.append("")
    mb = residuals[residuals["branch"] == "multibeam_ncei"]
    high_dup = mb[mb["branch_cell_duplicate_ratio_cell"] > 0.5]
    lines.append("Cells considered: `multibeam_ncei` residual rows whose branch cell has `duplicate_ratio_cell > 0.5`.")
    lines.append("")
    if high_dup.empty:
        lines.append("No multibeam_ncei overlap residual rows met `duplicate_ratio_cell > 0.5` in this run.")
        lines.append("")
    else:
        sentry = high_dup[high_dup["track_id"].astype(str).str.contains("sentry", case=False, regex=False)]
        sentry_rows = []
        for track_id, sub in sentry.groupby("track_id", sort=True):
            sentry_rows.append(
                {
                    "track_id": track_id,
                    "n_overlap_rows": int(len(sub)),
                    "n_overlap_cells": int(sub["cell_id"].nunique()),
                    "residual_p50": safe_quantile(sub["residual_m"], 0.50),
                    "abs_residual_p95": safe_quantile(sub["abs_residual_m"], 0.95),
                    "max_abs_residual_m": float(sub["abs_residual_m"].max()),
                    "rmse": safe_rmse(sub["residual_m"]),
                }
            )
        overall = pd.DataFrame([
            {
                "group": "all_high_duplicate_multibeam_ncei_rows",
                **summarize_residual_distribution(high_dup),
            },
            {
                "group": "sentry_only_high_duplicate_rows",
                **summarize_residual_distribution(sentry),
            },
        ])
        lines.extend(markdown_table(overall))
        lines.append("Sentry tracks contributing high-duplicate residual rows:")
        lines.append("")
        lines.extend(markdown_table(pd.DataFrame(sentry_rows).sort_values("max_abs_residual_m", ascending=False), max_rows=30))

    lines.append("## 7. Guardrails and cross-links")
    lines.append("")
    lines.append("- Step 04A audit/report: `ncei/docs/step04a_file_cells_1min_report.md`.")
    lines.append("- Step 04B report: `ncei/docs/step04b_cells_1min_merge_report.md`.")
    lines.append("- Spec §13 (Step 04A conventions): `.trellis/spec/backend/pipeline-design-decisions.md#13-ncei-step-04a--per-file-1-arcmin-cell-aggregation`.")
    lines.append("- Spec §14 (Step 04B conventions): `.trellis/spec/backend/pipeline-design-decisions.md#14-ncei-step-04b--source-specific-global-1-arcmin-cell-merge`.")
    lines.append("- Confirmed by this run: residual rows are branch-matched on both sides of the join; no single-track cells entered residual analysis; spot-check equality of the residual formula passed.")
    lines.append("")

    lines.append("## 8. Output paths")
    lines.append("")
    out_rows = [
        {"kind": "per-track-cell residuals", "path": str(paths["residuals_pq"].relative_to(REPO_ROOT))},
        {"kind": "track bias summary", "path": str(paths["track_summary_pq"].relative_to(REPO_ROOT))},
        {"kind": "branch overlap summary", "path": str(paths["branch_summary_pq"].relative_to(REPO_ROOT))},
        {"kind": "branch breakdowns TSV", "path": str(paths["breakdowns_tsv"].relative_to(REPO_ROOT))},
        {"kind": "manual-review TSV", "path": str(paths["manual_review_tsv"].relative_to(REPO_ROOT))},
        {"kind": "report (this file)", "path": str(paths["report_md"].relative_to(REPO_ROOT))},
    ]
    lines.extend(markdown_table(pd.DataFrame(out_rows), max_rows=20))

    lines.append("## 9. Recommendation")
    lines.append("")
    total_rows = int(branch_summary["n_overlap_track_cell_rows"].sum()) if len(branch_summary) else 0
    if total_rows == 0:
        recommendation = "No overlap residual rows were produced in this run; run a larger sample or full mode before Step 05B."
    else:
        recommendation = (
            "Ready to proceed to Step 05B (cross-branch overlap audit) if the headline residual distributions and "
            "Top-20 track tables above are acceptable. Step 05A is descriptive only; potential problem tracks listed "
            "here should be reviewed or downweighted in later stages, not filtered here."
        )
    lines.append(recommendation)
    lines.append("")

    lines.append("## 10. Run inputs")
    lines.append("")
    lines.extend(markdown_table(pd.DataFrame([{"branch": k, "selected_file_cell_parquets": v} for k, v in input_counts.items()])))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def source_existing_outputs(paths: dict[str, Path]) -> list[Path]:
    keys = [
        "residuals_pq",
        "track_summary_pq",
        "branch_summary_pq",
        "breakdowns_tsv",
        "manual_review_tsv",
        "report_md",
    ]
    return [paths[k] for k in keys if paths[k].exists()]


def run_source_overlap(args: argparse.Namespace) -> int:
    paths = source_overlap_paths(args.run_label)
    logger = setup_logging(paths["log"], "ncei_overlap_residuals")
    t0 = datetime.now()

    logger.info("=" * 60)
    logger.info("09_source_specific_overlap_residuals.py START")
    logger.info("Args: %s", vars(args))
    logger.info("Overlap analysis version: %s", OVERLAP_VERSION)

    if args.run_label == "full" and not args.confirm_full:
        logger.error("ABORTED: --run-label=full requires --confirm-full")
        return 2
    if args.run_label == "full" and args.limit_files_per_branch is not None:
        logger.warning("--limit-files-per-branch is ignored in full mode")

    for input_path in (FILE_CELLS_MANIFEST, CELLS_MANIFEST):
        if not input_path.exists():
            logger.error("ABORTED: required input manifest not found: %s", input_path)
            return 2

    if not args.overwrite:
        exists = source_existing_outputs(paths)
        if exists:
            logger.error("ABORTED: outputs exist; use --overwrite. Existing: %s", exists)
            return 2

    try:
        file_manifest = pd.read_parquet(FILE_CELLS_MANIFEST)
        cells_manifest = pd.read_parquet(CELLS_MANIFEST)
        logger.info("Loaded file-cell manifest: %d rows x %d cols", len(file_manifest), len(file_manifest.columns))
        logger.info("Loaded branch-cell manifest: %d rows x %d cols", len(cells_manifest), len(cells_manifest.columns))

        work = select_file_cell_manifest_rows(
            file_manifest,
            run_label=args.run_label,
            limit_files_per_branch=args.limit_files_per_branch,
            logger=logger,
        )
        branches = select_branches(cells_manifest)
        input_counts = {branch: int((work["branch"] == branch).sum()) for branch in branches}
        logger.info("Selected Step 04A file-cell inputs by branch: %s", input_counts)

        residual_frames: list[pd.DataFrame] = []
        branch_summary_rows: list[dict] = []

        for branch in branches:
            branch_t0 = datetime.now()
            logger.info("--- Branch %s ---", branch)
            branch_cells = read_branch_overlap_cells(branch, logger)
            n_branch_cells_total = branch_cell_total(cells_manifest, branch)
            n_overlap_cells = int(len(branch_cells))

            branch_work = work[work["branch"] == branch].reset_index(drop=True)
            if branch_work.empty:
                logger.warning("%s: no Step 04A file-cell inputs selected", branch)
                branch_residuals = pd.DataFrame(columns=RESIDUAL_COLUMNS)
            elif branch_cells.empty:
                logger.warning("%s: no overlap cells in Step 04B output", branch)
                branch_residuals = pd.DataFrame(columns=RESIDUAL_COLUMNS)
            else:
                overlap_cell_ids = set(branch_cells["cell_id"].astype(str).tolist())
                file_cells = read_selected_file_cells(branch, branch_work, overlap_cell_ids, logger)
                logger.info("%s: retained %d Step 04A file-cell rows in overlap cells", branch, len(file_cells))
                branch_residuals = make_branch_residuals(branch, file_cells, branch_cells, logger)

            branch_elapsed = (datetime.now() - branch_t0).total_seconds()
            branch_summary_rows.append(
                summarize_branch(
                    branch,
                    branch_residuals,
                    n_branch_cells_total=n_branch_cells_total,
                    n_overlap_cells=n_overlap_cells,
                    runtime_seconds=branch_elapsed,
                )
            )
            residual_frames.append(branch_residuals)
            logger.info(
                "%s summary: n_branch_cells_total=%d n_overlap_cells=%d residual_rows=%d elapsed=%.1fs",
                branch,
                n_branch_cells_total,
                n_overlap_cells,
                len(branch_residuals),
                branch_elapsed,
            )

        residuals = pd.concat(residual_frames, ignore_index=True, copy=False) if residual_frames else pd.DataFrame(columns=RESIDUAL_COLUMNS)
        residuals = ensure_columns(residuals, RESIDUAL_COLUMNS)

        if len(residuals):
            # Global guardrails after concatenation; still no cross-branch product
            # is written beyond descriptive branch-keyed rows.
            if (pd.to_numeric(residuals["branch_cell_n_track_cells"], errors="coerce") < 2).any():
                raise ValueError("single-track cells entered residual analysis")
            residual_formula_ok = (
                residuals.head(min(5000, len(residuals)))["residual_m"]
                == (
                    residuals.head(min(5000, len(residuals)))["track_cell_median_depth_m"]
                    - residuals.head(min(5000, len(residuals)))["branch_cell_median_depth_m"]
                )
            ).all()
            if not residual_formula_ok:
                raise ValueError("global residual formula spot-check failed")
            logger.info("Global guardrails OK: 0 single-track cells; residual formula spot-check passed")

        track_summary = summarize_tracks(residuals)
        track_summary = ensure_columns(track_summary, TRACK_SUMMARY_COLUMNS)

        branch_summary = pd.DataFrame(branch_summary_rows)
        branch_summary = ensure_columns(branch_summary, BRANCH_SUMMARY_COLUMNS)
        branch_summary = branch_summary.sort_values("branch").reset_index(drop=True)

        manual_review_summary, breakdowns = source_build_breakdowns(residuals)
        manual_review_summary = ensure_columns(manual_review_summary, MANUAL_REVIEW_SUMMARY_COLUMNS)
        breakdowns = ensure_columns(breakdowns, SOURCE_BREAKDOWN_COLUMNS)

        elapsed_s = (datetime.now() - t0).total_seconds()
        report_text = source_make_report(
            run_label=args.run_label,
            elapsed_s=elapsed_s,
            branch_summary=branch_summary,
            track_summary=track_summary,
            breakdowns=breakdowns,
            manual_review_summary=manual_review_summary,
            residuals=residuals,
            paths=paths,
            input_counts=input_counts,
        )

        atomic_write_parquet(residuals, paths["residuals_pq"])
        atomic_write_parquet(track_summary, paths["track_summary_pq"])
        atomic_write_parquet(branch_summary, paths["branch_summary_pq"])
        atomic_write_tsv(breakdowns, paths["breakdowns_tsv"])
        atomic_write_tsv(manual_review_summary, paths["manual_review_tsv"])
        atomic_write_text(report_text, paths["report_md"])

        logger.info("Wrote %s (%d rows)", paths["residuals_pq"], len(residuals))
        logger.info("Wrote %s (%d rows)", paths["track_summary_pq"], len(track_summary))
        logger.info("Wrote %s (%d rows)", paths["branch_summary_pq"], len(branch_summary))
        logger.info("Wrote %s (%d rows)", paths["breakdowns_tsv"], len(breakdowns))
        logger.info("Wrote %s (%d rows)", paths["manual_review_tsv"], len(manual_review_summary))
        logger.info("Wrote %s", paths["report_md"])
        logger.info("Elapsed: %.1fs", elapsed_s)
        logger.info("09_source_specific_overlap_residuals.py DONE")

        print("Selected file-cell inputs by branch:", input_counts)
        print("Residual rows by branch:", residuals["branch"].value_counts().to_dict() if len(residuals) else {})
        print(f"Residuals: {paths['residuals_pq']}")
        print(f"Track summary: {paths['track_summary_pq']}")
        print(f"Branch summary: {paths['branch_summary_pq']}")
        print(f"Report: {paths['report_md']}")
        return 0

    except Exception as exc:  # noqa: BLE001 - pipeline stage top-level guard
        logger.exception("ABORTED with error: %r", exc)
        return 1


# Cross-branch depth comparisons
# ---------------------------------------------------------------------------
# Path / logging / atomic-write helpers
# ---------------------------------------------------------------------------
def cross_overlap_dir(run_label: str) -> Path:
    return DERIVED_DIR / f"cross_branch_overlap_1min{suffix_for_run(run_label)}"


def cross_overlap_paths(run_label: str) -> dict[str, Path]:
    suffix = suffix_for_run(run_label)
    out_dir = cross_overlap_dir(run_label)
    return {
        "out_dir": out_dir,
        "cells_pq": out_dir / "cross_overlap_cells.parquet",
        "pair_summary_pq": out_dir / "cross_overlap_pair_summary.parquet",
        "breakdowns_tsv": out_dir / "cross_overlap_breakdowns.tsv",
        "report_md": DOCS_DIR / f"step05b_cross_branch_overlap_audit_report{suffix}.md",
        "log": LOG_DIR / f"10_cross_branch_overlap_audit{suffix}.log",
    }


def atomic_write_parquet_frames(frames: list[pd.DataFrame], target: Path, columns: list[str]) -> None:
    """Write multiple already-built frames with ParquetWriter if >5M rows.

    Expected production size is below the streaming threshold, but the
    writer path keeps the output stage bounded if future data expands.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    writer: pq.ParquetWriter | None = None
    try:
        for frame in frames:
            table = pa.Table.from_pandas(frame[columns], preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(tmp, table.schema)
            writer.write_table(table)
    finally:
        if writer is not None:
            writer.close()
    os.replace(tmp, target)


# ---------------------------------------------------------------------------
# Generic statistics / formatting helpers
# ---------------------------------------------------------------------------
def summarize_distribution(sub: pd.DataFrame) -> dict[str, float | int]:
    if sub.empty:
        return {
            "n_overlap_cells": 0,
            "residual_p50": float("nan"),
            "abs_residual_p50": float("nan"),
            "abs_residual_p95": float("nan"),
            "abs_residual_p99": float("nan"),
            "rmse": float("nan"),
        }
    return {
        "n_overlap_cells": int(len(sub)),
        "residual_p50": safe_quantile(sub["residual_m"], 0.50),
        "abs_residual_p50": safe_quantile(sub["abs_residual_m"], 0.50),
        "abs_residual_p95": safe_quantile(sub["abs_residual_m"], 0.95),
        "abs_residual_p99": safe_quantile(sub["abs_residual_m"], 0.99),
        "rmse": safe_rmse(sub["residual_m"]),
    }


def compute_lat_band(lat_center: pd.Series) -> pd.Series:
    band = (np.floor(lat_center.astype(float) / 10.0) * 10.0).astype(np.int64)
    return pd.Series(np.clip(band, -90, 80), index=lat_center.index, dtype="int64")


def coerce_cross_cell_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    int_cols = [
        "lon_bin",
        "lat_bin",
        "left_n_track_cells",
        "right_n_track_cells",
        "left_n_tracks",
        "right_n_tracks",
        "left_n_unique_triples_total",
        "right_n_unique_triples_total",
    ]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="raise").astype("int64")
    for col in ("left_manual_review_any", "right_manual_review_any"):
        if col in df.columns:
            df[col] = df[col].fillna(False).astype(bool)
    return df


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------
def read_branch_cells(branch: str, logger: logging.Logger) -> pd.DataFrame:
    path = branch_cells_dir(branch, DERIVED_DIR)
    if not path.exists():
        raise FileNotFoundError(f"Step 04B cells dataset not found for {branch}: {path}")

    dataset = ds.dataset(str(path), format="parquet", partitioning="hive")
    names = set(dataset.schema.names)
    missing = [c for c in CROSS_BRANCH_CELL_COLUMNS if c not in names]
    if missing:
        raise ValueError(f"{path} missing Step 04B columns: {missing}")

    read_cols = list(CROSS_BRANCH_CELL_COLUMNS)
    include_lat_band = "lat_band_10deg" in names
    if include_lat_band:
        read_cols.append("lat_band_10deg")

    table = dataset.to_table(columns=read_cols)
    df = table.to_pandas()
    if df.empty:
        raise ValueError(f"{branch}: Step 04B cells dataset is empty")

    df["branch"] = df["branch"].astype(str)
    branch_values = sorted(df["branch"].unique().tolist())
    if branch_values != [branch]:
        raise ValueError(f"{branch}: Step 04B hive read returned cross-branch rows: {branch_values}")

    if not include_lat_band:
        df["lat_band_10deg"] = compute_lat_band(df["lat_center"])

    # Keep only the small sidecar set that Step 05B is allowed to consume.
    df = df[INTERNAL_BRANCH_CELL_COLUMNS]
    int_cols = ["lon_bin", "lat_bin", "n_track_cells", "n_tracks", "n_unique_triples_total", "lat_band_10deg"]
    for col in int_cols:
        df[col] = pd.to_numeric(df[col], errors="raise").astype("int64")
    df["manual_review_any"] = df["manual_review_any"].fillna(False).astype(bool)
    df["cell_id"] = df["cell_id"].astype(str)
    df = df.sort_values("cell_id").reset_index(drop=True)
    if df["cell_id"].duplicated().any():
        dup = df.loc[df["cell_id"].duplicated(), "cell_id"].head(5).tolist()
        raise ValueError(f"{branch}: duplicate cell_id values in Step 04B cells: {dup}")

    logger.info("%s: loaded %d Step 04B cells from %s", branch, len(df), path)
    return df


# ---------------------------------------------------------------------------
# Pair joins and summaries
# ---------------------------------------------------------------------------
def default_limit_for_run(run_label: str, user_limit: int | None) -> int | None:
    if run_label == "full":
        return None
    if user_limit is not None:
        if user_limit <= 0:
            raise ValueError("--limit-rows-per-pair must be positive when provided")
        return user_limit
    return 50_000 if run_label == "sample" else 200_000


def prefix_branch_columns(df: pd.DataFrame, side: str) -> pd.DataFrame:
    return df.rename(
        columns={
            "branch": f"{side}_branch",
            "lon_bin": f"{side}_lon_bin",
            "lat_bin": f"{side}_lat_bin",
            "lon_center": f"{side}_lon_center",
            "lat_center": f"{side}_lat_center",
            "lat_band_10deg": f"{side}_lat_band_10deg",
            "median_depth_m": f"{side}_median_depth_m",
            "n_track_cells": f"{side}_n_track_cells",
            "n_tracks": f"{side}_n_tracks",
            "n_unique_triples_total": f"{side}_n_unique_triples_total",
            "duplicate_ratio_cell": f"{side}_duplicate_ratio_cell",
            "manual_review_any": f"{side}_manual_review_any",
            "iqr_of_track_medians": f"{side}_iqr_of_track_medians",
        }
    )


def make_pair_overlap(
    *,
    pair_label: str,
    left_branch: str,
    right_branch: str,
    left_cells: pd.DataFrame,
    right_cells: pd.DataFrame,
    limit_rows: int | None,
    logger: logging.Logger,
) -> tuple[pd.DataFrame, dict[str, int | bool]]:
    left = prefix_branch_columns(left_cells, "left")
    right = prefix_branch_columns(right_cells, "right")
    joined = left.merge(right, on="cell_id", how="inner", validate="one_to_one")
    n_total_overlap = int(len(joined))
    if n_total_overlap == 0:
        raise ValueError(f"{pair_label}: no cross-branch overlap cells found")

    joined = joined.sort_values("cell_id", kind="mergesort").reset_index(drop=True)
    capped = False
    if limit_rows is not None and len(joined) > limit_rows:
        joined = joined.head(limit_rows).copy()
        capped = True

    geom_mismatch = int(
        (
            (joined["left_lon_bin"] != joined["right_lon_bin"])
            | (joined["left_lat_bin"] != joined["right_lat_bin"])
        ).sum()
    )
    lat_band_mismatch = int((joined["left_lat_band_10deg"] != joined["right_lat_band_10deg"]).sum())
    if geom_mismatch:
        # cell_id is f"1min_{lat_bin}_{lon_bin}" per spec §13.2 — a left/right
        # disagreement on lon_bin or lat_bin after joining on cell_id indicates
        # an upstream Step 04B violation of the deterministic cell_id formula.
        sample = joined[
            (joined["left_lon_bin"] != joined["right_lon_bin"])
            | (joined["left_lat_bin"] != joined["right_lat_bin"])
        ].head(5)[["cell_id", "left_lon_bin", "right_lon_bin", "left_lat_bin", "right_lat_bin"]]
        logger.error("%s: %d overlap rows have left/right lon_bin or lat_bin mismatch (first 5): %s",
                     pair_label, geom_mismatch, sample.to_dict("records"))
        raise ValueError(
            f"{pair_label}: {geom_mismatch} overlap rows violate the deterministic "
            f"cell_id geometry contract (§13.2); upstream Step 04B output is corrupted"
        )
    if lat_band_mismatch:
        logger.warning("%s: %d overlap rows have left/right lat_band_10deg mismatch", pair_label, lat_band_mismatch)

    out = pd.DataFrame(
        {
            "pair_label": pair_label,
            "left_branch": left_branch,
            "right_branch": right_branch,
            "cell_id": joined["cell_id"],
            "lon_bin": joined["left_lon_bin"],
            "lat_bin": joined["left_lat_bin"],
            "lon_center": joined["left_lon_center"],
            "lat_center": joined["left_lat_center"],
            "left_median_depth_m": joined["left_median_depth_m"],
            "right_median_depth_m": joined["right_median_depth_m"],
            "left_n_track_cells": joined["left_n_track_cells"],
            "right_n_track_cells": joined["right_n_track_cells"],
            "left_n_tracks": joined["left_n_tracks"],
            "right_n_tracks": joined["right_n_tracks"],
            "left_n_unique_triples_total": joined["left_n_unique_triples_total"],
            "right_n_unique_triples_total": joined["right_n_unique_triples_total"],
            "left_duplicate_ratio_cell": joined["left_duplicate_ratio_cell"],
            "right_duplicate_ratio_cell": joined["right_duplicate_ratio_cell"],
            "left_manual_review_any": joined["left_manual_review_any"],
            "right_manual_review_any": joined["right_manual_review_any"],
            "left_iqr_of_track_medians": joined["left_iqr_of_track_medians"],
            "right_iqr_of_track_medians": joined["right_iqr_of_track_medians"],
            "left_lat_band_10deg": joined["left_lat_band_10deg"],
            "right_lat_band_10deg": joined["right_lat_band_10deg"],
        }
    )
    out["residual_m"] = out["left_median_depth_m"] - out["right_median_depth_m"]
    out["abs_residual_m"] = out["residual_m"].abs()
    out["cross_analysis_version"] = CROSS_OVERLAP_VERSION

    # Exact residual self-check on sampled rows.
    sample = out.head(min(5000, len(out)))
    if not (sample["residual_m"] == (sample["left_median_depth_m"] - sample["right_median_depth_m"])).all():
        raise ValueError(f"{pair_label}: residual_m formula spot-check failed")

    out = coerce_cross_cell_dtypes(out)
    logger.info(
        "%s: overlap cells=%d retained=%d capped=%s geom_mismatch=%d lat_band_mismatch=%d",
        pair_label,
        n_total_overlap,
        len(out),
        capped,
        geom_mismatch,
        lat_band_mismatch,
    )
    meta = {
        "n_total_overlap": n_total_overlap,
        "capped": capped,
        "geom_mismatch": geom_mismatch,
        "lat_band_mismatch": lat_band_mismatch,
    }
    return out, meta


def summarize_pair(
    *,
    pair_label: str,
    left_branch: str,
    right_branch: str,
    pair_df: pd.DataFrame,
    n_left_cells_total: int,
    n_right_cells_total: int,
    runtime_seconds: float,
) -> dict:
    n_overlap = int(len(pair_df))
    return {
        "pair_label": pair_label,
        "left_branch": left_branch,
        "right_branch": right_branch,
        "n_left_cells_total": int(n_left_cells_total),
        "n_right_cells_total": int(n_right_cells_total),
        "n_overlap_cells": n_overlap,
        "overlap_share_of_left": float(n_overlap / n_left_cells_total) if n_left_cells_total else float("nan"),
        "overlap_share_of_right": float(n_overlap / n_right_cells_total) if n_right_cells_total else float("nan"),
        "residual_p01": safe_quantile(pair_df["residual_m"], 0.01),
        "residual_p05": safe_quantile(pair_df["residual_m"], 0.05),
        "residual_p25": safe_quantile(pair_df["residual_m"], 0.25),
        "residual_p50": safe_quantile(pair_df["residual_m"], 0.50),
        "residual_p75": safe_quantile(pair_df["residual_m"], 0.75),
        "residual_p95": safe_quantile(pair_df["residual_m"], 0.95),
        "residual_p99": safe_quantile(pair_df["residual_m"], 0.99),
        "abs_residual_p50": safe_quantile(pair_df["abs_residual_m"], 0.50),
        "abs_residual_p95": safe_quantile(pair_df["abs_residual_m"], 0.95),
        "abs_residual_p99": safe_quantile(pair_df["abs_residual_m"], 0.99),
        "rmse_pair_m": safe_rmse(pair_df["residual_m"]),
        "n_overlap_both_flagged": int((pair_df["left_manual_review_any"] & pair_df["right_manual_review_any"]).sum()),
        "n_overlap_either_flagged": int((pair_df["left_manual_review_any"] | pair_df["right_manual_review_any"]).sum()),
        "cross_analysis_version": CROSS_OVERLAP_VERSION,
        "runtime_seconds": float(runtime_seconds),
    }


def branch_build_breakdowns(all_internal: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for pair_label, pdf in all_internal.groupby("pair_label", sort=True):
        pdf = pdf.copy()
        pdf["manual_review_either"] = pdf["left_manual_review_any"] | pdf["right_manual_review_any"]
        pdf["dup_ratio_either"] = pdf[["left_duplicate_ratio_cell", "right_duplicate_ratio_cell"]].max(axis=1)

        for flag in (False, True):
            sub = pdf[pdf["manual_review_either"] == flag]
            rows.append(
                {
                    "breakdown_type": "manual_review_either",
                    "pair_label": pair_label,
                    "group_value": str(bool(flag)),
                    **summarize_distribution(sub),
                }
            )

        if pdf.empty:
            for label in CROSS_DUPLICATE_RATIO_BIN_LABELS:
                rows.append(
                    {
                        "breakdown_type": "dup_ratio_either_bin",
                        "pair_label": pair_label,
                        "group_value": label,
                        **summarize_distribution(pdf),
                    }
                )
        else:
            clipped = pdf["dup_ratio_either"].clip(lower=0.0, upper=1.0)
            bins = pd.cut(
                clipped,
                bins=DUPLICATE_RATIO_BINS,
                labels=CROSS_DUPLICATE_RATIO_BIN_LABELS,
                include_lowest=True,
                right=False,
            ).astype(object)
            bins[clipped >= 0.5] = "[0.5, 1.0]"
            for label in CROSS_DUPLICATE_RATIO_BIN_LABELS:
                sub = pdf[bins == label]
                rows.append(
                    {
                        "breakdown_type": "dup_ratio_either_bin",
                        "pair_label": pair_label,
                        "group_value": label,
                        **summarize_distribution(sub),
                    }
                )

        for band, sub in pdf.groupby("left_lat_band_10deg", dropna=False, sort=True):
            rows.append(
                {
                    "breakdown_type": "lat_band_10deg",
                    "pair_label": pair_label,
                    "group_value": str(int(band)) if pd.notna(band) else "NA",
                    **summarize_distribution(sub),
                }
            )

    out = pd.DataFrame(rows)
    return ensure_columns(out, CROSS_BREAKDOWN_COLUMNS)


def spot_check_pair_from_dataset(
    *,
    pair_label: str,
    left_branch: str,
    right_branch: str,
    pair_df: pd.DataFrame,
    run_label: str,
    logger: logging.Logger,
) -> dict[str, str | float]:
    row = pair_df.iloc[0]
    cell_id = str(row["cell_id"])

    def load_one(branch: str) -> pd.DataFrame:
        dataset = ds.dataset(str(branch_cells_dir(branch, DERIVED_DIR)), format="parquet", partitioning="hive")
        table = dataset.to_table(
            columns=["branch", "cell_id", "median_depth_m"],
            filter=(ds.field("cell_id") == cell_id),
        )
        return table.to_pandas()

    left = load_one(left_branch)
    right = load_one(right_branch)
    if len(left) != 1 or len(right) != 1:
        raise ValueError(
            f"{pair_label}: spot-check expected one row per side for {cell_id}; "
            f"got left={len(left)} right={len(right)}"
        )
    expected = float(left["median_depth_m"].iloc[0] - right["median_depth_m"].iloc[0])
    observed = float(row["residual_m"])
    if not np.isclose(expected, observed, rtol=0.0, atol=0.0):
        raise ValueError(
            f"{pair_label}: dataset spot-check failed for {cell_id}: expected {expected}, observed {observed}"
        )
    logger.info("%s: dataset spot-check OK on %s (residual_m=%.6f)", pair_label, cell_id, observed)
    return {"pair_label": pair_label, "cell_id": cell_id, "residual_m": observed, "status": "OK"}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def make_cross_check_table(pair_meta: dict[str, dict[str, int | bool]], run_label: str) -> pd.DataFrame:
    rows = []
    for pair_label in sorted(EXPECTED_PAIR_LABELS):
        observed_total = int(pair_meta[pair_label]["n_total_overlap"])
        estimate = AUDIT_OVERLAP_ESTIMATES[pair_label]
        deviation = float((observed_total - estimate) / estimate) if estimate else float("nan")
        rows.append(
            {
                "pair_label": pair_label,
                "observed_total_overlap": observed_total,
                "audit_estimate": estimate,
                "deviation_pct": deviation * 100.0,
                "gt_5pct_deviation": bool(abs(deviation) > 0.05) if np.isfinite(deviation) else True,
                "run_label_note": "full comparable" if run_label == "full" else "sample/test observed_total is pre-cap; output rows may be capped",
            }
        )
    return pd.DataFrame(rows)


def branch_make_report(
    *,
    run_label: str,
    elapsed_s: float,
    pair_summary: pd.DataFrame,
    breakdowns: pd.DataFrame,
    all_internal: pd.DataFrame,
    pair_meta: dict[str, dict[str, int | bool]],
    spot_checks: list[dict[str, str | float]],
    paths: dict[str, Path],
) -> str:
    cross_checks = make_cross_check_table(pair_meta, run_label)
    lines: list[str] = []
    lines.append("# NCEI Step 05B — Cross-branch Overlap Audit Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Run label: `{run_label}`")
    lines.append(f"Cross-analysis version: `{CROSS_OVERLAP_VERSION}`")
    lines.append(f"Elapsed: {elapsed_s:.1f}s")
    lines.append("")
    lines.append("> Residual definition: `residual_m = left_branch.median_depth_m - right_branch.median_depth_m`.")
    lines.append("> This audit joins Step 04B branch-cell outputs on `cell_id` only. It does not merge branches, define A/B/C tiers, introduce exclusions, read points, or read external grids.")
    if run_label != "full":
        lines.append("> Scope note: sample/test100 outputs are capped per pair by `cell_id` lexicographic order. The cross-check section still reports the pre-cap overlap count computed from the branch-cell intersection.")
    lines.append("")

    lines.append("## 1. Per-pair headline")
    lines.append("")
    headline_cols = [
        "pair_label",
        "left_branch",
        "right_branch",
        "n_overlap_cells",
        "overlap_share_of_left",
        "overlap_share_of_right",
        "residual_p05",
        "residual_p50",
        "residual_p95",
        "abs_residual_p50",
        "abs_residual_p95",
        "abs_residual_p99",
        "rmse_pair_m",
        "n_overlap_either_flagged",
    ]
    lines.extend(markdown_table(pair_summary[headline_cols], max_rows=10))

    lines.append("## 2. Spatial distribution per pair (`lat_band_10deg`)")
    lines.append("")
    lines.append("Latitude bands use the left branch's `lat_band_10deg`; any left/right band mismatches are logged and summarized in §6.")
    lines.append("")
    lat_breakdowns = breakdowns[breakdowns["breakdown_type"] == "lat_band_10deg"]
    for pair_label in sorted(EXPECTED_PAIR_LABELS):
        lines.append(f"### {pair_label}")
        lines.append("")
        sub = lat_breakdowns[lat_breakdowns["pair_label"] == pair_label].sort_values("abs_residual_p95", ascending=False)
        lines.extend(markdown_table(sub, max_rows=30))

    lines.append("## 3. By `dup_ratio_either` bin")
    lines.append("")
    dup_breakdowns = breakdowns[breakdowns["breakdown_type"] == "dup_ratio_either_bin"]
    lines.extend(markdown_table(dup_breakdowns, max_rows=100))

    lines.append("## 4. By `manual_review_either`")
    lines.append("")
    manual_breakdowns = breakdowns[breakdowns["breakdown_type"] == "manual_review_either"]
    lines.extend(markdown_table(manual_breakdowns, max_rows=20))

    lines.append("## 5. Top-50 highest |residual_m| cells per pair")
    lines.append("")
    top_cols = [
        "cell_id",
        "lon_center",
        "lat_center",
        "left_median_depth_m",
        "right_median_depth_m",
        "residual_m",
        "abs_residual_m",
        "left_n_track_cells",
        "right_n_track_cells",
        "left_manual_review_any",
        "right_manual_review_any",
    ]
    for pair_label in sorted(EXPECTED_PAIR_LABELS):
        lines.append(f"### {pair_label}")
        lines.append("")
        top = all_internal[all_internal["pair_label"] == pair_label].sort_values("abs_residual_m", ascending=False)[top_cols].head(50)
        lines.extend(markdown_table(top, max_rows=50))

    lines.append("## 6. Cross-checks against Step 04 audit estimates")
    lines.append("")
    lines.extend(markdown_table(cross_checks, max_rows=10))
    mismatch_rows = []
    for pair_label in sorted(EXPECTED_PAIR_LABELS):
        meta = pair_meta[pair_label]
        mismatch_rows.append(
            {
                "pair_label": pair_label,
                "capped": bool(meta["capped"]),
                "geom_mismatch_rows": int(meta["geom_mismatch"]),
                "lat_band_mismatch_rows": int(meta["lat_band_mismatch"]),
            }
        )
    lines.append("Self-check metadata:")
    lines.append("")
    lines.extend(markdown_table(pd.DataFrame(mismatch_rows), max_rows=10))
    lines.append("Dataset spot-checks:")
    lines.append("")
    lines.extend(markdown_table(pd.DataFrame(spot_checks), max_rows=10))

    lines.append("## 7. Cross-links")
    lines.append("")
    lines.append("- Spec §13 (Step 04A conventions): `.trellis/spec/backend/pipeline-design-decisions.md#13-ncei-step-04a--per-file-1-arcmin-cell-aggregation`.")
    lines.append("- Spec §14 (Step 04B conventions): `.trellis/spec/backend/pipeline-design-decisions.md#14-ncei-step-04b--source-specific-global-1-arcmin-cell-merge`.")
    lines.append("- Spec §15 (Step 05A conventions): `.trellis/spec/backend/pipeline-design-decisions.md#15-ncei-step-05a--source-specific-overlap-residual-analysis`.")
    lines.append("- Step 04A audit: `ncei/docs/step04_aggregation_design_audit.md`.")
    lines.append("- Step 04B report: `ncei/docs/step04b_cells_1min_merge_report.md`.")
    lines.append("- Step 05A report: `ncei/docs/step05a_source_specific_overlap_bias_report.md`.")
    lines.append("")

    lines.append("## 8. Output paths")
    lines.append("")
    path_rows = [
        {"kind": "per-cell cross-branch residuals", "path": str(paths["cells_pq"].relative_to(REPO_ROOT))},
        {"kind": "per-pair summary", "path": str(paths["pair_summary_pq"].relative_to(REPO_ROOT))},
        {"kind": "breakdowns TSV", "path": str(paths["breakdowns_tsv"].relative_to(REPO_ROOT))},
        {"kind": "report (this file)", "path": str(paths["report_md"].relative_to(REPO_ROOT))},
    ]
    lines.extend(markdown_table(pd.DataFrame(path_rows), max_rows=10))

    lines.append("## 9. Recommendation")
    lines.append("")
    any_deviation = bool(cross_checks["gt_5pct_deviation"].any())
    any_geom_mismatch = any(int(meta["geom_mismatch"]) > 0 for meta in pair_meta.values())
    if run_label != "full":
        recommendation = (
            "Use this sample/test output as a plumbing check only. Run full mode before using the "
            "cross-branch distributions for A/B/C quality-tier calibration or PR-G validation planning."
        )
    elif any_deviation or any_geom_mismatch:
        recommendation = (
            "Do further cross-branch investigation before tier calibration: at least one pair deviates "
            ">5% from the Step 04 audit estimate or has geometry mismatches."
        )
    else:
        recommendation = (
            "Full cross-branch audit is ready to inform A/B/C quality-tier calibration and PR-G planning. "
            "This report is evidence only; a future policy stage must still define merge priorities and thresholds."
        )
    lines.append(recommendation)
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def branch_existing_outputs(paths: dict[str, Path]) -> list[Path]:
    keys = ["cells_pq", "pair_summary_pq", "breakdowns_tsv", "report_md"]
    return [paths[k] for k in keys if paths[k].exists()]


def run_branch_overlap(args: argparse.Namespace) -> int:
    paths = cross_overlap_paths(args.run_label)
    logger = setup_logging(paths["log"], "ncei_cross_branch_overlap")
    t0 = datetime.now()

    logger.info("=" * 60)
    logger.info("10_cross_branch_overlap_audit.py START")
    logger.info("Args: %s", vars(args))
    logger.info("Cross-overlap analysis version: %s", CROSS_OVERLAP_VERSION)

    if args.run_label == "full" and not args.confirm_full:
        logger.error("ABORTED: --run-label=full requires --confirm-full")
        return 2
    if args.run_label == "full" and args.limit_rows_per_pair is not None:
        logger.warning("--limit-rows-per-pair is ignored in full mode")

    limit_rows = default_limit_for_run(args.run_label, args.limit_rows_per_pair)
    if limit_rows is not None:
        logger.info("Per-pair overlap cap: %d rows by cell_id lexicographic order", limit_rows)

    if not CELLS_MANIFEST.exists():
        logger.error("ABORTED: required Step 04B manifest not found: %s", CELLS_MANIFEST)
        return 2

    if not args.overwrite:
        exists = branch_existing_outputs(paths)
        if exists:
            logger.error("ABORTED: outputs exist; use --overwrite. Existing: %s", exists)
            return 2

    try:
        cells_manifest = pd.read_parquet(CELLS_MANIFEST)
    except Exception as exc:  # noqa: BLE001 - pipeline stage top-level guard
        logger.exception("ABORTED loading Step 04B manifest: %r", exc)
        return 1

    try:
        logger.info("Loaded Step 04B cells manifest: %d rows x %d cols", len(cells_manifest), len(cells_manifest.columns))
        branches = select_branches(cells_manifest)
        branch_totals = {branch: branch_cell_total(cells_manifest, branch) for branch in branches}

        logger.info("Branch cell totals from manifest/dataset: %s", branch_totals)

        pair_labels = {label for label, _, _ in PAIR_SPECS}
        if pair_labels != EXPECTED_PAIR_LABELS:
            raise ValueError(f"pair label set drift: expected {EXPECTED_PAIR_LABELS}, got {pair_labels}")
        logger.info("Pair-label assertion OK: %s", sorted(pair_labels))

        branch_cells: dict[str, pd.DataFrame] = {}
        for branch in branches:
            branch_cells[branch] = read_branch_cells(branch, logger)

        pair_frames: list[pd.DataFrame] = []
        summary_rows: list[dict] = []
        pair_meta: dict[str, dict[str, int | bool]] = {}
        spot_checks: list[dict[str, str | float]] = []

        for pair_label, left_branch, right_branch in PAIR_SPECS:
            pair_t0 = datetime.now()
            logger.info("--- Pair %s: %s x %s ---", pair_label, left_branch, right_branch)
            pair_df, meta = make_pair_overlap(
                pair_label=pair_label,
                left_branch=left_branch,
                right_branch=right_branch,
                left_cells=branch_cells[left_branch],
                right_cells=branch_cells[right_branch],
                limit_rows=limit_rows,
                logger=logger,
            )
            pair_elapsed = (datetime.now() - pair_t0).total_seconds()
            summary_rows.append(
                summarize_pair(
                    pair_label=pair_label,
                    left_branch=left_branch,
                    right_branch=right_branch,
                    pair_df=pair_df,
                    n_left_cells_total=branch_totals[left_branch],
                    n_right_cells_total=branch_totals[right_branch],
                    runtime_seconds=pair_elapsed,
                )
            )
            pair_meta[pair_label] = meta
            spot_checks.append(
                spot_check_pair_from_dataset(
                    pair_label=pair_label,
                    left_branch=left_branch,
                    right_branch=right_branch,
                    pair_df=pair_df,
                    run_label=args.run_label,
                    logger=logger,
                )
            )
            pair_frames.append(pair_df)

        if len(pair_frames) != 3:
            raise ValueError(f"expected 3 pair frames, got {len(pair_frames)}")
        if any(frame.empty for frame in pair_frames):
            empty_labels = [str(frame["pair_label"].iloc[0]) if "pair_label" in frame and len(frame) else "unknown" for frame in pair_frames if frame.empty]
            raise ValueError(f"at least one pair is empty: {empty_labels}")

        all_internal = pd.concat(pair_frames, ignore_index=True, copy=False)
        observed_pair_labels = set(all_internal["pair_label"].astype(str).unique())
        if observed_pair_labels != EXPECTED_PAIR_LABELS:
            raise ValueError(f"output pair labels drift: expected {EXPECTED_PAIR_LABELS}, got {observed_pair_labels}")
        logger.info("Output pair-label assertion OK: %s", sorted(observed_pair_labels))

        all_public = ensure_columns(all_internal, CROSS_CELL_COLUMNS)
        summary = pd.DataFrame(summary_rows)
        summary = ensure_columns(summary, PAIR_SUMMARY_COLUMNS).sort_values("pair_label").reset_index(drop=True)
        breakdowns = branch_build_breakdowns(all_internal)

        elapsed_s = (datetime.now() - t0).total_seconds()
        report_text = branch_make_report(
            run_label=args.run_label,
            elapsed_s=elapsed_s,
            pair_summary=summary,
            breakdowns=breakdowns,
            all_internal=all_internal,
            pair_meta=pair_meta,
            spot_checks=spot_checks,
            paths=paths,
        )

        total_rows = int(len(all_public))
        if total_rows > STREAMING_ROW_THRESHOLD:
            logger.info(
                "Writing cross-overlap cells with ParquetWriter streaming path (%d rows > %d)",
                total_rows,
                STREAMING_ROW_THRESHOLD,
            )
            public_frames = [ensure_columns(frame, CROSS_CELL_COLUMNS) for frame in pair_frames]
            atomic_write_parquet_frames(public_frames, paths["cells_pq"], CROSS_CELL_COLUMNS)
        else:
            atomic_write_parquet(all_public, paths["cells_pq"])
        atomic_write_parquet(summary, paths["pair_summary_pq"])
        atomic_write_tsv(breakdowns, paths["breakdowns_tsv"])
        atomic_write_text(report_text, paths["report_md"])

        cross_checks = make_cross_check_table(pair_meta, args.run_label)
        bad_deviations = cross_checks[cross_checks["gt_5pct_deviation"]]
        if len(bad_deviations):
            logger.warning(
                "Observed overlap counts deviate >5%% from audit estimates: %s",
                bad_deviations[["pair_label", "observed_total_overlap", "audit_estimate", "deviation_pct"]].to_dict("records"),
            )
        else:
            logger.info("Observed overlap counts are within 5%% of Step 04 audit estimates")

        logger.info("Wrote %s (%d rows)", paths["cells_pq"], total_rows)
        logger.info("Wrote %s (%d rows)", paths["pair_summary_pq"], len(summary))
        logger.info("Wrote %s (%d rows)", paths["breakdowns_tsv"], len(breakdowns))
        logger.info("Wrote %s", paths["report_md"])
        logger.info("Elapsed: %.1fs", elapsed_s)
        logger.info("10_cross_branch_overlap_audit.py DONE")

        print("Cross-overlap rows by pair:", all_public["pair_label"].value_counts().sort_index().to_dict())
        print("Observed total overlaps before caps:", {k: int(v["n_total_overlap"]) for k, v in pair_meta.items()})
        print(f"Cross-overlap cells: {paths['cells_pq']}")
        print(f"Pair summary:        {paths['pair_summary_pq']}")
        print(f"Breakdowns:          {paths['breakdowns_tsv']}")
        print(f"Report:              {paths['report_md']}")
        return 0

    except Exception as exc:  # noqa: BLE001 - pipeline stage top-level guard
        logger.exception("ABORTED with error: %r", exc)
        return 1
