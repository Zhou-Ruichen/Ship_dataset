# Interpolation-level SB value test: GMT surface holdout on six regions

mode: exploratory (data-level evaluation; no neural training; no locked
evaluation data)

## Decision this task must answer

Does adding singlebeam points improve PLAIN INTERPOLATION of held-out
multibeam depths, independent of the neural pipeline? This separates "is the
SB data useful" from "does the TUNet pipeline exploit it well". If SB helps
here but hurt in the neural runs, the earlier five-region regression is a
pipeline problem, not a data problem.

## Design (predeclared)

- Regions: the six frozen tiles. Truth: strict-MB depths of the SAME
  pseudo-outer holdout blocks used in the downstream run, listed in
  `/mnt/data2/06-Projects/15-swot_feature_physics_bathy/outputs/20260902T175753Z-nested-pseudo-outer-sb-nested_pseudo_outer_sb/pseudo_outer_selection.json`
  (read-only import). Holdout blocks are inner_training role; reading their
  depths as evaluation truth is permitted. Do NOT read inner_validation or
  outer_evaluation depths.
- Training points come from the remaining inner_training blocks only, per
  variant:
  1. `mb_only`: strict-MB cell depths.
  2. `mb_sb_adjusted`: plus adjusted-SB cells from
     `ncei/derived/sb_track_bias_1min/controls_mb_sb_adjusted_<tile>.parquet`
     (rows with control_source `singlebeam_adjusted`).
  3. `mb_sb_reject`: plus SB cells from
     `ncei/derived/sb_track_bias_1min/controls_mb_sb_reject_<tile>.parquet`
     (rows with control_source `singlebeam_dispositioned`).
- Interpolator: GMT `surface` at 1 arcmin over each tile's freeze bounds,
  tension 0.25, the same GMT executable the downstream GGM stage uses (see
  `configs/feasibility/nested_sb_control_arms.yaml` in the 15 repo for the
  recorded GMT path; typically the torch27 conda env). Sample the grid at
  held-out cell centers with `grdtrack` (nearest). No masking beyond the
  tile bounds; compute differences only at the holdout cell centers.
- Metric (same formulas as the neural runs): per region, MSE within each
  holdout block, equal weight per block, square root = regional block-equal
  RMSE; pooled = square root of the equal-weight mean of regional MSEs.
  Report per-region and pooled values for all three variants, plus the
  pairwise differences.

## Hard constraints

- Read-only on all existing products in both repos; outputs additive under
  `ncei/derived/sb_interpolation_holdout/`.
- No GEBCO anywhere. No neural-network anything. No access to
  inner_validation / outer_evaluation depths.
- Run from repo root; pandas/pyarrow from
  `/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python`;
  GMT via its own env/executable as recorded downstream.

## Deliverables

1. `ncei/code/29_sb_interpolation_holdout.py` (new file).
2. `ncei/derived/sb_interpolation_holdout/`: per-region per-variant grids
   (or just sampled predictions at holdout centers + run manifest; full
   grids optional if large).
3. `ncei/docs/step10_sb_interpolation_holdout_report.md`: the three-variant
   comparison table (per region + pooled), the GMT settings used, and a
   plain-language verdict on the data-value question.

## Acceptance criteria

- Same holdout blocks and same metric formulas as the downstream
  pseudo-outer run, so the two tables can be compared row by row.
- Every number traceable to outputs of the recorded command.
- If GMT surface fails to converge or behaves pathologically on a tile,
  record it and report the partial result; do not silently switch
  interpolator settings per tile.

## Out of scope

- Other interpolators, tension sweeps, masking strategies.
- Downstream protocol changes; the outer evaluation.
