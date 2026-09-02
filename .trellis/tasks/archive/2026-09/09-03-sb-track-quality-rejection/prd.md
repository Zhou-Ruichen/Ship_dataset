# Six-region per-track SB quality table and rejection-arm control tables

mode: exploratory (rule definition + application on existing six-region
products; feeds the downstream rejection-arm comparison)

## Decision this task must answer

Define the three-way per-track disposition (correct / keep raw / reject) and
produce the rejection-variant control tables, so the downstream project can
run the fourth arm "MB + SB with bad tracks rejected, no corrections". The
empirical question the downstream arm will answer: does rejecting bad tracks
capture most of the harm removal without the coverage loss of correction
misfires (odp130jr) or the incompleteness of refused corrections (elt18)?

## Inputs (all existing, read-only)

- `ncei/derived/sb_track_bias_1min/track_bias_summary.parquet` (step23
  decisions: bias_m, nmad_m, n_colocated_cells, applied, gate_reason).
- `ncei/derived/true_crossover_audit/crossovers_<region>.parquet` (pairwise
  events with observed_diff_m, track ids, sign convention as documented in
  the step09 report).
- `ncei/derived/sb_track_bias_1min/controls_mb_sb_adjusted_<tile>.parquet`
  (the adjusted arm tables; the MB rows are shared).
- Time-QC findings from the step09 crossover report (3 tracks with backward
  steps; 7 zero-cell Eltanin/Conrad tracks).

## Predeclared disposition rule

Evaluate tracks per region. Apply step23 corrections FIRST, then judge
post-correction consistency:

1. `reject` if any of: (a) backward time steps or zero valid depth cells
   (hard QC failures); (b) n_crossovers >= 10 AND post-correction per-track
   median |crossover diff| > 3 x regional crossover NMAD (the track remains
   internally inconsistent after the best available correction);
   (c) pre-correction scatter that correction does not reduce below the
   same threshold.
2. `revert_to_raw` if step23 applied a correction but post-correction
   misfit is WORSE than raw misfit (the odp130jr pattern).
3. `correct` if step23 applied and post-correction misfit improves or stays
   low.
4. `keep_raw` otherwise (including all tracks with too few crossovers to
   judge; absence of evidence is not rejection).

Tracks with large step23 REFUSED bias (elt18 pattern: gate_refused but
crossover-consistent large offset) are NOT corrected and NOT rejected in
this task; record them as `flag_large_unapplied_bias` for the separate
second-round decision.

## Deliverables

1. `ncei/code/28_sb_track_quality_disposition_1min.py` (new file; reuse by
   import from scripts 23/24/27).
2. `ncei/derived/sb_track_quality_1min/track_quality_<region>.parquet`:
   one row per SB track with bias fields, crossover misfit before/after,
   n_crossovers, QC flags, disposition, reason.
3. `ncei/derived/sb_track_bias_1min/controls_mb_sb_reject_<tile>.parquet`:
   same schema as the other control tables; MB rows unchanged; SB rows with
   dispositions applied; rejected tracks' rows dropped entirely.
4. Report `ncei/docs/step10_sb_track_quality_report.md`: disposition counts
   per region, how many cells are lost to rejection, the elt18/odp130jr
   outcomes under this rule, and the exact rejection-rule parameters used.

## Hard constraints

- Read-only on all existing derived products; outputs additive only.
- Do NOT touch files owned by the concurrently running task
  09-02-global-sb-bias-product: `ncei/code/25_*`, `ncei/code/26_*`,
  `ncei/derived/sb_track_bias_global/`,
  `ncei/derived/singlebeam/file_cells_1min_adjusted/`,
  `ncei/derived/global_sb_crossover_audit/`, `ncei/figures/coverage_global/`.
- Run from repo root with
  `/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python`.
- No GEBCO anywhere.

## Acceptance criteria

- Rule applied exactly as predeclared; every disposition traceable to the
  quality table row and its evidence fields.
- odp130jr must come out as revert_to_raw; elt18 as
  flag_large_unapplied_bias; the 3 backward-time and 7 zero-cell tracks as
  reject.
- Control table row counts reconcile: MB rows identical to the adjusted
  tables; SB rows = adjusted-table rows minus rejected tracks' rows, with
  reverted tracks at raw values.

## Out of scope

- Global application (follows the global crossover audit).
- Downstream training runs (separate task in the downstream repo).
- Drift or along-track models.
