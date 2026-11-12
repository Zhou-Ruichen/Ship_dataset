"""Command-line entry for the JAMSTEC multibeam pipeline."""

from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path

ROOT_ENV = "JAMSTEC_MULTIBEAM_ROOT"

COMMANDS = {
    "extract": ("extract", "Extract and inventory the source archives."),
    "manifest": ("manifest", "Audit source files and build source manifests."),
    "curate": ("curate", "Select and annotate sources for point standardization."),
    "standardize": ("standardize", "Standardize source DAT files into point tables."),
    "point-qc": ("point_qc", "Append point-level quality flags."),
    "file-cells": ("file_cells", "Aggregate each source file into one-minute cells."),
    "merge-cells": ("merge_cells", "Merge file cells with file-balanced statistics."),
    "quality": ("quality", "Run overlap, source-quality, QC-filter and comparison stages."),
    "validation-cells": ("validation_cells", "Build primary and sensitivity validation cells."),
}


def top_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m jamstec.multibeam")
    parser.add_argument(
        "--project-root", type=Path,
        help="Isolated project root with the same relative layout (default: package directory).",
    )
    parser.add_argument("command", choices=COMMANDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        top_parser().print_help()
        print("\nCommands:")
        for command, (_, description) in COMMANDS.items():
            print(f"  {command:<18} {description}")
        return 0

    # Parse only global options. Command options, including --help, remain
    # untouched and are parsed by the lazily imported command module.
    global_parser = argparse.ArgumentParser(add_help=False)
    global_parser.add_argument("--project-root", type=Path)
    global_parser.add_argument("command", choices=COMMANDS)
    parsed, remaining = global_parser.parse_known_args(args)
    if parsed.project_root is not None:
        os.environ[ROOT_ENV] = str(parsed.project_root.resolve())
    module = importlib.import_module(f"{__package__}.{COMMANDS[parsed.command][0]}")
    return int(module.main(remaining) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
