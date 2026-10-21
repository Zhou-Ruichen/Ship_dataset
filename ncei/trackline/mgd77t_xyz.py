#!/usr/bin/env python3
"""Task E step 1 — convert the static-tree MGD77T corpus to xyz layout.

Reads every ncei/raw_round2/mgd77t_static/<SURVEY>/<survey>.m77t and writes
ncei/raw_round2/mgd77t_static_xyz/<track_id>.xyz in the exact layout the
existing singlebeam pipeline consumes (header LON,LAT,CORR_DEPTH; the 03
stage's read_xyz_full auto-detects the header).

MGD77T column handling (verified against the 21 headered files in the
corpus; headerless files share the same 27-column standard layout —
SURVEY_ID, TIMEZONE, DATE, TIME, LAT, LON, POS_TYPE, NAV_QUALCO,
BAT_TTIME, CORR_DEPTH, ...):
  LAT  = field 5, LON = field 6, CORR_DEPTH = field 10 (1-based).
Depth policy (corpus scan 2026-09, 150,562,054 rows):
  - blank CORR_DEPTH -> NaN (kept for geometry; includes the 160,788
    TTIME-only rows, which are NOT converted — no velocity assumption);
  - |value| >= 99999 -> NaN (the only sentinel band found, 8,102 rows);
  - everything else verbatim (sign diagnosis is downstream, per track).
Timezone is deliberately ignored: the xyz layout carries no time column.

Run from repo root:
    python -m ncei.trackline mgd77t-xyz [--surveys A B ...]
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "ncei/raw_round2/mgd77t_static"
OUT_ROOT = REPO_ROOT / "ncei/raw_round2/mgd77t_static_xyz"
MANIFEST_OUT = OUT_ROOT / "conversion_manifest.parquet"

SENTINEL_ABS = 99999.0
CHUNK = 500_000


def convert_one(m77t: Path, out_path: Path) -> dict:
    track_id = m77t.stem
    n_rows = n_depth = n_sentinel = n_blank = n_ttime_only = 0
    tmp = out_path.with_suffix(".xyz.tmp")
    with m77t.open("r", encoding="utf-8", errors="replace") as src, tmp.open("w", encoding="utf-8") as dst:
        dst.write("LON,LAT,CORR_DEPTH\n")
        first = src.readline()
        if not first.rstrip("\n").split("\t")[0].strip().upper() == "SURVEY_ID":
            src.seek(0)
        for line in src:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 10 or parts[0].strip().upper() == "SURVEY_ID":
                continue
            lat = parts[4].strip()
            lon = parts[5].strip()
            depth = parts[9].strip()
            if lon == "" or lat == "":
                continue
            n_rows += 1
            if depth == "":
                n_blank += 1
                if parts[8].strip() != "":
                    n_ttime_only += 1
                dst.write(f"{lon},{lat},\n")
                continue
            try:
                v = float(depth)
            except ValueError:
                n_blank += 1
                dst.write(f"{lon},{lat},\n")
                continue
            if abs(v) >= SENTINEL_ABS:
                n_sentinel += 1
                dst.write(f"{lon},{lat},\n")
                continue
            n_depth += 1
            dst.write(f"{lon},{lat},{v}\n")
    os.replace(tmp, out_path)
    return {
        "track_id": track_id, "survey": m77t.parent.name,
        "m77t_path": str(m77t.relative_to(REPO_ROOT)),
        "xyz_path": str(out_path.relative_to(REPO_ROOT)),
        "n_rows": n_rows, "n_depth_finite": n_depth,
        "n_blank_depth": n_blank, "n_ttime_only": n_ttime_only,
        "n_sentinel": n_sentinel,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ncei.trackline mgd77t-xyz", description=__doc__)
    parser.add_argument("--surveys", nargs="*", default=None)
    args = parser.parse_args(argv)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    files = sorted(SRC_ROOT.glob("*/*.m77t"))
    if args.surveys:
        keep = {s.lower() for s in args.surveys}
        files = [f for f in files if f.parent.name.lower() in keep]
    rows = []
    for i, m77t in enumerate(files):
        out_path = OUT_ROOT / f"{m77t.stem}.xyz"
        rows.append(convert_one(m77t, out_path))
        if (i + 1) % 100 == 0:
            print(f"{i+1}/{len(files)}")
    manifest = pd.DataFrame(rows)
    tmp = MANIFEST_OUT.with_suffix(".parquet.tmp")
    manifest.to_parquet(tmp, index=False)
    os.replace(tmp, MANIFEST_OUT)
    manifest.to_csv(OUT_ROOT / "conversion_manifest.tsv", sep="\t", index=False)
    print(f"{len(manifest)} tracks; rows={int(manifest.n_rows.sum()):,}, "
          f"depth-finite={int(manifest.n_depth_finite.sum()):,}, "
          f"sentinel={int(manifest.n_sentinel.sum()):,}, "
          f"ttime-only={int(manifest.n_ttime_only.sum()):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
