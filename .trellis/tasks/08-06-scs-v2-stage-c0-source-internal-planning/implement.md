# Future Stage C execution plan

This checklist is intentionally inactive. The task remains in `planning` and
must not be started until the user separately approves Stage C.

- [ ] Build an immutable MB-System `5.8.3beta16` environment from commit
  `1d9a52ce076c3c3c5f0150b9bcaa30fa108c7422`; record image digest and build
  inputs.
- [ ] Acquire or generate the independent non-candidate format-58 fixture,
  freeze its bytes/oracle hashes, and run the full fixture contract without
  mounting Stage B.
- [ ] Implement the parser adapter and exact schemas without candidate-data
  access; unit-test synthetic valid/flagged/null/duplicate cases.
- [ ] Implement the Stage C producer with exact authorization validation,
  sealed-root read-only guards, derived-only writes and atomic publication.
- [ ] Implement the independent verifier and forbidden product/model/training
  source guards.
- [ ] Freeze source code, config, command ledger, environment, fixture, QC,
  schema and verifier SHA256 values in a new readiness run.
- [ ] Obtain a separately signed Stage C authorization receipt bound to those
  hashes and a safe processing run ID.
- [ ] Rehash Stage B inputs before the first object body read; abort on any
  mismatch.
- [ ] Parse only allowed roles, preserve sounding-level lineage, and produce
  exact cell-by-official-cruise candidate aggregates.
- [ ] Run the independent verifier; publish only on `status=pass`.
- [ ] Stop before any GGM/PINN/product/model evaluation or role promotion.

Planned validation commands, with exact filenames to be finalized and hashed
in the readiness run:

```bash
python -m unittest _common.tests.test_scs_v2_stage_c_source_internal
python -m py_compile \
  ncei/code/process_scs_v2_stage_c_source_internal.py \
  ncei/code/verify_scs_v2_stage_c_source_internal.py

python ncei/code/prepare_scs_v2_stage_c_readiness.py \
  --config ncei/configs/scs_v2_stage_c_source_internal.yaml \
  --run-id <READINESS_RUN_ID> --confirm-readiness

python ncei/code/process_scs_v2_stage_c_source_internal.py \
  --authorization-receipt <ACTIVE_RECEIPT> \
  --processing-run-id <PROCESSING_RUN_ID> --confirm-stage-c

python ncei/code/verify_scs_v2_stage_c_source_internal.py \
  --run-dir ncei/derived/scs_v2_sealed_confirmation/stage_c/<PROCESSING_RUN_ID>
```
