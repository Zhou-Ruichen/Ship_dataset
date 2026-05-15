#!/usr/bin/env python3
"""Path-string rewrite tool for the jamstec/ + ncei/ refactor (task 05-11-singlebeam-integration).

Walks the repo, applies an ordered (longest-first) string-replacement
mapping to text files of interest, and reports per-file change counts.

Default mode is dry-run: prints a diff-like summary without touching
files. Pass --apply to actually write changes. Select which PR's mapping
to apply with --pr {A,B}.

Scope:
  - Included extensions: .md .json .yaml .yml .sh
  - Excluded paths: .git/, .trellis/tasks/archive/, scripts/refactor/
    (this tool itself), any path containing /archive/ at top level
  - .py files are NEVER touched — the 3 `source_dataset = "NCEI_multibeam"`
    literals are load-bearing lineage labels (Q5b locked decision).

Each mapping is hardcoded here for auditability — explicit beats clever.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Order matters: longest / most-specific match first so e.g. "JAMSTEC/archive"
# is rewritten before the bare "JAMSTEC/" fallback can swallow it.
MAPPING_PR_A: list[tuple[str, str]] = [
    ("JAMSTEC/bathymetry_data", "jamstec/archive/bathymetry_data"),
    ("JAMSTEC/gravity_data",    "jamstec/gravity_data"),
    ("JAMSTEC/archive",         "jamstec/archive/source_zips"),
    ("NCEI_multibeam",          "jamstec/multibeam"),
    # Bare "JAMSTEC/" fallback last — catches any remaining references
    # that point at the directory root itself (e.g. in prose). Capitalized
    # "JAMSTEC" without trailing slash (organization name in citations) is
    # NOT rewritten — that's a real proper noun.
    ("JAMSTEC/",                "jamstec/"),
]

# PR-B: NCEI_singlebeam/ → ncei/.
# IMPORTANT: NO bare "NCEI_singlebeam" → "ncei" fallback. The external
# zip filename `NCEI_singlebeam_tracks_raw_2018files.zip` lives outside
# the repo at /mnt/data2/00-Data/ and must be preserved verbatim wherever
# it is mentioned. A bare-token rewrite would corrupt it. All in-scope
# references to the directory consistently use the trailing-slash form
# (verified by grep before PR-B execution), so the slash form is
# sufficient and a fallback is unnecessary.
MAPPING_PR_B: list[tuple[str, str]] = [
    ("NCEI_singlebeam/", "ncei/"),
]

MAPPINGS: dict[str, list[tuple[str, str]]] = {
    "A": MAPPING_PR_A,
    "B": MAPPING_PR_B,
}

INCLUDED_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".sh"}

EXCLUDED_PATH_PARTS = (
    ".git",
    "scripts/refactor",
    ".trellis/tasks/archive",
)

# Path-suffix-based exclusions for files that describe the rename itself
# or are frozen historical investigations. Rewriting them would either
# destroy the central argument (the discovery docs that explain why the
# rename is correct) or produce nonsensical "X → X" sentences. Each gets
# a forward-pointer footer added manually instead.
EXCLUDED_FILE_SUFFIXES: tuple[str, ...] = (
    ".trellis/tasks/05-11-singlebeam-integration/prd.md",
    "docs/experiments/2026-05_dataset-source-attribution.md",
    "docs/experiments/2026-05_tmp-data-classification.md",
)


def is_excluded(path: Path, repo_root: Path) -> bool:
    rel = path.relative_to(repo_root).as_posix()
    if any(part in rel for part in EXCLUDED_PATH_PARTS):
        return True
    return any(rel.endswith(suffix) for suffix in EXCLUDED_FILE_SUFFIXES)


def collect_files(repo_root: Path) -> list[Path]:
    out: list[Path] = []
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in INCLUDED_SUFFIXES:
            continue
        if is_excluded(p, repo_root):
            continue
        out.append(p)
    return sorted(out)


def rewrite_text(text: str, mapping: list[tuple[str, str]]) -> tuple[str, dict[str, int]]:
    """Apply mapping in order. Returns (new_text, {pattern: count})."""
    counts: dict[str, int] = {}
    for old, new in mapping:
        if old in text:
            counts[old] = text.count(old)
            text = text.replace(old, new)
    return text, counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=".", help="Repo root (default: cwd)")
    ap.add_argument("--apply", action="store_true",
                    help="Actually write changes (default: dry-run)")
    ap.add_argument("--pr", choices=sorted(MAPPINGS), default="A",
                    help="Which PR's mapping to apply (default: A)")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    files = collect_files(repo_root)
    mapping = MAPPINGS[args.pr]

    changed_files: list[tuple[Path, dict[str, int]]] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new_text, counts = rewrite_text(text, mapping)
        if counts:
            changed_files.append((f, counts))
            if args.apply:
                f.write_text(new_text, encoding="utf-8")

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode} PR-{args.pr}] scanned {len(files)} files, {len(changed_files)} would change")
    print()
    total_per_pattern: dict[str, int] = {}
    for f, counts in changed_files:
        rel = f.relative_to(repo_root).as_posix()
        breakdown = ", ".join(f"{k}={v}" for k, v in counts.items())
        print(f"  {rel}: {breakdown}")
        for k, v in counts.items():
            total_per_pattern[k] = total_per_pattern.get(k, 0) + v
    print()
    print("Totals per pattern:")
    for old, _ in mapping:
        n = total_per_pattern.get(old, 0)
        print(f"  {old!r:42s} -> {n} occurrences")
    return 0


if __name__ == "__main__":
    sys.exit(main())
