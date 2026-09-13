# Result

## 逐条判定

1. **final_r2 缺目录内 manifest —— 属于**，已回填。规范第 4 节硬性要求交付目录内有
   `product_manifest.json`；权威生成记录原本只在
   `ncei/derived/sb_track_quality_global/product_manifest.json`。回填件复制其
   created_at/created_by/计数，补齐 8,827 项输入哈希与 5,365 项输出哈希，输出哈希与
   `global_grid_1min_r2` manifest 的独立 2026-09-02 记录逐文件核对：5,365 比 5,365，
   0 不符（文件自生成后未变）。
2. **strict_primary_multibeam_cells 无轮次标签/manifest —— 属于**，已回填（多产品
   目录用产品限定名 `product_manifest_strict_primary_multibeam_cells.json`）。不发明
   轮次标签：记产品版本号 `ncei_validation_cells_v0.1.0`（step07b 运行时报告）、生成
   脚本与输入（JAMSTEC 主验证格 + NCEI 多波束分支格，含哈希）、parquet sha256（与
   global_grid_1min_r2 记录一致）、行数 2,398,774。带轮次标签的后续版本留给多波束
   新轮次（另一代理在途，未触碰其文件）。
3. **点层地位 —— 属于**（规范此前只禁无标签格层中间层，点层悬空）。方案：定为
   "可引用层"，`points_checked/product_manifest.json`（2026-09-13 回填）逐文件哈希
   5,365 个点文件（nc 1,850 + xyz 3,515）+ 入口清单哈希；下游钉 manifest sha256 即
   固定版本。不做轮次目录快照：4 GB 复制无对应收益。规范第 1/4/5/6 节同步改。
4. **全球逐航线相对偏差表 —— 职责方向属于，本轮不实现**。理由：下游敏感性结论
   未出（其自身声明"不急"）；且本仓六区 network 原型（等权、逐事件留一）pooled 留出
   |残差| 中位数劣于 raw 与 step23，而下游（对数加权、3×MAD、样本内加权 RMS）大幅
   改善——权重/剔差/锚定/评估口径均不同，需先统一口径并重做留出对照，才能决定
   全球版是否成产品。已在 `ncei/docs/step10_sb_network_bias_report.md` 追加下游
   对照证据（含 RMS 数字、505 条航线处置核验、口径差异、r3 决策三问）。
5. **consumers.yaml 两条登记 —— 合规，提交**。字段与规范第 5 节一致；
   `wks_9bb5b84f15a2f91e` 经 paseo 核实存在且 cwd 为下游仓库；日期 2026-09-13 当日。

## 交付物

- `ncei/code/42_backfill_product_manifests.py`（幂等可复跑，`--only` 分产品）
- 盘上 manifest（derived/ 按仓库惯例不入库）：
  - `ncei/derived/singlebeam/file_cells_1min_final_r2/product_manifest.json`（2.1 MB）
  - `ncei/derived/validation_cells_1min/product_manifest_strict_primary_multibeam_cells.json`
  - `ncei/derived/singlebeam/points_checked/product_manifest.json`（723 KB）
- `docs/数据产品规范与下游接入.md`：§1.1 点层 manifest、§4 读什么第 4 条 + 严格多波束
  固定方式 + 回填说明 + 禁止事项范围澄清、§5 字段示例、§6 步骤 4 点层刷新要求
- `ncei/docs/step10_sb_network_bias_report.md`：下游对照证据节
- `consumers.yaml`：下游写好的两条登记（审核通过，随本任务提交）

## 下游声明核验

- b_c.tsv 六窗口 505 条唯一航次全部命中 `track_quality.parquet`，处置分布
  keep_raw 447 / reject 50 / correct 3 / revert_to_raw 4 / flag_large_unapplied_bias 1，
  与下游报告一致（其 605 条含一新窗口的 100 条，不在证据目录内，未核验）。
- 下游交叉点 RMS 数字与 `result.md` 表逐项一致。
- "r2 与点层一致（14,655 组合、中位差 0）"为下游自检，未重算。

## 未做与原因

- 全球逐航线相对偏差表：见判定 4。
- 点层轮次快照目录：判定 3 所述，manifest 哈希已满足固定版本需求。
- 不修改、不删除任何已交付数据文件；未推送；未触碰多波束 round-2 代理的
  32-34/41_*、step15/step17、raw_round2 文件。
