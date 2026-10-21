#!/usr/bin/env python3
"""Stage 2 — L1 point extraction for the COMPLETE raw_round2 swath cruises.

Supported formats: .mb58.gz (EM raw), .mb21.gz (Hydrosweep DS raw ASCII)
and suffix-less .gz whose decompressed body starts with the Hydrosweep
"ERGNMESS" header (also format 21). Formats resolving to None are
recorded and skipped. For each target cruise, every file is:

  1. decompressed with the fixed-version gzip from the sealed SCS
     mbsystem environment;
  2. parsed twice by the fixed-version mblist (5.8.3beta16) with the
     command lines -F<fmt> -P1 -L0 -MA -U3/-U0 -OMN#XYzH;
  3. joined U3(left)/U0(good-beams) via
     _common.mbsystem.raw_from_object (extracted from the archived SCS
     Stage C processing module; see docs/code_archive.md);
  4. converted to a per-file staging shard; at cruise end the shards are
     merged into the L1 points_raw contract with native quality and
     staging-record lineage, plus the points_checked QC extension.

Depth sign is diagnosed per cruise from the raw parser depths (the
L3 five-state enum) before the standardized depth column is written;
no global sign assumption is made.

Every external command is logged to a per-file JSONL command ledger
(argv, return code, stdout/stderr sha256).

Outputs (all under ncei/derived/mb_round2/<cruise>/):
  points_raw/<track_id>__mb<fmt>.parquet
  points_checked/<track_id>__mb<fmt>.parquet
  _staging/<filekey>.parquet            (per-file staging, kept for resume)
  _work/<filekey>/command_ledger.jsonl  (per-file command ledger, kept)
  extraction_manifest.parquet / .tsv    (per-file rows + cruise sign verdict)

Run from repo root:
    python -m ncei.swath extract [--cruises AR15 AR40 ...] \
        [--workers 8] [--merge-only]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[2]

from _common.mbsystem import raw_from_object

RAW_ROOT = REPO_ROOT / "ncei/raw_round2/platforms_tree"
COMP_PATH = REPO_ROOT / "ncei/derived/mb_round2/completeness_manifest.parquet"
FMT_PATH = REPO_ROOT / "ncei/derived/mb_round2/formats_manifest.parquet"
OUT_ROOT = REPO_ROOT / "ncei/derived/mb_round2"

ENVIRONMENT_ROOT = REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/environments/mbsystem-5.8.3beta16-1d9a52ce"
GZIP = ENVIRONMENT_ROOT / "bin/gzip"
MBLIST = ENVIRONMENT_ROOT / "build/mbsystem/src/utilities/mblist"
MBSYSTEM_VERSION = "5.8.3beta16"

# MBIO format id by filename suffix; None -> probe by content signature.
FORMAT_BY_SUFFIX = {
    ".mb58.gz": 58, ".all.gz": 58, ".mb21.gz": 21, ".mb57.gz": 57,
    ".mb41.gz": 41, ".mb32.gz": 32, ".mb11.gz": 11, ".rc00.gz": 15,
    ".mb84.gz": 84,  # Preserve the source .prj as _work/<filekey>/input.mb58.prj.
    ".gsf.mb121.gz": 121,
}
# '.all.gz' (NCEI level_00 tier-A packaging) is the same Kongsberg raw
# content as '.all.mb58.gz'; verified 2026-09 with mbinfo -F58
# (MBF_EM710RAW) on AR71-03/level_00/AR71-03_RAW_EM710.
# Known swath suffixes this chain does not support (recorded explicitly so
# they are not mislabelled as 'unknown').
KNOWN_UNSUPPORTED_SUFFIXES = {".mb56.gz", ".mb162.gz"}
# Hydrosweep DS raw ASCII header (format 21) — the only content signature
# we auto-detect for suffix-less files; anything else is skipped with a
# recorded reason rather than guessed.
CONTENT_SIGNATURES = {b"ERGNMESS": 21}
INSTRUMENT_CLASS = "multibeam"

# L1 contract columns (matches existing ncei/derived/multibeam/points_raw).
POINT_COLUMNS = [
    "source_type", "track_id", "point_index_in_track", "time",
    "lon_raw", "lat_raw", "lon", "lat", "depth_raw",
    "depth_m_positive_down", "elev_m", "gobs", "faa",
    "source_completeness", "instrument_class_pred", "standardization_version",
    "filekey", "file_ordinal", "point_index_in_file", "staging_row",
    "native_quality_state",
]
CHECK_COLUMNS = [
    "valid_lon", "valid_lat", "valid_depth_pos", "valid_depth_max",
    "valid_core_fields", "point_check_pass_basic",
]
DEPTH_VALID_MAX_M = 11500.0

STAGING_SCHEMA = pa.schema(
    [
        ("file_ordinal", pa.int32()),
        ("point_index_in_file", pa.int64()),
        ("time_us", pa.int64()),
        ("lon_raw", pa.float64()),
        ("lat_raw", pa.float64()),
        ("lon", pa.float64()),
        ("lat", pa.float64()),
        ("depth_raw", pa.float64()),
        ("native_quality_state", pa.string()),
    ]
)


def resolve_mb_format(rel: Path) -> tuple[int | None, str]:
    """MBIO format id for one raw file: suffix first, then content probe."""
    name = rel.name.lower()
    for suffix, fmt in FORMAT_BY_SUFFIX.items():
        if name.endswith(suffix):
            return fmt, f"suffix {suffix}"
    for suffix in KNOWN_UNSUPPORTED_SUFFIXES:
        if name.endswith(suffix):
            return None, f"known but unsupported suffix {suffix}"
    gz = RAW_ROOT / rel
    proc = subprocess.Popen([str(GZIP), "-dc", "--", str(gz)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        head = proc.stdout.read(16)
    finally:
        proc.kill()
        proc.wait()
    for signature, fmt in CONTENT_SIGNATURES.items():
        if head.startswith(signature):
            return fmt, f"content signature {signature!r}"
    return None, f"unknown format: head={head!r}"


def file_key(rel: Path) -> str:
    text = rel.as_posix()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def append_command(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def staging_statistics(path: Path) -> dict:
    """Recover quality and depth counts from an existing staging shard."""
    counts = dict.fromkeys(
        ["n_rows", "n_good", "n_flagged", "n_null", "n_unknown",
         "n_depth_pos", "n_depth_neg", "n_depth_zero", "n_depth_nan"], 0
    )
    shard = pq.ParquetFile(path)
    if "native_quality_state" not in shard.schema_arrow.names:
        raise ValueError(f"native_quality_state missing from staging: {path}")
    for batch in shard.iter_batches(
        batch_size=1_000_000, columns=["depth_raw", "native_quality_state"]
    ):
        df = batch.to_pandas()
        depth = df["depth_raw"].to_numpy(dtype=np.float64)
        finite = np.isfinite(depth)
        counts["n_rows"] += len(df)
        counts["n_depth_pos"] += int(np.count_nonzero(depth[finite] > 0))
        counts["n_depth_neg"] += int(np.count_nonzero(depth[finite] < 0))
        counts["n_depth_zero"] += int(np.count_nonzero(depth[finite] == 0))
        counts["n_depth_nan"] += int(np.count_nonzero(~finite))
        quality = df["native_quality_state"]
        for state in ("good", "flagged", "null"):
            counts[f"n_{state}"] += int(quality.eq(state).sum())
        counts["n_unknown"] += int((~quality.isin(["good", "flagged", "null"])).sum())
    return counts


def run_command(argv: list[str], *, stdout_path: Path | None, stderr_path: Path, ledger_path: Path, object_id: str, role: str) -> subprocess.CompletedProcess[str]:
    """Mirrors the SCS command-ledger contract (argv + rc + stream hashes)."""
    if stdout_path is None:
        completed = subprocess.run(argv, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
        stdout_bytes = completed.stdout.encode()
        stderr_bytes = completed.stderr.encode()
    else:
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            completed_raw = subprocess.run(argv, cwd=REPO_ROOT, stdout=stdout_handle, stderr=stderr_handle, check=False)
        stdout_bytes = stdout_path.read_bytes()
        stderr_bytes = stderr_path.read_bytes()
        completed = subprocess.CompletedProcess(argv, completed_raw.returncode, stdout_bytes.decode("utf-8", "replace"), stderr_bytes.decode("utf-8", "replace"))
    append_command(
        ledger_path,
        {
            "object_id": object_id,
            "role": role,
            "argv": argv,
            "returncode": completed.returncode,
            "stdout_sha256": hashlib.sha256(stdout_bytes).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr_bytes).hexdigest(),
        },
    )
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {argv!r}")
    return completed


def process_one_file(
    cruise: str, ordinal: int, rel: Path, mb_format: int, format_note: str, *,
    output_root: Path = OUT_ROOT, source_path: Path | None = None,
) -> dict:
    """Extract one raw swath file into a staging shard. Returns a manifest row."""
    out_cruise_dir = output_root / cruise
    staging_dir = out_cruise_dir / "_staging"
    key = file_key(rel)
    staging_path = staging_dir / f"{key}.parquet"
    work = out_cruise_dir / "_work" / key
    ledger = work / "command_ledger.jsonl"
    gz_path = source_path if source_path is not None else RAW_ROOT / rel
    object_id = f"mb_round2/{cruise}/{rel.name}"

    if staging_path.exists():
        return {
            "cruise": cruise, "file_ordinal": ordinal, "relpath": rel.as_posix(),
            "filekey": key, "mb_format": mb_format, "format_note": format_note, "status": "skipped_exists",
            "gz_bytes": gz_path.stat().st_size,
            **staging_statistics(staging_path),
            "error_code": "", "error_detail": "",
            "runtime_seconds": 0.0,
        }

    if mb_format is None:
        status = "skipped_format_unsupported" if "unsupported" in format_note else "skipped_format_unknown"
        return {
            "cruise": cruise, "file_ordinal": ordinal, "relpath": rel.as_posix(),
            "filekey": key, "mb_format": None, "format_note": format_note,
            "status": status,
            "gz_bytes": gz_path.stat().st_size if gz_path.exists() else 0, "n_rows": 0,
            "n_good": 0, "n_flagged": 0, "n_null": 0,
            "n_depth_pos": 0, "n_depth_neg": 0, "n_depth_zero": 0, "n_depth_nan": 0,
            "error_code": "FORMAT_UNKNOWN", "error_detail": format_note,
            "runtime_seconds": 0.0,
        }

    work.mkdir(parents=True, exist_ok=True)
    ledger.write_text("", encoding="utf-8")
    decompressed = work / "input.mb58"
    u3 = work / "all_u3.tsv"
    u0 = work / "good_u0.tsv"
    raw_path = work / "raw_joined.parquet"
    t0 = time.time()
    try:
        if source_path is None or gz_path.suffix == ".gz":
            run_command([str(GZIP), "-dc", "--", str(gz_path)], stdout_path=decompressed, stderr_path=work / "gzip.stderr", ledger_path=ledger, object_id=object_id, role="decompression")
        else:
            shutil.copyfile(gz_path, decompressed)
        u3_argv = [str(MBLIST), f"-I{decompressed}", f"-F{mb_format}", "-P1", "-L0", "-MA", "-U3", "-OMN#XYzH", f"-X{u3}"]
        u0_argv = [str(MBLIST), f"-I{decompressed}", f"-F{mb_format}", "-P1", "-L0", "-MA", "-U0", "-OMN#XYzH", f"-X{u0}"]
        run_command(u3_argv, stdout_path=None, stderr_path=work / "u3.stderr", ledger_path=ledger, object_id=object_id, role="mblist_u3")
        run_command(u0_argv, stdout_path=None, stderr_path=work / "u0.stderr", ledger_path=ledger, object_id=object_id, role="mblist_u0")
        total_rows, good_rows, error_code, error_detail = raw_from_object(object_id, u3, u0, work / "u0.sqlite", raw_path)
        if error_code:
            return {
                "cruise": cruise, "file_ordinal": ordinal, "relpath": rel.as_posix(),
                "filekey": key, "status": f"failed:{error_code}",
                "gz_bytes": gz_path.stat().st_size, "n_rows": 0,
                "n_good": 0, "n_flagged": 0, "n_null": 0,
                "n_depth_pos": 0, "n_depth_neg": 0, "n_depth_zero": 0, "n_depth_nan": 0,
                "error_code": error_code, "error_detail": (error_detail or "")[:500],
                "runtime_seconds": time.time() - t0,
            }

        # raw -> staging shard (streamed batches).
        staging_dir.mkdir(parents=True, exist_ok=True)
        tmp_staging = staging_path.with_suffix(".parquet.tmp")
        writer = pq.ParquetWriter(tmp_staging, STAGING_SCHEMA, compression="zstd")
        n_pos = n_neg = n_zero = n_nan = 0
        n_good = n_flagged = n_null = 0
        local_index = 0
        pf = pq.ParquetFile(raw_path)
        for batch in pf.iter_batches(batch_size=200_000):
            df = batch.to_pandas()
            depth_raw = df["parser_depth_value"].to_numpy(dtype=np.float64)
            finite = np.isfinite(depth_raw)
            n_pos += int(np.count_nonzero(depth_raw[finite] > 0))
            n_neg += int(np.count_nonzero(depth_raw[finite] < 0))
            n_zero += int(np.count_nonzero(depth_raw[finite] == 0))
            n_nan += int(np.count_nonzero(~finite))
            quality = df["native_quality_state"].to_numpy()
            n_good += int(np.count_nonzero(quality == "good"))
            n_flagged += int(np.count_nonzero(quality == "flagged"))
            n_null += int(np.count_nonzero(quality == "null"))
            shard = pa.Table.from_pydict(
                {
                    "file_ordinal": np.full(len(df), ordinal, dtype=np.int32),
                    "point_index_in_file": np.arange(local_index, local_index + len(df), dtype=np.int64),
                    "time_us": df["epoch_us"].to_numpy(dtype=np.int64),
                    "lon_raw": df["lon_deg"].to_numpy(dtype=np.float64),
                    "lat_raw": df["lat_deg"].to_numpy(dtype=np.float64),
                    "lon": df["lon_deg"].to_numpy(dtype=np.float64),
                    "lat": df["lat_deg"].to_numpy(dtype=np.float64),
                    "depth_raw": depth_raw,
                    "native_quality_state": quality.astype(str),
                },
                schema=STAGING_SCHEMA,
            )
            writer.write_table(shard)
            local_index += len(df)
        writer.close()
        os.replace(tmp_staging, staging_path)
        row = {
            "cruise": cruise, "file_ordinal": ordinal, "relpath": rel.as_posix(),
            "filekey": key, "mb_format": mb_format, "format_note": format_note, "status": "ok",
            "gz_bytes": gz_path.stat().st_size, "n_rows": total_rows,
            "n_good": n_good, "n_flagged": n_flagged, "n_null": n_null,
            "n_depth_pos": n_pos, "n_depth_neg": n_neg, "n_depth_zero": n_zero, "n_depth_nan": n_nan,
            "error_code": "", "error_detail": "",
            "runtime_seconds": time.time() - t0,
        }
    except Exception as error:  # noqa: BLE001 — per-file isolation, recorded
        tmp = staging_dir / f"{key}.parquet.tmp" if staging_dir.exists() else None
        if tmp is not None and tmp.exists():
            tmp.unlink()
        row = {
            "cruise": cruise, "file_ordinal": ordinal, "relpath": rel.as_posix(),
            "filekey": key, "mb_format": mb_format, "format_note": format_note, "status": f"failed:{type(error).__name__}",
            "gz_bytes": gz_path.stat().st_size if gz_path.exists() else 0, "n_rows": 0,
            "n_good": 0, "n_flagged": 0, "n_null": 0,
            "n_depth_pos": 0, "n_depth_neg": 0, "n_depth_zero": 0, "n_depth_nan": 0,
            "error_code": type(error).__name__, "error_detail": str(error)[:500],
            "runtime_seconds": time.time() - t0,
        }
    finally:
        # Keep the command ledger; drop bulky intermediates.
        for junk in (decompressed, u3, u0, raw_path, work / "u0.sqlite"):
            junk.unlink(missing_ok=True)
    return row


def merge_cruise(
    cruise: str, manifest: pd.DataFrame, *,
    staging_dir: Path | None = None, output_dir: Path | None = None,
) -> dict:
    """Merge shards with native quality and record lineage; recover manifest counts."""
    track_id = cruise.lower()
    ok_all = manifest[manifest["status"].isin(["ok", "skipped_exists"])].sort_values("file_ordinal")
    if ok_all.empty:
        statuses = manifest["status"].value_counts().to_dict()
        return {
            "cruise": cruise, "track_id": cruise.lower(), "mb_format": None,
            "depth_sign_raw": "no_depth_values", "sign_flip": 1.0,
            "n_rows": 0, "n_pass_basic": 0,
            "points_raw_path": "", "points_checked_path": "",
            "status": "no_usable_files", "file_statuses": json.dumps(statuses),
        }
    formats_used = sorted({int(f) for f in ok_all["mb_format"].dropna().unique()})
    mb_format = formats_used[0] if len(formats_used) == 1 else None
    if mb_format is None:
        raise ValueError(f"{cruise}: expected exactly one usable format, got {formats_used}")
    source_type = f"ncei_mb{mb_format}"
    source_completeness = f"mb{mb_format}_only"
    standardization_version = f"34_mb_round2_extract_points.py v2; mblist 5.8.3beta16 -F{mb_format} U3/U0 join; staging lineage"
    out_cruise_dir = output_dir if output_dir is not None else OUT_ROOT / cruise
    staging_dir = staging_dir if staging_dir is not None else OUT_ROOT / cruise / "_staging"
    ok = ok_all
    # Depth-sign stats recomputed from the shards themselves — manifest rows
    # for skipped files carry None counters, so they cannot be trusted as a
    # statistics source across resumed runs.
    totals = {}
    for row in ok.itertuples():
        counts = staging_statistics(staging_dir / f"{row.filekey}.parquet")
        for name, count in counts.items():
            manifest.loc[row.Index, name] = count
            totals[name] = totals.get(name, 0) + count
    n_pos, n_neg, n_zero = (totals[k] for k in ("n_depth_pos", "n_depth_neg", "n_depth_zero"))
    n_values = n_pos + n_neg + n_zero
    if n_values == 0:
        sign = "no_depth_values"
    elif n_zero == n_values:
        sign = "all_zero"
    elif n_pos / n_values >= 0.95:
        sign = "mostly_positive"
    elif n_neg / n_values >= 0.95:
        sign = "mostly_negative"
    else:
        sign = "mixed_sign"
    if sign == "mostly_negative":
        sign_flip = -1.0
    else:
        sign_flip = 1.0

    raw_out = out_cruise_dir / "points_raw" / f"{track_id}__mb{mb_format}.parquet"
    chk_out = out_cruise_dir / "points_checked" / f"{track_id}__mb{mb_format}.parquet"
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    chk_out.parent.mkdir(parents=True, exist_ok=True)
    tmp_raw = raw_out.with_suffix(".parquet.tmp")
    tmp_chk = chk_out.with_suffix(".parquet.tmp")

    raw_schema = pa.schema(
        [("source_type", pa.string()), ("track_id", pa.string()), ("point_index_in_track", pa.int64()),
         ("time", pa.timestamp("ns")), ("lon_raw", pa.float64()), ("lat_raw", pa.float64()),
         ("lon", pa.float64()), ("lat", pa.float64()), ("depth_raw", pa.float64()),
         ("depth_m_positive_down", pa.float64()), ("elev_m", pa.float64()), ("gobs", pa.float64()),
         ("faa", pa.float64()), ("source_completeness", pa.string()), ("instrument_class_pred", pa.string()),
         ("standardization_version", pa.string()), ("filekey", pa.string()),
         ("file_ordinal", pa.int32()), ("point_index_in_file", pa.int64()),
         ("staging_row", pa.int64()), ("native_quality_state", pa.string())])
    checked_schema = pa.schema(
        list(raw_schema) + [pa.field(name, pa.bool_()) for name in CHECK_COLUMNS]
    )
    writer_raw = pq.ParquetWriter(tmp_raw, raw_schema, compression="zstd")
    writer_chk = pq.ParquetWriter(tmp_chk, checked_schema, compression="zstd")

    global_index = 0
    n_rows = 0
    n_pass = 0
    n_selected = 0
    bounds = {"lon_min": np.inf, "lon_max": -np.inf, "lat_min": np.inf,
              "lat_max": -np.inf, "depth_min_raw": np.inf, "depth_max_raw": -np.inf}
    n_finite_position = 0
    for row in ok.itertuples():
        shard_path = staging_dir / f"{row.filekey}.parquet"
        pf = pq.ParquetFile(shard_path)
        staging_row = 0
        file_basic = file_selected = 0
        for batch in pf.iter_batches(batch_size=500_000):
            df = batch.to_pandas()
            n = len(df)
            depth_raw = df["depth_raw"].to_numpy(dtype=np.float64)
            depth_std = depth_raw * sign_flip
            elev = -depth_std
            valid_lon = np.isfinite(df["lon"].to_numpy()) & (df["lon"].to_numpy() >= -180.0) & (df["lon"].to_numpy() < 180.0)
            valid_lat = np.isfinite(df["lat"].to_numpy()) & (df["lat"].to_numpy() >= -90.0) & (df["lat"].to_numpy() <= 90.0)
            valid_pos = np.isfinite(depth_std) & (depth_std > 0.0)
            valid_max = np.isfinite(depth_std) & (depth_std <= DEPTH_VALID_MAX_M)
            core = valid_lon & valid_lat & valid_pos & valid_max
            selected = core & df["native_quality_state"].eq("good").to_numpy(dtype=bool)
            if not df["file_ordinal"].eq(row.file_ordinal).all():
                raise ValueError(f"file_ordinal disagrees with extraction manifest: {shard_path}")
            base = {
                "source_type": np.full(n, source_type, dtype=object),
                "track_id": np.full(n, track_id, dtype=object),
                "point_index_in_track": np.arange(global_index, global_index + n, dtype=np.int64),
                "time": df["time_us"].to_numpy(dtype="datetime64[us]").astype("datetime64[ns]"),
                "lon_raw": df["lon_raw"].to_numpy(dtype=np.float64),
                "lat_raw": df["lat_raw"].to_numpy(dtype=np.float64),
                "lon": df["lon"].to_numpy(dtype=np.float64),
                "lat": df["lat"].to_numpy(dtype=np.float64),
                "depth_raw": depth_raw,
                "depth_m_positive_down": depth_std,
                "elev_m": elev,
                "gobs": np.full(n, np.nan),
                "faa": np.full(n, np.nan),
                "source_completeness": np.full(n, source_completeness, dtype=object),
                "instrument_class_pred": np.full(n, INSTRUMENT_CLASS, dtype=object),
                "standardization_version": np.full(n, standardization_version, dtype=object),
                "filekey": np.full(n, row.filekey, dtype=object),
                "file_ordinal": df["file_ordinal"].to_numpy(dtype=np.int32),
                "point_index_in_file": df["point_index_in_file"].to_numpy(dtype=np.int64),
                "staging_row": np.arange(staging_row, staging_row + n, dtype=np.int64),
                "native_quality_state": df["native_quality_state"].to_numpy(),
            }
            writer_raw.write_table(pa.Table.from_pydict(base, schema=raw_schema))
            writer_chk.write_table(pa.Table.from_pydict({**base,
                "valid_lon": valid_lon, "valid_lat": valid_lat, "valid_depth_pos": valid_pos,
                "valid_depth_max": valid_max, "valid_core_fields": core, "point_check_pass_basic": core},
                schema=checked_schema))
            global_index += n
            staging_row += n
            n_rows += n
            n_pass += int(core.sum())
            n_selected += int(selected.sum())
            file_basic += int(core.sum())
            file_selected += int(selected.sum())
            finite_position = np.isfinite(df["lon"]) & np.isfinite(df["lat"])
            n_finite_position += int(finite_position.sum())
            for name in ("lon", "lat"):
                values = df.loc[finite_position, name].to_numpy()
                if len(values):
                    bounds[f"{name}_min"] = min(bounds[f"{name}_min"], float(values.min()))
                    bounds[f"{name}_max"] = max(bounds[f"{name}_max"], float(values.max()))
            finite_depth = depth_raw[np.isfinite(depth_raw)]
            if len(finite_depth):
                bounds["depth_min_raw"] = min(bounds["depth_min_raw"], float(finite_depth.min()))
                bounds["depth_max_raw"] = max(bounds["depth_max_raw"], float(finite_depth.max()))
        manifest.loc[row.Index, "n_pass_basic"] = file_basic
        manifest.loc[row.Index, "n_selected_basic_native_good"] = file_selected
    writer_raw.close()
    writer_chk.close()
    os.replace(tmp_raw, raw_out)
    os.replace(tmp_chk, chk_out)
    return {
        "cruise": cruise, "track_id": track_id, "mb_format": mb_format,
        "depth_sign_raw": sign,
        "sign_flip": sign_flip, "n_rows": n_rows, "n_pass_basic": n_pass,
        **{k: v for k, v in totals.items() if k != "n_rows"},
        "n_selected_basic_native_good": n_selected,
        "selection_rule": "point_check_pass_basic & (native_quality_state == 'good')",
        "n_finite_position": n_finite_position,
        **{k: v if np.isfinite(v) else None for k, v in bounds.items()},
        "points_raw_path": os.path.relpath(raw_out, REPO_ROOT),
        "points_checked_path": os.path.relpath(chk_out, REPO_ROOT),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ncei.swath extract", description=__doc__)
    parser.add_argument("--cruises", nargs="*", default=None, help="Subset of cruise IDs (default: all complete mb58 cruises).")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--merge-only", action="store_true", help="Skip extraction; only merge existing staging shards.")
    args = parser.parse_args(argv)

    comp = pd.read_parquet(COMP_PATH)
    complete = set(comp[comp["status"] == "complete"]["cruise"])
    all_cruises = {p.name for p in RAW_ROOT.iterdir() if p.is_dir()}
    targets = sorted(c for c in all_cruises if c in complete)
    if args.cruises:
        targets = [c for c in targets if c in set(args.cruises)]
    if not targets:
        print("no target cruises")
        return 1

    import multiprocessing as mp

    for cruise in targets:
        files = sorted(f for f in (RAW_ROOT / cruise).rglob("*.gz") if not f.name.endswith(".part"))
        files = [f.relative_to(RAW_ROOT) for f in files]
        formats = {rel.as_posix(): resolve_mb_format(rel) for rel in files}
        manifest_path = OUT_ROOT / cruise / "extraction_manifest.parquet"
        existing = pd.read_parquet(manifest_path) if manifest_path.exists() else None
        rows: list[dict] = []
        if not args.merge_only:
            tasks = [(cruise, ordinal, rel, *formats[rel.as_posix()]) for ordinal, rel in enumerate(files)]
            if not tasks:
                manifest = pd.DataFrame(columns=["cruise", "file_ordinal", "relpath", "filekey", "status"])
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest.to_parquet(manifest_path, index=False)
                summary = {"cruise": cruise, "track_id": cruise.lower(), "mb_format": None,
                           "depth_sign_raw": "no_depth_values", "sign_flip": 1.0, "n_rows": 0,
                           "n_pass_basic": 0, "points_raw_path": "", "points_checked_path": "",
                           "status": "no_gz_files"}
                (OUT_ROOT / cruise / "extraction_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                print(json.dumps(summary, sort_keys=True), flush=True)
                continue
            with mp.Pool(processes=max(1, min(args.workers, len(tasks)))) as pool:
                results = pool.starmap(_process_wrapper, tasks)
            rows = results
            manifest = pd.DataFrame(rows)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = manifest_path.with_suffix(".parquet.tmp")
            manifest.to_parquet(tmp, index=False)
            os.replace(tmp, manifest_path)
            manifest.to_csv(manifest_path.with_suffix(".tsv"), sep="\t", index=False)
        else:
            manifest = existing if existing is not None else pd.DataFrame(columns=["filekey", "file_ordinal", "status"])
        summary = merge_cruise(cruise, manifest)
        manifest.to_parquet(manifest_path, index=False)
        manifest.to_csv(manifest_path.with_suffix(".tsv"), sep="\t", index=False)
        summary_path = OUT_ROOT / cruise / "extraction_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(summary, sort_keys=True))
    return 0


def _process_wrapper(cruise: str, ordinal: int, rel_str: str, mb_format: int, format_note: str) -> dict:
    return process_one_file(cruise, ordinal, Path(rel_str), mb_format, format_note)


if __name__ == "__main__":
    raise SystemExit(main())
