#!/usr/bin/env python3
"""
09_batch_validate_swot_t1.py — Batch reconstruct & validate all SWOT T1 model predictions.

Workflow:
  1. Scan all experiment directories for T1 prediction NPZ files
  2. Reconstruct absolute bathymetry: absolute = prediction + GEBCO_lowpass
  3. Sample each reconstructed grid at ship validation cell locations
  4. Compute metrics (bias, MAE, RMSE, correlation, etc.)
  5. Output ranked comparison table + parquet with per-model metrics

Usage:
  python code/09_batch_validate_swot_t1.py
  python code/09_batch_validate_swot_t1.py --skip-reconstruct   # use existing reconstructed files
  python code/09_batch_validate_swot_t1.py --experiments-dir /path/to/3-evaluations
  python code/09_batch_validate_swot_t1.py --top-n 10           # only process top-N by prior RMSE
"""

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import RegularGridInterpolator

# ─── Configuration ───────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SWOT_ROOT = Path("/mnt/data2/06-Projects/01-SWOT/04-SWOT_seafloor")
EVALUATIONS_DIR = SWOT_ROOT / "output" / "3-evaluations"
SOURCE_DATA_DIR = SWOT_ROOT / "output" / "1-data"
SHIP_CELLS_PATH = PROJECT_ROOT / "derived" / "validation_cells_1min" / "primary_ship_validation_cells_1min.parquet"
OUTPUT_DIR = PROJECT_ROOT / "derived" / "swot_t1_batch_validation"

# T1 footprint
T1_LON_MIN, T1_LON_MAX = 105.0, 120.0
T1_LAT_MIN, T1_LAT_MAX = -45.0, -35.0

# Source data for GEBCO lowpass (same for all T1 variants)
T1_SOURCE_FILE = SOURCE_DATA_DIR / "bandpass_T1_norm.npz"


def discover_t1_predictions(evaluations_dir: Path) -> list[dict]:
    """Scan all experiment directories for T1 prediction files."""
    predictions = []
    if not evaluations_dir.exists():
        print(f"ERROR: evaluations dir not found: {evaluations_dir}")
        return predictions

    for exp_name in sorted(os.listdir(evaluations_dir)):
        exp_dir = evaluations_dir / exp_name
        if not exp_dir.is_dir():
            continue
        # Find eval_on_bandpass_T1* subdirectories
        for item in sorted(os.listdir(exp_dir)):
            if not item.startswith("eval_on_bandpass_T1"):
                continue
            eval_dir = exp_dir / item
            pred_file = eval_dir / "prediction.npz"
            if pred_file.exists():
                predictions.append({
                    "experiment": exp_name,
                    "eval_name": item,
                    "prediction_path": str(pred_file),
                    "short_name": exp_name,  # will be refined below
                })

    return predictions


def derive_source_file(eval_name: str) -> Path | None:
    """Derive source NPZ path from eval directory name.

    eval_on_bandpass_T1_norm        -> bandpass_T1_norm.npz
    eval_on_bandpass_T1_3_norm      -> bandpass_T1_3_norm.npz
    eval_on_bandpass_T1             -> bandpass_T1.npz
    eval_on_bandpass_T1_1113_1820_norm -> bandpass_T1_1113_1820_norm.npz (may not exist)
    """
    # Strip 'eval_on_' prefix
    source_name = eval_name.replace("eval_on_", "", 1)
    source_path = SOURCE_DATA_DIR / f"{source_name}.npz"
    if source_path.exists():
        return source_path
    # Fallback: try without _norm suffix
    if source_name.endswith("_norm"):
        alt_path = SOURCE_DATA_DIR / f"{source_name[:-5]}.npz"
        if alt_path.exists():
            return alt_path
    # Final fallback to T1_norm
    return T1_SOURCE_FILE


def reconstruct_absolute(prediction: np.ndarray, source_file: Path) -> np.ndarray:
    """Reconstruct absolute bathymetry from bandpass prediction.

    formula: absolute = prediction + (gebco_raw - gebco_bandpass)
    """
    src = np.load(str(source_file))
    gebco_raw = src["gebco_raw"]
    gebco_bandpass = src["gebco_bandpass"]
    lowpass = gebco_raw - gebco_bandpass

    # Handle shape mismatch (e.g., different resolution)
    if prediction.shape != lowpass.shape:
        print(f"    Shape mismatch: pred {prediction.shape} vs lowpass {lowpass.shape}, interpolating...")
        from scipy.interpolate import RegularGridInterpolator
        src_lat = src["gebco_lat"]
        src_lon = src["gebco_lon"]
        interp = RegularGridInterpolator(
            (src_lat[::-1], src_lon),
            lowpass[::-1],
            method="linear",
            bounds_error=False,
            fill_value=None,
        )
        # Build target grid from prediction's lat/lon (use default T1 range)
        n_lat, n_lon = prediction.shape
        target_lat = np.linspace(T1_LAT_MAX, T1_LAT_MIN, n_lat)  # high to low
        target_lon = np.linspace(T1_LON_MIN, T1_LON_MAX, n_lon)
        lon_grid, lat_grid = np.meshgrid(target_lon, target_lat)
        points = np.column_stack([lat_grid.ravel(), lon_grid.ravel()])
        lowpass = interp(points).reshape(n_lat, n_lon)

    absolute = prediction + lowpass
    return absolute


def batch_reconstruct(predictions: list[dict], output_dir: Path, skip_existing: bool = True) -> list[dict]:
    """Reconstruct absolute bathymetry for all predictions.

    Returns updated predictions list with 'reconstructed_path' added.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    reconstructed_dir = output_dir / "reconstructed"
    reconstructed_dir.mkdir(exist_ok=True)

    # Load GEBCO lowpass once (used for fallback)
    print(f"\n{'='*60}")
    print("Phase 1: Batch reconstruction")
    print(f"{'='*60}")

    # Check if we can reuse a single lowpass for all
    # All T1 source files have identical gebco_raw and gebco_bandpass shapes
    # Load from T1_SOURCE_FILE as the canonical source
    src_canon = np.load(str(T1_SOURCE_FILE))
    lowpass_canon = src_canon["gebco_raw"] - src_canon["gebco_bandpass"]
    src_lat_canon = src_canon["gebco_lat"]
    src_lon_canon = src_canon["gebco_lon"]
    print(f"  GEBCO lowpass: shape={lowpass_canon.shape}, range=[{lowpass_canon.min():.0f}, {lowpass_canon.max():.0f}]")

    n_total = len(predictions)
    for i, pred_info in enumerate(predictions):
        exp_name = pred_info["experiment"]
        eval_name = pred_info["eval_name"]
        out_name = f"absolute_{exp_name}__{eval_name}.npz"
        out_path = reconstructed_dir / out_name
        pred_info["reconstructed_path"] = str(out_path)

        if skip_existing and out_path.exists():
            print(f"  [{i+1}/{n_total}] SKIP (exists): {exp_name}/{eval_name}")
            continue

        print(f"  [{i+1}/{n_total}] Reconstructing: {exp_name}/{eval_name}")

        # Load prediction
        pred_data = np.load(pred_info["prediction_path"])
        prediction = pred_data["prediction"]
        lons = pred_data["lons"]
        lats = pred_data["lats"]

        # Find matching source file for this eval
        source_file = derive_source_file(eval_name)

        # Reconstruct
        if prediction.shape == lowpass_canon.shape:
            absolute = prediction + lowpass_canon
        else:
            # Shape mismatch — load source-specific lowpass
            absolute = reconstruct_absolute(prediction, source_file)

        # Save
        np.savez_compressed(
            str(out_path),
            prediction_absolute=absolute.astype(np.float32),
            lons=lons,
            lats=lats,
            source_experiment=exp_name,
            source_eval=eval_name,
        )
        valid = np.isfinite(absolute)
        print(f"    -> shape={absolute.shape}, range=[{absolute[valid].min():.0f}, {absolute[valid].max():.0f}], "
              f"saved {out_path.stat().st_size / 1024 / 1024:.1f} MB")

    print(f"\n  Reconstructed {n_total} predictions -> {reconstructed_dir}/")
    return predictions


def batch_validate(predictions: list[dict], output_dir: Path) -> pd.DataFrame:
    """Validate all reconstructed predictions against T1 ship cells.

    Returns DataFrame with metrics per model.
    """
    print(f"\n{'='*60}")
    print("Phase 2: Batch validation against ship cells")
    print(f"{'='*60}")

    # Load ship cells for T1
    print("  Loading ship cells...")
    ship_df = pd.read_parquet(str(SHIP_CELLS_PATH))
    t1_mask = (
        (ship_df["lon_center"] >= T1_LON_MIN) & (ship_df["lon_center"] <= T1_LON_MAX) &
        (ship_df["lat_center"] >= T1_LAT_MIN) & (ship_df["lat_center"] <= T1_LAT_MAX)
    )
    ship_t1 = ship_df[t1_mask].copy()
    print(f"  T1 ship cells: {len(ship_t1):,}")
    if len(ship_t1) == 0:
        print("  ERROR: No ship cells in T1 footprint!")
        return pd.DataFrame()

    ship_lons = ship_t1["lon_center"].values
    ship_lats = ship_t1["lat_center"].values
    ship_depths = ship_t1["ship_depth_m"].values  # positive down
    ship_elevs = ship_t1["ship_elev_m"].values     # negative down (elevation convention)

    # Metrics storage
    all_metrics = []

    for i, pred_info in enumerate(predictions):
        exp_name = pred_info["experiment"]
        eval_name = pred_info["eval_name"]
        recon_path = pred_info["reconstructed_path"]

        print(f"  [{i+1}/{len(predictions)}] {exp_name}/{eval_name}")

        if not os.path.exists(recon_path):
            print(f"    SKIP: reconstructed file not found")
            continue

        data = np.load(recon_path)
        grid = data["prediction_absolute"]
        lons = data["lons"]
        lats = data["lats"]

        # Create interpolator (grid is lat-major, lats may be descending)
        if lats[0] > lats[-1]:
            # Descending lat — flip
            grid_interp = grid[::-1]
            lats_interp = lats[::-1]
        else:
            grid_interp = grid
            lats_interp = lats

        interp = RegularGridInterpolator(
            (lats_interp, lons),
            grid_interp,
            method="linear",
            bounds_error=False,
            fill_value=np.nan,
        )

        # Sample at ship cell locations
        points = np.column_stack([ship_lats, ship_lons])
        sampled = interp(points)

        # Compute metrics
        valid = np.isfinite(sampled) & np.isfinite(ship_depths)
        n_valid = valid.sum()

        if n_valid < 10:
            print(f"    SKIP: only {n_valid} valid samples")
            continue

        pred_depths = sampled[valid]  # prediction is elevation convention (negative = depth)
        true_depths = ship_depths[valid]  # positive down

        # Convert prediction to positive-down depth for comparison
        pred_depth_pos = -pred_depths  # flip sign
        errors = pred_depth_pos - true_depths

        bias = np.mean(errors)
        mae = np.mean(np.abs(errors))
        rmse = np.sqrt(np.mean(errors**2))
        medae = np.median(np.abs(errors))
        correlation = np.corrcoef(pred_depth_pos, true_depths)[0, 1]

        # Depth-binned metrics
        depth_bins = [(0, 4000, "A_shallow"), (4000, 5000, "B_mid"), (5000, 7000, "C_deep")]
        bin_metrics = {}
        for d_min, d_max, bin_name in depth_bins:
            bmask = (true_depths >= d_min) & (true_depths < d_max)
            if bmask.sum() < 5:
                continue
            b_errors = errors[bmask]
            bin_metrics[f"bias_{bin_name}"] = np.mean(b_errors)
            bin_metrics[f"rmse_{bin_name}"] = np.sqrt(np.mean(b_errors**2))

        metrics = {
            "experiment": exp_name,
            "eval_name": eval_name,
            "n_cells": n_valid,
            "bias_m": round(bias, 2),
            "mae_m": round(mae, 2),
            "rmse_m": round(rmse, 2),
            "medae_m": round(medae, 2),
            "correlation": round(correlation, 4),
            "pred_range_min": round(float(np.nanmin(pred_depths)), 0),
            "pred_range_max": round(float(np.nanmax(pred_depths)), 0),
        }
        metrics.update({k: round(v, 2) for k, v in bin_metrics.items()})
        all_metrics.append(metrics)
        print(f"    bias={bias:+.1f}  MAE={mae:.1f}  RMSE={rmse:.1f}  r={correlation:.4f}  n={n_valid}")

    df = pd.DataFrame(all_metrics)
    return df


def validate_global_products(output_dir: Path) -> pd.DataFrame:
    """Validate global products (ETOPO, GEBCO, etc.) on T1 ship cells for comparison."""
    print(f"\n{'='*60}")
    print("Phase 3: Global product validation on T1 (for comparison baseline)")
    print(f"{'='*60}")

    # Load ship cells
    ship_df = pd.read_parquet(str(SHIP_CELLS_PATH))
    t1_mask = (
        (ship_df["lon_center"] >= T1_LON_MIN) & (ship_df["lon_center"] <= T1_LON_MAX) &
        (ship_df["lat_center"] >= T1_LAT_MIN) & (ship_df["lat_center"] <= T1_LAT_MAX)
    )
    ship_t1 = ship_df[t1_mask].copy()
    ship_lons = ship_t1["lon_center"].values
    ship_lats = ship_t1["lat_center"].values
    ship_depths = ship_t1["ship_depth_m"].values

    # Global products — use the existing 08 script's open_product logic
    # For simplicity, directly load and sample
    from collections import OrderedDict

    # Define global products
    global_products = OrderedDict([
        ("ETOPO_2022", {
            "path": "/mnt/data2/06-Projects/01-SWOT/04-SWOT_seafloor/output/0-external/ETOPO_2022_v1_60s.nc",
            "z_name": "z",
            "lon_name": "lon",
            "lat_name": "lat",
            "z_convention": "elevation",
        }),
        ("GEBCO_2024", {
            "path": "/mnt/data2/06-Projects/01-SWOT/04-SWOT_seafloor/output/0-external/GEBCO_2024.nc",
            "z_name": "elevation",
            "lon_name": "lon",
            "lat_name": "lat",
            "z_convention": "elevation",
        }),
        ("SRTM15_V2.7", {
            "path": "/mnt/data2/06-Projects/01-SWOT/04-SWOT_seafloor/output/0-external/SRTM15_V2.7.nc",
            "z_name": "z",
            "lon_name": "lon",
            "lat_name": "lat",
            "z_convention": "elevation",
        }),
        ("TOPO_25.1", {
            "path": "/mnt/data2/06-Projects/01-SWOT/04-SWOT_seafloor/output/0-external/Topo_25.1.nc",
            "z_name": "z",
            "lon_name": "lon",
            "lat_name": "lat",
            "z_convention": "elevation",
        }),
        ("SDUST_2023", {
            "path": "/mnt/data2/06-Projects/01-SWOT/04-SWOT_seafloor/output/0-external/SDUST_2023.nc",
            "z_name": "z",
            "lon_name": "lon",
            "lat_name": "lat",
            "z_convention": "elevation",
        }),
    ])

    all_metrics = []

    for prod_name, prod_cfg in global_products.items():
        print(f"  {prod_name}: ", end="", flush=True)
        prod_path = prod_cfg["path"]
        if not os.path.exists(prod_path):
            print(f"NOT FOUND")
            continue

        try:
            import xarray as xr
            ds = xr.open_dataset(prod_path)
            z = ds[prod_cfg["z_name"]].values
            lon = ds[prod_cfg["lon_name"]].values
            lat = ds[prod_cfg["lat_name"]].values
            ds.close()

            # Ensure lat is ascending
            if lat[0] > lat[-1]:
                z = z[::-1]
                lat = lat[::-1]

            interp = RegularGridInterpolator(
                (lat, lon), z,
                method="linear",
                bounds_error=False,
                fill_value=np.nan,
            )

            points = np.column_stack([ship_lats, ship_lons])
            sampled = interp(points)

            valid = np.isfinite(sampled) & np.isfinite(ship_depths)
            n_valid = valid.sum()

            if n_valid < 10:
                print(f"only {n_valid} valid")
                continue

            # Convert elevation to positive-down depth
            pred_depth_pos = -sampled[valid]
            true_depths = ship_depths[valid]
            errors = pred_depth_pos - true_depths

            bias = np.mean(errors)
            mae = np.mean(np.abs(errors))
            rmse = np.sqrt(np.mean(errors**2))
            correlation = np.corrcoef(pred_depth_pos, true_depths)[0, 1]

            print(f"bias={bias:+.1f}  MAE={mae:.1f}  RMSE={rmse:.1f}  r={correlation:.4f}  n={n_valid}")

            all_metrics.append({
                "experiment": prod_name,
                "eval_name": "global",
                "n_cells": n_valid,
                "bias_m": round(bias, 2),
                "mae_m": round(mae, 2),
                "rmse_m": round(rmse, 2),
                "medae_m": round(np.median(np.abs(errors)), 2),
                "correlation": round(correlation, 4),
                "is_global": True,
            })
        except Exception as e:
            print(f"ERROR: {e}")

    return pd.DataFrame(all_metrics)


def generate_report(swot_df: pd.DataFrame, global_df: pd.DataFrame, output_dir: Path) -> None:
    """Generate comparison report."""
    print(f"\n{'='*60}")
    print("Phase 4: Generating comparison report")
    print(f"{'='*60}")

    # Mark types
    if not swot_df.empty:
        swot_df["is_swot"] = True
        swot_df["is_global"] = False
    if not global_df.empty:
        global_df["is_swot"] = False
        global_df["is_global"] = True

    # Combine
    all_cols = ["experiment", "eval_name", "n_cells", "bias_m", "mae_m", "rmse_m",
                "medae_m", "correlation", "is_swot", "is_global"]
    extra_cols_swot = [c for c in swot_df.columns if c not in all_cols and c != "is_swot"]
    extra_cols_global = [c for c in global_df.columns if c not in all_cols and c != "is_global"]

    combined = pd.concat([swot_df, global_df], ignore_index=True)
    combined = combined.sort_values("rmse_m")

    # Save full table
    combined_path = output_dir / "t1_all_models_comparison.parquet"
    combined.to_parquet(str(combined_path), index=False)
    print(f"  Saved: {combined_path}")

    # Save TSV
    tsv_path = output_dir / "t1_all_models_comparison.tsv"
    # Select display columns
    display_cols = [c for c in ["experiment", "eval_name", "n_cells", "bias_m", "mae_m",
                                  "rmse_m", "medae_m", "correlation", "is_swot", "is_global"]
                    if c in combined.columns]
    combined[display_cols].to_csv(str(tsv_path), sep="\t", index=False, float_format="%.2f")
    print(f"  Saved: {tsv_path}")

    # Print ranked table
    print(f"\n{'='*80}")
    print("RANKED COMPARISON — All T1 models vs Global products (sorted by RMSE)")
    print(f"{'='*80}")
    print(f"{'Rank':>4}  {'Type':>6}  {'RMSE':>8}  {'MAE':>8}  {'Bias':>8}  {'MedAE':>8}  {'r':>7}  {'Experiment'}")
    print(f"{'─'*4}  {'─'*6}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*7}  {'─'*40}")

    for rank, (_, row) in enumerate(combined.iterrows(), 1):
        type_tag = "SWOT" if row.get("is_swot") else "GLOBAL"
        print(f"{rank:>4}  {type_tag:>6}  {row['rmse_m']:>8.1f}  {row['mae_m']:>8.1f}  "
              f"{row['bias_m']:>+8.1f}  {row['medae_m']:>8.1f}  {row['correlation']:>7.4f}  {row['experiment']}")

    # Highlight best SWOT model
    swot_only = combined[combined["is_swot"] == True].copy() if "is_swot" in combined.columns else pd.DataFrame()
    if not swot_only.empty:
        best = swot_only.iloc[0]
        print(f"\n{'='*80}")
        print(f"Best SWOT model: {best['experiment']}")
        print(f"  RMSE={best['rmse_m']:.1f}m  MAE={best['mae_m']:.1f}m  bias={best['bias_m']:+.1f}m  r={best['correlation']:.4f}")

        # Compare to best global
        global_only = combined[combined["is_global"] == True].copy() if "is_global" in combined.columns else pd.DataFrame()
        if not global_only.empty:
            best_global = global_only.iloc[0]
            print(f"\nBest global product: {best_global['experiment']}")
            print(f"  RMSE={best_global['rmse_m']:.1f}m  MAE={best_global['mae_m']:.1f}m  bias={best_global['bias_m']:+.1f}m  r={best_global['correlation']:.4f}")
            ratio = best['rmse_m'] / best_global['rmse_m'] if best_global['rmse_m'] > 0 else float('inf')
            print(f"\nSWOT/Global RMSE ratio: {ratio:.2f}x")


def main():
    parser = argparse.ArgumentParser(description="Batch reconstruct and validate SWOT T1 predictions")
    parser.add_argument("--experiments-dir", type=str, default=str(EVALUATIONS_DIR),
                        help="Path to 3-evaluations directory")
    parser.add_argument("--skip-reconstruct", action="store_true",
                        help="Skip reconstruction step (use existing files)")
    parser.add_argument("--output-dir", type=str, default=str(OUTPUT_DIR),
                        help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    start_time = time.time()

    # Step 1: Discover predictions
    print("=" * 60)
    print("Discovering T1 predictions...")
    predictions = discover_t1_predictions(Path(args.experiments_dir))
    print(f"  Found {len(predictions)} T1 predictions across {len(set(p['experiment'] for p in predictions))} experiments")

    if not predictions:
        print("No predictions found. Exiting.")
        sys.exit(1)

    # Step 2: Reconstruct
    if not args.skip_reconstruct:
        predictions = batch_reconstruct(predictions, output_dir, skip_existing=True)
    else:
        # Set reconstructed paths without rebuilding
        recon_dir = output_dir / "reconstructed"
        for pred_info in predictions:
            out_name = f"absolute_{pred_info['experiment']}__{pred_info['eval_name']}.npz"
            pred_info["reconstructed_path"] = str(recon_dir / out_name)

    # Step 3: Validate SWOT models
    swot_df = batch_validate(predictions, output_dir)

    # Step 4: Validate global products for comparison
    global_df = validate_global_products(output_dir)

    # Step 5: Generate report
    if not swot_df.empty or not global_df.empty:
        generate_report(swot_df, global_df, output_dir)
    else:
        print("\nNo validation results to report.")

    elapsed = time.time() - start_time
    print(f"\nTotal time: {elapsed:.1f}s ({elapsed/60:.1f} min)")


if __name__ == "__main__":
    main()
