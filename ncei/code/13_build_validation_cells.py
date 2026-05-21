#!/usr/bin/env python3
"""
13_build_validation_cells.py

Step 07B — Build NCEI validation-cell products.

This stage is a product builder on top of immutable inputs:

* NCEI Step 04B branch cells under ncei/derived/{singlebeam,multibeam,regional_mrar}/cells_1min/
* NCEI Step 06B quality sidecar ncei/derived/quality_flags_1min/cell_quality_flags_1min.parquet
* JAMSTEC legacy primary validation cells under jamstec/multibeam/derived/validation_cells_1min/

It does not define new quality rules, does not rescale validation weights,
does not mutate any predecessor output, and does not read external grids.

Run from repo root (/mnt/data2/00-Data/ship):

    python ncei/code/13_build_validation_cells.py --run-label sample --overwrite
    python ncei/code/13_build_validation_cells.py --run-label test100 --overwrite
    python ncei/code/13_build_validation_cells.py --run-label full --confirm-full --overwrite
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent          # ncei/
REPO_ROOT = ROOT_DIR.parent           # ship/

DERIVED_DIR = ROOT_DIR / "derived"
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"
JAMSTEC_ROOT = REPO_ROOT / "jamstec" / "multibeam"

VALIDATION_PRODUCT_VERSION = "ncei_validation_cells_v0.1.0"
VALID_RUN_LABELS = ("sample", "test100", "full")

QUALITY_FLAGS_PATH = DERIVED_DIR / "quality_flags_1min" / "cell_quality_flags_1min.parquet"
BRANCH_CELL_DIRS = {
    "singlebeam": DERIVED_DIR / "singlebeam" / "cells_1min",
    "multibeam_ncei": DERIVED_DIR / "multibeam" / "cells_1min",
    "regional_mrar": DERIVED_DIR / "regional_mrar" / "cells_1min",
}
JAMSTEC_CELLS_PATH = JAMSTEC_ROOT / "derived" / "cells_1min" / "cells.parquet"
JAMSTEC_PRIMARY_PATH = (
    JAMSTEC_ROOT
    / "derived"
    / "validation_cells_1min"
    / "primary_ship_validation_cells_1min.parquet"
)

EXPECTED_FULL_COUNTS = {
    "strict_primary": (2_398_774, 12_000),
    "expanded_primary": (2_732_689, 14_000),
    "supplementary_singlebeam": (12_277_633, 61_000),
    "regional_mrar_experiment": (9_019_383, 0),
    "validation_cell_catalog": (24_029_705, 120_000),
}

SAMPLE_TARGETS = {
    "sample": {"jamstec": 5_000, "multibeam_ncei": 5_000, "singlebeam": 5_000, "regional_mrar": 5_000},
    "test100": {"jamstec": 100_000, "multibeam_ncei": 100_000, "singlebeam": 100_000, "regional_mrar": 100_000},
}

NCEI_BRANCH_TO_PROVIDER = {
    "singlebeam": "ncei_singlebeam",
    "multibeam_ncei": "ncei_multibeam",
    "regional_mrar": "mrar",
}
JAMSTEC_TIER_MAP = {
    "A_tier": "high_confidence",
    "B_tier": "medium_confidence",
    "C_tier": "low_confidence",
}

NCEI_CELL_COLUMNS = [
    "branch",
    "cell_id",
    "lon_bin",
    "lat_bin",
    "lon_center",
    "lat_center",
    "median_depth_m",
    "n_track_cells",
    "n_tracks",
    "n_points_pass_total",
    "n_unique_triples_total",
    "duplicate_ratio_cell",
    "mean_of_track_medians",
    "std_of_track_medians",
    "iqr_of_track_medians",
    "min_track_median",
    "max_track_median",
    "range_track_median",
    "manual_review_any",
    "lat_band_10deg",
]
NCEI_REQUIRED_CELL_COLUMNS = [
    "branch",
    "cell_id",
    "lon_bin",
    "lat_bin",
    "lon_center",
    "lat_center",
    "median_depth_m",
    "n_track_cells",
    "n_points_pass_total",
    "n_unique_triples_total",
    "duplicate_ratio_cell",
]
NCEI_FLAG_COLUMNS = [
    "branch",
    "cell_id",
    "lon_bin",
    "lat_bin",
    "quality_tier",
    "evidence_class",
    "validation_weight",
    "branch_role",
    "use_for_primary_validation",
    "use_for_supplementary_validation",
    "use_for_regional_experiment",
    "sensitivity_only_flag",
    "exclude_from_primary",
    "matched_rule_id",
    "rule_version",
    "n_unique_triples_total",
    "n_points_pass_total",
    "duplicate_ratio_cell",
    "n_track_cells",
    "manual_review_any",
    "low_evidence_flag",
    "overlap_evidence_class",
    "n_cross_branch_overlap",
    "lat_band_10deg",
    "depth_bin",
    "auv_sentry_flag",
    "source_risk_class",
]
NCEI_REQUIRED_FLAG_COLUMNS = [
    "branch",
    "cell_id",
    "lon_bin",
    "lat_bin",
    "quality_tier",
    "evidence_class",
    "validation_weight",
    "branch_role",
    "use_for_primary_validation",
    "use_for_supplementary_validation",
    "use_for_regional_experiment",
    "sensitivity_only_flag",
    "rule_version",
    "auv_sentry_flag",
    "source_risk_class",
]

CORE_COLUMNS = [
    "cell_id",
    "lon_bin",
    "lat_bin",
    "lon_center",
    "lat_center",
    "lat_band_10deg",
    "source_provider",
    "branch",
    "branch_role",
    "representative_depth_m",
    "validation_weight",
    "quality_tier",
    "evidence_class",
    "auv_sentry_flag",
    "source_risk_class",
    "n_unique_triples_total",
    "n_points_pass_total",
    "n_track_cells",
    "duplicate_ratio_cell",
    "n_tracks",
    "manual_review_any",
    "low_evidence_flag",
    "n_cross_branch_overlap",
    "depth_bin",
    "sensitivity_only_flag",
    "precedence_resolution",
    "final_primary_source",
    "source_dataset",
    "dominant_file_id",
    "enforced_rules_version",
    "merge_version",
    "validation_product_version",
]
EXPANDED_EXTRA_COLUMNS = ["expanded_fill"]
CATALOG_EXTRA_COLUMNS = ["product_label", "product_membership"]

# Step 07A's catalog estimate includes one extra membership row for NCEI
# singlebeam cells that survive into expanded_primary_ship_cells. Product 2 as
# a whole is not duplicated in the catalog: only the sb fill membership is
# materialized so the catalog matches the locked Step 07A headline count while
# avoiding duplicate JAMSTEC/NCEI-mb primary rows.
INCLUDE_EXPANDED_SB_MEMBERSHIP_IN_CATALOG = True


# ---------------------------------------------------------------------------
# Paths / logging / writes
# ---------------------------------------------------------------------------
def suffix_for_run(run_label: str) -> str:
    return "" if run_label == "full" else f"_{run_label}"


def validation_root(run_label: str) -> Path:
    return DERIVED_DIR / f"validation_cells_1min{suffix_for_run(run_label)}"


def output_paths(run_label: str) -> dict[str, Path]:
    suffix = suffix_for_run(run_label)
    root = validation_root(run_label)
    return {
        "root": root,
        "strict_primary": root / "strict_primary_multibeam_cells.parquet",
        "expanded_primary": root / "expanded_primary_ship_cells.parquet",
        "supplementary_singlebeam": root / "supplementary_singlebeam_cells.parquet",
        "regional_mrar_experiment": root / "regional_mrar_experiment_cells.parquet",
        "validation_cell_catalog": root / "validation_cell_catalog.parquet",
        "report": DOCS_DIR / f"step07b_validation_cells_report{suffix}.md",
        "log": LOG_DIR / f"13_build_validation_cells{suffix}.log",
    }


def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ncei_build_validation_cells")
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


def existing_outputs(paths: dict[str, Path]) -> list[Path]:
    return [p for k, p in paths.items() if k not in {"root", "log"} and p.exists()]


def atomic_write_parquet(df: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    if tmp.exists():
        if tmp.is_dir():
            shutil.rmtree(tmp)
        else:
            tmp.unlink()
    df.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, target)


def atomic_write_text(text: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)


def write_hive_dataset(df: pd.DataFrame, target: Path, partition_cols: list[str], *, overwrite: bool) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f"{target.name}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    table = pa.Table.from_pandas(df, preserve_index=False)
    ds.write_dataset(
        table,
        str(tmp),
        format="parquet",
        partitioning=partition_cols,
        partitioning_flavor="hive",
        existing_data_behavior="error",
    )
    if target.exists():
        if not overwrite:
            shutil.rmtree(tmp)
            raise FileExistsError(f"output exists: {target}")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    os.replace(tmp, target)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------
def compute_lat_band(lat_center: pd.Series) -> pd.Series:
    values = np.floor(pd.to_numeric(lat_center, errors="coerce").astype(float) / 10.0) * 10.0
    values = values.clip(-90, 80)
    return values.astype("Int64")


def schema_names(path: Path) -> set[str]:
    if path.is_dir():
        return set(ds.dataset(str(path), format="parquet", partitioning="hive").schema.names)
    return set(pq.read_schema(path).names)


def read_parquet_dataset(path: Path, columns: list[str], required: list[str], filters=None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required input not found: {path}")
    names = schema_names(path)
    missing = [c for c in required if c not in names]
    if missing:
        raise ValueError(f"{path} missing required columns: {missing}")
    read_cols = [c for c in columns if c in names]
    if path.is_dir():
        dataset = ds.dataset(str(path), format="parquet", partitioning="hive")
        table = dataset.to_table(columns=read_cols, filter=filters)
        return table.to_pandas()
    if filters is not None:
        return pd.read_parquet(path, columns=read_cols, filters=filters)
    return pd.read_parquet(path, columns=read_cols)


def sample_by_lat_band(df: pd.DataFrame, label: str, run_label: str) -> pd.DataFrame:
    if run_label == "full" or df.empty:
        return df.reset_index(drop=True)
    target = SAMPLE_TARGETS[run_label].get(label, len(df))
    if len(df) <= target:
        return df.reset_index(drop=True)
    if "lat_band_10deg" not in df.columns:
        return df.sort_values("cell_id").head(target).reset_index(drop=True)
    per_band = max(1, int(np.ceil(target / max(1, df["lat_band_10deg"].nunique(dropna=False)))))
    sampled = (
        df.sort_values(["lat_band_10deg", "cell_id"])
        .groupby("lat_band_10deg", dropna=False, group_keys=False)
        .head(per_band)
        .head(target)
        .reset_index(drop=True)
    )
    if len(sampled) < target:
        rest = df.loc[~df["cell_id"].isin(sampled["cell_id"])].sort_values("cell_id")
        sampled = pd.concat([sampled, rest.head(target - len(sampled))], ignore_index=True)
    return sampled.reset_index(drop=True)


def ensure_columns(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = pd.NA
    return out[list(columns)]


def normalize_common_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    int_cols = [
        "lon_bin",
        "lat_bin",
        "lat_band_10deg",
        "n_unique_triples_total",
        "n_points_pass_total",
        "n_track_cells",
        "n_tracks",
        "n_cross_branch_overlap",
        "depth_bin",
    ]
    bool_cols = [
        "auv_sentry_flag",
        "manual_review_any",
        "low_evidence_flag",
        "sensitivity_only_flag",
        "expanded_fill",
    ]
    float_cols = ["lon_center", "lat_center", "representative_depth_m", "validation_weight", "duplicate_ratio_cell"]
    for col in int_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    for col in bool_cols:
        if col in out.columns:
            out[col] = out[col].where(out[col].notna(), False).astype(bool)
    for col in float_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    str_cols = [c for c in out.columns if c not in set(int_cols + bool_cols + float_cols)]
    for col in str_cols:
        out[col] = out[col].fillna("").astype(str)
    return out


# ---------------------------------------------------------------------------
# Input loaders and harmonization
# ---------------------------------------------------------------------------
def load_ncei_branch(branch: str, run_label: str, logger: logging.Logger) -> pd.DataFrame:
    flag_filter = (ds.field("branch") == branch)
    flags = read_parquet_dataset(QUALITY_FLAGS_PATH, NCEI_FLAG_COLUMNS, NCEI_REQUIRED_FLAG_COLUMNS, filters=flag_filter)
    cells = read_parquet_dataset(BRANCH_CELL_DIRS[branch], NCEI_CELL_COLUMNS, NCEI_REQUIRED_CELL_COLUMNS)
    if "lat_band_10deg" not in cells.columns:
        cells["lat_band_10deg"] = compute_lat_band(cells["lat_center"])
    if "lat_band_10deg" not in flags.columns:
        flags = flags.merge(cells[["branch", "cell_id", "lat_band_10deg"]], on=["branch", "cell_id"], how="left")

    key = ["branch", "cell_id", "lon_bin", "lat_bin"]
    if flags.duplicated(key).any():
        raise ValueError(f"Step 06B quality flags duplicate key rows for {branch}")
    if cells.duplicated(key).any():
        raise ValueError(f"Step 04B cells duplicate key rows for {branch}")

    merged = cells.merge(flags, on=key, how="inner", suffixes=("", "_flag"), validate="one_to_one")
    if len(merged) != len(flags) or len(merged) != len(cells):
        raise ValueError(
            f"{branch}: Step 04B/06B join was not 1:1 "
            f"(cells={len(cells):,}, flags={len(flags):,}, joined={len(merged):,})"
        )

    for col in ["lat_band_10deg", "n_unique_triples_total", "n_points_pass_total", "n_track_cells", "duplicate_ratio_cell", "manual_review_any"]:
        flag_col = f"{col}_flag"
        if flag_col in merged.columns:
            merged[col] = merged[col].where(merged[col].notna(), merged[flag_col])
            merged = merged.drop(columns=[flag_col])

    out = pd.DataFrame(index=merged.index)
    out["cell_id"] = merged["cell_id"].astype(str)
    out["lon_bin"] = pd.to_numeric(merged["lon_bin"], errors="coerce").astype("int64")
    out["lat_bin"] = pd.to_numeric(merged["lat_bin"], errors="coerce").astype("int64")
    out["lon_center"] = pd.to_numeric(merged["lon_center"], errors="coerce")
    out["lat_center"] = pd.to_numeric(merged["lat_center"], errors="coerce")
    out["lat_band_10deg"] = pd.to_numeric(merged["lat_band_10deg"], errors="coerce").astype("Int64")
    out["source_provider"] = NCEI_BRANCH_TO_PROVIDER[branch]
    out["branch"] = branch
    out["branch_role"] = merged["branch_role"].fillna("").astype(str)
    out["representative_depth_m"] = pd.to_numeric(merged["median_depth_m"], errors="coerce")
    out["validation_weight"] = pd.to_numeric(merged["validation_weight"], errors="coerce")
    out["quality_tier"] = merged["quality_tier"].fillna("").astype(str)
    out["evidence_class"] = merged["evidence_class"].fillna("").astype(str)
    out["auv_sentry_flag"] = merged["auv_sentry_flag"].fillna(False).astype(bool)
    out["source_risk_class"] = merged["source_risk_class"].fillna("").astype(str)
    out["n_unique_triples_total"] = pd.to_numeric(merged["n_unique_triples_total"], errors="coerce").astype("Int64")
    out["n_points_pass_total"] = pd.to_numeric(merged["n_points_pass_total"], errors="coerce").astype("Int64")
    out["n_track_cells"] = pd.to_numeric(merged["n_track_cells"], errors="coerce").astype("Int64")
    out["duplicate_ratio_cell"] = pd.to_numeric(merged["duplicate_ratio_cell"], errors="coerce")
    out["n_tracks"] = pd.to_numeric(merged.get("n_tracks", pd.Series(pd.NA, index=merged.index)), errors="coerce").astype("Int64")
    out["manual_review_any"] = merged.get("manual_review_any", pd.Series(False, index=merged.index)).fillna(False).astype(bool)
    out["low_evidence_flag"] = merged.get("low_evidence_flag", pd.Series(False, index=merged.index)).fillna(False).astype(bool)
    out["n_cross_branch_overlap"] = pd.to_numeric(merged.get("n_cross_branch_overlap", pd.Series(0, index=merged.index)), errors="coerce").fillna(0).astype("int64")
    out["depth_bin"] = pd.to_numeric(merged.get("depth_bin", pd.Series(pd.NA, index=merged.index)), errors="coerce").astype("Int64")
    out["sensitivity_only_flag"] = merged.get("sensitivity_only_flag", pd.Series(False, index=merged.index)).fillna(False).astype(bool)
    out["precedence_resolution"] = ""
    out["final_primary_source"] = ""
    out["source_dataset"] = "NCEI"
    out["dominant_file_id"] = ""
    out["enforced_rules_version"] = merged.get("rule_version", pd.Series("", index=merged.index)).fillna("").astype(str)
    out["merge_version"] = "ncei_cells_merge_v0.1.0"
    out["validation_product_version"] = VALIDATION_PRODUCT_VERSION

    for passthrough in [
        "use_for_primary_validation",
        "use_for_supplementary_validation",
        "use_for_regional_experiment",
        "exclude_from_primary",
        "matched_rule_id",
    ]:
        out[passthrough] = merged.get(passthrough, pd.Series(pd.NA, index=merged.index))

    out = sample_by_lat_band(out, branch, run_label)
    logger.info("%s: loaded %d validation-ready rows after %s sampling", branch, len(out), run_label)
    return out.reset_index(drop=True)


def load_jamstec_primary(run_label: str, logger: logging.Logger) -> pd.DataFrame:
    if not JAMSTEC_PRIMARY_PATH.exists():
        raise FileNotFoundError(f"JAMSTEC primary validation cells not found: {JAMSTEC_PRIMARY_PATH}")
    names = schema_names(JAMSTEC_PRIMARY_PATH)
    depth_col = "ship_depth_m" if "ship_depth_m" in names else "median_depth_file_balanced"
    required = ["cell_id", "lon_bin", "lat_bin", "lon_center", "lat_center", depth_col, "quality_tier", "validation_weight"]
    optional = [
        "use_for_primary_validation",
        "source_dataset",
        "dominant_file_id",
        "n_file_cells",
        "n_files",
        "n_points_total",
        "n_unique_triples_total",
        "duplicate_ratio_cell",
    ]
    cols = required + [c for c in optional if c in names]
    raw = pd.read_parquet(JAMSTEC_PRIMARY_PATH, columns=cols)
    if "use_for_primary_validation" in raw.columns:
        raw = raw[raw["use_for_primary_validation"].fillna(False).astype(bool)].copy()

    observed_tiers = set(raw["quality_tier"].dropna().astype(str).unique())
    unknown = observed_tiers - set(JAMSTEC_TIER_MAP)
    if unknown:
        raise ValueError(f"unexpected JAMSTEC quality_tier values: {sorted(unknown)}")

    out = pd.DataFrame(index=raw.index)
    out["cell_id"] = raw["cell_id"].astype(str)
    out["lon_bin"] = pd.to_numeric(raw["lon_bin"], errors="coerce").astype("int64")
    out["lat_bin"] = pd.to_numeric(raw["lat_bin"], errors="coerce").astype("int64")
    out["lon_center"] = pd.to_numeric(raw["lon_center"], errors="coerce")
    out["lat_center"] = pd.to_numeric(raw["lat_center"], errors="coerce")
    out["lat_band_10deg"] = compute_lat_band(out["lat_center"])
    out["source_provider"] = "jamstec"
    out["branch"] = "jamstec_mb"
    out["branch_role"] = "multibeam_primary"
    out["representative_depth_m"] = pd.to_numeric(raw[depth_col], errors="coerce")
    out["validation_weight"] = pd.to_numeric(raw["validation_weight"], errors="coerce")
    out["quality_tier"] = raw["quality_tier"].astype(str).map(JAMSTEC_TIER_MAP)
    out["evidence_class"] = "jamstec_legacy"
    out["auv_sentry_flag"] = False
    out["source_risk_class"] = ""
    out["n_unique_triples_total"] = pd.to_numeric(raw.get("n_unique_triples_total", pd.Series(pd.NA, index=raw.index)), errors="coerce").astype("Int64")
    out["n_points_pass_total"] = pd.to_numeric(raw.get("n_points_total", pd.Series(pd.NA, index=raw.index)), errors="coerce").astype("Int64")
    out["n_track_cells"] = pd.to_numeric(raw.get("n_file_cells", raw.get("n_files", pd.Series(pd.NA, index=raw.index))), errors="coerce").astype("Int64")
    out["duplicate_ratio_cell"] = pd.to_numeric(raw.get("duplicate_ratio_cell", pd.Series(np.nan, index=raw.index)), errors="coerce")
    out["n_tracks"] = pd.to_numeric(raw.get("n_files", pd.Series(pd.NA, index=raw.index)), errors="coerce").astype("Int64")
    out["manual_review_any"] = False
    out["low_evidence_flag"] = False
    out["n_cross_branch_overlap"] = 0
    out["depth_bin"] = pd.array([pd.NA] * len(raw), dtype="Int64")
    out["sensitivity_only_flag"] = False
    out["precedence_resolution"] = ""
    out["final_primary_source"] = ""
    out["source_dataset"] = raw.get("source_dataset", pd.Series("JAMSTEC", index=raw.index)).fillna("JAMSTEC").astype(str)
    out["dominant_file_id"] = raw.get("dominant_file_id", pd.Series("", index=raw.index)).fillna("").astype(str)
    out["enforced_rules_version"] = "jamstec_legacy"
    out["merge_version"] = "jamstec_legacy"
    out["validation_product_version"] = VALIDATION_PRODUCT_VERSION
    out["use_for_primary_validation"] = True
    out["use_for_supplementary_validation"] = False
    out["use_for_regional_experiment"] = False
    out["exclude_from_primary"] = False
    out["matched_rule_id"] = "jamstec_legacy"

    out = sample_by_lat_band(out, "jamstec", run_label)
    logger.info("jamstec: loaded %d primary rows after %s sampling", len(out), run_label)
    return out.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Product construction
# ---------------------------------------------------------------------------
def core_frame(df: pd.DataFrame, extra_cols: Sequence[str] = ()) -> pd.DataFrame:
    return normalize_common_dtypes(ensure_columns(df, [*CORE_COLUMNS, *extra_cols]))


def build_strict_primary(jamstec: pd.DataFrame, ncei_mb: pd.DataFrame) -> pd.DataFrame:
    mb_primary = ncei_mb[ncei_mb["use_for_primary_validation"].fillna(False).astype(bool)].copy()
    jam = jamstec.copy()
    overlap = set(jam["cell_id"]) & set(mb_primary["cell_id"])
    if overlap:
        raise AssertionError(
            "JAMSTEC × NCEI mb primary cell overlap is non-zero "
            f"({len(overlap):,}); precedence requires human re-confirmation"
        )
    out = pd.concat([jam, mb_primary], ignore_index=True, copy=False)
    out["final_primary_source"] = out["source_provider"]
    out["precedence_resolution"] = ""
    return core_frame(out)


def build_expanded_primary(strict_primary: pd.DataFrame, singlebeam: pd.DataFrame) -> pd.DataFrame:
    sb_primary = singlebeam[singlebeam["use_for_primary_validation"].fillna(False).astype(bool)].copy()
    strict_ids = set(strict_primary["cell_id"])
    strict_provider_by_cell = strict_primary.set_index("cell_id")["source_provider"].to_dict()

    # Label strict rows that win over NCEI singlebeam candidates.
    out_base = strict_primary.copy()
    sb_ids = set(sb_primary["cell_id"])
    strict_conflict = out_base["cell_id"].isin(sb_ids)
    out_base["precedence_resolution"] = ""
    out_base.loc[strict_conflict & out_base["source_provider"].eq("jamstec"), "precedence_resolution"] = "jamstec_over_sb"
    out_base.loc[strict_conflict & out_base["source_provider"].eq("ncei_multibeam"), "precedence_resolution"] = "ncei_mb_over_sb"
    out_base["expanded_fill"] = False
    out_base["final_primary_source"] = out_base["source_provider"]

    sb_fill = sb_primary[~sb_primary["cell_id"].isin(strict_ids)].copy()
    sb_fill["expanded_fill"] = True
    sb_fill["precedence_resolution"] = ""
    sb_fill["final_primary_source"] = "ncei_singlebeam"

    # Defensive annotation used later by the catalog for sb rows that lose.
    sb_primary["_precedence_loser"] = sb_primary["cell_id"].map(
        lambda c: "superseded_by_jamstec" if strict_provider_by_cell.get(c) == "jamstec" else (
            "superseded_by_ncei_mb" if strict_provider_by_cell.get(c) == "ncei_multibeam" else ""
        )
    )

    expanded = pd.concat([out_base, sb_fill], ignore_index=True, copy=False)
    expanded = core_frame(expanded, EXPANDED_EXTRA_COLUMNS)
    duplicate_count = int(expanded["cell_id"].duplicated().sum())
    if duplicate_count:
        raise AssertionError(f"expanded_primary_ship_cells has duplicate cell_id rows: {duplicate_count:,}")
    return expanded


def annotate_sb_precedence_for_catalog(singlebeam: pd.DataFrame, expanded: pd.DataFrame, strict_primary: pd.DataFrame) -> pd.DataFrame:
    out = singlebeam.copy()
    expanded_provider = expanded.set_index("cell_id")["source_provider"].to_dict()
    strict_provider = strict_primary.set_index("cell_id")["source_provider"].to_dict()

    def final_source(cell_id: str) -> str:
        provider = expanded_provider.get(cell_id, "")
        return "ncei_singlebeam" if provider == "ncei_singlebeam" else provider

    def resolution(cell_id: str) -> str:
        provider = strict_provider.get(cell_id, "")
        if provider == "jamstec":
            return "superseded_by_jamstec"
        if provider == "ncei_multibeam":
            return "superseded_by_ncei_mb"
        return ""

    out["final_primary_source"] = out["cell_id"].map(final_source).fillna("")
    out["precedence_resolution"] = out["cell_id"].map(resolution).fillna("")
    return out


def annotate_mrar_parallel(mrar: pd.DataFrame, expanded: pd.DataFrame) -> pd.DataFrame:
    out = mrar.copy()
    winners = expanded.set_index("cell_id")["source_provider"].to_dict()

    def parallel_label(cell_id: str) -> str:
        provider = winners.get(cell_id, "")
        if provider == "jamstec":
            return "primary_jamstec_regional_mrar_parallel"
        if provider == "ncei_multibeam":
            return "primary_mb_regional_mrar_parallel"
        if provider == "ncei_singlebeam":
            return "primary_sb_regional_mrar_parallel"
        return ""

    out["precedence_resolution"] = out["cell_id"].map(parallel_label).fillna("")
    out["final_primary_source"] = ""
    return out


def build_catalog(
    strict_primary: pd.DataFrame,
    expanded: pd.DataFrame,
    supplementary: pd.DataFrame,
    regional: pd.DataFrame,
) -> pd.DataFrame:
    strict = strict_primary.copy()
    strict["product_label"] = "strict_primary_multibeam"
    strict["product_membership"] = "strict_primary_multibeam"
    strict["final_primary_source"] = strict["source_provider"]

    supp = supplementary.copy()
    supp["product_label"] = "supplementary_singlebeam"
    supp["product_membership"] = "supplementary_singlebeam"

    reg = regional.copy()
    reg["product_label"] = "regional_mrar_experiment"
    reg["product_membership"] = "regional_mrar_experiment"

    frames = [strict, supp, reg]
    if INCLUDE_EXPANDED_SB_MEMBERSHIP_IN_CATALOG:
        expanded_sb = expanded[expanded["source_provider"].eq("ncei_singlebeam")].copy()
        expanded_sb["product_label"] = "supplementary_singlebeam"
        expanded_sb["product_membership"] = "expanded_primary_ship"
        frames.append(expanded_sb)

    out = pd.concat(frames, ignore_index=True, copy=False)
    return core_frame(out, CATALOG_EXTRA_COLUMNS)


# ---------------------------------------------------------------------------
# Assertions / summaries / reporting
# ---------------------------------------------------------------------------
def assert_count(name: str, got: int, *, run_label: str) -> str:
    expected, tolerance = EXPECTED_FULL_COUNTS[name]
    if run_label != "full":
        return f"SKIP ({run_label}): {name} count={got:,}; full expectation={expected:,} ± {tolerance:,}"
    lo = expected - tolerance
    hi = expected + tolerance
    if not (lo <= got <= hi):
        raise AssertionError(f"{name}: expected {expected:,} ± {tolerance:,}, got {got:,}")
    return f"PASS: {name} count={got:,} within expected {expected:,} ± {tolerance:,}"


def run_assertions(
    *,
    run_label: str,
    jamstec: pd.DataFrame,
    ncei_mb_primary: pd.DataFrame,
    strict_primary: pd.DataFrame,
    expanded: pd.DataFrame,
    supplementary: pd.DataFrame,
    regional: pd.DataFrame,
    catalog: pd.DataFrame,
) -> list[str]:
    lines: list[str] = []

    overlap = set(jamstec["cell_id"]) & set(ncei_mb_primary["cell_id"])
    if overlap:
        raise AssertionError(f"JAMSTEC × NCEI mb disjointness failed: {len(overlap):,} overlaps")
    lines.append("PASS: JAMSTEC × NCEI mb disjointness verified (0 overlaps)")

    for name, df in [("strict_primary", strict_primary), ("expanded_primary", expanded)]:
        bad = df["branch"].eq("regional_mrar") | df["source_provider"].eq("mrar")
        if int(bad.sum()):
            raise AssertionError(f"regional_mrar leaked into {name}: {int(bad.sum()):,} rows")
    lines.append("PASS: regional_mrar never appears in strict or expanded primary products")

    lines.append(assert_count("strict_primary", len(strict_primary), run_label=run_label))
    lines.append(assert_count("expanded_primary", len(expanded), run_label=run_label))
    lines.append(assert_count("supplementary_singlebeam", len(supplementary), run_label=run_label))
    lines.append(assert_count("regional_mrar_experiment", len(regional), run_label=run_label))
    lines.append(assert_count("validation_cell_catalog", len(catalog), run_label=run_label))

    n_sentry = int(strict_primary["auv_sentry_flag"].sum())
    min_sentry = 5 if run_label == "full" else 0
    if n_sentry < min_sentry:
        raise AssertionError(f"AUV Sentry retention failed: strict_primary has {n_sentry} AUV rows (<{min_sentry})")
    lines.append(f"PASS: AUV Sentry preserved in strict primary (n={n_sentry:,})")

    jam_max = strict_primary.loc[strict_primary["source_provider"].eq("jamstec"), "validation_weight"].max()
    ncei_mb_max = strict_primary.loc[strict_primary["source_provider"].eq("ncei_multibeam"), "validation_weight"].max()
    if pd.notna(jam_max) and float(jam_max) > 1.0:
        raise AssertionError(f"JAMSTEC validation_weight max {jam_max} > 1.0")
    if pd.notna(ncei_mb_max) and float(ncei_mb_max) > 0.95:
        raise AssertionError(f"NCEI multibeam validation_weight max {ncei_mb_max} > 0.95")
    lines.append(f"PASS: weights not rescaled (JAMSTEC max={jam_max}, NCEI mb max={ncei_mb_max})")

    dupes = int(expanded["cell_id"].duplicated().sum())
    if dupes:
        raise AssertionError(f"expanded_primary conflict resolution failed: {dupes:,} duplicate cell_ids")
    lines.append("PASS: expanded_primary has unique cell_id rows after precedence resolution")
    return lines


def value_counts_table(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=cols + ["n_rows"])
    return df.groupby(cols, dropna=False).size().reset_index(name="n_rows").sort_values(cols)


def markdown_table(df: pd.DataFrame, max_rows: int = 60) -> list[str]:
    if df.empty:
        return ["_None_", ""]
    preview = df.head(max_rows).copy()
    cols = list(preview.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
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


def product_summary(label: str, df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame([{"product": label, "n_rows": 0}])
    return pd.DataFrame([
        {
            "product": label,
            "n_rows": len(df),
            "n_cell_ids": df["cell_id"].nunique(),
            "min_weight": pd.to_numeric(df["validation_weight"], errors="coerce").min(),
            "max_weight": pd.to_numeric(df["validation_weight"], errors="coerce").max(),
            "n_auv_sentry": int(df["auv_sentry_flag"].sum()) if "auv_sentry_flag" in df else 0,
        }
    ])


def make_report(
    *,
    run_label: str,
    elapsed_s: float,
    strict_primary: pd.DataFrame,
    expanded: pd.DataFrame,
    supplementary: pd.DataFrame,
    regional: pd.DataFrame,
    catalog: pd.DataFrame,
    assertion_lines: list[str],
    paths: dict[str, Path],
) -> str:
    products = {
        "strict_primary_multibeam_cells": strict_primary,
        "expanded_primary_ship_cells": expanded,
        "supplementary_singlebeam_cells": supplementary,
        "regional_mrar_experiment_cells": regional,
        "validation_cell_catalog": catalog,
    }
    lines: list[str] = []
    lines.append("# NCEI Step 07B — Validation Cells Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Run label: `{run_label}`")
    lines.append(f"Validation product version: `{VALIDATION_PRODUCT_VERSION}`")
    lines.append(f"Elapsed: {elapsed_s:.1f}s")
    lines.append("")
    lines.append("This report is generated at runtime by `ncei/code/13_build_validation_cells.py`. The stage builds validation products only; it does not mutate Step 04B cells, Step 06B quality flags, or JAMSTEC inputs.")
    if run_label != "full":
        lines.append("")
        lines.append("> Sample/test100 note: row counts reflect stratified input subsets. Full-run expected-count assertions are reported as skipped in non-full modes.")
    lines.append("")

    lines.append("## 1. Per-product row count summary")
    lines.append("")
    summary = pd.concat([product_summary(label, df) for label, df in products.items()], ignore_index=True)
    lines.extend(markdown_table(summary))

    lines.append("## 2. Tier distribution + source provider mix")
    lines.append("")
    for label, df in products.items():
        lines.append(f"### {label}")
        lines.append("")
        lines.extend(markdown_table(value_counts_table(df, ["source_provider", "quality_tier"]), max_rows=80))

    lines.append("## 3. Conflict resolution outcome")
    lines.append("")
    lines.extend(markdown_table(value_counts_table(expanded, ["source_provider", "precedence_resolution", "expanded_fill"]), max_rows=80))

    lines.append("## 4. Runtime assertions")
    lines.append("")
    for item in assertion_lines:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## 5. AUV Sentry retention summary")
    lines.append("")
    sentry_rows = []
    for label, df in products.items():
        sentry_rows.append({"product": label, "n_auv_sentry": int(df["auv_sentry_flag"].sum()) if "auv_sentry_flag" in df else 0})
    lines.extend(markdown_table(pd.DataFrame(sentry_rows)))

    lines.append("## 6. Weight-scale comparison")
    lines.append("")
    weight_rows = []
    for label, df in products.items():
        for provider, sub in df.groupby("source_provider", dropna=False):
            w = pd.to_numeric(sub["validation_weight"], errors="coerce")
            weight_rows.append(
                {
                    "product": label,
                    "source_provider": provider,
                    "n_rows": len(sub),
                    "min_weight": w.min(),
                    "median_weight": w.median(),
                    "max_weight": w.max(),
                    "unique_weights_sample": ",".join(map(str, sorted(w.dropna().unique())[:12])),
                }
            )
    lines.extend(markdown_table(pd.DataFrame(weight_rows), max_rows=100))
    lines.append("Weights are preserved verbatim: NCEI Step 06B weights remain on the [0.1, 0.95] policy scale and JAMSTEC legacy A/B/C weights remain {0.4, 0.7, 1.0}. They are intentionally NOT rescaled.")
    lines.append("")

    lines.append("## 7. Cross-links")
    lines.append("")
    lines.append("- Spec: `.trellis/spec/backend/pipeline-design-decisions.md` §13–§18.")
    lines.append("- Step 07A preflight: `ncei/docs/step07a_validation_cell_preflight_report.md`.")
    lines.append("- Step 06B report: `ncei/docs/step06b_cell_quality_flags_report.md`.")
    lines.append("- Step 05B audit: `ncei/docs/step05b_cross_branch_overlap_audit_report.md`.")
    lines.append("")

    lines.append("## 8. Step 11 GEBCO/ETOPO/SRTM15/SWOT recommendation")
    lines.append("")
    lines.append("Use `expanded_primary_ship_cells` as the default one-row-per-cell ship-truth input for Step 11. It applies the locked source precedence (JAMSTEC mb > NCEI mb > NCEI singlebeam fill) while keeping source provenance and original weights. Use `strict_primary_multibeam_cells` for a multibeam-only baseline, `supplementary_singlebeam_cells` for coverage sensitivity, `regional_mrar_experiment_cells` only for regional experiments, and `validation_cell_catalog` for audit / sensitivity analyses of precedence-loser rows and product memberships.")
    lines.append("")

    lines.append("## 9. Output paths")
    lines.append("")
    out_rows = [{"kind": k, "path": str(p.relative_to(REPO_ROOT))} for k, p in paths.items() if k not in {"root", "log"}]
    lines.extend(markdown_table(pd.DataFrame(out_rows), max_rows=20))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Step 07B — build NCEI validation-cell products from Step 04B cells, "
            "Step 06B quality flags, and JAMSTEC primary validation cells. "
            "Run from repo root (/mnt/data2/00-Data/ship)."
        )
    )
    parser.add_argument("--run-label", choices=VALID_RUN_LABELS, default="sample")
    parser.add_argument("--confirm-full", action="store_true", help="Required when --run-label=full")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing Step 07B outputs")
    args = parser.parse_args(argv)

    paths = output_paths(args.run_label)
    logger = setup_logging(paths["log"])
    t0 = datetime.now()

    logger.info("=" * 72)
    logger.info("13_build_validation_cells.py START")
    logger.info("Args: %s", vars(args))
    logger.info("Validation product version: %s", VALIDATION_PRODUCT_VERSION)

    if args.run_label == "full" and not args.confirm_full:
        logger.error("ABORTED: --run-label=full requires --confirm-full")
        return 2
    if Path.cwd().resolve() != REPO_ROOT:
        logger.warning("Expected repo root cwd %s; current cwd is %s", REPO_ROOT, Path.cwd().resolve())
    if not args.overwrite:
        exists = existing_outputs(paths)
        if exists:
            logger.error("ABORTED: outputs exist; use --overwrite. Existing: %s", exists)
            return 2

    try:
        jamstec = load_jamstec_primary(args.run_label, logger)
        ncei_mb = load_ncei_branch("multibeam_ncei", args.run_label, logger)
        singlebeam = load_ncei_branch("singlebeam", args.run_label, logger)
        regional_src = load_ncei_branch("regional_mrar", args.run_label, logger)

        ncei_mb_primary = ncei_mb[ncei_mb["use_for_primary_validation"].fillna(False).astype(bool)].copy()
        strict_primary = build_strict_primary(jamstec, ncei_mb)
        expanded = build_expanded_primary(strict_primary, singlebeam)
        supplementary = singlebeam[singlebeam["use_for_supplementary_validation"].fillna(False).astype(bool)].copy()
        supplementary = annotate_sb_precedence_for_catalog(supplementary, expanded, strict_primary)
        supplementary["branch_role"] = "supplementary_coverage"
        supplementary = core_frame(supplementary)
        regional = regional_src.copy()
        regional["branch_role"] = "regional_experiment"
        regional = annotate_mrar_parallel(regional, expanded)
        regional = core_frame(regional)
        catalog = build_catalog(strict_primary, expanded, supplementary, regional)

        assertion_lines = run_assertions(
            run_label=args.run_label,
            jamstec=jamstec,
            ncei_mb_primary=ncei_mb_primary,
            strict_primary=strict_primary,
            expanded=expanded,
            supplementary=supplementary,
            regional=regional,
            catalog=catalog,
        )
        for line in assertion_lines:
            logger.info(line)

        elapsed_s = (datetime.now() - t0).total_seconds()
        report = make_report(
            run_label=args.run_label,
            elapsed_s=elapsed_s,
            strict_primary=strict_primary,
            expanded=expanded,
            supplementary=supplementary,
            regional=regional,
            catalog=catalog,
            assertion_lines=assertion_lines,
            paths=paths,
        )

        atomic_write_parquet(strict_primary, paths["strict_primary"])
        atomic_write_parquet(expanded, paths["expanded_primary"])
        write_hive_dataset(supplementary, paths["supplementary_singlebeam"], ["lat_band_10deg"], overwrite=args.overwrite)
        write_hive_dataset(regional, paths["regional_mrar_experiment"], ["lat_band_10deg"], overwrite=args.overwrite)
        write_hive_dataset(catalog, paths["validation_cell_catalog"], ["product_label"], overwrite=args.overwrite)
        atomic_write_text(report, paths["report"])

        logger.info("Wrote strict_primary_multibeam_cells: %s (%d rows)", paths["strict_primary"], len(strict_primary))
        logger.info("Wrote expanded_primary_ship_cells: %s (%d rows)", paths["expanded_primary"], len(expanded))
        logger.info("Wrote supplementary_singlebeam_cells dataset: %s (%d rows)", paths["supplementary_singlebeam"], len(supplementary))
        logger.info("Wrote regional_mrar_experiment_cells dataset: %s (%d rows)", paths["regional_mrar_experiment"], len(regional))
        logger.info("Wrote validation_cell_catalog dataset: %s (%d rows)", paths["validation_cell_catalog"], len(catalog))
        logger.info("Wrote report: %s", paths["report"])
        logger.info("Elapsed: %.1fs", elapsed_s)
        logger.info("13_build_validation_cells.py DONE")

        print(f"Strict primary:      {paths['strict_primary']} ({len(strict_primary):,} rows)")
        print(f"Expanded primary:    {paths['expanded_primary']} ({len(expanded):,} rows)")
        print(f"Supplementary SB:    {paths['supplementary_singlebeam']} ({len(supplementary):,} rows)")
        print(f"Regional M.rar:      {paths['regional_mrar_experiment']} ({len(regional):,} rows)")
        print(f"Catalog:             {paths['validation_cell_catalog']} ({len(catalog):,} rows)")
        print(f"Report:              {paths['report']}")
        return 0

    except Exception as exc:  # noqa: BLE001 - pipeline top-level guard
        logger.exception("ABORTED with error: %r", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
