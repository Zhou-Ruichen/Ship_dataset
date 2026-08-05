# SCS MRAR/JAMSTEC lineage supplement and exact replay v2

## Goal

Produce immutable, machine-readable evidence that supplements the existing
174,965-cell SCS lineage audit with a frozen MRAR artifact inventory, a
58-file JAMSTEC field-capability audit, contributor-level lineage, and exact
raw-point replay. The result supports a downstream v2 data contract; it does
not correct soundings, choose an aggregation estimator, or assign train/test
roles.

## Frozen Scope

- The cohort is exactly the previously audited 174,965 unique
  `canonical_cell_id` values: 165,966 MRAR and 8,999 JAMSTEC.
- Existing v1 products are read-only. All new outputs live under
  `ncei/derived/scs_ship_qc_v2_preflight/lineage/<UTC_RUN_ID>/`.
- The downstream handoff contract is read as a requirement document only.
  Its SHA256 at planning time is
  `8a152151016de6a45cbef966a78d74e9750c40dffba197ad36cae0a76cdfe94c`.
- The accepted upstream lineage inputs are:
  - `cell_lineage.parquet`, SHA256
    `0d58cf5f18233f1abb6cd111f6167eec7e5c00fc7cdb9667b49f00ef9aa7a74d`;
  - `raw_to_cell_replay.parquet`, SHA256
    `269b23072a0cb5e7c7ca569e03da8a05cca469e7a39271d8920c9a4c389b2ed0`.
- The accepted preflight receipts are:
  - `audit_manifest.json`, SHA256
    `8a0d21dde04de9afc4148d5fa6e9869a2e6836737a6d2677f4ef7fef725ca539`;
  - `verification.json`, SHA256
    `2779d2084ed971044c5457e86149476c45a530ca3760b38a3dbcbf45052983a5`.
- The producer may read only `canonical_cell_id` and
  `interpretation_state` from the frozen preflight candidate table to recover
  the already declared nine aggregation-conflict IDs. It must not read or use
  product-difference fields.

Any frozen hash, cohort, source-count, 52-cell, 2,658-cell, 2,472-cell, or
9-cell closure drift is a hard stop before an output run is published.

## Requirements

### Source artifact freeze

- Inventory `M.rar`, all three extracted text members, every cleaning parquet
  in the delivery directory, the cleaning producer, and direct provenance
  documents. Record absolute and repository-relative paths, logical role,
  byte size, UTC mtime, SHA256, row count/schema where applicable, archive
  member metadata, and explicit version evidence.
- Hash every one of the 58 contributing JAMSTEC `.dat` files and the manifest
  and official metadata files used to interpret them.
- Hash inputs before parsing them and record both expected and observed hashes
  in `audit_manifest.json`.

### MRAR identity and processing evidence

- Investigate the expansion of `MRAR`/`M.rar`, delivery source, and upstream
  processing level using direct files, hashes, README/provenance records,
  archive metadata, retained source metadata, or distinctive geometry only.
- Treat an association with RIAM/Uehara `tscs` as an unverified hypothesis.
  A name similarity, search result, or plausible geography is not an
  association.
- Bound the search to one complete local/direct-artifact pass and one focused
  official-source pass. If no direct fingerprint connects the artifacts,
  close the result as `identity_status=not_recoverable` and
  `source_independence=unknown`; do not broaden the search indefinitely.
- Separate known delivery-chain facts, observed file structure, locally
  applied cleaning, and unrecoverable pre-delivery processing. Do not label a
  historical processing stage as raw merely because it is the earliest file
  retained here.

### JAMSTEC contributor capability audit

- Audit exactly the 58 physical contributor files, joined by canonical
  `file_id`/`relative_path`, not basename.
- Record file format, column count/layout, header state, processing-level
  evidence, and whether row-level longitude, latitude, depth, date, time,
  line, navigation semantics, beam, heading, sonar index, and quality flags
  actually exist.
- Distinguish row coordinates from proven vessel-navigation records.
- Record row order as physical record order only unless a direct field or
  metadata contract proves chronological/ping order. Filename dates and
  official cruise periods must not be promoted to row time.

### Exact contributor and cell replay

- Stream all raw points that contribute to the frozen cohort and retain their
  exact zero-based source-row IDs. Apply the already frozen longitude, depth
  sign, QC, and 1-minute cell rules without changing thresholds.
- Produce an exact file-by-cell contributor table and a cell-by-official-
  cruise contributor table. MRAR rows retain a null
  `official_cruise_id`; a neutral contributor-group key may support table
  uniqueness but must never be presented as a cruise identity.
- Preserve source file, raw row ranges, point/file/cruise counts, exact median,
  NMAD, min/max/range, vertical-datum value/status, processing-level
  value/status, and the five-level status of every factual field.
- Compute medians from all contributing raw point depths. Never aggregate
  chunk medians.
- Preserve all three exact diagnostic alternatives where defined:
  pooled-point median, file-balanced median of exact file-cell medians, and
  cruise-balanced median of exact cruise-cell medians. Do not choose one as
  the corrected or final estimator.
- Re-run the full bounded replay with at least three fixed execution variants
  that change batch size, ascending/descending or seeded file order, and
  worker count. Canonically sorted point/contributor/replay tuples must have
  zero value mismatches and identical canonical digests across variants.
- Persist the 52 historical replay-difference cells with their old value, all
  new exact alternatives, signed differences, contributor details, and the
  Step 04a approximation explanation.
- Persist complete contributor statistics for exactly 2,658 multi-file cells,
  including the 2,472 multi-cruise subset and the nine frozen aggregation-
  conflict cells. Do not delete or pre-resolve any of them.

### Evidence vocabulary and reporting

- Every factual output field has a paired status drawn only from:
  `known`, `officially_unknown`, `not_recoverable`,
  `inferred_from_filename`, `verified_from_source_metadata`.
- `factual_status_counts.tsv` records every artifact/field/status count and
  includes explicit zero rows for all five statuses where absent.
- Record inputs, parameters, batch variants, seed, worker counts, Python and
  library versions, commands, assumptions, output schemas, row counts, paths,
  sizes, and SHA256 values.
- An independent verifier must reopen contractual outputs, recheck hashes,
  schemas, keys, enums, closures, arithmetic, canonical replay digests, and
  forbidden fields before writing `verification.json` with `status=pass`.

## Contractual Outputs

The immutable run must contain at least:

```text
source_artifact_inventory.tsv
mrar_identity_ledger.tsv
jamstec_file_capabilities.tsv
raw_point_contributions.parquet
file_cell_contributors.parquet
cell_official_cruise_contributors.parquet
exact_cell_replay.parquet
legacy_52_replay_differences.parquet
multi_file_cell_summary.parquet
multi_file_contributor_details.parquet
replay_invariance.tsv
factual_status_counts.tsv
audit_report.md
audit_manifest.json
verification.json
```

`audit_manifest.json` inventories every producer output except the verifier's
own receipt. `verification.json` records the manifest hash it verified.

## Acceptance Criteria

- [x] All frozen inputs match their accepted SHA256 before publication.
- [x] The source inventory covers `M.rar`, three extracted files, all cleaning
  parquets, direct provenance/version evidence, 58 JAMSTEC contributors, and
  every official metadata file used.
- [x] MRAR identity/independence conclusions follow the bounded evidence rule;
  absence of a recoverable identity is a completed result, not task failure.
- [x] `jamstec_file_capabilities.tsv` has exactly 58 unique canonical files and
  cannot claim unobserved row-level time/line/ping/beam/heading/quality data.
- [x] Raw-point and exact replay outputs close to 174,965 unique cells and the
  accepted source counts, with no chunk-median aggregation.
- [x] File-cell and cell-cruise aggregates independently recompute from the
  retained raw-point contribution table.
- [x] All fixed execution variants have zero mismatches and identical
  canonical content digests after stable sorting.
- [x] The 52 legacy differences, 2,658 multi-file cells, 2,472 multi-cruise
  cells, and nine aggregation-conflict IDs close exactly.
- [x] Every status-bearing artifact uses only the five-level vocabulary and
  the aggregate counts can be reported explicitly.
- [x] No correction/removal/data-role decision or aggregation winner appears
  in any output schema or report.
- [x] `verification.json` reports `status=pass`; every contractual artifact
  has an absolute path, row count/schema, byte size, and SHA256 in the final
  handoff.

## Out Of Scope

- Reading any GGM/PINN prediction, residual, model error, RMSE, or confirmation
  artifact; running GGM; or training PINN.
- Using GEBCO or any product-consensus value to mark, delete, replace, weight,
  or repair a sounding or cell.
- Deleting/replacing the 171/97 diagnostic candidates, modifying v1, assigning
  train/dev/test/confirmation roles, deciding a final estimator, or correcting
  bathymetry.
- Crossover adjustment: current three-column contributor files lack the
  demonstrated row-level time/line/ping semantics and common vertical datum
  required to authorize it.

## Downstream Decisions Left Open

- Which exact aggregation alternative, if any, becomes the v2 representative
  depth.
- Whether MRAR remains training-only or is excluded from specific evaluation
  roles given `source_independence=unknown` and unrecoverable cruise identity.
- How to treat multi-cruise disagreement and the nine aggregation-conflict
  cells after reviewing contributor evidence.
- Whether additional source data with real time/line/ping/datum fields can be
  obtained before considering crossover adjustment.
