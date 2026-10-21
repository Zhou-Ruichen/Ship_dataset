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
| `ncei/code/01_build_trackline_source_manifest.py` | `ncei/trackline/manifest.py` (`manifest`, alias `01`) |
| `ncei/code/02_standardize_singlebeam.py` | `ncei/trackline/standardize_singlebeam.py` (`standardize-nc`, alias `02`) |
| `ncei/code/03_standardize_xyz.py` | `ncei/trackline/standardize_xyz.py` (`standardize-xyz`, alias `03`) |
| `ncei/code/04_clean_mrar.py` | `ncei/trackline/clean_mrar.py` (`clean-mrar`, alias `04`) |
| `ncei/code/05_point_quality_check.py` | `ncei/trackline/point_qc.py` (`point-qc`, alias `05`) |
| `ncei/code/06_supplementary_quality_check.py` | `ncei/trackline/supplementary_qc.py` (`supplementary-qc`, alias `06`) |
| `ncei/code/07_aggregate_file_cells_1min.py` | `ncei/trackline/file_cells.py` (`file-cells`, alias `07`) |
| `ncei/code/08_merge_branch_cells_1min.py` | `ncei/trackline/merge_cells.py` (`merge-cells`, alias `08`) |
| `ncei/code/09_source_specific_overlap_residuals.py` | `ncei/trackline/source_overlap.py` (`source-overlap`, alias `09`) |
| `ncei/code/10_cross_branch_overlap_audit.py` | `ncei/trackline/branch_overlap.py` (`branch-overlap`, alias `10`) |
| `ncei/code/11_quality_policy_calibration_audit.py` | `ncei/trackline/policy_audit.py` (`policy-audit`, alias `11`) |
| `ncei/code/12_apply_quality_policy.py` | `ncei/trackline/apply_policy.py` (`apply-policy`, alias `12`) |
| `ncei/code/13_build_validation_cells.py` | `ncei/trackline/validation_cells.py` (`validation-cells`, alias `13`) |
| `ncei/code/23_estimate_singlebeam_track_bias_1min.py` | `ncei/trackline/track_bias.py` (`track-bias`, alias `23`) |
| `ncei/code/24_true_crossover_audit.py` | `ncei/trackline/crossover.py` (`crossover`, alias `24`) |
| `ncei/code/25_global_singlebeam_track_bias.py` | `ncei/trackline/global_bias.py` (`global-bias`, alias `25`) |
| `ncei/code/26_global_singlebeam_crossover_audit.py` | `ncei/trackline/global_crossover.py` (`global-crossover`, alias `26`) |
| `ncei/code/28_sb_track_quality_disposition_1min.py` | `ncei/trackline/disposition.py` (`disposition`, alias `28`) |
| `ncei/code/30_global_sb_track_disposition.py` | `ncei/trackline/global_disposition.py` (`global-disposition`, alias `30`) |
| `ncei/code/31_build_global_grid_1min.py` | `ncei/trackline/global_grid.py` (`global-grid`, alias `31`) |
| `ncei/code/33_mb_round2_format_survey.py` | `ncei/swath/census.py` (`census`, alias `33`) |
| `ncei/code/34_mb_round2_extract_points.py` | `ncei/swath/extract.py` (`extract`, alias `34`) |
| `ncei/code/35_mb_round2_file_cells.py` | `ncei/swath/file_cells.py` (`file-cells`, alias `35`) |
| `ncei/code/36_mb_round2_source_manifest_fragment.py` | `ncei/swath/manifest_fragment.py` (`manifest`, alias `36`) |
| `ncei/code/37_mb_round2_coverage_stats.py` | `ncei/swath/coverage.py` (`coverage`, alias `37`) |
| `ncei/code/38_mbbdb_value_ranking.py` | `ncei/download/rank.py` (`rank`, alias `38`) |
| `ncei/code/39_m77t_to_xyz.py` | `ncei/trackline/mgd77t_xyz.py` (`mgd77t-xyz`, alias `39`) |
| `ncei/code/40_m77t_static_fragments.py` | `ncei/trackline/mgd77t_fragments.py` (`mgd77t-fragments`, alias `40`) |
| `ncei/code/43_mb_round2_quality_revision.py` | `ncei/swath/quality_revision.py` (`quality-revision`, alias `43`) |
| `jamstec/multibeam/code/06d_compare_original_vs_qcfiltered_cells.py` | `jamstec/multibeam/analysis/06d_compare_original_vs_qcfiltered_cells.py` |
| `jamstec/multibeam/code/08_validate_gridded_products_against_ship_cells.py` | `jamstec/multibeam/analysis/08_validate_gridded_products_against_ship_cells.py` |
| `jamstec/multibeam/code/09_analyze_model_validation_errors_T1.py` | `jamstec/multibeam/analysis/09_analyze_model_validation_errors_T1.py` |
| `jamstec/multibeam/code/09_batch_validate_swot_t1.py` | `jamstec/multibeam/analysis/09_batch_validate_swot_t1.py` |
| `jamstec/multibeam/code/10_build_ship_supervised_residual_dataset_T1.py` | `jamstec/multibeam/analysis/10_build_ship_supervised_residual_dataset_T1.py` |
| `jamstec/multibeam/code/10b_generate_stratified_spatial_splits_T1.py` | `jamstec/multibeam/analysis/10b_generate_stratified_spatial_splits_T1.py` |
| `jamstec/multibeam/code/11_train_residual_baselines_T1.py` | `jamstec/multibeam/analysis/11_train_residual_baselines_T1.py` |
| `jamstec/multibeam/code/plot_multibeam_figures.py` | `jamstec/multibeam/analysis/plot_multibeam_figures.py` |
