"""Command line entry point for the unified round-2 downloader."""

import argparse
import json
import time
from pathlib import Path

from . import DEFAULT_CATALOG, DEFAULT_LOG, DEFAULT_PROXIES, DEFAULT_RAW, DEFAULT_WORK, GIB
from .download import diff, fetch
from .inventory import inventory, listing_failures, load_plan, tree_items
from .log import merge
from .transport import DiskFloorError, Transport, check_space
from .verify import verify


def parser():
    ap = argparse.ArgumentParser(
        prog="python -m ncei.download",
        description="Inventory, fetch, merge, and verify NCEI round-2 files.")
    ap.add_argument("command", choices=["inventory", "diff", "fetch", "merge", "verify", "run"])
    ap.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG,
                    help="survey catalog TSV for platforms_tree")
    ap.add_argument("--plan", type=Path,
                    help="URL plan or copied parquet log for r2r/m77t_static")
    ap.add_argument("--channel", choices=["platforms_tree", "r2r", "m77t_static"],
                    default="platforms_tree")
    ap.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--work", type=Path, default=DEFAULT_WORK)
    ap.add_argument("--out", type=Path, help="verification output directory")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--inventory-workers", type=int, default=8)
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--proxies", default=",".join(DEFAULT_PROXIES),
                    help="comma-separated proxies; empty string for direct access")
    ap.add_argument("--tag", default="ncei-download")
    ap.add_argument("--disk-floor-gb", type=float, default=400)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--gzip", default="gzip")
    ap.add_argument("--extraction-dir", type=Path)
    ap.add_argument("--max-rounds", type=int, default=0,
                    help="run limit; zero repeats until complete or disk floor")
    ap.add_argument("--interval", type=float, default=5)
    return ap


def get_items(args, transport, *, enumerate_remote=False):
    if args.channel == "platforms_tree":
        if enumerate_remote:
            trees = inventory(args.catalog, args.work, transport,
                              args.inventory_workers, args.refresh)
        else:
            trees = json.loads((args.work / "trees.json").read_text())
        return trees, tree_items(trees)
    if not args.plan:
        raise SystemExit(f"--plan is required for {args.channel}; remote enumeration is not implemented")
    return None, load_plan(args.plan, args.channel)


def report_errors(trees):
    errors = listing_failures(trees) if trees is not None else {}
    if errors:
        print(f"inventory: {len(errors)} failed surveys: {list(errors)[:8]}", flush=True)
    return errors


def main(argv=None):
    ap = parser()
    args = ap.parse_args(argv)
    if min(args.workers, args.inventory_workers, args.attempts) < 1:
        ap.error("worker counts and attempts must be positive")
    if min(args.disk_floor_gb, args.interval, args.max_rounds) < 0:
        ap.error("disk floor, interval, and max rounds cannot be negative")
    transport = Transport([p.strip() for p in args.proxies.split(",") if p.strip()] or [""])
    args.work.mkdir(parents=True, exist_ok=True)
    floor = int(args.disk_floor_gb * GIB)

    def download(todo):
        return fetch(todo, args.raw, args.work, transport, workers=args.workers,
                     attempts=args.attempts, tag=args.tag, min_free_bytes=floor)

    if args.command == "inventory":
        if args.channel != "platforms_tree":
            raise SystemExit("inventory is only implemented for platforms_tree")
        trees = inventory(args.catalog, args.work, transport, args.inventory_workers, args.refresh)
        print(f"inventory: {len(trees)} surveys, {sum(len(t['files']) for t in trees.values() if t)} files")
        return int(bool(report_errors(trees)))
    if args.command == "diff":
        trees, items = get_items(args, transport)
        diff(items, args.raw, args.work)
        return int(bool(report_errors(trees)))
    if args.command == "fetch":
        if args.plan:
            todo = load_plan(args.plan, args.channel)
        else:
            todo = json.loads((args.work / "todo.json").read_text())
        return int(download(todo)["failed"] > 0)
    if args.command == "merge":
        merge(args.work, args.log)
        return 0
    if args.command == "verify":
        if args.channel != "platforms_tree":
            raise SystemExit("verify completeness is only implemented for platforms_tree")
        trees = json.loads((args.work / "trees.json").read_text())
        out = args.out or args.work / "verify"
        return int(not verify(trees, args.raw, out, log_path=args.log, workers=args.workers,
                              gzip_executable=args.gzip, extraction_dir=args.extraction_dir))
    if args.command == "run":
        round_number = 0
        # Recover successful records left by an interrupted 41 or fetch pass.
        merge(args.work, args.log)
        while True:
            check_space(args.raw, floor)
            round_number += 1
            trees, items = get_items(args, transport, enumerate_remote=True)
            errors = report_errors(trees)
            todo = diff(items, args.raw, args.work)
            if not todo and not errors:
                print("run: complete; no pending files or failed inventories", flush=True)
                return 0
            if todo:
                try:
                    download(todo)
                finally:
                    merge(args.work, args.log)
            if args.max_rounds and round_number >= args.max_rounds:
                # Diff again so a successful last batch can finish at the limit.
                remaining = diff(items, args.raw, args.work)
                return int(bool(remaining or errors))
            time.sleep(args.interval)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DiskFloorError as exc:
        raise SystemExit(str(exc))
