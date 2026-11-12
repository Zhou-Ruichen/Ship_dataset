# JAMSTEC Multibeam Data Processing

## 1. Source archives and status

The dataset originates from two archives:

- `jamstec/multibeam/archive/国外水深第一部分.zip`
- `jamstec/multibeam/archive/国外水深第二部分.zip`

Equivalent source packaging is retained under `jamstec/archive/`. The archive
SHA-256 values are recorded in `docs/sha256_remote.txt`; both large archives
passed the `7z t` integrity check. The expected source inventory contains 776
sub-zips. Thirteen damaged sub-zips are listed in `docs/bad_subzips.txt` and
quarantined under `raw/subzips_bad/`.

Some sub-zips contain `.dat` files directly; others contain nested zip files.
The `extract` command handles both forms and writes the final payload under
`raw/dat_by_subzip/`.

## 2. Current package layout

```text
jamstec/multibeam/
├── __main__.py              # python -m jamstec.multibeam
├── extract.py               # archive extraction and DAT inventory
├── manifest.py              # source format audit and manifests
├── curate.py                # source inclusion and duplicate candidates
├── standardize.py           # DAT -> L1 point tables
├── point_qc.py              # point-quality flags
├── file_cells.py            # per-file one-minute cells
├── merge_cells.py           # file-balanced merged cells
├── quality.py               # stages 05, 06a, 06b, 06c, 06d in order
├── validation_cells.py      # primary and sensitivity validation cells
├── config/                  # reviewed source-quality exception tables
├── configs/                 # frozen gridded-product validation configuration
├── source/                  # extraction helpers called by extract
├── docs/                    # schemas, reports and source records
├── manifests/               # tracked TSV product inventories
├── figures/                 # retained figures
├── raw/                     # extracted sources, not tracked by git
├── derived/                 # generated products, not tracked by git
└── output/logs/             # run logs
```

The completed model-validation, SWOT and residual-baseline analysis code has
left the working tree. Its reports, configuration and figures remain. Removed
code is indexed in `docs/code_archive.md` at the repository root.

## 3. Run the pipeline

Run from the repository root with the project Python environment:

```bash
/opt/miniforge3/envs/torch29/bin/python -m jamstec.multibeam --help
/opt/miniforge3/envs/torch29/bin/python -m jamstec.multibeam extract
```

`extract` performs the four source steps in order: outer-archive extraction,
subzip integrity checks, recursive nested-zip extraction and DAT inventory.
It writes `raw/subzips/`, `raw/dat_by_subzip/` and `docs/dat_manifest.tsv`.
Intermediate nested zip files are removed after successful extraction.

See `PIPELINE_PROCESSING_GUIDE.md` for the remaining commands, products and
scientific conventions. Every command supports `--help` without starting
processing.

For an isolated check, place inputs under the same relative layout and select
another project root before the command name:

```bash
/opt/miniforge3/envs/torch29/bin/python -m jamstec.multibeam \
  --project-root jamstec/multibeam/derived/refactor_check/core/project \
  manifest --help
```

The default root is `jamstec/multibeam/`. Do not use an existing product root
as a scratch output root.

## 4. Source data conventions

Source files are ASCII tables under `raw/dat_by_subzip/<subzip>/`. The manifest
distinguishes the two bathymetric layouts:

- three columns: `lon lat depth`;
- six columns: `date time sonar lon lat depth`.

Depth is metres positive downward. Standardization retains raw coordinates,
normalizes longitude to `[-180, 180)`, and adds elevation as `-depth`.
Transit and auxiliary sources are marked during `curate`; inclusion is
controlled by `include_in_points_raw`, not inferred from a filename at a later
stage.

`docs/dat_manifest.tsv` is the source inventory. Read it from the repository
root rather than relying on the historical absolute `Path` values:

```python
from pathlib import Path
import pandas as pd

repo = Path("/mnt/data2/00-Data/ship")
project = repo / "jamstec/multibeam"
manifest = pd.read_csv(project / "docs/dat_manifest.tsv", sep="\t")
row = manifest.iloc[0]
source = project / "raw/dat_by_subzip" / row["Subzip"] / row["Filename"]
points = pd.read_csv(source, sep=r"\s+", header=None, names=["lon", "lat", "depth"])
```

The detailed point-table contract is in `docs/point_schema_v1.md`.
