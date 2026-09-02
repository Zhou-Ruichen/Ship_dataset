# Global merged 1-arcmin ship-bathymetry grid r2

mode: production (merge of two accepted products; the spec is written)

## Decision this task must answer

Produce the first merged global ship-bathymetry grid, round r2, exactly per
the spec in `docs/数据产品规范与下游接入.md` section 2. This is the product
downstream repos consume when they want one depth per cell.

## Inputs (both accepted)

- `ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet`
  (2,398,774 cells; read `representative_depth_m` — it is the primary
  product, not downstream evaluation data).
- `ncei/derived/singlebeam/file_cells_1min_final_r2/` (17,294,849 rows,
  per-track parquets with `median_depth_m`, `track_disposition`).

## Merge rule (from the spec; restated here to pin it)

- Output: one row per 1-arcmin cell that has any ship data.
- If a cell has strict MB: depth = MB representative depth,
  `source_layer = 'strict_mb'`. If SB rows also exist for the cell, their
  non-reject median goes to the diagnostic column `sb_depth_m`; else null.
- If a cell has only SB: depth = the median of that cell's non-reject SB
  track medians, `source_layer = 'sb_final'`, plus `sb_n_tracks`.
- Rejected-track rows never contribute. regional_mrar stays out (no track
  order/time; documented exclusion).
- Output columns: `cell_id`, `lon_center`, `lat_center`, `depth_m`,
  `source_layer`, `sb_depth_m` (nullable), `sb_n_tracks` (nullable).
- Partitioned parquet by 10-degree latitude band under
  `ncei/derived/global_grid_1min_r2/`; `product_manifest.json` records
  generation time, input file counts, input SHA-256s, and the merge rule.

## Hard constraints

- Read-only on both inputs and on everything else; additive output only.
- No GEBCO. No downstream evaluation data anywhere.
- Run from repo root with the analysis venv python.
- The concurrent download task writes only under `ncei/tracklines_m77t_round2/`;
  do not touch it. Do not edit README/docs (the spec is written; this task
  is the producer, not the writer). One exception: if the spec section 2
  contradicts what the inputs actually contain, STOP and report the
  contradiction instead of improvising.

## Deliverables

1. `ncei/code/31_build_global_grid_1min.py` (new file; reuse by import).
2. `ncei/derived/global_grid_1min_r2/` partitioned parquet +
   `product_manifest.json`.
3. A short production note appended as a section in
   `ncei/docs/step10_global_sb_products_report.md`: row counts by
   source_layer, overlap-cell count, per-latitude-band counts, and the
   command used.

## Acceptance criteria

- Total rows = |MB cells union SB cells|; MB-priority cells = strict MB
  count; no cell_id duplicated.
- Spot check: 5 random strict-MB cells carry the MB depth; 5 random
  overlap cells carry MB depth + non-null sb_depth_m; 5 random SB-only
  cells carry SB depth with source_layer sb_final.
- Row count reconciles: strict MB 2,398,774 cells all present; SB-only
  cells = final-layer non-reject cells minus overlaps.

## Out of scope

- r3 (with the 706 new surveys) — follows the download + ingestion tasks.
- Any interpolation/gridding beyond cell assembly (this is a data product,
  not a modeled grid). Downstream notification (uses consumers.yaml).
