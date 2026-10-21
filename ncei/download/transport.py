"""Curl transfers, proxy rotation, and successful directory-page caching."""

import itertools
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import DEFAULT_PROXIES

USER_AGENT = "Mozilla/5.0 ncei-download/1.0"
LISTING_ATTEMPTS = 3
TRANSFER_TIMEOUT = 21600
DISK_CHECK_SECONDS = 5


class DiskFloorError(RuntimeError):
    """The destination filesystem has reached its free-space floor."""


def check_space(path: Path, floor: int) -> None:
    while not path.exists():
        path = path.parent
    free = shutil.disk_usage(path).free
    if free < floor:
        raise DiskFloorError(f"free space {free / 1024**3:.1f} GiB < {floor / 1024**3:g} GiB")


def header_total(path: Path) -> int | None:
    """Read the exact object size from the final HTTP response, not redirects."""
    if not path.exists():
        return None
    blocks = re.split(r"\r?\n\r?\n", path.read_text(errors="replace").strip())
    blocks = [b for b in blocks if b.startswith("HTTP/")]
    if not blocks:
        return None
    block = blocks[-1]
    match = re.search(r"^content-range:\s*bytes\s+\S+/(\d+)", block, re.I | re.M)
    if not match:
        match = re.search(r"^content-length:\s*(\d+)", block, re.I | re.M)
        if re.match(r"HTTP/\S+\s+416\b", block):
            return None
    return int(match.group(1)) if match else None


class Transport:
    """Share a round-robin proxy pool across curl workers."""

    def __init__(self, proxies=None):
        self.proxies = itertools.cycle(DEFAULT_PROXIES if proxies is None else proxies)
        self.lock = threading.Lock()

    def next_proxy(self) -> str:
        with self.lock:
            return next(self.proxies)

    def curl(self, url: str, dest: Path, *, resume=False, timeout=120,
             proxy=None, headers=None, stall_guard=False, min_free_bytes=0):
        args = ["curl", "-L", "--silent", "--show-error", "--fail",
                "--connect-timeout", "10", "--max-time", str(timeout),
                "-A", USER_AGENT, "--proxy",
                self.next_proxy() if proxy is None else proxy,
                "-w", "%{http_code} %{size_download}", "-o", str(dest)]
        if stall_guard:
            args += ["--speed-time", "120", "--speed-limit", "1024"]
        if headers is not None:
            args += ["-D", str(headers)]
        if resume:
            args += ["-C", "-"]
        args.append(url)
        if min_free_bytes:
            check_space(dest.parent, min_free_bytes)
        with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True) as process:
            try:
                while True:
                    try:
                        stdout, _ = process.communicate(timeout=DISK_CHECK_SECONDS)
                        break
                    except subprocess.TimeoutExpired:
                        if min_free_bytes:
                            check_space(dest.parent, min_free_bytes)
            except BaseException:
                process.terminate()
                process.communicate()
                raise
        parts = stdout.split()
        code = int(parts[0]) if parts and parts[0].isdigit() else 0
        size = int(float(parts[1])) if len(parts) > 1 else 0
        return code, size, process.returncode

    def fetch_text(self, url: str, cache: Path, refresh=False) -> str | None:
        if cache.exists() and cache.stat().st_size and not refresh:
            return cache.read_text(errors="replace")
        cache.parent.mkdir(parents=True, exist_ok=True)
        part = cache.with_suffix(cache.suffix + ".part")
        for attempt in range(LISTING_ATTEMPTS):
            code, _, rc = self.curl(url, part)
            if code == 200 and rc == 0 and part.exists():
                part.replace(cache)
                return cache.read_text(errors="replace")
            if attempt + 1 < LISTING_ATTEMPTS:
                time.sleep(1 + attempt)
        return None
