# SCS v2 Stage C.2.3 zero-candidate receipt and navigation evidence correction

## Goal

Remove the two independent-review blockers left in C.2.2 without changing the
accepted Stage C navigation policy or running Stage C. Produce a new immutable
zero-candidate readiness for a separate reviewer.

## Requirements

- Keep the accepted U3/U0 NaN and Inf H03 behavior, time and duplicate-key
  object failure, finite U3/U0 mismatch failure, and existing 66 tests.
- Classify every field in the immutable authorization template as exactly one
  of: template-fixed, readiness-evidence-filled, or activation-controlled.
  Reject an unclassified or multiply classified template field.
- Validate every field in an active receipt. Recomputing the canonical receipt
  hash must not make a changed fixed field acceptable.
- Bind the Stage C0 planning lock to SHA256
  `ec0a0a491c995c374ac99306a37f3eb9b26e06692616939072736f7b7f08d78e`
  and commit `0aadea0d5f94783d138fdf6b4479e6f51b0d35db`.
- Persist non-null `u3_navigation_finite` and nullable
  `u0_navigation_finite` in `sounding_lineage.parquet`; null U0 means no U0
  row was present.
- Make the production verifier independently compute `navigation_valid` from
  the two source states and output coordinate range. It must reject forged
  final navigation or source-state values.
- Cover U3-invalid/U0-valid, U3-valid/U0-invalid, both invalid, U0 absent,
  finite but out-of-range coordinates, row/batch equality, and exclusion from
  contributor/candidate output.
- Do not modify readiness `20260809T030000Z` or any older run. Register it as
  `verified_but_not_authorizable_due_review_blockers`.
- Create a new immutable readiness only after code, rules, tests, and task
  contract are committed. It must have zero sealed-body reads, decompressions,
  candidate soundings, and candidate cells.
- Do not read or decompress sealed bodies, run Stage C, create real
  soundings/cells, compare products or models, merge MRAR, fit datum/bias, or
  aggregate across cruises.
- Keep C.2, C.2.1, C.2.2, and C.2.3 `in_progress` pending separate review.

## Acceptance Criteria

- [ ] A parameterized test changes every fixed receipt field, recomputes the
      canonical hash, and observes rejection from the shared production gate.
- [ ] The real authorizer produces a synthetic active receipt accepted by the
      shared gate, processor gate, and production verifier gate.
- [ ] The output schema contains both navigation-source fields with exact
      bool/nullability requirements.
- [ ] Producer row and batch paths emit identical values for all navigation
      cases, and the production verifier rejects forged navigation evidence.
- [ ] All related unit tests, Python compilation, diff checks, Trellis task
      validation, and the new readiness verifier pass.
- [ ] Old-run hashes and Stage C directory names remain unchanged.
- [ ] Stage C remains on HOLD and no implementation-agent approval is recorded.

## Review state

C.2.2 is not accepted. C.2.3 implementation and self-test cannot authorize
Stage C; a different agent must review the new commit and readiness.
