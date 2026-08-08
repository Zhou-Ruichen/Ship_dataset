# Implementation plan: SCS v2 Stage C.2.2 contract closure

## Scope checks

- [x] Independently inspect C.2/C.2.1 code, contracts, commits, and readiness
      metadata without reading sealed bodies.
- [x] Record the existing Stage C processing directory names.
- [x] Keep C.2 and C.2.1 `in_progress`.

## Tests first

- [x] Replace the incorrect U0-NaN eligible expectation with H03-only behavior.
- [x] Add U3/U0 NaN and Inf combinations, prefix retention, aggregation
      exclusion, row/batch equality, and atomic-failure tests.
- [x] Add real-authorizer and readiness/code/template/rule drift rejection
      tests, plus shared-root and command-ledger checks.
- [x] Extend the production-verifier fixture with separate U3-invalid and
      U0-invalid soundings.

## Implementation

- [x] Carry dual-source navigation finite state into sounding QC and output.
- [x] Update output/QC/verification rules and production verifier semantics.
- [x] Share exact receipt and readiness-frozen hash validation across all three
      production entry points.
- [x] Bind production code to the immutable template snapshot in the new
      readiness root.
- [x] Extend readiness producer/verifier manifests for C.2.2 files and rule
      hashes.

## Verification and evidence

- [x] Run focused and readiness unit tests, compilation, diff checks, and
      Trellis validation.
- [x] Commit code, tests, rules, and task records before producing readiness.
- [x] Create and independently verify `20260809T030000Z` with zero candidate
      access/output counters.
- [x] Record old-run status and immutable hashes, verify no Stage C directory
      was added, and commit evidence records.
- [x] Leave C.2, C.2.1, and C.2.2 `in_progress` pending a separate reviewer.
- [ ] Obtain a decision from a separate reviewer. This is outside the
      implementation agent's authority.
