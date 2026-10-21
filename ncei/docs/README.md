# NCEI Trackline Data — Singlebeam Pipeline

NCEI Marine Trackline Geophysical Data ingestion + cell-level quality
products. Started as a flat-XYZ archive note; rebuilt as a 13-script
per-track pipeline by task `.trellis/tasks/archive/2026-05/05-11-singlebeam-integration`
(PR-A through PR-G, May 2026).

## Pipeline at a glance

| Step | Command (`python -m ncei.trackline ...`) | Output |
|---|---|---|
| 01 | `01` / `manifest` | `manifests/trackline_source_manifest.parquet` (7,400 rows; R2 sb/mb classifier) |
| 02 | `02` / `standardize-nc` | `derived/singlebeam/points_raw/<id>__nc.parquet` (1,850 tracks) |
| 03 | `03` / `standardize-xyz` | `derived/{singlebeam,multibeam}/points_raw/<id>__xyz.parquet` (5,382 tracks, sb+mb routed) |
| 04 | `04` / `clean-mrar` | `archive/zhoushuai_processed_M/{bathymetry_points,land_mask}.parquet` (113.4M rows cleaned) |
| 05 | `05` / `point-qc` (Step 03A) | `derived/{branch}/points_checked/*.parquet` + entry manifest |
| 06 | `06` / `supplementary-qc` (Step 03B) | supplementary manifest + intersect divergence audit |
| 07 | `07` / `file-cells` (Step 04A) | `derived/{branch}/file_cells_1min/*.parquet` (per-track 1-arcmin cells) |
| 08 | `08` / `merge-cells` (Step 04B) | `derived/{branch}/cells_1min/` (hive-partitioned merged cells) |
| 09 | `09` / `source-overlap` (Step 05A) | within-branch residuals |
| 10 | `10` / `branch-overlap` (Step 05B) | cross-branch overlap residuals |
| 11 | `11` / `policy-audit` (Step 06A) | stratified evidence + 16 candidate rules |
| 12 | `12` / `apply-policy` (Step 06B) | `derived/quality_flags_1min/cell_quality_flags_1min.parquet` (23.6M cells, 31 cols) |
| 13 | `13` / `validation-cells` (Step 07B) | `derived/validation_cells_1min/` (5 final products) |

Stages 23–26, 28, 30–31, 39–40 (regional/global singlebeam chains, global grid, MGD77T static
bypass) run through the same dispatcher; `python -m ncei.trackline --help`
lists every command. The round-2 swath chain is
`python -m ncei.swath <command>` (stages 33–37, 43).

Run the trackline chain from repo root via `python -m ncei.trackline <command>` (stage numbers work as aliases). Commands accepting `--run-label full` retain the `--confirm-full` gate. Frozen analyses (Step 08 pack 14–22, 27, 29) live under `ncei/analysis/`.

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
`.trellis/tasks/archive/2026-05/05-11-singlebeam-integration/research/quality_policy_enforced_rules.tsv`.

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

## Step 08 publication pack (v1.0)

Global gridded-product validation results, frozen at commit `b376f95`
(2026-05-28):

- [`step08_final_global_validation_report.md`](step08_final_global_validation_report.md)
  — Stage 6 cross-stage final report (policy stance).
- [`publication_ready_step08_summary.md`](publication_ready_step08_summary.md)
  — outward-facing summary (metrics, bootstrap CIs, attribution, figure index).
- [`model_ranking_uncertainty_report.md`](model_ranking_uncertainty_report.md)
  — paired cluster block bootstrap CIs and ranking stability.
- [`step08_gapfill_error_structure_report.md`](step08_gapfill_error_structure_report.md)
  — gap-fill RMSE attribution by quality tier / depth / region.

Method spec: `.trellis/spec/backend/step08_publication_pack.md` (removed from
the working tree in commit `37bb180`; read it there via
`git show 37bb180:.trellis/spec/backend/step08_publication_pack.md`).
Machine-readable artifacts (gitignored) land under
`derived/model_validation_1min_step08_pub/{a_ranking_uncertainty,b_pub_tables,c_gapfill_structure,d_figures,summary}/`.

## Provenance / further reading

- Task PRD: `.trellis/tasks/archive/2026-05/05-11-singlebeam-integration/prd.md`
- Spec sections: `.trellis/spec/backend/pipeline-design-decisions.md`
  §13 (Step 04A) → §19 (Step 07B) — spec tree restructured in `37bb180`;
  read the frozen sections via
  `git show 37bb180:.trellis/spec/backend/pipeline-design-decisions.md`
- Cross-cutting contracts: `.trellis/spec/backend/data-contracts.md`
  (same commit)
- Source-attribution evidence (NCEI_multibeam → JAMSTEC rename):
  `docs/experiments/2026-05_dataset-source-attribution.md`
- M.rar provenance / cleaning: `archive/zhoushuai_processed_M/SOURCE.md`
- Reference paper:
  `ncei/docs/On the accuracy evaluation and correction of global single-beam depths.pdf`

## Document status groups

Docs in this directory split into three groups. "Current product
description" documents are the authority for a released or frozen product;
"historical stage reports" record one finished run and are not updated;
"external literature" is reference material.

### Current product descriptions

| Document | Describes |
|---|---|
| `README.md` | this index |
| `trackline_source_manifest_schema.md` | L3 per-column semantics |
| `trackline_source_manifest_report.md` | L3 generation report |
| `step03_point_quality_check_report.md` | points_checked manifest (authoritative generation record) |
| `step07a_validation_cell_preflight_report.md`, `step07b_validation_cells_report.md` | strict_primary generation record (manifest backfill basis) |
| `step08_final_global_validation_report.md` | v1.0 frozen validation report (policy stance) |
| `publication_ready_step08_summary.md` | v1.0 outward-facing summary |
| `model_ranking_uncertainty_report.md` | v1.0 bootstrap CIs + ranking stability |
| `step08_gapfill_error_structure_report.md` | v1.0 gap-fill RMSE attribution |
| `step10_sb_interpolation_holdout_report.md` | holdout evidence behind spec §3 |
| `step10_global_sb_final_product_report.md`, `step10_global_sb_products_report.md` | 25/26/30 global products |
| `step15_mb_round2_processing.md` | round-2 three-layer set (merge pending review) |
| `step16_mbbdb_value_ranking.md` | download order lists |
| `product_completion_table.tsv`, `product_anomaly_summary.tsv`, `strict_primary_weighted_vs_unweighted_summary.tsv` | summary tables |

### Historical stage reports

One run each, kept as records; not updated on later runs:

- Standardization era: `singlebeam_standardization_report.md`,
  `xyz_standardization_report.md`, `mrar_cleaning_report.md`
- L1/L2 design + runs: `step03b_supplementary_checks_report.md`,
  `step04_aggregation_design_audit.md`, `step04a_file_cells_1min_report.md`,
  `step04b_cells_1min_merge_report.md`
- Overlap/quality-policy era: `step05a_source_specific_overlap_bias_report.md`,
  `step05b_cross_branch_overlap_audit_report.md` (+ `_sample`),
  `step06a_quality_policy_calibration_report.md` (+ `_sample`),
  `step06b_cell_quality_flags_report.md` (+ `_sample`),
  `step06b_quality_policy_rule_review.md`, `step06b_semantic_lock_report.md`
- Step 07 sample run: `step07b_validation_cells_report_sample.md`
- Step 08 intermediate runs: `strict_primary_global_validation_report{,_full_strict_primary}.md`,
  `expanded_primary_global_validation_report{,_full_expanded_primary}.md`,
  `strict_primary_full_validation_audit_report.md`,
  `stage4_expanded_primary_validation_audit_report.md`,
  `step08_preflight_report_{full_strict_primary,full_expanded_primary,smoke}.md`,
  `step08_smoke_validation_report_smoke.md`,
  `step08_non_primary_diagnostics_report_stage5_non_primary.md`
- Six-region prototype chain: `step09_sb_track_bias_report.md`,
  `step09_true_crossover_audit_report.md`, `step10_sb_network_bias_report.md`,
  `step10_sb_track_quality_report.md`
- Round-2 decision chain: `step10_screening_methods_survey.md`,
  `step11_archive_gap_report.md`, `step12_channel_inventory.md`,
  `step13_mbbdb_crosswalk.md`, `step14_next_step_decision_memo.md`,
  `step17_tier_a_processing.md` (in-progress skeleton, tier-A loop)

### External literature

- `On the accuracy evaluation and correction of global single-beam depths.pdf`
