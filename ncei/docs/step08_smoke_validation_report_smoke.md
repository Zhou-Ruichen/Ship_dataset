# Step 08 Smoke Validation Report

Generated: 2026-05-26T16:36:45.944554+00:00
Elapsed: 14.2s
Preflight status: **PASS**
Smoke status: **PASS**
Validation rows: 8,000

## 1. Input products detected

| product | product_role | rows | path |
| --- | --- | --- | --- |
| strict_primary_multibeam_cells | strict_primary_multibeam | 2,398,774 | /mnt/data2/00-Data/ship/ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet |
| expanded_primary_ship_cells | expanded_primary_ship | 2,732,689 | /mnt/data2/00-Data/ship/ncei/derived/validation_cells_1min/expanded_primary_ship_cells.parquet |
| supplementary_singlebeam_cells | supplementary_singlebeam | 12,277,633 | /mnt/data2/00-Data/ship/ncei/derived/validation_cells_1min/supplementary_singlebeam_cells.parquet |
| regional_mrar_experiment_cells | regional_mrar_experiment | 9,019,383 | /mnt/data2/00-Data/ship/ncei/derived/validation_cells_1min/regional_mrar_experiment_cells.parquet |
| validation_cell_catalog | validation_cell_catalog | 24,029,705 | /mnt/data2/00-Data/ship/ncei/derived/validation_cells_1min/validation_cell_catalog.parquet |

## 2. Model status

| product_name | status | reason | rows |
| --- | --- | --- | --- |
| GEBCO_2024 | ok |  | 4,000 |
| ETOPO_2022 | ok |  | 4,000 |

## 3. Overall smoke metrics

| product_name | product_role | sampling_method | count | coverage_fraction | bias | MAE | RMSE | weighted_MAE | weighted_RMSE | median_error | MAD | abs_error_p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ETOPO_2022 | expanded_primary_ship | center_bilinear | 2,000 | 1.00 | 1.03 | 26.82 | 94.82 | 23.83 | 85.83 | 0.12 | 8.65 | 84.35 |
| ETOPO_2022 | strict_primary_multibeam | center_bilinear | 2,000 | 1.00 | 4.79 | 19.59 | 59.84 | 16.92 | 49.49 | 0.45 | 6.89 | 65.65 |
| GEBCO_2024 | expanded_primary_ship | center_nearest | 2,000 | 1.00 | 0.88 | 30.27 | 98.93 | 26.91 | 89.61 | 0.14 | 10.16 | 108.43 |
| GEBCO_2024 | strict_primary_multibeam | center_nearest | 2,000 | 1.00 | 4.51 | 23.08 | 64.32 | 20.44 | 54.82 | 0.68 | 8.48 | 84.72 |

## 4. Strict vs expanded comparison

| product_name | sampling_method | strict_count | expanded_count | coverage_gain_count | coverage_gain_fraction_vs_strict | strict_MAE | expanded_MAE | delta_MAE_expanded_minus_strict | strict_RMSE | expanded_RMSE | delta_RMSE_expanded_minus_strict | strict_weighted_RMSE | expanded_weighted_RMSE | delta_weighted_RMSE_expanded_minus_strict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ETOPO_2022 | center_bilinear | 2,000 | 2,000 | 0 | 0.00 | 19.59 | 26.82 | 7.23 | 59.84 | 94.82 | 34.98 | 49.49 | 85.83 | 36.34 |
| GEBCO_2024 | center_nearest | 2,000 | 2,000 | 0 | 0.00 | 23.08 | 30.27 | 7.18 | 64.32 | 98.93 | 34.62 | 54.82 | 89.61 | 34.78 |

## 5. Product convention diagnostics

| product_name | sampling_method | z_convention | lon_convention | fill_value | n_cells_requested | valid_count | nodata_count | raw_z_min | raw_z_max | model_depth_min | model_depth_max | elevation_correlation | sign_error_suspected |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEBCO_2024 | center_nearest | elevation_negative_ocean | -180_180 | N/A | 2,000 | 2,000 | 0 | -9559.00 | -45.00 | 45.00 | 9559.00 | 1.00 | 0 |
| GEBCO_2024 | center_nearest | elevation_negative_ocean | -180_180 | N/A | 2,000 | 2,000 | 0 | -9721.00 | -34.00 | 34.00 | 9721.00 | 1.00 | 0 |
| ETOPO_2022 | center_bilinear | elevation_negative_ocean | -180_180 | -99999.00 | 2,000 | 2,000 | 0 | -9553.00 | -45.06 | 45.06 | 9553.00 | 1.00 | 0 |
| ETOPO_2022 | center_bilinear | elevation_negative_ocean | -180_180 | -99999.00 | 2,000 | 2,000 | 0 | -9705.00 | -35.04 | 35.04 | 9705.00 | 1.00 | 0 |

## 6. Go / no-go recommendation

GO for full strict-primary validation after explicit user approval and `--confirm-full`. Do not include supplementary singlebeam or regional MRAR in strict-primary validation.
