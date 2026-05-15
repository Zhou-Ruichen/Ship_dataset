# Ship Bathymetry Dataset & Validation Pipeline

A reproducible pipeline that turns raw shipborne multibeam soundings into
1-arc-minute validation cells, then uses those cells to evaluate global
gridded bathymetry products (GEBCO, ETOPO, SRTM15+, SDUST, TOPO 25.1) and
SWOT-derived bathymetry, and to train residual-correction baselines on
held-out regions.

---

## What this repository contains

This repo holds **code, configuration, documentation, and small text
manifests only** — the actual data (raw `.dat`, derived parquet, source
zip archives) is intentionally not tracked. See `.gitignore` for the
exact exclusion list.

| Tracked | Not tracked (regenerable or external) |
|---|---|
| `jamstec/multibeam/code/` — 11-stage pipeline scripts | `**/raw/` (124 GB) — extracted `.dat` files |
| `jamstec/multibeam/configs/` — YAML configs | `**/derived/` (178 GB) — points / cells / models |
| `jamstec/multibeam/manifests/*.tsv` — small inventories | `**/archive/` (52 GB) — source zip / 7z |
| `jamstec/multibeam/figures/*.png` — paper figures | `*.parquet`, `*.zip`, `*.7z`, `*.nc`, `*.npz`, ... |
| `jamstec/multibeam/docs/*.md` — per-stage reports | `ncei/singlebeam.xyz` (3.1 GB flat dump) |
| `docs/` — cross-dataset reference docs | `**/output/logs/` — per-script run logs |
| `.trellis/` — workflow + spec + tasks | |
| `.claude/` — AI agent configuration | |

Reproducing the data products from a fresh clone requires obtaining the
source archives (see "Reproducibility" below).

---

## Datasets at a glance

| Directory | Source | Era | Pipeline status |
|---|---|---|---|
| `jamstec/multibeam/` | JAMSTEC (R/V Kaiyo / Kairei / Mirai / Kairei-Sonar; formerly mislabeled `NCEI_multibeam/`) | 2000–2015 | Step 00–11 complete |
| `jamstec/archive/bathymetry_data/` | Same JAMSTEC archive, alternate packaging | same | Source archive only; 13 `subzips_bad` recoverable from here |
| `jamstec/gravity_data/` | JAMSTEC gravity | — | Raw only, not yet processed |
| `ncei/` | NCEI singlebeam track archive | — | Raw `.nc` zip + flat `.xyz`; pipeline not yet built |

> **Provenance note**: `jamstec/multibeam/` was renamed from
> `NCEI_multibeam/` on 2026-05-16 (task `05-11-singlebeam-integration`
> PR-A) once a 2026-05 investigation confirmed the directory's content
> was entirely JAMSTEC, not NCEI. The string literal
> `source_dataset = "NCEI_multibeam"` still appears in 3 scripts under
> `jamstec/multibeam/code/` as a logical lineage label (load-bearing
> for Step 08 bit-identical verification, not a path). `ncei/` was
> renamed from `NCEI_singlebeam/` on 2026-05-16 (PR-B) as a symmetric
> pure-provenance refactor. Full evidence chain in
> [`docs/experiments/2026-05_dataset-source-attribution.md`](docs/experiments/2026-05_dataset-source-attribution.md).

---

## Pipeline overview (Step 00 -> Step 11)

The authoritative end-to-end description lives at
[`docs/多波束船测数据处理流程.md`](docs/多波束船测数据处理流程.md).
A short summary:

```
archive/*.zip
  |
  v   [00] shell extract + recursive unzip  (bash + 03_recursive_extract.py)
  v
raw/dat_by_subzip/*.dat        (5,140 audited / 5,083 processed)
  |
  v   [01] build manifest                    (01_build_multibeam_manifest.py)
  v   [02] standardize to parquet            (02_standardize_multibeam_xyz.py)
  v   [02a] curate manifest                  (02a_curate_points_manifest.py)
  v   [03] QC flags (no deletion)            (03_qc_multibeam_points.py)
  v   [04a] file-level 1' cells              (04a_make_multibeam_file_cells.py)
  v   [04b] file-balanced merge              (04b_merge_multibeam_cells.py)
  v   [05] overlap bias analysis             (05_analyze_cell_overlap_bias.py)
  v   [06a] extreme bias investigation       (06a_investigate_extreme_bias_sources.py)
  v   [06b] file quality flags               (06b_create_file_quality_flags_1min.py)
  v   [06c] rebuild QC-filtered cells        (06c_rebuild_cells_1min_qcfiltered.py)
  v   [06d] before/after comparison          (06d_compare_original_vs_qcfiltered_cells.py)
  v   [07] primary validation cells +        (07_prepare_primary_validation_cells_1min.py)
  v        A/B/C tier assignment
  v
derived/validation_cells_1min/primary_ship_validation_cells_1min.parquet
  |        (2,394,115 cells — the canonical exported product)
  |
  v   [08] validate gridded products         (08_validate_gridded_products_against_ship_cells.py)
  v   [09] SWOT T1 batch validation          (09_batch_validate_swot_t1.py + analyze)
  v   [10] residual dataset + 0.25° splits   (10_*, 10b_*)
  v   [11] residual baselines (XGB/LGBM/...) (11_train_residual_baselines_T1.py)
```

Key design choices behind these steps (file-balanced median, 1' grid,
A/B/C tiering, `run-label` gating, residual sign convention) are
documented in
[`.trellis/spec/backend/pipeline-design-decisions.md`](.trellis/spec/backend/pipeline-design-decisions.md).

---

## Repository layout

```
ship/
├── jamstec/                  # All JAMSTEC data (unified 2026-05-16 in PR-A)
│   ├── multibeam/            # JAMSTEC multibeam pipeline (formerly NCEI_multibeam/)
│   │   ├── code/             # 11-stage Python + shell scripts (tracked)
│   │   ├── configs/          # YAML for Step 08 product validation
│   │   ├── docs/             # Per-stage reports + schemas + cruise inventory
│   │   ├── figures/          # Paper figures (PNG)
│   │   ├── manifests/        # File inventories (TSV tracked, parquet ignored)
│   │   ├── raw/              # Extracted .dat files (ignored)
│   │   ├── derived/          # Pipeline outputs (ignored)
│   │   ├── archive/          # Source zips (ignored, external backup required)
│   │   └── output/logs/      # Per-script logs (ignored)
│   ├── gravity_data/         # Gravity zips (ignored, not yet processed)
│   └── archive/              # Frozen source archives (ignored)
│       ├── source_zips/      # 国外水深第一/第二部分.zip etc.
│       └── bathymetry_data/  # 776 cruise zips (same source as multibeam/raw/subzips)
├── ncei/                     # NCEI singlebeam — pipeline not yet built (renamed 2026-05-16 in PR-B)
│   ├── docs/                 # README + reference paper
│   └── singlebeam.xyz        # 3.1 GB flat dump (ignored; PR-C will archive)
├── archive/                  # Top-level helper archives (ignored)
├── docs/                     # Cross-dataset documentation
│   ├── 多波束船测数据处理流程.md   # Authoritative pipeline overview
│   └── experiments/          # Finished investigations
├── .trellis/                 # Trellis workflow framework
│   ├── spec/backend/         # Pipeline conventions (English)
│   ├── tasks/                # Active and archived tasks
│   ├── workflow.md           # Phase guide
│   └── scripts/task.py       # Task lifecycle CLI
├── .claude/                  # Claude Code agent / hook / skill config
├── AGENTS.md                 # Trellis instructions for AI assistants
└── .gitignore
```

---

## Key conventions for contributors

These are formalized in `.trellis/spec/backend/`:

- **Run-label gating**: every long stage (Step 02 / 03 / 04a, ~hours)
  refuses to run in `full` mode without `--confirm-full`, and writes
  `sample` / `test100` outputs to suffixed directories.
- **Resumability**: stages skip files whose output already exists unless
  `--overwrite`. A clean re-run completes in seconds with zero new output.
- **Per-file failure pattern**: bad files are appended to
  `output/logs/<script>_errors.tsv`; the run continues. A 5,083-file
  batch with 47 failures still exits 0.
- **Shard-per-file invariant**: per-file outputs go to
  `derived/<stage>/<file_id>.parquet`. Never concatenate into a monolith.
- **`file_id` is the cross-stage primary key**: format
  `<subzip>::<basename>.dat`. Never reconstruct it from filesystem
  normalization.
- **File-balanced aggregation**: cell-level products use `median over
  files of (per-file median)`, not `median over all points`. The
  difference is load-bearing — see
  [`pipeline-design-decisions.md`](.trellis/spec/backend/pipeline-design-decisions.md) §3.

---

## Reproducibility

To rebuild the data products from a fresh clone you need:

1. The two JAMSTEC source archives (~25 GB total) placed at
   `jamstec/multibeam/archive/{国外水深第一部分.zip,国外水深第二部分.zip}`
   *or* equivalently at `jamstec/archive/source_zips/bathymetry.7z`.
   These archives are not in git and must be obtained externally.
2. Python 3 with `pandas`, `numpy`, `pyarrow`, `xarray`, `scipy`,
   `scikit-learn`, `xgboost`, `lightgbm`, `cartopy`, `matplotlib`.
3. About 350 GB of free disk for `raw/` + `derived/`.
4. Then run the Step 00 -> Step 11 sequence in
   [`jamstec/multibeam/docs/PIPELINE_PROCESSING_GUIDE.md`](jamstec/multibeam/docs/PIPELINE_PROCESSING_GUIDE.md).
   A full run takes ~6–10 hours of single-machine time.

---

## Working with this repo via AI tools

The project uses [Trellis](https://github.com/) for AI-assisted
development. The `.trellis/spec/backend/` directory is auto-injected into
every AI sub-agent prompt, so an assistant working in this repo will
match the team's actual conventions instead of writing generic Python.
Active and queued tasks live under `.trellis/tasks/`. See
[`AGENTS.md`](AGENTS.md) and [`.trellis/workflow.md`](.trellis/workflow.md)
for the full workflow.

---

## License & data attribution

Code in this repository: see the LICENSE file (to be added).

Bathymetric soundings ingested by this pipeline originate from JAMSTEC
research vessels (R/V Kaiyo, Kairei, Mirai, plus collaborators) and from
the NCEI singlebeam track archive. Any downstream paper, dataset
release, or visualization built from this code must credit those
sources, not the directory names in this repository. See
[`docs/experiments/2026-05_dataset-source-attribution.md`](docs/experiments/2026-05_dataset-source-attribution.md)
for the suggested citation language.
