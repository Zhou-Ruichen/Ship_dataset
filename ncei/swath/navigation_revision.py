"""Source completeness and all-record comparisons for the navigation revision."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from itertools import zip_longest
from pathlib import Path
from urllib.parse import unquote, urlparse

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from ncei.trackline.file_cells import aggregate_track_file, point_selection_mask
from . import batch, extract
from .quality_revision import combined_cells

OLD_ROOT = extract.OUT_ROOT / "_runs/20261021_quality_revision"
FIRST_DOWNLOAD = extract.OUT_ROOT / "_runs/20261019T195752Z_first_batch"
REVISION_ROOT = extract.REPO_ROOT / "ncei/derived/processing_revision_20261025/swath"
CRUISES = ["HNRO07RR", "NT05-06", "RR1412", "AII8L18", "HNRO05RR", "HNRO06RR"]
CASES = [
    ("NT05-06", "53c68499f582da86", 0),
    ("HNRO07RR", "9851abb37f3e8ea6", 1370),
    ("RR1412", "9bc4e705ecd998d8", 0),
]
POLICY = batch.NAVIGATION_POLICY


def save_table(frame: pd.DataFrame, stem: Path) -> None:
    frame.to_parquet(stem.with_suffix(".parquet"), index=False)
    frame.to_csv(stem.with_suffix(".tsv"), sep="\t", index=False)


def audit_inputs(output_root: Path, cruises: list[str]) -> None:
    log_path = extract.REPO_ROOT / "ncei/manifests/round2_download_log.parquet"
    log = pd.read_parquet(log_path)
    retained = pd.read_csv(FIRST_DOWNLOAD / "completeness_manifest.tsv", sep="\t").set_index("cruise")
    gzip_preflight = pd.read_csv(FIRST_DOWNLOAD / "gzip_preflight.tsv", sep="\t")
    checks, summaries = [], []
    for cruise in cruises:
        records = log[log.survey_id.eq(cruise) & log.channel.eq("platforms_tree")]
        complete = records[records.status.str.startswith("first_batch_complete:", na=False)]
        if len(complete) != 1:
            raise ValueError(f"{cruise}: no unique first-batch download completion record")
        expected = int(complete.iloc[0].status.split(":")[1])
        ok = records[records.status.eq("ok")]
        if ok.source_url.nunique() != expected or retained.loc[cruise, "status"] != "complete":
            raise ValueError(f"{cruise}: retained completeness and download enumeration disagree")
        manifest = batch.input_manifest(cruise, extract.OUT_ROOT, True)
        gzip_checks = gzip_preflight[gzip_preflight.cruise.eq(cruise)]
        if len(gzip_checks) != len(manifest) or not gzip_checks.gzip_t_rc.eq(0).all():
            raise ValueError(f"{cruise}: retained gzip preflight does not cover all inputs")
        for record in ok.itertuples():
            tail = unquote(urlparse(record.source_url).path).split("/platforms/ocean/ships/")[1]
            ship, name, tail = tail.split("/", 2)
            tail = tail.split("/MB/", 1)[1] if "/MB/" in tail else tail.removeprefix("multibeam/")
            source = extract.RAW_ROOT / ship / name / tail
            actual = source.stat().st_size if source.is_file() else None
            checks.append({
                "cruise": cruise, "source_url": record.source_url,
                "source_path": str(source), "expected_bytes": record.bytes,
                "actual_bytes": actual, "complete": actual == record.bytes,
            })
        source_dir = extract.RAW_ROOT / Path(manifest.source_relpath.iloc[0]).parts[0] / cruise
        parts = list(source_dir.rglob("*.part"))
        if parts:
            raise ValueError(f"{cruise}: incomplete source files: {parts}")
        projections = [
            extract.projection_sidecar(extract.RAW_ROOT / row.source_relpath, int(row.mb_format))
            for row in manifest.itertuples()
        ]
        old_bytes = sum(p.stat().st_size for p in (OLD_ROOT / cruise).rglob("*.parquet"))
        old_bytes += sum(p.stat().st_size for p in (extract.OUT_ROOT / cruise / "_staging").glob("*.parquet"))
        summaries.append({
            "cruise": cruise, "completion_record": complete.iloc[0].status,
            "expected_files_including_auxiliary": expected, "raw_source_files": len(manifest),
            "projection_files": sum(p is not None for p in projections),
            "part_files": 0,
            "source_bytes": sum((extract.RAW_ROOT / p).stat().st_size for p in manifest.source_relpath),
            "old_product_bytes": old_bytes, "estimated_new_product_bytes": 2 * old_bytes,
            "retained_completeness_path": str(FIRST_DOWNLOAD / "completeness_manifest.tsv"),
            "gzip_preflight_path": str(FIRST_DOWNLOAD / "gzip_preflight.tsv"),
            "retained_gzip_check_all_pass": True,
        })
    frame = pd.DataFrame(checks)
    save_table(frame, output_root / "input_integrity")
    frame[~frame.complete].to_csv(output_root / "input_integrity_missing.tsv", sep="\t", index=False)
    pd.DataFrame(summaries).to_csv(output_root / "input_batches.tsv", sep="\t", index=False)
    if not frame.complete.all():
        raise ValueError("incomplete inputs; inspect input_integrity_missing.tsv")
    batch.write_json({
        "free_bytes_at_start": shutil.disk_usage(output_root).free,
        "estimated_product_bytes": sum(r["estimated_new_product_bytes"] for r in summaries),
        "estimated_product_bytes_basis": "twice retained L1/L2 and staging bytes; two extraction workers",
        "workers": 2, "blas_threads": 1, "input_integrity_rows": len(frame),
    }, output_root / "resource_estimate.json")


def compare_cases(output_root: Path) -> None:
    rows, comparisons = [], []
    for cruise, key, known_row in CASES:
        manifest = batch.input_manifest(cruise, extract.OUT_ROOT, True)
        record = manifest[manifest.filekey.eq(key)].to_dict("records")[0]
        result = batch.extract_record((cruise, record, output_root / "source_cases"))
        rows.append(result)
        if result["status"] not in {"ok", "skipped_exists"}:
            raise RuntimeError(result)
        old = pd.read_parquet(extract.OUT_ROOT / cruise / "_staging" / f"{key}.parquet")
        new = pd.read_parquet(output_root / "source_cases" / cruise / "_staging" / f"{key}.parquet")
        if len(old) != len(new):
            raise ValueError(f"{cruise}: source case row count changed")
        numeric = ["time_us", "lon", "lat", "depth_raw", "file_ordinal", "point_index_in_file"]
        mismatches = {name: int((~np.isclose(
            old[name], new[name], atol=0, rtol=0, equal_nan=True,
        )).sum()) for name in numeric}
        mismatches["native_quality_state"] = int(old.native_quality_state.ne(new.native_quality_state).sum())
        if any(mismatches.values()):
            raise ValueError(f"{cruise}: source case values changed: {mismatches}")
        point = new.iloc[known_row]
        fields = [
            "time_us", "lon", "lat", "depth_raw", "native_ping_counter", "beam_index",
            "ping_lon", "ping_lat", "valid_ping_navigation", "ping_navigation_reason",
        ]
        detail = {name: point[name].item() if isinstance(point[name], np.generic) else point[name]
                  for name in fields}
        detail["depth_raw"] = float(point.depth_raw) if np.isfinite(point.depth_raw) else None
        if cruise == "NT05-06":
            if not np.isclose(point.lon, 140.3591693493, atol=1e-10, rtol=0):
                raise ValueError("source projection not preserved")
        elif point.ping_lon != 0 or point.ping_lat != 0 or point.valid_ping_navigation:
            raise ValueError("known invalid source ping was not propagated to its beam")
        case_dir = output_root / "source_cases" / cruise
        case_manifest = pd.DataFrame([result])
        summary = extract.merge_cruise(
            cruise, case_manifest, staging_dir=case_dir / "_staging", output_dir=case_dir,
        )
        save_table(case_manifest, case_dir / "extraction_manifest")
        batch.write_json(summary, case_dir / "extraction_summary.json")
        checked_path = extract.REPO_ROOT / summary["points_checked_path"]
        cells_path = case_dir / "file_cells_1min" / checked_path.name
        aggregation = aggregate_track_file(
            input_path=checked_path, output_path=cells_path, track_id=cruise.lower(),
            source_type=f"ncei_mb{result['mb_format']}",
            source_completeness=f"mb{result['mb_format']}_only",
            instrument_class_pred="multibeam", branch="multibeam_ncei",
            manual_review_flag=False, overwrite=True, selection_policy=POLICY,
            batch_size=250_000,
        )
        batch.write_json(aggregation, case_dir / "aggregation_summary.json")
        comparisons.append({
            "cruise": cruise, "filekey": key, "rows": len(new),
            "mismatches": mismatches, "staging_row": known_row,
            "first_or_known_point": detail,
            "n_selected": aggregation["n_selected"], "n_cells": aggregation["n_cells"],
            "points_checked_path": str(checked_path), "file_cells_path": str(cells_path),
        })
    save_table(pd.DataFrame(rows), output_root / "source_case_manifest")
    batch.write_json({"cases": comparisons}, output_root / "source_case_comparison.json")
    source_record = rows[0]
    missing_dir = output_root / "source_cases" / "missing_projection"
    missing_dir.mkdir(exist_ok=True)
    source_copy = missing_dir / Path(source_record["source_path"]).name
    shutil.copyfile(extract.REPO_ROOT / source_record["source_path"], source_copy)
    missing = extract.process_one_file(
        "NT05-06", source_record["file_ordinal"], Path(source_record["relpath"]),
        84, source_record["format_note"], output_root=missing_dir / "output",
        source_path=source_copy,
    )
    if missing["error_code"] != "FileNotFoundError":
        raise ValueError("MB84 source without its projection was not rejected")
    batch.write_json(missing, output_root / "missing_projection_result.json")


def cell_keys(frame: pd.DataFrame, mask: np.ndarray) -> set[int]:
    lon = frame.loc[mask, "lon"].to_numpy()
    lat = frame.loc[mask, "lat"].to_numpy()
    keys = np.floor((lat + 90) * 60).astype(np.int64) * 21601
    keys += np.floor((lon + 180) * 60).astype(np.int64)
    return set(keys.tolist())


def compare_cruise(cruise_dir: Path, old_root: Path) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    cruise = cruise_dir.name
    old_dir = old_root / cruise
    old_path = next((old_dir / "points_checked").glob("*.parquet"))
    new_path = next((cruise_dir / "points_checked").glob("*.parquet"))
    old_columns = [
        "filekey", "file_ordinal", "staging_row", "point_index_in_file",
        "time", "lon", "lat", "depth_raw", "depth_m_positive_down",
        "native_quality_state", "point_check_pass_basic",
    ]
    new_columns = old_columns + [
        "valid_ping_navigation", "ping_navigation_reason", extract.NAVIGATION_SELECTION_COLUMN,
    ]
    files = {}
    old_reader = pq.ParquetFile(old_path).iter_batches(batch_size=250_000, columns=old_columns)
    new_reader = pq.ParquetFile(new_path).iter_batches(batch_size=250_000, columns=new_columns)
    checked_rows = 0
    for left, right in zip_longest(old_reader, new_reader):
        if left is None or right is None or len(left) != len(right):
            raise ValueError(f"{cruise}: source row counts changed")
        old, new = left.to_pandas(), right.to_pandas()
        for name in old_columns:
            if name in {"lon", "lat", "depth_raw", "depth_m_positive_down"}:
                equal = np.array_equal(old[name].to_numpy(), new[name].to_numpy(), equal_nan=True)
            else:
                equal = np.array_equal(old[name].to_numpy(), new[name].to_numpy())
            if not equal:
                raise ValueError(f"{cruise}: old/new source identity or value differs in {name}")
        if new.valid_ping_navigation.isna().any():
            raise ValueError(f"{cruise}: missing source ping navigation")
        old_selected = point_selection_mask(old, "basic_native_good")
        selected = point_selection_mask(new, POLICY)
        if not np.array_equal(selected, new[extract.NAVIGATION_SELECTION_COLUMN].to_numpy()):
            raise ValueError(f"{cruise}: stored point selection differs from the declared policy")
        near_origin = new.lon.abs().lt(0.1).to_numpy() & new.lat.abs().lt(0.1).to_numpy()
        invalid = ~new.valid_ping_navigation.to_numpy(dtype=bool)
        for (key, ordinal), positions in new.groupby(["filekey", "file_ordinal"], sort=False).indices.items():
            stats = files.setdefault((key, ordinal), {
                "cruise": cruise, "filekey": key, "file_ordinal": int(ordinal),
                "counts": Counter(), "old_cells": set(), "new_cells": set(),
                "old_origin_cells": set(), "new_origin_cells": set(),
            })
            local_old, local_new = old_selected[positions], selected[positions]
            local_invalid, local_origin = invalid[positions], near_origin[positions]
            stats["counts"].update({
                "n_rows": len(positions), "n_old_selected": int(local_old.sum()),
                "n_new_selected": int(local_new.sum()),
                "n_invalid_navigation_beams": int(local_invalid.sum()),
                "n_invalid_navigation_selected_before": int((local_invalid & local_old).sum()),
                "n_old_origin_selected": int((local_origin & local_old).sum()),
                "n_new_origin_selected": int((local_origin & local_new).sum()),
                "n_old_origin_selected_invalid_navigation": int((local_origin & local_old & local_invalid).sum()),
                "n_valid_navigation_beams": int((~local_invalid).sum()),
            })
            group = new.iloc[positions]
            for name, mask in [
                ("old_cells", local_old), ("new_cells", local_new),
                ("old_origin_cells", local_old & local_origin),
                ("new_origin_cells", local_new & local_origin),
            ]:
                stats[name].update(cell_keys(group, mask))
        checked_rows += len(new)
    manifest = pd.read_parquet(cruise_dir / "extraction_manifest.parquet").set_index(["filekey", "file_ordinal"])
    count_names = [
        "n_rows", "n_old_selected", "n_new_selected", "n_invalid_navigation_beams",
        "n_invalid_navigation_selected_before", "n_old_origin_selected", "n_new_origin_selected",
        "n_old_origin_selected_invalid_navigation", "n_valid_navigation_beams",
    ]
    for key, ordinal in manifest.index:
        files.setdefault((key, ordinal), {
            "cruise": cruise, "filekey": key, "file_ordinal": int(ordinal),
            "counts": Counter(dict.fromkeys(count_names, 0)),
            "old_cells": set(), "new_cells": set(),
            "old_origin_cells": set(), "new_origin_cells": set(),
        })
    output = []
    for (key, ordinal), item in files.items():
        record = manifest.loc[(key, ordinal)]
        navigation_path = cruise_dir / "_work" / key / "ping_navigation.parquet"
        navigation = pd.read_parquet(navigation_path)
        if navigation.duplicated(["epoch_us", "native_ping_counter"]).any():
            raise ValueError(f"{cruise}/{key}: ambiguous source ping identity")
        invalid = ~navigation.valid_ping_navigation
        source = extract.RAW_ROOT / record.source_relpath
        body = source.with_suffix("") if source.suffix == ".gz" else source
        source_inf = source.parent / "generated" / f"{body.name}.inf"
        output.append({
            "cruise": cruise, "filekey": key, "file_ordinal": ordinal, **item["counts"],
            "n_source_pings": len(navigation), "n_invalid_navigation_pings": int(invalid.sum()),
            "n_reused_native_ping_counter": len(navigation) - navigation.native_ping_counter.nunique(),
            "n_zero_navigation_pings": int(navigation.ping_navigation_reason.eq("zero_navigation").sum()),
            "n_nonfinite_navigation_pings": int(navigation.ping_navigation_reason.eq("nonfinite").sum()),
            "n_out_of_range_navigation_pings": int(navigation.ping_navigation_reason.eq("out_of_range").sum()),
            "n_old_cells": len(item["old_cells"]), "n_new_cells": len(item["new_cells"]),
            "n_lost_cells": len(item["old_cells"] - item["new_cells"]),
            "n_added_cells": len(item["new_cells"] - item["old_cells"]),
            "n_old_origin_cells": len(item["old_origin_cells"]),
            "n_new_origin_cells": len(item["new_origin_cells"]),
            "old_origin_cell_ids": ";".join(
                f"1min_{value // 21601}_{value % 21601}"
                for value in sorted(item["old_origin_cells"])
            ),
            "new_origin_cell_ids": ";".join(
                f"1min_{value // 21601}_{value % 21601}"
                for value in sorted(item["new_origin_cells"])
            ),
            "source_relpath": record.source_relpath,
            "source_inf_path": str(source_inf) if source_inf.is_file() else None,
            "projection_source_path": record.get("projection_source_path"),
            "projection_definition": record.get("projection_definition"),
            "navigation_path": str(navigation_path), "status": "completed",
            "source_values_compared": True,
        })
    file_table = pd.DataFrame(output).sort_values("file_ordinal").reset_index(drop=True)
    old_cells = pd.read_parquet(next((old_dir / "file_cells_1min").glob("*.parquet")))
    new_cells = pd.read_parquet(next((cruise_dir / "file_cells_1min").glob("*.parquet")))
    cell_comparison = old_cells.merge(new_cells, on="cell_id", how="outer",
                                     suffixes=("_old", "_new"), indicator=True)
    cell_comparison["cruise"] = cruise
    common = cell_comparison._merge.eq("both")
    cell_comparison["median_depth_change_m"] = (
        cell_comparison.median_depth_m_new - cell_comparison.median_depth_m_old
    )
    summary = {"cruise": cruise, "n_files": len(file_table), "n_rows_compared": checked_rows}
    for name in file_table.columns:
        if name.startswith("n_") and name not in {
            "n_old_cells", "n_new_cells", "n_lost_cells", "n_added_cells",
            "n_old_origin_cells", "n_new_origin_cells",
        }:
            summary[name] = int(file_table[name].sum())
    summary.update({
        "n_old_cells": len(old_cells), "n_new_cells": len(new_cells),
        "n_lost_cells": int(cell_comparison._merge.eq("left_only").sum()),
        "n_added_cells": int(cell_comparison._merge.eq("right_only").sum()),
        "n_old_origin_cells": len(set.union(*(f["old_origin_cells"] for f in files.values()))),
        "n_new_origin_cells": len(set.union(*(f["new_origin_cells"] for f in files.values()))),
        "max_common_cell_median_depth_change_m": float(
            cell_comparison.loc[common, "median_depth_change_m"].abs().max()
        ),
        "point_source_value_mismatches": 0, "status": "completed",
        "points_checked_path": str(new_path),
        "file_cells_path": str(next((cruise_dir / "file_cells_1min").glob("*.parquet"))),
    })
    if summary["n_new_selected"] != int(new_cells.n_points_pass.sum()):
        raise ValueError(f"{cruise}: selected soundings do not match the full L2 aggregation")
    if summary["n_old_selected"] - summary["n_new_selected"] != summary["n_invalid_navigation_selected_before"]:
        raise ValueError(f"{cruise}: point selection changed for a reason other than source navigation")
    print(json.dumps(summary, sort_keys=True), flush=True)
    return file_table, summary, cell_comparison


def retained_origin_points(directories: list[Path], output_root: Path) -> None:
    frames = []
    for directory in directories:
        path = next((directory / "points_checked").glob("*.parquet"))
        dataset = ds.dataset(path)
        predicate = (
            ds.field(extract.NAVIGATION_SELECTION_COLUMN)
            & (ds.field("lon") > -0.1) & (ds.field("lon") < 0.1)
            & (ds.field("lat") > -0.1) & (ds.field("lat") < 0.1)
        )
        frame = dataset.to_table(columns=[
            "filekey", "file_ordinal", "staging_row", "time", "lon", "lat",
            "depth_m_positive_down", "native_quality_state", "native_ping_counter",
            "beam_index", "ping_navigation_record_index", "ping_lon", "ping_lat",
            "valid_ping_navigation", "ping_navigation_reason",
        ], filter=predicate).to_pandas()
        frame.insert(0, "cruise", directory.name)
        frames.append(frame)
    save_table(pd.concat(frames, ignore_index=True), output_root / "retained_near_origin_points")


def compare_batches(
    output_root: Path, batch_roots: list[Path], old_root: Path,
    reuse_comparison_root: Path | None = None,
) -> None:
    directories = []
    for root in batch_roots:
        status = json.loads((root / "run_summary.json").read_text())
        if status["status"] != "completed" or status["selection_policy"] != POLICY:
            raise ValueError(f"batch is not complete under {POLICY}: {root}")
        directories += [root / cruise for cruise in status["cruises"]]
    if len({d.name for d in directories}) != len(directories):
        raise ValueError("a cruise occurs in more than one input batch")
    cached = {}
    if reuse_comparison_root is not None:
        record = json.loads((reuse_comparison_root / "comparison_summary.json").read_text())
        if (record["status"] != "completed" or record["old_root"] != str(old_root)
                or record["selection_policy"] != POLICY or record["point_source_value_mismatches"]):
            raise ValueError("saved all-record comparison does not match this revision")
        cached_batches = {Path(path) for path in record["batch_roots"]}
        tables = [pd.read_parquet(reuse_comparison_root / f"{name}_navigation_comparison.parquet")
                  for name in ("file", "cruise", "cell")]
        for directory in directories:
            if directory.parent not in cached_batches:
                continue
            summary = tables[1][tables[1].cruise.eq(directory.name)].to_dict("records")[0]
            current = next((directory / "points_checked").glob("*.parquet"))
            if (str(current) != summary["points_checked_path"]
                    or pq.read_metadata(current).num_rows != summary["n_rows_compared"]):
                raise ValueError(f"{directory.name}: saved comparison references a different L1")
            cached[directory.name] = (
                tables[0][tables[0].cruise.eq(directory.name)].copy(), summary,
                tables[2][tables[2].cruise.eq(directory.name)].copy(),
            )
    results = [
        cached[directory.name] if directory.name in cached else compare_cruise(directory, old_root)
        for directory in directories
    ]
    file_table = pd.concat([r[0] for r in results], ignore_index=True)
    save_table(file_table, output_root / "file_navigation_comparison")
    summaries = pd.DataFrame([r[1] for r in results])
    save_table(summaries, output_root / "cruise_navigation_comparison")
    save_table(pd.concat([r[2] for r in results], ignore_index=True), output_root / "cell_navigation_comparison")
    new_cells = pd.concat([
        pd.read_parquet(next((directory / "file_cells_1min").glob("*.parquet")))
        for directory in directories
    ], ignore_index=True)
    combined = combined_cells(new_cells)
    save_table(combined, output_root / "combined_ncei_cells")
    retained_origin_points(directories, output_root)
    origin_sets = {}
    for version in ("old", "new"):
        origin_sets[version] = {
            cell for text in file_table[f"{version}_origin_cell_ids"]
            for cell in text.split(";") if cell
        }
    batch.write_json({
        "status": "completed", "selection_policy": POLICY,
        "old_root": str(old_root), "batch_roots": [str(root) for root in batch_roots],
        "n_files": int(summaries.n_files.sum()),
        "n_rows_compared": int(summaries.n_rows_compared.sum()),
        "n_old_selected": int(summaries.n_old_selected.sum()),
        "n_new_selected": int(summaries.n_new_selected.sum()),
        "n_invalid_navigation_pings": int(summaries.n_invalid_navigation_pings.sum()),
        "n_invalid_navigation_beams": int(summaries.n_invalid_navigation_beams.sum()),
        "n_old_origin_selected": int(summaries.n_old_origin_selected.sum()),
        "n_new_origin_selected": int(summaries.n_new_origin_selected.sum()),
        "n_old_origin_unique_cells": len(origin_sets["old"]),
        "n_new_origin_unique_cells": len(origin_sets["new"]),
        "n_cruise_cells": len(new_cells), "n_combined_cells": len(combined),
        "point_source_value_mismatches": 0,
        "combined_depth_estimator": "median of cruise-cell medians; unweighted across cruises",
        "reused_comparison_root": str(reuse_comparison_root) if reuse_comparison_root else None,
    }, output_root / "comparison_summary.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("audit", "cases", "compare"))
    parser.add_argument("--output-root", type=Path, default=REVISION_ROOT)
    parser.add_argument("--cruises", nargs="+", default=CRUISES)
    parser.add_argument("--batch-roots", type=Path, nargs="+")
    parser.add_argument("--old-root", type=Path, default=OLD_ROOT)
    parser.add_argument("--reuse-comparison-root", type=Path)
    args = parser.parse_args(argv)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.stage == "audit":
        audit_inputs(root, args.cruises)
    elif args.stage == "cases":
        compare_cases(root)
    else:
        if not args.batch_roots:
            parser.error("compare requires --batch-roots")
        compare_batches(
            root, [p.resolve() for p in args.batch_roots], args.old_root.resolve(),
            args.reuse_comparison_root.resolve() if args.reuse_comparison_root else None,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
