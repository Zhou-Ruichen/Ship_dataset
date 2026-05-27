# Design — C: Gap-Fill Error Structure

## Data layout

```
For each model M in {GEBCO, ETOPO, SRTM15, TOPO, SDUST}:
    expanded by-cell (2,732,689 rows)
        ├── retained subset: expanded_fill == False  → 2,398,774 rows
        └── gapfill subset:  expanded_fill == True   → 333,915 rows
```

Slice dimensions (all already present as columns):
`lat_band_10deg`, `depth_bin`, `region_10deg`, `quality_tier`, `evidence_class`, `matched_rule_id`.

## Attribution formula

ΔRMSE^2 抬升的 cell-level 来源可以拆解。设：

- N_strict = 2,398,774
- N_exp = 2,732,689
- 在 expanded subset 上：
  - sumsq_exp = sum(elev_error_m^2 across expanded)
  - RMSE_exp = sqrt(sumsq_exp / N_exp)
- 在 strict subset (= retained subset) 上：
  - sumsq_strict = sum(elev_error_m^2 across strict)
  - RMSE_strict = sqrt(sumsq_strict / N_strict)

直接代数关系（per model）：

```
sumsq_exp = sumsq_retained + sumsq_gapfill
N_exp     = N_retained + N_gapfill
RMSE_exp^2 = (sumsq_retained + sumsq_gapfill) / N_exp
```

ΔRMSE^2 = RMSE_exp^2 − RMSE_strict^2
        = (sumsq_retained + sumsq_gapfill) / N_exp − sumsq_strict / N_strict

由于 retained == strict（同一 cell 集合，同一残差），sumsq_retained == sumsq_strict。代入得：

```
ΔRMSE^2 = sumsq_strict * (1/N_exp − 1/N_strict) + sumsq_gapfill / N_exp
        = sumsq_strict * (N_strict − N_exp) / (N_exp * N_strict) + sumsq_gapfill / N_exp
```

第一项是负值（dilution by larger N），第二项是正值（gapfill cells add squared error）。
Per-slice 归因关注**第二项的 slice 分量**：

```
contribution_slice = sumsq_gapfill_in_slice / N_exp        # 切片对正向项的贡献
total_positive_term = sumsq_gapfill / N_exp                 # 全 gap-fill 正向项

contribution_pct = sumsq_gapfill_in_slice / sumsq_gapfill * 100
```

Top-20 切片按 contribution_pct 排序；累计必须 ≥ 80%。

> 注：这是简化口径，把负向 dilution 项忽略，只解释"gap-fill 注入的额外平方误差"的来源。报告里要明示这一口径。

## Output schemas

### 单维切片 TSV（per `slice_dim`）

`gapfill_slice_by_<slice_dim>.tsv`

| col | note |
|---|---|
| slice_dim | constant |
| slice_value | dim 的取值 |
| model | 5 models |
| n_cells_gapfill | gap-fill cells in slice |
| n_cells_retained | retained cells in slice |
| share_of_gapfill | n_gapfill / 333,915 |
| sumsq_error_gapfill | sum(err^2) |
| sumsq_error_retained | sum(err^2) |
| RMSE_gapfill | √(sumsq/n) |
| RMSE_retained | √(sumsq/n) |
| delta_rmse_slice | RMSE_gapfill − RMSE_retained |
| weighted_RMSE_gapfill | with validation_weight |
| weighted_RMSE_retained | with validation_weight |
| contribution_pct_of_total_gapfill_sumsq | per formula above |

### 全局归因 TSV

`gapfill_attribution_topN.tsv`：跨维度并集，按 contribution_pct 降序，前 20 行。

### 安全检查表

`c_gapfill_safety_checks.tsv`：

| check_id | description |
|---|---|
| gapfill_count | per model = 333,915 |
| retained_count | per model = 2,398,774 |
| retained_rmse_match_strict | 每模型 retained RMSE 与 strict-primary 现有 summary 误差 < 0.01 |
| slice_sum_consistency | 每个 slice_dim 的 sum(n_cells_gapfill) = 333,915 |
| nan_slice_handled | NaN slice 已聚合为 "<NA>" 字面值 |
| top20_attribution_pct | ≥ 80（warning if not） |

## Performance

每模型 333,915 + 2,398,774 = 2,732,689 行，6 个单维 group_by + 全局算子，pandas 内存内可完成，单模型 < 10 s。5 模型 sequential 总耗时 < 1 min。

## Report

`ncei/docs/step08_gapfill_error_structure_report.md` 结构：

1. **Summary** —— 一句话结论（例：gap-fill 升高 RMSE 的 ~X% 来自 `depth_bin=0-200m` + `region_10deg=南大洋` 子集）。
2. **Method** —— 子集定义 + 归因公式 + caveat（忽略 dilution 项）。
3. **Top 20 attribution** —— 引用 `gapfill_attribution_topN.tsv`。
4. **By-dimension breakdown** —— 6 个维度各取 top-3 切片，对外可读。
5. **Cross-model consistency** —— 主导切片在 5 个模型间是否一致（如果一致，归因是真实的"困难区域"；如果不一致，更可能是模型差异）。
6. **Caveats** —— NaN 切片、稀疏 `matched_rule_id`、阈值 80% 未达情况下的解释。

## Pi-adapter dispatch

适合。规格清晰，所有列已存在，无环境不确定性。dispatch 时强调输出契约与 acceptance。
