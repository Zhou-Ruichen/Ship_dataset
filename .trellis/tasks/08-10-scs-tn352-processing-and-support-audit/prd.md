# SCS TN352 processing and support audit

## Goal

Establish what processing actually occurred between the official NCEI TN352
format-58 objects and the immutable Stage C one-arcminute development labels.
After that audit passes independent verification, diagnose whether the TN352
and MRAR depth tail changes when the two sources have matched spatial support.

The authoritative Stage C run is immutable:

```text
ncei/derived/scs_v2_sealed_confirmation/stage_c/20260808T231659Z
```

This task does not create confirmation evidence. Its maximum output role is
`development_only_not_confirmation`.

## Evidence levels

The report must keep these levels separate:

1. `official_raw_multibeam_source`: official NCEI TN352 `.mb58.gz` objects.
2. `mbsystem_parsed_sounding`: rows emitted by the recorded MB-System parser.
3. `source_internal_qc_retained_sounding`: parsed rows satisfying the frozen
   Stage C eligibility rules.
4. `one_arcmin_exact_median_development_label`: per-cruise exact medians from
   retained soundings.
5. `validated_bathymetric_truth`: not established by this task.

## Requirements

### R1. Immutable inputs and prohibited operations

- Read the accepted Stage C run, its code, command ledger, environment record,
  manifests, schemas, and already exposed derived lineage only.
- Do not modify any file in the accepted Stage C run or its 20260807T090000Z
  reference run.
- Phase A must not open a sealed object body. It audits retained evidence.
- Phase B may read only already exposed derived TN352 and MRAR lineage. It must
  not open a new sealed object or any `.fnv`, `.inf`, or `.fbt` body.
- The Phase B cohort is the complete set of 2,244 `cell_id` values in the
  user-supplied `paired_split_assignments.parquet`; its file SHA256 and split
  metadata are frozen before depth access.
- Do not run GGM, PINN, GEBCO, product residuals, model residuals, datum/bias
  fitting, cross-cruise aggregation, or depth-based selection/exclusion.
- Write a new immutable audit run. Existing run IDs must fail closed.

### R2. Phase A processing audit

For TN352, close every conclusion against code, `command_ledger.jsonl`,
`environment.json`, source-object rows, sounding lineage, candidate labels,
and retained verification records. Report:

- MB-System version, source commit/tag or package evidence, binary hashes, and
  environment digest;
- whether `mbformat`, `mbpreprocess`, `mbprocess`, `mblist`, `mbclean`, and
  `mbareaclean` were invoked;
- every actual command pattern and all flags, plus per-object command closure;
- whether Stage C parsed decompressed format-58 directly;
- U3/U0 fields, join key, completeness and independent-state limitations;
- depth source field, unit, sign, range, and any conversion;
- native good/flagged/null policy and the Stage C beam eligibility policy;
- U3/U0 navigation validity and `H03_NAVIGATION_RANGE` policy;
- whether amplitude, native quality code, beam angle, speed, depth range, SVP,
  tide, draft, lever arm, attitude, or patch-test corrections affected output;
- whether `.par`, `.esf`, `.fnv`, `.fbt`, or `.inf` bodies were read;
- the exact conjunction defining `qc_eligible_for_cell`;
- whether original NCEI depth was corrected before the current output; use
  `unknown` or `not_performed` when the repository cannot establish it;
- why object 0168 recovered 96,768 soundings and 86,184 eligible rows, why 198
  rows are H03, and how recovered rows added 10 cells and changed the exact
  medians of 20 common cells relative to 20260807T090000Z.

Every contract item has one of these statuses:

```text
verified_used
verified_not_used
known_from_output
unknown
not_performed
not_applicable
```

Absence from a command ledger is evidence only that the retained ledger did
not record the command. A `verified_not_used` result additionally requires
code-path and invocation-count closure.

### R3. Phase A classification

Choose exactly one classification:

```text
A = official_cruise_processed_development_reference
B = official_raw_source_development_label
```

Classification A requires a complete, evidenced processing chain beyond raw
format parsing, whether that processing occurred in the official upstream
archive or locally, including applied correction inputs and parameter sources.
Missing, unknown, or unexecuted correction provenance yields B. Neither result
is confirmation.

If the result is B, the report must contain a frozen, unexecuted
`TN352-v2-processed` proposal. It must identify required raw objects,
correction inputs, commands, parameters, output role, validation checks, and
unresolved prerequisites. It must not run reprocessing without separate user
authorization.

### R4. Phase B entry gate and cohort

Phase B starts only when Phase A `verification.json` has `status=pass`. Before
any depth-difference column is opened, the implementation must:

- copy and hash the approved `research/support-protocol-v1.yaml` into the new
  Phase B run;
- hash all Phase B inputs and write an input lock;
- compare the 2,244 frozen IDs against current TN352 candidates and current
  MRAR basic-pass raw-support IDs using non-depth identity/geometry columns;
- stop before depth access if any frozen ID is absent from either source;
- when the subset gate passes, write the exact 2,244-ID analysis cohort and
  mark the additional 123 current raw-support cells as
  `raw_support_only_not_in_frozen_scalar_pair` so they cannot enter a source
  difference output.

No cell, point, object, threshold, or stratum may be changed after a depth
difference is observed.

### R5. Phase B support metrics

For every common cell, report:

- TN352 and MRAR point counts and source-object/track counts;
- source centroids and centroid distance;
- minimum cross-source point distance;
- per-source depth range and NMAD;
- mutual-nearest matched-pair counts within 100, 250, and 500 m;
- for every distance threshold: count, signed bias, MAE, RMSE, absolute P50,
  absolute P95, signed minimum, and signed maximum;
- 100 m occupancy-grid intersection, union, Jaccard, and smaller-support
  coverage;
- original cell-median difference with an explicit positive-down sign;
- cruise, source object, MRAR track, navigation, and H03 counts.

Pair-level outputs must retain stable row identities, both coordinates, both
positive-down depths, distance, and signed depth difference. A pair must be
mutual-nearest before the distance threshold is applied.

### R6. Required conclusions

The Phase B report must answer, under the frozen definitions:

1. whether the original cell-level tail materially contracts in the
   mutual-nearest support-matched subset;
2. whether persistent tail cells are concentrated in zero/low footprint
   overlap, high relief, small object/track support, or H03-associated objects;
3. how many cells remain unresolved by the registered diagnostic factors;
4. whether the evidence supports a TN352 development-label upgrade.

Spatial agreement with MRAR cannot establish source independence, processing
provenance, or validated truth. Phase B alone cannot change B to A and cannot
promote either class to confirmation.

## Required outputs

Use separate phase directories because both phases have files with the same
names:

```text
ncei/derived/scs_tn352_processing_and_support_audit/<RUN_ID>/
  phase_a/
    tn352_processing_contract.tsv
    tn352_processing_contract.json
    tn352_object_policy_summary.tsv
    tn352_0168_change_audit.parquet
    audit_report.md
    audit_manifest.json
    verification.json
  phase_b/
    frozen_protocol.json
    input_lock.json
    cell_id_comparison.json
    phase_b_cell_id_status.parquet
    common_cell_cohort.parquet
    tn352_mrar_support_cells.parquet
    matched_difference_100m.parquet
    matched_difference_250m.parquet
    matched_difference_500m.parquet
    support_tail_summary.csv
    audit_report.md
    audit_manifest.json
    verification.json
```

The Phase B protocol, input lock, ID comparison, ID-status table, cohort, and
freeze receipt are required auxiliary evidence and must be included in the
Phase B manifest.

## Acceptance Criteria

- [x] Phase A reproduces the supplied four-cruise, TN352, SCS, and object 0168
      counts from the immutable derived artifacts without opening sealed data.
- [x] Phase A lists every retained command invocation and proves that command
      role counts close to the accepted verification receipt.
- [x] Every requested processing/correction item has a status and direct
      evidence locator; absent evidence is reported as `unknown` or
      `not_performed`, not inferred as success.
- [x] The five evidence levels remain distinct and exactly one A/B
      classification is emitted with `confirmation_role_eligible=false`.
- [x] The 0168 audit accounts for all 96,768 recovered rows, 86,184 eligible
      rows, 198 H03 rows, 10 added cells, and 20 changed common-cell medians.
- [x] Phase A TSV/JSON records are semantically identical and independently
      verified; all Phase A outputs are hashed in the manifest.
- [x] Phase B cannot start unless Phase A verification passes and the frozen
      protocol/input/cohort locks exist before depth access.
- [x] The common-cell cohort is unique, SCS-bounded, and exactly 2,244 rows;
      count drift stops execution.
- [x] Point identities are unique, cell membership is recomputed, and both
      source cell medians close against the frozen label tables before support
      metrics are accepted.
- [x] Mutual-nearest pairs are unique and nested across 100, 250, and 500 m;
      every pair-level difference recomputes exactly as TN352 minus MRAR.
- [x] `tn352_mrar_support_cells.parquet` contains exactly one row for each
      common cell, including zero-match cells with explicit null metrics.
- [x] Tail and concentration conclusions use only pre-registered thresholds;
      no post-result filter or threshold change is permitted.
- [x] Independent Phase B verification recomputes cohort identity, geometry,
      pair membership, metrics, hashes, and prohibited-access counters.
- [x] Both reports state that no GGM, PINN, GEBCO, model comparison, or product
      residual comparison was run and that results remain development-only.

## Notes

The user-supplied expected common-cell count is a gate, not permission to
adjust cell definitions until the count matches. A mismatch is a recorded
failure and requires review.
