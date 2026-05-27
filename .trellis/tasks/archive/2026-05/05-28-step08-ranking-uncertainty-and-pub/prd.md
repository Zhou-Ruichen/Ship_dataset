# Step 08 Followup: Model Ranking Uncertainty and Publication-Ready Tables/Figures

## Goal

Step 08 全局校核已完成（Stage 3/4/5/6 PASS，父任务已归档 `b68f8bd`）。本父任务负责把 Step 08 的现有产物深化为对外可发表的成果包，覆盖三类问题：

1. 给出模型 ranking 的统计不确定性（bootstrap CI、ranking 稳定概率、pairwise 显著性）。
2. 输出可出版的 strict-primary 评测表与 strict-vs-expanded 对比表。
3. 解释 expanded-primary 中 333,915 个 singlebeam gap-fill cell 为何整体推高 RMSE 6–8 m。

任务分 4 个独立可验收的子任务 A/B/C/D。父任务负责跨子任务整合、最终复核与对外汇总报告。

## Scope

**In scope**

- 基于 Step 08 已有 by-cell parquet（strict-primary + expanded-primary）的纯分析工作。
- 5 个全球模型：GEBCO_2024、ETOPO_2022、SRTM15_V2.7、TOPO_25.1、SDUST_2023。
- 1-min cell 网格，strict-primary 基线为 ranking 主表，expanded-primary 仅作为敏感性。

**Out of scope**

- SWOT_T1 区域校核（独立任务）。
- 任何模型重采或新模型接入。
- Step 06B 质量规则或 Step 07B validation product 的修改。
- 残差驱动的 cell 过滤、重标或晋升。

## Requirements

### 跨子任务硬性约束（继承自用户 prompt）

- **R1**：不修改 Step 06B 质量旗标。
- **R2**：不修改 Step 07B validation product。
- **R3**：不重跑 gridded 模型采样。
- **R4**：不使用模型残差去过滤 / 重标 / 晋升 validation cell。
- **R5**：strict-primary 是 ranking 的官方基线；expanded-primary 仅作敏感性。
- **R6**：所有分析脚本必须有 `--confirm-*` 之类的显式开关，避免误执行，并支持 `--overwrite` 控制写出。

### 子任务地图

| 子任务 | 目录 | 主输出 |
|---|---|---|
| A | `05-28-step08-a-ranking-uncertainty` | `ncei/docs/model_ranking_uncertainty_report.md` + bootstrap parquet/TSV |
| B | `05-28-step08-b-pub-tables` | strict-primary 与 strict-vs-expanded 出版级 TSV/CSV |
| C | `05-28-step08-c-gapfill-error-structure` | gap-fill 多维切片 TSV + 简报 markdown |
| D | `05-28-step08-d-pub-figures` | figure-ready 数据表 + 可选 PNG/PDF |

### 父任务直接工作（整合层）

- 跨子任务复核：A 的 CI 必须能解释 B 中点估计的稳定性；C 的切片必须能解释 B 中 ΔRMSE。
- 整合输出 `ncei/docs/publication_ready_step08_summary.md`：单一对外汇总文档，引用 A/B/C 数值与 D 图，给出"可被引用的一句话结论"。
- 整合输出 `ncei/derived/model_validation_1min_step08_pub/`（建议路径）：复合元数据与产物索引。

## Acceptance Criteria

跨子任务整体验收（父任务直接负责）：

- [ ] 4 个子任务全部 archive，对应主输出文件存在且通过各自 acceptance。
- [ ] `publication_ready_step08_summary.md` 引用 A 的 CI、B 的指标点估、C 的归因 top-N 切片，并链接 D 的图。
- [ ] 整合文档明示 strict-primary 作为 ranking 基线、expanded-primary 仅作敏感性的 policy 立场，保持与 Stage 6 最终报告一致。
- [ ] A 的 paired bootstrap 给出 GEBCO vs ETOPO 差异的 CI 与 p 值（或后验概率），结论与 B 的 ranking 表保持兼容。
- [ ] C 归因切片合计的 RMSE 贡献能解释 B 中"expanded vs strict +6 到 +8 m RMSE 抬升"的至少 80%。
- [ ] 所有数值与 Step 08 Stage 3/4/6 报告的现有数字在交叉点上一致（例如 strict_count=2,398,774；gap-fill=333,915；wRMSE 各模型点估）。
- [ ] 没有任何脚本修改 Step 06B 质量旗标 / Step 07B validation product / gridded 模型采样产物。

## Inputs (read-only)

- `ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_<MODEL>.parquet` × 5（每个 2,398,774 行）
- `ncei/derived/model_validation_1min_full_expanded_primary/full_validation_by_cell_expanded_primary_<MODEL>.parquet` × 5（每个 2,732,689 行，含 `expanded_fill` 标志）
- `ncei/derived/model_validation_1min_full_*/full_validation_metrics_summary_*.parquet`（Step 08 现有汇总）
- `ncei/derived/model_validation_1min_stage6_final/expanded_gapfill_sensitivity_summary.parquet`
- `ncei/docs/step08_final_global_validation_report.md`（policy 锚点）

## Outputs

- `ncei/docs/model_ranking_uncertainty_report.md`（A）
- `ncei/docs/publication_ready_step08_summary.md`（父任务整合）
- `ncei/docs/step08_gapfill_error_structure_report.md`（C）
- `ncei/derived/model_validation_1min_step08_pub/`（建议路径，存放跨子任务汇总产物 + 子任务索引）
- 子任务各自的 parquet/TSV/CSV 与图，分别落到各子任务约定目录。

## Risk / Open Questions

- **bootstrap 样本独立性**：1-min cell 在空间上有自相关，普通 i.i.d. cell-level bootstrap 会低估方差。A 子任务必须使用 block bootstrap（按 `region_10deg` 分块），否则 CI 不可靠。
- **paired 与非 paired 的取舍**：模型对之间用 paired 才能消掉公共 cell 难度。A 必须以 paired 为主。
- **绘图依赖**：D 子任务的 PNG/PDF 受当前 Python 绘图环境约束（matplotlib / cartopy 是否可用）。先输出 figure-ready 表，PNG 为可选项。
- **整合文档体量**：`publication_ready_step08_summary.md` 应保持精简（建议 < 400 行 markdown），把详细数据留在子任务报告。
