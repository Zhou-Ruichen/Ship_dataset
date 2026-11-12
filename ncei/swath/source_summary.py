"""Summarize swath source fields used by the trackline manifest."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from _common.r2_classifier import classify_from_arrays

from .aggregation import source_labels
from .sources import ROOT

SOURCE_ARCHIVE = "ncei platforms tree direct download (raw_round2, 2026-09)"


def source_summary(cruise: str, formats: list[int], directories: list[Path], counts: dict,
                   bounds: dict, sign: str, data_root: Path = ROOT) -> dict:
    """Reduce source bounds and counts to the historical 26 source fields."""
    paths = [str(path.relative_to(data_root / "ncei") if path.is_relative_to(data_root / "ncei") else path)
             for path in directories]
    n = counts["n_finite_position"]
    west, east, south, north = (bounds[name] for name in ("lon_min", "lon_max", "lat_min", "lat_max"))
    if n:
        area = (east - west) * (north - south) * math.cos(math.radians((south + north) / 2)) * 111.32 * 111.32
        density = n / area if area > 0 else math.inf
        result = classify_from_arrays(np.array([west, east]), np.array([south, north]), points=n)
        is_mb, rule = result.label == "mb", result.reason
    else:
        area = density = None
        is_mb, rule = False, ""
    source_type, completeness = source_labels(formats)
    return {
        "track_id": cruise.lower(), "source_type": source_type, "source_completeness": completeness,
        "source_path": ";".join(paths), "source_archive": SOURCE_ARCHIVE,
        "n_points": n, "bbox_lon_min": west, "bbox_lon_max": east,
        "bbox_lat_min": south, "bbox_lat_max": north, "bbox_area_km2": area,
        "point_density_km2": density, "has_time": counts["n_rows"] > 0,
        "has_depth": counts["n_rows"] > counts["n_depth_nan"], "has_gobs": False, "has_faa": False,
        "depth_sign_raw": sign, "depth_min_raw": bounds["depth_min_raw"],
        "depth_max_raw": bounds["depth_max_raw"], "instrument_class_pred": "multibeam" if is_mb else "singlebeam",
        "classification_rule": rule, "classification_review": is_mb,
        "review_reason": rule if is_mb else "r2_pred_sb_overridden_by_source",
        "manual_override": "" if is_mb else "multibeam; raw .all.mb58 swath source (stage-2 provenance)",
        "source_author": None, "survey_id": cruise,
    }
