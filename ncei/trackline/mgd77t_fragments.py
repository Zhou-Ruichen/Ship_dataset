#!/usr/bin/env python3
"""Task E step 2 — three-layer round-2 fragments for the static MGD77T corpus.

For every track converted by mgd77t_xyz.py, produces (all under
ncei/derived/sb_round2_static/, STANDALONE — no production product is
touched; merge awaits review):

  points_raw/<track_id>__xyz.parquet      16-col L1 (03's contract)
  points_checked/<track_id>__xyz.parquet  +6 QC columns (05's contract)
  file_cells_1min/<track_id>__xyz.parquet 23-col L2 (07's contract)
  sb_round2_static_source_manifest_fragment.parquet  L3 rows (26 cols)

Everything is reused by import, nothing copied:
  - manifest.depth_sign                    (per-track sign)
  - standardize_xyz.standardize_one_track   (L1 core)
  - point_qc.compute_flag_arrays            (QC columns)
  - file_cells.aggregate_track_file        (L2)
  - _common.r2_classifier.classify          (instrument class)

source_type is 'ncei_xyz' (closed enum preserved); source_completeness is
'xyz_only' in the fragment and must be re-resolved to 'nc_xyz_intersect'
at merge time for the tracks that pair with a local nc track.

Run from repo root:
    python -m ncei.trackline mgd77t-fragments [--tracks a b ...] [--workers 8]
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

from _common.r2_classifier import classify
from . import file_cells, manifest, point_qc, standardize_xyz

REPO_ROOT = Path(__file__).resolve().parents[2]
XYZ_ROOT = REPO_ROOT / "ncei/raw_round2/mgd77t_static_xyz"
OUT_ROOT = REPO_ROOT / "ncei/derived/sb_round2_static"
CONV_MANIFEST = XYZ_ROOT / "conversion_manifest.parquet"

COLUMNS = [
    "track_id", "source_type", "source_completeness", "source_path", "source_archive",
    "n_points", "bbox_lon_min", "bbox_lon_max", "bbox_lat_min", "bbox_lat_max",
    "bbox_area_km2", "point_density_km2",
    "has_time", "has_depth", "has_gobs", "has_faa",
    "depth_sign_raw", "depth_min_raw", "depth_max_raw",
    "instrument_class_pred", "classification_rule", "classification_review",
    "review_reason", "manual_override",
    "source_author", "survey_id",
]
SOURCE_ARCHIVE = "NCEI static MGD77T tree (round2, 2026-09)"


def process_track(track_id: str, survey: str) -> dict:
    xyz_path = XYZ_ROOT / f"{track_id}.xyz"
    raw_out = OUT_ROOT / "points_raw" / f"{track_id}__xyz.parquet"
    chk_out = OUT_ROOT / "points_checked" / f"{track_id}__xyz.parquet"
    cells_out = OUT_ROOT / "file_cells_1min" / f"{track_id}__xyz.parquet"

    lon, lat, depth = standardize_xyz.read_xyz_full(xyz_path)
    n_points = int(lon.size)
    finite_depth = depth[np.isfinite(depth)]
    sign = manifest.depth_sign(finite_depth) if finite_depth.size else "no_depth_values"

    points, summary = standardize_xyz.standardize_one_track(
        xyz_path, track_id, "xyz_only", "singlebeam", sign
    )
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    points.to_parquet(raw_out.with_suffix(".parquet.tmp"), index=False)
    os.replace(raw_out.with_suffix(".parquet.tmp"), raw_out)

    flags = point_qc.compute_flag_arrays(
        points["lon"].to_numpy(dtype=np.float64),
        points["lat"].to_numpy(dtype=np.float64),
        points["depth_m_positive_down"].to_numpy(dtype=np.float64),
    )
    checked = points.copy()
    for name, arr in flags.items():
        checked[name] = arr
    chk_out.parent.mkdir(parents=True, exist_ok=True)
    checked.to_parquet(chk_out.with_suffix(".parquet.tmp"), index=False)
    os.replace(chk_out.with_suffix(".parquet.tmp"), chk_out)

    l2 = file_cells.aggregate_track_file(
        input_path=chk_out,
        output_path=cells_out,
        track_id=track_id,
        source_type="ncei_xyz",
        source_completeness="xyz_only",
        instrument_class_pred="singlebeam",
        branch="singlebeam",
        manual_review_flag=False,
        overwrite=True,
    )

    if n_points:
        lon_min, lon_max = float(np.min(lon)), float(np.max(lon))
        lat_min, lat_max = float(np.min(lat)), float(np.max(lat))
        lat_mid = 0.5 * (lat_min + lat_max)
        area = (lon_max - lon_min) * (lat_max - lat_min) * math.cos(math.radians(lat_mid)) * 111.32 * 111.32
    else:
        lon_min = lon_max = lat_min = lat_max = math.nan
        area = math.nan
    density = n_points / area if area and area > 0 else (math.inf if n_points else math.nan)
    result = classify(lon, lat) if n_points else None
    pred = "multibeam" if (result is not None and result.label == "mb") else "singlebeam"
    rule = result.reason if result is not None else ""
    finite = finite_depth
    l3 = {
        "track_id": track_id,
        "source_type": "ncei_xyz",
        "source_completeness": "xyz_only",
        "source_path": f"raw_round2/mgd77t_static_xyz/{track_id}.xyz",
        "source_archive": SOURCE_ARCHIVE,
        "n_points": n_points,
        "bbox_lon_min": lon_min, "bbox_lon_max": lon_max,
        "bbox_lat_min": lat_min, "bbox_lat_max": lat_max,
        "bbox_area_km2": area, "point_density_km2": density,
        "has_time": False,
        "has_depth": finite.size > 0,
        "has_gobs": False, "has_faa": False,
        "depth_sign_raw": sign,
        "depth_min_raw": float(np.min(finite)) if finite.size else math.nan,
        "depth_max_raw": float(np.max(finite)) if finite.size else math.nan,
        "instrument_class_pred": pred,
        "classification_rule": rule,
        "classification_review": bool(pred == "multibeam"),
        "review_reason": rule if pred == "multibeam" else "",
        "manual_override": "",
        "source_author": None,
        "survey_id": survey,
    }
    return {"track_id": track_id, "n_points": n_points, "sign": sign,
            "n_cells": l2["n_cells"], "pred": pred, "l3": l3}


def _worker(track_id: str, survey: str) -> dict:
    try:
        return {"ok": True, **process_track(track_id, survey)}
    except Exception as error:  # noqa: BLE001 — per-track isolation
        return {"ok": False, "track_id": track_id, "error": f"{type(error).__name__}: {error}"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ncei.trackline mgd77t-fragments", description=__doc__)
    parser.add_argument("--tracks", nargs="*", default=None)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)

    conv = pd.read_parquet(CONV_MANIFEST)
    work = [(r.track_id, r.survey) for r in conv.itertuples()
            if args.tracks is None or r.track_id in set(args.tracks)]
    print(f"{len(work)} tracks")

    import multiprocessing as mp
    l3_rows: list[dict] = []
    failures: list[dict] = []
    with mp.Pool(args.workers) as pool:
        for i, res in enumerate(pool.starmap(_worker, work)):
            if res["ok"]:
                l3_rows.append(res["l3"])
            else:
                failures.append(res)
            if (i + 1) % 100 == 0:
                print(f"{i+1}/{len(work)}")

    fragment = pd.DataFrame(l3_rows, columns=COLUMNS)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    frag_path = OUT_ROOT / "sb_round2_static_source_manifest_fragment.parquet"
    fragment.to_parquet(frag_path.with_suffix(".parquet.tmp"), index=False)
    os.replace(frag_path.with_suffix(".parquet.tmp"), frag_path)
    fragment.to_csv(OUT_ROOT / "sb_round2_static_source_manifest_fragment.tsv", sep="\t", index=False)
    if failures:
        pd.DataFrame(failures).to_csv(OUT_ROOT / "failures.tsv", sep="\t", index=False)
    print(f"ok {len(l3_rows)}, failed {len(failures)}")
    print(f"sign distribution: {fragment.depth_sign_raw.value_counts().to_dict()}")
    print(f"class distribution: {fragment.instrument_class_pred.value_counts().to_dict()}")
    print(f"total cells: {int(fragment.n_points.notna().sum())} tracks; fragment: {frag_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
