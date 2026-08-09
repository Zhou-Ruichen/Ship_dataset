#!/usr/bin/env python3
"""Independently verify a TN352 Phase A processing audit."""

from __future__ import annotations

import argparse
import collections
import csv
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from ncei.code.scs_tn352_audit_common import (
    CONTRACT_FIELDS,
    CONTRACT_STATUSES,
    REFERENCE_STAGE_C_ROOT,
    REPO_ROOT,
    STAGE_C_ROOT,
    exact_median,
    read_contract_tsv,
    read_json,
    read_jsonl,
    require,
    sha256_file,
    write_json,
)


TN352 = "TN352"
OBJECT_0168 = "20260805T230449Z/objects/TN352/em302/0168_20180501_164920_TGT.all.mb58.gz"
OUTPUT_ROLE = "development_only_not_confirmation"


def scan_counts() -> dict[str, int]:
    dataset = ds.dataset(STAGE_C_ROOT / "sounding_lineage.parquet", format="parquet")
    all_eligible = 0
    for batch in dataset.scanner(columns=["qc_eligible_for_cell"], batch_size=1_048_576).to_batches():
        all_eligible += int(pc.sum(batch.column(0)).as_py())
    tn = {"soundings": 0, "eligible": 0, "scs_soundings": 0, "scs_eligible": 0}
    scanner = dataset.scanner(
        columns=["lon_deg", "lat_deg", "qc_eligible_for_cell"],
        filter=ds.field("official_cruise_id") == TN352,
        batch_size=262_144,
    )
    for batch in scanner.to_batches():
        lon = batch.column(0).to_numpy(zero_copy_only=False)
        lat = batch.column(1).to_numpy(zero_copy_only=False)
        eligible = batch.column(2).to_numpy(zero_copy_only=False)
        scs = (lon >= 105.0) & (lon < 125.0) & (lat >= 0.0) & (lat < 25.0)
        tn["soundings"] += batch.num_rows
        tn["eligible"] += int(np.count_nonzero(eligible))
        tn["scs_soundings"] += int(np.count_nonzero(scs))
        tn["scs_eligible"] += int(np.count_nonzero(scs & eligible))
    candidates = pq.read_table(STAGE_C_ROOT / "cell_cruise_candidates.parquet").to_pylist()
    tn_candidates = [row for row in candidates if row["official_cruise_id"] == TN352]
    tn_scs = [
        row
        for row in tn_candidates
        if 105.0 <= float(row["lon_center"]) < 125.0 and 0.0 <= float(row["lat_center"]) < 25.0
    ]
    return {
        "four_cruise_soundings": pq.ParquetFile(STAGE_C_ROOT / "sounding_lineage.parquet").metadata.num_rows,
        "four_cruise_eligible": all_eligible,
        "four_cruise_candidate_cells": len(candidates),
        "tn352_soundings": tn["soundings"],
        "tn352_eligible": tn["eligible"],
        "tn352_scs_soundings": tn["scs_soundings"],
        "tn352_scs_eligible": tn["scs_eligible"],
        "tn352_candidate_cells": len(tn_candidates),
        "tn352_scs_candidate_cells": len(tn_scs),
    }


def collect_depths(path: Path, cells: list[str]) -> dict[str, list[float]]:
    output: dict[str, list[float]] = collections.defaultdict(list)
    if not cells:
        return {}
    dataset = ds.dataset(path, format="parquet")
    scanner = dataset.scanner(
        columns=["cell_id", "depth_m_positive_down"],
        filter=(ds.field("official_cruise_id") == TN352)
        & ds.field("qc_eligible_for_cell")
        & ds.field("cell_id").isin(cells),
        batch_size=262_144,
    )
    for batch in scanner.to_batches():
        for cell_id, depth in zip(batch.column(0).to_pylist(), batch.column(1).to_numpy(zero_copy_only=False)):
            output[str(cell_id)].append(float(depth))
    return dict(output)


def candidate_map(root: Path) -> dict[str, dict[str, Any]]:
    table = pq.read_table(root / "cell_cruise_candidates.parquet", filters=[("official_cruise_id", "=", TN352)])
    return {str(row["cell_id"]): row for row in table.to_pylist()}


def verify_0168(change_path: Path) -> dict[str, Any]:
    old = candidate_map(REFERENCE_STAGE_C_ROOT)
    new = candidate_map(STAGE_C_ROOT)
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(
        cell_id
        for cell_id in set(old) & set(new)
        if float(old[cell_id]["median_depth_m_positive_down_exact"])
        != float(new[cell_id]["median_depth_m_positive_down_exact"])
    )
    require((len(added), len(removed), len(changed)) == (10, 0, 20), "independent old/new cell comparison differs")
    audit = pq.read_table(change_path).to_pylist()
    require(len(audit) == 30 and len({row["cell_id"] for row in audit}) == 30, "0168 audit row/key count differs")
    require({row["cell_id"] for row in audit} == set(added + changed), "0168 affected cohort differs")
    old_depths = collect_depths(REFERENCE_STAGE_C_ROOT / "sounding_lineage.parquet", changed)
    new_depths = collect_depths(STAGE_C_ROOT / "sounding_lineage.parquet", added + changed)
    for row in audit:
        cell_id = str(row["cell_id"])
        expected_new = float(new[cell_id]["median_depth_m_positive_down_exact"])
        require(exact_median(new_depths[cell_id]) == expected_new, f"new independent median differs: {cell_id}")
        require(float(row["new_recomputed_exact_median_m"]) == expected_new, f"new audit median differs: {cell_id}")
        require(int(row["new_n_qc_eligible"]) == len(new_depths[cell_id]), f"new audit count differs: {cell_id}")
        if cell_id in changed:
            expected_old = float(old[cell_id]["median_depth_m_positive_down_exact"])
            require(exact_median(old_depths[cell_id]) == expected_old, f"old independent median differs: {cell_id}")
            require(float(row["old_recomputed_exact_median_m"]) == expected_old, f"old audit median differs: {cell_id}")
            require(float(row["signed_median_change_m"]) == expected_new - expected_old, f"signed delta differs: {cell_id}")
        else:
            require(row["old_present"] is False and row["signed_median_change_m"] is None, f"added-cell state differs: {cell_id}")
        require(int(row["recovered_0168_eligible"]) > 0, f"affected cell lacks 0168 eligible support: {cell_id}")
    object_table = ds.dataset(STAGE_C_ROOT / "sounding_lineage.parquet", format="parquet").to_table(
        columns=["navigation_valid", "qc_eligible_for_cell", "cell_id"],
        filter=ds.field("source_object_id") == OBJECT_0168,
    )
    navigation = object_table["navigation_valid"].to_numpy(zero_copy_only=False)
    eligible = object_table["qc_eligible_for_cell"].to_numpy(zero_copy_only=False)
    valid_cells = sum(value is not None for value in object_table["cell_id"].to_pylist())
    require(object_table.num_rows == 96_768, "0168 independent sounding count differs")
    require(int(np.count_nonzero(eligible)) == 86_184, "0168 independent eligible count differs")
    require(int(np.count_nonzero(~navigation)) == 198, "0168 independent H03 count differs")
    require(valid_cells == 96_570, "0168 valid cell count differs")
    abs_changes = [abs(float(new[cell]["median_depth_m_positive_down_exact"]) - float(old[cell]["median_depth_m_positive_down_exact"])) for cell in changed]
    return {
        "soundings": object_table.num_rows,
        "eligible": int(np.count_nonzero(eligible)),
        "h03": int(np.count_nonzero(~navigation)),
        "valid_cell_soundings": valid_cells,
        "added_cells": len(added),
        "changed_common_cells": len(changed),
        "absolute_change_min_m": min(abs_changes),
        "absolute_change_median_m": float(np.median(np.asarray(abs_changes))),
        "absolute_change_max_m": max(abs_changes),
    }


def read_object_summary(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def verify(run_dir: Path) -> Path:
    run_dir = run_dir.resolve()
    phase_a = run_dir / "phase_a"
    verification_path = phase_a / "verification.json"
    require(phase_a.is_dir(), f"missing phase_a: {phase_a}")
    require(not verification_path.exists(), "verification receipt already exists")
    checks: list[str] = []
    try:
        manifest_path = phase_a / "audit_manifest.json"
        manifest = read_json(manifest_path)
        contract = read_json(phase_a / "tn352_processing_contract.json")
        tsv_records = read_contract_tsv(phase_a / "tn352_processing_contract.tsv")
        require(contract["records"] == tsv_records, "contract TSV/JSON semantic mismatch")
        require(all(set(record) == set(CONTRACT_FIELDS) for record in tsv_records), "contract record fields differ")
        require(all(record["status"] in CONTRACT_STATUSES for record in tsv_records), "unknown contract status")
        require(len({record["contract_item_id"] for record in tsv_records}) == len(tsv_records), "duplicate contract item")
        checks.append("contract_tsv_json_equivalence")
        require(contract["classification"] == {"code": "B", "value": "official_raw_source_development_label"}, "classification differs")
        require(contract["confirmation_role_eligible"] is False and contract["output_role"] == OUTPUT_ROLE, "claim boundary differs")
        correction_rows = [row for row in tsv_records if row["category"] == "corrections"]
        require(correction_rows and all(row["status"] == "not_performed" for row in correction_rows), "B decision correction evidence differs")
        require(any(row["contract_item_id"] == "DEP-04" and row["status"] == "unknown" for row in tsv_records), "upstream depth provenance is not unknown")
        proposal = contract["tn352_v2_processed_proposal"]
        require(proposal["status"] == "frozen_unexecuted_requires_separate_authorization", "reprocessing proposal status differs")
        require(len(proposal["source_objects"]) == 184, "reprocessing source object count differs")
        checks.append("classification_and_proposal")
        prohibited = contract["prohibited_operations"]
        require(prohibited and all(int(value) == 0 for value in prohibited.values()), "prohibited operation count is nonzero")
        report = (phase_a / "audit_report.md").read_text(encoding="utf-8")
        normalized_report = " ".join(report.split())
        for token in ("Classification: `B.", "no GGM, PINN, GEBCO", "not validated bathymetric truth"):
            require(token in normalized_report, f"report boundary missing: {token}")
        checks.append("prohibited_operations_and_report_boundary")
        ledger = read_jsonl(STAGE_C_ROOT / "command_ledger.jsonl")
        roles = collections.Counter(row["role"] for row in ledger)
        require(roles == {"decompression": 192, "mbinfo": 192, "mblist_u3": 192, "mblist_u0": 192}, "independent command role count differs")
        per_object: dict[str, set[str]] = collections.defaultdict(set)
        for row in ledger:
            require(int(row["returncode"]) == 0, "command return code differs")
            per_object[str(row["object_id"])].add(str(row["role"]))
        require(len(per_object) == 192 and all(len(value) == 4 for value in per_object.values()), "per-object command closure differs")
        require(len(contract["command_invocations"]) == 768, "literal command inventory differs")
        checks.append("command_ledger_closure")
        counts = scan_counts()
        require(counts == contract["counts"], "independent count scan differs")
        require(counts == {
            "four_cruise_soundings": 59_298_192,
            "four_cruise_eligible": 51_303_876,
            "four_cruise_candidate_cells": 3_549,
            "tn352_soundings": 19_574_784,
            "tn352_eligible": 17_211_316,
            "tn352_scs_soundings": 13_782_014,
            "tn352_scs_eligible": 12_351_039,
            "tn352_candidate_cells": 3_538,
            "tn352_scs_candidate_cells": 2_368,
        }, "fixed count closure differs")
        checks.append("independent_sounding_and_candidate_counts")
        object_check = verify_0168(phase_a / "tn352_0168_change_audit.parquet")
        require(contract["object_0168"]["soundings"] == object_check["soundings"], "0168 contract soundings differ")
        require(contract["object_0168"]["eligible"] == object_check["eligible"], "0168 contract eligible differs")
        require(contract["object_0168"]["h03"] == object_check["h03"], "0168 contract H03 differs")
        comparison = contract["comparison_to_reference"]
        for key in ("added_cells", "changed_common_cells", "absolute_change_min_m", "absolute_change_median_m", "absolute_change_max_m"):
            require(comparison[key] == object_check[key], f"0168 comparison differs: {key}")
        checks.append("independent_0168_median_and_conservation")
        object_rows = read_object_summary(phase_a / "tn352_object_policy_summary.tsv")
        require(len(object_rows) == 184 and len({row["source_object_id"] for row in object_rows}) == 184, "object summary key count differs")
        require(sum(int(row["n_soundings_all"]) for row in object_rows) == counts["tn352_soundings"], "object sounding sum differs")
        require(sum(int(row["n_qc_eligible"]) for row in object_rows) == counts["tn352_eligible"], "object eligible sum differs")
        object_0168_row = next(row for row in object_rows if row["source_object_id"] == OBJECT_0168)
        require((int(object_0168_row["n_soundings_all"]), int(object_0168_row["n_qc_eligible"]), int(object_0168_row["n_h03"])) == (96_768, 86_184, 198), "object summary 0168 differs")
        checks.append("object_policy_summary_conservation")
        for name, record in manifest["inputs"].items():
            path = Path(record["path"])
            require(path.is_file(), f"input disappeared: {name}")
            require(path.stat().st_size == int(record["bytes"]), f"input bytes drift: {name}")
            require(sha256_file(path) == record["sha256"], f"input hash drift: {name}")
        checks.append("input_hashes_unchanged")
        for name, record in manifest["outputs"].items():
            path = phase_a / name
            require(path.is_file(), f"output missing: {name}")
            require(path.stat().st_size == int(record["bytes"]), f"output bytes differ: {name}")
            require(sha256_file(path) == record["sha256"], f"output hash differs: {name}")
        checks.append("output_hashes")
        verification = {
            "schema_version": 1,
            "run_id": run_dir.name,
            "phase": "phase_a",
            "status": "pass",
            "output_role": OUTPUT_ROLE,
            "classification": contract["classification"],
            "confirmation_role_eligible": False,
            "checks": checks,
            "counts": counts,
            "object_0168": object_check,
            "audit_manifest_sha256": sha256_file(manifest_path),
            "verified_output_sha256": {name: record["sha256"] for name, record in manifest["outputs"].items()},
            "verifier_sha256": sha256_file(Path(__file__)),
            "independent_verifier_opened_sealed_body": False,
            "independent_verifier_invoked_mbsystem": False,
            "depth_difference_with_mrar_read_count": 0,
            "prohibited_operations": prohibited,
        }
        temp = verification_path.with_suffix(".json.tmp")
        write_json(temp, verification)
        os.rename(temp, verification_path)
        return verification_path
    except Exception as error:
        failure = {
            "schema_version": 1,
            "run_id": run_dir.name,
            "phase": "phase_a",
            "status": "fail",
            "checks_completed": checks,
            "error_type": type(error).__name__,
            "error": str(error),
            "independent_verifier_opened_sealed_body": False,
            "independent_verifier_invoked_mbsystem": False,
            "depth_difference_with_mrar_read_count": 0,
        }
        temp = verification_path.with_suffix(".json.tmp")
        write_json(temp, failure)
        os.rename(temp, verification_path)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    print(verify(args.run_dir))


if __name__ == "__main__":
    main()
