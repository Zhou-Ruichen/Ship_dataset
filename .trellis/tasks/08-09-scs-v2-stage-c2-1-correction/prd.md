# SCS v2 Stage C.2.1 correction (U0 X/Y demotion, schema closure, single readiness binding)

## Goal

Independent correction of the prior Stage C.2 pass. C.2 only relaxed X/Y
non-finite parsing for **U3** (`check_mode == 3`); the **U0** (`check_mode == 0`)
X/Y NaN/Inf path still aborts the whole source object, and the join/QC layers
have two follow-on defects. C.2.1 fixes U0 demotion, makes non-finite navigation
an H03-only failure, closes the template/schema/readiness chain, and proves all
of it on fixtures through the real production verifier. No sealed body read, no
Stage C rerun, zero new soundings/cells. `20260807T090000Z` and
`20260809T000001Z` are immutable.

## Independently rechecked code evidence (line numbers against the on-disk code)

1. `ncei/code/scs_v2_stage_c_processing.py:160`
   `allow_nonfinite_xy = check_mode == 3`. U0 runs at `check_mode == 0`, so U0
   X/Y non-finite still goes through `_parse_finite` (`:111-120`) which raises at
   `:118-119`. The raise propagates through `iter_mblist_rows` (called inside
   `scan_time_contract` at `:365` and the U0 insert loop at `:372`), up through
   `_raw_from_object_impl`, and is converted by `_raw_from_object` (`:349-352`)
   to `(0, 0, "PARSER_CONTRACT_FAILURE", ...)` -- a whole-object abort. C.2 only
   relaxed U3.
2. `:470` `quality = "good" if (u3_nav_ok and u0_nav_ok) else "flagged"`. Once U0
   NaN X/Y can reach the join (after fix #1), a U0 key that exists (joined row,
   not missing) but has non-finite `good_lon`/`good_lat` is marked `"flagged"`
   instead of `"good"`. U0 key existence must keep `native_quality_state = good`.
3. `:671-672` `if not native_good: failure_codes.append("H02_NATIVE_NOT_GOOD")`
   (row path) and the identical `:798-800` (batch path). Because of #2 a
   non-finite-navigation sounding gets `H02_NATIVE_NOT_GOOD` in addition to
   `H03_NAVIGATION_RANGE` (`:674`/`:801`). Correct: non-finite navigation must
   raise only `H03`, keep valid depth, and be `qc_eligible_for_cell = false` with
   `lon_bin = lat_bin = cell_id = None`.

Join-closure note (the part fix #1 makes live): U0 NaN X/Y stored in a sqlite
REAL column reads back as `None` (Python sqlite3 driver), so at the join SELECT
(`:432-433`) a present-but-NaN-nav U0 row looks like a missing key
(`good_lon is None`). The current `good_lon is None` branch (`:454-456`) cannot
distinguish "key absent" from "key present, nav non-finite". The closure check
`seen_u0 != u0_count` (`:496-497`) and the `missing_u0` LEFT JOIN count
(`:425-429`) must remain consistent. The fix distinguishes key presence (which
the LEFT JOIN already measures by row existence, not by nav value) from nav
finiteness.

## Scope (frozen)

- Code, fixtures, contracts, verifier, and a new single C2.1 readiness run only.
- No sealed body read, no Stage C rerun, zero new soundings/cells, no Stage D, no
  confirmation role promotion.
- `20260807T090000Z` and `20260809T000001Z` are byte-for-byte immutable; they are
  read only for SHA computation.
- Time-invalid (`M` empty/nonnumeric/nonfinite/negative in U3 or U0) and
  duplicate/structural key failures still abort the whole source object
  atomically (`parsed_row_count = 0`). This path is not relaxed.
- U3 X/Y non-finite handling from C.2 stays; C.2.1 extends the same per-sounding
  demotion to U0 and fixes the join/QC defects.

## Requirements (frozen 10)

1. U3 **and** U0 X/Y NaN/Inf are demoted per-sounding, not whole-object abort.
2. A U0 key that exists keeps `native_quality_state = "good"` even when its
   navigation is non-finite.
3. Non-finite navigation raises only `H03_NAVIGATION_RANGE`, never
   `H02_NATIVE_NOT_GOOD`; valid depth is retained, `qc_eligible_for_cell = false`,
   `lon_bin = lat_bin = cell_id = None`.
4. The producer output passes the real production verifier
   (`verify_scs_v2_stage_c_processing.py`) on a synthetic fixture, not only the
   readiness verifier.
5. Processor, authorizer, and verifier bind one single new C2.1 readiness run;
   all old `20260806T093740Z` hardcoding (`READINESS_ROOT` and derived constants
   in authorize/verifier/processor/readiness producer) is removed or
   parameterized onto the new run.
6. The readiness-template, the receipt-report template, and the verifier-accepted
   template are one immutable file with one SHA256.
7. Placeholder scanning is recursive over dict/list (today it only scans
   top-level str values); the receipt closes exactly against the template schema
   (reject missing and extra keys).
8. Tests added: U0 NaN/Inf X/Y, native quality stays good, no H02, production
   verifier passes, four bad-receipt rejections (placeholder / wrong template /
   missing field / extra field), and 768/576/0 ledger closure.
9. The new readiness manifest binds the SHA256 of helper, processor, authorizer,
   verifier, tests, the C2.1 contract, and the template.
10. `20260807T090000Z` and `20260809T000001Z` stay immutable; reading their SHA
    is allowed, modification/deletion/overwrite is not.

## Acceptance Criteria (all machine-verifiable)

- [ ] `python -m unittest _common.tests.test_scs_v2_stage_c_processing -v` passes,
      including new U0 NaN/Inf, no-H02, native-quality-good, and aggregation
      exclusion assertions.
- [ ] A fixture proves a U0 X=NaN (or Y=NaN) object is not aborted, that sounding
      is ineligible with empty cell fields and `H03` only, and its
      `native_quality_state == "good"` with no `H02`.
- [ ] A fixture proves a valid prefix is retained and eligible when a later U0
      NaN row appears.
- [ ] Time=NaN and duplicate-key still abort the whole object atomically.
- [ ] The production verifier passes on a synthetic run built from fixtures
      (768/576/0 command closure, H03 verification, schema closure).
- [ ] The verifier rejects (non-zero exit, clear message): a placeholder receipt,
      a wrong-template receipt, a missing-field receipt, and an extra-field
      receipt (placeholder scan is recursive).
- [ ] Authorize/verify/processor all resolve the same single C2.1 readiness run;
      no `20260806T093740Z` literal remains in those code paths.
- [ ] The readiness manifest binds helper, processor, authorizer, verifier,
      tests, C2.1 contract, and template SHA256; readiness status = pass with
      `sealed_object_body_read_count = 0`, `archive_decompression_count = 0`,
      `candidate_sounding_row_count = 0`, `candidate_cell_row_count = 0`.
- [ ] `20260807T090000Z` and `20260809T000001Z` are byte-identical to their
      recorded SHAs (re-SHA, read-only).

## Out of scope

- Stage C rerun on sealed bodies; Stage D confirmation; GEBCO/product/model
  comparison; MRAR merge; datum/bias fit; cross-cruise aggregation; confirmation
  role promotion; R03/R05 threshold changes.
