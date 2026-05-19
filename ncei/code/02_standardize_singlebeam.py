#!/usr/bin/env python3
"""
02_standardize_singlebeam.py

PR-E2 — Standardize NCEI singlebeam `.nc` tracks into per-track parquet
point tables, sourced from the PR-E1 trackline source manifest.

Inputs:
  - ncei/manifests/trackline_source_manifest.parquet (read-only)
  - ncei/tracklines_nc/<track_id>.nc

Filter applied (per PRD `Finding 2026-05-19` + PR-E2 routing rule):
  source_type == 'ncei_nc'
  AND instrument_class_pred == 'singlebeam'
  AND has_depth == True
  AND depth_sign_raw IN ('mostly_positive', 'mostly_negative')

This MUST yield exactly 1,850 rows in full mode (the 33 nc_only
`all_zero` tracks are gravity/FAA-only — see PRD Finding 2026-05-19).

Outputs (full mode):
  - ncei/derived/singlebeam/points_raw/<track_id>__nc.parquet  (one per track)
  - ncei/manifests/singlebeam_points_raw_manifest.parquet
  - ncei/manifests/singlebeam_points_raw_manifest.tsv
  - ncei/docs/singlebeam_standardization_report.md
  - ncei/output/logs/02_standardize_singlebeam.log
  - ncei/output/logs/02_standardize_singlebeam_errors.tsv

Outputs (sample/test100 mode): suffix all of the above with `_<run-label>`
except the per-track parquet outputs (which always live under
`ncei/derived/singlebeam/points_raw/` and carry the `__nc` source suffix).

The `__nc` suffix on per-track outputs is symmetric with the `__xyz`
suffix written by `03_standardize_xyz.py`; together they let both source
sides for an `nc_xyz_intersect` track coexist in one directory without
filename collisions.

Usage:
    python -m ncei.code.02_standardize_singlebeam --estimate-only
    python -m ncei.code.02_standardize_singlebeam --run-label sample --sample-n-files 5 --overwrite
    python -m ncei.code.02_standardize_singlebeam --run-label test100 --limit-files 100 --overwrite
    python -m ncei.code.02_standardize_singlebeam --run-label full --confirm-full --overwrite
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent

NC_DIR = ROOT_DIR / "tracklines_nc"
MANIFEST_DIR = ROOT_DIR / "manifests"
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"
DERIVED_DIR = ROOT_DIR / "derived" / "singlebeam" / "points_raw"

VALID_RUN_LABELS = ("sample", "test100", "full")
STANDARDIZATION_VERSION = "ncei_sb_v0.2.0"

# Filter contract — see module docstring + PRD Finding 2026-05-19.
ALLOWED_DEPTH_SIGN_RAW = ("mostly_positive", "mostly_negative")

# PR-F (PRD Finding 2026-05-19b): depth-sentinel upper clip. Anything past
# Mariana Trench (~10,994 m) is sentinel / unit-error pollution, not real
# bathymetry. Symmetric with PRD Q3 M.rar lower-bound (depth < -11,500m).
DEPTH_CLIP_UPPER_M = 11500.0

# Point schema column order — must match PRD lines 666-676 exactly.
POINT_COLUMNS = [
    "source_type",
    "track_id",
    "point_index_in_track",
    "time",
    "lon_raw",
    "lat_raw",
    "lon",
    "lat",
    "depth_raw",
    "depth_m_positive_down",
    "elev_m",
    "gobs",
    "faa",
    "source_completeness",
    "instrument_class_pred",
    "standardization_version",
]


# ---------------------------------------------------------------------------
# Paths / atomic writes
# ---------------------------------------------------------------------------
def get_output_paths(run_label: str) -> dict[str, Path]:
    suffix = "" if run_label == "full" else f"_{run_label}"
    return {
        "manifest_pq": MANIFEST_DIR / f"singlebeam_points_raw_manifest{suffix}.parquet",
        "manifest_tsv": MANIFEST_DIR / f"singlebeam_points_raw_manifest{suffix}.tsv",
        "report_md": DOCS_DIR / f"singlebeam_standardization_report{suffix}.md",
        "log": LOG_DIR / f"02_standardize_singlebeam{suffix}.log",
        "errors_tsv": LOG_DIR / f"02_standardize_singlebeam_errors{suffix}.tsv",
    }


def atomic_write_parquet(df: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    df.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, target)


def atomic_write_tsv(df: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, target)


def atomic_write_text(text: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)


def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ncei_standardize_singlebeam")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s")
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(levelname)-8s %(message)s"))
    logger.addHandler(ch)
    return logger


# ---------------------------------------------------------------------------
# NetCDF read + standardize helpers
# ---------------------------------------------------------------------------
def masked_to_float_array(values) -> np.ndarray:
    """Convert a netCDF masked array to a plain float64 array with NaN fills."""
    arr = np.ma.asarray(values)
    if arr.shape == ():
        arr = arr.reshape(1)
    arr = np.ma.filled(arr, np.nan)
    return np.asarray(arr, dtype=np.float64).reshape(-1)


def normalize_lon(lon: np.ndarray) -> np.ndarray:
    """Wrap any lon > 180 to (-180, 180]. Leaves NaNs alone."""
    out = lon.copy()
    mask = np.isfinite(out) & (out > 180.0)
    if mask.any():
        out[mask] = out[mask] - 360.0
    return out


def sanitize_lat(lat: np.ndarray) -> np.ndarray:
    """Replace out-of-[-90, 90] values with NaN (defensive; should not fire)."""
    out = lat.copy()
    mask = np.isfinite(out) & ((out < -90.0) | (out > 90.0))
    if mask.any():
        out[mask] = np.nan
    return out


def decode_time(ds, n_points: int) -> tuple[Optional[np.ndarray], bool]:
    """Return (timestamp ndarray of length n_points, has_time bool).

    Returns (None, False) when time is absent or all-masked or not decodable.
    """
    import netCDF4 as nc

    if "time" not in ds.variables:
        return None, False
    var = ds.variables["time"]
    if getattr(var, "size", 0) == 0:
        return None, False
    units = getattr(var, "units", None)
    if not units:
        return None, False
    raw = var[:]
    arr = np.ma.asarray(raw)
    if arr.shape == ():
        arr = arr.reshape(1)
    if arr.size != n_points:
        # Shape mismatch — defensive; downstream needs aligned arrays.
        return None, False
    mask = np.ma.getmaskarray(arr)
    if mask.all():
        return None, False
    try:
        decoded = nc.num2date(
            np.ma.filled(arr, np.nan),
            units=units,
            only_use_cftime_datetimes=False,
            only_use_python_datetimes=True,
        )
    except Exception:
        return None, False
    # Build pandas datetime64[ns] with NaT for masked entries.
    out = pd.Series(decoded)
    out = pd.to_datetime(out, errors="coerce")
    out[mask] = pd.NaT
    return out.to_numpy(), True


def read_per_point_or_nan(ds, varname: str, n_points: int) -> Optional[np.ndarray]:
    """Read a variable as float64 length n_points, or return None if not present
    / not per-point / all-NaN."""
    if varname not in ds.variables:
        return None
    var = ds.variables[varname]
    if getattr(var, "size", 0) == 0:
        return None
    raw = var[:]
    arr = np.ma.asarray(raw)
    if arr.shape == ():
        # Scalar attribute, not per-point — treat as absent for the point table.
        return None
    arr = np.ma.filled(arr, np.nan)
    arr = np.asarray(arr, dtype=np.float64).reshape(-1)
    if arr.size != n_points:
        return None
    if not np.isfinite(arr).any():
        return None
    return arr


def standardize_one_track(
    nc_path: Path,
    track_id: str,
    source_completeness: str,
    depth_sign_raw: str,
) -> tuple[pd.DataFrame, dict]:
    """Read one .nc file and return (point DataFrame, per-track summary dict).

    Raises on unrecoverable errors; per-file isolation is handled by the
    caller in `main()`.
    """
    import netCDF4 as nc

    warnings_count = 0

    with nc.Dataset(nc_path) as ds:
        if "lon" not in ds.variables or "lat" not in ds.variables:
            raise ValueError(f"missing lon/lat in {nc_path}")

        lon_full = masked_to_float_array(ds.variables["lon"][:])
        lat_full = masked_to_float_array(ds.variables["lat"][:])
        if lon_full.size != lat_full.size:
            raise ValueError(
                f"lon/lat length mismatch in {nc_path}: {lon_full.size} vs {lat_full.size}"
            )

        finite_xy_full = np.isfinite(lon_full) & np.isfinite(lat_full)
        # Read depth (required by filter contract; if missing, raise).
        if "depth" not in ds.variables:
            raise ValueError(f"missing depth in {nc_path} (manifest filter contract violated)")
        depth_full = masked_to_float_array(ds.variables["depth"][:])
        if depth_full.size != lon_full.size:
            raise ValueError(
                f"depth length mismatch in {nc_path}: {depth_full.size} vs {lon_full.size}"
            )

        # Time decoding (aligned to full track first; we slice with finite_xy
        # after).
        time_full, has_time = decode_time(ds, n_points=lon_full.size)

        gobs_full = read_per_point_or_nan(ds, "gobs", n_points=lon_full.size)
        faa_full = read_per_point_or_nan(ds, "faa", n_points=lon_full.size)

    # Apply finite-xy filter -- canonical row set for the output table.
    lon_raw = lon_full[finite_xy_full]
    lat_raw = lat_full[finite_xy_full]
    depth_raw = depth_full[finite_xy_full]

    n_points_in = int(lon_full.size)
    n_points_out = int(lon_raw.size)
    if n_points_out <= 0:
        raise ValueError(f"empty track after finite-xy filter: {nc_path}")

    # Normalize lon and sanitize lat.
    lon = normalize_lon(lon_raw)
    lat = sanitize_lat(lat_raw)

    # Time slice.
    # NOTE: use np.full(..., np.datetime64('NaT'), ...) rather than
    # `np.array([pd.NaT] * n, dtype='datetime64[ns]')` — the latter raises
    # `TypeError: 'float' object cannot be interpreted as an integer` under
    # numpy>=2 / pandas>=2 because pd.NaT is a float-like sentinel that the
    # constructor cannot coerce. This bug did not fire in PR-E2 only because
    # every standardized track had at least one valid timestamp after the
    # finite-xy filter — but the code path is reachable on future data.
    if has_time and time_full is not None:
        time_arr = time_full[finite_xy_full]
        # has_time stays True only if at least one valid timestamp remains.
        if not pd.notna(pd.Series(time_arr)).any():
            has_time = False
            time_arr = np.full(n_points_out, np.datetime64("NaT"), dtype="datetime64[ns]")
    else:
        time_arr = np.full(n_points_out, np.datetime64("NaT"), dtype="datetime64[ns]")

    # Depth sign normalization — per-track branch on depth_sign_raw.
    depth_m_positive_down = np.full(n_points_out, np.nan, dtype=np.float64)
    finite_depth_mask = np.isfinite(depth_raw)

    if depth_sign_raw == "mostly_positive":
        depth_m_positive_down[finite_depth_mask] = depth_raw[finite_depth_mask]
        # Any negative row inside a mostly-positive track: take abs() and warn.
        neg_mask = finite_depth_mask & (depth_raw < 0)
        if neg_mask.any():
            depth_m_positive_down[neg_mask] = np.abs(depth_raw[neg_mask])
            warnings_count += int(neg_mask.sum())
    elif depth_sign_raw == "mostly_negative":
        # Flip sign: NCEI XYZ convention is negative-down, so abs gives positive-down.
        depth_m_positive_down[finite_depth_mask] = -depth_raw[finite_depth_mask]
        # A positive row in a mostly-negative track is anomalous — abs and warn.
        pos_mask = finite_depth_mask & (depth_raw > 0)
        if pos_mask.any():
            depth_m_positive_down[pos_mask] = np.abs(depth_raw[pos_mask])
            warnings_count += int(pos_mask.sum())
    else:
        # Filter contract should keep us out of here; defensive — log via warning.
        warnings_count += n_points_out

    # PR-F universal depth clip (PRD Finding 2026-05-19b): NaN out any
    # positive-down depth > DEPTH_CLIP_UPPER_M. depth_raw preserved
    # unchanged for audit; only depth_m_positive_down + elev_m are NaN'd.
    over_clip = (
        np.isfinite(depth_m_positive_down)
        & (depth_m_positive_down > DEPTH_CLIP_UPPER_M)
    )
    n_clipped = int(over_clip.sum())
    if n_clipped:
        depth_m_positive_down[over_clip] = np.nan

    elev_m = -depth_m_positive_down

    # Optional fields: align with finite_xy filter; nullable.
    gobs = gobs_full[finite_xy_full] if gobs_full is not None else None
    faa = faa_full[finite_xy_full] if faa_full is not None else None

    has_gobs = bool(gobs is not None and np.isfinite(gobs).any())
    has_faa = bool(faa is not None and np.isfinite(faa).any())

    point_index = np.arange(n_points_out, dtype=np.int64)
    n_track = n_points_out

    data = {
        "source_type": np.array(["ncei_nc"] * n_track, dtype=object),
        "track_id": np.array([track_id] * n_track, dtype=object),
        "point_index_in_track": point_index,
        "time": time_arr,
        "lon_raw": lon_raw,
        "lat_raw": lat_raw,
        "lon": lon,
        "lat": lat,
        "depth_raw": depth_raw,
        "depth_m_positive_down": depth_m_positive_down,
        "elev_m": elev_m,
        "gobs": gobs if gobs is not None else np.full(n_track, np.nan, dtype=np.float64),
        "faa": faa if faa is not None else np.full(n_track, np.nan, dtype=np.float64),
        "source_completeness": np.array([source_completeness] * n_track, dtype=object),
        "instrument_class_pred": np.array(["singlebeam"] * n_track, dtype=object),
        "standardization_version": np.array([STANDARDIZATION_VERSION] * n_track, dtype=object),
    }
    df = pd.DataFrame(data, columns=POINT_COLUMNS)
    # Force the time column to datetime64[ns] explicitly (in case all NaT).
    df["time"] = pd.to_datetime(df["time"], errors="coerce")

    # Summary row for the aggregate manifest.
    bbox_lon_min = float(np.nanmin(lon)) if n_points_out else math.nan
    bbox_lon_max = float(np.nanmax(lon)) if n_points_out else math.nan
    bbox_lat_min = float(np.nanmin(lat)) if n_points_out else math.nan
    bbox_lat_max = float(np.nanmax(lat)) if n_points_out else math.nan

    if has_time:
        non_nat = df["time"].dropna()
        time_min = non_nat.min() if len(non_nat) else pd.NaT
        time_max = non_nat.max() if len(non_nat) else pd.NaT
    else:
        time_min = pd.NaT
        time_max = pd.NaT

    if finite_depth_mask.any():
        depth_min = float(np.nanmin(depth_m_positive_down))
        depth_max = float(np.nanmax(depth_m_positive_down))
    else:
        depth_min = math.nan
        depth_max = math.nan

    summary = {
        "track_id": track_id,
        "source_completeness": source_completeness,
        "n_points_in": n_points_in,
        "n_points_out": n_points_out,
        "bbox_lon_min": bbox_lon_min,
        "bbox_lon_max": bbox_lon_max,
        "bbox_lat_min": bbox_lat_min,
        "bbox_lat_max": bbox_lat_max,
        "time_min": time_min,
        "time_max": time_max,
        "depth_min": depth_min,
        "depth_max": depth_max,
        "depth_sign_raw": depth_sign_raw,
        "has_time": has_time,
        "has_gobs": has_gobs,
        "has_faa": has_faa,
        "n_warnings": warnings_count,
        "n_clipped": n_clipped,
        "standardization_version": STANDARDIZATION_VERSION,
        # output_path / output_size_bytes / error filled in by caller.
    }
    return df, summary


def process_one(
    row: pd.Series,
    overwrite: bool,
    logger: logging.Logger,
) -> dict:
    """Process one manifest row → write per-track parquet, return summary."""
    track_id = str(row["track_id"])
    depth_sign_raw = str(row["depth_sign_raw"])
    source_completeness = str(row["source_completeness"])

    nc_path = ROOT_DIR / str(row["source_path"])
    if not nc_path.exists():
        raise FileNotFoundError(f"source file missing: {nc_path}")

    out_path = DERIVED_DIR / f"{track_id}__nc.parquet"
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"output exists; pass --overwrite to replace: {out_path}")

    df, summary = standardize_one_track(
        nc_path=nc_path,
        track_id=track_id,
        source_completeness=source_completeness,
        depth_sign_raw=depth_sign_raw,
    )

    atomic_write_parquet(df, out_path)
    size_bytes = out_path.stat().st_size

    # Path convention matches 01_*.py: dataset-root-relative (i.e. relative
    # to ROOT_DIR = ncei/). Downstream consumers reconstruct full path via
    # `ROOT_DIR / row["output_path"]`.
    summary["output_path"] = str(out_path.relative_to(ROOT_DIR))
    summary["output_size_bytes"] = int(size_bytes)
    summary["error"] = None
    return summary


# ---------------------------------------------------------------------------
# Manifest filter
# ---------------------------------------------------------------------------
def load_filtered_manifest(manifest_path: Path, logger: logging.Logger) -> pd.DataFrame:
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"manifest not found: {manifest_path}. Regenerate via "
            "`python -m ncei.code.01_build_trackline_source_manifest --run-label full --confirm-full --overwrite`."
        )
    df = pd.read_parquet(manifest_path)
    logger.info("Loaded manifest: %d rows from %s", len(df), manifest_path)

    mask = (
        (df["source_type"] == "ncei_nc")
        & (df["instrument_class_pred"] == "singlebeam")
        & (df["has_depth"].astype(bool))
        & (df["depth_sign_raw"].isin(ALLOWED_DEPTH_SIGN_RAW))
    )
    filtered = df[mask].copy().reset_index(drop=True)
    logger.info(
        "Filter applied (source_type=ncei_nc, pred=singlebeam, has_depth, depth_sign in %s): %d rows",
        list(ALLOWED_DEPTH_SIGN_RAW),
        len(filtered),
    )
    return filtered


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def markdown_table(df: pd.DataFrame, max_rows: int = 20) -> list[str]:
    if len(df) == 0:
        return ["_None_", ""]
    preview = df.head(max_rows).copy()
    cols = list(preview.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in preview.iterrows():
        vals = []
        for col in cols:
            val = row[col]
            if isinstance(val, float):
                vals.append(f"{val:.3f}" if np.isfinite(val) else "")
            elif pd.isna(val):
                vals.append("")
            else:
                vals.append(str(val))
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    return lines


def make_report(
    manifest_df: pd.DataFrame,
    errors: list[dict],
    run_label: str,
    elapsed_s: float,
    tracks_in: int,
) -> str:
    lines: list[str] = []
    lines.append("# NCEI Singlebeam Standardization Report (PR-E2)")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Run label: `{run_label}`")
    lines.append(f"Standardization version: `{STANDARDIZATION_VERSION}`")
    lines.append(f"Elapsed: {elapsed_s:.1f}s")
    lines.append(f"Tracks in (after manifest filter): {tracks_in:,}")
    lines.append(f"Tracks standardized: {len(manifest_df):,}")
    lines.append(f"Errors: {len(errors):,}")
    if "n_warnings" in manifest_df.columns:
        lines.append(f"Total per-point warnings: {int(manifest_df['n_warnings'].sum()):,}")
    lines.append("")

    if len(manifest_df) == 0:
        lines.append("No tracks standardized.")
        if errors:
            lines.append("")
            lines.append("## Errors")
            lines.append("")
            lines.extend(markdown_table(pd.DataFrame(errors), max_rows=20))
        return "\n".join(lines)

    lines.append("## Source completeness counts")
    lines.append("")
    sc = manifest_df.groupby("source_completeness", dropna=False).size().reset_index(name="tracks")
    lines.extend(markdown_table(sc))

    lines.append("## Depth-sign-raw counts")
    lines.append("")
    ds_sign = manifest_df.groupby("depth_sign_raw", dropna=False).size().reset_index(name="tracks")
    lines.extend(markdown_table(ds_sign))

    lines.append("## Field availability")
    lines.append("")
    field_row = {
        "tracks": len(manifest_df),
        "has_time": int(manifest_df["has_time"].sum()),
        "has_gobs": int(manifest_df["has_gobs"].sum()),
        "has_faa": int(manifest_df["has_faa"].sum()),
    }
    lines.extend(markdown_table(pd.DataFrame([field_row])))

    lines.append("## Geometry / depth ranges")
    lines.append("")
    stats = {
        "n_points_in_total": int(manifest_df["n_points_in"].sum()),
        "n_points_out_total": int(manifest_df["n_points_out"].sum()),
        "n_points_in_per_track_min": int(manifest_df["n_points_in"].min()),
        "n_points_in_per_track_max": int(manifest_df["n_points_in"].max()),
        "lon_min": float(manifest_df["bbox_lon_min"].min()),
        "lon_max": float(manifest_df["bbox_lon_max"].max()),
        "lat_min": float(manifest_df["bbox_lat_min"].min()),
        "lat_max": float(manifest_df["bbox_lat_max"].max()),
        "depth_min_overall": float(manifest_df["depth_min"].min()),
        "depth_max_overall": float(manifest_df["depth_max"].max()),
    }
    lines.extend(markdown_table(pd.DataFrame([stats])))

    if manifest_df["has_time"].any():
        with_time = manifest_df[manifest_df["has_time"]]
        lines.append("## Time range (tracks with time only)")
        lines.append("")
        time_stats = {
            "tracks_with_time": int(len(with_time)),
            "time_min_overall": str(with_time["time_min"].min()),
            "time_max_overall": str(with_time["time_max"].max()),
        }
        lines.extend(markdown_table(pd.DataFrame([time_stats])))

    lines.append("## Warnings rollup")
    lines.append("")
    n_with_warn = int((manifest_df["n_warnings"] > 0).sum())
    lines.append(f"Tracks with one or more sign-anomaly points: {n_with_warn:,}")
    lines.append(f"Total sign-anomaly points across all tracks: {int(manifest_df['n_warnings'].sum()):,}")
    lines.append("")
    if n_with_warn:
        warn_top = manifest_df[manifest_df["n_warnings"] > 0].sort_values(
            "n_warnings", ascending=False
        )[["track_id", "depth_sign_raw", "n_points_out", "n_warnings"]].head(20)
        lines.extend(markdown_table(warn_top))

    lines.append("## Depth clip rollup (PR-F: depth > 11,500m → NaN)")
    lines.append("")
    n_with_clip = int((manifest_df["n_clipped"] > 0).sum())
    lines.append(f"Tracks with one or more clipped points: {n_with_clip:,}")
    lines.append(
        f"Total clipped points across all tracks: {int(manifest_df['n_clipped'].sum()):,}"
    )
    lines.append("")
    if n_with_clip:
        clip_top = manifest_df[manifest_df["n_clipped"] > 0].sort_values(
            "n_clipped", ascending=False
        )[["track_id", "depth_sign_raw", "n_points_out", "n_clipped"]].head(20)
        lines.extend(markdown_table(clip_top))

    if errors:
        lines.append("## Errors (top 20)")
        lines.append("")
        err_df = pd.DataFrame(errors)
        lines.extend(markdown_table(err_df, max_rows=20))

    lines.append("## Output paths")
    lines.append("")
    lines.append(f"- Per-track parquet dir: `ncei/derived/singlebeam/points_raw/`")
    lines.append(f"- Aggregate manifest (parquet): `ncei/manifests/singlebeam_points_raw_manifest{'_' + run_label if run_label != 'full' else ''}.parquet`")
    lines.append(f"- Aggregate manifest (tsv): `ncei/manifests/singlebeam_points_raw_manifest{'_' + run_label if run_label != 'full' else ''}.tsv`")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Standardize NCEI singlebeam .nc tracks (PR-E2)")
    parser.add_argument("--run-label", choices=VALID_RUN_LABELS, default="sample")
    parser.add_argument(
        "--sample-n-files",
        type=int,
        default=None,
        help="Randomly sample N files (required for sample mode unless --estimate-only)",
    )
    parser.add_argument(
        "--limit-files",
        type=int,
        default=None,
        help="Limit to first N files after sort (required for test100 mode)",
    )
    parser.add_argument("--confirm-full", action="store_true", help="Required when --run-label=full")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing per-track parquet outputs + summary manifests",
    )
    parser.add_argument(
        "--estimate-only",
        action="store_true",
        help="Print filter count and exit; does not require run-label-mode arg checks",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_DIR / "trackline_source_manifest.parquet",
        help="Path to the PR-E1 trackline source manifest",
    )
    args = parser.parse_args()

    paths = get_output_paths(args.run_label)
    logger = setup_logging(paths["log"])
    t0 = datetime.now()

    logger.info("=" * 60)
    logger.info("02_standardize_singlebeam.py START")
    logger.info("Args: %s", vars(args))

    if args.estimate_only:
        filtered = load_filtered_manifest(args.manifest, logger)
        print("Estimate only:")
        print(f"  manifest path:       {args.manifest}")
        print(f"  filter rows:         {len(filtered):,}")
        print(f"  source_completeness breakdown:")
        for sc, n in filtered["source_completeness"].value_counts().items():
            print(f"    {sc}: {n:,}")
        print(f"  depth_sign_raw breakdown:")
        for ds_sign, n in filtered["depth_sign_raw"].value_counts().items():
            print(f"    {ds_sign}: {n:,}")
        return 0

    if args.run_label == "full" and not args.confirm_full:
        logger.error("ABORTED: --run-label=full requires --confirm-full")
        return 2

    if args.run_label == "sample" and args.sample_n_files is None and args.limit_files is None:
        logger.error("ABORTED: sample mode requires --sample-n-files or --limit-files")
        return 2

    if args.run_label == "test100" and args.limit_files is None:
        logger.error("ABORTED: test100 mode requires --limit-files (e.g. 100)")
        return 2

    output_files = [paths["manifest_pq"], paths["manifest_tsv"], paths["report_md"]]
    if not args.overwrite:
        existing = [p for p in output_files if p.exists()]
        if existing:
            logger.error("ABORTED: outputs exist; use --overwrite. Existing: %s", existing)
            return 2

    filtered = load_filtered_manifest(args.manifest, logger)
    if args.run_label == "full" and len(filtered) != 1850:
        logger.error(
            "ABORTED: full-mode filter expected 1,850 rows per PRD Finding 2026-05-19; got %d",
            len(filtered),
        )
        return 3

    work = filtered.sort_values("track_id").reset_index(drop=True)

    # Apply sample / limit selection.
    if args.sample_n_files is not None and len(work) > args.sample_n_files:
        rng = np.random.default_rng(42)
        idx = sorted(rng.choice(len(work), size=args.sample_n_files, replace=False).tolist())
        work = work.iloc[idx].reset_index(drop=True)
    if args.limit_files is not None:
        work = work.head(args.limit_files).reset_index(drop=True)

    logger.info("Will standardize %d tracks", len(work))
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)

    summaries: list[dict] = []
    errors: list[dict] = []
    n_total = len(work)
    for idx, row in work.iterrows():
        if idx == 0 or (idx + 1) % 100 == 0 or (idx + 1) == n_total:
            logger.info("Processing %d/%d: %s", idx + 1, n_total, row["track_id"])
        try:
            summary = process_one(row, overwrite=args.overwrite, logger=logger)
            summaries.append(summary)
        except Exception as exc:  # per-file isolation
            logger.exception("Error processing track %s", row["track_id"])
            errors.append({
                "track_id": str(row["track_id"]),
                "source_path": str(row["source_path"]),
                "error": repr(exc),
            })

    manifest_df = pd.DataFrame(summaries)
    if len(manifest_df):
        manifest_df = manifest_df.sort_values("track_id").reset_index(drop=True)

    elapsed_s = (datetime.now() - t0).total_seconds()

    atomic_write_parquet(manifest_df, paths["manifest_pq"])
    # Cap TSV for non-full runs to keep diffs small.
    if args.run_label == "full":
        tsv_df = manifest_df
    else:
        tsv_df = manifest_df.head(500).copy()
    atomic_write_tsv(tsv_df, paths["manifest_tsv"])
    atomic_write_text(
        make_report(manifest_df, errors, args.run_label, elapsed_s, tracks_in=len(work)),
        paths["report_md"],
    )
    atomic_write_tsv(pd.DataFrame(errors), paths["errors_tsv"])

    logger.info("Wrote %s (%d rows)", paths["manifest_pq"], len(manifest_df))
    logger.info("Wrote %s", paths["report_md"])
    logger.info("Errors: %d", len(errors))
    logger.info("Elapsed: %.1fs", elapsed_s)
    logger.info("02_standardize_singlebeam.py DONE")

    print(f"Tracks standardized: {len(manifest_df):,}")
    print(f"Errors: {len(errors):,}")
    if "n_warnings" in manifest_df.columns and len(manifest_df):
        print(f"Per-point warnings (total): {int(manifest_df['n_warnings'].sum()):,}")
    if "n_clipped" in manifest_df.columns and len(manifest_df):
        print(
            f"Per-point depth clips (total, > {DEPTH_CLIP_UPPER_M:.0f}m): "
            f"{int(manifest_df['n_clipped'].sum()):,}"
        )
    print(f"Report: {paths['report_md']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
