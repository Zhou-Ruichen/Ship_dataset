#!/usr/bin/env python3
"""
01_build_multibeam_manifest.py

Build file_manifest and subzip_manifest from NCEI multibeam .dat files.

Reads:
  - raw/dat_by_subzip/         (all files, recursively)
  - docs/dat_manifest.tsv      (known dat file index, optional)
  - raw/subzips_bad/           (corrupt subzip names for status flagging)

Writes (full mode):
  - manifests/file_manifest.parquet + .tsv
  - manifests/subzip_manifest.parquet + .tsv
  - manifests/nonstandard_dat_files.tsv
  - docs/format_audit_report.md
  - output/logs/01_build_multibeam_manifest.log

Writes (sample/targeted mode):
  - manifests/samples/file_manifest_sample.parquet + .tsv
  - manifests/samples/subzip_manifest_sample.parquet + .tsv
  - manifests/samples/nonstandard_dat_files_sample.tsv
  - docs/format_audit_report_sample.md

Recognized formats:
  - 3-col:  lon lat depth                          -> ok_xyz_3col
  - 6-col:  date time sonar_idx lon lat depth       -> ok_xyz_6col_time_sonar_lonlatdepth
  - Other:  non-bathymetric or unrecognizable       -> various non-ok statuses

Usage:
    # Full run (overwrites):
    python 01_build_multibeam_manifest.py --overwrite

    # Random sample:
    python 01_build_multibeam_manifest.py --sample-n-files 20

    # Targeted sample by regex:
    python 01_build_multibeam_manifest.py --include-filename-regex 'dist_p10r|_t[.]dat$|T[0-9]{8}[.]dat$'
    python 01_build_multibeam_manifest.py --include-path-regex '2_OpenCheckData'

    # Limit files:
    python 01_build_multibeam_manifest.py --limit-files 100
"""

import argparse
import csv
import logging
import os
import re
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent

DAT_BY_SUBZIP = ROOT_DIR / "raw" / "dat_by_subzip"
DAT_MANIFEST_TSV = ROOT_DIR / "docs" / "dat_manifest.tsv"
SUBZIPS_BAD_DIR = ROOT_DIR / "raw" / "subzips_bad"

LOG_PATH = ROOT_DIR / "output" / "logs" / "01_build_multibeam_manifest.log"

SAMPLE_DIR = ROOT_DIR / "manifests" / "samples"

RE_TRANSIT_FILENAME = re.compile(r"^(T\d{8}\.dat|.*_t\.dat)$", re.IGNORECASE)
RE_DATE_YYYYMMDD = re.compile(r"(?:^|[^0-9])(\d{8})(?:[^0-9]|$)")

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------
OK_STATUSES = {
    "ok_xyz_3col",
    "ok_xyz_6col_time_sonar_lonlatdepth",
}

NON_OK_STATUSES = {
    "non_xyz_column_count",
    "invalid_lonlat_range",
    "negative_depth_unexpected",
    "zero_or_empty_file",
    "unreadable",
    "parse_error",
    "unknown",
    "bad_subzip",
}

# ---------------------------------------------------------------------------
# Data layout constants
# ---------------------------------------------------------------------------
LAYOUT_3COL = "lon_lat_depth_3col"
LAYOUT_6COL = "date_time_sonar_lon_lat_depth_6col"
LAYOUT_UNKNOWN = "unknown_or_non_bathymetry"

# ---------------------------------------------------------------------------
# Range constants
# ---------------------------------------------------------------------------
LON_MIN, LON_MAX = -180.0, 180.0
LON_ALT_MIN, LON_ALT_MAX = 0.0, 360.0
LAT_MIN, LAT_MAX = -90.0, 90.0
DEPTH_BOUND = 12000.0

FIRST_LINES_N = 5


# ---------------------------------------------------------------------------
# Range-check helpers
# ---------------------------------------------------------------------------
def _lon_ok(v_min: float, v_max: float) -> bool:
    if LON_MIN <= v_min <= LON_MAX and LON_MIN <= v_max <= LON_MAX:
        return True
    if LON_ALT_MIN <= v_min <= LON_ALT_MAX and LON_ALT_MIN <= v_max <= LON_ALT_MAX:
        return True
    return False


def _lat_ok(v_min: float, v_max: float) -> bool:
    return LAT_MIN <= v_min <= LAT_MAX and LAT_MIN <= v_max <= LAT_MAX


def _depth_range_ok(v_min: float, v_max: float) -> bool:
    return v_min >= -DEPTH_BOUND and v_max <= DEPTH_BOUND


def _classify_depth_sign(v_min: float, v_max: float) -> str:
    if v_max < 0:
        return "negative"
    if v_min >= 0:
        return "positive"
    return "mixed"


# ---------------------------------------------------------------------------
# Output path resolution
# ---------------------------------------------------------------------------
def get_output_paths(is_sample: bool):
    """Return (file_manifest_pq, file_manifest_tsv, subzip_manifest_pq,
    subzip_manifest_tsv, nonstandard_tsv, audit_report) based on mode."""
    if is_sample:
        return (
            SAMPLE_DIR / "file_manifest_sample.parquet",
            SAMPLE_DIR / "file_manifest_sample.tsv",
            SAMPLE_DIR / "subzip_manifest_sample.parquet",
            SAMPLE_DIR / "subzip_manifest_sample.tsv",
            SAMPLE_DIR / "nonstandard_dat_files_sample.tsv",
            ROOT_DIR / "docs" / "format_audit_report_sample.md",
        )
    return (
        ROOT_DIR / "manifests" / "file_manifest.parquet",
        ROOT_DIR / "manifests" / "file_manifest.tsv",
        ROOT_DIR / "manifests" / "subzip_manifest.parquet",
        ROOT_DIR / "manifests" / "subzip_manifest.tsv",
        ROOT_DIR / "manifests" / "nonstandard_dat_files.tsv",
        ROOT_DIR / "docs" / "format_audit_report.md",
    )


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("build_manifest")
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
# Collect all files
# ---------------------------------------------------------------------------
def collect_all_files(base_dir: Path) -> list[dict]:
    entries = []
    for dirpath, _dirnames, filenames in os.walk(base_dir):
        dir_p = Path(dirpath)
        for fn in filenames:
            fp = dir_p / fn
            rel = fp.relative_to(base_dir)
            parts = rel.parts
            subzip_id = parts[0]
            relative_path = str(rel)
            stat = fp.stat()
            entries.append({
                "subzip_id": subzip_id,
                "relative_path": relative_path,
                "filename": fn,
                "ext": fp.suffix.lower(),
                "size_bytes": stat.st_size,
                "_full_path": str(fp),
            })
    return entries


def load_dat_manifest(path: Path) -> set[str]:
    if not path.exists():
        return set()
    known = set()
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            p = row.get("Path", "").strip()
            if p:
                known.add(p)
    return known


def load_bad_subzips(bad_dir: Path) -> set[str]:
    bad = set()
    if not bad_dir.exists():
        return bad
    for fp in bad_dir.iterdir():
        if fp.is_file() and fp.suffix.lower() == ".zip":
            bad.add(fp.stem)
    return bad


# ---------------------------------------------------------------------------
# Audit a single .dat file
# ---------------------------------------------------------------------------
def audit_dat_file(
    full_path: str,
    logger: logging.Logger,
) -> dict:
    """
    Returns dict with keys:
        line_count, col_count, is_ascii, has_header,
        lon_min, lon_max, lat_min, lat_max, depth_min, depth_max,
        depth_sign, status, notes, first_lines, used_for_points,
        data_layout, lon_col, lat_col, depth_col,
        date_col, time_col, sonar_idx_col
    """
    line_count = 0
    col_count = None
    is_ascii = True
    has_header = False
    lon_min = lon_max = None
    lat_min = lat_max = None
    depth_min = depth_max = None
    depth_sign = "positive"
    status = "unknown"
    data_layout = LAYOUT_UNKNOWN
    lon_col = lat_col = depth_col = None
    date_col = time_col = sonar_idx_col = None
    notes = []
    first_lines_buf = []

    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline()
            if not first_line:
                return _result(
                    0, 0, True, False, None, None, None, None, None, None,
                    "empty", "zero_or_empty_file", "empty file", [],
                )

            try:
                first_line.encode("ascii")
            except UnicodeEncodeError:
                is_ascii = False

            first_lines_buf.append(first_line.rstrip())

            parts = first_line.strip().split()
            if not parts:
                return _result(
                    0, 0, is_ascii, False, None, None, None, None, None, None,
                    "empty", "zero_or_empty_file", "blank first line", first_lines_buf,
                )

            try:
                float(parts[0])
            except ValueError:
                has_header = True
                line_count = 1
                second = f.readline()
                if second.strip():
                    first_lines_buf.append(second.rstrip())
                    parts = second.strip().split()
                    line_count = 2
                else:
                    return _result(
                        1, len(parts), is_ascii, True,
                        None, None, None, None, None, None,
                        "unknown", "parse_error", "header but no data", first_lines_buf,
                    )

            col_count = len(parts)

            if col_count < 3:
                for _ in range(FIRST_LINES_N - len(first_lines_buf)):
                    ln = f.readline()
                    if ln:
                        first_lines_buf.append(ln.rstrip())
                notes.append(f"col_count={col_count}, expected>=3")
                return _result(
                    line_count, col_count, is_ascii, has_header,
                    None, None, None, None, None, None,
                    "unknown", "non_xyz_column_count",
                    "; ".join(notes), first_lines_buf,
                )

            # Collect column values.
            # Always collect cols 0,1,2.  If 6+ cols, also collect cols 3,4,5.
            c1_vals, c2_vals, c3_vals = [], [], []
            c4_vals, c5_vals, c6_vals = [], [], []

            def _parse_cols(p):
                try:
                    c1_vals.append(float(p[0]))
                    c2_vals.append(float(p[1]))
                    c3_vals.append(float(p[2]))
                except (ValueError, IndexError):
                    return False
                if len(p) >= 6:
                    try:
                        c4_vals.append(float(p[3]))
                        c5_vals.append(float(p[4]))
                        c6_vals.append(float(p[5]))
                    except (ValueError, IndexError):
                        pass
                return True

            _parse_cols(parts)
            line_count = line_count if has_header else 1

            for raw_line in f:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                line_count += 1
                if len(first_lines_buf) < FIRST_LINES_N:
                    first_lines_buf.append(stripped)
                p = stripped.split()
                _parse_cols(p)

            if not c1_vals:
                return _result(
                    line_count, col_count, is_ascii, has_header,
                    None, None, None, None, None, None,
                    "empty", "zero_or_empty_file", "no parseable numeric lines",
                    first_lines_buf,
                )

            c1_min, c1_max = min(c1_vals), max(c1_vals)
            c2_min, c2_max = min(c2_vals), max(c2_vals)
            c3_min, c3_max = min(c3_vals), max(c3_vals)

            if len(first_lines_buf) > FIRST_LINES_N:
                first_lines_buf = first_lines_buf[:FIRST_LINES_N]

            # --- Classification ---
            # Step 1: check if cols 0,1,2 are lon/lat/depth
            lon_ok_123 = _lon_ok(c1_min, c1_max)
            lat_ok_123 = _lat_ok(c2_min, c2_max)
            depth_ok_123 = _depth_range_ok(c3_min, c3_max)

            if lon_ok_123 and lat_ok_123 and depth_ok_123:
                # Cols 0,1,2 are lon/lat/depth
                lon_min, lon_max = c1_min, c1_max
                lat_min, lat_max = c2_min, c2_max
                depth_min, depth_max = c3_min, c3_max
                lon_col, lat_col, depth_col = 0, 1, 2
                data_layout = LAYOUT_3COL
                depth_sign = _classify_depth_sign(c3_min, c3_max)

                if depth_sign == "negative":
                    status = "negative_depth_unexpected"
                    notes.append(f"depth range [{c3_min:.2f},{c3_max:.2f}] all negative")
                else:
                    status = "ok_xyz_3col"
                    if col_count != 3:
                        notes.append(f"{col_count} columns, cols 0-2 are lon/lat/depth")

            elif col_count >= 6 and c4_vals:
                # Step 2: check if cols 3,4,5 are lon/lat/depth
                c4_min, c4_max = min(c4_vals), max(c4_vals)
                c5_min, c5_max = min(c5_vals), max(c5_vals)
                c6_min, c6_max = min(c6_vals), max(c6_vals)

                lon_ok_456 = _lon_ok(c4_min, c4_max)
                lat_ok_456 = _lat_ok(c5_min, c5_max)
                depth_ok_456 = _depth_range_ok(c6_min, c6_max)

                if lon_ok_456 and lat_ok_456 and depth_ok_456:
                    lon_min, lon_max = c4_min, c4_max
                    lat_min, lat_max = c5_min, c5_max
                    depth_min, depth_max = c6_min, c6_max
                    lon_col, lat_col, depth_col = 3, 4, 5
                    date_col, time_col, sonar_idx_col = 0, 1, 2
                    data_layout = LAYOUT_6COL
                    depth_sign = _classify_depth_sign(c6_min, c6_max)

                    if depth_sign == "negative":
                        status = "negative_depth_unexpected"
                        notes.append("6-col format but depth is negative")
                    else:
                        status = "ok_xyz_6col_time_sonar_lonlatdepth"
                else:
                    # Neither 0-2 nor 3-5 look like lon/lat/depth
                    lon_min, lon_max = c1_min, c1_max
                    lat_min, lat_max = c2_min, c2_max
                    depth_min, depth_max = c3_min, c3_max
                    depth_sign = _classify_depth_sign(c3_min, c3_max)
                    notes.append(
                        f"cols 0-2 range: [{c1_min:.2f},{c1_max:.2f}] "
                        f"[{c2_min:.2f},{c2_max:.2f}] [{c3_min:.2f},{c3_max:.2f}]; "
                        f"cols 3-5 range: [{c4_min:.2f},{c4_max:.2f}] "
                        f"[{c5_min:.2f},{c5_max:.2f}] [{c6_min:.2f},{c6_max:.2f}]"
                    )
                    status = "non_xyz_column_count"
                    notes.append(f"{col_count} columns; neither set matches lon/lat/depth")
            else:
                # Step 3: cols 0,1,2 fail and no 6-col fallback
                lon_min, lon_max = c1_min, c1_max
                lat_min, lat_max = c2_min, c2_max
                depth_min, depth_max = c3_min, c3_max
                depth_sign = _classify_depth_sign(c3_min, c3_max)
                notes.append(
                    f"col_range: c1=[{c1_min:.2f},{c1_max:.2f}] "
                    f"c2=[{c2_min:.2f},{c2_max:.2f}] "
                    f"c3=[{c3_min:.2f},{c3_max:.2f}]"
                )
                if not (lon_ok_123 and lat_ok_123):
                    status = "invalid_lonlat_range"
                    notes.append("col1/col2 outside lon/lat bounds")
                if not depth_ok_123:
                    status = "non_xyz_column_count"
                    notes.append("col3 outside expected depth bounds")

    except UnicodeDecodeError as e:
        logger.error(f"Encoding error reading {full_path}: {e}")
        return _result(
            0, 0, False, False, None, None, None, None, None, None,
            "error", "unreadable", str(e), [],
        )
    except Exception as e:
        logger.error(f"Failed to read {full_path}: {e}")
        return _result(
            0, 0, False, False, None, None, None, None, None, None,
            "error", "parse_error", str(e), [],
        )

    used = _compute_used_for_points(status, depth_sign)
    return {
        "line_count": line_count,
        "col_count": col_count or 0,
        "is_ascii": is_ascii,
        "has_header": has_header,
        "lon_min": lon_min, "lon_max": lon_max,
        "lat_min": lat_min, "lat_max": lat_max,
        "depth_min": depth_min, "depth_max": depth_max,
        "depth_sign": depth_sign,
        "status": status,
        "notes": "; ".join(notes) if notes else "",
        "first_lines": " | ".join(first_lines_buf),
        "used_for_points": used,
        "data_layout": data_layout,
        "lon_col": lon_col,
        "lat_col": lat_col,
        "depth_col": depth_col,
        "date_col": date_col,
        "time_col": time_col,
        "sonar_idx_col": sonar_idx_col,
    }


def _result(lc, cc, ascii_, hdr, lnmin, lnmax, ltmin, ltmax, dmin, dmax,
            dsign, status, notes, first_lines,
            data_layout=LAYOUT_UNKNOWN,
            lon_col=None, lat_col=None, depth_col=None,
            date_col=None, time_col=None, sonar_idx_col=None):
    used = _compute_used_for_points(status, dsign)
    return {
        "line_count": lc, "col_count": cc, "is_ascii": ascii_,
        "has_header": hdr,
        "lon_min": lnmin, "lon_max": lnmax,
        "lat_min": ltmin, "lat_max": ltmax,
        "depth_min": dmin, "depth_max": dmax,
        "depth_sign": dsign, "status": status,
        "notes": notes,
        "first_lines": " | ".join(first_lines) if first_lines else "",
        "used_for_points": used,
        "data_layout": data_layout,
        "lon_col": lon_col, "lat_col": lat_col, "depth_col": depth_col,
        "date_col": date_col, "time_col": time_col,
        "sonar_idx_col": sonar_idx_col,
    }


def _compute_used_for_points(status: str, depth_sign: str) -> bool:
    return status in OK_STATUSES and depth_sign == "positive"


# ---------------------------------------------------------------------------
# Guess cruise_id, date, track_kind
# ---------------------------------------------------------------------------
def guess_metadata(subzip_id: str, filename: str) -> dict:
    if RE_TRANSIT_FILENAME.match(filename):
        track_kind = "transit"
    elif "_transit" in filename.lower() or "/transit/" in (subzip_id + "/" + filename).lower():
        track_kind = "transit"
    else:
        track_kind = "unknown_or_survey"

    cruise_id_guess = re.sub(
        r"_(?:bathymetry|leg\d+_bathymetry|bathymetry_dmo|bathymetry_pi)(?:_.*)?$",
        "", subzip_id,
    )
    if subzip_id.isdigit():
        cruise_id_guess = subzip_id

    date_guess = None
    m = re.match(r"^T(\d{8})\.dat$", filename, re.IGNORECASE)
    if m:
        date_guess = m.group(1)
    else:
        m = re.match(r"^(\d{8})\.dat$", filename)
        if m:
            date_guess = m.group(1)
        else:
            m = RE_DATE_YYYYMMDD.search(filename)
            if m:
                date_guess = m.group(1)

    return {
        "cruise_id_guess": cruise_id_guess or "",
        "date_guess": date_guess or "",
        "track_kind": track_kind,
    }


# ---------------------------------------------------------------------------
# Filter dat files by regex
# ---------------------------------------------------------------------------
def filter_dat_files(
    dat_files: list[dict],
    filename_regex: Optional[re.Pattern],
    path_regex: Optional[re.Pattern],
) -> list[dict]:
    if filename_regex is None and path_regex is None:
        return dat_files
    out = []
    for f in dat_files:
        if filename_regex and filename_regex.search(f["filename"]):
            out.append(f)
            continue
        if path_regex and path_regex.search(f["relative_path"]):
            out.append(f)
            continue
    return out


# ---------------------------------------------------------------------------
# Build file_manifest
# ---------------------------------------------------------------------------
def build_file_manifest(
    all_files: list[dict],
    known_dat_paths: set[str],
    bad_subzips: set[str],
    logger: logging.Logger,
    sample_n: Optional[int] = None,
    limit_files: Optional[int] = None,
    filename_regex: Optional[re.Pattern] = None,
    path_regex: Optional[re.Pattern] = None,
) -> pd.DataFrame:
    dat_files = [f for f in all_files if f["ext"] == ".dat"]
    non_dat_files = [f for f in all_files if f["ext"] != ".dat"]

    # Regex filter first (targeted sample)
    if filename_regex is not None or path_regex is not None:
        dat_files = filter_dat_files(dat_files, filename_regex, path_regex)
        logger.info(f"After regex filter: {len(dat_files)} dat files match")

    if limit_files is not None:
        dat_files = dat_files[:limit_files]

    if sample_n is not None and sample_n < len(dat_files):
        random.seed(42)
        dat_files = random.sample(dat_files, sample_n)
        logger.info(f"Sampled {sample_n} dat files for auditing")

    total_dat = len(dat_files)
    logger.info(f"Auditing {total_dat} dat files + {len(non_dat_files)} non-dat files")

    rows = []
    for i, fentry in enumerate(dat_files):
        if (i + 1) % 500 == 0:
            logger.info(f"  Progress: {i+1}/{total_dat}")

        audit = audit_dat_file(fentry["_full_path"], logger)
        meta = guess_metadata(fentry["subzip_id"], fentry["filename"])

        subzip = fentry["subzip_id"]
        is_bad_subzip = subzip in bad_subzips

        combined_status = audit["status"]
        if is_bad_subzip:
            combined_status = "bad_subzip"

        file_id = f"{subzip}::{fentry['filename']}"
        if len(fentry["relative_path"].split("/")) > 2:
            file_id = f"{subzip}::{fentry['relative_path']}"

        rows.append({
            "file_id": file_id,
            "subzip_id": subzip,
            "relative_path": fentry["relative_path"],
            "filename": fentry["filename"],
            "ext": fentry["ext"],
            "size_bytes": fentry["size_bytes"],
            **audit,
            **meta,
        })

    for fentry in non_dat_files:
        file_id = f"{fentry['subzip_id']}::{fentry['filename']}"
        rows.append({
            "file_id": file_id,
            "subzip_id": fentry["subzip_id"],
            "relative_path": fentry["relative_path"],
            "filename": fentry["filename"],
            "ext": fentry["ext"],
            "size_bytes": fentry["size_bytes"],
            "line_count": None, "col_count": None,
            "is_ascii": None, "has_header": None,
            "lon_min": None, "lon_max": None,
            "lat_min": None, "lat_max": None,
            "depth_min": None, "depth_max": None,
            "depth_sign": "", "status": "non_dat", "notes": "",
            "first_lines": "", "used_for_points": False,
            "data_layout": LAYOUT_UNKNOWN,
            "lon_col": None, "lat_col": None, "depth_col": None,
            "date_col": None, "time_col": None, "sonar_idx_col": None,
            "cruise_id_guess": "", "date_guess": "", "track_kind": "",
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Build subzip_manifest
# ---------------------------------------------------------------------------
def build_subzip_manifest(
    file_manifest: pd.DataFrame,
    bad_subzips: set[str],
    logger: logging.Logger,
) -> pd.DataFrame:
    rows = []
    for subzip_id, group in file_manifest.groupby("subzip_id"):
        n_files = len(group)
        n_dat = int((group["ext"] == ".dat").sum())
        n_pdf = int((group["ext"] == ".pdf").sum())
        n_txt = int((group["ext"] == ".txt").sum())

        dat_group = group[group["ext"] == ".dat"]
        ok_mask = dat_group["status"].isin(OK_STATUSES)
        n_readable = int(ok_mask.sum())
        non_ok = dat_group[~ok_mask]
        n_bad = int(len(non_ok[non_ok["status"] != "non_dat"]))
        total_size = int(group["size_bytes"].sum())

        lon_min = dat_group["lon_min"].min()
        lon_max = dat_group["lon_max"].max()
        lat_min = dat_group["lat_min"].min()
        lat_max = dat_group["lat_max"].max()
        depth_min = dat_group["depth_min"].min()
        depth_max = dat_group["depth_max"].max()

        depth_signs = dat_group["depth_sign"].dropna().unique()
        depth_sign = ""
        if len(depth_signs) == 1:
            depth_sign = depth_signs[0]
        elif len(depth_signs) > 1:
            depth_sign = "mixed"

        contains_transit = bool((dat_group["track_kind"] == "transit").any())

        cruise_ids = dat_group["cruise_id_guess"].dropna().unique()
        cruise_id_guess = cruise_ids[0] if len(cruise_ids) > 0 else ""

        is_bad = subzip_id in bad_subzips
        if is_bad:
            status = "bad_subzip"
        elif n_bad > 0 and n_readable == 0:
            status = "all_dat_bad"
        elif n_bad > 0:
            status = "partial_bad"
        else:
            status = "ok"

        rows.append({
            "subzip_id": subzip_id,
            "n_files": n_files,
            "n_dat_files": n_dat,
            "n_pdf_files": n_pdf,
            "n_txt_files": n_txt,
            "n_readable_dat": n_readable,
            "n_bad_dat": n_bad,
            "total_size_bytes": total_size,
            "lon_min": lon_min, "lon_max": lon_max,
            "lat_min": lat_min, "lat_max": lat_max,
            "depth_min": depth_min, "depth_max": depth_max,
            "depth_sign": depth_sign,
            "contains_transit": contains_transit,
            "cruise_id_guess": cruise_id_guess,
            "status": status, "notes": "",
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Nonstandard dat files export
# ---------------------------------------------------------------------------
def write_nonstandard_dat_files(
    file_manifest: pd.DataFrame,
    out_path: Path,
    logger: logging.Logger,
):
    dat = file_manifest[file_manifest["ext"] == ".dat"]
    ns = dat[dat["status"].isin(NON_OK_STATUSES)]
    if len(ns) == 0:
        logger.info("No non-standard dat files found.")
    else:
        logger.info(f"Writing {len(ns)} non-standard dat entries to {out_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["relative_path", "filename", "subzip_id", "col_count",
            "status", "data_layout", "notes", "first_lines"]
    ns_out = ns[cols].copy()
    tmp = out_path.with_suffix(".tsv.tmp")
    ns_out.to_csv(tmp, sep="\t", index=False)
    os.replace(tmp, out_path)
    logger.info(f"Wrote nonstandard_dat_files: {out_path.name} ({len(ns)} rows)")


# ---------------------------------------------------------------------------
# Audit report
# ---------------------------------------------------------------------------
def write_audit_report(
    file_manifest: pd.DataFrame,
    subzip_manifest: pd.DataFrame,
    report_path: Path,
    logger: logging.Logger,
    is_sample: bool = False,
):
    report_path.parent.mkdir(parents=True, exist_ok=True)

    dat = file_manifest[file_manifest["ext"] == ".dat"]
    lines = []
    lines.append("# Format Audit Report\n")
    lines.append(f"Generated: {datetime.now().isoformat()}")
    if is_sample:
        lines.append("\n**⚠️  SAMPLE MODE — not all files audited**")

    lines.append("\n## Summary\n")
    lines.append(f"- Total files scanned: {len(file_manifest)}")
    lines.append(f"- .dat files audited: {len(dat)}")
    lines.append(f"- Subzips: {len(subzip_manifest)}")

    n_ok_3col = int((dat["status"] == "ok_xyz_3col").sum())
    n_ok_6col = int((dat["status"] == "ok_xyz_6col_time_sonar_lonlatdepth").sum())
    n_ok_total = n_ok_3col + n_ok_6col
    n_used = int(dat["used_for_points"].sum())
    lines.append(f"- ok_xyz_3col: {n_ok_3col}")
    lines.append(f"- ok_xyz_6col_time_sonar_lonlatdepth: {n_ok_6col}")
    lines.append(f"- total ok: {n_ok_total}")
    lines.append(f"- used_for_points=True: {n_used}")
    lines.append("")

    lines.append("## dat Status Breakdown\n")
    status_counts = dat["status"].value_counts()
    lines.append("| status | count |")
    lines.append("|--------|-------|")
    for st, cnt in status_counts.items():
        lines.append(f"| {st} | {cnt} |")
    lines.append("")

    lines.append("## Data Layout Distribution\n")
    layout_counts = dat["data_layout"].value_counts()
    lines.append("| data_layout | count |")
    lines.append("|-------------|-------|")
    for dl, cnt in layout_counts.items():
        lines.append(f"| {dl} | {cnt} |")
    lines.append("")

    lines.append("## used_for_points\n")
    lines.append("| value | count |")
    lines.append("|-------|-------|")
    for val, cnt in dat["used_for_points"].value_counts().items():
        lines.append(f"| {val} | {cnt} |")
    lines.append("")

    lines.append("## Column Count Distribution (dat files)\n")
    col_counts = dat["col_count"].value_counts().sort_index()
    lines.append("| col_count | count |")
    lines.append("|-----------|-------|")
    for cc, cnt in col_counts.items():
        lines.append(f"| {cc} | {cnt} |")
    lines.append("")

    lines.append("## Depth Sign\n")
    ds_counts = dat["depth_sign"].value_counts()
    lines.append("| depth_sign | count |")
    lines.append("|------------|-------|")
    for ds, cnt in ds_counts.items():
        lines.append(f"| {ds} | {cnt} |")
    lines.append("")

    lines.append("## Track Kind\n")
    tk_counts = dat["track_kind"].value_counts()
    lines.append("| track_kind | count |")
    lines.append("|------------|-------|")
    for tk, cnt in tk_counts.items():
        lines.append(f"| {tk} | {cnt} |")
    lines.append("")

    # 6-col usable bathymetric files
    ok_6col = dat[dat["status"] == "ok_xyz_6col_time_sonar_lonlatdepth"]
    lines.append("## 6-column Usable Bathymetric Files\n")
    if len(ok_6col) == 0:
        lines.append("None found.\n")
    else:
        lines.append(f"Found {len(ok_6col)} files with 6-col date/time/sonar/lon/lat/depth format:\n")
        for _, row in ok_6col.head(40).iterrows():
            lines.append(
                f"- `{row['relative_path']}`: cols={row['col_count']} "
                f"lines={row['line_count']} "
                f"lon=[{row['lon_min']:.4f},{row['lon_max']:.4f}] "
                f"lat=[{row['lat_min']:.4f},{row['lat_max']:.4f}] "
                f"depth=[{row['depth_min']:.2f},{row['depth_max']:.2f}]"
            )
        if len(ok_6col) > 40:
            lines.append(f"\n... and {len(ok_6col) - 40} more.")
    lines.append("")

    lines.append("## Non-standard Files\n")
    ns = dat[dat["status"].isin(NON_OK_STATUSES)]
    if len(ns) == 0:
        lines.append("No non-standard dat files detected.\n")
    else:
        lines.append(f"Found {len(ns)} non-standard dat files:\n")
        for _, row in ns.head(80).iterrows():
            lines.append(
                f"- `{row['relative_path']}`: status={row['status']} "
                f"layout={row['data_layout']} "
                f"cols={row['col_count']} lines={row['line_count']} "
                f"notes={row['notes']}"
            )
        if len(ns) > 80:
            lines.append(f"\n... and {len(ns) - 80} more.")
    lines.append("")

    lines.append("## Spatial Coverage (all usable dat files)\n")
    ok_dat = dat[dat["used_for_points"] == True]  # noqa: E712
    if len(ok_dat) > 0:
        lines.append(f"- Longitude: {ok_dat['lon_min'].min():.4f} ~ {ok_dat['lon_max'].max():.4f}")
        lines.append(f"- Latitude: {ok_dat['lat_min'].min():.4f} ~ {ok_dat['lat_max'].max():.4f}")
        lines.append(f"- Depth: {ok_dat['depth_min'].min():.2f} ~ {ok_dat['depth_max'].max():.2f}")
    else:
        lines.append("No usable dat files for spatial summary.")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Audit report written to {report_path}")


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
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Build file_manifest and subzip_manifest for NCEI multibeam data."
    )
    parser.add_argument(
        "--sample-n-files", type=int, default=None,
        help="Randomly sample N dat files for auditing.",
    )
    parser.add_argument(
        "--limit-files", type=int, default=None,
        help="Only audit the first N dat files.",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing full-mode output files.",
    )
    parser.add_argument(
        "--include-filename-regex", type=str, default=None,
        help="Only audit dat files whose filename matches this regex.",
    )
    parser.add_argument(
        "--include-path-regex", type=str, default=None,
        help="Only audit dat files whose relative path matches this regex.",
    )
    args = parser.parse_args()

    logger = setup_logging(LOG_PATH)
    logger.info("=" * 60)
    logger.info("Starting 01_build_multibeam_manifest.py")
    logger.info(f"Args: {vars(args)}")

    is_sample = (
        args.sample_n_files is not None
        or args.include_filename_regex is not None
        or args.include_path_regex is not None
    )

    (
        fm_pq, fm_tsv, sm_pq, sm_tsv,
        ns_tsv, audit_md,
    ) = get_output_paths(is_sample)

    if not is_sample:
        output_files = [fm_pq, fm_tsv, sm_pq, sm_tsv]
        if not args.overwrite and all(f.exists() for f in output_files):
            logger.info("All output files exist. Use --overwrite to regenerate. Exiting.")
            print("All output files exist. Use --overwrite to regenerate.")
            return

    fn_re = re.compile(args.include_filename_regex) if args.include_filename_regex else None
    path_re = re.compile(args.include_path_regex) if args.include_path_regex else None

    known_dat_paths = load_dat_manifest(DAT_MANIFEST_TSV)
    logger.info(f"Loaded {len(known_dat_paths)} known dat paths from dat_manifest.tsv")

    bad_subzips = load_bad_subzips(SUBZIPS_BAD_DIR)
    logger.info(f"Found {len(bad_subzips)} bad subzips")

    logger.info(f"Scanning {DAT_BY_SUBZIP} ...")
    all_files = collect_all_files(DAT_BY_SUBZIP)
    logger.info(f"Found {len(all_files)} total files")

    ext_summary = {}
    for f in all_files:
        ext_summary[f["ext"]] = ext_summary.get(f["ext"], 0) + 1
    logger.info(f"Extension breakdown: {ext_summary}")

    file_manifest = build_file_manifest(
        all_files, known_dat_paths, bad_subzips, logger,
        sample_n=args.sample_n_files,
        limit_files=args.limit_files,
        filename_regex=fn_re,
        path_regex=path_re,
    )
    logger.info(f"file_manifest: {len(file_manifest)} rows")

    subzip_manifest = build_subzip_manifest(file_manifest, bad_subzips, logger)
    logger.info(f"subzip_manifest: {len(subzip_manifest)} rows")

    atomic_write_df(file_manifest, fm_pq, fm_tsv, logger)
    atomic_write_df(subzip_manifest, sm_pq, sm_tsv, logger)

    write_nonstandard_dat_files(file_manifest, ns_tsv, logger)
    write_audit_report(file_manifest, subzip_manifest, audit_md, logger, is_sample=is_sample)

    logger.info("Done.")
    logger.info("=" * 60)

    dat_rows = file_manifest[file_manifest["ext"] == ".dat"]
    n_ok_3col = int((dat_rows["status"] == "ok_xyz_3col").sum())
    n_ok_6col = int((dat_rows["status"] == "ok_xyz_6col_time_sonar_lonlatdepth").sum())
    n_used = int(dat_rows["used_for_points"].sum())
    print(f"\n{'='*55}")
    print(f"  Mode: {'SAMPLE' if is_sample else 'FULL'}")
    print(f"  file_manifest: {len(file_manifest)} files ({len(dat_rows)} .dat)")
    print(f"  subzip_manifest: {len(subzip_manifest)} subzips")
    print(f"  ok_xyz_3col: {n_ok_3col}  |  ok_xyz_6col: {n_ok_6col}")
    print(f"  used_for_points: {n_used}")
    print(f"  Output: {fm_pq.parent}/")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
