#!/bin/bash
# 01_extract_subzips.sh
# Extracts sub-zips from the main archives to raw/subzips
# Usage: ./01_extract_subzips.sh

set -e

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

ARCHIVE_DIR="$ROOT_DIR/archive"
SUBZIPS_DIR="$ROOT_DIR/raw/subzips"

mkdir -p "$SUBZIPS_DIR"

echo "Extracting from archives to $SUBZIPS_DIR..."

# Function to extract
extract_archive() {
    local archive="$1"
    if [ -f "$archive" ]; then
        echo "Processing $(basename "$archive")..."
        # -y: assume yes
        # -o: output dir
        # e: extract files from archive (without using directory names) -> Flattens structure
        # We use 'e' because we want all sub-zips in one flat folder,
        # and we assume the large zip structure is just a container.
        7z e -y -o"$SUBZIPS_DIR" "$archive"
    else
        echo "Archive not found: $archive"
    fi
}

extract_archive "$ARCHIVE_DIR/国外水深第一部分.zip"
extract_archive "$ARCHIVE_DIR/国外水深第二部分.zip"

echo "Extraction complete."
echo "Sub-zips are in $SUBZIPS_DIR"
