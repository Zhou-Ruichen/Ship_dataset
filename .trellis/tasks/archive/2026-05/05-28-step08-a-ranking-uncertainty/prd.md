# A — Model Ranking Uncertainty (paired block bootstrap)

## Goal

对 5 个 strict-primary 全球模型给出 RMSE / MAE / weighted RMSE 的 bootstrap 置信区间，并量化 ranking 稳定性（rank-k 概率）与 pairwise 显著性（特别是 GEBCO vs ETOPO）。所有结果用于父任务整合到对外汇总报告。

## Scope

**In scope**

- 5 个 strict-primary by-cell 残差文件（2,398,774 行 × 5 模型）。
- Paired cluster bootstrap by `region_10deg`（124 cluster）。
- 报告 RMSE / MAE / weighted RMSE 的 95% CI；pairwise ΔRMSE 的 CI 与 P(model_i 优于 model_j)。
- ranking 稳定概率（每模型 rank-k 概率矩阵）。
- GEBCO vs ETOPO（以及其他相邻对）的显著性结论。

**Out of scope**

- expanded-primary 的 bootstrap（B/C 任务负责 expanded 的点估与归因；A 只做 strict-primary 的 ranking）。
- 非全球模型（SWOT_T1）。
- 模型残差驱动的过滤 / 重标。

## Requirements

### R-A1 — Paired residuals 构造

- 输入：5 个 `full_validation_by_cell_strict_primary_<MODEL>.parquet`，每个 2,398,774 行。
- 操作：按 `cell_id` inner-join，得 N × 5 paired residual 矩阵，N=2,398,774；同时 join `region_10deg` 与 `validation_weight`（任一模型副本即可，因为这两列由 cell_id 决定，与模型无关 — 需在脚本中先验证此独立性）。
- 数据契约：join 后无 NaN；不丢失任何 cell_id；保留 weight 与 region_10deg。

### R-A2 — Cluster bootstrap

- 单位：cluster = `region_10deg` 唯一值（124 个）。
- 算法：每次 iteration 用有放回方式从 124 个 cluster 中抽 124 个；把抽到的每个 cluster 的所有 cell（含 weight 与 paired residual）拼接为该次重采样本；再算 RMSE / MAE / wRMSE 与 pairwise ΔRMSE。
- 默认 `--bootstrap-iters 1000`，`--seed 20260528`，可命令行覆盖。
- 输出每次 iter 的 5 模型 RMSE / MAE / wRMSE / pairwise ΔRMSE，长格式 parquet。

### R-A3 — CI 与显著性

- 95% percentile CI（2.5%, 50%, 97.5%）。
- 同时输出点估（来自 B 的全局点估，无重采），作为引用对比。
- 对每对 (model_i, model_j)，输出 `delta_rmse_p2.5 / p50 / p97.5 / mean`、`p_i_better = mean(boot_rmse_i < boot_rmse_j)`、`significant_at_95pct = (p2.5 > 0) OR (p97.5 < 0)`。

### R-A4 — Ranking 稳定概率

- 对每次 bootstrap iter，按 RMSE 对 5 个模型排序，得 rank 向量。
- 汇总每个模型出现在 rank-1 / rank-2 / … rank-5 的频率。输出 5×5 矩阵 TSV。
- 同样为 weighted RMSE 重复一次（独立矩阵）。

### R-A5 — 报告 `model_ranking_uncertainty_report.md`

- 报告结构：summary（GEBCO vs ETOPO 一句话结论）→ method（block bootstrap 设计）→ tables（rank 概率矩阵、pairwise ΔRMSE CI、各模型 CI）→ caveats（cluster 大小不均匀、N 与 cluster 数）。
- 引用所有数值的 parquet/TSV 路径。

### R-A6 — 约束

- 只读访问输入；不写任何模型采样产物；不修改 Step 06B/07B/Step 08 上游文件。
- 显式开关：`--confirm-bootstrap`、`--overwrite`、`--bootstrap-iters N`、`--seed S`、`--check-only`。
- Memory：5×N×float32 paired residual 矩阵 ≈ 46 MB；可全内存计算；每次 iter 中间结果不落盘。
- 单次完整运行预计 < 30 min（B=1000，向量化 numpy 实现）。

## Acceptance Criteria

- [ ] `ncei/code/18_step08_ranking_bootstrap.py` 存在并通过 `python -m py_compile`。
- [ ] 完整运行 PASS，输出落到 `ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/`。
- [ ] 输出文件：
  - `ranking_bootstrap_iters.parquet`（B 行 × 5 模型 RMSE/MAE/wRMSE + pairwise ΔRMSE）
  - `model_metric_ci.tsv`（每模型 RMSE/MAE/wRMSE 的 p2.5/p50/p97.5/mean）
  - `pairwise_delta_rmse_ci.tsv`（C(5,2)=10 对，每对 CI + P + significant flag）
  - `ranking_stability_rmse.tsv`（5×5 概率矩阵）
  - `ranking_stability_wrmse.tsv`（5×5 概率矩阵）
  - `bootstrap_runtime_metadata.tsv`（seed / iter / cluster 列表 hash / elapsed）
- [ ] `ncei/docs/model_ranking_uncertainty_report.md` 写入并包含所有表格的核心数字与显式 method 说明。
- [ ] 安全检查 parquet（`a_ranking_safety_checks.tsv`）：每模型点估必须落入对应 95% CI；cluster bootstrap N=124 cluster；paired residual 矩阵无 NaN；输入文件 hash 记录。
- [ ] GEBCO vs ETOPO 显著性结论清晰（significant or not significant at 95%）。

## Inputs / Outputs (paths)

| Kind | Path |
|---|---|
| Input | `ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_<MODEL>.parquet` × 5 |
| Output dir | `ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/` |
| Script | `ncei/code/18_step08_ranking_bootstrap.py` |
| Report | `ncei/docs/model_ranking_uncertainty_report.md` |

## Risk

- Cluster 大小高度不均匀（min=2, max=267,406）→ 抽样方差受最大 cluster 主导。**接受**这一性质（这是空间相关结构的真实反映），但在报告 caveat 中明示。
- B=1000 不一定够收敛 → 在脚本中加 `--diagnose-convergence` 模式，跑 250/500/1000 各算一次 CI 看稳定性，写入 metadata。默认运行不开启。
- paired join 假设 cell_id 在 5 个文件中完全一致（Stage 3 PASS 已隐含保证），但脚本仍要显式 assert N=2,398,774。
