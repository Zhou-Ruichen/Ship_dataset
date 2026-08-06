#!/usr/bin/env python3
"""Create an immutable Stage C.1a atomic-time readiness run."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from ncei.code.prepare_scs_v2_stage_c1_readiness import (
    ACCEPTED_C0_LOCK_SHA256,
    CONTRACT_FILES as C1_CONTRACT_FILES,
    GOLDEN_FIXTURE,
    MBSYSTEM_COMMIT,
    MBSYSTEM_TAG,
    PRIMARY_IDS,
    READINESS_ROOT,
    REPO_ROOT,
    RESEARCH_ROOT,
    RUN_ID_RE,
    artifact_record,
    atomic_json,
    canonical_sha256,
    environment_material,
    run_fixture,
    sha256_file,
    utc_now,
    validate_inputs as validate_c1_inputs,
)
from ncei.code.scs_v2_stage_c1_contract import ACQUISITION_RUN_ID
from ncei.code.scs_v2_stage_c1a_contract import (
    TIME_FAILURE_STATUS,
    parse_source_streams_atomically,
)


PREDECESSOR_RUN_ID = "20260806T090504Z"
PREDECESSOR_RUN = READINESS_ROOT / PREDECESSOR_RUN_ID
PREDECESSOR_MANIFEST_SHA256 = "e822e795d90ebee83459d4c13fb2a3a8ad8879f0b54362bb71fc992ee4074789"
PREDECESSOR_VERIFICATION_SHA256 = "443e864009c87ffb315c784c1edaad4a5f5bad209374c4a3816e93ed63ebfb9e"
C1A_CONTRACT_FILES = [
    "stage-c1a-time-and-output-contract.yaml",
    "stage-c1a-fixture-contract.yaml",
    "stage-c1a-verification-contract.yaml",
]
CONTRACT_FILES = [*C1_CONTRACT_FILES, *C1A_CONTRACT_FILES]
FIXTURE_ROOT = REPO_ROOT / "_common/tests/fixtures"
C1_FIXTURE_ROOT = FIXTURE_ROOT / "scs_v2_stage_c1"
C1A_FIXTURE_ROOT = FIXTURE_ROOT / "scs_v2_stage_c1a"
SOURCE_FILES = {
    "base_adapter": REPO_ROOT / "ncei/code/scs_v2_stage_c1_contract.py",
    "base_oracle": REPO_ROOT / "_common/scs_v2_stage_c1_oracle.py",
    "base_future_verifier": REPO_ROOT / "ncei/code/verify_scs_v2_stage_c_source_internal.py",
    "base_readiness_utilities": REPO_ROOT / "ncei/code/prepare_scs_v2_stage_c1_readiness.py",
    "c1a_adapter": REPO_ROOT / "ncei/code/scs_v2_stage_c1a_contract.py",
    "c1a_future_verifier": REPO_ROOT / "ncei/code/verify_scs_v2_stage_c1a_source_internal.py",
    "c1a_readiness_producer": Path(__file__).resolve(),
    "c1a_readiness_verifier": REPO_ROOT / "ncei/code/verify_scs_v2_stage_c1a_readiness.py",
    "base_tests": REPO_ROOT / "_common/tests/test_scs_v2_stage_c1_readiness.py",
    "c1a_tests": REPO_ROOT / "_common/tests/test_scs_v2_stage_c1a_readiness.py",
}
TIME_FIXTURES = {
    "missing_time_in_u3": C1A_FIXTURE_ROOT / "synthetic_missing_time_u3.tsv",
    "invalid_time_in_u3": C1A_FIXTURE_ROOT / "synthetic_invalid_time_u3.tsv",
    "invalid_time_in_u0": C1A_FIXTURE_ROOT / "synthetic_invalid_time_u0.tsv",
}


def normalize_ldd_snapshot(text: str) -> str:
    """Remove ASLR load addresses while preserving resolved dependency paths."""
    return re.sub(r"\(0x[0-9a-fA-F]+\)", "(0xADDR)", text)


def normalize_environment_ldd(material: dict[str, Any], run_dir: Path) -> None:
    for name, record in material["binaries"].items():
        path = run_dir / f"{name}-ldd.txt"
        normalized = normalize_ldd_snapshot(path.read_text(encoding="utf-8"))
        path.write_text(normalized, encoding="utf-8")
        record["ldd_sha256"] = sha256_file(path)
    material["ldd_snapshot_contract"] = {
        "aslr_load_addresses_replaced_with": "0xADDR",
        "resolved_dependency_paths_preserved": True,
        "dependency_file_hashes_recorded_separately": True,
    }


def validate_inputs(environment_root: Path, source_root: Path, planning_commit: str) -> dict[str, Any]:
    c0_lock = validate_c1_inputs(environment_root, source_root, planning_commit)
    if sha256_file(PREDECESSOR_RUN / "audit_manifest.json") != PREDECESSOR_MANIFEST_SHA256:
        raise AssertionError("accepted C1 readiness manifest changed")
    if sha256_file(PREDECESSOR_RUN / "verification.json") != PREDECESSOR_VERIFICATION_SHA256:
        raise AssertionError("accepted C1 readiness verification changed")
    predecessor = json.loads((PREDECESSOR_RUN / "verification.json").read_text(encoding="utf-8"))
    zero_keys = (
        "sealed_object_body_read_count",
        "archive_decompression_count",
        "candidate_sounding_row_count",
        "candidate_cell_row_count",
    )
    if predecessor["status"] != "pass" or any(predecessor[key] != 0 for key in zero_keys):
        raise AssertionError("accepted C1 readiness is not a zero-access pass")
    for path in [
        *SOURCE_FILES.values(),
        *(RESEARCH_ROOT / name for name in CONTRACT_FILES),
        *TIME_FIXTURES.values(),
        C1_FIXTURE_ROOT / "synthetic_all_u3.tsv",
        C1_FIXTURE_ROOT / "synthetic_good_u0.tsv",
    ]:
        if not path.is_file():
            raise FileNotFoundError(path)
    return c0_lock


def run_time_fixtures() -> dict[str, Any]:
    valid_all = (C1_FIXTURE_ROOT / "synthetic_all_u3.tsv").read_text(encoding="ascii")
    valid_good = (C1_FIXTURE_ROOT / "synthetic_good_u0.tsv").read_text(encoding="ascii")
    definitions = {
        "missing_time_in_u3": (TIME_FIXTURES["missing_time_in_u3"].read_text(encoding="ascii"), valid_good, "TIME_UTC_MISSING"),
        "invalid_time_in_u3": (TIME_FIXTURES["invalid_time_in_u3"].read_text(encoding="ascii"), valid_good, "TIME_UTC_INVALID"),
        "invalid_time_in_u0": (valid_all, TIME_FIXTURES["invalid_time_in_u0"].read_text(encoding="ascii"), "TIME_UTC_INVALID"),
    }
    cases: dict[str, Any] = {}
    for name, (all_text, good_text, expected_error) in definitions.items():
        outcome = parse_source_streams_atomically(
            ACQUISITION_RUN_ID,
            f"fixtures/{name}.mb58",
            all_text,
            good_text,
        )
        if (
            outcome.parse_status != TIME_FAILURE_STATUS
            or outcome.error_code != expected_error
            or outcome.parsed_row_count != 0
            or outcome.soundings
            or outcome.time_utc_field_available
        ):
            raise AssertionError(f"atomic time fixture failed: {name}")
        cases[name] = {
            "status": "pass",
            "parse_status": outcome.parse_status,
            "error_code": outcome.error_code,
            "parsed_row_count": outcome.parsed_row_count,
            "sounding_row_count": len(outcome.soundings),
            "contributor_row_count": 0,
            "time_utc_field_available": outcome.time_utc_field_available,
            "time_utc_field_status": outcome.time_utc_field_status,
            "time_utc_evidence_kind": outcome.time_utc_evidence_kind,
        }
    return {
        "schema_version": 1,
        "stage": "C1a_atomic_time_fixture",
        "status": "pass",
        "candidate_data_accessed": False,
        "fixture_sha256": {name: sha256_file(path) for name, path in TIME_FIXTURES.items()},
        "cases": cases,
        "independent_output_verifier_tests": [
            "test_independent_verifier_accepts_atomic_failure_evidence",
            "test_independent_verifier_rejects_failed_object_sounding",
        ],
        "mismatch_count": 0,
        "sealed_object_body_read_count": 0,
        "archive_decompression_count": 0,
        "candidate_sounding_row_count": 0,
        "candidate_cell_row_count": 0,
    }


def run_tests() -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "unittest",
        "-v",
        "_common.tests.test_scs_v2_stage_c1_readiness",
        "_common.tests.test_scs_v2_stage_c1a_readiness",
    ]
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    combined = completed.stdout + completed.stderr
    match = re.search(r"Ran (\d+) tests?", combined)
    count = int(match.group(1)) if match else 0
    required_names = (
        "test_missing_time_in_u3_aborts_without_partial_output",
        "test_invalid_time_in_u3_aborts_without_partial_output",
        "test_invalid_time_in_u0_aborts_without_partial_output",
        "test_independent_verifier_accepts_atomic_failure_evidence",
        "test_independent_verifier_rejects_failed_object_sounding",
    )
    if completed.returncode != 0 or count < 16 or any(name not in combined for name in required_names):
        raise RuntimeError(f"Stage C.1a tests failed:\n{combined}")
    return {
        "status": "pass",
        "command": command,
        "cwd": str(REPO_ROOT),
        "returncode": completed.returncode,
        "tests_run": count,
        "required_test_names": list(required_names),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "candidate_network_access": False,
        "sealed_object_body_read_count": 0,
    }


def produce(environment_root: Path, source_root: Path, planning_commit: str, run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("readiness run ID must be YYYYMMDDTHHMMSSZ")
    environment_root = environment_root.resolve()
    source_root = source_root.resolve()
    c0_lock = validate_inputs(environment_root, source_root, planning_commit)
    final_dir = READINESS_ROOT / run_id
    if final_dir.exists():
        raise FileExistsError(f"immutable readiness run exists: {final_dir}")
    READINESS_ROOT.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=READINESS_ROOT))
    try:
        contracts_dir = temporary_dir / "contracts"
        contracts_dir.mkdir()
        contract_records: dict[str, Any] = {}
        for name in CONTRACT_FILES:
            source = RESEARCH_ROOT / name
            target = contracts_dir / name
            shutil.copy2(source, target)
            contract_records[name] = {
                "source_path": str(source),
                "sha256": sha256_file(target),
                "bytes": target.stat().st_size,
            }

        material, _help_paths = environment_material(environment_root, source_root, temporary_dir)
        normalize_environment_ldd(material, temporary_dir)
        environment_digest = canonical_sha256(material)
        atomic_json(
            {
                "schema_version": 1,
                "stage": "C1_fixed_parser_environment",
                "environment_digest": environment_digest,
                "material": material,
            },
            temporary_dir / "environment_lock.json",
        )
        base_fixture = run_fixture(environment_root, temporary_dir)
        atomic_json(base_fixture, temporary_dir / "fixture_verification.json")
        time_fixture = run_time_fixtures()
        atomic_json(time_fixture, temporary_dir / "time_contract_fixture_verification.json")
        tests = run_tests()
        atomic_json(tests, temporary_dir / "test_results.json")

        source_hashes = {name: {"path": str(path), "sha256": sha256_file(path)} for name, path in SOURCE_FILES.items()}
        authorization = {
            "schema_version": 3,
            "stage_c_authorized": False,
            "authorized_by": "",
            "authorized_utc": "",
            "processing_run_id": "<REQUIRED_SAFE_SINGLE_SEGMENT_ID>",
            "fixed_output_root": str((REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/stage_c").resolve()),
            "acquisition_run_id": ACQUISITION_RUN_ID,
            "immutable_primary_cruise_ids": PRIMARY_IDS,
            "sealed_archive_manifest_sha256": c0_lock["acquisition_run"]["sealed_archive_manifest_sha256"],
            "stage_b_verification_sha256": c0_lock["acquisition_run"]["verification_sha256"],
            "stage_b_access_lock_sha256": c0_lock["acquisition_run"]["access_lock_sha256"],
            "accepted_stage_c0_planning_lock_sha256": ACCEPTED_C0_LOCK_SHA256,
            "accepted_stage_c1_readiness_run_id": PREDECESSOR_RUN_ID,
            "accepted_stage_c1_readiness_manifest_sha256": PREDECESSOR_MANIFEST_SHA256,
            "accepted_stage_c1_readiness_verification_sha256": PREDECESSOR_VERIFICATION_SHA256,
            "stage_c1a_planning_commit": planning_commit,
            "stage_c1a_readiness_run_id": run_id,
            "stage_c1a_readiness_manifest_sha256": "<REQUIRED_PASS_C1A_MANIFEST_SHA256>",
            "stage_c1a_readiness_verification_sha256": "<REQUIRED_PASS_C1A_VERIFICATION_SHA256>",
            "parser_name": "MB-System",
            "parser_version": MBSYSTEM_TAG,
            "parser_source_commit": MBSYSTEM_COMMIT,
            "parser_environment_digest": environment_digest,
            "contract_sha256": {name: record["sha256"] for name, record in contract_records.items()},
            "c1a_adapter_sha256": source_hashes["c1a_adapter"]["sha256"],
            "c1a_future_verifier_sha256": source_hashes["c1a_future_verifier"]["sha256"],
            "c1a_readiness_verifier_sha256": source_hashes["c1a_readiness_verifier"]["sha256"],
            "gebco_or_product_comparison_authorized": False,
            "model_comparison_authorized": False,
            "mrar_merge_authorized": False,
            "cross_cruise_aggregation_authorized": False,
            "datum_or_bias_fit_authorized": False,
            "confirmation_role_promotion_authorized": False,
            "confirmation_role_eligible": False,
        }
        atomic_json(authorization, temporary_dir / "stage_c_authorization.template.json")

        access_ledger = {
            "schema_version": 1,
            "stage": "C1a_zero_candidate_contract_correction",
            "allowed_inputs": [
                str(PREDECESSOR_RUN / "audit_manifest.json"),
                str(PREDECESSOR_RUN / "verification.json"),
                str(environment_root),
                str(source_root),
                str(GOLDEN_FIXTURE),
                *[str(RESEARCH_ROOT / name) for name in CONTRACT_FILES],
                *[str(path) for path in SOURCE_FILES.values()],
                *[str(path) for path in TIME_FIXTURES.values()],
            ],
            "stage_b_objects_root_opened": False,
            "sealed_object_body_read_count": 0,
            "archive_decompression_count": 0,
            "candidate_sounding_row_count": 0,
            "candidate_cell_row_count": 0,
            "candidate_qc_result_count": 0,
            "external_product_or_model_reference_count": 0,
            "mrar_merge_count": 0,
            "cross_cruise_aggregation_count": 0,
            "datum_or_bias_fit_count": 0,
        }
        atomic_json(access_ledger, temporary_dir / "access_ledger.json")

        readiness_lock = {
            "schema_version": 1,
            "stage": "C1a_zero_candidate_contract_correction",
            "status": "ready_for_separate_stage_c_authorization",
            "run_id": run_id,
            "created_utc": utc_now(),
            "planning_commit": planning_commit,
            "accepted_stage_c0_planning_lock_sha256": ACCEPTED_C0_LOCK_SHA256,
            "accepted_stage_c1_readiness_run_id": PREDECESSOR_RUN_ID,
            "accepted_stage_c1_readiness_manifest_sha256": PREDECESSOR_MANIFEST_SHA256,
            "accepted_stage_c1_readiness_verification_sha256": PREDECESSOR_VERIFICATION_SHA256,
            "acquisition_run_id": ACQUISITION_RUN_ID,
            "immutable_primary_cruise_ids": PRIMARY_IDS,
            "environment_digest": environment_digest,
            "invalid_time_policy": "abort_source_object_atomically",
            "time_utc_nullable_in_emitted_soundings": False,
            "parser_ping_index_requires_valid_time": True,
            "base_fixture_status": base_fixture["status"],
            "time_fixture_status": time_fixture["status"],
            "offline_tests_run": tests["tests_run"],
            "sealed_object_body_read_count": 0,
            "archive_decompression_count": 0,
            "candidate_sounding_row_count": 0,
            "candidate_cell_row_count": 0,
            "stage_c_authorized": False,
            "confirmation_role_eligible": False,
        }
        atomic_json(readiness_lock, temporary_dir / "readiness_lock.json")

        output_names = [
            "environment_lock.json",
            "conda-explicit-lock.txt",
            "mbsystem-source-tree.tsv",
            "CMakeCache.txt",
            *[f"{name}-help.txt" for name in material["binaries"]],
            *[f"{name}-ldd.txt" for name in material["binaries"]],
            "fixture_verification.json",
            "time_contract_fixture_verification.json",
            "test_results.json",
            "stage_c_authorization.template.json",
            "access_ledger.json",
            "readiness_lock.json",
        ]
        outputs: dict[str, Any] = {}
        for name in output_names:
            path = temporary_dir / name
            outputs[name] = artifact_record(path, final_dir / name)
        for name in CONTRACT_FILES:
            path = contracts_dir / name
            outputs[f"contracts/{name}"] = artifact_record(path, final_dir / "contracts" / name)

        audit_manifest = {
            "schema_version": 1,
            "stage": "C1a_zero_candidate_contract_correction",
            "run_id": run_id,
            "created_utc": utc_now(),
            "planning_commit": planning_commit,
            "accepted_stage_c1": {
                "run_id": PREDECESSOR_RUN_ID,
                "audit_manifest_sha256": PREDECESSOR_MANIFEST_SHA256,
                "verification_sha256": PREDECESSOR_VERIFICATION_SHA256,
            },
            "source_code": source_hashes,
            "contracts": contract_records,
            "outputs": outputs,
            "summary": readiness_lock,
        }
        atomic_json(audit_manifest, temporary_dir / "audit_manifest.json")
        os.replace(temporary_dir, final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(temporary_dir)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment-root", required=True, type=Path)
    parser.add_argument("--mbsystem-source-root", required=True, type=Path)
    parser.add_argument("--planning-commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--confirm-zero-candidate-readiness", action="store_true")
    args = parser.parse_args()
    if not args.confirm_zero_candidate_readiness:
        print("ERROR: --confirm-zero-candidate-readiness is required", file=sys.stderr)
        return 2
    run_dir = produce(args.environment_root, args.mbsystem_source_root, args.planning_commit, args.run_id)
    print(json.dumps({"status": "created_unverified", "run_dir": str(run_dir)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
