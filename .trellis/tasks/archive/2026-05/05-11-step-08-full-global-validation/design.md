# Design — Step 08 Full Global Validation

## Overview

Step 08 validates configured gridded bathymetry products against immutable Step 07B ship-cell products. The validation stage is read-only with respect to Step 06B quality flags, Step 07B validation cells, and model grids.

The current implementation in `jamstec/multibeam/code/08_validate_gridded_products_against_ship_cells.py` was built for the legacy JAMSTEC Step 07 product. This task applies the same validation concepts to the post-integration Step 07B products while preserving their roles and provenance.

## Data flow

```text
Step 07B validation products
  → schema / z-sign / product-role preflight
  → smoke validation
  → full strict_primary validation
  → expanded_primary sensitivity validation
  → optional supplementary / regional diagnostics
  → final report
```

## Product roles

| Product | Role | Validation policy |
|---|---|---|
| `strict_primary_multibeam_cells` | Main global validation baseline | Full production validation input |
| `expanded_primary_ship_cells` | Sensitivity / coverage expansion | Separate sensitivity validation; quantify metric and coverage changes |
| `supplementary_singlebeam_cells` | Non-primary coverage diagnostics | Coverage diagnostics only; not primary truth |
| `regional_mrar_experiment_cells` | Regional sensitivity only | Optional regional experiments only; never primary |
| `validation_cell_catalog` | Audit catalog | Manifest / product-membership checks |

Strict-primary validation must not include supplementary singlebeam or regional MRAR rows. Expanded-primary validation must remain separate from strict-primary validation.

## Input schema mapping

Step 07B products use `representative_depth_m` as the positive-down ship depth. Step 08 validation should derive:

- `depth_m_positive_down = representative_depth_m`
- `elev_m = -representative_depth_m`
- `ship_depth_m = representative_depth_m` when compatibility with legacy Step 08 logic is needed
- `ship_elev_m = -representative_depth_m` when compatibility with legacy Step 08 logic is needed
- `product_role` from the Step 07B product name, e.g. `strict_primary_multibeam`
- `source_role` from existing `branch_role` / `branch`

Required provenance and quality fields must be carried into by-cell outputs and metric groupings: `quality_tier`, `evidence_class`, `validation_weight`, `branch`, `branch_role`, `source_provider`, `product_role`, and available rule / version fields.

`matched_rule_id` is required by preflight. Step 07B products do not physically carry it; it is inherited from NCEI Step 06B and is represented as `jamstec_legacy` for JAMSTEC rows. Preflight should verify that the rule provenance can be materialized, not mutate Step 07B files.

## Sampling strategy

- High-resolution products: use `cell_median` where supported; fall back to nearest/center sampling as configured by the product validator when full cell aggregation is too expensive.
- 1-minute products: use center bilinear interpolation or the configured method.
- Preserve z-sign convention:
  - Ship `elev_m` is ocean-negative.
  - Ship `depth_m_positive_down` is positive downward.
  - Model products configured as `elevation_negative_ocean` are already ocean-negative.
  - Model products configured as `depth_positive_down` are converted to ocean-negative elevation for residuals.
- Residual convention: `elev_error_m = model_elev_m - ship_elev_m`; `depth_error_m = model_depth_m - ship_depth_m`.

## Metrics

Compute at minimum:

- Bias / mean error.
- MAE.
- RMSE.
- Weighted MAE using `validation_weight`.
- Weighted RMSE using `validation_weight`.
- Median error.
- MAD.
- p90 / p95 / p99 absolute error.
- Count and coverage summaries.

Coverage denominators must be clear: requested cells, valid sampled cells, and product-footprint cells where a model footprint is configured.

## Breakdowns

Report metrics by:

- Model / gridded product.
- Validation product / `product_role`.
- `quality_tier`.
- `evidence_class`.
- `source_role` / branch (`branch_role`, `branch`, and/or `source_provider`).
- `depth_bin`.
- `lat_band_10deg`.
- 10-degree region.

## Safety gates

- No full run before preflight passes.
- No full run before smoke validation passes.
- Full production run must require an explicit `--confirm-full` flag or an equivalent Trellis approval gate.
- Smoke outputs must not overwrite full production outputs.
- Missing model grids should be marked skipped with a reason, not hidden.
- Sign-convention sanity failures stop before production validation.
- Schema mismatches stop before validation.

## Reproducibility

- Use a deterministic smoke subset.
- Use stable output paths with a run label.
- Write a manifest of input paths, input row counts, product config path, enabled model names, missing / skipped models, and code/config timestamps or hashes where practical.
- Write logs per run label.
- Preserve product-role separation in filenames and reports.

## Failure handling

- If a configured model grid is missing, mark that product skipped with reason and continue with other enabled models for smoke/full validation.
- If a product config entry is malformed, report the specific product and field; do not treat it as successful.
- If ship-cell z-sign sanity checks fail, stop before validation.
- If required schema fields are missing and cannot be derived losslessly, stop before validation.
- If strict/expanded role separation is violated, stop and report the violating product / cell set.

## Full-run boundary

This session is limited to preflight and smoke validation. Full strict-primary and expanded-primary production validation should be launched only after reviewing the smoke report and explicitly approving the full run.
