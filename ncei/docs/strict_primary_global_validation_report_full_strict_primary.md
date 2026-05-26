# Step 08 Strict-Primary Full Global Validation Report

Generated: 2026-05-26T18:52:45.149057+00:00
Elapsed: 2164.1s
Preflight status: **PASS**
Full strict-primary status: **PASS**
Output directory: `/mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_full_strict_primary`

## 1. Input baseline

| product | product_role | rows | path |
| --- | --- | --- | --- |
| strict_primary_multibeam_cells | strict_primary_multibeam | 2,398,774 | /mnt/data2/00-Data/ship/ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet |

## 2. Safety checks

| check | status | details |
| --- | --- | --- |
| input_row_count | PASS | rows=2,398,774; expected=2,398,774 |
| no_singlebeam_in_strict_primary | PASS | ncei_singlebeam rows=0 |
| no_regional_mrar_in_strict_primary | PASS | regional_mrar rows=0 |
| validation_weight_preserved | PASS | null weights=0 |
| quality_tier_preserved | PASS | null quality_tier=0 |
| evidence_class_preserved | PASS | null evidence_class=0 |
| matched_rule_id_preserved | PASS | null matched_rule_id=0 |
| sign_error_suspected_false | PASS | none |
| model_errors_do_not_corrupt_other_outputs | PASS | error products=0 |
| no_model_residual_filtering | PASS | all strict-primary rows are retained before model nodata masking in metrics |

## 3. Product status

| product_name | status | reason | rows | valid_count | nodata_count | configured_sampling_method | resolved_sampling_method | elapsed_s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEBCO_2024 | ok |  | 2,398,774 | 2398774.00 | 0.00 | cell_median | cell_median | 1042.30 |
| ETOPO_2022 | ok |  | 2,398,774 | 2398774.00 | 0.00 | center_bilinear | center_bilinear | 54.10 |
| SRTM15_V2.7 | ok |  | 2,398,774 | 2398774.00 | 0.00 | cell_median | cell_median | 961.90 |
| SDUST_2023 | ok |  | 2,398,774 | 2398774.00 | 0.00 | cell_median | cell_median | 51.50 |
| TOPO_25.1 | ok |  | 2,398,774 | 2398774.00 | 0.00 | cell_median | cell_median | 52.80 |
| SWOT_T1 | skipped | regional footprint product; not part of full global strict-primary run | 0 | N/A | N/A | N/A | N/A | 0.00 |

## 4. Overall metrics

| product_name | product_role | sampling_method | requested_cells | count | nodata_count | coverage_fraction | bias | MAE | RMSE | weighted_MAE | weighted_RMSE | median_error | MAD | abs_error_p90 | abs_error_p95 | abs_error_p99 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEBCO_2024 | strict_primary_multibeam | cell_median | 2,398,774 | 2,398,774 | 0 | 1.00 | 7.26 | 21.26 | 90.43 | 17.61 | 68.58 | 0.30 | 6.80 | 42.40 | 68.67 | 202.75 |
| ETOPO_2022 | strict_primary_multibeam | center_bilinear | 2,398,774 | 2,398,774 | 0 | 1.00 | 8.16 | 22.57 | 91.61 | 18.83 | 70.06 | 0.51 | 7.54 | 44.98 | 72.65 | 218.73 |
| SRTM15_V2.7 | strict_primary_multibeam | cell_median | 2,398,774 | 2,398,774 | 0 | 1.00 | 6.72 | 22.15 | 93.73 | 18.23 | 72.55 | 0.07 | 6.18 | 44.05 | 75.95 | 242.96 |
| SDUST_2023 | strict_primary_multibeam | cell_median | 2,398,774 | 2,398,774 | 0 | 1.00 | 9.84 | 33.09 | 99.94 | 29.12 | 79.97 | 2.52 | 13.64 | 70.43 | 112.59 | 295.53 |
| TOPO_25.1 | strict_primary_multibeam | cell_median | 2,398,774 | 2,398,774 | 0 | 1.00 | 5.61 | 25.24 | 97.31 | 21.21 | 76.72 | -1.39 | 6.91 | 51.58 | 89.67 | 284.17 |

## 5. Product convention diagnostics

| product_name | sampling_method | z_convention | lon_convention | fill_value | n_cells_requested | valid_count | nodata_count | raw_z_min | raw_z_max | model_depth_min | model_depth_max | elevation_correlation | sign_error_suspected |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEBCO_2024 | cell_median | elevation_negative_ocean | -180_180 | N/A | 2,398,774 | 2,398,774 | 0 | -10902.00 | 314.50 | -314.50 | 10902.00 | 1.00 | 0 |
| ETOPO_2022 | center_bilinear | elevation_negative_ocean | -180_180 | -99999.00 | 2,398,774 | 2,398,774 | 0 | -10540.92 | 318.14 | -318.14 | 10540.92 | 1.00 | 0 |
| SRTM15_V2.7 | cell_median | elevation_negative_ocean | -180_180 | N/A | 2,398,774 | 2,398,774 | 0 | -10624.50 | 314.50 | -314.50 | 10624.50 | 1.00 | 0 |
| SDUST_2023 | cell_median | elevation_negative_ocean | 0_360 | N/A | 2,398,774 | 2,398,774 | 0 | -10745.97 | 318.32 | -318.32 | 10745.97 | 1.00 | 0 |
| TOPO_25.1 | cell_median | elevation_negative_ocean | -180_180 | N/A | 2,398,774 | 2,398,774 | 0 | -10677.46 | 316.92 | -316.92 | 10677.46 | 1.00 | 0 |

## 6. Recommendation

Proceed to expanded_primary sensitivity validation if the objective is to quantify high-confidence singlebeam gap-fill coverage and metric sensitivity. Keep strict_primary as the main global baseline.
