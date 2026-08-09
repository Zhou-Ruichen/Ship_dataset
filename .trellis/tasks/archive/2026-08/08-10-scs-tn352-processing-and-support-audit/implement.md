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
- [x] Freeze the user-supplied 2,244-ID assignment and cohort amendment hashes.
- [x] Read only frozen/TN352/MRAR raw-support identity and geometry columns.
      Verify 2,244/2,244 frozen IDs have current support, register the additional
      123 current raw-support cells, and identify `1min_6739_18005` as the only
      TN352 candidate without MRAR raw support.
- [x] Create the input lock with paths, schemas, row counts, bytes, environment,
      commands, and SHA256.
- [x] Write and hash `cell_id_comparison.json`,
      `phase_b_cell_id_status.parquet`, and `common_cell_cohort.parquet`, then
      exit the freeze process.
      Do not import the Phase B depth reader in this command.

## Phase B run

- [x] Require immutable protocol/input/cohort locks before opening point-depth
      columns.
- [x] Select TN352 eligible soundings and MRAR basic-pass points using only the
      frozen selectors. Recompute cell membership and stable-key uniqueness.
- [x] Recompute source cell medians and abort unless they close to the frozen
      Stage C and MRAR labels.
- [x] Compute spherical centroids, centroid/minimum distances, the one
      mutual-nearest pair set, nested threshold subsets, depth metrics, and
      100 m occupancy metrics.
- [x] Emit exactly 2,244 support-cell rows and the three pair-level Parquets.
- [x] Apply only the registered tail/association rules and render all four
      required report answers, including an explicit no-confirmation boundary.
- [x] Write Phase B outputs atomically, then write the manifest. Do not write
      `verification.json` from the producer.

## Verification

- [x] Implement an independent Phase B verifier that reconstructs cohort IDs,
      point selectors, medians, geometry, pairs, metrics, nested sets, tail
      decisions, hashes, and access counters.
- [x] Test tie resolution, zero-match cells, dateline-safe spherical centroid,
      threshold inclusivity, occupancy anchoring, positive-down delta sign,
      NMAD, tail zero denominators, and count-drift failure.
- [x] Run the narrow test modules, syntax checks, retained Phase A verification,
      and Phase B
      verifier from the repository root.
- [x] Confirm accepted Stage C and reference-run inventories/hashes are
      unchanged after both phases.
- [x] Record that GGM/PINN/GEBCO/model/product comparison counts are zero.

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

The user authorized `task.py start`, then supplied the exact frozen assignment
and its lineage after the first count-gate stop.

## Accepted result

Phase A `20260809T174007Z` passed with classification
`B. official_raw_source_development_label`. Final Phase B run
`20260809T191946Z` passed independent verification. It analyzed exactly the
2,244 frozen IDs, excluded all 123 `raw_support_only_not_in_frozen_scalar_pair`
IDs, and emitted 29,600 / 32,102 / 32,302 mutual-nearest pairs at 100 / 250 /
500 m. See `research/execution-status-20260809T191946Z.md`.
