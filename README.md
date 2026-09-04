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
| `ncei/` | NCEI singlebeam and multibeam track archives | — | Global standardization, QC, bias, crossover, and disposition products available |

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
[`.trellis/spec/README.md`](.trellis/spec/README.md).

---

## Global model validation results (v1.0)

> **Global ship-cell model validation v1.0 is complete.**
> Frozen on `main` at commit `b376f95` (2026-05-28).

Reports:

- [`ncei/docs/step08_final_global_validation_report.md`](ncei/docs/step08_final_global_validation_report.md)
  — Stage 6 cross-stage final report; product-role policy stance.
- [`ncei/docs/publication_ready_step08_summary.md`](ncei/docs/publication_ready_step08_summary.md)
  — single outward-facing pack: metrics, bootstrap CIs, pairwise
  significance, gap-fill attribution, figure index.
- [`ncei/docs/model_ranking_uncertainty_report.md`](ncei/docs/model_ranking_uncertainty_report.md)
  — paired cluster block bootstrap CIs and ranking stability.
- [`ncei/docs/step08_gapfill_error_structure_report.md`](ncei/docs/step08_gapfill_error_structure_report.md)
  — expanded-primary gap-fill RMSE attribution by quality / depth / region.

Data and result-record rules: [`.trellis/spec/data/index.md`](.trellis/spec/data/index.md)
and [`.trellis/spec/shared/reproducibility.md`](.trellis/spec/shared/reproducibility.md).

Frozen ranking by strict-primary RMSE (N = 2,398,774 cells, 5 global models):
**GEBCO_2024 < ETOPO_2022 < SRTM15_V2.7 < TOPO_25.1 < SDUST_2023**. GEBCO
holds rank-1 with bootstrap probability 0.905; the GEBCO vs ETOPO pair
is *not* significant at 95% (ΔRMSE CI crosses 0).

Product-role policy (frozen at v1.0):

| product | role |
|---|---|
| `strict_primary_multibeam_cells` | global ranking baseline |
| `expanded_primary_ship_cells` | sensitivity / coverage expansion |
| `supplementary_singlebeam_cells` | non-primary coverage diagnostic |
| `regional_mrar_experiment_cells` | regional sensitivity only |
| `SWOT_T1` | separate regional task (not in v1.0) |

## Current singlebeam products

| Product | Path | How to use it |
|---|---|---|
| Global track bias | `ncei/derived/sb_track_bias_global/track_bias_summary.parquet` | Inspect the strict-multibeam bias estimate and whether it was applied to each supported track. |
| Global crossover audit | `ncei/derived/global_sb_crossover_audit/` | Inspect geometric crossing differences and nc time checks used to judge track consistency. |
| Global track disposition | `ncei/derived/sb_track_quality_global/track_quality.parquet` | Read one decision per singlebeam track, including the evidence and threshold behind it. |
| Final singlebeam cells, round 2 | `ncei/derived/singlebeam/file_cells_1min_final_r2/` | Use these cells outside strict-multibeam coverage and filter `track_disposition != 'reject'`; rows are marked, not deleted. |
| Six-region final controls | `ncei/derived/sb_track_bias_1min/controls_mb_sb_final_<tile>.parquet` | Use the retained strict-multibeam rows plus non-rejected final singlebeam rows for the named region. |

Use strict multibeam wherever it exists. Elsewhere use
`file_cells_1min_final_r2/` after filtering out rows whose
`track_disposition` is `reject`.

## Round-2 products (2026-09)

| Product | Path | Status / how to use |
|---|---|---|
| Merged global 1-arcmin grid, round 2 | `ncei/derived/global_grid_1min_r2/` | Spec §2 product (script `31_build_global_grid_1min.py`); strict mb wins, non-rejected final sb fills; `product_manifest.json` records input hashes. |
| Round-2 swath cruise three-layer set | `ncei/derived/mb_round2/<cruise>/{points_raw,points_checked,file_cells_1min}/` | L1/L2 for 12 complete cruises (10 × mb58 + 2 × mb21) + standalone L3 fragment `mb_round2_source_manifest_fragment.parquet`; **merge into production pending review** (`ncei/docs/step15_mb_round2_processing.md`). |
| MBBDB increment value ranking | `ncei/derived/mbbdb_value_ranking/` | A/B/C order lists for the next download round (`ncei/docs/step16_mbbdb_value_ranking.md`). |
| Round-2 raw sources | `ncei/raw_round2/{platforms_tree,r2r,mgd77t_static}/` | Raw swath archives + R2R products + static-tree MGD77T (in progress); provenance in `ncei/SOURCE.md`. |

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
├── ncei/                     # NCEI ship-data processing and retained products
│   ├── code/                 # Standardization, QC, cell, bias, crossover, and disposition stages
│   │   └── scs_confirmation/ # Archived SCS/TN352 confirmation chain, not an active pipeline stage
│   ├── docs/                 # Stage reports and product guidance
│   ├── manifests/            # Track identity and source records
│   └── derived/              # Generated products (ignored)
├── archive/                  # Top-level helper archives (ignored)
├── docs/                     # Cross-dataset documentation
│   ├── 多波束船测数据处理流程.md   # Authoritative pipeline overview
│   └── experiments/          # Finished investigations
├── .trellis/                 # Trellis workflow framework
│   ├── spec/                 # Data, evaluation, reproducibility, and writing rules
│   ├── tasks/                # Active and archived tasks
│   ├── workflow.md           # Phase guide
│   └── scripts/task.py       # Task lifecycle CLI
├── .claude/                  # Claude Code agent / hook / skill config
├── AGENTS.md                 # Trellis instructions for AI assistants
└── .gitignore
```

---

## Key conventions for contributors

The current project rules are indexed in [`.trellis/spec/README.md`](.trellis/spec/README.md):

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
  files of (per-file median)`, not `median over all points`; this gives
  each source file equal weight within a cell.

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

## Adding new ship data

Place new NCEI source files under the matching read-only source area:
`ncei/tracklines_nc/`, `ncei/tracklines_xyz/`, or `ncei/archive/source_zips/`.
Place JAMSTEC multibeam files under `jamstec/multibeam/raw/`. Do not mix new
inputs into an existing generated product.
Add their source paths and identities through the stage 01 manifest builder.
Compare `(track_id, source_type)` with
`ncei/manifests/trackline_source_manifest.parquet`: an unseen pair is a new
source record, while a matching pair retains the existing identity and is
handled as an updated source rather than a second track.

For NCEI ship data, rerun the applicable stages in this order from the repository
root: stage 01 manifest; stages 02–06 standardization and QC; stages 07–08 cell
products; stage 25 global bias; stage 26 global crossovers; stage 30 global
disposition and final cells. Read each script's arguments before running it and
keep existing derived rounds unchanged.

Raw swath multibeam downloaded from the NCEI platforms tree / R2R (round 2,
`ncei/raw_round2/`) follows the separate stage 32–37 chain: completeness audit
(32) → format census (33) → L1 extraction (34) → L2 cells (35) → L3 fragment
(36, standalone until reviewed) → coverage statistics (37). New source-side
values (`ncei_mb58`/`ncei_mb21`) enter production only after the fragment
merge is approved.

## Product rounds

Durable derived-product directories carry a round suffix, for example
`file_cells_1min_final_r2/`. Downstream work names the exact round instead of a
moving `final/` path. Each round's product manifest records its generation time,
input trackline-manifest SHA-256 value, input paths, output paths, and processing
command. A changed source manifest or disposition method produces a new round;
it does not overwrite an earlier round.

---

## Working with this repo via AI tools

The project uses [Trellis](https://github.com/) for AI-assisted
development. The current project rules live under `.trellis/spec/` and are
routed by `AGENTS.md` and `.trellis/workflow.md`.
Active and queued tasks live under `.trellis/tasks/`. See
[`AGENTS.md`](AGENTS.md) and [`.trellis/workflow.md`](.trellis/workflow.md)
for the full workflow.

The completed SCS/TN352 confirmation scripts were moved from the flat
`ncei/code/` listing to `ncei/code/scs_confirmation/`. They are retained for
provenance and are not part of the active ingestion pipeline.

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
