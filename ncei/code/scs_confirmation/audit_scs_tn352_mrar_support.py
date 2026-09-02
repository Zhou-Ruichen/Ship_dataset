#!/usr/bin/env python3
"""Run the frozen TN352-MRAR spatial-support diagnostic."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import scipy

from ncei.code.scs_confirmation.scs_tn352_audit_common import (
    MRAR_CELLS_PATH,
    REPO_ROOT,
    STAGE_C_ROOT,
    output_manifest,
    read_json,
    require,
    sha256_file,
    write_json,
)
from ncei.code.scs_confirmation.scs_tn352_support import (
    EARTH_RADIUS_M,
    THRESHOLDS_M,
    SupportPoints,
    cell_offsets,
    depth_summary,
    difference_metrics,
    great_circle_distance_m,
    load_mrar_points,
    load_tn352_points,
    mutual_nearest_pairs,
    occupancy_indices,
    pair_schema,
    spherical_centroid,
    support_schema,
    take_points,
    unit_vectors,
)


OUTPUT_ROLE = "development_only_not_confirmation"
TAIL_THRESHOLD_M = 500.0


class PairWriters:
    def __init__(self, directory: Path) -> None:
        self.schema = pair_schema()
        self.writers = {
            int(threshold): pq.ParquetWriter(
                directory / f"matched_difference_{int(threshold)}m.parquet",
                self.schema,
                compression="zstd",
            )
            for threshold in THRESHOLDS_M
        }
        self.counts = {int(threshold): 0 for threshold in THRESHOLDS_M}

    def write(self, threshold: int, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        table = pa.Table.from_pylist(rows, schema=self.schema)
        self.writers[threshold].write_table(table)
        self.counts[threshold] += table.num_rows

    def close(self) -> None:
        for writer in self.writers.values():
            writer.close()


def verify_freeze(phase_b: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    required = [
        "frozen_protocol.json",
        "input_lock.json",
        "cell_id_comparison.json",
        "phase_b_cell_id_status.parquet",
        "common_cell_cohort.parquet",
        "freeze_receipt.json",
    ]
    require(all((phase_b / name).is_file() for name in required), "Phase B freeze files are incomplete")
    protocol = read_json(phase_b / "frozen_protocol.json")
    lock = read_json(phase_b / "input_lock.json")
    receipt = read_json(phase_b / "freeze_receipt.json")
    require(protocol["status"] == "approved_frozen", "frozen protocol is not approved")
    require(lock["status"] == "frozen_before_depth_access" and lock["count_gate_status"] == "pass", "input lock did not pass")
    require(receipt["status"] == "pass" and receipt["process_boundary"] == "freeze_completed_without_depth_access", "freeze receipt did not pass")
    require(not lock["depth_value_columns_read_before_lock"] and not lock["depth_difference_columns_read_before_lock"], "freeze opened depth values")
    require(sha256_file(phase_b / "frozen_protocol.json") == receipt["frozen_protocol_sha256"] == lock["frozen_protocol_sha256"], "frozen protocol hash differs")
    require(sha256_file(phase_b / "input_lock.json") == receipt["input_lock_sha256"], "input lock hash differs")
    require(sha256_file(phase_b / "common_cell_cohort.parquet") == receipt["common_cell_cohort_sha256"] == lock["common_cell_cohort"]["sha256"], "cohort hash differs")
    require(sha256_file(phase_b / "cell_id_comparison.json") == receipt["cell_id_comparison_sha256"] == lock["cell_id_comparison"]["sha256"], "cell-ID comparison hash differs")
    require(sha256_file(phase_b / "phase_b_cell_id_status.parquet") == receipt["phase_b_cell_id_status_sha256"] == lock["phase_b_cell_id_status"]["sha256"], "cell-ID status hash differs")
    for name, record in lock["inputs"].items():
        path = Path(record["path"])
        if path.is_file():
            require(path.stat().st_size == int(record["bytes"]), f"locked input bytes differ: {name}")
            require(sha256_file(path) == record["sha256"], f"locked input hash differs: {name}")
        else:
            current_files = []
            for child in sorted(item for item in path.rglob("*") if item.is_file()):
                current_files.append(
                    {
                        "relative_path": child.relative_to(path).as_posix(),
                        "bytes": child.stat().st_size,
                        "sha256": sha256_file(child),
                    }
                )
            from ncei.code.scs_confirmation.scs_tn352_audit_common import canonical_sha256

            require(canonical_sha256(current_files) == record["sha256"], f"locked input tree hash differs: {name}")
    cohort = pq.read_table(phase_b / "common_cell_cohort.parquet").to_pylist()
    require(len(cohort) == 2_244 and len({row["cell_id"] for row in cohort}) == 2_244, "common cohort no longer has 2,244 unique cells")
    comparison = read_json(phase_b / "cell_id_comparison.json")
    require(comparison["status"] == "pass", "cell-ID comparison did not pass")
    require(not comparison["cell_ids"]["frozen_missing_tn352"], "frozen IDs are missing from TN352")
    require(not comparison["cell_ids"]["frozen_missing_raw_support"], "frozen IDs are missing MRAR raw support")
    require(comparison["counts"]["raw_support_only_not_in_frozen_scalar_pair"] == 123, "raw-support-only count differs")
    require({row["cell_id"] for row in cohort} == set(comparison["cell_ids"]["frozen_scalar_pair"]), "cohort differs from frozen assignments")
    return protocol, lock, cohort


def load_depth_labels(cohort: list[dict[str, Any]]) -> tuple[dict[str, float], dict[str, float]]:
    cell_ids = [str(row["cell_id"]) for row in cohort]
    stage = pq.read_table(
        STAGE_C_ROOT / "cell_cruise_candidates.parquet",
        columns=["cell_id", "median_depth_m_positive_down_exact"],
        filters=[("official_cruise_id", "=", "TN352")],
    ).to_pylist()
    stage_map = {
        str(row["cell_id"]): float(row["median_depth_m_positive_down_exact"])
        for row in stage
        if row["cell_id"] in set(cell_ids)
    }
    mrar_dataset = ds.dataset(MRAR_CELLS_PATH, format="parquet", partitioning="hive")
    mrar = mrar_dataset.to_table(
        columns=["cell_id", "representative_depth_m"],
        filter=ds.field("cell_id").isin(cell_ids),
    ).to_pylist()
    mrar_map = {str(row["cell_id"]): float(row["representative_depth_m"]) for row in mrar}
    require(set(stage_map) == set(cell_ids), "Stage C depth-label cohort differs")
    require(set(mrar_map) == set(cell_ids), "MRAR depth-label cohort differs")
    return stage_map, mrar_map


def load_object_h03(phase_a: Path) -> dict[str, int]:
    with (phase_a / "tn352_object_policy_summary.tsv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return {str(row["source_object_id"]): int(row["n_h03"]) for row in rows}


def validate_selected_source_object_count(selected: int, all_soundings: int, cell_id: str) -> None:
    require(selected > 0, f"TN352 selected source object count is zero: {cell_id}")
    require(
        selected <= all_soundings,
        f"TN352 selected source object count exceeds all-sounding count: {cell_id}",
    )


def point_slice(points: SupportPoints, start: int, stop: int) -> SupportPoints:
    return take_points(points, np.arange(start, stop, dtype=np.int64))


def metric_fields(prefix: str, metrics: dict[str, float | int | None]) -> dict[str, Any]:
    return {
        f"{prefix}_count": metrics["count"],
        f"{prefix}_bias_m": metrics["bias"],
        f"{prefix}_mae_m": metrics["mae"],
        f"{prefix}_rmse_m": metrics["rmse"],
        f"{prefix}_p50_abs_m": metrics["p50_abs"],
        f"{prefix}_p95_abs_m": metrics["p95_abs"],
        f"{prefix}_min_signed_m": metrics["min_signed"],
        f"{prefix}_max_signed_m": metrics["max_signed"],
        f"{prefix}_median_signed_m": metrics["median_signed"],
        f"{prefix}_persistent_tail": metrics["median_signed"] is not None and abs(float(metrics["median_signed"])) > TAIL_THRESHOLD_M,
        f"{prefix}_low_support": int(metrics["count"]) < 3,
    }


def pair_rows(
    cohort_row: dict[str, Any],
    tn: SupportPoints,
    mrar: SupportPoints,
    tn_indices: np.ndarray,
    mrar_indices: np.ndarray,
    distances: np.ndarray,
    threshold: float,
    object_h03: dict[str, int],
) -> list[dict[str, Any]]:
    selected = distances <= threshold
    rows: list[dict[str, Any]] = []
    for tn_index, mrar_index, distance in zip(tn_indices[selected], mrar_indices[selected], distances[selected]):
        tn_index = int(tn_index)
        mrar_index = int(mrar_index)
        tn_object = tn.group_values[int(tn.group_code[tn_index])]
        mrar_track = mrar.group_values[int(mrar.group_code[mrar_index])]
        delta = float(tn.depth[tn_index] - mrar.depth[mrar_index])
        rows.append(
            {
                "cell_id": str(cohort_row["cell_id"]),
                "lon_bin": int(cohort_row["lon_bin"]),
                "lat_bin": int(cohort_row["lat_bin"]),
                "tn352_source_object_id": tn_object,
                "tn352_parser_ping_index": int(tn.first_index[tn_index]),
                "tn352_beam_index": int(tn.second_index[tn_index]),
                "tn352_lon_deg": float(tn.lon[tn_index]),
                "tn352_lat_deg": float(tn.lat[tn_index]),
                "tn352_depth_m_positive_down": float(tn.depth[tn_index]),
                "mrar_track_id": mrar_track,
                "mrar_point_index_in_track": int(mrar.first_index[mrar_index]),
                "mrar_lon_deg": float(mrar.lon[mrar_index]),
                "mrar_lat_deg": float(mrar.lat[mrar_index]),
                "mrar_depth_m_positive_down": float(mrar.depth[mrar_index]),
                "distance_m": float(distance),
                "depth_difference_tn352_minus_mrar_m": delta,
                "absolute_depth_difference_m": abs(delta),
                "mutual_nearest": True,
                "threshold_m": float(threshold),
                "tn352_official_cruise_id": "TN352",
                "tn352_navigation_valid": bool(tn.navigation_valid[tn_index]),
                "tn352_qc_eligible_for_cell": True,
                "tn352_object_h03_associated": object_h03.get(tn_object, 0) > 0,
            }
        )
    return rows


def summarize_tail(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    definitions = [
        ("zero_or_low_footprint_overlap", lambda row, _prefix: bool(row["zero_footprint_overlap"] or row["low_footprint_overlap"])),
        ("high_relief", lambda row, _prefix: bool(row["high_relief"])),
        ("low_matched_support", lambda row, prefix: bool(row[f"{prefix}_low_support"]) if prefix else False),
        ("small_source_support", lambda row, _prefix: bool(row["small_source_support"])),
        ("h03_associated_object", lambda row, _prefix: bool(row["h03_associated_object"])),
    ]
    output: list[dict[str, Any]] = []
    bases: list[tuple[str, int | None, str | None, str]] = [("raw", None, None, "raw_cell_median_delta_m")]
    bases.extend((f"matched_{threshold}m", threshold, f"match_{threshold}m", f"match_{threshold}m_median_signed_m") for threshold in (100, 250, 500))
    for basis, threshold, prefix, value_field in bases:
        evaluable = [row for row in rows if row[value_field] is not None]
        values = np.asarray([float(row[value_field]) for row in evaluable], dtype=np.float64)
        tails = np.abs(values) > TAIL_THRESHOLD_M
        raw_same = np.asarray([abs(float(row["raw_cell_median_delta_m"])) for row in evaluable], dtype=np.float64)
        raw_tail_fraction = float(np.mean(raw_same > TAIL_THRESHOLD_M)) if evaluable else None
        tail_fraction = float(np.mean(tails)) if evaluable else None
        p95 = float(np.quantile(np.abs(values), 0.95, method="linear")) if evaluable else None
        raw_p95 = float(np.quantile(raw_same, 0.95, method="linear")) if evaluable else None
        p95_ratio = None if basis == "raw" or not raw_p95 else p95 / raw_p95
        tail_ratio = None if basis == "raw" or not raw_tail_fraction else tail_fraction / raw_tail_fraction
        if basis == "raw":
            contraction = "not_applicable"
        elif len(evaluable) < 30:
            contraction = "insufficient_support"
        elif raw_p95 == 0.0 or raw_tail_fraction == 0.0:
            contraction = "not_applicable"
        elif p95_ratio <= 0.75 and tail_ratio <= 0.75:
            contraction = "materially_contracted"
        else:
            contraction = "not_materially_contracted"
        overall = {
            "basis": basis,
            "threshold_m": threshold,
            "stratum": "overall",
            "cohort_cell_count": len(rows),
            "evaluable_cell_count": len(evaluable),
            "tail_cell_count": int(np.count_nonzero(tails)),
            "tail_fraction": tail_fraction,
            "absolute_delta_p50_m": float(np.quantile(np.abs(values), 0.50, method="linear")) if evaluable else None,
            "absolute_delta_p95_m": p95,
            "same_cell_raw_absolute_delta_p95_m": raw_p95,
            "same_cell_raw_tail_fraction": raw_tail_fraction,
            "p95_ratio_to_same_cell_raw": p95_ratio,
            "tail_fraction_ratio_to_same_cell_raw": tail_ratio,
            "material_contraction_decision": contraction,
            "stratum_cell_count": len(evaluable),
            "stratum_tail_count": int(np.count_nonzero(tails)),
            "complement_cell_count": 0,
            "complement_tail_count": 0,
            "tail_prevalence_risk_ratio": None,
            "concentration_decision": "not_applicable",
            "unresolved_cell_count": sum(bool(row["unresolved_500m"]) for row in rows),
            "label_upgrade_supported": False,
        }
        output.append(overall)
        for stratum, predicate in definitions:
            selected_rows = [row for row in evaluable if predicate(row, prefix)]
            complement_rows = [row for row in evaluable if not predicate(row, prefix)]
            selected_tail = sum(abs(float(row[value_field])) > TAIL_THRESHOLD_M for row in selected_rows)
            complement_tail = sum(abs(float(row[value_field])) > TAIL_THRESHOLD_M for row in complement_rows)
            selected_share = selected_tail / len(selected_rows) if selected_rows else None
            complement_share = complement_tail / len(complement_rows) if complement_rows else None
            if selected_share is None or complement_share is None:
                risk_ratio = None
            elif complement_share == 0.0:
                risk_ratio = math.inf if selected_share > 0.0 else None
            else:
                risk_ratio = selected_share / complement_share
            concentrated = selected_tail >= 10 and risk_ratio is not None and risk_ratio >= 2.0
            output.append(
                {
                    **overall,
                    "stratum": stratum,
                    "material_contraction_decision": "not_applicable",
                    "stratum_cell_count": len(selected_rows),
                    "stratum_tail_count": selected_tail,
                    "complement_cell_count": len(complement_rows),
                    "complement_tail_count": complement_tail,
                    "tail_prevalence_risk_ratio": risk_ratio,
                    "concentration_decision": "concentrated" if concentrated else "not_concentrated",
                }
            )
    return output


def write_tail_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def render_report(
    support_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    pair_counts: dict[int, int],
    cell_id_comparison: dict[str, Any],
) -> str:
    overall = {row["basis"]: row for row in summary_rows if row["stratum"] == "overall"}
    contraction_lines = []
    for threshold in (100, 250, 500):
        row = overall[f"matched_{threshold}m"]
        contraction_lines.append(
            f"- {threshold} m: `{row['material_contraction_decision']}`; "
            f"evaluable cells={row['evaluable_cell_count']:,}, P95 ratio={row['p95_ratio_to_same_cell_raw']:.4f}, "
            f"tail-fraction ratio={row['tail_fraction_ratio_to_same_cell_raw']:.4f}."
        )
    concentration = [
        row
        for row in summary_rows
        if row["basis"] == "matched_500m" and row["stratum"] != "overall" and row["concentration_decision"] == "concentrated"
    ]
    concentration_text = ", ".join(row["stratum"] for row in concentration) if concentration else "none of the registered strata"
    unresolved = sum(bool(row["unresolved_500m"]) for row in support_rows)
    matched_500 = overall["matched_500m"]
    overlap_500 = next(
        row
        for row in summary_rows
        if row["basis"] == "matched_500m" and row["stratum"] == "zero_or_low_footprint_overlap"
    )
    small_support_500 = next(
        row
        for row in summary_rows
        if row["basis"] == "matched_500m" and row["stratum"] == "small_source_support"
    )
    return f"""# TN352-MRAR spatial-support audit

Output role: `{OUTPUT_ROLE}`

Phase A classification: `B. official_raw_source_development_label`

Common-cell cohort: `{len(support_rows):,}`

Mutual-nearest pairs: 100 m `{pair_counts[100]:,}`, 250 m `{pair_counts[250]:,}`, 500 m `{pair_counts[500]:,}`

## Frozen cell-ID gate

All `{cell_id_comparison['counts']['frozen_scalar_pair']:,}` frozen scalar-pair
cell IDs are present in both the current TN352 candidates and MRAR raw support.
The current raw-support intersection contains
`{cell_id_comparison['counts']['raw_support_common']:,}` cells. Its additional
`{cell_id_comparison['counts']['raw_support_only_not_in_frozen_scalar_pair']:,}`
cells are recorded as `raw_support_only_not_in_frozen_scalar_pair` and excluded
from every source-difference result in this report. The only TN352 candidate
without MRAR raw support is
`{cell_id_comparison['cell_ids']['tn352_without_mrar_raw_support'][0]}`.

## Registered questions

### 1. Does the raw tail materially contract after support matching?

{chr(10).join(contraction_lines)}

The decision uses the frozen joint rule: at least 30 matched cells, P95 ratio
at most 0.75, and tail-fraction ratio at most 0.75. No threshold was changed
after reading depth differences.

### 2. Where is the persistent tail concentrated?

At 500 m, the registered concentration test is positive for:
`{concentration_text}`. The CSV records stratum and complement counts, tail
prevalence, and risk ratio. These are associations, not causal explanations.
The zero/low-overlap stratum contains
`{overlap_500['stratum_cell_count']:,}` of
`{matched_500['evaluable_cell_count']:,}` evaluable cells, so it does not
localize the tail by itself. High relief and low matched support remain the
discriminating positive strata.

### 3. How many cells remain unresolved?

`{unresolved:,}` cells meet the frozen unresolved definition: raw tail,
persistent or unmatched at 500 m, and none of the registered footprint,
relief, matched-support, source-support, or H03 associations.
This registered count is not a causal explanation count. The small-source
support flag applies to `{small_support_500['stratum_cell_count']:,}` of
`{matched_500['evaluable_cell_count']:,}` evaluable cells because MRAR has one
track here, so the protocol cannot identify a separate causally unexplained
subset.

### 4. Does this support a label upgrade?

No. Spatial agreement or disagreement with MRAR cannot establish TN352
processing provenance, source independence, or validated truth. Phase B does
not change the Phase A classification and does not promote the label to
confirmation or publication evidence.

## Method boundary

Distances use the frozen unit-sphere definition with radius
{EARTH_RADIUS_M:.1f} m. Mutual nearest neighbors are computed once without a
cutoff, with lexicographic stable-key tie resolution, and then subset at the
inclusive 100, 250, and 500 m thresholds. Signed depth difference is TN352
positive-down depth minus MRAR positive-down depth.

No GGM, PINN, GEBCO, product residual, model residual, MRAR merge, datum/bias
fit, cross-cruise aggregation, or sealed/sidecar body read was performed.
"""


def run(run_dir: Path) -> Path:
    run_dir = run_dir.resolve()
    phase_b = run_dir / "phase_b"
    require(phase_b.is_dir(), "Phase B freeze directory is missing")
    output_names = [
        "tn352_mrar_support_cells.parquet",
        "matched_difference_100m.parquet",
        "matched_difference_250m.parquet",
        "matched_difference_500m.parquet",
        "support_tail_summary.csv",
        "audit_report.md",
    ]
    require(all(not (phase_b / name).exists() for name in output_names + ["audit_manifest.json", "verification.json"]), "Phase B output already exists")
    failed = phase_b / "run_failed"
    require(not failed.exists(), "Phase B failed output already exists")
    protocol, lock, cohort = verify_freeze(phase_b)
    phase_a = Path(lock["phase_a_path"])
    require(phase_a.is_dir(), "locked Phase A directory is missing")
    cell_id_comparison = read_json(phase_b / "cell_id_comparison.json")
    temp = Path(tempfile.mkdtemp(prefix=".run-", dir=phase_b))
    try:
        stage_labels, mrar_labels = load_depth_labels(cohort)
        tn_points = load_tn352_points(cohort)
        mrar_points = load_mrar_points(cohort)
        object_h03 = load_object_h03(phase_a)
        tn_offsets = cell_offsets(tn_points, len(cohort))
        mrar_offsets = cell_offsets(mrar_points, len(cohort))
        writers = PairWriters(temp)
        support_rows: list[dict[str, Any]] = []
        try:
            for cell_index, cohort_row in enumerate(cohort):
                tn = point_slice(tn_points, int(tn_offsets[cell_index]), int(tn_offsets[cell_index + 1]))
                mrar = point_slice(mrar_points, int(mrar_offsets[cell_index]), int(mrar_offsets[cell_index + 1]))
                require(len(tn) == int(cohort_row["tn352_n_qc_eligible"]), f"TN352 point count differs: {cohort_row['cell_id']}")
                require(len(mrar) == int(cohort_row["mrar_n_points_pass_total"]), f"MRAR point count differs: {cohort_row['cell_id']}")
                tn_summary = depth_summary(tn.depth)
                mrar_summary = depth_summary(mrar.depth)
                cell_id = str(cohort_row["cell_id"])
                require(tn_summary["median"] == stage_labels[cell_id], f"TN352 exact median does not close: {cell_id}")
                require(mrar_summary["median"] == mrar_labels[cell_id], f"MRAR point median does not close: {cell_id}")
                tn_objects = sorted({tn.group_values[int(code)] for code in np.unique(tn.group_code)})
                mrar_tracks = sorted({mrar.group_values[int(code)] for code in np.unique(mrar.group_code)})
                validate_selected_source_object_count(
                    len(tn_objects),
                    int(cohort_row["tn352_n_source_objects_all_soundings"]),
                    cell_id,
                )
                require(len(mrar_tracks) == int(cohort_row["mrar_n_tracks"]), f"MRAR track count differs: {cell_id}")
                tn_centroid = spherical_centroid(tn.lon, tn.lat)
                mrar_centroid = spherical_centroid(mrar.lon, mrar.lat)
                centroid_distance = float(
                    great_circle_distance_m(
                        unit_vectors(np.asarray([tn_centroid[0]]), np.asarray([tn_centroid[1]])),
                        unit_vectors(np.asarray([mrar_centroid[0]]), np.asarray([mrar_centroid[1]])),
                    )[0]
                )
                tn_pair_index, mrar_pair_index, pair_distance, minimum_distance = mutual_nearest_pairs(tn, mrar)
                tn_occupancy = occupancy_indices(tn.lon, tn.lat, float(cohort_row["lon_center"]), float(cohort_row["lat_center"]))
                mrar_occupancy = occupancy_indices(mrar.lon, mrar.lat, float(cohort_row["lon_center"]), float(cohort_row["lat_center"]))
                intersection = len(tn_occupancy & mrar_occupancy)
                union = len(tn_occupancy | mrar_occupancy)
                smaller = min(len(tn_occupancy), len(mrar_occupancy))
                h03_objects = [object_id for object_id in tn_objects if object_h03.get(object_id, 0) > 0]
                row: dict[str, Any] = {
                    "cell_id": cell_id,
                    "lon_bin": int(cohort_row["lon_bin"]),
                    "lat_bin": int(cohort_row["lat_bin"]),
                    "lon_center": float(cohort_row["lon_center"]),
                    "lat_center": float(cohort_row["lat_center"]),
                    "tn352_official_cruise_id": "TN352",
                    "tn352_point_count": len(tn),
                    "mrar_point_count": len(mrar),
                    "tn352_source_object_count": len(tn_objects),
                    "mrar_track_count": len(mrar_tracks),
                    "tn352_source_object_ids": tn_objects,
                    "mrar_track_ids": mrar_tracks,
                    "tn352_navigation_valid_count": int(np.count_nonzero(tn.navigation_valid)),
                    "tn352_navigation_invalid_count": int(np.count_nonzero(~tn.navigation_valid)),
                    "h03_associated_object_count": len(h03_objects),
                    "h03_rows_in_contributing_objects": sum(object_h03[object_id] for object_id in h03_objects),
                    "tn352_centroid_lon": tn_centroid[0],
                    "tn352_centroid_lat": tn_centroid[1],
                    "mrar_centroid_lon": mrar_centroid[0],
                    "mrar_centroid_lat": mrar_centroid[1],
                    "centroid_distance_m": centroid_distance,
                    "minimum_cross_source_point_distance_m": minimum_distance,
                    "tn352_depth_min_m": tn_summary["min"],
                    "tn352_depth_max_m": tn_summary["max"],
                    "tn352_depth_range_m": tn_summary["range"],
                    "tn352_depth_nmad_m": tn_summary["nmad"],
                    "mrar_depth_min_m": mrar_summary["min"],
                    "mrar_depth_max_m": mrar_summary["max"],
                    "mrar_depth_range_m": mrar_summary["range"],
                    "mrar_depth_nmad_m": mrar_summary["nmad"],
                    "tn352_occupancy_count_100m": len(tn_occupancy),
                    "mrar_occupancy_count_100m": len(mrar_occupancy),
                    "occupancy_intersection_100m": intersection,
                    "occupancy_union_100m": union,
                    "occupancy_jaccard_100m": intersection / union if union else None,
                    "occupancy_smaller_support_coverage_100m": intersection / smaller if smaller else None,
                    "tn352_exact_median_depth_m_positive_down": stage_labels[cell_id],
                    "mrar_representative_depth_m_positive_down": mrar_labels[cell_id],
                    "raw_cell_median_delta_m": stage_labels[cell_id] - mrar_labels[cell_id],
                }
                for threshold in (100, 250, 500):
                    selected = pair_distance <= float(threshold)
                    delta = tn.depth[tn_pair_index[selected]] - mrar.depth[mrar_pair_index[selected]]
                    row.update(metric_fields(f"match_{threshold}m", difference_metrics(delta)))
                    writers.write(
                        threshold,
                        pair_rows(
                            cohort_row,
                            tn,
                            mrar,
                            tn_pair_index,
                            mrar_pair_index,
                            pair_distance,
                            float(threshold),
                            object_h03,
                        ),
                    )
                row["raw_tail"] = abs(float(row["raw_cell_median_delta_m"])) > TAIL_THRESHOLD_M
                row["high_relief"] = max(float(row["tn352_depth_range_m"]), float(row["mrar_depth_range_m"])) >= 500.0
                row["zero_footprint_overlap"] = intersection == 0
                row["low_footprint_overlap"] = row["occupancy_jaccard_100m"] is not None and float(row["occupancy_jaccard_100m"]) < 0.25
                row["small_source_support"] = len(tn_objects) <= 1 or len(mrar_tracks) <= 1
                row["h03_associated_object"] = bool(h03_objects)
                persistent = int(row["match_500m_count"]) == 0 or bool(row["match_500m_persistent_tail"])
                associated = (
                    row["zero_footprint_overlap"]
                    or row["low_footprint_overlap"]
                    or row["high_relief"]
                    or row["match_500m_low_support"]
                    or row["small_source_support"]
                    or row["h03_associated_object"]
                )
                row["unresolved_500m"] = bool(row["raw_tail"] and persistent and not associated)
                support_rows.append(row)
        finally:
            writers.close()
        require(len(support_rows) == 2_244, "support-cell output count differs")
        pq.write_table(pa.Table.from_pylist(support_rows, schema=support_schema()), temp / "tn352_mrar_support_cells.parquet", compression="zstd")
        summary_rows = summarize_tail(support_rows)
        write_tail_summary(temp / "support_tail_summary.csv", summary_rows)
        (temp / "audit_report.md").write_text(
            render_report(support_rows, summary_rows, writers.counts, cell_id_comparison), encoding="utf-8"
        )
        for name in output_names:
            os.rename(temp / name, phase_b / name)
        temp.rmdir()
        manifest_outputs = output_manifest(
            phase_b,
            [
                "frozen_protocol.json",
                "input_lock.json",
                "cell_id_comparison.json",
                "phase_b_cell_id_status.parquet",
                "common_cell_cohort.parquet",
                "freeze_receipt.json",
                *output_names,
            ],
        )
        manifest = {
            "schema_version": 1,
            "run_id": run_dir.name,
            "phase": "phase_b",
            "status": "produced_pending_independent_verification",
            "output_role": OUTPUT_ROLE,
            "confirmation_role_eligible": False,
            "phase_a_path": str(phase_a),
            "command": sys.argv,
            "cwd": str(Path.cwd()),
            "runtime_environment": {
                "python": sys.version,
                "platform": platform.platform(),
                "numpy": np.__version__,
                "pyarrow": pa.__version__,
                "scipy": scipy.__version__,
            },
            "random_seed": "not_applicable_deterministic_geometry",
            "phase_a_classification": {"code": "B", "value": "official_raw_source_development_label"},
            "frozen_protocol_sha256": sha256_file(phase_b / "frozen_protocol.json"),
            "input_lock_sha256": sha256_file(phase_b / "input_lock.json"),
            "common_cell_cohort_sha256": sha256_file(phase_b / "common_cell_cohort.parquet"),
            "outputs": manifest_outputs,
            "output_schema": {
                "support_cells": str(support_schema()),
                "matched_pairs": str(pair_schema()),
                "cell_id_status": str(pq.ParquetFile(phase_b / "phase_b_cell_id_status.parquet").schema_arrow),
                "tail_summary_fields": list(summary_rows[0]),
            },
            "row_counts": {
                "common_cells": len(support_rows),
                "raw_support_common_cells": cell_id_comparison["counts"]["raw_support_common"],
                "raw_support_only_not_in_frozen_scalar_pair": cell_id_comparison["counts"]["raw_support_only_not_in_frozen_scalar_pair"],
                "tn352_without_mrar_raw_support": cell_id_comparison["counts"]["tn352_without_mrar_raw_support"],
                "tn352_selected_points": len(tn_points),
                "mrar_selected_points": len(mrar_points),
                "matched_pairs_100m": writers.counts[100],
                "matched_pairs_250m": writers.counts[250],
                "matched_pairs_500m": writers.counts[500],
            },
            "access_counts": {
                "stage_c_depth_columns_opened_after_freeze": 2,
                "mrar_depth_columns_opened_after_freeze": 2,
                "sealed_body_reads": 0,
                "sidecar_body_reads": 0,
                "GGM": 0,
                "PINN": 0,
                "GEBCO": 0,
                "product_residual_comparison": 0,
                "model_residual_comparison": 0,
                "MRAR_merge": 0,
                "datum_or_bias_fit": 0,
                "cross_cruise_aggregation": 0,
            },
            "depth_access_started_after_freeze_process_exit": True,
        }
        write_json(phase_b / "audit_manifest.json", manifest)
        return phase_b
    except Exception as error:
        write_json(
            temp / "run_failure_receipt.json",
            {
                "schema_version": 1,
                "run_id": run_dir.name,
                "status": "fail",
                "error_type": type(error).__name__,
                "error": str(error),
                "freeze_files_modified": False,
            },
        )
        os.rename(temp, failed)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    print(run(args.run_dir))


if __name__ == "__main__":
    main()
