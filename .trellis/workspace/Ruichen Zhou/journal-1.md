# Journal - Ruichen Zhou (Part 1)

> AI development session journal
> Started: 2026-05-10

---



## Session 1: NCEI Step 04A → Step 07B + PR-G task closure

**Date**: 2026-05-22
**Task**: NCEI Step 04A → Step 07B + PR-G task closure
**Branch**: `main`

### Summary

Built the back half of the NCEI singlebeam pipeline: 1-arcmin per-file aggregation (Step 04A), source-specific branch merge (Step 04B), within-branch (Step 05A) + cross-branch (Step 05B) overlap residual audits, quality policy calibration (Step 06A) + enforcement (Step 06B) with a 16-rule TSV + 1 invariant + 5 mandatory runtime assertions, and the 5 final validation-cell products (Step 07A preflight + Step 07B Path B implementation). Verified 23.6M cells covered, JAMSTEC × NCEI mb 0 overlap, AUV Sentry preserved at weight 0.55 with risk-class flags, weights NOT rescaled across legacy JAMSTEC vs Step 06B scales. Spec sections §13-§19 added/updated. Trellis tooling bumped 0.6.0-beta.7 → 0.6.0-beta.18 mid-session. PR-G audit verdict: READY (cross-cutting README, directory-structure, data-contracts docs refreshed).

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `7cecded` | (see git log) |
| `d8d9fe6` | (see git log) |
| `bad70f9` | (see git log) |
| `737664b` | (see git log) |
| `c376622` | (see git log) |
| `3af6f13` | (see git log) |
| `e020063` | (see git log) |
| `5a57931` | (see git log) |
| `df82f61` | (see git log) |
| `86316c1` | (see git log) |
| `5c5159a` | (see git log) |
| `d581b85` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete

---

## Session 2: Step 08 Stage 3 + Stage 4 — Strict-Primary full run, Stage 4 expanded-primary sensitivity

**Date**: 2026-05-26 → 2026-05-27
**Task**: `05-11-step-08-full-global-validation` (parent) + `05-27-stage4-expanded-primary-sensitivity` (child)
**Branch**: `main`

### Summary

Drove Step 08 from preflight through Stage 4 expanded-primary sensitivity.

Stage 3 (`strict_primary_multibeam_cells`, 2,398,774 cells × 5 global models, elapsed 2164 s): full-strict-primary run completed PASS; all 10 safety checks PASS; SDUST_2023 dominant in MAE/MAD/p95; the worst regions are uniformly NW Pacific subduction zones (lon0140_lat0020, lon0150_lat0020, lon0150_lat-020) across all 5 products; no sign-flip; weighted vs unweighted RMSE diff of 20-24% driven by the low_confidence quality tier (14% of cells but ~10× RMSE). Audit GO for Stage 4.

Stage 4 (`expanded_primary_ship_cells`, 2,732,689 cells = 2,398,774 retained multibeam + 333,915 singlebeam gap-fill × 5 global models, elapsed 2508 s validation + 45 s compare): created child task and Phase 1 planning (PRD + design + implement). Refactored `14_validate_gridded_products_step08.py` to take a `--validation-product` arg, with role-aware safety checks and parametric output naming (backward-compatible default = strict). Wrote new `15_strict_vs_expanded_compare_step08.py` via Pi worktree dispatch (Part B, 750 LOC) — first dispatch attempt failed (`stream_read_error` on 158 KB prompt in isolated mode); slimmed implement.jsonl to 49 KB and re-dispatched successfully; fixed two `fillna("<NA>").astype(str)` type-coercion bugs against Int64 columns post-apply. Stage 4 PASS on all 11 safety checks; coverage gain = 333,915 cells (13.9% over strict); retained_multibeam RMSE matched strict RMSE byte-equivalently (cross-check); singlebeam_gapfill RMSE 140-145 m (1.4-1.6× retained); overall RMSE rose 6-8 m per product; bias dropped uniformly ~2 m; Drake Passage / S Sandwich Trench is a documented outlier window (59 singlebeam cells, +2,861 m mean error against all 5 models simultaneously). Audit recommendation: GO for sensitivity / coverage use, NO-GO for replacing strict as the primary baseline.

Spec captured: role-aware Step 08 safety-check pattern and the "no model residual filtering" invariant. Parent task remains `in_progress` for Stages 5-6 (supplementary / regional diagnostics / final report) — Stage 4 child archived independently.

### Main Changes

- `ncei/code/14_validate_gridded_products_step08.py`: added `--validation-product` CLI arg, refactored `run_full` + `full_safety_checks` + `make_full_report` to consume product_role and a derived `role_slug`, branched the hard-stop guards and safety-check semantics on role. Backward compatibility preserved.
- `ncei/code/15_strict_vs_expanded_compare_step08.py` (new, 750 LOC): reads strict + expanded summary parquets, asserts cell-id intersection / gap-fill membership / expanded_fill flag consistency, computes per-stratum coverage gain (7 dimensions, 405 rows) + per-product retained-vs-gap-fill RMSE split, writes comparison + coverage TSVs/parquets + `expanded_primary_global_validation_report.md`.
- `ncei/docs/strict_primary_full_validation_audit_report.md` + 3 TSVs (Stage 3 audit) and `ncei/docs/stage4_expanded_primary_validation_audit_report.md` (Stage 4 audit).
- `.trellis/tasks/05-27-stage4-expanded-primary-sensitivity/`: PRD + design + implement + manifests for the Stage 4 child task.
- `.trellis/spec/backend/step08_role_aware_safety_checks.md` + `.trellis/spec/backend/step08_no_residual_filtering.md`: captured cross-stage spec lessons.

### Git Commits

| Hash | Message |
|------|---------|
| `45667cc` | step08: add full-global validation preflight and smoke runner |
| `1d327e6` | step08: run full strict-primary global validation |
| `(this commit)` | step08 Stage 3 + Stage 4: audit reports, expanded-primary sensitivity validation, role-aware refactor (cbf60ef) |

### Testing

- [OK] Stage 3 strict-primary full run: 5 products × 2,398,774 cells, all safety checks PASS
- [OK] Stage 4 expanded-primary full run: 5 products × 2,732,689 cells, all 11 safety checks PASS
- [OK] retained-multibeam RMSE matches strict to floating-point precision (compare-script cross-check)
- [OK] strict_vs_expanded_comparison: 5 product rows, all delta_* columns finite
- [OK] coverage_gain_summary: 405 rows across 7 stratification dimensions
- [OK] strict output mtimes unchanged before/after Stage 4
- [OK] Stage 3 + Stage 4 audits each produced an independent GO/NO-GO recommendation tied to specific evidence sections

### Status

[OK] **Stage 4 child completed**; parent task `05-11-step-08-full-global-validation` remains `in_progress` for Stages 5-6 (non-primary diagnostics + final report).

### Next Steps

- Optional Stage 5 (supplementary_singlebeam_cells coverage diagnostics).
- Optional Stage 6 (final cross-stage report tying strict + expanded together with policy decisions).
- Pi-adapter MCP / skill improvements queued: `_modelMapCache` invalidation on config.toml mtime change; prompt-size guard + `embed_context=false` opt-out; richer error surfacing when `output.log` is empty (full prompts in earlier exchange).

---

## Session 3: Step 08 Stage 5 — Non-primary coverage diagnostics

**Date**: 2026-05-27
**Task**: `05-11-step-08-full-global-validation`
**Branch**: `main`

### Summary

Completed Stage 5 non-primary diagnostics for the parent Step 08 task. Added `ncei/code/16_non_primary_coverage_diagnostics_step08.py`, a read-only full-product diagnostic runner that scans `supplementary_singlebeam_cells` and `regional_mrar_experiment_cells` without sampling gridded models or computing residuals. The run completed PASS with all 16 safety checks passing.

Key results: `supplementary_singlebeam_cells` has 12,277,633 unique cells, 8,751,456 low-evidence cells, and 878,575 expanded-primary cell-id overlaps; `regional_mrar_experiment_cells` has 9,019,383 unique cells, 9,015,418 `review_or_sensitivity_only` cells, and 574,347 expanded-primary cell-id overlaps. All overlaps are diagnostic only and do not promote non-primary products into strict-primary validation.

Stage 5 also clarified a Step 07B catalog contract: `validation_cell_catalog` intentionally has 12,611,548 `supplementary_singlebeam` catalog rows for 12,277,633 unique cell IDs because the 333,915 expanded-primary singlebeam gap-fill cells are included as expanded-primary membership rows.

### Main Changes

- `ncei/code/16_non_primary_coverage_diagnostics_step08.py`: new Stage 5 diagnostic runner with role-purity checks, primary-product exclusion checks, catalog unique-cell checks, per-product summaries, stratum summaries, overlap summaries, and report generation.
- `ncei/docs/step08_non_primary_diagnostics_report_stage5_non_primary.md`: Stage 5 PASS report.
- `ncei/derived/model_validation_1min_stage5_non_primary/`: machine-readable Stage 5 summaries and safety checks.
- `.trellis/spec/backend/data-contracts.md` and `.trellis/spec/backend/pipeline-design-decisions.md`: updated validation-cell catalog contract for intentional supplementary membership duplicates.
- Parent task metadata/context manifests updated for Stage 5 PASS.

### Testing

- [OK] `python -m py_compile ncei/code/16_non_primary_coverage_diagnostics_step08.py`
- [OK] `python ncei/code/16_non_primary_coverage_diagnostics_step08.py --run-label stage5_non_primary --confirm-full --overwrite`
- [OK] `non_primary_safety_checks.parquet`: 16 PASS, 0 FAIL
- [OK] Report status PASS and output summaries cross-checked against parquet/TSV artifacts

### Status

[OK] **Stage 5 completed**; parent task remains `in_progress` for Stage 6 final cross-stage report.

### Next Steps

- Stage 6 final report tying strict-primary, expanded-primary sensitivity, Stage 5 non-primary diagnostics, skipped models, and policy recommendations together.

---

## Session 4: Step 08 Stage 6 — Final global validation report

**Date**: 2026-05-27
**Task**: `05-11-step-08-full-global-validation`
**Branch**: `main`

### Summary

Completed Stage 6 final cross-stage report for the parent Step 08 task. Added `ncei/code/17_step08_final_global_validation_report.py`, a read-only report generator that consolidates existing Stage 3 strict-primary validation outputs, Stage 4 expanded-primary sensitivity outputs, and Stage 5 non-primary diagnostics. The run completed PASS and did not resample model grids or mutate validation products.

Final policy recommendation: use `strict_primary_multibeam_cells` as the authoritative global validation baseline; keep `expanded_primary_ship_cells` as a secondary sensitivity / coverage-expansion output; keep `supplementary_singlebeam_cells` as coverage diagnostics only; keep `regional_mrar_experiment_cells` as explicit regional sensitivity only; do not claim global `SWOT_T1` validation.

### Main Changes

- `ncei/code/17_step08_final_global_validation_report.py`: new Stage 6 report generator, with review hardening to assert retained/gap-fill attribution against Stage 4 coverage-gain counts, `expanded_fill` flags, and `ncei_singlebeam` source membership.
- `ncei/docs/step08_final_global_validation_report.md`: final cross-stage PASS report and recommendations.
- `ncei/derived/model_validation_1min_stage6_final/`: machine-readable stage outcomes, policy recommendations, and expanded gap-fill sensitivity summary.
- Parent task metadata/context manifests updated for Stage 6 PASS and final-review readiness.

### Testing

- [OK] `python -m py_compile ncei/code/17_step08_final_global_validation_report.py`
- [OK] `python ncei/code/17_step08_final_global_validation_report.py --run-label stage6_final --confirm-final --overwrite` (PASS 2026-05-27T18:02Z, elapsed 23.3s)
- [OK] `step08_stage_outcomes.tsv`: Stage 3, Stage 4, and Stage 5 all PASS with zero failed safety checks.
- [OK] `expanded_gapfill_sensitivity_summary.tsv`: retained strict-primary count = 2,398,774 and gap-fill count = 333,915 for all five completed global products.
- [OK] Stage 6 gap-fill attribution checks: retained count equals strict count, gap-fill count equals Stage 4 coverage gain, retained cells are not `expanded_fill`, and gap-fill cells are `ncei_singlebeam`.
- [OK] Final report recommendation matches Stage 3 / Stage 4 / Stage 5 evidence.

### Status

[OK] **Stage 6 completed**; parent task is ready for final review / closure and remains `in_progress` until explicitly finished or archived.

### Next Steps

- Review `ncei/docs/step08_final_global_validation_report.md`.
- Optionally finish/archive the Trellis parent task and commit the uncommitted Stage 5 / Stage 6 artifacts.

---

## Session 5: Step 08 followup — Ranking uncertainty + publication pack

**Date**: 2026-05-28
**Tasks**:
- Parent: `05-28-step08-ranking-uncertainty-and-pub`
- Children: A `05-28-step08-a-ranking-uncertainty`, B `05-28-step08-b-pub-tables`, C `05-28-step08-c-gapfill-error-structure`, D `05-28-step08-d-pub-figures`
**Branch**: `main`

### Summary

Built the Step 08 publication pack on top of the existing Stage 3/4/5/6 outputs. Quantified model ranking uncertainty via paired cluster block bootstrap (B=1000, 124 `region_10deg` clusters), produced publication-ready strict-primary and strict-vs-expanded metric tables, attributed the +6 to +8 m expanded-primary RMSE lift to the singlebeam gap-fill subset, and shipped 6 publication figures. Read-only over Step 06B / 07B / Step 08 Stage 3-6 products; no model resampling.

Sub-tasks A, B, C were implemented through Pi-adapter dispatch in isolated worktrees; D and the parent integration script were implemented directly by the main agent. The first A dispatch crashed with a Pi stream_read_error (no patch); a clean re-dispatch with 90 min timeout succeeded.

GEBCO_2024 holds rank-1 with 90.5% bootstrap probability under both RMSE and weighted RMSE. **GEBCO vs ETOPO is not significant at 95%** (ΔRMSE CI = [-4.28, +0.16] m, P(GEBCO better) = 90.6%); GEBCO vs every other model is significant. The expanded-primary RMSE lift is ~82% explained by the `quality_tier=medium_confidence` singlebeam subset (and by an overlapping low-latitude deep-overlap matched_rule_id), confirming that gap-fill is lower-quality singlebeam in known-difficult oceanographic regions rather than a method artifact.

### Main Changes

- `ncei/code/18_step08_ranking_bootstrap.py` — A: paired cluster block bootstrap over Stage 3 by-cell residuals; 19 safety PASS.
- `ncei/code/19_step08_publication_tables.py` — B: publication-ready strict-primary and strict-vs-expanded tables (TSV + CSV); 99 safety PASS.
- `ncei/code/20_step08_gapfill_error_structure.py` — C: 6 single-dim gap-fill RMSE slices + top-N attribution; 30+ safety PASS.
- `ncei/code/21_step08_publication_figures.py` — D: 6 publication figures (matplotlib + cartopy), each with figure-ready TSV + PNG + PDF; 8 safety PASS.
- `ncei/code/22_step08_publication_summary.py` — parent integration: 30 cross-check assertions (A↔B point/CI, B↔C gap-fill RMSE, B↔Stage 4 anchor) all PASS within 0.01 m tolerance.
- `ncei/docs/model_ranking_uncertainty_report.md` — A report.
- `ncei/docs/step08_gapfill_error_structure_report.md` — C report.
- `ncei/docs/publication_ready_step08_summary.md` — parent integration summary, single outward-facing document.
- `ncei/derived/model_validation_1min_step08_pub/` — 46 artifact files across `a_ranking_uncertainty/`, `b_pub_tables/`, `c_gapfill_structure/`, `d_figures/`, `summary/`.
- `.trellis/spec/backend/step08_publication_pack.md` (+ index entry) — bootstrap design, cross-task numerical cross-check, publication output layout, fixed figure colors.
- 5 Trellis task directories archived under `.trellis/tasks/archive/2026-05/`.

### Testing

- [OK] All 5 scripts `python -m py_compile` PASS.
- [OK] All 5 scripts `--check-only` PASS in the main repo.
- [OK] Full A run: 1000 iters bootstrap, elapsed 10.2 s, 19 safety PASS, all 15 (model × metric) CIs cover the point estimate.
- [OK] Full B run: elapsed 4.1 s, 99 safety PASS; strict_count = 2,398,774 and expanded_count = 2,732,689 hit exactly; RMSE / wRMSE / coverage gain match Stage 6 / Stage 4 numbers exactly.
- [OK] Full C run: elapsed 32.3 s, 0 safety FAIL / 0 WARN; retained RMSE matches strict-primary baseline exactly per model; top-20 contributors include `quality_tier=medium_confidence` at ~82% of total gap-fill sumsq for every model.
- [OK] Full D run: elapsed 3.84 s, 8 safety PASS / 0 WARN; F5 / F6 cartopy maps rendered.
- [OK] Parent integration run: cross-check PASS = 30, FAIL = 0; summary md written; manifest covers 46 artifacts.

### Status

[OK] **Step 08 followup pack complete**; A/B/C/D sub-tasks and parent task archived. Pending: single Phase 3.4 commit covering scripts, reports, derived outputs, archived task directories, spec update, and this journal entry.

### Next Steps

- Phase 3.4 commit (single staged commit referencing the parent task path).
- Future: SWOT_T1 regional validation task (Stage 6 final report's flagged remaining work).



## Session 3: SCS ship sounding QC v2 preflight

**Date**: 2026-08-05
**Task**: SCS ship sounding QC v2 preflight
**Branch**: `main`

### Summary

Built and independently verified immutable candidate, raw-context, control, aggregation, reference-conflict, and metadata evidence; task remains active pending collaborator decisions before correction.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `a4c7516` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: SCS MRAR/JAMSTEC lineage exact replay v2

**Date**: 2026-08-06
**Task**: SCS MRAR/JAMSTEC lineage exact replay v2
**Branch**: `main`

### Summary

Produced and independently verified immutable run 20260805T182211Z for 174,965 frozen SCS cells: 22,859,691 raw-point contributions, exact file/cruise/cell replay, 58-file JAMSTEC capability ceiling, terminal MRAR identity evidence, and exact 52/2,658/2,472/9 closures. Three batch/order/worker variants had identical canonical digests and zero mismatches. Verification status pass; no model/product error read and no correction or data-role decision.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `251f4b6` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 5: SCS v2 Stage B opaque sealed acquisition

**Date**: 2026-08-06
**Task**: SCS v2 Stage B opaque sealed acquisition
**Branch**: `main`

### Summary

Acquired the frozen four-cruise 768-object set as 9,626,893,507 opaque bytes via the user-selected 2082/HK-DC route; independent verification passed 768 Last-Modified closures and 768 reopened SHA256 checks. Retained one prior failed_unsealed pre-body proxy attempt. Stage C remains unauthorized.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `84287ac` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
