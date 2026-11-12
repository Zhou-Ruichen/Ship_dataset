"""Produce and independently compare an explicit, source-complete legacy FAA batch."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import netCDF4
import numpy as np
import polars as pl

from .mgd77t import DATA_FIELDS, HEADER_FIELDS, read_header, read_mgd77t
from .mgd77t_netcdf import (
    CODE_FIELDS, NUMERIC_FIELDS, TIME_UNITS, align_legacy_rows, convert_mgd77t, read_numeric,
)


def _source_rows(path: Path) -> tuple[list[list[str]], np.ndarray, np.ndarray]:
    """Independent CSV-reader path for checking the conversion products."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        lines = list(csv.reader(handle, delimiter="\t"))
    rows, physical_lines, widths = [], [], []
    for physical_line, row in enumerate(lines, 1):
        if not row or row[0] == "SURVEY_ID":
            continue
        if any(row[len(DATA_FIELDS):]):
            raise ValueError(f"{path}:{physical_line}: unexpected extra field")
        rows.append(row[:len(DATA_FIELDS)] + [""] * max(0, len(DATA_FIELDS) - len(row)))
        physical_lines.append(physical_line)
        widths.append(len(row))
    return rows, np.asarray(physical_lines), np.asarray(widths)


def _numeric(rows: list[list[str]], field: str) -> np.ndarray:
    column = DATA_FIELDS.index(field)
    return np.asarray([float(row[column]) if row[column].strip() else np.nan for row in rows])


def _comparison(track: str, field: str, expected: np.ndarray, actual: np.ndarray) -> dict:
    missing_disagreement = np.isnan(expected) != np.isnan(actual)
    finite = np.isfinite(expected) & np.isfinite(actual)
    delta = np.abs(expected[finite] - actual[finite])
    mismatches = int(np.count_nonzero(~((expected == actual) | (np.isnan(expected) & np.isnan(actual)))))
    if mismatches:
        raise AssertionError(f"{track} {field}: {mismatches} source/product value or missingness differences")
    return {
        "cruise_id": track, "field": field, "rows_checked": len(expected),
        "source_missing": int(np.isnan(expected).sum()),
        "missingness_mismatches": int(missing_disagreement.sum()),
        "value_mismatches": mismatches,
        "max_finite_difference": float(delta.max()) if delta.size else None,
    }


def _independent_time(rows: list[list[str]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    utc = np.full(len(rows), np.nan)
    assumed = np.full(len(rows), np.nan)
    status = np.zeros(len(rows), dtype=np.int8)
    dates = {}
    for i, row in enumerate(rows):
        if not row[2].strip() or not row[3].strip():
            continue
        if row[2] not in dates:
            dates[row[2]] = datetime.strptime(row[2], "%Y%m%d").replace(tzinfo=timezone.utc).timestamp()
        hours, minutes = divmod(float(row[3]), 100)
        if hours < 0 or hours > 24 or minutes < 0 or minutes >= 60 or (hours == 24 and minutes != 0):
            status[i] = 3
            continue
        local = dates[row[2]] + hours * 3600 + minutes * 60
        if row[1].strip():
            correction = float(row[1])
            if not -13 <= correction <= 12:
                status[i] = 4
                continue
            utc[i] = local + correction * 3600
            assumed[i] = utc[i]
            status[i] = 1
        else:
            assumed[i] = local
            status[i] = 2
    return utc, assumed, status


def verify_one(
    track: str, source: Path, header_path: Path, legacy: Path, new: Path,
    mapping_path: Path, previous_fields: pl.DataFrame | None = None,
    previous_alignment: pl.DataFrame | None = None,
) -> tuple[dict, list[dict]]:
    rows, physical_lines, widths = _source_rows(source)
    fields = []
    with netCDF4.Dataset(new) as ds, netCDF4.Dataset(legacy) as old:
        n = len(rows)
        assert len(ds["time"]) == n
        for field, column in zip(DATA_FIELDS, zip(*rows)):
            saved = np.asarray(ds.groups["source_fields"][field][:]).astype(str)
            assert np.array_equal(saved, column), (track, field, "raw string mismatch")
            fields.append({
                "cruise_id": track, "field": f"source_fields/{field}", "rows_checked": n,
                "source_missing": sum(value == "" for value in column),
                "missingness_mismatches": 0, "value_mismatches": 0, "max_finite_difference": None,
            })
        for name, (field, _, _) in NUMERIC_FIELDS.items():
            fields.append(_comparison(track, name, _numeric(rows, field), read_numeric(ds[name])))
        for field in CODE_FIELDS:
            fields.append(_comparison(track, field, _numeric(rows, field), read_numeric(ds[field])))
        utc, assumed, status = _independent_time(rows)
        for name, expected in (("time", utc), ("time_assuming_unspecified_timezone_zero", assumed)):
            actual = read_numeric(ds[name])
            assert np.array_equal(np.isnan(expected), np.isnan(actual)), (track, name)
            good = np.isfinite(expected)
            delta = np.abs(expected[good] - actual[good])
            assert not delta.size or delta.max() <= 1e-6, (track, name, delta.max())
            assert ds[name].units == TIME_UNITS
            fields.append({
                "cruise_id": track, "field": name, "rows_checked": n,
                "source_missing": int(np.isnan(expected).sum()), "missingness_mismatches": 0,
                "value_mismatches": 0, "max_finite_difference": float(delta.max()) if delta.size else None,
            })
        assert np.array_equal(ds["time_status"][:], status)
        assert np.array_equal(ds["source_line_1based"][:], physical_lines)
        assert np.array_equal(ds["source_observation_index_0based"][:], np.arange(n))
        assert np.array_equal(ds["new_netcdf_row_0based"][:], np.arange(n))
        assert np.array_equal(ds["source_field_count"][:], widths)
        mapping = pl.read_parquet(mapping_path)
        assert mapping.height == n
        assert np.array_equal(mapping["source_line_1based"], physical_lines)
        assert np.array_equal(mapping["source_observation_index_0based"], np.arange(n))
        assert np.array_equal(mapping["new_netcdf_row_0based"], np.arange(n))
        old_rows = np.ma.filled(ds["old_netcdf_row_0based"][:], -1)
        assert mapping["old_netcdf_row_0based"].fill_null(-1).to_list() == old_rows.tolist()
        mapped = old_rows >= 0
        ii = old_rows[mapped]
        assert np.array_equal(ii, np.arange(len(old["time"])))
        assert mapping["old_netcdf_row_0based"][0] is None
        assert not mapped[0]
        # Coordinates establish correspondence independently of row-number offsets.
        for name, field in (("lon", "LON"), ("lat", "LAT")):
            before = read_numeric(old[name], len(ii))
            after = _numeric(rows, field)[mapped]
            difference = (before - after + 180) % 360 - 180 if name == "lon" else before - after
            assert np.max(np.abs(difference)) <= 1e-6
        for name, field in (("lon", "LON"), ("lat", "LAT"), ("depth", "CORR_DEPTH"), ("gobs", "GRA_OBS"), ("faa", "FREEAIR")):
            raw = _numeric(rows, field)[mapped]
            before = read_numeric(old[name], len(ii))
            finite = np.isfinite(raw) & np.isfinite(before)
            difference = raw[finite] - before[finite]
            if name == "lon":
                difference = (difference + 180) % 360 - 180
            delta = np.abs(difference)
            assert not delta.size or delta.max() <= 1e-9, (track, name, delta.max())
            if previous_fields is not None:
                prior = previous_fields.filter((pl.col("cruise_id") == track) & (pl.col("variable") == name)).row(0, named=True)
                assert prior["aligned_rows"] == len(ii)
                assert prior["source_missing"] == np.isnan(raw).sum()
                assert prior["source_missing_netcdf_zero"] == ((np.isnan(raw)) & (before == 0)).sum()
                assert prior["true_source_zero"] == (raw == 0).sum()
        old_time = read_numeric(old["time"])
        finite_time = np.isfinite(assumed[mapped])
        delta = np.abs(assumed[mapped][finite_time] - old_time[finite_time])
        assert not delta.size or delta.max() <= 1e-6
        if previous_alignment is not None:
            prior = previous_alignment.filter(pl.col("cruise_id") == track).row(0, named=True)
            assert prior["source_rows"] == n and prior["netcdf_rows"] == len(ii)
            assert prior["source_missing_time"] == int((~np.isfinite(assumed[mapped])).sum())
        with header_path.open(encoding="utf-8-sig", newline="") as handle:
            header_rows = list(csv.reader(handle, delimiter="\t"))
        header_names = tuple(header_rows[0]) if header_rows[0][0] == "SURVEY_ID" else HEADER_FIELDS
        formal = next(row for row in header_rows if row[0].casefold() == track.casefold())
        formal += [""] * (len(header_names) - len(formal))
        for field, expected in zip(header_names, formal):
            assert ds.groups["source_header"].getncattr(field) == expected
        assert ds.Source_Institution == formal[5]
        assert ds["depth"].units == "m" and ds["depth"].positive == "down"
        assert ds["faa"].units == "mGal" and np.isnan(ds["faa"]._FillValue)
        assert np.array_equal(read_numeric(ds["faa"])[0:1], _numeric(rows, "FREEAIR")[0:1], equal_nan=True)
        faa, depth = _numeric(rows, "FREEAIR"), _numeric(rows, "CORR_DEPTH")
        return {
            "cruise_id": track, "source_rows": n, "old_netcdf_rows": len(ii), "new_netcdf_rows": n,
            "first_observation_restored": True, "raw_fields_checked": len(DATA_FIELDS),
            "header_fields_checked": len(header_names), "numeric_fields_checked": len(NUMERIC_FIELDS) + len(CODE_FIELDS),
            "faa_missing": int(np.isnan(faa).sum()), "faa_finite": int(np.isfinite(faa).sum()),
            "faa_true_zero": int((faa == 0).sum()), "depth_missing": int(np.isnan(depth).sum()),
            "utc_missing": int(np.isnan(utc).sum()), "source_time_missing": int((status == 0).sum()),
            "timezone_unspecified": sum(row[1].strip() == "" for row in rows),
            "valid_time_timezone_unspecified": int((status == 2).sum()),
            "old_missing_time_written_epoch_zero": int((~finite_time & (old_time == 0)).sum()),
            "source_institution": ds.Source_Institution,
            "legacy_aligned_faa_missing": int(np.isnan(faa[mapped]).sum()),
            "legacy_missing_faa_written_zero": int((np.isnan(faa[mapped]) & (read_numeric(old["faa"]) == 0)).sum()),
            "restored_first_faa_missing": bool(np.isnan(faa[0])),
            "numeric_and_raw_mismatches": 0,
        }, fields


def verify_used_locations(paired: Path, output_root: Path, expected_path: Path) -> pl.DataFrame:
    used = pl.read_parquet(paired, columns=[
        "region", "cruise_id", "source_row_index", "longitude", "latitude", "faa_ship_mgal",
    ])
    mappings = pl.read_parquet(output_root / "row_mapping.parquet")
    joined = used.join(
        mappings.filter(pl.col("old_netcdf_row_0based").is_not_null()),
        left_on=["cruise_id", "source_row_index"], right_on=["cruise_id", "old_netcdf_row_0based"],
        how="left", validate="m:1",
    )
    assert joined.height == used.height and joined["new_netcdf_row_0based"].null_count() == 0
    products = []
    for track in used["cruise_id"].unique().sort():
        subset = joined.filter(pl.col("cruise_id") == track)
        new_i = subset["new_netcdf_row_0based"].to_numpy()
        old_i = subset["source_row_index"].to_numpy()
        with netCDF4.Dataset(output_root / "netcdf" / f"{track}.nc") as ds:
            faa = read_numeric(ds["faa"])[new_i]
            lon = read_numeric(ds["lon"])[new_i]
            lat = read_numeric(ds["lat"])[new_i]
            legacy = Path(ds.legacy_netcdf_file)
        with netCDF4.Dataset(legacy) as old:
            before = read_numeric(old["faa"])[old_i]
        assert np.allclose(before, subset["faa_ship_mgal"], rtol=0, atol=1e-9, equal_nan=True)
        longitude_difference = (lon - subset["longitude"].to_numpy() + 180) % 360 - 180
        assert np.all(np.abs(longitude_difference) <= 1e-6)
        assert np.allclose(lat, subset["latitude"], rtol=0, atol=1e-6)
        products.append(subset.with_columns(
            pl.Series("faa_revised_mgal", faa, nan_to_null=True),
            pl.Series("source_faa_missing", np.isnan(faa)),
            pl.Series("source_faa_true_zero", faa == 0),
        ))
    result = pl.concat(products)
    result.rename({
        "source_row_index": "old_netcdf_row_0based",
        "faa_ship_mgal": "faa_legacy_mgal",
        "longitude": "longitude_legacy",
        "latitude": "latitude_legacy",
    }).write_parquet(output_root / "used_locations_remapped.parquet")
    counts = result.group_by(["region", "cruise_id"]).agg(
        pl.len().alias("saved_locations"),
        (pl.col("faa_ship_mgal") == 0).sum().alias("saved_zero_faa"),
        pl.col("source_faa_missing").sum().alias("source_missing_faa"),
        (pl.col("source_faa_missing") & (pl.col("faa_ship_mgal") == 0)).sum().alias("missing_written_as_zero"),
        pl.col("source_faa_true_zero").sum().alias("true_zero_faa"),
        (~pl.col("source_faa_missing")).sum().alias("source_finite_faa"),
    ).sort(["region", "cruise_id"])
    expected = pl.read_csv(expected_path).sort(["region", "cruise_id"])
    assert counts.rows() == expected.select(counts.columns).rows()
    counts.write_csv(output_root / "used_location_comparison.csv")
    return counts


def inventory_complete_sources(static_root: Path, legacy_root: Path, output: Path) -> pl.DataFrame:
    matches = []
    for source in sorted(static_root.glob("*/*.m77t")):
        legacy = legacy_root / f"{source.stem.lower()}.nc"
        if not legacy.exists():
            continue
        records = read_mgd77t(source)
        header_path = source.with_suffix(".h77t")
        header = read_header(header_path, records.raw["SURVEY_ID"][0])
        with netCDF4.Dataset(legacy) as ds:
            n_old = len(ds["time"])
        try:
            _, alignment = align_legacy_rows(records, legacy)
            state = alignment["alignment_method"]
            start = alignment["legacy_source_start_index_0based"]
        except ValueError as error:
            state, start = str(error), None
        matches.append({
            "cruise_id": source.stem.lower(), "source_file": str(source.resolve()),
            "formal_header": str(header_path.resolve()), "source_bytes": source.stat().st_size,
            "source_observations": len(records), "legacy_netcdf": str(legacy.resolve()),
            "legacy_observations": n_old, "source_institution": header.fields["INST_SRC"],
            "coordinate_alignment": state, "legacy_source_start_index_0based": start,
            "rebuilt_this_batch": False,
        })
    table = pl.DataFrame(matches)
    table.write_csv(output / "additional_complete_source_inventory.csv")
    return table


def summarize_source_codes(output_root: Path) -> pl.DataFrame:
    """Report original code states, including unspecified codes, without selection."""
    counts = []
    for path in sorted((output_root / "netcdf").glob("*.nc")):
        with netCDF4.Dataset(path) as ds:
            for field in CODE_FIELDS:
                codes, numbers = np.unique(ds.groups["source_fields"][field][:], return_counts=True)
                for code, number in zip(codes, numbers):
                    counts.append({
                        "cruise_id": path.stem, "field": field, "source_code": str(code),
                        "source_state": "unspecified" if not str(code).strip() else "specified",
                        "observations": int(number),
                    })
    table = pl.DataFrame(counts)
    table.write_csv(output_root / "source_code_counts.csv")
    return table


def process_additional_inventory(args) -> int:
    root = args.output_root
    root.mkdir(parents=True, exist_ok=True)
    inventory = pl.read_csv(args.additional_inventory)
    manifest, comparisons, fields, mappings = [], [], [], []
    for item in inventory.to_dicts():
        track = item["cruise_id"]
        source, header, legacy = (Path(item[key]) for key in ("source_file", "formal_header", "legacy_netcdf"))
        new = root / "netcdf" / f"{track}.nc"
        mapping = root / "row_mapping" / f"{track}.parquet"
        if not args.verify_only:
            manifest.append(convert_mgd77t(
                source, new, header_path=header, legacy_netcdf=legacy,
                mapping_output=mapping, overwrite=args.overwrite,
            ))
        row, field_rows = verify_one(track, source, header, legacy, new, mapping)
        assert row["source_rows"] == item["source_observations"]
        assert row["old_netcdf_rows"] == item["legacy_observations"]
        comparisons.append(row)
        fields.extend(field_rows)
        mappings.append(pl.read_parquet(mapping))
        print(f"{track}: {row['source_rows']} records compared; FAA missing={row['faa_missing']}", flush=True)
    if manifest:
        pl.DataFrame(manifest).write_csv(root / "conversion_manifest.csv")
    pl.concat(mappings).write_parquet(root / "row_mapping.parquet")
    pl.DataFrame(comparisons).write_csv(root / "cruise_comparison.csv")
    pl.DataFrame(fields).write_csv(root / "field_comparison.csv")
    inventory.with_columns(pl.lit(True).alias("rebuilt_this_batch")).write_csv(root / "source_inventory.csv")
    summarize_source_codes(root)
    counters = (
        "source_rows", "old_netcdf_rows", "new_netcdf_rows", "faa_missing", "faa_finite",
        "faa_true_zero", "depth_missing", "utc_missing", "source_time_missing",
        "timezone_unspecified", "valid_time_timezone_unspecified",
        "old_missing_time_written_epoch_zero", "legacy_aligned_faa_missing",
        "legacy_missing_faa_written_zero", "restored_first_faa_missing",
    )
    summary = {"cruises": len(comparisons), **{
        name: sum(row[name] for row in comparisons) for name in counters
    }, "restored_first_observations": len(comparisons), "numeric_raw_time_mapping_mismatches": 0}
    (root / "comparison_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-root", type=Path)
    ap.add_argument("--metadata-root", type=Path)
    ap.add_argument("--legacy-root", type=Path)
    ap.add_argument("--output-root", type=Path, required=True)
    ap.add_argument("--paired-locations", type=Path)
    ap.add_argument("--static-root", type=Path)
    ap.add_argument("--additional-inventory", type=Path, help="Convert the complete-source inventory independently of the original 15-cruise evidence.")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args(argv)
    if args.additional_inventory:
        return process_additional_inventory(args)
    if any(getattr(args, name) is None for name in (
        "source_root", "metadata_root", "legacy_root", "paired_locations", "static_root",
    )):
        ap.error("the original batch requires source, metadata, legacy and static roots and paired locations")
    root = args.output_root
    root.mkdir(parents=True, exist_ok=True)
    previous_fields = pl.read_csv(args.source_root.parent / "legacy_field_comparison.csv")
    previous_alignment = pl.read_csv(args.source_root.parent / "legacy_track_alignment.csv")
    manifest, comparisons, field_checks, mappings = [], [], [], []
    for item in json.loads((args.source_root / "download_plan.json").read_text()):
        track = item["cruise"]
        source = args.source_root / f"{track}.m77t"
        header = args.metadata_root / f"{track}.h77t"
        legacy = args.legacy_root / f"{track}.nc"
        new = root / "netcdf" / f"{track}.nc"
        mapping = root / "row_mapping" / f"{track}.parquet"
        if not args.verify_only:
            manifest.append(convert_mgd77t(
                source, new, header_path=header, source_url=item["url"],
                header_url=item["url"].replace(".m77t", ".h77t"),
                legacy_netcdf=legacy, mapping_output=mapping, overwrite=args.overwrite,
            ))
        row, fields = verify_one(
            track, source, header, legacy, new, mapping, previous_fields, previous_alignment,
        )
        comparisons.append(row)
        field_checks.extend(fields)
        mappings.append(pl.read_parquet(mapping))
        print(f"{track}: {row['new_netcdf_rows']} records compared; FAA missing={row['faa_missing']}", flush=True)
    if manifest:
        pl.DataFrame(manifest).write_csv(root / "conversion_manifest.csv")
    pl.concat(mappings).write_parquet(root / "row_mapping.parquet")
    pl.DataFrame(comparisons).write_csv(root / "cruise_comparison.csv")
    pl.DataFrame(field_checks).write_csv(root / "field_comparison.csv")
    used = verify_used_locations(
        args.paired_locations, root, args.source_root.parent / "legacy_used_location_counts.csv",
    )
    inventory = inventory_complete_sources(args.static_root, args.legacy_root, root)
    summarize_source_codes(root)
    summary = {
        "cruises": len(comparisons),
        "source_observations": sum(row["source_rows"] for row in comparisons),
        "old_netcdf_observations": sum(row["old_netcdf_rows"] for row in comparisons),
        "new_netcdf_observations": sum(row["new_netcdf_rows"] for row in comparisons),
        "faa_missing": sum(row["faa_missing"] for row in comparisons),
        "legacy_aligned_faa_missing": previous_fields.filter(pl.col("variable") == "faa")["source_missing"].sum(),
        "restored_first_observation_faa_missing": sum(row["faa_missing"] for row in comparisons) - previous_fields.filter(pl.col("variable") == "faa")["source_missing"].sum(),
        "faa_finite": sum(row["faa_finite"] for row in comparisons),
        "faa_true_zero": sum(row["faa_true_zero"] for row in comparisons),
        "old_source_missing_time_written_epoch_zero": sum(row["old_missing_time_written_epoch_zero"] for row in comparisons),
        "source_timezone_unspecified": sum(row["timezone_unspecified"] for row in comparisons),
        "valid_source_time_timezone_unspecified": sum(row["valid_time_timezone_unspecified"] for row in comparisons),
        "new_utc_missing": sum(row["utc_missing"] for row in comparisons),
        "used_locations": used["saved_locations"].sum(),
        "used_source_faa_missing": used["source_missing_faa"].sum(),
        "used_source_faa_finite": used["source_finite_faa"].sum(),
        "used_source_faa_true_zero": used["true_zero_faa"].sum(),
        "additional_complete_sources": inventory.height,
        "numeric_raw_time_mapping_mismatches": 0,
    }
    (root / "comparison_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
