#!/usr/bin/env python3
"""Rebuild round-2 L1/L2 and source-separated coverage in an isolated run.

Run from the repository root. Existing staging, production outputs, and
historical runs are read-only. NCEI combined depth remains the median of
cruise-cell medians, not a point-weighted statistic.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
PROD = ROOT / "ncei/derived/mb_round2"
RUN_ROOT = PROD / "_runs/20261021_quality_revision"
OLD_L2 = PROD / "_runs/20261020T_l2_l3_first_batch"
OLD_AUDIT = PROD / "_runs/20261020T_source_audit"
JAM = ROOT / "jamstec/multibeam/derived/cells_1min_qcfiltered/cells.parquet"
STRICT = ROOT / "ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet"
CANDIDATES = Path("/mnt/data2/06-Projects/14-seamounts/outputs")
CRUISES = [
    "RR1412", "PD20IB02", "EW9508", "TN168", "NT05-06", "NT05-16",
    "AII8L18", "HNRO14RR", "HNRO07RR", "HNRO06RR", "HNRO05RR",
    "COOK09MV", "PPTU11WT",
]
REGIONS = {"japan_sea": (132, 136, 36, 40), "izu_bonin": (140, 144, 28, 32)}
SELECTION_POLICY = "basic_native_good"
CELL_COLUMNS = [
    "cell_id", "lon_center", "lat_center", "track_id", "n_points_pass",
    "median_depth_m", "std_depth_m", "iqr_depth_m", "range_depth_m",
]


def load_module(filename: str):
    spec = importlib.util.spec_from_file_location(Path(filename).stem, ROOT / "ncei/code" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_table(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path.with_suffix(".parquet"), index=False)
    frame.to_csv(path.with_suffix(".tsv"), sep="\t", index=False)


def write_json(value: dict, path: Path) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def read_record_list(path: Path | None) -> pd.DataFrame | None:
    """Normalize the diagnosis key while retaining source-record evidence."""
    if path is None:
        return None
    records = pd.read_parquet(path)
    if "filekey" not in records and "staging_stem" in records:
        records["filekey"] = records["staging_stem"]
    keys = ["filekey", "file_ordinal", "staging_row"]
    if not set(keys).issubset(records.columns):
        raise ValueError(f"record list requires {keys}")
    if records[keys].isna().any().any() or records.duplicated(keys).any():
        raise ValueError("record list contains missing or duplicate point keys")
    return records


def rebuild_cruise(task: tuple) -> dict:
    cruise, run, l1_root, exclusion_path, resume = task
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    extract = load_module("34_mb_round2_extract_points.py")
    aggregate = load_module("07_aggregate_file_cells_1min.py")
    sources = load_module("36_mb_round2_source_manifest_fragment.py")
    output = run / cruise
    l1_dir = l1_root / cruise
    summary_path = l1_dir / "extraction_summary.json"
    if (resume or l1_root != run) and summary_path.exists():
        summary = json.loads(summary_path.read_text())
        manifest = pd.read_parquet(l1_dir / "extraction_manifest.parquet")
    else:
        manifest = pd.read_parquet(PROD / cruise / "extraction_manifest.parquet")
        source_path, manifest = sources.resolve_source_paths(cruise, manifest)
        summary = extract.merge_cruise(
            cruise, manifest, staging_dir=PROD / cruise / "_staging", output_dir=l1_dir
        )
        summary["source_path"] = source_path
        write_table(manifest, l1_dir / "extraction_manifest")
        write_json(summary, summary_path)
    checked = ROOT / summary["points_checked_path"]
    if pq.read_metadata(checked).num_rows != summary["n_rows"]:
        raise ValueError(f"{cruise}: L1 row count differs from its merge summary")
    if "native_quality_state" not in pq.read_schema(checked).names:
        raise ValueError(f"{cruise}: L1 has not been rebuilt with native quality")
    exclusions = None
    if exclusion_path is not None:
        exclusions = read_record_list(exclusion_path)
        exclusions = exclusions[exclusions["filekey"].isin(manifest["filekey"])].copy()
        keys = ["filekey", "file_ordinal", "staging_row"]
        exclusions = exclusions[keys].drop_duplicates()
        limits = manifest[["filekey", "file_ordinal", "n_rows"]]
        located = exclusions.merge(limits, on=["filekey", "file_ordinal"], how="left", validate="many_to_one")
        if located["n_rows"].isna().any() or not (
            (located["staging_row"] >= 0) & (located["staging_row"] < located["n_rows"])
        ).all():
            raise ValueError(f"{cruise}: exclusion keys are not in the staging inputs")
    l2_path = output / "file_cells_1min" / checked.name
    agg_summary_path = output / "aggregation_summary.json"
    if resume and agg_summary_path.exists():
        result = json.loads(agg_summary_path.read_text())
    elif l1_root != run and (exclusions is None or exclusions.empty):
        original = json.loads((l1_dir / "aggregation_summary.json").read_text())
        if original["n_excluded_selected_records"] != 0 or original["selection_policy"] != SELECTION_POLICY:
            raise ValueError(f"{cruise}: cannot reuse L2 with a different selection")
        source_l2 = ROOT / original["output_path"]
        l2_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_l2, l2_path)
        result = {
            **original, "output_path": str(l2_path.relative_to(ROOT)),
            "aggregation_reused_from": str(source_l2.relative_to(ROOT)),
        }
        write_json(result, agg_summary_path)
    else:
        result = aggregate.aggregate_track_file(
            input_path=checked, output_path=l2_path, track_id=cruise.lower(),
            source_type=f"ncei_mb{summary['mb_format']}",
            source_completeness=f"mb{summary['mb_format']}_only",
            instrument_class_pred="multibeam", branch="multibeam_ncei",
            manual_review_flag=False, overwrite=False,
            selection_policy=SELECTION_POLICY, batch_size=500_000,
            excluded_records=exclusions,
        )
        write_json(result, agg_summary_path)
    expected = summary["n_selected_basic_native_good"] - result["n_excluded_selected_records"]
    l2_points = int(pd.read_parquet(l2_path, columns=["n_points_pass"])["n_points_pass"].sum())
    if expected != result["n_selected"] or expected != l2_points:
        raise AssertionError(f"{cruise}: L1 selected {expected} != L2 {l2_points}")
    print(f"{cruise}: basic={summary['n_pass_basic']:,}; selected={expected:,}; cells={result['n_cells']:,}", flush=True)
    return {
        **summary, **result, "cruise": cruise, "l1_dir": str(l1_dir.relative_to(ROOT)),
        "n_input_files": len(manifest), "status": "completed",
    }


def source_manifest(rows: list[dict]) -> pd.DataFrame:
    records = []
    for row in rows:
        area = (
            (row["lon_max"] - row["lon_min"]) * (row["lat_max"] - row["lat_min"])
            * math.cos(math.radians((row["lat_min"] + row["lat_max"]) / 2)) * 111.32**2
        )
        records.append({
            "track_id": row["track_id"], "source_type": row["source_type"],
            "source_completeness": f"mb{row['mb_format']}_only", "source_path": row["source_path"],
            "source_archive": "NCEI platforms tree direct download; first batch 2026-10-19",
            "n_points": row["n_finite_position"],
            "bbox_lon_min": row["lon_min"], "bbox_lon_max": row["lon_max"],
            "bbox_lat_min": row["lat_min"], "bbox_lat_max": row["lat_max"],
            "bbox_area_km2": area, "point_density_km2": row["n_finite_position"] / area,
            "has_time": True, "has_depth": row["n_rows"] > row["n_depth_nan"],
            "has_gobs": False, "has_faa": False, "depth_sign_raw": row["depth_sign_raw"],
            "depth_min_raw": row["depth_min_raw"], "depth_max_raw": row["depth_max_raw"],
            "instrument_class_pred": "multibeam",
            "classification_rule": "known NCEI multibeam swath source",
            "classification_review": True, "review_reason": "source-separated comparison",
            "manual_override": "", "source_author": None, "survey_id": row["cruise"],
        })
    return pd.DataFrame(records)


def read_cells(root: Path, cruises: list[str]) -> pd.DataFrame:
    return pd.concat([
        pd.read_parquet(next((root / cruise / "file_cells_1min").glob("*.parquet")), columns=CELL_COLUMNS)
        for cruise in cruises
    ], ignore_index=True)


def box(frame: pd.DataFrame, bounds: tuple) -> pd.DataFrame:
    west, east, south, north = bounds
    return frame[
        frame["lon_center"].ge(west) & frame["lon_center"].lt(east)
        & frame["lat_center"].ge(south) & frame["lat_center"].lt(north)
    ].copy()


def combined_cells(cells: pd.DataFrame) -> pd.DataFrame:
    if cells.duplicated(["track_id", "cell_id"]).any():
        raise ValueError("duplicate (cruise, cell_id) rows")
    return cells.groupby("cell_id", as_index=False).agg(
        lon_center=("lon_center", "first"), lat_center=("lat_center", "first"),
        ncei_median_depth_m=("median_depth_m", "median"),
        ncei_mean_depth_m=("median_depth_m", "mean"),
        ncei_std_between_cruise_m=("median_depth_m", "std"),
        ncei_n_points=("n_points_pass", "sum"),
        ncei_n_cruise_cells=("track_id", "nunique"),
        ncei_source_cruises=("track_id", lambda s: ";".join(sorted(set(s)))),
        ncei_within_cell_iqr_m=("iqr_depth_m", "median"),
        ncei_within_cell_std_m=("std_depth_m", "median"),
        ncei_within_cell_range_m=("range_depth_m", "median"),
    )


def expected_cells(lon: float, lat: float) -> pd.DataFrame:
    """Enumerate actual 1-minute cell centers in the full 12.5-km disk."""
    dx_deg = 12.5 / (111.32 * math.cos(math.radians(lat)))
    dy_deg = 12.5 / 111.32
    xb = np.arange(math.floor((lon - dx_deg + 180) * 60) - 1,
                   math.ceil((lon + dx_deg + 180) * 60) + 2)
    yb = np.arange(math.floor((lat - dy_deg + 90) * 60) - 1,
                   math.ceil((lat + dy_deg + 90) * 60) + 2)
    xx, yy = np.meshgrid(xb, yb)
    xx, yy = xx.ravel(), yy.ravel()
    x, y = -180 + (xx + 0.5) / 60, -90 + (yy + 0.5) / 60
    dx = (x - lon) * 111.32 * math.cos(math.radians(lat))
    dy = (y - lat) * 111.32
    radius = np.hypot(dx, dy)
    # A cell center on a sector axis belongs to the counterclockwise sector.
    dx[np.abs(dx) < 1e-9] = 0
    dy[np.abs(dy) < 1e-9] = 0
    angle = np.mod(np.arctan2(dy, dx), 2 * np.pi)
    grid = pd.DataFrame({
        "cell_id": [f"1min_{a}_{b}" for a, b in zip(yy, xx)],
        "lon_center": x, "lat_center": y, "radius_km": radius,
        "sector": np.floor(angle / (np.pi / 4)).astype(int),
        "core": radius <= 4, "ring": (radius >= 8) & (radius < 12.5),
    })
    return grid[grid["radius_km"] < 12.5].reset_index(drop=True)


def coverage_metric(ids: set[str], grid: pd.DataFrame) -> dict:
    observed = grid["cell_id"].isin(ids).to_numpy()
    core, ring = grid["core"].to_numpy(), grid["ring"].to_numpy()
    expected_sector = np.bincount(grid.loc[ring, "sector"], minlength=8)
    sector = np.bincount(grid.loc[observed & ring, "sector"], minlength=8)
    fractions = sector / expected_sector
    return {
        "core_cells": int((observed & core).sum()),
        "core_coverage": float((observed & core).sum() / core.sum()),
        "ring_cells": int((observed & ring).sum()),
        "ring_coverage": float((observed & ring).sum() / ring.sum()),
        "ring_sectors": int((sector > 0).sum()),
        "min_sector_coverage": float(fractions.min()),
        "ring_sector_cells": ";".join(map(str, sector)),
        "ring_sector_coverage": ";".join(f"{value:.8f}" for value in fractions),
    }


def read_references(candidates: pd.DataFrame, bounds: tuple) -> tuple[pd.DataFrame, pd.DataFrame]:
    grids = pd.concat([expected_cells(r.lon, r.lat) for r in candidates.itertuples()], ignore_index=True)
    west, east, south, north = bounds
    extent = (
        min(west, grids["lon_center"].min()) - 1 / 60,
        max(east, grids["lon_center"].max()) + 1 / 60,
        min(south, grids["lat_center"].min()) - 1 / 60,
        max(north, grids["lat_center"].max()) + 1 / 60,
    )
    filters = [("lon_center", ">=", extent[0]), ("lon_center", "<", extent[1]),
               ("lat_center", ">=", extent[2]), ("lat_center", "<", extent[3])]
    jam = pd.read_parquet(JAM, filters=filters, columns=[
        "cell_id", "lon_center", "lat_center", "median_depth_file_balanced",
        "iqr_depth_between_file_cells", "std_depth_between_file_cells", "range_depth_file_cell",
        "n_points_total", "n_files", "n_cruises_guess", "dominant_cruise_id_guess", "dominant_file_id",
    ]).rename(columns={
        "median_depth_file_balanced": "jam_depth_m", "iqr_depth_between_file_cells": "jam_iqr_m",
        "std_depth_between_file_cells": "jam_std_m", "range_depth_file_cell": "jam_range_m",
        "n_points_total": "jam_n_points", "n_files": "jam_n_files", "n_cruises_guess": "jam_n_cruises",
        "dominant_cruise_id_guess": "jam_source_cruise", "dominant_file_id": "jam_source_file",
    })
    strict = pd.read_parquet(STRICT, filters=filters, columns=[
        "cell_id", "lon_center", "lat_center", "representative_depth_m",
        "n_points_pass_total", "n_track_cells", "n_tracks", "source_provider",
        "source_dataset", "final_primary_source", "quality_tier",
    ]).rename(columns={
        "representative_depth_m": "strict_depth_m", "n_points_pass_total": "strict_n_points",
        "n_track_cells": "strict_n_track_cells", "n_tracks": "strict_n_tracks",
        "source_provider": "strict_provider", "source_dataset": "strict_dataset",
        "final_primary_source": "strict_source",
    })
    for name, table in (("jam", jam), ("strict", strict)):
        if table["cell_id"].duplicated().any():
            raise ValueError(f"{name}: duplicate cell_id")
    return jam, strict


def residuals(ncei: pd.DataFrame, jam: pd.DataFrame, strict: pd.DataFrame, depth: str) -> pd.DataFrame:
    jam_cols = [c for c in jam if c not in ("lon_center", "lat_center")]
    strict_cols = [c for c in strict if c not in ("lon_center", "lat_center")]
    joined = ncei.merge(jam[jam_cols], on="cell_id", how="inner", validate="many_to_one")
    joined = joined.merge(strict[strict_cols], on="cell_id", how="left", validate="many_to_one")
    joined["ncei_jam_depth_diff_m"] = joined[depth] - joined["jam_depth_m"]
    joined["ncei_jam_abs_diff_m"] = joined["ncei_jam_depth_diff_m"].abs()
    joined["ncei_strict_depth_diff_m"] = joined[depth] - joined["strict_depth_m"]
    return joined


def residual_summary(frame: pd.DataFrame, region: str, grouping: list[str] | None = None) -> pd.DataFrame:
    groups = frame.groupby(grouping, dropna=False) if grouping else [((), frame)]
    rows = []
    for key, sub in groups:
        labels = dict(zip(grouping or [], key if isinstance(key, tuple) else (key,)))
        for column in ("ncei_jam_depth_diff_m", "ncei_strict_depth_diff_m"):
            values = sub[column].dropna()
            rows.append({
                "region": region, **labels, "comparison": column,
                "n_overlap": len(values), "median_m": values.median(), "mean_m": values.mean(),
                "std_m": values.std(), "p05_m": values.quantile(.05),
                "p25_m": values.quantile(.25), "p75_m": values.quantile(.75),
                "p95_m": values.quantile(.95), "abs_p95_m": values.abs().quantile(.95),
                "abs_gt_100m_cells": int(values.abs().gt(100).sum()),
            })
    return pd.DataFrame(rows)


def nmad(values: pd.Series) -> float:
    values = values.dropna()
    if values.empty:
        return float("nan")
    median = float(values.median())
    return float(1.4826 * np.median(np.abs(values.to_numpy() - median)))


def quality_tables(
    run: Path, cruises: list[str], l1_root: Path, exclusion_path: Path | None,
    diagnosis_path: Path | None,
    baseline_diagnosis_path: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Write descriptive file/cruise quality tables without threshold labels."""
    l2 = read_cells(run, cruises)
    jam = pd.read_parquet(JAM, columns=["cell_id", "median_depth_file_balanced"]).rename(
        columns={"median_depth_file_balanced": "jam_depth_m"}
    )
    strict = pd.read_parquet(STRICT, columns=["cell_id", "representative_depth_m"]).rename(
        columns={"representative_depth_m": "strict_depth_m"}
    )
    joined = l2.merge(jam, on="cell_id", how="left", validate="many_to_one")
    joined = joined.merge(strict, on="cell_id", how="left", validate="many_to_one")
    joined["jam_residual_m"] = joined["median_depth_m"] - joined["jam_depth_m"]
    joined["strict_residual_m"] = joined["median_depth_m"] - joined["strict_depth_m"]
    write_table(joined, run / "cruise_cell_reference_residuals")
    residual_rows = {}
    for cruise, group in joined.groupby("track_id"):
        residual_rows[cruise] = {}
        for prefix in ("jam", "strict"):
            values = group[f"{prefix}_residual_m"].dropna()
            residual_rows[cruise][f"{prefix}_n"] = len(values)
            residual_rows[cruise][f"{prefix}_median_m"] = float(values.median()) if len(values) else np.nan
            residual_rows[cruise][f"{prefix}_nmad_m"] = nmad(values)

    diagnosed = read_record_list(diagnosis_path)
    diagnosis_counts = {} if diagnosed is None else diagnosed.groupby(["filekey", "file_ordinal"]).size().to_dict()
    excluded = read_record_list(exclusion_path)
    aggregate = load_module("07_aggregate_file_cells_1min.py")

    file_rows = []
    cruise_rows = []
    for cruise in cruises:
        manifest = pd.read_parquet(l1_root / cruise / "extraction_manifest.parquet")
        checked = next((l1_root / cruise / "points_checked").glob("*.parquet"))
        file_cells = {}
        file_selected = {}
        cruise_excluded = None if excluded is None else excluded[excluded["filekey"].isin(manifest["filekey"])]
        pf = pq.ParquetFile(checked)
        for batch in pf.iter_batches(
            batch_size=500_000,
            columns=["filekey", "file_ordinal", "staging_row", "lon", "lat",
                     "depth_m_positive_down", "point_check_pass_basic", "native_quality_state"],
        ):
            frame = batch.to_pandas()
            mask = aggregate.point_selection_mask(frame, SELECTION_POLICY)
            mask &= ~aggregate.record_exclusion_mask(frame, cruise_excluded)
            selected = frame[mask].copy()
            if selected.empty:
                continue
            selected["cell_key"] = (
                np.floor((selected["lat"].to_numpy() + 90) * 60).astype(np.int64) * 21601
                + np.floor((selected["lon"].to_numpy() + 180) * 60).astype(np.int64)
            )
            for (filekey, ordinal), group in selected.groupby(["filekey", "file_ordinal"]):
                file_cells[(filekey, ordinal)] = file_cells.get((filekey, ordinal), set())
                file_cells[(filekey, ordinal)].update(group["cell_key"].unique())
                file_selected[(filekey, ordinal)] = file_selected.get((filekey, ordinal), 0) + len(group)
        rows = []
        for record in manifest.itertuples():
            n_rows = int(record.n_rows)
            counts = {
                "n_good": int(record.n_good or 0), "n_flagged": int(record.n_flagged or 0),
                "n_null": int(record.n_null or 0), "n_unknown": int(getattr(record, "n_unknown", 0) or 0),
                "n_pass_basic": int(getattr(record, "n_pass_basic", 0) or 0),
                "n_selected": file_selected.get((record.filekey, record.file_ordinal), 0),
            }
            before_exclusion = int(record.n_selected_basic_native_good)
            denom = n_rows if n_rows else np.nan
            has_flag = True if counts["n_flagged"] > 0 else None
            basis = (
                "observed native_quality_state=flagged"
                if counts["n_flagged"] > 0
                else "no flagged rows observed; good/null alone do not establish recorded editing information"
            )
            residual = residual_rows.get(cruise.lower(), {})
            rows.append({
                "cruise": cruise, "filekey": record.filekey, "file_ordinal": record.file_ordinal,
                "source_relpath": record.source_relpath, "mb_format": record.mb_format,
                "n_rows": n_rows, **counts,
                "n_selected_before_record_exclusion": before_exclusion,
                "n_excluded_selected_records": before_exclusion - counts["n_selected"],
                **{f"{key.removeprefix('n_')}_proportion": value / denom for key, value in counts.items()
                   if key.startswith("n_") and key not in {"n_rows", "n_pass_basic", "n_selected"}},
                "basic_pass_proportion": counts["n_pass_basic"] / denom,
                "selected_proportion": counts["n_selected"] / denom,
                "has_native_edit_flag": has_flag, "native_edit_flag_basis": basis,
                "n_cells_1min": len(file_cells.get((record.filekey, record.file_ordinal), set())),
                "jam_residual_scope": "cruise-cell rows; file point contributions not isolated",
                "strict_residual_scope": "cruise-cell rows; file point contributions not isolated",
                "r2_affected_record_count": (
                    diagnosis_counts.get((record.filekey, record.file_ordinal), 0) if diagnosed is not None else np.nan
                ),
                "r2_count_scope": "located record list only; zero is not a source-quality assessment",
                **residual,
            })
        file_df = pd.DataFrame(rows)
        file_rows.extend(rows)
        if file_df.empty:
            continue
        summary = {
            "cruise": cruise, "status": "processed", "n_files": len(file_df),
            "n_rows": int(file_df["n_rows"].sum()), "n_good": int(file_df["n_good"].sum()),
            "n_flagged": int(file_df["n_flagged"].sum()), "n_null": int(file_df["n_null"].sum()),
            "n_unknown": int(file_df["n_unknown"].sum()), "n_pass_basic": int(file_df["n_pass_basic"].sum()),
            "n_selected": int(file_df["n_selected"].sum()),
            "n_selected_before_record_exclusion": int(file_df["n_selected_before_record_exclusion"].sum()),
            "n_excluded_selected_records": int(file_df["n_excluded_selected_records"].sum()),
            "n_cells_1min": int(l2["track_id"].eq(cruise.lower()).sum()),
            "good_proportion": float(file_df["n_good"].sum() / file_df["n_rows"].sum()),
            "flagged_proportion": float(file_df["n_flagged"].sum() / file_df["n_rows"].sum()),
            "null_proportion": float(file_df["n_null"].sum() / file_df["n_rows"].sum()),
            "unknown_proportion": float(file_df["n_unknown"].sum() / file_df["n_rows"].sum()),
            "file_flagged_proportion_median": float(file_df["flagged_proportion"].median()),
            "file_flagged_proportion_p90": float(file_df["flagged_proportion"].quantile(.9)),
            "file_flagged_proportion_max": float(file_df["flagged_proportion"].max()),
            "n_files_without_flagged": int((file_df["n_flagged"] == 0).sum()),
            "n_files_with_observed_flagged": int(file_df["n_flagged"].gt(0).sum()),
            "n_files_edit_information_unestablished": int(file_df["has_native_edit_flag"].isna().sum()),
            "r2_affected_record_count": float(file_df["r2_affected_record_count"].sum(min_count=1)),
            "r2_count_scope": "located record list only; zero is not a source-quality assessment",
            "residual_scope": "all (cruise, cell) rows; combined estimate is not point-weighted",
        }
        l2_selected = int(l2.loc[l2["track_id"].eq(cruise.lower()), "n_points_pass"].sum())
        if summary["n_selected"] != l2_selected:
            raise AssertionError(f"{cruise}: file quality selection count differs from L2")
        for prefix in ("jam", "strict"):
            values = joined.loc[joined["track_id"].eq(cruise.lower()), f"{prefix}_residual_m"].dropna()
            summary[f"{prefix}_residual_n"] = len(values)
            summary[f"{prefix}_residual_median_m"] = float(values.median()) if len(values) else np.nan
            summary[f"{prefix}_residual_nmad_m"] = nmad(values)
        cruise_rows.append(summary)
    # Explicitly preserve the parser state for the unprocessed cruise.
    cruise_rows.append({
        "cruise": "NT06-21", "status": "unprocessed_by_current_parser",
        "reason": "UTC unavailable or invalid; no observation-coverage inference",
    })
    file_df = pd.DataFrame(file_rows)
    cruise_df = pd.DataFrame(cruise_rows)
    if baseline_diagnosis_path is not None:
        baseline = read_record_list(baseline_diagnosis_path)
        baseline_counts = baseline.groupby(["filekey", "file_ordinal"]).size()
        file_df["r2_union_affected_record_count"] = file_df["r2_affected_record_count"]
        file_df["r2_affected_record_count"] = [
            baseline_counts.get((row.filekey, row.file_ordinal), 0)
            for row in file_df.itertuples()
        ]
        cruise_df["r2_union_affected_record_count"] = cruise_df["r2_affected_record_count"]
        cruise_df["r2_affected_record_count"] = cruise_df["cruise"].map(
            file_df.groupby("cruise")["r2_affected_record_count"].sum()
        )
        for frame in (file_df, cruise_df):
            frame["r2_count_scope"] = f"v1 located list: {baseline_diagnosis_path}"
            frame["r2_union_count_scope"] = (
                f"v1 union v2: {diagnosis_path}; both G1 pair members included; "
                "sensitivity upper bound, not an adjudicated bad-sounding count"
            )
    write_table(file_df, run / "file_quality_summary")
    write_table(cruise_df, run / "cruise_quality_summary")
    return file_df, cruise_df


def candidate_table(
    candidates: pd.DataFrame, ncei: pd.DataFrame, jam: pd.DataFrame,
    strict: pd.DataFrame, region: str, affected_ids: set[str],
) -> pd.DataFrame:
    source_ids = {"ncei": set(ncei["cell_id"]), "jam": set(jam["cell_id"]), "strict": set(strict["cell_id"])}
    source_ids["union"] = set.union(*source_ids.values())
    overlap = ncei.merge(jam[["cell_id", "jam_depth_m"]], on="cell_id")
    rows = []
    for candidate in candidates.itertuples():
        grid = expected_cells(candidate.lon, candidate.lat)
        nearby_ids = set(grid["cell_id"])
        row = {
            "region": region, "candidate_id": candidate.candidate_id,
            "lon": candidate.lon, "lat": candidate.lat,
            "expected_core_cells": int(grid["core"].sum()),
            "expected_ring_cells": int(grid["ring"].sum()),
            "expected_ring_sector_cells": ";".join(map(str, np.bincount(grid.loc[grid["ring"], "sector"], minlength=8))),
        }
        for source, ids in source_ids.items():
            row.update({f"{source}_{key}": value for key, value in coverage_metric(ids, grid).items()})
        window = overlap[overlap["cell_id"].isin(nearby_ids)]
        differences = window["ncei_median_depth_m"] - window["jam_depth_m"]
        cwin = ncei[ncei["cell_id"].isin(nearby_ids)]
        source_cruises = set(";".join(cwin["ncei_source_cruises"]).split(";")) - {""}
        condition = (
            row["union_core_coverage"] >= .6
            and row["union_ring_coverage"] >= .5
            and row["union_min_sector_coverage"] >= .25
        )
        affected = sorted(nearby_ids & affected_ids)
        row.update({
            "overlap_cells": len(window), "overlap_diff_median_m": differences.median(),
            "overlap_abs_diff_p95_m": differences.abs().quantile(.95),
            "overlap_abs_gt_100m_cells": int(differences.abs().gt(100).sum()),
            "ncei_source_cruises": ";".join(sorted(source_cruises)),
            "coverage_condition_met": condition,
            "coverage_condition": "inherited: core>=0.6 & ring>=0.5 & min_sector>=0.25",
            "hnro14rr_located_cells": ";".join(affected),
            "hnro14rr_located_cell_count": len(affected),
            "measurement_action": (
                "source_record_review" if condition and affected
                else "begin_source_separated_depth_measurement" if condition
                else "coverage_limited"
            ),
            "morphology_status": "not_assessed_in_this_run",
        })
        rows.append(row)
    result = pd.DataFrame(rows)
    fractions = [c for c in result if c.endswith("_coverage") and "sector_coverage" not in c]
    fractions += [c for c in result if c.endswith("_min_sector_coverage")]
    if not result[fractions].ge(0).all().all() or not result[fractions].le(1).all().all():
        raise AssertionError("candidate coverage outside [0, 1]")
    return result


def coverage_comparison(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    columns = ["candidate_id", "expected_core_cells", "expected_ring_cells"]
    columns += [c for c in new if c.endswith(("_coverage", "_cells")) and c in old and c not in columns]
    comparison = old[columns].merge(new[columns], on="candidate_id", suffixes=("_old", "_new"), validate="one_to_one")
    for column in columns[1:]:
        if pd.api.types.is_numeric_dtype(new[column]):
            comparison[f"{column}_change"] = comparison[f"{column}_new"] - comparison[f"{column}_old"]
    return comparison


def region_coverage(cells: pd.DataFrame, strict_ids: set[str], bounds: tuple | None) -> dict:
    sub = box(cells, bounds) if bounds is not None else cells
    ids = set(sub["cell_id"])
    return {
        "n_occupied_cells": len(ids), "n_in_strict": len(ids & strict_ids),
        "n_new_outside_strict": len(ids - strict_ids),
        "n_source_rows": len(sub), "n_cruises": sub["track_id"].nunique(),
    }


def point_cells(points: pd.DataFrame, *, jamstec: bool = False) -> pd.Series:
    scale = 1 / 60
    if jamstec:
        xb = np.floor((points["lon"] + 180) / scale).astype(np.int64)
        yb = np.floor((points["lat"] + 90) / scale).astype(np.int64)
    else:
        xb = np.floor((points["lon"] + 180) * 60).astype(np.int64)
        yb = np.floor((points["lat"] + 90) * 60).astype(np.int64)
    return "1min_" + yb.astype(str) + "_" + xb.astype(str)


def cell_point_filters(cell_ids: list[str]) -> list[list[tuple]]:
    filters = []
    for cell in cell_ids:
        _, y, x = cell.split("_")
        west, south = int(x) / 60 - 180, int(y) / 60 - 90
        filters.append([
            ("lon", ">=", west - 1e-10), ("lon", "<=", west + 1 / 60 + 1e-10),
            ("lat", ">=", south - 1e-10), ("lat", "<=", south + 1 / 60 + 1e-10),
        ])
    return filters


def position_summary(points: pd.DataFrame, source: str, cruise: str, cell: str, filekey: str) -> dict:
    _, y, x = cell.split("_")
    center_lon, center_lat = (int(x) + .5) / 60 - 180, (int(y) + .5) / 60 - 90
    east = (points["lon"].to_numpy() - center_lon) * 111320 * math.cos(math.radians(center_lat))
    north = (points["lat"].to_numpy() - center_lat) * 111320
    coordinates = np.column_stack([east, north])
    if len(points) > 1:
        eigenvalues, eigenvectors = np.linalg.eigh(np.cov(coordinates, rowvar=False))
        direction = eigenvectors[:, -1]
        axis_angle = float(np.degrees(np.arctan2(direction[1], direction[0])) % 180)
        major, minor = np.sqrt(np.maximum(eigenvalues, 0))[::-1]
    else:
        axis_angle = major = minor = np.nan
    return {
        "source": source, "cruise": cruise, "cell_id": cell, "filekey": filekey,
        "n_points": len(points), "east_mean_m": float(east.mean()), "north_mean_m": float(north.mean()),
        "east_min_m": float(east.min()), "east_max_m": float(east.max()),
        "north_min_m": float(north.min()), "north_max_m": float(north.max()),
        "position_major_std_m": float(major), "position_minor_std_m": float(minor),
        "position_axis_deg_from_east": axis_angle,
        "sample_median_depth_m": float(points["depth_m_positive_down"].median()),
        "sample_min_depth_m": float(points["depth_m_positive_down"].min()),
        "sample_max_depth_m": float(points["depth_m_positive_down"].max()),
    }


def inspect_izu_sampling(run: Path, l1_root: Path, exclusion_path: Path | None) -> None:
    """Inspect positions for the ten largest Izu cruise-cell differences."""
    focus = pd.read_parquet(run / "izu_bonin_largest_cruise_residual_cells.parquet")
    target_ids = set(focus["cell_id"])
    aggregate = load_module("07_aggregate_file_cells_1min.py")
    exclusions = read_record_list(exclusion_path)
    summaries, all_points = [], []
    for cruise, targets in focus.groupby("track_id"):
        checked = next((l1_root / cruise.upper() / "points_checked").glob("*.parquet"))
        points = pd.read_parquet(
            checked, filters=cell_point_filters(targets["cell_id"].tolist()),
            columns=["lon", "lat", "depth_m_positive_down", "point_check_pass_basic",
                     "native_quality_state", "filekey", "file_ordinal", "staging_row", "time"],
        )
        mask = aggregate.point_selection_mask(points, SELECTION_POLICY)
        mask &= ~aggregate.record_exclusion_mask(points, exclusions)
        points = points[mask].copy()
        points["cell_id"] = point_cells(points)
        points = points[points["cell_id"].isin(targets["cell_id"])]
        for (cell, filekey), sub in points.groupby(["cell_id", "filekey"]):
            summary = position_summary(sub, "ncei", cruise, cell, filekey)
            summary.update({"time_min": str(sub["time"].min()), "time_max": str(sub["time"].max())})
            summaries.append(summary)
        for cell, sub in points.groupby("cell_id"):
            summaries.append(position_summary(sub, "ncei", cruise, cell, "all_files"))
        all_points.append(points.assign(source="ncei", cruise=cruise))
    jam_root = ROOT / "jamstec/multibeam"
    manifest = pd.read_parquet(jam_root / "manifests/file_manifest_points_raw.parquet")
    quality = pd.read_parquet(jam_root / "manifests/file_quality_flags_1min.parquet")
    excluded_files = set(quality.loc[quality["exclude_from_primary_cells"], "file_id"])
    bounding = np.zeros(len(manifest), dtype=bool)
    for cell in target_ids:
        _, y, x = cell.split("_")
        west, south = int(x) / 60 - 180, int(y) / 60 - 90
        bounding |= (
            manifest["lon_max"].ge(west) & manifest["lon_min"].le(west + 1 / 60)
            & manifest["lat_max"].ge(south) & manifest["lat_min"].le(south + 1 / 60)
        ).to_numpy()
    manifest = manifest[bounding & manifest["include_in_points_raw"] & ~manifest["file_id"].isin(excluded_files)]
    qc_manifest = pd.read_parquet(jam_root / "manifests/points_qc_manifest.parquet").set_index("file_id")
    file_cells_manifest = pd.read_parquet(jam_root / "manifests/file_cells_manifest_1min.parquet").set_index("file_id")
    jam_points = []
    for record in manifest.itertuples():
        if record.file_id not in file_cells_manifest.index:
            continue
        membership = pd.read_parquet(
            jam_root / file_cells_manifest.loc[record.file_id, "output_path"],
            filters=[("cell_id", "in", sorted(target_ids))], columns=["cell_id", "n_points"],
        )
        if membership.empty:
            continue
        points = pd.read_parquet(
            jam_root / qc_manifest.loc[record.file_id, "output_path"],
            filters=cell_point_filters(membership["cell_id"].tolist()),
            columns=["lon", "lat", "depth_m_positive_down", "qc_pass_basic", "date_raw", "time_raw"],
        )
        points = points[points["qc_pass_basic"]].copy()
        points["cell_id"] = point_cells(points, jamstec=True)
        points = points[points["cell_id"].isin(target_ids)]
        expected_counts = membership.set_index("cell_id")["n_points"].sort_index()
        observed_counts = points.groupby("cell_id").size().reindex(expected_counts.index).fillna(0).astype(int)
        if not np.array_equal(expected_counts.to_numpy(), observed_counts.to_numpy()):
            raise ValueError(f"JAMSTEC selected point counts differ from file-cells: {record.file_id}")
        for cell, sub in points.groupby("cell_id"):
            summaries.append(position_summary(sub, "jam", record.cruise_id_guess, cell, record.file_id))
        jam_points.append(points.assign(filekey=record.file_id, source="jam", cruise=record.cruise_id_guess))
    jam_points = pd.concat(jam_points, ignore_index=True)
    for cell, sub in jam_points.groupby("cell_id"):
        summaries.append(position_summary(sub, "jam", "all_cruises", cell, "all_files"))
    all_points.append(jam_points)
    samples = pd.concat(all_points, ignore_index=True)
    samples.to_parquet(run / "izu_bonin_focus_point_positions.parquet", index=False)
    write_table(pd.DataFrame(summaries), run / "izu_bonin_focus_sampling")
    ncei_positions = pd.DataFrame(summaries).query("source == 'ncei' and filekey == 'all_files'")
    jam_positions = pd.DataFrame(summaries).query("source == 'jam' and filekey == 'all_files'")
    separation = ncei_positions.merge(jam_positions, on="cell_id", suffixes=("_ncei", "_jam"))
    separation["centroid_separation_m"] = np.hypot(
        separation["east_mean_m_ncei"] - separation["east_mean_m_jam"],
        separation["north_mean_m_ncei"] - separation["north_mean_m_jam"],
    )
    write_table(separation, run / "izu_bonin_focus_sampling_comparison")


def analyze(run: Path, cruises: list[str], diagnosis_path: Path | None) -> dict:
    cells = read_cells(run, cruises)
    old_cells = read_cells(OLD_L2, cruises)
    combined, old_combined = combined_cells(cells), combined_cells(old_cells)
    write_table(combined, run / "combined_ncei_cells")
    comparison = old_cells.merge(cells, on=["track_id", "cell_id"], how="outer", suffixes=("_old", "_new"), indicator=True)
    comparison["median_depth_change_m"] = comparison["median_depth_m_new"] - comparison["median_depth_m_old"]
    write_table(comparison, run / "cruise_cell_quality_comparison")
    strict_ids = set(pd.read_parquet(STRICT, columns=["cell_id"])["cell_id"])
    coverage_rows = []
    for version, table in (("old_basic", old_cells), ("native_good", cells)):
        for region, bounds in [("global", None), *REGIONS.items()]:
            coverage_rows.append({"version": version, "region": region, **region_coverage(table, strict_ids, bounds)})
    write_table(pd.DataFrame(coverage_rows), run / "coverage_stats_regions")
    # Without a diagnosis list, retain the original three reported cells.
    affected_ids = {"1min_7701_18851", "1min_7702_18852", "1min_7702_18851"}
    diagnosed = read_record_list(diagnosis_path)
    if diagnosed is not None:
        selected = diagnosed["point_check_pass_basic"] & diagnosed["native_quality_state"].eq("good")
        affected_ids = set(diagnosed.loc[selected, "cell_id"])
    result = {"regions": {}}
    for region, bounds in REGIONS.items():
        candidates = pd.read_csv(CANDIDATES / f"20261019-vgg-pick-vs-ship-{region.replace('_', '-')}" / "candidates.csv")
        jam, strict = read_references(candidates, bounds)
        provenance = box(strict, bounds).groupby(
            ["strict_provider", "strict_dataset", "strict_source"], dropna=False
        ).size().reset_index(name="n_cells")
        write_table(provenance, run / f"{region}_strict_provenance")
        new_residual = residuals(box(combined, bounds), jam, strict, "ncei_median_depth_m")
        old_residual = residuals(box(old_combined, bounds), jam, strict, "ncei_median_depth_m")
        cruise_residual = residuals(box(cells, bounds), jam, strict, "median_depth_m")
        old_cruise_residual = residuals(box(old_cells, bounds), jam, strict, "median_depth_m")
        write_table(new_residual, run / f"{region}_cell_residuals")
        write_table(cruise_residual, run / f"{region}_cruise_cell_residuals")
        write_table(old_cruise_residual, run / f"{region}_old_cruise_cell_residuals")
        write_table(pd.concat([
            residual_summary(old_residual, region).assign(version="old_basic"),
            residual_summary(new_residual, region).assign(version="native_good"),
        ], ignore_index=True), run / f"{region}_residual_summary")
        write_table(pd.concat([
            residual_summary(old_cruise_residual, region, ["track_id"]).assign(version="old_basic"),
            residual_summary(cruise_residual, region, ["track_id"]).assign(version="native_good"),
        ], ignore_index=True), run / f"{region}_residual_by_cruise")
        write_table(residual_summary(new_residual, region, ["ncei_source_cruises"]), run / f"{region}_residual_by_source_combination")
        current = candidate_table(candidates, combined, jam, strict, region, affected_ids)
        old_fixed_geometry = candidate_table(candidates, old_combined, jam, strict, region, affected_ids)
        write_table(current, run / f"{region}_candidate_coverage")
        write_table(old_fixed_geometry, run / f"{region}_old_quality_corrected_geometry")
        write_table(coverage_comparison(old_fixed_geometry, current), run / f"{region}_candidate_quality_comparison")
        historical = pd.read_parquet(OLD_AUDIT / f"{region}_candidate_source_audit_corrected.parquet")
        write_table(coverage_comparison(historical, current), run / f"{region}_candidate_historical_comparison")
        spatial_focus = cruise_residual.nlargest(10, "ncei_jam_abs_diff_m")
        write_table(spatial_focus, run / f"{region}_largest_cruise_residual_cells")
        result["regions"][region] = {
            "n_candidates": len(current),
            "coverage_condition_met": int(current["coverage_condition_met"].sum()),
            "begin_depth_measurement_ids": current.loc[
                current["measurement_action"].eq("begin_source_separated_depth_measurement"), "candidate_id"
            ].tolist(),
            "source_record_review_ids": current.loc[current["measurement_action"].eq("source_record_review"), "candidate_id"].tolist(),
            "coverage_limited_ids": current.loc[current["measurement_action"].eq("coverage_limited"), "candidate_id"].tolist(),
            "hnro14rr_located_candidate_ids": current.loc[current["hnro14rr_located_cell_count"].gt(0), "candidate_id"].tolist(),
            "combined_overlap_cells": len(new_residual), "cruise_overlap_rows": len(cruise_residual),
        }
    return result


def compare_record_exclusion(run: Path, retained_run: Path, exclusion_path: Path) -> None:
    """Compare located records without treating absent cells as zero residuals."""
    records = read_record_list(exclusion_path)
    selected = records["point_check_pass_basic"] & records["native_quality_state"].eq("good")
    affected = records.loc[selected].groupby("cell_id").size().rename("n_located_selected_records").reset_index()
    for label, version_run in (("retained", retained_run), ("excluded", run)):
        cells = pd.read_parquet(version_run / "cruise_cell_reference_residuals.parquet")
        hnro = cells[cells["track_id"].eq("hnro14rr")].drop(columns="track_id")
        affected = affected.merge(
            hnro.add_suffix(f"_{label}").rename(columns={f"cell_id_{label}": "cell_id"}),
            on="cell_id", how="left", validate="one_to_one",
        )
        combined = pd.read_parquet(version_run / "combined_ncei_cells.parquet")
        affected = affected.merge(
            combined[["cell_id", "ncei_median_depth_m", "ncei_n_points", "ncei_source_cruises"]].rename(
                columns={c: f"combined_{c}_{label}" for c in combined if c != "cell_id"}
            ),
            on="cell_id", how="left", validate="one_to_one",
        )
        for reference in ("jam", "strict"):
            reference_depth = affected[f"{reference}_depth_m_{label}"]
            if label == "excluded":
                reference_depth = reference_depth.combine_first(affected[f"{reference}_depth_m_retained"])
            affected[f"combined_{reference}_residual_m_{label}"] = (
                affected[f"combined_ncei_median_depth_m_{label}"] - reference_depth
            )
    affected["hnro_cell_retained_after_exclusion"] = affected["n_points_pass_excluded"].notna()
    for column in ("median_depth_m", "jam_residual_m", "strict_residual_m",
                   "combined_jam_residual_m", "combined_strict_residual_m"):
        affected[f"{column}_change"] = affected[f"{column}_excluded"] - affected[f"{column}_retained"]
    initial_ids = {"1min_7701_18851", "1min_7702_18852", "1min_7702_18851"}
    affected["initial_three_cells"] = affected["cell_id"].isin(initial_ids)
    write_table(affected, run / "hnro14rr_located_cell_comparison")
    summaries = []
    for label in ("retained", "excluded"):
        for source in ("", "combined_"):
            for reference in ("jam", "strict"):
                values = affected[f"{source}{reference}_residual_m_{label}"].dropna()
                summaries.append({
                    "version": label, "source": source or "hnro14rr", "reference": reference,
                    "n_overlap": len(values), "median_m": values.median(), "nmad_m": nmad(values),
                    "abs_p95_m": values.abs().quantile(.95), "abs_max_m": values.abs().max(),
                })
    write_table(pd.DataFrame(summaries), run / "hnro14rr_located_residual_summary")
    for region in REGIONS:
        retained = pd.read_parquet(retained_run / f"{region}_candidate_coverage.parquet")
        excluded = pd.read_parquet(run / f"{region}_candidate_coverage.parquet")
        comparison = coverage_comparison(retained, excluded)
        comparison = comparison.merge(excluded[[
            "candidate_id", "hnro14rr_located_cell_count", "hnro14rr_located_cells",
        ]], on="candidate_id", validate="one_to_one")
        comparison = comparison.merge(retained[[
            "candidate_id", "coverage_condition_met", "measurement_action",
        ]], on="candidate_id", validate="one_to_one")
        comparison = comparison.merge(excluded[[
            "candidate_id", "coverage_condition_met", "measurement_action",
        ]], on="candidate_id", suffixes=("_retained", "_excluded"), validate="one_to_one")
        write_table(comparison, run / f"{region}_record_exclusion_candidate_comparison")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=RUN_ROOT)
    parser.add_argument("--reuse-l1", type=Path, help="Reuse L1 from a previous quality-revision run.")
    parser.add_argument("--exclude-records", type=Path, help="Diagnosis parquet with point keys, cell_id, point_check_pass_basic, native_quality_state.")
    parser.add_argument("--diagnosis-records", type=Path, help="Located records for descriptive counts and candidate annotations; does not exclude points.")
    parser.add_argument("--baseline-diagnosis-records", type=Path, help="Keep v1 quality-table counts and add the active v1-union-v2 diagnosis counts separately.")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run = args.output_dir.resolve()
    if not run.is_relative_to(RUN_ROOT) or run == PROD:
        raise ValueError(f"output must be within {RUN_ROOT}")
    if not 1 <= args.workers <= max(1, (os.cpu_count() or 1) // 2):
        raise ValueError("workers must not exceed half the available CPU count")
    l1_root = args.reuse_l1.resolve() if args.reuse_l1 else run
    if not l1_root.is_relative_to(RUN_ROOT):
        raise ValueError("reused L1 must be from the isolated quality-revision directory")
    exclusion_path = args.exclude_records.resolve() if args.exclude_records else None
    diagnosis_path = args.diagnosis_records.resolve() if args.diagnosis_records else exclusion_path
    baseline_diagnosis_path = args.baseline_diagnosis_records.resolve() if args.baseline_diagnosis_records else None
    parameters = {
        "entry": str(Path(__file__).relative_to(ROOT)), "cruises": CRUISES,
        "staging_root": str(PROD), "l1_root": str(l1_root),
        "exclude_records": str(exclusion_path) if exclusion_path else None,
        "diagnosis_records": str(diagnosis_path) if diagnosis_path else None,
        "baseline_diagnosis_records": str(baseline_diagnosis_path) if baseline_diagnosis_path else None,
        "selection_policy": SELECTION_POLICY, "source_path_root": "ncei",
        "source_relpath_root": "ncei/raw_round2/platforms_tree",
        "combined_depth_estimator": "median of cruise-cell medians; unweighted across cruises",
        "distance_metric": "local equirectangular; 111.32 km per degree; cos(candidate latitude)",
        "coverage_geometry": {"core_km": 4, "annulus_km": [8, 12.5], "sectors": 8},
        "regions": REGIONS, "workers": args.workers,
        "jamstec": str(JAM), "strict": str(STRICT),
        "environment": {
            "python": sys.version, "executable": sys.executable,
            "numpy": np.__version__, "pandas": pd.__version__, "pyarrow": pa.__version__,
        },
        "command": [sys.executable, *sys.argv],
    }
    parameter_path = run / "run_parameters.json"
    if run.exists() and any(run.iterdir()):
        if not args.resume or not parameter_path.exists():
            raise FileExistsError(f"nonempty output; use --resume for this entry's existing run: {run}")
        previous = json.loads(parameter_path.read_text())
        for key in ("cruises", "l1_root", "exclude_records", "selection_policy"):
            if previous[key] != parameters[key]:
                raise ValueError(f"resume input changed: {key}")
    run.mkdir(parents=True, exist_ok=True)
    write_json(parameters, parameter_path)
    for path in {exclusion_path, diagnosis_path, baseline_diagnosis_path} - {None}:
        records = read_record_list(path)
        evidence_columns = {"cell_id", "point_check_pass_basic", "native_quality_state"}
        if not evidence_columns.issubset(records.columns):
            raise ValueError(f"{path}: diagnosis comparison requires {sorted(evidence_columns)}")
        all_keys = set()
        for cruise in CRUISES:
            all_keys.update(pd.read_parquet(PROD / cruise / "extraction_manifest.parquet")["filekey"])
        if not set(records["filekey"]).issubset(all_keys):
            raise ValueError("record list contains records outside this batch")
    tasks = [(cruise, run, l1_root, exclusion_path, args.resume) for cruise in CRUISES]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(rebuild_cruise, tasks))
    status = pd.DataFrame(rows)
    old = pd.read_csv(OLD_L2 / "run_status.tsv", sep="\t")
    old = old.rename(columns={
        "l1_basic_pass_rows": "old_reported_l1_basic_pass_rows",
        "l2_cells": "old_l2_cells", "l2_points_pass": "old_l2_points_pass",
    })
    status = status.merge(old[[
        "cruise", "old_reported_l1_basic_pass_rows", "old_l2_cells", "old_l2_points_pass",
    ]], on="cruise", validate="one_to_one")
    write_table(status, run / "run_status")
    write_table(status[[
        "cruise", "track_id", "branch", "source_type", "instrument_class_pred",
        "input_path", "output_path", "n_cells", "n_points_pass_total",
        "n_unique_triples_total", "duplicate_ratio_overall", "manual_review_flag",
        "runtime_seconds", "aggregation_version", "selection_policy",
        "n_input_rows", "n_pass_basic", "n_selected", "n_excluded_selected_records",
    ]], run / "l2_file_cells_manifest")
    write_table(pd.DataFrame([{
        "cruise": "NT06-21", "status": "unprocessed_by_current_parser",
        "reason": "UTC unavailable or invalid; no observation-coverage inference",
    }]), run / "unprocessed_cruises")
    write_table(source_manifest(rows), run / "source_manifest_fragment")
    quality_tables(run, CRUISES, l1_root, exclusion_path, diagnosis_path, baseline_diagnosis_path)
    outcome = analyze(run, CRUISES, diagnosis_path)
    inspect_izu_sampling(run, l1_root, exclusion_path)
    if exclusion_path is not None and l1_root != run:
        compare_record_exclusion(run, l1_root, exclusion_path)
    outcome["n_rows"] = int(status["n_rows"].sum())
    outcome["n_pass_basic"] = int(status["n_pass_basic"].sum())
    outcome["n_selected"] = int(status["n_selected"].sum())
    outcome["n_cruise_cells"] = int(status["n_cells"].sum())
    outcome["n_excluded_selected_records"] = int(status["n_excluded_selected_records"].sum())
    outcome["status"] = "completed"
    write_json(outcome, run / "run_summary.json")
    print(json.dumps(outcome, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
