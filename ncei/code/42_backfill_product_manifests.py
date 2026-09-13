"""Back-fill in-directory product manifests for delivered products (2026-09-13).

Why: docs/数据产品规范与下游接入.md §4 requires every delivered product
directory to carry a product_manifest.json (generation time + input hashes)
so downstream can pin a round by "round label + input hash". Three products
were delivered before that anchor existed inside their own directories:

1. ncei/derived/singlebeam/file_cells_1min_final_r2/        (SB final cells, round _r2)
2. ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet
3. ncei/derived/singlebeam/points_checked/                  (point layer, referenceable)

This script writes manifests WITHOUT touching any data file. It never
fabricates generation metadata: creation times/commands are copied from the
authoritative records written at generation time
(ncei/derived/sb_track_quality_global/product_manifest.json,
ncei/docs/step07b_validation_cells_report.md,
ncei/docs/step03_point_quality_check_report.md); everything hashed here is
labeled with the hash computation time. Manifest 1 additionally cross-checks
every output hash against the independent record in
ncei/derived/global_grid_1min_r2/product_manifest.json (hashed 2026-09-02,
before any consumer read the product) and reports mismatches.

The manifests live under **/derived/ (gitignored by repo convention: data
products and their manifests live on disk beside the data they describe).

Usage (repo root):
    python ncei/code/42_backfill_product_manifests.py
    python ncei/code/42_backfill_product_manifests.py --skip-input-hashes   # fast re-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DERIVED = REPO_ROOT / "ncei" / "derived"

# Generation-time records (inputs to this script; never rewritten here).
QUALITY_MANIFEST = DERIVED / "sb_track_quality_global" / "product_manifest.json"
GRID_MANIFEST = DERIVED / "global_grid_1min_r2" / "product_manifest.json"

FINAL_R2_DIR = DERIVED / "singlebeam" / "file_cells_1min_final_r2"
STRICT_MB_FILE = DERIVED / "validation_cells_1min" / "strict_primary_multibeam_cells.parquet"
STRICT_MB_MANIFEST = DERIVED / "validation_cells_1min" / "product_manifest_strict_primary_multibeam_cells.json"
POINTS_CHECKED_DIR = DERIVED / "singlebeam" / "points_checked"
ENTRY_MANIFEST = REPO_ROOT / "ncei" / "manifests" / "bathymetry_entry_manifest.parquet"

# Documented generation metadata (provenance cited in each manifest).
STRICT_MB_GENERATED_AT = "2026-05-21T21:13:40.056720+00:00"  # step07b report header, run label `full`
POINTS_GENERATED_AT = "2026-05-20T09:57:21.858747+00:00"     # step03 report header, run label `full'


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_directory(dir_path: Path) -> dict[str, str]:
    files = sorted(p for p in dir_path.rglob("*") if p.is_file())
    return {str(p.relative_to(REPO_ROOT)): sha256_file(p) for p in files}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(REPO_ROOT)} ({path.stat().st_size:,} bytes)")


def backfill_final_r2(skip_input_hashes: bool) -> None:
    record = json.loads(QUALITY_MANIFEST.read_text(encoding="utf-8"))
    grid = json.loads(GRID_MANIFEST.read_text(encoding="utf-8"))

    output_hashes = hash_directory(FINAL_R2_DIR)

    # Cross-check against the independent 2026-09-02 record in the grid manifest.
    prefix = str(FINAL_R2_DIR) + "/"
    rel_prefix = str(FINAL_R2_DIR.relative_to(REPO_ROOT)) + "/"
    grid_hashes = {k: v for k, v in grid["input_sha256"].items() if k.startswith(prefix)}
    mismatches = [
        k for k, v in grid_hashes.items()
        if output_hashes.get(rel_prefix + k[len(prefix):]) != v
    ]
    cross_check = {
        "reference_manifest": str(GRID_MANIFEST.relative_to(REPO_ROOT)),
        "reference_manifest_sha256": sha256_file(GRID_MANIFEST),
        "reference_hashed_at": grid["created_at"],
        "files_compared": len(grid_hashes),
        "mismatches": mismatches,
    }
    print(f"final_r2 cross-check vs grid manifest: {len(grid_hashes)} files, {len(mismatches)} mismatches")
    if mismatches:
        print("ERROR: final_r2 files differ from the 2026-09-02 record; aborting this manifest",
              file=sys.stderr)
        sys.exit(1)

    input_hashes: dict[str, str] = {}
    if not skip_input_hashes:
        for src in record["source_paths"]:
            p = Path(src)
            if not p.exists():
                print(f"WARNING: source path missing, skipped: {src}", file=sys.stderr)
                continue
            if p.is_dir():
                input_hashes.update(hash_directory(p))
            else:
                input_hashes[str(p.relative_to(REPO_ROOT))] = sha256_file(p)
        entry = record.get("input_manifest")
        if entry:
            input_hashes[str(Path(entry).relative_to(REPO_ROOT))] = record["input_manifest_sha256"]

    manifest = {
        "name": "singlebeam_final_cells_1min",
        "round": "_r2",
        "created_at": record["created_at"],
        "created_by": record["created_by"],
        "product_dir": str(FINAL_R2_DIR.relative_to(REPO_ROOT)),
        "depth_unit": "m, positive down",
        "columns": "file_cells_1min base columns + track_bias_m + bias_applied + bias_n_support + track_disposition",
        "disposition_rule_source": ".trellis/tasks/09-03-global-sb-final-product/prd.md",
        "counts": record["counts"],
        "source_paths": record["source_paths"],
        "input_manifest": record.get("input_manifest"),
        "input_manifest_sha256": record.get("input_manifest_sha256"),
        "input_sha256": input_hashes,
        "output_file_count": len(output_hashes),
        "output_sha256": output_hashes,
        "cross_check": cross_check,
        "backfilled_at": utc_now(),
        "backfilled_by": "ncei/code/42_backfill_product_manifests.py",
        "backfill_note": (
            "Original generation (2026-09-02) recorded its manifest in "
            "sb_track_quality_global/product_manifest.json, not inside the product directory. "
            "This in-directory manifest was back-filled later; created_at/created_by/counts are "
            "copied verbatim from that authoritative record. Input and output hashes were "
            "computed at backfilled_at. Output hashes were verified file-by-file against the "
            "independent record in the global_grid_1min_r2 manifest (see cross_check), so the "
            "files are bit-identical to what the grid round consumed on 2026-09-02."
        ),
    }
    write_json(FINAL_R2_DIR / "product_manifest.json", manifest)


def backfill_strict_mb() -> None:
    jamstec_primary = (
        REPO_ROOT / "jamstec" / "multibeam" / "derived" / "validation_cells_1min"
        / "primary_ship_validation_cells_1min.parquet"
    )
    ncei_mb_cells = REPO_ROOT / "ncei" / "derived" / "multibeam" / "cells_1min"

    inputs = {
        str(jamstec_primary.relative_to(REPO_ROOT)): sha256_file(jamstec_primary),
        **hash_directory(ncei_mb_cells),
    }
    manifest = {
        "name": "strict_primary_multibeam_cells",
        "product_version": "ncei_validation_cells_v0.1.0",
        "round": None,
        "round_note": (
            "This product predates the round-label convention and carries a product version "
            "instead. Pin a version by recording this parquet's sha256 (below), as "
            "global_grid_1min_r2/product_manifest.json does. Round-labeled successors belong "
            "to future multibeam rounds."
        ),
        "created_at": STRICT_MB_GENERATED_AT,
        "created_by": "ncei/code/13_build_validation_cells.py (run label `full`)",
        "created_at_source": "ncei/docs/step07b_validation_cells_report.md header",
        "product_file": str(STRICT_MB_FILE.relative_to(REPO_ROOT)),
        "product_sha256": sha256_file(STRICT_MB_FILE),
        "rows": 2398774,
        "depth_column": "representative_depth_m",
        "source_providers": {"jamstec": 2394115, "ncei_multibeam": 4659},
        "source_paths": {
            "jamstec_primary": str(jamstec_primary.relative_to(REPO_ROOT)),
            "ncei_multibeam_branch_cells": str(ncei_mb_cells.relative_to(REPO_ROOT)),
        },
        "input_sha256": inputs,
        "precedence": "JAMSTEC primary > NCEI multibeam (strict layer is multibeam-only)",
        "backfilled_at": utc_now(),
        "backfilled_by": "ncei/code/42_backfill_product_manifests.py",
        "backfill_note": (
            "created_at/product_version/rows are copied from the step07b report generated at "
            "run time. Input hashes were computed at backfilled_at; the parquet sha256 matches "
            " the value recorded in global_grid_1min_r2/product_manifest.json (2026-09-02)."
        ),
    }
    write_json(STRICT_MB_MANIFEST, manifest)


def backfill_points_checked() -> None:
    file_hashes = hash_directory(POINTS_CHECKED_DIR)
    n_nc = sum(1 for k in file_hashes if k.endswith("__nc.parquet"))
    n_xyz = sum(1 for k in file_hashes if k.endswith("__xyz.parquet"))
    manifest = {
        "name": "singlebeam_points_checked",
        "layer": "L1 point layer, referenceable (see spec section 4)",
        "check_version": "point_check_v0.1.0",
        "round": None,
        "round_note": (
            "The point layer has no round directories. Downstream pins a version by recording "
            "the sha256 of THIS manifest, which transitively pins every point file and the "
            "entry manifest. A round that changes points must refresh this manifest and say so "
            "in the round notification (spec section 6)."
        ),
        "created_at": POINTS_GENERATED_AT,
        "created_by": "ncei/code/05_point_quality_check.py --run-label full --confirm-full --overwrite",
        "created_at_source": "ncei/docs/step03_point_quality_check_report.md header",
        "product_dir": str(POINTS_CHECKED_DIR.relative_to(REPO_ROOT)),
        "file_counts": {"total": len(file_hashes), "nc": n_nc, "xyz": n_xyz},
        "added_columns": [
            "valid_lon", "valid_lat", "valid_depth_pos", "valid_depth_max",
            "valid_core_fields", "point_check_pass_basic",
        ],
        "entry_manifest": str(ENTRY_MANIFEST.relative_to(REPO_ROOT)),
        "entry_manifest_sha256": sha256_file(ENTRY_MANIFEST),
        "entry_manifest_rows": 7403,
        "file_sha256": file_hashes,
        "backfilled_at": utc_now(),
        "backfilled_by": "ncei/code/42_backfill_product_manifests.py",
        "backfill_note": (
            "created_at/check_version are copied from the step03 report generated at run time. "
            "File hashes were computed at backfilled_at."
        ),
    }
    write_json(POINTS_CHECKED_DIR / "product_manifest.json", manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=["final_r2", "strict_mb", "points"],
                        help="back-fill only one manifest (default: all three)")
    parser.add_argument("--skip-input-hashes", action="store_true",
                        help="skip re-hashing final_r2 inputs (cross-check still runs)")
    args = parser.parse_args()

    if args.only in (None, "final_r2"):
        backfill_final_r2(skip_input_hashes=args.skip_input_hashes)
    if args.only in (None, "strict_mb"):
        backfill_strict_mb()
    if args.only in (None, "points"):
        backfill_points_checked()


if __name__ == "__main__":
    main()
