#!/usr/bin/env python3
"""Frozen Stage C.1 object identity, mblist adapter, and 1-minute grid rules."""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Iterable


ACQUISITION_RUN_ID = "20260805T230449Z"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
OUTPUT_FIELDS = (
    "epoch_seconds_utc",
    "native_ping_counter",
    "beam_index",
    "lon_deg",
    "lat_deg",
    "parser_depth_value",
    "heading_deg",
)
DELIMITER = "\t"
CELL_DEG = 1.0 / 60.0


@dataclass(frozen=True)
class MblistRow:
    epoch_seconds_utc: Decimal
    native_ping_counter: int
    beam_index: int
    lon_deg: float
    lat_deg: float
    parser_depth_value: float
    heading_deg: float

    @property
    def join_key(self) -> tuple[Decimal, int, int]:
        return (self.epoch_seconds_utc, self.native_ping_counter, self.beam_index)


def validate_run_id(value: str) -> str:
    if not RUN_ID_RE.fullmatch(value) or value in {".", ".."} or ".." in value:
        raise ValueError(f"unsafe acquisition run ID: {value!r}")
    return value


def canonical_relative_path(value: str) -> str:
    if not value or "\\" in value:
        raise ValueError(f"invalid source object relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"invalid source object relative path: {value!r}")
    normalized = path.as_posix()
    if normalized != value:
        raise ValueError(f"source object path is not canonical POSIX: {value!r}")
    return normalized


def source_object_id(acquisition_run_id: str, source_object_relative_path: str) -> str:
    """Return the identity key; a content hash is deliberately not involved."""
    run_id = validate_run_id(acquisition_run_id)
    relative_path = canonical_relative_path(source_object_relative_path)
    return f"{run_id}/{relative_path}"


def _parse_int(value: str, field: str) -> int:
    stripped = value.strip()
    if not re.fullmatch(r"[0-9]+", stripped):
        raise ValueError(f"{field} is not a non-negative integer: {value!r}")
    return int(stripped)


def _parse_finite_float(value: str, field: str) -> float:
    try:
        parsed = float(value.strip())
    except ValueError as error:
        raise ValueError(f"{field} is not numeric: {value!r}") from error
    if not math.isfinite(parsed):
        raise ValueError(f"{field} must be finite: {value!r}")
    return parsed


def parse_mblist_tsv(text: str, *, check_mode: int) -> list[MblistRow]:
    """Parse the exact headerless ASCII-HT/LF seven-column mblist contract."""
    if check_mode not in {0, 3}:
        raise ValueError("only frozen mblist check modes U0 and U3 are supported")
    if "\r" in text:
        raise ValueError("CR is forbidden; mblist output must use LF records")

    rows: list[MblistRow] = []
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=DELIMITER, quoting=csv.QUOTE_NONE, strict=True)
    for line_number, fields in enumerate(reader, start=1):
        if not fields or fields == [""]:
            raise ValueError(f"blank record at line {line_number}")
        if len(fields) != len(OUTPUT_FIELDS):
            raise ValueError(f"line {line_number} has {len(fields)} fields, expected {len(OUTPUT_FIELDS)}")
        try:
            epoch = Decimal(fields[0].strip())
        except InvalidOperation as error:
            raise ValueError(f"invalid epoch at line {line_number}: {fields[0]!r}") from error
        if not epoch.is_finite():
            raise ValueError(f"epoch must be finite at line {line_number}")

        depth_text = fields[5].strip()
        if depth_text.lower() == "nan":
            if check_mode != 3:
                raise ValueError(f"NaN depth is allowed only in U3 at line {line_number}")
            depth = math.nan
        else:
            depth = _parse_finite_float(depth_text, "parser_depth_value")

        row = MblistRow(
            epoch_seconds_utc=epoch,
            native_ping_counter=_parse_int(fields[1], "native_ping_counter"),
            beam_index=_parse_int(fields[2], "beam_index"),
            lon_deg=_parse_finite_float(fields[3], "lon_deg"),
            lat_deg=_parse_finite_float(fields[4], "lat_deg"),
            parser_depth_value=depth,
            heading_deg=_parse_finite_float(fields[6], "heading_deg"),
        )
        if not -90.0 <= row.lat_deg <= 90.0:
            raise ValueError(f"latitude outside [-90, 90] at line {line_number}")
        if not 0.0 <= row.heading_deg < 360.0:
            raise ValueError(f"heading outside [0, 360) at line {line_number}")
        rows.append(row)
    return rows


def join_all_and_good(
    acquisition_run_id: str,
    source_object_relative_path: str,
    all_rows: Iterable[MblistRow],
    good_rows: Iterable[MblistRow],
) -> list[dict[str, object]]:
    """Classify U3 rows from the U0 subset without using filenames or hashes."""
    object_id = source_object_id(acquisition_run_id, source_object_relative_path)
    all_list = list(all_rows)
    good_list = list(good_rows)
    all_index = {row.join_key: row for row in all_list}
    good_index = {row.join_key: row for row in good_list}
    if len(all_index) != len(all_list):
        raise ValueError("duplicate U3 ping/beam key")
    if len(good_index) != len(good_list):
        raise ValueError("duplicate U0 ping/beam key")
    if not good_index.keys() <= all_index.keys():
        raise ValueError("U0 key is absent from U3 stream")

    ping_ordinals: dict[tuple[Decimal, int], int] = {}
    output: list[dict[str, object]] = []
    for row in all_list:
        ping_key = (row.epoch_seconds_utc, row.native_ping_counter)
        parser_ping_index = ping_ordinals.setdefault(ping_key, len(ping_ordinals))
        good = good_index.get(row.join_key)
        if good is not None:
            if any(
                abs(left - right) > tolerance
                for left, right, tolerance in (
                    (row.lon_deg, good.lon_deg, 1.0e-10),
                    (row.lat_deg, good.lat_deg, 1.0e-10),
                    (row.parser_depth_value, good.parser_depth_value, 1.0e-4),
                    (row.heading_deg, good.heading_deg, 1.0e-3),
                )
            ):
                raise ValueError(f"U0/U3 value mismatch for key {row.join_key}")
            quality_state = "good"
            depth = good.parser_depth_value
        elif math.isnan(row.parser_depth_value):
            quality_state = "null"
            depth = None
        else:
            quality_state = "flagged"
            depth = None

        output.append(
            {
                "source_object_id": object_id,
                "parser_ping_index": parser_ping_index,
                "native_ping_counter": row.native_ping_counter,
                "beam_index": row.beam_index,
                "epoch_seconds_utc": row.epoch_seconds_utc,
                "lon_deg": normalize_longitude(row.lon_deg),
                "lat_deg": row.lat_deg,
                "parser_depth_value": row.parser_depth_value,
                "depth_m_positive_down": depth,
                "heading_deg": row.heading_deg,
                "native_quality_state": quality_state,
            }
        )
    return output


def normalize_longitude(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("longitude must be finite")
    normalized = ((value + 180.0) % 360.0) - 180.0
    return -180.0 if normalized == 180.0 else normalized


def cell_assignment(lon_deg: float, lat_deg: float) -> tuple[int, int, str]:
    lon = normalize_longitude(lon_deg)
    if not math.isfinite(lat_deg) or not -90.0 <= lat_deg <= 90.0:
        raise ValueError("latitude must be finite and inside [-90, 90]")
    lon_bin = math.floor((lon + 180.0) / CELL_DEG)
    lat_bin = math.floor((lat_deg + 90.0) / CELL_DEG)
    return lon_bin, lat_bin, f"1min_{lat_bin}_{lon_bin}"


def cell_center(lon_bin: int, lat_bin: int) -> tuple[float, float]:
    return (
        -180.0 + (lon_bin + 0.5) * CELL_DEG,
        -90.0 + (lat_bin + 0.5) * CELL_DEG,
    )
