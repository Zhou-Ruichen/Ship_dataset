# Ship 上游修复任务

2026-10-21 核对。工作目录：`/mnt/data2/06-Projects/14-seamounts`。

本次确认的问题位于 Ship 的提取、聚合及本轮分析脚本中。没有修改上游代码和数据。本文件记录实测证据，并给出可交给 Ship 仓库代理执行的完整任务书。

## 已核对的证据

### 原生质量标志丢失，flagged 点进入聚合

`/mnt/data2/00-Data/ship/ncei/code/34_mb_round2_extract_points.py` 的 `process_one_file` 在 `_staging` 中保存 `native_quality_state`；`merge_cruise` 输出的 `points_raw`、`points_checked` 丢弃该字段及原文件内点索引。`point_check_pass_basic` 仅检查有限坐标、坐标范围和正向水深范围，水深上限为 11,500 m。

`ncei/code/07_aggregate_file_cells_1min.py` 当前仅依据 `point_check_pass_basic` 选点。

抽查 RR1412：

- 原文件：`RR1412/em122/0086_20141031_025617_revelle.all.mb58.gz`。
- staging：`ncei/derived/mb_round2/RR1412/_staging/761d2c6f1c51988d.parquet`。
- `good` 为 163,975 点，`flagged` 为 25,673 点。
- 两类点全部满足当前基础范围检查，25,673 个 flagged 点会进入当前聚合。

该样本证实质量标志丢失影响了选点。影响全批次多少网格、多少候选，须在修复后重算。

### HNRO14RR 极端残差不能只靠排除 flagged 解决

从 `20261020T_source_audit/japan_sea_cell_residuals.parquet` 选取含 HNRO14RR 且绝对残差最大的三个网格，再读取对应 staging 点。水深单位均为 m，向下为正。

| cell_id | 经度中心 | 纬度中心 | NCEI 中位水深 | JAMSTEC 水深 | 基础检查通过点数 | 原生质量 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1min_7701_18851 | 134.191667 | 38.358333 | 10394.0 | 2357.8160 | 2 | 全部 good |
| 1min_7702_18852 | 134.208333 | 38.375000 | 10300.0 | 2403.7970 | 3 | 全部 good |
| 1min_7702_18851 | 134.191667 | 38.375000 | 10186.0 | 2355.1575 | 29 | 全部 good |

34 点都来自：

`ncei/raw_round2/platforms_tree/roger_revelle/HNRO14RR/20070726161003120_sb2100_vf.20000203-2400p.mb41.gz`

对应 staging：`ncei/derived/mb_round2/HNRO14RR/_staging/437e75255a42abdc.parquet`，`file_ordinal=119`。

这三个网格没有混合其他 NCEI 航次。34 点水深合计范围为 8,767–11,414 m。原始记录异常、导航问题、格式或解析问题尚未区分；不能把排除 flagged 当作这一异常的解决办法。

### 状态表计数口径错误，不是 L2 凭空增加点

13 个已处理航次的 `extraction_summary.json:n_pass_basic` 均与 `run_status.tsv:l2_points_pass` 一致。状态表 `l1_basic_pass_rows` 与它们不一致。例如 RR1412：

- 实际 L1 基础检查通过数：53,560,845。
- L2 聚合点数：53,560,845。
- 状态表写作 L1 基础检查通过数：47,198,643。

HNRO14RR 状态表的 15,641,834 正好等于提取清单 `n_good` 的求和，不是实际基础检查通过数 15,643,210。存在 `skipped_exists` 的航次还需从已存在文件恢复计数。修复应分别报告原生质量与基础范围检查，不再混用。

### 其他影响复现和科学解释的问题

- `run_l2_l3.py:coverage_stats` 读取 `depth_median/depth_iqr`，聚合器输出 `median_depth_m/iqr_depth_m`；入口依赖后续 `finish_l2_l3.py` 才完成。其读取的 `n_tracks/n_surveys` 也不是原始聚合器输出。
- 两个脚本的 `source_path` 都拼成 `raw_round2/platforms_tree/{cruise}`，遗漏实际的船名层级。
- `source_audit_corrected.py:candtab` 先将数据裁到研究区，再计算候选完整 12.5 km 邻域的覆盖率，区域边缘候选的分子会缺少区外观测。
- `*_residual_by_ncei_cruise.tsv` 实际按来源组合分组，存在 `pd20ib02;rr1412` 等行，不是每个航次独立对照 JAMSTEC。HNRO14RR 的 456 格统计只对应其单一来源组；含该航次的重叠格共 475 格，另有 19 格混合其他航次。
- `shape_ready` 实际只表示脚本设定的覆盖条件，不包含形态测量或来源异常检查。现有“日本海 3 个、伊豆 55 个”的统计不能作为形态已可判定的结论。

## 可直接发送给 Ship 仓库代理的 prompt

你在 `/mnt/data2/00-Data/ship` 工作。请修复新增船载多波束数据从提取、选点、1′ 聚合到候选覆盖与来源差异分析的问题，并产出可供海山研究读取的修订版结果。完成代码与受影响数据的重算，不要只提出计划。

### 范围与保留要求

允许修改本仓库中的相关提取、聚合、来源清单代码，以及本轮分析脚本；允许添加针对本次实际错误的小型检查。先读本仓库规则、现有代码与未提交修改，保留其他人的工作。不要创建子代理。

新结果写入独立目录，例如 `ncei/derived/mb_round2/_runs/20261021_quality_revision/`；如目录已存在，先核对其所有者及状态。保留原始下载、staging、既有 L1/L2、旧报告和恢复入口，不覆盖旧结果。不要停止或重启下载任务，不将新结果自动合入生产主数据集，不修改海山仓库。不要给 NT06-21 编造 UTC；该航次保留“当前解析链未处理”的状态，不能解释成零观测覆盖。

已有输入：

- L1 与 staging：`ncei/derived/mb_round2/<cruise>/`。
- 旧 L2/L3 结果与脚本：`ncei/derived/mb_round2/_runs/20261020T_l2_l3_first_batch/`。
- 来源分析：`ncei/derived/mb_round2/_runs/20261020T_source_audit/`。
- JAMSTEC：`jamstec/multibeam/derived/cells_1min_qcfiltered/cells.parquet`。
- 旧主多波束层：`ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet`。
- 候选只读输入：`/mnt/data2/06-Projects/14-seamounts/outputs/20261019-vgg-pick-vs-ship-{japan-sea,izu-bonin}/candidates.csv`。

### 1. 恢复质量标志与点的来源

修复 `ncei/code/34_mb_round2_extract_points.py:merge_cruise`：保留 staging 中的原生质量状态，并保留足以追溯原文件和文件内点记录的信息。复用已有提取清单，不另造一套来源系统。已有 staging 可用时从 staging 重建，无需重复解压解析所有原始文件。

保持 `point_check_pass_basic` 的既有基础范围检查含义。为本批多波束增加明确的选点策略：基础检查通过且 `native_quality_state == "good"`；显式记录选点规则、good/flagged/null/unknown 数量及进入聚合的点数。旧数据没有质量字段时不得伪造 good，新策略遇到缺失字段应明确报告；旧调用维持其原有语义。

在 `ncei/code/07_aggregate_file_cells_1min.py` 中让本批次显式使用新策略，相关内存及流式路径保持一致。先用 RR1412 的 `761d2c6f1c51988d.parquet` 样本检查：163,975 个 good 点应被选入，25,673 个 flagged 点应排除。检查其余实际质量类别及计数，不以降低跨源残差为选点目标。

### 2. 追查 HNRO14RR 的 good 异常记录

优先分析原文件 `ncei/raw_round2/platforms_tree/roger_revelle/HNRO14RR/20070726161003120_sb2100_vf.20000203-2400p.mb41.gz`，对应 staging `437e75255a42abdc.parquet`，文件序号 119。

三个已知网格 `1min_7701_18851`、`1min_7702_18852`、`1min_7702_18851` 合计有 34 个基础检查通过点，全部标为 good；其中位水深为 10394、10300、10186 m，JAMSTEC 对应值约为 2358、2404、2355 m。

从这些点的文件内索引和时间追到原始记录，核对原格式、深度单位与符号、导航位置、时间连接及声束记录的对应关系。检查相邻记录和同航次相邻文件，比较原始解码输出与 staging，以区分源记录异常和处理程序错误。复用已有解析工具，只重解码诊断所需文件。

若确认代码错误，修复并重建受影响结果。若异常已存在于源记录且没有足够依据校正，保留原值和诊断状态，报告受影响记录、网格及候选；给出保留和暂不采用这些已定位记录时的结果对照。不要以“更接近 JAMSTEC”为理由改深度、改位置或自动剔除整个航次。原生 good 不等于已证明测深准确。

### 3. 统一可复现入口、路径和计数

修复 `run_l2_l3.py` 读取错误列名、依赖 `finish_l2_l3.py` 才能完成的问题，形成一个可独立执行的当前入口，复用正式聚合代码。旧脚本如有保留需要，应明确旧结果的复现入口，不继续叠加补丁脚本。

来源清单从实际下载或提取来源解析目录，补上船名层级，按既有约定说明相对路径的根目录，并核对每条路径存在。检查正式来源清单代码是否存在相同拼接错误，修复同一原因的调用。

计数至少区分总点数、基础检查通过数、原生质量各类别数、最终选入点数和 L2 点数。使用实际产物或合并汇总核对，不把 `n_good` 写成基础通过数；恢复 `skipped_exists` 文件的计数。相同选点条件下，L2 的 `n_points_pass` 求和必须等于 L1 实际选入点数。

### 4. 重算候选覆盖与逐航次残差

修复 `source_audit_corrected.py` 对区域边缘候选的截断：读取覆盖候选完整 12.5 km 邻域的数据，区域总覆盖面积仍按原研究区计算。保持原研究区：日本海 132–136°E、36–40°N；伊豆 140–144°E、28–32°N。

覆盖分母依据实际 1′ 网格中心和候选位置计算，核心半径 4 km，环带 8–12.5 km，8 个方位扇区。各来源及合并覆盖按 cell_id 去重；不要重复计入跨航次同一网格。统一入口中的旧覆盖计算也需要使用同一方法，不能留下另一份近似分母与未去重的扇区计数。

首先报告连续覆盖率。原有 0.6/0.5/0.25 覆盖条件如为兼容保留，应注明是沿用设置，不新增筛选阈值；将覆盖条件状态与形态判定分开，不能把覆盖达标写作海山已验证。保留前轮动态分母和三源并集的修复。

残差先按 `(cruise, cell_id)` 分别与 JAMSTEC 比较，再另报合并 NCEI 结果。现有按来源组合分组的统计可以保留为另一张表，不能称为逐航次独立残差。明确合并水深是航次中位数的中位数还是点加权统计，不悄悄改变估计量。

核对 strict 层的实际来源；其中源自 JAMSTEC 的观测不算第三套独立证据。1′ 同格残差包含空间采样差异；对伊豆陡坡上的重点差异先检查格内位置与测线分布。格内 IQR、标准差和跨源残差不能直接充当海山高度误差，`n_tracks=1` 不能解释成独立重复测线数。

### 5. 交付和完成条件

先用上述文件及小样本确认修复，再对受影响的已完成航次重建隔离版 L1/L2、来源清单、区域覆盖和候选表。没有变化的部分复用已有结果。无需等待仍在下载的航次，不重复启动下载。

检查实际错误对应的行为：质量策略、点的原文件追溯、计数一致、来源路径存在、重复 cell 合并、区域边缘候选、覆盖率在 0–1 内，以及单入口在新输出目录完成。保留必要的小型回归样本或构造测试，不跑无关全仓库检查。

交付一个结果记录和可读取的数据表，说明执行命令、输入、选点规则及代码位置。新旧结果至少对照：点数、有效网格数、各候选核心/环带/扇区覆盖率、逐航次残差、HNRO14RR 异常记录的处理及受影响候选。说明哪些候选可开始山顶与周边降深测量，哪些仍受测深来源异常或覆盖不足影响。

如 HNRO14RR 原始异常原因仍无法确定，保留可定位证据和下一步所需资料，完成其余已明确的代码修复与重算。不要用所有代码执行结束替代科学结果，也不要把现有“日本海 3 个、伊豆 55 个”沿用为修复后的结论。

## 本次小样本核对的复算方法

环境：海山仓库 `.venv/bin/python`，使用已有 pandas、numpy 和 pyarrow。以下为原生质量与极端水深抽查，不写上游文件：

```python
from pathlib import Path
import numpy as np
import pandas as pd

root = Path("/mnt/data2/00-Data/ship/ncei/derived/mb_round2")

def basic_mask(d):
    return (
        np.isfinite(d.lon) & d.lon.ge(-180) & d.lon.lt(180)
        & np.isfinite(d.lat) & d.lat.between(-90, 90)
        & np.isfinite(d.depth_raw) & d.depth_raw.gt(0)
        & d.depth_raw.le(11500)
    )

# These two cruises have sign_flip == 1 in extraction_summary.json.
p = root / "RR1412/_staging/761d2c6f1c51988d.parquet"
d = pd.read_parquet(p)
print(d.groupby("native_quality_state").size())
print(d[basic_mask(d)].groupby("native_quality_state").size())

a = pd.read_parquet(
    root / "_runs/20261020T_source_audit/japan_sea_cell_residuals.parquet"
)
top = a[a.ncei_source_cruises.str.contains("hnro14rr")].nlargest(
    3, "ncei_jam_abs_diff_m"
)
for cell_id in top.cell_id:
    _, yb, xb = cell_id.split("_")
    x, y = int(xb) / 60 - 180, int(yb) / 60 - 90
    parts = []
    for p in sorted((root / "HNRO14RR/_staging").glob("*.parquet")):
        d = pd.read_parquet(p, filters=[
            ("lon", ">=", x), ("lon", "<", x + 1 / 60),
            ("lat", ">=", y), ("lat", "<", y + 1 / 60),
        ])
        d = d[basic_mask(d)].copy()
        if not d.empty:
            d["filekey"] = p.stem
            parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    print(cell_id, d.groupby(
        ["filekey", "file_ordinal", "native_quality_state"]
    ).depth_raw.agg(["size", "min", "median", "max"]))
```
