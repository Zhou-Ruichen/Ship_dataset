# Design: SCS ship sounding QC v2 pre-correction investigation

## Boundary

This is an additive audit beside the archived lineage and product-consistency
runs. It produces evidence for a later QC v2 task but cannot mutate upstream
points, labels, quality flags, validation roles, cohorts, or splits. Product
differences are used only to freeze candidate/reference-control cohorts; all
candidate mechanism features are computed from lineage, raw records,
contributor structure, and official metadata.

## Components

1. `ncei/configs/scs_ship_qc_v2_preflight.yaml` freezes input paths/hashes,
   candidate definition, raw context size, control seed/strata, component
   adjacency, closed vocabularies, expected counts, and output guards.
2. `ncei/code/audit_scs_ship_qc_v2_preflight.py` validates inputs, builds the
   candidate/component/control/aggregation/metadata evidence, and publishes an
   immutable run plus manifest and reports.
3. `ncei/code/verify_scs_ship_qc_v2_preflight.py` independently recomputes
   contractual counts, arithmetic, hashes, raw-row containment, state closure,
   and forbidden-output checks.
4. `_common/tests/test_scs_ship_qc_v2_preflight.py` covers range expansion,
   component labelling, deterministic controls, raw-context features,
   weighted aggregation, status closure, and forbidden schema/path guards.

## Data Flow

```text
frozen product diagnostics ----> 905 candidate IDs + 16 reference conflicts
                                      |
cell lineage + raw replay ------------+--> contributor/raw-row registry
                                      |             |
                                      |             v
                                      |      targeted raw context features
                                      v
                          connected components + controls

all multi-file/multi-cruise lineage --> aggregation alternatives (diagnostic)
identity + vertical ledgers ----------> metadata/correction feasibility

all evidence --> collaborator decision pack + manifest --> verifier
```

## Candidate and Reference Boundary

The candidate predicate is frozen only to reproduce the already-opened
diagnostic tail:

```text
abs(gebco_2024_minus_ship_m) > 1000
```

It is not a proposed QC rule. The driver carries the signed difference and
product spread for provenance but does not expose them to raw-feature
thresholds or descriptive-state assignment. Reference-version controls are:

```text
abs(gebco_2024_minus_ship_m) > 1000
and abs(family_consensus_minus_ship_m) <= 100
```

They are forced to `reference_version_conflict` and excluded from any future
positive-rule calibration export.

## Component Contract

Components use exact integer `lon_index`/`lat_index`, 8-neighbour adjacency,
identical `source_provider`, and identical difference sign. Component IDs are
stable hashes of sorted member cell IDs. No distance tolerance or product
value is tuned after inspection.

## Raw Context Contract

Lineage zero-based inclusive ranges are expanded exactly. A fixed record-index
window around each target row is collected from only the referenced raw files.
The file SHA is verified before parsing. Context rows remain labelled by their
evidence ceiling:

- JAMSTEC three-column rows: `raw_record_order_only` unless actual time/sonar
  fields exist in the parsed file layout;
- MRAR quadrant rows: `source_grid_order_only`;
- no record ordering is called a line, swath, beam, or crossover without
  verified metadata.

Raw-only summaries use finite parsed values and a fixed nearby-coordinate
radius. Empty or insufficient context is preserved, not filled. NMAD is
`1.4826 * median(abs(x - median(x)))`.

## Control Contract

Controls are deterministic, disjoint from candidates, and sampled from the
same provider/raw-file support with frozen strata for ship-depth band and raw
point-count band. A seeded hash ordering chooses controls without looking at
downstream errors. Product difference may be carried after selection for
diagnostic comparison but cannot affect membership or raw-feature thresholds.
When an exact depth+point-count stratum is short, matching falls back in the
frozen order same-file+depth, same-file+point-count, then same-file only; the
actual `control_match_level` is persisted.

## Aggregation Contract

Contributor JSON is the authoritative per-file-cell input. For values `z_i`
and exact point counts `n_i`, persist:

```text
current_unweighted_median = median(z_i)
point_count_weighted_mean = sum(n_i * z_i) / sum(n_i)
point_count_weighted_median = first z in sorted order where cumulative n
                              reaches at least half total n
dominant_contributor_median = z_i for maximum n_i
between_contributor_nmad = NMAD(z_i)
```

These alternatives are descriptive. They are not treated as corrected cell
depths and are never joined into an existing validation product.

## Interpretation Contract

State assignment is conservative:

- reference controls are `reference_version_conflict`;
- multi-contributor candidates with material contributor spread may be
  `aggregation_conflict`;
- strong raw record/grid discontinuity evidence may receive the matching
  candidate state;
- smooth conflict or plausible steep terrain remains
  `terrain_or_source_ambiguous`;
- missing usable context is `insufficient_raw_context`.

No state means `invalid`, `exclude`, `correct`, or `replace`.

## Metadata Feasibility

The identity and vertical ledgers provide the factual ceiling. Existing source
reports/configs may add verified raw-layout availability, but missing fields
remain literal unknown/not recoverable. Crossover feasibility requires all of:

- verified cruise plus line/time identity;
- at least two comparable lines/surveys;
- common known vertical reference;
- raw observations capable of reconstructing the overlap.

Failure of any condition yields `not_feasible_from_current_inputs`.

## Outputs and Safety

- Full execution requires `--confirm-audit`; `--estimate-only` validates
  hashes, schemas, closure, and expected workload without creating a run.
- Existing run IDs are immutable and fail before writes.
- Outputs are atomic and include an inventory with SHA256.
- Forbidden output tokens/columns include corrected depth, invalid/exclude,
  eligibility, validation/sample weight, role, cohort, split, prediction, and
  model error. The required point-count-weighted aggregation diagnostics are
  explicitly descriptive and are not sample weights.
- The independent verifier reads persisted outputs and frozen inputs rather
  than trusting producer summaries.

## Performance

The analysis reads small frozen parquet/CSV artifacts in memory. Raw text/XYZ
files are streamed once per referenced file while retaining only requested row
windows; no global bathymetry product or downstream model artifact is read.

## Rollback

The run and code are additive. Rollback abandons the immutable run directory
and reverts task-owned code/config/spec changes. Existing raw points, v1
labels, archived audits, and downstream repositories remain untouched.
