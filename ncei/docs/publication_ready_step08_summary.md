# Step 08 Followup — Publication-Ready Summary

Generated: 2026-05-27T20:06:15.539270+00:00
Cross-check status: **PASS** (30 pass, 0 fail)

This is the parent-level integration of four sub-tasks:

- **A** — model ranking uncertainty (paired cluster block bootstrap)
- **B** — publication-ready strict-primary and strict-vs-expanded metric tables
- **C** — gap-fill singlebeam error structure attribution
- **D** — publication-ready figures and figure-ready TSV

All upstream Step 06B / 07B / Step 08 Stage 3-6 products are read-only.
No model resampling was performed; no validation cells were filtered by residuals.

## 1. Headline conclusions

1. `strict_primary_multibeam_cells` (N = 2,398,774) remains the authoritative global validation baseline. Final policy stance is unchanged from Stage 6 final report.
2. Model ranking by strict-primary RMSE — **GEBCO_2024 < ETOPO_2022 < SRTM15_V2.7 < TOPO_25.1 < SDUST_2023**. Cluster-bootstrap rank-1 probability for GEBCO is **0.905**; rank-5 probability for SDUST is **0.970**.
3. **GEBCO vs ETOPO is **NOT significant** at the 95% confidence level**: ΔRMSE 95% CI = [-4.28, 0.16], P(GEBCO better) = 0.906. All other pairs adjacent in ranking are reported in the full pairwise table below; tier-skipping pairs (GEBCO vs SRTM15+, etc.) are significant.
4. Expanded-primary lifts global RMSE by **+6 to +8 m** because the 333,915 singlebeam gap-fill cells have RMSE 1.43–1.59 × that of retained multibeam cells. Ranking is preserved under expansion; expanded-primary is sensitivity only.
5. Gap-fill RMSE inflation is dominated by **quality_tier = medium_confidence** (82.2% of total gap-fill squared error). Concretely: medium-confidence quality tier, low-latitude deep-overlap rule, and 1000–2000 m depth band drive the lift; this is consistent with the retained multibeam baseline being higher-quality multibeam and the gap-fill subset being lower-quality singlebeam.

## 2. Strict-primary publication metric table (B)

| model | n_cells | bias | MAE | RMSE | weighted MAE | weighted RMSE | median error | MAD | p95 abs error |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GEBCO_2024 | 2,398,774 | 7.26 | 21.26 | 90.43 | 17.61 | 68.58 | 0.30 | 6.80 | 68.67 |
| ETOPO_2022 | 2,398,774 | 8.16 | 22.57 | 91.61 | 18.83 | 70.06 | 0.51 | 7.54 | 72.65 |
| SRTM15_V2.7 | 2,398,774 | 6.72 | 22.15 | 93.73 | 18.23 | 72.55 | 0.07 | 6.18 | 75.95 |
| TOPO_25.1 | 2,398,774 | 5.61 | 25.24 | 97.31 | 21.21 | 76.72 | -1.39 | 6.91 | 89.67 |
| SDUST_2023 | 2,398,774 | 9.84 | 33.09 | 99.94 | 29.12 | 79.97 | 2.52 | 13.64 | 112.59 |

Source: `ncei/derived/model_validation_1min_step08_pub/b_pub_tables/strict_primary_publication_table.tsv`

## 3. Strict vs expanded comparison (B)

| model | strict RMSE | expanded RMSE | ΔRMSE | strict wRMSE | expanded wRMSE | ΔwRMSE | retained RMSE | gap-fill RMSE | ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GEBCO_2024 | 90.43 | 98.56 | +8.13 | 68.58 | 80.73 | +12.15 | 90.43 | 144.08 | 1.59 |
| ETOPO_2022 | 91.61 | 99.27 | +7.67 | 70.06 | 81.57 | +11.50 | 91.61 | 142.71 | 1.56 |
| SRTM15_V2.7 | 93.73 | 101.32 | +7.59 | 72.55 | 83.87 | +11.32 | 93.73 | 144.57 | 1.54 |
| TOPO_25.1 | 97.31 | 104.32 | +7.01 | 76.72 | 87.13 | +10.41 | 97.31 | 145.02 | 1.49 |
| SDUST_2023 | 99.94 | 106.10 | +6.15 | 79.97 | 89.23 | +9.26 | 99.94 | 142.71 | 1.43 |

Source: `ncei/derived/model_validation_1min_step08_pub/b_pub_tables/strict_vs_expanded_publication_table.tsv`

## 4. Bootstrap CI for strict-primary RMSE (A)

| model | point | p2.5 | p50 | p97.5 | CI covers point |
|---|---:|---:|---:|---:|:---:|
| GEBCO_2024 | 90.43 | 68.04 | 89.66 | 108.03 | True |
| ETOPO_2022 | 91.61 | 70.69 | 90.96 | 108.70 | True |
| SRTM15_V2.7 | 93.73 | 72.19 | 93.03 | 111.07 | True |
| TOPO_25.1 | 97.31 | 76.06 | 96.54 | 114.05 | True |
| SDUST_2023 | 99.94 | 82.02 | 99.22 | 115.24 | True |

Method: paired cluster bootstrap with 124 `region_10deg` blocks, B = 1000, percentile 95% CI, seed 20260528.

## 5. Bootstrap CI for strict-primary weighted RMSE (A)

| model | point | p2.5 | p50 | p97.5 | CI covers point |
|---|---:|---:|---:|---:|:---:|
| GEBCO_2024 | 68.58 | 52.76 | 67.91 | 81.34 | True |
| ETOPO_2022 | 70.06 | 55.71 | 69.58 | 82.46 | True |
| SRTM15_V2.7 | 72.55 | 57.36 | 72.01 | 85.13 | True |
| TOPO_25.1 | 76.72 | 61.97 | 76.28 | 89.61 | True |
| SDUST_2023 | 79.97 | 68.18 | 79.48 | 91.20 | True |

## 6. Pairwise ΔRMSE 95% CI (A)

| model A | model B | ΔRMSE point | 95% CI | P(A better) | significant 95% |
|---|---|---:|---|---:|:---:|
| GEBCO_2024 | ETOPO_2022 | -1.18 | [-4.28, 0.16] | 0.906 | False |
| GEBCO_2024 | SRTM15_V2.7 | -3.31 | [-5.20, -1.81] | 0.999 | True |
| GEBCO_2024 | TOPO_25.1 | -6.89 | [-10.28, -4.32] | 1.000 | True |
| GEBCO_2024 | SDUST_2023 | -9.51 | [-14.65, -6.73] | 1.000 | True |
| ETOPO_2022 | SRTM15_V2.7 | -2.12 | [-4.74, 1.37] | 0.914 | False |
| ETOPO_2022 | TOPO_25.1 | -5.70 | [-9.51, -1.96] | 0.997 | True |
| ETOPO_2022 | SDUST_2023 | -8.33 | [-13.43, -4.94] | 1.000 | True |
| SRTM15_V2.7 | TOPO_25.1 | -3.58 | [-5.84, -2.15] | 1.000 | True |
| SRTM15_V2.7 | SDUST_2023 | -6.21 | [-10.83, -3.81] | 1.000 | True |
| TOPO_25.1 | SDUST_2023 | -2.63 | [-6.86, 0.11] | 0.970 | False |

`p_a_better` = bootstrap fraction of iterations in which model A has lower RMSE than model B.

## 7. Ranking stability by RMSE (A)

| model | rank-1 | rank-2 | rank-3 | rank-4 | rank-5 |
|---|---:|---:|---:|---:|---:|
| GEBCO_2024 | 0.905 | 0.095 | 0.000 | 0.000 | 0.000 |
| ETOPO_2022 | 0.094 | 0.820 | 0.083 | 0.003 | 0.000 |
| SRTM15_V2.7 | 0.001 | 0.085 | 0.914 | 0.000 | 0.000 |
| TOPO_25.1 | 0.000 | 0.000 | 0.003 | 0.967 | 0.030 |
| SDUST_2023 | 0.000 | 0.000 | 0.000 | 0.030 | 0.970 |

## 8. Ranking stability by weighted RMSE (A)

| model | rank-1 | rank-2 | rank-3 | rank-4 | rank-5 |
|---|---:|---:|---:|---:|---:|
| GEBCO_2024 | 0.954 | 0.046 | 0.000 | 0.000 | 0.000 |
| ETOPO_2022 | 0.046 | 0.875 | 0.076 | 0.003 | 0.000 |
| SRTM15_V2.7 | 0.000 | 0.079 | 0.921 | 0.000 | 0.000 |
| TOPO_25.1 | 0.000 | 0.000 | 0.003 | 0.972 | 0.025 |
| SDUST_2023 | 0.000 | 0.000 | 0.000 | 0.025 | 0.975 |

## 9. Top gap-fill error contributors (C)

| dim | value | model | n_cells | share | RMSE gap-fill | RMSE retained | Δ slice | % of gap-fill sumsq |
|---|---|---|---:|---:|---:|---:|---:|---:|
| quality_tier | medium_confidence | SDUST_2023 | 235,210 | 0.704 | 154.20 | 51.21 | 102.99 | 82.24 |
| quality_tier | medium_confidence | GEBCO_2024 | 235,210 | 0.704 | 155.36 | 28.52 | 126.83 | 81.90 |
| quality_tier | medium_confidence | ETOPO_2022 | 235,210 | 0.704 | 153.87 | 33.08 | 120.79 | 81.89 |
| quality_tier | medium_confidence | TOPO_25.1 | 235,210 | 0.704 | 156.30 | 45.33 | 110.97 | 81.82 |
| quality_tier | medium_confidence | SRTM15_V2.7 | 235,210 | 0.704 | 155.22 | 37.50 | 117.72 | 81.21 |
| matched_rule_id | sb_v0_lowlat_deep_overlap_medium | SDUST_2023 | 234,427 | 0.702 | 145.59 | nan | nan | 73.07 |
| matched_rule_id | sb_v0_lowlat_deep_overlap_medium | GEBCO_2024 | 234,427 | 0.702 | 146.79 | nan | nan | 72.87 |
| matched_rule_id | sb_v0_lowlat_deep_overlap_medium | TOPO_25.1 | 234,427 | 0.702 | 147.62 | nan | nan | 72.75 |
| matched_rule_id | sb_v0_lowlat_deep_overlap_medium | ETOPO_2022 | 234,427 | 0.702 | 145.22 | nan | nan | 72.70 |
| matched_rule_id | sb_v0_lowlat_deep_overlap_medium | SRTM15_V2.7 | 234,427 | 0.702 | 146.64 | nan | nan | 72.24 |

`contribution_pct_of_total_gapfill_sumsq` is computed per slice as `sum(err^2 in slice) / sum(err^2 over all gap-fill cells)`. Slices from different dimensions overlap; do not add percentages across dimensions.

## 10. Figures (D)

| ID | Title | PNG | PDF | data TSV |
|---|---|---|---|---|
| F1 | Strict-primary RMSE + weighted RMSE with 95% CI | `ncei/derived/model_validation_1min_step08_pub/d_figures/F1_strict_rmse_ci.png` | `ncei/derived/model_validation_1min_step08_pub/d_figures/F1_strict_rmse_ci.pdf` | `ncei/derived/model_validation_1min_step08_pub/d_figures/figure_data_F1.tsv` |
| F2 | Strict vs expanded RMSE | `ncei/derived/model_validation_1min_step08_pub/d_figures/F2_strict_vs_expanded.png` | `ncei/derived/model_validation_1min_step08_pub/d_figures/F2_strict_vs_expanded.pdf` | `ncei/derived/model_validation_1min_step08_pub/d_figures/figure_data_F2.tsv` |
| F3 | Depth-bin RMSE curves | `ncei/derived/model_validation_1min_step08_pub/d_figures/F3_depth_bin_rmse.png` | `ncei/derived/model_validation_1min_step08_pub/d_figures/F3_depth_bin_rmse.pdf` | `ncei/derived/model_validation_1min_step08_pub/d_figures/figure_data_F3.tsv` |
| F4 | Latitude-band RMSE curves | `ncei/derived/model_validation_1min_step08_pub/d_figures/F4_lat_band_rmse.png` | `ncei/derived/model_validation_1min_step08_pub/d_figures/F4_lat_band_rmse.pdf` | `ncei/derived/model_validation_1min_step08_pub/d_figures/figure_data_F4.tsv` |
| F5 | 10° region RMSE map (GEBCO_2024) | `ncei/derived/model_validation_1min_step08_pub/d_figures/F5_region_rmse_map.png` | `ncei/derived/model_validation_1min_step08_pub/d_figures/F5_region_rmse_map.pdf` | `ncei/derived/model_validation_1min_step08_pub/d_figures/figure_data_F5.tsv` |
| F6 | Expanded gap-fill coverage map | `ncei/derived/model_validation_1min_step08_pub/d_figures/F6_gapfill_coverage_map.png` | `ncei/derived/model_validation_1min_step08_pub/d_figures/F6_gapfill_coverage_map.pdf` | `ncei/derived/model_validation_1min_step08_pub/d_figures/figure_data_F6.tsv` |

## 11. Cross-check (parent integration gate)

- 30 cross-check assertions PASS, 0 FAIL. Full table in `step08_pub_cross_check.tsv`.
- Stage 4 anchor: B strict RMSE and ΔRMSE per model exactly match `strict_vs_expanded_comparison.parquet` within tolerance 0.01 m.
- A 95% CI covers each B point estimate for both RMSE and weighted RMSE.
- C retained subset RMSE matches B strict-primary RMSE (and Stage 3) exactly.
- D figures derive from the same upstream TSV and embed no new aggregation.

## 12. Manifest

Total artifact files: 40

Subtask root: `ncei/derived/model_validation_1min_step08_pub/`
- `a_ranking_uncertainty/` — bootstrap iters parquet, CI tables, rank probability matrices, safety checks
- `b_pub_tables/` — TSV + CSV publication tables, safety checks
- `c_gapfill_structure/` — single-dim slice TSVs, attribution top-N, model totals, safety checks
- `d_figures/` — figure-ready TSVs, PNGs, PDFs, safety checks
- `summary/` — this report's cross-check, manifest, and metadata

Detailed file listing with sizes and SHA256: `ncei/derived/model_validation_1min_step08_pub/summary/step08_pub_manifest.tsv`

## 13. Policy stance (unchanged from Stage 6)

| area | recommendation |
|---|---|
| global_baseline | `strict_primary_multibeam_cells` is the authoritative global validation baseline. |
| expanded_primary | `expanded_primary_ship_cells` is secondary sensitivity / coverage-expansion only. |
| supplementary_singlebeam | Coverage diagnostics only. |
| regional_mrar | Explicit regional sensitivity experiments only. |
| swot_t1 | No global validation claim; separate regional task required. |
| quality_policy | Do not use model residuals to filter, relabel, or promote validation cells. |

## 14. Sub-task reports

- A: `ncei/docs/model_ranking_uncertainty_report.md`
- C: `ncei/docs/step08_gapfill_error_structure_report.md`
- Anchor: `ncei/docs/step08_final_global_validation_report.md` (Stage 6 final)

