# Step 10 SB per-track quality disposition and rejection-arm controls

Generated: 2026-09-02T20:10:19Z  
Script: `ncei/code/28_sb_track_quality_disposition_1min.py` (run from repo root)  
Interpreter: `/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python`  
Task: `.trellis/tasks/09-03-sb-track-quality-rejection/prd.md`

## Predeclared rule, as applied

Per region, step23 corrections are applied first and post-correction
crossover consistency is judged with the step09 crossover events
(`diff_m = depth_second - depth_first`; a track's residual at a
crossing is its own depth minus the partner's). Post-correction
residual of track t against partner p is `residual_t - bias_t +
bias_p`, bias = step23 `estimated_bias_m` (0 when not applied or the
partner has no step23 row in the region). Dispositions, in
precedence order:

1. `reject` (hard QC): backward nc time steps (full-track monotonicity
   QC from `nc_time_qc.parquet`) or zero valid depth cells (zero rows
   in `file_cells_1min` inside the region tile).
2. `flag_large_unapplied_bias` (elt18 pattern): step23 gate refused
   (`not_significant`) but the crossovers agree — |candidate bias| >=
   200 m, n_crossovers >= 10, crossover
   median signed diff same sign and |.| >= 200 m. Not
   corrected, not rejected; reserved for the second-round decision.
3. `reject` (misfit): n_crossovers >= 10 AND post-correction
   median |crossover diff| > 3 x regional crossover NMAD.
   Regional crossover NMAD = 1.4826 x MAD of the region's raw crossover
   `diff_m` values over all events. PRD clause (c) collapses into this
   test: a correction that fails to bring the track below the
   threshold leaves post > threshold; the n >= 10 evidence floor
   applies to both clauses because absence of evidence is not
   rejection.
4. `revert_to_raw`: step23 applied and post-correction misfit is worse
   than the raw misfit.
5. `correct`: step23 applied and the misfit improves or stays low.
6. `keep_raw`: everything else, including all tracks with too few
   crossovers to judge.

Rejection-arm control tables (`controls_mb_sb_reject_<tile>.parquet`):
MB rows copied unchanged from the adjusted tables (asserted identical
to the mb_only tables); SB cells rebuilt from per-track training-block
cells with dispositions applied — `correct` tracks at step23-adjusted
depths, `revert_to_raw` / `keep_raw` / `flag_large_unapplied_bias`
tracks at raw depths, rejected tracks dropped entirely; the cell value
is the median of the remaining per-track cell medians (step08
file-balanced rule). The rebuild reproduces the stored adjusted-arm SB
cells exactly (asserted), and SB rows carry `singlebeam_dispositioned`.

## Regional crossover NMAD and thresholds

| region | events | crossover NMAD (m) | 3x threshold (m) |
| --- | ---: | ---: | ---: |
| lon068_lat018 | 1276 | 25.93 | 77.80 |
| lon052_lat018 | 1286 | 5.36 | 16.09 |
| lon058_lat012 | 2575 | 31.93 | 95.78 |
| lon059_lat015 | 1006 | 73.02 | 219.05 |
| lon004_lat033 | 1860 | 34.43 | 103.29 |
| lon021_lat010 | 4826 | 94.78 | 284.33 |

## Disposition counts per region

| region | tracks | reject | flag_large_unapplied_bias | revert_to_raw | correct | keep_raw |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| lon068_lat018 | 37 | 4 | 0 | 6 | 3 | 24 |
| lon052_lat018 | 43 | 4 | 0 | 1 | 2 | 36 |
| lon058_lat012 | 44 | 8 | 0 | 0 | 1 | 35 |
| lon059_lat015 | 52 | 3 | 0 | 1 | 4 | 44 |
| lon004_lat033 | 14 | 7 | 0 | 0 | 0 | 7 |
| lon021_lat010 | 57 | 2 | 2 | 0 | 0 | 53 |
| all six | 247 | 28 | 2 | 8 | 10 | 199 |

## Rejected tracks

Hard QC (`reason = backward_time_steps`; full-track nc time QC):

| region | track | in step23 | n crossovers | raw median \|diff\| (m) | post median \|diff\| (m) | backward steps |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| lon068_lat018 | kh6705 | True | 30 | 18.53 | 10.25 | 1 |
| lon058_lat012 | dme10 | True | 118 | 168.56 | 286.61 | 1 |
| lon058_lat012 | ew0113 | True | 207 | 9.22 | 10.44 | 814 |
| lon058_lat012 | rc2707 | False | 1 | 5507.52 | 5507.52 | 485 |
| lon059_lat015 | v2009 | True | 62 | 16.03 | 30.31 | 1 |

Hard QC (`reason = zero_valid_depth_cells`; zero `file_cells_1min` rows
inside the tile; `n_in_tile_points = 0` marks tracks whose points only
graze the audit margin):

| region | track | in step23 | n in-tile points | n crossovers |
| --- | --- | --- | ---: | ---: |
| lon068_lat018 | 76010303 | False | 0 | 0 |
| lon068_lat018 | 87001511 | False | 0 | 0 |
| lon068_lat018 | v1907 | False | 0 | 0 |
| lon058_lat012 | rc0909 | False | 0 | 0 |
| lon059_lat015 | va16 | False | 3865 | 0 |

Misfit (`reason = post_correction_misfit_above_3x_region_nmad`):

| region | track | n crossovers | raw median \|diff\| (m) | post median \|diff\| (m) | threshold (m) | step23 bias (m) | applied |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| lon052_lat018 | circ05ar | 40 | 23.89 | 23.89 | 16.09 | 0.00 | False |
| lon052_lat018 | kh7605 | 48 | 16.30 | 16.30 | 16.09 | 0.00 | False |
| lon052_lat018 | so127 | 19 | 19.00 | 19.00 | 16.09 | 0.00 | False |
| lon052_lat018 | vit31b | 28 | 34.99 | 35.15 | 16.09 | 0.00 | False |
| lon058_lat012 | antac7 | 54 | 143.76 | 143.76 | 95.78 | 0.00 | False |
| lon058_lat012 | um69 | 77 | 94.51 | 135.14 | 95.78 | -138.50 | True |
| lon058_lat012 | v1811 | 50 | 313.62 | 211.27 | 95.78 | -102.35 | True |
| lon058_lat012 | vit31a | 107 | 152.26 | 152.26 | 95.78 | 0.00 | False |
| lon059_lat015 | jare32l1 | 43 | 240.86 | 240.86 | 219.05 | 0.00 | False |
| lon004_lat033 | he0302 | 25 | 161.41 | 161.41 | 103.29 | 0.00 | False |
| lon004_lat033 | hly0602 | 42 | 295.38 | 295.38 | 103.29 | 0.00 | False |
| lon004_lat033 | p193ar | 100 | 77.60 | 107.08 | 103.29 | -35.40 | True |
| lon004_lat033 | scicex97 | 99 | 147.88 | 147.88 | 103.29 | 0.00 | False |
| lon004_lat033 | sub6672b | 29 | 75.79 | 111.19 | 103.29 | 0.00 | False |
| lon004_lat033 | sub7382h | 277 | 272.59 | 274.59 | 103.29 | 0.00 | False |
| lon004_lat033 | sub9300b | 11 | 109.96 | 109.96 | 103.29 | 0.00 | False |
| lon021_lat010 | elt24 | 57 | 759.59 | 664.88 | 284.33 | 937.10 | True |
| lon021_lat010 | nbp0203 | 194 | 763.07 | 763.07 | 284.33 | 0.00 | False |

## Cells lost to rejection

| region | SB cells (adjusted) | SB cells (reject arm) | SB cells lost | lost, MB-covered | lost, SB-only | track-cell rows dropped | MB rows | rows (adjusted) | rows (reject arm) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lon068_lat018 | 4181 | 4104 | 77 | 7 | 70 | 81 | 2148 | 6329 | 6252 |
| lon052_lat018 | 7313 | 6851 | 462 | 0 | 462 | 545 | 1538 | 8851 | 8389 |
| lon058_lat012 | 8207 | 7697 | 510 | 14 | 496 | 778 | 1781 | 9988 | 9478 |
| lon059_lat015 | 6306 | 6226 | 80 | 11 | 69 | 143 | 7088 | 13394 | 13314 |
| lon004_lat033 | 7112 | 4348 | 2764 | 43 | 2721 | 3038 | 1051 | 8163 | 5399 |
| lon021_lat010 | 8098 | 7944 | 154 | 1 | 153 | 242 | 938 | 9036 | 8882 |

| all six | 41217 | 37170 | 4047 | 76 | 3971 | 4827 | 14544 | 55761 | 51714 |

MB rows are identical to the adjusted tables in every region (asserted
against the mb_only tables). Rejected tracks with zero training cells
contribute no control rows, so their rejection is recorded in the
quality tables only.

## Named tracks

| region | track | disposition | reason | n crossovers | raw median \|diff\| (m) | post median \|diff\| (m) | threshold (m) | step23 candidate (m) | applied | crossover median signed (m) |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| lon068_lat018 | odp130jr | revert_to_raw | applied_but_post_worse_than_raw | 141 | 3.91 | 44.42 | 77.80 | -44.00 | True | 0.02 |
| lon021_lat010 | elt18 | flag_large_unapplied_bias | large_refused_bias_crossover_consistent | 75 | 1032.77 | 1032.77 | 284.33 | -1247.20 | False | -965.06 |
| lon021_lat010 | elt19 | flag_large_unapplied_bias | large_refused_bias_crossover_consistent | 40 | 295.53 | 295.53 | 284.33 | -307.15 | False | -275.71 |

odp130jr: step23 applied -44.00 m; its 141 crossovers sit near zero raw
(median |diff| ~3.9 m) and the correction pushes the median to ~44 m.
Post-correction misfit is worse than raw, so the track reverts to raw.

elt18: step23 refused the -1247 m candidate (`not_significant`); its 75
crossovers show a consistent -965 m median offset, above the 284 m
regional threshold. It is flagged for the second-round decision, not
corrected and not rejected.

elt19 matches the same operationalized pattern (refused -307 m
candidate, crossover median -276 m over 40 events) and is flagged
with it. The sign-flipping/high-variance refused tracks the step09
consistency check distinguished (e.g. elt06, nbp0203 in lon021_lat010)
fail the sign/magnitude consistency clause and are not flagged;
nbp0203 is rejected by the misfit rule instead.

## Deviations from the PRD tallies

- The PRD expected `3 backward-time` and `7 zero-cell` rejected tracks. The literal hard-QC criteria over this universe reject 5 backward-time tracks (dme10, ew0113, kh6705, rc2707, v2009) and 6 zero-cell tracks (76010303, 87001511, rc0909, rc2707, v1907, va16); rc2707 trips both. The step09 report's per-region monotonicity counts (1 in lon068, 3 in lon058, 1 in lon059) already sum to 5 region-tracks, so the PRD's 3 cannot be recovered by any intersection with the six-region track sets checked here; the predeclared rule (any backward time step) rejects all of them.
- No reading of `zero valid depth cells` yields exactly 7 Eltanin/Conrad tracks: zero `file_cells_1min` rows inside the tile gives 6 tracks (2 Eltanin/Conrad); zero step23 colocated cells gives 8 Eltanin/Conrad region-rows (7 unique tracks), but those tracks have 13-577 region cells each and are not `zero-cell` in any literal sense. The literal cell-product criterion was applied.

## Output files

```text
ncei/derived/sb_track_quality_1min/
  track_quality_<region>.parquet     one row per SB track per region
ncei/derived/sb_track_bias_1min/
  controls_mb_sb_reject_<region>.parquet
```

The quality-table universe per region is the step23 track set united
with every track the step09 crossover audit loaded (>= 2 points inside
the tile bbox + 0.05 deg margin). Every disposition is traceable to
the row's evidence fields (step23 columns, crossover misfits, QC
flags, threshold).

## Reproduction

```bash
cd /mnt/data2/00-Data/ship
/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python ncei/code/28_sb_track_quality_disposition_1min.py --overwrite
```
