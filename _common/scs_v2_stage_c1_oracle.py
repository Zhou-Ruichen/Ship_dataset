#!/usr/bin/env python3
"""Independent, source-internal oracle for the Stage C.1 format-58 fixture.

This module reads Kongsberg datagram framing and XYZ88/position payloads
directly. It does not import, execute, or link MB-System.
"""

from __future__ import annotations

import bisect
import calendar
import math
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class Position:
    epoch_seconds: float
    longitude: float
    latitude: float


@dataclass(frozen=True)
class OracleBeam:
    epoch_seconds_utc: float
    native_ping_counter: int
    beam_index: int
    lon_deg: float
    lat_deg: float
    depth_m_positive_down: float | None
    parser_depth_value: float
    heading_deg: float
    quality_state: str


def _epoch(date: int, msec: int) -> float:
    midnight = datetime.strptime(str(date), "%Y%m%d").replace(tzinfo=timezone.utc)
    value = midnight + timedelta(milliseconds=msec)
    return calendar.timegm(value.utctimetuple()) + value.microsecond / 1_000_000.0


def iter_datagrams(data: bytes):
    offset = 0
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError(f"truncated datagram header at byte {offset}")
        payload_bytes = struct.unpack_from("<I", data, offset)[0]
        end = offset + 4 + payload_bytes
        if payload_bytes < 8 or end > len(data):
            raise ValueError(f"invalid datagram length {payload_bytes} at byte {offset}")
        if data[offset + 4] != 0x02:
            raise ValueError(f"invalid STX at byte {offset}")
        yield offset, data[offset + 5], memoryview(data)[offset:end]
        offset = end
    if offset != len(data):
        raise ValueError("fixture does not end at a datagram boundary")


def _positions(datagrams) -> list[Position]:
    output: list[Position] = []
    for _offset, kind, record in datagrams:
        if kind != ord("P"):
            continue
        date, msec, _count, _serial, lat, lon, _quality, _speed, _course, _heading, system, _size = struct.unpack_from(
            "<IIHHiiHHHHBB", record, 8
        )
        if system & 0x80:
            output.append(Position(_epoch(date, msec), lon / 10_000_000.0, lat / 20_000_000.0))
    if len(output) < 2 or any(a.epoch_seconds >= b.epoch_seconds for a, b in zip(output, output[1:])):
        raise ValueError("oracle requires strictly increasing active position fixes")
    return output


def _interpolate_position(positions: list[Position], epoch: float) -> tuple[float, float]:
    times = [item.epoch_seconds for item in positions]
    right = bisect.bisect_left(times, epoch)
    if right == 0 or right == len(positions):
        raise ValueError(f"ping time {epoch} lacks a bracketing position pair")
    left = right - 1
    fraction = (epoch - times[left]) / (times[right] - times[left])
    lon = positions[left].longitude + fraction * (positions[right].longitude - positions[left].longitude)
    lat = positions[left].latitude + fraction * (positions[right].latitude - positions[left].latitude)
    return lon, lat


def _wgs84_meter_to_degree(latitude: float) -> tuple[float, float]:
    semi_major = 6_378_137.0
    eccentricity_squared = 6.6943799901413165e-3
    radians = math.radians(latitude)
    sin_squared = math.sin(radians) ** 2
    prime_vertical = semi_major / math.sqrt(1.0 - eccentricity_squared * sin_squared)
    meridional = (
        semi_major
        * (1.0 - eccentricity_squared)
        / (1.0 - eccentricity_squared * sin_squared) ** 1.5
    )
    return (
        math.degrees(1.0 / (prime_vertical * math.cos(radians))),
        math.degrees(1.0 / meridional),
    )


def _quality_state(detection: int, cleaning: int, depth: float, across: float, along: float) -> str:
    if not all(math.isfinite(value) for value in (depth, across, along)):
        return "null"
    if detection & 0x80:
        return "null" if (detection & 0x0F) == 4 else "flagged"
    if cleaning != 0:
        return "flagged"
    return "good"


def read_format58_fixture(path: Path) -> list[OracleBeam]:
    data = path.read_bytes()
    datagrams = list(iter_datagrams(data))
    positions = _positions(datagrams)
    companion_counts = {
        kind: {struct.unpack_from("<H", record, 16)[0] for _offset, item_kind, record in datagrams if item_kind == kind}
        for kind in (ord("N"), ord("Y"))
    }

    output: list[OracleBeam] = []
    for offset, kind, record in datagrams:
        if kind != ord("X"):
            continue
        date, msec, count, _serial, heading_raw, _ssv, transducer_depth, n_beams, _valid, _rate, _spare = struct.unpack_from(
            "<IIHHHHfHHfI", record, 8
        )
        if count not in companion_counts[ord("N")] or count not in companion_counts[ord("Y")]:
            raise ValueError(f"XYZ88 ping {count} is incomplete")
        expected_length = 4 + 4 + 32 + 20 * n_beams + 4
        if len(record) != expected_length:
            raise ValueError(f"XYZ88 length mismatch at byte {offset}")
        epoch = _epoch(date, msec)
        nav_lon, nav_lat = _interpolate_position(positions, epoch)
        meter_to_lon, meter_to_lat = _wgs84_meter_to_degree(nav_lat)
        heading_deg = heading_raw / 100.0
        heading_x = math.sin(math.radians(heading_deg))
        heading_y = math.cos(math.radians(heading_deg))
        for beam_index in range(n_beams):
            beam_offset = 40 + 20 * beam_index
            depth, across, along, _window, _quality, _iba, detection, cleaning, _amplitude = struct.unpack_from(
                "<fffHBBbbh", record, beam_offset
            )
            detection &= 0xFF
            parser_depth = transducer_depth + depth
            state = _quality_state(detection, cleaning, depth, across, along)
            output.append(
                OracleBeam(
                    epoch_seconds_utc=epoch,
                    native_ping_counter=count,
                    beam_index=beam_index,
                    lon_deg=nav_lon + (heading_y * across + heading_x * along) * meter_to_lon,
                    lat_deg=nav_lat + (-heading_x * across + heading_y * along) * meter_to_lat,
                    depth_m_positive_down=parser_depth if state == "good" else None,
                    parser_depth_value=parser_depth,
                    heading_deg=heading_deg,
                    quality_state=state,
                )
            )
    if not output:
        raise ValueError("format-58 oracle found no complete XYZ88 pings")
    return output
