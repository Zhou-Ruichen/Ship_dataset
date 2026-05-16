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
