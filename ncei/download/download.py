"""Disk comparison and parallel resumable file acquisition."""

import concurrent.futures as cf
import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .inventory import target_path, write_json
from .transport import DiskFloorError, TRANSFER_TIMEOUT, header_total

HASH_BLOCK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(HASH_BLOCK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def missing_reason(item: dict, path: Path) -> str | None:
    if not path.exists():
        return "absent"
    size = path.stat().st_size
    if item.get("exact_bytes") is not None:
        if size != item["exact_bytes"]:
            return "size"
    elif item.get("expected") and size < item["expected"] * 0.9 - 1024:
        return "short"
    if item.get("sha256") and sha256_file(path) != item["sha256"].lower():
        return "sha256"
    return None


def diff(items: list[dict], raw: Path, work: Path) -> list[dict]:
    todo = []
    targets = {}
    for item in items:
        path = target_path(raw, item)
        if path in targets and targets[path] != item["url"]:
            raise ValueError(f"different URLs map to the same file: {path}")
        targets[path] = item["url"]
        reason = missing_reason(item, path)
        if reason:
            todo.append({**item, "reason": reason})
    todo.sort(key=lambda n: n.get("expected") or 0)
    write_json(work / "todo.json", todo)
    print(f"diff: {len(todo)} files to fetch", flush=True)
    return todo


def fetch(todo: list[dict], raw: Path, work: Path, transport, *,
          workers=32, attempts=3, tag="tierA-gapfill", min_free_bytes=0) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    logfile = work / f"download-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.jsonl"
    lock = threading.Lock()
    stopped = threading.Event()
    stats = {"files": 0, "failed": 0, "bytes": 0, "skipped": 0}
    start = time.monotonic()

    def one(item):
        if stopped.is_set():
            return
        target = target_path(raw, item)
        digest, size, exact, port = None, 0, None, None
        status = "ok"
        try:
            if missing_reason(item, target) is None:
                size = target.stat().st_size
                digest = item.get("sha256")
                skipped = True
            else:
                skipped = False
                target.parent.mkdir(parents=True, exist_ok=True)
                part = Path(str(target) + ".part")
                header = work / f"hdr-{threading.get_ident()}.txt"
                resume = True
                for attempt in range(attempts):
                    proxy = transport.next_proxy()
                    port = urlsplit(proxy).port if proxy else None
                    code, _, rc = transport.curl(
                        item["url"], part, resume=resume, proxy=proxy,
                        timeout=TRANSFER_TIMEOUT, stall_guard=True, headers=header,
                        min_free_bytes=min_free_bytes)
                    exact = header_total(header)
                    size = part.stat().st_size if part.exists() else 0
                    status = f"failed:curl_{code}rc{rc}"
                    complete = part.exists() and (
                        (code in (200, 206) and rc == 0)
                        or (code == 416 and exact is not None and size == exact))
                    if exact is not None and size != exact:
                        status = f"failed:short:{size}<{exact}" if size < exact else f"failed:size:{size}!={exact}"
                        complete = False
                    if item.get("exact_bytes") is not None and size != item["exact_bytes"]:
                        status = f"failed:size:{size}!={item['exact_bytes']}"
                        complete = False
                    if exact is None and item.get("expected") and size < item["expected"] * 0.9 - 1024:
                        status = f"failed:short:{size}<{item['expected'] * 0.9}"
                        complete = False
                    if complete:
                        digest = sha256_file(part)
                        if item.get("sha256") and digest != item["sha256"].lower():
                            status = "failed:sha256"
                            resume = False
                        else:
                            part.replace(target)
                            status = "ok"
                            break
                    # A server without byte ranges needs one fresh transfer.
                    if rc == 33 or (exact is not None and size > exact):
                        resume = False
                    if attempt + 1 < attempts:
                        time.sleep(min(5, 1 + attempt))
                if status == "failed:sha256":
                    part.unlink(missing_ok=True)
        except DiskFloorError:
            stopped.set()
            status, skipped = "failed:disk_floor", False
        record = {
            "survey_id": item["survey_id"],
            "channel": item.get("channel", "platforms_tree"),
            "source_url": item["url"], "bytes": size if status == "ok" else 0,
            "sha256": digest if status == "ok" else None,
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": status, "worker": tag, "port": port,
        }
        if status != "ok":
            record["expected_exact"] = exact
        with lock:
            output.write(json.dumps(record) + "\n")
            output.flush()
            stats["files"] += 1
            stats["failed"] += status != "ok"
            stats["skipped"] += skipped
            stats["bytes"] += record["bytes"]
            if stats["files"] % 100 == 0:
                print(f"fetch: {stats['files']}/{len(todo)}, failed {stats['failed']}", flush=True)

    with logfile.open("a") as output:
        with cf.ThreadPoolExecutor(max_workers=workers) as executor:
            for _ in executor.map(one, todo):
                pass
    print(f"fetch: {stats}, {time.monotonic() - start:.1f}s, {logfile}", flush=True)
    if stopped.is_set():
        raise DiskFloorError("download stopped at the free-space floor; partial files retained")
    return stats
