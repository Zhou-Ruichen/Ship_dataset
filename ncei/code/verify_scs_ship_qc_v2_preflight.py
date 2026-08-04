#!/usr/bin/env python3
"""Independently verify an immutable SCS ship-QC-v2 preflight run."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_OUTPUTS = {
    "candidate_cells.parquet",
    "candidate_components.parquet",
    "raw_context_features.parquet",
    "control_cells.parquet",
    "aggregation_conflicts.parquet",
    "reference_conflicts.parquet",
    "metadata_feasibility.csv",
    "preflight_summary.json",
    "collaborator_decision_pack.md",
    "audit_report.md",
    "audit_manifest.json",
}
PRODUCT_COLUMNS = [
    "canonical_cell_id", "source_provider", "lon_index", "lat_index",
    "ship_depth_m_positive_down", "raw_point_count", "gebco_2024_minus_ship_m",
    "family_consensus_minus_ship_m",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: str, seed: str = "") -> str:
    return hashlib.sha256(f"{seed}\0{value}".encode("utf-8")).hexdigest()


def resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def nmad(values: np.ndarray) -> float:
    median = float(np.median(values))
    return float(1.4826 * np.median(np.abs(values - median)))


def weighted_values(records: list[dict[str, Any]]) -> dict[str, float | int]:
    depths = np.asarray([float(record["file_cell_median_m"]) for record in records])
    counts = np.asarray([int(record["raw_point_count"]) for record in records], dtype=np.int64)
    order = np.argsort(depths, kind="stable")
    threshold = int(math.ceil(int(counts.sum()) / 2))
    weighted_median = depths[order][np.searchsorted(np.cumsum(counts[order]), threshold, side="left")]
    cruises = {str(record["cruise_id"]) for record in records if record.get("cruise_id")}
    return {
        "contributor_count": len(records),
        "contributor_raw_point_count": int(counts.sum()),
        "contributor_cruise_count": len(cruises),
        "replayed_unweighted_median_m": float(np.median(depths)),
        "point_count_weighted_mean_m": float(np.average(depths, weights=counts)),
        "point_count_weighted_median_m": float(weighted_median),
        "dominant_contributor_median_m": float(depths[int(np.argmax(counts))]),
        "contributor_range_m": float(np.ptp(depths)),
        "between_contributor_nmad_m": nmad(depths),
    }


def primary_raw_file(value: str) -> str:
    files = sorted(str(item) for item in json.loads(value))
    require(bool(files), "empty raw-files lineage")
    return files[0]


def band_label(value: float, edges: list[float], prefix: str) -> str:
    for lower, upper in zip(edges[:-1], edges[1:]):
        if lower < value <= upper or (lower == edges[0] and lower <= value <= upper):
            return f"{prefix}_{lower:g}_{upper:g}"
    raise ValueError(f"value outside frozen band edges: {value}")


def recompute_controls(base: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    cfg = config["controls"]
    seed = str(cfg["seed"])
    ratio = int(cfg["per_candidate_ratio"])
    depth_edges = [float(value) for value in cfg["depth_band_edges_m"]]
    count_edges = [float(value) for value in cfg["point_count_band_edges"]]
    cells = base.copy()
    cells["depth_band"] = cells["ship_depth_m_positive_down"].map(
        lambda value: band_label(float(value), depth_edges, "depth")
    )
    cells["point_count_band"] = cells["raw_point_count"].map(
        lambda value: band_label(float(value), count_edges, "points")
    )
    candidates = cells[cells["is_candidate"]].copy()
    candidates["_hash"] = candidates["canonical_cell_id"].map(
        lambda value: stable_hash(str(value), seed + "-candidate")
    )
    candidates = candidates.sort_values(["_hash", "canonical_cell_id"])
    available = cells[~cells["is_candidate"]].copy()
    available["_hash"] = available["canonical_cell_id"].map(lambda value: stable_hash(str(value), seed))
    available = available.sort_values(["_hash", "canonical_cell_id"])
    by_id = available.set_index("canonical_cell_id", drop=False)
    specs = {
        "same_file_depth_and_count": ["source_provider", "primary_raw_file", "depth_band", "point_count_band"],
        "same_file_depth": ["source_provider", "primary_raw_file", "depth_band"],
        "same_file_count": ["source_provider", "primary_raw_file", "point_count_band"],
        "same_file": ["source_provider", "primary_raw_file"],
    }
    pools: dict[tuple[str, tuple[Any, ...]], list[str]] = {}
    for level, columns in specs.items():
        for key, group in available.groupby(columns, sort=False, dropna=False):
            normalized = key if isinstance(key, tuple) else (key,)
            pools[(level, normalized)] = group["canonical_cell_id"].astype(str).tolist()
    positions: dict[tuple[str, tuple[Any, ...]], int] = defaultdict(int)
    used: set[str] = set()
    rows = []
    for candidate in candidates.itertuples(index=False):
        for _ in range(ratio):
            selected_id = None
            selected_level = None
            for level, columns in specs.items():
                pool_key = (level, tuple(getattr(candidate, column) for column in columns))
                pool = pools.get(pool_key, [])
                position = positions[pool_key]
                while position < len(pool) and pool[position] in used:
                    position += 1
                positions[pool_key] = position
                if position < len(pool):
                    selected_id = pool[position]
                    selected_level = level
                    positions[pool_key] = position + 1
                    break
            require(selected_id is not None, f"independent control selection failed for {candidate.canonical_cell_id}")
            used.add(str(selected_id))
            row = by_id.loc[selected_id].copy()
            row["control_match_level"] = selected_level
            row["matched_candidate_id"] = str(candidate.canonical_cell_id)
            rows.append(row)
    return pd.DataFrame(rows).sort_values("canonical_cell_id").reset_index(drop=True)


def recompute_components(candidates: pd.DataFrame) -> dict[str, str]:
    positions: dict[tuple[int, int, str, int], str] = {}
    attributes: dict[str, tuple[int, int, str, int]] = {}
    for row in candidates.itertuples(index=False):
        key = (int(row.lon_index), int(row.lat_index), str(row.source_provider), int(row.difference_sign))
        require(key not in positions, f"duplicate candidate position: {key}")
        positions[key] = str(row.canonical_cell_id)
        attributes[str(row.canonical_cell_id)] = key
    remaining = set(attributes)
    result: dict[str, str] = {}
    while remaining:
        first = min(remaining)
        queue = deque([first])
        remaining.remove(first)
        members = []
        while queue:
            cell_id = queue.popleft()
            members.append(cell_id)
            x, y, provider, sign = attributes[cell_id]
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    neighbour = positions.get((x + dx, y + dy, provider, sign))
                    if neighbour in remaining:
                        remaining.remove(neighbour)
                        queue.append(neighbour)
        members.sort()
        component = "cmp_" + stable_hash("\n".join(members))[:16]
        result.update({cell_id: component for cell_id in members})
    return result


def verify_manifest(run_dir: Path, manifest: dict[str, Any]) -> list[str]:
    checks = []
    require(manifest["run_id"] == run_dir.name, "manifest run ID mismatch")
    config_path = resolve(manifest["config_path"])
    require(sha256_file(config_path) == manifest["config_sha256"], "config SHA mismatch")
    checks.append("config_sha256")
    for name in ("producer", "verifier"):
        software = manifest["software"][name]
        require(sha256_file(resolve(software["path"])) == software["sha256"], f"software SHA mismatch: {name}")
    checks.append("software_sha256")
    for name, item in manifest["input_sha256"].items():
        path = resolve(item["path"])
        require(sha256_file(path) == item["sha256"], f"input SHA mismatch: {name}")
    checks.append("input_sha256")
    inventory_names = {item["path"] for item in manifest["outputs"]}
    require(inventory_names == REQUIRED_OUTPUTS - {"audit_manifest.json"}, "manifest output inventory mismatch")
    for item in manifest["outputs"]:
        path = run_dir / item["path"]
        require(path.is_file(), f"missing output: {path.name}")
        require(sha256_file(path) == item["sha256"], f"output SHA mismatch: {path.name}")
        require(path.stat().st_size == int(item["bytes"]), f"output size mismatch: {path.name}")
    checks.append("output_sha256_and_size")
    return checks


def verify_schemas(frames: dict[str, pd.DataFrame], config: dict[str, Any]) -> None:
    forbidden = [str(value).lower() for value in config["output_guards"]["forbidden_column_tokens"]]
    for name, frame in frames.items():
        violations = [column for column in frame.columns if any(token in column.lower() for token in forbidden)]
        require(not violations, f"forbidden decision columns in {name}: {violations}")
    forbidden_paths = [str(value).lower() for value in config["output_guards"]["forbidden_output_path_tokens"]]
    for name in REQUIRED_OUTPUTS:
        require(not any(token in name.lower() for token in forbidden_paths), f"forbidden decision token in output path: {name}")


def verify_run(run_dir: Path) -> dict[str, Any]:
    require(run_dir.is_dir(), f"run directory does not exist: {run_dir}")
    missing = REQUIRED_OUTPUTS - {path.name for path in run_dir.iterdir()}
    require(not missing, f"required outputs missing: {sorted(missing)}")
    manifest = json.loads((run_dir / "audit_manifest.json").read_text(encoding="utf-8"))
    checks = verify_manifest(run_dir, manifest)
    config_path = resolve(manifest["config_path"])
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    expected = config["expected"]
    product_path = resolve(config["inputs"]["product_consistency"]["path"])
    lineage_path = resolve(config["inputs"]["cell_lineage"]["path"])
    replay_path = resolve(config["inputs"]["raw_to_cell_replay"]["path"])
    product = pd.read_parquet(product_path, columns=PRODUCT_COLUMNS)
    lineage = pd.read_parquet(lineage_path)
    replay = pd.read_parquet(replay_path, columns=["canonical_cell_id", "replayed_depth_m", "frozen_depth_m", "signed_diff_m", "replay_result"])
    candidates = pd.read_parquet(run_dir / "candidate_cells.parquet")
    components = pd.read_parquet(run_dir / "candidate_components.parquet")
    raw_features = pd.read_parquet(run_dir / "raw_context_features.parquet")
    controls = pd.read_parquet(run_dir / "control_cells.parquet")
    aggregation = pd.read_parquet(run_dir / "aggregation_conflicts.parquet")
    reference = pd.read_parquet(run_dir / "reference_conflicts.parquet")
    metadata = pd.read_csv(run_dir / "metadata_feasibility.csv")
    frames = {
        "candidate_cells": candidates, "candidate_components": components,
        "raw_context_features": raw_features, "control_cells": controls,
        "aggregation_conflicts": aggregation, "reference_conflicts": reference,
        "metadata_feasibility": metadata,
    }
    verify_schemas(frames, config)
    checks.append("forbidden_output_schema")

    threshold = float(config["candidate"]["absolute_threshold_m"])
    expected_candidates = product[product["gebco_2024_minus_ship_m"].abs() > threshold].copy()
    require(len(expected_candidates) == int(expected["candidate_count"]), "independent candidate count drift")
    require(set(expected_candidates["canonical_cell_id"]) == set(candidates["canonical_cell_id"]), "candidate membership mismatch")
    require(candidates["canonical_cell_id"].is_unique, "duplicate candidate IDs")
    provider_counts = candidates["source_provider"].value_counts().to_dict()
    require(provider_counts == {key: int(value) for key, value in expected["candidate_provider_counts"].items()}, "candidate provider closure mismatch")
    checks.append("candidate_membership_and_counts")

    expected_reference = expected_candidates[
        expected_candidates["family_consensus_minus_ship_m"].abs()
        <= float(config["candidate"]["reference_consensus_absolute_threshold_m"])
    ]
    require(set(expected_reference["canonical_cell_id"]) == set(reference["canonical_cell_id"]), "reference-conflict membership mismatch")
    checks.append("reference_conflict_membership")

    component_map = recompute_components(candidates)
    persisted_map = dict(zip(candidates["canonical_cell_id"], candidates["component_id"]))
    require(component_map == persisted_map, "component assignment mismatch")
    require(set(components["component_id"]) == set(component_map.values()), "component summary ID mismatch")
    checks.append("component_membership")

    base = product.merge(lineage[["canonical_cell_id", "raw_files_json"]], on="canonical_cell_id", validate="one_to_one")
    base["primary_raw_file"] = base["raw_files_json"].map(primary_raw_file)
    base["is_candidate"] = base["gebco_2024_minus_ship_m"].abs() > threshold
    expected_controls = recompute_controls(base, config)
    require(expected_controls["canonical_cell_id"].tolist() == controls["canonical_cell_id"].tolist(), "control selection mismatch")
    require(expected_controls["control_match_level"].tolist() == controls["control_match_level"].tolist(), "control match-level mismatch")
    require(expected_controls["matched_candidate_id"].tolist() == controls["matched_candidate_id"].tolist(), "control pairing mismatch")
    require(not (set(controls["canonical_cell_id"]) & set(candidates["canonical_cell_id"])), "candidate/control overlap")
    checks.append("deterministic_controls")

    interpretation_vocabulary = set(config["interpretation_state_vocabulary"])
    require(set(candidates["interpretation_state"]) <= interpretation_vocabulary, "candidate interpretation state outside vocabulary")
    require(set(components["component_state"]) <= interpretation_vocabulary, "component state outside vocabulary")
    feature_by_id = raw_features.set_index("canonical_cell_id")
    lineage_by_id = lineage.set_index("canonical_cell_id")
    require(set(raw_features["sample_class"]) == {"candidate", "control"}, "raw feature sample-class closure failed")
    require(raw_features["canonical_cell_id"].is_unique, "duplicate raw-context cell IDs")
    for cell_id in set(candidates["canonical_cell_id"]) | set(controls["canonical_cell_id"]):
        feature = feature_by_id.loc[cell_id]
        lineage_row = lineage_by_id.loc[cell_id]
        require(int(feature["target_record_count"]) == int(lineage_row["raw_point_count"]), f"raw target-row count mismatch: {cell_id}")
        expected_ceiling = "source_grid_order_only" if lineage_row["source_provider"] == "mrar" else "raw_record_order_only"
        require(feature["context_evidence_ceiling"] == expected_ceiling, f"raw evidence ceiling mismatch: {cell_id}")
    raw_cfg = config["raw_context"]
    expected_sufficient = (
        raw_features["context_status"].eq("known")
        & raw_features["nearby_context_record_count"].ge(int(raw_cfg["minimum_nearby_records"]))
    )
    expected_signal = (
        expected_sufficient
        & raw_features["target_minus_context_m"].abs().gt(float(raw_cfg["discontinuity_absolute_threshold_m"]))
        & raw_features["target_minus_context_m"].abs().gt(
            float(raw_cfg["discontinuity_nmad_multiplier"]) * raw_features["context_nmad_m"].clip(lower=1.0)
        )
    )
    require(np.array_equal(expected_sufficient.to_numpy(), raw_features["raw_context_sufficient"].to_numpy()), "raw-context sufficiency arithmetic mismatch")
    require(np.array_equal(expected_signal.to_numpy(), raw_features["raw_discontinuity_signal"].to_numpy()), "raw discontinuity-signal arithmetic mismatch")
    aggregation_threshold = float(config["aggregation"]["material_between_contributor_nmad_m"])
    expected_states = []
    candidate_feature_by_id = raw_features[raw_features["sample_class"].eq("candidate")].set_index("canonical_cell_id")
    reference_ids = set(reference["canonical_cell_id"])
    for row in candidates.itertuples(index=False):
        feature = candidate_feature_by_id.loc[row.canonical_cell_id]
        if row.canonical_cell_id in reference_ids:
            state = "reference_version_conflict"
        elif (
            (math.isfinite(float(row.between_file_nmad_m)) and float(row.between_file_nmad_m) > aggregation_threshold)
            or (math.isfinite(float(row.between_cruise_nmad_m)) and float(row.between_cruise_nmad_m) > aggregation_threshold)
        ):
            state = "aggregation_conflict"
        elif not bool(feature.raw_context_sufficient):
            state = "insufficient_raw_context"
        elif bool(feature.raw_discontinuity_signal):
            state = "source_grid_discontinuity_candidate" if row.source_provider == "mrar" else "raw_record_discontinuity_candidate"
        else:
            state = "terrain_or_source_ambiguous"
        expected_states.append(state)
    require(expected_states == candidates["interpretation_state"].tolist(), "candidate interpretation-state arithmetic mismatch")
    checks.append("raw_row_context_signal_and_evidence_ceiling")

    expected_multi = lineage[lineage["contributor_records_json"].map(
        lambda value: len({record["raw_file"] for record in json.loads(value)}) > 1
    )]
    require(len(expected_multi) == int(expected["multi_file_count"]), "independent multi-file count drift")
    require(set(expected_multi["canonical_cell_id"]) == set(aggregation["canonical_cell_id"]), "aggregation census membership mismatch")
    aggregation_by_id = aggregation.set_index("canonical_cell_id")
    replay_by_id = replay.set_index("canonical_cell_id")
    numeric_fields = [
        "replayed_unweighted_median_m", "point_count_weighted_mean_m",
        "point_count_weighted_median_m", "dominant_contributor_median_m",
        "contributor_range_m", "between_contributor_nmad_m",
    ]
    for row in expected_multi.itertuples(index=False):
        computed = weighted_values(json.loads(row.contributor_records_json))
        persisted = aggregation_by_id.loc[row.canonical_cell_id]
        for field in numeric_fields:
            require(np.isclose(float(persisted[field]), float(computed[field]), rtol=0, atol=1e-9), f"aggregation arithmetic mismatch: {row.canonical_cell_id} {field}")
        replay_row = replay_by_id.loc[row.canonical_cell_id]
        require(np.isclose(float(persisted["replay_signed_difference_m"]), float(replay_row["signed_diff_m"]), rtol=0, atol=1e-12), f"replay difference mismatch: {row.canonical_cell_id}")
    require(int((aggregation["contributor_cruise_count"] > 1).sum()) == int(expected["multi_cruise_count"]), "multi-cruise closure mismatch")
    checks.append("aggregation_membership_and_arithmetic")

    factual_vocabulary = set(config["factual_status_vocabulary"])
    status_columns = [column for column in metadata.columns if column.endswith("_status")]
    require(len(metadata) == int(expected["vertical_ledger_count"]), "metadata row count mismatch")
    for column in status_columns:
        require(set(metadata[column].dropna().astype(str)) <= factual_vocabulary, f"metadata status outside vocabulary: {column}")
    require(metadata["crossover_feasibility"].eq("not_feasible_from_current_inputs").all(), "unsupported crossover feasibility")
    checks.append("metadata_status_and_crossover_ceiling")

    summary = json.loads((run_dir / "preflight_summary.json").read_text(encoding="utf-8"))
    require(int(summary["candidate_count"]) == len(candidates), "summary candidate mismatch")
    require(int(summary["control_count"]) == len(controls), "summary control mismatch")
    require(int(summary["aggregation_census_count"]) == len(aggregation), "summary aggregation mismatch")
    require(int(summary["reference_conflict_count"]) == len(reference), "summary reference mismatch")
    candidate_feature = raw_features[raw_features["sample_class"].eq("candidate")]
    control_feature = raw_features[raw_features["sample_class"].eq("control")]
    require(int(summary["raw_context_sufficient_candidate_count"]) == int(candidate_feature["raw_context_sufficient"].sum()), "summary raw-context count mismatch")
    expected_candidate_signal = candidate_feature[candidate_feature["raw_discontinuity_signal"]]["source_provider"].value_counts().sort_index().to_dict()
    expected_control_signal = control_feature[control_feature["raw_discontinuity_signal"]]["source_provider"].value_counts().sort_index().to_dict()
    require(summary["raw_signal_candidate_provider_counts"] == expected_candidate_signal, "summary candidate raw-signal mismatch")
    require(summary["raw_signal_control_provider_counts"] == expected_control_signal, "summary control raw-signal mismatch")
    for raw_file, expected_hash in summary["referenced_raw_file_sha256"].items():
        require(sha256_file(resolve(raw_file)) == expected_hash, f"referenced raw-file SHA mismatch: {raw_file}")
    checks.append("summary_and_referenced_raw_sha256")

    return {
        "status": "pass",
        "verified_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": run_dir.name,
        "checks": checks,
        "counts": {
            "candidate_cells": len(candidates),
            "candidate_components": len(components),
            "control_cells": len(controls),
            "raw_context_rows": len(raw_features),
            "aggregation_cells": len(aggregation),
            "reference_conflicts": len(reference),
            "metadata_rows": len(metadata),
        },
    }


def atomic_write_json(value: dict[str, Any], path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if Path.cwd().resolve() != REPO_ROOT:
        raise SystemExit(f"ERROR: run from repository root: {REPO_ROOT}")
    run_dir = resolve(args.run_dir).resolve()
    result = verify_run(run_dir)
    atomic_write_json(result, run_dir / "verification.json")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
