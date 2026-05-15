# NCEI Multibeam Data Processing

## 1. Background & Status
This dataset originates from two large archives:
- `/mnt/data2/00-Data/ship/jamstec/multibeam/archive/国外水深第一部分.zip`
- `/mnt/data2/00-Data/ship/jamstec/multibeam/archive/国外水深第二部分.zip`

**Verification:**
- SHA256 checksums verified (see `docs/sha256_remote.txt`).
- `7z t` integrity check passed for both large archives.
- Total expected sub-zips: **776** (excluding the 2 large archive filenames).

**Known Issues:**
- **Bad Sub-zips:** 13 sub-zips failed integrity checks and are moved to `raw/subzips_bad/` (see `docs/bad_subzips.txt`).
- **Nested Structure:** Some sub-zips contain `.dat` files directly, while others (e.g., `KM16-08_leg1_bathymetry_dmo.zip`) contain nested zips (e.g., `KM16-08_leg1.dat.zip`) which must be recursively extracted.

**Data Format:**
- Format: `.dat` text files.
- Columns: `lon lat depth_m` (Depth is positive meters).
- See **Section 4. Data Specifications** for detailed rules.

## 2. Directory Structure
```
jamstec/multibeam/
├── archive/                # Source large zip files
├── code/                   # Processing scripts
│   ├── 01_extract_subzips.sh
│   ├── 02_check_subzips.sh
│   ├── 03_recursive_extract.py
│   └── 04_organize_dat.sh
├── docs/                   # Logs and manifests
│   ├── bad_subzips.txt     # List of corrupted sub-zips
│   ├── dat_manifest.tsv    # Index of all extracted .dat files
│   └── sha256_remote.txt
├── raw/
│   ├── subzips/            # Extracted individual zip files (flat)
│   ├── subzips_bad/        # Corrupted sub-zips moved here
│   └── dat_by_subzip/      # Final extracted content, one folder per sub-zip
└── output/                 # (Reserved for future processing)
```

## 3. Processing Workflow
Run the scripts in `code/` in numerical order to reproduce the dataset.

### Step 1: Extract Sub-zips
Extracts the two large archives into `raw/subzips/`.
```bash
bash code/01_extract_subzips.sh
```

### Step 2: Verify Integrity
Checks each sub-zip. Corrupted files are moved to `raw/subzips_bad/`.
```bash
bash code/02_check_subzips.sh
```

### Step 3: Recursive Extraction
Extracts all sub-zips to `raw/dat_by_subzip/`.
- Handles nested zips (e.g., `.dat.zip`) by extracting them recursively.
- Deletes intermediate nested zip files to save space.
```bash
python3 code/03_recursive_extract.py
```

### Step 4: Index Data
Generates a manifest of all available `.dat` files at `docs/dat_manifest.tsv`.
```bash
bash code/04_organize_dat.sh
```

## 4. Data Specifications

### File Naming & Organization
The data is organized in `raw/dat_by_subzip/`, where each folder corresponds to a sub-zip.

**Folder Naming:**
- **Date-based:** e.g., `20120408/` (Contains daily data)
- **Cruise-based:** e.g., `KM16-08_leg1_bathymetry_dmo/` (Contains cruise data)

**File Naming Conventions:**
1.  **Daily Files:** `YYYYMMDD.dat` (e.g., `20120408.dat`) - Date is explicit.
2.  **Daily Files (Prefix):** `TYYYYMMDD.dat` (e.g., `T20101012.dat`) - Date is explicit.
3.  **Cruise Files:** `CruiseName.dat` (e.g., `KM16-08_leg1.dat`) - Date is implicit (associated with the cruise period).
4.  **Transit Files:** `CruiseName_t.dat` (e.g., `KM16-08_leg1_t.dat`) - Likely transit data (between stations/legs).

### Coordinate System
- **Format:** ASCII text, space-separated.
- **Columns:** `Longitude Latitude Depth`
- **Longitude:** -180 to 180 (Decimal Degrees). West is negative.
- **Latitude:** -90 to 90 (Decimal Degrees). South is negative.
- **Depth:** Positive meters (Down is positive).

### Metadata
- Some folders contain PDF files with cruise reports or readme files (e.g., `*_readme_eng.pdf`).
- `docs/dat_manifest.tsv` provides a full index of all available data files.

## 5. Usage Example (Python)

Here is a simple example of how to use the manifest to locate and load data files.

```python
import pandas as pd
import os

# 1. Load the manifest
manifest_path = 'docs/dat_manifest.tsv'
df_manifest = pd.read_csv(manifest_path, sep='\t')

print(f"Total files available: {len(df_manifest)}")
print(df_manifest.head())

# 2. Load a specific data file (e.g., the first one)
first_file_path = df_manifest.iloc[0]['Path']
print(f"Loading: {first_file_path}")

# Read the space-separated .dat file
# Columns: Longitude, Latitude, Depth
data = pd.read_csv(first_file_path, sep='\s+', header=None, names=['lon', 'lat', 'depth'])

print(data.describe())
```
