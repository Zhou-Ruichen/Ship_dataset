# Implementation plan

## Ordered checklist

- [x] Resolve the open approval gate for Stage A to Stage B transition.
- [x] Freeze config, repository snapshots, dirty-state receipts, SCS geometry,
  current 19, exposed 12, downstream no-confirmation receipt, MRAR artifacts,
  official source endpoints, status enums and stop rules.
- [x] Implement shared metadata/evidence helpers for stable JSON, SHA256,
  atomic writes, official URL capture, candidate ID/leg normalization and bbox
  intersection without any sounding-value reader.
- [x] Implement the exposure-registry builder across both current trees, git
  history, tasks, configs, manifests, output receipts, notebooks, figure
  producers and archive identity/hash evidence.
- [x] Implement the single bounded MRAR local/history/adjacent-artifact pass and
  its terminal stop condition.
- [x] Implement NCEI ArcGIS metadata discovery and per-cruise official ISO/XML,
  file-list and use-constraint capture; add the bounded JAMSTEC metadata pass.
- [x] Build all-candidate registry, negative-result ledger and deterministic
  hard-gate/ranking result without downloading candidate archives.
- [x] Generate and independently verify the immutable Stage A discovery run,
  including `preseal_lock.json` and exact selected candidate count.
- [x] Freeze Stage A.1 against accepted Stage A hashes, replace the old top-five
  policy with the complete chronology-first 2018+ unexposed cohort, and retain
  the named five cruises in the comparison.
- [x] Implement allowlisted official directory-metadata GET and physical-object
  HEAD collection with no Range header, object body read, or GET fallback.
- [x] Implement physical object lock, per-cruise/all-candidate byte budgets,
  revised branch qualifications and an independent offline A.1 verifier.
- [x] Publish and independently verify the immutable Stage A.1 discovery run;
  record all paths, rows, schemas, SHA256 values and technical Stage B blocks.
- [x] Freeze the exact four-cruise Stage A.2 primary set, explicit
  excluded/deferred set, no-replacement rule and 12 GiB aggregate cap.
- [x] Implement offline exact-integer listing-size recovery, primary physical
  lock, budgets, candidate decisions and Stage B dry-run plan.
- [x] Implement the independent Stage A.2 verifier and separately authorized
  opaque Stage B downloader; ensure dry-run contains no network path.
- [x] Publish and verify the immutable Stage A.2 run, execute only the read-only
  downloader dry-run, record the receipt and stop before Stage B.
- [x] Harden Stage B.0 resolved-URL and Last-Modified pre-body checks, exact
  authorization binding, safe run ID/fixed root and failed-unsealed receipt.
- [x] Implement the independent Stage B object verifier, final sealed manifest
  and access-lock producers without executing a download.
- [x] Publish and independently verify the zero-network Stage B.0 readiness run
  `20260805T224911Z`; 13 offline tests pass and dry-run network/download counts
  are both zero.
- [ ] After the approved Stage B gate, download only presealed URLs as opaque
  `*.part` files, record transport headers/commands, atomically seal bytes and
  prohibit archive enumeration/parsing.
- [ ] Build `sealed_archive_manifest.tsv`, final audit manifest/report and the
  sealed-directory access lock.
- [ ] Run the independent acquisition verifier, rehash every artifact/archive,
  recompute overlap and selection closure, and require `status=pass`.
- [ ] Run unit tests, syntax checks, estimate/discovery dry runs, source guard,
  `git diff --check`, scoped review and Trellis context validation.
- [ ] Update backend spec with the reusable sealed-confirmation contract;
  commit task-owned code/config/tests/spec/task artifacts, record the session
  and archive only after returning the downstream path/SHA handoff.

## Expected implementation files

```text
ncei/configs/scs_v2_sealed_confirmation.yaml
ncei/code/discover_scs_v2_sealed_confirmation.py
ncei/code/acquire_scs_v2_sealed_confirmation.py
ncei/code/verify_scs_v2_sealed_confirmation.py
_common/tests/test_scs_v2_sealed_confirmation.py
.trellis/spec/backend/scs-v2-sealed-confirmation.md
```

Contractual data roots:

```text
ncei/derived/scs_v2_sealed_confirmation/discovery/<DISCOVERY_RUN_ID>/
ncei/archive/scs_v2_sealed_confirmation/<ACQUISITION_RUN_ID>/
```

## Planned validation commands

```bash
cd /mnt/data2/00-Data/ship

python -m unittest _common.tests.test_scs_v2_sealed_confirmation
python -m py_compile \
  ncei/code/discover_scs_v2_sealed_confirmation.py \
  ncei/code/acquire_scs_v2_sealed_confirmation.py \
  ncei/code/verify_scs_v2_sealed_confirmation.py

python ncei/code/discover_scs_v2_sealed_confirmation.py \
  --config ncei/configs/scs_v2_sealed_confirmation.yaml \
  --estimate-only

python ncei/code/discover_scs_v2_sealed_confirmation.py \
  --config ncei/configs/scs_v2_sealed_confirmation.yaml \
  --run-id <DISCOVERY_RUN_ID> --confirm-discovery

python ncei/code/verify_scs_v2_sealed_confirmation.py \
  --discovery-dir ncei/derived/scs_v2_sealed_confirmation/discovery/<DISCOVERY_RUN_ID>

python ncei/code/discover_scs_v2_sealed_confirmation_stage_a1.py \
  --config ncei/configs/scs_v2_sealed_confirmation_stage_a1.yaml \
  --run-id <STAGE_A1_RUN_ID> --confirm-stage-a1

python ncei/code/verify_scs_v2_sealed_confirmation_stage_a1.py \
  --run-dir ncei/derived/scs_v2_sealed_confirmation/discovery/<STAGE_A1_RUN_ID>

python ncei/code/finalize_scs_v2_sealed_confirmation_stage_a2.py \
  --config ncei/configs/scs_v2_sealed_confirmation_stage_a2.yaml \
  --run-id <STAGE_A2_RUN_ID> --confirm-stage-a2

python ncei/code/verify_scs_v2_sealed_confirmation_stage_a2.py \
  --run-dir ncei/derived/scs_v2_sealed_confirmation/discovery/<STAGE_A2_RUN_ID>

python ncei/code/acquire_scs_v2_sealed_confirmation_stage_b.py \
  --a2-run ncei/derived/scs_v2_sealed_confirmation/discovery/<STAGE_A2_RUN_ID> \
  --dry-run

python ncei/code/prepare_scs_v2_sealed_confirmation_stage_b0.py \
  --config ncei/configs/scs_v2_sealed_confirmation_stage_b0.yaml \
  --run-id <STAGE_B0_RUN_ID> --confirm-stage-b0-readiness

python ncei/code/verify_scs_v2_sealed_confirmation_stage_b0.py \
  --run-dir ncei/derived/scs_v2_sealed_confirmation/readiness/<STAGE_B0_RUN_ID>

# Future only, after a separate Stage B authorization:
python ncei/code/acquire_scs_v2_sealed_confirmation_stage_b.py \
  --a2-run ncei/derived/scs_v2_sealed_confirmation/discovery/20260805T221441Z \
  --execute --authorization-receipt <AUTHORIZED_RECEIPT> \
  --acquisition-run-id <ACQUISITION_RUN_ID> --confirm-stage-b-download

python ncei/code/verify_scs_v2_sealed_confirmation_stage_b.py \
  --acquisition-dir ncei/archive/scs_v2_sealed_confirmation/<ACQUISITION_RUN_ID>

git diff --check
```

## Review gates

- Stage A code and queries must not contain candidate sounding/depth endpoints,
  reference-product inputs, model outputs or downstream error artifacts.
- Selected IDs and URLs are immutable after the preseal lock. A failed download
  cannot trigger replacement from a reserve candidate in the same run.
- `ever_read_by_repo=false` requires every defined exposure check to pass;
  missing evidence is `unknown` and excluded.
- Candidate `available_fields` are official metadata claims only. A generic
  sonar format capability is not proof that a particular archive retains it.
- No archive parser, member listing, extracted file, cell depth, QC result,
  residual, figure or crossover artifact may exist in either run.
- A verifier failure or selected-count shortfall blocks Stage B or downstream
  handoff without weakening the protocol.

## Rollback points

- Before Stage A publication: discard only the temporary discovery directory.
- After Stage A pass: preserve it as an immutable positive or negative result;
  use a new run ID for changed rules or candidates.
- During Stage B: retain command/error evidence and retry only the same frozen
  URL; do not replace candidates.
- After sealing: rollback means downstream ignores the acquisition run. Never
  delete or overwrite the sealed archives programmatically.
