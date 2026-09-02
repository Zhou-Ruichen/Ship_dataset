# Global SB track-bias product, global crossover audit, and global coverage figures

mode: exploratory (upstream data product development; no downstream evaluation data involved)

## Decision this task must answer

Produce the global, reusable upstream products so that any downstream region
can consume bias-corrected singlebeam without re-deriving it. The task also
fixes the coverage-figure window problem that caused the "multibeam is
Japan-only" misreading.

## Background

Task 09-02-sb-crossover-bias-arms (archived) built the machinery for six
downstream regions: `ncei/code/23_estimate_singlebeam_track_bias_1min.py`
(per-track constant bias vs strict MB cells, gate: n>=5 and |b|>=2*NMAD) and
`ncei/code/24_true_crossover_audit.py` (exact 2D segment intersection +
linear depth interpolation). The downstream three-arm run (15-swot project,
task 09-02) showed raw SB is harmful (+16.3 m pooled inner-validation RMSE)
while adjusted SB is near-neutral (+1.1 m), so the adjusted product is the
only SB form worth distributing.

## Deliverables

1. `ncei/code/25_global_singlebeam_track_bias.py`: per-track constant bias
   for EVERY SB track (nc and xyz branches, regional_mrar excluded) that has
   >=1 co-located strict-MB 1' cell anywhere globally. Same estimator and
   gates as script 23. Output
   `ncei/derived/sb_track_bias_global/track_bias_summary.parquet` with
   columns: track identity (from the trackline source manifest), branch,
   n_colocated_cells, mb_median, sb_median, bias_m, nmad_m, applied (bool),
   gate_reason.
2. `ncei/derived/singlebeam/file_cells_1min_adjusted/`: per-track 1' cell
   parquet mirroring `file_cells_1min/` schema, with `depth_median_m`
   replaced by the adjusted value for applied tracks and raw value for
   others, plus columns `track_bias_m`, `bias_applied`, `bias_n_support`.
   This is the first-class product downstream consumes.
3. `ncei/code/26_global_singlebeam_crossover_audit.py`: extend script 24 to
   all global SB tracks (nc branches with time QC; xyz branches order-based,
   sign-convention consistency checked via crossover-vs-geometry). Output
   `ncei/derived/global_sb_crossover_audit/` with per-crossover and per-track
   stats like the six-region version.
4. Global coverage figures in `ncei/figures/coverage_global/`: one global
   map per source (JAMSTEC multibeam, NCEI multibeam, SB nc, SB xyz) with
   cell density, plus a combined MB-vs-SB panel. Global window, not a
   regional crop.
5. Report `ncei/docs/step10_global_sb_products_report.md`: counts, bias
   distribution, crossover statistics, per-source coverage numbers, and an
   explicit "how downstream should consume this" section (including the rule
   that regional_mrar is excluded and why).

## Hard constraints

- Read-only on ALL existing derived products and manifests; everything new is
  additive. Do not rewrite existing parquets to fix the
  `source_dataset`/`source_provider` label confusion; document the mapping
  in the report and use clean labels in the NEW products only.
- GEBCO is not used anywhere in this task.
- No downstream evaluation roles exist in this repo; the inner/outer hygiene
  boundary is a downstream concern and is not violated here (we only read
  strict-MB cells, which are the public primary product).
- Interpreter: `/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python`
  (pandas/pyarrow/matplotlib available); run from repo root.
- Reuse scripts 23/24 logic by import or extraction, not by copy-paste; if a
  shared helper must move, move it to `_common/` and update scripts 23/24
  imports in the same commit.

## Acceptance criteria

- Bias table covers all SB tracks with co-located MB cells; counts reconcile
  with the trackline source manifest.
- Adjusted cell product row counts match `file_cells_1min/` per track.
- Global crossover audit reproduces the six-region numbers from task 09-02
  on the same region subset (spot check).
- Coverage figures are global-window and clearly labeled per source.
- Report numbers traceable to the new derived outputs.

## Out of scope

- Rewriting existing products, git-history cleanup, downstream experiments
  (pseudo-outer spatial holdout is a downstream task, decided separately).
- Second-round crossover-referenced bias refinement for gate-refused tracks.
