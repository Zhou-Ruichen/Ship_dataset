#!/usr/bin/env python3
"""Independently verify a zero-candidate-access Stage C.1a readiness run."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml

from ncei.code.prepare_scs_v2_stage_c1_readiness import (
    ACCEPTED_C0_LOCK,
    ACCEPTED_C0_LOCK_SHA256,
    PRIMARY_IDS,
    READINESS_ROOT,
    RESEARCH_ROOT,
    RUN_ID_RE,
)
from ncei.code.prepare_scs_v2_stage_c1a_readiness import (
    CONTRACT_FILES,
    PREDECESSOR_MANIFEST_SHA256,
    PREDECESSOR_RUN,
    PREDECESSOR_RUN_ID,
    PREDECESSOR_VERIFICATION_SHA256,
)
from ncei.code.verify_scs_v2_stage_c1_readiness import (
    canonical_sha256,
    sha256_file,
    verify_environment,
    verify_fixture,
)


def atomic_json(value: Any, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_predecessor() -> int:
    require(sha256_file(ACCEPTED_C0_LOCK) == ACCEPTED_C0_LOCK_SHA256, "accepted Stage C.0 lock changed")
    require(sha256_file(PREDECESSOR_RUN / "audit_manifest.json") == PREDECESSOR_MANIFEST_SHA256, "C1 manifest changed")
    require(sha256_file(PREDECESSOR_RUN / "verification.json") == PREDECESSOR_VERIFICATION_SHA256, "C1 verification changed")
    predecessor = load_json(PREDECESSOR_RUN / "verification.json")
    require(predecessor["status"] == "pass", "C1 predecessor is not pass")
    for key in ("sealed_object_body_read_count", "archive_decompression_count", "candidate_sounding_row_count", "candidate_cell_row_count"):
        require(predecessor[key] == 0, f"C1 predecessor counter is nonzero: {key}")
    require(predecessor["stage_c_authorized"] is False, "C1 predecessor authorized Stage C")
    return 8


def verify_manifest(run_dir: Path, manifest: dict[str, Any]) -> int:
    require(manifest["stage"] == "C1a_zero_candidate_contract_correction", "manifest stage mismatch")
    require(manifest["run_id"] == run_dir.name, "manifest run ID mismatch")
    require(manifest["accepted_stage_c1"] == {
        "run_id": PREDECESSOR_RUN_ID,
        "audit_manifest_sha256": PREDECESSOR_MANIFEST_SHA256,
        "verification_sha256": PREDECESSOR_VERIFICATION_SHA256,
    }, "manifest predecessor binding mismatch")
    checks = 3
    for name, record in manifest["source_code"].items():
        path = Path(record["path"])
        require(path.is_file(), f"source file missing: {name}")
        require(sha256_file(path) == record["sha256"], f"source hash mismatch: {name}")
        checks += 1
    for name in CONTRACT_FILES:
        record = manifest["contracts"][name]
        source = RESEARCH_ROOT / name
        copy = run_dir / "contracts" / name
        require(Path(record["source_path"]).resolve() == source.resolve(), f"contract source path mismatch: {name}")
        require(source.is_file() and copy.is_file(), f"contract missing: {name}")
        require(sha256_file(source) == record["sha256"] == sha256_file(copy), f"contract hash mismatch: {name}")
        require(copy.stat().st_size == record["bytes"], f"contract bytes mismatch: {name}")
        checks += 1
    listed = set(manifest["outputs"])
    actual = {
        str(path.relative_to(run_dir))
        for path in run_dir.rglob("*")
        if path.is_file() and path.name not in {"audit_manifest.json", "verification.json"}
    }
    require(actual == listed, f"output set mismatch: missing={sorted(listed - actual)}, extra={sorted(actual - listed)}")
    checks += 1
    for relative, record in manifest["outputs"].items():
        path = run_dir / relative
        require(Path(record["path"]).resolve() == path.resolve(), f"output path mismatch: {relative}")
        require(path.stat().st_size == record["bytes"], f"output bytes mismatch: {relative}")
        require(sha256_file(path) == record["sha256"], f"output hash mismatch: {relative}")
        checks += 1
    return checks


def verify_time_fixture(value: dict[str, Any]) -> int:
    require(value["status"] == "pass", "time fixture did not pass")
    require(value["candidate_data_accessed"] is False, "time fixture accessed candidate data")
    require(set(value["cases"]) == {"missing_time_in_u3", "invalid_time_in_u3", "invalid_time_in_u0"}, "time fixture cases mismatch")
    expected_errors = {
        "missing_time_in_u3": "TIME_UTC_MISSING",
        "invalid_time_in_u3": "TIME_UTC_INVALID",
        "invalid_time_in_u0": "TIME_UTC_INVALID",
    }
    for name, expected_error in expected_errors.items():
        case = value["cases"][name]
        require(case["status"] == "pass", f"time case failed: {name}")
        require(case["parse_status"] == "failed_invalid_or_missing_time", f"time parse status mismatch: {name}")
        require(case["error_code"] == expected_error, f"time error code mismatch: {name}")
        require(case["parsed_row_count"] == case["sounding_row_count"] == case["contributor_row_count"] == 0, f"partial rows emitted: {name}")
        require(case["time_utc_field_available"] is False, f"failed time marked available: {name}")
        require(case["time_utc_field_status"] == "known", f"failed time status mismatch: {name}")
        require(case["time_utc_evidence_kind"] == "parser_preflight_failure", f"failed time evidence mismatch: {name}")
    for key in ("sealed_object_body_read_count", "archive_decompression_count", "candidate_sounding_row_count", "candidate_cell_row_count", "mismatch_count"):
        require(value[key] == 0, f"time fixture counter nonzero: {key}")
    return 10 + 7 * len(expected_errors)


def verify_contract_and_authorization(run_dir: Path, authorization: dict[str, Any], environment_digest: str) -> int:
    contract = yaml.safe_load((run_dir / "contracts/stage-c1a-time-and-output-contract.yaml").read_text(encoding="utf-8"))
    policy = contract["unique_missing_or_invalid_time_policy"]
    require(policy["action"] == "abort_source_object_atomically", "invalid-time action mismatch")
    require(policy["sounding_lineage"] == {"rows_emitted": 0, "time_utc_nullable": False}, "sounding failure contract mismatch")
    require(policy["field_recovery_ledger"] == {
        "row_required": True,
        "field_name": "time_utc",
        "field_available": False,
        "field_status": "known",
        "evidence_kind": "parser_preflight_failure",
    }, "time ledger failure contract mismatch")
    require(contract["valid_time_policy"]["sounding_primary_key"] == ["source_object_id", "parser_ping_index", "beam_index"], "primary key mismatch")
    require(contract["atomicity"]["commit_outputs_only_after_both_U3_and_U0_streams_validate_and_join"] is True, "atomic commit disabled")
    require(contract["atomicity"]["partial_sounding_or_contributor_output_for_failed_object"] is False, "partial output allowed")

    require(authorization["stage_c_authorized"] is False, "authorization template is active")
    require(authorization["authorized_by"] == "" and authorization["authorized_utc"] == "", "inactive authorization identity populated")
    require(authorization["processing_run_id"] == "<REQUIRED_SAFE_SINGLE_SEGMENT_ID>", "processing run placeholder mismatch")
    require(authorization["stage_c1a_readiness_manifest_sha256"] == "<REQUIRED_PASS_C1A_MANIFEST_SHA256>", "manifest placeholder mismatch")
    require(authorization["stage_c1a_readiness_verification_sha256"] == "<REQUIRED_PASS_C1A_VERIFICATION_SHA256>", "verification placeholder mismatch")
    require(authorization["accepted_stage_c1_readiness_manifest_sha256"] == PREDECESSOR_MANIFEST_SHA256, "authorization predecessor manifest mismatch")
    require(authorization["accepted_stage_c1_readiness_verification_sha256"] == PREDECESSOR_VERIFICATION_SHA256, "authorization predecessor verification mismatch")
    require(authorization["parser_environment_digest"] == environment_digest, "authorization environment digest mismatch")
    require(authorization["immutable_primary_cruise_ids"] == PRIMARY_IDS, "authorization cruise order mismatch")
    prohibited = (
        "gebco_or_product_comparison_authorized",
        "model_comparison_authorized",
        "mrar_merge_authorized",
        "cross_cruise_aggregation_authorized",
        "datum_or_bias_fit_authorized",
        "confirmation_role_promotion_authorized",
        "confirmation_role_eligible",
    )
    for key in prohibited:
        require(authorization[key] is False, f"authorization enables prohibited action: {key}")
    return 16 + len(prohibited)


def verify_zero_access(access: dict[str, Any], readiness: dict[str, Any], tests: dict[str, Any]) -> int:
    require(access["stage_b_objects_root_opened"] is False, "Stage B objects root was opened")
    zero_keys = (
        "sealed_object_body_read_count",
        "archive_decompression_count",
        "candidate_sounding_row_count",
        "candidate_cell_row_count",
        "candidate_qc_result_count",
        "external_product_or_model_reference_count",
        "mrar_merge_count",
        "cross_cruise_aggregation_count",
        "datum_or_bias_fit_count",
    )
    for key in zero_keys:
        require(access[key] == 0, f"access counter is nonzero: {key}")
    require(tests["status"] == "pass" and tests["tests_run"] >= 16, "offline tests did not pass")
    for name in tests["required_test_names"]:
        require(name in tests["stderr"] + tests["stdout"], f"required test missing from output: {name}")
    require(tests["candidate_network_access"] is False and tests["sealed_object_body_read_count"] == 0, "tests accessed candidates")
    require(readiness["status"] == "ready_for_separate_stage_c_authorization", "readiness status mismatch")
    require(readiness["invalid_time_policy"] == "abort_source_object_atomically", "readiness time policy mismatch")
    require(readiness["time_utc_nullable_in_emitted_soundings"] is False, "readiness allows null sounding time")
    require(readiness["parser_ping_index_requires_valid_time"] is True, "readiness ping index time dependency missing")
    require(readiness["stage_c_authorized"] is False and readiness["confirmation_role_eligible"] is False, "readiness promotes role")
    return 16 + len(zero_keys) + len(tests["required_test_names"])


def verify_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    require(run_dir.parent == READINESS_ROOT.resolve(), "run directory outside fixed readiness root")
    require(RUN_ID_RE.fullmatch(run_dir.name) is not None, "unsafe readiness run ID")
    verification_path = run_dir / "verification.json"
    if verification_path.exists():
        raise FileExistsError(f"immutable verification already exists: {verification_path}")

    manifest_path = run_dir / "audit_manifest.json"
    manifest = load_json(manifest_path)
    environment = load_json(run_dir / "environment_lock.json")
    base_fixture = load_json(run_dir / "fixture_verification.json")
    time_fixture = load_json(run_dir / "time_contract_fixture_verification.json")
    tests = load_json(run_dir / "test_results.json")
    authorization = load_json(run_dir / "stage_c_authorization.template.json")
    access = load_json(run_dir / "access_ledger.json")
    readiness = load_json(run_dir / "readiness_lock.json")

    checks = verify_predecessor()
    checks += verify_manifest(run_dir, manifest)
    environment_checks, digest = verify_environment(run_dir, environment)
    checks += environment_checks
    checks += verify_fixture(base_fixture)
    checks += verify_time_fixture(time_fixture)
    checks += verify_contract_and_authorization(run_dir, authorization, digest)
    checks += verify_zero_access(access, readiness, tests)
    require(manifest["summary"] == readiness, "manifest/readiness summary mismatch")
    require(readiness["environment_digest"] == digest, "readiness environment digest mismatch")
    checks += 2

    result = {
        "schema_version": 1,
        "stage": "C1a_zero_candidate_contract_correction",
        "status": "pass",
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "audit_manifest_sha256": sha256_file(manifest_path),
        "accepted_stage_c1_readiness_run_id": PREDECESSOR_RUN_ID,
        "accepted_stage_c1_readiness_manifest_sha256": PREDECESSOR_MANIFEST_SHA256,
        "accepted_stage_c1_readiness_verification_sha256": PREDECESSOR_VERIFICATION_SHA256,
        "environment_digest": digest,
        "offline_tests_run": tests["tests_run"],
        "checks_passed": checks,
        "invalid_time_policy": "abort_source_object_atomically",
        "time_utc_nullable_in_emitted_soundings": False,
        "parser_ping_index_requires_valid_time": True,
        "sealed_object_body_read_count": 0,
        "archive_decompression_count": 0,
        "candidate_sounding_row_count": 0,
        "candidate_cell_row_count": 0,
        "stage_b_objects_root_opened": False,
        "stage_c_authorized": False,
        "confirmation_role_eligible": False,
        "gebco_or_product_comparison_authorized": False,
        "model_comparison_authorized": False,
        "mrar_merge_authorized": False,
        "cross_cruise_aggregation_authorized": False,
        "datum_or_bias_fit_authorized": False,
        "confirmation_role_promotion_authorized": False,
    }
    atomic_json(result, verification_path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    result = verify_run(parser.parse_args().run_dir)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
