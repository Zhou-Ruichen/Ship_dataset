#!/bin/bash
# 05_cleanup.sh
# Removes intermediate files to save space.
# WARNING: This deletes raw/subzips/ which can be re-generated from archive/
# Usage: ./05_cleanup.sh

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

SUBZIPS_DIR="$ROOT_DIR/raw/subzips"

echo "Cleaning up intermediate files..."

if [ -d "$SUBZIPS_DIR" ]; then
    echo "Removing $SUBZIPS_DIR..."
    rm -rf "$SUBZIPS_DIR"
    echo "Done."
else
    echo "$SUBZIPS_DIR does not exist or is already removed."
fi

echo "Note: raw/subzips_bad/ has been KEPT for your reference."
echo "To remove it, run: rm -rf $ROOT_DIR/raw/subzips_bad"
