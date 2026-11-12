"""Find downloaded swath files and retain their historical source keys."""

from __future__ import annotations

import gzip
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_ROOTS = (
    ROOT / "ncei/raw_round2/platforms_tree",
    Path("/mnt/data1/pub/ship/ncei/raw_round2/platforms_tree"),
)
LEDGER = ROOT / "ncei/manifests/round2_download_log.parquet"
HISTORICAL = ROOT / "ncei/derived/mb_round2"
OUTPUT = ROOT / "ncei/derived/swath_rebuild_20261112"
SUPPORTED_FORMATS = {11, 15, 21, 32, 41, 57, 58, 84, 121}
MB_SUFFIX = re.compile(r"\.mb(\d+)$")
RAW_SUFFIXES = {".all": 58, ".rc00": 15}


def file_key(relpath: Path) -> str:
    return hashlib.sha256(relpath.as_posix().encode()).hexdigest()[:16]


def format_of(path: Path) -> tuple[int | None, str]:
    """Resolve filename formats before probing suffixless gzip files."""
    stem = path.name.lower().removesuffix(".gz")
    if match := MB_SUFFIX.search(stem):
        return int(match[1]), f"suffix {match[0]}"
    if Path(stem).suffix in RAW_SUFFIXES:
        suffix = Path(stem).suffix
        return RAW_SUFFIXES[suffix], f"suffix {suffix}"
    if path.suffix.lower() == ".gz":
        try:
            with gzip.open(path, "rb") as stream:
                head = stream.read(16)
        except (OSError, EOFError) as error:
            return None, f"unreadable gzip header: {error}"
        if head.startswith(b"ERGNMESS"):
            return 21, "content signature ERGNMESS"
        return None, f"unknown format: head={head!r}"
    return None, "unknown uncompressed format"


def is_swath_file(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith(".gz"):
        return not name.endswith((".tar.gz", ".txt.gz", ".csv.gz", ".xml.gz", ".pdf.gz"))
    return bool(MB_SUFFIX.search(name)) or path.suffix.lower() in RAW_SUFFIXES


@dataclass(frozen=True)
class Source:
    cruise: str
    path: Path
    directory: Path
    relpath: Path
    file_ordinal: int
    filekey: str
    mb_format: int | None
    format_note: str
    bytes: int

    @property
    def supported(self) -> bool:
        return self.mb_format in SUPPORTED_FORMATS


def downloaded_cruises(ledger: Path = LEDGER) -> set[str]:
    ledger = pd.read_parquet(ledger, columns=["survey_id"], filters=[
        ("channel", "=", "platforms_tree"), ("status", "=", "ok"),
    ])
    return set(ledger.survey_id)


def cruise_directories(roots: list[Path], cruises: set[str], downloaded: set[str]) -> dict[str, list[tuple[Path, Path]]]:
    """Index the flat and ship-prefixed platform trees in root priority order."""
    result = {cruise: [] for cruise in cruises}
    for root in roots:
        for directory in sorted(root.iterdir()):
            if not directory.is_dir():
                continue
            if directory.name in cruises:
                result[directory.name].append((root, directory))
            elif directory.name not in downloaded:
                for child in sorted(directory.iterdir()):
                    if child.name in cruises and child.is_dir():
                        result[child.name].append((root, child))
    return result


def discover(cruise: str, directories: list[tuple[Path, Path]],
             historical_root: Path = HISTORICAL) -> list[Source]:
    """Discover source files, preferring historical keys and compressed copies."""
    if not directories:
        return []
    paths: dict[Path, tuple[Path, Path, Path]] = {}
    for root, directory in directories:
        for path in sorted(directory.rglob("*")):
            if is_swath_file(path) and path.is_file():
                tail = path.relative_to(directory)
                normalized = tail.with_suffix("") if tail.suffix.lower() == ".gz" else tail
                current = paths.get(normalized)
                if current is None or (current[1] == directory and tail.suffix.lower() == ".gz"):
                    paths[normalized] = path, directory, root

    sources = []
    next_ordinal = 0
    historical = historical_root / cruise / "extraction_manifest.parquet"
    if historical.is_file():
        columns = ["relpath", "file_ordinal", "filekey", "mb_format", "format_note"]
        for row in pd.read_parquet(historical, columns=columns).sort_values("file_ordinal").itertuples():
            rel = Path(row.relpath)
            tail = Path(*rel.parts[rel.parts.index(cruise) + 1:])
            key = tail.with_suffix("") if tail.suffix.lower() == ".gz" else tail
            next_ordinal = max(next_ordinal, row.file_ordinal + 1)
            if key not in paths:
                # Some legacy sources were unpacked and lost the MBIO suffix.
                if MB_SUFFIX.search(key.name):
                    key = key.with_suffix("")
                for root, directory in directories:
                    if (directory / key).is_file():
                        paths.setdefault(key, (directory / key, directory, root))
                        break
            fmt = int(row.mb_format) if pd.notna(row.mb_format) else None
            if key in paths:
                path, directory, _ = paths.pop(key)
                if fmt is None:
                    fmt, note = format_of(path)
                else:
                    note = row.format_note
                size = path.stat().st_size
            else:
                # Retain missing historical sources so the cruise cannot complete partially.
                _, directory = directories[0]
                path, size, note = directory / tail, 0, row.format_note
            sources.append(Source(cruise, path, directory, rel, row.file_ordinal,
                                  row.filekey, fmt, note, size))
    for ordinal, (path, directory, root) in enumerate(sorted(paths.values()), next_ordinal):
        rel = path.relative_to(root)
        fmt, note = format_of(path)
        sources.append(Source(cruise, path, directory, rel, ordinal, file_key(rel),
                              fmt, note, path.stat().st_size))
    return sources
