#!/usr/bin/env python3
"""Materialize an active Stage C authorization receipt without reading sources."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from ncei.code.scs_v2_stage_c_processing import (
    STAGE_C2_2_READINESS_ROOT,
    STAGE_C2_2_READINESS_RUN_ID,
    STAGE_C2_2_TEMPLATE_PATH,
    canonical_authorization_receipt_sha256,
    safe_processing_run_id,
    sha256_file,
    validate_readiness_bundle,
    validate_receipt_readiness_bindings,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PLANNING_LOCK_PATH = REPO_ROOT / ".trellis/tasks/08-06-scs-v2-stage-c0-source-internal-planning/research/stage-c0-planning-lock.json"
READINESS_ROOT = STAGE_C2_2_READINESS_ROOT
STAGE_C_ROOT = REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/stage_c"
PRIMARY_IDS = ["EQT20210702", "EQT190012", "EQT180002", "TN352"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def materialize_authorization(
    *,
    template_path: Path,
    processing_run_id: str,
    authorized_by: str,
    authorized_utc: str,
    output_path: Path,
    processor_path: Path,
    verifier_path: Path,
    processing_helper_path: Path,
    authorization_script_path: Path,
    output_schema_path: Path,
    qc_contract_path: Path,
    verification_contract_path: Path,
    readiness_root: Path = READINESS_ROOT,
    expected_readiness_run_id: str = STAGE_C2_2_READINESS_RUN_ID,
    stage_c_root: Path = STAGE_C_ROOT,
    planning_lock_path: Path = PLANNING_LOCK_PATH,
) -> dict[str, Any]:
    run_id = safe_processing_run_id(processing_run_id)
    require(authorized_by.strip() != "", "authorized_by is required")
    datetime.fromisoformat(authorized_utc.replace("Z", "+00:00"))

    code_bindings = {
        "stage_c_processing_helper_sha256": ("stage_c_processing_helper", processing_helper_path),
        "stage_c_processor_sha256": ("stage_c_processor", processor_path),
        "stage_c_authorizer_sha256": ("stage_c_authorizer", authorization_script_path),
        "stage_c_verifier_sha256": ("stage_c_verifier", verifier_path),
    }
    contract_bindings = {
        "output_schema_sha256": ("stage-c01-output-schema.yaml", output_schema_path),
        "qc_contract_sha256": ("stage-c01-source-internal-qc.yaml", qc_contract_path),
        "verification_contract_sha256": ("stage-c01-verification-contract.yaml", verification_contract_path),
    }
    readiness = validate_readiness_bundle(
        readiness_root,
        expected_readiness_run_id,
        code_bindings=code_bindings,
        contract_bindings=contract_bindings,
    )
    require(template_path.resolve() == readiness["template_path"], "authorization template is not the readiness snapshot")
    template = load(template_path)
    require(template["stage_c_authorized"] is False, "template is already active")
    require(template["processing_run_id"] == "<REQUIRED_SAFE_SINGLE_SEGMENT_ID>", "template placeholder mismatch")
    require(template["fixed_output_root"] == str(stage_c_root.resolve()), "template output root mismatch")
    require(not (stage_c_root / run_id).exists(), "processing run already exists")

    environment = load(readiness_root / "environment_lock.json")
    fixture = load(readiness_root / "fixture_verification.json")
    require(planning_lock_path.is_file(), "stage C0 planning lock missing")
    planning_lock_sha = sha256_file(planning_lock_path)
    planning_commit = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "log", "-1", "--format=%H", "--", str(planning_lock_path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    require(re.fullmatch(r"[0-9a-f]{40}", planning_commit) is not None, "planning commit not resolved")

    receipt = dict(template)
    receipt.pop("producer_sha256", None)
    receipt.update(
        {
            "schema_version": 5,
            "stage_c_authorized": True,
            "authorized_by": authorized_by,
            "authorized_utc": authorized_utc,
            "processing_run_id": run_id,
            "stage_c_readiness_run_id": readiness["run_id"],
            "authorization_template_sha256": readiness["template_sha256"],
            "authorization_script_sha256": readiness["code_hashes"]["stage_c_authorizer_sha256"],
            "processor_sha256": readiness["code_hashes"]["stage_c_processor_sha256"],
            "verifier_sha256": readiness["code_hashes"]["stage_c_verifier_sha256"],
            "processing_helper_sha256": readiness["code_hashes"]["stage_c_processing_helper_sha256"],
            **readiness["contract_hashes"],
            "stage_c0_planning_lock_sha256": planning_lock_sha,
            "stage_c0_planning_commit": planning_commit,
            "parser_environment_digest": environment["environment_digest"],
            "parser_binary_sha256": {
                name: environment["material"]["binaries"][name]["sha256"]
                for name in ("mblist", "mbinfo", "gzip")
            },
            "parser_help_snapshot_sha256": {
                name: environment["material"]["binaries"][name]["version_or_help_sha256"]
                for name in ("mblist", "mbinfo", "gzip")
            },
            "fixture_verification_sha256": sha256_file(readiness_root / "fixture_verification.json"),
            "time_fixture_verification_sha256": sha256_file(readiness_root / "time_contract_fixture_verification.json"),
            "format58_fixture_bytes_sha256": fixture["fixture"]["sha256"],
            "format58_fixture_oracle_sha256": fixture["oracle"]["sha256"],
            "stage_c1a_readiness_manifest_sha256": readiness["manifest_sha256"],
            "stage_c1a_readiness_verification_sha256": readiness["verification_sha256"],
            "source_internal_only": True,
            "permitted_body_read_counts": {".mb58.gz": 192, ".fnv": 0, ".inf": 0, ".fbt": 0},
            "prohibited_external_inputs": ["GEBCO", "product", "model", "GGM", "PINN", "MRAR_merge"],
            "gebco_or_product_comparison_authorized": False,
            "model_comparison_authorized": False,
            "mrar_merge_authorized": False,
            "cross_cruise_aggregation_authorized": False,
            "datum_or_bias_fit_authorized": False,
            "confirmation_role_promotion_authorized": False,
            "confirmation_role_eligible": False,
            "model_or_product_evaluation_authorized": False,
            "stage_d_confirmation_evaluation_authorized": False,
        }
    )
    receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(receipt)
    validate_receipt_readiness_bindings(receipt, readiness)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        raise FileExistsError(output_path)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output_path)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--processing-run-id", required=True)
    parser.add_argument("--authorized-by", required=True)
    parser.add_argument("--authorized-utc", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--processor", required=True, type=Path)
    parser.add_argument("--verifier", required=True, type=Path)
    parser.add_argument("--processing-helper", required=True, type=Path)
    parser.add_argument("--authorization-script", required=True, type=Path)
    parser.add_argument("--output-schema", required=True, type=Path)
    parser.add_argument("--qc-contract", required=True, type=Path)
    parser.add_argument("--verification-contract", required=True, type=Path)
    args = parser.parse_args()
    receipt = materialize_authorization(
        template_path=args.template,
        processing_run_id=args.processing_run_id,
        authorized_by=args.authorized_by,
        authorized_utc=args.authorized_utc,
        output_path=args.output,
        processor_path=args.processor,
        verifier_path=args.verifier,
        processing_helper_path=args.processing_helper,
        authorization_script_path=args.authorization_script,
        output_schema_path=args.output_schema,
        qc_contract_path=args.qc_contract,
        verification_contract_path=args.verification_contract,
    )
    print(json.dumps({"status": "active", "receipt": str(args.output), "sha256": sha256_file(args.output), "run_id": receipt["stage_c_readiness_run_id"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
