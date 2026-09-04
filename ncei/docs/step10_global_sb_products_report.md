# Step 10 global singlebeam products

Generated: 2026-09-02T19:36:05Z  
Interpreter: `/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python`  
Global crossover runtime: 1111.8 s

## Global track bias and adjusted cells

The bias table contains 1,647 SB tracks with at least one strict-MB co-located 1-minute cell. The gate applied a constant correction to 83 tracks; 115 had fewer than five support cells and 1,449 did not meet `|bias| >= 2 * NMAD`.

Applied signed bias (m, SB minus strict MB): minimum -7146.27, median -13.90, maximum 4156.48; median absolute bias 78.44.

The adjusted product contains 5,365 per-track files and 17,294,849 cell rows. It preserves the actual upstream field name `median_depth_m`; the PRD's `depth_median_m` wording does not match the existing schema. Added provenance fields are `track_bias_m`, `bias_applied`, and `bias_n_support`.

The bias reference is `strict_primary_multibeam_cells.parquet` only. No SB leave-one-out reference, regional_mrar, GEBCO, or downstream evaluation data is used.

## Global crossover audit

The audit found 5,205,339 crossovers over 260,976 track pairs. It imports the exact segment intersection, linear interpolation, gap, ordering, and nc time-QC functions from script 24. Global processing uses 10-degree tiles and removes repeated boundary events.

| branch pair | track pairs | crossovers | median |difference| (m) | p90 |difference| (m) | NMAD signed (m) |
| --- | ---: | ---: | ---: | ---: | ---: |
| nc_x_nc | 26,708 | 263,976 | 19.48 | 452.39 | 28.62 |
| nc_x_xyz | 128,089 | 1,434,243 | 20.42 | 264.73 | 30.40 |
| xyz_x_xyz | 258,179 | 3,507,120 | 16.45 | 159.92 | 24.27 |

nc time QC covers 1,850 usable tracks: 0 contain missing times, 163 fail monotonicity, and 0 fail the 1930-2035 epoch check.

Crossover-interpolated depths use metres positive down. The sign table records the observed nonnegative share for each branch; it is a convention check at actual geometric crossings, not an accuracy test.

| branch | interpolated depths | negative | nonnegative share | median depth (m positive down) |
| --- | ---: | ---: | ---: | ---: |
| nc | 1,962,195 | 0 | 1.000000 | 2081.05 |
| xyz | 8,448,483 | 0 | 1.000000 | 1584.17 |

The six-region event-count comparison reruns each original 5-degree bbox with the imported step 09 machinery, then compares against the retained step 09 event parquets:

| region | step 09 | same-bbox rerun | match |
| --- | ---: | ---: | --- |
| lon068_lat018 | 1,276 | 1,276 | yes |
| lon052_lat018 | 1,286 | 1,286 | yes |
| lon058_lat012 | 2,575 | 2,575 | yes |
| lon059_lat015 | 1,006 | 1,006 | yes |
| lon004_lat033 | 1,860 | 1,860 | yes |
| lon021_lat010 | 4,826 | 4,826 | yes |

This is a same-bbox reproducibility check, not a crop of the adaptive global table. The global audit subdivides dense 10-degree tiles and uses endpoint margins; direct regional crops of that table can therefore differ at tile boundaries.

## Global coverage

Coverage maps use a fixed global longitude/latitude window. Color is the number of occupied 1-minute cells in each 1-degree plotting bin.

| source | occupied 1-minute cells | occupied 1-degree bins | maximum per 1-degree bin |
| --- | ---: | ---: | ---: |
| jamstec_multibeam | 2,394,115 | 3,062 | 3,600 |
| ncei_multibeam | 5,960 | 39 | 1,015 |
| singlebeam_nc | 6,732,722 | 31,226 | 3,127 |
| singlebeam_xyz | 8,954,123 | 37,912 | 3,600 |

The historical strict-MB table has a label mismatch that is left unchanged: rows with `source_provider=jamstec` carry `source_dataset=NCEI_multibeam`, while `source_provider=ncei_multibeam` rows carry `source_dataset=NCEI`. New coverage outputs use the actual providers: JAMSTEC multibeam and NCEI multibeam.

## How downstream should consume this

Use `ncei/derived/singlebeam/file_cells_1min_adjusted/` instead of the raw `file_cells_1min/` directory. Keep `median_depth_m` as metres positive down and retain the three bias provenance fields when aggregating tracks. `bias_applied=False` with support greater than zero means the estimator was gated off; support zero means no strict-MB co-location was available.

Do not add `regional_mrar` to this product. It is a regional point cloud without per-track order, so the per-track constant-bias and crossover procedures used here do not apply to it.

The adjusted SB cells are an upstream product. Downstream projects remain responsible for their own training, validation, and evaluation separation.

## Outputs

- `ncei/derived/sb_track_bias_global/track_bias_summary.parquet`
- `ncei/derived/singlebeam/file_cells_1min_adjusted/*.parquet`
- `ncei/derived/global_sb_crossover_audit/*.parquet`
- `ncei/figures/coverage_global/*.png`

## Global merged 1-arcminute grid r2

Generated: 2026-09-02T22:55:03Z
Command: `/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python ncei/code/31_build_global_grid_1min.py`

The merged product contains 15,245,229 unique 1-arcminute ship cells: 2,398,774 use strict multibeam and 12,846,455 are filled by non-rejected final singlebeam. There are 489,958 overlap cells; their primary depth is strict multibeam and their singlebeam median remains in `sb_median_depth_m`.

| latitude band | rows |
| ---: | ---: |
| -90 | 1 |
| -80 | 265,162 |
| -70 | 651,077 |
| -60 | 701,126 |
| -50 | 658,243 |
| -40 | 799,104 |
| -30 | 785,394 |
| -20 | 996,711 |
| -10 | 956,231 |
| 0 | 1,226,872 |
| 10 | 1,509,259 |
| 20 | 1,871,432 |
| 30 | 1,816,778 |
| 40 | 1,237,458 |
| 50 | 765,865 |
| 60 | 373,380 |
| 70 | 345,395 |
| 80 | 285,741 |

All 15 fixed-seed spot checks passed: five strict-MB cells, five overlap cells, and five SB-only cells.
