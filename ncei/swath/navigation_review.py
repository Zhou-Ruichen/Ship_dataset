"""Bounded source-navigation reviews without changing released swath products."""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

from ncei.trackline.file_cells import aggregate_points
from . import batch, extract
from .navigation_revision import REVISION_ROOT, save_table
from .quality_revision import cell_point_filters, combined_cells, point_cells

CASES = {
    "HNRO07RR": (
        ("9cc351d9386a1a84", 270, 384, 385, 388),
        ("08f3919303c7af7b", 150, 236, 237, 240),
        ("c7699a5706dc689c", 1170, 1360, 1361, 1366),
    ),
    "HNRO05RR": (("a4778b6cfe3209ba", 0, 173, 174, 178),),
}
PRECEDING_TRACK_ANCHOR = {("HNRO05RR", "a4778b6cfe3209ba"): ("bb4c79475eab436f", 8)}
ORIGINAL_TARGETS = {
    "9cc351d9386a1a84": {388}, "08f3919303c7af7b": {240},
    "c7699a5706dc689c": {1366}, "a4778b6cfe3209ba": {176, 177, 178},
}
PING_KEYS = ["filekey", "ping_navigation_record_index", "epoch_us", "native_ping_counter"]
RESEARCH_POLICY = "basic_native_good_valid_ping_navigation_case_review"
RESEARCH_SELECTION = "point_selected_" + RESEARCH_POLICY
REVIEW_REASON = (
    "source_record_nonzero_transition_after_zero_navigation; "
    "disconnected_from_preceding_and_following_japan_track"
)


def spherical_distance_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Descriptive great-circle distance, not a point-selection threshold."""
    p1, p2 = np.deg2rad([lat1, lat2])
    dl = np.deg2rad(lon2 - lon1)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return float(6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1))))


def source_navigation(path: Path) -> pd.DataFrame:
    """Read navigation directly from fixed-width SB2100DR headers."""
    with gzip.open(path, "rb") as stream:
        raw = stream.read()
    marker = b"SB2100DR\r\n"
    parts = raw.split(marker)
    offset = len(parts[0])
    records = []
    for index, part in enumerate(parts[1:]):
        header = part.split(b"\r\n", 1)[0].decode("ascii")
        stamp = datetime(int(header[:4]), 1, 1, tzinfo=timezone.utc) + timedelta(
            days=int(header[4:7]) - 1, hours=int(header[7:9]),
            minutes=int(header[9:11]), seconds=int(header[11:13]),
            milliseconds=int(header[13:16]),
        )
        lat = int(header[17:19]) + int(header[19:25]) / 10000 / 60
        lon = int(header[26:29]) + int(header[29:35]) / 10000 / 60
        if header[16] not in "NS" or header[25] not in "EW":
            raise ValueError(f"{path}: invalid source hemisphere at DR record {index}")
        delta = stamp - datetime(1970, 1, 1, tzinfo=timezone.utc)
        records.append({
            "ping_navigation_record_index": index,
            "source_epoch_us": (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds,
            "source_ping_lon": -lon if header[25] == "W" else lon,
            "source_ping_lat": -lat if header[16] == "S" else lat,
            "source_dr_byte_offset": offset,
            "source_header_byte_offset": offset + len(marker),
            "source_dr_header": header,
        })
        offset += len(marker) + len(part)
    return pd.DataFrame(records)


def source_context(cruise_dir: Path, key: str, record: pd.Series) -> pd.DataFrame:
    source_path = extract.REPO_ROOT / record.source_path
    nav_path = cruise_dir / "_work" / key / "ping_navigation.parquet"
    nav = pd.read_parquet(nav_path)
    direct = source_navigation(source_path)
    context = nav.merge(direct, on="ping_navigation_record_index", validate="one_to_one")
    if len(context) != len(nav) or len(direct) != len(nav):
        raise ValueError(f"{key}: source DR records and extracted pings do not align")
    if not np.array_equal(context.epoch_us, context.source_epoch_us):
        raise ValueError(f"{key}: source and mblist times differ")
    for column in ("lon", "lat"):
        if not np.allclose(context[f"ping_{column}"], context[f"source_ping_{column}"],
                           atol=1e-10, rtol=0):
            raise ValueError(f"{key}: source and mblist {column} differ")
    context.insert(0, "filekey", key)
    context.insert(1, "file_ordinal", int(record.file_ordinal))
    context["source_path"] = str(source_path)
    context["navigation_path"] = str(nav_path)
    context["source_navigation_suspect"] = False
    context["source_navigation_review_state"] = "context_not_reviewed"
    context["is_original_near_origin_target"] = False
    context["is_original_three_ping_target"] = False
    context["review_reason"] = ""
    return context


def save_review_source_records(review: pd.DataFrame, output_root: Path) -> None:
    """Preserve exact source byte ranges for reviewed pings and track endpoints."""
    records = []
    for row in review.to_dict("records"):
        records.append({**{name: row[name] for name in (
            "filekey", "file_ordinal", "ping_navigation_record_index", "epoch_us",
            "native_ping_counter", "source_path", "source_dr_byte_offset", "source_dr_header",
        )}, "record_role": "invalid_confirmed_source_ping"})
        for prefix in ("track_before_zero_interval", "track_after_transition"):
            records.append({**{name: row[f"{prefix}_{name}"] for name in (
                "filekey", "file_ordinal", "ping_navigation_record_index", "epoch_us",
                "native_ping_counter", "source_path", "source_dr_byte_offset", "source_dr_header",
            )}, "record_role": "bracketing_track_evidence"})
    records = pd.DataFrame(records).drop_duplicates(["filekey", "ping_navigation_record_index"])
    target = output_root / "source_record_ranges"
    target.mkdir(exist_ok=True)
    for path, group in records.groupby("source_path", sort=False):
        with gzip.open(path, "rb") as stream:
            raw = stream.read()
        for index, row in group.iterrows():
            start = int(row.source_dr_byte_offset)
            if raw[start:start + 10] != b"SB2100DR\r\n":
                raise ValueError(f"{path}: source DR byte position changed")
            header = raw[start + 10:].split(b"\r\n", 1)[0].decode("ascii")
            if header != row.source_dr_header:
                raise ValueError(f"{path}: preserved source DR header changed")
            end = raw.find(b"SB2100DR\r\n", start + 10)
            end = len(raw) if end < 0 else end
            output = target / f"{row.filekey}__nav_{row.ping_navigation_record_index}.bin"
            output.write_bytes(raw[start:end])
            records.loc[index, "source_range_end_offset_exclusive"] = end
            records.loc[index, "source_range_bytes"] = end - start
            records.loc[index, "source_range_path"] = str(output)
    for column in ("source_range_end_offset_exclusive", "source_range_bytes"):
        records[column] = records[column].astype(np.int64)
    records["source_range_description"] = "DR marker through before next DR; includes ancillary records"
    save_table(records, output_root / "source_record_ranges")


def review_pings(cruise_dir: Path, output_root: Path) -> pd.DataFrame:
    cruise = cruise_dir.name
    manifest = pd.read_parquet(cruise_dir / "extraction_manifest.parquet").set_index("filekey")
    reviewed, contexts = [], {}
    for key, zero_start, zero_end, first, last in CASES[cruise]:
        record = manifest.loc[key]
        context = source_context(cruise_dir, key, record)
        contexts[key] = context
        if not context.iloc[zero_start:zero_end + 1].ping_navigation_reason.eq("zero_navigation").all():
            raise ValueError(f"{key}: the recorded preceding zero-navigation interval changed")
        if first != zero_end + 1 or not context.iloc[first:last + 1].valid_ping_navigation.all():
            raise ValueError(f"{key}: the recorded nonzero source transition changed")
        zero_start_key, complete_zero_start = key, zero_start
        if zero_start:
            before = context.iloc[zero_start - 1]
        else:
            # This known zero interval crosses file boundaries; never wrap to the last ping.
            anchor_key, anchor_index = PRECEDING_TRACK_ANCHOR[(cruise, key)]
            prior = manifest[
                manifest.file_ordinal.between(manifest.loc[anchor_key].file_ordinal,
                                              record.file_ordinal - 1)
            ].sort_values("file_ordinal")
            for prior_key, prior_record in prior.iterrows():
                preceding = source_context(cruise_dir, prior_key, prior_record)
                contexts[prior_key] = preceding
                tail = preceding.iloc[anchor_index + 1:] if prior_key == anchor_key else preceding
                if not tail.ping_navigation_reason.eq("zero_navigation").all():
                    raise ValueError(f"{prior_key}: the bounded preceding zero interval changed")
            before = contexts[anchor_key].iloc[anchor_index]
            zero_start_key, complete_zero_start = anchor_key, anchor_index + 1
        after = context.iloc[last + 1]
        if (not before.valid_ping_navigation or not after.valid_ping_navigation
                or not int(before.epoch_us) < int(context.iloc[first].epoch_us)
                or not int(context.iloc[last].epoch_us) < int(after.epoch_us)):
            raise ValueError(f"{key}: bracketing track identities or times are invalid")
        suspect = context.ping_navigation_record_index.between(first, last)
        context.loc[suspect, "source_navigation_suspect"] = True
        context.loc[suspect, "source_navigation_review_state"] = "invalid_confirmed"
        context["is_original_near_origin_target"] = context.ping_navigation_record_index.isin(
            ORIGINAL_TARGETS[key],
        )
        if cruise == "HNRO07RR":
            context["is_original_three_ping_target"] = context.is_original_near_origin_target
        context.loc[suspect, "review_reason"] = REVIEW_REASON
        for index in range(first, last + 1):
            row = context.iloc[index].to_dict()
            row.update({
                "source_navigation_invalid_confirmed": True,
                "preceding_zero_start_filekey": zero_start_key,
                "preceding_zero_start_index": complete_zero_start,
                "preceding_zero_end_filekey": key,
                "preceding_zero_end_index": zero_end,
                "local_preceding_zero_start_index": zero_start,
                "review_sequence_first_index": first,
                "review_sequence_last_index": last,
            })
            for prefix, other in (
                ("previous_ping", context.iloc[index - 1]),
                ("next_ping", context.iloc[index + 1]),
                ("track_before_zero_interval", before),
                ("track_after_transition", after),
            ):
                for field in ("filekey", "file_ordinal", "ping_navigation_record_index", "epoch_us",
                              "native_ping_counter", "ping_lon", "ping_lat", "source_path",
                              "source_dr_byte_offset", "source_dr_header"):
                    row[f"{prefix}_{field}"] = other[field]
                row[f"{prefix}_dt_s"] = (int(other.epoch_us) - int(row["epoch_us"])) / 1_000_000
                row[f"{prefix}_distance_km"] = spherical_distance_km(
                    row["ping_lon"], row["ping_lat"], other.ping_lon, other.ping_lat,
                )
            row["bracketing_track_dt_s"] = (int(after.epoch_us) - int(before.epoch_us)) / 1_000_000
            row["bracketing_track_distance_km"] = spherical_distance_km(
                before.ping_lon, before.ping_lat, after.ping_lon, after.ping_lat,
            )
            reviewed.append(row)
    review = pd.DataFrame(reviewed)
    if review.duplicated(PING_KEYS).any():
        raise ValueError("review contains duplicate exact ping identities")
    save_table(review, output_root / "ping_navigation_review")
    save_table(pd.concat(contexts.values(), ignore_index=True), output_root / "source_navigation_context")
    save_review_source_records(review, output_root)
    return review


def add_review_selection(points: pd.DataFrame, review: pd.DataFrame) -> pd.DataFrame:
    points = points.copy()
    points["epoch_us"] = points.time.to_numpy(dtype="datetime64[us]").astype(np.int64)
    keys = pd.MultiIndex.from_frame(points[PING_KEYS])
    reviewed_keys = pd.MultiIndex.from_frame(review[PING_KEYS])
    points["source_navigation_invalid_confirmed"] = keys.isin(reviewed_keys)
    points["source_navigation_review_state"] = np.where(
        points.source_navigation_invalid_confirmed, "invalid_confirmed", "not_reviewed",
    )
    points[RESEARCH_SELECTION] = (
        points[extract.NAVIGATION_SELECTION_COLUMN] & ~points.source_navigation_invalid_confirmed
    )
    return points


def reaggregate(cruise_dir: Path, output_root: Path, review: pd.DataFrame) -> dict:
    checked = next((cruise_dir / "points_checked").glob("*.parquet"))
    cells_path = next((cruise_dir / "file_cells_1min").glob("*.parquet"))
    dataset = ds.dataset(checked)
    predicate = None
    for key, group in review.groupby("filekey", sort=False):
        term = (ds.field("filekey") == key) & ds.field("ping_navigation_record_index").isin(
            group.ping_navigation_record_index.tolist(),
        )
        predicate = term if predicate is None else predicate | term
    points = add_review_selection(dataset.to_table(filter=predicate).to_pandas(), review)
    if not points.source_navigation_invalid_confirmed.all():
        raise ValueError("beam time or native counter differs from its reviewed source ping")
    counts = points.groupby(PING_KEYS, as_index=False).agg(
        n_beams=("staging_row", "size"),
        n_published_selected=(extract.NAVIGATION_SELECTION_COLUMN, "sum"),
        n_research_selected=(RESEARCH_SELECTION, "sum"),
    )
    review = review.merge(counts, on=PING_KEYS, validate="one_to_one")
    if review.n_beams.isna().any():
        raise ValueError("a reviewed source ping has no corresponding beam records")
    points["point_selected_basic_native_good"] = (
        points.point_check_pass_basic & points.native_quality_state.eq("good")
    )
    points["cell_id"] = point_cells(points)
    save_table(points, output_root / "point_selection_overlay")
    save_table(review, output_root / "ping_navigation_review")
    selected = points[extract.NAVIGATION_SELECTION_COLUMN]
    affected_ids = set(points.loc[selected, "cell_id"])
    filters = cell_point_filters(sorted(affected_ids))
    predicate = None
    for terms in filters:
        term = ds.scalar(True)
        for name, operator, value in terms:
            term = term & (ds.field(name) >= value if operator == ">=" else ds.field(name) <= value)
        predicate = term if predicate is None else predicate | term
    predicate = predicate & ds.field(extract.NAVIGATION_SELECTION_COLUMN)
    columns = PING_KEYS[:2] + ["time", "native_ping_counter", "staging_row", "lon", "lat",
                              "depth_m_positive_down", extract.NAVIGATION_SELECTION_COLUMN]
    affected = dataset.to_table(columns=columns, filter=predicate).to_pandas()
    affected["cell_id"] = point_cells(affected)
    affected = affected[affected.cell_id.isin(affected_ids)].copy()
    affected = add_review_selection(affected, review)
    old_cells = pd.read_parquet(cells_path)
    old_affected = old_cells[old_cells.cell_id.isin(affected_ids)].copy()
    recomputed_old = aggregate_points(affected)
    numerical = old_affected.merge(recomputed_old, on="cell_id", suffixes=("_published", "_recomputed"),
                                   validate="one_to_one")
    if len(numerical) != len(affected_ids):
        raise ValueError("affected-cell source selection is incomplete")
    for column in ("n_points_pass", "n_unique_triples", "median_depth_m",
                   "median_depth_m_unique_triples", "iqr_depth_m"):
        if not np.allclose(numerical[f"{column}_published"], numerical[f"{column}_recomputed"],
                           atol=1e-9, rtol=0, equal_nan=True):
            raise ValueError(f"affected-cell source selection differs in {column}")
    changed_cells = aggregate_points(affected[affected[RESEARCH_SELECTION]])
    for column in old_cells.columns.difference(changed_cells.columns):
        values = old_cells[column].unique()
        if len(values) != 1:
            raise ValueError(f"cannot retain a nonconstant cell metadata column: {column}")
        changed_cells[column] = values[0]
    changed_cells = changed_cells[old_cells.columns]
    comparison = old_affected.merge(changed_cells, on="cell_id", how="outer",
                                    suffixes=("_published", "_research"), indicator=True)
    comparison["median_depth_change_m"] = (
        comparison.median_depth_m_research - comparison.median_depth_m_published
    )
    save_table(comparison, output_root / "affected_cell_comparison")
    research_cells = pd.concat([
        old_cells[~old_cells.cell_id.isin(affected_ids)], changed_cells,
    ], ignore_index=True).sort_values("cell_id").reset_index(drop=True)
    research_cells["selection_policy"] = RESEARCH_POLICY
    research_cells["navigation_case_review_affected"] = research_cells.cell_id.isin(affected_ids)
    target = output_root / cruise_dir.name / "file_cells_1min"
    target.mkdir(parents=True, exist_ok=True)
    research_cells.to_parquet(target / cells_path.name, index=False)
    excluded = int(selected.sum())
    if int(old_cells.n_points_pass.sum() - research_cells.n_points_pass.sum()) != excluded:
        raise ValueError("review exclusions and research L2 point counts differ")
    if not np.isfinite(research_cells.median_depth_m).all():
        raise ValueError("research L2 contains invalid median depths")
    near_origin = points.lon.abs().lt(0.1) & points.lat.abs().lt(0.1)
    summary = {
        "status": "completed", "cruise": cruise_dir.name, "selection_policy": RESEARCH_POLICY,
        "published_selection_policy": batch.NAVIGATION_POLICY,
        "published_points_path": str(checked), "published_cells_path": str(cells_path),
        "research_cells_path": str(target / cells_path.name),
        "reviewed_invalid_pings": len(review), "source_files_reviewed": len(CASES[cruise_dir.name]),
        "source_context_pings": len(pd.read_parquet(output_root / "source_navigation_context.parquet")),
        "source_context_files": pd.read_parquet(
            output_root / "source_navigation_context.parquet", columns=["filekey"],
        ).filekey.nunique(),
        "reviewed_ping_beams": len(points), "excluded_published_selected_beams": excluded,
        "original_three_ping_selected_beams": int(review.loc[
            review.is_original_three_ping_target, "n_published_selected"].sum()),
        "original_near_origin_target_selected_beams": int(review.loc[
            review.is_original_near_origin_target, "n_published_selected"].sum()),
        "excluded_near_origin_selected_beams": int((near_origin & selected).sum()),
        "affected_cells": len(affected_ids), "lost_cells": len(affected_ids - set(changed_cells.cell_id)),
        "retained_affected_cells": len(changed_cells),
        "published_selected_beams": int(old_cells.n_points_pass.sum()),
        "research_selected_beams": int(research_cells.n_points_pass.sum()),
        "published_cells": len(old_cells), "research_cells": len(research_cells),
        "affected_selected_beams_before": len(affected),
        "affected_selected_beams_after": int(affected[RESEARCH_SELECTION].sum()),
        "unchanged_cells": int((~old_cells.cell_id.isin(affected_ids)).sum()),
        "other_navigation_review_state": "not_reviewed",
        "review_basis": REVIEW_REASON,
        "distance_unit": "km; spherical radius 6371.0088 km; descriptive only",
        "source_record_offset_unit": "bytes in decompressed source; zero based",
        "source_record_coordinate_comparison_atol_deg": 1e-10,
        "published_products_modified": False,
    }
    batch.write_json(summary, output_root / "review_summary.json")
    return summary


def combine_reviewed_cells(
    output_root: Path, batch_roots: list[Path], comparison_root: Path,
    review_roots: list[Path] | None = None,
) -> dict:
    comparison = json.loads((comparison_root / "comparison_summary.json").read_text())
    if (comparison["status"] != "completed" or comparison["selection_policy"] != batch.NAVIGATION_POLICY
            or {Path(p) for p in comparison["batch_roots"]} != set(batch_roots)):
        raise ValueError("completed navigation comparison does not match the merged batches")
    reviewed, reviews = {}, []
    for root in review_roots or [output_root]:
        record = json.loads((root / "review_summary.json").read_text())
        cruise = record["cruise"]
        if record["status"] != "completed" or cruise in reviewed:
            raise ValueError("review roots must contain distinct completed cruise cases")
        reviewed[cruise] = record
        pings = pd.read_parquet(root / "ping_navigation_review.parquet")
        pings["cruise"] = cruise
        reviews.append(pings)
    frames, cruises = [], []
    for root in batch_roots:
        status = json.loads((root / "run_summary.json").read_text())
        if status["status"] != "completed" or status["selection_policy"] != batch.NAVIGATION_POLICY:
            raise ValueError(f"input batch is not complete under the published selection: {root}")
        for cruise in status["cruises"]:
            cell_path = (
                Path(reviewed[cruise]["research_cells_path"]) if cruise in reviewed
                else next((root / cruise / "file_cells_1min").glob("*.parquet"))
            )
            frames.append(pd.read_parquet(cell_path))
            cruises.append(cruise)
    if not set(reviewed).issubset(cruises) or len(set(cruises)) != len(cruises):
        raise ValueError("reviewed merge requires all reviewed cruises and distinct input cruises")
    combined = combined_cells(pd.concat(frames, ignore_index=True))
    save_table(combined, output_root / "combined_ncei_cells_case_review")
    retained = pd.read_parquet(comparison_root / "retained_near_origin_points.parquet")
    retained[extract.NAVIGATION_SELECTION_COLUMN] = True
    review = pd.concat(reviews, ignore_index=True)
    if review.duplicated(PING_KEYS).any():
        raise ValueError("combined reviews contain duplicate exact ping identities")
    save_table(review, output_root / "ping_navigation_review_combined")
    retained = add_review_selection(retained, review)
    retained = retained[retained[RESEARCH_SELECTION]].copy()
    retained["cell_id"] = point_cells(retained)
    save_table(retained, output_root / "retained_near_origin_points_case_review")
    summary = {
        "status": "completed", "cruises": cruises, "batch_roots": [str(p) for p in batch_roots],
        "comparison_root": str(comparison_root),
        "selection_policy": RESEARCH_POLICY,
        "case_review_cruise": next(iter(reviewed)) if len(reviewed) == 1 else None,
        "case_review_cruises": list(reviewed),
        "review_roots": [str(p) for p in review_roots or [output_root]],
        "reviewed_invalid_pings": len(review),
        "excluded_published_selected_beams": sum(
            record["excluded_published_selected_beams"] for record in reviewed.values()
        ),
        "n_cruise_cells": sum(len(frame) for frame in frames),
        "n_selected_beams": sum(int(frame.n_points_pass.sum()) for frame in frames),
        "n_combined_cells": len(combined),
        "combined_depth_estimator": "median of cruise-cell medians; unweighted across cruises",
        "other_navigation_review_state": "not_reviewed",
        "n_retained_near_origin_selected_beams": len(retained),
        "n_retained_near_origin_pings": len(retained.drop_duplicates(["cruise", *PING_KEYS])),
        "n_retained_near_origin_unique_cells": retained.cell_id.nunique(),
        "retained_near_origin_cruises": sorted(retained.cruise.unique().tolist()),
        "near_origin_definition": "abs(lon)<0.1 and abs(lat)<0.1; descriptive, not a selection rule",
    }
    batch.write_json(summary, output_root / "combined_review_summary.json")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("review", "combine"))
    parser.add_argument("--cruise-dir", type=Path, default=REVISION_ROOT / "first_batch/HNRO07RR")
    parser.add_argument("--output-root", type=Path, default=REVISION_ROOT / "navigation_review")
    parser.add_argument("--batch-roots", type=Path, nargs="+")
    parser.add_argument("--comparison-root", type=Path, default=REVISION_ROOT)
    parser.add_argument("--review-roots", type=Path, nargs="+",
                        help="Completed cruise-case roots; default is this output root.")
    args = parser.parse_args(argv)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.stage == "review":
        pings = review_pings(args.cruise_dir.resolve(), root)
        summary = reaggregate(args.cruise_dir.resolve(), root, pings)
    else:
        if not args.batch_roots:
            parser.error("combine requires --batch-roots")
        summary = combine_reviewed_cells(
            root, [p.resolve() for p in args.batch_roots], args.comparison_root.resolve(),
            [p.resolve() for p in args.review_roots] if args.review_roots else None,
        )
    batch.write_json({"command": [sys.executable, "-m", "ncei.swath", "navigation-case-review",
                                *(sys.argv[2:] if argv is None else argv)]},
                     root / f"{args.stage}_parameters.json")
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
