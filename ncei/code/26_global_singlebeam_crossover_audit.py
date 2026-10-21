#!/usr/bin/env python3
"""Audit true geometric crossovers for all usable global SB nc/xyz tracks.

The exact segment-intersection, interpolation, ordering, time-QC, and gap rules
are imported from step 09 script 24. Existing manifests and derived products are
read-only. GEBCO and multibeam data are never opened.

Inputs:
  - ncei/manifests/trackline_source_manifest.parquet (track selection)
  - ncei/derived/singlebeam/points_raw/*__nc.parquet and *__xyz.parquet

Outputs (ncei/derived/global_sb_crossover_audit/):
  - crossovers.parquet, pair_stats.parquet, track_stats.parquet,
    nc_time_qc.parquet, source_pair_summary.parquet,
    sign_convention_summary.parquet, six_region_spot_check.parquet,
    tile_summary.parquet, tiles/crossovers_<tile>.parquet
  - report: ncei/docs/step10_global_sb_products_report.md

Run from repo root:
    python ncei/code/26_global_singlebeam_crossover_audit.py [--overwrite]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))  # make _common importable when run by path

from _common.file_io import atomic_write_parquet, atomic_write_text  # noqa: E402
NCEI_ROOT = REPO_ROOT / "ncei"
SCRIPT24_PATH = NCEI_ROOT / "code/24_true_crossover_audit.py"
MANIFEST_PATH = NCEI_ROOT / "manifests/trackline_source_manifest.parquet"
POINTS_ROOT = NCEI_ROOT / "derived/singlebeam/points_raw"
OUT_ROOT = NCEI_ROOT / "derived/global_sb_crossover_audit"
TILE_ROOT = OUT_ROOT / "tiles"
REPORT_PATH = NCEI_ROOT / "docs/step10_global_sb_products_report.md"
BIAS_PATH = NCEI_ROOT / "derived/sb_track_bias_global/track_bias_summary.parquet"
COVERAGE_PATH = NCEI_ROOT / "derived/sb_track_bias_global/coverage_summary.parquet"
ADJUSTED_ROOT = NCEI_ROOT / "derived/singlebeam/file_cells_1min_adjusted"
LOCAL_AUDIT_ROOT = NCEI_ROOT / "derived/true_crossover_audit"
TILE_SIZE_DEG = 10.0
MIN_TILE_SIZE_DEG = 0.01953125
MAX_SEGMENTS_PER_TILE = 100_000


def import_step09():
    spec = importlib.util.spec_from_file_location("step09_true_crossover", SCRIPT24_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {SCRIPT24_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STEP09 = import_step09()
EVENT_COLUMNS = STEP09.EVENT_COLUMNS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite", action="store_true", help="replace this script's outputs")
    return parser.parse_args()


def logger() -> logging.Logger:
    log = logging.getLogger("global_sb_crossover")
    log.handlers.clear()
    log.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(levelname)-8s %(message)s"))
    log.addHandler(handler)
    return log


def global_tiles(manifest: pd.DataFrame) -> list[tuple[str, tuple[float, float, float, float]]]:
    tiles = []
    for south in np.arange(-90.0, 90.0, TILE_SIZE_DEG):
        for west in np.arange(-180.0, 180.0, TILE_SIZE_DEG):
            bbox = (float(west), float(west + TILE_SIZE_DEG), float(south), float(south + TILE_SIZE_DEG))
            if len(STEP09.select_region_tracks(manifest, bbox)) >= 2:
                name = f"lon{int(west + 180):03d}_lat{int(south + 90):03d}"
                tiles.append((name, bbox))
    return tiles


def full_nc_time_qc(manifest: pd.DataFrame) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for rec in manifest.loc[manifest["source_type"].eq("ncei_nc")].itertuples(index=False):
        path = POINTS_ROOT / f"{rec.track_id}__nc.parquet"
        if not path.exists():
            continue
        times = pd.read_parquet(path, columns=["time"])["time"]
        rows[str(rec.track_id)] = STEP09.nc_time_qc_row(
            str(rec.track_id), STEP09.time_to_seconds(times)
        )
    return rows


def split_bbox(name: str, bbox) -> list[tuple[str, tuple[float, float, float, float]]]:
    west, east, south, north = bbox
    mid_lon = (west + east) / 2.0
    mid_lat = (south + north) / 2.0
    return [
        (f"{name}_sw", (west, mid_lon, south, mid_lat)),
        (f"{name}_se", (mid_lon, east, south, mid_lat)),
        (f"{name}_nw", (west, mid_lon, mid_lat, north)),
        (f"{name}_ne", (mid_lon, east, mid_lat, north)),
    ]


def process_tile(name: str, bbox, manifest, time_qc, log, allow_split: bool = True):
    selected = STEP09.select_region_tracks(manifest, bbox)
    tracks = STEP09.load_region(selected, bbox, log, time_qc)
    if tracks.n_tracks_used == 0:
        events = pd.DataFrame(columns=EVENT_COLUMNS)
        counts = {"raw": 0, "inside": 0, "nan_depth": 0, "finite": 0, "dup": 0, "final": 0}
        candidates = parallel = intersecting = segments = 0
    else:
        x1 = tracks.flat("x1")
        segments = len(x1)
        if segments == 0:
            events = pd.DataFrame(columns=EVENT_COLUMNS)
            counts = {"raw": 0, "inside": 0, "nan_depth": 0, "finite": 0, "dup": 0, "final": 0}
            candidates = parallel = intersecting = 0
        elif allow_split and segments > MAX_SEGMENTS_PER_TILE and (bbox[1] - bbox[0]) > MIN_TILE_SIZE_DEG:
            log.info(
                "split %s: %d segments exceeds %d", name, segments, MAX_SEGMENTS_PER_TILE
            )
            return None, split_bbox(name, bbox)
        else:
            STEP09.GRID_CELL_DEG = 0.02 if not allow_split else (
                0.002 if segments > 100_000 else 0.02
            )
            _, ranks = np.unique(np.asarray(tracks.track_ids), return_inverse=True)
            segment_ranks = ranks[tracks.flat("seg_track")]
            ci, cj = STEP09.grid_candidate_pairs(
                x1, tracks.flat("y1"), tracks.flat("x2"), tracks.flat("y2"),
                segment_ranks, int(ranks.max()) + 1, log,
            )
            candidates = len(ci)
            raw, parallel = STEP09.exact_intersections(tracks, ci, cj, log)
            intersecting = len(raw["cx"])
            events, counts = STEP09.orient_and_filter(raw, tracks, bbox, log)
    atomic_write_parquet(events, TILE_ROOT / f"crossovers_{name}.parquet")
    return {
        "tile": name, "west": bbox[0], "east": bbox[1], "south": bbox[2], "north": bbox[3],
        "n_tracks_used": tracks.n_tracks_used, "n_nc": tracks.n_nc, "n_xyz": tracks.n_xyz,
        "n_segments": int(segments), "n_candidates": int(candidates),
        "n_parallel": int(parallel), "n_intersecting": int(intersecting),
        "n_crossovers": int(counts["final"]), "n_nan_depth_dropped": int(counts["nan_depth"]),
        "n_duplicates_dropped": int(counts["dup"]),
    }, []


def deduplicate_global(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return events[EVENT_COLUMNS]
    work = events.copy()
    lon = pd.to_numeric(work["crossing_lon"]).to_numpy(dtype=float)
    lat = pd.to_numeric(work["crossing_lat"]).to_numpy(dtype=float)
    work["_lon_key"] = np.rint(lon / STEP09.DEDUP_EPS_DEG).astype(np.int64)
    work["_lat_key"] = np.rint(lat / STEP09.DEDUP_EPS_DEG).astype(np.int64)
    work = work.sort_values(["pair_key", "source_type_pair", "_lon_key", "_lat_key"])
    work = work.drop_duplicates(
        ["pair_key", "source_type_pair", "_lon_key", "_lat_key"], keep="first"
    )
    return work.drop(columns=["_lon_key", "_lat_key"])[EVENT_COLUMNS].reset_index(drop=True)


def pair_track_stats(events: pd.DataFrame, manifest: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    pair = (
        events.groupby(
            ["pair_key", "track_id_first", "track_id_second", "source_type_pair"], sort=True
        )
        .agg(
            n_crossovers=("diff_m", "size"),
            median_diff_m=("diff_m", "median"),
            nmad_diff_m=("diff_m", STEP09.nmad),
            median_abs_diff_m=("diff_m", lambda x: float(np.median(np.abs(x)))),
            n_ordered_by_time=("ordering_basis", lambda x: int(x.eq("time").sum())),
        )
        .reset_index()
    )
    a = pd.DataFrame({
        "track_id": events["track_id_first"],
        "partner": events["track_id_second"],
        "residual_m": events["depth_first_m"] - events["depth_second_m"],
    })
    b = pd.DataFrame({
        "track_id": events["track_id_second"],
        "partner": events["track_id_first"],
        "residual_m": events["depth_second_m"] - events["depth_first_m"],
    })
    both = pd.concat([a, b], ignore_index=True)
    track = (
        both.groupby("track_id", sort=True)
        .agg(
            n_crossovers=("residual_m", "size"),
            n_partner_tracks=("partner", "nunique"),
            median_signed_diff_m=("residual_m", "median"),
            median_abs_diff_m=("residual_m", lambda x: float(np.median(np.abs(x)))),
            nmad_signed_diff_m=("residual_m", STEP09.nmad),
        )
        .reset_index()
    )
    branches = (
        manifest.groupby("track_id")["source_type"]
        .agg(lambda x: "+".join(sorted({"nc" if v == "ncei_nc" else "xyz" for v in x})))
    )
    track["branches"] = track["track_id"].map(branches)
    return pair, track


def source_summary(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pair_type in ("nc_x_nc", "nc_x_xyz", "xyz_x_xyz"):
        part = events.loc[events["source_type_pair"].eq(pair_type)]
        diff = part["diff_m"].to_numpy(dtype=float)
        rows.append({
            "source_type_pair": pair_type,
            "n_track_pairs": int(part["pair_key"].nunique()),
            "n_crossovers": int(len(part)),
            "median_abs_diff_m": float(np.median(np.abs(diff))) if len(diff) else np.nan,
            "p90_abs_diff_m": float(np.percentile(np.abs(diff), 90)) if len(diff) else np.nan,
            "nmad_signed_diff_m": STEP09.nmad(diff),
        })
    return pd.DataFrame(rows)


def sign_summary(events: pd.DataFrame) -> pd.DataFrame:
    records = []
    for branch in ("nc", "xyz"):
        values = []
        if branch == "nc":
            values.extend(events.loc[events.source_type_pair.isin(["nc_x_nc", "nc_x_xyz"]), "depth_first_m"])
            values.extend(events.loc[events.source_type_pair.eq("nc_x_nc"), "depth_second_m"])
        else:
            values.extend(events.loc[events.source_type_pair.eq("xyz_x_xyz"), "depth_first_m"])
            values.extend(events.loc[events.source_type_pair.isin(["nc_x_xyz", "xyz_x_xyz"]), "depth_second_m"])
        array = np.asarray(values, dtype=float)
        records.append({
            "branch": branch, "n_interpolated_depths": len(array),
            "n_negative_depths": int((array < 0).sum()),
            "fraction_nonnegative": float((array >= 0).mean()) if len(array) else np.nan,
            "median_depth_m_positive_down": float(np.median(array)) if len(array) else np.nan,
        })
    return pd.DataFrame(records)


def six_region_check(manifest, time_qc, log) -> pd.DataFrame:
    rows = []
    for region, bbox in STEP09.REGIONS.items():
        name = f"spot_{region}"
        path = TILE_ROOT / f"crossovers_{name}.parquet"
        if not path.exists():
            process_tile(name, bbox, manifest, time_qc, log, allow_split=False)
        observed = pd.read_parquet(path, columns=["pair_key"])
        reference_path = LOCAL_AUDIT_ROOT / f"crossovers_{region}.parquet"
        expected = len(pd.read_parquet(reference_path, columns=["pair_key"]))
        rows.append({
            "region": region, "expected_crossovers": expected,
            "observed_crossovers": len(observed), "matched": len(observed) == expected,
        })
    return pd.DataFrame(rows)


def format_float(value) -> str:
    return "NA" if pd.isna(value) else f"{value:.2f}"


def write_report(events, pair_summary, time_qc, spot, sign, runtime_s) -> None:
    biases = pd.read_parquet(BIAS_PATH)
    coverage = pd.read_parquet(COVERAGE_PATH)
    adjusted_files = list(ADJUSTED_ROOT.glob("*.parquet"))
    adjusted_rows = sum(pq_rows(path) for path in adjusted_files)
    applied = biases.loc[biases["applied"]]
    lines = [
        "# Step 10 global singlebeam products",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}  ",
        f"Interpreter: `{sys.executable}`  ",
        f"Global crossover runtime: {runtime_s:.1f} s",
        "",
        "## Global track bias and adjusted cells",
        "",
        f"The bias table contains {len(biases):,} SB tracks with at least one strict-MB co-located 1-minute cell. "
        f"The gate applied a constant correction to {len(applied):,} tracks; "
        f"{biases.gate_reason.eq('thin_evidence').sum():,} had fewer than five support cells and "
        f"{biases.gate_reason.eq('not_significant').sum():,} did not meet `|bias| >= 2 * NMAD`.",
        "",
        f"Applied signed bias (m, SB minus strict MB): minimum {format_float(applied.bias_m.min())}, "
        f"median {format_float(applied.bias_m.median())}, maximum {format_float(applied.bias_m.max())}; "
        f"median absolute bias {format_float(applied.bias_m.abs().median())}.",
        "",
        f"The adjusted product contains {len(adjusted_files):,} per-track files and {adjusted_rows:,} cell rows. "
        "It preserves the actual upstream field name `median_depth_m`; the PRD's `depth_median_m` wording "
        "does not match the existing schema. Added provenance fields are `track_bias_m`, `bias_applied`, "
        "and `bias_n_support`.",
        "",
        "The bias reference is `strict_primary_multibeam_cells.parquet` only. No SB leave-one-out reference, "
        "regional_mrar, GEBCO, or downstream evaluation data is used.",
        "",
        "## Global crossover audit",
        "",
        f"The audit found {len(events):,} crossovers over {events.pair_key.nunique():,} track pairs. "
        "It imports the exact segment intersection, linear interpolation, gap, ordering, and nc time-QC "
        "functions from script 24. Global processing uses 10-degree tiles and removes repeated boundary events.",
        "",
        "| branch pair | track pairs | crossovers | median |difference| (m) | p90 |difference| (m) | NMAD signed (m) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in pair_summary.itertuples(index=False):
        lines.append(
            f"| {row.source_type_pair} | {row.n_track_pairs:,} | {row.n_crossovers:,} | "
            f"{format_float(row.median_abs_diff_m)} | {format_float(row.p90_abs_diff_m)} | "
            f"{format_float(row.nmad_signed_diff_m)} |"
        )
    lines.extend([
        "",
        f"nc time QC covers {len(time_qc):,} usable tracks: "
        f"{time_qc.n_time_nat.gt(0).sum():,} contain missing times, "
        f"{time_qc.monotonic_ok.eq(False).sum():,} fail monotonicity, and "
        f"{time_qc.epoch_ok.eq(False).sum():,} fail the 1930-2035 epoch check.",
        "",
        "Crossover-interpolated depths use metres positive down. The sign table records the observed "
        "nonnegative share for each branch; it is a convention check at actual geometric crossings, not an accuracy test.",
        "",
        "| branch | interpolated depths | negative | nonnegative share | median depth (m positive down) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for row in sign.itertuples(index=False):
        lines.append(
            f"| {row.branch} | {row.n_interpolated_depths:,} | {row.n_negative_depths:,} | "
            f"{row.fraction_nonnegative:.6f} | {format_float(row.median_depth_m_positive_down)} |"
        )
    lines.extend([
        "",
        "The six-region event-count comparison reruns each original 5-degree bbox with the imported "
        "step 09 machinery, then compares against the retained step 09 event parquets:",
        "",
        "| region | step 09 | same-bbox rerun | match |",
        "| --- | ---: | ---: | --- |",
    ])
    for row in spot.itertuples(index=False):
        lines.append(
            f"| {row.region} | {row.expected_crossovers:,} | {row.observed_crossovers:,} | "
            f"{'yes' if row.matched else 'no'} |"
        )
    lines.extend([
        "",
        "This is a same-bbox reproducibility check, not a crop of the adaptive global table. "
        "The global audit subdivides dense 10-degree tiles and uses endpoint margins; direct regional "
        "crops of that table can therefore differ at tile boundaries.",
    ])
    lines.extend([
        "",
        "## Global coverage",
        "",
        "Coverage maps use a fixed global longitude/latitude window. Color is the number of occupied "
        "1-minute cells in each 1-degree plotting bin.",
        "",
        "| source | occupied 1-minute cells | occupied 1-degree bins | maximum per 1-degree bin |",
        "| --- | ---: | ---: | ---: |",
    ])
    for row in coverage.itertuples(index=False):
        lines.append(
            f"| {row.source} | {row.n_occupied_1min_cells:,} | {row.n_occupied_1deg_bins:,} | "
            f"{row.max_1min_cells_per_1deg_bin:,} |"
        )
    lines.extend([
        "",
        "The historical strict-MB table has a label mismatch that is left unchanged: rows with "
        "`source_provider=jamstec` carry `source_dataset=NCEI_multibeam`, while "
        "`source_provider=ncei_multibeam` rows carry `source_dataset=NCEI`. New coverage outputs use "
        "the actual providers: JAMSTEC multibeam and NCEI multibeam.",
        "",
        "## How downstream should consume this",
        "",
        "Use `ncei/derived/singlebeam/file_cells_1min_adjusted/` instead of the raw "
        "`file_cells_1min/` directory. Keep `median_depth_m` as metres positive down and retain the three "
        "bias provenance fields when aggregating tracks. `bias_applied=False` with support greater than zero "
        "means the estimator was gated off; support zero means no strict-MB co-location was available.",
        "",
        "Do not add `regional_mrar` to this product. It is a regional point cloud without per-track order, "
        "so the per-track constant-bias and crossover procedures used here do not apply to it.",
        "",
        "The adjusted SB cells are an upstream product. Downstream projects remain responsible for their own "
        "training, validation, and evaluation separation.",
        "",
        "## Outputs",
        "",
        "- `ncei/derived/sb_track_bias_global/track_bias_summary.parquet`",
        "- `ncei/derived/singlebeam/file_cells_1min_adjusted/*.parquet`",
        "- `ncei/derived/global_sb_crossover_audit/*.parquet`",
        "- `ncei/figures/coverage_global/*.png`",
        "",
    ])
    atomic_write_text("\n".join(lines), REPORT_PATH)


def pq_rows(path: Path) -> int:
    import pyarrow.parquet as pq
    return pq.ParquetFile(path).metadata.num_rows


def main() -> int:
    args = parse_args()
    log = logger()
    start = time.time()
    manifest = pd.read_parquet(MANIFEST_PATH, columns=STEP09.MANIFEST_COLUMNS + ["instrument_class_pred"])
    manifest = manifest.loc[manifest.instrument_class_pred.eq("singlebeam")].drop(columns="instrument_class_pred")
    time_qc = full_nc_time_qc(manifest)
    tiles = global_tiles(manifest)
    tile_rows = []
    completed_tiles: list[tuple[str, tuple[float, float, float, float]]] = []
    queue = list(tiles)
    index = 0
    while queue:
        name, bbox = queue.pop(0)
        index += 1
        path = TILE_ROOT / f"crossovers_{name}.parquet"
        if path.exists() and not args.overwrite:
            log.info("tile %d/%d+ %s exists; reuse", index, index + len(queue), name)
            tile_rows.append({"tile": name, "west": bbox[0], "east": bbox[1], "south": bbox[2], "north": bbox[3], "reused": True})
            completed_tiles.append((name, bbox))
            continue
        log.info("tile %d/%d+ %s bbox=%s", index, index + len(queue), name, bbox)
        row, children = process_tile(name, bbox, manifest, time_qc, log)
        if children:
            queue = children + queue
            continue
        tile_rows.append(row)
        completed_tiles.append((name, bbox))

    parts = [pd.read_parquet(TILE_ROOT / f"crossovers_{name}.parquet") for name, _ in completed_tiles]
    events = deduplicate_global(pd.concat(parts, ignore_index=True))
    pair, track = pair_track_stats(events, manifest)
    summary = source_summary(events)
    sign = sign_summary(events)
    qc = pd.DataFrame(list(time_qc.values())).sort_values("track_id").reset_index(drop=True)
    spot = six_region_check(manifest, time_qc, log)

    atomic_write_parquet(events, OUT_ROOT / "crossovers.parquet")
    atomic_write_parquet(pair, OUT_ROOT / "pair_stats.parquet")
    atomic_write_parquet(track, OUT_ROOT / "track_stats.parquet")
    atomic_write_parquet(qc, OUT_ROOT / "nc_time_qc.parquet")
    atomic_write_parquet(summary, OUT_ROOT / "source_pair_summary.parquet")
    atomic_write_parquet(sign, OUT_ROOT / "sign_convention_summary.parquet")
    atomic_write_parquet(spot, OUT_ROOT / "six_region_spot_check.parquet")
    atomic_write_parquet(pd.DataFrame(tile_rows), OUT_ROOT / "tile_summary.parquet")
    runtime_s = time.time() - start
    write_report(events, summary, qc, spot, sign, runtime_s)
    atomic_write_text(json.dumps({
        "name": "global_singlebeam_crossover_audit",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": f"{sys.executable} ncei/code/26_global_singlebeam_crossover_audit.py --overwrite",
        "source_paths": [str(MANIFEST_PATH), str(POINTS_ROOT), str(SCRIPT24_PATH)],
        "outputs": [str(OUT_ROOT), str(REPORT_PATH)],
        "tile_size_deg": TILE_SIZE_DEG,
        "tile_margin_deg": STEP09.MARGIN_DEG,
        "n_crossovers": len(events),
        "n_track_pairs": int(events.pair_key.nunique()),
        "six_region_counts_match": bool(spot.matched.all()),
        "depth_unit": "m, positive down",
        "regional_mrar": "excluded",
        "gebco": "not used",
        "randomness": "none",
    }, indent=2) + "\n", OUT_ROOT / "product_manifest.json")
    print(f"Wrote {len(events)} global crossovers; six-region counts match={spot.matched.all()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
