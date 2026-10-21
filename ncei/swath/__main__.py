"""Command line dispatcher for the NCEI round-2 swath chain."""

from __future__ import annotations

import argparse
import importlib
import sys


COMMANDS = {
    "census": ("census", "Count raw round-2 file formats."),
    "extract": ("extract", "Extract round-2 L1 points."),
    "file-cells": ("file_cells", "Aggregate round-2 L2 file cells."),
    "manifest": ("manifest_fragment", "Build the round-2 source-manifest fragment."),
    "coverage": ("coverage", "Compare round-2 coverage with the strict layer."),
    "quality-revision": ("quality_revision", "Rebuild isolated round-2 quality products."),
    "batch": ("batch", "Process selected staged cruises end to end."),
}

ALIASES = {
    "33": "census", "34": "extract", "35": "file-cells", "36": "manifest",
    "37": "coverage", "43": "quality-revision",
}


def parser() -> argparse.ArgumentParser:
    lines = ["Commands (in processing order):"]
    for command, (_, description) in COMMANDS.items():
        aliases = ", ".join(key for key, value in ALIASES.items() if value == command)
        label = f"{command} ({aliases})" if aliases else command
        lines.append(f"  {label:<31} {description}")
    ap = argparse.ArgumentParser(
        prog="python -m ncei.swath",
        description="Run the NCEI swath processing chain.",
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
