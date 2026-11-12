"""Preserve MGD77T observations in point tables and one-minute cells."""

from __future__ import annotations

import argparse
import json
import logging
import multiprocessing as mp
import resource
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from . import file_cells, manifest, merge_cells, point_qc, standardize_xyz
from .mgd77t import DATA_FIELDS, decode_time, iter_mgd77t, read_header
from .mgd77t_netcdf import CODE_FIELDS


REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_ROOT = REPO_ROOT / "ncei/derived/sb_round2_static"

VERSION = "ncei_mgd77t_source_fields_v1"
REJECT_CODES = (3, 4, 5, 6)
OLD_COLUMNS = (
    "lon_raw", "lat_raw", "lon", "lat", "depth_raw",
    "depth_m_positive_down", "elev_m", "point_check_pass_basic",
)


def _same_numeric(expected, actual, *, atol: float, label: str) -> float:
    expected, actual = np.asarray(expected, dtype=float), np.asarray(actual, dtype=float)
    if not np.array_equal(np.isnan(expected), np.isnan(actual)):
        raise AssertionError(f"{label}: missingness differs")
    finite = np.isfinite(expected) & np.isfinite(actual)
    difference = np.abs(expected[finite] - actual[finite])
    maximum = float(difference.max()) if difference.size else 0.0
    if maximum > atol:
        raise AssertionError(f"{label}: max difference {maximum} > {atol}")
    return maximum


def _utc_timestamp(seconds: np.ndarray) -> pa.Array:
    finite = np.isfinite(seconds)
    nanoseconds = np.zeros(len(seconds), dtype=np.int64)
    if finite.any():
        nanoseconds[finite] = pd.to_datetime(seconds[finite], unit="s", utc=True).asi8
    # Converting an all-NaN float array through pandas can overflow internally.
    return pa.array(nanoseconds, mask=~finite, type=pa.timestamp("ns", tz="UTC"))


def _chunk_table(
    records, track: str, prediction: str, sign: str, header, old_start: int,
    legacy_aligned: bool = True,
):
    n = len(records)
    lon_raw, lat_raw = records.numeric("LON"), records.numeric("LAT")
    source_depth = records.numeric("CORR_DEPTH")
    depth_raw = source_depth.copy()
    depth_raw[np.abs(depth_raw) >= 99999] = np.nan
    depth = np.abs(depth_raw) if sign in {"mostly_positive", "mostly_negative"} else np.full(n, np.nan)
    depth[depth > standardize_xyz.DEPTH_CLIP_UPPER_M] = np.nan
    lon = standardize_xyz.normalize_lon(lon_raw)
    lat = standardize_xyz.sanitize_lat(lat_raw)
    flags = point_qc.compute_flag_arrays(lon, lat, depth)
    codes = {field: records.numeric(field) for field in CODE_FIELDS}
    bad_nav, bad_bat = np.isin(codes["NAV_QUALCO"], REJECT_CODES), np.isin(codes["BAT_QUALCO"], REJECT_CODES)
    usable = ~(bad_nav | bad_bat)
    basic = flags["point_check_pass_basic"]
    selected = basic & usable
    legacy_present = (records.source_field_count >= 10) & np.isfinite(lon_raw) & np.isfinite(lat_raw)
    old_indices = old_start + np.cumsum(legacy_present, dtype=np.int64) - 1
    times = decode_time(records)
    mismatched_header = header.fields["SURVEY_ID"].strip().casefold() != str(records.raw["SURVEY_ID"][0]).strip().casefold()
    values = {
        "source_type": ["ncei_xyz"] * n,
        "source_format": ["MGD77T"] * n,
        "track_id": [track] * n,
        "survey_id": records.raw["SURVEY_ID"],
        "source_file": [str(records.source_path)] * n,
        "source_line_1based": records.source_line_1based,
        "source_observation_index_0based": records.source_observation_index_0based,
        "source_field_count": records.source_field_count,
        "point_index_in_track": records.source_observation_index_0based,
        "point_table_row_0based": records.source_observation_index_0based,
        "legacy_point_index_in_track": pa.array(
            old_indices, mask=~legacy_present if legacy_aligned else np.ones(n, dtype=bool),
        ),
        "time": _utc_timestamp(times.utc_seconds),
        "time_utc_seconds": times.utc_seconds,
        "time_assuming_unspecified_timezone_zero": _utc_timestamp(times.assuming_unspecified_timezone_zero_seconds),
        "time_status": times.status,
        "TIMEZONE": records.raw["TIMEZONE"], "DATE": records.raw["DATE"], "TIME": records.raw["TIME"],
        "lon_raw": lon_raw, "lat_raw": lat_raw, "lon": lon, "lat": lat,
        "source_corr_depth_m": source_depth, "depth_raw": depth_raw,
        "depth_m_positive_down": depth, "elev_m": -depth,
        "gobs": records.numeric("GRA_OBS"), "faa": records.numeric("FREEAIR"),
        "source_completeness": ["xyz_only"] * n,
        "instrument_class_pred": [prediction] * n,
        "standardization_version": [VERSION] * n,
        "BATH_INSTR": [header.fields["BATH_INSTR"]] * n,
        "source_header_survey_id": [header.fields["SURVEY_ID"]] * n,
        "source_header_survey_id_mismatch": np.full(n, mismatched_header),
        "source_quality_usable": usable,
        "nav_quality_unspecified": np.char.strip(records.raw["NAV_QUALCO"]) == "",
        "bat_quality_unspecified": np.char.strip(records.raw["BAT_QUALCO"]) == "",
    }
    for field, numbers in codes.items():
        present = np.isfinite(numbers)
        if np.any(numbers[present] != np.floor(numbers[present])):
            raise ValueError(f"{track}: noninteger source code {field}")
        values[field] = pa.array(np.where(present, numbers, 0).astype(np.int16), mask=~present)
    values.update({f"{field}_raw": records.raw[field] for field in DATA_FIELDS})
    raw = pa.Table.from_pydict(values)
    checked = raw
    for field, array in flags.items():
        checked = checked.append_column(field, pa.array(array))
    checked = checked.append_column("point_selected_basic_source_quality", pa.array(selected))
    checked = checked.append_column("source_quality_excluded_from_basic", pa.array(basic & ~usable))
    arrays = {
        "lon_raw": lon_raw, "lat_raw": lat_raw, "lon": lon, "lat": lat,
        "depth_raw": depth_raw, "depth_m_positive_down": depth, "elev_m": -depth,
        "point_check_pass_basic": basic,
    }
    counts = {
        "source_rows": n, "short_source_rows": int((records.source_field_count < 10).sum()),
        "legacy_point_rows": int(legacy_present.sum()), "basic_selected": int(basic.sum()),
        "source_quality_selected": int(selected.sum()),
        "nav_rejected_basic": int((basic & bad_nav).sum()),
        "bat_rejected_basic": int((basic & bad_bat).sum()),
        "both_rejected_basic": int((basic & bad_nav & bad_bat).sum()),
        "union_rejected_basic": int((basic & ~usable).sum()),
        "nav_unspecified": int((np.char.strip(records.raw["NAV_QUALCO"]) == "").sum()),
        "bat_unspecified": int((np.char.strip(records.raw["BAT_QUALCO"]) == "").sum()),
        "source_blank_depth": int(np.isnan(source_depth).sum()),
        "source_depth_sentinels": int((np.abs(source_depth) >= 99999).sum()),
        "utc_time_present": int(np.isfinite(times.utc_seconds).sum()),
        "source_time_missing": int((times.status == 0).sum()),
        "valid_time_timezone_unspecified": int((times.status == 2).sum()),
        "source_time_invalid": int((times.status >= 3).sum()),
    }
    quality = Counter()
    for field in ("NAV_QUALCO", "BAT_QUALCO", "POS_TYPE", "BAT_TYPCO", "BAT_CPCO"):
        unique, inverse, source_counts = np.unique(records.raw[field], return_inverse=True, return_counts=True)
        for i, code in enumerate(unique):
            which = inverse == i
            quality[(field, str(code), "source")] += int(source_counts[i])
            quality[(field, str(code), "legacy_source")] += int((legacy_present & which).sum())
            quality[(field, str(code), "basic")] += int((basic & which).sum())
            quality[(field, str(code), "basic_source_quality")] += int((selected & which).sum())
    return raw, checked, arrays, legacy_present, counts, quality


def _compare_cells(basic_path: Path, legacy_path: Path) -> dict:
    current = pd.read_parquet(basic_path).sort_values("cell_id").reset_index(drop=True)
    old = pd.read_parquet(legacy_path).sort_values("cell_id").reset_index(drop=True)
    if current["cell_id"].tolist() != old["cell_id"].tolist():
        raise AssertionError(f"{basic_path.stem}: basic cell identities differ")
    maxima = {}
    for field in file_cells.OUTPUT_COLUMNS:
        if field in {"track_id", "source_type", "source_completeness", "instrument_class_pred", "branch", "cell_id", "manual_review_flag"}:
            continue
        maxima[field] = _same_numeric(old[field], current[field], atol=1e-8, label=f"{basic_path.stem}/{field}")
    return maxima


def _verify_saved(
    source: Path, checked_path: Path, sign: str, prediction: str, header,
    chunk_size: int, legacy_aligned: bool = True,
) -> int:
    """Read the effective parquet and compare every original field and identity."""
    batches = iter(pq.ParquetFile(checked_path).iter_batches(batch_size=chunk_size))
    n = old_start = 0
    for records in iter_mgd77t(source, chunk_size):
        batch = pa.Table.from_batches([next(batches)])
        if len(batch) != len(records):
            raise AssertionError(f"{source}: source/parquet chunk length differs")
        for field in DATA_FIELDS:
            if batch[f"{field}_raw"].to_pylist() != records.raw[field].tolist():
                raise AssertionError(f"{source}: raw {field} differs")
        _, expected, _, present, _, _ = _chunk_table(
            records, source.stem, prediction, sign, header, old_start, legacy_aligned,
        )
        for field in expected.column_names:
            if pa.types.is_floating(batch[field].type):
                _same_numeric(expected[field].to_numpy(), batch[field].to_numpy(), atol=0, label=f"{source.stem}/{field}")
            elif not expected[field].combine_chunks().equals(batch[field].combine_chunks()):
                raise AssertionError(f"{source}: saved {field} differs")
        n += len(records)
        old_start += int(present.sum())
    if next(batches, None) is not None:
        raise AssertionError(f"{source}: extra output records")
    metadata = pq.read_schema(checked_path).metadata
    if json.loads(metadata[b"source_header"]) != header.fields:
        raise AssertionError(f"{source}: formal header metadata differs")
    return n


def source_depth_sign(source: Path, chunk_size: int) -> str:
    """Apply the existing unfiltered XYZ sign rule without an old product."""
    pieces = []
    for records in iter_mgd77t(source, chunk_size):
        depth = records.numeric("CORR_DEPTH")
        present = (
            (records.source_field_count >= 10)
            & np.isfinite(records.numeric("LON")) & np.isfinite(records.numeric("LAT"))
            & np.isfinite(depth) & (np.abs(depth) < 99999)
        )
        pieces.append(depth[present])
    values = np.concatenate(pieces) if pieces else np.empty(0)
    return manifest.depth_sign(values)


def process_source_track(job: dict) -> dict:
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    start = time.monotonic()
    source, root, legacy_root = (Path(job[key]) for key in ("source", "output_root", "legacy_root"))
    track = source.stem
    prediction = job["previous"].get("instrument_class_pred", "unclassified")
    sign = job["previous"].get("depth_sign_raw") or source_depth_sign(source, job["chunk_size"])
    header = read_header(source.with_suffix(".h77t"), track, allow_survey_id_mismatch=True)
    raw_path = root / "points_raw" / f"{track}__mgd77t.parquet"
    checked_path = root / "points_checked" / f"{track}__mgd77t.parquet"
    main_cells = root / "file_cells_1min" / f"{track}__mgd77t.parquet"
    basic_cells = root / "file_cells_1min_basic" / f"{track}__mgd77t.parquet"
    report_path = root / "comparison" / f"{track}.json"
    if job["resume"] and report_path.exists():
        report = json.loads(report_path.read_text())
        for path in (raw_path, checked_path, main_cells, basic_cells):
            if not path.exists():
                raise FileNotFoundError(path)
        if report["source_bytes"] != source.stat().st_size:
            raise ValueError(f"{source}: changed source size")
        changed = False
        if report["status"] == "no_finite_depth":
            report["status"] = "no_selected_depth"
            changed = True
        if report["instrument_class_pred"] == "unclassified":
            for layer in report["l2"].values():
                if layer["n_cells"] == 0 and layer["branch"] != "unclassified":
                    layer["branch"] = "unclassified"
                    changed = True
        if not any(row["selection"] == "legacy_source" for row in report["quality_counts"]):
            fields = ("NAV_QUALCO", "BAT_QUALCO", "POS_TYPE", "BAT_TYPCO", "BAT_CPCO")
            pilot = pl.read_parquet(
                checked_path, columns=["legacy_point_index_in_track", *[f"{field}_raw" for field in fields]],
            ).filter(pl.col("legacy_point_index_in_track").is_not_null())
            for field in fields:
                for row in pilot.group_by(f"{field}_raw").len().to_dicts():
                    report["quality_counts"].append({
                        "field": field, "code": row[f"{field}_raw"],
                        "selection": "legacy_source", "count": row["len"],
                    })
            changed = True
        if changed:
            report_path.write_text(json.dumps(report, indent=2, allow_nan=True) + "\n")
        return report
    for path in (raw_path, checked_path, main_cells, basic_cells):
        if path.exists() and not job["overwrite"]:
            raise FileExistsError(path)
        path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path = legacy_root / "points_checked" / f"{track}__xyz.parquet"
    compare_legacy = job.get("compare_legacy", True)
    old = pl.read_parquet(legacy_path, columns=list(OLD_COLUMNS)) if compare_legacy and legacy_path.exists() else None
    legacy_aligned = old is not None
    totals, quality = Counter(), Counter()
    raw_writer = checked_writer = None
    maxima = {field: 0.0 for field in OLD_COLUMNS}
    metadata = {
        b"source_header": json.dumps(header.fields, ensure_ascii=True).encode(),
        b"source_header_file": str(header.source_path).encode(),
        b"units": b'{"depth_raw":"m","source_corr_depth_m":"m","depth_m_positive_down":"m positive down","gobs":"mGal","faa":"mGal","time_utc_seconds":"seconds since 1970-01-01 UTC"}',
        b"selection_policy": b"basic_source_quality: basic and neither NAV_QUALCO nor BAT_QUALCO in {3,4,5,6}; unspecified retained",
        b"time_policy": b"time requires specified timezone; time_assuming_unspecified_timezone_zero is an explicit assumption",
        b"version": VERSION.encode(),
        b"legacy_point_alignment": b"compared_to_historical_points" if legacy_aligned else b"not_compared_indices_null",
    }
    try:
        for records in iter_mgd77t(source, job["chunk_size"]):
            raw, checked, arrays, present, counts, codes = _chunk_table(
                records, track, prediction, sign, header, totals["legacy_point_rows"], legacy_aligned,
            )
            n_old = int(present.sum())
            if old is not None:
                previous = old.slice(totals["legacy_point_rows"], n_old)
                if previous.height != n_old:
                    raise AssertionError(f"{track}: old point alignment ended early")
                for field in OLD_COLUMNS:
                    maxima[field] = max(maxima[field], _same_numeric(
                        previous[field].to_numpy(), arrays[field][present],
                        atol=1e-9 if field != "point_check_pass_basic" else 0,
                        label=f"{track}/legacy/{field}",
                    ))
            raw, checked = raw.replace_schema_metadata(metadata), checked.replace_schema_metadata(metadata)
            if raw_writer is None:
                raw_writer = pq.ParquetWriter(str(raw_path) + ".tmp", raw.schema, compression="zstd")
                checked_writer = pq.ParquetWriter(str(checked_path) + ".tmp", checked.schema, compression="zstd")
            raw_writer.write_table(raw)
            checked_writer.write_table(checked)
            totals.update(counts)
            quality.update(codes)
    finally:
        if raw_writer is not None:
            raw_writer.close()
            checked_writer.close()
    for path in (raw_path, checked_path):
        Path(str(path) + ".tmp").replace(path)
    if old is not None and old.height != totals["legacy_point_rows"]:
        raise AssertionError(f"{track}: old point alignment has remaining rows")
    evidence = job.get("evidence", {})
    if evidence:
        for key in ("source_rows", "short_source_rows"):
            if totals[key] != evidence[key]:
                raise AssertionError(f"{track}: {key}={totals[key]} != evidence {evidence[key]}")
        if totals["basic_selected"] != (evidence["selected_points"] or 0):
            raise AssertionError(f"{track}: basic selected count changed")
        if sign != (evidence.get("sign") or "no_depth_values"):
            raise AssertionError(f"{track}: source depth sign differs from historical evidence")
    branch = {"singlebeam": "singlebeam", "multibeam": "multibeam_ncei"}.get(prediction, "unclassified")
    l2 = {}
    for policy, path in (("basic", basic_cells), ("basic_source_quality", main_cells)):
        l2[policy] = file_cells.aggregate_track_file(
            input_path=checked_path, output_path=path, track_id=track,
            source_type="ncei_xyz", source_completeness="xyz_only",
            instrument_class_pred=prediction, branch=branch, manual_review_flag=prediction == "multibeam",
            overwrite=job["overwrite"], selection_policy=policy, batch_size=job["chunk_size"],
        )
    cell_maxima = _compare_cells(basic_cells, legacy_root / "file_cells_1min" / f"{track}__xyz.parquet") if old is not None else {}
    checked_rows = _verify_saved(
        source, checked_path, sign, prediction, header, job["chunk_size"], legacy_aligned,
    )
    if checked_rows != totals["source_rows"] or pq.read_metadata(raw_path).num_rows != checked_rows:
        raise AssertionError(f"{track}: source/raw/checked counts differ")
    quality_rows = [
        {"field": field, "code": code, "selection": selection, "count": count}
        for (field, code, selection), count in sorted(quality.items())
    ]
    report = {
        "track_id": track, "source_file": str(source.resolve()), "source_bytes": source.stat().st_size,
        "source_mtime_ns": source.stat().st_mtime_ns, "instrument_class_pred": prediction,
        "classification_source": "retained_previous_manifest" if job["previous"] else "no_retained_prediction_unclassified",
        "depth_sign_raw": sign, "status": "no_selected_depth" if totals["basic_selected"] == 0 else "completed",
        "source_header": header.fields, "source_header_file": str(header.source_path),
        "source_header_survey_id_mismatch": header.fields["SURVEY_ID"].casefold() != track.casefold(),
        **dict(totals), "source_record_comparison_rows": checked_rows,
        "source_record_mismatches": 0, "legacy_point_max_differences": maxima,
        "historical_comparison_supplied": bool(evidence), "legacy_point_alignment_verified": legacy_aligned,
        "legacy_point_comparison_rows": totals["legacy_point_rows"] if legacy_aligned else 0,
        "xyz_compatible_rows": totals["legacy_point_rows"],
        "basic_cell_max_differences": cell_maxima, "quality_counts": quality_rows,
        "l2": l2, "previous_manifest": job["previous"],
        "output_bytes": sum(path.stat().st_size for path in (raw_path, checked_path, main_cells, basic_cells)),
        "runtime_seconds": time.monotonic() - start,
        "worker_peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, allow_nan=True) + "\n")
    return report


def verify_previous_quality(reports: list[dict], root: Path, evidence_root: Path) -> dict:
    """Compare code counts on the historical XYZ scope, not all original rows."""
    previous = pd.read_csv(evidence_root / "static_source_quality.csv", keep_default_na=False)
    field_names = {"navigation_quality": "NAV_QUALCO", "bathymetry_quality": "BAT_QUALCO"}
    comparisons = []
    compared_tracks = []
    for report in reports:
        track = report["track_id"]
        old = previous[previous.track_id == track]
        if old.empty:
            continue
        compared_tracks.append(track)
        current = Counter()
        for row in report["quality_counts"]:
            if row["field"] in field_names.values() and row["selection"] in ("basic", "legacy_source"):
                current[(row["field"], row["code"].strip(), row["selection"])] += row["count"]
        # The already-published five-source pilot predates the explicit scope count.
        if not any(key[2] == "legacy_source" for key in current):
            data = pl.read_parquet(
                root / "points_checked" / f"{track}__mgd77t.parquet",
                columns=["legacy_point_index_in_track", "NAV_QUALCO_raw", "BAT_QUALCO_raw"],
            ).filter(pl.col("legacy_point_index_in_track").is_not_null())
            for field in field_names.values():
                for row in data.group_by(f"{field}_raw").len().to_dicts():
                    current[(field, row[f"{field}_raw"].strip(), "legacy_source")] += row["len"]
        expected = Counter()
        for row in old.itertuples(index=False):
            field, code = field_names[row.field], str(row.code).strip()
            expected[(field, code, "legacy_source")] += int(row.source_count)
            expected[(field, code, "basic")] += int(row.basic_selected_count)
        for key in sorted(set(current) | set(expected)):
            field, code, selection = key
            actual, prior = current[key], expected[key]
            comparisons.append({
                "track_id": track, "field": field, "code": code, "selection": selection,
                "previous_count": prior, "revised_count": actual, "difference": actual - prior,
            })
            if actual != prior:
                raise AssertionError(f"{track}/{field}/{code}/{selection}: {actual} != {prior}")
    pd.DataFrame(comparisons).to_csv(root / "legacy_source_quality_comparison.csv", index=False)
    return {
        "tracks_with_prior_quality": len(compared_tracks),
        "tracks_without_prior_quality": sorted(set(r["track_id"] for r in reports) - set(compared_tracks)),
        "code_count_comparisons": len(comparisons), "code_count_mismatches": 0,
    }


def summarize_batch(reports: list[dict], root: Path, evidence_root: Path | None = None) -> dict:
    summaries, headers, qualities, layer_rows = [], [], [], []
    for report in sorted(reports, key=lambda row: row["track_id"]):
        track = report["track_id"]
        row = {key: value for key, value in report.items() if not isinstance(value, (dict, list))}
        for key in ("basic", "basic_source_quality"):
            row[f"cells_{key}"] = report["l2"][key]["n_cells"]
            layer_rows.append(report["l2"][key])
        summaries.append(row)
        headers.append({"track_id": track, "source_header_file": report["source_header_file"], **report["source_header"]})
        qualities.extend({"track_id": track, **entry} for entry in report["quality_counts"])
    pd.DataFrame(summaries).to_parquet(root / "source_manifest.parquet", index=False)
    pd.DataFrame(summaries).to_csv(root / "source_comparison.csv", index=False)
    pd.DataFrame(headers).fillna("").to_parquet(root / "source_headers.parquet", index=False)
    pd.DataFrame(qualities).to_csv(root / "source_quality_counts.csv", index=False)
    layers = pd.DataFrame(layer_rows)
    layers.to_parquet(root / "file_cells_manifest.parquet", index=False)
    log = logging.getLogger(__name__)
    merged = []
    for policy in ("basic", "basic_source_quality"):
        selected = layers[layers.selection_policy == policy]
        for branch in ("singlebeam", "multibeam_ncei"):
            cells, info = merge_cells.merge_branch(
                branch, selected[selected.branch == branch], reason_col=None, logger=log,
            )
            target = root / "merged_cells_1min" / policy
            target.mkdir(parents=True, exist_ok=True)
            cells.to_parquet(target / f"{branch}.parquet", index=False)
            merged.append({"selection_policy": policy, **info})
    pd.DataFrame(merged).to_csv(root / "merged_cell_summary.csv", index=False)
    counters = (
        "source_rows", "short_source_rows", "legacy_point_rows", "basic_selected",
        "source_quality_selected", "nav_rejected_basic", "bat_rejected_basic",
        "both_rejected_basic", "union_rejected_basic", "nav_unspecified", "bat_unspecified",
        "utc_time_present", "source_time_missing", "valid_time_timezone_unspecified",
        "source_time_invalid", "source_blank_depth", "source_depth_sentinels",
        "source_record_comparison_rows", "source_record_mismatches", "output_bytes",
    )
    summary = {"tracks": len(reports), **{key: sum(report.get(key, 0) for report in reports) for key in counters}}
    summary["instrument_class_counts"] = dict(Counter(report["instrument_class_pred"] for report in reports))
    summary["source_header_survey_id_mismatches"] = [r["track_id"] for r in reports if r["source_header_survey_id_mismatch"]]
    summary["source_header_field_counts"] = dict(Counter(len(r["source_header"]) for r in reports))
    summary["status_counts"] = dict(Counter(r["status"] for r in reports))
    summary["cells_basic"] = sum(r["l2"]["basic"]["n_cells"] for r in reports)
    summary["cells_basic_source_quality"] = sum(r["l2"]["basic_source_quality"]["n_cells"] for r in reports)
    summary["processing_runtime_sum_seconds"] = sum(r["runtime_seconds"] for r in reports)
    summary["worker_peak_rss_mib"] = max(r.get("worker_peak_rss_mib", 0) for r in reports)
    summary["unmerged_unclassified_selected_points"] = sum(
        r["source_quality_selected"] for r in reports if r["instrument_class_pred"] == "unclassified"
    )
    if evidence_root is not None:
        summary["previous_quality_comparison"] = verify_previous_quality(reports, root, evidence_root)
    (root / "comparison_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def run_points(args: argparse.Namespace) -> int:
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    prediction_path = args.classification_manifest
    if prediction_path is None and not args.no_legacy_comparison:
        prediction_path = args.legacy_root / "sb_round2_static_source_manifest_fragment.parquet"
    if args.classification_manifest is not None or (prediction_path is not None and prediction_path.exists()):
        previous = {row["track_id"]: row for row in pl.read_parquet(prediction_path).to_dicts()}
    else:
        previous = {}
    evidence = {
        row["track_id"]: row for row in pl.read_csv(args.evidence_root / "static_track_comparison.csv").to_dicts()
    } if args.evidence_root is not None else {}
    sources = sorted(args.source_root.glob("*/*.m77t"))
    tracks = {name.lower() for name in args.tracks} if args.tracks else {source.stem for source in sources}
    jobs = [{
        "source": str(source), "output_root": str(root), "legacy_root": str(args.legacy_root.resolve()),
        "previous": previous.get(source.stem, {}), "evidence": evidence.get(source.stem, {}),
        "chunk_size": args.chunk_size, "overwrite": args.overwrite, "resume": args.resume,
        "compare_legacy": not args.no_legacy_comparison,
    } for source in sources if source.stem in tracks]
    if {Path(job["source"]).stem for job in jobs} != tracks:
        raise ValueError("some requested tracks have no complete source file")
    started = time.monotonic()
    reports = []
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=mp.get_context("spawn")) as pool:
        futures = {pool.submit(process_source_track, job): job for job in jobs}
        for future in as_completed(futures):
            report = future.result()
            reports.append(report)
            print(
                f"{len(reports)}/{len(jobs)} {report['track_id']}: "
                f"{report['source_rows']} source, basic={report['basic_selected']}, "
                f"source_quality={report['source_quality_selected']}, "
                f"{report['runtime_seconds']:.1f}s", flush=True,
            )
    summary = summarize_batch(reports, root, args.evidence_root)
    summary["wall_seconds"] = time.monotonic() - started
    (root / "comparison_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ncei.trackline mgd77t-points", description=__doc__)
    parser.add_argument("--tracks", nargs="*", default=None)
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=REPO_ROOT / "ncei/raw_round2/mgd77t_static")
    parser.add_argument("--legacy-root", type=Path, default=LEGACY_ROOT)
    parser.add_argument("--evidence-root", type=Path, help="Optional historical source-comparison tables; not required for conversion.")
    parser.add_argument("--no-legacy-comparison", action="store_true", help="Do not read historical point products or their manifest.")
    parser.add_argument("--classification-manifest", type=Path, help="Optional retained instrument predictions, independent of point comparisons.")
    parser.add_argument("--chunk-size", type=int, default=100_000)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    return run_points(args)
