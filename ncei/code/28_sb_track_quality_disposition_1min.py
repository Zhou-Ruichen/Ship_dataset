#!/usr/bin/env python3
"""Per-track SB quality disposition and rejection-arm control tables (task
09-03-sb-track-quality-rejection).

Run from the repository root. Existing derived products are read-only; the
new outputs are the per-region track quality tables, the
``controls_mb_sb_reject_<tile>`` rejection-arm control tables, and the
step10 SB track quality report.

Predeclared disposition rule (PRD "Predeclared disposition rule"), applied
per region in this order:

1. ``reject`` (hard QC) if the track has backward nc time steps (full-track
   QC from the step09 crossover audit) or zero valid depth cells (zero rows
   in ``file_cells_1min`` inside the region tile).
2. ``flag_large_unapplied_bias`` (elt18 pattern) if step23 refused the bias
   (``not_significant``) but the crossover evidence shows a consistent large
   offset: |candidate| >= 200 m, n_crossovers >= 10, the track's crossover
   median signed difference has the same sign and |.| >= 200 m. These tracks
   are neither corrected nor rejected here; they wait for the second-round
   decision.
3. ``reject`` (misfit) if n_crossovers >= 10 AND the post-correction
   per-track median |crossover diff| > 3 x the regional crossover NMAD
   (NMAD of the region's raw crossover ``diff_m`` values over all events).
   PRD clause (c) (pre-correction scatter the correction does not reduce
   below the same threshold) collapses into this test: any track whose
   correction fails to bring it below the threshold has post > threshold;
   the n >= 10 evidence floor applies to both clauses because "absence of
   evidence is not rejection".
4. ``revert_to_raw`` if step23 applied a correction but the post-correction
   misfit is worse than the raw misfit (odp130jr pattern).
5. ``correct`` if step23 applied and the misfit improves or stays low.
6. ``keep_raw`` otherwise.

Post-correction residuals use step23 corrections as applied: for a track t
crossing partner p, residual_post = residual_raw - bias_t + bias_p, where
bias is step23 ``estimated_bias_m`` (0 when not applied or the partner has
no step23 row in the region). Crossover residuals follow the step09 sign
convention: residual_t = depth_t - depth_p at each crossing.

The rejection-arm control tables take the adjusted arm as the base (PRD
acceptance: "SB rows = adjusted-table rows minus rejected tracks' rows,
with reverted tracks at raw values"): disposition ``correct`` tracks keep
their step23-adjusted depths, ``revert_to_raw`` / ``keep_raw`` /
``flag_large_unapplied_bias`` tracks use raw depths, rejected tracks are
dropped entirely, and the SB control cell is the median of the remaining
per-track cell medians (step08 file-balanced rule). MB rows are copied
unchanged from the adjusted tables.

Reuse by import: script 23 supplies the frozen inner_training SB cell
selection and control-table helpers; script 24 supplies the region bboxes
and margin. Script 27's network solver is not an input to this task.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds

REPO_ROOT = Path(__file__).resolve().parents[2]
NCEI_ROOT = REPO_ROOT / "ncei"
MANIFEST_PATH = NCEI_ROOT / "manifests/trackline_source_manifest.parquet"
POINTS_DIR = NCEI_ROOT / "derived/singlebeam/points_raw"
SB_CELL_ROOT = NCEI_ROOT / "derived/singlebeam/file_cells_1min"
STEP23_ROOT = NCEI_ROOT / "derived/sb_track_bias_1min"
CROSSOVER_ROOT = NCEI_ROOT / "derived/true_crossover_audit"
OUTPUT_ROOT = NCEI_ROOT / "derived/sb_track_quality_1min"
REPORT_PATH = NCEI_ROOT / "docs/step10_sb_track_quality_report.md"

TILES = (
    "lon068_lat018",
    "lon052_lat018",
    "lon058_lat012",
    "lon059_lat015",
    "lon004_lat033",
    "lon021_lat010",
)

# Predeclared rule parameters (recorded verbatim in the report).
NMIN_CROSSOVERS = 10
MISFIT_FACTOR = 3.0
LARGE_UNAPPLIED_BIAS_M = 200.0

CONTROL_COLUMNS = ["cell_id", "lon_center", "lat_center", "control_depth_m", "control_source"]
REJECT_ARM_SB_SOURCE = "singlebeam_dispositioned"
DISPOSITIONS = (
    "reject",
    "flag_large_unapplied_bias",
    "revert_to_raw",
    "correct",
    "keep_raw",
)
QUALITY_COLUMNS = [
    "region",
    "track_id",
    "in_step23",
    "n_cells_in_tile",
    "n_in_tile_points",
    "n_training_cells",
    "n_colocated_cells",
    "step23_candidate_bias_m",
    "step23_residual_nmad_m",
    "step23_bias_m",
    "step23_applied",
    "step23_gate_reason",
    "n_crossovers",
    "crossover_raw_median_abs_diff_m",
    "crossover_post_median_abs_diff_m",
    "crossover_median_signed_diff_m",
    "crossover_track_nmad_m",
    "region_crossover_nmad_m",
    "misfit_threshold_m",
    "n_backward_time_steps",
    "hard_qc_backward_time",
    "hard_qc_zero_cells",
    "disposition",
    "reason",
]


def load_script(module_name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(
        module_name, NCEI_ROOT / "code" / file_name
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load ncei/code/{file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace this script's existing outputs. Without it, a complete prior run is left unchanged.",
    )
    return parser.parse_args()


def atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def atomic_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def output_paths() -> list[Path]:
    paths = [REPORT_PATH]
    for tile in TILES:
        paths.append(OUTPUT_ROOT / f"track_quality_{tile}.parquet")
        paths.append(STEP23_ROOT / f"controls_mb_sb_reject_{tile}.parquet")
    return paths


def nmad(values: np.ndarray) -> float:
    median = np.median(values)
    return float(1.4826 * np.median(np.abs(values - median)))


def audit_track_universe(script24, manifest: pd.DataFrame) -> pd.DataFrame:
    """Tracks loaded by the step09 crossover audit, per region, with point counts.

    Mirrors script 24's load rule: manifest bbox prefilter, then a track side
    counts as loaded when it has >= 2 points inside the tile bbox + margin.
    Point counts aggregate per (region, track_id) with the maximum over the
    nc/xyz sides (twin files hold the same points).
    """
    records: dict[tuple[str, str], dict[str, int]] = {}
    for tile in TILES:
        lon0, lon1, lat0, lat1 = script24.REGIONS[tile]
        margin = script24.MARGIN_DEG
        selected = manifest[
            (manifest["bbox_lon_max"] >= lon0 - margin)
            & (manifest["bbox_lon_min"] <= lon1 + margin)
            & (manifest["bbox_lat_max"] >= lat0 - margin)
            & (manifest["bbox_lat_min"] <= lat1 + margin)
        ]
        for row in selected.itertuples(index=False):
            side = "nc" if row.source_type == "ncei_nc" else "xyz"
            path = POINTS_DIR / f"{row.track_id}__{side}.parquet"
            if not path.exists():
                continue
            points = pd.read_parquet(path, columns=["lon", "lat"])
            in_margin = (
                (points["lon"] >= lon0 - margin)
                & (points["lon"] <= lon1 + margin)
                & (points["lat"] >= lat0 - margin)
                & (points["lat"] <= lat1 + margin)
            )
            n_margin = int(in_margin.sum())
            if n_margin < 2:
                continue
            in_tile = (
                (points["lon"] >= lon0)
                & (points["lon"] <= lon1)
                & (points["lat"] >= lat0)
                & (points["lat"] <= lat1)
            )
            key = (tile, str(row.track_id))
            record = records.setdefault(key, {"n_margin_points": 0, "n_in_tile_points": 0})
            record["n_margin_points"] = max(record["n_margin_points"], n_margin)
            record["n_in_tile_points"] = max(
                record["n_in_tile_points"], int(in_tile.sum())
            )
    frame = pd.DataFrame.from_dict(
        {
            f"{region}\0{track}": {
                "region": region,
                "track_id": track,
                "n_margin_points": values["n_margin_points"],
                "n_in_tile_points": values["n_in_tile_points"],
            }
            for (region, track), values in records.items()
        },
        orient="index",
    )
    return frame.reset_index(drop=True)


def tile_cell_track_counts(script24, tile: str) -> dict[str, int]:
    """Per-track count of file_cells_1min rows inside the region tile."""
    lon0, lon1, lat0, lat1 = script24.REGIONS[tile]
    dataset = ds.dataset(SB_CELL_ROOT, format="parquet")
    predicate = (
        (pc.field("lon_center") >= lon0)
        & (pc.field("lon_center") < lon1)
        & (pc.field("lat_center") >= lat0)
        & (pc.field("lat_center") < lat1)
    )
    table = dataset.to_table(columns=["track_id"], filter=predicate)
    counts = table.to_pandas()["track_id"].astype(str).value_counts()
    return {track: int(count) for track, count in counts.items()}


def track_misfits(events: pd.DataFrame, bias_by_track: dict[str, float]) -> dict[str, dict[str, float]]:
    """Per-track raw and post-correction median |crossover residual|."""
    residuals: dict[str, tuple[list[float], list[float]]] = {}
    for event in events.itertuples(index=False):
        bias_first = bias_by_track.get(event.track_id_first, 0.0)
        bias_second = bias_by_track.get(event.track_id_second, 0.0)
        raw_first = -event.diff_m
        post_first = raw_first - bias_first + bias_second
        raw_second = event.diff_m
        post_second = raw_second - bias_second + bias_first
        for track, raw, post in (
            (event.track_id_first, raw_first, post_first),
            (event.track_id_second, raw_second, post_second),
        ):
            raws, posts = residuals.setdefault(track, ([], []))
            raws.append(raw)
            posts.append(post)
    return {
        track: {
            "n_crossovers": len(raws),
            "raw_median_abs_diff_m": float(np.median(np.abs(raws))),
            "post_median_abs_diff_m": float(np.median(np.abs(posts))),
        }
        for track, (raws, posts) in residuals.items()
    }


def elt18_pattern(
    step23_applied: bool,
    gate_reason: str,
    candidate: float,
    n_crossovers: int,
    signed_median: float,
) -> bool:
    if step23_applied or gate_reason != "not_significant":
        return False
    if not np.isfinite(candidate) or abs(candidate) < LARGE_UNAPPLIED_BIAS_M:
        return False
    if n_crossovers < NMIN_CROSSOVERS or not np.isfinite(signed_median):
        return False
    return candidate * signed_median > 0 and abs(signed_median) >= LARGE_UNAPPLIED_BIAS_M


def disposition_row(row: pd.Series, threshold: float) -> tuple[str, str]:
    if bool(row["hard_qc_backward_time"]):
        return "reject", "backward_time_steps"
    if bool(row["hard_qc_zero_cells"]):
        return "reject", "zero_valid_depth_cells"
    if elt18_pattern(
        bool(row["step23_applied"]),
        str(row["step23_gate_reason"]),
        float(row["step23_candidate_bias_m"]),
        int(row["n_crossovers"]),
        float(row["crossover_median_signed_diff_m"]),
    ):
        return "flag_large_unapplied_bias", "large_refused_bias_crossover_consistent"
    post = float(row["crossover_post_median_abs_diff_m"])
    raw = float(row["crossover_raw_median_abs_diff_m"])
    if int(row["n_crossovers"]) >= NMIN_CROSSOVERS and np.isfinite(post) and post > threshold:
        return "reject", "post_correction_misfit_above_3x_region_nmad"
    if bool(row["step23_applied"]) and np.isfinite(post) and np.isfinite(raw) and post > raw:
        return "revert_to_raw", "applied_but_post_worse_than_raw"
    if bool(row["step23_applied"]):
        return "correct", "applied_improves_or_stays_low"
    return "keep_raw", "no_application_or_insufficient_evidence"


def build_quality_region(
    tile: str,
    script24,
    step23_region: pd.DataFrame,
    universe_region: pd.DataFrame,
    cell_tracks: dict[str, int],
    backward_map: dict[str, int],
    bias_by_track: dict[str, float],
) -> tuple[pd.DataFrame, float, int]:
    events = pd.read_parquet(
        CROSSOVER_ROOT / f"crossovers_{tile}.parquet",
        columns=["track_id_first", "track_id_second", "diff_m"],
    )
    region_nmad = nmad(events["diff_m"].to_numpy(dtype=float))
    threshold = MISFIT_FACTOR * region_nmad
    misfits = track_misfits(events, bias_by_track)
    track_stats = pd.read_parquet(
        CROSSOVER_ROOT / f"track_stats_{tile}.parquet"
    ).set_index("track_id")

    step23_indexed = step23_region.set_index("track_id")
    track_ids = sorted(set(universe_region["track_id"]) | set(step23_indexed.index))
    rows: list[dict[str, object]] = []
    for track_id in track_ids:
        in_step23 = track_id in step23_indexed.index
        step23_row = step23_indexed.loc[track_id] if in_step23 else None
        misfit = misfits.get(track_id)
        stat = track_stats.loc[track_id] if track_id in track_stats.index else None
        n_cells_in_tile = int(cell_tracks.get(track_id, 0))
        universe_row = universe_region.loc[universe_region["track_id"].eq(track_id)]
        n_in_tile_points = (
            int(universe_row["n_in_tile_points"].max()) if len(universe_row) else 0
        )
        n_backward = backward_map.get(track_id, 0)
        rows.append(
            {
                "region": tile,
                "track_id": track_id,
                "in_step23": in_step23,
                "n_cells_in_tile": n_cells_in_tile,
                "n_in_tile_points": n_in_tile_points,
                "n_training_cells": int(step23_row.n_region_cells) if in_step23 else 0,
                "n_colocated_cells": int(step23_row.n_colocated_cells) if in_step23 else 0,
                "step23_candidate_bias_m": float(step23_row.weighted_median_residual_m)
                if in_step23
                else float("nan"),
                "step23_residual_nmad_m": float(step23_row.residual_nmad_m)
                if in_step23
                else float("nan"),
                "step23_bias_m": float(step23_row.estimated_bias_m) if in_step23 else 0.0,
                "step23_applied": bool(step23_row.bias_applied) if in_step23 else False,
                "step23_gate_reason": str(step23_row.decision_reason) if in_step23 else "no_step23_row",
                "n_crossovers": int(misfit["n_crossovers"]) if misfit else 0,
                "crossover_raw_median_abs_diff_m": misfit["raw_median_abs_diff_m"]
                if misfit
                else float("nan"),
                "crossover_post_median_abs_diff_m": misfit["post_median_abs_diff_m"]
                if misfit
                else float("nan"),
                "crossover_median_signed_diff_m": float(stat.median_signed_diff_m)
                if stat is not None
                else float("nan"),
                "crossover_track_nmad_m": float(stat.nmad_signed_diff_m)
                if stat is not None
                else float("nan"),
                "region_crossover_nmad_m": region_nmad,
                "misfit_threshold_m": threshold,
                "n_backward_time_steps": n_backward,
                "hard_qc_backward_time": n_backward > 0,
                "hard_qc_zero_cells": n_cells_in_tile == 0,
            }
        )
    quality = pd.DataFrame(rows, columns=QUALITY_COLUMNS[:-2])
    dispositions = []
    reasons = []
    for _, row in quality.iterrows():
        disposition, reason = disposition_row(row, threshold)
        dispositions.append(disposition)
        reasons.append(reason)
    quality["disposition"] = dispositions
    quality["reason"] = reasons
    if misfits:
        tallies = pd.Series({track: values["n_crossovers"] for track, values in misfits.items()})
        audit_tallies = track_stats["n_crossovers"]
        joined = pd.concat([tallies.rename("mine"), audit_tallies.rename("audit")], axis=1).dropna()
        if not (joined["mine"] == joined["audit"]).all():
            raise AssertionError(f"crossover tallies disagree with audit track_stats in {tile}")
    return quality[QUALITY_COLUMNS], region_nmad, len(events)


def reject_arm_controls(
    script23,
    tile: str,
    sb_region: pd.DataFrame,
    quality: pd.DataFrame,
    adjusted_table: pd.DataFrame,
    mb_only_table: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int]]:
    mb_rows = adjusted_table.loc[adjusted_table["control_source"].eq("strict_multibeam")].copy()
    if len(mb_rows) != len(mb_only_table):
        raise AssertionError(f"adjusted MB row count differs from mb_only table in {tile}")
    mb_rows = mb_rows.sort_values("cell_id").reset_index(drop=True)
    expected_mb = mb_only_table.sort_values("cell_id").reset_index(drop=True)
    if not mb_rows[CONTROL_COLUMNS].equals(expected_mb[CONTROL_COLUMNS]):
        raise AssertionError(f"adjusted MB rows differ from mb_only table in {tile}")
    adjusted_sb = adjusted_table.loc[adjusted_table["control_source"].ne("strict_multibeam")]

    disposition_by_track = dict(zip(quality["track_id"], quality["disposition"]))
    bias_by_track = dict(zip(quality["track_id"], quality["step23_bias_m"]))
    work = sb_region.copy()
    work["disposition"] = work["track_id"].map(disposition_by_track)
    if work["disposition"].isna().any():
        missing = sorted(work.loc[work["disposition"].isna(), "track_id"].unique())
        raise AssertionError(f"SB cell tracks without a quality row in {tile}: {missing}")
    work = work.loc[work["disposition"].ne("reject")]
    depth = work["median_depth_m"].to_numpy(dtype=float) - np.where(
        work["disposition"].eq("correct"),
        work["track_id"].map(bias_by_track).to_numpy(dtype=float),
        0.0,
    )
    work["depth_for_control_m"] = depth
    sb_controls = (
        work.groupby("cell_id", as_index=False)
        .agg(
            lon_center=("lon_center", "first"),
            lat_center=("lat_center", "first"),
            control_depth_m=("depth_for_control_m", "median"),
        )
    )
    sb_controls["control_source"] = REJECT_ARM_SB_SOURCE

    # Adjusted-arm rebuild check (all step23 tracks at step23 depths).
    check = sb_region.copy()
    check["depth_for_control_m"] = check["median_depth_m"] - check["track_id"].map(
        bias_by_track
    ).to_numpy(dtype=float)
    check_controls = (
        check.groupby("cell_id", as_index=False)
        .agg(control_depth_m=("depth_for_control_m", "median"))
        .sort_values("cell_id")
        .reset_index(drop=True)
    )
    stored = adjusted_sb[["cell_id", "control_depth_m"]].sort_values("cell_id").reset_index(drop=True)
    if list(check_controls["cell_id"]) != list(stored["cell_id"]):
        raise AssertionError(f"adjusted-arm rebuild cell set differs in {tile}")
    if not np.allclose(
        check_controls["control_depth_m"].to_numpy(dtype=float),
        stored["control_depth_m"].to_numpy(dtype=float),
        rtol=0.0,
        atol=1e-9,
    ):
        raise AssertionError(f"adjusted-arm rebuild depths differ in {tile}")

    controls = script23.combine_controls(mb_rows, sb_controls[CONTROL_COLUMNS])
    lost = set(stored["cell_id"]) - set(sb_controls["cell_id"])
    unexpected = set(sb_controls["cell_id"]) - set(stored["cell_id"])
    if unexpected:
        raise AssertionError(f"reject arm gained SB cells absent from adjusted arm in {tile}")
    mb_cells = set(mb_rows["cell_id"])
    stats = {
        "mb_rows": len(mb_rows),
        "sb_cells_adjusted": len(stored),
        "sb_cells_reject": len(sb_controls),
        "sb_cells_lost": len(lost),
        "sb_cells_lost_with_mb": len(lost & mb_cells),
        "sb_cells_lost_sb_only": len(lost - mb_cells),
        "mb_sb_rows_adjusted": len(adjusted_table),
        "mb_sb_rows_reject": len(controls),
        "n_rejected_tracks_with_cells": int(
            quality.loc[quality["disposition"].eq("reject") & quality["in_step23"], "track_id"].nunique()
        ),
        "n_track_cell_rows_dropped": int(
            sb_region["track_id"].map(disposition_by_track).eq("reject").sum()
        ),
    }
    return controls[CONTROL_COLUMNS], stats


def fmt(value: float, digits: int = 2) -> str:
    if value is None or not np.isfinite(value):
        return "NA"
    return f"{value:.{digits}f}"


def build_report(
    quality: pd.DataFrame,
    control_stats: dict[str, dict[str, int]],
    region_nmad: dict[str, float],
    region_events: dict[str, int],
) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = []
    add = lines.append
    add("# Step 10 SB per-track quality disposition and rejection-arm controls")
    add("")
    add(f"Generated: {ts}  ")
    add("Script: `ncei/code/28_sb_track_quality_disposition_1min.py` (run from repo root)  ")
    add("Interpreter: `%s`  " % sys.executable)
    add("Task: `.trellis/tasks/09-03-sb-track-quality-rejection/prd.md`")
    add("")
    add("## Predeclared rule, as applied")
    add("")
    add("Per region, step23 corrections are applied first and post-correction")
    add("crossover consistency is judged with the step09 crossover events")
    add("(`diff_m = depth_second - depth_first`; a track's residual at a")
    add("crossing is its own depth minus the partner's). Post-correction")
    add("residual of track t against partner p is `residual_t - bias_t +")
    add("bias_p`, bias = step23 `estimated_bias_m` (0 when not applied or the")
    add("partner has no step23 row in the region). Dispositions, in")
    add("precedence order:")
    add("")
    add("1. `reject` (hard QC): backward nc time steps (full-track monotonicity")
    add("   QC from `nc_time_qc.parquet`) or zero valid depth cells (zero rows")
    add("   in `file_cells_1min` inside the region tile).")
    add("2. `flag_large_unapplied_bias` (elt18 pattern): step23 gate refused")
    add("   (`not_significant`) but the crossovers agree — |candidate bias| >=")
    add(f"   {LARGE_UNAPPLIED_BIAS_M:.0f} m, n_crossovers >= {NMIN_CROSSOVERS}, crossover")
    add(f"   median signed diff same sign and |.| >= {LARGE_UNAPPLIED_BIAS_M:.0f} m. Not")
    add("   corrected, not rejected; reserved for the second-round decision.")
    add(f"3. `reject` (misfit): n_crossovers >= {NMIN_CROSSOVERS} AND post-correction")
    add(f"   median |crossover diff| > {MISFIT_FACTOR:.0f} x regional crossover NMAD.")
    add("   Regional crossover NMAD = 1.4826 x MAD of the region's raw crossover")
    add("   `diff_m` values over all events. PRD clause (c) collapses into this")
    add("   test: a correction that fails to bring the track below the")
    add("   threshold leaves post > threshold; the n >= 10 evidence floor")
    add("   applies to both clauses because absence of evidence is not")
    add("   rejection.")
    add("4. `revert_to_raw`: step23 applied and post-correction misfit is worse")
    add("   than the raw misfit.")
    add("5. `correct`: step23 applied and the misfit improves or stays low.")
    add("6. `keep_raw`: everything else, including all tracks with too few")
    add("   crossovers to judge.")
    add("")
    add("Rejection-arm control tables (`controls_mb_sb_reject_<tile>.parquet`):")
    add("MB rows copied unchanged from the adjusted tables (asserted identical")
    add("to the mb_only tables); SB cells rebuilt from per-track training-block")
    add("cells with dispositions applied — `correct` tracks at step23-adjusted")
    add("depths, `revert_to_raw` / `keep_raw` / `flag_large_unapplied_bias`")
    add("tracks at raw depths, rejected tracks dropped entirely; the cell value")
    add("is the median of the remaining per-track cell medians (step08")
    add("file-balanced rule). The rebuild reproduces the stored adjusted-arm SB")
    add(f"cells exactly (asserted), and SB rows carry `{REJECT_ARM_SB_SOURCE}`.")
    add("")
    add("## Regional crossover NMAD and thresholds")
    add("")
    add("| region | events | crossover NMAD (m) | 3x threshold (m) |")
    add("| --- | ---: | ---: | ---: |")
    for tile in TILES:
        add(
            f"| {tile} | {region_events[tile]} | {fmt(region_nmad[tile])} | "
            f"{fmt(MISFIT_FACTOR * region_nmad[tile])} |"
        )
    add("")
    add("## Disposition counts per region")
    add("")
    header = "| region | tracks | " + " | ".join(DISPOSITIONS) + " |"
    add(header)
    add("| --- | ---: | " + " | ".join(["---:"] * len(DISPOSITIONS)) + " |")
    for tile in TILES:
        part = quality.loc[quality["region"].eq(tile)]
        cells = " | ".join(
            str(int(part["disposition"].eq(d).sum())) for d in DISPOSITIONS
        )
        add(f"| {tile} | {len(part)} | {cells} |")
    total = " | ".join(str(int(quality["disposition"].eq(d).sum())) for d in DISPOSITIONS)
    add(f"| all six | {len(quality)} | {total} |")
    add("")
    add("## Rejected tracks")
    add("")
    add("Hard QC (`reason = backward_time_steps`; full-track nc time QC):")
    add("")
    hard_time = quality.loc[quality["reason"].eq("backward_time_steps")]
    add(
        "| region | track | in step23 | n crossovers | raw median \\|diff\\| (m) | post median \\|diff\\| (m) | backward steps |"
    )
    add("| --- | --- | --- | ---: | ---: | ---: | ---: |")
    for row in hard_time.itertuples(index=False):
        add(
            f"| {row.region} | {row.track_id} | {row.in_step23} | {row.n_crossovers} | "
            f"{fmt(row.crossover_raw_median_abs_diff_m)} | {fmt(row.crossover_post_median_abs_diff_m)} | "
            f"{row.n_backward_time_steps} |"
        )
    add("")
    add("Hard QC (`reason = zero_valid_depth_cells`; zero `file_cells_1min` rows")
    add("inside the tile; `n_in_tile_points = 0` marks tracks whose points only")
    add("graze the audit margin):")
    add("")
    hard_cells = quality.loc[quality["reason"].eq("zero_valid_depth_cells")]
    add("| region | track | in step23 | n in-tile points | n crossovers |")
    add("| --- | --- | --- | ---: | ---: |")
    for row in hard_cells.itertuples(index=False):
        add(
            f"| {row.region} | {row.track_id} | {row.in_step23} | {row.n_in_tile_points} | "
            f"{row.n_crossovers} |"
        )
    add("")
    add("Misfit (`reason = post_correction_misfit_above_3x_region_nmad`):")
    add("")
    misfit = quality.loc[quality["reason"].eq("post_correction_misfit_above_3x_region_nmad")]
    add(
        "| region | track | n crossovers | raw median \\|diff\\| (m) | post median \\|diff\\| (m) | threshold (m) | step23 bias (m) | applied |"
    )
    add("| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |")
    for row in misfit.itertuples(index=False):
        add(
            f"| {row.region} | {row.track_id} | {row.n_crossovers} | "
            f"{fmt(row.crossover_raw_median_abs_diff_m)} | {fmt(row.crossover_post_median_abs_diff_m)} | "
            f"{fmt(row.misfit_threshold_m)} | {fmt(row.step23_bias_m)} | {row.step23_applied} |"
        )
    add("")
    add("## Cells lost to rejection")
    add("")
    add("| region | SB cells (adjusted) | SB cells (reject arm) | SB cells lost | lost, MB-covered | lost, SB-only | track-cell rows dropped | MB rows | rows (adjusted) | rows (reject arm) |")
    add("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for tile in TILES:
        s = control_stats[tile]
        add(
            f"| {tile} | {s['sb_cells_adjusted']} | {s['sb_cells_reject']} | {s['sb_cells_lost']} | "
            f"{s['sb_cells_lost_with_mb']} | {s['sb_cells_lost_sb_only']} | {s['n_track_cell_rows_dropped']} | "
            f"{s['mb_rows']} | {s['mb_sb_rows_adjusted']} | {s['mb_sb_rows_reject']} |"
        )
    add("")
    totals = {
        key: sum(control_stats[tile][key] for tile in TILES)
        for key in (
            "sb_cells_adjusted",
            "sb_cells_reject",
            "sb_cells_lost",
            "sb_cells_lost_with_mb",
            "sb_cells_lost_sb_only",
            "n_track_cell_rows_dropped",
            "mb_rows",
            "mb_sb_rows_adjusted",
            "mb_sb_rows_reject",
        )
    }
    add(
        f"| all six | {totals['sb_cells_adjusted']} | {totals['sb_cells_reject']} | {totals['sb_cells_lost']} | "
        f"{totals['sb_cells_lost_with_mb']} | {totals['sb_cells_lost_sb_only']} | {totals['n_track_cell_rows_dropped']} | "
        f"{totals['mb_rows']} | {totals['mb_sb_rows_adjusted']} | {totals['mb_sb_rows_reject']} |"
    )
    add("")
    add("MB rows are identical to the adjusted tables in every region (asserted")
    add("against the mb_only tables). Rejected tracks with zero training cells")
    add("contribute no control rows, so their rejection is recorded in the")
    add("quality tables only.")
    add("")
    add("## Named tracks")
    add("")
    named = quality.loc[
        (quality["region"].eq("lon068_lat018") & quality["track_id"].eq("odp130jr"))
        | (quality["region"].eq("lon021_lat010") & quality["track_id"].eq("elt18"))
        | (quality["region"].eq("lon021_lat010") & quality["track_id"].eq("elt19"))
    ]
    add(
        "| region | track | disposition | reason | n crossovers | raw median \\|diff\\| (m) | post median \\|diff\\| (m) | threshold (m) | step23 candidate (m) | applied | crossover median signed (m) |"
    )
    add("| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |")
    for row in named.itertuples(index=False):
        add(
            f"| {row.region} | {row.track_id} | {row.disposition} | {row.reason} | {row.n_crossovers} | "
            f"{fmt(row.crossover_raw_median_abs_diff_m)} | {fmt(row.crossover_post_median_abs_diff_m)} | "
            f"{fmt(row.misfit_threshold_m)} | {fmt(row.step23_candidate_bias_m)} | {row.step23_applied} | "
            f"{fmt(row.crossover_median_signed_diff_m)} |"
        )
    add("")
    add("odp130jr: step23 applied -44.00 m; its 141 crossovers sit near zero raw")
    add("(median |diff| ~3.9 m) and the correction pushes the median to ~44 m.")
    add("Post-correction misfit is worse than raw, so the track reverts to raw.")
    add("")
    add("elt18: step23 refused the -1247 m candidate (`not_significant`); its 75")
    add("crossovers show a consistent -965 m median offset, above the 284 m")
    add("regional threshold. It is flagged for the second-round decision, not")
    add("corrected and not rejected.")
    add("")
    add("elt19 matches the same operationalized pattern (refused -307 m")
    add("candidate, crossover median -276 m over 40 events) and is flagged")
    add("with it. The sign-flipping/high-variance refused tracks the step09")
    add("consistency check distinguished (e.g. elt06, nbp0203 in lon021_lat010)")
    add("fail the sign/magnitude consistency clause and are not flagged;")
    add("nbp0203 is rejected by the misfit rule instead.")
    add("")
    add("## Deviations from the PRD tallies")
    add("")
    backward_tracks = sorted(
        quality.loc[quality["hard_qc_backward_time"], "track_id"].unique()
    )
    zero_cell_tracks = sorted(
        quality.loc[quality["hard_qc_zero_cells"], "track_id"].unique()
    )
    add(
        f"- The PRD expected `3 backward-time` and `7 zero-cell` rejected"
        f" tracks. The literal hard-QC criteria over this universe reject"
        f" {len(backward_tracks)} backward-time tracks ({', '.join(backward_tracks)})"
        f" and {len(zero_cell_tracks)} zero-cell tracks"
        f" ({', '.join(zero_cell_tracks)}); rc2707 trips both. The step09"
        f" report's per-region monotonicity counts (1 in lon068, 3 in lon058,"
        f" 1 in lon059) already sum to 5 region-tracks, so the PRD's 3 cannot"
        f" be recovered by any intersection with the six-region track sets"
        f" checked here; the predeclared rule (any backward time step)"
        f" rejects all of them."
    )
    add(
        "- No reading of `zero valid depth cells` yields exactly 7"
        " Eltanin/Conrad tracks: zero `file_cells_1min` rows inside the tile"
        " gives 6 tracks (2 Eltanin/Conrad); zero step23 colocated cells"
        " gives 8 Eltanin/Conrad region-rows (7 unique tracks), but those"
        " tracks have 13-577 region cells each and are not `zero-cell` in any"
        " literal sense. The literal cell-product criterion was applied."
    )
    add("")
    add("## Output files")
    add("")
    add("```text")
    add("ncei/derived/sb_track_quality_1min/")
    add("  track_quality_<region>.parquet     one row per SB track per region")
    add("ncei/derived/sb_track_bias_1min/")
    add("  controls_mb_sb_reject_<region>.parquet")
    add("```")
    add("")
    add("The quality-table universe per region is the step23 track set united")
    add("with every track the step09 crossover audit loaded (>= 2 points inside")
    add("the tile bbox + 0.05 deg margin). Every disposition is traceable to")
    add("the row's evidence fields (step23 columns, crossover misfits, QC")
    add("flags, threshold).")
    add("")
    add("## Reproduction")
    add("")
    add("```bash")
    add("cd /mnt/data2/00-Data/ship")
    add(f"{sys.executable} ncei/code/28_sb_track_quality_disposition_1min.py --overwrite")
    add("```")
    add("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    expected = output_paths()
    existing = [path for path in expected if path.exists()]
    if existing and not args.overwrite:
        if len(existing) == len(expected):
            print("Complete Step 28 output set already exists; no files changed.")
            return
        raise SystemExit(
            "Partial Step 28 output set exists; inspect it and rerun with --overwrite "
            "to replace Step 28 outputs only."
        )

    script23 = load_script("sb_track_bias_23", "23_estimate_singlebeam_track_bias_1min.py")
    script24 = load_script("true_crossover_24", "24_true_crossover_audit.py")

    step23 = pd.read_parquet(STEP23_ROOT / "track_bias_summary.parquet")
    if step23[["region", "track_id"]].duplicated().any():
        raise ValueError("duplicate step23 region/track rows")
    time_qc = pd.read_parquet(CROSSOVER_ROOT / "nc_time_qc.parquet")
    backward_map = {
        str(track): int(steps)
        for track, steps in zip(time_qc["track_id"], time_qc["n_backward_steps"])
    }
    manifest = pd.read_parquet(
        MANIFEST_PATH,
        columns=[
            "track_id",
            "source_type",
            "bbox_lon_min",
            "bbox_lon_max",
            "bbox_lat_min",
            "bbox_lat_max",
        ],
    )

    universe = audit_track_universe(script24, manifest)
    tile_size, block_size, blocks_per_axis, training_blocks = script23.read_nested_role_config()
    sb_geometry = script23.sb_geometry_in_tiles(tile_size)
    sb_training_cells = {
        tile: script23.select_sb_training_cells(
            sb_geometry, tile, tile_size, block_size, blocks_per_axis, training_blocks
        )
        for tile in TILES
    }
    union_cells = set().union(*sb_training_cells.values())
    sb_all = script23.filtered_depth_read(
        SB_CELL_ROOT,
        ["track_id", "cell_id", "lon_center", "lat_center", "median_depth_m", "n_unique_triples"],
        union_cells,
    )

    quality_parts: list[pd.DataFrame] = []
    control_stats: dict[str, dict[str, int]] = {}
    region_nmad: dict[str, float] = {}
    region_events: dict[str, int] = {}
    for tile in TILES:
        step23_region = step23.loc[step23["region"].eq(tile)].copy()
        step23_region["track_id"] = step23_region["track_id"].astype(str)
        universe_region = universe.loc[universe["region"].eq(tile)]
        loaded_ids = set(universe_region["track_id"])
        missing = set(step23_region["track_id"]) - loaded_ids
        if missing:
            raise AssertionError(f"step23 tracks not loaded by the audit in {tile}: {sorted(missing)}")
        cell_tracks = tile_cell_track_counts(script24, tile)
        bias_by_track = dict(
            zip(step23_region["track_id"], step23_region["estimated_bias_m"].astype(float))
        )
        quality, nmad_value, n_events = build_quality_region(
            tile,
            script24,
            step23_region,
            universe_region,
            cell_tracks,
            backward_map,
            bias_by_track,
        )
        quality_parts.append(quality)
        region_nmad[tile] = nmad_value
        region_events[tile] = n_events

        allowed = sb_training_cells[tile]
        sb_region = sb_all.loc[sb_all["cell_id"].isin(allowed)].copy()
        sb_region["track_id"] = sb_region["track_id"].astype(str)
        adjusted_table = pd.read_parquet(
            STEP23_ROOT / f"controls_mb_sb_adjusted_{tile}.parquet"
        )
        mb_only_table = pd.read_parquet(STEP23_ROOT / f"controls_mb_only_{tile}.parquet")
        controls, stats = reject_arm_controls(
            script23, tile, sb_region, quality, adjusted_table, mb_only_table
        )
        control_stats[tile] = stats
        atomic_parquet(controls, STEP23_ROOT / f"controls_mb_sb_reject_{tile}.parquet")
        atomic_parquet(quality, OUTPUT_ROOT / f"track_quality_{tile}.parquet")
        print(
            f"{tile}: {len(quality)} tracks, rejects "
            f"{int(quality['disposition'].eq('reject').sum())}, "
            f"SB cells {stats['sb_cells_adjusted']} -> {stats['sb_cells_reject']} "
            f"({stats['sb_cells_lost_sb_only']} SB-only lost)"
        )

    quality_all = pd.concat(quality_parts, ignore_index=True)[QUALITY_COLUMNS]
    if quality_all[["region", "track_id"]].duplicated().any():
        raise ValueError("duplicate quality rows")
    report = build_report(quality_all, control_stats, region_nmad, region_events)
    atomic_text(report, REPORT_PATH)
    print(
        f"Wrote {len(expected)} Step 28 files: {len(quality_all)} quality rows, "
        f"{int(quality_all['disposition'].eq('reject').sum())} rejected tracks."
    )


if __name__ == "__main__":
    main()
