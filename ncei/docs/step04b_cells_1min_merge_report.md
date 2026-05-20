# NCEI Step 04B — Branch-specific 1-arcmin Cell Merge Report

Generated: 2026-05-20T20:26:48.449083+00:00
Run label: `full`
Merge version: `ncei_cells_merge_v0.1.0`
Cell size: 1 arc-minute (1/60°)
Elapsed: 609.3s

> Depth merge rule: `median_depth_m = median(per_file_cell.median_depth_m)`. 
> This is a median of per-track/per-file cell medians, not a pooled-point median and not weighted by `n_points_pass`.

> Duplicate convention: `n_unique_triples_total` is the sum of Step 04A per-file-cell `n_unique_triples`. 
> This intentionally over-counts exact triples duplicated across different files/tracks; per-file-cell exact-float dedup remains the authoritative production dedup level for now.

## 1. Per-branch input and output totals

| branch | input_file_cells | n_cells_total | n_track_cells_total | n_tracks_total | n_points_pass_grand_total | n_unique_triples_grand_total | n_lat_bands_occupied | n_manual_review_cells | manual_review_cell_share | runtime_seconds | merge_version |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| multibeam_ncei | 17 | 5960 | 6329 | 17 | 37799943 | 33162175 | 7 | 0 | 0.0000 | 0.2165 | ncei_cells_merge_v0.1.0 |
| regional_mrar | 3 | 9019383 | 9019512 | 3 | 113356269 | 112764924 | 17 | 0 | 0.0000 | 157.3946 | ncei_cells_merge_v0.1.0 |
| singlebeam | 5365 | 14611054 | 17294849 | 5365 | 77445882 | 77028749 | 18 | 206247 | 0.0141 | 440.1513 | ncei_cells_merge_v0.1.0 |

## 2. n_track_cells percentiles per merged cell

| branch | metric | p0 | p25 | p50 | p75 | p90 | p99 | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| singlebeam | n_track_cells | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 2.0000 | 3.0000 | 46.0000 |
| multibeam_ncei | n_track_cells | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 2.0000 | 5.0000 |
| regional_mrar | n_track_cells | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 2.0000 |

## 3. Depth distribution (`median_depth_m`) per branch

| branch | metric | p0 | p25 | p50 | p75 | p90 | p99 | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| singlebeam | median_depth_m | 0.1000 | 2069.3000 | 3568.0000 | 4644.0000 | 5318.0000 | 6102.0000 | 11231.3000 |
| multibeam_ncei | median_depth_m | 1.4500 | 485.5900 | 1249.0225 | 1936.5275 | 3675.1040 | 4814.3887 | 5741.4000 |
| regional_mrar | median_depth_m | 1.0000 | 3385.0000 | 4270.5000 | 5094.0000 | 5653.0000 | 7313.0000 | 11500.0000 |

## 4. Top cells by n_track_cells (multi-source hotspots)

### singlebeam

| cell_id | lon_center | lat_center | n_track_cells | n_tracks | median_depth_m | n_points_pass_total | manual_review_any |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1min_6676_1327 | -157.8750 | 21.2750 | 46 | 46 | 231.4750 | 1440 | False |
| 1min_6674_1328 | -157.8583 | 21.2417 | 38 | 38 | 469.5000 | 2052 | False |
| 1min_6675_1327 | -157.8750 | 21.2583 | 37 | 37 | 411.0000 | 1593 | False |
| 1min_6677_1327 | -157.8750 | 21.2917 | 35 | 35 | 29.0000 | 811 | False |
| 1min_6676_1326 | -157.8917 | 21.2750 | 34 | 34 | 274.4750 | 1835 | False |
| 1min_4349_1824 | -149.5917 | -17.5083 | 34 | 34 | 1001.4800 | 389 | False |
| 1min_4348_1824 | -149.5917 | -17.5250 | 33 | 33 | 681.5000 | 757 | False |
| 1min_6675_1328 | -157.8583 | 21.2583 | 32 | 32 | 362.0750 | 1449 | False |
| 1min_6674_1329 | -157.8417 | 21.2417 | 31 | 31 | 449.0000 | 868 | False |
| 1min_6674_1327 | -157.8750 | 21.2417 | 30 | 30 | 491.0000 | 3360 | False |

### multibeam_ncei

| cell_id | lon_center | lat_center | n_track_cells | n_tracks | median_depth_m | n_points_pass_total | manual_review_any |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1min_4022_4085 | -111.9083 | -22.9583 | 5 | 5 | 3609.5000 | 2036849 | False |
| 1min_4021_4085 | -111.9083 | -22.9750 | 3 | 3 | 4210.7000 | 1104315 | False |
| 1min_4021_4084 | -111.9250 | -22.9750 | 3 | 3 | 4744.7000 | 905278 | False |
| 1min_4022_4086 | -111.8917 | -22.9583 | 3 | 3 | 3518.5000 | 443732 | False |
| 1min_4022_4084 | -111.9250 | -22.9583 | 3 | 3 | 4342.1000 | 98206 | False |
| 1min_4025_4078 | -112.0250 | -22.9083 | 2 | 2 | 3877.7500 | 1478782 | False |
| 1min_4023_4085 | -111.9083 | -22.9417 | 2 | 2 | 4111.1000 | 1317678 | False |
| 1min_4021_4083 | -111.9417 | -22.9750 | 2 | 2 | 5110.3000 | 1143087 | False |
| 1min_4021_4086 | -111.8917 | -22.9750 | 2 | 2 | 3629.0500 | 922265 | False |
| 1min_4026_4077 | -112.0417 | -22.8917 | 2 | 2 | 3613.5500 | 897356 | False |

### regional_mrar

| cell_id | lon_center | lat_center | n_track_cells | n_tracks | median_depth_m | n_points_pass_total | manual_review_any |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1min_4800_5400 | -89.9917 | -9.9917 | 2 | 2 | 4139.5000 | 36 | False |
| 1min_4637_5400 | -89.9917 | -12.7083 | 2 | 2 | 4279.5000 | 30 | False |
| 1min_4639_5400 | -89.9917 | -12.6750 | 2 | 2 | 4238.0000 | 30 | False |
| 1min_4641_5400 | -89.9917 | -12.6417 | 2 | 2 | 4231.5000 | 30 | False |
| 1min_4679_5400 | -89.9917 | -12.0083 | 2 | 2 | 4130.5000 | 30 | False |
| 1min_4734_5400 | -89.9917 | -11.0917 | 2 | 2 | 4255.0000 | 30 | False |
| 1min_4736_5400 | -89.9917 | -11.0583 | 2 | 2 | 4212.5000 | 30 | False |
| 1min_4738_5400 | -89.9917 | -11.0250 | 2 | 2 | 4303.5000 | 30 | False |
| 1min_4740_5400 | -89.9917 | -10.9917 | 2 | 2 | 4311.5000 | 30 | False |
| 1min_4789_5400 | -89.9917 | -10.1750 | 2 | 2 | 4249.5000 | 30 | False |

## 5. Top cells by duplicate_ratio_cell

### singlebeam

| cell_id | lon_center | lat_center | duplicate_ratio_cell | n_track_cells | n_points_pass_total | n_unique_triples_total |
| --- | --- | --- | --- | --- | --- | --- |
| 1min_7618_10757 | -0.7083 | 36.9750 | 0.9991 | 1 | 4508 | 4 |
| 1min_9365_10402 | -6.6250 | 66.0917 | 0.9355 | 1 | 31 | 2 |
| 1min_7878_6542 | -70.9583 | 41.3083 | 0.9333 | 1 | 15 | 1 |
| 1min_7594_9612 | -19.7917 | 36.5750 | 0.9239 | 2 | 92 | 7 |
| 1min_7690_21088 | 171.4750 | 38.1750 | 0.9231 | 1 | 26 | 2 |
| 1min_6790_19759 | 149.3250 | 23.1750 | 0.9163 | 1 | 239 | 20 |
| 1min_5475_19590 | 146.5083 | 1.2583 | 0.9144 | 1 | 187 | 16 |
| 1min_6829_19760 | 149.3417 | 23.8250 | 0.9074 | 1 | 54 | 5 |
| 1min_3850_12886 | 34.7750 | -25.8250 | 0.9012 | 2 | 3887 | 384 |
| 1min_6950_19759 | 149.3250 | 25.8417 | 0.8909 | 2 | 55 | 6 |

### multibeam_ncei

| cell_id | lon_center | lat_center | duplicate_ratio_cell | n_track_cells | n_points_pass_total | n_unique_triples_total |
| --- | --- | --- | --- | --- | --- | --- |
| 1min_4015_4089 | -111.8417 | -23.0750 | 0.9203 | 1 | 352208 | 28062 |
| 1min_4025_4076 | -112.0583 | -22.9083 | 0.8839 | 1 | 233723 | 27145 |
| 1min_4022_4083 | -111.9417 | -22.9583 | 0.7269 | 2 | 793887 | 216779 |
| 1min_7181_5699 | -85.0083 | 29.6917 | 0.6209 | 1 | 1509 | 572 |
| 1min_4026_4078 | -112.0250 | -22.8917 | 0.5914 | 2 | 803425 | 328316 |
| 1min_3999_4102 | -111.6250 | -23.3417 | 0.5899 | 1 | 203606 | 83496 |
| 1min_4022_4085 | -111.9083 | -22.9583 | 0.5635 | 5 | 2036849 | 889028 |
| 1min_7183_5706 | -84.8917 | 29.7250 | 0.5633 | 1 | 829 | 362 |
| 1min_4020_4083 | -111.9417 | -22.9917 | 0.4977 | 2 | 477010 | 239581 |
| 1min_1654_7284 | -58.5917 | -62.4250 | 0.4797 | 2 | 123 | 64 |

### regional_mrar

| cell_id | lon_center | lat_center | duplicate_ratio_cell | n_track_cells | n_points_pass_total | n_unique_triples_total |
| --- | --- | --- | --- | --- | --- | --- |
| 1min_3206_1690 | -151.8250 | -36.5583 | 0.5000 | 1 | 24 | 12 |
| 1min_3206_1689 | -151.8417 | -36.5583 | 0.5000 | 1 | 32 | 16 |
| 1min_3206_1688 | -151.8583 | -36.5583 | 0.5000 | 1 | 32 | 16 |
| 1min_3206_1687 | -151.8750 | -36.5583 | 0.5000 | 1 | 32 | 16 |
| 1min_3206_1686 | -151.8917 | -36.5583 | 0.5000 | 1 | 24 | 12 |
| 1min_3206_1685 | -151.9083 | -36.5583 | 0.5000 | 1 | 32 | 16 |
| 1min_3206_1684 | -151.9250 | -36.5583 | 0.5000 | 1 | 32 | 16 |
| 1min_3206_1683 | -151.9417 | -36.5583 | 0.5000 | 1 | 18 | 9 |
| 1min_3206_1682 | -151.9583 | -36.5583 | 0.5000 | 1 | 32 | 16 |
| 1min_3206_1681 | -151.9750 | -36.5583 | 0.5000 | 1 | 32 | 16 |

## 6. Manual-review summary

Reason source: fallback constant `step03b_flag`

| branch | cells | manual_review_cells | manual_review_cell_share | manual_review_unique_triples | manual_review_unique_triples_share_of_branch |
| --- | --- | --- | --- | --- | --- |
| singlebeam | 14611054 | 206247 | 0.0141 | 2185024 | 0.0284 |
| multibeam_ncei | 5960 | 0 | 0.0000 | 0 | 0.0000 |
| regional_mrar | 9019383 | 0 | 0.0000 | 0 | 0.0000 |

## 7. Source / completeness / instrument row-count totals

| branch | n_source_ncei_nc | n_source_ncei_xyz | n_source_mrar_zhoushuai | n_completeness_nc_xyz_intersect | n_completeness_xyz_only | n_completeness_nc_only | n_instrument_singlebeam | n_instrument_multibeam |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| singlebeam | 7304682 | 9990167 | 0 | 7304682 | 9990167 | 0 | 17294849 | 0 |
| multibeam_ncei | 0 | 6329 | 0 | 0 | 6329 | 0 | 0 | 6329 |
| regional_mrar | 0 | 0 | 9019512 | 0 | 0 | 0 | 0 | 9019512 |

## 8. Output paths

| kind | path |
| --- | --- |
| top-level manifest | ncei/manifests/cells_1min_manifest.parquet |
| report (this file) | ncei/docs/step04b_cells_1min_merge_report.md |
| singlebeam cells dataset | ncei/derived/singlebeam/cells_1min |
| multibeam_ncei cells dataset | ncei/derived/multibeam/cells_1min |
| regional_mrar cells dataset | ncei/derived/regional_mrar/cells_1min |

## 9. Guardrails confirmed

- No cross-branch merge: each branch was read, grouped, and written independently; `branch` remains a partition key.
- No A/B/C quality tiers were defined.
- `manual_review_any` is informational only; no cell was dropped because of it.
- `median_depth_m` is the median of Step 04A per-file-cell medians.
- `n_unique_triples_total` is present/non-null on all loaded Step 04A rows.

## 10. References

- Step 04A implementation: `ncei/code/07_aggregate_file_cells_1min.py` (`AGGREGATION_VERSION`).
- Step 04A run report: `ncei/docs/step04a_file_cells_1min_report.md`.
- Step 04A/04B design audit: `ncei/docs/step04_aggregation_design_audit.md`.
- Spec §13 (NCEI Step 04A per-file 1-arcmin cell aggregation): `.trellis/spec/backend/pipeline-design-decisions.md`.
