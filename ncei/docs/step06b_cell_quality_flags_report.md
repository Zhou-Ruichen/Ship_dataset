# NCEI Step 06B — Cell Quality Flags Report

Generated: 2026-05-21T19:41:02.416968+00:00
Run label: `full`
Policy enforce version: `ncei_policy_enforce_v0.1.0`
Elapsed: 485.1s

This report is generated at runtime by `ncei/code/12_apply_quality_policy.py`. The script writes a sidecar quality manifest and does not mutate Step 04B cells.

## 1. Row counts

| branch | n_rows |
| --- | --- |
| multibeam_ncei | 5960 |
| regional_mrar | 9019383 |
| singlebeam | 14611054 |

## 2. Rule match distribution

| matched_rule_priority | matched_rule_id | quality_tier | exclude_from_primary | n_cells | mean_weight | n_auv_sentry |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | mb_v0_high_overlap_lowdup | high_confidence | False | 292 | 0.9500 | 0 |
| 2 | sb_v0_lowlat_shallow_overlap_high | high_confidence | False | 79760 | 0.8500 | 0 |
| 3 | sb_v0_lowlat_deep_overlap_medium | medium_confidence | False | 243921 | 0.6500 | 0 |
| 4 | mrar_v0_crossvalidated_medium | medium_confidence | True | 89 | 0.6000 | 0 |
| 5 | mrar_v0_shallow_highrisk | review_or_sensitivity_only | True | 39280 | 0.1000 | 0 |
| 6 | sb_v0_southern_ocean_review | review_or_sensitivity_only | False | 1725485 | 0.2500 | 0 |
| 7 | sb_v0_highlat_north_review | review_or_sensitivity_only | False | 607936 | 0.3000 | 0 |
| 8 | mb_v0_singletrack_lowdup | medium_confidence | False | 4314 | 0.7500 | 0 |
| 9 | mb_v0_highdup_sentry_downweight | medium_confidence | False | 8 | 0.5500 | 8 |
| 10 | sb_v0_no_overlap_low | low_confidence | False | 8751456 | 0.3500 | 0 |
| 11 | mrar_v0_default_sensitivity | review_or_sensitivity_only | True | 8976138 | 0.2000 | 0 |
| 12 | any_v0_overlap_both_high | high_confidence | False | 20564 | 0.9000 | 0 |
| 13 | any_v0_strong_unique_medium | medium_confidence | False | 837 | 0.7000 | 0 |
| 14 | any_v0_low_unique_low | low_confidence | False | 2889631 | 0.3000 | 0 |
| 15 | any_v0_dup_heavy_downweight | low_confidence | False | 33 | 0.3500 | 0 |
| 99 | default_unmatched | low_confidence | False | 296653 | 0.2500 | 0 |

## 3. Per-branch tier/use distribution

| branch | quality_tier | branch_role | use_for_primary_validation | use_for_supplementary_validation | use_for_regional_experiment | n_cells | mean_weight | n_auv_sentry | n_low_evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| multibeam_ncei | high_confidence | multibeam_supplement | True | True | False | 293 | 0.9498 | 0 | 0 |
| multibeam_ncei | low_confidence | multibeam_supplement | False | True | False | 1301 | 0.2558 | 0 | 233 |
| multibeam_ncei | medium_confidence | multibeam_supplement | True | True | False | 4366 | 0.7491 | 8 | 938 |
| regional_mrar | low_confidence | regional_experiment | False | True | True | 3876 | 0.3000 | 0 | 0 |
| regional_mrar | medium_confidence | regional_experiment | False | False | True | 89 | 0.6000 | 0 | 0 |
| regional_mrar | review_or_sensitivity_only | regional_experiment | False | False | True | 9015418 | 0.1996 | 0 | 7130082 |
| singlebeam | high_confidence | supplementary_coverage | True | True | False | 100323 | 0.8602 | 0 | 0 |
| singlebeam | low_confidence | supplementary_coverage | False | True | False | 11932596 | 0.3354 | 0 | 8751456 |
| singlebeam | medium_confidence | supplementary_coverage | True | True | False | 244714 | 0.6502 | 0 | 0 |
| singlebeam | review_or_sensitivity_only | supplementary_coverage | False | False | False | 2333421 | 0.2630 | 0 | 2162463 |

## 4. Evidence-class distribution

| branch | evidence_class | quality_tier | n_cells | mean_weight |
| --- | --- | --- | --- | --- |
| multibeam_ncei | both | high_confidence | 293 | 0.9498 |
| multibeam_ncei | both | low_confidence | 22 | 0.2523 |
| multibeam_ncei | both | medium_confidence | 47 | 0.6904 |
| multibeam_ncei | cross | low_confidence | 1046 | 0.2558 |
| multibeam_ncei | cross | medium_confidence | 3381 | 0.7498 |
| multibeam_ncei | none | low_confidence | 233 | 0.2560 |
| multibeam_ncei | none | medium_confidence | 938 | 0.7496 |
| regional_mrar | both | review_or_sensitivity_only | 33 | 0.2000 |
| regional_mrar | cross | low_confidence | 3876 | 0.3000 |
| regional_mrar | cross | medium_confidence | 89 | 0.6000 |
| regional_mrar | cross | review_or_sensitivity_only | 1885207 | 0.1991 |
| regional_mrar | none | review_or_sensitivity_only | 7130082 | 0.1997 |
| regional_mrar | within | review_or_sensitivity_only | 96 | 0.2000 |
| singlebeam | both | high_confidence | 24038 | 0.8928 |
| singlebeam | both | low_confidence | 216291 | 0.2918 |
| singlebeam | both | medium_confidence | 49140 | 0.6502 |
| singlebeam | both | review_or_sensitivity_only | 1049 | 0.3000 |
| singlebeam | cross | low_confidence | 1586787 | 0.2970 |
| singlebeam | cross | medium_confidence | 411 | 0.7000 |
| singlebeam | cross | review_or_sensitivity_only | 11601 | 0.3000 |
| singlebeam | none | low_confidence | 8751456 | 0.3500 |
| singlebeam | none | review_or_sensitivity_only | 2162463 | 0.2628 |
| singlebeam | within | high_confidence | 76285 | 0.8500 |
| singlebeam | within | low_confidence | 1378062 | 0.2940 |
| singlebeam | within | medium_confidence | 195163 | 0.6501 |
| singlebeam | within | review_or_sensitivity_only | 158308 | 0.2627 |

## 5. Invariant checks

- PASS: no manual_review_any-only first_match rule can exclude or upgrade cells
- PASS: manual_review_not_exclusion is invariant-only and not used for tier assignment
- PASS: no cells have validation_weight == 0
- PASS: regional_mrar exclude_from_primary share = 0.9996 (>=0.99)
- PASS: AUV Sentry rule sidecars correct (matched cells=8)

## 6. Spot checks

| branch | cell_id | rule_id | weight |
| --- | --- | --- | --- |
| singlebeam | 1min_5069_4251 | any_v0_low_unique_low | 0.3000 |
| multibeam_ncei | 1min_3730_7889 | mb_v0_singletrack_lowdup | 0.7500 |
| regional_mrar | 1min_4827_4276 | mrar_v0_default_sensitivity | 0.2000 |

## 7. Output paths

| kind | path |
| --- | --- |
| flags_parquet | ncei/derived/quality_flags_1min/cell_quality_flags_1min.parquet |
| flags_tsv | ncei/derived/quality_flags_1min/cell_quality_flags_1min.tsv |
| summary_branch | ncei/derived/quality_flags_1min/quality_summary_by_branch.parquet |
| summary_lat_depth | ncei/derived/quality_flags_1min/quality_summary_by_lat_depth.parquet |
| summary_rule | ncei/derived/quality_flags_1min/quality_summary_by_rule.parquet |
| summary_evidence | ncei/derived/quality_flags_1min/quality_summary_by_evidence_class.parquet |
| report | ncei/docs/step06b_cell_quality_flags_report.md |

## 8. Cross-links

- Spec: `.trellis/spec/backend/pipeline-design-decisions.md` §13 (data layers) / §14 (branch labels) / §15 (Step 05B cross-branch overlap) / §16 (Step 06 prerequisites) / §17 (Step 06A quality policy calibration).
- Enforced rules TSV: `.trellis/tasks/05-11-singlebeam-integration/research/quality_policy_enforced_rules.tsv` (18 cols × 16 rows; this script's only rule source).
- Semantic lock report: `ncei/docs/step06b_semantic_lock_report.md` (Step 06B implementation contract — §1.2 filter grammar, §1.3 invariant rule, §1.4 AUV Sentry handling).
- Predecessor (Step 06A): `ncei/code/11_quality_policy_calibration_audit.py` + `ncei/derived/quality_policy_calibration_1min/`.
