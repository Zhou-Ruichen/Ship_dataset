#!/usr/bin/env python3
"""Build the metadata-only SCS confirmation Stage A.1 physical-object lock.

Stage A.1 may GET official NCEI directory-listing HTML and may issue HEAD to
the physical objects named by those listings. It never GETs an object body,
sends a Range request, opens sonar data, generates cells, or authorizes Stage B.

Run from the repository root::

    python ncei/code/scs_confirmation/discover_scs_v2_sealed_confirmation_stage_a1.py \
      --config ncei/configs/scs_v2_sealed_confirmation_stage_a1.yaml \
      --run-id YYYYMMDDTHHMMSSZ --confirm-stage-a1
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z$")
NCEI_HOST = "data.ngdc.noaa.gov"
FIELD_STATUSES = {
    "known",
    "officially_unknown",
    "not_recoverable",
    "inferred_from_filename",
    "verified_from_source_metadata",
}
PHYSICAL_COLUMNS = [
    "official_cruise_id", "official_cruise_id_status",
    "filename", "filename_status",
    "direct_url", "direct_url_status",
    "resolved_url", "resolved_url_status",
    "content_length", "content_length_status",
    "etag", "etag_status",
    "last_modified", "last_modified_status",
    "format", "format_status",
    "role", "role_status",
    "head_status", "head_status_status",
    "head_http_status", "head_http_status_status",
    "head_error", "head_error_status",
    "content_type", "content_type_status",
    "listing_url", "listing_url_status",
    "selection_rank", "selection_rank_status",
    "object_body_read", "object_body_read_status",
    "range_header_sent", "range_header_sent_status",
]


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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def validate_status_pairs(frame: pd.DataFrame, exempt: set[str] | None = None) -> None:
    exempt = exempt or set()
    status_columns = {
        column for column in frame.columns
        if column.endswith("_status") and column.removesuffix("_status") in frame.columns
    }
    for column in frame.columns:
        if column in status_columns or column in exempt:
            continue
        status_column = f"{column}_status"
        if status_column not in frame.columns:
            raise ValueError(f"missing factual status for {column}")
    for column in status_columns:
        invalid = set(frame[column].dropna().astype(str)) - FIELD_STATUSES
        if invalid:
            raise ValueError(f"invalid evidence statuses in {column}: {sorted(invalid)}")


def load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ValueError("unsupported config schema_version")
    expected_guards = {
        "stage_b_authorized": False,
        "official_file_list_metadata_get_allowed": True,
        "physical_object_enumeration_allowed": True,
        "physical_object_head_allowed": True,
        "physical_object_get_allowed": False,
        "range_get_allowed": False,
        "candidate_depth_read_allowed": False,
        "cell_generation_allowed": False,
        "reference_or_model_comparison_allowed": False,
        "external_message_allowed": False,
    }
    if config.get("stage_a1_guards") != expected_guards:
        raise ValueError("Stage A.1 guards do not match the metadata-list/HEAD-only contract")
    if config["selection"].get("rule") != "all_2018plus_unexposed_candidates_no_count_cap":
        raise ValueError("selection rule must explicitly remove the old top-five cap")
    if config["official_file_list"].get("allowed_host") != NCEI_HOST:
        raise ValueError(f"only the official {NCEI_HOST} file-list host is allowed")
    return config


def validate_accepted_stage_a(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for name, item in config["accepted_stage_a"].items():
        if name == "run_dir":
            continue
        path = resolve_path(item["path"])
        actual = sha256_file(path)
        if actual != item["sha256"]:
            raise ValueError(f"accepted Stage A input hash mismatch for {name}: {actual}")
        records[name] = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": actual,
        }
    verification = json.loads(resolve_path(config["accepted_stage_a"]["verification"]["path"]).read_text(encoding="utf-8"))
    if verification.get("status") != "pass":
        raise ValueError("accepted Stage A verification is not pass")
    return records


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


def chronology_rank_key(row: dict[str, Any] | Any, cutoff: str) -> tuple[Any, ...]:
    getter = row.get if isinstance(row, dict) else lambda key, default=None: getattr(row, key, default)
    _, end = parse_date_bounds(getter("date", ""))
    cutoff_dt = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    chronology_class = 0 if end and end > cutoff_dt else 1
    end_desc = -end.timestamp() if end else float("inf")
    return (
        chronology_class,
        end_desc,
        -float(getter("scs_track_length_km", 0.0) or 0.0),
        str(getter("official_cruise_id", "")),
    )


def is_official_directory_url(url: str, host: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "https" and parsed.hostname == host and parsed.path.endswith("/") and not parsed.query


def select_comparison_rows(rows: Iterable[dict[str, Any]], minimum_year: int, host: str) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        start, _ = parse_date_bounds(row.get("date", ""))
        if not start or start.year < minimum_year:
            continue
        if row.get("ever_read_by_repo") != "false":
            continue
        if row.get("overlap_with_current_19") != "false" or row.get("overlap_with_exposed_12") != "false":
            continue
        if not bool(row.get("geometry_intersects_scs")):
            continue
        if not is_official_directory_url(str(row.get("archive", "")), host):
            continue
        selected.append(dict(row))
    return selected


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


def url_is_within_root(url: str, root_url: str, host: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    root = urllib.parse.urlparse(root_url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == host
        and parsed.query == ""
        and parsed.fragment == ""
        and parsed.path.startswith(root.path)
    )


def parse_directory_listing(body: bytes, listing_url: str, root_url: str, host: str) -> tuple[list[str], list[str]]:
    parser = LinkParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    directories: set[str] = set()
    objects: set[str] = set()
    for href in parser.hrefs:
        if href.startswith(("?", "#")):
            continue
        absolute = urllib.parse.urljoin(listing_url, href)
        if not url_is_within_root(absolute, root_url, host):
            continue
        if absolute == listing_url or absolute == root_url.rstrip("/"):
            continue
        parsed = urllib.parse.urlparse(absolute)
        normalized = urllib.parse.urlunparse(parsed._replace(query="", fragment=""))
        if parsed.path.endswith("/"):
            directories.add(normalized)
        else:
            objects.add(normalized)
    return sorted(directories), sorted(objects)


def infer_format_role(filename: str) -> tuple[str, str]:
    lower = filename.lower()
    compressed = (".gz", ".bz2", ".xz", ".z")
    raw_suffixes = (".all", ".kmall", ".s7k", ".raw", ".gsf", ".mb", ".hsx", ".xse")
    navigation_suffixes = (".fnv", ".nav", ".pos", ".gps")
    sidecar_suffixes = (".inf", ".fbt", ".par", ".log")
    document_suffixes = (".txt", ".md", ".pdf", ".html", ".xml", ".json")
    archive_suffixes = (".tar", ".tgz", ".zip", ".7z", ".rar")
    suffixes = Path(lower).suffixes
    format_name = "".join(suffixes[-2:]) if len(suffixes) >= 2 and suffixes[-1] in compressed else (suffixes[-1] if suffixes else "")
    uncompressed = lower
    if suffixes and suffixes[-1] in compressed:
        uncompressed = lower[: -len(suffixes[-1])]
    if re.search(r"\.mb\d+$", uncompressed):
        role = "multibeam_data_compressed" if lower.endswith(compressed) else "multibeam_data"
    elif uncompressed.endswith(raw_suffixes):
        role = "raw_sounding_compressed" if lower.endswith(compressed) else "raw_sounding"
    elif lower.endswith(navigation_suffixes):
        role = "navigation_sidecar"
    elif lower.endswith(sidecar_suffixes):
        role = "processing_sidecar"
    elif lower.endswith(document_suffixes):
        role = "documentation"
    elif lower.endswith(archive_suffixes):
        role = "archive_container"
    else:
        role = "unknown"
    return format_name, role


def fetch_directory_listing(
    url: str,
    cruise_id: str,
    evidence_dir: Path,
    timeout: int,
    user_agent: str,
    host: str,
    sequence: int,
) -> tuple[bytes | None, dict[str, Any], dict[str, Any] | None]:
    if not is_official_directory_url(url, host):
        raise ValueError(f"directory metadata GET rejected by allowlist: {url}")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml;q=0.9"},
        method="GET",
    )
    started = utc_now()
    status = 0
    resolved_url = url
    headers: dict[str, str] = {}
    error_text = ""
    body: bytes | None = None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            resolved_url = response.geturl()
            headers = {key.lower(): value for key, value in response.headers.items()}
            content_type = headers.get("content-type", "").lower()
            if not is_official_directory_url(resolved_url, host):
                raise RuntimeError(f"directory GET redirected outside directory allowlist: {resolved_url}")
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                raise RuntimeError(f"directory GET returned non-HTML content type: {content_type}")
            body = response.read()
    except urllib.error.HTTPError as error:
        status = int(error.code)
        resolved_url = error.geturl()
        headers = {key.lower(): value for key, value in error.headers.items()}
        error_text = f"HTTPError:{error.code}"
    except Exception as error:  # network/parser boundary, recorded literally
        error_text = f"{type(error).__name__}:{error}"
    path = evidence_dir / f"{cruise_id}_{sequence:04d}_{hashlib.sha256(url.encode()).hexdigest()[:16]}.html"
    evidence: dict[str, Any] | None = None
    if body is not None:
        path.write_bytes(body)
        evidence = {
            "evidence_id": f"file_list_{cruise_id}_{sequence:04d}",
            "official_cruise_id": cruise_id,
            "role": "official_cruise_file_list_metadata",
            "requested_url": url,
            "resolved_url": resolved_url,
            "path": str(path.resolve()),
            "mime_type": headers.get("content-type", ""),
            "bytes": len(body),
            "sha256": sha256_bytes(body),
            "http_status": status,
        }
    query = {
        "timestamp_utc": started,
        "operation": "official_file_list_metadata_get",
        "request_role": "official_cruise_file_list_metadata",
        "method": "GET",
        "official_cruise_id": cruise_id,
        "url": url,
        "resolved_url": resolved_url,
        "http_status": status,
        "response_path": str(path.resolve()) if body is not None else "",
        "response_bytes": len(body) if body is not None else 0,
        "response_sha256": sha256_bytes(body) if body is not None else "",
        "content_type": headers.get("content-type", ""),
        "error": error_text,
        "body_read": body is not None,
        "range_header_sent": False,
        "execution": "python urllib.request.urlopen directory-metadata GET",
        "replay_command": f"curl --fail --location --silent --show-error --output <metadata-html> {json.dumps(url)}",
    }
    return body, query, evidence


def head_physical_object(
    url: str,
    cruise_id: str,
    listing_url: str,
    selection_rank: int,
    timeout: int,
    user_agent: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept-Encoding": "identity"},
        method="HEAD",
    )
    started = utc_now()
    status = 0
    resolved_url = url
    headers: dict[str, str] = {}
    error_text = ""
    head_status = "success"
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            resolved_url = response.geturl()
            headers = {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as error:
        status = int(error.code)
        resolved_url = error.geturl()
        headers = {key.lower(): value for key, value in error.headers.items()}
        error_text = f"HTTPError:{error.code}"
        head_status = "http_error"
    except Exception as error:  # network boundary, recorded literally
        error_text = f"{type(error).__name__}:{error}"
        head_status = "network_error"
    content_length: int | None = None
    raw_length = headers.get("content-length", "")
    if raw_length.isdigit():
        content_length = int(raw_length)
    filename = urllib.parse.unquote(Path(urllib.parse.urlparse(url).path).name)
    format_name, role = infer_format_role(filename)
    record = {
        "official_cruise_id": cruise_id,
        "official_cruise_id_status": "verified_from_source_metadata",
        "filename": filename,
        "filename_status": "verified_from_source_metadata",
        "direct_url": url,
        "direct_url_status": "verified_from_source_metadata",
        "resolved_url": resolved_url,
        "resolved_url_status": "verified_from_source_metadata" if status else "officially_unknown",
        "content_length": content_length,
        "content_length_status": "verified_from_source_metadata" if content_length is not None else "officially_unknown",
        "etag": headers.get("etag", ""),
        "etag_status": "verified_from_source_metadata" if headers.get("etag") else "officially_unknown",
        "last_modified": headers.get("last-modified", ""),
        "last_modified_status": "verified_from_source_metadata" if headers.get("last-modified") else "officially_unknown",
        "format": format_name,
        "format_status": "inferred_from_filename",
        "role": role,
        "role_status": "inferred_from_filename",
        "head_status": head_status,
        "head_status_status": "known",
        "head_http_status": status if status else None,
        "head_http_status_status": "verified_from_source_metadata" if status else "officially_unknown",
        "head_error": error_text,
        "head_error_status": "known",
        "content_type": headers.get("content-type", ""),
        "content_type_status": "verified_from_source_metadata" if headers.get("content-type") else "officially_unknown",
        "listing_url": listing_url,
        "listing_url_status": "verified_from_source_metadata",
        "selection_rank": selection_rank,
        "selection_rank_status": "known",
        "object_body_read": False,
        "object_body_read_status": "known",
        "range_header_sent": False,
        "range_header_sent_status": "known",
    }
    query = {
        "timestamp_utc": started,
        "operation": "physical_object_head",
        "request_role": "physical_object_transport_metadata",
        "method": "HEAD",
        "official_cruise_id": cruise_id,
        "url": url,
        "resolved_url": resolved_url,
        "http_status": status,
        "response_path": "",
        "response_bytes": 0,
        "response_sha256": "",
        "content_type": headers.get("content-type", ""),
        "error": error_text,
        "body_read": False,
        "range_header_sent": False,
        "execution": "python urllib.request.urlopen HEAD",
        "replay_command": f"curl --head --location --silent --show-error {json.dumps(url)}",
    }
    return record, query


def enumerate_cruise_objects(
    candidate: dict[str, Any],
    evidence_dir: Path,
    settings: dict[str, Any],
) -> tuple[list[tuple[str, str]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    cruise_id = str(candidate["official_cruise_id"])
    root_url = str(candidate["archive"])
    host = str(settings["allowed_host"])
    queue: list[tuple[str, int]] = [(root_url, 0)]
    seen_directories: set[str] = set()
    objects: dict[str, str] = {}
    queries: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    negatives: list[dict[str, Any]] = []
    maximum_pages = int(settings["maximum_directory_pages_per_cruise"])
    maximum_depth = int(settings["maximum_directory_depth"])
    while queue:
        listing_url, depth = queue.pop(0)
        if listing_url in seen_directories:
            continue
        if len(seen_directories) >= maximum_pages:
            negatives.append({
                "category": "directory_limit",
                "official_cruise_id": cruise_id,
                "reason": "maximum_directory_pages_reached",
                "evidence": listing_url,
            })
            break
        seen_directories.add(listing_url)
        body, query, evidence_row = fetch_directory_listing(
            listing_url,
            cruise_id,
            evidence_dir,
            int(settings["request_timeout_seconds"]),
            str(settings["user_agent"]),
            host,
            len(seen_directories),
        )
        queries.append(query)
        if evidence_row is not None:
            evidence.append(evidence_row)
        if body is None:
            negatives.append({
                "category": "directory_metadata",
                "official_cruise_id": cruise_id,
                "reason": query["error"] or f"http_status_{query['http_status']}",
                "evidence": listing_url,
            })
            continue
        directories, listed_objects = parse_directory_listing(body, listing_url, root_url, host)
        for object_url in listed_objects:
            objects.setdefault(object_url, listing_url)
        if depth >= maximum_depth:
            for child in directories:
                negatives.append({
                    "category": "directory_limit",
                    "official_cruise_id": cruise_id,
                    "reason": "maximum_directory_depth_reached",
                    "evidence": child,
                })
        else:
            queue.extend((child, depth + 1) for child in directories if child not in seen_directories)
    return sorted(objects.items()), queries, evidence, negatives


def paired_budget_record(values: dict[str, Any], statuses: dict[str, str] | None = None) -> dict[str, Any]:
    statuses = statuses or {}
    record: dict[str, Any] = {}
    for key, value in values.items():
        record[key] = value
        record[f"{key}_status"] = statuses.get(key, "known")
    return record


def budget_for_cruise(
    cruise_id: str,
    selection_rank: int,
    directory_url: str,
    listing_pages: int,
    listing_failures: int,
    rows: pd.DataFrame,
) -> dict[str, Any]:
    object_count = len(rows)
    head_ok_count = int(rows["head_status"].eq("success").sum()) if object_count else 0
    content_length_known_count = int(rows["content_length"].notna().sum()) if object_count else 0
    head_failed_count = object_count - head_ok_count
    known_bytes = int(rows["content_length"].dropna().sum()) if object_count else 0
    if listing_failures:
        physical_lock_status = "blocked_directory_metadata_incomplete"
    elif object_count == 0:
        physical_lock_status = "blocked_directory_only_no_physical_objects"
    elif head_failed_count:
        physical_lock_status = "blocked_head_unavailable"
    elif content_length_known_count != object_count:
        physical_lock_status = "blocked_content_length_unknown"
    else:
        physical_lock_status = "closed_metadata_head_lock"
    stage_b_block_reason = (
        "separate_stage_b_approval_required"
        if physical_lock_status == "closed_metadata_head_lock"
        else physical_lock_status
    )
    return paired_budget_record(
        {
            "row_type": "cruise",
            "official_cruise_id": cruise_id,
            "selection_rank": selection_rank,
            "directory_url": directory_url,
            "listing_page_count": listing_pages,
            "listing_failure_count": listing_failures,
            "physical_object_count": object_count,
            "head_ok_count": head_ok_count,
            "head_failed_count": head_failed_count,
            "content_length_known_count": content_length_known_count,
            "total_bytes": known_bytes,
            "total_bytes_complete": content_length_known_count == object_count and object_count > 0,
            "physical_lock_status": physical_lock_status,
            "stage_b_authorized": False,
            "stage_b_block_reason": stage_b_block_reason,
        },
        {
            "official_cruise_id": "verified_from_source_metadata",
            "directory_url": "verified_from_source_metadata",
            "physical_object_count": "known",
            "content_length_known_count": "known",
            "total_bytes": "known",
        },
    )


def all_candidates_budget(rows: list[dict[str, Any]]) -> dict[str, Any]:
    frame = pd.DataFrame(rows)
    all_closed = bool(len(frame)) and frame["physical_lock_status"].eq("closed_metadata_head_lock").all()
    physical_status = "closed_metadata_head_lock" if all_closed else "blocked_one_or_more_cruises_incomplete"
    return paired_budget_record({
        "row_type": "all_candidates",
        "official_cruise_id": "__ALL_CANDIDATES__",
        "selection_rank": 0,
        "directory_url": "",
        "listing_page_count": int(frame["listing_page_count"].sum()),
        "listing_failure_count": int(frame["listing_failure_count"].sum()),
        "physical_object_count": int(frame["physical_object_count"].sum()),
        "head_ok_count": int(frame["head_ok_count"].sum()),
        "head_failed_count": int(frame["head_failed_count"].sum()),
        "content_length_known_count": int(frame["content_length_known_count"].sum()),
        "total_bytes": int(frame["total_bytes"].sum()),
        "total_bytes_complete": bool(frame["total_bytes_complete"].all()),
        "physical_lock_status": physical_status,
        "stage_b_authorized": False,
        "stage_b_block_reason": "separate_stage_b_approval_required" if all_closed else physical_status,
    })


def revise_candidate_registry(
    original: pd.DataFrame,
    selected: list[dict[str, Any]],
    budgets: pd.DataFrame,
    cutoff: str,
) -> pd.DataFrame:
    frame = original.copy()
    selected_ids = [str(row["official_cruise_id"]) for row in selected]
    rank = {cruise_id: index + 1 for index, cruise_id in enumerate(selected_ids)}
    cruise_budgets = budgets[budgets["row_type"].eq("cruise")].set_index("official_cruise_id")
    is_selected = frame["official_cruise_id"].isin(selected_ids)
    frame["sealed_status"] = is_selected.map({True: "selected_unsealed", False: "excluded"})
    frame["sealed_status_status"] = "known"
    frame["candidate_qualification"] = is_selected.map({True: "qualified_for_stage_a1_preseal", False: "excluded"})
    frame["candidate_qualification_status"] = "known"
    frame["confirmation_role_eligible"] = False
    frame["confirmation_role_eligible_status"] = "known"
    frame["selection_rank"] = frame["official_cruise_id"].map(rank).fillna(-1).astype("int64")
    frame["selection_rank_status"] = "known"
    frame["stage_a1_comparison_cohort"] = is_selected
    frame["stage_a1_comparison_cohort_status"] = "known"
    frame["stage_a1_selection_rule"] = "all_2018plus_unexposed_candidates_no_count_cap"
    frame["stage_a1_selection_rule_status"] = "known"
    frame["chronology_risk"] = "not_in_stage_a1_comparison_cohort"
    frame["chronology_risk_status"] = "known"
    frame["stage_a1_decision_reason"] = "not_in_2018plus_unexposed_comparison_cohort"
    frame["stage_a1_decision_reason_status"] = "known"
    frame["confirmation_candidate_v2_H_MRAR_out"] = "not_in_stage_a1_selected_set"
    frame["confirmation_candidate_v2_H_MRAR_out_status"] = "known"
    frame["confirmation_candidate_v2_W_MRAR_in"] = "not_in_stage_a1_selected_set"
    frame["confirmation_candidate_v2_W_MRAR_in_status"] = "known"
    frame["physical_object_count"] = pd.array([pd.NA] * len(frame), dtype="Int64")
    frame["physical_object_count_status"] = "officially_unknown"
    frame["physical_total_bytes"] = pd.array([pd.NA] * len(frame), dtype="Int64")
    frame["physical_total_bytes_status"] = "officially_unknown"
    frame["physical_lock_status"] = "not_in_stage_a1_selected_set"
    frame["physical_lock_status_status"] = "known"
    cutoff_dt = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    for index, row in frame[is_selected].iterrows():
        _, end = parse_date_bounds(row["date"])
        frame.at[index, "chronology_risk"] = (
            "chronology_excludes_mrar_delivery" if end and end > cutoff_dt
            else "chronology_does_not_exclude_mrar"
        )
        frame.at[index, "stage_a1_decision_reason"] = "selected_by_frozen_2018plus_unexposed_rule"
        frame.at[index, "confirmation_candidate_v2_H_MRAR_out"] = "pending_seal_and_processing"
        frame.at[index, "confirmation_candidate_v2_W_MRAR_in"] = "blocked_source_independence_unknown"
        budget = cruise_budgets.loc[row["official_cruise_id"]]
        frame.at[index, "physical_object_count"] = int(budget["physical_object_count"])
        frame.at[index, "physical_object_count_status"] = "known"
        frame.at[index, "physical_total_bytes"] = int(budget["total_bytes"])
        frame.at[index, "physical_total_bytes_status"] = "known"
        frame.at[index, "physical_lock_status"] = str(budget["physical_lock_status"])
    validate_status_pairs(frame)
    return frame


def rewrite_final_paths(rows: list[dict[str, Any]], final_dir: Path) -> None:
    final_evidence_dir = final_dir / "metadata_evidence"
    for row in rows:
        if row.get("path"):
            row["path"] = str(final_evidence_dir / Path(row["path"]).name)
        if row.get("response_path"):
            row["response_path"] = str(final_evidence_dir / Path(row["response_path"]).name)


def render_report(revised: pd.DataFrame, budgets: pd.DataFrame, queries: list[dict[str, Any]]) -> str:
    selected = revised[revised["stage_a1_comparison_cohort"]].sort_values("selection_rank")
    total = budgets[budgets["row_type"].eq("all_candidates")].iloc[0]
    return "\n".join([
        "# SCS v2 sealed confirmation acquisition: Stage A.1",
        "",
        "This immutable run used official Cruise File List HTML and HEAD transport metadata only. It did not GET or Range-GET any physical object body, read a depth value, generate a cell, contact NCEI, or authorize Stage B.",
        "",
        f"- 2018+ unexposed comparison candidates: {len(selected)}",
        f"- Physical objects enumerated from official file-list metadata: {int(total['physical_object_count'])}",
        f"- HEAD success: {int(total['head_ok_count'])}",
        f"- Known byte total: {int(total['total_bytes'])}",
        f"- File-list metadata GET count: {sum(row['method'] == 'GET' for row in queries)}",
        f"- Physical-object GET/Range GET count: 0/0",
        "- Global confirmation_role_eligible: false",
        "- Stage B authorized: false",
        "",
        "Chronology-first selected set: " + ", ".join(selected["official_cruise_id"].astype(str)),
        "",
        "The v2-H branch remains pending_seal_and_processing. The v2-W branch remains blocked_source_independence_unknown because MRAR identity is not recoverable and source independence is unknown.",
        "",
        "If direct object metadata cannot be closed, contacting NCEI for one official bulk package is a recorded alternative; no external message was sent.",
        "",
    ])


def run_stage_a1(config_path: Path, run_id: str) -> Path:
    if Path.cwd().resolve() != REPO_ROOT:
        raise ValueError(f"run from repository root: {REPO_ROOT}")
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run-id must match YYYYMMDDTHHMMSSZ")
    config = load_config(config_path)
    accepted_inputs = validate_accepted_stage_a(config)
    source_path = resolve_path(config["accepted_stage_a"]["candidate_registry"]["path"])
    original = pd.read_parquet(source_path)
    selected = select_comparison_rows(
        original.to_dict("records"),
        int(config["selection"]["minimum_start_year"]),
        str(config["official_file_list"]["allowed_host"]),
    )
    selected.sort(key=lambda row: chronology_rank_key(row, config["selection"]["mrar_delivery_cutoff_utc"]))
    selected_ids = {str(row["official_cruise_id"]) for row in selected}
    required_ids = set(map(str, config["selection"]["required_report_ids"]))
    if not required_ids.issubset(selected_ids):
        raise ValueError(f"required reported candidates missing from comparison cohort: {sorted(required_ids - selected_ids)}")

    output_root = resolve_path(config["output_root"])
    final_dir = output_root / run_id
    if final_dir.exists():
        raise FileExistsError(f"immutable run already exists: {final_dir}")
    output_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=output_root))
    evidence_dir = temp_dir / "metadata_evidence"
    evidence_dir.mkdir()
    query_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    negative_rows: list[dict[str, Any]] = []
    physical_rows: list[dict[str, Any]] = []
    budget_rows: list[dict[str, Any]] = []
    try:
        for selection_rank, candidate in enumerate(selected, start=1):
            candidate["selection_rank"] = selection_rank
            objects, listing_queries, listing_evidence, listing_negatives = enumerate_cruise_objects(
                candidate, evidence_dir, config["official_file_list"]
            )
            query_rows.extend(listing_queries)
            evidence_rows.extend(listing_evidence)
            negative_rows.extend(listing_negatives)
            head_inputs = [
                (
                    url,
                    str(candidate["official_cruise_id"]),
                    listing_url,
                    selection_rank,
                    int(config["official_file_list"]["request_timeout_seconds"]),
                    str(config["official_file_list"]["user_agent"]),
                )
                for url, listing_url in objects
            ]
            with concurrent.futures.ThreadPoolExecutor(max_workers=int(config["official_file_list"]["head_workers"])) as executor:
                head_results = list(executor.map(lambda args: head_physical_object(*args), head_inputs))
            cruise_physical = [result[0] for result in head_results]
            physical_rows.extend(cruise_physical)
            query_rows.extend(result[1] for result in head_results)
            for record in cruise_physical:
                if record["head_status"] != "success":
                    negative_rows.append({
                        "category": "physical_object_head",
                        "official_cruise_id": str(candidate["official_cruise_id"]),
                        "reason": record["head_error"] or record["head_status"],
                        "evidence": record["direct_url"],
                    })
                elif record["content_length"] is None:
                    negative_rows.append({
                        "category": "physical_object_content_length",
                        "official_cruise_id": str(candidate["official_cruise_id"]),
                        "reason": "head_200_without_content_length",
                        "evidence": record["direct_url"],
                    })
            cruise_frame = pd.DataFrame(cruise_physical, columns=PHYSICAL_COLUMNS)
            listing_failures = sum(row["category"].startswith("directory") for row in listing_negatives)
            budget_rows.append(budget_for_cruise(
                str(candidate["official_cruise_id"]),
                selection_rank,
                str(candidate["archive"]),
                len(listing_queries),
                listing_failures,
                cruise_frame,
            ))

        budget_rows.append(all_candidates_budget(budget_rows))
        physical = pd.DataFrame(physical_rows, columns=PHYSICAL_COLUMNS)
        if len(physical):
            physical["content_length"] = pd.array(physical["content_length"], dtype="Int64")
            physical["head_http_status"] = pd.array(physical["head_http_status"], dtype="Int64")
            physical = physical.sort_values(["selection_rank", "direct_url"]).reset_index(drop=True)
        validate_status_pairs(physical)
        budgets = pd.DataFrame(budget_rows)
        validate_status_pairs(budgets)
        revised = revise_candidate_registry(
            original,
            selected,
            budgets,
            str(config["selection"]["mrar_delivery_cutoff_utc"]),
        )

        rewrite_final_paths(evidence_rows, final_dir)
        rewrite_final_paths(query_rows, final_dir)
        evidence = pd.DataFrame(evidence_rows, columns=[
            "evidence_id", "official_cruise_id", "role", "requested_url", "resolved_url",
            "path", "mime_type", "bytes", "sha256", "http_status",
        ])
        negatives = pd.DataFrame(negative_rows, columns=["category", "official_cruise_id", "reason", "evidence"])
        if not negatives.empty:
            negatives = negatives.sort_values(["official_cruise_id", "category", "evidence"]).reset_index(drop=True)

        physical_path = temp_dir / "physical_object_lock.parquet"
        budget_path = temp_dir / "per_cruise_byte_budget.tsv"
        revised_path = temp_dir / "revised_candidate_registry.parquet"
        evidence_path = temp_dir / "metadata_evidence_registry.tsv"
        query_path = temp_dir / "query_command_ledger.jsonl"
        negatives_path = temp_dir / "negative_result_ledger.tsv"
        atomic_parquet(physical, physical_path)
        atomic_tsv(budgets, budget_path)
        atomic_parquet(revised, revised_path)
        atomic_tsv(evidence, evidence_path)
        atomic_text("".join(stable_json(row) + "\n" for row in query_rows), query_path)
        atomic_tsv(negatives, negatives_path)

        selected_revised = revised[revised["stage_a1_comparison_cohort"]].sort_values("selection_rank")
        total_budget = budgets[budgets["row_type"].eq("all_candidates")].iloc[0]
        revised_lock = {
            "schema_version": 1,
            "run_id": run_id,
            "created_utc": utc_now(),
            "stage": "A.1_metadata_file_list_and_head_only",
            "accepted_stage_a_candidate_registry_sha256": accepted_inputs["candidate_registry"]["sha256"],
            "selection_rule_frozen_before_network_access": True,
            "selection_rule": config["selection"],
            "selected_count": len(selected_revised),
            "selected_candidates": [
                {
                    "official_cruise_id": row.official_cruise_id,
                    "selection_rank": int(row.selection_rank),
                    "directory_url": row.archive,
                    "chronology_risk": row.chronology_risk,
                    "physical_object_count": int(row.physical_object_count),
                    "total_bytes": int(row.physical_total_bytes),
                    "physical_lock_status": row.physical_lock_status,
                    "confirmation_candidate_v2_H_MRAR_out": row.confirmation_candidate_v2_H_MRAR_out,
                    "confirmation_candidate_v2_W_MRAR_in": row.confirmation_candidate_v2_W_MRAR_in,
                    "confirmation_role_eligible": False,
                }
                for row in selected_revised.itertuples(index=False)
            ],
            "all_candidates": {
                "physical_object_count": int(total_budget["physical_object_count"]),
                "head_ok_count": int(total_budget["head_ok_count"]),
                "head_failed_count": int(total_budget["head_failed_count"]),
                "content_length_known_count": int(total_budget["content_length_known_count"]),
                "total_bytes": int(total_budget["total_bytes"]),
                "total_bytes_complete": bool(total_budget["total_bytes_complete"]),
                "physical_lock_status": str(total_budget["physical_lock_status"]),
            },
            "branch_contract": {
                "confirmation_candidate_v2_H_MRAR_out": "pending_seal_and_processing",
                "confirmation_candidate_v2_W_MRAR_in": "blocked_source_independence_unknown",
                "global_confirmation_role_eligible": False,
            },
            "mrar_terminal": {
                "identity_status": "not_recoverable",
                "source_independence": "unknown",
            },
            "bulk_package_alternative": {
                "action": "contact_NCEI_for_single_official_bulk_package",
                "external_message_sent": False,
            },
            "stage_b_authorized": False,
            "official_file_list_metadata_get_count": sum(row["method"] == "GET" for row in query_rows),
            "physical_object_head_count": sum(row["method"] == "HEAD" for row in query_rows),
            "physical_object_get_count": 0,
            "range_get_count": 0,
            "physical_object_body_read_count": 0,
            "candidate_depth_read": False,
            "cell_generation_count": 0,
            "reference_or_model_comparison_count": 0,
            "stage_b_requires_separate_user_approval": True,
        }
        lock_path = temp_dir / "revised_preseal_lock.json"
        atomic_json(revised_lock, lock_path)
        report_path = temp_dir / "audit_report.md"
        atomic_text(render_report(revised, budgets, query_rows), report_path)

        outputs = {
            "physical_object_lock": artifact_record(physical_path, physical),
            "per_cruise_byte_budget": artifact_record(budget_path, budgets),
            "revised_candidate_registry": artifact_record(revised_path, revised),
            "revised_preseal_lock": artifact_record(lock_path, row_count=1),
            "metadata_evidence_registry": artifact_record(evidence_path, evidence),
            "query_command_ledger": artifact_record(query_path, row_count=len(query_rows)),
            "negative_result_ledger": artifact_record(negatives_path, negatives),
            "audit_report": artifact_record(report_path, row_count=len(report_path.read_text(encoding="utf-8").splitlines())),
        }
        for record in outputs.values():
            record["path"] = str(final_dir / Path(record["path"]).name)
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "created_utc": utc_now(),
            "stage": "A.1_metadata_file_list_and_head_only",
            "config": {
                "path": str(config_path.resolve()),
                "bytes": config_path.stat().st_size,
                "sha256": sha256_file(config_path),
            },
            "accepted_stage_a_inputs": accepted_inputs,
            "selection_policy": config["selection"],
            "candidate_counts": {
                "accepted_registry_rows": len(original),
                "comparison_2018plus_unexposed": len(selected),
                "required_report_ids_present": len(required_ids),
                "confirmation_role_eligible": 0,
            },
            "physical_object_counts": revised_lock["all_candidates"],
            "network_method_counts": {
                "official_directory_metadata_get": revised_lock["official_file_list_metadata_get_count"],
                "physical_object_head": revised_lock["physical_object_head_count"],
                "physical_object_get": 0,
                "range_get": 0,
                "physical_object_body_read": 0,
            },
            "branch_contract": revised_lock["branch_contract"],
            "mrar_terminal": revised_lock["mrar_terminal"],
            "prohibited_actions": {
                "stage_b_authorized": False,
                "physical_object_get_count": 0,
                "range_get_count": 0,
                "candidate_depth_read": False,
                "cell_generation_count": 0,
                "reference_or_model_comparison_count": 0,
                "external_message_count": 0,
            },
            "outputs": outputs,
            "metadata_evidence": {
                row["evidence_id"]: {
                    "path": row["path"],
                    "bytes": row["bytes"],
                    "sha256": row["sha256"],
                    "role": row["role"],
                }
                for row in evidence_rows
            },
            "verification_required": True,
            "stage_b_requires_separate_user_approval": True,
        }
        manifest_path = temp_dir / "audit_manifest.json"
        atomic_json(manifest, manifest_path)
        os.replace(temp_dir, final_dir)
        print(stable_json({
            "status": "stage_a1_published_unverified",
            "run_dir": str(final_dir),
            "selected_count": len(selected),
            "physical_object_count": int(total_budget["physical_object_count"]),
            "total_bytes": int(total_budget["total_bytes"]),
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
    parser.add_argument("--confirm-stage-a1", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confirm_stage_a1:
        print("ERROR: Stage A.1 requires --confirm-stage-a1; Stage B is unavailable.", file=sys.stderr)
        return 2
    run_stage_a1(args.config.resolve(), args.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
