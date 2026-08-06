#!/usr/bin/env python3
"""Source-internal Stage C parser, QC, lineage and exact aggregation helpers."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sqlite3
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from ncei.code.scs_v2_stage_c1_contract import (
    MblistRow,
    cell_assignment,
    cell_center,
    normalize_longitude,
)


RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
FIVE_LEVEL_STATUS = {
    "known",
    "officially_unknown",
    "not_recoverable",
    "inferred_from_filename",
    "verified_from_source_metadata",
}
TIME_FAILURE_STATUS = "failed_invalid_or_missing_time"
PARSER_FAILURE_STATUS = "failed_parser_contract"
PASS_STATUS = "pass"
SIDECAR_STATUS = "not_applicable_sidecar"
FIELD_NAMES = (
    "time_utc",
    "line_id",
    "native_ping_id",
    "native_beam_id",
    "longitude",
    "latitude",
    "heading",
    "native_quality",
    "native_quality_code",
    "horizontal_datum",
    "vertical_datum",
    "depth",
)


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


def canonical_authorization_receipt_sha256(value: dict[str, Any]) -> str:
    """Hash an authorization receipt without creating an impossible self-hash."""
    payload = dict(value)
    payload.pop("authorization_receipt_sha256", None)
    return canonical_sha256(payload)


def safe_processing_run_id(value: str) -> str:
    if not RUN_ID_RE.fullmatch(value) or ".." in value or "/" in value or "\\" in value:
        raise ValueError(f"unsafe processing run ID: {value!r}")
    return value


def source_object_id(acquisition_run_id: str, relative_path: str) -> str:
    if not relative_path or Path(relative_path).is_absolute() or "\\" in relative_path:
        raise ValueError(f"invalid source object relative path: {relative_path!r}")
    parts = relative_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"noncanonical source object relative path: {relative_path!r}")
    if not RUN_ID_RE.fullmatch(acquisition_run_id):
        raise ValueError(f"invalid acquisition run ID: {acquisition_run_id!r}")
    return f"{acquisition_run_id}/{relative_path}"


def timestamp_us(epoch: Decimal) -> int:
    scaled = epoch * Decimal(1_000_000)
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise ValueError("M field has sub-microsecond precision")
    return int(integral)


def datetime_from_us(value: int) -> datetime:
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=value)


def _parse_finite(value: str, field: str, *, allow_nan: bool = False) -> float:
    try:
        parsed = float(value.strip())
    except ValueError as error:
        raise ValueError(f"{field} is not numeric: {value!r}") from error
    if math.isnan(parsed) and allow_nan:
        return parsed
    if not math.isfinite(parsed):
        raise ValueError(f"{field} is not finite: {value!r}")
    return parsed


def iter_mblist_rows(path: Path, *, check_mode: int) -> Iterator[tuple[MblistRow, int]]:
    """Stream the exact seven-column ASCII HT/LF contract."""
    if check_mode not in {0, 3}:
        raise ValueError(f"unsupported check mode: {check_mode}")
    with path.open("r", encoding="ascii", newline="") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if "\r" in raw:
                raise ValueError(f"CR is forbidden at line {line_number}")
            if not raw.endswith("\n"):
                raise ValueError(f"missing LF terminator at line {line_number}")
            fields = raw[:-1].split("\t")
            if len(fields) != 7:
                raise ValueError(f"line {line_number} has {len(fields)} fields, expected 7")
            epoch_text = fields[0].strip()
            if not epoch_text:
                raise ValueError(f"missing M at line {line_number}")
            try:
                epoch = Decimal(epoch_text)
            except InvalidOperation as error:
                raise ValueError(f"invalid M at line {line_number}") from error
            if not epoch.is_finite() or epoch < 0:
                raise ValueError(f"invalid M at line {line_number}")
            timestamp_us(epoch)
            try:
                native_ping = int(fields[1].strip())
                beam = int(fields[2].strip())
            except ValueError as error:
                raise ValueError(f"invalid N/# at line {line_number}") from error
            if native_ping < 0 or beam < 0:
                raise ValueError(f"negative N/# at line {line_number}")
            depth_text = fields[5].strip()
            if depth_text.lower() == "nan":
                if check_mode != 3:
                    raise ValueError(f"NaN depth in U0 at line {line_number}")
                depth = math.nan
            else:
                depth = _parse_finite(depth_text, "z")
            lon = _parse_finite(fields[3], "X")
            lat = _parse_finite(fields[4], "Y")
            heading = _parse_finite(fields[6], "H")
            if not -90.0 <= lat <= 90.0 or not 0.0 <= heading < 360.0:
                raise ValueError(f"navigation range failure at line {line_number}")
            yield (
                MblistRow(
                    epoch_seconds_utc=epoch,
                    native_ping_counter=native_ping,
                    beam_index=beam,
                    lon_deg=lon,
                    lat_deg=lat,
                    parser_depth_value=depth,
                    heading_deg=heading,
                ),
                timestamp_us(epoch),
            )


def scan_time_contract(path: Path, *, check_mode: int) -> tuple[int, str | None, str | None]:
    count = 0
    try:
        for _row, _time in iter_mblist_rows(path, check_mode=check_mode):
            count += 1
    except ValueError as error:
        message = str(error)
        if "missing M" in message:
            return count, "TIME_UTC_MISSING", message
        if "invalid M" in message or "sub-microsecond" in message:
            return count, "TIME_UTC_INVALID", message
        return count, "PARSER_CONTRACT_FAILURE", message
    return count, None, None


class ParquetAppender:
    def __init__(self, path: Path, schema: pa.Schema) -> None:
        self.path = path
        self.schema = schema
        self.writer: pq.ParquetWriter | None = None
        self.row_count = 0

    def append(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        table = pa.Table.from_pylist(rows, schema=self.schema)
        if self.writer is None:
            self.writer = pq.ParquetWriter(self.path, self.schema, compression="zstd")
        self.writer.write_table(table)
        self.row_count += len(rows)

    def close(self) -> None:
        if self.writer is None:
            pq.write_table(pa.Table.from_pylist([], schema=self.schema), self.path, compression="zstd")
        else:
            self.writer.close()


def arrow_type(type_name: str) -> pa.DataType:
    if type_name == "string":
        return pa.string()
    if type_name == "int64":
        return pa.int64()
    if type_name == "int32":
        return pa.int32()
    if type_name == "float64":
        return pa.float64()
    if type_name == "bool":
        return pa.bool_()
    if type_name == "list_string":
        return pa.list_(pa.string())
    if type_name == "timestamp_us_UTC":
        return pa.timestamp("us", tz="UTC")
    raise ValueError(f"unsupported output schema type: {type_name}")


def load_output_schemas(schema_path: Path) -> dict[str, pa.Schema]:
    spec = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    output: dict[str, pa.Schema] = {}
    for table_name, table_spec in spec["tables"].items():
        output[table_name] = pa.schema(
            [
                pa.field(field["name"], arrow_type(field["type"]), nullable=bool(field["nullable"]))
                for field in table_spec["fields"]
            ]
        )
    return output


def nmad(values: list[float]) -> float | None:
    if not values:
        return None
    median = statistics.median(values)
    return float(1.4826 * statistics.median([abs(value - median) for value in values]))


def quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(np.quantile(np.asarray(values, dtype=np.float64), q, method="linear"))


def haversine_m(lon_a: float, lat_a: float, lon_b: float, lat_b: float) -> float:
    radius = 6_371_000.0
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    dphi = phi_b - phi_a
    dlambda = math.radians(lon_b - lon_a)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * radius * math.asin(min(1.0, math.sqrt(a)))


@dataclass
class RawRow:
    source_object_id: str
    parser_ping_index: int
    native_ping_counter: int
    beam_index: int
    epoch_us: int
    lon_deg: float
    lat_deg: float
    parser_depth_value: float
    depth_m_positive_down: float | None
    heading_deg: float
    native_quality_state: str


RAW_SCHEMA = pa.schema(
    [
        ("source_object_id", pa.string()),
        ("parser_ping_index", pa.int64()),
        ("native_ping_counter", pa.int64()),
        ("beam_index", pa.int32()),
        ("epoch_us", pa.int64()),
        ("lon_deg", pa.float64()),
        ("lat_deg", pa.float64()),
        ("parser_depth_value", pa.float64()),
        ("depth_m_positive_down", pa.float64()),
        ("heading_deg", pa.float64()),
        ("native_quality_state", pa.string()),
    ]
)


def _raw_row_dict(row: RawRow) -> dict[str, Any]:
    return {
        "source_object_id": row.source_object_id,
        "parser_ping_index": row.parser_ping_index,
        "native_ping_counter": row.native_ping_counter,
        "beam_index": row.beam_index,
        "epoch_us": row.epoch_us,
        "lon_deg": row.lon_deg,
        "lat_deg": row.lat_deg,
        "parser_depth_value": row.parser_depth_value,
        "depth_m_positive_down": row.depth_m_positive_down,
        "heading_deg": row.heading_deg,
        "native_quality_state": row.native_quality_state,
    }


def _u0_db(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE u0 (epoch_us INTEGER, native_ping INTEGER, beam INTEGER, lon REAL, lat REAL, depth REAL, heading REAL, seen INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(epoch_us,native_ping,beam))"
    )
    return connection


def _raw_from_object(
    source_object_id_value: str,
    u3_path: Path,
    u0_path: Path,
    sqlite_path: Path,
    raw_path: Path,
) -> tuple[int, int, str | None, str | None]:
    u3_count, u3_error, u3_detail = scan_time_contract(u3_path, check_mode=3)
    if u3_error:
        return 0, 0, u3_error, u3_detail
    u0_count, u0_error, u0_detail = scan_time_contract(u0_path, check_mode=0)
    if u0_error:
        return 0, 0, u0_error, u0_detail
    database = _u0_db(sqlite_path)
    try:
        insert = "INSERT INTO u0(epoch_us,native_ping,beam,lon,lat,depth,heading) VALUES (?,?,?,?,?,?,?)"
        batch: list[tuple[Any, ...]] = []
        for row, epoch_us in iter_mblist_rows(u0_path, check_mode=0):
            batch.append((epoch_us, row.native_ping_counter, row.beam_index, row.lon_deg, row.lat_deg, row.parser_depth_value, row.heading_deg))
            if len(batch) >= 50_000:
                database.executemany(insert, batch)
                batch.clear()
        if batch:
            database.executemany(insert, batch)
        database.commit()
        appender = ParquetAppender(raw_path, RAW_SCHEMA)
        ping_ordinals: dict[tuple[int, int], int] = {}
        previous_ping_index = -1
        seen_u0 = 0
        row_batch: list[dict[str, Any]] = []
        key_seen: set[tuple[int, int, int]] = set()
        for row, epoch_us in iter_mblist_rows(u3_path, check_mode=3):
            key = (epoch_us, row.native_ping_counter, row.beam_index)
            if key in key_seen:
                raise ValueError(f"duplicate U3 key: {key}")
            key_seen.add(key)
            ping_key = (epoch_us, row.native_ping_counter)
            parser_ping_index = ping_ordinals.setdefault(ping_key, len(ping_ordinals))
            if parser_ping_index < previous_ping_index:
                raise ValueError("U3 parser ping order regressed")
            previous_ping_index = parser_ping_index
            match = database.execute(
                "SELECT lon,lat,depth,heading,seen FROM u0 WHERE epoch_us=? AND native_ping=? AND beam=?",
                key,
            ).fetchone()
            if match is None:
                if math.isnan(row.parser_depth_value):
                    quality = "null"
                    depth = None
                else:
                    quality = "flagged"
                    depth = None
            else:
                if any(
                    abs(left - right) > tolerance
                    for left, right, tolerance in (
                        (row.lon_deg, match[0], 1.0e-10),
                        (row.lat_deg, match[1], 1.0e-10),
                        (row.parser_depth_value, match[2], 1.0e-4),
                        (row.heading_deg, match[3], 1.0e-3),
                    )
                ):
                    raise ValueError(f"U0/U3 value mismatch for key {key}")
                database.execute(
                    "UPDATE u0 SET seen=1 WHERE epoch_us=? AND native_ping=? AND beam=?",
                    key,
                )
                seen_u0 += 1
                quality = "good"
                depth = float(match[2])
            row_batch.append(
                _raw_row_dict(
                    RawRow(
                        source_object_id=source_object_id_value,
                        parser_ping_index=parser_ping_index,
                        native_ping_counter=row.native_ping_counter,
                        beam_index=row.beam_index,
                        epoch_us=epoch_us,
                        lon_deg=normalize_longitude(row.lon_deg),
                        lat_deg=row.lat_deg,
                        parser_depth_value=row.parser_depth_value,
                        depth_m_positive_down=depth,
                        heading_deg=row.heading_deg,
                        native_quality_state=quality,
                    )
                )
            )
            if len(row_batch) >= 50_000:
                appender.append(row_batch)
                row_batch.clear()
        if row_batch:
            appender.append(row_batch)
        missing_u0 = database.execute("SELECT COUNT(*) FROM u0 WHERE seen=0").fetchone()[0]
        if missing_u0:
            raise ValueError(f"U0 keys absent from U3: {missing_u0}")
        database.commit()
        appender.close()
        return u3_count, seen_u0, None, None
    finally:
        database.close()


def ping_review_codes(raw_path: Path) -> dict[int, set[str]]:
    """Compute frozen review rules from one raw object's ordered rows."""
    ping_stats: list[dict[str, Any]] = []
    current_index: int | None = None
    current_rows: list[dict[str, Any]] = []
    reader = pq.ParquetFile(raw_path)
    for batch in reader.iter_batches(batch_size=50_000):
        for row in batch.to_pylist():
            index = int(row["parser_ping_index"])
            if current_index is None:
                current_index = index
            if index != current_index:
                ping_stats.append(_finish_ping(current_index, current_rows))
                current_rows = []
                current_index = index
            current_rows.append(row)
    if current_index is not None:
        ping_stats.append(_finish_ping(current_index, current_rows))
    codes: dict[int, set[str]] = defaultdict(set)
    for previous, current in zip(ping_stats, ping_stats[1:]):
        if current["epoch_us"] < previous["epoch_us"]:
            codes[current["parser_ping_index"]].add("R02_time_nonmonotonic")
        dt = (current["epoch_us"] - previous["epoch_us"]) / 1_000_000.0
        if dt > 0 and haversine_m(previous["lon_deg"], previous["lat_deg"], current["lon_deg"], current["lat_deg"]) / dt > 20.0:
            codes[current["parser_ping_index"]].add("R03_navigation_speed")
    for index, current in enumerate(ping_stats):
        context = [item for item in ping_stats[max(0, index - 5):index] + ping_stats[index + 1:index + 6] if item["median_depth"] is not None]
        if len(context) >= 3 and current["median_depth"] is not None:
            context_values = [item["median_depth"] for item in context]
            context_median = statistics.median(context_values)
            context_nmad = nmad(context_values) or 0.0
            if abs(current["median_depth"] - context_median) > max(1000.0, 10.0 * max(context_nmad, 1.0)):
                codes[current["parser_ping_index"]].add("R05_alongtrack_ping_median_discontinuity")
    return codes


def _finish_ping(index: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible_depths = [
        float(row["depth_m_positive_down"])
        for row in rows
        if row["native_quality_state"] == "good"
        and row["depth_m_positive_down"] is not None
        and math.isfinite(float(row["depth_m_positive_down"]))
        and 0.0 < float(row["depth_m_positive_down"]) <= 12_000.0
    ]
    return {
        "parser_ping_index": index,
        "epoch_us": int(rows[0]["epoch_us"]),
        "lon_deg": float(rows[0]["lon_deg"]),
        "lat_deg": float(rows[0]["lat_deg"]),
        "median_depth": statistics.median(eligible_depths) if eligible_depths else None,
        "nmad": nmad(eligible_depths),
    }


def source_field_ledger(
    official_cruise_id: str,
    object_id: str,
    relative_path: str,
    object_sha256: str,
    command_sha256: str,
    *,
    parsed: bool,
    time_failure: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    direct_fields = {"time_utc", "longitude", "latitude", "heading", "native_quality", "depth", "native_ping_id", "native_beam_id"}
    parser_available = {"time_utc", "longitude", "latitude", "heading", "native_quality", "depth"}
    for field_name in FIELD_NAMES:
        available = bool(parsed and field_name in parser_available)
        if time_failure and field_name == "time_utc":
            status = "known"
            evidence_kind = "parser_preflight_failure"
            note = "M field missing or invalid; source object aborted atomically"
            available = False
        elif available:
            status = "known"
            evidence_kind = "decoded_format58_parser_field"
            note = None
        else:
            status = "officially_unknown"
            evidence_kind = "not_recovered_under_initial_contract"
            note = "No direct evidence read under the initial source-internal contract"
        rows.append(
            {
                "official_cruise_id": official_cruise_id,
                "source_object_id": object_id,
                "source_object_relative_path": relative_path,
                "source_object_sha256": object_sha256,
                "field_name": field_name,
                "field_available": available,
                "field_status": status,
                "evidence_kind": evidence_kind,
                "evidence_path_or_command_sha256": command_sha256 if parsed or time_failure else object_sha256,
                "note": note,
            }
        )
    return rows


def source_processing_row(
    processing_run_id: str,
    acquisition_run_id: str,
    object_record: dict[str, Any],
    object_id: str,
    *,
    body_read_authorized: bool,
    body_read_performed: bool,
    parser_name: str | None,
    parser_version: str | None,
    parser_source_commit: str | None,
    parser_environment_digest: str | None,
    command_sha256: str | None,
    decompressed_sha256: str | None,
    parse_status: str,
    parsed_row_count: int,
    error_code: str | None,
    error_detail: str | None,
) -> dict[str, Any]:
    return {
        "processing_run_id": processing_run_id,
        "acquisition_run_id": acquisition_run_id,
        "source_object_id": object_id,
        "source_object_identity_basis": "acquisition_run_id + '/' + canonical_source_object_relative_path",
        "official_cruise_id": str(object_record["official_cruise_id"]),
        "official_cruise_id_status": "verified_from_source_metadata",
        "source_object_relative_path": str(object_record["relative_path"]),
        "source_object_filename": str(object_record["filename"]),
        "source_object_role": str(object_record["source_object_role"]),
        "source_object_format": str(object_record["format"]),
        "source_object_bytes": int(object_record["bytes"]),
        "source_object_sha256": str(object_record["sha256"]),
        "body_read_authorized": body_read_authorized,
        "body_read_performed": body_read_performed,
        "parser_name": parser_name,
        "parser_version": parser_version,
        "parser_source_commit": parser_source_commit,
        "parser_environment_digest": parser_environment_digest,
        "command_sha256": command_sha256,
        "decompressed_derivative_sha256": decompressed_sha256,
        "parse_status": parse_status,
        "parsed_row_count": int(parsed_row_count),
        "error_code": error_code,
        "error_detail": error_detail,
    }


def sounding_row(
    raw: dict[str, Any],
    processing_run_id: str,
    acquisition_run_id: str,
    object_record: dict[str, Any],
    parser_environment_digest: str,
    parser_command_sha256: str,
    review_codes: set[str],
) -> dict[str, Any]:
    depth = raw["depth_m_positive_down"]
    lon = float(raw["lon_deg"])
    lat = float(raw["lat_deg"])
    native_good = raw["native_quality_state"] == "good"
    depth_ok = depth is not None and math.isfinite(float(depth)) and 0.0 < float(depth) <= 12_000.0
    nav_ok = math.isfinite(lon) and -180.0 <= lon < 180.0 and math.isfinite(lat) and -90.0 <= lat <= 90.0
    failure_codes: list[str] = []
    if not native_good:
        failure_codes.append("H02_NATIVE_NOT_GOOD")
    if not nav_ok:
        failure_codes.append("H03_NAVIGATION_RANGE")
    if not depth_ok:
        failure_codes.append("H04_DEPTH_RANGE")
    hard_pass = not failure_codes
    if nav_ok:
        lon_bin, lat_bin, cell_id = cell_assignment(lon, lat)
    else:
        lon_bin = lat_bin = cell_id = None
    epoch = datetime_from_us(int(raw["epoch_us"]))
    status_known = "known"
    return {
        "processing_run_id": processing_run_id,
        "acquisition_run_id": acquisition_run_id,
        "source_object_id": str(raw["source_object_id"]),
        "source_object_relative_path": str(object_record["relative_path"]),
        "source_object_sha256": str(object_record["sha256"]),
        "official_cruise_id": str(object_record["official_cruise_id"]),
        "official_cruise_id_status": "verified_from_source_metadata",
        "parser_name": "MB-System",
        "parser_version": "5.8.3beta16",
        "parser_source_commit": "1d9a52ce076c3c3c5f0150b9bcaa30fa108c7422",
        "parser_environment_digest": parser_environment_digest,
        "parser_command_sha256": parser_command_sha256,
        "parser_ping_index": int(raw["parser_ping_index"]),
        "parser_ping_index_status": status_known,
        "native_ping_counter": int(raw["native_ping_counter"]),
        "native_ping_counter_status": status_known,
        "native_ping_id": None,
        "native_ping_id_status": "officially_unknown",
        "beam_index": int(raw["beam_index"]),
        "beam_index_status": status_known,
        "native_beam_id": None,
        "native_beam_id_status": "officially_unknown",
        "line_id": None,
        "line_id_status": "officially_unknown",
        "time_utc": epoch,
        "time_utc_status": "known",
        "lon_deg": lon,
        "lon_deg_status": status_known,
        "lat_deg": lat,
        "lat_deg_status": status_known,
        "horizontal_datum": None,
        "horizontal_datum_status": "officially_unknown",
        "parser_depth_value": float(raw["parser_depth_value"]),
        "depth_m_positive_down": float(depth) if depth is not None else None,
        "depth_m_positive_down_status": status_known,
        "elev_m": -float(depth) if depth is not None else None,
        "depth_unit": "m",
        "depth_direction": "positive_down",
        "vertical_datum": None,
        "vertical_datum_status": "officially_unknown",
        "heading_deg": float(raw["heading_deg"]),
        "heading_deg_status": status_known,
        "native_quality_state": str(raw["native_quality_state"]),
        "native_quality_state_status": status_known,
        "native_quality_code": None,
        "native_quality_code_status": "officially_unknown",
        "qc_hard_pass": hard_pass,
        "qc_hard_failure_codes": failure_codes,
        "qc_review_codes": sorted(review_codes),
        "qc_eligible_for_cell": hard_pass,
        "lon_bin": lon_bin,
        "lat_bin": lat_bin,
        "cell_id": cell_id,
        "held_out": True,
        "use_for_training": False,
        "use_for_tuning": False,
        "use_for_threshold_selection": False,
        "role_v2_h": "held_out_candidate_mrar_out",
        "role_v2_w": "blocked_source_independence_unknown",
        "confirmation_role_eligible": False,
    }


def aggregate_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {
            "median": None,
            "mean": None,
            "nmad": None,
            "q25": None,
            "q75": None,
            "min": None,
            "max": None,
            "range": None,
        }
    return {
        "median": float(statistics.median(values)),
        "mean": float(statistics.fmean(values)),
        "nmad": nmad(values),
        "q25": quantile(values, 0.25),
        "q75": quantile(values, 0.75),
        "min": float(min(values)),
        "max": float(max(values)),
        "range": float(max(values) - min(values)),
    }


def query_depths(connection: sqlite3.Connection, cell_id: str, cruise_id: str, object_id: str | None = None) -> list[float]:
    if object_id is None:
        rows = connection.execute(
            "SELECT depth FROM eligible WHERE cell_id=? AND cruise_id=? ORDER BY depth",
            (cell_id, cruise_id),
        )
    else:
        rows = connection.execute(
            "SELECT depth FROM eligible WHERE cell_id=? AND cruise_id=? AND source_object_id=? ORDER BY depth",
            (cell_id, cruise_id, object_id),
        )
    return [float(row[0]) for row in rows]
