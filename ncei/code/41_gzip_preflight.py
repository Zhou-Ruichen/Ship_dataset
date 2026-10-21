#!/usr/bin/env python3
"""Step 17 stage 0 — gzip integrity preflight for raw_round2 swath files.

Every *.gz under ncei/raw_round2/platforms_tree/ that has not already been
successfully consumed by the extraction pipeline (status ok / skipped_* in
the per-cruise extraction manifests) is verified with `gzip -t` from the
sealed mbsystem environment. Results land in
ncei/derived/mb_round2/gzip_preflight.parquet (+ .tsv):
  rc == 0            -> ok (extractable)
  rc != 0            -> corrupt (fail-closed; recorded, never ingested)
Files already verified by prior extraction are recorded as
previously_verified so the manifest is a complete view without re-hashing
1.4 TB of known-good data.

Run from repo root:
    python ncei/code/41_gzip_preflight.py [--workers 12]
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = REPO_ROOT / "ncei/raw_round2/platforms_tree"
OUT_DIR = REPO_ROOT / "ncei/derived/mb_round2"
GZIP = REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/environments/mbsystem-5.8.3beta16-1d9a52ce/bin/gzip"
OUT_PATH = OUT_DIR / "gzip_preflight.parquet"


def previously_consumed() -> set[str]:
    seen: set[str] = set()
    for manifest in glob.glob(str(OUT_ROOT := REPO_ROOT / "ncei/derived/mb_round2") + "/*/extraction_manifest.parquet"):
        df = pd.read_parquet(manifest, columns=["relpath", "status"])
        seen.update(df.loc[df["status"].isin(["ok", "skipped_exists", "skipped_format_unknown", "skipped_format_unsupported"]), "relpath"])
    return seen


def check_one(rel: str) -> dict:
    path = RAW_ROOT / rel
    result = subprocess.run([str(GZIP), "-t", str(path)], capture_output=True, text=True, check=False)
    return {
        "relpath": rel,
        "bytes": path.stat().st_size,
        "gzip_t_rc": result.returncode,
        "gzip_t_msg": (result.stderr.strip().splitlines() or [""])[-1][:200],
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    all_files = sorted(
        str(p.relative_to(RAW_ROOT)) for p in RAW_ROOT.rglob("*.gz") if not p.name.endswith(".part")
    )
    done = previously_consumed()
    todo = [f for f in all_files if f not in done]
    print(f"{len(all_files)} gz files; {len(done)} previously consumed; {len(todo)} to verify", flush=True)

    import multiprocessing as mp
    with mp.Pool(args.workers) as pool:
        results = pool.map(check_one, todo, chunksize=8)
    for rel in sorted(done):
        results.append({"relpath": rel, "bytes": -1, "gzip_t_rc": 0,
                        "gzip_t_msg": "previously_verified_by_extraction", "checked_at_utc": ""})
    out = pd.DataFrame(results).sort_values("relpath").reset_index(drop=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".parquet.tmp")
    out.to_parquet(tmp, index=False)
    os.replace(tmp, OUT_PATH)
    out.to_csv(OUT_PATH.with_suffix(".tsv"), sep="\t", index=False)
    bad = out[(out.gzip_t_rc != 0) & (out.gzip_t_msg != "previously_verified_by_extraction")]
    print(f"verified {len(todo)}; corrupt {len(bad)}", flush=True)
    if len(bad):
        print(bad[["relpath", "gzip_t_msg"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
