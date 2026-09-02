#!/usr/bin/env python3
"""Independently verify a zero-network Stage B.0 readiness run."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
READINESS_ROOT = (REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/readiness").resolve()
PRIMARY_IDS = ["EQT20210702", "EQT190012", "EQT180002", "TN352"]
EXPECTED_OBJECT_COUNT = 768
EXPECTED_TOTAL_BYTES = 9_626_893_507
DOWNLOAD_CAP_BYTES = 12 * 1024**3
FIXED_OUTPUT_ROOT = (REPO_ROOT / "ncei/archive/scs_v2_sealed_confirmation").resolve()
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(value: Any, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        (node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name),
        None,
    )
    if function is None:
        raise AssertionError(f"required function missing: {path}:{name}")
    return ast.get_source_segment(source, function) or ""


def verify_source_ordering(downloader_path: Path, producer_path: Path) -> dict[str, Any]:
    download_source = function_source(downloader_path, "download_object")
    response_guard = function_source(downloader_path, "validate_response_before_body")
    execute_source = function_source(downloader_path, "execute_stage_b")
    dry_run_source = function_source(downloader_path, "run_dry_run")
    producer_source = producer_path.read_text(encoding="utf-8")
    response_guard_position = download_source.find("validate_response_before_body")
    response_read_position = download_source.find("response.read")
    if response_guard_position < 0 or response_read_position < 0 or response_guard_position > response_read_position:
        raise AssertionError("response guard occurs after body read")
    for token in ("response.geturl", "last-modified", "validate_locked_object_url"):
        if token not in response_guard:
            raise AssertionError(f"response guard lacks required token: {token}")
    authorization_position = execute_source.find("validate_authorization_receipt")
    download_position = execute_source.find("download_object(")
    if authorization_position < 0 or download_position < 0 or authorization_position > download_position:
        raise AssertionError("authorization validation occurs after download call")
    if "urlopen" in dry_run_source or "Request(" in dry_run_source:
        raise AssertionError("Stage B dry-run contains a network path")
    if "urlopen" in producer_source or "urllib.request" in producer_source:
        raise AssertionError("Stage B.0 readiness producer contains a network path")
    return {
        "resolved_url_and_last_modified_before_body": True,
        "authorization_before_network": True,
        "dry_run_network_path": False,
        "readiness_producer_network_path": False,
    }


def verify(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    if run_dir.parent != READINESS_ROOT or not RUN_ID_RE.fullmatch(run_dir.name):
        raise AssertionError("invalid Stage B.0 readiness run path")
    verification_path = run_dir / "verification.json"
    if verification_path.exists():
        raise FileExistsError(f"immutable verification already exists: {verification_path}")
    manifest_path = run_dir / "audit_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("stage") != "B.0_offline_execution_readiness" or manifest.get("run_id") != run_dir.name:
        raise AssertionError("Stage B.0 manifest identity mismatch")
    config_path = Path(manifest["config"]["path"])
    if config_path.stat().st_size != manifest["config"]["bytes"] or sha256_file(config_path) != manifest["config"]["sha256"]:
        raise AssertionError("Stage B.0 config hash mismatch")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    outputs: dict[str, dict[str, Any]] = manifest["outputs"]
    expected_output_names = {
        "authorization_receipt_template",
        "dry_run_receipt",
        "test_results",
        "readiness_lock",
    }
    if set(outputs) != expected_output_names:
        raise AssertionError("Stage B.0 output set mismatch")
    loaded: dict[str, dict[str, Any]] = {}
    for name, record in outputs.items():
        path = Path(record["path"])
        if path.parent != run_dir or not path.is_file():
            raise AssertionError(f"Stage B.0 output path mismatch: {name}")
        if path.stat().st_size != int(record["bytes"]) or sha256_file(path) != record["sha256"]:
            raise AssertionError(f"Stage B.0 output hash mismatch: {name}")
        value = json.loads(path.read_text(encoding="utf-8"))
        actual_schema = [{"name": key, "type": type(value[key]).__name__} for key in sorted(value)]
        if record.get("row_count") != 1 or record.get("schema") != actual_schema:
            raise AssertionError(f"Stage B.0 output schema mismatch: {name}")
        loaded[name] = value

    for name, record in manifest["accepted_stage_a2"].items():
        path = Path(record["path"])
        if path.stat().st_size != int(record["bytes"]) or sha256_file(path) != record["sha256"]:
            raise AssertionError(f"accepted Stage A.2 artifact changed: {name}")
        if record["sha256"] != config["accepted_stage_a2"][name]["sha256"]:
            raise AssertionError(f"accepted Stage A.2 config closure failed: {name}")
    a2_verification = json.loads(Path(manifest["accepted_stage_a2"]["verification"]["path"]).read_text(encoding="utf-8"))
    if a2_verification.get("status") != "pass":
        raise AssertionError("accepted Stage A.2 verification is not pass")

    source_code = manifest["source_code"]
    for name, record in source_code.items():
        path = Path(record["path"])
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise AssertionError(f"Stage B.0 source hash mismatch: {name}")
    if source_code["downloader"]["sha256"] != config["stage_b_downloader"]["sha256"]:
        raise AssertionError("downloader/config SHA256 closure failed")
    if source_code["stage_b_verifier"]["sha256"] != config["stage_b_verifier"]["sha256"]:
        raise AssertionError("Stage B verifier/config SHA256 closure failed")

    authorization = loaded["authorization_receipt_template"]
    expected_authorization = {
        "schema_version": 2,
        "stage_b_authorized": False,
        "a2_run_id": a2_verification["run_id"],
        "a2_manifest_sha256": config["accepted_stage_a2"]["audit_manifest"]["sha256"],
        "a2_verification_sha256": config["accepted_stage_a2"]["verification"]["sha256"],
        "a2_final_download_lock_sha256": config["accepted_stage_a2"]["final_download_lock"]["sha256"],
        "primary_physical_object_lock_sha256": config["accepted_stage_a2"]["primary_physical_object_lock"]["sha256"],
        "immutable_primary_confirmation_cruise_ids": PRIMARY_IDS,
        "aggregate_download_cap_bytes": DOWNLOAD_CAP_BYTES,
        "acquisition_run_id": "<REQUIRED_SAFE_SINGLE_SEGMENT_ID>",
        "fixed_output_root": str(FIXED_OUTPUT_ROOT),
        "stage_b_downloader_sha256": source_code["downloader"]["sha256"],
        "stage_b_verifier_sha256": source_code["stage_b_verifier"]["sha256"],
        "authorized_by": "",
        "authorized_utc": "",
    }
    if authorization != expected_authorization:
        raise AssertionError("authorization receipt template mismatch")

    dry_run = loaded["dry_run_receipt"]
    expected_dry_values = {
        "status": "dry_run_pass",
        "stage_b_authorized": False,
        "primary_cruise_ids": PRIMARY_IDS,
        "physical_object_count": EXPECTED_OBJECT_COUNT,
        "last_modified_locked_count": EXPECTED_OBJECT_COUNT,
        "exact_total_bytes": EXPECTED_TOTAL_BYTES,
        "aggregate_download_cap_bytes": DOWNLOAD_CAP_BYTES,
        "download_count": 0,
        "network_request_count": 0,
        "maximum_post_download_role": "sealed_unprocessed",
        "manifest_verification_status": "pass",
    }
    for key, value in expected_dry_values.items():
        if dry_run.get(key) != value:
            raise AssertionError(f"Stage B dry-run mismatch for {key}")

    tests = loaded["test_results"]
    expected_test_command_tail = ["-m", "unittest", *config["offline_tests"]["modules"]]
    if (
        tests.get("status") != "pass"
        or tests.get("returncode") != 0
        or int(tests.get("tests_run", 0)) < 13
        or tests.get("command", [])[1:] != expected_test_command_tail
        or tests.get("cwd") != str(REPO_ROOT)
    ):
        raise AssertionError("Stage B.0 offline tests did not pass")
    readiness = loaded["readiness_lock"]
    expected_readiness = {
        "status": "ready_for_separate_stage_b_authorization",
        "immutable_primary_confirmation_cruise_ids": PRIMARY_IDS,
        "physical_object_count": EXPECTED_OBJECT_COUNT,
        "last_modified_locked_count": EXPECTED_OBJECT_COUNT,
        "exact_total_bytes": EXPECTED_TOTAL_BYTES,
        "aggregate_download_cap_bytes": DOWNLOAD_CAP_BYTES,
        "fixed_output_root": str(FIXED_OUTPUT_ROOT),
        "stage_b_authorized": False,
        "physical_object_get_count": 0,
        "range_get_count": 0,
        "response_body_read_count": 0,
        "download_count": 0,
        "network_request_count": 0,
        "stage_b_final_manifest_implemented": True,
        "stage_b_access_lock_implemented": True,
        "stage_b_independent_verifier_implemented": True,
        "maximum_post_download_role": "sealed_unprocessed",
        "confirmation_role_eligible": False,
        "stage_c_authorized": False,
    }
    for key, value in expected_readiness.items():
        if readiness.get(key) != value:
            raise AssertionError(f"Stage B.0 readiness mismatch for {key}")
    if manifest.get("summary") != readiness:
        raise AssertionError("Stage B.0 manifest summary differs from readiness lock")

    source_ordering = verify_source_ordering(
        Path(source_code["downloader"]["path"]),
        Path(source_code["producer"]["path"]),
    )
    receipt = {
        "schema_version": 1,
        "stage": "B.0_offline_execution_readiness",
        "status": "pass",
        "run_id": run_dir.name,
        "verified_utc": utc_now(),
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "checks": {
            "accepted_stage_a2_artifacts": len(manifest["accepted_stage_a2"]),
            "readiness_outputs": len(outputs),
            "primary_cruise_ids": PRIMARY_IDS,
            "physical_object_count": EXPECTED_OBJECT_COUNT,
            "last_modified_locked_count": EXPECTED_OBJECT_COUNT,
            "exact_total_bytes": EXPECTED_TOTAL_BYTES,
            "aggregate_download_cap_bytes": DOWNLOAD_CAP_BYTES,
            "offline_tests_run": tests["tests_run"],
            "dry_run_network_request_count": 0,
            "physical_object_get_count": 0,
            "response_body_read_count": 0,
            "stage_b_authorized": False,
            "confirmation_role_eligible": False,
            "source_ordering": source_ordering,
        },
    }
    atomic_json(receipt, verification_path)
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    receipt = verify(parse_args().run_dir)
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
