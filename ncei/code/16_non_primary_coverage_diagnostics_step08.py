#!/usr/bin/env python3
"""
16_non_primary_coverage_diagnostics_step08.py

Step 08 Stage 5 diagnostics for non-primary validation-cell products.

This script is read-only with respect to Step 07B validation products. It
summarizes coverage, quality mix, and cell-id overlap for the non-primary
products; it does not sample gridded models and does not write validation
by-cell residual outputs.

Reads:
  - ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet
  - ncei/derived/validation_cells_1min/expanded_primary_ship_cells.parquet
  - ncei/derived/validation_cells_1min/supplementary_singlebeam_cells.parquet/
  - ncei/derived/validation_cells_1min/regional_mrar_experiment_cells.parquet/
  - ncei/derived/validation_cells_1min/validation_cell_catalog.parquet/

Writes (full mode):
  - ncei/derived/model_validation_1min_<run-label>/non_primary_product_summary.parquet
  - ncei/derived/model_validation_1min_<run-label>/non_primary_product_summary.tsv
  - ncei/derived/model_validation_1min_<run-label>/non_primary_stratum_summary.parquet
  - ncei/derived/model_validation_1min_<run-label>/non_primary_stratum_summary.tsv
  - ncei/derived/model_validation_1min_<run-label>/non_primary_overlap_summary.parquet
  - ncei/derived/model_validation_1min_<run-label>/non_primary_overlap_summary.tsv
  - ncei/derived/model_validation_1min_<run-label>/non_primary_overlap_by_stratum.parquet
  - ncei/derived/model_validation_1min_<run-label>/non_primary_overlap_by_stratum.tsv
  - ncei/derived/model_validation_1min_<run-label>/non_primary_pairwise_overlap_summary.parquet
  - ncei/derived/model_validation_1min_<run-label>/non_primary_pairwise_overlap_summary.tsv
  - ncei/derived/model_validation_1min_<run-label>/validation_catalog_product_summary.parquet
  - ncei/derived/model_validation_1min_<run-label>/validation_catalog_product_summary.tsv
  - ncei/derived/model_validation_1min_<run-label>/non_primary_safety_checks.parquet
  - ncei/derived/model_validation_1min_<run-label>/non_primary_safety_checks.tsv
  - ncei/docs/step08_non_primary_diagnostics_report_<run-label>.md
  - ncei/output/logs/16_non_primary_coverage_diagnostics_step08_<run-label>.log

Usage:
    python ncei/code/16_non_primary_coverage_diagnostics_step08.py \
      --run-label stage5_non_primary --confirm-full --overwrite
"""

from __future__ import annotations

import argparse
import logging
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as pds
import pyarrow.parquet as pq

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent
REPO_ROOT = ROOT_DIR.parent

VALIDATION_ROOT = ROOT_DIR / "derived" / "validation_cells_1min"
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"

STRICT_PRIMARY_PATH = VALIDATION_ROOT / "strict_primary_multibeam_cells.parquet"
EXPANDED_PRIMARY_PATH = VALIDATION_ROOT / "expanded_primary_ship_cells.parquet"
CATALOG_PATH = VALIDATION_ROOT / "validation_cell_catalog.parquet"

NON_PRIMARY_PRODUCTS: dict[str, dict[str, Any]] = {
    "supplementary_singlebeam_cells": {
        "path": VALIDATION_ROOT / "supplementary_singlebeam_cells.parquet",
        "expected_rows": 12_277_633,
        "product_role": "supplementary_singlebeam",
        "expected_branch": "singlebeam",
        "expected_branch_role": "supplementary_coverage",
        "expected_source_provider": "ncei_singlebeam",
        "policy": "coverage diagnostics only",
    },
    "regional_mrar_experiment_cells": {
        "path": VALIDATION_ROOT / "regional_mrar_experiment_cells.parquet",
        "expected_rows": 9_019_383,
        "product_role": "regional_mrar_experiment",
        "expected_branch": "regional_mrar",
        "expected_branch_role": "regional_experiment",
        "expected_source_provider": "mrar",
        "policy": "regional sensitivity only",
    },
}

PRIMARY_PRODUCTS: dict[str, Path] = {
    "strict_primary_multibeam_cells": STRICT_PRIMARY_PATH,
    "expanded_primary_ship_cells": EXPANDED_PRIMARY_PATH,
}

DEPTH_BIN_LABELS = {
    0: "0-200m",
    200: "200-500m",
    500: "500-2000m",
    2000: "2000-4000m",
    4000: "4000-6000m",
    6000: "6000-11500m",
}

PRODUCT_COLUMNS = [
    "cell_id",
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

CORE_COLUMNS = {
    "cell_id",
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
    "depth_bin",
}

STRATIFICATION_COLUMNS = [
    "lat_band_10deg",
    "depth_bin_label",
    "quality_tier",
    "evidence_class",
    "source_risk_class",
    "low_evidence_flag",
    "manual_review_any",
    "sensitivity_only_flag",
    "region_10deg",
]

OVERLAP_STRATIFICATION_COLUMNS = [
    "lat_band_10deg",
    "depth_bin_label",
    "quality_tier",
    "evidence_class",
    "region_10deg",
]


# ---------------------------------------------------------------------------
# Paths / logging / atomic writes
# ---------------------------------------------------------------------------

def output_dir(run_label: str) -> Path:
    return ROOT_DIR / "derived" / f"model_validation_1min_{run_label}"


def setup_logging(run_label: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"16_non_primary_coverage_diagnostics_step08_{run_label}.log"

    logger = logging.getLogger("ncei_step08_stage5")
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


def ensure_writable(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output exists; pass --overwrite to replace: {path}")


def atomic_write_text(text: str, path: Path, overwrite: bool) -> None:
    ensure_writable(path, overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_parquet(df: pd.DataFrame, path: Path, overwrite: bool) -> None:
    ensure_writable(path, overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def atomic_write_tsv(df: pd.DataFrame, path: Path, overwrite: bool) -> None:
    ensure_writable(path, overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Read / transform helpers
# ---------------------------------------------------------------------------

def parquet_dataset(path: Path) -> pds.Dataset:
    if not path.exists():
        raise FileNotFoundError(path)
    return pds.dataset(path, format="parquet", partitioning="hive")


def dataset_row_count(path: Path) -> int:
    return int(parquet_dataset(path).count_rows())


def read_dataset_columns(path: Path, columns: Iterable[str], required: set[str]) -> pd.DataFrame:
    dataset = parquet_dataset(path)
    schema_names = set(dataset.schema.names)
    missing = sorted(required - schema_names)
    if missing:
        raise RuntimeError(f"{path} missing required column(s): {missing}")
    selected = [col for col in columns if col in schema_names]
    return dataset.to_table(columns=selected).to_pandas()


def read_id_frame(path: Path) -> pd.DataFrame:
    return read_dataset_columns(path, ["cell_id"], {"cell_id"})


def read_primary_frame(path: Path) -> pd.DataFrame:
    dataset = parquet_dataset(path)
    cols = ["cell_id", "source_provider", "branch", "expanded_fill"]
    selected = [col for col in cols if col in set(dataset.schema.names)]
    return dataset.to_table(columns=selected).to_pandas()


def normalize_bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    if str(series.dtype) == "boolean":
        return series.fillna(False).astype(bool)
    text = series.astype(str).str.strip().str.lower()
    return text.isin(["true", "1", "yes", "y"])


def depth_bin_label(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    labels = numeric.map(lambda value: DEPTH_BIN_LABELS.get(int(value), "unknown") if pd.notna(value) else "unknown")
    return labels.astype(str)


def region_10deg(lon: pd.Series, lat: pd.Series) -> pd.Series:
    lon_values = pd.to_numeric(lon, errors="coerce").to_numpy(dtype=np.float64)
    lat_values = pd.to_numeric(lat, errors="coerce").to_numpy(dtype=np.float64)
    valid = np.isfinite(lon_values) & np.isfinite(lat_values)
    out = np.full(len(lon_values), "unknown", dtype=object)
    lon_floor = (np.floor(lon_values[valid] / 10.0) * 10).astype(int)
    lat_floor = (np.floor(lat_values[valid] / 10.0) * 10).astype(int)
    out[valid] = [f"lon{lo:04d}_lat{la:04d}" for lo, la in zip(lon_floor, lat_floor)]
    return pd.Series(out, index=lon.index, dtype="string")


def prepare_non_primary_frame(product_key: str, path: Path, logger: logging.Logger) -> pd.DataFrame:
    logger.info("reading %s", path)
    df = read_dataset_columns(path, PRODUCT_COLUMNS, CORE_COLUMNS)
    logger.info("loaded %s rows=%d", product_key, len(df))

    for col in ["source_risk_class", "precedence_resolution", "final_primary_source", "source_dataset", "dominant_file_id"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)
        else:
            df[col] = ""

    for col in ["manual_review_any", "low_evidence_flag", "sensitivity_only_flag", "auv_sentry_flag"]:
        if col in df.columns:
            df[col] = normalize_bool_series(df[col])
        else:
            df[col] = False

    df["depth_bin_label"] = depth_bin_label(df["depth_bin"])
    df["region_10deg"] = region_10deg(df["lon_center"], df["lat_center"])
    df["has_cross_branch_overlap"] = pd.to_numeric(df.get("n_cross_branch_overlap", 0), errors="coerce").fillna(0).gt(0)
    df["product_key"] = product_key
    df["product_role"] = NON_PRIMARY_PRODUCTS[product_key]["product_role"]
    return df


# ---------------------------------------------------------------------------
# Summaries and checks
# ---------------------------------------------------------------------------

def count_value(series: pd.Series, value: Any) -> int:
    return int((series.astype(str) == str(value)).sum())


def finite_median(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce")
    return float(values.median()) if len(values) else np.nan


def product_summary(product_key: str, df: pd.DataFrame) -> dict[str, Any]:
    info = NON_PRIMARY_PRODUCTS[product_key]
    n_rows = int(len(df))
    n_cell_ids = int(df["cell_id"].nunique(dropna=True))
    weights = pd.to_numeric(df["validation_weight"], errors="coerce")
    depths = pd.to_numeric(df["representative_depth_m"], errors="coerce")
    duplicate_ratio = pd.to_numeric(df.get("duplicate_ratio_cell", pd.Series(dtype=float)), errors="coerce")

    return {
        "product_key": product_key,
        "product_role": info["product_role"],
        "policy": info["policy"],
        "n_rows": n_rows,
        "expected_rows": int(info["expected_rows"]),
        "row_count_delta": n_rows - int(info["expected_rows"]),
        "n_cell_ids": n_cell_ids,
        "duplicate_cell_rows": n_rows - n_cell_ids,
        "min_depth_m": float(depths.min()) if len(depths) else np.nan,
        "median_depth_m": float(depths.median()) if len(depths) else np.nan,
        "max_depth_m": float(depths.max()) if len(depths) else np.nan,
        "min_weight": float(weights.min()) if len(weights) else np.nan,
        "median_weight": float(weights.median()) if len(weights) else np.nan,
        "max_weight": float(weights.max()) if len(weights) else np.nan,
        "median_duplicate_ratio": float(duplicate_ratio.median()) if len(duplicate_ratio) else np.nan,
        "high_confidence_cells": count_value(df["quality_tier"], "high_confidence"),
        "medium_confidence_cells": count_value(df["quality_tier"], "medium_confidence"),
        "low_confidence_cells": count_value(df["quality_tier"], "low_confidence"),
        "review_or_sensitivity_only_cells": count_value(df["quality_tier"], "review_or_sensitivity_only"),
        "evidence_none_cells": count_value(df["evidence_class"], "none"),
        "low_evidence_flag_cells": int(df["low_evidence_flag"].sum()),
        "manual_review_cells": int(df["manual_review_any"].sum()),
        "sensitivity_only_cells": int(df["sensitivity_only_flag"].sum()),
        "cells_with_cross_branch_overlap": int(df["has_cross_branch_overlap"].sum()),
        "n_lat_bands": int(df["lat_band_10deg"].nunique(dropna=True)),
        "n_depth_bins": int(df["depth_bin_label"].nunique(dropna=True)),
        "n_regions_10deg": int(df["region_10deg"].nunique(dropna=True)),
    }


def stratum_summary(product_key: str, df: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    work = df.copy()
    for col in STRATIFICATION_COLUMNS:
        grouped = (
            work.groupby(col, dropna=False)
            .agg(
                cells=("cell_id", "count"),
                median_depth_m=("representative_depth_m", finite_median),
                median_weight=("validation_weight", finite_median),
                low_evidence_cells=("low_evidence_flag", "sum"),
                manual_review_cells=("manual_review_any", "sum"),
                sensitivity_only_cells=("sensitivity_only_flag", "sum"),
                cross_branch_overlap_cells=("has_cross_branch_overlap", "sum"),
            )
            .reset_index()
            .rename(columns={col: "stratum"})
        )
        grouped["stratum"] = grouped["stratum"].astype(str)
        grouped["product_key"] = product_key
        grouped["product_role"] = NON_PRIMARY_PRODUCTS[product_key]["product_role"]
        grouped["stratification"] = col
        rows.append(grouped)
    out = pd.concat(rows, ignore_index=True)
    ordered_cols = [
        "product_key",
        "product_role",
        "stratification",
        "stratum",
        "cells",
        "median_depth_m",
        "median_weight",
        "low_evidence_cells",
        "manual_review_cells",
        "sensitivity_only_cells",
        "cross_branch_overlap_cells",
    ]
    return out[ordered_cols].sort_values(["product_key", "stratification", "cells"], ascending=[True, True, False]).reset_index(drop=True)


def overlap_summary(product_key: str, df: pd.DataFrame, strict_ids: set[Any], expanded_ids: set[Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = df[["cell_id", *OVERLAP_STRATIFICATION_COLUMNS]].copy()
    work["in_strict_primary"] = work["cell_id"].isin(strict_ids)
    work["in_expanded_primary"] = work["cell_id"].isin(expanded_ids)
    work["not_in_expanded_primary"] = ~work["in_expanded_primary"]

    n_rows = int(len(work))
    strict_overlap = int(work["in_strict_primary"].sum())
    expanded_overlap = int(work["in_expanded_primary"].sum())
    summary = pd.DataFrame([{
        "product_key": product_key,
        "product_role": NON_PRIMARY_PRODUCTS[product_key]["product_role"],
        "non_primary_cells": n_rows,
        "strict_primary_overlap_cells": strict_overlap,
        "strict_primary_overlap_fraction": strict_overlap / n_rows if n_rows else np.nan,
        "expanded_primary_overlap_cells": expanded_overlap,
        "expanded_primary_overlap_fraction": expanded_overlap / n_rows if n_rows else np.nan,
        "outside_expanded_primary_cells": n_rows - expanded_overlap,
        "outside_expanded_primary_fraction": (n_rows - expanded_overlap) / n_rows if n_rows else np.nan,
    }])

    rows: list[pd.DataFrame] = []
    for col in OVERLAP_STRATIFICATION_COLUMNS:
        grouped = (
            work.groupby(col, dropna=False)
            .agg(
                non_primary_cells=("cell_id", "count"),
                strict_primary_overlap_cells=("in_strict_primary", "sum"),
                expanded_primary_overlap_cells=("in_expanded_primary", "sum"),
                outside_expanded_primary_cells=("not_in_expanded_primary", "sum"),
            )
            .reset_index()
            .rename(columns={col: "stratum"})
        )
        grouped["stratum"] = grouped["stratum"].astype(str)
        grouped["product_key"] = product_key
        grouped["product_role"] = NON_PRIMARY_PRODUCTS[product_key]["product_role"]
        grouped["stratification"] = col
        grouped["strict_primary_overlap_fraction"] = grouped["strict_primary_overlap_cells"] / grouped["non_primary_cells"]
        grouped["expanded_primary_overlap_fraction"] = grouped["expanded_primary_overlap_cells"] / grouped["non_primary_cells"]
        rows.append(grouped)
    by_stratum = pd.concat(rows, ignore_index=True)
    ordered = [
        "product_key",
        "product_role",
        "stratification",
        "stratum",
        "non_primary_cells",
        "strict_primary_overlap_cells",
        "strict_primary_overlap_fraction",
        "expanded_primary_overlap_cells",
        "expanded_primary_overlap_fraction",
        "outside_expanded_primary_cells",
    ]
    by_stratum = by_stratum[ordered].sort_values(
        ["product_key", "stratification", "non_primary_cells"],
        ascending=[True, True, False],
    ).reset_index(drop=True)
    return summary, by_stratum


def pairwise_non_primary_overlap(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    keys = list(frames)
    rows: list[dict[str, Any]] = []
    for left in keys:
        left_ids = set(frames[left]["cell_id"])
        for right in keys:
            if left >= right:
                continue
            right_ids = set(frames[right]["cell_id"])
            overlap = len(left_ids.intersection(right_ids))
            rows.append({
                "left_product_key": left,
                "right_product_key": right,
                "left_cells": len(left_ids),
                "right_cells": len(right_ids),
                "overlap_cells": overlap,
                "overlap_fraction_of_left": overlap / len(left_ids) if left_ids else np.nan,
                "overlap_fraction_of_right": overlap / len(right_ids) if right_ids else np.nan,
            })
    return pd.DataFrame(rows)


def validation_catalog_summary(path: Path) -> pd.DataFrame:
    df = read_dataset_columns(path, ["cell_id", "product_label", "final_primary_source"], {"cell_id", "product_label"})
    grouped = (
        df.groupby("product_label", dropna=False)
        .agg(
            catalog_rows=("cell_id", "count"),
            unique_cell_ids=("cell_id", "nunique"),
            final_primary_source_values=("final_primary_source", lambda s: ",".join(sorted(set(s.fillna("").astype(str))))),
        )
        .reset_index()
    )
    grouped["duplicate_product_cell_rows"] = grouped["catalog_rows"] - grouped["unique_cell_ids"]
    return grouped.sort_values("product_label").reset_index(drop=True)


def safety_checks(
    frames: dict[str, pd.DataFrame],
    primary_frames: dict[str, pd.DataFrame],
    catalog_summary_df: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for product_key, df in frames.items():
        info = NON_PRIMARY_PRODUCTS[product_key]
        n_rows = int(len(df))
        n_cell_ids = int(df["cell_id"].nunique(dropna=True))
        bad_branch = int((df["branch"].astype(str) != info["expected_branch"]).sum())
        bad_branch_role = int((df["branch_role"].astype(str) != info["expected_branch_role"]).sum())
        bad_source = int((df["source_provider"].astype(str) != info["expected_source_provider"]).sum())

        rows.extend([
            {
                "check": f"{product_key}_row_count_matches_expected",
                "status": "PASS" if n_rows == int(info["expected_rows"]) else "FAIL",
                "details": f"rows={n_rows:,}; expected={int(info['expected_rows']):,}",
            },
            {
                "check": f"{product_key}_cell_id_unique",
                "status": "PASS" if n_rows == n_cell_ids else "FAIL",
                "details": f"rows={n_rows:,}; unique_cell_ids={n_cell_ids:,}",
            },
            {
                "check": f"{product_key}_branch_matches_policy",
                "status": "PASS" if bad_branch == 0 else "FAIL",
                "details": f"rows with branch != {info['expected_branch']}: {bad_branch:,}",
            },
            {
                "check": f"{product_key}_branch_role_matches_policy",
                "status": "PASS" if bad_branch_role == 0 else "FAIL",
                "details": f"rows with branch_role != {info['expected_branch_role']}: {bad_branch_role:,}",
            },
            {
                "check": f"{product_key}_source_provider_matches_policy",
                "status": "PASS" if bad_source == 0 else "FAIL",
                "details": f"rows with source_provider != {info['expected_source_provider']}: {bad_source:,}",
            },
        ])

    strict = primary_frames["strict_primary_multibeam_cells"]
    strict_singlebeam = int((strict["source_provider"].astype(str) == "ncei_singlebeam").sum())
    strict_mrar = int((strict["branch"].astype(str) == "regional_mrar").sum())
    rows.extend([
        {
            "check": "strict_primary_contains_no_ncei_singlebeam_rows",
            "status": "PASS" if strict_singlebeam == 0 else "FAIL",
            "details": f"ncei_singlebeam rows in strict_primary={strict_singlebeam:,}",
        },
        {
            "check": "strict_primary_contains_no_regional_mrar_rows",
            "status": "PASS" if strict_mrar == 0 else "FAIL",
            "details": f"regional_mrar rows in strict_primary={strict_mrar:,}",
        },
    ])

    expanded = primary_frames["expanded_primary_ship_cells"]
    expanded_mrar = int((expanded["branch"].astype(str) == "regional_mrar").sum())
    if "expanded_fill" in expanded.columns:
        expanded_fill = normalize_bool_series(expanded["expanded_fill"])
        expanded_singlebeam = expanded["source_provider"].astype(str) == "ncei_singlebeam"
        unmarked_singlebeam = int((expanded_singlebeam & ~expanded_fill).sum())
    else:
        unmarked_singlebeam = -1
    rows.extend([
        {
            "check": "expanded_primary_contains_no_regional_mrar_rows",
            "status": "PASS" if expanded_mrar == 0 else "FAIL",
            "details": f"regional_mrar rows in expanded_primary={expanded_mrar:,}",
        },
        {
            "check": "expanded_primary_singlebeam_rows_are_marked_gapfill",
            "status": "PASS" if unmarked_singlebeam == 0 else "FAIL",
            "details": f"ncei_singlebeam rows with expanded_fill != True: {unmarked_singlebeam:,}",
        },
    ])

    for product_key, info in NON_PRIMARY_PRODUCTS.items():
        role = info["product_role"]
        matched = catalog_summary_df[catalog_summary_df["product_label"].astype(str).eq(role)]
        catalog_rows = int(matched["catalog_rows"].iloc[0]) if len(matched) else -1
        catalog_unique_cell_ids = int(matched["unique_cell_ids"].iloc[0]) if len(matched) else -1
        duplicate_product_cell_rows = int(matched["duplicate_product_cell_rows"].iloc[0]) if len(matched) else -1
        rows.append({
            "check": f"catalog_contains_{role}_with_expected_unique_cell_count",
            "status": "PASS" if catalog_unique_cell_ids == int(info["expected_rows"]) else "FAIL",
            "details": (
                f"unique_cell_ids={catalog_unique_cell_ids:,}; expected={int(info['expected_rows']):,}; "
                f"catalog_rows={catalog_rows:,}; duplicate_membership_rows={duplicate_product_cell_rows:,}"
            ),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def fmt(value: Any, places: int = 4) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.{places}f}" if np.isfinite(value) else ""
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    return str(value)


def markdown_table(df: pd.DataFrame, max_rows: int | None = None) -> str:
    if df is None or len(df) == 0:
        return "_(none)_"
    work = df.head(max_rows).copy() if max_rows is not None else df.copy()
    cols = list(work.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in work.iterrows():
        values = [fmt(row.get(c)).replace("\n", " ").replace("|", "\\|") for c in cols]
        lines.append("| " + " | ".join(values) + " |")
    if max_rows is not None and len(df) > max_rows:
        lines.append(f"\n_Showing {max_rows:,} of {len(df):,} rows._")
    return "\n".join(lines)


def environment_table(args: argparse.Namespace) -> pd.DataFrame:
    return pd.DataFrame([
        {"key": "python", "value": sys.version.replace("\n", " ")},
        {"key": "platform", "value": platform.platform()},
        {"key": "pandas", "value": pd.__version__},
        {"key": "pyarrow", "value": pa.__version__},
        {"key": "repo_root", "value": str(REPO_ROOT)},
        {"key": "run_label", "value": args.run_label},
        {"key": "confirm_full", "value": str(bool(args.confirm_full))},
        {"key": "overwrite", "value": str(bool(args.overwrite))},
        {"key": "sampling", "value": "none; full product scan"},
        {"key": "random_seed", "value": "none"},
    ])


def top_region_tables(stratum_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    regions = stratum_df[stratum_df["stratification"].eq("region_10deg")].copy()
    for product_key in NON_PRIMARY_PRODUCTS:
        sub = regions[regions["product_key"].eq(product_key)].sort_values("cells", ascending=False)
        out[product_key] = sub[[
            "stratum",
            "cells",
            "median_depth_m",
            "median_weight",
            "low_evidence_cells",
            "manual_review_cells",
            "sensitivity_only_cells",
        ]].head(15).reset_index(drop=True)
    return out


def make_report(
    *,
    args: argparse.Namespace,
    status: str,
    elapsed: float,
    inputs_df: pd.DataFrame,
    product_summary_df: pd.DataFrame,
    overlap_df: pd.DataFrame,
    pairwise_overlap_df: pd.DataFrame,
    catalog_summary_df: pd.DataFrame,
    safety_df: pd.DataFrame,
    stratum_df: pd.DataFrame,
    out_dir: Path,
    report_path: Path,
) -> str:
    lines: list[str] = []
    lines.append("# Step 08 Stage 5 - Non-primary Coverage Diagnostics")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Status: **{status}**")
    lines.append(f"Elapsed: {elapsed:.1f}s")
    lines.append(f"Run label: `{args.run_label}`")
    lines.append("")
    lines.append(
        "This report is generated by `ncei/code/16_non_primary_coverage_diagnostics_step08.py`. "
        "It performs coverage and policy diagnostics only; it does not sample gridded products, "
        "does not compute model residuals, and does not promote non-primary cells into strict-primary validation."
    )
    lines.append("")

    lines.append("## 1. Inputs and environment")
    lines.append(markdown_table(inputs_df))
    lines.append("")
    lines.append(markdown_table(environment_table(args)))
    lines.append("")

    lines.append("## 2. Safety checks")
    lines.append(markdown_table(safety_df))
    lines.append("")

    lines.append("## 3. Product summary")
    display_cols = [
        "product_key",
        "policy",
        "n_rows",
        "n_cell_ids",
        "duplicate_cell_rows",
        "median_weight",
        "high_confidence_cells",
        "medium_confidence_cells",
        "low_confidence_cells",
        "review_or_sensitivity_only_cells",
        "evidence_none_cells",
        "low_evidence_flag_cells",
        "sensitivity_only_cells",
        "n_regions_10deg",
    ]
    lines.append(markdown_table(product_summary_df[display_cols]))
    lines.append("")

    lines.append("## 4. Cell-id overlap diagnostics")
    lines.append(markdown_table(overlap_df))
    lines.append("")
    lines.append("Pairwise overlap between the two non-primary products:")
    lines.append("")
    lines.append(markdown_table(pairwise_overlap_df))
    lines.append("")
    lines.append(
        "Overlap is diagnostic, not promotion. A non-primary row can share a `cell_id` with a primary row "
        "as a precedence loser or coverage-only record; source rows still remain in separate products."
    )
    lines.append("")

    lines.append("## 5. Validation catalog product summary")
    lines.append(markdown_table(catalog_summary_df))
    lines.append("")
    lines.append(
        "`supplementary_singlebeam` can have more catalog rows than unique cell ids because Step 07B intentionally "
        "adds `expanded_primary_ship` singlebeam membership rows to the catalog when a high-confidence singlebeam "
        "cell also participates in expanded-primary."
    )
    lines.append("")

    lines.append("## 6. Top 10-degree regions")
    for product_key, table in top_region_tables(stratum_df).items():
        lines.append(f"### {product_key}")
        lines.append(markdown_table(table))
        lines.append("")

    lines.append("## 7. Interpretation")
    supp = product_summary_df[product_summary_df["product_key"].eq("supplementary_singlebeam_cells")].iloc[0]
    reg = product_summary_df[product_summary_df["product_key"].eq("regional_mrar_experiment_cells")].iloc[0]
    supp_overlap = overlap_df[overlap_df["product_key"].eq("supplementary_singlebeam_cells")].iloc[0]
    reg_overlap = overlap_df[overlap_df["product_key"].eq("regional_mrar_experiment_cells")].iloc[0]
    lines.append(
        f"- `supplementary_singlebeam_cells` has {int(supp['n_rows']):,} cells; "
        f"{int(supp['outside_expanded_primary_cells']) if 'outside_expanded_primary_cells' in supp.index else int(supp_overlap['outside_expanded_primary_cells']):,} "
        "are outside expanded-primary cell ids and remain coverage diagnostics only."
    )
    lines.append(
        f"- `regional_mrar_experiment_cells` has {int(reg['n_rows']):,} cells; "
        f"{int(reg['review_or_sensitivity_only_cells']):,} are `review_or_sensitivity_only`, "
        "so the product remains regional sensitivity material rather than primary truth."
    )
    lines.append(
        f"- Regional MRAR overlap with expanded-primary cell ids is {int(reg_overlap['expanded_primary_overlap_cells']):,} cells; "
        "this is a spatial overlap diagnostic and not evidence for promotion."
    )
    lines.append("")

    lines.append("## 8. Output paths")
    output_rows = [
        {"kind": "product_summary", "path": str(out_dir / "non_primary_product_summary.parquet")},
        {"kind": "stratum_summary", "path": str(out_dir / "non_primary_stratum_summary.parquet")},
        {"kind": "overlap_summary", "path": str(out_dir / "non_primary_overlap_summary.parquet")},
        {"kind": "overlap_by_stratum", "path": str(out_dir / "non_primary_overlap_by_stratum.parquet")},
        {"kind": "pairwise_overlap", "path": str(out_dir / "non_primary_pairwise_overlap_summary.parquet")},
        {"kind": "catalog_summary", "path": str(out_dir / "validation_catalog_product_summary.parquet")},
        {"kind": "safety_checks", "path": str(out_dir / "non_primary_safety_checks.parquet")},
        {"kind": "report", "path": str(report_path)},
    ]
    lines.append(markdown_table(pd.DataFrame(output_rows)))
    lines.append("")

    if status == "PASS":
        lines.append(
            "Recommendation: proceed to Stage 6 final cross-stage reporting. Keep strict-primary as the "
            "authoritative global baseline; use supplementary singlebeam and regional MRAR only as diagnostic "
            "and sensitivity references."
        )
    else:
        lines.append("Recommendation: stop before Stage 6 and resolve failed safety checks.")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Step 08 Stage 5 non-primary coverage diagnostics")
    parser.add_argument("--run-label", default="stage5_non_primary", help="Output run label suffix")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--confirm-full", action="store_true", help="Required because this scans full non-primary products")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.confirm_full:
        raise SystemExit("--confirm-full is required because Stage 5 scans full non-primary validation products")

    started = time.time()
    logger = setup_logging(args.run_label)
    out_dir = output_dir(args.run_label)
    report_path = DOCS_DIR / f"step08_non_primary_diagnostics_report_{args.run_label}.md"

    logger.info("starting Stage 5 non-primary diagnostics run_label=%s", args.run_label)
    out_dir.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    input_rows: list[dict[str, Any]] = []
    for product_key, info in NON_PRIMARY_PRODUCTS.items():
        observed = dataset_row_count(info["path"])
        input_rows.append({
            "product_key": product_key,
            "path": str(info["path"]),
            "expected_rows": int(info["expected_rows"]),
            "observed_rows": observed,
            "policy": info["policy"],
        })
    for product_key, path in PRIMARY_PRODUCTS.items():
        input_rows.append({
            "product_key": product_key,
            "path": str(path),
            "expected_rows": "",
            "observed_rows": dataset_row_count(path),
            "policy": "primary reference only",
        })
    input_rows.append({
        "product_key": "validation_cell_catalog",
        "path": str(CATALOG_PATH),
        "expected_rows": "",
        "observed_rows": dataset_row_count(CATALOG_PATH),
        "policy": "catalog reference",
    })
    inputs_df = pd.DataFrame(input_rows)

    frames: dict[str, pd.DataFrame] = {}
    for product_key, info in NON_PRIMARY_PRODUCTS.items():
        frames[product_key] = prepare_non_primary_frame(product_key, info["path"], logger)

    logger.info("reading primary cell ids")
    primary_frames = {key: read_primary_frame(path) for key, path in PRIMARY_PRODUCTS.items()}
    strict_ids = set(primary_frames["strict_primary_multibeam_cells"]["cell_id"])
    expanded_ids = set(primary_frames["expanded_primary_ship_cells"]["cell_id"])

    logger.info("building summaries")
    product_summary_df = pd.DataFrame([product_summary(key, df) for key, df in frames.items()])
    stratum_df = pd.concat([stratum_summary(key, df) for key, df in frames.items()], ignore_index=True)

    overlap_rows: list[pd.DataFrame] = []
    overlap_by_stratum_rows: list[pd.DataFrame] = []
    for product_key, df in frames.items():
        summary, by_stratum = overlap_summary(product_key, df, strict_ids, expanded_ids)
        overlap_rows.append(summary)
        overlap_by_stratum_rows.append(by_stratum)
    overlap_df = pd.concat(overlap_rows, ignore_index=True)
    overlap_by_stratum_df = pd.concat(overlap_by_stratum_rows, ignore_index=True)
    pairwise_overlap_df = pairwise_non_primary_overlap(frames)

    logger.info("reading validation catalog")
    catalog_summary_df = validation_catalog_summary(CATALOG_PATH)
    safety_df = safety_checks(frames, primary_frames, catalog_summary_df)
    status = "PASS" if (safety_df["status"] == "PASS").all() else "FAIL"

    product_summary_path = out_dir / "non_primary_product_summary.parquet"
    stratum_path = out_dir / "non_primary_stratum_summary.parquet"
    overlap_path = out_dir / "non_primary_overlap_summary.parquet"
    overlap_by_stratum_path = out_dir / "non_primary_overlap_by_stratum.parquet"
    pairwise_overlap_path = out_dir / "non_primary_pairwise_overlap_summary.parquet"
    catalog_path = out_dir / "validation_catalog_product_summary.parquet"
    safety_path = out_dir / "non_primary_safety_checks.parquet"

    outputs = [
        product_summary_path,
        product_summary_path.with_suffix(".tsv"),
        stratum_path,
        stratum_path.with_suffix(".tsv"),
        overlap_path,
        overlap_path.with_suffix(".tsv"),
        overlap_by_stratum_path,
        overlap_by_stratum_path.with_suffix(".tsv"),
        pairwise_overlap_path,
        pairwise_overlap_path.with_suffix(".tsv"),
        catalog_path,
        catalog_path.with_suffix(".tsv"),
        safety_path,
        safety_path.with_suffix(".tsv"),
        report_path,
    ]
    for path in outputs:
        ensure_writable(path, args.overwrite)

    logger.info("writing outputs to %s", out_dir)
    atomic_write_parquet(product_summary_df, product_summary_path, args.overwrite)
    atomic_write_tsv(product_summary_df, product_summary_path.with_suffix(".tsv"), args.overwrite)
    atomic_write_parquet(stratum_df, stratum_path, args.overwrite)
    atomic_write_tsv(stratum_df, stratum_path.with_suffix(".tsv"), args.overwrite)
    atomic_write_parquet(overlap_df, overlap_path, args.overwrite)
    atomic_write_tsv(overlap_df, overlap_path.with_suffix(".tsv"), args.overwrite)
    atomic_write_parquet(overlap_by_stratum_df, overlap_by_stratum_path, args.overwrite)
    atomic_write_tsv(overlap_by_stratum_df, overlap_by_stratum_path.with_suffix(".tsv"), args.overwrite)
    atomic_write_parquet(pairwise_overlap_df, pairwise_overlap_path, args.overwrite)
    atomic_write_tsv(pairwise_overlap_df, pairwise_overlap_path.with_suffix(".tsv"), args.overwrite)
    atomic_write_parquet(catalog_summary_df, catalog_path, args.overwrite)
    atomic_write_tsv(catalog_summary_df, catalog_path.with_suffix(".tsv"), args.overwrite)
    atomic_write_parquet(safety_df, safety_path, args.overwrite)
    atomic_write_tsv(safety_df, safety_path.with_suffix(".tsv"), args.overwrite)

    elapsed = time.time() - started
    report = make_report(
        args=args,
        status=status,
        elapsed=elapsed,
        inputs_df=inputs_df,
        product_summary_df=product_summary_df,
        overlap_df=overlap_df,
        pairwise_overlap_df=pairwise_overlap_df,
        catalog_summary_df=catalog_summary_df,
        safety_df=safety_df,
        stratum_df=stratum_df,
        out_dir=out_dir,
        report_path=report_path,
    )
    atomic_write_text(report, report_path, args.overwrite)

    logger.info("Stage 5 status=%s elapsed=%.1fs report=%s", status, elapsed, report_path)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
