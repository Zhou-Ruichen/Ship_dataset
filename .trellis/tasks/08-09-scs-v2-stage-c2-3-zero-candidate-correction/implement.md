# Implementation plan: SCS v2 Stage C.2.3

## Baseline and records

- [x] Read the reviewer findings and independently locate both failure paths.
- [x] Confirm the Stage C0 planning-lock SHA and commit.
- [x] Record the pre-change Stage C directories and old readiness hashes.
- [x] Register `030000Z` as verified but not authorizable due to review blockers.

## TDD cycle 1: active receipt fields

- [x] Add exhaustive template-classification and fixed-field mutation tests.
- [x] Run them against C.2.2 and record the expected failures.
- [x] Implement shared exact-value validation for every receipt field.
- [x] Prove the shared gate, processor gate, and verifier gate reject mutations.

## TDD cycle 2: navigation provenance

- [x] Add schema, row/batch, verifier forgery, and aggregation-exclusion tests.
- [x] Run them against C.2.2 and record the expected failures.
- [x] Add the two lineage fields and independent verifier computation.
- [x] Keep all accepted C.2.2 behavior unchanged.

## Freeze and readiness

- [x] Run all related unit tests, Python compilation, `git diff --check`, and
      Trellis task validation.
- [x] Commit code, tests, contracts, and C.2.3 task files.
- [x] Create and verify immutable readiness `20260809T040000Z`.
- [x] Recompute old-run hashes and Stage C directory names, then commit evidence.
- [x] Leave C.2/C.2.1/C.2.2/C.2.3 `in_progress` for separate review.
- [ ] Receive a decision from a separate reviewer. The implementation agent does
      not approve this task or authorize Stage C.
