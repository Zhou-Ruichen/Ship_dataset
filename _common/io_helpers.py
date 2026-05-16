"""Read lon/lat arrays from NCEI trackline files (.nc + .xyz).

Single-purpose helpers for the R2 calibration driver. Both readers stream
from disk; nothing else stays in memory after the call.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def read_xyz_lonlat(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Read lon, lat columns from an NCEI tracklines .xyz file.

    File format: 3-col CSV with header `LON,LAT,CORR_DEPTH`. Vectorized
    via `np.loadtxt` with usecols=(0, 1) to skip the depth column.
    """
    data = np.loadtxt(
        path,
        delimiter=",",
        skiprows=1,
        usecols=(0, 1),
        dtype=np.float64,
    )
    if data.ndim == 1:
        # Single-row file → (2,), reshape so unpacking below still works.
        data = data.reshape(1, 2)
    return data[:, 0], data[:, 1]


def read_nc_lonlat(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Read lon, lat from an MGD77+ NetCDF trackline (.nc) file.

    netCDF4 auto-applies the `scale_factor` attribute so values come back
    as float64 degrees. Masked entries are filled with NaN for downstream
    safety, then filtered out.
    """
    import netCDF4 as nc  # local import — only loaded when reading .nc

    with nc.Dataset(path) as ds:
        lon = np.asarray(ds.variables["lon"][:], dtype=np.float64)
        lat = np.asarray(ds.variables["lat"][:], dtype=np.float64)
    # Drop NaN entries (rare, but possible if upstream marked invalid rows).
    finite = np.isfinite(lon) & np.isfinite(lat)
    return lon[finite], lat[finite]
