"""Shared estimators for constant singlebeam track bias."""

from __future__ import annotations

import numpy as np
import pandas as pd


def weighted_median(values: pd.Series, weights: pd.Series) -> float:
    order = np.argsort(values.to_numpy(dtype=float), kind="mergesort")
    sorted_values = values.to_numpy(dtype=float)[order]
    sorted_weights = weights.to_numpy(dtype=float)[order]
    cutoff = sorted_weights.sum() / 2.0
    return float(sorted_values[np.searchsorted(np.cumsum(sorted_weights), cutoff, side="left")])


def nmad(values: pd.Series | np.ndarray) -> float:
    array = np.asarray(values, dtype=float)
    if len(array) == 0:
        return float("nan")
    center = np.median(array)
    return float(1.4826 * np.median(np.abs(array - center)))


def bias_decision(residuals: pd.Series, weights: pd.Series) -> tuple[float, float, bool, str]:
    """Return candidate bias, NMAD, application decision, and gate reason."""
    count = len(residuals)
    candidate = weighted_median(residuals, weights) if count else float("nan")
    spread = nmad(residuals)
    if count < 5:
        return candidate, spread, False, "thin_evidence"
    if abs(candidate) < 2.0 * spread:
        return candidate, spread, False, "not_significant"
    return candidate, spread, True, "applied"
