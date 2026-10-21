#!/usr/bin/env python3
"""Deliver candidate-neighbourhood soundings and 1-arcmin cells to 14-seamounts.

Run from the repository root:
    python -m ncei.analysis.seamount_candidate_delivery

The point radius applies to sounding coordinates. The cell radius applies to
cell centres and includes unobserved cells. Existing products are read-only.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from ncei.swath import quality_revision as qr
from ncei.trackline.file_cells import point_selection_mask, record_exclusion_mask

JAM_ROOT = ROOT / "jamstec/multibeam"
DIAGNOSIS_ROOT = ROOT / "ncei/derived/mb_round2/_runs/20261021_hnro14rr_diagnosis"
V1 = DIAGNOSIS_ROOT / "affected_records.parquet"
UNION = DIAGNOSIS_ROOT / "v2/affected_records_v1_union_v2.parquet"
EARTH_RADIUS_KM = 6371.0088
VARIANTS = {
    "all_good": "",
    "without_v1": "without_located_records",
    "without_v1_union_v2": "without_v1_union_v2_records",
}
SELECTED = [f"selected_{name}" for name in VARIANTS]
NCEI_COLUMNS = [
    "point_index_in_track", "time", "lon", "lat", "depth_m_positive_down",
    "filekey", "file_ordinal", "point_index_in_file", "staging_row",
    "native_quality_state", "point_check_pass_basic",
    "valid_lon", "valid_lat", "valid_depth_pos", "valid_depth_max", "valid_core_fields",
]
STRING_COLUMNS = [
    "region", "source", "cruise", "filekey", "file_id", "source_relpath",
    "l1_relpath", "native_quality_state", "cell_id", "date_raw", "time_raw",
    "file_quality_flag", "file_quality_reason", "file_quality_flag_source", "qc_reason",
]
INTEGER_COLUMNS = [
    "delivery_point_id", "point_index_in_track", "file_ordinal",
    "point_index_in_file", "staging_row", "qc_row", "sonar_idx",
]
BOOLEAN_COLUMNS = [
    "point_check_pass_basic", *SELECTED, "in_v1_record_list", "in_v1_union_v2_record_list",
    "selected_jamstec_qcfiltered", "exclude_from_primary_cells",
    "include_in_points_raw", "in_file_cells_manifest",
    "valid_lon", "valid_lat", "valid_depth_pos", "valid_depth_max", "valid_core_fields",
    "qc_valid_lon", "qc_valid_lat", "qc_depth_positive", "qc_depth_not_extreme",
    "qc_elev_negative", "qc_no_nan", "qc_zero_depth", "qc_pass_basic",
]
POINT_SCHEMA = pa.schema(
    [(c, pa.string()) for c in STRING_COLUMNS]
    + [(c, pa.int64()) for c in INTEGER_COLUMNS]
    + [(c, pa.bool_()) for c in BOOLEAN_COLUMNS]
    + [(c, pa.float64()) for c in ["lon", "lat", "depth_m_positive_down"]]
    + [("time", pa.timestamp("ns"))]
)


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def distance_km(lon, lat, centre_lon: float, centre_lat: float):
    """Great-circle distance on a sphere with mean Earth radius 6371.0088 km."""
    phi = np.deg2rad(lat)
    phi0 = math.radians(centre_lat)
    dlambda = np.deg2rad(lon - centre_lon)
    a = np.sin((phi - phi0) / 2) ** 2 + np.cos(phi) * math.cos(phi0) * np.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def cap_bounds(lon: float, lat: float, radius_km: float, padding_deg: float = 0) -> tuple:
    angle = radius_km / EARTH_RADIUS_KM
    dy = math.degrees(angle)
    dx = math.degrees(math.asin(math.sin(angle) / math.cos(math.radians(lat))))
    return lon - dx - padding_deg, lon + dx + padding_deg, lat - dy - padding_deg, lat + dy + padding_deg


def candidate_filter(candidates: pd.DataFrame, radius: float, *, cells=False, padding=0):
    lon, lat = ("lon_center", "lat_center") if cells else ("lon", "lat")
    expression = None
    for row in candidates.itertuples():
        w, e, s, n = cap_bounds(row.lon, row.lat, radius, padding)
        term = (ds.field(lon) >= w) & (ds.field(lon) <= e) & (ds.field(lat) >= s) & (ds.field(lat) <= n)
        expression = term if expression is None else expression | term
    return expression


def load_candidates(run: Path) -> pd.DataFrame:
    summary = json.loads((run / "run_summary.json").read_text())
    frames = []
    for region in qr.REGIONS:
        ids = (["V006", "V018", "V029"] if region == "japan_sea"
               else summary["regions"][region]["begin_depth_measurement_ids"])
        path = qr.CANDIDATES / f"20261019-vgg-pick-vs-ship-{region.replace('_', '-')}/candidates.csv"
        frame = pd.read_csv(path, usecols=["candidate_id", "candidate_key", "lon", "lat"])
        frame = frame[frame.candidate_id.isin(ids)].copy()
        assert set(frame.candidate_id) == set(ids)
        frame["region"] = region
        frame["candidate_source_path"] = str(path)
        frames.append(frame)
    result = pd.concat(frames, ignore_index=True)
    assert len(result) == 58
    return result


def append_table(writers: dict, path: Path, frame: pd.DataFrame, schema=None) -> None:
    if frame.empty:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if schema is not None:
        for field in schema:
            if field.name not in frame:
                frame[field.name] = None
        frame = frame[schema.names]
    table = pa.Table.from_pandas(frame, schema=schema, preserve_index=False)
    if path not in writers:
        writers[path] = pq.ParquetWriter(path, table.schema, compression="zstd")
    writers[path].write_table(table, row_group_size=250_000)


def point_flags(frame: pd.DataFrame, v1: pd.DataFrame, union: pd.DataFrame) -> pd.DataFrame:
    frame["in_v1_record_list"] = record_exclusion_mask(frame, v1)
    frame["in_v1_union_v2_record_list"] = record_exclusion_mask(frame, union)
    frame[SELECTED[0]] = point_selection_mask(frame, "basic_native_good")
    frame[SELECTED[1]] = frame[SELECTED[0]] & ~frame["in_v1_record_list"]
    frame[SELECTED[2]] = frame[SELECTED[0]] & ~frame["in_v1_union_v2_record_list"]
    return frame


def source_file_row(source: str, cruise: str, filekey: str, raw: Path, l1: Path, n_rows: int) -> dict:
    return {
        "source": source, "cruise": cruise, "filekey": filekey,
        "source_relpath": relative(raw), "source_path": str(raw),
        "source_exists": raw.is_file(), "l1_relpath": relative(l1),
        "l1_exists": l1.is_file(), "input_file_point_count": int(n_rows),
    }


def jamstec_batches(path: Path, candidates: pd.DataFrame, radius: float):
    """Retain absolute QC row positions; native file indices can repeat."""
    parquet = pq.ParquetFile(path)
    bounds = [cap_bounds(c.lon, c.lat, radius, 1 / 60 + 1e-9) for c in candidates.itertuples()]
    lon_column = parquet.schema_arrow.get_field_index("lon")
    lat_column = parquet.schema_arrow.get_field_index("lat")
    expression = candidate_filter(candidates, radius, padding=1 / 60 + 1e-9)
    offset = 0
    for group_id in range(parquet.num_row_groups):
        group = parquet.metadata.row_group(group_id)
        lon = group.column(lon_column).statistics
        lat = group.column(lat_column).statistics
        overlaps = (lon is None or lat is None or not lon.has_min_max or not lat.has_min_max
                    or any(lon.max >= w and lon.min <= e and lat.max >= s and lat.min <= n
                           for w, e, s, n in bounds))
        if not overlaps:
            offset += group.num_rows
            continue
        for batch in parquet.iter_batches(batch_size=250_000, row_groups=[group_id], use_threads=False):
            table = pa.Table.from_batches([batch]).append_column(
                "qc_row", pa.array(np.arange(offset, offset + batch.num_rows, dtype=np.int64))
            )
            offset += batch.num_rows
            yield ds.dataset(table).to_table(filter=expression, use_threads=False).to_pandas()
    assert offset == parquet.metadata.num_rows


def consume_points(
    frame: pd.DataFrame, candidates: pd.DataFrame, source: str, cruise: str,
    radius: float, output: Path, writers: dict, next_id: int,
    point_counts: Counter, file_counts: Counter, checks: Counter,
) -> int:
    """Write unique soundings and candidate membership; count cell-edge differences."""
    if frame.empty:
        return next_id
    frame = frame.reset_index(drop=True)
    region = candidates.iloc[0].region
    frame["cell_id"] = qr.point_cells(frame, jamstec=source == "jamstec")
    frame["region"], frame["source"], frame["cruise"] = region, source, cruise
    scale = 1 / 60
    if source == "jamstec":
        xb, yb = np.floor((frame.lon + 180) / scale), np.floor((frame.lat + 90) / scale)
    else:
        xb, yb = np.floor((frame.lon + 180) * 60), np.floor((frame.lat + 90) * 60)
    centre_lon, centre_lat = (xb + .5) / 60 - 180, (yb + .5) / 60 - 90
    selected_columns = SELECTED if source == "ncei" else ["selected_jamstec_qcfiltered"]
    memberships = []
    retained = np.zeros(len(frame), dtype=bool)
    for candidate in candidates.itertuples():
        distances = distance_km(frame.lon.to_numpy(), frame.lat.to_numpy(), candidate.lon, candidate.lat)
        inside = distances <= radius
        centres_inside = distance_km(centre_lon, centre_lat, candidate.lon, candidate.lat) <= radius
        key = (region, candidate.candidate_id, source)
        point_counts[(*key, "n_points")] += int(inside.sum())
        point_counts[(*key, "n_basic_pass")] += int((inside & frame.point_check_pass_basic).sum())
        point_counts[(*key, "n_depth_missing")] += int((inside & frame.depth_m_positive_down.isna()).sum())
        for state in ["good", "flagged", "null", "unknown"]:
            point_counts[(*key, f"n_native_{state}")] += int((inside & frame.native_quality_state.eq(state)).sum())
        for column in selected_columns:
            selected = frame[column].to_numpy(dtype=bool)
            point_counts[(*key, column)] += int((inside & selected).sum())
            check_key = (region, candidate.candidate_id, source, cruise, column)
            checks[(*check_key, "point_radius_count")] += int((inside & selected).sum())
            checks[(*check_key, "cell_centre_count_from_l1")] += int((centres_inside & selected).sum())
            checks[(*check_key, "inside_point_outside_cell")] += int((inside & ~centres_inside & selected).sum())
            checks[(*check_key, "outside_point_inside_cell")] += int((~inside & centres_inside & selected).sum())
        if inside.any():
            retained |= inside
            memberships.append((candidate.candidate_id, np.flatnonzero(inside), distances[inside]))
    if not retained.any():
        return next_id
    positions = np.flatnonzero(retained)
    ids = np.full(len(frame), -1, dtype=np.int64)
    ids[positions] = np.arange(next_id, next_id + len(positions))
    frame["delivery_point_id"] = ids
    points = frame.loc[retained].copy()
    for filekey, count in points.groupby("filekey").size().items():
        file_counts[(source, cruise, filekey, "n_points")] += int(count)
    for candidate_id, rows, distances in memberships:
        member = pd.DataFrame({
            "region": region, "source": source, "cruise": cruise,
            "candidate_id": candidate_id, "delivery_point_id": ids[rows], "distance_km": distances,
        })
        for filekey, count in frame.iloc[rows].groupby("filekey").size().items():
            file_counts[(source, cruise, filekey, "n_candidate_point_rows")] += int(count)
        append_table(writers, output / "l1" / region / source / cruise / "memberships.parquet", member)
    append_table(writers, output / "l1" / region / source / cruise / "points.parquet", points, POINT_SCHEMA)
    return next_id + len(points)


def l2_neighbourhood_counts(cells: pd.DataFrame, candidates: pd.DataFrame, radius: float, count_col: str) -> dict:
    return {
        c.candidate_id: int(cells.loc[
            distance_km(cells.lon_center, cells.lat_center, c.lon, c.lat) <= radius, count_col
        ].sum())
        for c in candidates.itertuples()
    }


def export_points(run: Path, output: Path, candidates: pd.DataFrame, radius: float) -> dict:
    v1, union = qr.read_record_list(V1), qr.read_record_list(UNION)
    writers, point_counts, file_counts, checks = {}, Counter(), Counter(), Counter()
    file_rows, expected, partitions = [], Counter(), []
    for cruise in qr.CRUISES:
        manifest = pd.read_parquet(run / cruise / "extraction_manifest.parquet")
        l1 = next((run / cruise / "points_checked").glob("*.parquet"))
        mapping = manifest.set_index(["filekey", "file_ordinal"])
        assert mapping.index.is_unique
        for rec in manifest.itertuples():
            raw = ROOT / "ncei/raw_round2/platforms_tree" / rec.source_relpath
            file_rows.append(source_file_row("ncei", cruise, rec.filekey, raw, l1, rec.n_rows))
        exclusions = [d[d.filekey.isin(manifest.filekey)] for d in [v1, union]]
        for region, group in candidates.groupby("region", sort=False):
            next_id = 0
            scanner = ds.dataset(l1).scanner(
                columns=NCEI_COLUMNS, filter=candidate_filter(group, radius, padding=1 / 60 + 1e-9),
                batch_size=250_000, use_threads=False,
            )
            for batch in scanner.to_batches():
                frame = batch.to_pandas()
                if frame.empty:
                    continue
                lookup = mapping.reindex(pd.MultiIndex.from_frame(frame[["filekey", "file_ordinal"]]))
                assert lookup.source_relpath.notna().all()
                assert ((frame.staging_row.to_numpy() >= 0) & (frame.staging_row.to_numpy() < lookup.n_rows.to_numpy())).all()
                frame["source_relpath"] = ("ncei/raw_round2/platforms_tree/" + lookup.source_relpath).to_numpy()
                frame["l1_relpath"] = relative(l1)
                frame = point_flags(frame, *exclusions)
                next_id = consume_points(
                    frame, group, "ncei", cruise, radius, output, writers, next_id,
                    point_counts, file_counts, checks,
                )
            partitions.append({"region": region, "source": "ncei", "cruise": cruise, "n_unique_points": next_id})
            for variant, dirname in VARIANTS.items():
                cell_path = next((run / dirname / cruise / "file_cells_1min").glob("*.parquet"))
                cells = pd.read_parquet(cell_path, columns=["lon_center", "lat_center", "n_points_pass"])
                for candidate, count in l2_neighbourhood_counts(cells, group, radius, "n_points_pass").items():
                    expected[(region, candidate, "ncei", cruise, f"selected_{variant}")] = count
        print(f"L1 NCEI {cruise}: extraction complete", flush=True)

    manifest = pd.read_parquet(JAM_ROOT / "manifests/file_manifest_points_raw.parquet")
    qc = pd.read_parquet(JAM_ROOT / "manifests/points_qc_manifest.parquet").set_index("file_id")
    quality = pd.read_parquet(JAM_ROOT / "manifests/file_quality_flags_1min.parquet").set_index("file_id")
    file_cells = pd.read_parquet(JAM_ROOT / "manifests/file_cells_manifest_1min.parquet").set_index("file_id")
    jam_ids = Counter()
    # The source manifest contains full-file coordinate extrema, not sampled bounds.
    for region, group in candidates.groupby("region", sort=False):
        intersects = np.zeros(len(manifest), dtype=bool)
        for c in group.itertuples():
            w, e, s, n = cap_bounds(c.lon, c.lat, radius, 1 / 60 + 1e-9)
            intersects |= (
                manifest.lon_max.ge(w) & manifest.lon_min.le(e)
                & manifest.lat_max.ge(s) & manifest.lat_min.le(n)
            ).to_numpy()
        files = manifest[intersects & manifest.include_in_points_raw]
        assert files.file_id.isin(qc.index).all()
        for rec in files.itertuples():
            cruise = rec.cruise_id_guess
            l1 = JAM_ROOT / qc.loc[rec.file_id, "output_path"]
            raw = JAM_ROOT / "raw/dat_by_subzip" / rec.relative_path
            q = quality.loc[rec.file_id]
            file_rows.append(source_file_row("jamstec", cruise, rec.file_id, raw, l1, qc.loc[rec.file_id, "rows_written"]))
            included = rec.file_id in file_cells.index and not bool(q.exclude_from_primary_cells)
            if included:
                cells = pd.read_parquet(
                    JAM_ROOT / file_cells.loc[rec.file_id, "output_path"],
                    columns=["lon_center", "lat_center", "n_points"],
                )
                for candidate, count in l2_neighbourhood_counts(cells, group, radius, "n_points").items():
                    expected[(region, candidate, "jamstec", cruise, "selected_jamstec_qcfiltered")] += count
            for frame in jamstec_batches(l1, group, radius):
                if frame.empty:
                    continue
                assert frame.file_id.eq(rec.file_id).all()
                frame["filekey"] = rec.file_id
                frame["source_relpath"], frame["l1_relpath"] = relative(raw), relative(l1)
                frame["native_quality_state"] = pd.Series(None, index=frame.index, dtype="string")
                frame["point_check_pass_basic"] = frame.qc_pass_basic
                frame["include_in_points_raw"] = bool(rec.include_in_points_raw)
                frame["in_file_cells_manifest"] = rec.file_id in file_cells.index
                frame["exclude_from_primary_cells"] = bool(q.exclude_from_primary_cells)
                frame["file_quality_flag"] = q.quality_flag
                frame["file_quality_reason"] = q.flag_reason
                frame["file_quality_flag_source"] = q.flag_source
                frame["selected_jamstec_qcfiltered"] = frame.qc_pass_basic & included
                jam_ids[(region, cruise)] = consume_points(
                    frame, group, "jamstec", cruise, radius, output, writers, jam_ids[(region, cruise)],
                    point_counts, file_counts, checks,
                )
        print(f"L1 JAMSTEC {region}: {len(files)} source files scanned", flush=True)
    for (region, cruise), count in jam_ids.items():
        partitions.append({"region": region, "source": "jamstec", "cruise": cruise, "n_unique_points": count})
    for writer in writers.values():
        writer.close()

    files = pd.DataFrame(file_rows).drop_duplicates(["source", "cruise", "filekey"])
    for column in ["n_points", "n_candidate_point_rows"]:
        files[column] = [file_counts[(r.source, r.cruise, r.filekey, column)] for r in files.itertuples()]
    assert files.source_exists.all() and files.l1_exists.all()
    qr.write_table(files, output / "l1_source_files")
    rows = []
    for c in candidates.itertuples():
        for source in ["ncei", "jamstec"]:
            key = (c.region, c.candidate_id, source)
            columns = ["n_points", "n_basic_pass", "n_depth_missing"]
            columns += ([f"n_native_{s}" for s in ["good", "flagged", "null", "unknown"]] + SELECTED
                        if source == "ncei" else ["selected_jamstec_qcfiltered"])
            rows.append({"region": c.region, "candidate_id": c.candidate_id, "source": source,
                         **{col: point_counts[(*key, col)] for col in columns}})
    count_table = pd.DataFrame(rows)
    qr.write_table(count_table, output / "candidate_point_counts")
    partition_table = pd.DataFrame(partitions)
    qr.write_table(partition_table, output / "point_partitions")
    totals = partition_table.groupby(["region", "source"], as_index=False).n_unique_points.sum()
    totals = totals.merge(count_table.groupby(["region", "source"], as_index=False).sum(numeric_only=True, min_count=1))
    totals = totals.rename(columns={"n_points": "n_candidate_point_rows"})
    qr.write_table(totals, output / "region_source_point_counts")
    check_rows = []
    all_keys = set(expected) | {key[:-1] for key in checks}
    for key in sorted(all_keys):
        row = dict(zip(["region", "candidate_id", "source", "cruise", "selection"], key))
        row.update({col: checks[(*key, col)] for col in [
            "point_radius_count", "cell_centre_count_from_l1", "inside_point_outside_cell", "outside_point_inside_cell",
        ]})
        row["cell_centre_count_from_l2"] = expected[key]
        assert row["cell_centre_count_from_l1"] == row["cell_centre_count_from_l2"], row
        assert (row["point_radius_count"] - row["cell_centre_count_from_l2"]
                == row["inside_point_outside_cell"] - row["outside_point_inside_cell"]), row
        check_rows.append(row)
    qr.write_table(pd.DataFrame(check_rows), output / "l1_l2_radius_count_checks")
    summary = {"region_source_counts": totals.replace({np.nan: None}).to_dict("records"), "n_source_files_scanned": len(files),
               "n_source_files_contributing": int(files.n_points.gt(0).sum()),
               "n_cell_centre_count_checks": len(check_rows)}
    qr.write_json(summary, output / "l1_summary.json")
    return summary


def complete_grid(candidates: pd.DataFrame, radius: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    memberships = []
    for c in candidates.itertuples():
        w, e, s, n = cap_bounds(c.lon, c.lat, radius)
        xx, yy = np.meshgrid(
            np.arange(math.floor((w + 180) * 60) - 1, math.ceil((e + 180) * 60) + 1),
            np.arange(math.floor((s + 90) * 60) - 1, math.ceil((n + 90) * 60) + 1),
        )
        frame = pd.DataFrame({"lon_bin": xx.ravel(), "lat_bin": yy.ravel()})
        frame["lon_center"] = (frame.lon_bin + .5) / 60 - 180
        frame["lat_center"] = (frame.lat_bin + .5) / 60 - 90
        frame["distance_km"] = distance_km(frame.lon_center, frame.lat_center, c.lon, c.lat)
        frame = frame[frame.distance_km <= radius].copy()
        frame["cell_id"] = "1min_" + frame.lat_bin.astype(str) + "_" + frame.lon_bin.astype(str)
        frame["candidate_id"], frame["region"] = c.candidate_id, c.region
        memberships.append(frame)
    membership = pd.concat(memberships, ignore_index=True)
    grid = membership[["region", "cell_id", "lon_bin", "lat_bin", "lon_center", "lat_center"]].drop_duplicates("cell_id")
    return grid.reset_index(drop=True), membership[["region", "candidate_id", "cell_id", "distance_km"]]


def grid_join(grid: pd.DataFrame, observations: pd.DataFrame, count_col: str) -> pd.DataFrame:
    """Keep every lattice cell; absent observations have zero counts and null depths."""
    columns = [c for c in observations if c not in grid or c == "cell_id"]
    result = grid.merge(observations[columns], on="cell_id", how="left", indicator=True)
    result["is_missing"] = result.pop("_merge").eq("left_only")
    result[count_col] = result[count_col].fillna(0).astype("int64")
    return result


def export_cells(run: Path, output: Path, candidates: pd.DataFrame, radius: float) -> dict:
    ncei = {name: qr.read_cells(run / dirname, qr.CRUISES) for name, dirname in VARIANTS.items()}
    sb_root = ROOT / "ncei/derived/singlebeam/file_cells_1min_final_r2"
    sb_paths = sorted(sb_root.glob("*.parquet"))
    sb = ds.dataset([str(p) for p in sb_paths], format="parquet").to_table(
        columns=pq.read_schema(sb_paths[0]).names + ["__filename"],
        filter=candidate_filter(candidates, radius, cells=True),
    ).to_pandas()
    jam = ds.dataset(qr.JAM).to_table(filter=candidate_filter(candidates, radius, cells=True)).to_pandas()
    source_rows, summary_rows, region_rows = [], [], []
    contributing_sb = Counter()
    for region, group in candidates.groupby("region", sort=False):
        grid, membership = complete_grid(group, radius)
        base = output / "l2" / region
        base.mkdir(parents=True, exist_ok=True)
        grid.to_parquet(base / "grid_cells.parquet", index=False)
        membership.to_parquet(base / "memberships.parquet", index=False)
        observed = {}
        for variant, cells in ncei.items():
            sub = cells[cells.cell_id.isin(grid.cell_id)].copy()
            sub["cruise"] = sub.track_id.str.upper()
            full_cruises = []
            for cruise in qr.CRUISES:
                frame = grid_join(grid, sub[sub.cruise.eq(cruise)].drop(columns="cruise"), "n_points_pass")
                frame["cruise"] = cruise
                full_cruises.append(frame)
                path = next((run / VARIANTS[variant] / cruise / "file_cells_1min").glob("*.parquet"))
                source_rows.append({
                    "region": region, "source": "ncei", "variant": variant, "cruise": cruise,
                    "path": str(path), "exists": path.is_file(),
                    "input_rows": pq.read_metadata(path).num_rows,
                    "delivered_observed_rows": int((~frame.is_missing).sum()),
                    "delivered_point_count": int(frame.n_points_pass.sum()),
                })
            pd.concat(full_cruises, ignore_index=True).to_parquet(base / f"ncei_cruise_cells_{variant}.parquet", index=False)
            combined = grid_join(grid, qr.combined_cells(sub), "ncei_n_points")
            combined["ncei_n_cruise_cells"] = combined.ncei_n_cruise_cells.fillna(0).astype("int64")
            combined.to_parquet(base / f"ncei_combined_cells_{variant}.parquet", index=False)
            observed[("ncei", variant)] = combined[["cell_id", "is_missing", "ncei_n_points"]].rename(columns={"ncei_n_points": "n_points"})
        jam_full = grid_join(grid, jam[jam.cell_id.isin(grid.cell_id)], "n_points_total")
        jam_full.to_parquet(base / "jamstec_cells.parquet", index=False)
        observed[("jamstec", "qcfiltered")] = jam_full[["cell_id", "is_missing", "n_points_total"]].rename(columns={"n_points_total": "n_points"})
        source_rows.append({
            "region": region, "source": "jamstec", "variant": "qcfiltered", "cruise": None,
            "path": str(qr.JAM), "exists": qr.JAM.is_file(), "input_rows": pq.read_metadata(qr.JAM).num_rows,
            "delivered_observed_rows": int((~jam_full.is_missing).sum()),
            "delivered_point_count": int(jam_full.n_points_total.sum()),
        })
        sb_sub = sb[sb.cell_id.isin(grid.cell_id)].copy()
        assert not sb_sub.duplicated(["track_id", "cell_id"]).any()
        for filename, frame in sb_sub.groupby("__filename"):
            path = Path(filename)
            source_rows.append({
                "region": region, "source": "singlebeam", "variant": "all_dispositions",
                "cruise": ";".join(sorted(frame.track_id.unique())), "path": str(path),
                "exists": path.is_file(), "input_rows": pq.read_metadata(path).num_rows,
                "delivered_observed_rows": len(frame), "delivered_point_count": int(frame.n_points_pass.sum()),
            })
            contributing_sb[filename] += len(frame)
        sb_sub["source_relpath"] = sb_sub.pop("__filename").map(lambda p: relative(Path(p)))
        sb_full = grid_join(grid, sb_sub, "n_points_pass")
        sb_full.to_parquet(base / "singlebeam_track_cells.parquet", index=False)
        sb_counts = sb_sub.groupby("cell_id", as_index=False).n_points_pass.sum()
        sb_counts = grid_join(grid, sb_counts, "n_points_pass")
        observed[("singlebeam", "all_dispositions")] = sb_counts[["cell_id", "is_missing", "n_points_pass"]].rename(columns={"n_points_pass": "n_points"})
        availability = grid.copy()
        for (source, variant), frame in observed.items():
            availability[f"{source}_{variant}_missing"] = frame.is_missing.to_numpy()
            joined = membership.merge(frame, on="cell_id", validate="many_to_one")
            for candidate, sub in joined.groupby("candidate_id"):
                summary_rows.append({
                    "region": region, "candidate_id": candidate, "source": source, "variant": variant,
                    "n_neighbourhood_cells": len(sub), "n_observed_cells": int((~sub.is_missing).sum()),
                    "n_missing_cells": int(sub.is_missing.sum()), "n_points": int(sub.n_points.sum()),
                })
        availability["all_sources_missing"] = (
            availability.ncei_all_good_missing & availability.jamstec_qcfiltered_missing
            & availability.singlebeam_all_dispositions_missing
        )
        availability.to_parquet(base / "cell_availability.parquet", index=False)
        w, e, s, n = qr.REGIONS[region]
        outside = ~(grid.lon_center.ge(w) & grid.lon_center.lt(e) & grid.lat_center.ge(s) & grid.lat_center.lt(n))
        region_rows.append({
            "region": region, "n_unique_grid_cells": len(grid), "n_candidate_cell_rows": len(membership),
            "n_outside_region_grid_cells": int(outside.sum()),
            "n_all_sources_missing_cells": int(availability.all_sources_missing.sum()),
            "n_singlebeam_observed_track_cells": len(sb_sub),
            "singlebeam_track_dispositions": sb_sub.track_disposition.value_counts().to_dict(),
        })
        print(f"L2 {region}: {len(grid):,} unique cells; {len(membership):,} candidate-cell rows", flush=True)
    files = pd.DataFrame(source_rows)
    assert files.exists.all()
    qr.write_table(files, output / "l2_source_files")
    qr.write_table(pd.DataFrame(summary_rows), output / "candidate_cell_counts")
    summary = {"regions": region_rows, "singlebeam_input_files": len(sb_paths),
               "singlebeam_contributing_files": len(contributing_sb)}
    qr.write_json(summary, output / "l2_summary.json")
    return summary


def check_samples(output: Path, candidates: pd.DataFrame, radius: float) -> dict:
    """Check persisted samples against L1 and an independent distance expression."""
    rows = []
    v1, union = qr.read_record_list(V1), qr.read_record_list(UNION)
    for path in sorted((output / "l1").glob("*/*/*/points.parquet")):
        points = pq.ParquetFile(path).read_row_group(0).to_pandas()
        sample = points.head(3)
        for column in ["native_quality_state", "point_check_pass_basic"]:
            sample = pd.concat([sample, points.drop_duplicates(column)])
        sample = sample.drop_duplicates("delivery_point_id")
        members = pd.read_parquet(
            path.with_name("memberships.parquet"),
            filters=[("delivery_point_id", "in", sample.delivery_point_id.tolist())],
        ).merge(sample, on=["region", "source", "cruise", "delivery_point_id"], validate="many_to_one")
        for row in members.itertuples():
            c = candidates[(candidates.region == row.region) & (candidates.candidate_id == row.candidate_id)].iloc[0]
            phi, phi0 = math.radians(row.lat), math.radians(c.lat)
            dlambda = math.radians(row.lon - c.lon)
            dot = math.sin(phi) * math.sin(phi0) + math.cos(phi) * math.cos(phi0) * math.cos(dlambda)
            independent = EARTH_RADIUS_KM * math.acos(max(-1, min(1, dot)))
            assert abs(independent - row.distance_km) < 1e-5
            assert row.distance_km <= radius
        for l1path, group in sample.groupby("l1_relpath"):
            l1 = ROOT / l1path
            if group.iloc[0].source == "ncei":
                original = pd.read_parquet(
                    l1, columns=NCEI_COLUMNS,
                    filters=[("point_index_in_track", "in", group.point_index_in_track.tolist())],
                )
                original = point_flags(original, v1, union)
                fields = ["filekey", "file_ordinal", "staging_row", "point_index_in_file",
                          "lon", "lat", "depth_m_positive_down", "time", "native_quality_state",
                          "point_check_pass_basic", *SELECTED]
                pd.testing.assert_frame_equal(
                    group.set_index("point_index_in_track")[fields].sort_index(),
                    original.set_index("point_index_in_track")[fields].sort_index(),
                    check_dtype=False,
                )
            else:
                parquet = pq.ParquetFile(l1)
                offset, originals = 0, []
                for group_id in range(parquet.num_row_groups):
                    n_rows = parquet.metadata.row_group(group_id).num_rows
                    positions = group.qc_row[(group.qc_row >= offset) & (group.qc_row < offset + n_rows)]
                    if len(positions):
                        original = parquet.read_row_group(group_id).to_pandas().iloc[
                            positions.to_numpy(dtype=np.int64) - offset
                        ].copy()
                        original["qc_row"] = positions.to_numpy(dtype=np.int64)
                        originals.append(original)
                    offset += n_rows
                original = pd.concat(originals, ignore_index=True)
                fields = ["file_id", "point_index_in_file", "lon", "lat",
                          "depth_m_positive_down", "qc_pass_basic", "qc_reason"]
                pd.testing.assert_frame_equal(
                    group.set_index("qc_row")[fields].sort_index(),
                    original.set_index("qc_row")[fields].sort_index(),
                    check_dtype=False,
                )
        rows.append({"path": relative(path), "sample_points": len(sample), "sample_memberships": len(members)})
    qr.write_table(pd.DataFrame(rows), output / "point_sample_checks")
    return {"partitions_checked": len(rows), "sample_points": sum(r["sample_points"] for r in rows),
            "sample_memberships": sum(r["sample_memberships"] for r in rows)}


def verify_delivery(output: Path) -> dict:
    """Check persisted partition keys, source ranges and explicit missing cells."""
    sources = pd.read_parquet(output / "l1_source_files.parquet")
    limits = sources.set_index(["source", "cruise", "filekey"]).input_file_point_count
    assert limits.index.is_unique
    columns = [
        "region", "source", "cruise", "delivery_point_id", "filekey", "file_ordinal",
        "staging_row", "qc_row", "native_quality_state", "point_check_pass_basic", *SELECTED,
        "selected_jamstec_qcfiltered", "qc_pass_basic", "exclude_from_primary_cells",
        "in_file_cells_manifest", "depth_m_positive_down", "lon", "lat",
    ]
    partitions = []
    for path in sorted((output / "l1").glob("*/*/*/points.parquet")):
        frame = pd.read_parquet(path, columns=columns)
        source, cruise, region = frame.iloc[0][["source", "cruise", "region"]]
        assert np.array_equal(frame.delivery_point_id, np.arange(len(frame)))
        assert np.isfinite(frame[["lon", "lat"]]).all().all()
        key_columns = ["filekey", "file_ordinal", "staging_row"] if source == "ncei" else ["filekey", "qc_row"]
        assert not frame.duplicated(key_columns).any()
        bounds = limits.reindex(pd.MultiIndex.from_frame(frame[["source", "cruise", "filekey"]]))
        row = frame.staging_row if source == "ncei" else frame.qc_row
        assert bounds.notna().all()
        assert ((row >= 0) & (row.to_numpy() < bounds.to_numpy())).all()
        if source == "ncei":
            expected = frame.point_check_pass_basic & frame.native_quality_state.eq("good")
            assert np.array_equal(expected, frame.selected_all_good)
            assert (frame.selected_without_v1 <= frame.selected_all_good).all()
            assert (frame.selected_without_v1_union_v2 <= frame.selected_without_v1).all()
        else:
            assert frame.native_quality_state.isna().all() and frame[SELECTED].isna().all().all()
            expected = frame.qc_pass_basic & ~frame.exclude_from_primary_cells & frame.in_file_cells_manifest
            assert np.array_equal(expected, frame.selected_jamstec_qcfiltered)
        w, e, s, n = qr.REGIONS[region]
        outside = ~(frame.lon.ge(w) & frame.lon.lt(e) & frame.lat.ge(s) & frame.lat.lt(n))
        partitions.append({
            "region": region, "source": source, "cruise": cruise, "n_points": len(frame),
            "n_outside_region_points": int(outside.sum()),
            "n_depth_missing": int(frame.depth_m_positive_down.isna().sum()),
            "n_unique_selected_all_good": int(frame.selected_all_good.sum()) if source == "ncei" else None,
            "n_unique_selected_jamstec_qcfiltered": int(frame.selected_jamstec_qcfiltered.sum()) if source == "jamstec" else None,
        })
    qr.write_table(pd.DataFrame(partitions), output / "point_partition_checks")
    grid_checks = []
    for region in qr.REGIONS:
        base = output / "l2" / region
        grid = pd.read_parquet(base / "grid_cells.parquet")
        membership = pd.read_parquet(base / "memberships.parquet")
        assert grid.cell_id.is_unique and not membership.duplicated(["candidate_id", "cell_id"]).any()
        assert set(grid.cell_id) == set(membership.cell_id)
        tables = [(f"ncei_combined_cells_{variant}", "ncei_median_depth_m", "ncei_n_points") for variant in VARIANTS]
        tables += [(f"ncei_cruise_cells_{variant}", "median_depth_m", "n_points_pass") for variant in VARIANTS]
        tables += [("jamstec_cells", "median_depth_file_balanced", "n_points_total"),
                   ("singlebeam_track_cells", "median_depth_m", "n_points_pass")]
        for name, depth, count in tables:
            frame = pd.read_parquet(base / f"{name}.parquet")
            assert set(frame.cell_id) == set(grid.cell_id)
            missing = frame.is_missing
            assert frame.loc[missing, depth].isna().all() and frame.loc[missing, count].eq(0).all()
            if name.startswith("ncei_cruise"):
                assert len(frame) == len(grid) * len(qr.CRUISES)
                assert not frame.duplicated(["cruise", "cell_id"]).any()
            elif name != "singlebeam_track_cells":
                assert frame.cell_id.is_unique
            grid_checks.append({
                "region": region, "table": name, "n_rows": len(frame),
                "n_missing_rows": int(missing.sum()), "n_points": int(frame[count].sum()),
            })
    qr.write_table(pd.DataFrame(grid_checks), output / "grid_table_checks")
    summary = {"n_point_partitions": len(partitions), "n_points_with_checked_keys": sum(p["n_points"] for p in partitions),
               "n_outside_region_points": sum(p["n_outside_region_points"] for p in partitions),
               "n_grid_tables": len(grid_checks)}
    qr.write_json(summary, output / "delivery_verification.json")
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=qr.RUN_ROOT)
    parser.add_argument("--output-dir", type=Path, default=qr.RUN_ROOT / "candidate_points")
    parser.add_argument("--point-radius-km", type=float, default=12.5)
    parser.add_argument("--cell-radius-km", type=float, default=90)
    parser.add_argument("--part", choices=["all", "l1", "l2"], default="all")
    args = parser.parse_args(argv)
    pa.set_cpu_count(4)
    pa.set_io_thread_count(4)
    assert 0 < args.point_radius_km <= args.cell_radius_km < 500
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    candidates = load_candidates(args.run_root)
    qr.write_table(candidates, output / "candidates")
    qr.write_json({
        "run_root": str(args.run_root.resolve()), "point_radius_km": args.point_radius_km,
        "cell_radius_km": args.cell_radius_km, "earth_radius_km": EARTH_RADIUS_KM,
        "v1_records": str(V1), "v1_union_v2_records": str(UNION),
        "command": [sys.executable, "-m", "ncei.analysis.seamount_candidate_delivery", *sys.argv[1:]],
    }, output / "parameters.json")
    if args.part in ("all", "l1"):
        export_points(args.run_root, output, candidates, args.point_radius_km)
        checks = check_samples(output, candidates, args.point_radius_km)
        qr.write_json(checks, output / "sample_check_summary.json")
    if args.part in ("all", "l2"):
        export_cells(args.run_root, output, candidates, args.cell_radius_km)
    if args.part == "all":
        verify_delivery(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
