#!/usr/bin/env python3
"""Independently verify an immutable SCS confirmation Stage A.1 run."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
NCEI_HOST = "data.ngdc.noaa.gov"
FIELD_STATUSES = {
    "known",
    "officially_unknown",
    "not_recoverable",
    "inferred_from_filename",
    "verified_from_source_metadata",
}
REQUIRED_OUTPUTS = {
    "physical_object_lock": "physical_object_lock.parquet",
    "per_cruise_byte_budget": "per_cruise_byte_budget.tsv",
    "revised_candidate_registry": "revised_candidate_registry.parquet",
    "revised_preseal_lock": "revised_preseal_lock.json",
    "metadata_evidence_registry": "metadata_evidence_registry.tsv",
    "query_command_ledger": "query_command_ledger.jsonl",
    "negative_result_ledger": "negative_result_ledger.tsv",
    "audit_report": "audit_report.md",
}
REQUIRED_PHYSICAL_COLUMNS = {
    "official_cruise_id", "filename", "direct_url", "resolved_url",
    "content_length", "etag", "last_modified", "format", "role",
    "head_status", "head_http_status", "listing_url", "object_body_read",
    "range_header_sent", "selection_rank",
}
REQUIRED_REVISED_COLUMNS = {
    "official_cruise_id", "date", "scs_track_length_km",
    "stage_a1_comparison_cohort", "stage_a1_selection_rule",
    "chronology_risk", "confirmation_candidate_v2_H_MRAR_out",
    "confirmation_candidate_v2_W_MRAR_in", "confirmation_role_eligible",
    "physical_object_count", "physical_total_bytes", "physical_lock_status",
    "selection_rank",
}


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def atomic_json(value: Any, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def dataframe_schema(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {"name": column, "dtype": str(frame[column].dtype), "nullable": bool(frame[column].isna().any())}
        for column in frame.columns
    ]


def check_status_pairs(frame: pd.DataFrame, name: str) -> int:
    status_columns = {
        column for column in frame.columns
        if column.endswith("_status") and column.removesuffix("_status") in frame.columns
    }
    missing: list[str] = []
    invalid: dict[str, list[str]] = {}
    for column in frame.columns:
        if column in status_columns:
            values = sorted(set(frame[column].dropna().astype(str)) - FIELD_STATUSES)
            if values:
                invalid[column] = values
        elif f"{column}_status" not in frame.columns:
            missing.append(column)
    if missing or invalid:
        raise AssertionError(f"{name} status-pair failure: missing={missing}, invalid={invalid}")
    return len(status_columns)


def parse_date_bounds(value: Any) -> tuple[datetime | None, datetime | None]:
    parts = str(value or "").split("/", maxsplit=1)
    try:
        start = datetime.fromisoformat(parts[0]).replace(tzinfo=timezone.utc)
    except ValueError:
        start = None
    try:
        end = datetime.fromisoformat(parts[-1]).replace(tzinfo=timezone.utc)
    except ValueError:
        end = start
    return start, end


def rank_key(row: Any, cutoff: str) -> tuple[Any, ...]:
    _, end = parse_date_bounds(row.date)
    cutoff_dt = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    return (
        0 if end and end > cutoff_dt else 1,
        -end.timestamp() if end else float("inf"),
        -float(row.scs_track_length_km),
        str(row.official_cruise_id),
    )


def official_directory(url: str) -> bool:
    parsed = urllib.parse.urlparse(str(url))
    return parsed.scheme == "https" and parsed.hostname == NCEI_HOST and parsed.path.endswith("/") and not parsed.query


def recompute_comparison(original: pd.DataFrame, minimum_year: int, cutoff: str) -> list[str]:
    rows = []
    for row in original.itertuples(index=False):
        start, _ = parse_date_bounds(row.date)
        if not start or start.year < minimum_year:
            continue
        if row.ever_read_by_repo != "false":
            continue
        if row.overlap_with_current_19 != "false" or row.overlap_with_exposed_12 != "false":
            continue
        if not bool(row.geometry_intersects_scs) or not official_directory(row.archive):
            continue
        rows.append(row)
    rows.sort(key=lambda row: rank_key(row, cutoff))
    return [str(row.official_cruise_id) for row in rows]


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def listing_links(body: bytes, listing_url: str, root_url: str) -> tuple[set[str], set[str]]:
    parser = LinkParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    root_path = urllib.parse.urlparse(root_url).path
    directories: set[str] = set()
    objects: set[str] = set()
    for href in parser.hrefs:
        if href.startswith(("?", "#")):
            continue
        absolute = urllib.parse.urljoin(listing_url, href)
        parsed = urllib.parse.urlparse(absolute)
        if (
            parsed.scheme != "https"
            or parsed.hostname != NCEI_HOST
            or parsed.query
            or parsed.fragment
            or not parsed.path.startswith(root_path)
        ):
            continue
        normalized = urllib.parse.urlunparse(parsed._replace(query="", fragment=""))
        if normalized in {listing_url, root_url.rstrip("/")}:
            continue
        if parsed.path.endswith("/"):
            directories.add(normalized)
        else:
            objects.add(normalized)
    return directories, objects


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verify_source_guard() -> dict[str, Any]:
    path = REPO_ROOT / "ncei/code/discover_scs_v2_sealed_confirmation_stage_a1.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "head_physical_object")
    segment = ast.get_source_segment(source, function) or ""
    if 'method="HEAD"' not in segment or 'method="GET"' in segment or '"Range"' in segment or "response.read" in segment:
        raise AssertionError("physical-object HEAD implementation violates the no-body/no-Range source guard")
    forbidden_imports = {"xarray", "netCDF4", "zipfile", "tarfile", "rarfile", "py7zr", "libarchive"}
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    if imports & forbidden_imports:
        raise AssertionError(f"forbidden data/archive reader imports: {sorted(imports & forbidden_imports)}")
    return {"path": str(path), "sha256": sha256_file(path)}


def verify_stage_a1(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    verification_path = run_dir / "verification.json"
    if verification_path.exists():
        raise FileExistsError(f"immutable verification already exists: {verification_path}")
    manifest_path = run_dir / "audit_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("stage") != "A.1_metadata_file_list_and_head_only":
        raise AssertionError("unexpected manifest stage")
    if set(REQUIRED_OUTPUTS) - set(manifest.get("outputs", {})):
        raise AssertionError("manifest is missing required Stage A.1 outputs")
    checks: dict[str, Any] = {}
    for name, filename in REQUIRED_OUTPUTS.items():
        path = run_dir / filename
        record = manifest["outputs"][name]
        if Path(record["path"]) != path or sha256_file(path) != record["sha256"] or path.stat().st_size != record["bytes"]:
            raise AssertionError(f"manifest output mismatch: {name}")
    checks["manifest_output_hashes"] = len(REQUIRED_OUTPUTS)

    config_path = Path(manifest["config"]["path"])
    if sha256_file(config_path) != manifest["config"]["sha256"]:
        raise AssertionError("config hash mismatch")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    for name, record in manifest["accepted_stage_a_inputs"].items():
        if sha256_file(Path(record["path"])) != record["sha256"]:
            raise AssertionError(f"accepted Stage A input changed: {name}")
    original_path = Path(manifest["accepted_stage_a_inputs"]["candidate_registry"]["path"])
    original = pd.read_parquet(original_path)
    expected_ids = recompute_comparison(
        original,
        int(config["selection"]["minimum_start_year"]),
        str(config["selection"]["mrar_delivery_cutoff_utc"]),
    )
    required_ids = set(map(str, config["selection"]["required_report_ids"]))
    if not required_ids.issubset(set(expected_ids)):
        raise AssertionError("required named candidates are absent from recomputed comparison cohort")
    checks["recomputed_chronology_first_comparison_ids"] = expected_ids

    physical = pd.read_parquet(run_dir / "physical_object_lock.parquet")
    budgets = pd.read_csv(run_dir / "per_cruise_byte_budget.tsv", sep="\t", keep_default_na=False)
    revised = pd.read_parquet(run_dir / "revised_candidate_registry.parquet")
    evidence = pd.read_csv(run_dir / "metadata_evidence_registry.tsv", sep="\t")
    negatives = pd.read_csv(run_dir / "negative_result_ledger.tsv", sep="\t", keep_default_na=False)
    queries = read_jsonl(run_dir / "query_command_ledger.jsonl")
    if not REQUIRED_PHYSICAL_COLUMNS.issubset(physical.columns):
        raise AssertionError("physical object lock schema is incomplete")
    if not REQUIRED_REVISED_COLUMNS.issubset(revised.columns):
        raise AssertionError("revised candidate registry schema is incomplete")
    checks["physical_status_pairs"] = check_status_pairs(physical, "physical_object_lock")
    checks["budget_status_pairs"] = check_status_pairs(budgets, "per_cruise_byte_budget")
    checks["revised_status_pairs"] = check_status_pairs(revised, "revised_candidate_registry")
    for name, frame in (("physical_object_lock", physical), ("per_cruise_byte_budget", budgets), ("revised_candidate_registry", revised), ("metadata_evidence_registry", evidence)):
        if dataframe_schema(frame) != manifest["outputs"][name]["schema"]:
            raise AssertionError(f"persisted schema mismatch: {name}")
        if len(frame) != manifest["outputs"][name]["row_count"]:
            raise AssertionError(f"persisted row count mismatch: {name}")

    selected = revised[revised["stage_a1_comparison_cohort"]].sort_values("selection_rank")
    actual_ids = selected["official_cruise_id"].astype(str).tolist()
    if actual_ids != expected_ids:
        raise AssertionError(f"chronology-first selected set mismatch: actual={actual_ids}, expected={expected_ids}")
    if revised["stage_a1_selection_rule"].ne("all_2018plus_unexposed_candidates_no_count_cap").any():
        raise AssertionError("revised registry does not freeze the no-count-cap selection rule")
    if revised["confirmation_role_eligible"].astype(bool).any():
        raise AssertionError("global confirmation_role_eligible must remain false")
    if selected["confirmation_candidate_v2_H_MRAR_out"].ne("pending_seal_and_processing").any():
        raise AssertionError("v2-H branch status mismatch")
    if selected["confirmation_candidate_v2_W_MRAR_in"].ne("blocked_source_independence_unknown").any():
        raise AssertionError("v2-W branch status mismatch")
    checks["branch_contract_and_global_ceiling"] = True

    if physical["direct_url"].duplicated().any():
        raise AssertionError("duplicate physical object URL")
    if physical["object_body_read"].astype(bool).any() or physical["range_header_sent"].astype(bool).any():
        raise AssertionError("physical lock records a prohibited body or Range access")
    for url in physical["direct_url"].astype(str):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != NCEI_HOST or parsed.path.endswith("/"):
            raise AssertionError(f"invalid physical object URL: {url}")

    head_queries = [row for row in queries if row["method"] == "HEAD"]
    get_queries = [row for row in queries if row["method"] == "GET"]
    if len(head_queries) != len(physical):
        raise AssertionError("HEAD query count does not equal physical object count")
    if {row["url"] for row in head_queries} != set(physical["direct_url"].astype(str)):
        raise AssertionError("HEAD query URL set does not close against physical object lock")
    if any(row["body_read"] or row["range_header_sent"] or row["response_bytes"] != 0 for row in head_queries):
        raise AssertionError("HEAD ledger records body/Range access")
    if any(row["request_role"] != "official_cruise_file_list_metadata" or not official_directory(row["url"]) for row in get_queries):
        raise AssertionError("GET ledger contains a non-directory or non-metadata request")
    if any(row["range_header_sent"] for row in get_queries):
        raise AssertionError("GET ledger contains a Range request")
    if set(row["url"] for row in get_queries) & set(physical["direct_url"].astype(str)):
        raise AssertionError("a physical object URL was requested with GET")
    checks["network_methods"] = {
        "directory_metadata_get": len(get_queries),
        "physical_object_head": len(head_queries),
        "physical_object_get": 0,
        "range_get": 0,
        "physical_object_body_read": 0,
    }

    for row in evidence.itertuples(index=False):
        path = Path(row.path)
        if sha256_file(path) != row.sha256 or path.stat().st_size != int(row.bytes):
            raise AssertionError(f"metadata evidence hash mismatch: {path}")
        if "text/html" not in str(row.mime_type).lower() and "application/xhtml+xml" not in str(row.mime_type).lower():
            raise AssertionError(f"non-HTML file-list evidence: {path}")
    manifest_evidence = manifest.get("metadata_evidence", {})
    if len(manifest_evidence) != len(evidence):
        raise AssertionError("manifest metadata evidence count mismatch")
    checks["metadata_evidence_hashes"] = len(evidence)

    roots = dict(zip(selected["official_cruise_id"].astype(str), selected["archive"].astype(str)))
    attempted_directories = {row["url"] for row in get_queries}
    reconstructed_objects: set[str] = set()
    reconstructed_directories: set[str] = set()
    for row in evidence.itertuples(index=False):
        root_url = roots[str(row.official_cruise_id)]
        directories, objects = listing_links(Path(row.path).read_bytes(), str(row.requested_url), root_url)
        reconstructed_directories.update(directories)
        reconstructed_objects.update(objects)
    if not reconstructed_directories.issubset(attempted_directories):
        missing = sorted(reconstructed_directories - attempted_directories)[:10]
        raise AssertionError(f"directory enumeration stopped without recorded attempts: {missing}")
    if reconstructed_objects != set(physical["direct_url"].astype(str)):
        raise AssertionError("reconstructed file-list object set differs from physical lock")
    checks["reconstructed_physical_object_urls"] = len(reconstructed_objects)

    incomplete_urls = set(physical.loc[
        physical["head_status"].ne("success") | physical["content_length"].isna(),
        "direct_url",
    ].astype(str))
    recorded_incomplete_urls = set(negatives.loc[
        negatives["category"].isin(["physical_object_head", "physical_object_content_length"]),
        "evidence",
    ].astype(str))
    if incomplete_urls != recorded_incomplete_urls:
        raise AssertionError("negative ledger does not close against HEAD/Content-Length failures")
    checks["physical_lock_negative_ledger_closure"] = len(incomplete_urls)

    cruise_budgets = budgets[budgets["row_type"].eq("cruise")].copy()
    if cruise_budgets["official_cruise_id"].astype(str).tolist() != expected_ids:
        raise AssertionError("per-cruise budget order differs from selected order")
    for budget in cruise_budgets.itertuples(index=False):
        subset = physical[physical["official_cruise_id"].eq(budget.official_cruise_id)]
        expected_count = len(subset)
        expected_head_ok = int(subset["head_status"].eq("success").sum())
        expected_lengths = int(subset["content_length"].notna().sum())
        expected_bytes = int(subset["content_length"].dropna().sum())
        if (
            int(budget.physical_object_count) != expected_count
            or int(budget.head_ok_count) != expected_head_ok
            or int(budget.head_failed_count) != expected_count - expected_head_ok
            or int(budget.content_length_known_count) != expected_lengths
            or int(budget.total_bytes) != expected_bytes
        ):
            raise AssertionError(f"byte-budget mismatch for {budget.official_cruise_id}")
        if budget.physical_lock_status != "closed_metadata_head_lock" and bool(budget.stage_b_authorized):
            raise AssertionError("incomplete physical lock cannot authorize Stage B")
    all_row = budgets[budgets["row_type"].eq("all_candidates")]
    if len(all_row) != 1:
        raise AssertionError("exactly one all-candidates byte-budget row is required")
    all_record = all_row.iloc[0]
    if (
        int(all_record["physical_object_count"]) != len(physical)
        or int(all_record["head_ok_count"]) != int(physical["head_status"].eq("success").sum())
        or int(all_record["content_length_known_count"]) != int(physical["content_length"].notna().sum())
        or int(all_record["total_bytes"]) != int(physical["content_length"].dropna().sum())
    ):
        raise AssertionError("all-candidates byte budget mismatch")
    checks["byte_budgets_recomputed"] = len(cruise_budgets) + 1

    lock = json.loads((run_dir / "revised_preseal_lock.json").read_text(encoding="utf-8"))
    if lock.get("stage_b_authorized") is not False:
        raise AssertionError("Stage B must remain unauthorized")
    if lock.get("selected_count") != len(expected_ids):
        raise AssertionError("revised preseal selected count mismatch")
    if [row["official_cruise_id"] for row in lock["selected_candidates"]] != expected_ids:
        raise AssertionError("revised preseal candidate order mismatch")
    zero_guards = (
        "physical_object_get_count", "range_get_count", "physical_object_body_read_count",
        "cell_generation_count", "reference_or_model_comparison_count",
    )
    if any(lock.get(key) != 0 for key in zero_guards) or lock.get("candidate_depth_read") is not False:
        raise AssertionError("revised preseal prohibited-action counter is nonzero")
    if lock.get("mrar_terminal") != {"identity_status": "not_recoverable", "source_independence": "unknown"}:
        raise AssertionError("MRAR terminal state changed without direct evidence")
    if lock.get("bulk_package_alternative", {}).get("external_message_sent") is not False:
        raise AssertionError("external bulk-package message must not be sent")
    checks["preseal_guards"] = True
    checks["source_guard"] = verify_source_guard()

    if manifest.get("prohibited_actions") != {
        "stage_b_authorized": False,
        "physical_object_get_count": 0,
        "range_get_count": 0,
        "candidate_depth_read": False,
        "cell_generation_count": 0,
        "reference_or_model_comparison_count": 0,
        "external_message_count": 0,
    }:
        raise AssertionError("manifest prohibited-action contract mismatch")
    result = {
        "schema_version": 1,
        "run_id": manifest["run_id"],
        "stage": manifest["stage"],
        "status": "pass",
        "verified_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "checks": checks,
        "summary": {
            "accepted_registry_rows": len(original),
            "comparison_candidate_count": len(expected_ids),
            "physical_object_count": len(physical),
            "head_ok_count": int(physical["head_status"].eq("success").sum()),
            "content_length_known_count": int(physical["content_length"].notna().sum()),
            "known_total_bytes": int(physical["content_length"].dropna().sum()),
            "global_confirmation_role_eligible": False,
            "stage_b_authorized": False,
        },
    }
    atomic_json(result, verification_path)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    result = verify_stage_a1(parse_args().run_dir)
    print(stable_json({
        "status": result["status"],
        "run_id": result["run_id"],
        "manifest_sha256": result["manifest_sha256"],
        "physical_object_count": result["summary"]["physical_object_count"],
        "stage_b_authorized": False,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
