# Step 10 report: interpolation-level singlebeam value test (GMT surface pseudo-outer holdout)

Run date: 2026-09-03. Script: `ncei/analysis/29_sb_interpolation_holdout.py`.
Outputs: `ncei/derived/sb_interpolation_holdout/` (per region × variant: `surface.nc`,
`gmt_log.json`, `predictions.parquet`; plus `result_table.{json,csv}` and `run_manifest.json`).

## Question and design

Does adding singlebeam (SB) points improve PLAIN INTERPOLATION of held-out multibeam
depths, independent of the neural pipeline? Per frozen region: grid the inner-training
control points of the non-holdout (training-pool) blocks with GMT `surface` at 1 arcmin,
sample at the pseudo-outer holdout cell centers with `grdtrack` (nearest), and score with
the same block-equal RMSE formulas as the downstream neural pseudo-outer run
(20260902T175753Z). Holdout blocks, training-pool blocks, and holdout cell counts are
imported verbatim from that run's `pseudo_outer_selection.json`; the truth depths are the
same strict-cell `representative_depth_m` values (max |truth − control-table depth| = 0
across all six regions). Inner-validation and outer-evaluation depths were never opened
(the control tables themselves contain only inner-training cells, verified by block color).

## GMT settings (identical to the downstream GGM stage contract)

- Executable `/opt/miniforge3/envs/torch27/bin/gmt`, GMT 6.5.0.
- `gmt surface controls.xyz -G<out> -R<w>/<e>/<s>/<n> -I0.0166666666667 -rp -fg -Am -T0.25 -Vw`,
  timeout 600 s per call, run in a scratch directory. Full commands in each `gmt_log.json`.
- Sampling: `gmt grdtrack holdout.xy -G<surface.nc> -nn` (nearest neighbor); holdout cell
  centers coincide with pixel-registered grid nodes.
- Duplicate rule: exact-coordinate controls replaced by their arithmetic mean before
  `surface` (the GMT surface contract requires unique coordinates). MB-only pools had zero
  duplicates; SB pools had 10–314 duplicate groups per run (counts in the manifest).
- No masking beyond tile bounds; one global setting set for all tiles (no per-tile tuning).
  All 18 surface runs converged.

## Three-variant table, block-equal RMSE (m)

Same holdout blocks, cells, and metric formulas as the neural pseudo-outer run, so rows
compare directly.

| Region | Cells | Blocks | GMT mb_only | GMT mb_sb_adjusted | GMT mb_sb_reject | Neural mb_only | Neural mb_sb_adjusted |
|---|---:|---:|---:|---:|---:|---:|---:|
| lon068_lat018 | 1637 | 3 | 224.53 | 256.02 | 262.11 | 299.15 | 136.67 |
| lon052_lat018 | 1485 | 2 | 226.42 | 560.87 | 570.57 | 48.18 | 69.90 |
| lon058_lat012 | 1547 | 3 | 439.37 | 371.49 | 371.63 | 88.06 | 185.10 |
| lon059_lat015 | 3190 | 3 | 695.30 | 743.58 | 744.05 | 105.50 | 128.62 |
| lon004_lat033 | 1003 | 2 | 1937.15 | 821.45 | 414.43 | 156.33 | 162.59 |
| lon021_lat010 | 747 | 3 | 3975.25 | 1208.87 | 1208.87 | 202.50 | 254.85 |
| **Pooled (6-region equal-weight)** | | | **1840.89** | **731.12** | **673.19** | **171.34** | **166.21** |

Pairwise deltas vs mb_only (GMT runs): lon068 +31.5 (adjusted) / +37.6 (reject);
lon052 +334.4 / +344.2; lon058 −67.9 / −67.7; lon059 +48.3 / +48.8; lon004 −1115.7 /
−1522.7; lon021 −2766.4 / −2766.4; pooled −1109.8 / −1167.7.

## Where GMT behaved badly

No convergence failures and no per-tile setting changes, but `surface` extrapolates
without bounds in data voids, and two tiles sit next to large voids:

- lon021_lat010: mb-only grid spans −25.4 km to +9.7 km against a control range of
  0.4–2.0 km; predictions at holdout centers reach −6083 m (negative depths). SB arms:
  −23.8 km to +8.6 km. This void extrapolation, not local misfit, produces the 3975 m
  mb-only RMSE (block biases −5868 / −3167 / −850 m).
- lon004_lat033: SB-arm grids undershoot to −11.9 km (adjusted) / −10.4 km (reject)
  against control minima of 0.14 km, and cross zero inside the tile.
- lon058_lat012: all three grids cross zero (mb-only −3971 m; SB arms ≈ −9.4 km to
  +13.0 km vs control range 0.05–5.3 km).
- lon052_lat018: SB-arm grids overshoot the control range by about ±1 km.
- lon068_lat018 and lon059_lat015 grids stay within the control range (±0.5 km
  tolerance); their errors are local misfit, not void extrapolation.

This is expected behavior of unmasked `surface` with sparse controls and is part of the
comparison being tested (the neural runs see the same voids but have gravity input).

Two data facts worth recording: in lon021_lat010 the adjusted and dispositioned SB rows
covering the training-pool blocks are identical (1925 cells, identical depths), so the two
SB variants produce bit-identical grids there. In lon004_lat033 the dispositioned arm
retains far fewer SB cells than the adjusted arm (156 vs 586 in the training pool), which
is the only tile where the reject variant clearly beats the adjusted variant.

## Verdict on the data-value question

At the interpolation level, adding SB improves the pooled block-equal RMSE from 1841 m to
731 m (adjusted) / 673 m (reject). The gain is dominated by the two tiles whose mb-only
training pool is tiny (lon004: 48 cells, lon021: 191 cells), where SB is the only real
constraint; in the dense-MB tiles the effect is small and mixed (helps lon058 by 68 m,
hurts lon068/lon052/lon059 by 31–344 m). So the SB points carry genuine depth information
that even a plain interpolator exploits: the data is not the reason the neural pipeline
regressed. The neural runs remain far better than plain interpolation almost everywhere
(only exception: lon068, where GMT mb-only at 225 m beats the neural mb-only 299 m), which
confirms the neural advantage comes from gravity inputs, and the earlier five-region-style
regression when adding SB is a pipeline problem, not a data problem.

Per region, the direction of the SB effect does not agree between the two tests (e.g.
lon052: GMT +334 m vs neural +22 m; lon068: GMT +32 m vs neural −163 m; lon004: GMT
−1116 m vs neural +6 m), so per-region neural deltas should not be explained by SB data
content alone.
