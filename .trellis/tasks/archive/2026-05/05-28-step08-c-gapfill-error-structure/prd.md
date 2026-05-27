# C — Gap-Fill Singlebeam Error Structure

## Goal

回答"为什么 expanded-primary 加 13.92% 覆盖会推高 RMSE 6–8 m"。把 Stage 4 expanded-primary 中 `expanded_fill==True` 的 333,915 个 singlebeam gap-fill cell 按多维切片分解 RMSE，识别贡献最大的地理 / 深度 / 质量层。

## Scope

**In scope**

- 仅分析 Stage 4 expanded-primary by-cell 中 `expanded_fill==True` 子集（=333,915 行/模型）。
- 切片维度：`lat_band_10deg`、`depth_bin`、`region_10deg`、`quality_tier`、`evidence_class`、`matched_rule_id`。
- 给出 top-N 切片对总 ΔRMSE（expanded − strict）的归因贡献。
- 输出归因报告 `ncei/docs/step08_gapfill_error_structure_report.md`。

**Out of scope**

- 不修改 expanded-primary 产物或 Step 06B 质量旗标。
- 不重采模型。
- 不做 bootstrap CI（A 任务可以后续按需补 gap-fill cell 的 CI）。

## Requirements

### R-C1 — gap-fill 子集

- 输入：5 个 `full_validation_by_cell_expanded_primary_<MODEL>.parquet`，每个 2,732,689 行。
- 过滤：`expanded_fill == True` → 每模型 333,915 行；脚本必须 assert 该数字。
- 同时保留 retained 子集（`expanded_fill == False`，2,398,774 行）作为参照基线（与 strict 应一致，需断言）。

### R-C2 — 多维切片

对每个 (slice_dim, slice_value, model) 组合计算：

| 列 | 公式 |
|---|---|
| n_cells | row count |
| share_of_gapfill | n_cells / 333,915 |
| RMSE_gapfill | sqrt(mean(elev_error_m^2)) on this slice (gap-fill subset) |
| RMSE_retained | RMSE on retained subset of same slice |
| RMSE_strict_baseline | 等价于 retained，给出对账列 |
| delta_rmse_slice | RMSE_gapfill − RMSE_retained |
| weighted_RMSE_gapfill | with validation_weight |
| weighted_RMSE_retained | with validation_weight |
| sum_sq_error_gapfill | sum of squared errors（用于归因贡献）|
| contribution_to_expanded_minus_strict_rmse_sq | sum_sq_error_gapfill / total_expanded_sq − sum_sq_error_retained_in_slice / total_strict_sq 的简化版本（详见 design.md） |

切片维度组合：
- 单维：`lat_band_10deg`, `depth_bin`, `region_10deg`, `quality_tier`, `evidence_class`, `matched_rule_id` —— 6 张表
- 双维（可选，由父任务决定是否纳入）：`depth_bin × lat_band_10deg`、`region_10deg × depth_bin` —— 2 张可选表

每张切片表输出一份 TSV。

### R-C3 — 归因汇总

最重要的输出：一张 `gapfill_attribution_topN.tsv`，列出对 expanded−strict ΔRMSE 贡献最大的 top-20 切片（跨所有维度并集），列：

| col | 说明 |
|---|---|
| slice_dim | 维度名 |
| slice_value | 维度取值 |
| model | 模型名 |
| n_cells | gap-fill cell 数 |
| share_of_gapfill | 占总 gap-fill 比例 |
| RMSE_gapfill | |
| RMSE_retained | |
| delta_rmse_slice | |
| contribution_pct_of_total_delta | 占 ΔRMSE^2 总抬升的百分比 |

汇总 top-20 贡献必须解释 expanded−strict ΔRMSE 抬升的至少 80%（acceptance criterion）。

### R-C4 — 报告 `step08_gapfill_error_structure_report.md`

- 报告结构：summary → method → top contributors → per-dimension breakdown → caveats。
- 包含 each-dimension top-3 表（地理 / 深度 / 质量）。
- 引用所有 TSV 路径。

### R-C5 — 约束

- 只读 expanded-primary by-cell。
- 不调整 quality flag / validation product / 模型采样。
- 脚本：`ncei/code/20_step08_gapfill_error_structure.py`。
- 显式开关：`--confirm-analyze`、`--overwrite`、`--check-only`。
- 输出目录：`ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/`。

## Acceptance Criteria

- [ ] `ncei/code/20_step08_gapfill_error_structure.py` 存在并通过 `python -m py_compile`。
- [ ] 完整运行 PASS，输出 6 张单维切片 TSV + 1 张 top-N 归因 TSV + 报告 markdown。
- [ ] `c_gapfill_safety_checks.tsv` 全部 PASS：
  - gap-fill 子集行数 = 333,915（每模型）
  - retained 子集行数 = 2,398,774
  - retained RMSE 与 strict-primary 表对账误差 < 0.01
  - 单维切片合计 n_cells = 333,915
- [ ] top-20 切片 contribution_pct 合计 ≥ 80%（按 ΔRMSE^2 计）。
- [ ] 报告 markdown 明确指出主导抬升的 1–2 个深度带 / 区域 / 质量层。

## Inputs / Outputs

| Kind | Path |
|---|---|
| Input | `ncei/derived/model_validation_1min_full_expanded_primary/full_validation_by_cell_expanded_primary_<MODEL>.parquet` × 5 |
| Input | `ncei/derived/model_validation_1min_full_strict_primary/full_validation_metrics_summary_strict_primary.parquet`（对账） |
| Output dir | `ncei/derived/model_validation_1min_step08_pub/c_gapfill_structure/` |
| Script | `ncei/code/20_step08_gapfill_error_structure.py` |
| Report | `ncei/docs/step08_gapfill_error_structure_report.md` |

## Risk

- 某些维度（如 `matched_rule_id`）可能稀疏 / 有大量 NaN；脚本必须显式处理 NaN 切片（聚合时分组为 `"<NA>"` 字面值）。
- top-N 归因合计 < 80% → 报告需要给出"长尾贡献"的解释而非简单失败；阈值可作为 review gate 输出 warning 但不阻断。
