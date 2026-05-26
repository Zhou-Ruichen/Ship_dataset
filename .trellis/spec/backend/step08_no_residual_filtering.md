# Step 08 — No Model Residual Filtering (invariant)

> Cross-stage invariant captured from Step 08 Stage 3 (strict_primary_multibeam) and Stage 4 (expanded_primary_ship) full-global validation runs. See `ncei/docs/strict_primary_full_validation_audit_report.md` and `ncei/docs/stage4_expanded_primary_validation_audit_report.md` for the audited evidence.

---

## Rule

Step 08 (`ncei/code/14_validate_gridded_products_step08.py`, `ncei/code/15_strict_vs_expanded_compare_step08.py`, and any downstream comparison/diagnostic) **must never** use a gridded-model residual to filter, drop, or relabel a validation cell.

Concretely, the pipeline:

- Loads validation cells from the configured Step 07B parquet (`strict_primary_multibeam_cells.parquet` or `expanded_primary_ship_cells.parquet`).
- Samples each gridded model at each cell.
- May mask **per-product metric averages** when a model returns nodata at a given cell.
- Must NOT remove rows from the by-cell output parquet because their residual exceeded a threshold, was an outlier, or disagreed with another model.
- Must NOT change `validation_weight`, `quality_tier`, `evidence_class`, or `matched_rule_id` based on residual.

Each `full_validation_safety_checks_<role_slug>.tsv` includes an explicit `no_model_residual_filtering` PASS line as a self-check signal. The audit pipeline re-verifies this by confirming that the by-cell parquet has the expected total row count (2,398,774 strict or 2,732,689 expanded), independently of which products produced nodata.

## Why

The validation contract is one-directional: **gridded models are evaluated against ship-derived truth**, not the reverse. Using model residuals to filter cells would:

1. Bias the metric distribution. Cells that the models find "hard" (high residual) would be silently removed, producing artificially low RMSE numbers for those models.
2. Couple Step 06B (quality policy, ship-side) and Step 08 (validation, model-side) in a way that breaks both: Step 06B's quality tiers stop being independent of model choice; Step 08's metrics stop being honest indicators of model quality.
3. Break reproducibility against external papers / methodologies that assume each gridded product is scored against the same baseline cell set regardless of its own behavior.

The strict / expanded separation policy depends on this invariant: strict_primary is the authoritative baseline precisely because no model — including SWOT_T1, SDUST_2023, or any future product — can change which cells are in it.

## How to apply

When extending Step 08 (new gridded product, new sampling method, new sensitivity analysis):

- Cells come ONLY from Step 07B validation-cell products. Do not augment with cells derived from model outputs.
- If a model returns nodata at a cell, write `model_depth_m = NaN` and `depth_error_m = NaN` for that row in the by-cell parquet — do NOT delete the row. Per-product metric aggregation (`build_metrics`) filters NaN residuals at aggregation time but the row remains in the by-cell file as evidence.
- If a downstream comparison/sensitivity script (e.g. `15_strict_vs_expanded_compare_step08.py`) computes a derived subset (retained_multibeam, singlebeam_gapfill), the subset is defined by **cell_id set membership**, not by residual magnitude.
- The `no_model_residual_filtering` PASS row in the safety-check output must remain truthful: the row is set to PASS by construction in `full_safety_checks`, and the audit confirms by independently counting by-cell parquet rows.

## Acceptance evidence

- Stage 3 strict-primary run: `no_model_residual_filtering` PASS; by-cell row count is exactly 2,398,774 for every product including SDUST_2023 (which has the highest residuals); no cells removed even when residuals exceed 4000 m. Cross-checked by independent PyArrow inspection in audit Section 4.
- Stage 4 expanded-primary run: `no_model_residual_filtering` PASS; by-cell row count is exactly 2,732,689 for every product; the 59 Drake Passage gap-fill cells with +2861m mean error are retained in the by-cell parquet and surfaced via the §7 sensitivity table — not silently dropped.

## Anti-patterns

- ❌ Adding a CLI flag like `--max-residual` to skip cells with `|residual| > X`. Use stratified metrics tables (lat_band, depth_bin, region) for outlier inspection instead.
- ❌ Using `pd.DataFrame.dropna(subset=["depth_error_m"])` on the by-cell DataFrame before writing parquet. NaN residuals are evidence; preserve them.
- ❌ Filtering cells based on per-model agreement (e.g., "drop cells where all 5 models disagree by > N m"). That mixes the model evaluations into the truth set, which is forbidden.
- ❌ Re-tiering quality_tier based on residual magnitude. Quality tiers come from Step 06B and are model-independent.

## Related

- [[step08-role-aware-safety-checks]] — the safety-check set that includes `no_model_residual_filtering` as the standing PASS row.
- `.trellis/spec/backend/pipeline-design-decisions.md` — the broader rule about strict/expanded separation and non-promotion of supplementary singlebeam / regional MRAR.
