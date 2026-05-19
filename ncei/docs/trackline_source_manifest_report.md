# NCEI Trackline Source Manifest Report

Generated: 2026-05-19T17:40:06.688518+00:00
Run label: `full`
Elapsed: 50.3s
Rows: 7,400
Errors: 0

## Source counts

| source_type | source_completeness | tracks |
| --- | --- | --- |
| ncei_nc | nc_only | 168 |
| ncei_nc | nc_xyz_intersect | 1850 |
| ncei_xyz | nc_xyz_intersect | 1850 |
| ncei_xyz | xyz_only | 3532 |

## Instrument predictions

| source_type | instrument_class_pred | tracks |
| --- | --- | --- |
| ncei_nc | singlebeam | 2018 |
| ncei_xyz | multibeam | 17 |
| ncei_xyz | singlebeam | 5365 |

## Field availability

| source_type | tracks | has_time | has_depth | has_gobs | has_faa |
| --- | --- | --- | --- | --- | --- |
| ncei_nc | 2018 | 2018 | 1883 | 778 | 2018 |
| ncei_xyz | 5382 | 0 | 5382 | 0 | 0 |

## Raw depth sign diagnosis

| source_type | depth_sign_raw | tracks |
| --- | --- | --- |
| ncei_nc | all_zero | 33 |
| ncei_nc | mostly_positive | 1850 |
| ncei_nc | no_depth_values | 135 |
| ncei_xyz | mostly_positive | 5382 |

> Note: MGD77+ corrected bathymetry is expected to be positive below sea level; NCEI XYZ documentation says exported XYZ depths may be negative. This report records observed raw signs and does not normalize depths.

## Classification review cases

Review rows: 157

| track_id | source_type | n_points | bbox_area_km2 | point_density_km2 | instrument_class_pred | classification_rule | review_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ra304-15 | ncei_xyz | 4791752 | 120814.248 | 39.662 | multibeam | hard_mb_points | hard_mb_points |
| ra022-3 | ncei_xyz | 4681732 | 219931.669 | 21.287 | multibeam | hard_mb_points | hard_mb_points |
| sentry421 | ncei_xyz | 2986580 | 14.022 | 212990.669 | multibeam | hard_mb_points | hard_mb_points |
| sentry422 | ncei_xyz | 2925767 | 12.452 | 234959.991 | multibeam | hard_mb_points | hard_mb_points |
| sentry428 | ncei_xyz | 2924587 | 24.719 | 118313.927 | multibeam | hard_mb_points | hard_mb_points |
| sentry424 | ncei_xyz | 2892350 | 17.149 | 168661.368 | multibeam | hard_mb_points | hard_mb_points |
| sentry426 | ncei_xyz | 2842137 | 17.117 | 166045.713 | multibeam | hard_mb_points | hard_mb_points |
| sentry420 | ncei_xyz | 2700654 | 11.517 | 234497.900 | multibeam | hard_mb_points | hard_mb_points |
| sentry427 | ncei_xyz | 2687721 | 11.227 | 239406.798 | multibeam | hard_mb_points | hard_mb_points |
| sentry419 | ncei_xyz | 2610931 | 13.434 | 194347.935 | multibeam | hard_mb_points | hard_mb_points |
| sentry418 | ncei_xyz | 2286087 | 20.671 | 110591.274 | multibeam | hard_mb_points | hard_mb_points |
| sentry423 | ncei_xyz | 1548425 | 11.827 | 130926.036 | multibeam | hard_mb_points | hard_mb_points |
| ra028-09 | ncei_xyz | 800058 | 1089.474 | 734.352 | multibeam | borderline_bbox_below_cutoff | borderline_bbox_below_cutoff |
| at27a | ncei_xyz | 709927 | 7873.763 | 90.164 | multibeam | borderline_density_above_cutoff | borderline_density_above_cutoff |
| nf-10-01-02-crer-rfr | ncei_xyz | 195180 | 91.181 | 2140.579 | multibeam | borderline_bbox_below_cutoff | borderline_bbox_below_cutoff |
| ab1999 | ncei_xyz | 109967 | 1089.618 | 100.922 | multibeam | borderline_bbox_below_cutoff | borderline_bbox_below_cutoff |
| int_9125 | ncei_xyz | 106088 | 4237.078 | 25.038 | multibeam | borderline_bbox_below_cutoff | borderline_bbox_below_cutoff |
| sbp1310 | ncei_xyz | 894604 | 47380.874 | 18.881 | singlebeam | borderline_default_sb | borderline_default_singlebeam |
| ra188-16 | ncei_xyz | 860154 | 7046495.434 | 0.122 | singlebeam | borderline_default_sb | borderline_default_singlebeam |
| mv0902 | ncei_xyz | 779771 | 166163.574 | 4.693 | singlebeam | borderline_default_sb | borderline_default_singlebeam |
| index13 | ncei_nc | 609668 | 945100.116 | 0.645 | singlebeam | borderline_default_sb | borderline_default_singlebeam |
| ra164-11 | ncei_xyz | 584117 | 829768.163 | 0.704 | singlebeam | borderline_default_sb | borderline_default_singlebeam |
| index13 | ncei_xyz | 582750 | 944958.301 | 0.617 | singlebeam | borderline_default_sb | borderline_default_singlebeam |
| ha1501 | ncei_xyz | 510145 | 6470006.746 | 0.079 | singlebeam | borderline_default_sb | borderline_default_singlebeam |
| mv1012 | ncei_xyz | 500085 | 38072.265 | 13.135 | singlebeam | borderline_default_sb | borderline_default_singlebeam |
| ha1201 | ncei_xyz | 477497 | 6469962.455 | 0.074 | singlebeam | borderline_default_sb | borderline_default_singlebeam |
| km0514 | ncei_nc | 467782 | 8586078.692 | 0.054 | singlebeam | borderline_default_sb | borderline_default_singlebeam |
| ra247-16 | ncei_xyz | 457488 | 2322968.147 | 0.197 | singlebeam | borderline_default_sb | borderline_default_singlebeam |
| ra022-2 | ncei_xyz | 451614 | 426008.242 | 1.060 | singlebeam | borderline_default_sb | borderline_default_singlebeam |
| ha1401 | ncei_xyz | 451183 | 1782180.495 | 0.253 | singlebeam | borderline_default_sb | borderline_default_singlebeam |

## Largest tracks

| track_id | source_type | source_completeness | n_points | bbox_area_km2 | point_density_km2 | instrument_class_pred | classification_rule |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ra304-15 | ncei_xyz | xyz_only | 4791752 | 120814.248 | 39.662 | multibeam | hard_mb_points |
| ra022-3 | ncei_xyz | xyz_only | 4681732 | 219931.669 | 21.287 | multibeam | hard_mb_points |
| sentry421 | ncei_xyz | xyz_only | 2986580 | 14.022 | 212990.669 | multibeam | hard_mb_points |
| sentry422 | ncei_xyz | xyz_only | 2925767 | 12.452 | 234959.991 | multibeam | hard_mb_points |
| sentry428 | ncei_xyz | xyz_only | 2924587 | 24.719 | 118313.927 | multibeam | hard_mb_points |
| sentry424 | ncei_xyz | xyz_only | 2892350 | 17.149 | 168661.368 | multibeam | hard_mb_points |
| sentry426 | ncei_xyz | xyz_only | 2842137 | 17.117 | 166045.713 | multibeam | hard_mb_points |
| sentry420 | ncei_xyz | xyz_only | 2700654 | 11.517 | 234497.900 | multibeam | hard_mb_points |
| sentry427 | ncei_xyz | xyz_only | 2687721 | 11.227 | 239406.798 | multibeam | hard_mb_points |
| sentry419 | ncei_xyz | xyz_only | 2610931 | 13.434 | 194347.935 | multibeam | hard_mb_points |
| sentry418 | ncei_xyz | xyz_only | 2286087 | 20.671 | 110591.274 | multibeam | hard_mb_points |
| sentry423 | ncei_xyz | xyz_only | 1548425 | 11.827 | 130926.036 | multibeam | hard_mb_points |
| sbp1310 | ncei_xyz | xyz_only | 894604 | 47380.874 | 18.881 | singlebeam | borderline_default_sb |
| ra188-16 | ncei_xyz | xyz_only | 860154 | 7046495.434 | 0.122 | singlebeam | borderline_default_sb |
| ra028-09 | ncei_xyz | xyz_only | 800058 | 1089.474 | 734.352 | multibeam | borderline_bbox_below_cutoff |
| mv0902 | ncei_xyz | xyz_only | 779771 | 166163.574 | 4.693 | singlebeam | borderline_default_sb |
| at27a | ncei_xyz | xyz_only | 709927 | 7873.763 | 90.164 | multibeam | borderline_density_above_cutoff |
| index13 | ncei_nc | nc_xyz_intersect | 609668 | 945100.116 | 0.645 | singlebeam | borderline_default_sb |
| ra164-11 | ncei_xyz | xyz_only | 584117 | 829768.163 | 0.704 | singlebeam | borderline_default_sb |
| index13 | ncei_xyz | nc_xyz_intersect | 582750 | 944958.301 | 0.617 | singlebeam | borderline_default_sb |
