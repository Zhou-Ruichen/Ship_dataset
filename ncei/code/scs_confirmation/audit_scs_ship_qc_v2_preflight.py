#!/usr/bin/env python3
"""Build a read-only pre-correction evidence package for SCS ship soundings.

This audit localizes diagnostic product disagreements, then uses only frozen
lineage, raw records, contributor structure, and source metadata to describe
possible mechanisms. It never writes a corrected depth or a removal decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
PRODUCT_COLUMNS = [
    "canonical_cell_id",
    "lat",
    "lon",
    "ship_depth_m_positive_down",
    "source_provider",
    "lon_index",
    "lat_index",
    "raw_point_count",
    "raw_file_count",
    "official_cruise_count",
    "between_file_nmad_m",
    "between_cruise_nmad_m",
    "raw_replay_signed_diff_m",
    "raw_replay_result",
    "gebco_2024_minus_ship_m",
    "family_consensus_minus_ship_m",
    "family_consensus_nmad_m",
    "family_consensus_range_m",
]


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: str, seed: str = "") -> str:
    return hashlib.sha256(f"{seed}\0{value}".encode("utf-8")).hexdigest()


def nmad(values: Iterable[float]) -> float:
    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return float("nan")
    median = float(np.median(array))
    return float(1.4826 * np.median(np.abs(array - median)))


def expand_ranges(ranges: list[list[int]]) -> list[int]:
    indices: list[int] = []
    previous_end = -1
    for item in ranges:
        if len(item) != 2:
            raise ValueError(f"raw row range must have two entries: {item}")
        start, end = (int(item[0]), int(item[1]))
        if start < 0 or end < start or start <= previous_end:
            raise ValueError(f"invalid or overlapping raw row range: {item}")
        indices.extend(range(start, end + 1))
        previous_end = end
    return indices


def context_indices(target_indices: Iterable[int], window: int) -> set[int]:
    if window < 0:
        raise ValueError("record window must be non-negative")
    result: set[int] = set()
    for target in target_indices:
        target = int(target)
        result.update(range(max(0, target - window), target + window + 1))
    return result


def assign_components(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "canonical_cell_id",
        "lon_index",
        "lat_index",
        "source_provider",
        "difference_sign",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"component input missing columns: {sorted(missing)}")
    out = frame.copy()
    position: dict[tuple[int, int, str, int], str] = {}
    attrs: dict[str, tuple[int, int, str, int]] = {}
    for row in out.itertuples(index=False):
        key = (int(row.lon_index), int(row.lat_index), str(row.source_provider), int(row.difference_sign))
        if key in position:
            raise ValueError(f"duplicate component position: {key}")
        position[key] = str(row.canonical_cell_id)
        attrs[str(row.canonical_cell_id)] = key

    component_by_id: dict[str, str] = {}
    member_count: dict[str, int] = {}
    remaining = set(attrs)
    while remaining:
        start = min(remaining)
        queue = deque([start])
        members: list[str] = []
        remaining.remove(start)
        while queue:
            cell_id = queue.popleft()
            members.append(cell_id)
            x, y, provider, sign = attrs[cell_id]
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    neighbour = position.get((x + dx, y + dy, provider, sign))
                    if neighbour in remaining:
                        remaining.remove(neighbour)
                        queue.append(neighbour)
        members.sort()
        component_id = "cmp_" + stable_hash("\n".join(members))[:16]
        member_count[component_id] = len(members)
        for cell_id in members:
            component_by_id[cell_id] = component_id

    out["component_id"] = out["canonical_cell_id"].map(component_by_id)
    out["component_member_count"] = out["component_id"].map(member_count).astype("int64")
    return out


def _band_label(value: float, edges: list[float], prefix: str) -> str:
    for lower, upper in zip(edges[:-1], edges[1:]):
        if lower < value <= upper or (lower == edges[0] and lower <= value <= upper):
            return f"{prefix}_{lower:g}_{upper:g}"
    raise ValueError(f"value {value} outside frozen {prefix} edges")


def add_control_strata(frame: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    out = frame.copy()
    depth_edges = [float(v) for v in config["depth_band_edges_m"]]
    count_edges = [float(v) for v in config["point_count_band_edges"]]
    out["depth_band"] = out["ship_depth_m_positive_down"].map(
        lambda value: _band_label(float(value), depth_edges, "depth")
    )
    out["point_count_band"] = out["raw_point_count"].map(
        lambda value: _band_label(float(value), count_edges, "points")
    )
    return out


def choose_controls(cells: pd.DataFrame, seed: str, ratio: int) -> pd.DataFrame:
    required = {
        "canonical_cell_id",
        "source_provider",
        "primary_raw_file",
        "depth_band",
        "point_count_band",
        "is_candidate",
    }
    missing = required - set(cells.columns)
    if missing:
        raise ValueError(f"control input missing columns: {sorted(missing)}")
    if ratio < 1:
        raise ValueError("control ratio must be positive")
    candidates = cells[cells["is_candidate"]].copy()
    candidates["_selection_hash"] = candidates["canonical_cell_id"].map(
        lambda cell_id: stable_hash(str(cell_id), seed + "-candidate")
    )
    candidates = candidates.sort_values(["_selection_hash", "canonical_cell_id"])
    available = cells[~cells["is_candidate"]].copy()
    available["_selection_hash"] = available["canonical_cell_id"].map(
        lambda cell_id: stable_hash(str(cell_id), seed)
    )
    available = available.sort_values(["_selection_hash", "canonical_cell_id"])
    available_by_id = available.set_index("canonical_cell_id", drop=False)
    pool_specs = {
        "same_file_depth_and_count": ["source_provider", "primary_raw_file", "depth_band", "point_count_band"],
        "same_file_depth": ["source_provider", "primary_raw_file", "depth_band"],
        "same_file_count": ["source_provider", "primary_raw_file", "point_count_band"],
        "same_file": ["source_provider", "primary_raw_file"],
    }
    pools: dict[tuple[str, tuple[Any, ...]], list[str]] = {}
    for level, columns in pool_specs.items():
        for key, group in available.groupby(columns, sort=False, dropna=False):
            normalized_key = key if isinstance(key, tuple) else (key,)
            pools[(level, normalized_key)] = group["canonical_cell_id"].astype(str).tolist()
    pool_positions: dict[tuple[str, tuple[Any, ...]], int] = defaultdict(int)
    used: set[str] = set()
    selected_rows: list[pd.Series] = []
    for candidate in candidates.itertuples(index=False):
        for replicate in range(ratio):
            chosen: pd.Series | None = None
            match_level = ""
            for level, columns in pool_specs.items():
                key = tuple(getattr(candidate, column) for column in columns)
                pool_key = (level, key)
                pool = pools.get(pool_key, [])
                position = pool_positions[pool_key]
                while position < len(pool) and pool[position] in used:
                    position += 1
                pool_positions[pool_key] = position
                if position < len(pool):
                    cell_id = pool[position]
                    pool_positions[pool_key] = position + 1
                    chosen = available_by_id.loc[cell_id].copy()
                    match_level = level
                    break
            if chosen is None:
                raise ValueError(
                    f"insufficient same-file controls for {candidate.canonical_cell_id} replicate {replicate}"
                )
            used.add(str(chosen["canonical_cell_id"]))
            chosen["control_stratum"] = "|".join([
                str(candidate.source_provider), str(candidate.primary_raw_file),
                str(candidate.depth_band), str(candidate.point_count_band),
            ])
            chosen["control_match_level"] = match_level
            chosen["matched_candidate_id"] = str(candidate.canonical_cell_id)
            selected_rows.append(chosen)
    if not selected_rows:
        return cells.iloc[0:0].copy()
    result = pd.DataFrame(selected_rows).drop(columns="_selection_hash")
    result["control_seed"] = seed
    result["selection_order"] = np.arange(len(result), dtype=np.int64)
    return result.sort_values("canonical_cell_id").reset_index(drop=True)


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius_km = 6371.0088
    lon1r, lat1r, lon2r, lat2r = map(math.radians, (lon1, lat1, lon2, lat2))
    dlon = lon2r - lon1r
    dlat = lat2r - lat1r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1r) * math.cos(lat2r) * math.sin(dlon / 2) ** 2
    return 2 * radius_km * math.asin(min(1.0, math.sqrt(a)))


def summarize_raw_rows(
    rows: dict[Any, tuple[float, float, float, int]],
    target_indices: set[Any],
    cell_lon: float,
    cell_lat: float,
    radius_km: float,
) -> dict[str, Any]:
    if not target_indices or not rows:
        return {
            "context_status": "not_recoverable",
            "target_record_count": 0,
            "context_record_count": 0,
            "nearby_context_record_count": 0,
            "target_depth_median_m": float("nan"),
            "context_depth_median_m": float("nan"),
            "context_nmad_m": float("nan"),
            "context_range_m": float("nan"),
            "target_minus_context_m": float("nan"),
            "record_order_depth_jump_median_m": float("nan"),
            "raw_layout_column_counts_json": "[]",
        }
    targets = [rows[index] for index in target_indices if index in rows]
    context_pairs = [(index, value) for index, value in rows.items() if index not in target_indices]
    nearby = [
        value for _, value in context_pairs
        if haversine_km(float(value[0]), float(value[1]), cell_lon, cell_lat) <= radius_km
    ]
    target_depths = np.asarray([value[2] for value in targets], dtype=float)
    context_depths = np.asarray([value[2] for value in nearby], dtype=float)
    layout_counts = Counter(int(value[3]) for value in rows.values())
    jumps: list[float] = []
    for _, grouped in _group_rows_by_file(context_pairs).items():
        ordered = [value[2] for _, value in sorted(grouped, key=lambda item: _row_number(item[0]))]
        jumps.extend(abs(b - a) for a, b in zip(ordered[:-1], ordered[1:]))
    status = "known" if target_depths.size else "not_recoverable"
    target_median = float(np.median(target_depths)) if target_depths.size else float("nan")
    context_median = float(np.median(context_depths)) if context_depths.size else float("nan")
    return {
        "context_status": status,
        "target_record_count": int(target_depths.size),
        "context_record_count": int(len(context_pairs)),
        "nearby_context_record_count": int(context_depths.size),
        "target_depth_median_m": target_median,
        "context_depth_median_m": context_median,
        "context_nmad_m": nmad(context_depths),
        "context_range_m": float(np.ptp(context_depths)) if context_depths.size else float("nan"),
        "target_minus_context_m": target_median - context_median,
        "record_order_depth_jump_median_m": float(np.median(jumps)) if jumps else float("nan"),
        "raw_layout_column_counts_json": json.dumps(dict(sorted(layout_counts.items())), separators=(",", ":")),
    }


def _row_number(index: Any) -> int:
    return int(index[-1]) if isinstance(index, tuple) else int(index)


def _group_rows_by_file(items: list[tuple[Any, tuple[float, float, float, int]]]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for index, value in items:
        file_key = str(index[0]) if isinstance(index, tuple) else "single"
        grouped[file_key].append((index, value))
    return grouped


def aggregation_alternatives(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise ValueError("contributor record list is empty")
    depths = np.asarray([float(record["file_cell_median_m"]) for record in records], dtype=float)
    counts = np.asarray([int(record["raw_point_count"]) for record in records], dtype=np.int64)
    if not np.isfinite(depths).all() or (counts <= 0).any():
        raise ValueError("invalid contributor depth or point count")
    order = np.argsort(depths, kind="stable")
    sorted_depths = depths[order]
    sorted_counts = counts[order]
    threshold = int(math.ceil(int(counts.sum()) / 2))
    weighted_median = float(sorted_depths[np.searchsorted(np.cumsum(sorted_counts), threshold, side="left")])
    dominant_index = int(np.argmax(counts))
    cruise_ids = {str(record["cruise_id"]) for record in records if record.get("cruise_id")}
    return {
        "contributor_count": int(len(records)),
        "contributor_raw_point_count": int(counts.sum()),
        "contributor_cruise_count": int(len(cruise_ids)),
        "replayed_unweighted_median_m": float(np.median(depths)),
        "point_count_weighted_mean_m": float(np.average(depths, weights=counts)),
        "point_count_weighted_median_m": weighted_median,
        "dominant_contributor_median_m": float(depths[dominant_index]),
        "dominant_contributor_point_count": int(counts[dominant_index]),
        "smallest_contributor_point_count": int(counts.min()),
        "largest_to_smallest_point_count_ratio": float(counts.max() / counts.min()),
        "contributor_range_m": float(np.ptp(depths)),
        "between_contributor_nmad_m": nmad(depths),
    }


def validate_interpretation_state(value: str, vocabulary: set[str]) -> None:
    if value not in vocabulary:
        raise ValueError(f"interpretation state outside frozen vocabulary: {value}")


def validate_output_schema(frame: pd.DataFrame, forbidden_tokens: list[str]) -> None:
    violations = [
        column for column in frame.columns
        if any(token.lower() in column.lower() for token in forbidden_tokens)
    ]
    if violations:
        raise ValueError(f"decision-bearing columns are forbidden in evidence output: {violations}")


def validate_output_path(path: Path, forbidden_tokens: list[str]) -> None:
    lowered = str(path).lower()
    violations = [token for token in forbidden_tokens if token.lower() in lowered]
    if violations:
        raise ValueError(f"forbidden decision token in output path {path}: {violations}")


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if config.get("version") != 1:
        raise ValueError("unsupported config version")
    return config


def validate_frozen_inputs(config: dict[str, Any]) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for key, spec in config["inputs"].items():
        path_text = str(spec["path"])
        lowered = path_text.lower()
        if any(token in lowered for token in ("prediction", "model_error", "residual_dataset")):
            raise ValueError(f"forbidden downstream artifact in input config: {path_text}")
        path = resolve_repo_path(path_text)
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = sha256_file(path)
        if actual != spec["sha256"]:
            raise ValueError(f"SHA256 mismatch for {key}: expected {spec['sha256']}, got {actual}")
        paths[key] = path
    return paths


def load_inputs(paths: dict[str, Path]) -> tuple[pd.DataFrame, ...]:
    product = pd.read_parquet(paths["product_consistency"], columns=PRODUCT_COLUMNS)
    lineage = pd.read_parquet(paths["cell_lineage"])
    replay_columns = [
        "canonical_cell_id", "replayed_depth_m", "frozen_depth_m", "signed_diff_m",
        "replay_result", "raw_file_count", "official_cruise_count",
    ]
    replay = pd.read_parquet(paths["raw_to_cell_replay"], columns=replay_columns)
    identity = pd.read_csv(paths["source_identity_ledger"])
    vertical = pd.read_csv(paths["vertical_datum_ledger"])
    return product, lineage, replay, identity, vertical


def validate_input_closure(
    product: pd.DataFrame,
    lineage: pd.DataFrame,
    replay: pd.DataFrame,
    identity: pd.DataFrame,
    vertical: pd.DataFrame,
    expected: dict[str, Any],
) -> None:
    for name, frame in (("product", product), ("lineage", lineage), ("replay", replay)):
        if len(frame) != int(expected["cell_count"]) or not frame["canonical_cell_id"].is_unique:
            raise ValueError(f"{name} cell closure failed")
    keys = set(product["canonical_cell_id"])
    if keys != set(lineage["canonical_cell_id"]) or keys != set(replay["canonical_cell_id"]):
        raise ValueError("cell keys differ across frozen inputs")
    provider_counts = product["source_provider"].value_counts().to_dict()
    if provider_counts != {key: int(value) for key, value in expected["provider_counts"].items()}:
        raise ValueError(f"provider closure failed: {provider_counts}")
    if len(identity) != int(expected["identity_ledger_count"]):
        raise ValueError("identity ledger count drift")
    if len(vertical) != int(expected["vertical_ledger_count"]):
        raise ValueError("vertical ledger count drift")
    replay_counts = replay["replay_result"].value_counts().to_dict()
    if replay_counts.get("exact", 0) != int(expected["replay_exact_count"]):
        raise ValueError(f"replay exact closure failed: {replay_counts}")
    if replay_counts.get("different", 0) != int(expected["replay_different_count"]):
        raise ValueError(f"replay different closure failed: {replay_counts}")


def _primary_raw_file(raw_files_json: str) -> str:
    files = sorted(str(value) for value in json.loads(raw_files_json))
    if not files:
        raise ValueError("cell has no lineage raw file")
    return files[0]


def build_registry(
    product: pd.DataFrame,
    lineage: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    candidate_cfg = config["candidate"]
    threshold = float(candidate_cfg["absolute_threshold_m"])
    consensus_threshold = float(candidate_cfg["reference_consensus_absolute_threshold_m"])
    base = product.merge(
        lineage[[
            "canonical_cell_id", "raw_files_json", "raw_file_sha256_json", "raw_row_ids_json",
            "official_cruise_ids_json", "contributor_records_json", "official_lines_json_status",
            "official_time_ranges_json_status", "sonar_types_json_status",
        ]],
        on="canonical_cell_id",
        how="left",
        validate="one_to_one",
    )
    base["primary_raw_file"] = base["raw_files_json"].map(_primary_raw_file)
    base["is_candidate"] = base[candidate_cfg["diagnostic_field"]].abs() > threshold
    base["difference_sign"] = np.sign(base[candidate_cfg["diagnostic_field"]]).astype("int8")
    base["is_reference_conflict"] = (
        base["is_candidate"]
        & (base[candidate_cfg["reference_consensus_field"]].abs() <= consensus_threshold)
    )
    base = add_control_strata(base, config["controls"])
    candidates = base[base["is_candidate"]].copy()
    expected = config["expected"]
    counts = candidates["source_provider"].value_counts().to_dict()
    if len(candidates) != int(expected["candidate_count"]):
        raise ValueError(f"candidate count drift: {len(candidates)}")
    if counts != {key: int(value) for key, value in expected["candidate_provider_counts"].items()}:
        raise ValueError(f"candidate provider drift: {counts}")
    mrar_extreme = candidates[
        candidates["source_provider"].eq("mrar")
        & candidates[candidate_cfg["diagnostic_field"]].abs().gt(5000.0)
    ]
    if len(mrar_extreme) != int(expected["mrar_candidate_absolute_difference_over_5000_count"]):
        raise ValueError(f"MRAR >5,000 m diagnostic-difference drift: {len(mrar_extreme)}")
    reference = candidates[candidates["is_reference_conflict"]].copy()
    if len(reference) != int(expected["reference_conflict_count"]):
        raise ValueError(f"reference conflict drift: {len(reference)}")
    jamstec = candidates[candidates["source_provider"].eq("jamstec")]
    jamstec_files = set()
    jamstec_cruises = set()
    for row in jamstec.itertuples(index=False):
        jamstec_files.update(json.loads(row.raw_files_json))
        jamstec_cruises.update(json.loads(row.official_cruise_ids_json))
    if len(jamstec_files) != int(expected["jamstec_candidate_raw_file_count"]):
        raise ValueError(f"JAMSTEC candidate file closure failed: {len(jamstec_files)}")
    if len(jamstec_cruises) != int(expected["jamstec_candidate_cruise_count"]):
        raise ValueError(f"JAMSTEC candidate cruise closure failed: {len(jamstec_cruises)}")
    controls = choose_controls(
        base,
        seed=str(config["controls"]["seed"]),
        ratio=int(config["controls"]["per_candidate_ratio"]),
    )
    if set(controls["canonical_cell_id"]) & set(candidates["canonical_cell_id"]):
        raise ValueError("control and candidate cells overlap")
    return candidates, controls, reference


def build_raw_requests(selected: pd.DataFrame, window: int) -> tuple[dict[str, set[int]], dict[str, dict[str, set[int]]], dict[str, str], dict[str, str]]:
    file_requests: dict[str, set[int]] = defaultdict(set)
    cell_targets: dict[str, dict[str, set[int]]] = {}
    expected_hashes: dict[str, str] = {}
    providers: dict[str, str] = {}
    for row in selected.itertuples(index=False):
        by_file: dict[str, set[int]] = {}
        hashes = json.loads(row.raw_file_sha256_json)
        for record in json.loads(row.raw_row_ids_json):
            raw_file = str(record["raw_file"])
            targets = set(expand_ranges(record["ranges_0_based_inclusive"]))
            if raw_file in by_file:
                raise ValueError(f"duplicate raw file entry for {row.canonical_cell_id}: {raw_file}")
            by_file[raw_file] = targets
            file_requests[raw_file].update(context_indices(targets, window))
            expected_hash = str(hashes.get(raw_file, ""))
            if not expected_hash:
                raise ValueError(f"missing lineage SHA for {raw_file}")
            if raw_file in expected_hashes and expected_hashes[raw_file] != expected_hash:
                raise ValueError(f"conflicting lineage SHA for {raw_file}")
            if raw_file in providers and providers[raw_file] != row.source_provider:
                raise ValueError(f"raw file assigned to multiple providers: {raw_file}")
            expected_hashes[raw_file] = expected_hash
            providers[raw_file] = str(row.source_provider)
        cell_targets[str(row.canonical_cell_id)] = by_file
    return file_requests, cell_targets, expected_hashes, providers


def parse_raw_line(line: str, provider: str) -> tuple[float, float, float, int]:
    tokens = line.split()
    if len(tokens) == 3:
        lon, lat, raw_depth = map(float, tokens)
    elif len(tokens) == 6:
        lon, lat, raw_depth = map(float, tokens[-3:])
    else:
        raise ValueError(f"unsupported raw row layout with {len(tokens)} columns")
    lon = ((lon + 180.0) % 360.0) - 180.0
    depth = -raw_depth if provider == "mrar" else raw_depth
    if not all(math.isfinite(value) for value in (lon, lat, depth)) or depth <= 0:
        raise ValueError("referenced raw row contains invalid coordinate/depth")
    return lon, lat, depth, len(tokens)


def stream_raw_requests(
    file_requests: dict[str, set[int]],
    expected_hashes: dict[str, str],
    providers: dict[str, str],
) -> tuple[dict[str, dict[int, tuple[float, float, float, int]]], dict[str, str]]:
    retained: dict[str, dict[int, tuple[float, float, float, int]]] = {}
    actual_hashes: dict[str, str] = {}
    for raw_file in sorted(file_requests):
        path = resolve_repo_path(raw_file)
        if not path.is_file():
            raise FileNotFoundError(path)
        requested = file_requests[raw_file]
        if not requested:
            retained[raw_file] = {}
            continue
        maximum = max(requested)
        digest = hashlib.sha256()
        found: dict[int, tuple[float, float, float, int]] = {}
        with path.open("rb") as handle:
            for row_index, raw_line in enumerate(handle):
                digest.update(raw_line)
                if row_index in requested:
                    line = raw_line.decode("utf-8", errors="strict")
                    found[row_index] = parse_raw_line(line, providers[raw_file])
                if row_index >= maximum:
                    for remainder in handle:
                        digest.update(remainder)
                    break
        actual = digest.hexdigest()
        if actual != expected_hashes[raw_file]:
            raise ValueError(f"raw-file SHA mismatch for {raw_file}: expected {expected_hashes[raw_file]}, got {actual}")
        actual_hashes[raw_file] = actual
        retained[raw_file] = found
    return retained, actual_hashes


def verify_raw_hashes(expected_hashes: dict[str, str]) -> dict[str, str]:
    actual: dict[str, str] = {}
    for raw_file, expected in sorted(expected_hashes.items()):
        digest = sha256_file(resolve_repo_path(raw_file))
        if digest != expected:
            raise ValueError(f"raw-file SHA mismatch for {raw_file}: expected {expected}, got {digest}")
        actual[raw_file] = digest
    return actual


def build_raw_context_features(
    selected: pd.DataFrame,
    cell_targets: dict[str, dict[str, set[int]]],
    retained: dict[str, dict[int, tuple[float, float, float, int]]],
    radius_km: float,
    record_window: int,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row in selected.itertuples(index=False):
        combined: dict[tuple[str, int], tuple[float, float, float, int]] = {}
        target_keys: set[tuple[str, int]] = set()
        missing_targets: list[tuple[str, int]] = []
        for raw_file, target_indices in cell_targets[str(row.canonical_cell_id)].items():
            own_window = context_indices(target_indices, record_window)
            for index in own_window:
                if index in retained[raw_file]:
                    combined[(raw_file, index)] = retained[raw_file][index]
            for index in target_indices:
                key = (raw_file, index)
                target_keys.add(key)
                if key not in combined:
                    missing_targets.append(key)
        if missing_targets:
            raise ValueError(f"referenced target rows not found for {row.canonical_cell_id}: {missing_targets[:3]}")
        summary = summarize_raw_rows(combined, target_keys, float(row.lon), float(row.lat), radius_km)
        evidence_ceiling = "source_grid_order_only" if row.source_provider == "mrar" else "raw_record_order_only"
        records.append({
            "canonical_cell_id": row.canonical_cell_id,
            "sample_class": row.sample_class,
            "source_provider": row.source_provider,
            "raw_file_count": len(cell_targets[str(row.canonical_cell_id)]),
            "context_evidence_ceiling": evidence_ceiling,
            **summary,
        })
    return pd.DataFrame(records).sort_values(["sample_class", "canonical_cell_id"]).reset_index(drop=True)


def assign_interpretation_states(
    candidates: pd.DataFrame,
    raw_features: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    vocabulary = set(config["interpretation_state_vocabulary"])
    raw_cfg = config["raw_context"]
    agg_threshold = float(config["aggregation"]["material_between_contributor_nmad_m"])
    features = raw_features[raw_features["sample_class"].eq("candidate")].set_index("canonical_cell_id")
    states: list[str] = []
    for row in candidates.itertuples(index=False):
        feature = features.loc[row.canonical_cell_id]
        if bool(row.is_reference_conflict):
            state = "reference_version_conflict"
        elif (
            (math.isfinite(float(row.between_file_nmad_m)) and float(row.between_file_nmad_m) > agg_threshold)
            or (math.isfinite(float(row.between_cruise_nmad_m)) and float(row.between_cruise_nmad_m) > agg_threshold)
        ):
            state = "aggregation_conflict"
        elif (
            feature.context_status != "known"
            or int(feature.nearby_context_record_count) < int(raw_cfg["minimum_nearby_records"])
        ):
            state = "insufficient_raw_context"
        else:
            strong = bool(feature.raw_discontinuity_signal)
            if strong and row.source_provider == "mrar":
                state = "source_grid_discontinuity_candidate"
            elif strong:
                state = "raw_record_discontinuity_candidate"
            else:
                state = "terrain_or_source_ambiguous"
        validate_interpretation_state(state, vocabulary)
        states.append(state)
    out = candidates.copy()
    out["interpretation_state"] = states
    return out


def add_raw_discontinuity_signal(frame: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    cfg = config["raw_context"]
    out = frame.copy()
    scale = out["context_nmad_m"].clip(lower=1.0)
    out["raw_context_sufficient"] = (
        out["context_status"].eq("known")
        & out["nearby_context_record_count"].ge(int(cfg["minimum_nearby_records"]))
    )
    out["raw_discontinuity_signal"] = (
        out["raw_context_sufficient"]
        & out["target_minus_context_m"].abs().gt(float(cfg["discontinuity_absolute_threshold_m"]))
        & out["target_minus_context_m"].abs().gt(float(cfg["discontinuity_nmad_multiplier"]) * scale)
    )
    return out


def build_component_summary(candidates: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for component_id, group in candidates.groupby("component_id", sort=True):
        state_counts = group["interpretation_state"].value_counts().sort_index().to_dict()
        rows.append({
            "component_id": component_id,
            "source_provider": group["source_provider"].iloc[0],
            "difference_sign": int(group["difference_sign"].iloc[0]),
            "member_count": int(len(group)),
            "lon_index_min": int(group["lon_index"].min()),
            "lon_index_max": int(group["lon_index"].max()),
            "lat_index_min": int(group["lat_index"].min()),
            "lat_index_max": int(group["lat_index"].max()),
            "lon_min": float(group["lon"].min()),
            "lon_max": float(group["lon"].max()),
            "lat_min": float(group["lat"].min()),
            "lat_max": float(group["lat"].max()),
            "member_ids_json": json.dumps(sorted(group["canonical_cell_id"].tolist()), separators=(",", ":")),
            "state_counts_json": json.dumps(state_counts, sort_keys=True, separators=(",", ":")),
            "component_state": group["interpretation_state"].iloc[0] if len(state_counts) == 1 else "terrain_or_source_ambiguous",
        })
    return pd.DataFrame(rows)


def build_aggregation_census(lineage: pd.DataFrame, replay: pd.DataFrame, expected: dict[str, Any]) -> pd.DataFrame:
    replay_by_id = replay.set_index("canonical_cell_id")
    rows: list[dict[str, Any]] = []
    for row in lineage.itertuples(index=False):
        records = json.loads(row.contributor_records_json)
        raw_files = {record["raw_file"] for record in records}
        if len(raw_files) <= 1:
            continue
        alternatives = aggregation_alternatives(records)
        current = replay_by_id.loc[row.canonical_cell_id]
        rows.append({
            "canonical_cell_id": row.canonical_cell_id,
            "source_provider": row.source_provider,
            "current_frozen_depth_m": float(current.frozen_depth_m),
            "replayed_depth_m": float(current.replayed_depth_m),
            "replay_signed_difference_m": float(current.signed_diff_m),
            "replay_result": current.replay_result,
            **alternatives,
            "weighted_mean_minus_current_m": alternatives["point_count_weighted_mean_m"] - float(current.frozen_depth_m),
            "weighted_median_minus_current_m": alternatives["point_count_weighted_median_m"] - float(current.frozen_depth_m),
            "dominant_minus_current_m": alternatives["dominant_contributor_median_m"] - float(current.frozen_depth_m),
        })
    out = pd.DataFrame(rows).sort_values("canonical_cell_id").reset_index(drop=True)
    if len(out) != int(expected["multi_file_count"]):
        raise ValueError(f"multi-file census closure failed: {len(out)}")
    if int((out["contributor_cruise_count"] > 1).sum()) != int(expected["multi_cruise_count"]):
        raise ValueError("multi-cruise census closure failed")
    return out


def build_metadata_feasibility(
    lineage: pd.DataFrame,
    identity: pd.DataFrame,
    vertical: pd.DataFrame,
    factual_vocabulary: set[str],
) -> pd.DataFrame:
    identity_by_cruise = identity.set_index("cruise_id_candidate")
    cruise_lineage: dict[str, list[pd.Series]] = defaultdict(list)
    for _, row in lineage[lineage["source_provider"].eq("jamstec")].iterrows():
        for cruise in json.loads(row["official_cruise_ids_json"]):
            cruise_lineage[str(cruise)].append(row)
    rows: list[dict[str, Any]] = []
    for vertical_row in vertical.itertuples(index=False):
        source = str(vertical_row.source_cruise)
        provider = str(vertical_row.source_provider)
        if source in identity_by_cruise.index:
            identity_row = identity_by_cruise.loc[source]
            identity_state = str(identity_row["identity_state"])
            identity_status = str(identity_row["identity_state_status"])
        elif provider == "mrar":
            identity_state = "unknown"
            identity_status = "not_recoverable"
        else:
            identity_state = "official_cruise_id_from_lineage"
            identity_status = "verified_from_source_metadata"
        represented = cruise_lineage.get(source, [])
        line_statuses = {str(row["official_lines_json_status"]) for row in represented}
        time_statuses = {str(row["official_time_ranges_json_status"]) for row in represented}
        sonar_statuses = {str(row["sonar_types_json_status"]) for row in represented}
        line_status = next(iter(line_statuses)) if len(line_statuses) == 1 else "not_recoverable"
        time_status = next(iter(time_statuses)) if len(time_statuses) == 1 else "not_recoverable"
        sonar_status = next(iter(sonar_statuses)) if len(sonar_statuses) == 1 else "not_recoverable"
        if not represented:
            line_status = time_status = sonar_status = "not_recoverable"
        for status in (
            identity_status, str(vertical_row.vertical_datum_status),
            str(vertical_row.sounding_reduction_status), str(vertical_row.tide_correction_status),
            str(vertical_row.horizontal_geodetic_system_status), line_status, time_status, sonar_status,
        ):
            if status not in factual_vocabulary:
                raise ValueError(f"metadata status outside five-level vocabulary: {status}")
        reasons = []
        if str(vertical_row.vertical_datum_status) not in {"known", "verified_from_source_metadata"}:
            reasons.append("common_vertical_reference_not_established")
        if line_status not in {"known", "verified_from_source_metadata"}:
            reasons.append("line_identity_not_established")
        reasons.append("row_time_not_established")
        reasons.append("beam_or_raw_sonar_observations_not_available_in_current_inputs")
        rows.append({
            "source_cruise": source,
            "source_cruise_status": str(vertical_row.source_cruise_status),
            "source_provider": provider,
            "source_provider_status": str(vertical_row.source_provider_status),
            "identity_state": identity_state,
            "identity_state_status": identity_status,
            "line_identity": "unknown" if line_status != "not_recoverable" else "not_recoverable",
            "line_identity_status": line_status,
            "official_cruise_time_range": "recorded_in_lineage" if time_status in {"known", "verified_from_source_metadata"} else "unknown",
            "official_cruise_time_range_status": time_status,
            "row_time_identity": "not_recoverable",
            "row_time_identity_status": "not_recoverable",
            "official_sonar_type": "recorded_in_lineage" if sonar_status in {"known", "verified_from_source_metadata"} else "unknown",
            "official_sonar_type_status": sonar_status,
            "row_sonar_identity": "not_recoverable",
            "row_sonar_identity_status": "not_recoverable",
            "vertical_datum": str(vertical_row.vertical_datum),
            "vertical_datum_status": str(vertical_row.vertical_datum_status),
            "sounding_reduction": str(vertical_row.sounding_reduction),
            "sounding_reduction_status": str(vertical_row.sounding_reduction_status),
            "tide_correction": str(vertical_row.tide_correction),
            "tide_correction_status": str(vertical_row.tide_correction_status),
            "horizontal_geodetic_system": str(vertical_row.horizontal_geodetic_system),
            "horizontal_geodetic_system_status": str(vertical_row.horizontal_geodetic_system_status),
            "processed_xyz_availability": "available",
            "processed_xyz_availability_status": "known",
            "beam_identity": "not_recoverable",
            "beam_identity_status": "not_recoverable",
            "raw_sonar_observation_availability": "unknown",
            "raw_sonar_observation_availability_status": "officially_unknown",
            "crossover_feasibility": "not_feasible_from_current_inputs",
            "crossover_feasibility_status": "known",
            "crossover_blockers_json": json.dumps(sorted(set(reasons)), separators=(",", ":")),
        })
    return pd.DataFrame(rows).sort_values("source_cruise").reset_index(drop=True)


def candidate_output(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "canonical_cell_id", "lat", "lon", "lon_index", "lat_index", "source_provider",
        "ship_depth_m_positive_down", "raw_point_count", "raw_file_count", "official_cruise_count",
        "gebco_2024_minus_ship_m", "family_consensus_minus_ship_m", "family_consensus_nmad_m",
        "family_consensus_range_m", "difference_sign", "is_reference_conflict",
        "between_file_nmad_m", "between_cruise_nmad_m", "raw_replay_signed_diff_m",
        "raw_replay_result", "primary_raw_file", "depth_band", "point_count_band",
        "component_id", "component_member_count", "interpretation_state",
    ]
    return frame[columns].sort_values("canonical_cell_id").reset_index(drop=True)


def control_output(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "canonical_cell_id", "lat", "lon", "lon_index", "lat_index", "source_provider",
        "ship_depth_m_positive_down", "raw_point_count", "raw_file_count", "official_cruise_count",
        "gebco_2024_minus_ship_m", "family_consensus_minus_ship_m", "primary_raw_file",
        "depth_band", "point_count_band", "control_stratum", "control_match_level",
        "matched_candidate_id", "control_seed", "selection_order",
    ]
    return frame[columns].sort_values("canonical_cell_id").reset_index(drop=True)


def reference_output(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "canonical_cell_id", "source_provider", "ship_depth_m_positive_down",
        "gebco_2024_minus_ship_m", "family_consensus_minus_ship_m", "family_consensus_nmad_m",
        "family_consensus_range_m", "primary_raw_file",
    ]
    return frame[columns].sort_values("canonical_cell_id").reset_index(drop=True)


def make_summary(
    candidates: pd.DataFrame,
    components: pd.DataFrame,
    controls: pd.DataFrame,
    raw_features: pd.DataFrame,
    aggregation: pd.DataFrame,
    reference: pd.DataFrame,
    metadata: pd.DataFrame,
    raw_hashes: dict[str, str],
) -> dict[str, Any]:
    candidate_features = raw_features[raw_features["sample_class"].eq("candidate")]
    control_features = raw_features[raw_features["sample_class"].eq("control")]
    strongest = candidates.merge(
        candidate_features[[
            "canonical_cell_id", "source_provider", "raw_discontinuity_signal",
            "target_minus_context_m", "nearby_context_record_count",
        ]],
        on=["canonical_cell_id", "source_provider"],
        validate="one_to_one",
    )
    strongest = strongest[strongest["raw_discontinuity_signal"]].copy()
    strongest["_magnitude"] = strongest["target_minus_context_m"].abs()
    strongest = strongest.nlargest(10, "_magnitude")[[
        "canonical_cell_id", "source_provider", "lon", "lat",
        "gebco_2024_minus_ship_m", "target_minus_context_m",
        "nearby_context_record_count", "interpretation_state",
    ]]
    largest_components = components.nlargest(10, "member_count")[[
        "component_id", "source_provider", "member_count", "difference_sign",
        "lon_min", "lon_max", "lat_min", "lat_max", "component_state",
    ]]
    return {
        "status": "complete",
        "scientific_use": "diagnostic_pre_correction_only",
        "candidate_count": int(len(candidates)),
        "candidate_provider_counts": candidates["source_provider"].value_counts().sort_index().to_dict(),
        "candidate_state_counts": candidates["interpretation_state"].value_counts().sort_index().to_dict(),
        "component_count": int(len(components)),
        "control_count": int(len(controls)),
        "raw_context_sufficient_candidate_count": int(
            candidate_features["raw_context_sufficient"].sum()
        ),
        "raw_signal_candidate_provider_counts": (
            candidate_features[candidate_features["raw_discontinuity_signal"]]
            ["source_provider"].value_counts().sort_index().to_dict()
        ),
        "raw_signal_control_provider_counts": (
            control_features[control_features["raw_discontinuity_signal"]]
            ["source_provider"].value_counts().sort_index().to_dict()
        ),
        "strongest_raw_signal_locations": json.loads(strongest.to_json(orient="records")),
        "largest_candidate_components": json.loads(largest_components.to_json(orient="records")),
        "aggregation_census_count": int(len(aggregation)),
        "multi_cruise_census_count": int((aggregation["contributor_cruise_count"] > 1).sum()),
        "reference_conflict_count": int(len(reference)),
        "metadata_row_count": int(len(metadata)),
        "crossover_feasible_count": int(metadata["crossover_feasibility"].eq("feasible").sum()),
        "referenced_raw_file_count": int(len(raw_hashes)),
        "referenced_raw_file_sha256": raw_hashes,
        "guardrails": [
            "No depth or upstream QC value was changed.",
            "No candidate state authorizes deletion or numerical correction.",
            "Product differences only defined diagnostic candidate/reference sets.",
            "No downstream model error was read.",
        ],
    }


def render_markdown_table(frame: pd.DataFrame) -> str:
    columns = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in frame.itertuples(index=False, name=None):
        values = []
        for value in row:
            if isinstance(value, (float, np.floating)):
                values.append(f"{float(value):.6g}")
            else:
                values.append(str(value).replace("|", "\\|"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def render_decision_pack(summary: dict[str, Any], aggregation: pd.DataFrame) -> str:
    states = summary["candidate_state_counts"]
    largest_agg = aggregation.nlargest(10, "contributor_range_m")[[
        "canonical_cell_id", "contributor_range_m", "largest_to_smallest_point_count_ratio",
        "weighted_median_minus_current_m",
    ]]
    lines = [
        "# SCS 船测 QC v2 协作者决策包",
        "",
        "## 已由仓库证据支持的事实",
        "",
        f"- 诊断候选共 {summary['candidate_count']:,} 个，组件 {summary['component_count']:,} 个；候选状态计数：`{json.dumps(states, ensure_ascii=False, sort_keys=True)}`。",
        f"- 同分层对照共 {summary['control_count']:,} 个；5 km 内至少有 3 条上下文记录的候选 {summary['raw_context_sufficient_candidate_count']:,} 个。",
        f"- raw-only 不连续信号：候选 `{json.dumps(summary['raw_signal_candidate_provider_counts'], ensure_ascii=False, sort_keys=True)}`；同文件分层对照 `{json.dumps(summary['raw_signal_control_provider_counts'], ensure_ascii=False, sort_keys=True)}`。这是线索，不是无效判决。",
        f"- 多文件聚合审计覆盖 {summary['aggregation_census_count']:,} 个 cell，其中多航次 {summary['multi_cruise_census_count']:,} 个。",
        f"- 参考版本冲突 {summary['reference_conflict_count']:,} 个；它们不能用于标定船测删除阈值。",
        f"- 当前元数据下可实施交叉点平差的来源数为 {summary['crossover_feasible_count']}；垂直基准、逐行时间/测线或原始声呐观测缺口仍在。",
        "- 本产物没有改深度、删航线、改 QC 标志、改数据用途或读取下游模型误差。",
        "",
        "## 需要协作者决定（当前均为 pending）",
        "",
        "1. **1 分钟标签目标**：建议 v2 明确为“经质量控制后的观测分布统计量”，同时保留点数、离散度和来源结构；不要把 GEBCO 当替代真值。需要确认选用原始点加权中位数、航次平衡中位数，还是分层估计器。",
        "2. **异常状态语义**：建议把 `ambiguous`/`unresolved` 与已证实无效分开。只有可复现的原始记录错误或元数据矛盾才能进入无效候选，产品分歧本身不能触发删除。",
        "3. **MRAR 用途**：建议在身份、测线和垂直基准不可恢复时保持 train-only/敏感性分析，不作为独立验证；是否局部保留需结合本次组件和对照分布决定。",
        "4. **聚合方法**：建议先对比原始点加权中位数、航次平衡中位数与主贡献者统计，禁止直接把点数加权均值认定为正确答案。需要确认未来标签及不确定性列。",
        "5. **交叉点平差**：建议只有在逐行时间、测线身份、共同垂直基准和可重建交叉点同时具备时实施。当前处理 XYZ 不满足，是否回取原始声呐/导航数据需协作者决定。",
        "6. **v1/v2 迁移**：建议 v1 冻结，v2 新版本并重建数据用途与空间分组；不得原地覆盖。需要确认是否重新生成所有依赖 v1 的划分。",
        "",
        "## 最大聚合分歧示例（仅诊断）",
        "",
        render_markdown_table(largest_agg),
        "",
        "## 最强 raw-only 不连续位置线索（仅诊断）",
        "",
        render_markdown_table(pd.DataFrame(summary["strongest_raw_signal_locations"])),
        "",
        "## 最大候选空间组件（仅诊断）",
        "",
        render_markdown_table(pd.DataFrame(summary["largest_candidate_components"])),
        "",
        "在上述六项决定签字前，不开始数值修正或航线剔除。",
        "",
    ]
    return "\n".join(lines)


def render_report(summary: dict[str, Any], config_path: Path) -> str:
    return "\n".join([
        "# SCS ship sounding QC v2 pre-correction audit",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Config: `{config_path.relative_to(REPO_ROOT)}`",
        f"Supersedes: `{summary.get('supersedes_run_id', 'none')}`",
        "",
        "This immutable package is diagnostic evidence only. It does not identify GEBCO as truth,",
        "does not turn disagreement into deletion, and does not implement correction.",
        "",
        "## Closure",
        "",
        f"- candidates: {summary['candidate_count']:,}",
        f"- components: {summary['component_count']:,}",
        f"- controls: {summary['control_count']:,}",
        f"- reference-version conflicts: {summary['reference_conflict_count']:,}",
        f"- multi-file aggregation cells: {summary['aggregation_census_count']:,}",
        f"- metadata rows: {summary['metadata_row_count']:,}",
        f"- crossover feasible from current inputs: {summary['crossover_feasible_count']:,}",
        "",
        "## Evidence ceilings",
        "",
        "JAMSTEC three-column neighbours are raw-record-order context only. MRAR neighbours",
        "are source-grid-order context only. Neither is promoted to verified line, ping, swath,",
        "beam, or crossover evidence. The 52 historical replay differences remain aggregation",
        "approximation evidence, not bad-ping evidence.",
        "",
    ])


def atomic_write_parquet(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    os.replace(temporary, path)


def atomic_write_text(text: str, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def write_json(value: Any, path: Path) -> None:
    atomic_write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", path)


def write_outputs(
    run_dir: Path,
    frames: dict[str, pd.DataFrame],
    summary: dict[str, Any],
    config: dict[str, Any],
    config_path: Path,
    input_paths: dict[str, Path],
) -> None:
    forbidden = list(config["output_guards"]["forbidden_column_tokens"])
    forbidden_paths = list(config["output_guards"]["forbidden_output_path_tokens"])
    for name, frame in frames.items():
        validate_output_schema(frame, forbidden)
        validate_output_path(Path(name), forbidden_paths)
        if name.endswith(".csv"):
            temporary = run_dir / (name + ".tmp")
            frame.to_csv(temporary, index=False)
            os.replace(temporary, run_dir / name)
        else:
            atomic_write_parquet(frame, run_dir / name)
    for name in ("preflight_summary.json", "collaborator_decision_pack.md", "audit_report.md", "audit_manifest.json"):
        validate_output_path(Path(name), forbidden_paths)
    write_json(summary, run_dir / "preflight_summary.json")
    atomic_write_text(render_decision_pack(summary, frames["aggregation_conflicts.parquet"]), run_dir / "collaborator_decision_pack.md")
    atomic_write_text(render_report(summary, config_path), run_dir / "audit_report.md")
    inventory = []
    for path in sorted(run_dir.iterdir()):
        if path.name == "audit_manifest.json":
            continue
        inventory.append({"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    manifest = {
        "schema_version": 1,
        "run_id": run_dir.name[1:].split(".tmp-", 1)[0] if run_dir.name.startswith(".") else run_dir.name,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config_path.relative_to(REPO_ROOT)),
        "config_sha256": sha256_file(config_path),
        "input_sha256": {
            key: {"path": str(path.relative_to(REPO_ROOT)), "sha256": sha256_file(path)}
            for key, path in sorted(input_paths.items())
        },
        "software": {
            "producer": {
                "path": str(Path(__file__).resolve().relative_to(REPO_ROOT)),
                "sha256": sha256_file(Path(__file__).resolve()),
            },
            "verifier": {
                "path": "ncei/code/scs_confirmation/verify_scs_ship_qc_v2_preflight.py",
                "sha256": sha256_file(REPO_ROOT / "ncei/code/scs_confirmation/verify_scs_ship_qc_v2_preflight.py"),
            },
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        "outputs": inventory,
        "scientific_use": "diagnostic_pre_correction_only",
    }
    write_json(manifest, run_dir / "audit_manifest.json")


def prepare_analysis(config: dict[str, Any]) -> dict[str, Any]:
    paths = validate_frozen_inputs(config)
    product, lineage, replay, identity, vertical = load_inputs(paths)
    validate_input_closure(product, lineage, replay, identity, vertical, config["expected"])
    candidates, controls, reference = build_registry(product, lineage, config)
    candidate_components = assign_components(candidates)
    selected = pd.concat([
        candidate_components.assign(sample_class="candidate"),
        controls.assign(sample_class="control"),
    ], ignore_index=True, sort=False)
    file_requests, cell_targets, raw_hashes, providers = build_raw_requests(
        selected, int(config["raw_context"]["record_window"])
    )
    return {
        "paths": paths,
        "product": product,
        "lineage": lineage,
        "replay": replay,
        "identity": identity,
        "vertical": vertical,
        "candidates": candidate_components,
        "controls": controls,
        "reference": reference,
        "selected": selected,
        "file_requests": file_requests,
        "cell_targets": cell_targets,
        "raw_hashes": raw_hashes,
        "providers": providers,
    }


def run_full(config: dict[str, Any], config_path: Path, run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run ID must use UTC YYYYMMDDTHHMMSSZ format")
    analysis = prepare_analysis(config)
    output_root = resolve_repo_path(config["output_root"])
    final_dir = output_root / run_id
    temp_dir = output_root / f".{run_id}.tmp-{os.getpid()}"
    if final_dir.exists() or temp_dir.exists():
        raise FileExistsError(f"immutable run path already exists: {final_dir}")
    validate_output_path(final_dir.relative_to(REPO_ROOT), config["output_guards"]["forbidden_output_path_tokens"])
    output_root.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir()
    try:
        retained, actual_raw_hashes = stream_raw_requests(
            analysis["file_requests"], analysis["raw_hashes"], analysis["providers"]
        )
        raw_features = build_raw_context_features(
            analysis["selected"], analysis["cell_targets"], retained,
            float(config["raw_context"]["nearby_radius_km"]),
            int(config["raw_context"]["record_window"]),
        )
        raw_features = add_raw_discontinuity_signal(raw_features, config)
        candidates = assign_interpretation_states(analysis["candidates"], raw_features, config)
        components = build_component_summary(candidates)
        aggregation = build_aggregation_census(analysis["lineage"], analysis["replay"], config["expected"])
        metadata = build_metadata_feasibility(
            analysis["lineage"], analysis["identity"], analysis["vertical"],
            set(config["factual_status_vocabulary"]),
        )
        frames = {
            "candidate_cells.parquet": candidate_output(candidates),
            "candidate_components.parquet": components,
            "raw_context_features.parquet": raw_features,
            "control_cells.parquet": control_output(analysis["controls"]),
            "aggregation_conflicts.parquet": aggregation,
            "reference_conflicts.parquet": reference_output(analysis["reference"]),
            "metadata_feasibility.csv": metadata,
        }
        summary = make_summary(
            candidates, components, analysis["controls"], raw_features, aggregation,
            analysis["reference"], metadata, actual_raw_hashes,
        )
        summary["supersedes_run_id"] = config.get("supersedes_run_id")
        write_outputs(temp_dir, frames, summary, config, config_path, analysis["paths"])
        os.replace(temp_dir, final_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    return final_dir


def estimate(config: dict[str, Any]) -> dict[str, Any]:
    analysis = prepare_analysis(config)
    raw_hashes = verify_raw_hashes(analysis["raw_hashes"])
    return {
        "status": "estimate_only",
        "candidate_count": int(len(analysis["candidates"])),
        "control_count": int(len(analysis["controls"])),
        "referenced_raw_file_count": int(len(raw_hashes)),
        "requested_raw_record_count": int(sum(len(rows) for rows in analysis["file_requests"].values())),
        "raw_file_sha256": raw_hashes,
        "output_created": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--estimate-only", action="store_true")
    parser.add_argument("--confirm-audit", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if Path.cwd().resolve() != REPO_ROOT:
        raise SystemExit(f"ERROR: run from repository root: {REPO_ROOT}")
    config_path = resolve_repo_path(args.config).resolve()
    config = load_config(config_path)
    if args.estimate_only:
        if args.run_id or args.confirm_audit:
            raise SystemExit("ERROR: --estimate-only cannot be combined with --run-id/--confirm-audit")
        print(json.dumps(estimate(config), indent=2, sort_keys=True))
        return
    if not args.confirm_audit or not args.run_id:
        raise SystemExit("ERROR: full execution requires --run-id and --confirm-audit")
    run_dir = run_full(config, config_path, args.run_id)
    print(f"Audit run: {run_dir.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
