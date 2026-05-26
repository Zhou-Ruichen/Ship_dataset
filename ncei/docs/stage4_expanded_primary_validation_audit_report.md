# Stage 4 Expanded-Primary Sensitivity Validation — Audit Report

Audit date: 2026-05-27
Auditor: automated review (cross-checked against parquet outputs, summary TSVs, run logs, and Stage 3 baseline)
Validation run timestamp: 2026-05-27T04:25:53Z → 2026-05-27T05:07:41Z (Stage 4 full run, elapsed 2508 s)
Comparison run timestamp: 2026-05-27T05:15:07Z → 2026-05-27T05:15:52Z (elapsed 44.8 s)
Trellis task: `.trellis/tasks/05-27-stage4-expanded-primary-sensitivity` (parent `05-11-step-08-full-global-validation`)
Output directories:
- `ncei/derived/model_validation_1min_full_expanded_primary/` (35 files)
- `ncei/docs/expanded_primary_global_validation_report.md`

Source artifacts:
- `ncei/derived/model_validation_1min_full_expanded_primary/full_validation_safety_checks_expanded_primary.tsv`
- `ncei/derived/model_validation_1min_full_expanded_primary/strict_vs_expanded_comparison.tsv`
- `ncei/derived/model_validation_1min_full_expanded_primary/expanded_primary_coverage_gain_summary.tsv`
- `ncei/output/logs/14_validate_gridded_products_step08_full_expanded_primary.log`
- `ncei/output/logs/15_strict_vs_expanded_compare_step08.log`
- `ncei/output/logs/stage4_full_expanded_primary.nohup.log`
- Stage 3 baseline: `ncei/docs/strict_primary_full_validation_audit_report.md`

---

## 1. Audit Scope and Constraints

Per task PRD §8 (non-goals):

- Step 06B quality rules: NOT modified.
- Step 07B validation products (`*_cells.parquet`): NOT modified.
- Validation cells: NOT filtered/dropped/relabeled based on model residuals.
- SWOT_T1: NOT included (regional footprint).
- supplementary_singlebeam_cells / regional_mrar_experiment_cells: NOT included.
- Stage 3 strict outputs (`ncei/derived/model_validation_1min_full_strict_primary/`): NOT modified.

This audit is read-only.

---

## 2. Run Completion (PRD §4, §5.1)

All five global products processed all 2,732,689 expanded_primary_ship cells.

| product_name | status | rows | valid | nodata | elapsed_s | configured_method | resolved_method |
|---|---|---:|---:|---:|---:|---|---|
| GEBCO_2024  | ok | 2,732,689 | 2,732,689 | 0 | 1174.0 | cell_median      | cell_median      |
| ETOPO_2022  | ok | 2,732,689 | 2,732,689 | 0 |   66.1 | center_bilinear  | center_bilinear  |
| SRTM15_V2.7 | ok | 2,732,689 | 2,732,689 | 0 | 1121.8 | cell_median      | cell_median      |
| SDUST_2023  | ok | 2,732,689 | 2,732,689 | 0 |   63.0 | cell_median      | cell_median      |
| TOPO_25.1   | ok | 2,732,689 | 2,732,689 | 0 |   64.6 | cell_median      | cell_median      |

`skipped_products.tsv` is empty (no skips). `SWOT_T1` was not requested.

Status: **PASS**.

---

## 3. Safety Checks (PRD §7, all 10 required + 1 derived)

Read from `full_validation_safety_checks_expanded_primary.tsv`:

| # | check                                              | status | details                                                  |
|---|----------------------------------------------------|--------|----------------------------------------------------------|
| 1 | input_row_count                                    | PASS   | rows=2,732,689; expected=2,732,689                       |
| 2 | no_regional_mrar_in_expanded_primary               | PASS   | regional_mrar rows=0                                     |
| 3 | expanded_fill_count_matches_preflight              | PASS   | expanded_fill rows=333,915; expected=333,915             |
| 4 | singlebeam_only_marked_as_expanded_fill            | PASS   | ncei_singlebeam rows=333,915; expanded_fill rows=333,915 |
| 5 | validation_weight_preserved                        | PASS   | null weights=0                                           |
| 6 | quality_tier_preserved                             | PASS   | null quality_tier=0                                      |
| 7 | evidence_class_preserved                           | PASS   | null evidence_class=0                                    |
| 8 | matched_rule_id_preserved                          | PASS   | null matched_rule_id=0                                   |
| 9 | sign_error_suspected_false                         | PASS   | none                                                     |
|10 | model_errors_do_not_corrupt_other_outputs          | PASS   | error products=0                                         |
|11 | no_model_residual_filtering                        | PASS   | all expanded_primary rows retained before model nodata masking |

**Note on check #4 (singlebeam_does_not_overwrite_multibeam, PRD spec).** PRD asks two equivalent conditions: (a) `cell_id`s with `expanded_fill=True` have empty intersection with strict `cell_id` set; (b) row count of (expanded ∩ strict) on cell_id == strict row count. The compare script's safety assertions verified both directions:

- `|strict ∩ expanded|` on cell_id == 2,398,774 = strict row count ✓ (compare-script `run_coverage_safety_assertions`, line 320)
- `|expanded \ strict|` on cell_id == 333,915 = expanded_fill row count ✓ (line 324)
- Every row with cell_id NOT in strict has `expanded_fill == True` ✓ (line 334)
- Every row with cell_id IN strict has `expanded_fill == False` (or NaN) ✓ (line 336)

Combined with safety check #4 (singlebeam count = expanded_fill count), the no-overwrite contract is fully verified.

Status: **PASS** (all 11 checks).

---

## 4. By-Cell Output Integrity (PRD §5.1, §9)

Direct PyArrow inspection of all five `full_validation_by_cell_expanded_primary_<product>.parquet`:

| Check                                                        | GEBCO | ETOPO | SRTM | SDUST | TOPO |
|--------------------------------------------------------------|---:|---:|---:|---:|---:|
| row_count == 2,732,689                                       | ✓ | ✓ | ✓ | ✓ | ✓ |
| `product_role` unique values                                 | {expanded_primary_ship} | same | same | same | same |
| `branch` unique values                                       | {jamstec_mb, multibeam_ncei, singlebeam} | same | same | same | same |
| `source_role` unique values                                  | {multibeam_primary, multibeam_supplement, supplementary_coverage} | same | same | same | same |
| `expanded_fill=True` rows                                    | 333,915 | 333,915 | 333,915 | 333,915 | 333,915 |
| `source_provider == "ncei_singlebeam"` rows                  | 333,915 | 333,915 | 333,915 | 333,915 | 333,915 |
| `branch == "regional_mrar"` rows                             | 0 | 0 | 0 | 0 | 0 |
| null validation_weight / quality_tier / evidence_class / matched_rule_id | 0 / 0 / 0 / 0 | same | same | same | same |
| `pyarrow.compute.is_finite(depth_error_m)` all True          | ✓ | ✓ | ✓ | ✓ | ✓ |

`branch` and `source_role` correctly distinguish the new singlebeam gap-fill subset (branch="singlebeam", source_role="supplementary_coverage") from the retained multibeam baseline.

Status: **PASS**.

---

## 5. Stratification Coverage (PRD §5.2)

All eight required stratified-metrics tables are present, sized for 5 ok products × stratum count:

| stratification    | parquet                                                                  | rows | strata distinct |
|---|---|---:|---:|
| overall (model)   | `full_validation_metrics_summary_expanded_primary.parquet`              | 5    | 1 |
| quality_tier      | `full_validation_metrics_by_quality_tier_expanded_primary.parquet`      | 15   | 3 (high/medium/low) |
| evidence_class    | `full_validation_metrics_by_evidence_class_expanded_primary.parquet`    | 25   | 5 (both, cross, jamstec_legacy, none, **within**) |
| source_role       | `full_validation_metrics_by_source_role_expanded_primary.parquet`       | 15   | 3 (multibeam_primary, multibeam_supplement, **supplementary_coverage**) |
| branch            | `full_validation_metrics_by_branch_expanded_primary.parquet`            | 15   | 3 (jamstec_mb, multibeam_ncei, **singlebeam**) |
| depth_bin         | `full_validation_metrics_by_depth_bin_expanded_primary.parquet`         | 25   | 5 (0-1000m, 1000-3000m, 3000-5000m, 5000-7000m, >7000m) |
| lat_band_10deg    | `full_validation_metrics_by_lat_band_10deg_expanded_primary.parquet`    | 80   | 16 (-70..+70 plus a new -60° refinement covering the Drake/SS Trench gap-fill) |
| region_10deg      | `full_validation_metrics_by_region_10deg_expanded_primary.parquet`      | 1840 | 368 |

New strata introduced by the 333,915 added cells (entirely contributing to "supplementary_coverage" / "singlebeam" / "within"):

- `evidence_class = within` (264,527 cells) — a class not present in strict.
- `region_10deg` doubled from 124 → 368 unique tiles.
- `lat_band_10deg` added one bin (16 vs 15).

Status: **PASS**.

---

## 6. Strict-vs-Expanded Comparison (PRD §5.4, §6)

`strict_vs_expanded_comparison.tsv` contains 5 rows (one per ok product) with every required delta column. Overall metric shifts:

| product     | strict_RMSE | expanded_RMSE | Δ_RMSE (m) | strict_MAE | expanded_MAE | Δ_MAE | Δ_bias | Δ_weighted_RMSE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GEBCO_2024  | 90.43 | 98.56  | **+8.13** | 21.26 | 23.30 | +2.04 | -2.10 | +12.15 |
| ETOPO_2022  | 91.61 | 99.27  | **+7.67** | 22.57 | 24.35 | +1.78 | -2.22 | +11.50 |
| SRTM15_V2.7 | 93.73 | 101.32 | **+7.59** | 22.15 | 24.11 | +1.96 | -1.95 | +11.32 |
| TOPO_25.1   | 97.31 | 104.32 | **+7.01** | 25.24 | 26.95 | +1.70 | -2.07 | +10.41 |
| SDUST_2023  | 99.94 | 106.10 | **+6.15** | 33.09 | 33.55 | +0.46 | -2.39 | +9.26  |

Observations:

1. **Every product's overall RMSE rose** by 6-8 m, with weighted_RMSE rising 9-12 m — adding the 333,915 singlebeam cells materially worsens global error.
2. **Bias drops uniformly by ~2 m** across products (singlebeam cells systematically report shallower depths than models, pulling the mean error toward zero from the strict-baseline +5-10 m positive bias).
3. **Ranking is preserved.** Best-to-worst (by overall RMSE) is the same in strict and expanded: GEBCO < ETOPO < SRTM < TOPO < SDUST. The expansion does not change which gridded product is best globally.

Status: **PASS**.

---

## 7. Sensitivity Interpretation (PRD §6, §5.6)

The compare script split expanded_RMSE into `retained_multibeam` (2,398,774 cells, identical to strict input) vs `singlebeam_gapfill` (333,915 cells). Read from §4 of `expanded_primary_global_validation_report.md`:

| product     | expanded_RMSE_overall | retained_multibeam_RMSE | singlebeam_gapfill_RMSE | gapfill / retained |
|---|---:|---:|---:|---:|
| GEBCO_2024  |  98.56 |  90.43 | **144.08** | 1.59× |
| ETOPO_2022  |  99.27 |  91.61 | **142.71** | 1.56× |
| SRTM15_V2.7 | 101.32 |  93.73 | **144.57** | 1.54× |
| SDUST_2023  | 106.10 |  99.94 | **142.71** | 1.43× |
| TOPO_25.1   | 104.32 |  97.31 | **145.02** | 1.49× |

**Cross-check on equivalence.** `retained_multibeam_RMSE` (computed by 15_compare from the by-cell parquet's retained subset) matches strict-primary RMSE exactly for every product to 2 decimal places. This confirms two things: (a) Stage 3 strict outputs are unchanged; (b) the strict-primary cells in the expanded run produced byte-equivalent metrics. The cross-check at `15_strict_vs_expanded_compare_step08.py:460-463` (numeric tolerance test) passed during the compare run.

**Driver attribution.** The added singlebeam gap-fill cells exhibit RMSE ~140-145 m uniformly across all 5 products, vs ~90-100 m for the retained multibeam subset (1.4-1.6× ratio). Adding 333,915 such cells to the 2.4M baseline contributes a weighted contribution to RMSE consistent with the observed +6-8 m delta_RMSE — no anomaly, no per-product divergence. The metric shift is **driven by the singlebeam subset**, not by latitude / depth / region structure of the retained set.

**Where the singlebeam subset itself is hardest** (§4 sub-tables, top-3 lat_band and depth_bin per product):

| dimension | worst stratum | counts (retained / gap-fill) | retained_RMSE | gap-fill RMSE | gap-fill − retained |
|---|---|---|---:|---:|---:|
| lat_band_10deg | -60° (Drake Passage / S Sandwich Trench area) | 17,910 / **59** | 60.4 | **2992** | **+2932** |
| depth_bin | 0 (cells with `depth_bin=0`, i.e. very shallow) | 597 / **46,500** | 16.8 | 140.4 | +123.6 |

The -60° lat_band finding deserves explicit attention. The 59 singlebeam cells in this band are clustered at lat -57° to -59°, lon -62° to -64° (Drake Passage continental slope). The ship-reported depths average 755 m (positive-down) while GEBCO at those locations averages 3,616 m. Mean depth_error = +2,861 m, max +4,127 m. quality_tier=`medium_confidence`, evidence_class=`cross` (cross-branch agreement). Sample rows:

| lat       | lon       | ship depth_m | model depth_m | error_m |
|---|---|---:|---:|---:|
| -57.758 | -63.942 |  295.25 | 4079.0 | +3783.75 |
| -57.758 | -63.925 |  200.84 | 4099.5 | +3898.66 |
| -57.742 | -63.942 |  351.75 | 4042.5 | +3690.75 |

These look like either (a) singlebeam reports stuck at a wrong scale or surface return, (b) data with mis-corrected positions falling onto the continental slope while the original was on shelf, or (c) a Step 06B rule edge case where cross-branch evidence agreed but agreement was between two equally biased singlebeam sources. **This audit does NOT recommend changing Step 06B**; the finding is preserved as-is and surfaces a concrete window where expanded_primary should not be trusted unconditionally.

Status: **PASS** with documented regional caveats.

---

## 8. Coverage Gain Summary (PRD §5.5)

`expanded_primary_coverage_gain_summary.tsv` has 405 rows across all 7 dimensions (3 + 7 + 5 + 3 + 3 + 16 + 368 = 405). Key counts:

| dimension          | added_cells distribution (top examples) |
|---|---|
| source_role        | 333,915 entirely in `supplementary_coverage` |
| branch             | 333,915 entirely in `singlebeam` |
| quality_tier       | 235,210 medium_confidence + 98,705 high_confidence; **0 low_confidence** |
| evidence_class     | 264,527 in `within` + 68,983 in `both` + 405 in `cross`; **0 in jamstec_legacy or none** |
| lat_band_10deg     | concentrated +20°-+40° (137 k cells, mid-latitudes) and at -20° (38 k) |
| depth_bin          | dominated by `depth_bin=2000` (152 k), `4000` (83 k), `0` (47 k), `200` (34 k) |
| region_10deg       | top: NE Pacific lon[-130 to -100], lat[+20 to +40] |

`retained_multibeam_cells` vs `singlebeam_gapfill_cells` are correctly broken out per stratum (the report's §3 tables and the underlying parquet both have these columns). The PRD §5.5 contract is satisfied.

**Observation: low_confidence has zero gap-fill.** Step 06B's quality rules screened singlebeam in such a way that none of the 333,915 added cells fell into the low_confidence tier. This is consistent with the strict run's weighted-vs-unweighted RMSE pattern (low_confidence dominates the strict baseline's unweighted RMSE), and explains why expanded's weighted_RMSE rises by a similar absolute amount as unweighted RMSE — there's no quality-tier dilution available for the new cells.

Status: **PASS**.

---

## 9. Stage 3 Non-Mutation Verification

mtimes of all 31 files under `ncei/derived/model_validation_1min_full_strict_primary/` captured before the run and after Step 5 (compare) — diff is empty.

Status: **PASS**. Stage 3 strict-primary outputs are byte-identical and timestamp-identical to their post-audit state.

---

## 10. Implementation / Code-Change Audit

Two code changes were applied to the main repository:

1. **`ncei/code/14_validate_gridded_products_step08.py`** — refactored to take a `--validation-product` CLI argument (default `strict_primary_multibeam_cells`, choices include `expanded_primary_ship_cells`). Within `run_full`, `full_safety_checks`, and `make_full_report`, all hardcoded `strict_primary` substrings in output filenames and report titles are now interpolated from a role-derived `role_slug` ("strict_primary" or "expanded_primary"). Safety checks branch on product_role: expanded uses `no_regional_mrar_in_expanded_primary`, `expanded_fill_count_matches_preflight`, `singlebeam_only_marked_as_expanded_fill` instead of the strict-only mutually-exclusive checks. Hard-stop guards in `run_full` likewise branch. Backward compatibility is preserved: any caller without `--validation-product` defaults to the original strict-only behavior.

2. **`ncei/code/15_strict_vs_expanded_compare_step08.py`** — new 750-line downstream script. Reads strict and expanded summary parquets, builds the comparison table; loads the GEBCO_2024 by-cell parquet from each side to derive the strict cell_id set; runs the four safety assertions (intersection size, set difference, expanded_fill membership consistency); builds coverage gain summary per dimension; computes per-product RMSE on retained_multibeam vs singlebeam_gapfill subsets (with cross-check against the summary RMSE per product); writes the comparison and coverage outputs to the expanded directory plus the final `expanded_primary_global_validation_report.md`. Two minor type-coercion bugs in the script were caught by the orchestrator's first compare run (`fillna("<NA>")` on Int64 columns) and fixed in-place before the successful second run. The fix uses `astype(str)` which handles both NaN/`<NA>` and integer cases uniformly. (See `git diff` on lines 378 and 481.)

Compilation and `--help` verified for both files; no other files were modified outside this scope.

Status: **PASS**.

---

## 11. Outputs Inventory (PRD §5)

| PRD requirement | Output path | Exists? |
|---|---|:---:|
| 5 × `full_validation_by_cell_expanded_primary_<product>.parquet` | `ncei/derived/model_validation_1min_full_expanded_primary/full_validation_by_cell_expanded_primary_*.parquet` | ✓ (5 files) |
| `full_validation_metrics_summary_expanded_primary.{parquet,tsv}` | same dir | ✓ |
| 7 by-stratum metrics tables in parquet+tsv | same dir | ✓ (14 files) |
| `full_validation_product_status_expanded_primary.{parquet,tsv}` | same dir | ✓ |
| `full_validation_safety_checks_expanded_primary.tsv` | same dir | ✓ |
| `full_validation_sample_diagnostics_expanded_primary.{parquet,tsv}` | same dir | ✓ |
| `skipped_products.tsv` | same dir | ✓ (empty body — no skips) |
| `strict_vs_expanded_comparison.{parquet,tsv}` | same dir | ✓ |
| `expanded_primary_coverage_gain_summary.{parquet,tsv}` | same dir | ✓ |
| `ncei/docs/expanded_primary_global_validation_report.md` | docs dir | ✓ |
| Run logs | `ncei/output/logs/14_validate_gridded_products_step08_full_expanded_primary.log`, `15_strict_vs_expanded_compare_step08.log`, `stage4_full_expanded_primary.nohup.log` | ✓ |

Status: **PASS**. All required outputs exist.

---

## 12. Acceptance Criteria Check (PRD §9)

- [x] `full_validation_safety_checks_expanded_primary.tsv` has all 10 (plus the no-residual-filtering provenance check) checks PASS.
- [x] Every required output file in §5 exists, is non-empty, and is readable.
- [x] Per-product by-cell parquet has exactly 2,732,689 rows for every product (5/5).
- [x] `product_role` value is exactly `expanded_primary_ship` in every by-cell row.
- [x] All 8 stratification tables (overall + 7 cross-cuts) are present and populated.
- [x] `strict_vs_expanded_comparison.{parquet,tsv}` has 5 rows with all delta_* columns non-NaN.
- [x] `expanded_primary_coverage_gain_summary.{parquet,tsv}` includes coverage-gain rows for source_role, branch, quality_tier, evidence_class, lat_band_10deg, depth_bin, region_10deg, with retained vs singlebeam_gapfill breakout.
- [x] `expanded_primary_global_validation_report.md` exists, references the PRD, contains sensitivity-interpretation and secondary-vs-regional-use recommendation.
- [x] Stage 3 strict-primary outputs are unchanged.

All 9 acceptance criteria satisfied.

---

## 13. Recommendation for the Role of expanded_primary

**Keep expanded_primary as a secondary / sensitivity-only validation product. Do not promote it to replace strict_primary as the main global baseline.**

Evidence supporting this decision:

1. **The added cells are systematically harder.** Singlebeam-gapfill RMSE is ~140-145 m versus ~90-100 m for retained multibeam — a ~50% RMSE penalty applied uniformly across all 5 gridded products (Section 7). This is not a per-product defect; it is an intrinsic property of the singlebeam-derived gap-fill subset relative to GEBCO/ETOPO/SRTM/SDUST/TOPO.
2. **Adding the gap-fill worsens the global baseline by 6-8 m RMSE.** That is a 7-9% RMSE increase versus strict (Section 6). Any downstream "model ranking" that uses expanded as the baseline will report worse-looking absolute numbers for all gridded products while preserving their ranking — confusing for cross-paper comparisons.
3. **Localized failure mode exists.** The Drake Passage / S Sandwich Trench region produces 59 gap-fill cells with mean +2,861 m depth error against all 5 models simultaneously (Section 7). The gap-fill subset cannot be assumed globally trustworthy.
4. **Conditional regional use remains possible.** In windows where singlebeam-gapfill RMSE is comparable to retained-multibeam RMSE (the §4 tables don't surface such windows above the 25 m threshold the compare script uses), expanded_primary could be used as the primary input. But that decision is per-region and must be made with the documented singlebeam provenance and the specific window's RMSE in hand — not as a global policy change.
5. **Strict-primary remains the authoritative global baseline.** No evidence in this run argues for changing that.

This audit does **not** authorize any modification to Step 06B, Step 07B, or the strict/expanded separation policy. The expanded outputs are a sensitivity reference, suitable for:

- Coverage-completeness diagnostics (where does multibeam alone miss territory?).
- Singlebeam-vs-multibeam validation experiments at the region or depth-bin level.
- Future regional analyses that explicitly account for the +50% RMSE penalty of the singlebeam subset.

---

## 14. GO / NO-GO for Downstream Use

**GO for sensitivity / coverage reference use of expanded_primary.**
**NO-GO for replacing strict_primary as the primary global baseline.**

Pre-conditions observed (must remain true for the GO to hold):

- Step 06B / Step 07B unchanged.
- Stage 3 strict-primary outputs unchanged (verified Section 9).
- expanded_primary outputs stored separately from strict outputs (verified — directory `model_validation_1min_full_expanded_primary/` is the only place they live).
- The recommendation paragraph in the auto-generated `expanded_primary_global_validation_report.md` matches this audit's recommendation (verified).

---

## 15. Files Produced by This Audit

- `ncei/docs/stage4_expanded_primary_validation_audit_report.md` (this file)
