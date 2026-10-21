# HNRO14RR 原生 good 异常记录诊断

2026-10-21，R2。结论：**源记录异常。初始 34 点的异常水深和长旅行时已写在原始 SeaBeam 文件中，不是本仓库的单位、符号、时间连接、声束排序或导航投影错误。** 无须为这 34 点修改 `34_mb_round2_extract_points.py` 的深度提取或导航计算。

诊断产物：

`ncei/derived/mb_round2/_runs/20261021_hnro14rr_diagnosis/`

以下文件名均相对于该目录。只读原始文件、旧 staging 和旧 L1；未改动原值、旧结果或生产代码。

## 1. 从 34 个 staging 行定位到源记录

原文件：

`ncei/raw_round2/platforms_tree/roger_revelle/HNRO14RR/20070726161003120_sb2100_vf.20000203-2400p.mb41.gz`

staging：`HNRO14RR/_staging/437e75255a42abdc.parquet`，`file_ordinal=119`。

34 点位于 staging 的 0 起始行 11508 至 13925，分布在 13 个 ping。ping 序号为 77 至 93，声束索引为 30 至 37。源时间为 **2000-02-03 23:22:05.994 至 23:28:04.020 UTC**。文件名前缀 `20070726` 不是这些观测的采集日期。

本文件每个 DR 记录有 151 个声束。`mblist -ON` 在该格式中提供本次读取的 1 起始 ping 序号，源 DR 头没有单独的仪器 ping 编号；`#` 是 0 起始声束索引。这里满足：

```text
staging_row = point_index_in_file = (ping_number - 1) * 151 + beam_index
```

逐点对应见 `initial_34_records.tsv`。该表保留源 DR 和声束行的解压后字节偏移、完整 ASCII 行、量程、旅行时、船位、声束偏移和 staging 值。

| cell_id | 初始点数 | NCEI 中位水深 / m | JAMSTEC 中位水深 / m |
|---|---:|---:|---:|
| 1min_7701_18851 | 2 | 10394.0 | 2357.8160 |
| 1min_7702_18851 | 29 | 10186.0 | 2355.1575 |
| 1min_7702_18852 | 3 | 10300.0 | 2403.7970 |

该表由 `build_outputs.py` 重新读取 JAMSTEC `median_depth_file_balanced` 得到，产物为 `initial_cells_reference.tsv`。JAMSTEC 只用于复现初始对照，未用其水深改写任何点。

## 2. 原始深度、量程和质量码

固定环境中的 `mbinfo` 识别为 `MBF_SB2100RW`，格式 41。源元数据记载 `METASONAR:Seabeam_2112`，属于这里使用的 SeaBeam 2100 系列格式；原文件包含 ASCII 测深 DR 记录和二进制侧扫 SS 数据。源元数据中人工编辑和自动编辑均为 0。

直接解析 DR 字段的依据为 MB-System **5.8.3beta16** 官方源码，已保存到 `mbsystem_source/`：

- `mbf_sb2100rw.h` 的 `range_scale` 定义：`D` 为 m，`I` 为 0.1 m，`S` 为 0.01 m。
- `mbr_sb2100rw.c:550` 起读取 DR 时间和船位；`:584` 读取量程；`:668` 读取声束行第 17 至 21 字节的深度整数；`:674` 读取第 42 字节质量码。字节索引从 0 起始。
- `mbr_sb2100rw.c:1126` 按量程把深度、横向和沿航向偏移换成 m。
- `mbsys_sb2100.c:209` 起把空格质量码映射为不加旗标的声束；`:221` 输出源深度。

源文件本身存在以下两个可直接核对的例子：

| staging_row | ping / beam | 深度整数 | 量程 | 原格式换算 / m | staging / m | 源旅行时 / s | 源质量码 |
|---|---|---:|---|---:|---:|---:|---|
| 11508 | 77 / 32 | 10300 | D | 10300.0 | 10300.0000 | 18.924 | 空格 |
| 12261 | 82 / 30 | 89967 | I | 8996.7 | 8996.7002 | 17.138 | 空格 |

第二行的尾数来自 MB-System 内部 float32 和四位小数输出，不是量程错误。34 点同时包含 D 和 I 量程，换算结果均与 staging 一致。旧 `extraction_summary.json` 的 `sign_flip=1.0`，本例没有符号翻转。

34 点均来自 `W` 测底算法记录，质量字符均为空格；`mblist -U0` 全部输出这些声束。`good` 表示源记录未给它们加旗标，不代表进行了独立的准确度核对。

34 点的源旅行时为 **16.633 至 19.706 s**，源横向偏移为 **−10478 至 −8492 m**。异常不是仅存在于深度列的放大：原始旅行时和横向距离也已经很大。具体声学原因，例如错误测底检测、干扰或采集端处理，不能仅靠该归档文件区分。

## 3. 时间、导航和 U3/U0 连接

对文件 117、118、119、120、121 共 **417364 行、2764 个 ping** 执行原命令等价的 U3/U0 重解码，再与旧 staging 按原行顺序比较：

1. 所有行的时间、ping 序号、声束索引与直接读取的 DR 记录对应。
2. 所有 staging 行的位置、深度和时间与此次 U3 输出一致；位置比较仅容许经度归一化的浮点尾差。
3. 以 `(time_us, ping_number, beam_index)` 比较 U0/U3，键唯一；所有 U0 行均能对应 U3；U0 行数量及逐行 `good` 状态与 staging 一致。
4. 所有 DR/SS 配对的时间、船位和量程相同，没有把一个 ping 的深度连到另一时刻的导航。
5. 按 DR 船位、航向和源横向/沿航向偏移，独立重建声束位置。与 mblist 的最大经纬度差均小于 **5.1×10⁻¹¹ 度**，与其十位小数输出一致。
6. 直接读取源整数、应用量程和 float32 后，与 mblist 深度的最大绝对差小于 **0.00005 m**，来自四位小数文本输出。

例如行 11508：源船位为 134.138423333°E、38.452596667°N，航向约 233.902°；源横向偏移为 −9875 m。换算后的声束位置为 134.203871875°E、38.380026132°N，与 staging 一致。staging 中的位置是声束落点，不是把船位错误写成了声束位置。

目标时段及紧邻 ping 的船位变化对应 6.742 至 7.048 m/s，时间顺序正常。该时段没有能够解释公里级深度差的导航跳变证据。

仓库提取路径为 `34_mb_round2_extract_points.py:process_one_file` 的 `mblist -F41 -P1 -L0 -MA -U3/-U0 -OMN#XYzH`，随后进入 `scs_v2_stage_c_processing.py:_raw_from_object_impl`。后者在第 874 行按时间、ping 和声束键连接，并在第 913 行起核对同键值；深度来自 U3 的原值，没有按相邻时刻插值。

完整对照在 `source_staging_comparison.parquet`；每个文件的检查结果在 `neighboring_files.tsv`。

## 4. 同一 ping 和相邻文件

将目标首末 ping 之间的 17 个 ping 全部展开，而非只取最初三个网格：

| 声束范围，0 起始 | 有限深度点数 | 最小水深 / m | 中位水深 / m | 最大水深 / m |
|---|---:|---:|---:|---:|
| 左舷 30–38 | 127 | 5280.6001 | 9048.5996 | 11617.0 |
| 中央 60–90 | 527 | 1456.0 | 1622.4 | 1798.6 |
| 右舷 112–120 | 153 | 1644.0 | 1797.0 | 1907.5 |

127 个左舷点包括初始 34 点，分布于 **11 个网格**。其中 126 点通过旧基础范围检查；另一个点为 11617 m，已被 11500 m 上限挡住。中央声束和对侧声束仍构成较平滑的水深序列，异常集中在左舷长旅行时声束。

`same_ping_all_beams.parquet` 保存这 17 个 ping 的全部 2567 行，包括 null 以及异常段与中央声束之间的过渡记录。`same_ping_sectors.tsv` 保存上表；`neighboring_pings.tsv` 保存五个文件的逐 ping 船位、时间、深度分布和正下方声束深度。

相邻文件不是空白对照，117、118 和 120 也存在同类左舷长旅行时深度尾部。文件 120 的异常尾部逐渐收缩；文件 121 的全部有限深度为 763.9 至 1017.5 m。

## 5. 已定位记录清单及范围

`affected_records.parquet` 共 **3633 行**，以 `(staging_stem, staging_row)` 唯一定位原 staging 点。深度和坐标保留原值，`diagnosis_state` 与 `native_quality_state` 分开：

| 文件序号 | 源中已存在的 >5000 m 点数 | 通过旧基础检查 | 点所在网格数 | 时间范围，UTC |
|---|---:|---:|---:|---|
| 117 | 874 | 869 | 55 | 2000-02-03 20:59:43.732 至 21:48:09.348 |
| 118 | 997 | 997 | 32 | 2000-02-03 22:10:01.001 至 22:58:14.720 |
| 119 | 1576 | 1575 | 76 | 2000-02-03 22:58:30.843 至 23:58:11.210 |
| 120 | 183 | 183 | 20 | 2000-02-03 23:58:28.562 至 2000-02-04 00:12:39.317 |

这 **3630 个有限深度点**全部原生 good，直接源解码确认其深度、旅行时和声束对应关系；状态为 `source_encoded_extreme_depth`。检索下限 5000 m 用于界定这次相邻文件的深度尾部清单，并未写入生产 QC；它不表示 5000 m 以下的过渡声束已证明可靠。清单不是全航次异常点的穷尽分类。

文件 117 还存在 **3 条原格式畸形记录**：staging 行 6831、7585、7888，分别为 ping/beam 46/36、51/35、53/36。声束行实际长 44 字节，规范字段长 43 字节；深度整数占用了 6 位，使后续字段错位。按扩展字段解释，其深度分别可能为 10082.9、10185.1、10026.9 m。该解释只保存在 `overflow_depth_hypothesis_m`，没有回填深度。这三行原 staging 均为 null、`depth_raw=NaN`，已不通过基础检查；状态为 `source_fixed_width_depth_overflow`。

合计 3633 条记录所在网格去重后为 **179 个**。真正影响“基础检查通过且原生 good”选点的为 **3624 点、177 个网格**；6 个 >11500 m 点和 3 个 null 已被旧基础检查排除。逐网格清单见 `affected_cells.tsv`，逐文件和诊断状态见 `affected_files.tsv`。表中 `initial_34` 与 `same_port_sector_17_pings` 可以分别重建初始样本和 127 点源内对照范围。

读取整个航次已有 staging 的同口径尾部盘点得到 9233 个 >5000 m 点，其中 **5603 点**来自文件 51–55、67、116，未在本次重解码中读取其原文件。它们保存在 `cruise_staging_depth_gt5000_inventory.parquet`，`raw_verified_in_this_diagnosis=False`，不混入已核对原文的 `affected_records.parquet`。该盘点说明不能把初始三格修正后的覆盖解释成全航次来源问题已解决。

## 6. 对修订版处理的结论

这次诊断不支持修改深度比例、正负号、经纬度或时间连接。直接重解码已复现旧 staging。R1 恢复原生质量和点溯源的工作仍有必要，单纯筛除 flagged 不能去除这里的 3630 个原生 good 尾部点。

主代理可用 `affected_records.parquet` 的精确键做“保留”和“暂不采用已定位记录”的敏感性对照，影响新选点的键为其中 `point_check_pass_basic=True` 的 3624 条。这个对照只解释本次已定位记录的影响，不自动删除整个航次，也不校正其深度。正式质量判断还需覆盖同一时段的过渡声束及其他已发现尾部时段。

具体声学故障尚未确定。若要校正而非仅定位，需要该航次原始声学记录或厂商处理输出、仪器配置及采集日志、对应声速剖面和独立导航记录。仅靠现有的深度、旅行时和编辑标记，不能决定替换水深。

## 7. 复算

在仓库根目录执行，Python 使用现有 `/opt/miniforge3/bin/python` 的 pandas、numpy、pyarrow。所有原始文件读取均使用隔离模式，原路径通过参数传入。解压文件写入诊断目录的新子目录，不在 raw 中启动解释器。

```bash
cd /mnt/data2/00-Data/ship
D="$PWD/ncei/derived/mb_round2/_runs/20261021_hnro14rr_diagnosis"

# 首次诊断使用 $D/redecoded；复算使用尚不存在的新子目录。
python -I "$D/decode_files.py" \
  --repo "$PWD" \
  --raw-root "$PWD/ncei/raw_round2/platforms_tree/roger_revelle" \
  --output "$D/redecoded_repeat"

python -I "$D/inspect_records.py" \
  --repo "$PWD" --decoded "$D/redecoded_repeat" --output "$D"

python -I "$D/build_outputs.py" \
  --comparison "$D/source_staging_comparison.parquet" \
  --output "$D" --repo "$PWD"
```

原执行的外部命令及原路径保存在 `redecoded/decode_commands.json`；各文件的解压副本、U3、U0、`mbinfo` 和 stderr 保存在 `redecoded/file_117` 至 `redecoded/file_121`。原提取 ledger 也保留在旧 `HNRO14RR/_work/<staging_stem>/command_ledger.jsonl`。

官方源码快照的版本和地址模板为：

```text
https://raw.githubusercontent.com/dwcaress/MB-System/5.8.3beta16/src/mbio/mbr_sb2100rw.c
https://raw.githubusercontent.com/dwcaress/MB-System/5.8.3beta16/src/mbio/mbf_sb2100rw.h
https://raw.githubusercontent.com/dwcaress/MB-System/5.8.3beta16/src/mbio/mbsys_sb2100.c
https://raw.githubusercontent.com/dwcaress/MB-System/5.8.3beta16/src/mbio/mbsys_sb2100.h
https://raw.githubusercontent.com/dwcaress/MB-System/5.8.3beta16/src/mbio/mb_coor_scale.c
https://raw.githubusercontent.com/dwcaress/MB-System/5.8.3beta16/src/utilities/mblist.cc
```

旧航次提取清单的 `relpath` 省略了船名层级。复算通过 `--raw-root .../platforms_tree/roger_revelle` 恢复实际路径；原 extraction ledger 指向的也是这一船名目录。该路径问题不改变已解码记录的数值。

## Research Check

- 执行：`decode_files.py`、`inspect_records.py` 和 `build_outputs.py` 已产生本报告引用的表。
- 形状与单位：五文件 417364 行，staging 行位置、时间、ping 和 beam 对应；水深与声束偏移为 m，时间为 UTC，深度向下为正。
- 非有限值：128544 个原生 null 深度，三个格式畸形记录包含在内；经纬度与深度没有 Inf。未将 null 当作有效深度。
- 结果来源：报告数字来自该诊断目录的实际重解码、直接 ASCII 字段读取和明确标识的 staging 尾部盘点。
- 发现：初始 34 点在源文件中已经异常；五文件的 staging 与重解码一致；没有发现解释这些点的仓库提取错误。
