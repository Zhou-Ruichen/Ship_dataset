# Technical design

## Flow

```text
active authorization receipt
  -> manifest/access/input hash gate
  -> exact role selection
  -> read-only source object rehash
  -> derived-only gzip + MB-System mblist/mbinfo
  -> atomic time preflight and U3/U0 join
  -> sounding lineage + source processing + field ledger
  -> source-internal hard QC/review flags
  -> exact cell x official-cruise aggregation
  -> independent verifier
  -> immutable publication or failed_processing receipt
```

The producer writes only under a sibling temporary directory of the requested
processing run. It never writes to the Stage B archive. It processes manifest
rows in deterministic order and uses one worker; deterministic invariance is
checked by rerunning aggregation from the persisted sounding table with the
same contract.

## Object and field policy

The physical object key is `acquisition_run_id/relative_path`; the content
SHA256 is integrity-only. Official cruise identity comes from the manifest.
Parser `M/N/#/X/Y/z/H` fields receive direct parser evidence statuses; line,
native IDs, exact quality code, horizontal datum and vertical datum remain
unknown without direct evidence. `.fnv`, `.inf`, and `.fbt` remain unopened in
this execution; their Stage B manifest hashes are retained as provenance and
no sidecar field is used to invent a sounding value.

## Atomic time handling

The adapter first validates every M field in both U3 and U0 text outputs. Any
failure returns a file-level failure object before the join or any output row
is committed. Valid files use the C1a parser-ping rule and keep non-null UTC
timestamps. This makes the primary key, field ledger and cell eligibility
semantics consistent.

## Output ownership

The producer owns `source_object_processing`, `sounding_lineage`,
`cell_cruise_contributors`, `cell_cruise_candidates`, and
`field_recovery_ledger`, plus command/access/audit manifests. The independent
verifier reopens only derived outputs and manifest metadata; it does not reopen
sealed sources or call a parser.

## Stop conditions

Stop before the next permitted body read on any authorization/input/hash/
Last-Modified mismatch, inaccessible exact object, decompression/parser
failure, time contract failure, duplicate key, forbidden reference, output
path escape or changed sealed metadata. Only the 192 `.mb58.gz` bodies are
opened; all sidecars, including the 192 `.fbt` bodies, remain unopened and are
represented by their Stage B manifest hashes. Preserve a machine-readable
`failed_processing` receipt and do not publish a candidate-ready run.
