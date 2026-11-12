# MGD77T 来源质量点表与完整静态批次

## 完整 695 航次已交付

2026-10-25，完整静态批次已处理并核对全部 150,587,793 条原观测，
包括旧 XYZ 未收录的 25,739 条短记录。`points_raw/` 和
`points_checked/` 各 695 个文件，均保留全部原观测；两种选择各有
695 个航次格文件，空格网也保留来源状态。

| 量 | basic 对照 | 来源质量主选择 |
| --- | ---: | ---: |
| 选入原观测 | 119,751,714 | 105,457,041 |
| 航次格 | 1,266,224 | 1,235,712 |
| singlebeam 文件均衡合并格 | 966,856 | 959,389 |
| multibeam_ncei 文件均衡合并格 | 138,470 | 122,616 |

两个分支的格数分开报告，跨分支有空间重叠，不相加作为全球唯一格数。
逐航次数量表为产品根的 `source_comparison.csv` 与
`source_manifest.parquet`，包括原记录、短记录、旧 XYZ 可对应记录数、两种选入数、
NAV/BAT 移除并集/交集、缺测状态和两种格数。

来源质量实际移除并集为 14,294,673 点：
12,496,788 个导航拒绝点 + 2,025,974 个测深拒绝点 - 228,089 个重叠点。
`NAV_QUALCO` 未指定 132,506,377 条，`BAT_QUALCO` 未指定
144,115,023 条，统计范围是全部原记录。1/2 和未指定保留，未指定不标为 good。

全部 26 原字符串、数值、时刻、代码和身份字段逐记录核对差异为零。
150,562,054 条旧点记录的数值、缺测和 basic 标记完全复现；全部
1,266,224 个 basic 航次格的格号、点数、全点/唯一三元组中位数、
重复比例、均值和其他既有统计最大差均为零。
`legacy_source_quality_comparison.csv` 的 3,700 项 NAV/BAT 来源及 basic
代码频数与独立旧证据吻合，覆盖已有 692 点产品的全部航次。
`source` 频数包括短记录，`legacy_source` 按旧 XYZ 的字段数/有限坐标范围
统计，两个范围不混用。

既有 692 个预测保持 627 singlebeam、65 multibeam，并传入原始点、
质量点和航次格；未按过滤后几何重判。三个旧无点产品来源完整保留：

| 来源 | 原记录 | 全为短记录 | 分类 | 状态 |
| --- | ---: | ---: | --- | --- |
| alar02rr | 11,877 | 11,877 | unclassified | no_selected_depth |
| dnwh-bho | 4,217 | 4,217 | unclassified | no_selected_depth |
| dnwh-cho | 3,202 | 3,202 | unclassified | no_selected_depth |

全批有 35 个 `no_selected_depth` 状态，表示 basic 未选入深度，不等于
原文所有深度都缺测。`bh17-04` 至 `bh17-09` 仍有非缺测、非哨兵的原深度，
这些原值继续保留。全原记录的空/未给出深度为 21,210,040 条，等于旧 XYZ
范围的 21,184,301 条加 25,739 条短记录；另有 8,102 个既定哨兵。

主时间有 1,979,743 条可确定 UTC，148,608,050 条原日期/时刻有效且时区
未指定，主 UTC 保持缺测；原日期/时刻缺测及无效计数均为零。
未知时区只在明确命名的假设时间列提供兼容时间，不作为 UTC 事实。
时间不参与本轮测深选择。

## 五航次首批覆盖了实际接口差异

2026-10-25，指定五个完整源文件已生成 L1、两类 L2 和文件均衡合并格，
共保留 507,264 条原观测，包括 3,212 条短记录。26 个原字符串、全部
数值/时间/代码/身份字段与写出的点表逐记录核对差异为零；已有点表按显式
旧索引关联，basic 数值、缺测和选点复现；basic 格网全统计与旧格网核对。

| 航次 | 原观测 | 短记录 | 旧分类 | basic 选入 | 来源质量选入 | basic 格 | 来源质量格 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| ar1-06 | 338,605 | 0 | singlebeam | 319,989 | 291,031 | 1,000 | 879 |
| 29he20120507 | 62,930 | 0 | singlebeam | 62,759 | 62,740 | 11,796 | 11,794 |
| skq201818s | 102,290 | 0 | multibeam | 102,290 | 102,283 | 23 | 23 |
| cntl01rr | 237 | 10 | singlebeam | 0 | 0 | 0 | 0 |
| dnwh-cho | 3,202 | 3,202 | 无旧点产品，未分类 | 0 | 0 | 0 | 0 |
| 合计 | 507,264 | 3,212 | | 485,038 | 456,054 | 12,819 | 12,696 |

首批移除并集 28,984 点，覆盖双质量码、无观测列标题、multibeam 预测、
部分短记录及全无深度来源。完整批次复用首批已核对点和格网，不重建。

产品与读取说明：
`ncei/derived/processing_revision_20261025/trackline/README.md`。
主点表为 `points_checked/<track>__mgd77t.parquet`；
主选择列为 `point_selected_basic_source_quality`，
basic 对照列为 `point_check_pass_basic`。

原身份为 `source_file`、`survey_id`、`source_line_1based`、
`source_observation_index_0based`、`source_field_count`，新密集索引
`point_table_row_0based` 与旧密集索引 `legacy_point_index_in_track`
分开保存。旧索引在原 XYZ 漏掉的短记录上为空，未把筛后行号当原观测行号。
全部 26 原字段保存为 `<FIELD>_raw`；`TIMEZONE/DATE/TIME` 也直接保留。
主时间只在时区已指定时为 UTC，假设时间列明确命名，时间不参与本轮选点。

## 正式头的实际格式

695 对源文件均存在并已读正式头：500 个 96 命名列扩展头、195 个
58 列头。新解析保留全部命名字段，不将目录扩展字段截掉。
其中 310 个原 `FORMAT_77` 为 `MG77T`，按该源文字面变体接受且不改写。

11 个头文件存在同一完整头/记录无换行重复粘连，重复记录相同；
6 个头文件的 PROJECT 文本内嵌换行。解析按完整命名列标题识别逻辑记录，
保留字段内的换行和原文件，只消除相同逻辑记录的解析歧义。

`NF1013L2/nf1013l2.h77t` 原文的 `SURVEY_ID` 为 `NF1013L1`，
观测文件和文件名均为 `nf1013l2`。新产品保留配套头原 ID，并设置
`source_header_survey_id_mismatch=True`；它不是 NF1013L2 已确认的机构
或改正证据。其他 694 个头的 ID 与观测文件匹配。既有 `read_header`
默认仍要求指定 ID 匹配，新静态模式显式允许并记录唯一配套头的不匹配。

正式 `BATH_INSTR/BATH_ADD/SOUND_VEL/VDATUM_CO/BATH_INTRP/ADD_DOC`
及全部目录字段写入 `source_headers.parquet` 和每个 L1 的 schema metadata。
`BATH_INSTR` 也保留在点表中，仪器预测从既有 manifest 继承，不按新几何重判。

## 独立入口不依赖历史产品或外仓核对表

共用入口从 `--source-root/*/*.m77t` 发现完整输入，本库未筛选来源和
既有 `manifest.depth_sign` 规则确定符号。外仓证据仅由可选
`--evidence-root` 提供历史比较，不是转换前提。
`--no-legacy-comparison` 不读取旧点表或旧分类表；可另用
`--classification-manifest` 传入已保留预测。无预测时保留 `unclassified`
点和航次格，不混入 singlebeam/multibeam 合并。未实际核对旧点表时，旧索引为空。

已实际执行独立 `ar1-06`，未传入外仓证据且禁用历史读取：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 POLARS_MAX_THREADS=1 \
/opt/miniforge3/envs/torch29/bin/python -m ncei.trackline mgd77t-fragments \
  --source-fields --workers 1 --tracks ar1-06 --no-legacy-comparison \
  --source-root ncei/raw_round2/mgd77t_static \
  --output-root ncei/derived/processing_revision_20261025/trackline/independent_source_check
```

保留 338,605 条原记录，basic 319,989 点、主选择 291,031 点；
basic 1,000 格、主选择 879 格。相对完整批次同源，77 个可比字段的全部
数值、原字符串、时间状态与两个格网的全部数值统计差异为零。
两个有意不同的字段是分类为 unclassified、旧点索引为空，反映没有历史输入，
不伪造来源判断。其 291,031 个主选点未进入任何已分类合并分支。

实际日志、独立比较 JSON 和复算脚本均在 `independent_source_check/`。
从仓库根运行
`python ncei/derived/processing_revision_20261025/trackline/independent_source_check/compare_with_batch.py`
可复核该比较。

`source_type=ncei_xyz/source_completeness=xyz_only` 是原聚合器/来源登记表的
兼容标签，不表示新产物只有 XYZ。`source_format=MGD77T`、26 原字段、
正式头、时间与质量列表达本轮实际保留的完整来源。

## 六研究区实际没有支持的本批交叉点

两种选择均已执行既有几何函数。只使用本批 627 个既有 singlebeam
预测，不包含 multibeam 或其他旧产品。原观测索引差必须为 1，
沿用 0.25° 间隔、0.05° 裁剪余量和 0.02° 候选格，不将筛后相邻表行跨接。

| 区域 | bbox 候选 | 主选择有段航次 | 主选择线段 | 实际交叉点 |
| --- | ---: | ---: | ---: | ---: |
| lon068_lat018 | 3 | 0 | 0 | 0 |
| lon052_lat018 | 14 | 2 | 6,186 | 0 |
| lon058_lat012 | 5 | 0 | 0 | 0 |
| lon059_lat015 | 7 | 1 | 23,300 | 0 |
| lon004_lat033 | 1 | 0 | 0 | 0 |
| lon021_lat010 | 9 | 1 | 244,772 | 0 |

basic 的六区交叉点也均为零。`lon059_lat015` 的 `rr2201` 有一个来源质量
移除点，点数从 23,332 降至 23,331，线段从 23,302 降至 23,300，
原索引断点从 6 增至 7，没有把删除点两侧连成一段。
两个有段航次的 `lon052_lat018` 没有共同候选格，其余有段区只有一个航次。
本批在这些区域没有可支持的航次交叉差，不估计零偏差或自动删航次。

复用 `RegionTracks/grid_candidate_pairs/exact_intersections/orient_and_filter/`
`pair_and_track_stats`。候选格按至少两个不同航次计数，修正了原代码把
同一航次在格内出现至少两段作为候选条件的判断。MGD77T 已知 UTC 可用于
事件方向；未知时区时只使用标明 arbitrary 的确定性顺序。
不采用任一倒序时刻拒绝整航次的规则，不做交叉点改正或重力差删点。

结果为 `crossovers/{basic,basic_source_quality}/` 下各六区的交叉点、配对、
航次统计 Parquet，及 `region_summary.csv`、`track_region_coverage.csv`、
`method.json`。空事件表有明确源身份列，不填造交叉差。

## 完整批次的复算与运行记录

复用 `mgd77t.py`、`point_qc.compute_flag_arrays`、
`file_cells.aggregate_track_file` 与 `merge_cells.merge_branch`。
既有 `mgd77t-xyz` 三列合同和 fragment 默认模式不变；
`mgd77t-fragments --source-fields` 才启用新源字段模式。

`source_quality_usable` 为 NAV/BAT 两项质量码均不在 3/4/5/6；
`basic_source_quality` 为既有 basic 与该列的交集。1/2 与未指定保留，
原码及未指定频数分别统计。`POS_TYPE/BAT_TYPCO/BAT_CPCO`、时刻、
观测/插值类型不加新硬阈值，不按待评价重力差删除。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 POLARS_MAX_THREADS=1 \
/opt/miniforge3/envs/torch29/bin/python -m ncei.trackline mgd77t-fragments \
  --source-fields --workers 2 --resume \
  --evidence-root /mnt/data2/06-Projects/11-swot-ssl-encoder/outputs/ship-source-processing-verification-v1 \
  --output-root ncei/derived/processing_revision_20261025/trackline
```

在新空输出根重建时去掉 `--resume` 并改输出路径；显式证据用于历史比较，
新完整来源转换可省略该项。旧 XYZ 三列合同及默认 fragment 模式保持原样。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 POLARS_MAX_THREADS=1 \
/opt/miniforge3/envs/torch29/bin/python -m ncei.trackline crossover \
  --source-points-root ncei/derived/processing_revision_20261025/trackline \
  --output-root ncei/derived/processing_revision_20261025/trackline/crossovers

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 POLARS_MAX_THREADS=1 \
/opt/miniforge3/envs/torch29/bin/python \
  ncei/derived/processing_revision_20261025/trackline/delivery_check.py
```

`first_batch.log` 记录五航次首批，墙钟 19.26 s、四类产物
84,286,111 字节。扩展前估算全批约 25 GB，保留不低于 40 GiB 的输出空间。
首次全批调用日志为 `full_batch.log`，实际完成 694 航次，日志起止间隔
4,094.48 s；`mgl1705` 的全缺测主 UTC 数组触发 pandas 内部浮点溢出。
时间写出改为只把有限秒值送入日期转换，缺测直接写为空。接续日志
`full_batch_resume.log` 仅计算该航次并复用其余 694 航次，完成汇总和四个
合并产品，墙钟 80.84 s。没有重做已通过的源记录比较。

实际逐航次四类产物合计 21,160,973,014 字节，含合并、独立比较、核对脚本
及报告的整根约 19.84 GiB。每块 100,000 原记录、最多两个计算进程，
数值库单线程；记录到的单个工作进程最大 RSS 为 2,210.62 MiB。
检查时 data2 仍余约 3.7 TiB。

`delivery_check.py` 已实际执行：检查 1,390 个点文件和 1,390 个航次格文件
的有效行数、头字段、单位、分类和选点数；复用全量源记录比较与旧数值/格网
比较，独立转换和六区输出均已读取。结果为 `delivery_checks.json`，
日志 `delivery_check.log`；完整汇总为 `comparison_summary.json`。
环境为 `/opt/miniforge3/envs/torch29/bin/python`，Python 3.12.12、
NumPy 2.4.1、pandas 2.3.3、Polars 1.41.2、PyArrow 24.0.0、
netCDF4 1.7.4。

六航次附加 FAA 已转换并逐记录核对，见 `additional_faa_result.md` 和
`legacy_faa_additional/README.md`。原 15 航次 FAA 根及其 267,343 位置表保持
原发布状态。当前完整 695、六 FAA 和交叉点计算进程均已退出，本执行阶段完成，
执行名额交回协调员进行来源状态结构化整理。
