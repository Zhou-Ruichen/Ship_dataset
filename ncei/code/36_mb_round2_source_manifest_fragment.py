#!/usr/bin/env python3
"""Stage 4 — L3 trackline-source-manifest fragment for the mb_round2 cruises.

Builds one 26-column row per cruise following the column semantics of
ncei/docs/trackline_source_manifest_schema.md. The output is a STANDALONE
fragment under ncei/derived/mb_round2/ — the production
ncei/manifests/trackline_source_manifest.parquet is NOT touched (merge
awaits user review).

New source-side values introduced (add-only, per the schema's stable
contract): source_type='ncei_mb58', source_completeness='mb58_only'.

Classification reuses _common.r2_classifier.classify; the depth-sign
enum follows 01_build_trackline_source_manifest.depth_sign's threshold
(>=95% of nonzero finite raw depths).

Run from repo root:
    python ncei/code/36_mb_round2_source_manifest_fragment.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from _common.file_io import atomic_write_parquet  # noqa: E402
from _common.r2_classifier import classify  # noqa: E402

OUT_ROOT = REPO_ROOT / "ncei/derived/mb_round2"

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

SOURCE_ARCHIVE = "ncei platforms tree direct download (raw_round2, 2026-09)"


def resolve_source_paths(
    cruise: str, manifest: pd.DataFrame,
    raw_root: Path = REPO_ROOT / "ncei/raw_round2/platforms_tree",
) -> tuple[str, pd.DataFrame]:
    """Resolve extraction paths without changing their historical file keys.

    source_relpath is relative to platforms_tree; source_path is relative
    to ncei, as required by the trackline source-manifest contract.
    """
    resolved = manifest.copy()
    candidates = [raw_root / cruise, *sorted(raw_root.glob(f"*/{cruise}"))]
    source_dirs = [path for path in candidates if path.is_dir()]
    paths = []
    for row in resolved.itertuples():
        rel = Path(row.relpath)
        if "source_relpath" in resolved and pd.notna(row.source_relpath):
            path = raw_root / row.source_relpath
        elif (raw_root / rel).is_file():
            path = raw_root / rel
        else:
            parts = rel.parts
            tail = Path(*parts[parts.index(cruise) + 1:])
            matches = [directory / tail for directory in source_dirs if (directory / tail).is_file()]
            if not matches and tail.suffix == ".gz":
                # Historical staging can outlive a source archive that was
                # unpacked in place; use the existing uncompressed source.
                raw_tail = tail.with_suffix("")
                candidates_without_compression = [raw_tail]
                if raw_tail.suffix in {".mb11", ".mb32", ".mb41", ".mb58", ".mb84", ".mb121"}:
                    candidates_without_compression.append(raw_tail.with_suffix(""))
                for candidate in candidates_without_compression:
                    matches = [
                        directory / candidate for directory in source_dirs
                        if (directory / candidate).is_file()
                    ]
                    if matches:
                        break
            if len(matches) != 1:
                raise ValueError(f"{cruise}: source path is missing or ambiguous: {rel}: {matches}")
            path = matches[0]
        if not path.is_file():
            raise FileNotFoundError(path)
        paths.append(path.relative_to(raw_root).as_posix())
    resolved["source_relpath"] = paths
    cruise_dirs = set()
    for rel in paths:
        parts = Path(rel).parts
        cruise_dirs.add(Path(*parts[:parts.index(cruise) + 1]))
    if len(cruise_dirs) != 1:
        raise ValueError(f"{cruise}: expected one source directory, got {cruise_dirs}")
    directory = raw_root / cruise_dirs.pop()
    return directory.relative_to(REPO_ROOT / "ncei").as_posix(), resolved


def main() -> int:
    rows = []
    for cruise_dir in sorted(p for p in OUT_ROOT.iterdir() if (p / "points_checked").is_dir()):
        cruise = cruise_dir.name
        track_id = cruise.lower()
        shards = sorted((cruise_dir / "points_checked").glob(f"{track_id}__mb*.parquet"))
        if not shards:
            continue
        points_path = shards[0]
        tag = points_path.stem.split("__", 1)[1]
        manifest = pd.read_parquet(cruise_dir / "extraction_manifest.parquet")
        ok = manifest[manifest["status"].isin(["ok", "skipped_exists"])]
        source_path, _ = resolve_source_paths(cruise, ok)
        # Depth-sign verdict comes from the stage-2 merge summary; manifest
        # counters are None for files skipped on resumed runs and cannot be
        # summed across mixed runs.
        summary = json.loads((cruise_dir / "extraction_summary.json").read_text(encoding="utf-8"))
        sign = summary["depth_sign_raw"]

        lon_chunks, lat_chunks = [], []
        n_depth_finite = 0
        depth_min, depth_max = math.inf, -math.inf
        pf = pq.ParquetFile(points_path)
        for batch in pf.iter_batches(batch_size=1_000_000, columns=["lon", "lat", "depth_raw"]):
            df = batch.to_pandas()
            lon = df["lon"].to_numpy(dtype=np.float64)
            lat = df["lat"].to_numpy(dtype=np.float64)
            finite = np.isfinite(lon) & np.isfinite(lat)
            lon_chunks.append(lon[finite])
            lat_chunks.append(lat[finite])
            depth = df["depth_raw"].to_numpy(dtype=np.float64)
            dfinite = np.isfinite(depth)
            n_depth_finite += int(np.count_nonzero(dfinite))
            if dfinite.any():
                depth_min = min(depth_min, float(depth[dfinite].min()))
                depth_max = max(depth_max, float(depth[dfinite].max()))
        lon = np.concatenate(lon_chunks) if lon_chunks else np.array([])
        lat = np.concatenate(lat_chunks) if lat_chunks else np.array([])
        del lon_chunks, lat_chunks

        n_points = int(len(lon))
        if n_points:
            lon_min, lon_max = float(lon.min()), float(lon.max())
            lat_min, lat_max = float(lat.min()), float(lat.max())
            lat_mid = 0.5 * (lat_min + lat_max)
            area = (lon_max - lon_min) * (lat_max - lat_min) * math.cos(math.radians(lat_mid)) * 111.32 * 111.32
        else:
            lon_min = lon_max = lat_min = lat_max = math.nan
            area = math.nan
        density = n_points / area if area and area > 0 else (math.inf if n_points else math.nan)

        result = classify(lon, lat) if n_points else None
        pred = "multibeam" if (result is not None and result.label == "mb") else "singlebeam"
        rule = result.reason if result is not None else ""
        # The R2 classifier infers instrument class from trackline geometry;
        # for these cruises the instrument is known from the raw source
        # (.all.mb58 em122/em710/em302). Where the classifier disagrees with
        # the known source, record the source truth in manual_override for
        # curator review instead of silently trusting either side.
        override = ""
        if pred != "multibeam":
            override = "multibeam; raw .all.mb58 swath source (stage-2 provenance)"

        rows.append({
            "track_id": track_id,
            "source_type": f"ncei_{tag}",
            "source_completeness": f"{tag}_only",
            "source_path": source_path,
            "source_archive": SOURCE_ARCHIVE,
            "n_points": n_points,
            "bbox_lon_min": lon_min, "bbox_lon_max": lon_max,
            "bbox_lat_min": lat_min, "bbox_lat_max": lat_max,
            "bbox_area_km2": area, "point_density_km2": density,
            "has_time": True,
            "has_depth": n_depth_finite > 0,
            "has_gobs": False, "has_faa": False,
            "depth_sign_raw": sign,
            "depth_min_raw": depth_min if math.isfinite(depth_min) else math.nan,
            "depth_max_raw": depth_max if math.isfinite(depth_max) else math.nan,
            "instrument_class_pred": pred,
            "classification_rule": rule,
            "classification_review": bool(pred == "multibeam"),
            "review_reason": (rule if pred == "multibeam" else "r2_pred_sb_overridden_by_source"),
            "manual_override": override,
            "source_author": None,
            "survey_id": cruise,
        })

    out = pd.DataFrame(rows, columns=COLUMNS)
    out_path = OUT_ROOT / "mb_round2_source_manifest_fragment.parquet"
    atomic_write_parquet(out, out_path)
    out.to_csv(OUT_ROOT / "mb_round2_source_manifest_fragment.tsv", sep="\t", index=False)
    print(out[["track_id", "n_points", "bbox_area_km2", "depth_sign_raw", "instrument_class_pred", "classification_rule"]].to_string(index=False))
    print(f"fragment: {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
