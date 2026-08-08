# Design: SCS v2 Stage C.2 zero-candidate correction and readiness

## Scope reminder

Code, fixtures, contracts, verifier, and a zero-candidate readiness run only.
No sealed body read, no Stage C rerun. See `prd.md`.

## D1. H03 non-finite X/Y handling (the core semantic fix)

### Current behavior (bug)

`scs_v2_stage_c_processing.py:160-161` parses U-row X and Y via
`_parse_finite(fields[3], "X")` / `_parse_finite(fields[4], "Y")` with the
default `allow_nan=False`. `_parse_finite` raises `ValueError` on any non-finite
value (`scs_v2_stage_c_processing.py:118-119`). The raise propagates out of
`iter_mblist_rows`, up through `_raw_from_object_impl`, and is caught by
`_raw_from_object` (`:338-352`), which converts it to a whole-object
`PARSER_CONTRACT_FAILURE` with `parsed_row_count = 0`. That is how TN352 0168
died on one `X = nan` row.

### Fix (three layers)

The fix spans three layers because of how NaN travels through sqlite.

**Layer 1: parsing.** `iter_mblist_rows` already accepts `allow_nan` on
`_parse_finite` (`:111-120`), and depth already special-cases NaN in U3
(`check_mode == 3`, `:154-157`). Change X and Y parses to tolerate non-finite
values and extend `_parse_finite` so `allow_nan=True` means "allow non-finite"
(NaN and Inf both pass through; confirmed `math.isfinite` is False for both):

- `_parse_finite` `:116-117`: replace the `math.isnan(parsed) and allow_nan`
  guard with `allow_nan and not math.isfinite(parsed)`.
- `iter_mblist_rows` `:160-161`: parse X and Y with `allow_nan=True`.

**Layer 2: the U3/U0 join in `_raw_from_object_impl`.** This is the layer the
initial design missed. U3 lon/lat are inserted into a sqlite REAL column
(`:386`). The Python sqlite3 driver stores NaN as NULL but reads Inf back as
`inf` (verified), so after the join SELECT (`:431-433`) the U3 `lon`/`lat`
variables are `None` for NaN input and `inf` for Inf input. The current join
loop assumes U3 lon/lat are finite: `:475` does `normalize_longitude(float(lon))`
unconditionally and crashes on `None`, and the U0/U3 mismatch check (`:454-463`)
would compute `abs(nan - good_lon)`. Fix the join loop so that a non-finite or
None U3 lon/lat (or U0 good_lon/good_lat) is treated as navigation failure:

- Introduce `u3_nav_ok = lon is not None and math.isfinite(lon) and lat is not
  None and math.isfinite(lat)` and an equivalent `u0_nav_ok` for good_lon/
  good_lat.
- When `u3_nav_ok` is false: set quality to "flagged" (or "null" if depth is
  also NaN), pass `float("nan")` as lon_deg/lat_deg into RawRow, and skip the
  U0/U3 value-mismatch comparison for lon/lat (a NaN cannot be mismatched
  against a finite U0 value meaningfully; treat the row as navigation-failed
  rather than raise). Depth/heading mismatch checks remain.
- When `u3_nav_ok` is true but `u0_nav_ok` is false: keep the existing
  `good_lon is None` branch intent but extend it to non-finite good_lon/lat.

The RawRow carries NaN lon/lat into `sounding_lineage`.

**Layer 3: per-sounding QC (already correct, no change).** `sounding_row`
(`:660-678`) and `sounding_batch_table` (`:763-800`) compute
`nav_ok = math.isfinite(lon) and ... and math.isfinite(lat) ...`, append
`H03_NAVIGATION_RANGE` to failure codes, set `qc_hard_pass = False`,
`qc_eligible_for_cell = False`, and leave `lon_bin = lat_bin = cell_id = None`.
The ineligible row is retained in sounding lineage but never enters the
`eligible` table (producer `process_one_mb58` `:332-343` inserts only eligible
rows), so it never aggregates.

`H03_NAVIGATION_RANGE` already exists as a failure code (`:791`), confirming
the contract always expected per-sounding H03 demotion; the prior whole-object
abort was an artifact of layer 1 raising before layer 3 could run.

### What stays atomic (unchanged)

- Time `M` empty/nonnumeric/nonfinite/negative: caught by
  `scan_time_contract` before the row loop, returns `TIME_UTC_*` and aborts the
  object (`_raw_from_object_impl` early-returns). Not touched.
- Duplicate (epoch, ping, beam) key: `sqlite3.IntegrityError` on U0 insert is
  converted to `ValueError("duplicate U0 key: ...")` and aborts the object
  (`:397-405`). Not touched.
- Non-finite depth: U0 NaN depth still raises at `:154-157` (check_mode 0 !=
  3); U3 NaN depth is already allowed and demoted by `depth_ok`. The H03 fix
  does not change depth handling.
- U0/U3 value mismatch for finite values (depth, heading, and finite
  lon/lat) still raises and aborts the object (`:454-463`). Only the
  NaN/Inf-navigation case is exempted from the lon/lat mismatch comparison.

### Why this is safe for the producer contract

The object no longer aborts on a single bad X/Y. Objects that previously died
(`failed_parser_contract`, count 1 in run 090000Z) would instead emit their
valid soundings plus one ineligible row. This **changes future Stage C output
counts**, which is exactly why this task does not rerun Stage C: the corrected
semantics are proven on fixtures only, and the real rerun waits for separate
authorization.

## D2. Authorization generator (`authorize_scs_v2_stage_c.py`)

### Problems

- The template has 10 `<REQUIRED_...>` fields. `authorize` fills some at
  activation (processor, verifier, helper, schema, contracts, environment,
  fixtures, run id) but leaves `producer_sha256`, `stage_c0_planning_commit`,
  `stage_c0_planning_lock_sha256` as literals in the active receipt.
- The active receipt binds `authorization_template_sha256` (the file SHA of the
  consumed template), but nothing verifies the active receipt's field set
  matches the template's field set, so stale/extra/placeholder fields are not
  rejected.

### Fix

In `authorize_scs_v2_stage_c.main`, after building the receipt dict:

1. Fill `stage_c0_planning_lock_sha256` from the actual planning-lock file SHA
   (the file is `research/stage-c0-planning-lock.json`, SHA
   `ec0a0a491c995c374ac99306a37f3eb9b26e06692616939072736f7b7f08d78e`).
2. Fill `stage_c0_planning_commit` from git (the commit that introduced the
   planning lock / the current `HEAD` of the planning task branch; resolved at
   authorization time, not hardcoded).
3. Remove the redundant `producer_sha256` field from the active receipt. The
   producer is already bound by `processor_sha256`. `producer_sha256` is
   template scaffolding with no distinct meaning; drop it from the active
   schema and from the canonical-hash input.
4. Add a final guard before writing: scan every string value in the receipt
   for `<REQUIRED` and fail loudly if any remain.

The canonical hash function `canonical_authorization_receipt_sha256` hashes a
sorted-JSON of the receipt. Because we remove `producer_sha256` and fill the
other two, the hashed field set is finalized and stable.

### Template binding semantics

The active receipt keeps `authorization_template_sha256` = SHA of the template
file consumed (483b...). The verifier (D3) is configured with the same expected
template SHA and rejects mismatches. This closes finding 3's real gap: an
active receipt is now provably derived from a specific, verifier-accepted
template, with no placeholders and no extra/missing fields.

## D3. Verifier (`verify_scs_v2_stage_c_processing.py`)

### New pre-data rejection gate (before any table check)

After loading the receipt, before the existing hash bindings, add:

1. **Placeholder rejection**: fail if any string value in the receipt contains
   `<REQUIRED`.
2. **Template binding**: require
   `receipt["authorization_template_sha256"] == EXPECTED_TEMPLATE_SHA`, where
   `EXPECTED_TEMPLATE_SHA` is a module constant equal to the SHA of the
   template file the project treats as authoritative (483b6981...). Also
   require the on-disk template file's SHA to equal the same constant (catches
   template drift between authorize and verify).
3. **Field-set closure**: compute the active receipt's key set and require it
   to equal the template's key set with placeholders filled (i.e. the template
   keys minus scaffold-only keys like `producer_sha256` that authorize removes,
   plus none). Reject missing or extra keys.

### Command/parser count closure

Read `command_ledger.jsonl`, count by `role`, and require:

```
decompression_count == 192
mbinfo_count        == 192
mblist_u3_count     == 192
mblist_u0_count     == 192
processing_command_invocation_count == 768   # sum of the four
processing_parser_invocation_count  == 576   # mbinfo + mblist_u3 + mblist_u0
independent_verifier_parser_invocation_count == 0
```

The constants 192/768/576 are for the real 768-object sealed set. For the
fixture-driven readiness run (zero candidate), the ledger will be fixture-sized
and the verifier counts whatever the fixture ledger records (the readiness
verifier uses its own fixture ledger). The production verifier path keeps the
real-set closure. To avoid hardcoding two regimes, the verifier closes
**against the ledger actually present** (count roles, derive the totals), and
also checks the receipt's `object_count` to scale expectations: for the sealed
set `object_count = 768` implies 192 `.mb58.gz` bodies, so each command role =
192. The readiness fixture uses a small synthetic object count; its ledger
counts are whatever the fixture emits, and the verifier checks internal
consistency (sum of roles == processing_command_invocation_count, parser roles
sum == processing_parser_invocation_count, verifier own count == 0).

`independent_verifier_parser_invocation_count = 0` is asserted directly: the
verifier must not call mblist/mbinfo/gzip.

### H03 verification

Add a check (on the production path, reading `sounding_lineage.parquet`):
every row with non-finite `lon_deg` or `lat_deg` must have
`qc_hard_pass == False`, `qc_eligible_for_cell == False`, and
`lon_bin is None and lat_bin is None and cell_id is None`. The fixture tests
(D4) cover the case where the object also has valid rows.

## D4. Fixtures and offline tests

Extend `_common/tests/test_scs_v2_stage_c_processing.py` with fixtures built
from synthetic U3/U0 ASCII (the seven-column contract), not sealed bodies:

- `test_xy_nan_row_is_demoted_not_aborted`: one object, several valid rows +
  one `X=NaN` row. Assert object `parse_status == pass`, the NaN row is present
  in the sounding table with `qc_eligible_for_cell == False` and empty cell
  fields, and the valid rows aggregate normally.
- `test_y_nan_row_is_demoted_not_aborted`: same with `Y=NaN`.
- `test_valid_prefix_then_xy_nan_keeps_prefix`: valid rows before the NaN row
  are retained and eligible.
- `test_time_nan_still_aborts_object`: `M=NaN` aborts the whole object
  (`parse_status` time-failure, `parsed_row_count == 0`).
- `test_duplicate_key_still_aborts_object`: duplicate (ping, beam) aborts.
- `test_ineligible_sounding_excluded_from_aggregation`: an ineligible row
  (NaN X) does not appear in the eligible table or contributor/candidate
  aggregates.

The existing `test_parser_contract_failure_is_atomic_and_has_no_raw_rows`
remains valid for the time/duplicate paths.

## D5. Diagnostic registry

`research/diagnostic-failed-audit-contract-registry.json`: a single JSON object
recording run `20260807T090000Z`, its four SHAs and counts (from prd R5), the
six findings, and `classification: diagnostic_failed_audit_contract`. No file
under the original run directory is touched; the registry only references SHAs.

## D6. Zero-candidate readiness run

Reuse the existing readiness infrastructure
(`prepare_scs_v2_stage_c1a_readiness.py` produces
`stage_c_readiness/<RUN_ID>`; `verify_scs_v2_stage_c1a_readiness.py` verifies
it). The corrected code (D1) and verifier (D3) must be exercised by the
readiness fixtures, and the readiness run must record
`sealed_object_body_read_count = 0`, `archive_decompression_count = 0`,
`candidate_sounding_row_count = 0`, `candidate_cell_row_count = 0`.

If the existing readiness harness already runs on fixtures (the C1a receipt
shows `sealed_object_body_read_count = 0`), the main work is re-running it
against the corrected code and confirming the new H03 fixture passes inside
readiness, plus emitting the new command-count fields. If the readiness
verifier does not yet emit the split command counts, extend it minimally.

## Compatibility and risk

- **Producer hash changes** (D1 edits the helper and possibly the producer).
  This invalidates the frozen run's receipt by design; the run is already
  classified diagnostic and is not rerun.
- **Verifier hash changes** (D3). Same; the readiness run binds the new hash.
- **Authorize hash changes** (D2). The readiness authorization uses the new
  authorize.
- No sealed body is read at any point. The readiness fixtures are synthetic
  ASCII. The 090000Z directory is read-only for SHA computation (registry D5)
  and never written.

## Open technical decisions to confirm at review

1. `stage_c0_planning_commit` value: current `HEAD` of `main`, or the specific
   commit that introduced `stage-c0-planning-lock.json`? Proposal: the commit
   that last touched the planning lock file, resolved via
   `git log -1 --format=%H -- <planning-lock>`.
2. Whether to also drop `producer_sha256` from the **template** file (not just
   the active receipt). Proposal: yes, remove from template too, so the
   field-set closure check is template-driven.
3. Whether the readiness verifier needs the split command-count fields added,
   or only the production verifier. Proposal: add to both, sharing one counting
   helper.
