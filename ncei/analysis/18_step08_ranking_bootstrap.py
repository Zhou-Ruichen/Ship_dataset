#!/usr/bin/env python3
"""
18_step08_ranking_bootstrap.py

Step 08 public-output task A: paired region-cluster bootstrap for strict-primary
model ranking uncertainty.

READ-ONLY with respect to Step 07B validation-cell products and Step 08
by-cell validation outputs. This script does not resample gridded products and
never filters, drops, or relabels validation cells based on model residuals.

Reads:
  - ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_GEBCO_2024.parquet
  - ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_ETOPO_2022.parquet
  - ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_SRTM15_V2.7.parquet
  - ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_TOPO_25.1.parquet
  - ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_SDUST_2023.parquet

Writes:
  - ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/ranking_bootstrap_iters.parquet
  - ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/model_metric_ci.tsv
  - ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/pairwise_delta_rmse_ci.tsv
  - ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/ranking_stability_rmse.tsv
  - ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/ranking_stability_wrmse.tsv
  - ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/bootstrap_runtime_metadata.tsv
  - ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/a_ranking_safety_checks.tsv
  - ncei/docs/model_ranking_uncertainty_report.md
  - ncei/output/logs/18_step08_ranking_bootstrap_<run-label>.log

Usage:
    python ncei/analysis/18_step08_ranking_bootstrap.py --check-only
    python ncei/analysis/18_step08_ranking_bootstrap.py \
      --run-label a_ranking --bootstrap-iters 1000 --seed 20260528 \
      --confirm-bootstrap --overwrite
    python ncei/analysis/18_step08_ranking_bootstrap.py \
      --run-label a_ranking_diag --bootstrap-iters 1000 --seed 20260528 \
      --diagnose-convergence --confirm-bootstrap --overwrite
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent          # ncei/
REPO_ROOT = ROOT_DIR.parent           # repository root
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"

STRICT_EXPECTED_ROWS = 2_398_774
EXPECTED_CLUSTERS = 124
DEFAULT_BOOTSTRAP_ITERS = 1000
DEFAULT_SEED = 20260528
DEFAULT_RUN_LABEL = "a_ranking"
OUTPUT_REL_DIR = Path("model_validation_1min_step08_pub") / "a_ranking_uncertainty"

MODEL_NAMES = ["GEBCO_2024", "ETOPO_2022", "SRTM15_V2.7", "TOPO_25.1", "SDUST_2023"]
METRICS = ["RMSE", "MAE", "wRMSE"]
PAIRWISE_MODELS = [(a, b) for i, a in enumerate(MODEL_NAMES) for b in MODEL_NAMES[i + 1:]]
REQUIRED_BY_CELL_COLUMNS = ["cell_id", "validation_weight", "region_10deg", "depth_error_m"]


# ---------------------------------------------------------------------------
# Paths / logging / atomic writes
# ---------------------------------------------------------------------------

def find_data_repo_root() -> Path:
    """Return the repo root that owns the large derived inputs.

    Pi implementation worktrees may contain only tracked source files while the
    large, git-ignored derived parquet files remain in an ancestor checkout. The
    search is derived from this script path (no hard-coded absolute paths) and
    falls back to the current worktree for normal in-repo execution.
    """
    rel = Path("ncei") / "derived" / "model_validation_1min_full_strict_primary"
    for candidate in [REPO_ROOT, *REPO_ROOT.parents]:
        if (candidate / rel).exists():
            return candidate
    return REPO_ROOT


DATA_REPO_ROOT = find_data_repo_root()
INPUT_DIR = DATA_REPO_ROOT / "ncei" / "derived" / "model_validation_1min_full_strict_primary"
OUTPUT_DIR = ROOT_DIR / "derived" / OUTPUT_REL_DIR
DEFAULT_REPORT_PATH = DOCS_DIR / "model_ranking_uncertainty_report.md"


def setup_logging(run_label: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"18_step08_ranking_bootstrap_{run_label}.log"
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


def ensure_writable(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise RuntimeError(f"Output exists; pass --overwrite to replace: {path}")


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
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, tmp)
    os.replace(tmp, path)


def atomic_write_tsv(df: pd.DataFrame, path: Path, overwrite: bool) -> None:
    ensure_writable(path, overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Formatting / metadata helpers
# ---------------------------------------------------------------------------

def fmt(value: Any, places: int = 4) -> str:
    if pd.isna(value):
        return "N/A"
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.{places}f}"
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    text = str(value)
    return text.replace("\n", " ").replace("|", "\\|")


def markdown_table(df: pd.DataFrame, max_rows: int | None = None, places: int = 4) -> str:
    if df is None or len(df) == 0:
        return "_(none)_"
    work = df.copy()
    if max_rows is not None:
        work = work.head(max_rows)
    cols = list(work.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in work.iterrows():
        lines.append("| " + " | ".join(fmt(row.get(c), places=places) for c in cols) + " |")
    return "\n".join(lines)


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def hash_text_values(values: list[str]) -> str:
    h = hashlib.sha256()
    for value in values:
        h.update(str(value).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def by_cell_path(model_name: str) -> Path:
    return INPUT_DIR / f"full_validation_by_cell_strict_primary_{model_name}.parquet"


def delta_col(model_a: str, model_b: str) -> str:
    safe_a = model_a.replace(".", "_")
    safe_b = model_b.replace(".", "_")
    return f"delta_RMSE_{safe_a}_minus_{safe_b}"


def metric_col(metric: str, model_name: str) -> str:
    safe_model = model_name.replace(".", "_")
    return f"{metric}_{safe_model}"


# ---------------------------------------------------------------------------
# Input loading and paired validation
# ---------------------------------------------------------------------------

def read_required_columns(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    schema_names = set(pq.read_schema(path).names)
    missing = [c for c in REQUIRED_BY_CELL_COLUMNS if c not in schema_names]
    if missing:
        raise RuntimeError(f"{path} missing required column(s): {missing}")
    return pq.read_table(path, columns=REQUIRED_BY_CELL_COLUMNS).to_pandas()


def validate_reference_frame(ref: pd.DataFrame) -> dict[str, Any]:
    n_rows = int(len(ref))
    n_cell_null = int(ref["cell_id"].isna().sum())
    n_region_null = int(ref["region_10deg"].isna().sum())
    n_weight_null = int(ref["validation_weight"].isna().sum())
    n_resid_null = int(ref["depth_error_m"].isna().sum())
    duplicate_cell_ids = int(ref["cell_id"].duplicated().sum())
    weights = pd.to_numeric(ref["validation_weight"], errors="coerce").to_numpy(dtype=np.float64)
    return {
        "n_rows": n_rows,
        "n_cell_null": n_cell_null,
        "n_region_null": n_region_null,
        "n_weight_null": n_weight_null,
        "n_resid_null": n_resid_null,
        "duplicate_cell_ids": duplicate_cell_ids,
        "weight_min": float(np.nanmin(weights)) if len(weights) else np.nan,
        "weight_max": float(np.nanmax(weights)) if len(weights) else np.nan,
        "weight_nonfinite": int((~np.isfinite(weights)).sum()),
    }


def align_model_to_reference(ref: pd.DataFrame, other: pd.DataFrame, model_name: str) -> tuple[np.ndarray, dict[str, Any]]:
    """Return residuals in reference cell_id order and validation details."""
    details: dict[str, Any] = {
        "model": model_name,
        "input_rows": int(len(other)),
        "same_cell_order": bool(ref["cell_id"].equals(other["cell_id"])),
        "used_inner_join": False,
        "weight_mismatches": 0,
        "region_mismatches": 0,
    }
    if details["same_cell_order"]:
        aligned = other
    else:
        details["used_inner_join"] = True
        if int(other["cell_id"].duplicated().sum()) > 0:
            raise RuntimeError(f"{model_name}: duplicate cell_id values prevent paired join")
        aligned = ref[["cell_id", "validation_weight", "region_10deg"]].merge(
            other,
            on="cell_id",
            how="inner",
            suffixes=("_ref", ""),
            sort=False,
            validate="one_to_one",
        )
        if len(aligned) != len(ref):
            raise RuntimeError(
                f"{model_name}: paired inner join rows={len(aligned):,}; expected={len(ref):,}"
            )
        details["joined_rows"] = int(len(aligned))

    other_weight = pd.to_numeric(aligned["validation_weight"], errors="coerce").to_numpy(dtype=np.float64)
    ref_weight = pd.to_numeric(ref["validation_weight"], errors="coerce").to_numpy(dtype=np.float64)
    weight_mismatch = (~np.isclose(ref_weight, other_weight, rtol=0.0, atol=1e-8)) | (~np.isfinite(other_weight))
    region_mismatch = ref["region_10deg"].astype(str).to_numpy() != aligned["region_10deg"].astype(str).to_numpy()
    details["weight_mismatches"] = int(weight_mismatch.sum())
    details["region_mismatches"] = int(region_mismatch.sum())
    if details["weight_mismatches"]:
        raise RuntimeError(f"{model_name}: validation_weight differs from reference for {details['weight_mismatches']:,} rows")
    if details["region_mismatches"]:
        raise RuntimeError(f"{model_name}: region_10deg differs from reference for {details['region_mismatches']:,} rows")

    resid = pd.to_numeric(aligned["depth_error_m"], errors="coerce").to_numpy(dtype=np.float32)
    details["residual_nan_or_inf"] = int((~np.isfinite(resid)).sum())
    if details["residual_nan_or_inf"]:
        raise RuntimeError(f"{model_name}: residual matrix has {details['residual_nan_or_inf']:,} NaN/inf values")
    return resid, details


def load_paired_residuals(logger: logging.Logger) -> dict[str, Any]:
    input_paths = {model: by_cell_path(model) for model in MODEL_NAMES}
    missing = [str(path) for path in input_paths.values() if not path.exists()]
    if missing:
        raise RuntimeError("Missing strict-primary by-cell input(s):\n  - " + "\n  - ".join(missing))

    logger.info("input_dir=%s", INPUT_DIR)
    logger.info("loading reference model=%s", MODEL_NAMES[0])
    ref = read_required_columns(input_paths[MODEL_NAMES[0]])
    ref_stats = validate_reference_frame(ref)
    if ref_stats["n_rows"] != STRICT_EXPECTED_ROWS:
        raise RuntimeError(f"paired rows={ref_stats['n_rows']:,}; expected={STRICT_EXPECTED_ROWS:,}")
    if ref_stats["duplicate_cell_ids"]:
        raise RuntimeError(f"reference duplicate cell_id count={ref_stats['duplicate_cell_ids']:,}")
    if ref_stats["n_cell_null"] or ref_stats["n_region_null"] or ref_stats["n_weight_null"] or ref_stats["n_resid_null"]:
        raise RuntimeError(f"reference null check failed: {ref_stats}")
    if ref_stats["weight_nonfinite"]:
        raise RuntimeError(f"reference non-finite validation_weight count={ref_stats['weight_nonfinite']:,}")

    n_rows = int(len(ref))
    residuals = np.empty((n_rows, len(MODEL_NAMES)), dtype=np.float32)
    first_resid = pd.to_numeric(ref["depth_error_m"], errors="coerce").to_numpy(dtype=np.float32)
    if int((~np.isfinite(first_resid)).sum()):
        raise RuntimeError(f"{MODEL_NAMES[0]} residuals contain NaN/inf")
    residuals[:, 0] = first_resid
    align_details = [{
        "model": MODEL_NAMES[0],
        "input_rows": n_rows,
        "same_cell_order": True,
        "used_inner_join": False,
        "weight_mismatches": 0,
        "region_mismatches": 0,
        "residual_nan_or_inf": 0,
    }]

    for j, model in enumerate(MODEL_NAMES[1:], start=1):
        logger.info("loading paired model=%s", model)
        other = read_required_columns(input_paths[model])
        resid, details = align_model_to_reference(ref, other, model)
        residuals[:, j] = resid
        align_details.append(details)

    weights = pd.to_numeric(ref["validation_weight"], errors="coerce").to_numpy(dtype=np.float32)
    regions = ref["region_10deg"].astype(str).to_numpy()
    cluster_names, region_codes = np.unique(regions, return_inverse=True)
    region_codes = region_codes.astype(np.int16, copy=False)
    cluster_sizes = np.bincount(region_codes, minlength=len(cluster_names)).astype(np.int64)
    if len(cluster_names) != EXPECTED_CLUSTERS:
        raise RuntimeError(f"region_10deg clusters={len(cluster_names):,}; expected={EXPECTED_CLUSTERS:,}")

    input_hashes = {model: sha256_file(path) for model, path in input_paths.items()}
    cluster_hash = hash_text_values([f"{name}\t{int(size)}" for name, size in zip(cluster_names, cluster_sizes)])

    logger.info(
        "paired residual matrix rows=%d models=%d clusters=%d min_cluster=%d max_cluster=%d",
        n_rows,
        len(MODEL_NAMES),
        len(cluster_names),
        int(cluster_sizes.min()),
        int(cluster_sizes.max()),
    )

    return {
        "input_paths": input_paths,
        "input_hashes": input_hashes,
        "ref_stats": ref_stats,
        "align_details": align_details,
        "cell_ids": ref["cell_id"],
        "weights": weights,
        "regions": regions,
        "region_codes": region_codes,
        "cluster_names": cluster_names,
        "cluster_sizes": cluster_sizes,
        "cluster_hash": cluster_hash,
        "residuals": residuals,
    }


# ---------------------------------------------------------------------------
# Bootstrap computation
# ---------------------------------------------------------------------------

def compute_cluster_stats(residuals: np.ndarray, weights: np.ndarray, region_codes: np.ndarray, n_clusters: int) -> dict[str, np.ndarray]:
    n_models = residuals.shape[1]
    cluster_n = np.bincount(region_codes, minlength=n_clusters).astype(np.float64)
    cluster_weight_sum = np.bincount(region_codes, weights=weights.astype(np.float64), minlength=n_clusters).astype(np.float64)
    sum_sq = np.empty((n_clusters, n_models), dtype=np.float64)
    sum_abs = np.empty((n_clusters, n_models), dtype=np.float64)
    sum_w_sq = np.empty((n_clusters, n_models), dtype=np.float64)
    weights64 = weights.astype(np.float64)
    for j in range(n_models):
        r = residuals[:, j].astype(np.float64)
        sum_sq[:, j] = np.bincount(region_codes, weights=r * r, minlength=n_clusters)
        sum_abs[:, j] = np.bincount(region_codes, weights=np.abs(r), minlength=n_clusters)
        sum_w_sq[:, j] = np.bincount(region_codes, weights=weights64 * r * r, minlength=n_clusters)
    return {
        "cluster_n": cluster_n,
        "cluster_weight_sum": cluster_weight_sum,
        "sum_sq": sum_sq,
        "sum_abs": sum_abs,
        "sum_w_sq": sum_w_sq,
    }


def metrics_from_cluster_multiplicity(multiplicity: np.ndarray, stats: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    total_n = float(multiplicity @ stats["cluster_n"])
    total_w = float(multiplicity @ stats["cluster_weight_sum"])
    sum_sq = multiplicity @ stats["sum_sq"]
    sum_abs = multiplicity @ stats["sum_abs"]
    sum_w_sq = multiplicity @ stats["sum_w_sq"]
    rmse = np.sqrt(sum_sq / total_n)
    mae = sum_abs / total_n
    wrmse = np.sqrt(sum_w_sq / total_w)
    return rmse, mae, wrmse


def full_point_estimates(stats: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    multiplicity = np.ones(len(stats["cluster_n"]), dtype=np.float64)
    rmse, mae, wrmse = metrics_from_cluster_multiplicity(multiplicity, stats)
    return {"RMSE": rmse, "MAE": mae, "wRMSE": wrmse}


def run_bootstrap(
    stats: dict[str, np.ndarray],
    n_iters: int,
    seed: int,
    logger: logging.Logger,
) -> tuple[pd.DataFrame, np.ndarray, dict[str, np.ndarray]]:
    rng = np.random.default_rng(seed)
    n_clusters = len(stats["cluster_n"])
    n_models = len(MODEL_NAMES)
    rmse_values = np.empty((n_iters, n_models), dtype=np.float64)
    mae_values = np.empty((n_iters, n_models), dtype=np.float64)
    wrmse_values = np.empty((n_iters, n_models), dtype=np.float64)
    sampled_clusters = np.empty((n_iters, n_clusters), dtype=np.int16)

    log_every = max(1, n_iters // 20)
    for i in range(n_iters):
        draw = rng.choice(n_clusters, size=n_clusters, replace=True)
        sampled_clusters[i, :] = draw.astype(np.int16)
        multiplicity = np.bincount(draw, minlength=n_clusters).astype(np.float64)
        rmse, mae, wrmse = metrics_from_cluster_multiplicity(multiplicity, stats)
        rmse_values[i, :] = rmse
        mae_values[i, :] = mae
        wrmse_values[i, :] = wrmse
        if (i + 1) % log_every == 0 or i + 1 == n_iters:
            logger.info("bootstrap progress=%d/%d (%.1f%%)", i + 1, n_iters, 100.0 * (i + 1) / n_iters)

    rows: dict[str, Any] = {"iter": np.arange(n_iters, dtype=np.int32)}
    for j, model in enumerate(MODEL_NAMES):
        rows[metric_col("RMSE", model)] = rmse_values[:, j].astype(np.float32)
        rows[metric_col("MAE", model)] = mae_values[:, j].astype(np.float32)
        rows[metric_col("wRMSE", model)] = wrmse_values[:, j].astype(np.float32)
    for model_a, model_b in PAIRWISE_MODELS:
        ia = MODEL_NAMES.index(model_a)
        ib = MODEL_NAMES.index(model_b)
        rows[delta_col(model_a, model_b)] = (rmse_values[:, ia] - rmse_values[:, ib]).astype(np.float32)

    iter_df = pd.DataFrame(rows)
    arrays = {"RMSE": rmse_values, "MAE": mae_values, "wRMSE": wrmse_values}
    return iter_df, sampled_clusters, arrays


# ---------------------------------------------------------------------------
# Summaries, safety checks, report
# ---------------------------------------------------------------------------

def build_model_metric_ci(point: dict[str, np.ndarray], boot_arrays: dict[str, np.ndarray]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for metric in METRICS:
        arr = boot_arrays[metric]
        for j, model in enumerate(MODEL_NAMES):
            values = arr[:, j]
            p025, p50, p975 = np.percentile(values, [2.5, 50.0, 97.5])
            point_est = float(point[metric][j])
            rows.append({
                "model": model,
                "metric": metric,
                "point_estimate": point_est,
                "p2.5": float(p025),
                "p50": float(p50),
                "p97.5": float(p975),
                "boot_mean": float(np.mean(values)),
                "ci_covers_point": bool(p025 <= point_est <= p975),
            })
    return pd.DataFrame(rows)


def build_pairwise_ci(point: dict[str, np.ndarray], boot_rmse: np.ndarray) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for model_a, model_b in PAIRWISE_MODELS:
        ia = MODEL_NAMES.index(model_a)
        ib = MODEL_NAMES.index(model_b)
        delta = boot_rmse[:, ia] - boot_rmse[:, ib]
        p025, p50, p975 = np.percentile(delta, [2.5, 50.0, 97.5])
        delta_point = float(point["RMSE"][ia] - point["RMSE"][ib])
        rows.append({
            "model_a": model_a,
            "model_b": model_b,
            "delta_point": delta_point,
            "delta_rmse_p2.5": float(p025),
            "delta_rmse_p50": float(p50),
            "delta_rmse_p97.5": float(p975),
            "delta_rmse_mean": float(np.mean(delta)),
            "p_a_better": float(np.mean(delta < 0.0)),
            "significant_at_95pct": bool((p025 > 0.0) or (p975 < 0.0)),
        })
    return pd.DataFrame(rows)


def build_ranking_stability(metric_values: np.ndarray) -> pd.DataFrame:
    n_iters, n_models = metric_values.shape
    order = np.argsort(metric_values, axis=1)
    counts = np.zeros((n_models, n_models), dtype=np.int64)
    for rank_idx in range(n_models):
        ranked_models = order[:, rank_idx]
        counts[:, rank_idx] = np.bincount(ranked_models, minlength=n_models)
    rows = []
    for model_idx, model in enumerate(MODEL_NAMES):
        row: dict[str, Any] = {"model": model}
        for rank_idx in range(n_models):
            row[f"rank_{rank_idx + 1}"] = float(counts[model_idx, rank_idx] / n_iters)
        rows.append(row)
    return pd.DataFrame(rows)


def build_metadata(
    args: argparse.Namespace,
    paired: dict[str, Any],
    elapsed: float,
    sampled_clusters: np.ndarray | None,
) -> pd.DataFrame:
    rows: list[dict[str, str]] = [
        {"key": "generated_utc", "value": datetime.now(timezone.utc).isoformat()},
        {"key": "python", "value": sys.version.replace("\n", " ")},
        {"key": "platform", "value": platform.platform()},
        {"key": "pandas", "value": pd.__version__},
        {"key": "numpy", "value": np.__version__},
        {"key": "pyarrow", "value": pa.__version__},
        {"key": "repo_root", "value": str(REPO_ROOT)},
        {"key": "data_repo_root", "value": str(DATA_REPO_ROOT)},
        {"key": "input_dir", "value": str(INPUT_DIR)},
        {"key": "output_dir", "value": str(OUTPUT_DIR)},
        {"key": "run_label", "value": str(args.run_label)},
        {"key": "bootstrap_iters", "value": str(args.bootstrap_iters)},
        {"key": "seed", "value": str(args.seed)},
        {"key": "confirm_bootstrap", "value": str(args.confirm_bootstrap)},
        {"key": "overwrite", "value": str(args.overwrite)},
        {"key": "check_only", "value": str(args.check_only)},
        {"key": "diagnose_convergence", "value": str(args.diagnose_convergence)},
        {"key": "elapsed_seconds", "value": f"{elapsed:.3f}"},
        {"key": "paired_n_cells", "value": str(len(paired["weights"]))},
        {"key": "n_models", "value": str(len(MODEL_NAMES))},
        {"key": "models", "value": ",".join(MODEL_NAMES)},
        {"key": "n_clusters", "value": str(len(paired["cluster_names"]))},
        {"key": "cluster_list_hash", "value": str(paired["cluster_hash"])},
        {"key": "cluster_min_size", "value": str(int(paired["cluster_sizes"].min()))},
        {"key": "cluster_max_size", "value": str(int(paired["cluster_sizes"].max()))},
    ]
    if sampled_clusters is not None:
        h = hashlib.sha256(sampled_clusters.tobytes()).hexdigest()
        rows.append({"key": "sampled_cluster_sequence_hash", "value": h})
    for model in MODEL_NAMES:
        rows.append({"key": f"input_path_{model}", "value": str(paired["input_paths"][model])})
        rows.append({"key": f"input_sha256_{model}", "value": str(paired["input_hashes"][model])})
    return pd.DataFrame(rows)


def pass_fail(condition: bool) -> str:
    return "PASS" if bool(condition) else "FAIL"


def build_safety_checks(
    paired: dict[str, Any],
    ci_df: pd.DataFrame | None,
    args: argparse.Namespace,
) -> pd.DataFrame:
    residuals = paired["residuals"]
    weights = paired["weights"]
    cluster_sizes = paired["cluster_sizes"]
    ref_stats = paired["ref_stats"]
    align = pd.DataFrame(paired["align_details"])
    rows: list[dict[str, Any]] = []

    def add(check_id: str, description: str, condition: bool, observed: Any, expected: Any = "") -> None:
        rows.append({
            "check_id": check_id,
            "description": description,
            "status": pass_fail(condition),
            "observed": observed,
            "expected": expected,
        })

    add("paired_n_cells", "Paired strict-primary residual matrix preserves all input cells", residuals.shape[0] == STRICT_EXPECTED_ROWS, residuals.shape[0], STRICT_EXPECTED_ROWS)
    add("paired_n_models", "Residual matrix has five strict-primary global models", residuals.shape[1] == len(MODEL_NAMES), residuals.shape[1], len(MODEL_NAMES))
    add("cell_id_unique", "Reference cell_id values are unique", ref_stats["duplicate_cell_ids"] == 0, ref_stats["duplicate_cell_ids"], 0)
    add("no_nan_residuals", "No NaN/inf values in the N x 5 residual matrix", bool(np.isfinite(residuals).all()), int((~np.isfinite(residuals)).sum()), 0)
    add("no_nan_weights", "No NaN/inf validation_weight values", bool(np.isfinite(weights).all()), int((~np.isfinite(weights)).sum()), 0)
    add("n_clusters", "Cluster bootstrap uses 124 region_10deg clusters", len(paired["cluster_names"]) == EXPECTED_CLUSTERS, len(paired["cluster_names"]), EXPECTED_CLUSTERS)
    add("cluster_min_positive", "Every region_10deg cluster has at least one cell", int(cluster_sizes.min()) > 0, int(cluster_sizes.min()), ">0")
    add("weight_range", "Strict-primary validation weights remain within the expected [0.4, 1.0] range", float(np.nanmin(weights)) >= 0.4 and float(np.nanmax(weights)) <= 1.0, f"{float(np.nanmin(weights)):.4f}..{float(np.nanmax(weights)):.4f}", "0.4..1.0")
    add("weight_region_independent", "validation_weight and region_10deg are identical across model copies", int(align["weight_mismatches"].sum()) == 0 and int(align["region_mismatches"].sum()) == 0, f"weight_mismatches={int(align['weight_mismatches'].sum())}; region_mismatches={int(align['region_mismatches'].sum())}", "0; 0")
    add("no_join_row_loss", "Any paired inner-join fallback retained all cells", all(int(d.get("input_rows", 0)) == STRICT_EXPECTED_ROWS for d in paired["align_details"]), "; ".join(f"{d['model']}={d.get('input_rows')}" for d in paired["align_details"]), STRICT_EXPECTED_ROWS)
    add("reproducible_seed", "Bootstrap seed is recorded and fixed by CLI", args.seed is not None, args.seed, "non-null")
    add("input_hashes_recorded", "SHA256 hash recorded for every model input", len(paired["input_hashes"]) == len(MODEL_NAMES) and all(paired["input_hashes"].values()), len(paired["input_hashes"]), len(MODEL_NAMES))
    for model in MODEL_NAMES:
        add(f"input_hash_{model}", f"Input SHA256 recorded for {model}", len(paired["input_hashes"].get(model, "")) == 64, paired["input_hashes"].get(model, ""), "64 hex chars")
    add("no_residual_filter", "No cells were filtered by residual magnitude; row count equals strict-primary input count", residuals.shape[0] == STRICT_EXPECTED_ROWS, residuals.shape[0], STRICT_EXPECTED_ROWS)
    if ci_df is not None:
        n_cover = int(ci_df["ci_covers_point"].sum())
        add("ci_covers_point", "All 15 model/metric point estimates are inside their 95% bootstrap percentile CI", n_cover == len(ci_df), f"{n_cover}/{len(ci_df)}", f"{len(ci_df)}/{len(ci_df)}")
    return pd.DataFrame(rows)


def build_convergence_diagnostics(
    boot_arrays: dict[str, np.ndarray],
    boot_rmse: np.ndarray,
    n_iters: int,
) -> pd.DataFrame:
    cutoffs = [c for c in [250, 500, 1000] if c <= n_iters]
    if n_iters not in cutoffs:
        cutoffs.append(n_iters)
    rows: list[dict[str, Any]] = []
    for cutoff in sorted(set(cutoffs)):
        for metric in METRICS:
            arr = boot_arrays[metric][:cutoff]
            for j, model in enumerate(MODEL_NAMES):
                p025, p50, p975 = np.percentile(arr[:, j], [2.5, 50.0, 97.5])
                rows.append({
                    "cutoff_iters": cutoff,
                    "kind": "model_metric",
                    "model": model,
                    "metric": metric,
                    "model_a": "",
                    "model_b": "",
                    "p2.5": float(p025),
                    "p50": float(p50),
                    "p97.5": float(p975),
                })
        for model_a, model_b in PAIRWISE_MODELS:
            ia = MODEL_NAMES.index(model_a)
            ib = MODEL_NAMES.index(model_b)
            delta = boot_rmse[:cutoff, ia] - boot_rmse[:cutoff, ib]
            p025, p50, p975 = np.percentile(delta, [2.5, 50.0, 97.5])
            rows.append({
                "cutoff_iters": cutoff,
                "kind": "pairwise_delta_rmse",
                "model": "",
                "metric": "RMSE_delta",
                "model_a": model_a,
                "model_b": model_b,
                "p2.5": float(p025),
                "p50": float(p50),
                "p97.5": float(p975),
            })
    return pd.DataFrame(rows)


def build_report(
    args: argparse.Namespace,
    elapsed: float,
    paired: dict[str, Any],
    ci_df: pd.DataFrame,
    pairwise_df: pd.DataFrame,
    rank_rmse: pd.DataFrame,
    rank_wrmse: pd.DataFrame,
    safety_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    convergence_df: pd.DataFrame | None,
) -> str:
    generated = datetime.now(timezone.utc).isoformat()
    gebco_etopo = pairwise_df[(pairwise_df["model_a"] == "GEBCO_2024") & (pairwise_df["model_b"] == "ETOPO_2022")].iloc[0]
    sig_word = "significant" if bool(gebco_etopo["significant_at_95pct"]) else "not significant"
    better = "GEBCO_2024" if float(gebco_etopo["p_a_better"]) >= 0.5 else "ETOPO_2022"
    summary_sentence = (
        f"GEBCO_2024 vs ETOPO_2022 ΔRMSE (GEBCO − ETOPO) point="
        f"{float(gebco_etopo['delta_point']):.4f} m, 95% CI "
        f"[{float(gebco_etopo['delta_rmse_p2.5']):.4f}, {float(gebco_etopo['delta_rmse_p97.5']):.4f}] m; "
        f"the adjacent-pair difference is {sig_word} at 95%, with {better} lower in "
        f"{100.0 * float(gebco_etopo['p_a_better'] if better == 'GEBCO_2024' else 1.0 - gebco_etopo['p_a_better']):.1f}% "
        f"of bootstrap iterations."
    )

    metric_summary = ci_df.pivot(index="model", columns="metric", values="point_estimate").reset_index()
    metric_ci_view = ci_df[["model", "metric", "point_estimate", "p2.5", "p50", "p97.5", "boot_mean", "ci_covers_point"]]
    pairwise_view = pairwise_df.sort_values("delta_point")
    safety_counts = safety_df["status"].value_counts().to_dict()
    output_paths = pd.DataFrame([
        {"kind": "bootstrap_iters", "path": str(OUTPUT_DIR / "ranking_bootstrap_iters.parquet")},
        {"kind": "model_metric_ci", "path": str(OUTPUT_DIR / "model_metric_ci.tsv")},
        {"kind": "pairwise_delta_rmse_ci", "path": str(OUTPUT_DIR / "pairwise_delta_rmse_ci.tsv")},
        {"kind": "ranking_stability_rmse", "path": str(OUTPUT_DIR / "ranking_stability_rmse.tsv")},
        {"kind": "ranking_stability_wrmse", "path": str(OUTPUT_DIR / "ranking_stability_wrmse.tsv")},
        {"kind": "runtime_metadata", "path": str(OUTPUT_DIR / "bootstrap_runtime_metadata.tsv")},
        {"kind": "safety_checks", "path": str(OUTPUT_DIR / "a_ranking_safety_checks.tsv")},
        {"kind": "report", "path": str(DEFAULT_REPORT_PATH)},
    ])
    if convergence_df is not None:
        output_paths = pd.concat([output_paths, pd.DataFrame([{
            "kind": "convergence_diagnostics",
            "path": str(OUTPUT_DIR / "bootstrap_convergence_diagnostics.tsv"),
        }])], ignore_index=True)

    lines = [
        "# Model Ranking Uncertainty Report",
        "",
        f"Generated: {generated}",
        f"Status: **{'PASS' if not (safety_df['status'] != 'PASS').any() else 'FAIL'}**",
        f"Elapsed: {elapsed:.1f}s",
        f"Run label: `{args.run_label}`",
        "",
        "## 1. Summary",
        summary_sentence,
        "",
        "Strict-primary point estimates used for ranking:",
        "",
        markdown_table(metric_summary, places=4),
        "",
        "## 2. Method",
        f"This task reads the five strict-primary by-cell residual parquets and validates that all files contain the same {STRICT_EXPECTED_ROWS:,} `cell_id` values, `validation_weight`, and `region_10deg` assignments. It then computes paired cluster bootstrap intervals using `region_10deg` as the resampling unit.",
        "",
        f"Bootstrap settings: B={args.bootstrap_iters:,}, seed={args.seed}, clusters={len(paired['cluster_names'])}. Each iteration samples {len(paired['cluster_names'])} clusters with replacement and recomputes RMSE, MAE, weighted RMSE, pairwise ΔRMSE, and rankings from per-cluster sufficient statistics. No validation row is filtered by residual magnitude.",
        "",
        "## 3. Ranking stability by RMSE",
        markdown_table(rank_rmse, places=4),
        "",
        "## 4. Ranking stability by weighted RMSE",
        markdown_table(rank_wrmse, places=4),
        "",
        "## 5. Pairwise ΔRMSE confidence intervals",
        "`delta = RMSE(model_a) - RMSE(model_b)`, so negative means `model_a` has lower RMSE.",
        "",
        markdown_table(pairwise_view, places=4),
        "",
        "## 6. Model metric confidence intervals",
        markdown_table(metric_ci_view, places=4),
        "",
        "## 7. Safety checks",
        f"Safety status counts: {safety_counts}",
        "",
        markdown_table(safety_df, places=4),
        "",
        "## 8. Caveats",
        f"- The cluster bootstrap has {len(paired['cluster_names'])} clusters with highly uneven cell counts (min={int(paired['cluster_sizes'].min()):,}, max={int(paired['cluster_sizes'].max()):,}); intervals therefore reflect the influence of the largest 10-degree regions.",
        f"- The analysis is strict-primary only (N={len(paired['weights']):,}) and excludes expanded-primary, supplementary singlebeam, regional MRAR, and SWOT_T1 products by task scope.",
        "- Percentile intervals are used; BCa or moving-block bootstrap variants are out of scope for this task.",
    ]
    if convergence_df is not None and len(convergence_df):
        lines.extend([
            "- Optional convergence diagnostics were requested and written to `bootstrap_convergence_diagnostics.tsv`.",
        ])
    lines.extend([
        "",
        "## 9. Reproducibility and output paths",
        markdown_table(metadata_df, places=4),
        "",
        markdown_table(output_paths, places=4),
        "",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI / main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Paired cluster bootstrap for strict-primary Step 08 model ranking uncertainty.")
    parser.add_argument("--run-label", default=DEFAULT_RUN_LABEL, help="Run label for logs/metadata (default: a_ranking).")
    parser.add_argument("--bootstrap-iters", type=int, default=DEFAULT_BOOTSTRAP_ITERS, help="Number of bootstrap iterations (default: 1000).")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Numpy random seed (default: 20260528).")
    parser.add_argument("--confirm-bootstrap", action="store_true", help="Required for a full bootstrap run.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing output files.")
    parser.add_argument("--check-only", action="store_true", help="Read and validate inputs, record hashes, then exit before bootstrap/output writes.")
    parser.add_argument("--diagnose-convergence", action="store_true", help="Write CI diagnostics for prefixes of the bootstrap sequence (250/500/1000 where available).")
    return parser.parse_args()


def planned_outputs(diagnose_convergence: bool) -> list[Path]:
    outputs = [
        OUTPUT_DIR / "ranking_bootstrap_iters.parquet",
        OUTPUT_DIR / "model_metric_ci.tsv",
        OUTPUT_DIR / "pairwise_delta_rmse_ci.tsv",
        OUTPUT_DIR / "ranking_stability_rmse.tsv",
        OUTPUT_DIR / "ranking_stability_wrmse.tsv",
        OUTPUT_DIR / "bootstrap_runtime_metadata.tsv",
        OUTPUT_DIR / "a_ranking_safety_checks.tsv",
        DEFAULT_REPORT_PATH,
    ]
    if diagnose_convergence:
        outputs.append(OUTPUT_DIR / "bootstrap_convergence_diagnostics.tsv")
    return outputs


def main() -> int:
    args = parse_args()
    logger = setup_logging(args.run_label)
    started = time.time()
    logger.info("argv=%s", " ".join(sys.argv))
    logger.info("repo_root=%s", REPO_ROOT)
    logger.info("data_repo_root=%s", DATA_REPO_ROOT)
    logger.info("output_dir=%s", OUTPUT_DIR)

    if args.bootstrap_iters <= 0:
        logger.error("--bootstrap-iters must be positive")
        return 2
    if not args.check_only and not args.confirm_bootstrap:
        logger.error("Full bootstrap is gated; pass --confirm-bootstrap or use --check-only")
        return 2
    if not args.check_only:
        for path in planned_outputs(args.diagnose_convergence):
            ensure_writable(path, args.overwrite)

    paired = load_paired_residuals(logger)
    stats = compute_cluster_stats(
        residuals=paired["residuals"],
        weights=paired["weights"],
        region_codes=paired["region_codes"],
        n_clusters=len(paired["cluster_names"]),
    )

    if args.check_only:
        safety_df = build_safety_checks(paired, ci_df=None, args=args)
        elapsed = time.time() - started
        metadata_df = build_metadata(args, paired, elapsed, sampled_clusters=None)
        logger.info("check-only paired_n_cells=%d n_clusters=%d elapsed=%.1fs", len(paired["weights"]), len(paired["cluster_names"]), elapsed)
        logger.info("check-only safety_status_counts=%s", safety_df["status"].value_counts().to_dict())
        logger.info("check-only metadata_rows=%d", len(metadata_df))
        if (safety_df["status"] != "PASS").any():
            logger.error("check-only failed safety checks")
            return 1
        return 0

    point = full_point_estimates(stats)
    logger.info("running bootstrap iterations=%d seed=%d", args.bootstrap_iters, args.seed)
    iter_df, sampled_clusters, boot_arrays = run_bootstrap(stats, args.bootstrap_iters, args.seed, logger)
    ci_df = build_model_metric_ci(point, boot_arrays)
    pairwise_df = build_pairwise_ci(point, boot_arrays["RMSE"])
    rank_rmse = build_ranking_stability(boot_arrays["RMSE"])
    rank_wrmse = build_ranking_stability(boot_arrays["wRMSE"])
    convergence_df = build_convergence_diagnostics(boot_arrays, boot_arrays["RMSE"], args.bootstrap_iters) if args.diagnose_convergence else None
    elapsed = time.time() - started
    metadata_df = build_metadata(args, paired, elapsed, sampled_clusters=sampled_clusters)
    safety_df = build_safety_checks(paired, ci_df=ci_df, args=args)

    logger.info("writing outputs to %s", OUTPUT_DIR)
    atomic_write_parquet(iter_df, OUTPUT_DIR / "ranking_bootstrap_iters.parquet", args.overwrite)
    atomic_write_tsv(ci_df, OUTPUT_DIR / "model_metric_ci.tsv", args.overwrite)
    atomic_write_tsv(pairwise_df, OUTPUT_DIR / "pairwise_delta_rmse_ci.tsv", args.overwrite)
    atomic_write_tsv(rank_rmse, OUTPUT_DIR / "ranking_stability_rmse.tsv", args.overwrite)
    atomic_write_tsv(rank_wrmse, OUTPUT_DIR / "ranking_stability_wrmse.tsv", args.overwrite)
    atomic_write_tsv(metadata_df, OUTPUT_DIR / "bootstrap_runtime_metadata.tsv", args.overwrite)
    atomic_write_tsv(safety_df, OUTPUT_DIR / "a_ranking_safety_checks.tsv", args.overwrite)
    if convergence_df is not None:
        atomic_write_tsv(convergence_df, OUTPUT_DIR / "bootstrap_convergence_diagnostics.tsv", args.overwrite)
    report = build_report(args, elapsed, paired, ci_df, pairwise_df, rank_rmse, rank_wrmse, safety_df, metadata_df, convergence_df)
    atomic_write_text(report, DEFAULT_REPORT_PATH, args.overwrite)

    status_counts = safety_df["status"].value_counts().to_dict()
    logger.info("safety_status_counts=%s", status_counts)
    logger.info("elapsed_seconds=%.1f", elapsed)
    if (safety_df["status"] != "PASS").any():
        logger.error("one or more safety checks failed; see %s", OUTPUT_DIR / "a_ranking_safety_checks.tsv")
        return 1
    logger.info("PASS ranking uncertainty bootstrap complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
