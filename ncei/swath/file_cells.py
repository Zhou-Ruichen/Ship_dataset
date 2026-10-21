#!/usr/bin/env python3
"""Stage 3 — L2 1-arcmin file cells for the processed mb_round2 cruises (any mb format).

Reuses ncei/trackline/file_cells.py::aggregate_track_file
(imported, not copied) — the NCEI-branch canonical aggregation with the
same cell_id convention as JAMSTEC 04a (see the 07 docstring: "Cell-id
convention (per ... + JAMSTEC 04a_make_multibeam_file_cells.py)"). The
07 implementation is preferred over a literal 04a import because it
produces the spec §1.2 23-column multibeam_ncei contract exactly and
with exact (non-approximate) per-cell statistics.

Run from repo root:
    python -m ncei.swath file-cells [--cruises AR40 ...]
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ncei.trackline import file_cells as agg

REPO_ROOT = Path(__file__).resolve().parents[2]

from _common.file_io import atomic_write_parquet

OUT_ROOT = REPO_ROOT / "ncei/derived/mb_round2"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ncei.swath file-cells", description=__doc__)
    parser.add_argument("--cruises", nargs="*", default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    cruises = [p.name for p in sorted(OUT_ROOT.iterdir()) if (p / "points_checked").is_dir()]
    if args.cruises:
        cruises = [c for c in cruises if c in set(args.cruises)]
    if not cruises:
        print("no cruises with points_checked outputs; run stage 2 first")
        return 1

    rows = []
    for cruise in cruises:
        track_id = cruise.lower()
        shards = sorted((OUT_ROOT / cruise / "points_checked").glob(f"{track_id}__mb*.parquet"))
        if not shards:
            print(f"skip {cruise}: no points_checked shard")
            continue
        input_path = shards[0]
        tag = input_path.stem.split("__", 1)[1]  # e.g. mb58 / mb21
        output_path = OUT_ROOT / cruise / "file_cells_1min" / input_path.name
        row = agg.aggregate_track_file(
            input_path=input_path,
            output_path=output_path,
            track_id=track_id,
            source_type=f"ncei_{tag}",
            source_completeness=f"{tag}_only",
            instrument_class_pred="multibeam",
            branch="multibeam_ncei",
            manual_review_flag=False,
            overwrite=args.overwrite,
        )
        rows.append(row)
        print(
            f"{cruise}: {row['n_cells']:,} cells, {row['n_points_pass_total']:,} pass points, "
            f"dup {row['duplicate_ratio_overall']:.4f}, {row['runtime_seconds']:.1f}s"
        )

    manifest = pd.DataFrame(rows)
    manifest_path = OUT_ROOT / "file_cells_manifest.parquet"
    atomic_write_parquet(manifest, manifest_path)
    manifest.to_csv(OUT_ROOT / "file_cells_manifest.tsv", sep="\t", index=False)
    print(f"manifest: {manifest_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
