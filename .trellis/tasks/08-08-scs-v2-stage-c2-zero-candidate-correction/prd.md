# SCS v2 Stage C.2 zero-candidate correction and readiness

## Goal

Correct the Stage C.2 authorization, verifier, and source-internal parsing
contract so that a future authorized Stage C run would be audit-complete and
H03-compliant. This task produces **only code, fixtures, contracts, verifier,
and a zero-candidate readiness run**. It does **not** read any sealed body, does
not rerun Stage C, and produces zero new soundings or cells.

## Background (the six confirmed findings)

Independent recheck against the frozen run `20260807T090000Z` confirmed all six:

1. `verification.json` `candidate_row_count = 3539` (not the 3593 previously
   reported in the journal; the journal is corrected separately).
2. The active `authorization_receipt.json` still carries literal placeholders
   `producer_sha256 = <REQUIRED_SHA256>`,
   `stage_c0_planning_commit = <REQUIRED_GIT_COMMIT>`,
   `stage_c0_planning_lock_sha256 = <REQUIRED_SHA256>`.
3. The active receipt binds `authorization_template_sha256 = 483b6981...`
   (the current Stage C schema-v1 template). The C1a readiness receipt's
   `inactive_authorization_template_sha256 = 40772949...` refers to the older
   schema-v3 template stored inside the C1a readiness run directory. The two
   are different schemas, not a formatting drift. The authorization chain does
   not currently force an active receipt to bind the exact template the
   `authorize` script consumed, nor reject placeholders or schema mismatches.
4. TN352 `objects/TN352/em302/0168_20180501_164920_TGT.all.mb58.gz` was
   aborted whole-object (`failed_parser_contract`, `parsed_row_count = 0`)
   because a single U-row has `X = nan`. The error detail is
   `X is not finite: '            nan'`. This violates the frozen H03 rule: a
   non-finite X/Y must demote that single sounding
   (`qc_eligible_for_cell = false`, empty lon/lat bin and cell) while keeping
   the object's other valid soundings. Only time-invalid and
   structural/duplicate-key failures abort the whole object atomically.
5. `command_ledger.jsonl` has 768 lines (192 each of `decompression`,
   `mbinfo`, `mblist_u3`, `mblist_u0`), but `verification.json` records
   `parser_invocation_count = 0`. The verifier does not close the producer's
   parser/command activity against the ledger.
6. Under the frozen Stage A South China Sea rectangle
   (`105 <= lon < 125`, `0 <= lat < 25`) the frozen run has exactly 2,359
   candidate cells and 16,033,970 eligible soundings, of which TN352 owns
   2,358 cells / 12,264,855 eligible, EQT190012 owns 1 cell / 3,769,115
   eligible, and EQT180002 and EQT20210702 own 0 cells. The "four-cruise
   South China Sea" framing is therefore inaccurate; the SCS cells are almost
   entirely TN352.

## Scope (frozen decisions)

- Interpretation A: this task delivers corrected code, fixtures, contracts,
  verifier, and a zero-candidate readiness run only. No sealed body read, no
  Stage C rerun, zero new soundings/cells, no Stage D, no confirmation role
  promotion.
- H03 implementation: X/Y NaN/Inf are preserved through parsing and demoted at
  per-sounding QC (`qc_hard_pass = false`, `qc_eligible_for_cell = false`,
  `lon_bin = lat_bin = None`, `cell_id = None`); other valid soundings in the
  same object are kept. Time-invalid and structural/duplicate-key failures
  still abort the whole source object atomically per the frozen time contract.
- The original run `20260807T090000Z` is left byte-for-byte untouched. A
  machine-readable registry under this task's `research/` records it as
  `diagnostic_failed_audit_contract`, binding its verification, audit manifest,
  and output SHAs.
- Command counting uses a split vocabulary:
  `processing_command_invocation_count = 768` (decompression 192, mbinfo 192,
  mblist_u3 192, mblist_u0 192), `processing_parser_invocation_count = 576`
  (the three parser-class commands: mbinfo, mblist_u3, mblist_u0), and
  `independent_verifier_parser_invocation_count = 0`.
- The South China Sea metadata candidate-discovery task is **not** created in
  this task. It is opened separately after this task's readiness stops.

## Requirements

### R1 Authorization generator (`authorize_scs_v2_stage_c.py`)

- The active receipt must bind the exact SHA256 of the authorization template
  the script actually consumed (`stage-c-authorization.template.json`,
  currently `483b6981fdb7b2dfbc84053feec6ccfb1188827cdd50758887028cb8d0f295ac`).
- An active receipt must contain no `<REQUIRED_...>` literals in any field.
  Fields that previously held placeholders must be filled with real values
  computed at authorization time, or removed from the active-receipt schema if
  they are template-only scaffolding.
- The receipt must bind current producer (`processor_sha256`), verifier
  (`verifier_sha256`), helper (`processing_helper_sha256`), authorization
  script, output schema, QC contract, verification contract, the Stage C0
  planning lock SHA, and the Stage C0 planning commit. All bindings must close.
- The canonical authorization receipt hash must cover the finalized field set
  (no placeholder fields left inside the hashed object).

### R2 Verifier (`verify_scs_v2_stage_c_processing.py`)

- Reject any receipt whose template SHA differs from the template the verifier
  is configured to accept.
- Reject any receipt containing a `<REQUIRED_...>` literal, a missing required
  field, or an extra unknown field, before any data check.
- Close command/parser counts against `command_ledger.jsonl`:
  `processing_command_invocation_count`, `decompression_count` (192),
  `mbinfo_count` (192), `mblist_u3_count` (192), `mblist_u0_count` (192),
  `processing_parser_invocation_count` (576), and
  `independent_verifier_parser_invocation_count = 0`.
- Verify that any X/Y-non-finite sounding carries `qc_hard_pass = false`,
  `qc_eligible_for_cell = false`, `lon_bin = lat_bin = cell_id = None`, and is
  excluded from contributor/candidate aggregation, while its object still
  contributes its valid soundings (no whole-object abort for X/Y NaN/Inf).

### R3 H03 parsing (`scs_v2_stage_c_processing.py` + producer)

- `_parse_finite` (or its caller) must tolerate NaN/Inf in X (lon) and Y (lat)
  columns of U3/U0 rows, preserving them into the per-sounding record.
- A non-finite X/Y sounding is an H03 failure: `nav_ok = false`,
  `qc_hard_pass = false`, `qc_eligible_for_cell = false`,
  `lon_bin = lat_bin = cell_id = None`. It is retained in sounding lineage but
  excluded from the eligible table and from aggregation.
- Depth NaN/Inf handling is unchanged: a non-finite or out-of-range depth makes
  `qc_hard_pass = false`, `qc_eligible_for_cell = false`.
- Time-invalid (`M` empty/nonnumeric/nonfinite/negative in U3 or U0) and
  duplicate/structural key failures still abort the whole source object
  atomically (`parsed_row_count = 0`, no soundings, no aggregation) per the
  frozen time contract. This path is not relaxed.

### R4 Fixtures and offline tests

Add fixtures and assertions covering:
- U3 row with `X = NaN` (object not aborted; that sounding ineligible).
- U3 row with `Y = NaN` (same).
- A valid prefix followed by an X/Y NaN row (valid prefix soundings retained).
- `time = NaN` / negative `M` still aborts the whole object.
- Duplicate (ping, beam) key still aborts the whole object.
- A failed or ineligible sounding does not enter the eligible table or any
  contributor/candidate aggregate.

### R5 Diagnostic registry

Under `research/`, add a machine-readable registry recording run
`20260807T090000Z` as `diagnostic_failed_audit_contract`, binding:
`verification.json` SHA `9b768fa5eaa59ba67d20fab707b324cbb5c10e95f3a550738d279f2c07e2d0c8`,
`audit_manifest.json` SHA `53fd36868f36447daa7025bbe1a6efefcc29713767698107744817343fbd2067`,
`authorization_receipt.json` SHA `0c4a8313d7306dcf0c75cba24663dd6cffac9847cf24771e6f43febf1209e412`,
its candidate/contributor/sounding counts, and the specific findings (H03,
placeholders, template binding, command count) that disqualify it.

### R6 Zero-candidate readiness run

Produce a new readiness run under
`ncei/derived/scs_v2_sealed_confirmation/stage_c_readiness/<RUN_ID>` that
exercises the corrected code on fixtures (not sealed bodies) and records:
`sealed_object_body_read_count = 0`, `archive_decompression_count = 0`,
`candidate_sounding_row_count = 0`, `candidate_cell_row_count = 0`, and all
authorization-chain bindings closed.

## Acceptance Criteria (all machine-verifiable)

- [ ] `python -m unittest _common.tests.test_scs_v2_stage_c_processing` passes,
  including the new H03 and command-count assertions.
- [ ] A new fixture-driven test proves an object with one X=NaN row is not
  aborted and that row is ineligible with empty cell fields.
- [ ] A new fixture-driven test proves time=NaN and duplicate-key still abort
  the whole object.
- [ ] `authorize_scs_v2_stage_c.py` produces an active receipt with zero
  `<REQUIRED_...>` literals and a template SHA equal to the consumed template.
- [ ] The verifier rejects (non-zero exit, clear message): a placeholder
  receipt, a wrong-template receipt, a missing-field receipt, and an
  extra-field receipt.
- [ ] The verifier closes `processing_command_invocation_count = 768`,
  `processing_parser_invocation_count = 576`, and
  `independent_verifier_parser_invocation_count = 0` against the ledger, on a
  fixture-derived run that records those counts.
- [ ] The diagnostic registry exists, is valid JSON, and binds the four SHAs
  and counts listed in R5.
- [ ] The new readiness run records `sealed_object_body_read_count = 0`,
  `archive_decompression_count = 0`, `candidate_sounding_row_count = 0`,
  `candidate_cell_row_count = 0`, and `status = pass`.
- [ ] No file under `ncei/derived/scs_v2_sealed_confirmation/stage_c/20260807T090000Z/`
  is modified (byte-identical to the committed reference SHAs in R5).
- [ ] Stage C is not rerun; no new `.mb58.gz` body is read.

## Out of scope

- Stage C rerun on sealed bodies.
- Stage D confirmation evaluation, GEBCO/product/model comparison, MRAR merge,
  datum/bias fit, cross-cruise aggregation, confirmation role promotion.
- R03/R05 threshold changes (report-only; no sounding deletion).
- The South China Sea metadata candidate-discovery task (separate task).
