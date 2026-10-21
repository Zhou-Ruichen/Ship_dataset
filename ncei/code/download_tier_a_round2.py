#!/usr/bin/env python3
"""Tier-A round-2 NCEI platforms_tree downloader (resumable).

Reimplementation of the round-2 download worker originally launched by Codex
agent 14ffee33 (killed 2026-09-06 06:16 CST by a Paseo daemon cgroup kill).
Authored fresh on 2026-09-06 per user request; semantics follow the original:

- Queue:   ncei/derived/mbbdb_value_ranking/order_tier_A.tsv (surveyId, platform)
- Done:    ncei/manifests/round2_download_log.parquet, channel == platforms_tree,
           status starting with tierA_complete: / tierA_skip:
- Skipped: files whose source_url already has a status=="ok" record
- Output:  ncei/raw_round2/platforms_tree/{surveyId}/<path under .../MB/>
- Log:     JSONL rows (same schema as round2_download_log.parquet) appended to
           /tmp/tierA_retry_resume/logs2/w{1,2}.jsonl — merge into the parquet
           (dedupe on channel+source_url) before any later restart.
- Transport: curl -x http://127.0.0.1:2085, >= 2 s between requests per worker,
           per-request --max-time 3600, abort when < 1 B/s for 30 s.

Run from repo root:  python ncei/code/download_tier_a_round2.py
"""

import csv
import hashlib
import json
import multiprocessing as mp
import re
import subprocess
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

R = Path("/mnt/data2/00-Data/ship")
TSV = R / "ncei/derived/mbbdb_value_ranking/order_tier_A.tsv"
PARQUET = R / "ncei/manifests/round2_download_log.parquet"
OUT = R / "ncei/raw_round2/platforms_tree"
LOGDIR = R / "ncei/output/logs/tierA_resume"  # 2026-10-20: durable log location (was /tmp)
PROXY = "http://127.0.0.1:2085"
UA = "Mozilla/5.0 round2-tierA-resume/2.0"
GAP = 2.0          # seconds between requests, per worker
N_WORKERS = 2
ATTEMPTS = 3

BASE = ("https://data.ngdc.noaa.gov/platforms/ocean/ships/"
        "{plat}/{sid}/multibeam/data/version1/MB/")


def plat_dir(platform: str) -> str:
    s = re.sub(r"\s+", "_", platform.strip().lower())
    return urllib.parse.quote(s, safe="._()-")


def curl(url: str, out: Path | None = None) -> tuple[int, int]:
    """GET url via proxy. Returns (http_code, curl_exit)."""
    a = ["curl", "-L", "--fail", "--silent", "--show-error",
         "--connect-timeout", "10", "--max-time", "3600",
         "--speed-time", "30", "--speed-limit", "1",
         "-A", UA, "--proxy", PROXY]
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        a += ["-C", "-", "-o", str(out)]
    a += ["-w", "%{http_code}", url]
    try:
        r = subprocess.run(a, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=3630)
    except subprocess.TimeoutExpired:
        return 0, 0
    code = 0
    if r.stdout:
        digits = "".join(ch for ch in r.stdout[-3:] if ch.isdigit())
        code = int(digits) if len(digits) == 3 else 0
    return code, r.returncode


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_listing(html: str) -> list[str]:
    """Return hrefs from an Apache autoindex page (dirs keep trailing '/')."""
    out = []
    for m in re.finditer(r'href="([^"]+)"', html):
        h = m.group(1)
        if h.startswith(("/", "http", "?", "#")) or h in ("", "./"):
            continue
        if h.startswith("../") or "Parent" in h:
            continue
        out.append(h)
    return out


class Logger:
    def __init__(self, path: Path):
        self.f = path.open("a")

    def emit(self, sid, url, status, n=0, h=None):
        rec = {"survey_id": sid, "channel": "platforms_tree", "source_url": url,
               "bytes": n, "sha256": h,
               "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
               "status": status, "worker": getattr(self, "tag", None), "port": 2085}
        self.f.write(json.dumps(rec) + "\n")
        self.f.flush()


def worker(w: int, q: mp.Queue, ok_urls: set):
    tag = f"tierA-2085-{w}"
    LOGDIR.mkdir(parents=True, exist_ok=True)
    lg = Logger(LOGDIR / f"w{w}.jsonl")
    lg.tag = tag
    page_tmp = LOGDIR / f"page_{w}.html"
    last = 0.0

    def throttle():
        nonlocal last
        wait = GAP - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
        last = time.monotonic()

    while True:
        try:
            sid, plat = q.get_nowait()
        except mp.queues.Empty:
            break
        base = BASE.format(plat=plat_dir(plat), sid=urllib.parse.quote(sid, safe="-_."))
        n_ok = 0
        todo, seen, files = [base], set(), []
        aborted = False
        while todo:
            u = todo.pop(0)
            if u in seen:
                continue
            seen.add(u)
            code = 0
            for _ in range(ATTEMPTS):
                throttle()
                code, _rc = curl(u, page_tmp)
                if code == 200:
                    break
                if code == 404:
                    # NOAA/proxy occasionally bursts soft-404s when throttled
                    # (seen 2026-09-06: every survey 404ed for ~70 s, then
                    # recovered). Only trust a 404 that repeats after backoff.
                    time.sleep(30)
                    throttle()
                    code, _rc = curl(u, page_tmp)
                    if code == 200:
                        break
                time.sleep(5)
            if code == 404:
                lg.emit(sid, base, "tierA_skip:404")
                print(f"[w{w}] {sid}: skip 404", flush=True)
                aborted = True
                break
            if code != 200:
                lg.emit(sid, u, "failed:listing")
                continue
            for h in parse_listing(page_tmp.read_text(errors="replace")):
                child = urllib.parse.urljoin(u, h)
                if child.endswith("/"):
                    todo.append(child)
                else:
                    files.append(child)
        if aborted:
            continue
        for i, fu in enumerate(files):
            if fu in ok_urls:
                continue
            rel = urllib.parse.unquote(fu[len(base):])
            dest = OUT / sid / rel
            st, _rc = "failed:curl_0", 0
            for attempt in range(ATTEMPTS):
                throttle()
                code, rc = curl(fu, dest)
                if rc == 0 and code == 200 and dest.exists():
                    st, _rc = "ok", dest.stat().st_size
                    break
                if rc == 22:  # HTTP-level error (404/403...): retry won't help
                    break
                time.sleep(GAP)
            if st == "ok":
                n_ok += 1
                ok_urls.add(fu)
                lg.emit(sid, fu, "ok", n=dest.stat().st_size, h=sha256_of(dest))
            else:
                lg.emit(sid, fu, "failed:curl_0")
            if (i + 1) % 50 == 0:
                print(f"[w{w}] {sid}: {i + 1}/{len(files)} files "
                      f"({n_ok} ok this session)", flush=True)
        lg.emit(sid, base, f"tierA_complete:{n_ok}")
        print(f"[w{w}] {sid}: DONE, {n_ok} files downloaded "
              f"({len(files)} total in tree)", flush=True)


def main():
    t = pd.read_csv(TSV, sep="\t", dtype=str)
    D = pd.read_parquet(PARQUET)
    d = D[D.channel == "platforms_tree"]
    ok_urls = set(d[d.status == "ok"].source_url.dropna().astype(str))
    done = set(d[d.status.astype(str)
                  .str.startswith(("tierA_complete:", "tierA_skip:"))]
                .survey_id.astype(str))

    q = mp.Queue()
    nq = 0
    for _, r in t.iterrows():
        sid = str(r["surveyId"])
        if sid not in done:
            q.put((sid, str(r["platform"])))
            nq += 1
    print(f"resume: {len(done)} surveys done, {nq} queued, "
          f"{len(ok_urls)} file urls already ok", flush=True)

    ps = [mp.Process(target=worker, args=(w, q, ok_urls)) for w in range(1, N_WORKERS + 1)]
    for p in ps:
        p.start()
    for p in ps:
        p.join()
    print("all workers finished", flush=True)


if __name__ == "__main__":
    main()
