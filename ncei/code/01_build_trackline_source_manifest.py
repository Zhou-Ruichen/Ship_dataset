#!/usr/bin/env python3
"""
01_build_trackline_source_manifest.py

Build the NCEI trackline source manifest for PR-E1.

Reads:
  - ncei/tracklines_nc/*.nc
  - ncei/tracklines_xyz/*.xyz

Writes (full mode):
  - ncei/manifests/trackline_source_manifest.parquet
  - ncei/manifests/trackline_source_manifest.tsv
  - ncei/manifests/trackline_classification_review.tsv
  - ncei/docs/trackline_source_manifest_report.md
  - ncei/output/logs/01_build_trackline_source_manifest.log
  - ncei/output/logs/01_build_trackline_source_manifest_errors.tsv

Writes (sample/test100 mode):
  - ncei/manifests/trackline_source_manifest_<run-label>.parquet
  - ncei/manifests/trackline_source_manifest_<run-label>.tsv
  - ncei/manifests/trackline_classification_review_<run-label>.tsv
  - ncei/docs/trackline_source_manifest_report_<run-label>.md

Usage:
    python -m ncei.code.01_build_trackline_source_manifest --run-label sample --sample-n-files 20 --overwrite
    python -m ncei.code.01_build_trackline_source_manifest --run-label test100 --limit-files 100 --overwrite
    python -m ncei.code.01_build_trackline_source_manifest --run-label full --confirm-full --overwrite
    python -m ncei.code.01_build_trackline_source_manifest --run-label full --confirm-full --estimate-only
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from _common.r2_classifier import (
    R2_BBOX_KM2_CUTOFF,
    R2_DENSITY_PPKM2_CUTOFF,
    R2_HARD_SB_POINTS,
    classify_from_arrays,
)

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent

NC_DIR = ROOT_DIR / "tracklines_nc"
XYZ_DIR = ROOT_DIR / "tracklines_xyz"
MANIFEST_DIR = ROOT_DIR / "manifests"
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"

VALID_RUN_LABELS = ("sample", "test100", "full")
XYZ_CHUNK_SIZE = 500_000
SMALL_REVIEW_BBOX_KM2_CUTOFF = R2_BBOX_KM2_CUTOFF
SMALL_REVIEW_DENSITY_PPKM2_CUTOFF = R2_DENSITY_PPKM2_CUTOFF


# ---------------------------------------------------------------------------
# Paths / atomic writes
# ---------------------------------------------------------------------------
def get_output_paths(run_label: str) -> dict[str, Path]:
    suffix = "" if run_label == "full" else f"_{run_label}"
    return {
        "manifest_pq": MANIFEST_DIR / f"trackline_source_manifest{suffix}.parquet",
        "manifest_tsv": MANIFEST_DIR / f"trackline_source_manifest{suffix}.tsv",
        "review_tsv": MANIFEST_DIR / f"trackline_classification_review{suffix}.tsv",
        "report_md": DOCS_DIR / f"trackline_source_manifest_report{suffix}.md",
        "log": LOG_DIR / f"01_build_trackline_source_manifest{suffix}.log",
        "errors_tsv": LOG_DIR / f"01_build_trackline_source_manifest_errors{suffix}.tsv",
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
    logger = logging.getLogger("ncei_trackline_manifest")
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
# Source discovery and geometry helpers
# ---------------------------------------------------------------------------
def normalize_track_id(path: Path) -> str:
    return path.stem.lower()


def classify_source_completeness(track_id: str, nc_ids: set[str], xyz_ids: set[str]) -> str:
    in_nc = track_id in nc_ids
    in_xyz = track_id in xyz_ids
    if in_nc and in_xyz:
        return "nc_xyz_intersect"
    if in_nc:
        return "nc_only"
    if in_xyz:
        return "xyz_only"
    raise ValueError(f"track_id not present in either source set: {track_id}")


def bbox_km2_from_bounds(lon_min: float, lon_max: float, lat_min: float, lat_max: float) -> float:
    if not all(np.isfinite([lon_min, lon_max, lat_min, lat_max])):
        return math.nan
    lon_span = lon_max - lon_min
    lat_span = lat_max - lat_min
    lat_mid = (lat_max + lat_min) / 2.0
    return lon_span * lat_span * math.cos(math.radians(lat_mid)) * (111.32 * 111.32)


def depth_sign(values: np.ndarray) -> str:
    finite = values[np.isfinite(values)]
    if len(finite) == 0:
        return "no_depth_values"
    positive = int(np.sum(finite > 0))
    negative = int(np.sum(finite < 0))
    nonzero = positive + negative
    if nonzero == 0:
        return "all_zero"
    if positive / nonzero >= 0.95:
        return "mostly_positive"
    if negative / nonzero >= 0.95:
        return "mostly_negative"
    return "mixed_sign"


def masked_to_float_array(values) -> np.ndarray:
    arr = np.ma.asarray(values)
    if arr.shape == ():
        arr = arr.reshape(1)
    arr = np.ma.filled(arr, np.nan)
    return np.asarray(arr, dtype=np.float64).reshape(-1)


def finite_minmax(values: np.ndarray) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if len(finite) == 0:
        return math.nan, math.nan
    return float(np.min(finite)), float(np.max(finite))


def read_nc_track(path: Path) -> dict:
    import netCDF4 as nc

    with nc.Dataset(path) as ds:
        vars_ = ds.variables
        lon = masked_to_float_array(vars_["lon"][:]) if "lon" in vars_ else np.array([], dtype=np.float64)
        lat = masked_to_float_array(vars_["lat"][:]) if "lat" in vars_ else np.array([], dtype=np.float64)
        finite_xy = np.isfinite(lon) & np.isfinite(lat)
        lon = lon[finite_xy]
        lat = lat[finite_xy]

        if "depth" in vars_:
            depth = masked_to_float_array(vars_["depth"][:])
        else:
            depth = np.array([], dtype=np.float64)

        n_points = int(len(lon))
        lon_min, lon_max = finite_minmax(lon)
        lat_min, lat_max = finite_minmax(lat)

        has_time = "time" in vars_ and getattr(vars_["time"], "size", 0) > 0
        has_depth = "depth" in vars_ and np.isfinite(depth).any()
        has_gobs = "gobs" in vars_ and np.isfinite(masked_to_float_array(vars_["gobs"][:])).any()
        has_faa = "faa" in vars_ and np.isfinite(masked_to_float_array(vars_["faa"][:])).any()

        survey_id = getattr(ds, "Survey_Identifier", None)
        source_author = getattr(ds, "Author", None)

    return {
        "n_points": n_points,
        "lon": lon,
        "lat": lat,
        "bbox_lon_min": lon_min,
        "bbox_lon_max": lon_max,
        "bbox_lat_min": lat_min,
        "bbox_lat_max": lat_max,
        "has_time": bool(has_time),
        "has_depth": bool(has_depth),
        "has_gobs": bool(has_gobs),
        "has_faa": bool(has_faa),
        "depth_sign_raw": depth_sign(depth),
        "source_archive": "NCEI_singlebeam_tracks_raw_2018files.zip; converted by 李杨; forwarded by 孙明智",
        "source_author": source_author,
        "survey_id": survey_id,
    }


def read_xyz_track(path: Path) -> dict:
    n_points = 0
    lon_min = lat_min = depth_min = math.inf
    lon_max = lat_max = depth_max = -math.inf
    positive = negative = zero = finite_depth = 0
    lon_parts: list[np.ndarray] = []
    lat_parts: list[np.ndarray] = []

    first_line = path.open("r", encoding="utf-8", errors="replace").readline().strip().upper()
    has_header = all(name in first_line for name in ("LON", "LAT"))
    read_kwargs = {
        "chunksize": XYZ_CHUNK_SIZE,
        "header": 0 if has_header else None,
        "names": None if has_header else ["LON", "LAT", "CORR_DEPTH"],
        "usecols": ["LON", "LAT", "CORR_DEPTH"],
    }

    for chunk in pd.read_csv(path, **read_kwargs):
        lon = pd.to_numeric(chunk["LON"], errors="coerce").to_numpy(dtype=np.float64)
        lat = pd.to_numeric(chunk["LAT"], errors="coerce").to_numpy(dtype=np.float64)
        depth = pd.to_numeric(chunk["CORR_DEPTH"], errors="coerce").to_numpy(dtype=np.float64)
        finite_xy = np.isfinite(lon) & np.isfinite(lat)
        lon = lon[finite_xy]
        lat = lat[finite_xy]
        depth_xy = depth[finite_xy]

        n_points += int(len(lon))
        if len(lon):
            lon_min = min(lon_min, float(np.min(lon)))
            lon_max = max(lon_max, float(np.max(lon)))
            lat_min = min(lat_min, float(np.min(lat)))
            lat_max = max(lat_max, float(np.max(lat)))
            lon_parts.append(lon)
            lat_parts.append(lat)

        finite = depth_xy[np.isfinite(depth_xy)]
        if len(finite):
            finite_depth += int(len(finite))
            positive += int(np.sum(finite > 0))
            negative += int(np.sum(finite < 0))
            zero += int(np.sum(finite == 0))
            depth_min = min(depth_min, float(np.min(finite)))
            depth_max = max(depth_max, float(np.max(finite)))

    if n_points == 0:
        lon = np.array([], dtype=np.float64)
        lat = np.array([], dtype=np.float64)
        lon_min = lon_max = lat_min = lat_max = math.nan
    else:
        lon = np.concatenate(lon_parts) if lon_parts else np.array([], dtype=np.float64)
        lat = np.concatenate(lat_parts) if lat_parts else np.array([], dtype=np.float64)

    if finite_depth == 0:
        sign = "no_depth_values"
    else:
        nonzero_depth = positive + negative
        if nonzero_depth == 0:
            sign = "all_zero"
        elif positive / nonzero_depth >= 0.95:
            sign = "mostly_positive"
        elif negative / nonzero_depth >= 0.95:
            sign = "mostly_negative"
        else:
            sign = "mixed_sign"

    return {
        "n_points": n_points,
        "lon": lon,
        "lat": lat,
        "bbox_lon_min": lon_min,
        "bbox_lon_max": lon_max,
        "bbox_lat_min": lat_min,
        "bbox_lat_max": lat_max,
        "has_time": False,
        "has_depth": finite_depth > 0,
        "has_gobs": False,
        "has_faa": False,
        "depth_sign_raw": sign,
        "source_archive": "total_tracklines_xyz.zip; provider 安德超",
        "source_author": None,
        "survey_id": None,
        "depth_min_raw": depth_min if finite_depth else math.nan,
        "depth_max_raw": depth_max if finite_depth else math.nan,
    }


# ---------------------------------------------------------------------------
# Classification review
# ---------------------------------------------------------------------------
def review_reason(result, n_points: int, bbox_area_km2: float, density_ppkm2: float) -> str:
    reasons: list[str] = []
    if result.label == "mb":
        reasons.append(result.reason)
    if n_points < R2_HARD_SB_POINTS and n_points >= 1_000:
        compact = np.isfinite(bbox_area_km2) and bbox_area_km2 < SMALL_REVIEW_BBOX_KM2_CUTOFF
        dense = np.isfinite(density_ppkm2) and density_ppkm2 > SMALL_REVIEW_DENSITY_PPKM2_CUTOFF
        if compact and dense:
            reasons.append("review_multibeam_candidate")
        elif dense:
            reasons.append("review_high_density_small_track")
    if result.reason == "borderline_default_sb":
        reasons.append("borderline_default_singlebeam")
    return ";".join(dict.fromkeys(reasons))


def process_one(path: Path, source_type: str, nc_ids: set[str], xyz_ids: set[str]) -> dict:
    track_id = normalize_track_id(path)
    if source_type == "ncei_nc":
        rec = read_nc_track(path)
    elif source_type == "ncei_xyz":
        rec = read_xyz_track(path)
    else:
        raise ValueError(source_type)

    if rec["n_points"] <= 0:
        raise ValueError(f"empty track after lon/lat filtering: {path}")

    bbox_area = bbox_km2_from_bounds(
        rec["bbox_lon_min"], rec["bbox_lon_max"], rec["bbox_lat_min"], rec["bbox_lat_max"]
    )
    density = rec["n_points"] / bbox_area if np.isfinite(bbox_area) and bbox_area > 0 else math.inf
    r2 = classify_from_arrays(rec.pop("lon"), rec.pop("lat"), points=rec["n_points"])
    pred = "multibeam" if r2.label == "mb" else "singlebeam"
    reason = review_reason(r2, rec["n_points"], bbox_area, density)

    source_path = str(path.relative_to(ROOT_DIR))
    out = {
        "track_id": track_id,
        "source_type": source_type,
        "source_completeness": classify_source_completeness(track_id, nc_ids, xyz_ids),
        "source_path": source_path,
        "source_archive": rec.pop("source_archive"),
        "n_points": rec.pop("n_points"),
        "bbox_lon_min": rec.pop("bbox_lon_min"),
        "bbox_lon_max": rec.pop("bbox_lon_max"),
        "bbox_lat_min": rec.pop("bbox_lat_min"),
        "bbox_lat_max": rec.pop("bbox_lat_max"),
        "bbox_area_km2": bbox_area,
        "point_density_km2": density,
        "has_time": rec.pop("has_time"),
        "has_depth": rec.pop("has_depth"),
        "has_gobs": rec.pop("has_gobs"),
        "has_faa": rec.pop("has_faa"),
        "depth_sign_raw": rec.pop("depth_sign_raw"),
        "instrument_class_pred": pred,
        "classification_rule": r2.reason,
        "classification_review": bool(reason),
        "review_reason": reason,
        "manual_override": "",
        "source_author": rec.pop("source_author", None),
        "survey_id": rec.pop("survey_id", None),
        "depth_min_raw": rec.pop("depth_min_raw", math.nan),
        "depth_max_raw": rec.pop("depth_max_raw", math.nan),
    }
    return out


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
            else:
                vals.append(str(val))
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    return lines


def make_report(df: pd.DataFrame, errors: list[dict], run_label: str, elapsed_s: float) -> str:
    lines: list[str] = []
    lines.append("# NCEI Trackline Source Manifest Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Run label: `{run_label}`")
    lines.append(f"Elapsed: {elapsed_s:.1f}s")
    lines.append(f"Rows: {len(df):,}")
    lines.append(f"Errors: {len(errors):,}")
    lines.append("")

    if len(df) == 0:
        lines.append("No rows generated.")
        return "\n".join(lines)

    lines.append("## Source counts")
    lines.append("")
    counts = df.groupby(["source_type", "source_completeness"], dropna=False).size().reset_index(name="tracks")
    lines.extend(markdown_table(counts))

    lines.append("## Instrument predictions")
    lines.append("")
    pred = df.groupby(["source_type", "instrument_class_pred"], dropna=False).size().reset_index(name="tracks")
    lines.extend(markdown_table(pred))

    lines.append("## Field availability")
    lines.append("")
    field_rows = []
    for source_type, sub in df.groupby("source_type"):
        row = {"source_type": source_type, "tracks": len(sub)}
        for col in ["has_time", "has_depth", "has_gobs", "has_faa"]:
            row[col] = int(sub[col].sum())
        field_rows.append(row)
    lines.extend(markdown_table(pd.DataFrame(field_rows)))

    lines.append("## Raw depth sign diagnosis")
    lines.append("")
    sign = df.groupby(["source_type", "depth_sign_raw"], dropna=False).size().reset_index(name="tracks")
    lines.extend(markdown_table(sign))
    lines.append("> Note: MGD77+ corrected bathymetry is expected to be positive below sea level; NCEI XYZ documentation says exported XYZ depths may be negative. This report records observed raw signs and does not normalize depths.")
    lines.append("")

    lines.append("## Classification review cases")
    lines.append("")
    review = df[df["classification_review"]].sort_values(["instrument_class_pred", "n_points"], ascending=[True, False])
    lines.append(f"Review rows: {len(review):,}")
    lines.append("")
    review_cols = ["track_id", "source_type", "n_points", "bbox_area_km2", "point_density_km2", "instrument_class_pred", "classification_rule", "review_reason"]
    lines.extend(markdown_table(review[review_cols], max_rows=30))

    lines.append("## Largest tracks")
    lines.append("")
    largest_cols = ["track_id", "source_type", "source_completeness", "n_points", "bbox_area_km2", "point_density_km2", "instrument_class_pred", "classification_rule"]
    lines.extend(markdown_table(df.sort_values("n_points", ascending=False)[largest_cols], max_rows=20))

    if errors:
        lines.append("## Errors")
        lines.append("")
        lines.extend(markdown_table(pd.DataFrame(errors), max_rows=20))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Build NCEI trackline source manifest (PR-E1)")
    parser.add_argument("--run-label", choices=VALID_RUN_LABELS, default="sample")
    parser.add_argument("--sample-n-files", type=int, default=None, help="Randomly sample N files per source type in sample mode")
    parser.add_argument("--limit-files", type=int, default=None, help="Limit to first N files per source type")
    parser.add_argument("--confirm-full", action="store_true", help="Required when --run-label=full")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--estimate-only", action="store_true", help="Print file counts and exit without writing")
    args = parser.parse_args()

    paths = get_output_paths(args.run_label)
    logger = setup_logging(paths["log"])
    t0 = datetime.now()

    logger.info("=" * 60)
    logger.info("01_build_trackline_source_manifest.py START")
    logger.info("Args: %s", vars(args))

    if args.run_label == "full" and not args.confirm_full:
        logger.error("ABORTED: --run-label=full requires --confirm-full")
        return 2

    if (
        args.run_label == "sample"
        and not args.estimate_only
        and args.sample_n_files is None
        and args.limit_files is None
    ):
        logger.error("ABORTED: sample mode requires --sample-n-files or --limit-files")
        return 2

    output_files = [paths["manifest_pq"], paths["manifest_tsv"], paths["review_tsv"], paths["report_md"]]
    if not args.overwrite and not args.estimate_only:
        existing = [p for p in output_files if p.exists()]
        if existing:
            logger.error("ABORTED: outputs exist; use --overwrite. Existing: %s", existing)
            return 2

    nc_files = sorted(NC_DIR.glob("*.nc"))
    xyz_files = sorted(XYZ_DIR.glob("*.xyz"))
    nc_ids = {normalize_track_id(p) for p in nc_files}
    xyz_ids = {normalize_track_id(p) for p in xyz_files}

    logger.info("Discovered %d .nc files and %d .xyz files", len(nc_files), len(xyz_files))
    logger.info("Overlap: %d; nc_only: %d; xyz_only: %d", len(nc_ids & xyz_ids), len(nc_ids - xyz_ids), len(xyz_ids - nc_ids))

    if args.estimate_only:
        print("Estimate only:")
        print(f"  nc files:  {len(nc_files):,}")
        print(f"  xyz files: {len(xyz_files):,}")
        print(f"  overlap:   {len(nc_ids & xyz_ids):,}")
        print(f"  nc_only:   {len(nc_ids - xyz_ids):,}")
        print(f"  xyz_only:  {len(xyz_ids - nc_ids):,}")
        return 0

    if args.sample_n_files is not None:
        rng = np.random.default_rng(42)
        if len(nc_files) > args.sample_n_files:
            nc_files = sorted(rng.choice(nc_files, size=args.sample_n_files, replace=False).tolist())
        if len(xyz_files) > args.sample_n_files:
            xyz_files = sorted(rng.choice(xyz_files, size=args.sample_n_files, replace=False).tolist())
    if args.limit_files is not None:
        nc_files = nc_files[:args.limit_files]
        xyz_files = xyz_files[:args.limit_files]

    logger.info("Selected %d .nc files and %d .xyz files", len(nc_files), len(xyz_files))

    rows: list[dict] = []
    errors: list[dict] = []
    work: list[tuple[Path, str]] = [(p, "ncei_nc") for p in nc_files] + [(p, "ncei_xyz") for p in xyz_files]
    for idx, (path, source_type) in enumerate(work, start=1):
        if idx == 1 or idx % 100 == 0:
            logger.info("Processing %d/%d: %s", idx, len(work), path.name)
        try:
            rows.append(process_one(path, source_type, nc_ids, xyz_ids))
        except Exception as exc:  # per-file isolation required for pipeline scripts
            logger.exception("Error processing %s", path)
            errors.append({"source_type": source_type, "source_path": str(path.relative_to(ROOT_DIR)), "error": repr(exc)})

    df = pd.DataFrame(rows)
    if len(df):
        df = df.sort_values(["track_id", "source_type"]).reset_index(drop=True)

    elapsed_s = (datetime.now() - t0).total_seconds()
    review_cols = [
        "track_id", "source_type", "n_points", "bbox_area_km2", "point_density_km2",
        "instrument_class_pred", "classification_rule", "review_reason", "manual_override",
    ]
    review_df = df[df["classification_review"]][review_cols].copy() if len(df) else pd.DataFrame(columns=review_cols)

    atomic_write_parquet(df, paths["manifest_pq"])
    if args.run_label == "full":
        tsv_df = df
    else:
        tsv_df = df.head(500).copy()
    atomic_write_tsv(tsv_df, paths["manifest_tsv"])
    atomic_write_tsv(review_df, paths["review_tsv"])
    atomic_write_text(make_report(df, errors, args.run_label, elapsed_s), paths["report_md"])
    atomic_write_tsv(pd.DataFrame(errors), paths["errors_tsv"])

    logger.info("Wrote %s (%d rows)", paths["manifest_pq"], len(df))
    logger.info("Wrote %s (%d rows)", paths["review_tsv"], len(review_df))
    logger.info("Errors: %d", len(errors))
    logger.info("Elapsed: %.1fs", elapsed_s)
    logger.info("01_build_trackline_source_manifest.py DONE")

    print(f"Manifest rows: {len(df):,}")
    print(f"Review rows: {len(review_df):,}")
    print(f"Errors: {len(errors):,}")
    print(f"Report: {paths['report_md']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
