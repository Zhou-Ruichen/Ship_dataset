# Execution plan: SCS v2 Stage C.2 zero-candidate correction and readiness

All steps are fixture/synthetic-driven. No step reads a sealed `.mb58.gz` body.
The only access to `ncei/derived/.../20260807T090000Z/` is read-only SHA
computation for the registry (step 8).

## Phase 1: H03 parsing fix

- [ ] 1.1 `scs_v2_stage_c_processing.py`: change `_parse_finite` `allow_nan`
      semantics to "allow non-finite" (NaN and Inf pass through when allowed);
      update the docstring; keep the parameter name.
- [ ] 1.2 `scs_v2_stage_c_processing.py:160-161`: parse X and Y with
      `allow_nan=True`. Leave H (`:162`) as-is (heading non-finite is not an
      H03 trigger; confirm whether heading NaN should also demote — default:
      leave heading strict, since H03 names X/Y only).
- [ ] 1.3 Confirm downstream demotion already works: `nav_ok` at `:663-664`
      and `:767` makes NaN/Inf X/Y ineligible; `cell_assignment` skipped at
      `:668-678` leaves bins/cell None. No producer change needed unless the
      row path and batch path diverge.
- [ ] 1.4 `python -m py_compile ncei/code/scs_v2_stage_c_processing.py`.

## Phase 2: fixtures and unit tests

- [ ] 2.1 Add a synthetic U3/U0 ASCII fixture builder in
      `_common/tests/test_scs_v2_stage_c_processing.py` (seven-column
      tab/LF contract), parameterizable to inject X=NaN, Y=NaN, M=NaN,
      duplicate key.
- [ ] 2.2 `test_xy_nan_row_is_demoted_not_aborted`.
- [ ] 2.3 `test_y_nan_row_is_demoted_not_aborted`.
- [ ] 2.4 `test_valid_prefix_then_xy_nan_keeps_prefix`.
- [ ] 2.5 `test_time_nan_still_aborts_object`.
- [ ] 2.6 `test_duplicate_key_still_aborts_object`.
- [ ] 2.7 `test_ineligible_sounding_excluded_from_aggregation`.
- [ ] 2.8 `python -m unittest _common.tests.test_scs_v2_stage_c_processing -v`
      all pass (existing 8 + new 6).

## Phase 3: authorization generator

- [ ] 3.1 `authorize_scs_v2_stage_c.py`: fill
      `stage_c0_planning_lock_sha256` from the planning-lock file SHA.
- [ ] 3.2 Fill `stage_c0_planning_commit` from
      `git log -1 --format=%H -- <planning-lock>` at authorization time.
- [ ] 3.3 Remove `producer_sha256` from the active receipt and from the
      template file `stage-c-authorization.template.json`.
- [ ] 3.4 Add a pre-write guard: fail if any receipt string value contains
      `<REQUIRED`.
- [ ] 3.5 `python -m py_compile` and a smoke authorize against the readiness
      template producing a receipt with zero placeholders and correct template
      SHA.

## Phase 4: verifier

- [ ] 4.1 Add `EXPECTED_TEMPLATE_SHA` constant = current template file SHA.
- [ ] 4.2 Pre-data rejection gate: placeholder scan, template SHA match (both
      receipt field and on-disk template file), field-set closure (receipt keys
      == template keys after scaffold removal).
- [ ] 4.3 Command/parser count closure: count `command_ledger.jsonl` by role;
      derive totals; assert `processing_command_invocation_count`,
      `processing_parser_invocation_count`,
      `independent_verifier_parser_invocation_count == 0`. Share one counting
      helper with the readiness verifier.
- [ ] 4.4 H03 verification: every non-finite lon/lat sounding row is
      ineligible with empty cell fields.
- [ ] 4.5 `python -m py_compile ncei/code/verify_scs_v2_stage_c_processing.py`.

## Phase 5: verifier rejection tests

- [ ] 5.1 Add tests (fixture receipts) proving the verifier rejects: a
      placeholder receipt, a wrong-template receipt, a missing-field receipt,
      an extra-field receipt.
- [ ] 5.2 Add a test proving the verifier closes the command counts on a
      fixture ledger.
- [ ] 5.3 `python -m unittest` all pass.

## Phase 6: diagnostic registry

- [ ] 6.1 Write `research/diagnostic-failed-audit-contract-registry.json`
      binding run 090000Z's four SHAs, counts, and the six findings.
- [ ] 6.2 Assert (test or script) that the registry SHAs match the actual
      on-disk files under 090000Z, and that no file there was modified.

## Phase 7: zero-candidate readiness run

- [ ] 7.1 Run `prepare_scs_v2_stage_c1a_readiness.py` (fixture-driven) against
      the corrected code; produce a new readiness run id.
- [ ] 7.2 Run `verify_scs_v2_stage_c1a_readiness.py`; confirm
      `sealed_object_body_read_count = 0`, `archive_decompression_count = 0`,
      `candidate_sounding_row_count = 0`, `candidate_cell_row_count = 0`,
      `status = pass`, and the new command-count fields present.
- [ ] 7.3 Record readiness run id, manifest SHA, verification SHA, template
      SHA, contract SHAs.

## Phase 8: hard-stop verification and report

- [ ] 8.1 Confirm no sealed body read: `sealed_object_body_read_count = 0`,
      `archive_decompression_count = 0`, no new sounding/cell.
- [ ] 8.2 Confirm 090000Z byte-identical (re-SHA the four files, compare to
      registry).
- [ ] 8.3 Confirm Stage C not rerun (no new run under `stage_c/`).
- [ ] 8.4 Commit code + fixtures + contracts + registry + readiness artifacts
      (readiness outputs are gitignored; commit receipts/manifests only, per
      convention).
- [ ] 8.5 Report: PRD/design/implement paths, changed files, fixture/test
      results, readiness run, all SHA256, commits, explicit "Stage C not
      rerun".

## Validation commands

```bash
python -m unittest _common.tests.test_scs_v2_stage_c_processing -v
python -m py_compile ncei/code/scs_v2_stage_c_processing.py
python -m py_compile ncei/code/process_scs_v2_stage_c_source_internal.py
python -m py_compile ncei/code/verify_scs_v2_stage_c_processing.py
python -m py_compile ncei/code/authorize_scs_v2_stage_c.py
python -m ncei.code.verify_scs_v2_stage_c1a_readiness --run-dir <READINESS_RUN>
```

## Rollback points

- After Phase 1/2: H03 fix is isolated to the helper; revertible by restoring
  `allow_nan=False` on X/Y.
- After Phase 3/4: authorize/verifier changes are independent of the producer
  run path; the frozen run is untouched.
- Phase 7 readiness is additive; a failed readiness run does not affect the
  frozen run.
