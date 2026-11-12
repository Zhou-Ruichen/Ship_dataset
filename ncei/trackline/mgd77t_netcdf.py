"""Convert explicit MGD77T inputs to isolated, source-preserving NetCDF files."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import netCDF4
import numpy as np
import polars as pl

from .mgd77t import DATA_FIELDS, MGD77TRecords, decode_time, read_header, read_mgd77t


VERSION = "mgd77t_source_preserving_v1"
TIME_UNITS = "seconds since 1970-01-01 00:00:00 +00:00"
NUMERIC_FIELDS = {
    "lon": ("LON", "degrees_east", "Longitude"),
    "lat": ("LAT", "degrees_north", "Latitude"),
    "depth": ("CORR_DEPTH", "m", "Source corrected depth, positive down"),
    "gobs": ("GRA_OBS", "mGal", "Source observed gravity"),
    "faa": ("FREEAIR", "mGal", "Source free-air gravity anomaly"),
    "timezone_correction_hours": ("TIMEZONE", "h", "Hours added to source time to obtain GMT"),
    "bat_ttime": ("BAT_TTIME", "s", "Source bathymetric two-way travel time"),
    "mag_tot": ("MAG_TOT", "nT", "Source magnetic total field, first sensor"),
    "mag_tot2": ("MAG_TOT2", "nT", "Source magnetic total field, second sensor"),
    "mag_res": ("MAG_RES", "nT", "Source magnetic residual field"),
    "mag_dicorr": ("MAG_DICORR", "nT", "Source magnetic diurnal correction"),
    "mag_sdepth": ("MAG_SDEPTH", "m", "Source magnetic sensor depth or altitude"),
    "eotvos": ("EOTVOS", "mGal", "Source Eotvos correction"),
}
CODE_FIELDS = (
    "POS_TYPE", "NAV_QUALCO", "BAT_CPCO", "BAT_TYPCO", "BAT_QUALCO",
    "MAG_RESSEN", "MAG_QUALCO", "GRA_QUALCO",
)
QUALITY_MEANINGS = (
    "good fair poor bad suspected_by_originating_institution suspected_by_data_center"
)
HEADER_ALIASES = {
    "Survey_Identifier": "SURVEY_ID",
    "Format_Acronym": "FORMAT_77",
    "Data_Center_File_Number": "CENTER_ID",
    "Source_Institution": "INST_SRC",
    "Country": "COUNTRY",
    "Platform_Name": "PLATFORM",
    "Gravity_Instrumentation": "GRAV_INSTR",
    "Bathymetry_Instrumentation": "BATH_INSTR",
    "Geodetic_Datum_Position_Determination_Method": "POS_INFO",
    "Bathymetry_Assumed_Sound_Velocity": "SOUND_VEL",
    "Bathymetry_Datum_Code": "VDATUM_CO",
    "Gravity_Theoretical_Formula_Code": "G_FORMU_CO",
    "Gravity_Theoretical_Formula": "GRAV_FORMU",
    "Gravity_Reference_System_Code": "G_RFSYS_CO",
    "Gravity_Reference_System": "GRAV_RFSYS",
    "Gravity_Corrections_Applied": "GRAV_CORR",
}


def read_numeric(variable, n: int | None = None) -> np.ndarray:
    values = np.asarray(np.ma.asarray(variable[:], dtype=float).filled(np.nan))
    if n is not None:
        values = np.broadcast_to(values, (n,))
    return values


def align_legacy_rows(records: MGD77TRecords, legacy_path: str | Path) -> tuple[np.ndarray, dict]:
    """Verify contiguous source-order alignment using every old longitude/latitude.

    Supports identical observation sets or one omitted end observation. No old
    index is shifted until a unique coordinate-verified alignment is established.
    """
    with netCDF4.Dataset(legacy_path) as old:
        old_lon = read_numeric(old["lon"]).reshape(-1)
        old_lat = read_numeric(old["lat"]).reshape(-1)
    n_old = len(old_lon)
    difference = len(records) - n_old
    if difference not in (0, 1):
        raise ValueError(
            f"{legacy_path}: source={len(records)}, legacy={n_old}; "
            "needs an explicit non-contiguous alignment"
        )
    lon, lat = records.numeric("LON"), records.numeric("LAT")
    matches = []
    for start in range(difference + 1):
        source_lon, source_lat = lon[start:start + n_old], lat[start:start + n_old]
        lon_difference = (old_lon - source_lon + 180.0) % 360.0 - 180.0
        lat_difference = old_lat - source_lat
        if (
            np.isfinite(lon_difference).all() and np.isfinite(lat_difference).all()
            and np.all(np.abs(lon_difference) <= 1e-6)
            and np.all(np.abs(lat_difference) <= 1e-6)
        ):
            matches.append((
                start, float(np.max(np.abs(lon_difference))),
                float(np.max(np.abs(lat_difference))),
            ))
    if len(matches) != 1:
        raise ValueError(f"{legacy_path}: expected one coordinate-verified alignment, found {matches}")
    start, max_lon, max_lat = matches[0]
    old_rows = np.full(len(records), -1, dtype=np.int64)
    old_rows[start:start + n_old] = np.arange(n_old, dtype=np.int64)
    return old_rows, {
        "legacy_rows": n_old, "legacy_source_start_index_0based": start,
        "max_legacy_longitude_difference_deg": max_lon,
        "max_legacy_latitude_difference_deg": max_lat,
        "alignment_method": "unique_contiguous_source_order_all_coordinates_atol_1e-6_deg",
    }


def _float_variable(ds, name: str, values: np.ndarray, units: str, long_name: str):
    var = ds.createVariable(name, "f8", ("time",), zlib=True, complevel=4, fill_value=np.nan)
    var[:] = values
    var.units = units
    var.long_name = long_name
    return var


def convert_mgd77t(
    input_path: str | Path,
    output_path: str | Path,
    *,
    header_path: str | Path | None = None,
    source_url: str = "",
    header_url: str = "",
    legacy_netcdf: str | Path | None = None,
    mapping_output: str | Path | None = None,
    overwrite: bool = False,
) -> dict:
    """Convert one whole survey; raw fields, missingness and real zeroes survive."""
    input_path, output_path = Path(input_path).resolve(), Path(output_path).resolve()
    mapping_output = Path(mapping_output).resolve() if mapping_output else None
    protected = {input_path}
    protected.update(Path(path).resolve() for path in (header_path, legacy_netcdf) if path is not None)
    if output_path in protected:
        raise ValueError("output must differ from the source, formal header and legacy NetCDF")
    if mapping_output and mapping_output.suffix not in (".csv", ".parquet"):
        raise ValueError("mapping_output must end in .csv or .parquet")
    if mapping_output in protected | {output_path}:
        raise ValueError("mapping_output must differ from all input files and the NetCDF output")
    for path in (output_path, mapping_output):
        if path is not None and path.exists() and not overwrite:
            raise FileExistsError(path)
    records = read_mgd77t(input_path)
    surveys = {value.strip() for value in records.raw["SURVEY_ID"]}
    if len(surveys) != 1:
        raise ValueError(f"{input_path}: NetCDF conversion requires one survey, found {surveys}")
    survey = surveys.pop()
    header = read_header(header_path, survey) if header_path else None
    time = decode_time(records)
    old_rows = np.full(len(records), -1, dtype=np.int64)
    alignment = {"legacy_rows": 0, "alignment_method": "no_legacy_file_supplied"}
    if legacy_netcdf is not None:
        old_rows, alignment = align_legacy_rows(records, legacy_netcdf)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    with netCDF4.Dataset(temporary, "w", format="NETCDF4") as ds:
        ds.createDimension("time", len(records))
        ds.title = f"Source-preserving MGD77T observations: {survey}"
        ds.conversion_version = VERSION
        ds.history = f"{datetime.now(timezone.utc).isoformat()} MGD77T to NetCDF; no physical reprocessing"
        ds.source_file = str(input_path)
        ds.source_url = source_url
        ds.source_format_specification = "NOAA MGD77T, February 2010, sections III-IV"
        ds.missing_value_policy = "Empty and omitted trailing fields are missing; nonempty numeric values, including zero, are unchanged."
        ds.quality_policy = "All source records and quality codes retained; no source quality selection."
        ds.physical_processing = "No sound-speed, gravity, tide, datum or other physical correction applied by this conversion."
        ds.time_policy = (
            "time is UTC only when DATE, TIME and TIMEZONE are specified and valid. "
            "time_assuming_unspecified_timezone_zero is a separately named compatibility assumption; "
            "unknown TIMEZONE remains empty in source_fields and NaN in timezone_correction_hours."
        )
        ds.source_header_status = "formal_h77t" if header else "not_supplied"
        ds.source_header_file = str(header.source_path) if header else ""
        ds.source_header_url = header_url
        ds.legacy_netcdf_file = str(Path(legacy_netcdf).resolve()) if legacy_netcdf else ""
        ds.legacy_row_missing_value = "-1 means this new observation has no old NetCDF row."
        ds.row_index_conventions = "source_line_1based counts physical lines; all observation and NetCDF row indices are zero-based."
        for key, value in alignment.items():
            ds.setncattr(key, value)
        if header:
            metadata = ds.createGroup("source_header")
            metadata.source_line_1based = header.source_line_1based
            for name, value in header.fields.items():
                metadata.setncattr(name, value)
            for alias, source_name in HEADER_ALIASES.items():
                ds.setncattr(alias, header.fields[source_name])
        else:
            ds.Survey_Identifier = survey
            ds.Source_Institution = ""
        for name, (field, units, long_name) in NUMERIC_FIELDS.items():
            variable = _float_variable(ds, name, records.numeric(field), units, long_name)
            variable.source_field = field
            if name == "depth":
                variable.positive = "down"
                variable.comment = "CORR_DEPTH copied verbatim; correction status is expressed by BAT_CPCO and the formal header."
            if name == "faa":
                variable.ancillary_variables = "GRA_QUALCO"
            if name in ("lon", "lat"):
                variable.standard_name = "longitude" if name == "lon" else "latitude"
        for field in CODE_FIELDS:
            values = records.numeric(field)
            finite = np.isfinite(values)
            if np.any(values[finite] != np.floor(values[finite])):
                raise ValueError(f"{input_path}: non-integer {field}")
            var = ds.createVariable(field, "i4", ("time",), zlib=True, fill_value=-2147483648)
            var[:] = np.where(finite, values, -2147483648).astype(np.int32)
            var.source_field = field
            if field.endswith("_QUALCO"):
                var.flag_values = np.arange(1, 7, dtype=np.int32)
                var.flag_meanings = QUALITY_MEANINGS
        strict = _float_variable(ds, "time", time.utc_seconds, TIME_UNITS, "UTC from specified source date, time and timezone")
        strict.calendar = "proleptic_gregorian"
        strict.standard_name = "time"
        assumed = _float_variable(
            ds, "time_assuming_unspecified_timezone_zero",
            time.assuming_unspecified_timezone_zero_seconds, TIME_UNITS,
            "Compatibility time assuming unspecified source timezone correction is zero",
        )
        assumed.calendar = "proleptic_gregorian"
        assumed.comment = "Assumed UTC only for time_status=2. Missing source DATE or TIME remains missing."
        status = ds.createVariable("time_status", "i1", ("time",), zlib=True)
        status[:] = time.status
        status.flag_values = np.arange(5, dtype=np.int8)
        status.flag_meanings = (
            "date_or_time_unspecified utc_with_specified_timezone "
            "timezone_unspecified invalid_date_or_time invalid_timezone"
        )
        for name, values in (
            ("source_line_1based", records.source_line_1based),
            ("source_observation_index_0based", records.source_observation_index_0based),
            ("source_field_count", records.source_field_count),
            ("new_netcdf_row_0based", np.arange(len(records), dtype=np.int64)),
            ("old_netcdf_row_0based", old_rows),
        ):
            var = ds.createVariable(
                name, "i8", ("time",), zlib=True,
                fill_value=-1 if name == "old_netcdf_row_0based" else False,
            )
            var[:] = values
        raw_group = ds.createGroup("source_fields")
        raw_group.description = "Exact field strings; absent trailing fields padded with empty strings. No field is interpreted as survey metadata."
        for field in DATA_FIELDS:
            encoded = [value.encode("utf-8") for value in records.raw[field]]
            width = max(1, max(map(len, encoded)))
            dimension = f"{field}_nbytes"
            raw_group.createDimension(dimension, width)
            var = raw_group.createVariable(field, "S1", ("time", dimension), zlib=True, complevel=4)
            var[:] = np.asarray(encoded, dtype=f"S{width}").view("S1").reshape(len(records), width)
            var.setncattr("_Encoding", "utf-8")
    temporary.replace(output_path)
    if mapping_output:
        mapping_output.parent.mkdir(parents=True, exist_ok=True)
        table = pl.DataFrame({
            "cruise_id": [survey.lower()] * len(records),
            "source_file": [str(input_path)] * len(records),
            "old_netcdf_file": [str(Path(legacy_netcdf).resolve()) if legacy_netcdf else None] * len(records),
            "new_netcdf_file": [str(output_path)] * len(records),
            "old_netcdf_row_0based": [int(value) if value >= 0 else None for value in old_rows],
            "source_line_1based": records.source_line_1based,
            "source_observation_index_0based": records.source_observation_index_0based,
            "new_netcdf_row_0based": np.arange(len(records), dtype=np.int64),
        })
        if mapping_output.suffix == ".csv":
            table.write_csv(mapping_output)
        elif mapping_output.suffix == ".parquet":
            table.write_parquet(mapping_output)
        else:
            raise ValueError("mapping_output must end in .csv or .parquet")
    faa = records.numeric("FREEAIR")
    depth = records.numeric("CORR_DEPTH")
    return {
        "cruise_id": survey.lower(), "source_file": str(input_path),
        "netcdf_file": str(output_path), "source_rows": len(records),
        "faa_missing": int(np.isnan(faa).sum()), "faa_finite": int(np.isfinite(faa).sum()),
        "faa_true_zero": int((faa == 0).sum()), "depth_missing": int(np.isnan(depth).sum()),
        "time_missing_date_or_time": int((time.status == 0).sum()),
        "time_timezone_unspecified": int((np.char.strip(records.raw["TIMEZONE"]) == "").sum()),
        "time_utc_finite": int(np.isfinite(time.utc_seconds).sum()),
        "formal_header": str(header.source_path) if header else "",
        "source_institution": header.fields["INST_SRC"] if header else "",
        "output_bytes": output_path.stat().st_size, **alignment,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--header", type=Path)
    ap.add_argument("--source-url", default="")
    ap.add_argument("--header-url", default="")
    ap.add_argument("--legacy-netcdf", type=Path)
    ap.add_argument("--mapping-output", type=Path)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args(argv)
    print(convert_mgd77t(
        args.input, args.output, header_path=args.header, source_url=args.source_url,
        header_url=args.header_url, legacy_netcdf=args.legacy_netcdf,
        mapping_output=args.mapping_output, overwrite=args.overwrite,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
