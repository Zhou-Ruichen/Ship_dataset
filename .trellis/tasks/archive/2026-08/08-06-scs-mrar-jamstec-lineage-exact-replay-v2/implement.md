# Implementation Plan

## Ordered Checklist

- [x] Freeze the config, handoff receipt, prior lineage/preflight hashes,
  accepted schemas/counts/status vocabulary, and forbidden inputs/outputs.
- [x] Add narrow shared helpers only where the existing lineage/preflight code
  already duplicates normalization, cell-ID, NMAD, hashing, and stable JSON;
  otherwise reuse the existing implementation without refactoring unrelated
  pipeline code.
- [x] Implement source inventory and MRAR evidence-ledger generation, including
  archive member inspection and the bounded RIAM/Uehara `tscs` hypothesis
  check with an explicit terminal result.
- [x] Implement the 58-file JAMSTEC capability audit using exact `file_id` and
  relative-path joins plus full structural scans.
- [x] Implement raw-point extraction for the frozen cohort with exact source
  row IDs and persisted point contributions.
- [x] Build exact file-cell, cell-cruise, and cell replay outputs directly from
  persisted raw points; retain pooled/file-balanced/cruise-balanced methods as
  diagnostic alternatives only.
- [x] Build the exact 52-cell, 2,658-cell, 2,472-cell, and 9-cell focused
  outputs with closure assertions and complete contributors.
- [x] Run the three fixed batch/order/worker variants and publish canonical
  content-digest/value comparisons.
- [x] Generate five-level status counts, report, manifest, schemas, and hashes;
  confirm no forbidden decision or model/product field appears.
- [x] Implement and run an independent verifier that reopens every artifact
  and recomputes contributor/cell arithmetic from raw-point contributions.
- [x] Run focused unit tests, syntax checks, estimate-only mode, the full
  immutable audit, verifier, `git diff --check`, and scoped review.
- [x] Update the backend spec only with reusable new contracts, commit task-
  owned code/config/tests/spec/task artifacts, record the session, and archive
  the task after the downstream handoff is complete.

## Expected Implementation Files

```text
ncei/configs/scs_ship_lineage_exact_replay_v2.yaml
ncei/code/audit_scs_ship_lineage_exact_replay_v2.py
ncei/code/verify_scs_ship_lineage_exact_replay_v2.py
_common/tests/test_scs_ship_lineage_exact_replay_v2.py
.trellis/spec/backend/scs-ship-lineage-exact-replay-v2.md
```

Existing v1 producers and `ncei/archive/zhoushuai_processed_M/SOURCE.md` are
read-only for this task.

## Validation Commands

```bash
cd /mnt/data2/00-Data/ship

python -m unittest _common.tests.test_scs_ship_lineage_exact_replay_v2
python -m py_compile \
  ncei/code/audit_scs_ship_lineage_exact_replay_v2.py \
  ncei/code/verify_scs_ship_lineage_exact_replay_v2.py

python ncei/code/audit_scs_ship_lineage_exact_replay_v2.py \
  --config ncei/configs/scs_ship_lineage_exact_replay_v2.yaml \
  --estimate-only

python ncei/code/audit_scs_ship_lineage_exact_replay_v2.py \
  --config ncei/configs/scs_ship_lineage_exact_replay_v2.yaml \
  --run-id <YYYYMMDDTHHMMSSZ> \
  --confirm-audit

python ncei/code/verify_scs_ship_lineage_exact_replay_v2.py \
  --run-dir ncei/derived/scs_ship_qc_v2_preflight/lineage/<RUN_ID>

git diff --check
```

## Review Gates

- Do not create a published run directory before all accepted hashes and
  closures pass.
- Do not join JAMSTEC contributors by basename or infer row semantics from a
  filename/cruise period.
- Do not associate MRAR with RIAM/Uehara `tscs` without a direct artifact
  fingerprint; close the bounded search instead of relaxing evidence.
- Do not compute exact medians from chunk medians or historical file-cell
  approximations.
- Do not hide undefined cruise-balanced values behind zeros or assumed cruise
  IDs.
- Do not let a product-derived value enter raw replay, contributor statistics,
  correction logic, or membership beyond the frozen nine-ID receipt.
- Do not publish if any replay variant differs or the independent verifier does
  not report `status=pass`.

## Rollback Points

- Before full replay: estimate-only output may be discarded; no immutable run
  exists.
- During full replay: only the task-owned temporary run may be abandoned.
- After producer completion but verifier failure: keep the run non-contractual,
  diagnose without overwriting it, and use a new run ID after fixes.
- After verification: rollback means downstream ignores the new run; v1 and
  all source artifacts remain unchanged.
