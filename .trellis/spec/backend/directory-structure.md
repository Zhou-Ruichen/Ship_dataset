# Directory Structure

> How code and data are organized in this project.

This is a **Python data-processing project**, not a web backend. There is no
ORM, no HTTP layer, no service classes. Each dataset lives in its own
top-level directory and follows the same internal layout.

---

## Top-level layout

```
ship/
├── jamstec/                # All JAMSTEC data (2000–2020+), unified under one tree.
│   ├── multibeam/          # Active processed pipeline (Step 00–11 complete).
│   │                       #   Formerly ship/NCEI_multibeam/ — renamed 2026-05-16
│   │                       #   when JAMSTEC provenance was confirmed.
│   ├── gravity_data/       # JAMSTEC gravity sub-corpus. Raw only, no pipeline.
│   └── archive/            # Frozen source archives (don't process directly).
│       ├── source_zips/    # 国外水深第一/第二部分.zip etc. (~27 GB)
│       └── bathymetry_data/# 776 cruise-named zips (~25 GB; same source as multibeam/raw/subzips)
├── ncei/                   # NCEI singlebeam track corpus. Formerly
│                           #   ship/NCEI_singlebeam/ — renamed 2026-05-16
│                           #   (PR-B). PR-C will populate tracklines_{nc,xyz}/
│                           #   and archive/ subdirs.
├── _common/                # Shared lib for jamstec + ncei pipelines (PR-D, 2026-05-16).
│                           #   Houses R2 sb/mb classifier today; PR-E will migrate
│                           #   Step 03/04a/04b/05/06a-d/07–11 algorithmic primitives
│                           #   here. Importable from any script run with cwd = repo root.
├── archive/                # Top-level original downloaded zips (do not delete).
├── docs/                   # Cross-dataset documentation
│   └── experiments/        # Finished investigations / experiment narratives
├── .trellis/               # Trellis spec / tasks / workspace
└── AGENTS.md               # Trellis-managed agent instructions
```

For the source-attribution evidence behind the JAMSTEC provenance (which
the historical `NCEI_multibeam/` name obscured), see
[`docs/experiments/2026-05_dataset-source-attribution.md`](../../../docs/experiments/2026-05_dataset-source-attribution.md).

Each dataset directory follows the same internal layout when populated:

```
<dataset>/
├── code/                # Numbered Python scripts (01_*.py … 11_*.py) + helper .sh
├── configs/             # YAML configs consumed by --config flags
├── manifests/           # Parquet/TSV file inventories and per-stage manifests
├── derived/             # Intermediate + final products (parquet, npz, etc.)
├── raw/                 # Extracted source files (subzips, .dat)
├── output/logs/         # Per-script .log files + *_errors.tsv
├── docs/                # Per-dataset reports + schema docs
├── figures/             # Generated plots (pdf/png)
└── archive/             # (optional) old runs preserved for reproducibility
```

---

## Script naming

Scripts are numbered by **pipeline stage**, not by author or feature:

```
01_build_multibeam_manifest.py
02_standardize_multibeam_xyz.py
02a_curate_points_manifest.py        # 'a' suffix = subprocedure of step 02
03_qc_multibeam_points.py
04a_make_multibeam_file_cells.py     # per-file aggregation
04b_merge_multibeam_cells.py         # global merge
06a_… 06b_… 06c_… 06d_…              # multi-step investigation under one stage
```

Rules:
- **Two-digit prefix** = pipeline stage. Never reuse a number for a different
  purpose. New stages append at the end.
- **Letter suffix** (`a/b/c/d`) = ordered sub-steps within one stage. Each
  letter has a single script.
- **Shell scripts** (`*.sh`) handle pre-extraction (`01_extract_subzips.sh`,
  `02_check_subzips.sh`) — the corresponding numeric Python step takes over
  after.
- The number `00` is reserved for shell pre-processing.
- Helper / non-pipeline scripts (`plot_multibeam_figures.py`) have no numeric
  prefix and live in the same `code/` directory.

---

## Output paths (always relative to dataset root)

| Kind | Path | Example |
|------|------|---------|
| Per-file intermediate | `derived/<stage>/<file_id>.parquet` | `derived/points_qc/MR03-K02__20030527.parquet` |
| Aggregated product | `derived/<stage>/cells.parquet` | `derived/cells_1min/cells.parquet` |
| Manifest | `manifests/<name>_manifest.parquet` (+ `.tsv` mirror) | `manifests/file_quality_flags_1min.parquet` |
| Report | `docs/<stage>_report.md` | `docs/qc_points_report.md` |
| Log | `output/logs/<script_name>.log` | `output/logs/03_qc_multibeam_points.log` |
| Error rows | `output/logs/<script_name>_errors.tsv` | `output/logs/03_qc_errors.tsv` |
| Config | `configs/<purpose>.yaml` | `configs/gridded_products_validation.yaml` |
| Figure | `figures/<name>.pdf` | `figures/qc_depth_histogram.pdf` |

Path resolution at the top of every script:

```python
SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent          # dataset root, NOT repo root
```

Never use the repo root or `os.getcwd()` for path resolution — scripts must
run from any working directory.

---

## Where new code goes

| Kind of work | Location |
|---|---|
| New pipeline stage on existing dataset | New `<NN>_*.py` in that dataset's `code/` |
| Sub-step of an existing stage | New `<NN><letter>_*.py` next to siblings |
| New dataset | New top-level dir (`<NAME>/`) mirroring the layout above |
| One-off analysis / plotting | Un-numbered script in `code/`, output to `figures/` |
| Cross-dataset utility shared across pipelines | `_common/` (see top-level layout above) |

`_common/` is the single carved-out shared lib. PR-D (2026-05-16) seeded
it with the R2 sb/mb classifier; PR-E will migrate the Step 03–11
algorithmic primitives that `jamstec/multibeam/` and `ncei/` both reuse.
Anything genuinely cross-dataset belongs there. Anything dataset-specific
(Step 02 readers, Step 07 thresholds re-calibrated per sensor type)
stays in `<dataset>/code/`.

Imports from `_common/` work via the project-wide
"run from repo root" execution convention — see
[`pipeline-design-decisions.md`](./pipeline-design-decisions.md#11-python-execution-convention--run-from-repo-root)
§11 and [`AGENTS.md`](../../../AGENTS.md#python-execution-convention-run-from-repo-root)
for the full rationale.
