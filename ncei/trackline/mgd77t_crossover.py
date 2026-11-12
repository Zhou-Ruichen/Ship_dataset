"""Use the existing six-region crossover geometry on source-indexed MGD77T."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

from . import crossover


ENDPOINT_FIELDS = (
    "source_observation_index_0based_start", "source_observation_index_0based_end",
    "source_line_1based_start", "source_line_1based_end",
)


def load_source_region(
    root: Path, selected: pd.DataFrame, bbox: tuple[float, float, float, float],
    policy: str,
) -> tuple[crossover.RegionTracks, list[dict]]:
    """Break segments at omitted source observations, not filtered table rows."""
    rt = crossover.RegionTracks()
    for field in ENDPOINT_FIELDS:
        setattr(rt, field, [])
    rt.segment_time_decreases = []
    track_rows = []
    lon0, lon1, lat0, lat1 = bbox
    margin = crossover.MARGIN_DEG
    selection = "point_check_pass_basic" if policy == "basic" else "point_selected_basic_source_quality"
    for row in selected.itertuples(index=False):
        path = root / "points_checked" / f"{row.track_id}__mgd77t.parquet"
        points = (
            pl.scan_parquet(path)
            .filter(
                pl.col(selection)
                & pl.col("lon").is_between(lon0 - margin, lon1 + margin)
                & pl.col("lat").is_between(lat0 - margin, lat1 + margin)
            )
            .select(
                "source_observation_index_0based", "source_line_1based", "lon", "lat",
                "depth_m_positive_down", "time_utc_seconds",
            )
            .sort("source_observation_index_0based")
            .collect()
        )
        index = points["source_observation_index_0based"].to_numpy()
        line = points["source_line_1based"].to_numpy()
        lon, lat = points["lon"].to_numpy(), points["lat"].to_numpy()
        depth, utc = points["depth_m_positive_down"].to_numpy(), points["time_utc_seconds"].to_numpy()
        continuous = np.diff(index) == 1
        spacing = np.hypot(np.diff(lon), np.diff(lat))
        nonzero = (np.diff(lon) != 0) | (np.diff(lat) != 0)
        link = continuous & (spacing <= crossover.GAP_BREAK_DEG)
        good = link & nonzero
        n_segments = int(good.sum())
        backwards = np.isfinite(utc[:-1]) & np.isfinite(utc[1:]) & (utc[1:] < utc[:-1])
        track_rows.append({
            "track_id": row.track_id, "source_file": row.source_file,
            "instrument_class_pred": "singlebeam", "selection_policy": policy,
            "points_in_margin": len(index), "segments": n_segments,
            "source_discontinuities": int((~continuous).sum()),
            "distance_breaks": int((continuous & (spacing > crossover.GAP_BREAK_DEG)).sum()),
            "zero_length_segments_dropped": int((link & ~nonzero).sum()),
            "segments_with_known_utc_endpoints": int((good & np.isfinite(utc[:-1]) & np.isfinite(utc[1:])).sum()),
            "segments_with_decreasing_utc": int((good & backwards).sum()),
        })
        rt.n_points_in_margin += len(index)
        rt.n_gap_breaks += int((~link).sum())
        rt.n_zero_len_dropped += int((link & ~nonzero).sum())
        if not n_segments:
            continue
        for name, array in (
            ("x1", lon[:-1]), ("y1", lat[:-1]), ("x2", lon[1:]), ("y2", lat[1:]),
            ("d1", depth[:-1]), ("d2", depth[1:]), ("t1", utc[:-1]), ("t2", utc[1:]),
            (ENDPOINT_FIELDS[0], index[:-1]), (ENDPOINT_FIELDS[1], index[1:]),
            (ENDPOINT_FIELDS[2], line[:-1]), (ENDPOINT_FIELDS[3], line[1:]),
            ("segment_time_decreases", backwards),
        ):
            getattr(rt, name).append(array[good])
        rt.seg_track.append(np.full(n_segments, len(rt.track_ids), dtype=np.int64))
        rt.track_ids.append(row.track_id)
        rt.track_source.append("mgd77t")
        rt.n_tracks_used += 1
    if len(rt.flat(ENDPOINT_FIELDS[0])):
        if not np.all(rt.flat(ENDPOINT_FIELDS[1]) - rt.flat(ENDPOINT_FIELDS[0]) == 1):
            raise AssertionError("a crossover segment spans omitted original observations")
    return rt, track_rows


def attach_source_identity(
    events: pd.DataFrame, rt: crossover.RegionTracks, source_files: dict[str, str],
) -> pd.DataFrame:
    for side in ("first", "second"):
        ids = events[f"segment_id_{side}"].to_numpy(dtype=np.int64)
        events[f"source_file_{side}"] = events[f"track_id_{side}"].map(source_files)
        for field in ENDPOINT_FIELDS:
            events[f"{field}_{side}"] = rt.flat(field)[ids].astype(np.int64)
        events[f"segment_time_decreases_{side}"] = rt.flat("segment_time_decreases")[ids].astype(bool)
        events[f"time_{side}"] = pd.to_datetime(events[f"time_{side}"], utc=True)
    return events


def run_source_crossovers(args) -> int:
    started = time.monotonic()
    root, output = args.source_points_root.resolve(), args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler())
    rows = []
    for path in sorted((root / "comparison").glob("*.json")):
        report = json.loads(path.read_text())
        if report["instrument_class_pred"] != "singlebeam":
            continue
        previous = report["previous_manifest"]
        rows.append({
            "track_id": report["track_id"], "source_file": report["source_file"],
            **{key: previous[key] for key in (
                "bbox_lon_min", "bbox_lon_max", "bbox_lat_min", "bbox_lat_max",
            )},
        })
    manifest = pd.DataFrame(rows)
    source_files = dict(zip(manifest.track_id, manifest.source_file))
    summaries, track_coverage = [], []
    for policy in args.selection_policies:
        target = output / policy
        target.mkdir(parents=True, exist_ok=True)
        for tile, bbox in crossover.REGIONS.items():
            event_path = target / f"crossovers_{tile}.parquet"
            if event_path.exists() and not args.overwrite:
                raise FileExistsError(event_path)
            selected = crossover.select_region_tracks(manifest, bbox)
            rt, coverage = load_source_region(root, selected, bbox, policy)
            track_coverage.extend({"region": tile, **row} for row in coverage)
            n_segments = len(rt.flat("x1"))
            n_candidates = n_parallel = 0
            events = pd.DataFrame(columns=crossover.EVENT_COLUMNS)
            for side in ("first", "second"):
                events[f"segment_id_{side}"] = pd.Series(dtype="int64")
            counts = {"raw": 0, "inside": 0, "nan_depth": 0, "finite": 0, "dup": 0, "final": 0}
            if n_segments and rt.n_tracks_used > 1:
                seg_track = rt.flat("seg_track")
                ci, cj = crossover.grid_candidate_pairs(
                    rt.flat("x1"), rt.flat("y1"), rt.flat("x2"), rt.flat("y2"),
                    seg_track, len(rt.track_ids), logger,
                )
                n_candidates = len(ci)
                result, n_parallel = crossover.exact_intersections(rt, ci, cj, logger)
                events, counts = crossover.orient_and_filter(
                    result, rt, bbox, logger, include_segment_identity=True,
                )
                for side in ("first", "second"):
                    if f"segment_id_{side}" not in events:
                        events[f"segment_id_{side}"] = pd.Series(dtype="int64")
            events = attach_source_identity(events, rt, source_files)
            pairs, tracks = crossover.pair_and_track_stats(events, rt)
            events.to_parquet(event_path, index=False)
            pairs.to_parquet(target / f"pair_stats_{tile}.parquet", index=False)
            tracks.to_parquet(target / f"track_stats_{tile}.parquet", index=False)
            summaries.append({
                "region": tile, "selection_policy": policy,
                "bbox_candidates": len(selected), "tracks_with_segments": rt.n_tracks_used,
                "points_in_margin": rt.n_points_in_margin, "segments": n_segments,
                "source_discontinuities": sum(row["source_discontinuities"] for row in coverage),
                "distance_breaks": sum(row["distance_breaks"] for row in coverage),
                "zero_length_segments_dropped": rt.n_zero_len_dropped,
                "candidate_segment_pairs": n_candidates, "parallel_pairs": n_parallel,
                **{f"events_{key}": value for key, value in counts.items()},
                "track_pairs": int(events["pair_key"].nunique()),
                "events_with_known_utc_order": int((events["ordering_basis"] == "time").sum()),
                "median_signed_difference_m": events["diff_m"].median(),
                "median_absolute_difference_m": events["diff_m"].abs().median(),
            })
            print(f"{policy} {tile}: {len(selected)} bbox candidates, {n_segments} segments, {len(events)} crossovers", flush=True)
    pd.DataFrame(summaries).to_csv(output / "region_summary.csv", index=False)
    pd.DataFrame(summaries).to_parquet(output / "region_summary.parquet", index=False)
    pd.DataFrame(track_coverage).to_csv(output / "track_region_coverage.csv", index=False)
    description = {
        "points_root": str(root), "singlebeam_tracks": len(manifest),
        "selection_policies": args.selection_policies, "regions": crossover.REGIONS,
        "source_index_continuity": "endpoint observation indices differ by exactly one",
        "gap_break_deg": crossover.GAP_BREAK_DEG, "margin_deg": crossover.MARGIN_DEG,
        "grid_cell_deg": crossover.GRID_CELL_DEG, "dedup_eps_deg": crossover.DEDUP_EPS_DEG,
        "time_ordering": "specified valid UTC at both endpoints on both tracks; otherwise deterministic track ID order",
        "physical_processing": "source depths unchanged; no crossover correction or automatic track deletion",
        "wall_seconds": time.monotonic() - started,
    }
    (output / "method.json").write_text(json.dumps(description, indent=2) + "\n")
    return 0
