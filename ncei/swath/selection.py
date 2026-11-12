"""Apply the 10-25 sounding checks and exact source-ping exclusions."""

from __future__ import annotations

import numpy as np
import pandas as pd

PING_ID = ["ping_navigation_record_index", "epoch_us", "native_ping_counter"]
SELECTION_COLUMN = "point_selected_basic_native_good_valid_ping_navigation"
SELECTION_RULE = (
    "point_check_pass_basic & (native_quality_state == 'good') & valid_ping_navigation"
    " & ~confirmed_invalid_source_ping"
)
STATES = ("good", "flagged", "null", "unknown")
DEPTH_COUNTS = ("n_depth_pos", "n_depth_neg", "n_depth_zero", "n_depth_nan")
STAGE_COUNTS = (
    "n_pass_basic", "n_selected_basic_native_good", "n_selected_before_exclusions",
    "n_excluded_selected_beams", "n_selected",
)
COUNTS = (
    "n_rows", "n_finite_position", *DEPTH_COUNTS, *(f"n_{state}" for state in STATES),
    "n_valid_navigation_beams", "n_invalid_navigation_beams", "n_excluded_beams", *STAGE_COUNTS,
)
BOUNDS = ("lon_min", "lon_max", "lat_min", "lat_max", "depth_min_raw", "depth_max_raw")


def depth_counts(depth: np.ndarray) -> dict[str, int]:
    finite = depth[np.isfinite(depth)]
    return dict(zip(DEPTH_COUNTS, (
        int((finite > 0).sum()), int((finite < 0).sum()), int((finite == 0).sum()),
        len(depth) - len(finite),
    )))


def depth_sign(counts: dict[str, int]) -> tuple[str, int]:
    """Keep the historical cruise-wide 95% convention, including zero depths."""
    pos, neg, zero = (counts[name] for name in DEPTH_COUNTS[:3])
    total = pos + neg + zero
    if not total:
        return "no_depth_values", 1
    if zero == total:
        return "all_zero", 1
    if pos / total >= 0.95:
        return "mostly_positive", 1
    if neg / total >= 0.95:
        return "mostly_negative", -1
    return "mixed_sign", 1


def basic_checks(lon: np.ndarray, lat: np.ndarray, depth: np.ndarray) -> dict[str, np.ndarray]:
    valid_lon = np.isfinite(lon) & (lon >= -180) & (lon < 180)
    valid_lat = np.isfinite(lat) & (lat >= -90) & (lat <= 90)
    valid_pos = np.isfinite(depth) & (depth > 0)
    valid_max = np.isfinite(depth) & (depth <= 11500)
    core = valid_lon & valid_lat & valid_pos & valid_max
    return {
        "valid_lon": valid_lon, "valid_lat": valid_lat, "valid_depth_pos": valid_pos,
        "valid_depth_max": valid_max, "valid_core_fields": core, "point_check_pass_basic": core,
    }


def excluded_pings(beams: pd.DataFrame, identities: set[tuple[int, int, int]]) -> np.ndarray:
    """Exclude only beams with all three exact ping identity fields equal."""
    excluded = np.zeros(len(beams), dtype=bool)
    for index, time, counter in identities:
        excluded |= ((beams[PING_ID[0]].to_numpy() == index) & (beams.epoch_us.to_numpy() == time)
                     & (beams.native_ping_counter.to_numpy() == counter))
    return excluded


def limits(values: np.ndarray) -> tuple[float | None, float | None]:
    return (float(values.min()), float(values.max())) if len(values) else (None, None)


def grid_candidates(beams: pd.DataFrame, identities: set[tuple[int, int, int]]) -> tuple[pd.DataFrame, dict]:
    """Keep candidate triples of either depth sign until the cruise sign is known."""
    lon, lat, depth = (beams[name].to_numpy() for name in ("lon", "lat", "depth_raw"))
    nav_valid = beams.valid_ping_navigation.to_numpy()
    quality = beams.native_quality_state
    good = quality.eq("good").to_numpy()
    excluded = excluded_pings(beams, identities)
    finite_position = np.isfinite(lon) & np.isfinite(lat)
    counts = {
        "n_rows": len(beams), "n_finite_position": int(finite_position.sum()),
        **depth_counts(depth),
        **{f"n_{state}": int(quality.eq(state).sum()) for state in STATES[:-1]},
        "n_unknown": int((~quality.isin(STATES[:-1])).sum()),
        "n_valid_navigation_beams": int(nav_valid.sum()),
        "n_invalid_navigation_beams": int((~nav_valid).sum()),
        "n_excluded_beams": int(excluded.sum()),
        **dict(zip(BOUNDS, (*limits(lon[finite_position]), *limits(lat[finite_position]),
                            *limits(depth[np.isfinite(depth)])))),
    }
    for sign, name in ((1, "positive"), (-1, "negative")):
        basic = basic_checks(lon, lat, depth * sign)["point_check_pass_basic"]
        basic_good = basic & good
        valid = basic_good & nav_valid
        stages = (basic, basic_good, valid, valid & excluded, valid & ~excluded)
        counts[name] = {key: int(mask.sum()) for key, mask in zip(STAGE_COUNTS, stages)}
    candidate = basic_checks(lon, lat, np.abs(depth))["point_check_pass_basic"] & good & nav_valid & ~excluded
    return beams.loc[candidate, ["lon", "lat", "depth_raw"]], counts
