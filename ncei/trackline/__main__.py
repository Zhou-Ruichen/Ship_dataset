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
    "point-qc": ("point_qc", "Build the point-quality layer."),
    "supplementary-qc": ("supplementary_qc", "Run supplementary point-quality checks."),
    "file-cells": ("file_cells", "Aggregate checked points into one-minute file cells."),
    "merge-cells": ("merge_cells", "Merge branch file-cell products."),
    "source-overlap": ("source_overlap", "Audit overlap within each source."),
    "branch-overlap": ("branch_overlap", "Audit overlap between source branches."),
    "policy-audit": ("policy_audit", "Calibrate the quality policy."),
    "apply-policy": ("apply_policy", "Apply the quality policy to cells."),
    "validation-cells": ("validation_cells", "Build validation-cell products."),
    "track-bias": ("track_bias", "Estimate regional singlebeam track bias."),
    "crossover": ("crossover", "Audit true singlebeam crossovers."),
    "global-bias": ("global_bias", "Estimate global singlebeam track bias."),
    "global-crossover": ("global_crossover", "Audit global singlebeam crossovers."),
    "disposition": ("disposition", "Build regional track-quality dispositions."),
    "global-disposition": ("global_disposition", "Build the global singlebeam disposition."),
    "global-grid": ("global_grid", "Build the merged global one-minute grid."),
    "mgd77t-xyz": ("mgd77t_xyz", "Convert static MGD77T files to XYZ."),
    "mgd77t-fragments": ("mgd77t_fragments", "Build static MGD77T L1-L3 fragments."),
}

ALIASES = {
    "01": "manifest", "02": "standardize-nc", "03": "standardize-xyz",
    "04": "clean-mrar", "05": "point-qc", "06": "supplementary-qc",
    "07": "file-cells", "08": "merge-cells", "09": "source-overlap",
    "10": "branch-overlap", "11": "policy-audit", "12": "apply-policy",
    "13": "validation-cells", "23": "track-bias", "24": "crossover",
    "25": "global-bias", "26": "global-crossover", "28": "disposition",
    "30": "global-disposition", "31": "global-grid", "39": "mgd77t-xyz",
    "40": "mgd77t-fragments",
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
