# Execution plan

- [x] Freeze run ID `20260808T231659Z`; verify the output path does not exist.
- [x] Create an isolated C.2.2 execution tree at commit `3131f72`.
- [x] Verify readiness `20260809T030000Z`, frozen code/contract hashes, the
      66-test suite, the 192-body whitelist, and prior-run invariance baseline.
- [x] Materialize one active authorization receipt for the frozen run ID.
- [x] Execute the Stage C producer once and retain all logs and ledgers.
- [x] Run the production verifier and require `status = pass`.
- [x] Compute source-internal counts, per-cruise/SCS-rectangle summaries, 0168
      recovery, and cell differences against `20260807T090000Z`.
- [x] Compute schemas and SHA256 values for every Parquet plus manifest and
      verification artifacts.
- [x] Write and validate the downstream handoff receipt under `research/`.
- [x] Confirm prior run hashes/directories are unchanged and report no external
      product, GGM, PINN, MRAR, datum/bias, or model operation.

## Stop rules

- Stop before body access if readiness, code, contract, test, manifest, parser,
  authorization, or old-run checks fail.
- Stop before reporting the output if the production verifier fails.
- Do not modify or retry inside a failed run directory. Any retry requires a
  new run ID and separate authorization.
