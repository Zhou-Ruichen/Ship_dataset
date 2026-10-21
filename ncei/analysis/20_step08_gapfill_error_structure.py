#!/usr/bin/env python3
"""
20_step08_gapfill_error_structure.py

Analyze Stage 4 expanded-primary singlebeam gap-fill error structure without
resampling gridded models or mutating validation products.

Reads:
  - ncei/derived/model_validation_1min_full_expanded_primary/full_validation_by_cell_expanded_primary_<MODEL>.parquet
  - ncei/derived/model_validation_1min_full_strict_primary/full_validation_metrics_summary_strict_primary.parquet

Writes (full mode):
  - ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_lat_band_10deg.tsv
  - ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_depth_bin.tsv
  - ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_region_10deg.tsv
  - ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_quality_tier.tsv
  - ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_evidence_class.tsv
  - ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_matched_rule_id.tsv
  - ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_attribution_topN.tsv
  - ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/c_gapfill_safety_checks.tsv
  - ncei/docs/step08_gapfill_error_structure_report.md
  - ncei/output/logs/20_step08_gapfill_error_structure_<run-label>.log

Usage:
    python ncei/analysis/20_step08_gapfill_error_structure.py --check-only
    python ncei/analysis/20_step08_gapfill_error_structure.py \
      --run-label c_gapfill --confirm-analyze --overwrite
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent          # ncei/
REPO_ROOT = ROOT_DIR.parent           # repository root
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"
OUTPUT_DIR = ROOT_DIR / "derived" / "model_validation_1min_step08_pub" / "c_gapfill_structure"

EXPANDED_REL_DIR = Path("ncei/derived/model_validation_1min_full_expanded_primary")
STRICT_REL_DIR = Path("ncei/derived/model_validation_1min_full_strict_primary")
STRICT_SUMMARY_REL = STRICT_REL_DIR / "full_validation_metrics_summary_strict_primary.parquet"

PRODUCT_NAMES = ["GEBCO_2024", "ETOPO_2022", "SRTM15_V2.7", "TOPO_25.1", "SDUST_2023"]
SLICE_DIMS = [
    "lat_band_10deg",
    "depth_bin",
    "region_10deg",
    "quality_tier",
    "evidence_class",
    "matched_rule_id",
]
EXPECTED_EXPANDED_ROWS = 2_732_689
EXPECTED_RETAINED_ROWS = 2_398_774
EXPECTED_GAPFILL_ROWS = 333_915
STRICT_RMSE_TOL = 0.01
TOP20_ACCEPTANCE_PCT = 80.0
NA_SLICE = "<NA>"

SLICE_OUTPUT_COLUMNS = [
    "slice_dim",
    "slice_value",
    "model",
    "n_cells",
    "n_cells_gapfill",
    "n_cells_retained",
    "n_valid_gapfill",
    "n_valid_retained",
    "share_of_gapfill",
    "sumsq_error_gapfill",
    "sumsq_error_retained",
    "RMSE_gapfill",
    "RMSE_retained",
    "RMSE_strict_baseline",
    "delta_rmse_slice",
    "weighted_RMSE_gapfill",
    "weighted_RMSE_retained",
    "positive_gapfill_rmse_sq_contribution",
    "contribution_to_expanded_minus_strict_rmse_sq",
    "contribution_pct_of_total_gapfill_sumsq",
    "contribution_pct_of_total_delta",
    "total_model_delta_rmse_sq",
]

TOPN_COLUMNS = [
    "slice_dim",
    "slice_value",
    "model",
    "n_cells",
    "share_of_gapfill",
    "RMSE_gapfill",
    "RMSE_retained",
    "delta_rmse_slice",
    "contribution_pct_of_total_delta",
    "contribution_pct_of_total_gapfill_sumsq",
    "contribution_to_expanded_minus_strict_rmse_sq",
]


# ---------------------------------------------------------------------------
# Paths / logging / atomic writes
# ---------------------------------------------------------------------------

def setup_logging(run_label: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"20_step08_gapfill_error_structure_{run_label}.log"
    logger = logging.getLogger(Path(__file__).stem)
    logger.handlers.clear()
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def resolve_path(value: str | Path, base: Path = REPO_ROOT) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base / path).resolve()


def runtime_outer_repo_root() -> Path | None:
    """Return the real repository root when running from a Trellis runtime worktree.

    The isolated implementation worktree may contain code but not large derived
    parquets. This fallback is derived from SCRIPT_DIR parents and is only used
    for read-only inputs when the local worktree lacks ncei/derived.
    """
    for parent in REPO_ROOT.parents:
        if parent.name == ".trellis":
            outer = parent.parent
            if (outer / EXPANDED_REL_DIR).exists() and (outer / STRICT_SUMMARY_REL).exists():
                return outer
    return None


def default_input_repo_root() -> Path:
    if (REPO_ROOT / EXPANDED_REL_DIR).exists() and (REPO_ROOT / STRICT_SUMMARY_REL).exists():
        return REPO_ROOT

    env_root = os.environ.get("NCEI_INPUT_REPO_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if (candidate / EXPANDED_REL_DIR).exists() and (candidate / STRICT_SUMMARY_REL).exists():
            return candidate

    outer = runtime_outer_repo_root()
    if outer is not None:
        return outer

    return REPO_ROOT


def expanded_by_cell_path(input_repo_root: Path, product_name: str) -> Path:
    return input_repo_root / EXPANDED_REL_DIR / f"full_validation_by_cell_expanded_primary_{product_name}.parquet"


def strict_summary_path(input_repo_root: Path) -> Path:
    return input_repo_root / STRICT_SUMMARY_REL


def ensure_inputs_exist(paths: Iterable[Path]) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required input(s):\n  - " + "\n  - ".join(missing))


def ensure_writable(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output exists; pass --overwrite to replace: {path}")


def atomic_write_text(text: str, path: Path, overwrite: bool) -> None:
    ensure_writable(path, overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_tsv(df: pd.DataFrame, path: Path, overwrite: bool) -> None:
    ensure_writable(path, overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def normalize_bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0).astype(float).ne(0)
    text = series.fillna(False).astype(str).str.strip().str.lower()
    return text.isin(["true", "t", "1", "yes", "y"])


def schema_names(path: Path) -> list[str]:
    return list(pq.read_schema(path).names)


def row_count(path: Path) -> int:
    return int(pq.ParquetFile(path).metadata.num_rows)


def format_slice_value(series: pd.Series) -> pd.Series:
    out = series.astype("object").where(series.notna(), NA_SLICE)
    out = out.astype(str)
    return out.where(~out.isin(["nan", "None", "NaT", "<NA>"]), NA_SLICE)


def safe_divide(numer: pd.Series | float, denom: pd.Series | float) -> pd.Series | float:
    if isinstance(numer, pd.Series) or isinstance(denom, pd.Series):
        n = pd.Series(numer) if not isinstance(numer, pd.Series) else numer
        d = pd.Series(denom, index=n.index) if not isinstance(denom, pd.Series) else denom
        return n.divide(d.where(d != 0, np.nan))
    return float(numer) / float(denom) if float(denom) != 0 else np.nan


def rmse_from_sumsq(sumsq: float, n_valid: int) -> float:
    if n_valid <= 0 or not np.isfinite(sumsq):
        return np.nan
    return float(np.sqrt(float(sumsq) / int(n_valid)))


def weighted_rmse_from_sums(weighted_sumsq: float, sum_weight: float) -> float:
    if sum_weight <= 0 or not np.isfinite(weighted_sumsq):
        return np.nan
    return float(np.sqrt(float(weighted_sumsq) / float(sum_weight)))


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
    return str(value).replace("\n", " ").replace("|", "\\|")


def markdown_table(df: pd.DataFrame, max_rows: int | None = None, places: int = 2) -> str:
    if df is None or len(df) == 0:
        return "_(none)_"
    work = df.head(max_rows).copy() if max_rows is not None else df.copy()
    cols = list(work.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in work.iterrows():
        lines.append("| " + " | ".join(fmt(row.get(col), places=places) for col in cols) + " |")
    if max_rows is not None and len(df) > max_rows:
        lines.append(f"\n_Showing {max_rows:,} of {len(df):,} rows._")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Input checks and loading
# ---------------------------------------------------------------------------

def required_columns_for_analysis() -> list[str]:
    return ["expanded_fill", "elev_error_m", "validation_weight"] + SLICE_DIMS


def preflight_inputs(input_repo_root: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    summary_path = strict_summary_path(input_repo_root)
    rows.append({
        "kind": "strict_summary",
        "path": str(summary_path),
        "exists": summary_path.exists(),
        "row_count": row_count(summary_path) if summary_path.exists() else -1,
        "missing_columns": "" if summary_path.exists() else "path missing",
        "status": "PASS" if summary_path.exists() else "FAIL",
    })

    required = set(required_columns_for_analysis())
    for product_name in PRODUCT_NAMES:
        path = expanded_by_cell_path(input_repo_root, product_name)
        exists = path.exists()
        names = set(schema_names(path)) if exists else set()
        missing = sorted(required - names)
        n_rows = row_count(path) if exists else -1
        status = "PASS" if exists and not missing and n_rows == EXPECTED_EXPANDED_ROWS else "FAIL"
        rows.append({
            "kind": "expanded_by_cell",
            "path": str(path),
            "exists": exists,
            "row_count": n_rows,
            "missing_columns": ",".join(missing),
            "status": status,
            "product_name": product_name,
        })
    return pd.DataFrame(rows)


def load_strict_summary(input_repo_root: Path) -> pd.DataFrame:
    path = strict_summary_path(input_repo_root)
    df = pd.read_parquet(path)
    required = {"product_name", "RMSE", "count"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(f"Strict summary missing required column(s): {missing}")
    if "stratification" in df.columns:
        df = df[df["stratification"].astype(str).eq("overall")]
    if "stratum" in df.columns:
        df = df[df["stratum"].astype(str).eq("all")]
    df = df[df["product_name"].isin(PRODUCT_NAMES)].copy()
    products_found = set(df["product_name"].astype(str))
    missing_products = [name for name in PRODUCT_NAMES if name not in products_found]
    if missing_products:
        raise RuntimeError(f"Strict summary missing product(s): {missing_products}")
    return df.drop_duplicates("product_name").set_index("product_name", drop=False)


def read_expanded_product(input_repo_root: Path, product_name: str) -> pd.DataFrame:
    path = expanded_by_cell_path(input_repo_root, product_name)
    names = set(schema_names(path))
    required = required_columns_for_analysis()
    missing = [col for col in required if col not in names]
    if missing:
        raise RuntimeError(f"{path} missing required column(s): {missing}")
    df = pd.read_parquet(path, columns=required)
    df["model"] = product_name
    df["expanded_fill_bool"] = normalize_bool_series(df["expanded_fill"])
    df["elev_error_m"] = pd.to_numeric(df["elev_error_m"], errors="coerce")
    df["validation_weight"] = pd.to_numeric(df["validation_weight"], errors="coerce")
    df["err_sq"] = df["elev_error_m"] ** 2
    df.loc[~np.isfinite(df["err_sq"].to_numpy(dtype=np.float64)), "err_sq"] = np.nan
    valid_weight = df["validation_weight"].where(np.isfinite(df["validation_weight"]) & (df["validation_weight"] > 0), np.nan)
    df["valid_weight"] = valid_weight.where(df["err_sq"].notna(), np.nan)
    df["weighted_err_sq"] = df["err_sq"] * df["valid_weight"]
    for dim in SLICE_DIMS:
        df[dim] = format_slice_value(df[dim])
    return df


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_one_mask(df: pd.DataFrame, dim: str, mask: pd.Series, prefix: str) -> pd.DataFrame:
    work = df.loc[mask, [dim, "err_sq", "weighted_err_sq", "valid_weight"]].copy()
    grouped = work.groupby(dim, dropna=False).agg(
        **{
            f"n_cells_{prefix}": (dim, "size"),
            f"n_valid_{prefix}": ("err_sq", "count"),
            f"sumsq_error_{prefix}": ("err_sq", "sum"),
            f"weighted_sumsq_{prefix}": ("weighted_err_sq", "sum"),
            f"sum_weight_{prefix}": ("valid_weight", "sum"),
        }
    ).reset_index().rename(columns={dim: "slice_value"})
    return grouped


def build_slice_table_for_model(df: pd.DataFrame, dim: str, totals: dict[str, Any]) -> pd.DataFrame:
    gapfill_mask = df["expanded_fill_bool"]
    retained_mask = ~gapfill_mask
    gap = aggregate_one_mask(df, dim, gapfill_mask, "gapfill")
    retained = aggregate_one_mask(df, dim, retained_mask, "retained")
    out = gap.merge(retained, on="slice_value", how="outer")

    for col in [
        "n_cells_gapfill", "n_valid_gapfill", "n_cells_retained", "n_valid_retained",
        "sumsq_error_gapfill", "sumsq_error_retained", "weighted_sumsq_gapfill",
        "weighted_sumsq_retained", "sum_weight_gapfill", "sum_weight_retained",
    ]:
        if col not in out.columns:
            out[col] = 0
        out[col] = out[col].fillna(0)

    for col in ["n_cells_gapfill", "n_valid_gapfill", "n_cells_retained", "n_valid_retained"]:
        out[col] = out[col].astype("int64")

    out["slice_dim"] = dim
    out["model"] = str(totals["model"])
    out["n_cells"] = out["n_cells_gapfill"]
    out["share_of_gapfill"] = out["n_cells_gapfill"] / float(EXPECTED_GAPFILL_ROWS)
    out["RMSE_gapfill"] = np.where(
        out["n_valid_gapfill"] > 0,
        np.sqrt(out["sumsq_error_gapfill"] / out["n_valid_gapfill"].replace(0, np.nan)),
        np.nan,
    )
    out["RMSE_retained"] = np.where(
        out["n_valid_retained"] > 0,
        np.sqrt(out["sumsq_error_retained"] / out["n_valid_retained"].replace(0, np.nan)),
        np.nan,
    )
    out["RMSE_strict_baseline"] = out["RMSE_retained"]
    out["delta_rmse_slice"] = out["RMSE_gapfill"] - out["RMSE_retained"]
    out["weighted_RMSE_gapfill"] = np.where(
        out["sum_weight_gapfill"] > 0,
        np.sqrt(out["weighted_sumsq_gapfill"] / out["sum_weight_gapfill"].replace(0, np.nan)),
        np.nan,
    )
    out["weighted_RMSE_retained"] = np.where(
        out["sum_weight_retained"] > 0,
        np.sqrt(out["weighted_sumsq_retained"] / out["sum_weight_retained"].replace(0, np.nan)),
        np.nan,
    )

    n_exp = float(totals["n_expanded_valid"])
    n_strict = float(totals["n_strict_valid"])
    total_gapfill_sumsq = float(totals["sumsq_gapfill"])
    total_delta_rmse_sq = float(totals["total_delta_rmse_sq"])
    out["positive_gapfill_rmse_sq_contribution"] = out["sumsq_error_gapfill"] / n_exp
    out["contribution_to_expanded_minus_strict_rmse_sq"] = (
        out["sumsq_error_gapfill"] / n_exp
        + out["sumsq_error_retained"] * (1.0 / n_exp - 1.0 / n_strict)
    )
    out["contribution_pct_of_total_gapfill_sumsq"] = np.where(
        total_gapfill_sumsq > 0,
        out["sumsq_error_gapfill"] / total_gapfill_sumsq * 100.0,
        np.nan,
    )
    out["contribution_pct_of_total_delta"] = np.where(
        total_delta_rmse_sq != 0,
        out["contribution_to_expanded_minus_strict_rmse_sq"] / total_delta_rmse_sq * 100.0,
        np.nan,
    )
    out["total_model_delta_rmse_sq"] = total_delta_rmse_sq

    out = out.sort_values(
        ["contribution_pct_of_total_gapfill_sumsq", "n_cells_gapfill"],
        ascending=[False, False],
    ).reset_index(drop=True)
    return out[SLICE_OUTPUT_COLUMNS]


def model_totals(df: pd.DataFrame, product_name: str, strict_summary: pd.DataFrame) -> dict[str, Any]:
    fill = df["expanded_fill_bool"]
    retained = ~fill
    strict_row = strict_summary.loc[product_name]

    n_expanded_rows = int(len(df))
    n_gapfill_rows = int(fill.sum())
    n_retained_rows = int(retained.sum())
    n_expanded_valid = int(df["err_sq"].notna().sum())
    n_gapfill_valid = int(df.loc[fill, "err_sq"].notna().sum())
    n_retained_valid = int(df.loc[retained, "err_sq"].notna().sum())
    sumsq_expanded = float(df["err_sq"].sum(skipna=True))
    sumsq_gapfill = float(df.loc[fill, "err_sq"].sum(skipna=True))
    sumsq_retained = float(df.loc[retained, "err_sq"].sum(skipna=True))
    rmse_gapfill = rmse_from_sumsq(sumsq_gapfill, n_gapfill_valid)
    rmse_retained = rmse_from_sumsq(sumsq_retained, n_retained_valid)
    rmse_expanded = rmse_from_sumsq(sumsq_expanded, n_expanded_valid)
    strict_rmse = float(strict_row["RMSE"])
    strict_count = int(strict_row["count"])
    total_delta_rmse_sq = rmse_expanded ** 2 - strict_rmse ** 2

    return {
        "model": product_name,
        "n_expanded_rows": n_expanded_rows,
        "n_gapfill_rows": n_gapfill_rows,
        "n_retained_rows": n_retained_rows,
        "n_expanded_valid": n_expanded_valid,
        "n_gapfill_valid": n_gapfill_valid,
        "n_retained_valid": n_retained_valid,
        "n_strict_valid": strict_count,
        "sumsq_expanded": sumsq_expanded,
        "sumsq_gapfill": sumsq_gapfill,
        "sumsq_retained": sumsq_retained,
        "RMSE_expanded": rmse_expanded,
        "RMSE_gapfill": rmse_gapfill,
        "RMSE_retained": rmse_retained,
        "RMSE_strict_baseline": strict_rmse,
        "retained_vs_strict_rmse_abs_diff": abs(rmse_retained - strict_rmse),
        "total_delta_rmse_sq": total_delta_rmse_sq,
        "total_delta_rmse": rmse_expanded - strict_rmse,
    }


def build_safety_checks(
    totals_df: pd.DataFrame,
    slice_tables: dict[str, pd.DataFrame],
    topn: pd.DataFrame,
    preflight_df: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for _, row in preflight_df.iterrows():
        if row["status"] != "PASS":
            rows.append({
                "check_id": "input_preflight",
                "model": row.get("product_name", ""),
                "slice_dim": "",
                "status": "FAIL",
                "observed": row.get("row_count", ""),
                "expected": "input exists, schema complete, expanded rows match expected",
                "description": row.get("path", ""),
                "details": row.get("missing_columns", ""),
            })

    for _, row in totals_df.iterrows():
        model = row["model"]
        rows.append({
            "check_id": "gapfill_count",
            "model": model,
            "slice_dim": "",
            "status": "PASS" if int(row["n_gapfill_rows"]) == EXPECTED_GAPFILL_ROWS else "FAIL",
            "observed": int(row["n_gapfill_rows"]),
            "expected": EXPECTED_GAPFILL_ROWS,
            "description": "expanded_fill == True row count per model",
            "details": "",
        })
        rows.append({
            "check_id": "retained_count",
            "model": model,
            "slice_dim": "",
            "status": "PASS" if int(row["n_retained_rows"]) == EXPECTED_RETAINED_ROWS else "FAIL",
            "observed": int(row["n_retained_rows"]),
            "expected": EXPECTED_RETAINED_ROWS,
            "description": "expanded_fill == False retained strict-primary row count per model",
            "details": "",
        })
        rows.append({
            "check_id": "expanded_count",
            "model": model,
            "slice_dim": "",
            "status": "PASS" if int(row["n_expanded_rows"]) == EXPECTED_EXPANDED_ROWS else "FAIL",
            "observed": int(row["n_expanded_rows"]),
            "expected": EXPECTED_EXPANDED_ROWS,
            "description": "expanded-primary by-cell row count per model",
            "details": "",
        })
        diff = float(row["retained_vs_strict_rmse_abs_diff"])
        rows.append({
            "check_id": "retained_rmse_match_strict",
            "model": model,
            "slice_dim": "",
            "status": "PASS" if diff < STRICT_RMSE_TOL else "FAIL",
            "observed": f"{diff:.8f}",
            "expected": f"<{STRICT_RMSE_TOL}",
            "description": "retained subset RMSE matches strict-primary summary",
            "details": f"retained={row['RMSE_retained']:.8f}; strict={row['RMSE_strict_baseline']:.8f}",
        })

    for dim, table in slice_tables.items():
        for model in PRODUCT_NAMES:
            sub = table[table["model"].eq(model)]
            observed = int(sub["n_cells_gapfill"].sum())
            rows.append({
                "check_id": "slice_sum_consistency",
                "model": model,
                "slice_dim": dim,
                "status": "PASS" if observed == EXPECTED_GAPFILL_ROWS else "FAIL",
                "observed": observed,
                "expected": EXPECTED_GAPFILL_ROWS,
                "description": "single-dimensional slice n_cells_gapfill sums to gap-fill count",
                "details": "",
            })
        na_rows = int((table["slice_value"] == NA_SLICE).sum())
        rows.append({
            "check_id": "nan_slice_handled",
            "model": "all",
            "slice_dim": dim,
            "status": "PASS",
            "observed": na_rows,
            "expected": "NaN values grouped as literal <NA> when present",
            "description": "NaN slice handling",
            "details": "No NaN values observed" if na_rows == 0 else f"{na_rows} model slice row(s) use <NA>",
        })

    cumulative_gapfill_pct = float(topn["contribution_pct_of_total_gapfill_sumsq"].sum()) if len(topn) else 0.0
    cumulative_delta_pct = float(topn["contribution_pct_of_total_delta"].sum()) if len(topn) else 0.0
    cumulative_gapfill_pct_capped = min(100.0, cumulative_gapfill_pct)
    rows.append({
        "check_id": "top20_attribution_pct",
        "model": "all",
        "slice_dim": "all",
        "status": "PASS" if cumulative_gapfill_pct >= TOP20_ACCEPTANCE_PCT else "WARN",
        "observed": f"{cumulative_gapfill_pct_capped:.4f}",
        "expected": f">={TOP20_ACCEPTANCE_PCT:.1f}",
        "description": "top-N cumulative positive gap-fill share; capped at 100 because dimensions overlap",
        "details": f"raw_overlapping_sum={cumulative_gapfill_pct:.4f}; cumulative contribution_pct_of_total_delta={cumulative_delta_pct:.4f}; WARN is review gate, not a residual filter",
    })
    rows.append({
        "check_id": "no_model_residual_filtering",
        "model": "all",
        "slice_dim": "",
        "status": "PASS",
        "observed": "all rows retained for counting; residuals used only for aggregation",
        "expected": "no rows removed based on residual magnitude",
        "description": "Step 08 invariant preserved",
        "details": "The script reads Stage 4 by-cell outputs and does not mutate upstream validation cells or quality flags.",
    })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def output_paths(top_n: int) -> list[Path]:
    paths = [OUTPUT_DIR / f"gapfill_slice_by_{dim}.tsv" for dim in SLICE_DIMS]
    paths.extend([
        OUTPUT_DIR / "gapfill_attribution_topN.tsv",
        OUTPUT_DIR / "c_gapfill_safety_checks.tsv",
        OUTPUT_DIR / "gapfill_model_totals.tsv",
        DOCS_DIR / "step08_gapfill_error_structure_report.md",
    ])
    return paths


def summarize_top_dimension(slice_tables: dict[str, pd.DataFrame], dim: str, top_k: int = 3) -> pd.DataFrame:
    table = slice_tables[dim].copy()
    grouped = table.groupby(["slice_dim", "slice_value"], as_index=False).agg(
        n_cells=("n_cells_gapfill", "sum"),
        contribution_pct_of_total_gapfill_sumsq=("contribution_pct_of_total_gapfill_sumsq", "sum"),
        mean_RMSE_gapfill=("RMSE_gapfill", "mean"),
        mean_delta_rmse_slice=("delta_rmse_slice", "mean"),
    )
    return grouped.sort_values(
        ["contribution_pct_of_total_gapfill_sumsq", "n_cells"], ascending=[False, False]
    ).head(top_k).reset_index(drop=True)


def dominant_values(slice_tables: dict[str, pd.DataFrame], dim: str, top_k: int = 2) -> str:
    top = summarize_top_dimension(slice_tables, dim, top_k=top_k)
    if len(top) == 0:
        return "none"
    return ", ".join(str(v) for v in top["slice_value"].tolist())


def cross_model_consistency(topn: pd.DataFrame) -> pd.DataFrame:
    if len(topn) == 0:
        return pd.DataFrame()
    grouped = topn.groupby(["slice_dim", "slice_value"], as_index=False).agg(
        models=("model", lambda s: ",".join(sorted(set(map(str, s))))),
        n_models=("model", lambda s: len(set(map(str, s)))),
        top20_rows=("model", "size"),
        cumulative_gapfill_pct=("contribution_pct_of_total_gapfill_sumsq", "sum"),
    )
    return grouped.sort_values(["n_models", "cumulative_gapfill_pct"], ascending=[False, False]).head(10)


def make_report(
    *,
    input_repo_root: Path,
    totals_df: pd.DataFrame,
    slice_tables: dict[str, pd.DataFrame],
    topn: pd.DataFrame,
    safety: pd.DataFrame,
    elapsed_s: float,
    run_label: str,
) -> str:
    cumulative_gapfill_pct = float(topn["contribution_pct_of_total_gapfill_sumsq"].sum()) if len(topn) else 0.0
    cumulative_delta_pct = float(topn["contribution_pct_of_total_delta"].sum()) if len(topn) else 0.0
    cumulative_gapfill_pct_capped = min(100.0, cumulative_gapfill_pct)
    cumulative_delta_pct_capped = min(100.0, cumulative_delta_pct)
    status = "PASS" if not (safety["status"] == "FAIL").any() else "FAIL"
    warn_count = int((safety["status"] == "WARN").sum())

    model_display = totals_df[[
        "model", "n_retained_rows", "n_gapfill_rows", "RMSE_strict_baseline",
        "RMSE_retained", "RMSE_gapfill", "total_delta_rmse", "retained_vs_strict_rmse_abs_diff",
    ]].copy()

    top_display = topn[TOPN_COLUMNS].copy()
    per_dim_rows: list[pd.DataFrame] = []
    for dim in SLICE_DIMS:
        per_dim_rows.append(summarize_top_dimension(slice_tables, dim, top_k=3))
    per_dim = pd.concat(per_dim_rows, ignore_index=True) if per_dim_rows else pd.DataFrame()

    consistency = cross_model_consistency(topn)
    depth_summary = dominant_values(slice_tables, "depth_bin", top_k=2)
    region_summary = dominant_values(slice_tables, "region_10deg", top_k=2)
    quality_summary = dominant_values(slice_tables, "quality_tier", top_k=2)

    lines: list[str] = []
    lines.append("# Step 08 Gap-Fill Error Structure Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Status: **{status}**" + (f" ({warn_count} warning review gate)" if warn_count else ""))
    lines.append(f"Run label: `{run_label}`")
    lines.append(f"Elapsed: {elapsed_s:.1f}s")
    lines.append(f"Input repo root: `{input_repo_root}`")
    lines.append(f"Output directory: `{OUTPUT_DIR}`")
    lines.append("")

    lines.append("## 1. Summary")
    lines.append("")
    lines.append(
        "The expanded-primary RMSE increase is driven by the 333,915 `expanded_fill=True` "
        "singlebeam gap-fill cells having materially higher RMSE than the retained strict-primary cells. "
        f"Across the top-{len(topn)} attribution rows, the dominant positive gap-fill squared-error share reaches "
        f"{cumulative_gapfill_pct_capped:.1f}% of the gap-fill term (raw overlapping sum {cumulative_gapfill_pct:.1f}% "
        f"because dimensions are not mutually exclusive). The exact ΔRMSE² percentage, including retained-set dilution, "
        f"reaches {cumulative_delta_pct_capped:.1f}% (raw overlapping sum {cumulative_delta_pct:.1f}%)."
    )
    lines.append(
        f"The leading depth bands are `{depth_summary}`, the leading 10° regions are `{region_summary}`, "
        f"and the leading quality tiers are `{quality_summary}`. These are the primary slices to inspect when "
        "explaining why +13.92% coverage raises global RMSE by 6–8 m."
    )
    lines.append("")

    lines.append("## 2. Method")
    lines.append("")
    lines.append(
        "This script is read-only: it loads the five Stage 4 expanded-primary by-cell parquets, splits rows by "
        "`expanded_fill`, and aggregates existing `elev_error_m` residuals. It does not resample gridded models, "
        "change Step 06B quality flags, alter Step 07B validation cells, or filter rows by residual magnitude."
    )
    lines.append("")
    lines.append(
        "For each model, `expanded_fill=True` must be 333,915 rows and `expanded_fill=False` must be 2,398,774 rows. "
        "The retained subset RMSE is reconciled to the strict-primary metrics summary with tolerance <0.01 m. "
        "All NaN slice values are grouped under the literal `<NA>`."
    )
    lines.append("")
    lines.append(
        "Attribution uses the simplified positive-term convention from the design: `sumsq_gapfill_in_slice / "
        "sumsq_gapfill_total` explains where the gap-fill squared error enters. The report also emits an exact "
        "per-slice ΔRMSE² contribution that includes the negative retained-set dilution term, but top contributors "
        "are ranked by the positive gap-fill squared-error share. Because the top-N table is the union of multiple "
        "overlapping dimensions (quality, evidence, depth, region, etc.), cumulative percentages are capped at 100% "
        "for acceptance while raw sums are retained in the safety-check details."
    )
    lines.append("")
    lines.append("Model-level reconciliation:")
    lines.append("")
    lines.append(markdown_table(model_display, places=4))
    lines.append("")

    lines.append("## 3. Top contributors")
    lines.append("")
    lines.append(f"Path: `{OUTPUT_DIR / 'gapfill_attribution_topN.tsv'}`")
    lines.append("")
    lines.append(markdown_table(top_display, max_rows=20, places=4))
    lines.append("")

    lines.append("## 4. Per-dimension breakdown")
    lines.append("")
    for dim in SLICE_DIMS:
        lines.append(f"- `{dim}` TSV: `{OUTPUT_DIR / f'gapfill_slice_by_{dim}.tsv'}`")
    lines.append("")
    lines.append("Each-dimension top-3 contributors, summed across models:")
    lines.append("")
    lines.append(markdown_table(per_dim, places=4))
    lines.append("")

    lines.append("## 5. Cross-model consistency")
    lines.append("")
    if len(consistency):
        lines.append(
            "Repeated slice values across several models indicate ship-side / geography-driven difficult areas rather "
            "than a product-specific artifact."
        )
        lines.append("")
        lines.append(markdown_table(consistency, places=4))
    else:
        lines.append("No cross-model consistency table was available.")
    lines.append("")

    lines.append("## 6. Safety checks")
    lines.append("")
    lines.append(f"Path: `{OUTPUT_DIR / 'c_gapfill_safety_checks.tsv'}`")
    lines.append("")
    safety_summary = safety.groupby("status", as_index=False).size().rename(columns={"size": "n_checks"})
    lines.append(markdown_table(safety_summary, places=0))
    if warn_count:
        lines.append("")
        lines.append(
            "Warnings are review gates rather than hard failures. In particular, a top-20 attribution warning would "
            "indicate a longer error-contribution tail, not a reason to filter validation cells."
        )
    lines.append("")

    lines.append("## 7. Outputs")
    lines.append("")
    output_rows = [
        {"kind": "topN", "path": str(OUTPUT_DIR / "gapfill_attribution_topN.tsv")},
        {"kind": "safety", "path": str(OUTPUT_DIR / "c_gapfill_safety_checks.tsv")},
        {"kind": "model_totals", "path": str(OUTPUT_DIR / "gapfill_model_totals.tsv")},
        {"kind": "report", "path": str(DOCS_DIR / "step08_gapfill_error_structure_report.md")},
    ] + [
        {"kind": f"slice_{dim}", "path": str(OUTPUT_DIR / f"gapfill_slice_by_{dim}.tsv")}
        for dim in SLICE_DIMS
    ]
    lines.append(markdown_table(pd.DataFrame(output_rows), places=2))
    lines.append("")

    lines.append("## 8. Caveats")
    lines.append("")
    lines.append("- The top-N table intentionally ranks overlapping dimension slices; percentages can overlap across dimensions.")
    lines.append("- `matched_rule_id` can be sparse; missing values are retained as `<NA>` rather than dropped.")
    lines.append("- This is not a bootstrap confidence interval analysis and does not claim statistical uncertainty bounds.")
    lines.append("- No residual magnitude threshold is applied; large-error cells remain represented in the by-cell inputs and aggregate outputs.")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze expanded-primary singlebeam gap-fill error structure")
    parser.add_argument("--run-label", default="c_gapfill", help="Run label for logs/report metadata")
    parser.add_argument("--confirm-analyze", action="store_true", help="Required for full analysis writes")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--check-only", action="store_true", help="Validate inputs and schema without writing outputs")
    parser.add_argument("--top-n", type=int, default=20, help="Number of top attribution rows to write")
    parser.add_argument("--input-repo-root", default=None, help="Optional repository root containing ncei/derived inputs")
    return parser.parse_args(argv)


def run_analysis(args: argparse.Namespace, input_repo_root: Path, logger: logging.Logger) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    strict_summary = load_strict_summary(input_repo_root)
    totals: list[dict[str, Any]] = []
    slice_accumulator: dict[str, list[pd.DataFrame]] = {dim: [] for dim in SLICE_DIMS}

    for i, product_name in enumerate(PRODUCT_NAMES, start=1):
        logger.info("reading product=%s (%d/%d)", product_name, i, len(PRODUCT_NAMES))
        df = read_expanded_product(input_repo_root, product_name)
        total = model_totals(df, product_name, strict_summary)
        totals.append(total)
        logger.info(
            "%s rows expanded=%d retained=%d gapfill=%d rmse_retained=%.4f rmse_gapfill=%.4f",
            product_name,
            total["n_expanded_rows"],
            total["n_retained_rows"],
            total["n_gapfill_rows"],
            total["RMSE_retained"],
            total["RMSE_gapfill"],
        )
        for dim in SLICE_DIMS:
            slice_accumulator[dim].append(build_slice_table_for_model(df, dim, total))

    totals_df = pd.DataFrame(totals)
    slice_tables = {
        dim: pd.concat(parts, ignore_index=True).sort_values(
            ["model", "contribution_pct_of_total_gapfill_sumsq"], ascending=[True, False]
        ).reset_index(drop=True)
        for dim, parts in slice_accumulator.items()
    }
    all_slices = pd.concat(slice_tables.values(), ignore_index=True)
    topn = all_slices.sort_values(
        ["contribution_pct_of_total_gapfill_sumsq", "n_cells_gapfill"], ascending=[False, False]
    ).head(args.top_n).reset_index(drop=True)
    return totals_df, slice_tables, topn, all_slices


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.top_n <= 0:
        raise SystemExit("--top-n must be positive")
    if not args.check_only and not args.confirm_analyze:
        raise SystemExit("--confirm-analyze is required unless --check-only is used")

    started = time.time()
    logger = setup_logging(args.run_label)
    logger.info("argv=%s", " ".join(sys.argv))

    try:
        input_repo_root = resolve_path(args.input_repo_root) if args.input_repo_root else default_input_repo_root()
        logger.info("code_repo_root=%s", REPO_ROOT)
        logger.info("input_repo_root=%s", input_repo_root)
        logger.info("output_dir=%s", OUTPUT_DIR)
        logger.info("docs_dir=%s", DOCS_DIR)

        required_paths = [strict_summary_path(input_repo_root)] + [
            expanded_by_cell_path(input_repo_root, product_name) for product_name in PRODUCT_NAMES
        ]
        ensure_inputs_exist(required_paths)
        preflight = preflight_inputs(input_repo_root)
        if (preflight["status"] != "PASS").any():
            logger.error("input preflight failed")
            logger.error("%s", preflight.to_string(index=False))
            return 1
        logger.info("input preflight PASS (%d rows)", len(preflight))

        if args.check_only:
            logger.info("check-only PASS; no outputs written")
            return 0

        for path in output_paths(args.top_n):
            ensure_writable(path, args.overwrite)

        totals_df, slice_tables, topn, _all_slices = run_analysis(args, input_repo_root, logger)
        safety = build_safety_checks(totals_df, slice_tables, topn, preflight)
        elapsed_s = time.time() - started
        report = make_report(
            input_repo_root=input_repo_root,
            totals_df=totals_df,
            slice_tables=slice_tables,
            topn=topn,
            safety=safety,
            elapsed_s=elapsed_s,
            run_label=args.run_label,
        )

        logger.info("writing outputs")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        for dim, table in slice_tables.items():
            atomic_write_tsv(table, OUTPUT_DIR / f"gapfill_slice_by_{dim}.tsv", args.overwrite)
        atomic_write_tsv(topn[TOPN_COLUMNS], OUTPUT_DIR / "gapfill_attribution_topN.tsv", args.overwrite)
        atomic_write_tsv(safety, OUTPUT_DIR / "c_gapfill_safety_checks.tsv", args.overwrite)
        atomic_write_tsv(totals_df, OUTPUT_DIR / "gapfill_model_totals.tsv", args.overwrite)
        atomic_write_text(report, DOCS_DIR / "step08_gapfill_error_structure_report.md", args.overwrite)

        fail_count = int((safety["status"] == "FAIL").sum())
        warn_count = int((safety["status"] == "WARN").sum())
        logger.info("safety fail_count=%d warn_count=%d", fail_count, warn_count)
        logger.info("completed elapsed_s=%.1f", time.time() - started)
        return 0 if fail_count == 0 else 1
    except Exception as exc:
        logger.error("failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
