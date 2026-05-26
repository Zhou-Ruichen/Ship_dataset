#!/usr/bin/env python3
"""
15_strict_vs_expanded_compare_step08.py

Compare Step 08 strict-primary and expanded-primary full validation outputs,
quantify coverage gain, and write the expanded-primary sensitivity report.

Reads:
  - ncei/derived/model_validation_1min_full_strict_primary/full_validation_metrics_summary_strict_primary.parquet
  - ncei/derived/model_validation_1min_full_expanded_primary/full_validation_metrics_summary_expanded_primary.parquet
  - ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_<product>.parquet
  - ncei/derived/model_validation_1min_full_expanded_primary/full_validation_by_cell_expanded_primary_<product>.parquet

Writes (full mode):
  - ncei/derived/model_validation_1min_full_expanded_primary/strict_vs_expanded_comparison.parquet
  - ncei/derived/model_validation_1min_full_expanded_primary/strict_vs_expanded_comparison.tsv
  - ncei/derived/model_validation_1min_full_expanded_primary/expanded_primary_coverage_gain_summary.parquet
  - ncei/derived/model_validation_1min_full_expanded_primary/expanded_primary_coverage_gain_summary.tsv
  - ncei/docs/expanded_primary_global_validation_report.md
  - ncei/output/logs/15_strict_vs_expanded_compare_step08.log

Usage:
    python3 ncei/code/15_strict_vs_expanded_compare_step08.py \
      --strict-dir ncei/derived/model_validation_1min_full_strict_primary \
      --expanded-dir ncei/derived/model_validation_1min_full_expanded_primary \
      --docs-dir ncei/docs \
      --overwrite
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
LOG_DIR = ROOT_DIR / "output" / "logs"

PRODUCT_NAMES = ["GEBCO_2024", "ETOPO_2022", "SRTM15_V2.7", "SDUST_2023", "TOPO_25.1"]
STRICT_EXPECTED_ROWS = 2_398_774
EXPANDED_GAPFILL_EXPECTED_ROWS = 333_915
STRATIFICATION_COLUMNS = [
    "source_role",
    "branch",
    "quality_tier",
    "evidence_class",
    "lat_band_10deg",
    "depth_bin",
    "region_10deg",
]
COMPARISON_COLUMNS = [
    "product_name",
    "sampling_method",
    "strict_count",
    "expanded_count",
    "coverage_gain_count",
    "coverage_gain_fraction_vs_strict",
    "strict_bias",
    "expanded_bias",
    "delta_bias_expanded_minus_strict",
    "strict_MAE",
    "expanded_MAE",
    "delta_MAE_expanded_minus_strict",
    "strict_RMSE",
    "expanded_RMSE",
    "delta_RMSE_expanded_minus_strict",
    "strict_weighted_MAE",
    "expanded_weighted_MAE",
    "delta_weighted_MAE_expanded_minus_strict",
    "strict_weighted_RMSE",
    "expanded_weighted_RMSE",
    "delta_weighted_RMSE_expanded_minus_strict",
]
COVERAGE_COLUMNS = [
    "stratification",
    "stratum",
    "expanded_cells",
    "strict_cells",
    "added_cells",
    "retained_multibeam_cells",
    "singlebeam_gapfill_cells",
]


# ---------------------------------------------------------------------------
# Paths / logging / atomic writes
# ---------------------------------------------------------------------------

def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "15_strict_vs_expanded_compare_step08.log"
    logger = logging.getLogger("15_strict_vs_expanded_compare_step08")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def atomic_write_text(text: str, path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise RuntimeError(f"Output exists; pass --overwrite to replace: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_parquet(df: pd.DataFrame, path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise RuntimeError(f"Output exists; pass --overwrite to replace: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, tmp)
    os.replace(tmp, path)


def atomic_write_tsv(df: pd.DataFrame, path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise RuntimeError(f"Output exists; pass --overwrite to replace: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, path)


def ensure_inputs_exist(paths: Iterable[Path]) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise RuntimeError("Missing required input(s):\n  - " + "\n  - ".join(missing))


def ensure_outputs_available(paths: Iterable[Path], overwrite: bool) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing and not overwrite:
        raise RuntimeError("Output(s) exist; pass --overwrite to replace:\n  - " + "\n  - ".join(existing))


# ---------------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------------

def fmt(value: Any, places: int = 2) -> str:
    if pd.isna(value):
        return "N/A"
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.{places}f}"
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    text = str(value)
    return text.replace("\n", " ").replace("|", "\\|")


def markdown_table(df: pd.DataFrame, max_rows: int | None = None) -> str:
    """Render a compact Markdown table without optional tabulate dependency."""
    if df is None or len(df) == 0:
        return "_(none)_"
    work = df.copy()
    if max_rows is not None:
        work = work.head(max_rows)
    cols = list(work.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in work.iterrows():
        lines.append("| " + " | ".join(fmt(row.get(c)) for c in cols) + " |")
    return "\n".join(lines)


def normalize_bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0).astype(float).ne(0)
    text = series.fillna(False).astype(str).str.strip().str.lower()
    return text.isin(["true", "t", "1", "yes", "y"])


def read_parquet_columns(path: Path, columns: list[str], required: bool = True) -> pd.DataFrame:
    schema_names = set(pq.read_schema(path).names)
    missing = [col for col in columns if col not in schema_names]
    if missing and required:
        raise RuntimeError(f"Missing required column(s) in {path}: {missing}")
    read_cols = [col for col in columns if col in schema_names]
    if not read_cols:
        n_rows = pq.ParquetFile(path).metadata.num_rows
        return pd.DataFrame(index=range(n_rows))
    return pq.read_table(path, columns=read_cols).to_pandas()


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------

def metric_value(row: pd.Series, col: str) -> float:
    if col not in row.index or pd.isna(row[col]):
        return np.nan
    return float(row[col])


def build_comparison(strict_summary: pd.DataFrame, expanded_summary: pd.DataFrame) -> pd.DataFrame:
    required = ["product_name", "sampling_method", "count", "bias", "MAE", "RMSE", "weighted_MAE", "weighted_RMSE"]
    for name, df in [("strict", strict_summary), ("expanded", expanded_summary)]:
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise RuntimeError(f"{name} summary missing required column(s): {missing}")

    strict = strict_summary[strict_summary["product_name"].isin(PRODUCT_NAMES)].copy()
    expanded = expanded_summary[expanded_summary["product_name"].isin(PRODUCT_NAMES)].copy()
    if "status" in strict.columns:
        strict = strict[strict["status"].astype(str).eq("ok")]
    if "status" in expanded.columns:
        expanded = expanded[expanded["status"].astype(str).eq("ok")]

    rows: list[dict[str, Any]] = []
    merged = strict.merge(
        expanded,
        on=["product_name", "sampling_method"],
        how="inner",
        suffixes=("_strict", "_expanded"),
    )
    for _, row in merged.iterrows():
        strict_count = int(row["count_strict"])
        expanded_count = int(row["count_expanded"])
        strict_bias = metric_value(row, "bias_strict")
        expanded_bias = metric_value(row, "bias_expanded")
        strict_mae = metric_value(row, "MAE_strict")
        expanded_mae = metric_value(row, "MAE_expanded")
        strict_rmse = metric_value(row, "RMSE_strict")
        expanded_rmse = metric_value(row, "RMSE_expanded")
        strict_weighted_mae = metric_value(row, "weighted_MAE_strict")
        expanded_weighted_mae = metric_value(row, "weighted_MAE_expanded")
        strict_weighted_rmse = metric_value(row, "weighted_RMSE_strict")
        expanded_weighted_rmse = metric_value(row, "weighted_RMSE_expanded")
        rows.append({
            "product_name": row["product_name"],
            "sampling_method": row["sampling_method"],
            "strict_count": strict_count,
            "expanded_count": expanded_count,
            "coverage_gain_count": expanded_count - strict_count,
            "coverage_gain_fraction_vs_strict": float((expanded_count - strict_count) / strict_count) if strict_count else np.nan,
            "strict_bias": strict_bias,
            "expanded_bias": expanded_bias,
            "delta_bias_expanded_minus_strict": expanded_bias - strict_bias,
            "strict_MAE": strict_mae,
            "expanded_MAE": expanded_mae,
            "delta_MAE_expanded_minus_strict": expanded_mae - strict_mae,
            "strict_RMSE": strict_rmse,
            "expanded_RMSE": expanded_rmse,
            "delta_RMSE_expanded_minus_strict": expanded_rmse - strict_rmse,
            "strict_weighted_MAE": strict_weighted_mae,
            "expanded_weighted_MAE": expanded_weighted_mae,
            "delta_weighted_MAE_expanded_minus_strict": expanded_weighted_mae - strict_weighted_mae,
            "strict_weighted_RMSE": strict_weighted_rmse,
            "expanded_weighted_RMSE": expanded_weighted_rmse,
            "delta_weighted_RMSE_expanded_minus_strict": expanded_weighted_rmse - strict_weighted_rmse,
        })

    comparison = pd.DataFrame(rows, columns=COMPARISON_COLUMNS)
    products_found = set(comparison["product_name"].astype(str)) if len(comparison) else set()
    missing_products = [name for name in PRODUCT_NAMES if name not in products_found]
    if missing_products:
        raise RuntimeError(f"Strict/expanded comparison missing product(s): {missing_products}")
    return comparison.sort_values(["product_name", "sampling_method"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Coverage gain and safety assertions
# ---------------------------------------------------------------------------

def product_paths(strict_dir: Path, expanded_dir: Path, product_name: str) -> tuple[Path, Path]:
    strict_path = strict_dir / f"full_validation_by_cell_strict_primary_{product_name}.parquet"
    expanded_path = expanded_dir / f"full_validation_by_cell_expanded_primary_{product_name}.parquet"
    return strict_path, expanded_path


def read_id_set(path: Path) -> set[Any]:
    ids = pq.read_table(path, columns=["cell_id"]).column("cell_id").to_pylist()
    return set(ids)


def add_membership_and_flags(expanded_df: pd.DataFrame, strict_ids: set[Any]) -> pd.DataFrame:
    out = expanded_df.copy()
    out["is_retained_multibeam"] = out["cell_id"].isin(strict_ids)
    out["is_singlebeam_gapfill"] = ~out["is_retained_multibeam"]
    out["expanded_fill_bool"] = normalize_bool_series(out["expanded_fill"]) if "expanded_fill" in out.columns else False
    return out


def run_coverage_safety_assertions(expanded_df: pd.DataFrame, strict_ids: set[Any]) -> None:
    expanded_ids = set(expanded_df["cell_id"].tolist())
    retained = len(strict_ids.intersection(expanded_ids))
    added = len(expanded_ids.difference(strict_ids))
    if retained != STRICT_EXPECTED_ROWS:
        raise RuntimeError(
            f"Safety assertion failed: |strict ∩ expanded|={retained:,}; expected={STRICT_EXPECTED_ROWS:,}"
        )
    if added != EXPANDED_GAPFILL_EXPECTED_ROWS:
        raise RuntimeError(
            f"Safety assertion failed: |expanded \\ strict|={added:,}; expected={EXPANDED_GAPFILL_EXPECTED_ROWS:,}"
        )

    added_mask = expanded_df["is_singlebeam_gapfill"].to_numpy(dtype=bool)
    retained_mask = expanded_df["is_retained_multibeam"].to_numpy(dtype=bool)
    fill = expanded_df["expanded_fill_bool"].to_numpy(dtype=bool)
    added_bad = int((~fill[added_mask]).sum())
    retained_bad = int(fill[retained_mask].sum())
    if added_bad:
        raise RuntimeError(f"Safety assertion failed: {added_bad:,} added cells have expanded_fill != True")
    if retained_bad:
        raise RuntimeError(f"Safety assertion failed: {retained_bad:,} retained strict cells have expanded_fill == True")


def prepare_coverage_frame(expanded_path: Path, strict_ids: set[Any]) -> pd.DataFrame:
    schema = set(pq.read_schema(expanded_path).names)
    cols = ["cell_id", "expanded_fill"]
    optional_cols = [
        "source_role",
        "branch_role",
        "branch",
        "quality_tier",
        "evidence_class",
        "lat_band_10deg",
        "depth_bin",
        "depth_bin_label",
        "region_10deg",
    ]
    cols.extend([col for col in optional_cols if col in schema])
    missing_core = [col for col in ["cell_id", "expanded_fill"] if col not in schema]
    if missing_core:
        raise RuntimeError(f"Expanded by-cell parquet missing required column(s): {missing_core}")
    df = pq.read_table(expanded_path, columns=cols).to_pandas()
    if "source_role" not in df.columns:
        if "branch_role" in df.columns:
            df["source_role"] = df["branch_role"]
        else:
            raise RuntimeError("Expanded by-cell parquet has neither source_role nor branch_role")
    if "depth_bin" not in df.columns:
        if "depth_bin_label" in df.columns:
            df["depth_bin"] = df["depth_bin_label"]
        else:
            raise RuntimeError("Expanded by-cell parquet has neither depth_bin nor depth_bin_label")
    for col in STRATIFICATION_COLUMNS:
        if col not in df.columns:
            raise RuntimeError(f"Expanded by-cell parquet missing required stratification column: {col}")
    return add_membership_and_flags(df, strict_ids)


def build_coverage_gain_summary(expanded_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for col in STRATIFICATION_COLUMNS:
        work = expanded_df[[col, "cell_id", "is_retained_multibeam", "is_singlebeam_gapfill"]].copy()
        work[col] = work[col].astype(str)
        grouped = work.groupby(col, dropna=False).agg(
            expanded_cells=("cell_id", "count"),
            retained_multibeam_cells=("is_retained_multibeam", "sum"),
            singlebeam_gapfill_cells=("is_singlebeam_gapfill", "sum"),
        ).reset_index()
        grouped = grouped.rename(columns={col: "stratum"})
        grouped["stratification"] = col
        grouped["strict_cells"] = grouped["retained_multibeam_cells"].astype(int)
        grouped["added_cells"] = grouped["expanded_cells"].astype(int) - grouped["strict_cells"].astype(int)
        rows.append(grouped[COVERAGE_COLUMNS])
    coverage = pd.concat(rows, ignore_index=True)
    for col in ["expanded_cells", "strict_cells", "added_cells", "retained_multibeam_cells", "singlebeam_gapfill_cells"]:
        coverage[col] = coverage[col].astype("int64")
    return coverage.sort_values(["stratification", "singlebeam_gapfill_cells", "expanded_cells"], ascending=[True, False, False]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# RMSE sensitivity helpers
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


def metrics_for_subset(df: pd.DataFrame) -> dict[str, Any]:
    valid = np.isfinite(pd.to_numeric(df["depth_error_m"], errors="coerce").to_numpy(dtype=np.float64))
    out = {
        "count": int(valid.sum()),
        "RMSE": rmse(df["depth_error_m"]),
        "weighted_RMSE": np.nan,
    }
    if "validation_weight" in df.columns:
        out["weighted_RMSE"] = weighted_rmse(df["depth_error_m"], df["validation_weight"])
    return out


def read_expanded_product_for_rmse(expanded_path: Path, strict_ids: set[Any]) -> pd.DataFrame:
    schema = set(pq.read_schema(expanded_path).names)
    required = ["cell_id", "depth_error_m"]
    missing = [col for col in required if col not in schema]
    if missing:
        raise RuntimeError(f"Expanded by-cell parquet missing required RMSE column(s): {missing}")
    optional = ["validation_weight", "lat_band_10deg", "depth_bin", "depth_bin_label"]
    cols = required + [col for col in optional if col in schema]
    df = pq.read_table(expanded_path, columns=cols).to_pandas()
    df["is_retained_multibeam"] = df["cell_id"].isin(strict_ids)
    df["is_singlebeam_gapfill"] = ~df["is_retained_multibeam"]
    if "depth_bin" not in df.columns and "depth_bin_label" in df.columns:
        df["depth_bin"] = df["depth_bin_label"]
    return df


def build_product_sensitivity(expanded_dir: Path, strict_ids: set[Any], comparison: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    stratum_rows: list[dict[str, Any]] = []
    expected_rmse = {
        str(row["product_name"]): float(row["expanded_RMSE"])
        for _, row in comparison.iterrows()
        if pd.notna(row["expanded_RMSE"])
    }

    for product_name in PRODUCT_NAMES:
        _, expanded_path = product_paths(Path("unused"), expanded_dir, product_name)
        df = read_expanded_product_for_rmse(expanded_path, strict_ids)
        overall = metrics_for_subset(df)
        retained = metrics_for_subset(df[df["is_retained_multibeam"]])
        gapfill = metrics_for_subset(df[df["is_singlebeam_gapfill"]])
        expected = expected_rmse.get(product_name, np.nan)
        if pd.notna(expected) and pd.notna(overall["RMSE"]) and not np.isclose(overall["RMSE"], expected, rtol=1e-8, atol=1e-6):
            raise RuntimeError(
                f"Expanded RMSE cross-check failed for {product_name}: by-cell={overall['RMSE']}; summary={expected}"
            )
        rows.append({
            "product_name": product_name,
            "expanded_RMSE_overall": overall["RMSE"],
            "expanded_RMSE_retained_multibeam": retained["RMSE"],
            "expanded_RMSE_singlebeam_gapfill": gapfill["RMSE"],
            "expanded_weighted_RMSE_overall": overall["weighted_RMSE"],
            "expanded_weighted_RMSE_retained_multibeam": retained["weighted_RMSE"],
            "expanded_weighted_RMSE_singlebeam_gapfill": gapfill["weighted_RMSE"],
            "overall_valid_count": overall["count"],
            "retained_valid_count": retained["count"],
            "singlebeam_gapfill_valid_count": gapfill["count"],
        })

        for dim in ["lat_band_10deg", "depth_bin"]:
            if dim not in df.columns:
                continue
            work = df[[dim, "depth_error_m", "validation_weight", "is_retained_multibeam", "is_singlebeam_gapfill"]].copy() if "validation_weight" in df.columns else df[[dim, "depth_error_m", "is_retained_multibeam", "is_singlebeam_gapfill"]].copy()
            work[dim] = work[dim].astype(str)
            for stratum, sub in work.groupby(dim, dropna=False):
                retained_sub = sub[sub["is_retained_multibeam"]]
                gapfill_sub = sub[sub["is_singlebeam_gapfill"]]
                if len(retained_sub) == 0 or len(gapfill_sub) == 0:
                    continue
                retained_metrics = metrics_for_subset(retained_sub)
                gapfill_metrics = metrics_for_subset(gapfill_sub)
                if pd.isna(retained_metrics["RMSE"]) or pd.isna(gapfill_metrics["RMSE"]):
                    continue
                stratum_rows.append({
                    "product_name": product_name,
                    "stratification": dim,
                    "stratum": str(stratum),
                    "retained_count": retained_metrics["count"],
                    "singlebeam_gapfill_count": gapfill_metrics["count"],
                    "retained_RMSE": retained_metrics["RMSE"],
                    "singlebeam_gapfill_RMSE": gapfill_metrics["RMSE"],
                    "gapfill_minus_retained_RMSE": gapfill_metrics["RMSE"] - retained_metrics["RMSE"],
                })
    return pd.DataFrame(rows), pd.DataFrame(stratum_rows)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def compact_metrics_table(expanded_summary: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "product_name",
        "sampling_method",
        "count",
        "nodata_count",
        "bias",
        "MAE",
        "RMSE",
        "weighted_MAE",
        "weighted_RMSE",
        "abs_error_p95",
    ]
    use_cols = [col for col in cols if col in expanded_summary.columns]
    out = expanded_summary[expanded_summary["product_name"].isin(PRODUCT_NAMES)][use_cols].copy()
    if "RMSE" in out.columns:
        out = out.sort_values("RMSE")
    return out.reset_index(drop=True)


def top_coverage_tables(coverage: pd.DataFrame) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    cols = ["stratum", "expanded_cells", "strict_cells", "added_cells", "retained_multibeam_cells", "singlebeam_gapfill_cells"]
    for dim in STRATIFICATION_COLUMNS:
        sub = coverage[coverage["stratification"].eq(dim)].copy()
        sub = sub.sort_values(["singlebeam_gapfill_cells", "expanded_cells"], ascending=[False, False]).head(5)
        tables[dim] = sub[cols]
    return tables


def diagnose_product(row: pd.Series) -> str:
    retained = row["expanded_RMSE_retained_multibeam"]
    gapfill = row["expanded_RMSE_singlebeam_gapfill"]
    if pd.isna(retained) or pd.isna(gapfill):
        return "insufficient retained/gap-fill data for diagnosis"
    if gapfill > retained * 1.10 or (gapfill - retained) > 25.0:
        return "delta_RMSE is likely driven upward by added singlebeam gap-fill cells"
    if gapfill < retained * 0.90:
        return "added singlebeam gap-fill cells have lower RMSE than retained multibeam cells in this run"
    return "singlebeam gap-fill RMSE is broadly comparable to retained multibeam RMSE"


def build_recommendation(product_sensitivity: pd.DataFrame, stratum_sensitivity: pd.DataFrame) -> str:
    material_flags = []
    for _, row in product_sensitivity.iterrows():
        retained = row["expanded_RMSE_retained_multibeam"]
        gapfill = row["expanded_RMSE_singlebeam_gapfill"]
        material_flags.append(pd.notna(retained) and pd.notna(gapfill) and (gapfill > retained * 1.10 or (gapfill - retained) > 25.0))
    material_count = int(sum(material_flags))
    comparable_windows = pd.DataFrame()
    if len(stratum_sensitivity):
        work = stratum_sensitivity.copy()
        work = work[np.isfinite(work["gapfill_minus_retained_RMSE"].to_numpy(dtype=np.float64))]
        comparable_windows = work[work["gapfill_minus_retained_RMSE"].abs().le(25.0)].sort_values(
            ["singlebeam_gapfill_count", "gapfill_minus_retained_RMSE"], ascending=[False, True]
        ).head(3)

    if material_count >= max(1, len(product_sensitivity) // 2):
        return (
            "Recommendation: keep expanded_primary as a secondary/sensitivity-only validation product for global ranking. "
            "The singlebeam gap-fill subset has materially higher RMSE than retained multibeam cells for a majority of products, "
            "so strict_primary should remain the authoritative global baseline. Expanded_primary may still be useful for coverage "
            "diagnostics and carefully caveated regional analyses where the stratum-level RMSE is comparable."
        )
    if len(comparable_windows):
        windows = "; ".join(
            f"{r['product_name']} {r['stratification']}={r['stratum']}"
            for _, r in comparable_windows.iterrows()
        )
        return (
            "Recommendation: keep expanded_primary secondary for global policy, but conditional regional use is reasonable in "
            f"windows with comparable retained/gap-fill RMSE (examples: {windows}). Use these results with the documented "
            "singlebeam provenance and avoid promoting expanded_primary over strict_primary without a separate policy task."
        )
    return (
        "Recommendation: keep expanded_primary as a secondary/sensitivity-only product. The available stratum diagnostics do not "
        "identify a clear, repeated region/depth window where gap-fill behavior is comparable enough to justify broader use."
    )


def make_report(strict_dir: Path, expanded_dir: Path, docs_dir: Path, expanded_summary: pd.DataFrame,
                comparison: pd.DataFrame, coverage: pd.DataFrame, product_sensitivity: pd.DataFrame,
                stratum_sensitivity: pd.DataFrame, elapsed_s: float) -> str:
    lines: list[str] = []
    lines.append("# Step 08 Expanded-Primary Global Validation Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("Generated by: `ncei/code/15_strict_vs_expanded_compare_step08.py`")
    lines.append("Task / PRD: `.trellis/tasks/05-27-stage4-expanded-primary-sensitivity/prd.md`")
    lines.append(f"Elapsed: {elapsed_s:.1f}s")
    lines.append(f"Strict-primary input directory: `{strict_dir}`")
    lines.append(f"Expanded-primary input/output directory: `{expanded_dir}`")
    lines.append(f"Docs directory: `{docs_dir}`")
    lines.append("Comparison safety assertions: **PASS** (strict/expanded cell-id intersection, gap-fill count, and `expanded_fill` membership checks)")
    lines.append("")

    lines.append("## 1. Overall expanded-primary metrics")
    lines.append("")
    lines.append(markdown_table(compact_metrics_table(expanded_summary)))
    lines.append("")

    lines.append("## 2. Strict vs expanded comparison")
    lines.append("")
    display_cols = [
        "product_name", "sampling_method", "strict_count", "expanded_count", "coverage_gain_count",
        "coverage_gain_fraction_vs_strict", "strict_RMSE", "expanded_RMSE", "delta_RMSE_expanded_minus_strict",
        "strict_MAE", "expanded_MAE", "delta_MAE_expanded_minus_strict",
        "delta_bias_expanded_minus_strict", "delta_weighted_RMSE_expanded_minus_strict",
    ]
    lines.append(markdown_table(comparison[display_cols]))
    lines.append("")

    lines.append("## 3. Top coverage-gain strata")
    lines.append("")
    for dim, table in top_coverage_tables(coverage).items():
        lines.append(f"### {dim}")
        lines.append("")
        lines.append(markdown_table(table))
        lines.append("")

    lines.append("## 4. Sensitivity interpretation")
    lines.append("")
    sensitivity_display = product_sensitivity.copy()
    sensitivity_display["diagnosis"] = sensitivity_display.apply(diagnose_product, axis=1)
    lines.append(markdown_table(sensitivity_display[[
        "product_name",
        "expanded_RMSE_overall",
        "expanded_RMSE_retained_multibeam",
        "expanded_RMSE_singlebeam_gapfill",
        "expanded_weighted_RMSE_overall",
        "expanded_weighted_RMSE_retained_multibeam",
        "expanded_weighted_RMSE_singlebeam_gapfill",
        "diagnosis",
    ]]))
    lines.append("")

    if len(stratum_sensitivity):
        for dim in ["lat_band_10deg", "depth_bin"]:
            top = stratum_sensitivity[stratum_sensitivity["stratification"].eq(dim)].copy()
            top = top.sort_values("gapfill_minus_retained_RMSE", ascending=False).head(3)
            lines.append(f"### Top-3 {dim} strata where gap-fill RMSE exceeds retained RMSE")
            lines.append("")
            lines.append(markdown_table(top[[
                "product_name", "stratum", "retained_count", "singlebeam_gapfill_count",
                "retained_RMSE", "singlebeam_gapfill_RMSE", "gapfill_minus_retained_RMSE",
            ]]))
            lines.append("")
    else:
        lines.append("Stratum-level retained-vs-gap-fill RMSE diagnostics were not computable from the by-cell parquets.")
        lines.append("")

    lines.append("## 5. Recommendation")
    lines.append("")
    lines.append(build_recommendation(product_sensitivity, stratum_sensitivity))
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare strict-primary vs expanded-primary Step 08 full validation outputs")
    parser.add_argument("--strict-dir", default="ncei/derived/model_validation_1min_full_strict_primary")
    parser.add_argument("--expanded-dir", default="ncei/derived/model_validation_1min_full_expanded_primary")
    parser.add_argument("--docs-dir", default="ncei/docs")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite comparison outputs if they already exist")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    logger = setup_logging()
    logger.info("argv=%s", " ".join(sys.argv))
    t0 = time.time()

    try:
        strict_dir = resolve_path(args.strict_dir)
        expanded_dir = resolve_path(args.expanded_dir)
        docs_dir = resolve_path(args.docs_dir)
        logger.info("strict_dir=%s", strict_dir)
        logger.info("expanded_dir=%s", expanded_dir)
        logger.info("docs_dir=%s", docs_dir)

        strict_summary_path = strict_dir / "full_validation_metrics_summary_strict_primary.parquet"
        expanded_summary_path = expanded_dir / "full_validation_metrics_summary_expanded_primary.parquet"
        required_paths = [strict_summary_path, expanded_summary_path]
        for product_name in PRODUCT_NAMES:
            strict_path, expanded_path = product_paths(strict_dir, expanded_dir, product_name)
            required_paths.extend([strict_path, expanded_path])
        ensure_inputs_exist(required_paths)

        strict_summary = pq.read_table(strict_summary_path).to_pandas()
        expanded_summary = pq.read_table(expanded_summary_path).to_pandas()
        comparison = build_comparison(strict_summary, expanded_summary)
        logger.info("comparison_rows=%d", len(comparison))

        safety_strict_path, safety_expanded_path = product_paths(strict_dir, expanded_dir, "GEBCO_2024")
        strict_ids = read_id_set(safety_strict_path)
        expanded_coverage_df = prepare_coverage_frame(safety_expanded_path, strict_ids)
        run_coverage_safety_assertions(expanded_coverage_df, strict_ids)
        logger.info("coverage safety assertions passed")

        coverage = build_coverage_gain_summary(expanded_coverage_df)
        product_sensitivity, stratum_sensitivity = build_product_sensitivity(expanded_dir, strict_ids, comparison)
        elapsed_s = time.time() - t0
        report = make_report(strict_dir, expanded_dir, docs_dir, expanded_summary, comparison, coverage,
                             product_sensitivity, stratum_sensitivity, elapsed_s)

        comparison_parquet = expanded_dir / "strict_vs_expanded_comparison.parquet"
        comparison_tsv = expanded_dir / "strict_vs_expanded_comparison.tsv"
        coverage_parquet = expanded_dir / "expanded_primary_coverage_gain_summary.parquet"
        coverage_tsv = expanded_dir / "expanded_primary_coverage_gain_summary.tsv"
        report_path = docs_dir / "expanded_primary_global_validation_report.md"
        ensure_outputs_available([
            comparison_parquet,
            comparison_tsv,
            coverage_parquet,
            coverage_tsv,
            report_path,
        ], args.overwrite)

        atomic_write_parquet(comparison, comparison_parquet, args.overwrite)
        atomic_write_tsv(comparison, comparison_tsv, args.overwrite)
        atomic_write_parquet(coverage, coverage_parquet, args.overwrite)
        atomic_write_tsv(coverage, coverage_tsv, args.overwrite)
        atomic_write_text(report, report_path, args.overwrite)

        logger.info("wrote %s", comparison_parquet)
        logger.info("wrote %s", comparison_tsv)
        logger.info("wrote %s", coverage_parquet)
        logger.info("wrote %s", coverage_tsv)
        logger.info("wrote %s", report_path)
        logger.info("completed successfully elapsed_s=%.1f", time.time() - t0)
        return 0
    except Exception as exc:
        logger.error("failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
