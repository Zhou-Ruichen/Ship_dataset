# Design — Step 08 Followup: Ranking Uncertainty + Publication Pack

## Overall data flow

```
Step 08 by-cell parquet (strict + expanded)
        │
        ├── A: paired residuals  ── block bootstrap (by region_10deg) ── CI / ranking probabilities
        │
        ├── B: aggregate metrics per model (strict)  ── publication-ready tables
        │                                            ── strict-vs-expanded comparison
        │
        ├── C: expanded_fill == True 子集 ── multi-axis RMSE slices  ── attribution markdown
        │
        └── D: aggregate tables consumed by A/B/C  ── figure-ready data
                                                  ── optional matplotlib PNG/PDF
                ↓
         Parent integration: publication_ready_step08_summary.md
```

All sub-task scripts are read-only over Step 06B/07B/Step 08 artifacts. None touch gridded model files or validation cell parquet.

## Module boundaries

| Module | Owns | Reads | Writes |
|---|---|---|---|
| A | bootstrap + CI script | Stage 3 by-cell × 5 | bootstrap parquet + report md |
| B | aggregation script | Stage 3 by-cell × 5, Stage 4 by-cell × 5 | publication TSV/CSV |
| C | slicing script | Stage 4 by-cell × 5 (expanded_fill == True 子集) | slice TSV + report md |
| D | plotting script | aggregated tables from A/B/C | figure data + optional PNG/PDF |
| Parent | integration script + markdown | A/B/C/D outputs | summary md + manifest |

No cross-module write paths; each module's outputs land under a deterministic path declared in its `implement.md`.

## Statistical contract (binding for A)

- **Residual definition**：`elev_error_m = ship_elev_m - model_elev_m`（已存在于 by-cell parquet）。绝对误差用 `abs_elev_error_m`。Strict-primary 文件中无 NaN（已由 Step 08 Stage 3 safety check 保证）。
- **Paired bootstrap**：对每个 cell_id，按所有 5 个模型 inner-join，得到 N × 5 的 paired residual 矩阵。N = 2,398,774。
- **Block bootstrap**：以 `region_10deg`（lon × lat 各 10° bin）为重采块。共 ~648 个潜在 region 块，实际值需从数据中取唯一值。每次 bootstrap iteration 按 cluster 整块重采。
- **重采次数**：默认 B = 1000。运行时可调 (`--bootstrap-iters`)。固定 seed (`--seed 20260528`)。
- **置信水平**：默认 95% CI（percentile）。可输出 (2.5%, 50%, 97.5%) 三个分位 + 平均值。
- **指标**：每次重采计算 RMSE、MAE、weighted RMSE（按 `validation_weight`）、pairwise ΔRMSE。
- **Ranking 稳定概率**：在 B 次重采中统计每个模型出现在 rank-1 / rank-2 / … rank-5 的频率，作为后验概率近似。
- **paired 显著性**：对每对 (model_i, model_j)，bootstrap 分布的 ΔRMSE 的 2.5–97.5% CI 是否跨 0；同时报告 P(model_i RMSE < model_j RMSE)。

## Output contract

- **A 的 parquet**：长格式 `metric × model × statistic × value`，便于 D 直接读取作图。
- **B 的 TSV**：每个模型一行，列固定为 prd.md 中所列指标顺序。
- **C 的 TSV**：长格式 `slice_dim × slice_value × model × metric × value`，附带 `n_cells_in_slice`、`fraction_of_total_rmse_increase`。
- **D**：直接产出 figure-ready 表（每个图一份）；PNG 可选。
- **父任务汇总**：`publication_ready_step08_summary.md` 引用上述文件路径；不冗余复制大数据表。

## Compatibility / rollout

- 所有脚本放在 `ncei/code/` 下，沿用现有命名风格（数字前缀）。例如：
  - `18_step08_ranking_bootstrap.py`（A）
  - `19_step08_publication_tables.py`（B）
  - `20_step08_gapfill_error_structure.py`（C）
  - `21_step08_publication_figures.py`（D）
  - `22_step08_publication_summary.py`（父任务整合）
- 写出目录：`ncei/derived/model_validation_1min_step08_pub/` 作为汇总根目录；各子任务在其下建子目录 `a_ranking_uncertainty/`、`b_pub_tables/`、`c_gapfill_structure/`、`d_figures/`、`summary/`。
- 旧产物（Step 08 Stage 3/4/5/6）只读，不动。
- 没有数据库迁移、没有外部接口。

## Rollback

- 单次运行通过 `--overwrite` 控制覆盖；不开 `--overwrite` 时遇已存在文件直接报错退出。
- 任意阶段失败 → 删除该子目录重新执行；不会影响其他子任务或上游 Step 08 产物。
- 如果某子任务最终方法路线变更，可整体删除 `ncei/derived/model_validation_1min_step08_pub/<sub>/` 重做，不影响其他模块。

## Tradeoffs and rejected options

- **i.i.d. cell-level bootstrap**：放弃。1-min cell 空间自相关明显，会低估 ΔRMSE 方差与 ranking 稳定性。
- **每模型独立 bootstrap**：放弃。无法获得 paired ΔRMSE 的 CI（消公共难度后才有效信号）。
- **逐子任务独立 markdown 也作为父任务最终对外口径**：放弃，因为对外协作者只读一份才不会乱。统一一个 `publication_ready_step08_summary.md`。
- **直接出 PNG 不出 figure-ready 表**：放弃。数据表是源真相，图是衍生物，未来其他绘图工具/合作者可复用表。
