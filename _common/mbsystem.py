"""mblist U3/U0 listing parser and join for round-2 swath extraction.

The round-2 L1 extraction (``ncei/swath/extract.py``)
parses each decompressed raw swath file twice with the fixed-version
``mblist`` (5.8.3beta16) from the sealed MB-System environment under
``ncei/derived/scs_v2_sealed_confirmation/environments/``: once with
``-U3`` (every sounding) and once with ``-U0`` (good beams only). This
module parses those two seven-column listings, joins them key-wise in an
SQLite scratch database, and writes one ``raw`` parquet per source file
with the native quality state attached:

- ``good``    key present in U0 (native good beam);
- ``flagged`` key absent from U0 while the U3 depth is finite;
- ``null``    key absent from U0 and the U3 depth is NaN.

The parsing and join logic was extracted from the archived SCS Stage C
processing module
(``ncei/code/scs_confirmation/scs_v2_stage_c_processing.py`` at commit
``bc4cd36``; see ``docs/code_archive.md``). Row-level behaviour — column
contract, error codes, tolerance checks — is unchanged; branches that
served only the sealed-confirmation workflow were dropped.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator

import pyarrow as pa
import pyarrow.parquet as pq


@dataclass(frozen=True)
class MblistRow:
    """One row of an mblist ``-OMN#XYzH`` seven-column listing."""

    epoch_seconds_utc: Decimal
    native_ping_counter: int
    beam_index: int
    lon_deg: float
    lat_deg: float
    parser_depth_value: float
    heading_deg: float


def normalize_longitude(value: float) -> float:
    """Map a finite longitude into [-180, 180)."""
    if not math.isfinite(value):
        raise ValueError("longitude must be finite")
    normalized = ((value + 180.0) % 360.0) - 180.0
    return -180.0 if normalized == 180.0 else normalized


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


def iter_mblist_rows(path: Path, *, check_mode: int) -> Iterator[tuple[MblistRow, int]]:
    """Stream the exact seven-column ASCII HT/LF contract.

    ``check_mode`` mirrors the mblist ``-U`` flag that produced the file:
    3 (all soundings; NaN depths allowed) or 0 (good beams; NaN depths
    rejected). Non-finite navigation is tolerated in both modes and
    surfaced downstream rather than aborting the object.
    """
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
            # Both U3 (check_mode 3) and U0 (check_mode 0) tolerate non-finite
            # X/Y: a non-finite navigation value demotes that single sounding at
            # per-sounding QC (H03) rather than aborting the whole object. The M
            # (time) and z (depth, for U0) parses stay strict below.
            allow_nonfinite_xy = check_mode in (0, 3)
            lon = _parse_finite(fields[3], "X", allow_nan=allow_nonfinite_xy)
            lat = _parse_finite(fields[4], "Y", allow_nan=allow_nonfinite_xy)
            heading = _parse_finite(fields[6], "H")
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
    """Count listing rows; classify a time-contract failure instead of raising."""
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
    """Append rows to one parquet file, creating it on first append."""

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


@dataclass
class RawRow:
    """One joined sounding with its native quality state."""

    source_object_id: str
    parser_ping_index: int
    native_ping_counter: int
    beam_index: int
    epoch_us: int
    lon_deg: float
    lat_deg: float
    u3_navigation_finite: bool
    u0_navigation_finite: bool | None
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
        ("u3_navigation_finite", pa.bool_()),
        ("u0_navigation_finite", pa.bool_()),
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
        "u3_navigation_finite": row.u3_navigation_finite,
        "u0_navigation_finite": row.u0_navigation_finite,
        "parser_depth_value": row.parser_depth_value,
        "depth_m_positive_down": row.depth_m_positive_down,
        "heading_deg": row.heading_deg,
        "native_quality_state": row.native_quality_state,
    }


def _u0_db(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE u0 (epoch_us INTEGER, native_ping INTEGER, beam INTEGER, lon REAL, lat REAL, depth REAL, heading REAL, PRIMARY KEY(epoch_us,native_ping,beam))"
    )
    connection.execute(
        "CREATE TABLE u3 (row_order INTEGER PRIMARY KEY, epoch_us INTEGER, native_ping INTEGER, beam INTEGER, lon REAL, lat REAL, depth REAL, depth_is_nan INTEGER NOT NULL, heading REAL)"
    )
    connection.execute("CREATE UNIQUE INDEX u3_key ON u3(epoch_us,native_ping,beam)")
    return connection


def raw_from_object(
    source_object_id_value: str,
    u3_path: Path,
    u0_path: Path,
    sqlite_path: Path,
    raw_path: Path,
) -> tuple[int, int, str | None, str | None]:
    """Join one object's U3/U0 listings into ``raw_path``.

    Returns ``(u3_rows, joined_u0_rows, error_code, error_detail)``; a
    parser-contract failure is returned as an error code with both output
    files removed instead of leaking partial rows.
    """
    try:
        return _raw_from_object_impl(source_object_id_value, u3_path, u0_path, sqlite_path, raw_path)
    except ValueError as error:
        raw_path.unlink(missing_ok=True)
        sqlite_path.unlink(missing_ok=True)
        return 0, 0, "PARSER_CONTRACT_FAILURE", str(error)


def _raw_from_object_impl(
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
                try:
                    database.executemany(insert, batch)
                except sqlite3.IntegrityError as error:
                    raise ValueError(f"duplicate U0 key: {error}") from error
                finally:
                    batch.clear()
        if batch:
            try:
                database.executemany(insert, batch)
            except sqlite3.IntegrityError as error:
                raise ValueError(f"duplicate U0 key: {error}") from error
        database.commit()
        u3_insert = "INSERT INTO u3(row_order,epoch_us,native_ping,beam,lon,lat,depth,depth_is_nan,heading) VALUES (?,?,?,?,?,?,?,?,?)"
        ping_ordinals: dict[tuple[int, int], int] = {}
        previous_ping_index = -1
        u3_batch: list[tuple[Any, ...]] = []
        row_order = 0
        for row, epoch_us in iter_mblist_rows(u3_path, check_mode=3):
            ping_key = (epoch_us, row.native_ping_counter)
            parser_ping_index = ping_ordinals.setdefault(ping_key, len(ping_ordinals))
            if parser_ping_index < previous_ping_index:
                raise ValueError("U3 parser ping order regressed")
            previous_ping_index = parser_ping_index
            u3_batch.append(
                (
                    row_order,
                    epoch_us,
                    row.native_ping_counter,
                    row.beam_index,
                    row.lon_deg,
                    row.lat_deg,
                    None if math.isnan(row.parser_depth_value) else row.parser_depth_value,
                    int(math.isnan(row.parser_depth_value)),
                    row.heading_deg,
                )
            )
            row_order += 1
            if len(u3_batch) >= 50_000:
                try:
                    database.executemany(u3_insert, u3_batch)
                except sqlite3.IntegrityError as error:
                    raise ValueError(f"duplicate U3 key: {error}") from error
                finally:
                    u3_batch.clear()
        if u3_batch:
            try:
                database.executemany(u3_insert, u3_batch)
            except sqlite3.IntegrityError as error:
                raise ValueError(f"duplicate U3 key: {error}") from error
        database.commit()
        missing_u0 = database.execute(
            "SELECT COUNT(*) FROM u0 LEFT JOIN u3 ON u0.epoch_us=u3.epoch_us AND u0.native_ping=u3.native_ping AND u0.beam=u3.beam WHERE u3.row_order IS NULL"
        ).fetchone()[0]
        if missing_u0:
            raise ValueError(f"U0 keys absent from U3: {missing_u0}")
        appender = ParquetAppender(raw_path, RAW_SCHEMA)
        row_batch: list[dict[str, Any]] = []
        joined = database.execute(
            "SELECT u3.row_order,u3.epoch_us,u3.native_ping,u3.beam,u3.lon,u3.lat,u3.depth,u3.depth_is_nan,u3.heading,u0.lon,u0.lat,u0.depth,u0.heading,u0.rowid AS u0_rowid FROM u3 LEFT JOIN u0 ON u0.epoch_us=u3.epoch_us AND u0.native_ping=u3.native_ping AND u0.beam=u3.beam ORDER BY u3.row_order"
        )
        seen_u0 = 0
        for (
            _row_order,
            epoch_us,
            native_ping,
            beam,
            lon,
            lat,
            parser_depth,
            depth_is_nan,
            heading,
            good_lon,
            good_lat,
            good_depth,
            good_heading,
            u0_rowid,
        ) in joined:
            u3_lon = None if lon is None else float(lon)
            u3_lat = None if lat is None else float(lat)
            u3_nav_ok = u3_lon is not None and math.isfinite(u3_lon) and u3_lat is not None and math.isfinite(u3_lat)
            u0_nav_ok: bool | None = None
            # Branch on key presence, not on good_lon: a U0 row with non-finite
            # navigation is stored with NULL lon/lat in the REAL column, so
            # good_lon is None both for a missing key and for a present key whose
            # nav is NaN. u0_rowid distinguishes the two (NULL only when the key
            # is truly absent from u0).
            if u0_rowid is None:
                quality = "null" if depth_is_nan else "flagged"
                depth = None
            else:
                # Key present: native_quality_state stays "good" even when the
                # U0 or U3 navigation is non-finite (requirement 2). A
                # non-finite navigation is surfaced only as H03 at per-sounding
                # QC, never as a native-quality demotion here.
                u0_lon = None if good_lon is None else float(good_lon)
                u0_lat = None if good_lat is None else float(good_lat)
                u0_nav_ok = u0_lon is not None and math.isfinite(u0_lon) and u0_lat is not None and math.isfinite(u0_lat)
                if any(
                    left is not None and right is not None and abs(left - right) > tolerance
                    for left, right, tolerance in (
                        (u3_lon if u3_nav_ok else None, u0_lon if u0_nav_ok else None, 1.0e-10),
                        (u3_lat if u3_nav_ok else None, u0_lat if u0_nav_ok else None, 1.0e-10),
                        (float(parser_depth), float(good_depth), 1.0e-4),
                        (float(heading), float(good_heading), 1.0e-3),
                    )
                ):
                    raise ValueError(f"U0/U3 value mismatch for key {(epoch_us, native_ping, beam)}")
                seen_u0 += 1
                quality = "good"
                depth = float(good_depth)
            row_batch.append(
                _raw_row_dict(
                    RawRow(
                        source_object_id=source_object_id_value,
                        parser_ping_index=ping_ordinals[(int(epoch_us), int(native_ping))],
                        native_ping_counter=int(native_ping),
                        beam_index=int(beam),
                        epoch_us=int(epoch_us),
                        lon_deg=normalize_longitude(u3_lon) if u3_nav_ok else math.nan,
                        lat_deg=u3_lat if u3_nav_ok else math.nan,
                        u3_navigation_finite=u3_nav_ok,
                        u0_navigation_finite=u0_nav_ok,
                        parser_depth_value=math.nan if depth_is_nan else float(parser_depth),
                        depth_m_positive_down=depth,
                        heading_deg=float(heading),
                        native_quality_state=quality,
                    )
                )
            )
            if len(row_batch) >= 50_000:
                appender.append(row_batch)
                row_batch.clear()
        if row_batch:
            appender.append(row_batch)
        database.commit()
        appender.close()
        if seen_u0 != u0_count:
            raise ValueError(f"U0 join count mismatch: expected {u0_count}, got {seen_u0}")
        return u3_count, seen_u0, None, None
    finally:
        database.close()
