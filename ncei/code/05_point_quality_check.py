#!/usr/bin/env python3
"""
05_point_quality_check.py

Step 03A — Build the bathymetry entry manifest (the curated "what to
actually use" registry across all 7,400 NCEI tracklines + 3 M.rar
quadrants) AND run a per-point quality check on every primary /
regional entry, emitting per-track parquet outputs with 6 extra boolean
flag columns appended.

Inputs (read-only):
  - ncei/manifests/trackline_source_manifest.parquet (PR-E1: 7,400 rows)
  - ncei/manifests/singlebeam_points_raw_manifest.parquet (PR-E2: nc-sb)
  - ncei/manifests/xyz_points_raw_manifest.parquet (PR-E3: xyz)
  - ncei/archive/zhoushuai_processed_M/cleaning_audit.parquet (PR-F)
  - ncei/archive/zhoushuai_processed_M/bathymetry_points.parquet (PR-F)
  - Per-track point parquets under ncei/derived/{singlebeam,multibeam}/points_raw/

Source priority rule (PRD Finding 2026-05-19 + Finding 2026-05-19c):
  - source_type=ncei_nc + has_depth + depth_sign_raw OK ........... primary
  - source_type=ncei_nc + (no_depth OR all_zero) .................. skip
  - source_type=ncei_xyz + xyz_only (sb or mb) .................... primary
  - source_type=ncei_xyz + nc_xyz_intersect ....................... supplementary
  - M.rar quadrants ............................................... regional

Expected entry counts (full mode):
  primary       = 1,850 (nc-sb) + 3,515 (xyz-sb-xyz_only) + 17 (xyz-mb) = 5,382
  supplementary = 1,850 (xyz intersect)
  skip          = 168   (nc_only: 135 no_depth + 33 all_zero)
  regional      = 3     (M.rar quadrants)
  TOTAL         = 7,403

Per-point quality checks (applied to primary + regional only):
  valid_lon            : (lon >= -180) AND (lon < 180)
  valid_lat            : (lat >= -90)  AND (lat <= 90)
  valid_depth_pos      : depth_m_positive_down > 0
  valid_depth_max      : depth_m_positive_down <= 11500
  valid_core_fields    : lon.notna() AND lat.notna() AND depth_m_positive_down.notna()
  point_check_pass_basic : AND of the 5 above

Outputs (full mode):
  - ncei/manifests/bathymetry_entry_manifest.parquet           (7,403 rows)
  - ncei/manifests/bathymetry_entry_manifest.tsv
  - ncei/docs/step03_point_quality_check_report.md
  - ncei/derived/singlebeam/points_checked/<id>__{nc,xyz}.parquet  (primary sb)
  - ncei/derived/multibeam/points_checked/<id>__xyz.parquet        (primary mb, 17)
  - ncei/derived/regional_mrar/points_checked/bathymetry_points.parquet (M.rar)
  - ncei/output/logs/05_point_quality_check.log
  - ncei/output/logs/05_point_quality_check_errors.tsv

Outputs (sample/test100 mode): suffix all of the above with `_<run-label>`
except the per-track parquet outputs (which always carry their canonical
filenames so re-runs simply overwrite under --overwrite).

Usage:
    python -m ncei.code.05_point_quality_check --estimate-only
    python -m ncei.code.05_point_quality_check --run-label sample --sample-n-files 5 --overwrite
    python -m ncei.code.05_point_quality_check --run-label test100 --limit-files 100 --overwrite
    python -m ncei.code.05_point_quality_check --run-label full --confirm-full --overwrite
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent  # ncei/
REPO_ROOT = ROOT_DIR.parent   # ship/

MANIFEST_DIR = ROOT_DIR / "manifests"
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"

DERIVED_SB_RAW = ROOT_DIR / "derived" / "singlebeam" / "points_raw"
DERIVED_MB_RAW = ROOT_DIR / "derived" / "multibeam" / "points_raw"
DERIVED_SB_CHK = ROOT_DIR / "derived" / "singlebeam" / "points_checked"
DERIVED_MB_CHK = ROOT_DIR / "derived" / "multibeam" / "points_checked"
DERIVED_REG_CHK = ROOT_DIR / "derived" / "regional_mrar" / "points_checked"

MRAR_DIR = ROOT_DIR / "archive" / "zhoushuai_processed_M"
MRAR_BATHY_PQ = MRAR_DIR / "bathymetry_points.parquet"
MRAR_AUDIT_PQ = MRAR_DIR / "cleaning_audit.parquet"

VALID_RUN_LABELS = ("sample", "test100", "full")
CHECK_VERSION = "point_check_v0.1.0"

# Per PRD Finding 2026-05-19: nc tracks with `has_depth=False` OR
# depth_sign_raw IN ('all_zero', 'no_depth_values') have no usable
# bathymetry depth and must be skipped at standardization /
# point-check stage.
ALLOWED_DEPTH_SIGN_RAW = ("mostly_positive", "mostly_negative")

# Per PRD Finding 2026-05-19b: universal upper-bound clip (sentinel
# pollution past Mariana Trench). Symmetric with the M.rar lower-bound.
DEPTH_VALID_MAX_M = 11500.0

# For M.rar streaming (one combined parquet input, ~113M rows).
MRAR_BATCH_SIZE = 500_000

EXPECTED_PRIMARY_COUNT = 5_382  # 1,850 nc + 3,515 xyz-sb + 17 xyz-mb
EXPECTED_SUPPLEMENTARY_COUNT = 1_850
EXPECTED_SKIP_COUNT = 168
EXPECTED_REGIONAL_COUNT = 3
EXPECTED_TOTAL_ENTRIES = 7_403

# Six new boolean flag columns appended to standardized point tables.
FLAG_COLUMNS = [
    "valid_lon",
    "valid_lat",
    "valid_depth_pos",
    "valid_depth_max",
    "valid_core_fields",
    "point_check_pass_basic",
]

# Entry manifest column order — must match brief verbatim.
ENTRY_MANIFEST_COLUMNS = [
    "track_id",
    "source_type",
    "source_completeness",
    "input_path",
    "instrument_class_pred",
    "bathymetry_eligible",
    "source_priority",
    "use_for_primary_bathymetry",
    "use_for_supplementary_bathymetry",
    "skip_reason",
    "depth_anomaly_flag",
    "n_points_in",
    "n_invalid_lon",
    "n_invalid_lat",
    "n_invalid_depth_pos",
    "n_invalid_depth_max",
    "n_missing_core",
    "n_points_pass",
    "output_path",
    "check_version",
]


# ---------------------------------------------------------------------------
# Paths / atomic writes / logging (mirrors 02/03/04 conventions)
# ---------------------------------------------------------------------------
def get_output_paths(run_label: str) -> dict[str, Path]:
    suffix = "" if run_label == "full" else f"_{run_label}"
    return {
        "entry_pq": MANIFEST_DIR / f"bathymetry_entry_manifest{suffix}.parquet",
        "entry_tsv": MANIFEST_DIR / f"bathymetry_entry_manifest{suffix}.tsv",
        "report_md": DOCS_DIR / f"step03_point_quality_check_report{suffix}.md",
        "log": LOG_DIR / f"05_point_quality_check{suffix}.log",
        "errors_tsv": LOG_DIR / f"05_point_quality_check_errors{suffix}.tsv",
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
    logger = logging.getLogger("ncei_point_quality_check")
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
# Entry-manifest construction (Part 1)
# ---------------------------------------------------------------------------
def repo_relative(path_or_str: object) -> Optional[str]:
    """Convert a possibly dataset-root-relative or absolute path to
    repo-root-relative (prefix `ncei/`).
    """
    if path_or_str is None:
        return None
    if isinstance(path_or_str, float) and np.isnan(path_or_str):
        return None
    s = str(path_or_str)
    if not s or s.lower() == "nan":
        return None
    p = Path(s)
    if p.is_absolute():
        try:
            return str(p.relative_to(REPO_ROOT))
        except ValueError:
            return s
    # Dataset-root-relative path (e.g. "tracklines_nc/64018.nc" or
    # "derived/singlebeam/points_raw/64018__nc.parquet") → prefix "ncei/".
    if s.startswith("ncei/"):
        return s
    return f"ncei/{s}"


def build_entry_rows(
    trackline_df: pd.DataFrame,
    nc_sb_df: pd.DataFrame,
    xyz_df: pd.DataFrame,
    mrar_audit_df: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """Compose the 7,403-row bathymetry entry manifest from upstream sources.

    Counts populated post-point-check are left as <NA>; the caller fills
    them in after running each entry through the per-point quality check.
    """
    # Index upstream per-track manifests by (track_id, source_completeness)
    # so we can join n_clipped + n_points_out cheaply.
    nc_sb_idx = nc_sb_df.set_index("track_id")[
        ["n_points_out", "n_clipped", "output_path"]
    ]
    xyz_idx = xyz_df.set_index("track_id")[
        [
            "source_completeness",
            "instrument_class_pred",
            "n_points_out",
            "n_clipped",
            "output_path",
        ]
    ]

    rows: list[dict] = []

    # --- ncei_nc rows (1,850 primary + 168 skip) ---------------------------
    nc_mask = trackline_df["source_type"] == "ncei_nc"
    for _, t in trackline_df[nc_mask].iterrows():
        track_id = str(t["track_id"])
        sc = str(t["source_completeness"])
        instr_pred = str(t["instrument_class_pred"])
        has_depth = bool(t["has_depth"])
        depth_sign = str(t["depth_sign_raw"])

        usable = (
            has_depth
            and depth_sign in ALLOWED_DEPTH_SIGN_RAW
        )

        if usable:
            # Primary (nc-sb has highest priority; nc-mb does not exist in the
            # nc archive per upstream classifier, but defensive: keep
            # instrument_class_pred verbatim).
            n_points_in = (
                int(nc_sb_idx.loc[track_id, "n_points_out"])
                if track_id in nc_sb_idx.index
                else None
            )
            n_clipped = (
                int(nc_sb_idx.loc[track_id, "n_clipped"])
                if track_id in nc_sb_idx.index
                else 0
            )
            output_rel = (
                str(nc_sb_idx.loc[track_id, "output_path"])
                if track_id in nc_sb_idx.index
                else None
            )
            row = {
                "track_id": track_id,
                "source_type": "ncei_nc",
                "source_completeness": sc,
                "input_path": repo_relative(output_rel),
                "instrument_class_pred": instr_pred,
                "bathymetry_eligible": True,
                "source_priority": "primary",
                "use_for_primary_bathymetry": True,
                "use_for_supplementary_bathymetry": False,
                "skip_reason": None,
                "depth_anomaly_flag": bool(n_clipped > 0),
                "n_points_in": n_points_in,
                "output_path_planned": str(
                    (DERIVED_SB_CHK / f"{track_id}__nc.parquet").relative_to(REPO_ROOT)
                ),
            }
        else:
            row = {
                "track_id": track_id,
                "source_type": "ncei_nc",
                "source_completeness": sc,
                "input_path": None,  # not standardized (skipped upstream)
                "instrument_class_pred": instr_pred,
                "bathymetry_eligible": False,
                "source_priority": "skip",
                "use_for_primary_bathymetry": False,
                "use_for_supplementary_bathymetry": False,
                "skip_reason": "no_usable_depth",
                "depth_anomaly_flag": False,
                "n_points_in": None,
                "output_path_planned": None,
            }
        rows.append(row)

    # --- ncei_xyz rows (1,850 supplementary + 3,532 primary) ---------------
    xyz_mask = trackline_df["source_type"] == "ncei_xyz"
    for _, t in trackline_df[xyz_mask].iterrows():
        track_id = str(t["track_id"])
        sc = str(t["source_completeness"])
        instr_pred = str(t["instrument_class_pred"])

        # Per-track xyz manifest may have richer info for n_clipped /
        # output_path; tolerate absence (e.g. partial sample runs upstream).
        if track_id in xyz_idx.index:
            n_points_in = int(xyz_idx.loc[track_id, "n_points_out"])
            n_clipped = int(xyz_idx.loc[track_id, "n_clipped"])
            output_rel_input = str(xyz_idx.loc[track_id, "output_path"])
        else:
            n_points_in = None
            n_clipped = 0
            output_rel_input = None

        if sc == "nc_xyz_intersect":
            # Per PRD Finding 2026-05-19c: xyz intersect → supplementary,
            # nc primary takes precedence.
            row = {
                "track_id": track_id,
                "source_type": "ncei_xyz",
                "source_completeness": sc,
                "input_path": repo_relative(output_rel_input),
                "instrument_class_pred": instr_pred,
                "bathymetry_eligible": True,
                "source_priority": "supplementary",
                "use_for_primary_bathymetry": False,
                "use_for_supplementary_bathymetry": True,
                "skip_reason": None,
                "depth_anomaly_flag": bool(n_clipped > 0),
                "n_points_in": n_points_in,
                "output_path_planned": None,  # supplementary not point-checked
            }
        else:  # xyz_only — primary, route by instrument_class_pred
            if instr_pred == "multibeam":
                planned = DERIVED_MB_CHK / f"{track_id}__xyz.parquet"
            else:
                planned = DERIVED_SB_CHK / f"{track_id}__xyz.parquet"
            row = {
                "track_id": track_id,
                "source_type": "ncei_xyz",
                "source_completeness": sc,
                "input_path": repo_relative(output_rel_input),
                "instrument_class_pred": instr_pred,
                "bathymetry_eligible": True,
                "source_priority": "primary",
                "use_for_primary_bathymetry": True,
                "use_for_supplementary_bathymetry": False,
                "skip_reason": None,
                "depth_anomaly_flag": bool(n_clipped > 0),
                "n_points_in": n_points_in,
                "output_path_planned": str(planned.relative_to(REPO_ROOT)),
            }
        rows.append(row)

    # --- M.rar regional rows (3 quadrants) ---------------------------------
    # Pull per-quadrant counts from the cleaning_audit parquet (excluding
    # the synthetic TOTALS row).
    quad_audit = mrar_audit_df[mrar_audit_df["quadrant"] != "TOTALS"].copy()
    combined_output = DERIVED_REG_CHK / "bathymetry_points.parquet"
    for _, q in quad_audit.iterrows():
        track_id = f"mrar_{q['quadrant']}"
        n_points_in = int(q["rows_bathymetry"])
        row = {
            "track_id": track_id,
            "source_type": "mrar_zhoushuai",
            "source_completeness": "mrar_regional",
            "input_path": str(MRAR_BATHY_PQ.relative_to(REPO_ROOT)),
            "instrument_class_pred": "multibeam",
            "bathymetry_eligible": True,
            "source_priority": "regional",
            "use_for_primary_bathymetry": False,
            "use_for_supplementary_bathymetry": False,
            "skip_reason": None,
            "depth_anomaly_flag": False,  # PR-F already cleaned sentinels
            "n_points_in": n_points_in,
            "output_path_planned": str(combined_output.relative_to(REPO_ROOT)),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    logger.info("Built entry manifest: %d rows", len(df))

    # Sanity-check the expected breakdown.
    by_prio = df["source_priority"].value_counts().to_dict()
    logger.info("Priority breakdown: %s", by_prio)
    return df


# ---------------------------------------------------------------------------
# Per-point quality check
# ---------------------------------------------------------------------------
def compute_flag_arrays(
    lon: np.ndarray,
    lat: np.ndarray,
    depth: np.ndarray,
) -> dict[str, np.ndarray]:
    """Vectorized per-row check.  Inputs may contain NaNs."""
    finite_lon = np.isfinite(lon)
    finite_lat = np.isfinite(lat)
    finite_depth = np.isfinite(depth)

    valid_lon = np.zeros(lon.shape[0], dtype=bool)
    valid_lat = np.zeros(lon.shape[0], dtype=bool)
    valid_depth_pos = np.zeros(lon.shape[0], dtype=bool)
    valid_depth_max = np.zeros(lon.shape[0], dtype=bool)

    if finite_lon.any():
        valid_lon[finite_lon] = (lon[finite_lon] >= -180.0) & (
            lon[finite_lon] < 180.0
        )
    if finite_lat.any():
        valid_lat[finite_lat] = (lat[finite_lat] >= -90.0) & (
            lat[finite_lat] <= 90.0
        )
    if finite_depth.any():
        valid_depth_pos[finite_depth] = depth[finite_depth] > 0.0
        valid_depth_max[finite_depth] = depth[finite_depth] <= DEPTH_VALID_MAX_M

    valid_core_fields = finite_lon & finite_lat & finite_depth
    pass_basic = (
        valid_lon
        & valid_lat
        & valid_depth_pos
        & valid_depth_max
        & valid_core_fields
    )
    return {
        "valid_lon": valid_lon,
        "valid_lat": valid_lat,
        "valid_depth_pos": valid_depth_pos,
        "valid_depth_max": valid_depth_max,
        "valid_core_fields": valid_core_fields,
        "point_check_pass_basic": pass_basic,
    }


def summarize_flags(flags: dict[str, np.ndarray]) -> dict[str, int]:
    """Per-track summary: count of rows that FAIL each check + total pass."""
    n_points = flags["valid_lon"].size
    return {
        "n_points_in": int(n_points),
        "n_invalid_lon": int((~flags["valid_lon"]).sum()),
        "n_invalid_lat": int((~flags["valid_lat"]).sum()),
        "n_invalid_depth_pos": int((~flags["valid_depth_pos"]).sum()),
        "n_invalid_depth_max": int((~flags["valid_depth_max"]).sum()),
        "n_missing_core": int((~flags["valid_core_fields"]).sum()),
        "n_points_pass": int(flags["point_check_pass_basic"].sum()),
    }


def attach_flag_columns(df: pd.DataFrame, flags: dict[str, np.ndarray]) -> pd.DataFrame:
    """Append the 6 flag columns to the input DataFrame in canonical order."""
    out = df.copy()
    for col in FLAG_COLUMNS:
        out[col] = flags[col]
    return out


def process_primary_entry(entry: pd.Series, overwrite: bool) -> dict:
    """Read the per-track raw parquet, compute flags, write the checked
    parquet, return per-entry count summary.
    """
    track_id = str(entry["track_id"])
    input_rel = entry["input_path"]
    output_rel = entry["output_path_planned"]
    if not input_rel or not output_rel:
        raise ValueError(
            f"missing input_path or output_path_planned for {track_id}"
        )
    input_path = REPO_ROOT / input_rel
    output_path = REPO_ROOT / output_rel
    if not input_path.exists():
        raise FileNotFoundError(f"input not found: {input_path}")
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"output exists; pass --overwrite to replace: {output_path}"
        )

    df = pd.read_parquet(input_path)
    expected_cols = 16
    if df.shape[1] != expected_cols:
        raise ValueError(
            f"{input_path}: expected {expected_cols} cols, got {df.shape[1]}"
        )

    lon = df["lon"].to_numpy(dtype=np.float64)
    lat = df["lat"].to_numpy(dtype=np.float64)
    depth = df["depth_m_positive_down"].to_numpy(dtype=np.float64)

    flags = compute_flag_arrays(lon, lat, depth)
    counts = summarize_flags(flags)

    out_df = attach_flag_columns(df, flags)
    atomic_write_parquet(out_df, output_path)
    counts["output_path"] = output_rel
    return counts


def process_regional_mrar(
    entries: pd.DataFrame,
    overwrite: bool,
    logger: logging.Logger,
) -> dict[str, dict]:
    """Stream the M.rar combined bathymetry parquet, aggregate per-track
    flag counts, write ONE combined output parquet.

    Returns dict keyed by track_id with per-track count dicts.
    """
    if not MRAR_BATHY_PQ.exists():
        raise FileNotFoundError(f"M.rar bathymetry parquet not found: {MRAR_BATHY_PQ}")

    track_ids = entries["track_id"].tolist()
    track_id_set = set(track_ids)

    output_path = DERIVED_REG_CHK / "bathymetry_points.parquet"
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"output exists; pass --overwrite to replace: {output_path}"
        )

    # Counters keyed by track_id (= quadrant filename, e.g. "mrar_0-180E-0-85N.txt").
    counters: dict[str, dict[str, int]] = {
        tid: {
            "n_points_in": 0,
            "n_invalid_lon": 0,
            "n_invalid_lat": 0,
            "n_invalid_depth_pos": 0,
            "n_invalid_depth_max": 0,
            "n_missing_core": 0,
            "n_points_pass": 0,
        }
        for tid in track_ids
    }

    pf = pq.ParquetFile(MRAR_BATHY_PQ)
    # Source schema (16 cols) + 6 flag cols → 22 cols target.
    src_schema = pf.schema_arrow
    out_fields = list(src_schema)
    for col in FLAG_COLUMNS:
        out_fields.append(pa.field(col, pa.bool_()))
    out_schema = pa.schema(out_fields)

    DERIVED_REG_CHK.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")

    n_rows_total = 0
    batch_idx = 0
    writer = pq.ParquetWriter(tmp_path, out_schema, compression="snappy")
    try:
        for batch in pf.iter_batches(batch_size=MRAR_BATCH_SIZE):
            batch_idx += 1
            df = batch.to_pandas()
            n = len(df)
            n_rows_total += n
            if n == 0:
                continue

            lon = df["lon"].to_numpy(dtype=np.float64)
            lat = df["lat"].to_numpy(dtype=np.float64)
            depth = df["depth_m_positive_down"].to_numpy(dtype=np.float64)
            flags = compute_flag_arrays(lon, lat, depth)

            # Per-track aggregation: group the batch by track_id.
            track_ids_arr = df["track_id"].to_numpy()
            for tid in np.unique(track_ids_arr):
                tid_str = str(tid)
                if tid_str not in track_id_set:
                    # Defensive: unknown quadrant in mrar parquet.
                    counters.setdefault(
                        tid_str,
                        {
                            "n_points_in": 0,
                            "n_invalid_lon": 0,
                            "n_invalid_lat": 0,
                            "n_invalid_depth_pos": 0,
                            "n_invalid_depth_max": 0,
                            "n_missing_core": 0,
                            "n_points_pass": 0,
                        },
                    )
                    track_id_set.add(tid_str)
                mask = track_ids_arr == tid
                tc = counters[tid_str]
                tc["n_points_in"] += int(mask.sum())
                tc["n_invalid_lon"] += int((~flags["valid_lon"][mask]).sum())
                tc["n_invalid_lat"] += int((~flags["valid_lat"][mask]).sum())
                tc["n_invalid_depth_pos"] += int((~flags["valid_depth_pos"][mask]).sum())
                tc["n_invalid_depth_max"] += int((~flags["valid_depth_max"][mask]).sum())
                tc["n_missing_core"] += int((~flags["valid_core_fields"][mask]).sum())
                tc["n_points_pass"] += int(flags["point_check_pass_basic"][mask].sum())

            # Write the batch with flag columns appended, preserving row
            # order (no rows dropped — audit trail).
            out_df = attach_flag_columns(df, flags)
            table = pa.Table.from_pandas(out_df, schema=out_schema, preserve_index=False)
            writer.write_table(table)

            if batch_idx % 20 == 0 or batch_idx == 1:
                logger.info(
                    "  mrar batch %d: rows=%d cum=%d",
                    batch_idx,
                    n,
                    n_rows_total,
                )
    finally:
        writer.close()

    os.replace(tmp_path, output_path)
    logger.info("  mrar combined output: %s (%d rows)", output_path, n_rows_total)

    output_rel = str(output_path.relative_to(REPO_ROOT))
    result: dict[str, dict] = {}
    for tid, tc in counters.items():
        out = dict(tc)
        out["output_path"] = output_rel
        result[tid] = out
    return result


# ---------------------------------------------------------------------------
# Selection (sample / test100 / full)
# ---------------------------------------------------------------------------
def select_workload(
    entry_df: pd.DataFrame,
    run_label: str,
    sample_n_files: Optional[int],
    limit_files: Optional[int],
    logger: logging.Logger,
) -> pd.DataFrame:
    """Pick the subset of work-eligible entries (primary + regional) to run
    point check on, based on the run-label.
    """
    work = entry_df[
        entry_df["source_priority"].isin(["primary", "regional"])
    ].copy()
    work = work.sort_values(["source_priority", "source_type", "track_id"]).reset_index(
        drop=True
    )

    if run_label == "full":
        return work

    if run_label == "test100":
        if limit_files is None:
            raise ValueError("test100 mode requires --limit-files")
        return work.head(limit_files).reset_index(drop=True)

    # sample mode: stratify across source_type so each bucket gets some
    # coverage (ncei_nc / ncei_xyz-sb / ncei_xyz-mb / mrar_zhoushuai).
    if sample_n_files is None:
        raise ValueError("sample mode requires --sample-n-files")

    rng = np.random.default_rng(42)
    strata: list[pd.DataFrame] = []

    nc_pool = work[work["source_type"] == "ncei_nc"]
    if len(nc_pool):
        k = min(sample_n_files, len(nc_pool))
        idx = sorted(rng.choice(len(nc_pool), size=k, replace=False).tolist())
        strata.append(nc_pool.iloc[idx])

    xyz_sb_pool = work[
        (work["source_type"] == "ncei_xyz")
        & (work["instrument_class_pred"] == "singlebeam")
    ]
    if len(xyz_sb_pool):
        k = min(sample_n_files, len(xyz_sb_pool))
        idx = sorted(rng.choice(len(xyz_sb_pool), size=k, replace=False).tolist())
        strata.append(xyz_sb_pool.iloc[idx])

    xyz_mb_pool = work[
        (work["source_type"] == "ncei_xyz")
        & (work["instrument_class_pred"] == "multibeam")
    ]
    if len(xyz_mb_pool):
        # Only 17 mb tracks total — take a few.
        k = min(max(2, sample_n_files // 2), len(xyz_mb_pool))
        idx = sorted(rng.choice(len(xyz_mb_pool), size=k, replace=False).tolist())
        strata.append(xyz_mb_pool.iloc[idx])

    mrar_pool = work[work["source_priority"] == "regional"]
    if len(mrar_pool):
        # Always include at least 1 mrar quadrant.
        k = min(1, len(mrar_pool))
        strata.append(mrar_pool.head(k))

    sampled = pd.concat(strata, ignore_index=True)
    logger.info("Sample stratified: %d entries selected", len(sampled))
    return sampled


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def markdown_table(df: pd.DataFrame, max_rows: int = 20) -> list[str]:
    if df is None or len(df) == 0:
        return ["_None_", ""]
    preview = df.head(max_rows).copy()
    cols = list(preview.columns)
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
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
    entry_df: pd.DataFrame,
    run_label: str,
    elapsed_s: float,
    n_processed: int,
    n_errors: int,
    paths: dict[str, Path],
) -> str:
    lines: list[str] = []
    lines.append("# NCEI Step 03A — Point Quality Check Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Run label: `{run_label}`")
    lines.append(f"Check version: `{CHECK_VERSION}`")
    lines.append(f"Elapsed: {elapsed_s:.1f}s")
    lines.append(f"Entries in manifest: {len(entry_df):,}")
    lines.append(f"Entries point-checked this run: {n_processed:,}")
    lines.append(f"Errors: {n_errors:,}")
    lines.append("")

    # ------- Section 2: entry manifest rollup -----------
    lines.append("## 2. Entry manifest rollup")
    lines.append("")
    lines.append("### By source_priority")
    lines.append("")
    prio = entry_df.groupby("source_priority", dropna=False).size().reset_index(
        name="entries"
    )
    lines.extend(markdown_table(prio))

    lines.append("### By source_type")
    lines.append("")
    st = entry_df.groupby("source_type", dropna=False).size().reset_index(name="entries")
    lines.extend(markdown_table(st))

    lines.append("### By source_completeness")
    lines.append("")
    sc = entry_df.groupby("source_completeness", dropna=False).size().reset_index(
        name="entries"
    )
    lines.extend(markdown_table(sc))

    lines.append("### By instrument_class_pred")
    lines.append("")
    icp = entry_df.groupby("instrument_class_pred", dropna=False).size().reset_index(
        name="entries"
    )
    lines.extend(markdown_table(icp))

    lines.append("### By skip_reason")
    lines.append("")
    sr = (
        entry_df[entry_df["source_priority"] == "skip"]
        .groupby("skip_reason", dropna=False)
        .size()
        .reset_index(name="entries")
    )
    lines.extend(markdown_table(sr))

    # ------- Section 3: point check rollup --------
    lines.append("## 3. Point check rollup (primary + regional)")
    lines.append("")
    work = entry_df[entry_df["source_priority"].isin(["primary", "regional"])].copy()
    # Only roll up across entries that were actually point-checked this run
    # (n_points_pass populated). In sample / test100 mode this excludes
    # entries whose n_points_in is filled from upstream manifests but were
    # never processed — preventing a misleading "full corpus denominator +
    # partial-run numerator" pass-rate.
    if "n_points_pass" in work.columns:
        processed = work[work["n_points_pass"].notna()]
    else:
        processed = work.iloc[0:0]
    rollup_cols = [
        "n_points_in",
        "n_invalid_lon",
        "n_invalid_lat",
        "n_invalid_depth_pos",
        "n_invalid_depth_max",
        "n_missing_core",
        "n_points_pass",
    ]
    total = {}
    for c in rollup_cols:
        if c in processed.columns:
            total[c] = int(
                pd.to_numeric(processed[c], errors="coerce").fillna(0).sum()
            )
        else:
            total[c] = 0
    pass_pct = (
        100.0 * total["n_points_pass"] / total["n_points_in"]
        if total["n_points_in"]
        else 0.0
    )
    summary_row = pd.DataFrame(
        [
            {
                "total_points_read": total["n_points_in"],
                "total_invalid_lon": total["n_invalid_lon"],
                "total_invalid_lat": total["n_invalid_lat"],
                "total_invalid_depth_pos": total["n_invalid_depth_pos"],
                "total_invalid_depth_max": total["n_invalid_depth_max"],
                "total_missing_core": total["n_missing_core"],
                "total_pass": total["n_points_pass"],
                "pass_rate_pct": round(pass_pct, 4),
            }
        ]
    )
    lines.extend(markdown_table(summary_row))

    # ------- Section 4: top tracks with most failed-check points -------
    lines.append("## 4. Top tracks with most failed-check points (per priority bucket)")
    lines.append("")
    # Same filter as Section 3: only rank entries actually processed this
    # run. Otherwise sample/test100 reports rank unprocessed entries first
    # (their `n_points_pass` is NA→0, so n_failed == n_points_in).
    if "n_points_in" in work.columns and len(processed):
        ranked = processed.copy()
        ranked["n_failed"] = (
            pd.to_numeric(ranked["n_points_in"], errors="coerce").fillna(0).astype(int)
            - pd.to_numeric(ranked["n_points_pass"], errors="coerce").fillna(0).astype(int)
        )
        for bucket in ("primary", "regional"):
            sub = ranked[ranked["source_priority"] == bucket].sort_values(
                "n_failed", ascending=False
            )
            if len(sub) == 0:
                continue
            lines.append(f"### {bucket}")
            lines.append("")
            preview = sub[
                ["track_id", "source_type", "n_points_in", "n_points_pass", "n_failed"]
            ].head(20)
            lines.extend(markdown_table(preview))

    # ------- Section 5: depth anomaly flag tracks ---------
    lines.append("## 5. Depth anomaly tracks (depth_anomaly_flag = True)")
    lines.append("")
    anom = entry_df[entry_df["depth_anomaly_flag"]].copy()
    lines.append(f"Total flagged: {len(anom):,}")
    lines.append("")
    if len(anom):
        preview = anom[
            [
                "track_id",
                "source_type",
                "source_priority",
                "instrument_class_pred",
                "depth_anomaly_flag",
            ]
        ].head(30)
        lines.extend(markdown_table(preview))

    # ------- Section 6: acceptance checks -----------
    lines.append("## 6. Acceptance checks")
    lines.append("")

    primary_intersect_count = int(
        (
            (entry_df["source_priority"] == "primary")
            & (entry_df["source_type"] == "ncei_xyz")
            & (entry_df["source_completeness"] == "nc_xyz_intersect")
        ).sum()
    )
    supplementary_count = int(
        (entry_df["source_priority"] == "supplementary").sum()
    )
    xyz_only_primary = int(
        (
            (entry_df["source_priority"] == "primary")
            & (entry_df["source_completeness"] == "xyz_only")
        ).sum()
    )
    nc_only_skip = int(
        (
            (entry_df["source_priority"] == "skip")
            & (entry_df["skip_reason"] == "no_usable_depth")
        ).sum()
    )

    ac_rows = [
        {
            "check": "primary xyz with completeness=nc_xyz_intersect (must be 0)",
            "observed": primary_intersect_count,
            "expected": 0,
            "ok": primary_intersect_count == 0,
        },
        {
            "check": "supplementary count (must be 1,850)",
            "observed": supplementary_count,
            "expected": EXPECTED_SUPPLEMENTARY_COUNT,
            "ok": supplementary_count == EXPECTED_SUPPLEMENTARY_COUNT,
        },
        {
            "check": "primary with completeness=xyz_only (must be 3,532)",
            "observed": xyz_only_primary,
            "expected": 3_532,
            "ok": xyz_only_primary == 3_532,
        },
        {
            "check": "skip with skip_reason='no_usable_depth' (must be 168)",
            "observed": nc_only_skip,
            "expected": EXPECTED_SKIP_COUNT,
            "ok": nc_only_skip == EXPECTED_SKIP_COUNT,
        },
    ]
    lines.extend(markdown_table(pd.DataFrame(ac_rows)))

    # ------- Section 7: path table -----------
    lines.append("## 7. Output paths")
    lines.append("")
    path_rows = [
        {
            "kind": "bathymetry entry manifest (parquet)",
            "path": str(paths["entry_pq"].relative_to(REPO_ROOT)),
        },
        {
            "kind": "bathymetry entry manifest (tsv)",
            "path": str(paths["entry_tsv"].relative_to(REPO_ROOT)),
        },
        {"kind": "report (this file)", "path": str(paths["report_md"].relative_to(REPO_ROOT))},
        {
            "kind": "primary sb points_checked dir",
            "path": str(DERIVED_SB_CHK.relative_to(REPO_ROOT)),
        },
        {
            "kind": "primary mb points_checked dir",
            "path": str(DERIVED_MB_CHK.relative_to(REPO_ROOT)),
        },
        {
            "kind": "regional M.rar points_checked dir",
            "path": str(DERIVED_REG_CHK.relative_to(REPO_ROOT)),
        },
    ]
    lines.extend(markdown_table(pd.DataFrame(path_rows)))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step 03A — Build bathymetry entry manifest + run per-point quality check"
    )
    parser.add_argument("--run-label", choices=VALID_RUN_LABELS, default="sample")
    parser.add_argument(
        "--sample-n-files",
        type=int,
        default=None,
        help="Stratified sample size per source_type bucket (required for sample mode)",
    )
    parser.add_argument(
        "--limit-files",
        type=int,
        default=None,
        help="First N work-eligible entries to process (required for test100 mode)",
    )
    parser.add_argument(
        "--confirm-full",
        action="store_true",
        help="Required when --run-label=full",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing entry-manifest + per-track points_checked outputs",
    )
    parser.add_argument(
        "--estimate-only",
        action="store_true",
        help="Print entry-manifest breakdown by priority + exit; no point check runs",
    )
    parser.add_argument(
        "--trackline-manifest",
        type=Path,
        default=MANIFEST_DIR / "trackline_source_manifest.parquet",
    )
    parser.add_argument(
        "--nc-sb-manifest",
        type=Path,
        default=MANIFEST_DIR / "singlebeam_points_raw_manifest.parquet",
    )
    parser.add_argument(
        "--xyz-manifest",
        type=Path,
        default=MANIFEST_DIR / "xyz_points_raw_manifest.parquet",
    )
    parser.add_argument(
        "--mrar-audit",
        type=Path,
        default=MRAR_AUDIT_PQ,
    )
    args = parser.parse_args()

    paths = get_output_paths(args.run_label)
    logger = setup_logging(paths["log"])
    t0 = datetime.now()

    logger.info("=" * 60)
    logger.info("05_point_quality_check.py START")
    logger.info("Args: %s", vars(args))

    # Validate input manifests exist.
    for label, p in (
        ("trackline_source_manifest", args.trackline_manifest),
        ("singlebeam_points_raw_manifest", args.nc_sb_manifest),
        ("xyz_points_raw_manifest", args.xyz_manifest),
        ("cleaning_audit", args.mrar_audit),
    ):
        if not p.exists():
            logger.error("ABORTED: missing input manifest %s at %s", label, p)
            return 2

    trackline_df = pd.read_parquet(args.trackline_manifest)
    nc_sb_df = pd.read_parquet(args.nc_sb_manifest)
    xyz_df = pd.read_parquet(args.xyz_manifest)
    mrar_audit_df = pd.read_parquet(args.mrar_audit)
    logger.info(
        "Loaded: trackline=%d, nc_sb=%d, xyz=%d, mrar_audit=%d",
        len(trackline_df),
        len(nc_sb_df),
        len(xyz_df),
        len(mrar_audit_df),
    )

    # Build entry manifest (Part 1).
    entry_df = build_entry_rows(
        trackline_df=trackline_df,
        nc_sb_df=nc_sb_df,
        xyz_df=xyz_df,
        mrar_audit_df=mrar_audit_df,
        logger=logger,
    )

    if args.estimate_only:
        print("Estimate only:")
        print(f"  total entries: {len(entry_df):,}")
        print("  by source_priority:")
        for prio, n in entry_df["source_priority"].value_counts().items():
            print(f"    {prio}: {n:,}")
        print("  by source_type:")
        for st, n in entry_df["source_type"].value_counts().items():
            print(f"    {st}: {n:,}")
        print("  by source_completeness:")
        for sc, n in entry_df["source_completeness"].value_counts().items():
            print(f"    {sc}: {n:,}")
        print("  by skip_reason (skip entries only):")
        skip_df = entry_df[entry_df["source_priority"] == "skip"]
        for sr, n in skip_df["skip_reason"].value_counts(dropna=False).items():
            print(f"    {sr}: {n:,}")
        return 0

    # Run-label gating.
    if args.run_label == "full" and not args.confirm_full:
        logger.error("ABORTED: --run-label=full requires --confirm-full")
        return 2
    if args.run_label == "sample" and args.sample_n_files is None:
        logger.error("ABORTED: sample mode requires --sample-n-files")
        return 2
    if args.run_label == "test100" and args.limit_files is None:
        logger.error("ABORTED: test100 mode requires --limit-files")
        return 2

    # Acceptance-count gate when in full mode: total entries must match
    # the expected 7,403 before we start (catches upstream manifest drift).
    if args.run_label == "full":
        if len(entry_df) != EXPECTED_TOTAL_ENTRIES:
            logger.error(
                "ABORTED: full-mode entry count expected %d (per PRD); got %d",
                EXPECTED_TOTAL_ENTRIES,
                len(entry_df),
            )
            return 3

    # Existing-output gate.
    output_files = [paths["entry_pq"], paths["entry_tsv"], paths["report_md"]]
    if not args.overwrite:
        existing = [p for p in output_files if p.exists()]
        if existing:
            logger.error(
                "ABORTED: outputs exist; use --overwrite. Existing: %s", existing
            )
            return 2

    # Select work + run point check (Part 2).
    work = select_workload(
        entry_df=entry_df,
        run_label=args.run_label,
        sample_n_files=args.sample_n_files,
        limit_files=args.limit_files,
        logger=logger,
    )
    logger.info("Will run point check on %d entries", len(work))

    # Initialize the post-check count columns so the manifest schema is
    # stable regardless of which subset got processed.
    int_count_cols = [
        "n_invalid_lon",
        "n_invalid_lat",
        "n_invalid_depth_pos",
        "n_invalid_depth_max",
        "n_missing_core",
        "n_points_pass",
    ]
    for c in int_count_cols:
        entry_df[c] = pd.NA
    entry_df["output_path"] = None
    entry_df["check_version"] = CHECK_VERSION

    errors: list[dict] = []
    n_processed = 0

    # Handle regional first (one streaming pass over the M.rar parquet).
    regional_work = work[work["source_priority"] == "regional"]
    if len(regional_work):
        try:
            mrar_counts = process_regional_mrar(
                entries=regional_work,
                overwrite=args.overwrite,
                logger=logger,
            )
            for tid, counts in mrar_counts.items():
                # Skip phantom quadrants not in the entry manifest.
                if tid not in set(entry_df["track_id"]):
                    continue
                row_mask = entry_df["track_id"] == tid
                entry_df.loc[row_mask, "n_points_in"] = counts["n_points_in"]
                for c in int_count_cols:
                    entry_df.loc[row_mask, c] = counts[c]
                entry_df.loc[row_mask, "output_path"] = counts["output_path"]
                n_processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Regional M.rar point check failed")
            errors.append(
                {
                    "track_id": "<mrar_combined>",
                    "source_type": "mrar_zhoushuai",
                    "error": repr(exc),
                }
            )
            for tid in regional_work["track_id"]:
                mask = entry_df["track_id"] == tid
                entry_df.loc[mask, "skip_reason"] = "point_check_error"

    # Handle primary entries (per-track parquets).
    primary_work = work[work["source_priority"] == "primary"]
    n_primary = len(primary_work)
    for i, (_, entry) in enumerate(primary_work.iterrows()):
        if i == 0 or (i + 1) % 100 == 0 or (i + 1) == n_primary:
            logger.info(
                "Primary %d/%d: %s (%s)",
                i + 1,
                n_primary,
                entry["track_id"],
                entry["source_type"],
            )
        try:
            counts = process_primary_entry(entry, overwrite=args.overwrite)
            row_mask = (entry_df["track_id"] == entry["track_id"]) & (
                entry_df["source_type"] == entry["source_type"]
            )
            entry_df.loc[row_mask, "n_points_in"] = counts["n_points_in"]
            for c in int_count_cols:
                entry_df.loc[row_mask, c] = counts[c]
            entry_df.loc[row_mask, "output_path"] = counts["output_path"]
            n_processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error point-checking %s", entry["track_id"])
            errors.append(
                {
                    "track_id": str(entry["track_id"]),
                    "source_type": str(entry["source_type"]),
                    "input_path": entry["input_path"],
                    "error": repr(exc),
                }
            )
            row_mask = (entry_df["track_id"] == entry["track_id"]) & (
                entry_df["source_type"] == entry["source_type"]
            )
            entry_df.loc[row_mask, "skip_reason"] = "point_check_error"

    # Finalize the entry manifest schema: select / reorder columns, coerce
    # integer count columns to nullable Int64 so empty rows are <NA>.
    # Drop the planning helper column.
    if "output_path_planned" in entry_df.columns:
        entry_df = entry_df.drop(columns=["output_path_planned"])

    for c in ["n_points_in", *int_count_cols]:
        entry_df[c] = pd.to_numeric(entry_df[c], errors="coerce").astype("Int64")

    entry_df = entry_df[ENTRY_MANIFEST_COLUMNS].sort_values(
        ["source_priority", "source_type", "track_id"]
    ).reset_index(drop=True)

    elapsed_s = (datetime.now() - t0).total_seconds()

    # Write outputs.
    atomic_write_parquet(entry_df, paths["entry_pq"])
    # TSV: full export for full runs; first 500 rows for partial runs.
    tsv_df = entry_df if args.run_label == "full" else entry_df.head(500).copy()
    atomic_write_tsv(tsv_df, paths["entry_tsv"])
    atomic_write_text(
        make_report(
            entry_df=entry_df,
            run_label=args.run_label,
            elapsed_s=elapsed_s,
            n_processed=n_processed,
            n_errors=len(errors),
            paths=paths,
        ),
        paths["report_md"],
    )
    atomic_write_tsv(pd.DataFrame(errors), paths["errors_tsv"])

    logger.info("Wrote %s (%d rows)", paths["entry_pq"], len(entry_df))
    logger.info("Wrote %s", paths["entry_tsv"])
    logger.info("Wrote %s", paths["report_md"])
    logger.info("Errors: %d", len(errors))
    logger.info("Elapsed: %.1fs", elapsed_s)
    logger.info("05_point_quality_check.py DONE")

    print(f"Entries in manifest: {len(entry_df):,}")
    print(f"Entries point-checked: {n_processed:,}")
    print(f"Errors: {len(errors):,}")
    print(f"Report: {paths['report_md']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
