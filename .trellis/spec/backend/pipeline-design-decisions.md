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
