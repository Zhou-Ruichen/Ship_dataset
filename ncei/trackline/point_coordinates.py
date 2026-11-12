"""Normalize longitude and latitude in NCEI point tables."""

import numpy as np


def normalize_lon(lon: np.ndarray) -> np.ndarray:
    """Wrap any lon > 180 to (-180, 180]. Leaves NaNs alone."""
    out = lon.copy()
    mask = np.isfinite(out) & (out > 180.0)
    if mask.any():
        out[mask] = out[mask] - 360.0
    return out


def sanitize_lat(lat: np.ndarray) -> np.ndarray:
    """Replace out-of-[-90, 90] values with NaN."""
    out = lat.copy()
    mask = np.isfinite(out) & ((out < -90.0) | (out > 90.0))
    if mask.any():
        out[mask] = np.nan
    return out
