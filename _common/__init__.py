"""Shared utilities for the ship bathymetry pipelines (mb + sb)."""

from _common.r2_classifier import (
    R2Result,
    classify,
    classify_from_arrays,
    R2_HARD_MB_POINTS,
    R2_HARD_SB_POINTS,
    R2_BBOX_KM2_CUTOFF,
    R2_DENSITY_PPKM2_CUTOFF,
)

__all__ = [
    "R2Result",
    "classify",
    "classify_from_arrays",
    "R2_HARD_MB_POINTS",
    "R2_HARD_SB_POINTS",
    "R2_BBOX_KM2_CUTOFF",
    "R2_DENSITY_PPKM2_CUTOFF",
]
