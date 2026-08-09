#!/usr/bin/env python3
"""Audit retained evidence for the accepted TN352 Stage C processing chain."""

from __future__ import annotations

import argparse
import ast
import collections
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from ncei.code.scs_tn352_audit_common import (
    AUDIT_ROOT,
    CONTRACT_FIELDS,
    CONTRACT_STATUSES,
    HANDOFF_PATH,
    PROTOCOL_PATH,
    REFERENCE_STAGE_C_ROOT,
    REPO_ROOT,
    STAGE_C_ROOT,
    exact_median,
    nmad,
    output_manifest,
    path_record,
    read_json,
    read_jsonl,
    require,
    safe_run_id,
    sha256_file,
    write_contract_tsv,
    write_json,
)


TN352 = "TN352"
OBJECT_0168 = "20260805T230449Z/objects/TN352/em302/0168_20180501_164920_TGT.all.mb58.gz"
OUTPUT_ROLE = "development_only_not_confirmation"
CLASSIFICATION = "official_raw_source_development_label"
EXPECTED_ACCEPTED_HASHES = {
    "sounding_lineage.parquet": "06f5c22d24260af1b690b7d389eff2d94ed8b27847553e366bd5c3567d54708f",
    "cell_cruise_contributors.parquet": "e1e44fab67f1d187859ad38eda9ee36ec941c793eb2d523eb3a11740c367e644",
    "cell_cruise_candidates.parquet": "cc23c17170ad51e1adfa35fad2176e448a0368643240652f81d625140816e214",
    "source_object_processing.parquet": "c3e4a44cfd4d5c0840765229f246723512e3fd00f16e58c98a16e698a51be8de",
    "field_recovery_ledger.parquet": "ea9b0e078ae0e17e00e33e838ab618c998f331d1ab851315cebb2400066484b6",
}
EXPECTED_REFERENCE_HASHES = {
    "sounding_lineage.parquet": "b5870e44e431af471f2d6601c72961f4732852f845422fb14693ff735c90e3e1",
    "cell_cruise_candidates.parquet": "2a5fd921a26fcd96105e13f410f93e3c73300cc5c91b0fcbdb25bad92e60a28e",
    "source_object_processing.parquet": "6de7d63658c6cc829e3f822053aea52be06817e319be09d09c599d3c7b5d4786",
}
PROCESSOR_PATH = REPO_ROOT / "ncei/code/process_scs_v2_stage_c_source_internal.py"
HELPER_PATH = REPO_ROOT / "ncei/code/scs_v2_stage_c_processing.py"
ADAPTER_PATH = REPO_ROOT / "ncei/code/scs_v2_stage_c1_contract.py"


def contract_record(
    item_id: str,
    category: str,
    item: str,
    status: str,
    observed_value: Any,
    *,
    unit: str | None = None,
    evidence_path: Path,
    evidence_locator: str,
    notes: str = "",
) -> dict[str, Any]:
    require(status in CONTRACT_STATUSES, f"invalid contract status: {status}")
    return {
        "contract_item_id": item_id,
        "category": category,
        "item": item,
        "status": status,
        "observed_value": observed_value,
        "unit": unit,
        "evidence_path": str(evidence_path.relative_to(REPO_ROOT)),
        "evidence_locator": evidence_locator,
        "evidence_sha256": sha256_file(evidence_path),
        "notes": notes,
    }


def validate_input_hashes() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for name, expected in EXPECTED_ACCEPTED_HASHES.items():
        path = STAGE_C_ROOT / name
        record = path_record(path, with_schema=True)
        require(record["sha256"] == expected, f"accepted Stage C hash drift: {name}")
        records[f"accepted/{name}"] = record
    for name, expected in EXPECTED_REFERENCE_HASHES.items():
        path = REFERENCE_STAGE_C_ROOT / name
        record = path_record(path, with_schema=True)
        require(record["sha256"] == expected, f"reference Stage C hash drift: {name}")
        records[f"reference/{name}"] = record
    for name, path in {
        "accepted/audit_manifest.json": STAGE_C_ROOT / "audit_manifest.json",
        "accepted/verification.json": STAGE_C_ROOT / "verification.json",
        "accepted/command_ledger.jsonl": STAGE_C_ROOT / "command_ledger.jsonl",
        "accepted/environment.json": STAGE_C_ROOT / "environment.json",
        "accepted/object_access_closure.parquet": STAGE_C_ROOT / "object_access_closure.parquet",
        "handoff": HANDOFF_PATH,
        "support_protocol": PROTOCOL_PATH,
        "stage_c_processor": PROCESSOR_PATH,
        "stage_c_helper": HELPER_PATH,
        "stage_c_adapter": ADAPTER_PATH,
    }.items():
        records[name] = path_record(path, with_schema=path.suffix == ".parquet")
    accepted_verification = read_json(STAGE_C_ROOT / "verification.json")
    require(accepted_verification["status"] == "pass", "accepted Stage C verification is not pass")
    require(not accepted_verification["confirmation_role_eligible"], "accepted Stage C role changed")
    return records


def verify_command_ledger() -> tuple[list[dict[str, Any]], dict[str, dict[str, dict[str, Any]]], dict[str, int]]:
    rows = read_jsonl(STAGE_C_ROOT / "command_ledger.jsonl")
    role_counts = collections.Counter(str(row["role"]) for row in rows)
    expected_roles = {"decompression", "mbinfo", "mblist_u3", "mblist_u0"}
    require(set(role_counts) == expected_roles, f"unexpected command roles: {sorted(role_counts)}")
    require(all(role_counts[role] == 192 for role in expected_roles), "command role count does not close at 192")
    by_object: dict[str, dict[str, dict[str, Any]]] = collections.defaultdict(dict)
    for row in rows:
        role = str(row["role"])
        object_id = str(row["object_id"])
        require(int(row["returncode"]) == 0, f"nonzero command return code: {object_id} {role}")
        require(role not in by_object[object_id], f"duplicate command role: {object_id} {role}")
        argv = [str(value) for value in row["argv"]]
        executable = Path(argv[0]).name
        if role == "decompression":
            require(executable == "gzip" and argv[1:3] == ["-dc", "--"] and len(argv) == 4, "gzip flags differ")
        elif role == "mbinfo":
            require(executable == "mbinfo" and len(argv) == 4, "mbinfo argv shape differs")
            require(argv[2:] == ["-F58", "-X1"] and argv[1].startswith("-I"), "mbinfo flags differ")
        else:
            check_mode = "-U3" if role == "mblist_u3" else "-U0"
            require(executable == "mblist" and len(argv) == 9, f"{role} argv shape differs")
            require(
                argv[2:8] == ["-F58", "-P1", "-L0", "-MA", check_mode, "-OMN#XYzH"]
                and argv[1].startswith("-I")
                and argv[8].startswith("-X"),
                f"{role} flags differ",
            )
        by_object[object_id][role] = row
    for object_id, object_rows in by_object.items():
        require(set(object_rows) == expected_roles, f"per-object command closure failed: {object_id}")
    return rows, by_object, dict(sorted(role_counts.items()))


def scan_processor_executables() -> dict[str, Any]:
    tree = ast.parse(PROCESSOR_PATH.read_text(encoding="utf-8"))
    assigned: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in {"GZIP", "MBINFO", "MBLIST"}:
                assigned[name] = ast.unparse(node.value)
    require(set(assigned) == {"GZIP", "MBINFO", "MBLIST"}, "processor executable bindings differ")
    source = PROCESSOR_PATH.read_text(encoding="utf-8")
    forbidden = ["mbformat", "mbpreprocess", "mbprocess", "mbclean", "mbareaclean"]
    return {
        "assigned_executables": assigned,
        "forbidden_executable_references": {name: source.count(name) for name in forbidden},
    }


def _empty_object_stats() -> dict[str, int]:
    return {
        "n_soundings_all": 0,
        "n_native_good": 0,
        "n_native_flagged": 0,
        "n_native_null": 0,
        "n_navigation_valid": 0,
        "n_navigation_invalid": 0,
        "n_h02": 0,
        "n_h03": 0,
        "n_h04": 0,
        "n_qc_eligible": 0,
        "n_review": 0,
    }


def scan_tn352_soundings() -> tuple[dict[str, Any], dict[str, dict[str, int]], dict[str, dict[str, Any]]]:
    dataset = ds.dataset(STAGE_C_ROOT / "sounding_lineage.parquet", format="parquet")
    scanner = dataset.scanner(
        columns=[
            "source_object_id",
            "native_quality_state",
            "navigation_valid",
            "depth_m_positive_down",
            "qc_eligible_for_cell",
            "qc_review_codes",
            "lon_deg",
            "lat_deg",
            "cell_id",
        ],
        filter=ds.field("official_cruise_id") == TN352,
        batch_size=262_144,
        use_threads=True,
    )
    totals = {"soundings": 0, "eligible": 0, "scs_soundings": 0, "scs_eligible": 0}
    object_stats: dict[str, dict[str, int]] = collections.defaultdict(_empty_object_stats)
    recovered: dict[str, dict[str, Any]] = collections.defaultdict(
        lambda: {"n_all": 0, "n_eligible": 0, "eligible_depths": []}
    )
    for batch in scanner.to_batches():
        names = batch.schema.names
        encoded = pc.dictionary_encode(batch.column(names.index("source_object_id")))
        ids = encoded.dictionary.to_pylist()
        codes = encoded.indices.to_numpy(zero_copy_only=False)
        quality = np.asarray(batch.column(names.index("native_quality_state")).to_pylist(), dtype=object)
        navigation = batch.column(names.index("navigation_valid")).to_numpy(zero_copy_only=False)
        depth = batch.column(names.index("depth_m_positive_down")).to_numpy(zero_copy_only=False)
        eligible = batch.column(names.index("qc_eligible_for_cell")).to_numpy(zero_copy_only=False)
        review_count = pc.list_value_length(batch.column(names.index("qc_review_codes"))).to_numpy(zero_copy_only=False)
        lon = batch.column(names.index("lon_deg")).to_numpy(zero_copy_only=False)
        lat = batch.column(names.index("lat_deg")).to_numpy(zero_copy_only=False)
        scs = (lon >= 105.0) & (lon < 125.0) & (lat >= 0.0) & (lat < 25.0)
        depth_ok = np.isfinite(depth) & (depth > 0.0) & (depth <= 12_000.0)
        totals["soundings"] += batch.num_rows
        totals["eligible"] += int(np.count_nonzero(eligible))
        totals["scs_soundings"] += int(np.count_nonzero(scs))
        totals["scs_eligible"] += int(np.count_nonzero(scs & eligible))
        masks = {
            "n_soundings_all": np.ones(batch.num_rows, dtype=bool),
            "n_native_good": quality == "good",
            "n_native_flagged": quality == "flagged",
            "n_native_null": quality == "null",
            "n_navigation_valid": navigation,
            "n_navigation_invalid": ~navigation,
            "n_h02": quality != "good",
            "n_h03": ~navigation,
            "n_h04": ~depth_ok,
            "n_qc_eligible": eligible,
            "n_review": review_count > 0,
        }
        for code, object_id in enumerate(ids):
            object_mask = codes == code
            stats = object_stats[str(object_id)]
            for key, mask in masks.items():
                stats[key] += int(np.count_nonzero(object_mask & mask))
            if object_id == OBJECT_0168:
                cells = batch.column(names.index("cell_id")).to_pylist()
                for index in np.flatnonzero(object_mask):
                    cell_id = cells[int(index)]
                    if cell_id is None:
                        continue
                    item = recovered[str(cell_id)]
                    item["n_all"] += 1
                    if bool(eligible[int(index)]):
                        item["n_eligible"] += 1
                        item["eligible_depths"].append(float(depth[int(index)]))
    return totals, dict(object_stats), dict(recovered)


def count_all_eligible() -> int:
    dataset = ds.dataset(STAGE_C_ROOT / "sounding_lineage.parquet", format="parquet")
    total = 0
    for batch in dataset.scanner(columns=["qc_eligible_for_cell"], batch_size=1_048_576).to_batches():
        total += int(pc.sum(batch.column(0)).as_py())
    return total


def candidate_maps(root: Path) -> dict[str, dict[str, Any]]:
    table = pq.read_table(
        root / "cell_cruise_candidates.parquet",
        filters=[("official_cruise_id", "=", TN352)],
    )
    return {str(row["cell_id"]): row for row in table.to_pylist()}


def compare_candidates(
    old: dict[str, dict[str, Any]], new: dict[str, dict[str, Any]]
) -> tuple[list[str], list[str], list[str]]:
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(
        cell_id
        for cell_id in set(old) & set(new)
        if float(old[cell_id]["median_depth_m_positive_down_exact"])
        != float(new[cell_id]["median_depth_m_positive_down_exact"])
    )
    return added, removed, changed


def collect_cell_depths(path: Path, cells: list[str]) -> dict[str, list[float]]:
    output: dict[str, list[float]] = collections.defaultdict(list)
    if not cells:
        return {}
    dataset = ds.dataset(path, format="parquet")
    filter_expression = (
        (ds.field("official_cruise_id") == TN352)
        & ds.field("qc_eligible_for_cell")
        & ds.field("cell_id").isin(cells)
    )
    scanner = dataset.scanner(
        columns=["cell_id", "depth_m_positive_down"],
        filter=filter_expression,
        batch_size=262_144,
        use_threads=True,
    )
    for batch in scanner.to_batches():
        cell_values = batch.column(0).to_pylist()
        depth_values = batch.column(1).to_numpy(zero_copy_only=False)
        for cell_id, depth_value in zip(cell_values, depth_values):
            output[str(cell_id)].append(float(depth_value))
    return dict(output)


def build_change_rows(
    old: dict[str, dict[str, Any]],
    new: dict[str, dict[str, Any]],
    added: list[str],
    changed: list[str],
    recovered: dict[str, dict[str, Any]],
    old_depths: dict[str, list[float]],
    new_depths: dict[str, list[float]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cell_id in sorted(added + changed, key=lambda value: (int(value.split("_")[1]), int(value.split("_")[2]))):
        new_row = new[cell_id]
        old_row = old.get(cell_id)
        old_median = None if old_row is None else float(old_row["median_depth_m_positive_down_exact"])
        new_median = float(new_row["median_depth_m_positive_down_exact"])
        old_recomputed = exact_median(old_depths.get(cell_id, []))
        new_recomputed = exact_median(new_depths.get(cell_id, []))
        if old_row is not None:
            require(len(old_depths.get(cell_id, [])) == int(old_row["n_qc_eligible"]), f"old eligible count mismatch: {cell_id}")
            require(old_recomputed == old_median, f"old median mismatch: {cell_id}")
        require(len(new_depths.get(cell_id, [])) == int(new_row["n_qc_eligible"]), f"new eligible count mismatch: {cell_id}")
        require(new_recomputed == new_median, f"new median mismatch: {cell_id}")
        item = recovered.get(cell_id, {"n_all": 0, "n_eligible": 0, "eligible_depths": []})
        recovered_depths = [float(value) for value in item["eligible_depths"]]
        require(item["n_eligible"] > 0, f"affected cell lacks recovered 0168 eligible rows: {cell_id}")
        lon_bin = int(new_row["lon_bin"])
        lat_bin = int(new_row["lat_bin"])
        below = equal = above = None
        if old_median is not None:
            array = np.asarray(recovered_depths, dtype=np.float64)
            below = int(np.count_nonzero(array < old_median))
            equal = int(np.count_nonzero(array == old_median))
            above = int(np.count_nonzero(array > old_median))
        delta = None if old_median is None else new_median - old_median
        rows.append(
            {
                "cell_id": cell_id,
                "lon_bin": lon_bin,
                "lat_bin": lat_bin,
                "lon_center": float(new_row["lon_center"]),
                "lat_center": float(new_row["lat_center"]),
                "in_south_china_sea": 105.0 <= float(new_row["lon_center"]) < 125.0 and 0.0 <= float(new_row["lat_center"]) < 25.0,
                "change_type": "added" if cell_id in added else "depth_changed_common",
                "old_present": old_row is not None,
                "new_present": True,
                "old_n_qc_eligible": None if old_row is None else int(old_row["n_qc_eligible"]),
                "new_n_qc_eligible": int(new_row["n_qc_eligible"]),
                "old_median_depth_m_positive_down_exact": old_median,
                "new_median_depth_m_positive_down_exact": new_median,
                "signed_median_change_m": delta,
                "absolute_median_change_m": None if delta is None else abs(delta),
                "old_recomputed_exact_median_m": old_recomputed,
                "new_recomputed_exact_median_m": new_recomputed,
                "recovered_0168_soundings_with_valid_cell": int(item["n_all"]),
                "recovered_0168_eligible": int(item["n_eligible"]),
                "recovered_0168_depth_min_m": min(recovered_depths),
                "recovered_0168_depth_max_m": max(recovered_depths),
                "recovered_0168_depth_nmad_m": nmad(recovered_depths),
                "recovered_below_old_median": below,
                "recovered_equal_old_median": equal,
                "recovered_above_old_median": above,
                "change_attributed_to_recovered_0168_rows": True,
            }
        )
    return rows


def build_object_summary(
    object_stats: dict[str, dict[str, int]],
    commands: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    processing = pq.read_table(
        STAGE_C_ROOT / "source_object_processing.parquet",
        filters=[("official_cruise_id", "=", TN352), ("source_object_format", "=", ".mb58.gz")],
    ).to_pylist()
    contributors = pq.read_table(
        STAGE_C_ROOT / "cell_cruise_contributors.parquet",
        filters=[("official_cruise_id", "=", TN352)],
    ).to_pylist()
    candidate_cells: collections.Counter[str] = collections.Counter()
    for row in contributors:
        if int(row["n_qc_eligible"]) > 0:
            candidate_cells[str(row["source_object_id"])] += 1
    output = []
    for row in sorted(processing, key=lambda value: str(value["source_object_id"])):
        object_id = str(row["source_object_id"])
        stats = object_stats.get(object_id, _empty_object_stats())
        object_commands = commands.get(object_id, {})
        require(set(object_commands) == {"decompression", "mbinfo", "mblist_u3", "mblist_u0"}, f"TN352 command closure: {object_id}")
        require(int(row["parsed_row_count"]) == stats["n_soundings_all"], f"parsed row mismatch: {object_id}")
        output.append(
            {
                "source_object_id": object_id,
                "source_object_relative_path": str(row["source_object_relative_path"]),
                "source_object_sha256": str(row["source_object_sha256"]),
                "parse_status": str(row["parse_status"]),
                "parsed_row_count": int(row["parsed_row_count"]),
                "decompression_argv_sha256": str(object_commands["decompression"]["argv_sha256"]),
                "mbinfo_argv_sha256": str(object_commands["mbinfo"]["argv_sha256"]),
                "mblist_u3_argv_sha256": str(object_commands["mblist_u3"]["argv_sha256"]),
                "mblist_u0_argv_sha256": str(object_commands["mblist_u0"]["argv_sha256"]),
                **stats,
                "n_candidate_cells": int(candidate_cells[object_id]),
                "is_object_0168": object_id == OBJECT_0168,
            }
        )
    require(len(output) == 184, "TN352 mb58 object count differs from 184")
    return output


def write_object_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    import csv

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_contract(
    environment: dict[str, Any],
    role_counts: dict[str, int],
    code_closure: dict[str, Any],
    counts: dict[str, Any],
) -> list[dict[str, Any]]:
    env_path = STAGE_C_ROOT / "environment.json"
    ledger_path = STAGE_C_ROOT / "command_ledger.jsonl"
    manifest_path = STAGE_C_ROOT / "audit_manifest.json"
    verification_path = STAGE_C_ROOT / "verification.json"
    records: list[dict[str, Any]] = []

    def add(item_id: str, category: str, item: str, status: str, value: Any, path: Path, locator: str, notes: str = "", unit: str | None = None) -> None:
        records.append(
            contract_record(
                item_id,
                category,
                item,
                status,
                value,
                unit=unit,
                evidence_path=path,
                evidence_locator=locator,
                notes=notes,
            )
        )

    source = environment["material"]["source"]
    binaries = environment["material"]["binaries"]
    add("ENV-01", "environment", "MB-System version/tag", "verified_used", source["tag"], env_path, "/material/source/tag")
    add("ENV-02", "environment", "MB-System source commit", "verified_used", source["commit"], env_path, "/material/source/commit")
    add("ENV-03", "environment", "MB-System source tree", "verified_used", source["tree"], env_path, "/material/source/tree")
    add("ENV-04", "environment", "parser environment digest", "verified_used", environment["environment_digest"], env_path, "/environment_digest")
    add("ENV-05", "environment", "parser binary SHA256", "verified_used", {name: binaries[name]["sha256"] for name in ("gzip", "mbinfo", "mblist")}, env_path, "/material/binaries")
    add("CMD-01", "commands", "retained command role counts", "verified_used", role_counts, ledger_path, "all 768 JSONL records")
    add("CMD-02", "commands", "gzip command pattern", "verified_used", "gzip -dc -- <authorized .mb58.gz>", ledger_path, "role=decompression")
    add("CMD-03", "commands", "mbinfo command pattern", "verified_used", "mbinfo -I<input.mb58> -F58 -X1", ledger_path, "role=mbinfo")
    add("CMD-04", "commands", "mblist U3 command pattern", "verified_used", "mblist -I<input.mb58> -F58 -P1 -L0 -MA -U3 -OMN#XYzH -X<all_u3.tsv>", ledger_path, "role=mblist_u3")
    add("CMD-05", "commands", "mblist U0 command pattern", "verified_used", "mblist -I<input.mb58> -F58 -P1 -L0 -MA -U0 -OMN#XYzH -X<good_u0.tsv>", ledger_path, "role=mblist_u0")
    for index, executable in enumerate(("mbformat", "mbpreprocess", "mbprocess", "mbclean", "mbareaclean"), start=6):
        add(
            f"CMD-{index:02d}",
            "commands",
            f"{executable} invocation",
            "verified_not_used",
            0,
            PROCESSOR_PATH,
            f"AST executable bindings and text reference count={code_closure['forbidden_executable_references'][executable]}; ledger role closure",
            "The accepted producer binds only gzip, mbinfo, and mblist, and all 768 recorded roles close per object.",
        )
    add("FMT-01", "format", "Stage C format input", "verified_used", "decompressed format-58 parsed directly with -F58", PROCESSOR_PATH, "process_primary_object gzip_argv/mbinfo_argv/u3_argv/u0_argv")
    add("FLD-01", "fields", "mblist output fields", "verified_used", ["M epoch", "N native ping counter", "# beam index", "X longitude", "Y latitude", "z depth", "H heading"], ADAPTER_PATH, "OUTPUT_FIELDS and MblistRow")
    add("FLD-02", "fields", "U3/U0 join key", "verified_used", ["epoch_us", "native_ping_counter", "beam_index"], HELPER_PATH, "_raw_from_object_impl SQL join")
    add("FLD-03", "fields", "U3/U0 membership policy", "verified_used", "U3 supplies all beams; U0 key membership marks good; absent finite-z U3 is flagged; absent NaN-z U3 is null", HELPER_PATH, "_raw_from_object_impl")
    add("FLD-04", "fields", "independent U3/U0 navigation state in final output", "unknown", "not persisted as separate columns in accepted sounding schema", STAGE_C_ROOT / "sounding_lineage.parquet", "Parquet schema", "The parser used both states, but the accepted output cannot independently reconstruct each state.")
    add("DEP-01", "depth", "depth source field", "verified_used", "U0 mblist z for good beams", HELPER_PATH, "_raw_from_object_impl good_depth assignment")
    add("DEP-02", "depth", "depth unit and direction", "known_from_output", {"unit": "m", "direction": "positive_down", "elevation": "-depth"}, STAGE_C_ROOT / "sounding_lineage.parquet", "depth_unit/depth_direction/elev_m")
    add("DEP-03", "depth", "local depth conversion", "not_performed", "parser_depth_value copied to depth_m_positive_down; elev_m=-depth", HELPER_PATH, "sounding_batch_table")
    add("DEP-04", "depth", "upstream correction provenance before archived format-58", "unknown", "no retained correction chain or parameter sources", HANDOFF_PATH, "/known_engineering_limitations and Stage C evidence boundary")
    add("QC-01", "quality", "beam flag policy", "verified_used", "U0/U3 membership classifies good, flagged, and null", HELPER_PATH, "_raw_from_object_impl")
    add("QC-02", "quality", "good beam handling", "verified_used", "good is necessary but not sufficient for eligibility", HELPER_PATH, "sounding_batch_table hard_values")
    add("QC-03", "quality", "flagged beam handling", "verified_used", "retained in lineage; H02 and H04; excluded from cell median", HELPER_PATH, "sounding_batch_table failure_values")
    add("QC-04", "quality", "null beam handling", "verified_used", "retained in lineage; H02 and H04; excluded from cell median", HELPER_PATH, "sounding_batch_table failure_values")
    add("QC-05", "quality", "navigation validity", "verified_used", "U3 finite AND (U0 absent OR U0 finite) AND lon/lat range; failure is H03", HELPER_PATH, "sounding_batch_table navigation_sources_finite/nav_values")
    add("QC-06", "quality", "depth range", "verified_used", "finite and 0 < depth <= 12000", HELPER_PATH, "sounding_batch_table depth_ok_values", unit="m")
    add("QC-07", "quality", "eligible definition", "verified_used", "native_quality_state == good AND navigation_valid AND finite 0 < depth_m_positive_down <= 12000", HELPER_PATH, "sounding_batch_table hard_values")
    add("QC-08", "quality", "speed", "verified_used", "used only for R03_navigation_speed review annotation; not an eligibility exclusion", HELPER_PATH, "ping_review_codes")
    add("QC-09", "quality", "native quality code", "verified_not_used", "not emitted by -OMN#XYzH; output value officially_unknown", HELPER_PATH, "sounding_batch_table native_quality_code")
    for item_id, item in (("QC-10", "amplitude"), ("QC-11", "beam angle")):
        add(item_id, "quality", item, "verified_not_used", "not requested by -OMN#XYzH and absent from eligibility", ledger_path, "mblist argv plus helper field closure")
    for item_id, item in (
        ("COR-01", "SVP correction"),
        ("COR-02", "tide correction"),
        ("COR-03", "draft correction"),
        ("COR-04", "lever-arm correction"),
        ("COR-05", "attitude correction"),
        ("COR-06", "patch-test correction"),
    ):
        add(item_id, "corrections", item, "not_performed", "no local correction command or parameter input", PROCESSOR_PATH, "executable and input closure", "Whether NCEI applied it before archiving format-58 is unknown.")
    for item_id, suffix in (("ACC-01", ".fnv"), ("ACC-02", ".inf"), ("ACC-03", ".fbt")):
        add(item_id, "access", f"{suffix} body read", "verified_not_used", 0, manifest_path, f"/body_read_scope/{suffix}")
    for item_id, suffix in (("ACC-04", ".par"), ("ACC-05", ".esf")):
        add(item_id, "access", f"{suffix} body read", "verified_not_used", 0, PROCESSOR_PATH, "code-path and command-role closure")
    add("AGG-01", "aggregation", "one-arcminute label", "verified_used", "per-cruise exact median of qc_eligible_for_cell soundings", PROCESSOR_PATH, "aggregate_outputs")
    add("ROLE-01", "evidence", "evidence levels", "known_from_output", ["official_raw_multibeam_source", "mbsystem_parsed_sounding", "source_internal_qc_retained_sounding", "one_arcmin_exact_median_development_label"], verification_path, "accepted output chain")
    add("ROLE-02", "evidence", "validated bathymetric truth", "unknown", False, verification_path, "/confirmation_role_eligible")
    add("CNT-01", "counts", "recomputed row and cell counts", "known_from_output", counts, STAGE_C_ROOT / "sounding_lineage.parquet", "selected-column scans and candidate table")
    add("OBJ-0168", "object", "object 0168 recovery", "known_from_output", {"soundings": 96768, "eligible": 86184, "H03": 198, "added_cells": 10, "changed_common_cells": 20}, HANDOFF_PATH, "/object_0168 and /comparison_to_20260807T090000Z")
    require(len({record["contract_item_id"] for record in records}) == len(records), "duplicate contract item ID")
    return records


def unexecuted_reprocessing_proposal(object_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "proposal_id": "TN352-v2-processed",
        "status": "frozen_unexecuted_requires_separate_authorization",
        "source_objects": [
            {"source_object_id": row["source_object_id"], "sha256": row["source_object_sha256"]}
            for row in object_rows
        ],
        "required_correction_inputs": {
            "svp": "unresolved",
            "tide": "unresolved",
            "draft_and_waterline": "unresolved",
            "lever_arm": "unresolved",
            "attitude_latency": "unresolved",
            "patch_test": "unresolved",
            "navigation_processing_history": "unresolved",
        },
        "proposed_command_stages": [
            "mbformat inventory and format confirmation",
            "mbpreprocess with separately frozen sensor/navigation parameters",
            "mbprocess with a hashed per-object .par configuration",
            "mblist export with the existing U3/U0 field and join rules",
        ],
        "mbclean_mbareaclean_policy": "disabled unless a separate depth-blind threshold protocol is approved before output depths are inspected",
        "required_validation": [
            "hash closure for every input, .par, .esf, command, environment, and output",
            "synthetic sign/unit oracle and direct pre/post correction spot checks",
            "navigation, beam-state, row-count, and exact-median conservation",
            "independent verifier with no confirmation promotion",
        ],
        "output_role": OUTPUT_ROLE,
        "stop_rules": [
            "stop if any correction input or reference frame is unresolved",
            "stop if format or object hashes drift",
            "stop if corrected depth sign/unit or row identity does not close",
        ],
    }


def render_report(
    run_id: str,
    counts: dict[str, Any],
    object_0168: dict[str, Any],
    comparison: dict[str, Any],
    proposal: dict[str, Any],
) -> str:
    return f"""# TN352 processing audit

Run ID: `{run_id}`

Output role: `{OUTPUT_ROLE}`

Classification: `B. {CLASSIFICATION}`

Confirmation eligible: `false`

## Finding

The accepted Stage C run parses the official NCEI format-58 objects directly
with MB-System and applies source-internal beam, navigation, and depth-range
eligibility rules before per-cruise exact-median aggregation. The retained
evidence does not document a processing chain with traceable SVP, tide, draft,
lever-arm, attitude, or patch-test inputs. It therefore supports classification
B, not a processed-cruise reference and not validated bathymetric truth.

## Counts

| Scope | Soundings | Eligible | Candidate cells |
|---|---:|---:|---:|
| Four cruises | {counts['four_cruise_soundings']:,} | {counts['four_cruise_eligible']:,} | {counts['four_cruise_candidate_cells']:,} |
| TN352 global | {counts['tn352_soundings']:,} | {counts['tn352_eligible']:,} | {counts['tn352_candidate_cells']:,} |
| TN352 SCS `[105,125) x [0,25)` | {counts['tn352_scs_soundings']:,} | {counts['tn352_scs_eligible']:,} | {counts['tn352_scs_candidate_cells']:,} |

## Actual processing

Each of the 192 authorized format-58 objects has one successful invocation of
each retained role: `gzip -dc`, `mbinfo -F58 -X1`, `mblist -U3`, and
`mblist -U0`. No `mbformat`, `mbpreprocess`, `mbprocess`, `mbclean`, or
`mbareaclean` invocation occurred in this Stage C run. The complete 768 literal
argv records and their hashes are retained in `tn352_processing_contract.json`.

U3 and U0 use fields `M N # X Y z H` and join on epoch in microseconds, native
ping counter, and beam index. U0 membership marks a good beam. A finite-depth
U3 row absent from U0 is flagged; a NaN-depth U3 row absent from U0 is null.
Eligible means good native state, valid U3/U0 navigation and coordinate range,
and finite positive-down depth in `(0, 12000]` m. Flagged and null rows remain
in lineage but do not enter cell medians. Speed is used only for the R03 review
annotation and does not exclude a sounding.

The accepted final Parquet does not retain the two navigation-source booleans
separately. It therefore cannot independently reconstruct whether an H03 row
failed U3, U0, or both. This is a known engineering limitation.

## Object 0168

Object `0168_20180501_164920_TGT.all.mb58.gz` changed from
`failed_parser_contract` to `pass`. It recovered {object_0168['soundings']:,}
soundings and {object_0168['eligible']:,} eligible rows. Exactly
{object_0168['h03']:,} rows have invalid navigation and H03; they have no cell
assignment. The recovered eligible rows added {comparison['added_cells']}
cells and changed the exact median in {comparison['changed_common_cells']}
existing cells. The absolute common-cell changes span
{comparison['absolute_change_min_m']:.4f} to
{comparison['absolute_change_max_m']:.4f} m. The Parquet audit independently
recomputes old and new medians from sounding lineage for all affected cells.

## Depth provenance

For good beams, the current `depth_m_positive_down` is copied from the U0
`mblist z` field in metres; `elev_m` is its negative. No local correction
command or correction parameter file is present. Whether the archived NCEI
format-58 depths already include upstream corrections is `unknown`; a direct
uncorrected-raw versus current-depth comparison was `not_performed` because no
separate uncorrected field is retained.

## TN352-v2-processed proposal

Status: `{proposal['status']}`. The proposal is recorded in the JSON contract
with all {len(proposal['source_objects'])} TN352 object hashes, unresolved
correction inputs, proposed MB-System stages, validation checks, and stop
rules. It was not executed. Reprocessing requires separate authorization after
the sensor, navigation, reference-frame, and correction inputs are resolved.

## Evidence boundary

The official raw source, MB-System parsed sounding, source-internal retained
sounding, and one-arcminute development label are separate evidence levels.
This audit establishes none of them as validated bathymetric truth. It ran no
GGM, PINN, GEBCO, product residual, model residual, MRAR merge, datum/bias fit,
or cross-cruise aggregation.
"""


def run(run_id: str) -> Path:
    run_id = safe_run_id(run_id)
    final_root = AUDIT_ROOT / run_id
    failed_root = AUDIT_ROOT / f"{run_id}.failed"
    require(not final_root.exists(), f"audit run already exists: {final_root}")
    require(not failed_root.exists(), f"failed audit run already exists: {failed_root}")
    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=f".{run_id}.tmp-", dir=AUDIT_ROOT))
    phase_a = temp_root / "phase_a"
    phase_a.mkdir()
    try:
        input_records = validate_input_hashes()
        ledger_rows, command_by_object, role_counts = verify_command_ledger()
        code_closure = scan_processor_executables()
        accepted_verification = read_json(STAGE_C_ROOT / "verification.json")
        environment = read_json(STAGE_C_ROOT / "environment.json")
        tn_totals, object_stats, recovered = scan_tn352_soundings()
        all_eligible = count_all_eligible()
        new_candidates = candidate_maps(STAGE_C_ROOT)
        old_candidates = candidate_maps(REFERENCE_STAGE_C_ROOT)
        added, removed, changed = compare_candidates(old_candidates, new_candidates)
        require(len(added) == 10 and not removed and len(changed) == 20, "old/new cell delta differs")
        affected = added + changed
        old_depths = collect_cell_depths(REFERENCE_STAGE_C_ROOT / "sounding_lineage.parquet", changed)
        new_depths = collect_cell_depths(STAGE_C_ROOT / "sounding_lineage.parquet", affected)
        change_rows = build_change_rows(
            old_candidates,
            new_candidates,
            added,
            changed,
            recovered,
            old_depths,
            new_depths,
        )
        object_rows = build_object_summary(object_stats, command_by_object)
        object_0168_row = next(row for row in object_rows if row["is_object_0168"])
        require(object_0168_row["n_soundings_all"] == 96_768, "0168 sounding count differs")
        require(object_0168_row["n_qc_eligible"] == 86_184, "0168 eligible count differs")
        require(object_0168_row["n_h03"] == 198, "0168 H03 count differs")
        candidate_table = pq.read_table(STAGE_C_ROOT / "cell_cruise_candidates.parquet")
        tn_candidate_rows = [row for row in candidate_table.to_pylist() if row["official_cruise_id"] == TN352]
        tn_scs_candidates = [
            row
            for row in tn_candidate_rows
            if 105.0 <= float(row["lon_center"]) < 125.0 and 0.0 <= float(row["lat_center"]) < 25.0
        ]
        counts = {
            "four_cruise_soundings": pq.ParquetFile(STAGE_C_ROOT / "sounding_lineage.parquet").metadata.num_rows,
            "four_cruise_eligible": all_eligible,
            "four_cruise_candidate_cells": candidate_table.num_rows,
            "tn352_soundings": tn_totals["soundings"],
            "tn352_eligible": tn_totals["eligible"],
            "tn352_scs_soundings": tn_totals["scs_soundings"],
            "tn352_scs_eligible": tn_totals["scs_eligible"],
            "tn352_candidate_cells": len(tn_candidate_rows),
            "tn352_scs_candidate_cells": len(tn_scs_candidates),
        }
        require(counts["four_cruise_soundings"] == int(accepted_verification["sounding_row_count"]), "total sounding count differs")
        require(counts["four_cruise_eligible"] == int(accepted_verification["eligible_sounding_row_count"]), "total eligible count differs")
        require(
            (counts["tn352_soundings"], counts["tn352_eligible"], counts["tn352_scs_soundings"], counts["tn352_scs_eligible"])
            == (19_574_784, 17_211_316, 13_782_014, 12_351_039),
            "TN352 supplied counts differ",
        )
        absolute_changes = [float(row["absolute_median_change_m"]) for row in change_rows if row["change_type"] == "depth_changed_common"]
        comparison = {
            "reference_run_id": REFERENCE_STAGE_C_ROOT.name,
            "added_cells": len(added),
            "removed_cells": len(removed),
            "changed_common_cells": len(changed),
            "absolute_change_min_m": min(absolute_changes),
            "absolute_change_median_m": float(np.median(np.asarray(absolute_changes))),
            "absolute_change_max_m": max(absolute_changes),
        }
        object_0168 = {
            "source_object_id": OBJECT_0168,
            "old_parse_status": next(
                row["parse_status"]
                for row in pq.read_table(
                    REFERENCE_STAGE_C_ROOT / "source_object_processing.parquet",
                    filters=[("source_object_id", "=", OBJECT_0168)],
                ).to_pylist()
                if row["source_object_format"] == ".mb58.gz"
            ),
            "new_parse_status": object_0168_row["parse_status"],
            "soundings": object_0168_row["n_soundings_all"],
            "eligible": object_0168_row["n_qc_eligible"],
            "h03": object_0168_row["n_h03"],
            "valid_cell_soundings": sum(int(item["n_all"]) for item in recovered.values()),
            "eligible_in_affected_cells": sum(int(recovered[cell]["n_eligible"]) for cell in affected),
        }
        require(object_0168["old_parse_status"] == "failed_parser_contract", "0168 old status differs")
        require(object_0168["new_parse_status"] == "pass", "0168 new status differs")
        require(object_0168["valid_cell_soundings"] == 96_570, "0168 valid-cell conservation differs")
        contract_records = build_contract(environment, role_counts, code_closure, counts)
        proposal = unexecuted_reprocessing_proposal(object_rows)
        contract_json = {
            "schema_version": 1,
            "run_id": run_id,
            "stage": "TN352_processing_audit_phase_a",
            "status": "produced_pending_independent_verification",
            "output_role": OUTPUT_ROLE,
            "confirmation_role_eligible": False,
            "classification": {"code": "B", "value": CLASSIFICATION},
            "evidence_levels": [
                "official_raw_multibeam_source",
                "mbsystem_parsed_sounding",
                "source_internal_qc_retained_sounding",
                "one_arcmin_exact_median_development_label",
                "validated_bathymetric_truth_not_established",
            ],
            "records": contract_records,
            "command_invocations": ledger_rows,
            "counts": counts,
            "object_0168": object_0168,
            "comparison_to_reference": comparison,
            "known_engineering_limitations": [
                "authorization receipt fields were not all independently validated by the accepted Stage C gate",
                "accepted Stage C output does not persist separate U3 and U0 navigation-state columns",
            ],
            "tn352_v2_processed_proposal": proposal,
            "prohibited_operations": {
                "GGM": 0,
                "PINN": 0,
                "GEBCO": 0,
                "product_residual_comparison": 0,
                "model_residual_comparison": 0,
                "MRAR_merge": 0,
                "datum_or_bias_fit": 0,
                "cross_cruise_aggregation": 0,
                "sealed_body_reads_by_audit": 0,
                "sidecar_body_reads_by_audit": 0,
                "mbsystem_invocations_by_audit": 0,
            },
        }
        write_contract_tsv(phase_a / "tn352_processing_contract.tsv", contract_records)
        write_json(phase_a / "tn352_processing_contract.json", contract_json)
        write_object_summary(phase_a / "tn352_object_policy_summary.tsv", object_rows)
        change_schema = pa.schema(
            [
                ("cell_id", pa.string()),
                ("lon_bin", pa.int64()),
                ("lat_bin", pa.int64()),
                ("lon_center", pa.float64()),
                ("lat_center", pa.float64()),
                ("in_south_china_sea", pa.bool_()),
                ("change_type", pa.string()),
                ("old_present", pa.bool_()),
                ("new_present", pa.bool_()),
                ("old_n_qc_eligible", pa.int64()),
                ("new_n_qc_eligible", pa.int64()),
                ("old_median_depth_m_positive_down_exact", pa.float64()),
                ("new_median_depth_m_positive_down_exact", pa.float64()),
                ("signed_median_change_m", pa.float64()),
                ("absolute_median_change_m", pa.float64()),
                ("old_recomputed_exact_median_m", pa.float64()),
                ("new_recomputed_exact_median_m", pa.float64()),
                ("recovered_0168_soundings_with_valid_cell", pa.int64()),
                ("recovered_0168_eligible", pa.int64()),
                ("recovered_0168_depth_min_m", pa.float64()),
                ("recovered_0168_depth_max_m", pa.float64()),
                ("recovered_0168_depth_nmad_m", pa.float64()),
                ("recovered_below_old_median", pa.int64()),
                ("recovered_equal_old_median", pa.int64()),
                ("recovered_above_old_median", pa.int64()),
                ("change_attributed_to_recovered_0168_rows", pa.bool_()),
            ]
        )
        pq.write_table(pa.Table.from_pylist(change_rows, schema=change_schema), phase_a / "tn352_0168_change_audit.parquet", compression="zstd")
        (phase_a / "audit_report.md").write_text(
            render_report(run_id, counts, object_0168, comparison, proposal), encoding="utf-8"
        )
        output_names = [
            "tn352_processing_contract.tsv",
            "tn352_processing_contract.json",
            "tn352_object_policy_summary.tsv",
            "tn352_0168_change_audit.parquet",
            "audit_report.md",
        ]
        output_records = output_manifest(phase_a, output_names)
        for name, record in output_records.items():
            record["path"] = str((final_root / "phase_a" / name).resolve())
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "phase": "phase_a",
            "status": "produced_pending_independent_verification",
            "output_role": OUTPUT_ROLE,
            "classification": {"code": "B", "value": CLASSIFICATION},
            "accepted_stage_c_run": str(STAGE_C_ROOT),
            "reference_stage_c_run": str(REFERENCE_STAGE_C_ROOT),
            "inputs": input_records,
            "outputs": output_records,
            "output_schema": {
                "contract_tsv_fields": list(CONTRACT_FIELDS),
                "change_audit_parquet": str(change_schema),
                "object_summary_fields": list(object_rows[0]),
            },
            "access_counts": contract_json["prohibited_operations"],
        }
        write_json(phase_a / "audit_manifest.json", manifest)
        os.rename(temp_root, final_root)
        return final_root
    except Exception:
        os.rename(temp_root, failed_root)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="immutable UTC run ID, YYYYMMDDTHHMMSSZ")
    args = parser.parse_args()
    print(run(args.run_id))


if __name__ == "__main__":
    main()
