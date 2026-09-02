#!/usr/bin/env python3
"""Discover and freeze SCS v2 confirmation candidates from metadata only.

Purpose
-------
Run Stage A only: query official cruise metadata, audit prior exposure in the
two repositories, make candidate decisions, and publish an immutable receipt.

Reads
-----
The frozen inputs and official metadata endpoints named by the YAML config.
Candidate sounding records and candidate archive contents are never requested.

Writes
------
An immutable discovery run below
``ncei/derived/scs_v2_sealed_confirmation/discovery/<RUN_ID>/``. No archive
directory, extracted file, sounding value, cell, residual, or model output is
created.

Usage
-----
Run from the repository root::

    python ncei/code/scs_confirmation/discover_scs_v2_sealed_confirmation.py \
      --config ncei/configs/scs_v2_sealed_confirmation_stage_a.yaml \
      --run-id YYYYMMDDTHHMMSSZ --confirm-stage-a
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z$")
FIELD_STATUSES = {
    "known",
    "officially_unknown",
    "not_recoverable",
    "inferred_from_filename",
    "verified_from_source_metadata",
}
TRI_STATES = {"true", "false", "unknown"}
SEALED_STATES = {"excluded", "selected_unsealed"}
ARCHIVE_SUFFIXES = {
    ".7z", ".bz2", ".dat", ".gz", ".kmall", ".mb", ".nc", ".rar",
    ".s7k", ".tar", ".tgz", ".txt", ".xyz", ".zip",
}
FORBIDDEN_ARCHIVE_MODULES = {
    "libarchive", "netCDF4", "py7zr", "rarfile", "tarfile", "xarray", "zipfile",
}
OFFICIAL_HOST_SUFFIXES = (".noaa.gov", ".jamstec.go.jp")
NCEI_FIELDS = [
    "SURVEY_ID", "PLATFORM", "SURVEY_YEAR", "SOURCE", "NGDC_ID",
    "CHIEF_SCIENTIST", "DEPARTURE_PORT", "ARRIVAL_PORT", "INSTRUMENT",
    "FILE_COUNT", "TRACK_LENGTH", "TOTAL_TIME", "BATHY_BEAMS", "AMP_BEAMS",
    "SIDESCANS", "ENTERED_DATE", "DOWNLOAD_URL", "START_TIME", "END_TIME",
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


def normalize_cruise_id(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = re.sub(r"_MULTIBEAM$", "", text)
    text = re.sub(r"[^A-Z0-9]+", "-", text).strip("-")
    return text


def cruise_aliases(value: Any) -> set[str]:
    normalized = normalize_cruise_id(value)
    if not normalized:
        return set()
    aliases = {normalized}
    aliases.add(re.sub(r"-LEG-?\d+$", "", normalized))
    return {alias for alias in aliases if alias}


def overlaps_ids(candidate: str, exposed: Iterable[str]) -> bool:
    candidate_aliases = cruise_aliases(candidate)
    return any(candidate_aliases & cruise_aliases(item) for item in exposed)


def parse_official_time(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)) and not pd.isna(value):
        seconds = float(value) / 1000.0 if float(value) > 10_000_000_000 else float(value)
        try:
            return datetime.fromtimestamp(seconds, timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return ""
    text = str(value).strip()
    match = re.search(r"(19|20)\d{2}-\d{2}-\d{2}", text)
    return match.group(0) if match else text


def geometry_bbox(geometry: dict[str, Any]) -> list[float] | None:
    points: list[tuple[float, float]] = []
    for key in ("paths", "rings"):
        for part in geometry.get(key, []) or []:
            for coordinate in part:
                if len(coordinate) >= 2:
                    points.append((float(coordinate[0]), float(coordinate[1])))
    for coordinate in geometry.get("points", []) or []:
        if len(coordinate) >= 2:
            points.append((float(coordinate[0]), float(coordinate[1])))
    if "x" in geometry and "y" in geometry:
        points.append((float(geometry["x"]), float(geometry["y"])))
    if not points:
        return None
    xs, ys = zip(*points)
    return [min(xs), min(ys), max(xs), max(ys)]


def bbox_intersects(bbox: list[float] | None, area: dict[str, float]) -> bool:
    if bbox is None or len(bbox) != 4:
        return False
    xmin, ymin, xmax, ymax = bbox
    return xmax >= area["xmin"] and xmin < area["xmax"] and ymax >= area["ymin"] and ymin < area["ymax"]


def clip_segment_to_area(
    first: tuple[float, float],
    second: tuple[float, float],
    area: dict[str, float],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    x1, y1 = first
    x2, y2 = second
    while x2 - x1 > 180.0:
        x2 -= 360.0
    while x2 - x1 < -180.0:
        x2 += 360.0
    for shift in (-360.0, 0.0, 360.0):
        xmin = area["xmin"] + shift
        xmax = math.nextafter(area["xmax"] + shift, float("-inf"))
        ymin = area["ymin"]
        ymax = math.nextafter(area["ymax"], float("-inf"))
        dx = x2 - x1
        dy = y2 - y1
        p = (-dx, dx, -dy, dy)
        q = (x1 - xmin, xmax - x1, y1 - ymin, ymax - y1)
        lower, upper = 0.0, 1.0
        accepted = True
        for pi, qi in zip(p, q):
            if pi == 0.0:
                if qi < 0.0:
                    accepted = False
                    break
                continue
            ratio = qi / pi
            if pi < 0.0:
                lower = max(lower, ratio)
            else:
                upper = min(upper, ratio)
            if lower > upper:
                accepted = False
                break
        if accepted:
            clipped_first = (x1 + lower * dx - shift, y1 + lower * dy)
            clipped_second = (x1 + upper * dx - shift, y1 + upper * dy)
            return clipped_first, clipped_second
    return None


def segment_intersects_area(first: tuple[float, float], second: tuple[float, float], area: dict[str, float]) -> bool:
    return clip_segment_to_area(first, second, area) is not None


def haversine_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, first)
    lon2, lat2 = map(math.radians, second)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    value = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    return 6371.0088 * 2.0 * math.asin(min(1.0, math.sqrt(value)))


def geometry_track_length_in_area_km(geometry: dict[str, Any], area: dict[str, float]) -> float:
    total = 0.0
    for key in ("paths", "rings"):
        for part in geometry.get(key, []) or []:
            points = [(float(point[0]), float(point[1])) for point in part if len(point) >= 2]
            for first, second in zip(points, points[1:]):
                clipped = clip_segment_to_area(first, second, area)
                if clipped is not None:
                    total += haversine_km(*clipped)
    return total


def geometry_intersects_area(geometry: dict[str, Any], area: dict[str, float]) -> bool:
    for key in ("paths", "rings"):
        for part in geometry.get(key, []) or []:
            points = [(float(point[0]), float(point[1])) for point in part if len(point) >= 2]
            if any(segment_intersects_area(first, second, area) for first, second in zip(points, points[1:])):
                return True
            if len(points) == 1 and segment_intersects_area(points[0], points[0], area):
                return True
    for point in geometry.get("points", []) or []:
        if len(point) >= 2 and segment_intersects_area((float(point[0]), float(point[1])), (float(point[0]), float(point[1])), area):
            return True
    if "x" in geometry and "y" in geometry:
        point = (float(geometry["x"]), float(geometry["y"]))
        return segment_intersects_area(point, point, area)
    return False


def official_url(value: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme in {"http", "https"} and any(host.endswith(suffix) for suffix in OFFICIAL_HOST_SUFFIXES)


def strip_html(value: str) -> str:
    text = re.sub(r"<script\b.*?</script>", " ", value, flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_detail_html(body: bytes, page_url: str) -> dict[str, Any]:
    source = body.decode("utf-8", errors="replace")
    plain = strip_html(source)
    distribution_formats = sorted(set(re.findall(r"\b(?:MBF|INFO)_[A-Z0-9_.+-]+\b", plain, flags=re.I)))
    raw_documented = any("RAW" in item.upper() for item in distribution_formats)
    download_url = ""
    for match in re.finditer(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", source, flags=re.I | re.S):
        label = strip_html(match.group(2)).lower()
        if "cruise file list" in label or "download data" in label:
            download_url = urllib.parse.urljoin(page_url, html.unescape(match.group(1)))
            break
    vertical_datum = ""
    datum_match = re.search(r"Vertical\s+Datum\s*[:\-]?\s*([A-Za-z0-9 /_.()+-]{2,80})", plain, flags=re.I)
    if datum_match:
        candidate = datum_match.group(1).strip()
        if not candidate.lower().startswith(("unknown", "not available", "not applicable")):
            vertical_datum = candidate
    has_constraints = bool(re.search(r"\b(?:Use Constraints|Access Constraints|Constraints)\b", plain, flags=re.I))
    return {
        "distribution_formats": distribution_formats,
        "raw_archive_documented": raw_documented,
        "download_url": download_url,
        "vertical_datum": vertical_datum,
        "has_constraints": has_constraints,
    }


@dataclass
class FetchRecorder:
    evidence_dir: Path
    timeout: int
    user_agent: str
    query_rows: list[dict[str, Any]]
    evidence_rows: list[dict[str, Any]]

    def get(self, url: str, filename: str, role: str) -> bytes:
        if role == "candidate_archive":
            raise ValueError("Stage A cannot request a candidate archive")
        suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
        if suffix in ARCHIVE_SUFFIXES and role != "official_metadata":
            raise ValueError(f"Stage A URL looks like an archive or sounding file: {url}")
        path = self.evidence_dir / filename
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json,text/html,application/xml,text/xml;q=0.9,*/*;q=0.1"})
        started = utc_now()
        status = 0
        resolved_url = url
        headers: dict[str, str] = {}
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = int(getattr(response, "status", 200))
                resolved_url = response.geturl()
                headers = {key.lower(): value for key, value in response.headers.items()}
                body = response.read()
        except urllib.error.HTTPError as error:
            status = int(error.code)
            resolved_url = error.geturl()
            headers = {key.lower(): value for key, value in error.headers.items()}
            body = error.read()
        path.write_bytes(body)
        digest = sha256_bytes(body)
        self.query_rows.append({
            "timestamp_utc": started,
            "operation": "official_metadata_get",
            "request_role": role,
            "method": "GET",
            "url": url,
            "resolved_url": resolved_url,
            "http_status": status,
            "response_path": str(path.resolve()),
            "response_bytes": len(body),
            "response_sha256": digest,
            "content_type": headers.get("content-type", ""),
            "etag": headers.get("etag", ""),
            "last_modified": headers.get("last-modified", ""),
            "execution": "python urllib.request.urlopen",
            "replay_command": f"curl --fail --location --silent --show-error --output {path.resolve()} {json.dumps(url)}",
            "candidate_archive_requested": False,
        })
        self.evidence_rows.append({
            "evidence_id": f"metadata_{len(self.evidence_rows) + 1:04d}",
            "role": role,
            "requested_url": url,
            "resolved_url": resolved_url,
            "path": str(path.resolve()),
            "mime_type": headers.get("content-type", ""),
            "bytes": len(body),
            "sha256": digest,
            "http_status": status,
        })
        if status < 200 or status >= 300:
            raise RuntimeError(f"official metadata request failed with HTTP {status}: {url}")
        return body


def load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ValueError("unsupported config schema_version")
    guards = config.get("stage_a_guards", {})
    if guards != {
        "stage_b_authorized": False,
        "candidate_archive_download_allowed": False,
        "candidate_archive_enumeration_allowed": False,
        "candidate_depth_read_allowed": False,
        "cell_generation_allowed": False,
        "reference_or_model_comparison_allowed": False,
    }:
        raise ValueError("Stage A guards must all be explicit false")
    if set(config.get("factual_status_vocabulary", [])) != FIELD_STATUSES:
        raise ValueError("factual status vocabulary drift")
    area = config["study_area"]
    if [area[key] for key in ("xmin", "ymin", "xmax", "ymax")] != [105.0, 0.0, 125.0, 25.0]:
        raise ValueError("SCS rectangle drift")
    selection = config["selection"]
    if selection["minimum_required"] != 0 or not 0 <= selection["maximum_selected"] <= 5:
        raise ValueError("Stage A must permit zero and select at most five")
    return config


def validate_frozen_inputs(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for role, item in config["frozen_inputs"].items():
        path = resolve_path(item["path"])
        if not path.is_file():
            raise FileNotFoundError(f"missing frozen input {role}: {path}")
        actual = sha256_file(path)
        if actual != item["sha256"]:
            raise ValueError(f"frozen input SHA256 drift for {role}: {actual}")
        records[role] = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": actual,
        }
    return records


def load_exposed_sets(config: dict[str, Any]) -> tuple[list[str], list[str]]:
    current = pd.read_csv(resolve_path(config["frozen_inputs"]["current_19"]["path"]), sep="\t", usecols=["official_cruise_id"])
    current_ids = sorted(set(current["official_cruise_id"].dropna().astype(str)))
    exposed = pd.read_csv(resolve_path(config["frozen_inputs"]["exposed_12"]["path"]), usecols=["cruise_id_candidate"])
    exposed_ids = sorted(set(exposed["cruise_id_candidate"].dropna().astype(str)))
    if len(current_ids) != 19 or len(exposed_ids) != 12:
        raise ValueError(f"frozen exposure closure failed: current={len(current_ids)}, exposed={len(exposed_ids)}")
    if not set(exposed_ids).issubset(set(current_ids)):
        raise ValueError("exposed 12 are not a subset of current 19")
    confirmation = json.loads(resolve_path(config["frozen_inputs"]["downstream_confirmation_registry"]["path"]).read_text(encoding="utf-8"))
    if sorted(confirmation.get("audited_current_official_cruises", [])) != current_ids:
        raise ValueError("downstream confirmation registry does not close to current 19")
    if confirmation.get("status") != "no_pristine_confirmation_available" or confirmation.get("model_or_product_residual_used") is not False:
        raise ValueError("downstream confirmation evidence ceiling drift")
    return current_ids, exposed_ids


def arcgis_query_url(config: dict[str, Any], offset: int) -> str:
    area = config["study_area"]
    base = config["official_metadata"]["ncei_layer_url"].rstrip("/") + "/query"
    params = {
        "where": "1=1",
        "geometry": stable_json({
            "xmin": area["xmin"], "ymin": area["ymin"],
            "xmax": area["xmax"], "ymax": area["ymax"],
            "spatialReference": {"wkid": 4326},
        }),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": ",".join(NCEI_FIELDS),
        "returnGeometry": "true",
        "returnZ": "false",
        "returnM": "false",
        "orderByFields": "SURVEY_ID ASC",
        "resultOffset": str(offset),
        "resultRecordCount": str(config["official_metadata"]["ncei_page_size"]),
        "f": "json",
    }
    return base + "?" + urllib.parse.urlencode(params)


def query_ncei_features(config: dict[str, Any], fetcher: FetchRecorder) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    page_size = int(config["official_metadata"]["ncei_page_size"])
    offset = 0
    page = 0
    while True:
        body = fetcher.get(arcgis_query_url(config, offset), f"ncei_arcgis_page_{page:03d}.json", "ncei_arcgis_spatial_query")
        payload = json.loads(body)
        if "error" in payload:
            raise RuntimeError(f"NCEI ArcGIS error: {payload['error']}")
        batch = payload.get("features", [])
        features.extend(batch)
        if not batch or not payload.get("exceededTransferLimit", False):
            break
        offset += len(batch)
        page += 1
        if page > 100 or len(batch) > page_size:
            raise RuntimeError("NCEI ArcGIS pagination guard triggered")
    return features


def coalesce_features(features: list[dict[str, Any]], area: dict[str, float]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for feature in features:
        attrs = feature.get("attributes") or {}
        survey_id = str(attrs.get("SURVEY_ID") or "").strip()
        key = normalize_cruise_id(survey_id) or f"missing-{len(grouped):06d}"
        grouped.setdefault(key, []).append(feature)
    rows: list[dict[str, Any]] = []
    for _, group in grouped.items():
        attrs = group[0].get("attributes") or {}
        bboxes = [bbox for bbox in (geometry_bbox(item.get("geometry") or {}) for item in group) if bbox]
        bbox = None
        if bboxes:
            bbox = [min(item[0] for item in bboxes), min(item[1] for item in bboxes), max(item[2] for item in bboxes), max(item[3] for item in bboxes)]
        start = parse_official_time(attrs.get("START_TIME"))
        end = parse_official_time(attrs.get("END_TIME"))
        if not start and attrs.get("SURVEY_YEAR") not in (None, ""):
            start = str(attrs.get("SURVEY_YEAR"))
        date = "/".join(part for part in (start, end) if part)
        file_count_value = pd.to_numeric(attrs.get("FILE_COUNT"), errors="coerce")
        file_count = int(file_count_value) if pd.notna(file_count_value) else None
        beams_value = pd.to_numeric(attrs.get("BATHY_BEAMS"), errors="coerce")
        rows.append({
            "official_cruise_id": str(attrs.get("SURVEY_ID") or "").strip(),
            "provider": "NCEI",
            "platform": str(attrs.get("PLATFORM") or "").strip(),
            "date": date,
            "start_date": start,
            "end_date": end,
            "instrument": str(attrs.get("INSTRUMENT") or "").strip(),
            "bbox_value": bbox,
            "bbox": stable_json(bbox) if bbox else "",
            "file_count": file_count,
            "bathy_beams_documented": bool(pd.notna(beams_value) and float(beams_value) > 0),
            "archive": str(attrs.get("DOWNLOAD_URL") or "").strip(),
            "source": str(attrs.get("SOURCE") or "").strip(),
            "ngdc_id": str(attrs.get("NGDC_ID") or "").strip(),
            "entered_date": parse_official_time(attrs.get("ENTERED_DATE")),
            "official_feature_count": len(group),
            "geometry_intersects_scs": any(
                geometry_intersects_area(item.get("geometry") or {}, area) for item in group
            ),
            "scs_track_length_km": sum(
                geometry_track_length_in_area_km(item.get("geometry") or {}, area) for item in group
            ),
        })
    return rows


def preliminary_sort_key(row: dict[str, Any], cutoff_date: str) -> tuple[Any, ...]:
    start = row.get("start_date", "")
    post_delivery = bool(re.match(r"^\d{4}-\d{2}-\d{2}$", start) and start >= cutoff_date)
    metadata_count = sum(bool(row.get(key)) for key in ("official_cruise_id", "date", "instrument", "bbox", "archive", "file_count"))
    return (
        0 if post_delivery else 1,
        -float(row.get("scs_track_length_km", 0.0)),
        0 if row.get("bathy_beams_documented") else 1,
        -metadata_count,
        normalize_cruise_id(row.get("official_cruise_id")),
    )


def fetch_candidate_details(rows: list[dict[str, Any]], config: dict[str, Any], fetcher: FetchRecorder, negatives: list[dict[str, Any]]) -> None:
    cutoff_date = config["selection"]["mrar_delivery_cutoff_utc"][:10]
    ordered = sorted(rows, key=lambda row: preliminary_sort_key(row, cutoff_date))
    limit = int(config["selection"]["maximum_detail_queries"])
    template = config["official_metadata"]["ncei_item_template"]
    for index, row in enumerate(ordered):
        row["detail_evaluated"] = False
        row["detail_error"] = ""
        row["detail_metadata_url"] = ""
        row["detail_metadata_sha256"] = ""
        row["distribution_formats"] = []
        row["raw_archive_documented"] = False
        row["vertical_datum"] = ""
        row["license"] = ""
        row["license_status"] = "officially_unknown"
        if index >= limit:
            row["detail_error"] = "maximum_detail_queries_reached"
            continue
        survey_id = row["official_cruise_id"]
        if not survey_id:
            row["detail_error"] = "missing_official_cruise_id"
            continue
        url = template.format(survey_id=urllib.parse.quote(survey_id, safe=""))
        filename = f"ncei_item_{index:03d}_{re.sub(r'[^A-Za-z0-9_.-]+', '_', survey_id)}.html"
        try:
            body = fetcher.get(url, filename, "official_metadata")
        except Exception as error:
            row["detail_error"] = f"official_metadata_request_failed:{type(error).__name__}"
            negatives.append({"category": "metadata_request", "official_cruise_id": survey_id, "reason": row["detail_error"], "evidence": url})
            continue
        detail = parse_detail_html(body, url)
        row["detail_evaluated"] = True
        row["detail_metadata_url"] = url
        row["detail_metadata_sha256"] = sha256_bytes(body)
        row["distribution_formats"] = detail["distribution_formats"]
        row["raw_archive_documented"] = detail["raw_archive_documented"]
        row["vertical_datum"] = detail["vertical_datum"]
        if detail["download_url"] and official_url(detail["download_url"]):
            row["archive"] = detail["download_url"]
        if detail["has_constraints"]:
            row["license"] = "candidate-specific NCEI metadata constraints section"
            row["license_status"] = "verified_from_source_metadata"


def run_git(repo: Path, args: list[str], query_rows: list[dict[str, Any]], role: str) -> str:
    command = ["git", "-C", str(repo), *args]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    stdout = completed.stdout
    query_rows.append({
        "timestamp_utc": utc_now(),
        "operation": "repository_identity_audit",
        "request_role": role,
        "method": "local_git",
        "url": "",
        "resolved_url": "",
        "http_status": "",
        "response_path": "",
        "response_bytes": len(stdout.encode("utf-8")),
        "response_sha256": sha256_bytes(stdout.encode("utf-8")),
        "content_type": "text/plain",
        "etag": "",
        "last_modified": "",
        "execution": "subprocess.run",
        "replay_command": " ".join(json.dumps(part) for part in command),
        "exit_status": completed.returncode,
        "candidate_archive_requested": False,
    })
    if completed.returncode not in (0, 1):
        raise RuntimeError(f"git command failed ({completed.returncode}): {' '.join(command)}\n{completed.stderr[:500]}")
    return stdout


def repository_snapshot(repo: Path, query_rows: list[dict[str, Any]], role: str) -> dict[str, Any]:
    head = run_git(repo, ["rev-parse", "HEAD"], query_rows, f"{role}_head").strip()
    status = run_git(repo, ["status", "--short"], query_rows, f"{role}_status")
    return {
        "path": str(repo.resolve()),
        "head": head,
        "dirty": bool(status.strip()),
        "status_paths": [line[3:] for line in status.splitlines() if len(line) >= 4],
        "status_sha256": sha256_bytes(status.encode("utf-8")),
    }


def repository_file_inventory(repositories: dict[str, Path], query_rows: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for repository, root in repositories.items():
        relative_paths: list[str] = []
        for directory, directory_names, filenames in os.walk(root):
            current = Path(directory)
            relative_dir = current.relative_to(root)
            directory_names[:] = sorted(
                name for name in directory_names
                if name not in {".git", ".venv", "node_modules", "__pycache__"}
                and not (
                    repository == "ship"
                    and (relative_dir / name).as_posix().startswith(
                        "ncei/derived/scs_v2_sealed_confirmation/discovery"
                    )
                )
            )
            for filename in sorted(filenames):
                relative_paths.append((relative_dir / filename).as_posix())
        payload = "\n".join(relative_paths).encode("utf-8")
        query_rows.append({
            "timestamp_utc": utc_now(),
            "operation": "repository_filename_inventory",
            "request_role": f"{repository}_all_file_names",
            "method": "local_filesystem_names_only",
            "url": "",
            "resolved_url": "",
            "http_status": "",
            "response_path": "",
            "response_bytes": len(payload),
            "response_sha256": sha256_bytes(payload),
            "content_type": "text/plain path inventory",
            "etag": "",
            "last_modified": "",
            "execution": "os.walk names only; file contents not opened",
            "replay_command": f"find {root} -type f -printf '%P\\n' with .git/runtime exclusions",
            "exit_status": 0,
            "candidate_archive_requested": False,
        })
        rows.extend({"repository": repository, "relative_path": path} for path in relative_paths)
    return pd.DataFrame(rows, columns=["repository", "relative_path"])


def identity_filesystem_hits(inventory: pd.DataFrame, cruise_id: str) -> list[dict[str, str]]:
    aliases = cruise_aliases(cruise_id)
    hits: list[dict[str, str]] = []
    for row in inventory.itertuples(index=False):
        normalized_path = normalize_cruise_id(row.relative_path)
        for alias in aliases:
            if re.search(rf"(?:^|-){re.escape(alias)}(?:-|$)", normalized_path):
                hits.append({
                    "repository": row.repository,
                    "scope": "current_filesystem_filename",
                    "identity": alias,
                    "path": row.relative_path,
                    "commit": "",
                })
                break
    return hits


def identity_git_hits(repo: Path, cruise_id: str, query_rows: list[dict[str, Any]], role: str) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    searched: set[str] = set()
    for alias in sorted(cruise_aliases(cruise_id)):
        for search_value in {alias, alias.replace("-", "_")}:
            if search_value in searched:
                continue
            searched.add(search_value)
            current = run_git(repo, ["grep", "-I", "-l", "-F", search_value, "--", "."], query_rows, f"{role}_current_identity")
            for path in current.splitlines():
                if "scs_v2_sealed_confirmation/discovery" not in path:
                    hits.append({"repository": role, "scope": "current_tracked_text", "identity": search_value, "path": path, "commit": ""})
            history = run_git(repo, ["log", "--all", f"-S{search_value}", "--format=COMMIT:%H", "--name-only", "--", "."], query_rows, f"{role}_history_identity")
            commit = ""
            for line in history.splitlines():
                if line.startswith("COMMIT:"):
                    commit = line.split(":", 1)[1]
                elif line.strip() and "scs_v2_sealed_confirmation/discovery" not in line:
                    hits.append({"repository": role, "scope": "git_history_identity", "identity": search_value, "path": line.strip(), "commit": commit})
    unique = {(item["repository"], item["scope"], item["identity"], item["path"], item["commit"]): item for item in hits}
    return list(unique.values())


def mrar_followup(config: dict[str, Any], query_rows: list[dict[str, Any]]) -> pd.DataFrame:
    identity_path = resolve_path(config["frozen_inputs"]["mrar_identity_ledger"]["path"])
    source_inventory = resolve_path(config["frozen_inputs"]["mrar_source_inventory"]["path"])
    source_path = resolve_path(config["frozen_inputs"]["mrar_source"]["path"])
    prior = pd.read_csv(identity_path, sep="\t")
    terminal = prior[prior["claim_id"].eq("source_independence")]
    if len(terminal) != 1 or terminal.iloc[0]["identity_status"] != "not_recoverable" or terminal.iloc[0]["source_independence"] != "unknown":
        raise ValueError("prior MRAR terminal state drift")
    source_text = source_path.read_text(encoding="utf-8", errors="replace")
    direct_terms = sorted(term for term in ("Tscs", "RIAM", "Uehara") if term.lower() in source_text.lower())
    history = run_git(REPO_ROOT, ["log", "--all", "-G(Tscs|RIAM|Uehara)", "--format=COMMIT:%H", "--name-only", "--", "ncei/archive/zhoushuai_processed_M"], query_rows, "mrar_adjacent_history")
    history_paths = sorted({line for line in history.splitlines() if line and not line.startswith("COMMIT:")})
    new_direct = bool(direct_terms or history_paths)
    # A matching term in provenance prose would still require an artifact-level
    # mapping. Preserve the evidence ceiling unless such a mapping is present.
    direct_mapping = new_direct and bool(re.search(r"M\.rar.{0,120}(?:Tscs|RIAM|Uehara)|(?:Tscs|RIAM|Uehara).{0,120}M\.rar", source_text, flags=re.I | re.S))
    identity_status = "known" if direct_mapping else "not_recoverable"
    independence = "known" if direct_mapping else "unknown"
    rows = [
        {
            "check_id": "prior_verified_identity_ledger",
            "scope": "frozen prior bounded audit",
            "direct_evidence_found": False,
            "evidence_paths_json": stable_json([str(identity_path)]),
            "finding": "prior audit closed without direct M.rar to Tscs/RIAM/Uehara evidence",
            "identity_status": "not_recoverable",
            "source_independence": "unknown",
        },
        {
            "check_id": "archive_metadata_and_members",
            "scope": "frozen source inventory; candidate archives not touched",
            "direct_evidence_found": False,
            "evidence_paths_json": stable_json([str(source_inventory)]),
            "finding": "retained M.rar member names are quadrant files and contain no source mapping",
            "identity_status": "not_recoverable",
            "source_independence": "unknown",
        },
        {
            "check_id": "adjacent_readme_license_and_git_history",
            "scope": "SOURCE.md plus bounded path-only git history search",
            "direct_evidence_found": bool(direct_mapping),
            "evidence_paths_json": stable_json([str(source_path), *history_paths]),
            "finding": "direct artifact mapping found" if direct_mapping else "no new direct artifact mapping found",
            "identity_status": identity_status,
            "source_independence": independence,
        },
        {
            "check_id": "terminal",
            "scope": "bounded branch stop",
            "direct_evidence_found": bool(direct_mapping),
            "evidence_paths_json": stable_json([str(identity_path), str(source_inventory), str(source_path)]),
            "finding": "direct mapping established" if direct_mapping else "search stopped at retained evidence ceiling",
            "identity_status": identity_status,
            "source_independence": independence,
        },
    ]
    frame = pd.DataFrame(rows)
    for column in ("check_id", "scope", "direct_evidence_found", "evidence_paths_json", "finding", "identity_status", "source_independence"):
        frame[f"{column}_status"] = "known"
    if not direct_mapping:
        frame.loc[:, "identity_status_status"] = "not_recoverable"
        frame.loc[:, "source_independence_status"] = "not_recoverable"
    return frame


def available_fields(row: dict[str, Any]) -> dict[str, str]:
    return {
        "time": "cruise_metadata_only" if row.get("date") else "officially_unknown",
        "line": "officially_unknown",
        "navigation": "verified_from_source_metadata" if row.get("bbox") else "officially_unknown",
        "ping": "officially_unknown",
        "beam": "verified_from_source_metadata" if row.get("bathy_beams_documented") else "officially_unknown",
        "quality_flag": "officially_unknown",
        "vertical_datum": "verified_from_source_metadata" if row.get("vertical_datum") else "officially_unknown",
    }


def detail_rank_key(row: dict[str, Any]) -> tuple[Any, ...]:
    fields = available_fields(row)
    field_count = sum(value == "verified_from_source_metadata" for value in fields.values())
    metadata_complete = sum(bool(row.get(key)) for key in ("date", "instrument", "bbox", "archive", "file_count", "license"))
    mrar_order = {"false": 0, "unknown": 1, "true": 2}.get(row.get("possible_MRAR_overlap", "unknown"), 1)
    return (
        mrar_order,
        -float(row.get("scs_track_length_km", 0.0)),
        0 if row.get("raw_archive_documented") else 1,
        -field_count,
        0 if row.get("vertical_datum") else 1,
        -metadata_complete,
        normalize_cruise_id(row.get("official_cruise_id")),
    )


def build_candidate_registry(
    rows: list[dict[str, Any]],
    config: dict[str, Any],
    current_ids: list[str],
    exposed_ids: list[str],
    repositories: dict[str, Path],
    file_inventory: pd.DataFrame,
    query_rows: list[dict[str, Any]],
    exposure_rows: list[dict[str, Any]],
    negatives: list[dict[str, Any]],
) -> pd.DataFrame:
    cutoff = config["selection"]["mrar_delivery_cutoff_utc"][:10]
    for row in rows:
        row["overlap_with_current_19"] = "true" if overlaps_ids(row["official_cruise_id"], current_ids) else "false"
        row["overlap_with_exposed_12"] = "true" if overlaps_ids(row["official_cruise_id"], exposed_ids) else "false"
        start = row.get("start_date", "")
        if re.match(r"^\d{4}-\d{2}-\d{2}$", start) and start > cutoff:
            row["possible_MRAR_overlap"] = "false"
            row["possible_mrar_basis"] = "official survey start is after retained M.rar delivery cutoff"
        else:
            row["possible_MRAR_overlap"] = "unknown"
            row["possible_mrar_basis"] = "MRAR identity is not recoverable and chronology does not exclude membership"
        row["repository_hits"] = []
        row["ever_read_by_repo"] = "unknown"

    ordered = sorted((row for row in rows if row.get("detail_evaluated")), key=detail_rank_key)
    selected: list[dict[str, Any]] = []
    maximum = int(config["selection"]["maximum_selected"])
    for row in ordered:
        basic_failures = []
        if not row["official_cruise_id"]:
            basic_failures.append("missing_official_cruise_id")
        if not row["date"]:
            basic_failures.append("missing_official_date")
        if not row["instrument"]:
            basic_failures.append("missing_instrument")
        if not row["geometry_intersects_scs"]:
            basic_failures.append("official_geometry_not_in_scs")
        if not row["archive"] or not official_url(row["archive"]):
            basic_failures.append("missing_stable_official_archive_access_url")
        if row["license_status"] != "verified_from_source_metadata":
            basic_failures.append("candidate_specific_license_not_verified")
        if row["overlap_with_current_19"] == "true":
            basic_failures.append("overlap_current_19")
        if row["overlap_with_exposed_12"] == "true":
            basic_failures.append("overlap_exposed_12")
        if basic_failures:
            row["qualification_failures"] = basic_failures
            continue
        all_hits = identity_filesystem_hits(file_inventory, row["official_cruise_id"])
        if not all_hits:
            for repo_role, repo in repositories.items():
                all_hits.extend(identity_git_hits(repo, row["official_cruise_id"], query_rows, repo_role))
        row["repository_hits"] = all_hits
        row["ever_read_by_repo"] = "true" if all_hits else "false"
        for hit in all_hits:
            exposure_rows.append({"exposure_class": "repository_identity_hit", "official_cruise_id": row["official_cruise_id"], **hit})
        if all_hits:
            row["qualification_failures"] = ["prior_repository_identity_hit"]
            continue
        row["qualification_failures"] = []
        if len(selected) < maximum:
            selected.append(row)

    selected_ids = {id(row) for row in selected}
    records: list[dict[str, Any]] = []
    rank = 0
    for row in sorted(rows, key=lambda item: (detail_rank_key(item), normalize_cruise_id(item.get("official_cruise_id")))):
        failures = list(row.get("qualification_failures", []))
        if not row.get("detail_evaluated"):
            failures.append(row.get("detail_error") or "detail_not_evaluated")
        selected_row = id(row) in selected_ids
        if selected_row:
            rank += 1
        elif not failures and row.get("detail_evaluated"):
            failures.append("selection_limit_reached")
        if failures:
            negatives.append({
                "category": "candidate_exclusion",
                "official_cruise_id": row.get("official_cruise_id", ""),
                "reason": ";".join(sorted(set(failures))),
                "evidence": row.get("detail_metadata_url", "") or "NCEI ArcGIS spatial metadata",
            })
        fields = available_fields(row)
        vertical = row.get("vertical_datum", "")
        record = {
            "official_cruise_id": row.get("official_cruise_id", ""),
            "official_cruise_id_status": "verified_from_source_metadata" if row.get("official_cruise_id") else "officially_unknown",
            "archive": row.get("archive", ""),
            "archive_status": "verified_from_source_metadata" if row.get("archive") and official_url(row["archive"]) else "officially_unknown",
            "date": row.get("date", ""),
            "date_status": "verified_from_source_metadata" if row.get("date") else "officially_unknown",
            "instrument": row.get("instrument", ""),
            "instrument_status": "verified_from_source_metadata" if row.get("instrument") else "officially_unknown",
            "bbox": row.get("bbox", ""),
            "bbox_status": "verified_from_source_metadata" if row.get("bbox") else "officially_unknown",
            "geometry_intersects_scs": bool(row.get("geometry_intersects_scs")),
            "geometry_intersects_scs_status": "verified_from_source_metadata",
            "geometry_basis": "official_polyline_segment_intersection",
            "geometry_basis_status": "known",
            "scs_track_length_km": float(row.get("scs_track_length_km", 0.0)),
            "scs_track_length_km_status": "verified_from_source_metadata",
            "file_count": row.get("file_count"),
            "file_count_status": "verified_from_source_metadata" if row.get("file_count") is not None else "officially_unknown",
            "available_fields": stable_json(fields),
            "available_fields_status": "verified_from_source_metadata",
            "vertical_datum": vertical,
            "vertical_datum_status": "verified_from_source_metadata" if vertical else "officially_unknown",
            "overlap_with_current_19": row["overlap_with_current_19"],
            "overlap_with_current_19_status": "known",
            "overlap_with_exposed_12": row["overlap_with_exposed_12"],
            "overlap_with_exposed_12_status": "known",
            "possible_MRAR_overlap": row["possible_MRAR_overlap"],
            "possible_MRAR_overlap_status": "known" if row["possible_MRAR_overlap"] == "false" else "not_recoverable",
            "ever_read_by_repo": row["ever_read_by_repo"],
            "ever_read_by_repo_status": "known" if row["ever_read_by_repo"] != "unknown" else "not_recoverable",
            "sealed_status": "selected_unsealed" if selected_row else "excluded",
            "sealed_status_status": "known",
            "exclusion_reason": "" if selected_row else ";".join(sorted(set(failures))),
            "exclusion_reason_status": "known",
            "provider": row.get("provider", "NCEI"),
            "provider_status": "verified_from_source_metadata",
            "platform": row.get("platform", ""),
            "platform_status": "verified_from_source_metadata" if row.get("platform") else "officially_unknown",
            "source_metadata_url": row.get("detail_metadata_url", ""),
            "source_metadata_url_status": "verified_from_source_metadata" if row.get("detail_metadata_url") else "officially_unknown",
            "source_metadata_sha256": row.get("detail_metadata_sha256", ""),
            "source_metadata_sha256_status": "known" if row.get("detail_metadata_sha256") else "officially_unknown",
            "distribution_formats": stable_json(row.get("distribution_formats", [])),
            "distribution_formats_status": "verified_from_source_metadata" if row.get("detail_evaluated") else "officially_unknown",
            "raw_archive_documented": bool(row.get("raw_archive_documented")),
            "raw_archive_documented_status": "verified_from_source_metadata" if row.get("detail_evaluated") else "officially_unknown",
            "license": row.get("license", ""),
            "license_status": row.get("license_status", "officially_unknown"),
            "possible_mrar_basis": row["possible_mrar_basis"],
            "possible_mrar_basis_status": "known",
            "repository_identity_hits_json": stable_json(row.get("repository_hits", [])),
            "repository_identity_hits_json_status": "known" if row["ever_read_by_repo"] != "unknown" else "not_recoverable",
            "candidate_qualification": "qualified_for_stage_b_review" if selected_row else "excluded",
            "candidate_qualification_status": "known",
            "confirmation_role_eligible": bool(selected_row and row["possible_MRAR_overlap"] == "false"),
            "confirmation_role_eligible_status": "known",
            "selection_rank": rank if selected_row else -1,
            "selection_rank_status": "known",
        }
        records.append(record)
    frame = pd.DataFrame(records)
    frame["file_count"] = pd.array(frame["file_count"], dtype="Int64")
    return frame


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
            raise ValueError(f"invalid statuses in {column}: {sorted(invalid)}")


def dataframe_schema(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{"name": column, "dtype": str(frame[column].dtype), "nullable": bool(frame[column].isna().any())} for column in frame.columns]


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


def render_report(candidate: pd.DataFrame, negatives: pd.DataFrame, mrar: pd.DataFrame, snapshots: dict[str, Any]) -> str:
    selected = candidate[candidate["sealed_status"].eq("selected_unsealed")]
    eligible = selected[selected["confirmation_role_eligible"]]
    lines = [
        "# SCS v2 sealed confirmation acquisition: Stage A",
        "",
        "## Boundary",
        "",
        "This run used official metadata and repository identity evidence only. It did not download or enumerate candidate archives, read candidate sounding/depth values, generate cells, or use GEBCO, product, QC-error, GGM, PINN, or model residuals.",
        "",
        "## Result",
        "",
        f"- Inspected official cruise records: {len(candidate)}",
        f"- Selected for Stage B review, still unsealed: {len(selected)}",
        f"- Selected with MRAR chronological non-overlap: {len(eligible)}",
        f"- Excluded/not fully qualified: {len(candidate) - len(selected)}",
        f"- Negative-result rows: {len(negatives)}",
        "- Stage B authorization: false",
        "",
        "Selected IDs: " + (", ".join(selected["official_cruise_id"].astype(str)) if len(selected) else "none"),
        "",
        "## MRAR terminal state",
        "",
        f"- identity_status: {mrar.iloc[-1]['identity_status']}",
        f"- source_independence: {mrar.iloc[-1]['source_independence']}",
        "- No open-ended attribution search was performed.",
        "",
        "## Repository snapshots",
        "",
    ]
    for name, snapshot in snapshots.items():
        lines.append(f"- {name}: `{snapshot['head']}`; dirty={str(snapshot['dirty']).lower()}")
    lines.extend(["", "Stage A stops at this receipt. Candidate archive access requires separate user approval.", ""])
    return "\n".join(lines)


def prepare_exposure_rows(current_ids: list[str], exposed_ids: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cruise_id in current_ids:
        rows.append({"exposure_class": "current_19", "official_cruise_id": cruise_id, "repository": "ship", "scope": "frozen_lineage_v2", "identity": normalize_cruise_id(cruise_id), "path": "", "commit": ""})
    for cruise_id in exposed_ids:
        rows.append({"exposure_class": "exposed_12", "official_cruise_id": cruise_id, "repository": "downstream", "scope": "frozen_external_groups", "identity": normalize_cruise_id(cruise_id), "path": "", "commit": ""})
    return rows


def finalize_metadata_paths(
    evidence_rows: list[dict[str, Any]],
    query_rows: list[dict[str, Any]],
    final_dir: Path,
) -> None:
    evidence_dir = final_dir / "metadata_evidence"
    for row in evidence_rows:
        row["path"] = str(evidence_dir / Path(row["path"]).name)
    for row in query_rows:
        if row.get("response_path"):
            row["response_path"] = str(evidence_dir / Path(row["response_path"]).name)


def run_stage_a(config_path: Path, run_id: str) -> Path:
    if Path.cwd().resolve() != REPO_ROOT:
        raise ValueError(f"run from repository root: {REPO_ROOT}")
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run-id must match YYYYMMDDTHHMMSSZ")
    config = load_config(config_path)
    inputs = validate_frozen_inputs(config)
    current_ids, exposed_ids = load_exposed_sets(config)
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
    fetcher = FetchRecorder(
        evidence_dir=evidence_dir,
        timeout=int(config["official_metadata"]["request_timeout_seconds"]),
        user_agent=str(config["official_metadata"]["user_agent"]),
        query_rows=query_rows,
        evidence_rows=evidence_rows,
    )
    try:
        for filename, role, url in (
            ("ncei_layer_schema.json", "ncei_layer_schema", config["official_metadata"]["ncei_layer_url"] + "?f=pjson"),
            ("ncei_access_terms.html", "ncei_access_terms", config["official_metadata"]["ncei_license_url"]),
            ("ncei_submission_metadata.html", "ncei_submission_metadata", config["official_metadata"]["ncei_submission_metadata_url"]),
            ("jamstec_catalog.html", "jamstec_catalog_bounded_pass", config["official_metadata"]["jamstec_catalog_url"]),
            ("jamstec_policy.html", "jamstec_policy", config["official_metadata"]["jamstec_policy_url"]),
        ):
            try:
                fetcher.get(url, filename, role)
            except Exception as error:
                negative_rows.append({"category": "official_source", "official_cruise_id": "", "reason": f"{role}:{type(error).__name__}", "evidence": url})
        features = query_ncei_features(config, fetcher)
        rows = coalesce_features(features, config["study_area"])
        fetch_candidate_details(rows, config, fetcher, negative_rows)

        repositories = {name: Path(path).resolve() for name, path in config["repositories"].items()}
        snapshots = {name: repository_snapshot(repo, query_rows, name) for name, repo in repositories.items()}
        file_inventory = repository_file_inventory(repositories, query_rows)
        mrar = mrar_followup(config, query_rows)
        exposure_rows = prepare_exposure_rows(current_ids, exposed_ids)
        candidate = build_candidate_registry(
            rows, config, current_ids, exposed_ids, repositories, file_inventory,
            query_rows, exposure_rows, negative_rows,
        )
        validate_status_pairs(candidate)
        validate_status_pairs(mrar)
        finalize_metadata_paths(evidence_rows, query_rows, final_dir)

        exposure = pd.DataFrame(exposure_rows).sort_values(["exposure_class", "official_cruise_id", "repository", "path"]).reset_index(drop=True)
        evidence = pd.DataFrame(evidence_rows)
        negatives = pd.DataFrame(negative_rows, columns=["category", "official_cruise_id", "reason", "evidence"])
        queries_path = temp_dir / "query_command_ledger.jsonl"
        atomic_text("".join(stable_json(row) + "\n" for row in query_rows), queries_path)
        candidate_path = temp_dir / "candidate_registry.parquet"
        exposure_path = temp_dir / "exposure_registry.parquet"
        file_inventory_path = temp_dir / "repository_file_inventory.tsv"
        evidence_path = temp_dir / "metadata_evidence_registry.tsv"
        negatives_path = temp_dir / "negative_result_ledger.tsv"
        mrar_path = temp_dir / "mrar_bounded_followup.tsv"
        atomic_parquet(candidate, candidate_path)
        atomic_parquet(exposure, exposure_path)
        atomic_tsv(file_inventory, file_inventory_path)
        atomic_tsv(evidence, evidence_path)
        atomic_tsv(negatives, negatives_path)
        atomic_tsv(mrar, mrar_path)

        selected = candidate[candidate["sealed_status"].eq("selected_unsealed")].sort_values("selection_rank")
        preseal = {
            "schema_version": 1,
            "run_id": run_id,
            "created_utc": utc_now(),
            "stage": "A_metadata_only",
            "stage_b_authorized": False,
            "candidate_archive_download_count": 0,
            "candidate_archive_enumeration_count": 0,
            "candidate_depth_read": False,
            "cell_generation_count": 0,
            "reference_or_model_comparison_count": 0,
            "candidate_registry_sha256": sha256_file(candidate_path),
            "selected_count": len(selected),
            "selected_candidates": [
                {"official_cruise_id": row.official_cruise_id, "archive_access_url": row.archive, "selection_rank": int(row.selection_rank), "confirmation_role_eligible": bool(row.confirmation_role_eligible)}
                for row in selected.itertuples(index=False)
            ],
        }
        preseal_path = temp_dir / "preseal_lock.json"
        atomic_json(preseal, preseal_path)
        report_path = temp_dir / "audit_report.md"
        atomic_text(render_report(candidate, negatives, mrar, snapshots), report_path)

        final_paths = {path.name: final_dir / path.name for path in temp_dir.iterdir() if path.is_file()}
        outputs = {
            "candidate_registry": artifact_record(candidate_path, candidate),
            "exposure_registry": artifact_record(exposure_path, exposure),
            "repository_file_inventory": artifact_record(file_inventory_path, file_inventory),
            "metadata_evidence_registry": artifact_record(evidence_path, evidence),
            "query_command_ledger": artifact_record(queries_path, row_count=len(query_rows)),
            "negative_result_ledger": artifact_record(negatives_path, negatives),
            "mrar_bounded_followup": artifact_record(mrar_path, mrar),
            "preseal_lock": artifact_record(preseal_path, row_count=1),
            "audit_report": artifact_record(report_path, row_count=len(report_path.read_text(encoding="utf-8").splitlines())),
        }
        for record in outputs.values():
            record["path"] = str(final_dir / Path(record["path"]).name)
        evidence_artifacts = {
            row["evidence_id"]: {
                "path": str(final_dir / "metadata_evidence" / Path(row["path"]).name),
                "bytes": row["bytes"],
                "sha256": row["sha256"],
                "role": row["role"],
            }
            for row in evidence_rows
        }
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "created_utc": utc_now(),
            "stage": "A_metadata_only",
            "config": {"path": str(config_path.resolve()), "bytes": config_path.stat().st_size, "sha256": sha256_file(config_path)},
            "study_area": config["study_area"],
            "selection_policy": config["selection"],
            "inputs": inputs,
            "repository_snapshots": snapshots,
            "exposure_closure": {"current_19": len(current_ids), "exposed_12": len(exposed_ids)},
            "candidate_counts": {
                "official_records": len(candidate),
                "detail_evaluated": int(candidate["source_metadata_sha256"].ne("").sum()),
                "selected_unsealed": len(selected),
                "confirmation_role_eligible": int(selected["confirmation_role_eligible"].sum()),
                "excluded": int(candidate["sealed_status"].eq("excluded").sum()),
            },
            "mrar_terminal": {
                "identity_status": str(mrar.iloc[-1]["identity_status"]),
                "source_independence": str(mrar.iloc[-1]["source_independence"]),
            },
            "prohibited_actions": {
                "stage_b_authorized": False,
                "candidate_archive_download_count": 0,
                "candidate_archive_enumeration_count": 0,
                "candidate_depth_read": False,
                "cell_generation_count": 0,
                "reference_or_model_comparison_count": 0,
                "ggm_run_count": 0,
                "pinn_run_count": 0,
            },
            "field_statuses": sorted(FIELD_STATUSES),
            "outputs": outputs,
            "metadata_evidence": evidence_artifacts,
            "verification_required": True,
            "stage_b_requires_separate_user_approval": True,
        }
        manifest_path = temp_dir / "audit_manifest.json"
        atomic_json(manifest, manifest_path)
        os.replace(temp_dir, final_dir)
        print(stable_json({
            "status": "stage_a_published_unverified",
            "run_dir": str(final_dir),
            "candidate_count": len(candidate),
            "selected_unsealed": len(selected),
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
    parser.add_argument("--confirm-stage-a", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confirm_stage_a:
        print("ERROR: Stage A requires --confirm-stage-a; Stage B is not available in this script.", file=sys.stderr)
        return 2
    run_stage_a(args.config.resolve(), args.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
