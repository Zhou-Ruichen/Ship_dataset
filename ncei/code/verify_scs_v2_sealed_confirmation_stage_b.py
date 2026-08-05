#!/usr/bin/env python3
"""Independently verify an opaque SCS v2 Stage B acquisition.

This verifier treats every downloaded object as opaque bytes. It never opens an
archive or imports a sounding, sonar, navigation, or depth parser.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
PRIMARY_IDS = ["EQT20210702", "EQT190012", "EQT180002", "TN352"]
EXPECTED_OBJECT_COUNT = 768
EXPECTED_TOTAL_BYTES = 9_626_893_507
DOWNLOAD_CAP_BYTES = 12 * 1024**3
OFFICIAL_OBJECT_HOST = "data.ngdc.noaa.gov"
STAGE_B_OUTPUT_ROOT = (REPO_ROOT / "ncei/archive/scs_v2_sealed_confirmation").resolve()
DOWNLOADER_PATH = (REPO_ROOT / "ncei/code/acquire_scs_v2_sealed_confirmation_stage_b.py").resolve()
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
REQUIRED_MANIFEST_COLUMNS = [
    "official_cruise_id",
    "filename",
    "source_object_role",
    "format",
    "sealed_role",
    "original_url",
    "resolved_url",
    "relative_path",
    "bytes",
    "sha256",
    "expected_last_modified",
    "response_last_modified",
    "etag",
    "http_status",
    "downloaded_utc",
    "content_parsed",
]
FORBIDDEN_IMPORT_ROOTS = {
    "h5py",
    "libarchive",
    "netCDF4",
    "py7zr",
    "rarfile",
    "tarfile",
    "xarray",
    "zipfile",
}
FORBIDDEN_CALL_TOKENS = {
    "7z",
    "bs2asc",
    "dump",
    "extract",
    "gdal",
    "mbcopy",
    "mbdump",
    "mblist",
    "ncdump",
    "parse_depth",
    "read_depth",
    "unpack",
    "unrar",
    "unzip",
}


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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_run_id(value: str) -> str:
    if (
        not value
        or not RUN_ID_RE.fullmatch(value)
        or value in {".", ".."}
        or ".." in value
        or "/" in value
        or "\\" in value
        or Path(value).is_absolute()
    ):
        raise AssertionError("unsafe Stage B acquisition run ID")
    return value


def normalized_url(value: str) -> tuple[str, str, int | None, str, str]:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != OFFICIAL_OBJECT_HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or not parsed.path.startswith("/")
        or parsed.path.endswith("/")
        or parsed.fragment
    ):
        raise AssertionError(f"invalid official object URL: {value}")
    return parsed.scheme, parsed.hostname, parsed.port, parsed.path, parsed.query


def validate_relative_path(value: str, cruise_id: str) -> PurePosixPath:
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.parts[:2] != ("objects", cruise_id)
        or len(relative.parts) < 3
    ):
        raise AssertionError(f"object path escapes cruise directory: {value}")
    return relative


def assert_no_parser_logic(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)
    bad_imports = sorted(imports & FORBIDDEN_IMPORT_ROOTS)
    bad_calls = sorted(name for name in called_names if name.lower() in FORBIDDEN_CALL_TOKENS)
    if bad_imports or bad_calls:
        raise AssertionError(f"archive/sonar/depth parser guard failed for {path}: imports={bad_imports}, calls={bad_calls}")
    return {"path": str(path), "sha256": sha256_file(path), "forbidden_imports": 0, "forbidden_calls": 0}


def verify_downloaded_objects(frame: pd.DataFrame, acquisition_dir: Path) -> dict[str, Any]:
    if frame.columns.tolist() != REQUIRED_MANIFEST_COLUMNS:
        raise AssertionError("sealed manifest schema/order mismatch")
    if frame["relative_path"].duplicated().any() or frame["original_url"].duplicated().any():
        raise AssertionError("sealed manifest contains duplicate URL or path")
    if frame["sealed_role"].ne("sealed_unprocessed").any():
        raise AssertionError("sealed manifest role exceeds or differs from sealed_unprocessed")
    if frame["content_parsed"].astype(bool).any():
        raise AssertionError("sealed manifest claims parsed content")
    if frame["http_status"].astype(int).map(lambda value: value < 200 or value >= 300).any():
        raise AssertionError("sealed manifest contains non-success HTTP status")

    object_paths: set[str] = set()
    total_bytes = 0
    for row in frame.itertuples(index=False):
        cruise_id = str(row.official_cruise_id)
        relative = validate_relative_path(str(row.relative_path), cruise_id)
        if str(relative.name) != str(row.filename):
            raise AssertionError(f"manifest filename/path mismatch: {relative}")
        if normalized_url(str(row.original_url)) != normalized_url(str(row.resolved_url)):
            raise AssertionError(f"resolved URL differs from locked object: {row.original_url}")
        if not str(row.expected_last_modified) or str(row.response_last_modified) != str(row.expected_last_modified):
            raise AssertionError(f"Last-Modified closure failed: {row.original_url}")
        path = acquisition_dir / Path(*relative.parts)
        if not path.is_file():
            raise AssertionError(f"sealed object is missing: {path}")
        expected_bytes = int(row.bytes)
        if path.stat().st_size != expected_bytes:
            raise AssertionError(f"sealed object byte mismatch: {path}")
        if sha256_file(path) != str(row.sha256):
            raise AssertionError(f"sealed object SHA256 mismatch: {path}")
        if path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            raise AssertionError(f"sealed object remains writable: {path}")
        object_paths.add(relative.as_posix())
        total_bytes += expected_bytes
    return {"object_count": len(frame), "total_bytes": total_bytes, "relative_paths": object_paths}


def verify_stage_b(acquisition_dir: Path) -> dict[str, Any]:
    acquisition_dir = acquisition_dir.resolve()
    run_id = validate_run_id(acquisition_dir.name)
    if acquisition_dir.parent != STAGE_B_OUTPUT_ROOT:
        raise AssertionError(f"Stage B run is outside fixed output root: {acquisition_dir}")
    verification_path = acquisition_dir / "verification.json"
    if verification_path.exists():
        raise FileExistsError(f"immutable verification already exists: {verification_path}")
    if (acquisition_dir / "failure_receipt.json").exists():
        raise AssertionError("failed acquisition cannot be marked sealed")

    manifest_path = acquisition_dir / "audit_manifest.json"
    sealed_path = acquisition_dir / "sealed_archive_manifest.parquet"
    access_path = acquisition_dir / "access_lock.json"
    authorization_path = acquisition_dir / "authorization_receipt.json"
    for path in (manifest_path, sealed_path, access_path, authorization_path):
        if not path.is_file():
            raise AssertionError(f"required Stage B artifact missing: {path}")

    audit = json.loads(manifest_path.read_text(encoding="utf-8"))
    access = json.loads(access_path.read_text(encoding="utf-8"))
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    sealed = pd.read_parquet(sealed_path)
    if audit.get("stage") != "B_opaque_sealed_acquisition_pending_verification":
        raise AssertionError("unexpected Stage B audit stage")
    if audit.get("run_id") != run_id or authorization.get("acquisition_run_id") != run_id:
        raise AssertionError("acquisition run ID closure failed")
    if authorization.get("fixed_output_root") != str(STAGE_B_OUTPUT_ROOT):
        raise AssertionError("authorization output-root closure failed")
    if authorization.get("stage_b_authorized") is not True:
        raise AssertionError("Stage B authorization is absent")
    if authorization.get("immutable_primary_confirmation_cruise_ids") != PRIMARY_IDS:
        raise AssertionError("authorization primary ID order changed")
    if authorization.get("aggregate_download_cap_bytes") != DOWNLOAD_CAP_BYTES:
        raise AssertionError("authorization download cap changed")
    expected_authorization_keys = {
        "schema_version", "stage_b_authorized", "a2_run_id",
        "a2_manifest_sha256", "a2_verification_sha256",
        "a2_final_download_lock_sha256", "primary_physical_object_lock_sha256",
        "immutable_primary_confirmation_cruise_ids", "aggregate_download_cap_bytes",
        "acquisition_run_id", "fixed_output_root", "stage_b_downloader_sha256",
        "stage_b_verifier_sha256", "authorized_by", "authorized_utc",
    }
    if set(authorization) != expected_authorization_keys:
        raise AssertionError("authorization receipt schema changed")
    if not str(authorization["authorized_by"]).strip() or not str(authorization["authorized_utc"]).strip():
        raise AssertionError("authorization author/time is missing")
    if audit.get("authorization") != authorization:
        raise AssertionError("authorization receipt differs from embedded audit contract")

    a2 = audit["a2_run"]
    a2_dir = Path(a2["path"]).resolve()
    a2_manifest_path = a2_dir / "audit_manifest.json"
    a2_verification_path = a2_dir / "verification.json"
    a2_lock_path = a2_dir / "final_download_lock.json"
    if not a2.get("manifest_sha256") or sha256_file(a2_manifest_path) != a2["manifest_sha256"]:
        raise AssertionError("accepted A.2 manifest SHA256 changed")
    if not a2.get("verification_sha256") or sha256_file(a2_verification_path) != a2["verification_sha256"]:
        raise AssertionError("accepted A.2 verification SHA256 changed")
    if not a2.get("final_download_lock_sha256") or sha256_file(a2_lock_path) != a2["final_download_lock_sha256"]:
        raise AssertionError("accepted A.2 final-lock SHA256 changed")
    authorization_hash_fields = {
        "a2_manifest_sha256": a2["manifest_sha256"],
        "a2_verification_sha256": a2["verification_sha256"],
        "a2_final_download_lock_sha256": a2["final_download_lock_sha256"],
        "primary_physical_object_lock_sha256": a2["primary_physical_object_lock_sha256"],
    }
    for key, value in authorization_hash_fields.items():
        if authorization.get(key) != value:
            raise AssertionError(f"authorization A.2 hash closure failed for {key}")
    a2_verification = json.loads(a2_verification_path.read_text(encoding="utf-8"))
    a2_lock = json.loads(a2_lock_path.read_text(encoding="utf-8"))
    if a2_verification.get("status") != "pass":
        raise AssertionError("accepted A.2 verification is not pass")
    if a2_lock.get("immutable_primary_confirmation_cruise_ids") != PRIMARY_IDS:
        raise AssertionError("accepted A.2 primary IDs changed")
    if a2_lock.get("run_id") != authorization.get("a2_run_id"):
        raise AssertionError("accepted A.2 run ID changed")
    if a2_lock.get("primary_physical_object_lock_sha256") != a2["primary_physical_object_lock_sha256"]:
        raise AssertionError("accepted A.2 physical-lock SHA256 changed")

    a2_manifest = json.loads(a2_manifest_path.read_text(encoding="utf-8"))
    plan_record = a2_manifest["outputs"]["stage_b_dry_run_plan"]
    plan_path = Path(plan_record["path"])
    physical_path = Path(a2_manifest["outputs"]["primary_physical_object_lock"]["path"])
    if plan_path.stat().st_size != int(plan_record["bytes"]) or sha256_file(plan_path) != plan_record["sha256"]:
        raise AssertionError("A.2 dry-run plan bytes changed")
    if sha256_file(physical_path) != a2["primary_physical_object_lock_sha256"]:
        raise AssertionError("A.2 physical-object lock bytes changed")
    plan = pd.read_csv(plan_path, sep="\t", keep_default_na=False)
    if len(plan) != EXPECTED_OBJECT_COUNT or int(plan["expected_bytes"].sum()) != EXPECTED_TOTAL_BYTES:
        raise AssertionError("accepted A.2 object count/bytes changed")

    object_checks = verify_downloaded_objects(sealed, acquisition_dir)
    expected = plan[[
        "official_cruise_id", "filename", "role", "format", "direct_url",
        "relative_destination", "expected_bytes", "last_modified",
    ]].rename(columns={
        "role": "source_object_role",
        "direct_url": "original_url",
        "relative_destination": "relative_path",
        "expected_bytes": "bytes",
        "last_modified": "expected_last_modified",
    })
    actual = sealed[[
        "official_cruise_id", "filename", "source_object_role", "format",
        "original_url", "relative_path", "bytes", "expected_last_modified",
    ]].copy()
    expected["bytes"] = expected["bytes"].astype("int64")
    actual["bytes"] = actual["bytes"].astype("int64")
    if not actual.reset_index(drop=True).equals(expected.reset_index(drop=True)):
        raise AssertionError("sealed manifest does not close one-to-one against A.2 plan")

    inventory = {
        path.relative_to(acquisition_dir).as_posix()
        for path in (acquisition_dir / "objects").rglob("*")
        if path.is_file()
    }
    if inventory != object_checks["relative_paths"]:
        raise AssertionError("sealed object filesystem inventory does not match manifest")
    if object_checks["object_count"] != EXPECTED_OBJECT_COUNT or object_checks["total_bytes"] != EXPECTED_TOTAL_BYTES:
        raise AssertionError("sealed object count/byte closure failed")
    if sealed["official_cruise_id"].drop_duplicates().tolist() != PRIMARY_IDS:
        raise AssertionError("sealed cruise ID order/set changed")

    expected_audit_values = {
        "primary_cruise_ids": PRIMARY_IDS,
        "object_count": EXPECTED_OBJECT_COUNT,
        "total_bytes": EXPECTED_TOTAL_BYTES,
        "download_cap_bytes": DOWNLOAD_CAP_BYTES,
        "role": "sealed_unprocessed",
        "content_parsed": False,
        "verification_required": True,
        "stage_c_authorized": False,
    }
    for key, value in expected_audit_values.items():
        if audit.get(key) != value:
            raise AssertionError(f"Stage B audit mismatch for {key}")
    if set(audit.get("outputs", {})) != {"sealed_archive_manifest", "access_lock"}:
        raise AssertionError("Stage B audit output set mismatch")

    for name, path in (("sealed_archive_manifest", sealed_path), ("access_lock", access_path)):
        record = audit["outputs"][name]
        if Path(record["path"]).resolve() != path or path.stat().st_size != int(record["bytes"]) or sha256_file(path) != record["sha256"]:
            raise AssertionError(f"Stage B audit output mismatch: {name}")
    authorization_record = audit["authorization_receipt"]
    if (
        Path(authorization_record["path"]).resolve() != authorization_path
        or authorization_path.stat().st_size != int(authorization_record["bytes"])
        or sha256_file(authorization_path) != authorization_record["sha256"]
    ):
        raise AssertionError("authorization receipt copy changed")

    downloader_guard = assert_no_parser_logic(DOWNLOADER_PATH)
    verifier_guard = assert_no_parser_logic(Path(__file__).resolve())
    if authorization.get("stage_b_downloader_sha256") != downloader_guard["sha256"]:
        raise AssertionError("authorization downloader SHA256 mismatch")
    if authorization.get("stage_b_verifier_sha256") != verifier_guard["sha256"]:
        raise AssertionError("authorization verifier SHA256 mismatch")
    if audit["source_code"]["downloader_sha256"] != downloader_guard["sha256"]:
        raise AssertionError("audit downloader SHA256 mismatch")
    if audit["source_code"]["verifier_sha256"] != verifier_guard["sha256"]:
        raise AssertionError("audit verifier SHA256 mismatch")
    if Path(audit["source_code"]["downloader_path"]).resolve() != DOWNLOADER_PATH:
        raise AssertionError("audit downloader path mismatch")
    if Path(audit["source_code"]["verifier_path"]).resolve() != Path(__file__).resolve():
        raise AssertionError("audit verifier path mismatch")

    expected_access = {
        "status": "sealed_unprocessed",
        "role": "sealed_unprocessed",
        "content_parsed": False,
        "primary_cruise_ids": PRIMARY_IDS,
        "object_count": EXPECTED_OBJECT_COUNT,
        "total_bytes": EXPECTED_TOTAL_BYTES,
        "confirmation_role_eligible": False,
        "stage_c_authorized": False,
        "stage_c_required": True,
        "access_allowed": False,
        "verification_required": True,
    }
    for key, value in expected_access.items():
        if access.get(key) != value:
            raise AssertionError(f"access-lock mismatch for {key}")
    if access.get("sealed_archive_manifest_sha256") != sha256_file(sealed_path):
        raise AssertionError("access lock manifest SHA256 mismatch")
    if Path(access.get("verification_path", "")).resolve() != verification_path:
        raise AssertionError("access lock verification path mismatch")

    receipt = {
        "schema_version": 1,
        "status": "pass",
        "stage": "B_opaque_sealed_acquisition_verification",
        "run_id": run_id,
        "verified_utc": utc_now(),
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "checks": {
            "a2_manifest_sha256": a2["manifest_sha256"],
            "a2_verification_sha256": a2["verification_sha256"],
            "a2_final_download_lock_sha256": a2["final_download_lock_sha256"],
            "primary_physical_object_lock_sha256": a2["primary_physical_object_lock_sha256"],
            "primary_cruise_ids": PRIMARY_IDS,
            "object_count": object_checks["object_count"],
            "total_bytes": object_checks["total_bytes"],
            "objects_reopened_and_rehashed": object_checks["object_count"],
            "last_modified_closed": int(sealed["expected_last_modified"].ne("").sum()),
            "content_parsed": False,
            "role": "sealed_unprocessed",
            "confirmation_role_eligible": False,
            "parser_guards": [downloader_guard, verifier_guard],
        },
    }
    atomic_json(receipt, verification_path)
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    result = verify_stage_b(parse_args().acquisition_dir)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
