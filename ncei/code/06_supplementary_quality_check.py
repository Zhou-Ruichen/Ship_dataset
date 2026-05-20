#!/usr/bin/env python3
"""
06_supplementary_quality_check.py

Step 03B — Supplementary point-level quality checks layered on top of
Step 03A outputs. Diagnostic only: emits a parallel
`bathymetry_entry_manifest_supplementary.parquet` plus a per-pair
intersect-divergence audit and a Markdown report. **Does not modify
Step 03A artifacts, _common/, or any points_raw / points_checked
parquet.**

Inputs (read-only):
  - ncei/manifests/bathymetry_entry_manifest.parquet       (Step 03A)
  - ncei/manifests/singlebeam_points_raw_manifest.parquet  (PR-E2; for bbox)
  - ncei/manifests/xyz_points_raw_manifest.parquet         (PR-E3; for bbox)
  - ncei/derived/singlebeam/points_checked/*.parquet       (primary sb)
  - ncei/derived/multibeam/points_checked/*.parquet        (primary mb)
  - ncei/derived/regional_mrar/points_checked/bathymetry_points.parquet
  - ncei/derived/singlebeam/points_raw/<id>__xyz.parquet   (intersect xyz; Check D)

Four supplementary check categories:

  A. Finite-but-<=0 depth attribution
       n_depth_eq_zero        : count where depth_m_positive_down == 0
       n_depth_negative_finite: count where depth_m_positive_down < 0 finite
  B. Within-track duplicates (lon, lat, depth_m_positive_down triple)
       n_duplicate_points     : 2nd+ occurrences of an identical triple
       n_unique_triples       : distinct triples
  C. Within-track depth jump candidates (consecutive-row delta > 1000 m)
       n_depth_jump_candidates: per-track count; null for mrar regional
  D. Intersect dual-submission divergence (1,850 pairs)
       Separate per-pair output `intersect_divergence_audit.parquet`.

Outputs (full mode):
  - ncei/manifests/bathymetry_entry_manifest_supplementary.parquet  (7,403 x 26)
  - ncei/manifests/bathymetry_entry_manifest_supplementary.tsv
  - ncei/manifests/intersect_divergence_audit.parquet               (1,850 rows)
  - ncei/manifests/intersect_divergence_audit.tsv
  - ncei/docs/step03b_supplementary_checks_report.md
  - ncei/output/logs/06_supplementary_quality_check.log
  - ncei/output/logs/06_supplementary_quality_check_errors.tsv

Outputs (sample/test100 mode): suffix the manifest/report/log/errors_tsv
paths with `_<run-label>` (intersect-divergence audit always uses
canonical filename so a single sample run does not shadow full output).

Usage:
    python -m ncei.code.06_supplementary_quality_check --estimate-only
    python -m ncei.code.06_supplementary_quality_check --run-label sample --sample-n-files 5 --overwrite
    python -m ncei.code.06_supplementary_quality_check --run-label test100 --limit-files 100 --overwrite
    python -m ncei.code.06_supplementary_quality_check --run-label full --confirm-full --overwrite
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
import pyarrow.parquet as pq

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent  # ncei/
REPO_ROOT = ROOT_DIR.parent   # ship/

MANIFEST_DIR = ROOT_DIR / "manifests"
DOCS_DIR = ROOT_DIR / "docs"
LOG_DIR = ROOT_DIR / "output" / "logs"

DERIVED_SB_RAW = ROOT_DIR / "derived" / "singlebeam" / "points_raw"
DERIVED_SB_CHK = ROOT_DIR / "derived" / "singlebeam" / "points_checked"
DERIVED_MB_CHK = ROOT_DIR / "derived" / "multibeam" / "points_checked"
DERIVED_REG_CHK = ROOT_DIR / "derived" / "regional_mrar" / "points_checked"
MRAR_BATHY_CHK = DERIVED_REG_CHK / "bathymetry_points.parquet"

VALID_RUN_LABELS = ("sample", "test100", "full")
SUPP_CHECK_VERSION = "supp_check_v0.1.0"

# Per Check C: depth jump threshold (module constant, tunable in future PR).
# Singlebeam tracks rarely sample at <100m intervals, so a 1000m depth
# change between consecutive points indicates either a real seafloor
# discontinuity (volcanic islands, trench walls — TRUE positive worth
# review) or a sentinel/unit error (cm-vs-m).
JUMP_THRESHOLD_M = 1000.0

# Check D divergence thresholds.
DIVERGENT_COUNT_RATIO_LO = 0.5
DIVERGENT_COUNT_RATIO_HI = 2.0
DIVERGENT_BBOX_JACCARD_MIN = 0.5
DIVERGENT_DEPTH_MED_RATIO_LO = 0.5
DIVERGENT_DEPTH_MED_RATIO_HI = 2.0

# Streaming batch size for the 113M-row mrar parquet.
MRAR_BATCH_SIZE = 500_000

EXPECTED_TOTAL_ENTRIES = 7_403
EXPECTED_WORK_ENTRIES = 5_385       # 5,382 primary + 3 regional
EXPECTED_INTERSECT_PAIRS = 1_850

# Six new columns appended to the supplementary manifest (order matters).
NEW_COLUMNS = [
    "n_depth_eq_zero",
    "n_depth_negative_finite",
    "n_duplicate_points",
    "n_unique_triples",
    "n_depth_jump_candidates",
    "supplementary_check_version",
]


# ---------------------------------------------------------------------------
# Paths / atomic writes / logging (mirrors 05_*.py conventions)
# ---------------------------------------------------------------------------
def get_output_paths(run_label: str) -> dict[str, Path]:
    suffix = "" if run_label == "full" else f"_{run_label}"
    return {
        "supp_pq": MANIFEST_DIR / f"bathymetry_entry_manifest_supplementary{suffix}.parquet",
        "supp_tsv": MANIFEST_DIR / f"bathymetry_entry_manifest_supplementary{suffix}.tsv",
        "divergence_pq": MANIFEST_DIR / f"intersect_divergence_audit{suffix}.parquet",
        "divergence_tsv": MANIFEST_DIR / f"intersect_divergence_audit{suffix}.tsv",
        "report_md": DOCS_DIR / f"step03b_supplementary_checks_report{suffix}.md",
        "log": LOG_DIR / f"06_supplementary_quality_check{suffix}.log",
        "errors_tsv": LOG_DIR / f"06_supplementary_quality_check_errors{suffix}.tsv",
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
    logger = logging.getLogger("ncei_supplementary_quality_check")
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
# Per-track supplementary checks (Checks A, B, C) — primary entries
# ---------------------------------------------------------------------------
def compute_per_track_checks(
    lon: np.ndarray,
    lat: np.ndarray,
    depth: np.ndarray,
    *,
    do_jump_check: bool,
) -> dict[str, int]:
    """Compute Checks A, B, (optionally C) on a single track's arrays.

    Inputs may contain NaNs. Order is assumed to be the track's natural
    along-track order (input parquets are already sorted by
    point_index_in_track per Step 02/03/05 contract).
    """
    n = depth.shape[0]
    finite_depth = np.isfinite(depth)

    # ----- Check A: finite-but-<=0 depth attribution -----
    n_eq_zero = int(((depth == 0.0) & finite_depth).sum())
    n_neg_finite = int(((depth < 0.0) & finite_depth).sum())

    # ----- Check B: within-track exact duplicates of (lon, lat, depth) -----
    # Use pandas for the duplicate count — handles NaN==NaN as equal under
    # `.duplicated(keep='first')`, which is what we want for an exact-row
    # duplicate detector.
    triples = pd.DataFrame({"lon": lon, "lat": lat, "depth": depth})
    dup_mask = triples.duplicated(keep="first")
    n_dup = int(dup_mask.sum())
    n_unique = int(n - n_dup)

    out: dict[str, int] = {
        "n_depth_eq_zero": n_eq_zero,
        "n_depth_negative_finite": n_neg_finite,
        "n_duplicate_points": n_dup,
        "n_unique_triples": n_unique,
    }

    # ----- Check C: consecutive-row depth jumps -----
    if do_jump_check:
        if n < 2 or not finite_depth.any():
            out["n_depth_jump_candidates"] = 0
        else:
            # Consecutive-row delta computed only where both endpoints are
            # finite; NaN-flanked gaps contribute 0 candidates.
            d = depth
            both_finite = finite_depth[:-1] & finite_depth[1:]
            deltas = np.zeros(n - 1, dtype=np.float64)
            deltas[both_finite] = np.abs(d[1:][both_finite] - d[:-1][both_finite])
            out["n_depth_jump_candidates"] = int((deltas > JUMP_THRESHOLD_M).sum())
    else:
        out["n_depth_jump_candidates"] = None  # signaled as null in manifest

    return out


def process_primary_entry(entry: pd.Series) -> dict:
    """Read a primary entry's points_checked parquet and compute Checks A/B/C.

    Returns a counts dict suitable for manifest backfill.
    """
    output_rel = entry["output_path"]
    if not output_rel:
        raise ValueError(f"missing output_path for {entry['track_id']}")
    input_path = REPO_ROOT / output_rel
    if not input_path.exists():
        raise FileNotFoundError(f"points_checked parquet not found: {input_path}")

    # Read only the columns we need to keep this cheap on the 5k+ track loop.
    df = pd.read_parquet(input_path, columns=["lon", "lat", "depth_m_positive_down"])
    lon = df["lon"].to_numpy(dtype=np.float64)
    lat = df["lat"].to_numpy(dtype=np.float64)
    depth = df["depth_m_positive_down"].to_numpy(dtype=np.float64)
    return compute_per_track_checks(lon, lat, depth, do_jump_check=True)


# ---------------------------------------------------------------------------
# Regional M.rar: streaming Checks A + B (skip Check C — not track-ordered)
# ---------------------------------------------------------------------------
def process_regional_mrar(
    entries: pd.DataFrame,
    logger: logging.Logger,
) -> dict[str, dict]:
    """Stream the M.rar bathymetry_points.parquet, accumulating Check A
    counters per track_id and exact-triple sets for Check B.

    Returns dict keyed by track_id with the same field names as
    `compute_per_track_checks`. `n_depth_jump_candidates` is set to None
    (Check C skipped — mrar rows are not along-track ordered).
    """
    if not MRAR_BATHY_CHK.exists():
        raise FileNotFoundError(f"M.rar points_checked parquet missing: {MRAR_BATHY_CHK}")

    track_ids = set(entries["track_id"].astype(str).tolist())

    # Per-track accumulators.
    # For Check B we keep a streaming `set` of seen (lon, lat, depth) triples
    # per track. M.rar quadrants are ~40M rows each → ~600MB-1GB of Python
    # set entries; this is the simplest correct approach. If memory becomes
    # an issue in a future PR, swap for sorted-tempfile dedupe.
    n_eq_zero: dict[str, int] = {tid: 0 for tid in track_ids}
    n_neg_finite: dict[str, int] = {tid: 0 for tid in track_ids}
    n_points_seen: dict[str, int] = {tid: 0 for tid in track_ids}
    seen_triples: dict[str, set] = {tid: set() for tid in track_ids}
    n_dup: dict[str, int] = {tid: 0 for tid in track_ids}

    pf = pq.ParquetFile(MRAR_BATHY_CHK)
    batch_idx = 0
    n_rows_total = 0
    for batch in pf.iter_batches(
        batch_size=MRAR_BATCH_SIZE,
        columns=["track_id", "lon", "lat", "depth_m_positive_down"],
    ):
        batch_idx += 1
        df = batch.to_pandas()
        n = len(df)
        n_rows_total += n
        if n == 0:
            continue

        depth = df["depth_m_positive_down"].to_numpy(dtype=np.float64)
        finite_depth = np.isfinite(depth)

        track_id_arr = df["track_id"].to_numpy()
        for tid in np.unique(track_id_arr):
            tid_str = str(tid)
            if tid_str not in track_ids:
                # Not in the selected workload — silently skip (e.g. sample
                # mode picks only 1 mrar quadrant; the streaming pass still
                # sees rows from the other 2, by design).
                continue
            mask = track_id_arr == tid
            sub_depth = depth[mask]
            sub_finite = finite_depth[mask]

            # Check A — finite-but-<=0 attribution.
            n_eq_zero[tid_str] += int(((sub_depth == 0.0) & sub_finite).sum())
            n_neg_finite[tid_str] += int(((sub_depth < 0.0) & sub_finite).sum())

            # Check B — accumulate distinct triples + count dups in this batch.
            sub_lon = df.loc[mask, "lon"].to_numpy(dtype=np.float64)
            sub_lat = df.loc[mask, "lat"].to_numpy(dtype=np.float64)
            existing = seen_triples[tid_str]
            for lo, la, de in zip(sub_lon, sub_lat, sub_depth):
                key = (lo, la, de)
                if key in existing:
                    n_dup[tid_str] += 1
                else:
                    existing.add(key)

            n_points_seen[tid_str] += int(mask.sum())

        if batch_idx % 20 == 0 or batch_idx == 1:
            logger.info(
                "  mrar batch %d: rows=%d cum=%d",
                batch_idx,
                n,
                n_rows_total,
            )

    result: dict[str, dict] = {}
    for tid in track_ids:
        n_seen = n_points_seen[tid]
        result[tid] = {
            "n_depth_eq_zero": n_eq_zero[tid],
            "n_depth_negative_finite": n_neg_finite[tid],
            "n_duplicate_points": n_dup[tid],
            "n_unique_triples": int(n_seen - n_dup[tid]),
            "n_depth_jump_candidates": None,
        }
        logger.info(
            "  mrar %s: n_eq_zero=%d n_neg=%d n_dup=%d n_unique=%d",
            tid,
            n_eq_zero[tid],
            n_neg_finite[tid],
            n_dup[tid],
            n_seen - n_dup[tid],
        )
        # Free memory before the next track's batch arrives.
        seen_triples[tid].clear()
    return result


# ---------------------------------------------------------------------------
# Check D — intersect dual-submission divergence
# ---------------------------------------------------------------------------
def bbox_jaccard(
    nc_lon_min: float,
    nc_lon_max: float,
    nc_lat_min: float,
    nc_lat_max: float,
    xyz_lon_min: float,
    xyz_lon_max: float,
    xyz_lat_min: float,
    xyz_lat_max: float,
) -> float:
    """Axis-aligned bbox Jaccard (intersection-over-union).

    Returns 0.0 if either bbox is degenerate or boxes do not overlap; 1.0
    when bboxes coincide. Both inputs are in lon-lat degrees — Jaccard is
    computed in lon*lat units (consistent with the supplementary-check
    semantics where it is only used as a divergence flag, not as physical
    area).
    """
    if any(
        not np.isfinite(v)
        for v in (
            nc_lon_min,
            nc_lon_max,
            nc_lat_min,
            nc_lat_max,
            xyz_lon_min,
            xyz_lon_max,
            xyz_lat_min,
            xyz_lat_max,
        )
    ):
        return 0.0
    ix_lon = max(0.0, min(nc_lon_max, xyz_lon_max) - max(nc_lon_min, xyz_lon_min))
    ix_lat = max(0.0, min(nc_lat_max, xyz_lat_max) - max(nc_lat_min, xyz_lat_min))
    intersection = ix_lon * ix_lat

    nc_area = max(0.0, nc_lon_max - nc_lon_min) * max(0.0, nc_lat_max - nc_lat_min)
    xyz_area = max(0.0, xyz_lon_max - xyz_lon_min) * max(0.0, xyz_lat_max - xyz_lat_min)
    union = nc_area + xyz_area - intersection
    if union <= 0.0:
        return 0.0
    return float(intersection / union)


def process_intersect_pair(
    track_id: str,
    nc_bbox: tuple[float, float, float, float],
    xyz_bbox: tuple[float, float, float, float],
    nc_checked_path: Path,
    xyz_raw_path: Path,
) -> dict:
    """Compute the Check D row for one (nc, xyz) intersect pair.

    nc side: read `point_check_pass_basic` + `depth_m_positive_down` from
    nc points_checked parquet → valid count + depth median.
    xyz side: read `depth_m_positive_down` from xyz points_raw parquet,
    define valid = `finite(depth) AND depth > 0` (mirroring Step 03A's
    valid-bathymetry semantics; supplementary xyz never went through
    points_checked).
    """
    if not nc_checked_path.exists():
        raise FileNotFoundError(f"nc points_checked missing: {nc_checked_path}")
    if not xyz_raw_path.exists():
        raise FileNotFoundError(f"xyz points_raw missing: {xyz_raw_path}")

    nc_df = pd.read_parquet(
        nc_checked_path,
        columns=["depth_m_positive_down", "point_check_pass_basic"],
    )
    n_raw_nc = int(len(nc_df))
    nc_valid_mask = nc_df["point_check_pass_basic"].to_numpy(dtype=bool)
    n_valid_nc = int(nc_valid_mask.sum())
    if n_valid_nc > 0:
        depth_med_nc = float(
            np.nanmedian(nc_df.loc[nc_valid_mask, "depth_m_positive_down"].to_numpy())
        )
    else:
        depth_med_nc = float("nan")

    xyz_df = pd.read_parquet(xyz_raw_path, columns=["depth_m_positive_down"])
    n_raw_xyz = int(len(xyz_df))
    xyz_depth = xyz_df["depth_m_positive_down"].to_numpy(dtype=np.float64)
    xyz_valid_mask = np.isfinite(xyz_depth) & (xyz_depth > 0.0)
    n_valid_xyz = int(xyz_valid_mask.sum())
    if n_valid_xyz > 0:
        depth_med_xyz = float(np.nanmedian(xyz_depth[xyz_valid_mask]))
    else:
        depth_med_xyz = float("nan")

    if n_valid_xyz > 0:
        valid_count_ratio = float(n_valid_nc / n_valid_xyz)
    else:
        valid_count_ratio = float("nan")

    if np.isfinite(depth_med_nc) and np.isfinite(depth_med_xyz) and depth_med_xyz > 0:
        depth_med_ratio = float(depth_med_nc / depth_med_xyz)
    else:
        depth_med_ratio = float("nan")

    jaccard = bbox_jaccard(*nc_bbox, *xyz_bbox)

    divergent_count = (
        not np.isfinite(valid_count_ratio)
        or valid_count_ratio < DIVERGENT_COUNT_RATIO_LO
        or valid_count_ratio > DIVERGENT_COUNT_RATIO_HI
    )
    divergent_bbox = jaccard < DIVERGENT_BBOX_JACCARD_MIN
    divergent_depth = (
        not np.isfinite(depth_med_ratio)
        or depth_med_ratio < DIVERGENT_DEPTH_MED_RATIO_LO
        or depth_med_ratio > DIVERGENT_DEPTH_MED_RATIO_HI
    )
    divergent_flag = bool(divergent_count or divergent_bbox or divergent_depth)

    return {
        "track_id": track_id,
        "n_raw_nc": n_raw_nc,
        "n_valid_nc": n_valid_nc,
        "n_raw_xyz": n_raw_xyz,
        "n_valid_xyz": n_valid_xyz,
        "valid_count_ratio": valid_count_ratio,
        "nc_bbox_lon_min": nc_bbox[0],
        "nc_bbox_lon_max": nc_bbox[1],
        "nc_bbox_lat_min": nc_bbox[2],
        "nc_bbox_lat_max": nc_bbox[3],
        "xyz_bbox_lon_min": xyz_bbox[0],
        "xyz_bbox_lon_max": xyz_bbox[1],
        "xyz_bbox_lat_min": xyz_bbox[2],
        "xyz_bbox_lat_max": xyz_bbox[3],
        "bbox_overlap_jaccard": jaccard,
        "depth_med_nc": depth_med_nc,
        "depth_med_xyz": depth_med_xyz,
        "depth_med_ratio": depth_med_ratio,
        "divergent_flag": divergent_flag,
    }


# ---------------------------------------------------------------------------
# Selection (sample / test100 / full) — mirrors 05_*.py
# ---------------------------------------------------------------------------
def select_workload(
    entry_df: pd.DataFrame,
    run_label: str,
    sample_n_files: Optional[int],
    limit_files: Optional[int],
    logger: logging.Logger,
) -> pd.DataFrame:
    """Pick the subset of work-eligible entries (primary + regional)."""
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

    # sample mode — stratify across source_type + always include 1 mrar
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
        k = min(max(2, sample_n_files // 2), len(xyz_mb_pool))
        idx = sorted(rng.choice(len(xyz_mb_pool), size=k, replace=False).tolist())
        strata.append(xyz_mb_pool.iloc[idx])

    mrar_pool = work[work["source_priority"] == "regional"]
    if len(mrar_pool):
        strata.append(mrar_pool.head(1))

    sampled = pd.concat(strata, ignore_index=True)
    logger.info("Sample stratified: %d entries selected", len(sampled))
    return sampled


def select_intersect_pairs(
    entry_df: pd.DataFrame,
    nc_sb_df: pd.DataFrame,
    xyz_df: pd.DataFrame,
    run_label: str,
    sample_n_files: Optional[int],
    limit_files: Optional[int],
    work: pd.DataFrame,
) -> pd.DataFrame:
    """Build the list of (track_id, nc_bbox, xyz_bbox, paths) for Check D.

    For sample/test100, restrict to intersect tracks that appear in the
    selected primary `work` set so the run is self-consistent. For full,
    return all 1,850.
    """
    # Identify the 1,850 nc-side intersect entries.
    nc_intersect = entry_df[
        (entry_df["source_type"] == "ncei_nc")
        & (entry_df["source_completeness"] == "nc_xyz_intersect")
        & (entry_df["source_priority"] == "primary")
    ].copy()

    # xyz-side intersect entries (the 1,850 supplementary rows).
    xyz_intersect = entry_df[
        (entry_df["source_priority"] == "supplementary")
        & (entry_df["source_completeness"] == "nc_xyz_intersect")
    ].copy()

    # Restrict to track_ids common to both sides (defensive).
    common_ids = sorted(
        set(nc_intersect["track_id"]) & set(xyz_intersect["track_id"])
    )

    if run_label != "full":
        # Restrict to the nc-intersect track_ids that ended up in `work`.
        work_nc_ids = set(
            work.loc[
                (work["source_type"] == "ncei_nc")
                & (work["source_completeness"] == "nc_xyz_intersect"),
                "track_id",
            ].tolist()
        )
        common_ids = sorted(set(common_ids) & work_nc_ids)
        # Make sure there are at least 5 pairs for a sample run; if work
        # underfilled the nc-intersect bucket, pad from the global set.
        if run_label == "sample":
            need = max(5, len(common_ids))
            if len(common_ids) < 5:
                extra_pool = sorted(
                    set(nc_intersect["track_id"]) & set(xyz_intersect["track_id"])
                )
                rng = np.random.default_rng(123)
                pad = [t for t in extra_pool if t not in set(common_ids)]
                if pad:
                    pad_idx = rng.choice(
                        len(pad), size=min(need - len(common_ids), len(pad)), replace=False
                    )
                    common_ids = sorted(
                        set(common_ids) | {pad[int(i)] for i in pad_idx}
                    )

    # Index bbox sources by track_id for cheap lookup.
    nc_bbox_idx = nc_sb_df.set_index("track_id")[
        ["bbox_lon_min", "bbox_lon_max", "bbox_lat_min", "bbox_lat_max"]
    ]
    xyz_bbox_idx = xyz_df[xyz_df["source_completeness"] == "nc_xyz_intersect"].set_index(
        "track_id"
    )[["bbox_lon_min", "bbox_lon_max", "bbox_lat_min", "bbox_lat_max"]]

    rows: list[dict] = []
    for tid in common_ids:
        if tid not in nc_bbox_idx.index or tid not in xyz_bbox_idx.index:
            continue
        nc_b = nc_bbox_idx.loc[tid]
        xyz_b = xyz_bbox_idx.loc[tid]
        rows.append(
            {
                "track_id": tid,
                "nc_bbox": (
                    float(nc_b["bbox_lon_min"]),
                    float(nc_b["bbox_lon_max"]),
                    float(nc_b["bbox_lat_min"]),
                    float(nc_b["bbox_lat_max"]),
                ),
                "xyz_bbox": (
                    float(xyz_b["bbox_lon_min"]),
                    float(xyz_b["bbox_lon_max"]),
                    float(xyz_b["bbox_lat_min"]),
                    float(xyz_b["bbox_lat_max"]),
                ),
                "nc_checked_path": DERIVED_SB_CHK / f"{tid}__nc.parquet",
                "xyz_raw_path": DERIVED_SB_RAW / f"{tid}__xyz.parquet",
            }
        )
    return pd.DataFrame(rows)


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
    supp_df: pd.DataFrame,
    divergence_df: pd.DataFrame,
    run_label: str,
    elapsed_s: float,
    n_processed: int,
    n_errors: int,
    paths: dict[str, Path],
) -> str:
    lines: list[str] = []
    lines.append("# NCEI Step 03B — Supplementary Quality Check Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Run label: `{run_label}`")
    lines.append(f"Check version: `{SUPP_CHECK_VERSION}`")
    lines.append(f"Elapsed: {elapsed_s:.1f}s")
    lines.append(f"Entries in supplementary manifest: {len(supp_df):,}")
    lines.append(f"Entries supplementary-checked this run: {n_processed:,}")
    lines.append(f"Intersect pairs in divergence audit: {len(divergence_df):,}")
    lines.append(f"Errors: {n_errors:,}")
    lines.append("")
    lines.append(f"Check C jump threshold: `{JUMP_THRESHOLD_M:.0f} m` (module constant)")
    lines.append("")

    # Only consider rows that were actually checked this run (n_unique_triples
    # is the most reliable "processed" signal — it's null for unchecked rows).
    processed_mask = supp_df["n_unique_triples"].notna()
    proc = supp_df[processed_mask].copy()

    # ----- Check A — finite-but-<=0 depth attribution -----
    lines.append("## A. Finite-but-≤0 depth attribution")
    lines.append("")
    if len(proc):
        a_total = pd.DataFrame(
            [
                {
                    "total_n_depth_eq_zero": int(
                        pd.to_numeric(proc["n_depth_eq_zero"], errors="coerce").fillna(0).sum()
                    ),
                    "total_n_depth_negative_finite": int(
                        pd.to_numeric(proc["n_depth_negative_finite"], errors="coerce").fillna(0).sum()
                    ),
                }
            ]
        )
        lines.extend(markdown_table(a_total))

        a_by_src = proc.groupby("source_type", dropna=False).agg(
            entries=("track_id", "size"),
            n_depth_eq_zero=("n_depth_eq_zero", lambda s: int(pd.to_numeric(s, errors="coerce").fillna(0).sum())),
            n_depth_negative_finite=("n_depth_negative_finite", lambda s: int(pd.to_numeric(s, errors="coerce").fillna(0).sum())),
        ).reset_index()
        lines.append("### A1. By source_type")
        lines.append("")
        lines.extend(markdown_table(a_by_src))

        lines.append("### A2. Top-20 tracks by n_depth_eq_zero")
        lines.append("")
        top_zero = proc.sort_values("n_depth_eq_zero", ascending=False, na_position="last").head(20)
        lines.extend(
            markdown_table(
                top_zero[["track_id", "source_type", "n_points_in", "n_depth_eq_zero"]]
            )
        )

        lines.append("### A3. Top-20 tracks by n_depth_negative_finite")
        lines.append("")
        top_neg = proc.sort_values("n_depth_negative_finite", ascending=False, na_position="last").head(20)
        lines.extend(
            markdown_table(
                top_neg[["track_id", "source_type", "n_points_in", "n_depth_negative_finite"]]
            )
        )
    else:
        lines.append("_No processed entries this run._")
        lines.append("")

    # ----- Check B — within-track duplicates -----
    lines.append("## B. Within-track exact-triple duplicates")
    lines.append("")
    if len(proc):
        b_total = pd.DataFrame(
            [
                {
                    "total_n_duplicate_points": int(
                        pd.to_numeric(proc["n_duplicate_points"], errors="coerce").fillna(0).sum()
                    ),
                    "total_n_unique_triples": int(
                        pd.to_numeric(proc["n_unique_triples"], errors="coerce").fillna(0).sum()
                    ),
                    "tracks_with_any_dup": int(
                        (pd.to_numeric(proc["n_duplicate_points"], errors="coerce").fillna(0) > 0).sum()
                    ),
                    "tracks_processed": int(len(proc)),
                }
            ]
        )
        lines.extend(markdown_table(b_total))

        b_by_src = proc.groupby("source_type", dropna=False).agg(
            entries=("track_id", "size"),
            n_duplicate_points=("n_duplicate_points", lambda s: int(pd.to_numeric(s, errors="coerce").fillna(0).sum())),
            n_unique_triples=("n_unique_triples", lambda s: int(pd.to_numeric(s, errors="coerce").fillna(0).sum())),
        ).reset_index()
        lines.append("### B1. By source_type")
        lines.append("")
        lines.extend(markdown_table(b_by_src))

        lines.append("### B2. Top-20 tracks by n_duplicate_points")
        lines.append("")
        top_dup = proc.sort_values("n_duplicate_points", ascending=False, na_position="last").head(20)
        lines.extend(
            markdown_table(
                top_dup[["track_id", "source_type", "n_points_in", "n_duplicate_points", "n_unique_triples"]]
            )
        )
    else:
        lines.append("_No processed entries this run._")
        lines.append("")

    # ----- Check C — depth jumps -----
    lines.append("## C. Within-track depth jump candidates")
    lines.append(f"Threshold: |Δdepth| > {JUMP_THRESHOLD_M:.0f} m between consecutive points")
    lines.append("(mrar regional is skipped — rows not along-track ordered)")
    lines.append("")
    if len(proc):
        proc_with_c = proc[proc["n_depth_jump_candidates"].notna()]
        c_total = pd.DataFrame(
            [
                {
                    "total_n_depth_jump_candidates": int(
                        pd.to_numeric(proc_with_c["n_depth_jump_candidates"], errors="coerce").fillna(0).sum()
                    ),
                    "tracks_with_jumps": int(
                        (pd.to_numeric(proc_with_c["n_depth_jump_candidates"], errors="coerce").fillna(0) > 0).sum()
                    ),
                    "tracks_checked_for_jumps": int(len(proc_with_c)),
                }
            ]
        )
        lines.extend(markdown_table(c_total))

        lines.append("### C1. Top-20 tracks by n_depth_jump_candidates")
        lines.append("")
        top_jump = proc_with_c.sort_values(
            "n_depth_jump_candidates", ascending=False, na_position="last"
        ).head(20)
        lines.extend(
            markdown_table(
                top_jump[["track_id", "source_type", "n_points_in", "n_depth_jump_candidates"]]
            )
        )
    else:
        lines.append("_No processed entries this run._")
        lines.append("")

    # ----- Check D — intersect divergence -----
    lines.append("## D. Intersect dual-submission divergence")
    lines.append("")
    if len(divergence_df):
        d_total = pd.DataFrame(
            [
                {
                    "pairs_scanned": int(len(divergence_df)),
                    "divergent_flag_true": int(divergence_df["divergent_flag"].sum()),
                    "divergent_pct": round(
                        100.0 * float(divergence_df["divergent_flag"].sum()) / len(divergence_df),
                        2,
                    ),
                }
            ]
        )
        lines.extend(markdown_table(d_total))

        lines.append("### D1. Top-20 most-divergent pairs (smallest bbox_overlap_jaccard)")
        lines.append("")
        top_div = divergence_df.sort_values(
            ["divergent_flag", "bbox_overlap_jaccard"], ascending=[False, True]
        ).head(20)
        lines.extend(
            markdown_table(
                top_div[
                    [
                        "track_id",
                        "n_valid_nc",
                        "n_valid_xyz",
                        "valid_count_ratio",
                        "bbox_overlap_jaccard",
                        "depth_med_nc",
                        "depth_med_xyz",
                        "depth_med_ratio",
                        "divergent_flag",
                    ]
                ]
            )
        )

        lines.append("### D2. Divergence rule summary")
        lines.append("")
        lines.append(
            f"- count: valid_count_ratio outside [{DIVERGENT_COUNT_RATIO_LO:.1f}, "
            f"{DIVERGENT_COUNT_RATIO_HI:.1f}]"
        )
        lines.append(
            f"- bbox:  bbox_overlap_jaccard < {DIVERGENT_BBOX_JACCARD_MIN:.2f}"
        )
        lines.append(
            f"- depth: depth_med_ratio outside [{DIVERGENT_DEPTH_MED_RATIO_LO:.1f}, "
            f"{DIVERGENT_DEPTH_MED_RATIO_HI:.1f}]"
        )
        lines.append("")
    else:
        lines.append("_No intersect pairs in this run._")
        lines.append("")

    # ----- Section: comparison vs Step 03A -----
    lines.append("## Comparison vs Step 03A")
    lines.append("")
    lines.append(
        "Step 03B does not modify or invalidate any Step 03A flag (point_check_pass_basic "
        "and the 5 underlying boolean columns are preserved unchanged on every points_checked "
        "parquet)."
    )
    lines.append("")
    lines.append(
        "Refinements layered on top of Step 03A's results:"
    )
    lines.append("")
    lines.append(
        "- Check A attributes Step 03A's `n_invalid_depth_pos` aggregate: the finite-but-≤0 "
        "share is split into exact-zero (likely upstream sentinel) vs. negative-finite "
        "(likely sign-flip / unit error). NaN-depth rows (the bulk of `n_invalid_depth_pos` "
        "on the nc-sb leg per Step 03A §3b) are excluded from both A counts by construction."
    )
    lines.append("")
    lines.append(
        "- Check B is orthogonal to Step 03A — exact-triple duplicates pass every basic flag "
        "but represent a per-cell aggregation concern (double-counting at Step 04)."
    )
    lines.append("")
    lines.append(
        "- Check C is orthogonal to Step 03A — jump candidates may all pass `point_check_pass_basic` "
        "individually but flag tracks that warrant per-track review before being treated as "
        "primary cell-aggregation input."
    )
    lines.append("")
    lines.append(
        "- Check D quantifies the nc-vs-xyz intersect agreement that PRD Finding 19c "
        "(2026-05-20 correction) established as the basis for the 'prefer nc on intersect' rule."
    )
    lines.append("")

    # ----- Section: recommendation for Step 04 -----
    lines.append("## Recommendation for Step 04 cell aggregation")
    lines.append("")
    lines.append(
        "Step 03B emits flags only. Step 04's cell aggregation should consume the "
        "supplementary manifest as a per-track filtering hint, NOT as a hard drop rule: "
        "(i) tracks with `n_depth_jump_candidates > 0` warrant per-cell IQR review (the "
        "1-arcmin file-balanced median is already robust to a few jump candidates, but "
        "deep-volcanic / trench-wall tracks may legitimately flag many); (ii) tracks with "
        "high `n_duplicate_points` density should NOT be treated as having more independent "
        "soundings than `n_unique_triples` for cell-weighted statistics; (iii) intersect-pair "
        "divergent_flag=True cases should default to nc-side per the existing PRD Finding 19c "
        "policy, but the audit row should be cross-checked when nc and xyz disagree on "
        "instrument-class implications (e.g., one suggests mb-density, the other sb-sparsity)."
    )
    lines.append("")

    # ----- Section: paths -----
    lines.append("## Output paths")
    lines.append("")
    path_rows = [
        {"kind": "supplementary manifest (parquet)", "path": str(paths["supp_pq"].relative_to(REPO_ROOT))},
        {"kind": "supplementary manifest (tsv)",     "path": str(paths["supp_tsv"].relative_to(REPO_ROOT))},
        {"kind": "intersect divergence audit (parquet)", "path": str(paths["divergence_pq"].relative_to(REPO_ROOT))},
        {"kind": "intersect divergence audit (tsv)",     "path": str(paths["divergence_tsv"].relative_to(REPO_ROOT))},
        {"kind": "this report",                       "path": str(paths["report_md"].relative_to(REPO_ROOT))},
    ]
    lines.extend(markdown_table(pd.DataFrame(path_rows)))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step 03B — supplementary point-level quality checks layered on Step 03A"
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
        help="Overwrite existing supplementary manifest / report outputs",
    )
    parser.add_argument(
        "--estimate-only",
        action="store_true",
        help="Print work + intersect-pair counts and exit",
    )
    parser.add_argument(
        "--entry-manifest",
        type=Path,
        default=MANIFEST_DIR / "bathymetry_entry_manifest.parquet",
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
    args = parser.parse_args()

    paths = get_output_paths(args.run_label)
    logger = setup_logging(paths["log"])
    t0 = datetime.now()

    logger.info("=" * 60)
    logger.info("06_supplementary_quality_check.py START")
    logger.info("Args: %s", vars(args))

    # Validate input manifests.
    for label, p in (
        ("bathymetry_entry_manifest", args.entry_manifest),
        ("singlebeam_points_raw_manifest", args.nc_sb_manifest),
        ("xyz_points_raw_manifest", args.xyz_manifest),
    ):
        if not p.exists():
            logger.error("ABORTED: missing input manifest %s at %s", label, p)
            return 2

    entry_df = pd.read_parquet(args.entry_manifest)
    nc_sb_df = pd.read_parquet(args.nc_sb_manifest)
    xyz_df = pd.read_parquet(args.xyz_manifest)
    logger.info(
        "Loaded: entry=%d, nc_sb=%d, xyz=%d",
        len(entry_df),
        len(nc_sb_df),
        len(xyz_df),
    )

    # Sanity-check entry manifest column shape (Step 03A contract: 20 cols).
    expected_in_cols = 20
    if entry_df.shape[1] != expected_in_cols:
        logger.warning(
            "entry manifest has %d cols (expected %d) — proceeding but report may misalign",
            entry_df.shape[1],
            expected_in_cols,
        )

    # ----- estimate-only short-circuit -----
    work_all = entry_df[entry_df["source_priority"].isin(["primary", "regional"])]
    nc_intersect_ids = entry_df[
        (entry_df["source_type"] == "ncei_nc")
        & (entry_df["source_completeness"] == "nc_xyz_intersect")
    ]["track_id"]
    xyz_intersect_ids = entry_df[
        (entry_df["source_priority"] == "supplementary")
        & (entry_df["source_completeness"] == "nc_xyz_intersect")
    ]["track_id"]
    intersect_common = sorted(set(nc_intersect_ids) & set(xyz_intersect_ids))
    if args.estimate_only:
        print("Estimate only:")
        print(f"  entries in manifest: {len(entry_df):,}")
        print(f"  work-eligible entries (primary + regional): {len(work_all):,}")
        for prio, n in work_all["source_priority"].value_counts().items():
            print(f"    {prio}: {n:,}")
        print(f"  intersect dual-submission pairs available: {len(intersect_common):,}")
        return 0

    # ----- run-label gating -----
    if args.run_label == "full" and not args.confirm_full:
        logger.error("ABORTED: --run-label=full requires --confirm-full")
        return 2
    if args.run_label == "sample" and args.sample_n_files is None:
        logger.error("ABORTED: sample mode requires --sample-n-files")
        return 2
    if args.run_label == "test100" and args.limit_files is None:
        logger.error("ABORTED: test100 mode requires --limit-files")
        return 2

    # Acceptance-count gate when in full mode.
    if args.run_label == "full":
        if len(entry_df) != EXPECTED_TOTAL_ENTRIES:
            logger.error(
                "ABORTED: full-mode entry count expected %d (per PRD); got %d",
                EXPECTED_TOTAL_ENTRIES,
                len(entry_df),
            )
            return 3

    # Existing-output gate.
    output_files = [
        paths["supp_pq"],
        paths["supp_tsv"],
        paths["divergence_pq"],
        paths["divergence_tsv"],
        paths["report_md"],
    ]
    if not args.overwrite:
        existing = [p for p in output_files if p.exists()]
        if existing:
            logger.error(
                "ABORTED: outputs exist; use --overwrite. Existing: %s", existing
            )
            return 2

    # Select work + intersect pairs.
    work = select_workload(
        entry_df=entry_df,
        run_label=args.run_label,
        sample_n_files=args.sample_n_files,
        limit_files=args.limit_files,
        logger=logger,
    )
    logger.info("Will run supplementary check on %d entries", len(work))

    pairs_df = select_intersect_pairs(
        entry_df=entry_df,
        nc_sb_df=nc_sb_df,
        xyz_df=xyz_df,
        run_label=args.run_label,
        sample_n_files=args.sample_n_files,
        limit_files=args.limit_files,
        work=work,
    )
    logger.info("Will run intersect-divergence check on %d pairs", len(pairs_df))

    # Initialize the new columns on the supplementary manifest copy.
    supp_df = entry_df.copy()
    for c in NEW_COLUMNS[:-1]:  # all but supplementary_check_version
        supp_df[c] = pd.NA
    supp_df["supplementary_check_version"] = SUPP_CHECK_VERSION
    # Add a nullable error column (only the brief mentions it; null on success).
    supp_df["supplementary_error"] = None

    errors: list[dict] = []
    n_processed = 0

    # ----- Regional M.rar (one streaming pass, Checks A + B only) -----
    regional_work = work[work["source_priority"] == "regional"]
    if len(regional_work):
        try:
            mrar_counts = process_regional_mrar(entries=regional_work, logger=logger)
            for tid, counts in mrar_counts.items():
                mask = supp_df["track_id"] == tid
                if not mask.any():
                    continue
                for c in (
                    "n_depth_eq_zero",
                    "n_depth_negative_finite",
                    "n_duplicate_points",
                    "n_unique_triples",
                ):
                    supp_df.loc[mask, c] = counts[c]
                # Check C explicitly null for mrar.
                supp_df.loc[mask, "n_depth_jump_candidates"] = pd.NA
                n_processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Regional M.rar supplementary check failed")
            errors.append(
                {
                    "track_id": "<mrar_combined>",
                    "source_type": "mrar_zhoushuai",
                    "error": repr(exc),
                }
            )
            for tid in regional_work["track_id"]:
                mask = supp_df["track_id"] == tid
                supp_df.loc[mask, "supplementary_error"] = "mrar_streaming_error"

    # ----- Primary entries (per-track) -----
    primary_work = work[work["source_priority"] == "primary"]
    n_primary = len(primary_work)
    for i, (_, entry) in enumerate(primary_work.iterrows()):
        if i == 0 or (i + 1) % 200 == 0 or (i + 1) == n_primary:
            logger.info(
                "Primary %d/%d: %s (%s)",
                i + 1,
                n_primary,
                entry["track_id"],
                entry["source_type"],
            )
        try:
            counts = process_primary_entry(entry)
            row_mask = (supp_df["track_id"] == entry["track_id"]) & (
                supp_df["source_type"] == entry["source_type"]
            )
            for c in (
                "n_depth_eq_zero",
                "n_depth_negative_finite",
                "n_duplicate_points",
                "n_unique_triples",
                "n_depth_jump_candidates",
            ):
                supp_df.loc[row_mask, c] = counts[c]
            n_processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Error supplementary-checking %s (%s)",
                entry["track_id"],
                entry["source_type"],
            )
            errors.append(
                {
                    "track_id": str(entry["track_id"]),
                    "source_type": str(entry["source_type"]),
                    "output_path": entry["output_path"],
                    "error": repr(exc),
                }
            )
            row_mask = (supp_df["track_id"] == entry["track_id"]) & (
                supp_df["source_type"] == entry["source_type"]
            )
            supp_df.loc[row_mask, "supplementary_error"] = repr(exc)[:200]

    # ----- Check D — intersect divergence -----
    divergence_rows: list[dict] = []
    n_pairs = len(pairs_df)
    for j, (_, prow) in enumerate(pairs_df.iterrows()):
        if j == 0 or (j + 1) % 200 == 0 or (j + 1) == n_pairs:
            logger.info("Intersect pair %d/%d: %s", j + 1, n_pairs, prow["track_id"])
        try:
            div = process_intersect_pair(
                track_id=str(prow["track_id"]),
                nc_bbox=prow["nc_bbox"],
                xyz_bbox=prow["xyz_bbox"],
                nc_checked_path=prow["nc_checked_path"],
                xyz_raw_path=prow["xyz_raw_path"],
            )
            divergence_rows.append(div)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error in intersect pair %s", prow["track_id"])
            errors.append(
                {
                    "track_id": str(prow["track_id"]),
                    "source_type": "intersect_pair",
                    "error": repr(exc),
                }
            )

    divergence_df = pd.DataFrame(divergence_rows)

    # Finalize supplementary manifest schema: coerce new int counts to Int64.
    int_cols = [
        "n_depth_eq_zero",
        "n_depth_negative_finite",
        "n_duplicate_points",
        "n_unique_triples",
        "n_depth_jump_candidates",
    ]
    for c in int_cols:
        supp_df[c] = pd.to_numeric(supp_df[c], errors="coerce").astype("Int64")

    # Drop the helper supplementary_error column from the final manifest if
    # all-null (keep when populated so failures are auditable).
    if supp_df["supplementary_error"].isna().all():
        supp_df = supp_df.drop(columns=["supplementary_error"])

    # Sort to match Step 03A's canonical order.
    supp_df = supp_df.sort_values(
        ["source_priority", "source_type", "track_id"]
    ).reset_index(drop=True)

    elapsed_s = (datetime.now() - t0).total_seconds()

    # Write outputs.
    atomic_write_parquet(supp_df, paths["supp_pq"])
    tsv_df = supp_df if args.run_label == "full" else supp_df.head(500).copy()
    atomic_write_tsv(tsv_df, paths["supp_tsv"])

    if len(divergence_df):
        atomic_write_parquet(divergence_df, paths["divergence_pq"])
        atomic_write_tsv(divergence_df, paths["divergence_tsv"])
    else:
        # Still write an empty stub so downstream consumers see the schema.
        empty_div = pd.DataFrame(
            columns=[
                "track_id",
                "n_raw_nc",
                "n_valid_nc",
                "n_raw_xyz",
                "n_valid_xyz",
                "valid_count_ratio",
                "nc_bbox_lon_min",
                "nc_bbox_lon_max",
                "nc_bbox_lat_min",
                "nc_bbox_lat_max",
                "xyz_bbox_lon_min",
                "xyz_bbox_lon_max",
                "xyz_bbox_lat_min",
                "xyz_bbox_lat_max",
                "bbox_overlap_jaccard",
                "depth_med_nc",
                "depth_med_xyz",
                "depth_med_ratio",
                "divergent_flag",
            ]
        )
        atomic_write_parquet(empty_div, paths["divergence_pq"])
        atomic_write_tsv(empty_div, paths["divergence_tsv"])

    atomic_write_text(
        make_report(
            supp_df=supp_df,
            divergence_df=divergence_df,
            run_label=args.run_label,
            elapsed_s=elapsed_s,
            n_processed=n_processed,
            n_errors=len(errors),
            paths=paths,
        ),
        paths["report_md"],
    )
    atomic_write_tsv(pd.DataFrame(errors), paths["errors_tsv"])

    logger.info("Wrote %s (%d rows, %d cols)", paths["supp_pq"], len(supp_df), supp_df.shape[1])
    logger.info("Wrote %s", paths["supp_tsv"])
    logger.info("Wrote %s (%d pairs)", paths["divergence_pq"], len(divergence_df))
    logger.info("Wrote %s", paths["divergence_tsv"])
    logger.info("Wrote %s", paths["report_md"])
    logger.info("Errors: %d", len(errors))
    logger.info("Elapsed: %.1fs", elapsed_s)
    logger.info("06_supplementary_quality_check.py DONE")

    print(f"Entries in supplementary manifest: {len(supp_df):,}")
    print(f"Entries supplementary-checked: {n_processed:,}")
    print(f"Intersect pairs scanned: {len(divergence_df):,}")
    print(f"Errors: {len(errors):,}")
    print(f"Report: {paths['report_md']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
