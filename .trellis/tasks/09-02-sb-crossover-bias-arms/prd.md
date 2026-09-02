# SB crossover audit and per-track bias arms for six-region GGM controls

mode: exploratory (audit + data products feeding a downstream experiment)

## Decision this task must answer

Before any singlebeam (SB) cell enters GGM control fitting in the six frozen
nested regions, decide which control-set form is defensible:
MB-only vs MB+raw-SB vs MB+adjusted-SB. This task produces the audit evidence
and the three control tables; it does NOT run the downstream GGM/PINN training
and does NOT select the final arm (arm selection happens downstream on
inner-validation under the frozen protocol).

## Hard constraints (hygiene boundary)

- Bias parameters are estimated ONLY from cells whose frozen role is
  `inner_training` (region membership parquets listed below).
- Never read `representative_depth_m` of cells whose role is
  `inner_validation` or `outer_evaluation`, for any purpose (fitting,
  QC, reporting, diagnostics). Role columns and cell coordinates may be read.
- Do not modify any existing pipeline output. All new code/outputs are
  additive. Read-only on: `ncei/derived/`, `ncei/manifests/`,
  `jamstec/multibeam/derived/`, the downstream freeze directory.
- Run scripts from repo root (`/mnt/data2/00-Data/ship`) per AGENTS.md.
- Python interpreter with pandas/pyarrow/netCDF4 on this machine:
  `/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python`
  (base python3 lacks pandas).

## Verified inputs (from the methods review, 2026-09-02)

- Region roles: `/mnt/data2/06-Projects/15-swot_feature_physics_bathy/outputs/20260901T220024Z-prospective-nested-ggm-nested_region_freeze/region_cells_<tile>.parquet`
  with tiles lon068_lat018 (160-165E/0-5N), lon052_lat018 (80-85E/0-5N),
  lon058_lat012 (110-115E/30-25S), lon059_lat015 (115-120E/15-10S),
  lon004_lat033 (160-155W/75-80N), lon021_lat010 (75-70W/40-35S).
  Columns: `one_minute_cell_id` (int; ship-repo string id =
  `1min_{cid//21600}_{cid%21600}`), `lon`, `lat`, `block_lon`, `block_lat`,
  `group_id`, `role`.
- Strict MB cells (reference depths, inner_training only):
  `ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet`
  (`cell_id`, `lon_center`, `lat_center`, `representative_depth_m`,
  `dominant_file_id`).
- SB per-track-per-cell stats:
  `ncei/derived/singlebeam/file_cells_1min/*.parquet`
  (`track_id, cell_id, median_depth_m, n_unique_triples, duplicate_ratio`,
  built by `ncei/code/07_aggregate_file_cells_1min.py`).
- SB point tables (nc tracks carry `time` + `point_index_in_track`; xyz tracks
  carry order only): `ncei/derived/singlebeam/points_raw/*__nc.parquet`,
  `*__xyz.parquet`.
- Track metadata: `ncei/manifests/trackline_source_manifest.parquet`
  (`has_time`, `instrument_class_pred`, bbox).
- GEBCO 2024 grid for DIAGNOSTIC STRATIFICATION ONLY (never a gate):
  `/mnt/data2/00-Data/bathymetry/GEBCO/GEBCO_2024.nc`.

## Deliverables

### D1 (assigned: codex/gpt-5.6-sol) — per-track SB bias + three control tables

New script(s) under `ncei/code/` (next free numbering, current max is 22;
use `23_estimate_singlebeam_track_bias_1min.py`). Per region, restricted to
`inner_training` cells:

1. Reference per cell: strict MB `representative_depth_m` where the cell is a
   strict cell; else leave-one-out SB consensus (median over other tracks'
   `median_depth_m` in the same cell; require >= 2 contributing tracks).
2. Per SB track: `b_track = weighted median over that track's co-located
   inner_training cells of (track cell median - reference)`, weights =
   `n_unique_triples`. Apply only when `n_colocated_cells >= 5` AND
   `|b| >= 2 * NMAD(track residuals)`; otherwise `b = 0` and record the reason
   (`thin_evidence` / `not_significant`).
3. Three control tables per region
   (`cell_id, lon_center, lat_center, control_depth_m, control_source`):
   `controls_mb_only`, `controls_mb_sb_raw` (SB depth as-is),
   `controls_mb_sb_adjusted` (per-track bias subtracted before re-aggregating
   multi-track cells by the file-balanced median convention of step 08).
4. Outputs: `ncei/derived/sb_track_bias_1min/` (parquet tables +
   `track_bias_summary.parquet`), report `ncei/docs/step09_sb_track_bias_report.md`
   with per-region counts, bias distribution, and stratification by
   |SB cell depth - GEBCO 2024 sampled at cell center| bands (diagnostic only).

### D2 (assigned: claude/glm-5.3) — true crossover audit

New script `ncei/code/24_true_crossover_audit.py`. Scope: the six region
tiles (all roles — this is a raw-data diagnostic that feeds no fitting).

1. From `points_raw` nc tracks (time + order) and xyz tracks (order only)
   intersecting each region bbox, compute track-line segment intersections
   (ordered lon/lat polyline vs polyline), interpolate each track's depth to
   the crossing point from bracketing points, and difference
   (`later_track_depth - earlier_track_depth` for nc; unordered pairs for xyz
   get arbitrary but recorded order). SB x SB pairs only: SB data never enters
   the frozen evaluation sets, so this audit touches no role-protected depth.
   JAMSTEC/NCEI-MB point files stay unread in this round.
2. QC: per-track time monotonicity and epoch sanity for nc tracks (report
   violations; time is otherwise unused).
3. Per track pair and per track: crossover difference stats
   (n, median, NMAD). Outputs:
   `ncei/derived/true_crossover_audit/` (parquet) +
   `ncei/docs/step09_true_crossover_audit_report.md`, including per-region
   summaries split by source_type (nc x nc / nc x xyz / xyz x xyz).
4. Do NOT compare against D1 bias estimates (the reviewer does that).

## Acceptance criteria

- Both scripts run to completion from repo root; outputs at the stated paths.
- A rerun of each script without --overwrite changes nothing (resumability
  convention may be minimal here since runtime is small; document the choice).
- D1's report states per region: n SB tracks with bias applied, median |b|,
  and confirms (with a code-level assertion) that no non-inner_training depth
  was read (e.g. filtered read + assert on role set).
- D2's report states per region: n crossovers found, median |difference|,
  split by nc/xyz, plus time-QC violation counts.
- No existing file under `ncei/derived/`, `ncei/manifests/`,
  `jamstec/`, or the freeze directory is modified (verify with git status +
  directory mtimes sampling).

## Out of scope

- Downstream three-arm GGM/PINN training and mu selection.
- regional_mrar (point cloud, no track order; not adjustable).
- GEBCO-based exclusion as a gate.
- Along-track drift models (allowed only as a documented D1 variant if the
  constant-bias residual shows a monotone along-track trend AND the track has
  >= 3 non-overlapping inner_training segments with >= 5 co-located cells
  each; report it separately, never merged into the primary adjusted table).
