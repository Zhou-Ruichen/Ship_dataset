#!/usr/bin/env python3
"""
24_true_crossover_audit.py

Task 09-02 deliverable D2 (.trellis/tasks/09-02-sb-crossover-bias-arms/prd.md):
true track-crossover audit for NCEI singlebeam (SB) tracks inside the six
frozen nested-GGM region tiles.

What it computes, per region tile:
  1. SB tracks whose points fall inside the region bbox (manifest-bbox
     prefilter, then exact point filter with a small margin). Track order =
     `point_index_in_track` (dense 0..N-1, verified at standardization).
  2. Ordered lon/lat polylines per track, split into runs at index gaps and
     at along-track jumps > GAP_BREAK_DEG (leg gaps / wrap artifacts in the
     raw tracks; a 5-degree tile makes such steps impossible within one
     surveyed line).
  3. Segment x segment intersections between DIFFERENT tracks (grid-bucketed
     candidates, exact 2D line-intersection test, numpy only). Depth (and
     nc time) at the crossing is linearly interpolated from the bracketing
     segment endpoints on each track.
  4. Difference = later_track_depth - earlier_track_depth for nc x nc pairs
     (ordered by the interpolated crossing time); pairs containing an xyz
     track carry no usable time and get a deterministic arbitrary order
     (nc before xyz, then track_id ascending) that is recorded per event.

Hygiene boundary (PRD "Hard constraints"):
  - SB x SB only. This script never opens any JAMSTEC or NCEI multibeam
    file and never reads any cell product (in particular no
    `representative_depth_m`, no `median_depth_m`); region role columns are
    irrelevant here because the audit uses raw points in a bbox, all roles.
  - Everything it reads is read-only.

Inputs (read-only):
  - ncei/manifests/trackline_source_manifest.parquet
      (columns: track_id, source_type, bbox_lon_min/max, bbox_lat_min/max)
  - ncei/derived/singlebeam/points_raw/<track_id>__nc.parquet
      columns used: point_index_in_track, time, lon, lat, depth_m_positive_down
  - ncei/derived/singlebeam/points_raw/<track_id>__xyz.parquet
      columns used: point_index_in_track, lon, lat, depth_m_positive_down
  - <freeze_dir>/region_cells_<tile>.parquet, columns lon/lat only, used
    solely to assert that the tile bbox matches the frozen region file.

Outputs (additive; atomic writes):
  - ncei/derived/true_crossover_audit/crossovers_<tile>.parquet   (per event)
  - ncei/derived/true_crossover_audit/pair_stats_<tile>.parquet   (per track pair)
  - ncei/derived/true_crossover_audit/track_stats_<tile>.parquet  (per track)
  - ncei/derived/true_crossover_audit/nc_time_qc.parquet          (per nc track, full-track)
  - ncei/derived/true_crossover_audit/region_summary.parquet      (region x pair type)
  - ncei/derived/true_crossover_audit/region_time_qc_summary.parquet
  - ncei/docs/step09_true_crossover_audit_report.md
  - ncei/output/logs/24_true_crossover_audit.log

Resumability: minimal skip-if-exists convention (PRD allows this; runtime is
small). Without --overwrite the script does nothing when all six per-region
crossover parquets already exist; with --overwrite (or with any of the six
missing) it recomputes everything. A rerun without --overwrite therefore
changes no file.

Usage (from repo root):
    python -m ncei.trackline crossover [--overwrite]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time as _time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent.parent.resolve()

from _common.file_io import atomic_write_parquet
from _common.script_utils import setup_logging
from _common.singlebeam_bias import nmad

MANIFEST_PATH = ROOT_DIR / "ncei" / "manifests" / "trackline_source_manifest.parquet"
POINTS_DIR = ROOT_DIR / "ncei" / "derived" / "singlebeam" / "points_raw"
OUT_DIR = ROOT_DIR / "ncei" / "derived" / "true_crossover_audit"
DOCS_DIR = ROOT_DIR / "ncei" / "docs"
LOG_DIR = ROOT_DIR / "ncei" / "output" / "logs"
REPORT_PATH = DOCS_DIR / "step09_true_crossover_audit_report.md"

FREEZE_DIR = Path(
    "/mnt/data2/06-Projects/15-swot_feature_physics_bathy/outputs/"
    "20260901T220024Z-prospective-nested-ggm-nested_region_freeze"
)

# Six frozen region tiles (PRD "Verified inputs"). lon0 < lon1, lat0 < lat1.
REGIONS: dict[str, tuple[float, float, float, float]] = {
    "lon068_lat018": (160.0, 165.0, 0.0, 5.0),
    "lon052_lat018": (80.0, 85.0, 0.0, 5.0),
    "lon058_lat012": (110.0, 115.0, -30.0, -25.0),
    "lon059_lat015": (115.0, 120.0, -15.0, -10.0),
    "lon004_lat033": (-160.0, -155.0, 75.0, 80.0),
    "lon021_lat010": (-75.0, -70.0, -40.0, -35.0),
}

# Point-selection margin around the tile bbox: keeps segments that straddle
# the boundary so crossings just inside the tile are found. Only crossings
# inside the un-margined bbox are reported.
MARGIN_DEG = 0.05

# Polyline break threshold for consecutive-point spacing. In-region steps
# > 0.25 deg are 0.027% of all steps and correspond to leg gaps / bad jumps
# (a 5-degree tile cannot contain a legitimate 0.25-degree sampling step
# chain gap of this kind); connecting them would fabricate crossings.
GAP_BREAK_DEG = 0.25

# Grid cell size (degrees) for segment-bucket candidate generation.
GRID_CELL_DEG = 0.02

# Two events of the same track pair closer than this (degrees, ~1 cm) are the
# same physical crossing detected twice (vertex-sharing segment pairs).
DEDUP_EPS_DEG = 1e-7

# |denom| below this in the segment-pair intersection test -> treated as
# parallel/collinear and skipped (no unique crossing point).
DENOM_EPS = 1e-15

# nc time QC bounds (epoch sanity). NCEI trackline geophysics vintage is
# mid-20th century onward; anything outside this window is a decode artifact.
EPOCH_MIN = np.datetime64("1930-01-01T00:00:00", "ns")
EPOCH_MAX = np.datetime64("2035-01-01T00:00:00", "ns")
# Same bounds as float seconds since the 1970 epoch (for the QC comparison).
EPOCH_MIN_S = EPOCH_MIN.view("int64") / 1e9
EPOCH_MAX_S = EPOCH_MAX.view("int64") / 1e9
_INT64_MIN = np.iinfo(np.int64).min

# Chunking for the vectorized exact-intersection pass.
INTERSECT_CHUNK = 2_000_000

MANIFEST_COLUMNS = [
    "track_id",
    "source_type",
    "bbox_lon_min",
    "bbox_lon_max",
    "bbox_lat_min",
    "bbox_lat_max",
]

EVENT_COLUMNS = [
    "pair_key",
    "track_id_first",
    "track_id_second",
    "source_type_pair",
    "crossing_lon",
    "crossing_lat",
    "depth_first_m",
    "depth_second_m",
    "diff_m",
    "time_first",
    "time_second",
    "ordering_basis",
]


def verify_region_bbox(tile: str, bbox: tuple[float, float, float, float], logger: logging.Logger) -> bool:
    """Assert the freeze file's cell coordinates sit inside the stated bbox.

    Reads only lon/lat from the freeze parquet (role columns are irrelevant
    here; the audit is all-roles by design).
    """
    path = FREEZE_DIR / f"region_cells_{tile}.parquet"
    if not path.exists():
        logger.warning("freeze parquet missing, skipping bbox cross-check: %s", path)
        return False
    cells = pd.read_parquet(path, columns=["lon", "lat"])
    lon0, lon1, lat0, lat1 = bbox
    ok = bool(
        cells.lon.between(lon0, lon1).all() and cells.lat.between(lat0, lat1).all()
    )
    if not ok:
        raise AssertionError(
            f"freeze cells for {tile} fall outside stated bbox {bbox}"
        )
    logger.info(
        "region %s: %d freeze cells within bbox (lon %.4f..%.4f, lat %.4f..%.4f)",
        tile, len(cells), cells.lon.min(), cells.lon.max(),
        cells.lat.min(), cells.lat.max(),
    )
    return True


def select_region_tracks(
    manifest: pd.DataFrame, bbox: tuple[float, float, float, float]
) -> pd.DataFrame:
    """Manifest rows whose track bbox intersects the tile bbox (prefilter)."""
    lon0, lon1, lat0, lat1 = bbox
    m = MARGIN_DEG
    return manifest[
        (manifest.bbox_lon_max >= lon0 - m)
        & (manifest.bbox_lon_min <= lon1 + m)
        & (manifest.bbox_lat_max >= lat0 - m)
        & (manifest.bbox_lat_min <= lat1 + m)
    ].copy()


def time_to_seconds(t: pd.Series) -> np.ndarray:
    """datetime64[ns] -> float64 seconds since 1970 epoch; NaT -> NaN."""
    v = t.to_numpy(dtype="datetime64[ns]").view("int64")
    out = v.astype(np.float64) / 1e9
    out[v == _INT64_MIN] = np.nan
    return out


def nc_time_qc_row(track_id: str, tsec: np.ndarray) -> dict:
    """Full-track nc time QC: monotonicity + epoch sanity.

    monotonic_ok is False when any time value is missing (cannot be verified)
    or when any consecutive present pair goes backward. The per-region report
    separates "missing time" tracks from backward-step tracks.
    """
    finite = np.isfinite(tsec)
    n_points = int(len(tsec))
    n_present = int(finite.sum())
    row = {
        "track_id": track_id,
        "source_type": "nc",
        "n_points": n_points,
        "n_time_present": n_present,
        "n_time_nat": n_points - n_present,
        "n_backward_steps": 0,
        "max_backward_step_s": 0.0,
        "time_min": pd.NaT,
        "time_max": pd.NaT,
        "monotonic_ok": bool(n_present == n_points),
        "epoch_ok": bool(n_present > 0),
    }
    if n_present == 0:
        return row
    if n_present >= 2:
        a = tsec[:-1]
        b = tsec[1:]
        both = finite[:-1] & finite[1:]
        back = both & (b < a)
        row["n_backward_steps"] = int(back.sum())
        if back.any():
            row["max_backward_step_s"] = float(np.max(a[back] - b[back]))
            row["monotonic_ok"] = False
    row["time_min"] = pd.to_datetime(np.min(tsec[finite]), unit="s")
    row["time_max"] = pd.to_datetime(np.max(tsec[finite]), unit="s")
    row["epoch_ok"] = bool(
        (tsec[finite] >= EPOCH_MIN_S).all() and (tsec[finite] <= EPOCH_MAX_S).all()
    )
    return row


class RegionTracks:
    """In-margin points and polyline segments for one region tile."""

    def __init__(self) -> None:
        self.x1: list[np.ndarray] = []
        self.y1: list[np.ndarray] = []
        self.x2: list[np.ndarray] = []
        self.y2: list[np.ndarray] = []
        self.d1: list[np.ndarray] = []
        self.d2: list[np.ndarray] = []
        self.t1: list[np.ndarray] = []
        self.t2: list[np.ndarray] = []
        self.seg_track: list[np.ndarray] = []
        self.track_ids: list[str] = []
        self.track_source: list[str] = []
        self.n_tracks_used = 0
        self.n_gap_breaks = 0
        self.n_zero_len_dropped = 0
        self.n_points_in_margin = 0
        self.n_twin_ids = 0

    def finalize_twin_count(self) -> None:
        """Track ids whose other-side (nc<->xyz) file also exists in
        points_raw; those pairs are excluded from candidate generation."""
        seen: set[str] = set()
        n = 0
        for t, s in zip(self.track_ids, self.track_source):
            if t in seen:
                continue
            seen.add(t)
            other = "xyz" if s == "nc" else "nc"
            if (POINTS_DIR / f"{t}__{other}.parquet").exists():
                n += 1
        self.n_twin_ids = n

    @property
    def n_nc(self) -> int:
        return sum(1 for s in self.track_source if s == "nc")

    @property
    def n_xyz(self) -> int:
        return sum(1 for s in self.track_source if s == "xyz")

    def flat(self, name: str) -> np.ndarray:
        return np.concatenate(getattr(self, name)) if getattr(self, name) else np.empty(0)


def load_region(
    sel: pd.DataFrame, bbox: tuple[float, float, float, float], logger: logging.Logger,
    time_qc: dict[str, dict],
) -> RegionTracks:
    lon0, lon1, lat0, lat1 = bbox
    m = MARGIN_DEG
    rt = RegionTracks()

    for rec in sel.itertuples(index=False):
        st = "nc" if rec.source_type == "ncei_nc" else "xyz"
        path = POINTS_DIR / f"{rec.track_id}__{st}.parquet"
        if not path.exists():
            continue  # track filtered out at standardization (not SB / no depth)
        cols = ["point_index_in_track", "lon", "lat", "depth_m_positive_down"]
        if st == "nc":
            cols.append("time")
        df = pd.read_parquet(path, columns=cols)
        lon = df["lon"].to_numpy(dtype=np.float64)
        lat = df["lat"].to_numpy(dtype=np.float64)
        inb = (
            (lon >= lon0 - m) & (lon <= lon1 + m)
            & (lat >= lat0 - m) & (lat <= lat1 + m)
        )
        tsec_full = time_to_seconds(df["time"]) if st == "nc" else None
        if st == "nc" and rec.track_id not in time_qc:
            # Full-track time QC (time is otherwise unused by the geometry).
            time_qc[rec.track_id] = nc_time_qc_row(rec.track_id, tsec_full)
        if int(inb.sum()) < 2:
            continue

        ii = np.flatnonzero(inb)
        lo_ = lon[ii]
        la_ = lat[ii]
        dep = df["depth_m_positive_down"].to_numpy(dtype=np.float64)[ii]
        rt.n_points_in_margin += int(len(ii))

        # Run continuity: consecutive point index AND spacing within threshold.
        link = (np.diff(ii) == 1) & (
            np.hypot(np.diff(lo_), np.diff(la_)) <= GAP_BREAK_DEG
        )
        rt.n_gap_breaks += int((~link).sum())

        x1 = lo_[:-1][link]
        y1 = la_[:-1][link]
        x2 = lo_[1:][link]
        y2 = la_[1:][link]
        d1 = dep[:-1][link]
        d2 = dep[1:][link]
        if st == "nc":
            tsec_in = tsec_full[ii]
            t1 = tsec_in[:-1][link]
            t2 = tsec_in[1:][link]
        else:
            t1 = np.full(len(x1), np.nan)
            t2 = np.full(len(x1), np.nan)

        good = ~((x1 == x2) & (y1 == y2))  # zero-length segments carry no direction
        rt.n_zero_len_dropped += int((~good).sum())

        g = int(len(rt.track_ids))
        for name, arr in (
            ("x1", x1), ("y1", y1), ("x2", x2), ("y2", y2),
            ("d1", d1), ("d2", d2), ("t1", t1), ("t2", t2),
        ):
            getattr(rt, name).append(arr[good])
        rt.seg_track.append(np.full(int(good.sum()), g, dtype=np.int64))
        rt.track_ids.append(rec.track_id)
        rt.track_source.append(st)
        rt.n_tracks_used += 1

    rt.finalize_twin_count()
    logger.info(
        "loaded %d usable tracks (%d nc, %d xyz; %d track ids have an nc/xyz "
        "twin file present), %d in-margin points, %d gap breaks, "
        "%d zero-length segments dropped",
        rt.n_tracks_used, rt.n_nc, rt.n_xyz, rt.n_twin_ids,
        rt.n_points_in_margin, rt.n_gap_breaks, rt.n_zero_len_dropped,
    )
    return rt


def grid_candidate_pairs(
    x1: np.ndarray, y1: np.ndarray, x2: np.ndarray, y2: np.ndarray,
    seg_idrank: np.ndarray, n_idranks: int, logger: logging.Logger,
) -> tuple[np.ndarray, np.ndarray]:
    """Deduplicated candidate segment pairs (i < j) that share at least one
    grid cell (segment bbox cell coverage).

    Pairs are formed only between segments of DIFFERENT track ids: a survey
    that exists both as a `__nc` and a `__xyz` file (the standardization
    splits nc_xyz_intersect tracks into both sides) is one track, not two,
    and crossing it with itself would fabricate ~zero-difference events.
    """
    ix1 = np.floor(x1 / GRID_CELL_DEG).astype(np.int64)
    iy1 = np.floor(y1 / GRID_CELL_DEG).astype(np.int64)
    ix2 = np.floor(x2 / GRID_CELL_DEG).astype(np.int64)
    iy2 = np.floor(y2 / GRID_CELL_DEG).astype(np.int64)
    ixmin = np.minimum(ix1, ix2)
    nx = np.abs(ix2 - ix1) + 1
    iymin = np.minimum(iy1, iy2)
    ny = np.abs(iy2 - iy1) + 1
    ncell = nx * ny

    S = len(x1)
    total = int(ncell.sum())
    starts = np.concatenate(([0], np.cumsum(ncell)[:-1]))
    rep = np.repeat(np.arange(S, dtype=np.int64), ncell)
    off = np.arange(total, dtype=np.int64) - np.repeat(starts, ncell)
    nyr = np.repeat(ny, ncell)
    cx = np.repeat(ixmin, ncell) + off // nyr
    cy = np.repeat(iymin, ncell) + off % nyr
    key = (cx + (1 << 20)) * (1 << 21) + (cy + (1 << 20))

    order = np.argsort(key, kind="stable")
    key_s = key[order]
    seg_s = rep[order]
    idr_s = seg_idrank[seg_s]

    pair_key = key_s * np.int64(n_idranks + 1) + idr_s
    uk, counts = np.unique(pair_key, return_counts=True)
    active = uk[counts >= 2]
    active_keys = np.unique(active // np.int64(n_idranks + 1))
    logger.info(
        "grid: %d segment-cell entries, %d non-empty cells, %d cells with >=2 track ids",
        total, len(np.unique(key_s)), len(active_keys),
    )

    ci_parts: list[np.ndarray] = []
    cj_parts: list[np.ndarray] = []
    for k in active_keys:
        lo = int(np.searchsorted(key_s, k, "left"))
        hi = int(np.searchsorted(key_s, k, "right"))
        s = seg_s[lo:hi]
        tr = idr_s[lo:hi]
        o = np.argsort(tr, kind="stable")
        tr_o = tr[o]
        s_o = s[o]
        bnd = np.flatnonzero(np.diff(tr_o)) + 1
        gstart = np.concatenate(([0], bnd))
        gend = np.concatenate((bnd, [len(tr_o)]))
        for a in range(len(gstart)):
            ia = s_o[gstart[a]:gend[a]]
            if len(ia) == 0:
                continue
            for b in range(a + 1, len(gstart)):
                ib = s_o[gstart[b]:gend[b]]
                if len(ib) == 0:
                    continue
                # Sharing a coarse grid cell is necessary but can create a
                # very large Cartesian product for dense, nearly collinear
                # tracks.  A true segment intersection also requires the two
                # segment bounding boxes to overlap.  Apply that exact
                # necessary condition in bounded chunks before retaining the
                # candidate ids; this changes cost, not the event set.
                block = max(1, INTERSECT_CHUNK // len(ib))
                for start in range(0, len(ia), block):
                    aa = np.repeat(ia[start:start + block], len(ib))
                    bb = np.tile(ib, min(block, len(ia) - start))
                    overlap = (
                        (np.minimum(x1[aa], x2[aa]) <= np.maximum(x1[bb], x2[bb]))
                        & (np.minimum(x1[bb], x2[bb]) <= np.maximum(x1[aa], x2[aa]))
                        & (np.minimum(y1[aa], y2[aa]) <= np.maximum(y1[bb], y2[bb]))
                        & (np.minimum(y1[bb], y2[bb]) <= np.maximum(y1[aa], y2[aa]))
                    )
                    if overlap.any():
                        aa = aa[overlap]
                        bb = bb[overlap]
                        rx = x2[aa] - x1[aa]
                        ry = y2[aa] - y1[aa]
                        sx = x2[bb] - x1[bb]
                        sy = y2[bb] - y1[bb]
                        denom = rx * sy - ry * sx
                        nonparallel = np.abs(denom) > DENOM_EPS
                        if not nonparallel.any():
                            continue
                        aa = aa[nonparallel]
                        bb = bb[nonparallel]
                        rx = rx[nonparallel]
                        ry = ry[nonparallel]
                        sx = sx[nonparallel]
                        sy = sy[nonparallel]
                        denom = denom[nonparallel]
                        qx = x1[bb] - x1[aa]
                        qy = y1[bb] - y1[aa]
                        t = (qx * sy - qy * sx) / denom
                        u = (qx * ry - qy * rx) / denom
                        intersects = (t >= 0.0) & (t <= 1.0) & (u >= 0.0) & (u <= 1.0)
                        if intersects.any():
                            ci_parts.append(aa[intersects])
                            cj_parts.append(bb[intersects])

    if not ci_parts:
        return np.empty(0, np.int64), np.empty(0, np.int64)
    ci = np.concatenate(ci_parts)
    cj = np.concatenate(cj_parts)
    enc = np.minimum(ci, cj) * np.int64(S) + np.maximum(ci, cj)
    enc = np.unique(enc)
    logger.info("candidates: %d raw -> %d unique segment pairs", len(ci), len(enc))
    return enc // S, enc % S


def exact_intersections(
    rt: RegionTracks, ci: np.ndarray, cj: np.ndarray, logger: logging.Logger,
) -> tuple[dict[str, np.ndarray], int]:
    """Vectorized exact segment-pair intersection; interpolate depth and time.

    Segment i (track A): P1 + t*(P2-P1); segment j (track B): Q1 + u*(Q2-Q1).
    t = cross(Q-P, s)/cross(r, s); u = cross(Q-P, r)/cross(r, s).
    Returns (dict of per-event arrays, n parallel/collinear candidates skipped).
    """
    x1 = rt.flat("x1"); y1 = rt.flat("y1")
    x2 = rt.flat("x2"); y2 = rt.flat("y2")
    d1 = rt.flat("d1"); d2 = rt.flat("d2")
    t1 = rt.flat("t1"); t2 = rt.flat("t2")

    out: dict[str, list[np.ndarray]] = {k: [] for k in ("i", "j", "cx", "cy", "da", "db", "ta", "tb")}
    n_parallel = 0
    n_events = 0
    for s0 in range(0, len(ci), INTERSECT_CHUNK):
        a = ci[s0:s0 + INTERSECT_CHUNK]
        b = cj[s0:s0 + INTERSECT_CHUNK]
        rx = x2[a] - x1[a]
        ry = y2[a] - y1[a]
        sx = x2[b] - x1[b]
        sy = y2[b] - y1[b]
        denom = rx * sy - ry * sx
        ok_den = np.abs(denom) > DENOM_EPS
        n_parallel += int((~ok_den).sum())
        if not ok_den.any():
            continue
        a = a[ok_den]; b = b[ok_den]
        rx = rx[ok_den]; ry = ry[ok_den]
        sx = sx[ok_den]; sy = sy[ok_den]
        denom = denom[ok_den]
        qx = x1[b] - x1[a]
        qy = y1[b] - y1[a]
        t = (qx * sy - qy * sx) / denom
        u = (qx * ry - qy * rx) / denom
        keep = (t >= 0.0) & (t <= 1.0) & (u >= 0.0) & (u <= 1.0)
        if not keep.any():
            continue
        a = a[keep]; b = b[keep]
        t = t[keep]; u = u[keep]
        rx = rx[keep]; ry = ry[keep]
        out["i"].append(a); out["j"].append(b)
        out["cx"].append(x1[a] + t * rx)
        out["cy"].append(y1[a] + t * ry)
        out["da"].append(d1[a] + t * (d2[a] - d1[a]))
        out["db"].append(d1[b] + u * (d2[b] - d1[b]))
        out["ta"].append(t1[a] + t * (t2[a] - t1[a]))
        out["tb"].append(t1[b] + u * (t2[b] - t1[b]))
        n_events += int(len(a))
    logger.info(
        "exact test: %d candidates, %d parallel/collinear skipped, %d intersecting",
        len(ci), n_parallel, n_events,
    )
    res = {k: (np.concatenate(v) if v else np.empty(0)) for k, v in out.items()}
    return res, n_parallel


def orient_and_filter(
    res: dict[str, np.ndarray],
    rt: RegionTracks,
    bbox: tuple[float, float, float, float],
    logger: logging.Logger,
) -> tuple[pd.DataFrame, dict]:
    """Keep crossings inside the true bbox with finite depths, dedup
    vertex-sharing duplicates, apply the ordering convention.

    Returns (events DataFrame, filter counts for the report).
    """
    lon0, lon1, lat0, lat1 = bbox
    counts = {"raw": int(len(res["cx"])), "inside": 0, "nan_depth": 0, "finite": 0, "dup": 0, "final": 0}
    if counts["raw"] == 0:
        logger.info("no intersecting segment pairs after exact test")
        return pd.DataFrame(columns=EVENT_COLUMNS), counts

    cx, cy = res["cx"], res["cy"]
    inside = (cx >= lon0) & (cx <= lon1) & (cy >= lat0) & (cy <= lat1)
    counts["inside"] = int(inside.sum())
    da, db = res["da"][inside], res["db"][inside]
    ta, tb = res["ta"][inside], res["tb"][inside]
    cx, cy = cx[inside], cy[inside]
    i_idx = res["i"][inside]
    j_idx = res["j"][inside]
    finite = np.isfinite(da) & np.isfinite(db)
    counts["nan_depth"] = int((~finite).sum())
    counts["finite"] = int(finite.sum())
    da, db = da[finite], db[finite]
    ta, tb = ta[finite], tb[finite]
    cx, cy = cx[finite], cy[finite]
    i_idx, j_idx = i_idx[finite], j_idx[finite]

    seg_track = rt.flat("seg_track")
    trk_a = seg_track[i_idx]
    trk_b = seg_track[j_idx]

    # Dedup vertex-sharing duplicates per canonical track pair.
    n_tracks = len(rt.track_ids)
    pk = np.minimum(trk_a, trk_b) * n_tracks + np.maximum(trk_a, trk_b)
    order = np.lexsort((cy, cx, pk))
    pk_s = pk[order]
    cx_s = cx[order]
    cy_s = cy[order]
    keep = np.ones(len(order), dtype=bool)
    if len(order) > 1:
        same_pair = pk_s[1:] == pk_s[:-1]
        close = (
            (np.abs(cx_s[1:] - cx_s[:-1]) <= DEDUP_EPS_DEG)
            & (np.abs(cy_s[1:] - cy_s[:-1]) <= DEDUP_EPS_DEG)
        )
        keep[1:] = ~(same_pair & close)
    counts["dup"] = int(len(order) - keep.sum())
    sel = order[keep]
    counts["final"] = int(len(sel))

    trk_a = trk_a[sel]
    trk_b = trk_b[sel]
    da = da[sel]; db = db[sel]
    ta = ta[sel]; tb = tb[sel]
    cx = cx[sel]; cy = cy[sel]

    # Ordering: nc x nc with both crossing times finite -> by time (earlier
    # first); otherwise deterministic arbitrary (nc before xyz, then
    # track_id ascending).
    is_nc = np.array([s == "nc" for s in rt.track_source])
    lex_rank = np.argsort(np.array(rt.track_ids), kind="stable")
    rank = np.empty(n_tracks, dtype=np.int64)
    rank[lex_rank] = np.arange(n_tracks)
    arb_rank = np.where(is_nc, rank, rank + n_tracks)

    a_nc = is_nc[trk_a]
    b_nc = is_nc[trk_b]
    use_time = a_nc & b_nc & np.isfinite(ta) & np.isfinite(tb)
    swap_time = tb < ta  # strict: tie keeps A (lower segment index) first
    swap_arb = arb_rank[trk_b] < arb_rank[trk_a]
    swap = np.where(use_time, swap_time, swap_arb)

    tid_a = np.array(rt.track_ids)[trk_a]
    tid_b = np.array(rt.track_ids)[trk_b]
    st_a = np.array(rt.track_source)[trk_a]
    st_b = np.array(rt.track_source)[trk_b]

    tid_first = np.where(swap, tid_b, tid_a)
    tid_second = np.where(swap, tid_a, tid_b)
    st_first = np.where(swap, st_b, st_a)
    st_second = np.where(swap, st_a, st_b)
    depth_first = np.where(swap, db, da)
    depth_second = np.where(swap, da, db)
    t_first = np.where(swap, tb, ta)
    t_second = np.where(swap, ta, tb)

    pair_type = np.where(
        st_first == "nc",
        np.where(st_second == "nc", "nc_x_nc", "nc_x_xyz"),
        "xyz_x_xyz",
    )
    # Canonical (lexicographic) pair key, independent of the event orientation.
    first_le = tid_first <= tid_second
    canonical_a = np.where(first_le, tid_first, tid_second)
    canonical_b = np.where(first_le, tid_second, tid_first)

    events = pd.DataFrame(
        {
            "pair_key": [f"{a}|{b}" for a, b in zip(canonical_a, canonical_b)],
            "track_id_first": tid_first,
            "track_id_second": tid_second,
            "source_type_pair": pair_type,
            "crossing_lon": cx,
            "crossing_lat": cy,
            "depth_first_m": depth_first,
            "depth_second_m": depth_second,
            "diff_m": depth_second - depth_first,
            "time_first": pd.to_datetime(
                np.where(np.isfinite(t_first), t_first, np.nan), unit="s", errors="coerce"
            ),
            "time_second": pd.to_datetime(
                np.where(np.isfinite(t_second), t_second, np.nan), unit="s", errors="coerce"
            ),
            "ordering_basis": np.where(use_time, "time", "arbitrary"),
        }
    )
    logger.info(
        "events: %(raw)d raw -> %(inside)d inside bbox -> %(nan_depth)d dropped "
        "for NaN depth -> %(dup)d vertex duplicates -> %(final)d final",
        counts,
    )
    return events, counts


def pair_and_track_stats(
    events: pd.DataFrame, rt: RegionTracks
) -> tuple[pd.DataFrame, pd.DataFrame]:
    src = {t: s for t, s in zip(rt.track_ids, rt.track_source)}
    empty_pair = pd.DataFrame()
    empty_track = pd.DataFrame()
    if events is None or events.empty:
        return empty_pair, empty_track

    pair_stats = (
        events.groupby(
            ["pair_key", "track_id_first", "track_id_second", "source_type_pair"],
            sort=True,
        )
        .agg(
            n_crossovers=("diff_m", "size"),
            median_diff_m=("diff_m", "median"),
            nmad_diff_m=("diff_m", nmad),
            median_abs_diff_m=("diff_m", lambda v: float(np.median(np.abs(v)))),
            n_ordered_by_time=("ordering_basis", lambda s: int((s == "time").sum())),
        )
        .reset_index()
    )

    # Track-level residual: this track's depth minus the partner's, per event.
    side_a = pd.DataFrame(
        {
            "track_id": events["track_id_first"].to_numpy(),
            "residual_m": events["depth_first_m"].to_numpy()
            - events["depth_second_m"].to_numpy(),
        }
    )
    side_b = pd.DataFrame(
        {
            "track_id": events["track_id_second"].to_numpy(),
            "residual_m": events["depth_second_m"].to_numpy()
            - events["depth_first_m"].to_numpy(),
        }
    )
    both = pd.concat([side_a, side_b], ignore_index=True)
    track_stats = (
        both.groupby("track_id")
        .agg(
            n_crossovers=("residual_m", "size"),
            median_signed_diff_m=("residual_m", "median"),
            median_abs_diff_m=("residual_m", lambda v: float(np.median(np.abs(v)))),
            nmad_signed_diff_m=("residual_m", nmad),
        )
        .reset_index()
    )
    partners = pd.concat(
        [
            pd.DataFrame(
                {"track_id": events["track_id_first"], "partner": events["track_id_second"]}
            ),
            pd.DataFrame(
                {"track_id": events["track_id_second"], "partner": events["track_id_first"]}
            ),
        ]
    )
    track_stats["n_partner_tracks"] = (
        track_stats["track_id"].map(partners.groupby("track_id")["partner"].nunique())
    )
    track_stats["source_type"] = track_stats["track_id"].map(src)
    return pair_stats, track_stats


def region_summary_rows(
    tile: str, events: pd.DataFrame, rt: RegionTracks, time_qc: dict[str, dict],
) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    for pt in ("nc_x_nc", "nc_x_xyz", "xyz_x_xyz"):
        ev = events[events["source_type_pair"] == pt] if events is not None and not events.empty else None
        row = {
            "region": tile,
            "source_type_pair": pt,
            "n_tracks_nc": rt.n_nc,
            "n_tracks_xyz": rt.n_xyz,
            "n_track_pairs": int(ev["pair_key"].nunique()) if ev is not None else 0,
            "n_crossovers": int(len(ev)) if ev is not None else 0,
            "median_abs_diff_m": float("nan"),
            "p90_abs_diff_m": float("nan"),
            "nmad_abs_diff_m": float("nan"),
            "median_signed_diff_m": float("nan"),
            "nmad_signed_diff_m": float("nan"),
        }
        if ev is not None and len(ev):
            x = ev["diff_m"].to_numpy()
            row["median_abs_diff_m"] = float(np.median(np.abs(x)))
            row["p90_abs_diff_m"] = float(np.percentile(np.abs(x), 90))
            row["nmad_abs_diff_m"] = nmad(np.abs(x))
            row["median_signed_diff_m"] = float(np.median(x))
            row["nmad_signed_diff_m"] = nmad(x)
        rows.append(row)

    nc_ids = [t for t, s in zip(rt.track_ids, rt.track_source) if s == "nc"]
    qc = [time_qc[t] for t in nc_ids if t in time_qc]
    tmin = [r["time_min"] for r in qc if pd.notna(r["time_min"])]
    tmax = [r["time_max"] for r in qc if pd.notna(r["time_max"])]
    qrow = {
        "region": tile,
        "n_nc_tracks_used": len(nc_ids),
        "n_tracks_with_missing_time": sum(1 for r in qc if r["n_time_nat"] > 0),
        "n_monotonic_violations": sum(1 for r in qc if not r["monotonic_ok"]),
        "n_epoch_violations": sum(1 for r in qc if not r["epoch_ok"]),
        "n_backward_steps_total": sum(r["n_backward_steps"] for r in qc),
        "time_min": min(tmin) if tmin else pd.NaT,
        "time_max": max(tmax) if tmax else pd.NaT,
    }
    return rows, qrow


def fmt(v, nd: int = 1) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "-"
    return f"{v:.{nd}f}"


def write_report(
    path: Path,
    summary_rows: list[dict],
    qc_rows: list[dict],
    region_notes: dict[str, dict],
    run_info: dict,
    global_median_abs: dict[str, float],
    logger: logging.Logger,
) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    epoch_lo = str(EPOCH_MIN.astype("datetime64[s]"))
    epoch_hi = str(EPOCH_MAX.astype("datetime64[s]"))
    lines: list[str] = []
    a = lines.append
    a("# Step 09 — True singlebeam crossover audit (deliverable D2)")
    a("")
    a(f"Generated: {ts}  ")
    a("Script: `ncei/trackline/crossover.py` (run from repo root)  ")
    a(f"Interpreter: `{run_info['python']}`  ")
    a(f"Runtime: {run_info['runtime_s']:.1f} s  ")
    a("Task: `.trellis/tasks/09-02-sb-crossover-bias-arms/prd.md` (D2)")
    a("")
    a("## Scope and question")
    a("")
    a("How consistent is singlebeam depth where two SB tracks physically cross")
    a("inside the six frozen nested-GGM region tiles? Each crossing gives two")
    a("interpolated depths at the same geographic point; their difference is a")
    a("bias/noise observation built from raw points only. This audit feeds no")
    a("fitting and is NOT compared against the D1 per-track bias estimates")
    a("here (the reviewer does that).")
    a("")
    a("## Method")
    a("")
    a("Inputs: `ncei/derived/singlebeam/points_raw/*__nc.parquet` (`time` +")
    a("`point_index_in_track`) and `*__xyz.parquet` (order only), selected via")
    a("the trackline manifest bbox then filtered by exact point coordinates.")
    a("Hygiene: SB x SB only — no JAMSTEC or NCEI multibeam file is opened and")
    a("no cell product (in particular no `representative_depth_m`) is read;")
    a("the only freeze-file access is a lon/lat containment check of the tile")
    a("bboxes. Depth column: `depth_m_positive_down` (standardized, m).")
    a("")
    a(f"- Points selected within tile bbox + {MARGIN_DEG} deg margin; only")
    a("  crossings inside the un-margined bbox are reported.")
    a("- Polyline continuity broken where consecutive points are not adjacent")
    a(f"  in `point_index_in_track` or spaced > {GAP_BREAK_DEG} deg. In-region")
    a("  steps beyond this threshold are 0.027% of all in-region steps and")
    a("  correspond to leg gaps or bad jumps; connecting them would fabricate")
    a("  crossings. Break counts are reported per region below.")
    a(f"- Candidate segment pairs come from a {GRID_CELL_DEG} deg grid bucketing")
    a("  of segment-bbox cell coverage; the exact 2D segment intersection test")
    a("  then keeps pairs meeting in 0 <= t,u <= 1 (parallel/collinear pairs")
    a("  skipped and counted). Different track ids only — no self-crossings,")
    a("  and never a track against its own nc/xyz twin file: the")
    a("  standardization splits `nc_xyz_intersect` tracks into a `__nc` and a")
    a("  `__xyz` side holding the same points, so crossing the two sides")
    a("  compares identical data (observed |diff| ~ 1e-13 m). Twin ids are")
    a("  excluded from candidate pairing and counted per region below.")
    a("- Depth (and nc time) at the crossing: linear interpolation between the")
    a("  two bracketing points of each track's segment (fraction in lon/lat).")
    a("- Difference convention: `diff_m = depth_second - depth_first`. For")
    a("  nc x nc pairs first = earlier by the interpolated crossing time")
    a("  (`ordering_basis = 'time'`); pairs containing an xyz track have no")
    a("  usable time and use a recorded arbitrary order (nc before xyz, then")
    a("  track_id ascending; `ordering_basis = 'arbitrary'`). Signed statistics")
    a("  of arbitrary-order aggregates are orientation-dependent; the |diff|")
    a("  statistics are not.")
    a(f"- Vertex-sharing duplicate detections (same pair within {DEDUP_EPS_DEG:.0e}")
    a("  deg, ~1 cm) collapse to one event. Events with a non-finite")
    a("  interpolated depth on either side are dropped (counted).")
    a("- nc time QC (full track, not just the tile): monotonicity = all")
    a("  consecutive steps non-decreasing over present times; tracks with any")
    a(f"  missing time are reported separately. Epoch sanity = present times")
    a(f"  within [{epoch_lo}, {epoch_hi}].")
    a("- Resumability: minimal skip-if-exists convention — without")
    a("  `--overwrite` the script does nothing when all six per-region")
    a("  crossover parquets exist, so a rerun changes no file. Runtime is")
    a("  small enough that full recompute with `--overwrite` is the only")
    a("  recovery path.")
    a("")
    a("NMAD = 1.4826 * median(|x - median(x)|).")
    a("")
    a("## Per-region results")
    a("")
    for tile, bbox in REGIONS.items():
        lon0, lon1, lat0, lat1 = bbox
        n = region_notes[tile]
        q = next(r for r in qc_rows if r["region"] == tile)
        a(f"### {tile} (lon {lon0:g}..{lon1:g}, lat {lat0:g}..{lat1:g})")
        a("")
        a(
            f"Tracks used: {n['n_tracks_used']} ({n['n_nc']} nc, {n['n_xyz']} xyz); "
            f"{n['n_twin_ids']} track ids have an nc/xyz twin file present "
            f"(excluded from pairing); {n['n_points']} in-margin points; "
            f"{n['n_segments']} segments "
            f"({n['n_gap_breaks']} gap breaks, {n['n_zero_len']} zero-length dropped)."
        )
        a("")
        a(
            "| pair type | track pairs | crossovers | median \\|diff\\| (m) "
            "| p90 \\|diff\\| (m) | NMAD \\|diff\\| (m) | median signed (m) "
            "| NMAD signed (m) |"
        )
        a("|---|---:|---:|---:|---:|---:|---:|---:|")
        for row in [r for r in summary_rows if r["region"] == tile]:
            a(
                f"| {row['source_type_pair']} | {row['n_track_pairs']} | "
                f"{row['n_crossovers']} | {fmt(row['median_abs_diff_m'])} | "
                f"{fmt(row['p90_abs_diff_m'])} | {fmt(row['nmad_abs_diff_m'])} | "
                f"{fmt(row['median_signed_diff_m'])} | {fmt(row['nmad_signed_diff_m'])} |"
            )
        a("")
        e = n["n_events"]
        a(
            f"Event pipeline: {n['n_candidates']} candidate segment pairs -> "
            f"{n['n_intersecting']} intersecting ({n['n_parallel']} parallel/collinear "
            f"skipped) -> {e['inside']} inside bbox -> {e['finite']} with finite depths "
            f"({e['nan_depth']} dropped NaN) -> {e['final']} after dedup "
            f"({e['dup']} vertex duplicates)."
        )
        a("")
        a(
            f"nc time QC: {q['n_nc_tracks_used']} nc tracks; "
            f"{q['n_tracks_with_missing_time']} with missing time values; "
            f"{q['n_monotonic_violations']} monotonicity violations "
            f"({q['n_backward_steps_total']} backward steps total); "
            f"{q['n_epoch_violations']} epoch violations; time span "
            f"{q['time_min']} .. {q['time_max']}."
        )
        a("")
    a("## Global summary")
    a("")
    tot = sum(r["n_crossovers"] for r in summary_rows)
    a(
        f"Six regions total: {tot} crossovers over "
        f"{sum(r['n_track_pairs'] for r in summary_rows)} track pairs."
    )
    a("")
    a("| region | nc x nc | nc x xyz | xyz x xyz | all crossovers | median \\|diff\\| (m) |")
    a("|---|---:|---:|---:|---:|---:|")
    for tile in REGIONS:
        rs = {r["source_type_pair"]: r for r in summary_rows if r["region"] == tile}
        a(
            f"| {tile} | {rs['nc_x_nc']['n_crossovers']} | "
            f"{rs['nc_x_xyz']['n_crossovers']} | {rs['xyz_x_xyz']['n_crossovers']} | "
            f"{sum(r['n_crossovers'] for r in rs.values())} | "
            f"{fmt(global_median_abs.get(tile, float('nan')))} |"
        )
    a("")
    a("## Output files")
    a("")
    a("```text")
    a("ncei/derived/true_crossover_audit/")
    a("  crossovers_<tile>.parquet     one row per crossing event")
    a("  pair_stats_<tile>.parquet     n / median / NMAD per track pair")
    a("  track_stats_<tile>.parquet    per-track residual vs all partners")
    a("  nc_time_qc.parquet            full-track nc time QC (all regions)")
    a("  region_summary.parquet        region x pair-type summary table")
    a("  region_time_qc_summary.parquet")
    a("```")
    a("")
    a("## Limitations")
    a("")
    a("- Event depths are interpolated from RAW points (`points_raw`, pre-QC):")
    a("  no depth quality filter is applied (the PRD scopes QC to nc time). A")
    a("  crossing that lands on a segment adjacent to a bad sounding inherits")
    a("  it, so single-event values can be extreme (observed: a ~1319 -> 132 m")
    a("  spike next to a crossing in lon004_lat033 pulling one interpolation")
    a("  ~335 m off). Read the median/NMAD columns, not individual events.")
    a("- Strict geometric crossing: near-parallel or collinear co-located")
    a("  tracks contribute nothing (collinear candidate pairs are skipped and")
    a("  counted), and true crossings need both interpolated depths finite;")
    a("  nc tracks with high depth-missing rates lose events (counted per")
    a("  region as 'dropped NaN').")
    a("- nc x nc event counts are small in some tiles (e.g. 1 in")
    a("  lon004_lat033); read those medians with n in mind. Track-id twin")
    a("  pairs (same survey as nc and xyz files) are excluded by design.")
    a("")
    a("## Reproduction")
    a("")
    a("```bash")
    a("cd /mnt/data2/00-Data/ship")
    a(f"{run_info['python']} -m ncei.trackline crossover --overwrite")
    a("```")
    a("")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    os.replace(tmp, path)
    logger.info("wrote %s", path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ncei.trackline crossover", description="True SB crossover audit, six frozen region tiles")
    parser.add_argument(
        "--overwrite", action="store_true",
        help="recompute even if all six per-region outputs exist",
    )
    args = parser.parse_args(argv)

    t_start = _time.time()
    logger = setup_logging(LOG_DIR / "24_true_crossover_audit.log", "ncei_true_crossover_audit")
    logger.info("true crossover audit start (overwrite=%s)", args.overwrite)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = [OUT_DIR / f"crossovers_{t}.parquet" for t in REGIONS]
    if all(p.exists() for p in existing) and not args.overwrite:
        logger.info(
            "all six crossovers_<tile>.parquet exist; skip (minimal skip-if-exists "
            "resumability; pass --overwrite to recompute)"
        )
        return 0

    manifest = pd.read_parquet(MANIFEST_PATH, columns=MANIFEST_COLUMNS)
    logger.info("manifest: %d tracks", len(manifest))

    for tile, bbox in REGIONS.items():
        verify_region_bbox(tile, bbox, logger)

    time_qc: dict[str, dict] = {}
    summary_rows: list[dict] = []
    qc_rows: list[dict] = []
    region_notes: dict[str, dict] = {}
    global_median_abs: dict[str, float] = {}

    for tile, bbox in REGIONS.items():
        logger.info("=== region %s %s", tile, bbox)
        sel = select_region_tracks(manifest, bbox)
        rt = load_region(sel, bbox, logger, time_qc)

        if rt.n_tracks_used == 0:
            logger.warning("no usable tracks in %s", tile)
            events = pd.DataFrame(columns=EVENT_COLUMNS)
            counts = {"raw": 0, "inside": 0, "nan_depth": 0, "finite": 0, "dup": 0, "final": 0}
            pair_stats = pd.DataFrame()
            track_stats = pd.DataFrame()
            n_candidates = 0
            n_parallel = 0
            n_intersecting = 0
            n_segments = 0
        else:
            x1 = rt.flat("x1")
            n_segments = int(len(x1))
            # Dense rank over unique track ids: same-id nc/xyz twin files must
            # not be crossed against each other.
            _, idr = np.unique(np.array(rt.track_ids), return_inverse=True)
            seg_idrank = idr[rt.flat("seg_track")]
            ci, cj = grid_candidate_pairs(
                x1, rt.flat("y1"), rt.flat("x2"), rt.flat("y2"),
                seg_idrank, int(idr.max()) + 1, logger,
            )
            n_candidates = int(len(ci))
            res, n_parallel = exact_intersections(rt, ci, cj, logger)
            n_intersecting = int(len(res["cx"]))
            events, counts = orient_and_filter(res, rt, bbox, logger)
            pair_stats, track_stats = pair_and_track_stats(events, rt)

        atomic_write_parquet(events, OUT_DIR / f"crossovers_{tile}.parquet", logger)
        atomic_write_parquet(pair_stats, OUT_DIR / f"pair_stats_{tile}.parquet", logger)
        atomic_write_parquet(track_stats, OUT_DIR / f"track_stats_{tile}.parquet", logger)

        rows, qrow = region_summary_rows(tile, events, rt, time_qc)
        summary_rows.extend(rows)
        qc_rows.append(qrow)
        region_notes[tile] = {
            "n_tracks_used": rt.n_tracks_used,
            "n_nc": rt.n_nc,
            "n_xyz": rt.n_xyz,
            "n_twin_ids": rt.n_twin_ids,
            "n_points": rt.n_points_in_margin,
            "n_segments": n_segments,
            "n_gap_breaks": rt.n_gap_breaks,
            "n_zero_len": rt.n_zero_len_dropped,
            "n_candidates": n_candidates,
            "n_parallel": n_parallel,
            "n_intersecting": n_intersecting,
            "n_events": counts,
        }
        global_median_abs[tile] = (
            float(np.median(np.abs(events["diff_m"].to_numpy())))
            if len(events)
            else float("nan")
        )

    qc_df = pd.DataFrame(list(time_qc.values()))
    atomic_write_parquet(qc_df, OUT_DIR / "nc_time_qc.parquet", logger)
    atomic_write_parquet(pd.DataFrame(summary_rows), OUT_DIR / "region_summary.parquet", logger)
    atomic_write_parquet(pd.DataFrame(qc_rows), OUT_DIR / "region_time_qc_summary.parquet", logger)

    run_info = {"python": sys.executable, "runtime_s": _time.time() - t_start}
    write_report(REPORT_PATH, summary_rows, qc_rows, region_notes, run_info,
                 global_median_abs, logger)
    logger.info("done in %.1f s", _time.time() - t_start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
