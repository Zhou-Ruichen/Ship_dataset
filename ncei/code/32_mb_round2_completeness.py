#!/usr/bin/env python3
"""Stage 0 — completeness audit of ncei/raw_round2/platforms_tree/ cruises.

Compares the downloader's enumerated file URL set (from
ncei/manifests/round2_download_log.parquet, channel == 'platforms_tree')
against the files actually on disk, plus .part residue. Classifies each
on-disk cruise directory as complete / incomplete and records what is
missing (counts, subdirectory gaps). Read-only with respect to raw data;
writes only the audit manifest under ncei/derived/mb_round2/.

Run from repo root:
    python ncei/code/32_mb_round2_completeness.py
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = REPO_ROOT / "ncei/raw_round2/platforms_tree"
LOG_PATH = REPO_ROOT / "ncei/manifests/round2_download_log.parquet"
OUT_DIR = REPO_ROOT / "ncei/derived/mb_round2"
LISTING_DIR = OUT_DIR / "dir_listings"

PROXY = "http://127.0.0.1:2085"
PLATFORMS_BASE = "https://data.ngdc.noaa.gov/platforms/ocean/ships"

# NCEI platforms-tree URL prefix that maps onto RAW_ROOT.
PLATFORMS_URL_PREFIX = "https://data.ngdc.noaa.gov/platforms/ocean/ships/"

# Apache site-chrome files that appear as plain relative hrefs in listings.
JUNK_PAGE_NAMES = {
    "alerts.css", "aboutngdc.html", "education.html", "favicon.ico",
    "index.html", "ngdc.html", "privacy.html", "mailto:ncei.info@noaa.gov",
}


def url_to_relpath(url: str) -> str | None:
    """Map a download URL to a path relative to RAW_ROOT.

    Directory-listing URLs end with '/' and are not files; return None.
    """
    parsed = urlparse(url)
    rest = unquote(parsed.path)
    marker = "/platforms/ocean/ships/"
    idx = rest.find(marker)
    if idx < 0:
        return None
    rest = rest[idx + len(marker):]
    parts = rest.split("/", 2)  # <ship>/<cruise>/<remainder>
    if len(parts) < 3 or not parts[2] or parts[2].endswith("/"):
        return None
    tail = parts[2]
    # The downloader strips the 'multibeam/data/version1/MB/' prefix when
    # laying files out on disk; mirror that so URL set == disk set.
    mb_idx = tail.find("/MB/")
    if mb_idx >= 0:
        tail = tail[mb_idx + len("/MB/"):]
    else:
        # A dozen cruises use <cruise>/multibeam/{level_00,generated,...}/...
        # with no version1/MB level; the downloader strips that prefix too.
        # Note `tail` has already lost the leading slash, so match without it.
        if tail.startswith("multibeam/"):
            tail = tail[len("multibeam/"):]
    return f"{parts[1]}/{tail}"


def fetch_listing(url: str, cache_name: str) -> str | None:
    """Fetch one directory listing through the proxy, cached on disk.

    Retries once with a longer timeout; returns None on persistent failure
    (the caller treats that subdirectory as unverifiable rather than
    crashing the whole audit).
    """
    cache = LISTING_DIR / cache_name
    if cache.exists() and cache.stat().st_size > 0:
        return cache.read_text(encoding="utf-8", errors="replace")
    last_rc = None
    for timeout in ("60", "120"):
        result = subprocess.run(
            ["curl", "-sS", "--proxy", PROXY, "--connect-timeout", "10", "--max-time", timeout, url],
            capture_output=True, text=True, check=False,
        )
        last_rc = result.returncode
        if result.returncode == 0 and result.stdout:
            LISTING_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(result.stdout, encoding="utf-8")
            return result.stdout
    print(f"WARNING: listing fetch failed rc={last_rc}: {url}", flush=True)
    return None


def live_expected_for_cruise(cruise: str, ship_dirs: dict[str, str]) -> set[str]:
    """Authoritative expected file set from live NCEI directory listings.

    ship_dirs maps cruise -> ship directory name (from the download log).
    Subdirectories are the distinct sonar dirs seen in the log URLs for this
    cruise plus the MB root; each is fetched once and cached.
    """
    expected: set[str] = set()
    subdirs = ship_dirs.get("_subdirs", set())
    # classic layout root, harmless 404 for the new level_00 layout
    for subdir in sorted(subdirs | {"data/version1/MB"}):
        url = f"{PLATFORMS_BASE}/{ship_dirs['ship']}/{cruise}/multibeam/"
        if subdir:
            url += subdir + "/"
        cache_name = f"{cruise}__{subdir.replace('/', '_') or 'ROOT'}.html"
        html = fetch_listing(url, cache_name)
        if html is None:
            continue
        for href in re.findall(r'href="([^"]+)"', html):
            # Plain relative data filenames only: no '/', query or scheme;
            # excludes Apache sort links, mailto:, and the per-file nav
            # pages ("<file>/aboutngdc.html" shape carries an inner '/').
            # Beyond site chrome (JUNK), everything counts — old surveyor-era
            # trees carry uncompressed .mb15/.xyz/.hdr, not just .gz.
            if "/" in href or "?" in href or ":" in href:
                continue
            name = unquote(href)
            if name in JUNK_PAGE_NAMES:
                continue
            # disk layout strips the classic 'data/version1/MB/' component
            sub_disk = subdir.replace("data/version1/MB/", "") if subdir != "data/version1/MB" else ""
            tail = f"{sub_disk}/{name}" if sub_disk else name
            expected.add(f"{cruise}/{tail}")
    return expected


def crawl_cruise_tree(slug: str, cruise: str, *, depth: int = 0, path: str = "", max_depth: int = 5) -> set[str]:
    """Recursively list a cruise directory on the platforms tree.

    Used for cruises absent from the download log (tier-A direct fetches):
    newer NCEI packaging uses level_00/<PRODUCT>/ instead of the classic
    multibeam/data/version1/MB/ path, so the log-derived subdir map does
    not apply. Returns expected relpaths (cruise/<subpath>).
    """
    url = f"{PLATFORMS_BASE}/{slug}/{cruise}/"
    if path:
        url += path
    cache_name = f"CRAWL__{cruise}__{path.replace('/', '_') or 'ROOT'}.html"
    html = fetch_listing(url, cache_name)
    if html is None:
        return set()
    expected: set[str] = set()
    dirs: list[str] = []
    for href in re.findall(r'href="([^"]+)"', html):
        if "?" in href or ":" in href:
            continue
        is_dir = href.endswith("/")
        name = unquote(href.rstrip("/"))
        if not name or "/" in name:  # absolute/root-relative links
            continue
        if is_dir:
            dirs.append(name)
        elif name not in JUNK_PAGE_NAMES:
            expected.add(f"{cruise}/{path}{name}")
    if depth < max_depth:
        for d in dirs:
            expected |= crawl_cruise_tree(slug, cruise, depth=depth + 1, path=f"{path}{d}/", max_depth=max_depth)
    return expected


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-expected", action="store_true",
                        help="Classify against live NCEI directory listings (cached under dir_listings/) "
                             "instead of the download-log URL enumeration, which was truncated "
                             "for some cruises. Fetches metadata only.")
    args = parser.parse_args()

    log = pd.read_parquet(LOG_PATH)
    pt = log[log["channel"] == "platforms_tree"].copy()

    # Enumerated (expected) file set per cruise: unique file URLs.
    pt["rel"] = pt["source_url"].map(url_to_relpath)
    file_rows = pt[pt["rel"].notna()]
    expected: dict[str, set[str]] = {}
    ok_rel: dict[str, set[str]] = {}
    for survey, rel in zip(file_rows["survey_id"], file_rows["rel"]):
        expected.setdefault(str(survey), set()).add(rel)
        # ok rows keyed separately for "downloaded ok" set
    ok_rows = file_rows[file_rows["status"] == "ok"]
    for survey, rel in zip(ok_rows["survey_id"], ok_rows["rel"]):
        ok_rel.setdefault(str(survey), set()).add(rel)

    live_expected: dict[str, set[str]] = {}
    slug_overrides: dict[str, str] = {}
    overrides_path = LISTING_DIR / "ship_slug_overrides.tsv"
    if overrides_path.exists():
        ov = pd.read_csv(overrides_path, sep="\t")
        slug_overrides = dict(zip(ov["cruise"].astype(str), ov["ship_slug"].astype(str)))
    if args.live_expected:
        # Ship directory + sonar subdirs per cruise, derived from log URLs.
        # Ship candidates containing spaces/parens are percent-encoded or
        # display names; prefer clean slugs, then the overrides table.
        meta: dict[str, dict] = {}
        for row in file_rows.itertuples():
            parsed = urlparse(row.source_url)
            rest = unquote(parsed.path)
            marker = "/platforms/ocean/ships/"
            tail = rest[rest.find(marker) + len(marker):]
            parts_ = tail.split("/")
            if len(parts_) < 3:
                continue
            ship, cruise = parts_[0], parts_[1]
            mb_idx = tail.find("/multibeam/")
            sub = tail[mb_idx + len("/multibeam/"):].rsplit("/", 1)[0] if mb_idx >= 0 else ""
            entry = meta.setdefault(cruise, {"ships": set(), "_subdirs": set()})
            entry["ships"].add(ship)
            if sub:
                entry["_subdirs"].add(sub)

    # Disk scan first — its subdirectory set feeds the live listings so that
    # subdirs present on disk but absent from the log are also enumerated.
    disk: dict[str, set[str]] = {}
    parts_by_cruise: dict[str, list[str]] = {}
    bytes_on_disk: dict[str, int] = {}
    for cruise_dir in sorted(p for p in RAW_ROOT.iterdir() if p.is_dir()):
        cruise = cruise_dir.name
        disk[cruise] = set()
        bytes_on_disk[cruise] = 0
        for f in cruise_dir.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(RAW_ROOT).as_posix()
            if rel.endswith(".part"):
                parts_by_cruise.setdefault(cruise, []).append(rel)
            else:
                disk[cruise].add(rel)
                bytes_on_disk[cruise] += f.stat().st_size

    if args.live_expected:
        for cruise in sorted(disk):
            disk_subdirs = {"/".join(rel.split("/")[1:-1]) for rel in disk[cruise] if rel.count("/") >= 2}
            disk_subdirs = {s for s in disk_subdirs if s}
            disk_subdirs = {s.replace("data/version1/MB/", "") for s in disk_subdirs}
            entry = meta.get(cruise)
            if entry:
                ships = [s for s in entry["ships"] if " " not in s and "(" not in s]
                ship = ships[0] if ships else (slug_overrides.get(cruise) or sorted(entry["ships"])[0])
                live_expected[cruise] = live_expected_for_cruise(
                    cruise, {"ship": ship, "_subdirs": entry["_subdirs"] | disk_subdirs}
                )
            elif cruise in slug_overrides:
                live_expected[cruise] = crawl_cruise_tree(slug_overrides[cruise], cruise)

    rows = []
    for cruise in sorted(disk):
        exp = live_expected.get(cruise, expected.get(cruise, set())) if args.live_expected else expected.get(cruise, set())
        got = disk[cruise]
        part_list = parts_by_cruise.get(cruise, [])
        # A .part only marks incompleteness when its target file never landed.
        stale_parts = [p for p in part_list if p[: -len(".part")] in got]
        live_parts = [p for p in part_list if p[: -len(".part")] not in got]
        missing = sorted(exp - got)
        # The downloader stripped path prefixes inconsistently across rounds
        # (e.g. data/version1/xyz/ vs flat); a file counts as present when its
        # basename exists anywhere in the cruise.
        got_by_name = {rel.rsplit("/", 1)[-1] for rel in got}
        missing = [rel for rel in missing if rel.rsplit("/", 1)[-1] not in got_by_name]
        extra = sorted(got - exp)
        # Subdirectory-level gap summary (e.g. em710/ never fetched).
        gap_dirs: dict[str, int] = {}
        for rel in missing:
            tail = rel.split(f"{cruise}/", 1)[1]
            subdir = "/".join(tail.split("/")[:-1]) or "(root)"
            gap_dirs[subdir] = gap_dirs.get(subdir, 0) + 1
        if exp and not missing and not live_parts:
            status = "complete"
        elif not exp:
            status = "expected_unknown_no_part" if not live_parts else "incomplete"
        else:
            status = "incomplete"
        rows.append(
            {
                "cruise": cruise,
                "status": status,
                "n_expected_files": len(exp),
                "n_ok_downloads": len(ok_rel.get(cruise, set())),
                "n_disk_files": len(got),
                "n_missing": len(missing),
                "n_part_files": len(part_list),
                "n_stale_part": len(stale_parts),
                "part_files": ";".join(live_parts),
                "missing_subdir_gaps": ";".join(f"{k}:{v}" for k, v in sorted(gap_dirs.items())) if missing else "",
                "missing_sample": ";".join(missing[:5]),
                "n_extra_on_disk": len(extra),
                "bytes_on_disk": bytes_on_disk[cruise],
            }
        )

    out = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    attrs = pd.DataFrame([{"generated_at_utc": stamp, "log_path": str(LOG_PATH.relative_to(REPO_ROOT)), "raw_root": str(RAW_ROOT.relative_to(REPO_ROOT))}])
    pq_path = OUT_DIR / "completeness_manifest.parquet"
    tmp = pq_path.with_suffix(".parquet.tmp")
    out.to_parquet(tmp, index=False)
    os.replace(tmp, pq_path)
    tsv_path = OUT_DIR / "completeness_manifest.tsv"
    out.to_csv(tsv_path.with_suffix(".tsv.tmp"), sep="\t", index=False)
    os.replace(tsv_path.with_suffix(".tsv.tmp"), tsv_path)

    print(out.to_string(index=False))
    n_complete = int((out["status"] == "complete").sum())
    print(f"\ncomplete: {n_complete}/{len(out)}  (manifest: {pq_path.relative_to(REPO_ROOT)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
