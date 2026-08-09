#!/usr/bin/env python3
"""Shared, data-independent helpers for the TN352 audit."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pyarrow.parquet as pq


REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_ROOT = REPO_ROOT / "ncei/derived/scs_tn352_processing_and_support_audit"
STAGE_C_ROOT = REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/stage_c/20260808T231659Z"
REFERENCE_STAGE_C_ROOT = REPO_ROOT / "ncei/derived/scs_v2_sealed_confirmation/stage_c/20260807T090000Z"
TASK_ROOT = REPO_ROOT / ".trellis/tasks/08-10-scs-tn352-processing-and-support-audit"
PROTOCOL_PATH = TASK_ROOT / "research/support-protocol-v1.yaml"
HANDOFF_PATH = (
    REPO_ROOT
    / ".trellis/tasks/archive/2026-08/08-09-scs-v2-stage-c-development-rerun/research"
    / "stage-c-development-handoff-20260808T231659Z.json"
)
MRAR_POINTS_PATH = REPO_ROOT / "ncei/derived/regional_mrar/points_checked/bathymetry_points.parquet"
MRAR_CELLS_PATH = REPO_ROOT / "ncei/derived/validation_cells_1min/regional_mrar_experiment_cells.parquet"

RUN_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
CONTRACT_FIELDS = (
    "contract_item_id",
    "category",
    "item",
    "status",
    "observed_value",
    "unit",
    "evidence_path",
    "evidence_locator",
    "evidence_sha256",
    "notes",
)
CONTRACT_STATUSES = {
    "verified_used",
    "verified_not_used",
    "known_from_output",
    "unknown",
    "not_performed",
    "not_applicable",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def safe_run_id(value: str) -> str:
    require(bool(RUN_ID_RE.fullmatch(value)), f"invalid UTC run ID: {value!r}")
    return value


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def path_record(path: Path, *, with_schema: bool = False) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if path.suffix == ".parquet":
        parquet = pq.ParquetFile(path)
        record["rows"] = parquet.metadata.num_rows
        if with_schema:
            record["schema"] = str(parquet.schema_arrow)
            record["columns"] = parquet.schema_arrow.names
    else:
        record["rows"] = None
    return record


def tree_record(path: Path, *, with_schema: bool = False) -> dict[str, Any]:
    if path.is_file():
        return path_record(path, with_schema=with_schema)
    files = []
    total_bytes = 0
    total_rows = 0
    schemas: set[str] = set()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        item = path_record(child, with_schema=with_schema)
        item["relative_path"] = child.relative_to(path).as_posix()
        files.append(item)
        total_bytes += int(item["bytes"])
        if item["rows"] is not None:
            total_rows += int(item["rows"])
        if "schema" in item:
            schemas.add(str(item["schema"]))
    digest_rows = [
        {"relative_path": item["relative_path"], "bytes": item["bytes"], "sha256": item["sha256"]}
        for item in files
    ]
    record = {
        "path": str(path.resolve()),
        "bytes": total_bytes,
        "rows": total_rows,
        "sha256": canonical_sha256(digest_rows),
        "hash_basis": "canonical_relative_file_inventory",
        "files": files,
    }
    if with_schema:
        record["schemas"] = sorted(schemas)
    return record


def encode_tsv_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def decode_tsv_value(value: str) -> Any:
    return json.loads(value)


def write_contract_tsv(path: Path, records: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CONTRACT_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for record in records:
            require(set(record) == set(CONTRACT_FIELDS), f"contract fields differ: {record.get('contract_item_id')}")
            writer.writerow({key: encode_tsv_value(record[key]) for key in CONTRACT_FIELDS})


def read_contract_tsv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        require(tuple(reader.fieldnames or ()) == CONTRACT_FIELDS, "contract TSV header mismatch")
        return [{key: decode_tsv_value(value) for key, value in row.items()} for row in reader]


def nmad(values: Iterable[float]) -> float | None:
    array = np.asarray(list(values), dtype=np.float64)
    if array.size == 0:
        return None
    median = float(np.median(array))
    return float(1.4826 * np.median(np.abs(array - median)))


def exact_median(values: Iterable[float]) -> float | None:
    array = np.asarray(list(values), dtype=np.float64)
    return None if array.size == 0 else float(np.median(array))


def one_min_cell(lon_deg: float, lat_deg: float) -> tuple[int, int, str, float, float]:
    require(math.isfinite(lon_deg) and -180.0 <= lon_deg < 180.0, "longitude outside frozen range")
    require(math.isfinite(lat_deg) and -90.0 <= lat_deg <= 90.0, "latitude outside frozen range")
    lon_bin = math.floor((lon_deg + 180.0) * 60.0)
    lat_bin = math.floor((lat_deg + 90.0) * 60.0)
    cell_id = f"1min_{lat_bin}_{lon_bin}"
    lon_center = -180.0 + (lon_bin + 0.5) / 60.0
    lat_center = -90.0 + (lat_bin + 0.5) / 60.0
    return lon_bin, lat_bin, cell_id, lon_center, lat_center


def output_manifest(directory: Path, names: Iterable[str]) -> dict[str, dict[str, Any]]:
    return {name: path_record(directory / name, with_schema=name.endswith(".parquet")) for name in names}
