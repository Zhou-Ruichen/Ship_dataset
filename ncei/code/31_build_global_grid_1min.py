#!/usr/bin/env python3
"""Build the immutable round-2 merged global 1-arcminute ship grid.

Run from the repository root with the analysis environment. Strict multibeam
wins wherever present; non-rejected final singlebeam fills other cells.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))  # make _common importable when run by path

from _common.file_io import atomic_write_text  # noqa: E402
NCEI_ROOT = REPO_ROOT / "ncei"
MB_PATH = NCEI_ROOT / "derived/validation_cells_1min/strict_primary_multibeam_cells.parquet"
SB_ROOT = NCEI_ROOT / "derived/singlebeam/file_cells_1min_final_r2"
OUTPUT_ROOT = NCEI_ROOT / "derived/global_grid_1min_r2"
MANIFEST_PATH = OUTPUT_ROOT / "product_manifest.json"
REPORT_PATH = NCEI_ROOT / "docs/step10_global_sb_products_report.md"
ROUND = "_r2"
SPOT_SEED = 20260903
OUTPUT_COLUMNS = [
    "cell_id", "lon_bin", "lat_bin", "lon_center", "lat_center", "depth_m",
    "source_layer", "sb_median_depth_m", "n_tracks_sb", "round",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, list[Path]]:
    mb = pd.read_parquet(
        MB_PATH,
        columns=[
            "cell_id", "lon_bin", "lat_bin", "lon_center", "lat_center",
            "representative_depth_m",
        ],
    )
    if mb["cell_id"].duplicated().any():
        raise AssertionError("strict MB cell_id is not unique")
    sb_files = sorted(SB_ROOT.glob("*.parquet"))
    if not sb_files:
        raise FileNotFoundError(f"no final SB parquet files under {SB_ROOT}")
    sb = ds.dataset([str(path) for path in sb_files], format="parquet").to_table(
        columns=[
            "track_id", "cell_id", "lon_bin", "lat_bin", "lon_center",
            "lat_center", "median_depth_m", "track_disposition",
        ]
    ).to_pandas()
    if sb.duplicated(["track_id", "cell_id"]).any():
        raise AssertionError("final SB track/cell identity is not unique")
    if not np.isfinite(mb["representative_depth_m"]).all():
        raise AssertionError("strict MB contains non-finite representative depth")
    accepted = sb.loc[sb["track_disposition"].ne("reject")].copy()
    if not np.isfinite(accepted["median_depth_m"]).all():
        raise AssertionError("accepted final SB contains non-finite median depth")
    return mb, accepted, sb_files


def aggregate_sb(sb: pd.DataFrame) -> pd.DataFrame:
    grouped = sb.groupby("cell_id", sort=True, observed=True)
    summary = grouped.agg(
        lon_bin=("lon_bin", "first"), lat_bin=("lat_bin", "first"),
        lon_center=("lon_center", "first"), lat_center=("lat_center", "first"),
        sb_median_depth_m=("median_depth_m", "median"),
        n_tracks_sb=("track_id", "nunique"),
        n_lon_bin=("lon_bin", "nunique"), n_lat_bin=("lat_bin", "nunique"),
        n_lon_center=("lon_center", "nunique"), n_lat_center=("lat_center", "nunique"),
    ).reset_index()
    if summary[["n_lon_bin", "n_lat_bin", "n_lon_center", "n_lat_center"]].ne(1).any().any():
        raise AssertionError("one SB cell_id maps to inconsistent grid coordinates")
    return summary.drop(columns=["n_lon_bin", "n_lat_bin", "n_lon_center", "n_lat_center"])


def merge_layers(mb: pd.DataFrame, sb: pd.DataFrame) -> pd.DataFrame:
    mb = mb.rename(columns={
        "lon_bin": "mb_lon_bin", "lat_bin": "mb_lat_bin",
        "lon_center": "mb_lon_center", "lat_center": "mb_lat_center",
        "representative_depth_m": "mb_depth_m",
    })
    sb = sb.rename(columns={
        "lon_bin": "sb_lon_bin", "lat_bin": "sb_lat_bin",
        "lon_center": "sb_lon_center", "lat_center": "sb_lat_center",
    })
    merged = mb.merge(sb, on="cell_id", how="outer", validate="one_to_one", indicator=True)
    overlap = merged["_merge"].eq("both")
    if not (
        merged.loc[overlap, "mb_lon_bin"].eq(merged.loc[overlap, "sb_lon_bin"]).all()
        and merged.loc[overlap, "mb_lat_bin"].eq(merged.loc[overlap, "sb_lat_bin"]).all()
        and np.allclose(merged.loc[overlap, "mb_lon_center"], merged.loc[overlap, "sb_lon_center"], rtol=0, atol=1e-12)
        and np.allclose(merged.loc[overlap, "mb_lat_center"], merged.loc[overlap, "sb_lat_center"], rtol=0, atol=1e-12)
    ):
        raise AssertionError("MB/SB overlap cell coordinates disagree")
    has_mb = merged["mb_depth_m"].notna()
    out = pd.DataFrame({
        "cell_id": merged["cell_id"].astype(str),
        "lon_bin": merged["mb_lon_bin"].where(has_mb, merged["sb_lon_bin"]).astype(np.int64),
        "lat_bin": merged["mb_lat_bin"].where(has_mb, merged["sb_lat_bin"]).astype(np.int64),
        "lon_center": merged["mb_lon_center"].where(has_mb, merged["sb_lon_center"]).astype(float),
        "lat_center": merged["mb_lat_center"].where(has_mb, merged["sb_lat_center"]).astype(float),
        "depth_m": merged["mb_depth_m"].where(has_mb, merged["sb_median_depth_m"]).astype(float),
        "source_layer": np.where(has_mb, "multibeam_strict", "singlebeam_final"),
        "sb_median_depth_m": merged["sb_median_depth_m"].astype(float),
        "n_tracks_sb": merged["n_tracks_sb"].astype("Int64"),
        "round": ROUND,
    })
    if out["cell_id"].duplicated().any() or not np.isfinite(out["depth_m"]).all():
        raise AssertionError("merged grid has duplicate cells or non-finite primary depths")
    return out[OUTPUT_COLUMNS]


def spot_checks(grid: pd.DataFrame, mb: pd.DataFrame) -> dict[str, list[dict]]:
    mb_depth = mb.set_index("cell_id")["representative_depth_m"]
    strict = grid.loc[grid["source_layer"].eq("multibeam_strict")]
    overlap = strict.loc[strict["sb_median_depth_m"].notna()]
    sb_only = grid.loc[grid["source_layer"].eq("singlebeam_final")]
    if min(len(strict), len(overlap), len(sb_only)) < 5:
        raise AssertionError("not enough cells for required spot checks")

    records: dict[str, list[dict]] = {}
    for name, frame in (("strict_mb", strict), ("overlap", overlap), ("sb_only", sb_only)):
        sample = frame.sample(n=5, random_state=SPOT_SEED).sort_values("cell_id")
        rows = []
        for row in sample.itertuples(index=False):
            if name in {"strict_mb", "overlap"}:
                expected = float(mb_depth.loc[row.cell_id])
                if not np.isclose(row.depth_m, expected, rtol=0, atol=1e-12):
                    raise AssertionError(f"MB spot check failed: {row.cell_id}")
            else:
                expected = float(row.sb_median_depth_m)
                if row.source_layer != "singlebeam_final" or not np.isclose(row.depth_m, expected, rtol=0, atol=1e-12):
                    raise AssertionError(f"SB-only spot check failed: {row.cell_id}")
            if name == "overlap" and (pd.isna(row.sb_median_depth_m) or pd.isna(row.n_tracks_sb)):
                raise AssertionError(f"overlap diagnostic missing: {row.cell_id}")
            rows.append({
                "cell_id": row.cell_id, "depth_m": float(row.depth_m),
                "expected_depth_m": expected,
                "sb_median_depth_m": None if pd.isna(row.sb_median_depth_m) else float(row.sb_median_depth_m),
                "passed": True,
            })
        records[name] = rows
    return records


def write_partitions(grid: pd.DataFrame) -> dict[int, int]:
    bands = np.floor(grid["lat_center"].to_numpy(dtype=float) / 10.0).astype(int) * 10
    bands = np.clip(bands, -90, 80)
    grid = grid.assign(lat_band_10deg=bands)
    counts = {}
    for band, part in grid.groupby("lat_band_10deg", sort=True):
        path = OUTPUT_ROOT / f"lat_band_10deg={int(band)}" / "part-00000.parquet"
        path.parent.mkdir(parents=True, exist_ok=False)
        part[OUTPUT_COLUMNS].to_parquet(path, index=False, engine="pyarrow")
        counts[int(band)] = len(part)
    return counts


def append_report(manifest: dict) -> None:
    heading = "## Global merged 1-arcminute grid r2"
    current = REPORT_PATH.read_text(encoding="utf-8")
    if heading in current:
        current = current.split(heading, 1)[0].rstrip()
    counts = manifest["counts"]
    lines = [
        "", heading, "",
        f"Generated: {manifest['created_at']}",
        f"Command: `{manifest['created_by']}`", "",
        f"The merged product contains {counts['total_rows']:,} unique 1-arcminute ship cells: "
        f"{counts['multibeam_strict']:,} use strict multibeam and "
        f"{counts['singlebeam_final']:,} are filled by non-rejected final singlebeam. "
        f"There are {counts['overlap_cells']:,} overlap cells; their primary depth is strict multibeam "
        "and their singlebeam median remains in `sb_median_depth_m`.", "",
        "| latitude band | rows |", "| ---: | ---: |",
    ]
    for band, count in sorted(manifest["latitude_band_rows"].items(), key=lambda item: int(item[0])):
        lines.append(f"| {band} | {count:,} |")
    lines.extend(["", "All 15 fixed-seed spot checks passed: five strict-MB cells, five overlap cells, and five SB-only cells.", ""])
    atomic_write_text(current.rstrip() + "\n" + "\n".join(lines), REPORT_PATH)


def main() -> int:
    if OUTPUT_ROOT.exists():
        raise SystemExit(f"round output already exists; preserve it and use a new round: {OUTPUT_ROOT}")
    mb, sb_rows, sb_files = load_inputs()
    sb = aggregate_sb(sb_rows)
    grid = merge_layers(mb, sb)
    checks = spot_checks(grid, mb)
    expected_union = len(set(mb["cell_id"]) | set(sb["cell_id"]))
    if len(grid) != expected_union or int(grid["source_layer"].eq("multibeam_strict").sum()) != len(mb):
        raise AssertionError("merged row counts do not reconcile with the input union")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=False)
    band_counts = write_partitions(grid)
    input_files = [MB_PATH, *sb_files]
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {
        "name": "global_grid_1min_r2", "round": ROUND, "created_at": created_at,
        "created_by": f"{sys.executable} ncei/code/31_build_global_grid_1min.py",
        "source_paths": [str(MB_PATH), str(SB_ROOT)],
        "input_file_counts": {"strict_multibeam": 1, "singlebeam_final": len(sb_files)},
        "input_sha256": {str(path): sha256(path) for path in input_files},
        "merge_rule": "strict multibeam wins; otherwise median non-reject final SB track cells; overlap SB median retained diagnostically; regional_mrar excluded",
        "columns": OUTPUT_COLUMNS, "partitioning": "hive lat_band_10deg", "depth_unit": "m, positive down",
        "counts": {
            "total_rows": len(grid),
            "multibeam_strict": int(grid["source_layer"].eq("multibeam_strict").sum()),
            "singlebeam_final": int(grid["source_layer"].eq("singlebeam_final").sum()),
            "overlap_cells": int(grid["source_layer"].eq("multibeam_strict").mul(grid["sb_median_depth_m"].notna()).sum()),
            "accepted_sb_cells": len(sb),
        },
        "latitude_band_rows": {str(key): value for key, value in band_counts.items()},
        "spot_check_seed": SPOT_SEED, "spot_checks": checks,
        "randomness": "fixed seed used only to select verification rows; product assembly is deterministic",
        "gebco": "not used", "regional_mrar": "excluded",
    }
    append_report(manifest)
    atomic_write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", MANIFEST_PATH)
    print(json.dumps(manifest["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
