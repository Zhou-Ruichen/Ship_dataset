# Execution plan

This task is not authorized to execute while its status is `planning`.

## Phase A

- [x] Freeze a new audit run ID and hash the accepted Stage C evidence, the
      20260807T090000Z comparison outputs, source code, schemas, and task
      protocol. Abort if any accepted hash differs from the planning evidence.
- [x] Implement the Phase A producer using retained JSONL/JSON/TSV/Parquet
      evidence only. Do not import or invoke MB-System and do not open a sealed
      body.
- [x] Emit a long-form processing contract and per-TN352-object policy table.
      Close literal commands, flags, parser/environment identities, sidecar
      access, quality states, eligibility, and correction status.
- [x] Recompute supplied total/TN352/SCS counts from selected Parquet columns.
- [x] Build the 0168 old/new cell audit and conserve recovered, eligible, H03,
      added-cell, and changed-median counts.
- [x] Apply the fixed A/B classification. If B, render only an unexecuted
      `TN352-v2-processed` proposal with explicit blockers.
- [x] Implement an independent Phase A verifier and tests for command closure,
      status semantics, exact medians, immutable inputs, TSV/JSON equivalence,
      manifests, and prohibited access.
- [x] Run Phase A producer and its independent verifier. The accepted Phase A
      run is `20260809T174007Z`; verification passed with classification B.

## Phase B freeze

- [x] Require Phase A `verification.json=status=pass` and verify its hashes.
- [x] Copy the approved task protocol into the preserved failed-freeze evidence
      with
      status `approved_frozen`; record the task commit and protocol SHA256.
- [ ] Create the input lock with paths, schemas, row counts, bytes, and SHA256.
- [x] Read only cell identity/geometry columns and form the sorted common-cell
      cohort. The hard gate observed 2,367 rather than 2,244 unique SCS cells,
      wrote a failure receipt, and stopped before writing a passing input lock.
- [ ] Write and hash `common_cell_cohort.parquet`, then exit the freeze process.
      Do not import the Phase B depth reader in this command.

## Phase B run

- [ ] Require immutable protocol/input/cohort locks before opening point-depth
      columns.
- [ ] Select TN352 eligible soundings and MRAR basic-pass points using only the
      frozen selectors. Recompute cell membership and stable-key uniqueness.
- [ ] Recompute source cell medians and abort unless they close to the frozen
      Stage C and MRAR labels.
- [ ] Compute spherical centroids, centroid/minimum distances, the one
      mutual-nearest pair set, nested threshold subsets, depth metrics, and
      100 m occupancy metrics.
- [ ] Emit exactly 2,244 support-cell rows and the three pair-level Parquets.
- [ ] Apply only the registered tail/association rules and render all four
      required report answers, including an explicit no-confirmation boundary.
- [ ] Write Phase B outputs atomically, then write the manifest. Do not write
      `verification.json` from the producer.

## Verification

- [x] Implement an independent Phase B verifier that reconstructs cohort IDs,
      point selectors, medians, geometry, pairs, metrics, nested sets, tail
      decisions, hashes, and access counters.
- [x] Test tie resolution, zero-match cells, dateline-safe spherical centroid,
      threshold inclusivity, occupancy anchoring, positive-down delta sign,
      NMAD, tail zero denominators, and count-drift failure.
- [ ] Run the narrow test modules, syntax checks, Phase A verifier, and Phase B
      verifier from the repository root.
- [ ] Confirm accepted Stage C and reference-run inventories/hashes are
      unchanged after both phases.
- [ ] Record that GGM/PINN/GEBCO/model/product comparison counts are zero.

Expected validation commands after implementation:

```bash
python -m unittest \
  _common.tests.test_scs_tn352_processing_audit \
  _common.tests.test_scs_tn352_mrar_support_audit

python -m py_compile \
  ncei/code/audit_scs_tn352_processing.py \
  ncei/code/verify_scs_tn352_processing_audit.py \
  ncei/code/freeze_scs_tn352_mrar_support.py \
  ncei/code/audit_scs_tn352_mrar_support.py \
  ncei/code/verify_scs_tn352_mrar_support_audit.py
```

The user authorized `task.py start`; Phase A and the Phase B freeze attempt are
recorded below.

## Current stop condition

Phase B is stopped at the pre-depth cohort gate. Current Stage C candidate
labels and current MRAR label/checked-point identities both yield 2,367 common
cells under the frozen selector; the expected value is 2,244. No Phase B depth
column, pair difference, or support metric was read or computed. See
`research/execution-status-20260809T174007Z.md`.
