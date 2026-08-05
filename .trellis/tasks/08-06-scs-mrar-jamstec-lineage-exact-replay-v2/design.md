# Technical Design

## Boundary

This is an additive lineage/replay audit. It consumes only frozen upstream
lineage receipts, minimal preflight membership, direct source artifacts, and
official source metadata. It never reads downstream model artifacts or
product-difference columns and never mutates v1.

The producer writes to a temporary sibling directory and atomically promotes
it to:

```text
ncei/derived/scs_ship_qc_v2_preflight/lineage/<UTC_RUN_ID>/
```

An existing run ID is an error. The independent verifier is the only writer of
`verification.json`.

## Input Boundaries

### Cohort and diagnostic membership

`cell_lineage.parquet` is the authoritative 174,965-key cohort and raw-file/
row-range locator. `raw_to_cell_replay.parquet` provides frozen v1 depth and
the historical 52-cell difference set. The latest preflight manifest and
verification receipts must both pass their frozen hashes before the producer
reads two columns from `candidate_cells.parquet` to obtain the nine already
declared `aggregation_conflict` IDs. No GEBCO or consensus column is loaded.

### Physical sources

MRAR assets are resolved under
`ncei/archive/zhoushuai_processed_M/`. JAMSTEC paths are joined through
`jamstec/multibeam/manifests/file_manifest_points_raw.parquet` by exact
`relative_path` and canonical `file_id`. Basename joins are prohibited because
the corpus contains duplicate basenames across subzip directories.

All source paths and hashes are resolved before raw replay. The current
`SOURCE.md` is evidence input and remains read-only, including user changes.

## Evidence Model

The five-level vocabulary describes how a fact is supported; it does not grade
sounding quality. Each factual value column has one paired status column.

MRAR evidence is separated into four layers:

1. retained bytes and observed geometry/format;
2. documented 2026-05-15 collaborator delivery chain;
3. locally versioned `mrar_v0.1.0` cleaning;
4. pre-delivery identity and processing, which remain unrecoverable unless a
   direct fingerprint is found.

The RIAM/Uehara `tscs` hypothesis is recorded as a hypothesis row. One local
artifact search and one official-source search are sufficient. A result may
be marked associated only with an exact hash, direct README/metadata statement,
or a distinctive geometry/row/file structure match strong enough to identify
the same delivered artifact. Otherwise the terminal state is
`not_recoverable`; independence remains literal `unknown`.

For JAMSTEC, the capability audit records both physical columns and semantic
ceilings. Longitude/latitude columns are known coordinates but are not called
vessel navigation without a source contract. Three-column physical record
order is retained as `raw_record_order_only`; time/ping ordering is not
recoverable from current inputs.

## Data Flow

1. Validate cwd, CLI confirmation, config schema, accepted hashes, run-ID
   immutability, and forbidden paths/columns.
2. Inventory and hash all MRAR/JAMSTEC/direct-metadata inputs; parse archive
   and parquet schemas without changing source files.
3. Complete the bounded MRAR identity evidence ledger.
4. Resolve exactly 58 JAMSTEC contributors by full relative path; scan every
   file to verify row width, parseability, line count, and the absence/presence
   of row-level fields.
5. Stream MRAR and JAMSTEC source points. Apply the frozen normalization, sign,
   QC, and 1-minute cell rules, then retain only cohort contributions with
   zero-based source-row IDs.
6. Stable-sort and write `raw_point_contributions.parquet`; aggregate exact
   file-cell, cell-cruise, and cell-level alternatives directly from its raw
   depths.
7. Join frozen v1 values and materialize the 52-cell and multi-source subsets.
8. Repeat steps 4-6 under fixed execution variants. Compare canonical content
   digests and values, not Parquet byte hashes, because row-group layout may
   vary with batch size.
9. Write status counts, report, and manifest. The verifier reopens outputs and
   recomputes table arithmetic and closure before issuing its receipt.

## Output Contracts

### `source_artifact_inventory.tsv`

One row per direct artifact with path, role, version/status, size, UTC mtime,
SHA256, row count/schema when applicable, and archive-member details. It is the
join target for file hashes so hashes are not repeated in every raw-point row.

### `mrar_identity_ledger.tsv`

One row per tested identity/source/processing claim. Columns distinguish claim,
observed evidence, evidence path/hash/URL, result, identity status,
`source_independence`, processing level, and the paired five-level statuses.

### `jamstec_file_capabilities.tsv`

Exactly 58 rows keyed by `file_id`. It records canonical relative path, format,
layout, processing-level evidence, line count, each physical/semantic field
capability, row-order semantics, cruise metadata and statuses, and source
hashes through the inventory.

### `raw_point_contributions.parquet`

One row per QC-passed source point entering a frozen cell. Core columns are
`canonical_cell_id`, provider, `file_id`, nullable `official_cruise_id`,
`raw_row_id`, normalized coordinates, and positive-down depth. It is stably
sorted by cell, file, and row and is the arithmetic source of every exact
aggregate.

### `file_cell_contributors.parquet`

One row per `(canonical_cell_id, file_id)` with raw-row ranges, exact point
count, median, NMAD, min/max/range, cruise metadata, datum, processing level,
and paired statuses.

### `cell_official_cruise_contributors.parquet`

One row per `(canonical_cell_id, contributor_group_key)`. JAMSTEC group keys
are official cruise IDs. MRAR uses a neutral non-cruise key while
`official_cruise_id` stays null and its status remains `not_recoverable`.
Aggregates are computed over raw points, not file medians.

### `exact_cell_replay.parquet`

Exactly one row per cell. It preserves v1 depth, exact pooled-point median,
exact file-balanced median, exact cruise-balanced median where defined,
counts/dispersion, signed differences, and explicit method labels. Each method
has `diagnostic_only=true`; no final-depth column is created.

### Focused subsets

`legacy_52_replay_differences.parquet` preserves exactly 52 cells and all
contributor/difference evidence. `multi_file_cell_summary.parquet` contains
exactly 2,658 cells with flags for the 2,472 multi-cruise and nine frozen
aggregation-conflict subsets. `multi_file_contributor_details.parquet` is the
complete filtered contributor table for those 2,658 cells.

### Receipts

`replay_invariance.tsv` records variant parameters, raw/contributor/cell row
counts, canonical digests, mismatch counts, and maximum absolute differences.
`factual_status_counts.tsv` is a long table keyed by artifact, field, and each
of the five statuses. `audit_manifest.json` carries all input/output paths,
schemas, rows, bytes, hashes, versions, commands, assumptions, and forbidden-
input confirmation. `verification.json` cites the verified manifest SHA256.

## Exactness and Determinism

The baseline and two alternates change all three execution dimensions:

| Variant | Batch rows | File order | Workers | Seed |
|---|---:|---|---:|---:|
| baseline | 1,000,000 | ascending | 1 | 42 |
| reverse | 250,000 | descending | 2 | 42 |
| seeded | 333,333 | seeded permutation | 4 | 42 |

The exact values are order-independent medians over raw IEEE-754 depths.
Canonical tuple hashing uses fixed column order, stable row order, explicit
null encoding, and deterministic numeric serialization. The acceptance rule
is zero row/value mismatches; an approximate tolerance cannot hide a changed
contributor set.

## Validation Boundaries

- Validate hash and schema at file ingress.
- Validate row width, numeric parse, line count, and exact relative-path join
  at source ingress.
- Validate unique keys, raw-row membership, five-state enums, and arithmetic at
  every produced table boundary.
- Validate all aggregate values by regrouping the persisted raw-point table,
  not by trusting producer in-memory summaries.
- Validate forbidden output schemas against correction, removal, weight, role,
  prediction, residual, model-error, GEBCO, and product-consensus tokens.

## Failure and Rollback

Hash, schema, closure, parse, enum, arithmetic, or invariance drift aborts and
leaves no published run directory. Existing raw, cleaned, v1, lineage, and
preflight products are never modified. Rollback is limited to disregarding the
new run and reverting task-owned code/config/spec files; source data is not
deleted.

## Trade-Offs

- Persisting selected raw contributions costs disk space, but it makes the
  exact medians independently recomputable and removes trust in chunk-level
  intermediates.
- Three full bounded replays add I/O cost, but directly test the requested
  batch/order/worker invariance and remain limited to the frozen SCS cohort.
- Keeping three estimator alternatives increases table width, but avoids an
  unsupported scientific decision in an evidence-only task.
