# NCEI Step 04A — Per-file 1-arcmin Cell Aggregation Report

Generated: 2026-05-20T18:02:55.778759+00:00
Run label: `full`
Aggregation version: `ncei_cells_v0.1.0`
Cell size: 1 arc-minute (1/60°)
Elapsed: 1257.6s
Inputs processed: 5,385
Errors: 0

## 1. Per-branch totals

| branch | files | cells | pass_points | unique_triples | avg_runtime_s | manual_review | overall_dup_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- |
| multibeam_ncei | 17 | 6329 | 37799943 | 33162175 | 1.6291 | 0 | 0.1227 |
| regional_mrar | 3 | 9019512 | 113356269 | 112764924 | 184.7883 | 0 | 0.0052 |
| singlebeam | 5365 | 17294849 | 77445882 | 77028749 | 0.1251 | 106 | 0.0054 |

## 2. Expected vs observed workload per branch

| branch | expected | observed | ok |
| --- | --- | --- | --- |
| singlebeam | 5365 | 5365 | True |
| multibeam_ncei | 17 | 17 | True |
| regional_mrar | 3 | 3 | True |

## 3. duplicate_ratio_overall distribution per branch

| branch | files | p0 | p25 | p50 | p75 | p90 | p99 | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| multibeam_ncei | 17 | 0.0000 | 0.0126 | 0.1468 | 0.1907 | 0.2065 | 0.3110 | 0.3279 |
| regional_mrar | 3 | 0.0000 | 0.0000 | 0.0000 | 0.0060 | 0.0096 | 0.0117 | 0.0120 |
| singlebeam | 5365 | 0.0000 | 0.0000 | 0.0000 | 0.0001 | 0.0023 | 0.0899 | 0.8795 |

## 4. manual_review_flag tracks (informational; not excluded)

Total flagged: 106

| track_id | branch | source_type | n_cells | n_points_pass_total | duplicate_ratio_overall |
| --- | --- | --- | --- | --- | --- |
| 64018 | singlebeam | ncei_nc | 40 | 112 | 0.0000 |
| 76010302 | singlebeam | ncei_nc | 3513 | 8705 | 0.0000 |
| 76029 | singlebeam | ncei_nc | 6341 | 16961 | 0.0000 |
| 78050400 | singlebeam | ncei_nc | 1976 | 4312 | 0.0000 |
| 80101002 | singlebeam | ncei_nc | 172 | 463 | 0.0000 |
| 84006411 | singlebeam | ncei_nc | 1252 | 5980 | 0.0000 |
| 85000611 | singlebeam | ncei_nc | 1309 | 6622 | 0.0000 |
| 85001511 | singlebeam | ncei_nc | 1696 | 6887 | 0.0000 |
| 88001511 | singlebeam | ncei_nc | 8324 | 22613 | 0.0000 |
| 88003111 | singlebeam | ncei_nc | 724 | 2922 | 0.0000 |
| 88003311 | singlebeam | ncei_nc | 364 | 1485 | 0.0000 |
| 89000911 | singlebeam | ncei_nc | 86 | 481 | 0.0000 |
| 89001011 | singlebeam | ncei_nc | 23 | 262 | 0.0000 |
| 91039 | singlebeam | ncei_nc | 9943 | 37513 | 0.0021 |
| a2049 | singlebeam | ncei_nc | 2715 | 3485 | 0.0063 |
| ai9101 | singlebeam | ncei_nc | 275 | 275 | 0.0000 |
| aku30b | singlebeam | ncei_nc | 185 | 185 | 0.0000 |
| aku31 | singlebeam | ncei_nc | 265 | 265 | 0.0000 |
| b174ar | singlebeam | ncei_nc | 87 | 180 | 0.0000 |
| ba68021m | singlebeam | ncei_nc | 12931 | 52294 | 0.0000 |
| ba79015m | singlebeam | ncei_nc | 7155 | 7989 | 0.0000 |
| bp7806 | singlebeam | ncei_nc | 553 | 580 | 0.0000 |
| bp7807 | singlebeam | ncei_nc | 423 | 442 | 0.0000 |
| bp7901 | singlebeam | ncei_nc | 249 | 951 | 0.0000 |
| bp7905 | singlebeam | ncei_nc | 172 | 693 | 0.0000 |
| cntl06rr | singlebeam | ncei_nc | 18 | 56 | 0.0000 |
| cook09mv | singlebeam | ncei_nc | 492 | 2549 | 0.0722 |
| cook13mv | singlebeam | ncei_nc | 32 | 113 | 0.0000 |
| core01mv | singlebeam | ncei_nc | 34 | 289 | 0.0242 |
| crgn04wt | singlebeam | ncei_nc | 751 | 4586 | 0.0000 |

## 5. Highest duplicate_ratio_overall files per branch (top 10)

### multibeam_ncei

| track_id | n_cells | n_points_pass_total | n_unique_triples_total | duplicate_ratio_overall |
| --- | --- | --- | --- | --- |
| sentry423 | 5 | 1548425 | 1040746 | 0.3279 |
| ab1999 | 158 | 109967 | 85519 | 0.2223 |
| sentry421 | 8 | 2986580 | 2401122 | 0.1960 |
| sentry420 | 9 | 2700654 | 2176764 | 0.1940 |
| sentry418 | 9 | 2286087 | 1850021 | 0.1907 |
| sentry426 | 8 | 2842137 | 2308348 | 0.1878 |
| sentry419 | 8 | 2610931 | 2157590 | 0.1736 |
| sentry424 | 8 | 2892350 | 2437930 | 0.1571 |
| sentry422 | 8 | 2925767 | 2496153 | 0.1468 |
| sentry428 | 10 | 2924587 | 2527563 | 0.1358 |

### regional_mrar

| track_id | n_cells | n_points_pass_total | n_unique_triples_total | duplicate_ratio_overall |
| --- | --- | --- | --- | --- |
| mrar_90-180W-0-85S.txt | 4125568 | 49479115 | 48887770 | 0.0120 |
| mrar_0-180E-0-85N.txt | 2598409 | 38590538 | 38590538 | 0.0000 |
| mrar_0-90W-0-85S.txt | 2295535 | 25286616 | 25286616 | 0.0000 |

### singlebeam

| track_id | n_cells | n_points_pass_total | n_unique_triples_total | duplicate_ratio_overall |
| --- | --- | --- | --- | --- |
| gh7405 | 139 | 1162 | 140 | 0.8795 |
| at27b | 1 | 1274 | 419 | 0.6711 |
| cntl08rr | 94 | 2744 | 1326 | 0.5168 |
| jr361 | 5970 | 67634 | 34212 | 0.4942 |
| 03575 | 57 | 287 | 146 | 0.4913 |
| tf89-90 | 834 | 1568 | 836 | 0.4668 |
| woce_p10 | 3232 | 39770 | 23841 | 0.4005 |
| 26869j | 1725 | 4862 | 3033 | 0.3762 |
| 03572 | 1167 | 2424 | 1553 | 0.3593 |
| at3l13 | 39 | 638 | 422 | 0.3386 |

## 6. Output paths

| kind | path |
| --- | --- |
| manifest (parquet) | ncei/manifests/file_cells_1min_manifest.parquet |
| manifest (tsv) | ncei/manifests/file_cells_1min_manifest.tsv |
| report (this file) | ncei/docs/step04a_file_cells_1min_report.md |
| singlebeam file_cells dir | ncei/derived/singlebeam/file_cells_1min |
| multibeam_ncei file_cells dir | ncei/derived/multibeam/file_cells_1min |
| regional_mrar file_cells dir | ncei/derived/regional_mrar/file_cells_1min |

## 7. References

- Design audit: `ncei/docs/step04_aggregation_design_audit.md`
- Step 03A output: `ncei/manifests/bathymetry_entry_manifest.parquet`
- Step 03B supplement: `ncei/manifests/bathymetry_entry_manifest_supplementary.parquet`
- Duplicate-triple convention: `pd.DataFrame({'lon','lat','depth'}).duplicated(keep='first')` with exact float equality — same as `06_supplementary_quality_check.py` Check B.
