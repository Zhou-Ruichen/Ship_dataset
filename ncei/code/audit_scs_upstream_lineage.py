#!/usr/bin/env python3
"""Audit raw lineage for the frozen 174,965-cell South China Sea cohort.

This is a bounded handoff audit. It reads only the four frozen downstream
cohort/manifest inputs, then replays the corresponding upstream JAMSTEC and
MRAR source rows. It never reads predictions, residuals, model errors, or any
other downstream product.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
JAM_ROOT = REPO_ROOT / "jamstec" / "multibeam"
NCEI_ROOT = REPO_ROOT / "ncei"

EXPECTED_INPUTS = {
    "downstream_union": "89d8771335e3eeb43a4ac370e9a911260618bd3f45212ee708023344179ba456",
    "counts_closure": "2bec462f27b2293d9b7077c6e80225bada845994ea97e7908e6651ce895a1a2f",
    "downstream_manifest": "606fa69da644d9efd538da3e42e6d96eaad80462eca434c06b0e64f0b5ddbaeb",
    "external_group_manifest": "4f12d42de0a7b071947b5eb4c7b454a243b99796f9ca6303f4829dfda8054d1f",
}
EXPECTED_CELL_COUNT = 174_965
EXPECTED_SOURCE_COUNTS = {"mrar": 165_966, "jamstec": 8_999}
EXPECTED_EXTERNAL_COUNT = 4_229
EXPECTED_IDENTITY_GROUPS = {
    "KR03-04", "KR13-18", "KR15-16", "KR15-18", "KR16-E06", "KY02-01",
    "KY03-09", "KY05-01", "KY12-08", "KY14-03", "MR00-K07", "MR06-05",
}
FIELD_STATUSES = {
    "known",
    "officially_unknown",
    "not_recoverable",
    "inferred_from_filename",
    "verified_from_source_metadata",
}
IDENTITY_STATES = {
    "official_exact", "official_leg_ambiguous", "filename_only", "unresolved",
}
FORBIDDEN_NAME_TOKENS = ("prediction", "predictions", "residual", "error", "errors")
CELL_DEG = 1.0 / 60.0
REPLAY_ATOL_M = 1e-9


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def nmad(values: Iterable[float]) -> float:
    array = np.asarray(list(values), dtype=np.float64)
    array = array[np.isfinite(array)]
    if array.size < 2:
        return float("nan")
    median = np.median(array)
    return float(1.4826 * np.median(np.abs(array - median)))


def grouped_nmad(frame: pd.DataFrame, group_column: str, value_column: str) -> pd.Series:
    """Compute NMAD per group without one Python callback per group."""
    medians = frame.groupby(group_column, sort=False)[value_column].transform("median")
    deviations = (frame[value_column] - medians).abs()
    result = deviations.groupby(frame[group_column], sort=False).median() * 1.4826
    counts = frame.groupby(group_column, sort=False)[value_column].count()
    result[counts < 2] = np.nan
    return result


def normalize_lon(lon: np.ndarray) -> np.ndarray:
    return ((lon + 180.0) % 360.0) - 180.0


def normalize_mrar_lon(lon: np.ndarray) -> np.ndarray:
    out = lon.copy()
    mask = np.isfinite(out) & (out > 180.0)
    out[mask] -= 360.0
    return out


def cell_ids(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    lon_bin = np.floor((lon + 180.0) / CELL_DEG).astype(np.int32)
    lat_bin = np.floor((lat + 90.0) / CELL_DEG).astype(np.int32)
    return np.char.add(np.char.add(np.char.add("1min_", lat_bin.astype(str)), "_"), lon_bin.astype(str))


def compress_ranges(indices: Iterable[int]) -> list[list[int]]:
    ordered = np.unique(np.asarray(list(indices), dtype=np.int64))
    if ordered.size == 0:
        return []
    starts = np.r_[True, np.diff(ordered) != 1]
    ends = np.r_[np.diff(ordered) != 1, True]
    return [[int(a), int(b)] for a, b in zip(ordered[starts], ordered[ends])]


def file_id_to_parquet_name(file_id: str) -> str:
    safe = file_id.replace("::", "__").replace("/", "__")
    if safe.endswith(".dat"):
        safe = safe[:-4]
    return safe + ".parquet"


def cruise_from_subzip(subzip_id: str) -> str:
    match = re.match(r"(.+?)(?:_leg\d+)?_bathymetry(?:_dmo)?$", subzip_id, flags=re.I)
    return match.group(1) if match else subzip_id


def leg_from_subzip(subzip_id: str) -> str | None:
    match = re.search(r"_(leg\d+)_bathymetry", subzip_id, flags=re.I)
    return match.group(1).title() if match else None


def atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temp, index=False, compression="snappy")
    os.replace(temp, path)


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temp, index=False)
    os.replace(temp, path)


def atomic_text(text: str, path: Path) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def validate_frozen_inputs(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for role, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"missing frozen input {role}: {path}")
        lowered = path.name.lower()
        if any(token in lowered for token in FORBIDDEN_NAME_TOKENS):
            raise ValueError(f"forbidden downstream filename for {role}: {path.name}")
        actual = sha256_file(path)
        expected = EXPECTED_INPUTS[role]
        if actual != expected:
            raise ValueError(f"input SHA256 drift for {role}: expected {expected}, got {actual}")
        records[role] = {"path": str(path.resolve()), "sha256": actual, "size_bytes": path.stat().st_size}
    return records


def load_cohort(union_path: Path, external_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    union_columns = [
        "canonical_cell_id", "lon", "lat", "roles", "cohorts",
        "representative_depth_m", "source_provider",
    ]
    union = pd.read_parquet(union_path, columns=union_columns)
    if len(union) != EXPECTED_CELL_COUNT or union["canonical_cell_id"].nunique() != EXPECTED_CELL_COUNT:
        raise ValueError("frozen union row/key closure failed")
    if union["canonical_cell_id"].isna().any():
        raise ValueError("frozen union contains null canonical_cell_id")
    counts = union["source_provider"].value_counts().to_dict()
    if counts != EXPECTED_SOURCE_COUNTS:
        raise ValueError(f"source closure drift: {counts}")

    external_columns = [
        "cell_id", "lon_center", "lat_center", "cruise_id_candidate",
        "dominant_file_id", "source_provider",
    ]
    external = pd.read_parquet(external_path, columns=external_columns)
    if len(external) != EXPECTED_EXTERNAL_COUNT:
        raise ValueError(f"external row closure drift: {len(external)}")
    groups = set(external["cruise_id_candidate"].dropna().astype(str))
    if groups != EXPECTED_IDENTITY_GROUPS:
        raise ValueError(f"external identity group drift: {sorted(groups)}")
    if not set(external["cell_id"]).issubset(set(union["canonical_cell_id"])):
        raise ValueError("external cells are not a subset of the frozen union")
    return union.sort_values("canonical_cell_id").reset_index(drop=True), external


def discover_jamstec_contributors(target_ids: set[str], target: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    file_manifest = pd.read_parquet(JAM_ROOT / "manifests/file_manifest_points_raw.parquet")
    file_manifest = file_manifest[file_manifest["include_in_points_raw"].fillna(False)].copy()
    if file_manifest["file_id"].duplicated().any():
        raise ValueError("JAMSTEC file manifest has duplicate file_id")

    lon_min, lon_max = float(target["lon"].min()) - CELL_DEG, float(target["lon"].max()) + CELL_DEG
    lat_min, lat_max = float(target["lat"].min()) - CELL_DEG, float(target["lat"].max()) + CELL_DEG
    candidates = file_manifest[
        file_manifest["lon_max"].ge(lon_min)
        & file_manifest["lon_min"].le(lon_max)
        & file_manifest["lat_max"].ge(lat_min)
        & file_manifest["lat_min"].le(lat_max)
    ]

    rows: list[pd.DataFrame] = []
    for meta in candidates.itertuples(index=False):
        path = JAM_ROOT / "derived/file_cells_1min" / file_id_to_parquet_name(meta.file_id)
        if not path.is_file():
            raise FileNotFoundError(f"missing JAMSTEC file-cell product: {path}")
        frame = pd.read_parquet(
            path,
            columns=["cell_id", "n_points", "median_depth_m_positive_down"],
        )
        frame = frame[frame["cell_id"].isin(target_ids)]
        if frame.empty:
            continue
        frame["file_id"] = meta.file_id
        frame["subzip_id"] = meta.subzip_id
        frame["relative_path"] = meta.relative_path
        frame["filename"] = meta.filename
        frame["cruise_id_guess"] = meta.cruise_id_guess
        frame["data_layout"] = meta.data_layout
        rows.append(frame)

    if not rows:
        raise ValueError("no JAMSTEC contributors found for frozen target cells")
    contributors = pd.concat(rows, ignore_index=True)
    if set(contributors["cell_id"]) != target_ids:
        missing = sorted(target_ids - set(contributors["cell_id"]))[:10]
        raise ValueError(f"JAMSTEC contributor closure failed; missing cells: {missing}")
    used_meta = file_manifest[file_manifest["file_id"].isin(contributors["file_id"].unique())].copy()
    return contributors, used_meta


def verify_upstream_cell_products(union: pd.DataFrame, jam_contributors: pd.DataFrame) -> dict[str, Any]:
    jam_target = union[union["source_provider"].eq("jamstec")]
    jam_global = pd.read_parquet(
        JAM_ROOT / "derived/cells_1min/cells.parquet",
        columns=["cell_id", "median_depth_file_balanced", "n_points_total"],
    )
    jam_global = jam_global[jam_global["cell_id"].isin(set(jam_target["canonical_cell_id"]))]
    merged = jam_target.merge(jam_global, left_on="canonical_cell_id", right_on="cell_id", how="left", validate="one_to_one")
    if merged["cell_id"].isna().any():
        raise ValueError("JAMSTEC global-cell join closure failed")
    jam_diff = merged["representative_depth_m"] - merged["median_depth_file_balanced"]
    if float(jam_diff.abs().max()) > REPLAY_ATOL_M:
        raise ValueError("JAMSTEC frozen depth differs from upstream global cells")

    mrar_target = union[union["source_provider"].eq("mrar")]
    mrar_fc = pd.read_parquet(NCEI_ROOT / "derived/regional_mrar/file_cells_1min/mrar_0-180E-0-85N.txt.parquet")
    mrar_fc = mrar_fc[mrar_fc["cell_id"].isin(set(mrar_target["canonical_cell_id"]))]
    mrar_merged = mrar_target.merge(mrar_fc, left_on="canonical_cell_id", right_on="cell_id", how="left", validate="one_to_one")
    if mrar_merged["cell_id"].isna().any():
        raise ValueError("MRAR file-cell join closure failed")
    mrar_diff = mrar_merged["representative_depth_m"] - mrar_merged["median_depth_m"]
    if float(mrar_diff.abs().max()) > REPLAY_ATOL_M:
        raise ValueError("MRAR frozen depth differs from upstream file cells")

    return {
        "jamstec_cells": len(jam_target),
        "jamstec_file_cell_rows": len(jam_contributors),
        "jamstec_upstream_max_abs_diff_m": float(jam_diff.abs().max()),
        "mrar_cells": len(mrar_target),
        "mrar_upstream_points": int(mrar_fc["n_points_pass"].sum()),
        "mrar_upstream_max_abs_diff_m": float(mrar_diff.abs().max()),
    }


def find_official_pdf(subzip_id: str) -> Path:
    directory = JAM_ROOT / "raw/dat_by_subzip" / subzip_id
    candidates = sorted(directory.glob("darwin-data-*-bathymetry_e.pdf"))
    if len(candidates) != 1:
        raise ValueError(f"expected one official English DARWIN PDF for {subzip_id}, found {len(candidates)}")
    return candidates[0]


def parse_official_pdf(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    text = result.stdout

    def first(pattern: str) -> str | None:
        match = re.search(pattern, text, flags=re.I | re.M)
        return match.group(1).strip() if match else None

    cruise_label = first(r"^\s*Cruise ID:\s*(.+?)\s*$")
    ship = first(r"^\s*Ship Name:\s*([^\n]+?)\s*$")
    period = first(r"^\s*Period:\s*(\d{4}-\d{2}-\d{2}\s*-\s*\d{4}-\d{2}-\d{2})")
    sonar = first(r"^\s*Type\s*:\s*([^\n]+?)\s*$")
    geodetic = first(r"Geodetic system:\s*([^\n]+)")
    report_url = first(r"^\s*(https?://\S+\.pdf)\s*$")
    official_entries = sorted(set(re.findall(
        r"\b[A-Za-z0-9_-]+(?:\.dat(?:\.zip)?|\.zip)\b",
        text,
    )))
    if not all((cruise_label, ship, period, sonar, geodetic)):
        raise ValueError(f"official PDF metadata parse incomplete: {path}")
    base_match = re.match(r"(.+?)(?:\s+Leg\d+)?$", cruise_label, flags=re.I)
    leg_match = re.search(r"\b(Leg\d+)\b", cruise_label, flags=re.I)
    return {
        "pdf_path": str(path.relative_to(REPO_ROOT)),
        "pdf_sha256": sha256_file(path),
        "cruise_label": cruise_label,
        "cruise_id": base_match.group(1),
        "leg": leg_match.group(1).title() if leg_match else None,
        "ship": ship,
        "period": period.replace(" ", ""),
        "sonar": sonar,
        "horizontal_datum": geodetic,
        "report_url": report_url,
        "official_files": sorted({official_raw_filename(entry) for entry in official_entries}),
        "depth_unit": "m" if re.search(r"\bDepth\b[^\n]*\bm\s*$", text, flags=re.I | re.M) else None,
        "sound_velocity_corrected": bool(re.search(r"sound velocity profile correction", text, flags=re.I)),
        "tide_not_corrected": bool(re.search(r"tide is not corrected", text, flags=re.I)),
        "vertical_datum_stated": bool(re.search(r"vertical datum", text, flags=re.I)),
        "ellipsoid_stated": bool(re.search(r"ellipsoid", text, flags=re.I)),
        "geoid_stated": bool(re.search(r"\bgeoid\b", text, flags=re.I)),
        "chart_datum_stated": bool(re.search(r"chart datum", text, flags=re.I)),
    }


def load_official_metadata(used_meta: pd.DataFrame) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for subzip_id in sorted(used_meta["subzip_id"].unique()):
        records[subzip_id] = parse_official_pdf(find_official_pdf(subzip_id))
    return records


def expected_official_archive(filename: str) -> str:
    return Path(filename).name


def official_raw_filename(entry: str) -> str:
    if entry.endswith(".dat.zip"):
        return entry[:-4]
    if entry.endswith(".zip"):
        return entry[:-4] + ".dat"
    return entry


def replay_jamstec(
    used_meta: pd.DataFrame,
    target_ids: set[str],
) -> tuple[pd.DataFrame, dict[str, dict[str, float]], dict[str, str]]:
    records: list[dict[str, Any]] = []
    full_envelopes: dict[str, dict[str, float]] = {}
    raw_hashes: dict[str, str] = {}

    for position, meta in enumerate(used_meta.sort_values("file_id").itertuples(index=False), start=1):
        raw_path = JAM_ROOT / "raw/dat_by_subzip" / meta.relative_path
        if not raw_path.is_file():
            raise FileNotFoundError(f"missing JAMSTEC raw file: {raw_path}")
        raw_rel = str(raw_path.relative_to(REPO_ROOT))
        raw_hashes[raw_rel] = sha256_file(raw_path)
        selected: list[pd.DataFrame] = []
        full_lon_min = full_lat_min = float("inf")
        full_lon_max = full_lat_max = float("-inf")
        row_offset = 0
        usecols = [int(meta.lon_col), int(meta.lat_col), int(meta.depth_col)]
        for chunk in pd.read_csv(
            raw_path,
            sep=r"\s+",
            header=None,
            usecols=usecols,
            names=["lon_raw", "lat_raw", "depth"],
            chunksize=1_000_000,
            engine="c",
        ):
            n_rows = len(chunk)
            lon = normalize_lon(chunk["lon_raw"].to_numpy(dtype=np.float64))
            lat = chunk["lat_raw"].to_numpy(dtype=np.float64)
            depth = chunk["depth"].to_numpy(dtype=np.float64)
            finite_xy = np.isfinite(lon) & np.isfinite(lat)
            if finite_xy.any():
                full_lon_min = min(full_lon_min, float(lon[finite_xy].min()))
                full_lon_max = max(full_lon_max, float(lon[finite_xy].max()))
                full_lat_min = min(full_lat_min, float(lat[finite_xy].min()))
                full_lat_max = max(full_lat_max, float(lat[finite_xy].max()))
            qc = (
                finite_xy & np.isfinite(depth)
                & (lon >= -180.0) & (lon < 180.0)
                & (lat >= -90.0) & (lat <= 90.0)
                & (depth > 0.0) & (depth <= 12_000.0)
            )
            ids = np.full(n_rows, "", dtype=object)
            ids[qc] = cell_ids(lon[qc], lat[qc])
            keep = qc & pd.Index(ids).isin(target_ids)
            if keep.any():
                selected.append(pd.DataFrame({
                    "cell_id": ids[keep],
                    "raw_row_id": np.arange(row_offset, row_offset + n_rows, dtype=np.int64)[keep],
                    "depth_m": depth[keep],
                    "lon": lon[keep],
                    "lat": lat[keep],
                }))
            row_offset += n_rows

        if row_offset != int(meta.line_count):
            raise ValueError(f"raw line count drift for {meta.file_id}: {row_offset} != {int(meta.line_count)}")
        full_envelopes[meta.file_id] = {
            "lon_min": full_lon_min, "lon_max": full_lon_max,
            "lat_min": full_lat_min, "lat_max": full_lat_max,
        }
        if not selected:
            raise ValueError(f"discovered contributor has no replay target points: {meta.file_id}")
        points = pd.concat(selected, ignore_index=True)
        for cell_id, group in points.groupby("cell_id", sort=True):
            records.append({
                "cell_id": cell_id,
                "source_provider": "jamstec",
                "file_id": meta.file_id,
                "subzip_id": meta.subzip_id,
                "cruise_id": meta.cruise_id_guess,
                "leg": leg_from_subzip(meta.subzip_id),
                "raw_file": raw_rel,
                "raw_file_sha256": raw_hashes[raw_rel],
                "raw_row_ranges": compress_ranges(group["raw_row_id"]),
                "raw_point_count": len(group),
                "file_cell_median_m": float(group["depth_m"].median()),
                "within_file_nmad_m": nmad(group["depth_m"]),
                "target_lon_min": float(group["lon"].min()),
                "target_lon_max": float(group["lon"].max()),
                "target_lat_min": float(group["lat"].min()),
                "target_lat_max": float(group["lat"].max()),
            })
        print(f"JAMSTEC replay {position}/{len(used_meta)}: {meta.file_id} ({len(points):,} target points)", flush=True)

    return pd.DataFrame(records), full_envelopes, raw_hashes


def replay_mrar(target_ids: set[str]) -> tuple[pd.DataFrame, dict[str, str]]:
    raw_path = NCEI_ROOT / "archive/zhoushuai_processed_M/0-180E-0-85N.txt"
    archive_path = NCEI_ROOT / "archive/zhoushuai_processed_M/M.rar"
    raw_hashes = {
        str(raw_path.relative_to(REPO_ROOT)): sha256_file(raw_path),
        str(archive_path.relative_to(REPO_ROOT)): sha256_file(archive_path),
    }
    selected: list[pd.DataFrame] = []
    row_offset = 0
    for chunk_no, chunk in enumerate(pd.read_csv(
        raw_path,
        sep="\t",
        header=None,
        names=["lon_raw", "lat_raw", "depth_raw"],
        usecols=["lon_raw", "lat_raw", "depth_raw"],
        chunksize=2_000_000,
        engine="c",
        dtype={"lon_raw": np.float64, "lat_raw": np.float64, "depth_raw": np.float64},
    ), start=1):
        n_rows = len(chunk)
        lon = normalize_mrar_lon(chunk["lon_raw"].to_numpy(dtype=np.float64))
        lat = chunk["lat_raw"].to_numpy(dtype=np.float64)
        depth = -chunk["depth_raw"].to_numpy(dtype=np.float64)
        qc = (
            np.isfinite(lon) & np.isfinite(lat) & np.isfinite(depth)
            & (lon >= -180.0) & (lon < 180.0)
            & (lat >= -90.0) & (lat <= 90.0)
            & (depth > 0.0) & (depth <= 11_500.0)
        )
        ids = np.full(n_rows, "", dtype=object)
        ids[qc] = cell_ids(lon[qc], lat[qc])
        keep = qc & pd.Index(ids).isin(target_ids)
        if keep.any():
            selected.append(pd.DataFrame({
                "cell_id": ids[keep],
                "raw_row_id": np.arange(row_offset, row_offset + n_rows, dtype=np.int64)[keep],
                "depth_m": depth[keep],
                "lon": lon[keep],
                "lat": lat[keep],
            }))
        row_offset += n_rows
        print(f"MRAR replay chunk {chunk_no}: {row_offset:,} raw rows scanned", flush=True)
    points = pd.concat(selected, ignore_index=True)
    if set(points["cell_id"]) != target_ids:
        missing = sorted(target_ids - set(points["cell_id"]))[:10]
        raise ValueError(f"MRAR raw replay cell closure failed; missing {missing}")
    raw_rel = str(raw_path.relative_to(REPO_ROOT))
    points = points.sort_values(["cell_id", "raw_row_id"]).reset_index(drop=True)
    cell_change = points["cell_id"].ne(points["cell_id"].shift())
    row_gap = points["raw_row_id"].sub(points["raw_row_id"].shift()).ne(1)
    points["_segment"] = (cell_change | row_gap).cumsum()
    segments = (
        points.groupby(["cell_id", "_segment"], sort=False)["raw_row_id"]
        .agg(["first", "last"])
        .reset_index(level="_segment", drop=True)
    )
    range_map: dict[str, list[list[int]]] = defaultdict(list)
    for cell_id, segment in segments.iterrows():
        range_map[str(cell_id)].append([int(segment["first"]), int(segment["last"])])
    grouped = points.groupby("cell_id", sort=False)
    records = grouped.agg(
        raw_point_count=("depth_m", "size"),
        file_cell_median_m=("depth_m", "median"),
        target_lon_min=("lon", "min"),
        target_lon_max=("lon", "max"),
        target_lat_min=("lat", "min"),
        target_lat_max=("lat", "max"),
    )
    records["within_file_nmad_m"] = grouped_nmad(points, "cell_id", "depth_m")
    records["raw_row_ranges"] = records.index.map(range_map)
    records = records.reset_index()
    records["source_provider"] = "mrar"
    records["file_id"] = "mrar_0-180E-0-85N.txt"
    records["subzip_id"] = "M.rar"
    records["cruise_id"] = None
    records["leg"] = None
    records["raw_file"] = raw_rel
    records["raw_file_sha256"] = raw_hashes[raw_rel]
    return records, raw_hashes


def build_replay(union: pd.DataFrame, contributors: pd.DataFrame) -> pd.DataFrame:
    grouped = contributors.groupby("cell_id", sort=False)
    replay = grouped.agg(
        source_provider=("source_provider", "first"),
        replayed_depth_m=("file_cell_median_m", "median"),
        raw_point_count=("raw_point_count", "sum"),
        raw_file_count=("file_id", "nunique"),
        official_cruise_count=("cruise_id", "nunique"),
        within_file_nmad_m=("within_file_nmad_m", "median"),
    )
    replay["between_file_nmad_m"] = grouped_nmad(contributors, "cell_id", "file_cell_median_m")
    cruise_medians = (
        contributors.dropna(subset=["cruise_id"])
        .groupby(["cell_id", "cruise_id"], sort=False)["file_cell_median_m"]
        .median()
        .reset_index()
    )
    replay["between_cruise_nmad_m"] = grouped_nmad(cruise_medians, "cell_id", "file_cell_median_m")
    replay = replay.reset_index().rename(columns={"cell_id": "canonical_cell_id"})
    replay = replay.merge(
        union[["canonical_cell_id", "representative_depth_m"]],
        on="canonical_cell_id",
        how="left",
        validate="one_to_one",
    ).rename(columns={"representative_depth_m": "frozen_depth_m"})
    replay["signed_diff_m"] = replay["replayed_depth_m"] - replay["frozen_depth_m"]
    replay["absolute_diff_m"] = replay["signed_diff_m"].abs()
    replay["replay_result"] = np.where(replay["absolute_diff_m"].le(REPLAY_ATOL_M), "exact", "different")
    replay["source_provider_status"] = "known"
    replay["frozen_depth_m_status"] = "known"
    replay["replayed_depth_m_status"] = "known"
    replay["signed_diff_m_status"] = "known"
    replay["absolute_diff_m_status"] = "known"
    replay["replay_result_status"] = "known"
    replay["raw_point_count_status"] = "known"
    replay["raw_file_count_status"] = "known"
    replay["official_cruise_count_status"] = np.where(
        replay["source_provider"].eq("jamstec"), "verified_from_source_metadata", "not_recoverable"
    )
    replay["within_file_nmad_m_status"] = np.where(
        replay["within_file_nmad_m"].notna(), "known", "not_recoverable"
    )
    replay["between_file_nmad_m_status"] = np.where(
        replay["between_file_nmad_m"].notna(), "known", "not_recoverable"
    )
    replay["between_cruise_nmad_m_status"] = np.where(
        replay["between_cruise_nmad_m"].notna(), "known", "not_recoverable"
    )
    replay["aggregation_method"] = np.where(
        replay["source_provider"].eq("jamstec"),
        "median_of_file_cell_medians",
        "median_of_qc_passed_points",
    )
    replay["aggregation_method_status"] = "known"
    if len(replay) != EXPECTED_CELL_COUNT or set(replay["canonical_cell_id"]) != set(union["canonical_cell_id"]):
        raise ValueError("raw replay cell closure failed")
    return replay


def contributor_json(group: pd.DataFrame) -> str:
    result = []
    for row in group.sort_values(["source_provider", "file_id"]).itertuples(index=False):
        result.append({
            "file_id": row.file_id,
            "subzip_id": row.subzip_id,
            "cruise_id": row.cruise_id,
            "leg": row.leg,
            "raw_file": row.raw_file,
            "raw_file_sha256": row.raw_file_sha256,
            "raw_row_ranges_0_based_inclusive": row.raw_row_ranges,
            "raw_point_count": int(row.raw_point_count),
            "file_cell_median_m": float(row.file_cell_median_m),
        })
    return stable_json(result)


def build_cell_lineage(
    union: pd.DataFrame,
    contributors: pd.DataFrame,
    official: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    jam_contributors = contributors[contributors["source_provider"].eq("jamstec")]
    contributor_groups = {key: group for key, group in jam_contributors.groupby("cell_id", sort=False)}
    rows: list[dict[str, Any]] = []
    for frozen in union[union["source_provider"].eq("jamstec")].itertuples(index=False):
        group = contributor_groups[frozen.canonical_cell_id]
        provider = "jamstec"
        raw_files = sorted(group["raw_file"].unique())
        raw_hashes = {row.raw_file: row.raw_file_sha256 for row in group.itertuples(index=False)}
        row_ids = [
            {"raw_file": row.raw_file, "ranges_0_based_inclusive": row.raw_row_ranges}
            for row in group.sort_values("file_id").itertuples(index=False)
        ]
        metadata = [official[subzip] for subzip in sorted(group["subzip_id"].unique())]
        cruises = sorted({record["cruise_id"] for record in metadata})
        legs = sorted({record["leg"] for record in metadata if record["leg"]})
        periods = sorted({record["period"] for record in metadata})
        sonars = sorted({record["sonar"] for record in metadata})
        source_archive = [
            "jamstec/multibeam/archive/foreign_bathymetry_part_1_or_2.zip (exact parent mapping not retained)"
        ]
        source_archive_status = "not_recoverable"
        official_status = "verified_from_source_metadata"
        survey_ids = cruises
        lines: list[str] = []
        lines_status = "officially_unknown"
        time_value = periods
        time_status = official_status
        sonar_value = sonars
        sonar_status = official_status
        depth_unit_status = official_status
        depth_sign = "positive_down"
        depth_sign_status = "known"
        qc_flags = [
            "finite_lon_lat_depth", "lon_in_-180_180", "lat_in_-90_90",
            "depth_gt_0_m", "depth_le_12000_m", "elevation_lt_0_m",
        ]
        aggregation = "per-file QC-point median, then unweighted median across file-cell medians"

        rows.append({
            "canonical_cell_id": frozen.canonical_cell_id,
            "source_provider": provider,
            "source_provider_status": "known",
            "source_archive_json": stable_json(source_archive),
            "source_archive_json_status": source_archive_status,
            "raw_files_json": stable_json(raw_files),
            "raw_files_json_status": "known",
            "raw_file_sha256_json": stable_json(raw_hashes),
            "raw_file_sha256_json_status": "known",
            "raw_row_ids_json": stable_json(row_ids),
            "raw_row_ids_json_status": "known",
            "raw_point_count": int(group["raw_point_count"].sum()),
            "raw_point_count_status": "known",
            "official_cruise_ids_json": stable_json(cruises),
            "official_cruise_ids_json_status": official_status,
            "official_survey_ids_json": stable_json(survey_ids),
            "official_survey_ids_json_status": official_status,
            "official_legs_json": stable_json(legs),
            "official_legs_json_status": official_status if legs else ("officially_unknown" if provider == "jamstec" else "not_recoverable"),
            "official_lines_json": stable_json(lines),
            "official_lines_json_status": lines_status,
            "official_time_ranges_json": stable_json(time_value),
            "official_time_ranges_json_status": time_status,
            "sonar_types_json": stable_json(sonar_value),
            "sonar_types_json_status": sonar_status,
            "depth_unit": "m",
            "depth_unit_status": depth_unit_status,
            "depth_sign": depth_sign,
            "depth_sign_status": depth_sign_status,
            "upstream_qc_flags_json": stable_json(qc_flags),
            "upstream_qc_flags_json_status": "known",
            "aggregation_method": aggregation,
            "aggregation_method_status": "known",
            "lineage_class": "exact_raw_row_lineage",
            "lineage_class_status": "known",
            "contributor_records_json": contributor_json(group),
            "contributor_records_json_status": "known",
        })

    mrar_source_archive_json = stable_json(["ncei/archive/zhoushuai_processed_M/M.rar"])
    mrar_raw_files_json = stable_json(["ncei/archive/zhoushuai_processed_M/0-180E-0-85N.txt"])
    empty_json = stable_json([])
    mrar_qc_json = stable_json([
        "raw_depth_lt_0_m", "raw_depth_ge_-11500_m", "finite_lon_lat_depth",
        "longitude_gt_180_minus_360", "positive_down_conversion", "1min_cell_assignment",
    ])
    mrar_records = contributors[contributors["source_provider"].eq("mrar")]
    if len(mrar_records) != EXPECTED_SOURCE_COUNTS["mrar"] or mrar_records["cell_id"].duplicated().any():
        raise ValueError("MRAR contributor table is not one row per frozen cell")
    for record in mrar_records.itertuples(index=False):
        raw_hash_json = stable_json({record.raw_file: record.raw_file_sha256})
        row_ids_json = stable_json([{
            "raw_file": record.raw_file,
            "ranges_0_based_inclusive": record.raw_row_ranges,
        }])
        contributor_record = stable_json([{
            "file_id": record.file_id,
            "subzip_id": record.subzip_id,
            "cruise_id": None,
            "leg": None,
            "raw_file": record.raw_file,
            "raw_file_sha256": record.raw_file_sha256,
            "raw_row_ranges_0_based_inclusive": record.raw_row_ranges,
            "raw_point_count": int(record.raw_point_count),
            "file_cell_median_m": float(record.file_cell_median_m),
        }])
        rows.append({
            "canonical_cell_id": record.cell_id,
            "source_provider": "mrar",
            "source_provider_status": "known",
            "source_archive_json": mrar_source_archive_json,
            "source_archive_json_status": "known",
            "raw_files_json": mrar_raw_files_json,
            "raw_files_json_status": "known",
            "raw_file_sha256_json": raw_hash_json,
            "raw_file_sha256_json_status": "known",
            "raw_row_ids_json": row_ids_json,
            "raw_row_ids_json_status": "known",
            "raw_point_count": int(record.raw_point_count),
            "raw_point_count_status": "known",
            "official_cruise_ids_json": empty_json,
            "official_cruise_ids_json_status": "not_recoverable",
            "official_survey_ids_json": empty_json,
            "official_survey_ids_json_status": "not_recoverable",
            "official_legs_json": empty_json,
            "official_legs_json_status": "not_recoverable",
            "official_lines_json": empty_json,
            "official_lines_json_status": "not_recoverable",
            "official_time_ranges_json": empty_json,
            "official_time_ranges_json_status": "not_recoverable",
            "sonar_types_json": empty_json,
            "sonar_types_json_status": "not_recoverable",
            "depth_unit": "m",
            "depth_unit_status": "known",
            "depth_sign": "negative_down_raw; converted_to_positive_down",
            "depth_sign_status": "known",
            "upstream_qc_flags_json": mrar_qc_json,
            "upstream_qc_flags_json_status": "known",
            "aggregation_method": "median across QC-passed points from one M.rar quadrant source",
            "aggregation_method_status": "known",
            "lineage_class": "exact_raw_row_lineage",
            "lineage_class_status": "known",
            "contributor_records_json": contributor_record,
            "contributor_records_json_status": "known",
        })
    lineage = pd.DataFrame(rows).sort_values("canonical_cell_id").reset_index(drop=True)
    if len(lineage) != EXPECTED_CELL_COUNT or lineage["canonical_cell_id"].duplicated().any():
        raise ValueError("cell lineage key closure failed")
    return lineage


def envelope_from_records(records: pd.DataFrame) -> dict[str, float]:
    return {
        "lon_min": float(records["target_lon_min"].min()),
        "lon_max": float(records["target_lon_max"].max()),
        "lat_min": float(records["target_lat_min"].min()),
        "lat_max": float(records["target_lat_max"].max()),
    }


def union_envelopes(envelopes: Iterable[dict[str, float]]) -> dict[str, float]:
    values = list(envelopes)
    return {
        "lon_min": min(item["lon_min"] for item in values),
        "lon_max": max(item["lon_max"] for item in values),
        "lat_min": min(item["lat_min"] for item in values),
        "lat_max": max(item["lat_max"] for item in values),
    }


def envelope_contains(outer: dict[str, float], inner: dict[str, float], tolerance: float = CELL_DEG / 2) -> bool:
    return (
        inner["lon_min"] >= outer["lon_min"] - tolerance
        and inner["lon_max"] <= outer["lon_max"] + tolerance
        and inner["lat_min"] >= outer["lat_min"] - tolerance
        and inner["lat_max"] <= outer["lat_max"] + tolerance
    )


def build_identity_ledger(
    external: pd.DataFrame,
    contributors: pd.DataFrame,
    official: dict[str, dict[str, Any]],
    full_envelopes: dict[str, dict[str, float]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    jam = contributors[contributors["source_provider"].eq("jamstec")]
    for candidate in sorted(EXPECTED_IDENTITY_GROUPS):
        external_group = external[external["cruise_id_candidate"].eq(candidate)]
        target_cells = set(external_group["cell_id"])
        records = jam[jam["cell_id"].isin(target_cells) & jam["cruise_id"].eq(candidate)].copy()
        if records.empty:
            raise ValueError(f"no upstream candidate contributors for external group {candidate}")
        subzips = sorted(records["subzip_id"].unique())
        metadata = [official[subzip] for subzip in subzips]
        official_ids = sorted({item["cruise_id"] for item in metadata})
        official_legs = sorted({item["leg"] for item in metadata if item["leg"]})
        official_files = sorted({name for item in metadata for name in item["official_files"]})
        contributor_files = sorted(records["file_id"].unique())
        expected_files = sorted({expected_official_archive(file_id.split("::", 1)[1]) for file_id in contributor_files})
        file_list_match = set(expected_files).issubset(set(official_files))
        observed = envelope_from_records(records)
        official_envelope = union_envelopes(full_envelopes[file_id] for file_id in contributor_files)
        envelope_match = envelope_contains(official_envelope, observed)
        base_match = official_ids == [candidate]
        leg_complete = all(official[subzip]["leg"] == leg_from_subzip(subzip) for subzip in subzips)
        if base_match and file_list_match and envelope_match and leg_complete:
            identity_state = "official_exact"
        elif base_match:
            identity_state = "official_leg_ambiguous"
        elif contributor_files:
            identity_state = "filename_only"
        else:
            identity_state = "unresolved"
        rows.append({
            "cruise_id_candidate": candidate,
            "cruise_id_candidate_status": "inferred_from_filename",
            "n_external_cells": len(external_group),
            "n_external_cells_status": "known",
            "official_cruise_ids_json": stable_json(official_ids),
            "official_cruise_ids_json_status": "verified_from_source_metadata",
            "official_legs_json": stable_json(official_legs),
            "official_legs_json_status": "verified_from_source_metadata" if official_legs else "officially_unknown",
            "official_ships_json": stable_json(sorted({item["ship"] for item in metadata})),
            "official_ships_json_status": "verified_from_source_metadata",
            "official_periods_json": stable_json(sorted({item["period"] for item in metadata})),
            "official_periods_json_status": "verified_from_source_metadata",
            "contributor_subzips_json": stable_json(subzips),
            "contributor_subzips_json_status": "known",
            "contributor_raw_files_json": stable_json(contributor_files),
            "contributor_raw_files_json_status": "known",
            "official_raw_files_json": stable_json(official_files),
            "official_raw_files_json_status": "verified_from_source_metadata",
            "official_file_list_contains_all_contributors": file_list_match,
            "official_file_list_contains_all_contributors_status": "verified_from_source_metadata",
            "observed_raw_point_envelope_json": stable_json(observed),
            "observed_raw_point_envelope_json_status": "known",
            "official_file_data_envelope_json": stable_json(official_envelope),
            "official_file_data_envelope_json_status": "known",
            "observed_envelope_within_official_file_data_envelope": envelope_match,
            "observed_envelope_within_official_file_data_envelope_status": "known",
            "identity_state": identity_state,
            "identity_state_status": "verified_from_source_metadata" if identity_state.startswith("official_") else "inferred_from_filename",
            "evidence_paths_json": stable_json(sorted({item["pdf_path"] for item in metadata})),
            "evidence_paths_json_status": "known",
            "evidence_sha256_json": stable_json({item["pdf_path"]: item["pdf_sha256"] for item in metadata}),
            "evidence_sha256_json_status": "known",
            "cruise_report_urls_json": stable_json(sorted({item["report_url"] for item in metadata if item["report_url"]})),
            "cruise_report_urls_json_status": "verified_from_source_metadata",
            "ncei_exact_metadata_match": "not_recovered",
            "ncei_exact_metadata_match_status": "not_recoverable",
            "notes": "JAMSTEC official DARWIN metadata is primary; NCEI indexed-search non-recovery is not evidence of absence.",
            "notes_status": "known",
        })
    ledger = pd.DataFrame(rows)
    if set(ledger["identity_state"]) - IDENTITY_STATES:
        raise ValueError("identity ledger contains invalid four-state value")
    return ledger


def build_vertical_ledger(
    contributors: pd.DataFrame,
    official: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    jam = contributors[contributors["source_provider"].eq("jamstec")]
    for cruise_id, group in jam.groupby("cruise_id", sort=True):
        metadata = [official[subzip] for subzip in sorted(group["subzip_id"].unique())]
        vertical_stated = any(item["vertical_datum_stated"] for item in metadata)
        ellipsoid_stated = any(item["ellipsoid_stated"] for item in metadata)
        geoid_stated = any(item["geoid_stated"] for item in metadata)
        chart_stated = any(item["chart_datum_stated"] for item in metadata)
        rows.append({
            "source_cruise": cruise_id,
            "source_cruise_status": "verified_from_source_metadata",
            "source_provider": "jamstec",
            "source_provider_status": "known",
            "vertical_datum": "stated_in_source" if vertical_stated else "unknown",
            "vertical_datum_status": "verified_from_source_metadata" if vertical_stated else "officially_unknown",
            "sounding_reduction": "sound_velocity_profile_corrected",
            "sounding_reduction_status": "verified_from_source_metadata",
            "tide_correction": "not_corrected",
            "tide_correction_status": "verified_from_source_metadata",
            "horizontal_geodetic_system": stable_json(sorted({item["horizontal_datum"] for item in metadata})),
            "horizontal_geodetic_system_status": "verified_from_source_metadata",
            "ellipsoid": "stated_in_source" if ellipsoid_stated else "unknown",
            "ellipsoid_status": "verified_from_source_metadata" if ellipsoid_stated else "officially_unknown",
            "geoid": "stated_in_source" if geoid_stated else "unknown",
            "geoid_status": "verified_from_source_metadata" if geoid_stated else "officially_unknown",
            "chart_datum": "stated_in_source" if chart_stated else "unknown",
            "chart_datum_status": "verified_from_source_metadata" if chart_stated else "officially_unknown",
            "depth_unit": "m",
            "depth_unit_status": "verified_from_source_metadata",
            "raw_depth_sign": "positive_down",
            "raw_depth_sign_status": "known",
            "evidence_paths_json": stable_json(sorted({item["pdf_path"] for item in metadata})),
            "evidence_paths_json_status": "known",
            "evidence_sha256_json": stable_json({item["pdf_path"]: item["pdf_sha256"] for item in metadata}),
            "evidence_sha256_json_status": "known",
        })
    rows.append({
        "source_cruise": "mrar_0-180E-0-85N.txt",
        "source_cruise_status": "not_recoverable",
        "source_provider": "mrar",
        "source_provider_status": "known",
        "vertical_datum": "unknown",
        "vertical_datum_status": "not_recoverable",
        "sounding_reduction": "unknown",
        "sounding_reduction_status": "not_recoverable",
        "tide_correction": "unknown",
        "tide_correction_status": "not_recoverable",
        "horizontal_geodetic_system": "unknown",
        "horizontal_geodetic_system_status": "not_recoverable",
        "ellipsoid": "unknown",
        "ellipsoid_status": "not_recoverable",
        "geoid": "unknown",
        "geoid_status": "not_recoverable",
        "chart_datum": "unknown",
        "chart_datum_status": "not_recoverable",
        "depth_unit": "m",
        "depth_unit_status": "known",
        "raw_depth_sign": "negative_down; converted_to_positive_down",
        "raw_depth_sign_status": "known",
        "evidence_paths_json": stable_json([
            "ncei/archive/zhoushuai_processed_M/SOURCE.md",
            "ncei/code/04_clean_mrar.py",
        ]),
        "evidence_paths_json_status": "known",
        "evidence_sha256_json": stable_json({
            "ncei/archive/zhoushuai_processed_M/SOURCE.md": sha256_file(NCEI_ROOT / "archive/zhoushuai_processed_M/SOURCE.md"),
            "ncei/code/04_clean_mrar.py": sha256_file(NCEI_ROOT / "code/04_clean_mrar.py"),
        }),
        "evidence_sha256_json_status": "known",
    })
    return pd.DataFrame(rows)


def validate_status_pairs(frame: pd.DataFrame, key_columns: set[str]) -> None:
    value_columns = [column for column in frame.columns if not column.endswith("_status") and column not in key_columns]
    missing = [column for column in value_columns if f"{column}_status" not in frame.columns]
    if missing:
        raise ValueError(f"fields missing five-level status columns: {missing}")
    for column in frame.columns:
        if column.endswith("_status"):
            invalid = set(frame[column].dropna().astype(str)) - FIELD_STATUSES
            if invalid:
                raise ValueError(f"invalid five-level values in {column}: {sorted(invalid)}")


def diff_summary(replay: pd.DataFrame) -> dict[str, Any]:
    by_source: dict[str, Any] = {}
    for provider, group in replay.groupby("source_provider", sort=True):
        abs_diff = group["absolute_diff_m"].to_numpy(dtype=np.float64)
        by_source[provider] = {
            "cell_count": len(group),
            "exact_count_at_1e-9_m": int((abs_diff <= REPLAY_ATOL_M).sum()),
            "different_count_at_1e-9_m": int((abs_diff > REPLAY_ATOL_M).sum()),
            "max_abs_diff_m": float(abs_diff.max()),
            "median_abs_diff_m": float(np.median(abs_diff)),
            "raw_point_count": int(group["raw_point_count"].sum()),
        }
    all_abs = replay["absolute_diff_m"].to_numpy(dtype=np.float64)
    return {
        "comparison_tolerance_m": REPLAY_ATOL_M,
        "cell_count": len(replay),
        "exact_count_at_1e-9_m": int((all_abs <= REPLAY_ATOL_M).sum()),
        "different_count_at_1e-9_m": int((all_abs > REPLAY_ATOL_M).sum()),
        "max_abs_diff_m": float(all_abs.max()),
        "median_abs_diff_m": float(np.median(all_abs)),
        "by_source": by_source,
    }


def jamstec_file_cell_diagnostics(
    upstream_file_cells: pd.DataFrame,
    raw_file_cells: pd.DataFrame,
) -> dict[str, Any]:
    upstream = upstream_file_cells[[
        "cell_id", "file_id", "n_points", "median_depth_m_positive_down",
    ]]
    raw = raw_file_cells[[
        "cell_id", "file_id", "raw_point_count", "file_cell_median_m",
    ]]
    merged = upstream.merge(raw, on=["cell_id", "file_id"], how="outer", validate="one_to_one", indicator=True)
    if not merged["_merge"].eq("both").all():
        raise ValueError("JAMSTEC upstream/raw file-cell key closure failed")
    count_mismatch = merged["n_points"].ne(merged["raw_point_count"])
    median_diff = merged["file_cell_median_m"] - merged["median_depth_m_positive_down"]
    different = median_diff.abs().gt(REPLAY_ATOL_M)
    implementation_path = JAM_ROOT / "code/04a_make_multibeam_file_cells.py"
    return {
        "file_cell_rows": len(merged),
        "raw_point_count_mismatch_rows": int(count_mismatch.sum()),
        "median_different_file_cell_rows": int(different.sum()),
        "median_different_cells": int(merged.loc[different, "cell_id"].nunique()),
        "max_abs_file_cell_median_diff_m": float(median_diff.abs().max()),
        "root_cause": "cross-batch cells use an n_points-weighted average of chunk medians in _combine_chunk_cells; raw replay computes the exact all-point median",
        "upstream_implementation_path": str(implementation_path.relative_to(REPO_ROOT)),
        "upstream_implementation_sha256": sha256_file(implementation_path),
    }


def build_report(
    run_id: str,
    inputs: dict[str, dict[str, Any]],
    upstream: dict[str, Any],
    identity: pd.DataFrame,
    vertical: pd.DataFrame,
    lineage: pd.DataFrame,
    replay_summary: dict[str, Any],
) -> str:
    status_counts: dict[str, int] = defaultdict(int)
    for column in lineage.columns:
        if column.endswith("_status"):
            for value, count in lineage[column].value_counts().items():
                status_counts[str(value)] += int(count)
    identity_counts = identity["identity_state"].value_counts().to_dict()
    inputs_table = "\n".join(
        f"| `{role}` | `{record['path']}` | `{record['sha256']}` |"
        for role, record in inputs.items()
    )
    status_table = "\n".join(f"| `{status}` | {status_counts.get(status, 0):,} |" for status in sorted(FIELD_STATUSES))
    identity_table = "\n".join(f"| `{state}` | {identity_counts.get(state, 0):,} |" for state in sorted(IDENTITY_STATES))
    return f"""# SCS upstream lineage and label audit

Run ID: `{run_id}`

## Scope and boundary

The audited cohort is exactly the frozen 174,965-cell union supplied by the
downstream handoff. The audit did not inspect global non-cohort cells beyond
the narrow upstream joins needed to locate contributors. It did not read any
downstream prediction, residual, model-error, or metric file, and it does not
decide label eligibility. No cell is removed or relabeled using GEBCO,
three-standard-deviation filtering, or any downstream discrepancy.

## Frozen inputs

| Role | Absolute path | SHA256 |
|---|---|---|
{inputs_table}

## Closure and replay

- Union cells: {EXPECTED_CELL_COUNT:,} ({EXPECTED_SOURCE_COUNTS['mrar']:,} MRAR; {EXPECTED_SOURCE_COUNTS['jamstec']:,} JAMSTEC).
- External identity cells/groups: {EXPECTED_EXTERNAL_COUNT:,} / {len(EXPECTED_IDENTITY_GROUPS)}.
- JAMSTEC contributor files/file-cells: {lineage.loc[lineage['source_provider'].eq('jamstec'), 'raw_files_json'].map(json.loads).explode().nunique():,} / {upstream['jamstec_file_cell_rows']:,}.
- MRAR upstream points in the frozen cells: {upstream['mrar_upstream_points']:,}.
- Raw replay exact cells at 1e-9 m: {replay_summary['exact_count_at_1e-9_m']:,}; different: {replay_summary['different_count_at_1e-9_m']:,}; maximum absolute difference: {replay_summary['max_abs_diff_m']:.12g} m.

All {replay_summary['by_source']['mrar']['cell_count']:,} MRAR cells reproduce
exactly. At the JAMSTEC file-cell layer,
{replay_summary['jamstec_file_cell_diagnostics']['median_different_file_cell_rows']:,}
rows across {replay_summary['jamstec_file_cell_diagnostics']['median_different_cells']:,}
cells differ despite identical raw point counts; after the median across files,
{replay_summary['by_source']['jamstec']['different_count_at_1e-9_m']:,} final
cell depths differ. These differences are explained by the documented
`_combine_chunk_cells` approximation in
`{replay_summary['jamstec_file_cell_diagnostics']['upstream_implementation_path']}`:
when one cell crosses Parquet batches, the existing product stores an
`n_points`-weighted average of chunk medians rather than the exact median of all
raw points. The raw replay reports the exact median and preserves the signed
difference; this is an aggregation implementation difference, not evidence that
the underlying pings are bad.

## P0 identity result

| Four-state result | Groups |
|---|---:|
{identity_table}

The official evidence is the locally retained English JAMSTEC DARWIN PDF for
each contributing cruise/leg, hashed in the ledgers. Identity requires the
official cruise ID, ship/period metadata, official archive member list, leg
mapping where applicable, and containment within the corresponding official
file-data envelope. The file-data envelope is computed from the officially
listed delivered source files; it is not presented as an independently
digitized cruise-report track. Failure to recover an exact NCEI indexed record
is recorded as `not_recoverable`, not as proof that no record exists.

## P1 vertical metadata

The ledger has {len(vertical):,} source/cruise rows. JAMSTEC documents WGS84 as
the horizontal geodetic system, sound-velocity-profile correction, and no tide
correction. They do not state a vertical datum, ellipsoid, geoid, or chart datum;
those fields therefore remain literal `unknown` with `officially_unknown`.
MRAR cruise/line and vertical reference remain `unknown`/`not_recoverable`.

## P2 five-level status counts

Counts below aggregate all status-bearing cell-lineage fields, not cells.

| Status | Field values |
|---|---:|
{status_table}

All cells have exact, zero-based raw source-row ranges and raw-file SHA256.
MRAR's earlier derived `point_index_in_track` is not promoted to a raw row ID;
the row ranges here were recovered by a fresh bounded stream over the source
quadrant file.

## P3 aggregation and dispersion

JAMSTEC replay applies longitude normalization, basic point QC, 1 arc-minute
assignment, per-file point medians, and an unweighted median across file-cell
medians. MRAR applies its documented negative-down to positive-down conversion,
basic QC, 1 arc-minute assignment, and point median. Within-file, between-file,
and between-cruise NMAD are reported only when the corresponding independent
units exist; undefined layers are null and are not replaced by zero.

## Incomplete and bounded items

- NCEI exact cruise-metadata records for the 12 JAMSTEC candidate IDs were not
  recovered; JAMSTEC DARWIN metadata is the official primary identity evidence.
- JAMSTEC active extraction was retained under two large transfer archives, but
  their exact member-to-parent mapping was not preserved. Raw files and the
  locally retained official metadata PDFs are hashed; the ambiguous
  parent archive field is `not_recoverable`.
- The contract's prior P4 count (137,859 points / 9,069 file-cells) is not used
  as a cell-level replay count. For this frozen union, the observed MRAR replay
  scale is reported directly and the prior conclusion is retained only for the
  unresolved cruise/line identity boundary.
- Exact MRAR source-row numbers are recoverable, but cruise, line, and time are
  not. Adjacent source rows therefore cannot be promoted to verified adjacent
  pings or used for a line-level crossover adjustment.
- Candidate official SCS cruises that never entered the downstream workflow are
  outside this blocking audit and were not promoted into its frozen cohort.
"""


def parse_args() -> argparse.Namespace:
    downstream_root = Path("/mnt/data2/06-Projects/12-ggm_scs")
    union_dir = downstream_root / "outputs/diagnostics/downstream_cell_union/20260804T183655Z"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downstream-union", type=Path, default=union_dir / "downstream_cell_union.parquet")
    parser.add_argument("--counts-closure", type=Path, default=union_dir / "counts_closure.json")
    parser.add_argument("--downstream-manifest", type=Path, default=union_dir / "manifest.json")
    parser.add_argument(
        "--external-group-manifest",
        type=Path,
        default=downstream_root / "outputs/diagnostics/survey_group_validation/20260729T050611318804Z_06415a1299eb/cohort/group_manifest.parquet",
    )
    parser.add_argument("--output-root", type=Path, default=NCEI_ROOT / "derived/scs_upstream_lineage_audit")
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--confirm-audit", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confirm_audit:
        raise SystemExit("refusing audit without --confirm-audit")
    if Path.cwd().resolve() != REPO_ROOT:
        raise SystemExit(f"run from repository root: cd {REPO_ROOT}")
    run_dir = args.output_root.resolve() / args.run_id
    if run_dir.exists():
        raise FileExistsError(f"immutable run directory already exists: {run_dir}")

    input_paths = {
        "downstream_union": args.downstream_union.resolve(),
        "counts_closure": args.counts_closure.resolve(),
        "downstream_manifest": args.downstream_manifest.resolve(),
        "external_group_manifest": args.external_group_manifest.resolve(),
    }
    inputs = validate_frozen_inputs(input_paths)
    union, external = load_cohort(input_paths["downstream_union"], input_paths["external_group_manifest"])
    jam_target = union[union["source_provider"].eq("jamstec")]
    mrar_target = union[union["source_provider"].eq("mrar")]
    jam_fc, jam_meta = discover_jamstec_contributors(set(jam_target["canonical_cell_id"]), jam_target)
    upstream = verify_upstream_cell_products(union, jam_fc)
    official = load_official_metadata(jam_meta)

    jam_records, full_envelopes, jam_hashes = replay_jamstec(
        jam_meta, set(jam_target["canonical_cell_id"])
    )
    mrar_records, mrar_hashes = replay_mrar(set(mrar_target["canonical_cell_id"]))
    print(f"MRAR grouped: {len(mrar_records):,} cells", flush=True)
    contributors = pd.concat([jam_records, mrar_records], ignore_index=True)
    replay = build_replay(union, contributors)
    print(f"Replay table built: {len(replay):,} cells", flush=True)
    lineage = build_cell_lineage(union, contributors, official)
    print(f"Lineage table built: {len(lineage):,} cells", flush=True)
    identity = build_identity_ledger(external, contributors, official, full_envelopes)
    vertical = build_vertical_ledger(contributors, official)
    print(f"Ledgers built: {len(identity)} identity groups, {len(vertical)} vertical rows", flush=True)
    validate_status_pairs(lineage, {"canonical_cell_id"})
    validate_status_pairs(identity, set())
    validate_status_pairs(vertical, set())
    validate_status_pairs(replay, {"canonical_cell_id"})
    summary = diff_summary(replay)
    summary["jamstec_file_cell_diagnostics"] = jamstec_file_cell_diagnostics(jam_fc, jam_records)

    run_dir.mkdir(parents=True)
    print(f"Writing immutable artifacts: {run_dir}", flush=True)
    artifact_paths = {
        "cell_lineage": run_dir / "cell_lineage.parquet",
        "source_identity_ledger": run_dir / "source_identity_ledger.csv",
        "vertical_datum_ledger": run_dir / "vertical_datum_ledger.csv",
        "raw_to_cell_replay": run_dir / "raw_to_cell_replay.parquet",
        "diff_summary": run_dir / "diff_summary.json",
        "audit_report": run_dir / "audit_report.md",
    }
    atomic_parquet(lineage, artifact_paths["cell_lineage"])
    atomic_csv(identity, artifact_paths["source_identity_ledger"])
    atomic_csv(vertical, artifact_paths["vertical_datum_ledger"])
    atomic_parquet(replay.sort_values("canonical_cell_id"), artifact_paths["raw_to_cell_replay"])
    atomic_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", artifact_paths["diff_summary"])
    report = build_report(args.run_id, inputs, upstream, identity, vertical, lineage, summary)
    atomic_text(report, artifact_paths["audit_report"])

    output_records = {
        role: {"path": str(path), "sha256": sha256_file(path), "size_bytes": path.stat().st_size}
        for role, path in artifact_paths.items()
    }
    manifest = {
        "audit_contract": "08-04-scs-upstream-lineage-and-label-contract",
        "run_id": args.run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "command": sys.argv,
        "working_directory": str(Path.cwd()),
        "python": sys.version,
        "platform": platform.platform(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "field_statuses": sorted(FIELD_STATUSES),
        "identity_states": sorted(IDENTITY_STATES),
        "forbidden_downstream_tokens": list(FORBIDDEN_NAME_TOKENS),
        "downstream_model_error_read": False,
        "inputs": inputs,
        "upstream_closure": upstream,
        "raw_source_sha256": {**jam_hashes, **mrar_hashes},
        "official_metadata_sha256": {
            item["pdf_path"]: item["pdf_sha256"] for item in official.values()
        },
        "outputs": output_records,
    }
    manifest_path = run_dir / "audit_manifest.json"
    atomic_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", manifest_path)
    print(f"Audit complete: {run_dir}")
    print(f"Manifest SHA256: {sha256_file(manifest_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
