# NCEI Step 05A — Source-specific Overlap Bias Report

Generated: 2026-05-21T14:47:26.102733+00:00
Run label: `full`
Analysis version: `ncei_overlap_v0.1.0`
Elapsed: 3412.1s

> Residual definition: `residual_m = track_cell_median_depth_m - branch_cell_median_depth_m`.
> Only cells with `n_track_cells >= 2` enter this analysis; single-track cells have residual 0 by construction and are excluded.
> This is source-specific only: no branch is merged with another branch, no validation tiers are defined, and no external grid product is read.

## 1. Per-branch headline numbers

| branch | n_branch_cells_total | n_overlap_cells | overlap_share | n_overlap_track_cell_rows | residual_p05 | residual_p50 | residual_p95 | abs_residual_p50 | abs_residual_p95 | rmse_residual_m_branch |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| multibeam_ncei | 5960 | 362 | 0.0607 | 731 | -59.7200 | 0.0000 | 60.3225 | 8.2700 | 107.1400 | 55.1220 |
| regional_mrar | 9019383 | 129 | 0.0000 | 258 | -27.2250 | 0.0000 | 27.2250 | 8.0000 | 46.5000 | 91.9131 |
| singlebeam | 14611054 | 2098336 | 0.1436 | 4782131 | -99.0000 | 0.0000 | 96.6500 | 10.5000 | 187.0000 | 212.2392 |

## 2. Residual distribution by source_type per branch

| breakdown_type | branch | group_value | n_track_cells | n_overlap_rows | residual_p50 | abs_residual_p50 | abs_residual_p95 | abs_residual_p99 | rmse |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| source_type | singlebeam | ncei_nc | 2003471 | 2003471 | 0.0000 | 10.0000 | 174.7500 | 736.2500 | 220.8085 |
| source_type | singlebeam | ncei_xyz | 2778660 | 2778660 | 0.0000 | 10.6500 | 196.8000 | 820.0000 | 205.8392 |
| source_type | multibeam_ncei | ncei_xyz | 731 | 731 | 0.0000 | 8.2700 | 107.1400 | 202.3675 | 55.1220 |
| source_type | regional_mrar | mrar_zhoushuai | 258 | 258 | 0.0000 | 8.0000 | 46.5000 | 555.7500 | 91.9131 |

## 3. Residual distribution by manual_review_flag per branch

| branch | manual_review_flag | n_track_cells | n_overlap_rows | residual_p50 | abs_residual_p50 | abs_residual_p95 | abs_residual_p99 | rmse |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| singlebeam | False | 4701327 | 4701327 | 0.0000 | 10.5000 | 188.0000 | 789.8000 | 212.7123 |
| singlebeam | True | 80804 | 80804 | -0.5500 | 7.2000 | 144.4962 | 597.7328 | 182.6118 |
| multibeam_ncei | False | 731 | 731 | 0.0000 | 8.2700 | 107.1400 | 202.3675 | 55.1220 |
| multibeam_ncei | True | 0 | 0 |  |  |  |  |  |
| regional_mrar | False | 258 | 258 | 0.0000 | 8.0000 | 46.5000 | 555.7500 | 91.9131 |
| regional_mrar | True | 0 | 0 |  |  |  |  |  |

## 4. Residual distribution by duplicate_ratio_cell bins per branch

| breakdown_type | branch | group_value | n_track_cells | n_overlap_rows | residual_p50 | abs_residual_p50 | abs_residual_p95 | abs_residual_p99 | rmse |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| duplicate_ratio_cell_bin | singlebeam | [0,0.01) | 4747061 | 4747061 | 0.0000 | 10.4250 | 186.5000 | 781.0000 | 211.4033 |
| duplicate_ratio_cell_bin | singlebeam | [0.01,0.1) | 15530 | 15530 | 0.0000 | 12.4500 | 285.2750 | 1711.1700 | 329.5542 |
| duplicate_ratio_cell_bin | singlebeam | [0.1,0.5) | 18840 | 18840 | 0.0000 | 20.5500 | 390.0000 | 1347.2500 | 288.4418 |
| duplicate_ratio_cell_bin | singlebeam | [0.5,1.0] | 700 | 700 | 0.0000 | 2.3000 | 134.0000 | 399.6500 | 97.2980 |
| duplicate_ratio_cell_bin | multibeam_ncei | [0,0.01) | 678 | 678 | 0.0000 | 8.0750 | 91.1488 | 191.7000 | 43.1571 |
| duplicate_ratio_cell_bin | multibeam_ncei | [0.01,0.1) | 24 | 24 | -0.0000 | 8.2688 | 198.5271 | 202.3675 | 89.5695 |
| duplicate_ratio_cell_bin | multibeam_ncei | [0.1,0.5) | 20 | 20 | 0.0000 | 30.9862 | 170.5000 | 170.5000 | 85.8886 |
| duplicate_ratio_cell_bin | multibeam_ncei | [0.5,1.0] | 9 | 9 | 0.0000 | 12.9000 | 561.6200 | 593.5240 | 262.0885 |
| duplicate_ratio_cell_bin | regional_mrar | [0,0.01) | 258 | 258 | 0.0000 | 8.0000 | 46.5000 | 555.7500 | 91.9131 |
| duplicate_ratio_cell_bin | regional_mrar | [0.01,0.1) | 0 | 0 |  |  |  |  |  |
| duplicate_ratio_cell_bin | regional_mrar | [0.1,0.5) | 0 | 0 |  |  |  |  |  |
| duplicate_ratio_cell_bin | regional_mrar | [0.5,1.0] | 0 | 0 |  |  |  |  |  |

## 5. Top-20 tracks by p95_abs_residual_m per branch

### singlebeam

| branch | track_id | source_type | source_completeness | manual_review_flag | n_overlap_cells | median_residual_m | p95_abs_residual_m | max_abs_residual_m | duplicate_ratio_summary |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| singlebeam | gh7801 | ncei_nc | nc_xyz_intersect | False | 49 | 6679.0000 | 8512.0000 | 8646.7000 | 0.0000 |
| singlebeam | erdc07wt | ncei_xyz | xyz_only | False | 476 | -103.8375 | 7636.1500 | 8360.4000 | 0.0009 |
| singlebeam | gh7901 | ncei_nc | nc_xyz_intersect | False | 2421 | 4.0000 | 5845.5000 | 8844.0000 | 0.0000 |
| singlebeam | at32 | ncei_xyz | xyz_only | False | 159 | -2228.8700 | 4510.8400 | 4860.6400 | 0.0000 |
| singlebeam | mmw02 | ncei_xyz | xyz_only | False | 578 | 2307.2500 | 4475.1500 | 6791.1000 | 0.0000 |
| singlebeam | jr323 | ncei_xyz | xyz_only | False | 428 | 74.4750 | 4274.0125 | 4333.6000 | 0.0000 |
| singlebeam | jr320 | ncei_xyz | xyz_only | False | 663 | -12.0750 | 4255.5500 | 4674.6000 | 0.0000 |
| singlebeam | l182nc | ncei_xyz | xyz_only | False | 168 | 49.0000 | 4234.9650 | 6590.1000 | 0.0000 |
| singlebeam | ht8403 | ncei_nc | nc_xyz_intersect | False | 1474 | 0.0000 | 4228.3250 | 9194.0000 | 0.0006 |
| singlebeam | l484sp | ncei_nc | nc_xyz_intersect | False | 376 | 1719.1875 | 4126.5500 | 4370.7000 | 0.1005 |
| singlebeam | ztes4bar | ncei_xyz | xyz_only | False | 483 | -1.7000 | 4019.0925 | 8258.2000 | 0.0000 |
| singlebeam | rama07wt | ncei_xyz | xyz_only | False | 717 | 2.8500 | 3860.0750 | 4378.6000 | 0.0000 |
| singlebeam | dsd44agc | ncei_xyz | xyz_only | False | 337 | -4.5000 | 3830.9800 | 7629.5000 | 0.0069 |
| singlebeam | pptu08wt | ncei_xyz | xyz_only | False | 1030 | 5.0750 | 3753.3000 | 4161.2500 | 0.0000 |
| singlebeam | ra188-16 | ncei_xyz | xyz_only | False | 1536 | -44.3500 | 3398.5150 | 6056.3500 | 0.0240 |
| singlebeam | tbd375 | ncei_xyz | xyz_only | False | 756 | -865.6250 | 3227.1250 | 4347.5000 | 0.0000 |
| singlebeam | nbp95-6 | ncei_xyz | xyz_only | False | 554 | -44.6500 | 3183.8500 | 3782.0000 | 0.0205 |
| singlebeam | rc2607 | ncei_nc | nc_xyz_intersect | False | 3176 | -2629.5000 | 3062.3375 | 3525.0750 | 0.0000 |
| singlebeam | tt-208 | ncei_xyz | xyz_only | False | 435 | 316.9500 | 3061.4500 | 4697.4000 | 0.0000 |
| singlebeam | odp120jr | ncei_xyz | xyz_only | False | 269 | 0.0000 | 2936.6000 | 3141.0000 | 0.0000 |

### multibeam_ncei

| branch | track_id | source_type | source_completeness | manual_review_flag | n_overlap_cells | median_residual_m | p95_abs_residual_m | max_abs_residual_m | duplicate_ratio_summary |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| multibeam_ncei | sentry423 | ncei_xyz | xyz_only | False | 5 | 162.4500 | 439.7800 | 501.8000 | 0.3279 |
| multibeam_ncei | sentry420 | ncei_xyz | xyz_only | False | 9 | 60.3000 | 430.7400 | 601.5000 | 0.1940 |
| multibeam_ncei | sentry418 | ncei_xyz | xyz_only | False | 5 | -13.9000 | 393.7300 | 456.9000 | 0.2410 |
| multibeam_ncei | sentry428 | ncei_xyz | xyz_only | False | 6 | -1.4000 | 275.7750 | 299.9500 | 0.1608 |
| multibeam_ncei | sentry424 | ncei_xyz | xyz_only | False | 6 | 1.4000 | 275.7750 | 299.9500 | 0.1171 |
| multibeam_ncei | sentry422 | ncei_xyz | xyz_only | False | 6 | -19.7250 | 184.3875 | 191.7000 | 0.1734 |
| multibeam_ncei | sentry421 | ncei_xyz | xyz_only | False | 4 | -27.8500 | 181.0000 | 202.3000 | 0.2032 |
| multibeam_ncei | sentry419 | ncei_xyz | xyz_only | False | 8 | -6.7750 | 173.1650 | 174.6000 | 0.1736 |
| multibeam_ncei | int_9125 | ncei_xyz | xyz_only | False | 341 | -3.8150 | 85.5250 | 202.3675 | 0.0220 |
| multibeam_ncei | ra022-3 | ncei_xyz | xyz_only | False | 341 | 3.8150 | 85.5250 | 202.3675 | 0.0000 |

### regional_mrar

| branch | track_id | source_type | source_completeness | manual_review_flag | n_overlap_cells | median_residual_m | p95_abs_residual_m | max_abs_residual_m | duplicate_ratio_summary |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| regional_mrar | mrar_0-90W-0-85S.txt | mrar_zhoushuai | mrar_regional | False | 129 | 0.2500 | 46.1000 | 858.5000 | 0.0000 |
| regional_mrar | mrar_90-180W-0-85S.txt | mrar_zhoushuai | mrar_regional | False | 129 | -0.2500 | 46.1000 | 858.5000 | 0.0000 |

## 6. AUV Sentry deep-dive (multibeam_ncei)

Cells considered: `multibeam_ncei` residual rows whose branch cell has `duplicate_ratio_cell > 0.5`.

| group | n_track_cells | n_overlap_rows | residual_p50 | abs_residual_p50 | abs_residual_p95 | abs_residual_p99 | rmse |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all_high_duplicate_multibeam_ncei_rows | 9 | 9 | 0.0000 | 12.9000 | 561.6200 | 593.5240 | 262.0885 |
| sentry_only_high_duplicate_rows | 9 | 9 | 0.0000 | 12.9000 | 561.6200 | 593.5240 | 262.0885 |

Sentry tracks contributing high-duplicate residual rows:

| track_id | n_overlap_rows | n_overlap_cells | residual_p50 | abs_residual_p95 | max_abs_residual_m | rmse |
| --- | --- | --- | --- | --- | --- | --- |
| sentry420 | 2 | 2 | 295.7750 | 571.9225 | 601.5000 | 425.3829 |
| sentry423 | 1 | 1 | 501.8000 | 501.8000 | 501.8000 | 501.8000 |
| sentry419 | 1 | 1 | -55.6000 | 55.6000 | 55.6000 | 55.6000 |
| sentry422 | 1 | 1 | -31.4000 | 31.4000 | 31.4000 | 31.4000 |
| sentry424 | 1 | 1 | -12.9000 | 12.9000 | 12.9000 | 12.9000 |
| sentry428 | 1 | 1 | 12.9000 | 12.9000 | 12.9000 | 12.9000 |
| sentry421 | 1 | 1 | 9.9500 | 9.9500 | 9.9500 | 9.9500 |
| sentry418 | 1 | 1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

## 7. Guardrails and cross-links

- Step 04A audit/report: `ncei/docs/step04a_file_cells_1min_report.md`.
- Step 04B report: `ncei/docs/step04b_cells_1min_merge_report.md`.
- Spec §13 (Step 04A conventions): `.trellis/spec/backend/pipeline-design-decisions.md#13-ncei-step-04a--per-file-1-arcmin-cell-aggregation`.
- Spec §14 (Step 04B conventions): `.trellis/spec/backend/pipeline-design-decisions.md#14-ncei-step-04b--source-specific-global-1-arcmin-cell-merge`.
- Confirmed by this run: residual rows are branch-matched on both sides of the join; no single-track cells entered residual analysis; spot-check equality of the residual formula passed.

## 8. Output paths

| kind | path |
| --- | --- |
| per-track-cell residuals | ncei/derived/overlap_bias_1min/source_specific_overlap_residuals.parquet |
| track bias summary | ncei/derived/overlap_bias_1min/track_bias_summary.parquet |
| branch overlap summary | ncei/derived/overlap_bias_1min/branch_overlap_summary.parquet |
| branch breakdowns TSV | ncei/derived/overlap_bias_1min/branch_overlap_breakdowns.tsv |
| manual-review TSV | ncei/derived/overlap_bias_1min/manual_review_overlap_summary.tsv |
| report (this file) | ncei/docs/step05a_source_specific_overlap_bias_report.md |

## 9. Recommendation

Ready to proceed to Step 05B (cross-branch overlap audit) if the headline residual distributions and Top-20 track tables above are acceptable. Step 05A is descriptive only; potential problem tracks listed here should be reviewed or downweighted in later stages, not filtered here.

## 10. Run inputs

| branch | selected_file_cell_parquets |
| --- | --- |
| singlebeam | 5365 |
| multibeam_ncei | 17 |
| regional_mrar | 3 |
