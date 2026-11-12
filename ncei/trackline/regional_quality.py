"""Build track bias, crossover evidence and track dispositions for six regions."""

import argparse

from .crossover import run_crossovers
from .disposition import run_disposition
from .track_bias import run_track_bias


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ncei.trackline regional-quality", description=__doc__)
    parser.add_argument("--overwrite", action="store_true", help="Replace existing six-region outputs.")
    args = parser.parse_args(argv)
    run_track_bias(overwrite=args.overwrite)
    status = run_crossovers(overwrite=args.overwrite)
    if status:
        return status
    run_disposition(overwrite=args.overwrite)
    return 0
