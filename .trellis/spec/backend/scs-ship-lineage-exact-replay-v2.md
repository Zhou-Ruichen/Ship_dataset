# SCS MRAR/JAMSTEC Lineage Supplement and Exact Replay v2

## 1. Scope / Trigger

Use this contract when the frozen 174,965-cell SCS cohort needs exact
MRAR/JAMSTEC contributor evidence beyond the v1 lineage audit. This is an
additive evidence audit: it does not correct depths, select an aggregation
estimator, assign data roles, read downstream model errors, or use GEBCO or
product consensus to judge a sounding.

## 2. Signatures

Run from the repository root:

```bash
python ncei/code/audit_scs_ship_lineage_exact_replay_v2.py \
  --config ncei/configs/scs_ship_lineage_exact_replay_v2.yaml \
  --estimate-only

python ncei/code/audit_scs_ship_lineage_exact_replay_v2.py \
  --config ncei/configs/scs_ship_lineage_exact_replay_v2.yaml \
  --run-id <YYYYMMDDTHHMMSSZ> \
  --confirm-audit

python ncei/code/verify_scs_ship_lineage_exact_replay_v2.py \
  --run-dir ncei/derived/scs_ship_qc_v2_preflight/lineage/<RUN_ID>
```

Full mode requires confirmation and an unused UTC run ID. The producer
publishes atomically only after all replay variants pass. The verifier alone
writes `verification.json` and refuses to overwrite an existing receipt.

## 3. Contracts

The YAML freezes path plus SHA256 for the downstream handoff, v1 lineage and
replay tables, vertical-datum ledger, preflight receipts, candidate membership,
JAMSTEC manifest, `M.rar`, its extracts, local cleaning products, provenance,
and cleaning code. Only `canonical_cell_id` and `interpretation_state` may be
read from the preflight candidate table.

Core closures are:

```text
cells = 174965 (MRAR 165966, JAMSTEC 8999)
JAMSTEC files = 58
official cruises = 19
raw point contributions = 22859691
historical replay differences = 52
multi-file cells = 2658
multi-cruise cells = 2472
aggregation-conflict cells = 9
```

`raw_point_contributions.parquet` is the arithmetic source of truth. File-cell
and cruise-cell medians are recomputed from all selected raw depths, never from
chunk medians. MRAR keeps a null `official_cruise_id` and neutral
`unresolved_source:mrar` group key. The formal MRAR terminal state is
`identity_status=not_recoverable` and `source_independence=unknown` unless a
direct artifact fingerprint is later supplied.

All factual value columns have a paired `<field>_status` drawn only from:

```text
known
officially_unknown
not_recoverable
inferred_from_filename
verified_from_source_metadata
```

The three execution variants must change batch rows, file order, and worker
count. Their canonical raw-point, file-cell, and cell-replay digests must be
identical with zero value mismatches. The immutable run contains source and
identity ledgers, the 58-file capability table, raw/file/cruise/cell Parquets,
focused 52/2658 contributor evidence, invariance and status TSVs, report,
manifest, and verifier receipt.

## 4. Validation & Error Matrix

| Condition | Required behavior |
|---|---|
| Frozen SHA, source count, or cohort closure differs | Abort before publication |
| JAMSTEC join depends on basename | Reject; join by canonical `file_id` and full relative path |
| Raw row time/line/ping/beam/heading/quality is absent | Record absence; do not infer it from filename or cruise period |
| MRAR cruise identity cannot be fingerprinted | Null cruise ID + `not_recoverable`; independence stays `unknown` |
| A file-cell crosses batches | Pool all contributing raw depths before taking the median |
| Any replay variant differs | Abort and remove only the temporary run |
| Output contains correction, role, model-error, GEBCO, or consensus fields | Reject publication |
| Independent arithmetic/hash/status check fails | Do not cite the run; use a new run ID after a code fix |
| Existing run or verification receipt is targeted | Refuse to overwrite |

## 5. Good / Base / Bad Cases

- Good: a JAMSTEC cruise ID comes from inspected official metadata and is
  tagged `verified_from_source_metadata`.
- Base: a three-column file preserves physical record order but has no proven
  time or ping semantics; record `raw_record_order_only` and false capability
  flags.
- Base: MRAR delivery and local cleaning are known while pre-delivery identity
  remains `not_recoverable`.
- Bad: invent a cruise for MRAR from `M.rar` or quadrant filenames.
- Bad: use a median of chunk medians as an exact raw-point median.
- Bad: choose pooled, file-balanced, or cruise-balanced depth as the final v2
  estimator inside this audit.

## 6. Tests Required

```bash
python -m unittest _common.tests.test_scs_ship_lineage_exact_replay_v2
python -m py_compile \
  ncei/code/audit_scs_ship_lineage_exact_replay_v2.py \
  ncei/code/verify_scs_ship_lineage_exact_replay_v2.py
```

Unit tests cover exact medians/NMAD, raw-row ranges, non-cruise MRAR grouping,
canonical digest order invariance, five-level status pairing/counts, and
forbidden schemas. A contractual run additionally requires estimate-only,
three full replay variants, and an independent `verification.json` with
`status=pass`.

## 7. Wrong vs Correct

Wrong:

```python
# Chunk boundaries can change this result and MRAR has no verified cruise ID.
cell_depth = np.median(chunk_medians)
mrar_cruise_id = Path(raw_file).stem
```

Correct:

```python
cell_depth = raw_points.groupby("canonical_cell_id")["depth_m_positive_down"].median()
mrar_cruise_id = None
mrar_cruise_id_status = "not_recoverable"
```
