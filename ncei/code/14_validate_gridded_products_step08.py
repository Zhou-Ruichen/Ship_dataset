#!/usr/bin/env python3
"""
14_validate_gridded_products_step08.py

Step 08 wrapper for validating configured gridded bathymetry products against
post-integration Step 07B validation-cell products.

READ-ONLY: does not modify Step 06B quality flags, Step 07B validation-cell
products, or gridded product files.

Reads:
  - ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet
  - ncei/derived/validation_cells_1min/expanded_primary_ship_cells.parquet
  - ncei/derived/validation_cells_1min/supplementary_singlebeam_cells.parquet/
  - ncei/derived/validation_cells_1min/regional_mrar_experiment_cells.parquet/
  - ncei/derived/validation_cells_1min/validation_cell_catalog.parquet/
  - ncei/derived/quality_flags_1min/cell_quality_flags_1min.parquet
  - jamstec/multibeam/configs/gridded_products_validation.yaml

Writes (smoke mode):
  - ncei/derived/model_validation_1min_<run-label>/validation_by_cell_<product>.parquet
  - ncei/derived/model_validation_1min_<run-label>/validation_sample_diagnostics.parquet + .tsv
  - ncei/derived/model_validation_1min_<run-label>/validation_metrics_summary.parquet + .tsv
  - ncei/derived/model_validation_1min_<run-label>/validation_metrics_by_<stratum>.parquet + .tsv
  - ncei/derived/model_validation_1min_<run-label>/strict_vs_expanded_comparison.parquet + .tsv
  - ncei/docs/step08_preflight_report_<run-label>.md
  - ncei/docs/step08_smoke_validation_report_<run-label>.md
  - ncei/output/logs/14_validate_gridded_products_step08_<run-label>.log

Usage:
    python3 ncei/code/14_validate_gridded_products_step08.py \
      --stage preflight --run-label smoke --overwrite

    python3 ncei/code/14_validate_gridded_products_step08.py \
      --stage smoke --run-label smoke --product-name GEBCO_2024 \
      --product-name ETOPO_2022 --sample-n-cells 2000 --overwrite

    # Full production validation is intentionally gated and must not be run
    # without explicit approval:
    python3 ncei/code/14_validate_gridded_products_step08.py \
      --stage full --run-label full --confirm-full
"""

from __future__ import annotations

import argparse
import gc
import importlib.util
import logging
import os
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.dataset as pds
import pyarrow.parquet as pq
import yaml

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent          # ncei/
REPO_ROOT = ROOT_DIR.parent           # ship/
JAMSTEC_ROOT = REPO_ROOT / "jamstec" / "multibeam"

VALIDATION_ROOT = ROOT_DIR / "derived" / "validation_cells_1min"
QUALITY_FLAGS_PATH = ROOT_DIR / "derived" / "quality_flags_1min" / "cell_quality_flags_1min.parquet"
DEFAULT_CONFIG = JAMSTEC_ROOT / "configs" / "gridded_products_validation.yaml"
LEGACY_STEP08_PATH = JAMSTEC_ROOT / "code" / "08_validate_gridded_products_against_ship_cells.py"
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"

EXPECTED_PRODUCTS: dict[str, dict[str, Any]] = {
    "strict_primary_multibeam_cells": {
        "path": VALIDATION_ROOT / "strict_primary_multibeam_cells.parquet",
        "expected_rows": 2_398_774,
        "product_role": "strict_primary_multibeam",
    },
    "expanded_primary_ship_cells": {
        "path": VALIDATION_ROOT / "expanded_primary_ship_cells.parquet",
        "expected_rows": 2_732_689,
        "product_role": "expanded_primary_ship",
    },
    "supplementary_singlebeam_cells": {
        "path": VALIDATION_ROOT / "supplementary_singlebeam_cells.parquet",
        "expected_rows": 12_277_633,
        "product_role": "supplementary_singlebeam",
    },
    "regional_mrar_experiment_cells": {
        "path": VALIDATION_ROOT / "regional_mrar_experiment_cells.parquet",
        "expected_rows": 9_019_383,
        "product_role": "regional_mrar_experiment",
    },
    "validation_cell_catalog": {
        "path": VALIDATION_ROOT / "validation_cell_catalog.parquet",
        "expected_rows": 24_029_705,
        "product_role": "validation_cell_catalog",
    },
}

PHYSICAL_REQUIRED_COLUMNS = [
    "cell_id",
    "lon_center",
    "lat_center",
    "representative_depth_m",
    "source_provider",
    "branch",
    "branch_role",
    "quality_tier",
    "evidence_class",
    "validation_weight",
    "n_unique_triples_total",
    "duplicate_ratio_cell",
]

OPTIONAL_CARRY_COLUMNS = [
    "lon_bin",
    "lat_bin",
    "lat_band_10deg",
    "n_points_pass_total",
    "n_track_cells",
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
    "source_risk_class",
    "auv_sentry_flag",
    "expanded_fill",
    "product_membership",
    "product_label",
]

SMOKE_PRODUCT_KEYS = ["strict_primary_multibeam_cells", "expanded_primary_ship_cells"]
FULL_STRICT_PRODUCT_KEY = "strict_primary_multibeam_cells"
FULL_FOOTPRINT_SKIP_REASON = "regional footprint product; not part of full global strict-primary run"
CELL_SIZE_DEG = 1.0 / 60.0
DEPTH_BINS = [
    (0, 1000, "0-1000m"),
    (1000, 3000, "1000-3000m"),
    (3000, 5000, "3000-5000m"),
    (5000, 7000, "5000-7000m"),
    (7000, 99999, ">7000m"),
]


# ---------------------------------------------------------------------------
# Paths / logging / atomic writes
# ---------------------------------------------------------------------------

def output_dir(run_label: str) -> Path:
    return ROOT_DIR / "derived" / f"model_validation_1min_{run_label}"


def setup_logging(run_label: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"14_validate_gridded_products_step08_{run_label}.log"
    logger = logging.getLogger("ncei_step08")
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


def atomic_write_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, path)


def atomic_write_tsv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Parquet helpers
# ---------------------------------------------------------------------------

def parquet_dataset(path: Path) -> pds.Dataset:
    if path.is_dir():
        return pds.dataset(str(path), format="parquet", partitioning="hive")
    return pds.dataset(str(path), format="parquet")


def row_count(path: Path) -> int:
    if not path.exists():
        return -1
    if path.is_dir():
        return int(parquet_dataset(path).count_rows())
    return int(pq.ParquetFile(path).metadata.num_rows)


def schema_names(path: Path) -> list[str]:
    if not path.exists():
        return []
    if path.is_dir():
        return list(parquet_dataset(path).schema.names)
    return list(pq.read_schema(path).names)


def read_parquet_columns(path: Path, columns: list[str]) -> pd.DataFrame:
    names = schema_names(path)
    read_cols = [c for c in columns if c in names]
    if not read_cols:
        return pd.DataFrame(index=range(row_count(path)))
    if path.is_dir():
        return parquet_dataset(path).to_table(columns=read_cols).to_pandas()
    return pd.read_parquet(path, columns=read_cols)


# ---------------------------------------------------------------------------
# Config / legacy sampler loading
# ---------------------------------------------------------------------------

def load_config(config_path: Path) -> dict[str, Any]:
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    if "products" not in config or not isinstance(config["products"], list):
        raise ValueError(f"Config missing products list: {config_path}")
    return config


def load_legacy_step08_module():
    if not LEGACY_STEP08_PATH.exists():
        raise FileNotFoundError(f"Legacy Step 08 sampler not found: {LEGACY_STEP08_PATH}")
    spec = importlib.util.spec_from_file_location("legacy_step08_sampler", LEGACY_STEP08_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec for {LEGACY_STEP08_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def enabled_products(config: dict[str, Any], product_names: list[str] | None) -> list[dict[str, Any]]:
    products = [p for p in config.get("products", []) if p.get("enabled", True)]
    if product_names:
        wanted = set(product_names)
        products = [p for p in products if p.get("name") in wanted]
        missing = wanted - {p.get("name") for p in products}
        if missing:
            raise ValueError(f"Requested product names not found/enabled in config: {sorted(missing)}")
    return products


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def check_product_schema(product_key: str, info: dict[str, Any]) -> dict[str, Any]:
    path = Path(info["path"])
    names = schema_names(path)
    names_set = set(names)
    n_rows = row_count(path)
    missing = [c for c in PHYSICAL_REQUIRED_COLUMNS if c not in names_set]
    optional_present = [c for c in OPTIONAL_CARRY_COLUMNS if c in names_set]

    status = "PASS"
    problems: list[str] = []
    if not path.exists():
        status = "FAIL"
        problems.append("path missing")
    if n_rows != int(info["expected_rows"]):
        status = "FAIL"
        problems.append(f"row count {n_rows:,} != expected {int(info['expected_rows']):,}")
    if missing:
        status = "FAIL"
        problems.append(f"missing physical columns: {missing}")

    return {
        "product_key": product_key,
        "product_role": info["product_role"],
        "path": str(path),
        "exists": path.exists(),
        "is_hive_dir": path.is_dir(),
        "row_count": n_rows,
        "expected_rows": int(info["expected_rows"]),
        "schema_columns": len(names),
        "missing_physical_columns": ",".join(missing),
        "optional_carry_columns_present": ",".join(optional_present),
        "status": status,
        "problems": "; ".join(problems),
    }


def depth_sign_check(product_key: str, info: dict[str, Any]) -> dict[str, Any]:
    path = Path(info["path"])
    if not path.exists() or "representative_depth_m" not in schema_names(path):
        return {
            "product_key": product_key,
            "status": "FAIL",
            "n_rows": row_count(path),
            "n_null_depth": None,
            "n_nonpositive_depth": None,
            "min_depth_m": np.nan,
            "max_depth_m": np.nan,
            "derived_elev_max_m": np.nan,
            "problem": "representative_depth_m unavailable",
        }
    depth = read_parquet_columns(path, ["representative_depth_m"])["representative_depth_m"]
    n_null = int(depth.isna().sum())
    n_nonpositive = int((depth <= 0).sum())
    status = "PASS" if n_null == 0 and n_nonpositive == 0 else "FAIL"
    problem = "" if status == "PASS" else f"null={n_null:,}, nonpositive={n_nonpositive:,}"
    return {
        "product_key": product_key,
        "status": status,
        "n_rows": int(len(depth)),
        "n_null_depth": n_null,
        "n_nonpositive_depth": n_nonpositive,
        "min_depth_m": float(depth.min()) if len(depth) else np.nan,
        "max_depth_m": float(depth.max()) if len(depth) else np.nan,
        "derived_elev_max_m": float((-depth).max()) if len(depth) else np.nan,
        "problem": problem,
    }


def role_separation_checks() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    strict = read_parquet_columns(
        EXPECTED_PRODUCTS["strict_primary_multibeam_cells"]["path"],
        ["source_provider", "branch", "branch_role"],
    )
    strict_singlebeam = int((strict.get("source_provider") == "ncei_singlebeam").sum()) if "source_provider" in strict else -1
    strict_mrar = int((strict.get("branch") == "regional_mrar").sum()) if "branch" in strict else -1
    checks.append({
        "check": "strict_primary_has_no_singlebeam",
        "status": "PASS" if strict_singlebeam == 0 else "FAIL",
        "details": f"ncei_singlebeam rows in strict={strict_singlebeam:,}",
    })
    checks.append({
        "check": "strict_primary_has_no_regional_mrar",
        "status": "PASS" if strict_mrar == 0 else "FAIL",
        "details": f"regional_mrar rows in strict={strict_mrar:,}",
    })

    expanded = read_parquet_columns(
        EXPECTED_PRODUCTS["expanded_primary_ship_cells"]["path"],
        ["source_provider", "branch", "expanded_fill"],
    )
    expanded_mrar = int((expanded.get("branch") == "regional_mrar").sum()) if "branch" in expanded else -1
    fill_rows = int(expanded.get("expanded_fill", pd.Series(dtype=bool)).fillna(False).sum()) if "expanded_fill" in expanded else -1
    sb_rows = int((expanded.get("source_provider") == "ncei_singlebeam").sum()) if "source_provider" in expanded else -1
    checks.append({
        "check": "expanded_primary_has_no_regional_mrar",
        "status": "PASS" if expanded_mrar == 0 else "FAIL",
        "details": f"regional_mrar rows in expanded={expanded_mrar:,}",
    })
    checks.append({
        "check": "expanded_primary_singlebeam_gapfill_marked",
        "status": "PASS" if fill_rows == sb_rows and fill_rows > 0 else "FAIL",
        "details": f"expanded_fill rows={fill_rows:,}; ncei_singlebeam rows={sb_rows:,}",
    })

    supplementary = read_parquet_columns(
        EXPECTED_PRODUCTS["supplementary_singlebeam_cells"]["path"],
        ["branch_role", "source_provider"],
    )
    supplementary_bad_role = int((supplementary.get("branch_role") != "supplementary_coverage").sum()) if "branch_role" in supplementary else -1
    checks.append({
        "check": "supplementary_is_non_primary_coverage",
        "status": "PASS" if supplementary_bad_role == 0 else "FAIL",
        "details": f"rows with branch_role != supplementary_coverage: {supplementary_bad_role:,}",
    })

    regional = read_parquet_columns(
        EXPECTED_PRODUCTS["regional_mrar_experiment_cells"]["path"],
        ["branch_role", "branch"],
    )
    regional_bad_role = int((regional.get("branch_role") != "regional_experiment").sum()) if "branch_role" in regional else -1
    checks.append({
        "check": "regional_mrar_is_experiment_only",
        "status": "PASS" if regional_bad_role == 0 else "FAIL",
        "details": f"rows with branch_role != regional_experiment: {regional_bad_role:,}",
    })

    return checks


def quality_sidecar_check() -> dict[str, Any]:
    names = schema_names(QUALITY_FLAGS_PATH)
    required = {"branch", "cell_id", "matched_rule_id"}
    missing = sorted(required - set(names))
    status = "PASS" if QUALITY_FLAGS_PATH.exists() and not missing else "FAIL"
    return {
        "check": "matched_rule_id_materialization_sidecar",
        "status": status,
        "path": str(QUALITY_FLAGS_PATH),
        "row_count": row_count(QUALITY_FLAGS_PATH),
        "details": "" if status == "PASS" else f"missing={missing}",
    }


def config_checks(config_path: Path, product_names: list[str] | None = None) -> list[dict[str, Any]]:
    config = load_config(config_path)
    products = enabled_products(config, product_names)
    required = {"name", "path", "format", "lon_name", "lat_name", "z_name", "z_convention", "sampling_method", "lon_convention"}
    rows = []
    for prod in products:
        missing = sorted(required - set(prod))
        ppath = Path(str(prod.get("path", "")))
        status = "PASS"
        problems = []
        if missing:
            status = "FAIL"
            problems.append(f"missing fields: {missing}")
        if not ppath.exists():
            status = "SKIP"
            problems.append(f"grid file not found: {ppath}")
        rows.append({
            "product_name": prod.get("name", ""),
            "status": status,
            "path": str(ppath),
            "exists": ppath.exists(),
            "size_gb": round(ppath.stat().st_size / 1e9, 3) if ppath.exists() and ppath.is_file() else np.nan,
            "format": prod.get("format", ""),
            "sampling_method": prod.get("sampling_method", ""),
            "z_convention": prod.get("z_convention", ""),
            "lon_convention": prod.get("lon_convention", ""),
            "has_footprint": bool(prod.get("footprint")),
            "problems": "; ".join(problems),
        })
    return rows


def make_preflight_report(schema_df: pd.DataFrame, sign_df: pd.DataFrame, role_df: pd.DataFrame,
                          sidecar: dict[str, Any], config_df: pd.DataFrame, status: str) -> str:
    lines = []
    lines.append("# Step 08 Preflight Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Overall status: **{status}**")
    lines.append("")
    lines.append("## 1. Step 07B product row counts and schema")
    lines.append("")
    lines.append(markdown_table(schema_df))
    lines.append("")
    lines.append("## 2. Derived required fields")
    lines.append("")
    lines.append("| Required field | Source | Status |")
    lines.append("|---|---|---|")
    lines.append("| depth_m_positive_down | derived from representative_depth_m | PASS |")
    lines.append("| elev_m | derived as -representative_depth_m | PASS |")
    lines.append("| product_role | derived from Step 07B product name | PASS |")
    lines.append("| source_role | represented by branch_role / branch | PASS |")
    lines.append("| matched_rule_id | Step 06B sidecar for NCEI rows; jamstec_legacy for JAMSTEC rows | " + sidecar["status"] + " |")
    lines.append("")
    lines.append("## 3. Z-sign sanity")
    lines.append("")
    lines.append(markdown_table(sign_df))
    lines.append("")
    lines.append("## 4. Product-role safety checks")
    lines.append("")
    lines.append(markdown_table(role_df))
    lines.append("")
    lines.append("## 5. Quality-rule provenance sidecar")
    lines.append("")
    lines.append(markdown_table(pd.DataFrame([sidecar])))
    lines.append("")
    lines.append("## 6. Gridded product config")
    lines.append("")
    lines.append(markdown_table(config_df))
    lines.append("")
    lines.append("## 7. Go / no-go")
    lines.append("")
    if status == "PASS":
        lines.append("Preflight passed. Smoke validation may proceed for explicitly selected products.")
    else:
        lines.append("Preflight failed. Do not run smoke or full validation until failures are resolved.")
    lines.append("")
    return "\n".join(lines)


def run_preflight(args, logger: logging.Logger) -> tuple[str, Path]:
    logger.info("Running Stage 1 preflight")
    schema_rows = [check_product_schema(k, v) for k, v in EXPECTED_PRODUCTS.items()]
    schema_df = pd.DataFrame(schema_rows)

    sign_rows = [depth_sign_check(k, v) for k, v in EXPECTED_PRODUCTS.items()]
    sign_df = pd.DataFrame(sign_rows)

    role_rows = role_separation_checks()
    role_df = pd.DataFrame(role_rows)

    sidecar = quality_sidecar_check()
    config_rows = config_checks(Path(args.config), None)
    config_df = pd.DataFrame(config_rows)

    failed = (
        (schema_df["status"] == "FAIL").any()
        or (sign_df["status"] == "FAIL").any()
        or (role_df["status"] == "FAIL").any()
        or sidecar["status"] == "FAIL"
        or (config_df["status"] == "FAIL").any()
    )
    status = "FAIL" if failed else "PASS"

    out_dir = output_dir(args.run_label)
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_tsv(schema_df, out_dir / "preflight_schema.tsv")
    atomic_write_tsv(sign_df, out_dir / "preflight_z_sign.tsv")
    atomic_write_tsv(role_df, out_dir / "preflight_role_checks.tsv")
    atomic_write_tsv(config_df, out_dir / "preflight_config_status.tsv")

    report = make_preflight_report(schema_df, sign_df, role_df, sidecar, config_df, status)
    report_path = DOCS_DIR / f"step08_preflight_report_{args.run_label}.md"
    atomic_write_text(report, report_path)
    logger.info("Preflight status: %s", status)
    logger.info("Wrote %s", report_path)
    return status, report_path


# ---------------------------------------------------------------------------
# Smoke validation helpers
# ---------------------------------------------------------------------------

def stable_hash_series(values: pd.Series) -> pd.Series:
    return pd.util.hash_pandas_object(values.astype(str), index=False).astype("uint64")


def deterministic_subset(df: pd.DataFrame, n: int, product_role: str) -> pd.DataFrame:
    if n <= 0 or len(df) <= n:
        return df.copy()

    work = df.copy()
    work["_stable_hash"] = stable_hash_series(work["cell_id"] + ":" + product_role)

    if "expanded_fill" in work.columns and work["expanded_fill"].fillna(False).any() and n >= 20:
        fill_target = max(1, int(round(n * 0.20)))
        non_fill_target = n - fill_target
        fill = work[work["expanded_fill"].fillna(False)].sort_values("_stable_hash").head(fill_target)
        non_fill = work[~work["expanded_fill"].fillna(False)].sort_values("_stable_hash").head(non_fill_target)
        out = pd.concat([non_fill, fill], ignore_index=True)
        if len(out) < n:
            used = set(out["cell_id"].astype(str) + "|" + out.get("branch", "").astype(str))
            rest = work[~(work["cell_id"].astype(str) + "|" + work.get("branch", "").astype(str)).isin(used)]
            out = pd.concat([out, rest.sort_values("_stable_hash").head(n - len(out))], ignore_index=True)
        return out.drop(columns=["_stable_hash"])

    return work.sort_values("_stable_hash").head(n).drop(columns=["_stable_hash"])


def read_validation_product_for_smoke(product_key: str, sample_n: int) -> pd.DataFrame:
    df = prepare_validation_cells(product_key, attach_rule_ids=False)
    df = deterministic_subset(df, sample_n, EXPECTED_PRODUCTS[product_key]["product_role"])
    df = attach_matched_rule_id(df)
    return df.reset_index(drop=True)


def attach_matched_rule_id(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "matched_rule_id" in out.columns:
        return out

    out["matched_rule_id"] = pd.NA
    jamstec_mask = out["source_provider"].astype(str).eq("jamstec")
    out.loc[jamstec_mask, "matched_rule_id"] = "jamstec_legacy"

    ncei = out.loc[~jamstec_mask, ["branch", "cell_id"]].drop_duplicates()
    if len(ncei) == 0:
        out["matched_rule_id"] = out["matched_rule_id"].fillna("not_applicable")
        return out

    branches = sorted(ncei["branch"].dropna().astype(str).unique())
    cell_ids = sorted(ncei["cell_id"].dropna().astype(str).unique())
    dataset = parquet_dataset(QUALITY_FLAGS_PATH)
    filt = pds.field("branch").isin(branches) & pds.field("cell_id").isin(cell_ids)
    lookup = dataset.to_table(columns=["branch", "cell_id", "matched_rule_id"], filter=filt).to_pandas()
    out = out.merge(lookup, on=["branch", "cell_id"], how="left", suffixes=("", "_from_sidecar"))
    out["matched_rule_id"] = out["matched_rule_id"].where(
        out["matched_rule_id"].notna(), out["matched_rule_id_from_sidecar"]
    )
    out.drop(columns=["matched_rule_id_from_sidecar"], inplace=True)
    out["matched_rule_id"] = out["matched_rule_id"].fillna("missing_from_quality_sidecar")
    return out


def prepare_validation_cells(product_key: str, attach_rule_ids: bool = True) -> pd.DataFrame:
    """Read a Step 07B validation product and derive the Step 08 physical fields."""
    info = EXPECTED_PRODUCTS[product_key]
    path = Path(info["path"])
    cols = PHYSICAL_REQUIRED_COLUMNS + OPTIONAL_CARRY_COLUMNS
    df = read_parquet_columns(path, cols)
    df["product_role"] = info["product_role"]
    df["source_role"] = df["branch_role"]
    df["depth_m_positive_down"] = df["representative_depth_m"].astype(float)
    df["elev_m"] = -df["depth_m_positive_down"]
    df["ship_depth_m"] = df["depth_m_positive_down"]
    df["ship_elev_m"] = df["elev_m"]
    if "expanded_fill" not in df.columns:
        df["expanded_fill"] = False
    if attach_rule_ids:
        df = attach_matched_rule_id(df)
    return df.reset_index(drop=True)


def assign_depth_bin(depth_m: float) -> str:
    if pd.isna(depth_m):
        return "unknown"
    for lo, hi, label in DEPTH_BINS:
        if lo <= float(depth_m) < hi:
            return label
    return ">7000m"


def assign_region_10deg(lon: float, lat: float) -> str:
    return f"lon{int(np.floor(lon / 10) * 10):04d}_lat{int(np.floor(lat / 10) * 10):04d}"


def sample_model_product(step08, prod: dict[str, Any], cells: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    ppath = Path(prod["path"])
    if not ppath.exists():
        return pd.DataFrame(), {"status": "skipped", "reason": f"file not found: {ppath}"}

    ds_obj = step08.open_product(prod)
    try:
        fill_value = step08.get_fill_value(ds_obj, prod)
        raw_values, effective_method = step08.sample_product(ds_obj, prod, cells)
        raw_values = np.asarray(raw_values, dtype=np.float64)
        model_elev_m, model_depth_m = apply_z_convention(raw_values, prod)
    finally:
        close = getattr(ds_obj, "close", None)
        if callable(close):
            close()

    result = build_cell_result(cells, prod, raw_values, model_elev_m, model_depth_m, effective_method, run_stage="smoke")
    diag = convention_diagnostic(prod, cells, raw_values, model_elev_m, model_depth_m, effective_method, fill_value)
    return result, diag


def _nearest_indices_1d(sorted_vals: np.ndarray, queries: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(sorted_vals, queries)
    idx = np.clip(idx, 1, len(sorted_vals) - 1)
    left = idx - 1
    d_left = np.abs(queries - sorted_vals[left])
    d_right = np.abs(queries - sorted_vals[idx])
    return np.where(d_left <= d_right, left, idx).astype(np.int64)


def _monotonic_coords(values: np.ndarray, name: str) -> tuple[np.ndarray, bool]:
    vals = np.asarray(values, dtype=np.float64)
    if vals.ndim != 1:
        raise ValueError(f"{name} coordinate must be 1-D")
    if len(vals) < 2:
        raise ValueError(f"{name} coordinate must have at least two values")
    ascending = bool(vals[0] < vals[-1])
    check_vals = vals if ascending else vals[::-1]
    if not np.all(np.diff(check_vals) > 0):
        raise ValueError(f"{name} coordinate is not strictly monotonic")
    return vals, ascending


def _searchsorted_monotonic(values: np.ndarray, queries: np.ndarray, ascending: bool, side: str = "left") -> np.ndarray:
    if ascending:
        return np.searchsorted(values, queries, side=side)
    reversed_idx = np.searchsorted(values[::-1], queries, side=side)
    return len(values) - reversed_idx


def _nearest_indices_monotonic(values: np.ndarray, queries: np.ndarray, ascending: bool) -> np.ndarray:
    if ascending:
        return _nearest_indices_1d(values, queries)
    reversed_idx = _nearest_indices_1d(values[::-1], queries)
    return (len(values) - 1 - reversed_idx).astype(np.int64)


def _coordinate_window(values: np.ndarray, center: float, half_width: float, ascending: bool) -> tuple[int, int]:
    lo_q = center - half_width
    hi_q = center + half_width
    if ascending:
        start = int(np.searchsorted(values, lo_q, side="left"))
        stop = int(np.searchsorted(values, hi_q, side="left"))
    else:
        start = int(len(values) - np.searchsorted(values[::-1], hi_q, side="right"))
        stop = int(len(values) - np.searchsorted(values[::-1], lo_q, side="right"))
    start = max(0, min(start, len(values)))
    stop = max(start, min(stop, len(values)))
    if stop == start:
        nearest = int(_nearest_indices_monotonic(values, np.array([center], dtype=np.float64), ascending)[0])
        start = max(0, nearest)
        stop = min(len(values), nearest + 1)
    return start, stop


def _read_netcdf_var_attributes(path: Path, var_name: str) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    try:
        import netCDF4
        with netCDF4.Dataset(path) as ds:
            var = ds.variables[var_name]
            for key in ("_FillValue", "missing_value", "scale_factor", "add_offset"):
                if hasattr(var, key):
                    value = getattr(var, key)
                    try:
                        attrs[key] = float(np.asarray(value).reshape(-1)[0])
                    except Exception:
                        attrs[key] = value
    except Exception:
        pass
    return attrs


def _apply_fill_scale_offset(values: np.ndarray, attrs: dict[str, Any]) -> np.ndarray:
    out = values.astype(np.float64, copy=False)
    fill_values = []
    for key in ("_FillValue", "missing_value"):
        if key in attrs:
            try:
                fill_values.append(float(attrs[key]))
            except (TypeError, ValueError):
                pass
    if fill_values:
        for fill in fill_values:
            out = np.where(out == fill, np.nan, out)
    scale = float(attrs.get("scale_factor", 1.0) or 1.0)
    offset = float(attrs.get("add_offset", 0.0) or 0.0)
    if scale != 1.0 or offset != 0.0:
        mask = np.isfinite(out)
        out = out.astype(np.float64, copy=True)
        out[mask] = out[mask] * scale + offset
    return out


def sample_product_full(prod: dict[str, Any], cells: pd.DataFrame, logger: logging.Logger) -> tuple[np.ndarray, str, dict[str, Any]]:
    """Sample a configured global product against all strict-primary cells.

    For high-resolution products configured as cell_median/cell_mean, this honors the
    configured method by aggregating the grid pixels inside each 1-minute validation
    cell. Unlike the legacy smoke sampler, this implementation does not downgrade
    global 15s products to center_nearest solely because the grid is large.
    """
    import xarray as xr
    from scipy.interpolate import RegularGridInterpolator

    path = Path(prod["path"])
    if not path.exists():
        raise FileNotFoundError(f"grid file not found: {path}")

    method = prod.get("sampling_method", "center_bilinear")
    z_name = prod["z_name"]
    lon_name = prod["lon_name"]
    lat_name = prod["lat_name"]
    lon_convention = prod.get("lon_convention", "-180_180")
    logger.info("Resolved sampling method for %s: configured=%s", prod["name"], method)

    ds = xr.open_dataset(path, decode_cf=False, mask_and_scale=False)
    try:
        lat_vals, lat_asc = _monotonic_coords(ds[lat_name].values, lat_name)
        lon_vals, lon_asc = _monotonic_coords(ds[lon_name].values, lon_name)
        lats = cells["lat_center"].to_numpy(dtype=np.float64)
        lons = cells["lon_center"].to_numpy(dtype=np.float64)
        query_lons = lons % 360.0 if lon_convention == "0_360" else lons
        da = ds[z_name]
        attrs = _read_netcdf_var_attributes(path, z_name)
        if not attrs:
            for key in ("_FillValue", "missing_value", "scale_factor", "add_offset"):
                if key in da.attrs:
                    attrs[key] = da.attrs[key]
        fill_value = attrs.get("_FillValue", attrs.get("missing_value", np.nan))

        if method == "center_bilinear":
            lat_start = _searchsorted_monotonic(lat_vals, np.array([float(np.nanmin(lats)) - 0.5]), lat_asc)[0]
            lat_stop = _searchsorted_monotonic(lat_vals, np.array([float(np.nanmax(lats)) + 0.5]), lat_asc, side="right")[0]
            lon_start = _searchsorted_monotonic(lon_vals, np.array([float(np.nanmin(query_lons)) - 0.5]), lon_asc)[0]
            lon_stop = _searchsorted_monotonic(lon_vals, np.array([float(np.nanmax(query_lons)) + 0.5]), lon_asc, side="right")[0]
            lat_start = max(0, int(lat_start)); lat_stop = min(len(lat_vals), int(lat_stop))
            lon_start = max(0, int(lon_start)); lon_stop = min(len(lon_vals), int(lon_stop))
            if lat_stop <= lat_start or lon_stop <= lon_start:
                raw_values = np.full(len(cells), np.nan, dtype=np.float64)
            else:
                z_sub = da[lat_start:lat_stop, lon_start:lon_stop].values
                z_sub = _apply_fill_scale_offset(np.asarray(z_sub), attrs)
                lat_sub = lat_vals[lat_start:lat_stop]
                lon_sub = lon_vals[lon_start:lon_stop]
                if not lat_asc:
                    lat_sub = lat_sub[::-1]
                    z_sub = z_sub[::-1, :]
                if not lon_asc:
                    lon_sub = lon_sub[::-1]
                    z_sub = z_sub[:, ::-1]
                interp = RegularGridInterpolator(
                    (lat_sub, lon_sub), z_sub,
                    method="linear", bounds_error=False, fill_value=np.nan,
                )
                raw_values = interp(np.column_stack([lats, query_lons])).astype(np.float64)
            effective_method = method
        elif method == "center_nearest":
            lat_idx = _nearest_indices_monotonic(lat_vals, lats, lat_asc)
            lon_idx = _nearest_indices_monotonic(lon_vals, query_lons, lon_asc)
            raw_values = np.full(len(cells), np.nan, dtype=np.float64)
            unique_lat_idx = np.unique(lat_idx)
            band_size = 500
            for band_start in range(0, len(unique_lat_idx), band_size):
                band_lats = unique_lat_idx[band_start:band_start + band_size]
                mask = np.isin(lat_idx, band_lats)
                lat_lo = int(max(0, band_lats.min()))
                lat_hi = int(min(len(lat_vals), band_lats.max() + 1))
                lon_lo = int(max(0, lon_idx[mask].min()))
                lon_hi = int(min(len(lon_vals), lon_idx[mask].max() + 1))
                chunk = _apply_fill_scale_offset(np.asarray(da[lat_lo:lat_hi, lon_lo:lon_hi].values), attrs)
                raw_values[mask] = chunk[lat_idx[mask] - lat_lo, lon_idx[mask] - lon_lo]
            effective_method = method
        elif method in ("cell_median", "cell_mean"):
            agg_func = np.nanmedian if method == "cell_median" else np.nanmean
            half_width = CELL_SIZE_DEG / 2.0
            lat_starts = _searchsorted_monotonic(lat_vals, lats - half_width, lat_asc)
            lat_stops = _searchsorted_monotonic(lat_vals, lats + half_width, lat_asc)
            lon_starts = _searchsorted_monotonic(lon_vals, query_lons - half_width, lon_asc)
            lon_stops = _searchsorted_monotonic(lon_vals, query_lons + half_width, lon_asc)
            lat_counts = np.maximum(lat_stops - lat_starts, 0)
            lon_counts = np.maximum(lon_stops - lon_starts, 0)

            if int(np.max(lat_counts)) <= 1 and int(np.max(lon_counts)) <= 1:
                logger.info("%s aggregate window is one pixel; using exact center_nearest-equivalent reads", prod["name"])
                lat_idx = _nearest_indices_monotonic(lat_vals, lats, lat_asc)
                lon_idx = _nearest_indices_monotonic(lon_vals, query_lons, lon_asc)
                raw_values = np.full(len(cells), np.nan, dtype=np.float64)
                unique_lat_idx = np.unique(lat_idx)
                band_size = 500
                for band_start in range(0, len(unique_lat_idx), band_size):
                    band_lats = unique_lat_idx[band_start:band_start + band_size]
                    mask = np.isin(lat_idx, band_lats)
                    lat_lo = int(max(0, band_lats.min()))
                    lat_hi = int(min(len(lat_vals), band_lats.max() + 1))
                    lon_lo = int(max(0, lon_idx[mask].min()))
                    lon_hi = int(min(len(lon_vals), lon_idx[mask].max() + 1))
                    chunk = _apply_fill_scale_offset(np.asarray(da[lat_lo:lat_hi, lon_lo:lon_hi].values), attrs)
                    raw_values[mask] = chunk[lat_idx[mask] - lat_lo, lon_idx[mask] - lon_lo]
                effective_method = method
            else:
                logger.info(
                    "%s aggregate window max pixels: lat=%s lon=%s; grouping %s unique cells",
                    prod["name"], int(lat_counts.max()), int(lon_counts.max()), len(cells),
                )
                raw_values = np.full(len(cells), np.nan, dtype=np.float64)
                groups: dict[tuple[int, int, int, int], list[int]] = {}
                for idx, (lat_s, lat_e, lon_s, lon_e) in enumerate(zip(lat_starts, lat_stops, lon_starts, lon_stops)):
                    lat_s = int(max(0, min(lat_s, len(lat_vals))))
                    lat_e = int(max(lat_s, min(lat_e, len(lat_vals))))
                    lon_s = int(max(0, min(lon_s, len(lon_vals))))
                    lon_e = int(max(lon_s, min(lon_e, len(lon_vals))))
                    if lat_e <= lat_s:
                        lat_s, lat_e = _coordinate_window(lat_vals, float(lats[idx]), half_width, lat_asc)
                    if lon_e <= lon_s:
                        lon_s, lon_e = _coordinate_window(lon_vals, float(query_lons[idx]), half_width, lon_asc)
                    groups.setdefault((lat_s, lat_e, lon_s, lon_e), []).append(idx)
                logger.info("%s aggregate unique grid windows: %s", prod["name"], len(groups))
                for n_done, (window, idxs) in enumerate(groups.items(), start=1):
                    if n_done % 250000 == 0:
                        logger.info("%s aggregate windows processed: %s/%s", prod["name"], n_done, len(groups))
                    lat_s, lat_e, lon_s, lon_e = window
                    arr = _apply_fill_scale_offset(np.asarray(da[lat_s:lat_e, lon_s:lon_e].values), attrs)
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", category=RuntimeWarning)
                        val = float(agg_func(arr)) if arr.size else np.nan
                    raw_values[idxs] = val
                effective_method = method
        else:
            raise ValueError(f"Unknown sampling_method: {method}")
    finally:
        ds.close()

    return raw_values, effective_method, {"fill_value": fill_value}


def apply_z_convention(raw_values: np.ndarray, prod_cfg: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    z_conv = prod_cfg.get("z_convention", "elevation_negative_ocean")
    if z_conv == "depth_positive_down":
        model_elev_m = -raw_values
    else:
        model_elev_m = raw_values.copy()
    return model_elev_m, -model_elev_m


def build_cell_result(cells: pd.DataFrame, prod: dict[str, Any], raw_values: np.ndarray,
                      model_elev_m: np.ndarray, model_depth_m: np.ndarray,
                      effective_method: str, run_stage: str = "smoke") -> pd.DataFrame:
    keep_cols = [
        "cell_id", "lon_center", "lat_center", "lon_bin", "lat_bin", "lat_band_10deg",
        "representative_depth_m", "depth_m_positive_down", "elev_m", "ship_depth_m", "ship_elev_m",
        "product_role", "source_provider", "branch", "branch_role", "source_role",
        "quality_tier", "evidence_class", "validation_weight", "matched_rule_id",
        "n_unique_triples_total", "n_points_pass_total", "n_track_cells", "n_tracks",
        "duplicate_ratio_cell", "manual_review_any", "low_evidence_flag", "n_cross_branch_overlap",
        "depth_bin", "source_risk_class", "auv_sentry_flag", "expanded_fill",
        "precedence_resolution", "final_primary_source", "source_dataset", "dominant_file_id",
        "enforced_rules_version", "merge_version", "validation_product_version",
    ]
    available = [c for c in keep_cols if c in cells.columns]
    out = cells[available].copy()
    out["product_name"] = prod["name"]
    out["raw_z"] = raw_values
    out["model_elev_m"] = model_elev_m
    out["model_depth_m"] = model_depth_m
    out["elev_error_m"] = model_elev_m - out["ship_elev_m"].to_numpy(dtype=np.float64)
    out["depth_error_m"] = model_depth_m - out["ship_depth_m"].to_numpy(dtype=np.float64)
    out["abs_elev_error_m"] = np.abs(out["elev_error_m"])
    out["sampling_method"] = effective_method
    out["config_sampling_method"] = prod.get("sampling_method", "")
    out["z_convention"] = prod.get("z_convention", "")
    out["lon_convention"] = prod.get("lon_convention", "")
    out["run_stage"] = run_stage
    if "depth_bin" not in out.columns or pd.api.types.is_numeric_dtype(out.get("depth_bin")):
        out["depth_bin_label"] = out["ship_depth_m"].apply(assign_depth_bin)
    else:
        out["depth_bin_label"] = out["depth_bin"].astype(str)
    if "lat_band_10deg" not in out.columns:
        out["lat_band_10deg"] = (np.floor(out["lat_center"] / 10.0) * 10).astype(int)
    region_lon = (np.floor(out["lon_center"].to_numpy(dtype=np.float64) / 10.0) * 10).astype(int)
    region_lat = (np.floor(out["lat_center"].to_numpy(dtype=np.float64) / 10.0) * 10).astype(int)
    out["region_10deg"] = [f"lon{lon:04d}_lat{lat:04d}" for lon, lat in zip(region_lon, region_lat)]
    return out


def convention_diagnostic(prod: dict[str, Any], cells: pd.DataFrame, raw_values: np.ndarray,
                          model_elev_m: np.ndarray, model_depth_m: np.ndarray,
                          sampling_method: str, fill_value: Any) -> dict[str, Any]:
    ship_elev = cells["ship_elev_m"].to_numpy(dtype=np.float64)
    valid = np.isfinite(model_elev_m) & np.isfinite(ship_elev)
    corr = np.nan
    if int(valid.sum()) >= 2:
        corr = float(np.corrcoef(model_elev_m[valid], ship_elev[valid])[0, 1])
    return {
        "product_name": prod["name"],
        "sampling_method": sampling_method,
        "z_convention": prod.get("z_convention", ""),
        "lon_convention": prod.get("lon_convention", ""),
        "fill_value": fill_value,
        "n_cells_requested": int(len(cells)),
        "valid_count": int(valid.sum()),
        "nodata_count": int((~np.isfinite(raw_values)).sum()),
        "raw_z_min": float(np.nanmin(raw_values)) if np.isfinite(raw_values).any() else np.nan,
        "raw_z_max": float(np.nanmax(raw_values)) if np.isfinite(raw_values).any() else np.nan,
        "model_depth_min": float(np.nanmin(model_depth_m)) if np.isfinite(model_depth_m).any() else np.nan,
        "model_depth_max": float(np.nanmax(model_depth_m)) if np.isfinite(model_depth_m).any() else np.nan,
        "elevation_correlation": corr,
        "sign_error_suspected": bool(pd.notna(corr) and corr < 0),
    }


# ---------------------------------------------------------------------------
# Metrics / reports
# ---------------------------------------------------------------------------

def compute_metric_row(sub: pd.DataFrame, extras: dict[str, Any]) -> dict[str, Any]:
    valid = sub[np.isfinite(sub["elev_error_m"])].copy()
    errors = valid["elev_error_m"].to_numpy(dtype=np.float64)
    weights = valid["validation_weight"].to_numpy(dtype=np.float64) if len(valid) else np.array([], dtype=np.float64)
    weights = np.where(np.isfinite(weights) & (weights > 0), weights, np.nan)
    abs_err = np.abs(errors)
    row: dict[str, Any] = {
        "requested_cells": int(len(sub)),
        "count": int(len(errors)),
        "nodata_count": int(len(sub) - len(errors)),
        "coverage_fraction": float(len(errors) / len(sub)) if len(sub) else 0.0,
        "bias": np.nan,
        "MAE": np.nan,
        "RMSE": np.nan,
        "weighted_MAE": np.nan,
        "weighted_RMSE": np.nan,
        "median_error": np.nan,
        "MAD": np.nan,
        "abs_error_p90": np.nan,
        "abs_error_p95": np.nan,
        "abs_error_p99": np.nan,
    }
    if len(errors):
        med = float(np.median(errors))
        row.update({
            "bias": float(np.mean(errors)),
            "MAE": float(np.mean(abs_err)),
            "RMSE": float(np.sqrt(np.mean(errors ** 2))),
            "median_error": med,
            "MAD": float(np.median(np.abs(errors - med))),
            "abs_error_p90": float(np.percentile(abs_err, 90)),
            "abs_error_p95": float(np.percentile(abs_err, 95)),
            "abs_error_p99": float(np.percentile(abs_err, 99)),
        })
        wmask = np.isfinite(weights)
        if int(wmask.sum()) > 0:
            w = weights[wmask]
            e = errors[wmask]
            ae = np.abs(e)
            row["weighted_MAE"] = float(np.sum(w * ae) / np.sum(w))
            row["weighted_RMSE"] = float(np.sqrt(np.sum(w * (e ** 2)) / np.sum(w)))
    row.update(extras)
    return row


def build_metrics(cells_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    group_base = ["product_name", "product_role", "sampling_method"]
    outputs: dict[str, pd.DataFrame] = {}

    summary_rows = []
    for keys, sub in cells_df.groupby(group_base, dropna=False):
        product_name, product_role, sampling_method = keys
        summary_rows.append(compute_metric_row(sub, {
            "product_name": product_name,
            "product_role": product_role,
            "sampling_method": sampling_method,
            "stratification": "overall",
            "stratum": "all",
        }))
    outputs["summary"] = pd.DataFrame(summary_rows)

    strata = {
        "quality_tier": "quality_tier",
        "evidence_class": "evidence_class",
        "source_role": "source_role",
        "branch": "branch",
        "depth_bin": "depth_bin_label",
        "lat_band": "lat_band_10deg",
        "region_10deg": "region_10deg",
    }
    for out_name, col in strata.items():
        rows = []
        if col not in cells_df.columns:
            outputs[f"by_{out_name}"] = pd.DataFrame()
            continue
        for keys, prod_df in cells_df.groupby(group_base, dropna=False):
            product_name, product_role, sampling_method = keys
            for stratum, sub in prod_df.groupby(col, dropna=False):
                rows.append(compute_metric_row(sub, {
                    "product_name": product_name,
                    "product_role": product_role,
                    "sampling_method": sampling_method,
                    "stratification": out_name,
                    "stratum": str(stratum),
                }))
        outputs[f"by_{out_name}"] = pd.DataFrame(rows)
    return outputs


def build_strict_expanded_comparison(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (pname, method), sub in summary.groupby(["product_name", "sampling_method"], dropna=False):
        strict = sub[sub["product_role"] == "strict_primary_multibeam"]
        expanded = sub[sub["product_role"] == "expanded_primary_ship"]
        if len(strict) == 0 or len(expanded) == 0:
            continue
        s = strict.iloc[0]
        e = expanded.iloc[0]
        rows.append({
            "product_name": pname,
            "sampling_method": method,
            "strict_count": int(s["count"]),
            "expanded_count": int(e["count"]),
            "coverage_gain_count": int(e["count"] - s["count"]),
            "coverage_gain_fraction_vs_strict": float((e["count"] - s["count"]) / s["count"]) if s["count"] else np.nan,
            "strict_MAE": float(s["MAE"]),
            "expanded_MAE": float(e["MAE"]),
            "delta_MAE_expanded_minus_strict": float(e["MAE"] - s["MAE"]),
            "strict_RMSE": float(s["RMSE"]),
            "expanded_RMSE": float(e["RMSE"]),
            "delta_RMSE_expanded_minus_strict": float(e["RMSE"] - s["RMSE"]),
            "strict_weighted_RMSE": float(s["weighted_RMSE"]),
            "expanded_weighted_RMSE": float(e["weighted_RMSE"]),
            "delta_weighted_RMSE_expanded_minus_strict": float(e["weighted_RMSE"] - s["weighted_RMSE"]),
        })
    return pd.DataFrame(rows)


def fmt(value: Any, places: int = 2) -> str:
    if pd.isna(value):
        return "N/A"
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.{places}f}"
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    return str(value)


def markdown_table(df: pd.DataFrame) -> str:
    """Render a small Markdown table without pandas' optional tabulate dependency."""
    if df is None or len(df) == 0:
        return "_(none)_"
    work = df.copy()
    cols = list(work.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in work.iterrows():
        lines.append("| " + " | ".join(fmt(row.get(c)) for c in cols) + " |")
    return "\n".join(lines)


def make_full_report(metrics: dict[str, pd.DataFrame], diagnostics: pd.DataFrame, product_status: pd.DataFrame,
                     preflight_status: str, safety_checks: pd.DataFrame, elapsed: float,
                     status: str, out_dir: Path, product_key: str = FULL_STRICT_PRODUCT_KEY) -> str:
    product_info = EXPECTED_PRODUCTS[product_key]
    product_role = product_info["product_role"]
    if product_role == "strict_primary_multibeam":
        title_label = "Strict-Primary"
        status_label = "Full strict-primary status"
    else:
        title_label = "Expanded-Primary"
        status_label = "Full expanded-primary status"
    lines = []
    lines.append(f"# Step 08 {title_label} Full Global Validation Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Elapsed: {elapsed:.1f}s")
    lines.append(f"Preflight status: **{preflight_status}**")
    lines.append(f"{status_label}: **{status}**")
    lines.append(f"Output directory: `{out_dir}`")
    lines.append("")
    lines.append("## 1. Input baseline")
    lines.append("")
    lines.append(markdown_table(pd.DataFrame([{
        "product": product_key,
        "product_role": product_info["product_role"],
        "rows": row_count(product_info["path"]),
        "path": str(product_info["path"]),
    }])))
    lines.append("")
    lines.append("## 2. Safety checks")
    lines.append("")
    lines.append(markdown_table(safety_checks))
    lines.append("")
    lines.append("## 3. Product status")
    lines.append("")
    lines.append(markdown_table(product_status))
    lines.append("")
    lines.append("## 4. Overall metrics")
    lines.append("")
    summary = metrics.get("summary", pd.DataFrame()).copy()
    display_cols = [
        "product_name", "product_role", "sampling_method", "requested_cells", "count", "nodata_count",
        "coverage_fraction", "bias", "MAE", "RMSE", "weighted_MAE", "weighted_RMSE",
        "median_error", "MAD", "abs_error_p90", "abs_error_p95", "abs_error_p99",
    ]
    if len(summary):
        lines.append(markdown_table(summary[[c for c in display_cols if c in summary.columns]]))
    else:
        lines.append("No metrics produced.")
    lines.append("")
    lines.append("## 5. Product convention diagnostics")
    lines.append("")
    lines.append(markdown_table(diagnostics))
    lines.append("")
    lines.append("## 6. Recommendation")
    lines.append("")
    if product_role == "strict_primary_multibeam":
        if status == "PASS":
            lines.append("Proceed to expanded_primary sensitivity validation if the objective is to quantify high-confidence singlebeam gap-fill coverage and metric sensitivity. Keep strict_primary as the main global baseline.")
        else:
            lines.append("Do not proceed to expanded_primary sensitivity validation until the failed strict-primary checks/products are reviewed.")
    else:
        if status == "PASS":
            lines.append("Expanded-primary sensitivity outputs are available. Run `ncei/code/15_strict_vs_expanded_compare_step08.py` to compute strict-vs-expanded deltas and coverage gain; expanded_primary remains a sensitivity product and does not replace strict_primary as the main global baseline.")
        else:
            lines.append("Do not interpret expanded_primary as a sensitivity comparison until the failed expanded-primary checks are resolved.")
    lines.append("")
    return "\n".join(lines)


def full_safety_checks(cells: pd.DataFrame, diagnostics: pd.DataFrame, product_status: pd.DataFrame,
                       product_key: str = FULL_STRICT_PRODUCT_KEY) -> pd.DataFrame:
    checks: list[dict[str, Any]] = []
    product_info = EXPECTED_PRODUCTS[product_key]
    product_role = product_info["product_role"]
    expected_rows = int(product_info["expected_rows"])
    role_slug = "strict_primary" if product_role == "strict_primary_multibeam" else "expanded_primary"
    checks.append({
        "check": "input_row_count",
        "status": "PASS" if len(cells) == expected_rows else "FAIL",
        "details": f"rows={len(cells):,}; expected={expected_rows:,}",
    })
    singlebeam = int((cells["source_provider"].astype(str) == "ncei_singlebeam").sum())
    regional = int((cells["branch"].astype(str) == "regional_mrar").sum())
    if product_role == "strict_primary_multibeam":
        checks.append({"check": "no_singlebeam_in_strict_primary", "status": "PASS" if singlebeam == 0 else "FAIL", "details": f"ncei_singlebeam rows={singlebeam:,}"})
        checks.append({"check": "no_regional_mrar_in_strict_primary", "status": "PASS" if regional == 0 else "FAIL", "details": f"regional_mrar rows={regional:,}"})
    else:
        # expanded_primary_ship: singlebeam IS expected as gap-fill, but only marked via expanded_fill; regional MRAR still forbidden.
        if "expanded_fill" in cells.columns:
            expanded_fill_rows = int(cells["expanded_fill"].fillna(False).astype(bool).sum())
        else:
            expanded_fill_rows = -1
        expected_expanded_fill = 333_915
        checks.append({"check": "no_regional_mrar_in_expanded_primary",
                       "status": "PASS" if regional == 0 else "FAIL",
                       "details": f"regional_mrar rows={regional:,}"})
        checks.append({"check": "expanded_fill_count_matches_preflight",
                       "status": "PASS" if expanded_fill_rows == expected_expanded_fill else "FAIL",
                       "details": f"expanded_fill rows={expanded_fill_rows:,}; expected={expected_expanded_fill:,}"})
        checks.append({"check": "singlebeam_only_marked_as_expanded_fill",
                       "status": "PASS" if (expanded_fill_rows >= 0 and singlebeam == expanded_fill_rows) else "FAIL",
                       "details": f"ncei_singlebeam rows={singlebeam:,}; expanded_fill rows={expanded_fill_rows:,}"})
    weights_ok = bool(cells["validation_weight"].notna().all())
    checks.append({"check": "validation_weight_preserved", "status": "PASS" if weights_ok else "FAIL", "details": f"null weights={int(cells['validation_weight'].isna().sum()):,}"})
    for col in ["quality_tier", "evidence_class", "matched_rule_id"]:
        nulls = int(cells[col].isna().sum()) if col in cells.columns else len(cells)
        checks.append({"check": f"{col}_preserved", "status": "PASS" if nulls == 0 else "FAIL", "details": f"null {col}={nulls:,}"})
    if len(diagnostics):
        bad = diagnostics[diagnostics["sign_error_suspected"].fillna(False).astype(bool)]
        details = ",".join(sorted(bad["product_name"].astype(str).unique())) if len(bad) else "none"
        checks.append({"check": "sign_error_suspected_false", "status": "PASS" if len(bad) == 0 else "FAIL", "details": details})
    else:
        checks.append({"check": "sign_error_suspected_false", "status": "FAIL", "details": "no diagnostics"})
    errors = product_status[product_status["status"].eq("error")] if len(product_status) else product_status
    checks.append({"check": "model_errors_do_not_corrupt_other_outputs", "status": "PASS" if len(errors) == 0 else "WARN", "details": f"error products={len(errors)}"})
    checks.append({"check": "no_model_residual_filtering", "status": "PASS", "details": f"all {role_slug} rows are retained before model nodata masking in metrics"})
    return pd.DataFrame(checks)


def run_full(args, logger: logging.Logger) -> tuple[str, Path]:
    product_key = getattr(args, "validation_product", FULL_STRICT_PRODUCT_KEY)
    product_info = EXPECTED_PRODUCTS[product_key]
    product_role = product_info["product_role"]
    role_slug = "strict_primary" if product_role == "strict_primary_multibeam" else "expanded_primary"
    role_label = "strict-primary" if role_slug == "strict_primary" else "expanded-primary"
    run_stage_label = f"full_{role_slug}"

    logger.info("Running Stage %s full %s global validation", "3" if role_slug == "strict_primary" else "4", role_label)
    if not args.confirm_full:
        raise RuntimeError(f"Full {role_label} validation requires --confirm-full")
    if args.run_label == "smoke":
        raise RuntimeError("Refusing to write full outputs to smoke run-label")

    preflight_status, preflight_report = run_preflight(args, logger)
    if preflight_status != "PASS":
        raise RuntimeError(f"Preflight failed; see {preflight_report}")

    config = load_config(Path(args.config))
    default_products = ["GEBCO_2024", "ETOPO_2022", "SRTM15_V2.7", "SDUST_2023", "TOPO_25.1", "SWOT_T1"]
    product_names = args.product_name or default_products
    products = enabled_products(config, product_names)
    products_by_name = {p["name"]: p for p in products}
    ordered_products = [products_by_name[name] for name in product_names if name in products_by_name]

    out_dir = output_dir(args.run_label)
    if out_dir.exists() and any(out_dir.iterdir()) and not args.overwrite:
        raise RuntimeError(f"Output dir has files (use --overwrite only if intentionally replacing this production run): {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    cells = prepare_validation_cells(product_key, attach_rule_ids=True)
    logger.info("Loaded %s cells: %s", role_label, len(cells))
    expected_rows = int(product_info["expected_rows"])
    if len(cells) != expected_rows:
        raise RuntimeError(f"{role_label.capitalize()} row count {len(cells):,} != expected {expected_rows:,}")
    if product_role == "strict_primary_multibeam":
        if int((cells["source_provider"].astype(str) == "ncei_singlebeam").sum()) != 0:
            raise RuntimeError("Strict-primary input contains ncei_singlebeam rows")
        if int((cells["branch"].astype(str) == "regional_mrar").sum()) != 0:
            raise RuntimeError("Strict-primary input contains regional_mrar rows")
    else:
        if int((cells["branch"].astype(str) == "regional_mrar").sum()) != 0:
            raise RuntimeError("Expanded-primary input contains regional_mrar rows")

    logger.info("Configured full-run products and sampling methods:")
    for prod in ordered_products:
        logger.info("  %s: sampling_method=%s z_convention=%s lon_convention=%s footprint=%s",
                    prod.get("name"), prod.get("sampling_method"), prod.get("z_convention"),
                    prod.get("lon_convention"), bool(prod.get("footprint")))

    diagnostics: list[dict[str, Any]] = []
    product_status: list[dict[str, Any]] = []
    metric_frames: dict[str, list[pd.DataFrame]] = {k: [] for k in [
        "summary", "by_quality_tier", "by_evidence_class", "by_source_role", "by_branch",
        "by_depth_bin", "by_lat_band", "by_region_10deg",
    ]}
    t0 = time.time()

    for prod in ordered_products:
        pname = prod["name"]
        product_t0 = time.time()
        if prod.get("footprint"):
            reason = FULL_FOOTPRINT_SKIP_REASON
            logger.info("Skipping %s: %s", pname, reason)
            product_status.append({"product_name": pname, "status": "skipped", "reason": reason, "rows": 0, "elapsed_s": 0.0})
            continue
        if not Path(prod["path"]).exists():
            reason = f"file not found: {prod['path']}"
            logger.warning("Skipping %s: %s", pname, reason)
            product_status.append({"product_name": pname, "status": "skipped", "reason": reason, "rows": 0, "elapsed_s": 0.0})
            continue

        logger.info("Full %s sampling product %s", role_label, pname)
        try:
            raw_values, effective_method, sample_meta = sample_product_full(prod, cells, logger)
            model_elev_m, model_depth_m = apply_z_convention(raw_values, prod)
            result = build_cell_result(cells, prod, raw_values, model_elev_m, model_depth_m, effective_method, run_stage=run_stage_label)
            diag = convention_diagnostic(prod, cells, raw_values, model_elev_m, model_depth_m, effective_method, sample_meta.get("fill_value", np.nan))
            diagnostics.append(diag)
            product_metrics = build_metrics(result)
            for key, df in product_metrics.items():
                if len(df):
                    metric_frames.setdefault(key, []).append(df)
            out_path = out_dir / f"full_validation_by_cell_{role_slug}_{pname}.parquet"
            atomic_write_parquet(result, out_path)
            product_status.append({
                "product_name": pname,
                "status": "ok",
                "reason": "",
                "rows": int(len(result)),
                "valid_count": int(np.isfinite(result["elev_error_m"]).sum()),
                "nodata_count": int((~np.isfinite(result["elev_error_m"])).sum()),
                "configured_sampling_method": prod.get("sampling_method", ""),
                "resolved_sampling_method": effective_method,
                "elapsed_s": round(time.time() - product_t0, 1),
            })
            del raw_values, model_elev_m, model_depth_m, result, product_metrics
            gc.collect()
        except Exception as exc:
            logger.exception("Product %s failed; recording skip/error and continuing", pname)
            product_status.append({
                "product_name": pname,
                "status": "error",
                "reason": str(exc),
                "rows": 0,
                "elapsed_s": round(time.time() - product_t0, 1),
            })
            gc.collect()
            continue

    metrics = {key: (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()) for key, frames in metric_frames.items()}
    diagnostics_df = pd.DataFrame(diagnostics)
    product_status_df = pd.DataFrame(product_status)
    skipped_df = product_status_df[product_status_df["status"].isin(["skipped", "error"])] if len(product_status_df) else pd.DataFrame()
    safety_df = full_safety_checks(cells, diagnostics_df, product_status_df, product_key=product_key)

    metric_stems = {
        "summary": f"full_validation_metrics_summary_{role_slug}",
        "by_quality_tier": f"full_validation_metrics_by_quality_tier_{role_slug}",
        "by_evidence_class": f"full_validation_metrics_by_evidence_class_{role_slug}",
        "by_source_role": f"full_validation_metrics_by_source_role_{role_slug}",
        "by_branch": f"full_validation_metrics_by_branch_{role_slug}",
        "by_depth_bin": f"full_validation_metrics_by_depth_bin_{role_slug}",
        "by_lat_band": f"full_validation_metrics_by_lat_band_10deg_{role_slug}",
        "by_region_10deg": f"full_validation_metrics_by_region_10deg_{role_slug}",
    }
    for key, stem in metric_stems.items():
        df = metrics.get(key, pd.DataFrame())
        if len(df) == 0:
            continue
        atomic_write_parquet(df, out_dir / f"{stem}.parquet")
        atomic_write_tsv(df, out_dir / f"{stem}.tsv")

    atomic_write_parquet(diagnostics_df, out_dir / f"full_validation_sample_diagnostics_{role_slug}.parquet")
    atomic_write_tsv(diagnostics_df, out_dir / f"full_validation_sample_diagnostics_{role_slug}.tsv")
    atomic_write_parquet(product_status_df, out_dir / f"full_validation_product_status_{role_slug}.parquet")
    atomic_write_tsv(product_status_df, out_dir / f"full_validation_product_status_{role_slug}.tsv")
    atomic_write_tsv(skipped_df, out_dir / "skipped_products.tsv")
    atomic_write_tsv(safety_df, out_dir / f"full_validation_safety_checks_{role_slug}.tsv")

    failed_safety = bool((safety_df["status"] == "FAIL").any())
    sign_fail = bool(len(diagnostics_df) and diagnostics_df["sign_error_suspected"].fillna(False).astype(bool).any())
    no_success = bool((product_status_df["status"] == "ok").sum() == 0) if len(product_status_df) else True
    status = "FAIL" if failed_safety or sign_fail or no_success else "PASS"
    elapsed = time.time() - t0
    report = make_full_report(metrics, diagnostics_df, product_status_df, preflight_status, safety_df, elapsed, status, out_dir, product_key=product_key)
    report_path = DOCS_DIR / f"{role_slug}_global_validation_report.md"
    atomic_write_text(report, report_path)
    run_label_report_path = DOCS_DIR / f"{role_slug}_global_validation_report_{args.run_label}.md"
    if run_label_report_path != report_path:
        atomic_write_text(report, run_label_report_path)
    logger.info("Full %s status: %s", role_label, status)
    logger.info("Wrote %s", report_path)
    return status, report_path


def make_smoke_report(cells_df: pd.DataFrame, metrics: dict[str, pd.DataFrame], comparison: pd.DataFrame,
                      diagnostics: pd.DataFrame, product_status: pd.DataFrame, preflight_status: str,
                      elapsed: float, go_no_go: str) -> str:
    lines = []
    lines.append("# Step 08 Smoke Validation Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Elapsed: {elapsed:.1f}s")
    lines.append(f"Preflight status: **{preflight_status}**")
    lines.append(f"Smoke status: **{go_no_go}**")
    lines.append(f"Validation rows: {len(cells_df):,}")
    lines.append("")

    lines.append("## 1. Input products detected")
    lines.append("")
    input_rows = []
    for key, info in EXPECTED_PRODUCTS.items():
        input_rows.append({
            "product": key,
            "product_role": info["product_role"],
            "rows": row_count(info["path"]),
            "path": str(info["path"]),
        })
    lines.append(markdown_table(pd.DataFrame(input_rows)))
    lines.append("")

    lines.append("## 2. Model status")
    lines.append("")
    lines.append(markdown_table(product_status))
    lines.append("")

    lines.append("## 3. Overall smoke metrics")
    lines.append("")
    summary = metrics["summary"].copy()
    display_cols = [
        "product_name", "product_role", "sampling_method", "count", "coverage_fraction",
        "bias", "MAE", "RMSE", "weighted_MAE", "weighted_RMSE", "median_error",
        "MAD", "abs_error_p95",
    ]
    if len(summary):
        lines.append(markdown_table(summary[display_cols]))
    else:
        lines.append("No metrics produced.")
    lines.append("")

    lines.append("## 4. Strict vs expanded comparison")
    lines.append("")
    if len(comparison):
        lines.append(markdown_table(comparison))
    else:
        lines.append("No strict/expanded comparison was produced.")
    lines.append("")

    lines.append("## 5. Product convention diagnostics")
    lines.append("")
    if len(diagnostics):
        lines.append(markdown_table(diagnostics))
    else:
        lines.append("No diagnostics produced.")
    lines.append("")

    lines.append("## 6. Go / no-go recommendation")
    lines.append("")
    if go_no_go == "PASS":
        lines.append("GO for full strict-primary validation after explicit user approval and `--confirm-full`. Do not include supplementary singlebeam or regional MRAR in strict-primary validation.")
    else:
        lines.append("NO-GO for full strict-primary validation until the smoke failures above are resolved.")
    lines.append("")
    return "\n".join(lines)


def run_smoke(args, logger: logging.Logger) -> tuple[str, Path]:
    logger.info("Running Stage 2 smoke validation")
    preflight_status, preflight_report = run_preflight(args, logger)
    if preflight_status != "PASS":
        raise RuntimeError(f"Preflight failed; see {preflight_report}")

    config = load_config(Path(args.config))
    product_names = args.product_name or ["GEBCO_2024"]
    products = enabled_products(config, product_names)
    products_by_name = {p["name"]: p for p in products}
    ordered_products = [products_by_name[name] for name in product_names if name in products_by_name]

    step08 = load_legacy_step08_module()
    cell_sets = {
        key: read_validation_product_for_smoke(key, int(args.sample_n_cells))
        for key in SMOKE_PRODUCT_KEYS
    }

    all_results: list[pd.DataFrame] = []
    diagnostics: list[dict[str, Any]] = []
    product_status: list[dict[str, Any]] = []
    t0 = time.time()

    for i, prod in enumerate(ordered_products):
        pname = prod["name"]
        logger.info("Smoke sampling product %s", pname)
        if Path(prod["path"]).exists() is False:
            status = {"product_name": pname, "status": "skipped", "reason": f"file not found: {prod['path']}"}
            product_status.append(status)
            if i == 0:
                raise RuntimeError(f"First smoke product {pname} missing; cannot continue")
            continue

        product_rows = 0
        try:
            for _, cells in cell_sets.items():
                result, diag = sample_model_product(step08, prod, cells)
                if len(result):
                    all_results.append(result)
                    product_rows += int(len(result))
                diagnostics.append(diag)
        except Exception as exc:
            product_status.append({"product_name": pname, "status": "error", "reason": str(exc), "rows": product_rows})
            if i == 0:
                raise
            continue
        product_status.append({"product_name": pname, "status": "ok", "reason": "", "rows": product_rows})

    if not all_results:
        raise RuntimeError("No smoke validation rows produced")

    cells_df = pd.concat(all_results, ignore_index=True)
    diagnostics_df = pd.DataFrame(diagnostics)
    product_status_df = pd.DataFrame(product_status)
    metrics = build_metrics(cells_df)
    comparison = build_strict_expanded_comparison(metrics["summary"])

    sign_fail = bool(diagnostics_df.get("sign_error_suspected", pd.Series(dtype=bool)).fillna(False).any())
    no_valid = bool((metrics["summary"]["count"] <= 0).any()) if len(metrics["summary"]) else True
    product_errors = bool((product_status_df["status"] == "error").any()) if len(product_status_df) else True
    go_no_go = "FAIL" if sign_fail or no_valid or product_errors else "PASS"

    out_dir = output_dir(args.run_label)
    if out_dir.exists() and any(out_dir.iterdir()) and not args.overwrite:
        raise RuntimeError(f"Output dir has files (use --overwrite): {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    for pname, sub in cells_df.groupby("product_name"):
        atomic_write_parquet(sub, out_dir / f"validation_by_cell_{pname}.parquet")

    atomic_write_parquet(diagnostics_df, out_dir / "validation_sample_diagnostics.parquet")
    atomic_write_tsv(diagnostics_df, out_dir / "validation_sample_diagnostics.tsv")
    atomic_write_parquet(product_status_df, out_dir / "model_product_status.parquet")
    atomic_write_tsv(product_status_df, out_dir / "model_product_status.tsv")

    metric_stems = {
        "summary": "validation_metrics_summary",
        "by_quality_tier": "validation_metrics_by_quality_tier",
        "by_evidence_class": "validation_metrics_by_evidence_class",
        "by_source_role": "validation_metrics_by_source_role",
        "by_branch": "validation_metrics_by_branch",
        "by_depth_bin": "validation_metrics_by_depth_bin",
        "by_lat_band": "validation_metrics_by_lat_band",
        "by_region_10deg": "validation_metrics_by_region_10deg",
    }
    for key, stem in metric_stems.items():
        df = metrics.get(key, pd.DataFrame())
        if len(df) == 0:
            continue
        atomic_write_parquet(df, out_dir / f"{stem}.parquet")
        atomic_write_tsv(df, out_dir / f"{stem}.tsv")

    if len(comparison):
        atomic_write_parquet(comparison, out_dir / "strict_vs_expanded_comparison.parquet")
        atomic_write_tsv(comparison, out_dir / "strict_vs_expanded_comparison.tsv")

    elapsed = time.time() - t0
    report = make_smoke_report(
        cells_df, metrics, comparison, diagnostics_df, product_status_df,
        preflight_status, elapsed, go_no_go,
    )
    report_path = DOCS_DIR / f"step08_smoke_validation_report_{args.run_label}.md"
    atomic_write_text(report, report_path)
    logger.info("Smoke status: %s", go_no_go)
    logger.info("Wrote %s", report_path)
    return go_no_go, report_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args(argv: Iterable[str] | None = None):
    parser = argparse.ArgumentParser(description="Validate gridded products against Step 07B validation cells")
    parser.add_argument("--stage", choices=["preflight", "smoke", "full"], required=True)
    parser.add_argument("--run-label", default="smoke", help="Output label; full requires --confirm-full")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to gridded_products_validation.yaml")
    parser.add_argument("--product-name", action="append", default=None, help="Product to smoke-test; repeatable")
    parser.add_argument("--sample-n-cells", type=int, default=2000, help="Deterministic smoke rows per validation product")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite smoke/preflight outputs")
    parser.add_argument("--confirm-full", action="store_true", help="Required for stage=full or run-label=full")
    parser.add_argument(
        "--validation-product",
        choices=["strict_primary_multibeam_cells", "expanded_primary_ship_cells"],
        default="strict_primary_multibeam_cells",
        help="Validation cell product for stage=full. Default is strict_primary_multibeam_cells (backward-compatible Stage 3 behavior).",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    logger = setup_logging(args.run_label)

    logger.info("14_validate_gridded_products_step08.py START")
    logger.info("stage=%s run_label=%s config=%s product_name=%s sample_n_cells=%s overwrite=%s validation_product=%s",
                args.stage, args.run_label, args.config, args.product_name, args.sample_n_cells, args.overwrite,
                getattr(args, "validation_product", FULL_STRICT_PRODUCT_KEY))

    if (args.stage == "full" or args.run_label == "full") and not args.confirm_full:
        logger.error("Full production validation requires --confirm-full")
        return 2

    try:
        if args.stage == "preflight":
            status, report = run_preflight(args, logger)
            print(f"Preflight status: {status}\nReport: {report}")
            return 0 if status == "PASS" else 1
        if args.stage == "smoke":
            status, report = run_smoke(args, logger)
            print(f"Smoke status: {status}\nReport: {report}")
            return 0 if status == "PASS" else 1
        if args.stage == "full":
            status, report = run_full(args, logger)
            role_label = "strict-primary" if EXPECTED_PRODUCTS[getattr(args, "validation_product", FULL_STRICT_PRODUCT_KEY)]["product_role"] == "strict_primary_multibeam" else "expanded-primary"
            print(f"Full {role_label} status: {status}\nReport: {report}")
            return 0 if status == "PASS" else 1
    except Exception as exc:
        logger.exception("Stage failed: %s", exc)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    logger.error("Unknown stage: %s", args.stage)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
