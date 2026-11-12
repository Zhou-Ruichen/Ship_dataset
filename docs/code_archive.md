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

## Streaming swath replacement (2026-11-12)

Last commit containing the removed code: `1900142`. This snapshot retains
the quality and navigation commands referenced in
`.trellis/tasks/10-25-ship-processing-repair/swath_result.md`.
Use `git show 1900142:<path>` to inspect the retained source version.
Existing products remain on disk. The current entry point is
`python -m ncei.swath {census,run,points,coverage}`.

| Removed path or code | Purpose | Retained products and reports |
| --- | --- | --- |
| `ncei/swath/batch.py` | Staging-to-L1/L2 batch orchestration | `processing_revision_20261025/swath/{first_batch,navigation_affected_extension}` |
| `ncei/swath/extract.py` | Raw-to-staging extraction and two L1 tables | `mb_round2/*/{_staging,points_raw,points_checked}`; 10-25 source reconstruction |
| `ncei/swath/file_cells.py` | Stage-35 L2 wrapper | `mb_round2/*/file_cells_1min` |
| `ncei/swath/manifest_fragment.py` | Stage-36 standalone source fragment | `mb_round2/mb_round2_source_manifest_fragment.*` |
| `ncei/swath/quality_revision.py` | Fixed first-batch revision and seamount comparison | `mb_round2/_runs/20261021_quality_revision` |
| `ncei/swath/navigation_revision.py` | Six-cruise source-navigation revision comparison | `processing_revision_20261025/swath/*comparison*` |
| `ncei/swath/navigation_review.py` | Two confirmed-invalid source-navigation cases | `processing_revision_20261025/swath/navigation_review*` |
| `_common/mbsystem.py` U3/U0-to-raw parquet and SQLite join helpers | Parse/join staging input for the removed extractor | Historical staging above; source-ping parser remains in `_common/mbsystem.py` |

The obsolete extraction API (`extract.process_one_file`, `extract.merge_cruise`,
and `_common.mbsystem.raw_from_object`) was also imported by
`/mnt/data2/06-Projects/11-swot-ssl-encoder/scripts/process_ew0202_v1.py`.
Its last available source snapshot is the pre-deletion HEAD `1900142`.
Future source reconstruction uses `python -m ncei.swath run` or
`python -m ncei.swath points`.

Old command aliases 33/34/35/36/37/43 were removed with their dispatch entries.
The format census and coverage modules were replaced in place to read the
new source and L2 layout.

## Frozen analyses and R2 calibration (2026-11-12)

Last commit containing the removed files: `1900142`. Reports, products and
figures remain in place; `git show 1900142:<path>` restores the source.

| Path | Purpose | produced_results | evidence | Last containing commit |
|---|---|---|---|---|
| `ncei/analysis/14_validate_gridded_products_step08.py` | Step08 preflight/smoke/full model validation | strict/expanded global validation metrics | `ncei/analysis/14_validate_gridded_products_step08.py:L64-L99,L255-L263,L1310-L1386` | `1900142` |
| `ncei/analysis/15_strict_vs_expanded_compare_step08.py` | Step08 strict versus expanded sensitivity | strict/expanded coverage and RMSE comparison | `ncei/analysis/15_strict_vs_expanded_compare_step08.py:L46-L88,L670-L723` | `1900142` |
| `ncei/analysis/16_non_primary_coverage_diagnostics_step08.py` | Step08 non-primary coverage diagnostics | supplementary SB and regional MRAR diagnostics | `ncei/analysis/16_non_primary_coverage_diagnostics_step08.py:L64-L98,L785-L796` | `1900142` |
| `ncei/analysis/17_step08_final_global_validation_report.py` | Step08 final report and policy tables | Step08 final ranking/policy anchor | `ncei/analysis/17_step08_final_global_validation_report.py:L54-L65,L618-L630` | `1900142` |
| `ncei/analysis/18_step08_ranking_bootstrap.py` | paired cluster bootstrap ranking uncertainty | 1,000-iteration CIs/rank probabilities | `ncei/analysis/18_step08_ranking_bootstrap.py:L64-L99,L683-L775` | `1900142` |
| `ncei/analysis/19_step08_publication_tables.py` | Step08 publication tables | publication strict/comparison tables | `ncei/analysis/19_step08_publication_tables.py:L101-L151` | `1900142` |
| `ncei/analysis/20_step08_gapfill_error_structure.py` | Step08 gap-fill error attribution | gap-fill RMSE attribution | `ncei/analysis/20_step08_gapfill_error_structure.py:L51-L71,L621-L630` | `1900142` |
| `ncei/analysis/21_step08_publication_figures.py` | Step08 publication figures/data | six Step08 publication figures | `ncei/analysis/21_step08_publication_figures.py:L54-L65,L130-L166,L527-L592` | `1900142` |
| `ncei/analysis/22_step08_publication_summary.py` | Step08 publication summary/manifest | publication_ready_step08_summary.md | `ncei/analysis/22_step08_publication_summary.py:L48-L56,L401-L452,L457-L537` | `1900142` |
| `ncei/analysis/27_sb_crossover_network_bias_1min.py` | crossover-network constant-offset prototype | network 61.64 m versus Step23 23.86 m heldout median abs residual | `ncei/analysis/27_sb_crossover_network_bias_1min.py:L24-L31,L130-L142`; `.trellis/tasks/archive/2026-09/09-03-sb-network-bias-prototype/result.md:L21-L45` | `1900142` |
| `ncei/analysis/29_sb_interpolation_holdout.py` | GMT interpolation holdout for SB value | 1,840.89 -> 731.12 -> 673.19 m old-control pooled RMSE | `ncei/analysis/29_sb_interpolation_holdout.py:L36-L65,L430-L489`; `docs/数据产品规范与下游接入.md:L170-L180` | `1900142` |
| `ncei/analysis/seamount_candidate_delivery.py` | 58-seamount candidate point/90 km cell delivery | 29,356,223 delivered points and complete candidate-cell tables | `ncei/analysis/seamount_candidate_delivery.py:L30-L36,L664-L697`; `.trellis/tasks/10-21-mb-round2-quality-revision/result.md:L573-L610` | `1900142` |
| `_common/r2_calibration.py` | one-off R2 threshold calibration driver | calibration tables used to freeze classifier | `_common/r2_calibration.py:L39-L58,L298-L348` | `1900142` |
| `_common/calibration/r2_borderline.csv` | R2 borderline calibration table | 129-line calibration evidence | `_common/calibration/r2_borderline.csv:L1` | `1900142` |
| `_common/calibration/r2_borderline.png` | R2 calibration scatter figure | borderline density/bbox figure | `_common/calibration/r2_borderline.png (binary); _common/r2_calibration.py:L56-L58` | `1900142` |
| `_common/calibration/r2_calibration_summary.txt` | R2 calibration summary | frozen-threshold summary | `_common/calibration/r2_calibration_summary.txt:L1` | `1900142` |
| `_common/calibration/r2_hard_mb_files.csv` | hard multibeam calibration examples | 12 hard-MB records plus header | `_common/calibration/r2_hard_mb_files.csv:L1` | `1900142` |
| `_common/tests/fixtures/scs_v2_stage_c1/MGL1104-9999-eight-ping.mb58` | MB58 eight-ping binary fixture | archived SCS test input | `_common/tests/fixtures/scs_v2_stage_c1/MGL1104-9999-eight-ping.mb58:L1`; `_common/README.md:L45-L47` | `1900142` |
| `_common/tests/fixtures/scs_v2_stage_c1/golden_provenance.json` | SCS fixture provenance | archived SCS test input | `_common/tests/fixtures/scs_v2_stage_c1/golden_provenance.json:L1`; `_common/README.md:L45-L47` | `1900142` |
| `_common/tests/fixtures/scs_v2_stage_c1/synthetic_all_u3.tsv` | synthetic U3 listing fixture | archived SCS test input | `_common/tests/fixtures/scs_v2_stage_c1/synthetic_all_u3.tsv:L1`; `_common/README.md:L45-L47` | `1900142` |
| `_common/tests/fixtures/scs_v2_stage_c1/synthetic_good_u0.tsv` | synthetic U0 listing fixture | archived SCS test input | `_common/tests/fixtures/scs_v2_stage_c1/synthetic_good_u0.tsv:L1`; `_common/README.md:L45-L47` | `1900142` |
| `_common/tests/fixtures/scs_v2_stage_c1a/synthetic_invalid_time_u0.tsv` | invalid-time U0 fixture | archived SCS test input | `_common/tests/fixtures/scs_v2_stage_c1a/synthetic_invalid_time_u0.tsv:L1`; `_common/README.md:L45-L47` | `1900142` |
| `_common/tests/fixtures/scs_v2_stage_c1a/synthetic_invalid_time_u3.tsv` | invalid-time U3 fixture | archived SCS test input | `_common/tests/fixtures/scs_v2_stage_c1a/synthetic_invalid_time_u3.tsv:L1`; `_common/README.md:L45-L47` | `1900142` |
| `_common/tests/fixtures/scs_v2_stage_c1a/synthetic_missing_time_u3.tsv` | missing-time U3 fixture | archived SCS test input | `_common/tests/fixtures/scs_v2_stage_c1a/synthetic_missing_time_u3.tsv:L1`; `_common/README.md:L45-L47` | `1900142` |

## Trackline consolidation (2026-11-12)

One entry point `python -m ncei.trackline` with 19 commands; equivalence
checks in `.trellis/tasks/11-12-ship-refactor/research/trackline_refactor_check.md`.
Last commit containing the removed or renamed files: `1900142`.

| 原路径 | 用途 | 产出产品或报告 | 最后包含提交（删除前 HEAD） |
| --- | --- | --- | --- |
| `ncei/trackline/policy_audit.py` | 探索并校准候选质量规则 | `ncei/derived/quality_policy_calibration_1min/` 下的校准表和候选规则；`ncei/docs/step06a_quality_policy_calibration_report.md` | `1900142929166fd19cd272ab02716e4ae4d73f22` |
| `ncei/trackline/mgd77t_xyz.py` | 旧静态 MGD77T 三列 XYZ 转换 | `ncei/raw_round2/mgd77t_static_xyz/` 与 `conversion_manifest.parquet` | `1900142929166fd19cd272ab02716e4ae4d73f22` |
| `ncei/trackline/mgd77t_fragments.py` | 默认 XYZ 分支生产独立点表、格网和来源清单；完整来源分支入口迁至 `mgd77t_points.py` | `ncei/derived/sb_round2_static/`；`sb_round2_static_source_manifest_fragment.parquet` | `1900142929166fd19cd272ab02716e4ae4d73f22` |
| `ncei/trackline/legacy_faa_revision.py` | 原 15 航次 FAA 重建、原字段对照、已用位置重映射及追加来源清点；显式清单转换迁至 `mgd77t_faa.py` | `ncei/derived/processing_revision_20261025/legacy_faa/`；`.trellis/tasks/10-25-ship-processing-repair/legacy_faa_result.md` | `1900142929166fd19cd272ab02716e4ae4d73f22` |
| `ncei/trackline/source_overlap.py` | 分支内文件格重叠残差，迁至 `quality_overlap.py` | `ncei/derived/overlap_bias_1min/`；`ncei/docs/step05a_source_specific_overlap_bias_report.md` | `1900142929166fd19cd272ab02716e4ae4d73f22` |
| `ncei/trackline/branch_overlap.py` | 分支间共址格深度对照，迁至 `quality_overlap.py` | `ncei/derived/cross_branch_overlap_1min/`；`ncei/docs/step05b_cross_branch_overlap_audit_report.md` | `1900142929166fd19cd272ab02716e4ae4d73f22` |
| `ncei/trackline/apply_policy.py` | 执行批准的质量规则，迁至 `quality_policy.py` | `ncei/derived/quality_flags_1min/`；`ncei/docs/step06b_cell_quality_flags_report.md` | `1900142929166fd19cd272ab02716e4ae4d73f22` |
| `ncei/trackline/mgd77t_source_fields.py` | 完整 MGD77T 来源字段、质量选择与历史对照，迁至 `mgd77t_points.py` | `ncei/derived/processing_revision_20261025/trackline/`；`.trellis/tasks/10-25-ship-processing-repair/mgd77t_result.md` | `1900142929166fd19cd272ab02716e4ae4d73f22` |

## JAMSTEC multibeam package (2026-11-12)

Entry point `python -m jamstec.multibeam`; equivalence checks in
`.trellis/tasks/11-12-ship-refactor/research/jamstec_refactor_check.md`.
Last commit containing the removed or moved files: `1900142`.

| Path | Purpose | Products / reports | Last commit |
|---|---|---|---|
| `jamstec/multibeam/analysis/08_validate_gridded_products_against_ship_cells.py` | JAMSTEC primary/sensitivity cells 的全球地形产品采样、验证和报告；也是 NCEI Step 08 `14` 动态加载的 sampler | `jamstec/multibeam/derived/model_validation_1min/`；配置 `configs/gridded_products_validation.yaml`；NCEI Step 08 v1.0 结果记录 | `1900142` |
| `jamstec/multibeam/analysis/09_analyze_model_validation_errors_T1.py` | SWOT T1 与全球产品的误差、偏差分解和深部/质量分层分析 | `derived/model_validation_T1_error_analysis/`；`docs/experiments/2026-05_swot_t1_residual_baseline.md` | `1900142` |
| `jamstec/multibeam/analysis/09_batch_validate_swot_t1.py` | 批量重建 SWOT T1 绝对预测并与船测格及全球产品比较 | `derived/swot_t1_batch_validation/`；上述 SWOT T1 结果记录 | `1900142` |
| `jamstec/multibeam/analysis/10_build_ship_supervised_residual_dataset_T1.py` | 生成船测监督的 T1 残差数据集和初始空间划分 | `derived/ship_supervised_residual_T1/ship_residual_dataset_T1*.parquet`、split manifest 与报告 | `1900142` |
| `jamstec/multibeam/analysis/10b_generate_stratified_spatial_splits_T1.py` | 优化分层空间块划分并生成推荐的 0.25° split | `derived/ship_supervised_residual_T1/splits/`；split comparison/report | `1900142` |
| `jamstec/multibeam/analysis/11_train_residual_baselines_T1.py` | 训练和评价 T1 残差基线模型 | `derived/ship_supervised_residual_T1/baselines_block025/`；`docs/experiments/2026-05_swot_t1_residual_baseline.md` | `1900142` |
| `jamstec/multibeam/analysis/plot_multibeam_figures.py` | 生成 JAMSTEC 质量、覆盖和模型验证图 | `jamstec/multibeam/figures/fig01_*.png` 至 `fig11_*.png`，全部保留 | `1900142` |


| Old path at `1900142` | New path |
|---|---|
| `jamstec/multibeam/code/01_extract_subzips.sh` | `jamstec/multibeam/source/extract_subzips.sh` |
| `jamstec/multibeam/code/02_check_subzips.sh` | `jamstec/multibeam/source/check_subzips.sh` |
| `jamstec/multibeam/code/03_recursive_extract.py` | `jamstec/multibeam/source/recursive_extract.py` |
| `jamstec/multibeam/code/04_organize_dat.sh` | `jamstec/multibeam/source/organize_dat.sh` |
| `jamstec/multibeam/code/01_build_multibeam_manifest.py` | `jamstec/multibeam/manifest.py` |
| `jamstec/multibeam/code/02a_curate_points_manifest.py` | `jamstec/multibeam/curate.py` |
| `jamstec/multibeam/code/02_standardize_multibeam_xyz.py` | `jamstec/multibeam/standardize.py` |
| `jamstec/multibeam/code/03_qc_multibeam_points.py` | `jamstec/multibeam/point_qc.py` |
| `jamstec/multibeam/code/04a_make_multibeam_file_cells.py` | `jamstec/multibeam/file_cells.py` |
| `jamstec/multibeam/code/04b_merge_multibeam_cells.py` | `jamstec/multibeam/merge_cells.py` |
| `jamstec/multibeam/code/05_analyze_cell_overlap_bias.py` | `jamstec/multibeam/overlap.py` |
| `jamstec/multibeam/code/06a_investigate_extreme_bias_sources.py` | `jamstec/multibeam/extreme_bias.py` |
| `jamstec/multibeam/code/06b_create_file_quality_flags_1min.py` | `jamstec/multibeam/file_quality.py` |
| `jamstec/multibeam/code/06c_rebuild_cells_1min_qcfiltered.py` | `jamstec/multibeam/qcfiltered_cells.py` |
| `jamstec/multibeam/code/07_prepare_primary_validation_cells_1min.py` | `jamstec/multibeam/validation_cells.py` |
| `jamstec/multibeam/analysis/06d_compare_original_vs_qcfiltered_cells.py` | `jamstec/multibeam/compare_cells.py` |
