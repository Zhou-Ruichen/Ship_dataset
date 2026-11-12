"""Command line dispatcher for the NCEI trackline processing chain."""

from __future__ import annotations

import argparse
import importlib
import sys


COMMANDS = {
    "manifest": ("manifest", "Build the trackline source manifest."),
    "standardize-nc": ("standardize_singlebeam", "Standardize NCEI NetCDF singlebeam tracks."),
    "standardize-xyz": ("standardize_xyz", "Standardize NCEI XYZ tracks."),
    "clean-mrar": ("clean_mrar", "Clean the regional MRAR point cloud."),
    "point-qc": ("entry_manifest", "Build the point-quality layer."),
    "supplementary-qc": ("supplementary_qc", "Run supplementary point-quality checks."),
    "file-cells": ("file_cells", "Aggregate checked points into one-minute file cells."),
    "merge-cells": ("merge_cells", "Merge branch file-cell products."),
    "quality-policy": ("quality_policy", "Compute overlap evidence and apply the approved cell quality policy."),
    "validation-cells": ("validation_cells", "Build validation-cell products."),
    "regional-quality": ("regional_quality", "Build six-region track biases, crossovers and dispositions."),
    "global-bias": ("global_bias", "Estimate global singlebeam track bias."),
    "global-crossover": ("global_crossover", "Audit global singlebeam crossovers."),
    "global-disposition": ("global_disposition", "Build the global singlebeam disposition."),
    "global-grid": ("global_grid", "Build the merged global one-minute grid."),
    "mgd77t-points": ("mgd77t_points", "Build source-preserving MGD77T point and cell tables."),
    "mgd77t-crossovers": ("mgd77t_crossover", "Compute source-indexed MGD77T crossovers."),
    "mgd77t-netcdf": ("mgd77t_netcdf", "Convert or verify complete MGD77T surveys."),
    "source-corrections": ("source_corrections", "Structure source physical-correction states with evidence."),
}

ALIASES = {
    "01": "manifest", "02": "standardize-nc", "03": "standardize-xyz",
    "04": "clean-mrar", "05": "point-qc", "06": "supplementary-qc",
    "07": "file-cells", "08": "merge-cells", "13": "validation-cells",
    "25": "global-bias", "26": "global-crossover", "30": "global-disposition",
    "31": "global-grid",
}


def parser() -> argparse.ArgumentParser:
    lines = ["Commands (in processing order):"]
    for command, (_, description) in COMMANDS.items():
        aliases = ", ".join(key for key, value in ALIASES.items() if value == command)
        label = f"{command} ({aliases})" if aliases else command
        lines.append(f"  {label:<31} {description}")
    ap = argparse.ArgumentParser(
        prog="python -m ncei.trackline",
        description="Run the NCEI trackline processing chain.",
        epilog="\n".join(lines),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("command", choices=(*COMMANDS, *ALIASES), metavar="COMMAND")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    ap = parser()
    if not args:
        ap.print_help()
        return 0
    token = ap.parse_args(args[:1]).command
    command = ALIASES.get(token, token)
    module = importlib.import_module(f"{__package__}.{COMMANDS[command][0]}")
    return int(module.main(args[1:]) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
