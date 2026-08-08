#!/usr/bin/env python3
"""Source-internal Stage C parser, QC, lineage and exact aggregation helpers."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sqlite3
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from ncei.code.scs_v2_stage_c1_contract import (
    MblistRow,
    cell_assignment,
    cell_center,
    normalize_longitude,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE_C2_3_READINESS_RUN_ID = "20260809T040000Z"
STAGE_C2_3_READINESS_ROOT = (
    REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/stage_c_readiness" / STAGE_C2_3_READINESS_RUN_ID
)
STAGE_C2_3_TEMPLATE_SOURCE_PATH = (
    REPO_ROOT / ".trellis/tasks/08-06-scs-v2-stage-c0-source-internal-planning/research/stage-c-authorization.template.json"
)
STAGE_C2_3_TEMPLATE_PATH = STAGE_C2_3_READINESS_ROOT / "stage_c_authorization.template.json"
STAGE_C_PRODUCTION_CODE_BINDINGS = {
    "stage_c_processing_helper_sha256": ("stage_c_processing_helper", Path(__file__).resolve()),
    "stage_c_processor_sha256": ("stage_c_processor", REPO_ROOT / "ncei/code/process_scs_v2_stage_c_source_internal.py"),
    "stage_c_authorizer_sha256": ("stage_c_authorizer", REPO_ROOT / "ncei/code/authorize_scs_v2_stage_c.py"),
    "stage_c_verifier_sha256": ("stage_c_verifier", REPO_ROOT / "ncei/code/verify_scs_v2_stage_c_processing.py"),
}
STAGE_C_PRODUCTION_CONTRACT_BINDINGS = {
    "output_schema_sha256": (
        "stage-c01-output-schema.yaml",
        REPO_ROOT / ".trellis/tasks/08-06-scs-v2-stage-c0-source-internal-planning/research/stage-c01-output-schema.yaml",
    ),
    "qc_contract_sha256": (
        "stage-c01-source-internal-qc.yaml",
        REPO_ROOT / ".trellis/tasks/08-06-scs-v2-stage-c0-source-internal-planning/research/stage-c01-source-internal-qc.yaml",
    ),
    "verification_contract_sha256": (
        "stage-c01-verification-contract.yaml",
        REPO_ROOT / ".trellis/tasks/08-06-scs-v2-stage-c0-source-internal-planning/research/stage-c01-verification-contract.yaml",
    ),
}
AUTHORIZATION_SCAFFOLD_REMOVED = frozenset({"producer_sha256"})
AUTHORIZATION_RECEIPT_ONLY_FIELDS = frozenset(
    {
        "authorization_receipt_sha256",
        "authorization_script_sha256",
        "authorization_template_sha256",
        "confirmation_role_promotion_authorized",
        "cross_cruise_aggregation_authorized",
        "datum_or_bias_fit_authorized",
        "gebco_or_product_comparison_authorized",
        "model_comparison_authorized",
        "mrar_merge_authorized",
        "parser_binary_sha256",
        "permitted_body_read_counts",
        "processing_helper_sha256",
        "processor_sha256",
        "prohibited_external_inputs",
        "source_internal_only",
        "stage_c_readiness_run_id",
        "stage_c1a_readiness_manifest_sha256",
        "stage_c1a_readiness_verification_sha256",
        "time_fixture_verification_sha256",
    }
)
# Compatibility export used by the production verifier and existing schema tests.
AUTHORIZATION_ADDED_KEYS = AUTHORIZATION_RECEIPT_ONLY_FIELDS
ACTIVE_AUTHORIZATION_RECEIPT_SCHEMA_VERSION = 6
STAGE_C0_PLANNING_LOCK_SHA256 = "ec0a0a491c995c374ac99306a37f3eb9b26e06692616939072736f7b7f08d78e"
STAGE_C0_PLANNING_COMMIT = "0aadea0d5f94783d138fdf6b4479e6f51b0d35db"
AUTHORIZATION_TEMPLATE_FIXED_FIELDS = frozenset(
    {
        "access_lock_sha256",
        "acquisition_run_id",
        "command_contract_sha256",
        "confirmation_role_eligible",
        "fixed_output_root",
        "fixture_contract_sha256",
        "immutable_primary_cruise_ids",
        "model_or_product_evaluation_authorized",
        "object_count",
        "parser_name",
        "parser_source_commit",
        "parser_version",
        "permitted_object_reads",
        "sealed_archive_manifest_sha256",
        "stage_b_verification_sha256",
        "stage_d_confirmation_evaluation_authorized",
        "total_bytes",
    }
)
AUTHORIZATION_TEMPLATE_EVIDENCE_FIELDS = frozenset(
    {
        "fixture_verification_sha256",
        "format58_fixture_bytes_sha256",
        "format58_fixture_oracle_sha256",
        "output_schema_sha256",
        "parser_environment_digest",
        "parser_help_snapshot_sha256",
        "qc_contract_sha256",
        "stage_c0_planning_commit",
        "stage_c0_planning_lock_sha256",
        "verification_contract_sha256",
        "verifier_sha256",
    }
)
AUTHORIZATION_TEMPLATE_ACTIVATION_FIELDS = frozenset(
    {
        "authorized_by",
        "authorized_utc",
        "processing_run_id",
        "schema_version",
        "stage_c_authorized",
    }
)
AUTHORIZATION_VARIABLE_ACTIVATION_FIELDS = frozenset(
    {"authorized_by", "authorized_utc", "processing_run_id"}
)
PERMITTED_BODY_READ_COUNTS = {".mb58.gz": 192, ".fnv": 0, ".inf": 0, ".fbt": 0}
PROHIBITED_EXTERNAL_INPUTS = ["GEBCO", "product", "model", "GGM", "PINN", "MRAR_merge"]
PROHIBITED_AUTHORIZATION_FIELDS = (
    "gebco_or_product_comparison_authorized",
    "model_comparison_authorized",
    "mrar_merge_authorized",
    "cross_cruise_aggregation_authorized",
    "datum_or_bias_fit_authorized",
    "confirmation_role_promotion_authorized",
    "confirmation_role_eligible",
    "model_or_product_evaluation_authorized",
    "stage_d_confirmation_evaluation_authorized",
)


RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
FIVE_LEVEL_STATUS = {
    "known",
    "officially_unknown",
    "not_recoverable",
    "inferred_from_filename",
    "verified_from_source_metadata",
}
TIME_FAILURE_STATUS = "failed_invalid_or_missing_time"
PARSER_FAILURE_STATUS = "failed_parser_contract"
PASS_STATUS = "pass"
SIDECAR_STATUS = "not_applicable_sidecar"
FIELD_NAMES = (
    "time_utc",
    "line_id",
    "native_ping_id",
    "native_beam_id",
    "longitude",
    "latitude",
    "heading",
    "native_quality",
    "native_quality_code",
    "horizontal_datum",
    "vertical_datum",
    "depth",
)


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


def canonical_authorization_receipt_sha256(value: dict[str, Any]) -> str:
    """Hash an authorization receipt without creating an impossible self-hash."""
    payload = dict(value)
    payload.pop("authorization_receipt_sha256", None)
    return canonical_sha256(payload)


def find_placeholder_fields(value: Any, *, marker: str = "<REQUIRED") -> list[str]:
    """Recursively collect JSON paths that still hold a template placeholder.

    Scans dict values and list items at every depth, not just top-level string
    values, so a placeholder nested inside ``permitted_body_read_counts`` or a
    list cannot slip through. Each hit is reported as a dotted path
    (``"a.b[2].c"``); the caller fails loudly when the list is non-empty.
    """
    hits: list[str] = []

    def walk(node: Any, prefix: str) -> None:
        if isinstance(node, str):
            if marker in node:
                hits.append(prefix)
        elif isinstance(node, dict):
            for key, item in node.items():
                walk(item, f"{prefix}.{key}" if prefix else str(key))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{prefix}[{index}]")

    walk(value, "")
    return hits


def validate_readiness_bundle(
    readiness_root: Path,
    expected_run_id: str,
    *,
    code_bindings: Mapping[str, tuple[str, Path]] | None = None,
    contract_bindings: Mapping[str, tuple[str, Path]] | None = None,
) -> dict[str, Any]:
    """Validate the immutable readiness files and their production bindings."""
    root = readiness_root.resolve()
    if root.name != expected_run_id:
        raise AssertionError("readiness run ID does not match configured root")
    manifest_path = root / "audit_manifest.json"
    lock_path = root / "readiness_lock.json"
    verification_path = root / "verification.json"
    for path in (manifest_path, lock_path, verification_path):
        if not path.is_file():
            raise AssertionError(f"readiness file missing: {path.name}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    if manifest.get("run_id") != expected_run_id or lock.get("run_id") != expected_run_id or verification.get("run_id") != expected_run_id:
        raise AssertionError("readiness run ID mismatch")
    if Path(verification.get("run_dir", "")).resolve() != root:
        raise AssertionError("readiness verification root mismatch")
    if verification.get("status") != "pass":
        raise AssertionError("readiness verification is not pass")
    if verification.get("stage_c_authorized") is not False or verification.get("confirmation_role_eligible") is not False:
        raise AssertionError("readiness is not inactive")
    for key in (
        "sealed_object_body_read_count",
        "archive_decompression_count",
        "candidate_sounding_row_count",
        "candidate_cell_row_count",
    ):
        if verification.get(key) != 0:
            raise AssertionError(f"readiness counter is nonzero: {key}")
    manifest_sha = sha256_file(manifest_path)
    if verification.get("audit_manifest_sha256") != manifest_sha:
        raise AssertionError("readiness manifest hash mismatch")
    if manifest.get("summary") != lock:
        raise AssertionError("readiness manifest and lock differ")

    template_path = root / "stage_c_authorization.template.json"
    template_record = manifest.get("outputs", {}).get(template_path.name, {})
    if not template_path.is_file():
        raise AssertionError("readiness template missing")
    template_sha = sha256_file(template_path)
    if Path(template_record.get("path", "")).resolve() != template_path:
        raise AssertionError("readiness template path mismatch")
    if template_record.get("sha256") != template_sha or template_record.get("bytes") != template_path.stat().st_size:
        raise AssertionError("readiness template output mismatch")
    for path_key, sha_key in (
        ("authorization_template_path", "authorization_template_sha256"),
        ("receipt_report_template_path", "receipt_report_template_sha256"),
        ("verifier_template_path", "verifier_template_sha256"),
    ):
        if Path(lock.get(path_key, "")).resolve() != template_path or lock.get(sha_key) != template_sha:
            raise AssertionError("readiness template binding mismatch")
        if verification.get(sha_key) != template_sha:
            raise AssertionError("readiness verification template binding mismatch")

    active_code_bindings = code_bindings or STAGE_C_PRODUCTION_CODE_BINDINGS
    code_hashes: dict[str, str] = {}
    for summary_key, (manifest_name, path) in active_code_bindings.items():
        record = manifest.get("source_code", {}).get(manifest_name, {})
        resolved = path.resolve()
        if not resolved.is_file() or Path(record.get("path", "")).resolve() != resolved:
            raise AssertionError(f"readiness code path mismatch: {manifest_name}")
        digest = sha256_file(resolved)
        if record.get("sha256") != digest or lock.get(summary_key) != digest or verification.get(summary_key) != digest:
            raise AssertionError(f"readiness code SHA mismatch: {manifest_name}")
        code_hashes[summary_key] = digest

    active_contract_bindings = contract_bindings or STAGE_C_PRODUCTION_CONTRACT_BINDINGS
    contract_hashes: dict[str, str] = {}
    for receipt_key, (filename, source) in active_contract_bindings.items():
        record = manifest.get("contracts", {}).get(filename, {})
        frozen = root / "contracts" / filename
        resolved = source.resolve()
        if not resolved.is_file() or not frozen.is_file() or Path(record.get("source_path", "")).resolve() != resolved:
            raise AssertionError(f"readiness contract path mismatch: {filename}")
        digest = sha256_file(resolved)
        if (
            record.get("sha256") != digest
            or record.get("bytes") != frozen.stat().st_size
            or sha256_file(frozen) != digest
            or lock.get(receipt_key) != digest
            or verification.get(receipt_key) != digest
        ):
            raise AssertionError(f"readiness contract SHA mismatch: {filename}")
        contract_hashes[receipt_key] = digest

    return {
        "run_id": expected_run_id,
        "root": root,
        "manifest": manifest,
        "lock": lock,
        "verification": verification,
        "manifest_sha256": manifest_sha,
        "verification_sha256": sha256_file(verification_path),
        "template_path": template_path,
        "template_sha256": template_sha,
        "code_hashes": code_hashes,
        "contract_hashes": contract_hashes,
    }


def expected_authorization_keys(template_path: Path) -> set[str]:
    template = json.loads(template_path.read_text(encoding="utf-8"))
    if not isinstance(template, dict):
        raise AssertionError("authorization template is not an object")
    authorization_template_field_classification(template_path)
    return (set(template) - AUTHORIZATION_SCAFFOLD_REMOVED) | AUTHORIZATION_ADDED_KEYS


def authorization_template_field_classification(template_path: Path) -> dict[str, frozenset[str]]:
    template = json.loads(template_path.read_text(encoding="utf-8"))
    if not isinstance(template, dict):
        raise AssertionError("authorization template is not an object")
    classification = {
        "template_fixed": AUTHORIZATION_TEMPLATE_FIXED_FIELDS,
        "readiness_evidence_filled": AUTHORIZATION_TEMPLATE_EVIDENCE_FIELDS,
        "activation_controlled": AUTHORIZATION_TEMPLATE_ACTIVATION_FIELDS,
    }
    classified: set[str] = set()
    for name, fields in classification.items():
        overlap = classified & fields
        if overlap:
            raise AssertionError(f"authorization template fields multiply classified in {name}: {sorted(overlap)}")
        classified.update(fields)
    template_fields = set(template)
    if classified != template_fields:
        missing = template_fields - classified
        stale = classified - template_fields
        raise AssertionError(
            f"authorization template classification mismatch: unclassified={sorted(missing)}, stale={sorted(stale)}"
        )
    return classification


def _readiness_output_file(readiness: Mapping[str, Any], relative_path: str) -> Path:
    path = (Path(readiness["root"]) / relative_path).resolve()
    record = readiness["manifest"].get("outputs", {}).get(relative_path, {})
    if not path.is_file() or Path(record.get("path", "")).resolve() != path:
        raise AssertionError(f"readiness output path mismatch: {relative_path}")
    if record.get("sha256") != sha256_file(path) or record.get("bytes") != path.stat().st_size:
        raise AssertionError(f"readiness output SHA mismatch: {relative_path}")
    return path


def expected_active_authorization_values(readiness: Mapping[str, Any]) -> dict[str, Any]:
    template_path = Path(readiness["template_path"])
    template = json.loads(template_path.read_text(encoding="utf-8"))
    classification = authorization_template_field_classification(template_path)
    expected = {
        field: template[field]
        for field in classification["template_fixed"]
    }

    environment_path = _readiness_output_file(readiness, "environment_lock.json")
    fixture_path = _readiness_output_file(readiness, "fixture_verification.json")
    time_fixture_path = _readiness_output_file(
        readiness, "time_contract_fixture_verification.json"
    )
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    binaries = environment["material"]["binaries"]
    environment_digest = environment["environment_digest"]
    if readiness["lock"].get("environment_digest") != environment_digest:
        raise AssertionError("readiness environment digest mismatch")
    if readiness["verification"].get("environment_digest") != environment_digest:
        raise AssertionError("readiness verification environment digest mismatch")
    if readiness["lock"].get("accepted_stage_c0_planning_lock_sha256") != STAGE_C0_PLANNING_LOCK_SHA256:
        raise AssertionError("readiness Stage C0 planning lock mismatch")
    if readiness["verification"].get("stage_c0_planning_lock_sha256") != STAGE_C0_PLANNING_LOCK_SHA256:
        raise AssertionError("readiness verification Stage C0 planning lock mismatch")
    if readiness["verification"].get("stage_c0_planning_commit") != STAGE_C0_PLANNING_COMMIT:
        raise AssertionError("readiness verification Stage C0 planning commit mismatch")

    expected.update(
        {
            "fixture_verification_sha256": sha256_file(fixture_path),
            "format58_fixture_bytes_sha256": fixture["fixture"]["sha256"],
            "format58_fixture_oracle_sha256": fixture["oracle"]["sha256"],
            "output_schema_sha256": readiness["contract_hashes"]["output_schema_sha256"],
            "parser_environment_digest": environment_digest,
            "parser_help_snapshot_sha256": {
                name: binaries[name]["version_or_help_sha256"]
                for name in ("mblist", "mbinfo", "gzip")
            },
            "qc_contract_sha256": readiness["contract_hashes"]["qc_contract_sha256"],
            "stage_c0_planning_commit": STAGE_C0_PLANNING_COMMIT,
            "stage_c0_planning_lock_sha256": STAGE_C0_PLANNING_LOCK_SHA256,
            "verification_contract_sha256": readiness["contract_hashes"]["verification_contract_sha256"],
            "verifier_sha256": readiness["code_hashes"]["stage_c_verifier_sha256"],
            "schema_version": ACTIVE_AUTHORIZATION_RECEIPT_SCHEMA_VERSION,
            "stage_c_authorized": True,
            "authorization_template_sha256": readiness["template_sha256"],
            "authorization_script_sha256": readiness["code_hashes"]["stage_c_authorizer_sha256"],
            "processor_sha256": readiness["code_hashes"]["stage_c_processor_sha256"],
            "processing_helper_sha256": readiness["code_hashes"]["stage_c_processing_helper_sha256"],
            "parser_binary_sha256": {
                name: binaries[name]["sha256"]
                for name in ("mblist", "mbinfo", "gzip")
            },
            "permitted_body_read_counts": PERMITTED_BODY_READ_COUNTS,
            "prohibited_external_inputs": PROHIBITED_EXTERNAL_INPUTS,
            "source_internal_only": True,
            "stage_c_readiness_run_id": readiness["run_id"],
            "stage_c1a_readiness_manifest_sha256": readiness["manifest_sha256"],
            "stage_c1a_readiness_verification_sha256": readiness["verification_sha256"],
            "time_fixture_verification_sha256": sha256_file(time_fixture_path),
            "gebco_or_product_comparison_authorized": False,
            "model_comparison_authorized": False,
            "mrar_merge_authorized": False,
            "cross_cruise_aggregation_authorized": False,
            "datum_or_bias_fit_authorized": False,
            "confirmation_role_promotion_authorized": False,
        }
    )
    exact_fields = expected_authorization_keys(template_path) - AUTHORIZATION_VARIABLE_ACTIVATION_FIELDS - {
        "authorization_receipt_sha256"
    }
    if set(expected) != exact_fields:
        missing = exact_fields - set(expected)
        extra = set(expected) - exact_fields
        raise AssertionError(
            f"active authorization field validation is incomplete: missing={sorted(missing)}, extra={sorted(extra)}"
        )
    return expected


def validate_authorization_receipt(receipt: dict[str, Any], template_path: Path) -> None:
    """Reject any active receipt that differs from the exact accepted schema."""
    expected = expected_authorization_keys(template_path)
    actual = set(receipt)
    missing = expected - actual
    extra = actual - expected
    if missing:
        raise AssertionError(f"authorization receipt missing keys: {sorted(missing)}")
    if extra:
        raise AssertionError(f"authorization receipt has unexpected keys: {sorted(extra)}")
    leaked = find_placeholder_fields(receipt)
    if leaked:
        raise AssertionError(f"authorization receipt has placeholder fields: {leaked}")
    if receipt["authorization_template_sha256"] != sha256_file(template_path):
        raise AssertionError("authorization template SHA mismatch")
    if receipt["authorization_receipt_sha256"] != canonical_authorization_receipt_sha256(receipt):
        raise AssertionError("authorization canonical hash mismatch")


def validate_receipt_readiness_bindings(receipt: dict[str, Any], readiness: Mapping[str, Any]) -> None:
    """Require an active receipt to use exactly the readiness-frozen files."""
    validate_authorization_receipt(receipt, Path(readiness["template_path"]))
    if (
        receipt["stage_c_authorized"] is not True
        or not isinstance(receipt["authorized_by"], str)
        or not receipt["authorized_by"].strip()
    ):
        raise AssertionError("authorization receipt is not active")
    if not isinstance(receipt["authorized_utc"], str):
        raise AssertionError("authorization UTC is not a string")
    try:
        authorized_utc = datetime.fromisoformat(receipt["authorized_utc"].replace("Z", "+00:00"))
    except ValueError as error:
        raise AssertionError("authorization UTC is invalid") from error
    if authorized_utc.tzinfo is None or authorized_utc.utcoffset() != timedelta(0):
        raise AssertionError("authorization UTC must have a UTC offset")
    if not isinstance(receipt["processing_run_id"], str):
        raise AssertionError("authorization processing run ID is not a string")
    try:
        safe_processing_run_id(receipt["processing_run_id"])
    except ValueError as error:
        raise AssertionError("authorization processing run ID is unsafe") from error
    for key in PROHIBITED_AUTHORIZATION_FIELDS:
        if receipt[key] is not False:
            raise AssertionError(f"authorization enables prohibited action: {key}")
    if receipt["stage_c_readiness_run_id"] != readiness["run_id"]:
        raise AssertionError("authorization readiness run ID mismatch")
    for field, expected in expected_active_authorization_values(readiness).items():
        if canonical_sha256(receipt[field]) != canonical_sha256(expected):
            raise AssertionError(f"authorization receipt fixed field mismatch: {field}")



def safe_processing_run_id(value: str) -> str:
    if not RUN_ID_RE.fullmatch(value) or ".." in value or "/" in value or "\\" in value:
        raise ValueError(f"unsafe processing run ID: {value!r}")
    return value


def source_object_id(acquisition_run_id: str, relative_path: str) -> str:
    if not relative_path or Path(relative_path).is_absolute() or "\\" in relative_path:
        raise ValueError(f"invalid source object relative path: {relative_path!r}")
    parts = relative_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"noncanonical source object relative path: {relative_path!r}")
    if not RUN_ID_RE.fullmatch(acquisition_run_id):
        raise ValueError(f"invalid acquisition run ID: {acquisition_run_id!r}")
    return f"{acquisition_run_id}/{relative_path}"


def timestamp_us(epoch: Decimal) -> int:
    scaled = epoch * Decimal(1_000_000)
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise ValueError("M field has sub-microsecond precision")
    return int(integral)


def datetime_from_us(value: int) -> datetime:
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=value)


def _parse_finite(value: str, field: str, *, allow_nan: bool = False) -> float:
    try:
        parsed = float(value.strip())
    except ValueError as error:
        raise ValueError(f"{field} is not numeric: {value!r}") from error
    if allow_nan and not math.isfinite(parsed):
        return parsed
    if not math.isfinite(parsed):
        raise ValueError(f"{field} is not finite: {value!r}")
    return parsed


def iter_mblist_rows(path: Path, *, check_mode: int) -> Iterator[tuple[MblistRow, int]]:
    """Stream the exact seven-column ASCII HT/LF contract."""
    if check_mode not in {0, 3}:
        raise ValueError(f"unsupported check mode: {check_mode}")
    with path.open("r", encoding="ascii", newline="") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if "\r" in raw:
                raise ValueError(f"CR is forbidden at line {line_number}")
            if not raw.endswith("\n"):
                raise ValueError(f"missing LF terminator at line {line_number}")
            fields = raw[:-1].split("\t")
            if len(fields) != 7:
                raise ValueError(f"line {line_number} has {len(fields)} fields, expected 7")
            epoch_text = fields[0].strip()
            if not epoch_text:
                raise ValueError(f"missing M at line {line_number}")
            try:
                epoch = Decimal(epoch_text)
            except InvalidOperation as error:
                raise ValueError(f"invalid M at line {line_number}") from error
            if not epoch.is_finite() or epoch < 0:
                raise ValueError(f"invalid M at line {line_number}")
            timestamp_us(epoch)
            try:
                native_ping = int(fields[1].strip())
                beam = int(fields[2].strip())
            except ValueError as error:
                raise ValueError(f"invalid N/# at line {line_number}") from error
            if native_ping < 0 or beam < 0:
                raise ValueError(f"negative N/# at line {line_number}")
            depth_text = fields[5].strip()
            if depth_text.lower() == "nan":
                if check_mode != 3:
                    raise ValueError(f"NaN depth in U0 at line {line_number}")
                depth = math.nan
            else:
                depth = _parse_finite(depth_text, "z")
            # Both U3 (check_mode 3) and U0 (check_mode 0) tolerate non-finite
            # X/Y: a non-finite navigation value demotes that single sounding at
            # per-sounding QC (H03) rather than aborting the whole object. The M
            # (time) and z (depth, for U0) parses stay strict below.
            allow_nonfinite_xy = check_mode in (0, 3)
            lon = _parse_finite(fields[3], "X", allow_nan=allow_nonfinite_xy)
            lat = _parse_finite(fields[4], "Y", allow_nan=allow_nonfinite_xy)
            heading = _parse_finite(fields[6], "H")
            yield (
                MblistRow(
                    epoch_seconds_utc=epoch,
                    native_ping_counter=native_ping,
                    beam_index=beam,
                    lon_deg=lon,
                    lat_deg=lat,
                    parser_depth_value=depth,
                    heading_deg=heading,
                ),
                timestamp_us(epoch),
            )


def scan_time_contract(path: Path, *, check_mode: int) -> tuple[int, str | None, str | None]:
    count = 0
    try:
        for _row, _time in iter_mblist_rows(path, check_mode=check_mode):
            count += 1
    except ValueError as error:
        message = str(error)
        if "missing M" in message:
            return count, "TIME_UTC_MISSING", message
        if "invalid M" in message or "sub-microsecond" in message:
            return count, "TIME_UTC_INVALID", message
        return count, "PARSER_CONTRACT_FAILURE", message
    return count, None, None


class ParquetAppender:
    def __init__(self, path: Path, schema: pa.Schema) -> None:
        self.path = path
        self.schema = schema
        self.writer: pq.ParquetWriter | None = None
        self.row_count = 0

    def append(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        table = pa.Table.from_pylist(rows, schema=self.schema)
        if self.writer is None:
            self.writer = pq.ParquetWriter(self.path, self.schema, compression="zstd")
        self.writer.write_table(table)
        self.row_count += len(rows)

    def append_table(self, table: pa.Table | pa.RecordBatch) -> None:
        if isinstance(table, pa.RecordBatch):
            table = pa.Table.from_batches([table], schema=self.schema)
        if table.schema != self.schema:
            table = table.cast(self.schema)
        if self.writer is None:
            self.writer = pq.ParquetWriter(self.path, self.schema, compression="zstd")
        self.writer.write_table(table)
        self.row_count += table.num_rows

    def close(self) -> None:
        if self.writer is None:
            pq.write_table(pa.Table.from_pylist([], schema=self.schema), self.path, compression="zstd")
        else:
            self.writer.close()


def arrow_type(type_name: str) -> pa.DataType:
    if type_name == "string":
        return pa.string()
    if type_name == "int64":
        return pa.int64()
    if type_name == "int32":
        return pa.int32()
    if type_name == "float64":
        return pa.float64()
    if type_name == "bool":
        return pa.bool_()
    if type_name == "list_string":
        return pa.list_(pa.string())
    if type_name == "timestamp_us_UTC":
        return pa.timestamp("us", tz="UTC")
    raise ValueError(f"unsupported output schema type: {type_name}")


def load_output_schemas(schema_path: Path) -> dict[str, pa.Schema]:
    spec = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    output: dict[str, pa.Schema] = {}
    for table_name, table_spec in spec["tables"].items():
        output[table_name] = pa.schema(
            [
                pa.field(field["name"], arrow_type(field["type"]), nullable=bool(field["nullable"]))
                for field in table_spec["fields"]
            ]
        )
    return output


def nmad(values: list[float]) -> float | None:
    if not values:
        return None
    median = statistics.median(values)
    return float(1.4826 * statistics.median([abs(value - median) for value in values]))


def quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(np.quantile(np.asarray(values, dtype=np.float64), q, method="linear"))


def haversine_m(lon_a: float, lat_a: float, lon_b: float, lat_b: float) -> float:
    radius = 6_371_000.0
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    dphi = phi_b - phi_a
    dlambda = math.radians(lon_b - lon_a)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * radius * math.asin(min(1.0, math.sqrt(a)))


@dataclass
class RawRow:
    source_object_id: str
    parser_ping_index: int
    native_ping_counter: int
    beam_index: int
    epoch_us: int
    lon_deg: float
    lat_deg: float
    u3_navigation_finite: bool
    u0_navigation_finite: bool | None
    parser_depth_value: float
    depth_m_positive_down: float | None
    heading_deg: float
    native_quality_state: str


RAW_SCHEMA = pa.schema(
    [
        ("source_object_id", pa.string()),
        ("parser_ping_index", pa.int64()),
        ("native_ping_counter", pa.int64()),
        ("beam_index", pa.int32()),
        ("epoch_us", pa.int64()),
        ("lon_deg", pa.float64()),
        ("lat_deg", pa.float64()),
        ("u3_navigation_finite", pa.bool_()),
        ("u0_navigation_finite", pa.bool_()),
        ("parser_depth_value", pa.float64()),
        ("depth_m_positive_down", pa.float64()),
        ("heading_deg", pa.float64()),
        ("native_quality_state", pa.string()),
    ]
)


def _raw_row_dict(row: RawRow) -> dict[str, Any]:
    return {
        "source_object_id": row.source_object_id,
        "parser_ping_index": row.parser_ping_index,
        "native_ping_counter": row.native_ping_counter,
        "beam_index": row.beam_index,
        "epoch_us": row.epoch_us,
        "lon_deg": row.lon_deg,
        "lat_deg": row.lat_deg,
        "u3_navigation_finite": row.u3_navigation_finite,
        "u0_navigation_finite": row.u0_navigation_finite,
        "parser_depth_value": row.parser_depth_value,
        "depth_m_positive_down": row.depth_m_positive_down,
        "heading_deg": row.heading_deg,
        "native_quality_state": row.native_quality_state,
    }


def _u0_db(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE u0 (epoch_us INTEGER, native_ping INTEGER, beam INTEGER, lon REAL, lat REAL, depth REAL, heading REAL, PRIMARY KEY(epoch_us,native_ping,beam))"
    )
    connection.execute(
        "CREATE TABLE u3 (row_order INTEGER PRIMARY KEY, epoch_us INTEGER, native_ping INTEGER, beam INTEGER, lon REAL, lat REAL, depth REAL, depth_is_nan INTEGER NOT NULL, heading REAL)"
    )
    connection.execute("CREATE UNIQUE INDEX u3_key ON u3(epoch_us,native_ping,beam)")
    return connection


def _raw_from_object(
    source_object_id_value: str,
    u3_path: Path,
    u0_path: Path,
    sqlite_path: Path,
    raw_path: Path,
) -> tuple[int, int, str | None, str | None]:
    """Return an atomic parser-contract failure instead of leaking partial rows."""
    try:
        return _raw_from_object_impl(source_object_id_value, u3_path, u0_path, sqlite_path, raw_path)
    except ValueError as error:
        raw_path.unlink(missing_ok=True)
        sqlite_path.unlink(missing_ok=True)
        return 0, 0, "PARSER_CONTRACT_FAILURE", str(error)


def _raw_from_object_impl(
    source_object_id_value: str,
    u3_path: Path,
    u0_path: Path,
    sqlite_path: Path,
    raw_path: Path,
) -> tuple[int, int, str | None, str | None]:
    u3_count, u3_error, u3_detail = scan_time_contract(u3_path, check_mode=3)
    if u3_error:
        return 0, 0, u3_error, u3_detail
    u0_count, u0_error, u0_detail = scan_time_contract(u0_path, check_mode=0)
    if u0_error:
        return 0, 0, u0_error, u0_detail
    database = _u0_db(sqlite_path)
    try:
        insert = "INSERT INTO u0(epoch_us,native_ping,beam,lon,lat,depth,heading) VALUES (?,?,?,?,?,?,?)"
        batch: list[tuple[Any, ...]] = []
        for row, epoch_us in iter_mblist_rows(u0_path, check_mode=0):
            batch.append((epoch_us, row.native_ping_counter, row.beam_index, row.lon_deg, row.lat_deg, row.parser_depth_value, row.heading_deg))
            if len(batch) >= 50_000:
                try:
                    database.executemany(insert, batch)
                except sqlite3.IntegrityError as error:
                    raise ValueError(f"duplicate U0 key: {error}") from error
                finally:
                    batch.clear()
        if batch:
            try:
                database.executemany(insert, batch)
            except sqlite3.IntegrityError as error:
                raise ValueError(f"duplicate U0 key: {error}") from error
        database.commit()
        u3_insert = "INSERT INTO u3(row_order,epoch_us,native_ping,beam,lon,lat,depth,depth_is_nan,heading) VALUES (?,?,?,?,?,?,?,?,?)"
        ping_ordinals: dict[tuple[int, int], int] = {}
        previous_ping_index = -1
        u3_batch: list[tuple[Any, ...]] = []
        row_order = 0
        for row, epoch_us in iter_mblist_rows(u3_path, check_mode=3):
            ping_key = (epoch_us, row.native_ping_counter)
            parser_ping_index = ping_ordinals.setdefault(ping_key, len(ping_ordinals))
            if parser_ping_index < previous_ping_index:
                raise ValueError("U3 parser ping order regressed")
            previous_ping_index = parser_ping_index
            u3_batch.append(
                (
                    row_order,
                    epoch_us,
                    row.native_ping_counter,
                    row.beam_index,
                    row.lon_deg,
                    row.lat_deg,
                    None if math.isnan(row.parser_depth_value) else row.parser_depth_value,
                    int(math.isnan(row.parser_depth_value)),
                    row.heading_deg,
                )
            )
            row_order += 1
            if len(u3_batch) >= 50_000:
                try:
                    database.executemany(u3_insert, u3_batch)
                except sqlite3.IntegrityError as error:
                    raise ValueError(f"duplicate U3 key: {error}") from error
                finally:
                    u3_batch.clear()
        if u3_batch:
            try:
                database.executemany(u3_insert, u3_batch)
            except sqlite3.IntegrityError as error:
                raise ValueError(f"duplicate U3 key: {error}") from error
        database.commit()
        missing_u0 = database.execute(
            "SELECT COUNT(*) FROM u0 LEFT JOIN u3 ON u0.epoch_us=u3.epoch_us AND u0.native_ping=u3.native_ping AND u0.beam=u3.beam WHERE u3.row_order IS NULL"
        ).fetchone()[0]
        if missing_u0:
            raise ValueError(f"U0 keys absent from U3: {missing_u0}")
        appender = ParquetAppender(raw_path, RAW_SCHEMA)
        row_batch: list[dict[str, Any]] = []
        joined = database.execute(
            "SELECT u3.row_order,u3.epoch_us,u3.native_ping,u3.beam,u3.lon,u3.lat,u3.depth,u3.depth_is_nan,u3.heading,u0.lon,u0.lat,u0.depth,u0.heading,u0.rowid AS u0_rowid FROM u3 LEFT JOIN u0 ON u0.epoch_us=u3.epoch_us AND u0.native_ping=u3.native_ping AND u0.beam=u3.beam ORDER BY u3.row_order"
        )
        seen_u0 = 0
        for (
            _row_order,
            epoch_us,
            native_ping,
            beam,
            lon,
            lat,
            parser_depth,
            depth_is_nan,
            heading,
            good_lon,
            good_lat,
            good_depth,
            good_heading,
            u0_rowid,
        ) in joined:
            u3_lon = None if lon is None else float(lon)
            u3_lat = None if lat is None else float(lat)
            u3_nav_ok = u3_lon is not None and math.isfinite(u3_lon) and u3_lat is not None and math.isfinite(u3_lat)
            u0_nav_ok: bool | None = None
            # Branch on key presence, not on good_lon: a U0 row with non-finite
            # navigation is stored with NULL lon/lat in the REAL column, so
            # good_lon is None both for a missing key and for a present key whose
            # nav is NaN. u0_rowid distinguishes the two (NULL only when the key
            # is truly absent from u0).
            if u0_rowid is None:
                quality = "null" if depth_is_nan else "flagged"
                depth = None
            else:
                # Key present: native_quality_state stays "good" even when the
                # U0 or U3 navigation is non-finite (requirement 2). A
                # non-finite navigation is surfaced only as H03 at per-sounding
                # QC, never as a native-quality demotion here.
                u0_lon = None if good_lon is None else float(good_lon)
                u0_lat = None if good_lat is None else float(good_lat)
                u0_nav_ok = u0_lon is not None and math.isfinite(u0_lon) and u0_lat is not None and math.isfinite(u0_lat)
                if any(
                    left is not None and right is not None and abs(left - right) > tolerance
                    for left, right, tolerance in (
                        (u3_lon if u3_nav_ok else None, u0_lon if u0_nav_ok else None, 1.0e-10),
                        (u3_lat if u3_nav_ok else None, u0_lat if u0_nav_ok else None, 1.0e-10),
                        (float(parser_depth), float(good_depth), 1.0e-4),
                        (float(heading), float(good_heading), 1.0e-3),
                    )
                ):
                    raise ValueError(f"U0/U3 value mismatch for key {(epoch_us, native_ping, beam)}")
                seen_u0 += 1
                quality = "good"
                depth = float(good_depth)
            row_batch.append(
                _raw_row_dict(
                    RawRow(
                        source_object_id=source_object_id_value,
                        parser_ping_index=ping_ordinals[(int(epoch_us), int(native_ping))],
                        native_ping_counter=int(native_ping),
                        beam_index=int(beam),
                        epoch_us=int(epoch_us),
                        lon_deg=normalize_longitude(u3_lon) if u3_nav_ok else math.nan,
                        lat_deg=u3_lat if u3_nav_ok else math.nan,
                        u3_navigation_finite=u3_nav_ok,
                        u0_navigation_finite=u0_nav_ok,
                        parser_depth_value=math.nan if depth_is_nan else float(parser_depth),
                        depth_m_positive_down=depth,
                        heading_deg=float(heading),
                        native_quality_state=quality,
                    )
                )
            )
            if len(row_batch) >= 50_000:
                appender.append(row_batch)
                row_batch.clear()
        if row_batch:
            appender.append(row_batch)
        database.commit()
        appender.close()
        if seen_u0 != u0_count:
            raise ValueError(f"U0 join count mismatch: expected {u0_count}, got {seen_u0}")
        return u3_count, seen_u0, None, None
    finally:
        database.close()


def ping_review_codes(raw_path: Path) -> dict[int, set[str]]:
    """Compute frozen review rules from one raw object's ordered rows."""
    ping_stats: list[dict[str, Any]] = []
    current_index: int | None = None
    current_rows: list[dict[str, Any]] = []
    reader = pq.ParquetFile(raw_path)
    for batch in reader.iter_batches(batch_size=50_000):
        for row in batch.to_pylist():
            index = int(row["parser_ping_index"])
            if current_index is None:
                current_index = index
            if index != current_index:
                ping_stats.append(_finish_ping(current_index, current_rows))
                current_rows = []
                current_index = index
            current_rows.append(row)
    if current_index is not None:
        ping_stats.append(_finish_ping(current_index, current_rows))
    codes: dict[int, set[str]] = defaultdict(set)
    for previous, current in zip(ping_stats, ping_stats[1:]):
        if current["epoch_us"] < previous["epoch_us"]:
            codes[current["parser_ping_index"]].add("R02_time_nonmonotonic")
        dt = (current["epoch_us"] - previous["epoch_us"]) / 1_000_000.0
        if dt > 0 and haversine_m(previous["lon_deg"], previous["lat_deg"], current["lon_deg"], current["lat_deg"]) / dt > 20.0:
            codes[current["parser_ping_index"]].add("R03_navigation_speed")
    for index, current in enumerate(ping_stats):
        context = [item for item in ping_stats[max(0, index - 5):index] + ping_stats[index + 1:index + 6] if item["median_depth"] is not None]
        if len(context) >= 3 and current["median_depth"] is not None:
            context_values = [item["median_depth"] for item in context]
            context_median = statistics.median(context_values)
            context_nmad = nmad(context_values) or 0.0
            if abs(current["median_depth"] - context_median) > max(1000.0, 10.0 * max(context_nmad, 1.0)):
                codes[current["parser_ping_index"]].add("R05_alongtrack_ping_median_discontinuity")
    return codes


def _finish_ping(index: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible_depths = [
        float(row["depth_m_positive_down"])
        for row in rows
        if row["native_quality_state"] == "good"
        and row["depth_m_positive_down"] is not None
        and math.isfinite(float(row["depth_m_positive_down"]))
        and 0.0 < float(row["depth_m_positive_down"]) <= 12_000.0
    ]
    return {
        "parser_ping_index": index,
        "epoch_us": int(rows[0]["epoch_us"]),
        "lon_deg": float(rows[0]["lon_deg"]),
        "lat_deg": float(rows[0]["lat_deg"]),
        "median_depth": statistics.median(eligible_depths) if eligible_depths else None,
        "nmad": nmad(eligible_depths),
    }


def source_field_ledger(
    official_cruise_id: str,
    object_id: str,
    relative_path: str,
    object_sha256: str,
    command_sha256: str,
    *,
    parsed: bool,
    time_failure: bool = False,
    parser_failure: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    direct_fields = {"time_utc", "longitude", "latitude", "heading", "native_quality", "depth", "native_ping_id", "native_beam_id"}
    parser_available = {"time_utc", "longitude", "latitude", "heading", "native_quality", "depth"}
    for field_name in FIELD_NAMES:
        available = bool(parsed and field_name in parser_available)
        if time_failure and field_name == "time_utc":
            status = "known"
            evidence_kind = "parser_preflight_failure"
            note = "M field missing or invalid; source object aborted atomically"
            available = False
        elif parser_failure:
            status = "officially_unknown"
            evidence_kind = "parser_contract_failure"
            note = "Source object emitted no rows because the frozen parser contract failed"
        elif available:
            status = "known"
            evidence_kind = "decoded_format58_parser_field"
            note = None
        else:
            status = "officially_unknown"
            evidence_kind = "not_recovered_under_initial_contract"
            note = "No direct evidence read under the initial source-internal contract"
        rows.append(
            {
                "official_cruise_id": official_cruise_id,
                "source_object_id": object_id,
                "source_object_relative_path": relative_path,
                "source_object_sha256": object_sha256,
                "field_name": field_name,
                "field_available": available,
                "field_status": status,
                "evidence_kind": evidence_kind,
                "evidence_path_or_command_sha256": command_sha256 if parsed or time_failure else object_sha256,
                "note": note,
            }
        )
    return rows


def source_processing_row(
    processing_run_id: str,
    acquisition_run_id: str,
    object_record: dict[str, Any],
    object_id: str,
    *,
    body_read_authorized: bool,
    body_read_performed: bool,
    parser_name: str | None,
    parser_version: str | None,
    parser_source_commit: str | None,
    parser_environment_digest: str | None,
    command_sha256: str | None,
    decompressed_sha256: str | None,
    parse_status: str,
    parsed_row_count: int,
    error_code: str | None,
    error_detail: str | None,
) -> dict[str, Any]:
    return {
        "processing_run_id": processing_run_id,
        "acquisition_run_id": acquisition_run_id,
        "source_object_id": object_id,
        "source_object_identity_basis": "acquisition_run_id + '/' + canonical_source_object_relative_path",
        "official_cruise_id": str(object_record["official_cruise_id"]),
        "official_cruise_id_status": "verified_from_source_metadata",
        "source_object_relative_path": str(object_record["relative_path"]),
        "source_object_filename": str(object_record["filename"]),
        "source_object_role": str(object_record["source_object_role"]),
        "source_object_format": str(object_record["format"]),
        "source_object_bytes": int(object_record["bytes"]),
        "source_object_sha256": str(object_record["sha256"]),
        "body_read_authorized": body_read_authorized,
        "body_read_performed": body_read_performed,
        "parser_name": parser_name,
        "parser_version": parser_version,
        "parser_source_commit": parser_source_commit,
        "parser_environment_digest": parser_environment_digest,
        "command_sha256": command_sha256,
        "decompressed_derivative_sha256": decompressed_sha256,
        "parse_status": parse_status,
        "parsed_row_count": int(parsed_row_count),
        "error_code": error_code,
        "error_detail": error_detail,
    }


def sounding_row(
    raw: dict[str, Any],
    processing_run_id: str,
    acquisition_run_id: str,
    object_record: dict[str, Any],
    parser_environment_digest: str,
    parser_command_sha256: str,
    review_codes: set[str],
) -> dict[str, Any]:
    depth = raw["depth_m_positive_down"]
    lon = float(raw["lon_deg"])
    lat = float(raw["lat_deg"])
    native_good = raw["native_quality_state"] == "good"
    depth_ok = depth is not None and math.isfinite(float(depth)) and 0.0 < float(depth) <= 12_000.0
    u0_navigation_finite = raw["u0_navigation_finite"]
    navigation_sources_finite = bool(raw["u3_navigation_finite"]) and (
        u0_navigation_finite is None or bool(u0_navigation_finite)
    )
    nav_ok = navigation_sources_finite and math.isfinite(lon) and -180.0 <= lon < 180.0 and math.isfinite(lat) and -90.0 <= lat <= 90.0
    failure_codes: list[str] = []
    if not native_good:
        failure_codes.append("H02_NATIVE_NOT_GOOD")
    if not nav_ok:
        failure_codes.append("H03_NAVIGATION_RANGE")
    if not depth_ok:
        failure_codes.append("H04_DEPTH_RANGE")
    hard_pass = not failure_codes
    if nav_ok:
        lon_bin, lat_bin, cell_id = cell_assignment(lon, lat)
    else:
        lon_bin = lat_bin = cell_id = None
    epoch = datetime_from_us(int(raw["epoch_us"]))
    status_known = "known"
    return {
        "processing_run_id": processing_run_id,
        "acquisition_run_id": acquisition_run_id,
        "source_object_id": str(raw["source_object_id"]),
        "source_object_relative_path": str(object_record["relative_path"]),
        "source_object_sha256": str(object_record["sha256"]),
        "official_cruise_id": str(object_record["official_cruise_id"]),
        "official_cruise_id_status": "verified_from_source_metadata",
        "parser_name": "MB-System",
        "parser_version": "5.8.3beta16",
        "parser_source_commit": "1d9a52ce076c3c3c5f0150b9bcaa30fa108c7422",
        "parser_environment_digest": parser_environment_digest,
        "parser_command_sha256": parser_command_sha256,
        "parser_ping_index": int(raw["parser_ping_index"]),
        "parser_ping_index_status": status_known,
        "native_ping_counter": int(raw["native_ping_counter"]),
        "native_ping_counter_status": status_known,
        "native_ping_id": None,
        "native_ping_id_status": "officially_unknown",
        "beam_index": int(raw["beam_index"]),
        "beam_index_status": status_known,
        "native_beam_id": None,
        "native_beam_id_status": "officially_unknown",
        "line_id": None,
        "line_id_status": "officially_unknown",
        "time_utc": epoch,
        "time_utc_status": "known",
        "lon_deg": lon,
        "lon_deg_status": status_known,
        "lat_deg": lat,
        "lat_deg_status": status_known,
        "u3_navigation_finite": bool(raw["u3_navigation_finite"]),
        "u0_navigation_finite": (
            None if u0_navigation_finite is None else bool(u0_navigation_finite)
        ),
        "navigation_valid": nav_ok,
        "horizontal_datum": None,
        "horizontal_datum_status": "officially_unknown",
        "parser_depth_value": float(raw["parser_depth_value"]),
        "depth_m_positive_down": float(depth) if depth is not None else None,
        "depth_m_positive_down_status": status_known,
        "elev_m": -float(depth) if depth is not None else None,
        "depth_unit": "m",
        "depth_direction": "positive_down",
        "vertical_datum": None,
        "vertical_datum_status": "officially_unknown",
        "heading_deg": float(raw["heading_deg"]),
        "heading_deg_status": status_known,
        "native_quality_state": str(raw["native_quality_state"]),
        "native_quality_state_status": status_known,
        "native_quality_code": None,
        "native_quality_code_status": "officially_unknown",
        "qc_hard_pass": hard_pass,
        "qc_hard_failure_codes": failure_codes,
        "qc_review_codes": sorted(review_codes),
        "qc_eligible_for_cell": hard_pass,
        "lon_bin": lon_bin,
        "lat_bin": lat_bin,
        "cell_id": cell_id,
        "held_out": True,
        "use_for_training": False,
        "use_for_tuning": False,
        "use_for_threshold_selection": False,
        "role_v2_h": "held_out_candidate_mrar_out",
        "role_v2_w": "blocked_source_independence_unknown",
        "confirmation_role_eligible": False,
    }


def sounding_batch_table(
    raw_batch: pa.RecordBatch,
    processing_run_id: str,
    acquisition_run_id: str,
    object_record: dict[str, Any],
    parser_environment_digest: str,
    parser_command_sha256: str,
    review_codes: dict[int, set[str]],
    schema: pa.Schema,
) -> pa.Table:
    """Build one lineage batch with column operations and no per-row dictionaries."""
    raw = raw_batch.to_pydict()
    count = len(raw["parser_ping_index"])
    object_id = str(raw["source_object_id"][0]) if count else ""
    relative = str(object_record["relative_path"])
    cruise = str(object_record["official_cruise_id"])
    lon_values = [float(value) for value in raw["lon_deg"]]
    lat_values = [float(value) for value in raw["lat_deg"]]
    depth_values = [
        None if value is None or math.isnan(float(value)) else float(value)
        for value in raw["depth_m_positive_down"]
    ]
    quality_values = [str(value) for value in raw["native_quality_state"]]
    navigation_sources_finite = [
        bool(u3_finite) and (u0_finite is None or bool(u0_finite))
        for u3_finite, u0_finite in zip(
            raw["u3_navigation_finite"], raw["u0_navigation_finite"]
        )
    ]
    nav_values = [
        sources_finite
        and math.isfinite(lon)
        and -180.0 <= lon < 180.0
        and math.isfinite(lat)
        and -90.0 <= lat <= 90.0
        for lon, lat, sources_finite in zip(lon_values, lat_values, navigation_sources_finite)
    ]
    depth_ok_values = [
        value is not None and math.isfinite(value) and 0.0 < value <= 12_000.0
        for value in depth_values
    ]
    hard_values = [quality == "good" and nav_ok and depth_ok for quality, nav_ok, depth_ok in zip(quality_values, nav_values, depth_ok_values)]
    cell_values: list[str | None] = []
    lon_bins: list[int | None] = []
    lat_bins: list[int | None] = []
    for lon, lat, nav_ok in zip(lon_values, lat_values, nav_values):
        if nav_ok:
            lon_bin, lat_bin, cell_id = cell_assignment(lon, lat)
            lon_bins.append(lon_bin)
            lat_bins.append(lat_bin)
            cell_values.append(cell_id)
        else:
            lon_bins.append(None)
            lat_bins.append(None)
            cell_values.append(None)
    times = [datetime_from_us(int(value)) for value in raw["epoch_us"]]
    review_values = [sorted(review_codes.get(int(value), set())) for value in raw["parser_ping_index"]]
    failure_values: list[list[str]] = []
    for quality, nav_ok, depth_ok in zip(quality_values, nav_values, depth_ok_values):
        codes: list[str] = []
        if quality != "good":
            codes.append("H02_NATIVE_NOT_GOOD")
        if not nav_ok:
            codes.append("H03_NAVIGATION_RANGE")
        if not depth_ok:
            codes.append("H04_DEPTH_RANGE")
        failure_values.append(codes)
    parser_depth_values = [float(value) for value in raw["parser_depth_value"]]
    data: dict[str, Any] = {
        "processing_run_id": [processing_run_id] * count,
        "acquisition_run_id": [acquisition_run_id] * count,
        "source_object_id": [object_id] * count,
        "source_object_relative_path": [relative] * count,
        "source_object_sha256": [str(object_record["sha256"])] * count,
        "official_cruise_id": [cruise] * count,
        "official_cruise_id_status": ["verified_from_source_metadata"] * count,
        "parser_name": ["MB-System"] * count,
        "parser_version": ["5.8.3beta16"] * count,
        "parser_source_commit": ["1d9a52ce076c3c3c5f0150b9bcaa30fa108c7422"] * count,
        "parser_environment_digest": [parser_environment_digest] * count,
        "parser_command_sha256": [parser_command_sha256] * count,
        "parser_ping_index": [int(value) for value in raw["parser_ping_index"]],
        "parser_ping_index_status": ["known"] * count,
        "native_ping_counter": [int(value) for value in raw["native_ping_counter"]],
        "native_ping_counter_status": ["known"] * count,
        "native_ping_id": [None] * count,
        "native_ping_id_status": ["officially_unknown"] * count,
        "beam_index": [int(value) for value in raw["beam_index"]],
        "beam_index_status": ["known"] * count,
        "native_beam_id": [None] * count,
        "native_beam_id_status": ["officially_unknown"] * count,
        "line_id": [None] * count,
        "line_id_status": ["officially_unknown"] * count,
        "time_utc": times,
        "time_utc_status": ["known"] * count,
        "lon_deg": lon_values,
        "lon_deg_status": ["known"] * count,
        "lat_deg": lat_values,
        "lat_deg_status": ["known"] * count,
        "u3_navigation_finite": [bool(value) for value in raw["u3_navigation_finite"]],
        "u0_navigation_finite": [
            None if value is None else bool(value)
            for value in raw["u0_navigation_finite"]
        ],
        "navigation_valid": nav_values,
        "horizontal_datum": [None] * count,
        "horizontal_datum_status": ["officially_unknown"] * count,
        "parser_depth_value": parser_depth_values,
        "depth_m_positive_down": depth_values,
        "depth_m_positive_down_status": ["known"] * count,
        "elev_m": [None if value is None else -value for value in depth_values],
        "depth_unit": ["m"] * count,
        "depth_direction": ["positive_down"] * count,
        "vertical_datum": [None] * count,
        "vertical_datum_status": ["officially_unknown"] * count,
        "heading_deg": [float(value) for value in raw["heading_deg"]],
        "heading_deg_status": ["known"] * count,
        "native_quality_state": quality_values,
        "native_quality_state_status": ["known"] * count,
        "native_quality_code": [None] * count,
        "native_quality_code_status": ["officially_unknown"] * count,
        "qc_hard_pass": hard_values,
        "qc_hard_failure_codes": failure_values,
        "qc_review_codes": review_values,
        "qc_eligible_for_cell": hard_values,
        "lon_bin": lon_bins,
        "lat_bin": lat_bins,
        "cell_id": cell_values,
        "held_out": [True] * count,
        "use_for_training": [False] * count,
        "use_for_tuning": [False] * count,
        "use_for_threshold_selection": [False] * count,
        "role_v2_h": ["held_out_candidate_mrar_out"] * count,
        "role_v2_w": ["blocked_source_independence_unknown"] * count,
        "confirmation_role_eligible": [False] * count,
    }
    return pa.Table.from_pydict(data, schema=schema)


def aggregate_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {
            "median": None,
            "mean": None,
            "nmad": None,
            "q25": None,
            "q75": None,
            "min": None,
            "max": None,
            "range": None,
        }
    return {
        "median": float(statistics.median(values)),
        "mean": float(statistics.fmean(values)),
        "nmad": nmad(values),
        "q25": quantile(values, 0.25),
        "q75": quantile(values, 0.75),
        "min": float(min(values)),
        "max": float(max(values)),
        "range": float(max(values) - min(values)),
    }


def query_depths(connection: sqlite3.Connection, cell_id: str, cruise_id: str, object_id: str | None = None) -> list[float]:
    if object_id is None:
        rows = connection.execute(
            "SELECT depth FROM eligible WHERE cell_id=? AND cruise_id=? ORDER BY depth",
            (cell_id, cruise_id),
        )
    else:
        rows = connection.execute(
            "SELECT depth FROM eligible WHERE cell_id=? AND cruise_id=? AND source_object_id=? ORDER BY depth",
            (cell_id, cruise_id, object_id),
        )
    return [float(row[0]) for row in rows]
