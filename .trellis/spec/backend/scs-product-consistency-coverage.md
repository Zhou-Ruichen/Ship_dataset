# SCS Product Consistency and Coverage Audit

## 1. Scope / Trigger

Use this bounded audit after the frozen SCS lineage audit when a downstream
consumer needs:

- mature-product values and descriptive consensus at all 174,965 audited ship
  cells;
- full-domain ship-cell coverage and nearest-support distance over the frozen
  South China Sea grid; or
- GEBCO TID composition by release.

This is QC layer C. It is descriptive and must not mutate label eligibility,
quality tiers, validation rows, cohorts, splits, or weights. It must not read
downstream predictions, residuals, model errors, metrics, or error-derived
cohort columns.

## 2. Signatures

Run from the repository root:

```bash
python ncei/code/audit_scs_product_consistency_coverage.py \
  --config ncei/configs/scs_product_consistency_coverage.yaml \
  --estimate-only

python ncei/code/audit_scs_product_consistency_coverage.py \
  --config ncei/configs/scs_product_consistency_coverage.yaml \
  --run-id <UTC_RUN_ID> \
  --confirm-audit

python ncei/code/verify_scs_product_consistency_coverage.py \
  --run-dir ncei/derived/scs_product_consistency_coverage/<UTC_RUN_ID>
```

`--estimate-only` verifies all frozen input hashes, schemas, the cell-key
closure, and the frozen ocean mask without creating a run directory. A full
run refuses to start without `--confirm-audit`. Existing run IDs are immutable.

## 3. Contracts

### Inputs

The YAML config is the single source of truth for paths and expected SHA256.
The required input roles are:

```text
downstream_union
cell_lineage
raw_to_cell_replay
frozen_scs_context
product_gebco_2024 / product_gebco_2025 / product_gebco_2026
product_etopo_2022 / product_srtm15_v2_7 / product_topo_25_1 / product_sdust_2023
tid_2024 / tid_2025 / tid_2026
```

Only these columns may be read from `downstream_union`:

```text
canonical_cell_id, lon, lat, representative_depth_m, source_provider
```

Do not read `roles`, `outlier97`, `distance_to_evaluation_control_km`, or any
prediction/residual/error/metric column. Union, lineage, and replay must close
on exactly 174,965 unique keys, with source counts 165,966 MRAR plus 8,999
JAMSTEC. Replay must close on 174,913 exact plus 52 documented aggregation
differences.

### Grid and sign

The coverage denominator is the frozen downstream mask, not a mask regenerated
from a newer GEBCO release:

```text
domain: [105, 125) E x [0, 25) N
registration: 1-arcminute pixel
shape: lat=1500, lon=1200
strict-ocean cells: 1,288,723
land rule: frozen GEBCO 2024 context land_fraction > 0
```

All comparison values use metres positive down. Aligned 15-arcsecond products
are reduced to 1 arc-minute with the exact median over each 4x4 pixel block.
Aligned 1-arcminute products are read at exact pixel centres. Nodata remains
NaN without row deletion. Finite non-positive values remain diagnostic values.

### Consensus

For row vector `x`:

```text
median = nanmedian(x)
NMAD = 1.4826 * nanmedian(abs(x - median))
```

Persist both:

- seven-product consensus over all seven configured depth values;
- family-balanced consensus over
  `median(GEBCO 2024, 2025, 2026)`, ETOPO, SRTM15+, TOPO, and SDUST.

The family-balanced result only prevents three GEBCO releases from receiving
three votes. It does not establish independence among the five components.
Persist `reference_independence=not_established`. Signed differences are
`reference_depth - ship_depth`.

### TID

TID groups are disjoint and frozen in config:

```text
land: 0
direct_measurement: 10-17
gravity_guided_or_predicted: 40, 44, 45
other_indirect_or_unknown: 41, 42, 43, 46, 47, 48, 70, 71, 72
```

An unconfigured observed code aborts the run. Exact per-code counts are
authoritative. Group fractions are the fraction of the 16 aligned TID pixels
in a 1-arcminute cell. `direct_measurement` is not synonymous with a verified
independent ship source.

### Outputs

Each run directory contains:

| File | Contract |
|---|---|
| `product_consistency_by_cell.parquet` | 174,965 rows; seven depths/differences, two consensus families, TID fractions, lineage and replay fields |
| `scs_product_context_1min.nc` | 1500x1200 seven-product depth and three-release TID context |
| `coverage_grid_1min.nc` | frozen mask, occupancy, cell area, nearest distance, 1-degree control count |
| `coverage_by_block_1deg.parquet` | exactly 500 anchored 1-degree blocks |
| `product_metrics.tsv` | overall and source-provider diagnostic metrics |
| `tid_composition.tsv` | exact per-release TID code counts and groups |
| `coverage_summary.json` | cell/area coverage and frozen distance-radius curve |
| `audit_report.md` | evidence boundary, inputs, methods, results, limitations |
| `audit_manifest.json` | input/output hashes and explicit no-mutation/no-error-read flags |
| `verification.json` | independent verifier result |

The per-cell diagnostic table must not contain a weight, eligibility,
exclusion, outlier, decision, or 3STD column.

## 4. Validation and Error Matrix

| Condition | Required behavior |
|---|---|
| Full run lacks `--confirm-audit` | Refuse before hashing or writing |
| Run directory already exists | Raise; do not overwrite |
| Input hash differs from config | Abort before analysis |
| Input path contains prediction/residual/model-error/error-cohort token | Reject input |
| Requested union columns differ from five-column allowlist | Reject read |
| Union/lineage/replay key or count differs | Abort |
| Product/TID coordinates do not exactly align | Abort |
| TID groups overlap or observed code is unconfigured | Abort |
| Mature product returns nodata | Preserve row with NaN; aggregate metrics over finite values only |
| Product has finite non-positive ocean depth | Preserve and count; do not drop |
| Product disagreement is large | Preserve cell and difference; no decision field |
| Output or input hash fails verifier | Verification fails; do not cite run |

## 5. Good / Base / Bad Cases

- Good: all seven product values are finite, family NMAD is small, and the row
  remains labelled `qc_layer_c_diagnostic_only`.
- Base: one reference product is non-positive at a frozen-ocean cell. Retain
  the value and row, increment the non-positive diagnostic count, and do not
  change label eligibility.
- Base: a GEBCO cell contains eight direct and eight gravity-guided TID pixels.
  Persist both fractions as 0.5; do not force a false independent-source class.
- Bad: turn `family_consensus_nmad_m` into a PINN sample weight inside this
  task.
- Bad: remove a cell because `abs(reference - ship) > 3 * std`.
- Bad: call TID code 11 proof that GEBCO and the audited ship cell are
  independent.

## 6. Tests Required

- Unit-test half-open target centres and exact 4x4 median aggregation.
- Unit-test positive-up elevation to positive-down depth conversion while
  preserving non-positive values.
- Unit-test seven-product and family-balanced median/NMAD separately.
- Unit-test spherical cell area and great-circle nearest distance.
- Unit-test disjoint TID groups, unexpected-code rejection, and fraction
  closure.
- Unit-test union allowlist and decision/weight output-column rejection.
- Run `--estimate-only`, a full immutable audit, and the independent verifier.
- The verifier must rehash all inputs/outputs, recompute all consensus rows,
  all 1,288,723 ocean-cell distances, all product metric rows, exact TID code
  counts, 500 block closure, and the 174,913/52 replay split.

## 7. Wrong vs Correct

Wrong:

```python
diagnostic = diagnostic[diagnostic["family_consensus_nmad_m"] < threshold]
diagnostic["sample_weight"] = 1 / (1 + diagnostic["family_consensus_nmad_m"])
```

Correct:

```python
diagnostic["family_consensus_nmad_m"] = family_nmad
diagnostic["comparison_role"] = "qc_layer_c_diagnostic_only"
# A separately frozen downstream task may study weighting; this audit does not.
```
