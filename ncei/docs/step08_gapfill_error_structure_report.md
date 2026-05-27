# Step 08 Gap-Fill Error Structure Report

Generated: 2026-05-27T19:50:58.264741+00:00
Status: **PASS**
Run label: `c_gapfill`
Elapsed: 32.2s
Input repo root: `/mnt/data2/00-Data/ship`
Output directory: `/mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure`

## 1. Summary

The expanded-primary RMSE increase is driven by the 333,915 `expanded_fill=True` singlebeam gap-fill cells having materially higher RMSE than the retained strict-primary cells. Across the top-20 attribution rows, the dominant positive gap-fill squared-error share reaches 100.0% of the gap-fill term (raw overlapping sum 1368.6% because dimensions are not mutually exclusive). The exact ΔRMSE² percentage, including retained-set dilution, reaches 100.0% (raw overlapping sum 2384.8%).
The leading depth bands are `2000, 4000`, the leading 10° regions are `lon-030_lat-050, lon0120_lat0010`, and the leading quality tiers are `medium_confidence, high_confidence`. These are the primary slices to inspect when explaining why +13.92% coverage raises global RMSE by 6–8 m.

## 2. Method

This script is read-only: it loads the five Stage 4 expanded-primary by-cell parquets, splits rows by `expanded_fill`, and aggregates existing `elev_error_m` residuals. It does not resample gridded models, change Step 06B quality flags, alter Step 07B validation cells, or filter rows by residual magnitude.

For each model, `expanded_fill=True` must be 333,915 rows and `expanded_fill=False` must be 2,398,774 rows. The retained subset RMSE is reconciled to the strict-primary metrics summary with tolerance <0.01 m. All NaN slice values are grouped under the literal `<NA>`.

Attribution uses the simplified positive-term convention from the design: `sumsq_gapfill_in_slice / sumsq_gapfill_total` explains where the gap-fill squared error enters. The report also emits an exact per-slice ΔRMSE² contribution that includes the negative retained-set dilution term, but top contributors are ranked by the positive gap-fill squared-error share. Because the top-N table is the union of multiple overlapping dimensions (quality, evidence, depth, region, etc.), cumulative percentages are capped at 100% for acceptance while raw sums are retained in the safety-check details.

Model-level reconciliation:

| model | n_retained_rows | n_gapfill_rows | RMSE_strict_baseline | RMSE_retained | RMSE_gapfill | total_delta_rmse | retained_vs_strict_rmse_abs_diff |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GEBCO_2024 | 2,398,774 | 333,915 | 90.4265 | 90.4265 | 144.0781 | 8.1348 | 0.0000 |
| ETOPO_2022 | 2,398,774 | 333,915 | 91.6099 | 91.6099 | 142.7109 | 7.6651 | 0.0000 |
| SRTM15_V2.7 | 2,398,774 | 333,915 | 93.7345 | 93.7345 | 144.5665 | 7.5883 | 0.0000 |
| TOPO_25.1 | 2,398,774 | 333,915 | 97.3126 | 97.3126 | 145.0187 | 7.0060 | 0.0000 |
| SDUST_2023 | 2,398,774 | 333,915 | 99.9411 | 99.9411 | 142.7077 | 6.1544 | 0.0000 |

## 3. Top contributors

Path: `/mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_attribution_topN.tsv`

| slice_dim | slice_value | model | n_cells | share_of_gapfill | RMSE_gapfill | RMSE_retained | delta_rmse_slice | contribution_pct_of_total_delta | contribution_pct_of_total_gapfill_sumsq | contribution_to_expanded_minus_strict_rmse_sq |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| quality_tier | medium_confidence | SDUST_2023 | 235,210 | 0.7044 | 154.2006 | 51.2148 | 102.9858 | 147.0029 | 82.2427 | 1864.0341 |
| quality_tier | medium_confidence | GEBCO_2024 | 235,210 | 0.7044 | 155.3560 | 28.5235 | 126.8324 | 131.4431 | 81.8993 | 2020.7712 |
| quality_tier | medium_confidence | ETOPO_2022 | 235,210 | 0.7044 | 153.8686 | 33.0794 | 120.7893 | 134.0709 | 81.8852 | 1961.6480 |
| quality_tier | medium_confidence | TOPO_25.1 | 235,210 | 0.7044 | 156.2974 | 45.3315 | 110.9659 | 138.7206 | 81.8230 | 1959.6135 |
| quality_tier | medium_confidence | SRTM15_V2.7 | 235,210 | 0.7044 | 155.2243 | 37.5039 | 117.7204 | 133.4974 | 81.2090 | 1975.9746 |
| matched_rule_id | sb_v0_lowlat_deep_overlap_medium | SDUST_2023 | 234,427 | 0.7021 | 145.5943 |  |  | 143.4096 | 73.0745 | 1818.4709 |
| matched_rule_id | sb_v0_lowlat_deep_overlap_medium | GEBCO_2024 | 234,427 | 0.7021 | 146.7861 |  |  | 120.2286 | 72.8695 | 1848.3638 |
| matched_rule_id | sb_v0_lowlat_deep_overlap_medium | TOPO_25.1 | 234,427 | 0.7021 | 147.6188 |  |  | 132.3339 | 72.7456 | 1869.3931 |
| matched_rule_id | sb_v0_lowlat_deep_overlap_medium | ETOPO_2022 | 234,427 | 0.7021 | 145.2220 |  |  | 123.6504 | 72.6979 | 1809.1812 |
| matched_rule_id | sb_v0_lowlat_deep_overlap_medium | SRTM15_V2.7 | 234,427 | 0.7021 | 146.6416 |  |  | 124.6302 | 72.2356 | 1844.7264 |
| evidence_class | within | ETOPO_2022 | 264,527 | 0.7922 | 135.7742 |  |  | 121.9629 | 71.7057 | 1784.4902 |
| evidence_class | within | SDUST_2023 | 264,527 | 0.7922 | 135.3750 |  |  | 139.9035 | 71.2880 | 1774.0122 |
| evidence_class | within | TOPO_25.1 | 264,527 | 0.7922 | 137.3966 |  |  | 129.3607 | 71.1112 | 1827.3935 |
| evidence_class | within | GEBCO_2024 | 264,527 | 0.7922 | 135.9750 |  |  | 116.4176 | 70.5597 | 1789.7736 |
| evidence_class | within | SRTM15_V2.7 | 264,527 | 0.7922 | 136.0218 |  |  | 121.0007 | 70.1319 | 1791.0047 |
| depth_bin | 2000 | TOPO_25.1 | 151,679 | 0.4542 | 149.8846 | 60.5039 | 89.3807 | 88.2596 | 48.5239 | 1246.7855 |
| depth_bin | 2000 | SDUST_2023 | 151,679 | 0.4542 | 147.4561 | 47.3356 | 100.1206 | 95.1692 | 48.4976 | 1206.7703 |
| depth_bin | 2000 | SRTM15_V2.7 | 151,679 | 0.4542 | 148.8984 | 58.5204 | 90.3780 | 83.1289 | 48.1875 | 1230.4411 |
| depth_bin | 2000 | ETOPO_2022 | 151,679 | 0.4542 | 146.7977 | 47.1040 | 99.6938 | 81.7431 | 48.0633 | 1196.0180 |
| depth_bin | 2000 | GEBCO_2024 | 151,679 | 0.4542 | 147.8140 | 44.2832 | 103.5308 | 78.8779 | 47.8107 | 1212.6479 |

## 4. Per-dimension breakdown

- `lat_band_10deg` TSV: `/mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_lat_band_10deg.tsv`
- `depth_bin` TSV: `/mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_depth_bin.tsv`
- `region_10deg` TSV: `/mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_region_10deg.tsv`
- `quality_tier` TSV: `/mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_quality_tier.tsv`
- `evidence_class` TSV: `/mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_evidence_class.tsv`
- `matched_rule_id` TSV: `/mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_matched_rule_id.tsv`

Each-dimension top-3 contributors, summed across models:

| slice_dim | slice_value | n_cells | contribution_pct_of_total_gapfill_sumsq | mean_RMSE_gapfill | mean_delta_rmse_slice |
| --- | --- | --- | --- | --- | --- |
| lat_band_10deg | -50 | 82,895 | 80.2788 | 258.6084 | 214.9560 |
| lat_band_10deg | 10 | 96,190 | 55.6349 | 199.8499 | 113.0835 |
| lat_band_10deg | 40 | 226,990 | 48.8130 | 121.8588 | 69.7342 |
| depth_bin | 2000 | 758,395 | 241.0830 | 148.1702 | 96.6208 |
| depth_bin | 4000 | 415,320 | 123.4458 | 143.2690 | 84.7458 |
| depth_bin | 0 | 232,500 | 67.0299 | 141.0943 | 117.7834 |
| region_10deg | lon-030_lat-050 | 490 | 66.2426 | 3055.3650 |  |
| region_10deg | lon0120_lat0010 | 7,785 | 35.7892 | 563.3487 | 515.9511 |
| region_10deg | lon-070_lat-060 | 265 | 34.5575 | 3000.9044 | 2944.3509 |
| quality_tier | medium_confidence | 1,176,050 | 409.0591 | 154.9894 | 115.8588 |
| quality_tier | high_confidence | 493,525 | 90.9409 | 112.8104 | 80.6243 |
| quality_tier | low_confidence | 0 | 0.0000 |  |  |
| evidence_class | within | 1,322,635 | 354.7966 | 136.1085 |  |
| evidence_class | both | 344,915 | 103.5540 | 143.9912 | 94.7821 |
| evidence_class | cross | 2,025 | 41.6495 | 1191.7756 | 1133.8034 |
| matched_rule_id | sb_v0_lowlat_deep_overlap_medium | 1,172,135 | 363.6231 | 146.3726 |  |
| matched_rule_id | sb_v0_lowlat_shallow_overlap_high | 392,855 | 83.0811 | 120.8429 |  |
| matched_rule_id | any_v0_strong_unique_medium | 3,915 | 45.4360 | 895.2528 | 808.1530 |

## 5. Cross-model consistency

Repeated slice values across several models indicate ship-side / geography-driven difficult areas rather than a product-specific artifact.

| slice_dim | slice_value | models | n_models | top20_rows | cumulative_gapfill_pct |
| --- | --- | --- | --- | --- | --- |
| quality_tier | medium_confidence | ETOPO_2022,GEBCO_2024,SDUST_2023,SRTM15_V2.7,TOPO_25.1 | 5 | 5 | 409.0591 |
| matched_rule_id | sb_v0_lowlat_deep_overlap_medium | ETOPO_2022,GEBCO_2024,SDUST_2023,SRTM15_V2.7,TOPO_25.1 | 5 | 5 | 363.6231 |
| evidence_class | within | ETOPO_2022,GEBCO_2024,SDUST_2023,SRTM15_V2.7,TOPO_25.1 | 5 | 5 | 354.7966 |
| depth_bin | 2000 | ETOPO_2022,GEBCO_2024,SDUST_2023,SRTM15_V2.7,TOPO_25.1 | 5 | 5 | 241.0830 |

## 6. Safety checks

Path: `/mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/c_gapfill_safety_checks.tsv`

| status | n_checks |
| --- | --- |
| PASS | 58 |

## 7. Outputs

| kind | path |
| --- | --- |
| topN | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_attribution_topN.tsv |
| safety | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/c_gapfill_safety_checks.tsv |
| model_totals | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_model_totals.tsv |
| report | /mnt/data2/00-Data/ship/ncei/docs/step08_gapfill_error_structure_report.md |
| slice_lat_band_10deg | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_lat_band_10deg.tsv |
| slice_depth_bin | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_depth_bin.tsv |
| slice_region_10deg | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_region_10deg.tsv |
| slice_quality_tier | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_quality_tier.tsv |
| slice_evidence_class | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_evidence_class.tsv |
| slice_matched_rule_id | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_matched_rule_id.tsv |

## 8. Caveats

- The top-N table intentionally ranks overlapping dimension slices; percentages can overlap across dimensions.
- `matched_rule_id` can be sparse; missing values are retained as `<NA>` rather than dropped.
- This is not a bootstrap confidence interval analysis and does not claim statistical uncertainty bounds.
- No residual magnitude threshold is applied; large-error cells remain represented in the by-cell inputs and aggregate outputs.
