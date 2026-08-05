#!/usr/bin/env python3
"""Dry-run or separately authorized opaque Stage B acquisition.

The accepted Stage A.2 receipt does not authorize execution. ``--dry-run`` is
read-only. ``--execute`` requires a separate authorization receipt bound to the
exact A.2 lock, acquisition run ID, fixed output root, downloader/verifier
source hashes, primary IDs and 12 GiB cap before any network request can occur.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
PRIMARY_IDS = ["EQT20210702", "EQT190012", "EQT180002", "TN352"]
DOWNLOAD_CAP_BYTES = 12 * 1024**3
OFFICIAL_OBJECT_HOST = "data.ngdc.noaa.gov"
STAGE_B_OUTPUT_ROOT = (REPO_ROOT / "ncei/archive/scs_v2_sealed_confirmation").resolve()
STAGE_B_VERIFIER = (REPO_ROOT / "ncei/code/verify_scs_v2_sealed_confirmation_stage_b.py").resolve()
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


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


def atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False, compression="snappy")
    os.replace(temporary, path)


def validate_acquisition_run_id(value: str) -> str:
    if (
        not value
        or not RUN_ID_RE.fullmatch(value)
        or value in {".", ".."}
        or ".." in value
        or "/" in value
        or "\\" in value
        or Path(value).is_absolute()
    ):
        raise ValueError("acquisition_run_id must be one safe path segment without '..' or separators")
    return value


def validate_output_root(value: Path) -> Path:
    resolved = value.resolve()
    if resolved != STAGE_B_OUTPUT_ROOT:
        raise ValueError(f"Stage B output root must be fixed at {STAGE_B_OUTPUT_ROOT}")
    return resolved


def validate_locked_object_url(url: str) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(url)
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
        raise ValueError(f"invalid locked NCEI physical-object URL: {url}")
    return parsed


def validate_response_before_body(
    response: Any,
    expected_url: str,
    expected_last_modified: str,
) -> tuple[int, str, dict[str, str]]:
    status = int(getattr(response, "status", 200))
    if status < 200 or status >= 300:
        raise RuntimeError(f"physical object GET failed with HTTP {status}: {expected_url}")
    expected = validate_locked_object_url(expected_url)
    resolved_url = str(response.geturl())
    resolved = validate_locked_object_url(resolved_url)
    if (
        resolved.scheme != expected.scheme
        or resolved.hostname != expected.hostname
        or resolved.port != expected.port
        or resolved.path != expected.path
        or resolved.query != expected.query
    ):
        raise RuntimeError(f"physical object redirect changed locked host/path: {expected_url} -> {resolved_url}")
    headers = {key.lower(): value for key, value in response.headers.items()}
    response_last_modified = headers.get("last-modified", "")
    if not expected_last_modified:
        raise RuntimeError(f"locked Last-Modified is missing for {expected_url}")
    if not response_last_modified:
        raise RuntimeError(f"GET response Last-Modified is missing for {expected_url}")
    if response_last_modified != expected_last_modified:
        raise RuntimeError(
            f"GET response Last-Modified mismatch for {expected_url}: "
            f"{response_last_modified!r} != {expected_last_modified!r}"
        )
    return status, resolved_url, headers


def validate_a2_run(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], pd.DataFrame]:
    run_dir = run_dir.resolve()
    manifest_path = run_dir / "audit_manifest.json"
    verification_path = run_dir / "verification.json"
    final_lock_path = run_dir / "final_download_lock.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    final_lock = json.loads(final_lock_path.read_text(encoding="utf-8"))
    if manifest.get("stage") != "A.2_offline_final_download_lock" or verification.get("status") != "pass":
        raise ValueError("Stage A.2 run is not independently verified")
    if final_lock.get("immutable_primary_confirmation_cruise_ids") != PRIMARY_IDS:
        raise ValueError("Stage A.2 primary IDs do not match the downloader contract")
    if final_lock.get("aggregate_download_cap_bytes") != DOWNLOAD_CAP_BYTES:
        raise ValueError("Stage A.2 download cap mismatch")
    if final_lock.get("stage_b_authorized") is not False or final_lock.get("stage_b_dry_run_only") is not True:
        raise ValueError("Stage A.2 lock must remain unauthorized and dry-run only")
    for name, record in manifest["outputs"].items():
        path = Path(record["path"])
        if not path.exists() or path.stat().st_size != record["bytes"] or sha256_file(path) != record["sha256"]:
            raise ValueError(f"Stage A.2 artifact mismatch: {name}")
    physical_path = Path(manifest["outputs"]["primary_physical_object_lock"]["path"])
    if sha256_file(physical_path) != final_lock["primary_physical_object_lock_sha256"]:
        raise ValueError("primary physical-object lock hash mismatch")
    plan = pd.read_csv(Path(manifest["outputs"]["stage_b_dry_run_plan"]["path"]), sep="\t", keep_default_na=False)
    if len(plan) != int(final_lock["physical_object_count"]):
        raise ValueError("dry-run plan count mismatch")
    if plan["download_executed"].astype(bool).any() or plan["dry_run_status"].ne("planned_not_authorized").any():
        raise ValueError("Stage A.2 plan contains an executed object")
    if int(plan["expected_bytes"].sum()) != int(final_lock["exact_total_bytes"]):
        raise ValueError("dry-run plan byte total mismatch")
    if int(final_lock["exact_total_bytes"]) > DOWNLOAD_CAP_BYTES:
        raise ValueError("dry-run plan exceeds the 12 GiB cap")
    for row in plan.itertuples(index=False):
        validate_locked_object_url(str(row.direct_url))
        if not str(row.last_modified):
            raise ValueError(f"dry-run plan lacks frozen Last-Modified: {row.direct_url}")
        destination = PurePosixPath(str(row.relative_destination))
        expected_prefix = ("objects", str(row.official_cruise_id))
        if destination.is_absolute() or ".." in destination.parts or destination.parts[:2] != expected_prefix:
            raise ValueError(f"dry-run destination escapes its cruise root: {destination}")
    return manifest, verification, final_lock, plan


def run_dry_run(run_dir: Path) -> dict[str, Any]:
    manifest, verification, final_lock, plan = validate_a2_run(run_dir)
    return {
        "status": "dry_run_pass",
        "stage_b_authorized": False,
        "a2_run_id": final_lock["run_id"],
        "a2_manifest_sha256": sha256_file(Path(run_dir) / "audit_manifest.json"),
        "a2_verification_sha256": sha256_file(Path(run_dir) / "verification.json"),
        "primary_physical_object_lock_sha256": final_lock["primary_physical_object_lock_sha256"],
        "primary_cruise_ids": PRIMARY_IDS,
        "physical_object_count": len(plan),
        "last_modified_locked_count": int(plan["last_modified"].astype(str).ne("").sum()),
        "exact_total_bytes": int(plan["expected_bytes"].sum()),
        "aggregate_download_cap_bytes": DOWNLOAD_CAP_BYTES,
        "download_count": 0,
        "network_request_count": 0,
        "maximum_post_download_role": final_lock["maximum_post_download_role"],
        "manifest_verification_status": verification["status"],
        "manifest_stage": manifest["stage"],
    }


def authorization_contract(
    final_lock: dict[str, Any],
    a2_manifest_sha256: str,
    a2_verification_sha256: str,
    a2_final_download_lock_sha256: str,
    acquisition_run_id: str,
    output_root: Path,
) -> dict[str, Any]:
    run_id = validate_acquisition_run_id(acquisition_run_id)
    fixed_root = validate_output_root(output_root)
    if not STAGE_B_VERIFIER.exists():
        raise ValueError(f"Stage B verifier is missing: {STAGE_B_VERIFIER}")
    return {
        "schema_version": 2,
        "stage_b_authorized": True,
        "a2_run_id": final_lock["run_id"],
        "a2_manifest_sha256": a2_manifest_sha256,
        "a2_verification_sha256": a2_verification_sha256,
        "a2_final_download_lock_sha256": a2_final_download_lock_sha256,
        "primary_physical_object_lock_sha256": final_lock["primary_physical_object_lock_sha256"],
        "immutable_primary_confirmation_cruise_ids": PRIMARY_IDS,
        "aggregate_download_cap_bytes": DOWNLOAD_CAP_BYTES,
        "acquisition_run_id": run_id,
        "fixed_output_root": str(fixed_root),
        "stage_b_downloader_sha256": sha256_file(Path(__file__).resolve()),
        "stage_b_verifier_sha256": sha256_file(STAGE_B_VERIFIER),
    }


def validate_authorization_receipt(
    receipt_path: Path,
    final_lock: dict[str, Any],
    a2_manifest_sha256: str,
    a2_verification_sha256: str,
    a2_final_download_lock_sha256: str,
    acquisition_run_id: str,
    output_root: Path,
) -> dict[str, Any]:
    if not receipt_path.exists():
        raise ValueError("Stage B requires a separate authorization receipt")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    expected = authorization_contract(
        final_lock,
        a2_manifest_sha256,
        a2_verification_sha256,
        a2_final_download_lock_sha256,
        acquisition_run_id,
        output_root,
    )
    allowed_keys = set(expected) | {"authorized_by", "authorized_utc"}
    if set(receipt) != allowed_keys:
        raise ValueError("Stage B authorization receipt fields do not exactly match the contract")
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise ValueError(f"Stage B authorization receipt mismatch for {key}")
    if not str(receipt.get("authorized_by", "")).strip() or not str(receipt.get("authorized_utc", "")).strip():
        raise ValueError("Stage B authorization receipt requires authorized_by and authorized_utc")
    return receipt


def download_object(
    url: str,
    destination: Path,
    expected_bytes: int,
    expected_last_modified: str,
    timeout: int,
    user_agent: str,
) -> dict[str, Any]:
    validate_locked_object_url(url)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept-Encoding": "identity"},
        method="GET",
    )
    digest = hashlib.sha256()
    bytes_written = 0
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status, resolved_url, headers = validate_response_before_body(response, url, expected_last_modified)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        with temporary.open("xb") as handle:
            while chunk := response.read(8 * 1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > expected_bytes:
                    raise RuntimeError(f"download exceeded locked Content-Length: {url}")
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
    if bytes_written != expected_bytes:
        raise RuntimeError(f"download byte mismatch for {url}: {bytes_written} != {expected_bytes}")
    os.replace(temporary, destination)
    destination.chmod(0o444)
    return {
        "original_url": url,
        "resolved_url": resolved_url,
        "bytes": bytes_written,
        "sha256": digest.hexdigest(),
        "expected_last_modified": expected_last_modified,
        "response_last_modified": headers["last-modified"],
        "etag": headers.get("etag", ""),
        "http_status": status,
        "downloaded_utc": utc_now(),
        "content_parsed": False,
    }


def manifest_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    columns = [
        "official_cruise_id", "filename", "source_object_role", "format",
        "sealed_role", "original_url", "resolved_url", "relative_path",
        "bytes", "sha256", "expected_last_modified", "response_last_modified",
        "etag", "http_status", "downloaded_utc", "content_parsed",
    ]
    frame = pd.DataFrame(records, columns=columns)
    if len(frame):
        frame["bytes"] = pd.array(frame["bytes"], dtype="Int64")
        frame["http_status"] = pd.array(frame["http_status"], dtype="Int64")
    return frame


def write_failure_receipt(
    temporary_dir: Path,
    error: Exception,
    current_row: Any | None,
    records: list[dict[str, Any]],
    final_lock: dict[str, Any],
    authorization_receipt: Path,
    acquisition_run_id: str,
) -> None:
    completed = manifest_frame(records)
    atomic_parquet(completed, temporary_dir / "completed_object_manifest.parquet")
    receipt = {
        "schema_version": 1,
        "status": "failed_unsealed",
        "sealed": False,
        "acquisition_run_id": acquisition_run_id,
        "failed_utc": utc_now(),
        "error_type": type(error).__name__,
        "error": str(error),
        "failed_object": {
            "official_cruise_id": str(getattr(current_row, "official_cruise_id", "")),
            "direct_url": str(getattr(current_row, "direct_url", "")),
            "relative_destination": str(getattr(current_row, "relative_destination", "")),
        },
        "completed_object_count": len(completed),
        "completed_bytes": int(completed["bytes"].sum()) if len(completed) else 0,
        "expected_object_count": int(final_lock["physical_object_count"]),
        "expected_total_bytes": int(final_lock["exact_total_bytes"]),
        "authorization_receipt_path": str(authorization_receipt.resolve()),
        "authorization_receipt_sha256": sha256_file(authorization_receipt),
        "candidate_replacement_allowed": False,
        "content_parsed": False,
        "role": "failed_unsealed",
        "verification_status": "not_run",
    }
    atomic_json(receipt, temporary_dir / "failure_receipt.json")


def execute_stage_b(
    run_dir: Path,
    authorization_receipt: Path,
    output_root: Path,
    acquisition_run_id: str,
    timeout: int,
) -> Path:
    run_id = validate_acquisition_run_id(acquisition_run_id)
    fixed_root = validate_output_root(output_root)
    manifest, verification, final_lock, plan = validate_a2_run(run_dir)
    a2_manifest_path = Path(run_dir).resolve() / "audit_manifest.json"
    a2_verification_path = Path(run_dir).resolve() / "verification.json"
    a2_final_lock_path = Path(run_dir).resolve() / "final_download_lock.json"
    a2_manifest_sha = sha256_file(a2_manifest_path)
    a2_verification_sha = sha256_file(a2_verification_path)
    a2_final_lock_sha = sha256_file(a2_final_lock_path)
    authorization = validate_authorization_receipt(
        authorization_receipt,
        final_lock,
        a2_manifest_sha,
        a2_verification_sha,
        a2_final_lock_sha,
        run_id,
        fixed_root,
    )
    final_dir = fixed_root / run_id
    failed_dir = fixed_root / f"{run_id}.failed"
    if final_dir.exists() or failed_dir.exists():
        raise FileExistsError(f"immutable Stage B run or failure receipt already exists for {run_id}")
    fixed_root.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=fixed_root))
    records: list[dict[str, Any]] = []
    total = 0
    current_row: Any | None = None
    try:
        (temporary_dir / "authorization_receipt.json").write_bytes(authorization_receipt.read_bytes())
        for current_row in plan.itertuples(index=False):
            expected = int(current_row.expected_bytes)
            total += expected
            if total > DOWNLOAD_CAP_BYTES:
                raise RuntimeError("download plan exceeded the 12 GiB cap during execution")
            destination = temporary_dir / str(current_row.relative_destination)
            result = download_object(
                str(current_row.direct_url),
                destination,
                expected,
                str(current_row.last_modified),
                timeout,
                "SCS-v2-sealed-confirmation-stage-b/2.0 opaque-acquisition",
            )
            result.update({
                "official_cruise_id": current_row.official_cruise_id,
                "filename": current_row.filename,
                "source_object_role": current_row.role,
                "format": current_row.format,
                "sealed_role": "sealed_unprocessed",
                "relative_path": str(current_row.relative_destination),
            })
            records.append(result)

        sealed_manifest = manifest_frame(records)
        sealed_manifest_path = temporary_dir / "sealed_archive_manifest.parquet"
        atomic_parquet(sealed_manifest, sealed_manifest_path)
        access_lock = {
            "schema_version": 1,
            "status": "sealed_unprocessed",
            "role": "sealed_unprocessed",
            "content_parsed": False,
            "primary_cruise_ids": PRIMARY_IDS,
            "object_count": len(sealed_manifest),
            "total_bytes": int(sealed_manifest["bytes"].sum()),
            "sealed_archive_manifest_sha256": sha256_file(sealed_manifest_path),
            "confirmation_role_eligible": False,
            "stage_c_authorized": False,
            "stage_c_required": True,
            "access_allowed": False,
            "verification_required": True,
            "verification_path": str(final_dir / "verification.json"),
        }
        access_lock_path = temporary_dir / "access_lock.json"
        atomic_json(access_lock, access_lock_path)
        copied_authorization = temporary_dir / "authorization_receipt.json"
        audit_manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "created_utc": utc_now(),
            "stage": "B_opaque_sealed_acquisition_pending_verification",
            "authorization": authorization,
            "authorization_receipt": {
                "path": str((final_dir / "authorization_receipt.json")),
                "bytes": copied_authorization.stat().st_size,
                "sha256": sha256_file(copied_authorization),
            },
            "a2_run": {
                "path": str(Path(run_dir).resolve()),
                "manifest_sha256": a2_manifest_sha,
                "verification_sha256": a2_verification_sha,
                "final_download_lock_sha256": a2_final_lock_sha,
                "primary_physical_object_lock_sha256": final_lock["primary_physical_object_lock_sha256"],
            },
            "source_code": {
                "downloader_path": str(Path(__file__).resolve()),
                "downloader_sha256": sha256_file(Path(__file__).resolve()),
                "verifier_path": str(STAGE_B_VERIFIER),
                "verifier_sha256": sha256_file(STAGE_B_VERIFIER),
            },
            "primary_cruise_ids": PRIMARY_IDS,
            "object_count": len(sealed_manifest),
            "total_bytes": int(sealed_manifest["bytes"].sum()),
            "download_cap_bytes": DOWNLOAD_CAP_BYTES,
            "role": "sealed_unprocessed",
            "content_parsed": False,
            "outputs": {
                "sealed_archive_manifest": {
                    "path": str(final_dir / "sealed_archive_manifest.parquet"),
                    "bytes": sealed_manifest_path.stat().st_size,
                    "sha256": sha256_file(sealed_manifest_path),
                    "row_count": len(sealed_manifest),
                },
                "access_lock": {
                    "path": str(final_dir / "access_lock.json"),
                    "bytes": access_lock_path.stat().st_size,
                    "sha256": sha256_file(access_lock_path),
                    "row_count": 1,
                },
            },
            "verification_required": True,
            "stage_c_authorized": False,
        }
        atomic_json(audit_manifest, temporary_dir / "audit_manifest.json")
        os.replace(temporary_dir, final_dir)
        return final_dir
    except Exception as error:
        write_failure_receipt(
            temporary_dir,
            error,
            current_row,
            records,
            final_lock,
            authorization_receipt,
            run_id,
        )
        os.replace(temporary_dir, failed_dir)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a2-run", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--authorization-receipt", type=Path)
    parser.add_argument("--output-root", type=Path, default=STAGE_B_OUTPUT_ROOT)
    parser.add_argument("--acquisition-run-id")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--confirm-stage-b-download", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.dry_run:
        print(stable_json(run_dry_run(args.a2_run)))
        return 0
    if not args.confirm_stage_b_download:
        print("ERROR: Stage B execution requires --confirm-stage-b-download.", file=sys.stderr)
        return 2
    if args.authorization_receipt is None or not args.acquisition_run_id:
        print("ERROR: Stage B execution requires an authorization receipt and acquisition run ID.", file=sys.stderr)
        return 2
    result = execute_stage_b(
        args.a2_run,
        args.authorization_receipt,
        args.output_root,
        args.acquisition_run_id,
        args.timeout,
    )
    print(stable_json({"status": "sealed_unprocessed_pending_verification", "run_dir": str(result)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
