#!/usr/bin/env python3
"""
03_standardize_xyz.py

PR-E3 — Standardize NCEI tracklines `.xyz` tracks into per-track parquet
point tables, sourced from the PR-E1 trackline source manifest.

Routing (per-track, from manifest's `instrument_class_pred`):
  - 'singlebeam' → ncei/derived/singlebeam/points_raw/<track_id>__xyz.parquet
  - 'multibeam'  → ncei/derived/multibeam/points_raw/<track_id>__xyz.parquet

Inputs:
  - ncei/manifests/trackline_source_manifest.parquet (read-only)
  - ncei/tracklines_xyz/<track_id>.xyz

Filter applied:
  source_type == 'ncei_xyz'

This MUST yield exactly 5,382 rows in full mode (5,365 sb + 17 mb),
per PRD Finding 2026-05-19 (all xyz are `mostly_positive` with depth).

Point schema mirrors `02_standardize_singlebeam.py` exactly (16 columns,
same order, same dtypes) so the two sides can be unioned downstream.
Per PRD line 683: "Missing .xyz fields stay null; do not invent fake
time/gravity fields." → `time=NaT`, `gobs=NaN`, `faa=NaN`.

Outputs (full mode):
  - ncei/derived/singlebeam/points_raw/<track_id>__xyz.parquet  (per sb track)
  - ncei/derived/multibeam/points_raw/<track_id>__xyz.parquet   (per mb track)
  - ncei/manifests/xyz_points_raw_manifest.parquet
  - ncei/manifests/xyz_points_raw_manifest.tsv
  - ncei/docs/xyz_standardization_report.md
  - ncei/output/logs/03_standardize_xyz.log
  - ncei/output/logs/03_standardize_xyz_errors.tsv

Outputs (sample/test100 mode): suffix all of the above with `_<run-label>`
except the per-track parquet outputs (which always carry the `__xyz`
source suffix).

Usage:
    python -m ncei.code.03_standardize_xyz --estimate-only
    python -m ncei.code.03_standardize_xyz --run-label sample --sample-n-files 5 --overwrite
    python -m ncei.code.03_standardize_xyz --run-label test100 --limit-files 100 --overwrite
    python -m ncei.code.03_standardize_xyz --run-label full --confirm-full --overwrite
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

XYZ_DIR = ROOT_DIR / "tracklines_xyz"
MANIFEST_DIR = ROOT_DIR / "manifests"
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"
DERIVED_SB_DIR = ROOT_DIR / "derived" / "singlebeam" / "points_raw"
DERIVED_MB_DIR = ROOT_DIR / "derived" / "multibeam" / "points_raw"

VALID_RUN_LABELS = ("sample", "test100", "full")
STANDARDIZATION_VERSION = "ncei_xyz_v0.1.0"
XYZ_CHUNK_SIZE = 500_000

# Filter contract — see module docstring + PRD Finding 2026-05-19.
EXPECTED_FULL_ROWS = 5382
EXPECTED_SB_ROWS = 5365
EXPECTED_MB_ROWS = 17

# Point schema column order — must exactly match the 02_*.py output so
# the two sides can be unioned downstream (PRD line 681).
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
        "manifest_pq": MANIFEST_DIR / f"xyz_points_raw_manifest{suffix}.parquet",
        "manifest_tsv": MANIFEST_DIR / f"xyz_points_raw_manifest{suffix}.tsv",
        "report_md": DOCS_DIR / f"xyz_standardization_report{suffix}.md",
        "log": LOG_DIR / f"03_standardize_xyz{suffix}.log",
        "errors_tsv": LOG_DIR / f"03_standardize_xyz_errors{suffix}.tsv",
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
    logger = logging.getLogger("ncei_standardize_xyz")
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
# XYZ read + standardize helpers
# ---------------------------------------------------------------------------
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


def read_xyz_full(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Read a .xyz file into (lon, lat, depth) float64 arrays, finite-xy filtered.

    Mirrors `01_build_trackline_source_manifest.py:read_xyz_track`'s
    headerless-detection + chunked-read pattern but builds full per-track
    arrays (rather than just summary stats). NaN-rejection happens on
    (lon, lat) only — `depth` retains NaNs at non-finite-xy-filtered rows
    so the caller can detect missing-depth-in-otherwise-valid-xy rows.
    """
    first_line = path.open("r", encoding="utf-8", errors="replace").readline().strip().upper()
    has_header = all(name in first_line for name in ("LON", "LAT"))
    read_kwargs: dict = {
        "chunksize": XYZ_CHUNK_SIZE,
        "header": 0 if has_header else None,
        "names": None if has_header else ["LON", "LAT", "CORR_DEPTH"],
        "usecols": ["LON", "LAT", "CORR_DEPTH"],
    }

    lon_parts: list[np.ndarray] = []
    lat_parts: list[np.ndarray] = []
    depth_parts: list[np.ndarray] = []

    for chunk in pd.read_csv(path, **read_kwargs):
        lon = pd.to_numeric(chunk["LON"], errors="coerce").to_numpy(dtype=np.float64)
        lat = pd.to_numeric(chunk["LAT"], errors="coerce").to_numpy(dtype=np.float64)
        depth = pd.to_numeric(chunk["CORR_DEPTH"], errors="coerce").to_numpy(dtype=np.float64)
        finite_xy = np.isfinite(lon) & np.isfinite(lat)
        lon_parts.append(lon[finite_xy])
        lat_parts.append(lat[finite_xy])
        depth_parts.append(depth[finite_xy])

    if lon_parts:
        lon_arr = np.concatenate(lon_parts)
        lat_arr = np.concatenate(lat_parts)
        depth_arr = np.concatenate(depth_parts)
    else:
        lon_arr = np.array([], dtype=np.float64)
        lat_arr = np.array([], dtype=np.float64)
        depth_arr = np.array([], dtype=np.float64)
    return lon_arr, lat_arr, depth_arr


def standardize_one_track(
    xyz_path: Path,
    track_id: str,
    source_completeness: str,
    instrument_class_pred: str,
    depth_sign_raw: str,
) -> tuple[pd.DataFrame, dict]:
    """Read one .xyz file and return (point DataFrame, per-track summary dict).

    Raises on unrecoverable errors; per-file isolation is handled by the
    caller in `main()`.
    """
    warnings_count = 0

    lon_raw, lat_raw, depth_raw = read_xyz_full(xyz_path)

    n_points_in = int(lon_raw.size)  # finite-xy already applied by reader
    n_points_out = n_points_in
    if n_points_out <= 0:
        raise ValueError(f"empty track after finite-xy filter: {xyz_path}")

    # Normalize lon and sanitize lat.
    lon = normalize_lon(lon_raw)
    lat = sanitize_lat(lat_raw)

    # All xyz tracks are documented `mostly_positive` per PR-E1 full scan
    # (see PRD Finding 2026-05-19). Use the same sign-normalization branch
    # logic as 02_*.py for symmetric handling.
    depth_m_positive_down = np.full(n_points_out, np.nan, dtype=np.float64)
    finite_depth_mask = np.isfinite(depth_raw)

    if depth_sign_raw == "mostly_positive":
        depth_m_positive_down[finite_depth_mask] = depth_raw[finite_depth_mask]
        neg_mask = finite_depth_mask & (depth_raw < 0)
        if neg_mask.any():
            depth_m_positive_down[neg_mask] = np.abs(depth_raw[neg_mask])
            warnings_count += int(neg_mask.sum())
    elif depth_sign_raw == "mostly_negative":
        depth_m_positive_down[finite_depth_mask] = -depth_raw[finite_depth_mask]
        pos_mask = finite_depth_mask & (depth_raw > 0)
        if pos_mask.any():
            depth_m_positive_down[pos_mask] = np.abs(depth_raw[pos_mask])
            warnings_count += int(pos_mask.sum())
    else:
        # Filter contract should keep us out of here; defensive — log via warning.
        warnings_count += n_points_out

    elev_m = -depth_m_positive_down

    # Build the point table — `time`, `gobs`, `faa` stay null per PRD line 683.
    point_index = np.arange(n_points_out, dtype=np.int64)
    time_arr = np.full(n_points_out, np.datetime64("NaT"), dtype="datetime64[ns]")
    gobs = np.full(n_points_out, np.nan, dtype=np.float64)
    faa = np.full(n_points_out, np.nan, dtype=np.float64)

    data = {
        "source_type": np.array(["ncei_xyz"] * n_points_out, dtype=object),
        "track_id": np.array([track_id] * n_points_out, dtype=object),
        "point_index_in_track": point_index,
        "time": time_arr,
        "lon_raw": lon_raw,
        "lat_raw": lat_raw,
        "lon": lon,
        "lat": lat,
        "depth_raw": depth_raw,
        "depth_m_positive_down": depth_m_positive_down,
        "elev_m": elev_m,
        "gobs": gobs,
        "faa": faa,
        "source_completeness": np.array([source_completeness] * n_points_out, dtype=object),
        "instrument_class_pred": np.array([instrument_class_pred] * n_points_out, dtype=object),
        "standardization_version": np.array(
            [STANDARDIZATION_VERSION] * n_points_out, dtype=object
        ),
    }
    df = pd.DataFrame(data, columns=POINT_COLUMNS)
    df["time"] = pd.to_datetime(df["time"], errors="coerce")

    # Summary row for the aggregate manifest.
    bbox_lon_min = float(np.nanmin(lon)) if n_points_out else math.nan
    bbox_lon_max = float(np.nanmax(lon)) if n_points_out else math.nan
    bbox_lat_min = float(np.nanmin(lat)) if n_points_out else math.nan
    bbox_lat_max = float(np.nanmax(lat)) if n_points_out else math.nan

    if finite_depth_mask.any():
        depth_min = float(np.nanmin(depth_m_positive_down))
        depth_max = float(np.nanmax(depth_m_positive_down))
    else:
        depth_min = math.nan
        depth_max = math.nan

    summary = {
        "track_id": track_id,
        "source_completeness": source_completeness,
        "instrument_class_pred": instrument_class_pred,
        "n_points_in": n_points_in,
        "n_points_out": n_points_out,
        "bbox_lon_min": bbox_lon_min,
        "bbox_lon_max": bbox_lon_max,
        "bbox_lat_min": bbox_lat_min,
        "bbox_lat_max": bbox_lat_max,
        "time_min": pd.NaT,
        "time_max": pd.NaT,
        "depth_min": depth_min,
        "depth_max": depth_max,
        "depth_sign_raw": depth_sign_raw,
        "has_time": False,
        "has_gobs": False,
        "has_faa": False,
        "n_warnings": warnings_count,
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
    instrument_class_pred = str(row["instrument_class_pred"])

    xyz_path = ROOT_DIR / str(row["source_path"])
    if not xyz_path.exists():
        raise FileNotFoundError(f"source file missing: {xyz_path}")

    if instrument_class_pred == "singlebeam":
        out_dir = DERIVED_SB_DIR
    elif instrument_class_pred == "multibeam":
        out_dir = DERIVED_MB_DIR
    else:
        raise ValueError(
            f"unexpected instrument_class_pred for track {track_id}: {instrument_class_pred!r}"
        )

    out_path = out_dir / f"{track_id}__xyz.parquet"
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"output exists; pass --overwrite to replace: {out_path}")

    df, summary = standardize_one_track(
        xyz_path=xyz_path,
        track_id=track_id,
        source_completeness=source_completeness,
        instrument_class_pred=instrument_class_pred,
        depth_sign_raw=depth_sign_raw,
    )

    atomic_write_parquet(df, out_path)
    size_bytes = out_path.stat().st_size

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

    mask = df["source_type"] == "ncei_xyz"
    filtered = df[mask].copy().reset_index(drop=True)
    logger.info(
        "Filter applied (source_type=ncei_xyz): %d rows (%d sb + %d mb)",
        len(filtered),
        int((filtered["instrument_class_pred"] == "singlebeam").sum()),
        int((filtered["instrument_class_pred"] == "multibeam").sum()),
    )
    return filtered


def stratified_sample(work: pd.DataFrame, n_per_class: int, seed: int = 42) -> pd.DataFrame:
    """Stratified sample: take up to N from each instrument_class_pred bucket.

    Ensures the small mb minority is exercised when --sample-n-files is small.
    """
    rng = np.random.default_rng(seed)
    parts: list[pd.DataFrame] = []
    for pred, sub in work.groupby("instrument_class_pred"):
        if len(sub) <= n_per_class:
            parts.append(sub)
        else:
            idx = sorted(rng.choice(len(sub), size=n_per_class, replace=False).tolist())
            parts.append(sub.iloc[idx])
    out = pd.concat(parts, ignore_index=True)
    return out.sort_values("track_id").reset_index(drop=True)


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
    lines.append("# NCEI XYZ Standardization Report (PR-E3)")
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

    lines.append("## Routing (per instrument_class_pred)")
    lines.append("")
    pred_counts = (
        manifest_df.groupby("instrument_class_pred", dropna=False).size().reset_index(name="tracks")
    )
    lines.extend(markdown_table(pred_counts))

    lines.append("## Source completeness counts")
    lines.append("")
    sc = (
        manifest_df.groupby("source_completeness", dropna=False).size().reset_index(name="tracks")
    )
    lines.extend(markdown_table(sc))

    lines.append("## Depth-sign-raw counts")
    lines.append("")
    ds_sign = (
        manifest_df.groupby("depth_sign_raw", dropna=False).size().reset_index(name="tracks")
    )
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

    lines.append("## Top 5 largest multibeam tracks (by n_points_out)")
    lines.append("")
    mb_top = manifest_df[manifest_df["instrument_class_pred"] == "multibeam"].sort_values(
        "n_points_out", ascending=False
    )[["track_id", "source_completeness", "n_points_out", "bbox_lon_min", "bbox_lon_max", "bbox_lat_min", "bbox_lat_max"]]
    lines.extend(markdown_table(mb_top, max_rows=5))

    lines.append("## Top 5 largest singlebeam tracks (by n_points_out)")
    lines.append("")
    sb_top = manifest_df[manifest_df["instrument_class_pred"] == "singlebeam"].sort_values(
        "n_points_out", ascending=False
    )[["track_id", "source_completeness", "n_points_out", "bbox_lon_min", "bbox_lon_max", "bbox_lat_min", "bbox_lat_max"]]
    lines.extend(markdown_table(sb_top, max_rows=5))

    lines.append("## Warnings rollup")
    lines.append("")
    n_with_warn = int((manifest_df["n_warnings"] > 0).sum())
    lines.append(f"Tracks with one or more sign-anomaly points: {n_with_warn:,}")
    lines.append(
        f"Total sign-anomaly points across all tracks: {int(manifest_df['n_warnings'].sum()):,}"
    )
    lines.append("")
    if n_with_warn:
        warn_top = manifest_df[manifest_df["n_warnings"] > 0].sort_values(
            "n_warnings", ascending=False
        )[["track_id", "instrument_class_pred", "depth_sign_raw", "n_points_out", "n_warnings"]].head(20)
        lines.extend(markdown_table(warn_top))

    # Depth-anomaly flag: surface tracks whose per-track depth_max exceeds the
    # Challenger Deep + headroom cutoff (PRD Q3 picked −11,500 m for M.rar
    # cleaning; we re-use that absolute magnitude here as a soft anomaly flag).
    # Cleaning / clipping itself is out of PR-E3 scope — only surface for review.
    DEPTH_ANOMALY_CUTOFF_M = 11500.0
    anomalous = manifest_df[manifest_df["depth_max"] > DEPTH_ANOMALY_CUTOFF_M].sort_values(
        "depth_max", ascending=False
    )
    lines.append("## Depth-anomaly review (depth_max > 11,500 m)")
    lines.append("")
    lines.append(
        "Tracks whose per-track `depth_max` exceeds the Challenger Deep + "
        "headroom cutoff. These are surfaced as known anomalies (likely "
        "unit/sentinel issues in the upstream `.xyz` export); no clipping "
        "is applied at PR-E3 — cleaning belongs to a later QC step."
    )
    lines.append("")
    lines.append(f"Tracks with depth_max > {DEPTH_ANOMALY_CUTOFF_M:.0f} m: {len(anomalous):,}")
    lines.append("")
    if len(anomalous):
        lines.extend(markdown_table(
            anomalous[["track_id", "instrument_class_pred", "n_points_out", "depth_min", "depth_max"]],
            max_rows=20,
        ))

    if errors:
        lines.append("## Errors (top 20)")
        lines.append("")
        err_df = pd.DataFrame(errors)
        lines.extend(markdown_table(err_df, max_rows=20))

    lines.append("## Output paths")
    lines.append("")
    suffix = "" if run_label == "full" else f"_{run_label}"
    lines.append("- Per-track parquet dirs:")
    lines.append("  - singlebeam: `ncei/derived/singlebeam/points_raw/<track_id>__xyz.parquet`")
    lines.append("  - multibeam:  `ncei/derived/multibeam/points_raw/<track_id>__xyz.parquet`")
    lines.append(
        f"- Aggregate manifest (parquet): `ncei/manifests/xyz_points_raw_manifest{suffix}.parquet`"
    )
    lines.append(
        f"- Aggregate manifest (tsv): `ncei/manifests/xyz_points_raw_manifest{suffix}.tsv`"
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Standardize NCEI tracklines .xyz tracks (PR-E3)")
    parser.add_argument("--run-label", choices=VALID_RUN_LABELS, default="sample")
    parser.add_argument(
        "--sample-n-files",
        type=int,
        default=None,
        help=(
            "Sample mode: take up to N tracks from each instrument_class_pred bucket "
            "(stratified sb/mb). Required for sample mode unless --estimate-only."
        ),
    )
    parser.add_argument(
        "--limit-files",
        type=int,
        default=None,
        help="Limit to first N tracks after sort (required for test100 mode)",
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
    logger.info("03_standardize_xyz.py START")
    logger.info("Args: %s", vars(args))

    if args.estimate_only:
        filtered = load_filtered_manifest(args.manifest, logger)
        print("Estimate only:")
        print(f"  manifest path:       {args.manifest}")
        print(f"  filter rows:         {len(filtered):,}")
        print(f"  instrument_class_pred breakdown:")
        for pred, n in filtered["instrument_class_pred"].value_counts().items():
            print(f"    {pred}: {n:,}")
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
    if args.run_label == "full" and len(filtered) != EXPECTED_FULL_ROWS:
        logger.error(
            "ABORTED: full-mode filter expected %d rows (%d sb + %d mb); got %d",
            EXPECTED_FULL_ROWS,
            EXPECTED_SB_ROWS,
            EXPECTED_MB_ROWS,
            len(filtered),
        )
        return 3

    work = filtered.sort_values("track_id").reset_index(drop=True)

    # Apply sample / limit selection.
    if args.sample_n_files is not None and len(work) > 2 * args.sample_n_files:
        # Stratified sample so the small mb minority is exercised.
        work = stratified_sample(work, n_per_class=args.sample_n_files, seed=42)
    elif args.sample_n_files is not None and len(work) > args.sample_n_files:
        rng = np.random.default_rng(42)
        idx = sorted(rng.choice(len(work), size=args.sample_n_files, replace=False).tolist())
        work = work.iloc[idx].reset_index(drop=True)
    if args.limit_files is not None:
        work = work.head(args.limit_files).reset_index(drop=True)

    logger.info(
        "Will standardize %d tracks (%d sb + %d mb)",
        len(work),
        int((work["instrument_class_pred"] == "singlebeam").sum()),
        int((work["instrument_class_pred"] == "multibeam").sum()),
    )
    DERIVED_SB_DIR.mkdir(parents=True, exist_ok=True)
    DERIVED_MB_DIR.mkdir(parents=True, exist_ok=True)

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
    logger.info("03_standardize_xyz.py DONE")

    print(f"Tracks standardized: {len(manifest_df):,}")
    if len(manifest_df):
        sb_n = int((manifest_df["instrument_class_pred"] == "singlebeam").sum())
        mb_n = int((manifest_df["instrument_class_pred"] == "multibeam").sum())
        print(f"  singlebeam: {sb_n:,}")
        print(f"  multibeam:  {mb_n:,}")
    print(f"Errors: {len(errors):,}")
    if "n_warnings" in manifest_df.columns and len(manifest_df):
        print(f"Per-point warnings (total): {int(manifest_df['n_warnings'].sum()):,}")
    print(f"Report: {paths['report_md']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
