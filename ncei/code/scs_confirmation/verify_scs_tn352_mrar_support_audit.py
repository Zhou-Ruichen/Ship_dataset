#!/usr/bin/env python3
"""Independently verify the frozen TN352-MRAR support audit."""

from __future__ import annotations

import argparse
import collections
import csv
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.dataset as ds
import pyarrow.parquet as pq
from scipy.spatial import cKDTree

from ncei.code.scs_confirmation.scs_tn352_audit_common import (
    canonical_sha256,
    read_json,
    require,
    sha256_file,
    write_json,
)
from ncei.code.scs_confirmation.scs_tn352_support import (
    EARTH_RADIUS_M,
    TIE_TOLERANCE_M,
    SupportPoints,
    cell_offsets,
    load_mrar_points,
    load_tn352_points,
    take_points,
)


OUTPUT_ROLE = "development_only_not_confirmation"


def cell_sort_key(cell_id: str) -> tuple[int, int]:
    prefix, lat_bin, lon_bin = cell_id.split("_")
    require(prefix == "1min", f"invalid cell ID prefix: {cell_id}")
    return int(lat_bin), int(lon_bin)


def verify_cell_id_gate(lock: dict[str, Any], phase_b: Path) -> None:
    frozen_path = Path(lock["inputs"]["frozen_scalar_pair_assignments"]["path"])
    frozen_rows = pq.read_table(frozen_path, columns=["cell_id"]).column("cell_id").to_pylist()
    frozen = {str(value) for value in frozen_rows}
    require(len(frozen_rows) == len(frozen) == 2_244, "independent frozen assignment count differs")

    stage_path = Path(lock["inputs"]["stage_c_candidate_labels"]["path"])
    stage_rows = pq.read_table(
        stage_path,
        columns=["cell_id", "lon_center", "lat_center", "aggregation_basis"],
        filters=[("official_cruise_id", "=", "TN352")],
    ).to_pylist()
    tn352 = {
        str(row["cell_id"])
        for row in stage_rows
        if 105.0 <= float(row["lon_center"]) < 125.0
        and 0.0 <= float(row["lat_center"]) < 25.0
        and row["aggregation_basis"] == "individual_qc_eligible_beams_exact"
    }
    require(len(tn352) == 2_368, "independent TN352 candidate count differs")

    mrar_path = Path(lock["inputs"]["mrar_checked_points"]["path"])
    mrar_dataset = ds.dataset(mrar_path, format="parquet")
    mrar_filter = (
        ds.field("point_check_pass_basic")
        & (ds.field("lon") >= 105.0)
        & (ds.field("lon") < 125.0)
        & (ds.field("lat") >= 0.0)
        & (ds.field("lat") < 25.0)
    )
    coordinate_table = mrar_dataset.to_table(columns=["lon", "lat"], filter=mrar_filter)
    lon = coordinate_table.column("lon").to_numpy(zero_copy_only=False)
    lat = coordinate_table.column("lat").to_numpy(zero_copy_only=False)
    require(np.all(np.isfinite(lon) & np.isfinite(lat)), "independent MRAR coordinates are non-finite")
    lon_bin = np.floor((lon + 180.0) * 60.0).astype(np.int64)
    lat_bin = np.floor((lat + 90.0) * 60.0).astype(np.int64)
    mrar = {f"1min_{lat_value}_{lon_value}" for lon_value, lat_value in zip(lon_bin, lat_bin)}
    raw_common = tn352 & mrar

    expected_sets = {
        "frozen_scalar_pair": sorted(frozen, key=cell_sort_key),
        "frozen_missing_tn352": sorted(frozen - tn352, key=cell_sort_key),
        "frozen_missing_raw_support": sorted(frozen - raw_common, key=cell_sort_key),
        "raw_support_common": sorted(raw_common, key=cell_sort_key),
        "raw_support_only_not_in_frozen_scalar_pair": sorted(raw_common - frozen, key=cell_sort_key),
        "tn352_without_mrar_raw_support": sorted(tn352 - mrar, key=cell_sort_key),
    }
    observed = read_json(phase_b / "cell_id_comparison.json")
    require(observed["cell_ids"] == expected_sets, "independent cell-ID set comparison differs")
    require(observed["counts"] == {name: len(values) for name, values in expected_sets.items()}, "cell-ID counts differ")
    require(not expected_sets["frozen_missing_tn352"] and not expected_sets["frozen_missing_raw_support"], "frozen cohort is not fully supported")
    require(len(raw_common) == 2_367 and len(raw_common - frozen) == 123, "raw-support set counts differ")
    require(expected_sets["tn352_without_mrar_raw_support"] == ["1min_6739_18005"], "TN352 no-support cell differs")

    statuses = pq.read_table(phase_b / "phase_b_cell_id_status.parquet").to_pylist()
    require(len(statuses) == 2_368 and len({row["cell_id"] for row in statuses}) == 2_368, "cell-ID status rows differ")
    expected_status = {}
    for cell_id in tn352:
        if cell_id in frozen:
            expected_status[cell_id] = "frozen_scalar_pair"
        elif cell_id in raw_common:
            expected_status[cell_id] = "raw_support_only_not_in_frozen_scalar_pair"
        else:
            expected_status[cell_id] = "tn352_without_mrar_raw_support"
    require(
        {str(row["cell_id"]): str(row["analysis_status"]) for row in statuses} == expected_status,
        "cell-ID analysis statuses differ",
    )
    for row in statuses:
        cell_id = str(row["cell_id"])
        require(bool(row["in_frozen_scalar_pair"]) == (cell_id in frozen), f"frozen status differs: {cell_id}")
        require(bool(row["in_tn352_candidate"]) == (cell_id in tn352), f"TN352 status differs: {cell_id}")
        require(bool(row["in_mrar_raw_support"]) == (cell_id in raw_common), f"MRAR status differs: {cell_id}")
        require(bool(row["included_in_phase_b"]) == (cell_id in frozen), f"Phase B inclusion differs: {cell_id}")


def close(left: Any, right: Any, message: str, *, atol: float = 1.0e-8, rtol: float = 1.0e-12) -> None:
    if left is None or right is None:
        require(left is None and right is None, message)
        return
    require(math.isclose(float(left), float(right), abs_tol=atol, rel_tol=rtol), f"{message}: {left} != {right}")


def vectors(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    lon_rad = np.radians(lon.astype(np.float64, copy=False))
    lat_rad = np.radians(lat.astype(np.float64, copy=False))
    return np.column_stack(
        (
            np.cos(lat_rad) * np.cos(lon_rad),
            np.cos(lat_rad) * np.sin(lon_rad),
            np.sin(lat_rad),
        )
    )


def arc_distance(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    dot = np.sum(left * right, axis=-1)
    cross = np.linalg.norm(np.cross(left, right), axis=-1)
    return EARTH_RADIUS_M * np.arctan2(cross, np.clip(dot, -1.0, 1.0))


def centroid(lon: np.ndarray, lat: np.ndarray) -> tuple[float, float]:
    mean = vectors(lon, lat).sum(axis=0)
    mean /= np.linalg.norm(mean)
    return math.degrees(math.atan2(float(mean[1]), float(mean[0]))), math.degrees(math.atan2(float(mean[2]), math.hypot(float(mean[0]), float(mean[1]))))


def nearest_with_ties(query: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tree = cKDTree(target)
    if target.shape[0] == 1:
        selected = np.zeros(query.shape[0], dtype=np.int64)
        return selected, arc_distance(query, target[selected])
    chord, indices = tree.query(query, k=2, workers=1)
    selected = indices[:, 0].astype(np.int64)
    first = arc_distance(query, target[selected])
    second = arc_distance(query, target[indices[:, 1]])
    for query_index in np.flatnonzero(second - first <= TIE_TOLERANCE_M):
        radius = 2.0 * math.sin((float(first[query_index]) + TIE_TOLERANCE_M) / (2.0 * EARTH_RADIUS_M)) + 1.0e-15
        candidates = np.asarray(tree.query_ball_point(query[query_index], radius), dtype=np.int64)
        distances = arc_distance(np.repeat(query[query_index][None, :], candidates.size, axis=0), target[candidates])
        minimum = float(distances.min())
        selected[query_index] = int(candidates[distances <= minimum + TIE_TOLERANCE_M].min())
        first[query_index] = minimum
    return selected, first


def independent_pairs(tn: SupportPoints, mrar: SupportPoints) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    tn_order = np.lexsort((tn.second_index, tn.first_index, tn.group_code))
    mrar_order = np.lexsort((mrar.first_index, mrar.group_code))
    tn_xyz = vectors(tn.lon[tn_order], tn.lat[tn_order])
    mrar_xyz = vectors(mrar.lon[mrar_order], mrar.lat[mrar_order])
    forward, distance = nearest_with_ties(tn_xyz, mrar_xyz)
    reverse, _ = nearest_with_ties(mrar_xyz, tn_xyz)
    source = np.arange(tn_xyz.shape[0], dtype=np.int64)
    mask = reverse[forward] == source
    return tn_order[source[mask]], mrar_order[forward[mask]], distance[mask], float(distance.min())


def independent_occupancy(lon: np.ndarray, lat: np.ndarray, center_lon: float, center_lat: float) -> set[tuple[int, int]]:
    x = EARTH_RADIUS_M * math.cos(math.radians(center_lat)) * (np.radians(lon) - math.radians(center_lon))
    y = EARTH_RADIUS_M * (np.radians(lat) - math.radians(center_lat))
    return set(zip(np.floor(x / 100.0).astype(np.int64).tolist(), np.floor(y / 100.0).astype(np.int64).tolist()))


def metrics(delta: np.ndarray) -> dict[str, Any]:
    if delta.size == 0:
        return {"count": 0, "bias": None, "mae": None, "rmse": None, "p50_abs": None, "p95_abs": None, "min_signed": None, "max_signed": None, "median_signed": None}
    absolute = np.abs(delta)
    return {
        "count": int(delta.size),
        "bias": float(delta.sum() / delta.size),
        "mae": float(absolute.sum() / delta.size),
        "rmse": float(math.sqrt(float(np.dot(delta, delta)) / delta.size)),
        "p50_abs": float(np.percentile(absolute, 50, method="linear")),
        "p95_abs": float(np.percentile(absolute, 95, method="linear")),
        "min_signed": float(delta.min()),
        "max_signed": float(delta.max()),
        "median_signed": float(np.percentile(delta, 50, method="linear")),
    }


def point_slice(points: SupportPoints, offsets: np.ndarray, index: int) -> SupportPoints:
    return take_points(points, np.arange(int(offsets[index]), int(offsets[index + 1]), dtype=np.int64))


def pair_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(row["cell_id"]),
        str(row["tn352_source_object_id"]),
        int(row["tn352_parser_ping_index"]),
        int(row["tn352_beam_index"]),
        str(row["mrar_track_id"]),
        int(row["mrar_point_index_in_track"]),
    )


def expected_pair_key(cell_id: str, tn: SupportPoints, mrar: SupportPoints, tn_index: int, mrar_index: int) -> tuple[Any, ...]:
    return (
        cell_id,
        tn.group_values[int(tn.group_code[tn_index])],
        int(tn.first_index[tn_index]),
        int(tn.second_index[tn_index]),
        mrar.group_values[int(mrar.group_code[mrar_index])],
        int(mrar.first_index[mrar_index]),
    )


def read_pairs(phase_b: Path) -> tuple[dict[int, dict[str, list[dict[str, Any]]]], dict[int, set[tuple[Any, ...]]]]:
    grouped: dict[int, dict[str, list[dict[str, Any]]]] = {}
    keys: dict[int, set[tuple[Any, ...]]] = {}
    for threshold in (100, 250, 500):
        rows = pq.read_table(phase_b / f"matched_difference_{threshold}m.parquet").to_pylist()
        threshold_keys = [pair_key(row) for row in rows]
        require(len(threshold_keys) == len(set(threshold_keys)), f"{threshold} m pair keys are not unique")
        require(all(row["mutual_nearest"] is True and float(row["distance_m"]) <= threshold for row in rows), f"{threshold} m pair flag/distance differs")
        for row in rows:
            close(float(row["tn352_depth_m_positive_down"]) - float(row["mrar_depth_m_positive_down"]), row["depth_difference_tn352_minus_mrar_m"], f"{threshold} m pair depth delta")
            close(abs(float(row["depth_difference_tn352_minus_mrar_m"])), row["absolute_depth_difference_m"], f"{threshold} m pair absolute delta")
            direct = float(
                arc_distance(
                    vectors(np.asarray([row["tn352_lon_deg"]]), np.asarray([row["tn352_lat_deg"]])),
                    vectors(np.asarray([row["mrar_lon_deg"]]), np.asarray([row["mrar_lat_deg"]])),
                )[0]
            )
            close(direct, row["distance_m"], f"{threshold} m pair distance", atol=1.0e-5)
        by_cell: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for row in rows:
            by_cell[str(row["cell_id"])].append(row)
        grouped[threshold] = dict(by_cell)
        keys[threshold] = set(threshold_keys)
    require(keys[100] <= keys[250] <= keys[500], "pair threshold sets are not nested")
    return grouped, keys


def object_h03_map(phase_a: Path) -> dict[str, int]:
    with (phase_a / "tn352_object_policy_summary.tsv").open("r", encoding="utf-8", newline="") as handle:
        return {str(row["source_object_id"]): int(row["n_h03"]) for row in csv.DictReader(handle, delimiter="\t")}


def verify_tail_summary(phase_b: Path, support: list[dict[str, Any]]) -> None:
    with (phase_b / "support_tail_summary.csv").open("r", encoding="utf-8", newline="") as handle:
        summary = list(csv.DictReader(handle))
    require(len(summary) == 24, "tail summary row count differs")
    by_key = {(row["basis"], row["stratum"]): row for row in summary}
    require(len(by_key) == 24, "tail summary keys differ")
    strata = {
        "zero_or_low_footprint_overlap": lambda row, prefix: bool(row["zero_footprint_overlap"] or row["low_footprint_overlap"]),
        "high_relief": lambda row, prefix: bool(row["high_relief"]),
        "low_matched_support": lambda row, prefix: bool(row[f"{prefix}_low_support"]),
        "small_source_support": lambda row, prefix: bool(row["small_source_support"]),
        "h03_associated_object": lambda row, prefix: bool(row["h03_associated_object"]),
    }
    for basis, threshold, prefix, field in [
        ("raw", None, None, "raw_cell_median_delta_m"),
        ("matched_100m", 100, "match_100m", "match_100m_median_signed_m"),
        ("matched_250m", 250, "match_250m", "match_250m_median_signed_m"),
        ("matched_500m", 500, "match_500m", "match_500m_median_signed_m"),
    ]:
        evaluable = [row for row in support if row[field] is not None]
        values = np.abs(np.asarray([float(row[field]) for row in evaluable]))
        overall = by_key[(basis, "overall")]
        require(int(overall["evaluable_cell_count"]) == len(evaluable), f"tail evaluable count differs: {basis}")
        require(int(overall["tail_cell_count"]) == int(np.count_nonzero(values > 500.0)), f"tail count differs: {basis}")
        if evaluable:
            close(float(np.quantile(values, 0.95, method="linear")), float(overall["absolute_delta_p95_m"]), f"tail P95 differs: {basis}")
        for stratum, predicate in strata.items():
            row = by_key[(basis, stratum)]
            if basis == "raw" and stratum == "low_matched_support":
                selected = []
            else:
                selected = [item for item in evaluable if predicate(item, prefix)]
            complement = [item for item in evaluable if item not in selected]
            require(int(row["stratum_cell_count"]) == len(selected), f"stratum count differs: {basis}/{stratum}")
            require(int(row["complement_cell_count"]) == len(complement), f"complement count differs: {basis}/{stratum}")


def verify(run_dir: Path) -> Path:
    run_dir = run_dir.resolve()
    phase_b = run_dir / "phase_b"
    verification_path = phase_b / "verification.json"
    require(not verification_path.exists(), "Phase B verification already exists")
    checks: list[str] = []
    try:
        manifest = read_json(phase_b / "audit_manifest.json")
        protocol = read_json(phase_b / "frozen_protocol.json")
        lock = read_json(phase_b / "input_lock.json")
        freeze_receipt = read_json(phase_b / "freeze_receipt.json")
        require(protocol["status"] == "approved_frozen", "protocol status differs")
        require(lock["status"] == "frozen_before_depth_access" and freeze_receipt["status"] == "pass", "freeze status differs")
        require(not lock["depth_value_columns_read_before_lock"], "depth values were read before freeze")
        require(sha256_file(phase_b / "frozen_protocol.json") == manifest["frozen_protocol_sha256"], "protocol hash differs")
        require(sha256_file(phase_b / "input_lock.json") == manifest["input_lock_sha256"], "input lock hash differs")
        require(sha256_file(phase_b / "common_cell_cohort.parquet") == manifest["common_cell_cohort_sha256"], "cohort hash differs")
        require(sha256_file(phase_b / "cell_id_comparison.json") == lock["cell_id_comparison"]["sha256"], "cell-ID comparison hash differs")
        require(sha256_file(phase_b / "phase_b_cell_id_status.parquet") == lock["phase_b_cell_id_status"]["sha256"], "cell-ID status hash differs")
        checks.append("freeze_order_and_hashes")
        for name, record in lock["inputs"].items():
            path = Path(record["path"])
            if path.is_file():
                require(path.stat().st_size == int(record["bytes"]) and sha256_file(path) == record["sha256"], f"input drift: {name}")
            else:
                rows = []
                for child in sorted(item for item in path.rglob("*") if item.is_file()):
                    rows.append({"relative_path": child.relative_to(path).as_posix(), "bytes": child.stat().st_size, "sha256": sha256_file(child)})
                require(canonical_sha256(rows) == record["sha256"], f"input tree drift: {name}")
        checks.append("input_hashes_unchanged")
        verify_cell_id_gate(lock, phase_b)
        checks.append("independent_pre_depth_cell_id_sets_and_statuses")
        phase_a = Path(lock["phase_a_path"])
        require(phase_a.is_dir(), "locked Phase A directory is missing")
        cohort = pq.read_table(phase_b / "common_cell_cohort.parquet").to_pylist()
        support = pq.read_table(phase_b / "tn352_mrar_support_cells.parquet").to_pylist()
        require(len(cohort) == len(support) == 2_244, "cohort/support row count differs")
        require([row["cell_id"] for row in cohort] == [row["cell_id"] for row in support], "support row ordering or cohort differs")
        require(len({row["cell_id"] for row in support}) == 2_244, "support cell IDs are not unique")
        status_rows = pq.read_table(phase_b / "phase_b_cell_id_status.parquet").to_pylist()
        excluded_ids = {
            str(row["cell_id"])
            for row in status_rows
            if row["analysis_status"] == "raw_support_only_not_in_frozen_scalar_pair"
        }
        require(len(excluded_ids) == 123, "excluded raw-support-only ID count differs")
        require(not (excluded_ids & {str(row["cell_id"]) for row in support}), "excluded IDs entered support output")
        checks.append("cohort_support_and_excluded_keys")
        pair_rows, pair_keys = read_pairs(phase_b)
        for threshold in (100, 250, 500):
            require(not (excluded_ids & set(pair_rows[threshold])), f"excluded IDs entered {threshold} m pairs")
        checks.append("pair_schema_delta_distance_nesting_and_exclusions")
        tn_points = load_tn352_points(cohort)
        mrar_points = load_mrar_points(cohort)
        tn_offsets = cell_offsets(tn_points, len(cohort))
        mrar_offsets = cell_offsets(mrar_points, len(cohort))
        h03 = object_h03_map(phase_a)
        for cell_index, (cohort_row, observed) in enumerate(zip(cohort, support)):
            cell_id = str(cohort_row["cell_id"])
            tn = point_slice(tn_points, tn_offsets, cell_index)
            mrar = point_slice(mrar_points, mrar_offsets, cell_index)
            require(len(tn) == int(observed["tn352_point_count"]) == int(cohort_row["tn352_n_qc_eligible"]), f"TN352 cell point count differs: {cell_id}")
            require(len(mrar) == int(observed["mrar_point_count"]) == int(cohort_row["mrar_n_points_pass_total"]), f"MRAR cell point count differs: {cell_id}")
            close(float(np.median(tn.depth)), observed["tn352_exact_median_depth_m_positive_down"], f"TN352 median differs: {cell_id}")
            close(float(np.median(mrar.depth)), observed["mrar_representative_depth_m_positive_down"], f"MRAR median differs: {cell_id}")
            close(float(observed["tn352_exact_median_depth_m_positive_down"]) - float(observed["mrar_representative_depth_m_positive_down"]), observed["raw_cell_median_delta_m"], f"raw delta sign differs: {cell_id}")
            tn_centroid = centroid(tn.lon, tn.lat)
            mrar_centroid = centroid(mrar.lon, mrar.lat)
            close(tn_centroid[0], observed["tn352_centroid_lon"], f"TN352 centroid lon differs: {cell_id}")
            close(tn_centroid[1], observed["tn352_centroid_lat"], f"TN352 centroid lat differs: {cell_id}")
            close(mrar_centroid[0], observed["mrar_centroid_lon"], f"MRAR centroid lon differs: {cell_id}")
            close(mrar_centroid[1], observed["mrar_centroid_lat"], f"MRAR centroid lat differs: {cell_id}")
            centroid_distance = float(arc_distance(vectors(np.asarray([tn_centroid[0]]), np.asarray([tn_centroid[1]])), vectors(np.asarray([mrar_centroid[0]]), np.asarray([mrar_centroid[1]])))[0])
            close(centroid_distance, observed["centroid_distance_m"], f"centroid distance differs: {cell_id}", atol=1.0e-5)
            tn_occ = independent_occupancy(tn.lon, tn.lat, float(cohort_row["lon_center"]), float(cohort_row["lat_center"]))
            mrar_occ = independent_occupancy(mrar.lon, mrar.lat, float(cohort_row["lon_center"]), float(cohort_row["lat_center"]))
            intersection = len(tn_occ & mrar_occ)
            union = len(tn_occ | mrar_occ)
            smaller = min(len(tn_occ), len(mrar_occ))
            require(intersection == int(observed["occupancy_intersection_100m"]) and union == int(observed["occupancy_union_100m"]), f"occupancy counts differ: {cell_id}")
            close(intersection / union, observed["occupancy_jaccard_100m"], f"occupancy Jaccard differs: {cell_id}")
            close(intersection / smaller, observed["occupancy_smaller_support_coverage_100m"], f"occupancy smaller coverage differs: {cell_id}")
            tn_index, mrar_index, distance, minimum = independent_pairs(tn, mrar)
            close(minimum, observed["minimum_cross_source_point_distance_m"], f"minimum point distance differs: {cell_id}", atol=1.0e-5)
            for threshold in (100, 250, 500):
                selected = distance <= threshold
                expected_keys = {
                    expected_pair_key(cell_id, tn, mrar, int(tn_i), int(mrar_i))
                    for tn_i, mrar_i in zip(tn_index[selected], mrar_index[selected])
                }
                actual_keys = {pair_key(row) for row in pair_rows[threshold].get(cell_id, [])}
                require(expected_keys == actual_keys, f"mutual pair membership differs: {cell_id}/{threshold}m")
                delta = tn.depth[tn_index[selected]] - mrar.depth[mrar_index[selected]]
                expected_metrics = metrics(delta)
                prefix = f"match_{threshold}m"
                require(int(observed[f"{prefix}_count"]) == expected_metrics["count"], f"pair count differs: {cell_id}/{threshold}m")
                for source, suffix in (
                    ("bias", "bias_m"),
                    ("mae", "mae_m"),
                    ("rmse", "rmse_m"),
                    ("p50_abs", "p50_abs_m"),
                    ("p95_abs", "p95_abs_m"),
                    ("min_signed", "min_signed_m"),
                    ("max_signed", "max_signed_m"),
                    ("median_signed", "median_signed_m"),
                ):
                    close(expected_metrics[source], observed[f"{prefix}_{suffix}"], f"metric differs: {cell_id}/{threshold}m/{source}")
                require(bool(observed[f"{prefix}_low_support"]) == (expected_metrics["count"] < 3), f"low-support flag differs: {cell_id}/{threshold}m")
                expected_tail = expected_metrics["median_signed"] is not None and abs(float(expected_metrics["median_signed"])) > 500.0
                require(bool(observed[f"{prefix}_persistent_tail"]) == expected_tail, f"persistent-tail flag differs: {cell_id}/{threshold}m")
            objects = sorted({tn.group_values[int(code)] for code in np.unique(tn.group_code)})
            tracks = sorted({mrar.group_values[int(code)] for code in np.unique(mrar.group_code)})
            require(observed["tn352_source_object_ids"] == objects and observed["mrar_track_ids"] == tracks, f"source identity list differs: {cell_id}")
            require(int(observed["tn352_source_object_count"]) == len(objects), f"TN352 selected object count differs: {cell_id}")
            require(len(objects) <= int(cohort_row["tn352_n_source_objects_all_soundings"]), f"TN352 selected object count exceeds all-sounding count: {cell_id}")
            require(int(observed["mrar_track_count"]) == len(tracks), f"MRAR track count differs: {cell_id}")
            h03_objects = [value for value in objects if h03.get(value, 0) > 0]
            require(int(observed["h03_associated_object_count"]) == len(h03_objects), f"H03 object count differs: {cell_id}")
            require(int(observed["h03_rows_in_contributing_objects"]) == sum(h03[value] for value in h03_objects), f"H03 associated rows differ: {cell_id}")
            raw_tail = abs(float(observed["raw_cell_median_delta_m"])) > 500.0
            associated = bool(
                observed["zero_footprint_overlap"]
                or observed["low_footprint_overlap"]
                or observed["high_relief"]
                or observed["match_500m_low_support"]
                or observed["small_source_support"]
                or observed["h03_associated_object"]
            )
            persistent = int(observed["match_500m_count"]) == 0 or bool(observed["match_500m_persistent_tail"])
            require(bool(observed["unresolved_500m"]) == (raw_tail and persistent and not associated), f"unresolved flag differs: {cell_id}")
        checks.append("independent_full_cell_geometry_pairs_metrics_and_flags")
        verify_tail_summary(phase_b, support)
        checks.append("tail_summary_registered_rules")
        for name, record in manifest["outputs"].items():
            path = phase_b / name
            require(path.is_file() and path.stat().st_size == int(record["bytes"]), f"output missing or bytes differ: {name}")
            require(sha256_file(path) == record["sha256"], f"output hash differs: {name}")
        checks.append("output_hashes")
        access = manifest["access_counts"]
        prohibited = ["sealed_body_reads", "sidecar_body_reads", "GGM", "PINN", "GEBCO", "product_residual_comparison", "model_residual_comparison", "MRAR_merge", "datum_or_bias_fit", "cross_cruise_aggregation"]
        require(all(int(access[name]) == 0 for name in prohibited), "prohibited operation count differs")
        report = " ".join((phase_b / "audit_report.md").read_text(encoding="utf-8").split())
        require("No GGM, PINN, GEBCO" in report and "does not promote the label" in report, "report evidence boundary differs")
        require("raw_support_only_not_in_frozen_scalar_pair" in report, "report cell-ID exclusion status differs")
        checks.append("prohibited_operations_and_claim_boundary")
        verification = {
            "schema_version": 1,
            "run_id": run_dir.name,
            "phase": "phase_b",
            "status": "pass",
            "output_role": OUTPUT_ROLE,
            "phase_a_classification": manifest["phase_a_classification"],
            "confirmation_role_eligible": False,
            "checks": checks,
            "row_counts": manifest["row_counts"],
            "audit_manifest_sha256": sha256_file(phase_b / "audit_manifest.json"),
            "verified_output_sha256": {name: record["sha256"] for name, record in manifest["outputs"].items()},
            "verifier_sha256": sha256_file(Path(__file__)),
            "independent_full_cell_recomputation": True,
            "sealed_or_sidecar_body_reads": 0,
            "GGM_PINN_GEBCO_model_product_operations": 0,
            "label_upgrade_supported": False,
        }
        temp = verification_path.with_suffix(".json.tmp")
        write_json(temp, verification)
        os.rename(temp, verification_path)
        return verification_path
    except Exception as error:
        failure = {
            "schema_version": 1,
            "run_id": run_dir.name,
            "phase": "phase_b",
            "status": "fail",
            "checks_completed": checks,
            "error_type": type(error).__name__,
            "error": str(error),
            "sealed_or_sidecar_body_reads": 0,
            "GGM_PINN_GEBCO_model_product_operations": 0,
        }
        temp = verification_path.with_suffix(".json.tmp")
        write_json(temp, failure)
        os.rename(temp, verification_path)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    print(verify(args.run_dir))


if __name__ == "__main__":
    main()
