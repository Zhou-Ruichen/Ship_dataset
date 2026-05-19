# NCEI XYZ Standardization Report (PR-E3)

Generated: 2026-05-19T20:44:05.427276+00:00
Run label: `full`
Standardization version: `ncei_xyz_v0.1.0`
Elapsed: 253.0s
Tracks in (after manifest filter): 5,382
Tracks standardized: 5,382
Errors: 0
Total per-point warnings: 5

## Routing (per instrument_class_pred)

| instrument_class_pred | tracks |
| --- | --- |
| multibeam | 17 |
| singlebeam | 5365 |

## Source completeness counts

| source_completeness | tracks |
| --- | --- |
| nc_xyz_intersect | 1850 |
| xyz_only | 3532 |

## Depth-sign-raw counts

| depth_sign_raw | tracks |
| --- | --- |
| mostly_positive | 5382 |

## Field availability

| tracks | has_time | has_gobs | has_faa |
| --- | --- | --- | --- |
| 5382 | 0 | 0 | 0 |

## Geometry / depth ranges

| n_points_in_total | n_points_out_total | n_points_in_per_track_min | n_points_in_per_track_max | lon_min | lon_max | lat_min | lat_max | depth_min_overall | depth_max_overall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 115256003.000 | 115256003.000 | 3.000 | 4791752.000 | -180.000 | 180.000 | -83.082 | 90.000 | 0.000 | 87178.400 |

## Top 5 largest multibeam tracks (by n_points_out)

| track_id | source_completeness | n_points_out | bbox_lon_min | bbox_lon_max | bbox_lat_min | bbox_lat_max |
| --- | --- | --- | --- | --- | --- | --- |
| ra304-15 | xyz_only | 4791752 | -42.477 | -38.382 | -24.002 | -21.421 |
| ra022-3 | xyz_only | 4681732 | -62.555 | -56.803 | -64.626 | -58.179 |
| sentry421 | xyz_only | 2986580 | -111.970 | -111.932 | -22.988 | -22.956 |
| sentry422 | xyz_only | 2925767 | -111.923 | -111.891 | -22.964 | -22.929 |
| sentry428 | xyz_only | 2924587 | -112.053 | -112.012 | -22.929 | -22.876 |

## Top 5 largest singlebeam tracks (by n_points_out)

| track_id | source_completeness | n_points_out | bbox_lon_min | bbox_lon_max | bbox_lat_min | bbox_lat_max |
| --- | --- | --- | --- | --- | --- | --- |
| sbp1310 | xyz_only | 894604 | 124.069 | 127.324 | -9.324 | -8.135 |
| ra188-16 | xyz_only | 860154 | -64.135 | -22.977 | -67.384 | -43.139 |
| mv0902 | xyz_only | 779771 | 120.217 | 124.331 | 11.222 | 14.565 |
| ra164-11 | xyz_only | 584117 | -50.762 | -42.171 | -31.858 | -23.074 |
| index13 | nc_xyz_intersect | 582750 | 68.912 | 109.425 | -21.337 | -19.330 |

## Warnings rollup

Tracks with one or more sign-anomaly points: 2
Total sign-anomaly points across all tracks: 5

| track_id | instrument_class_pred | depth_sign_raw | n_points_out | n_warnings |
| --- | --- | --- | --- | --- |
| jr353 | singlebeam | mostly_positive | 50913 | 4 |
| nbp0505 | singlebeam | mostly_positive | 20261 | 1 |

## Depth-anomaly review (depth_max > 11,500 m)

Tracks whose per-track `depth_max` exceeds the Challenger Deep + headroom cutoff. These are surfaced as known anomalies (likely unit/sentinel issues in the upstream `.xyz` export); no clipping is applied at PR-E3 — cleaning belongs to a later QC step.

Tracks with depth_max > 11500 m: 13

| track_id | instrument_class_pred | n_points_out | depth_min | depth_max |
| --- | --- | --- | --- | --- |
| ant4 | singlebeam | 101410 | 7.700 | 87178.400 |
| wi343802 | singlebeam | 3142 | 66.970 | 74999.930 |
| ant8 | singlebeam | 47919 | 0.000 | 52002.000 |
| so36 | singlebeam | 106533 | 0.000 | 44215.000 |
| so16 | singlebeam | 57108 | 40.000 | 27760.000 |
| 91039 | singlebeam | 37521 | 1.000 | 23233.000 |
| so49 | singlebeam | 46085 | 60.000 | 12386.000 |
| rr1108 | singlebeam | 91191 | 263.330 | 11966.290 |
| rr1112 | singlebeam | 62149 | 730.580 | 11960.120 |
| rr1106 | singlebeam | 66738 | 890.230 | 11927.620 |
| rr1110 | singlebeam | 256931 | 251.420 | 11922.930 |
| mv0902 | singlebeam | 779771 | 12.230 | 11752.350 |
| rr1109 | singlebeam | 101409 | 340.750 | 11706.650 |

## Output paths

- Per-track parquet dirs:
  - singlebeam: `ncei/derived/singlebeam/points_raw/<track_id>__xyz.parquet`
  - multibeam:  `ncei/derived/multibeam/points_raw/<track_id>__xyz.parquet`
- Aggregate manifest (parquet): `ncei/manifests/xyz_points_raw_manifest.parquet`
- Aggregate manifest (tsv): `ncei/manifests/xyz_points_raw_manifest.tsv`
