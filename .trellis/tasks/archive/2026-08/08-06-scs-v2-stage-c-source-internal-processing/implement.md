# Execution plan

- [ ] Freeze active authorization receipt, safe processing run ID and output
  root; verify all C1a and Stage B hashes before body access.
- [ ] Implement role-filtered source reader: open only `.mb58.gz`, with exact
  size/SHA before/after guards; keep every sidecar body closed.
- [ ] Implement atomic U3/U0 time preflight, MB-System command capture and
  field recovery ledger.
- [ ] Implement sounding lineage, source processing rows, source-internal QC
  flags and exact cell-by-cruise aggregation.
- [ ] Implement `verify_scs_v2_stage_c_processing.py` with independent checks
  for schemas, keys, hashes, roles, invalid-time behavior and forbidden
  references. It may reopen derived outputs and `aggregation.sqlite`, but never
  a sealed body or parser.
- [ ] Run the producer with active authorization and preserve any failure
  receipt; publish only after verifier `status=pass`.
- [ ] Run final tests and record all machine-readable artifact hashes.
- [ ] Stop before any external product/model/MRAR/confirmation evaluation.

Validation commands:

```bash
python -m unittest _common.tests.test_scs_v2_stage_c_processing
python -m py_compile ncei/code/process_scs_v2_stage_c_source_internal.py
python -m ncei.code.verify_scs_v2_stage_c_processing --run-dir <PROCESSING_RUN_DIR>
```
