#!/usr/bin/env python3
"""
04b_merge_multibeam_cells.py

Merge file-level cell statistics into global cell-level bathymetry product.

For each unique cell_id across all file-cell parquets, computes:
- File-balanced median and mean depth (unweighted average of file-cell medians)
- Point-weighted mean depth
- Between-file-cell variability (std, IQR, min, max, range)
- Source metadata (dominant file, cruise, track kind, data layout)
- Coverage counts (n_file_cells, n_files, n_cruises, n_subzips, etc.)

Reads:
  - derived/file_cells_1min/*.parquet          (from 04a)
  - manifests/file_cells_manifest_1min.parquet  (from 04a)

Writes (full mode, cell-size=1min):
  - derived/cells_1min/cells.parquet
  - manifests/cells_manifest_1min.parquet + .tsv
  - docs/cells_report_1min.md
  - output/logs/04b_merge_multibeam_cells_full.log
  - output/logs/04b_merge_cells_errors_full.tsv

Usage:
    # Sample: 50 random file-cell files
    python 04b_merge_multibeam_cells.py --run-label sample --cell-size 1min --sample-n-files 50 --overwrite

    # Test100
    python 04b_merge_multibeam_cells.py --run-label test100 --cell-size 1min --limit-files 100 --overwrite

    # Full run
    python 04b_merge_multibeam_cells.py --run-label full --cell-size 1min --confirm-full --overwrite

    # Estimate only
    python 04b_merge_multibeam_cells.py --run-label full --cell-size 1min --confirm-full --estimate-only
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent

# Input paths — fixed regardless of run_label
FC_DIR = ROOT_DIR / "derived" / "file_cells_1min"
FC_MANIFEST_PQ = ROOT_DIR / "manifests" / "file_cells_manifest_1min.parquet"

LOG_DIR = ROOT_DIR / "output" / "logs"

VALID_RUN_LABELS = ("sample", "test100", "full")
VALID_CELL_SIZES = ("1min",)

CELL_SIZES = {
    "1min": 1.0 / 60.0,
}


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
def get_run_paths(run_label: str, cell_size: str):
    """Return (output_dir, cells_parquet, manifest_pq, manifest_tsv, report_path)."""
    derived = ROOT_DIR / "derived"
    manifests = ROOT_DIR / "manifests"
    docs = ROOT_DIR / "docs"
    cs = cell_size
    if run_label == "full":
        return (
            derived / f"cells_{cs}",
            derived / f"cells_{cs}" / "cells.parquet",
            manifests / f"cells_manifest_{cs}.parquet",
            manifests / f"cells_manifest_{cs}.tsv",
            docs / f"cells_report_{cs}.md",
        )
    suffix = run_label
    return (
        derived / f"cells_{cs}_{suffix}",
        derived / f"cells_{cs}_{suffix}" / "cells.parquet",
        manifests / f"cells_manifest_{cs}_{suffix}.parquet",
        manifests / f"cells_manifest_{cs}_{suffix}.tsv",
        docs / f"cells_report_{cs}_{suffix}.md",
    )


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("merge_cells")
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
# Atomic write helpers
# ---------------------------------------------------------------------------
def atomic_write_parquet(df: pd.DataFrame, target: Path, logger: logging.Logger):
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    logger.info(f"  Wrote temp: {tmp.name} ({len(df):,} rows)")
    os.replace(tmp, target)
    logger.info(f"  Renamed to: {target.name}")


def atomic_write_tsv(df: pd.DataFrame, target: Path, logger: logging.Logger):
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tsv.tmp")
    df.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, target)
    logger.info(f"  Wrote manifest TSV: {target.name}")


def write_errors_tsv(errors: list[dict], errors_path: Path, logger: logging.Logger):
    if not errors:
        return
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    df_err = pd.DataFrame(errors)
    df_err.to_csv(errors_path, sep="\t", index=False)
    logger.info(f"Wrote {len(errors)} errors to {errors_path}")


# ---------------------------------------------------------------------------
# Read file-cell parquets
# ---------------------------------------------------------------------------
def read_file_cells(
    manifest_ok: pd.DataFrame,
    logger: logging.Logger,
) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    """Read all file-cell parquets listed in manifest_ok.

    Returns:
        (concatenated DataFrame, list of manifest entries, list of error dicts)
    """
    all_dfs = []
    manifest_entries = []
    errors = []
    total_rows = 0

    for idx, (_, row) in enumerate(manifest_ok.iterrows()):
        file_id = row["file_id"]
        fc_path = ROOT_DIR / row["output_path"]

        entry = {
            "file_id": file_id,
            "input_path": row["output_path"],
            "n_cells_in": 0,
            "n_points_in": 0,
            "status": "ok",
            "notes": "",
        }

        try:
            if not fc_path.exists():
                entry["status"] = "error"
                entry["notes"] = f"file not found: {fc_path}"
                errors.append(entry.copy())
                manifest_entries.append(entry)
                logger.warning(f"  SKIP (not found): {fc_path}")
                continue

            df = pd.read_parquet(fc_path)
            n_cells = len(df)
            n_pts = int(df["n_points"].sum()) if n_cells > 0 else 0

            entry["n_cells_in"] = n_cells
            entry["n_points_in"] = n_pts

            all_dfs.append(df)
            total_rows += n_cells

            if (idx + 1) % 500 == 0:
                logger.info(f"  Read {idx + 1}/{len(manifest_ok)} files, {total_rows:,} file-cell rows")

            manifest_entries.append(entry)

        except Exception as e:
            entry["status"] = "error"
            entry["notes"] = str(e)
            errors.append(entry.copy())
            manifest_entries.append(entry)
            logger.error(f"  ERROR reading {fc_path}: {e}")

    logger.info(f"  Read complete: {len(all_dfs)}/{len(manifest_ok)} files, {total_rows:,} file-cell rows")

    if not all_dfs:
        return pd.DataFrame(), manifest_entries, errors

    fc = pd.concat(all_dfs, ignore_index=True)
    logger.info(f"  Concatenated DataFrame: {len(fc):,} rows x {len(fc.columns)} columns")

    return fc, manifest_entries, errors


# ---------------------------------------------------------------------------
# Merge logic
# ---------------------------------------------------------------------------
def merge_cells(
    fc: pd.DataFrame,
    cell_size: str,
    logger: logging.Logger,
) -> pd.DataFrame:
    """Merge file-cells into global cells.

    Each output row = one unique cell_id with merged statistics.
    """
    if len(fc) == 0:
        logger.warning("Empty file-cell DataFrame — nothing to merge.")
        return pd.DataFrame()

    logger.info(f"Merging {len(fc):,} file-cell rows into global cells...")

    # Pre-compute helper columns
    fc["_weighted_depth"] = fc["mean_depth_m_positive_down"].values * fc["n_points"].values
    is_3col = (fc["data_layout"] == "lon_lat_depth_3col").astype(np.int32)
    is_6col = (fc["data_layout"] == "lon_lat_depth_time_sonar_6col").astype(np.int32)

    # --- Main aggregation ---
    logger.info("  Step 1/5: Main groupby aggregation...")
    agg = fc.groupby("cell_id").agg(
        lon_bin=("lon_bin", "first"),
        lat_bin=("lat_bin", "first"),
        lon_center=("lon_center", "first"),
        lat_center=("lat_center", "first"),
        n_points_total=("n_points", "sum"),
        n_files=("file_id", "nunique"),
        n_cruises_guess=("cruise_id_guess", "nunique"),
        n_subzips=("subzip_id", "nunique"),
        _sum_weighted_depth=("_weighted_depth", "sum"),
        _median_depth=("median_depth_m_positive_down", "median"),
        _mean_depth=("median_depth_m_positive_down", "mean"),
        _std_depth=("median_depth_m_positive_down", "std"),
        _min_depth_file_cell=("min_depth_m", "min"),
        _max_depth_file_cell=("max_depth_m", "max"),
    )

    # n_file_cells (group size)
    agg["n_file_cells"] = fc.groupby("cell_id").size()

    # --- Quantiles ---
    logger.info("  Step 2/5: Quantiles...")
    q25 = fc.groupby("cell_id")["median_depth_m_positive_down"].quantile(0.25)
    q75 = fc.groupby("cell_id")["median_depth_m_positive_down"].quantile(0.75)
    agg["_q25_depth"] = q25
    agg["_q75_depth"] = q75

    # --- Layout counts ---
    logger.info("  Step 3/5: Layout counts...")
    agg["n_3col_file_cells"] = is_3col.groupby(fc["cell_id"]).sum().astype(np.int32)
    agg["n_6col_file_cells"] = is_6col.groupby(fc["cell_id"]).sum().astype(np.int32)

    # --- Dominant file info ---
    logger.info("  Step 4/5: Dominant source info...")
    dominant_idx = fc.groupby("cell_id")["n_points"].idxmax()
    dominant = fc.loc[dominant_idx, ["cell_id", "file_id", "cruise_id_guess",
                                     "track_kind", "data_layout"]].copy()
    dominant.columns = ["cell_id", "dominant_file_id", "dominant_cruise_id_guess",
                        "dominant_track_kind", "dominant_data_layout"]

    # --- Assemble result ---
    logger.info("  Step 5/5: Assembling output...")
    result = agg.reset_index().merge(dominant, on="cell_id", how="left")

    # Derived columns
    result["cell_size"] = cell_size
    result["median_depth_file_balanced"] = result["_median_depth"]
    result["median_elev_file_balanced"] = -result["median_depth_file_balanced"]
    result["mean_depth_file_balanced"] = result["_mean_depth"]
    result["mean_elev_file_balanced"] = -result["mean_depth_file_balanced"]

    # Weighted mean depth (point-weighted)
    result["weighted_mean_depth_point_weighted"] = (
        result["_sum_weighted_depth"] / result["n_points_total"]
    )
    result["weighted_mean_elev_point_weighted"] = -result["weighted_mean_depth_point_weighted"]

    # Between-file-cell variability
    result["std_depth_between_file_cells"] = result["_std_depth"].fillna(0.0)
    result["q25_depth_between_file_cells"] = result["_q25_depth"]
    result["q75_depth_between_file_cells"] = result["_q75_depth"]
    result["iqr_depth_between_file_cells"] = result["_q75_depth"] - result["_q25_depth"]

    # Min/max/range across file-cells
    result["min_depth_file_cell"] = result["_min_depth_file_cell"]
    result["max_depth_file_cell"] = result["_max_depth_file_cell"]
    result["range_depth_file_cell"] = result["_max_depth_file_cell"] - result["_min_depth_file_cell"]

    result["source_dataset"] = "NCEI_multibeam"

    # Select and reorder output columns
    output_cols = [
        "cell_id", "cell_size", "lon_bin", "lat_bin", "lon_center", "lat_center",
        "median_depth_file_balanced", "median_elev_file_balanced",
        "mean_depth_file_balanced", "mean_elev_file_balanced",
        "weighted_mean_depth_point_weighted", "weighted_mean_elev_point_weighted",
        "std_depth_between_file_cells",
        "q25_depth_between_file_cells", "q75_depth_between_file_cells",
        "iqr_depth_between_file_cells",
        "min_depth_file_cell", "max_depth_file_cell", "range_depth_file_cell",
        "n_points_total", "n_file_cells", "n_files", "n_cruises_guess", "n_subzips",
        "n_3col_file_cells", "n_6col_file_cells",
        "dominant_file_id", "dominant_cruise_id_guess",
        "dominant_track_kind", "dominant_data_layout",
        "source_dataset",
    ]
    result = result[output_cols]

    logger.info(f"  Merged into {len(result):,} unique cells")
    return result


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def write_report(
    report_path: Path,
    result: pd.DataFrame,
    manifest_entries: list[dict],
    run_label: str,
    cell_size: str,
    elapsed_s: float,
    logger: logging.Logger,
):
    cell_deg = CELL_SIZES[cell_size]
    n_input_files = len(manifest_entries)
    n_input_ok = sum(1 for e in manifest_entries if e["status"] == "ok")
    n_input_err = sum(1 for e in manifest_entries if e["status"] == "error")
    total_input_fc_rows = sum(e["n_cells_in"] for e in manifest_entries if e["status"] == "ok")
    total_input_points = sum(e["n_points_in"] for e in manifest_entries if e["status"] == "ok")

    n_output_cells = len(result)
    n_overlap = int((result["n_file_cells"] > 1).sum()) if n_output_cells > 0 else 0

    lines = [
        f"# Cells Merge Report — {run_label} ({cell_size})",
        f"",
        f"Generated: {datetime.now().isoformat()}",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Cell size | {cell_size} ({cell_deg:.6f} deg) |",
        f"| Input file-cell files | {n_input_ok} ok, {n_input_err} errors ({n_input_files} total) |",
        f"| Input file-cell rows | {total_input_fc_rows:,} |",
        f"| Input total points | {total_input_points:,} |",
        f"| Output unique cells | {n_output_cells:,} |",
        f"| Overlap cells (n_file_cells > 1) | {n_overlap:,} ({100 * n_overlap / n_output_cells:.1f}%)" if n_output_cells > 0 else f"| Overlap cells | 0 |",
        f"| Elapsed | {elapsed_s:.1f}s |",
        f"| Backend | pandas |",
        f"",
    ]

    if n_output_cells > 0:
        lines.append(f"## Cell coverage distribution")
        lines.append(f"")
        lines.append(f"| Stat | n_file_cells | n_files | n_cruises_guess | n_points_total |")
        lines.append(f"|------|-------------|---------|-----------------|----------------|")
        for col in ["n_file_cells", "n_files", "n_cruises_guess", "n_points_total"]:
            pass  # Will add per-column stats below
        lines.append(f"")
        lines.append(f"### n_file_cells distribution")
        lines.append(f"")
        lines.append(f"| Stat | Value |")
        lines.append(f"|------|-------|")
        fc_counts = result["n_file_cells"]
        lines.append(f"| min | {int(fc_counts.min())} |")
        lines.append(f"| p25 | {float(fc_counts.quantile(0.25)):.0f} |")
        lines.append(f"| p50 | {float(fc_counts.quantile(0.50)):.0f} |")
        lines.append(f"| p75 | {float(fc_counts.quantile(0.75)):.0f} |")
        lines.append(f"| max | {int(fc_counts.max())} |")
        lines.append(f"| mean | {fc_counts.mean():.1f} |")
        lines.append(f"")

        lines.append(f"### n_points_total distribution")
        lines.append(f"")
        lines.append(f"| Stat | Value |")
        lines.append(f"|------|-------|")
        pts = result["n_points_total"]
        lines.append(f"| sum | {int(pts.sum()):,} |")
        lines.append(f"| min | {int(pts.min())} |")
        lines.append(f"| p50 | {float(pts.quantile(0.50)):.0f} |")
        lines.append(f"| max | {int(pts.max())} |")
        lines.append(f"| mean | {pts.mean():.1f} |")
        lines.append(f"")

        lines.append(f"## Depth statistics")
        lines.append(f"")
        for col in [
            "median_depth_file_balanced", "mean_depth_file_balanced",
            "weighted_mean_depth_point_weighted",
            "std_depth_between_file_cells", "iqr_depth_between_file_cells",
            "min_depth_file_cell", "max_depth_file_cell",
        ]:
            s = result[col]
            lines.append(f"### {col}")
            lines.append(f"")
            lines.append(f"| Stat | Value |")
            lines.append(f"|------|-------|")
            lines.append(f"| min | {float(s.min()):.2f} m |")
            lines.append(f"| p50 | {float(s.quantile(0.50)):.2f} m |")
            lines.append(f"| max | {float(s.max()):.2f} m |")
            lines.append(f"| mean | {float(s.mean()):.2f} m |")
            lines.append(f"")

        lines.append(f"## Categorical distributions")
        lines.append(f"")
        lines.append(f"### dominant_track_kind")
        lines.append(f"")
        vc = result["dominant_track_kind"].value_counts()
        for val, cnt in vc.items():
            lines.append(f"- {val}: {cnt:,}")
        lines.append(f"")
        lines.append(f"### dominant_data_layout")
        lines.append(f"")
        vc = result["dominant_data_layout"].value_counts()
        for val, cnt in vc.items():
            lines.append(f"- {val}: {cnt:,}")
        lines.append(f"")

    content = "\n".join(lines)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(content, encoding="utf-8")
    logger.info(f"Report written to {report_path}")


# ---------------------------------------------------------------------------
# Estimate only
# ---------------------------------------------------------------------------
def estimate_only(
    manifest_ok: pd.DataFrame,
    output_dir: Path,
    cell_size: str,
    logger: logging.Logger,
):
    n_files = len(manifest_ok)
    total_fc_rows = int(manifest_ok["n_cells"].sum()) if "n_cells" in manifest_ok.columns else 0
    total_points = int(manifest_ok["n_points_total"].sum()) if "n_points_total" in manifest_ok.columns else 0
    cell_deg = CELL_SIZES[cell_size]

    # Estimate unique cells: overlap reduces count
    # Typical overlap factor: 0.3-0.7 of file-cell rows are unique cells
    est_unique_cells = int(total_fc_rows * 0.5)  # rough estimate
    est_bytes_per_row = 200  # ~200 bytes per merged cell row
    est_output_mb = est_unique_cells * est_bytes_per_row / 1e6

    logger.info(f"Output dir would be: {output_dir}")
    logger.info(f"Input file-cell files: {n_files}")
    logger.info(f"Input file-cell rows: {total_fc_rows:,}")
    logger.info(f"Input total points: {total_points:,}")
    logger.info(f"Est. unique cells: ~{est_unique_cells:,}")
    logger.info(f"Est. output size: ~{est_output_mb:.1f} MB")

    print(f"\n{'=' * 60}")
    print(f"  ESTIMATE ONLY (no files written)")
    print(f"  cell_size:              {cell_size} ({cell_deg:.6f} deg)")
    print(f"  run_label target dir:   {output_dir}")
    print(f"  Input file-cell files:  {n_files}")
    print(f"  Input file-cell rows:   {total_fc_rows:,}")
    print(f"  Input total points:     {total_points:,}")
    print(f"  Est. unique cells:      ~{est_unique_cells:,}")
    print(f"  Est. output size:       ~{est_output_mb:.1f} MB")
    print(f"  Est. bytes/cell_row:    ~{est_bytes_per_row}")
    print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Merge file-level cell statistics into global cell-level bathymetry product.",
    )
    parser.add_argument(
        "--run-label", type=str, default="sample",
        choices=VALID_RUN_LABELS,
        help="Run label: sample (default), test100, full.",
    )
    parser.add_argument(
        "--cell-size", type=str, default="1min",
        choices=VALID_CELL_SIZES,
        help="Cell size: 1min (default).",
    )
    parser.add_argument(
        "--confirm-full", action="store_true",
        help="Required when --run-label=full.",
    )
    parser.add_argument(
        "--sample-n-files", type=int, default=None,
        help="Randomly sample N file-cell files from manifest.",
    )
    parser.add_argument(
        "--limit-files", type=int, default=None,
        help="Process only first N file-cell files.",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing output files.",
    )
    parser.add_argument(
        "--estimate-only", action="store_true",
        help="Print estimates and exit. No files written.",
    )
    args = parser.parse_args()

    run_label = args.run_label
    cell_size = args.cell_size
    cell_deg = CELL_SIZES[cell_size]

    log_suffix = run_label
    log_path = LOG_DIR / f"04b_merge_multibeam_cells_{log_suffix}.log"
    errors_tsv = LOG_DIR / f"04b_merge_cells_errors_{log_suffix}.tsv"

    logger = setup_logging(log_path)
    logger.info("=" * 60)
    logger.info("Starting 04b_merge_multibeam_cells.py")
    logger.info(f"Args: {vars(args)}")

    # Safety gate
    if run_label == "full" and not args.confirm_full:
        msg = "ABORTED: --run-label=full requires --confirm-full."
        logger.error(msg)
        print(f"ERROR: {msg}")
        sys.exit(1)

    # Load file-cell manifest
    if not FC_MANIFEST_PQ.exists():
        logger.error(f"file_cells_manifest not found: {FC_MANIFEST_PQ}")
        print(f"ERROR: file_cells_manifest not found: {FC_MANIFEST_PQ}")
        sys.exit(1)

    fc_manifest = pd.read_parquet(FC_MANIFEST_PQ)
    fc_manifest = fc_manifest[fc_manifest["status"] == "ok"].copy()
    logger.info(f"Loaded file_cells_manifest: {len(fc_manifest)} ok files")

    # Resolve output paths
    output_dir, cells_parquet, manifest_pq, manifest_tsv, report_path = get_run_paths(run_label, cell_size)

    # Select files to process
    to_process = fc_manifest.copy()

    if args.sample_n_files is not None:
        n = min(args.sample_n_files, len(to_process))
        to_process = to_process.sample(n=n, random_state=42)
        logger.info(f"Sampled {n} file-cell files")

    if args.limit_files is not None:
        to_process = to_process.head(args.limit_files)
        logger.info(f"Limited to first {len(to_process)} file-cell files")

    if len(to_process) == 0:
        logger.info("No files to process.")
        print("No files to process.")
        return

    # Config summary
    summary = (
        f"\n{'=' * 60}\n"
        f"  CONFIG SUMMARY\n"
        f"{'=' * 60}\n"
        f"  input_dir:            {FC_DIR}\n"
        f"  fc_manifest:          {FC_MANIFEST_PQ}\n"
        f"  total ok files:       {len(fc_manifest)}\n"
        f"  selected files:       {len(to_process)}\n"
        f"  cell_size:            {cell_size} ({cell_deg:.6f} deg)\n"
        f"  run_label:            {run_label}\n"
        f"  output_dir:           {output_dir}\n"
        f"  cells_parquet:        {cells_parquet}\n"
        f"  confirm_full:         {args.confirm_full}\n"
        f"  estimate_only:        {args.estimate_only}\n"
        f"  backend:              pandas\n"
        f"{'=' * 60}"
    )
    logger.info(summary)
    print(summary)

    if args.estimate_only:
        estimate_only(to_process, output_dir, cell_size, logger)
        return

    # Check overwrite
    if not args.overwrite and cells_parquet.exists():
        msg = f"Output already exists: {cells_parquet}. Use --overwrite to replace."
        logger.error(msg)
        print(f"ERROR: {msg}")
        sys.exit(1)

    t_start = datetime.now()

    # Step 1: Read file-cell parquets
    logger.info("Reading file-cell parquets...")
    fc, manifest_entries, read_errors = read_file_cells(to_process, logger)

    if len(fc) == 0:
        logger.error("No file-cell data read. Aborting.")
        print("ERROR: No file-cell data read.")
        write_errors_tsv(read_errors, errors_tsv, logger)
        return

    logger.info(f"Input: {len(fc):,} file-cell rows from {len(to_process)} files")
    logger.info(f"Input columns: {list(fc.columns)}")

    # Verify required columns
    required = [
        "cell_id", "lon_bin", "lat_bin", "lon_center", "lat_center",
        "file_id", "subzip_id", "cruise_id_guess", "track_kind", "data_layout",
        "median_depth_m_positive_down", "mean_depth_m_positive_down",
        "min_depth_m", "max_depth_m", "n_points",
    ]
    missing = [c for c in required if c not in fc.columns]
    if missing:
        logger.error(f"Missing required columns: {missing}")
        print(f"ERROR: Missing required columns: {missing}")
        write_errors_tsv(read_errors, errors_tsv, logger)
        return

    # Step 2: Merge cells
    result = merge_cells(fc, cell_size, logger)

    if len(result) == 0:
        logger.error("Merge produced no output cells.")
        print("ERROR: Merge produced no output cells.")
        write_errors_tsv(read_errors, errors_tsv, logger)
        return

    # Step 3: Write output
    logger.info("Writing output...")
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_parquet(result, cells_parquet, logger)

    # Step 4: Write manifest
    manifest_df = pd.DataFrame(manifest_entries)
    manifest_df.to_parquet(manifest_pq.with_suffix(".parquet.tmp"), index=False)
    manifest_df.to_csv(manifest_tsv.with_suffix(".tsv.tmp"), sep="\t", index=False)
    os.replace(manifest_pq.with_suffix(".parquet.tmp"), manifest_pq)
    os.replace(manifest_tsv.with_suffix(".tsv.tmp"), manifest_tsv)
    logger.info(f"Wrote manifest: {manifest_pq.name} ({len(manifest_df)} rows)")

    # Step 5: Write errors
    write_errors_tsv(read_errors, errors_tsv, logger)

    t_end = datetime.now()
    elapsed_s = (t_end - t_start).total_seconds()

    # Step 6: Write report
    write_report(report_path, result, manifest_entries, run_label, cell_size, elapsed_s, logger)

    # Step 7: Final summary
    n_output_cells = len(result)
    n_input_fc_rows = len(fc)
    total_input_points = int(fc["n_points"].sum())
    total_output_points = int(result["n_points_total"].sum())
    n_overlap = int((result["n_file_cells"] > 1).sum())
    n_read_errors = len(read_errors)

    # Output file size
    output_bytes = cells_parquet.stat().st_size if cells_parquet.exists() else 0
    bytes_per_cell = output_bytes / n_output_cells if n_output_cells > 0 else 0

    # Verify point conservation
    points_match = total_input_points == total_output_points

    report = f"""
{'=' * 60}
  RUN REPORT — 04b_merge_multibeam_cells.py
{'=' * 60}
  run_label:               {run_label}
  cell_size:               {cell_size} ({cell_deg:.6f} deg)
  output_dir:              {output_dir}
  cells_parquet:           {cells_parquet}
  manifest:                {manifest_pq}

  Input file-cell files:   {len(to_process)}
  Input file-cell rows:    {n_input_fc_rows:,}
  Input total points:      {total_input_points:,}
  Read errors:             {n_read_errors}

  Output unique cells:     {n_output_cells:,}
  Output total points:     {total_output_points:,}
  Points conserved:        {points_match}
  Overlap cells (>1 fc):   {n_overlap:,} ({100 * n_overlap / n_output_cells:.1f}% of cells)

  Output file size:        {output_bytes / 1e6:.2f} MB
  Bytes per cell:          {bytes_per_cell:.1f}

  Elapsed:                 {elapsed_s:.1f}s
  Backend:                 pandas
{'=' * 60}
"""
    logger.info(report)
    print(report)


if __name__ == "__main__":
    main()
