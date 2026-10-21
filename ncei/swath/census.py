#!/usr/bin/env python3
"""Stage 1 — file-format census of the COMPLETE raw_round2 cruises.

Reads ncei/derived/mb_round2/completeness_manifest.parquet (stage 0),
scans the complete cruise directories on disk, and tabulates file
counts and bytes by extension. Writes formats_manifest under
ncei/derived/mb_round2/. Read-only with respect to raw data.

Run from repo root:
    python -m ncei.swath census
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = REPO_ROOT / "ncei/raw_round2/platforms_tree"
COMP_PATH = REPO_ROOT / "ncei/derived/mb_round2/completeness_manifest.parquet"
OUT_DIR = REPO_ROOT / "ncei/derived/mb_round2"


def classify_ext(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(".part"):
        return ".part(stale)"
    if lowered.endswith(".all.mb58.gz"):
        return ".all.mb58.gz"
    if lowered.endswith(".all.gz"):
        return ".all.gz"
    if lowered.endswith(".mb58.gz"):
        return ".mb58.gz"
    if lowered.endswith(".raw.all.mb56.gz"):
        return ".raw.all.mb56.gz"
    if lowered.endswith(".mb56.gz"):
        return ".mb56.gz"
    if lowered.endswith(".mb57.gz"):
        return ".mb57.gz"
    if lowered.endswith(".mb21.gz"):
        return ".mb21.gz"
    if lowered.endswith(".gz"):
        return ".gz(no format suffix)"
    if lowered.endswith(".mb57"):
        return ".mb57"
    return "." + lowered.rsplit(".", 1)[-1] if "." in lowered else "(no ext)"


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(prog="python -m ncei.swath census", description=__doc__).parse_args(argv)
    comp = pd.read_parquet(COMP_PATH)
    complete = comp[comp["status"] == "complete"]["cruise"].tolist()

    rows = []
    for cruise in sorted(complete):
        stats: dict[str, list] = defaultdict(lambda: [0, 0])
        for f in (RAW_ROOT / cruise).rglob("*"):
            if not f.is_file() or f.name.endswith(".part"):
                continue
            ext = classify_ext(f.name)
            stats[ext][0] += 1
            stats[ext][1] += f.stat().st_size
        for ext, (n, b) in sorted(stats.items()):
            rows.append({"cruise": cruise, "format": ext, "n_files": n, "bytes": b})

    out = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pq_path = OUT_DIR / "formats_manifest.parquet"
    tmp = pq_path.with_suffix(".parquet.tmp")
    out.to_parquet(tmp, index=False)
    os.replace(tmp, pq_path)
    tsv_path = OUT_DIR / "formats_manifest.tsv"
    out.to_csv(tsv_path.with_suffix(".tsv.tmp"), sep="\t", index=False)
    os.replace(tsv_path.with_suffix(".tsv.tmp"), tsv_path)

    total = out.groupby("format").agg(n_files=("n_files", "sum"), bytes=("bytes", "sum")).sort_values("bytes", ascending=False)
    print("== complete cruises: format totals ==")
    print(total.to_string())
    print(f"\nmanifest: {pq_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
