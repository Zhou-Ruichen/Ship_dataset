#!/usr/bin/env python3
"""
03_qc_multibeam_points.py

Apply quality-control flags to standardized point tables from 02.

Reads:
  - derived/points_raw/*.parquet             (from 02 script)
  - manifests/points_raw_manifest.parquet    (from 02 script)

Writes (full mode):
  - derived/points_qc/<file_id>.parquet
  - manifests/points_qc_manifest.parquet + .tsv
  - docs/qc_points_report.md
  - output/logs/03_qc_multibeam_points.log
  - output/logs/03_qc_errors.tsv

QC columns added to each row:
  qc_valid_lon          bool    lon >= -180 and lon < 180
  qc_valid_lat          bool    lat >= -90 and lat <= 90
  qc_depth_positive     bool    depth_m_positive_down > 0
  qc_depth_not_extreme  bool    depth_m_positive_down <= 12000
  qc_elev_negative      bool    elev_m < 0
  qc_no_nan             bool    lon, lat, depth_m_positive_down, elev_m all non-NaN
  qc_zero_depth         bool    depth_m_positive_down == 0
  qc_pass_basic         bool    all of the above (except qc_zero_depth) are True
  qc_reason             string  comma-separated failure reasons, empty string if pass

Usage:
    # Sample: 5 random files
    python 03_qc_multibeam_points.py --run-label sample --sample-n-files 5 --overwrite

    # Test100
    python 03_qc_multibeam_points.py --run-label test100 --limit-files 100 --overwrite

    # Full run
    python 03_qc_multibeam_points.py --run-label full --confirm-full --overwrite

    # Estimate only
    python 03_qc_multibeam_points.py --run-label full --confirm-full --estimate-only
"""

import argparse
import logging
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

POINTS_RAW_DIR = ROOT_DIR / "derived" / "points_raw"
RAW_MANIFEST_PQ = ROOT_DIR / "manifests" / "points_raw_manifest.parquet"

LOG_DIR = ROOT_DIR / "output" / "logs"

VALID_RUN_LABELS = ("sample", "test100", "full")
DEFAULT_CHUNK_SIZE = 1_000_000
DEPTH_EXTREME_THRESHOLD = 12_000


def get_run_paths(run_label: str):
    derived = ROOT_DIR / "derived"
    manifests = ROOT_DIR / "manifests"
    docs = ROOT_DIR / "docs"
    if run_label == "full":
        return (
            derived / "points_qc",
            manifests / "points_qc_manifest.parquet",
            manifests / "points_qc_manifest.tsv",
            docs / "qc_points_report.md",
        )
    suffix = run_label
    return (
        derived / f"points_qc_{suffix}",
        manifests / f"points_qc_manifest_{suffix}.parquet",
        manifests / f"points_qc_manifest_{suffix}.tsv",
        docs / f"qc_points_report_{suffix}.md",
    )


def file_id_to_parquet_name(file_id: str) -> str:
    safe = file_id.replace("::", "__").replace("/", "__")
    if safe.endswith(".dat"):
        safe = safe[:-4]
    return safe + ".parquet"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("qc_points")
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
# QC logic — operates on a pandas DataFrame chunk in-place, returns QC cols
# ---------------------------------------------------------------------------
def apply_qc(df: pd.DataFrame) -> pd.DataFrame:
    """Add QC flag columns to df. Returns df with new columns."""
    lon = df["lon"].values
    lat = df["lat"].values
    depth = df["depth_m_positive_down"].values
    elev = df["elev_m"].values

    qc_valid_lon = (lon >= -180) & (lon < 180)
    qc_valid_lat = (lat >= -90) & (lat <= 90)
    qc_depth_positive = depth > 0
    qc_depth_not_extreme = depth <= DEPTH_EXTREME_THRESHOLD
    qc_elev_negative = elev < 0

    nan_lon = np.isnan(lon)
    nan_lat = np.isnan(lat)
    nan_depth = np.isnan(depth)
    nan_elev = np.isnan(elev)
    qc_no_nan = ~nan_lon & ~nan_lat & ~nan_depth & ~nan_elev

    qc_zero_depth = depth == 0

    qc_pass_basic = (
        qc_valid_lon
        & qc_valid_lat
        & qc_depth_positive
        & qc_depth_not_extreme
        & qc_elev_negative
        & qc_no_nan
    )

    # Build qc_reason as comma-separated string
    n = len(df)
    reasons = [""] * n
    for i in range(n):
        parts = []
        if not qc_valid_lon[i]:
            parts.append("invalid_lon")
        if not qc_valid_lat[i]:
            parts.append("invalid_lat")
        if not qc_depth_positive[i]:
            parts.append("non_positive_depth")
        if not qc_depth_not_extreme[i]:
            parts.append("extreme_depth")
        if not qc_elev_negative[i]:
            parts.append("non_negative_elev")
        if not qc_no_nan[i]:
            parts.append("nan_value")
        reasons[i] = ",".join(parts)

    df = df.copy()
    df["qc_valid_lon"] = qc_valid_lon
    df["qc_valid_lat"] = qc_valid_lat
    df["qc_depth_positive"] = qc_depth_positive
    df["qc_depth_not_extreme"] = qc_depth_not_extreme
    df["qc_elev_negative"] = qc_elev_negative
    df["qc_no_nan"] = qc_no_nan
    df["qc_zero_depth"] = qc_zero_depth
    df["qc_pass_basic"] = qc_pass_basic
    df["qc_reason"] = reasons

    return df


QC_OUTPUT_COLUMNS = [
    "file_id", "point_index_in_file",
    "lon_raw", "lat_raw", "lon", "lat",
    "depth_m_positive_down", "elev_m",
    "date_raw", "time_raw", "sonar_idx",
    "qc_valid_lon", "qc_valid_lat",
    "qc_depth_positive", "qc_depth_not_extreme",
    "qc_elev_negative", "qc_no_nan",
    "qc_zero_depth", "qc_pass_basic", "qc_reason",
]

QC_PA_SCHEMA = pa.schema([
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
    ("qc_valid_lon", pa.bool_()),
    ("qc_valid_lat", pa.bool_()),
    ("qc_depth_positive", pa.bool_()),
    ("qc_depth_not_extreme", pa.bool_()),
    ("qc_elev_negative", pa.bool_()),
    ("qc_no_nan", pa.bool_()),
    ("qc_zero_depth", pa.bool_()),
    ("qc_pass_basic", pa.bool_()),
    ("qc_reason", pa.string()),
])


# ---------------------------------------------------------------------------
# Process a single points_raw parquet file
# ---------------------------------------------------------------------------
def process_file(
    file_id: str,
    input_path: Path,
    output_dir: Path,
    chunk_size: int,
    overwrite: bool,
    logger: logging.Logger,
) -> dict:
    safe_name = file_id_to_parquet_name(file_id)
    out_path = output_dir / safe_name

    if not overwrite and out_path.exists():
        return {
            "file_id": file_id,
            "input_path": str(input_path.relative_to(ROOT_DIR)),
            "output_path": str(out_path.relative_to(ROOT_DIR)),
            "rows_read": -1,
            "rows_written": -1,
            "qc_pass_count": None,
            "qc_fail_count": None,
            "qc_pass_rate": None,
            "fail_lon": None, "fail_lat": None,
            "fail_depth_positive": None, "fail_depth_extreme": None,
            "fail_elev_negative": None, "fail_nan": None, "fail_zero_depth": None,
            "status": "skipped_exists",
            "notes": "",
        }

    if not input_path.exists():
        return {
            "file_id": file_id,
            "input_path": str(input_path),
            "output_path": "",
            "rows_read": 0, "rows_written": 0,
            "qc_pass_count": 0, "qc_fail_count": 0, "qc_pass_rate": 0.0,
            "fail_lon": 0, "fail_lat": 0,
            "fail_depth_positive": 0, "fail_depth_extreme": 0,
            "fail_elev_negative": 0, "fail_nan": 0, "fail_zero_depth": 0,
            "status": "error",
            "notes": f"input not found: {input_path}",
        }

    logger.info(f"  Processing: {safe_name}")

    tmp_path = out_path.with_suffix(".parquet.tmp")
    output_dir.mkdir(parents=True, exist_ok=True)

    total_read = 0
    total_written = 0
    total_pass = 0
    total_fail = 0
    acc_fail_lon = 0
    acc_fail_lat = 0
    acc_fail_depth_pos = 0
    acc_fail_depth_ext = 0
    acc_fail_elev = 0
    acc_fail_nan = 0
    acc_fail_zero = 0

    writer = None

    try:
        pf = pq.ParquetFile(str(input_path))
        for batch in pf.iter_batches(batch_size=chunk_size):
            chunk_df = batch.to_pandas()
            n_read = len(chunk_df)
            total_read += n_read

            qc_df = apply_qc(chunk_df)
            total_pass += int(qc_df["qc_pass_basic"].sum())
            total_fail += n_read - int(qc_df["qc_pass_basic"].sum())
            acc_fail_lon += int((~qc_df["qc_valid_lon"]).sum())
            acc_fail_lat += int((~qc_df["qc_valid_lat"]).sum())
            acc_fail_depth_pos += int((~qc_df["qc_depth_positive"]).sum())
            acc_fail_depth_ext += int((~qc_df["qc_depth_not_extreme"]).sum())
            acc_fail_elev += int((~qc_df["qc_elev_negative"]).sum())
            acc_fail_nan += int((~qc_df["qc_no_nan"]).sum())
            acc_fail_zero += int(qc_df["qc_zero_depth"].sum())

            out_cols = [c for c in QC_OUTPUT_COLUMNS if c in qc_df.columns]
            table = pa.Table.from_pandas(qc_df[out_cols], schema=QC_PA_SCHEMA,
                                         preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(str(tmp_path), QC_PA_SCHEMA)
            writer.write_table(table)
            total_written += len(qc_df)

        if writer is not None:
            writer.close()

        if total_written == 0:
            if tmp_path.exists():
                tmp_path.unlink()
            return {
                "file_id": file_id,
                "input_path": str(input_path.relative_to(ROOT_DIR)),
                "output_path": "",
                "rows_read": total_read, "rows_written": 0,
                "qc_pass_count": 0, "qc_fail_count": 0, "qc_pass_rate": 0.0,
                "fail_lon": 0, "fail_lat": 0,
                "fail_depth_positive": 0, "fail_depth_extreme": 0,
                "fail_elev_negative": 0, "fail_nan": 0, "fail_zero_depth": 0,
                "status": "empty_output",
                "notes": "no rows written",
            }

        os.replace(tmp_path, out_path)
        pass_rate = total_pass / total_written if total_written > 0 else 0.0

        logger.info(f"    -> {safe_name}: {total_written:,} rows, "
                     f"pass={total_pass:,} ({pass_rate:.4%})")

        return {
            "file_id": file_id,
            "input_path": str(input_path.relative_to(ROOT_DIR)),
            "output_path": str(out_path.relative_to(ROOT_DIR)),
            "rows_read": total_read,
            "rows_written": total_written,
            "qc_pass_count": total_pass,
            "qc_fail_count": total_fail,
            "qc_pass_rate": pass_rate,
            "fail_lon": acc_fail_lon,
            "fail_lat": acc_fail_lat,
            "fail_depth_positive": acc_fail_depth_pos,
            "fail_depth_extreme": acc_fail_depth_ext,
            "fail_elev_negative": acc_fail_elev,
            "fail_nan": acc_fail_nan,
            "fail_zero_depth": acc_fail_zero,
            "status": "ok",
            "notes": "",
        }

    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass
        logger.error(f"  ERROR processing {safe_name}: {e}")
        return {
            "file_id": file_id,
            "input_path": str(input_path.relative_to(ROOT_DIR)) if input_path.exists() else str(input_path),
            "output_path": "",
            "rows_read": total_read,
            "rows_written": total_written,
            "qc_pass_count": total_pass,
            "qc_fail_count": total_fail,
            "qc_pass_rate": 0.0,
            "fail_lon": acc_fail_lon,
            "fail_lat": acc_fail_lat,
            "fail_depth_positive": acc_fail_depth_pos,
            "fail_depth_extreme": acc_fail_depth_ext,
            "fail_elev_negative": acc_fail_elev,
            "fail_nan": acc_fail_nan,
            "fail_zero_depth": acc_fail_zero,
            "status": "error",
            "notes": str(e),
        }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------
def atomic_write_df(df: pd.DataFrame, target_parquet: Path, target_tsv: Path,
                    logger: logging.Logger):
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


def write_errors_tsv(errors: list[dict], errors_path: Path, logger: logging.Logger):
    if not errors:
        return
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    df_err = pd.DataFrame(errors)
    df_err.to_csv(errors_path, sep="\t", index=False)
    logger.info(f"Wrote {len(errors)} errors to {errors_path}")


# ---------------------------------------------------------------------------
# QC report
# ---------------------------------------------------------------------------
def write_qc_report(
    report_path: Path,
    manifest_df: pd.DataFrame,
    run_label: str,
    elapsed_s: float,
    logger: logging.Logger,
):
    n_ok = int((manifest_df["status"] == "ok").sum())
    n_skip = int((manifest_df["status"] == "skipped_exists").sum())
    n_err = int((manifest_df["status"] == "error").sum())

    total_rows = int(manifest_df.loc[manifest_df["status"] == "ok", "rows_written"].sum())
    total_pass = int(manifest_df.loc[manifest_df["status"] == "ok", "qc_pass_count"].sum())
    total_fail = total_rows - total_pass
    pass_rate = total_pass / total_rows if total_rows > 0 else 0.0

    sum_col = lambda c: int(manifest_df.loc[manifest_df["status"] == "ok", c].sum())

    lines = [
        f"# QC Points Report — {run_label}",
        f"",
        f"Generated: {datetime.now().isoformat()}",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Files processed | {n_ok} ok, {n_skip} skipped, {n_err} errors |",
        f"| Total rows | {total_rows:,} |",
        f"| QC pass | {total_pass:,} ({pass_rate:.4%}) |",
        f"| QC fail | {total_fail:,} ({1-pass_rate:.4%}) |",
        f"| Elapsed | {elapsed_s:.1f}s |",
        f"",
        f"## QC Flag Failures (across all passing files)",
        f"",
        f"| Flag | Fail count |",
        f"|------|------------|",
        f"| qc_valid_lon (lon outside [-180,180)) | {sum_col('fail_lon'):,} |",
        f"| qc_valid_lat (lat outside [-90,90]) | {sum_col('fail_lat'):,} |",
        f"| qc_depth_positive (depth <= 0) | {sum_col('fail_depth_positive'):,} |",
        f"| qc_depth_not_extreme (depth > {DEPTH_EXTREME_THRESHOLD}) | {sum_col('fail_depth_extreme'):,} |",
        f"| qc_elev_negative (elev >= 0) | {sum_col('fail_elev_negative'):,} |",
        f"| qc_no_nan (NaN in core fields) | {sum_col('fail_nan'):,} |",
        f"| qc_zero_depth (depth == 0) | {sum_col('fail_zero_depth'):,} |",
        f"",
    ]

    # Per-file pass rate distribution
    ok_files = manifest_df[manifest_df["status"] == "ok"]
    if len(ok_files) > 0:
        rates = ok_files["qc_pass_rate"].values
        lines.append(f"## Per-file pass rate distribution")
        lines.append(f"")
        lines.append(f"| Stat | Value |")
        lines.append(f"|------|-------|")
        lines.append(f"| Min pass rate | {rates.min():.4%} |")
        lines.append(f"| Max pass rate | {rates.max():.4%} |")
        lines.append(f"| Mean pass rate | {rates.mean():.4%} |")
        lines.append(f"| Files at 100% | {int((rates == 1.0).sum())} / {len(ok_files)} |")
        lines.append(f"| Files < 99% | {int((rates < 0.99).sum())} |")
        lines.append(f"| Files < 90% | {int((rates < 0.90).sum())} |")
        lines.append(f"")

        # Worst 20 files by pass rate
        worst = ok_files.nsmallest(min(20, len(ok_files)), "qc_pass_rate")
        lines.append(f"### Worst 20 files by pass rate")
        lines.append(f"")
        lines.append(f"| file_id | rows | pass | fail | pass_rate | reasons |")
        lines.append(f"|----------|------|------|------|-----------|---------|")
        for _, r in worst.iterrows():
            fid_short = r["file_id"][-60:]
            lines.append(
                f"| {fid_short} | {int(r['rows_written']):,} | "
                f"{int(r['qc_pass_count']):,} | {int(r['qc_fail_count']):,} | "
                f"{r['qc_pass_rate']:.4%} | {r.get('notes', '')} |"
            )
        lines.append(f"")

    content = "\n".join(lines)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(content, encoding="utf-8")
    logger.info(f"QC report written to {report_path}")


# ---------------------------------------------------------------------------
# Estimate only
# ---------------------------------------------------------------------------
def estimate_only(
    raw_manifest: pd.DataFrame,
    output_dir: Path,
    selected_total_lines: int,
    logger: logging.Logger,
):
    n_files = len(raw_manifest)
    est_bytes_per_row_in = 33.6  # points_raw benchmark
    est_bytes_per_row_out = 44.0  # qc adds ~10 bytes of bools + reason string
    est_in_gb = selected_total_lines * est_bytes_per_row_in / 1e9
    est_out_gb = selected_total_lines * est_bytes_per_row_out / 1e9

    logger.info(f"Output dir would be: {output_dir}")
    logger.info(f"Files: {n_files}")
    logger.info(f"Total rows: {selected_total_lines:,}")
    logger.info(f"Est. input size: {est_in_gb:.1f} GB")
    logger.info(f"Est. output size: {est_out_gb:.1f} GB")

    print(f"\n{'='*60}")
    print(f"  ESTIMATE ONLY (no files written)")
    print(f"  run_label target dir: {output_dir}")
    print(f"  Files: {n_files}")
    print(f"  Total rows: {selected_total_lines:,}")
    print(f"  Est. input read: {est_in_gb:.1f} GB")
    print(f"  Est. output write: {est_out_gb:.1f} GB (~{est_bytes_per_row_out} bytes/row)")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Apply QC flags to NCEI multibeam point tables.",
    )
    parser.add_argument(
        "--run-label", type=str, default="sample",
        choices=VALID_RUN_LABELS,
        help="Run label: sample (default), test100, full.",
    )
    parser.add_argument(
        "--confirm-full", action="store_true",
        help="Required when --run-label=full.",
    )
    parser.add_argument(
        "--sample-n-files", type=int, default=None,
        help="Randomly sample N files from points_raw.",
    )
    parser.add_argument(
        "--limit-files", type=int, default=None,
        help="Process only first N files.",
    )
    parser.add_argument(
        "--file-id", type=str, nargs="*", default=None,
        help="Process specific file_id(s).",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing output files.",
    )
    parser.add_argument(
        "--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
        help=f"Rows per batch when reading parquet (default: {DEFAULT_CHUNK_SIZE}).",
    )
    parser.add_argument(
        "--estimate-only", action="store_true",
        help="Print estimates and exit. No files written.",
    )
    args = parser.parse_args()

    run_label = args.run_label

    # Per-run-label log and error paths
    if run_label == "full":
        log_suffix = "full"
    else:
        log_suffix = run_label
    log_path = LOG_DIR / f"03_qc_multibeam_points_{log_suffix}.log"
    errors_tsv = LOG_DIR / f"03_qc_errors_{log_suffix}.tsv"

    logger = setup_logging(log_path)
    logger.info("=" * 60)
    logger.info("Starting 03_qc_multibeam_points.py")
    logger.info(f"Args: {vars(args)}")

    # Safety gate
    if run_label == "full" and not args.confirm_full:
        msg = "ABORTED: --run-label=full requires --confirm-full."
        logger.error(msg)
        print(f"ERROR: {msg}")
        sys.exit(1)

    # Load points_raw manifest
    if not RAW_MANIFEST_PQ.exists():
        logger.error(f"points_raw_manifest not found: {RAW_MANIFEST_PQ}")
        print(f"ERROR: points_raw_manifest not found: {RAW_MANIFEST_PQ}")
        sys.exit(1)

    raw_manifest = pd.read_parquet(RAW_MANIFEST_PQ)
    # Only process ok files from 02
    raw_manifest = raw_manifest[raw_manifest["status"] == "ok"].copy()
    logger.info(f"Loaded points_raw_manifest: {len(raw_manifest)} ok files")

    selected_total_lines = int(raw_manifest["rows_written"].sum())

    # Select files
    to_process = raw_manifest.copy()

    if args.file_id:
        to_process = to_process[to_process["file_id"].isin(args.file_id)]
    elif args.sample_n_files is not None:
        n = min(args.sample_n_files, len(to_process))
        to_process = to_process.sample(n=n, random_state=42)
    
    if args.limit_files is not None:
        to_process = to_process.head(args.limit_files)

    if len(to_process) == 0:
        logger.info("No files to process.")
        print("No files to process.")
        return

    # Resolve output paths
    output_dir, manifest_pq, manifest_tsv, report_path = get_run_paths(run_label)

    # Config summary
    summary = (
        f"\n{'='*60}\n"
        f"  CONFIG SUMMARY\n"
        f"{'='*60}\n"
        f"  input_dir:            {POINTS_RAW_DIR}\n"
        f"  raw_manifest:         {RAW_MANIFEST_PQ}\n"
        f"  total ok files:       {len(raw_manifest)}\n"
        f"  selected files:       {len(to_process)}\n"
        f"  selected_total_rows:  {selected_total_lines:,}\n"
        f"  run_label:            {run_label}\n"
        f"  output_dir:           {output_dir}\n"
        f"  confirm_full:         {args.confirm_full}\n"
        f"  estimate_only:        {args.estimate_only}\n"
        f"{'='*60}"
    )
    logger.info(summary)
    print(summary)

    if args.estimate_only:
        estimate_only(raw_manifest, output_dir, selected_total_lines, logger)
        return

    logger.info(f"Files to process: {len(to_process)}")

    # Process files
    manifest_entries = []
    errors = []
    t_start = datetime.now()

    for idx, (_, row) in enumerate(to_process.iterrows()):
        if idx % 100 == 0 and idx > 0:
            logger.info(f"  Progress: {idx}/{len(to_process)}")

        file_id = row["file_id"]
        pq_name = file_id_to_parquet_name(file_id)
        input_path = POINTS_RAW_DIR / pq_name

        result = process_file(
            file_id=file_id,
            input_path=input_path,
            output_dir=output_dir,
            chunk_size=args.chunk_size,
            overwrite=args.overwrite,
            logger=logger,
        )
        manifest_entries.append(result)
        if result["status"] == "error":
            errors.append(result)

    t_end = datetime.now()
    elapsed_s = (t_end - t_start).total_seconds()

    # Write manifest
    manifest_df = pd.DataFrame(manifest_entries)
    atomic_write_df(manifest_df, manifest_pq, manifest_tsv, logger)
    write_errors_tsv(errors, errors_tsv, logger)

    # Write QC report
    write_qc_report(report_path, manifest_df, run_label, elapsed_s, logger)

    # Summary
    ok_entries = [e for e in manifest_entries if e["status"] == "ok"]
    n_ok = len(ok_entries)
    n_skip = sum(1 for e in manifest_entries if e["status"] == "skipped_exists")
    n_err = sum(1 for e in manifest_entries if e["status"] == "error")
    total_rows = sum(e["rows_written"] for e in ok_entries)
    total_pass = sum(e["qc_pass_count"] for e in ok_entries)
    total_fail = total_rows - total_pass
    pass_rate = total_pass / total_rows if total_rows > 0 else 0.0

    # Output size
    output_bytes = 0
    if output_dir.exists():
        for f in output_dir.glob("*.parquet"):
            output_bytes += f.stat().st_size

    rows_per_sec = total_rows / elapsed_s if elapsed_s > 0 else 0

    report = f"""
{'='*60}
  RUN REPORT — 03_qc_multibeam_points.py
{'='*60}
  run_label:           {run_label}
  output_dir:          {output_dir}
  manifest:            {manifest_pq}
  files_processed:     {n_ok} ok, {n_skip} skipped, {n_err} errors
  total_rows:          {total_rows:,}
  qc_pass_basic:       {total_pass:,} ({pass_rate:.4%})
  qc_fail:             {total_fail:,} ({1-pass_rate:.4%})
  output_size:         {output_bytes / 1e6:.1f} MB
  bytes_per_row:       {output_bytes / total_rows:.1f}
  elapsed:             {elapsed_s:.1f}s
  rows/sec:            {rows_per_sec:,.0f}
  error_files:         {n_err}
{'='*60}
"""
    logger.info(report)
    print(report)


if __name__ == "__main__":
    main()
