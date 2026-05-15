#!/usr/bin/env python3
"""
02_standardize_multibeam_xyz.py

Convert usable NCEI multibeam .dat files into standardized Parquet point tables.

Reads:
  - manifests/file_manifest.parquet   (from 01 script)
  - raw/dat_by_subzip/                (source .dat files)

Writes (full mode):
  - derived/points_raw/<file_id>.parquet   (one per source .dat)
  - manifests/points_raw_manifest.parquet + .tsv
  - output/logs/02_standardize_multibeam_xyz.log
  - output/logs/02_standardize_errors.tsv
  - docs/point_schema_v1.md

Writes (sample mode):
  - derived/points_raw_sample/<file_id>.parquet
  - manifests/points_raw_manifest_sample.parquet + .tsv

Point schema (each row):
  file_id               string    (e.g. "MR03-K02_bathymetry_dmo::20030527.dat")
  point_index_in_file   int64     (0-based row index within source file)
  lon_raw               float64   (original longitude, may be [0,360))
  lat_raw               float64   (original latitude)
  lon                   float64   (normalized to [-180, 180))
  lat                   float64   (= lat_raw)
  depth_m_positive_down float64   (original depth, positive down)
  elev_m                float64   (= -depth_m_positive_down)
  date_raw              string?   (6-col only, else null)
  time_raw              string?   (6-col only, else null)
  sonar_idx             int64?    (6-col only, else null)

Usage:
    # Sample: 2 files per layout
    python 02_standardize_multibeam_xyz.py --sample-per-layout 2 --chunk-size 1000000 --overwrite

    # Specific files
    python 02_standardize_multibeam_xyz.py --file-id "KY11-02_leg1_bathymetry_dmo::T20110205.dat" --overwrite

    # Full run
    python 02_standardize_multibeam_xyz.py --overwrite

    # Dry run (no output files written)
    python 02_standardize_multibeam_xyz.py --dry-run --sample-per-layout 2

    # Estimate total rows/size only
    python 02_standardize_multibeam_xyz.py --estimate-only
"""

import argparse
import csv
import logging
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent

CURATED_MANIFEST_PQ = ROOT_DIR / "manifests" / "file_manifest_points_raw.parquet"
ORIGINAL_MANIFEST_PQ = ROOT_DIR / "manifests" / "file_manifest.parquet"
RAW_DIR = ROOT_DIR / "raw" / "dat_by_subzip"

LOG_PATH = ROOT_DIR / "output" / "logs" / "02_standardize_multibeam_xyz.log"
ERRORS_TSV = ROOT_DIR / "output" / "logs" / "02_standardize_errors.tsv"
SCHEMA_DOC = ROOT_DIR / "docs" / "point_schema_v1.md"

LAYOUT_3COL = "lon_lat_depth_3col"
LAYOUT_6COL = "date_time_sonar_lon_lat_depth_6col"

VALID_RUN_LABELS = ("sample", "lon360", "test100", "sample_curated",
                     "test100_curated", "full")
DEFAULT_CHUNK_SIZE = 1_000_000

AUX_PREFIXES = ("grid_", "track_", "dist_")


def get_run_paths(run_label: str):
    """Return (output_dir, manifest_pq, manifest_tsv) for a given run-label."""
    derived = ROOT_DIR / "derived"
    manifests = ROOT_DIR / "manifests"
    if run_label == "full":
        return (
            derived / "points_raw",
            manifests / "points_raw_manifest.parquet",
            manifests / "points_raw_manifest.tsv",
        )
    suffix = run_label  # sample, lon360, test100
    return (
        derived / f"points_raw_{suffix}",
        manifests / f"points_raw_manifest_{suffix}.parquet",
        manifests / f"points_raw_manifest_{suffix}.tsv",
    )

# ---------------------------------------------------------------------------
# Point table PyArrow schema
# ---------------------------------------------------------------------------
POINT_SCHEMA = pa.schema([
    ("file_id", pa.string()),
    ("point_index_in_file", pa.int64()),
    ("lon_raw", pa.float64()),
    ("lat_raw", pa.float64()),
    ("lon", pa.float64()),
    ("lat", pa.float64()),
    ("depth_m_positive_down", pa.float64()),
    ("elev_m", pa.float64()),
    ("date_raw", pa.string()),
    ("time_raw", pa.string()),
    ("sonar_idx", pa.int64()),
])


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("standardize_xyz")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s %(message)s"))
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(levelname)-8s %(message)s"))
    logger.addHandler(ch)
    return logger


# ---------------------------------------------------------------------------
# Sample selection
# ---------------------------------------------------------------------------
def select_sample_files(
    fm: pd.DataFrame,
    sample_n_files: Optional[int],
    sample_per_layout: Optional[int],
    limit_files: Optional[int],
    file_ids: Optional[list[str]],
    subzip_ids: Optional[list[str]],
    require_raw_lon_gt_180: bool = False,
) -> pd.DataFrame:
    """Filter file_manifest to a sample of usable files.

    fm is expected to already be filtered to include-only rows.
    """
    df = fm.copy()

    if require_raw_lon_gt_180:
        df = df[df["lon_max"] > 180]

    if file_ids:
        df = df[df["file_id"].isin(file_ids)]
    if subzip_ids:
        df = df[df["subzip_id"].isin(subzip_ids)]

    if sample_per_layout is not None:
        parts = []
        layouts = df["data_layout"].unique()
        for layout in layouts:
            sub = df[df["data_layout"] == layout]
            n = min(sample_per_layout, len(sub))
            parts.append(sub.sample(n=n, random_state=42))
        df = pd.concat(parts, ignore_index=True)
    elif sample_n_files is not None:
        n = min(sample_n_files, len(df))
        df = df.sample(n=n, random_state=42)

    if limit_files is not None:
        df = df.head(limit_files)

    return df


# ---------------------------------------------------------------------------
# Read a chunk of lines from a .dat file and convert to DataFrame
# ---------------------------------------------------------------------------
def _normalize_lon(lon_raw: np.ndarray) -> np.ndarray:
    """Convert longitude to [-180, 180)."""
    return ((lon_raw + 180.0) % 360.0) - 180.0


def parse_chunk(
    lines: list[str],
    file_id: str,
    data_layout: str,
    lon_col: int,
    lat_col: int,
    depth_col: int,
    date_col: Optional[int],
    time_col: Optional[int],
    sonar_idx_col: Optional[int],
    start_index: int,
) -> pd.DataFrame:
    """Parse a list of text lines into a DataFrame with POINT_SCHEMA columns."""
    n = len(lines)
    if n == 0:
        return pd.DataFrame(columns=[
            "file_id", "point_index_in_file",
            "lon_raw", "lat_raw", "lon", "lat",
            "depth_m_positive_down", "elev_m",
            "date_raw", "time_raw", "sonar_idx",
        ])

    # Pre-allocate arrays
    lon_raw = np.empty(n, dtype=np.float64)
    lat_raw = np.empty(n, dtype=np.float64)
    depth = np.empty(n, dtype=np.float64)
    date_raw = np.full(n, np.nan, dtype=object)
    time_raw = np.full(n, np.nan, dtype=object)
    sonar_idx = np.full(n, -1, dtype=np.int64)

    has_6col = (data_layout == LAYOUT_6COL)

    for i, line in enumerate(lines):
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            lon_raw[i] = float(parts[lon_col])
            lat_raw[i] = float(parts[lat_col])
            depth[i] = float(parts[depth_col])
            if has_6col:
                date_raw[i] = parts[date_col] if date_col is not None else None
                time_raw[i] = parts[time_col] if time_col is not None else None
                sonar_idx[i] = int(float(parts[sonar_idx_col])) if sonar_idx_col is not None else -1
        except (ValueError, IndexError):
            continue

    lon = _normalize_lon(lon_raw)
    elev = -depth

    df = pd.DataFrame({
        "file_id": file_id,
        "point_index_in_file": np.arange(start_index, start_index + n, dtype=np.int64),
        "lon_raw": lon_raw,
        "lat_raw": lat_raw,
        "lon": lon,
        "lat": lat_raw,
        "depth_m_positive_down": depth,
        "elev_m": elev,
        "date_raw": date_raw if has_6col else None,
        "time_raw": time_raw if has_6col else None,
        "sonar_idx": sonar_idx if has_6col else None,
    })

    return df


# ---------------------------------------------------------------------------
# Process a single file
# ---------------------------------------------------------------------------
def process_file(
    row: pd.Series,
    output_dir: Path,
    chunk_size: int,
    overwrite: bool,
    dry_run: bool,
    logger: logging.Logger,
) -> dict:
    """Process one .dat file into Parquet point table.

    Returns manifest entry dict.
    """
    file_id = row["file_id"]
    relative_path = row["relative_path"]
    data_layout = row["data_layout"]
    line_count_expected = row["line_count"]

    lon_col = int(row["lon_col"])
    lat_col = int(row["lat_col"])
    depth_col = int(row["depth_col"])
    date_col = int(row["date_col"]) if pd.notna(row["date_col"]) else None
    time_col = int(row["time_col"]) if pd.notna(row["time_col"]) else None
    sonar_idx_col = int(row["sonar_idx_col"]) if pd.notna(row["sonar_idx_col"]) else None

    full_path = RAW_DIR / relative_path

    # Flatten file_id to a safe filename: replace :: and / with __, drop .dat extension
    safe_name = file_id.replace("::", "__").replace("/", "__")
    if safe_name.endswith(".dat"):
        safe_name = safe_name[:-4]
    out_filename = safe_name + ".parquet"
    out_path = output_dir / out_filename

    # Skip if exists and not overwrite
    if not overwrite and out_path.exists():
        logger.info(f"  Skip (exists): {out_filename}")
        return {
            "file_id": file_id,
            "input_relative_path": relative_path,
            "output_relative_path": str(out_path.relative_to(ROOT_DIR)),
            "data_layout": data_layout,
            "rows_expected_from_manifest": line_count_expected,
            "rows_written": -1,  # skipped
            "lon_raw_min": None, "lon_raw_max": None,
            "lon_min": None, "lon_max": None,
            "lat_min": None, "lat_max": None,
            "depth_min": None, "depth_max": None,
            "elev_min": None, "elev_max": None,
            "has_date_time_sonar": data_layout == LAYOUT_6COL,
            "status": "skipped_exists",
            "notes": "output file already exists",
        }

    if dry_run:
        logger.info(f"  [DRY RUN] Would process: {relative_path} ({line_count_expected} lines)")
        return {
            "file_id": file_id,
            "input_relative_path": relative_path,
            "output_relative_path": str(out_path.relative_to(ROOT_DIR)),
            "data_layout": data_layout,
            "rows_expected_from_manifest": line_count_expected,
            "rows_written": 0,
            "lon_raw_min": None, "lon_raw_max": None,
            "lon_min": None, "lon_max": None,
            "lat_min": None, "lat_max": None,
            "depth_min": None, "depth_max": None,
            "elev_min": None, "elev_max": None,
            "has_date_time_sonar": data_layout == LAYOUT_6COL,
            "status": "dry_run",
            "notes": "",
        }

    if not full_path.exists():
        return {
            "file_id": file_id,
            "input_relative_path": relative_path,
            "output_relative_path": "",
            "data_layout": data_layout,
            "rows_expected_from_manifest": line_count_expected,
            "rows_written": 0,
            "lon_raw_min": None, "lon_raw_max": None,
            "lon_min": None, "lon_max": None,
            "lat_min": None, "lat_max": None,
            "depth_min": None, "depth_max": None,
            "elev_min": None, "elev_max": None,
            "has_date_time_sonar": data_layout == LAYOUT_6COL,
            "status": "error",
            "notes": f"source file not found: {full_path}",
        }

    logger.info(f"  Processing: {relative_path} ({line_count_expected} lines, {data_layout})")

    # Track stats
    total_rows = 0
    all_lon_raw = []
    all_lon = []
    all_lat = []
    all_depth = []
    all_elev = []

    tmp_path = out_path.with_suffix(".parquet.tmp")
    output_dir.mkdir(parents=True, exist_ok=True)

    writer = None
    point_index = 0

    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            chunk_lines = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                chunk_lines.append(line)

                if len(chunk_lines) >= chunk_size:
                    df_chunk = parse_chunk(
                        chunk_lines, file_id, data_layout,
                        lon_col, lat_col, depth_col,
                        date_col, time_col, sonar_idx_col,
                        point_index,
                    )
                    chunk_lines = []

                    if len(df_chunk) > 0:
                        # Accumulate stats
                        all_lon_raw.extend([df_chunk["lon_raw"].min(), df_chunk["lon_raw"].max()])
                        all_lon.extend([df_chunk["lon"].min(), df_chunk["lon"].max()])
                        all_lat.extend([df_chunk["lat"].min(), df_chunk["lat"].max()])
                        all_depth.extend([df_chunk["depth_m_positive_down"].min(), df_chunk["depth_m_positive_down"].max()])
                        all_elev.extend([df_chunk["elev_m"].min(), df_chunk["elev_m"].max()])

                        table = pa.Table.from_pandas(df_chunk, schema=POINT_SCHEMA, preserve_index=False)
                        if writer is None:
                            writer = pq.ParquetWriter(str(tmp_path), POINT_SCHEMA)
                        writer.write_table(table)
                        total_rows += len(df_chunk)
                    point_index += len(chunk_lines) if len(chunk_lines) == 0 else chunk_size

            # Flush remaining lines
            if chunk_lines:
                df_chunk = parse_chunk(
                    chunk_lines, file_id, data_layout,
                    lon_col, lat_col, depth_col,
                    date_col, time_col, sonar_idx_col,
                    point_index,
                )
                if len(df_chunk) > 0:
                    all_lon_raw.extend([df_chunk["lon_raw"].min(), df_chunk["lon_raw"].max()])
                    all_lon.extend([df_chunk["lon"].min(), df_chunk["lon"].max()])
                    all_lat.extend([df_chunk["lat"].min(), df_chunk["lat"].max()])
                    all_depth.extend([df_chunk["depth_m_positive_down"].min(), df_chunk["depth_m_positive_down"].max()])
                    all_elev.extend([df_chunk["elev_m"].min(), df_chunk["elev_m"].max()])

                    table = pa.Table.from_pandas(df_chunk, schema=POINT_SCHEMA, preserve_index=False)
                    if writer is None:
                        writer = pq.ParquetWriter(str(tmp_path), POINT_SCHEMA)
                    writer.write_table(table)
                    total_rows += len(df_chunk)

        if writer is not None:
            writer.close()

        if total_rows == 0:
            # Empty result, remove tmp
            if tmp_path.exists():
                tmp_path.unlink()
            logger.warning(f"  No rows extracted from {relative_path}")
            return {
                "file_id": file_id,
                "input_relative_path": relative_path,
                "output_relative_path": "",
                "data_layout": data_layout,
                "rows_expected_from_manifest": line_count_expected,
                "rows_written": 0,
                "lon_raw_min": None, "lon_raw_max": None,
                "lon_min": None, "lon_max": None,
                "lat_min": None, "lat_max": None,
                "depth_min": None, "depth_max": None,
                "elev_min": None, "elev_max": None,
                "has_date_time_sonar": data_layout == LAYOUT_6COL,
                "status": "empty_output",
                "notes": "no rows extracted",
            }

        # Atomic rename
        os.replace(tmp_path, out_path)

        out_rel = str(out_path.relative_to(ROOT_DIR))

        logger.info(f"    -> {out_filename}: {total_rows:,} rows")

        return {
            "file_id": file_id,
            "input_relative_path": relative_path,
            "output_relative_path": out_rel,
            "data_layout": data_layout,
            "rows_expected_from_manifest": line_count_expected,
            "rows_written": total_rows,
            "lon_raw_min": min(all_lon_raw) if all_lon_raw else None,
            "lon_raw_max": max(all_lon_raw) if all_lon_raw else None,
            "lon_min": min(all_lon) if all_lon else None,
            "lon_max": max(all_lon) if all_lon else None,
            "lat_min": min(all_lat) if all_lat else None,
            "lat_max": max(all_lat) if all_lat else None,
            "depth_min": min(all_depth) if all_depth else None,
            "depth_max": max(all_depth) if all_depth else None,
            "elev_min": min(all_elev) if all_elev else None,
            "elev_max": max(all_elev) if all_elev else None,
            "has_date_time_sonar": data_layout == LAYOUT_6COL,
            "status": "ok",
            "notes": "",
        }

    except Exception as e:
        # Clean up tmp
        if tmp_path.exists():
            tmp_path.unlink()
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass
        logger.error(f"  ERROR processing {relative_path}: {e}")
        return {
            "file_id": file_id,
            "input_relative_path": relative_path,
            "output_relative_path": "",
            "data_layout": data_layout,
            "rows_expected_from_manifest": line_count_expected,
            "rows_written": total_rows,
            "lon_raw_min": None, "lon_raw_max": None,
            "lon_min": None, "lon_max": None,
            "lat_min": None, "lat_max": None,
            "depth_min": None, "depth_max": None,
            "elev_min": None, "elev_max": None,
            "has_date_time_sonar": data_layout == LAYOUT_6COL,
            "status": "error",
            "notes": str(e),
        }


# ---------------------------------------------------------------------------
# Write point schema doc
# ---------------------------------------------------------------------------
def write_point_schema_doc(doc_path: Path, logger: logging.Logger):
    """Write docs/point_schema_v1.md."""
    content = """# Point Schema v1

Generated: {ts}

## Schema

Standardized point table for NCEI multibeam bathymetric data.

| Column                  | Type     | Nullable | Description |
|-------------------------|----------|----------|-------------|
| file_id                 | string   | No       | Foreign key to file_manifest.file_id (e.g. "MR03-K02_bathymetry_dmo::20030527.dat") |
| point_index_in_file     | int64    | No       | 0-based row index within the source .dat file |
| lon_raw                 | float64  | No       | Original longitude from source file (may be [0,360)) |
| lat_raw                 | float64  | No       | Original latitude from source file |
| lon                     | float64  | No       | Longitude normalized to [-180, 180). Formula: `((lon_raw + 180) % 360) - 180` |
| lat                     | float64  | No       | Latitude (= lat_raw) |
| depth_m_positive_down   | float64  | No       | Depth in meters, positive downward (original value) |
| elev_m                  | float64  | No       | Elevation in meters (= -depth_m_positive_down). Negative for below sea level. |
| date_raw                | string   | Yes      | Date string from 6-col files (e.g. "20110205"), null for 3-col files |
| time_raw                | string   | Yes      | Time string from 6-col files (e.g. "000002335"), null for 3-col files |
| sonar_idx               | int64    | Yes      | Sonar beam index from 6-col files, null for 3-col files |

## Data Sources

### lon_lat_depth_3col (5,072 files)
- Columns: lon lat depth
- lon_col=0, lat_col=1, depth_col=2
- date_raw, time_raw, sonar_idx: all null

### date_time_sonar_lon_lat_depth_6col (24 files)
- Columns: date time sonar_idx lon lat depth
- date_col=0, time_col=1, sonar_idx_col=2, lon_col=3, lat_col=4, depth_col=5
- date_raw, time_raw, sonar_idx: populated

## Design Decisions

1. **No metadata duplication**: Each row contains only `file_id`. Join with `file_manifest` for
   subzip_id, cruise_id_guess, track_kind, etc. Join with `points_raw_manifest` for per-file
   statistics (row counts, lon/lat/depth ranges).

2. **One Parquet per source .dat**: Output is `derived/points_raw/<file_id>.parquet` where
   file_id uses `__` instead of `::`. Large files are written chunk-by-chunk but into a single
   Parquet file using PyArrow's chunked writer.

3. **Lon normalization**: All lon values are converted to [-180, 180) using the formula
   `((lon_raw + 180) % 360) - 180`. Files with lon in [0,360) will be converted correctly.

4. **Depth convention**: depth_m_positive_down is always positive (depth below sea level).
   elev_m = -depth_m_positive_down is always negative (below sea level).

5. **Resumable**: If output Parquet exists and --overwrite is not set, the file is skipped.

## Relationships

```
file_manifest (1) -- (1) points_raw_manifest   [by file_id]
file_manifest (1) -- (N) points_raw/*.parquet   [by file_id]
```
""".format(ts=datetime.now().isoformat())

    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(content, encoding="utf-8")
    logger.info(f"Point schema doc written to {doc_path}")


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------
def atomic_write_df(
    df: pd.DataFrame,
    target_parquet: Path,
    target_tsv: Path,
    logger: logging.Logger,
):
    target_parquet.parent.mkdir(parents=True, exist_ok=True)

    tmp_pq = target_parquet.with_suffix(".parquet.tmp")
    tmp_tsv = target_tsv.with_suffix(".tsv.tmp")

    df.to_parquet(tmp_pq, index=False)
    logger.info(f"Wrote temp parquet: {tmp_pq}")

    df.to_csv(tmp_tsv, sep="\t", index=False)
    logger.info(f"Wrote temp tsv: {tmp_tsv}")

    os.replace(tmp_pq, target_parquet)
    os.replace(tmp_tsv, target_tsv)
    logger.info(f"Renamed to final: {target_parquet.name}, {target_tsv.name}")


# ---------------------------------------------------------------------------
# Write errors TSV
# ---------------------------------------------------------------------------
def write_errors_tsv(errors: list[dict], errors_path: Path, logger: logging.Logger):
    if not errors:
        return
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    df_err = pd.DataFrame(errors)
    df_err.to_csv(errors_path, sep="\t", index=False)
    logger.info(f"Wrote {len(errors)} errors to {errors_path}")



# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Convert NCEI multibeam .dat files to standardized Parquet point tables.",
    )
    parser.add_argument(
        "--manifest-path", type=str, default=None,
        help="Path to manifest parquet (default: curated if exists, else original).",
    )
    parser.add_argument(
        "--allow-auxiliary", action="store_true",
        help="Allow grid_/track_/dist_ files. Not recommended.",
    )
    parser.add_argument(
        "--run-label", type=str, default="sample",
        choices=VALID_RUN_LABELS,
        help="Run label: sample (default), lon360, test100, full. Determines output directory.",
    )
    parser.add_argument(
        "--confirm-full", action="store_true",
        help="Required safety flag when --run-label=full.",
    )
    parser.add_argument(
        "--sample-n-files", type=int, default=None,
        help="Randomly sample N usable .dat files.",
    )
    parser.add_argument(
        "--sample-per-layout", type=int, default=None,
        help="Sample N files per data_layout (ensures 6-col representation).",
    )
    parser.add_argument(
        "--limit-files", type=int, default=None,
        help="Process only the first N usable files.",
    )
    parser.add_argument(
        "--file-id", type=str, nargs="*", default=None,
        help="Process specific file_id(s).",
    )
    parser.add_argument(
        "--subzip-id", type=str, nargs="*", default=None,
        help="Process all usable files in specific subzip_id(s).",
    )
    parser.add_argument(
        "--require-raw-lon-gt-180", action="store_true",
        help="Only select files where lon_max > 180 (for lon360 validation).",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing output Parquet files.",
    )
    parser.add_argument(
        "--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
        help=f"Lines per chunk for reading large files (default: {DEFAULT_CHUNK_SIZE}).",
    )
    parser.add_argument(
        "--estimate-only", action="store_true",
        help="Print estimated row counts and output sizes, then exit. No files written.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be processed without writing output.",
    )
    args = parser.parse_args()

    run_label = args.run_label

    logger = setup_logging(LOG_PATH)
    logger.info("=" * 60)
    logger.info("Starting 02_standardize_multibeam_xyz.py")
    logger.info(f"Args: {vars(args)}")

    # Safety gate for full mode
    if run_label == "full" and not args.confirm_full:
        msg = "ABORTED: --run-label=full requires --confirm-full to prevent accidental full runs."
        logger.error(msg)
        print(f"ERROR: {msg}")
        sys.exit(1)

    # Resolve manifest path: explicit > curated (if exists) > original
    if args.manifest_path:
        manifest_path = Path(args.manifest_path)
        if not manifest_path.is_absolute():
            manifest_path = ROOT_DIR / manifest_path
    elif CURATED_MANIFEST_PQ.exists():
        manifest_path = CURATED_MANIFEST_PQ
    else:
        manifest_path = ORIGINAL_MANIFEST_PQ

    if not manifest_path.exists():
        logger.error(f"manifest not found: {manifest_path}")
        print(f"ERROR: manifest not found: {manifest_path}")
        sys.exit(1)

    fm = pd.read_parquet(manifest_path)
    logger.info(f"Loaded manifest: {manifest_path} ({len(fm)} rows)")

    # Filter: include_in_points_raw if present, else used_for_points
    has_include = "include_in_points_raw" in fm.columns
    if has_include:
        usable = fm[fm["include_in_points_raw"] == True].copy()  # noqa: E712
        n_inc_true = int(fm["include_in_points_raw"].sum())
        logger.info(f"include_in_points_raw=True: {n_inc_true} / {len(fm)}")
    else:
        usable = fm[fm["used_for_points"] == True].copy()  # noqa: E712
        logger.info(f"used_for_points=True: {len(usable)} / {len(fm)}")

    selected_total_lines = int(usable["line_count"].sum())

    logger.info(f"  3-col: {int((usable['data_layout'] == LAYOUT_3COL).sum())}")
    logger.info(f"  6-col: {int((usable['data_layout'] == LAYOUT_6COL).sum())}")

    # Guard: reject auxiliary files (grid_/track_/dist_) unless --allow-auxiliary
    aux_mask = usable["filename"].apply(
        lambda fn: any(os.path.basename(fn).startswith(p) for p in AUX_PREFIXES)
    )
    n_aux = int(aux_mask.sum())
    if n_aux > 0 and not args.allow_auxiliary:
        aux_names = usable.loc[aux_mask, "filename"].head(10).tolist()
        msg = (f"ABORTED: {n_aux} auxiliary file(s) found (grid_/track_/dist_). "
               f"Use --allow-auxiliary to override. Examples: {aux_names}")
        logger.error(msg)
        print(f"ERROR: {msg}")
        sys.exit(1)

    if args.require_raw_lon_gt_180:
        lon360_count = int((usable["lon_max"] > 180).sum())
        logger.info(f"Files with lon_max > 180: {lon360_count}")

    # Resolve output paths from run-label
    output_dir, manifest_pq, manifest_tsv = get_run_paths(run_label)

    # Print config summary
    config_summary = (
        f"\n{'='*60}\n"
        f"  CONFIG SUMMARY\n"
        f"{'='*60}\n"
        f"  manifest_path:        {manifest_path}\n"
        f"  manifest total rows:  {len(fm)}\n"
        f"  include field:        {'include_in_points_raw' if has_include else 'used_for_points'}\n"
        f"  selected files:       {len(usable)}\n"
        f"  selected_total_lines: {selected_total_lines:,}\n"
        f"  run_label:            {run_label}\n"
        f"  output_dir:           {output_dir}\n"
        f"  confirm_full:         {args.confirm_full}\n"
        f"  estimate_only:        {args.estimate_only}\n"
        f"{'='*60}"
    )
    logger.info(config_summary)
    print(config_summary)

    # Estimate-only mode (after resolving paths so we can show target dir)
    if args.estimate_only:
        _estimate(usable, output_dir, selected_total_lines, logger)
        return

    # Select files to process
    to_process = select_sample_files(
        usable,
        sample_n_files=args.sample_n_files,
        sample_per_layout=args.sample_per_layout,
        limit_files=args.limit_files,
        file_ids=args.file_id,
        subzip_ids=args.subzip_id,
        require_raw_lon_gt_180=args.require_raw_lon_gt_180,
    )

    if len(to_process) == 0:
        logger.info("No files to process.")
        print("No files to process.")
        return

    logger.info(f"Files to process: {len(to_process)}")
    for _, r in to_process.iterrows():
        logger.info(f"  {r['file_id']} ({r['data_layout']}, {r['line_count']:.0f} lines)")

    # Print target directory before writing
    print(f"Target output dir: {output_dir}")
    print(f"Target manifest:   {manifest_pq}")
    if run_label != "full":
        print(f"(run_label={run_label} — will NOT write to derived/points_raw/)")

    # Process files with timing
    manifest_entries = []
    errors = []
    t_start = datetime.now()

    for idx, (_, row) in enumerate(to_process.iterrows()):
        if idx % 100 == 0 and idx > 0:
            logger.info(f"  Progress: {idx}/{len(to_process)}")

        result = process_file(
            row=row,
            output_dir=output_dir,
            chunk_size=args.chunk_size,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
            logger=logger,
        )
        manifest_entries.append(result)
        if result["status"] == "error":
            errors.append(result)

    t_end = datetime.now()
    elapsed_s = (t_end - t_start).total_seconds()

    # Write manifest
    manifest_df = pd.DataFrame(manifest_entries)
    if not args.dry_run:
        atomic_write_df(manifest_df, manifest_pq, manifest_tsv, logger)

    write_errors_tsv(errors, ERRORS_TSV, logger)

    if not args.dry_run:
        write_point_schema_doc(SCHEMA_DOC, logger)

    # Compute run report
    n_ok = sum(1 for e in manifest_entries if e["status"] == "ok")
    n_skip = sum(1 for e in manifest_entries if e["status"] == "skipped_exists")
    n_err = sum(1 for e in manifest_entries if e["status"] == "error")
    total_rows = sum(
        e["rows_written"] for e in manifest_entries
        if isinstance(e["rows_written"], (int, float)) and e["rows_written"] > 0
    )

    # Output size
    output_size_bytes = 0
    if output_dir.exists():
        for f in output_dir.glob("*.parquet"):
            output_size_bytes += f.stat().st_size

    bytes_per_row = output_size_bytes / total_rows if total_rows > 0 else 0
    rows_per_sec = total_rows / elapsed_s if elapsed_s > 0 else 0
    full_est_bytes = bytes_per_row * selected_total_lines
    full_est_time_s = selected_total_lines / rows_per_sec if rows_per_sec > 0 else 0
    full_est_hrs = full_est_time_s / 3600

    logger.info("Done.")
    logger.info("=" * 60)

    report = f"""
{'='*60}
  RUN REPORT — 02_standardize_multibeam_xyz.py
{'='*60}
  run_label:           {run_label}
  output_dir:          {output_dir}
  manifest:            {manifest_pq}
  files_processed:     {n_ok} ok, {n_skip} skipped, {n_err} errors
  total_rows_written:  {total_rows:,}
  output_size:         {output_size_bytes / 1e6:.1f} MB
  bytes_per_row:       {bytes_per_row:.1f}
  elapsed:             {elapsed_s:.1f}s
  rows/sec:            {rows_per_sec:,.0f}
  ── full run projection ({selected_total_lines:,} rows) ──
  est. parquet size:   {full_est_bytes / 1e9:.2f} GB
  est. wall time:      {full_est_hrs:.1f} hrs ({full_est_time_s / 60:.0f} min)
  error_files:         {n_err}
{'='*60}
"""
    logger.info(report)
    print(report)


def _estimate(usable: pd.DataFrame, output_dir: Path,
              selected_total_lines: int, logger: logging.Logger):
    """Print estimated total rows and output size without writing any files."""
    total_lines = selected_total_lines
    n_files = len(usable)

    est_bytes_per_row = 33.4  # from test100 curated benchmark
    est_bytes_parquet = total_lines * est_bytes_per_row

    logger.info(f"Output dir would be: {output_dir}")
    logger.info(f"Files to process: {n_files}")
    logger.info(f"Selected total lines: {total_lines:,}")
    logger.info(f"Estimated Parquet size: {est_bytes_parquet / 1e9:.2f} GB")

    print(f"\n{'='*60}")
    print(f"  ESTIMATE ONLY (no files written)")
    print(f"  run_label target dir: {output_dir}")
    print(f"  Files: {n_files}")
    print(f"  Total rows: {total_lines:,}")
    print(f"  Est. Parquet: {est_bytes_parquet / 1e9:.2f} GB (~{est_bytes_per_row} bytes/row)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
