# SB crossover network constant-offset solve, six-region prototype

mode: exploratory (three-way comparison on existing six-region crossover events)

## Decision this task must answer

Does a crossover-network least-squares solve for per-track constant offsets
beat (a) no correction and (b) the step23 reference-cell bias, judged ONLY by
held-out crossover residuals in the six frozen downstream regions? If yes, it
becomes the candidate bias method for the global product; if no, step23
stays.

## Method (from the step10 screening survey, recommendation 1)

- Observations: the existing pairwise crossover events from
  `ncei/derived/true_crossover_audit/` (exact segment intersections with
  linear depth interpolation; one depth difference per event, sign =
  track_B - track_A as recorded there).
- Graph: SB tracks as nodes, crossover events as edges; solve per connected
  component. Components containing >=1 track with an APPLIED step23 bias
  (MB-anchored) get an absolute datum by fixing those tracks to their step23
  offsets; components without MB support use a free-network constraint
  (offsets sum to zero) and are marked relative-only.
- Solver: plain weighted least squares on the design matrix (one unknown per
  track, one equation per crossover event). Record per-track: offset,
  offset standard error, n_crossovers, n_distinct_neighbor_tracks, component
  id, datum type (anchored / free).
- Evaluation protocol (predeclared): per component with >=3 tracks and
  >=2 crossovers per track on average, leave-one-out over crossover events:
  re-solve without event i, predict event i, collect residual. Compare the
  three variants (raw / step23 / network) on pooled median |residual| and
  pooled NMAD of residuals per region. Also report the unweighted solve
  alongside any weighted variant. GEBCO does not participate anywhere.
- Tracks with a single crossover only get a relative offset and are excluded
  from the held-out evaluation (their residual is not identifiable).

## Hard constraints

- Read-only on all existing derived products; new outputs additive under
  `ncei/derived/sb_network_bias_1min/`.
- Do NOT touch any file that task 09-02-global-sb-bias-product (running
  concurrently) writes: `ncei/code/25_*`, `ncei/code/26_*`,
  `ncei/derived/sb_track_bias_global/`,
  `ncei/derived/singlebeam/file_cells_1min_adjusted/`,
  `ncei/derived/global_sb_crossover_audit/`, `ncei/figures/coverage_global/`.
- Run from repo root with
  `/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python`.

## Deliverables

1. `ncei/code/27_sb_crossover_network_bias_1min.py` (new file; reuse by
   import from scripts 23/24 where possible).
2. `ncei/derived/sb_network_bias_1min/`: per-track network offsets per
   region, component table, held-out residual table per variant.
3. Report `ncei/docs/step10_sb_network_bias_report.md`: the three-variant
   comparison per region and pooled, the datum split (anchored vs free
   components, how many tracks each), and an explicit recommendation:
   globalize / keep step23 / inconclusive, with the evidence.

## Acceptance criteria

- Every reported number traceable to the new derived outputs.
- The held-out protocol is applied identically to all three variants.
- The elt18 and odp130jr edge cases from the step09 consistency check are
  revisited: report what the network assigns to each and whether that agrees
  with the crossover evidence documented in
  `.trellis/tasks/archive/2026-09/09-02-sb-crossover-bias-arms/research/d1-d2-consistency-check.md`.

## Out of scope

- Global solve (contingent on this prototype's recommendation).
- Drift/along-track models; weighting by depth-dependent uncertainty
  (survey recommendation 3, separate task).
