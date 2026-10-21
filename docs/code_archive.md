# Code archive index

Scripts removed from the working tree during repository reorganization are
registered here. To inspect a removed script, run `git show bc4cd36:<path>`;
to restore it, run `git checkout bc4cd36 -- <path>`. Historical reports and
product manifests written before the reorganization reference the old paths
recorded below.

## Removed code

Last commit containing all entries: `bc4cd36` (2026-10-21 pre-reorganization
checkpoint).

| Path (at `bc4cd36`) | Purpose | Products / reports it produced or modified | Last commit |
|---|---|---|---|
| `jamstec/multibeam/code/05_cleanup.sh` | Delete intermediate `.dat` scratch files after extraction | none (disk cleanup only) | `bc4cd36` |
| `scripts/refactor/rewrite_paths.py` | One-shot path-string rewriter for the 2026-05 JAMSTEC/NCEI directory rename (task 05-11) | renamed doc/config paths during PR-A/PR-B; no data products | `bc4cd36` |
| `ncei/code/42_backfill_product_manifests.py` | One-shot backfill of `product_manifest.json` into first-delivery product directories | `ncei/derived/{file_cells_1min_final_r2,points_checked,...}/product_manifest.json` (`backfilled_by` fields); documented in `docs/数据产品规范与下游接入.md` §manifest 回填说明 | `bc4cd36` |
| `ncei/code/scs_confirmation/` (37 scripts + shared modules + README, ≈21,800 lines) | SCS/TN352 sealed-confirmation audit chain: discovery, acquisition, lineage/QC/consistency audits, Stage C source-internal processing and authorization, and their verifiers | sealed evidence under `ncei/derived/scs_v2_sealed_confirmation/` (63 GB, kept) and `ncei/archive/scs_v2_sealed_confirmation/`; reports in `.trellis/tasks/archive/2026-08/*scs*`; `ncei/docs/step14_next_step_decision_memo.md` records the chain's outcome | `bc4cd36` |
| `_common/tests/scs_confirmation/` (14 tests + `__init__.py`, ≈3,500 lines) | Unit tests for the SCS confirmation chain above | kept the chain's verifiers honest during 2026-08; no data products | `bc4cd36` |
| `_common/scs_v2_stage_c1_oracle.py` (166 lines) | Format-58 fixture oracle for Stage C.1 readiness verification | fixture verification records inside `ncei/derived/scs_v2_sealed_confirmation/stage_c_readiness/` | `bc4cd36` |
| `ncei/configs/scs_*.yaml` (7 files) | Run configuration for the SCS confirmation chain scripts | same sealed evidence as above; no other consumer | `bc4cd36` |

The mblist parsing/join helpers that `ncei/code/34_mb_round2_extract_points.py`
needed (`_raw_from_object`, `iter_mblist_rows`, `scan_time_contract`,
`ParquetAppender`, `RAW_SCHEMA`/`RawRow`, and `normalize_longitude` from the
Stage C.1 contract) were extracted before removal and now live in
`_common/mbsystem.py` (`raw_from_object`); behaviour is unchanged.

## Moved paths

Old → new locations from the 2026-10-21 reorganization. Use this table to
resolve old paths found in historical reports and product manifests.

| Old path | New path |
|---|---|
| `ncei/code/14_validate_gridded_products_step08.py` | `ncei/analysis/14_validate_gridded_products_step08.py` |
| `ncei/code/15_strict_vs_expanded_compare_step08.py` | `ncei/analysis/15_strict_vs_expanded_compare_step08.py` |
| `ncei/code/16_non_primary_coverage_diagnostics_step08.py` | `ncei/analysis/16_non_primary_coverage_diagnostics_step08.py` |
| `ncei/code/17_step08_final_global_validation_report.py` | `ncei/analysis/17_step08_final_global_validation_report.py` |
| `ncei/code/18_step08_ranking_bootstrap.py` | `ncei/analysis/18_step08_ranking_bootstrap.py` |
| `ncei/code/19_step08_publication_tables.py` | `ncei/analysis/19_step08_publication_tables.py` |
| `ncei/code/20_step08_gapfill_error_structure.py` | `ncei/analysis/20_step08_gapfill_error_structure.py` |
| `ncei/code/21_step08_publication_figures.py` | `ncei/analysis/21_step08_publication_figures.py` |
| `ncei/code/22_step08_publication_summary.py` | `ncei/analysis/22_step08_publication_summary.py` |
| `ncei/code/27_sb_crossover_network_bias_1min.py` | `ncei/analysis/27_sb_crossover_network_bias_1min.py` |
| `ncei/code/29_sb_interpolation_holdout.py` | `ncei/analysis/29_sb_interpolation_holdout.py` |
| `jamstec/multibeam/code/06d_compare_original_vs_qcfiltered_cells.py` | `jamstec/multibeam/analysis/06d_compare_original_vs_qcfiltered_cells.py` |
| `jamstec/multibeam/code/08_validate_gridded_products_against_ship_cells.py` | `jamstec/multibeam/analysis/08_validate_gridded_products_against_ship_cells.py` |
| `jamstec/multibeam/code/09_analyze_model_validation_errors_T1.py` | `jamstec/multibeam/analysis/09_analyze_model_validation_errors_T1.py` |
| `jamstec/multibeam/code/09_batch_validate_swot_t1.py` | `jamstec/multibeam/analysis/09_batch_validate_swot_t1.py` |
| `jamstec/multibeam/code/10_build_ship_supervised_residual_dataset_T1.py` | `jamstec/multibeam/analysis/10_build_ship_supervised_residual_dataset_T1.py` |
| `jamstec/multibeam/code/10b_generate_stratified_spatial_splits_T1.py` | `jamstec/multibeam/analysis/10b_generate_stratified_spatial_splits_T1.py` |
| `jamstec/multibeam/code/11_train_residual_baselines_T1.py` | `jamstec/multibeam/analysis/11_train_residual_baselines_T1.py` |
| `jamstec/multibeam/code/plot_multibeam_figures.py` | `jamstec/multibeam/analysis/plot_multibeam_figures.py` |
