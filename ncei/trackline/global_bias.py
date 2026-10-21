#!/usr/bin/env python3
"""Build global per-track SB bias, adjusted 1-minute cells, and coverage maps.

Run from the repository root. Existing manifests and derived products are read-only.
The bias reference is the public strict-primary multibeam 1-minute cell product;
regional_mrar and GEBCO are not read.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[2]

from _common.file_io import atomic_write_parquet, atomic_write_text
NCEI_ROOT = REPO_ROOT / "ncei"
from _common.singlebeam_bias import bias_decision
MANIFEST_PATH = NCEI_ROOT / "manifests/trackline_source_manifest.parquet"
SB_ROOT = NCEI_ROOT / "derived/singlebeam/file_cells_1min"
MB_STRICT_PATH = NCEI_ROOT / "derived/validation_cells_1min/strict_primary_multibeam_cells.parquet"
JAMSTEC_MB_PATH = REPO_ROOT / "jamstec/multibeam/derived/cells_1min_qcfiltered/cells.parquet"
NCEI_MB_ROOT = NCEI_ROOT / "derived/multibeam/cells_1min"
BIAS_ROOT = NCEI_ROOT / "derived/sb_track_bias_global"
BIAS_PATH = BIAS_ROOT / "track_bias_summary.parquet"
ADJUSTED_ROOT = NCEI_ROOT / "derived/singlebeam/file_cells_1min_adjusted"
COVERAGE_ROOT = NCEI_ROOT / "figures/coverage_global"
COVERAGE_STATS_PATH = BIAS_ROOT / "coverage_summary.parquet"
PRODUCT_MANIFEST_PATH = BIAS_ROOT / "product_manifest.json"

IDENTITY_COLUMNS = [
    "track_id", "source_type", "source_completeness", "source_path",
    "source_archive", "survey_id",
]
BIAS_COLUMNS = IDENTITY_COLUMNS + [
    "branch", "n_colocated_cells", "mb_median", "sb_median", "bias_m",
    "nmad_m", "applied", "gate_reason",
]
PROVENANCE_COLUMNS = ["track_bias_m", "bias_applied", "bias_n_support"]
FIGURE_SOURCES = (
    "jamstec_multibeam", "ncei_multibeam", "singlebeam_nc", "singlebeam_xyz"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m ncei.trackline global-bias", description=__doc__)
    parser.add_argument(
        "--overwrite", action="store_true",
        help="replace only this script's global outputs",
    )
    return parser.parse_args(argv)


def read_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sb_columns = [
        "track_id", "source_type", "branch", "cell_id", "lon_center", "lat_center",
        "median_depth_m", "n_unique_triples",
    ]
    sb = ds.dataset(SB_ROOT, format="parquet").to_table(columns=sb_columns).to_pandas()
    mb = pd.read_parquet(
        MB_STRICT_PATH, columns=["cell_id", "representative_depth_m"]
    )
    manifest = pd.read_parquet(MANIFEST_PATH, columns=IDENTITY_COLUMNS + ["instrument_class_pred"])

    if sb.duplicated(["track_id", "source_type", "cell_id"]).any():
        raise AssertionError("SB track/source/cell identity is not unique")
    if mb["cell_id"].duplicated().any():
        raise AssertionError("strict MB cell_id is not unique")
    if (sb["n_unique_triples"] <= 0).any():
        raise AssertionError("SB n_unique_triples must be positive")
    if set(sb["branch"].unique()) != {"singlebeam"}:
        raise AssertionError(f"unexpected SB branches: {sorted(sb['branch'].unique())}")
    if not set(sb["source_type"].unique()) <= {"ncei_nc", "ncei_xyz"}:
        raise AssertionError("global SB input contains a non-nc/xyz source")

    manifest = manifest.loc[manifest["instrument_class_pred"].eq("singlebeam")].drop(
        columns="instrument_class_pred"
    )
    if manifest.duplicated(["track_id", "source_type"]).any():
        raise AssertionError("manifest track/source identity is not unique")
    return sb, mb, manifest


def estimate_biases(sb: pd.DataFrame, mb: pd.DataFrame, manifest: pd.DataFrame) -> pd.DataFrame:
    colocated = sb.merge(mb, on="cell_id", how="inner", validate="many_to_one")
    colocated["residual_m"] = (
        colocated["median_depth_m"] - colocated["representative_depth_m"]
    )
    rows: list[dict[str, object]] = []
    for (track_id, source_type), cells in colocated.groupby(
        ["track_id", "source_type"], sort=True
    ):
        bias, spread, applied, reason = bias_decision(
            cells["residual_m"], cells["n_unique_triples"]
        )
        rows.append({
            "track_id": str(track_id),
            "source_type": str(source_type),
            "branch": "nc" if source_type == "ncei_nc" else "xyz",
            "n_colocated_cells": int(len(cells)),
            "mb_median": float(cells["representative_depth_m"].median()),
            "sb_median": float(cells["median_depth_m"].median()),
            "bias_m": bias,
            "nmad_m": spread,
            "applied": applied,
            "gate_reason": reason,
        })
    estimates = pd.DataFrame(rows)
    out = estimates.merge(
        manifest, on=["track_id", "source_type"], how="left", validate="one_to_one"
    )
    if out["source_path"].isna().any():
        missing = out.loc[out["source_path"].isna(), ["track_id", "source_type"]]
        raise AssertionError(f"bias tracks missing manifest identity: {missing.head().to_dict('records')}")
    return out[BIAS_COLUMNS].sort_values(["branch", "track_id"]).reset_index(drop=True)


def write_adjusted_files(biases: pd.DataFrame) -> tuple[int, int]:
    lookup = biases.set_index(["track_id", "source_type"])
    n_files = 0
    n_rows = 0
    for input_path in sorted(SB_ROOT.glob("*.parquet")):
        frame = pd.read_parquet(input_path)
        key = (str(frame["track_id"].iloc[0]), str(frame["source_type"].iloc[0]))
        if not (
            frame["track_id"].eq(key[0]).all()
            and frame["source_type"].eq(key[1]).all()
        ):
            raise AssertionError(f"mixed track identity in {input_path}")
        if key in lookup.index:
            row = lookup.loc[key]
            frame["track_bias_m"] = float(row["bias_m"])
            frame["bias_applied"] = bool(row["applied"])
            frame["bias_n_support"] = int(row["n_colocated_cells"])
            if bool(row["applied"]):
                frame["median_depth_m"] = frame["median_depth_m"] - float(row["bias_m"])
        else:
            frame["track_bias_m"] = np.nan
            frame["bias_applied"] = False
            frame["bias_n_support"] = 0
        atomic_write_parquet(frame, ADJUSTED_ROOT / input_path.name)
        n_files += 1
        n_rows += len(frame)
    return n_files, n_rows


def density_grid(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    valid = np.isfinite(lon) & np.isfinite(lat)
    grid, _, _ = np.histogram2d(
        lat[valid], lon[valid], bins=(180, 360), range=((-90.0, 90.0), (-180.0, 180.0))
    )
    return grid


def plot_density(grid: np.ndarray, title: str, path: Path, axis=None) -> None:
    own = axis is None
    if own:
        figure, axis = plt.subplots(figsize=(12, 5.8), constrained_layout=True)
    positive = grid[grid > 0]
    vmax = max(1.0, float(positive.max())) if len(positive) else 1.0
    image = axis.imshow(
        np.ma.masked_less_equal(grid, 0), origin="lower", extent=(-180, 180, -90, 90),
        cmap="viridis", norm=LogNorm(vmin=1, vmax=vmax), aspect="auto", interpolation="nearest",
    )
    axis.set(xlim=(-180, 180), ylim=(-90, 90), xlabel="Longitude", ylabel="Latitude", title=title)
    axis.set_xticks(np.arange(-180, 181, 60))
    axis.set_yticks(np.arange(-90, 91, 30))
    axis.grid(color="0.75", linewidth=0.35)
    if own:
        figure.colorbar(image, ax=axis, label="Occupied 1-minute cells per 1-degree bin")
        path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(path, dpi=180)
        plt.close(figure)
    return image


def build_coverage(sb: pd.DataFrame) -> pd.DataFrame:
    jam = pd.read_parquet(JAMSTEC_MB_PATH, columns=["cell_id", "lon_center", "lat_center"])
    ncei_mb = ds.dataset(NCEI_MB_ROOT, format="parquet", partitioning="hive").to_table(
        columns=["cell_id", "lon_center", "lat_center"]
    ).to_pandas()
    sources = {
        "jamstec_multibeam": jam,
        "ncei_multibeam": ncei_mb,
        "singlebeam_nc": sb.loc[sb["source_type"].eq("ncei_nc"), ["cell_id", "lon_center", "lat_center"]],
        "singlebeam_xyz": sb.loc[sb["source_type"].eq("ncei_xyz"), ["cell_id", "lon_center", "lat_center"]],
    }
    titles = {
        "jamstec_multibeam": "JAMSTEC multibeam: global 1-minute cell density",
        "ncei_multibeam": "NCEI multibeam: global 1-minute cell density",
        "singlebeam_nc": "NCEI singlebeam nc: global 1-minute cell density",
        "singlebeam_xyz": "NCEI singlebeam xyz: global 1-minute cell density",
    }
    grids: dict[str, np.ndarray] = {}
    rows = []
    for name in FIGURE_SOURCES:
        frame = sources[name].drop_duplicates("cell_id")
        grid = density_grid(frame["lon_center"].to_numpy(), frame["lat_center"].to_numpy())
        grids[name] = grid
        plot_density(grid, titles[name], COVERAGE_ROOT / f"{name}.png")
        rows.append({
            "source": name,
            "n_occupied_1min_cells": int(frame["cell_id"].nunique()),
            "n_occupied_1deg_bins": int((grid > 0).sum()),
            "max_1min_cells_per_1deg_bin": int(grid.max()),
        })

    figure, axes = plt.subplots(2, 1, figsize=(12, 10), constrained_layout=True)
    mb_grid = grids["jamstec_multibeam"] + grids["ncei_multibeam"]
    sb_grid = grids["singlebeam_nc"] + grids["singlebeam_xyz"]
    im0 = plot_density(mb_grid, "Multibeam coverage", Path(), axes[0])
    im1 = plot_density(sb_grid, "Singlebeam coverage", Path(), axes[1])
    figure.colorbar(im0, ax=axes[0], label="Occupied 1-minute cells per 1-degree bin")
    figure.colorbar(im1, ax=axes[1], label="Occupied 1-minute cells per 1-degree bin")
    COVERAGE_ROOT.mkdir(parents=True, exist_ok=True)
    figure.savefig(COVERAGE_ROOT / "multibeam_vs_singlebeam.png", dpi=180)
    plt.close(figure)
    return pd.DataFrame(rows)


def write_manifest(biases: pd.DataFrame, n_files: int, n_rows: int) -> None:
    payload = {
        "name": "global_singlebeam_track_bias_and_adjusted_cells",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": f"{sys.executable} -m ncei.trackline global-bias --overwrite",
        "source_paths": [str(MANIFEST_PATH), str(SB_ROOT), str(MB_STRICT_PATH)],
        "output_paths": [str(BIAS_PATH), str(ADJUSTED_ROOT), str(COVERAGE_ROOT), str(COVERAGE_STATS_PATH)],
        "counts": {"bias_rows": len(biases), "adjusted_files": n_files, "adjusted_rows": n_rows},
        "bias_rule": "weighted median of SB-minus-strict-MB cell residuals; apply for n>=5 and abs(bias)>=2*NMAD",
        "depth_unit": "m, positive down",
        "regional_mrar": "excluded",
        "gebco": "not used",
        "randomness": "none",
    }
    atomic_write_text(json.dumps(payload, indent=2) + "\n", PRODUCT_MANIFEST_PATH)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if BIAS_PATH.exists() and PRODUCT_MANIFEST_PATH.exists() and not args.overwrite:
        print("Global SB bias outputs already exist; no files changed.")
        return 0

    sb, mb, manifest = read_inputs()
    biases = estimate_biases(sb, mb, manifest)
    atomic_write_parquet(biases, BIAS_PATH)
    n_files, n_rows = write_adjusted_files(biases)
    coverage = build_coverage(sb)
    atomic_write_parquet(coverage, COVERAGE_STATS_PATH)
    write_manifest(biases, n_files, n_rows)
    print(
        f"Wrote {len(biases)} bias rows, {n_files} adjusted files / {n_rows} cells, "
        f"and {len(FIGURE_SOURCES) + 1} coverage figures."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
