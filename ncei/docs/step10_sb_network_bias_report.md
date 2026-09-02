# Step 10 SB crossover network constant-offset comparison

## 结论

建议：`keep step23`。Step 23 在两项预声明 pooled 指标上均优于 network。该判断只适用于六个冻结区域的既有 SB×SB 交叉事件。

## 三种方法的逐事件留一比较

每个可评价连通分量逐次留出一个交叉事件。raw、Step 23 和 network 使用完全相同的留出事件；若删除该事件后轨线偏移差不可识别，三种方法均排除该事件。残差定义为观测 `depth_second - depth_first` 减去相应方法预测的偏移差。network 为等权最小二乘，没有使用 GEBCO 或深度相关权重。

| region | variant | held-out events | median |residual| (m) | residual NMAD (m) |
| --- | --- | ---: | ---: | ---: |
| lon068_lat018 | raw | 1275 | 17.05 | 25.94 |
| lon068_lat018 | step23 | 1275 | 8.74 | 13.08 |
| lon068_lat018 | network | 1275 | 39.14 | 56.38 |
| lon052_lat018 | raw | 1286 | 4.17 | 5.36 |
| lon052_lat018 | step23 | 1286 | 4.02 | 5.42 |
| lon052_lat018 | network | 1286 | 32.00 | 46.06 |
| lon058_lat012 | raw | 2573 | 21.77 | 31.81 |
| lon058_lat012 | step23 | 2573 | 22.77 | 33.83 |
| lon058_lat012 | network | 2573 | 35.72 | 53.58 |
| lon059_lat015 | raw | 1006 | 49.04 | 73.02 |
| lon059_lat015 | step23 | 1006 | 34.08 | 48.93 |
| lon059_lat015 | network | 1006 | 98.29 | 146.84 |
| lon004_lat033 | raw | 1860 | 22.51 | 34.43 |
| lon004_lat033 | step23 | 1860 | 23.05 | 35.33 |
| lon004_lat033 | network | 1860 | 42.66 | 60.51 |
| lon021_lat010 | raw | 4825 | 63.78 | 94.80 |
| lon021_lat010 | step23 | 4825 | 63.01 | 93.53 |
| lon021_lat010 | network | 4825 | 124.97 | 186.04 |
| pooled | raw | 12825 | 28.39 | 42.14 |
| pooled | step23 | 12825 | 23.86 | 35.35 |
| pooled | network | 12825 | 61.64 | 90.80 |

## 绝对锚定与自由网

包含至少一条已应用 Step 23 偏移轨线的分量固定这些轨线的 Step 23 值；其余分量采用分量内偏移和为零，只能解释相对偏移。

| datum type | components | tracks |
| --- | ---: | ---: |
| anchored | 6 | 240 |

| region | components | anchored components | free components | anchored tracks | free tracks | evaluated events | LOO-unidentifiable events |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lon068_lat018 | 1 | 1 | 0 | 34 | 0 | 1275 | 0 |
| lon052_lat018 | 1 | 1 | 0 | 43 | 0 | 1286 | 0 |
| lon058_lat012 | 1 | 1 | 0 | 43 | 0 | 2573 | 1 |
| lon059_lat015 | 1 | 1 | 0 | 50 | 0 | 1006 | 0 |
| lon004_lat033 | 1 | 1 | 0 | 14 | 0 | 1860 | 0 |
| lon021_lat010 | 1 | 1 | 0 | 56 | 0 | 4825 | 0 |

## elt18 与 odp130jr

| region | track | datum | Step 23 anchor | Step 23 offset (m) | network offset (m) | crossovers | evaluated events | raw median |LOO residual| (m) | Step 23 median (m) | network median (m) |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lon021_lat010 | elt18 | anchored | False | 0.00 | -969.91 | 75 | 75 | 1032.77 | 1032.77 | 770.95 |
| lon068_lat018 | odp130jr | anchored | True | -44.00 | -44.00 | 141 | 141 | 3.91 | 44.42 | 44.74 |

elt18 的 network 偏移为 -969.91 m，与先前 Step 23 候选值 -1247 m 方向相同且同为约千米量级。其事件级留出残差绝对值中位数从 raw 的 1032.77 m 降至 770.95 m，但仍有 770.95 m，因此只支持存在大幅负偏移，不支持该常数偏移已充分解释交叉差。

odp130jr 是 Step 23 锚，按预声明方法被固定为 -44.00 m，network 没有独立估计它。该轨线的留出残差绝对值中位数从 raw 的 3.91 m 增至 44.74 m；这与先前 141 个交叉事件中心接近零的证据一致，也说明 -44 m 锚值不受这些交叉事件支持。

## 方法与可追溯输出

轨线偏移、标准误、交叉数、不同邻轨数和分量编号见 `track_offsets_<region>.parquet`。分量基准类型与评价纳入数见 `components.parquet`。每个事件的三种方法残差及排除原因见 `heldout_residuals_<region>.parquet`，汇总数来自 `comparison_summary.parquet`。运行命令、输入和软件环境见 `manifest.json`。
