# 首批多波束质量修订

## 结果

13 个已提取航次已完成隔离重建。原生 good 选点将实际进入聚合的点数从
151,384,880 减到 144,129,182，去重后的 1′ 网格从 156,403 减到 154,949。
日本海 V006、V018、V029 和伊豆 55 个候选满足沿用的覆盖条件，
可以开始分来源的山顶与周边降深测量；该状态不表示已完成形态判断。

HNRO14RR 的源记录异常见 `research/hnro14rr_diagnosis.md`。
按 R2 已定位记录的精确键暂不采用 3,624 个原生 good 点后，
该航次从 4,084 格减到 3,983 格。三个初始极端网格没有剩余 NCEI 点，
不是残差降为零。仍与 JAMSTEC 重叠的 38 个受影响格中位残差为
1,652.50 m，记录排除对照没有解决该时段所有深度差异。

输出根目录为 `ncei/derived/mb_round2/_runs/20261021_quality_revision/`：

- 根目录：保留全部满足基础检查的原生 good 记录，下文简称“保留版”。
- `without_located_records/`：暂不采用 R2 已定位记录，下文简称“排除对照”。
- 两版都不改原始下载、原 staging、既有 L1/L2、旧 run 或生产主数据集。

## 方法与输入

选点为 `point_check_pass_basic & (native_quality_state == "good")`。
基础范围检查保持原义，标准化水深单位 m，向下为正，范围 `0 < depth <= 11500`。
原生 good 是选点条件，不作为测深准确性的判据。

34 号脚本从原有 staging 重建 L1，保留 `filekey`、`file_ordinal`、
`point_index_in_file`、`staging_row`、`native_quality_state`。
`staging_row` 为 staging parquet 的 0 起始行位置。
提取清单保留历史 `relpath` 与 `filekey`，新增的 `source_relpath` 相对于
`ncei/raw_round2/platforms_tree/`，来源片段 `source_path` 相对于 `ncei/`。
36 号脚本解析实际存在的直接航次或船名/航次目录，核对来源文件存在。

07 号聚合器的默认策略仍为 `basic`；本批入口显式传入 `basic_native_good`。
内存和分批读取共用选点函数，记录缺少原生质量字段时拒绝新策略，不伪造 good。
每个航次的最终选入数与 L2 的 `n_points_pass` 求和核对。

研究区仍为日本海 132–136°E、36–40°N 和伊豆 140–144°E、28–32°N。
候选覆盖使用完整 12.5 km 邻域、全球 1′ 网格实际中心、4 km 核心、8–12.5 km 环带和 8 方位扇区。
各来源及合并覆盖按 `cell_id` 去重；沿用的 0.6/0.5/0.25 条件仅记录覆盖状态。
逐航次残差按 `(track_id, cell_id)` 对照 JAMSTEC。
合并 NCEI 水深保持为航次格中位水深的中位数，不按点数加权。

只读输入：

- `ncei/derived/mb_round2/<cruise>/_staging/` 与对应提取清单。
- 旧 L2：`ncei/derived/mb_round2/_runs/20261020T_l2_l3_first_batch/`。
- 旧覆盖：`ncei/derived/mb_round2/_runs/20261020T_source_audit/`。
- JAMSTEC：`jamstec/multibeam/derived/cells_1min_qcfiltered/cells.parquet`。
- strict：`ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet`。
- 两区候选：`/mnt/data2/06-Projects/14-seamounts/outputs/20261019-vgg-pick-vs-ship-{japan-sea,izu-bonin}/candidates.csv`。

## 执行命令

所有命令从 `/mnt/data2/00-Data/ship` 执行：

```bash
python -m unittest _common.tests.test_mb_round2_quality -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python ncei/code/43_mb_round2_quality_revision.py --workers 4

# 已有隔离重建完成后，补充诊断统计；不排除记录。
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python ncei/code/43_mb_round2_quality_revision.py --workers 4 --resume \
  --diagnosis-records ncei/derived/mb_round2/_runs/20261021_hnro14rr_diagnosis/affected_records.parquet

# 复用隔离 L1 和未受影响航次 L2，重算 HNRO14RR 及全部分析表。
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python ncei/code/43_mb_round2_quality_revision.py \
  --output-dir ncei/derived/mb_round2/_runs/20261021_quality_revision/without_located_records \
  --reuse-l1 ncei/derived/mb_round2/_runs/20261021_quality_revision \
  --exclude-records ncei/derived/mb_round2/_runs/20261021_hnro14rr_diagnosis/affected_records.parquet \
  --diagnosis-records ncei/derived/mb_round2/_runs/20261021_hnro14rr_diagnosis/affected_records.parquet \
  --workers 4
```

两版 `run_summary.json` 均为 `completed`。执行环境、完整参数和命令在各自的
`run_parameters.json`，日志为 `with_diagnosis.log`、`without_located_records.log`。
使用 4 个工作进程，机器为 64 核。首次重建在核对 COOK09MV/PPTU11WT 的历史压缩文件名时停止；
修正为实际存在的解压文件路径后，用 `--resume` 继续，未重解码原文件。

零行文件的比例改为空值后，使用同一入口的 `quality_tables` 重算两版描述性表：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python - <<'PY'
import importlib.util
from pathlib import Path
p = Path("ncei/code/43_mb_round2_quality_revision.py")
s = importlib.util.spec_from_file_location("revision", p)
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)
d = m.PROD / "_runs/20261021_hnro14rr_diagnosis/affected_records.parquet"
for run, excluded in [(m.RUN_ROOT, None), (m.RUN_ROOT / "without_located_records", d)]:
    m.quality_tables(run, m.CRUISES, m.RUN_ROOT, excluded, d)
PY
```

代码位置：34 号脚本的 `staging_statistics`、`merge_cruise`；
07 号脚本的 `point_selection_mask`、`record_exclusion_mask`、`aggregate_track_file`；
36 号脚本的 `resolve_source_paths`；新入口
`43_mb_round2_quality_revision.py` 的 `rebuild_cruise`、`quality_tables`、
`expected_cells`、`coverage_metric`、`analyze`、`inspect_izu_sampling` 和
`compare_record_exclusion`。37 号脚本保持原状，新入口不调用其旧的区域分析路径。

## 已完成的检查

6 个小型回归检查通过，覆盖 native-good 选点、缺失质量字段、null/unknown、
staging 行号与 `skipped_exists` 计数恢复、内存/流式一致、已定位记录排除、
两种来源目录结构、重复网格去重及研究区边缘的完整邻域；
质量表检查覆盖诊断键名、最终选入数、文件格数、零行文件比例和 NT06-21 状态。

RR1412 样本 `761d2c6f1c51988d.parquet` 共 189,648 点：
good 163,975，flagged 25,673，null 0，unknown 0。
189,648 点均通过基础检查，新规则选入 163,975，排除 25,673 个 flagged。

1,923 条提取来源路径与 13 条航次来源路径均在磁盘上存在。
每个航次 L1 按实际策略选入数、文件质量表最终选入数与 L2 `n_points_pass`
求和一致。两版全部核心、环带和八扇区覆盖率均在 0–1 内。
NT06-21 在航次质量表中是未处理状态，点数、格数留空。
R2 的全部 3,633 个点键均能连接到新 L1，经纬度、深度、原生质量和基础检查状态逐条一致。

## 点数与有效网格

全批次共 172,191,502 行：good 144,132,221，flagged 7,269,206，
null 20,790,075，unknown 0。基础检查通过 151,384,880 点；
新选点保留 144,129,182 点，少 7,255,698 点。3,039 个原生 good
没有通过基础检查，所以 good 计数与最终选入数仍分开记录。

| 航次 | 旧实际选入点数 | 保留版选入点数 | 旧航次格数 | 保留版航次格数 |
|---|---:|---:|---:|---:|
| RR1412 | 53,560,845 | 47,198,643 | 31,770 | 30,281 |
| PD20IB02 | 6,524,786 | 6,117,977 | 8,910 | 8,683 |
| EW9508 | 7,131,934 | 7,131,934 | 26,088 | 26,088 |
| TN168 | 6,245,646 | 6,245,646 | 33,140 | 33,140 |
| NT05-06 | 1,374,954 | 1,262,339 | 94 | 86 |
| NT05-16 | 1,573,048 | 1,201,821 | 72 | 65 |
| AII8L18 | 4,218,532 | 4,218,532 | 4,162 | 4,162 |
| HNRO14RR | 15,643,210 | 15,643,091 | 4,084 | 4,084 |
| HNRO07RR | 37,723,275 | 37,723,275 | 18,337 | 18,337 |
| HNRO06RR | 9,876,800 | 9,876,800 | 7,013 | 7,013 |
| HNRO05RR | 963,793 | 963,793 | 288 | 288 |
| COOK09MV | 3,189,641 | 3,189,641 | 1,732 | 1,732 |
| PPTU11WT | 3,358,416 | 3,355,690 | 27,956 | 27,865 |
| 合计 | 151,384,880 | 144,129,182 | 163,646 | 161,824 |

旧点数来自旧 L2 的实际 `n_points_pass`，不是旧状态表错误标作
`l1_basic_pass_rows` 的数字。新 `run_status` 保留这两个旧字段以便核对；
提取清单中的 `skipped_exists` 计数已从 staging 恢复。

| 范围 | 旧去重格数 | 保留版去重格数 | 排除对照去重格数 | 保留版 strict 外新增格 |
|---|---:|---:|---:|---:|
| 全球 | 156,403 | 154,949 | 154,848 | 84,839 |
| 日本海 | 7,541 | 7,541 | 7,440 | 5,902 |
| 伊豆 | 13,902 | 13,581 | 13,581 | 1,512 |

完整数据：`run_status`、`coverage_stats_regions`、
`cruise_cell_quality_comparison`、`combined_ncei_cells`。
合并表每个 `cell_id` 一行，航次格表保留每个 `(track_id, cell_id)` 一行。

## 候选覆盖与测量安排

所有候选的连续核心、环带、八扇区覆盖在 `*_candidate_coverage`。
`*_candidate_quality_comparison` 固定修正后的几何，仅比较选点；
`*_candidate_historical_comparison` 对照前轮来源分析的实际输出。

选点变化使伊豆 V008 的 NCEI 环带覆盖从 0.224490 降到 0.214286，
V039 从 0.244898 降到 0.234694；两者均少一格，三来源并集覆盖不变。
日本海候选的选点覆盖没有变化。

新覆盖计算对分子和分母使用同一组实际网格中心及扇区归属，完整读取区域外邻域。
相对前轮来源分析，日本海 V050 和伊豆 38 个候选的最小扇区覆盖改变；
这些变化不能全部归因于质量选点。完整差值和八扇区序列保存在对照表。

| 日本海候选 | 并集核心覆盖 | 并集环带覆盖 | 最小扇区覆盖 | 当前测量安排 |
|---|---:|---:|---:|---|
| V006 | 0.952381 | 0.852941 | 0.583333 | 开始分来源的山顶及周边降深测量 |
| V018 | 1.000000 | 0.637255 | 0.250000 | 开始分来源测量，保留扇区覆盖差异 |
| V029 | 0.666667 | 0.911765 | 0.600000 | 开始分来源测量，保留核心覆盖差异 |
| V050 | 0.904762 | 0.833333 | 0.133333 | 扇区覆盖不足；邻域含 7 个已定位受影响格 |
| V052 | 0.904762 | 0.715686 | 0.000000 | 有空白扇区；邻域含 5 个已定位受影响格 |

日本海其余 83 个候选未满足沿用覆盖条件。伊豆可开始分来源测量的 55 个候选
见 `run_summary.json:regions.izu_bonin.begin_depth_measurement_ids`；
覆盖不足的 12 个是 V001、V004、V009、V018、V021、V022、V023、
V024、V028、V035、V037、V054。两版覆盖条件状态一致。
这些安排是测量起点，不是海山验证结果。

## 逐航次残差与伊豆格内位置

残差定义为 NCEI 水深减 JAMSTEC 水深，单位 m，正值表示 NCEI 更深。
`*_cruise_cell_residuals` 是逐航次格表，`*_residual_by_cruise`
与 `*_residual_by_source_combination` 分别报告独立航次和来源组合；
不能将后者解释成独立航次统计。

| 伊豆航次 | 重叠格数，旧→保留版 | 中位残差 / m，旧→保留版 | 绝对残差 P95 / m，旧→保留版 |
|---|---:|---:|---:|
| AII8L18 | 507→507 | −3.98→−3.98 | 213.46→213.46 |
| EW9508 | 654→654 | −63.98→−63.98 | 192.72→192.72 |
| NT05-06 | 43→41 | −112.54→−83.88 | 552.64→396.69 |
| NT05-16 | 10→8 | −326.24→−276.86 | 773.65→601.07 |
| PD20IB02 | 3,464→3,388 | 5.61→3.53 | 178.02→143.47 |
| RR1412 | 7,481→7,153 | 14.13→15.22 | 168.19→113.86 |
| TN168 | 1,771→1,771 | −45.40→−45.40 | 270.70→270.70 |

日本海保留版共有 1,706 条逐航次重叠格记录，合并后 1,639 格；
伊豆为 13,522 条、合并后 12,069 格。HNRO14RR 在日本海是 475 个独立航次格，
前轮单来源组合中的 456 格不代表其全部重叠范围。

两区 strict 层分别有 14,879 和 50,454 格，其 `source_provider` 和
`final_primary_source` 均为 `jamstec`。在本次 NCEI 重叠格上，strict 与 JAMSTEC
深度差均为 0。其 `source_dataset` 留有 `NCEI_multibeam` 字符串，
不能据此将 strict 当作第三套独立观测；实际来源列在 `*_strict_provenance`。

伊豆绝对逐航次残差最大的十格均来自 RR1412，差值为 1,405.80–3,181.06 m。
已读取这些格内的实际选入点以及 JAMSTEC 的 QC 后文件点，
核对 JAMSTEC 点数与其 file-cells 一致，并保存文件/测线分布和位置主轴。
两来源点质心相隔 313.92–948.10 m，部分 RR1412 格仅含 4–9 点且集中在格的一边。
这些采样差异不支持把同格残差直接当作海山高度误差，也不足以将公里级差值全部归因于陡坡。
十格均不在当前伊豆候选的 12.5 km 邻域内。

逐点位置、逐文件分布和质心比较见 `izu_bonin_focus_point_positions.parquet`、
`izu_bonin_focus_sampling`、`izu_bonin_focus_sampling_comparison`。
JAMSTEC 表的参考深度保持文件平衡中位数；位置检查中的汇总点中位数仅描述采样，
没有替换参考深度。`n_tracks=1` 只表示一个航次标识，不是独立重复测线数。

## HNRO14RR

R2 核对原始记录后确认异常已存在于源文件，提取程序无需修改深度、位置或连接逻辑。
诊断清单 `ncei/derived/mb_round2/_runs/20261021_hnro14rr_diagnosis/affected_records.parquet`
共 3,633 条：3,630 条源中极端深度，3 条固定宽度溢出的原生 null；
其中 3,624 条通过基础检查，涉及 177 格。排除对照按点键执行，
不以接近 JAMSTEC 为理由改深度、改位置或排除整条航次。

| 数量 | 保留版 | 排除对照 |
|---|---:|---:|
| HNRO14RR 最终选入点数 | 15,643,091 | 15,639,467 |
| HNRO14RR 格数 | 4,084 | 3,983 |
| 全批次选入点数 | 144,129,182 | 144,125,558 |
| 全批次航次格数 | 161,824 | 161,723 |
| HNRO14RR 日本海 JAMSTEC 重叠格 | 475 | 422 |
| HNRO14RR 日本海中位残差 / m | 22.793 | 14.718 |
| HNRO14RR 日本海绝对残差 P95 / m | 5,700.085 | 1,569.314 |

| 初始网格 | 保留版点数 | 保留版水深 / m | JAMSTEC / m | 保留版残差 / m | 排除后 |
|---|---:|---:|---:|---:|---|
| 1min_7701_18851 | 2 | 10,394 | 2,357.8160 | 8,036.1840 | 无 NCEI 点，残差为空 |
| 1min_7702_18852 | 3 | 10,300 | 2,403.7970 | 7,896.2030 | 无 NCEI 点，残差为空 |
| 1min_7702_18851 | 29 | 10,186 | 2,355.1575 | 7,830.8425 | 无 NCEI 点，残差为空 |

177 个受影响网格中 101 格失去全部 NCEI 点，76 格保留其他选入点。
与 JAMSTEC 重叠的格数为 91→38，中位残差为 3,864.32→1,652.50 m，
NMAD 为 2,530.75→576.29 m。这个对照包含样本范围变化。
只比较两版都有观测的同一组 38 格，中位残差为 2,135.22→1,652.50 m，
NMAD 为 1,247.27→576.29 m，绝对残差 P95 为 3,301.18→2,188.11 m。
每格的点数、水深、JAMSTEC/strict 残差及变化在排除对照的
`hnro14rr_located_cell_comparison`；汇总在 `hnro14rr_located_residual_summary`。

受影响候选仅为日本海 V050、V052。两版 NCEI 和并集的核心、环带及每个扇区
覆盖均不变，详见 `japan_sea_record_exclusion_candidate_comparison`。
它们邻域中的受影响格仍有其他点，不能由覆盖不变推断源记录问题已解决。
V050 的八扇区并集覆盖为
`1.000000;0.909091;1.000000;0.916667;0.133333;0.818182;1.000000;1.000000`，
V052 为
`0.533333;0.000000;0.384615;1.000000;0.800000;1.000000;1.000000;1.000000`。
两者继续需要区分测深来源，补充缺失方位的观测后再评估完整周边降深。

同航次文件 51–55、67、116 的另外 5,603 个大于 5,000 m 的点，
已由 R2 在 v2 中重新解码并核对原文，原始记录与 staging 一致。
它们未进入上述 v1 排除对照；其中 2,136 点命中 G1，0 点命中 F1，
进入文末 v1∪v2 并集的敏感性对照，实际影响选点的是 2,098 点。
116 号文件的 48 点全部在左舷，与 117–120 号文件的记录连续，
其中 31 点命中 G1；其余文件的尾部主要在右舷，不能统一归为同一种左舷机制。
5,000 m 仅用于和前轮盘点对账，不参与 G1，也不是质量筛选阈值。
已读取归档声速剖面；进一步区分声学机制仍需逐声束原始回波、时间门、
实际声速延拓设置或独立交叉测线观测，见 R2 报告第 8 节。

## 文件与航次描述性质量表

两版均生成 `file_quality_summary.parquet/.tsv`（1,923 行）与
`cruise_quality_summary.parquet/.tsv`（13 个处理航次和 NT06-21 共 14 行）。
计数包括总点数、四类原生质量、基础检查通过数、实际最终选入数、
排除前选入数和诊断记录排除数；文件格数应用该版本的实际选点。

974 个文件观察到 flagged，`has_native_edit_flag=True`；
949 个文件未观察到 flagged，该字段留空并说明尚未证实记录了编辑信息。
good/null 的存在或格式号本身不作为编辑完成的证据。
RR1412 有一个零行文件，比例留空，不写成零比例。
这些表没有稳定/不稳定或好/坏标签。HNRO14RR 几乎没有 flagged，
仍包含已由源记录确认的异常，选点不变不表示测深准确。

残差列按该文件所属航次的全部 `(cruise, cell)` 重叠格统计，
给出 n、中位数和 NMAD，不将每个文件的点单独重估水深。
NMAD 定义为 `1.4826 * median(abs(residual - median(residual)))`。
完整逐航次格残差在 `cruise_cell_reference_residuals`，包括只与 strict
重叠的格。诊断记录数仅表示 R2 已定位清单中的记录，不把 0 解释成排除了其他异常。
排除对照中 HNRO14RR 文件 117/118/119/120 分别少
869/997/1,575/183 个选入点，诊断记录数分别是 877/997/1,576/183。

NT06-21 保持“当前解析链未处理”，未补造 UTC，也未将其记作零覆盖。

## Research Check

- 执行：两版由统一入口完成，回归检查针对本次实际错误。
- 形状与单位：1′ 格、m、向下为正；文件键及 staging 行位置可追到实际源文件。
- NaN/Inf：有效覆盖率无 NaN/Inf 且在 0–1；无重叠、失去全部点、零行文件和未处理航次保留有意义的空值。
- 结果来源：本记录引用隔离 run 中实际生成的表；旧对照来自只读旧 L2 和来源分析。
- 发现：原生质量丢失、状态计数、来源路径与覆盖几何已修订；HNRO14RR 源记录异常和伊豆少数格的跨源差异仍需来源层面的判断。

## v1∪v2 扩展敏感性对照（2026-10-21）

第三版暂不采用 v1 尾部清单与 v2 的 G1/F1 清单的并集，
输出为 `ncei/derived/mb_round2/_runs/20261021_quality_revision/without_v1_union_v2_records/`。
原有保留版和 v1 排除对照保持原样，第三版复用保留版 L1 和未受影响航次的 L2。

G1 定位同一 ping、同一舷侧的声束落点次序反转，是有条件的几何冲突；
每对的两名成员都进入清单，不能据此确定哪一束有错。
F1 是声束行从 43 字节溢出到 44 字节的源格式错误。
第三版是暂不采用双方候选的敏感性对照上界，不是清洗后的产品。
此处的“上界”指候选记录的处置范围，不表示残差或误差存在数值上界。

实际 parquet 的 v1 为 3,633 条，v2 为 9,020 条，精确键交集为 **837 条**，
并集为 11,816 条、459 格。并集中 11,737 个原生 good 点通过基础检查，涉及 451 格。
任务补充消息中的交集 962 条已按实际键更正为 837 条；
单独使用 v2 会重新纳入 2,796 条仅属于 v1 的记录，所以本次使用并集。

### 运行与计数口径

从仓库根目录执行：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python ncei/code/43_mb_round2_quality_revision.py \
  --output-dir ncei/derived/mb_round2/_runs/20261021_quality_revision/without_v1_union_v2_records \
  --reuse-l1 ncei/derived/mb_round2/_runs/20261021_quality_revision \
  --exclude-records ncei/derived/mb_round2/_runs/20261021_hnro14rr_diagnosis/v2/affected_records_v1_union_v2.parquet \
  --diagnosis-records ncei/derived/mb_round2/_runs/20261021_hnro14rr_diagnosis/v2/affected_records_v1_union_v2.parquet \
  --baseline-diagnosis-records ncei/derived/mb_round2/_runs/20261021_hnro14rr_diagnosis/affected_records.parquet \
  --workers 4

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python ncei/derived/mb_round2/_runs/20261021_quality_revision/without_v1_union_v2_records/summarize_extended_sensitivity.py
```

43 号入口只作两处补充：允许用 `--baseline-diagnosis-records` 保留质量表的 v1 计数，
并将候选对照中的受影响格标注取自当前活动清单，避免沿用保留版的 v1 标注。
07、34、36 号脚本未改动。此次执行基于 E2/E3 重构后的仓库，
原有深度估计量和基础检查不变。

第三版 `file_quality_summary` 和 `cruise_quality_summary` 的
`r2_affected_record_count` 继续按 v1 计，合计 3,633；
新增 `r2_union_affected_record_count` 按 v1∪v2 计，合计 11,816。
`r2_count_scope` 与 `r2_union_count_scope` 分别记录清单路径和解释口径。
最终选入数与文件格数按第三版实际选点计算，不把 G1 候选数写成已确定的错误点数。

### 日本海残差与固定网格对照

以下统计均为 HNRO14RR 单航次格与 JAMSTEC 的比较，残差单位 m。
NMAD 定义同前；P95 使用绝对残差，数据表也保存有符号 P95，
本次所列各组的两者数值相同。

| 数量 | 保留全部 good | 暂不采用 v1 | 暂不采用 v1∪v2 |
|---|---:|---:|---:|
| HNRO14RR 选入点数 | 15,643,091 | 15,639,467 | 15,631,354 |
| HNRO14RR 全航次格数 | 4,084 | 3,983 | 3,964 |
| 日本海 JAMSTEC 重叠格数 | 475 | 422 | 419 |
| 日本海中位残差 / m | 22.793 | 14.718 | 14.470 |
| 日本海 NMAD / m | 59.528 | 53.181 | 52.496 |
| 日本海绝对残差 P95 / m | 5,700.085 | 1,569.314 | 1,357.939 |

扩展对照相对 v1 少 8,113 个选入点、19 个航次格。
全批次第三版为 144,117,445 点、161,704 个航次格、154,830 个去重格。

区域统计的格组随处置变化。固定三版都有 HNRO14RR 和 JAMSTEC 观测的
**419 格**后：

| 固定格组指标 | 保留全部 good | 暂不采用 v1 | 暂不采用 v1∪v2 |
|---|---:|---:|---:|
| 格数 | 419 | 419 | 419 |
| 中位残差 / m | 14.470 | 14.470 | 14.470 |
| NMAD / m | 52.496 | 52.496 | 52.496 |
| 绝对残差 P95 / m | 1,718.137 | 1,361.269 | 1,357.939 |

v1 对照中仍与 JAMSTEC 重叠的 38 个受影响格，
有 2 格在扩展对照中失去全部 HNRO14RR 选入点。
固定剩余的同一组 **36 格**：

| 原受影响格的固定格组指标 | 保留全部 good | 暂不采用 v1 | 暂不采用 v1∪v2 |
|---|---:|---:|---:|
| 格数 | 36 | 36 | 36 |
| 中位残差 / m | 2,103.818 | 1,652.500 | 1,626.020 |
| NMAD / m | 1,229.142 | 576.292 | 661.596 |
| 绝对残差 P95 / m | 3,175.284 | 2,200.041 | 2,190.141 |

38 格原有的 3,045 个剩余点中，482 点进入 G1 候选，
**2,563 点仍未由 G1/F1 解释**。将双方候选暂不采用后，固定 36 格的中位残差
仅从 1,652.500 m 变为 1,626.020 m，NMAD 从 576.292 m 变为 661.596 m。
这项扩展对照没有解释大部分剩余差异，也不能据此将未命中的点判为可靠。

三版逐格记录、共同格标记和汇总分别见新目录的
`three_version_hnro14rr_cell_residuals`、
`three_version_hnro14rr_residual_summary`、`three_version_hnro14rr_counts`。
其中 `japan_sea_three_version_common_cells` 为 419 格，
`v1_affected_three_version_common_cells` 为原受影响范围中的 36 格。

### 五个受影响候选的覆盖

与并集 451 个有效网格相交的候选只有日本海 V050、V052、V071、V076、V080，
各候选 12.5 km 邻域涉及 19、9、2、16、5 格。
伊豆没有候选与本次并集网格相交。

下表是 NCEI、JAMSTEC 和 strict 的网格并集覆盖，strict 仍不构成独立的第三套测深证据。
环带及最小扇区列为三版共同值：

| 候选 | 核心覆盖：保留 / v1 / v1∪v2 | 环带覆盖 | 最小扇区覆盖 | 沿用覆盖条件：三版 |
|---|---|---:|---:|---|
| V050 | 0.904762 / 0.904762 / 0.904762 | 0.833333 | 0.133333 | 均不满足 |
| V052 | 0.904762 / 0.904762 / 0.904762 | 0.715686 | 0.000000 | 均不满足 |
| V071 | 0.809524 / 0.809524 / 0.809524 | 0.333333 | 0.000000 | 均不满足 |
| V076 | 0.142857 / 0.142857 / 0.095238 | 0.401961 | 0.000000 | 均不满足 |
| V080 | 0.523810 / 0.523810 / 0.523810 | 0.372549 | 0.000000 | 均不满足 |

V076 的核心并集覆盖从 3/21 减到 2/21，NCEI 单层核心覆盖也有相同变化。
所有候选的环带和每个扇区覆盖均不变；其余核心覆盖也不变。
以下八扇区并集覆盖三版相同，扇区从正东方向起逆时针编号，每个扇区 45°：

| 候选 | 扇区 0 | 扇区 1 | 扇区 2 | 扇区 3 | 扇区 4 | 扇区 5 | 扇区 6 | 扇区 7 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V050 | 1.000000 | 0.909091 | 1.000000 | 0.916667 | 0.133333 | 0.818182 | 1.000000 | 1.000000 |
| V052 | 0.533333 | 0.000000 | 0.384615 | 1.000000 | 0.800000 | 1.000000 | 1.000000 | 1.000000 |
| V071 | 0.666667 | 0.000000 | 0.461538 | 0.083333 | 0.400000 | 0.000000 | 0.076923 | 0.833333 |
| V076 | 0.133333 | 0.818182 | 0.000000 | 0.166667 | 0.800000 | 0.909091 | 0.461538 | 0.000000 |
| V080 | 0.000000 | 0.636364 | 0.230769 | 0.666667 | 0.866667 | 0.000000 | 0.538462 | 0.000000 |

全部 153 个候选的沿用覆盖条件状态均未变化：
日本海仍为 V006、V018、V029，伊豆仍为 55 个满足条件。
这五个受影响候选继续受覆盖不足影响，G1 的条件几何冲突也仍需来源判断。
所有来源分层和八扇区序列见 `three_version_candidate_coverage`；
受影响候选单列在 `three_version_affected_candidate_coverage`，
变化记录在 `three_version_candidate_changes`。

### 5,603 个尾部点与 G1/F1 的交集

按 `(staging_stem, staging_row, file_ordinal)` 将前轮库存与 v1∪v2 并集连接：

| 文件序号 | 前轮尾部点数 | G1 命中并进入并集 | F1 命中 | 实际影响选点 | 未进入并集 |
|---|---:|---:|---:|---:|---:|
| 51 | 47 | 46 | 0 | 46 | 1 |
| 52 | 976 | 224 | 0 | 223 | 752 |
| 53 | 1,940 | 702 | 0 | 697 | 1,238 |
| 54 | 2,366 | 1,048 | 0 | 1,016 | 1,318 |
| 55 | 136 | 6 | 0 | 6 | 130 |
| 67 | 90 | 79 | 0 | 79 | 11 |
| 116 | 48 | 31 | 0 | 31 | 17 |
| 合计 | 5,603 | 2,136 | 0 | 2,098 | 3,467 |

进入并集的另外 38 个尾部点已被既有基础检查排除。
F1 记录原生为 null、深度为 NaN，不在有限深度大于 5,000 m 的这份库存中。
这些尾部点已核对源记录，不再记作“未经原文核对”；
其机制仍须按文件和舷侧区分，不能把共同的深度尾部解释成统一的左舷故障。
逐点成员关系和逐文件汇总保存在 `previous_5603_tail_membership` 和
`previous_5603_tail_membership_summary`，38 格中的点数核对见 `diagnosis_membership_summary`。
