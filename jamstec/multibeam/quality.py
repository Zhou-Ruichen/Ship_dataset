"""Run the existing JAMSTEC quality stages in their fixed order."""

from __future__ import annotations

import argparse
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m jamstec.multibeam quality")
    parser.add_argument("--run-label", choices=("sample", "full"), default="sample")
    parser.add_argument("--cell-size", choices=("1min",), default="1min")
    parser.add_argument("--sample-n-files", type=int)
    parser.add_argument("--limit-files", type=int)
    parser.add_argument("--file-cells-manifest", type=Path, help="Optional cell-closure manifest for 06c.")
    parser.add_argument("--original-cells", type=Path, help="Optional matching original-cell table for 06c/06d.")
    parser.add_argument("--confirm-full", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--estimate-only", action="store_true")
    args = parser.parse_args(argv)
    if args.run_label == "full" and not args.confirm_full:
        parser.error("--run-label=full requires --confirm-full")

    from . import compare_cells, extreme_bias, file_quality, overlap, qcfiltered_cells

    common = ["--run-label", args.run_label, "--cell-size", args.cell_size]
    if args.confirm_full:
        common.append("--confirm-full")
    if args.overwrite:
        common.append("--overwrite")
    if args.estimate_only:
        common.append("--estimate-only")
    overlap_args = list(common)
    if args.sample_n_files is not None:
        overlap_args.extend(["--sample-n-files", str(args.sample_n_files)])
    if args.limit_files is not None:
        overlap_args.extend(["--limit-files", str(args.limit_files)])
    overlap.main(overlap_args)
    extreme_bias.main(common)

    # These stages historically have one output layout. Their inputs may be
    # explicit cell-closure tables; no scientific rules are selected here.
    quality_args = ["--overwrite"] if args.overwrite else []
    if args.estimate_only:
        quality_args.append("--dry-run")
    file_quality.main(quality_args)
    qc_args = ["--overwrite"] if args.overwrite else []
    if args.estimate_only:
        qc_args.append("--estimate-only")
    if args.file_cells_manifest:
        qc_args.extend(["--file-cells-manifest", str(args.file_cells_manifest)])
    if args.original_cells:
        qc_args.extend(["--original-cells", str(args.original_cells)])
    qcfiltered_cells.main(qc_args)
    if not args.estimate_only:
        compare_args = ["--overwrite"] if args.overwrite else []
        if args.original_cells:
            compare_args.extend(["--original-cells", str(args.original_cells)])
        compare_cells.main(compare_args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
