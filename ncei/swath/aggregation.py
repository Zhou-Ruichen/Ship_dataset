"""Aggregate selected soundings with the shared 1-arcmin implementation."""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from _common.file_io import atomic_write_parquet
from ncei.trackline.file_cells import aggregate_track_file

TARGET_PARTITION_ROWS = 40_000_000
AGG_SCHEMA = pa.schema([
    ("lon", pa.float64()), ("lat", pa.float64()), ("depth_m_positive_down", pa.float64()),
    ("point_check_pass_basic", pa.bool_()),
])


def source_labels(formats: list[int]) -> tuple[str, str]:
    if not formats:
        return "", ""
    tag = "_".join(f"mb{fmt}" for fmt in formats)
    return f"ncei_{tag}", f"{tag}_only" if len(formats) == 1 else tag


def partition_inputs(shards: list[Path], work: Path, sign: int, n_parts: int) -> list[Path]:
    """Route entire cells to one partition while preserving within-cell source order."""
    paths = {}
    writers = {}
    with ExitStack() as stack:
        for shard in shards:
            for batch in pq.ParquetFile(shard).iter_batches(batch_size=500_000):
                frame = batch.to_pandas()
                depth = frame.depth_raw.to_numpy() * sign
                keep = depth > 0
                depth, lon, lat = depth[keep], frame.lon.to_numpy()[keep], frame.lat.to_numpy()[keep]
                if n_parts == 1:
                    groups = [(0, slice(None))]
                else:
                    # Use the canonical 1-minute bin expression only to keep cells intact.
                    x = np.floor((lon + 180) * 60).astype(np.int64)
                    y = np.floor((lat + 90) * 60).astype(np.int64)
                    buckets = ((x * 73_856_093) ^ (y * 19_349_663)) % n_parts
                    order = np.argsort(buckets, kind="stable")
                    ids, starts = np.unique(buckets[order], return_index=True)
                    groups = [(int(key), order[start:end]) for key, start, end in
                              zip(ids, starts, np.r_[starts[1:], len(order)])]
                for key, idx in groups:
                    if key not in writers:
                        paths[key] = work / f"selected-{key}.parquet"
                        writers[key] = stack.enter_context(pq.ParquetWriter(paths[key], AGG_SCHEMA, compression="zstd"))
                    part_depth = depth[idx]
                    writers[key].write_table(pa.Table.from_arrays([
                        pa.array(lon[idx]), pa.array(lat[idx]), pa.array(part_depth),
                        pa.array(np.ones(len(part_depth), dtype=bool)),
                    ], schema=AGG_SCHEMA))
            shard.unlink()
    if not paths:
        path = work / "selected-0.parquet"
        pq.write_table(pa.Table.from_batches([], schema=AGG_SCHEMA), path, compression="zstd")
        return [path]
    return list(paths.values())


def aggregate_cruise(shards: list[Path], work: Path, output: Path, cruise: str,
                     formats: list[int], sign: int, n_selected: int) -> dict:
    """Apply the canonical aggregation to disjoint groups of complete cells."""
    n_parts = max(1, (n_selected + TARGET_PARTITION_ROWS - 1) // TARGET_PARTITION_ROWS)
    inputs = partition_inputs(shards, work, sign, n_parts)
    source_type, completeness = source_labels(formats)
    cell_paths = []
    n_cells = n_points = 0
    for i, path in enumerate(inputs):
        destination = output if len(inputs) == 1 else work / f"cells-{i}.parquet"
        result = aggregate_track_file(
            input_path=path, output_path=destination, track_id=cruise.lower(),
            source_type=source_type, source_completeness=completeness,
            instrument_class_pred="multibeam", branch="multibeam_ncei", manual_review_flag=False,
            overwrite=False, batch_size=500_000,
        )
        path.unlink()
        cell_paths.append(destination)
        n_cells += result["n_cells"]
        n_points += result["n_selected"]
    if len(cell_paths) > 1:
        frames = [pd.read_parquet(path) for path in cell_paths]
        atomic_write_parquet(pd.concat(frames, ignore_index=True).sort_values("cell_id"), output)
    return {"n_cells": n_cells, "n_selected": n_points}
