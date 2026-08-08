# Design: SCS v2 Stage C.2.1 correction

Code, fixtures, contracts, verifier, and one new C2.1 readiness run only. No
sealed body read, no Stage C rerun. See `prd.md`. Where a prior C.2 design note
conflicts with the on-disk code, the code wins (recorded inline).

## D1. U0 X/Y non-finite demotion (the core fix C.2 missed)

### Current behavior (bug)

`scs_v2_stage_c_processing.py:160` sets `allow_nonfinite_xy = check_mode == 3`.
C.2 relaxed only U3. U0 runs at `check_mode == 0` (`:365`, `:372`), so a U0
`X=nan`/`Y=nan`/`inf` still raises in `_parse_finite` (`:118-119`), propagates
through `iter_mblist_rows`, and becomes a whole-object `PARSER_CONTRACT_FAILURE`
(`:349-352`). This is the same class of bug C.2 fixed for U3, left unfixed for
U0.

### Fix (three layers)

**Layer 1: parsing.** Make `iter_mblist_rows` allow non-finite X/Y for both
modes. `_parse_finite` already means "allow non-finite" when `allow_nan=True`
(C.2 changed `:116-117` to `allow_nan and not math.isfinite(parsed)`). Change
`:160` to `allow_nonfinite_xy = check_mode in (0, 3)` (or drop the gate and pass
`allow_nan=True` unconditionally for X/Y; the check_mode gate stays for clarity).
Depth handling is untouched: U0 NaN depth still raises at `:154-157`
(check_mode 0 != 3); U3 NaN depth still demotes.

**Layer 2: the U3/U0 join in `_raw_from_object_impl` (the subtle layer).** Once
U0 NaN X/Y can be inserted, a NaN stored into the U0 sqlite REAL column reads
back as `None` (Python sqlite3 driver; verified behavior). So at the join SELECT
(`:432-433`) a present-but-NaN-nav U0 row produces `good_lon is None`, which the
current code (`:454`) treats as "key absent". That conflates two cases:

  - (A) key truly absent: no U0 row matches the (epoch, ping, beam).
  - (B) key present, U0 nav non-finite: U0 row exists, `u0.lon`/`u0.lat` are
    NULL because they were NaN.

The `missing_u0` LEFT JOIN count (`:425-429`) measures case (A) correctly
because it keys on `u3.row_order IS NULL` (row existence), not nav value. The
`seen_u0` closure (`:496-497`) counts every row that took the "key present"
branch. So the join loop must branch on **key presence**, not on `good_lon is
None`. Restructure the join SELECT to surface a key-presence flag:

```sql
SELECT u3.*, u0.lon, u0.lat, u0.depth, u0.heading, u0.rowid AS u0_rowid
FROM u3 LEFT JOIN u0 ON ...
```

A non-null `u0_rowid` means the key is present (case B), even when `u0.lon` is
NULL. Then:

  - `u0_present is False` (case A): keep the existing intent -- `quality =
    "null" if depth_is_nan else "flagged"`, `depth = None`. This is a genuinely
    missing key and stays a non-good quality (no H03 overclaim, but also not
    "good"). `seen_u0` is NOT incremented for absent keys (matches today).
  - `u0_present is True` (case B, including finite-nav present keys):
    `native_quality_state = "good"` always (requirement 2). Increment `seen_u0`.
    Run the value-mismatch check only on the fields that can be compared
    meaningfully: depth and heading always; lon/lat only when both U3 and U0 nav
    are finite (`u3_nav_ok and u0_nav_ok`). A NaN cannot be mismatched against a
    finite value, so exempt the lon/lat pair from the mismatch comparison when
    either side is non-finite (C.2 already did this for U3-only; extend to U0).

The RawRow then carries U3 lon/lat when finite, else `math.nan`, into the raw
parquet -- same as C.2's U3 path. The `seen_u0 == u0_count` closure remains valid
because `u0_count` is the number of U0 rows scanned (`:365`) and `seen_u0`
counts present keys, regardless of nav finiteness.

**Layer 3: per-sounding QC.** `sounding_row` (`:665-681`) and
`sounding_batch_table` (`:770-804`) already compute `nav_ok` from lon/lat and
append `H03_NAVIGATION_RANGE`; the cell assignment is skipped when nav is bad,
leaving `lon_bin = lat_bin = cell_id = None`. No structural change needed there
once layers 1-2 feed it. The H02 overclaim is fixed at its source (layer 2 keeps
quality "good"), not patched here.

### What stays atomic (unchanged)

- Time `M` empty/nonnumeric/nonfinite/negative (U3 or U0): `scan_time_contract`
  still returns `TIME_UTC_*` and the object aborts atomically (`:362-367`). The
  U0 parse relaxation does NOT relax the `M` parse (`:136-145`).
- Duplicate (epoch, ping, beam) key: `sqlite3.IntegrityError` -> `ValueError`
  -> atomic abort (`:374-385`). Unchanged.
- U0 NaN depth: still raises at `:154-157` (check_mode 0 != 3). Unchanged.
- U0/U3 value mismatch for finite depth/heading (and finite lon/lat on both
  sides): still raises and aborts. Only the non-finite-nav pair is exempted.

## D2. H03-only failure coding (no H02) -- requirement 3

`sounding_row` (`:670-676`) and `sounding_batch_table` (`:796-804`) build
`failure_codes` from `quality != "good"` -> `H02_NATIVE_NOT_GOOD`, then
`not nav_ok` -> `H03_NAVIGATION_RANGE`, then `not depth_ok` -> `H04_DEPTH_RANGE`.

After D1 keeps `native_quality_state = "good"` for present U0 keys, a
non-finite-nav sounding will no longer trigger H02; only H03 fires. The
`hard_pass` computation (`quality == "good" and nav_ok and depth_ok`) already
makes nav-bad rows ineligible, and `qc_eligible_for_cell = hard_pass` with
`cell_assignment` skipped leaves bins/cell None. So D2 is a consequence of D1
layer 2, not a separate edit -- but it must be asserted in tests (a non-finite
nav sounding has exactly `["H03_NAVIGATION_RANGE"]`, depth retained).

### Semantic clarification found during implementation (code wins)

A sounding's own `lon_deg`/`lat_deg` come from **U3** (the join loop emits
`u3_lon`/`u3_lat` at `:496-497`). So whether H03 fires is determined by the U3
navigation, not the U0 navigation:

- U3 X=NaN, U0 finite -> sounding lon is NaN -> H03 fires, native good, ineligible.
- U0 X=NaN, U3 finite -> sounding lon is finite -> no H03, native good, the row
  is cell-eligible (it has valid navigation of its own).

This is the correct reading of requirement 3 ("non-finite navigation raises only
H03"): "navigation" is the sounding's own position. Requirement 2 ("U0 key
present keeps native good") is the load-bearing part for the U0-NaN case: the
prior code would have flagged it. The `test_u3_nan_nav_with_present_u0_*` test
pins the H03-only path; the `test_u0_xy_nan_*` tests pin the native-good path.

Note on the "null" quality (depth_is_nan, key absent): that path keeps
`native_quality_state` in `{"null","flagged"}` and legitimately raises H02 (it is
a missing-key / non-good native state). D2 only removes the spurious H02 from the
present-key non-finite-nav case.

## D3. Single immutable template + exact schema closure + recursive placeholder

### Decision: one canonical template

The existing Stage C authorization template is the canonical immutable file.
Readiness copies its bytes into `stage_c_authorization.template.json`, the
receipt report records the same path and SHA, and the authorizer/verifier bind
that same path and SHA. Readiness provenance remains in `readiness_lock.json`
and `audit_manifest.json`; it is not represented by a second authorization
template with a different schema.

### Exact schema closure

Today `verify_run` (`:446-462`) does `template_keys <= active_keys` (subset) and
then `active_keys - template_keys - authorize_added`. That allows the template to
have FEWER keys than the active receipt (the `authorize_added` whitelist absorbs
extras) but does not reject an active receipt that DROPPED a template key after
filling. Requirement 7 wants exact closure. Replace the subset check with an exact
set relation:

  `active_keys == (template_keys - scaffold_removed) | authorize_added`

where `scaffold_removed` is the deterministic set authorize removes (e.g.
`producer_sha256`) and `authorize_added` is the deterministic set authorize
fills. Compute both sets from the template + a frozen added-list, so missing and
extra keys are both rejected. (C.2 already drops `producer_sha256`; record it in
`scaffold_removed`.)

### Recursive placeholder scan

Today the scans at `authorize:142` and `verify:440` are
`isinstance(v, str) and "<REQUIRED" in v` over top-level values only. A
placeholder nested inside `permitted_body_read_counts` (a dict) or a list would
slip through. Add a shared recursive walker that descends dict values and list
items and fails on any `str` containing `<REQUIRED`. Put it in the helper module
(`scs_v2_stage_c_processing.py`) so authorize, verifier, and tests share one
definition; use it in both the authorize pre-write guard and the verifier
pre-data gate.

## D4. Single C2.1 readiness binding; remove 20260806T093740Z hardcode

`READINESS_ROOT` is hardcoded to `20260806T093740Z` in `authorize:22`,
`verify:28`, and `processor:51`. C.2 readiness actually ran as
`20260809T000001Z`; the production code still points at the older run. Requirement
5: all three bind the same new C2.1 readiness run. Approach: add a module-level
constant `C2_1_READINESS_RUN_ID = "<new run id>"` in each file (or a shared
constant in the helper) and derive `READINESS_ROOT` from it, so there is exactly
one place to update and the binding is auditable. The new run id is chosen at
execution time; the constant is set before the readiness run is produced.

The C1a manifest/verification SHAs the production chain pins
(`C1A_MANIFEST_SHA256`, `C1A_VERIFICATION_SHA256`) are currently pinned to the
`20260806T093740Z` run's values. After C2.1 produces a new readiness run, those
pins move to the new run's manifest/verification SHAs (the new run supersedes the
old as the readiness-of-record).

## D5. Production verifier fixture (requirement 4)

C.2 only proved the helper against the readiness verifier. Requirement 4 demands
the producer output pass the real `verify_scs_v2_stage_c_processing.py`. That
verifier reads a full run dir (manifest, parquet tables, command_ledger, etc.).
A fixture-driven path must assemble a minimal valid run dir from synthetic U3/U0
ASCII. The smallest faithful unit is `_raw_from_object` + `sounding_batch_table`
+ a synthetic command_ledger + an authorization receipt. Because the production
verifier hardcounts 768 objects / 192 mb58 / 4 command roles (`:213`, `:500-502`),
the fixture either (a) builds a 768-object synthetic manifest, or (b) the test
exercises the verifier's closure logic against a synthetic ledger directly
(counting helper) plus an end-to-end single-object run through the producer path.

The test builds one synthetic producer output with `_raw_from_object`,
`sounding_batch_table`, and `aggregate_outputs`, then calls the real
`verify_run` with only its manifest/root dependencies injected. This exercises
object tables, sounding QC, aggregation, access closure, schema closure, H03,
and the command ledger without opening sealed data. A separate ledger test
keeps the frozen `768/576/0` closure.

## D6. Readiness manifest SHA binding (requirement 9)

The new readiness manifest binds SHA256 of: helper
(`scs_v2_stage_c_processing.py`), processor
(`process_scs_v2_stage_c_source_internal.py`), authorizer
(`authorize_scs_v2_stage_c.py`), verifier (`verify_scs_v2_stage_c_processing.py`
and `verify_scs_v2_stage_c1a_readiness.py`), the C2.1 test module, the C2.1
contract file(s), and the single template. The readiness lock and receipt report
surface these bindings, including the C2.1 contract and both C2.1 test modules.

## D7. Immutability of 090000Z and 000001Z (requirement 10)

Both runs are read only for SHA recomputation. No code path writes under either
directory. Tests assert the recorded SHAs still match on-disk files (read-only
`sha256_file`). The diagnostic registry from C.2 already records `090000Z`;
C2.1 does not modify it.

## Compatibility and risk

- Helper/authorizer/verifier hashes change -> the frozen `090000Z` and `000001Z`
  receipts no longer match by design; both are already classified
  diagnostic/frozen and are not rerun.
- Template unification (D3) changes the readiness producer/verifier; covered by
  the readiness verifier test path.
- D1 layer 2 is the highest-risk edit (join semantics + closure). Tests cover:
  present-key non-finite nav (good quality, H03 only), absent key (non-good),
  finite-nav mismatch (still raises), and the `seen_u0 == u0_count` closure with
  a mixed fixture.

## Open decisions (confirm at review)

1. Whether `allow_nonfinite_xy` should also cover heading `H` (`:162`). Default:
   leave heading strict; H03 names X/Y only and a non-finite heading is not in
   scope. (Same call C.2 made.)
2. The readiness and production chains use the same canonical template; no
   separate schema-v3 authorization template is emitted.
3. The full synthetic verifier path is covered with a one-object producer
   fixture; `768/576/0` remains a separate exact ledger closure test.
