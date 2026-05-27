# Step 08 Final Global Validation Report

Generated: 2026-05-27T18:02:00.335864+00:00
Status: **PASS**
Elapsed: 23.3s
Run label: `stage6_final`

This report consolidates Stage 3 strict-primary validation, Stage 4 expanded-primary sensitivity, and Stage 5 non-primary diagnostics. It does not resample gridded models and does not mutate validation-cell products.

## 1. Final recommendation
Use `strict_primary_multibeam_cells` as the authoritative global validation baseline. `expanded_primary_ship_cells` is useful for coverage sensitivity, but should remain secondary for global ranking. `supplementary_singlebeam_cells` and `regional_mrar_experiment_cells` remain diagnostic/sensitivity products only.

| area | recommendation | basis |
| --- | --- | --- |
| global_baseline | Use strict_primary_multibeam_cells as the authoritative global validation baseline. | Stage 3 passed all safety checks on 2,398,774 multibeam cells with no singlebeam or regional_mrar rows. |
| expanded_primary | Keep expanded_primary_ship_cells as secondary sensitivity / coverage-expansion output, not the global baseline. | Stage 4 adds 333,915 singlebeam gap-fill cells and raises overall RMSE by 6-8 m across all products while preserving ranking. |
| supplementary_singlebeam | Use supplementary_singlebeam_cells for coverage diagnostics only. | Stage 5 role checks passed; 11,399,058 supplementary cells are outside expanded-primary cell IDs and remain non-primary coverage material. |
| regional_mrar | Use regional_mrar_experiment_cells only for explicit regional sensitivity experiments. | Stage 5 role checks passed; 9,015,418 of 9,019,383 cells are review_or_sensitivity_only, and overlap with primary cell IDs is diagnostic only. |
| swot_t1 | Do not claim global SWOT_T1 validation from this task. | Stage 3 skipped SWOT_T1 because it is a regional footprint product; a separate regional-footprint-compatible task is required. |
| quality_policy | Do not use model residuals to filter, relabel, or promote validation cells. | Stages 3 and 4 passed no_model_residual_filtering checks; Stage 5 performed diagnostics without model sampling. |

## 2. Stage outcomes
| stage | product_scope | status | cells | completed_products | safety_pass | safety_fail | skip_summary | policy_role |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 3 | strict_primary_multibeam_cells | PASS | 2,398,774 | 5 | 10 | 0 | SWOT_T1: regional footprint product; not part of full global strict-primary run | authoritative global baseline |
| Stage 4 | expanded_primary_ship_cells | PASS | 2,732,689 | 5 | 11 | 0 | none | secondary sensitivity / coverage expansion |
| Stage 5 | supplementary_singlebeam + regional_mrar_experiment | PASS | 21,297,016 | 2 | 16 | 0 | not applicable; diagnostics only | non-primary diagnostics / regional sensitivity only |

## 3. Strict vs expanded metrics
| product_name | strict_count | strict_bias | strict_MAE | strict_RMSE | strict_weighted_RMSE | strict_abs_error_p95 | expanded_count | expanded_bias | expanded_MAE | expanded_RMSE | expanded_weighted_RMSE | expanded_abs_error_p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEBCO_2024 | 2,398,774 | 7.26 | 21.26 | 90.43 | 68.58 | 68.67 | 2,732,689 | 5.16 | 23.30 | 98.56 | 80.73 | 75.90 |
| ETOPO_2022 | 2,398,774 | 8.16 | 22.57 | 91.61 | 70.06 | 72.65 | 2,732,689 | 5.94 | 24.35 | 99.27 | 81.57 | 78.86 |
| SRTM15_V2.7 | 2,398,774 | 6.72 | 22.15 | 93.73 | 72.55 | 75.95 | 2,732,689 | 4.77 | 24.11 | 101.32 | 83.87 | 82.60 |
| TOPO_25.1 | 2,398,774 | 5.61 | 25.24 | 97.31 | 76.72 | 89.67 | 2,732,689 | 3.54 | 26.95 | 104.32 | 87.13 | 95.06 |
| SDUST_2023 | 2,398,774 | 9.84 | 33.09 | 99.94 | 79.97 | 112.59 | 2,732,689 | 7.45 | 33.55 | 106.10 | 89.23 | 113.50 |

Strict-vs-expanded deltas:

| product_name | strict_count | expanded_count | coverage_gain_count | coverage_gain_fraction_vs_strict | strict_RMSE | expanded_RMSE | delta_RMSE_expanded_minus_strict | strict_weighted_RMSE | expanded_weighted_RMSE | delta_weighted_RMSE_expanded_minus_strict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEBCO_2024 | 2,398,774 | 2,732,689 | 333,915 | 0.1392 | 90.4265 | 98.5613 | 8.1348 | 68.5825 | 80.7330 | 12.1506 |
| ETOPO_2022 | 2,398,774 | 2,732,689 | 333,915 | 0.1392 | 91.6099 | 99.2749 | 7.6651 | 70.0648 | 81.5688 | 11.5040 |
| SRTM15_V2.7 | 2,398,774 | 2,732,689 | 333,915 | 0.1392 | 93.7345 | 101.3228 | 7.5883 | 72.5505 | 83.8699 | 11.3194 |
| TOPO_25.1 | 2,398,774 | 2,732,689 | 333,915 | 0.1392 | 97.3126 | 104.3186 | 7.0060 | 76.7194 | 87.1330 | 10.4136 |
| SDUST_2023 | 2,398,774 | 2,732,689 | 333,915 | 0.1392 | 99.9411 | 106.0955 | 6.1544 | 79.9667 | 89.2309 | 9.2643 |

## 4. Expanded-primary gap-fill attribution
| product_name | retained_multibeam_count | singlebeam_gapfill_count | retained_multibeam_RMSE | singlebeam_gapfill_RMSE | gapfill_minus_retained_RMSE | gapfill_to_retained_RMSE_ratio |
| --- | --- | --- | --- | --- | --- | --- |
| GEBCO_2024 | 2,398,774 | 333,915 | 90.43 | 144.08 | 53.65 | 1.59 |
| ETOPO_2022 | 2,398,774 | 333,915 | 91.61 | 142.71 | 51.10 | 1.56 |
| SRTM15_V2.7 | 2,398,774 | 333,915 | 93.73 | 144.57 | 50.83 | 1.54 |
| TOPO_25.1 | 2,398,774 | 333,915 | 97.31 | 145.02 | 47.71 | 1.49 |
| SDUST_2023 | 2,398,774 | 333,915 | 99.94 | 142.71 | 42.77 | 1.43 |

The retained-multibeam subset matches the strict-primary input count. The singlebeam gap-fill subset has higher RMSE for every product, which explains why expanded-primary raises global RMSE while preserving product ranking.
Stage 6 enforces this attribution against the Stage 4 comparison table: retained count must equal strict count, gap-fill count must equal coverage gain, `expanded_fill` must be false for retained strict cells and true for gap-fill cells, and gap-fill cells must be `ncei_singlebeam`.

## 5. Non-primary diagnostics
| product_key | n_rows | n_cell_ids | median_weight | low_evidence_flag_cells | review_or_sensitivity_only_cells | sensitivity_only_cells | cells_with_cross_branch_overlap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| supplementary_singlebeam_cells | 12,277,633 | 12,277,633 | 0.3500 | 8,751,456 | 0 | 0 | 1,876,667 |
| regional_mrar_experiment_cells | 9,019,383 | 9,019,383 | 0.2000 | 7,130,082 | 9,015,418 | 9,015,418 | 1,889,205 |

| product_key | non_primary_cells | strict_primary_overlap_cells | expanded_primary_overlap_cells | outside_expanded_primary_cells | outside_expanded_primary_fraction |
| --- | --- | --- | --- | --- | --- |
| supplementary_singlebeam_cells | 12,277,633 | 544,660 | 878,575 | 11,399,058 | 0.9284 |
| regional_mrar_experiment_cells | 9,019,383 | 504,968 | 574,347 | 8,445,036 | 0.9363 |

| product_label | catalog_rows | unique_cell_ids | final_primary_source_values | duplicate_product_cell_rows |
| --- | --- | --- | --- | --- |
| regional_mrar_experiment | 9,019,383 | 9,019,383 |  | 0 |
| strict_primary_multibeam | 2,398,774 | 2,398,774 | jamstec,ncei_multibeam | 0 |
| supplementary_singlebeam | 12,611,548 | 12,277,633 | ,jamstec,ncei_multibeam,ncei_singlebeam | 333,915 |

Catalog note: `supplementary_singlebeam` has more catalog rows than unique cell IDs because Step 07B intentionally adds expanded-primary singlebeam membership rows for the 333,915 gap-fill cells.

## 6. Skipped / out-of-scope products
- `SWOT_T1` was skipped in Stage 3 because it is a regional footprint product, not a full-global product.
- Stage 4 did not request `SWOT_T1`; no expanded-primary product was skipped.
- A separate regional validation task is required before making any SWOT_T1 regional claim.

## 7. Reproducibility
| key | value |
| --- | --- |
| generated_utc | 2026-05-27T18:02:00.338359+00:00 |
| python | 3.12.10 \| packaged by conda-forge \| (main, Apr 10 2025, 22:21:13) [GCC 13.3.0] |
| platform | Linux-6.8.0-63-generic-x86_64-with-glibc2.39 |
| pandas | 2.3.3 |
| pyarrow | 24.0.0 |
| repo_root | /mnt/data2/00-Data/ship |
| run_label | stage6_final |
| confirm_final | True |
| overwrite | True |
| model_sampling | none; report reads existing Stage 3/4/5 artifacts |
| random_seed | none |

| kind | path |
| --- | --- |
| strict_summary | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_full_strict_primary/full_validation_metrics_summary_strict_primary.parquet |
| expanded_summary | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_full_expanded_primary/full_validation_metrics_summary_expanded_primary.parquet |
| strict_vs_expanded | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_full_expanded_primary/strict_vs_expanded_comparison.parquet |
| stage5_product_summary | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_stage5_non_primary/non_primary_product_summary.parquet |
| stage5_overlap_summary | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_stage5_non_primary/non_primary_overlap_summary.parquet |
| strict_primary_cells | /mnt/data2/00-Data/ship/ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet |

| kind | path |
| --- | --- |
| stage_outcomes | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_stage6_final/step08_stage_outcomes.parquet |
| policy_recommendations | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_stage6_final/step08_final_policy_recommendations.parquet |
| gapfill_sensitivity | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_stage6_final/expanded_gapfill_sensitivity_summary.parquet |
| report | /mnt/data2/00-Data/ship/ncei/docs/step08_final_global_validation_report.md |

## 8. Closure
Step 08 full-global validation is ready for task closure after review. No residual-based filtering, quality relabeling, or primary-product promotion is recommended.
