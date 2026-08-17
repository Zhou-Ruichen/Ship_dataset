# Guide: Research Code Review

Use this checklist before considering a change complete.

## Correctness

- [ ] The code addresses the real failure or requested behavior.
- [ ] Data assumptions are explicit.
- [ ] Shapes, schemas, units, missing values, and coordinate conventions are
      clear where relevant.
- [ ] Errors fail loudly at boundaries instead of producing fake success.

## Reproducibility

- [ ] Parameters, configs, or retained commands are the source of truth.
- [ ] Retained run outputs include manifest, command/config, seed or randomness
      state, environment freeze, data/source record, assumptions, and result
      files.
- [ ] Any result claim is backed by an actual retained artifact.
- [ ] Durable data products have manifests and rebuild instructions.

## Anti-Bloat

- [ ] No copied analysis, data-processing, or evaluation scripts.
- [ ] No `*_v2`, `*_final`, or backup source directories.
- [ ] New reusable logic is in the project's source area.
- [ ] One-off exploration stayed in `notebooks/`, scratch output, or a thin
      script.
- [ ] Superseded variants were deleted, not left to accumulate; every deletion
      is listed, and no experiment record was removed without asking.

## Verification

- [ ] Ran the narrowest meaningful command.
- [ ] If no command was run, the reason is stated.
- [ ] Test or smoke-check scope matches the risk of the change.
- [ ] No metric-value assertion gates the task; a missed target is reported
      as a finding, not treated as failure.
- [ ] No TDD scaffolding or result assertions were added; sanity checks
      verify code, not outcomes.
- [ ] One-off test and diagnostic code was deleted, not committed.
