# D — Publication-Ready Figures

## Goal

把 A/B/C 的聚合数据转成对外发表的图。环境已确认：matplotlib 3.10.3 与 cartopy 0.25.0 可用，PNG/PDF 可作为必选输出（不是 optional）。每张图额外写出 figure-ready TSV 作为数据真相。

## Scope

**In scope（6 张图）**

1. **F1 — 强主表 RMSE 对比柱状图**：strict-primary RMSE / weighted RMSE，5 个模型，并列双柱。
2. **F2 — Strict vs Expanded RMSE 对比图**：strict / expanded RMSE，5 个模型，并列双柱 + ΔRMSE 注释。
3. **F3 — 深度带 RMSE 曲线**：x = `depth_bin`，y = RMSE，5 模型 5 条曲线。来自 `full_validation_metrics_by_depth_bin_strict_primary.parquet`。
4. **F4 — 纬度带 RMSE 曲线**：x = `lat_band_10deg`，y = RMSE，5 模型 5 条曲线。来自 `full_validation_metrics_by_lat_band_10deg_strict_primary.parquet`。
5. **F5 — 10° 区域 RMSE 地图**：cartopy 全球底图，按 `region_10deg` 上色填充 GEBCO 的 RMSE（其他模型作为附图或仅出表）。
6. **F6 — Expanded gap-fill 覆盖增益地图**：cartopy 全球底图，按 `region_10deg` 上色显示 gap-fill cell 计数或占比。

**Out of scope**

- 不重做指标计算（D 任务从 A/B/C 聚合表读，不再算原始残差）。
- 不画 cell-level 散点图（百万行级别，对发表无意义）。
- 不出交互式 HTML（这是 markdown / PDF 输出场景）。

## Requirements

### R-D1 — 数据真相先于图

每张图必须先输出一份 `figure_data_F<N>.tsv`，是该图的精确输入。脚本随后从 TSV 读再画 PNG/PDF。这样：

- 图像 / 数据可独立审计。
- 协作者可用 R / Excel / 其他工具重画。
- 图脚本失败不影响表的可用性。

### R-D2 — 图样式约束

- 颜色：5 个模型固定色板，跨图保持一致。建议：
  - GEBCO_2024 → tab:blue
  - ETOPO_2022 → tab:orange
  - SRTM15_V2.7 → tab:green
  - TOPO_25.1 → tab:red
  - SDUST_2023 → tab:purple
- DPI：PNG 300，PDF 矢量。
- 字体：matplotlib 默认即可（DejaVu Sans）。无中文图，全部英文标签便于对外发表。
- Figure size：6×4 (单图) / 8×4 (双柱并排) / 10×6 (cartopy 地图)。

### R-D3 — 数值一致性

每张图的 RMSE / 计数必须与 A/B/C 表对应数值精确一致（误差 < 0.01）。脚本必须在写出前 assert。

### R-D4 — 约束

- 只读 A/B/C 输出与 Stage 3/4 现有聚合 parquet。
- 不修改上游产物。
- 脚本：`ncei/code/21_step08_publication_figures.py`。
- 显式开关：`--confirm-figures`、`--overwrite`、`--check-only`、`--skip-png`（仅输出 TSV，调试用）。
- 输出目录：`ncei/derived/model_validation_1min_step08_pub/d_figures/`，PNG/PDF 与 TSV 同目录。

### R-D5 — 顺序依赖

D 必须在 A/B/C 至少完成 B 之后才能运行（F1/F2 完全依赖 B；F3/F4 依赖 Stage 3 已存在表；F5/F6 依赖 Stage 3 / Stage 4 已存在表；最理想是 A/B/C 全部完成后再运行，以便 F1 可以叠加 A 的 CI 误差棒）。

**建议**：F1 在 A 完成后增强为带 95% CI 误差棒；如果 A 未完成则先出无误差棒版本（脚本支持两种模式 `--with-ci` / `--no-ci`）。

## Acceptance Criteria

- [ ] `ncei/code/21_step08_publication_figures.py` 存在并通过 `python -m py_compile`。
- [ ] 完整运行 PASS，6 张图各输出：
  - `figure_data_F<N>.tsv`
  - `F<N>_<short_title>.png` (300 dpi)
  - `F<N>_<short_title>.pdf` (矢量)
- [ ] `d_figures_safety_checks.tsv` 全部 PASS：
  - 每张图 TSV 与上游 A/B/C 数值一致（< 0.01）
  - PNG/PDF 文件存在且非空
  - color 编码命中固定模型→颜色映射
- [ ] F1 在 A 完成的前提下带 95% CI 误差棒；A 未完成则在文件名加 `_no_ci` 后缀。

## Inputs / Outputs

| Kind | Path |
|---|---|
| Input | `ncei/derived/model_validation_1min_step08_pub/b_pub_tables/strict_primary_publication_table.tsv` (F1) |
| Input | `ncei/derived/model_validation_1min_step08_pub/b_pub_tables/strict_vs_expanded_publication_table.tsv` (F2) |
| Input | `ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/model_metric_ci.tsv` (F1 with CI, optional) |
| Input | `ncei/derived/model_validation_1min_full_strict_primary/full_validation_metrics_by_depth_bin_strict_primary.parquet` (F3) |
| Input | `ncei/derived/model_validation_1min_full_strict_primary/full_validation_metrics_by_lat_band_10deg_strict_primary.parquet` (F4) |
| Input | `ncei/derived/model_validation_1min_full_strict_primary/full_validation_metrics_by_region_10deg_strict_primary.parquet` (F5) |
| Input | `ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/gapfill_slice_by_region_10deg.tsv` (F6) |
| Output dir | `ncei/derived/model_validation_1min_step08_pub/d_figures/` |
| Script | `ncei/code/21_step08_publication_figures.py` |

## Risk

- cartopy 底图依赖 `cartopy.feature.LAND` 等离线 shapefile，首次运行可能尝试下载 → 脚本应处理离线场景（catch + 优雅降级为无底图灰色方块格点）。
- F5/F6 地图按 `region_10deg` 着色：region_10deg 是字符串编码（如 `lon0080_lat-060`），需先 parse 出 (lon_bin, lat_bin) 才能画。脚本必须有 parsing helper + unit test。
- PNG/PDF 同时输出可能存在字体嵌入差异；PDF 优先矢量，PNG 用于 markdown 引用。

## Pi-adapter dispatch

不推荐（环境依赖性强：matplotlib / cartopy + 离线底图 + 颜色/字体校对）。建议 main agent 自做。
