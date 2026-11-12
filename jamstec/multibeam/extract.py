"""Extract JAMSTEC source archives and build the DAT inventory."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from ._paths import PROJECT_ROOT, ROOT_ENV


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m jamstec.multibeam extract")
    parser.parse_args(argv)
    source = Path(__file__).resolve().parent / "source"
    env = os.environ.copy()
    env[ROOT_ENV] = str(PROJECT_ROOT)
    for script in ("extract_subzips.sh", "check_subzips.sh"):
        subprocess.run(["bash", str(source / script)], env=env, check=True)
    from .source.recursive_extract import main as recursive_extract

    recursive_extract()
    subprocess.run(["bash", str(source / "organize_dat.sh")], env=env, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
