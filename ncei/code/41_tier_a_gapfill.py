#!/usr/bin/env python3
"""Tier-A gap fill: authoritative remote inventory + unlimited parallel download.

Why this exists
---------------
The first Tier-A pass (agent 14ffee33, /tmp/tierA_resume_404.py) treated any
non-200 answer to a directory probe as a silent skip: `if code != 200:
continue` left the file list empty and then wrote `tierA_complete:0`.  NCEI
answered with throttling/5xx on 2026-09-04..05, so 88 of the 178 Tier-A
surveys were marked complete without a single file.  On top of that the
platform directory slug was derived from the MBBDB platform *display* name
("NOAA Ship DAVIDSON (S331)"), which never matches the real tree
(`davidson/`), so those probes 404'd.

What it does
------------
1. inventory  -- GET the ships index, every platform directory, and the
   full `MB/` tree of all 178 Tier-A surveys.  Directory listings carry
   name + size, so this is an authoritative expected-file set.
2. diff       -- compare the expected set with the bytes on disk.
3. download   -- fetch every missing/undersized file with N parallel curl
   processes, resume partial files, retry per file.  No rate limiting, no
   inter-request sleep, no global stop flag: a single failed request can no
   longer kill the batch.
4. merge      -- append new records to ncei/manifests/round2_download_log.parquet
   (one backup per run) so downstream completeness checks see them.

Run from the repo root:

    /opt/miniforge3/bin/python ncei/code/41_tier_a_gapfill.py --stage diff
    /opt/miniforge3/bin/python ncei/code/41_tier_a_gapfill.py --stage download --workers 32

Caches (inventory, hashes) live in /tmp/tierA_gapfill/ and are cheap to
rebuild; the repository only receives the data files and the log records.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import re
import shutil
import subprocess
import threading
import time
import urllib.parse
from pathlib import Path

import pandas as pd

R = Path("/mnt/data2/00-Data/ship")
CAT = R / "ncei/derived/mbbdb_value_ranking/order_tier_A.tsv"
LOG = R / "ncei/manifests/round2_download_log.parquet"
RAW = R / "ncei/raw_round2/platforms_tree"
WORK = Path("/tmp/tierA_gapfill")
TAG = "tierA-gapfill"
# 2085 is the unmetered egress.  2081/2082/2084/2087 also answer on this
# host but may be traffic-metered, so they are opt-in only:
#   --proxies http://127.0.0.1:2081,http://127.0.0.1:2085
DEFAULT_PROXIES = ["http://127.0.0.1:2085"]
UA = "Mozilla/5.0 tierA-gapfill/1.0"
SHIPS = "https://data.ngdc.noaa.gov/platforms/ocean/ships/"
COLS = ["survey_id", "channel", "source_url", "bytes", "sha256",
        "downloaded_at_utc", "status", "worker", "port"]

ROW_RE = re.compile(
    r'<tr><td><a href="([^"]+)">([^<]*)</a></td>'
    r'<td align="right">([^<]*)</td><td align="right">([^<]*)</td></tr>')
SIZE_UNITS = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}
_print_lock = threading.Lock()
_proxy_lock = threading.Lock()
_proxy_state = {"list": list(DEFAULT_PROXIES), "next": 0}


def set_proxies(proxies: list[str]) -> None:
    with _proxy_lock:
        _proxy_state["list"] = list(proxies) or list(DEFAULT_PROXIES)
        _proxy_state["next"] = 0


def next_proxy() -> str:
    with _proxy_lock:
        pool = _proxy_state["list"]
        proxy = pool[_proxy_state["next"] % len(pool)]
        _proxy_state["next"] += 1
        return proxy


def log(msg: str) -> None:
    with _print_lock:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def parse_size(text: str) -> int | None:
    text = text.strip().replace(",", "")
    if not text or text == "-":
        return None
    m = re.fullmatch(r"([\d.]+)\s*([KMGT]?)", text)
    if not m:
        return None
    return int(float(m.group(1)) * SIZE_UNITS[m.group(2)])


def curl(url: str, dest: Path | None = None, resume: bool = False,
         timeout: int = 120, proxy: str | None = None,
         stall_guard: bool = False,
         headers: Path | None = None) -> tuple[int, int, int]:
    """GET url through one of the local egress proxies.

    stall_guard aborts a transfer that stays below 1 KB/s for two minutes so a
    dead connection cannot hold a worker for hours.  It is a stall detector, not
    a bandwidth cap.
    """
    args = ["curl", "-L", "--silent", "--show-error", "--fail",
            "--connect-timeout", "10", "--max-time", str(timeout),
            "-A", UA, "--proxy", proxy or next_proxy(),
            "-w", "%{http_code} %{size_download}"]
    if stall_guard:
        args += ["--speed-time", "120", "--speed-limit", "1024"]
    if headers is not None:
        args += ["-D", str(headers)]
    if resume:
        args += ["-C", "-"]
    if dest is not None:
        args += ["-o", str(dest)]
    args.append(url)
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True)
    parts = (p.stdout or "").split()
    code = int(parts[0]) if parts and parts[0].isdigit() else 0
    size = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return code, size, p.returncode


def header_total(path: Path) -> int | None:
    """Exact size of the served object from the last response block.

    Directory listings round sizes to two significant digits ("1.1M"), so a
    size comparison has to come from Content-Length / Content-Range instead.
    """
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None
    for block in reversed(re.split(r"\r?\n\r?\n", text.strip())):
        m = re.search(r"^content-range:\s*bytes\s+\S+/(\d+)", block,
                      re.I | re.M)
        if m:
            return int(m.group(1))
        m = re.search(r"^content-length:\s*(\d+)", block, re.I | re.M)
        if m:
            return int(m.group(1))
    return None


def fetch_text(url: str, cache: Path | None = None, refresh: bool = False,
               timeout: int = 120) -> str | None:
    if cache is not None and cache.exists() and not refresh:
        return cache.read_text(errors="replace")
    tmp = (cache or WORK / "tmp.html")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        code, _, rc = curl(url, tmp, timeout=timeout)
        if code == 200 and tmp.exists():
            if cache is None:
                return tmp.read_text(errors="replace")
            return cache.read_text(errors="replace")
        time.sleep(1 + attempt)
    return None


def list_dir(url: str, cache: Path | None = None, refresh: bool = False):
    """Return (subdirs, files) where files is {name: (url, size_estimate)}."""
    html = fetch_text(url, cache, refresh)
    if html is None:
        return None, None
    rows = ROW_RE.findall(html)
    dirs, files = [], {}
    for href, _text, _mtime, size in rows:
        if href.startswith("?") or href in ("../", "./"):
            continue
        child = urllib.parse.urljoin(url, href)
        if not child.startswith(url):
            continue
        if href.endswith("/"):
            dirs.append(child)
        else:
            files[urllib.parse.unquote(child.split("/")[-1])] = (
                child, parse_size(size))
    return dirs, files


def cache_name(url: str) -> Path:
    rel = url.split("/ships/", 1)[-1].rstrip("/") or "ships_index"
    return WORK / "lists" / (rel.replace("/", "__") + ".html")


# --------------------------------------------------------------------------
# stage: inventory
# --------------------------------------------------------------------------
def stage_inventory(workers: int, refresh: bool) -> dict:
    WORK.mkdir(parents=True, exist_ok=True)
    platforms = json.loads((WORK / "platforms.json").read_text()) \
        if (WORK / "platforms.json").exists() and not refresh else None
    idx = fetch_text(SHIPS, WORK / "ships_index.html", refresh)
    if idx is None:
        raise SystemExit("cannot reach ships index through proxy")
    found = sorted({u for u in (urllib.parse.urljoin(SHIPS, h)
                                for h in re.findall(r'href="([^"?:/][^"]*/)"', idx))
                    if u.startswith(SHIPS)})
    log(f"ships index: {len(found)} platform dirs")
    if platforms is None:
        platforms = {}

    def one(url: str):
        dirs, files = list_dir(url, cache_name(url), refresh)
        return url, dirs

    todo = [u for u in found
            if refresh
            or urllib.parse.unquote(u.split('/ships/', 1)[1].rstrip('/')) not in platforms]
    if todo:
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for url, dirs in ex.map(one, todo):
                key = urllib.parse.unquote(url.split('/ships/', 1)[1].rstrip('/'))
                platforms[key] = [
                    urllib.parse.unquote(d.split('/ships/', 1)[1].rstrip('/')).split('/')[-1]
                    for d in (dirs or [])]
        (WORK / "platforms.json").write_text(json.dumps(platforms, indent=1))
    log(f"platform listings cached: {len(platforms)} platforms, "
        f"{sum(len(v) for v in platforms.values())} survey dirs")

    cat = pd.read_csv(CAT, sep="\t", dtype=str)
    wanted = cat.surveyId.astype(str).tolist()
    sid2plat: dict[str, str] = {}
    for plat, sids in platforms.items():
        for sid in sids:
            sid2plat.setdefault(sid, plat)
    resolved = {sid: sid2plat.get(sid) for sid in wanted}
    missing = [s for s, p in resolved.items() if p is None]
    log(f"Tier-A surveys resolved to a platform dir: "
        f"{len(wanted) - len(missing)}/{len(wanted)}"
        + (f"  unresolved: {missing[:10]}" if missing else ""))
    (WORK / "sid2platform.json").write_text(json.dumps(resolved, indent=1))

    trees = json.loads((WORK / "trees.json").read_text()) \
        if (WORK / "trees.json").exists() and not refresh else {}
    pending = [s for s in wanted if s not in trees]

    def walk(sid: str):
        plat = resolved.get(sid)
        if not plat:
            return sid, None
        # NCEI uses two layouts: <sid>/multibeam/data/version1/MB/... for most
        # surveys, <sid>/multibeam/{level_00,generated}/... for a dozen older
        # or unprocessed ones.  Root the walk at <sid>/multibeam/ and keep
        # whichever relpath convention matches what the first pass wrote.
        root = (f"{SHIPS}{urllib.parse.quote(plat)}/{urllib.parse.quote(sid)}"
                f"/multibeam/")
        files: dict[str, list] = {}

        def rel_of(child: str) -> str | None:
            for marker in ("/MB/", "/multibeam/"):
                if marker in child:
                    return urllib.parse.unquote(child.split(marker, 1)[1])
            return None

        level = [root]
        seen = set()
        ok_root = False
        while level:
            url = level.pop()
            if url in seen:
                continue
            seen.add(url)
            dirs, fs = list_dir(url, cache_name(url), refresh)
            if fs is None:
                return sid, {"root": root, "error": f"listing failed: {url}",
                             "files": files}
            if url == root:
                ok_root = True
            for _name, (child, size) in fs.items():
                rel = rel_of(child)
                if rel:
                    files[rel] = [child, size]
            level.extend(dirs)
        return sid, {"root": root,
                     "error": None if ok_root else "root listing failed",
                     "files": files}

    if pending:
        done = 0
        with cf.ThreadPoolExecutor(max_workers=max(8, workers)) as ex:
            for sid, tree in ex.map(walk, pending):
                trees[sid] = tree
                done += 1
                if done % 20 == 0 or done == len(pending):
                    (WORK / "trees.json").write_text(json.dumps(trees))
                    log(f"tree walk {done}/{len(pending)}")
        (WORK / "trees.json").write_text(json.dumps(trees))
    bad = [s for s, t in trees.items() if t and t.get("error")]
    total_files = sum(len(t["files"]) for t in trees.values() if t)
    log(f"remote tree: {total_files} files across {len(trees)} surveys; "
        f"listing errors: {len(bad)} {bad[:8]}")
    return trees


# --------------------------------------------------------------------------
# stage: diff
# --------------------------------------------------------------------------
def stage_diff(trees: dict) -> list[dict]:
    todo = []
    per_survey = []
    for sid, tree in sorted(trees.items()):
        if not tree:
            continue
        exp = tree["files"]
        need = []
        for rel, (url, size) in exp.items():
            target = RAW / sid / rel
            if not target.exists():
                need.append({"survey_id": sid, "rel": rel, "url": url,
                             "expected": size, "reason": "absent"})
            elif size and target.stat().st_size < size * 0.9 - 1024:
                need.append({"survey_id": sid, "rel": rel, "url": url,
                             "expected": size, "reason": "short"})
        if need:
            per_survey.append((sid, len(exp), len(need),
                               sum(n["expected"] or 0 for n in need)))
        todo.extend(need)
    todo.sort(key=lambda n: (n["expected"] or 0))
    (WORK / "todo.json").write_text(json.dumps(todo))
    total_gb = sum(gb for _, _, _, gb in per_survey) / 1024 ** 3
    log(f"diff: {len(todo)} files to fetch in {len(per_survey)} surveys, "
        f"{total_gb:.1f} GB")
    for sid, exp, nd, gb in per_survey[:20]:
        log(f"   {sid:16s} remote {exp:5d} files, missing {nd:5d}, "
            f"~{gb / 1024 ** 2:.0f} MB")
    return todo


# --------------------------------------------------------------------------
# stage: download
# --------------------------------------------------------------------------
def stage_download(todo: list[dict], workers: int, attempts: int) -> None:
    logger = WORK / f"download-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    logfile = open(logger, "a")
    records: list[dict] = []
    lock = threading.Lock()
    stats = {"files": 0, "bytes": 0, "failed": 0, "skipped": 0}
    start = time.time()

    def progress(stop: threading.Event):
        while not stop.wait(15):
            el = time.time() - start
            with lock:
                f, b, bad, sk = (stats["files"], stats["bytes"],
                                 stats["failed"], stats["skipped"])
            log(f"progress {f}/{len(todo)} files, {b / 1024 ** 3:.1f} GB, "
                f"{b / el / 1024 ** 2:.1f} MB/s avg, failed {bad}, "
                f"already present {sk}")

    def emit(rec: dict):
        with lock:
            records.append(rec)
            logfile.write(json.dumps(rec) + "\n")
            logfile.flush()

    def one(item: dict):
        sid, rel = item["survey_id"], item["rel"]
        url = item["url"]
        expected = item["expected"]
        target = RAW / sid / rel
        # Already complete (previous partial run or overlap with pass 1): keep it.
        if target.exists() and (not expected
                                or target.stat().st_size >= expected * 0.98 - 1024):
            size = target.stat().st_size
            emit({"survey_id": sid, "channel": "platforms_tree",
                  "source_url": url, "bytes": size, "sha256": None,
                  "downloaded_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
                  "status": "ok", "worker": TAG, "port": 2085})
            with lock:
                stats["files"] += 1
                stats["skipped"] += 1
                stats["bytes"] += size
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        part = Path(str(target) + ".part")
        hdr = WORK / f"hdr-{threading.get_ident()}.txt"
        code = 0
        size = 0
        rc = 0
        exact = None
        for attempt in range(attempts):
            code, size, rc = curl(url, part, resume=True, timeout=21600,
                                  stall_guard=True, headers=hdr)
            exact = header_total(hdr) or exact
            need = exact or expected
            got = part.stat().st_size if part.exists() else 0
            # Break only when the object is actually complete: a dropped
            # connection still answers 200/206 with a short body, and that must
            # resume instead of being recorded as done.
            if code in (200, 206, 416) and (not need or got >= need - 1024):
                break
            time.sleep(min(5, 1 + attempt))
        digest = None
        status = f"failed:curl_{code}rc{rc}"
        if code == 416 and part.exists():
            code = 206
        if code in (200, 206) and part.exists():
            total = part.stat().st_size
            # Exact size from the response header; fall back to the rounded
            # listing value with slack when the header is unavailable.
            expected_exact = exact if exact else (
                expected * 0.9 if expected else None)
            if expected_exact and total < expected_exact - 1024:
                status = f"failed:short:{total}<{expected_exact}"
            else:
                if target.exists():
                    target.unlink()
                part.replace(target)
                hasher = hashlib.sha256()
                with open(target, "rb") as fh:
                    for block in iter(lambda: fh.read(1024 * 1024), b""):
                        hasher.update(block)
                digest = hasher.hexdigest()
                size = total
                status = "ok"
        rec = {
            "survey_id": sid, "channel": "platforms_tree", "source_url": url,
            "bytes": size if status == "ok" else 0, "sha256": digest,
            "downloaded_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
            "status": status, "worker": TAG, "port": 2085,
        }
        if status != "ok":
            rec["expected_exact"] = exact
        emit(rec)
        with lock:
            stats["files"] += 1
            if status == "ok":
                stats["bytes"] += size
            else:
                stats["failed"] += 1
        return rec

    stop = threading.Event()
    watcher = threading.Thread(target=progress, args=(stop,), daemon=True)
    watcher.start()
    log(f"download start: {len(todo)} files, {workers} parallel curls")
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for _ in ex.map(one, todo):
            pass
    stop.set()
    logfile.close()
    el = time.time() - start
    log(f"download done: {stats['files']} attempted, {stats['bytes'] / 1024 ** 3:.1f} GB ok, "
        f"{stats['failed']} failed, {el / 60:.1f} min, "
        f"{stats['bytes'] / el / 1024 ** 2:.1f} MB/s")


# --------------------------------------------------------------------------
# stage: merge
# --------------------------------------------------------------------------
def stage_merge() -> None:
    parts = sorted(WORK.glob("download-*.jsonl"))
    if not parts:
        raise SystemExit("nothing to merge")
    new = pd.concat([pd.read_json(p, lines=True) for p in parts],
                    ignore_index=True)
    new = new[new.status.astype(str).str.startswith(("ok", "tierA"))]
    if new.empty:
        log("no successful records to merge")
        return
    data = pd.read_parquet(LOG)
    before = len(data)
    combined = pd.concat([data[COLS], new[COLS]], ignore_index=True)
    combined = combined.drop_duplicates(
        subset=["channel", "source_url"], keep="last")
    backup = LOG.with_suffix(f".parquet.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(LOG, backup)
    combined.to_parquet(LOG, index=False)
    log(f"merged: {before} -> {len(combined)} rows "
        f"(+{len(combined) - before}), backup {backup.name}")


def main() -> None:
    global CAT, WORK, TAG
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=["inventory", "diff", "download", "merge", "all"])
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--proxies", default=",".join(DEFAULT_PROXIES),
                    help="comma separated egress proxies, round-robin per request")
    ap.add_argument("--refresh", action="store_true",
                    help="ignore cached listings and re-fetch")
    ap.add_argument("--catalog", default=str(CAT),
                    help="queue tsv with a surveyId column")
    ap.add_argument("--work", default=str(WORK),
                    help="scratch/cache directory")
    ap.add_argument("--tag", default=TAG,
                    help="worker tag written to the download log")
    args = ap.parse_args()
    CAT = Path(args.catalog)
    WORK = Path(args.work)
    TAG = args.tag
    set_proxies([p.strip() for p in args.proxies.split(",") if p.strip()])

    trees = None
    if args.stage in ("inventory", "diff", "all"):
        trees = stage_inventory(args.workers, args.refresh)
    if args.stage in ("diff", "all") or trees is None:
        if trees is None:
            trees = json.loads((WORK / "trees.json").read_text())
        todo = stage_diff(trees)
        if args.stage == "diff":
            return
    if args.stage in ("download", "all"):
        if not (WORK / "todo.json").exists():
            raise SystemExit("run --stage diff first")
        todo = json.loads((WORK / "todo.json").read_text())
        if todo:
            stage_download(todo, args.workers, args.attempts)
    if args.stage in ("merge", "all"):
        stage_merge()


if __name__ == "__main__":
    main()
