#!/usr/bin/env python3
"""Build a diagnostic-only SCS product-consistency and coverage audit.

Reads:
  - the frozen 174,965-cell downstream union (five allowlisted columns only)
  - persisted SCS lineage and raw-replay audit products
  - the frozen downstream 1-arcminute land mask
  - seven configured mature bathymetry grids
  - GEBCO 2024/2025/2026 TID grids

Writes under one immutable run directory:
  - product_consistency_by_cell.parquet
  - scs_product_context_1min.nc
  - coverage_grid_1min.nc
  - coverage_by_block_1deg.parquet
  - product_metrics.tsv
  - tid_composition.tsv
  - coverage_summary.json
  - audit_report.md
  - audit_manifest.json

Run from the repository root. This audit never reads downstream predictions,
residuals, model errors, metrics, or error-derived cohort columns. Mature-grid
agreement is descriptive and cannot filter, reweight, or relabel ship cells.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import xarray as xr
import yaml
from scipy.spatial import cKDTree


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[3]
DEFAULT_CONFIG = REPO_ROOT / "ncei/configs/scs_product_consistency_coverage.yaml"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "ncei/derived/scs_product_consistency_coverage"

EXPECTED_CELL_COUNT = 174_965
EXPECTED_SOURCE_COUNTS = {"mrar": 165_966, "jamstec": 8_999}
EXPECTED_REPLAY_COUNTS = {"exact": 174_913, "different": 52}
EXPECTED_GRID_SHAPE = (1500, 1200)
EXPECTED_OCEAN_CELL_COUNT = 1_288_723
REPLAY_ATOL_M = 1e-9
NMAD_SCALE = 1.4826
EARTH_RADIUS_KM = 6371.0088

UNION_COLUMNS = {
    "canonical_cell_id",
    "lon",
    "lat",
    "representative_depth_m",
    "source_provider",
}
FORBIDDEN_INPUT_TOKENS = {
    "external_samples",
    "model_error",
    "prediction",
    "predictions",
    "residual",
    "residuals",
    "outlier97",
}
FORBIDDEN_OUTPUT_COLUMN_TOKENS = {
    "weight",
    "eligible",
    "eligibility",
    "exclude",
    "exclusion",
    "decision",
    "outlier",
    "3std",
}

PRODUCT_DEPTH_COLUMNS = [
    "gebco_2024_depth_m",
    "gebco_2025_depth_m",
    "gebco_2026_depth_m",
    "etopo_2022_depth_m",
    "srtm15_v2_7_depth_m",
    "topo_25_1_depth_m",
    "sdust_2023_depth_m",
]
GEBCO_DEPTH_COLUMNS = [
    "gebco_2024_depth_m",
    "gebco_2025_depth_m",
    "gebco_2026_depth_m",
]
FAMILY_COMPONENT_COLUMNS = [
    "gebco_family_median_depth_m",
    "etopo_2022_depth_m",
    "srtm15_v2_7_depth_m",
    "topo_25_1_depth_m",
    "sdust_2023_depth_m",
]


def sha256_file(path: Path, chunk_size: int = 16 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def target_centers(
    west: float,
    east: float,
    south: float,
    north: float,
    increment_arcmin: int,
) -> tuple[np.ndarray, np.ndarray]:
    increment = increment_arcmin / 60.0
    n_lon = round((east - west) / increment)
    n_lat = round((north - south) / increment)
    lon = west + (np.arange(n_lon, dtype=np.float64) + 0.5) * increment
    lat = south + (np.arange(n_lat, dtype=np.float64) + 0.5) * increment
    return lon, lat


def aggregate_aligned_fine_grid(
    values: np.ndarray,
    factor: int,
    reducer: str,
) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 2 or factor < 1:
        raise ValueError("aligned aggregation expects a two-dimensional array and factor >= 1")
    if array.shape[0] % factor or array.shape[1] % factor:
        raise ValueError(f"fine-grid shape {array.shape} is not divisible by factor {factor}")
    if factor == 1:
        return array.astype(np.float64, copy=False)
    blocks = array.reshape(
        array.shape[0] // factor,
        factor,
        array.shape[1] // factor,
        factor,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        if reducer == "median":
            return np.nanmedian(blocks, axis=(1, 3))
        if reducer == "mean":
            return np.nanmean(blocks, axis=(1, 3))
    raise ValueError(f"unsupported aligned-grid reducer: {reducer}")


def elevation_to_depth(values: np.ndarray) -> np.ndarray:
    return -np.asarray(values, dtype=np.float64)


def nmad_rows(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 2:
        raise ValueError("row NMAD expects a two-dimensional array")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        median = np.nanmedian(array, axis=1)
        return NMAD_SCALE * np.nanmedian(np.abs(array - median[:, None]), axis=1)


def _row_range(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        result = np.nanmax(array, axis=1) - np.nanmin(array, axis=1)
    result[np.isfinite(array).sum(axis=1) == 0] = np.nan
    return result


def add_consensus_columns(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(PRODUCT_DEPTH_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"missing product columns for consensus: {missing}")
    product_values = frame[PRODUCT_DEPTH_COLUMNS].to_numpy(dtype=np.float64)
    gebco_values = frame[GEBCO_DEPTH_COLUMNS].to_numpy(dtype=np.float64)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        frame["gebco_family_median_depth_m"] = np.nanmedian(gebco_values, axis=1)
        frame["product_consensus_median_depth_m"] = np.nanmedian(product_values, axis=1)
    frame["product_consensus_nmad_m"] = nmad_rows(product_values)
    frame["product_consensus_range_m"] = _row_range(product_values)
    frame["product_consensus_count"] = np.isfinite(product_values).sum(axis=1).astype(np.int16)

    family_values = frame[FAMILY_COMPONENT_COLUMNS].to_numpy(dtype=np.float64)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        frame["family_consensus_median_depth_m"] = np.nanmedian(family_values, axis=1)
    frame["family_consensus_nmad_m"] = nmad_rows(family_values)
    frame["family_consensus_range_m"] = _row_range(family_values)
    frame["family_consensus_count"] = np.isfinite(family_values).sum(axis=1).astype(np.int16)
    return frame


def cell_area_km2(lat_centers: np.ndarray, increment_arcmin: int) -> np.ndarray:
    lat = np.asarray(lat_centers, dtype=np.float64)
    half = np.deg2rad(increment_arcmin / 120.0)
    delta_lon = np.deg2rad(increment_arcmin / 60.0)
    center = np.deg2rad(lat)
    return EARTH_RADIUS_KM**2 * delta_lon * (
        np.sin(center + half) - np.sin(center - half)
    )


def lonlat_to_unit_xyz(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    lon_rad = np.deg2rad(np.asarray(lon, dtype=np.float64))
    lat_rad = np.deg2rad(np.asarray(lat, dtype=np.float64))
    cos_lat = np.cos(lat_rad)
    return np.column_stack([
        cos_lat * np.cos(lon_rad),
        cos_lat * np.sin(lon_rad),
        np.sin(lat_rad),
    ])


def _chord_to_great_circle_km(chord: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(chord, dtype=np.float64) / 2.0, 0.0, 1.0)
    return 2.0 * np.arcsin(clipped) * EARTH_RADIUS_KM


def nearest_great_circle_km(queries_xyz: np.ndarray, controls_xyz: np.ndarray) -> np.ndarray:
    if len(controls_xyz) == 0:
        raise ValueError("nearest distance requires at least one control")
    tree = cKDTree(np.asarray(controls_xyz, dtype=np.float64))
    chord, _ = tree.query(np.asarray(queries_xyz, dtype=np.float64), k=1)
    return _chord_to_great_circle_km(chord)


def validate_tid_groups(groups: dict[str, Iterable[int]]) -> None:
    seen: dict[int, str] = {}
    if not groups:
        raise ValueError("TID groups cannot be empty")
    for group, codes in groups.items():
        codes_list = [int(value) for value in codes]
        if not codes_list:
            raise ValueError(f"TID group {group} cannot be empty")
        for code in codes_list:
            if code in seen:
                raise ValueError(f"TID code {code} appears in both {seen[code]} and {group}")
            seen[code] = group


def _tid_code_to_group(groups: dict[str, Iterable[int]]) -> dict[int, str]:
    validate_tid_groups(groups)
    return {int(code): group for group, codes in groups.items() for code in codes}


def aggregate_tid_groups(
    fine_values: np.ndarray,
    factor: int,
    groups: dict[str, Iterable[int]],
) -> tuple[dict[str, np.ndarray], dict[int, int]]:
    array = np.asarray(fine_values)
    if array.ndim != 2 or array.shape[0] % factor or array.shape[1] % factor:
        raise ValueError("TID fine grid is not aligned to the target factor")
    code_to_group = _tid_code_to_group(groups)
    observed, observed_counts = np.unique(array, return_counts=True)
    unexpected = sorted(int(code) for code in observed if int(code) not in code_to_group)
    if unexpected:
        raise ValueError(f"unconfigured TID codes observed: {unexpected}")
    fractions = {
        group: aggregate_aligned_fine_grid(
            np.isin(array, np.asarray(list(codes), dtype=array.dtype)).astype(np.float32),
            factor,
            "mean",
        ).astype(np.float32)
        for group, codes in groups.items()
    }
    counts = {int(code): int(count) for code, count in zip(observed, observed_counts)}
    closure = np.sum(np.stack(list(fractions.values()), axis=0), axis=0)
    if not np.allclose(closure, 1.0, rtol=0, atol=1e-7):
        raise ValueError("TID grouped fractions do not close to one")
    return fractions, counts


def validate_union_columns(requested_columns: Iterable[str]) -> None:
    requested = {str(column) for column in requested_columns}
    unexpected = sorted(requested - UNION_COLUMNS)
    missing = sorted(UNION_COLUMNS - requested)
    forbidden = sorted(
        column for column in requested
        if any(token in column.lower() for token in FORBIDDEN_INPUT_TOKENS)
    )
    if unexpected or missing or forbidden:
        raise ValueError(
            f"union read must use exactly the five allowlisted columns: "
            f"missing={missing}, unexpected={unexpected}, forbidden={forbidden}"
        )


def validate_diagnostic_output_columns(columns: Iterable[str]) -> None:
    bad = sorted(
        str(column) for column in columns
        if any(token in str(column).lower() for token in FORBIDDEN_OUTPUT_COLUMN_TOKENS)
    )
    if bad:
        raise ValueError(f"diagnostic output contains decision/weight columns: {bad}")


def _validate_input_path(path: Path) -> None:
    lowered = str(path).lower()
    forbidden = sorted(token for token in FORBIDDEN_INPUT_TOKENS if token in lowered)
    if forbidden:
        raise ValueError(f"forbidden downstream-derived input path {path}: {forbidden}")


def _atomic_text(value: str, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    frame.to_parquet(temporary, index=False)
    os.replace(temporary, path)


def _atomic_tsv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    frame.to_csv(temporary, sep="\t", index=False)
    os.replace(temporary, path)


def _atomic_netcdf(dataset: xr.Dataset, path: Path) -> None:
    temporary = path.with_name(path.stem + ".tmp.nc")
    encoding: dict[str, dict[str, Any]] = {}
    for name, variable in dataset.data_vars.items():
        if np.issubdtype(variable.dtype, np.floating):
            encoding[name] = {
                "zlib": True,
                "complevel": 4,
                "shuffle": True,
                "dtype": "float32",
                "_FillValue": np.float32(np.nan),
            }
        elif np.issubdtype(variable.dtype, np.bool_):
            encoding[name] = {"zlib": True, "complevel": 4, "dtype": "uint8"}
        else:
            encoding[name] = {"zlib": True, "complevel": 4}
    dataset.to_netcdf(temporary, engine="netcdf4", encoding=encoding)
    os.replace(temporary, path)


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError("audit config must be a YAML mapping")
    return config


def _flatten_input_config(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for role, record in config.get("inputs", {}).items():
        records[str(role)] = dict(record)
    for product in config.get("products", []):
        records[f"product_{product['key']}"] = {
            "path": product["path"],
            "sha256": product["sha256"],
        }
    for tid in config.get("tids", []):
        records[f"tid_{tid['year']}"] = {
            "path": tid["path"],
            "sha256": tid["sha256"],
        }
    if len(config.get("products", [])) != 7 or len(config.get("tids", [])) != 3:
        raise ValueError("config must contain exactly seven products and three TID grids")
    return records


def validate_frozen_inputs(config: dict[str, Any], logger: logging.Logger) -> dict[str, dict[str, Any]]:
    expected_records = _flatten_input_config(config)
    result: dict[str, dict[str, Any]] = {}
    for role, record in expected_records.items():
        path = Path(record["path"]).resolve()
        _validate_input_path(path)
        if not path.is_file():
            raise FileNotFoundError(f"missing frozen input {role}: {path}")
        expected = str(record["sha256"]).lower()
        if len(expected) != 64:
            raise ValueError(f"invalid expected SHA256 for {role}")
        started = time.monotonic()
        actual = sha256_file(path)
        logger.info("hashed role=%s size=%d elapsed_s=%.1f", role, path.stat().st_size, time.monotonic() - started)
        if actual != expected:
            raise ValueError(f"frozen input hash mismatch for {role}: {actual} != {expected}")
        result[role] = {
            "path": str(path),
            "sha256": actual,
            "size_bytes": path.stat().st_size,
        }
    return result


def _domain(config: dict[str, Any]) -> dict[str, Any]:
    domain = dict(config["domain"])
    lon, lat = target_centers(
        float(domain["west"]),
        float(domain["east"]),
        float(domain["south"]),
        float(domain["north"]),
        int(domain["increment_arcmin"]),
    )
    expected = (int(domain["expected_lat_count"]), int(domain["expected_lon_count"]))
    if (len(lat), len(lon)) != expected or expected != EXPECTED_GRID_SHAPE:
        raise ValueError(f"configured domain shape drift: {(len(lat), len(lon))} != {EXPECTED_GRID_SHAPE}")
    return {**domain, "lon": lon, "lat": lat}


def _selected_indices(values: np.ndarray, lower: float, upper: float, label: str) -> np.ndarray:
    coordinate = np.asarray(values, dtype=np.float64)
    indices = np.flatnonzero((coordinate >= lower) & (coordinate < upper))
    if len(indices) == 0 or not np.array_equal(indices, np.arange(indices[0], indices[-1] + 1)):
        raise ValueError(f"{label} SCS selection is empty or non-contiguous")
    return indices


def _apply_fill_scale(values: np.ndarray, attrs: dict[str, Any]) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    for key in ("_FillValue", "missing_value"):
        if key in attrs:
            fill = float(np.asarray(attrs[key]).reshape(-1)[0])
            result = np.where(result == fill, np.nan, result)
    scale = float(np.asarray(attrs.get("scale_factor", 1.0)).reshape(-1)[0])
    offset = float(np.asarray(attrs.get("add_offset", 0.0)).reshape(-1)[0])
    finite = np.isfinite(result)
    result[finite] = result[finite] * scale + offset
    return result


def _read_scs_window(record: dict[str, Any], domain: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    path = Path(record["path"])
    lon_name = record.get("lon_name", "lon")
    lat_name = record.get("lat_name", "lat")
    variable = record["variable"]
    west = float(domain["west"])
    east = float(domain["east"])
    if record.get("lon_convention", "-180_180") == "0_360":
        west %= 360.0
        east %= 360.0
    with xr.open_dataset(path, decode_cf=False, mask_and_scale=False) as dataset:
        lon_all = np.asarray(dataset[lon_name].values, dtype=np.float64)
        lat_all = np.asarray(dataset[lat_name].values, dtype=np.float64)
        lon_indices = _selected_indices(lon_all, west, east, f"{record.get('key', path.name)} longitude")
        lat_indices = _selected_indices(
            lat_all,
            float(domain["south"]),
            float(domain["north"]),
            f"{record.get('key', path.name)} latitude",
        )
        variable_data = dataset[variable].isel({
            lat_name: slice(int(lat_indices[0]), int(lat_indices[-1]) + 1),
            lon_name: slice(int(lon_indices[0]), int(lon_indices[-1]) + 1),
        }).transpose(lat_name, lon_name)
        values = _apply_fill_scale(variable_data.values, variable_data.attrs)
        lon = lon_all[lon_indices]
        lat = lat_all[lat_indices]
    if lon[0] > lon[-1]:
        lon = lon[::-1]
        values = values[:, ::-1]
    if lat[0] > lat[-1]:
        lat = lat[::-1]
        values = values[::-1, :]
    return lon, lat, values


def _validate_alignment(
    source_lon: np.ndarray,
    source_lat: np.ndarray,
    factor: int,
    target_lon: np.ndarray,
    target_lat: np.ndarray,
    label: str,
) -> None:
    expected_shape = (len(target_lat) * factor, len(target_lon) * factor)
    if (len(source_lat), len(source_lon)) != expected_shape:
        raise ValueError(
            f"{label} SCS shape {(len(source_lat), len(source_lon))} "
            f"does not match aligned shape {expected_shape}"
        )
    coarse_lon = source_lon.reshape(len(target_lon), factor).mean(axis=1)
    coarse_lat = source_lat.reshape(len(target_lat), factor).mean(axis=1)
    if not np.allclose(coarse_lon, target_lon, rtol=0, atol=2e-9):
        raise ValueError(f"{label} longitude is not exactly aligned to target centres")
    if not np.allclose(coarse_lat, target_lat, rtol=0, atol=2e-9):
        raise ValueError(f"{label} latitude is not exactly aligned to target centres")


def load_product_grid(record: dict[str, Any], domain: dict[str, Any]) -> np.ndarray:
    lon, lat, raw = _read_scs_window(record, domain)
    resolution_arcsec = int(record["resolution_arcsec"])
    if 60 % resolution_arcsec:
        raise ValueError(f"product resolution must divide one arc-minute: {record['key']}")
    factor = 60 // resolution_arcsec
    _validate_alignment(lon, lat, factor, domain["lon"], domain["lat"], record["key"])
    aggregation = record["aggregation"]
    if factor == 1 and aggregation != "exact":
        raise ValueError(f"one-arcminute product {record['key']} must use exact sampling")
    if factor > 1 and aggregation not in {"median", "mean"}:
        raise ValueError(f"fine-grid product {record['key']} requires median or mean aggregation")
    aggregated = aggregate_aligned_fine_grid(raw, factor, "median" if aggregation == "exact" else aggregation)
    if record["z_convention"] != "elevation_positive_up":
        raise ValueError(f"unsupported z convention for {record['key']}: {record['z_convention']}")
    return elevation_to_depth(aggregated).astype(np.float32)


def load_tid_grid(
    record: dict[str, Any],
    domain: dict[str, Any],
    groups: dict[str, Iterable[int]],
) -> tuple[np.ndarray, dict[str, np.ndarray], dict[int, int], int]:
    lon, lat, raw = _read_scs_window(record, domain)
    resolution_arcsec = int(record["resolution_arcsec"])
    if 60 % resolution_arcsec:
        raise ValueError("TID resolution must divide one arc-minute")
    factor = 60 // resolution_arcsec
    _validate_alignment(lon, lat, factor, domain["lon"], domain["lat"], f"TID {record['year']}")
    if not np.isfinite(raw).all() or not np.allclose(raw, np.rint(raw), rtol=0, atol=0):
        raise ValueError(f"TID {record['year']} contains missing or non-integer values in SCS")
    fine = np.rint(raw).astype(np.int16)
    fractions, counts = aggregate_tid_groups(fine, factor, groups)
    return fine, fractions, counts, factor


def load_frozen_cohort(
    union_path: Path,
    domain: dict[str, Any],
) -> pd.DataFrame:
    validate_union_columns(UNION_COLUMNS)
    schema_names = set(pq.ParquetFile(union_path).schema_arrow.names)
    missing = sorted(UNION_COLUMNS - schema_names)
    if missing:
        raise ValueError(f"frozen union is missing allowlisted columns: {missing}")
    cohort = pd.read_parquet(union_path, columns=sorted(UNION_COLUMNS))
    if len(cohort) != EXPECTED_CELL_COUNT or cohort["canonical_cell_id"].nunique() != EXPECTED_CELL_COUNT:
        raise ValueError("frozen union row/key closure failed")
    if cohort["source_provider"].value_counts().to_dict() != EXPECTED_SOURCE_COUNTS:
        raise ValueError("frozen union source closure failed")
    if not np.isfinite(cohort[["lon", "lat", "representative_depth_m"]].to_numpy(dtype=np.float64)).all():
        raise ValueError("frozen union contains non-finite geometry/depth")
    increment = int(domain["increment_arcmin"]) / 60.0
    lon_index = np.floor((cohort["lon"].to_numpy() - float(domain["west"])) / increment).astype(np.int32)
    lat_index = np.floor((cohort["lat"].to_numpy() - float(domain["south"])) / increment).astype(np.int32)
    if (
        (lon_index < 0).any()
        or (lon_index >= len(domain["lon"])).any()
        or (lat_index < 0).any()
        or (lat_index >= len(domain["lat"])).any()
    ):
        raise ValueError("frozen union contains cells outside the SCS domain")
    if not np.allclose(cohort["lon"], domain["lon"][lon_index], rtol=0, atol=2e-9):
        raise ValueError("frozen union longitudes do not match target cell centres")
    if not np.allclose(cohort["lat"], domain["lat"][lat_index], rtol=0, atol=2e-9):
        raise ValueError("frozen union latitudes do not match target cell centres")
    cohort["lon_index"] = lon_index
    cohort["lat_index"] = lat_index
    return cohort


def load_frozen_land_mask(path: Path, domain: dict[str, Any]) -> np.ndarray:
    with xr.open_dataset(path) as dataset:
        if "land_mask" not in dataset:
            raise ValueError("frozen domain context lacks land_mask")
        if not np.allclose(dataset["lon"].values, domain["lon"], rtol=0, atol=2e-9):
            raise ValueError("frozen land-mask longitude drift")
        if not np.allclose(dataset["lat"].values, domain["lat"], rtol=0, atol=2e-9):
            raise ValueError("frozen land-mask latitude drift")
        land = np.asarray(dataset["land_mask"].values, dtype=bool)
    if land.shape != EXPECTED_GRID_SHAPE or int((~land).sum()) != EXPECTED_OCEAN_CELL_COUNT:
        raise ValueError("frozen strict-ocean mask count/shape drift")
    return land


def load_lineage_and_replay(
    lineage_path: Path,
    replay_path: Path,
    cohort: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    lineage_columns = [
        "canonical_cell_id",
        "source_provider",
        "lineage_class",
        "lineage_class_status",
    ]
    replay_columns = [
        "canonical_cell_id",
        "source_provider",
        "raw_point_count",
        "raw_file_count",
        "official_cruise_count",
        "within_file_nmad_m",
        "between_file_nmad_m",
        "between_cruise_nmad_m",
        "signed_diff_m",
        "absolute_diff_m",
        "replay_result",
        "aggregation_method",
    ]
    lineage = pd.read_parquet(lineage_path, columns=lineage_columns)
    replay = pd.read_parquet(replay_path, columns=replay_columns)
    expected_keys = set(cohort["canonical_cell_id"])
    for name, frame in (("lineage", lineage), ("replay", replay)):
        if len(frame) != EXPECTED_CELL_COUNT or frame["canonical_cell_id"].nunique() != EXPECTED_CELL_COUNT:
            raise ValueError(f"{name} row/key closure failed")
        if set(frame["canonical_cell_id"]) != expected_keys:
            raise ValueError(f"{name} key set differs from frozen union")
    replay_counts = replay["replay_result"].value_counts().to_dict()
    if replay_counts != EXPECTED_REPLAY_COUNTS:
        raise ValueError(f"replay result closure drift: {replay_counts}")
    if int((replay["absolute_diff_m"] > REPLAY_ATOL_M).sum()) != EXPECTED_REPLAY_COUNTS["different"]:
        raise ValueError("replay tolerance closure drift")
    return lineage, replay


def build_cell_diagnostics(
    cohort: pd.DataFrame,
    lineage: pd.DataFrame,
    replay: pd.DataFrame,
    product_grids: dict[str, np.ndarray],
    tid_fractions: dict[int, dict[str, np.ndarray]],
) -> pd.DataFrame:
    base = cohort.rename(columns={"representative_depth_m": "ship_depth_m_positive_down"}).copy()
    base = base.merge(
        lineage.rename(columns={"source_provider": "lineage_source_provider"}),
        on="canonical_cell_id",
        validate="one_to_one",
    )
    replay_renames = {
        "source_provider": "replay_source_provider",
        "signed_diff_m": "raw_replay_signed_diff_m",
        "absolute_diff_m": "raw_replay_absolute_diff_m",
        "replay_result": "raw_replay_result",
        "aggregation_method": "raw_replay_aggregation_method",
    }
    base = base.merge(
        replay.rename(columns=replay_renames),
        on="canonical_cell_id",
        validate="one_to_one",
    )
    if not base["source_provider"].eq(base["lineage_source_provider"]).all():
        raise ValueError("union/lineage source-provider mismatch")
    if not base["source_provider"].eq(base["replay_source_provider"]).all():
        raise ValueError("union/replay source-provider mismatch")
    base = base.drop(columns=["lineage_source_provider", "replay_source_provider"])

    lat_index = base["lat_index"].to_numpy(dtype=np.int64)
    lon_index = base["lon_index"].to_numpy(dtype=np.int64)
    for key, grid in product_grids.items():
        column = f"{key}_depth_m"
        base[column] = grid[lat_index, lon_index].astype(np.float64)
        base[f"{key}_minus_ship_m"] = base[column] - base["ship_depth_m_positive_down"]
    add_consensus_columns(base)
    base["product_consensus_minus_ship_m"] = (
        base["product_consensus_median_depth_m"] - base["ship_depth_m_positive_down"]
    )
    base["family_consensus_minus_ship_m"] = (
        base["family_consensus_median_depth_m"] - base["ship_depth_m_positive_down"]
    )
    for year, fractions in tid_fractions.items():
        for group, grid in fractions.items():
            base[f"gebco_{year}_tid_{group}_fraction"] = grid[lat_index, lon_index].astype(np.float32)
    base["comparison_role"] = "qc_layer_c_diagnostic_only"
    base["reference_independence"] = "not_established"
    base["replay_difference_interpretation"] = np.where(
        base["raw_replay_result"].eq("different"),
        "documented_chunk_median_aggregation_difference_not_bad_ping_evidence",
        "exact_raw_replay",
    )
    validate_diagnostic_output_columns(base.columns)
    if len(base) != EXPECTED_CELL_COUNT or base["canonical_cell_id"].nunique() != EXPECTED_CELL_COUNT:
        raise ValueError("per-cell diagnostic row/key closure failed")
    return base.sort_values("canonical_cell_id").reset_index(drop=True)


def _metric_values(difference: np.ndarray) -> dict[str, Any]:
    values = np.asarray(difference, dtype=np.float64)
    finite = values[np.isfinite(values)]
    if len(finite) == 0:
        return {
            "count": 0,
            "bias_mean_m": np.nan,
            "median_difference_m": np.nan,
            "nmad_difference_m": np.nan,
            "mae_m": np.nan,
            "rmse_m": np.nan,
            "centered_rmse_m": np.nan,
            "abs_difference_p95_m": np.nan,
        }
    median = float(np.median(finite))
    return {
        "count": int(len(finite)),
        "bias_mean_m": float(np.mean(finite)),
        "median_difference_m": median,
        "nmad_difference_m": float(NMAD_SCALE * np.median(np.abs(finite - median))),
        "mae_m": float(np.mean(np.abs(finite))),
        "rmse_m": float(np.sqrt(np.mean(np.square(finite)))),
        "centered_rmse_m": float(np.sqrt(np.mean(np.square(finite - np.mean(finite))))),
        "abs_difference_p95_m": float(np.percentile(np.abs(finite), 95)),
    }


def build_product_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    comparisons = [
        (column.removesuffix("_depth_m"), f"{column.removesuffix('_depth_m')}_minus_ship_m", column)
        for column in PRODUCT_DEPTH_COLUMNS
    ] + [
        ("product_consensus", "product_consensus_minus_ship_m", "product_consensus_median_depth_m"),
        ("family_consensus", "family_consensus_minus_ship_m", "family_consensus_median_depth_m"),
    ]
    rows: list[dict[str, Any]] = []
    strata = [("all", "all", frame)] + [
        ("source_provider", str(provider), group)
        for provider, group in frame.groupby("source_provider", sort=True)
    ]
    for stratum, stratum_value, group in strata:
        for reference, difference_column, depth_column in comparisons:
            row = {
                "reference": reference,
                "stratum": stratum,
                "stratum_value": stratum_value,
                "requested_count": int(len(group)),
                "valid_fraction": float(np.isfinite(group[difference_column]).mean()),
                "nonpositive_reference_depth_count": int(
                    (np.isfinite(group[depth_column]) & group[depth_column].le(0)).sum()
                ),
                "difference_sign": "reference_depth_minus_ship_depth",
                "evidence_role": "diagnostic_product_consistency_not_independent_accuracy",
            }
            row.update(_metric_values(group[difference_column].to_numpy(dtype=np.float64)))
            rows.append(row)
    return pd.DataFrame(rows)


def _query_ocean_distances(
    lon: np.ndarray,
    lat: np.ndarray,
    ocean_mask: np.ndarray,
    cohort: pd.DataFrame,
    chunk_size: int,
    logger: logging.Logger,
) -> np.ndarray:
    control_xyz = lonlat_to_unit_xyz(cohort["lon"].to_numpy(), cohort["lat"].to_numpy())
    tree = cKDTree(control_xyz)
    ocean_i, ocean_j = np.nonzero(ocean_mask)
    result = np.full(ocean_mask.shape, np.nan, dtype=np.float32)
    distances = np.empty(len(ocean_i), dtype=np.float64)
    for start in range(0, len(ocean_i), chunk_size):
        stop = min(start + chunk_size, len(ocean_i))
        queries = lonlat_to_unit_xyz(lon[ocean_j[start:stop]], lat[ocean_i[start:stop]])
        chord, _ = tree.query(queries, k=1, workers=-1)
        distances[start:stop] = _chord_to_great_circle_km(chord)
        logger.info("nearest-distance progress=%d/%d", stop, len(ocean_i))
    result[ocean_i, ocean_j] = distances.astype(np.float32)
    return result


def _weighted_fraction(mask: np.ndarray, area_by_lat: np.ndarray, ocean_mask: np.ndarray) -> float:
    weights = np.broadcast_to(area_by_lat[:, None], ocean_mask.shape)
    return float(weights[mask & ocean_mask].sum() / weights[ocean_mask].sum())


def build_coverage_products(
    domain: dict[str, Any],
    land_mask: np.ndarray,
    cohort: pd.DataFrame,
    replay: pd.DataFrame,
    thresholds_km: list[float],
    query_chunk_size: int,
    logger: logging.Logger,
) -> tuple[xr.Dataset, pd.DataFrame, dict[str, Any]]:
    ocean_mask = ~land_mask
    occupied = np.zeros(EXPECTED_GRID_SHAPE, dtype=bool)
    occupied[
        cohort["lat_index"].to_numpy(dtype=np.int64),
        cohort["lon_index"].to_numpy(dtype=np.int64),
    ] = True
    if int(occupied.sum()) != EXPECTED_CELL_COUNT or bool((occupied & land_mask).any()):
        raise ValueError("audited-cell occupancy does not close on frozen ocean mask")
    distances = _query_ocean_distances(
        domain["lon"], domain["lat"], ocean_mask, cohort, query_chunk_size, logger
    )
    if float(np.nanmax(distances[occupied])) > 1e-5:
        raise ValueError("occupied cells do not have zero nearest-control distance")
    area_by_lat = cell_area_km2(domain["lat"], int(domain["increment_arcmin"]))
    area_grid = np.broadcast_to(area_by_lat[:, None], EXPECTED_GRID_SHAPE)

    block_shape = (25, 60, 20, 60)
    block_counts = occupied.reshape(block_shape).sum(axis=(1, 3)).astype(np.int32)
    expanded_block_counts = np.repeat(np.repeat(block_counts, 60, axis=0), 60, axis=1)

    block_rows: list[dict[str, Any]] = []
    for lat_block in range(25):
        for lon_block in range(20):
            lat_slice = slice(lat_block * 60, (lat_block + 1) * 60)
            lon_slice = slice(lon_block * 60, (lon_block + 1) * 60)
            block_ocean = ocean_mask[lat_slice, lon_slice]
            block_occupied = occupied[lat_slice, lon_slice]
            block_distance = distances[lat_slice, lon_slice][block_ocean]
            block_area = area_grid[lat_slice, lon_slice]
            ocean_count = int(block_ocean.sum())
            occupied_count = int(block_occupied.sum())
            row = {
                "block_id": f"lon{105 + lon_block:03d}_lat{lat_block:02d}",
                "west": 105.0 + lon_block,
                "east": 106.0 + lon_block,
                "south": float(lat_block),
                "north": float(lat_block + 1),
                "ocean_cell_count": ocean_count,
                "audited_ship_cell_count": occupied_count,
                "cell_coverage_fraction": float(occupied_count / ocean_count) if ocean_count else np.nan,
                "ocean_area_km2": float(block_area[block_ocean].sum()),
                "audited_ship_cell_area_km2": float(block_area[block_occupied].sum()),
            }
            row["area_coverage_fraction"] = (
                row["audited_ship_cell_area_km2"] / row["ocean_area_km2"]
                if row["ocean_area_km2"] else np.nan
            )
            for percentile in (50, 90, 95, 99):
                row[f"nearest_control_p{percentile}_km"] = (
                    float(np.percentile(block_distance, percentile)) if len(block_distance) else np.nan
                )
            row["nearest_control_max_km"] = float(np.max(block_distance)) if len(block_distance) else np.nan
            block_rows.append(row)

    ocean_distance = distances[ocean_mask].astype(np.float64)
    ocean_area = float(area_grid[ocean_mask].sum())
    occupied_area = float(area_grid[occupied].sum())
    threshold_rows = []
    for threshold in thresholds_km:
        within = np.isfinite(distances) & (distances <= float(threshold) + 1e-7)
        threshold_rows.append({
            "threshold_km": float(threshold),
            "ocean_cell_count": int((within & ocean_mask).sum()),
            "ocean_cell_fraction": float((within & ocean_mask).sum() / ocean_mask.sum()),
            "ocean_area_km2": float(area_grid[within & ocean_mask].sum()),
            "ocean_area_fraction": _weighted_fraction(within, area_by_lat, ocean_mask),
        })
    summary = {
        "domain": {
            "west": float(domain["west"]),
            "east": float(domain["east"]),
            "south": float(domain["south"]),
            "north": float(domain["north"]),
            "increment_arcmin": int(domain["increment_arcmin"]),
            "shape": list(EXPECTED_GRID_SHAPE),
        },
        "strict_ocean_cell_count": int(ocean_mask.sum()),
        "land_or_mixed_cell_count": int(land_mask.sum()),
        "audited_ship_cell_count": int(occupied.sum()),
        "cell_coverage_fraction": float(occupied.sum() / ocean_mask.sum()),
        "strict_ocean_area_km2": ocean_area,
        "audited_ship_cell_area_km2": occupied_area,
        "area_coverage_fraction": float(occupied_area / ocean_area),
        "nearest_control_distance_km": {
            f"p{percentile}": float(np.percentile(ocean_distance, percentile))
            for percentile in (50, 90, 95, 99)
        } | {"max": float(np.max(ocean_distance))},
        "distance_coverage": threshold_rows,
        "source_provider_cell_counts": cohort["source_provider"].value_counts().to_dict(),
        "raw_point_count_sum": int(replay["raw_point_count"].sum()),
        "raw_point_count_median_per_observed_cell": float(replay["raw_point_count"].median()),
        "track_spacing_status": "not_computed_mrar_line_and_time_identity_not_recoverable",
    }

    dataset = xr.Dataset(
        {
            "frozen_land_mask": (("lat", "lon"), land_mask),
            "audited_ship_cell": (("lat", "lon"), occupied),
            "nearest_audited_ship_cell_km": (("lat", "lon"), distances),
            "control_count_1deg": (("lat", "lon"), expanded_block_counts),
            "cell_area_km2": (("lat",), area_by_lat.astype(np.float32)),
        },
        coords={"lat": domain["lat"], "lon": domain["lon"]},
        attrs={
            "title": "SCS audited ship-cell spatial support",
            "coverage_role": "PINN applicability-domain planning only",
            "cohort_mutation": "forbidden",
            "land_mask_contract": "frozen downstream GEBCO 2024 context; land_fraction > 0",
            "distance_method": "unit-sphere cKDTree chord converted to great-circle distance",
            "earth_radius_km": EARTH_RADIUS_KM,
        },
    )
    dataset["nearest_audited_ship_cell_km"].attrs.update({"units": "km"})
    dataset["cell_area_km2"].attrs.update({"units": "km2"})
    return dataset, pd.DataFrame(block_rows), summary


def tid_composition_rows(
    year: int,
    fine: np.ndarray,
    factor: int,
    groups: dict[str, Iterable[int]],
    ocean_mask: np.ndarray,
) -> list[dict[str, Any]]:
    code_to_group = _tid_code_to_group(groups)
    blocks = fine.reshape(
        fine.shape[0] // factor,
        factor,
        fine.shape[1] // factor,
        factor,
    )
    rows = []
    for code in sorted(int(value) for value in np.unique(fine)):
        counts_by_cell = (blocks == code).sum(axis=(1, 3))
        rows.append({
            "year": int(year),
            "tid_code": code,
            "tid_group": code_to_group[code],
            "fine_pixel_count_full_domain": int(counts_by_cell.sum()),
            "fine_pixel_count_within_frozen_ocean_cells": int(counts_by_cell[ocean_mask].sum()),
            "one_minute_ocean_cells_with_any_code": int(((counts_by_cell > 0) & ocean_mask).sum()),
            "interpretation": "composition_only_not_independence_proof",
        })
    return rows


def add_tid_coverage_summary(
    summary: dict[str, Any],
    tid_fractions: dict[int, dict[str, np.ndarray]],
    ocean_mask: np.ndarray,
) -> None:
    result: dict[str, Any] = {}
    for year, fractions in sorted(tid_fractions.items()):
        direct = fractions["direct_measurement"]
        gravity = fractions["gravity_guided_or_predicted"]
        result[str(year)] = {
            "direct_measurement_any_ocean_cells": int(((direct > 0) & ocean_mask).sum()),
            "direct_measurement_majority_ocean_cells": int(((direct >= 0.5) & ocean_mask).sum()),
            "direct_measurement_complete_ocean_cells": int(((direct == 1.0) & ocean_mask).sum()),
            "gravity_guided_any_ocean_cells": int(((gravity > 0) & ocean_mask).sum()),
            "gravity_guided_majority_ocean_cells": int(((gravity >= 0.5) & ocean_mask).sum()),
            "denominator_frozen_ocean_cells": int(ocean_mask.sum()),
            "interpretation": "TID composition only; not verified ship identity or independence",
        }
    summary["gebco_tid_coverage"] = result


def build_product_context_dataset(
    domain: dict[str, Any],
    land_mask: np.ndarray,
    product_grids: dict[str, np.ndarray],
    tid_fractions: dict[int, dict[str, np.ndarray]],
) -> xr.Dataset:
    variables: dict[str, Any] = {
        "frozen_land_mask": (("lat", "lon"), land_mask),
    }
    for key, values in product_grids.items():
        variables[f"{key}_depth_m"] = (("lat", "lon"), values.astype(np.float32))
    for year, fractions in tid_fractions.items():
        for group, values in fractions.items():
            variables[f"gebco_{year}_tid_{group}_fraction"] = (
                ("lat", "lon"), values.astype(np.float32)
            )
    dataset = xr.Dataset(
        variables,
        coords={"lat": domain["lat"], "lon": domain["lon"]},
        attrs={
            "title": "SCS mature-product and TID diagnostic context",
            "grid_registration": "pixel",
            "depth_sign": "positive_down",
            "reference_independence": "not_established",
            "comparison_role": "QC layer C diagnostic only",
            "label_filtering": "forbidden",
        },
    )
    for key in product_grids:
        dataset[f"{key}_depth_m"].attrs.update({"units": "m", "positive": "down"})
    for name in dataset.data_vars:
        if "_tid_" in name:
            dataset[name].attrs.update({
                "units": "1",
                "interpretation": "GEBCO TID composition only, not independence proof",
            })
    return dataset


def build_report(
    run_id: str,
    inputs: dict[str, dict[str, Any]],
    coverage: dict[str, Any],
    metrics: pd.DataFrame,
) -> str:
    input_rows = "\n".join(
        f"| `{role}` | `{record['path']}` | `{record['sha256']}` |"
        for role, record in inputs.items()
    )
    overall = metrics[metrics["stratum"].eq("all")]
    metric_rows = "\n".join(
        f"| `{row.reference}` | {int(row.count):,} | {row.median_difference_m:.6g} | "
        f"{row.nmad_difference_m:.6g} | {row.mae_m:.6g} | {row.rmse_m:.6g} | "
        f"{row.centered_rmse_m:.6g} |"
        for row in overall.itertuples(index=False)
    )
    tid_lines = []
    for year, values in coverage["gebco_tid_coverage"].items():
        tid_lines.append(
            f"| {year} | {values['direct_measurement_any_ocean_cells']:,} | "
            f"{values['direct_measurement_majority_ocean_cells']:,} | "
            f"{values['direct_measurement_complete_ocean_cells']:,} | "
            f"{values['gravity_guided_any_ocean_cells']:,} | "
            f"{values['gravity_guided_majority_ocean_cells']:,} |"
        )
    distance_lines = "\n".join(
        f"| {row['threshold_km']:.0f} | {row['ocean_cell_count']:,} | "
        f"{row['ocean_cell_fraction']:.6f} | {row['ocean_area_fraction']:.6f} |"
        for row in coverage["distance_coverage"]
    )
    return f"""# SCS mature-product consistency and coverage audit

Run ID: `{run_id}`

## Evidence boundary

This run compares exactly 174,965 audited ship cells with seven mature
bathymetry products and describes their support over the frozen SCS ocean
domain. It did not read downstream predictions, residuals, model errors,
metrics, `external_samples.parquet`, `roles`, or `outlier97`.

Product agreement is QC layer C and is diagnostic only. No cell was removed,
relabelled, reweighted, or made eligible/ineligible. GEBCO TID describes source
type composition and does not establish source identity or independence. The
coverage result informs PINN applicability-domain planning and does not modify
an existing cohort or split.

## Frozen inputs

| Role | Absolute path | SHA256 |
|---|---|---|
{input_rows}

## Coverage

- Frozen grid: 1 arc-minute, 1200 x 1500 cells, `[105, 125) E x [0, 25) N`.
- Strict-ocean cells: {coverage['strict_ocean_cell_count']:,}.
- Audited ship cells: {coverage['audited_ship_cell_count']:,}.
- Cell coverage fraction: {coverage['cell_coverage_fraction']:.8f}.
- Area-weighted coverage fraction: {coverage['area_coverage_fraction']:.8f}.
- Nearest-control distance P50/P90/P95/P99/max: """ \
        f"{coverage['nearest_control_distance_km']['p50']:.3f} / " \
        f"{coverage['nearest_control_distance_km']['p90']:.3f} / " \
        f"{coverage['nearest_control_distance_km']['p95']:.3f} / " \
        f"{coverage['nearest_control_distance_km']['p99']:.3f} / " \
        f"{coverage['nearest_control_distance_km']['max']:.3f} km.\n\n" \
        f"""| Radius (km) | Ocean cells within radius | Cell fraction | Area fraction |
|---:|---:|---:|---:|
{distance_lines}

Track spacing is not reported because MRAR line/time identity is not
recoverable.

## Product consistency at ship cells

Difference sign is `reference depth - ship depth`; positive means the
reference product is deeper. Absolute statistics have limited confirmatory
meaning because ship vertical datums remain unknown. Centered RMSE is reported
separately. GEBCO-family and SRTM-derived products are dependent, so neither
the seven-product nor family-balanced consensus is independent truth.

| Reference | Valid cells | Median diff (m) | Difference NMAD (m) | MAE (m) | RMSE (m) | Centered RMSE (m) |
|---|---:|---:|---:|---:|---:|---:|
{metric_rows}

No 3STD flag or product-derived PINN weight is emitted.

## GEBCO TID composition on the frozen ocean domain

| Year | Any direct | Majority direct | Complete direct | Any gravity-guided | Majority gravity-guided |
|---:|---:|---:|---:|---:|---:|
{chr(10).join(tid_lines)}

`direct_measurement` follows the configured GEBCO TID code group 10-17; it is
not synonymous with independently verified ship data. Exact per-code counts
are in `tid_composition.tsv`.

## Replay registration

The diagnostic table retains all 174,965 replay rows: 174,913 exact and 52
different at 1e-9 m. The 52 differences retain the documented cross-batch
weighted chunk-median interpretation and are not labelled as bad pings.
"""


def _setup_logging(run_dir: Path) -> logging.Logger:
    logger = logging.getLogger("scs_product_consistency_coverage")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = logging.FileHandler(run_dir / "audit.log", mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def _estimate_logger() -> logging.Logger:
    logger = logging.getLogger("scs_product_consistency_coverage_estimate")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    return logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--confirm-audit", action="store_true")
    parser.add_argument("--estimate-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if Path.cwd().resolve() != REPO_ROOT:
        raise SystemExit(f"run from repository root: cd {REPO_ROOT}")
    if not args.estimate_only and not args.confirm_audit:
        raise SystemExit("refusing full audit without --confirm-audit")
    config_path = args.config.resolve()
    config = _load_yaml(config_path)
    domain = _domain(config)

    run_dir = args.output_root.resolve() / args.run_id
    if not args.estimate_only:
        run_dir.mkdir(parents=True, exist_ok=False)
        logger = _setup_logging(run_dir)
    else:
        logger = _estimate_logger()
    logger.info("argv=%s", sys.argv)
    logger.info("config=%s", config_path)

    inputs = validate_frozen_inputs(config, logger)
    union_path = Path(inputs["downstream_union"]["path"])
    lineage_path = Path(inputs["cell_lineage"]["path"])
    replay_path = Path(inputs["raw_to_cell_replay"]["path"])
    frozen_context_path = Path(inputs["frozen_scs_context"]["path"])
    cohort = load_frozen_cohort(union_path, domain)
    lineage, replay = load_lineage_and_replay(lineage_path, replay_path, cohort)
    land_mask = load_frozen_land_mask(frozen_context_path, domain)
    if bool(land_mask[
        cohort["lat_index"].to_numpy(dtype=np.int64),
        cohort["lon_index"].to_numpy(dtype=np.int64),
    ].any()):
        raise ValueError("one or more frozen cohort cells falls on frozen land/mixed mask")
    if args.estimate_only:
        estimate = {
            "status": "estimate_only_pass",
            "cell_count": len(cohort),
            "source_counts": cohort["source_provider"].value_counts().to_dict(),
            "grid_shape": list(EXPECTED_GRID_SHAPE),
            "strict_ocean_cell_count": int((~land_mask).sum()),
            "products": [product["key"] for product in config["products"]],
            "tid_years": [int(tid["year"]) for tid in config["tids"]],
            "input_bytes": int(sum(record["size_bytes"] for record in inputs.values())),
            "downstream_columns_read": sorted(UNION_COLUMNS),
            "downstream_model_error_read": False,
        }
        print(json.dumps(estimate, indent=2, sort_keys=True))
        return 0

    started = time.monotonic()
    product_grids: dict[str, np.ndarray] = {}
    for product in config["products"]:
        logger.info("loading product=%s", product["key"])
        product_grids[product["key"]] = load_product_grid(product, domain)
        logger.info(
            "loaded product=%s finite=%d nonpositive=%d",
            product["key"],
            int(np.isfinite(product_grids[product["key"]]).sum()),
            int((np.isfinite(product_grids[product["key"]]) & (product_grids[product["key"]] <= 0)).sum()),
        )
    if [f"{key}_depth_m" for key in product_grids] != PRODUCT_DEPTH_COLUMNS:
        raise ValueError("configured product order/keys drift from consensus contract")

    groups = {name: [int(code) for code in codes] for name, codes in config["tid_groups"].items()}
    validate_tid_groups(groups)
    tid_fractions: dict[int, dict[str, np.ndarray]] = {}
    tid_rows: list[dict[str, Any]] = []
    for tid in config["tids"]:
        year = int(tid["year"])
        logger.info("loading GEBCO TID year=%d", year)
        fine, fractions, _, factor = load_tid_grid(tid, domain, groups)
        tid_fractions[year] = fractions
        tid_rows.extend(tid_composition_rows(year, fine, factor, groups, ~land_mask))
        del fine

    diagnostics = build_cell_diagnostics(cohort, lineage, replay, product_grids, tid_fractions)
    metrics = build_product_metrics(diagnostics)
    coverage_dataset, coverage_blocks, coverage_summary = build_coverage_products(
        domain,
        land_mask,
        cohort,
        replay,
        [float(value) for value in config["coverage"]["distance_thresholds_km"]],
        int(config["coverage"]["query_chunk_size"]),
        logger,
    )
    add_tid_coverage_summary(coverage_summary, tid_fractions, ~land_mask)
    product_context = build_product_context_dataset(domain, land_mask, product_grids, tid_fractions)
    tid_table = pd.DataFrame(tid_rows)

    artifact_paths = {
        "product_consistency_by_cell": run_dir / "product_consistency_by_cell.parquet",
        "scs_product_context_1min": run_dir / "scs_product_context_1min.nc",
        "coverage_grid_1min": run_dir / "coverage_grid_1min.nc",
        "coverage_by_block_1deg": run_dir / "coverage_by_block_1deg.parquet",
        "product_metrics": run_dir / "product_metrics.tsv",
        "tid_composition": run_dir / "tid_composition.tsv",
        "coverage_summary": run_dir / "coverage_summary.json",
        "audit_report": run_dir / "audit_report.md",
    }
    _atomic_parquet(diagnostics, artifact_paths["product_consistency_by_cell"])
    _atomic_netcdf(product_context, artifact_paths["scs_product_context_1min"])
    _atomic_netcdf(coverage_dataset, artifact_paths["coverage_grid_1min"])
    _atomic_parquet(coverage_blocks, artifact_paths["coverage_by_block_1deg"])
    _atomic_tsv(metrics, artifact_paths["product_metrics"])
    _atomic_tsv(tid_table, artifact_paths["tid_composition"])
    _atomic_text(json.dumps(coverage_summary, indent=2, sort_keys=True) + "\n", artifact_paths["coverage_summary"])
    report = build_report(args.run_id, inputs, coverage_summary, metrics)
    _atomic_text(report, artifact_paths["audit_report"])

    outputs = {
        role: {
            "path": str(path),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for role, path in artifact_paths.items()
    }
    manifest = {
        "run_id": args.run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": {
            "path": str(config_path),
            "sha256": sha256_file(config_path),
        },
        "inputs": inputs,
        "outputs": outputs,
        "code": {
            "driver_path": str(SCRIPT_PATH),
            "driver_sha256": sha256_file(SCRIPT_PATH),
        },
        "domain": {
            key: domain[key]
            for key in ("west", "east", "south", "north", "increment_arcmin", "expected_lon_count", "expected_lat_count")
        },
        "products": [product["key"] for product in config["products"]],
        "tid_years": [int(tid["year"]) for tid in config["tids"]],
        "tid_groups": groups,
        "distance_thresholds_km": [float(value) for value in config["coverage"]["distance_thresholds_km"]],
        "downstream_columns_read": sorted(UNION_COLUMNS),
        "downstream_model_error_read": False,
        "error_derived_cohort_columns_read": False,
        "comparison_role": "qc_layer_c_diagnostic_only",
        "reference_independence": "not_established",
        "tid_independence_proof": False,
        "cohort_mutated": False,
        "row_weight_generated": False,
        "row_exclusion_generated": False,
        "three_std_filter_applied": False,
        "cell_count": len(diagnostics),
        "strict_ocean_cell_count": int((~land_mask).sum()),
        "replay_counts": diagnostics["raw_replay_result"].value_counts().to_dict(),
        "elapsed_seconds": time.monotonic() - started,
    }
    manifest_path = run_dir / "audit_manifest.json"
    _atomic_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", manifest_path)
    logger.info("completed run_dir=%s elapsed_s=%.1f", run_dir, time.monotonic() - started)
    logger.info("manifest_sha256=%s", sha256_file(manifest_path))
    print(f"run_dir={run_dir}")
    print(f"manifest_sha256={sha256_file(manifest_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
