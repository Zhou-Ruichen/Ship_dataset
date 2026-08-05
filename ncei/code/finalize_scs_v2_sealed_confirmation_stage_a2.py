#!/usr/bin/env python3
"""Create the offline immutable SCS confirmation Stage A.2 download lock.

Stage A.2 reads only the accepted Stage A.1 receipt and its frozen official
directory HTML. It selects the exact four-cruise primary acquisition set,
recovers only exact integer listing sizes, freezes a 12 GiB cap, and emits a
Stage B dry-run plan. It performs no network request or physical-object read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any

import pandas as pd
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z$")
PRIMARY_IDS = ["EQT20210702", "EQT190012", "EQT180002", "TN352"]
DOWNLOAD_CAP_BYTES = 12 * 1024**3
FIELD_STATUSES = {
    "known",
    "officially_unknown",
    "not_recoverable",
    "inferred_from_filename",
    "verified_from_source_metadata",
}


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


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def atomic_text(value: str, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(value: Any, path: Path) -> None:
    atomic_text(json.dumps(value, indent=2, sort_keys=True) + "\n", path)


def atomic_tsv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, sep="\t", index=False)
    os.replace(temporary, path)


def atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False, compression="snappy")
    os.replace(temporary, path)


def dataframe_schema(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {"name": column, "dtype": str(frame[column].dtype), "nullable": bool(frame[column].isna().any())}
        for column in frame.columns
    ]


def artifact_record(path: Path, frame: pd.DataFrame | None = None, row_count: int | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if frame is not None:
        record["row_count"] = len(frame)
        record["schema"] = dataframe_schema(frame)
    elif row_count is not None:
        record["row_count"] = row_count
    return record


def validate_status_pairs(frame: pd.DataFrame, name: str) -> None:
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
        raise ValueError(f"{name} status-pair failure: missing={missing}, invalid={invalid}")


class ListingTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple[str, list[str]]] = []
        self.in_row = False
        self.in_cell = False
        self.current_href = ""
        self.current_cell: list[str] = []
        self.current_cells: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self.in_row = True
            self.current_href = ""
            self.current_cells = []
        elif tag == "td" and self.in_row:
            self.in_cell = True
            self.current_cell = []
        elif tag == "a" and self.in_row:
            for key, value in attrs:
                if key.lower() == "href" and value:
                    self.current_href = value

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "td" and self.in_cell:
            self.current_cells.append("".join(self.current_cell).strip())
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.current_href:
                self.rows.append((self.current_href, list(self.current_cells)))
            self.in_row = False


def parse_exact_listing_sizes(body: bytes, listing_url: str) -> dict[str, int]:
    parser = ListingTableParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    sizes: dict[str, int] = {}
    for href, cells in parser.rows:
        if not cells:
            continue
        size_token = cells[-1].strip()
        if not re.fullmatch(r"\d+", size_token):
            continue
        url = urllib.parse.urljoin(listing_url, href)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "data.ngdc.noaa.gov" or parsed.path.endswith("/"):
            continue
        size = int(size_token)
        if url in sizes and sizes[url] != size:
            raise ValueError(f"conflicting exact listing sizes for {url}")
        sizes[url] = size
    return sizes


def validate_primary_ids(values: list[str]) -> None:
    if values != PRIMARY_IDS:
        raise ValueError(f"primary acquisition IDs must be exact and ordered: {PRIMARY_IDS}")


def within_download_cap(total_bytes: int, cap_bytes: int) -> bool:
    return 0 <= total_bytes <= cap_bytes


def load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ValueError("unsupported config schema_version")
    validate_primary_ids(list(config["primary_acquisition"]["immutable_cruise_ids"]))
    if int(config["primary_acquisition"]["aggregate_download_cap_bytes"]) != DOWNLOAD_CAP_BYTES:
        raise ValueError("aggregate download cap must be exactly 12 GiB")
    expected_guards = {
        "stage_b_authorized": False,
        "network_access_allowed": False,
        "physical_object_get_allowed": False,
        "range_get_allowed": False,
        "candidate_depth_read_allowed": False,
        "archive_parse_allowed": False,
        "cell_generation_allowed": False,
        "reference_or_model_comparison_allowed": False,
        "candidate_replacement_allowed": False,
        "external_message_allowed": False,
    }
    if config.get("stage_a2_guards") != expected_guards:
        raise ValueError("Stage A.2 guards do not match the offline final-lock contract")
    if set(config.get("decisions", {})) != {"SR1912", "TN359", "TN358", "TN354"}:
        raise ValueError("Stage A.2 exclusions/deferments must be exact")
    if any(bool(row.get("replacement_allowed")) for row in config["decisions"].values()):
        raise ValueError("excluded or deferred candidates cannot replace the primary set")
    return config


def validate_inputs(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for name, item in config["accepted_stage_a1"].items():
        if name == "run_dir":
            continue
        path = resolve_path(item["path"])
        actual = sha256_file(path)
        if actual != item["sha256"]:
            raise ValueError(f"Stage A.1 input hash mismatch for {name}: {actual}")
        records[name] = {"path": str(path), "bytes": path.stat().st_size, "sha256": actual}
    verification = json.loads(Path(records["verification"]["path"]).read_text(encoding="utf-8"))
    if verification.get("status") != "pass" or verification.get("summary", {}).get("stage_b_authorized") is not False:
        raise ValueError("accepted Stage A.1 receipt is not a passing, unauthorized receipt")
    return records


def load_exact_size_evidence(
    evidence_registry_path: Path,
) -> dict[str, dict[str, Any]]:
    evidence = pd.read_csv(evidence_registry_path, sep="\t")
    exact: dict[str, dict[str, Any]] = {}
    for row in evidence.itertuples(index=False):
        path = Path(row.path)
        if path.stat().st_size != int(row.bytes) or sha256_file(path) != row.sha256:
            raise ValueError(f"frozen listing evidence hash mismatch: {path}")
        for url, size in parse_exact_listing_sizes(path.read_bytes(), str(row.requested_url)).items():
            record = {
                "bytes": size,
                "listing_url": str(row.requested_url),
                "evidence_path": str(path),
                "evidence_sha256": str(row.sha256),
            }
            if url in exact and exact[url] != record:
                raise ValueError(f"conflicting frozen listing evidence for {url}")
            exact[url] = record
    return exact


def build_primary_lock(
    physical: pd.DataFrame,
    registry: pd.DataFrame,
    exact_sizes: dict[str, dict[str, Any]],
    config: dict[str, Any],
    inputs: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    roots = registry.set_index("official_cruise_id")["archive"].astype(str).to_dict()
    rank = {cruise_id: index + 1 for index, cruise_id in enumerate(PRIMARY_IDS)}
    selected = physical[physical["official_cruise_id"].isin(PRIMARY_IDS)].copy()
    if set(selected["official_cruise_id"].astype(str)) != set(PRIMARY_IDS):
        raise ValueError("one or more primary cruises have no physical objects")
    expected_recovery = {
        (cruise_id, filename)
        for cruise_id, filenames in config["primary_acquisition"]["exact_listing_size_recovery"].items()
        for filename in filenames
    }
    actual_missing = set(
        selected.loc[selected["content_length"].isna(), ["official_cruise_id", "filename"]]
        .itertuples(index=False, name=None)
    )
    if actual_missing != expected_recovery:
        raise ValueError(f"unexpected primary Content-Length gaps: {sorted(actual_missing ^ expected_recovery)}")
    records: list[dict[str, Any]] = []
    for row in selected.itertuples(index=False):
        cruise_id = str(row.official_cruise_id)
        direct_url = str(row.direct_url)
        if pd.isna(row.content_length):
            if direct_url not in exact_sizes:
                recovered_bytes: int | None = None
                source = "unresolved"
                source_path = ""
                source_sha = ""
                bytes_status = "officially_unknown"
            else:
                evidence = exact_sizes[direct_url]
                recovered_bytes = int(evidence["bytes"])
                source = "official_directory_listing_exact_integer"
                source_path = str(evidence["evidence_path"])
                source_sha = str(evidence["evidence_sha256"])
                bytes_status = "verified_from_source_metadata"
        else:
            recovered_bytes = int(row.content_length)
            source = "head_content_length"
            source_path = inputs["physical_object_lock"]["path"]
            source_sha = inputs["physical_object_lock"]["sha256"]
            bytes_status = "verified_from_source_metadata"
        root_path = PurePosixPath(urllib.parse.urlparse(roots[cruise_id]).path)
        object_path = PurePosixPath(urllib.parse.urlparse(direct_url).path)
        try:
            relative = object_path.relative_to(root_path)
        except ValueError as error:
            raise ValueError(f"physical URL is outside cruise root: {direct_url}") from error
        record = {
            "official_cruise_id": cruise_id,
            "official_cruise_id_status": "verified_from_source_metadata",
            "primary_rank": rank[cruise_id],
            "primary_rank_status": "known",
            "filename": str(row.filename),
            "filename_status": str(row.filename_status),
            "direct_url": direct_url,
            "direct_url_status": str(row.direct_url_status),
            "relative_object_path": relative.as_posix(),
            "relative_object_path_status": "known",
            "role": str(row.role),
            "role_status": str(row.role_status),
            "format": str(row.format),
            "format_status": str(row.format_status),
            "bytes": recovered_bytes,
            "bytes_status": bytes_status,
            "bytes_source": source,
            "bytes_source_status": "known",
            "bytes_evidence_path": source_path,
            "bytes_evidence_path_status": "known" if source_path else "officially_unknown",
            "bytes_evidence_sha256": source_sha,
            "bytes_evidence_sha256_status": "known" if source_sha else "officially_unknown",
            "last_modified": str(row.last_modified),
            "last_modified_status": str(row.last_modified_status),
            "etag": str(row.etag),
            "etag_status": str(row.etag_status),
            "head_status": str(row.head_status),
            "head_status_status": str(row.head_status_status),
            "vertical_datum": "",
            "vertical_datum_status": "officially_unknown",
            "confirmation_role_eligible": False,
            "confirmation_role_eligible_status": "known",
        }
        records.append(record)
    frame = pd.DataFrame(records)
    frame["bytes"] = pd.array(frame["bytes"], dtype="Int64")
    frame = frame.sort_values(["primary_rank", "direct_url"]).reset_index(drop=True)
    validate_status_pairs(frame, "primary_physical_object_lock")
    return frame


def paired(values: dict[str, Any], statuses: dict[str, str] | None = None) -> dict[str, Any]:
    statuses = statuses or {}
    record: dict[str, Any] = {}
    for key, value in values.items():
        record[key] = value
        record[f"{key}_status"] = statuses.get(key, "known")
    return record


def build_budget(lock: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    track = registry.set_index("official_cruise_id")["scs_track_length_km"].astype(float).to_dict()
    rows: list[dict[str, Any]] = []
    for rank, cruise_id in enumerate(PRIMARY_IDS, start=1):
        subset = lock[lock["official_cruise_id"].eq(cruise_id)]
        total = int(subset["bytes"].dropna().sum())
        complete = bool(len(subset)) and subset["bytes"].notna().all()
        rows.append(paired({
            "row_type": "cruise",
            "official_cruise_id": cruise_id,
            "primary_rank": rank,
            "physical_object_count": len(subset),
            "head_content_length_count": int(subset["bytes_source"].eq("head_content_length").sum()),
            "listing_exact_size_count": int(subset["bytes_source"].eq("official_directory_listing_exact_integer").sum()),
            "bytes_known_count": int(subset["bytes"].notna().sum()),
            "total_bytes": total,
            "total_bytes_complete": complete,
            "scs_track_length_km": float(track[cruise_id]),
            "download_cap_bytes": DOWNLOAD_CAP_BYTES,
            "within_download_cap": complete and within_download_cap(total, DOWNLOAD_CAP_BYTES),
            "stage_b_authorized": False,
        }, {
            "official_cruise_id": "verified_from_source_metadata",
            "physical_object_count": "known",
            "total_bytes": "known",
            "scs_track_length_km": "verified_from_source_metadata",
        }))
    frame = pd.DataFrame(rows)
    total_bytes = int(frame["total_bytes"].sum())
    total_objects = int(frame["physical_object_count"].sum())
    complete = bool(frame["total_bytes_complete"].all())
    rows.append(paired({
        "row_type": "all_primary",
        "official_cruise_id": "__ALL_PRIMARY__",
        "primary_rank": 0,
        "physical_object_count": total_objects,
        "head_content_length_count": int(frame["head_content_length_count"].sum()),
        "listing_exact_size_count": int(frame["listing_exact_size_count"].sum()),
        "bytes_known_count": int(frame["bytes_known_count"].sum()),
        "total_bytes": total_bytes,
        "total_bytes_complete": complete,
        "scs_track_length_km": float(frame["scs_track_length_km"].sum()),
        "download_cap_bytes": DOWNLOAD_CAP_BYTES,
        "within_download_cap": complete and within_download_cap(total_bytes, DOWNLOAD_CAP_BYTES),
        "stage_b_authorized": False,
    }))
    result = pd.DataFrame(rows)
    validate_status_pairs(result, "primary_cruise_budget")
    return result


def build_decisions(config: dict[str, Any], registry: pd.DataFrame, a1_budget: pd.DataFrame) -> pd.DataFrame:
    metadata = registry.set_index("official_cruise_id")
    costs = a1_budget[a1_budget["row_type"].eq("cruise")].set_index("official_cruise_id")
    records: list[dict[str, Any]] = []
    for cruise_id in PRIMARY_IDS + ["SR1912", "TN359", "TN358", "TN354"]:
        if cruise_id in PRIMARY_IDS:
            decision = "primary_acquisition"
            reason = "immutable_user_approved_primary_set"
        else:
            decision = str(config["decisions"][cruise_id]["decision"])
            reason = str(config["decisions"][cruise_id]["reason"])
        records.append(paired({
            "official_cruise_id": cruise_id,
            "decision": decision,
            "reason": reason,
            "scs_track_length_km": float(metadata.loc[cruise_id, "scs_track_length_km"]),
            "stage_a1_known_bytes": int(costs.loc[cruise_id, "total_bytes"]),
            "replacement_allowed": False,
            "model_or_product_result_used": False,
            "confirmation_role_eligible": False,
        }, {
            "official_cruise_id": "verified_from_source_metadata",
            "scs_track_length_km": "verified_from_source_metadata",
            "stage_a1_known_bytes": "known",
        }))
    frame = pd.DataFrame(records)
    validate_status_pairs(frame, "candidate_decision_registry")
    return frame


def build_dry_run_plan(lock: pd.DataFrame, run_id: str) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for index, row in enumerate(lock.itertuples(index=False), start=1):
        destination = f"objects/{row.official_cruise_id}/{row.relative_object_path}"
        records.append({
            "plan_index": index,
            "official_cruise_id": row.official_cruise_id,
            "primary_rank": int(row.primary_rank),
            "direct_url": row.direct_url,
            "filename": row.filename,
            "relative_destination": destination,
            "expected_bytes": int(row.bytes) if not pd.isna(row.bytes) else None,
            "role": row.role,
            "format": row.format,
            "last_modified": row.last_modified,
            "etag": row.etag,
            "request_method_if_authorized": "GET",
            "range_header_if_authorized": False,
            "dry_run_status": "planned_not_authorized",
            "download_executed": False,
            "stage_a2_run_id": run_id,
        })
    frame = pd.DataFrame(records)
    frame["expected_bytes"] = pd.array(frame["expected_bytes"], dtype="Int64")
    if frame["relative_destination"].duplicated().any():
        raise ValueError("dry-run destination collision")
    return frame


def render_report(budget: pd.DataFrame, decisions: pd.DataFrame) -> str:
    total = budget[budget["row_type"].eq("all_primary")].iloc[0]
    return "\n".join([
        "# SCS v2 sealed confirmation acquisition: Stage A.2",
        "",
        "This offline run froze the exact four-cruise primary acquisition set and a 12 GiB aggregate cap from accepted Stage A.1 metadata. It made no network request and downloaded no object.",
        "",
        f"- Primary cruises: {', '.join(PRIMARY_IDS)}",
        f"- Physical objects: {int(total['physical_object_count'])}",
        f"- Exact total bytes: {int(total['total_bytes'])}",
        f"- Official SCS track length: {float(total['scs_track_length_km']):.6f} km",
        f"- Within 12 GiB cap: {str(bool(total['within_download_cap'])).lower()}",
        "- TN352 exact listing-size recoveries: 2",
        "- Physical object downloads: 0",
        "- Stage B authorized: false",
        "- Maximum role after any future approved download: sealed_unprocessed",
        "",
        "Excluded/deferred without replacement: " + ", ".join(
            decisions.loc[~decisions["official_cruise_id"].isin(PRIMARY_IDS), "official_cruise_id"].astype(str)
        ),
        "",
    ])


def run_stage_a2(config_path: Path, run_id: str) -> Path:
    if Path.cwd().resolve() != REPO_ROOT:
        raise ValueError(f"run from repository root: {REPO_ROOT}")
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run-id must match YYYYMMDDTHHMMSSZ")
    config = load_config(config_path)
    inputs = validate_inputs(config)
    physical = pd.read_parquet(Path(inputs["physical_object_lock"]["path"]))
    registry = pd.read_parquet(Path(inputs["revised_candidate_registry"]["path"]))
    a1_budget = pd.read_csv(Path(inputs["per_cruise_byte_budget"]["path"]), sep="\t", keep_default_na=False)
    exact_sizes = load_exact_size_evidence(Path(inputs["metadata_evidence_registry"]["path"]))

    output_root = resolve_path(config["output_root"])
    final_dir = output_root / run_id
    if final_dir.exists():
        raise FileExistsError(f"immutable run already exists: {final_dir}")
    output_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=output_root))
    try:
        primary_lock = build_primary_lock(physical, registry, exact_sizes, config, inputs)
        budget = build_budget(primary_lock, registry)
        decisions = build_decisions(config, registry, a1_budget)
        dry_run_plan = build_dry_run_plan(primary_lock, run_id)
        total = budget[budget["row_type"].eq("all_primary")].iloc[0]
        if not bool(total["total_bytes_complete"]) or not bool(total["within_download_cap"]):
            raise ValueError("primary physical lock is incomplete or exceeds the 12 GiB cap")

        primary_path = temp_dir / "primary_physical_object_lock.parquet"
        budget_path = temp_dir / "primary_cruise_budget.tsv"
        decisions_path = temp_dir / "candidate_decision_registry.tsv"
        plan_path = temp_dir / "stage_b_dry_run_plan.tsv"
        atomic_parquet(primary_lock, primary_path)
        atomic_tsv(budget, budget_path)
        atomic_tsv(decisions, decisions_path)
        atomic_tsv(dry_run_plan, plan_path)

        recovered = primary_lock[primary_lock["bytes_source"].eq("official_directory_listing_exact_integer")]
        final_lock = {
            "schema_version": 1,
            "run_id": run_id,
            "created_utc": utc_now(),
            "stage": "A.2_offline_final_download_lock",
            "accepted_stage_a1_manifest_sha256": inputs["audit_manifest"]["sha256"],
            "accepted_stage_a1_verification_sha256": inputs["verification"]["sha256"],
            "immutable_primary_confirmation_cruise_ids": PRIMARY_IDS,
            "primary_cruise_count": len(PRIMARY_IDS),
            "physical_object_count": len(primary_lock),
            "exact_total_bytes": int(total["total_bytes"]),
            "aggregate_download_cap_bytes": DOWNLOAD_CAP_BYTES,
            "remaining_cap_bytes": DOWNLOAD_CAP_BYTES - int(total["total_bytes"]),
            "within_download_cap": True,
            "official_scs_track_length_km": float(total["scs_track_length_km"]),
            "primary_physical_object_lock_sha256": sha256_file(primary_path),
            "primary_cruise_budget_sha256": sha256_file(budget_path),
            "stage_b_dry_run_plan_sha256": sha256_file(plan_path),
            "tn352_exact_listing_size_recovery": [
                {
                    "filename": row.filename,
                    "direct_url": row.direct_url,
                    "bytes": int(row.bytes),
                    "bytes_source": row.bytes_source,
                    "evidence_path": row.bytes_evidence_path,
                    "evidence_sha256": row.bytes_evidence_sha256,
                }
                for row in recovered.itertuples(index=False)
            ],
            "excluded_or_deferred": [
                {
                    "official_cruise_id": row.official_cruise_id,
                    "decision": row.decision,
                    "reason": row.reason,
                    "replacement_allowed": False,
                }
                for row in decisions.loc[~decisions["official_cruise_id"].isin(PRIMARY_IDS)].itertuples(index=False)
            ],
            "branch_contract": {
                "confirmation_candidate_v2_H_MRAR_out": "pending_seal_and_processing",
                "confirmation_candidate_v2_W_MRAR_in": "blocked_source_independence_unknown",
                "global_confirmation_role_eligible": False,
            },
            "vertical_datum_status": "officially_unknown",
            "maximum_post_download_role": "sealed_unprocessed",
            "stage_c_required_before_processing": True,
            "candidate_replacement_allowed": False,
            "stage_b_authorized": False,
            "stage_b_dry_run_only": True,
            "network_access_count": 0,
            "physical_object_download_count": 0,
            "physical_object_body_read_count": 0,
            "range_get_count": 0,
            "candidate_depth_read": False,
            "archive_parse_count": 0,
            "cell_generation_count": 0,
            "reference_or_model_comparison_count": 0,
            "external_message_count": 0,
            "stage_b_requires_separate_user_approval": True,
        }
        final_lock_path = temp_dir / "final_download_lock.json"
        atomic_json(final_lock, final_lock_path)
        report_path = temp_dir / "audit_report.md"
        atomic_text(render_report(budget, decisions), report_path)

        outputs = {
            "primary_physical_object_lock": artifact_record(primary_path, primary_lock),
            "primary_cruise_budget": artifact_record(budget_path, budget),
            "candidate_decision_registry": artifact_record(decisions_path, decisions),
            "stage_b_dry_run_plan": artifact_record(plan_path, dry_run_plan),
            "final_download_lock": artifact_record(final_lock_path, row_count=1),
            "audit_report": artifact_record(report_path, row_count=len(report_path.read_text(encoding="utf-8").splitlines())),
        }
        for record in outputs.values():
            record["path"] = str(final_dir / Path(record["path"]).name)
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "created_utc": utc_now(),
            "stage": "A.2_offline_final_download_lock",
            "config": {
                "path": str(config_path.resolve()),
                "bytes": config_path.stat().st_size,
                "sha256": sha256_file(config_path),
            },
            "accepted_stage_a1_inputs": inputs,
            "primary_acquisition": {
                "immutable_cruise_ids": PRIMARY_IDS,
                "cruise_count": len(PRIMARY_IDS),
                "physical_object_count": len(primary_lock),
                "exact_total_bytes": int(total["total_bytes"]),
                "aggregate_download_cap_bytes": DOWNLOAD_CAP_BYTES,
                "within_download_cap": True,
                "official_scs_track_length_km": float(total["scs_track_length_km"]),
            },
            "branch_contract": final_lock["branch_contract"],
            "role_ceiling": {
                "current_confirmation_role_eligible": False,
                "maximum_post_download_role": "sealed_unprocessed",
                "stage_c_required": True,
            },
            "prohibited_actions": {
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
            },
            "outputs": outputs,
            "verification_required": True,
            "stage_b_requires_separate_user_approval": True,
        }
        manifest_path = temp_dir / "audit_manifest.json"
        atomic_json(manifest, manifest_path)
        os.replace(temp_dir, final_dir)
        print(stable_json({
            "status": "stage_a2_published_unverified",
            "run_dir": str(final_dir),
            "primary_cruise_ids": PRIMARY_IDS,
            "physical_object_count": len(primary_lock),
            "exact_total_bytes": int(total["total_bytes"]),
            "manifest_sha256": sha256_file(final_dir / "audit_manifest.json"),
            "stage_b_authorized": False,
        }))
        return final_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--confirm-stage-a2", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confirm_stage_a2:
        print("ERROR: Stage A.2 requires --confirm-stage-a2; Stage B is unavailable.", file=sys.stderr)
        return 2
    run_stage_a2(args.config.resolve(), args.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
