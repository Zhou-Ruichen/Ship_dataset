# B — Publication-Ready Strict-Primary & Strict-vs-Expanded Tables

## Goal

把 Step 08 Stage 3 与 Stage 4 的现有指标重整为对外可发表的两张主表：

1. **strict-primary 模型评测表**：bias / MAE / RMSE / weighted MAE / weighted RMSE / median error / MAD / p95 abs error，5 个模型 × 8 指标。
2. **strict-vs-expanded 对比表**：coverage gain / ΔRMSE / Δweighted RMSE / gap-fill RMSE / retained multibeam RMSE，5 个模型。

是 A/C/D 的数值锚点。先于 A、C、D 完成（Wave 1，参见父 implement.md）。

## Scope

**In scope**

- 直接从 Stage 3 / Stage 4 / Stage 6 现成 parquet 与 by-cell 残差聚合。
- 输出 TSV + CSV 两种格式（TSV 主，CSV 便于 Excel）。
- 计算 median error、MAD、weighted MAE 与 p95 absolute error（现有 metrics summary 表里可能未直接含，需要从 by-cell 现算）。

**Out of scope**

- 不做 bootstrap（A 任务负责）。
- 不做切片归因（C 任务负责）。
- 不做绘图（D 任务负责）。

## Requirements

### R-B1 — Strict-primary 主表

输入：`ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_<MODEL>.parquet` × 5。

每个模型计算以下指标（基于 strict-primary 2,398,774 cell）：

| 指标 | 公式 |
|---|---|
| bias | mean(elev_error_m) |
| MAE | mean(abs_elev_error_m) |
| RMSE | sqrt(mean(elev_error_m^2)) |
| weighted MAE | sum(w * abs_elev_error_m) / sum(w) |
| weighted RMSE | sqrt(sum(w * elev_error_m^2) / sum(w)) |
| median error | median(elev_error_m) |
| MAD | median(abs(elev_error_m - median(elev_error_m))) |
| p95 abs error | quantile(abs_elev_error_m, 0.95) |
| n_cells | row count |

其中 `w = validation_weight`。

输出 `strict_primary_publication_table.tsv` / `.csv`，列固定为：
`model, n_cells, bias, MAE, RMSE, weighted_MAE, weighted_RMSE, median_error, MAD, p95_abs_error`。
行按 RMSE 升序（与现有 Stage 6 报告一致：GEBCO < ETOPO < SRTM15 < TOPO < SDUST）。

### R-B2 — Strict-vs-Expanded 对比表

输入：strict + expanded by-cell × 5 模型，以及 Stage 4 现有 coverage gain 表。

每个模型计算：

| 指标 | 来源 |
|---|---|
| strict_count | 直接 row count (2,398,774) |
| expanded_count | row count (2,732,689) |
| coverage_gain_count | expanded − strict (333,915) |
| coverage_gain_fraction | gain / strict (0.1392) |
| strict_RMSE | R-B1 |
| expanded_RMSE | RMSE on expanded by-cell |
| delta_RMSE | expanded − strict |
| strict_weighted_RMSE | R-B1 |
| expanded_weighted_RMSE | wRMSE on expanded by-cell |
| delta_weighted_RMSE | expanded − strict |
| retained_multibeam_RMSE | RMSE on expanded with expanded_fill==False |
| gapfill_singlebeam_RMSE | RMSE on expanded with expanded_fill==True |
| gapfill_to_retained_RMSE_ratio | gapfill / retained |

输出 `strict_vs_expanded_publication_table.tsv` / `.csv`。

### R-B3 — 数值一致性

- 所有 RMSE / wRMSE / coverage gain 必须与 Stage 6 报告 §3-§4 表格在同行同列上一致（误差容差 < 0.01）。
- 脚本必须在写出前做交叉对账（assert）。
- `strict_count = 2,398,774`、`expanded_count = 2,732,689`、`gap-fill = 333,915` 必须命中。

### R-B4 — 约束

- 只读输入；不重采模型；不修改上游产物。
- 脚本命名：`ncei/code/19_step08_publication_tables.py`。
- 显式开关：`--run-label`、`--confirm-publish`、`--overwrite`、`--check-only`。
- 输出目录：`ncei/derived/model_validation_1min_step08_pub/b_pub_tables/`。

## Acceptance Criteria

- [ ] `ncei/code/19_step08_publication_tables.py` 存在并通过 `python -m py_compile`。
- [ ] 完整运行 PASS，输出两份 TSV + 两份 CSV。
- [ ] `b_pub_safety_checks.tsv` 全部 PASS：
  - n_cells 命中 strict / expanded 期望值
  - RMSE/wRMSE 与 Stage 6 报告对账误差 < 0.01
  - coverage gain = 333,915
  - retained vs gap-fill 行数分别为 2,398,774 / 333,915
- [ ] 表格行按 RMSE 升序。
- [ ] CSV 与 TSV 内容完全一致（仅分隔符不同）。

## Inputs / Outputs

| Kind | Path |
|---|---|
| Input | `ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_<MODEL>.parquet` × 5 |
| Input | `ncei/derived/model_validation_1min_full_expanded_primary/full_validation_by_cell_expanded_primary_<MODEL>.parquet` × 5 |
| Input | `ncei/derived/model_validation_1min_full_strict_primary/full_validation_metrics_summary_strict_primary.parquet` (cross-check) |
| Input | `ncei/derived/model_validation_1min_full_expanded_primary/expanded_primary_coverage_gain_summary.parquet` (cross-check) |
| Output dir | `ncei/derived/model_validation_1min_step08_pub/b_pub_tables/` |
| Script | `ncei/code/19_step08_publication_tables.py` |

## Notes

- 轻量任务，PRD-only。无需 design.md / implement.md。
- 父任务 implement.md 已规定执行顺序：B 在 Wave 1 最先做。
- Pi-adapter dispatch 完全可行（机械、规范、无模糊点）。
