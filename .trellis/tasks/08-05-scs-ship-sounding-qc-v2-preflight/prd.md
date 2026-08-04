# SCS ship sounding QC v2 pre-correction investigation

## Goal

Produce a frozen, read-only evidence package that determines which ship-depth
disagreement mechanisms can support a future QC v2 rule and which must remain
ambiguous or unresolved. The task must give the user and collaborators enough
raw-context, aggregation, and metadata evidence to freeze correction policy
without changing any sounding, label, cohort, split, or downstream result.

## Confirmed Facts

- The frozen cohort contains 174,965 unique 1-arcminute cells: 165,966 MRAR
  and 8,999 JAMSTEC.
- Against GEBCO 2024, 905 cells have absolute diagnostic disagreement greater
  than 1,000 m: 857 MRAR and 48 JAMSTEC. The JAMSTEC cells involve five raw
  files and four official cruises (`KR13-18`, `KR15-18`, `KY02-01`,
  `KY12-08`).
- All 153 cells with disagreement greater than 5,000 m are MRAR.
- Sixteen cells have GEBCO 2024 disagreement greater than 1,000 m while the
  family-balanced product consensus is within 100 m of the ship label; these
  are reference-version conflict controls, not ship-QC positives.
- The cohort has 2,658 multi-file cells and 2,472 multi-cruise cells. There are
  124 cells with between-file NMAD greater than 100 m and 121 with
  between-cruise NMAD greater than 100 m.
- Current JAMSTEC point QC checks coordinates, sign, finiteness, and depth no
  greater than 12,000 m; current MRAR cleaning treats values below -11,500 m
  as sentinel. These broad range checks do not detect the observed spikes.
- Current merged representative depth is the unweighted median of per-file or
  per-track cell medians. A sparse anomalous contributor can therefore receive
  the same vote as a dense contributor.
- JAMSTEC identity is official, but vertical datum remains officially unknown.
  MRAR cruise, line, time, and vertical reference are not recoverable.
- MRAR adjacent source rows cannot be promoted to verified adjacent pings or
  used for crossover adjustment.

## Frozen Inputs

| Role | Path | SHA256 |
|---|---|---|
| Product diagnostic | `ncei/derived/scs_product_consistency_coverage/20260804T210900Z/product_consistency_by_cell.parquet` | `3c6a140e3569c16611fa6540590d711bbfaf372e9f2d69e10da3c272c17b624e` |
| Cell lineage | `ncei/derived/scs_upstream_lineage_audit/20260804T202026Z/cell_lineage.parquet` | `0d58cf5f18233f1abb6cd111f6167eec7e5c00fc7cdb9667b49f00ef9aa7a74d` |
| Raw replay | `ncei/derived/scs_upstream_lineage_audit/20260804T202026Z/raw_to_cell_replay.parquet` | `269b23072a0cb5e7c7ca569e03da8a05cca469e7a39271d8920c9a4c389b2ed0` |
| Identity ledger | `ncei/derived/scs_upstream_lineage_audit/20260804T202026Z/source_identity_ledger.csv` | `089ad0cacbff2a3cd89407ec8f818445691883c63f20b44c128b9791c9baaffb` |
| Vertical ledger | `ncei/derived/scs_upstream_lineage_audit/20260804T202026Z/vertical_datum_ledger.csv` | `4b83f872997cffcf80bd85e753467be2fc498d5048c826b78c22510690b583d0` |

Every raw source file referenced by `cell_lineage.parquet` must also match its
persisted SHA256 before its rows are inspected.

## Requirements

### R1. Immutable, bounded execution

- Validate all frozen hashes, schemas, key closure, source counts, and expected
  candidate counts before producing an output run.
- Write one new immutable run-ID directory and refuse overwrite.
- Read only raw files referenced by candidate or deterministic control cells.
  Do not scan the global processing chain or regenerate upstream products.

### R2. Strict evidence boundary

- Do not read downstream predictions, residuals, model errors, metrics,
  `external_samples.parquet`, `outlier97`, roles, or split assignments.
- Product differences may define diagnostic candidate and reference-conflict
  cohorts. They must not define a QC threshold, corrected depth, invalid flag,
  weight, eligibility decision, or replacement value.
- Preserve positive-down metres and retain vertical-datum uncertainty in every
  interpretation of absolute differences.

### R3. Complete candidate and component registry

- Persist all 905 cells with `abs(GEBCO_2024 - ship) > 1,000 m`, with signed
  difference, source, lineage/replay fields, raw contributor identities, and
  product-family spread.
- Partition candidates into deterministic 8-neighbour connected components by
  source and difference sign. Record component extent, size, maximum
  disagreement, raw-point/file/cruise counts, and product-spread summaries.
- Persist the 16 reference-version conflict cells as a protected negative
  control cohort.

### R4. Raw-record context and negative controls

- Expand the exact zero-based raw-row ranges from lineage and extract a fixed
  record-index context window around candidate observations.
- For JAMSTEC, label record adjacency as record-order evidence only unless time
  and beam metadata are actually present. Do not infer beam number or swath
  membership from position in a three-column file.
- For MRAR, label neighbouring source rows as source-grid context only. Never
  call them adjacent pings, tracks, or crossover evidence.
- Compute raw-only context features such as target/context depth medians,
  NMAD, range, coordinate separation, record-order jump, and target residual
  from nearby finite context. These are descriptive features, not deletion
  rules.
- Include a deterministic, source/file/depth/count-stratified control sample
  from non-candidate cells. Record the seed and exact control IDs.

### R5. Aggregation-conflict census

- Persist all 2,658 multi-file cells and all 2,472 multi-cruise cells without
  row loss.
- Recompute, from contributor records only, the current unweighted median,
  point-count-weighted median, point-count-weighted mean, dominant-contributor
  median, contributor range, and between-contributor NMAD.
- Do not select a replacement aggregation rule. Produce paired differences and
  clearly identify cases where sparse and dense contributors receive equal
  current weight.
- Keep the 52 Step 04a replay differences separate from bad-ping evidence.

### R6. Metadata and correction-feasibility matrix

- Cover every represented official JAMSTEC cruise and every vertical-ledger
  row, not only the four extreme-disagreement cruises.
- Report availability/status for time, line, sonar, sound-velocity correction,
  tide correction, horizontal reference, vertical datum, beam identity, raw
  sonar, and processed XYZ only.
- Mark crossover/line adjustment feasible only when line/time identity and a
  common vertical reference are established. Unknown must remain unknown.

### R7. Closed interpretation vocabulary

Each candidate/component must receive one descriptive state from:

```text
raw_record_discontinuity_candidate
source_grid_discontinuity_candidate
aggregation_conflict
reference_version_conflict
terrain_or_source_ambiguous
insufficient_raw_context
```

These states do not authorize deletion or numerical correction. Factual
metadata fields continue to use the existing five-level status vocabulary.

### R8. Collaborator decision package

Produce a concise decision package that separates repository-supported facts
from choices requiring collaborator approval:

- target meaning of a 1-minute label;
- invalid versus ambiguous versus unresolved data roles;
- MRAR train-only/exclude/partial-retention policy;
- future aggregation estimator and uncertainty representation;
- conditions for line/crossover adjustment;
- v1/v2 cohort and split migration policy.

The package must recommend a choice where evidence supports one, describe the
trade-off, and leave the decision explicitly pending.

### R9. Deliverables and independent verification

Each run must contain:

- `candidate_cells.parquet`
- `candidate_components.parquet`
- `raw_context_features.parquet`
- `control_cells.parquet`
- `aggregation_conflicts.parquet`
- `reference_conflicts.parquet`
- `metadata_feasibility.csv`
- `preflight_summary.json`
- `collaborator_decision_pack.md`
- `audit_report.md`
- `audit_manifest.json`
- verifier-produced `verification.json`

An independent verifier must recompute input/output hashes, key and count
closure, candidate/component membership, control determinism, aggregation
arithmetic, raw-row containment, state vocabulary, evidence flags, and the
absence of correction/deletion/weight/split outputs.

## Acceptance Criteria

- [x] Frozen input and referenced raw-file hashes all match.
- [x] Candidate closure is exactly 905 cells: 857 MRAR plus 48 JAMSTEC.
- [x] The 48 JAMSTEC candidates close on five files and four official cruises.
- [x] The 153 MRAR cells with absolute diagnostic difference >5,000 m and 16
      reference conflicts are retained.
- [x] Every candidate belongs to exactly one deterministic component and has
      raw context or an explicit `insufficient_raw_context` state.
- [x] Controls are reproducible from a frozen seed and contain no candidate ID.
- [x] Aggregation census contains exactly 2,658 multi-file cells and preserves
      all 2,472 multi-cruise cells.
- [x] Replay differences close on 174,913 exact plus 52 different and are not
      promoted to bad-ping evidence.
- [x] Metadata feasibility covers all represented official cruises and all
      vertical-ledger rows without filename inference.
- [x] No output changes a depth, QC pass flag, role, weight, cohort, or split.
- [x] Unit tests, estimate-only mode, one immutable full run, independent
      verification, task validation, and `git diff --check` pass.

## Out of Scope

- Deleting or correcting raw soundings or 1-minute labels.
- Implementing QC v2 thresholds, crossover adjustment, CUBE, or a new grid.
- Replacing any missing or rejected sounding with GEBCO/product consensus.
- Choosing the final scientific label target without collaborator approval.
- Editing downstream repositories, cohorts, splits, or model inputs.
- Reading or using any downstream model error.

## Open Questions

No question blocks this preflight. The label target, MRAR role, aggregation
estimator, crossover policy, and split migration are explicit outputs for the
collaborator decision gate before correction implementation.
