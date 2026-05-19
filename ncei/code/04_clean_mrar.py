#!/usr/bin/env python3
"""
04_clean_mrar.py

PR-F — Clean the regional processed-multibeam point cloud unpacked from
`ncei/archive/zhoushuai_processed_M/*.txt` (3 quadrant files, ~113.4M
total rows; provider 周帅, see that dir's SOURCE.md for the full
provenance and anomaly description).

Per PRD Q3, classify each row by sign:
  - `depth_raw > 0`            → land point (mixed-in DEM / sentinel)
                                 → routed to `land_mask.parquet`
                                 (preserved as labeled artifact).
  - `depth_raw < -11,500`      → nodata sentinel (e.g. -30,990)
                                 → dropped entirely.
  - `-11,500 ≤ depth_raw ≤ 0`  → bathymetry; kept and converted to the
                                 positive-down convention shared with
                                 02_standardize_singlebeam.py + 03_*.py.

Sign convention: M.rar depths are NEGATIVE-DOWN in the raw input
(opposite of NCEI .xyz which is positive-down). The cleaning step
flips sign so the output `depth_m_positive_down` column matches the
nc/xyz standardization schema.

Inputs:
  - ncei/archive/zhoushuai_processed_M/0-180E-0-85N.txt
  - ncei/archive/zhoushuai_processed_M/0-90W-0-85S.txt
  - ncei/archive/zhoushuai_processed_M/90-180W-0-85S.txt
  (tab-separated, no header, 3 columns: lon, lat, depth)

Outputs (full mode):
  - ncei/archive/zhoushuai_processed_M/bathymetry_points.parquet
      (16-column schema, union-compatible with 02/03)
  - ncei/archive/zhoushuai_processed_M/land_mask.parquet
      (simpler 7-column schema, land elevation artifact)
  - ncei/archive/zhoushuai_processed_M/cleaning_audit.parquet
      (per-quadrant + TOTALS counts)
  - ncei/docs/mrar_cleaning_report.md
  - ncei/output/logs/04_clean_mrar.log

Outputs (sample mode): suffix all of the above with `_sample` except the
log uses the same suffix. Sample mode reads only the first N rows per
quadrant.

Usage:
    python -m ncei.code.04_clean_mrar --estimate-only
    python -m ncei.code.04_clean_mrar --run-label sample --sample-n-rows 100000 --overwrite
    python -m ncei.code.04_clean_mrar --run-label full --confirm-full --overwrite
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent

MRAR_DIR = ROOT_DIR / "archive" / "zhoushuai_processed_M"
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"

VALID_RUN_LABELS = ("sample", "full")
CLEANING_VERSION = "mrar_v0.1.0"

# Cleaning constants — see module docstring + PRD Q3.
DEPTH_CLIP_LOWER_M = -11500.0  # Anything below this is sentinel.
LAND_DEPTH_CUTOFF_M = 0.0      # Anything above this is land elevation.

CHUNK_SIZE = 2_000_000

# Per-quadrant input files (resolved at runtime).
QUADRANT_FILES = (
    "0-180E-0-85N.txt",
    "0-90W-0-85S.txt",
    "90-180W-0-85S.txt",
)

# Bathymetry schema — column order MUST match
# 02_standardize_singlebeam.py / 03_standardize_xyz.py exactly so the
# three sides can be unioned downstream.
BATHY_COLUMNS = [
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

# Land mask schema — these rows are NOT bathymetry, so a simpler schema.
LAND_COLUMNS = [
    "track_id",
    "lon_raw",
    "lat_raw",
    "lon",
    "lat",
    "elevation_m",
    "source_type",
    "standardization_version",
]

BATHY_ARROW_SCHEMA = pa.schema(
    [
        pa.field("source_type", pa.string()),
        pa.field("track_id", pa.string()),
        pa.field("point_index_in_track", pa.int64()),
        pa.field("time", pa.timestamp("ns")),
        pa.field("lon_raw", pa.float64()),
        pa.field("lat_raw", pa.float64()),
        pa.field("lon", pa.float64()),
        pa.field("lat", pa.float64()),
        pa.field("depth_raw", pa.float64()),
        pa.field("depth_m_positive_down", pa.float64()),
        pa.field("elev_m", pa.float64()),
        pa.field("gobs", pa.float64()),
        pa.field("faa", pa.float64()),
        pa.field("source_completeness", pa.string()),
        pa.field("instrument_class_pred", pa.string()),
        pa.field("standardization_version", pa.string()),
    ]
)

LAND_ARROW_SCHEMA = pa.schema(
    [
        pa.field("track_id", pa.string()),
        pa.field("lon_raw", pa.float64()),
        pa.field("lat_raw", pa.float64()),
        pa.field("lon", pa.float64()),
        pa.field("lat", pa.float64()),
        pa.field("elevation_m", pa.float64()),
        pa.field("source_type", pa.string()),
        pa.field("standardization_version", pa.string()),
    ]
)


# ---------------------------------------------------------------------------
# Paths / atomic writes
# ---------------------------------------------------------------------------
def get_output_paths(run_label: str) -> dict[str, Path]:
    suffix = "" if run_label == "full" else f"_{run_label}"
    return {
        "bathy_pq": MRAR_DIR / f"bathymetry_points{suffix}.parquet",
        "land_pq": MRAR_DIR / f"land_mask{suffix}.parquet",
        "audit_pq": MRAR_DIR / f"cleaning_audit{suffix}.parquet",
        "report_md": DOCS_DIR / f"mrar_cleaning_report{suffix}.md",
        "log": LOG_DIR / f"04_clean_mrar{suffix}.log",
    }


def atomic_write_parquet(df: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    df.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, target)


def atomic_write_text(text: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)


def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ncei_clean_mrar")
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
# Geometry helpers
# ---------------------------------------------------------------------------
def normalize_lon(lon: np.ndarray) -> np.ndarray:
    """Wrap any lon > 180 to (-180, 180]. Leaves NaNs alone.

    M.rar files include lon up to 180.003 (e.g. 0-180E-0-85N.txt); the
    handful of rows just past 180 get pulled back into (-180, 180] for
    symmetric handling with nc/xyz.
    """
    out = lon.copy()
    mask = np.isfinite(out) & (out > 180.0)
    if mask.any():
        out[mask] = out[mask] - 360.0
    return out


def estimate_rows(path: Path, sample_lines: int = 1024) -> int:
    """Estimate row count from file size + average line length over a head sample.

    Fast: O(file size / sample window) for the line-length sample,
    O(1) for size lookup.
    """
    size = path.stat().st_size
    with path.open("rb") as fh:
        head = fh.read(64 * 1024)
    lines = head.splitlines()
    if len(lines) < 2:
        return 0
    sample = lines[: min(sample_lines, len(lines))]
    avg_len = sum(len(line) + 1 for line in sample) / len(sample)
    if avg_len <= 0:
        return 0
    return int(size / avg_len)


# ---------------------------------------------------------------------------
# Per-quadrant cleaning
# ---------------------------------------------------------------------------
def make_bathy_table(
    quadrant_name: str,
    lon_raw: np.ndarray,
    lat_raw: np.ndarray,
    depth_raw: np.ndarray,
    point_index_start: int,
) -> pd.DataFrame:
    """Build a 16-col bathymetry DataFrame for a chunk's bathymetry rows."""
    n = lon_raw.size
    lon = normalize_lon(lon_raw)
    lat = lat_raw.copy()
    depth_m_positive_down = -depth_raw  # flip sign: raw is negative-down
    elev_m = depth_raw.astype(np.float64)  # already in elev convention

    point_index = np.arange(
        point_index_start, point_index_start + n, dtype=np.int64
    )
    time_arr = np.full(n, np.datetime64("NaT"), dtype="datetime64[ns]")
    gobs = np.full(n, np.nan, dtype=np.float64)
    faa = np.full(n, np.nan, dtype=np.float64)

    data = {
        "source_type": np.array(["mrar_zhoushuai"] * n, dtype=object),
        "track_id": np.array([f"mrar_{quadrant_name}"] * n, dtype=object),
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
        "source_completeness": np.array(["mrar_regional"] * n, dtype=object),
        "instrument_class_pred": np.array(["multibeam"] * n, dtype=object),
        "standardization_version": np.array([CLEANING_VERSION] * n, dtype=object),
    }
    df = pd.DataFrame(data, columns=BATHY_COLUMNS)
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    return df


def make_land_table(
    quadrant_name: str,
    lon_raw: np.ndarray,
    lat_raw: np.ndarray,
    depth_raw: np.ndarray,
) -> pd.DataFrame:
    """Build a land-mask DataFrame from rows with depth_raw > 0."""
    n = lon_raw.size
    lon = normalize_lon(lon_raw)
    lat = lat_raw.copy()
    data = {
        "track_id": np.array([f"mrar_{quadrant_name}"] * n, dtype=object),
        "lon_raw": lon_raw,
        "lat_raw": lat_raw,
        "lon": lon,
        "lat": lat,
        "elevation_m": depth_raw.astype(np.float64),
        "source_type": np.array(["mrar_zhoushuai"] * n, dtype=object),
        "standardization_version": np.array([CLEANING_VERSION] * n, dtype=object),
    }
    return pd.DataFrame(data, columns=LAND_COLUMNS)


def clean_one_quadrant(
    path: Path,
    quadrant_name: str,
    bathy_writer: pq.ParquetWriter,
    land_writer: pq.ParquetWriter,
    sample_n_rows: int | None,
    point_index_start: int,
    logger: logging.Logger,
) -> tuple[dict, int]:
    """Stream-clean one quadrant file.

    Returns (audit_summary_dict, n_bathy_rows_written).
    """
    audit = {
        "quadrant": quadrant_name,
        "rows_in": 0,
        "rows_land": 0,
        "rows_nodata": 0,
        "rows_bathymetry": 0,
        "rows_nan_depth": 0,
        "depth_min_bathy_raw": float("inf"),
        "depth_max_bathy_raw": float("-inf"),
        "lon_min": float("inf"),
        "lon_max": float("-inf"),
        "lat_min": float("inf"),
        "lat_max": float("-inf"),
        "depth_clip_lower_m": DEPTH_CLIP_LOWER_M,
        "land_depth_cutoff_m": LAND_DEPTH_CUTOFF_M,
        "cleaning_version": CLEANING_VERSION,
    }

    n_bathy_written = 0
    track_point_idx = point_index_start

    # Sample mode: nrows kwarg caps total read; pandas still chunks it.
    read_kwargs: dict = {
        "sep": "\t",
        "header": None,
        "names": ["lon", "lat", "depth"],
        "usecols": ["lon", "lat", "depth"],
        "chunksize": CHUNK_SIZE,
        "dtype": {"lon": np.float64, "lat": np.float64, "depth": np.float64},
    }
    if sample_n_rows is not None:
        read_kwargs["nrows"] = sample_n_rows

    chunk_idx = 0
    for chunk in pd.read_csv(path, **read_kwargs):
        chunk_idx += 1
        n_in = len(chunk)
        if n_in == 0:
            continue

        lon = chunk["lon"].to_numpy(dtype=np.float64)
        lat = chunk["lat"].to_numpy(dtype=np.float64)
        depth = chunk["depth"].to_numpy(dtype=np.float64)

        # Geometry rollup (use finite values only).
        finite_xy = np.isfinite(lon) & np.isfinite(lat)
        if finite_xy.any():
            audit["lon_min"] = min(audit["lon_min"], float(np.min(lon[finite_xy])))
            audit["lon_max"] = max(audit["lon_max"], float(np.max(lon[finite_xy])))
            audit["lat_min"] = min(audit["lat_min"], float(np.min(lat[finite_xy])))
            audit["lat_max"] = max(audit["lat_max"], float(np.max(lat[finite_xy])))

        finite_depth = np.isfinite(depth)
        nan_depth = int((~finite_depth).sum())

        # Classification masks — only operate on rows with finite depth.
        # Rows with NaN depth are counted but not routed anywhere
        # (they cannot be classified as land vs bathy vs nodata).
        land_mask = finite_depth & (depth > LAND_DEPTH_CUTOFF_M)
        nodata_mask = finite_depth & (depth < DEPTH_CLIP_LOWER_M)
        bathy_mask = finite_depth & (depth <= LAND_DEPTH_CUTOFF_M) & (depth >= DEPTH_CLIP_LOWER_M)

        audit["rows_in"] += int(n_in)
        audit["rows_land"] += int(land_mask.sum())
        audit["rows_nodata"] += int(nodata_mask.sum())
        audit["rows_bathymetry"] += int(bathy_mask.sum())
        audit["rows_nan_depth"] += nan_depth

        # Bathymetry depth range tracker.
        if bathy_mask.any():
            audit["depth_min_bathy_raw"] = min(
                audit["depth_min_bathy_raw"], float(np.min(depth[bathy_mask]))
            )
            audit["depth_max_bathy_raw"] = max(
                audit["depth_max_bathy_raw"], float(np.max(depth[bathy_mask]))
            )

        # Write bathy partition.
        if bathy_mask.any():
            bathy_df = make_bathy_table(
                quadrant_name=quadrant_name,
                lon_raw=lon[bathy_mask],
                lat_raw=lat[bathy_mask],
                depth_raw=depth[bathy_mask],
                point_index_start=track_point_idx,
            )
            track_point_idx += len(bathy_df)
            n_bathy_written += len(bathy_df)
            table = pa.Table.from_pandas(
                bathy_df, schema=BATHY_ARROW_SCHEMA, preserve_index=False
            )
            bathy_writer.write_table(table)

        # Write land partition.
        if land_mask.any():
            land_df = make_land_table(
                quadrant_name=quadrant_name,
                lon_raw=lon[land_mask],
                lat_raw=lat[land_mask],
                depth_raw=depth[land_mask],
            )
            table = pa.Table.from_pandas(
                land_df, schema=LAND_ARROW_SCHEMA, preserve_index=False
            )
            land_writer.write_table(table)

        if chunk_idx % 5 == 0 or chunk_idx == 1:
            logger.info(
                "  %s chunk %d: in=%d land=%d nodata=%d bathy=%d (cum bathy=%d)",
                quadrant_name,
                chunk_idx,
                n_in,
                int(land_mask.sum()),
                int(nodata_mask.sum()),
                int(bathy_mask.sum()),
                n_bathy_written,
            )

    # Sentinel-clean rolled values (replace inf with NaN for unused fields).
    for key in ("depth_min_bathy_raw", "depth_max_bathy_raw", "lon_min", "lon_max", "lat_min", "lat_max"):
        v = audit[key]
        if not np.isfinite(v):
            audit[key] = float("nan")

    return audit, n_bathy_written


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
    audit_df: pd.DataFrame,
    run_label: str,
    elapsed_s: float,
    bathy_out_path: Path,
    land_out_path: Path,
    audit_out_path: Path,
) -> str:
    suffix = "" if run_label == "full" else f"_{run_label}"
    lines: list[str] = []
    lines.append("# M.rar Cleaning Report (PR-F)")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Run label: `{run_label}`")
    lines.append(f"Cleaning version: `{CLEANING_VERSION}`")
    lines.append(f"Elapsed: {elapsed_s:.1f}s")
    lines.append("")
    lines.append("## Rules")
    lines.append("")
    lines.append(f"- `depth_raw > {LAND_DEPTH_CUTOFF_M:.0f}` → land mask (sidecar).")
    lines.append(
        f"- `depth_raw < {DEPTH_CLIP_LOWER_M:.0f}` → nodata sentinel, dropped."
    )
    lines.append(
        f"- `{DEPTH_CLIP_LOWER_M:.0f} ≤ depth_raw ≤ {LAND_DEPTH_CUTOFF_M:.0f}` → "
        "bathymetry, kept; sign-flipped to positive-down."
    )
    lines.append("")
    lines.append("## Per-quadrant cleaning split")
    lines.append("")
    cols = [
        "quadrant",
        "rows_in",
        "rows_land",
        "rows_nodata",
        "rows_bathymetry",
        "rows_nan_depth",
    ]
    lines.extend(markdown_table(audit_df[cols]))
    lines.append("## Per-quadrant ranges")
    lines.append("")
    cols = [
        "quadrant",
        "lon_min",
        "lon_max",
        "lat_min",
        "lat_max",
        "depth_min_bathy_raw",
        "depth_max_bathy_raw",
    ]
    lines.extend(markdown_table(audit_df[cols]))
    lines.append("## Output paths")
    lines.append("")
    lines.append(f"- Bathymetry parquet: `{bathy_out_path.relative_to(SCRIPT_DIR.parent.parent)}`")
    lines.append(f"- Land mask parquet: `{land_out_path.relative_to(SCRIPT_DIR.parent.parent)}`")
    lines.append(f"- Audit parquet: `{audit_out_path.relative_to(SCRIPT_DIR.parent.parent)}`")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clean M.rar regional multibeam point cloud (PR-F)"
    )
    parser.add_argument(
        "--run-label",
        choices=VALID_RUN_LABELS,
        default="sample",
        help="sample = read first N rows per quadrant (--sample-n-rows N); "
        "full = read every row (--confirm-full required).",
    )
    parser.add_argument(
        "--sample-n-rows",
        type=int,
        default=None,
        help="Required for sample mode: first N rows read per quadrant.",
    )
    parser.add_argument(
        "--confirm-full",
        action="store_true",
        help="Required when --run-label=full.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output parquets / report.",
    )
    parser.add_argument(
        "--estimate-only",
        action="store_true",
        help="Print per-quadrant file sizes + estimated row counts; exit.",
    )
    args = parser.parse_args()

    paths = get_output_paths(args.run_label)
    logger = setup_logging(paths["log"])
    t0 = datetime.now()

    logger.info("=" * 60)
    logger.info("04_clean_mrar.py START")
    logger.info("Args: %s", vars(args))

    quadrant_paths = [(name, MRAR_DIR / name) for name in QUADRANT_FILES]
    for name, p in quadrant_paths:
        if not p.exists():
            logger.error("ABORTED: missing input file: %s", p)
            return 2

    if args.estimate_only:
        print("Estimate only:")
        total = 0
        for name, p in quadrant_paths:
            size = p.stat().st_size
            est = estimate_rows(p)
            total += est
            print(f"  {name}: {size:,} bytes, ~{est:,} rows")
        print(f"  TOTAL (est): ~{total:,} rows")
        return 0

    if args.run_label == "full" and not args.confirm_full:
        logger.error("ABORTED: --run-label=full requires --confirm-full")
        return 2

    if args.run_label == "sample" and args.sample_n_rows is None:
        logger.error("ABORTED: sample mode requires --sample-n-rows")
        return 2

    output_files = [paths["bathy_pq"], paths["land_pq"], paths["audit_pq"], paths["report_md"]]
    if not args.overwrite:
        existing = [p for p in output_files if p.exists()]
        if existing:
            logger.error("ABORTED: outputs exist; use --overwrite. Existing: %s", existing)
            return 2

    MRAR_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # Stream-write parquet via ParquetWriter so we don't materialize the
    # full ~3-4 GB bathymetry table in memory. Use atomic `.tmp` + rename
    # at the end.
    bathy_tmp = paths["bathy_pq"].with_suffix(paths["bathy_pq"].suffix + ".tmp")
    land_tmp = paths["land_pq"].with_suffix(paths["land_pq"].suffix + ".tmp")
    bathy_writer: pq.ParquetWriter | None = None
    land_writer: pq.ParquetWriter | None = None
    summaries: list[dict] = []
    n_bathy_total = 0

    try:
        bathy_writer = pq.ParquetWriter(bathy_tmp, BATHY_ARROW_SCHEMA, compression="snappy")
        land_writer = pq.ParquetWriter(land_tmp, LAND_ARROW_SCHEMA, compression="snappy")

        point_idx_running = 0
        for name, p in quadrant_paths:
            logger.info("Quadrant %s ← %s", name, p)
            try:
                audit, n_bathy = clean_one_quadrant(
                    path=p,
                    quadrant_name=name,
                    bathy_writer=bathy_writer,
                    land_writer=land_writer,
                    sample_n_rows=args.sample_n_rows,
                    point_index_start=point_idx_running,
                    logger=logger,
                )
            except Exception as exc:
                # Per-quadrant isolation: record the failure, keep going so
                # the other quadrants still ship.
                logger.exception("Error processing quadrant %s", name)
                audit = {
                    "quadrant": name,
                    "rows_in": 0,
                    "rows_land": 0,
                    "rows_nodata": 0,
                    "rows_bathymetry": 0,
                    "rows_nan_depth": 0,
                    "depth_min_bathy_raw": float("nan"),
                    "depth_max_bathy_raw": float("nan"),
                    "lon_min": float("nan"),
                    "lon_max": float("nan"),
                    "lat_min": float("nan"),
                    "lat_max": float("nan"),
                    "depth_clip_lower_m": DEPTH_CLIP_LOWER_M,
                    "land_depth_cutoff_m": LAND_DEPTH_CUTOFF_M,
                    "cleaning_version": CLEANING_VERSION,
                    "error": repr(exc),
                }
                n_bathy = 0

            point_idx_running += n_bathy
            n_bathy_total += n_bathy
            summaries.append(audit)
            logger.info(
                "  %s: in=%d land=%d nodata=%d bathy=%d nan=%d",
                name,
                audit["rows_in"],
                audit["rows_land"],
                audit["rows_nodata"],
                audit["rows_bathymetry"],
                audit["rows_nan_depth"],
            )
    finally:
        if bathy_writer is not None:
            bathy_writer.close()
        if land_writer is not None:
            land_writer.close()

    # Commit-rename atomically.
    os.replace(bathy_tmp, paths["bathy_pq"])
    os.replace(land_tmp, paths["land_pq"])

    # Build audit DataFrame with TOTALS row appended.
    audit_df = pd.DataFrame(summaries)
    if len(audit_df):
        sum_cols = ["rows_in", "rows_land", "rows_nodata", "rows_bathymetry", "rows_nan_depth"]
        totals = {
            "quadrant": "TOTALS",
            **{c: int(audit_df[c].sum()) for c in sum_cols},
            "depth_min_bathy_raw": float(np.nanmin(audit_df["depth_min_bathy_raw"]))
            if audit_df["depth_min_bathy_raw"].notna().any()
            else float("nan"),
            "depth_max_bathy_raw": float(np.nanmax(audit_df["depth_max_bathy_raw"]))
            if audit_df["depth_max_bathy_raw"].notna().any()
            else float("nan"),
            "lon_min": float(np.nanmin(audit_df["lon_min"]))
            if audit_df["lon_min"].notna().any()
            else float("nan"),
            "lon_max": float(np.nanmax(audit_df["lon_max"]))
            if audit_df["lon_max"].notna().any()
            else float("nan"),
            "lat_min": float(np.nanmin(audit_df["lat_min"]))
            if audit_df["lat_min"].notna().any()
            else float("nan"),
            "lat_max": float(np.nanmax(audit_df["lat_max"]))
            if audit_df["lat_max"].notna().any()
            else float("nan"),
            "depth_clip_lower_m": DEPTH_CLIP_LOWER_M,
            "land_depth_cutoff_m": LAND_DEPTH_CUTOFF_M,
            "cleaning_version": CLEANING_VERSION,
        }
        audit_df = pd.concat([audit_df, pd.DataFrame([totals])], ignore_index=True)

    atomic_write_parquet(audit_df, paths["audit_pq"])

    elapsed_s = (datetime.now() - t0).total_seconds()
    atomic_write_text(
        make_report(
            audit_df=audit_df,
            run_label=args.run_label,
            elapsed_s=elapsed_s,
            bathy_out_path=paths["bathy_pq"],
            land_out_path=paths["land_pq"],
            audit_out_path=paths["audit_pq"],
        ),
        paths["report_md"],
    )

    logger.info("Wrote %s (%d bathy rows)", paths["bathy_pq"], n_bathy_total)
    logger.info("Wrote %s", paths["land_pq"])
    logger.info("Wrote %s", paths["audit_pq"])
    logger.info("Wrote %s", paths["report_md"])
    logger.info("Elapsed: %.1fs", elapsed_s)
    logger.info("04_clean_mrar.py DONE")

    print(f"Bathy rows: {n_bathy_total:,}")
    if len(audit_df):
        tot_row = audit_df.iloc[-1]
        print(
            f"Totals — in={tot_row['rows_in']:,} "
            f"land={tot_row['rows_land']:,} "
            f"nodata={tot_row['rows_nodata']:,} "
            f"bathy={tot_row['rows_bathymetry']:,} "
            f"nan={tot_row['rows_nan_depth']:,}"
        )
    print(f"Bathy parquet: {paths['bathy_pq']}")
    print(f"Land parquet:  {paths['land_pq']}")
    print(f"Audit parquet: {paths['audit_pq']}")
    print(f"Report:        {paths['report_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
