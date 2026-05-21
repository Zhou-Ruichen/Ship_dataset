#!/usr/bin/env python3
"""
09_source_specific_overlap_residuals.py

Step 05A — Source-specific overlap residual analysis for NCEI branch
cell products.

This descriptive audit consumes ONLY Step 04A per-file-cell outputs and
Step 04B branch-cell outputs. It stays within each source branch
(singlebeam, multibeam_ncei, regional_mrar), joins per-track/per-file
cell medians to the corresponding branch median for cells with at least
two contributing track-cells, and reports within-branch residuals:

    residual_m = per_file_cell.median_depth_m - branch_cell.median_depth_m

No point-level data are read, no cross-branch product is created, no
external grids (GEBCO / ETOPO / SRTM15 / SWOT) are touched, and no
filter/exclusion decision is made. Manual-review and duplicate-ratio
fields are carried through as audit dimensions only.

Inputs (read-only):
  - ncei/manifests/file_cells_1min_manifest.parquet
  - ncei/manifests/cells_1min_manifest.parquet
  - ncei/derived/{singlebeam,multibeam,regional_mrar}/file_cells_1min/*.parquet
  - ncei/derived/{singlebeam,multibeam,regional_mrar}/cells_1min/ hive datasets

Outputs (full mode):
  - ncei/derived/overlap_bias_1min/source_specific_overlap_residuals.parquet
  - ncei/derived/overlap_bias_1min/track_bias_summary.parquet
  - ncei/derived/overlap_bias_1min/branch_overlap_summary.parquet
  - ncei/derived/overlap_bias_1min/branch_overlap_breakdowns.tsv
  - ncei/derived/overlap_bias_1min/manual_review_overlap_summary.tsv
  - ncei/docs/step05a_source_specific_overlap_bias_report.md
  - ncei/output/logs/09_source_specific_overlap_residuals.log

Sample/test100 modes write to suffixed output directories and log/report
filenames (for example overlap_bias_1min_sample/ and *_sample.log).
Full mode requires --confirm-full.

Usage:
    python ncei/code/09_source_specific_overlap_residuals.py --help
    python ncei/code/09_source_specific_overlap_residuals.py --run-label sample --overwrite
    python ncei/code/09_source_specific_overlap_residuals.py --run-label test100 --overwrite
    python ncei/code/09_source_specific_overlap_residuals.py --run-label full --confirm-full --overwrite

Always run from repo root (/mnt/data2/00-Data/ship) per the project's
"run from repo root" convention.
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

FILE_CELLS_MANIFEST = MANIFEST_DIR / "file_cells_1min_manifest.parquet"
CELLS_MANIFEST = MANIFEST_DIR / "cells_1min_manifest.parquet"

VALID_RUN_LABELS = ("sample", "test100", "full")
BRANCHES = ("singlebeam", "multibeam_ncei", "regional_mrar")
OVERLAP_VERSION = "ncei_overlap_v0.1.0"

# Branch names are the data/manifest names. Directory names follow the
# already-established NCEI derived layout: the NCEI multibeam branch lives
# under derived/multibeam/ even though its branch label is multibeam_ncei.
BRANCH_DERIVED_DIRS = {
    "singlebeam": DERIVED_DIR / "singlebeam",
    "multibeam_ncei": DERIVED_DIR / "multibeam",
    "regional_mrar": DERIVED_DIR / "regional_mrar",
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

REQUIRED_BRANCH_CELL_COLUMNS = [
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

BREAKDOWN_COLUMNS = [
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
DUPLICATE_RATIO_BIN_LABELS = ["[0,0.01)", "[0.01,0.1)", "[0.1,0.5)", "[0.5,1.0]"]
FALLBACK_REVIEW_REASON = "step03b_flag"


# ---------------------------------------------------------------------------
# Path / logging / atomic-write helpers
# ---------------------------------------------------------------------------
def suffix_for_run(run_label: str) -> str:
    return "" if run_label == "full" else f"_{run_label}"


def output_dir_for_run(run_label: str) -> Path:
    return DERIVED_DIR / f"overlap_bias_1min{suffix_for_run(run_label)}"


def get_output_paths(run_label: str) -> dict[str, Path]:
    suffix = suffix_for_run(run_label)
    out_dir = output_dir_for_run(run_label)
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


def repo_path(rel_path: str) -> Path:
    return REPO_ROOT / rel_path


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
    logger = logging.getLogger("ncei_overlap_residuals")
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


def branch_cells_dir(branch: str) -> Path:
    return BRANCH_DERIVED_DIRS[branch] / "cells_1min"


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


def read_parquet_schema(path: Path) -> list[str]:
    return pq.read_schema(path).names


def read_branch_overlap_cells(branch: str, logger: logging.Logger) -> pd.DataFrame:
    """Read Step 04B cells for one branch, filtered to n_track_cells>=2."""
    path = branch_cells_dir(branch)
    if not path.exists():
        raise FileNotFoundError(f"Step 04B cells dataset not found for {branch}: {path}")

    dataset = ds.dataset(str(path), format="parquet", partitioning="hive")
    names = set(dataset.schema.names)
    missing = [c for c in REQUIRED_BRANCH_CELL_COLUMNS if c not in names]
    if missing:
        raise ValueError(f"{path} missing Step 04B columns: {missing}")

    table = dataset.to_table(
        columns=REQUIRED_BRANCH_CELL_COLUMNS,
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


def get_branch_cell_total(cells_manifest: pd.DataFrame, branch: str) -> int:
    row = cells_manifest[cells_manifest["branch"].astype(str) == branch]
    if row.empty:
        raise ValueError(f"cells manifest has no row for {branch}")
    for col in ("n_cells_total", "n_branch_cells_total"):
        if col in row.columns and pd.notna(row.iloc[0][col]):
            return int(row.iloc[0][col])
    dataset = ds.dataset(str(branch_cells_dir(branch)), format="parquet", partitioning="hive")
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


def build_breakdowns(residuals: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
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
            for label in DUPLICATE_RATIO_BIN_LABELS:
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
                labels=DUPLICATE_RATIO_BIN_LABELS,
                include_lowest=True,
                right=False,
            )
            # Include the right edge value 1.0 in the last bin.
            bins = bins.astype(object)
            bins[bdf["branch_cell_duplicate_ratio_cell"] >= 0.5] = "[0.5,1.0]"
            for label in DUPLICATE_RATIO_BIN_LABELS:
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
    for col in BREAKDOWN_COLUMNS:
        if col not in breakdown_df.columns:
            breakdown_df[col] = pd.NA
    breakdown_df = breakdown_df[BREAKDOWN_COLUMNS]
    return manual_df, breakdown_df


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def make_report(
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
def existing_outputs(paths: dict[str, Path]) -> list[Path]:
    keys = [
        "residuals_pq",
        "track_summary_pq",
        "branch_summary_pq",
        "breakdowns_tsv",
        "manual_review_tsv",
        "report_md",
    ]
    return [paths[k] for k in keys if paths[k].exists()]


def ensure_columns(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = pd.NA
    return out[list(columns)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Step 05A — Source-specific overlap residuals for NCEI Step 04A/04B "
            "branch products. Run from repo root (/mnt/data2/00-Data/ship)."
        )
    )
    parser.add_argument("--run-label", choices=VALID_RUN_LABELS, default="sample")
    parser.add_argument(
        "--limit-files-per-branch",
        type=int,
        default=None,
        help="Limit non-M.rar branches to N Step 04A per-file-cell parquets in sample/test100 mode "
        "(defaults: sample=50, test100=100; ignored for full; M.rar always all 3).",
    )
    parser.add_argument("--confirm-full", action="store_true", help="Required when --run-label=full")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing Step 05A outputs")
    args = parser.parse_args()

    paths = get_output_paths(args.run_label)
    logger = setup_logging(paths["log"])
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
        exists = existing_outputs(paths)
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
            n_branch_cells_total = get_branch_cell_total(cells_manifest, branch)
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

        manual_review_summary, breakdowns = build_breakdowns(residuals)
        manual_review_summary = ensure_columns(manual_review_summary, MANUAL_REVIEW_SUMMARY_COLUMNS)
        breakdowns = ensure_columns(breakdowns, BREAKDOWN_COLUMNS)

        elapsed_s = (datetime.now() - t0).total_seconds()
        report_text = make_report(
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


if __name__ == "__main__":
    raise SystemExit(main())
