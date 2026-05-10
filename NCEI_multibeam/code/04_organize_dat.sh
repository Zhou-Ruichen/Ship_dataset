#!/bin/bash
# 04_organize_dat.sh
# Finds all .dat files and creates a summary list
# Usage: ./04_organize_dat.sh

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

DAT_BY_SUBZIP="$ROOT_DIR/raw/dat_by_subzip"
DOCS_DIR="$ROOT_DIR/docs"
MANIFEST="$DOCS_DIR/dat_manifest.tsv"

mkdir -p "$DOCS_DIR"

echo "Organizing .dat files..."
echo -e "Subzip\tFilename\tPath" > "$MANIFEST"

# Find all .dat files
# We use find and process line by line
find "$DAT_BY_SUBZIP" -type f -name "*.dat" | while read -r filepath; do
    filename=$(basename "$filepath")
    # Get the subzip name (parent folder immediately under dat_by_subzip)
    # Path is .../raw/dat_by_subzip/<subzip_name>/.../file.dat
    # We strip the prefix up to dat_by_subzip/
    relpath="${filepath#$DAT_BY_SUBZIP/}"
    subzip_name=$(echo "$relpath" | cut -d'/' -f1)

    echo -e "$subzip_name\t$filename\t$filepath" >> "$MANIFEST"
done

echo "Manifest created at $MANIFEST"
echo "Total .dat files found: $(tail -n +2 "$MANIFEST" | wc -l)"
