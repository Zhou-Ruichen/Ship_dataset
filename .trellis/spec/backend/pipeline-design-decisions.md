# Pipeline Design Decisions

> Why the bathymetry pipeline is shaped the way it is. These are the
> load-bearing decisions — change them only with explicit discussion,
> because every downstream stage assumes them.

Source of truth for the *what* (step-by-step description) is
`docs/多波束船测数据处理流程.md`. This file documents the *why* so future
edits don't accidentally undo a deliberate choice.

---

## 1. Parquet for everything intermediate

**Choice**: Parquet, one file per source `.dat`, sharded by `file_id`.

**Why**:
- Columnar reads — downstream stages typically need 2-3 columns out of 11.
- Per-file shards make resumability trivial (skip if exists).
- 5,083 files × ~17 MB = manageable; merging a single 86 GB monolith would
  not be.
- pandas + pyarrow round-trip is lossless for our schema.

**Don't**: switch to a single concatenated parquet, even "for convenience".
The shard-per-file invariant is what makes Step 02–03 resumable across
days of intermittent runs.

---

## 2. QC marks, never deletes

**Choice**: Step 03 adds `qc_*` boolean columns alongside every row;
nothing is dropped.

**Why**:
- Lets us tune QC thresholds in later stages without re-running Step 02
  (86 GB rewrite).
- Makes the QC criteria themselves auditable — you can re-aggregate with
  `qc_pass_basic & ~qc_zero_depth` and see what changed.
- A row deleted at Step 03 is invisible to Step 06's bias investigation,
  which often needs the suspicious points to *understand* the failure.

**Don't**: introduce a `points_clean/` stage that drops bad rows. Always
filter in the consumer.

---

## 3. File-balanced median for cell aggregation

**Choice**: Step 04b computes `cell_depth = median over files of (file's median depth in cell)`,
not `cell_depth = median over all points in cell`.

**Why**:
- Different surveys have wildly different point density. A modern
  multibeam pass may drop 100,000 points in a 1' cell; an older single-line
  pass drops 10. A point-weighted median lets the dense survey unilaterally
  set the answer.
- File-balanced gives every survey one vote per cell. When two surveys
  disagree we want to *see* the disagreement (Step 05), not paper over it.

**Don't**: substitute mean-of-points or volume-weighted median without
re-running Step 05 and Step 08 — the bias signatures change materially.

---

## 4. Cell size = 1 arc-minute

**Choice**: 1' grid (≈ 1.85 km at the equator). All cells share global
indexing:
```
lon_bin = floor((lon + 180) / cell_deg)
lat_bin = floor((lat + 90)  / cell_deg)
cell_id = f"1min_{lat_bin}_{lon_bin}"
```

**Why**:
- Matches the resolution of the validation targets (GEBCO_2024 15", ETOPO 1').
- Coarser than typical multibeam ping spacing → most files contribute many
  points per cell, so per-file medians are statistically meaningful.
- Yields ~2.4M occupied cells globally — manageable in a single parquet.

**Don't**: change `cell_deg` casually. Cell IDs are not portable across
resolutions, and quality-tier thresholds (n_points ≥ 100, etc.) are
calibrated to this size.

---

## 5. Two-tier quality system: file-level, then cell-level

**Choice**:
- Step 06b assigns each *file* a flag (`keep` / `high_variance_review` /
  `review` / `exclude`).
- Step 07 then assigns each *cell* a tier (A / B / C) based on coverage
  and dispersion.

**Why**: A cruise can be globally suspect (KY12-01 → exclude all 20 files)
*and* an individual cell can be marginal regardless of source. The two
problems are independent and need separate gates. Folding them into one
score would lose the ability to say "this cell is fine, the cruise is
dubious" or vice versa.

See: [`quality-tiering.md`](./quality-tiering.md) for the exact thresholds.

---

## 6. Validation-cells parquet is the single export

**Choice**: Step 07 produces *one* parquet (`primary_ship_validation_cells_1min.parquet`,
2.39M rows) that every downstream consumer reads.

**Why**:
- Step 08 (gridded products), Step 10 (residual dataset), and any future
  external consumer share one canonical "ground truth" surface.
- Updating QC thresholds re-runs Step 06–07 only; no consumer code changes.
- The sensitivity-analysis variant (`sensitivity_original_ship_cells_1min.parquet`)
  exists so we can quantify the cost of QC filtering, not as a parallel
  production export.

---

## 7. Run-label gating (`sample` / `test100` / `full`)

**Choice**: Every long-running stage refuses to run in `full` mode without
`--confirm-full`, and writes sample/test100 outputs to suffixed directories.

**Why**: A full Step 02 / 03 / 04a run takes hours and produces 86 GB of
parquet that overwrites the previous run. Without the two-flag gate, an
accidental `--run-label full` from shell history is catastrophic. The
`_sample` / `_test100` suffix means iteration on a small subset can never
clobber production.

This is the single most important operational invariant in the codebase.
Do not loosen it.

---

## 8. Residual = `ship_elev - model_elev`

**Choice**: For Step 10–11, the supervised target is
`target_residual = ship_elev - model_elev`,
equivalently `model_depth - ship_depth`.

**Why**:
- Sign convention: positive residual ⇔ model says deeper than reality
  (model elevation more negative). Matches the literature convention for
  bathymetry bias (model bias = predicted − truth).
- Working in `elev` (negative downward) means the same sign convention as
  GEBCO/ETOPO/SWOT NetCDFs, so no axis-flipping bug at ingest time.

**Don't**: redefine target as `depth_ship - depth_model` (signs invert)
without retraining every baseline; the sign convention is hardcoded into
the report tables and the `target_residual_SWOT_T1` column name.

---

## 9. Spatial blocks for train/val/test (0.25°)

**Choice**: Splits in Step 10b are computed by 0.25° blocks (113 blocks
across the T1 footprint), with stratified sampling, not random row split.

**Why**: Adjacent cells are spatially correlated; a random 80/20 split
leaks information across the boundary and overstates model accuracy. The
0.25° block is large enough to be effectively independent at our cell
size and small enough that 113 blocks gives a reasonable train/val/test
distribution.

**Don't**: revert to random split. The naïve random-split RMSE is
deceptively low (~50 m vs the honest ~141 m) and that gap is reported
in the Step 11 baseline report as the cautionary example.

---

## 10. R2 sb/mb classifier (NCEI tracklines)

**Choice**: Mixed singlebeam + multibeam bundles (`ncei/tracklines_xyz/`
in particular) are split at pipeline runtime by the R2 classifier — not
at filesystem ingestion. The classifier lives in `_common/r2_classifier.py`
and is invoked post-standardize for `.nc` inputs, post-minimal-parse for
`.xyz` inputs. Files are then routed to `ncei/derived/singlebeam/` or
`ncei/derived/multibeam/`.

The rule (R2 = threshold + spatial-spread):

| Point count | Decision |
|---|---|
| `> 1,000,000` | mb (hard rule) |
| `100,000 – 1,000,000` | mb if `bbox < 5,000 km²` OR `density > 50 pts/km²`; else sb |
| `< 100,000` | sb (hard rule) |

**Canonical values**: the four thresholds above are duplicated here for
readability; source of truth is `_common/r2_classifier.py` module-level
constants (`R2_HARD_MB_POINTS`, `R2_HARD_SB_POINTS`, `R2_BBOX_KM2_CUTOFF`,
`R2_DENSITY_PPKM2_CUTOFF`). Tune there, not here.

bbox formula: `(lon_max − lon_min) × (lat_max − lat_min) × cos(lat_mid)`
in deg², converted to km² via `(111.32)² ≈ 12,392.34 km²/deg²`.
density: `points / bbox_km²`.

**Why**:
- Singlebeam tracks have a stable ~14,000 pts/track baseline (measured
  post-PR-C across the full nc + xyz corpora). The 12 confirmed-mb files
  in `tracklines_xyz/` all exceed 2.1M points — well clear of the hard
  cutoff.
- The 100k–1M borderline band is genuinely ambiguous by point count
  alone (long singlebeam transect vs short multibeam swath have similar
  totals). Bbox + density disambiguates: multibeam swaths concentrate
  points into compact polygons; singlebeam tracks spread them over long
  cruise distances.
- Calibration scatter (committed at `_common/calibration/r2_borderline.png`)
  shows clean separation: 5 mb / 123 sb in the borderline band under
  starter thresholds. All 12 confirmed-mb hard-cutoff files classify
  correctly. The 5 borderline-mb hits include `ra028-09.xyz` from the
  same R/V Atlantis series as the confirmed `ra022-3` / `ra304-15`
  fixtures — the rule generalizes.

**Don't**: filesystem-based pre-sorting (e.g. moving big `.xyz` files
into a `multibeam/` dir before pipeline reads). The bundle stays unified
in `ncei/tracklines_xyz/`; the classifier owns the sb/mb decision and
records the call in the manifest. This way threshold changes re-run the
pipeline cleanly without re-ingesting raw data.

**References**:
- PRD `.trellis/tasks/05-11-singlebeam-integration/prd.md` Q2 (rule
  derivation) + Locked decisions #4 (pipeline-stage split) + #11
  (李杨 finding does not change algorithm).
- Calibration artifacts: `_common/calibration/r2_borderline.{csv,png}`,
  `_common/calibration/r2_hard_mb_files.csv`, and
  `_common/calibration/r2_calibration_summary.txt`.

---

## 11. Python execution convention — run from repo root

**Choice**: All Python scripts in this repo (pipeline steps under
`jamstec/multibeam/code/`, future `ncei/code/`, calibration drivers and
tests under `_common/`) are invoked from the **repo root**
(`/mnt/data2/00-Data/ship/`). Cwd is on `sys.path`, so
`from _common.r2_classifier import classify` works from any consumer
without sys.path hacks or `PYTHONPATH`.

**Why**: PR-D introduced `_common/` as the shared lib for the R2
classifier (decision #10 above) and the PR-E migration of Step 03–11
algorithmic primitives. The classifier had to be importable from both
`jamstec/multibeam/code/` and the future `ncei/code/` without
duplicating code. Three options were on the table:

1. `sys.path.insert(0, REPO_ROOT)` at the top of every consumer script.
2. `pyproject.toml` + `pip install -e .` to make `_common` a real
   installable package.
3. **Run from repo root** so cwd is on `sys.path` automatically.

(3) won because it costs zero infrastructure and matches the existing
single-user workflow. (2) was deferred — no immediate need; can be
adopted later without breaking (3). (1) was rejected because it
spreads boilerplate across every consumer and pins the import strategy
to a specific directory depth.

Single source of truth for the rationale + invocation pattern lives in
[`AGENTS.md`](../../../AGENTS.md#python-execution-convention-run-from-repo-root).
This spec entry exists so the convention is also discoverable from the
backend spec tree.

**Don't**: introduce `sys.path.insert(...)` boilerplate in pipeline
scripts. If a script needs to import from `_common/` and the import
fails, the fix is to run from repo root, not to mutate `sys.path`.

---

## 12. Universal depth clip at ±11,500 m

**Choice**: Across all NCEI bathymetry inputs (nc + xyz + M.rar),
depths with absolute magnitude > 11,500 m are treated as sentinel /
unit-error pollution and removed from `depth_m_positive_down`:

- `02_standardize_singlebeam.py` (nc) and `03_standardize_xyz.py`
  (xyz) apply the **upper-bound** clip:
  `depth_m_positive_down > 11,500 m → NaN`.
- `04_clean_mrar.py` (M.rar) applies the **lower-bound** clip on the
  negative-down raw input: `depth_raw < -11,500 m` rows are dropped
  entirely (nodata).

In both cases, the per-row `depth_raw` column is preserved verbatim
in the per-track / per-quadrant output so the original sentinel
value remains auditable; only the standardized `depth_m_positive_down`
column reflects the clip. Per-track / per-quadrant clip counts land
in the aggregate manifests as `n_clipped` (nc / xyz) or in
`cleaning_audit.parquet` as `rows_nodata` (M.rar).

**Why**:
- Mariana Trench ≈ 10,994 m; anything past 11,500 m (~5% headroom
  past Challenger Deep) is not a real bathymetric observation. The
  evidence: 16 distinct tracks across nc + xyz carry values from
  12,386 m to 87,178 m, with the 87,000 / 75,000 / 52,000 / 44,000 m
  values obvious unit / sentinel errors regardless of threshold
  choice. M.rar carries `-30,990 m` sentinels in the third
  quadrant — clearly nodata.
- A symmetric threshold (`|depth| > 11,500 m → invalid`) keeps the
  rule trivially memorable and operationally identical across the
  three depth-sign conventions (nc/xyz positive-down vs M.rar
  negative-down).
- Clipping in the standardize / cleaning step (not in downstream QC)
  means consumers of the standardized parquet schema never see the
  pollution. The schema-level invariant
  `depth_m_positive_down ∈ [0, 11500] ∪ {NaN}` is contract-grade.

**Don't**: bake additional clips at downstream stages (Step 03+ QC
will still flag other anomalies — extreme positive values not caught
by the sign-sensitive normalize, missing-coord rows, etc. — but the
±11,500 m clip is settled here, not redebated downstream). And don't
loosen the threshold to 12,000 m without re-walking the borderline
`rr11xx` cluster (which sits 11,700–11,966 m) — those tracks were
deliberately included in the clipped set after eyeballing the
distribution.

**Source of truth for the threshold value**:
- `DEPTH_CLIP_UPPER_M = 11500.0` — module-level constant defined
  identically in `ncei/code/02_standardize_singlebeam.py` and
  `ncei/code/03_standardize_xyz.py`. Changing it here without
  updating both scripts (and `04_clean_mrar.py`'s
  `DEPTH_CLIP_LOWER_M = -11500.0`) silently breaks the symmetric-
  threshold invariant.
- `DEPTH_CLIP_LOWER_M = -11500.0` and `LAND_DEPTH_CUTOFF_M = 0.0` —
  module-level constants in `ncei/code/04_clean_mrar.py`.

**References**:
- PRD `.trellis/tasks/05-11-singlebeam-integration/prd.md` Q3
  (M.rar lower bound) + "Finding 2026-05-19b: depth sentinel
  pollution" (per-track table for the 16 nc+xyz cases).
- M.rar cleaning audit lives at
  `ncei/archive/zhoushuai_processed_M/cleaning_audit.parquet`.
- nc / xyz per-track clip counts in `n_clipped` column of
  `ncei/manifests/singlebeam_points_raw_manifest.parquet` and
  `ncei/manifests/xyz_points_raw_manifest.parquet`.

---

## 13. NCEI Step 04A — per-file 1-arcmin cell aggregation

Locks in the production conventions for `ncei/code/07_aggregate_file_cells_1min.py`
so Step 04B / 06b / future re-runs all stay coherent.

### 13.1 AGGREGATION_VERSION

`AGGREGATION_VERSION = "ncei_cells_v0.1.0"` — module constant in
`ncei/code/07_aggregate_file_cells_1min.py`, written into every row of
`ncei/manifests/file_cells_1min_manifest.parquet`. Bump on any schema
or semantics change.

### 13.2 cell_id convention (cross-pipeline, exact)

The 1-arcmin cell-id formula is fixed and shared across pipelines (see
also §4):

```
cell_deg   = 1.0 / 60.0
lon_bin    = floor((lon + 180.0) / cell_deg)      # int64, ∈ [0, 21600]
lat_bin    = floor((lat +  90.0) / cell_deg)      # int64, ∈ [0, 10800]
lon_center = -180.0 + (lon_bin + 0.5) * cell_deg
lat_center =  -90.0 + (lat_bin + 0.5) * cell_deg
cell_id    = f"1min_{lat_bin}_{lon_bin}"          # string, join key
```

Already enforced by `jamstec/multibeam/code/04a_make_multibeam_file_cells.py`
and `ncei/code/07_aggregate_file_cells_1min.py`. **All future 1-arcmin cell
consumers MUST use this exact string format** — Step 04B and the Step 06b
validation joins key on `cell_id`.

### 13.3 Duplicate convention — exact float (production)

Production duplicate detection uses **exact-float equality** on
`(lon, lat, depth_m_positive_down)`:

```python
triples = pd.DataFrame({"lon": lon, "lat": lat, "depth": depth})
dup_mask = triples.duplicated(keep="first")
n_unique_triples = (~dup_mask).sum()
```

Implemented in `ncei/code/06_supplementary_quality_check.py` (Step 03B
Check B) and reused per-cell-scoped in `ncei/code/07_aggregate_file_cells_1min.py`
(the per-cell `cell_key` column scopes dedup within a cell).

**REJECTED for production**: the Step 04A0 audit
(`ncei/docs/step04_aggregation_design_audit.md` §2) used a coarser
`(round(lon, 4), round(lat, 4), round(depth, 1))` triple. That was an
audit-time approximation and produced misleading dup-ratio predictions
(audit said mb branch dup ≈ 0.695; actual exact-float is 0.123). Audit-
rounded triples MUST NOT enter production code or downstream weighting.

### 13.4 duplicate_ratio definition

```
duplicate_ratio = 1.0 - n_unique_triples / n_points_pass
```

Undefined when `n_points_pass == 0`; rows with zero pass-points are
excluded from cell output before this column is computed.

### 13.5 Step 04A vs Step 04B scope

- **Step 04A** (`07_aggregate_file_cells_1min.py`): per-track / per-file
  1-arcmin cells, one parquet per input file under
  `ncei/derived/{singlebeam,multibeam,regional_mrar}/file_cells_1min/`.
  **No** cross-track merge inside a branch. **No** cross-branch merge.
- **Step 04B** (not yet implemented): source-specific global merge within
  ONE branch (all singlebeam tracks → one singlebeam cells parquet, etc.).
  Still **no** cross-branch merge.
- **A/B/C quality tiers**: deferred. Calibrated against real per-cell
  distributions after Step 04B lands; bringing them forward to Step 04A
  is out of scope.
- **Cross-source validation cells** (sb + mb + JAMSTEC + M.rar combined):
  deferred. Single-source merges (Step 04B) must precede any combined
  product.

### 13.6 Branch semantics — three disjoint branches

| branch | source | populated by | row count |
|---|---|---|---:|
| `singlebeam` | NCEI nc + xyz (singlebeam only) | nc-primary for intersect tracks; xyz-only otherwise | 5,365 |
| `multibeam_ncei` | NCEI xyz (multibeam only) | 11 AUV Sentry + 6 misc | 17 |
| `regional_mrar` | 周帅-provided M.rar processed multibeam | 3 quadrant partitions | 3 |

M.rar's `regional_mrar` branch stays **distinct from** `multibeam_ncei`
even though both are multibeam-class. They come from different processing
pipelines, different sign conventions (pre-PR-F: nc/xyz positive-down,
M.rar raw negative-down), and different provenance opacity.

**Don't** collapse `regional_mrar` into `multibeam_ncei` for Step 04B
merging — keep three branch-specific outputs. Cross-source combining
(if it happens at all) is a later step with explicit conflict rules.

### 13.7 Branch derivation rule

The supplementary manifest
(`ncei/manifests/bathymetry_entry_manifest_supplementary.parquet`) has no
`branch` column; derive it deterministically from `source_priority` +
`instrument_class_pred`:

```python
if source_priority == "regional":           branch = "regional_mrar"
elif source_priority == "primary":
    if instrument_class_pred == "multibeam":  branch = "multibeam_ncei"
    elif instrument_class_pred == "singlebeam": branch = "singlebeam"
# source_priority ∈ {"supplementary", "skip"} → excluded from Step 04A workload
```

Assert per-branch row counts at runtime (5,365 / 17 / 3) and fail loudly
on mismatch — silent drift here would scramble downstream weighting.

### 13.8 manual_review_flag composition

The Step 04A `manual_review_flag` column is the union of three sources
(informational only — does NOT gate inclusion):

1. `depth_anomaly_flag = True` from the Step 03B supplementary manifest
   (primary tracks only, ≤10 such rows in current run).
2. 96 bbox-only divergent intersect track_ids from
   `ncei/manifests/intersect_divergence_audit.parquet`, filtered by
   `bbox_overlap_jaccard < 0.5 AND valid_count_ratio ∈ [0.5, 2.0] AND
   depth_med_ratio ∈ [0.5, 2.0]`.
3. Explicit override: `{"f-10-89-cp"}` (already covered by #2 in the
   current run; kept defensive for future threshold tightening).

Total in current full run: 106 (10 + 96 + 0 extra). Downstream consumers
choose whether to drop, downweight, or quarantine these tracks; Step 04A
emits the flag and lets later stages decide.

### 13.9 References

- Implementation: `ncei/code/07_aggregate_file_cells_1min.py`
  (`AGGREGATION_VERSION = "ncei_cells_v0.1.0"`).
- Run report: `ncei/docs/step04a_file_cells_1min_report.md`.
- Design audit (history, supersedes audit-rounded dup convention):
  `ncei/docs/step04_aggregation_design_audit.md`.
- Cell-id contract (cross-pipeline): see also §4 and
  `.trellis/spec/backend/data-contracts.md` §file-cell schema.

---

## 14. NCEI Step 04B — source-specific global 1-arcmin cell merge

Locks in the production conventions for
`ncei/code/08_merge_branch_cells_1min.py` so future merges across the
three NCEI branches stay reproducible and consumer-readable.

### 14.1 MERGE_VERSION

`MERGE_VERSION = "ncei_cells_merge_v0.1.0"` — module constant in
`ncei/code/08_merge_branch_cells_1min.py`, written into every row of
`ncei/manifests/cells_1min_manifest.parquet`. Bump on any schema or
semantics change.

### 14.2 Final representative depth — median of medians (contractual)

For each (branch, cell_id):

```
median_depth_m = median([row.median_depth_m for row in per_file_cells_in_cell])
```

The final cell depth is the **median of per-file-cell medians**, NOT a
median over pooled pass-points and NOT weighted by `n_points_pass`. This
is the contract — downstream weighting / calibration adjusts via the
sidecar fields (n_unique_triples_total, manual_review_*), never by
recomputing depth from pooled points.

### 14.3 Per-cell sidecar fields

- `n_track_cells` = number of contributing per-file-cell rows.
- `n_tracks` = number of distinct `track_id` contributing.
- `n_points_pass_total` = sum of per-file-cell `n_points_pass`.
- `n_unique_triples_total` = sum of per-file-cell `n_unique_triples`.
  **Note**: this is a sum across files, NOT a re-dedup across files —
  the per-file exact-float dedup (§13.3) remains the authoritative
  dedup boundary. Inter-file duplicates within a cell are documented
  in the run report; addressing them is deferred to a later stage if
  needed.
- `duplicate_ratio_cell = 1 - n_unique_triples_total / n_points_pass_total`.
- Spread statistics over per-file-cell medians:
  `mean_of_track_medians`, `std_of_track_medians` (ddof=1; NaN if
  n_track_cells==1), `iqr_of_track_medians` (p75−p25),
  `min_track_median`, `max_track_median`, `range_track_median`.

### 14.4 Provenance count columns

Integer counts of per-file-cell rows by category (allow downstream
filters / inspections without re-reading Step 04A outputs):

- `n_source_ncei_nc`, `n_source_ncei_xyz`, `n_source_mrar_zhoushuai`
- `n_completeness_nc_xyz_intersect`, `n_completeness_xyz_only`,
  `n_completeness_nc_only`
- `n_instrument_singlebeam`, `n_instrument_multibeam`

The `n_source_mrar_zhoushuai` counter must defensively accept the union
`{"mrar_zhoushuai", "mrar_processed", "ncei_mrar"}` since pre-Step-03A
script generations used different literals. Current data emits
`mrar_zhoushuai` (canonical going forward); the multi-literal acceptance
is kept for re-run / archive interop.

### 14.5 manual_review_* aggregation (informational, not exclusion)

- `manual_review_any` = **OR** over contributors' `manual_review_flag`
  (not AND, not majority).
- `manual_review_track_cell_count` = number of contributing rows with
  flag=True.
- `manual_review_unique_triples` = sum of `n_unique_triples` over
  flagged contributors.
- `manual_review_unique_triples_share` =
  `manual_review_unique_triples / n_unique_triples_total` (NaN when
  `n_unique_triples_total == 0`).
- `manual_review_reasons` = semicolon-joined sorted distinct reason
  codes. Step 04A per-file-cell parquets do NOT carry a per-row reason
  column; consumers fall back to the constant `"step03b_flag"` when
  reading the source (Step 04B handles this transparently).

**Do NOT use `manual_review_any` as a hard exclusion.** All flagged
cells are retained in the output; downstream consumers choose whether
to drop, downweight, or quarantine.

### 14.6 Output partitioning — hive-flavored (cross-tool readability)

Per-branch datasets live under
`ncei/derived/{singlebeam,multibeam,regional_mrar}/cells_1min/`,
written via `pyarrow.dataset.write_dataset(..., partitioning=["branch",
"lat_band_10deg"], partitioning_flavor="hive")`. Paths look like:

```
ncei/derived/multibeam/cells_1min/branch=multibeam_ncei/lat_band_10deg=30/part-0.parquet
```

The `partitioning_flavor="hive"` is **required** (default directory
flavor strips the partition keys on standard hive-reader reads, which
silently loses `branch` and `lat_band_10deg`). Sample / test100 modes
write to suffixed roots (`cells_1min_sample/`, `cells_1min_test100/`)
so they never collide with canonical full-run output.

### 14.7 `lat_band_10deg` derivation

```
lat_band_10deg = floor(lat_center / 10) * 10    # int64, ∈ {-90, -80, ..., 80}
```

18 bands. Used only for partitioning; not part of the per-row
user-facing schema directly (but reappears on hive read via the
partition key path).

### 14.8 Step 04A vs Step 04B vs future cross-branch step

Reaffirms §13.5:

- **Step 04A** (`07_*.py`): per-track / per-file cells, one parquet
  per input file. No merge.
- **Step 04B** (`08_*.py`): single-branch merge — sb tracks → sb
  cells, mb tracks → mb cells, M.rar quadrants → mrar cells. No
  cross-branch merge.
- **Cross-source product** (sb + mb + JAMSTEC + M.rar): deferred. Must
  follow a later spec section with explicit conflict / priority rules.

### 14.9 References

- Implementation: `ncei/code/08_merge_branch_cells_1min.py`
  (`MERGE_VERSION = "ncei_cells_merge_v0.1.0"`).
- Run report: `ncei/docs/step04b_cells_1min_merge_report.md`.
- Top-level manifest: `ncei/manifests/cells_1min_manifest.parquet`
  (3 rows, one per branch).
- Predecessor: §13 (Step 04A) — all §13 conventions remain in force.

---

## 15. NCEI Step 05A — source-specific overlap residual analysis

Locks in the production conventions for
`ncei/code/09_source_specific_overlap_residuals.py`. Descriptive
analysis only; **no filtering, no exclusion, no quality tiers**.

### 15.1 OVERLAP_VERSION

`OVERLAP_VERSION = "ncei_overlap_v0.1.0"` — module constant, written
into every output parquet as an `analysis_version` column. Bump on any
schema or semantics change.

### 15.2 Residual formula (contractual)

For each branch and each cell with `n_track_cells >= 2`, and each
contributing per-file-cell row:

```
residual_m     = per_file_cell.median_depth_m - branch_cell.median_depth_m
abs_residual_m = abs(residual_m)
```

The reference depth is the §14.2 median-of-per-file-cell-medians, NOT
a pooled-point median and NOT a re-weighted central tendency. Cells
with `n_track_cells == 1` have residual ≡ 0 by construction and are
EXCLUDED from the per-track-cell residuals output — they carry no
information about cross-track consistency.

### 15.3 Input source compliance (closed boundary)

Step 05A consumes Step 04A + Step 04B outputs ONLY:

- Step 04A per-file-cell parquets under
  `ncei/derived/{singlebeam,multibeam,regional_mrar}/file_cells_1min/`,
  driven by `ncei/manifests/file_cells_1min_manifest.parquet`.
- Step 04B hive-partitioned datasets under
  `ncei/derived/{singlebeam,multibeam,regional_mrar}/cells_1min/`,
  driven by `ncei/manifests/cells_1min_manifest.parquet`.

It MUST NOT read `points_checked/`, `points_raw/`, the PR-F raw M.rar
extract, or any external reference grid (GEBCO / ETOPO / SRTM15 /
SWOT). External-grid validation is the job of a later step (Step 11 /
PR-G).

### 15.4 Branch-disjoint join contract

The (branch, cell_id, lon_bin, lat_bin) join key is fully scoped by
`branch` — left and right sides of every join must agree on `branch`.
Same `cell_id` appearing in two branches refers to two physically
distinct rows from two disjoint data sources; cross-branch residuals
are NOT meaningful at this stage and are explicitly forbidden until a
later cross-source spec section justifies them.

### 15.5 Output artifacts (5 files + report)

All under `ncei/derived/overlap_bias_1min/` (canonical) or suffixed
roots `overlap_bias_1min_sample/` / `overlap_bias_1min_test100/`:

1. `source_specific_overlap_residuals.parquet` — per-row residuals
   (one row per contributing per-file-cell where the branch cell has
   `n_track_cells >= 2`). 21+ columns. Carry both per-file-cell and
   branch-cell sidecar fields for downstream filtering without re-join.
2. `track_bias_summary.parquet` — one row per track with median /
   mean / MAD / IQR / RMSE / p95-abs / max-abs residual,
   duplicate_ratio_summary, manual_review_cell_share.
3. `branch_overlap_summary.parquet` — 3 rows (one per branch) with
   n_branch_cells_total, n_overlap_cells, overlap_share, residual
   percentiles, abs-residual percentiles, branch RMSE.
4. `branch_overlap_breakdowns.tsv` — residual stats sliced by
   source_type, manual_review_flag, and `duplicate_ratio_cell` bin
   `[0, 0.01) | [0.01, 0.1) | [0.1, 0.5) | [0.5, 1.0]`.
5. `manual_review_overlap_summary.tsv` — 6 rows (3 branches × 2
   flag values).

Plus markdown: `ncei/docs/step05a_source_specific_overlap_bias_report.md`.

Logs: `ncei/output/logs/09_source_specific_overlap_residuals.log`
with run-label suffix.

### 15.6 Descriptive-only mandate

Step 05A produces ZERO filter / exclude / drop / quality-tier columns.
Even tracks with very high `p95_abs_residual_m` are kept verbatim in
all outputs; downstream consumers decide what to drop or downweight.

This is a deliberate decoupling: the analysis stage publishes evidence
(residual distributions, top-N problem tracks, source-type and dup-
ratio breakdowns), the policy stage (later steps) chooses thresholds
based on that evidence.

### 15.7 Step 05A vs Step 05B vs cross-source step

- **Step 05A** (`09_*.py`): single-branch overlap residuals
  (per-branch within-source consistency).
- **Step 05B** (not yet implemented): cross-branch overlap audit
  (e.g. cell appears in both singlebeam and multibeam_ncei → compute
  the cross-source residual on the same cell_id). Branches stay
  disjoint at the residual-row level; the audit is a per-cell join
  across branches, not a merge.
- **Cross-source product** (sb + mb + JAMSTEC + M.rar combined
  authoritative depth): still deferred. Requires explicit priority
  rules and a separate spec section.

### 15.8 Performance notes (informational)

Full sb branch is the runtime bottleneck (~57 min wall on current
hardware for 5,365 file-cell parquets joined against 14.6M branch
cells). The materialized-pd.Index pattern in the implementation cuts
the per-file isin-filter cost by ~6×; do not regress it.

### 15.9 References

- Implementation: `ncei/code/09_source_specific_overlap_residuals.py`
  (`OVERLAP_VERSION = "ncei_overlap_v0.1.0"`).
- Run report: `ncei/docs/step05a_source_specific_overlap_bias_report.md`.
- Predecessors: §13 (Step 04A) + §14 (Step 04B) — all conventions
  remain in force.

---

## 16. NCEI Step 05B — cross-branch overlap audit

Locks in conventions for
`ncei/code/10_cross_branch_overlap_audit.py`. Like Step 05A, this stage
is **descriptive only** — it joins Step 04B branch cells across branches,
emits residuals + sidecar fields, and lets policy steps decide what to
do with them.

### 16.1 CROSS_OVERLAP_VERSION

`CROSS_OVERLAP_VERSION = "ncei_cross_overlap_v0.1.0"` — module constant,
written into every output parquet row as a `cross_analysis_version`
column. Bump on any schema or semantics change.

### 16.2 Pair ordering (canonical, fixed)

The 3 unordered branch pairs are normalized to alphabetical
`left < right` order, with stable labels:

| pair_label | left_branch | right_branch |
|---|---|---|
| `mb_vs_mrar` | multibeam_ncei | regional_mrar |
| `mb_vs_sb` | multibeam_ncei | singlebeam |
| `mrar_vs_sb` | regional_mrar | singlebeam |

`residual_m = left.median_depth_m - right.median_depth_m`. Sign matters
and is fixed by this table — do NOT flip residual direction in
downstream consumers.

### 16.3 Geometry consistency (hard contract)

Step 04B cell_id is a deterministic function of `lon_bin`/`lat_bin`
(§13.2). Two cells with the same cell_id from different branches MUST
have identical `lon_bin`, `lat_bin`, `lon_center`, `lat_center`.
Step 05B asserts this and **raises** on any mismatch (silently
warning here would hide a corrupted upstream Step 04B output).
`lat_band_10deg` mismatch is informational only since it's a partition
key derivative, not part of the join key.

### 16.4 Input source compliance (closed boundary)

Step 05B consumes Step 04B hive-partitioned datasets ONLY, driven by
`ncei/manifests/cells_1min_manifest.parquet`. It MUST NOT read:

- Step 04A per-file-cells (use Step 05A for that level of detail).
- `points_checked/`, `points_raw/`, or the PR-F raw M.rar extract.
- `jamstec/` data (cross-source merge is a separate spec section).
- External reference grids (GEBCO / ETOPO / SRTM15 / SWOT).

### 16.5 Audit-only mandate — no cross-branch MERGED depth

Step 05B emits **both** branches' representative depths plus the
residual; it does NOT compute a single "cross-source authoritative"
depth (e.g. arithmetic mean of left/right). Cross-branch fusion is a
later step with explicit priority rules — Step 05B's role is to
quantify the disagreement, not resolve it.

### 16.6 Output artifacts (3 files + report)

All under `ncei/derived/cross_branch_overlap_1min/` (canonical) or
suffixed roots `cross_branch_overlap_1min_sample/` /
`cross_branch_overlap_1min_test100/`:

1. `cross_overlap_cells.parquet` — 25 cols, one row per (pair_label,
   cell_id) where both branches are populated. Carries left+right
   median_depth_m, residual_m, abs_residual_m, plus left/right sidecar
   fields (n_track_cells, n_tracks, n_unique_triples_total,
   duplicate_ratio_cell, manual_review_any, iqr_of_track_medians) and
   `cross_analysis_version`.
2. `cross_overlap_pair_summary.parquet` — 3 rows (one per pair) with
   n_left_cells_total, n_right_cells_total, n_overlap_cells,
   overlap_share_of_left, overlap_share_of_right, residual
   percentiles (p01/p05/p25/p50/p75/p95/p99), abs-residual percentiles
   (p50/p95/p99), `rmse_pair_m`, manual_review-either counts,
   cross_analysis_version, runtime_seconds.
3. `cross_overlap_breakdowns.tsv` — residual stats sliced by
   `manual_review_either`, `dup_ratio_either_bin`
   (`[0, 0.01) | [0.01, 0.1) | [0.1, 0.5) | [0.5, 1.0]`), and
   `lat_band_10deg` (left branch's band).

Plus markdown: `ncei/docs/step05b_cross_branch_overlap_audit_report.md`.

Logs: `ncei/output/logs/10_cross_branch_overlap_audit.log` with
run-label suffix.

### 16.7 Sample / test100 capping behavior

In sample / test100 modes, `--limit-rows-per-pair` caps the per-pair
retained rows after sorting by `cell_id` (defaults: sample=50,000,
test100=200,000). The cap affects only what lands in
`cross_overlap_cells.parquet`; the **pre-cap overlap count** is still
reported in the pair summary and the report §6 cross-check table.
This dual-reporting must remain — consumers reading the per-cell
parquet need to know whether they have the full overlap or a sample.

### 16.8 Step 05A vs 05B vs cross-source product

- **Step 05A** (`09_*.py`): single-branch overlap residuals (within-source
  consistency).
- **Step 05B** (`10_*.py`): cross-branch overlap residuals (this section)
  — same cell, different branches. Audit only, no merge.
- **Cross-source authoritative product** (sb + mb + JAMSTEC + M.rar
  merged depth): still deferred. Step 05B is its evidence base; the
  fusion stage must consume Step 05B output as input.

### 16.9 References

- Implementation: `ncei/code/10_cross_branch_overlap_audit.py`
  (`CROSS_OVERLAP_VERSION = "ncei_cross_overlap_v0.1.0"`).
- Run report: `ncei/docs/step05b_cross_branch_overlap_audit_report.md`.
- Predecessors: §13 (Step 04A) + §14 (Step 04B) + §15 (Step 05A) —
  all conventions remain in force.

---

## 17. NCEI Step 06A — quality policy calibration audit

Locks in conventions for
`ncei/code/11_quality_policy_calibration_audit.py`. **Audit only** —
emits stratified evidence + candidate rules; does NOT enforce
policies, does NOT define final tiers, does NOT exclude cells.

### 17.1 POLICY_CALIBRATION_VERSION

`POLICY_CALIBRATION_VERSION = "ncei_policy_calib_v0.1.0"` — module
constant, written into every output parquet row as
`policy_calibration_version`. Bump on any schema or rule-list change.

### 17.2 Audit-only contract (hard)

Step 06A MUST NOT:

- write a `quality_tier` / `validation_weight` / `exclude_from_primary`
  column to any parquet (a runtime assertion validates this before
  every parquet write — see `validate_no_final_tiers_in_parquets` in
  the implementation).
- drop / filter / "soft-exclude" cells.
- bind any final tier definition outside `quality_policy_candidate_rules.tsv`.

The TSV is the **only** place candidate tier labels are persisted.
Step 06B (future) is responsible for converting candidates → enforced
rules after human review.

### 17.3 Stratification bin definitions (fixed; do not change without bumping version)

```python
LAT_BANDS              = [-90,-80,...,80,90]                      # 18 bands of 10°
DEPTH_BINS             = [0, 200, 500, 2000, 4000, 6000, 11500]   # 6 right-open bins, last closes
DUP_RATIO_BINS         = [0.0, 0.01, 0.1, 0.5, 1.0]               # 4 bins (mirrors §16.6/§14)
N_UNIQUE_TRIPLES_BINS  = [1, 10, 100, 1000, 10000, inf]           # 5 bins
N_TRACK_CELLS_BINS     = [1, 2, 5, 20, inf]                       # 4 bins (1 = single, no overlap)
MANUAL_REVIEW_SHARE_BINS = [0.0, 0.001, 0.01, 0.1, 1.0]           # 4 bins (currently reserved)
```

Use `pd.cut(right=False)` for right-open intervals; the last bin
closes on the right.

### 17.4 Candidate-rules TSV schema (fixed)

`quality_policy_candidate_rules.tsv` columns:

| col | type | notes |
|---|---|---|
| `rule_id` | string | unique, e.g. `mb_v0_high_xvalid_lowdup` |
| `candidate_tier` | enum | {high_confidence, medium_confidence, low_confidence, review_or_sensitivity_only} |
| `applies_to_branch` | string | one of {singlebeam, multibeam_ncei, regional_mrar, "*"} |
| `applies_to_lat_band_filter` | string | e.g. "\*", "-90..0", "-60..-50" |
| `applies_to_depth_bin_filter` | string | e.g. "\*", "0..200", "2000..6000" |
| `condition` | string | plain-English logical expression over Step 04B cell columns |
| `recommended_weight` | float | ∈ [0, 1]; never negative, never >1 |
| `requires_step05_overlap` | bool | rule requires within-branch or cross-branch overlap evidence |
| `exclude_from_primary` | bool | true ⇒ keep out of primary validation (mrar default) |
| `evidence_basis` | string | which Step 05A/05B observations support this rule |
| `notes` | string | free-form caveats, open questions |

Step 06B MUST consume this schema verbatim; do not rename columns.

### 17.5 Locked policy principles (encoded in current 16 rules)

All future rule revisions MUST keep these principles:

1. **multibeam_ncei** is the highest-precision branch; high_confidence
   rules require cross-validation against mrar OR low dup_ratio_cell.
2. **singlebeam** thresholds MUST stratify by `lat_band_10deg` and
   `depth_bin`; Southern Ocean (lat ≤ -50) is review-only.
3. **regional_mrar** defaults to `review_or_sensitivity_only` with
   `exclude_from_primary=True`; only graduates to medium with
   cross-validation against multibeam_ncei in same area.
4. **`manual_review_flag` alone NEVER excludes** — must be paired
   with residual evidence to gate behavior.
5. **`duplicate_ratio_cell > 0.5`** (AUV-Sentry-like) → reduce
   `recommended_weight`, never zero.
6. **`n_unique_triples_total`** is the preferred weighting variable,
   not `n_points_pass_total`.
7. **No overlap evidence** (n_track_cells=1 AND not in cross-branch)
   → `low_confidence` with `low_evidence` note; not automatically bad.

### 17.6 Output artifacts (4 files + report)

Under `ncei/derived/quality_policy_calibration_1min/` (canonical) or
suffixed roots `_sample/` / `_test100/`:

1. `quality_calibration_by_branch.parquet` — 3 rows.
2. `quality_calibration_by_lat_depth.parquet` — per (branch, lat_band,
   depth_bin).
3. `quality_calibration_by_source_pair.parquet` — per (pair, dup_bin,
   n_unique_bin).
4. `quality_policy_candidate_rules.tsv` — candidate rules (current:
   16 rows; schema fixed in §17.4).

Plus markdown: `ncei/docs/step06a_quality_policy_calibration_report.md`.

Logs: `ncei/output/logs/11_quality_policy_calibration_audit.log` with
run-label suffix.

### 17.7 Step 06A vs Step 06B

- **Step 06A** (`11_*.py`): publish stratified evidence + candidate
  rules. THIS section.
- **Step 06B** (not yet implemented): consume `quality_policy_candidate_rules.tsv`
  + (revised) human-approved rules to write enforced quality flags
  onto Step 04B cells. Will introduce the `quality_tier` /
  `validation_weight` / `evidence_class` columns that §17.2 forbids
  here.

### 17.8 References

- Implementation: `ncei/code/11_quality_policy_calibration_audit.py`
  (`POLICY_CALIBRATION_VERSION = "ncei_policy_calib_v0.1.0"`).
- Run report: `ncei/docs/step06a_quality_policy_calibration_report.md`.
- Predecessors: §13 + §14 + §15 + §16 — all conventions remain in
  force.

---

## 18. NCEI Step 06B — enforce quality policy + cell quality manifest

Locks in conventions for `ncei/code/12_apply_quality_policy.py`. This
is the **first stage in this pipeline that emits final per-cell tier
labels and validation weights**. It MUST consume the policy decisions
made in §17 plus the Step 06B semantic lock report; it MUST NOT
revisit or extend policy.

### 18.1 POLICY_ENFORCE_VERSION

`POLICY_ENFORCE_VERSION = "ncei_policy_enforce_v0.1.0"` — module
constant in `ncei/code/12_apply_quality_policy.py`, written as
`rule_version` on every output cell row. Bump on any rule-grammar /
schema / contract change.

### 18.2 Single authoritative rule source

Step 06B MUST read rules **only** from
`.trellis/tasks/05-11-singlebeam-integration/research/quality_policy_enforced_rules.tsv`
(18 cols × 16 rows; locked by `ncei/docs/step06b_semantic_lock_report.md`).
It MUST NOT read the Step 06A candidate TSV.

### 18.3 Rule partitioning and application order

- Rules with `applies_as == "first_match"` (15 rules, priorities 1–15)
  are sorted by `priority` ascending and applied **first-match-wins**
  per cell.
- Rules with `applies_as == "invariant"` (1 rule: `manual_review_not_exclusion`)
  are **NEVER** used for tier assignment. They are evaluated as
  post-tier assertions (§18.6 below).
- Cells unmatched by all 15 first-match rules are assigned the
  documented `default_unmatched` safeguard:
  `matched_rule_id="default_unmatched"`, `matched_rule_priority=99`,
  `quality_tier="low_confidence"`, `validation_weight=0.25`,
  `applied_rule_description="No enforced rule matched; default
  low_confidence safeguard."`

### 18.4 Filter parser semantics (asymmetric closed vs half-open)

The filter grammar (per §17 lock §1.2) uses TWO distinct semantics
depending on the field:

- `applies_to_lat_band_filter`: **closed interval on discrete band
  members**.
  `"-70..-50"` → `lat_band_10deg IN {-70, -60, -50}` (3 bands, both
  endpoints included).
  `"-80..-70,-30..-20"` → `lat_band_10deg IN {-80, -70, -30, -20}`
  (4 bands).
  `"60..90"` → `lat_band_10deg IN {60, 70, 80}` (90 not a valid band
  on Earth's lat_band grid; ranges including 90 clip).
- `applies_to_depth_bin_filter`: **half-open interval on bin-left-
  edges** (the §17.3 DEPTH_BINS are `[0, 200, 500, 2000, 4000, 6000,
  11500]`; the upper edge of the filter range is NOT included as a
  bin).
  `"0..200"` → `depth_bin_lo IN {0}` (only the `[0, 200)` bin).
  `"500..6000"` → `depth_bin_lo IN {500, 2000, 4000}` (3 bins).
  `"2000..6000"` → `depth_bin_lo IN {2000, 4000}` (2 bins).

The asymmetry is intentional: lat bands are discrete labels with both
endpoints meaningful; depth filters describe a contiguous depth range
and the upper edge defines a NEXT bin, not the current bin's content.

The Step 06B implementation MUST parse these two filters with the
right convention. A reference implementation lives in
`ncei/code/12_apply_quality_policy.py::parse_exact_membership_filter`
with an `upper_inclusive` kwarg.

### 18.5 Slice lookup contract

For rules with `slice_lookup_table != "none"`:

- `by_lat_depth`: join cells to
  `ncei/derived/quality_policy_calibration_1min/quality_calibration_by_lat_depth.parquet`
  on `(branch, lat_band_10deg, depth_bin_lo)`. Slice fields
  available include `within_branch_residual_p95`,
  `cross_branch_residual_max_p95`, etc. — see Step 06A schema.
- `by_source_pair`: join cells to
  `quality_calibration_by_source_pair.parquet` on
  `(pair_label, dup_bin_lo, n_unique_lo)`. The `pair_label` is
  determined by the rule's `condition_canonical` (e.g.
  `slice.mb_vs_mrar.*` joins on `pair_label='mb_vs_mrar'`); the cell's
  `(dup_bin_lo, n_unique_lo)` are derived from `duplicate_ratio_cell`
  and `n_unique_triples_total` using the §17.3 bin definitions.

**NaN-as-fail contract**: when a slice lookup returns NaN (the cell
has no matching slice row), the rule's condition MUST evaluate to
`False`. Silent NaN propagation that would silently match a rule is
forbidden.

### 18.6 Mandatory post-check invariants (must all PASS at runtime)

The implementation MUST run and report PASS/FAIL on all 5 of:

1. **No flag-only exclusion**: no first-match rule whose condition
   tests ONLY `manual_review_any` can be the matched_rule_id for any
   cell. (Guaranteed by §18.3 partitioning — verify by inspection.)
2. **No flag-only upgrade**: same as above; the invariant rule's
   tier is NEVER assigned via first-match.
3. **No zero weights**: no cell has `validation_weight == 0`. (The
   default safeguard sets 0.25; the lowest rule weight is 0.1.)
4. **regional_mrar exclude_from_primary share ≥ 0.99**: at least 99%
   of mrar cells have `exclude_from_primary=True` (a small carve-out
   for rule 4 cross-validated cells is allowed).
5. **AUV Sentry sidecars correct**: every cell matching
   `mb_v0_highdup_sentry_downweight` (rule 9) has both
   `auv_sentry_flag=True` AND `source_risk_class='auv_sentry_highdup'`.

Implementation MUST exit non-zero if any assertion fails.

### 18.7 Output schema (31 cols in exact order; do not reorder)

`cell_quality_flags_1min.parquet` columns (full list pinned by the
Step 06B brief; the implementation already emits this exact order):

```
branch, cell_id, lon_bin, lat_bin,
quality_tier, evidence_class, validation_weight, branch_role,
use_for_primary_validation, use_for_supplementary_validation,
use_for_regional_experiment, sensitivity_only_flag,
exclude_from_primary, exclusion_or_review_reason,
matched_rule_id, matched_rule_priority, applied_rule_description,
rule_version,
n_unique_triples_total, n_points_pass_total, duplicate_ratio_cell,
n_track_cells, manual_review_any, manual_review_unique_triples_share,
low_evidence_flag, overlap_evidence_class, n_cross_branch_overlap,
lat_band_10deg, depth_bin,
auv_sentry_flag, source_risk_class
```

### 18.8 branch_role table (fixed)

Each branch maps to one and only one `branch_role`:

| branch | branch_role |
|---|---|
| singlebeam | `supplementary_coverage` |
| multibeam_ncei | `multibeam_supplement` |
| regional_mrar | `regional_experiment` |

AUV Sentry cells do NOT get a new `branch_role`; they keep
`multibeam_supplement` and are surfaced via `auv_sentry_flag` +
`source_risk_class='auv_sentry_highdup'` (per §17 lock §1.4).

### 18.9 Step 04B cell preservation (immutable upstream)

Step 06B MUST be a **sidecar producer** keyed by `(branch, cell_id,
lon_bin, lat_bin)`. It MUST NOT rewrite, overwrite, or otherwise
modify Step 04B `cells_1min/` parquet datasets. Downstream consumers
join on the key.

### 18.10 Output artifacts (6 + report)

Under `ncei/derived/quality_flags_1min/` (canonical) or suffixed
roots:

1. `cell_quality_flags_1min.parquet` — 31 cols, one row per Step 04B
   cell (≈ 23.6M rows full).
2. `cell_quality_flags_1min.tsv` — stratified subset for human
   inspection (full-mode TSV is capped; sample/test100 TSV = full
   sample rows).
3. `quality_summary_by_branch.parquet`.
4. `quality_summary_by_lat_depth.parquet`.
5. `quality_summary_by_rule.parquet`.
6. `quality_summary_by_evidence_class.parquet`.

Plus markdown: `ncei/docs/step06b_cell_quality_flags_report.md`.

Logs: `ncei/output/logs/12_apply_quality_policy.log` with run-label
suffix.

### 18.11 References

- Implementation: `ncei/code/12_apply_quality_policy.py`
  (`POLICY_ENFORCE_VERSION = "ncei_policy_enforce_v0.1.0"`).
- Enforced rules: `.trellis/tasks/05-11-singlebeam-integration/research/quality_policy_enforced_rules.tsv`.
- Preflight + lock: `ncei/docs/step06b_quality_policy_rule_review.md`,
  `ncei/docs/step06b_semantic_lock_report.md`.
- Run report: `ncei/docs/step06b_cell_quality_flags_report.md`.
- Predecessors: §13 + §14 + §15 + §16 + §17 — all conventions remain
  in force.
