# SCS v2 Stage C.2.2 contract closure

## Goal

Correct the remaining C.2.1 defects found by an independent audit. The task
must make U3 and U0 non-finite navigation produce the same per-sounding H03
result, and must bind future authorization and verification to the files frozen
inside one new immutable readiness run. This task does not authorize Stage C.

## Confirmed defects

1. The production-chain constant points to `20260809T020000Z`, which has no
   `verification.json`. The later pass run, `20260809T020001Z`, is not consumed
   by the processor, authorizer, or production verifier.
2. A present U0 row with non-finite X or Y keeps native quality `good`, but its
   navigation defect is discarded before QC. If U3 is finite, the sounding is
   incorrectly eligible and receives a cell.
3. Production authorization compares receipt hashes with mutable working-tree
   files. It does not require those files to match the SHA256 values frozen by
   readiness, so coordinated post-readiness drift can pass.
4. The production-verifier fixture constructs its authorization receipt by
   hand and covers only U3-invalid navigation.

## Requirements

1. U3 or present U0 X/Y NaN or Inf is a per-sounding navigation failure. It
   must not abort the source object.
2. A present U0 key keeps `native_quality_state = good`, including when its X/Y
   value is non-finite.
3. With valid depth, either source's non-finite navigation produces exactly
   `H03_NAVIGATION_RANGE`: no H02, no H04, no hard pass, no cell eligibility,
   and null `lon_bin`, `lat_bin`, and `cell_id`. Depth remains present.
4. Missing or invalid time, duplicate keys, structural parse failures, and
   finite U0/U3 value mismatches retain their existing whole-object failure
   behavior.
5. Row and batch sounding paths must emit the same values for every field.
6. The output must carry enough explicit navigation state for the production
   verifier to check U0-invalid and U3-invalid results independently of the
   output coordinates.
7. Active receipts must have the exact accepted key set and recursively reject
   every string containing `<REQUIRED` in dictionaries or lists.
8. The authorizer, processor, and production verifier must each require an
   inactive pass readiness and compare the template, helper, processor,
   authorizer, production verifier, output schema, QC rules, and verification
   rules against SHA256 values frozen in that readiness.
9. The production authorization template is the immutable snapshot in the
   bound readiness run. The source template may be used only to create and
   verify that snapshot before readiness verification.
10. The new readiness manifest must bind the helper, processor, authorizer,
    production verifier, readiness producer/verifier, all relevant tests,
    C.2.1 and C.2.2 task contracts, output/QC/verification rules, and the
    template snapshot.
11. `20260809T020000Z` must be recorded as incomplete/failed readiness;
    `20260809T020001Z` must be recorded as superseded and not authorizable.
    Neither run may be changed.
12. The new readiness must contain no candidate access or output: all body-read,
    decompression, sounding, and cell counts are zero; Stage C authorization and
    confirmation eligibility remain false.

## Acceptance criteria

- [ ] U3-invalid/U0-valid, U3-valid/U0-invalid, and both-invalid fixtures each
      retain valid depth and produce exactly H03 with no cell.
- [ ] A valid prefix remains eligible and aggregatable when a later U0-invalid
      sounding is excluded from eligible/contributor/candidate inputs.
- [ ] Row and batch results match field by field for all dual-source navigation
      fixtures.
- [ ] NaN/negative time and duplicate-key fixtures still emit no raw rows.
- [ ] A synthetic producer run containing both U3-invalid and U0-invalid rows
      passes the real production verifier.
- [ ] The synthetic active receipt is produced by the real authorizer logic.
- [ ] Tests reject wrong readiness ID, missing readiness verification, every
      listed code/template SHA drift, nested placeholders, missing/extra receipt
      fields, and wrong command counts.
- [ ] The 192-object command ledger still closes to 768 commands, 576 parser
      commands, and zero independent-verifier parser commands.
- [ ] The shared production readiness root contains `verification.json`, and
      its directory name, manifest run ID, verification run ID, and configured
      run ID are equal.
- [ ] Focused unit tests, Python compilation, `git diff --check`, Trellis
      validation, and the new readiness verifier pass.
- [ ] Recorded hashes for `20260807T090000Z`, `20260809T000001Z`,
      `20260809T020000Z`, and `20260809T020001Z` remain unchanged.
- [ ] No new directory appears under the Stage C processing root.

## Prohibited work

- Reading or decompressing a sealed `.mb58.gz` body.
- Running Stage C or producing new sounding/cell data.
- GEBCO, product, or model comparison; MRAR merge; datum or bias fitting;
  cross-cruise aggregation; confirmation-role promotion.
- Modifying an existing readiness or Stage C run.
- Relaxing H03 or another QC rule based on observed output.
- Marking C.2, C.2.1, or C.2.2 complete before a separate reviewer accepts the
  implementation and evidence.
