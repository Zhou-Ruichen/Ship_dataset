"""R2 sb/mb classifier — threshold + spatial-spread rule.

Spec source: `.trellis/tasks/05-11-singlebeam-integration/prd.md` Q2 +
Locked decision #2. Classifies an NCEI trackline as singlebeam (sb) or
multibeam (mb) from its raw lon/lat geometry:

- `>R2_HARD_MB_POINTS` points → mb (hard rule, evidence: 12-file set).
- `<R2_HARD_SB_POINTS` points → sb (hard rule).
- Borderline 100k–1M points → mb if bbox < R2_BBOX_KM2_CUTOFF km²
  OR density > R2_DENSITY_PPKM2_CUTOFF pts/km²; else sb.

Thresholds are starter values, tunable post-calibration; see
`_common/calibration/r2_borderline.csv` for the scatter used to set them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

# Threshold constants — starter values per Q2 (tunable post-calibration).
R2_HARD_MB_POINTS: int = 1_000_000
R2_HARD_SB_POINTS: int = 100_000
R2_BBOX_KM2_CUTOFF: float = 5_000.0
R2_DENSITY_PPKM2_CUTOFF: float = 50.0

# Geodesy constant: km² per square degree at the equator.
# (111.32 km/deg)^2 ≈ 12,392.34 km²/deg². Latitude correction via cos(lat_mid)
# is applied to the lon span; the result is approximate but adequate for
# the order-of-magnitude bbox check the rule needs.
_KM2_PER_DEG2: float = 111.32 * 111.32


Label = Literal["sb", "mb"]
Reason = Literal[
    "hard_mb_points",
    "hard_sb_points",
    "borderline_bbox_below_cutoff",
    "borderline_density_above_cutoff",
    "borderline_default_sb",
]


@dataclass(frozen=True)
class R2Result:
    """Outcome of R2 classification for one trackline."""

    label: Label
    points: int
    bbox_km2: float | None  # None when label decision didn't need bbox
    density_ppkm2: float | None  # None when label decision didn't need density
    reason: Reason


def _bbox_km2(lon: np.ndarray, lat: np.ndarray) -> float:
    """Approximate bbox area in km², latitude-corrected."""
    lon_span = float(lon.max() - lon.min())
    lat_span = float(lat.max() - lat.min())
    lat_mid = float((lat.max() + lat.min()) / 2.0)
    cos_lat = math.cos(math.radians(lat_mid))
    # Latitude correction shrinks the lon-degree span at high latitudes.
    return lon_span * lat_span * cos_lat * _KM2_PER_DEG2


def classify(lon: np.ndarray, lat: np.ndarray) -> R2Result:
    """Classify a trackline from its full lon/lat arrays."""
    if len(lon) != len(lat):
        raise ValueError(f"lon/lat length mismatch: {len(lon)} vs {len(lat)}")
    if len(lon) == 0:
        raise ValueError("empty track")
    return _classify_impl(np.asarray(lon), np.asarray(lat), points=len(lon))


def classify_from_arrays(
    lon: np.ndarray,
    lat: np.ndarray,
    *,
    points: int | None = None,
) -> R2Result:
    """Like classify(), but accept an explicit `points` override.

    Useful for the cheap path: when only file size has been measured and
    the caller estimates point count without materializing arrays.
    """
    if points is None:
        return classify(lon, lat)
    if len(lon) != len(lat):
        raise ValueError(f"lon/lat length mismatch: {len(lon)} vs {len(lat)}")
    if len(lon) == 0 and points <= 0:
        raise ValueError("empty track")
    return _classify_impl(np.asarray(lon), np.asarray(lat), points=points)


def _classify_impl(lon: np.ndarray, lat: np.ndarray, *, points: int) -> R2Result:
    # Hard rules first — no bbox needed.
    if points > R2_HARD_MB_POINTS:
        return R2Result(
            label="mb",
            points=points,
            bbox_km2=None,
            density_ppkm2=None,
            reason="hard_mb_points",
        )
    if points < R2_HARD_SB_POINTS:
        return R2Result(
            label="sb",
            points=points,
            bbox_km2=None,
            density_ppkm2=None,
            reason="hard_sb_points",
        )

    # Borderline band: need bbox + density.
    bbox = _bbox_km2(lon, lat)
    if bbox <= 0.0:
        # Degenerate single-point file (all lon/lat identical).
        # Density is infinite by definition; route to mb.
        return R2Result(
            label="mb",
            points=points,
            bbox_km2=bbox,
            density_ppkm2=math.inf,
            reason="borderline_bbox_below_cutoff",
        )
    density = points / bbox
    if bbox < R2_BBOX_KM2_CUTOFF:
        return R2Result(
            label="mb",
            points=points,
            bbox_km2=bbox,
            density_ppkm2=density,
            reason="borderline_bbox_below_cutoff",
        )
    if density > R2_DENSITY_PPKM2_CUTOFF:
        return R2Result(
            label="mb",
            points=points,
            bbox_km2=bbox,
            density_ppkm2=density,
            reason="borderline_density_above_cutoff",
        )
    return R2Result(
        label="sb",
        points=points,
        bbox_km2=bbox,
        density_ppkm2=density,
        reason="borderline_default_sb",
    )
