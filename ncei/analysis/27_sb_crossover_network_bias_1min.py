#!/usr/bin/env python3
"""Solve six regional SB crossover networks for constant track offsets.

Run from the repository root. Existing crossover events and Step 23 track
biases are read-only. The retained outputs contain the unweighted network
solve and a common-event leave-one-crossover-out comparison of raw, Step 23,
and network residuals. GEBCO is not read.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
NCEI_ROOT = REPO_ROOT / "ncei"
CROSSOVER_ROOT = NCEI_ROOT / "derived/true_crossover_audit"
STEP23_PATH = NCEI_ROOT / "derived/sb_track_bias_1min/track_bias_summary.parquet"
OUTPUT_ROOT = NCEI_ROOT / "derived/sb_network_bias_1min"
REPORT_PATH = NCEI_ROOT / "docs/step10_sb_network_bias_report.md"

REGIONS = (
    "lon068_lat018",
    "lon052_lat018",
    "lon058_lat012",
    "lon059_lat015",
    "lon004_lat033",
    "lon021_lat010",
)
EVENT_COLUMNS = [
    "pair_key",
    "track_id_first",
    "track_id_second",
    "crossing_lon",
    "crossing_lat",
    "diff_m",
]
STEP23_COLUMNS = [
    "region",
    "track_id",
    "estimated_bias_m",
    "bias_applied",
    "decision_reason",
]
TRACK_COLUMNS = [
    "region",
    "track_id",
    "component_id",
    "datum_type",
    "network_offset_m",
    "offset_standard_error_m",
    "n_crossovers",
    "n_distinct_neighbor_tracks",
    "is_step23_anchor",
    "step23_offset_m",
    "solve_variant",
]
COMPONENT_COLUMNS = [
    "region",
    "component_id",
    "datum_type",
    "n_tracks",
    "n_crossovers",
    "crossovers_per_track_average",
    "n_step23_anchors",
    "n_single_crossover_tracks",
    "n_evaluation_candidate_events",
    "n_evaluated_events",
    "n_unidentifiable_leave_one_out_events",
    "evaluation_component_eligible",
    "solve_rank",
    "n_free_parameters",
    "residual_degrees_of_freedom",
    "residual_rms_m",
    "solve_variant",
]
HELDOUT_COLUMNS = [
    "region",
    "component_id",
    "event_index",
    "pair_key",
    "track_id_first",
    "track_id_second",
    "crossing_lon",
    "crossing_lat",
    "observed_diff_m",
    "variant",
    "heldout_residual_m",
    "abs_heldout_residual_m",
    "included_in_comparison",
    "exclusion_reason",
    "network_leverage",
    "solve_variant",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace only this script's existing outputs.",
    )
    return parser.parse_args()


def atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    os.replace(temporary, path)


def atomic_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def output_paths() -> list[Path]:
    paths = [
        OUTPUT_ROOT / "components.parquet",
        OUTPUT_ROOT / "comparison_summary.parquet",
        OUTPUT_ROOT / "manifest.json",
        REPORT_PATH,
    ]
    for region in REGIONS:
        paths.extend(
            [
                OUTPUT_ROOT / f"track_offsets_{region}.parquet",
                OUTPUT_ROOT / f"heldout_residuals_{region}.parquet",
            ]
        )
    return paths


def nmad(values: pd.Series | np.ndarray) -> float:
    array = np.asarray(values, dtype=np.float64)
    if len(array) == 0:
        return float("nan")
    median = np.median(array)
    return float(1.4826 * np.median(np.abs(array - median)))


def connected_components(events: pd.DataFrame) -> list[list[str]]:
    neighbors: dict[str, set[str]] = {}
    for first, second in events[["track_id_first", "track_id_second"]].itertuples(index=False):
        neighbors.setdefault(first, set()).add(second)
        neighbors.setdefault(second, set()).add(first)
    components: list[list[str]] = []
    remaining = set(neighbors)
    while remaining:
        start = min(remaining)
        stack = [start]
        found: set[str] = set()
        while stack:
            track = stack.pop()
            if track in found:
                continue
            found.add(track)
            stack.extend(neighbors[track] - found)
        remaining -= found
        components.append(sorted(found))
    return sorted(components, key=lambda tracks: tracks[0])


def design_matrix(events: pd.DataFrame, tracks: list[str]) -> np.ndarray:
    index = {track: position for position, track in enumerate(tracks)}
    matrix = np.zeros((len(events), len(tracks)), dtype=np.float64)
    rows = np.arange(len(events))
    first = events["track_id_first"].map(index).to_numpy(dtype=np.int64)
    second = events["track_id_second"].map(index).to_numpy(dtype=np.int64)
    matrix[rows, first] = -1.0
    matrix[rows, second] = 1.0
    return matrix


def solve_component(
    events: pd.DataFrame,
    tracks: list[str],
    anchors: dict[str, float],
) -> dict[str, object]:
    """Fit one component and retain the linear quantities needed for LOO."""
    full_design = design_matrix(events, tracks)
    observed = events["diff_m"].to_numpy(dtype=np.float64)
    n_tracks = len(tracks)
    anchor_positions = {tracks.index(track): value for track, value in anchors.items()}

    if anchors:
        fixed = np.zeros(n_tracks, dtype=np.float64)
        for position, value in anchor_positions.items():
            fixed[position] = value
        free_positions = [i for i in range(n_tracks) if i not in anchor_positions]
        transform = np.zeros((n_tracks, len(free_positions)), dtype=np.float64)
        for column, position in enumerate(free_positions):
            transform[position, column] = 1.0
        reduced_design = full_design @ transform
        reduced_observed = observed - full_design @ fixed
        base = fixed
        datum_type = "anchored"
    else:
        transform = np.vstack(
            [np.eye(n_tracks - 1, dtype=np.float64), -np.ones((1, n_tracks - 1))]
        )
        reduced_design = full_design @ transform
        reduced_observed = observed
        base = np.zeros(n_tracks, dtype=np.float64)
        datum_type = "free"

    n_parameters = reduced_design.shape[1]
    rank = int(np.linalg.matrix_rank(reduced_design)) if n_parameters else 0
    if rank != n_parameters:
        raise RuntimeError(
            f"component solve is rank deficient before leave-one-out: rank {rank}, "
            f"parameters {n_parameters}"
        )
    if n_parameters:
        parameters, _, _, _ = np.linalg.lstsq(reduced_design, reduced_observed, rcond=None)
        inverse_normal = np.linalg.inv(reduced_design.T @ reduced_design)
        leverage = np.einsum(
            "ij,jk,ik->i", reduced_design, inverse_normal, reduced_design
        )
    else:
        parameters = np.empty(0, dtype=np.float64)
        inverse_normal = np.empty((0, 0), dtype=np.float64)
        leverage = np.zeros(len(events), dtype=np.float64)
    offsets = base + transform @ parameters
    residual = observed - full_design @ offsets
    degrees_of_freedom = len(events) - n_parameters
    residual_variance = (
        float(residual @ residual / degrees_of_freedom)
        if degrees_of_freedom > 0
        else float("nan")
    )
    if n_parameters and np.isfinite(residual_variance):
        covariance = transform @ (residual_variance * inverse_normal) @ transform.T
        standard_error = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    else:
        standard_error = np.full(n_tracks, np.nan, dtype=np.float64)
    for position in anchor_positions:
        standard_error[position] = 0.0

    return {
        "datum_type": datum_type,
        "full_design": full_design,
        "offsets": offsets,
        "standard_error": standard_error,
        "residual": residual,
        "leverage": leverage,
        "rank": rank,
        "n_parameters": n_parameters,
        "degrees_of_freedom": degrees_of_freedom,
    }


def event_exclusion_reason(
    component_eligible: bool,
    first: str,
    second: str,
    crossover_counts: dict[str, int],
    leverage: float,
) -> str:
    if not component_eligible:
        return "component_below_predeclared_support"
    if crossover_counts[first] == 1 or crossover_counts[second] == 1:
        return "single_crossover_track"
    if not np.isfinite(leverage) or 1.0 - leverage <= 1e-10:
        return "leave_one_out_difference_not_identifiable"
    return ""


def analyze_region(
    region: str,
    events: pd.DataFrame,
    step23: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    events = events.copy()
    for column in ("track_id_first", "track_id_second", "pair_key"):
        events[column] = events[column].astype(str)
    if events[EVENT_COLUMNS].isna().any().any():
        raise ValueError(f"missing required crossover value in {region}")
    if (events["track_id_first"] == events["track_id_second"]).any():
        raise ValueError(f"self-crossover event in {region}")
    if not np.isfinite(events["diff_m"].to_numpy(dtype=float)).all():
        raise ValueError(f"non-finite crossover difference in {region}")

    step23_region = step23.loc[step23["region"].eq(region)].copy()
    if step23_region["track_id"].duplicated().any():
        raise ValueError(f"duplicate Step 23 track in {region}")
    step23_offset = dict(
        zip(
            step23_region["track_id"].astype(str),
            step23_region["estimated_bias_m"].astype(float),
        )
    )
    applied = step23_region.loc[step23_region["bias_applied"]]
    anchor_offset = dict(
        zip(applied["track_id"].astype(str), applied["estimated_bias_m"].astype(float))
    )

    track_rows: list[dict[str, object]] = []
    component_rows: list[dict[str, object]] = []
    heldout_rows: list[dict[str, object]] = []
    for component_number, tracks in enumerate(connected_components(events), start=1):
        component_id = f"{region}_c{component_number:03d}"
        selected = events.loc[
            events["track_id_first"].isin(tracks)
            & events["track_id_second"].isin(tracks)
        ].copy()
        selected["event_index"] = selected.index.astype(np.int64)
        selected = selected.reset_index(drop=True)
        anchors = {track: anchor_offset[track] for track in tracks if track in anchor_offset}
        fit = solve_component(selected, tracks, anchors)

        count_series = pd.concat(
            [selected["track_id_first"], selected["track_id_second"]], ignore_index=True
        ).value_counts()
        crossover_counts = {track: int(count_series.get(track, 0)) for track in tracks}
        neighbor_sets = {track: set() for track in tracks}
        for first, second in selected[["track_id_first", "track_id_second"]].itertuples(index=False):
            neighbor_sets[first].add(second)
            neighbor_sets[second].add(first)
        average_crossovers = 2.0 * len(selected) / len(tracks)
        component_eligible = len(tracks) >= 3 and average_crossovers >= 2.0

        offsets = np.asarray(fit["offsets"])
        standard_error = np.asarray(fit["standard_error"])
        for position, track in enumerate(tracks):
            track_rows.append(
                {
                    "region": region,
                    "track_id": track,
                    "component_id": component_id,
                    "datum_type": fit["datum_type"],
                    "network_offset_m": float(offsets[position]),
                    "offset_standard_error_m": float(standard_error[position]),
                    "n_crossovers": crossover_counts[track],
                    "n_distinct_neighbor_tracks": len(neighbor_sets[track]),
                    "is_step23_anchor": track in anchors,
                    "step23_offset_m": float(step23_offset.get(track, 0.0)),
                    "solve_variant": "unweighted",
                }
            )

        leverage = np.asarray(fit["leverage"])
        network_residual = np.asarray(fit["residual"])
        included_count = 0
        unidentifiable_count = 0
        candidate_count = 0
        for position, event in selected.iterrows():
            reason = event_exclusion_reason(
                component_eligible,
                event.track_id_first,
                event.track_id_second,
                crossover_counts,
                float(leverage[position]),
            )
            if component_eligible and crossover_counts[event.track_id_first] > 1 and crossover_counts[event.track_id_second] > 1:
                candidate_count += 1
            if reason == "leave_one_out_difference_not_identifiable":
                unidentifiable_count += 1
            included = reason == ""
            included_count += int(included)
            observed = float(event.diff_m)
            first_step23 = float(step23_offset.get(event.track_id_first, 0.0))
            second_step23 = float(step23_offset.get(event.track_id_second, 0.0))
            residual_by_variant = {
                "raw": observed,
                "step23": observed - (second_step23 - first_step23),
                "network": (
                    float(network_residual[position] / (1.0 - leverage[position]))
                    if included
                    else float("nan")
                ),
            }
            for variant, residual_value in residual_by_variant.items():
                if not included:
                    residual_value = float("nan")
                heldout_rows.append(
                    {
                        "region": region,
                        "component_id": component_id,
                        "event_index": int(event.event_index),
                        "pair_key": event.pair_key,
                        "track_id_first": event.track_id_first,
                        "track_id_second": event.track_id_second,
                        "crossing_lon": float(event.crossing_lon),
                        "crossing_lat": float(event.crossing_lat),
                        "observed_diff_m": observed,
                        "variant": variant,
                        "heldout_residual_m": residual_value,
                        "abs_heldout_residual_m": abs(residual_value),
                        "included_in_comparison": included,
                        "exclusion_reason": reason,
                        "network_leverage": float(leverage[position]),
                        "solve_variant": "unweighted",
                    }
                )

        residual = np.asarray(fit["residual"])
        component_rows.append(
            {
                "region": region,
                "component_id": component_id,
                "datum_type": fit["datum_type"],
                "n_tracks": len(tracks),
                "n_crossovers": len(selected),
                "crossovers_per_track_average": average_crossovers,
                "n_step23_anchors": len(anchors),
                "n_single_crossover_tracks": sum(value == 1 for value in crossover_counts.values()),
                "n_evaluation_candidate_events": candidate_count,
                "n_evaluated_events": included_count,
                "n_unidentifiable_leave_one_out_events": unidentifiable_count,
                "evaluation_component_eligible": component_eligible,
                "solve_rank": fit["rank"],
                "n_free_parameters": fit["n_parameters"],
                "residual_degrees_of_freedom": fit["degrees_of_freedom"],
                "residual_rms_m": float(np.sqrt(np.mean(residual**2))),
                "solve_variant": "unweighted",
            }
        )

    return (
        pd.DataFrame(track_rows, columns=TRACK_COLUMNS),
        pd.DataFrame(component_rows, columns=COMPONENT_COLUMNS),
        pd.DataFrame(heldout_rows, columns=HELDOUT_COLUMNS),
    )


def comparison_summary(heldout: pd.DataFrame) -> pd.DataFrame:
    included = heldout.loc[heldout["included_in_comparison"]].copy()
    rows: list[dict[str, object]] = []
    for region in [*REGIONS, "pooled"]:
        selected = included if region == "pooled" else included.loc[included["region"].eq(region)]
        for variant in ("raw", "step23", "network"):
            part = selected.loc[selected["variant"].eq(variant)]
            residual = part["heldout_residual_m"]
            rows.append(
                {
                    "region": region,
                    "variant": variant,
                    "n_heldout_events": int(len(part)),
                    "median_abs_heldout_residual_m": float(residual.abs().median()),
                    "nmad_heldout_residual_m": nmad(residual),
                    "solve_variant": "unweighted" if variant == "network" else "not_applicable",
                }
            )
    return pd.DataFrame(rows)


def fmt(value: float) -> str:
    return "NA" if not np.isfinite(value) else f"{value:.2f}"


def edge_case_rows(tracks: pd.DataFrame, heldout: pd.DataFrame) -> list[dict[str, object]]:
    cases = [("lon021_lat010", "elt18"), ("lon068_lat018", "odp130jr")]
    rows = []
    for region, track_id in cases:
        track = tracks.loc[tracks["region"].eq(region) & tracks["track_id"].eq(track_id)]
        if len(track) != 1:
            raise RuntimeError(f"expected one network row for {region}/{track_id}, found {len(track)}")
        events = heldout.loc[
            heldout["region"].eq(region)
            & (heldout["track_id_first"].eq(track_id) | heldout["track_id_second"].eq(track_id))
            & heldout["included_in_comparison"]
        ]
        metrics = {}
        for variant in ("raw", "step23", "network"):
            residual = events.loc[events["variant"].eq(variant), "heldout_residual_m"]
            metrics[variant] = float(residual.abs().median())
        record = track.iloc[0]
        rows.append(
            {
                "region": region,
                "track_id": track_id,
                "network_offset_m": float(record.network_offset_m),
                "step23_offset_m": float(record.step23_offset_m),
                "is_step23_anchor": bool(record.is_step23_anchor),
                "datum_type": record.datum_type,
                "n_crossovers": int(record.n_crossovers),
                "n_evaluated_events": int(len(events) // 3),
                "raw_median_abs_heldout_residual_m": metrics["raw"],
                "step23_median_abs_heldout_residual_m": metrics["step23"],
                "network_median_abs_heldout_residual_m": metrics["network"],
            }
        )
    return rows


def recommendation(summary: pd.DataFrame) -> tuple[str, str]:
    pooled = summary.loc[summary["region"].eq("pooled")].set_index("variant")
    network_median = pooled.loc["network", "median_abs_heldout_residual_m"]
    network_nmad = pooled.loc["network", "nmad_heldout_residual_m"]
    raw_median = pooled.loc["raw", "median_abs_heldout_residual_m"]
    raw_nmad = pooled.loc["raw", "nmad_heldout_residual_m"]
    step23_median = pooled.loc["step23", "median_abs_heldout_residual_m"]
    step23_nmad = pooled.loc["step23", "nmad_heldout_residual_m"]
    if network_median < min(raw_median, step23_median) and network_nmad < min(raw_nmad, step23_nmad):
        return (
            "globalize",
            "network 的 pooled 留出残差绝对值中位数和 NMAD 均低于两个对照",
        )
    if step23_median <= network_median and step23_nmad <= network_nmad:
        return (
            "keep step23",
            "Step 23 在两项预声明 pooled 指标上均优于 network",
        )
    return (
        "inconclusive",
        "两项预声明 pooled 指标没有一致支持同一种候选方法",
    )


def build_report(
    summary: pd.DataFrame,
    components: pd.DataFrame,
    tracks: pd.DataFrame,
    heldout: pd.DataFrame,
) -> str:
    decision, reason = recommendation(summary)
    cases = edge_case_rows(tracks, heldout)
    lines = [
        "# Step 10 SB crossover network constant-offset comparison",
        "",
        "## 结论",
        "",
        f"建议：`{decision}`。{reason}。该判断只适用于六个冻结区域的既有 SB×SB 交叉事件。",
        "",
        "## 三种方法的逐事件留一比较",
        "",
        "每个可评价连通分量逐次留出一个交叉事件。raw、Step 23 和 network 使用完全相同的留出事件；若删除该事件后轨线偏移差不可识别，三种方法均排除该事件。残差定义为观测 `depth_second - depth_first` 减去相应方法预测的偏移差。network 为等权最小二乘，没有使用 GEBCO 或深度相关权重。",
        "",
        "| region | variant | held-out events | median |residual| (m) | residual NMAD (m) |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for row in summary.itertuples(index=False):
        lines.append(
            f"| {row.region} | {row.variant} | {row.n_heldout_events} | "
            f"{fmt(row.median_abs_heldout_residual_m)} | {fmt(row.nmad_heldout_residual_m)} |"
        )

    split = (
        components.groupby("datum_type", as_index=False)
        .agg(n_components=("component_id", "size"), n_tracks=("n_tracks", "sum"))
        .sort_values("datum_type")
    )
    lines.extend(
        [
            "",
            "## 绝对锚定与自由网",
            "",
            "包含至少一条已应用 Step 23 偏移轨线的分量固定这些轨线的 Step 23 值；其余分量采用分量内偏移和为零，只能解释相对偏移。",
            "",
            "| datum type | components | tracks |",
            "| --- | ---: | ---: |",
        ]
    )
    for row in split.itertuples(index=False):
        lines.append(f"| {row.datum_type} | {row.n_components} | {row.n_tracks} |")
    lines.extend(
        [
            "",
            "| region | components | anchored components | free components | anchored tracks | free tracks | evaluated events | LOO-unidentifiable events |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for region in REGIONS:
        part = components.loc[components["region"].eq(region)]
        lines.append(
            f"| {region} | {len(part)} | {part['datum_type'].eq('anchored').sum()} | "
            f"{part['datum_type'].eq('free').sum()} | "
            f"{part.loc[part['datum_type'].eq('anchored'), 'n_tracks'].sum()} | "
            f"{part.loc[part['datum_type'].eq('free'), 'n_tracks'].sum()} | "
            f"{part['n_evaluated_events'].sum()} | "
            f"{part['n_unidentifiable_leave_one_out_events'].sum()} |"
        )

    lines.extend(
        [
            "",
            "## elt18 与 odp130jr",
            "",
            "| region | track | datum | Step 23 anchor | Step 23 offset (m) | network offset (m) | crossovers | evaluated events | raw median |LOO residual| (m) | Step 23 median (m) | network median (m) |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in cases:
        lines.append(
            f"| {case['region']} | {case['track_id']} | {case['datum_type']} | "
            f"{case['is_step23_anchor']} | {fmt(case['step23_offset_m'])} | "
            f"{fmt(case['network_offset_m'])} | {case['n_crossovers']} | "
            f"{case['n_evaluated_events']} | "
            f"{fmt(case['raw_median_abs_heldout_residual_m'])} | "
            f"{fmt(case['step23_median_abs_heldout_residual_m'])} | "
            f"{fmt(case['network_median_abs_heldout_residual_m'])} |"
        )
    elt18 = next(case for case in cases if case["track_id"] == "elt18")
    odp130jr = next(case for case in cases if case["track_id"] == "odp130jr")
    lines.extend(
        [
            "",
            f"elt18 的 network 偏移为 {fmt(elt18['network_offset_m'])} m，与先前 Step 23 候选值 -1247 m 方向相同且同为约千米量级。其事件级留出残差绝对值中位数从 raw 的 {fmt(elt18['raw_median_abs_heldout_residual_m'])} m 降至 {fmt(elt18['network_median_abs_heldout_residual_m'])} m，但仍有 {fmt(elt18['network_median_abs_heldout_residual_m'])} m，因此只支持存在大幅负偏移，不支持该常数偏移已充分解释交叉差。",
            "",
            f"odp130jr 是 Step 23 锚，按预声明方法被固定为 {fmt(odp130jr['network_offset_m'])} m，network 没有独立估计它。该轨线的留出残差绝对值中位数从 raw 的 {fmt(odp130jr['raw_median_abs_heldout_residual_m'])} m 增至 {fmt(odp130jr['network_median_abs_heldout_residual_m'])} m；这与先前 141 个交叉事件中心接近零的证据一致，也说明 -44 m 锚值不受这些交叉事件支持。",
            "",
            "## 方法与可追溯输出",
            "",
            "轨线偏移、标准误、交叉数、不同邻轨数和分量编号见 `track_offsets_<region>.parquet`。分量基准类型与评价纳入数见 `components.parquet`。每个事件的三种方法残差及排除原因见 `heldout_residuals_<region>.parquet`，汇总数来自 `comparison_summary.parquet`。运行命令、输入和软件环境见 `manifest.json`。",
            "",
        ]
    )
    return "\n".join(lines)


def git_state() -> dict[str, object]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, capture_output=True, check=True
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
    )
    return {"commit": commit, "dirty": dirty}


def build_manifest() -> dict[str, object]:
    return {
        "name": "sb_network_bias_1min_six_region_prototype",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "command": (
            "/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python "
            "ncei/analysis/27_sb_crossover_network_bias_1min.py"
        ),
        "retention": "retained",
        "retention_reason": "predeclared six-region method comparison",
        "git": git_state(),
        "parameters": {
            "solve_variant": "unweighted",
            "event_weight": 1.0,
            "component_min_tracks_for_evaluation": 3,
            "component_min_average_crossovers_per_track": 2.0,
            "single_crossover_tracks_excluded": True,
            "leave_one_out_identifiability_tolerance": 1e-10,
            "randomness": "deterministic",
        },
        "environment": {
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
            "pandas_version": pd.__version__,
            "numpy_version": np.__version__,
        },
        "source_paths": [
            str(CROSSOVER_ROOT.relative_to(REPO_ROOT)),
            str(STEP23_PATH.relative_to(REPO_ROOT)),
        ],
        "output_paths": [str(path.relative_to(REPO_ROOT)) for path in output_paths()],
        "assumptions": [
            "diff_m equals depth_second_m minus depth_first_m",
            "network offsets are subtracted from observed depths",
            "Step 23 tracks with bias_applied true are fixed anchors",
            "components without anchors use a zero-sum datum",
        ],
    }


def main() -> None:
    args = parse_args()
    expected = output_paths()
    existing = [path for path in expected if path.exists()]
    if existing and not args.overwrite:
        if len(existing) == len(expected):
            print("Complete Step 27 output set already exists; no files changed.")
            return
        raise SystemExit(
            "Partial Step 27 output set exists; inspect it and rerun with --overwrite "
            "to replace only Step 27 outputs."
        )

    step23 = pd.read_parquet(STEP23_PATH, columns=STEP23_COLUMNS)
    if step23[STEP23_COLUMNS].isna().any().any():
        raise ValueError("missing required Step 23 value")
    all_tracks = []
    all_components = []
    all_heldout = []
    for region in REGIONS:
        crossover_path = CROSSOVER_ROOT / f"crossovers_{region}.parquet"
        events = pd.read_parquet(crossover_path, columns=EVENT_COLUMNS)
        tracks, components, heldout = analyze_region(region, events, step23)
        all_tracks.append(tracks)
        all_components.append(components)
        all_heldout.append(heldout)

    tracks = pd.concat(all_tracks, ignore_index=True)
    components = pd.concat(all_components, ignore_index=True)
    heldout = pd.concat(all_heldout, ignore_index=True)
    summary = comparison_summary(heldout)
    report = build_report(summary, components, tracks, heldout)

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    for region in REGIONS:
        atomic_parquet(
            tracks.loc[tracks["region"].eq(region), TRACK_COLUMNS].reset_index(drop=True),
            OUTPUT_ROOT / f"track_offsets_{region}.parquet",
        )
        atomic_parquet(
            heldout.loc[heldout["region"].eq(region), HELDOUT_COLUMNS].reset_index(drop=True),
            OUTPUT_ROOT / f"heldout_residuals_{region}.parquet",
        )
    atomic_parquet(components[COMPONENT_COLUMNS], OUTPUT_ROOT / "components.parquet")
    atomic_parquet(summary, OUTPUT_ROOT / "comparison_summary.parquet")
    atomic_text(json.dumps(build_manifest(), indent=2) + "\n", OUTPUT_ROOT / "manifest.json")
    atomic_text(report, REPORT_PATH)
    print(
        f"Wrote {len(expected)} Step 27 files: {len(tracks)} regional track rows, "
        f"{len(components)} components, and "
        f"{int(heldout['included_in_comparison'].sum() / 3)} evaluated crossover events."
    )


if __name__ == "__main__":
    main()
