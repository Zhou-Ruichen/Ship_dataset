# Execution plan: SCS v2 Stage C.2.1 correction

## Scope gate

- [x] Keep Stage C rerun on HOLD.
- [x] Keep C.2 and C.2.1 tasks `in_progress` until independent review passes.
- [x] Do not read sealed object bodies or create a Stage C processing run.
- [x] Preserve `20260807T090000Z` and `20260809T000001Z`.

## Implementation

- [x] Demote U0 and U3 non-finite X/Y per sounding, preserve valid depth, and
      keep an existing U0 key's native quality as `good`.
- [x] Close H03/H02 behavior, cell exclusion, U0 join count, and recursive
      placeholder scanning with fixture tests.
- [x] Bind processor, authorizer, verifier, readiness producer, tests, the
      C2.1 contract, and one canonical template to the same hashes.
- [x] Add a full synthetic producer-output path through the production verifier.
- [x] Produce the new zero-candidate readiness run `20260809T020001Z`.
- [x] Independently verify the new readiness run with the readiness verifier.

## Verification

- [x] Run the focused processing and verifier unit tests.
- [x] Run Python compilation checks.
- [x] Run the readiness verifier and confirm all zero-access counters.
- [x] Recheck old-run immutability from recorded hashes without opening bodies.
- [ ] Obtain a separate-agent review; the implementer cannot self-approve.

## Finish gate

- [x] Record the readiness run, verification result, template/contract/code
      hashes, and explicit Stage C HOLD status.
- [x] Commit only the C.2.1 changes that belong to this task; preserve unrelated
      worktree changes.
- [ ] Keep both C.2 and C.2.1 task records `in_progress` until review is done.

## Review gate

The code and readiness evidence are complete, but the separate-agent review is
still open. An external Pi review dispatch was rejected because it would send
repository code, contracts, and readiness metadata to an external service
without explicit destination approval. C.2 and C.2.1 remain `in_progress`.
