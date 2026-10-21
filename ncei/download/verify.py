"""Read-only completeness and gzip checks, written in downstream schemas."""

import concurrent.futures as cf
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .download import missing_reason
from .inventory import listing_failures, platform_parts, target_path

GZIP_COLUMNS = ["relpath", "bytes", "gzip_t_rc", "gzip_t_msg", "checked_at_utc"]


def check_gzip(path: Path, raw: Path, executable="gzip") -> dict:
    result = subprocess.run([executable, "-t", str(path)], capture_output=True, text=True)
    return {
        "relpath": path.relative_to(raw).as_posix(), "bytes": path.stat().st_size,
        "gzip_t_rc": result.returncode,
        "gzip_t_msg": (result.stderr.strip().splitlines() or [""])[-1][:200],
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def completeness(trees: dict, raw: Path, log_path: Path | None = None) -> pd.DataFrame:
    """Audit listed cruises, including absent cruises and failed inventories."""
    ok = {}
    if log_path is not None and log_path.exists():
        data = pd.read_parquet(log_path)
        for row in data[(data.channel == "platforms_tree") & (data.status == "ok")].itertuples():
            try:
                _, survey, rel = platform_parts(row.source_url)
            except ValueError:
                continue
            ok.setdefault(survey, set()).add(rel)
    rows = []
    bad = listing_failures(trees)
    for survey, tree in sorted(trees.items()):
        files = tree.get("files", {}) if tree else {}
        roots = {raw / "platforms_tree" / survey}
        for url, _ in files.values():
            ship, _, _ = platform_parts(url)
            roots.add(raw / "platforms_tree" / ship / survey)
        # Failed inventories can still have an existing ship-level directory.
        roots.update((raw / "platforms_tree").glob(f"*/{survey}"))
        got, parts, size = set(), set(), 0
        for root in sorted(roots):
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()
                if rel.endswith(".part"):
                    parts.add(rel)
                else:
                    got.add(rel)
                    size += path.stat().st_size
        missing = []
        for rel, (url, expected) in files.items():
            item = {"survey_id": survey, "url": url, "rel": rel, "expected": expected}
            if missing_reason(item, target_path(raw, item)):
                missing.append(rel)
        missing.sort()
        live_parts = sorted(p for p in parts if p[:-5] not in got)
        gaps = {}
        for rel in missing:
            parent = str(Path(rel).parent)
            parent = "(root)" if parent == "." else parent
            gaps[parent] = gaps.get(parent, 0) + 1
        status = "listing_failed" if survey in bad else (
            "complete" if not missing and not live_parts else "incomplete")
        rows.append({
            "cruise": survey, "status": status, "n_expected_files": len(files),
            "n_ok_downloads": len(ok.get(survey, set())), "n_disk_files": len(got),
            "n_missing": len(missing), "n_part_files": len(parts),
            "n_stale_part": len(parts) - len(live_parts),
            "part_files": ";".join(f"{survey}/{p}" for p in live_parts),
            "missing_subdir_gaps": ";".join(f"{k}:{v}" for k, v in sorted(gaps.items())),
            "missing_sample": ";".join(f"{survey}/{p}" for p in missing[:5]),
            "n_extra_on_disk": len(got - files.keys()), "bytes_on_disk": size,
            "listing_error": bad.get(survey, ""),
        })
    return pd.DataFrame(rows)


def write_table(data: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".parquet.tmp")
    data.to_parquet(temp, index=False)
    temp.replace(path)
    data.to_csv(path.with_suffix(".tsv"), sep="\t", index=False)


def verify(trees: dict, raw: Path, out: Path, *, log_path=None,
           workers=12, gzip_executable="gzip", extraction_dir=None) -> bool:
    audit = completeness(trees, raw, log_path)
    write_table(audit, out / "completeness_manifest.parquet")
    base = raw / "platforms_tree"
    paths = set()
    for survey, tree in trees.items():
        roots = {base / survey, *base.glob(f"*/{survey}")}
        for root in roots:
            if root.is_dir():
                paths.update(root.rglob("*.gz"))
    consumed = set()
    if extraction_dir is not None:
        for manifest in extraction_dir.glob("*/extraction_manifest.parquet"):
            data = pd.read_parquet(manifest, columns=["relpath", "status"])
            consumed.update(data.loc[data.status.isin([
                "ok", "skipped_exists", "skipped_format_unknown", "skipped_format_unsupported",
            ]), "relpath"])

    def one(path):
        rel = path.relative_to(base).as_posix()
        if rel in consumed:
            return {"relpath": rel, "bytes": -1, "gzip_t_rc": 0,
                    "gzip_t_msg": "previously_verified_by_extraction", "checked_at_utc": ""}
        return check_gzip(path, base, gzip_executable)

    with cf.ThreadPoolExecutor(max_workers=workers) as executor:
        rows = list(executor.map(one, sorted(paths)))
    gzip = pd.DataFrame(rows, columns=GZIP_COLUMNS)
    write_table(gzip, out / "gzip_preflight.parquet")
    bad = int((gzip.gzip_t_rc != 0).sum())
    complete = int((audit.status == "complete").sum()) if not audit.empty else 0
    print(f"verify: complete {complete}/{len(audit)}, corrupt gzip {bad}/{len(gzip)}", flush=True)
    return not audit.empty and complete == len(audit) and bad == 0
