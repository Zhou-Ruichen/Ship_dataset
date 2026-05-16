"""R2 classifier calibration driver.

Scans `ncei/tracklines_xyz/*.xyz` + `ncei/tracklines_nc/*.nc`, runs each
file through the R2 classifier, and emits four artifacts the user can
eyeball to tune thresholds:

  - calibration/r2_borderline.csv     (per-file rows for borderline band)
  - calibration/r2_borderline.png     (scatter: bbox vs density)
  - calibration/r2_hard_mb_files.csv  (per-file rows for hard-mb band)
  - calibration/r2_calibration_summary.txt

The borderline band = files in `100k <= points <= 1M`, where the bbox /
density rule actually fires. Files outside that band are still scanned
(so per-band counts are accurate); borderline rows land in the
borderline CSV, hard-mb rows (points > 1M) land in the hard-mb roster.

Usage:
    python ship/_common/r2_calibration.py             # full scan
    python ship/_common/r2_calibration.py --limit 50  # dev iteration
    python ship/_common/r2_calibration.py --xyz-only  # skip .nc scan
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# Allow running this file directly (no PYTHONPATH setup):
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402  (post-sys.path)

from _common.io_helpers import read_nc_lonlat, read_xyz_lonlat  # noqa: E402
from _common.r2_classifier import (  # noqa: E402
    R2_BBOX_KM2_CUTOFF,
    R2_DENSITY_PPKM2_CUTOFF,
    R2_HARD_MB_POINTS,
    R2_HARD_SB_POINTS,
    R2Result,
    classify,
)

NCEI_DIR = REPO_ROOT / "ncei"
XYZ_DIR = NCEI_DIR / "tracklines_xyz"
NC_DIR = NCEI_DIR / "tracklines_nc"

CALIB_DIR = SCRIPT_DIR / "calibration"
CSV_PATH = CALIB_DIR / "r2_borderline.csv"
PNG_PATH = CALIB_DIR / "r2_borderline.png"
HARD_MB_CSV_PATH = CALIB_DIR / "r2_hard_mb_files.csv"
SUMMARY_PATH = CALIB_DIR / "r2_calibration_summary.txt"


@dataclass
class FileRow:
    """One row of per-file classification output."""

    path: str
    file_type: str  # "nc" | "xyz"
    points: int
    bbox_km2: float | None
    density_ppkm2: float | None
    label: str
    reason: str


def _iter_paths(root: Path, suffix: str, limit: int | None) -> Iterator[Path]:
    paths = sorted(root.glob(f"*{suffix}"))
    if limit is not None:
        paths = paths[:limit]
    return iter(paths)


def _scan_dir(
    root: Path,
    suffix: str,
    file_type: str,
    reader,
    *,
    limit: int | None,
    log_every: int,
) -> list[FileRow]:
    """Scan a directory of trackline files, classify each, return rows."""
    rows: list[FileRow] = []
    paths = sorted(root.glob(f"*{suffix}"))
    if limit is not None:
        paths = paths[:limit]
    total = len(paths)
    if total == 0:
        print(f"  [warn] no {suffix} files under {root}")
        return rows
    t0 = time.time()
    for i, p in enumerate(paths, 1):
        try:
            lon, lat = reader(p)
        except Exception as exc:
            print(f"  [skip] {p.name}: {exc}")
            continue
        if len(lon) == 0:
            continue
        res: R2Result = classify(lon, lat)
        rows.append(FileRow(
            path=str(p.relative_to(REPO_ROOT)),
            file_type=file_type,
            points=res.points,
            bbox_km2=res.bbox_km2,
            density_ppkm2=res.density_ppkm2,
            label=res.label,
            reason=res.reason,
        ))
        if i % log_every == 0 or i == total:
            dt = time.time() - t0
            print(f"  scanned {i}/{total} {suffix} files in {dt:.1f}s")
    return rows


def _band_for(points: int) -> str:
    if points > R2_HARD_MB_POINTS:
        return ">1M"
    if points >= R2_HARD_SB_POINTS:
        return "100k-1M"
    return "<100k"


def _is_borderline(points: int) -> bool:
    return R2_HARD_SB_POINTS <= points <= R2_HARD_MB_POINTS


def _is_hard_mb(points: int) -> bool:
    return points > R2_HARD_MB_POINTS


def _write_csv(rows: list[FileRow], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    borderline = [r for r in rows if _is_borderline(r.points)]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "path", "file_type", "points",
            "bbox_km2", "density_ppkm2",
            "label", "reason",
        ])
        for r in borderline:
            w.writerow([
                r.path, r.file_type, r.points,
                f"{r.bbox_km2:.3f}" if r.bbox_km2 is not None else "",
                f"{r.density_ppkm2:.6f}" if r.density_ppkm2 is not None else "",
                r.label, r.reason,
            ])
    return len(borderline)


def _write_hard_mb_csv(rows: list[FileRow], out_path: Path) -> list[FileRow]:
    """Write the hard-mb file roster (points > R2_HARD_MB_POINTS).

    Same column schema as the borderline CSV. bbox_km2/density_ppkm2 are
    `None` for hard-mb rows by classifier design (no bbox computed); they
    serialize as empty cells.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    hard_mb = sorted((r for r in rows if _is_hard_mb(r.points)), key=lambda r: r.path)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "path", "file_type", "points",
            "bbox_km2", "density_ppkm2",
            "label", "reason",
        ])
        for r in hard_mb:
            w.writerow([
                r.path, r.file_type, r.points,
                f"{r.bbox_km2:.3f}" if r.bbox_km2 is not None else "",
                f"{r.density_ppkm2:.6f}" if r.density_ppkm2 is not None else "",
                r.label, r.reason,
            ])
    return hard_mb


def _write_scatter(rows: list[FileRow], out_path: Path) -> None:
    """Scatter of bbox vs density for the borderline band, log/log axes."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    borderline = [
        r for r in rows
        if _is_borderline(r.points)
        and r.bbox_km2 is not None and r.density_ppkm2 is not None
        and r.bbox_km2 > 0 and r.density_ppkm2 > 0
    ]
    if not borderline:
        print(f"  [warn] no borderline points to plot")
        return

    fig, ax = plt.subplots(figsize=(8, 6))
    markers = {"nc": "o", "xyz": "x"}
    colors = {"mb": "tab:red", "sb": "tab:blue"}
    for ft in ("xyz", "nc"):
        for lab in ("sb", "mb"):
            sub = [r for r in borderline if r.file_type == ft and r.label == lab]
            if not sub:
                continue
            ax.scatter(
                [r.bbox_km2 for r in sub],
                [r.density_ppkm2 for r in sub],
                marker=markers[ft],
                color=colors[lab],
                s=30,
                alpha=0.7,
                label=f"{ft} / {lab} (n={len(sub)})",
            )
    ax.axvline(R2_BBOX_KM2_CUTOFF, color="grey", linestyle="--", linewidth=1,
               label=f"bbox cutoff = {R2_BBOX_KM2_CUTOFF:.0f} km²")
    ax.axhline(R2_DENSITY_PPKM2_CUTOFF, color="grey", linestyle=":", linewidth=1,
               label=f"density cutoff = {R2_DENSITY_PPKM2_CUTOFF:.0f} pts/km²")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("bbox area (km²)")
    ax.set_ylabel("density (pts/km²)")
    ax.set_title("R2 classifier — borderline band (100k–1M points)")
    ax.legend(fontsize=8, loc="best")
    ax.grid(True, which="both", linestyle=":", alpha=0.4)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def _write_summary(rows: list[FileRow], out_path: Path) -> dict[str, int]:
    """Write summary stats; return counters for caller logging."""
    # Per-band, per-label counts.
    bands = ["<100k", "100k-1M", ">1M"]
    counts: dict[tuple[str, str], int] = {(b, lab): 0 for b in bands for lab in ("sb", "mb")}
    per_type_total = {"nc": 0, "xyz": 0}
    for r in rows:
        band = _band_for(r.points)
        counts[(band, r.label)] += 1
        per_type_total[r.file_type] = per_type_total.get(r.file_type, 0) + 1

    borderline = sorted(
        (r for r in rows if _is_borderline(r.points)),
        key=lambda r: -(r.density_ppkm2 or 0.0),
    )
    top_density = borderline[:10]
    top_bbox = sorted(
        (r for r in rows if _is_borderline(r.points) and r.bbox_km2 is not None),
        key=lambda r: -(r.bbox_km2 or 0.0),
    )[:10]
    hard_mb = sorted((r for r in rows if _is_hard_mb(r.points)), key=lambda r: r.path)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# R2 calibration summary\n\n")
        f.write(f"Total files scanned: {len(rows)}\n")
        f.write(f"  nc:  {per_type_total.get('nc', 0)}\n")
        f.write(f"  xyz: {per_type_total.get('xyz', 0)}\n\n")
        f.write("Per-band, per-label counts:\n")
        f.write(f"  {'band':<10}  {'sb':>6}  {'mb':>6}\n")
        for b in bands:
            f.write(f"  {b:<10}  {counts[(b, 'sb')]:>6}  {counts[(b, 'mb')]:>6}\n")
        f.write("\n")
        f.write(f"Thresholds in use (defaults; tunable):\n")
        f.write(f"  R2_HARD_MB_POINTS       = {R2_HARD_MB_POINTS:,}\n")
        f.write(f"  R2_HARD_SB_POINTS       = {R2_HARD_SB_POINTS:,}\n")
        f.write(f"  R2_BBOX_KM2_CUTOFF      = {R2_BBOX_KM2_CUTOFF:.1f} km²\n")
        f.write(f"  R2_DENSITY_PPKM2_CUTOFF = {R2_DENSITY_PPKM2_CUTOFF:.1f} pts/km²\n\n")
        f.write(f"Hard-mb file roster (>1M points, {len(hard_mb)} files):\n")
        for r in hard_mb:
            f.write(f"  {r.path}: pts={r.points:,}\n")
        f.write(f"\nTop-10 highest density (borderline band only):\n")
        for r in top_density:
            d = r.density_ppkm2 or 0.0
            b = r.bbox_km2 or 0.0
            f.write(
                f"  {r.path}: pts={r.points:,} bbox={b:,.1f} km² "
                f"density={d:,.1f} pts/km² label={r.label} reason={r.reason}\n"
            )
        f.write(f"\nTop-10 largest bbox (borderline band only):\n")
        for r in top_bbox:
            d = r.density_ppkm2 or 0.0
            b = r.bbox_km2 or 0.0
            f.write(
                f"  {r.path}: pts={r.points:,} bbox={b:,.1f} km² "
                f"density={d:,.1f} pts/km² label={r.label} reason={r.reason}\n"
            )
    return {f"{b}_{lab}": counts[(b, lab)] for b in bands for lab in ("sb", "mb")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None,
                    help="Process at most N files per directory (dev mode)")
    ap.add_argument("--xyz-only", action="store_true",
                    help="Skip .nc scan (xyz is the slow one)")
    ap.add_argument("--nc-only", action="store_true",
                    help="Skip .xyz scan")
    ap.add_argument("--log-every", type=int, default=200,
                    help="Log progress every N files (default 200)")
    args = ap.parse_args()

    rows: list[FileRow] = []
    if not args.nc_only:
        if not XYZ_DIR.is_dir():
            print(f"[error] {XYZ_DIR} not found", file=sys.stderr)
            return 2
        print(f"Scanning {XYZ_DIR}...")
        rows.extend(_scan_dir(
            XYZ_DIR, ".xyz", "xyz", read_xyz_lonlat,
            limit=args.limit, log_every=args.log_every,
        ))
    if not args.xyz_only:
        if not NC_DIR.is_dir():
            print(f"[error] {NC_DIR} not found", file=sys.stderr)
            return 2
        print(f"Scanning {NC_DIR}...")
        rows.extend(_scan_dir(
            NC_DIR, ".nc", "nc", read_nc_lonlat,
            limit=args.limit, log_every=args.log_every,
        ))

    if not rows:
        print("[error] no rows produced", file=sys.stderr)
        return 1

    n_csv = _write_csv(rows, CSV_PATH)
    _write_scatter(rows, PNG_PATH)
    hard_mb_rows = _write_hard_mb_csv(rows, HARD_MB_CSV_PATH)
    summary = _write_summary(rows, SUMMARY_PATH)
    print()
    print(f"Wrote {CSV_PATH} ({n_csv} borderline rows)")
    print(f"Wrote {PNG_PATH}")
    print(f"Wrote {HARD_MB_CSV_PATH} ({len(hard_mb_rows)} hard-mb rows)")
    print(f"Wrote {SUMMARY_PATH}")
    print(f"Per-band counts: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
