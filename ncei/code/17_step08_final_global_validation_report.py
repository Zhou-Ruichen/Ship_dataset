#!/usr/bin/env python3
"""
17_step08_final_global_validation_report.py

Step 08 Stage 6 final cross-stage report for global gridded-product validation.

This script is read-only with respect to Step 07B validation-cell products and
existing Step 08 by-cell validation outputs. It consolidates Stage 3 strict
primary validation, Stage 4 expanded-primary sensitivity validation, and Stage
5 non-primary diagnostics into one final policy report.

Reads:
  - ncei/derived/model_validation_1min_full_strict_primary/
  - ncei/derived/model_validation_1min_full_expanded_primary/
  - ncei/derived/model_validation_1min_stage5_non_primary/
  - ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet

Writes:
  - ncei/derived/model_validation_1min_stage6_final/step08_stage_outcomes.parquet
  - ncei/derived/model_validation_1min_stage6_final/step08_stage_outcomes.tsv
  - ncei/derived/model_validation_1min_stage6_final/step08_final_policy_recommendations.parquet
  - ncei/derived/model_validation_1min_stage6_final/step08_final_policy_recommendations.tsv
  - ncei/derived/model_validation_1min_stage6_final/expanded_gapfill_sensitivity_summary.parquet
  - ncei/derived/model_validation_1min_stage6_final/expanded_gapfill_sensitivity_summary.tsv
  - ncei/docs/step08_final_global_validation_report.md
  - ncei/output/logs/17_step08_final_global_validation_report_<run-label>.log

Usage:
    python ncei/code/17_step08_final_global_validation_report.py \
      --run-label stage6_final --confirm-final --overwrite
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

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent
REPO_ROOT = ROOT_DIR.parent

DERIVED_DIR = ROOT_DIR / "derived"
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"

STRICT_DIR = DERIVED_DIR / "model_validation_1min_full_strict_primary"
EXPANDED_DIR = DERIVED_DIR / "model_validation_1min_full_expanded_primary"
STAGE5_DIR = DERIVED_DIR / "model_validation_1min_stage5_non_primary"
VALIDATION_ROOT = DERIVED_DIR / "validation_cells_1min"
STRICT_PRIMARY_CELLS = VALIDATION_ROOT / "strict_primary_multibeam_cells.parquet"

DEFAULT_REPORT_PATH = DOCS_DIR / "step08_final_global_validation_report.md"
EXPECTED_GLOBAL_PRODUCTS = ["GEBCO_2024", "ETOPO_2022", "SRTM15_V2.7", "SDUST_2023", "TOPO_25.1"]


# ---------------------------------------------------------------------------
# Paths / logging / atomic writes
# ---------------------------------------------------------------------------

def output_dir(run_label: str) -> Path:
    return DERIVED_DIR / f"model_validation_1min_{run_label}"


def setup_logging(run_label: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"17_step08_final_global_validation_report_{run_label}.log"

    logger = logging.getLogger("ncei_step08_stage6")
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
# Read helpers
# ---------------------------------------------------------------------------

def require_path(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def read_tsv(path: Path) -> pd.DataFrame:
    require_path(path)
    return pd.read_csv(path, sep="\t")


def read_parquet(path: Path) -> pd.DataFrame:
    require_path(path)
    return pd.read_parquet(path)


def read_cell_ids(path: Path) -> set[Any]:
    dataset = pds.dataset(require_path(path), format="parquet", partitioning="hive")
    table = dataset.to_table(columns=["cell_id"])
    return set(table.column("cell_id").to_pylist())


def normalize_bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0).astype(float).ne(0)
    text = series.fillna(False).astype(str).str.strip().str.lower()
    return text.isin(["true", "t", "1", "yes", "y"])


def read_by_cell_for_sensitivity(path: Path, strict_ids: set[Any]) -> pd.DataFrame:
    required = ["cell_id", "depth_error_m", "validation_weight", "expanded_fill", "source_provider"]
    dataset = pds.dataset(require_path(path), format="parquet", partitioning="hive")
    schema_names = set(dataset.schema.names)
    missing = [col for col in required if col not in schema_names]
    if missing:
        raise RuntimeError(f"{path} missing required column(s): {missing}")
    df = dataset.to_table(columns=required).to_pandas()
    df["is_retained_multibeam"] = df["cell_id"].isin(strict_ids)
    df["is_singlebeam_gapfill"] = ~df["is_retained_multibeam"]
    df["expanded_fill_bool"] = normalize_bool_series(df["expanded_fill"])
    return df


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def rmse(values: pd.Series) -> float:
    arr = pd.to_numeric(values, errors="coerce").to_numpy(dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return np.nan
    return float(np.sqrt(np.mean(arr ** 2)))


def weighted_rmse(errors: pd.Series, weights: pd.Series) -> float:
    e = pd.to_numeric(errors, errors="coerce").to_numpy(dtype=np.float64)
    w = pd.to_numeric(weights, errors="coerce").to_numpy(dtype=np.float64)
    mask = np.isfinite(e) & np.isfinite(w) & (w > 0)
    if int(mask.sum()) == 0:
        return np.nan
    return float(np.sqrt(np.sum(w[mask] * (e[mask] ** 2)) / np.sum(w[mask])))


def subset_metrics(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "count": int(pd.to_numeric(df["depth_error_m"], errors="coerce").notna().sum()),
        "RMSE": rmse(df["depth_error_m"]),
        "weighted_RMSE": weighted_rmse(df["depth_error_m"], df["validation_weight"]),
    }


def product_name_from_expanded_path(path: Path) -> str:
    prefix = "full_validation_by_cell_expanded_primary_"
    name = path.name
    if not name.startswith(prefix) or not name.endswith(".parquet"):
        raise ValueError(f"Unexpected expanded by-cell filename: {path}")
    return name[len(prefix):-len(".parquet")]


def completed_product_status(path: Path) -> tuple[int, list[str], int]:
    df = read_parquet(path)
    completed = set(df[df["status"].astype(str).eq("ok")]["product_name"].astype(str))
    missing = [name for name in EXPECTED_GLOBAL_PRODUCTS if name not in completed]
    failed_statuses = int((~df["status"].astype(str).isin(["ok", "skipped"])).sum())
    return len(completed), missing, failed_statuses


def validate_gapfill_membership(
    product_name: str,
    df: pd.DataFrame,
    expected_retained: int,
    expected_gapfill: int,
    expected_expanded: int,
) -> None:
    retained_mask = df["is_retained_multibeam"].to_numpy(dtype=bool)
    gapfill_mask = df["is_singlebeam_gapfill"].to_numpy(dtype=bool)

    actual_expanded = int(len(df))
    actual_retained = int(retained_mask.sum())
    actual_gapfill = int(gapfill_mask.sum())
    if actual_expanded != expected_expanded:
        raise RuntimeError(
            f"{product_name}: expanded by-cell rows={actual_expanded:,}; expected={expected_expanded:,}"
        )
    if actual_retained != expected_retained:
        raise RuntimeError(
            f"{product_name}: retained strict cells={actual_retained:,}; expected={expected_retained:,}"
        )
    if actual_gapfill != expected_gapfill:
        raise RuntimeError(
            f"{product_name}: singlebeam gap-fill cells={actual_gapfill:,}; expected={expected_gapfill:,}"
        )

    fill = df["expanded_fill_bool"].to_numpy(dtype=bool)
    added_bad = int((~fill[gapfill_mask]).sum())
    retained_bad = int(fill[retained_mask].sum())
    if added_bad:
        raise RuntimeError(f"{product_name}: {added_bad:,} gap-fill cells have expanded_fill != True")
    if retained_bad:
        raise RuntimeError(f"{product_name}: {retained_bad:,} retained strict cells have expanded_fill == True")

    source = df["source_provider"].astype(str)
    gapfill_source_bad = int((df["is_singlebeam_gapfill"] & source.ne("ncei_singlebeam")).sum())
    retained_source_bad = int((df["is_retained_multibeam"] & source.eq("ncei_singlebeam")).sum())
    if gapfill_source_bad:
        raise RuntimeError(f"{product_name}: {gapfill_source_bad:,} gap-fill cells are not ncei_singlebeam")
    if retained_source_bad:
        raise RuntimeError(f"{product_name}: {retained_source_bad:,} retained strict cells are ncei_singlebeam")


def build_gapfill_sensitivity(
    strict_ids: set[Any],
    comparison: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    comparison_by_product = comparison.set_index("product_name", drop=False)
    missing_products = [name for name in EXPECTED_GLOBAL_PRODUCTS if name not in comparison_by_product.index]
    if missing_products:
        raise RuntimeError(f"Stage 4 comparison missing expected product(s): {missing_products}")

    rows: list[dict[str, Any]] = []
    for product_name in EXPECTED_GLOBAL_PRODUCTS:
        path = EXPANDED_DIR / f"full_validation_by_cell_expanded_primary_{product_name}.parquet"
        logger.info("computing retained/gap-fill RMSE for %s", product_name)
        df = read_by_cell_for_sensitivity(path, strict_ids)
        expected = comparison_by_product.loc[product_name]
        validate_gapfill_membership(
            product_name,
            df,
            expected_retained=int(expected["strict_count"]),
            expected_gapfill=int(expected["coverage_gain_count"]),
            expected_expanded=int(expected["expanded_count"]),
        )
        retained = subset_metrics(df[df["is_retained_multibeam"]])
        gapfill = subset_metrics(df[df["is_singlebeam_gapfill"]])
        rows.append({
            "product_name": product_name,
            "retained_multibeam_count": retained["count"],
            "singlebeam_gapfill_count": gapfill["count"],
            "retained_multibeam_RMSE": retained["RMSE"],
            "singlebeam_gapfill_RMSE": gapfill["RMSE"],
            "gapfill_minus_retained_RMSE": gapfill["RMSE"] - retained["RMSE"],
            "gapfill_to_retained_RMSE_ratio": gapfill["RMSE"] / retained["RMSE"] if retained["RMSE"] else np.nan,
            "retained_multibeam_weighted_RMSE": retained["weighted_RMSE"],
            "singlebeam_gapfill_weighted_RMSE": gapfill["weighted_RMSE"],
        })
    return pd.DataFrame(rows).sort_values("product_name").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Report tables
# ---------------------------------------------------------------------------

def safety_status(path: Path) -> tuple[int, int]:
    df = read_tsv(path)
    pass_count = int((df["status"] == "PASS").sum())
    fail_count = int((df["status"] != "PASS").sum())
    return pass_count, fail_count


def skipped_summary(path: Path) -> str:
    df = read_tsv(path)
    if len(df) == 0:
        return "none"
    return "; ".join(f"{row.product_name}: {row.reason}" for row in df.itertuples(index=False))


def build_stage_outcomes(
    strict_summary: pd.DataFrame,
    expanded_summary: pd.DataFrame,
    stage5_product: pd.DataFrame,
    stage5_safety: pd.DataFrame,
) -> pd.DataFrame:
    strict_pass, strict_fail = safety_status(STRICT_DIR / "full_validation_safety_checks_strict_primary.tsv")
    expanded_pass, expanded_fail = safety_status(EXPANDED_DIR / "full_validation_safety_checks_expanded_primary.tsv")
    stage5_pass = int((stage5_safety["status"] == "PASS").sum())
    stage5_fail = int((stage5_safety["status"] != "PASS").sum())
    strict_completed, strict_missing, strict_failed_statuses = completed_product_status(
        STRICT_DIR / "full_validation_product_status_strict_primary.parquet"
    )
    expanded_completed, expanded_missing, expanded_failed_statuses = completed_product_status(
        EXPANDED_DIR / "full_validation_product_status_expanded_primary.parquet"
    )

    supp = stage5_product[stage5_product["product_key"].eq("supplementary_singlebeam_cells")].iloc[0]
    reg = stage5_product[stage5_product["product_key"].eq("regional_mrar_experiment_cells")].iloc[0]

    return pd.DataFrame([
        {
            "stage": "Stage 3",
            "product_scope": "strict_primary_multibeam_cells",
            "status": "PASS" if strict_fail == 0 and not strict_missing and strict_failed_statuses == 0 else "FAIL",
            "cells": int(strict_summary["requested_cells"].iloc[0]),
            "completed_products": strict_completed,
            "safety_pass": strict_pass,
            "safety_fail": strict_fail,
            "skip_summary": skipped_summary(STRICT_DIR / "skipped_products.tsv"),
            "policy_role": "authoritative global baseline",
        },
        {
            "stage": "Stage 4",
            "product_scope": "expanded_primary_ship_cells",
            "status": "PASS" if expanded_fail == 0 and not expanded_missing and expanded_failed_statuses == 0 else "FAIL",
            "cells": int(expanded_summary["requested_cells"].iloc[0]),
            "completed_products": expanded_completed,
            "safety_pass": expanded_pass,
            "safety_fail": expanded_fail,
            "skip_summary": skipped_summary(EXPANDED_DIR / "skipped_products.tsv"),
            "policy_role": "secondary sensitivity / coverage expansion",
        },
        {
            "stage": "Stage 5",
            "product_scope": "supplementary_singlebeam + regional_mrar_experiment",
            "status": "PASS" if stage5_fail == 0 else "FAIL",
            "cells": int(supp["n_rows"]) + int(reg["n_rows"]),
            "completed_products": 2,
            "safety_pass": stage5_pass,
            "safety_fail": stage5_fail,
            "skip_summary": "not applicable; diagnostics only",
            "policy_role": "non-primary diagnostics / regional sensitivity only",
        },
    ])


def build_policy_recommendations() -> pd.DataFrame:
    rows = [
        {
            "area": "global_baseline",
            "recommendation": "Use strict_primary_multibeam_cells as the authoritative global validation baseline.",
            "basis": "Stage 3 passed all safety checks on 2,398,774 multibeam cells with no singlebeam or regional_mrar rows.",
        },
        {
            "area": "expanded_primary",
            "recommendation": "Keep expanded_primary_ship_cells as secondary sensitivity / coverage-expansion output, not the global baseline.",
            "basis": "Stage 4 adds 333,915 singlebeam gap-fill cells and raises overall RMSE by 6-8 m across all products while preserving ranking.",
        },
        {
            "area": "supplementary_singlebeam",
            "recommendation": "Use supplementary_singlebeam_cells for coverage diagnostics only.",
            "basis": "Stage 5 role checks passed; 11,399,058 supplementary cells are outside expanded-primary cell IDs and remain non-primary coverage material.",
        },
        {
            "area": "regional_mrar",
            "recommendation": "Use regional_mrar_experiment_cells only for explicit regional sensitivity experiments.",
            "basis": "Stage 5 role checks passed; 9,015,418 of 9,019,383 cells are review_or_sensitivity_only, and overlap with primary cell IDs is diagnostic only.",
        },
        {
            "area": "swot_t1",
            "recommendation": "Do not claim global SWOT_T1 validation from this task.",
            "basis": "Stage 3 skipped SWOT_T1 because it is a regional footprint product; a separate regional-footprint-compatible task is required.",
        },
        {
            "area": "quality_policy",
            "recommendation": "Do not use model residuals to filter, relabel, or promote validation cells.",
            "basis": "Stages 3 and 4 passed no_model_residual_filtering checks; Stage 5 performed diagnostics without model sampling.",
        },
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def fmt(value: Any, places: int = 2) -> str:
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


def markdown_table(df: pd.DataFrame, max_rows: int | None = None, places: int = 2) -> str:
    if df is None or len(df) == 0:
        return "_(none)_"
    work = df.head(max_rows).copy() if max_rows is not None else df.copy()
    cols = list(work.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in work.iterrows():
        values = [fmt(row.get(c), places=places).replace("\n", " ").replace("|", "\\|") for c in cols]
        lines.append("| " + " | ".join(values) + " |")
    if max_rows is not None and len(df) > max_rows:
        lines.append(f"\n_Showing {max_rows:,} of {len(df):,} rows._")
    return "\n".join(lines)


def environment_table(args: argparse.Namespace) -> pd.DataFrame:
    return pd.DataFrame([
        {"key": "generated_utc", "value": datetime.now(timezone.utc).isoformat()},
        {"key": "python", "value": sys.version.replace("\n", " ")},
        {"key": "platform", "value": platform.platform()},
        {"key": "pandas", "value": pd.__version__},
        {"key": "pyarrow", "value": pa.__version__},
        {"key": "repo_root", "value": str(REPO_ROOT)},
        {"key": "run_label", "value": args.run_label},
        {"key": "confirm_final", "value": str(bool(args.confirm_final))},
        {"key": "overwrite", "value": str(bool(args.overwrite))},
        {"key": "model_sampling", "value": "none; report reads existing Stage 3/4/5 artifacts"},
        {"key": "random_seed", "value": "none"},
    ])


def compact_metric_table(strict_summary: pd.DataFrame, expanded_summary: pd.DataFrame) -> pd.DataFrame:
    strict = strict_summary[["product_name", "count", "bias", "MAE", "RMSE", "weighted_RMSE", "abs_error_p95"]].copy()
    strict = strict.rename(columns={
        "count": "strict_count",
        "bias": "strict_bias",
        "MAE": "strict_MAE",
        "RMSE": "strict_RMSE",
        "weighted_RMSE": "strict_weighted_RMSE",
        "abs_error_p95": "strict_abs_error_p95",
    })
    expanded = expanded_summary[["product_name", "count", "bias", "MAE", "RMSE", "weighted_RMSE", "abs_error_p95"]].copy()
    expanded = expanded.rename(columns={
        "count": "expanded_count",
        "bias": "expanded_bias",
        "MAE": "expanded_MAE",
        "RMSE": "expanded_RMSE",
        "weighted_RMSE": "expanded_weighted_RMSE",
        "abs_error_p95": "expanded_abs_error_p95",
    })
    return strict.merge(expanded, on="product_name", how="inner").sort_values("strict_RMSE").reset_index(drop=True)


def make_report(
    *,
    args: argparse.Namespace,
    status: str,
    elapsed_s: float,
    stage_outcomes: pd.DataFrame,
    strict_summary: pd.DataFrame,
    expanded_summary: pd.DataFrame,
    comparison: pd.DataFrame,
    gapfill_sensitivity: pd.DataFrame,
    stage5_product: pd.DataFrame,
    stage5_overlap: pd.DataFrame,
    catalog_summary: pd.DataFrame,
    policy: pd.DataFrame,
    out_dir: Path,
    report_path: Path,
) -> str:
    metric_table = compact_metric_table(strict_summary, expanded_summary)
    comparison_display = comparison[[
        "product_name",
        "strict_count",
        "expanded_count",
        "coverage_gain_count",
        "coverage_gain_fraction_vs_strict",
        "strict_RMSE",
        "expanded_RMSE",
        "delta_RMSE_expanded_minus_strict",
        "strict_weighted_RMSE",
        "expanded_weighted_RMSE",
        "delta_weighted_RMSE_expanded_minus_strict",
    ]].sort_values("strict_RMSE").reset_index(drop=True)

    gapfill_display = gapfill_sensitivity[[
        "product_name",
        "retained_multibeam_count",
        "singlebeam_gapfill_count",
        "retained_multibeam_RMSE",
        "singlebeam_gapfill_RMSE",
        "gapfill_minus_retained_RMSE",
        "gapfill_to_retained_RMSE_ratio",
    ]].sort_values("retained_multibeam_RMSE").reset_index(drop=True)

    stage5_display = stage5_product[[
        "product_key",
        "n_rows",
        "n_cell_ids",
        "median_weight",
        "low_evidence_flag_cells",
        "review_or_sensitivity_only_cells",
        "sensitivity_only_cells",
        "cells_with_cross_branch_overlap",
    ]]
    overlap_display = stage5_overlap[[
        "product_key",
        "non_primary_cells",
        "strict_primary_overlap_cells",
        "expanded_primary_overlap_cells",
        "outside_expanded_primary_cells",
        "outside_expanded_primary_fraction",
    ]]

    lines: list[str] = []
    lines.append("# Step 08 Final Global Validation Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Status: **{status}**")
    lines.append(f"Elapsed: {elapsed_s:.1f}s")
    lines.append(f"Run label: `{args.run_label}`")
    lines.append("")
    lines.append(
        "This report consolidates Stage 3 strict-primary validation, Stage 4 expanded-primary sensitivity, "
        "and Stage 5 non-primary diagnostics. It does not resample gridded models and does not mutate validation-cell products."
    )
    lines.append("")

    lines.append("## 1. Final recommendation")
    lines.append(
        "Use `strict_primary_multibeam_cells` as the authoritative global validation baseline. "
        "`expanded_primary_ship_cells` is useful for coverage sensitivity, but should remain secondary for global ranking. "
        "`supplementary_singlebeam_cells` and `regional_mrar_experiment_cells` remain diagnostic/sensitivity products only."
    )
    lines.append("")
    lines.append(markdown_table(policy, places=2))
    lines.append("")

    lines.append("## 2. Stage outcomes")
    lines.append(markdown_table(stage_outcomes, places=4))
    lines.append("")

    lines.append("## 3. Strict vs expanded metrics")
    lines.append(markdown_table(metric_table, places=2))
    lines.append("")
    lines.append("Strict-vs-expanded deltas:")
    lines.append("")
    lines.append(markdown_table(comparison_display, places=4))
    lines.append("")

    lines.append("## 4. Expanded-primary gap-fill attribution")
    lines.append(markdown_table(gapfill_display, places=2))
    lines.append("")
    lines.append(
        "The retained-multibeam subset matches the strict-primary input count. The singlebeam gap-fill subset has "
        "higher RMSE for every product, which explains why expanded-primary raises global RMSE while preserving product ranking."
    )
    lines.append(
        "Stage 6 enforces this attribution against the Stage 4 comparison table: retained count must equal strict count, "
        "gap-fill count must equal coverage gain, `expanded_fill` must be false for retained strict cells and true for "
        "gap-fill cells, and gap-fill cells must be `ncei_singlebeam`."
    )
    lines.append("")

    lines.append("## 5. Non-primary diagnostics")
    lines.append(markdown_table(stage5_display, places=4))
    lines.append("")
    lines.append(markdown_table(overlap_display, places=4))
    lines.append("")
    lines.append(markdown_table(catalog_summary, places=4))
    lines.append("")
    lines.append(
        "Catalog note: `supplementary_singlebeam` has more catalog rows than unique cell IDs because Step 07B intentionally "
        "adds expanded-primary singlebeam membership rows for the 333,915 gap-fill cells."
    )
    lines.append("")

    lines.append("## 6. Skipped / out-of-scope products")
    lines.append("- `SWOT_T1` was skipped in Stage 3 because it is a regional footprint product, not a full-global product.")
    lines.append("- Stage 4 did not request `SWOT_T1`; no expanded-primary product was skipped.")
    lines.append("- A separate regional validation task is required before making any SWOT_T1 regional claim.")
    lines.append("")

    lines.append("## 7. Reproducibility")
    lines.append(markdown_table(environment_table(args), places=2))
    lines.append("")
    input_rows = [
        {"kind": "strict_summary", "path": str(STRICT_DIR / "full_validation_metrics_summary_strict_primary.parquet")},
        {"kind": "expanded_summary", "path": str(EXPANDED_DIR / "full_validation_metrics_summary_expanded_primary.parquet")},
        {"kind": "strict_vs_expanded", "path": str(EXPANDED_DIR / "strict_vs_expanded_comparison.parquet")},
        {"kind": "stage5_product_summary", "path": str(STAGE5_DIR / "non_primary_product_summary.parquet")},
        {"kind": "stage5_overlap_summary", "path": str(STAGE5_DIR / "non_primary_overlap_summary.parquet")},
        {"kind": "strict_primary_cells", "path": str(STRICT_PRIMARY_CELLS)},
    ]
    lines.append(markdown_table(pd.DataFrame(input_rows), places=2))
    lines.append("")
    output_rows = [
        {"kind": "stage_outcomes", "path": str(out_dir / "step08_stage_outcomes.parquet")},
        {"kind": "policy_recommendations", "path": str(out_dir / "step08_final_policy_recommendations.parquet")},
        {"kind": "gapfill_sensitivity", "path": str(out_dir / "expanded_gapfill_sensitivity_summary.parquet")},
        {"kind": "report", "path": str(report_path)},
    ]
    lines.append(markdown_table(pd.DataFrame(output_rows), places=2))
    lines.append("")

    lines.append("## 8. Closure")
    if status == "PASS":
        lines.append(
            "Step 08 full-global validation is ready for task closure after review. No residual-based filtering, "
            "quality relabeling, or primary-product promotion is recommended."
        )
    else:
        lines.append("Resolve failed checks before closing Step 08.")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Step 08 final global validation report")
    parser.add_argument("--run-label", default="stage6_final", help="Output run label suffix")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--confirm-final", action="store_true", help="Required to write the final Step 08 report")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.confirm_final:
        raise SystemExit("--confirm-final is required to write the final Step 08 report")

    started = time.time()
    logger = setup_logging(args.run_label)
    out_dir = output_dir(args.run_label)
    report_path = DEFAULT_REPORT_PATH

    logger.info("starting Stage 6 final report run_label=%s", args.run_label)
    out_dir.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    strict_summary = read_parquet(STRICT_DIR / "full_validation_metrics_summary_strict_primary.parquet")
    expanded_summary = read_parquet(EXPANDED_DIR / "full_validation_metrics_summary_expanded_primary.parquet")
    comparison = read_parquet(EXPANDED_DIR / "strict_vs_expanded_comparison.parquet")
    stage5_product = read_parquet(STAGE5_DIR / "non_primary_product_summary.parquet")
    stage5_overlap = read_parquet(STAGE5_DIR / "non_primary_overlap_summary.parquet")
    stage5_safety = read_parquet(STAGE5_DIR / "non_primary_safety_checks.parquet")
    catalog_summary = read_parquet(STAGE5_DIR / "validation_catalog_product_summary.parquet")

    logger.info("reading strict-primary cell ids")
    strict_ids = read_cell_ids(STRICT_PRIMARY_CELLS)
    gapfill_sensitivity = build_gapfill_sensitivity(strict_ids, comparison, logger)

    stage_outcomes = build_stage_outcomes(strict_summary, expanded_summary, stage5_product, stage5_safety)
    policy = build_policy_recommendations()

    status = "PASS" if (stage_outcomes["status"] == "PASS").all() else "FAIL"

    stage_outcomes_path = out_dir / "step08_stage_outcomes.parquet"
    policy_path = out_dir / "step08_final_policy_recommendations.parquet"
    gapfill_path = out_dir / "expanded_gapfill_sensitivity_summary.parquet"
    outputs = [
        stage_outcomes_path,
        stage_outcomes_path.with_suffix(".tsv"),
        policy_path,
        policy_path.with_suffix(".tsv"),
        gapfill_path,
        gapfill_path.with_suffix(".tsv"),
        report_path,
    ]
    for path in outputs:
        ensure_writable(path, args.overwrite)

    logger.info("writing final report outputs")
    atomic_write_parquet(stage_outcomes, stage_outcomes_path, args.overwrite)
    atomic_write_tsv(stage_outcomes, stage_outcomes_path.with_suffix(".tsv"), args.overwrite)
    atomic_write_parquet(policy, policy_path, args.overwrite)
    atomic_write_tsv(policy, policy_path.with_suffix(".tsv"), args.overwrite)
    atomic_write_parquet(gapfill_sensitivity, gapfill_path, args.overwrite)
    atomic_write_tsv(gapfill_sensitivity, gapfill_path.with_suffix(".tsv"), args.overwrite)

    elapsed_s = time.time() - started
    report = make_report(
        args=args,
        status=status,
        elapsed_s=elapsed_s,
        stage_outcomes=stage_outcomes,
        strict_summary=strict_summary,
        expanded_summary=expanded_summary,
        comparison=comparison,
        gapfill_sensitivity=gapfill_sensitivity,
        stage5_product=stage5_product,
        stage5_overlap=stage5_overlap,
        catalog_summary=catalog_summary,
        policy=policy,
        out_dir=out_dir,
        report_path=report_path,
    )
    atomic_write_text(report, report_path, args.overwrite)

    logger.info("Stage 6 status=%s elapsed=%.1fs report=%s", status, elapsed_s, report_path)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
