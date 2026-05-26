# PRD — Step 08 Stage 4 · Expanded-Primary Sensitivity Validation

## 1. Goal

Run the five Stage 3 global gridded bathymetry products against the `expanded_primary_ship_cells` validation product, then quantify (a) the metric shift versus the strict_primary baseline and (b) where the added coverage comes from (geography, depth, quality, evidence, branch).

This is a sensitivity / coverage-expansion exercise. The strict_primary baseline from Stage 3 remains the authoritative global validation; expanded_primary is not promoted to primary.

## 2. Preconditions (audit-confirmed)

| Precondition | Source of confirmation |
|---|---|
| Stage 3 full strict-primary validation passed | `ncei/derived/model_validation_1min_full_strict_primary/full_validation_safety_checks_strict_primary.tsv` (all PASS) |
| Stage 3 post-run audit returned GO | `ncei/docs/strict_primary_full_validation_audit_report.md` (Section 9) |
| Step 06B quality flags untouched | This task does not modify them |
| Step 07B validation products untouched | This task only reads `expanded_primary_ship_cells.parquet` |

## 3. Input

- Validation product: `ncei/derived/validation_cells_1min/expanded_primary_ship_cells.parquet`
  - Expected rows: 2,732,689
  - Of those, `expanded_fill=True` (singlebeam gap-fill) is expected to be 333,915 rows (from Step 07B preflight)
  - Combines strict-primary multibeam cells + high-confidence singlebeam gap-fill cells
- Validation role: `product_role = expanded_primary_ship`
- Strict reference for comparison: existing Stage 3 outputs in `ncei/derived/model_validation_1min_full_strict_primary/`

## 4. Products

Same five global products as Stage 3:

- `GEBCO_2024`
- `ETOPO_2022`
- `SRTM15_V2.7`
- `SDUST_2023`
- `TOPO_25.1`

`SWOT_T1` is a regional footprint product and must be skipped (same skip reason as Stage 3) unless explicitly added as a separate footprint-only diagnostic — which is out of scope for this task.

## 5. Required Outputs

### 5.1 Per-cell residuals (one file per product, in `ncei/derived/model_validation_1min_full_expanded_primary/`)

- `full_validation_by_cell_expanded_primary_<product>.parquet`

### 5.2 Stratified metrics (one set, `_expanded_primary` suffix)

- `full_validation_metrics_summary_expanded_primary.{parquet,tsv}`
- `full_validation_metrics_by_quality_tier_expanded_primary.{parquet,tsv}`
- `full_validation_metrics_by_evidence_class_expanded_primary.{parquet,tsv}`
- `full_validation_metrics_by_source_role_expanded_primary.{parquet,tsv}`
- `full_validation_metrics_by_branch_expanded_primary.{parquet,tsv}`
- `full_validation_metrics_by_depth_bin_expanded_primary.{parquet,tsv}`
- `full_validation_metrics_by_lat_band_10deg_expanded_primary.{parquet,tsv}`
- `full_validation_metrics_by_region_10deg_expanded_primary.{parquet,tsv}`

Each must contain, per product (and stratum where applicable): `count, nodata_count, bias, MAE, RMSE, weighted_MAE, weighted_RMSE, median_error, MAD, abs_error_p90, abs_error_p95, abs_error_p99`.

### 5.3 Safety + provenance artifacts (per-run)

- `full_validation_product_status_expanded_primary.{parquet,tsv}` — per-product status (ok / skipped / error with reason)
- `full_validation_safety_checks_expanded_primary.tsv` — see §7 for the contract
- `full_validation_sample_diagnostics_expanded_primary.{parquet,tsv}` — z-convention / sign / elevation_correlation per product
- `skipped_products.tsv`
- Run log under `ncei/output/logs/`

### 5.4 Strict-vs-expanded comparison

- `strict_vs_expanded_comparison.{parquet,tsv}` — one row per (product_name, sampling_method) containing:
  - `strict_count`, `expanded_count`, `coverage_gain_count`, `coverage_gain_fraction_vs_strict`
  - `strict_bias`, `expanded_bias`, `delta_bias_expanded_minus_strict`
  - `strict_MAE`, `expanded_MAE`, `delta_MAE_expanded_minus_strict`
  - `strict_RMSE`, `expanded_RMSE`, `delta_RMSE_expanded_minus_strict`
  - `strict_weighted_MAE`, `expanded_weighted_MAE`, `delta_weighted_MAE_expanded_minus_strict`
  - `strict_weighted_RMSE`, `expanded_weighted_RMSE`, `delta_weighted_RMSE_expanded_minus_strict`

### 5.5 Coverage gain summary

- `expanded_primary_coverage_gain_summary.{parquet,tsv}` — coverage delta (cells added by expanded relative to strict) sliced by:
  - `source_role`
  - `branch`
  - `quality_tier`
  - `evidence_class`
  - `lat_band_10deg`
  - `depth_bin`
  - `region_10deg`
- Must also break out **retained multibeam cells** vs **singlebeam gap-fill cells** (using `expanded_fill` / `source_provider` / `source_role`).

### 5.6 Final report

- `ncei/docs/expanded_primary_global_validation_report.md` — generation timestamp, preflight status, safety check status, product status table, overall metrics table, sample diagnostics, and a recommendation paragraph.

## 6. Metric Comparison Requirements

Versus strict_primary (overall, then per-stratum):

- `delta_bias`, `delta_MAE`, `delta_RMSE`, `delta_weighted_MAE`, `delta_weighted_RMSE` (signed; expanded − strict).

Coverage:

- `added_cells_total` = `expanded_count − strict_count`
- `added_cells_by_source_role`, `_by_branch`, `_by_quality_tier`, `_by_evidence_class`, `_by_lat_band_10deg`, `_by_depth_bin`, `_by_region_10deg`
- Separate `retained_multibeam_cells` (intersection on `cell_id` with strict baseline) from `singlebeam_gapfill_cells` (set difference; expected to align with `expanded_fill=True`)

Driver attribution in the report:

- Are observed metric shifts driven by (a) added singlebeam cells, (b) specific lat bands, (c) specific depth bins, (d) specific regions?

## 7. Safety Checks (each must PASS for status to be PASS)

| # | check | expected | rationale |
|---|---|---|---|
| 1 | `input_row_count` | rows = 2,732,689 | Matches Step 07B expected row count for `expanded_primary_ship_cells` |
| 2 | `no_regional_mrar_in_expanded_primary` | regional_mrar rows = 0 | Expanded must not contain regional-experiment cells |
| 3 | `expanded_fill_count_matches_preflight` | `expanded_fill=True` rows = 333,915 (unless explicitly documented otherwise) | Preserves the documented singlebeam gap-fill count |
| 4 | `singlebeam_does_not_overwrite_multibeam` | `cell_id`s with `expanded_fill=True` have empty intersection with strict-primary `cell_id`s; OR equivalently, the row count of (expanded ∩ strict) on `cell_id` equals strict row count (2,398,774), and the union row count equals expanded row count (2,732,689) | Singlebeam may only ADD cells, never overwrite multibeam |
| 5 | `validation_weight_preserved` | null `validation_weight` = 0 | Step 06B/07B contract |
| 6 | `quality_tier_preserved` | null `quality_tier` = 0 | Step 06B/07B contract |
| 7 | `evidence_class_preserved` | null `evidence_class` = 0 | Step 06B/07B contract |
| 8 | `matched_rule_id_preserved` | null `matched_rule_id` = 0 | Step 06B/07B contract |
| 9 | `sign_error_suspected_false` (per product) | False for every product with status=ok | z-convention / sign sanity |
| 10 | `no_model_residual_filtering` | All 2,732,689 expanded rows retained before model nodata masking | Models do not change validation cells |

## 8. Non-Goals / Constraints

- Do not modify Step 06B quality rules or files.
- Do not modify Step 07B validation products (`*_cells.parquet`).
- Do not filter, drop, or re-label validation cells based on model residuals.
- Do not include `SWOT_T1` in this run.
- Do not include `supplementary_singlebeam_cells` or `regional_mrar_experiment_cells`.
- Do not overwrite Stage 3 strict-primary outputs in `model_validation_1min_full_strict_primary/`. Expanded outputs live in a **separate directory** `model_validation_1min_full_expanded_primary/`.
- Do not promote expanded_primary to replace strict_primary as the primary global baseline.
- Final recommendation must address whether expanded_primary remains secondary/sensitivity-only or can be used in selected regional analyses — but it is **not** authorized in this task to actually change that policy in the rest of the codebase.

## 9. Acceptance Criteria

- [ ] `full_validation_safety_checks_expanded_primary.tsv` has all 10 checks present and all PASS.
- [ ] Every required output file in §5 exists, is non-empty, and is readable as parquet/tsv.
- [ ] Per-product by-cell parquet has exactly 2,732,689 rows for every product with status=ok.
- [ ] `product_role` value is exactly `expanded_primary_ship` in every by-cell row.
- [ ] All 8 stratification tables (overall + 7 cross-cuts) are present.
- [ ] `strict_vs_expanded_comparison.{parquet,tsv}` has 5 rows (one per ok product), each with the delta columns from §5.4.
- [ ] `expanded_primary_coverage_gain_summary.{parquet,tsv}` includes coverage-gain rows for source_role, branch, quality_tier, evidence_class, lat_band_10deg, depth_bin, region_10deg — and breaks out retained multibeam vs singlebeam gap-fill.
- [ ] `expanded_primary_global_validation_report.md` is generated, references this PRD, and contains a sensitivity-interpretation paragraph + a secondary-vs-regional-use recommendation.
- [ ] Stage 3 strict-primary outputs are unchanged (timestamps and content identical to pre-run snapshot).

## 10. Out-of-Scope (for this task)

- SWOT_T1 footprint diagnostic.
- supplementary_singlebeam_cells coverage diagnostic.
- regional_mrar_experiment_cells sensitivity.
- Re-running Stage 3.
- Any change to Step 06B / Step 07B logic or outputs.
- Editorial changes to `validation_cell_catalog`.
