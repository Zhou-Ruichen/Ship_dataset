#!/usr/bin/env python3
"""Dry-run or separately authorized opaque Stage B acquisition.

The current Stage A.2 receipt does not authorize execution. ``--dry-run`` is
read-only. ``--execute`` requires a separate authorization receipt bound to the
exact A.2 lock, manifest, verification, primary IDs and 12 GiB cap before any
network request can occur.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
PRIMARY_IDS = ["EQT20210702", "EQT190012", "EQT180002", "TN352"]
DOWNLOAD_CAP_BYTES = 12 * 1024**3


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
        "exact_total_bytes": int(plan["expected_bytes"].sum()),
        "aggregate_download_cap_bytes": DOWNLOAD_CAP_BYTES,
        "download_count": 0,
        "network_request_count": 0,
        "maximum_post_download_role": final_lock["maximum_post_download_role"],
        "manifest_verification_status": verification["status"],
        "manifest_stage": manifest["stage"],
    }


def validate_authorization_receipt(
    receipt_path: Path,
    final_lock: dict[str, Any],
    manifest_sha256: str,
    verification_sha256: str,
) -> dict[str, Any]:
    if not receipt_path.exists():
        raise ValueError("Stage B requires a separate authorization receipt")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version": 1,
        "stage_b_authorized": True,
        "a2_run_id": final_lock["run_id"],
        "a2_manifest_sha256": manifest_sha256,
        "a2_verification_sha256": verification_sha256,
        "primary_physical_object_lock_sha256": final_lock["primary_physical_object_lock_sha256"],
        "immutable_primary_confirmation_cruise_ids": PRIMARY_IDS,
        "aggregate_download_cap_bytes": DOWNLOAD_CAP_BYTES,
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise ValueError(f"Stage B authorization receipt mismatch for {key}")
    return receipt


def download_object(url: str, destination: Path, expected_bytes: int, timeout: int, user_agent: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept-Encoding": "identity"},
        method="GET",
    )
    digest = hashlib.sha256()
    bytes_written = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(request, timeout=timeout) as response, temporary.open("xb") as handle:
        status = int(getattr(response, "status", 200))
        if status < 200 or status >= 300:
            raise RuntimeError(f"physical object GET failed with HTTP {status}: {url}")
        while chunk := response.read(8 * 1024 * 1024):
            bytes_written += len(chunk)
            if bytes_written > expected_bytes:
                raise RuntimeError(f"download exceeded locked Content-Length: {url}")
            digest.update(chunk)
            handle.write(chunk)
        handle.flush()
        os.fsync(handle.fileno())
        headers = {key.lower(): value for key, value in response.headers.items()}
        resolved_url = response.geturl()
    if bytes_written != expected_bytes:
        raise RuntimeError(f"download byte mismatch for {url}: {bytes_written} != {expected_bytes}")
    os.replace(temporary, destination)
    destination.chmod(0o444)
    return {
        "original_url": url,
        "resolved_url": resolved_url,
        "local_path": str(destination.resolve()),
        "bytes": bytes_written,
        "sha256": digest.hexdigest(),
        "etag": headers.get("etag", ""),
        "last_modified": headers.get("last-modified", ""),
        "downloaded_utc": utc_now(),
        "content_parsed": False,
    }


def execute_stage_b(
    run_dir: Path,
    authorization_receipt: Path,
    output_root: Path,
    acquisition_run_id: str,
    timeout: int,
) -> Path:
    manifest, verification, final_lock, plan = validate_a2_run(run_dir)
    manifest_sha = sha256_file(Path(run_dir) / "audit_manifest.json")
    verification_sha = sha256_file(Path(run_dir) / "verification.json")
    authorization = validate_authorization_receipt(authorization_receipt, final_lock, manifest_sha, verification_sha)
    final_dir = output_root.resolve() / acquisition_run_id
    if final_dir.exists():
        raise FileExistsError(f"immutable acquisition run already exists: {final_dir}")
    output_root.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix=f".{acquisition_run_id}.", dir=output_root))
    records: list[dict[str, Any]] = []
    total = 0
    try:
        for row in plan.itertuples(index=False):
            expected = int(row.expected_bytes)
            total += expected
            if total > DOWNLOAD_CAP_BYTES:
                raise RuntimeError("download plan exceeded the 12 GiB cap during execution")
            destination = temporary_dir / str(row.relative_destination)
            result = download_object(
                str(row.direct_url),
                destination,
                expected,
                timeout,
                "SCS-v2-sealed-confirmation-stage-b/1.0 opaque-acquisition",
            )
            result.update({
                "official_cruise_id": row.official_cruise_id,
                "filename": row.filename,
                "role": row.role,
                "format": row.format,
            })
            records.append(result)
        manifest_out = {
            "schema_version": 1,
            "run_id": acquisition_run_id,
            "created_utc": utc_now(),
            "stage": "B_opaque_sealed_acquisition",
            "authorization_receipt": {
                "path": str(authorization_receipt.resolve()),
                "sha256": sha256_file(authorization_receipt),
                "authorization": authorization,
            },
            "a2_run": {
                "path": str(Path(run_dir).resolve()),
                "manifest_sha256": manifest_sha,
                "verification_sha256": verification_sha,
                "primary_physical_object_lock_sha256": final_lock["primary_physical_object_lock_sha256"],
            },
            "primary_cruise_ids": PRIMARY_IDS,
            "object_count": len(records),
            "total_bytes": total,
            "download_cap_bytes": DOWNLOAD_CAP_BYTES,
            "role": "sealed_unprocessed",
            "content_parsed": False,
            "objects": records,
            "source_manifest_stage": manifest["stage"],
            "source_verification_status": verification["status"],
        }
        atomic_json(manifest_out, temporary_dir / "sealed_archive_manifest.json")
        os.replace(temporary_dir, final_dir)
        return final_dir
    except Exception:
        failed_dir = output_root.resolve() / f"{acquisition_run_id}.failed"
        if not failed_dir.exists():
            os.replace(temporary_dir, failed_dir)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a2-run", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--authorization-receipt", type=Path)
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT / "ncei/archive/scs_v2_sealed_confirmation")
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
    print(stable_json({"status": "sealed_unprocessed", "run_dir": str(result)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
