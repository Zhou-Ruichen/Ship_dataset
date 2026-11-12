"""Recreate the checked point table for on-demand sounding delivery."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from _common.mbsystem import PING_NAVIGATION_SCHEMA

from .decode import ENVIRONMENT, MBSYSTEM_VERSION, decode
from .selection import DEPTH_COUNTS, SELECTION_COLUMN, basic_checks, depth_counts, depth_sign, excluded_pings
from .sources import Source

NAVIGATION_FIELDS = [
    pa.field("parser_ping_index", pa.int64()), pa.field("native_ping_counter", pa.int64()),
    pa.field("beam_index", pa.int32()),
    *[field for field in PING_NAVIGATION_SCHEMA if field.name not in {"epoch_us", "native_ping_counter"}],
]
CHECK_COLUMNS = ["valid_lon", "valid_lat", "valid_depth_pos", "valid_depth_max", "valid_core_fields",
                 "point_check_pass_basic", SELECTION_COLUMN]
SCHEMA = pa.schema([
    ("source_type", pa.string()), ("track_id", pa.string()), ("point_index_in_track", pa.int64()),
    ("time", pa.timestamp("ns")), ("lon_raw", pa.float64()), ("lat_raw", pa.float64()),
    ("lon", pa.float64()), ("lat", pa.float64()), ("depth_raw", pa.float64()),
    ("depth_m_positive_down", pa.float64()), ("elev_m", pa.float64()), ("gobs", pa.float64()),
    ("faa", pa.float64()), ("source_completeness", pa.string()), ("instrument_class_pred", pa.string()),
    ("standardization_version", pa.string()), ("filekey", pa.string()), ("file_ordinal", pa.int32()),
    ("point_index_in_file", pa.int64()), ("staging_row", pa.int64()), ("native_quality_state", pa.string()),
    *NAVIGATION_FIELDS, *[pa.field(name, pa.bool_()) for name in CHECK_COLUMNS],
])


def checked_frame(beams: pd.DataFrame, source: Source, offset: int) -> pd.DataFrame:
    n = len(beams)
    rows = np.arange(n, dtype=np.int64)
    mb_format = source.mb_format
    return beams.assign(
        source_type=f"ncei_mb{mb_format}", track_id=source.cruise.lower(), point_index_in_track=offset + rows,
        time=beams.epoch_us.to_numpy(dtype="datetime64[us]").astype("datetime64[ns]"),
        lon_raw=beams.lon, lat_raw=beams.lat, gobs=np.nan, faa=np.nan, source_completeness=f"mb{mb_format}_only",
        instrument_class_pred="multibeam", standardization_version=(
            f"ncei.swath.extract v3; mblist {MBSYSTEM_VERSION} -F{mb_format} U3/U0 join; exact source ping navigation; staging lineage"
        ), filekey=source.filekey, file_ordinal=source.file_ordinal, point_index_in_file=rows, staging_row=rows,
    )


def checked_table(frame: pd.DataFrame, sign: int, invalid_pings: dict) -> pa.Table:
    depth = frame.depth_raw.to_numpy() * sign
    checks = basic_checks(frame.lon.to_numpy(), frame.lat.to_numpy(), depth)
    selected = checks["point_check_pass_basic"] & frame.native_quality_state.eq("good").to_numpy()
    selected &= frame.valid_ping_navigation.to_numpy()
    for filekey, group in frame.groupby("filekey", sort=False):
        if filekey in invalid_pings:
            selected[group.index] &= ~excluded_pings(group, invalid_pings[filekey])
    checked = frame.assign(depth_m_positive_down=depth, elev_m=-depth, **checks,
                           **{SELECTION_COLUMN: selected})
    return pa.Table.from_pydict({name: checked[name].to_numpy() for name in SCHEMA.names}, schema=SCHEMA)


def write_points(sources: list[Source], output: Path, file_ids: set[str], bounds: list[float] | None,
                 invalid_pings: dict, environment: Path = ENVIRONMENT) -> None:
    chosen = {source.filekey for source in sources if source.supported}
    if file_ids:
        chosen.clear()
        for identifier in file_ids:
            matches = [source for source in sources if identifier in
                       {source.filekey, str(source.relpath), source.path.name, str(source.path)}]
            if len(matches) != 1 or not matches[0].supported:
                raise ValueError(f"expected one supported source file for {identifier!r}")
            chosen.add(matches[0].filekey)
    if not chosen:
        raise ValueError("no supported source files for points")
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as name:
        work = Path(name)
        provisional = work / "positive.parquet"
        counts = dict.fromkeys(DEPTH_COUNTS, 0)
        offset = 0
        with pq.ParquetWriter(provisional, SCHEMA, compression="zstd") as writer:
            for source in sources:
                if not source.supported:
                    continue
                beams = decode(source, work, environment)
                for key, count in depth_counts(beams.depth_raw.to_numpy()).items():
                    counts[key] += count
                if source.filekey in chosen:
                    frame = checked_frame(beams, source, offset)
                    if bounds:
                        west, south, east, north = bounds
                        frame = frame[frame.lon.between(west, east) & frame.lat.between(south, north)]
                    if len(frame):
                        writer.write_table(checked_table(frame.reset_index(drop=True), 1, invalid_pings))
                offset += len(beams)
        _, sign = depth_sign(counts)
        if sign == 1:
            os.replace(provisional, output)
        else:
            negative = work / "negative.parquet"
            with pq.ParquetWriter(negative, SCHEMA, compression="zstd") as writer:
                for batch in pq.ParquetFile(provisional).iter_batches(batch_size=500_000):
                    frame = batch.to_pandas()
                    frame["epoch_us"] = frame.time.to_numpy(dtype="datetime64[us]").astype(np.int64)
                    writer.write_table(checked_table(frame, -1, invalid_pings))
            os.replace(negative, output)
