# SCS Ship Sounding QC v2 Pre-Correction Audit

## 1. Scope / Trigger

Use `ncei/code/audit_scs_ship_qc_v2_preflight.py` after the frozen SCS
lineage and product-consistency audits when collaborators need localized
evidence before defining a new sounding QC or aggregation policy.

This stage is diagnostic only. It may use product differences to freeze a
candidate/reference set, but raw mechanism states must use lineage, raw-row
context, contributor structure, and source metadata only. It must not alter
depths, QC flags, data-use fields, or downstream artifacts.

## 2. Signatures

Run from the repository root:

```bash
python ncei/code/audit_scs_ship_qc_v2_preflight.py \
  --config ncei/configs/scs_ship_qc_v2_preflight.yaml \
  --estimate-only

python ncei/code/audit_scs_ship_qc_v2_preflight.py \
  --config ncei/configs/scs_ship_qc_v2_preflight.yaml \
  --run-id <YYYYMMDDTHHMMSSZ> \
  --confirm-audit

python ncei/code/verify_scs_ship_qc_v2_preflight.py \
  --run-dir ncei/derived/scs_ship_qc_v2_preflight/<RUN_ID>
```

`--estimate-only` and full mode are mutually exclusive. Full mode requires
both the UTC run ID and `--confirm-audit`. Existing run IDs are immutable.

## 3. Contracts

### Frozen inputs

The YAML records path plus SHA256 for:

- `product_consistency_by_cell.parquet`
- `cell_lineage.parquet`
- `raw_to_cell_replay.parquet`
- `source_identity_ledger.csv`
- `vertical_datum_ledger.csv`

The producer reads only the product columns required to define the diagnostic
set. Prediction, model-error, or downstream residual-dataset inputs are
forbidden.

### Diagnostic membership

The current candidate predicate is:

```text
abs(gebco_2024_minus_ship_m) > 1000 m
```

It reproduces 905 cells and is not a QC threshold. A reference-version
conflict additionally has:

```text
abs(family_consensus_minus_ship_m) <= 100 m
```

Components use same-provider, same-sign, 8-neighbour integer cell adjacency.
Controls are disjoint and deterministic. They always match provider and raw
file; matching tries depth+point-count, depth, point-count, then same-file
only. The persisted `control_match_level` makes every fallback explicit.

### Raw context

Lineage ranges are zero-based inclusive. Raw files are SHA-verified before
their rows are interpreted. A file may be streamed into one shared cache, but
each cell summary must reselect only that cell's fixed record window:

```python
own_window = context_indices(cell_target_indices, record_window)
cell_rows = {i: file_cache[i] for i in own_window if i in file_cache}
```

JAMSTEC three-column context is `raw_record_order_only`; MRAR context is
`source_grid_order_only`. Neither supports line, ping, beam, swath, or
crossover claims.

`context_status=known` means the target window was successfully parsed. Zero
nearby rows is a known observation, not `officially_unknown`. Interpretation
uses `raw_context_sufficient=false` when fewer than the configured minimum
nearby records exist.

The raw discontinuity signal uses only raw context:

```text
nearby count >= 3
and abs(target median - context median) > 1000 m
and abs(target median - context median) > 10 * max(context NMAD, 1 m)
```

It is a diagnostic signal, never an invalid/delete flag. Candidate states are
closed to:

```text
raw_record_discontinuity_candidate
source_grid_discontinuity_candidate
aggregation_conflict
reference_version_conflict
terrain_or_source_ambiguous
insufficient_raw_context
```

### Aggregation and metadata

All multi-file cells persist unweighted contributor median, point-count
weighted mean/median, dominant-contributor median, range, and NMAD. These are
alternatives, not replacement depths. Output guards therefore allow
`point_count_weighted_*` evidence columns while forbidding
`validation_weight` and `sample_weight` decisions.

Crossover feasibility is `not_feasible_from_current_inputs` unless row-level
time/line identity, comparable observations, a common vertical reference, and
reconstructable overlap are all established. An official cruise time range is
not a row timestamp.

### Outputs

Each immutable run contains:

```text
candidate_cells.parquet
candidate_components.parquet
raw_context_features.parquet
control_cells.parquet
aggregation_conflicts.parquet
reference_conflicts.parquet
metadata_feasibility.csv
preflight_summary.json
collaborator_decision_pack.md
audit_report.md
audit_manifest.json
verification.json
```

`audit_manifest.json` inventories all producer outputs by SHA256. The
manifest also freezes producer/verifier SHA256 and Python/numpy/pandas
versions. The independent verifier writes `verification.json` only after all
checks pass.
The `derived/` tree remains locally persisted and gitignored by repository
policy; code, config, tests, task artifacts, and this contract are committed.

## 4. Validation & Error Matrix

| Condition | Required behavior |
|---|---|
| Frozen input SHA differs | Abort before creating a run directory |
| Candidate/source/count closure differs | Abort before raw streaming |
| Referenced raw SHA or target row differs | Abort and remove only the temporary run |
| Same-file controls are insufficient | Abort; do not sample another source/file |
| Product-derived value enters raw signal arithmetic | Verification failure |
| Shared file cache leaks another cell's window | Unit-test and verification failure |
| Required output has a correction/removal/data-use column | Abort publication |
| Run ID already exists | Refuse to overwrite |
| Verifier finds hash/arithmetic/state drift | Do not cite the run |

## 5. Good / Base / Bad Cases

- Good: a candidate has at least three nearby raw-context rows and a large
  target/context discontinuity; persist the matching candidate state while
  stating that it does not prove invalidity.
- Base: a fixed window parses but has fewer than three nearby rows; write
  `context_status=known`, `raw_context_sufficient=false`, and
  `insufficient_raw_context`.
- Base: same depth+count control stratum is short; fall back within the same
  raw file and persist the actual match level.
- Bad: call an MRAR adjacent source-grid row an adjacent ping or track.
- Bad: infer row time from an official cruise period.
- Bad: replace a cell with GEBCO or choose a weighted aggregation estimator in
  this audit.

## 6. Tests Required

Run:

```bash
python -m unittest _common.tests.test_scs_ship_qc_v2_preflight
python -m py_compile \
  ncei/code/audit_scs_ship_qc_v2_preflight.py \
  ncei/code/verify_scs_ship_qc_v2_preflight.py
```

Tests assert inclusive ranges, per-cell cache isolation, component closure,
control determinism/fallback, raw-context status and signal arithmetic,
aggregation alternatives, closed states, and forbidden schemas. Cite a full
run only when the independent verifier reports `status=pass`.

## 7. Wrong vs Correct

Wrong:

```python
# Includes cached windows requested for every other cell in this raw file.
cell_rows = retained[raw_file]
```

Correct:

```python
own_window = context_indices(target_indices, record_window)
cell_rows = {i: retained[raw_file][i] for i in own_window if i in retained[raw_file]}
```

Wrong:

```python
if nearby_count == 0:
    context_status = "officially_unknown"
```

Correct:

```python
context_status = "known"       # the requested window was parsed
raw_context_sufficient = False  # but it cannot support a local comparison
```
