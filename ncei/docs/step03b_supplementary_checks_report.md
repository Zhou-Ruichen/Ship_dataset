# NCEI Step 03B — Supplementary Quality Check Report

Generated: 2026-05-20T11:46:33.012549+00:00
Run label: `full`
Check version: `supp_check_v0.1.0`
Elapsed: 293.7s
Entries in supplementary manifest: 7,403
Entries supplementary-checked this run: 5,385
Intersect pairs in divergence audit: 1,850
Errors: 0

Check C jump threshold: `1000 m` (module constant)

## A. Finite-but-≤0 depth attribution

| total_n_depth_eq_zero | total_n_depth_negative_finite |
| --- | --- |
| 995871 | 0 |

### A1. By source_type

| source_type | entries | n_depth_eq_zero | n_depth_negative_finite |
| --- | --- | --- | --- |
| mrar_zhoushuai | 3 | 313 | 0 |
| ncei_nc | 1850 | 992662 | 0 |
| ncei_xyz | 3532 | 2896 | 0 |

### A2. Top-20 tracks by n_depth_eq_zero

| track_id | source_type | n_points_in | n_depth_eq_zero |
| --- | --- | --- | --- |
| p193ar | ncei_nc | 268635 | 122964 |
| kk830802 | ncei_nc | 89513 | 50153 |
| f-9-90-cp | ncei_nc | 158450 | 37783 |
| f-10-89-cp | ncei_nc | 53637 | 27467 |
| west10mv | ncei_nc | 61614 | 26528 |
| rc2502 | ncei_nc | 44623 | 22624 |
| rc2806 | ncei_nc | 91630 | 19098 |
| mrtn09wt | ncei_nc | 32580 | 18639 |
| cntl12rr | ncei_nc | 21110 | 18443 |
| krus01rr | ncei_nc | 32873 | 16038 |
| mrtn08wt | ncei_nc | 30506 | 14774 |
| rc2603 | ncei_nc | 33869 | 13205 |
| s677bs | ncei_nc | 43301 | 12552 |
| p385cb | ncei_nc | 18339 | 11978 |
| l284an | ncei_nc | 48919 | 11396 |
| re9302 | ncei_nc | 30593 | 11319 |
| l478bs | ncei_nc | 32693 | 10860 |
| di134 | ncei_nc | 17825 | 10065 |
| s979wg | ncei_nc | 18768 | 9716 |
| mw8712 | ncei_nc | 63091 | 9286 |

### A3. Top-20 tracks by n_depth_negative_finite

| track_id | source_type | n_points_in | n_depth_negative_finite |
| --- | --- | --- | --- |
| 64018 | ncei_nc | 11639 | 0 |
| 64019 | ncei_nc | 12197 | 0 |
| 64027 | ncei_nc | 7926 | 0 |
| 68101200 | ncei_nc | 18836 | 0 |
| 69005611 | ncei_nc | 9638 | 0 |
| 69005621 | ncei_nc | 5247 | 0 |
| 69005631 | ncei_nc | 5636 | 0 |
| 69005641 | ncei_nc | 3493 | 0 |
| 69005651 | ncei_nc | 3583 | 0 |
| 69006011 | ncei_nc | 1775 | 0 |
| 69006111 | ncei_nc | 1389 | 0 |
| 69006211 | ncei_nc | 1056 | 0 |
| 70005511 | ncei_nc | 9413 | 0 |
| 70005611 | ncei_nc | 6242 | 0 |
| 70005711 | ncei_nc | 9446 | 0 |
| 70005811 | ncei_nc | 4158 | 0 |
| 70006311 | ncei_nc | 5570 | 0 |
| 70006411 | ncei_nc | 3179 | 0 |
| 70006511 | ncei_nc | 4605 | 0 |
| 70042201 | ncei_nc | 16543 | 0 |

## B. Within-track exact-triple duplicates

| total_n_duplicate_points | total_n_unique_triples | tracks_with_any_dup | tracks_processed |
| --- | --- | --- | --- |
| 6158685 | 233990750 | 1921 | 5385 |

### B1. By source_type

| source_type | entries | n_duplicate_points | n_unique_triples |
| --- | --- | --- | --- |
| mrar_zhoushuai | 3 | 591345 | 112765237 |
| ncei_nc | 1850 | 570316 | 35271442 |
| ncei_xyz | 3532 | 4997024 | 85954071 |

### B2. Top-20 tracks by n_duplicate_points

| track_id | source_type | n_points_in | n_duplicate_points | n_unique_triples |
| --- | --- | --- | --- | --- |
| mrar_90-180W-0-85S.txt | mrar_zhoushuai | 49479115 | 591345 | 48887770 |
| sentry421 | ncei_xyz | 2986580 | 585458 | 2401122 |
| sentry426 | ncei_xyz | 2842137 | 533789 | 2308348 |
| sentry420 | ncei_xyz | 2700654 | 523890 | 2176764 |
| sentry423 | ncei_xyz | 1548425 | 507679 | 1040746 |
| sentry424 | ncei_xyz | 2892350 | 454420 | 2437930 |
| sentry419 | ncei_xyz | 2610931 | 453341 | 2157590 |
| sentry418 | ncei_xyz | 2286087 | 436066 | 1850021 |
| sentry422 | ncei_xyz | 2925767 | 429614 | 2496153 |
| sentry428 | ncei_xyz | 2924587 | 397024 | 2527563 |
| sentry427 | ncei_xyz | 2687721 | 281724 | 2405997 |
| sbp1310 | ncei_xyz | 894604 | 49410 | 845194 |
| l784sp | ncei_nc | 67464 | 34682 | 32782 |
| jr361 | ncei_xyz | 67635 | 33422 | 34213 |
| drft05rr | ncei_nc | 47314 | 25183 | 22131 |
| ab1999 | ncei_xyz | 109967 | 24448 | 85519 |
| ra188-16 | ncei_xyz | 860154 | 19221 | 840933 |
| avon07mv | ncei_nc | 31476 | 19209 | 12267 |
| lprs02rr | ncei_nc | 44635 | 19082 | 25553 |
| lfex01mv | ncei_nc | 43496 | 18084 | 25412 |

## C. Within-track depth jump candidates
Threshold: |Δdepth| > 1000 m between consecutive points
(mrar regional is skipped — rows not along-track ordered)

| total_n_depth_jump_candidates | tracks_with_jumps | tracks_checked_for_jumps |
| --- | --- | --- |
| 505886 | 3285 | 5382 |

### C1. Top-20 tracks by n_depth_jump_candidates

| track_id | source_type | n_points_in | n_depth_jump_candidates |
| --- | --- | --- | --- |
| rc2502 | ncei_nc | 44623 | 29534 |
| rc2806 | ncei_nc | 91630 | 19054 |
| re9302 | ncei_nc | 30593 | 18999 |
| rc2709 | ncei_xyz | 96876 | 18707 |
| kk830802 | ncei_nc | 89513 | 17827 |
| p193ar | ncei_nc | 268635 | 12317 |
| ew9608 | ncei_nc | 94040 | 11959 |
| hly0602 | ncei_nc | 305134 | 9277 |
| rc2802 | ncei_nc | 76180 | 8420 |
| rc2511 | ncei_nc | 76403 | 7654 |
| rc2608 | ncei_nc | 66618 | 6370 |
| mw8712 | ncei_nc | 63091 | 5974 |
| f-9-90-cp | ncei_nc | 158450 | 5223 |
| rc2508 | ncei_xyz | 28590 | 5184 |
| mw8702 | ncei_nc | 52690 | 4576 |
| rc2308 | ncei_nc | 10177 | 3898 |
| rc2610 | ncei_nc | 42210 | 3808 |
| m14 | ncei_nc | 176702 | 3629 |
| rr0903 | ncei_xyz | 380102 | 3206 |
| rc2707 | ncei_nc | 16939 | 3190 |

## D. Intersect dual-submission divergence

| pairs_scanned | divergent_flag_true | divergent_pct |
| --- | --- | --- |
| 1850.000 | 96.000 | 5.190 |

### D1. Top-20 most-divergent pairs (smallest bbox_overlap_jaccard)

| track_id | n_valid_nc | n_valid_xyz | valid_count_ratio | bbox_overlap_jaccard | depth_med_nc | depth_med_xyz | depth_med_ratio | divergent_flag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hs8102 | 4637 | 4637 | 1.000 | 0.000 | 786.000 | 786.000 | 1.000 | True |
| f-10-89-cp | 1413 | 1413 | 1.000 | 0.000 | 1958.300 | 1958.300 | 1.000 | True |
| hs7501 | 3575 | 3576 | 1.000 | 0.000 | 781.000 | 781.500 | 0.999 | True |
| 89001011 | 262 | 262 | 1.000 | 0.001 | 4867.000 | 4867.000 | 1.000 | True |
| ht99t414 | 4 | 4 | 1.000 | 0.001 | 1085.000 | 1085.000 | 1.000 | True |
| kea09-69 | 26 | 26 | 1.000 | 0.001 | 923.000 | 923.000 | 1.000 | True |
| 64018 | 112 | 113 | 0.991 | 0.004 | 170.950 | 170.000 | 1.006 | True |
| l1380np | 3023 | 3023 | 1.000 | 0.018 | 5524.000 | 5524.000 | 1.000 | True |
| hs8203 | 3998 | 3999 | 1.000 | 0.020 | 831.000 | 831.000 | 1.000 | True |
| tuim04mv | 1435 | 1435 | 1.000 | 0.021 | 5504.000 | 5504.000 | 1.000 | True |
| 80101002 | 463 | 463 | 1.000 | 0.041 | 1290.000 | 1290.000 | 1.000 | True |
| l184an | 15985 | 15985 | 1.000 | 0.048 | 2872.200 | 2872.200 | 1.000 | True |
| hs7604 | 1450 | 1451 | 0.999 | 0.049 | 2550.000 | 2550.000 | 1.000 | True |
| sojn02mv | 10019 | 10019 | 1.000 | 0.050 | 3248.000 | 3248.000 | 1.000 | True |
| kea01-69 | 267 | 268 | 0.996 | 0.055 | 49.000 | 49.000 | 1.000 | True |
| hu66019m | 11285 | 11285 | 1.000 | 0.069 | 2505.400 | 2505.400 | 1.000 | True |
| a2049 | 3485 | 3485 | 1.000 | 0.069 | 1906.000 | 1906.000 | 1.000 | True |
| aku30b | 185 | 185 | 1.000 | 0.075 | 2530.000 | 2530.000 | 1.000 | True |
| aku31 | 265 | 265 | 1.000 | 0.077 | 3101.000 | 3101.000 | 1.000 | True |
| nv9704mv | 1066 | 1066 | 1.000 | 0.078 | 1032.000 | 1032.000 | 1.000 | True |

### D2. Divergence rule summary

- count: valid_count_ratio outside [0.5, 2.0]
- bbox:  bbox_overlap_jaccard < 0.50
- depth: depth_med_ratio outside [0.5, 2.0]

### D3. Interpretation — all 96 divergent_flag=True are bbox-only

Across all 1,850 intersect pairs, the count and depth-median criteria
agree on 1,850/1,850 — every flag is driven by `bbox_overlap_jaccard <
0.5` alone. The nc-side bbox in this audit is sourced from
`singlebeam_points_raw_manifest.parquet`, which records the bbox of
**all raw nc rows** (including NaN-depth / gravity-only segments per
Step 03A §3b and PRD Finding 19c [2026-05-20 correction]). The xyz-side
bbox is the bbox of finite-depth-only rows (xyz drops no-depth rows at
upstream export). When an nc track carries gravity-only segments that
extend far beyond the bathymetry region (e.g. `hs8102` nc-raw bbox
spans 0–171° lon, 3.6–88° lat, while its finite-depth subset and the
matching xyz both sit in a 1.9°×1.0° box near 130° E / 29° N), the
bbox Jaccard collapses toward 0 even though the bathymetry agrees
exactly (`n_valid_nc == n_valid_xyz`, `depth_med_nc ≈ depth_med_xyz`).

→ The 96 flagged pairs are **bbox-shape artifacts, not bathymetry
disagreements**. They reinforce — rather than contradict — the
"prefer nc on intersect" rule in PRD Finding 19c (2026-05-20
correction). A future Step 03B revision could compute the nc-side
bbox over `point_check_pass_basic=True` rows to remove this artifact;
the current bbox-of-all-rows behavior is preserved for
backward-compatibility with the `singlebeam_points_raw_manifest`
bbox semantics.

## Comparison vs Step 03A

Step 03B does not modify or invalidate any Step 03A flag (point_check_pass_basic and the 5 underlying boolean columns are preserved unchanged on every points_checked parquet).

Refinements layered on top of Step 03A's results:

- Check A attributes Step 03A's `n_invalid_depth_pos` aggregate: the finite-but-≤0 share is split into exact-zero (likely upstream sentinel) vs. negative-finite (likely sign-flip / unit error). NaN-depth rows (the bulk of `n_invalid_depth_pos` on the nc-sb leg per Step 03A §3b) are excluded from both A counts by construction.

- Check B is orthogonal to Step 03A — exact-triple duplicates pass every basic flag but represent a per-cell aggregation concern (double-counting at Step 04).

- Check C is orthogonal to Step 03A — jump candidates may all pass `point_check_pass_basic` individually but flag tracks that warrant per-track review before being treated as primary cell-aggregation input.

- Check D quantifies the nc-vs-xyz intersect agreement that PRD Finding 19c (2026-05-20 correction) established as the basis for the 'prefer nc on intersect' rule.

## Recommendation for Step 04 cell aggregation

Step 03B emits flags only. Step 04's cell aggregation should consume the supplementary manifest as a per-track filtering hint, NOT as a hard drop rule: (i) tracks with `n_depth_jump_candidates > 0` warrant per-cell IQR review (the 1-arcmin file-balanced median is already robust to a few jump candidates, but deep-volcanic / trench-wall tracks may legitimately flag many); (ii) tracks with high `n_duplicate_points` density should NOT be treated as having more independent soundings than `n_unique_triples` for cell-weighted statistics; (iii) intersect-pair divergent_flag=True cases should default to nc-side per the existing PRD Finding 19c policy, but the audit row should be cross-checked when nc and xyz disagree on instrument-class implications (e.g., one suggests mb-density, the other sb-sparsity).

## Output paths

| kind | path |
| --- | --- |
| supplementary manifest (parquet) | ncei/manifests/bathymetry_entry_manifest_supplementary.parquet |
| supplementary manifest (tsv) | ncei/manifests/bathymetry_entry_manifest_supplementary.tsv |
| intersect divergence audit (parquet) | ncei/manifests/intersect_divergence_audit.parquet |
| intersect divergence audit (tsv) | ncei/manifests/intersect_divergence_audit.tsv |
| this report | ncei/docs/step03b_supplementary_checks_report.md |
