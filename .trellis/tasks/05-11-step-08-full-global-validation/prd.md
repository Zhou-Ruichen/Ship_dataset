# PRD — Step 08 Full Global Validation

## Goal

Run full global validation of configured gridded bathymetry products against the Step 07B validation-cell products produced by the JAMSTEC + NCEI integration.

The historical task description referenced 2,394,115 global validation cells. Treat that as the legacy pre-integration JAMSTEC-only count. The current Step 07B products and expected row counts are:

| Step 07B product | Expected rows | Role in this task |
|---|---:|---|
| `strict_primary_multibeam_cells` | 2,398,774 | Main global validation baseline |
| `expanded_primary_ship_cells` | 2,732,689 | Sensitivity / coverage expansion comparison |
| `supplementary_singlebeam_cells` | 12,277,633 | Non-primary coverage diagnostics only |
| `regional_mrar_experiment_cells` | 9,019,383 | Regional sensitivity experiments only |
| `validation_cell_catalog` | 24,029,705 | Audit catalog / manifest source |

## Primary objective

Validate GEBCO / ETOPO / SRTM15 / other configured global gridded products against `strict_primary_multibeam_cells`.

`strict_primary_multibeam_cells` is the authoritative full-global baseline for this task. It combines JAMSTEC multibeam and NCEI multibeam under Step 07B precedence, and singlebeam must not overwrite multibeam in this product.

## Secondary objective

Compare `strict_primary_multibeam_cells` against `expanded_primary_ship_cells` to quantify coverage and metric sensitivity from high-confidence NCEI singlebeam gap-fill.

The strict and expanded outputs must remain separate. Expanded-primary results are a sensitivity product, not a replacement for strict-primary validation unless a later task explicitly changes that policy.

## Non-primary diagnostics

- `supplementary_singlebeam_cells`: use only for non-primary coverage diagnostics.
- `regional_mrar_experiment_cells`: use only for regional sensitivity experiments.

Neither product may enter strict-primary validation. Regional MRAR must not be promoted to primary validation.

## Non-goals

- Do not re-open Step 06B quality rules.
- Do not modify Step 07B validation products.
- Do not create new validation-cell products.
- Do not use gridded models as filtering truth.
- Do not use GEBCO / ETOPO / SRTM15 / SWOT residuals to change quality flags or cell inclusion.
- Do not merge `regional_mrar_experiment_cells` into primary validation.
- Do not run SWOT regional validation unless the footprint is compatible and explicitly configured.
- Do not let singlebeam overwrite multibeam in the strict primary product.

## Inputs

- `ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet`
- `ncei/derived/validation_cells_1min/expanded_primary_ship_cells.parquet`
- `ncei/derived/validation_cells_1min/supplementary_singlebeam_cells.parquet/`
- `ncei/derived/validation_cells_1min/regional_mrar_experiment_cells.parquet/`
- `ncei/derived/validation_cells_1min/validation_cell_catalog.parquet/`
- Gridded product configuration file: `jamstec/multibeam/configs/gridded_products_validation.yaml`
- Configured product files referenced by that YAML.

## Outputs

Outputs should be written to stable Step 08 run directories under `ncei/derived/` / `ncei/docs/` / `ncei/output/logs/`, with run-label or stage labels that prevent smoke outputs from overwriting production outputs.

Required output classes:

- `validation_by_cell` per gridded product and validation product.
- Metrics summary by model.
- Metrics by `quality_tier`.
- Metrics by `evidence_class`.
- Metrics by `source_role` / branch.
- Metrics by `depth_bin`.
- Metrics by `lat_band`.
- Metrics by 10-degree region.
- Strict-vs-expanded comparison.
- Preflight report.
- Smoke validation report.
- Full global validation report after a later full run.

## Acceptance criteria

- Preflight passes before any validation run.
- Smoke validation passes before any full validation run.
- Full `strict_primary_multibeam_cells` validation completes in the later production run.
- Metrics preserve and report `quality_tier`, `evidence_class`, `validation_weight`, `source_role`/branch, and `product_role`.
- `strict_primary_multibeam_cells` and `expanded_primary_ship_cells` outputs remain separate.
- No `supplementary_singlebeam_cells` or `regional_mrar_experiment_cells` cells enter strict-primary validation.
- No model residuals are used to change quality flags or cell inclusion.
- Missing model grids are reported as skipped with reasons rather than silently treated as successful.
- Schema mismatch or z-sign sanity failure stops before production validation.

## Dispatch boundary for this session

This dispatch should:

1. Create the missing planning documents.
2. Move the Trellis task from `planning` to `in_progress`.
3. Run Stage 1 preflight.
4. If preflight passes, run Stage 2 smoke validation.
5. Stop after smoke validation and report go/no-go for a later full strict-primary validation.

This dispatch must not run full global validation.
