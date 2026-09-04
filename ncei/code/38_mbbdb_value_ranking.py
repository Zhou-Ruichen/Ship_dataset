#!/usr/bin/env python3
"""Stage C — download-value ranking of the MBBDB increment cruises.

Pure computation + catalog metadata fetch; never downloads data files.

Pipeline (run from repo root):
  1. python ncei/code/38_mbbdb_value_ranking.py --fetch-trackline
     Batch-queries the NCEI trackline catalog (next-catalogs
     /rest/trackline/catalog/survey?surveyIds=...) via curl through
     127.0.0.1:2085 for every increment cruise that has a same-ID
     singlebeam survey; parses the returned track bbox. Raw JSON pages
     are kept in /tmp/mbbdb_r2/trackline/.
  2. python ncei/code/38_mbbdb_value_ranking.py --compute
     Builds the value ranking and the A/B/C order lists.

Estimation model (see ncei/docs/step16_mbbdb_value_ranking.md):
  - trackline-same-ID cruises: upper bound = 1-arcmin cells inside the
    TRACKLINE track bbox that are not already in the strict layer;
  - other cruises: cells inside the MBBDB survey bbox outside the
    strict layer, times a strip discount calibrated on the step15
    anchors (actual new cells / bbox-outside-strict cells);
  - value = estimated new cells / fileSizeSum(GB); greedy selection
    with per-platform 15% and per-decade 25% seat caps; tiers are
    prefixes of the same greedy list at ~1 / ~5 / ~9.5 TB.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "ncei/derived/mbbdb_value_ranking"
TMP_DIR = Path("/tmp/mbbdb_r2")
TRACKLINE_RAW = TMP_DIR / "trackline"

MBBDB_TSV = TMP_DIR / "mbbdb_surveys.tsv"
GAP_PATH = REPO_ROOT / "ncei/manifests/ncei_catalog_gap_2026-09.parquet"
STRICT_PATH = REPO_ROOT / "ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet"
STEP15_CELLS = REPO_ROOT / "ncei/derived/mb_round2/file_cells_manifest.parquet"

LON_BINS = 21_600
LAT_BINS = 10_800
LON_BIN_SPAN = LON_BINS + 1

PROXY = "http://127.0.0.1:2085"
BATCH = 100
# Server-side broken trackline record (500 even alone; documented in
# ncei/docs/step11_archive_gap_report.md). Its cruise falls back to the
# bbox x discount estimate.
EXCLUDE_TL = {"U2019-032"}

SHIP_CAP = 0.15
DECADE_CAP = 0.25
TIER_BYTES = {"A": 1.0e12, "B": 5.0e12, "C": 9.5e12}

# Upper bound on extractable soundings per compressed GB, calibrated on the
# step15 corpus: 462,628,624 rows / 61.99 GB = 7.46e6 rows/GB. A cruise's
# distinct new cells cannot exceed its sounding count, so this caps the
# bbox-based estimates for tiny-file / huge-bbox entries.
ROWS_PER_GB = 7.46e6
# Realized new-strict-cells per compressed GB on the same corpus:
# 50,614 cells / 61.99 GB ~= 816.5. Caps the central estimate so that
# data-volume-bound cruises are valued at the achieved average density,
# not the theoretical sounding bound.
ANCHOR_CELLS_PER_GB = 50_614 / 61.99

# Six downstream regions (annotation only, never a filter).
REGIONS = {
    "lon068_lat018": (160.0, 165.0, 0.0, 5.0),
    "lon052_lat018": (80.0, 85.0, 0.0, 5.0),
    "lon058_lat012": (110.0, 115.0, -30.0, -25.0),
    "lon059_lat015": (115.0, 120.0, -15.0, -10.0),
    "lon004_lat033": (-160.0, -155.0, 75.0, 80.0),
    "lon021_lat010": (-75.0, -70.0, -40.0, -35.0),
}


def norm(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def local_keys() -> set[str]:
    keys: set[str] = set()
    jam = pd.read_csv(REPO_ROOT / "jamstec/multibeam/manifests/cruise_summary_for_review.tsv", sep="\t")
    keys |= {norm(x) for x in jam["cruise_id"].astype(str)}
    frag = {"ab1999", "at27a", "int_9125", "nf-10-01-02-crer-rfr", "ra022-3", "ra028-09", "ra304-15"} | {f"sentry{i}" for i in range(418, 429)}
    keys |= {norm(x) for x in frag}
    keys |= {norm(p.name) for p in (REPO_ROOT / "ncei/raw_round2/platforms_tree").iterdir()}
    keys |= {norm(p.name[:-7]) for p in (REPO_ROOT / "ncei/raw_round2/r2r").glob("*.tar.gz")}
    return keys


def parse_geometry(text: str) -> tuple[float, float, float, float] | None:
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        lon_min, lat_min, lon_max, lat_max = (float(v) for v in text.split(","))
    except ValueError:
        return None
    return lon_min, lat_min, lon_max, lat_max


def strict_grid() -> np.ndarray:
    """Boolean mask of strict-layer cells on the 21600 x 10800 1-arcmin grid."""
    cells = pd.read_parquet(STRICT_PATH, columns=["cell_id"])["cell_id"].astype(str)
    lat_bin = cells.str.split("_").str[1].astype(np.int32).to_numpy()
    lon_bin = cells.str.split("_").str[2].astype(np.int32).to_numpy()
    grid = np.zeros((LAT_BINS, LON_BINS), dtype=bool)
    grid[lat_bin, lon_bin] = True
    return grid


def cells_outside_strict(grid: np.ndarray, bbox: tuple[float, float, float, float]) -> int:
    lon_min, lat_min, lon_max, lat_max = bbox
    lo = math.floor((lon_min + 180.0) * 60.0)
    hi = math.ceil((lon_max + 180.0) * 60.0)
    la = math.floor((lat_min + 90.0) * 60.0)
    lb = math.ceil((lat_max + 90.0) * 60.0)
    lo, hi = max(lo, 0), min(hi, LON_BINS)
    la, lb = max(la, 0), min(lb, LAT_BINS)
    if hi <= lo or lb <= la:
        return 0
    region = grid[la:lb, lo:hi]
    return int(region.size - region.sum())


def fetch_trackline(ids: list[str]) -> None:
    TRACKLINE_RAW.mkdir(parents=True, exist_ok=True)
    for i in range(0, len(ids), BATCH):
        batch = ids[i : i + BATCH]
        out = TRACKLINE_RAW / f"tl_{i//BATCH:03d}.json"
        if out.exists() and out.stat().st_size > 0:
            continue
        url = "https://www.ngdc.noaa.gov/next-catalogs/rest/trackline/catalog/survey?surveyIds=" + ",".join(batch)
        for attempt in (1, 2):
            result = subprocess.run(
                ["curl", "-sS", "--proxy", PROXY, "--connect-timeout", "10", "--max-time", "90", "-o", str(out) + ".tmp", "-w", "%{http_code}", url],
                capture_output=True, text=True, check=False,
            )
            code = result.stdout.strip()
            if code == "200":
                os.replace(str(out) + ".tmp", out)
                break
            print(f"batch {i//BATCH}: http {code} (attempt {attempt})", file=sys.stderr)
            time.sleep(5)
        else:
            raise RuntimeError(f"trackline catalog batch {i//BATCH} failed after retries")
        print(f"batch {i//BATCH}: {len(batch)} ids ok ({out.stat().st_size} bytes)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-trackline", action="store_true")
    parser.add_argument("--compute", action="store_true")
    args = parser.parse_args()

    # ---- increment definition (same matching rule as step13/step15) ----
    mb = pd.read_csv(MBBDB_TSV, sep="\t").drop_duplicates(subset=["surveyId"]).copy()
    mb["key"] = mb["surveyId"].map(norm)
    have = local_keys()
    inc = mb[~mb["key"].isin(have)].copy()
    inc["year"] = pd.to_numeric(inc["startTime"].astype(str).str[:4], errors="coerce")
    inc["decade"] = (inc["year"] // 10 * 10).astype("Int64")
    inc["bytes"] = pd.to_numeric(inc["fileSizeSum"], errors="coerce").fillna(0)
    inc["bbox_mb"] = inc["geometry"].map(parse_geometry)

    gap = pd.read_parquet(GAP_PATH)
    gap_ids = {norm(s): str(s) for s in gap["survey_id"].astype(str).unique()}
    inc["trackline_id"] = inc["key"].map(gap_ids)
    inc["trackline_hit"] = inc["trackline_id"].notna()

    if args.fetch_trackline:
        ids = inc.loc[inc["trackline_hit"], "trackline_id"].drop_duplicates().tolist()
        ids = [i for i in ids if i not in EXCLUDE_TL]
        print(f"fetching trackline bboxes for {len(ids)} surveys")
        fetch_trackline(ids)

    if not args.compute:
        return 0

    # ---- trackline bboxes from cached pages ----
    tl_bbox: dict[str, tuple[float, float, float, float]] = {}
    for page in sorted(TRACKLINE_RAW.glob("tl_*.json")):
        for item in json.loads(page.read_text(encoding="utf-8")).get("items", []):
            box = item.get("bbox")
            if box and len(box) == 4:
                tl_bbox[str(item["surveyId"])] = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
    inc["bbox_tl"] = inc["trackline_id"].map(tl_bbox)
    has_tl_bbox = inc["bbox_tl"].map(lambda v: isinstance(v, tuple))

    grid = strict_grid()

    # ---- discount calibration on the step15 anchors ----
    anchor_cells = pd.read_parquet(STEP15_CELLS)[["track_id", "n_cells"]]
    anchor_ids = {"ar15": "AR15", "ar23-02": "AR23-02", "ar30-01": "AR30-01", "ar40": "AR40", "ar41": "AR41", "ar42-02": "AR42-02", "ar59": "AR59", "ar9-03": "AR9-03", "fk006c": "FK006C", "fk008": "FK008"}
    anchor_rows = []
    for track, sid in anchor_ids.items():
        actual = int(anchor_cells.loc[anchor_cells["track_id"] == track, "n_cells"].iloc[0])
        bbox = parse_geometry(mb.loc[mb["surveyId"] == sid, "geometry"].iloc[0])
        outside = cells_outside_strict(grid, bbox) if bbox else 0
        anchor_rows.append({"surveyId": sid, "actual_new_cells": actual, "bbox_cells_outside_strict": outside, "ratio": actual / outside if outside else np.nan})
    anchors = pd.DataFrame(anchor_rows)
    # AR40's MBBDB bbox is a single-degree box whose cells are almost all
    # already strict (bbox_outside=4) — a degenerate anchor; drop anchors
    # with fewer than 100 bbox-outside cells before taking the median.
    sane = anchors[anchors["bbox_cells_outside_strict"] >= 100]
    discount = float(np.median(sane["ratio"]))

    # ---- per-cruise estimates ----
    # Upper bound: cells inside the (track or survey) bbox outside the strict
    # layer, capped by the sounding-count bound from compressed size.
    # Central estimate (used for value ranking): upper bound x strip discount.
    inc["gb"] = inc["bytes"] / 1e9
    rows_bound = inc["gb"] * ROWS_PER_GB
    upper_tl, upper_bbox = [], []
    for row in inc.itertuples():
        bound = rows_bound.loc[row.Index]
        if has_tl_bbox.loc[row.Index]:
            upper_tl.append(min(cells_outside_strict(grid, row.bbox_tl), bound))
            upper_bbox.append(np.nan)
        else:
            upper_tl.append(np.nan)
            upper_bbox.append(min(cells_outside_strict(grid, row.bbox_mb), bound) if isinstance(row.bbox_mb, tuple) else 0.0)
    inc["est_cells_tl_upper"] = pd.Series(upper_tl, index=inc.index)
    inc["est_cells_bbox_upper"] = pd.Series(upper_bbox, index=inc.index)
    inc["est_cells_upper"] = inc["est_cells_tl_upper"].fillna(inc["est_cells_bbox_upper"])
    density_bound = inc["gb"] * ANCHOR_CELLS_PER_GB
    inc["est_new_cells"] = np.minimum(inc["est_cells_upper"].astype(float) * discount, density_bound)
    orderable = (inc["gb"] > 0) & (inc["est_new_cells"] > 0)
    inc["orderable"] = orderable
    inc.loc[orderable, "value_cells_per_gb"] = inc.loc[orderable, "est_new_cells"] / inc.loc[orderable, "gb"]

    # ---- greedy selection with ship/decade seat caps ----
    # Primary key: value (est new cells per GB). Most cruises are
    # density-bound (tie at ANCHOR_CELLS_PER_GB); the tiebreak prefers
    # compact surveys (smaller bbox-cells-per-GB upper bound), which are more
    # likely to realize the anchor density than transit-dominated bboxes.
    pool = inc[orderable].copy()
    pool["upper_per_gb"] = pool["est_cells_upper"] / pool["gb"]
    pool = pool.sort_values(
        ["value_cells_per_gb", "upper_per_gb", "gb"], ascending=[False, True, True]
    ).reset_index(drop=True)

    def fill(ship_quota: int, decade_quota: int) -> list[int]:
        chosen: list[int] = []
        ship_count: dict[str, int] = {}
        decade_count: dict[int, int] = {}
        cum = 0.0
        for idx, row in pool.iterrows():
            if cum >= max(TIER_BYTES.values()):
                break
            ship = str(row["platform"])
            dec_key = int(row["decade"]) if pd.notna(row["decade"]) else -1
            if len(chosen) > 0 and (ship_count.get(ship, 0) >= ship_quota or decade_count.get(dec_key, 0) >= decade_quota):
                continue
            chosen.append(idx)
            ship_count[ship] = ship_count.get(ship, 0) + 1
            decade_count[dec_key] = decade_count.get(dec_key, 0) + 1
            cum += row["bytes"]
        return chosen

    uncapped = fill(ship_quota=10**9, decade_quota=10**9)
    n_target = len(uncapped)
    ship_quota = max(1, math.ceil(SHIP_CAP * n_target))
    decade_quota = max(1, math.ceil(DECADE_CAP * n_target))
    chosen = fill(ship_quota, decade_quota)
    for _ in range(3):
        if float(pool.loc[chosen, "bytes"].sum()) >= 0.9 * TIER_BYTES["C"] or len(chosen) == len(uncapped):
            break
        ship_quota = math.ceil(ship_quota * 1.2)
        decade_quota = math.ceil(decade_quota * 1.2)
        chosen = fill(ship_quota, decade_quota)

    selected = pool.loc[chosen].copy()
    selected["rank"] = range(1, len(selected) + 1)
    selected["cum_bytes"] = selected["bytes"].cumsum()
    selected["tier"] = np.select(
        [selected["cum_bytes"] <= TIER_BYTES["A"], selected["cum_bytes"] <= TIER_BYTES["B"]],
        ["A", "B"],
        default="C",
    )

    # ---- region annotation (bbox intersects which regions) ----
    def region_tags(bbox):
        if bbox is None:
            return ""
        tags = []
        for rid, (w, e, s, n) in REGIONS.items():
            if bbox[0] < e and bbox[2] > w and bbox[1] < n and bbox[3] > s:
                tags.append(rid)
        return ";".join(tags)
    selected["regions_touched"] = selected["bbox_mb"].map(region_tags)
    inc["regions_touched"] = inc["bbox_mb"].map(region_tags)

    # ---- write outputs ----
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    keep = ["surveyId", "platform", "year", "decade", "trackline_hit", "gb", "est_new_cells",
            "est_cells_upper", "est_cells_tl_upper", "est_cells_bbox_upper", "value_cells_per_gb", "regions_touched"]
    full = inc[keep].copy()
    full.to_parquet(OUT_DIR / "ranking_full.parquet", index=False)
    full.to_csv(OUT_DIR / "ranking_full.tsv", sep="\t", index=False)
    sel_cols = ["rank", "tier", "surveyId", "platform", "year", "decade", "trackline_hit", "gb", "est_new_cells", "value_cells_per_gb", "regions_touched"]
    selected[sel_cols].to_parquet(OUT_DIR / "order_list.parquet", index=False)
    for tier in ("A", "B", "C"):
        sub = selected[selected["tier"] == tier]
        sub[sel_cols].to_csv(OUT_DIR / f"order_tier_{tier}.tsv", sep="\t", index=False)
    anchors.to_csv(OUT_DIR / "discount_calibration.tsv", sep="\t", index=False)

    summary = {
        "mbdb_unique": len(mb),
        "increment": len(inc),
        "trackline_hit": int(inc["trackline_hit"].sum()),
        "trackline_bbox_resolved": int(has_tl_bbox.sum()),
        "orderable": int(orderable.sum()),
        "discount_median": discount,
        "n_uncapped_fill": n_target,
        "ship_quota": ship_quota,
        "decade_quota": decade_quota,
        "n_selected": len(selected),
        "selected_bytes": float(selected["bytes"].sum()),
        "selected_est_new_cells": float(selected["est_new_cells"].sum()),
        "tier_counts": {t: int((selected["tier"] == t).sum()) for t in ("A", "B", "C")},
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(anchors.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
