# Step 08 Preflight Report

Generated: 2026-05-26T16:36:12.342143+00:00
Overall status: **PASS**

## 1. Step 07B product row counts and schema

| product_key | product_role | path | exists | is_hive_dir | row_count | expected_rows | schema_columns | missing_physical_columns | optional_carry_columns_present | status | problems |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| strict_primary_multibeam_cells | strict_primary_multibeam | /mnt/data2/00-Data/ship/ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet | 1 | 0 | 2,398,774 | 2,398,774 | 32 |  | lon_bin,lat_bin,lat_band_10deg,n_points_pass_total,n_track_cells,n_tracks,manual_review_any,low_evidence_flag,n_cross_branch_overlap,depth_bin,sensitivity_only_flag,precedence_resolution,final_primary_source,source_dataset,dominant_file_id,enforced_rules_version,merge_version,validation_product_version,source_risk_class,auv_sentry_flag | PASS |  |
| expanded_primary_ship_cells | expanded_primary_ship | /mnt/data2/00-Data/ship/ncei/derived/validation_cells_1min/expanded_primary_ship_cells.parquet | 1 | 0 | 2,732,689 | 2,732,689 | 33 |  | lon_bin,lat_bin,lat_band_10deg,n_points_pass_total,n_track_cells,n_tracks,manual_review_any,low_evidence_flag,n_cross_branch_overlap,depth_bin,sensitivity_only_flag,precedence_resolution,final_primary_source,source_dataset,dominant_file_id,enforced_rules_version,merge_version,validation_product_version,source_risk_class,auv_sentry_flag,expanded_fill | PASS |  |
| supplementary_singlebeam_cells | supplementary_singlebeam | /mnt/data2/00-Data/ship/ncei/derived/validation_cells_1min/supplementary_singlebeam_cells.parquet | 1 | 1 | 12,277,633 | 12,277,633 | 32 |  | lon_bin,lat_bin,lat_band_10deg,n_points_pass_total,n_track_cells,n_tracks,manual_review_any,low_evidence_flag,n_cross_branch_overlap,depth_bin,sensitivity_only_flag,precedence_resolution,final_primary_source,source_dataset,dominant_file_id,enforced_rules_version,merge_version,validation_product_version,source_risk_class,auv_sentry_flag | PASS |  |
| regional_mrar_experiment_cells | regional_mrar_experiment | /mnt/data2/00-Data/ship/ncei/derived/validation_cells_1min/regional_mrar_experiment_cells.parquet | 1 | 1 | 9,019,383 | 9,019,383 | 32 |  | lon_bin,lat_bin,lat_band_10deg,n_points_pass_total,n_track_cells,n_tracks,manual_review_any,low_evidence_flag,n_cross_branch_overlap,depth_bin,sensitivity_only_flag,precedence_resolution,final_primary_source,source_dataset,dominant_file_id,enforced_rules_version,merge_version,validation_product_version,source_risk_class,auv_sentry_flag | PASS |  |
| validation_cell_catalog | validation_cell_catalog | /mnt/data2/00-Data/ship/ncei/derived/validation_cells_1min/validation_cell_catalog.parquet | 1 | 1 | 24,029,705 | 24,029,705 | 34 |  | lon_bin,lat_bin,lat_band_10deg,n_points_pass_total,n_track_cells,n_tracks,manual_review_any,low_evidence_flag,n_cross_branch_overlap,depth_bin,sensitivity_only_flag,precedence_resolution,final_primary_source,source_dataset,dominant_file_id,enforced_rules_version,merge_version,validation_product_version,source_risk_class,auv_sentry_flag,product_membership,product_label | PASS |  |

## 2. Derived required fields

| Required field | Source | Status |
|---|---|---|
| depth_m_positive_down | derived from representative_depth_m | PASS |
| elev_m | derived as -representative_depth_m | PASS |
| product_role | derived from Step 07B product name | PASS |
| source_role | represented by branch_role / branch | PASS |
| matched_rule_id | Step 06B sidecar for NCEI rows; jamstec_legacy for JAMSTEC rows | PASS |

## 3. Z-sign sanity

| product_key | status | n_rows | n_null_depth | n_nonpositive_depth | min_depth_m | max_depth_m | derived_elev_max_m | problem |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| strict_primary_multibeam_cells | PASS | 2,398,774 | 0 | 0 | 1.45 | 11229.00 | -1.45 |  |
| expanded_primary_ship_cells | PASS | 2,732,689 | 0 | 0 | 1.00 | 11229.00 | -1.00 |  |
| supplementary_singlebeam_cells | PASS | 12,277,633 | 0 | 0 | 0.10 | 11231.30 | -0.10 |  |
| regional_mrar_experiment_cells | PASS | 9,019,383 | 0 | 0 | 1.00 | 11500.00 | -1.00 |  |
| validation_cell_catalog | PASS | 24,029,705 | 0 | 0 | 0.10 | 11500.00 | -0.10 |  |

## 4. Product-role safety checks

| check | status | details |
| --- | --- | --- |
| strict_primary_has_no_singlebeam | PASS | ncei_singlebeam rows in strict=0 |
| strict_primary_has_no_regional_mrar | PASS | regional_mrar rows in strict=0 |
| expanded_primary_has_no_regional_mrar | PASS | regional_mrar rows in expanded=0 |
| expanded_primary_singlebeam_gapfill_marked | PASS | expanded_fill rows=333,915; ncei_singlebeam rows=333,915 |
| supplementary_is_non_primary_coverage | PASS | rows with branch_role != supplementary_coverage: 0 |
| regional_mrar_is_experiment_only | PASS | rows with branch_role != regional_experiment: 0 |

## 5. Quality-rule provenance sidecar

| check | status | path | row_count | details |
| --- | --- | --- | --- | --- |
| matched_rule_id_materialization_sidecar | PASS | /mnt/data2/00-Data/ship/ncei/derived/quality_flags_1min/cell_quality_flags_1min.parquet | 23,636,397 |  |

## 6. Gridded product config

| product_name | status | path | exists | size_gb | format | sampling_method | z_convention | lon_convention | has_footprint | problems |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEBCO_2024 | PASS | /mnt/data2/00-Data/bathymetry/GEBCO/GEBCO_2024.nc | 1 | 7.47 | netcdf | cell_median | elevation_negative_ocean | -180_180 | 0 |  |
| ETOPO_2022 | PASS | /mnt/data2/00-Data/bathymetry/ETOPO/ETOPO_2022_v1_60s_N90W180_bed.nc | 1 | 0.49 | netcdf | center_bilinear | elevation_negative_ocean | -180_180 | 0 |  |
| SRTM15_V2.7 | PASS | /mnt/data2/00-Data/bathymetry/SRTM/SRTM15_V2.7.nc | 1 | 6.56 | netcdf | cell_median | elevation_negative_ocean | -180_180 | 0 |  |
| SDUST_2023 | PASS | /mnt/data2/00-Data/bathymetry/SDUST/SDUST2023BCO.nc | 1 | 0.56 | netcdf | cell_median | elevation_negative_ocean | 0_360 | 0 |  |
| TOPO_25.1 | PASS | /mnt/data2/00-Data/bathymetry/TOPO/topo_25.1.nc | 1 | 0.55 | netcdf | cell_median | elevation_negative_ocean | -180_180 | 0 |  |
| SWOT_T1 | PASS | /mnt/data2/06-Projects/01-SWOT/04-SWOT_seafloor/output/3-evaluations/unet-multi-p128-b96-lr1e-4-1112-0646-ab40/reconstructed_absolute/swot_absolute_T1.npz | 1 | 0.04 | npz | center_bilinear | elevation_negative_ocean | -180_180 | 1 |  |

## 7. Go / no-go

Preflight passed. Smoke validation may proceed for explicitly selected products.
