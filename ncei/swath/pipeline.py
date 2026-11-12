"""Run one cruise at a time and save completed cruise checkpoints."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

import pandas as pd

from _common.file_io import atomic_write_parquet, atomic_write_text

from . import exclusions
from .aggregation import aggregate_cruise
from .decode import ENVIRONMENT_RELATIVE, MBSYSTEM_VERSION, decode
from .selection import BOUNDS, COUNTS, DEPTH_COUNTS, SELECTION_RULE, STAGE_COUNTS, depth_sign, grid_candidates
from .source_summary import source_summary
from .format_times import format_time_summary
from .sources import LEDGER, ROOT, Source, discover

FREE_BYTES_MIN = 300_000_000_000


def write_json(path: Path, value: dict) -> None:
    atomic_write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", path)


def process_file(source: Source, *, temp: Path, invalid_pings: dict, environment: Path) -> dict:
    started = time.monotonic()
    row = {
        "cruise": source.cruise, "filekey": source.filekey, "file_ordinal": source.file_ordinal,
        "relpath": str(source.relpath), "source_path": str(source.path), "mb_format": source.mb_format,
        "format_note": source.format_note, "raw_bytes": source.bytes,
        "status": "unsupported", "error_detail": "",
        "ping_time_start_us": None, "ping_time_end_us": None,
        "n_source_pings": 0, "n_invalid_navigation_pings": 0,
    }
    counts = {**dict.fromkeys(COUNTS, 0), **dict.fromkeys(BOUNDS),
              **{sign: dict.fromkeys(STAGE_COUNTS, 0) for sign in ("positive", "negative")}}
    if source.supported:
        try:
            beams = decode(source, temp, environment)
        except (ValueError, OSError, RuntimeError) as error:
            row.update(status="failed", error_detail="".join(traceback.format_exception(error)))
        else:
            row.update(beams.attrs)
            triples, counts = grid_candidates(beams, invalid_pings.get(source.filekey, set()))
            if len(triples):
                triples.to_parquet(temp / f"{source.filekey}.parquet", index=False, compression="zstd")
            row["status"] = "ok"
    return {**row, **counts, "runtime_seconds": time.monotonic() - started}


def process_cruise(cruise: str, sources: list[Source], output: Path,
                   invalid_pings: dict, workers: int, data_root: Path = ROOT) -> tuple[list[dict], dict]:
    started = time.monotonic()
    temp = output / "_tmp" / cruise
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True)
    cells = output / "cells_1min" / f"{cruise}.parquet"
    cells.unlink(missing_ok=True)
    process = partial(process_file, temp=temp, invalid_pings=invalid_pings, environment=data_root / ENVIRONMENT_RELATIVE)
    if workers == 1:
        rows = list(map(process, sources))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(process, sources))
    sign_name, sign = depth_sign({name: sum(row[name] for row in rows) for name in DEPTH_COUNTS})
    for row in rows:
        chosen = row.pop("positive" if sign == 1 else "negative")
        row.pop("negative" if sign == 1 else "positive")
        row.update(chosen)
    counts = {name: sum(row[name] for row in rows) for name in COUNTS}
    bounds = {}
    for name in BOUNDS:
        values = [row[name] for row in rows if row[name] is not None]
        bounds[name] = (min if "_min" in name else max)(values) if values else None
    ok = [row for row in rows if row["status"] == "ok"]
    failed = sum(row["status"] == "failed" for row in rows)
    unsupported = sum(row["status"] == "unsupported" for row in rows)
    formats = sorted({row["mb_format"] for row in ok})
    directories = sorted({source.directory for source in sources})
    format_summary = format_time_summary(rows)
    summary = {
        **format_summary,
        **source_summary(cruise, formats, directories, counts, bounds, sign_name, data_root),
        **counts, "cruise": cruise, "sign_flip": sign, "mb_formats": formats,
        "n_files": len(rows), "n_unsupported_files": unsupported, "n_failed_files": failed,
        "n_missing_sources": sum(source.bytes == 0 and not source.path.is_file() for source in sources), "raw_bytes": sum(row["raw_bytes"] for row in rows),
        "n_cells": 0, "cells_path": None,
        "status": "failed" if failed or not sources else "completed" if ok else "no_usable_files",
    }
    if summary["format_overlaps"] and not failed:
        summary["status"] = "format_overlap"
    if ok and summary["status"] == "completed":
        shards = [temp / f"{row['filekey']}.parquet" for row in ok if row["n_selected"]]
        result = aggregate_cruise(shards, temp, cells, cruise, formats, sign, counts["n_selected"])
        if result["n_selected"] != counts["n_selected"]:
            raise ValueError(f"{cruise}: selected-file and aggregated beam counts disagree")
        summary.update(n_cells=result["n_cells"], cells_path=str(cells.relative_to(output)))
    summary["runtime_seconds"] = time.monotonic() - started
    return rows, summary


def checkpoint(output: Path, rows: list[dict], summary: dict) -> None:
    cruise = summary["cruise"]
    write_json(output / "_checkpoints" / f"{cruise}.json", {"files": rows, "cruise": summary})
    if summary["status"] == "completed":
        atomic_write_text("completed\n", output / "_completed" / cruise)
    shutil.rmtree(output / "_tmp" / cruise)


def publish_manifests(output: Path) -> None:
    checkpoints = sorted((output / "_checkpoints").glob("*.json"))
    if not checkpoints:
        return
    records = [json.loads(path.read_text()) for path in checkpoints]
    replaced = {record["cruise"]["cruise"] for record in records}
    for name, rows in (
        ("files", [row for record in records for row in record["files"]]),
        ("cruises", [record["cruise"] for record in records]),
    ):
        path = output / f"{name}.parquet"
        frame = pd.DataFrame(rows)
        if path.exists():
            previous = pd.read_parquet(path)
            frame = pd.concat([previous[~previous.cruise.isin(replaced)], frame], ignore_index=True)
        order = ["cruise", "file_ordinal"] if name == "files" and "file_ordinal" in frame else ["cruise"]
        if frame.empty and "cruise" not in frame:
            frame["cruise"] = pd.Series(dtype=str)
        if name == "files":
            for column in ("mb_format", "ping_time_start_us", "ping_time_end_us"):
                if column in frame:
                    frame[column] = frame[column].astype("Int64")
        atomic_write_parquet(frame.sort_values(order), path)
    for path in checkpoints:
        path.unlink()


def prepare_run(output: Path, roots: list[Path], selected: list[str] | None, resume: bool,
                exclusion_path: Path | None, default_exclusions: bool, ledger: Path = LEDGER,
                data_root: Path = ROOT) -> dict:
    parameters_path = output / "run_parameters.json"
    if parameters_path.exists() and not resume:
        raise FileExistsError(f"use --resume for {output}")
    if not parameters_path.exists() and output.exists() and any(
        path.name != "census.parquet" for path in output.iterdir()
    ):
        raise FileExistsError(f"output contains files from a different run: {output}")
    if default_exclusions:
        exclusion_path = output / exclusions.EXCLUSION_TABLE
        if not exclusion_path.exists():
            exclusions.write_default(exclusion_path, data_root / "ncei/derived/processing_revision_20261025/swath")
    invalid_pings = exclusions.load(exclusion_path)
    parameters = {
        "raw_roots": [str(root) for root in roots], "cruises": selected, "ledger": str(ledger),
        "data_root": str(data_root),
        "selection_policy": "basic_native_good_valid_ping_navigation_case_review" if exclusion_path
                            else "basic_native_good_valid_ping_navigation",
        "selection_rule": SELECTION_RULE if exclusion_path else SELECTION_RULE.split(" & ~")[0],
        "exclusion_path": str(exclusion_path) if exclusion_path else None,
        "exclusion_sha256": hashlib.sha256(exclusion_path.read_bytes()).hexdigest() if exclusion_path else None,
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "mbsystem_version": MBSYSTEM_VERSION,
    }
    if parameters_path.exists():
        if json.loads(parameters_path.read_text()) != parameters:
            raise ValueError("resume inputs or selection differ from run_parameters.json")
    else:
        exclusions.write_sensitivity(output / exclusions.SENSITIVITY_TABLE, data_root / "ncei/derived/mb_round2")
        write_json(parameters_path, parameters)
    return invalid_pings


def run(output: Path, targets: list[str], directories: dict[str, list[tuple[Path, Path]]], invalid_pings: dict,
        workers: int, resume: bool, data_root: Path = ROOT) -> int:
    failures = 0
    try:
        for cruise in targets:
            if resume and (output / "_completed" / cruise).is_file():
                remaining = output / "_tmp" / cruise
                if remaining.exists():
                    shutil.rmtree(remaining)
                continue
            if shutil.disk_usage(data_root).free < FREE_BYTES_MIN:
                print(f"Stopped before {cruise}: data2 has less than 300 GB free", flush=True)
                break
            rows, summary = process_cruise(cruise, discover(cruise, directories[cruise], data_root / "ncei/derived/mb_round2"),
                                           output, invalid_pings, workers, data_root)
            checkpoint(output, rows, summary)
            failures += summary["status"] == "failed"
            print(f"{cruise}: {summary['status']}; {summary['n_rows']:,} beams; "
                  f"{summary['n_selected']:,} selected; {summary['n_cells']:,} cells; "
                  f"{summary['runtime_seconds']:.2f} s", flush=True)
    finally:
        publish_manifests(output)
    return int(failures > 0)
