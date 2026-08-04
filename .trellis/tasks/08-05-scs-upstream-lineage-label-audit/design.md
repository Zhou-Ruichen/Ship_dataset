# Technical Design

## Boundary

The audit treats the downstream union as an immutable cohort manifest, not as
an upstream source of lineage truth. Only the label value
`representative_depth_m` is used for replay comparison. No prediction,
residual, metric, or model output is read.

The implementation is a one-off, rerunnable audit script under `ncei/code/`.
It accepts all handoff paths as explicit CLI arguments and writes to a new UTC
run directory under `ncei/derived/scs_upstream_lineage_audit/`.

## Data Flow

1. Hash the four handoff files and stop on any mismatch.
2. Read the minimal union columns and enforce cohort/key/source closure.
3. Join JAMSTEC cells by exact `canonical_cell_id == cell_id` to JAMSTEC global
   cells and per-file cells, then use the file manifest to locate and replay
   physical raw `.dat` paths.
4. Join MRAR cells by exact `cell_id` to the regional MRAR file-cell product,
   then stream the physical quadrant text to recover original source rows.
   Never promote the earlier dense derived point index to a raw row identity.
5. Parse the locally retained official JAMSTEC DARWIN English PDFs, hash each
   PDF, and normalize their cruise/leg/member-list metadata. Filename-only
   facts remain filename inference even when they look plausible.
6. Build cell lineage and replay tables from exact contributor sets. A
   contributor is selected by matching source cell IDs, not by scanning global
   archives.
7. Write artifacts atomically, generate report/manifest, then independently
   validate produced schemas, keys, counts, enums, hashes, and replay diffs.

## Output Contracts

### `cell_lineage.parquet`

One row per `canonical_cell_id`. Required values use snake_case columns; every
contract factual field has `<field>_status`. Contributor-valued fields use
stable JSON arrays sorted by source/file/row ID so Parquet rows remain scalar
and deterministic. `lineage_class` distinguishes exact raw lineage from
`derived_source_no_raw_lineage`.

### `source_identity_ledger.csv`

Exactly 12 rows. The primary key is `cruise_id_candidate`. It contains local
candidate paths, official cruise/vessel/leg/date/file/envelope evidence,
observed envelope, the four-state identity result, field-level five-state
statuses, evidence URLs/paths, and notes.

### `vertical_datum_ledger.csv`

One row per represented source/cruise. Datum-related values are `unknown`
unless an official source states them. Absence from an inspected official
metadata document is `officially_unknown`; no generic vessel or IHO default is
substituted.

### `raw_to_cell_replay.parquet`

One row per union cell with replay source, replay result, frozen and replayed
depth, signed/absolute diff, contributor counts, and three NMAD layers. A layer
with fewer than two independent units is null with an explicit status, not
zero.

### Sidecars

`diff_summary.json`, `audit_manifest.json`, and `audit_report.md` record the
run command, environment, schemas, counts, hashes, assumptions, validation
results, and incomplete items.

## Evidence Semantics

The only allowed field statuses are the handoff five-state vocabulary. They
describe evidence quality, not data quality. Identity state is a separate
four-state P0 result. Replay result is operational and is `exact` or
`different`; its evidence status is separately recorded as `known`.

For official spatial comparison, the observed contributor envelope is tested
against the official bathymetry-file envelope or cruise-track envelope when an
official numeric/geometry source is available. A cruise PDF that only names
the cruise cannot support an envelope claim.

## Failure And Rollback

- Hash, cohort, key, schema, or enum drift aborts before outputs are promoted.
- Outputs are written to a new run directory; no existing product is mutated.
- Partial `.tmp` files are not contractual artifacts.
- Because the audit is additive, rollback consists of disregarding the new run
  directory and reverting only the task's code/research files; raw and existing
  derived products are untouched.

## Trade-Offs

- Contributor arrays make the cell table wider but preserve a one-row-per-cell
  contract without silently retaining only a dominant file.
- Hashing every contributing raw file is I/O-heavy but required for defensible
  raw lineage; hashing is restricted to files that hit the frozen cohort.
- Official web metadata is saved as evidence metadata/URLs, while the local
  downloaded official PDFs provide stable byte-level evidence where present.
