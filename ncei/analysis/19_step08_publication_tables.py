#!/usr/bin/env python3
"""
19_step08_publication_tables.py

Build publication-ready Step 08 strict-primary and strict-vs-expanded tables
from existing by-cell validation outputs. This script is read-only with respect
to upstream validation products and never resamples gridded models.

Reads:
  - ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_<MODEL>.parquet
  - ncei/derived/model_validation_1min_full_expanded_primary/full_validation_by_cell_expanded_primary_<MODEL>.parquet
  - ncei/derived/model_validation_1min_full_strict_primary/full_validation_metrics_summary_strict_primary.parquet
  - ncei/derived/model_validation_1min_full_expanded_primary/full_validation_metrics_summary_expanded_primary.parquet
  - ncei/derived/model_validation_1min_full_expanded_primary/strict_vs_expanded_comparison.parquet
  - ncei/derived/model_validation_1min_full_expanded_primary/expanded_primary_coverage_gain_summary.parquet
  - ncei/derived/model_validation_1min_stage6_final/expanded_gapfill_sensitivity_summary.parquet

Writes (publish mode):
  - ncei/derived/model_validation_1min_step08_pub/b_pub_tables/strict_primary_publication_table.tsv
  - ncei/derived/model_validation_1min_step08_pub/b_pub_tables/strict_primary_publication_table.csv
  - ncei/derived/model_validation_1min_step08_pub/b_pub_tables/strict_vs_expanded_publication_table.tsv
  - ncei/derived/model_validation_1min_step08_pub/b_pub_tables/strict_vs_expanded_publication_table.csv
  - ncei/derived/model_validation_1min_step08_pub/b_pub_tables/b_pub_safety_checks.tsv
  - ncei/output/logs/19_step08_publication_tables_<run_label>.log

Usage:
    python ncei/analysis/19_step08_publication_tables.py --check-only
    python ncei/analysis/19_step08_publication_tables.py --run-label b_pub_tables --confirm-publish --overwrite
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

SCRIPT_DIR = Path(__file__).parent.resolve()
CODE_NCEI_ROOT = SCRIPT_DIR.parent
CODE_REPO_ROOT = CODE_NCEI_ROOT.parent

PRODUCT_NAMES = ["GEBCO_2024", "ETOPO_2022", "SRTM15_V2.7", "TOPO_25.1", "SDUST_2023"]
STRICT_EXPECTED_ROWS = 2_398_774
EXPANDED_EXPECTED_ROWS = 2_732_689
GAPFILL_EXPECTED_ROWS = 333_915
CHECK_TOLERANCE = 0.01
FLOAT_FORMAT = "%.6f"

STRICT_COLUMNS = [
    "model",
    "n_cells",
    "bias",
    "MAE",
    "RMSE",
    "weighted_MAE",
    "weighted_RMSE",
    "median_error",
    "MAD",
    "p95_abs_error",
]
STRICT_VS_EXPANDED_COLUMNS = [
    "model",
    "strict_count",
    "expanded_count",
    "coverage_gain_count",
    "coverage_gain_fraction",
    "strict_RMSE",
    "expanded_RMSE",
    "delta_RMSE",
    "strict_weighted_RMSE",
    "expanded_weighted_RMSE",
    "delta_weighted_RMSE",
    "retained_multibeam_RMSE",
    "gapfill_singlebeam_RMSE",
    "gapfill_to_retained_RMSE_ratio",
]


def find_data_repo_root() -> Path:
    """Find the repository root that contains the gitignored derived data.

    In normal runs this is CODE_REPO_ROOT. In Trellis isolated worktrees the
    tracked code lives under .trellis/.runtime while large derived artifacts
    remain in an ancestor repository checkout; walking ancestors keeps the
    script usable without hardcoded absolute paths.
    """
    sentinel = Path("ncei") / "derived" / "model_validation_1min_full_strict_primary"
    for candidate in [CODE_REPO_ROOT, *CODE_REPO_ROOT.parents]:
        if (candidate / sentinel).exists():
            return candidate
    return CODE_REPO_ROOT


DATA_REPO_ROOT = find_data_repo_root()
ROOT_DIR = DATA_REPO_ROOT / "ncei"
DERIVED_DIR = ROOT_DIR / "derived"
LOG_DIR = ROOT_DIR / "output" / "logs"
STRICT_DIR = DERIVED_DIR / "model_validation_1min_full_strict_primary"
EXPANDED_DIR = DERIVED_DIR / "model_validation_1min_full_expanded_primary"
STAGE6_DIR = DERIVED_DIR / "model_validation_1min_stage6_final"
OUTPUT_DIR = DERIVED_DIR / "model_validation_1min_step08_pub" / "b_pub_tables"

STRICT_SUMMARY_PATH = STRICT_DIR / "full_validation_metrics_summary_strict_primary.parquet"
EXPANDED_SUMMARY_PATH = EXPANDED_DIR / "full_validation_metrics_summary_expanded_primary.parquet"
STRICT_VS_EXPANDED_PATH = EXPANDED_DIR / "strict_vs_expanded_comparison.parquet"
COVERAGE_GAIN_PATH = EXPANDED_DIR / "expanded_primary_coverage_gain_summary.parquet"
STAGE6_GAPFILL_PATH = STAGE6_DIR / "expanded_gapfill_sensitivity_summary.parquet"


# ---------------------------------------------------------------------------
# Paths / logging / atomic writes
# ---------------------------------------------------------------------------


def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
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


def strict_by_cell_path(product_name: str) -> Path:
    return STRICT_DIR / f"full_validation_by_cell_strict_primary_{product_name}.parquet"


def expanded_by_cell_path(product_name: str) -> Path:
    return EXPANDED_DIR / f"full_validation_by_cell_expanded_primary_{product_name}.parquet"


def output_paths() -> list[Path]:
    return [
        OUTPUT_DIR / "strict_primary_publication_table.tsv",
        OUTPUT_DIR / "strict_primary_publication_table.csv",
        OUTPUT_DIR / "strict_vs_expanded_publication_table.tsv",
        OUTPUT_DIR / "strict_vs_expanded_publication_table.csv",
        OUTPUT_DIR / "b_pub_safety_checks.tsv",
    ]


def require_inputs() -> None:
    paths = [
        STRICT_SUMMARY_PATH,
        EXPANDED_SUMMARY_PATH,
        STRICT_VS_EXPANDED_PATH,
        COVERAGE_GAIN_PATH,
        STAGE6_GAPFILL_PATH,
    ]
    for product_name in PRODUCT_NAMES:
        paths.extend([strict_by_cell_path(product_name), expanded_by_cell_path(product_name)])
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required input(s):\n  - " + "\n  - ".join(missing))


def ensure_outputs_available(paths: Iterable[Path], overwrite: bool) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError("Output(s) exist; pass --overwrite to replace:\n  - " + "\n  - ".join(existing))


def atomic_write_text(text: str, path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output exists; pass --overwrite to replace: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def dataframe_to_text(df: pd.DataFrame, sep: str) -> str:
    return df.to_csv(sep=sep, index=False, float_format=FLOAT_FORMAT, lineterminator="\n")


def atomic_write_table_pair(df: pd.DataFrame, stem: str, overwrite: bool) -> tuple[Path, Path]:
    tsv_path = OUTPUT_DIR / f"{stem}.tsv"
    csv_path = OUTPUT_DIR / f"{stem}.csv"
    tsv_text = dataframe_to_text(df, "\t")
    csv_text = dataframe_to_text(df, ",")
    if tsv_text.replace("\t", ",") != csv_text:
        raise RuntimeError(f"CSV/TSV serialization mismatch for {stem}")
    atomic_write_text(tsv_text, tsv_path, overwrite)
    atomic_write_text(csv_text, csv_path, overwrite)
    return tsv_path, csv_path


# ---------------------------------------------------------------------------
# Data loading / metrics
# ---------------------------------------------------------------------------


def read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def read_by_cell(path: Path, columns: list[str]) -> pd.DataFrame:
    schema_names = set(pq.read_schema(path).names)
    missing = [col for col in columns if col not in schema_names]
    if missing:
        raise RuntimeError(f"{path} missing required column(s): {missing}")
    return pq.read_table(path, columns=columns).to_pandas()


def normalize_bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0).astype(float).ne(0)
    text = series.fillna(False).astype(str).str.strip().str.lower()
    return text.isin(["true", "t", "1", "yes", "y"])


def row_count(path: Path) -> int:
    return int(pq.ParquetFile(path).metadata.num_rows)


def finite_error_arrays(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    errors = pd.to_numeric(df["elev_error_m"], errors="coerce").to_numpy(dtype=np.float64)
    if "abs_elev_error_m" in df.columns:
        abs_errors = pd.to_numeric(df["abs_elev_error_m"], errors="coerce").to_numpy(dtype=np.float64)
    else:
        abs_errors = np.abs(errors)
    weights = pd.to_numeric(df["validation_weight"], errors="coerce").to_numpy(dtype=np.float64)
    mask = np.isfinite(errors)
    return errors[mask], abs_errors[mask], weights[mask]


def metric_dict(df: pd.DataFrame, n_cells: int) -> dict[str, float | int]:
    errors, abs_errors, weights = finite_error_arrays(df)
    if len(errors) == 0:
        raise RuntimeError("Cannot compute metrics: no finite elev_error_m values")
    med = float(np.median(errors))
    wmask = np.isfinite(weights) & (weights > 0)
    if int(wmask.sum()) == 0:
        weighted_mae = np.nan
        weighted_rmse = np.nan
    else:
        w = weights[wmask]
        e = errors[wmask]
        ae = np.abs(e)
        weighted_mae = float(np.sum(w * ae) / np.sum(w))
        weighted_rmse = float(np.sqrt(np.sum(w * (e ** 2)) / np.sum(w)))
    return {
        "n_cells": int(n_cells),
        "valid_error_count": int(len(errors)),
        "bias": float(np.mean(errors)),
        "MAE": float(np.mean(abs_errors)),
        "RMSE": float(np.sqrt(np.mean(errors ** 2))),
        "weighted_MAE": weighted_mae,
        "weighted_RMSE": weighted_rmse,
        "median_error": med,
        "MAD": float(np.median(np.abs(errors - med))),
        "p95_abs_error": float(np.quantile(abs_errors, 0.95)),
    }


def rmse_for_subset(df: pd.DataFrame) -> float:
    errors = pd.to_numeric(df["elev_error_m"], errors="coerce").to_numpy(dtype=np.float64)
    errors = errors[np.isfinite(errors)]
    if len(errors) == 0:
        return np.nan
    return float(np.sqrt(np.mean(errors ** 2)))


def weighted_rmse_for_subset(df: pd.DataFrame) -> float:
    errors = pd.to_numeric(df["elev_error_m"], errors="coerce").to_numpy(dtype=np.float64)
    weights = pd.to_numeric(df["validation_weight"], errors="coerce").to_numpy(dtype=np.float64)
    mask = np.isfinite(errors) & np.isfinite(weights) & (weights > 0)
    if int(mask.sum()) == 0:
        return np.nan
    return float(np.sqrt(np.sum(weights[mask] * (errors[mask] ** 2)) / np.sum(weights[mask])))


def summary_by_product(df: pd.DataFrame) -> dict[str, pd.Series]:
    if "product_name" not in df.columns:
        raise RuntimeError("Metrics summary missing product_name column")
    out: dict[str, pd.Series] = {}
    for product_name in PRODUCT_NAMES:
        sub = df[df["product_name"].astype(str).eq(product_name)]
        if len(sub) != 1:
            raise RuntimeError(f"Expected exactly one summary row for {product_name}, found {len(sub)}")
        out[product_name] = sub.iloc[0]
    return out


# ---------------------------------------------------------------------------
# Safety checks
# ---------------------------------------------------------------------------


def add_check(rows: list[dict[str, Any]], check: str, status: bool, details: str,
              observed: Any = "", expected: Any = "") -> None:
    rows.append({
        "check": check,
        "status": "PASS" if status else "FAIL",
        "observed": observed,
        "expected": expected,
        "details": details,
    })


def close_enough(a: float, b: float, tolerance: float = CHECK_TOLERANCE) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    return abs(float(a) - float(b)) < tolerance


def build_safety_checks(
    strict_table: pd.DataFrame,
    strict_vs_expanded: pd.DataFrame,
    strict_summary: pd.DataFrame,
    expanded_summary: pd.DataFrame,
    comparison: pd.DataFrame,
    coverage_gain: pd.DataFrame,
    stage6_gapfill: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    strict_summary_rows = summary_by_product(strict_summary)
    expanded_summary_rows = summary_by_product(expanded_summary)
    comparison_rows = summary_by_product(comparison.rename(columns={"product_name": "product_name"}))
    gapfill_rows = summary_by_product(stage6_gapfill)

    add_check(
        rows,
        "strict_table_sorted_by_RMSE",
        strict_table["RMSE"].is_monotonic_increasing,
        "strict-primary publication rows are sorted in ascending RMSE",
    )
    add_check(
        rows,
        "strict_vs_expanded_table_sorted_by_strict_RMSE",
        strict_vs_expanded["strict_RMSE"].is_monotonic_increasing,
        "strict-vs-expanded publication rows are sorted in ascending strict_RMSE",
    )

    for product_name in PRODUCT_NAMES:
        strict_row = strict_table[strict_table["model"].eq(product_name)].iloc[0]
        sve_row = strict_vs_expanded[strict_vs_expanded["model"].eq(product_name)].iloc[0]
        ss = strict_summary_rows[product_name]
        es = expanded_summary_rows[product_name]
        comp = comparison_rows[product_name]
        gap = gapfill_rows[product_name]

        add_check(
            rows,
            f"strict_n_cells_{product_name}",
            int(strict_row["n_cells"]) == STRICT_EXPECTED_ROWS,
            "strict by-cell row count matches expected global strict-primary count",
            int(strict_row["n_cells"]),
            STRICT_EXPECTED_ROWS,
        )
        add_check(
            rows,
            f"expanded_n_cells_{product_name}",
            int(sve_row["expanded_count"]) == EXPANDED_EXPECTED_ROWS,
            "expanded by-cell row count matches expected expanded-primary count",
            int(sve_row["expanded_count"]),
            EXPANDED_EXPECTED_ROWS,
        )
        add_check(
            rows,
            f"coverage_gain_{product_name}",
            int(sve_row["coverage_gain_count"]) == GAPFILL_EXPECTED_ROWS,
            "expanded minus strict count matches expected singlebeam gap-fill count",
            int(sve_row["coverage_gain_count"]),
            GAPFILL_EXPECTED_ROWS,
        )
        add_check(
            rows,
            f"retained_multibeam_count_{product_name}",
            int(gap["retained_multibeam_count"]) == STRICT_EXPECTED_ROWS,
            "Stage 6 retained-multibeam count matches strict count",
            int(gap["retained_multibeam_count"]),
            STRICT_EXPECTED_ROWS,
        )
        add_check(
            rows,
            f"gapfill_singlebeam_count_{product_name}",
            int(gap["singlebeam_gapfill_count"]) == GAPFILL_EXPECTED_ROWS,
            "Stage 6 gap-fill count matches expected count",
            int(gap["singlebeam_gapfill_count"]),
            GAPFILL_EXPECTED_ROWS,
        )

        metric_pairs = [
            ("strict_RMSE", float(strict_row["RMSE"]), float(ss["RMSE"])),
            ("strict_weighted_RMSE", float(strict_row["weighted_RMSE"]), float(ss["weighted_RMSE"])),
            ("strict_MAE", float(strict_row["MAE"]), float(ss["MAE"])),
            ("strict_weighted_MAE", float(strict_row["weighted_MAE"]), float(ss["weighted_MAE"])),
            ("strict_p95_abs_error", float(strict_row["p95_abs_error"]), float(ss["abs_error_p95"])),
            ("expanded_RMSE", float(sve_row["expanded_RMSE"]), float(es["RMSE"])),
            ("expanded_weighted_RMSE", float(sve_row["expanded_weighted_RMSE"]), float(es["weighted_RMSE"])),
            ("comparison_strict_RMSE", float(sve_row["strict_RMSE"]), float(comp["strict_RMSE"])),
            ("comparison_expanded_RMSE", float(sve_row["expanded_RMSE"]), float(comp["expanded_RMSE"])),
            ("comparison_strict_weighted_RMSE", float(sve_row["strict_weighted_RMSE"]), float(comp["strict_weighted_RMSE"])),
            ("comparison_expanded_weighted_RMSE", float(sve_row["expanded_weighted_RMSE"]), float(comp["expanded_weighted_RMSE"])),
            ("stage6_retained_RMSE", float(sve_row["retained_multibeam_RMSE"]), float(gap["retained_multibeam_RMSE"])),
            ("stage6_gapfill_RMSE", float(sve_row["gapfill_singlebeam_RMSE"]), float(gap["singlebeam_gapfill_RMSE"])),
        ]
        for check_name, observed, expected in metric_pairs:
            add_check(
                rows,
                f"{check_name}_{product_name}",
                close_enough(observed, expected),
                f"{check_name} agrees with existing Stage 3/4/6 artifact within < {CHECK_TOLERANCE}",
                f"{observed:.6f}",
                f"{expected:.6f}",
            )

    for stratification, sub in coverage_gain.groupby("stratification", dropna=False):
        expanded_total = int(sub["expanded_cells"].sum())
        strict_total = int(sub["strict_cells"].sum())
        added_total = int(sub["added_cells"].sum())
        add_check(
            rows,
            f"coverage_gain_summary_totals_{stratification}",
            expanded_total == EXPANDED_EXPECTED_ROWS and strict_total == STRICT_EXPECTED_ROWS and added_total == GAPFILL_EXPECTED_ROWS,
            "Stage 4 coverage-gain summary totals match expected counts for this stratification",
            f"expanded={expanded_total}; strict={strict_total}; added={added_total}",
            f"expanded={EXPANDED_EXPECTED_ROWS}; strict={STRICT_EXPECTED_ROWS}; added={GAPFILL_EXPECTED_ROWS}",
        )

    safety = pd.DataFrame(rows, columns=["check", "status", "observed", "expected", "details"])
    return safety


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------


def build_tables(logger: logging.Logger) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    strict_summary = read_parquet(STRICT_SUMMARY_PATH)
    expanded_summary = read_parquet(EXPANDED_SUMMARY_PATH)
    comparison = read_parquet(STRICT_VS_EXPANDED_PATH)
    coverage_gain = read_parquet(COVERAGE_GAIN_PATH)
    stage6_gapfill = read_parquet(STAGE6_GAPFILL_PATH)

    strict_rows: list[dict[str, Any]] = []
    strict_metrics_by_product: dict[str, dict[str, float | int]] = {}
    expanded_metrics_by_product: dict[str, dict[str, float | int]] = {}
    subset_metrics_by_product: dict[str, dict[str, float | int]] = {}

    for product_name in PRODUCT_NAMES:
        logger.info("computing strict-primary publication metrics product=%s", product_name)
        strict_path = strict_by_cell_path(product_name)
        strict_n = row_count(strict_path)
        strict_df = read_by_cell(strict_path, ["elev_error_m", "abs_elev_error_m", "validation_weight"])
        strict_metrics = metric_dict(strict_df, strict_n)
        strict_metrics_by_product[product_name] = strict_metrics
        strict_rows.append({
            "model": product_name,
            "n_cells": strict_metrics["n_cells"],
            "bias": strict_metrics["bias"],
            "MAE": strict_metrics["MAE"],
            "RMSE": strict_metrics["RMSE"],
            "weighted_MAE": strict_metrics["weighted_MAE"],
            "weighted_RMSE": strict_metrics["weighted_RMSE"],
            "median_error": strict_metrics["median_error"],
            "MAD": strict_metrics["MAD"],
            "p95_abs_error": strict_metrics["p95_abs_error"],
        })

        logger.info("computing expanded-primary publication metrics product=%s", product_name)
        expanded_path = expanded_by_cell_path(product_name)
        expanded_n = row_count(expanded_path)
        expanded_df = read_by_cell(expanded_path, ["elev_error_m", "abs_elev_error_m", "validation_weight", "expanded_fill"])
        expanded_metrics = metric_dict(expanded_df, expanded_n)
        expanded_metrics_by_product[product_name] = expanded_metrics

        expanded_fill = normalize_bool_series(expanded_df["expanded_fill"])
        retained = expanded_df[~expanded_fill]
        gapfill = expanded_df[expanded_fill]
        subset_metrics_by_product[product_name] = {
            "retained_count": int(len(retained)),
            "gapfill_count": int(len(gapfill)),
            "retained_multibeam_RMSE": rmse_for_subset(retained),
            "gapfill_singlebeam_RMSE": rmse_for_subset(gapfill),
            "retained_multibeam_weighted_RMSE": weighted_rmse_for_subset(retained),
            "gapfill_singlebeam_weighted_RMSE": weighted_rmse_for_subset(gapfill),
        }

    strict_table = pd.DataFrame(strict_rows, columns=STRICT_COLUMNS).sort_values("RMSE").reset_index(drop=True)

    sve_rows: list[dict[str, Any]] = []
    for product_name in PRODUCT_NAMES:
        strict_metrics = strict_metrics_by_product[product_name]
        expanded_metrics = expanded_metrics_by_product[product_name]
        subset_metrics = subset_metrics_by_product[product_name]
        strict_count = int(strict_metrics["n_cells"])
        expanded_count = int(expanded_metrics["n_cells"])
        coverage_gain_count = expanded_count - strict_count
        retained_rmse = float(subset_metrics["retained_multibeam_RMSE"])
        gapfill_rmse = float(subset_metrics["gapfill_singlebeam_RMSE"])
        sve_rows.append({
            "model": product_name,
            "strict_count": strict_count,
            "expanded_count": expanded_count,
            "coverage_gain_count": coverage_gain_count,
            "coverage_gain_fraction": float(coverage_gain_count / strict_count) if strict_count else np.nan,
            "strict_RMSE": strict_metrics["RMSE"],
            "expanded_RMSE": expanded_metrics["RMSE"],
            "delta_RMSE": float(expanded_metrics["RMSE"] - strict_metrics["RMSE"]),
            "strict_weighted_RMSE": strict_metrics["weighted_RMSE"],
            "expanded_weighted_RMSE": expanded_metrics["weighted_RMSE"],
            "delta_weighted_RMSE": float(expanded_metrics["weighted_RMSE"] - strict_metrics["weighted_RMSE"]),
            "retained_multibeam_RMSE": retained_rmse,
            "gapfill_singlebeam_RMSE": gapfill_rmse,
            "gapfill_to_retained_RMSE_ratio": float(gapfill_rmse / retained_rmse) if retained_rmse else np.nan,
        })
    strict_vs_expanded = pd.DataFrame(sve_rows, columns=STRICT_VS_EXPANDED_COLUMNS)
    strict_vs_expanded = strict_vs_expanded.sort_values("strict_RMSE").reset_index(drop=True)

    safety = build_safety_checks(
        strict_table,
        strict_vs_expanded,
        strict_summary,
        expanded_summary,
        comparison,
        coverage_gain,
        stage6_gapfill,
    )
    return strict_table, strict_vs_expanded, safety


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Step 08 publication-ready strict-primary and strict-vs-expanded tables")
    parser.add_argument("--run-label", default="b_pub_tables", help="Run label for logs/reproducibility (default: b_pub_tables)")
    parser.add_argument("--confirm-publish", action="store_true", help="Required to write publication tables")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing publication-table outputs")
    parser.add_argument("--check-only", action="store_true", help="Run computations and safety checks without writing tables")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.check_only and not args.confirm_publish:
        raise SystemExit("--confirm-publish is required unless --check-only is set")

    log_path = LOG_DIR / f"19_step08_publication_tables_{args.run_label}.log"
    logger = setup_logging(log_path)
    started = time.time()
    logger.info("argv=%s", " ".join(sys.argv))
    logger.info("code_repo_root=%s", CODE_REPO_ROOT)
    logger.info("data_repo_root=%s", DATA_REPO_ROOT)
    logger.info("strict_dir=%s", STRICT_DIR)
    logger.info("expanded_dir=%s", EXPANDED_DIR)
    logger.info("stage6_dir=%s", STAGE6_DIR)
    logger.info("output_dir=%s", OUTPUT_DIR)
    logger.info("run_label=%s check_only=%s overwrite=%s", args.run_label, args.check_only, args.overwrite)

    try:
        require_inputs()
        if not args.check_only:
            ensure_outputs_available(output_paths(), args.overwrite)

        strict_table, strict_vs_expanded, safety = build_tables(logger)
        failed = safety[safety["status"].ne("PASS")]
        logger.info("safety_checks=%d failed=%d", len(safety), len(failed))
        if len(failed):
            logger.error("safety check failure(s):\n%s", failed.to_string(index=False))
            return 1

        if args.check_only:
            logger.info("check-only PASS elapsed_s=%.1f", time.time() - started)
            return 0

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        strict_tsv, strict_csv = atomic_write_table_pair(strict_table, "strict_primary_publication_table", args.overwrite)
        sve_tsv, sve_csv = atomic_write_table_pair(strict_vs_expanded, "strict_vs_expanded_publication_table", args.overwrite)
        safety_path = OUTPUT_DIR / "b_pub_safety_checks.tsv"
        atomic_write_text(dataframe_to_text(safety, "\t"), safety_path, args.overwrite)

        logger.info("wrote %s", strict_tsv)
        logger.info("wrote %s", strict_csv)
        logger.info("wrote %s", sve_tsv)
        logger.info("wrote %s", sve_csv)
        logger.info("wrote %s", safety_path)
        logger.info("completed PASS elapsed_s=%.1f", time.time() - started)
        return 0
    except Exception as exc:
        logger.error("failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
