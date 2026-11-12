"""Rebuild or extract a batch of cruises into a separate release directory."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from _common.file_io import atomic_write_parquet, atomic_write_text, atomic_write_tsv
from ncei.trackline import file_cells
from . import coverage, extract, manifest_fragment

NAVIGATION_POLICY = "basic_native_good_valid_ping_navigation"


def write_json(value: dict, path: Path) -> None:
    atomic_write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", path)


def input_manifest(cruise: str, input_root: Path, reextract: bool) -> pd.DataFrame:
    path = input_root / cruise / "extraction_manifest.parquet"
    if path.exists():
        manifest = pd.read_parquet(path)
    elif reextract:
        candidates = [extract.RAW_ROOT / cruise, *sorted(extract.RAW_ROOT.glob(f"*/{cruise}"))]
        directories = [p for p in candidates if p.is_dir()]
        if len(directories) != 1:
            raise ValueError(f"{cruise}: expected one raw source directory, got {directories}")
        files = sorted(directories[0].rglob("*.gz"))
        if not files:
            raise ValueError(f"{cruise}: no gzip source files")
        rows = []
        for ordinal, path in enumerate(files):
            rel = path.relative_to(extract.RAW_ROOT)
            fmt, note = extract.resolve_mb_format(rel)
            rows.append({
                "file_ordinal": ordinal, "relpath": rel.as_posix(),
                "mb_format": fmt, "format_note": note,
            })
        manifest = pd.DataFrame(rows)
    else:
        raise FileNotFoundError(path)
    _, manifest = manifest_fragment.resolve_source_paths(cruise, manifest)
    return manifest


def process_cruise(
    cruise: str, input_root: Path, output_root: Path, reextract: bool, resume: bool,
    selection_policy: str = "basic_native_good", workers: int = 1,
) -> dict:
    destination = output_root / cruise
    summary_path = destination / "extraction_summary.json"
    out_manifest = destination / "extraction_manifest.parquet"
    if resume and summary_path.exists():
        summary = json.loads(summary_path.read_text())
        raw = extract.REPO_ROOT / summary["points_raw_path"]
        checked = extract.REPO_ROOT / summary["points_checked_path"]
        if not (raw.is_file() and checked.is_file() and out_manifest.is_file()):
            raise FileNotFoundError(f"{cruise}: incomplete saved L1 checkpoint")
        if pq.read_metadata(checked).num_rows != summary["n_rows"]:
            raise ValueError(f"{cruise}: L1 row count differs from its checkpoint")
        if "native_quality_state" not in pq.read_schema(checked).names:
            raise ValueError(f"{cruise}: L1 lacks native quality")
    else:
        manifest = input_manifest(cruise, input_root, reextract)
        staging = input_root / cruise / "_staging"
        if reextract:
            rows = []
            records = manifest.to_dict("records")
            tasks = [(cruise, record, output_root) for record in records]
            if workers == 1:
                results = map(extract_record, tasks)
                for row in results:
                    rows.append(row)
                    print(f"{cruise} file {len(rows)}/{len(tasks)}: {row['status']}", flush=True)
            else:
                with ProcessPoolExecutor(max_workers=workers) as pool:
                    for row in pool.map(extract_record, tasks):
                        rows.append(row)
                        print(f"{cruise} file {len(rows)}/{len(tasks)}: {row['status']}", flush=True)
            manifest = pd.DataFrame(rows)
            staging = destination / "_staging"
            atomic_write_parquet(manifest, out_manifest)
            atomic_write_tsv(manifest, out_manifest.with_suffix(".tsv"))
        failed = manifest["status"].str.startswith("failed:")
        if failed.any():
            raise RuntimeError(f"{cruise}: {int(failed.sum())} failed extraction files; inspect the manifest")
        summary = extract.merge_cruise(
            cruise, manifest, staging_dir=staging, output_dir=destination,
        )
        if not summary["points_checked_path"]:
            raise ValueError(f"{cruise}: {summary['status']}")
        atomic_write_parquet(manifest, out_manifest)
        atomic_write_tsv(manifest, out_manifest.with_suffix(".tsv"))
        write_json(summary, summary_path)
        checked = extract.REPO_ROOT / summary["points_checked_path"]

    required = file_cells.selection_columns(selection_policy)
    missing = set(required) - set(pq.read_schema(checked).names)
    if missing:
        raise ValueError(f"{cruise}: {selection_policy} missing fields: {sorted(missing)}")
    if selection_policy == NAVIGATION_POLICY and summary.get("n_unknown_navigation_beams", summary["n_rows"]):
        raise ValueError(f"{cruise}: source ping navigation has not been extracted for every beam")
    l2 = destination / "file_cells_1min" / checked.name
    aggregation_path = destination / "aggregation_summary.json"
    if resume and aggregation_path.exists():
        result = json.loads(aggregation_path.read_text())
        if result["selection_policy"] != selection_policy:
            raise ValueError(f"{cruise}: saved L2 uses a different selection policy")
        if not l2.is_file() or pq.read_metadata(l2).num_rows != result["n_cells"]:
            raise ValueError(f"{cruise}: L2 differs from its checkpoint")
    else:
        result = file_cells.aggregate_track_file(
            input_path=checked, output_path=l2, track_id=cruise.lower(),
            source_type=f"ncei_mb{summary['mb_format']}",
            source_completeness=f"mb{summary['mb_format']}_only",
            instrument_class_pred="multibeam", branch="multibeam_ncei",
            manual_review_flag=False, overwrite=resume, selection_policy=selection_policy,
            batch_size=500_000,
        )
        write_json(result, aggregation_path)
    summary_count = "n_selected_" + selection_policy
    if result["n_selected"] != summary[summary_count]:
        raise ValueError(f"{cruise}: L1 and L2 selected-point counts differ")
    print(f"{cruise}: {summary['n_rows']:,} points; {result['n_selected']:,} selected; {result['n_cells']:,} cells")
    return {**summary, **result, "cruise": cruise}


def extract_record(task: tuple) -> dict:
    cruise, record, output_root = task
    fmt = int(record["mb_format"]) if pd.notna(record["mb_format"]) else None
    row = extract.process_one_file(
        cruise, record["file_ordinal"], Path(record["relpath"]), fmt,
        record["format_note"], output_root=output_root,
        source_path=extract.RAW_ROOT / record["source_relpath"],
    )
    row["source_relpath"] = record["source_relpath"]
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ncei.swath batch",
        description=(
            "Rebuild selected staged cruises into an explicit output root, "
            "then write L1, basic_native_good L2, source-manifest, and coverage products."
        ),
    )
    parser.add_argument("--input-root", type=Path, default=extract.OUT_ROOT,
                        help="Existing mb_round2 root containing cruise staging directories.")
    parser.add_argument("--output-root", type=Path, required=True,
                        help="Scratch or release root for this batch; never defaults to production.")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--cruises", nargs="+", help="Cruises to process.")
    selection.add_argument("--all-staged", action="store_true",
                           help="Process every input cruise with a _staging directory.")
    parser.add_argument("--extract", action="store_true",
                        help="Extract raw sources into the new root instead of reusing input staging.")
    parser.add_argument("--resume", action="store_true",
                        help="Reuse completed L1/L2 outputs and continue missing steps.")
    parser.add_argument("--selection-policy", choices=("basic_native_good", NAVIGATION_POLICY),
                        default="basic_native_good",
                        help="Navigation policy requires newly extracted per-ping navigation.")
    parser.add_argument("--workers", type=int, default=1,
                        help="Concurrent source-file extraction processes.")
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be positive")
    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()
    production = extract.OUT_ROOT.resolve()
    if output_root == input_root or output_root == production:
        parser.error("--output-root must differ from input and production roots")
    if output_root.is_relative_to(production) and not output_root.is_relative_to(production / "_runs"):
        parser.error("new production-adjacent runs must be under mb_round2/_runs/")
    if any(output_root.is_relative_to(p) for p in input_root.iterdir() if (p / "_staging").is_dir()):
        parser.error("--output-root must not be inside an input cruise")
    cruises = sorted(set(args.cruises or [
        p.name for p in input_root.iterdir()
        if (p / "_staging").is_dir()
    ]))
    if not cruises:
        parser.error("no staged cruises found")
    if any(Path(c).name != c or c in {".", ".."} for c in cruises):
        parser.error("cruise IDs must be directory names, not paths")
    parameters = {
        "cruises": cruises, "input_root": str(input_root), "output_root": str(output_root),
        "extract": args.extract, "selection_policy": args.selection_policy,
        "workers": args.workers,
    }
    parameter_path = output_root / "run_parameters.json"
    if output_root.exists() and any(output_root.iterdir()):
        if not args.resume or not parameter_path.is_file():
            raise FileExistsError(f"nonempty output; --resume requires this batch's checkpoint: {output_root}")
        saved_parameters = json.loads(parameter_path.read_text())
        saved_parameters.setdefault("workers", 1)
        if saved_parameters != parameters:
            raise ValueError("resume parameters differ from the saved batch")
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(parameters, parameter_path)
    rows = [
        process_cruise(cruise, input_root, output_root, args.extract, args.resume,
                       args.selection_policy, args.workers)
        for cruise in cruises
    ]
    atomic_write_parquet(pd.DataFrame(rows), output_root / "file_cells_manifest.parquet")
    atomic_write_tsv(pd.DataFrame(rows), output_root / "file_cells_manifest.tsv")
    manifest_fragment.build_fragment(output_root)
    if coverage.coverage_stats(output_root):
        return 1
    write_json({
        "status": "completed", "cruises": cruises, "selection_policy": args.selection_policy,
        "n_rows": sum(r["n_rows"] for r in rows), "n_selected": sum(r["n_selected"] for r in rows),
        "n_cruise_cells": sum(r["n_cells"] for r in rows),
        "command": [sys.executable, "-m", "ncei.swath", "batch", *(sys.argv[1:] if argv is None else argv)],
    }, output_root / "run_summary.json")
    return 0
