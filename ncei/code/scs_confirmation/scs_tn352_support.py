#!/usr/bin/env python3
"""Frozen point selection and geometry for the TN352-MRAR support audit."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
from scipy.spatial import cKDTree

from ncei.code.scs_confirmation.scs_tn352_audit_common import MRAR_POINTS_PATH, STAGE_C_ROOT, nmad, require


EARTH_RADIUS_M = 6_371_008.8
TIE_TOLERANCE_M = 1.0e-6
THRESHOLDS_M = (100.0, 250.0, 500.0)
TN352 = "TN352"


@dataclass
class SupportPoints:
    cell_index: np.ndarray
    group_code: np.ndarray
    first_index: np.ndarray
    second_index: np.ndarray
    lon: np.ndarray
    lat: np.ndarray
    depth: np.ndarray
    navigation_valid: np.ndarray
    group_values: list[str]

    def __len__(self) -> int:
        return int(self.cell_index.size)


class StringEncoder:
    def __init__(self) -> None:
        self._codes: dict[str, int] = {}

    def encode(self, values: pa.Array) -> np.ndarray:
        encoded = pc.dictionary_encode(values)
        local_values = [str(value) for value in encoded.dictionary.to_pylist()]
        local_to_global = np.asarray(
            [self._codes.setdefault(value, len(self._codes)) for value in local_values],
            dtype=np.int32,
        )
        return local_to_global[encoded.indices.to_numpy(zero_copy_only=False)]

    def lexicographic_remap(self, chunks: list[np.ndarray]) -> tuple[np.ndarray, list[str]]:
        values = sorted(self._codes)
        lex_code = {value: index for index, value in enumerate(values)}
        old_to_lex = np.empty(len(self._codes), dtype=np.int32)
        for value, old_code in self._codes.items():
            old_to_lex[old_code] = lex_code[value]
        combined = concatenate(chunks, np.int32)
        return old_to_lex[combined], values


def concatenate(chunks: list[np.ndarray], dtype: np.dtype[Any] | type[Any]) -> np.ndarray:
    if not chunks:
        return np.asarray([], dtype=dtype)
    return np.concatenate(chunks).astype(dtype, copy=False)


def build_bin_lookup(cohort: list[dict[str, Any]]) -> tuple[np.ndarray, int, int, int, int]:
    lon_min = min(int(row["lon_bin"]) for row in cohort)
    lon_max = max(int(row["lon_bin"]) for row in cohort)
    lat_min = min(int(row["lat_bin"]) for row in cohort)
    lat_max = max(int(row["lat_bin"]) for row in cohort)
    width = lon_max - lon_min + 1
    height = lat_max - lat_min + 1
    lookup = np.full(width * height, -1, dtype=np.int32)
    for index, row in enumerate(cohort):
        offset = (int(row["lat_bin"]) - lat_min) * width + int(row["lon_bin"]) - lon_min
        require(lookup[offset] == -1, f"duplicate cohort bin: {row['cell_id']}")
        lookup[offset] = index
    return lookup, lon_min, lat_min, width, height


def lookup_cell_indices(
    lon_bin: np.ndarray,
    lat_bin: np.ndarray,
    lookup: np.ndarray,
    lon_min: int,
    lat_min: int,
    width: int,
    height: int,
) -> np.ndarray:
    lon_offset = lon_bin.astype(np.int64, copy=False) - lon_min
    lat_offset = lat_bin.astype(np.int64, copy=False) - lat_min
    inside = (lon_offset >= 0) & (lon_offset < width) & (lat_offset >= 0) & (lat_offset < height)
    output = np.full(lon_bin.size, -1, dtype=np.int32)
    positions = lat_offset[inside] * width + lon_offset[inside]
    output[inside] = lookup[positions]
    return output


def _finalize_points(
    chunks: dict[str, list[np.ndarray]],
    encoder: StringEncoder,
) -> SupportPoints:
    group_code, group_values = encoder.lexicographic_remap(chunks["group_code"])
    points = SupportPoints(
        cell_index=concatenate(chunks["cell_index"], np.int32),
        group_code=group_code,
        first_index=concatenate(chunks["first_index"], np.int64),
        second_index=concatenate(chunks["second_index"], np.int32),
        lon=concatenate(chunks["lon"], np.float64),
        lat=concatenate(chunks["lat"], np.float64),
        depth=concatenate(chunks["depth"], np.float64),
        navigation_valid=concatenate(chunks["navigation_valid"], bool),
        group_values=group_values,
    )
    order = np.argsort(points.cell_index, kind="stable")
    return take_points(points, order)


def take_points(points: SupportPoints, indices: np.ndarray) -> SupportPoints:
    return SupportPoints(
        cell_index=points.cell_index[indices],
        group_code=points.group_code[indices],
        first_index=points.first_index[indices],
        second_index=points.second_index[indices],
        lon=points.lon[indices],
        lat=points.lat[indices],
        depth=points.depth[indices],
        navigation_valid=points.navigation_valid[indices],
        group_values=points.group_values,
    )


def empty_chunks() -> dict[str, list[np.ndarray]]:
    return {
        "cell_index": [],
        "group_code": [],
        "first_index": [],
        "second_index": [],
        "lon": [],
        "lat": [],
        "depth": [],
        "navigation_valid": [],
    }


def load_tn352_points(cohort: list[dict[str, Any]]) -> SupportPoints:
    lookup, lon_min, lat_min, width, height = build_bin_lookup(cohort)
    dataset = ds.dataset(STAGE_C_ROOT / "sounding_lineage.parquet", format="parquet")
    columns = [
        "source_object_id",
        "parser_ping_index",
        "beam_index",
        "lon_deg",
        "lat_deg",
        "depth_m_positive_down",
        "navigation_valid",
        "qc_eligible_for_cell",
        "lon_bin",
        "lat_bin",
    ]
    scanner = dataset.scanner(
        columns=columns,
        filter=(ds.field("official_cruise_id") == TN352) & ds.field("qc_eligible_for_cell"),
        batch_size=262_144,
        use_threads=True,
    )
    chunks = empty_chunks()
    encoder = StringEncoder()
    for batch in scanner.to_batches():
        names = batch.schema.names
        lon_bin = batch.column(names.index("lon_bin")).to_numpy(zero_copy_only=False).astype(np.int64)
        lat_bin = batch.column(names.index("lat_bin")).to_numpy(zero_copy_only=False).astype(np.int64)
        cell_index = lookup_cell_indices(lon_bin, lat_bin, lookup, lon_min, lat_min, width, height)
        selected = cell_index >= 0
        if not np.any(selected):
            continue
        lon = batch.column(names.index("lon_deg")).to_numpy(zero_copy_only=False)[selected]
        lat = batch.column(names.index("lat_deg")).to_numpy(zero_copy_only=False)[selected]
        depth = batch.column(names.index("depth_m_positive_down")).to_numpy(zero_copy_only=False)[selected]
        navigation = batch.column(names.index("navigation_valid")).to_numpy(zero_copy_only=False)[selected]
        eligible = batch.column(names.index("qc_eligible_for_cell")).to_numpy(zero_copy_only=False)[selected]
        recomputed_lon_bin = np.floor((lon + 180.0) * 60.0).astype(np.int64)
        recomputed_lat_bin = np.floor((lat + 90.0) * 60.0).astype(np.int64)
        require(np.array_equal(recomputed_lon_bin, lon_bin[selected]), "TN352 cell longitude recomputation differs")
        require(np.array_equal(recomputed_lat_bin, lat_bin[selected]), "TN352 cell latitude recomputation differs")
        require(np.all(navigation) and np.all(eligible), "TN352 selected point violates frozen selector")
        require(np.all(np.isfinite(depth) & (depth > 0.0) & (depth <= 12_000.0)), "TN352 selected depth invalid")
        group_codes = encoder.encode(batch.column(names.index("source_object_id")))[selected]
        chunks["cell_index"].append(cell_index[selected])
        chunks["group_code"].append(group_codes)
        chunks["first_index"].append(batch.column(names.index("parser_ping_index")).to_numpy(zero_copy_only=False)[selected])
        chunks["second_index"].append(batch.column(names.index("beam_index")).to_numpy(zero_copy_only=False)[selected])
        chunks["lon"].append(lon)
        chunks["lat"].append(lat)
        chunks["depth"].append(depth)
        chunks["navigation_valid"].append(navigation)
    points = _finalize_points(chunks, encoder)
    expected = sum(int(row["tn352_n_qc_eligible"]) for row in cohort)
    require(len(points) == expected, f"TN352 selected point count differs: {len(points)} != {expected}")
    validate_point_keys(points, include_second=True, source="TN352")
    return points


def load_mrar_points(cohort: list[dict[str, Any]]) -> SupportPoints:
    lookup, lon_min, lat_min, width, height = build_bin_lookup(cohort)
    dataset = ds.dataset(MRAR_POINTS_PATH, format="parquet")
    columns = [
        "track_id",
        "point_index_in_track",
        "lon",
        "lat",
        "depth_m_positive_down",
        "point_check_pass_basic",
    ]
    filter_expression = (
        ds.field("point_check_pass_basic")
        & (ds.field("lon") >= 105.0)
        & (ds.field("lon") < 125.0)
        & (ds.field("lat") >= 0.0)
        & (ds.field("lat") < 25.0)
    )
    scanner = dataset.scanner(columns=columns, filter=filter_expression, batch_size=262_144, use_threads=True)
    chunks = empty_chunks()
    encoder = StringEncoder()
    for batch in scanner.to_batches():
        names = batch.schema.names
        lon = batch.column(names.index("lon")).to_numpy(zero_copy_only=False)
        lat = batch.column(names.index("lat")).to_numpy(zero_copy_only=False)
        lon_bin = np.floor((lon + 180.0) * 60.0).astype(np.int64)
        lat_bin = np.floor((lat + 90.0) * 60.0).astype(np.int64)
        cell_index = lookup_cell_indices(lon_bin, lat_bin, lookup, lon_min, lat_min, width, height)
        selected = cell_index >= 0
        if not np.any(selected):
            continue
        depth = batch.column(names.index("depth_m_positive_down")).to_numpy(zero_copy_only=False)[selected]
        passed = batch.column(names.index("point_check_pass_basic")).to_numpy(zero_copy_only=False)[selected]
        require(np.all(passed), "MRAR selected point violates point_check_pass_basic")
        require(np.all(np.isfinite(lon[selected]) & np.isfinite(lat[selected])), "MRAR selected coordinate is non-finite")
        require(np.all(np.isfinite(depth) & (depth > 0.0)), "MRAR selected depth is non-positive or non-finite")
        group_codes = encoder.encode(batch.column(names.index("track_id")))[selected]
        chunks["cell_index"].append(cell_index[selected])
        chunks["group_code"].append(group_codes)
        chunks["first_index"].append(batch.column(names.index("point_index_in_track")).to_numpy(zero_copy_only=False)[selected])
        chunks["second_index"].append(np.zeros(int(np.count_nonzero(selected)), dtype=np.int32))
        chunks["lon"].append(lon[selected])
        chunks["lat"].append(lat[selected])
        chunks["depth"].append(depth)
        chunks["navigation_valid"].append(np.ones(int(np.count_nonzero(selected)), dtype=bool))
    points = _finalize_points(chunks, encoder)
    expected = sum(int(row["mrar_n_points_pass_total"]) for row in cohort)
    require(len(points) == expected, f"MRAR selected point count differs: {len(points)} != {expected}")
    validate_point_keys(points, include_second=False, source="MRAR")
    return points


def validate_point_keys(points: SupportPoints, *, include_second: bool, source: str) -> None:
    if len(points) < 2:
        return
    if include_second:
        order = np.lexsort((points.second_index, points.first_index, points.group_code))
        same = (
            (points.group_code[order][1:] == points.group_code[order][:-1])
            & (points.first_index[order][1:] == points.first_index[order][:-1])
            & (points.second_index[order][1:] == points.second_index[order][:-1])
        )
    else:
        order = np.lexsort((points.first_index, points.group_code))
        same = (
            (points.group_code[order][1:] == points.group_code[order][:-1])
            & (points.first_index[order][1:] == points.first_index[order][:-1])
        )
    require(not np.any(same), f"{source} stable point keys are not unique")


def cell_offsets(points: SupportPoints, cell_count: int) -> np.ndarray:
    return np.searchsorted(points.cell_index, np.arange(cell_count + 1, dtype=np.int32))


def unit_vectors(lon_deg: np.ndarray, lat_deg: np.ndarray) -> np.ndarray:
    lon = np.radians(np.asarray(lon_deg, dtype=np.float64))
    lat = np.radians(np.asarray(lat_deg, dtype=np.float64))
    cos_lat = np.cos(lat)
    return np.column_stack((cos_lat * np.cos(lon), cos_lat * np.sin(lon), np.sin(lat)))


def great_circle_distance_m(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    chord = np.linalg.norm(np.asarray(left) - np.asarray(right), axis=-1)
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.minimum(1.0, chord / 2.0))


def spherical_centroid(lon: np.ndarray, lat: np.ndarray) -> tuple[float, float]:
    vectors = unit_vectors(lon, lat)
    mean = vectors.mean(axis=0)
    norm = float(np.linalg.norm(mean))
    require(norm > 0.0, "spherical centroid is undefined")
    normalized = mean / norm
    return math.degrees(math.atan2(float(normalized[1]), float(normalized[0]))), math.degrees(math.asin(float(normalized[2])))


def _stable_nearest(query: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    require(query.shape[0] > 0 and target.shape[0] > 0, "nearest search requires nonempty arrays")
    tree = cKDTree(target)
    if target.shape[0] == 1:
        chosen = np.zeros(query.shape[0], dtype=np.int64)
        distances = great_circle_distance_m(query, target[chosen])
        return chosen, distances
    chord, indices = tree.query(query, k=2, workers=1)
    chosen = indices[:, 0].astype(np.int64)
    first_distance = great_circle_distance_m(query, target[chosen])
    second_distance = great_circle_distance_m(query, target[indices[:, 1]])
    tied = np.flatnonzero(second_distance - first_distance <= TIE_TOLERANCE_M)
    for query_index in tied:
        radius_m = float(first_distance[query_index] + TIE_TOLERANCE_M)
        chord_radius = 2.0 * math.sin(radius_m / (2.0 * EARTH_RADIUS_M)) + 1.0e-15
        candidates = np.asarray(tree.query_ball_point(query[query_index], chord_radius), dtype=np.int64)
        candidate_distances = great_circle_distance_m(
            np.repeat(query[query_index][None, :], candidates.size, axis=0), target[candidates]
        )
        minimum = float(candidate_distances.min())
        tied_candidates = candidates[candidate_distances <= minimum + TIE_TOLERANCE_M]
        chosen[query_index] = int(tied_candidates.min())
        first_distance[query_index] = minimum
    return chosen, first_distance


def mutual_nearest_pairs(tn: SupportPoints, mrar: SupportPoints) -> tuple[np.ndarray, np.ndarray, np.ndarray, float | None]:
    if len(tn) == 0 or len(mrar) == 0:
        empty = np.asarray([], dtype=np.int64)
        return empty, empty, np.asarray([], dtype=np.float64), None
    tn_order = np.lexsort((tn.second_index, tn.first_index, tn.group_code))
    mrar_order = np.lexsort((mrar.first_index, mrar.group_code))
    tn_xyz = unit_vectors(tn.lon[tn_order], tn.lat[tn_order])
    mrar_xyz = unit_vectors(mrar.lon[mrar_order], mrar.lat[mrar_order])
    tn_to_mrar, tn_distances = _stable_nearest(tn_xyz, mrar_xyz)
    mrar_to_tn, _ = _stable_nearest(mrar_xyz, tn_xyz)
    tn_stable_index = np.arange(tn_xyz.shape[0], dtype=np.int64)
    mutual = mrar_to_tn[tn_to_mrar] == tn_stable_index
    selected_tn_stable = tn_stable_index[mutual]
    selected_mrar_stable = tn_to_mrar[mutual]
    return (
        tn_order[selected_tn_stable],
        mrar_order[selected_mrar_stable],
        tn_distances[mutual],
        float(tn_distances.min()),
    )


def occupancy_indices(lon: np.ndarray, lat: np.ndarray, center_lon: float, center_lat: float) -> set[tuple[int, int]]:
    lon_rad = np.radians(np.asarray(lon, dtype=np.float64))
    lat_rad = np.radians(np.asarray(lat, dtype=np.float64))
    center_lon_rad = math.radians(center_lon)
    center_lat_rad = math.radians(center_lat)
    x = EARTH_RADIUS_M * math.cos(center_lat_rad) * (lon_rad - center_lon_rad)
    y = EARTH_RADIUS_M * (lat_rad - center_lat_rad)
    x_index = np.floor(x / 100.0).astype(np.int64)
    y_index = np.floor(y / 100.0).astype(np.int64)
    return set(zip(x_index.tolist(), y_index.tolist()))


def depth_summary(values: np.ndarray) -> dict[str, float | None]:
    if values.size == 0:
        return {"min": None, "max": None, "range": None, "nmad": None, "median": None}
    minimum = float(np.min(values))
    maximum = float(np.max(values))
    return {
        "min": minimum,
        "max": maximum,
        "range": maximum - minimum,
        "nmad": nmad(values),
        "median": float(np.median(values)),
    }


def difference_metrics(delta: np.ndarray) -> dict[str, float | int | None]:
    if delta.size == 0:
        return {
            "count": 0,
            "bias": None,
            "mae": None,
            "rmse": None,
            "p50_abs": None,
            "p95_abs": None,
            "min_signed": None,
            "max_signed": None,
            "median_signed": None,
        }
    absolute = np.abs(delta)
    return {
        "count": int(delta.size),
        "bias": float(np.mean(delta)),
        "mae": float(np.mean(absolute)),
        "rmse": float(np.sqrt(np.mean(np.square(delta)))),
        "p50_abs": float(np.quantile(absolute, 0.50, method="linear")),
        "p95_abs": float(np.quantile(absolute, 0.95, method="linear")),
        "min_signed": float(np.min(delta)),
        "max_signed": float(np.max(delta)),
        "median_signed": float(np.median(delta)),
    }


def support_schema() -> pa.Schema:
    fields: list[tuple[str, pa.DataType]] = [
        ("cell_id", pa.string()),
        ("lon_bin", pa.int64()),
        ("lat_bin", pa.int64()),
        ("lon_center", pa.float64()),
        ("lat_center", pa.float64()),
        ("tn352_official_cruise_id", pa.string()),
        ("tn352_point_count", pa.int64()),
        ("mrar_point_count", pa.int64()),
        ("tn352_source_object_count", pa.int64()),
        ("mrar_track_count", pa.int64()),
        ("tn352_source_object_ids", pa.list_(pa.string())),
        ("mrar_track_ids", pa.list_(pa.string())),
        ("tn352_navigation_valid_count", pa.int64()),
        ("tn352_navigation_invalid_count", pa.int64()),
        ("h03_associated_object_count", pa.int64()),
        ("h03_rows_in_contributing_objects", pa.int64()),
        ("tn352_centroid_lon", pa.float64()),
        ("tn352_centroid_lat", pa.float64()),
        ("mrar_centroid_lon", pa.float64()),
        ("mrar_centroid_lat", pa.float64()),
        ("centroid_distance_m", pa.float64()),
        ("minimum_cross_source_point_distance_m", pa.float64()),
        ("tn352_depth_min_m", pa.float64()),
        ("tn352_depth_max_m", pa.float64()),
        ("tn352_depth_range_m", pa.float64()),
        ("tn352_depth_nmad_m", pa.float64()),
        ("mrar_depth_min_m", pa.float64()),
        ("mrar_depth_max_m", pa.float64()),
        ("mrar_depth_range_m", pa.float64()),
        ("mrar_depth_nmad_m", pa.float64()),
        ("tn352_occupancy_count_100m", pa.int64()),
        ("mrar_occupancy_count_100m", pa.int64()),
        ("occupancy_intersection_100m", pa.int64()),
        ("occupancy_union_100m", pa.int64()),
        ("occupancy_jaccard_100m", pa.float64()),
        ("occupancy_smaller_support_coverage_100m", pa.float64()),
        ("tn352_exact_median_depth_m_positive_down", pa.float64()),
        ("mrar_representative_depth_m_positive_down", pa.float64()),
        ("raw_cell_median_delta_m", pa.float64()),
    ]
    for threshold in (100, 250, 500):
        prefix = f"match_{threshold}m"
        fields.extend(
            [
                (f"{prefix}_count", pa.int64()),
                (f"{prefix}_bias_m", pa.float64()),
                (f"{prefix}_mae_m", pa.float64()),
                (f"{prefix}_rmse_m", pa.float64()),
                (f"{prefix}_p50_abs_m", pa.float64()),
                (f"{prefix}_p95_abs_m", pa.float64()),
                (f"{prefix}_min_signed_m", pa.float64()),
                (f"{prefix}_max_signed_m", pa.float64()),
                (f"{prefix}_median_signed_m", pa.float64()),
                (f"{prefix}_persistent_tail", pa.bool_()),
                (f"{prefix}_low_support", pa.bool_()),
            ]
        )
    fields.extend(
        [
            ("raw_tail", pa.bool_()),
            ("high_relief", pa.bool_()),
            ("zero_footprint_overlap", pa.bool_()),
            ("low_footprint_overlap", pa.bool_()),
            ("small_source_support", pa.bool_()),
            ("h03_associated_object", pa.bool_()),
            ("unresolved_500m", pa.bool_()),
        ]
    )
    return pa.schema(fields)


def pair_schema() -> pa.Schema:
    return pa.schema(
        [
            ("cell_id", pa.string()),
            ("lon_bin", pa.int64()),
            ("lat_bin", pa.int64()),
            ("tn352_source_object_id", pa.string()),
            ("tn352_parser_ping_index", pa.int64()),
            ("tn352_beam_index", pa.int32()),
            ("tn352_lon_deg", pa.float64()),
            ("tn352_lat_deg", pa.float64()),
            ("tn352_depth_m_positive_down", pa.float64()),
            ("mrar_track_id", pa.string()),
            ("mrar_point_index_in_track", pa.int64()),
            ("mrar_lon_deg", pa.float64()),
            ("mrar_lat_deg", pa.float64()),
            ("mrar_depth_m_positive_down", pa.float64()),
            ("distance_m", pa.float64()),
            ("depth_difference_tn352_minus_mrar_m", pa.float64()),
            ("absolute_depth_difference_m", pa.float64()),
            ("mutual_nearest", pa.bool_()),
            ("threshold_m", pa.float64()),
            ("tn352_official_cruise_id", pa.string()),
            ("tn352_navigation_valid", pa.bool_()),
            ("tn352_qc_eligible_for_cell", pa.bool_()),
            ("tn352_object_h03_associated", pa.bool_()),
        ]
    )
