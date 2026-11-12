"""Command-line entry point for streaming swath products."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pyarrow as pa

from _common.file_io import atomic_write_parquet

from . import census, coverage, exclusions, pipeline, points, sources
from .decode import ENVIRONMENT_RELATIVE


def parser() -> argparse.ArgumentParser:
    main = argparse.ArgumentParser(prog="python -m ncei.swath", description=__doc__)
    commands = main.add_subparsers(dest="command", required=True)
    for name in ("census", "run", "points"):
        command = commands.add_parser(name)
        command.add_argument("--raw-root", type=Path, action="append", help="Repeat for multiple platform trees.")
        command.add_argument("--output-root", type=Path)
        command.add_argument("--data-root", type=Path, default=sources.ROOT, help="Existing data checkout for MB-System and historical tables.")
        command.add_argument("--ledger", type=Path)
        if name == "points":
            command.add_argument("--cruise", required=True)
            command.add_argument("--files", nargs="+", default=[], help="Source names, paths, or historical filekeys.")
            command.add_argument("--bbox", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
        else:
            command.add_argument("--cruises", nargs="+", help="Default: all downloaded platform-tree cruises.")
        if name == "run":
            command.add_argument("--resume", action="store_true")
            command.add_argument("--workers", type=int, default=1)
        if name in {"run", "points"}:
            group = command.add_mutually_exclusive_group()
            group.add_argument("--exclude-pings", type=Path)
            group.add_argument("--no-exclusions", action="store_true", help="Omit the 19 reviewed pings for numerical comparison.")
    command = commands.add_parser("coverage")
    command.add_argument("--output-root", type=Path)
    command.add_argument("--data-root", type=Path, default=sources.ROOT)
    command.add_argument("--strict-path", type=Path)
    command.add_argument("--regions-yaml", type=Path, default=coverage.REGIONS_YAML)
    return main


def main(argv: list[str] | None = None) -> int:
    ap = parser()
    args = ap.parse_args(argv)
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    data_root = args.data_root.resolve()
    output = (args.output_root or data_root / "ncei/derived/swath_rebuild_20261112").resolve()
    if args.command == "coverage":
        return coverage.coverage_stats(output, args.strict_path or data_root /
                                       "ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet",
                                       args.regions_yaml)
    if args.command == "run" and args.workers < 1:
        ap.error("--workers must be positive")
    roots = [root.resolve() for root in args.raw_root or [data_root / "ncei/raw_round2/platforms_tree", sources.RAW_ROOTS[1]]]
    ledger = (args.ledger or data_root / "ncei/manifests/round2_download_log.parquet").resolve()
    downloaded = sources.downloaded_cruises(ledger)
    requested = [args.cruise] if args.command == "points" else args.cruises
    targets = sorted(downloaded) if not requested else list(dict.fromkeys(requested))
    if not targets or not set(targets) <= downloaded or any(Path(c).name != c or c in {".", ".."} for c in targets):
        ap.error("cruises must be platform-tree IDs with status=ok in the download ledger")
    if args.command == "points" and args.bbox:
        west, south, east, north = args.bbox
        if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            ap.error("--bbox requires -180 <= WEST <= EAST <= 180 and -90 <= SOUTH <= NORTH <= 90")
    if not requested and "RR0913" in targets:
        targets.remove("RR0913")
        targets.insert(0, "RR0913")
    directories = sources.cruise_directories(roots, set(targets), downloaded)
    if args.command == "census":
        rows = []
        for cruise in targets:
            inputs = sources.discover(cruise, directories[cruise], data_root / "ncei/derived/mb_round2")
            rows.extend(census.census_rows(cruise, inputs))
        frame = pd.DataFrame(rows)
        atomic_write_parquet(frame, output / "census.parquet")
        print(frame.groupby(["mb_format", "supported"], dropna=False)[["n_files", "raw_bytes"]].sum().to_string())
        return 0
    exclusion_path = args.exclude_pings.resolve() if args.exclude_pings else None
    if args.command == "points":
        if exclusion_path is None and not args.no_exclusions:
            exclusion_path = output / exclusions.EXCLUSION_TABLE
            if not exclusion_path.exists():
                exclusions.write_default(exclusion_path, data_root / "ncei/derived/processing_revision_20261025/swath")
        inputs = sources.discover(args.cruise, directories[args.cruise], data_root / "ncei/derived/mb_round2")
        path = output / "points_checked" / f"{args.cruise}.parquet"
        points.write_points(inputs, path, set(args.files), args.bbox, exclusions.load(exclusion_path), data_root / ENVIRONMENT_RELATIVE)
        print(path)
        return 0
    invalid_pings = pipeline.prepare_run(output, roots, requested, args.resume, exclusion_path,
                                         not args.no_exclusions and exclusion_path is None, ledger, data_root)
    return pipeline.run(output, targets, directories, invalid_pings, args.workers, args.resume, data_root)
