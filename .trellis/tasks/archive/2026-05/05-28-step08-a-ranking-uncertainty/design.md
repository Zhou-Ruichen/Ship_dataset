# Design — A: Ranking Uncertainty (paired cluster bootstrap)

## Data layout in memory

```
cell_id (N=2,398,774, uint32)
region_10deg (N, str → factorized int16, 124 unique values)
validation_weight (N, float32, [0.4, 1.0])
elev_error_m matrix shape (N, 5), float32, models in column order:
  [GEBCO_2024, ETOPO_2022, SRTM15_V2.7, TOPO_25.1, SDUST_2023]
```

Total memory budget for paired residual matrix: 2,398,774 × 5 × 4 bytes ≈ 46 MB. Comfortably fits in RAM.

## Bootstrap algorithm

```
1. Factorize region_10deg → region_idx (uint16), region_offsets (CSR-like).
2. Precompute, per cluster c:
     - cell indices vector cells_c
     - weights vector w_c
     - residual sub-matrix R_c (n_c × 5)
3. For b in 1..B:
     a. sampled_cluster_ids = rng.choice(124, size=124, replace=True)
     b. Concatenate (R_c, w_c) for sampled clusters → R_b (n_b × 5), w_b (n_b,)
     c. Per-model metric on column j of R_b:
         RMSE_j  = sqrt(mean(R_b[:, j]**2))
         MAE_j   = mean(|R_b[:, j]|)
         wRMSE_j = sqrt(sum(w_b * R_b[:, j]**2) / sum(w_b))
     d. Pairwise: dRMSE_ij = RMSE_i − RMSE_j for all i<j
     e. Persist row to bootstrap result table.
4. Compute percentile CIs from result table.
5. Compute ranking probabilities by per-iter argsort over RMSE columns.
```

注意 step 3.b 不需要物理 concat：可以在每次 iter 用 fancy indexing 把所有抽到的 cell idx 拼成一个数组，再向量化算 RMSE。`numpy.concatenate` 在 N≈2.4M 量级是 ms 级。

如果出现 cluster 重复抽中（必然，有放回抽样），cells 会重复出现 — 这正是 cluster bootstrap 想要的：方差由 cluster 的不可重复性主导。

## Why cluster bootstrap by region_10deg

- 1-min cell 的空间自相关在 ~100 km 量级内显著。10° region ≈ 1100 km，远大于自相关尺度，cluster 之间近似独立。
- i.i.d. cell-level bootstrap 假设每个 cell 是独立样本 → 显著低估 ΔRMSE 方差。
- moving block bootstrap on a 2D grid 实现复杂；这里 region_10deg 已被 Step 08 用作既有切分维度，复用是最低风险的选择。

## Convergence diagnostics (optional)

`--diagnose-convergence` 模式：在 B=1000 的同一组 cluster 重采序列中，分别取前 250 / 500 / 1000 次计算 CI；输出三组 CI 到 `bootstrap_convergence_diagnostics.tsv`。如果 1000 vs 500 的 CI 端点差异 > 5% → 在报告 caveats 中标注 B 可能不足。

## Output schemas

### `ranking_bootstrap_iters.parquet`

| col | type | note |
|---|---|---|
| iter | uint16 | 0..B-1 |
| metric | str | "RMSE" / "MAE" / "wRMSE" |
| model | str | model name |
| value | float32 | metric value for this iter |

For pairwise differences, separate file `ranking_bootstrap_pairwise_iters.parquet`:

| col | type | note |
|---|---|---|
| iter | uint16 |  |
| model_a | str |  |
| model_b | str |  |
| delta_rmse | float32 | RMSE_a − RMSE_b |

### `model_metric_ci.tsv`

| col | note |
|---|---|
| model | model name |
| metric | RMSE / MAE / wRMSE |
| point_estimate | from full-data computation (no bootstrap) |
| p2.5 / p50 / p97.5 | from bootstrap percentiles |
| boot_mean | bootstrap distribution mean |
| ci_covers_point | bool, p2.5 ≤ point_estimate ≤ p97.5 |

### `pairwise_delta_rmse_ci.tsv`

| col | note |
|---|---|
| model_a | model name |
| model_b | model name |
| delta_point | RMSE_a_point − RMSE_b_point |
| delta_p2.5 / p50 / p97.5 | from bootstrap |
| p_a_better | mean(delta_rmse < 0) over iters |
| significant_at_95pct | bool |

### `ranking_stability_rmse.tsv`

| col | note |
|---|---|
| model | row index |
| rank_1 | P(this model ranks 1st by RMSE) |
| rank_2 | P(this model ranks 2nd) |
| rank_3 | … |
| rank_4 | … |
| rank_5 | … |

Same schema for `ranking_stability_wrmse.tsv` with weighted RMSE.

### `a_ranking_safety_checks.tsv`

| check_id | description | status | observed |
|---|---|---|---|
| paired_n_cells | N == 2,398,774 | PASS / FAIL | |
| no_nan_residuals | no NaN in N×5 matrix | PASS / FAIL | |
| n_clusters | 124 | PASS / FAIL | |
| weight_range | [0.4, 1.0] | PASS / FAIL | |
| ci_covers_point | all 15 (5 models × 3 metrics) cover point | PASS / FAIL | n_pass / 15 |
| reproducible_seed | seed and rng state recorded | PASS / FAIL | |
| no_residual_filter | no row of input was dropped by residual condition | PASS / FAIL | |

## Reproducibility

- Fixed seed in metadata.
- Input file SHA256 hashes recorded in `bootstrap_runtime_metadata.tsv`.
- Python / numpy / pandas / pyarrow versions logged.

## Tradeoffs

- **Cluster bootstrap vs spatial moving block**：选择前者，因为 region_10deg 已在 Step 08 体系内，复用 + 实现简单；moving block 需要明确空间核与块长，超出本任务范围。
- **Percentile CI vs BCa**：选择 percentile，因为 B 已经设到 1000，且本任务对极端尾部精度要求不高。BCa 后续可加。
- **每 iter 落盘 vs 全 iter 落盘后写**：选择全 iter 在内存中聚合后一次写出（B×5×3 ≈ 15k 行 + B×10 ≈ 10k 行 pairwise，量很小）。
