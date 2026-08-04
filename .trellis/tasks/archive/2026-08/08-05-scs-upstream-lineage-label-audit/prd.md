# SCS upstream lineage and label audit

## Goal

Produce a fact-only upstream lineage audit for the frozen 174,965-cell South
China Sea cohort handed off by `/mnt/data2/06-Projects/12-ggm_scs`. The audit
must let the downstream repository decide label eligibility without exposing
or using any downstream model error.

The permitted claim is limited to provenance: which source records and
official metadata can or cannot support each cell-level field. This task does
not decide whether a cell is suitable for training, development, or final
confirmation.

## Frozen Inputs

| Input | SHA256 at acceptance |
|---|---|
| `downstream_cell_union.parquet` | `89d8771335e3eeb43a4ac370e9a911260618bd3f45212ee708023344179ba456` |
| `counts_closure.json` | `2bec462f27b2293d9b7077c6e80225bada845994ea97e7908e6651ce895a1a2f` |
| `manifest.json` | `606fa69da644d9efd538da3e42e6d96eaad80462eca434c06b0e64f0b5ddbaeb` |
| `group_manifest.parquet` | `4f12d42de0a7b071947b5eb4c7b454a243b99796f9ca6303f4829dfda8054d1f` |

Any hash drift is a hard stop. The cohort must remain 174,965 unique
`canonical_cell_id` values; no global-chain rescan or cohort expansion is
allowed.

## Requirements

- Audit only the handed-off cells and only source records needed by those
  cells.
- P0: verify all 12 external `cruise_id_candidate` groups against official
  JAMSTEC DARWIN/cruise metadata and, where available, NCEI metadata. Record
  vessel, cruise, leg, dates, official spatial/file evidence, observed point
  envelope, and one identity state:
  `official_exact`, `official_leg_ambiguous`, `filename_only`, or `unresolved`.
- Treat multi-leg cruises as one cruise identity. Never create an independent
  cruise identity from a leg. If cell-to-leg assignment is not evidenced,
  retain the cruise identity and mark leg ambiguity.
- P1: create a per-source/per-cruise vertical-datum ledger covering vertical
  datum, sounding reduction, tide correction, ellipsoid/geoid/chart datum, and
  the exact evidence path. Unknown values remain literal `unknown`.
- P2: create one `cell_lineage.parquet` row per frozen
  `canonical_cell_id`, covering source archive, raw file and SHA256, raw row
  IDs, raw point count, official cruise/survey/leg/line/time, sonar, depth
  unit/sign, upstream QC flags, and aggregation method.
- Every P1/P2 factual field has a paired status drawn only from:
  `known`, `officially_unknown`, `not_recoverable`,
  `inferred_from_filename`, `verified_from_source_metadata`.
- Add a row-level `lineage_class`; cells without a defensible raw-row link are
  explicitly `derived_source_no_raw_lineage`, never represented as silently
  missing verified lineage.
- P3: replay coordinate normalization, positive-down conversion, upstream QC,
  1-minute cell assignment, source precedence, and aggregation only for source
  records that can contribute to the frozen cohort. Compare replayed cell
  depth to the handed-off `representative_depth_m` and report raw-point,
  file/cruise counts plus within-file, between-file, and between-cruise NMAD.
- P4: confirm and cite the existing MRAR source-layer conclusion; do not
  re-derive global MRAR processing. The quadrant file may be known while real
  cruise/line identity remains not recoverable.
- Record script version, command, UTC run ID, environment, input/output paths,
  SHA256 values, assumptions, and incomplete/blocked fields.
- Keep outputs immutable under a run-ID directory in this repository and
  return absolute paths plus SHA256 for every contractual deliverable.

## Acceptance Criteria

- [x] All four frozen inputs match the accepted SHA256 values before reading.
- [x] Union closure is exact: 174,965 rows, 174,965 unique non-null
  `canonical_cell_id`, with exactly 165,966 MRAR and 8,999 JAMSTEC rows.
- [x] The P0 ledger has exactly the 12 handed-off candidate groups and only the
  four allowed identity states; each row contains evidence and a track-envelope
  comparison.
- [x] `cell_lineage.parquet` has exactly one row for every frozen
  `canonical_cell_id`, no extras, and no invalid field-status value.
- [x] MRAR raw-row identity is not claimed unless an exact link to original
  source lines is demonstrated; otherwise its cells carry
  `derived_source_no_raw_lineage`.
- [x] The vertical ledger covers every source/cruise represented in the audit
  and uses literal `unknown` rather than inferred datum values.
- [x] Replay output has exactly one row per frozen cell and a diff-status for
  every row; skipped or unrecoverable replays are explicit rather than zeroed.
- [x] Replay closure and depth differences are independently recomputed from
  produced artifacts and summarized by source and status.
- [x] No file or column containing downstream model predictions, residuals,
  RMSE, or model-error values is read by the audit implementation.
- [x] Report and manifest jointly list method, five-level field-status counts,
  four-state identity counts, input/output hashes, incomplete items, and
  allowed/prohibited interpretations.

## Out Of Scope

- Re-running or re-auditing the 5,000+ file global processing chain.
- Reading downstream model errors or selecting/excluding labels based on error.
- Changing any existing raw, derived, validation, or downstream data product.
- Deciding final label eligibility.
- A comprehensive inventory of official South China Sea cruises that never
  entered the downstream workflow; such candidates may be listed separately
  only if encountered from metadata during the contracted audit.

## Open Questions

None. The handoff contract and the user's instruction explicitly authorize
implementation with the boundaries above.
