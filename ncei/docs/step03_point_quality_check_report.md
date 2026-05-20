# NCEI Step 03A — Point Quality Check Report

Generated: 2026-05-20T09:57:21.858747+00:00
Run label: `full`
Check version: `point_check_v0.1.0`
Elapsed: 473.2s
Entries in manifest: 7,403
Entries point-checked this run: 5,385
Errors: 0

## 2. Entry manifest rollup

### By source_priority

| source_priority | entries |
| --- | --- |
| primary | 5382 |
| regional | 3 |
| skip | 168 |
| supplementary | 1850 |

### By source_type

| source_type | entries |
| --- | --- |
| mrar_zhoushuai | 3 |
| ncei_nc | 2018 |
| ncei_xyz | 5382 |

### By source_completeness

| source_completeness | entries |
| --- | --- |
| mrar_regional | 3 |
| nc_only | 168 |
| nc_xyz_intersect | 3700 |
| xyz_only | 3532 |

### By instrument_class_pred

| instrument_class_pred | entries |
| --- | --- |
| multibeam | 20 |
| singlebeam | 7383 |

### By skip_reason

| skip_reason | entries |
| --- | --- |
| no_usable_depth | 168 |

## 3. Point check rollup (primary + regional)

| total_points_read | total_invalid_lon | total_invalid_lat | total_invalid_depth_pos | total_invalid_depth_max | total_missing_core | total_pass | pass_rate_pct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 240149435.000 | 167.000 | 0.000 | 11547194.000 | 10551323.000 | 10551323.000 | 228602094.000 | 95.192 |

### 3a. Breakdown by source_type

| source_type | entries | n_points_in | n_invalid_lon | n_invalid_depth_pos | n_invalid_depth_max | n_missing_core | n_points_pass |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mrar_zhoushuai | 3 | 113,356,582 | 0 | 313 | 0 | 0 | 113,356,269 |
| ncei_nc | 1,850 | 35,841,758 | 49 | 11,543,956 | 10,551,294 | 10,551,294 | 24,297,773 |
| ncei_xyz | 3,532 | 90,951,095 | 118 | 2,925 | 29 | 29 | 90,948,052 |

### 3b. Why the 10.55M `n_missing_core` / `n_invalid_depth_max` parity?

The two columns are equal because both count rows whose
`depth_m_positive_down` is NaN — for a NaN value, both `valid_core_fields`
(requires `finite(depth)`) and `valid_depth_max` (initialized to `False`
and only set `True` on finite rows that pass `depth <= 11,500`) evaluate
to `False`. The 167 `n_invalid_lon` rows on top of that are separately
NaN-or-out-of-range lon values.

All 10.55M NaN-depth rows are in the **nc-sb leg** (zero in xyz / mrar).
Source: MGD77+ NetCDF masked entries in `ncei/tracklines_nc/`. PR-E2
deliberately preserves all input rows verbatim (manifest:
`n_points_in == n_points_out` for every nc-sb track; no row dropping at
standardization). The MGD77+ format records sensor measurements
interleaved along each cruise's timeline; rows where the depth sensor
did not sample are stored as masked. Step 02 reads them with
`netCDF4.Dataset` and the mask survives as NaN in
`depth_m_positive_down`. Spot-check on `64018.nc`: 11,527 of 11,639
records have masked depth (99 % nc tracks are bath+gravity composites;
gravity sub-intervals leave depth NaN).

This is **expected**, not a defect. Downstream Step 04+ aggregation
will filter on `point_check_pass_basic == True` (which excludes
NaN-depth rows) before any per-cell rollup. The point-check parquets
preserve every row so the audit trail keeps the gravity-side rows
available for the parallel gravity pipeline (PRD Locked decision #10,
dual-consumption).

The 11.55M `n_invalid_depth_pos` total is the NaN-depth set
(10.55M) plus a residual ~1.0M rows with finite depth ≤ 0 (likely
zero-depth sentinel rows or sign-flip anomalies in nc files — worth a
look in a future PR, not load-bearing for Step 04).

### 3c. Tracks with `n_invalid_lon > 0`

Total: 44 tracks (18 nc-sb + 26 xyz-sb). Top 10 by `n_invalid_lon`:

| track_id | source_type | n_invalid_lon | n_points_in |
| --- | --- | --- | --- |
| pol6829 | ncei_xyz | 42 | 18,470 |
| cmapsu7e | ncei_xyz | 31 | 3,624 |
| hc9104 | ncei_nc | 10 | 11,691 |
| scicex95 | ncei_xyz | 10 | 367,758 |
| cmapsu4s | ncei_nc | 9 | 13,477 |
| v2006 | ncei_nc | 8 | 3,704 |
| cmapsu5a | ncei_nc | 6 | 2,852 |
| di9402 | ncei_xyz | 5 | 26,724 |
| scicex99 | ncei_xyz | 5 | 351,595 |
| elt27 | ncei_xyz | 2 | 11,313 |

Counts are tiny relative to track size (<0.3% in all cases) — isolated
outliers, not systemic file corruption.

## 4. Top tracks with most failed-check points (per priority bucket)

### primary

| track_id | source_type | n_points_in | n_points_pass | n_failed |
| --- | --- | --- | --- | --- |
| p193ar | ncei_nc | 268635 | 11543 | 257092 |
| f-9-90-cp | ncei_nc | 158450 | 5592 | 152858 |
| cd37_889 | ncei_nc | 123618 | 28377 | 95241 |
| mw9603 | ncei_nc | 115050 | 32430 | 82620 |
| ka75018b | ncei_nc | 169532 | 89209 | 80323 |
| kk830802 | ncei_nc | 89513 | 14345 | 75168 |
| 84002113 | ncei_nc | 85500 | 12790 | 72710 |
| va16 | ncei_nc | 76988 | 6032 | 70956 |
| hu74026m | ncei_nc | 85530 | 19604 | 65926 |
| 84002112 | ncei_nc | 73935 | 14991 | 58944 |
| l784sp | ncei_nc | 67464 | 9442 | 58022 |
| nbp92-8 | ncei_nc | 67397 | 11078 | 56319 |
| rc2806 | ncei_nc | 91630 | 36374 | 55256 |
| nbp93-1 | ncei_nc | 63425 | 9872 | 53553 |
| mw9006 | ncei_nc | 83387 | 30258 | 53129 |
| mw9204 | ncei_nc | 88213 | 35339 | 52874 |
| f-10-89-cp | ncei_nc | 53637 | 1413 | 52224 |
| g175eg | ncei_nc | 67722 | 15511 | 52211 |
| mw8710 | ncei_nc | 94534 | 42637 | 51897 |
| sojn02mv | ncei_nc | 61779 | 10019 | 51760 |

### regional

| track_id | source_type | n_points_in | n_points_pass | n_failed |
| --- | --- | --- | --- | --- |
| mrar_0-180E-0-85N.txt | mrar_zhoushuai | 38590851 | 38590538 | 313 |
| mrar_0-90W-0-85S.txt | mrar_zhoushuai | 25286616 | 25286616 | 0 |
| mrar_90-180W-0-85S.txt | mrar_zhoushuai | 49479115 | 49479115 | 0 |

## 5. Depth anomaly tracks (depth_anomaly_flag = True)

Total flagged: 16

| track_id | source_type | source_priority | instrument_class_pred | depth_anomaly_flag |
| --- | --- | --- | --- | --- |
| 91039 | ncei_nc | primary | singlebeam | True |
| so16 | ncei_nc | primary | singlebeam | True |
| so49 | ncei_nc | primary | singlebeam | True |
| mv0902 | ncei_xyz | primary | singlebeam | True |
| rr1106 | ncei_xyz | primary | singlebeam | True |
| rr1108 | ncei_xyz | primary | singlebeam | True |
| rr1109 | ncei_xyz | primary | singlebeam | True |
| rr1110 | ncei_xyz | primary | singlebeam | True |
| rr1112 | ncei_xyz | primary | singlebeam | True |
| wi343802 | ncei_xyz | primary | singlebeam | True |
| 91039 | ncei_xyz | supplementary | singlebeam | True |
| ant4 | ncei_xyz | supplementary | singlebeam | True |
| ant8 | ncei_xyz | supplementary | singlebeam | True |
| so16 | ncei_xyz | supplementary | singlebeam | True |
| so36 | ncei_xyz | supplementary | singlebeam | True |
| so49 | ncei_xyz | supplementary | singlebeam | True |

## 6. Acceptance checks

| check | observed | expected | ok |
| --- | --- | --- | --- |
| primary xyz with completeness=nc_xyz_intersect (must be 0) | 0 | 0 | True |
| supplementary count (must be 1,850) | 1850 | 1850 | True |
| primary with completeness=xyz_only (must be 3,532) | 3532 | 3532 | True |
| skip with skip_reason='no_usable_depth' (must be 168) | 168 | 168 | True |

## 7. Output paths

| kind | path |
| --- | --- |
| bathymetry entry manifest (parquet) | ncei/manifests/bathymetry_entry_manifest.parquet |
| bathymetry entry manifest (tsv) | ncei/manifests/bathymetry_entry_manifest.tsv |
| report (this file) | ncei/docs/step03_point_quality_check_report.md |
| primary sb points_checked dir | ncei/derived/singlebeam/points_checked |
| primary mb points_checked dir | ncei/derived/multibeam/points_checked |
| regional M.rar points_checked dir | ncei/derived/regional_mrar/points_checked |
