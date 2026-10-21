#!/usr/bin/env python3
"""Estimate constant singlebeam track biases in six frozen training regions.

Run from the repository root. Strict MB depths are filtered by frozen
``inner_training`` membership cells. SB depths are filtered by the 15
``inner_training`` one-degree blocks defined by the frozen color formula.
GEBCO is sampled only after all bias decisions and control tables have been
constructed; it is diagnostic only.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))  # make _common importable when run by path

from _common.file_io import atomic_write_parquet, atomic_write_text  # noqa: E402
NCEI_ROOT = REPO_ROOT / "ncei"
_BIAS_SPEC = importlib.util.spec_from_file_location(
    "singlebeam_bias", REPO_ROOT / "_common/singlebeam_bias.py"
)
if _BIAS_SPEC is None or _BIAS_SPEC.loader is None:
    raise RuntimeError("cannot load _common/singlebeam_bias.py")
_BIAS_MODULE = importlib.util.module_from_spec(_BIAS_SPEC)
_BIAS_SPEC.loader.exec_module(_BIAS_MODULE)
bias_decision = _BIAS_MODULE.bias_decision
FREEZE_ROOT = Path(
    "/mnt/data2/06-Projects/15-swot_feature_physics_bathy/outputs/"
    "20260901T220024Z-prospective-nested-ggm-nested_region_freeze"
)
MB_PATH = NCEI_ROOT / "derived/validation_cells_1min/strict_primary_multibeam_cells.parquet"
SB_ROOT = NCEI_ROOT / "derived/singlebeam/file_cells_1min"
GEBCO_PATH = Path("/mnt/data2/00-Data/bathymetry/GEBCO/GEBCO_2024.nc")
NESTED_CONFIG_PATH = Path(
    "/mnt/data2/06-Projects/15-swot_feature_physics_bathy/configs/feasibility/"
    "prospective_nested_ggm_selection.yaml"
)
OUTPUT_ROOT = NCEI_ROOT / "derived/sb_track_bias_1min"
REPORT_PATH = NCEI_ROOT / "docs/step09_sb_track_bias_report.md"

TILES = (
    "lon068_lat018",
    "lon052_lat018",
    "lon058_lat012",
    "lon059_lat015",
    "lon004_lat033",
    "lon021_lat010",
)
CONTROL_COLUMNS = ["cell_id", "lon_center", "lat_center", "control_depth_m", "control_source"]
BIAS_COLUMNS = [
    "region", "track_id", "n_region_cells", "n_colocated_cells",
    "n_mb_reference_cells", "n_sb_consensus_reference_cells",
    "weighted_median_residual_m", "residual_nmad_m", "estimated_bias_m",
    "bias_applied", "decision_reason",
]
GEBCO_BINS = [-np.inf, 100.0, 500.0, np.inf]
GEBCO_LABELS = ["<100 m", "100-<500 m", ">=500 m"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Replace this script's existing D1 outputs. Without it, a complete prior run is left unchanged.",
    )
    return parser.parse_args()


def output_paths() -> list[Path]:
    paths = [OUTPUT_ROOT / "track_bias_summary.parquet", REPORT_PATH]
    for tile in TILES:
        for arm in ("mb_only", "mb_sb_raw", "mb_sb_adjusted"):
            paths.append(OUTPUT_ROOT / f"controls_{arm}_{tile}.parquet")
    return paths


def cell_string(cell_number: int) -> str:
    return f"1min_{int(cell_number) // 21600}_{int(cell_number) % 21600}"


def read_regions() -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    regions: dict[str, pd.DataFrame] = {}
    role_by_region_cell: dict[str, str] = {}
    for tile in TILES:
        path = FREEZE_ROOT / f"region_cells_{tile}.parquet"
        table = pq.read_table(path, columns=["one_minute_cell_id", "lon", "lat", "role"])
        region = table.to_pandas()
        region["cell_id"] = region["one_minute_cell_id"].map(cell_string)
        if region["cell_id"].duplicated().any():
            raise AssertionError(f"duplicate frozen cell ids in {tile}")
        for cell_id, role in region[["cell_id", "role"]].itertuples(index=False):
            key = f"{tile}\0{cell_id}"
            role_by_region_cell[key] = str(role)
        regions[tile] = region.loc[region["role"].eq("inner_training")].copy()
    return regions, role_by_region_cell


def read_nested_role_config() -> tuple[float, float, int, set[tuple[int, int]]]:
    with NESTED_CONFIG_PATH.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    candidate = config["candidate"]
    roles = config["nested_roles"]
    tile_size = float(candidate["tile_size_deg"])
    block_size = float(candidate["block_size_deg"])
    blocks_per_axis = int(candidate["blocks_per_axis"])
    training_colors = {int(value) for value in roles["inner_training_colors"]}
    if roles["color_formula"] != "(block_lon + 2 * block_lat) mod 5":
        raise AssertionError("unexpected nested-role color formula")
    blocks = {
        (block_lon, block_lat)
        for block_lon in range(blocks_per_axis)
        for block_lat in range(blocks_per_axis)
        if (block_lon + 2 * block_lat) % 5 in training_colors
    }
    if len(blocks) != int(roles["expected_blocks"]["inner_training"]):
        raise AssertionError("computed inner_training block count differs from config")
    return tile_size, block_size, blocks_per_axis, blocks


def tile_bounds(tile: str, tile_size: float) -> tuple[float, float, float, float]:
    lon_index = int(tile[3:6])
    lat_index = int(tile[10:13])
    west = -180.0 + lon_index * tile_size
    south = -90.0 + lat_index * tile_size
    return west, west + tile_size, south, south + tile_size


def sb_geometry_in_tiles(tile_size: float) -> pd.DataFrame:
    dataset = ds.dataset(SB_ROOT, format="parquet")
    predicate = None
    for tile in TILES:
        west, east, south, north = tile_bounds(tile, tile_size)
        tile_predicate = (
            (pc.field("lon_center") >= west)
            & (pc.field("lon_center") < east)
            & (pc.field("lat_center") >= south)
            & (pc.field("lat_center") < north)
        )
        predicate = tile_predicate if predicate is None else predicate | tile_predicate
    return dataset.to_table(
        columns=["cell_id", "lon_center", "lat_center"], filter=predicate
    ).to_pandas()


def select_sb_training_cells(
    geometry: pd.DataFrame,
    tile: str,
    tile_size: float,
    block_size: float,
    blocks_per_axis: int,
    training_blocks: set[tuple[int, int]],
) -> set[str]:
    west, east, south, north = tile_bounds(tile, tile_size)
    inside = geometry.loc[
        geometry["lon_center"].ge(west)
        & geometry["lon_center"].lt(east)
        & geometry["lat_center"].ge(south)
        & geometry["lat_center"].lt(north)
    ].copy()
    inside["block_lon"] = np.floor((inside["lon_center"] - west) / block_size).astype(int)
    inside["block_lat"] = np.floor((inside["lat_center"] - south) / block_size).astype(int)
    if not inside["block_lon"].between(0, blocks_per_axis - 1).all():
        raise AssertionError(f"SB longitude block outside tile grid in {tile}")
    if not inside["block_lat"].between(0, blocks_per_axis - 1).all():
        raise AssertionError(f"SB latitude block outside tile grid in {tile}")
    keep = [
        (block_lon, block_lat) in training_blocks
        for block_lon, block_lat in inside[["block_lon", "block_lat"]].itertuples(index=False)
    ]
    return set(inside.loc[keep, "cell_id"].astype(str))


def filtered_depth_read(path: Path, columns: list[str], allowed_cells: set[str]) -> pd.DataFrame:
    """Push the training-cell predicate into Arrow before loading depth columns."""
    dataset = ds.dataset(path, format="parquet")
    predicate = pc.field("cell_id").isin(sorted(allowed_cells))
    return dataset.to_table(columns=columns, filter=predicate).to_pandas()


def assert_training_depths(
    frame: pd.DataFrame,
    region: str,
    allowed_cells: set[str],
    role_by_region_cell: dict[str, str],
) -> None:
    observed = set(frame["cell_id"].astype(str))
    assert observed <= allowed_cells, f"depth rows outside inner_training cell filter in {region}"
    observed_roles = {role_by_region_cell[f"{region}\0{cell_id}"] for cell_id in observed}
    assert observed_roles <= {"inner_training"}, (
        f"non-inner_training depth reached computation in {region}: {observed_roles}"
    )


def assert_sb_training_blocks(
    frame: pd.DataFrame,
    region: str,
    allowed_cells: set[str],
    tile_size: float,
    block_size: float,
    blocks_per_axis: int,
    training_blocks: set[tuple[int, int]],
) -> None:
    assert set(frame["cell_id"].astype(str)) <= allowed_cells, (
        f"SB depth rows outside preselected inner_training cells in {region}"
    )
    west, east, south, north = tile_bounds(region, tile_size)
    assert frame["lon_center"].ge(west).all() and frame["lon_center"].lt(east).all()
    assert frame["lat_center"].ge(south).all() and frame["lat_center"].lt(north).all()
    block_lon = np.floor((frame["lon_center"] - west) / block_size).astype(int)
    block_lat = np.floor((frame["lat_center"] - south) / block_size).astype(int)
    assert block_lon.between(0, blocks_per_axis - 1).all()
    assert block_lat.between(0, blocks_per_axis - 1).all()
    observed_blocks = set(zip(block_lon, block_lat))
    assert observed_blocks <= training_blocks, (
        f"SB depth rows outside inner_training blocks in {region}: {observed_blocks - training_blocks}"
    )


def sb_leave_one_out_references(sb: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for cell_id, cell in sb.groupby("cell_id", sort=False):
        if len(cell) < 3:
            continue
        depths = cell["median_depth_m"].to_numpy(dtype=float)
        tracks = cell["track_id"].astype(str).to_numpy()
        for index, track_id in enumerate(tracks):
            other = np.delete(depths, index)
            if len(other) >= 2:
                rows.append({
                    "track_id": track_id,
                    "cell_id": cell_id,
                    "reference_depth_m": float(np.median(other)),
                    "reference_kind": "leave_one_out_sb_consensus",
                })
    return pd.DataFrame(rows, columns=["track_id", "cell_id", "reference_depth_m", "reference_kind"])


def estimate_region_biases(region: str, sb: pd.DataFrame, mb: pd.DataFrame) -> pd.DataFrame:
    mb_reference = mb[["cell_id", "representative_depth_m"]].rename(
        columns={"representative_depth_m": "reference_depth_m"}
    )
    with_mb = sb.merge(mb_reference, on="cell_id", how="inner")
    with_mb["reference_kind"] = "strict_multibeam"

    without_mb = sb.loc[~sb["cell_id"].isin(set(mb["cell_id"]))]
    loo = sb_leave_one_out_references(without_mb)
    with_loo = without_mb.merge(loo, on=["track_id", "cell_id"], how="inner")
    colocated = pd.concat([with_mb, with_loo], ignore_index=True)
    if not colocated.empty:
        colocated["residual_m"] = colocated["median_depth_m"] - colocated["reference_depth_m"]

    rows: list[dict[str, object]] = []
    for track_id, track_cells in sb.groupby("track_id", sort=True):
        residuals = colocated.loc[colocated["track_id"].eq(track_id)]
        count = len(residuals)
        candidate, spread, applied, reason = bias_decision(
            residuals["residual_m"], residuals["n_unique_triples"]
        )
        rows.append({
            "region": region,
            "track_id": str(track_id),
            "n_region_cells": int(len(track_cells)),
            "n_colocated_cells": int(count),
            "n_mb_reference_cells": int(residuals["reference_kind"].eq("strict_multibeam").sum()) if count else 0,
            "n_sb_consensus_reference_cells": int(residuals["reference_kind"].eq("leave_one_out_sb_consensus").sum()) if count else 0,
            "weighted_median_residual_m": candidate,
            "residual_nmad_m": spread,
            "estimated_bias_m": candidate if applied else 0.0,
            "bias_applied": applied,
            "decision_reason": reason,
        })
    return pd.DataFrame(rows, columns=BIAS_COLUMNS)


def mb_controls(mb: pd.DataFrame) -> pd.DataFrame:
    out = mb[["cell_id", "lon_center", "lat_center", "representative_depth_m"]].copy()
    out = out.rename(columns={"representative_depth_m": "control_depth_m"})
    out["control_source"] = "strict_multibeam"
    return out[CONTROL_COLUMNS].sort_values("cell_id").reset_index(drop=True)


def aggregate_sb_controls(sb: pd.DataFrame, biases: pd.DataFrame, adjusted: bool) -> pd.DataFrame:
    work = sb.copy()
    if adjusted:
        work = work.merge(biases[["track_id", "estimated_bias_m"]], on="track_id", how="left", validate="many_to_one")
        work["depth_for_control_m"] = work["median_depth_m"] - work["estimated_bias_m"]
        source = "singlebeam_adjusted"
    else:
        work["depth_for_control_m"] = work["median_depth_m"]
        source = "singlebeam_raw"
    out = work.groupby("cell_id", as_index=False).agg(
        lon_center=("lon_center", "first"),
        lat_center=("lat_center", "first"),
        control_depth_m=("depth_for_control_m", "median"),
    )
    out["control_source"] = source
    return out[CONTROL_COLUMNS]


def combine_controls(mb: pd.DataFrame, sb: pd.DataFrame) -> pd.DataFrame:
    # The combined arm contains one MB control and one file-balanced SB control
    # when both sources occupy a cell.  ``control_source`` keeps those two
    # observations distinct for downstream fitting.
    return (
        pd.concat([mb, sb], ignore_index=True)
        .sort_values(["cell_id", "control_source"])
        .reset_index(drop=True)
    )


def sample_gebco_depth(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Nearest-cell GEBCO depth, positive down; called for diagnostics only."""
    with netCDF4.Dataset(GEBCO_PATH) as grid:
        grid_lon = grid.variables["lon"][:]
        grid_lat = grid.variables["lat"][:]
        lon_index = np.clip(np.searchsorted(grid_lon, lon), 1, len(grid_lon) - 1)
        lon_index -= (np.abs(lon - grid_lon[lon_index - 1]) <= np.abs(lon - grid_lon[lon_index])).astype(int)
        lat_index = np.clip(np.searchsorted(grid_lat, lat), 1, len(grid_lat) - 1)
        lat_index -= (np.abs(lat - grid_lat[lat_index - 1]) <= np.abs(lat - grid_lat[lat_index])).astype(int)
        elevation = np.empty(len(lon_index), dtype=float)
        elevation_grid = grid.variables["elevation"]
        for row_index in np.unique(lat_index):
            selected = lat_index == row_index
            elevation[selected] = np.asarray(
                elevation_grid[int(row_index), lon_index[selected]], dtype=float
            )
    return -elevation


def diagnostic_rows(region: str, raw: pd.DataFrame, adjusted: pd.DataFrame) -> list[dict[str, object]]:
    raw_sb = raw.loc[raw["control_source"].eq("singlebeam_raw")].copy()
    adjusted_sb = adjusted.loc[adjusted["control_source"].eq("singlebeam_adjusted"), ["cell_id", "control_depth_m"]]
    adjusted_sb = adjusted_sb.rename(columns={"control_depth_m": "adjusted_depth_m"})
    frame = raw_sb.merge(adjusted_sb, on="cell_id", how="inner", validate="one_to_one")
    if frame.empty:
        return []
    gebco = sample_gebco_depth(frame["lon_center"].to_numpy(), frame["lat_center"].to_numpy())
    frame["raw_abs_gebco_difference_m"] = np.abs(frame["control_depth_m"] - gebco)
    frame["adjusted_abs_gebco_difference_m"] = np.abs(frame["adjusted_depth_m"] - gebco)
    frame["gebco_band"] = pd.cut(
        frame["raw_abs_gebco_difference_m"], bins=GEBCO_BINS, labels=GEBCO_LABELS, right=False
    )
    rows = []
    for band in GEBCO_LABELS:
        part = frame.loc[frame["gebco_band"].eq(band)]
        rows.append({
            "region": region,
            "gebco_band": band,
            "n_sb_cells": int(len(part)),
            "median_raw_abs_gebco_difference_m": float(part["raw_abs_gebco_difference_m"].median()) if len(part) else np.nan,
            "median_adjusted_abs_gebco_difference_m": float(part["adjusted_abs_gebco_difference_m"].median()) if len(part) else np.nan,
        })
    return rows


def format_number(value: float) -> str:
    return "NA" if pd.isna(value) else f"{value:.2f}"


def build_report(
    summaries: pd.DataFrame,
    control_counts: list[dict[str, int]],
    diagnostics: pd.DataFrame,
) -> str:
    lines = [
        "# Step 09 singlebeam track-bias controls",
        "",
        "Bias estimates and all three control arms use only frozen `inner_training` scope. "
        "For strict MB, the script pushes membership-parquet `inner_training` cell ids into "
        "the Arrow depth read and asserts every MB depth row against the frozen role map. "
        "For SB, it computes all 15 training blocks on each tile's 5x5 grid using "
        "`(block_lon + 2 * block_lat) mod 5 in {2, 3, 4}`, selects cell ids from coordinates "
        "before reading SB depths, and asserts every SB depth row remains in those blocks. "
        "The block definition comes from "
        "`15-swot_feature_physics_bathy/configs/feasibility/prospective_nested_ggm_selection.yaml` "
        "under `nested_roles`. No strict MB `representative_depth_m` from `inner_validation` "
        "or `outer_evaluation` was read.",
        "",
        "A track bias is the `n_unique_triples`-weighted median of track-cell depth minus its "
        "reference. Strict MB is the reference when present; otherwise the reference is the "
        "median of at least two other SB tracks in that cell. The bias is applied only with "
        "at least five reference cells and `|bias| >= 2 * NMAD`. Step 08's file-balanced rule "
        "is retained: an SB control cell is the median of its per-track cell medians.",
        "",
        "## Per-region results",
        "",
        "| region | SB tracks | bias applied | thin evidence | not significant | median |b| applied (m) | MB controls | SB controls | SB-only coverage | MB+SB control rows |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    counts_by_region = {row["region"]: row for row in control_counts}
    for region in TILES:
        part = summaries.loc[summaries["region"].eq(region)]
        applied = part.loc[part["bias_applied"]]
        counts = counts_by_region[region]
        lines.append(
            f"| {region} | {len(part)} | {len(applied)} | "
            f"{part['decision_reason'].eq('thin_evidence').sum()} | "
            f"{part['decision_reason'].eq('not_significant').sum()} | "
            f"{format_number(applied['estimated_bias_m'].abs().median())} | "
            f"{counts['mb_only']} | {counts['sb_controls']} | "
            f"{counts['sb_only_coverage']} | {counts['mb_sb_raw']} |"
        )
    applied_all = summaries.loc[summaries["bias_applied"], "estimated_bias_m"]
    lines.extend([
        "",
        "Across applied tracks, the signed bias distribution (m) is: "
        f"minimum {format_number(applied_all.min())}, median {format_number(applied_all.median())}, "
        f"maximum {format_number(applied_all.max())}; median absolute bias "
        f"{format_number(applied_all.abs().median())}.",
        "",
        "## GEBCO diagnostic stratification",
        "",
        "Bands are defined from the raw SB control-cell difference: `<100 m`, `100-<500 m`, "
        "and `>=500 m`. GEBCO 2024 was sampled at each SB cell center only after bias decisions "
        "and control membership were fixed. These values did not gate cells, tracks, bias "
        "application, or any control arm.",
        "",
        "| region | raw SB-GEBCO band | SB cells | median raw |difference| (m) | median adjusted |difference| (m) |",
        "| --- | --- | ---: | ---: | ---: |",
    ])
    for row in diagnostics.itertuples(index=False):
        lines.append(
            f"| {row.region} | {row.gebco_band} | {row.n_sb_cells} | "
            f"{format_number(row.median_raw_abs_gebco_difference_m)} | "
            f"{format_number(row.median_adjusted_abs_gebco_difference_m)} |"
        )
    lines.extend([
        "",
        "## Outputs and reruns",
        "",
        "Each region has `controls_mb_only_<region>.parquet`, "
        "`controls_mb_sb_raw_<region>.parquet`, and "
        "`controls_mb_sb_adjusted_<region>.parquet` under "
        "`ncei/derived/sb_track_bias_1min/`. Track decisions are in "
        "`track_bias_summary.parquet`. A rerun without `--overwrite` exits without changing a "
        "complete output set; a partial output set requires `--overwrite`.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    expected = output_paths()
    existing = [path for path in expected if path.exists()]
    if existing and not args.overwrite:
        if len(existing) == len(expected):
            print("Complete D1 output set already exists; no files changed.")
            return
        raise SystemExit("Partial D1 output set exists; inspect it and rerun with --overwrite to replace D1 outputs.")

    regions, role_by_region_cell = read_regions()
    tile_size, block_size, blocks_per_axis, training_blocks = read_nested_role_config()
    sb_geometry = sb_geometry_in_tiles(tile_size)
    sb_training_cells = {
        tile: select_sb_training_cells(
            sb_geometry, tile, tile_size, block_size, blocks_per_axis, training_blocks
        )
        for tile in TILES
    }
    union_mb_training = set().union(*(set(frame["cell_id"]) for frame in regions.values()))
    union_sb_training = set().union(*sb_training_cells.values())
    mb_all = filtered_depth_read(
        MB_PATH,
        ["cell_id", "lon_center", "lat_center", "representative_depth_m", "dominant_file_id"],
        union_mb_training,
    )
    sb_all = filtered_depth_read(
        SB_ROOT,
        ["track_id", "cell_id", "lon_center", "lat_center", "median_depth_m", "n_unique_triples", "duplicate_ratio"],
        union_sb_training,
    )

    summaries = []
    controls: dict[tuple[str, str], pd.DataFrame] = {}
    control_counts: list[dict[str, int]] = []
    diagnostic_records: list[dict[str, object]] = []
    for region, frozen in regions.items():
        mb_allowed = set(frozen["cell_id"])
        sb_allowed = sb_training_cells[region]
        mb = mb_all.loc[mb_all["cell_id"].isin(mb_allowed)].copy()
        sb = sb_all.loc[sb_all["cell_id"].isin(sb_allowed)].copy()
        assert_training_depths(mb, region, mb_allowed, role_by_region_cell)
        assert_sb_training_blocks(
            sb, region, sb_allowed, tile_size, block_size, blocks_per_axis, training_blocks
        )
        if mb["cell_id"].duplicated().any():
            raise AssertionError(f"strict MB cell ids are not unique in {region}")
        if sb.duplicated(["track_id", "cell_id"]).any():
            raise AssertionError(f"SB track-cell ids are not unique in {region}")
        if (sb["n_unique_triples"] <= 0).any():
            raise AssertionError(f"non-positive SB weights in {region}")

        region_biases = estimate_region_biases(region, sb, mb)
        summaries.append(region_biases)
        mb_arm = mb_controls(mb)
        raw_arm = combine_controls(mb_arm, aggregate_sb_controls(sb, region_biases, adjusted=False))
        adjusted_arm = combine_controls(mb_arm, aggregate_sb_controls(sb, region_biases, adjusted=True))
        controls[(region, "mb_only")] = mb_arm
        controls[(region, "mb_sb_raw")] = raw_arm
        controls[(region, "mb_sb_adjusted")] = adjusted_arm
        control_counts.append({
            "region": region,
            "mb_only": len(mb_arm),
            "sb_controls": int(sb["cell_id"].nunique()),
            "sb_only_coverage": int(len(set(sb["cell_id"]) - set(mb["cell_id"]))),
            "mb_sb_raw": len(raw_arm),
            "mb_sb_adjusted": len(adjusted_arm),
        })
        diagnostic_records.extend(diagnostic_rows(region, raw_arm, adjusted_arm))

    summary = pd.concat(summaries, ignore_index=True)[BIAS_COLUMNS]
    diagnostics = pd.DataFrame(diagnostic_records)
    report = build_report(summary, control_counts, diagnostics)

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    for (region, arm), frame in controls.items():
        atomic_write_parquet(frame[CONTROL_COLUMNS], OUTPUT_ROOT / f"controls_{arm}_{region}.parquet")
    atomic_write_parquet(summary, OUTPUT_ROOT / "track_bias_summary.parquet")
    atomic_write_text(report, REPORT_PATH)
    print(f"Wrote {len(expected)} D1 files for {len(TILES)} frozen regions.")


if __name__ == "__main__":
    main()
