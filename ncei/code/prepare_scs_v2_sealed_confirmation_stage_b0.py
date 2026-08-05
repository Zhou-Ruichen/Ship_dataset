#!/usr/bin/env python3
"""Create an immutable, zero-network Stage B.0 readiness receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
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


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def atomic_json(value: Any, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def json_schema(value: dict[str, Any]) -> list[dict[str, str]]:
    return [{"name": key, "type": type(value[key]).__name__} for key in sorted(value)]


def artifact_record(path: Path, published_path: Path, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(published_path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "row_count": 1,
        "schema": json_schema(value),
    }


def validate_config(path: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1 or config.get("stage") != "B.0_offline_execution_readiness":
        raise ValueError("unsupported Stage B.0 config")
    expected_guards = {
        "stage_b_authorized": False,
        "physical_object_get_allowed": False,
        "range_get_allowed": False,
        "response_body_read_allowed": False,
        "archive_parse_allowed": False,
        "candidate_depth_read_allowed": False,
        "cell_generation_allowed": False,
        "reference_or_model_comparison_allowed": False,
        "candidate_replacement_allowed": False,
        "stage_c_authorized": False,
        "confirmation_role_eligible": False,
    }
    if config.get("guards") != expected_guards:
        raise ValueError("Stage B.0 guards differ from the zero-network contract")
    if config.get("immutable_primary_confirmation_cruise_ids") != PRIMARY_IDS:
        raise ValueError("Stage B.0 primary cruise IDs/order changed")
    if int(config.get("physical_object_count", -1)) != EXPECTED_OBJECT_COUNT:
        raise ValueError("Stage B.0 physical-object count changed")
    if int(config.get("exact_total_bytes", -1)) != EXPECTED_TOTAL_BYTES:
        raise ValueError("Stage B.0 exact total bytes changed")
    if int(config.get("aggregate_download_cap_bytes", -1)) != DOWNLOAD_CAP_BYTES:
        raise ValueError("Stage B.0 download cap changed")
    if Path(config.get("fixed_output_root", "")).resolve() != FIXED_OUTPUT_ROOT:
        raise ValueError("Stage B.0 fixed output root changed")
    if config.get("maximum_post_download_role") != "sealed_unprocessed":
        raise ValueError("Stage B.0 role ceiling changed")

    paths: dict[str, Path] = {}
    for name, record in config["accepted_stage_a2"].items():
        if name == "run_dir":
            continue
        source = resolve_path(record["path"])
        if sha256_file(source) != record["sha256"]:
            raise ValueError(f"accepted A.2 hash mismatch: {name}")
        paths[f"a2_{name}"] = source
    for name in ("stage_b_downloader", "stage_b_verifier"):
        source = resolve_path(config[name]["path"])
        if sha256_file(source) != config[name]["sha256"]:
            raise ValueError(f"Stage B.0 source hash mismatch: {name}")
        paths[name] = source
    return config, paths


def run_offline_tests(modules: list[str]) -> dict[str, Any]:
    command = [sys.executable, "-m", "unittest", *modules]
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    combined = completed.stdout + completed.stderr
    match = re.search(r"Ran (\d+) tests?", combined)
    tests_run = int(match.group(1)) if match else 0
    result = {
        "status": "pass" if completed.returncode == 0 and tests_run > 0 else "fail",
        "command": command,
        "cwd": str(REPO_ROOT),
        "returncode": completed.returncode,
        "tests_run": tests_run,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "network_test_policy": "all transport calls in Stage B tests are mocked; no live endpoint is used",
    }
    if result["status"] != "pass":
        raise RuntimeError(f"offline Stage B.0 tests failed: {combined}")
    return result


def run_stage_b_dry_run(downloader_path: Path, a2_run: Path) -> dict[str, Any]:
    command = [sys.executable, str(downloader_path), "--a2-run", str(a2_run), "--dry-run"]
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Stage B dry-run failed: {completed.stderr}")
    try:
        receipt = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Stage B dry-run did not emit one JSON receipt") from error
    receipt["command"] = command
    receipt["cwd"] = str(REPO_ROOT)
    receipt["returncode"] = completed.returncode
    return receipt


def build_authorization_template(config: dict[str, Any], paths: dict[str, Path]) -> dict[str, Any]:
    a2_lock = json.loads(paths["a2_final_download_lock"].read_text(encoding="utf-8"))
    return {
        "schema_version": 2,
        "stage_b_authorized": False,
        "a2_run_id": a2_lock["run_id"],
        "a2_manifest_sha256": config["accepted_stage_a2"]["audit_manifest"]["sha256"],
        "a2_verification_sha256": config["accepted_stage_a2"]["verification"]["sha256"],
        "a2_final_download_lock_sha256": config["accepted_stage_a2"]["final_download_lock"]["sha256"],
        "primary_physical_object_lock_sha256": config["accepted_stage_a2"]["primary_physical_object_lock"]["sha256"],
        "immutable_primary_confirmation_cruise_ids": PRIMARY_IDS,
        "aggregate_download_cap_bytes": DOWNLOAD_CAP_BYTES,
        "acquisition_run_id": "<REQUIRED_SAFE_SINGLE_SEGMENT_ID>",
        "fixed_output_root": str(FIXED_OUTPUT_ROOT),
        "stage_b_downloader_sha256": sha256_file(paths["stage_b_downloader"]),
        "stage_b_verifier_sha256": sha256_file(paths["stage_b_verifier"]),
        "authorized_by": "",
        "authorized_utc": "",
    }


def produce(config_path: Path, run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("Stage B.0 readiness run ID must be YYYYMMDDTHHMMSSZ")
    config_path = config_path.resolve()
    config, paths = validate_config(config_path)
    final_dir = READINESS_ROOT / run_id
    if final_dir.exists():
        raise FileExistsError(f"immutable Stage B.0 readiness run exists: {final_dir}")
    READINESS_ROOT.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=READINESS_ROOT))
    try:
        a2_run = resolve_path(config["accepted_stage_a2"]["run_dir"])
        dry_run = run_stage_b_dry_run(paths["stage_b_downloader"], a2_run)
        if dry_run.get("network_request_count") != 0 or dry_run.get("download_count") != 0:
            raise AssertionError("Stage B dry-run performed network or download work")
        tests = run_offline_tests(list(config["offline_tests"]["modules"]))
        authorization_template = build_authorization_template(config, paths)
        readiness_lock = {
            "schema_version": 1,
            "stage": "B.0_offline_execution_readiness",
            "status": "ready_for_separate_stage_b_authorization",
            "created_utc": utc_now(),
            "run_id": run_id,
            "accepted_stage_a2_run_id": dry_run["a2_run_id"],
            "immutable_primary_confirmation_cruise_ids": PRIMARY_IDS,
            "physical_object_count": EXPECTED_OBJECT_COUNT,
            "last_modified_locked_count": dry_run["last_modified_locked_count"],
            "exact_total_bytes": EXPECTED_TOTAL_BYTES,
            "aggregate_download_cap_bytes": DOWNLOAD_CAP_BYTES,
            "fixed_output_root": str(FIXED_OUTPUT_ROOT),
            "stage_b_downloader_sha256": sha256_file(paths["stage_b_downloader"]),
            "stage_b_verifier_sha256": sha256_file(paths["stage_b_verifier"]),
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
        values = {
            "authorization_receipt_template": authorization_template,
            "dry_run_receipt": dry_run,
            "test_results": tests,
            "readiness_lock": readiness_lock,
        }
        filenames = {
            "authorization_receipt_template": "authorization_receipt.template.json",
            "dry_run_receipt": "stage_b_dry_run_receipt.json",
            "test_results": "test_results.json",
            "readiness_lock": "readiness_lock.json",
        }
        outputs: dict[str, dict[str, Any]] = {}
        for name, value in values.items():
            path = temporary_dir / filenames[name]
            atomic_json(value, path)
            outputs[name] = artifact_record(path, final_dir / filenames[name], value)

        audit_manifest = {
            "schema_version": 1,
            "stage": "B.0_offline_execution_readiness",
            "run_id": run_id,
            "created_utc": utc_now(),
            "config": {
                "path": str(config_path),
                "bytes": config_path.stat().st_size,
                "sha256": sha256_file(config_path),
            },
            "accepted_stage_a2": {
                name: {
                    "path": str(paths[f"a2_{name}"]),
                    "bytes": paths[f"a2_{name}"].stat().st_size,
                    "sha256": config["accepted_stage_a2"][name]["sha256"],
                }
                for name in ("audit_manifest", "verification", "final_download_lock", "primary_physical_object_lock")
            },
            "source_code": {
                "producer": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve())},
                "downloader": {"path": str(paths["stage_b_downloader"]), "sha256": sha256_file(paths["stage_b_downloader"])},
                "stage_b_verifier": {"path": str(paths["stage_b_verifier"]), "sha256": sha256_file(paths["stage_b_verifier"])},
                "readiness_verifier": {
                    "path": str((REPO_ROOT / "ncei/code/verify_scs_v2_sealed_confirmation_stage_b0.py").resolve()),
                    "sha256": sha256_file(REPO_ROOT / "ncei/code/verify_scs_v2_sealed_confirmation_stage_b0.py"),
                },
                "test_stage_a2": {
                    "path": str((REPO_ROOT / "_common/tests/test_scs_v2_sealed_confirmation_stage_a2.py").resolve()),
                    "sha256": sha256_file(REPO_ROOT / "_common/tests/test_scs_v2_sealed_confirmation_stage_a2.py"),
                },
                "test_stage_b0": {
                    "path": str((REPO_ROOT / "_common/tests/test_scs_v2_sealed_confirmation_stage_b0.py").resolve()),
                    "sha256": sha256_file(REPO_ROOT / "_common/tests/test_scs_v2_sealed_confirmation_stage_b0.py"),
                },
            },
            "outputs": outputs,
            "summary": readiness_lock,
        }
        atomic_json(audit_manifest, temporary_dir / "audit_manifest.json")
        os.replace(temporary_dir, final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(temporary_dir)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--confirm-stage-b0-readiness", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confirm_stage_b0_readiness:
        print("ERROR: --confirm-stage-b0-readiness is required.", file=sys.stderr)
        return 2
    result = produce(args.config, args.run_id)
    print(json.dumps({"status": "created_unverified", "run_dir": str(result)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
