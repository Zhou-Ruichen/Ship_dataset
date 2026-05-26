# Step 08 Expanded-Primary Full Global Validation Report

Generated: 2026-05-26T21:07:41.547498+00:00
Elapsed: 2491.5s
Preflight status: **PASS**
Full expanded-primary status: **PASS**
Output directory: `/mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_full_expanded_primary`

## 1. Input baseline

| product | product_role | rows | path |
| --- | --- | --- | --- |
| expanded_primary_ship_cells | expanded_primary_ship | 2,732,689 | /mnt/data2/00-Data/ship/ncei/derived/validation_cells_1min/expanded_primary_ship_cells.parquet |

## 2. Safety checks

| check | status | details |
| --- | --- | --- |
| input_row_count | PASS | rows=2,732,689; expected=2,732,689 |
| no_regional_mrar_in_expanded_primary | PASS | regional_mrar rows=0 |
| expanded_fill_count_matches_preflight | PASS | expanded_fill rows=333,915; expected=333,915 |
| singlebeam_only_marked_as_expanded_fill | PASS | ncei_singlebeam rows=333,915; expanded_fill rows=333,915 |
| validation_weight_preserved | PASS | null weights=0 |
| quality_tier_preserved | PASS | null quality_tier=0 |
| evidence_class_preserved | PASS | null evidence_class=0 |
| matched_rule_id_preserved | PASS | null matched_rule_id=0 |
| sign_error_suspected_false | PASS | none |
| model_errors_do_not_corrupt_other_outputs | PASS | error products=0 |
| no_model_residual_filtering | PASS | all expanded_primary rows are retained before model nodata masking in metrics |

## 3. Product status

| product_name | status | reason | rows | valid_count | nodata_count | configured_sampling_method | resolved_sampling_method | elapsed_s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEBCO_2024 | ok |  | 2,732,689 | 2,732,689 | 0 | cell_median | cell_median | 1174.00 |
| ETOPO_2022 | ok |  | 2,732,689 | 2,732,689 | 0 | center_bilinear | center_bilinear | 66.10 |
| SRTM15_V2.7 | ok |  | 2,732,689 | 2,732,689 | 0 | cell_median | cell_median | 1121.80 |
| SDUST_2023 | ok |  | 2,732,689 | 2,732,689 | 0 | cell_median | cell_median | 63.00 |
| TOPO_25.1 | ok |  | 2,732,689 | 2,732,689 | 0 | cell_median | cell_median | 64.60 |

## 4. Overall metrics

| product_name | product_role | sampling_method | requested_cells | count | nodata_count | coverage_fraction | bias | MAE | RMSE | weighted_MAE | weighted_RMSE | median_error | MAD | abs_error_p90 | abs_error_p95 | abs_error_p99 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEBCO_2024 | expanded_primary_ship | cell_median | 2,732,689 | 2,732,689 | 0 | 1.00 | 5.16 | 23.30 | 98.56 | 19.82 | 80.73 | 0.20 | 7.24 | 46.25 | 75.90 | 230.00 |
| ETOPO_2022 | expanded_primary_ship | center_bilinear | 2,732,689 | 2,732,689 | 0 | 1.00 | 5.94 | 24.35 | 99.27 | 20.80 | 81.57 | 0.30 | 7.94 | 48.43 | 78.86 | 240.75 |
| SRTM15_V2.7 | expanded_primary_ship | cell_median | 2,732,689 | 2,732,689 | 0 | 1.00 | 4.77 | 24.11 | 101.32 | 20.41 | 83.87 | -0.05 | 6.65 | 48.19 | 82.60 | 263.83 |
| SDUST_2023 | expanded_primary_ship | cell_median | 2,732,689 | 2,732,689 | 0 | 1.00 | 7.45 | 33.55 | 106.10 | 29.86 | 89.23 | 1.71 | 13.41 | 70.77 | 113.50 | 303.78 |
| TOPO_25.1 | expanded_primary_ship | cell_median | 2,732,689 | 2,732,689 | 0 | 1.00 | 3.54 | 26.95 | 104.32 | 23.15 | 87.13 | -1.54 | 7.35 | 55.24 | 95.06 | 299.53 |

## 5. Product convention diagnostics

| product_name | sampling_method | z_convention | lon_convention | fill_value | n_cells_requested | valid_count | nodata_count | raw_z_min | raw_z_max | model_depth_min | model_depth_max | elevation_correlation | sign_error_suspected |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEBCO_2024 | cell_median | elevation_negative_ocean | -180_180 | N/A | 2,732,689 | 2,732,689 | 0 | -10902.00 | 564.50 | -564.50 | 10902.00 | 1.00 | 0 |
| ETOPO_2022 | center_bilinear | elevation_negative_ocean | -180_180 | -99999.00 | 2,732,689 | 2,732,689 | 0 | -10540.92 | 534.15 | -534.15 | 10540.92 | 1.00 | 0 |
| SRTM15_V2.7 | cell_median | elevation_negative_ocean | -180_180 | N/A | 2,732,689 | 2,732,689 | 0 | -10624.50 | 570.50 | -570.50 | 10624.50 | 1.00 | 0 |
| SDUST_2023 | cell_median | elevation_negative_ocean | 0_360 | N/A | 2,732,689 | 2,732,689 | 0 | -10745.97 | 641.77 | -641.77 | 10745.97 | 1.00 | 0 |
| TOPO_25.1 | cell_median | elevation_negative_ocean | -180_180 | N/A | 2,732,689 | 2,732,689 | 0 | -10677.46 | 1200.11 | -1200.11 | 10677.46 | 1.00 | 0 |

## 6. Recommendation

Expanded-primary sensitivity outputs are available. Run `ncei/code/15_strict_vs_expanded_compare_step08.py` to compute strict-vs-expanded deltas and coverage gain; expanded_primary remains a sensitivity product and does not replace strict_primary as the main global baseline.
