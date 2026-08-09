# Execution status: 20260809T191946Z

## Accepted inputs and roles

- Phase A reference:
  `ncei/derived/scs_tn352_processing_and_support_audit/20260809T174007Z/phase_a`
- Phase A status/classification:
  `pass`, `B. official_raw_source_development_label`
- Phase B output role: `development_only_not_confirmation`
- frozen assignment rows/unique IDs: `2,244 / 2,244`
- frozen assignment SHA256:
  `c7c3aacc0a33d680e3800162220e720776a8c475247562b9315a5588656d5efb`

## Cell-ID gate before depth access

- frozen IDs missing TN352 candidates: `0`
- frozen IDs missing current MRAR raw support: `0`
- current TN352/MRAR raw-support intersection: `2,367`
- `raw_support_only_not_in_frozen_scalar_pair`: `123`
- TN352 candidate without MRAR raw support: `1min_6739_18005`
- freeze depth-value and depth-difference columns read: `[] / []`
- all 123 excluded IDs are absent from the support table and every pair table

## Phase B verified output

Accepted path:

```text
ncei/derived/scs_tn352_processing_and_support_audit/20260809T191946Z/phase_b
```

- support cells: `2,244`
- selected TN352 eligible soundings: `11,790,285`
- selected MRAR basic-pass points: `40,912`
- mutual-nearest pairs at 100 / 250 / 500 m:
  `29,600 / 32,102 / 32,302`
- independently verified: `pass`
- audit manifest SHA256:
  `b1e79e7535586e084283014efe8bbacfe92d02895e415ec2049e4a03127add71`

Registered cell-level tail decisions:

| Threshold | Evaluable cells | P95 ratio | Tail-fraction ratio | Decision |
|---:|---:|---:|---:|---|
| 100 m | 2,099 | 1.4154 | 1.0714 | `not_materially_contracted` |
| 250 m | 2,203 | 1.0937 | 1.1250 | `not_materially_contracted` |
| 500 m | 2,238 | 0.9940 | 1.1206 | `not_materially_contracted` |

At 500 m, the registered concentration test is positive for zero/low
footprint overlap, high relief, and low matched support. Zero/low overlap
covers 2,237/2,238 evaluable cells and therefore does not localize the tail.
High relief and low matched support are the discriminating positive strata.

The frozen unresolved flag is `0`, but this is not a causal explanation
count: `small_source_support` covers all 2,238 evaluable cells because the MRAR
input has one track. The protocol cannot identify a separate causally
unexplained subset. No TN352 label upgrade is supported.

## Verified output SHA256

- `tn352_mrar_support_cells.parquet`:
  `bcbc4abe3008006691ff65e7660d8cd44e99f5180a2a7218ab7b371b9de0ba97`
- `matched_difference_100m.parquet`:
  `0ddb5d0232f4ecfe661c3954f17e3dea3049a76dcf5d357d58828f9ae64a0f4e`
- `matched_difference_250m.parquet`:
  `f1aafbc53a138a90f2a87d748f6edb96ed91bd739440445fa6ebe3945da76bf9`
- `matched_difference_500m.parquet`:
  `ced4b4ad77ba4467a9069696e9087e17feef6b5df95b3ef167cd1a11c2e516d6`
- `common_cell_cohort.parquet`:
  `4781737822db23df9dff9227b5211d9a54443b2c5b3fb6d2eebe778af32965c2`
- `phase_b_cell_id_status.parquet`:
  `30b4b8057fecce42b2594b5b2e46b4801a26f726a06f038eed1f4b7c83de45cf`
- `cell_id_comparison.json`:
  `818d19a5acadee1e23e39a16b96fe4a6242aa2d453c19d5096179d4393cf7765`
- `support_tail_summary.csv`:
  `43d44f275b9e23073a2cbbbc78d3683b02d8b92ee175273290c41364c07e187e`
- `audit_report.md`:
  `6810fb8e51d5069dfea0e117830ddd01d741ecc622972927fabc8f8816c7d2e7`

## Preserved attempts

- `20260809T174007Z.failed/phase_b`: first 2,367-versus-2,244 count-gate
  failure, before the frozen assignment provenance was supplied; no depth read.
- `20260809T190916Z.failed/phase_b`: frozen-ID gate passed, then an exact
  cross-source center comparison rejected a maximum serialization difference
  below `6e-14` degrees; no depth read.
- `20260809T191132Z/phase_b/run_failed`: depth-enabled run stopped because
  Stage C `n_source_objects` counts all-sounding contributor objects while the
  diagnostic counts eligible-point objects. The partial run is not citable.
- `20260809T191457Z/phase_b`: independently verified result superseded by
  `20260809T191946Z`, which adds explicit exclusion verification and a clearer
  limitation on the unresolved count. Its cohort and numerical metrics agree.

## Prohibited operations

GGM, PINN, GEBCO, product/model residual comparison, MRAR merge, datum/bias
fit, cross-cruise aggregation, sealed-body reads, and sidecar-body reads: `0`.
