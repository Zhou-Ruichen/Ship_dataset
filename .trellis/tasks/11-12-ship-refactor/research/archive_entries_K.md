# K：JAMSTEC 归档索引条目

删除前 HEAD / 最后包含提交：
`1900142929166fd19cd272ab02716e4ae4d73f22`（`1900142`）。
可用 `git show 1900142:<path>` 读取。以下代码均产出过已保留的结果；本表供主代理合并进 `docs/code_archive.md`。

## 归档删除

| Path | Purpose | Products / reports | Last commit |
|---|---|---|---|
| `jamstec/multibeam/analysis/08_validate_gridded_products_against_ship_cells.py` | JAMSTEC primary/sensitivity cells 的全球地形产品采样、验证和报告；也是 NCEI Step 08 `14` 动态加载的 sampler | `jamstec/multibeam/derived/model_validation_1min/`；配置 `configs/gridded_products_validation.yaml`；NCEI Step 08 v1.0 结果记录 | `1900142` |
| `jamstec/multibeam/analysis/09_analyze_model_validation_errors_T1.py` | SWOT T1 与全球产品的误差、偏差分解和深部/质量分层分析 | `derived/model_validation_T1_error_analysis/`；`docs/experiments/2026-05_swot_t1_residual_baseline.md` | `1900142` |
| `jamstec/multibeam/analysis/09_batch_validate_swot_t1.py` | 批量重建 SWOT T1 绝对预测并与船测格及全球产品比较 | `derived/swot_t1_batch_validation/`；上述 SWOT T1 结果记录 | `1900142` |
| `jamstec/multibeam/analysis/10_build_ship_supervised_residual_dataset_T1.py` | 生成船测监督的 T1 残差数据集和初始空间划分 | `derived/ship_supervised_residual_T1/ship_residual_dataset_T1*.parquet`、split manifest 与报告 | `1900142` |
| `jamstec/multibeam/analysis/10b_generate_stratified_spatial_splits_T1.py` | 优化分层空间块划分并生成推荐的 0.25° split | `derived/ship_supervised_residual_T1/splits/`；split comparison/report | `1900142` |
| `jamstec/multibeam/analysis/11_train_residual_baselines_T1.py` | 训练和评价 T1 残差基线模型 | `derived/ship_supervised_residual_T1/baselines_block025/`；`docs/experiments/2026-05_swot_t1_residual_baseline.md` | `1900142` |
| `jamstec/multibeam/analysis/plot_multibeam_figures.py` | 生成 JAMSTEC 质量、覆盖和模型验证图 | `jamstec/multibeam/figures/fig01_*.png` 至 `fig11_*.png`，全部保留 | `1900142` |

`06d_compare_original_vs_qcfiltered_cells.py` 不在删除组：它移为生产模块
`jamstec/multibeam/compare_cells.py`，其 common/lost-cell 表仍被 07 读取。

## 移动路径对照

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
