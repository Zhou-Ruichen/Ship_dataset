# Experiment: SWOT T1 Residual Baselines

> **Period**: 2026-04-30 → 2026-05-03
> **Region**: SWOT T1 footprint — `lon ∈ [105°E, 120°E]`, `lat ∈ [-45°S, -35°S]`
> **Pipeline stages**: Step 09 (batch validate) → Step 10 (residual dataset) → Step 11 (baseline training)

This is the project's first end-to-end ML experiment: can we train a
residual-correction model that improves SWOT T1 bathymetry predictions
using ship-supervised cells as ground truth?

---

## What was tried

| Component | Choice |
|---|---|
| Validation cells | 8,121 cells inside the T1 footprint, all three quality tiers |
| Target | `target_residual_SWOT_T1 = ship_elev - SWOT_T1_elev` |
| Spatial split | 0.25° blocks, stratified by tier and depth, seed 42 (`block025_stratified_seed42`); 60/20/20 → 4,873 train / 1,624 val / 1,624 test |
| Feature sets | (a) `swot_only_inference` — only SWOT prediction + derivatives; (b) `global_product_fusion_diagnostic` — multiple gridded products; (c) `oracle_ship_quality_diagnostic` — uses the ship-cell QC info itself (upper-bound diagnostic, not deployable) |
| Models | no-correction, global-bias, depth-bin-bias, LinearRegression, Ridge, RandomForest, XGBoost, LightGBM |

---

## Results (test RMSE, meters)

| Approach | Test RMSE | vs no-correction |
|---|---:|---:|
| No correction (raw SWOT_T1) | **160.37** | — |
| Depth-bin bias | 157.17 | −2.0% |
| Global bias | ~158 | ~−1% |
| **SWOT-only XGBoost / LightGBM** | **141.18** | **−12.0%** |
| Global product fusion (Linear, diagnostic) | **29.87** | −81% (upper bound; uses other products' depths as features, not deployable for SWOT-only inference) |

Full numbers in
`NCEI_multibeam/derived/ship_supervised_residual_T1/baselines_block025/residual_baseline_report.md`.

---

## What we learned

1. **The residual is mostly spatial, not depth-dependent.** Depth-binning
   alone barely helps (−2%). The ~12% improvement from XGBoost/LightGBM
   comes from learning a smooth spatial correction surface, not from
   exploiting the depth axis.
2. **The 0.25° block split matters a lot.** Earlier random-split
   experiments showed Test RMSE of ~50 m. That number was leakage from
   spatial autocorrelation, not real generalization. The honest 141 m is
   what the model would deliver on a held-out ocean basin. Always block-split.
3. **Diagnostic upper bound (~30 m) is not directly deployable.** It uses
   GEBCO/ETOPO/SRTM as features at inference time; if those were already
   that good in the T1 footprint, you wouldn't need SWOT. But the gap
   tells us the residual contains a lot of recoverable structure if we
   can supply the right features — motivates trying patch-based or
   sparse-input models that consume more spatial context than a
   per-cell feature vector.
4. **A/B/C tier weighting changes leaderboard ordering.** Unweighted RMSE
   over-counts C-tier cells where the ground-truth ship value itself is
   noisier; weighted metrics flatten the ranking among the top 3 models.

---

## Failed / abandoned threads

- **Random row-level split** — abandoned after the 50 m vs 141 m gap was
  isolated. The naïve number was reported in early drafts and had to be
  retracted; do not redo this experiment without spatial blocks.
- **Per-cruise leave-one-out CV** — explored briefly; rejected because
  T1 footprint cruise count is too small (≤ 12) to give stable folds and
  the cruise/spatial confounding was severe.

---

## What to try next (not yet done)

1. **Sparse-ship input model** — feed the model ship cells from the
   *neighbourhood* of the prediction cell as additional features, instead
   of only the SWOT prediction at the target cell. The diagnostic
   fusion result suggests this should close most of the 141 → 30 m gap.
2. **Patch-based residual model** — predict a residual *patch* around
   each ship cell rather than a per-cell scalar; lets the model use
   spatial context end-to-end.
3. **Repeat in a second SWOT region** — T1 is one footprint. Some of the
   12% improvement may be footprint-specific. Need at least one
   independent region (T2 or similar) to claim the approach generalizes.
4. **Re-run with the post-Step-08 full-globe validation cells** when
   they become available (currently Step 08 has only completed for the
   T1 footprint; full global is the queued ~3.5–4h job).

---

## Provenance / reproducibility

- Source scripts: `NCEI_multibeam/code/{09,10,10b,11}_*.py`
- Inputs:
  - `derived/validation_cells_1min/primary_ship_validation_cells_1min.parquet`
  - `derived/swot_t1_batch_validation/` (Step 09 batch outputs)
- Outputs:
  - `derived/ship_supervised_residual_T1/`
  - `derived/ship_supervised_residual_T1/baselines_block025/`
- Companion reports:
  - `derived/ship_supervised_residual_T1/ship_residual_dataset_report.md`
  - `derived/ship_supervised_residual_T1/baselines_block025/residual_baseline_report.md`

If anything in this note conflicts with the two report MDs above, the
reports win (they are auto-generated; this note is a human-curated
narrative).

---

## Why this lives here, not in `.trellis/`

`.trellis/spec/` records *constraints* (what must be true going forward).
This is a *narrative* about a finished experiment — the kind of thing
spec/ doesn't have a slot for. Future experiments should add new files in
this directory with the same `YYYY-MM_<slug>.md` naming.
