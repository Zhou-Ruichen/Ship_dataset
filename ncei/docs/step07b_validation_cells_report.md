# NCEI Step 07B — Validation Cells Report

Generated: 2026-05-21T21:13:40.056720+00:00
Run label: `full`
Validation product version: `ncei_validation_cells_v0.1.0`
Elapsed: 485.8s

This report is generated at runtime by `ncei/code/13_build_validation_cells.py`. The stage builds validation products only; it does not mutate Step 04B cells, Step 06B quality flags, or JAMSTEC inputs.

## 1. Per-product row count summary

| product | n_rows | n_cell_ids | min_weight | max_weight | n_auv_sentry |
| --- | --- | --- | --- | --- | --- |
| strict_primary_multibeam_cells | 2398774 | 2398774 | 0.4000 | 1.0000 | 8 |
| expanded_primary_ship_cells | 2732689 | 2732689 | 0.4000 | 1.0000 | 8 |
| supplementary_singlebeam_cells | 12277633 | 12277633 | 0.2500 | 0.9000 | 0 |
| regional_mrar_experiment_cells | 9019383 | 9019383 | 0.1000 | 0.6000 | 0 |
| validation_cell_catalog | 24029705 | 20907702 | 0.1000 | 1.0000 | 8 |

## 2. Tier distribution + source provider mix

### strict_primary_multibeam_cells

| source_provider | quality_tier | n_rows |
| --- | --- | --- |
| jamstec | high_confidence | 696989 |
| jamstec | low_confidence | 334948 |
| jamstec | medium_confidence | 1362178 |
| ncei_multibeam | high_confidence | 293 |
| ncei_multibeam | medium_confidence | 4366 |

### expanded_primary_ship_cells

| source_provider | quality_tier | n_rows |
| --- | --- | --- |
| jamstec | high_confidence | 696989 |
| jamstec | low_confidence | 334948 |
| jamstec | medium_confidence | 1362178 |
| ncei_multibeam | high_confidence | 293 |
| ncei_multibeam | medium_confidence | 4366 |
| ncei_singlebeam | high_confidence | 98705 |
| ncei_singlebeam | medium_confidence | 235210 |

### supplementary_singlebeam_cells

| source_provider | quality_tier | n_rows |
| --- | --- | --- |
| ncei_singlebeam | high_confidence | 100323 |
| ncei_singlebeam | low_confidence | 11932596 |
| ncei_singlebeam | medium_confidence | 244714 |

### regional_mrar_experiment_cells

| source_provider | quality_tier | n_rows |
| --- | --- | --- |
| mrar | low_confidence | 3876 |
| mrar | medium_confidence | 89 |
| mrar | review_or_sensitivity_only | 9015418 |

### validation_cell_catalog

| source_provider | quality_tier | n_rows |
| --- | --- | --- |
| jamstec | high_confidence | 696989 |
| jamstec | low_confidence | 334948 |
| jamstec | medium_confidence | 1362178 |
| mrar | low_confidence | 3876 |
| mrar | medium_confidence | 89 |
| mrar | review_or_sensitivity_only | 9015418 |
| ncei_multibeam | high_confidence | 293 |
| ncei_multibeam | medium_confidence | 4366 |
| ncei_singlebeam | high_confidence | 199028 |
| ncei_singlebeam | low_confidence | 11932596 |
| ncei_singlebeam | medium_confidence | 479924 |

## 3. Conflict resolution outcome

| source_provider | precedence_resolution | expanded_fill | n_rows |
| --- | --- | --- | --- |
| jamstec |  | False | 2383509 |
| jamstec | jamstec_over_sb | False | 10606 |
| ncei_multibeam |  | False | 4143 |
| ncei_multibeam | ncei_mb_over_sb | False | 516 |
| ncei_singlebeam |  | True | 333915 |

## 4. Runtime assertions

- PASS: JAMSTEC × NCEI mb disjointness verified (0 overlaps)
- PASS: regional_mrar never appears in strict or expanded primary products
- PASS: strict_primary count=2,398,774 within expected 2,398,774 ± 12,000
- PASS: expanded_primary count=2,732,689 within expected 2,732,689 ± 14,000
- PASS: supplementary_singlebeam count=12,277,633 within expected 12,277,633 ± 61,000
- PASS: regional_mrar_experiment count=9,019,383 within expected 9,019,383 ± 0
- PASS: validation_cell_catalog count=24,029,705 within expected 24,029,705 ± 120,000
- PASS: AUV Sentry preserved in strict primary (n=8)
- PASS: weights not rescaled (JAMSTEC max=1.0, NCEI mb max=0.95)
- PASS: expanded_primary has unique cell_id rows after precedence resolution

## 5. AUV Sentry retention summary

| product | n_auv_sentry |
| --- | --- |
| strict_primary_multibeam_cells | 8 |
| expanded_primary_ship_cells | 8 |
| supplementary_singlebeam_cells | 0 |
| regional_mrar_experiment_cells | 0 |
| validation_cell_catalog | 8 |

## 6. Weight-scale comparison

| product | source_provider | n_rows | min_weight | median_weight | max_weight | unique_weights_sample |
| --- | --- | --- | --- | --- | --- | --- |
| strict_primary_multibeam_cells | jamstec | 2394115 | 0.4000 | 0.7000 | 1.0000 | 0.4,0.7,1.0 |
| strict_primary_multibeam_cells | ncei_multibeam | 4659 | 0.5500 | 0.7500 | 0.9500 | 0.55,0.7,0.75,0.9,0.95 |
| expanded_primary_ship_cells | jamstec | 2394115 | 0.4000 | 0.7000 | 1.0000 | 0.4,0.7,1.0 |
| expanded_primary_ship_cells | ncei_multibeam | 4659 | 0.5500 | 0.7500 | 0.9500 | 0.55,0.7,0.75,0.9,0.95 |
| expanded_primary_ship_cells | ncei_singlebeam | 333915 | 0.6500 | 0.6500 | 0.9000 | 0.65,0.7,0.85,0.9 |
| supplementary_singlebeam_cells | ncei_singlebeam | 12277633 | 0.2500 | 0.3500 | 0.9000 | 0.25,0.3,0.35,0.65,0.7,0.85,0.9 |
| regional_mrar_experiment_cells | mrar | 9019383 | 0.1000 | 0.2000 | 0.6000 | 0.1,0.2,0.3,0.6 |
| validation_cell_catalog | jamstec | 2394115 | 0.4000 | 0.7000 | 1.0000 | 0.4,0.7,1.0 |
| validation_cell_catalog | mrar | 9019383 | 0.1000 | 0.2000 | 0.6000 | 0.1,0.2,0.3,0.6 |
| validation_cell_catalog | ncei_multibeam | 4659 | 0.5500 | 0.7500 | 0.9500 | 0.55,0.7,0.75,0.9,0.95 |
| validation_cell_catalog | ncei_singlebeam | 12611548 | 0.2500 | 0.3500 | 0.9000 | 0.25,0.3,0.35,0.65,0.7,0.85,0.9 |

Weights are preserved verbatim: NCEI Step 06B weights remain on the [0.1, 0.95] policy scale and JAMSTEC legacy A/B/C weights remain {0.4, 0.7, 1.0}. They are intentionally NOT rescaled.

## 7. Cross-links

- Spec: `.trellis/spec/backend/pipeline-design-decisions.md` §13–§18.
- Step 07A preflight: `ncei/docs/step07a_validation_cell_preflight_report.md`.
- Step 06B report: `ncei/docs/step06b_cell_quality_flags_report.md`.
- Step 05B audit: `ncei/docs/step05b_cross_branch_overlap_audit_report.md`.

## 8. Step 11 GEBCO/ETOPO/SRTM15/SWOT recommendation

Use `expanded_primary_ship_cells` as the default one-row-per-cell ship-truth input for Step 11. It applies the locked source precedence (JAMSTEC mb > NCEI mb > NCEI singlebeam fill) while keeping source provenance and original weights. Use `strict_primary_multibeam_cells` for a multibeam-only baseline, `supplementary_singlebeam_cells` for coverage sensitivity, `regional_mrar_experiment_cells` only for regional experiments, and `validation_cell_catalog` for audit / sensitivity analyses of precedence-loser rows and product memberships.

## 9. Output paths

| kind | path |
| --- | --- |
| strict_primary | ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet |
| expanded_primary | ncei/derived/validation_cells_1min/expanded_primary_ship_cells.parquet |
| supplementary_singlebeam | ncei/derived/validation_cells_1min/supplementary_singlebeam_cells.parquet |
| regional_mrar_experiment | ncei/derived/validation_cells_1min/regional_mrar_experiment_cells.parquet |
| validation_cell_catalog | ncei/derived/validation_cells_1min/validation_cell_catalog.parquet |
| report | ncei/docs/step07b_validation_cells_report.md |
