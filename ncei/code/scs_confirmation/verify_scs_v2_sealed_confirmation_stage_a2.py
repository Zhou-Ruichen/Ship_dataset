#!/usr/bin/env python3
"""Independently verify an offline SCS confirmation Stage A.2 final lock."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
PRIMARY_IDS = ["EQT20210702", "EQT190012", "EQT180002", "TN352"]
DEFERRED_OR_EXCLUDED = ["SR1912", "TN359", "TN358", "TN354"]
DOWNLOAD_CAP_BYTES = 12 * 1024**3
FIELD_STATUSES = {
    "known",
    "officially_unknown",
    "not_recoverable",
    "inferred_from_filename",
    "verified_from_source_metadata",
}
REQUIRED_OUTPUTS = {
    "primary_physical_object_lock": "primary_physical_object_lock.parquet",
    "primary_cruise_budget": "primary_cruise_budget.tsv",
    "candidate_decision_registry": "candidate_decision_registry.tsv",
    "stage_b_dry_run_plan": "stage_b_dry_run_plan.tsv",
    "final_download_lock": "final_download_lock.json",
    "audit_report": "audit_report.md",
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
            unexpected = sorted(set(frame[column].dropna().astype(str)) - FIELD_STATUSES)
            if unexpected:
                invalid[column] = unexpected
        elif f"{column}_status" not in frame.columns:
            missing.append(column)
    if missing or invalid:
        raise AssertionError(f"{name} status-pair failure: missing={missing}, invalid={invalid}")
    return len(status_columns)


class ListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple[str, list[str]]] = []
        self.in_row = False
        self.in_cell = False
        self.href = ""
        self.cell: list[str] = []
        self.cells: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self.in_row = True
            self.href = ""
            self.cells = []
        elif tag == "td" and self.in_row:
            self.in_cell = True
            self.cell = []
        elif tag == "a" and self.in_row:
            for key, value in attrs:
                if key.lower() == "href" and value:
                    self.href = value

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "td" and self.in_cell:
            self.cells.append("".join(self.cell).strip())
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.href:
                self.rows.append((self.href, list(self.cells)))
            self.in_row = False


def exact_listing_sizes(evidence_registry: pd.DataFrame) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in evidence_registry.itertuples(index=False):
        path = Path(row.path)
        if path.stat().st_size != int(row.bytes) or sha256_file(path) != row.sha256:
            raise AssertionError(f"frozen listing evidence mismatch: {path}")
        parser = ListingParser()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        for href, cells in parser.rows:
            if not cells or not re.fullmatch(r"\d+", cells[-1].strip()):
                continue
            url = urllib.parse.urljoin(str(row.requested_url), href)
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme != "https" or parsed.hostname != "data.ngdc.noaa.gov" or parsed.path.endswith("/"):
                continue
            record = {
                "bytes": int(cells[-1].strip()),
                "path": str(path),
                "sha256": str(row.sha256),
            }
            if url in result and result[url] != record:
                raise AssertionError(f"conflicting exact listing size: {url}")
            result[url] = record
    return result


def verify_source_guards() -> dict[str, Any]:
    producer_path = REPO_ROOT / "ncei/code/scs_confirmation/finalize_scs_v2_sealed_confirmation_stage_a2.py"
    producer_source = producer_path.read_text(encoding="utf-8")
    if "urllib.request" in producer_source or "urlopen" in producer_source:
        raise AssertionError("Stage A.2 producer contains a network request path")
    downloader_path = REPO_ROOT / "ncei/code/scs_confirmation/acquire_scs_v2_sealed_confirmation_stage_b.py"
    downloader_source = downloader_path.read_text(encoding="utf-8")
    tree = ast.parse(downloader_source)
    dry_run = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_dry_run")
    segment = ast.get_source_segment(downloader_source, dry_run) or ""
    if "urlopen" in segment or "Request(" in segment:
        raise AssertionError("Stage B dry-run contains a network request")
    authorization = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "validate_authorization_receipt")
    execute = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "execute_stage_b")
    execute_segment = ast.get_source_segment(downloader_source, execute) or ""
    if "validate_authorization_receipt" not in execute_segment:
        raise AssertionError("Stage B execution is not gated by a separate authorization receipt")
    return {
        "stage_a2_producer_sha256": sha256_file(producer_path),
        "stage_b_downloader_sha256": sha256_file(downloader_path),
        "authorization_guard_function": authorization.name,
    }


def verify_stage_a2(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    verification_path = run_dir / "verification.json"
    if verification_path.exists():
        raise FileExistsError(f"immutable verification already exists: {verification_path}")
    manifest_path = run_dir / "audit_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("stage") != "A.2_offline_final_download_lock":
        raise AssertionError("unexpected Stage A.2 manifest stage")
    if set(REQUIRED_OUTPUTS) - set(manifest.get("outputs", {})):
        raise AssertionError("Stage A.2 manifest is missing required outputs")
    checks: dict[str, Any] = {}
    for name, filename in REQUIRED_OUTPUTS.items():
        path = run_dir / filename
        record = manifest["outputs"][name]
        if Path(record["path"]) != path or path.stat().st_size != record["bytes"] or sha256_file(path) != record["sha256"]:
            raise AssertionError(f"Stage A.2 output mismatch: {name}")
    checks["manifest_output_hashes"] = len(REQUIRED_OUTPUTS)

    config_path = Path(manifest["config"]["path"])
    if sha256_file(config_path) != manifest["config"]["sha256"]:
        raise AssertionError("Stage A.2 config hash mismatch")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config["primary_acquisition"]["immutable_cruise_ids"] != PRIMARY_IDS:
        raise AssertionError("primary acquisition IDs are not exact and ordered")
    if int(config["primary_acquisition"]["aggregate_download_cap_bytes"]) != DOWNLOAD_CAP_BYTES:
        raise AssertionError("download cap is not exactly 12 GiB")
    if set(config["decisions"]) != set(DEFERRED_OR_EXCLUDED):
        raise AssertionError("excluded/deferred set mismatch")
    for name, record in manifest["accepted_stage_a1_inputs"].items():
        if sha256_file(Path(record["path"])) != record["sha256"]:
            raise AssertionError(f"accepted Stage A.1 input changed: {name}")
    a1_verification = json.loads(Path(manifest["accepted_stage_a1_inputs"]["verification"]["path"]).read_text(encoding="utf-8"))
    if a1_verification.get("status") != "pass":
        raise AssertionError("accepted Stage A.1 verification is not pass")
    checks["accepted_stage_a1_hashes"] = len(manifest["accepted_stage_a1_inputs"])

    primary = pd.read_parquet(run_dir / "primary_physical_object_lock.parquet")
    budget = pd.read_csv(run_dir / "primary_cruise_budget.tsv", sep="\t", keep_default_na=False)
    decisions = pd.read_csv(run_dir / "candidate_decision_registry.tsv", sep="\t", keep_default_na=False)
    plan = pd.read_csv(
        run_dir / "stage_b_dry_run_plan.tsv",
        sep="\t",
        keep_default_na=False,
        dtype={"expected_bytes": "Int64"},
    )
    for name, frame in (
        ("primary_physical_object_lock", primary),
        ("primary_cruise_budget", budget),
        ("candidate_decision_registry", decisions),
        ("stage_b_dry_run_plan", plan),
    ):
        if dataframe_schema(frame) != manifest["outputs"][name]["schema"]:
            raise AssertionError(f"persisted schema mismatch: {name}")
        if len(frame) != manifest["outputs"][name]["row_count"]:
            raise AssertionError(f"persisted row count mismatch: {name}")
    checks["primary_status_pairs"] = check_status_pairs(primary, "primary_physical_object_lock")
    checks["budget_status_pairs"] = check_status_pairs(budget, "primary_cruise_budget")
    checks["decision_status_pairs"] = check_status_pairs(decisions, "candidate_decision_registry")

    a1_physical = pd.read_parquet(Path(manifest["accepted_stage_a1_inputs"]["physical_object_lock"]["path"]))
    expected_a1 = a1_physical[a1_physical["official_cruise_id"].isin(PRIMARY_IDS)].sort_values(
        ["official_cruise_id", "direct_url"]
    )
    if set(primary["direct_url"].astype(str)) != set(expected_a1["direct_url"].astype(str)):
        raise AssertionError("primary physical URL set differs from the exact four-cruise A.1 subset")
    if set(primary["official_cruise_id"].astype(str)) != set(PRIMARY_IDS):
        raise AssertionError("primary lock contains an unexpected cruise")
    rank_map = {cruise_id: index + 1 for index, cruise_id in enumerate(PRIMARY_IDS)}
    if any(int(row.primary_rank) != rank_map[str(row.official_cruise_id)] for row in primary.itertuples(index=False)):
        raise AssertionError("primary rank mismatch")

    evidence_registry = pd.read_csv(Path(manifest["accepted_stage_a1_inputs"]["metadata_evidence_registry"]["path"]), sep="\t")
    listing_sizes = exact_listing_sizes(evidence_registry)
    a1_by_url = a1_physical.set_index("direct_url")
    listing_recoveries: list[str] = []
    for row in primary.itertuples(index=False):
        source = a1_by_url.loc[row.direct_url]
        if pd.isna(source.content_length):
            evidence = listing_sizes.get(row.direct_url)
            if evidence is None or int(row.bytes) != int(evidence["bytes"]):
                raise AssertionError(f"listing size recovery mismatch: {row.direct_url}")
            if row.bytes_source != "official_directory_listing_exact_integer":
                raise AssertionError("missing HEAD length was not labeled as listing recovery")
            if row.bytes_evidence_path != evidence["path"] or row.bytes_evidence_sha256 != evidence["sha256"]:
                raise AssertionError("listing recovery evidence path/hash mismatch")
            listing_recoveries.append(row.direct_url)
        else:
            if int(row.bytes) != int(source.content_length) or row.bytes_source != "head_content_length":
                raise AssertionError(f"HEAD Content-Length transfer mismatch: {row.direct_url}")
        if row.confirmation_role_eligible:
            raise AssertionError("global confirmation role must remain false")
        if row.vertical_datum_status != "officially_unknown":
            raise AssertionError("vertical datum status was improperly promoted")
    expected_recovery_names = {
        "0126_20180425_004502_TGT.all.mb58.fnv",
        "0127_20180425_011502_TGT.all.mb58.fnv",
    }
    if set(primary.loc[primary["direct_url"].isin(listing_recoveries), "filename"].astype(str)) != expected_recovery_names:
        raise AssertionError("TN352 exact listing recovery set mismatch")
    if any(int(primary.loc[primary["direct_url"].eq(url), "bytes"].iloc[0]) != 0 for url in listing_recoveries):
        raise AssertionError("TN352 recovered listing sizes are not exact zero bytes")
    checks["exact_listing_size_recoveries"] = len(listing_recoveries)

    cruise_budget = budget[budget["row_type"].eq("cruise")]
    if cruise_budget["official_cruise_id"].astype(str).tolist() != PRIMARY_IDS:
        raise AssertionError("per-cruise budget order mismatch")
    for row in cruise_budget.itertuples(index=False):
        subset = primary[primary["official_cruise_id"].eq(row.official_cruise_id)]
        if (
            int(row.physical_object_count) != len(subset)
            or int(row.bytes_known_count) != int(subset["bytes"].notna().sum())
            or int(row.total_bytes) != int(subset["bytes"].sum())
            or not bool(row.total_bytes_complete)
        ):
            raise AssertionError(f"primary cruise budget mismatch: {row.official_cruise_id}")
    total_row = budget[budget["row_type"].eq("all_primary")]
    if len(total_row) != 1:
        raise AssertionError("one all-primary budget row is required")
    total = total_row.iloc[0]
    expected_total = int(primary["bytes"].sum())
    expected_track = float(cruise_budget["scs_track_length_km"].sum())
    if (
        expected_total != 9_626_893_507
        or int(total["total_bytes"]) != expected_total
        or int(total["download_cap_bytes"]) != DOWNLOAD_CAP_BYTES
        or not bool(total["within_download_cap"])
        or abs(float(total["scs_track_length_km"]) - expected_track) > 1e-9
    ):
        raise AssertionError("all-primary budget/cap mismatch")
    checks["primary_budget"] = {
        "objects": len(primary),
        "bytes": expected_total,
        "track_length_km": expected_track,
        "cap_bytes": DOWNLOAD_CAP_BYTES,
    }

    if decisions["official_cruise_id"].astype(str).tolist() != PRIMARY_IDS + DEFERRED_OR_EXCLUDED:
        raise AssertionError("candidate decision order/set mismatch")
    decision_map = decisions.set_index("official_cruise_id")
    for cruise_id in PRIMARY_IDS:
        if decision_map.loc[cruise_id, "decision"] != "primary_acquisition":
            raise AssertionError(f"primary decision mismatch: {cruise_id}")
    for cruise_id in DEFERRED_OR_EXCLUDED:
        expected = config["decisions"][cruise_id]
        if decision_map.loc[cruise_id, "decision"] != expected["decision"] or decision_map.loc[cruise_id, "reason"] != expected["reason"]:
            raise AssertionError(f"excluded/deferred decision mismatch: {cruise_id}")
    if decisions["replacement_allowed"].astype(bool).any() or decisions["model_or_product_result_used"].astype(bool).any():
        raise AssertionError("decision registry allows replacement or model/product selection")
    checks["candidate_decisions"] = len(decisions)

    if len(plan) != len(primary) or set(plan["direct_url"].astype(str)) != set(primary["direct_url"].astype(str)):
        raise AssertionError("Stage B dry-run plan does not close against primary lock")
    if plan["relative_destination"].duplicated().any():
        raise AssertionError("Stage B dry-run destinations are not unique")
    if plan["download_executed"].astype(bool).any() or plan["dry_run_status"].ne("planned_not_authorized").any():
        raise AssertionError("Stage B plan records an executed download")
    for row in plan.itertuples(index=False):
        root = f"objects/{row.official_cruise_id}/"
        if not str(row.relative_destination).startswith(root):
            raise AssertionError(f"dry-run destination escaped cruise root: {row.relative_destination}")
    checks["stage_b_dry_run_plan"] = len(plan)

    final_lock_path = run_dir / "final_download_lock.json"
    final_lock = json.loads(final_lock_path.read_text(encoding="utf-8"))
    if final_lock["immutable_primary_confirmation_cruise_ids"] != PRIMARY_IDS:
        raise AssertionError("final lock primary IDs mismatch")
    if final_lock["primary_physical_object_lock_sha256"] != sha256_file(run_dir / "primary_physical_object_lock.parquet"):
        raise AssertionError("final lock physical object hash mismatch")
    if final_lock["stage_b_dry_run_plan_sha256"] != sha256_file(run_dir / "stage_b_dry_run_plan.tsv"):
        raise AssertionError("final lock dry-run plan hash mismatch")
    if (
        final_lock["stage_b_authorized"] is not False
        or final_lock["stage_b_dry_run_only"] is not True
        or final_lock["maximum_post_download_role"] != "sealed_unprocessed"
        or final_lock["stage_c_required_before_processing"] is not True
        or final_lock["candidate_replacement_allowed"] is not False
    ):
        raise AssertionError("final lock authorization/role ceiling mismatch")
    if final_lock["branch_contract"] != {
        "confirmation_candidate_v2_H_MRAR_out": "pending_seal_and_processing",
        "confirmation_candidate_v2_W_MRAR_in": "blocked_source_independence_unknown",
        "global_confirmation_role_eligible": False,
    }:
        raise AssertionError("final lock branch contract mismatch")
    zero_keys = (
        "network_access_count", "physical_object_download_count", "physical_object_body_read_count",
        "range_get_count", "archive_parse_count", "cell_generation_count",
        "reference_or_model_comparison_count", "external_message_count",
    )
    if any(final_lock[key] != 0 for key in zero_keys) or final_lock["candidate_depth_read"] is not False:
        raise AssertionError("final lock contains a prohibited Stage A.2 action")
    checks["final_download_lock"] = True
    checks["source_guards"] = verify_source_guards()

    expected_prohibited = {
        "stage_b_authorized": False,
        "network_access_count": 0,
        "physical_object_download_count": 0,
        "physical_object_body_read_count": 0,
        "range_get_count": 0,
        "candidate_depth_read": False,
        "archive_parse_count": 0,
        "cell_generation_count": 0,
        "reference_or_model_comparison_count": 0,
        "candidate_replacement_count": 0,
        "external_message_count": 0,
    }
    if manifest["prohibited_actions"] != expected_prohibited:
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
            "primary_cruise_ids": PRIMARY_IDS,
            "primary_cruise_count": len(PRIMARY_IDS),
            "physical_object_count": len(primary),
            "exact_total_bytes": expected_total,
            "aggregate_download_cap_bytes": DOWNLOAD_CAP_BYTES,
            "within_download_cap": True,
            "official_scs_track_length_km": expected_track,
            "tn352_listing_size_recovery_count": len(listing_recoveries),
            "stage_b_dry_run_only": True,
            "stage_b_authorized": False,
            "global_confirmation_role_eligible": False,
            "maximum_post_download_role": "sealed_unprocessed",
        },
    }
    atomic_json(result, verification_path)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    result = verify_stage_a2(parse_args().run_dir)
    print(stable_json({
        "status": result["status"],
        "run_id": result["run_id"],
        "manifest_sha256": result["manifest_sha256"],
        "primary_cruise_ids": result["summary"]["primary_cruise_ids"],
        "exact_total_bytes": result["summary"]["exact_total_bytes"],
        "stage_b_authorized": False,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
