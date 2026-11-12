"""Read MGD77T observations and formal survey headers without discarding fields."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np


DATA_FIELDS = (
    "SURVEY_ID", "TIMEZONE", "DATE", "TIME", "LAT", "LON", "POS_TYPE",
    "NAV_QUALCO", "BAT_TTIME", "CORR_DEPTH", "BAT_CPCO", "BAT_TYPCO",
    "BAT_QUALCO", "MAG_TOT", "MAG_TOT2", "MAG_RES", "MAG_RESSEN",
    "MAG_DICORR", "MAG_SDEPTH", "MAG_QUALCO", "GRA_OBS", "EOTVOS",
    "FREEAIR", "GRA_QUALCO", "LINEID", "POINTID",
)

HEADER_FIELDS = (
    "SURVEY_ID", "FORMAT_77", "CENTER_ID", "PARAMS_CO", "DATE_CREAT",
    "INST_SRC", "COUNTRY", "PLATFORM", "PLAT_TYPCO", "PLAT_TYP", "CHIEF",
    "PROJECT", "FUNDING", "DATE_DEP", "PORT_DEP", "DATE_ARR", "PORT_ARR",
    "NAV_INSTR", "POS_INFO", "BATH_INSTR", "BATH_ADD", "MAG_INSTR",
    "MAG_ADD", "GRAV_INSTR", "GRAV_ADD", "SEIS_INSTR", "SEIS_FRMTS",
    "LAT_TOP", "LAT_BOTTOM", "LON_LEFT", "LON_RIGHT", "BATH_DRATE",
    "BATH_SRATE", "SOUND_VEL", "VDATUM_CO", "BATH_INTRP", "MAG_DRATE",
    "MAG_SRATE", "MAG_TOWDST", "MAG_SNSDEP", "MAG_SNSSEP", "M_REFFL_CO",
    "MAG_REFFLD", "MAG_RF_MTH", "GRAV_DRATE", "GRAV_SRATE", "G_FORMU_CO",
    "GRAV_FORMU", "G_RFSYS_CO", "GRAV_RFSYS", "GRAV_CORR", "G_ST_DEP_G",
    "G_ST_DEP", "G_ST_ARR_G", "G_ST_ARR", "IDS_10_NUM", "IDS_10DEG",
    "ADD_DOC",
)


@dataclass
class MGD77TRecords:
    """One ordered chunk; raw strings retain leading zeroes and unspecified fields."""

    source_path: Path
    raw: dict[str, np.ndarray]
    source_line_1based: np.ndarray
    source_observation_index_0based: np.ndarray
    source_field_count: np.ndarray

    def __len__(self) -> int:
        return len(self.source_line_1based)

    def numeric(self, field: str) -> np.ndarray:
        """Decode explicit values as float64; only empty fields become NaN."""
        return np.fromiter(
            (float(value) if value.strip() else np.nan for value in self.raw[field]),
            dtype=np.float64,
            count=len(self),
        )


@dataclass
class MGD77THeader:
    source_path: Path
    source_line_1based: int
    fields: dict[str, str]


@dataclass
class MGD77TTime:
    utc_seconds: np.ndarray
    assuming_unspecified_timezone_zero_seconds: np.ndarray
    status: np.ndarray


def _pad_fields(parts: list[str], fields: tuple[str, ...], path: Path, line: int) -> list[str]:
    if any(value.strip() for value in parts[len(fields):]):
        raise ValueError(f"{path}:{line}: nonempty fields beyond the {len(fields)} MGD77T fields")
    return parts[:len(fields)] + [""] * max(0, len(fields) - len(parts))


def iter_mgd77t(path: str | Path, chunk_size: int = 100_000) -> Iterator[MGD77TRecords]:
    """Yield every observation, including short records and a headerless first row.

    Line numbers count physical lines from one; observation indices start at zero
    and exclude optional column headings and empty physical lines. Extra trailing
    empty fields are accepted and counted, not interpreted as observations.
    """
    path = Path(path).resolve()
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    rows, lines, counts = [], [], []
    observation_index = 0

    def make_chunk() -> MGD77TRecords:
        values = {
            name: np.asarray(column, dtype=str)
            for name, column in zip(DATA_FIELDS, zip(*rows))
        }
        n = len(lines)
        return MGD77TRecords(
            path, values, np.asarray(lines, dtype=np.int64),
            np.arange(observation_index - n, observation_index, dtype=np.int64),
            np.asarray(counts, dtype=np.int16),
        )

    with path.open(encoding="utf-8-sig", newline="") as handle:
        for line_number, text in enumerate(handle, 1):
            text = text.rstrip("\r\n")
            if not text:
                continue
            parts = text.split("\t")
            if parts[0].strip().upper() == "SURVEY_ID":
                heading = _pad_fields(parts, DATA_FIELDS, path, line_number)
                if tuple(value.strip().upper() for value in heading) != DATA_FIELDS:
                    raise ValueError(f"{path}:{line_number}: unexpected observation column heading")
                continue
            if not parts[0].strip():
                raise ValueError(f"{path}:{line_number}: unspecified survey identifier")
            counts.append(len(parts))
            rows.append(_pad_fields(parts, DATA_FIELDS, path, line_number))
            lines.append(line_number)
            observation_index += 1
            if len(rows) == chunk_size:
                yield make_chunk()
                rows, lines, counts = [], [], []
        if rows:
            yield make_chunk()


def read_mgd77t(path: str | Path) -> MGD77TRecords:
    """Read a whole survey; use iter_mgd77t for large point-table conversions."""
    chunks = list(iter_mgd77t(path))
    if not chunks:
        raise ValueError(f"{path}: no observations")
    if len(chunks) == 1:
        return chunks[0]
    return MGD77TRecords(
        chunks[0].source_path,
        {name: np.concatenate([chunk.raw[name] for chunk in chunks]) for name in DATA_FIELDS},
        np.concatenate([chunk.source_line_1based for chunk in chunks]),
        np.concatenate([chunk.source_observation_index_0based for chunk in chunks]),
        np.concatenate([chunk.source_field_count for chunk in chunks]),
    )


def read_header(
    path: str | Path, survey_id: str, *, allow_survey_id_mismatch: bool = False,
) -> MGD77THeader:
    """Read formal fields, including NOAA's named catalogue extensions.

    Some catalogue exports repeat an identical header/record without a newline,
    or contain a newline inside a text field. The named heading identifies the
    logical record; the original file remains unchanged.
    """
    path = Path(path).resolve()
    text = path.read_text(encoding="utf-8-sig")
    physical = text.splitlines()
    named = bool(physical and len(physical[0].split("\t")) > 1
                 and physical[0].split("\t")[1].strip().upper() == "FORMAT_77")
    if named:
        heading = physical[0]
        names = [value.strip().upper() for value in heading.split("\t")]
        while names and names[-1] == "":
            names.pop()
        if tuple(names[:len(HEADER_FIELDS)]) != HEADER_FIELDS:
            raise ValueError(f"{path}: unexpected formal header column heading")
        if len(set(names)) != len(names) or "" in names:
            raise ValueError(f"{path}: empty or duplicate formal header field name")
        field_names = tuple(names)
        # A repeated complete heading is an exact delimiter, not survey text.
        blocks = text.split(heading)
        records = []
        cursor = 0
        for block in blocks[1:]:
            body = block.strip("\r\n")
            line = text.find(body, cursor) if body else -1
            if not body:
                continue
            cursor = line + len(body)
            records.append((text.count("\n", 0, line) + 1, body.split("\t")))
    else:
        field_names = HEADER_FIELDS
        records = [(line, value.split("\t")) for line, value in enumerate(physical, 1) if value.strip()]
    parsed = []
    for line_number, parts in records:
        if len(parts) < 2 or parts[1].strip().upper() not in {"MGD77T", "MG77T"}:
            raise ValueError(f"{path}:{line_number}: not a formal MGD77T header")
        fields = dict(zip(field_names, _pad_fields(parts, field_names, path, line_number)))
        if not parsed or parsed[-1].fields != fields:
            parsed.append(MGD77THeader(path, line_number, fields))
    matches = [record for record in parsed if record.fields["SURVEY_ID"].strip().casefold() == survey_id.casefold()]
    if not matches and allow_survey_id_mismatch and len(parsed) == 1:
        matches = parsed
    if len(matches) != 1:
        raise ValueError(f"{path}: expected one distinct formal header for {survey_id}, found {len(matches)}")
    return matches[0]


def decode_time(records: MGD77TRecords) -> MGD77TTime:
    """Decode HHMM.decimal-minutes, adding the source timezone correction.

    Status 0: date/time unspecified; 1: UTC with specified timezone; 2: valid
    source date/time with unspecified timezone; 3: invalid date/time; 4: invalid
    timezone. Missing times stay NaN, including in the explicit assumption field.
    """
    import pandas as pd

    date = np.char.strip(records.raw["DATE"])
    time = records.numeric("TIME")
    zone = records.numeric("TIMEZONE")
    midnight = pd.to_datetime(date, format="%Y%m%d", errors="coerce")
    seconds = midnight.to_numpy(dtype="datetime64[ns]").astype(np.int64).astype(float) / 1e9
    seconds[np.asarray(midnight.isna())] = np.nan
    hour = np.floor(time / 100.0)
    minute = time - hour * 100.0
    specified = (date != "") & np.isfinite(time)
    valid = (
        specified & np.isfinite(seconds) & (hour >= 0) & (hour <= 24)
        & (minute >= 0) & (minute < 60) & ((hour < 24) | (minute == 0))
    )
    zone_unspecified = np.char.strip(records.raw["TIMEZONE"]) == ""
    zone_valid = np.isfinite(zone) & (zone >= -13) & (zone <= 12)
    status = np.zeros(len(records), dtype=np.int8)
    status[specified & ~valid] = 3
    status[valid & ~zone_unspecified & ~zone_valid] = 4
    status[valid & zone_unspecified] = 2
    status[valid & zone_valid] = 1
    local_seconds = seconds + hour * 3600.0 + minute * 60.0
    utc = np.full(len(records), np.nan)
    assumed = np.full(len(records), np.nan)
    known = status == 1
    unknown = status == 2
    utc[known] = local_seconds[known] + zone[known] * 3600.0
    assumed[known] = utc[known]
    assumed[unknown] = local_seconds[unknown]
    return MGD77TTime(utc, assumed, status)
