# Implementation Plan — Step 08 Full Global Validation

## Stage 1 — Preflight only

Validate the Step 07B validation products and gridded product configuration without sampling model grids.

Checklist:

- Validate input product paths:
  - `strict_primary_multibeam_cells`
  - `expanded_primary_ship_cells`
  - `supplementary_singlebeam_cells`
  - `regional_mrar_experiment_cells`
  - `validation_cell_catalog`
- Validate schema and derived compatibility fields.
- Validate row counts against Step 07B expected values:
  - `strict_primary_multibeam_cells = 2,398,774`
  - `expanded_primary_ship_cells = 2,732,689`
  - `supplementary_singlebeam_cells = 12,277,633`
  - `regional_mrar_experiment_cells = 9,019,383`
  - `validation_cell_catalog = 24,029,705`
- Validate required fields or lossless derivations:
  - `cell_id`
  - `lon_center`
  - `lat_center`
  - `depth_m_positive_down` (derived from `representative_depth_m` if needed)
  - `elev_m` (derived as `-representative_depth_m` if needed)
  - `product_role` (derived from product name if needed)
  - `branch` / `source_role` (`source_role` may be represented by `branch_role`)
  - `quality_tier`
  - `evidence_class`
  - `validation_weight`
  - `n_unique_triples_total`
  - `duplicate_ratio_cell`
  - `matched_rule_id` (materialized from Step 06B for NCEI rows and `jamstec_legacy` for JAMSTEC rows if needed)
- Validate z-sign consistency:
  - `representative_depth_m > 0` for validation rows.
  - Derived `elev_m < 0` for ocean rows.
  - `elev_m + depth_m_positive_down ≈ 0`.
- Validate strict/expanded separation:
  - strict product contains no `ncei_singlebeam` rows.
  - strict product contains no regional MRAR rows.
  - expanded product keeps `expanded_fill=True` for singlebeam gap-fill cells.
- Validate supplementary/regional non-primary roles:
  - supplementary branch role remains `supplementary_coverage`.
  - regional branch role remains `regional_experiment`.
- Validate gridded product config and file availability.
- Produce a preflight report and go/no-go for smoke validation.

Expected command for this dispatch:

```bash
python3 ncei/code/14_validate_gridded_products_step08.py \
  --stage preflight \
  --run-label smoke \
  --config jamstec/multibeam/configs/gridded_products_validation.yaml \
  --overwrite
```

If the new wrapper script is not yet present, create it before running preflight. The script must be read-only with respect to Step 06B / Step 07B products.

## Stage 2 — Smoke validation

Run a deterministic small subset after preflight passes.

Checklist:

- Include `strict_primary_multibeam_cells` and `expanded_primary_ship_cells`.
- Use a deterministic subset keyed by `cell_id` / stable seed.
- Run `GEBCO_2024` first.
- Optionally run `ETOPO_2022` if GEBCO smoke passes.
- Preserve `product_role` on all by-cell outputs.
- Produce smoke validation outputs and a smoke report.
- Stop and report go/no-go for full validation.

Expected command for this dispatch:

```bash
python3 ncei/code/14_validate_gridded_products_step08.py \
  --stage smoke \
  --run-label smoke \
  --config jamstec/multibeam/configs/gridded_products_validation.yaml \
  --product-name GEBCO_2024 \
  --product-name ETOPO_2022 \
  --sample-n-cells 2000 \
  --overwrite
```

If GEBCO fails, do not run ETOPO in a way that obscures the failure. Report the GEBCO failure and stop.

## Stage 3 — Full strict-primary validation

Only after smoke passes and the user explicitly approves a full run.

Checklist:

- Input: `strict_primary_multibeam_cells` only.
- Require explicit `--confirm-full` or equivalent Trellis approval.
- Run configured global gridded products.
- Preserve `product_role = strict_primary_multibeam`.
- Produce by-cell validation and metrics summaries.
- Record skipped models and reasons.

Do not run this stage in the current dispatch.

## Stage 4 — Expanded-primary sensitivity validation

After strict-primary full validation completes.

Checklist:

- Input: `expanded_primary_ship_cells`.
- Keep outputs separate from strict-primary outputs.
- Compare against strict-primary results.
- Report coverage gain and metric changes.
- Separate retained multibeam cells from singlebeam gap-fill cells using `expanded_fill` / `source_provider` / `branch_role`.

Do not run this stage in the current dispatch.

## Stage 5 — Non-primary diagnostics

Optional after primary validation is stable.

Checklist:

- `supplementary_singlebeam_cells`: coverage diagnostics only.
- `regional_mrar_experiment_cells`: regional sensitivity only.
- Do not mix either into strict-primary validation.

Do not run this stage in the current dispatch.

## Stage 6 — Final report

After full strict and expanded validations are available:

- Summarize strict-primary results.
- Summarize strict vs expanded sensitivity.
- Summarize skipped models.
- Provide final recommendations for whether `expanded_primary_ship_cells` should remain a secondary product only or be considered for specific regional analyses.

## Review gates

- Gate A: preflight report reviewed before smoke.
- Gate B: smoke report reviewed before full strict-primary run.
- Gate C: full strict-primary report reviewed before expanded-primary sensitivity run.

## Rollback / cleanup

- Smoke outputs live under a smoke-specific output directory and can be deleted without affecting production Step 07B products.
- No input parquet or model grid is modified.
- If a wrapper script is added, it should be additive and should not alter the legacy JAMSTEC Step 08 script unless explicitly required.
