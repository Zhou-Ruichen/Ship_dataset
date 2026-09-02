#!/usr/bin/env python3
"""Independently verify a zero-candidate-access Stage C.1 readiness run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

from ncei.code.scs_confirmation.scs_v2_stage_c1_contract import ACQUISITION_RUN_ID, source_object_id


REPO_ROOT = Path(__file__).resolve().parents[3]
TASK_ROOT = REPO_ROOT / ".trellis/tasks/08-06-scs-v2-stage-c0-source-internal-planning"
RESEARCH_ROOT = TASK_ROOT / "research"
READINESS_ROOT = REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/stage_c_readiness"
ACCEPTED_C0_LOCK = RESEARCH_ROOT / "stage-c0-planning-lock.json"
ACCEPTED_C0_LOCK_SHA256 = "ec0a0a491c995c374ac99306a37f3eb9b26e06692616939072736f7b7f08d78e"
MBSYSTEM_COMMIT = "1d9a52ce076c3c3c5f0150b9bcaa30fa108c7422"
MBSYSTEM_TAG = "5.8.3beta16"
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z$")
PRIMARY_IDS = ["EQT20210702", "EQT190012", "EQT180002", "TN352"]
CONTRACT_FILES = [
    "stage-c01-object-identity-contract.json",
    "stage-c01-output-schema.yaml",
    "stage-c01-parser-command-contract.yaml",
    "stage-c01-fixture-contract.yaml",
    "stage-c01-source-internal-qc.yaml",
    "stage-c01-verification-contract.yaml",
]
PACKAGE_KEYS = (
    "name",
    "version",
    "build",
    "build_number",
    "channel",
    "subdir",
    "fn",
    "url",
    "md5",
    "sha256",
    "requested_spec",
)
EXPECTED_PRIMARY_KEYS = {
    "source_object_processing.parquet": ["source_object_id"],
    "sounding_lineage.parquet": ["source_object_id", "parser_ping_index", "beam_index"],
    "cell_cruise_contributors.parquet": ["cell_id", "official_cruise_id", "source_object_id"],
    "cell_cruise_candidates.parquet": ["cell_id", "official_cruise_id"],
    "field_recovery_ledger.parquet": ["official_cruise_id", "source_object_id", "field_name"],
}


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def atomic_json(value: Any, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_manifest(run_dir: Path, manifest: dict[str, Any]) -> int:
    require(manifest["stage"] == "C0.1_C1_zero_candidate_readiness", "manifest stage mismatch")
    require(manifest["run_id"] == run_dir.name, "manifest run ID mismatch")
    require(manifest["accepted_stage_c0"]["sha256"] == ACCEPTED_C0_LOCK_SHA256, "accepted C0 hash mismatch")
    require(Path(manifest["accepted_stage_c0"]["path"]).resolve() == ACCEPTED_C0_LOCK.resolve(), "accepted C0 path mismatch")

    checks = 4
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
        require(copy.stat().st_size == record["bytes"], f"contract byte mismatch: {name}")
        checks += 1

    listed = set(manifest["outputs"])
    actual = {
        str(path.relative_to(run_dir))
        for path in run_dir.rglob("*")
        if path.is_file() and path.name not in {"audit_manifest.json", "verification.json"}
    }
    require(actual == listed, f"readiness output set mismatch: missing={sorted(listed - actual)}, extra={sorted(actual - listed)}")
    checks += 1
    for relative, record in manifest["outputs"].items():
        path = run_dir / relative
        require(Path(record["path"]).resolve() == path.resolve(), f"output path mismatch: {relative}")
        require(path.stat().st_size == record["bytes"], f"output byte mismatch: {relative}")
        require(sha256_file(path) == record["sha256"], f"output hash mismatch: {relative}")
        checks += 1
    return checks


def verify_environment(run_dir: Path, environment_lock: dict[str, Any]) -> tuple[int, str]:
    material = environment_lock["material"]
    digest = canonical_sha256(material)
    require(environment_lock["stage"] == "C1_fixed_parser_environment", "environment stage mismatch")
    require(environment_lock["environment_digest"] == digest, "environment digest mismatch")
    require(material["source"]["commit"] == MBSYSTEM_COMMIT, "MB-System source commit mismatch")
    require(material["source"]["tag"] == MBSYSTEM_TAG, "MB-System source tag mismatch")
    require(sha256_file(run_dir / "mbsystem-source-tree.tsv") == material["source"]["tree_listing_sha256"], "source tree hash mismatch")
    require(sha256_file(run_dir / "conda-explicit-lock.txt") == material["conda_explicit_lock_sha256"], "explicit lock hash mismatch")
    require(sha256_file(run_dir / "CMakeCache.txt") == material["cmake_cache_sha256"], "CMake cache hash mismatch")

    environment_root = Path(material["environment_root"])
    require(environment_root.is_dir(), "fixed environment root missing")
    checks = 8
    for record in material["conda_packages"]:
        metadata = load_json(environment_root / "conda-meta" / record["metadata_filename"])
        current = {key: metadata.get(key) for key in PACKAGE_KEYS}
        current["metadata_filename"] = record["metadata_filename"]
        require(current == record, f"conda package metadata mismatch: {record['metadata_filename']}")
        checks += 1
    require(any(item["name"] == "gzip" and item["version"] == "1.14" for item in material["conda_packages"]), "gzip pin missing")

    for name, record in material["binaries"].items():
        binary = Path(record["path"])
        help_path = run_dir / f"{name}-help.txt"
        ldd_path = run_dir / f"{name}-ldd.txt"
        require(binary.is_file(), f"binary missing: {name}")
        require(binary.stat().st_size == record["bytes"], f"binary bytes mismatch: {name}")
        require(sha256_file(binary) == record["sha256"], f"binary hash mismatch: {name}")
        require(sha256_file(help_path) == record["version_or_help_sha256"], f"binary help hash mismatch: {name}")
        require(sha256_file(ldd_path) == record["ldd_sha256"], f"ldd snapshot mismatch: {name}")
        checks += 1
    for record in material["runtime_files"]:
        path = Path(record["path"])
        require(path.is_file(), f"runtime file missing: {path}")
        require(path.stat().st_size == record["bytes"], f"runtime file bytes mismatch: {path}")
        require(sha256_file(path) == record["sha256"], f"runtime file hash mismatch: {path}")
        checks += 1
    return checks, digest


def verify_fixture(fixture: dict[str, Any]) -> int:
    require(fixture["status"] == "pass", "fixture verification did not pass")
    require(fixture["candidate_data_accessed"] is False, "candidate data was accessed by fixture")
    require(fixture["fixture"]["stage_b_primary_overlap"] is False, "golden fixture overlaps Stage B")
    require(fixture["fixture"]["sha256"] == "03dae8f817bcb4d9b5262bc4094367cbcd011d37cf8c35685aee6fd3d33af2a0", "golden hash mismatch")
    require(fixture["oracle"]["imports_or_executes_mbsystem"] is False, "oracle is not independent")
    require(fixture["mblist"]["field_count"] == 7, "golden field count mismatch")
    require(fixture["mblist"]["field_order"] == ["M", "N", "#", "X", "Y", "z", "H"], "golden field order mismatch")
    require(fixture["mblist"]["delimiter_hex"] == "09", "golden delimiter mismatch")
    require(fixture["mblist"]["record_terminator_hex"] == "0A", "golden record terminator mismatch")
    require(fixture["mblist"]["u3_rows"] == 3456 and fixture["mblist"]["u0_rows"] == 3450, "golden row count mismatch")
    require(fixture["mblist"]["quality_counts"] == {"flagged": 6, "good": 3450}, "golden quality mismatch")
    require(fixture["mbinfo"] == {"record_count": 8, "beam_count": 3456, "good_beam_count": 3450, "flagged_beam_count": 6}, "mbinfo golden count mismatch")
    require(fixture["mismatch_count"] == 0, "golden/oracle mismatch")
    for name, difference in fixture["oracle_max_abs_difference"].items():
        require(difference <= fixture["tolerances"][name], f"oracle tolerance exceeded: {name}")
    return 14 + len(fixture["oracle_max_abs_difference"])


def verify_contracts_and_authorization(run_dir: Path, authorization: dict[str, Any], digest: str) -> int:
    schema = yaml.safe_load((run_dir / "contracts/stage-c01-output-schema.yaml").read_text(encoding="utf-8"))
    actual_primary_keys = {name: value["primary_key"] for name, value in schema["tables"].items()}
    require(actual_primary_keys == EXPECTED_PRIMARY_KEYS, "output primary keys mismatch")
    require(schema["global_contract"]["source_object_sha256_semantics"] == "content_integrity_only", "hash semantics mismatch")
    require(schema["global_contract"]["source_object_id_formula"] == "acquisition_run_id + '/' + canonical_source_object_relative_path", "object ID formula mismatch")

    require(authorization["stage_c_authorized"] is False, "authorization template is active")
    require(authorization["authorized_by"] == "" and authorization["authorized_utc"] == "", "inactive authorization identity populated")
    require(authorization["processing_run_id"] == "<REQUIRED_SAFE_SINGLE_SEGMENT_ID>", "processing run placeholder mismatch")
    require(authorization["stage_c1_readiness_manifest_sha256"] == "<REQUIRED_PASS_READINESS_MANIFEST_SHA256>", "manifest placeholder mismatch")
    require(authorization["stage_c1_readiness_verification_sha256"] == "<REQUIRED_PASS_READINESS_VERIFICATION_SHA256>", "verification placeholder mismatch")
    require(authorization["acquisition_run_id"] == ACQUISITION_RUN_ID, "authorization acquisition run mismatch")
    require(authorization["immutable_primary_cruise_ids"] == PRIMARY_IDS, "authorization cruise IDs/order mismatch")
    require(authorization["parser_source_commit"] == MBSYSTEM_COMMIT, "authorization parser commit mismatch")
    require(authorization["parser_environment_digest"] == digest, "authorization environment digest mismatch")
    require(authorization["confirmation_role_eligible"] is False, "authorization promotes confirmation role")
    require(authorization["model_or_product_evaluation_authorized"] is False, "authorization enables external evaluation")
    require(authorization["stage_d_confirmation_evaluation_authorized"] is False, "authorization enables Stage D")

    empty_sha = hashlib.sha256(b"").hexdigest()
    first = source_object_id(ACQUISITION_RUN_ID, "objects/TN352/navigation/empty-a.fnv")
    second = source_object_id(ACQUISITION_RUN_ID, "objects/TN352/navigation/empty-b.fnv")
    require(first != second, "two empty TN352 objects collapsed to one identity")
    require(len({empty_sha, empty_sha}) == 1, "empty content hash regression setup failed")
    return 17


def verify_zero_access(access: dict[str, Any], readiness: dict[str, Any], tests: dict[str, Any]) -> int:
    require(access["stage_b_objects_root_opened"] is False, "Stage B object root was opened")
    for key in (
        "sealed_object_body_read_count",
        "archive_decompression_count",
        "candidate_sounding_row_count",
        "candidate_cell_row_count",
        "candidate_qc_result_count",
        "product_or_model_reference_count",
    ):
        require(access[key] == 0, f"zero-access counter is nonzero: {key}")
    require(tests["status"] == "pass" and tests["tests_run"] >= 9, "offline tests did not pass")
    require(tests["candidate_network_access"] is False, "tests used candidate network access")
    require(tests["sealed_object_body_read_count"] == 0, "tests read sealed object bodies")
    require(readiness["status"] == "ready_for_separate_stage_c_authorization", "readiness status mismatch")
    require(readiness["sealed_object_body_read_count"] == 0, "readiness body read count nonzero")
    require(readiness["archive_decompression_count"] == 0, "readiness decompression count nonzero")
    require(readiness["candidate_sounding_row_count"] == 0 and readiness["candidate_cell_row_count"] == 0, "readiness candidate rows nonzero")
    require(readiness["stage_c_authorized"] is False, "Stage C is authorized")
    require(readiness["confirmation_role_eligible"] is False, "confirmation role is eligible")
    require(readiness["source_object_id_formula_frozen"] is True, "object ID formula not frozen")
    require(readiness["source_object_sha256_used_as_identity"] is False, "content hash used as identity")
    require(readiness["immutable_primary_cruise_ids"] == PRIMARY_IDS, "readiness cruise IDs/order mismatch")
    return 19


def verify_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    require(run_dir.parent == READINESS_ROOT.resolve(), "run directory is outside fixed readiness root")
    require(RUN_ID_RE.fullmatch(run_dir.name) is not None, "unsafe readiness run ID")
    verification_path = run_dir / "verification.json"
    if verification_path.exists():
        raise FileExistsError(f"immutable verification already exists: {verification_path}")
    require(sha256_file(ACCEPTED_C0_LOCK) == ACCEPTED_C0_LOCK_SHA256, "accepted Stage C.0 planning lock changed")

    manifest_path = run_dir / "audit_manifest.json"
    manifest = load_json(manifest_path)
    environment = load_json(run_dir / "environment_lock.json")
    fixture = load_json(run_dir / "fixture_verification.json")
    tests = load_json(run_dir / "test_results.json")
    authorization = load_json(run_dir / "stage_c_authorization.template.json")
    access = load_json(run_dir / "access_ledger.json")
    readiness = load_json(run_dir / "readiness_lock.json")

    checks = 1
    checks += verify_manifest(run_dir, manifest)
    environment_checks, digest = verify_environment(run_dir, environment)
    checks += environment_checks
    checks += verify_fixture(fixture)
    checks += verify_contracts_and_authorization(run_dir, authorization, digest)
    checks += verify_zero_access(access, readiness, tests)
    require(manifest["summary"] == readiness, "manifest/readiness summary mismatch")
    require(readiness["environment_digest"] == digest, "readiness environment digest mismatch")
    checks += 2

    result = {
        "schema_version": 1,
        "stage": "C0.1_C1_zero_candidate_readiness",
        "status": "pass",
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "audit_manifest_sha256": sha256_file(manifest_path),
        "accepted_stage_c0_planning_lock_sha256": ACCEPTED_C0_LOCK_SHA256,
        "environment_digest": digest,
        "mbsystem_version": MBSYSTEM_TAG,
        "mbsystem_source_commit": MBSYSTEM_COMMIT,
        "fixture_sha256": fixture["fixture"]["sha256"],
        "oracle_sha256": fixture["oracle"]["sha256"],
        "offline_tests_run": tests["tests_run"],
        "checks_passed": checks,
        "sealed_object_body_read_count": 0,
        "archive_decompression_count": 0,
        "candidate_sounding_row_count": 0,
        "candidate_cell_row_count": 0,
        "stage_b_objects_root_opened": False,
        "stage_c_authorized": False,
        "confirmation_role_eligible": False,
        "source_object_id_formula_closed": True,
        "source_object_sha256_used_as_identity": False,
        "two_empty_tn352_objects_remain_distinct": True,
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
