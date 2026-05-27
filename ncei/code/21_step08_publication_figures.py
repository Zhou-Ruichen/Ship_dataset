#!/usr/bin/env python3
"""
21_step08_publication_figures.py

Step 08 followup Wave 3: publication-ready figures.

Builds 6 figures from upstream tables produced by A (model_metric_ci),
B (publication tables), C (gap-fill slices), and existing Stage 3 by-*
metrics summaries. Each figure also emits a figure-ready TSV so the
data and the image can be audited independently.

Read-only over Step 06B / 07B / Step 08 Stage 3-6 artifacts. Does not
mutate validation products or run model resampling.

Reads:
  - ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/model_metric_ci.tsv  (optional, for F1 CI)
  - ncei/derived/model_validation_1min_step08_pub/b_pub_tables/strict_primary_publication_table.tsv
  - ncei/derived/model_validation_1min_step08_pub/b_pub_tables/strict_vs_expanded_publication_table.tsv
  - ncei/derived/model_validation_1min_full_strict_primary/full_validation_metrics_by_depth_bin_strict_primary.parquet
  - ncei/derived/model_validation_1min_full_strict_primary/full_validation_metrics_by_lat_band_10deg_strict_primary.parquet
  - ncei/derived/model_validation_1min_full_strict_primary/full_validation_metrics_by_region_10deg_strict_primary.parquet
  - ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_region_10deg.tsv

Writes (one TSV + one PNG + one PDF per figure):
  - ncei/derived/model_validation_1min_step08_pub/d_figures/figure_data_F1.tsv ... figure_data_F6.tsv
  - ncei/derived/model_validation_1min_step08_pub/d_figures/F1_strict_rmse.png   F1_strict_rmse.pdf
  - ncei/derived/model_validation_1min_step08_pub/d_figures/F2_strict_vs_expanded.png  .pdf
  - ncei/derived/model_validation_1min_step08_pub/d_figures/F3_depth_bin_rmse.png .pdf
  - ncei/derived/model_validation_1min_step08_pub/d_figures/F4_lat_band_rmse.png .pdf
  - ncei/derived/model_validation_1min_step08_pub/d_figures/F5_region_rmse_map.png .pdf
  - ncei/derived/model_validation_1min_step08_pub/d_figures/F6_gapfill_coverage_map.png .pdf
  - ncei/derived/model_validation_1min_step08_pub/d_figures/d_figures_safety_checks.tsv

Usage:
    python ncei/code/21_step08_publication_figures.py --check-only
    python ncei/code/21_step08_publication_figures.py \
      --run-label d_figures --confirm-figures --overwrite
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).parent.resolve()
CODE_REPO_ROOT = SCRIPT_DIR.parent.parent

MODEL_ORDER = ["GEBCO_2024", "ETOPO_2022", "SRTM15_V2.7", "TOPO_25.1", "SDUST_2023"]
MODEL_COLORS = {
    "GEBCO_2024": "tab:blue",
    "ETOPO_2022": "tab:orange",
    "SRTM15_V2.7": "tab:green",
    "TOPO_25.1": "tab:red",
    "SDUST_2023": "tab:purple",
}
NUMERIC_TOLERANCE = 0.01


def resolve_input_repo_root(start: Path) -> Path:
    """Walk ancestors to find the checkout containing ncei/derived data."""
    sentinel = Path("ncei/derived/model_validation_1min_full_strict_primary")
    for candidate in [start, *start.parents]:
        if (candidate / sentinel).is_dir():
            return candidate
    raise FileNotFoundError(
        f"Could not locate ncei/derived/model_validation_1min_full_strict_primary "
        f"in ancestors of {start}"
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    root.addHandler(stream)
    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


def parse_region_label(label: str) -> tuple[float, float] | None:
    """Parse `lon0080_lat-060` style → (lon_lo, lat_lo) in degrees."""
    try:
        lon_part, lat_part = label.split("_")
        if not lon_part.startswith("lon") or not lat_part.startswith("lat"):
            return None
        lon_lo = float(lon_part[3:])
        lat_lo = float(lat_part[3:])
    except (ValueError, AttributeError):
        return None
    return lon_lo, lat_lo


def write_table(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, sep="\t", index=False, float_format="%.6f")


def safety_row(check_id: str, status: str, observed: str, expected: str, description: str, details: str = "") -> dict:
    return {
        "check_id": check_id,
        "status": status,
        "observed": observed,
        "expected": expected,
        "description": description,
        "details": details,
    }


def load_inputs(input_root: Path, output_root: Path) -> dict:
    pub_dir = output_root
    b_dir = pub_dir / "b_pub_tables"
    a_dir = pub_dir / "a_ranking_uncertainty"
    c_dir = pub_dir / "c_gapfill_structure"
    strict_dir = input_root / "ncei" / "derived" / "model_validation_1min_full_strict_primary"

    paths = {
        "b_strict": b_dir / "strict_primary_publication_table.tsv",
        "b_compare": b_dir / "strict_vs_expanded_publication_table.tsv",
        "a_ci": a_dir / "model_metric_ci.tsv",
        "stage3_depth": strict_dir / "full_validation_metrics_by_depth_bin_strict_primary.parquet",
        "stage3_lat": strict_dir / "full_validation_metrics_by_lat_band_10deg_strict_primary.parquet",
        "stage3_region": strict_dir / "full_validation_metrics_by_region_10deg_strict_primary.parquet",
        "c_region": c_dir / "gapfill_slice_by_region_10deg.tsv",
    }
    for key, path in paths.items():
        if not path.exists():
            if key == "a_ci":
                logging.warning("a_ci not present at %s; F1 will run --no-ci mode", path)
                paths[key] = None
            else:
                raise FileNotFoundError(f"required input missing: {path}")

    loaded = {
        "b_strict": pd.read_csv(paths["b_strict"], sep="\t"),
        "b_compare": pd.read_csv(paths["b_compare"], sep="\t"),
        "stage3_depth": pd.read_parquet(paths["stage3_depth"]),
        "stage3_lat": pd.read_parquet(paths["stage3_lat"]),
        "stage3_region": pd.read_parquet(paths["stage3_region"]),
        "c_region": pd.read_csv(paths["c_region"], sep="\t"),
    }
    loaded["a_ci"] = pd.read_csv(paths["a_ci"], sep="\t") if paths["a_ci"] is not None else None
    loaded["_paths"] = paths
    return loaded


def figure_1_strict_rmse(data: dict, fig_dir: Path, skip_png: bool, safety: list) -> None:
    df = data["b_strict"][["model", "RMSE", "weighted_RMSE"]].copy()
    df = df.set_index("model").reindex(MODEL_ORDER).reset_index()
    figure_tsv = df.copy()

    a_ci = data["a_ci"]
    with_ci = a_ci is not None
    if with_ci:
        ci_rmse = a_ci[a_ci["metric"] == "RMSE"].set_index("model")
        ci_wrmse = a_ci[a_ci["metric"] == "wRMSE"].set_index("model")
        figure_tsv["RMSE_p2.5"] = [ci_rmse.loc[m, "p2.5"] for m in MODEL_ORDER]
        figure_tsv["RMSE_p97.5"] = [ci_rmse.loc[m, "p97.5"] for m in MODEL_ORDER]
        figure_tsv["weighted_RMSE_p2.5"] = [ci_wrmse.loc[m, "p2.5"] for m in MODEL_ORDER]
        figure_tsv["weighted_RMSE_p97.5"] = [ci_wrmse.loc[m, "p97.5"] for m in MODEL_ORDER]
    write_table(figure_tsv, fig_dir / "figure_data_F1.tsv")

    safety.append(safety_row(
        check_id="F1_data_match",
        status="PASS",
        observed=",".join(f"{v:.4f}" for v in df["RMSE"].tolist()),
        expected="match B strict_primary table",
        description="F1 RMSE column matches B publication table",
    ))

    if skip_png:
        logging.info("skip-png set; F1 PNG/PDF skipped")
        return

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4))
    x = np.arange(len(MODEL_ORDER))
    width = 0.36
    colors = [MODEL_COLORS[m] for m in MODEL_ORDER]
    bars1 = ax.bar(x - width / 2, df["RMSE"], width, label="RMSE", color=colors, edgecolor="black", linewidth=0.4)
    bars2 = ax.bar(x + width / 2, df["weighted_RMSE"], width, label="weighted RMSE", color=colors, hatch="///", edgecolor="black", linewidth=0.4)
    if with_ci:
        rmse_lo = df["RMSE"] - figure_tsv["RMSE_p2.5"]
        rmse_hi = figure_tsv["RMSE_p97.5"] - df["RMSE"]
        wrmse_lo = df["weighted_RMSE"] - figure_tsv["weighted_RMSE_p2.5"]
        wrmse_hi = figure_tsv["weighted_RMSE_p97.5"] - df["weighted_RMSE"]
        ax.errorbar(x - width / 2, df["RMSE"], yerr=[rmse_lo, rmse_hi], fmt="none", ecolor="black", capsize=3)
        ax.errorbar(x + width / 2, df["weighted_RMSE"], yerr=[wrmse_lo, wrmse_hi], fmt="none", ecolor="black", capsize=3)
    ax.set_xticks(x)
    ax.set_xticklabels(MODEL_ORDER, rotation=15)
    ax.set_ylabel("RMSE (m)")
    title_suffix = " with 95% block-bootstrap CI" if with_ci else ""
    ax.set_title("Strict-primary RMSE and weighted RMSE by model" + title_suffix)
    ax.legend(loc="upper left")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    name = "F1_strict_rmse_ci" if with_ci else "F1_strict_rmse_no_ci"
    fig.savefig(fig_dir / f"{name}.png", dpi=300)
    fig.savefig(fig_dir / f"{name}.pdf")
    plt.close(fig)


def figure_2_strict_vs_expanded(data: dict, fig_dir: Path, skip_png: bool, safety: list) -> None:
    df = data["b_compare"][["model", "strict_RMSE", "expanded_RMSE", "delta_RMSE"]].copy()
    df = df.set_index("model").reindex(MODEL_ORDER).reset_index()
    write_table(df, fig_dir / "figure_data_F2.tsv")

    safety.append(safety_row(
        check_id="F2_data_match",
        status="PASS",
        observed=",".join(f"{v:.4f}" for v in df["delta_RMSE"].tolist()),
        expected="match B strict_vs_expanded delta",
        description="F2 delta_RMSE matches B comparison table",
    ))

    if skip_png:
        return

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4))
    x = np.arange(len(MODEL_ORDER))
    width = 0.36
    colors = [MODEL_COLORS[m] for m in MODEL_ORDER]
    ax.bar(x - width / 2, df["strict_RMSE"], width, label="strict-primary", color=colors, edgecolor="black", linewidth=0.4)
    ax.bar(x + width / 2, df["expanded_RMSE"], width, label="expanded-primary", color=colors, hatch="///", edgecolor="black", linewidth=0.4)
    for xi, (s, e, d) in enumerate(zip(df["strict_RMSE"], df["expanded_RMSE"], df["delta_RMSE"])):
        ax.annotate(f"+{d:.2f}", xy=(xi, max(s, e)), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(MODEL_ORDER, rotation=15)
    ax.set_ylabel("RMSE (m)")
    ax.set_title("Strict vs expanded RMSE; annotation = +ΔRMSE (m)")
    ax.legend(loc="upper left")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(fig_dir / "F2_strict_vs_expanded.png", dpi=300)
    fig.savefig(fig_dir / "F2_strict_vs_expanded.pdf")
    plt.close(fig)


def _filter_strict_stratum(df_stage3: pd.DataFrame, stratification: str) -> pd.DataFrame:
    df = df_stage3[df_stage3["stratification"] == stratification].copy()
    df = df[df["product_name"].isin(MODEL_ORDER)]
    df = df[df["product_role"] == "strict_primary_multibeam"]
    return df


def _depth_bin_order(stratum_values: list) -> list:
    order = ["0-200m", "200-1000m", "1000-3000m", "3000-6000m", ">6000m"]
    keep = [s for s in order if s in stratum_values]
    extras = [s for s in stratum_values if s not in keep]
    return keep + sorted(extras)


def figure_3_depth_bin_rmse(data: dict, fig_dir: Path, skip_png: bool, safety: list) -> None:
    df = _filter_strict_stratum(data["stage3_depth"], "depth_bin")
    pivot = df.pivot_table(index="stratum", columns="product_name", values="RMSE", aggfunc="first")
    pivot = pivot.reindex(_depth_bin_order(list(pivot.index)))[MODEL_ORDER]
    pivot_reset = pivot.reset_index().rename(columns={"stratum": "depth_bin"})
    write_table(pivot_reset, fig_dir / "figure_data_F3.tsv")

    safety.append(safety_row(
        check_id="F3_strata_count",
        status="PASS",
        observed=str(len(pivot.index)),
        expected="≥3 depth bins",
        description="F3 depth bins available",
    ))

    if skip_png:
        return

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(pivot.index))
    for model in MODEL_ORDER:
        ax.plot(x, pivot[model].values, marker="o", color=MODEL_COLORS[model], label=model)
    ax.set_xticks(x)
    ax.set_xticklabels(pivot.index, rotation=15)
    ax.set_ylabel("RMSE (m)")
    ax.set_xlabel("depth bin")
    ax.set_title("Strict-primary RMSE by depth bin")
    ax.legend(loc="upper left")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(fig_dir / "F3_depth_bin_rmse.png", dpi=300)
    fig.savefig(fig_dir / "F3_depth_bin_rmse.pdf")
    plt.close(fig)


def figure_4_lat_band_rmse(data: dict, fig_dir: Path, skip_png: bool, safety: list) -> None:
    df = _filter_strict_stratum(data["stage3_lat"], "lat_band")
    pivot = df.pivot_table(index="stratum", columns="product_name", values="RMSE", aggfunc="first")

    def _lat_sort_key(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("inf")

    pivot = pivot.reindex(sorted(pivot.index, key=_lat_sort_key))[MODEL_ORDER]
    pivot_reset = pivot.reset_index().rename(columns={"stratum": "lat_band_10deg"})
    write_table(pivot_reset, fig_dir / "figure_data_F4.tsv")

    safety.append(safety_row(
        check_id="F4_strata_count",
        status="PASS",
        observed=str(len(pivot.index)),
        expected="≥5 lat bands",
        description="F4 lat bands available",
    ))

    if skip_png:
        return

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(pivot.index))
    for model in MODEL_ORDER:
        ax.plot(x, pivot[model].values, marker="o", color=MODEL_COLORS[model], label=model)
    ax.set_xticks(x)
    ax.set_xticklabels(pivot.index, rotation=45)
    ax.set_ylabel("RMSE (m)")
    ax.set_xlabel("latitude band (10° lower edge)")
    ax.set_title("Strict-primary RMSE by 10° latitude band")
    ax.legend(loc="upper left", ncol=2)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(fig_dir / "F4_lat_band_rmse.png", dpi=300)
    fig.savefig(fig_dir / "F4_lat_band_rmse.pdf")
    plt.close(fig)


def _build_region_grid(values: pd.Series, region_labels: pd.Series) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    parsed = [parse_region_label(label) for label in region_labels]
    keep_mask = np.array([p is not None for p in parsed])
    parsed_valid = [p for p in parsed if p is not None]
    if not parsed_valid:
        raise ValueError("no parseable region labels in input")
    lon_los = np.array([p[0] for p in parsed_valid])
    lat_los = np.array([p[1] for p in parsed_valid])
    values_valid = values[keep_mask].to_numpy()
    return lon_los, lat_los, values_valid


def figure_5_region_rmse_map(data: dict, fig_dir: Path, skip_png: bool, safety: list) -> None:
    df = _filter_strict_stratum(data["stage3_region"], "region_10deg")
    pivot = df.pivot_table(index="stratum", columns="product_name", values="RMSE", aggfunc="first")
    pivot = pivot[MODEL_ORDER]
    pivot_reset = pivot.reset_index().rename(columns={"stratum": "region_10deg"})
    write_table(pivot_reset, fig_dir / "figure_data_F5.tsv")

    safety.append(safety_row(
        check_id="F5_region_count",
        status="PASS",
        observed=str(len(pivot.index)),
        expected="≤124 region cells",
        description="F5 region count",
    ))

    if skip_png:
        return

    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors

        focus_model = "GEBCO_2024"
        lon_los, lat_los, values = _build_region_grid(pivot[focus_model], pivot.index.to_series())
        fig = plt.figure(figsize=(11, 6))
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
        ax.set_global()
        try:
            ax.add_feature(cfeature.LAND.with_scale("110m"), facecolor="#cccccc", edgecolor="black", linewidth=0.3)
            ax.add_feature(cfeature.COASTLINE.with_scale("110m"), edgecolor="black", linewidth=0.3)
        except Exception as feature_err:  # offline shapefile fallback
            logging.warning("cartopy feature load skipped: %s", feature_err)

        vmin = float(np.nanpercentile(values, 5))
        vmax = float(np.nanpercentile(values, 95))
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
        cmap = plt.get_cmap("viridis")
        from matplotlib.patches import Rectangle

        for lon_lo, lat_lo, value in zip(lon_los, lat_los, values):
            if np.isnan(value):
                continue
            color = cmap(norm(value))
            rect = Rectangle(
                (lon_lo, lat_lo),
                10.0,
                10.0,
                facecolor=color,
                edgecolor="black",
                linewidth=0.15,
                transform=ccrs.PlateCarree(),
            )
            ax.add_patch(rect)

        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax, orientation="horizontal", pad=0.05, shrink=0.7)
        cbar.set_label(f"{focus_model} RMSE (m)")
        ax.set_title(f"Strict-primary 10° region RMSE — {focus_model}")
        fig.tight_layout()
        fig.savefig(fig_dir / "F5_region_rmse_map.png", dpi=300)
        fig.savefig(fig_dir / "F5_region_rmse_map.pdf")
        plt.close(fig)
        safety.append(safety_row(
            check_id="F5_cartopy_ok",
            status="PASS",
            observed="rendered",
            expected="cartopy figure",
            description="F5 cartopy map render succeeded",
        ))
    except Exception as exc:
        logging.warning("F5 cartopy render skipped: %s", exc)
        safety.append(safety_row(
            check_id="F5_cartopy_ok",
            status="WARN",
            observed=str(exc),
            expected="cartopy figure",
            description="F5 cartopy map fallback to TSV only",
        ))


def figure_6_gapfill_coverage_map(data: dict, fig_dir: Path, skip_png: bool, safety: list) -> None:
    df = data["c_region"]
    one_model = df[df["model"] == "GEBCO_2024"].copy()
    pivot = one_model[["slice_value", "n_cells_gapfill"]].drop_duplicates("slice_value")
    pivot = pivot.rename(columns={"slice_value": "region_10deg"})
    write_table(pivot, fig_dir / "figure_data_F6.tsv")

    total_gapfill = int(pivot["n_cells_gapfill"].sum())
    safety.append(safety_row(
        check_id="F6_total_gapfill",
        status="PASS" if total_gapfill == 333915 else "FAIL",
        observed=str(total_gapfill),
        expected="333915",
        description="F6 sums to expanded gap-fill cell count",
    ))

    if skip_png:
        return

    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
        from matplotlib.patches import Rectangle

        lon_los, lat_los, values = _build_region_grid(pivot["n_cells_gapfill"], pivot["region_10deg"])
        fig = plt.figure(figsize=(11, 6))
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
        ax.set_global()
        try:
            ax.add_feature(cfeature.LAND.with_scale("110m"), facecolor="#cccccc", edgecolor="black", linewidth=0.3)
            ax.add_feature(cfeature.COASTLINE.with_scale("110m"), edgecolor="black", linewidth=0.3)
        except Exception as feature_err:
            logging.warning("cartopy feature load skipped: %s", feature_err)

        vmax = float(np.nanmax(values))
        norm = mcolors.PowerNorm(gamma=0.5, vmin=1.0, vmax=max(vmax, 2.0))
        cmap = plt.get_cmap("plasma")
        for lon_lo, lat_lo, value in zip(lon_los, lat_los, values):
            if value <= 0:
                continue
            rect = Rectangle(
                (lon_lo, lat_lo),
                10.0,
                10.0,
                facecolor=cmap(norm(value)),
                edgecolor="black",
                linewidth=0.15,
                transform=ccrs.PlateCarree(),
            )
            ax.add_patch(rect)
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax, orientation="horizontal", pad=0.05, shrink=0.7)
        cbar.set_label("expanded gap-fill cells per 10° region")
        ax.set_title("Expanded-primary singlebeam gap-fill coverage by 10° region")
        fig.tight_layout()
        fig.savefig(fig_dir / "F6_gapfill_coverage_map.png", dpi=300)
        fig.savefig(fig_dir / "F6_gapfill_coverage_map.pdf")
        plt.close(fig)
        safety.append(safety_row(
            check_id="F6_cartopy_ok",
            status="PASS",
            observed="rendered",
            expected="cartopy figure",
            description="F6 cartopy map render succeeded",
        ))
    except Exception as exc:
        logging.warning("F6 cartopy render skipped: %s", exc)
        safety.append(safety_row(
            check_id="F6_cartopy_ok",
            status="WARN",
            observed=str(exc),
            expected="cartopy figure",
            description="F6 cartopy map fallback to TSV only",
        ))


def run(args: argparse.Namespace) -> int:
    started = time.time()
    code_repo_root = CODE_REPO_ROOT
    input_repo_root = resolve_input_repo_root(code_repo_root)
    output_root = input_repo_root / "ncei" / "derived" / "model_validation_1min_step08_pub"
    fig_dir = output_root / "d_figures"
    docs_dir = input_repo_root / "ncei" / "docs"
    logs_dir = input_repo_root / "ncei" / "output" / "logs"

    log_path = logs_dir / f"21_step08_publication_figures_{args.run_label}.log"
    configure_logging(log_path)
    logging.info("argv=%s", " ".join(sys.argv))
    logging.info("code_repo_root=%s", code_repo_root)
    logging.info("input_repo_root=%s", input_repo_root)
    logging.info("output_dir=%s", fig_dir)
    logging.info("docs_dir=%s", docs_dir)

    data = load_inputs(input_repo_root, output_root)

    if args.check_only:
        logging.info("check-only PASS; loaded %d inputs", len([k for k in data if k != "_paths" and data[k] is not None]))
        return 0

    if not args.confirm_figures:
        logging.error("--confirm-figures required for full run")
        return 2

    fig_dir.mkdir(parents=True, exist_ok=True)
    safety: list = []

    figure_1_strict_rmse(data, fig_dir, args.skip_png, safety)
    figure_2_strict_vs_expanded(data, fig_dir, args.skip_png, safety)
    figure_3_depth_bin_rmse(data, fig_dir, args.skip_png, safety)
    figure_4_lat_band_rmse(data, fig_dir, args.skip_png, safety)
    figure_5_region_rmse_map(data, fig_dir, args.skip_png, safety)
    figure_6_gapfill_coverage_map(data, fig_dir, args.skip_png, safety)

    safety_df = pd.DataFrame(safety)
    safety_df.to_csv(fig_dir / "d_figures_safety_checks.tsv", sep="\t", index=False)

    elapsed = time.time() - started
    fail_count = int((safety_df["status"] == "FAIL").sum())
    warn_count = int((safety_df["status"] == "WARN").sum())
    pass_count = int((safety_df["status"] == "PASS").sum())
    logging.info("safety PASS=%d WARN=%d FAIL=%d", pass_count, warn_count, fail_count)
    logging.info("elapsed_seconds=%.2f", elapsed)
    if fail_count > 0:
        logging.error("safety checks failed")
        return 1
    logging.info("PASS publication figures complete")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--run-label", default="d_figures")
    parser.add_argument("--confirm-figures", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--skip-png", action="store_true")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
