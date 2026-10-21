#!/usr/bin/env python3
"""Stage 5 — read-only coverage statistics vs the strict primary layer.

Compares the union of new mb_round2 L2 cells against
ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet:

  a) global count of new strict-admissible cells (cells not present in
     the strict layer — note: strict admission itself is a downstream
     decision; here we only measure the cell-id delta);
  b) new cells inside each of the six downstream regions defined in
     /mnt/data2/06-Projects/15-swot_feature_physics_bathy/configs/feasibility/final_data_round.yaml
     (read-only reference);
  c) overlap ratio with the existing strict layer.

Writes ncei/derived/mb_round2/coverage_vs_strict_primary.parquet and
prints the tables. Does not update any deliverable.

Run from repo root:
    python -m ncei.swath coverage
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

from _common.file_io import atomic_write_parquet

OUT_ROOT = REPO_ROOT / "ncei/derived/mb_round2"
STRICT_PATH = REPO_ROOT / "ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet"
REGIONS_YAML = Path("/mnt/data2/06-Projects/15-swot_feature_physics_bathy/configs/feasibility/final_data_round.yaml")

# Cells with both |lon_center| and |lat_center| below this bound are
# pre-GPS-lock navigation artifacts (a file's first ping parked near (0,0)).
# Deterministic rule; counted everywhere, filtered nowhere.
NAV_ORIGIN_DEG = 1.0


def nav_origin_mask(lon_deg: np.ndarray, lat_deg: np.ndarray) -> np.ndarray:
    return (np.abs(lon_deg) < NAV_ORIGIN_DEG) & (np.abs(lat_deg) < NAV_ORIGIN_DEG)


def coverage_stats(out_root: Path = OUT_ROOT) -> int:
    new_frames = []
    for cells_path in sorted(out_root.glob("*/file_cells_1min/*.parquet")):
        df = pd.read_parquet(cells_path, columns=["cell_id", "lon_center", "lat_center", "track_id"])
        new_frames.append(df)
    if not new_frames:
        print("no L2 outputs found; run stage 3 first")
        return 1
    new = pd.concat(new_frames, ignore_index=True)
    new["track_id"] = new["track_id"].astype(str)
    per_track_counts = new.groupby("track_id")["cell_id"].nunique()

    # Union across tracks (a cell produced by several cruises counts once).
    # nav-origin artifact cells are flagged deterministically (see
    # nav_origin_mask) and carried onto the union table by cell_id.
    new["suspect_nav_origin"] = nav_origin_mask(new["lon_center"].to_numpy(), new["lat_center"].to_numpy())
    union = new.drop_duplicates("cell_id").reset_index(drop=True)
    strict = pd.read_parquet(STRICT_PATH, columns=["cell_id"])
    strict_ids = set(strict["cell_id"].astype(str))
    union["in_strict"] = union["cell_id"].isin(strict_ids)

    regions_spec = yaml.safe_load(REGIONS_YAML.read_text(encoding="utf-8"))
    regions = regions_spec["regions"]

    lon = union["lon_center"].to_numpy()
    lat = union["lat_center"].to_numpy()
    region_labels = {}
    for region in regions:
        rid = str(region["id"])
        west, east = float(region["west"]), float(region["east"])
        south, north = float(region["south"]), float(region["north"])
        mask = (lon >= west) & (lon < east) & (lat >= south) & (lat < north)
        region_labels[rid] = mask

    rows = [{
        "scope": "global",
        "region_id": "",
        "n_new_cells": int(len(union)),
        "n_new_cells_in_strict": int(union["in_strict"].sum()),
        "n_new_cells_not_in_strict": int((~union["in_strict"]).sum()),
        "overlap_ratio": float(union["in_strict"].mean()),
        "n_suspect_nav_origin_cells": int(union["suspect_nav_origin"].sum()),
    }]
    for rid, mask in region_labels.items():
        sub = union[mask]
        rows.append({
            "scope": "region",
            "region_id": rid,
            "n_new_cells": int(len(sub)),
            "n_new_cells_in_strict": int(sub["in_strict"].sum()),
            "n_new_cells_not_in_strict": int((~sub["in_strict"]).sum()),
            "overlap_ratio": float(sub["in_strict"].mean()) if len(sub) else float("nan"),
            "n_suspect_nav_origin_cells": int(sub["suspect_nav_origin"].sum()),
        })

    out = pd.DataFrame(rows)
    out_path = out_root / "coverage_vs_strict_primary.parquet"
    atomic_write_parquet(out, out_path)

    print("== per-cruise unique cells ==")
    print(per_track_counts.to_string())
    print("\n== coverage vs strict primary ==")
    print(out.to_string(index=False))
    print(f"\nstats: {os.path.relpath(out_path, REPO_ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(prog="python -m ncei.swath coverage", description=__doc__).parse_args(argv)
    return coverage_stats()


if __name__ == "__main__":
    raise SystemExit(main())
