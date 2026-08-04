#!/usr/bin/env python3
"""Independently verify persisted SCS product-consistency/coverage artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr
from scipy.spatial import cKDTree


EXPECTED_CELL_COUNT = 174_965
EXPECTED_SOURCE_COUNTS = {"mrar": 165_966, "jamstec": 8_999}
EXPECTED_REPLAY_COUNTS = {"exact": 174_913, "different": 52}
EXPECTED_GRID_SHAPE = (1500, 1200)
EXPECTED_OCEAN_CELL_COUNT = 1_288_723
EARTH_RADIUS_KM = 6371.0088
NMAD_SCALE = 1.4826

PRODUCT_KEYS = [
    "gebco_2024",
    "gebco_2025",
    "gebco_2026",
    "etopo_2022",
    "srtm15_v2_7",
    "topo_25_1",
    "sdust_2023",
]
PRODUCT_COLUMNS = [f"{key}_depth_m" for key in PRODUCT_KEYS]
GEBCO_COLUMNS = [f"gebco_{year}_depth_m" for year in (2024, 2025, 2026)]
FORBIDDEN_COLUMN_TOKENS = {
    "weight",
    "eligible",
    "eligibility",
    "exclude",
    "exclusion",
    "decision",
    "outlier",
    "3std",
}


def sha256_file(path: Path, chunk_size: int = 16 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(value: Any, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def row_nmad(values: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        median = np.nanmedian(values, axis=1)
        return NMAD_SCALE * np.nanmedian(np.abs(values - median[:, None]), axis=1)


def target_centers(domain: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    increment = float(domain["increment_arcmin"]) / 60.0
    lon = float(domain["west"]) + (np.arange(int(domain["expected_lon_count"])) + 0.5) * increment
    lat = float(domain["south"]) + (np.arange(int(domain["expected_lat_count"])) + 0.5) * increment
    return lon, lat


def cell_area_km2(lat: np.ndarray, increment_arcmin: int) -> np.ndarray:
    half = np.deg2rad(increment_arcmin / 120.0)
    center = np.deg2rad(np.asarray(lat, dtype=np.float64))
    delta_lon = np.deg2rad(increment_arcmin / 60.0)
    return EARTH_RADIUS_KM**2 * delta_lon * (
        np.sin(center + half) - np.sin(center - half)
    )


def unit_xyz(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    lon_rad = np.deg2rad(np.asarray(lon, dtype=np.float64))
    lat_rad = np.deg2rad(np.asarray(lat, dtype=np.float64))
    cos_lat = np.cos(lat_rad)
    return np.column_stack([
        cos_lat * np.cos(lon_rad),
        cos_lat * np.sin(lon_rad),
        np.sin(lat_rad),
    ])


def great_circle_from_chord(chord: np.ndarray) -> np.ndarray:
    return 2.0 * np.arcsin(np.clip(np.asarray(chord) / 2.0, 0.0, 1.0)) * EARTH_RADIUS_KM


def assert_close(name: str, actual: Any, expected: Any, atol: float = 1e-9) -> None:
    if not np.isclose(float(actual), float(expected), rtol=0, atol=atol, equal_nan=True):
        raise AssertionError(f"{name}: {actual} != {expected}")


def verify_consensus(frame: pd.DataFrame) -> dict[str, Any]:
    products = frame[PRODUCT_COLUMNS].to_numpy(dtype=np.float64)
    with np.errstate(invalid="ignore"):
        product_median = np.nanmedian(products, axis=1)
    if not np.allclose(product_median, frame["product_consensus_median_depth_m"], rtol=0, atol=1e-9):
        raise AssertionError("seven-product consensus median mismatch")
    if not np.allclose(row_nmad(products), frame["product_consensus_nmad_m"], rtol=0, atol=1e-9):
        raise AssertionError("seven-product consensus NMAD mismatch")
    if not np.array_equal(np.isfinite(products).sum(axis=1), frame["product_consensus_count"]):
        raise AssertionError("seven-product finite count mismatch")

    gebco = frame[GEBCO_COLUMNS].to_numpy(dtype=np.float64)
    with np.errstate(invalid="ignore"):
        gebco_median = np.nanmedian(gebco, axis=1)
    if not np.allclose(gebco_median, frame["gebco_family_median_depth_m"], rtol=0, atol=1e-9):
        raise AssertionError("GEBCO-family median mismatch")
    families = np.column_stack([
        gebco_median,
        frame["etopo_2022_depth_m"],
        frame["srtm15_v2_7_depth_m"],
        frame["topo_25_1_depth_m"],
        frame["sdust_2023_depth_m"],
    ])
    with np.errstate(invalid="ignore"):
        family_median = np.nanmedian(families, axis=1)
    if not np.allclose(family_median, frame["family_consensus_median_depth_m"], rtol=0, atol=1e-9):
        raise AssertionError("family-balanced consensus median mismatch")
    if not np.allclose(row_nmad(families), frame["family_consensus_nmad_m"], rtol=0, atol=1e-9):
        raise AssertionError("family-balanced consensus NMAD mismatch")
    if not np.array_equal(np.isfinite(families).sum(axis=1), frame["family_consensus_count"]):
        raise AssertionError("family-balanced finite count mismatch")

    ship = frame["ship_depth_m_positive_down"].to_numpy(dtype=np.float64)
    for key in PRODUCT_KEYS:
        expected = frame[f"{key}_depth_m"].to_numpy(dtype=np.float64) - ship
        if not np.allclose(expected, frame[f"{key}_minus_ship_m"], rtol=0, atol=1e-9, equal_nan=True):
            raise AssertionError(f"{key} signed difference mismatch")
    return {
        "seven_product_rows_recomputed": len(frame),
        "family_balanced_rows_recomputed": len(frame),
    }


def metric_values(values: np.ndarray) -> dict[str, float | int]:
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
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


def verify_metrics(frame: pd.DataFrame, metrics: pd.DataFrame) -> int:
    difference_columns = {
        **{key: f"{key}_minus_ship_m" for key in PRODUCT_KEYS},
        "product_consensus": "product_consensus_minus_ship_m",
        "family_consensus": "family_consensus_minus_ship_m",
    }
    checked = 0
    for row in metrics.itertuples(index=False):
        group = frame if row.stratum == "all" else frame[frame[row.stratum].astype(str).eq(str(row.stratum_value))]
        expected = metric_values(group[difference_columns[row.reference]].to_numpy(dtype=np.float64))
        if int(row.requested_count) != len(group):
            raise AssertionError("product metric requested count mismatch")
        for key, value in expected.items():
            if key == "count":
                if int(getattr(row, key)) != value:
                    raise AssertionError(f"product metric count mismatch: {row.reference}")
            else:
                assert_close(f"metric {row.reference}/{row.stratum_value}/{key}", getattr(row, key), value, 1e-8)
        checked += 1
    return checked


def read_tid_scs(path: Path, domain: dict[str, Any]) -> np.ndarray:
    with xr.open_dataset(path, decode_cf=False, mask_and_scale=False) as dataset:
        lon = np.asarray(dataset["lon"].values, dtype=np.float64)
        lat = np.asarray(dataset["lat"].values, dtype=np.float64)
        lon_indices = np.flatnonzero((lon >= float(domain["west"])) & (lon < float(domain["east"])))
        lat_indices = np.flatnonzero((lat >= float(domain["south"])) & (lat < float(domain["north"])))
        values = dataset["tid"].isel(
            lat=slice(int(lat_indices[0]), int(lat_indices[-1]) + 1),
            lon=slice(int(lon_indices[0]), int(lon_indices[-1]) + 1),
        ).values
        selected_lon = lon[lon_indices]
        selected_lat = lat[lat_indices]
    if selected_lon[0] > selected_lon[-1]:
        values = values[:, ::-1]
    if selected_lat[0] > selected_lat[-1]:
        values = values[::-1, :]
    return np.asarray(values, dtype=np.int16)


def verify_tid(
    manifest: dict[str, Any],
    product_context: xr.Dataset,
    tid_table: pd.DataFrame,
) -> dict[str, Any]:
    groups = {name: [int(value) for value in codes] for name, codes in manifest["tid_groups"].items()}
    code_group = {code: name for name, codes in groups.items() for code in codes}
    years_checked = []
    for year in manifest["tid_years"]:
        fine = read_tid_scs(Path(manifest["inputs"][f"tid_{year}"]["path"]), manifest["domain"])
        observed, counts = np.unique(fine, return_counts=True)
        actual = {int(code): int(count) for code, count in zip(observed, counts)}
        recorded_rows = tid_table[tid_table["year"].eq(int(year))]
        recorded = dict(zip(recorded_rows["tid_code"].astype(int), recorded_rows["fine_pixel_count_full_domain"].astype(int)))
        if actual != recorded:
            raise AssertionError(f"TID {year} exact code count mismatch")
        if set(actual) - set(code_group):
            raise AssertionError(f"TID {year} contains unconfigured codes")
        blocks = fine.reshape(EXPECTED_GRID_SHAPE[0], 4, EXPECTED_GRID_SHAPE[1], 4)
        fraction_names = []
        for group, codes in groups.items():
            expected_fraction = np.isin(blocks, np.asarray(codes)).mean(axis=(1, 3))
            name = f"gebco_{year}_tid_{group}_fraction"
            fraction_names.append(name)
            if not np.allclose(expected_fraction, product_context[name].values, rtol=0, atol=1e-7):
                raise AssertionError(f"TID {year} grouped fraction mismatch: {group}")
        closure = sum(product_context[name].values for name in fraction_names)
        if not np.allclose(closure, 1.0, rtol=0, atol=1e-7):
            raise AssertionError(f"TID {year} persisted group closure mismatch")
        years_checked.append(int(year))
    return {"years_checked": years_checked, "exact_code_rows": len(tid_table)}


def verify_coverage(
    manifest: dict[str, Any],
    frame: pd.DataFrame,
    coverage: xr.Dataset,
    blocks: pd.DataFrame,
    summary: dict[str, Any],
) -> dict[str, Any]:
    domain = manifest["domain"]
    lon, lat = target_centers(domain)
    if coverage.sizes.get("lat") != EXPECTED_GRID_SHAPE[0] or coverage.sizes.get("lon") != EXPECTED_GRID_SHAPE[1]:
        raise AssertionError("coverage grid shape mismatch")
    if not np.allclose(coverage["lon"].values, lon, rtol=0, atol=2e-9):
        raise AssertionError("coverage longitude mismatch")
    if not np.allclose(coverage["lat"].values, lat, rtol=0, atol=2e-9):
        raise AssertionError("coverage latitude mismatch")
    land = coverage["frozen_land_mask"].values.astype(bool)
    ocean = ~land
    occupied = coverage["audited_ship_cell"].values.astype(bool)
    distances = coverage["nearest_audited_ship_cell_km"].values.astype(np.float64)
    if int(ocean.sum()) != EXPECTED_OCEAN_CELL_COUNT:
        raise AssertionError("strict-ocean count mismatch")
    if int(occupied.sum()) != EXPECTED_CELL_COUNT or bool((occupied & land).any()):
        raise AssertionError("occupied-cell closure mismatch")
    expected_occupied = np.zeros(EXPECTED_GRID_SHAPE, dtype=bool)
    expected_occupied[
        frame["lat_index"].to_numpy(dtype=np.int64),
        frame["lon_index"].to_numpy(dtype=np.int64),
    ] = True
    if not np.array_equal(occupied, expected_occupied):
        raise AssertionError("coverage occupancy differs from per-cell diagnostic")
    if not np.isnan(distances[land]).all() or not np.isfinite(distances[ocean]).all():
        raise AssertionError("coverage distance land/ocean nodata contract failed")
    if float(np.max(distances[occupied])) > 1e-5:
        raise AssertionError("occupied cells have non-zero persisted distance")

    expected_area = cell_area_km2(lat, int(domain["increment_arcmin"]))
    if not np.allclose(expected_area, coverage["cell_area_km2"].values, rtol=0, atol=2e-6):
        raise AssertionError("cell area mismatch")
    area_grid = np.broadcast_to(expected_area[:, None], EXPECTED_GRID_SHAPE)
    assert_close("summary cell coverage", summary["cell_coverage_fraction"], occupied.sum() / ocean.sum(), 1e-12)
    assert_close(
        "summary area coverage",
        summary["area_coverage_fraction"],
        area_grid[occupied].sum() / area_grid[ocean].sum(),
        1e-9,
    )

    controls = unit_xyz(frame["lon"].to_numpy(), frame["lat"].to_numpy())
    tree = cKDTree(controls)
    ocean_i, ocean_j = np.nonzero(ocean)
    recomputed = np.empty(len(ocean_i), dtype=np.float64)
    for start in range(0, len(ocean_i), 200_000):
        stop = min(start + 200_000, len(ocean_i))
        query = unit_xyz(lon[ocean_j[start:stop]], lat[ocean_i[start:stop]])
        chord, _ = tree.query(query, k=1, workers=-1)
        recomputed[start:stop] = great_circle_from_chord(chord)
    if not np.allclose(recomputed, distances[ocean], rtol=0, atol=2e-4):
        raise AssertionError("full-ocean nearest distance mismatch")

    threshold_by_value = {float(row["threshold_km"]): row for row in summary["distance_coverage"]}
    for threshold in manifest["distance_thresholds_km"]:
        within = recomputed <= float(threshold) + 1e-7
        row = threshold_by_value[float(threshold)]
        if int(row["ocean_cell_count"]) != int(within.sum()):
            raise AssertionError(f"distance coverage cell count mismatch at {threshold} km")
        assert_close(
            f"distance coverage cell fraction at {threshold}",
            row["ocean_cell_fraction"],
            within.mean(),
            1e-12,
        )
        within_grid = np.zeros(EXPECTED_GRID_SHAPE, dtype=bool)
        within_grid[ocean_i, ocean_j] = within
        assert_close(
            f"distance coverage area fraction at {threshold}",
            row["ocean_area_fraction"],
            area_grid[within_grid].sum() / area_grid[ocean].sum(),
            1e-9,
        )
    if len(blocks) != 500 or int(blocks["audited_ship_cell_count"].sum()) != EXPECTED_CELL_COUNT:
        raise AssertionError("1-degree block coverage closure mismatch")
    return {
        "grid_shape": list(EXPECTED_GRID_SHAPE),
        "strict_ocean_cell_count": int(ocean.sum()),
        "audited_ship_cell_count": int(occupied.sum()),
        "full_ocean_distances_recomputed": len(recomputed),
        "blocks_checked": len(blocks),
    }


def verify(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "audit_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required_flags = {
        "downstream_model_error_read": False,
        "error_derived_cohort_columns_read": False,
        "tid_independence_proof": False,
        "cohort_mutated": False,
        "row_weight_generated": False,
        "row_exclusion_generated": False,
        "three_std_filter_applied": False,
        "comparison_role": "qc_layer_c_diagnostic_only",
        "reference_independence": "not_established",
    }
    for key, expected in required_flags.items():
        if manifest.get(key) != expected:
            raise AssertionError(f"manifest evidence-boundary flag mismatch: {key}")
    expected_columns = sorted([
        "canonical_cell_id", "lon", "lat", "representative_depth_m", "source_provider",
    ])
    if manifest.get("downstream_columns_read") != expected_columns:
        raise AssertionError("manifest downstream allowlist drift")

    config_record = manifest["config"]
    if sha256_file(Path(config_record["path"])) != config_record["sha256"]:
        raise AssertionError("config hash mismatch")
    input_hash_checks = {}
    for role, record in manifest["inputs"].items():
        actual = sha256_file(Path(record["path"]))
        input_hash_checks[role] = actual == record["sha256"]
        if not input_hash_checks[role]:
            raise AssertionError(f"frozen input hash mismatch: {role}")
    output_hash_checks = {}
    for role, record in manifest["outputs"].items():
        path = Path(record["path"])
        if path.parent != run_dir:
            raise AssertionError(f"output escaped immutable run directory: {role}")
        actual = sha256_file(path)
        output_hash_checks[role] = actual == record["sha256"]
        if not output_hash_checks[role]:
            raise AssertionError(f"output hash mismatch: {role}")

    frame = pd.read_parquet(run_dir / "product_consistency_by_cell.parquet")
    forbidden = sorted(
        column for column in frame.columns
        if any(token in column.lower() for token in FORBIDDEN_COLUMN_TOKENS)
    )
    if forbidden:
        raise AssertionError(f"diagnostic table contains decision/weight columns: {forbidden}")
    if len(frame) != EXPECTED_CELL_COUNT or frame["canonical_cell_id"].nunique() != EXPECTED_CELL_COUNT:
        raise AssertionError("per-cell diagnostic row/key closure failed")
    if frame["source_provider"].value_counts().to_dict() != EXPECTED_SOURCE_COUNTS:
        raise AssertionError("per-cell source closure failed")
    if frame["raw_replay_result"].value_counts().to_dict() != EXPECTED_REPLAY_COUNTS:
        raise AssertionError("replay count closure failed")
    consensus_checks = verify_consensus(frame)

    union_keys = set(pd.read_parquet(
        manifest["inputs"]["downstream_union"]["path"], columns=["canonical_cell_id"]
    )["canonical_cell_id"])
    lineage_keys = set(pd.read_parquet(
        manifest["inputs"]["cell_lineage"]["path"], columns=["canonical_cell_id"]
    )["canonical_cell_id"])
    replay_keys = set(pd.read_parquet(
        manifest["inputs"]["raw_to_cell_replay"]["path"], columns=["canonical_cell_id"]
    )["canonical_cell_id"])
    if union_keys != lineage_keys or union_keys != replay_keys or union_keys != set(frame["canonical_cell_id"]):
        raise AssertionError("union/lineage/replay/diagnostic key closure failed")

    with xr.open_dataset(run_dir / "scs_product_context_1min.nc") as opened:
        product_context = opened.load()
    with xr.open_dataset(run_dir / "coverage_grid_1min.nc") as opened:
        coverage = opened.load()
    if product_context.sizes.get("lat") != EXPECTED_GRID_SHAPE[0] or product_context.sizes.get("lon") != EXPECTED_GRID_SHAPE[1]:
        raise AssertionError("product context shape mismatch")
    for key in PRODUCT_KEYS:
        persisted = product_context[f"{key}_depth_m"].values[
            frame["lat_index"].to_numpy(dtype=np.int64),
            frame["lon_index"].to_numpy(dtype=np.int64),
        ]
        if not np.allclose(persisted, frame[f"{key}_depth_m"], rtol=0, atol=1e-9, equal_nan=True):
            raise AssertionError(f"product context/per-cell mismatch: {key}")
    if not np.array_equal(
        product_context["frozen_land_mask"].values.astype(bool),
        coverage["frozen_land_mask"].values.astype(bool),
    ):
        raise AssertionError("product/coverage frozen land masks differ")

    metrics = pd.read_csv(run_dir / "product_metrics.tsv", sep="\t")
    metrics_checked = verify_metrics(frame, metrics)
    tid_table = pd.read_csv(run_dir / "tid_composition.tsv", sep="\t")
    tid_checks = verify_tid(manifest, product_context, tid_table)
    blocks = pd.read_parquet(run_dir / "coverage_by_block_1deg.parquet")
    summary = json.loads((run_dir / "coverage_summary.json").read_text(encoding="utf-8"))
    coverage_checks = verify_coverage(manifest, frame, coverage, blocks, summary)

    return {
        "status": "pass",
        "run_dir": str(run_dir),
        "manifest_sha256": sha256_file(manifest_path),
        "input_hash_checks": input_hash_checks,
        "output_hash_checks": output_hash_checks,
        "cell_count": len(frame),
        "source_counts": frame["source_provider"].value_counts().to_dict(),
        "replay_counts": frame["raw_replay_result"].value_counts().to_dict(),
        "consensus_checks": consensus_checks,
        "metrics_rows_checked": metrics_checked,
        "tid_checks": tid_checks,
        "coverage_checks": coverage_checks,
        "evidence_boundary_flags": required_flags,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    result = verify(run_dir)
    verification_path = run_dir / "verification.json"
    atomic_json(result, verification_path)
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"verification_sha256={sha256_file(verification_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
