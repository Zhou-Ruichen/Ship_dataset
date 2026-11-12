"""Parse exact source-ping navigation from MB-System listings."""


from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pyarrow as pa


def timestamp_us(epoch: Decimal) -> int:
    """Convert mblist epoch seconds to integer microseconds."""
    scaled = epoch * Decimal(1_000_000)
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise ValueError("M field has sub-microsecond precision")
    return int(integral)


def _parse_finite(value: str, field: str, *, allow_nan: bool = False) -> float:
    try:
        parsed = float(value.strip())
    except ValueError as error:
        raise ValueError(f"{field} is not numeric: {value!r}") from error
    if allow_nan and not math.isfinite(parsed):
        return parsed
    if not math.isfinite(parsed):
        raise ValueError(f"{field} is not finite: {value!r}")
    return parsed


PING_NAVIGATION_SCHEMA = pa.schema([
    ("ping_navigation_record_index", pa.int64()),
    ("epoch_us", pa.int64()),
    ("native_ping_counter", pa.int64()),
    ("ping_lon", pa.float64()),
    ("ping_lat", pa.float64()),
    ("valid_ping_navigation", pa.bool_()),
    ("ping_navigation_reason", pa.string()),
])


def read_ping_navigation(path: Path) -> pa.Table:
    """Read -OMNXYzH without -MA, retaining exact ping identity and navigation."""
    records = []
    seen = set()
    with path.open("r", encoding="ascii", newline="") as handle:
        for index, line in enumerate(handle):
            fields = line.rstrip("\n").split("\t")
            if not line.endswith("\n") or "\r" in line or len(fields) != 6:
                raise ValueError(f"invalid ping navigation listing at line {index + 1}")
            try:
                epoch = Decimal(fields[0].strip())
            except InvalidOperation as error:
                raise ValueError(f"invalid ping M at line {index + 1}") from error
            if not epoch.is_finite() or epoch < 0:
                raise ValueError(f"invalid ping M at line {index + 1}")
            epoch_us = timestamp_us(epoch)
            native_ping = int(fields[1].strip())
            if native_ping < 0:
                raise ValueError(f"negative ping N at line {index + 1}")
            key = (epoch_us, native_ping)
            if key in seen:
                raise ValueError(f"ambiguous duplicate navigation ping key: {key}")
            seen.add(key)
            lon = _parse_finite(fields[2], "ping X", allow_nan=True)
            lat = _parse_finite(fields[3], "ping Y", allow_nan=True)
            if not math.isfinite(lon) or not math.isfinite(lat):
                reason = "nonfinite"
            elif not (-180 <= lon <= 180 and -90 <= lat <= 90):
                reason = "out_of_range"
            elif lon == 0 and lat == 0:
                reason = "zero_navigation"
            else:
                reason = "valid"
            records.append({
                "ping_navigation_record_index": index, "epoch_us": epoch_us,
                "native_ping_counter": native_ping, "ping_lon": lon, "ping_lat": lat,
                "valid_ping_navigation": reason == "valid",
                "ping_navigation_reason": reason,
            })
    return pa.Table.from_pylist(records, schema=PING_NAVIGATION_SCHEMA)
