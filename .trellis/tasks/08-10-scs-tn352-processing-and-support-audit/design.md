# Design

## 1. Run structure and immutability

The producer writes to a temporary sibling directory and renames it to:

```text
ncei/derived/scs_tn352_processing_and_support_audit/<RUN_ID>/
```

The run ID uses the repository's bounded UTC identifier convention. Existing
run IDs and any completed phase directory fail closed. Phase A and Phase B
have separate manifests and verification receipts. A Phase B failure is
preserved under `<RUN_ID>.failed/phase_b/`; it never alters a passing Phase A.

The accepted Stage C run and the 20260807T090000Z comparison run are read-only.
The verifier records their before/after file inventories and hashes.

## 2. Evidence inputs

### Phase A

- accepted Stage C JSON/TSV/Parquet/SQLite outputs;
- accepted Stage C producer, helper, verifier, output schema, readiness bundle,
  and archived development handoff;
- `command_ledger.jsonl` and `environment.json`;
- old Stage C candidate/contributor outputs for the 0168 delta audit.

Phase A does not need `aggregation.sqlite` depth rows to answer the processing
chain. If 0168 median-rank attribution needs eligible depths, it reads only the
already exposed old/new Stage C Parquet lineage and candidate tables.

### Phase B

- TN352 rows from accepted `sounding_lineage.parquet` and
  `cell_cruise_candidates.parquet`;
- MRAR checked point lineage at
  `ncei/derived/regional_mrar/points_checked/bathymetry_points.parquet`;
- MRAR labels at
  `ncei/derived/validation_cells_1min/regional_mrar_experiment_cells.parquet`;
- the 2,244-row frozen scalar-pair assignment at the user-supplied archived
  GGM-task path, locked by SHA256;
- passing Phase A verification and its manifest.

No source outside these registered paths is permitted. The input lock records
absolute path, bytes, row count, schema, SHA256, and selected columns.

## 3. Phase A data flow

1. Verify the accepted run manifest, verification status, output hashes, and
   `development_only_not_confirmation` handoff.
2. Parse the command ledger as JSONL. Normalize only temporary paths for
   pattern reporting; retain every literal argv and argv hash in JSON.
3. Close each TN352 `.mb58.gz` processing row to exactly one decompression,
   `mbinfo`, U3 `mblist`, and U0 `mblist` invocation.
4. Inspect producer/helper code and environment material. Build a long-form
   processing contract with direct file/line or JSON-pointer evidence.
5. Recompute TN352 quality-state and eligibility counts from sounding lineage.
6. Compare object 0168 and the old/new candidate tables. For each affected
   cell, recompute old/new exact medians and quantify the recovered 0168 rows'
   rank contribution.
7. Apply the fixed A/B rule and render the report.
8. Run an independent verifier that does not invoke MB-System or open sealed
   bodies.

### Processing contract schema

`tn352_processing_contract.tsv` has one row per audit question:

```text
contract_item_id, category, item, status, observed_value, unit,
evidence_path, evidence_locator, evidence_sha256, notes
```

The JSON file contains run metadata plus the same ordered records. TSV string
values use canonical JSON encoding for arrays/objects. The verifier compares
the two representations field by field.

### Object-policy schema

`tn352_object_policy_summary.tsv` has one row per TN352 format-58 object and
contains object identity/hash, parse status, four command hashes, all/good/
flagged/null sounding counts, navigation-valid/invalid counts, H02/H03/H04
counts, eligible/review counts, candidate-cell count, and 0168 marker.

### Object 0168 schema

`tn352_0168_change_audit.parquet` contains the union of added and changed
cells. It records old/new presence, old/new eligible count and exact median,
signed and absolute median change, recovered 0168 all/eligible counts, recovered
depth range/NMAD, added-vs-changed status, and deterministic median-rank
diagnostics. H03 rows with no valid cell remain in the object-policy summary
and report-level conservation checks; they are never assigned to a cell using
invalid navigation.

## 4. Phase A classification

Classification A is allowed only when all of the following are verified:

- the official raw object identity and hashes close;
- processing beyond format decoding is documented as occurring either in the
  official upstream chain or locally, with retained command/parameter evidence;
- every applied depth/navigation correction has a traceable parameter/input;
- the depth lineage from raw field through correction to output is known;
- correction status for SVP, tide, draft, lever arm, attitude, and patch test is
  either verified applied or verified explicit no-op.

If any condition is false or unknown, classification B is emitted. Parsed
format-58 rows and source-internal QC do not by themselves satisfy A.

If B is emitted, `audit_report.md` and the JSON contract include an unexecuted
`TN352-v2-processed` proposal. It is a lock proposal, not an authorization. It
must list exact source hashes, available/missing correction inputs, proposed
MB-System commands and parameter hashes, output schema, independent checks,
and stop rules. Unknown correction inputs remain blocking fields.

## 5. Phase B freeze order

Phase B uses three separate commands/processes:

1. `freeze`: verify Phase A pass, combine the unchanged geometry protocol with
   the user-approved cohort amendment, hash inputs, compare only frozen/TN352/
   MRAR raw-support IDs, register all set differences, create the exact
   2,244-cell cohort, and exit.
2. `run`: require the immutable freeze outputs and their hashes, then open the
   registered point and depth columns and produce support outputs.
3. `verify`: independently recompute the cohort, geometry, matches, metrics,
   row conservation, and output hashes.

The `run` command refuses a protocol with status other than `approved_frozen`,
an input hash mismatch, a cohort hash mismatch, or a non-passing Phase A
receipt. This process boundary makes the pre-depth freeze auditable.

## 6. Phase B source selection

### Common cells

- Analysis IDs: all 2,244 unique `cell_id` values from the frozen assignment,
  retaining its `split`, `role`, sorted index, and permutation position.
- TN352 side: accepted Stage C candidates with `official_cruise_id == "TN352"`,
  `aggregation_basis == "individual_qc_eligible_beams_exact"`, and centers
  inside `[105,125) x [0,25)`.
- MRAR raw-support side: checked points with `point_check_pass_basic == true`
  and finite coordinates in the same rectangle; recompute `cell_id` from the
  coordinates without opening depth.
- Require every frozen ID in TN352 and MRAR raw support. Register, but exclude,
  the 123 additional current raw-support cells. Require the MRAR cell-label row
  for every included frozen ID.
- Sort by `(lat_bin, lon_bin, cell_id)`. The expected unique count is 2,244.

### TN352 support points

Use accepted sounding-lineage rows with TN352, common `cell_id`, and
`qc_eligible_for_cell == true`. Recompute and verify cell membership. Stable
identity is `(source_object_id, parser_ping_index, beam_index)`.
The Stage C candidate field `n_source_objects` counts objects containing any
sounding in the cell. The support output separately counts and lists objects
that contribute selected eligible points; that count may be smaller.

### MRAR support points

Use checked MRAR rows with `point_check_pass_basic == true`, finite lon/lat,
finite positive-down depth, and recomputed `cell_id` in the common cohort.
Stable identity is `(track_id, point_index_in_track)`. No new quality or depth
filter is introduced.

Before matching, recompute exact source medians per cell and require closure to
the Stage C candidate median and MRAR `representative_depth_m`. Any mismatch is
a hard failure, not a reason to replace points.

## 7. Frozen geometry

The approved protocol in `research/support-protocol-v1.yaml` is authoritative.
The implementation uses its definitions verbatim:

- longitudes/latitudes are decimal degrees;
- distances use unit-sphere Cartesian vectors and mean Earth radius
  6,371,008.8 m;
- a source centroid is the normalized mean unit vector of its points;
- centroid and point distances are great-circle arc lengths;
- nearest searches use `scipy.spatial.cKDTree` on unit vectors, then recompute
  arc distance; equal-distance ties use stable point identity;
- mutual-nearest status is computed once without a distance cutoff;
- the 100, 250, and 500 m files are nested subsets of that one pair set;
- 100 m occupancy uses a local tangent equirectangular plane centered on the
  exact cell center and indices `floor(x/100), floor(y/100)`.

## 8. Frozen depth metrics

All depths are metres positive down. For every matched pair:

```text
delta_m = TN352_depth_m_positive_down - MRAR_depth_m_positive_down
```

Positive delta means TN352 is deeper. Per-cell and aggregate summaries use:

```text
bias = mean(delta)
MAE = mean(abs(delta))
RMSE = sqrt(mean(delta^2))
P50/P95 = quantile(abs(delta), 0.50/0.95), linear interpolation
min/max = signed min/max(delta)
NMAD = 1.4826 * median(abs(depth - median(depth)))
```

Metrics are unweighted. Empty matched sets have count zero and null metrics.

The raw cell difference is:

```text
raw_cell_median_delta_m = TN352_exact_median - MRAR_representative_depth
```

For tail comparison, each matched cell also has the signed median of its pair
deltas. Comparisons use the same set of cells at each threshold.

## 9. Tail and association decisions

The protocol fixes these diagnostic flags before depth access:

- raw or persistent tail: absolute cell-level delta greater than 500 m;
- high relief: maximum of the two source depth ranges at least 500 m;
- zero footprint overlap: occupancy intersection equals zero;
- low footprint overlap: occupancy Jaccard below 0.25;
- low matched support: fewer than 3 mutual pairs at the threshold;
- small source support: one TN352 object or one MRAR track in the cell;
- H03-associated: a contributing TN352 object has one or more H03 rows in its
  object summary. This is object association, not reassignment of invalid rows.

For a threshold with at least 30 matched cells, the report says the tail
`materially_contracted` only when both:

```text
matched_abs_cell_delta_p95 / raw_abs_cell_delta_p95 <= 0.75
matched_tail_fraction / raw_tail_fraction <= 0.75
```

Zero denominators are handled explicitly as `not_applicable`; fewer than 30
matched cells yields `insufficient_support`.

A tail concentration flag is positive only when the registered stratum has at
least 10 tail cells and its tail prevalence risk ratio versus the complement
is at least 2.0. Exact counts and risk ratios are always reported.

A cell is unresolved when it is a raw tail cell, has no mutual pair within
500 m or retains an absolute matched-cell median delta above 500 m, and has
none of the registered footprint, relief, low-support, small-support, or H03
association flags. These flags are associations, not causal explanations.

## 10. Phase B output schemas

### Cell-ID freeze evidence

`cell_id_comparison.json` records both directions of every frozen/current
raw-support set difference. `phase_b_cell_id_status.parquet` contains all 2,368
TN352 candidate IDs and assigns exactly one analysis status; only
`frozen_scalar_pair` rows may enter the difference outputs.

### `tn352_mrar_support_cells.parquet`

Exactly one row per common cell. It contains identity/centers; point, object,
track, navigation and H03 counts; both centroids; centroid/minimum distance;
both depth range/NMAD values; occupancy metrics; raw median difference; and,
for each threshold, pair count and all registered depth metrics. It also
contains the frozen diagnostic flags and unresolved status.

### `matched_difference_<threshold>m.parquet`

One row per mutual pair within the inclusive threshold. Columns retain cell
identity, both stable point identities, both lon/lat coordinates, both depths,
distance, signed delta, absolute delta, both source-object/track identifiers,
TN352 cruise ID, and TN352 navigation/QC evidence. Keys are unique and the
100 m set is a subset of 250 m, which is a subset of 500 m.

### `support_tail_summary.csv`

Contains overall and registered-stratum rows for raw and 100/250/500 m
support-matched cell summaries: cohort count, matched count, tail count/share,
absolute P50/P95, contraction ratios, risk ratio, concentration decision,
unresolved count, and label-upgrade conclusion.

## 11. Label conclusion

Phase B can describe support-matched compatibility only. It cannot prove that
TN352 received processing corrections, cannot prove MRAR independence or
truth, and cannot change B to A. If Phase A emits A, Phase B may report whether
the spatial-support diagnostic supports retaining that development reference;
it still cannot promote it to confirmation.

## 12. Independent verification

Each verifier must inspect actual producer schemas rather than trust planned
columns. It independently checks:

- input/output inventories and SHA256;
- run immutability and phase ordering;
- no sealed-body or prohibited external input access;
- row/key uniqueness and conservation;
- A/B decision inputs;
- exact median closure and 0168 old/new changes;
- common-cell identity and expected count;
- centroid, nearest-pair, occupancy and metric recomputation;
- threshold nesting and tie resolution;
- frozen tail rules and all report conclusions.

The verifier writes `verification.json` last. A partial run or a missing pass
receipt is not citable.
