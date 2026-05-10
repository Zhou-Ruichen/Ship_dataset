#!/bin/bash
# 02_check_subzips.sh
# Verifies integrity of sub-zips and moves bad ones to raw/subzips_bad
# Usage: ./02_check_subzips.sh

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

SUBZIPS_DIR="$ROOT_DIR/raw/subzips"
BAD_DIR="$ROOT_DIR/raw/subzips_bad"
DOCS_DIR="$ROOT_DIR/docs"
BAD_LIST="$DOCS_DIR/bad_subzips.txt"

mkdir -p "$BAD_DIR"
mkdir -p "$DOCS_DIR"

echo "Checking sub-zips in $SUBZIPS_DIR..."
> "$BAD_LIST" # Clear list

count=0
bad_count=0

# Enable nullglob so loop doesn't run if no matches
shopt -s nullglob

for zipfile in "$SUBZIPS_DIR"/*.zip; do
    count=$((count + 1))

    # 7z t tests integrity
    if ! 7z t "$zipfile" > /dev/null 2>&1; then
        echo "BAD: $(basename "$zipfile")"
        echo "$(basename "$zipfile")" >> "$BAD_LIST"
        mv "$zipfile" "$BAD_DIR/"
        bad_count=$((bad_count + 1))
    fi

    if (( count % 50 == 0 )); then
        echo "Processed $count files..."
    fi
done

echo "Check complete. Processed: $count. Bad: $bad_count."
echo "Bad list saved to $BAD_LIST"
