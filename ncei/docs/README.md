# NCEI Trackline Data — Singlebeam Pipeline

NCEI Marine Trackline Geophysical Data ingestion + cell-level quality
products. Started as a flat-XYZ archive note; rebuilt as a 13-script
per-track pipeline by task `.trellis/tasks/05-11-singlebeam-integration`
(PR-A through PR-G, May 2026).

## Pipeline at a glance

| Step | Script | Output |
|---|---|---|
| 01 | `code/01_build_trackline_source_manifest.py` | `manifests/trackline_source_manifest.parquet` (7,400 rows; R2 sb/mb classifier) |
| 02 | `code/02_standardize_singlebeam.py` | `derived/singlebeam/points_raw/<id>__nc.parquet` (1,850 tracks) |
| 03 | `code/03_standardize_xyz.py` | `derived/{singlebeam,multibeam}/points_raw/<id>__xyz.parquet` (5,382 tracks, sb+mb routed) |
| 04 | `code/04_clean_mrar.py` | `archive/zhoushuai_processed_M/{bathymetry_points,land_mask}.parquet` (113.4M rows cleaned) |
| 05 | `code/05_point_quality_check.py` (Step 03A) | `derived/{branch}/points_checked/*.parquet` + entry manifest |
| 06 | `code/06_supplementary_quality_check.py` (Step 03B) | supplementary manifest + intersect divergence audit |
| 07 | `code/07_aggregate_file_cells_1min.py` (Step 04A) | `derived/{branch}/file_cells_1min/*.parquet` (per-track 1-arcmin cells) |
| 08 | `code/08_merge_branch_cells_1min.py` (Step 04B) | `derived/{branch}/cells_1min/` (hive-partitioned merged cells) |
| 09 | `code/09_source_specific_overlap_residuals.py` (Step 05A) | within-branch residuals |
| 10 | `code/10_cross_branch_overlap_audit.py` (Step 05B) | cross-branch overlap residuals |
| 11 | `code/11_quality_policy_calibration_audit.py` (Step 06A) | stratified evidence + 16 candidate rules |
| 12 | `code/12_apply_quality_policy.py` (Step 06B) | `derived/quality_flags_1min/cell_quality_flags_1min.parquet` (23.6M cells, 31 cols) |
| 13 | `code/13_build_validation_cells.py` (Step 07B) | `derived/validation_cells_1min/` (5 final products) |

Run any step from repo root: `python ncei/code/<NN>_*.py --run-label sample|test100|full` (full requires `--confirm-full`).

## Three branches (do not collapse)

Per spec §13.6 / §18.8 / §19:

| branch | source | n cells (Step 04B) | branch_role | use |
|---|---|---:|---|---|
| `singlebeam` | NCEI nc + xyz, R2 pred=sb | 14,611,054 | `supplementary_coverage` | primary fill + supplementary coverage |
| `multibeam_ncei` | NCEI xyz, R2 pred=mb (incl. AUV Sentry) | 5,960 | `multibeam_supplement` | strict primary candidate |
| `regional_mrar` | 周帅-provided M.rar processed | 9,019,383 | `regional_experiment` | sensitivity / experiment only, NEVER primary |

M.rar stays **distinct** from `multibeam_ncei` even though both are
multibeam-class — different sign conventions (pre-PR-F: nc/xyz
positive-down vs M.rar negative-down) and different provenance opacity.

## 5 final validation products (Step 07B)

Under `derived/validation_cells_1min/`:

| product | rows | source mix |
|---|---:|---|
| `strict_primary_multibeam_cells.parquet` | 2,398,774 | JAMSTEC 2,394,115 + NCEI mb 4,659 (0 cell_id overlap) |
| `expanded_primary_ship_cells.parquet` | 2,732,689 | strict + sb high-conf gap-fill |
| `supplementary_singlebeam_cells.parquet` | 12,277,633 | sb supplementary coverage |
| `regional_mrar_experiment_cells.parquet` | 9,019,383 | all mrar, sensitivity-only |
| `validation_cell_catalog.parquet` | 24,029,705 | long-format catalog |

Source precedence is **fixed** (§19.2):
```
JAMSTEC mb  >  NCEI mb (strict primary)  >  NCEI sb high-confidence (expanded primary fill)
regional_mrar → always regional_experiment (NEVER primary, NEVER expanded primary)
```

## Quality tiers (Step 06A audit + Step 06B enforce)

| candidate_tier | weight range | n cells (full) |
|---|---|---:|
| `high_confidence` | 0.85–1.0 | ~2.5M (NCEI mb 293 + JAMSTEC A 1.5M + NCEI sb high 100k) |
| `medium_confidence` | 0.55–0.75 | ~700k |
| `low_confidence` | 0.25–0.35 | ~11.9M |
| `review_or_sensitivity_only` | 0.10–0.30 | ~11.3M |

16 enforced rules + 1 invariant (manual_review_not_exclusion) live in
`.trellis/tasks/05-11-singlebeam-integration/research/quality_policy_enforced_rules.tsv`.

## Key conventions (pinned in spec §13–§19)

- **cell_id** = `f"1min_{lat_bin}_{lon_bin}"` with non-negative bins
  `floor((lon+180)/cell_deg)`, `floor((lat+90)/cell_deg)`. Shared with
  JAMSTEC pipeline.
- **depth sign**: `depth_m_positive_down` (PR-F universal clip ±11,500m;
  M.rar raw was negative-down, flipped in cleaning).
- **dedup convention**: exact-float equality on `(lon, lat, depth)`
  triples. Audit-time rounded triples are NOT production.
- **AUV Sentry**: 8 mb cells with dup_ratio > 0.5; downweight to 0.55
  with `auv_sentry_flag=True` + `source_risk_class='auv_sentry_highdup'`.
  Never excluded, never get a separate `branch_role`.
- **manual_review_flag**: **NEVER** excludes or upgrades a cell on its
  own (enforced as invariant in Step 06B).
- **Weight scales NOT rescaled**: JAMSTEC legacy ∈ {0.4, 0.7, 1.0} and
  NCEI Step 06B ∈ [0.1, 0.95] coexist in validation products; downstream
  Step 11 chooses how to combine.

## Source data

Raw inputs (all under `archive/` or upstream paths, all gitignored):

- `tracklines_nc/*.nc` — 2,018 MGD77+ per-track NetCDF files (PR-C ingest)
- `tracklines_xyz/*.xyz` — 5,382 per-track XYZ files (PR-C ingest)
- `archive/zhoushuai_processed_M/*.txt` — 3 quadrant TSVs from M.rar
  (113.4M total points; PR-C → PR-F cleaning)
- `archive/sunmingzhi_singlebeam_xyz/singlebeam.xyz` — legacy flat XYZ
  (114.5M points; superseded by per-track ingest)
- `NCEI_singlebeam_tracks_raw_2018files.zip` — original 2,018-file
  archive (matches a subset of singlebeam.xyz; see commit history)

## Provenance / further reading

- Per-step reports under `docs/step{0NA,03_,03b,04_,04a,04b,05a,05b,06a,06b,07a,07b,mrar,trackline,singlebeam,xyz}_*.md`
- Task PRD: `.trellis/tasks/05-11-singlebeam-integration/prd.md`
- Spec sections: `.trellis/spec/backend/pipeline-design-decisions.md`
  §13 (Step 04A) → §19 (Step 07B)
- Cross-cutting contracts: `.trellis/spec/backend/data-contracts.md`
- Source-attribution evidence (NCEI_multibeam → JAMSTEC rename):
  `docs/experiments/2026-05_dataset-source-attribution.md`
- M.rar provenance / cleaning: `archive/zhoushuai_processed_M/SOURCE.md`
- Reference paper:
  `docs/On the accuracy evaluation and correction of global single-beam depths.pdf`
