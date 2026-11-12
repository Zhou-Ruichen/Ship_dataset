"""Pointwise coordinate and depth checks for NCEI bathymetry."""

from __future__ import annotations

import numpy as np
import pandas as pd

CHECK_VERSION = "point_check_v0.1.0"

DEPTH_VALID_MAX_M = 11500.0

FLAG_COLUMNS = [
    "valid_lon",
    "valid_lat",
    "valid_depth_pos",
    "valid_depth_max",
    "valid_core_fields",
    "point_check_pass_basic",
]


def compute_flag_arrays(
    lon: np.ndarray,
    lat: np.ndarray,
    depth: np.ndarray,
) -> dict[str, np.ndarray]:
    """Vectorized per-row check.  Inputs may contain NaNs."""
    finite_lon = np.isfinite(lon)
    finite_lat = np.isfinite(lat)
    finite_depth = np.isfinite(depth)

    valid_lon = np.zeros(lon.shape[0], dtype=bool)
    valid_lat = np.zeros(lon.shape[0], dtype=bool)
    valid_depth_pos = np.zeros(lon.shape[0], dtype=bool)
    valid_depth_max = np.zeros(lon.shape[0], dtype=bool)

    if finite_lon.any():
        valid_lon[finite_lon] = (lon[finite_lon] >= -180.0) & (
            lon[finite_lon] < 180.0
        )
    if finite_lat.any():
        valid_lat[finite_lat] = (lat[finite_lat] >= -90.0) & (
            lat[finite_lat] <= 90.0
        )
    if finite_depth.any():
        valid_depth_pos[finite_depth] = depth[finite_depth] > 0.0
        valid_depth_max[finite_depth] = depth[finite_depth] <= DEPTH_VALID_MAX_M

    valid_core_fields = finite_lon & finite_lat & finite_depth
    pass_basic = (
        valid_lon
        & valid_lat
        & valid_depth_pos
        & valid_depth_max
        & valid_core_fields
    )
    return {
        "valid_lon": valid_lon,
        "valid_lat": valid_lat,
        "valid_depth_pos": valid_depth_pos,
        "valid_depth_max": valid_depth_max,
        "valid_core_fields": valid_core_fields,
        "point_check_pass_basic": pass_basic,
    }


def summarize_flags(flags: dict[str, np.ndarray]) -> dict[str, int]:
    """Per-track summary: count of rows that FAIL each check + total pass."""
    n_points = flags["valid_lon"].size
    return {
        "n_points_in": int(n_points),
        "n_invalid_lon": int((~flags["valid_lon"]).sum()),
        "n_invalid_lat": int((~flags["valid_lat"]).sum()),
        "n_invalid_depth_pos": int((~flags["valid_depth_pos"]).sum()),
        "n_invalid_depth_max": int((~flags["valid_depth_max"]).sum()),
        "n_missing_core": int((~flags["valid_core_fields"]).sum()),
        "n_points_pass": int(flags["point_check_pass_basic"].sum()),
    }


def attach_flag_columns(df: pd.DataFrame, flags: dict[str, np.ndarray]) -> pd.DataFrame:
    """Append the 6 flag columns to the input DataFrame in canonical order."""
    out = df.copy()
    for col in FLAG_COLUMNS:
        out[col] = flags[col]
    return out
