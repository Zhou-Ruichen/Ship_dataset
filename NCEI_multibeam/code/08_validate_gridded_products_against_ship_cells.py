#!/usr/bin/env python3
"""08_validate_gridded_products_against_ship_cells.py

Validate gridded bathymetry products against ship validation cells.

READ-ONLY: does not modify ship data or gridded products.

Input:
  - derived/validation_cells_1min/primary_ship_validation_cells_1min.parquet
  - derived/validation_cells_1min/sensitivity_original_ship_cells_1min.parquet
  - configs/gridded_products_validation.yaml

Output:
  - derived/model_validation_1min/validation_by_cell_<product>.parquet
  - derived/model_validation_1min/validation_sample_diagnostics_<product>.parquet
  - derived/model_validation_1min/validation_metrics_summary.parquet + .tsv
  - derived/model_validation_1min/validation_metrics_by_quality_tier.parquet + .tsv
  - derived/model_validation_1min/validation_metrics_by_depth_bin.parquet + .tsv
  - derived/model_validation_1min/validation_metrics_by_region_10deg.parquet + .tsv
  - derived/model_validation_1min/model_validation_report.md
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import yaml

PROJECT = Path(__file__).resolve().parent.parent

INPUTS = {
    "primary_cells": PROJECT / "derived" / "validation_cells_1min" / "primary_ship_validation_cells_1min.parquet",
    "sensitivity_cells": PROJECT / "derived" / "validation_cells_1min" / "sensitivity_original_ship_cells_1min.parquet",
}

DEFAULT_CONFIG = PROJECT / "configs" / "gridded_products_validation.yaml"

OUTPUT_DIR = PROJECT / "derived" / "model_validation_1min"

LOG_PATH = PROJECT / "output" / "logs" / "08_validate_gridded_products.log"

DEPTH_BINS = [
    (0, 1000, "0-1000m"),
    (1000, 3000, "1000-3000m"),
    (3000, 5000, "3000-5000m"),
    (5000, 7000, "5000-7000m"),
    (7000, 99999, ">7000m"),
]

CELL_SIZE_DEG = 1.0 / 60.0  # 1 arc-minute


# ---------------------------------------------------------------------------
# Atomic write helpers
# ---------------------------------------------------------------------------

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


def atomic_write_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Sampling functions (intentionally preserved)
# ---------------------------------------------------------------------------

def open_product(prod_cfg):
    """Open a gridded product and return an xarray-like Dataset."""
    ppath = Path(prod_cfg["path"])
    fmt = prod_cfg.get("format", "netcdf").lower()

    if fmt == "netcdf":
        return xr.open_dataset(ppath)
    elif fmt == "geotiff" or fmt == "tiff":
        import rasterio  # type: ignore[import-not-found]

        ds_raster = rasterio.open(ppath)
        band1 = ds_raster.read(1)
        transform = ds_raster.transform
        nrows, ncols = band1.shape
        lons = np.array([transform.c + (j + 0.5) * transform.a for j in range(ncols)])
        lats = np.array([transform.f + (i + 0.5) * transform.e for i in range(nrows)])
        ds = xr.Dataset(
            {prod_cfg["z_name"]: (["lat", "lon"], band1)},
            coords={"lat": lats, "lon": lons}
        )
        ds_raster.close()
        return ds
    elif fmt == "npz":
        data = np.load(ppath)
        z_data = data[prod_cfg["z_name"]]
        lon_data = data[prod_cfg["lon_name"]]
        lat_data = data[prod_cfg["lat_name"]]
        lon_name = prod_cfg["lon_name"]
        lat_name = prod_cfg["lat_name"]
        ds = xr.Dataset(
            {prod_cfg["z_name"]: ([lat_name, lon_name], z_data)},
            coords={lat_name: lat_data, lon_name: lon_data}
        )
        return ds
    elif fmt == "grd":
        try:
            from scipy.io import netcdf_file

            nc = netcdf_file(ppath, 'r')
            z_name = prod_cfg["z_name"]
            lon_name = prod_cfg["lon_name"]
            lat_name = prod_cfg["lat_name"]
            z_data = np.array(nc.variables[z_name])
            lon_data = np.array(nc.variables[lon_name])
            lat_data = np.array(nc.variables[lat_name])
            ds = xr.Dataset(
                {z_name: (["lat", "lon"], z_data)},
                coords={"lat": lat_data, "lon": lon_data}
            )
            nc.close()
            return ds
        except Exception:
            return xr.open_dataset(ppath)
    else:
        return xr.open_dataset(ppath)


def sample_center_bilinear(ds, product_cfg, cells_df):
    """Bilinear interpolation at cell centers using fast numpy."""
    from scipy.interpolate import RegularGridInterpolator

    z_name = product_cfg["z_name"]

    lons = cells_df["lon_center"].values.astype(np.float64)
    lats = cells_df["lat_center"].values.astype(np.float64)

    if product_cfg.get("lon_convention", "-180_180") == "0_360":
        lons = lons % 360.0

    lat_vals = ds[product_cfg["lat_name"]].values.astype(np.float64)
    lon_vals = ds[product_cfg["lon_name"]].values.astype(np.float64)

    # Extract a bounding box to avoid loading the full global grid
    margin = 0.5  # degrees
    lat_mask = (lat_vals >= lats.min() - margin) & (lat_vals <= lats.max() + margin)
    lon_mask = (lon_vals >= lons.min() - margin) & (lon_vals <= lons.max() + margin)
    lat_sub = lat_vals[lat_mask]
    lon_sub = lon_vals[lon_mask]

    if len(lat_sub) == 0 or len(lon_sub) == 0:
        return np.full(len(cells_df), np.nan, dtype=np.float64)

    da = ds[z_name]
    lat_start = int(np.searchsorted(lat_vals, lat_sub[0]))
    lat_end = int(np.searchsorted(lat_vals, lat_sub[-1])) + 1
    lon_start = int(np.searchsorted(lon_vals, lon_sub[0])) if lon_vals[0] < lon_vals[-1] else int(np.searchsorted(-lon_vals, -lon_sub[0]))
    lon_end = lon_start + len(lon_sub)

    z_sub = da[lat_start:lat_end, lon_start:lon_end].values.astype(np.float64)

    interp = RegularGridInterpolator(
        (lat_sub, lon_sub), z_sub,
        method="linear", bounds_error=False, fill_value=np.nan
    )
    values = interp(np.column_stack([lats, lons]))
    return values


def _nearest_indices_1d(sorted_vals, queries):
    """Find nearest index for each query in a sorted 1D array."""
    idx = np.searchsorted(sorted_vals, queries)
    idx = np.clip(idx, 1, len(sorted_vals) - 1)
    left = idx - 1
    d_left = np.abs(queries - sorted_vals[left])
    d_right = np.abs(queries - sorted_vals[idx])
    nearest = np.where(d_left <= d_right, left, idx)
    return nearest.astype(int)


def sample_center_nearest(ds, product_cfg, cells_df):
    """Nearest-neighbor at cell centers.

    For -180/180 lon products: fast numpy searchsorted + banded I/O.
    For 0-360 lon products: xarray .sel (handles wraparound correctly).
    """
    lon_name = product_cfg["lon_name"]
    lat_name = product_cfg["lat_name"]
    z_name = product_cfg["z_name"]
    is_0_360 = product_cfg.get("lon_convention", "-180_180") == "0_360"

    lons = cells_df["lon_center"].values.astype(np.float64)
    lats = cells_df["lat_center"].values.astype(np.float64)

    if is_0_360:
        lons = lons % 360.0

    # For 0-360 products, use xarray sel which handles the coordinate system
    if is_0_360:
        da = ds[z_name]
        n = len(cells_df)
        results = np.full(n, np.nan, dtype=np.float64)
        batch_size = 500
        for start in range(0, n, batch_size):
            end = min(start + batch_size, n)
            values = da.sel(
                {lat_name: xr.DataArray(lats[start:end], dims="points"),
                 lon_name: xr.DataArray(lons[start:end], dims="points")},
                method="nearest"
            ).values.astype(np.float64)
            results[start:end] = values
        return results

    # For -180/180 products: fast numpy approach
    lat_vals = ds[lat_name].values.astype(np.float64)
    lon_vals = ds[lon_name].values.astype(np.float64)
    da = ds[z_name]

    lat_idx = _nearest_indices_1d(lat_vals, lats)
    lon_idx = _nearest_indices_1d(lon_vals, lons)

    n = len(cells_df)
    results = np.full(n, np.nan, dtype=np.float64)

    unique_lat_idx = np.unique(lat_idx)
    band_size = 500
    for band_start in range(0, len(unique_lat_idx), band_size):
        band_end = min(band_start + band_size, len(unique_lat_idx))
        band_lats = unique_lat_idx[band_start:band_end]
        mask = np.isin(lat_idx, band_lats)

        lat_lo = int(band_lats[0])
        lat_hi = int(band_lats[-1]) + 2
        lon_lo = int(lon_idx[mask].min())
        lon_hi = int(lon_idx[mask].max()) + 2

        chunk = da[lat_lo:lat_hi, lon_lo:lon_hi].values
        local_lat = lat_idx[mask] - lat_lo
        local_lon = lon_idx[mask] - lon_lo

        results[mask] = chunk[local_lat, local_lon].astype(np.float64)

    return results


def sample_cell_aggregate(ds, product_cfg, cells_df, agg="median"):
    """Aggregate all product pixels within each 1min cell.

    Strategy: use nearest-neighbor lookup to find grid indices,
    then extract a small local window around each cell center
    and aggregate. Falls back to nearest-neighbor for very large
    grids (>500M pixels) to avoid memory issues.
    """
    lon_name = product_cfg["lon_name"]
    lat_name = product_cfg["lat_name"]
    z_name = product_cfg["z_name"]

    lons = cells_df["lon_center"].values.astype(np.float64)
    lats = cells_df["lat_center"].values.astype(np.float64)
    n = len(cells_df)

    da = ds[z_name]
    shape = da.shape

    # For very large grids, nearest-neighbor is sufficient and avoids OOM
    total_pixels = shape[0] * shape[1]
    if total_pixels > 500_000_000:
        return sample_center_nearest(ds, product_cfg, cells_df), "center_nearest"

    lat_vals = ds[lat_name].values.astype(np.float64)
    lon_vals = ds[lon_name].values.astype(np.float64)

    dlat = float(np.median(np.diff(lat_vals)))
    dlon = float(np.median(np.diff(lon_vals)))
    n_pix_lat = max(1, int(round(CELL_SIZE_DEG / abs(dlat))))
    n_pix_lon = max(1, int(round(CELL_SIZE_DEG / abs(dlon))))
    total_pix = n_pix_lat * n_pix_lon

    if total_pix <= 1:
        return sample_center_nearest(ds, product_cfg, cells_df), "center_nearest"

    half_lat_idx = n_pix_lat // 2
    half_lon_idx = n_pix_lon // 2

    # Load full grid into memory (filtered above for reasonable size)
    all_data = da.values

    # Find nearest index for each cell center
    lat_indices = np.searchsorted(lat_vals, lats)
    lat_indices = np.clip(lat_indices, 0, len(lat_vals) - 1)

    query_lons = lons.copy()
    if product_cfg.get("lon_convention", "-180_180") == "0_360":
        query_lons = query_lons % 360.0

    if lon_vals[0] < lon_vals[-1]:
        lon_indices = np.searchsorted(lon_vals, query_lons)
    else:
        lon_indices = np.searchsorted(-lon_vals, -query_lons)
    lon_indices = np.clip(lon_indices, 0, len(lon_vals) - 1)

    results = np.full(n, np.nan, dtype=np.float64)
    agg_func = np.median if agg == "median" else np.mean

    for i in range(n):
        li = lat_indices[i]
        lo = lon_indices[i]
        lat_lo = max(0, li - half_lat_idx)
        lat_hi = min(shape[0], li + half_lat_idx + 1)
        lon_lo = max(0, lo - half_lon_idx)
        lon_hi = min(shape[1], lo + half_lon_idx + 1)
        window = all_data[lat_lo:lat_hi, lon_lo:lon_hi].ravel()
        valid = window[~np.isnan(window)]
        if len(valid) > 0:
            results[i] = float(agg_func(valid))

    del all_data
    return results, f"cell_{agg}"


def sample_product(ds, product_cfg, cells_df):
    """Route to the correct sampling method."""
    method = product_cfg.get("sampling_method", "center_bilinear")

    if method == "cell_median":
        return sample_cell_aggregate(ds, product_cfg, cells_df, agg="median")
    elif method == "cell_mean":
        return sample_cell_aggregate(ds, product_cfg, cells_df, agg="mean")
    elif method == "center_bilinear":
        return sample_center_bilinear(ds, product_cfg, cells_df), method
    elif method == "center_nearest":
        return sample_center_nearest(ds, product_cfg, cells_df), method
    else:
        raise ValueError(f"Unknown sampling_method: {method}")


# ---------------------------------------------------------------------------
# Diagnostics and metrics computation
# ---------------------------------------------------------------------------

def get_fill_value(ds, prod_cfg):
    da = ds[prod_cfg["z_name"]]
    for key in ("_FillValue", "missing_value"):
        if key in da.attrs:
            try:
                return float(da.attrs[key])
            except (TypeError, ValueError):
                return da.attrs[key]
        if key in da.encoding:
            try:
                return float(da.encoding[key])
            except (TypeError, ValueError):
                return da.encoding[key]
    return np.nan


def apply_z_convention(raw_values: np.ndarray, prod_cfg: dict) -> tuple[np.ndarray, np.ndarray]:
    z_conv = prod_cfg.get("z_convention", "elevation_negative_ocean")
    if z_conv == "depth_positive_down":
        model_elev_m = -raw_values
    else:
        model_elev_m = raw_values.copy()
    return model_elev_m, -model_elev_m


def _safe_min(values: np.ndarray) -> float:
    valid = values[np.isfinite(values)]
    return float(np.min(valid)) if len(valid) else np.nan


def _safe_max(values: np.ndarray) -> float:
    valid = values[np.isfinite(values)]
    return float(np.max(valid)) if len(valid) else np.nan


def diagnose_product_convention(raw_values, model_elev_m, model_depth_m, ship_elev_m, prod_cfg):
    """Return per-product convention diagnostics for sampled values."""
    raw = np.asarray(raw_values, dtype=np.float64)
    elev = np.asarray(model_elev_m, dtype=np.float64)
    depth = np.asarray(model_depth_m, dtype=np.float64)
    ship = np.asarray(ship_elev_m, dtype=np.float64)
    fill_value = prod_cfg.get("_runtime_fill_value", np.nan)

    fill_mask = np.zeros(len(raw), dtype=bool)
    if pd.notna(fill_value):
        try:
            fill_mask = np.isclose(raw, float(fill_value), equal_nan=False)
        except (TypeError, ValueError):
            fill_mask = raw == fill_value
    nodata_mask = np.isnan(raw) | fill_mask
    valid_mask = np.isfinite(elev) & np.isfinite(ship) & ~nodata_mask

    corr = np.nan
    if int(valid_mask.sum()) >= 2:
        corr = float(np.corrcoef(elev[valid_mask], ship[valid_mask])[0, 1])

    return {
        "z_convention": prod_cfg.get("z_convention", "elevation_negative_ocean"),
        "raw_z_min": _safe_min(raw),
        "raw_z_max": _safe_max(raw),
        "converted_model_elev_min": _safe_min(elev),
        "converted_model_elev_max": _safe_max(elev),
        "model_depth_min": _safe_min(depth),
        "model_depth_max": _safe_max(depth),
        "fill_value": fill_value,
        "nodata_count": int(nodata_mask.sum()),
        "valid_count": int(valid_mask.sum()),
        "lon_convention": prod_cfg.get("lon_convention", "-180_180"),
        "lon_0_360_conversion_applied": bool(prod_cfg.get("lon_convention", "-180_180") == "0_360"),
        "elevation_correlation": corr,
        "sign_error_suspected": bool(pd.notna(corr) and corr < 0),
    }


def compute_metrics(errors: np.ndarray, requested_ship_cells: int, total_primary_cells: int) -> dict:
    """Compute validation metrics from an array of errors."""
    valid = errors[~np.isnan(errors)]
    n = len(valid)
    base: dict[str, object] = {
        "requested_ship_cells": int(requested_ship_cells),
        "total_primary_cells_in_dataset": int(total_primary_cells),
    }
    if n == 0:
        base.update({
            "count": 0, "coverage_count": 0,
            "coverage_fraction": 0.0,
            "global_fraction": 0.0,
            "bias_mean": np.nan, "bias_median": np.nan,
            "MAE": np.nan, "RMSE": np.nan,
            "STD": np.nan, "MAD": np.nan,
            "p05": np.nan, "p25": np.nan,
            "p75": np.nan, "p95": np.nan,
            "abs_error_p95": np.nan,
        })
        return base

    abs_err = np.abs(valid)
    med = float(np.median(valid))
    base.update({
        "count": n,
        "coverage_count": n,
        "coverage_fraction": n / requested_ship_cells if requested_ship_cells > 0 else 0.0,
        "global_fraction": n / total_primary_cells if total_primary_cells > 0 else 0.0,
        "bias_mean": float(np.mean(valid)),
        "bias_median": med,
        "MAE": float(np.mean(abs_err)),
        "RMSE": float(np.sqrt(np.mean(valid ** 2))),
        "STD": float(np.std(valid, ddof=1)) if n > 1 else 0.0,
        "MAD": float(np.median(np.abs(valid - med))),
        "p05": float(np.percentile(valid, 5)),
        "p25": float(np.percentile(valid, 25)),
        "p75": float(np.percentile(valid, 75)),
        "p95": float(np.percentile(valid, 95)),
        "abs_error_p95": float(np.percentile(abs_err, 95)),
    })
    return base


def assign_depth_bin(depth_m):
    for lo, hi, label in DEPTH_BINS:
        if lo <= depth_m < hi:
            return label
    return ">7000m"


def assign_region_10deg(lon, lat):
    return f"lon{int(np.floor(lon / 10) * 10):04d}_lat{int(np.floor(lat / 10) * 10):04d}"


def assign_overlap_class(n_fc):
    if n_fc >= 10:
        return "10+"
    elif n_fc >= 5:
        return "5-9"
    elif n_fc >= 2:
        return "2-4"
    else:
        return "1"


def assign_file_cell_class(n_fc):
    if n_fc >= 10:
        return "10+"
    elif n_fc >= 5:
        return "5+"
    elif n_fc >= 2:
        return "2+"
    else:
        return "1"


def assign_cruise_class(n_cruise):
    if n_cruise >= 5:
        return "5+"
    elif n_cruise >= 2:
        return "2+"
    else:
        return "1"


# ---------------------------------------------------------------------------
# Main flow helpers
# ---------------------------------------------------------------------------

def load_validation_sets(validation_set: str) -> tuple[dict[str, pd.DataFrame], int]:
    log = logging.getLogger("08")
    cell_sets = {}

    log.info("Loading primary validation cells ...")
    primary = pd.read_parquet(INPUTS["primary_cells"])
    primary["cell_source"] = "primary"
    primary["validation_set"] = "primary"
    total_primary = len(primary)
    log.info(f"  {total_primary:,} primary cells")
    if validation_set in ("primary", "both"):
        cell_sets["primary"] = primary

    if validation_set in ("sensitivity", "both"):
        sens_path = INPUTS["sensitivity_cells"]
        if not sens_path.exists():
            log.error(f"Sensitivity cells not found: {sens_path}")
            sys.exit(1)
        log.info("Loading sensitivity original validation cells ...")
        sensitivity = pd.read_parquet(sens_path)
        sensitivity["cell_source"] = "sensitivity_original"
        sensitivity["validation_set"] = "sensitivity"
        cell_sets["sensitivity"] = sensitivity
        log.info(f"  {len(sensitivity):,} sensitivity cells")

    return cell_sets, total_primary


def footprint_from_product(product: dict) -> dict | None:
    footprint = product.get("footprint")
    if not footprint:
        return None
    required = {"lon_min", "lon_max", "lat_min", "lat_max"}
    missing = required - set(footprint)
    if missing:
        raise ValueError(f"Product {product['name']} footprint missing keys: {sorted(missing)}")
    return footprint


def filter_to_footprint(cells: pd.DataFrame, footprint: dict | None) -> pd.DataFrame:
    if not footprint:
        return cells.copy()
    mask = (
        (cells["lon_center"] >= float(footprint["lon_min"]))
        & (cells["lon_center"] <= float(footprint["lon_max"]))
        & (cells["lat_center"] >= float(footprint["lat_min"]))
        & (cells["lat_center"] <= float(footprint["lat_max"]))
    )
    return cells.loc[mask].copy()


def sample_cells(cells: pd.DataFrame, sample_n_cells: int | None, seed_key: str) -> pd.DataFrame:
    if sample_n_cells and sample_n_cells < len(cells):
        seed = (abs(hash(seed_key)) % (2**32 - 1)) or 42
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(cells), size=sample_n_cells, replace=False)
        return cells.iloc[idx].copy()
    return cells.copy()


def build_cell_result(cells, prod, raw_values, model_elev_m, model_depth_m, effective_method,
                      region_subset_name, comparison_footprint, n_cells_in_footprint,
                      n_cells_requested, total_primary_cells):
    ship_elev_m = cells["ship_elev_m"].to_numpy(dtype=np.float64)
    ship_depth_m = cells["ship_depth_m"].to_numpy(dtype=np.float64)
    elev_error = model_elev_m - ship_elev_m
    depth_error = model_depth_m - ship_depth_m
    keep_cols = [
        "cell_id", "lon_center", "lat_center", "ship_depth_m", "ship_elev_m",
        "quality_tier", "validation_weight", "n_file_cells", "n_cruises_guess",
        "dominant_track_kind", "cell_source", "validation_set",
    ]
    available_cols = [c for c in keep_cols if c in cells.columns]
    cell_result = cells[available_cols].copy()
    cell_result["product_name"] = prod["name"]
    cell_result["raw_z"] = raw_values
    cell_result["model_elev_m"] = model_elev_m
    cell_result["model_depth_m"] = model_depth_m
    cell_result["elev_error_m"] = elev_error
    cell_result["depth_error_m"] = depth_error
    cell_result["abs_elev_error_m"] = np.abs(elev_error)
    cell_result["sampling_method"] = effective_method
    cell_result["config_sampling_method"] = prod.get("sampling_method", "center_bilinear")
    cell_result["z_convention"] = prod.get("z_convention", "elevation_negative_ocean")
    cell_result["lon_convention"] = prod.get("lon_convention", "-180_180")
    cell_result["lon_0_360_conversion_applied"] = bool(prod.get("lon_convention", "-180_180") == "0_360")
    cell_result["region_subset_name"] = region_subset_name
    cell_result["comparison_footprint"] = comparison_footprint or ""
    cell_result["n_cells_in_footprint"] = int(n_cells_in_footprint)
    cell_result["n_cells_requested"] = int(n_cells_requested)
    cell_result["requested_ship_cells"] = int(n_cells_requested)
    cell_result["total_primary_cells_in_dataset"] = int(total_primary_cells)
    return cell_result


def classify_sdust_issue(diag: dict, sampled_df: pd.DataFrame) -> str:
    if diag.get("sign_error_suspected"):
        return "sign error"
    raw_series = sampled_df["raw_z"] if "raw_z" in sampled_df.columns else pd.Series(dtype=float)
    raw = raw_series.to_numpy(dtype=np.float64)
    if int(np.sum(np.isfinite(raw) & (np.abs(raw) > 50000))) > 0 or diag.get("nodata_count", 0) > 0:
        return "nodata contamination"
    if diag.get("valid_count", 0) < max(10, 0.5 * len(sampled_df)):
        return "coverage gap"
    if diag.get("lon_0_360_conversion_applied") and diag.get("valid_count", 0) == 0:
        return "longitude misalignment"
    return "not obvious; inspect largest-error cells"


def make_diagnostic_rows(prod, validation_set, sampling_method, raw_values, model_elev_m,
                         model_depth_m, cells, fill_value, region_subset_name,
                         comparison_footprint, sdust_detail=False):
    prod_diag_cfg = dict(prod)
    prod_diag_cfg["_runtime_fill_value"] = fill_value
    diag = diagnose_product_convention(
        raw_values, model_elev_m, model_depth_m,
        cells["ship_elev_m"].to_numpy(dtype=np.float64), prod_diag_cfg
    )
    diag.update({
        "product_name": prod["name"],
        "validation_set": validation_set,
        "sampling_method": sampling_method,
        "region_subset_name": region_subset_name,
        "comparison_footprint": comparison_footprint or "",
        "n_cells_requested": int(len(cells)),
        "suspicious_extreme_count_abs_z_gt_50000": int(np.sum(np.isfinite(raw_values) & (np.abs(raw_values) > 50000))),
        "diagnostic_kind": "summary",
    })
    rows = [diag]
    if sdust_detail:
        tmp = cells[["cell_id", "lon_center", "lat_center", "ship_elev_m"]].copy()
        tmp["model_elev_m"] = model_elev_m
        tmp["elev_error_m"] = model_elev_m - cells["ship_elev_m"].to_numpy(dtype=np.float64)
        tmp["raw_z"] = raw_values
        tmp["abs_error"] = np.abs(tmp["elev_error_m"])
        likely = classify_sdust_issue(diag, tmp)
        for _, row in tmp.sort_values("abs_error", ascending=False).head(20).iterrows():
            detail = {
                "product_name": prod["name"],
                "validation_set": validation_set,
                "sampling_method": sampling_method,
                "region_subset_name": region_subset_name,
                "comparison_footprint": comparison_footprint or "",
                "diagnostic_kind": "largest_abs_error_cell",
                "likely_issue": likely,
                "cell_id": row["cell_id"],
                "lon": float(row["lon_center"]),
                "lat": float(row["lat_center"]),
                "ship_elev": float(row["ship_elev_m"]),
                "model_elev": float(row["model_elev_m"]),
                "error": float(row["elev_error_m"]),
                "raw_z": float(row["raw_z"]) if pd.notna(row["raw_z"]) else np.nan,
                "fill_value": fill_value,
                "suspicious_extreme_count_abs_z_gt_50000": diag["suspicious_extreme_count_abs_z_gt_50000"],
            }
            detail.update({k: np.nan for k in diag if k not in detail})
            rows.append(detail)
        rows[0]["likely_issue"] = likely
    return rows


def run(args):
    log = logging.getLogger("08")

    config_path = Path(args.config)
    if not config_path.exists():
        log.error(f"Config not found: {config_path}")
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    products = config.get("products", [])
    if args.product_name:
        products = [p for p in products if p["name"] == args.product_name]
    products = [p for p in products if p.get("enabled", True)]

    comparison_footprint = None
    comparison_footprint_name = ""
    if args.comparison_footprint:
        matches = [p for p in products if p["name"] == args.comparison_footprint]
        if not matches:
            log.error(f"--comparison-footprint product not enabled/found: {args.comparison_footprint}")
            sys.exit(1)
        comparison_footprint = footprint_from_product(matches[0])
        if not comparison_footprint:
            log.error(f"--comparison-footprint product has no footprint: {args.comparison_footprint}")
            sys.exit(1)
        comparison_footprint_name = str(comparison_footprint.get("name", args.comparison_footprint))
        log.info(f"Using comparison footprint from {args.comparison_footprint}: {comparison_footprint}")

    log.info(f"  {len(products)} enabled products")
    cell_sets, total_primary_cells = load_validation_sets(args.validation_set)

    all_cell_results = []
    all_diagnostics = []
    product_status = []

    for prod in products:
        pname = prod["name"]
        ppath = Path(prod["path"])
        log.info(f"Processing {pname} ...")

        if not ppath.exists():
            log.warning(f"  SKIP (not found): {ppath}")
            product_status.append({"name": pname, "status": "skipped", "reason": f"file not found: {ppath}"})
            continue

        try:
            product_footprint = footprint_from_product(prod)
        except ValueError as e:
            log.error(str(e))
            product_status.append({"name": pname, "status": "error", "reason": str(e)})
            continue

        effective_footprint = comparison_footprint if comparison_footprint else product_footprint
        region_subset_name = "global"
        if effective_footprint:
            region_subset_name = str(effective_footprint.get("name", pname if product_footprint else comparison_footprint_name))

        try:
            ds = open_product(prod)
            fill_value = get_fill_value(ds, prod)
        except Exception as e:
            log.error(f"  ERROR opening {ppath}: {e}")
            product_status.append({"name": pname, "status": "error", "reason": str(e)})
            continue

        log.info(f"  Opened {ppath} ({os.path.getsize(ppath)/1e9:.1f} GB)")
        product_ok = True
        product_valid = 0

        for validation_set, base_cells in cell_sets.items():
            footprint_cells = filter_to_footprint(base_cells, effective_footprint)
            n_cells_in_footprint = len(footprint_cells)
            if n_cells_in_footprint == 0:
                log.warning(f"  {pname}/{validation_set}: no cells inside footprint; skipping")
                continue
            cells = sample_cells(footprint_cells, args.sample_n_cells, f"{pname}:{validation_set}:{region_subset_name}")
            n_cells_requested = len(cells)
            log.info(f"  {pname}/{validation_set}: requested {n_cells_requested:,} cells ({n_cells_in_footprint:,} in footprint)")

            try:
                raw_values, effective_method = sample_product(ds, prod, cells)
                raw_values = np.asarray(raw_values, dtype=np.float64)
            except Exception as e:
                log.error(f"  ERROR sampling {pname}/{validation_set}: {e}")
                product_status.append({"name": pname, "status": "error", "reason": f"sampling {validation_set}: {e}"})
                product_ok = False
                break

            model_elev_m, model_depth_m = apply_z_convention(raw_values, prod)
            product_valid += int(np.sum(~np.isnan(model_elev_m)))

            all_cell_results.append(build_cell_result(
                cells, prod, raw_values, model_elev_m, model_depth_m, effective_method,
                region_subset_name, comparison_footprint_name, n_cells_in_footprint,
                n_cells_requested, total_primary_cells,
            ))
            all_diagnostics.extend(make_diagnostic_rows(
                prod, validation_set, effective_method, raw_values, model_elev_m, model_depth_m,
                cells, fill_value, region_subset_name, comparison_footprint_name,
                sdust_detail=(pname == "SDUST_2023"),
            ))

            config_method = prod.get("sampling_method", "center_bilinear")
            if config_method in ("cell_median", "cell_mean"):
                try:
                    sens_values = np.asarray(sample_center_bilinear(ds, prod, cells), dtype=np.float64)
                except Exception as e:
                    log.error(f"  ERROR sensitivity sampling {pname}/{validation_set}: {e}")
                    product_status.append({"name": pname, "status": "error", "reason": f"sensitivity sampling {validation_set}: {e}"})
                    product_ok = False
                    break
                sens_elev, sens_depth = apply_z_convention(sens_values, prod)
                all_cell_results.append(build_cell_result(
                    cells, prod, sens_values, sens_elev, sens_depth, "center_bilinear_sensitivity",
                    region_subset_name, comparison_footprint_name, n_cells_in_footprint,
                    n_cells_requested, total_primary_cells,
                ))
                all_diagnostics.extend(make_diagnostic_rows(
                    prod, validation_set, "center_bilinear_sensitivity", sens_values, sens_elev, sens_depth,
                    cells, fill_value, region_subset_name, comparison_footprint_name,
                    sdust_detail=(pname == "SDUST_2023"),
                ))

        ds.close()
        if product_ok:
            product_status.append({"name": pname, "status": "ok", "reason": "", "n_sampled": product_valid})

    if not all_cell_results:
        log.error("No products successfully processed — aborting")
        return None

    return {
        "cells_df": pd.concat(all_cell_results, ignore_index=True),
        "diagnostics_df": pd.DataFrame(all_diagnostics),
        "product_status": product_status,
        "products": products,
        "total_primary_cells": total_primary_cells,
    }


# ---------------------------------------------------------------------------
# Metrics aggregation
# ---------------------------------------------------------------------------

def _group_keys() -> list[str]:
    return ["product_name", "validation_set", "sampling_method"]


def _group_denominators(sub: pd.DataFrame) -> tuple[int, int]:
    requested = int(sub["requested_ship_cells"].iloc[0]) if "requested_ship_cells" in sub.columns and len(sub) else len(sub)
    total_primary = int(sub["total_primary_cells_in_dataset"].iloc[0]) if "total_primary_cells_in_dataset" in sub.columns and len(sub) else 0
    return requested, total_primary


def _metric_row(sub: pd.DataFrame, extras: dict) -> dict:
    requested, total_primary = _group_denominators(sub)
    m = compute_metrics(sub["elev_error_m"].to_numpy(dtype=np.float64), requested, total_primary)
    for key in ["region_subset_name", "comparison_footprint", "n_cells_in_footprint", "n_cells_requested"]:
        if key in sub.columns and len(sub):
            m[key] = sub[key].iloc[0]
    m.update(extras)
    return m


def build_all_metrics(cells_df):
    """Build all metric tables, grouped by product + validation_set + sampling_method."""
    work = cells_df.copy()
    rows = []

    for keys, sub in work.groupby(_group_keys(), dropna=False):
        pname, validation_set, sampling_method = keys
        rows.append(_metric_row(sub, {
            "product_name": pname,
            "validation_set": validation_set,
            "sampling_method": sampling_method,
            "stratification": "overall",
            "stratum": "all",
        }))
    summary_rows = rows

    tier_rows = []
    for keys, prod_df in work.groupby(_group_keys(), dropna=False):
        pname, validation_set, sampling_method = keys
        for tier in ["A_tier", "B_tier", "C_tier"]:
            sub = prod_df[prod_df["quality_tier"] == tier]
            tier_rows.append(_metric_row(sub, {
                "product_name": pname, "validation_set": validation_set,
                "sampling_method": sampling_method, "quality_tier": tier,
            }))

    work["depth_bin"] = work["ship_depth_m"].apply(assign_depth_bin)
    depth_rows = []
    for keys, prod_df in work.groupby(_group_keys(), dropna=False):
        pname, validation_set, sampling_method = keys
        for _, _, label in DEPTH_BINS:
            sub = prod_df[prod_df["depth_bin"] == label]
            depth_rows.append(_metric_row(sub, {
                "product_name": pname, "validation_set": validation_set,
                "sampling_method": sampling_method, "depth_bin": label,
            }))

    work["overlap_class"] = work["n_file_cells"].apply(assign_overlap_class)
    overlap_rows = []
    for keys, prod_df in work.groupby(_group_keys(), dropna=False):
        pname, validation_set, sampling_method = keys
        for cls in ["1", "2-4", "5-9", "10+"]:
            sub = prod_df[prod_df["overlap_class"] == cls]
            overlap_rows.append(_metric_row(sub, {
                "product_name": pname, "validation_set": validation_set,
                "sampling_method": sampling_method, "overlap_class": cls,
            }))

    work["n_file_cells_class"] = work["n_file_cells"].apply(assign_file_cell_class)
    fc_rows = []
    for keys, prod_df in work.groupby(_group_keys(), dropna=False):
        pname, validation_set, sampling_method = keys
        for cls in ["1", "2+", "5+", "10+"]:
            sub = prod_df[prod_df["n_file_cells_class"] == cls]
            fc_rows.append(_metric_row(sub, {
                "product_name": pname, "validation_set": validation_set,
                "sampling_method": sampling_method, "n_file_cells_class": cls,
            }))

    work["cruise_class"] = work["n_cruises_guess"].apply(assign_cruise_class)
    cruise_rows = []
    for keys, prod_df in work.groupby(_group_keys(), dropna=False):
        pname, validation_set, sampling_method = keys
        for cls in ["1", "2+", "5+"]:
            sub = prod_df[prod_df["cruise_class"] == cls]
            cruise_rows.append(_metric_row(sub, {
                "product_name": pname, "validation_set": validation_set,
                "sampling_method": sampling_method, "n_cruises_guess_class": cls,
            }))

    track_rows = []
    for keys, prod_df in work.groupby(_group_keys(), dropna=False):
        pname, validation_set, sampling_method = keys
        for track in sorted(prod_df["dominant_track_kind"].dropna().unique()):
            sub = prod_df[prod_df["dominant_track_kind"] == track]
            if len(sub) < 10:
                continue
            track_rows.append(_metric_row(sub, {
                "product_name": pname, "validation_set": validation_set,
                "sampling_method": sampling_method, "dominant_track_kind": track,
            }))

    work["region_10deg"] = work.apply(lambda r: assign_region_10deg(r["lon_center"], r["lat_center"]), axis=1)
    region_rows = []
    for keys, prod_df in work.groupby(_group_keys(), dropna=False):
        pname, validation_set, sampling_method = keys
        for region in sorted(prod_df["region_10deg"].unique()):
            sub = prod_df[prod_df["region_10deg"] == region]
            if len(sub) < 10:
                continue
            region_rows.append(_metric_row(sub, {
                "product_name": pname, "validation_set": validation_set,
                "sampling_method": sampling_method, "region_10deg": region,
            }))

    return {
        "summary": pd.DataFrame(summary_rows),
        "by_quality_tier": pd.DataFrame(tier_rows),
        "by_depth_bin": pd.DataFrame(depth_rows),
        "by_overlap_class": pd.DataFrame(overlap_rows),
        "by_n_file_cells": pd.DataFrame(fc_rows),
        "by_n_cruises_guess": pd.DataFrame(cruise_rows),
        "by_dominant_track_kind": pd.DataFrame(track_rows),
        "by_region_10deg": pd.DataFrame(region_rows),
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def fmt(v, places=2):
    if pd.isna(v):
        return "N/A"
    if isinstance(v, (float, np.floating)):
        return f"{v:.{places}f}"
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}"
    return str(v)


def generate_report(cells_df, metrics, diagnostics_df, product_status, total_primary_cells, elapsed, is_sample):
    lines = []
    lines.append("# Model Validation Report (1min)")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Elapsed: {elapsed:.1f}s")
    lines.append(f"Validation rows: {len(cells_df):,}")
    if is_sample:
        lines.append("**SAMPLE MODE**: metrics use sampled requested-cell denominators, not global primary total.")
    lines.append("")

    lines.append("## 1. Product status")
    lines.append("")
    lines.append("| Product | Status | Details |")
    lines.append("|---------|--------|---------|")
    for ps in product_status:
        detail = ps.get("reason", "") or f"{ps.get('n_sampled', 0):,} valid samples"
        lines.append(f"| {ps['name']} | {ps['status']} | {detail} |")
    lines.append("")

    lines.append("## 2. Overall validation metrics")
    lines.append("")
    metric_cols = ["count", "bias_mean", "bias_median", "MAE", "RMSE", "STD", "MAD",
                   "p05", "p25", "p75", "p95", "abs_error_p95", "coverage_count",
                   "requested_ship_cells", "coverage_fraction", "global_fraction"]
    head = ["product_name", "validation_set", "sampling_method"] + metric_cols
    lines.append("| " + " | ".join(head) + " |")
    lines.append("| " + " | ".join(["---"] * len(head)) + " |")
    for _, row in metrics["summary"].iterrows():
        lines.append("| " + " | ".join(fmt(row.get(c)) for c in head) + " |")
    lines.append("")

    lines.append("## 3. Metrics by quality tier")
    lines.append("")
    qt = metrics["by_quality_tier"]
    if len(qt) > 0:
        lines.append("| Product | Validation Set | Sampling | Tier | Count | Bias (m) | MAE (m) | RMSE (m) | STD (m) |")
        lines.append("|---------|----------------|----------|------|-------|----------|---------|----------|---------|")
        for _, row in qt.iterrows():
            lines.append(f"| {row['product_name']} | {row['validation_set']} | {row['sampling_method']} | "
                         f"{row['quality_tier']} | {fmt(row['count'])} | {fmt(row['bias_mean'])} | "
                         f"{fmt(row['MAE'])} | {fmt(row['RMSE'])} | {fmt(row['STD'])} |")
    lines.append("")

    lines.append("## 4. Metrics by depth bin")
    lines.append("")
    db = metrics["by_depth_bin"]
    if len(db) > 0:
        lines.append("| Product | Validation Set | Sampling | Depth Bin | Count | Bias (m) | MAE (m) | RMSE (m) |")
        lines.append("|---------|----------------|----------|-----------|-------|----------|---------|----------|")
        for _, row in db.iterrows():
            if row["count"] == 0:
                continue
            lines.append(f"| {row['product_name']} | {row['validation_set']} | {row['sampling_method']} | "
                         f"{row['depth_bin']} | {fmt(row['count'])} | {fmt(row['bias_mean'])} | "
                         f"{fmt(row['MAE'])} | {fmt(row['RMSE'])} |")
    lines.append("")

    lines.append("## 5. Metrics by overlap class")
    lines.append("")
    oc = metrics["by_overlap_class"]
    if len(oc) > 0:
        lines.append("| Product | Validation Set | Sampling | Overlap | Count | Bias (m) | MAE (m) | RMSE (m) |")
        lines.append("|---------|----------------|----------|---------|-------|----------|---------|----------|")
        for _, row in oc.iterrows():
            if row["count"] == 0:
                continue
            lines.append(f"| {row['product_name']} | {row['validation_set']} | {row['sampling_method']} | "
                         f"{row['overlap_class']} | {fmt(row['count'])} | {fmt(row['bias_mean'])} | "
                         f"{fmt(row['MAE'])} | {fmt(row['RMSE'])} |")
    lines.append("")

    lines.append("## 6. Product configuration")
    lines.append("")
    lines.append("| Product | z_convention | lon_convention | config_method | effective_methods | region_subset | comparison_footprint |")
    lines.append("|---------|--------------|----------------|---------------|-------------------|---------------|----------------------|")
    for pname in cells_df["product_name"].unique():
        sub = cells_df[cells_df["product_name"] == pname]
        actual_methods = sorted(sub["sampling_method"].unique())
        config_method = sub["config_sampling_method"].iloc[0]
        z_conv = sub["z_convention"].iloc[0]
        lon_conv = sub["lon_convention"].iloc[0]
        region = sub["region_subset_name"].iloc[0]
        comp = sub["comparison_footprint"].iloc[0]
        lines.append(f"| {pname} | {z_conv} | {lon_conv} | {config_method} | {', '.join(actual_methods)} | {region} | {comp} |")
    lines.append("")
    lines.append("> **Note**: For large global grids (>500M pixels), `cell_median`/`cell_mean` fall back to nearest-neighbor sampling.")
    lines.append("")

    lines.append("## 7. Product convention diagnostics")
    lines.append("")
    diag_summary = diagnostics_df[diagnostics_df.get("diagnostic_kind", "summary") == "summary"] if len(diagnostics_df) else diagnostics_df
    if len(diag_summary) > 0:
        cols = ["product_name", "validation_set", "sampling_method", "z_convention", "raw_z_min", "raw_z_max",
                "converted_model_elev_min", "converted_model_elev_max", "model_depth_min", "model_depth_max",
                "nodata_count", "valid_count", "lon_convention", "lon_0_360_conversion_applied",
                "elevation_correlation", "sign_error_suspected"]
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
        for _, row in diag_summary.iterrows():
            lines.append("| " + " | ".join(fmt(row.get(c), 4 if c == "elevation_correlation" else 2) for c in cols) + " |")
    lines.append("")

    lines.append("## 8. Depth sign sanity check")
    lines.append("")
    for keys, sub in cells_df.groupby(["product_name", "validation_set", "sampling_method"], dropna=False):
        pname, validation_set, sampling_method = keys
        valid = sub.dropna(subset=["model_depth_m", "ship_depth_m"])
        label = f"{pname}/{validation_set}/{sampling_method}"
        if len(valid) < 2:
            lines.append(f"- {label}: N/A (fewer than 2 valid samples)")
            continue
        corr = float(np.corrcoef(valid["model_depth_m"], valid["ship_depth_m"])[0, 1])
        bias = float(valid["depth_error_m"].mean())
        lines.append(f"- {label}: correlation={corr:.4f}, mean_depth_bias={bias:.1f}m")
        if corr < 0:
            lines.append("  ⚠️ **NEGATIVE correlation — possible depth sign inversion!**")
        elif corr > 0.9:
            lines.append("  ✅ Strong positive correlation — depth convention correct")
        else:
            lines.append("  ⚠️ Moderate correlation — check for systematic offsets")
    lines.append("")

    lines.append("## 9. Conclusion")
    lines.append("")
    if is_sample:
        lines.append(f"Sample validation completed. Primary dataset size for reference: {total_primary_cells:,} cells.")
    else:
        lines.append("Full validation completed.")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Validate gridded products against ship cells (08)")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to gridded_products_validation.yaml")
    parser.add_argument("--product-name", default=None, help="Only process this product name")
    parser.add_argument("--sample-n-cells", type=int, default=None, help="Random sample N cells per validation set after footprint filtering")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")
    parser.add_argument("--validation-set", choices=["primary", "sensitivity", "both"], default="primary",
                        help="Validation cells to use: primary, sensitivity, or both")
    parser.add_argument("--use-sensitivity-cells", action="store_true",
                        help="Deprecated alias for --validation-set both")
    parser.add_argument("--comparison-footprint", default=None,
                        help="Filter all products to the footprint of this enabled product")
    args = parser.parse_args()

    if args.use_sensitivity_cells:
        print("WARNING: --use-sensitivity-cells is deprecated; use --validation-set both", file=sys.stderr)
        args.validation_set = "both"

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    log = logging.getLogger("08")

    t0 = time.time()
    log.info("=" * 60)
    log.info("08_validate_gridded_products_against_ship_cells.py  START")
    log.info(f"  --config={args.config}  --product-name={args.product_name}")
    log.info(f"  --sample-n-cells={args.sample_n_cells}  --overwrite={args.overwrite}")
    log.info(f"  --validation-set={args.validation_set}  --comparison-footprint={args.comparison_footprint}")

    if not INPUTS["primary_cells"].exists():
        log.error(f"Input not found: primary_cells = {INPUTS['primary_cells']}")
        sys.exit(1)

    if not args.overwrite:
        output_files = list(OUTPUT_DIR.glob("*.parquet")) + list(OUTPUT_DIR.glob("*.tsv")) + list(OUTPUT_DIR.glob("*.md"))
        if output_files:
            log.error(f"Output dir has files (use --overwrite): {OUTPUT_DIR}")
            sys.exit(1)

    result = run(args)
    if result is None:
        log.error("No results — aborting")
        sys.exit(1)

    cells_df = result["cells_df"]
    diagnostics_df = result["diagnostics_df"]
    product_status = result["product_status"]
    total_primary_cells = result["total_primary_cells"]
    is_sample = args.sample_n_cells is not None
    elapsed = time.time() - t0

    log.info("Computing metrics ...")
    metrics = build_all_metrics(cells_df)

    report_text = generate_report(cells_df, metrics, diagnostics_df, product_status, total_primary_cells, elapsed, is_sample)

    log.info("Writing output files ...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for pname in cells_df["product_name"].unique():
        sub = cells_df[cells_df["product_name"] == pname]
        out_path = OUTPUT_DIR / f"validation_by_cell_{pname}.parquet"
        atomic_write_parquet(sub, out_path)
        log.info(f"  Wrote {out_path.name} ({len(sub):,} rows)")

    for pname in diagnostics_df["product_name"].dropna().unique():
        sub = diagnostics_df[diagnostics_df["product_name"] == pname]
        out_path = OUTPUT_DIR / f"validation_sample_diagnostics_{pname}.parquet"
        atomic_write_parquet(sub, out_path)
        log.info(f"  Wrote {out_path.name} ({len(sub):,} rows)")

    metric_files = {
        "summary": "validation_metrics_summary",
        "by_quality_tier": "validation_metrics_by_quality_tier",
        "by_depth_bin": "validation_metrics_by_depth_bin",
        "by_overlap_class": "validation_metrics_by_overlap_class",
        "by_n_file_cells": "validation_metrics_by_n_file_cells",
        "by_n_cruises_guess": "validation_metrics_by_n_cruises_guess",
        "by_dominant_track_kind": "validation_metrics_by_dominant_track_kind",
        "by_region_10deg": "validation_metrics_by_region_10deg",
    }
    for metric_name, stem in metric_files.items():
        df = metrics[metric_name]
        if len(df) == 0:
            continue
        atomic_write_parquet(df, OUTPUT_DIR / f"{stem}.parquet")
        atomic_write_tsv(df, OUTPUT_DIR / f"{stem}.tsv")
        log.info(f"  Wrote {stem}")

    atomic_write_text(report_text, OUTPUT_DIR / "model_validation_report.md")
    log.info("  Wrote model_validation_report.md")

    log.info("=" * 60)
    log.info(f"Validation rows: {len(cells_df):,}")
    log.info(f"Products: {len([p for p in product_status if p['status'] == 'ok'])} OK, "
             f"{len([p for p in product_status if p['status'] != 'ok'])} skipped/error")
    log.info(f"Elapsed: {elapsed:.1f}s")
    log.info("08_validate_gridded_products_against_ship_cells.py  DONE")

    print(report_text)


if __name__ == "__main__":
    main()
