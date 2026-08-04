# SCS Frozen-Cohort Lineage Audit

## 1. Scope / Trigger

Use `ncei/code/audit_scs_upstream_lineage.py` only for the frozen South
China Sea handoff cohort. It is a provenance and replay audit, not a quality
filter. It must not read predictions, residuals, model errors, or use GEBCO
agreement to remove or relabel cells.

## 2. Signatures

Run from the repository root:

```bash
python ncei/code/audit_scs_upstream_lineage.py \
  --downstream-union <downstream_cell_union.parquet> \
  --counts-closure <counts_closure.json> \
  --downstream-manifest <manifest.json> \
  --external-group-manifest <group_manifest.parquet> \
  --run-id <UTC_RUN_ID> \
  --confirm-audit

python ncei/code/verify_scs_upstream_lineage_audit.py \
  --run-dir ncei/derived/scs_upstream_lineage_audit/<UTC_RUN_ID>
```

The driver refuses to run without `--confirm-audit` or when cwd is not the
repository root. A run ID is immutable: an existing run directory is an error.

## 3. Contracts

Inputs:

- Exactly four handoff files; each SHA256 is frozen in the audit driver.
- Exactly 174,965 unique `canonical_cell_id` values.
- Source closure is 165,966 `mrar` plus 8,999 `jamstec` cells.
- External identity closure is 4,229 cells in 12 candidate groups.

Outputs under one run-ID directory:

- `cell_lineage.parquet`: one row per frozen cell, exact raw-file hashes and
  zero-based inclusive raw-row ranges.
- `source_identity_ledger.csv`: exactly 12 rows and identity state in
  `official_exact`, `official_leg_ambiguous`, `filename_only`, `unresolved`.
- `vertical_datum_ledger.csv`: one row per represented source/cruise. Missing
  vertical metadata remains literal `unknown`.
- `raw_to_cell_replay.parquet` and `diff_summary.json`: exact raw replay plus
  within-file, between-file, and between-cruise NMAD where defined.
- `audit_report.md`, `audit_manifest.json`, and verifier-produced
  `verification.json`.

Every factual value has a paired `<field>_status` from:

```text
known
officially_unknown
not_recoverable
inferred_from_filename
verified_from_source_metadata
```

### Step 04a exactness boundary

`jamstec/multibeam/code/04a_make_multibeam_file_cells.py` reads point parquet
in batches. If a `(file_id, cell_id)` crosses batches,
`_combine_chunk_cells()` stores an `n_points`-weighted average of the chunk
medians in `median_depth_m_positive_down`. It is not the exact median over all
raw points for that file-cell. Point counts remain additive and exact.

Consumers that need exact raw-point medians must replay the raw/QC points.
They must preserve both the stored value and signed difference rather than
silently replacing historical products.

## 4. Validation & Error Matrix

| Condition | Required behavior |
|---|---|
| Any frozen input SHA differs | Abort before output directory creation |
| Cell/source/group closure differs | Abort before raw replay |
| Downstream filename contains prediction/residual/error token | Reject input |
| Official metadata omits vertical datum | Write `unknown` + `officially_unknown` |
| Cruise/line cannot be recovered | Write empty value + `not_recoverable` |
| Output run ID already exists | Abort; never overwrite |
| File-cell raw point count differs from upstream | Fail audit |
| Stored and exact raw median differ with equal counts | Preserve diff and report Step 04a approximation |
| Any field status is outside the five-value vocabulary | Fail audit and verifier |

## 5. Good / Base / Bad Cases

- Good: official PDF cruise ID, member list, leg mapping, and delivered file
  envelope agree; identity is `official_exact` with PDF path and SHA256.
- Base: datum is absent from an inspected official PDF; value is `unknown` and
  status is `officially_unknown`.
- Bad: infer a datum, line ID, or cruise identity from a plausible filename and
  label it `verified_from_source_metadata`.
- Bad: drop a cell because `abs(ship - GEBCO) > 3 * std`.

## 6. Tests Required

- Unit-test longitude normalization, 1-minute cell assignment, range
  compression, grouped NMAD, official member-name normalization, MRAR trailing
  tabs, five-level enums, and file-cell count/median diagnostics.
- Run the full bounded audit and then the independent verifier.
- Assert 174,965 keys in both parquet outputs, 12 identity rows, 20 vertical
  rows, input/output hash matches, and recomputed diff-summary equality.

## 7. Wrong vs Correct

Wrong:

```python
# Treats the historical Step 04a value as an exact raw median.
exact_depth = file_cell["median_depth_m_positive_down"]
```

Correct:

```python
# Recompute from all QC-passed raw points and retain the historical difference.
exact_depth = raw_points.loc[raw_points["cell_id"] == cell_id, "depth_m"].median()
signed_diff = exact_depth - file_cell["median_depth_m_positive_down"]
```
