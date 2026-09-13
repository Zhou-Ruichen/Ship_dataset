# 下游交付契约补全：产品 manifest 回填与点层引用规则

mode: production（文档契约补全 + 盘上 manifest 回填；不改任何数据文件内容）

## 背景

下游仓库 12-ggm_scs 于 2026-09-13 提出五条交付层需求。逐条判定后，属于本仓库职责的
三条在本任务内完成；不属于或应推迟的记录理由（见 result）。

## 需求判定（结论）

1. `file_cells_1min_final_r2/` 缺目录内 `product_manifest.json`（规范第 4 节硬性要求）
   —— 属于。权威生成记录已在 `ncei/derived/sb_track_quality_global/product_manifest.json`
   （created_at 2026-09-02T21:13:15Z，含 input_manifest sha256 与计数），但规范要求
   manifest 在产品目录内。回填一份目录内 manifest：引用权威记录、补齐输入与输出
   文件 sha256，并与 `global_grid_1min_r2` manifest 的独立哈希记录（2026-09-02）交叉
   核对，证明文件自生成后未变。
2. `strict_primary_multibeam_cells.parquet` 无轮次标签/manifest —— 属于（规范第 4 节
   把它列为下游直接输入）。按多产品目录用产品限定名
   `product_manifest_strict_primary_multibeam_cells.json` 回填：记产品版本号
   `ncei_validation_cells_v0.1.0`、生成时间与脚本（step07b 报告）、sha256、行数。
   不发明轮次标签；带标签的后续版本由多波束 round-2 之后的轮次决定（不在本任务内）。
3. 点层（`points_checked/` + `ncei/manifests/bathymetry_entry_manifest.parquet`）地位
   不明 —— 属于（规范只禁了无标签格层中间层，点名未覆盖点层）。补一份
   `points_checked/product_manifest.json`（5,365 文件逐个 sha256 + 入口清单哈希），
   并在规范第 4 节写明：点层是"可引用层"，下游钉 manifest 哈希即可用；不做轮次
   目录快照（4 GB 复制无对应收益，manifest 哈希已可固定版本）。轮次若改动点层，
   刷新该 manifest 并在第 6 节通知中说明。
4. 全球版逐航线相对偏差表 —— 职责方向属于本仓库（step10 调研已规划、27 号脚本已做
   六区原型），但本轮不实现：下游敏感性结论未出；且本仓六区原型（等权、留一残差
   评估）与下游平差（对数加权、样本内加权 RMS）口径不同、结论相反，需先对齐方法。
   在 `step10_sb_network_bias_report.md` 追加下游对照证据与开放问题，供 r3 决策。
5. consumers.yaml 两条登记 —— 合规（字段齐全、workspace 已验证存在、日期当日），
   随本任务提交。

## 约束

- 不修改任何已交付目录中的数据文件；只新增 manifest 说明文件（derived/ 按 .gitignore
  惯例留在盘上不入库）。
- 不碰多波束 round-2 代理的未提交/未跟踪文件（ncei/code/32-34、41_*、
  download_tier_a_round2.py、ncei/docs/step15/step17、ncei/raw_round2/）。
- 回填 manifest 必须注明是回填、注明哈希计算时间，不得伪造生成时点。

## 交付

1. `ncei/code/42_backfill_product_manifests.py`（可复跑，幂等）
2. 三份盘上 manifest（见上）
3. `docs/数据产品规范与下游接入.md` 第 1/4/6 节增补
4. `ncei/docs/step10_sb_network_bias_report.md` 追加下游对照节
5. consumers.yaml（下游已写好，随任务提交）

## 验收

- 回填脚本运行成功；final_r2 的 5,365 个输出哈希与 global_grid_1min_r2 manifest
  逐一一致（0 不符）。
- 三份 manifest 均含 created_at/created_by/哈希/计数，且回填性质已标注。
- 规范改动后自洽：点层引用规则、strict MB 固定方式、回填说明互相引用无矛盾。
- git 提交只含本任务文件 + consumers.yaml。
