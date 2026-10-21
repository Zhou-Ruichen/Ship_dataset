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

## 8. v2：几何冲突定位，不将候选直接判为坏点

2026-10-21 追加诊断。**5000 m 以下存在与长旅行时声束相邻的几何冲突；现有归档不足以划定全部异常点。** v2 使用旅行时、声束方向、名义波束宽度和归档声速范围，不使用 JAMSTEC 水深或水深检索下限。产出的 `affected_records_v2.parquet` 是几何冲突候选与格式错误的清单，不是已经逐条判坏的排除名单。

v2 共 **9020 条、402 格**，其中 **8943 个原生 good 点、394 格**通过基础检查。对 R1 保留的 38 个 JAMSTEC 重叠格，3045 点中 **482 点、31 格**参与几何冲突，**2563 点**未由该判据定位。不能把这 2563 点解释成已经可靠，也不能因剩余残差较大而将它们统一剔除。

### 8.1 完整 ping 对照和新增源记录核对

对文件 51–55、67、116 新增直接源解析与 U3/U0 重解码，累计核对文件 51–55、67、116–121 的 **820836 行、5436 个 ping**。新增文件的 staging 行位置、时间、声束、深度、位置和原生质量状态均与源解码对应。DR/SS 的时间、船位和量程也对应；未发现本仓库提取或导航连接错误。

76 个保留格的 4855 点逐格数量与 R1 的 `n_points_pass_excluded` 完全对应。表内格数存在跨文件重叠，不能相加。

| 文件序号 | 76 格内剩余点 | 其中 G1 候选 | 38 个重叠格内剩余点 | 其中 G1 候选 |
|---|---:|---:|---:|---:|
| 116 | 113 | 29 | 113 | 29 |
| 117 | 1683 | 181 | 1567 | 181 |
| 118 | 2080 | 644 | 1365 | 272 |
| 119 | 918 | 118 | 0 | 0 |
| 120 | 61 | 10 | 0 | 0 |
| 合计 | 4855 | 982 | 3045 | 482 |

逐点字段在 `v2/remaining_points_geometry.parquet`，含 ping、beam、原旅行时、声束方向、横向距离、测底算法、时间、中央声束参考和冲突角色；按文件、时间范围与声束范围汇总在 `v2/remaining_geometry_summary.tsv`。中央参考由每个完整 ping 的原生 good、格式正常的 60–90 号声束计算，不从目标网格裁剪后的点计算。76 格中有 89 点所在 ping 没有该中央参考，38 格中为 58 点；相关比值保留 NaN，没有插值。

新增核对得到 **32 条**原格式深度字段溢出，文件 52、53、54 分别为 9、14、9 条。连同 v1 的 3 条共 35 条，均为 I 量程、44 字节声束行、原生 null，原 staging 深度为 NaN。它们属于可确认的源格式错误，不会影响 `basic_native_good` 选点。

### 8.2 G1 的声学依据与计算

第一手依据为原厂《Multibeam Sonar Theory of Operation》（L-3 Communications SeaBeam Instruments，2000），本地文件 `v2/SeaBeam2100MultibeamTheoryOperation.pdf`，来源为 MBARI 的 MB-System 文档镜像。印刷页 4-1 给出 4/3 或 8/3 ms 采样间隔，4-11 给出 1° 声束间隔和 2° 波束宽度，4-24 至 4-28 说明 WMT/BDI 及时间门，4-29 至 4-31 说明声束方向、旅行时和声速剖面参与位置计算。

原文件确实包含 PR 声速剖面。已读取的剖面范围为 6–4500 m、1457.2–1526.0 m/s，完整值保存在 `v2/source_sound_speed_profiles.tsv`。这一发现补充第 6 节的资料需求：缺少的不是所有声速信息，而是归档之外的实际声速、深层延拓设置与原始回波证据。

MB-System `mbsys_sb2100.c:515` 起将 `angle_across` 和 `angle_forward` 输出为有符号发射角与方位角。设其为 θ、φ，表层声速为 c0，横向方向分量为 `u = abs(sin θ cos φ)`。定义：

```text
γ = asin(u)
h = 1° + 0.0005° + 0.005° = 1.0055°
p− = sin(max(γ − h, 0)) / (c0 + 0.005 m/s)
p+ = sin(min(γ + h, 90°)) / (c0 − 0.005 m/s)
δt = echo_length_samples × (8/3 ms) + 1 ms
T− = max(TWT − δt, 0) / 2
T+ = (TWT + δt) / 2
c− = min(1457.2, c0) − 0.005 m/s
c+ = max(1526.0, c0) + 0.005 m/s
X− = T− × p− × c−²
X+ = T+ × p+ × c+²
```

1° 来自名义波束半宽；0.0005°、0.005° 分别来自 0.001°、0.01° 源角度字段的半个量化间隔；声速补偿为其 0.01 m/s 字段的半个量化间隔。时间两侧均保留整段回波长度与 1 ms 源时间分辨率，没有设经验百分比。

在水平分层声速模型中，横向射线参数 p_x 守恒，单程 `dx/dt = p_x c(z)^2`，给出上述横向距离包络。它不把表观深度当成真深度，也不要求外侧声束落在中央声束的水平底面上。所有已核对原生 good 记录的源横向距离均在各自包络内。

G1 在**同一 ping、同一舷侧**寻找声束对 `(i, j)`：

1. i 的发射方向较内侧，考虑名义主瓣和字段量化后仍与 j 不重叠，即 `p+i < p−j`。
2. i 的完整横向距离包络在 j 外侧，即 `X−i > X+j`。
3. i 的旅行时支持区间晚于 j，即 `TWTi − δti > TWTj + δtj`。
4. 两束的沿航向扇面方向差不超过 2.011°，保留名义沿航向主瓣重叠的情况。

对于局部二维、连续海底的直达主瓣底回波，更内侧射线不应越过更外侧射线的首个海底交点后才落底。G1 定位这种落点次序反转。计算找到 **20586 对**；每一对的两名成员都进入候选表，`geometry_role` 标识 `long`、`short` 或两种角色，`example_pair_id` 连到 `v2/geometry_conflict_pairs.parquet`。

例如文件 118、ping 303，2000-02-03 22:48:04.735 UTC：

| 字段 | 较内侧 beam 34 | 较外侧 beam 31 |
|---|---:|---:|
| staging_row | 45636 | 45633 |
| 原深度 / m | 4875.3999 | 1793.9 |
| 原 TWT / s | 8.686 | 3.351 |
| 发射角绝对值 / ° | 41.001 | 44.001 |
| 原横向距离 / m | −4260.2 | −1685.8 |
| 横向距离绝对值包络 / m | 3976.3–4547.1 | 1627.1–1854.5 |

两点均低于 v1 的 5000 m 检索下限，横向支持区间仍反转 **2121.9 m**。可复算例子保存在 `v2/sub5000_conflict_examples.tsv`。

**G1 检查的是有明确条件的几何不相容，不是逐点错误真值。** 名义 2° 主瓣不是回波存在范围的硬截断；WMT 是门内加权到达时刻，不保证选中首个海底回波。G1 还假设局部海底在所比较的沿航向范围内可按二维连续剖面解释，使用归档声速包络；剖面在 4500 m 以下的实际声速与源处理延拓方式没有得到验证。旁瓣、多途、错误时间门、强沿航向地形变化或不适用的声速模型，都可能破坏这些条件。现有归档不能仅凭一对记录确定哪一束错，更不能确定统一的仪器故障机制。

源字段 `svp_correction=A` 的官方含义是 True Xtrack / Apparent Depth（`mbf_sb2100rw.h:130`），不是完整真深度。深度、横距和旅行时由同一测底结果生成，其相互一致不能作为独立海底证据。这里不采用“深于中央”“TWT 长于中央”或 W 算法作为排除规则；普通倾斜海底与正常外侧声束也可满足这些描述。

### 8.3 v2 范围与 38 格的解释程度

`affected_records_v2.parquet` 保留 v1 的全部列名和同一组键，增加 `scope_rule`、源角度、包络、冲突角色和配对索引。各行依据只有：

- `F1_source_fixed_width_44_not_43_bytes`：35 条已确认源格式错误。
- `G1_same_ping_nonoverlapping_2deg_mainlobes_reversed_x_support_both_members`：8985 条条件几何冲突候选；其中 8943 条通过基础检查，另 42 条超过既有 11500 m 上限。

| 文件范围 | G1 候选数 | F1 格式错误数 | 通过基础检查的点数 |
|---|---:|---:|---:|
| 51–55 | 5712 | 32 | 5674 |
| 67 | 901 | 0 | 901 |
| 116 | 120 | 0 | 120 |
| 117 | 459 | 3 | 455 |
| 118 | 1257 | 0 | 1257 |
| 119 | 446 | 0 | 446 |
| 120 | 90 | 0 | 90 |
| 121 | 0 | 0 | 0 |
| 合计 | 8985 | 35 | 8943 |

38 格内的 482 个候选中，184 点仅作为较内侧长回波成员，281 点仅作为较外侧短回波成员，17 点在不同配对中具有两种角色；470 点为 W，12 点为 B。不能把这 482 点统称为已经证实的长回波坏点。

未进入 G1 的 2563 点分为：

- 1774 点为左舷、深于本 ping 中央中位值且 TWT 更长的记录；这是描述，不足以判坏。
- 638 点位于 60–90 号中央声束范围；中央位置也不构成准确度证明。
- 151 点属于其他情况或缺少中央参考。

逐格解释表为 `v2/retained_cells_v2_explanation_with_reference.tsv`。G1 涉及 38 格中的 31 格，若将双方候选都暂不采用，2 格失去剩余点，36 格仍保留。固定这同一组 36 格，HNRO14RR−JAMSTEC 的中位残差仅由 **1652.50 m** 变为 **1626.02 m**。这项对照在 G1 规则固定后计算，未参与选点。残差结果表明 G1 没有解释大部分剩余差异。

这 38 格的 JAMSTEC 中位水深为 2086.33–2968.58 m，格间中位数 2758.15 m；初始三格约 2.4 km 的数值不代表所有 38 格。

### 8.4 其他 5603 个尾部点的机制比较

第 5 节未核对源记录的 5603 个 >5000 m 点，本轮已经全部核对原文；它们不是 staging 放大或连接产生的。这里的 5000 m 仅用于与前轮盘点逐项对账，不参与 G1。

| 文件序号 | 前轮尾部点数 | 其中 G1 配对成员 | 左舷 / 右舷点数 |
|---|---:|---:|---:|
| 51 | 47 | 46 | 39 / 8 |
| 52 | 976 | 224 | 0 / 976 |
| 53 | 1940 | 702 | 14 / 1926 |
| 54 | 2366 | 1048 | 271 / 2095 |
| 55 | 136 | 6 | 10 / 126 |
| 67 | 90 | 79 | 0 / 90 |
| 116 | 48 | 31 | 48 / 0 |

文件 116 的 48 点全部位于左舷，TWT 为 7.124–12.599 s、beam 33–66，与文件 117–120 的左舷长回波段相邻，可视为同一类记录表现的延续。文件 52、53、54、55 和 67 的尾部主要在右舷；文件 51 还包含较中央声束。它们共同出现长回波和部分几何反转，归档不支持把这些时段统一归因为同一左舷外侧故障。各时段的时间、声束、TWT 和中央参考详见 `v2/previous_tail_acoustic_summary.tsv`、`v2/previous_tail_by_side.tsv`。

### 8.5 与 v1 的关系及下游使用

v1 的 `affected_records.parquet` 保持不变。**v2 是独立的物理模型诊断，不是 v1 的超集。** 两表重叠 837 行，v2 新增 8183 行；v1 有 2796 行未命中 G1，包括最初 34 点中的 31 点。平滑、单调延伸的长回波可以不发生声束次序反转，不命中 G1 不能解除 v1 对它们的来源疑问。

为防止 R1 直接替换名单后重新引入 v1 记录，已保存精确键并集：

`v2/affected_records_v1_union_v2.parquet`

并集共 **11816 条、459 格**；其中 **11737 个原生 good 点、451 格**通过基础检查。仅属于 v1 的行明确标为 `V1_legacy_source_depth_inventory_not_G1_adjudicated`，不伪装成通过了几何判据。该并集可用于扩展的“保留 / 暂不采用候选”敏感性对照，不能作为完成来源 QC 的产品发布依据。两版分别回答旧尾部检索和条件几何冲突的影响，仍没有得到全航次的完整坏点范围。

本轮不要求修改 `34_mb_round2_extract_points.py`。下一项能改变判断的证据是目标时段的逐声束原始回波及时间门、实际采用的声速延拓设置，或独立交叉测线对这些声束落点的重复观测。这些资料可区分真实陡坡、错误回波选择和声速/方向模型问题；继续仅降低深度下限不能完成该区分。

### 8.6 复算与结果核对

```bash
cd /mnt/data2/00-Data/ship
D="$PWD/ncei/derived/mb_round2/_runs/20261021_hnro14rr_diagnosis"

# 本轮新增解码，首次输出到此前不存在的目录。
python -I "$D/decode_files.py" \
  --repo "$PWD" \
  --raw-root "$PWD/ncei/raw_round2/platforms_tree/roger_revelle" \
  --output "$D/v2/additional" --ordinals 51 52 53 54 55 67

# 文件 116 已在 $D/v2/file_116；其等价独立复算可用新目录：
# python -I "$D/decode_files.py" --repo "$PWD" \
#   --raw-root "$PWD/ncei/raw_round2/platforms_tree/roger_revelle" \
#   --output "$D/v2/redecode_116_repeat" --ordinals 116

python -I "$D/analyze_v2.py" \
  --repo "$PWD" --diagnosis "$D" --output "$D/v2"

python -I "$D/summarize_v2.py" --diagnosis "$D" \
  --r1-comparison "$PWD/ncei/derived/mb_round2/_runs/20261021_quality_revision/without_located_records/hnro14rr_located_cell_comparison.parquet"
```

已存在的解压目录不应重复创建；复算解码时使用新目录，并将分析器中的输入目录指向相应副本。G1 分析可直接复用保留的解压文件。`decode_files.py` 的默认文件列表仍为 v1 的 117–121，新增 `--ordinals` 只用于本轮诊断。

`analyze_v2.py` 的目标格输入为 `v2/remaining_points_after_v1.parquet`。`summarize_v2.py` 从完整源对照、v1 精确键及 R1 的 76 格重新构造这一点集，检查键与逐格点数，排除了目标格漏接或重复连接。主统计在 `v2/v2_summary.json`，交付核对在 `v2/v2_delivery_checks.json`，执行日志为 `v2/analyze_v2.log` 和 `v2/summarize_v2.log`。

本轮 Research Check：

- 执行：新增解码、完整源对照、G1 配对、并集和固定格组对照均已完成；保留的脚本产生本节数字。
- 单位与形状：820836 行、5436 个 ping；角度为度，TWT 为双程秒，横向距离为 m，UTC 时间与 staging 行键对应。中央参考从完整 ping 计算。
- 非有限值：v2 中 35 个 NaN 深度全部是源格式溢出的原生 null；数值列无 Inf。没有将缺失中央参考补成可用值。
- 对照一致性：v1 仍为 3633 行；v2 与并集键唯一；76 格逐格点数、剔除前中位水深与 R1 相符。
- 判据实现：所有 G1 配对均有正的横向支持间隔、正的时间支持间隔和大于 2.011° 的方向分离；G1 未读取 JAMSTEC 深度，`diagnostic_depth_threshold_m` 全为 NaN。
- 结论：提取错误仍被排除；过渡段中存在源内条件几何冲突；38 格中多数剩余差异及每对冲突的错误成员仍未确定。
