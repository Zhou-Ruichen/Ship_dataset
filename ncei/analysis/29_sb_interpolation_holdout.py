"""Interpolation-level singlebeam value test: GMT surface on pseudo-outer holdout.

For each of the six frozen regions, grid the inner-training control points
(training-pool blocks only, per variant) with GMT surface at 1 arcmin /
tension 0.25 / pixel registration / -Am aspect (the settings recorded in the
downstream 15-repo config), sample the grid at the held-out pseudo-outer cell
centers with grdtrack (nearest), and compute the same block-equal RMSE
formulas as the downstream neural run so the tables compare row by row.

Variants per region:
  mb_only         strict_multibeam rows only
  mb_sb_adjusted  plus singlebeam_adjusted rows
  mb_sb_reject    plus singlebeam_dispositioned rows

Run from repo root:
  /mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python \
      ncei/analysis/29_sb_interpolation_holdout.py

All existing products are read-only; outputs are additive under
ncei/derived/sb_interpolation_holdout/.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]

DOWNSTREAM_ROOT = Path("/mnt/data2/06-Projects/15-swot_feature_physics_bathy")
ARMS_CONFIG = DOWNSTREAM_ROOT / "configs" / "feasibility" / "nested_sb_control_arms.yaml"
SELECTION_JSON = (
    DOWNSTREAM_ROOT
    / "outputs"
    / "20260902T175753Z-nested-pseudo-outer-sb-nested_pseudo_outer_sb"
    / "pseudo_outer_selection.json"
)
CONTROL_DIR = ROOT / "ncei" / "derived" / "sb_track_bias_1min"
STRICT_CELLS = (
    ROOT / "ncei" / "derived" / "validation_cells_1min" / "strict_primary_multibeam_cells.parquet"
)
OUT_DIR = ROOT / "ncei" / "derived" / "sb_interpolation_holdout"

VARIANTS = {
    "mb_only": {"table_suffix": "mb_only", "allowed_sources": {"strict_multibeam"}},
    "mb_sb_adjusted": {
        "table_suffix": "mb_sb_adjusted",
        "allowed_sources": {"strict_multibeam", "singlebeam_adjusted"},
    },
    "mb_sb_reject": {
        "table_suffix": "mb_sb_reject",
        "allowed_sources": {"strict_multibeam", "singlebeam_dispositioned"},
    },
}

EXPECTED_COLUMNS = {"cell_id", "lon_center", "lat_center", "control_depth_m", "control_source"}
NON_CONVERGENCE_PHRASES = (
    "did not converge",
    "failed to converge",
    "convergence failed",
    "no convergence",
)


def fail(message: str) -> None:
    raise SystemExit(f"29_sb_interpolation_holdout: {message}")


def fmt(value: float) -> str:
    return f"{value:.12g}"


def encode_cell_id(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    lon_bin = np.floor(np.asarray(lon, dtype=float) * 60.0).astype(np.int64) + 10_800
    lat_bin = np.floor(np.asarray(lat, dtype=float) * 60.0).astype(np.int64) + 5_400
    return lat_bin * 21_600 + lon_bin


def cell_id_strings(ids: np.ndarray) -> list[str]:
    return [f"1min_{int(cid) // 21_600}_{int(cid) % 21_600}" for cid in ids]


def load_controls(tile: str, variant: str) -> pd.DataFrame:
    spec = VARIANTS[variant]
    path = CONTROL_DIR / f"controls_{spec['table_suffix']}_{tile}.parquet"
    frame = pd.read_parquet(path)
    if set(frame.columns) != EXPECTED_COLUMNS:
        fail(f"{path.name}: unexpected columns {sorted(frame.columns)}")
    found = set(frame["control_source"].astype(str).unique())
    if not found or not found <= spec["allowed_sources"]:
        fail(f"{path.name}: unexpected control sources {sorted(found)}")
    numeric = frame[["lon_center", "lat_center", "control_depth_m"]].to_numpy(float)
    if not np.isfinite(numeric).all():
        fail(f"{path.name}: non-finite control values")
    ids = encode_cell_id(
        frame["lon_center"].to_numpy(float), frame["lat_center"].to_numpy(float)
    )
    expected_ids = np.array(cell_id_strings(ids))
    if not np.array_equal(expected_ids, frame["cell_id"].astype(str).to_numpy()):
        fail(f"{path.name}: cell_id disagrees with control coordinates")
    result = frame.copy()
    result["one_minute_cell_id"] = ids
    return result


def assign_blocks(frame: pd.DataFrame, west: float, south: float) -> pd.DataFrame:
    block_lon = np.floor(frame["lon_center"].to_numpy(float) - west).astype(int)
    block_lat = np.floor(frame["lat_center"].to_numpy(float) - south).astype(int)
    color = (block_lon + 2 * block_lat) % 5
    if not (
        (block_lon >= 0).all()
        and (block_lon < 5).all()
        and (block_lat >= 0).all()
        and (block_lat < 5).all()
        and np.isin(color, [2, 3, 4]).all()
    ):
        fail("control rows fall outside frozen inner-training blocks")
    result = frame.copy()
    result["block_lon"] = block_lon
    result["block_lat"] = block_lat
    return result


def run_gmt(
    executable: str,
    arguments: list[str],
    work_dir: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess:
    command = [executable, *arguments]
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=work_dir,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        fail(f"GMT execution failed: {error}")


def gmt_surface(
    controls: pd.DataFrame,
    region: dict,
    gmt: dict,
    version: str,
    variant_dir: Path,
) -> dict:
    """Grid with GMT surface using the downstream GGM-stage command contract."""
    west = float(region["west"])
    east = float(region["east"])
    south = float(region["south"])
    north = float(region["north"])
    increment = 1.0 / (60.0 * int(gmt["increment_arcmin"]))
    tension = float(gmt["tension"])
    aspect = str(gmt["aspect"])
    verbosity = str(gmt["verbosity"])
    executable = str(gmt["executable"])
    timeout = int(gmt["timeout_seconds"])
    if aspect != "m" or verbosity != "w":
        fail("GMT settings disagree with the recorded downstream contract")
    region_argument = "/".join(fmt(v) for v in (west, east, south, north))

    raw_rows = len(controls)
    unique = (
        controls.groupby(["lon_center", "lat_center"], as_index=False)["control_depth_m"]
        .mean()
        .rename(columns={"control_depth_m": "value"})
    )
    duplicate_groups = int(raw_rows - len(unique))
    values = unique[["lon_center", "lat_center", "value"]].to_numpy(float)

    surface_path = variant_dir / "surface.nc"
    if surface_path.exists():
        fail(f"immutable GMT output already exists: {surface_path}")
    with tempfile.TemporaryDirectory(dir=variant_dir, prefix=".surface.") as tmp:
        work = Path(tmp)
        xyz_path = work / "controls.xyz"
        temporary_output = work / "surface.nc"
        np.savetxt(xyz_path, values, fmt="%.17g", delimiter="\t")
        command = (
            executable,
            "surface",
            str(xyz_path),
            f"-G{temporary_output}",
            f"-R{region_argument}",
            f"-I{fmt(increment)}",
            "-rp",
            "-fg",
            f"-A{aspect}",
            f"-T{tension:.2f}",
            f"-V{verbosity}",
        )
        try:
            process = subprocess.run(
                list(command),
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=work,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            fail(f"GMT surface execution failed: {error}")
        if process.returncode != 0:
            fail(
                f"GMT surface exit {process.returncode}; "
                f"command={list(command)!r}; stderr={process.stderr.strip()!r}"
            )
        if not temporary_output.is_file():
            fail("GMT surface returned success without an output grid")
        log_text = process.stdout + "\n" + process.stderr
        converged = not any(
            phrase in log_text.lower() for phrase in NON_CONVERGENCE_PHRASES
        )
        if not converged:
            fail(f"GMT surface reported non-convergence: {process.stderr.strip()!r}")
        temporary_output.replace(surface_path)
    return {
        "command": list(command),
        "gmt_version": version,
        "stdout": process.stdout,
        "stderr": process.stderr,
        "returncode": 0,
        "converged": True,
        "raw_control_rows": int(raw_rows),
        "unique_control_coordinates": int(len(unique)),
        "duplicate_coordinate_groups": duplicate_groups,
        "output_path": str(surface_path),
        "grid_shape_lon_lat": [
            int(round((east - west) / increment)),
            int(round((north - south) / increment)),
        ],
        "gmt_settings": {
            "region": region_argument,
            "increment_argument": fmt(increment),
            "registration": "pixel (-rp)",
            "tension": tension,
            "aspect": aspect,
            "verbosity": verbosity,
        },
    }


def grdtrack_holdout(
    executable: str,
    grid_path: Path,
    targets: pd.DataFrame,
    work_dir: Path,
    timeout: int,
) -> np.ndarray:
    points = targets[["lon_center", "lat_center"]].to_numpy(float)
    points_path = work_dir / "holdout.xy"
    np.savetxt(points_path, points, fmt="%.17g", delimiter="\t")
    process = run_gmt(
        executable,
        ["grdtrack", str(points_path), f"-G{grid_path}", "-nn"],
        work_dir,
        timeout,
    )
    if process.returncode != 0:
        fail(f"grdtrack exit {process.returncode}: {process.stderr.strip()!r}")
    lines = [line.split() for line in process.stdout.strip().splitlines() if line.strip()]
    if len(lines) != len(points):
        fail(f"grdtrack returned {len(lines)} rows for {len(points)} points")
    try:
        values = np.array([float(row[2]) for row in lines], dtype=float)
    except (IndexError, ValueError) as error:
        fail(f"cannot parse grdtrack output: {error}")
    if not np.isfinite(values).all():
        fail("grdtrack returned non-finite depths at holdout centers")
    return values


def main() -> int:
    arms_config = yaml.safe_load(ARMS_CONFIG.read_text())
    gmt = arms_config["ggm"]
    executable = str(gmt["executable"])
    timeout = int(gmt["timeout_seconds"])
    version = run_gmt(executable, ["--version"], Path.cwd(), 30).stdout.strip()

    selection = json.loads(SELECTION_JSON.read_text())
    regions = {str(r["id"]): r for r in arms_config["regions"]}
    if set(regions) != set(selection["regions"]):
        fail("arms-config regions disagree with the pseudo-outer selection JSON")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    strict_depths = pd.read_parquet(
        STRICT_CELLS, columns=["cell_id", "representative_depth_m"]
    ).set_index("cell_id")["representative_depth_m"]

    result_rows: list[dict] = []
    regional_mse: dict[str, dict[str, float]] = {v: {} for v in VARIANTS}
    manifest: dict = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "script": str(Path(__file__).resolve()),
        "selection_json": str(SELECTION_JSON),
        "arms_config": str(ARMS_CONFIG),
        "strict_cells": str(STRICT_CELLS),
        "gmt_version": version,
        "gmt_settings": {
            "tension": float(gmt["tension"]),
            "aspect": str(gmt["aspect"]),
            "increment_arcmin": int(gmt["increment_arcmin"]),
            "registration": str(gmt["grid_registration"]),
            "executable": executable,
            "timeout_seconds": timeout,
            "verbosity": str(gmt["verbosity"]),
        },
        "duplicate_rule": (
            "exact-coordinate controls replaced by their arithmetic mean "
            "before GMT surface (GMT surface contract requires unique "
            "coordinates); raw and unique counts recorded per run"
        ),
        "sampling": "gmt grdtrack nearest-neighbor (-nn) at holdout cell centers",
        "metric": (
            "per holdout block MSE over its cells, equal weight per block; "
            "regional block-equal RMSE = sqrt(mean block MSE); "
            "pooled = sqrt(equal-weight mean of regional MSEs)"
        ),
        "runs": {},
    }

    for tile, region in regions.items():
        sel = selection["regions"][tile]
        holdout_blocks = {
            (int(b["block_lon"]), int(b["block_lat"])) for b in sel["pseudo_outer_blocks"]
        }
        training_blocks = {
            (int(b["block_lon"]), int(b["block_lat"]))
            for b in sel["training_pool_blocks"]
        }
        if holdout_blocks & training_blocks:
            fail(f"{tile}: holdout and training-pool blocks overlap")

        mb_only_full = assign_blocks(load_controls(tile, "mb_only"), float(region["west"]), float(region["south"]))
        holdout_mask = mb_only_full.apply(
            lambda row: (int(row.block_lon), int(row.block_lat)) in holdout_blocks, axis=1
        )
        holdout = mb_only_full.loc[holdout_mask].sort_values("one_minute_cell_id").reset_index(drop=True)
        if len(holdout) != int(sel["pseudo_outer_cell_count"]):
            fail(
                f"{tile}: holdout cell count {len(holdout)} disagrees with "
                f"selection JSON {sel['pseudo_outer_cell_count']}"
            )
        holdout_ids = holdout["one_minute_cell_id"].to_numpy(np.int64)
        id_strings = cell_id_strings(holdout_ids)
        observed = strict_depths.reindex(id_strings).to_numpy(float)
        if not np.isfinite(observed).all():
            fail(f"{tile}: missing strict-cell truth for holdout cells")
        control_depths = holdout["control_depth_m"].to_numpy(float)
        truth_max_abs_diff = float(np.max(np.abs(observed - control_depths)))

        block_keys = (
            holdout["block_lon"].astype(str) + "," + holdout["block_lat"].astype(str)
        ).to_numpy()

        manifest["runs"][tile] = {}
        for variant in VARIANTS:
            variant_dir = OUT_DIR / tile / variant
            variant_dir.mkdir(parents=True, exist_ok=True)
            frame = assign_blocks(
                load_controls(tile, variant), float(region["west"]), float(region["south"])
            )
            training = frame.loc[
                frame.apply(
                    lambda row: (int(row.block_lon), int(row.block_lat)) in training_blocks,
                    axis=1,
                )
            ].reset_index(drop=True)
            if training.empty:
                fail(f"{tile}/{variant}: empty training control pool")
            training_ids = set(training["one_minute_cell_id"])
            if training_ids & set(holdout_ids.tolist()):
                fail(f"{tile}/{variant}: holdout target leaked into training points")

            surface_record = gmt_surface(training, region, gmt, version, variant_dir)
            manifest["runs"][tile][variant] = {
                **surface_record,
                "training_source_rows": {
                    str(k): int(v)
                    for k, v in training["control_source"].value_counts().sort_index().items()
                },
                "training_pool_blocks": sorted(
                    [list(b) for b in training_blocks]
                ),
                "pseudo_outer_blocks": sorted([list(b) for b in holdout_blocks]),
                "truth_vs_control_max_abs_diff_m": truth_max_abs_diff,
            }

            with tempfile.TemporaryDirectory(dir=variant_dir, prefix=".grdtrack.") as tmp:
                work = Path(tmp)
                predicted = grdtrack_holdout(
                    executable, variant_dir / "surface.nc", holdout, work, timeout
                )
            error = predicted - observed
            block_mse = {
                str(block): float(np.mean(np.square(error[block_keys == block])))
                for block in sorted(set(block_keys))
            }
            region_mse = float(np.mean(list(block_mse.values())))
            regional_mse[variant][tile] = region_mse
            row = {
                "region": tile,
                "variant": variant,
                "pseudo_outer_cells": int(len(holdout)),
                "pseudo_outer_blocks": int(len(block_mse)),
                "block_equal_rmse_m": float(np.sqrt(region_mse)),
                "pooled_cell_rmse_m": float(np.sqrt(np.mean(np.square(error)))),
                "pooled_cell_mae_m": float(np.mean(np.abs(error))),
                "pooled_cell_bias_m": float(np.mean(error)),
            }
            result_rows.append(row)
            predictions = holdout[
                ["cell_id", "lon_center", "lat_center", "block_lon", "block_lat"]
            ].copy()
            predictions["observed_depth_m"] = observed
            predictions["predicted_depth_m"] = predicted
            predictions["error_m"] = error
            predictions.to_parquet(variant_dir / "predictions.parquet", index=False)
            (variant_dir / "gmt_log.json").write_text(
                json.dumps(manifest["runs"][tile][variant], indent=1)
            )
            print(
                f"{tile} {variant}: block-equal RMSE "
                f"{row['block_equal_rmse_m']:.4f} m "
                f"(cells {row['pseudo_outer_cells']}, blocks {row['pseudo_outer_blocks']})",
                flush=True,
            )

    pooled_rows = []
    for variant in VARIANTS:
        per_region = regional_mse[variant]
        pooled_rows.append(
            {
                "variant": variant,
                "regions": len(per_region),
                "pooled_block_equal_rmse_m": float(
                    np.sqrt(np.mean(list(per_region.values())))
                ),
            }
        )

    frame = pd.DataFrame(result_rows)
    baseline = {
        r["region"]: r["block_equal_rmse_m"]
        for r in result_rows
        if r["variant"] == "mb_only"
    }
    for row in result_rows:
        row["rmse_delta_vs_mb_only_m"] = row["block_equal_rmse_m"] - baseline[row["region"]]
    baseline_pooled = {r["variant"]: r["pooled_block_equal_rmse_m"] for r in pooled_rows}
    for row in pooled_rows:
        row["pooled_rmse_delta_vs_mb_only_m"] = (
            row["pooled_block_equal_rmse_m"] - baseline_pooled["mb_only"]
        )

    result = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "metric": manifest["metric"],
        "per_region_per_variant": result_rows,
        "pooled_per_variant": pooled_rows,
    }
    (OUT_DIR / "result_table.json").write_text(json.dumps(result, indent=1))
    frame.to_csv(OUT_DIR / "result_table.csv", index=False)
    manifest["result_table"] = "result_table.json"
    (OUT_DIR / "run_manifest.json").write_text(json.dumps(manifest, indent=1))

    print("\nPooled block-equal RMSE (m):")
    for row in pooled_rows:
        print(
            f"  {row['variant']}: {row['pooled_block_equal_rmse_m']:.4f} "
            f"(delta vs mb_only {row['pooled_rmse_delta_vs_mb_only_m']:+.4f})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
