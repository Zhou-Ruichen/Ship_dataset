#!/usr/bin/env python3
"""Materialize an active Stage C authorization receipt without reading sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ncei.code.scs_v2_stage_c_processing import canonical_authorization_receipt_sha256


REPO_ROOT = Path(__file__).resolve().parents[2]
SEALED_ROOT = REPO_ROOT / "ncei/archive/scs_v2_sealed_confirmation/20260805T230449Z"
READINESS_ROOT = REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/stage_c_readiness/20260806T093740Z"
STAGE_C_ROOT = REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/stage_c"
ACQUISITION_RUN_ID = "20260805T230449Z"
C1A_MANIFEST_SHA256 = "c260960dc4999f08bad710b7d2f6111acd90087a158eb661957f01280bc89615"
C1A_VERIFICATION_SHA256 = "9f3464bfa3f1a90d319761b543bb5488d0d5c154bfc6837b23a278d53558c717"
PRIMARY_IDS = ["EQT20210702", "EQT190012", "EQT180002", "TN352"]
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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

    run_id = args.processing_run_id
    require(RUN_ID_RE.fullmatch(run_id) is not None and ".." not in run_id and "/" not in run_id and "\\" not in run_id, "unsafe processing run ID")
    require(args.authorized_by.strip() != "", "authorized_by is required")
    datetime.fromisoformat(args.authorized_utc.replace("Z", "+00:00"))
    require(args.template.is_file(), "authorization template missing")
    template = load(args.template)
    require(template["stage_c_authorized"] is False, "template is already active")
    require(template["processing_run_id"] == "<REQUIRED_SAFE_SINGLE_SEGMENT_ID>", "template placeholder mismatch")
    require(sha256_file(READINESS_ROOT / "audit_manifest.json") == "c260960dc4999f08bad710b7d2f6111acd90087a158eb661957f01280bc89615", "C1a manifest changed")
    require(sha256_file(READINESS_ROOT / "verification.json") == "9f3464bfa3f1a90d319761b543bb5488d0d5c154bfc6837b23a278d53558c717", "C1a verification changed")
    verification = load(READINESS_ROOT / "verification.json")
    require(verification["status"] == "pass" and verification["stage_c_authorized"] is False, "C1a readiness is not an inactive pass")
    require(not (REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/stage_c" / run_id).exists(), "processing run already exists")

    for path in [args.processor, args.verifier, args.processing_helper, args.authorization_script, args.output_schema, args.qc_contract, args.verification_contract]:
        require(path.is_file(), f"authorization input missing: {path}")
    environment = load(READINESS_ROOT / "environment_lock.json")
    fixture = load(READINESS_ROOT / "fixture_verification.json")
    template_sha = sha256_file(args.template)
    receipt = dict(template)
    receipt.update(
        {
            "schema_version": 4,
            "stage_c_authorized": True,
            "authorized_by": args.authorized_by,
            "authorized_utc": args.authorized_utc,
            "processing_run_id": run_id,
            "authorization_template_sha256": template_sha,
            "authorization_script_sha256": sha256_file(args.authorization_script),
            "processor_sha256": sha256_file(args.processor),
            "verifier_sha256": sha256_file(args.verifier),
            "processing_helper_sha256": sha256_file(args.processing_helper),
            "output_schema_sha256": sha256_file(args.output_schema),
            "qc_contract_sha256": sha256_file(args.qc_contract),
            "verification_contract_sha256": sha256_file(args.verification_contract),
            "parser_environment_digest": environment["environment_digest"],
            "parser_binary_sha256": {
                name: environment["material"]["binaries"][name]["sha256"]
                for name in ("mblist", "mbinfo", "gzip")
            },
            "parser_help_snapshot_sha256": {
                name: environment["material"]["binaries"][name]["version_or_help_sha256"]
                for name in ("mblist", "mbinfo", "gzip")
            },
            "fixture_verification_sha256": sha256_file(READINESS_ROOT / "fixture_verification.json"),
            "time_fixture_verification_sha256": sha256_file(READINESS_ROOT / "time_contract_fixture_verification.json"),
            "format58_fixture_bytes_sha256": fixture["fixture"]["sha256"],
            "format58_fixture_oracle_sha256": fixture["oracle"]["sha256"],
            "stage_c1a_readiness_manifest_sha256": C1A_MANIFEST_SHA256,
            "stage_c1a_readiness_verification_sha256": C1A_VERIFICATION_SHA256,
            "source_internal_only": True,
            "permitted_body_read_counts": {".mb58.gz": 192, ".fnv": 0, ".inf": 0, ".fbt": 0},
            "prohibited_external_inputs": ["GEBCO", "product", "model", "GGM", "PINN", "MRAR_merge"],
            "confirmation_role_eligible": False,
            "model_or_product_evaluation_authorized": False,
            "stage_d_confirmation_evaluation_authorized": False,
        }
    )
    receipt["authorization_receipt_sha256"] = canonical_authorization_receipt_sha256(receipt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(args.output)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps({"status": "active", "receipt": str(args.output), "sha256": sha256_file(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
