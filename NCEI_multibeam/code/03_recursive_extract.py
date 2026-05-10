#!/usr/bin/env python3
# 03_recursive_extract.py
# Recursively extracts sub-zips to raw/dat_by_subzip
# Handles nested zips by extracting them in-place and deleting the intermediate zip.

import os
import subprocess
import shutil
from pathlib import Path
import sys

# Setup paths
SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent
SUBZIPS_DIR = ROOT_DIR / "raw" / "subzips"
OUTPUT_DIR = ROOT_DIR / "raw" / "dat_by_subzip"
BAD_DIR = ROOT_DIR / "raw" / "subzips_bad"


def extract_zip(zip_path, extract_to):
    """Extracts a zip file using 7z."""
    # -y: assume Yes on all queries
    # -o: output directory
    cmd = ["7z", "x", "-y", f"-o{extract_to}", str(zip_path)]
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if result.returncode != 0:
            print(
                f"  [ERROR] 7z failed for {zip_path.name}: {result.stderr.decode().strip()}"
            )
            return False
        return True
    except Exception as e:
        print(f"  [ERROR] Exception extracting {zip_path.name}: {e}")
        return False


def process_directory(directory):
    """Recursively finds and extracts zip files in a directory."""
    # Loop until no more zips are found in this directory tree
    while True:
        zips_found = list(directory.rglob("*.zip"))
        if not zips_found:
            break

        for zip_file in zips_found:
            # Extract to the same directory where the zip is
            parent_dir = zip_file.parent
            # print(f"    Extracting nested: {zip_file.name}")

            if extract_zip(zip_file, parent_dir):
                # Remove the zip file after successful extraction to keep it clean
                try:
                    zip_file.unlink()
                except OSError as e:
                    print(f"    [WARN] Could not delete {zip_file.name}: {e}")
            else:
                print(f"    [WARN] Failed to extract nested zip {zip_file.name}")
                # Rename it so we don't try again endlessly
                new_name = zip_file.with_suffix(".zip.bad")
                try:
                    zip_file.rename(new_name)
                except OSError:
                    pass


def main():
    if not SUBZIPS_DIR.exists():
        print(f"Error: {SUBZIPS_DIR} does not exist. Run 01_extract_subzips.sh first.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    BAD_DIR.mkdir(parents=True, exist_ok=True)

    subzips = sorted(list(SUBZIPS_DIR.glob("*.zip")))
    total = len(subzips)
    print(f"Found {total} sub-zips in {SUBZIPS_DIR}")

    for i, zip_file in enumerate(subzips, 1):
        subzip_name = zip_file.stem
        target_dir = OUTPUT_DIR / subzip_name

        # If target directory exists, we might want to skip or clean it.
        # For reproducibility, let's assume we want to ensure it's fresh if we run this.
        # But checking existence saves time on re-runs.
        if target_dir.exists():
            # Check if it has content?
            pass

        print(f"[{i}/{total}] Processing {subzip_name}...")

        # Ensure target dir exists
        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. Extract the main subzip
        if not extract_zip(zip_file, target_dir):
            print(f"  [FAIL] Could not extract {zip_file.name}. Moving to bad.")
            try:
                shutil.move(str(zip_file), str(BAD_DIR / zip_file.name))
            except shutil.Error:
                pass  # Already exists in bad

            # Cleanup partial extraction
            if target_dir.exists():
                shutil.rmtree(str(target_dir))
            continue

        # 2. Recursively handle nested zips
        process_directory(target_dir)

    print("Recursive extraction complete.")


if __name__ == "__main__":
    main()
