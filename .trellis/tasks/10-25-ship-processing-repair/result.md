# 船测来源处理修订

日期：2026-10-25。新版产品根目录：
`ncei/derived/processing_revision_20261025/`。

本批已完成 21 个 FAA 航次、695 条 MGD77T 航线和六个多波束航次的来源修订，
并交付可连接到原记录的物理改正状态表。缺测与真实零分开保存，来源质量
与导航修订进入独立选择列；已有有效观测值和格网估计方法保留。
总读取说明为产品根目录的 `README.md`。

## 15 航次 FAA 已交付

15 个新 NetCDF 保留全部 512,234 条原观测，恢复原来遗漏的 15 条首观测。
305,688 条 FAA 缺测保持缺测，206,546 条非缺测 FAA 保留原值，其中
230 条为真实零。缺测总数包含旧保留行中的 305,680 条，以及恢复首观测中的
8 条。单位为 mGal，深度为 m、向下为正。

正式头记录、26 个原字段、时间状态、源质量代码和全量旧/原/新行号映射均已保存。
执行者逐记录对照没有发现新产物与原文的数值、缺测或字符串差异。
协调员实读完整映射和已用位置表，检查 HEN04-3、EW9601、A2089L03 的
首观测、机构、质量列和时间状态；未重复转换。

下游入口为 `legacy_faa/README.md`。核心文件：

- `legacy_faa/netcdf/<cruise>.nc`：15 航次全部原观测。
- `legacy_faa/row_mapping.parquet`：512,234 行旧/原/新索引，旧首观测对应为空。
- `legacy_faa/used_locations_remapped.parquet`：267,343 个原已用位置；
  `faa_revised_mgal` 中有 184,997 个空值、82,346 个非空值，包含 79 个真实零。
  旧值明确命名为 `faa_legacy_mgal`。
- `legacy_faa/source_code_counts.csv`：源代码频数；本批 `GRA_QUALCO`
  全部未指定，未改为 good。

主 UTC 时间缺测 229,205 条，其中 225,948 条有源时刻且时区未指定，
另有 3,257 条原时刻缺测。零时区假设结果保存在明确命名的
`time_assuming_unspecified_timezone_zero`；FAA 非缺测性不要求主 UTC 有值。

实现入口为 `python -m ncei.trackline mgd77t-nc`；15 航次复算入口、
全量核对表和每航次数量见 `legacy_faa_result.md`。额外六航次已单独完成，
见下节；其余旧航次的原文与匹配正式头仍是扩大覆盖的依赖。
没有重新计算 SWOT 船测精度。

下游已读取 README、索引映射和 NetCDF，接续核对既有位置与新观测的对应。
正式头中的 `G_FORMU_CO/GRAV_FORMU`、`G_RFSYS_CO/GRAV_RFSYS`、
`GRAV_CORR/ADD_DOC` 保留逐航次原文，用于区分正常重力公式、重力参考系统
和提供方改正说明。本轮不进行重力基准转换；下游直接读取现成字段。

下游在既有有效位置检查了
`GRA_OBS - FREEAIR - 正常重力(纬度)` 的闭合。协调员读取其完整结果表：

| 航次 | 配对观测数 | 正常重力公式 | 闭合 RMS / mGal | 来源解释 |
| --- | ---: | --- | ---: | --- |
| 88000911 | 4,755 | IGF1980 | 0.02853 | 正式头写 IAG SYS，数值与 IGF1980 相容 |
| gh7504 | 1,391 | IGF1930 | 0.07495 | 正式头未指定，保留数值闭合证据 |
| 84002111 | 9,338 | IGF1930 | 40.54666 | 在闭合式中加源 EOTVOS 后 RMS 为 0.58517 |

84002111 的结果表明，不能把该航次的 `GRA_OBS` 直接解释为已包含全部
厄特沃什改正，也不能给现成 `FREEAIR` 再统一添加 `EOTVOS`。
正式头与数值闭合是两类证据，不相互替换。FAA 仍使用提供方的原值。
逐区域、逐航次完整结果及命令由下游保存在
`/mnt/data2/06-Projects/11-swot-ssl-encoder/outputs/eval/l2d_reference_field_repair_v1/review/faa_normal_gravity_closure.csv`
及同名 `.json`，Ship 未重复计算。

## 六航次 FAA 扩展已交付

`cntl01rr`、`cntl02rr`、`ew9801`、`f1190cp`、`f989nc`、`hs8304`
的新 NetCDF 位于 `legacy_faa_additional/netcdf/`。全部 304,615 条原观测保留，
恢复六条首观测；FAA 缺测 93,513 条，有值 211,102 条，其中真实零 172 条。
旧行对应的原缺测中，3,660 条曾写成零，其余 89,849 条旧值已经缺测。
六源的 `CORR_DEPTH` 全部未指定，未从走时假定声速换算深度。

执行者逐记录核对原字段、数值、时间、正式头和索引，差异为零。
协调员读取六份新 NetCDF 和完整映射，核对各航次总数、缺测、真实零、
机构字段及恢复首观测的空旧索引。读取与复算命令见
`legacy_faa_additional/README.md`，逐航次数量见 `additional_faa_result.md`。
原 15 航次与 267,343 位置映射保持不变。六源也属于静态 695 航线，
两种产品不能当成独立重复观测合并。

## 来源物理改正状态已交付

`source_corrections/` 将正式头、原文件处理注释及 `.inf` 原文整理为
逐来源状态，不改动测深或 FAA 数值。三个主表覆盖全部已交付来源：

- `trackline_source_corrections.parquet`：695 行，以 `track_id` 连接静态
  航线清单与点表；`nf1013l2` 保留配套头 ID 不匹配状态。
- `legacy_faa_source_corrections.parquet`：21 行，以 `track_id` 连接两批
  FAA 映射的 `cruise_id`。六个附加航次的 `header_shared_with_static=true`
  标明与静态航线共用来源。
- `swath_source_corrections.parquet`：1,508 个产品源文件，以 `filekey`
  连接提取清单和声束。另有一个 HNRO14RR 证据样本，
  `is_sample_evidence_only=true`，不属于六航次产品。

HNRO07RR 的 502 个、HNRO05RR 的 17 个、HNRO06RR 的 178 个文件明确记录
按给定声速剖面重新声线追踪，合计 697 个产品源文件。HNRO06RR 另 18 个文件
声明声速已改正，所记录的 mbprocess 步骤为换能器深度/升沉调整模式；
实际参数是 `Heave: not modified`、`Draft set: 6.000000 meters`。
模式句、升沉设置和吃水设置分列保存，不把模式名称解释为已施加升沉改正。

这 715 个 MB41 产品源文件所记录的处理步骤均关闭潮位计算与横摇、纵摇偏差
再次施加。HNRO06RR 标定元数据中的横摇偏差有两组，169 个文件为 -0.97°，
27 个文件为 0.06°，纵摇偏差均为 0.38°。标定值与步骤开关分开保存，
步骤关闭不表示仪器采集链未使用姿态观测。全部多波束源的命名垂向基准
仍为未知，`CORRECTED` 表示水深处理声明。

RR1412 的 736 个文件有声速剖面记录通知，732 个有表层声速记录通知，
736 个有姿态记录通知。表中保存实际 `.inf` 路径、原通知和行号；
这些记录是否参与实时或后处理改正仍为未知。NT05-06 的 38 个与 AII8L18
的 19 个文件也未从本次来源读取确定改正应用状态。下一依赖为提供方处理
档案、仪器参数及转换说明，不据未知状态统一重做声速或潮位改正。

`swath_svp_profiles.parquet` 保存 123 条不同处理剖面，以 `svp_id` 连接
源文件。其中 122 条来自六航次产品，另有 HNRO14RR 样本的 18 点剖面，
编号 122。保留提供方至 12,000 m 的延拓参数，不当作深层实测声速。
HNRO14RR 样本原文件为
`ncei/raw_round2/platforms_tree/roger_revelle/HNRO14RR/20070726161003120_sb2100_vf.20000203-2400p.mb41.gz`，
末端延拓声速为 1,524 m/s。其逐 ping `svp_correction=A` 与声线追踪注释
并存，不能单凭该码判定未做声速改正。该样本继续作为既有源声束异常与
敏感性解释的证据，原诊断与条件几何冲突清单保留。

静态和 FAA 状态表保留记录仪假定声速、逐记录 `BAT_CPCO` 频数、
垂向基准代码、正常重力公式与参考系统、提供方改正说明。假定声速不等于
声速改正已应用。静态表有三个明确吃水改正声明，均为 5 m；21 个 FAA
航次有四个，原 15 航次为 `lh7803`、`pptu01wt`，附加为 `cntl01rr`、
`cntl02rr`。`lh7803` 未给吃水数值，其余三个为 5 m。其他吃水状态及
这些头记录中的潮位、姿态改正应用状态保留未知。源 FAA 不作重力基准转换，
也不重施厄特沃什改正；数值闭合证据与头声明分开保存。

`evidence_texts.parquet` 有 11,422 条原文，含 631 条头字段、716 条
MB41 前导和 10,075 条 `.inf` 行。各条给出头字段、解压字节范围或原行号。
`checks.json` 记录 695 航线主键、1,508 产品文件键与输入清单的集合一致性，
以及 HNRO06RR 模式参数、RR1412 通知、HNRO14RR 剖面连接和吃水声明核对。
协调员实读最终表与关键原文，核对 18 文件的升沉/吃水状态、RR1412 通知
位置和样本剖面连接。读取与复算见 `source_corrections/README.md`，
完整阶段记录为 `source_corrections_result.md`。复算入口：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 POLARS_MAX_THREADS=1 \
/opt/miniforge3/envs/torch29/bin/python -m ncei.trackline source-corrections
```

下游已实际读取全部来源状态表，695 个航线 ID、21 个 FAA 映射 ID、
六个共用头、1,508 个多波束文件键及路径均连接一致，全部被引用的剖面可读取。
HNRO14RR 样本排除于产品连接。协调员读取下游接收记录与
`/mnt/data2/06-Projects/11-swot-ssl-encoder/outputs/ship-source-processing-verification-v1/source_correction_links.json`，
确认其保留 HNRO06RR 步骤区别、未知应用状态及现有数值产品。

## 多波束两个完整航次已交付

HNRO07RR 与 NT05-06 的 540 个源文件已从头提取，
48,315,733 条声束的时间、坐标、深度、原生质量与源身份逐记录对照差异为零。
新版选入 37,697,369 条声束，形成 18,411 个航次格。深度为 m、向下为正，
格网间隔为 1′，沿用全点中位数、唯一三元组中位数和重复比例。

| 航次 | 旧选入声束 | 新选入声束 | 旧航次格 | 新航次格 |
| --- | ---: | ---: | ---: | ---: |
| HNRO07RR | 37,723,275 | 36,435,030 | 18,337 | 18,325 |
| NT05-06 | 1,262,339 | 1,262,339 | 86 | 86 |

HNRO07RR 的 18,299 个零导航 ping 对应 1,659,933 条声束，其中
1,288,245 条曾通过基础检查与原生 good 选择。本轮将源 ping 的导航有效性
传给每条声束，这些点留在 L1 并退出格网。NT05-06 的 38 份 `.prj` 均逐源
传递，未发现无效源导航，选入点与格数不变。

HNRO07RR 的近原点选入声束从 1,288,592 条降至 347 条。余下声束的源 ping
导航非零，符合本轮数值有效性规则，来自三个 ping。具体记录在
`swath/first_batch_comparison/retained_near_origin_points.parquet`。
下游要求的相邻时刻和船位核对已完成。这三个 ping 分属零导航段之后的
4、4、6 条非零错误过渡序列，共 14 个 ping。直接读取三份原文的
2,627 条 `SB2100DR` 头记录，时间和坐标与解码结果一致。过渡序列结束后
船位在数秒内跳回日本附近；零导航段之前与过渡段之后的船位分别仅相距
3.31、2.98、0.78 km。证据将异常定位到档案源导航，不是声束偏移或投影读取。

研究用选择按这 14 个精确 ping 身份排除 1,634 个原选入声束，
HNRO07RR 保留 36,433,396 个声束、18,268 格。只重聚合 58 个受影响格：
57 格消失，一格保留其他 ping 的 39 个声束；18,267 个未受影响格保留原值。
已发布首批产品未改写，未设置半径或航速阈值。

研究用格网在
`swath/navigation_review/HNRO07RR/file_cells_1min/hnro07rr__mb41.parquet`。
`ping_navigation_review.parquet` 保存精确身份、原文、相邻船位与
`source_navigation_invalid_confirmed`；
`point_selection_overlay.parquet` 保留全部 2,114 条所属声束、原字段及新旧选择。
其余导航状态为 `not_reviewed`，未标为已核对可靠。复算入口为
`python -m ncei.swath navigation-case-review review`。

读取位置：

- 点表：`swath/first_batch/HNRO07RR/points_checked/hnro07rr__mb41.parquet`
  和 `swath/first_batch/NT05-06/points_checked/nt05-06__mb84.parquet`。
- 格网：相同航次目录下 `file_cells_1min/` 的同名文件。
- 选点列：`point_selected_basic_native_good_valid_ping_navigation`；
  原生质量、源导航、导航原因与 ping/beam 身份保留在点表。
- 全记录对照：`swath/first_batch_comparison/`；其中
  `combined_ncei_cells.parquet` 沿用航次格中位数的等权中位数。

协调员读取完成标志、逐航次对照和 L1/L2 schema，并核对比较入口的
源身份与逐记录选择检查；读取了 14 个 ping 的原文头、邻接证据、
2,114 条覆盖记录和研究用格网，格内点数总和与研究选择一致。
完整复算命令和输入资料见 `swath_result.md`。

## 六航次完整批次已完成

四航次扩展已完成，与首批合计 1,508 个原文件、121,116,093 条声束。
六航次全记录的源时刻、坐标、深度、原生质量和身份差异为零。
数值导航选择共 99,359,551 条声束、60,124 个航次格，合并为 57,703 格。

| 扩展航次 | 原声束 | 数值导航选入声束 | 航次格 |
| --- | ---: | ---: | ---: |
| AII8L18 | 6,378,015 | 4,218,494 | 4,159 |
| HNRO05RR | 1,114,371 | 465,699 | 278 |
| HNRO06RR | 11,743,286 | 9,780,182 | 7,002 |
| RR1412 | 53,564,688 | 47,197,807 | 30,274 |

新增点表和航次格在 `swath/navigation_affected_extension/<cruise>/`，
六航次数值导航合并格在 `swath/combined_ncei_cells.parquet`。
22,831 个零导航 ping 共对应 2,333,817 条声束，实际减少
1,883,831 个旧选入声束。HNRO07RR 个案研究选择的六航次合并版本在
`swath/navigation_review/combined_ncei_cells_case_review.parquet`，
含 99,357,917 个选入声束、57,647 个唯一格。

完整批次发现 HNRO05RR 仍有 287 个近原点声束，来自
`a4778b6cfe3209ba` 的三个非零导航 ping。协调员读取其原生邻接导航，
随后由原执行者核对跨 9 个源文件的 3,957 条直接 DR 记录。
当前文件从零导航开始，前端真实船位位于前一连续航段；
零段后的索引 174--178 是非零错误过渡，179 在 8.564 秒后回到日本附近。
这五个 ping 的错误坐标直接存在于原文，原文与解码导航的坐标差不超过
1e-10 度，时刻一致。

HNRO05RR 个案资料另存在 `swath/navigation_review_hnro05rr/`：
全部 745 条所属声束保留，研究选择排除 709 个原选点，其中近原点窗口内
287 个、窗口外 422 个。27 个受影响航次格退出，其余 251 格保留原值；
HNRO05RR 研究选择为 464,990 个声束、251 格。

**当前六航次研究用合并格网**为
`swath/navigation_review_combined_cases/combined_ncei_cells_case_review.parquet`，
包含 HNRO07RR 与 HNRO05RR 两项已完成个案，保留 99,357,208 个选入声束、
60,040 个航次格、57,623 个唯一格。19 个确认无效 ping 合计减少
2,343 个数值导航阶段的选点。相对 HNRO07RR-only 版本，新增修订使
24 个唯一格退出，3 格保留其他航次贡献，其余合并格数值相同。
描述性近原点余表为零行，其余导航仍为 `not_reviewed`。

下游已实际读取双个案研究产品，并从六份航次格独立计算合并水深。
57,623 个唯一格的选点数、航次格数逐项一致，中位水深最大差为 0 m。
协调员读取了下游的 `six_cruise_delivery_check.json`，其输入指向本次
双个案版本；结果与复算脚本保存在
`/mnt/data2/06-Projects/11-swot-ssl-encoder/outputs/ship-source-processing-verification-v1/`。
这批测深尚未替换下游既有的 64 区域固定比较。

完成对照在 `swath/comparison_summary.json`，实际输入、投影与选点核对在
`swath/delivery_checks.json`。多波束新产品约 16.17 GiB，
data2 余约 3.71 TiB；六航次批处理进程已正常退出。

## 完整 695 航线来源质量产品已交付

新版点表保留 150,587,793 条原观测，包括旧 XYZ 未保留的 25,739 条短记录。
基础选择复现 119,751,714 个旧选点、1,266,224 个航线格。
导航与测深来源质量码均不为 3/4/5/6 的主选择保留 105,457,041 点、
1,235,712 个航线格，实际退出并集为 14,294,673 点。
其中导航标记涉及 12,496,788 点、测深标记涉及 2,025,974 点，
两者重叠 228,089 点。未指定质量码继续保留，不改写为 good。

时间、原记录身份、位置类型、测深类型、声速改正代码和 26 个原字符串
进入新点表。全部源记录对照、旧点数值与基础选择、旧格网统计差异均为零。
既有 627 个单波束和 65 个多波束预测保持不变，三个全部为短记录且无深度的
来源保持未分类。1,979,743 条观测可确定 UTC；148,608,050 条有效源时刻
的时区未指定，主 UTC 留空，显式假设时间另列保存。

读取 `trackline/points_checked/<track>__mgd77t.parquet`，主选择列为
`point_selected_basic_source_quality`，水深为
`depth_m_positive_down`，单位 m、向下为正。主格网位于
`trackline/file_cells_1min/`，基础选择对照位于
`trackline/file_cells_1min_basic/`；两者沿用既有 1′ 聚合和文件均衡合并。
源头记录与代码频数在相同根目录，完整复算命令和逐航次数量见
`mgd77t_result.md` 及 `trackline/README.md`。主选择的单波束文件均衡合并格
为 959,389 个，多波束分支为 122,616 个；分支之间存在空间重叠，不相加
当成唯一格总数。合并深度列为 `median_depth_m`，单位 m、向下为正。

协调员实读首批五份点表、完整 695 航线清单、分类和有效文件核对记录，
核对新增短记录、质量选择并集、时间状态和新旧索引。新入口已将历史对照
改为可选输入：独立 AR1-06 转换不读取旧点表或外仓核对表，338,605 条源
观测的 77 个可比字段与两类格网统计均和完整批次相同。没有历史依据的
分类保持未分类、旧点索引为空，不混入已分类合并。

六个既有研究区对本批单波束航线执行了两种选择的交叉点计算，均无支持的
航次交叉点，未估计航次偏差。源观测索引必须连续；RR2201 删除一个来源
可疑点后减少两个线段，没有跨接缺口。协调员读取实际覆盖和断点表，
并检查唯一有两个带段航次的区域：两航迹在裁剪范围内的纬度范围不相交。
这些空交叉点结果只描述本批六区覆盖，不能解释为航次偏差为零。

下游已从 695 份航线格表独立重算两个合并分支，逐格点数与航线格数一致，
中位水深最大差为 4.55e-13 m。两个分支重叠 18,224 格，空间并集
1,063,781 个 1′ 格；该并集只表示覆盖，未把两分支水深合成一个估计量。
下游还逐记录核对六份附加 FAA 与同源 MGD77T 点表的坐标、FAA、观测重力、
缺测和身份，数值差为零。协调员已读取其
`/mnt/data2/06-Projects/11-swot-ssl-encoder/outputs/ship-source-processing-verification-v1/complete_trackline_delivery_check.json`，
其中保存实际输入和命令。既有 64 区域测深及 82,346 位置 FAA 比较未扩充。

## 本批完成与后续覆盖

本批数值产品、源记录映射、来源物理改正状态和复算入口均已交付。
所有 Ship 执行者已完成；已交付数值批次不再重算。下游已实际读取并核对
数值产品和来源状态，连接字段与原文指针已接入下游来源记录。
15 航次 FAA 的来源和取得方式保存在
`legacy_faa/source_metadata/provenance.json`。

尚未重建的旧 NetCDF 有 1,997 航次，扩大来源恢复需对应原观测和匹配正式头。
原 13 航次多波束中的 COOK09MV、EW9508、HNRO14RR、NT05-16、PD20IB02、
PPTU11WT、TN168 仍保留 20261021 质量修订产品，未纳入本次六航次导航产品。
其原完成清单已有完整记录，下一批需重新核对选定文件及辅助资料后按新导航
入口处理；HNRO14RR 继续保留现有精确记录诊断与敏感性产品。
本批不启动其余航次或全球全量重建。下载由原负责人继续管理。
