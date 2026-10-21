# Step 10 船测水深筛选方法调研与差距表

## 范围与结论

本调研只比较已有方法与本仓库 Step 05A 至 Step 09 的现状，不执行数据处理，也不把 GEBCO 当作筛选门槛。

建议优先评估三项增补：

1. 在 `ncei/code/24_true_crossover_audit.py` 之后增加按连通分量求解的单波束轨线常数偏移网络。先用与多波束相交的轨线固定绝对基准；没有多波束支撑的分量采用偏移和为零的自由网，并明确标成相对改正。GMT 的 `x2sys_solve` 正是从交叉差求每条轨线的系统改正，常数项因差分而没有绝对基准，默认以各连通分量内偏移和为零来约束（GMT, 2026；Wessel, 2010）。
2. 在 `ncei/code/23_estimate_singlebeam_track_bias_1min.py` 与上述网络输出之后形成轨线质量等级。输入限于偏移显著性、改正后交叉残差、网络支撑度，以及年代、测深仪、声速、潮汐、吃水和基准元数据的完整性；不要用 GEBCO 残差决定等级。交叉差可以揭示轨线间不一致，但在未知地形梯度和定位误差存在时，不能单独归因为测深仪误差（Wessel and Watts, 1988）。
3. 在 `ncei/code/12_apply_quality_policy.py` 形成单元格权重时加入随水深变化的单波束不确定度。只对元数据足以建立误差模型的记录计算；元数据缺失的旧测深给出保守等级，不能声称符合 IHO S-44。S-44 要求在 95% 置信水平记录由所有误差源传播得到的水平和垂向不确定度，而非只套用一个固定百分比（IHO, 2024）。

## 1. 基于交叉点的轨线调整

### 1.1 GMT x2sys 的方法谱系

Wessel and Watts（1988）在海洋重力轨线交点用线性插值计算交叉差，利用交叉差估计轨线的常数偏移和线性漂移；该研究还指出，高梯度区的定位误差会放大交叉差。它证明了交叉网络适合寻找轨线级系统差，但对象是重力，不能把其 mGal 阈值移植到水深（Wessel and Watts, 1988）。

GMT 后续把该流程整理为 x2sys：`x2sys_cross` 计算轨线内部和轨线之间的交点，并输出交点位置、沿轨距离、时间、航向、速度和交叉差；默认线性插值，也提供 Akima 与三次样条（GMT, 2019；Wessel, 1989, 2010）。`x2sys_solve` 同时估计每条轨线的常数项、随距离或时间的线性漂移、比例项等；对水深，常数偏移和比例改正都有官方示例（GMT, 2026）。

常数偏移模型可写为

\[
d_{ij,k}=b_i-b_j+\epsilon_{ij,k},
\]

其中 \(d_{ij,k}\) 是轨线 \(i\) 与 \(j\) 的第 \(k\) 个交叉差，\(b_i,b_j\) 是待求轨线偏移。每个交叉点形成一行设计矩阵，所有轨线同时最小二乘求解。GMT 可接受每个交叉点的复合权重，进行加权最小二乘（GMT, 2026）。

仅有轨线差时，给所有 \(b_i\) 加同一常数不会改变观测，因此解没有绝对高程基准。`x2sys_solve` 对每个互不连通的轨线分量自动添加“偏移和为零”的约束；如要指定参考轨线，需把求得的相对解整体平移到该参考值（GMT, 2026）。本仓库若有可靠的多波束交叉控制，应直接把相应单波束轨线约束到多波束基准；其余分量保留自由网标签，不与绝对改正混写。

### 1.2 坏轨线、权重与迭代检查

GMT 接受交叉点级权重，但官方 `x2sys_solve` 文档没有规定水深数据的统一异常轨线阈值，也没有规定每条轨线至少需要多少交叉点（GMT, 2026）。因此不能把 Step 09 现有“至少 5 个参考单元格”直接当成网络解的文献阈值。

可评估的筛选顺序是：

1. 先按轨线图的连通分量求解，只让具有可识别参数的轨线进入。常数偏移至少需要与另一条轨线有交叉，但一个交叉点没有冗余，不能估计该轨线的残差稳定性。
2. 对每条轨线报告不同相邻轨线数、交叉点数、空间分布、设计矩阵杠杆值、偏移及其标准误、改正前后加权残差。交叉点很多但集中在一处，不能视为沿轨全程都有支撑。
3. 用预先规定的稳健权重或基于标准化残差的迭代降权，重算到参数与纳入集合稳定；同时保留未降权结果。GMT 只提供输入复合权重，具体稳健迭代规则需要本项目另行登记，不能称为 x2sys 默认行为（GMT, 2026）。
4. 用按交叉点或按相邻轨线的留一验证确定最低支撑条件。没有原始来源支持统一的“最少 N 个交叉点”，本调研不建议先定一个数字。

### 1.3 MB-System

MB-System 的 `mbnavadjust` 面向重叠多波束条带：在重叠地形中设置连接点，随后以最小二乘反演得到经度、纬度和深度方向的导航改正；它解决的是条带地形配准和导航模型，不是单波束轨线的纯深度常数偏移（Schmidt, Chayes, and Caress, 2006；MB-System, 2025）。`mbclean`、`mbedit` 等编辑产生的波束有效性标志可让坏波束不进入后续配准（MB-System, 2026）。

对本仓库的适用范围很窄：MB-System 提供了“重叠观测形成网络并整体反演”的方法参照，但当前 NCEI 多波束多数只有聚合后的 XYZ，缺少逐 ping 时间、姿态和原始波束，不能重建 `mbnavadjust` 所需的导航改正问题。可采用的是网络诊断思路，不应把 1′ 单元格差称为 MB-System 导航调整。

## 2. 大型汇编中的筛选

### 2.1 GEBCO

GEBCO 说明其数字测深资料会先检查定位和深度错误；制作格网时可迭代检查尖峰、修改坏测深并重新格网。其以卫星重力预测水深辅助船测质量检查和差值插值的流程，属于格网编制方法（GEBCO, 2026；Smith and Sandwell, 1997）。GEBCO 全球格网还要经过区域中心、技术委员会和区域制图委员会审查（GEBCO, 2026）。

这不提供可直接复制的逐轨线阈值。GEBCO 汇集质量和覆盖不一的异质来源，部分浅水数据的垂向基准并非平均海平面；其官网明确说明仍在处理这种基准混合问题（GEBCO, 2026）。因此本仓库只可把 GEBCO 差异用于诊断分层，不能用来排除船测，也不能把与 GEBCO 一致当成独立正确性。

### 2.2 GMRT

GMRT 保存多波束资料的原始分辨率，以多级瓦片持续更新；资料在加入瓦片前经过编辑（Ryan et al., 2009）。公开的 GMRT 质量说明还表明，传统资料的标识、采集参数、处理方法和导航可能不准确，因此不作统一精度保证（GMRT, 2026）。

GMRT 2010 年自动质量保证材料说明，以定制 GeoMapApp 在汇编背景中检查数据并定位问题，但目前检得的是会议海报记录，不足以确认一套公开、可复现的轨线接受阈值（Coplan et al., 2010）。本仓库可借鉴“在邻近资料和地形背景中人工复核自动标记”，不能声称 GMRT 使用了某个固定交叉差门槛。

### 2.3 NCEI 轨线资料及质量字段

NCEI Marine Trackline Geophysical Database 保存 1930 年代以来的单波束、重力和磁力等资料。MGD77T 每个航次包含头记录与按时间顺序的数据记录；头记录保存测深仪、假定声速、测深基准和已施加改正等信息，数据记录可带测深质量码（NGDC, 2011；NCEI, 2023）。NCEI 的当前提交说明要求单波束资料有导航才能在发现服务中发布，并要求记录处理、清理和改正信息（NCEI, 2023）。

这些字段是来源元数据和提供者质量标记，不等同于 NCEI 已对全球历史资料实施统一的现代精度复核。公开的一手格式文档没有给出“某质量码必然达到某个米级误差”的映射（NGDC, 2011）。本仓库应保留原质量码，并把缺失、来源方可疑、NCEI 后加标记分别编码；不能把空值解释为合格。

### 2.4 SIO 船测重力清理

Sandwell 团队的海洋重力与地形工作使用船测轨线和交叉差检查资料。Wessel and Watts（1988）展示了对全球海洋重力库按轨线估计常数偏移和漂移；GEBCO 也说明 SIO 的预测水深被用于寻找船测尖峰（Wessel and Watts, 1988；GEBCO, 2026）。

本调研未找到 Sandwell 团队公开的一手文档，能够完整规定当前 SIO 船测重力清理中的坏轨线阈值、迭代拒绝规则和最低交叉数。已确认的是交叉检查和预测场诊断的使用，未确认的具体阈值不作为本仓库设计依据。

## 3. 质量标准与单波束不确定度

### 3.1 IHO S-44

IHO S-44 6.2.0 定义 Exclusive、Special、1a、1b 和 2 五类航海安全测量等级。完全符合某一等级要求该测量同时满足该等级适用的测深、目标探测和其他要求；不能只凭垂向误差给历史资料贴 S-44 等级（IHO, 2024）。

S-44 的垂向不确定度形式为

\[
TVU_{max}(d)=\sqrt{a^2+(b d)^2},
\]

其中 \(a\) 是与水深无关的分量，\(b\) 是随水深增长的分量，所有数值按 95% 置信水平解释。S-44 还要求将定位、声速、潮汐或垂向参考、姿态、吃水等所有适用误差源纳入总传播不确定度，并随测量资料记录（IHO, 2024）。

本仓库的全球历史单波束不是为航海安全重新实施的系统测量，常缺原始误差预算、设备校准和改正记录。因此 S-44 应用作不确定度结构和元数据检查表，不应用作合格认证。

### 3.2 随水深变化的单波束误差

声学测深由双程传播时间与假定声速换算。实际声速偏离仪器采用值时，深度误差与水深成比例；NOAA 水道测量手册指出，小于水深 0.5% 的声速改正曾可忽略，这只是该手册的处理规则，不是所有旧单波束资料的通用精度（NOAA, 2017）。

对可获得假定声速 \(c_0\) 和可信实际声速 \(c\) 的记录，声速比例误差可按

\[
\Delta d_{sv}\approx d(c/c_0-1)
\]

估算。这直接来自传播时间换算关系。MGD77 头记录专门保存假定声速；历史常见值包括 1463 m/s 和 1500 m/s（NGDC, 2011）。NCEI 也提供按温度、盐度和压力改正假定 1500 m/s 等声速所得测深的官方表（NCEI, 1984）。

若只有“按 1500 m/s 计算”而没有温盐深或改正表适用信息，不能恢复真实深度。可做的是把声速项作为随深度增长的不确定度，并标记“未作声速改正”；不能统一乘一个全球改正系数。

### 3.3 潮汐、吃水和垂向基准

S-44 把 reduced depth 定义为包含测量、后处理和归算到适当垂向基准的全部改正后的深度，并要求明确垂向参考框架及其与其他基准的关系（IHO, 2024）。NCEI 接受多波束资料时把声速剖面、潮汐和船体偏移列为应随原始资料提交的辅助信息（NCEI, 2023）。

缺失时仍可能保留的系统误差包括：换能器至水面的吃水偏移、随时间和位置变化的潮位或动态水面偏移、基准之间的常数或空间变化差，以及声速造成的比例误差。没有原始辅助资料时，这些分量通常不能从单条深度序列唯一分离；交叉网络只能估计可由轨线差识别的合成偏移，不能说明它来自哪一项（IHO, 2024；Wessel and Watts, 1988）。

## 4. 多波束条带质量控制

### 4.1 CUBE 与波束质量标志

CUBE 利用密集多波束在格网节点附近的统计冗余，按每个测深的不确定度形成一个或多个深度假设，识别离群值，并输出深度及不确定度；多假设节点仍需判别或人工关注（Calder, 2003；NOAA, 2017）。它依赖逐测深位置、深度和不确定度，目标是从密集条带形成带不确定度的表面。

MB-System 的清理和编辑程序以逐 ping、逐波束有效性标志控制哪些测深进入后续处理；`mbnavadjust` 也用这些标志排除已判坏测深（MB-System, 2026）。波束标志属于测量级证据，聚合成 1′ 中位数后无法恢复是哪一个波束、哪个 ping 或哪一种底部检测导致异常。

### 4.2 对 1′ 产品的适用性

CUBE 不适合直接作用于本仓库现有 1′ 单元格。当前多数 NCEI 多波束文件缺时间戳，且 Step 04 已将点汇总为单元格统计量；CUBE 所需的逐测深不确定度、局部密度和多假设结构已经丢失。对现有资料可采用的只有较弱的汇总诊断：单元格内离散度、文件间离散度、重复资料比例、邻格突变，以及来源是否保留原始波束质量标志。这些诊断不能称为 CUBE，也不能反推 IHO 合规性（Calder, 2003；IHO, 2024）。

若未来接收带时间、姿态、声速和波束标志的原始多波束，应在 `ncei/code/01-04` 的点级清理与 1′ 汇总之前完成波束级处理；进入 1′ 产品时只携带接受点数、不确定度摘要和来源标志。

## 5. 与本仓库流程的差距表

状态含义：`have` 表示已有同类计算并进入现有输出；`partial` 表示只有部分输入、诊断或区域实现；`missing` 表示没有该方法。步骤名依据 `ncei/code/01-24` 和 Step 05 至 Step 09 报告。

| 方法 | 对应流程步骤 | 状态 | 依据与建议 |
| --- | --- | --- | --- |
| 点级范围、重复和人工标记 | `ncei/code/01_build_trackline_source_manifest.py`、`02_standardize_singlebeam.py`、`03_standardize_xyz.py`、`04_clean_mrar.py`、`05_point_quality_check.py`、`06_supplementary_quality_check.py` | have | 已在 `07_aggregate_file_cells_1min.py` 汇总前执行来源登记、标准化和点级 QC。保留，不用后续格网残差替代来源标记。 |
| 单来源内 1′ 重叠残差 | `ncei/code/09_source_specific_overlap_residuals.py`（Step 05A） | have | 已按轨线单元格减分支单元格中位数形成描述性残差；它不是物理交叉点，也没有全网解。 |
| 分支间 1′ 重叠差 | `ncei/code/10_cross_branch_overlap_audit.py`（Step 05B） | have | 已比较 MB、SB、MRAR 的同格差。继续作为来源间诊断，不替代轨线网络。 |
| 质量等级和单元格权重 | `ncei/code/11_quality_policy_calibration_audit.py`、`12_apply_quality_policy.py`（Step 06A/06B） | partial | 已有等级、权重和主验证资格；权重尚未包含可解释的随水深单波束不确定度。增加元数据完整性和深度项，但先校准，不追认 S-44 等级。 |
| 来源优先级和严格验证集 | `ncei/code/13_build_validation_cells.py`（Step 07B） | have | 已实施 JAMSTEC MB > NCEI MB > NCEI SB 填空，严格基线只用 MB。轨线调整只能改变 SB 补充或扩展产品，不改严格 MB 基线。 |
| GEBCO/全球格网残差筛选 | `ncei/analysis/14-22`（Step 08） | have（禁止项） | 已明确不按模型残差过滤、改级或提升船测。保持 GEBCO 仅作诊断分层，符合本任务边界。 |
| 区域 SB 轨线常数偏移 | `ncei/code/23_estimate_singlebeam_track_bias_1min.py`（Step 09） | partial | 已用严格 MB 优先、否则同格其他 SB 的参考估计偏移，至少 5 个参考格且偏移达到 2 NMAD 才应用；仅六个区域，且不是交叉网络联立解。作为对照臂保留。 |
| 真正 SB×SB 交叉点与时间 QC | `ncei/code/24_true_crossover_audit.py`（Step 09） | partial | 已在六个区域计算成对交叉差和 nc 时间 QC；未使用深度质量过滤，未与轨线偏移对照，未形成全球网络。应作为网络观测生产者，而不是终点。 |
| 轨线偏移网络最小二乘 | 建议接在 `ncei/code/24` 后、进入 `ncei/code/12/13` 前 | missing | 按连通分量求常数偏移；MB 支撑分量固定绝对基准，无 MB 分量用偏移和为零并标记为相对解。先在冻结区域与 Step 23 对照，再决定是否全球化。方法依据 GMT（2026）和 Wessel（2010）。 |
| 交叉点加权和异常轨线迭代降权 | 同上 | missing | 预先定义交叉点权重、标准化残差与停止条件；同时输出未加权解。不得从文献虚构统一水深阈值。GMT（2026）只规定可传入复合权重。 |
| 每条轨线最低交叉数 | 同上 | missing | 没有核实到通用阈值。用网络可识别性、不同邻轨数、空间分布和留一误差确定本数据的准入条件；单交叉轨线只可求相对偏移，不能评估稳定性。 |
| 轨线质量等级 | 建议由 Step 09 输出，供 `ncei/code/12` 使用 | missing | 合并偏移显著性、改正后交叉残差、网络支撑度和来源元数据；不要合并 GEBCO 残差。等级需保留各分量，避免一个总分掩盖原因。 |
| 深度相关 SB 不确定度 | `ncei/code/11/12`（Step 06A/06B） | missing | 对元数据充分的记录按 TVU 结构和声速项建模；缺声速、潮汐、吃水或基准信息时给保守等级并列出缺项。依据 IHO（2024）、NOAA（2017）和 NGDC（2011）。 |
| NCEI/MGD77T 质量码和头元数据 | `ncei/code/01-03` | partial | 已读入的字段需与原 MGD77T 质量码、假定声速、基准和改正记录逐项核对；空值保持 unknown，不解释为通过。依据 NGDC（2011）。 |
| GEBCO 异常诊断 | Step 09 诊断分层 | have | 已在偏移决定之后取样，未参与门控。保持此顺序；GEBCO 的编制本身使用船测，不能作为独立真值（GEBCO, 2026）。 |
| CUBE/逐波束 QC | 应位于 `ncei/code/01-04` 之前 | missing，现有聚合资料不可补做 | 仅对未来具有逐 ping 时间、姿态、声速、波束标志和不确定度的原始 MB 使用；现有 1′ 产品只保留汇总诊断。依据 Calder（2003）。 |
| MB-System 重叠条带导航调整 | 原始 MB 预处理，位于 `ncei/code/01-04` 之前 | missing，当前多数资料不适用 | 未来原始条带可用；当前无逐 ping 资料时不实施，也不把同格差改称导航调整。依据 Schmidt, Chayes, and Caress（2006）与 MB-System（2025）。 |

## 6. 建议增加项，按优先级

1. **先评估 SB 交叉网络常数偏移。** 固定六个 Step 09 区域和现有交叉事件，对比三组结果：未改正、Step 23 参考格偏移、交叉网络偏移。评价量只用改正前后留出交叉残差、轨线支撑度和对 MB 交叉的外部偏差；GEBCO 不参与选择。若 MB 支撑不足，结果只报告相对一致性。
2. **形成可分解的轨线质量等级。** 把偏移显著性、网络残差、不同邻轨数、交叉空间分布、年代/仪器/声速/潮汐/吃水/基准字段分别保存。先作为 Step 06A 校准输入，确认它比现有规则提供额外判别后，再进入 Step 06B 权重。
3. **建立深度相关 SB 不确定度。** 从有完整 MGD77T 头记录的轨线开始，分别计算固定项和随深度项；缺元数据者不插补虚假精度。该权重只影响 SB 补充和扩展产品，Step 08 的严格 MB 基线不变。
4. **原始 MB 资料另设入口条件。** 只有取得逐 ping 时间、导航、姿态、声速、潮汐/垂向参考和波束标志后，才评估 CUBE 或 MB-System；现有 1′ 单元格不补做逐波束处理。

## 7. 未由一手来源确认的事项

- 没有确认船测水深交叉网络中“每条轨线至少 N 个交叉点”的通用数字。GMT、Wessel 方法论文和 MB-System 材料均未给出可直接用于本数据的统一阈值。
- 没有确认 GMT `x2sys_solve` 自带迭代异常轨线拒绝规则。官方文档确认的是加权最小二乘接口；稳健迭代需本项目另行规定。
- 没有确认 GEBCO 或 GMRT 对贡献船测采用公开、统一的逐轨线接受阈值。已确认的是资料检查、编辑、格网审查和人工检查流程。
- 没有确认当前 SIO/Sandwell 船测重力清理所用的坏轨线阈值、迭代停止条件和最低交叉数。已确认的只限交叉差与预测场诊断。
- 没有确认 NCEI 历史轨线质量码与米级水深精度的一一对应关系。格式质量码不能替代误差预算。

## 参考文献与官方文档

- Calder, B. R. (2003). Automatic Statistical Processing of Multibeam Echosounder Data. *International Hydrographic Review*, 4(1), 53–68. https://scholars.unh.edu/ccom/980/
- Schmidt, V., Chayes, D. N., and Caress, D. W. (2006). *The MB-System Cookbook*. MBARI and Lamont-Doherty Earth Observatory. https://www.ldeo.columbia.edu/res/pi/MB-System/mbweb/mbcookbook.pdf
- Coplan, J., O'Hara, S., et al. (2010). Tools for Automated Quality Assurance of Multibeam Bathymetry Data for the GMRT Synthesis. AGU Fall Meeting poster record. https://www.marine-geo.org/about/meetings_reports.php
- GEBCO (2026). Frequently asked questions: creating bathymetric grids and quality control. https://www.gebco.net/about-us/faq
- GEBCO (2026). GEBCO grid development and review. https://www.gebco.net/data-products/gridded-bathymetry-data/grid-development
- GMRT (2026). Terms of Use, accuracy statement. https://gmrt.org/about/terms_of_use.php
- GMT (2019). `x2sys_cross` documentation. https://docs.generic-mapping-tools.org/5.4/supplements/x2sys/x2sys_cross.html
- GMT (2026). `x2sys_solve` documentation, GMT 6.7 development manual. https://docs.generic-mapping-tools.org/dev/supplements/x2sys/x2sys_solve.html
- IHO (2024). *IHO Standards for Hydrographic Surveys, S-44 Edition 6.2.0*. https://iho.int/uploads/user/pubs/standards/s-44/S-44_Edition_6.2.0_adopted.pdf
- MB-System (2025). *MB-System Training Tutorial*. https://github.com/dwcaress/MB-System-Tutorial
- MB-System (2026). Change log and program behavior for `mbnavadjust`, `mbnavadjustmerge`, `mbclean`, and beam flags. https://github.com/dwcaress/MB-System/blob/master/ChangeLog.html
- NCEI (1984). Echo-Sounding Correction Tables for Computer Use. https://www.ngdc.noaa.gov/mgg/fliers/84mgg18.html
- NCEI (2023). Submitting Marine Geophysical Data. https://www.ncei.noaa.gov/iho-data-centre-digital-bathymetry/submitting-marine-geophysical-data
- NGDC (2011). *The Marine Geophysical Data Exchange Format MGD77/MGD77T*. https://www.ncei.noaa.gov/sites/default/files/2022-01/mgd77.pdf
- NOAA (2017). *Hydrographic Surveying Manual, Fourth Edition*. https://nauticalcharts.noaa.gov/publications/docs/standards-and-requirements/hydrographic-manual/hydro-man-4th-edition.pdf
- Ryan, W. B. F., Carbotte, S. M., Coplan, J. O., et al. (2009). Global Multi-Resolution Topography synthesis. *Geochemistry, Geophysics, Geosystems*, 10, Q03014. https://doi.org/10.1029/2008GC002332
- Smith, W. H. F., and Sandwell, D. T. (1997). Global Sea Floor Topography from Satellite Altimetry and Ship Depth Soundings. *Science*, 277, 1956–1962. https://doi.org/10.1126/science.277.5334.1956
- Wessel, P., and Watts, A. B. (1988). On the accuracy of marine gravity measurements. *Journal of Geophysical Research*, 93(B1), 393–413. https://doi.org/10.1029/JB093iB01p00393
- Wessel, P. (1989). XOVER: A cross-over error detector for track data. *Computers & Geosciences*, 15(3), 333–346. https://doi.org/10.1016/0098-3004(89)90044-7
- Wessel, P. (2010). Tools for analyzing intersecting tracks: the x2sys package. *Computers & Geosciences*, 36, 348–354. https://doi.org/10.1016/j.cageo.2009.05.009
