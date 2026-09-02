#!/usr/bin/env python3
"""Create an immutable Stage C.0.1/C.1 readiness run with zero candidate access."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from _common.scs_v2_stage_c1_oracle import read_format58_fixture
from ncei.code.scs_confirmation.scs_v2_stage_c1_contract import (
    ACQUISITION_RUN_ID,
    join_all_and_good,
    parse_mblist_tsv,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
TASK_ROOT = REPO_ROOT / ".trellis/tasks/08-06-scs-v2-stage-c0-source-internal-planning"
RESEARCH_ROOT = TASK_ROOT / "research"
READINESS_ROOT = REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/stage_c_readiness"
FIXTURE_ROOT = REPO_ROOT / "_common/tests/fixtures/scs_v2_stage_c1"
GOLDEN_FIXTURE = FIXTURE_ROOT / "MGL1104-9999-eight-ping.mb58"
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
SOURCE_FILES = {
    "adapter": REPO_ROOT / "ncei/code/scs_confirmation/scs_v2_stage_c1_contract.py",
    "oracle": REPO_ROOT / "_common/scs_v2_stage_c1_oracle.py",
    "future_stage_c_verifier": REPO_ROOT / "ncei/code/scs_confirmation/verify_scs_v2_stage_c_source_internal.py",
    "readiness_producer": Path(__file__).resolve(),
    "readiness_verifier": REPO_ROOT / "ncei/code/scs_confirmation/verify_scs_v2_stage_c1_readiness.py",
    "tests": REPO_ROOT / "_common/tests/test_scs_v2_stage_c1_readiness.py",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    return sha256_bytes(encoded)


def atomic_json(value: Any, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def run_checked(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(argv, cwd=cwd or REPO_ROOT, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {argv!r}\n{completed.stderr}")
    return completed


def validate_inputs(environment_root: Path, source_root: Path, planning_commit: str) -> dict[str, Any]:
    if sha256_file(ACCEPTED_C0_LOCK) != ACCEPTED_C0_LOCK_SHA256:
        raise AssertionError("accepted Stage C.0 planning lock changed")
    c0_lock = json.loads(ACCEPTED_C0_LOCK.read_text(encoding="utf-8"))
    if c0_lock["acquisition_run"]["run_id"] != ACQUISITION_RUN_ID:
        raise AssertionError("accepted acquisition run changed")
    if c0_lock["acquisition_run"]["ordered_cruise_ids"] != PRIMARY_IDS:
        raise AssertionError("accepted cruise IDs/order changed")
    if not re.fullmatch(r"[0-9a-f]{40}", planning_commit):
        raise ValueError("planning commit must be a full Git SHA1")
    if run_checked(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).stdout.strip() != planning_commit:
        raise AssertionError("planning commit is not current HEAD")
    if run_checked(["git", "rev-parse", "HEAD"], cwd=source_root).stdout.strip() != MBSYSTEM_COMMIT:
        raise AssertionError("MB-System source commit mismatch")
    if run_checked(["git", "describe", "--tags", "--exact-match", "HEAD"], cwd=source_root).stdout.strip() != MBSYSTEM_TAG:
        raise AssertionError("MB-System source tag mismatch")
    if run_checked(["git", "status", "--porcelain"], cwd=source_root).stdout.strip():
        raise AssertionError("MB-System source checkout is dirty")
    if not environment_root.is_dir():
        raise FileNotFoundError(environment_root)
    for path in [*SOURCE_FILES.values(), *(RESEARCH_ROOT / name for name in CONTRACT_FILES), GOLDEN_FIXTURE]:
        if not path.is_file():
            raise FileNotFoundError(path)
    return c0_lock


def package_records(environment_root: Path) -> list[dict[str, Any]]:
    records = []
    keys = ("name", "version", "build", "build_number", "channel", "subdir", "fn", "url", "md5", "sha256", "requested_spec")
    for path in sorted((environment_root / "conda-meta").glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        record = {key: value.get(key) for key in keys}
        record["metadata_filename"] = path.name
        records.append(record)
    if not records or not any(item["name"] == "gzip" and item["version"] == "1.14" for item in records):
        raise AssertionError("fixed environment lacks gzip 1.14")
    return records


def write_explicit_lock(records: list[dict[str, Any]], path: Path) -> None:
    lines = ["@EXPLICIT"]
    for record in records:
        if not record["url"] or not record["md5"] or not record["sha256"]:
            raise AssertionError(f"conda package lacks URL/hash: {record['name']}")
        lines.append(f"{record['url']}#md5={record['md5']}&sha256={record['sha256']}")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def parse_ldd(binary: Path) -> tuple[str, list[Path]]:
    output = run_checked(["ldd", str(binary)]).stdout
    paths: set[Path] = set()
    for line in output.splitlines():
        match = re.search(r"=>\s+(/\S+)", line)
        if match is None:
            match = re.match(r"\s*(/\S+)\s+\(", line)
        if match is not None:
            path = Path(match.group(1)).resolve()
            if path.is_file():
                paths.add(path)
    return output, sorted(paths, key=str)


def environment_material(environment_root: Path, source_root: Path, run_dir: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    build_root = environment_root / "build/mbsystem"
    binaries = {
        "mblist": build_root / "src/utilities/mblist",
        "mbinfo": build_root / "src/utilities/mbinfo",
        "gzip": environment_root / "bin/gzip",
        "cmake": environment_root / "bin/cmake",
        "ninja": environment_root / "bin/ninja",
        "c_compiler": environment_root / "bin/x86_64-conda-linux-gnu-gcc",
        "cxx_compiler": environment_root / "bin/x86_64-conda-linux-gnu-g++",
    }
    if not all(path.is_file() for path in binaries.values()):
        missing = [name for name, path in binaries.items() if not path.is_file()]
        raise FileNotFoundError(f"fixed environment tools missing: {missing}")

    records = package_records(environment_root)
    explicit_lock = run_dir / "conda-explicit-lock.txt"
    write_explicit_lock(records, explicit_lock)

    source_tree = run_checked(["git", "ls-tree", "-r", "--full-tree", "HEAD"], cwd=source_root).stdout
    source_tree_path = run_dir / "mbsystem-source-tree.tsv"
    source_tree_path.write_text(source_tree, encoding="utf-8")
    source_remote = run_checked(["git", "remote", "get-url", "origin"], cwd=source_root).stdout.strip()
    source_tree_id = run_checked(["git", "rev-parse", "HEAD^{tree}"], cwd=source_root).stdout.strip()

    cache_path = build_root / "CMakeCache.txt"
    cache_copy = run_dir / "CMakeCache.txt"
    shutil.copy2(cache_path, cache_copy)
    selected_cache_keys = {
        "BUILD_SHARED_LIBS",
        "CMAKE_BUILD_RPATH",
        "CMAKE_BUILD_TYPE",
        "CMAKE_CXX_COMPILER",
        "CMAKE_CXX_FLAGS",
        "CMAKE_C_COMPILER",
        "CMAKE_C_FLAGS",
        "CMAKE_FIND_ROOT_PATH",
        "CMAKE_FIND_ROOT_PATH_MODE_INCLUDE",
        "CMAKE_FIND_ROOT_PATH_MODE_LIBRARY",
        "CMAKE_FIND_ROOT_PATH_MODE_PACKAGE",
        "CMAKE_INSTALL_PREFIX",
        "CMAKE_INSTALL_RPATH",
        "buildDeprecated",
        "buildGSF",
        "buildGUIs",
        "buildOpenCV",
        "buildQt",
        "buildTRN",
        "buildTRNLCM",
        "buildTests",
    }
    selected_cache: dict[str, str] = {}
    for line in cache_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith(("#", "//")) or "=" not in line or ":" not in line.split("=", 1)[0]:
            continue
        left, value = line.split("=", 1)
        key = left.split(":", 1)[0]
        if key in selected_cache_keys:
            selected_cache[key] = value
    if selected_cache.get("buildGSF") != "ON" or selected_cache.get("buildGUIs") != "OFF":
        raise AssertionError("CMake cache differs from frozen headless parser build")

    help_paths: dict[str, Path] = {}
    binary_records: dict[str, Any] = {}
    runtime_paths: set[Path] = set()
    for name, binary in binaries.items():
        help_argv = [str(binary), "-h"] if name in {"mblist", "mbinfo"} else [str(binary), "--version"]
        completed = run_checked(help_argv)
        snapshot = (completed.stdout + completed.stderr).encode("utf-8")
        help_path = run_dir / f"{name}-help.txt"
        help_path.write_bytes(snapshot)
        help_paths[name] = help_path
        ldd_output, dependencies = parse_ldd(binary)
        ldd_path = run_dir / f"{name}-ldd.txt"
        ldd_path.write_text(ldd_output, encoding="utf-8")
        runtime_paths.update(dependencies)
        binary_records[name] = {
            "path": str(binary.resolve()),
            "bytes": binary.stat().st_size,
            "sha256": sha256_file(binary),
            "version_or_help_argv": help_argv,
            "version_or_help_sha256": sha256_file(help_path),
            "ldd_sha256": sha256_file(ldd_path),
        }
    if "MB-system Version 5.8.3beta16" not in help_paths["mblist"].read_text(encoding="utf-8"):
        raise AssertionError("mblist help does not identify the pinned version")
    if "MB-system Version 5.8.3beta16" not in help_paths["mbinfo"].read_text(encoding="utf-8"):
        raise AssertionError("mbinfo help does not identify the pinned version")

    runtime_records = [
        {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(runtime_paths, key=str)
    ]
    configure_argv = [
        str(environment_root / "bin/cmake"),
        "-S", str(source_root),
        "-B", str(build_root),
        "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_C_COMPILER={environment_root / 'bin/x86_64-conda-linux-gnu-gcc'}",
        f"-DCMAKE_CXX_COMPILER={environment_root / 'bin/x86_64-conda-linux-gnu-g++'}",
        f"-DCMAKE_PREFIX_PATH={environment_root}",
        f"-DCMAKE_FIND_ROOT_PATH={environment_root}",
        "-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY",
        "-DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=ONLY",
        "-DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=ONLY",
        f"-DCMAKE_INSTALL_PREFIX={environment_root / 'install'}",
        f"-DCMAKE_INSTALL_RPATH={environment_root / 'lib'}",
        f"-DCMAKE_BUILD_RPATH={environment_root / 'lib'}",
        "-DBUILD_SHARED_LIBS=ON",
        "-DbuildGUIs=OFF",
        "-DbuildOpenCV=OFF",
        "-DbuildTRN=OFF",
        "-DbuildTRNLCM=OFF",
        "-DbuildGSF=ON",
        "-DbuildQt=OFF",
        "-DbuildDeprecated=OFF",
        "-DbuildTests=OFF",
        f"-DCMAKE_C_FLAGS=-I{environment_root / 'include/glib-2.0'} -I{environment_root / 'lib/glib-2.0/include'}",
        f"-DCMAKE_CXX_FLAGS=-I{environment_root / 'include/glib-2.0'} -I{environment_root / 'lib/glib-2.0/include'}",
    ]
    build_argv = [
        str(environment_root / "bin/cmake"), "--build", str(build_root), "--target", "mblist", "mbinfo", "--parallel", "8"
    ]
    material = {
        "environment_root": str(environment_root),
        "source": {
            "remote": source_remote,
            "commit": MBSYSTEM_COMMIT,
            "tag": MBSYSTEM_TAG,
            "tree": source_tree_id,
            "tree_listing_sha256": sha256_file(source_tree_path),
        },
        "conda_packages": records,
        "conda_explicit_lock_sha256": sha256_file(explicit_lock),
        "cmake_cache_sha256": sha256_file(cache_copy),
        "cmake_cache_selected": selected_cache,
        "configure_argv": configure_argv,
        "build_argv": build_argv,
        "binaries": binary_records,
        "runtime_files": runtime_records,
        "host_abi": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "libc": list(platform.libc_ver()),
        },
    }
    return material, help_paths


def run_fixture(environment_root: Path, run_dir: Path) -> dict[str, Any]:
    mblist = environment_root / "build/mbsystem/src/utilities/mblist"
    mbinfo = environment_root / "build/mbsystem/src/utilities/mbinfo"
    all_path = run_dir / "golden-u3.tsv"
    good_path = run_dir / "golden-u0.tsv"
    commands = {
        "mbinfo": [str(mbinfo), f"-I{GOLDEN_FIXTURE}", "-F58", "-X1"],
        "mblist_u3": [str(mblist), f"-I{GOLDEN_FIXTURE}", "-F58", "-P1", "-L0", "-MA", "-U3", "-OMN#XYzH", f"-X{all_path}"],
        "mblist_u0": [str(mblist), f"-I{GOLDEN_FIXTURE}", "-F58", "-P1", "-L0", "-MA", "-U0", "-OMN#XYzH", f"-X{good_path}"],
    }
    mbinfo_completed = run_checked(commands["mbinfo"])
    mbinfo_value = json.loads(mbinfo_completed.stdout)
    run_checked(commands["mblist_u3"])
    run_checked(commands["mblist_u0"])
    all_rows = parse_mblist_tsv(all_path.read_text(encoding="ascii"), check_mode=3)
    good_rows = parse_mblist_tsv(good_path.read_text(encoding="ascii"), check_mode=0)
    joined = join_all_and_good(ACQUISITION_RUN_ID, "fixtures/MGL1104-9999-eight-ping.mb58", all_rows, good_rows)
    oracle = read_format58_fixture(GOLDEN_FIXTURE)
    if len(all_rows) != len(oracle):
        raise AssertionError("golden U3/oracle row count mismatch")
    differences = {
        "epoch_seconds": max(abs(float(actual.epoch_seconds_utc) - expected.epoch_seconds_utc) for actual, expected in zip(all_rows, oracle)),
        "longitude_deg": max(abs(actual.lon_deg - expected.lon_deg) for actual, expected in zip(all_rows, oracle)),
        "latitude_deg": max(abs(actual.lat_deg - expected.lat_deg) for actual, expected in zip(all_rows, oracle)),
        "depth_m": max(abs(actual.parser_depth_value - expected.parser_depth_value) for actual, expected in zip(all_rows, oracle)),
        "heading_deg": max(abs(actual.heading_deg - expected.heading_deg) for actual, expected in zip(all_rows, oracle)),
    }
    tolerances = {
        "epoch_seconds": 1.0e-6,
        "longitude_deg": 5.0e-8,
        "latitude_deg": 5.0e-8,
        "depth_m": 1.1e-4,
        "heading_deg": 1.0e-3,
    }
    if any(differences[name] > limit for name, limit in tolerances.items()):
        raise AssertionError(f"golden/oracle numeric mismatch: {differences}")
    actual_states = Counter(str(row["native_quality_state"]) for row in joined)
    oracle_states = Counter(row.quality_state for row in oracle)
    if actual_states != oracle_states or actual_states != {"good": 3450, "flagged": 6}:
        raise AssertionError("golden/oracle quality-state mismatch")
    all_path.unlink()
    good_path.unlink()
    return {
        "schema_version": 1,
        "status": "pass",
        "candidate_data_accessed": False,
        "fixture": {
            "path": str(GOLDEN_FIXTURE),
            "bytes": GOLDEN_FIXTURE.stat().st_size,
            "sha256": sha256_file(GOLDEN_FIXTURE),
            "cruise_id": "MGL1104",
            "stage_b_primary_overlap": False,
        },
        "oracle": {
            "path": str(SOURCE_FILES["oracle"]),
            "sha256": sha256_file(SOURCE_FILES["oracle"]),
            "imports_or_executes_mbsystem": False,
        },
        "commands": {name: {"argv": argv, "argv_sha256": canonical_sha256(argv)} for name, argv in commands.items()},
        "mbinfo": {
            "record_count": int(mbinfo_value["data_totals"]["number_of_records"]),
            "beam_count": int(mbinfo_value["bathymetry_data"]["number_beams"]),
            "good_beam_count": int(mbinfo_value["bathymetry_data"]["number_good_beams"]),
            "flagged_beam_count": int(mbinfo_value["bathymetry_data"]["number_flagged_beams"]),
        },
        "mblist": {
            "u3_rows": len(all_rows),
            "u0_rows": len(good_rows),
            "ping_count": len({(row.epoch_seconds_utc, row.native_ping_counter) for row in all_rows}),
            "field_count": 7,
            "field_order": ["M", "N", "#", "X", "Y", "z", "H"],
            "delimiter_hex": "09",
            "record_terminator_hex": "0A",
            "quality_counts": dict(sorted(actual_states.items())),
        },
        "oracle_max_abs_difference": differences,
        "tolerances": tolerances,
        "mismatch_count": 0,
    }


def run_tests() -> dict[str, Any]:
    command = [sys.executable, "-m", "unittest", "_common.tests.test_scs_v2_stage_c1_readiness"]
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    combined = completed.stdout + completed.stderr
    match = re.search(r"Ran (\d+) tests?", combined)
    count = int(match.group(1)) if match else 0
    if completed.returncode != 0 or count < 9:
        raise RuntimeError(f"Stage C.1 tests failed:\n{combined}")
    return {
        "status": "pass",
        "command": command,
        "cwd": str(REPO_ROOT),
        "returncode": completed.returncode,
        "tests_run": count,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "candidate_network_access": False,
        "sealed_object_body_read_count": 0,
    }


def artifact_record(path: Path, final_path: Path, *, row_count: int = 1, schema: Any = None) -> dict[str, Any]:
    return {
        "path": str(final_path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "row_count": row_count,
        "schema": schema,
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
        environment_digest = canonical_sha256(material)
        environment_lock = {
            "schema_version": 1,
            "stage": "C1_fixed_parser_environment",
            "environment_digest": environment_digest,
            "material": material,
        }
        atomic_json(environment_lock, temporary_dir / "environment_lock.json")
        fixture = run_fixture(environment_root, temporary_dir)
        atomic_json(fixture, temporary_dir / "fixture_verification.json")
        tests = run_tests()
        atomic_json(tests, temporary_dir / "test_results.json")

        source_hashes = {name: {"path": str(path), "sha256": sha256_file(path)} for name, path in SOURCE_FILES.items()}
        authorization = {
            "schema_version": 2,
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
            "stage_c01_planning_commit": planning_commit,
            "stage_c1_readiness_run_id": run_id,
            "stage_c1_readiness_manifest_sha256": "<REQUIRED_PASS_READINESS_MANIFEST_SHA256>",
            "stage_c1_readiness_verification_sha256": "<REQUIRED_PASS_READINESS_VERIFICATION_SHA256>",
            "parser_name": "MB-System",
            "parser_version": MBSYSTEM_TAG,
            "parser_source_commit": MBSYSTEM_COMMIT,
            "parser_environment_digest": environment_digest,
            "parser_binary_sha256": {
                name: material["binaries"][name]["sha256"] for name in ("mblist", "mbinfo", "gzip")
            },
            "parser_help_sha256": {
                name: material["binaries"][name]["version_or_help_sha256"] for name in ("mblist", "mbinfo")
            },
            "contract_sha256": {name: value["sha256"] for name, value in contract_records.items()},
            "fixture_bytes_sha256": fixture["fixture"]["sha256"],
            "fixture_oracle_sha256": fixture["oracle"]["sha256"],
            "fixture_verification_sha256": sha256_file(temporary_dir / "fixture_verification.json"),
            "adapter_sha256": source_hashes["adapter"]["sha256"],
            "future_stage_c_verifier_sha256": source_hashes["future_stage_c_verifier"]["sha256"],
            "confirmation_role_eligible": False,
            "model_or_product_evaluation_authorized": False,
            "stage_d_confirmation_evaluation_authorized": False,
        }
        atomic_json(authorization, temporary_dir / "stage_c_authorization.template.json")

        access_ledger = {
            "schema_version": 1,
            "stage": "C0.1_C1_zero_candidate_readiness",
            "allowed_inputs": [
                str(ACCEPTED_C0_LOCK),
                str(environment_root),
                str(source_root),
                str(GOLDEN_FIXTURE),
                *[str(RESEARCH_ROOT / name) for name in CONTRACT_FILES],
                *[str(path) for path in SOURCE_FILES.values()],
            ],
            "stage_b_objects_root_opened": False,
            "sealed_object_body_read_count": 0,
            "archive_decompression_count": 0,
            "candidate_sounding_row_count": 0,
            "candidate_cell_row_count": 0,
            "candidate_qc_result_count": 0,
            "product_or_model_reference_count": 0,
        }
        atomic_json(access_ledger, temporary_dir / "access_ledger.json")

        readiness_lock = {
            "schema_version": 1,
            "stage": "C0.1_C1_zero_candidate_readiness",
            "status": "ready_for_separate_stage_c_authorization",
            "run_id": run_id,
            "created_utc": utc_now(),
            "planning_commit": planning_commit,
            "accepted_stage_c0_planning_lock_sha256": ACCEPTED_C0_LOCK_SHA256,
            "acquisition_run_id": ACQUISITION_RUN_ID,
            "immutable_primary_cruise_ids": PRIMARY_IDS,
            "environment_digest": environment_digest,
            "mbsystem_version": MBSYSTEM_TAG,
            "mbsystem_source_commit": MBSYSTEM_COMMIT,
            "fixture_status": fixture["status"],
            "offline_tests_run": tests["tests_run"],
            "source_object_id_formula_frozen": True,
            "source_object_sha256_used_as_identity": False,
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
            "stage": "C0.1_C1_zero_candidate_readiness",
            "run_id": run_id,
            "created_utc": utc_now(),
            "planning_commit": planning_commit,
            "accepted_stage_c0": {
                "path": str(ACCEPTED_C0_LOCK),
                "sha256": ACCEPTED_C0_LOCK_SHA256,
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
