# NCEI Singlebeam Standardization Report (PR-E2)

Generated: 2026-05-19T19:50:27.436156+00:00
Run label: `full`
Standardization version: `ncei_sb_v0.1.0`
Elapsed: 157.0s
Tracks in (after manifest filter): 1,850
Tracks standardized: 1,850
Errors: 0
Total per-point warnings: 1

## Source completeness counts

| source_completeness | tracks |
| --- | --- |
| nc_xyz_intersect | 1850 |

## Depth-sign-raw counts

| depth_sign_raw | tracks |
| --- | --- |
| mostly_positive | 1850 |

## Field availability

| tracks | has_time | has_gobs | has_faa |
| --- | --- | --- | --- |
| 1850 | 1850 | 694 | 1850 |

## Geometry / depth ranges

| n_points_in_total | n_points_out_total | n_points_in_per_track_min | n_points_in_per_track_max | lon_min | lon_max | lat_min | lat_max | depth_min_overall | depth_max_overall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 35841758.000 | 35841758.000 | 35.000 | 609668.000 | -180.000 | 180.000 | -78.592 | 88.277 | 0.000 | 18640.000 |

## Time range (tracks with time only)

| tracks_with_time | time_min_overall | time_max_overall |
| --- | --- | --- |
| 1850 | 1961-01-12 09:22:00 | 2017-10-09 11:00:19.980000 |

## Warnings rollup

Tracks with one or more sign-anomaly points: 1
Total sign-anomaly points across all tracks: 1

| track_id | depth_sign_raw | n_points_out | n_warnings |
| --- | --- | --- | --- |
| nbp0505 | mostly_positive | 21685 | 1 |

## Output paths

- Per-track parquet dir: `ncei/derived/singlebeam/points_raw/`
- Aggregate manifest (parquet): `ncei/manifests/singlebeam_points_raw_manifest.parquet`
- Aggregate manifest (tsv): `ncei/manifests/singlebeam_points_raw_manifest.tsv`
