# 多波束流式链路与全量 L2 重建

父任务：`11-12-ship-refactor`。负责人 S（codex gpt-6.1-sol）。

## 问题

现行 `ncei/swath/` 先把每个航次解成 staging 与两层 L1（`ncei/derived/mb_round2/` 94 个航次已占 1.8 TiB），选点规则按轮次叠加成 `basic`、`basic_native_good`、`basic_native_good_valid_ping_navigation` 三种策略和四个修订命令。data2 余 1.3 TiB，已下载约 2,050 个多波束航次（data2 约 6.5 TB、data1 约 5.7 TB 原文件），三层全量放不下。

## 已定规格

选点（唯一现行规则）：`point_check_pass_basic`、原生质量 `good`、`valid_ping_navigation`，再按精确 ping 身份排除已确认的无效源导航 ping。数值、单位、格网与聚合沿用 10-25 产品：深度 m、向下为正，1′ 格，全点中位数、唯一三元组中位数、重复比例，聚合函数复用 `ncei.trackline.file_cells.aggregate_track_file`（不搬动它）。

处理单元：逐原文件 `mblist` 解码 → 选点 → 只把格网聚合所需列写入航次临时表 `<output>/_tmp/<cruise>/`；航次全部文件完成后聚合为 L2，写航次完成标记，删除临时目录。不写 staging 与 L1。

失败：某个受支持格式文件解码失败，记入逐文件清单，该航次不生成 L2、状态 `failed`，批次继续下一个航次。不支持的格式记入清单，航次用其余文件生成 L2，并在航次汇总中给出不支持文件数。

产出（`ncei/derived/swath_rebuild_20261112/`）：
- `cells_1min/<cruise>.parquet`：航次格 L2，列与 10-25 `file_cells_1min` 相同。
- `files.parquet`：逐源文件清单，含 filekey、源路径、格式、状态、原声束数，基础检查、原生质量 good/flagged/null/unknown、有效导航、排除 ping 各阶段计数及选入数。
- `cruises.parquet`：逐航次汇总与状态；源清单片段沿用 36 号的字段。
- `run_parameters.json`：输入根、选点规则、排除表路径与哈希、代码提交。

原文件根：`ncei/raw_round2/platforms_tree`（data2）与 `/mnt/data1/pub/ship/ncei/raw_round2/platforms_tree`（data1），可重复传入 `--raw-root`，两种目录布局（`<cruise>/`、`<ship>/<cruise>/`）都解析。航次清单取自 `ncei/manifests/round2_download_log.parquet` 中 `status=ok` 的平台树航次。filekey 与历史提取清单的定义保持一致，使排除表与旧产品可连接。

排除表：由 `processing_revision_20261025/swath/navigation_review/HNRO07RR/ping_navigation_review.parquet` 与 `navigation_review_hnro05rr/ping_navigation_review.parquet` 中 `source_navigation_invalid_confirmed` 的 19 个 ping 合成一个表，键为 filekey + 精确 ping 身份。HNRO14RR 的 v1∪v2 记录不进入默认选点；把它转换为同一种源键（借现有 staging 连接一次）保存在输出根，供敏感性变体使用。

## 包结构与命令

目标命令（`python -m ncei.swath <command>`）：
- `census`：逐航次格式与受支持状态。
- `run`：上面的流式重建，`--resume` 跳过有完成标记的航次，data2 余量低于 300 GB 时停在航次边界。
- `points`：按需为一个航次（可选文件列表、经纬度范围）生成 L1 点表，列与 10-25 `points_checked` 相同，供下游点级交付。
- `coverage`：读 L2，与严格层和六区域比较（现 37 号）。

模块按处理步骤分：源文件发现与 filekey、单文件解码（含导航匹配与 MB84 `.prj`）、选点、聚合、批次编排、CLI。批次编排不含科学计算；科学函数不读写目录。

`batch`、`extract`、`file-cells`、`manifest`、`quality-revision`、`navigation-revision`、`navigation-case-review` 及仅为它们存在的代码删除，记入 `docs/code_archive.md`。它们写出的产品留在磁盘不动。`ncei/analysis/seamount_candidate_delivery.py` 若导入被删函数，改为从新模块导入。

## 对照（新链路完成的条件）

1. NT05-06（MB84，38 文件）：L2 与 `processing_revision_20261025/swath/first_batch/NT05-06/file_cells_1min/` 逐行逐列相同；逐文件选入数与该批提取清单相同。
2. HNRO05RR：不加排除表与 `navigation_affected_extension/HNRO05RR/file_cells_1min/` 相同；加排除表与 `navigation_review_hnro05rr/HNRO05RR/file_cells_1min/` 相同。
3. HNRO07RR 加排除表：与 `navigation_review/HNRO07RR/file_cells_1min/hnro07rr__mb41.parquet` 相同（18,268 格）。
4. `points`：对 NT05-06 生成的点表与 10-25 `points_checked` 相同。
5. 试运行：RR0913 与两个 Tier B 航次（不同格式）、一个 data1 上的 Tier C 航次，报告计数、耗时、临时目录峰值。
6. 对照全部在 scratch 输出根进行；`python -m unittest discover _common/tests` 通过。

## 全量运行（主代理验收对照后启动）

全部已下载平台树航次，RR0913 先跑。先跑 `census`，不支持格式的处理方式由主代理决定。workers 由主代理按当时主机负载给定。

## 约束

- 允许改动：`ncei/swath/`、`_common/mbsystem.py`、`_common/tests/` 中 swath 相关测试、`ncei/analysis/seamount_candidate_delivery.py` 的导入行、`docs/code_archive.md`、`ncei/swath/README.md`、本任务目录。
- 不改：`ncei/trackline/`（只读，复用聚合函数）、`ncei/download/`、`ncei/code/`、台账、原文件、`ncei/derived/` 下现有产品。
- 不提交；完成后回报主代理。

## 状态

- 2026-11-12：任务创建，S 派出为 paseo agent ef6b00e2（codex gpt-6.1-sol，full-access）。
- 2026-11-12 主代理决定：L2 只写正式 23 列，选点规则记在 run_parameters.json，10-25 个案表多出的 selection_policy、navigation_case_review_affected 只报告结构差异。同一航次多种受支持格式：按格式求 ping 时间区间并集，无交叠则合并，source_type/source_completeness 用排序格式串（如 `ncei_mb56_mb57`），cruises.parquet 记 formats 与各格式计数；有交叠则不生成 L2、状态 `format_overlap`，逐航次由主代理决定（可能是同一 ping 的原始与处理两版）。旧 census 中 NBP0603、TN253（mb56/mb57）与 HLY1102（mb56/mb58）三例，S 先用现有 staging 算交叠。files.parquet 增加每文件 ping 时间起止。
- 2026-11-12 S 对照：四组 L2 23 列逐值差异 0（NT05-06 86 格；HNRO05RR 无排除 278、加排除 251；HNRO07RR 加排除 18,268），NT05-06 逐文件选入 38/38 相同。RR0913（2.23 GB 解码）：25,528,176 声束、23,801,097 选入、17,181 格；8/16/32 workers 吞吐约 6.9/16.8/23.0 MB/s，32 workers RSS 峰 9.0 GB、临时 2.2 GB。台账 12.17 TB 中受支持后缀原文件 8.96 TB（MB58 8.38 TB）。主代理定全量 32 workers、航次依次执行，估约 4.5 天。
- 2026-11-12：S 完成流式实现、规定对照、四航次试运行和 RR0913 的 16/32 workers 测速。记录见 `result.md`；待主代理决定全量并发与不支持格式处置。
