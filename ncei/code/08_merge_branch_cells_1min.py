#!/usr/bin/env python3
"""
08_merge_branch_cells_1min.py

Step 04B — Source-specific global 1-arcmin cell merge for the NCEI
branches (singlebeam, multibeam_ncei, regional_mrar).

This stage consumes the Step 04A per-file/per-track cell manifest and
merges per-file-cell rows into branch-specific global cell datasets. It
never combines branches, never creates validation cells, never defines
A/B/C tiers, and never pools point-level rows. The depth rule is the
contractual file-balanced median from the backend spec: per global cell,
`median_depth_m = median(per_file_cell.median_depth_m)`.

Inputs (read-only):
  - ncei/manifests/file_cells_1min_manifest.parquet
  - per-file-cell parquets referenced by that manifest's `output_path`

Outputs (full mode):
  - ncei/derived/singlebeam/cells_1min/
  - ncei/derived/multibeam/cells_1min/
  - ncei/derived/regional_mrar/cells_1min/
  - ncei/manifests/cells_1min_manifest.parquet
  - ncei/docs/step04b_cells_1min_merge_report.md
  - ncei/output/logs/08_merge_branch_cells_1min.log

For run-label safety, sample/test100 runs use suffixed dataset roots and
manifest/report/log filenames (`*_sample`, `*_test100`) so exploratory
runs cannot clobber production Step 04B outputs. Full mode writes the
canonical paths and requires `--confirm-full`.

Usage:
    python ncei/code/08_merge_branch_cells_1min.py --help
    python ncei/code/08_merge_branch_cells_1min.py --run-label sample --overwrite
    python ncei/code/08_merge_branch_cells_1min.py --run-label test100 --overwrite
    python ncei/code/08_merge_branch_cells_1min.py --run-label full --confirm-full --overwrite

Always run from repo root (`/mnt/data2/00-Data/ship`) per the project's
"run from repo root" convention.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
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

MANIFEST_DIR = ROOT_DIR / "manifests"
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"

INPUT_MANIFEST = MANIFEST_DIR / "file_cells_1min_manifest.parquet"

DERIVED_SB = ROOT_DIR / "derived" / "singlebeam"
DERIVED_MB = ROOT_DIR / "derived" / "multibeam"
DERIVED_REG = ROOT_DIR / "derived" / "regional_mrar"

VALID_RUN_LABELS = ("sample", "test100", "full")
MERGE_VERSION = "ncei_cells_merge_v0.1.0"

# Branch names are the Step 04A / spec §13 names. Output directory names
# intentionally use `multibeam/` for the NCEI multibeam branch, matching
# the existing derived layout.
BRANCHES = ("singlebeam", "multibeam_ncei", "regional_mrar")
BRANCH_OUTPUT_BASES = {
    "singlebeam": DERIVED_SB,
    "multibeam_ncei": DERIVED_MB,
    "regional_mrar": DERIVED_REG,
}

# Full-mode manifest row counts from spec §13.6 / Step 04A report.
EXPECTED_FULL_INPUTS = {
    "singlebeam": 5_365,
    "multibeam_ncei": 17,
    "regional_mrar": 3,
}

# Per-file-cell columns required from Step 04A parquets.
REQUIRED_FILE_CELL_COLUMNS = [
    "track_id",
    "source_type",
    "source_completeness",
    "instrument_class_pred",
    "branch",
    "cell_id",
    "lon_bin",
    "lat_bin",
    "lon_center",
    "lat_center",
    "n_points_pass",
    "n_unique_triples",
    "median_depth_m",
    "manual_review_flag",
]

# Final user-facing schema order from the brief. The partition key
# `lat_band_10deg` is appended for dataset writing.
OUTPUT_COLUMNS = [
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
    "mean_of_track_medians",
    "std_of_track_medians",
    "iqr_of_track_medians",
    "min_track_median",
    "max_track_median",
    "range_track_median",
    "n_source_ncei_nc",
    "n_source_ncei_xyz",
    "n_source_mrar_zhoushuai",
    "n_completeness_nc_xyz_intersect",
    "n_completeness_xyz_only",
    "n_completeness_nc_only",
    "n_instrument_singlebeam",
    "n_instrument_multibeam",
    "manual_review_any",
    "manual_review_track_cell_count",
    "manual_review_unique_triples",
    "manual_review_unique_triples_share",
    "manual_review_reasons",
]
OUTPUT_COLUMNS_WITH_PARTITION = OUTPUT_COLUMNS + ["lat_band_10deg"]

MANIFEST_COLUMNS = [
    "branch",
    "n_cells_total",
    "n_track_cells_total",
    "n_tracks_total",
    "n_points_pass_grand_total",
    "n_unique_triples_grand_total",
    "n_lat_bands_occupied",
    "n_manual_review_cells",
    "manual_review_cell_share",
    "runtime_seconds",
    "merge_version",
]

# If future Step 04A outputs carry a reason column, use it. Current
# Step 04A outputs carry only `manual_review_flag`, so the fallback is
# expected today.
MANUAL_REVIEW_REASON_CANDIDATES = [
    "manual_review_reason",
    "manual_review_reasons",
    "review_reason",
    "review_reasons",
    "classification_review",
    "classification_review_reason",
]
FALLBACK_REVIEW_REASON = "step03b_flag"

MRAR_SOURCE_TYPE_VALUES = frozenset({"mrar_zhoushuai", "mrar_processed", "ncei_mrar"})


# ---------------------------------------------------------------------------
# Paths / atomic writes / logging
# ---------------------------------------------------------------------------
def suffix_for_run(run_label: str) -> str:
    return "" if run_label == "full" else f"_{run_label}"


def cells_output_dir(branch: str, run_label: str) -> Path:
    """Return the branch-specific Step 04B dataset root.

    Full mode writes canonical `cells_1min/`. Non-full runs use suffixed
    roots for run-label safety.
    """
    suffix = suffix_for_run(run_label)
    return BRANCH_OUTPUT_BASES[branch] / f"cells_1min{suffix}"


def get_output_paths(run_label: str) -> dict[str, Path]:
    suffix = suffix_for_run(run_label)
    return {
        "manifest_pq": MANIFEST_DIR / f"cells_1min_manifest{suffix}.parquet",
        "report_md": DOCS_DIR / f"step04b_cells_1min_merge_report{suffix}.md",
        "log": LOG_DIR / f"08_merge_branch_cells_1min{suffix}.log",
    }


def repo_path(rel_path: str) -> Path:
    return REPO_ROOT / rel_path


def atomic_write_parquet(df: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    df.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, target)


def atomic_write_text(text: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)


def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ncei_cells_1min_merge")
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
# Input inspection / selection
# ---------------------------------------------------------------------------
def read_parquet_schema(path: Path) -> list[str]:
    return pq.read_schema(path).names


def find_manual_review_reason_column(paths: Iterable[Path], logger: logging.Logger) -> str | None:
    """Inspect a small set of per-file-cell parquets for a reason column."""
    inspected = 0
    for path in paths:
        if not path.exists():
            continue
        inspected += 1
        names = read_parquet_schema(path)
        for col in MANUAL_REVIEW_REASON_CANDIDATES:
            if col in names:
                logger.info("manual_review reason column detected: %s (from %s)", col, path)
                return col
        if inspected >= 12:
            break
    logger.info(
        "No per-file-cell manual-review reason column detected in %d inspected files; "
        "flagged contributors will use fallback reason %r",
        inspected,
        FALLBACK_REVIEW_REASON,
    )
    return None


def select_manifest_rows(
    manifest: pd.DataFrame,
    *,
    run_label: str,
    limit_files_per_branch: int | None,
    logger: logging.Logger,
) -> pd.DataFrame:
    """Select branch-stratified Step 04B inputs from the Step 04A manifest."""
    missing = {"branch", "track_id", "output_path"} - set(manifest.columns)
    if missing:
        raise ValueError(f"input manifest missing required columns: {sorted(missing)}")

    work = manifest[manifest["branch"].isin(BRANCHES)].copy()
    work = work.sort_values(["branch", "track_id", "output_path"]).reset_index(drop=True)

    if run_label == "full":
        return work

    if limit_files_per_branch is not None and limit_files_per_branch <= 0:
        raise ValueError("--limit-files-per-branch must be positive when provided")

    default_n = 50 if run_label == "sample" else 100
    n_take = limit_files_per_branch if limit_files_per_branch is not None else default_n
    parts: list[pd.DataFrame] = []
    for branch in BRANCHES:
        pool = work[work["branch"] == branch]
        if branch == "regional_mrar":
            # M.rar always runs all three quadrant file-cell outputs.
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


def validate_full_counts(work: pd.DataFrame) -> None:
    observed = work["branch"].value_counts().to_dict()
    bad = []
    for branch, expected in EXPECTED_FULL_INPUTS.items():
        got = int(observed.get(branch, 0))
        if got != expected:
            bad.append(f"{branch}: expected {expected}, got {got}")
    if bad:
        raise ValueError("full-mode Step 04A manifest row-count drift: " + "; ".join(bad))


# ---------------------------------------------------------------------------
# Branch merge
# ---------------------------------------------------------------------------
def normalize_bool_series(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s.fillna(False)
    return s.fillna(False).astype(bool)


def is_mrar_source_type(series: pd.Series) -> pd.Series:
    values = series.fillna("").astype(str)
    return values.isin(MRAR_SOURCE_TYPE_VALUES) | values.str.contains("mrar", case=False, regex=False)


def load_branch_rows(rows: pd.DataFrame, reason_col: str | None, logger: logging.Logger) -> pd.DataFrame:
    """Read all Step 04A per-file-cell parquets for one branch."""
    frames: list[pd.DataFrame] = []
    n_files = len(rows)
    for i, (_, manifest_row) in enumerate(rows.iterrows(), start=1):
        rel = str(manifest_row["output_path"])
        path = repo_path(rel)
        if not path.exists():
            raise FileNotFoundError(f"per-file-cell parquet not found: {path}")

        schema_cols = read_parquet_schema(path)
        missing = [c for c in REQUIRED_FILE_CELL_COLUMNS if c not in schema_cols]
        if missing:
            raise ValueError(f"{path} missing required Step 04A columns: {missing}")

        cols = list(REQUIRED_FILE_CELL_COLUMNS)
        if reason_col and reason_col in schema_cols:
            cols.append(reason_col)
        df = pd.read_parquet(path, columns=cols)
        frames.append(df)

        if i == 1 or i % 250 == 0 or i == n_files:
            logger.info("  loaded %d/%d file-cell parquets", i, n_files)

    if not frames:
        return pd.DataFrame(columns=REQUIRED_FILE_CELL_COLUMNS)

    out = pd.concat(frames, ignore_index=True, copy=False)
    return out


def compute_lat_band(lat_center: pd.Series) -> pd.Series:
    """10-degree latitude band lower edge used for Hive partitioning.

    The contract names bands {-90, -80, ..., 80}. If a rare exact-pole
    cell produces floor(...)=90, clamp it into the 80–90 band.
    """
    band = (np.floor(lat_center.astype(float) / 10.0) * 10.0).astype(np.int64)
    return pd.Series(np.clip(band, -90, 80), index=lat_center.index, dtype="int64")


def sorted_reason_join(values: pd.Series) -> str:
    toks = sorted({str(v) for v in values.dropna().tolist() if str(v)})
    return ";".join(toks)


def merge_branch(
    branch: str,
    branch_manifest: pd.DataFrame,
    *,
    reason_col: str | None,
    logger: logging.Logger,
) -> tuple[pd.DataFrame, dict]:
    """Merge one source branch from per-file-cells to global cells."""
    start = datetime.now()
    logger.info("Merging branch %s from %d per-file-cell parquets", branch, len(branch_manifest))

    raw = load_branch_rows(branch_manifest, reason_col, logger)
    n_input_rows = len(raw)
    if raw.empty:
        empty = pd.DataFrame(columns=OUTPUT_COLUMNS_WITH_PARTITION)
        summary = {
            "branch": branch,
            "n_cells_total": 0,
            "n_track_cells_total": 0,
            "n_tracks_total": 0,
            "n_points_pass_grand_total": 0,
            "n_unique_triples_grand_total": 0,
            "n_lat_bands_occupied": 0,
            "n_manual_review_cells": 0,
            "manual_review_cell_share": np.nan,
            "runtime_seconds": (datetime.now() - start).total_seconds(),
            "merge_version": MERGE_VERSION,
        }
        return empty, summary

    # Contract checks on Step 04A input rows.
    if raw["n_unique_triples"].isna().any():
        raise ValueError(f"{branch}: n_unique_triples has null values")
    if (pd.to_numeric(raw["n_points_pass"], errors="coerce") <= 0).any():
        raise ValueError(f"{branch}: found non-positive n_points_pass in Step 04A rows")
    branch_values = sorted(raw["branch"].astype(str).unique().tolist())
    if branch_values != [branch]:
        raise ValueError(f"{branch}: cross-branch contamination in input rows: {branch_values}")

    raw["manual_review_flag"] = normalize_bool_series(raw["manual_review_flag"])
    raw["_n_source_ncei_nc"] = (raw["source_type"].astype(str) == "ncei_nc").astype("int64")
    raw["_n_source_ncei_xyz"] = (raw["source_type"].astype(str) == "ncei_xyz").astype("int64")
    raw["_n_source_mrar_zhoushuai"] = is_mrar_source_type(raw["source_type"]).astype("int64")
    raw["_n_completeness_nc_xyz_intersect"] = (raw["source_completeness"].astype(str) == "nc_xyz_intersect").astype("int64")
    raw["_n_completeness_xyz_only"] = (raw["source_completeness"].astype(str) == "xyz_only").astype("int64")
    raw["_n_completeness_nc_only"] = (raw["source_completeness"].astype(str) == "nc_only").astype("int64")
    raw["_n_instrument_singlebeam"] = (raw["instrument_class_pred"].astype(str) == "singlebeam").astype("int64")
    raw["_n_instrument_multibeam"] = (raw["instrument_class_pred"].astype(str) == "multibeam").astype("int64")
    raw["_manual_review_flag_i"] = raw["manual_review_flag"].astype("int64")
    raw["_manual_review_unique_triples"] = np.where(
        raw["manual_review_flag"].to_numpy(dtype=bool),
        raw["n_unique_triples"].to_numpy(dtype=np.int64),
        0,
    ).astype(np.int64)

    g = raw.groupby("cell_id", sort=False)
    agg = g.agg(
        branch=("branch", "first"),
        lon_bin=("lon_bin", "first"),
        lat_bin=("lat_bin", "first"),
        lon_center=("lon_center", "first"),
        lat_center=("lat_center", "first"),
        n_track_cells=("median_depth_m", "size"),
        n_tracks=("track_id", "nunique"),
        n_points_pass_total=("n_points_pass", "sum"),
        n_unique_triples_total=("n_unique_triples", "sum"),
        median_depth_m=("median_depth_m", "median"),
        mean_of_track_medians=("median_depth_m", "mean"),
        std_of_track_medians=("median_depth_m", lambda s: s.std(ddof=1) if len(s) > 1 else np.nan),
        min_track_median=("median_depth_m", "min"),
        max_track_median=("median_depth_m", "max"),
        n_source_ncei_nc=("_n_source_ncei_nc", "sum"),
        n_source_ncei_xyz=("_n_source_ncei_xyz", "sum"),
        n_source_mrar_zhoushuai=("_n_source_mrar_zhoushuai", "sum"),
        n_completeness_nc_xyz_intersect=("_n_completeness_nc_xyz_intersect", "sum"),
        n_completeness_xyz_only=("_n_completeness_xyz_only", "sum"),
        n_completeness_nc_only=("_n_completeness_nc_only", "sum"),
        n_instrument_singlebeam=("_n_instrument_singlebeam", "sum"),
        n_instrument_multibeam=("_n_instrument_multibeam", "sum"),
        manual_review_track_cell_count=("_manual_review_flag_i", "sum"),
        manual_review_unique_triples=("_manual_review_unique_triples", "sum"),
    )

    q = g["median_depth_m"].quantile([0.25, 0.75]).unstack(level=-1)
    q.columns = ["q25", "q75"]
    agg["iqr_of_track_medians"] = q["q75"] - q["q25"]

    out = agg.reset_index()
    out["duplicate_ratio_cell"] = np.where(
        out["n_points_pass_total"] > 0,
        1.0 - out["n_unique_triples_total"] / out["n_points_pass_total"],
        np.nan,
    )
    out["range_track_median"] = out["max_track_median"] - out["min_track_median"]
    out["manual_review_any"] = out["manual_review_track_cell_count"] > 0
    out["manual_review_unique_triples_share"] = np.where(
        out["n_unique_triples_total"] > 0,
        out["manual_review_unique_triples"] / out["n_unique_triples_total"],
        np.nan,
    )

    if reason_col and reason_col in raw.columns:
        raw["_review_reason"] = np.where(
            raw["manual_review_flag"].to_numpy(dtype=bool),
            raw[reason_col].fillna("").astype(str),
            "",
        )
    else:
        raw["_review_reason"] = np.where(
            raw["manual_review_flag"].to_numpy(dtype=bool),
            FALLBACK_REVIEW_REASON,
            "",
        )
    reason_by_cell = raw.loc[raw["manual_review_flag"], ["cell_id", "_review_reason"]]
    if reason_by_cell.empty:
        out["manual_review_reasons"] = ""
    else:
        joined = reason_by_cell.groupby("cell_id")["_review_reason"].agg(sorted_reason_join)
        out = out.merge(joined.rename("manual_review_reasons"), on="cell_id", how="left")
        out["manual_review_reasons"] = out["manual_review_reasons"].fillna("")

    out["lat_band_10deg"] = compute_lat_band(out["lat_center"])

    # Stable user-facing ordering and dtypes.
    int_cols = [
        "lon_bin",
        "lat_bin",
        "n_track_cells",
        "n_tracks",
        "n_points_pass_total",
        "n_unique_triples_total",
        "n_source_ncei_nc",
        "n_source_ncei_xyz",
        "n_source_mrar_zhoushuai",
        "n_completeness_nc_xyz_intersect",
        "n_completeness_xyz_only",
        "n_completeness_nc_only",
        "n_instrument_singlebeam",
        "n_instrument_multibeam",
        "manual_review_track_cell_count",
        "manual_review_unique_triples",
        "lat_band_10deg",
    ]
    for col in int_cols:
        out[col] = pd.to_numeric(out[col], errors="raise").astype("int64")
    out["manual_review_any"] = out["manual_review_any"].astype(bool)
    out["manual_review_reasons"] = out["manual_review_reasons"].astype(str)
    out = out[OUTPUT_COLUMNS_WITH_PARTITION].sort_values("cell_id").reset_index(drop=True)

    # Self-reporting sanity checks.
    nc_only_cells = int((out["n_completeness_nc_only"] > 0).sum())
    if nc_only_cells:
        logger.warning("%s: n_completeness_nc_only present in %d merged cells", branch, nc_only_cells)
    else:
        logger.info("%s: n_completeness_nc_only assertion OK (0 cells)", branch)

    # Find one multi-contributor cell with differing per-file medians for
    # a median-of-medians sanity spot-check. The full `groupby(...).filter`
    # path materializes every matching group and is wasteful on the M.rar
    # branch (9M+ rows). Restrict the search to the small multi-contributor
    # subset (typically <200 cells even on the 9M-cell M.rar output) and
    # short-circuit on the first qualifying cell.
    spot_cell: str | None = None
    multi_mask = out["n_track_cells"] > 1
    if multi_mask.any():
        multi_cells = set(out.loc[multi_mask, "cell_id"].tolist())
        subset = raw[raw["cell_id"].isin(multi_cells)]
        nunique = subset.groupby("cell_id")["median_depth_m"].nunique(dropna=True)
        differ_cells = nunique[nunique > 1].index.tolist()
        if differ_cells:
            spot_cell = str(differ_cells[0])

    if spot_cell is not None:
        medians = raw.loc[raw["cell_id"] == spot_cell, "median_depth_m"].to_numpy(dtype=float)
        expected = float(np.median(medians))
        observed = float(out.loc[out["cell_id"] == spot_cell, "median_depth_m"].iloc[0])
        if not np.isclose(expected, observed, rtol=0.0, atol=0.0):
            raise ValueError(
                f"{branch}: median-of-medians sanity failed for {spot_cell}: "
                f"expected {expected}, observed {observed}"
            )
        logger.info(
            "%s: median-of-medians sanity OK on %s (n_track_cells=%d, median=%.3f)",
            branch,
            spot_cell,
            len(medians),
            observed,
        )
    else:
        logger.info("%s: no multi-track differing-median cell available for spot-check", branch)

    high_dup_cells = int((out["duplicate_ratio_cell"] > 0.5).sum())
    if branch == "multibeam_ncei":
        if high_dup_cells:
            logger.info("%s: duplicate_ratio_cell>0.5 sanity OK (%d cells)", branch, high_dup_cells)
        else:
            logger.warning("%s: no duplicate_ratio_cell>0.5 cells found in this run", branch)

    logger.info(
        "%s: merged %d per-file-cell rows -> %d cells; manual_review_cells=%d; runtime=%.1fs",
        branch,
        n_input_rows,
        len(out),
        int(out["manual_review_any"].sum()),
        (datetime.now() - start).total_seconds(),
    )

    elapsed = (datetime.now() - start).total_seconds()
    summary = {
        "branch": branch,
        "n_cells_total": int(len(out)),
        "n_track_cells_total": int(out["n_track_cells"].sum()),
        "n_tracks_total": int(raw["track_id"].nunique()),
        "n_points_pass_grand_total": int(out["n_points_pass_total"].sum()),
        "n_unique_triples_grand_total": int(out["n_unique_triples_total"].sum()),
        "n_lat_bands_occupied": int(out["lat_band_10deg"].nunique()),
        "n_manual_review_cells": int(out["manual_review_any"].sum()),
        "manual_review_cell_share": float(out["manual_review_any"].mean()) if len(out) else np.nan,
        "runtime_seconds": float(elapsed),
        "merge_version": MERGE_VERSION,
    }
    return out, summary


# ---------------------------------------------------------------------------
# Output writing / reporting
# ---------------------------------------------------------------------------
def write_partitioned_cells(df: pd.DataFrame, target_dir: Path, *, overwrite: bool) -> None:
    if target_dir.exists():
        if not overwrite:
            raise FileExistsError(f"output dataset exists; pass --overwrite to replace: {target_dir}")
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    table = pa.Table.from_pandas(df, preserve_index=False)
    # Hive-flavored partitioning so consumers can read back the dataset with
    # the standard ``ds.dataset(path, partitioning="hive")`` call and recover
    # both partition keys (`branch`, `lat_band_10deg`) as columns. With the
    # default directory-partitioning flavor those keys would only be
    # reconstructed if the consumer passed an explicit partition schema, which
    # silently strips them under the more common hive read path.
    ds.write_dataset(
        table,
        base_dir=str(target_dir),
        format="parquet",
        partitioning=["branch", "lat_band_10deg"],
        partitioning_flavor="hive",
        existing_data_behavior="delete_matching",
        basename_template="part-{i}.parquet",
    )


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
        vals = []
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


def percentile_row(branch: str, s: pd.Series, name: str) -> dict:
    q = s.quantile([0.0, 0.25, 0.5, 0.75, 0.9, 0.99, 1.0]) if len(s) else pd.Series([np.nan] * 7)
    return {
        "branch": branch,
        "metric": name,
        "p0": float(q.iloc[0]),
        "p25": float(q.iloc[1]),
        "p50": float(q.iloc[2]),
        "p75": float(q.iloc[3]),
        "p90": float(q.iloc[4]),
        "p99": float(q.iloc[5]),
        "max": float(q.iloc[6]),
    }


def make_report(
    *,
    run_label: str,
    manifest_df: pd.DataFrame,
    branch_outputs: dict[str, pd.DataFrame],
    input_counts: dict[str, int],
    output_dirs: dict[str, Path],
    reason_col: str | None,
    elapsed_s: float,
) -> str:
    lines: list[str] = []
    lines.append("# NCEI Step 04B — Branch-specific 1-arcmin Cell Merge Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Run label: `{run_label}`")
    lines.append(f"Merge version: `{MERGE_VERSION}`")
    lines.append("Cell size: 1 arc-minute (1/60°)")
    lines.append(f"Elapsed: {elapsed_s:.1f}s")
    lines.append("")
    lines.append("> Depth merge rule: `median_depth_m = median(per_file_cell.median_depth_m)`. ")
    lines.append("> This is a median of per-track/per-file cell medians, not a pooled-point median and not weighted by `n_points_pass`.")
    lines.append("")
    lines.append("> Duplicate convention: `n_unique_triples_total` is the sum of Step 04A per-file-cell `n_unique_triples`. ")
    lines.append("> This intentionally over-counts exact triples duplicated across different files/tracks; per-file-cell exact-float dedup remains the authoritative production dedup level for now.")
    lines.append("")

    lines.append("## 1. Per-branch input and output totals")
    lines.append("")
    totals = manifest_df.copy()
    totals.insert(1, "input_file_cells", totals["branch"].map(input_counts).astype("int64"))
    lines.extend(markdown_table(totals))

    lines.append("## 2. n_track_cells percentiles per merged cell")
    lines.append("")
    rows = []
    for branch, df in branch_outputs.items():
        rows.append(percentile_row(branch, df["n_track_cells"], "n_track_cells"))
    lines.extend(markdown_table(pd.DataFrame(rows)))

    lines.append("## 3. Depth distribution (`median_depth_m`) per branch")
    lines.append("")
    rows = []
    for branch, df in branch_outputs.items():
        rows.append(percentile_row(branch, df["median_depth_m"], "median_depth_m"))
    lines.extend(markdown_table(pd.DataFrame(rows)))

    lines.append("## 4. Top cells by n_track_cells (multi-source hotspots)")
    lines.append("")
    for branch, df in branch_outputs.items():
        lines.append(f"### {branch}")
        lines.append("")
        cols = ["cell_id", "lon_center", "lat_center", "n_track_cells", "n_tracks", "median_depth_m", "n_points_pass_total", "manual_review_any"]
        top = df.sort_values(["n_track_cells", "n_points_pass_total"], ascending=False)[cols].head(10)
        lines.extend(markdown_table(top))

    lines.append("## 5. Top cells by duplicate_ratio_cell")
    lines.append("")
    for branch, df in branch_outputs.items():
        lines.append(f"### {branch}")
        lines.append("")
        cols = ["cell_id", "lon_center", "lat_center", "duplicate_ratio_cell", "n_track_cells", "n_points_pass_total", "n_unique_triples_total"]
        top = df.sort_values("duplicate_ratio_cell", ascending=False)[cols].head(10)
        lines.extend(markdown_table(top))

    lines.append("## 6. Manual-review summary")
    lines.append("")
    lines.append(
        "Reason source: "
        + (f"per-file-cell column `{reason_col}`" if reason_col else f"fallback constant `{FALLBACK_REVIEW_REASON}`")
    )
    lines.append("")
    rows = []
    for branch, df in branch_outputs.items():
        rows.append(
            {
                "branch": branch,
                "cells": len(df),
                "manual_review_cells": int(df["manual_review_any"].sum()),
                "manual_review_cell_share": float(df["manual_review_any"].mean()) if len(df) else np.nan,
                "manual_review_unique_triples": int(df["manual_review_unique_triples"].sum()),
                "manual_review_unique_triples_share_of_branch": (
                    float(df["manual_review_unique_triples"].sum() / df["n_unique_triples_total"].sum())
                    if df["n_unique_triples_total"].sum() else np.nan
                ),
            }
        )
    lines.extend(markdown_table(pd.DataFrame(rows)))

    lines.append("## 7. Source / completeness / instrument row-count totals")
    lines.append("")
    count_cols = [
        "n_source_ncei_nc",
        "n_source_ncei_xyz",
        "n_source_mrar_zhoushuai",
        "n_completeness_nc_xyz_intersect",
        "n_completeness_xyz_only",
        "n_completeness_nc_only",
        "n_instrument_singlebeam",
        "n_instrument_multibeam",
    ]
    rows = []
    for branch, df in branch_outputs.items():
        row = {"branch": branch}
        for col in count_cols:
            row[col] = int(df[col].sum())
        rows.append(row)
    lines.extend(markdown_table(pd.DataFrame(rows)))

    lines.append("## 8. Output paths")
    lines.append("")
    path_rows = [
        {"kind": "top-level manifest", "path": str((MANIFEST_DIR / f"cells_1min_manifest{suffix_for_run(run_label)}.parquet").relative_to(REPO_ROOT))},
        {"kind": "report (this file)", "path": str((DOCS_DIR / f"step04b_cells_1min_merge_report{suffix_for_run(run_label)}.md").relative_to(REPO_ROOT))},
    ]
    for branch, out_dir in output_dirs.items():
        path_rows.append({"kind": f"{branch} cells dataset", "path": str(out_dir.relative_to(REPO_ROOT))})
    lines.extend(markdown_table(pd.DataFrame(path_rows)))

    lines.append("## 9. Guardrails confirmed")
    lines.append("")
    lines.append("- No cross-branch merge: each branch was read, grouped, and written independently; `branch` remains a partition key.")
    lines.append("- No A/B/C quality tiers were defined.")
    lines.append("- `manual_review_any` is informational only; no cell was dropped because of it.")
    lines.append("- `median_depth_m` is the median of Step 04A per-file-cell medians.")
    lines.append("- `n_unique_triples_total` is present/non-null on all loaded Step 04A rows.")
    lines.append("")
    lines.append("## 10. References")
    lines.append("")
    lines.append("- Step 04A implementation: `ncei/code/07_aggregate_file_cells_1min.py` (`AGGREGATION_VERSION`).")
    lines.append("- Step 04A run report: `ncei/docs/step04a_file_cells_1min_report.md`.")
    lines.append("- Step 04A/04B design audit: `ncei/docs/step04_aggregation_design_audit.md`.")
    lines.append("- Spec §13 (NCEI Step 04A per-file 1-arcmin cell aggregation): `.trellis/spec/backend/pipeline-design-decisions.md`.")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Step 04B — Merge NCEI Step 04A per-file 1-arcmin cells into "
            "branch-specific global cells. Run from repo root."
        )
    )
    parser.add_argument("--run-label", choices=VALID_RUN_LABELS, default="sample")
    parser.add_argument(
        "--limit-files-per-branch",
        type=int,
        default=None,
        help="Limit non-M.rar branches to N per-file-cell parquets in sample/test100 mode "
        "(defaults: sample=50, test100=100; ignored for full; M.rar always all 3).",
    )
    parser.add_argument("--confirm-full", action="store_true", help="Required when --run-label=full")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing Step 04B outputs")
    parser.add_argument(
        "--input-manifest",
        type=Path,
        default=INPUT_MANIFEST,
        help="Path to ncei/manifests/file_cells_1min_manifest.parquet",
    )
    args = parser.parse_args()

    paths = get_output_paths(args.run_label)
    logger = setup_logging(paths["log"])
    t0 = datetime.now()

    logger.info("=" * 60)
    logger.info("08_merge_branch_cells_1min.py START")
    logger.info("Args: %s", vars(args))
    logger.info("Merge version: %s", MERGE_VERSION)

    if args.run_label == "full" and not args.confirm_full:
        logger.error("ABORTED: --run-label=full requires --confirm-full")
        return 2
    if args.run_label == "full" and args.limit_files_per_branch is not None:
        logger.warning("--limit-files-per-branch is ignored in full mode")

    if not args.input_manifest.exists():
        logger.error("ABORTED: input manifest not found: %s", args.input_manifest)
        return 2

    top_outputs = [paths["manifest_pq"], paths["report_md"]]
    if not args.overwrite:
        existing = [p for p in top_outputs if p.exists()]
        existing += [cells_output_dir(branch, args.run_label) for branch in BRANCHES if cells_output_dir(branch, args.run_label).exists()]
        if existing:
            logger.error("ABORTED: outputs exist; use --overwrite. Existing: %s", existing)
            return 2

    try:
        manifest = pd.read_parquet(args.input_manifest)
        logger.info("Loaded Step 04A manifest: %d rows x %d cols", len(manifest), len(manifest.columns))

        work = select_manifest_rows(
            manifest,
            run_label=args.run_label,
            limit_files_per_branch=args.limit_files_per_branch,
            logger=logger,
        )
        if args.run_label == "full":
            validate_full_counts(work)
        input_counts = {branch: int((work["branch"] == branch).sum()) for branch in BRANCHES}
        logger.info("Input file counts by branch: %s", input_counts)

        inspect_paths = [repo_path(str(p)) for p in work["output_path"].head(30).tolist()]
        reason_col = find_manual_review_reason_column(inspect_paths, logger)

        branch_outputs: dict[str, pd.DataFrame] = {}
        manifest_rows: list[dict] = []
        output_dirs: dict[str, Path] = {}

        for branch in BRANCHES:
            branch_work = work[work["branch"] == branch].reset_index(drop=True)
            out_dir = cells_output_dir(branch, args.run_label)
            output_dirs[branch] = out_dir
            if branch_work.empty:
                logger.warning("No inputs selected for branch %s", branch)
                cells_df = pd.DataFrame(columns=OUTPUT_COLUMNS_WITH_PARTITION)
                summary = {
                    "branch": branch,
                    "n_cells_total": 0,
                    "n_track_cells_total": 0,
                    "n_tracks_total": 0,
                    "n_points_pass_grand_total": 0,
                    "n_unique_triples_grand_total": 0,
                    "n_lat_bands_occupied": 0,
                    "n_manual_review_cells": 0,
                    "manual_review_cell_share": np.nan,
                    "runtime_seconds": 0.0,
                    "merge_version": MERGE_VERSION,
                }
            else:
                cells_df, summary = merge_branch(
                    branch,
                    branch_work,
                    reason_col=reason_col,
                    logger=logger,
                )

            branch_outputs[branch] = cells_df
            manifest_rows.append(summary)
            write_partitioned_cells(cells_df, out_dir, overwrite=args.overwrite)
            logger.info("Wrote branch dataset: %s (%d cells)", out_dir, len(cells_df))

        manifest_df = pd.DataFrame(manifest_rows)
        for col in MANIFEST_COLUMNS:
            if col not in manifest_df.columns:
                manifest_df[col] = pd.NA
        manifest_df = manifest_df[MANIFEST_COLUMNS].sort_values("branch").reset_index(drop=True)

        elapsed_s = (datetime.now() - t0).total_seconds()
        report_text = make_report(
            run_label=args.run_label,
            manifest_df=manifest_df,
            branch_outputs=branch_outputs,
            input_counts=input_counts,
            output_dirs=output_dirs,
            reason_col=reason_col,
            elapsed_s=elapsed_s,
        )

        atomic_write_parquet(manifest_df, paths["manifest_pq"])
        atomic_write_text(report_text, paths["report_md"])

        # Final self-report logs.
        logger.info("Wrote %s (%d rows)", paths["manifest_pq"], len(manifest_df))
        logger.info("Wrote %s", paths["report_md"])
        logger.info("Manual-review reason source: %s", reason_col or FALLBACK_REVIEW_REASON)
        logger.info("M.rar source_type values counted as n_source_mrar_zhoushuai include: %s", sorted(MRAR_SOURCE_TYPE_VALUES))
        logger.info("Elapsed: %.1fs", elapsed_s)
        logger.info("08_merge_branch_cells_1min.py DONE")

        print(f"Inputs by branch: {input_counts}")
        print("Cells by branch:", {b: int(len(df)) for b, df in branch_outputs.items()})
        print(f"Manifest: {paths['manifest_pq']}")
        print(f"Report:   {paths['report_md']}")
        return 0

    except Exception as exc:  # noqa: BLE001 - pipeline stage top-level guard
        logger.exception("ABORTED with error: %r", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
