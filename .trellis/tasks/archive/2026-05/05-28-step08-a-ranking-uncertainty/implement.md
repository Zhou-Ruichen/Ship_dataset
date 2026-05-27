# Implement — A: Ranking Uncertainty

## Execution checklist

- [ ] 创建脚本骨架 `ncei/code/18_step08_ranking_bootstrap.py`：argparse、I/O 路径、logging、metadata 记录。
- [ ] 实现 paired residuals 构造与 cell_id 一致性 assert（N=2,398,774；validation_weight 与 region_10deg 在 5 模型间一致）。
- [ ] 实现 cluster 索引化（region_10deg → int16，构造每 cluster 的 cell indices）。
- [ ] 实现单次 bootstrap iter 函数（输入 sampled cluster ids，输出 metric dict + pairwise dict）。
- [ ] 向量化批 iter：B=1000 默认。固定 seed=20260528。进度 logging（每 100 iter）。
- [ ] 计算 CI：percentile (2.5, 50, 97.5)；mean。
- [ ] 计算 ranking 概率：argsort over RMSE / wRMSE 列。
- [ ] 安全检查表落盘 `a_ranking_safety_checks.tsv`。
- [ ] 写出所有 parquet/TSV 到 `ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/`。
- [ ] 生成 `ncei/docs/model_ranking_uncertainty_report.md`：summary + method + tables + caveats。
- [ ] 自验证：`python -m py_compile`、`--check-only` 干跑模式（只读输入，输出 shape/hash 摘要）。
- [ ] 完整运行：`python ncei/code/18_step08_ranking_bootstrap.py --run-label a_ranking --confirm-bootstrap --overwrite`，确认 elapsed 与 safety checks。
- [ ] 与父任务 G2 一致性复核（CI 包含 B 的点估）。

## Validation commands

```bash
# Compile check
python -m py_compile ncei/code/18_step08_ranking_bootstrap.py

# Dry run (read inputs, print shape/hashes, skip bootstrap)
python ncei/code/18_step08_ranking_bootstrap.py --check-only

# Full run
python ncei/code/18_step08_ranking_bootstrap.py \
  --run-label a_ranking \
  --bootstrap-iters 1000 \
  --seed 20260528 \
  --confirm-bootstrap \
  --overwrite

# Optional convergence diagnostics
python ncei/code/18_step08_ranking_bootstrap.py \
  --run-label a_ranking_diag \
  --bootstrap-iters 1000 \
  --seed 20260528 \
  --diagnose-convergence \
  --confirm-bootstrap \
  --overwrite
```

## Review gates

| Gate | Condition |
|---|---|
| G-A-1 | paired join N=2,398,774 PASS，无 NaN |
| G-A-2 | 124 cluster；最大 cluster ≤ 267,406 |
| G-A-3 | safety checks 全部 PASS（16+ 项） |
| G-A-4 | model_metric_ci.tsv 中 ci_covers_point 全 PASS |
| G-A-5 | pairwise_delta_rmse_ci.tsv 中 GEBCO vs ETOPO 给出明确显著性结论 |
| G-A-6 | model_ranking_uncertainty_report.md 写入并通过人工 review |

## Pi-adapter 分发说明

此任务规格完备、机械性强，适合 Pi-adapter 分发。dispatch 时需带：

- Active task: `.trellis/tasks/05-28-step08-a-ranking-uncertainty`
- 强调约束：只读输入、不修改上游产物、固定 seed、显式 `--confirm-*` 开关。
- 引用本 prd.md + design.md 作为 spec。

如本 main agent 自行实现也可，由父任务在 Phase 1.4 review 后定夺。

## Rollback

- 单次失败：删除 `ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/` 与 `ncei/docs/model_ranking_uncertainty_report.md` 重新执行。
- 方法路线变更（如换 BCa CI 或 moving block）：保留现脚本，做 v2 副本；不覆盖现行产物，由父整合层选用。

## Open questions deferred to execution

- 如果 paired residual 矩阵中发现 NaN（不应发生但 robustness 要求） → 视作 BUG，立即停跑并向用户报告。
- 如果 G-A-4 失败（点估落在 CI 外） → 视作 cluster 内重复抽样导致的偏差，需要切到 mean-bias-corrected percentile 或 BCa；在该情景下停跑、回到 design.md 修订。
