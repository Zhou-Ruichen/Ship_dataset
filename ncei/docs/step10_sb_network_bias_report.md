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

## 下游独立平差的对照证据（2026-09-13，供 r3 决策参考）

下游仓库 12-ggm_scs 在 6 个 4°×4° 窗口（南海、日本海、夏威夷、大西洋中脊、阿根廷海盆、吕宋海峡西部）对全部 QC 保留航次做了逐航次常数偏差自由网平差：0.004° 箱交叉点对表、交叉点对数加权最小二乘、连通分量内锚定（偏移加权和为零）、一次 3×MAD 剔除。交叉点加权 RMS 平差前后：大西洋中脊 74.1→17.1 m，夏威夷 14.5→8.3 m，南海 35.3→32.3 m，日本海 9.4→7.6 m，阿根廷海盆 6.5→2.9 m，吕宋 9.7→6.1 m。证据与预登记协议在下游仓库 `outputs/20260913T105537Z_ggm_leveled_sensitivity/`（protocol.json、b_c.tsv、crossover_residuals.tsv、result.md）。

与 Step 23 门控的对照（本仓核验）：b_c.tsv 覆盖的六窗口 505 条航线在 `ncei/derived/sb_track_quality_global/track_quality.parquet` 中处置为 keep_raw 447、reject 50、correct 3、revert_to_raw 4、flag_large_unapplied_bias 1（与下游报告的 605 条含一新窗口，新增窗口的 100 条不在该证据目录内，未核验）。correct 恰为 3 条：Step 23 以多波束为基准的门控在这些窗口几乎未施加改正，而下游相对网平差显示多数窗口的交叉一致性可大幅改善。这不是矛盾：门控只在有严格多波束共位支撑且达 2 NMAD 时才改正，其目标是绝对基准；自由网解决的是航次间相对一致。

与本报告 network 臂的口径差异（重要）：本报告 network 为等权最小二乘、按逐事件留一残差评估，pooled 留出 |残差| 中位数 61.64 m，劣于 raw（28.39）与 step23（23.86）；下游为对数加权、含 3×MAD 剔除，按保留对的样本内加权 RMS 评估，多数窗口大幅改善。两者权重、剔差、锚定与评估口径都不同，样本内加权 RMS 的改善不能直接推出留出预测能力。全球版若采纳，必须先统一口径并重做同样的留出对照。

r3 决策问题（下游关于该平差是否改变其 GGM 结论的敏感性分析仍在进行，暂不实施全球版）：

1. 全球版逐航线相对偏差表（含不确定度、支持数、是否多波束锚定、残差）是否作为交付产品；
2. 权重（对数 vs 等权 vs 复合）、剔差规则、锚定策略按下游协议还是本报告预声明规则固定；
3. 与 Step 23 门控的关系：替换、并行输出，或作为 track_disposition 的输入。

下游敏感性结论出来后补记于此。
