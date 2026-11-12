# 多波束导航与投影修订

## 当前状态

2026-10-25，主机 `Precision-7920-Tower`。已修复 `process_one_file` 的 MB84
投影文件传递，加入逐 ping 原始导航的精确键匹配及声束字段。三个已知案例
已从原文提取到新目录，没有复用旧 `_work`。

六航次均完成原文重提取、全航次聚合和全记录数值对照：
1,508 个文件、121,116,093 条声束记录，源时刻、经纬度、深度、原生质量及
记录身份差异为零。数值导航选择为 99,359,551 个声束 / 60,124 个航次格，
合并为 57,703 个唯一格。两个批次的 `run_summary.json` 和根目录
`comparison_summary.json` 均为 `completed`。

后续授权的 HNRO07RR、HNRO05RR 两项源导航个案已完成，
当前研究合并指针为 `navigation_review_combined_cases/combined_ncei_cells_case_review.parquet`，
99,357,208 个选点 / 57,623 个唯一格；其他导航仍为 `not_reviewed`。

实际提取命令使用两个工作进程、数值库单线程：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
python -u -m ncei.swath batch --cruises HNRO07RR NT05-06 \
  --output-root ncei/derived/processing_revision_20261025/swath/first_batch \
  --extract --selection-policy basic_native_good_valid_ping_navigation --workers 2
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
python -u -m ncei.swath batch --cruises AII8L18 HNRO05RR HNRO06RR RR1412 \
  --output-root ncei/derived/processing_revision_20261025/swath/navigation_affected_extension \
  --extract --selection-policy basic_native_good_valid_ping_navigation --workers 2
```

首批执行句柄 `57576` / 启动 PID `2629613`，扩展句柄 `77761` /
启动 PID `2659573` 均已退出 0，没有停止状态的待续进程。
日志为输出根的 `first_batch.log`、`navigation_affected_extension.log`。
为把总提取并发维持在两个，扩展在首批合并末段临时等待，
其主进程及两个工作进程 `2659573/2659593/2659594` 曾为停止状态。
首批完成后已逐一 `SIGCONT` 恢复，四个扩展航次随后全部完成。
记录在 `swath/extension_resource_wait.json`，状态为 `resumed`；
没有暂停下载或其他项目任务。

## 六航次完整数值修订

| 航次 | 旧选点 | 新选点 | 无效导航 ping | 所属 beam | 旧格数 | 新格数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HNRO07RR | 37,723,275 | 36,435,030 | 18,299 | 1,659,933 | 18,337 | 18,325 |
| NT05-06 | 1,262,339 | 1,262,339 | 0 | 0 | 86 | 86 |
| AII8L18 | 4,218,532 | 4,218,494 | 15 | 285 | 4,162 | 4,159 |
| HNRO05RR | 963,793 | 465,699 | 3,843 | 572,607 | 288 | 278 |
| HNRO06RR | 9,876,800 | 9,780,182 | 672 | 100,128 | 7,013 | 7,002 |
| RR1412 | 47,198,643 | 47,197,807 | 2 | 864 | 30,281 | 30,274 |

旧选点共 101,243,382，新选点共 99,359,551，减少 1,883,831。
22,831 个无效源导航 ping 的全部所属声束为 2,333,817 条，包含原已不选入的
null/flagged 声束；全部无效理由均为精确零导航，非有限及越界 ping 数均为零。
旧观察的近原点 1,884,465 个选点 / 31 个唯一格在全六航次对照中得到复现；
数值导航修订后为 634 个选点 / 22 格，不把该描述性窗口作为删点条件。
7 个共同格的中位深度变化全部位于近原点窗口，窗口外共同格变化为零。

逐文件、航次和网格表分别为根目录的 `file_navigation_comparison`、
`cruise_navigation_comparison`、`cell_navigation_comparison`。
全部 L1/L2 选点数一致，1,508 个文件均为 `ok`；
6,032 条解压、U3、U0、源导航命令返回码全部为 0，
所有保留格的中位深度有限。`delivery_checks.json` 保留这些实际产品核对结果。

完整数值对照调用如下，沿用已完成的首批对照，不重复核对该批声束：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
python -u -m ncei.swath navigation-revision compare \
  --batch-roots ncei/derived/processing_revision_20261025/swath/first_batch \
                ncei/derived/processing_revision_20261025/swath/navigation_affected_extension \
  --reuse-comparison-root ncei/derived/processing_revision_20261025/swath/first_batch_comparison
```

HNRO07RR 移除的 1,288,245 个原选入声束全部属于 `(0,0)` 源导航，
声束位置与深度原值未变。近原点 `abs(lon)<0.1 & abs(lat)<0.1`
计数从 1,288,592 降为 347，相关航次格从 23 降为 11。
347 个声束来自三条有限、范围内、非零源导航；按本轮明确规则保留：

| filekey | UTC | native ping | 源经度 | 源纬度 | 选入声束 |
| --- | --- | ---: | ---: | ---: | ---: |
| 9cc351d9386a1a84 | 1999-07-03 06:40:28.259 | 389 | -0.0469416667 | -0.0137716667 | 105 |
| 08f3919303c7af7b | 1999-07-05 12:28:50.254 | 241 | -0.0507533333 | -0.0146966667 | 121 |
| c7699a5706dc689c | 1999-07-12 20:47:52.692 | 1367 | 0.0870916667 | 0.0266750000 | 121 |

这些是已发布数值规则下保留的记录，个案核对另存，不改写发布选择。
具体声束见
`first_batch_comparison/retained_near_origin_points.parquet/.tsv`。
非近原点的共同网格中位深度变化数为零。
近原点共同网格的最大中位深度变化为 1,399.54995 m。

首批 L1 与 L2 的 37,697,369 个选点数相等，540 个来源文件的
解压、U3、U0 与逐 ping 导航命令均返回 0。

## HNRO07RR 原生导航个案核对已完成

父代理授权的原 3 个 ping，及同一错误序列的邻接 11 个 ping，
共 14 个已按直接源记录确认为无效导航。独立目录
`ncei/derived/processing_revision_20261025/swath/navigation_review/` 保留
`ping_navigation_review`、`source_navigation_context`、`point_selection_overlay`、
`affected_cell_comparison`、`review_summary.json` 与读取说明。

三个文件的全部 2,627 个 `SB2100DR` 导航头与保留的 `mblist` 导航逐项对应：
时刻相等，坐标差小于 `1e-10` 度。错误序列紧接精确零导航段，
逐步靠近或经过原点；下一个 ping 回到原航段。
原 3 个目标到下一船位为 5.948 / 7.568 / 3.394 s，
对应约 13,625.553 / 13,812.444 / 13,799.977 km；
零段前、错误序列后航迹端点间距仅 3.308 / 2.975 / 0.778 km。
这是原档案的导航错误，不是声束偏移或本次读取造成。
具体生成步骤未确定，没有搜索或采用泛用半径、航速阈值。

| filekey | 确认无效导航记录索引，0起始 | 原生 ping | 全部声束 | 原选入声束 |
| --- | --- | --- | ---: | ---: |
| 9cc351d9386a1a84 | 385–388 | 386–389 | 604 | 424 |
| 08f3919303c7af7b | 237–240 | 238–241 | 604 | 484 |
| c7699a5706dc689c | 1361–1366 | 1362–1367 | 906 | 726 |

review 表用 `filekey + ping_navigation_record_index + epoch_us + native_ping_counter`
给出精确身份，保留源 DR 头、解压后字节位置、前后 ping 和零段外船位证据。
overlay 的 2,114 条记录保留原坐标、深度、native 状态和发布选择，
新增 `point_selected_basic_native_good_valid_ping_navigation_case_review`。
其余导航不标为全面 reviewed good。

研究选择移除 1,634 个原选入声束，包括原 3 个 ping 的 347 个近原点声束。
只读取并重聚合 58 个受影响格，57 格消失，1 格保留其他 ping 的 39 个声束；
该格中位深度变化为 +9.15015 m。其他 18,267 格沿用。
完整 HNRO07RR 研究格网为 36,433,396 个选点 / 18,268 格，位置：
`navigation_review/HNRO07RR/file_cells_1min/hnro07rr__mb41.parquet`。
已发布 `first_batch/` 和 `first_batch_comparison/` 均未重写。

实际结果调用：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
python -u -m ncei.swath navigation-case-review review
```

该次调用退出 0，源记录对照、58 格原聚合复现及研究 L1/L2 计数在同次计算中完成；
保留格中位深度均有限。未通过深度检查的原 null 声束继续保留 NaN。
六航次研究合并格网已生成，不重做本次个案提取：
`navigation_review/combined_ncei_cells_case_review.parquet`，
99,357,917 个选点、60,067 个航次格、57,647 个唯一格。
估计量仍为航次格中位数的非加权中位数。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
python -u -m ncei.swath navigation-case-review combine \
  --batch-roots ncei/derived/processing_revision_20261025/swath/first_batch \
                ncei/derived/processing_revision_20261025/swath/navigation_affected_extension
```

仅含 HNRO07RR 个案的保留版本仍有 HNRO05RR 的 287 个近原点声束 / 12 格，来自
`a4778b6cfe3209ba`、文件序号 15 的导航记录 176、177、178，
原生 ping 177、178、179；时刻分别为 1999-06-02 04:24:25.019、
04:24:33.569、04:24:42.129 UTC。原文件为
`roger_revelle/HNRO05RR/sb2100_vf.19990602-0500p.mb41.gz`。
这三个非零导航 ping 未纳入 HNRO07RR 个案；该版本保留数值选择及
`not_reviewed` 状态，不根据近原点窗口删除。
可读记录为 `navigation_review/retained_near_origin_points_case_review.parquet/.tsv`，
下节给出随后授权的 HNRO05RR 独立个案结果，不改写此保留版本。

## HNRO05RR 五个 ping 与双个案合并已完成

原文件 `roger_revelle/HNRO05RR/sb2100_vf.19990602-0500p.mb41.gz`、
文件键 `a4778b6cfe3209ba`、历史序号 15 的导航记录 174–178
由直接 `SB2100DR` 头及跨文件航迹证据确认为无效导航，
原生 ping 175–179。记录 173 为零船位，174–178 的非零船位依次趋向原点；
记录 179 在 8.564 s 后回到 `130.0010483333 E, 36.1805333333 N`，
与记录 178 的球面距离约 13,479.882 km。源档案已经含这些坐标。

当前文件从记录 0 起即为零导航，不能把本文件最后一条误作零段前的记录。
沿原文件顺序读取零段前记录：
`sb2100_vf.19990601-2100p.mb41.gz`、文件键 `bb4c79475eab436f`、
序号 7、导航记录 8、原生 ping 9，1999-06-01 19:59:57.960 UTC，
`132.042995 E, 36.907390 N`。其后 3,689 条零导航跨越 9 个文件，
直到当前文件记录 173；零段外前后航迹端点相隔 30,292.733 s / 199.513 km。
9 个文件的 3,957 条原文 DR 导航时刻与保留 mblist 相等，坐标差在
`1e-10` 度内。仅 174–178 标 `invalid_confirmed`，其他导航仍非 reviewed good。

独立目录 `swath/navigation_review_hnro05rr/` 保存：
5 行 `ping_navigation_review`、3,957 行 `source_navigation_context`、
745 行全部所属声束的 `point_selection_overlay`、27 格 `affected_cell_comparison`、
`review_summary.json`，以及 7 份 `source_record_ranges/*.bin` 原字节区间。
7 份区间对应五个错误 ping 和两个跨文件端点，共 104,475 bytes；
表中给出完整文件/ping 身份、解压字节起止位置，原 DR 头与船位保持原值。

研究选择排除 709 个原选点，287 个在描述性近原点窗口内，422 个在窗口外；
原目标三个 ping 的全部选点为 427 个，287 只计其中窗口内的声束。
27 个受影响 HNRO05RR 航次格均失去全部选点，其余 251 格沿用。
完整研究格网为 464,990 个选点 / 251 格：
`navigation_review_hnro05rr/HNRO05RR/file_cells_1min/hnro05rr__mb41.parquet`。

同时包含 HNRO07RR、HNRO05RR 两项个案的当前研究合并格网为
`navigation_review_combined_cases/combined_ncei_cells_case_review.parquet`：
99,357,208 个选点 / 60,040 个航次格 / 57,623 个唯一格。
精确确认无效的源 ping 共 19 个，移除的原选点共 2,343 个。
相对仅含 HNRO07RR 个案的版本，24 个唯一格消失，3 个共同格保留其他航次贡献，
中位深度变化为 −177.75、−129.65、−72.50 m；其他合并格完全相同。
这 27 格的合并对照为 `hnro05rr_combined_cell_update.parquet/.tsv`。

双个案选择的描述性近原点剩余表为 0 行，保留
`retained_near_origin_points_case_review.parquet/.tsv`。
筛选依据仍是上述精确源记录，其他导航状态为 `not_reviewed`。
已发布 `first_batch/`、`navigation_affected_extension/`、全记录数值对照和
HNRO07RR `navigation_review/` 均未重写。

实际执行命令：

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
python -u -m ncei.swath navigation-case-review review \
  --cruise-dir ncei/derived/processing_revision_20261025/swath/navigation_affected_extension/HNRO05RR \
  --output-root ncei/derived/processing_revision_20261025/swath/navigation_review_hnro05rr
python -u -m ncei.swath navigation-case-review combine \
  --batch-roots ncei/derived/processing_revision_20261025/swath/first_batch \
                ncei/derived/processing_revision_20261025/swath/navigation_affected_extension \
  --review-roots ncei/derived/processing_revision_20261025/swath/navigation_review \
                 ncei/derived/processing_revision_20261025/swath/navigation_review_hnro05rr \
  --output-root ncei/derived/processing_revision_20261025/swath/navigation_review_combined_cases
```

两个入口均退出 0。复现原 27 格聚合后完成受影响格重聚合，双个案格网点数、
航次格数与合并计数一致，格中位深度均有限；未重提取六航次或重复全记录比较。
实际核对保存于 `navigation_review_combined_cases/delivery_checks.json`。

## 输入与空间

新输出根：`ncei/derived/processing_revision_20261025/swath/`。
输入表 `input_batches.tsv`；原文及辅助文件逐一核对表
`input_integrity.parquet`，6,142 行，路径存在且大小与成功下载记录一致。
`input_integrity_missing.tsv` 无数据行。所有六个目标航次均有
`first_batch_complete:<数量>` 记录，无 `.part`。

首批原完整性证据：
`ncei/derived/mb_round2/_runs/20261019T195752Z_first_batch/` 下的
`download_final_status.tsv`、`completeness_manifest.tsv`、
`gzip_preflight.tsv` 及 `download_<cruise>.json`。
全局 `mb_round2/completeness_manifest` 未收录这六个航次，
本次不将该缺项解释为下载不完整。

| 航次 | 主数据文件 | 含辅助文件的输入数 | MB84 投影文件 |
| --- | ---: | ---: | ---: |
| HNRO07RR | 502 | 2,008 | 0 |
| NT05-06 | 38 | 190 | 38 |
| RR1412 | 736 | 2,944 | 0 |
| AII8L18 | 19 | 148 | 0 |
| HNRO05RR | 17 | 68 | 0 |
| HNRO06RR | 196 | 784 | 0 |

估算依据为旧 L1/L2 与 staging 的合计大小乘二，预计新增
34,239,697,660 bytes（31.89 GiB），另保留两个文件的暂存空间。
实际产品约 16.2 GiB，处理后 data2 剩余约 3.71 TiB；
实际字节数及检查时空闲量见 `delivery_checks.json`。
`resource_estimate.json` 保留启动时空闲量与估算。

## 已完成的源记录案例

`source_case_manifest.parquet` 和 `source_cases/<cruise>/_staging/` 保留三份
真实重新提取结果；每个 `_work/<filekey>/` 有 `source_metadata.json`、
`command_ledger.jsonl`、`ping_navigation.parquet`。
三个源案例的 L1/L2 已完成，实际选点/格数分别为
NT05-06 3,764/5、HNRO07RR 36,764/27、RR1412 106,356/44。
源案例的经纬度、深度、时间、原生质量与原 staging 全记录一致，
差异数为零，结果见 `source_case_comparison.json`。

- NT05-06，`53c68499f582da86`：5,040 个声束、40 个 ping，
  复制原文件同名 `.mb84.prj`，定义 `UTM54N`。
- HNRO07RR，`9851abb37f3e8ea6`：116,723 个声束、773 个 ping，
  488 个源导航为 `(0,0)`。
- RR1412，`9bc4e705ecd998d8`：123,984 个声束、287 个 ping，
  2 个源导航为 `(0,0)`。

对实际 MB84 原文副本移去投影依赖的正式入口调用返回
`failed:FileNotFoundError`，记录在 `missing_projection_result.json`；
该失败案例不混入完成产品。

## 接口与选择

旧 `basic`、`basic_native_good` 策略保留。新多波束产品显式使用
`basic_native_good_valid_ping_navigation`：
`point_check_pass_basic & (native_quality_state == "good") & valid_ping_navigation`。
未提取源导航的旧 staging 合并时保留未知导航，不伪造 valid；
旧策略仍能处理它们。新批次策略拒绝缺少源导航的输入。

共享聚合器还增加 `basic_source_quality`：
`point_check_pass_basic & source_quality_usable`，供 MGD77T 执行者复用；
没有更改其他 trackline 模块。

## 来源物理改正状态

本次不另做声速、姿态、吃水或潮位改正。具体来源状态由协调员整理。
HNRO07RR 已知案例的原 `.inf` 声明 Corrected Depths:YES、
Tide Corrected:NO、Draft:6m；原文件头另有 2003 年 mbprocess 的用户声速剖面
射线追踪、CORRECTED 测深参考、潮位关闭记录。RR1412 的已知 `.inf`
记录 SVP/SSV 存在，不单独证明改正完成。来源证据保持具体文件范围。

HNRO14RR 不在本轮六航次中，沿用既有诊断：
`.trellis/tasks/10-21-mb-round2-quality-revision/research/hnro14rr_diagnosis.md`；
`ncei/derived/mb_round2/_runs/20261021_hnro14rr_diagnosis/affected_records.parquet`、
`affected_records_v2.parquet` 与
`v2/affected_records_v1_union_v2.parquet`。
这些是已有源记录诊断和敏感性记录，不在本轮自动转成删除规则。
