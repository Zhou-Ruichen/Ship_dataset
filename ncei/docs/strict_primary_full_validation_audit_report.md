# Stage 3 Full Strict-Primary Global Validation — Audit Report

Audit date: 2026-05-27
Auditor: automated review (cross-checked against parquet outputs, summary TSVs, and run logs)
Validation run timestamp: 2026-05-26T18:52:45Z (elapsed 2164.1 s)
Validation outputs: `ncei/derived/model_validation_1min_full_strict_primary/`
Source reports:
- `ncei/docs/strict_primary_global_validation_report.md`
- `ncei/docs/strict_primary_global_validation_report_full_strict_primary.md` (identical copy)
Source logs:
- `ncei/output/logs/14_validate_gridded_products_step08_full_strict_primary.log`
- `ncei/output/logs/stage3_full_strict_primary.nohup.log`

Companion deliverables:
- `ncei/docs/product_completion_table.tsv`
- `ncei/docs/product_anomaly_summary.tsv`
- `ncei/docs/strict_primary_weighted_vs_unweighted_summary.tsv`

---

## 1. Audit Scope and Constraints

Per audit charter:

- Step 06B quality rules: NOT modified.
- Step 07B validation products: NOT modified.
- Validation cells: NOT filtered or removed based on model residuals.
- expanded_primary: NOT executed in this audit.

This audit is read-only: it cross-checks already-generated artifacts and reports a Stage 4 GO/NO-GO recommendation.

---

## 2. Product Completion (Task 1)

All five global products completed successfully. Each was sampled against the full strict_primary cell list (2,398,774 cells) with the configured z/lon convention and sampling method, and produced a complete `full_validation_by_cell_strict_primary_<product>.parquet` plus its share of every stratification metrics table.

| product_name | status | rows | valid | nodata | sampling_method | elapsed_s |
|---|---|---:|---:|---:|---|---:|
| GEBCO_2024  | ok | 2,398,774 | 2,398,774 | 0 | cell_median      | 1042.3 |
| ETOPO_2022  | ok | 2,398,774 | 2,398,774 | 0 | center_bilinear  |   54.1 |
| SRTM15_V2.7 | ok | 2,398,774 | 2,398,774 | 0 | cell_median      |  961.9 |
| SDUST_2023  | ok | 2,398,774 | 2,398,774 | 0 | cell_median      |   51.5 |
| TOPO_25.1   | ok | 2,398,774 | 2,398,774 | 0 | cell_median      |   52.8 |

Source: `full_validation_product_status_strict_primary.tsv`, cross-checked against by-cell parquet row counts (see §4).

Status: **PASS**. All five expected global products are present and complete.

---

## 3. SWOT_T1 Skip (Task 2)

`skipped_products.tsv` records:

```
SWOT_T1	skipped	regional footprint product; not part of full global strict-primary run	0
```

The preflight (`preflight_config_status.tsv`) flagged SWOT_T1 as `has_footprint=True` while the other five products are `has_footprint=False`. The run log confirms: `Skipping SWOT_T1: regional footprint product; not part of full global strict-primary run`.

This is the documented, expected behavior. Skipping is content-policy correct (regional product cannot be globally validated against the full strict-primary cell set).

Status: **PASS**. Skip is documented and matches policy.

---

## 4. By-Cell Output Integrity (Task 3)

Direct PyArrow inspection of all five `full_validation_by_cell_strict_primary_<product>.parquet` files:

| Check                                  | GEBCO | ETOPO | SRTM | SDUST | TOPO |
|---|---:|---:|---:|---:|---:|
| row_count == 2,398,774                 | ✓ | ✓ | ✓ | ✓ | ✓ |
| product_role unique values             | {strict_primary_multibeam} | same | same | same | same |
| branch_role unique values              | {multibeam_primary, multibeam_supplement} | same | same | same | same |
| source_role unique values              | {multibeam_primary, multibeam_supplement} | same | same | same | same |
| rows containing "singlebeam" in any of (branch_role, source_role, branch, source_dataset, final_primary_source) | 0 | 0 | 0 | 0 | 0 |
| rows containing "regional_mrar" / "regional" in same columns                                                  | 0 | 0 | 0 | 0 | 0 |
| null validation_weight                 | 0 | 0 | 0 | 0 | 0 |
| null quality_tier                      | 0 | 0 | 0 | 0 | 0 |
| null evidence_class                    | 0 | 0 | 0 | 0 | 0 |
| null matched_rule_id                   | 0 | 0 | 0 | 0 | 0 |
| pyarrow.compute.is_finite(depth_error_m) all True | ✓ | ✓ | ✓ | ✓ | ✓ |
| RMSE matches summary table             | ✓ | ✓ | ✓ | ✓ | ✓ |

`depth_error_m` and `elev_error_m` are the residual columns present in each by-cell parquet; both are finite for every row. The pyarrow-computed RMSE (90.43, 91.61, 93.73, 99.94, 97.31) matches `full_validation_metrics_summary_strict_primary.tsv` to floating-point precision.

Status: **PASS**. Every by-cell file satisfies the row-count, role, null, and residual-finiteness contracts.

---

## 5. Stratified Metrics Coverage (Task 4)

All seven required stratification tables are present and populated for all five products:

| stratification | parquet                                                              | rows | strata distinct | strata values |
|---|---|---:|---:|---|
| model (overall)   | `full_validation_metrics_summary_strict_primary.parquet`            |  5  | 1  | "all" |
| quality_tier      | `full_validation_metrics_by_quality_tier_strict_primary.parquet`    | 15  | 3  | high_confidence, medium_confidence, low_confidence |
| evidence_class    | `full_validation_metrics_by_evidence_class_strict_primary.parquet`  | 20  | 4  | both, cross, jamstec_legacy, none |
| source_role       | `full_validation_metrics_by_source_role_strict_primary.parquet`     | 10  | 2  | multibeam_primary, multibeam_supplement |
| branch            | `full_validation_metrics_by_branch_strict_primary.parquet`          | 10  | 2  | jamstec_mb, multibeam_ncei |
| depth_bin         | `full_validation_metrics_by_depth_bin_strict_primary.parquet`       | 25  | 5  | 0-1000m, 1000-3000m, 3000-5000m, 5000-7000m, >7000m |
| lat_band_10deg    | `full_validation_metrics_by_lat_band_10deg_strict_primary.parquet`  | 75  | 15 | -70 … 70 in 10° steps |
| region_10deg      | `full_validation_metrics_by_region_10deg_strict_primary.parquet`    | 620 | 124 | 10° × 10° tiles |

Status: **PASS**. All seven cross-cuts requested by the audit charter are produced.

---

## 6. Product-Specific Anomaly Analysis (Task 5)

### 6.1 SDUST_2023 — highest MAE / MAD / p95

Overall (versus the four other products): MAE 33.09 (vs 21-25), MAD 13.64 (vs 6-8), p95 112.59 (vs 68-90), p99 295.53 (vs 203-284).

**Error is broadly distributed, not localized to a single regime.** SDUST RMSE exceeds peers in every depth bin and every lat band, with three pronounced concentrations:

| dimension | hot spots (SDUST RMSE) | peer RMSE for context |
|---|---|---|
| **lat_band_10deg** | +20° (137.81, n=549,924), +30° (105.55, n=650,691), +10° (98.48, n=244,008) | GEBCO/ETOPO at same bands: 132.84/132.79, 99.01/98.50, 79.77/81.74 — *similar magnitude, SDUST consistently a few m higher* |
| **lat_band_10deg** (high-lat divergence) | −40° (60.10, n=14,553), +70° (56.85, n=49,846), −70° (57.16, n=3,015) | GEBCO at same bands: 37.35, 22.87, 40.00 — *SDUST notably worse at high latitudes, consistent with altimetric model degradation away from ground-truth constraints* |
| **depth_bin** | mid-depth excess: 1000-3000m RMSE 68.43, 3000-5000m RMSE 71.76 | GEBCO equivalents: 49.78, 55.41 — *SDUST is ~15-20 m worse in 1-5 km depth, the bulk of the ocean by count (n≈1.09 M cells in mid bins)* |
| **depth_bin** | trench: >7000m RMSE 466.47, bias +104.83 m (n=45,956) | GEBCO 460.24 / +92.06; SDUST trench tail only marginally worse than peers |
| **region_10deg** (top 5) | lon0140_lat0020 (Izu-Bonin/Japan): RMSE 181.13; lon0150_lat0020 (Mariana/Bonin): 162.54; lon0150_lat-020 (New Britain/Solomon): 134.57; lon0150_lat0030 (Japan Trench north): 128.55; lon0170_lat0000 (West Pacific equatorial trench complex): 134.36 | These same NW Pacific subduction-zone tiles are the worst regions for **every** product (see §6.3) — SDUST's regional pattern matches peers, just at a higher floor |

**Interpretation.** SDUST's elevated error is structural and global; it is not a single regional defect. The pattern (worst at mid-latitudes/mid-depths and at the poles) is consistent with the known limits of an altimetry-derived bathymetry model relative to in-situ constraints. There is no evidence of a sampling or conversion bug — the elevation_correlation is 0.998 and the depth range maps cleanly to peer products.

### 6.2 TOPO_25.1 and SRTM15_V2.7 — slightly higher RMSE than GEBCO / ETOPO

Overall RMSEs: GEBCO 90.43 < ETOPO 91.61 < SRTM 93.73 < TOPO 97.31 < SDUST 99.94.

The TOPO and SRTM excess over GEBCO / ETOPO is **global, not regional**:

| depth_bin   | GEBCO RMSE | ETOPO RMSE | SRTM RMSE | TOPO RMSE | SRTM − GEBCO | TOPO − GEBCO |
|---|---:|---:|---:|---:|---:|---:|
| 0-1000m     | 51.83 | 50.60 | 56.16 | 57.89 | +4.3 | +6.1 |
| 1000-3000m  | 49.78 | 51.58 | 60.91 | 66.18 | +11.1 | +16.4 |
| 3000-5000m  | 55.41 | 60.01 | 62.22 | 68.53 | +6.8  | +13.1 |
| 5000-7000m  | 74.28 | 74.33 | 75.89 | 79.66 | +1.6  | +5.4  |
| >7000m      | 460.24 | 461.39 | 463.43 | 465.39 | +3.2  | +5.2  |

The excess is largest in the **1000-5000 m mid-depth regime**, where TOPO is ~+13 m and SRTM is ~+7 m over GEBCO. The trench (>7000m) and the deep abyssal (5000-7000m) bins are essentially identical across all four products — the trench tail is dominated by interpolation in the same hard regions for every model.

By lat_band, the same picture holds. At high southern latitudes:

| lat_band | GEBCO RMSE | ETOPO RMSE | SRTM RMSE | TOPO RMSE |
|---|---:|---:|---:|---:|
| −70°     | 40.00 | 41.92 | **72.60** | **77.78** |
| −60°     | 60.38 | 68.91 | 60.65 | 60.41 |

The −70° band is the one place TOPO/SRTM diverge sharply from GEBCO/ETOPO (about +30 m RMSE), but it represents only 3,015 cells (0.13% of the global count), so it contributes little to the overall RMSE delta. The bulk of the TOPO/SRTM excess is the broad mid-depth pattern, not the south-polar anomaly.

**Interpretation.** TOPO and SRTM are global products with slightly noisier interpolation in mid-depth regions where seamounts and rough topography dominate. No product-specific defect requiring code or rule changes; the gap is a known property of the underlying gridded models.

### 6.3 Cross-product worst-region check

The top-5 highest-RMSE 10°×10° tiles (filtering to ≥2,000 cells) for each product are dominated by the same three NW Pacific subduction-zone tiles:

| Tile | Region | In top-5 RMSE for |
|---|---|---|
| lon0140_lat0020 | Izu-Bonin / Japan Trench    | all 5 products |
| lon0150_lat0020 | Mariana / Bonin             | all 5 products |
| lon0150_lat-020 | New Britain / Solomon       | all 5 products |

This shared pattern confirms the spatial distribution of error is dominated by *terrain difficulty*, not by product-specific bugs.

### 6.4 Sign-flip behavior — no product affected

Two independent checks rule out any sign-convention error:

1. **Sample diagnostics:** `full_validation_sample_diagnostics_strict_primary.tsv` reports `sign_error_suspected=False` for every product. Elevation correlation against ship-track elevation is 0.998 for all five.
2. **Audit re-check:** Inspecting `bias` per lat_band: all five products show the **same** sign pattern (positive bias at +10°…+30°, mixed near ±50°, near-zero at the equator). If any one product had a flipped convention, its bias column would be the mirror image of the others — instead, all five move in the same direction at each latitude.

Status: **PASS** (no sign flip).

---

## 7. Weighted vs Unweighted Comparison (Task 6)

Source: `full_validation_metrics_summary_strict_primary.parquet` and `full_validation_metrics_by_quality_tier_strict_primary.parquet`.

| product     | unweighted RMSE | weighted RMSE | Δ (m) | Δ (%) | weighted < unweighted? |
|---|---:|---:|---:|---:|---|
| GEBCO_2024  | 90.43 | 68.58 | -21.84 | -24.16% | YES |
| ETOPO_2022  | 91.61 | 70.06 | -21.55 | -23.52% | YES |
| SRTM15_V2.7 | 93.73 | 72.55 | -21.18 | -22.60% | YES |
| SDUST_2023  | 99.94 | 79.97 | -19.97 | -19.99% | YES |
| TOPO_25.1   | 97.31 | 76.72 | -20.59 | -21.16% | YES |

**Driver of the reduction — the low_confidence tier.** Quality-tier RMSE breakdown:

| tier               | count    | share | GEBCO RMSE | ETOPO RMSE | SRTM RMSE | SDUST RMSE | TOPO RMSE |
|---|---:|---:|---:|---:|---:|---:|---:|
| high_confidence    |   697,282 | 29.07% |  23.47 |  25.69 |  31.06 |  43.02 |  37.69 |
| medium_confidence  | 1,366,544 | 56.97% |  28.52 |  33.08 |  37.50 |  51.21 |  45.33 |
| low_confidence     |   334,948 | 13.96% | 232.58 | 232.95 | 234.90 | 238.70 | 237.65 |

Low_confidence cells are ~14% of the cell count but have RMSE ~230-240 m — roughly **10× the high_confidence tier**. Because RMSE is variance-dominated, this 14% pulls the unweighted RMSE up dramatically. The `validation_weight` field down-weights these cells, recovering the ~20-24% RMSE reduction shown above.

SDUST shows the smallest relative reduction (-19.99%) because its high/medium tiers are themselves elevated, so the low-confidence dilution effect is proportionally smaller.

Status: **PASS**. Weighted RMSE is lower than unweighted RMSE for every product, and the reduction is unambiguously driven by the low_confidence tier.

---

## 8. Safety Re-Check (Independent Re-Verification)

Reproduced from `full_validation_safety_checks_strict_primary.tsv` and cross-checked against per-cell data:

| check                                              | reported | audit re-check |
|---|---|---|
| input_row_count                                    | PASS (2,398,774) | PASS — every by-cell parquet has exactly 2,398,774 rows |
| no_singlebeam_in_strict_primary                    | PASS | PASS — 0 rows with "singlebeam" in any source label |
| no_regional_mrar_in_strict_primary                 | PASS | PASS — 0 rows with "regional_mrar" / "regional" in any source label |
| validation_weight_preserved (no nulls)             | PASS | PASS — 0 nulls per product |
| quality_tier_preserved (no nulls)                  | PASS | PASS — 0 nulls per product |
| evidence_class_preserved (no nulls)                | PASS | PASS — 0 nulls per product |
| matched_rule_id_preserved (no nulls)               | PASS | PASS — 0 nulls per product |
| sign_error_suspected_false                         | PASS | PASS — elev_corr 0.998 across all; consistent bias signs across products |
| model_errors_do_not_corrupt_other_outputs          | PASS | PASS — 0 error products |
| no_model_residual_filtering                        | PASS | PASS — every strict-primary cell appears in every by-cell parquet, with `depth_error_m` populated and finite (no model-residual-based row drops) |

---

## 9. GO / NO-GO Recommendation for Stage 4 expanded_primary Sensitivity Validation (Task 7)

**Recommendation: GO.**

Rationale:

1. **Strict-primary baseline is clean.** All five global products processed all 2,398,774 strict_primary cells with no nodata, no nulls in support attributes, no forbidden source mixing, and finite residuals everywhere.
2. **All required stratifications are produced.** model / quality_tier / evidence_class / source_role / branch / depth_bin / lat_band_10deg / region_10deg are populated for every product. Stage 4 sensitivity comparisons against expanded_primary will have a 1-to-1 baseline.
3. **No sign-convention error.** Independent re-check via elevation correlation and cross-product bias-sign pattern matches the run's own `sign_error_suspected=False`.
4. **Anomalies are explained.** SDUST's elevated error is global and structural (altimetric model), not a defect. TOPO/SRTM's slight RMSE excess over GEBCO/ETOPO is mid-depth/global and not regional. All five products share the same worst-region pattern (NW Pacific subduction zones), confirming the error structure reflects terrain difficulty rather than product-specific bugs. None of these warrant changes to Step 06B / Step 07B.
5. **Weighted-vs-unweighted behavior is exactly as designed.** The 20-24% RMSE reduction maps cleanly to the low_confidence tier (~14% of cells, ~10× RMSE), validating the weighting policy from Step 06B.

Stage 4 expanded_primary sensitivity validation can proceed against this strict_primary baseline. Pre-conditions for Stage 4 entry (no modifications to quality rules, no residual-based filtering, no validation_cell mutation) are observed in this audit and should be maintained when expanded_primary runs.

---

## 10. Files Produced by This Audit

- `ncei/docs/strict_primary_full_validation_audit_report.md` (this file)
- `ncei/docs/product_completion_table.tsv`
- `ncei/docs/product_anomaly_summary.tsv`
- `ncei/docs/strict_primary_weighted_vs_unweighted_summary.tsv`
