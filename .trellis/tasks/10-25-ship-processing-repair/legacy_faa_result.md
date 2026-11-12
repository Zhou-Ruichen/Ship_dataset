# 15 航次 FAA 转换修正与全记录核对

2026-10-25

15 个新 NetCDF 已交付，共 512,234 条原观测；旧产品为 512,219 条。
15 条遗漏首观测全部恢复。新版 FAA 缺测 305,688 条，其中旧保留行
305,680 条、恢复首条 8 条；非缺测 206,546 条，包括 230 个真实零值。
FAA 数值、缺测和质量信息从原文保留，没有按时间是否可确定为 UTC
删除 FAA，也没有重做重力、声速或其他物理改正。

产品根：
`ncei/derived/processing_revision_20261025/legacy_faa/`。
读取说明为该目录 `README.md`。旧 NetCDF、原始下载和既有产品保持只读。

## 输入与正式头记录

- 观测原文：`/mnt/data2/06-Projects/11-swot-ssl-encoder/outputs/ship-source-processing-verification-v1/source/*.m77t`，15 个航次均读取全部观测。
- 格式依据：同一 `source/` 中的 `mgd77.txt`、`mgd77.pdf`；MGD77T 数据字段中的时区改正应加到原时间，空字段及省略尾字段均为未指定。
- 旧产品：`ncei/tracklines_nc/<cruise>.nc`。
- 既有对照：证据根的 `legacy_track_alignment.csv`、`legacy_field_comparison.csv`、`legacy_used_location_counts.csv` 和 `check_legacy.py`。
- 已用位置：`/mnt/data2/06-Projects/11-swot-ssl-encoder/outputs/eval/l2d_geophysical_correction_comparison_v1/paired_locations.parquet`。
- 解释依据：`/mnt/data2/06-Projects/11-swot-ssl-encoder/reports/ship_source_processing_verification_v1.md` 和同目录 `data_processing_literature_comparison_2026-10-25.md` 的 MGD77T 部分。

本地 `ncei/` 下正式 MGD77T 文件盘点得到 695 对 `.m77t/.h77t`，
没有这 15 航次的正式头。HEN04-3 的 `.h77t` 从只读证据复制到新版
`source_metadata/`；其余 14 个从原始 `.m77t` 对应 NOAA 目录取得。
全部 15 个正式头共 16,531 字节，保存路径、官方 URL、实际取得来源和日期
见 `source_metadata/provenance.json`。下载使用父协调员提供的已有本机代理，
没有修改代理配置或原始下载树。取得命令模式为：

```bash
curl --fail --silent --show-error --location --max-time 60 \
  --proxy http://127.0.0.1:2085 \
  --output ncei/derived/processing_revision_20261025/legacy_faa/source_metadata/<cruise>.h77t \
  <provenance.json中的header_url>
```

全部 58 个正式头字段保留在 NetCDF 的 `source_header` 属性中；
`Source_Institution` 等兼容属性只由正式头提供。HEN04-3 的机构为
`University of New Hampshire`，不再使用首条观测经度。

## 每航次数量

| 航次 | 原文及新 NetCDF | 旧 NetCDF | FAA 缺测 | FAA 非缺测 | 真实零 FAA |
| --- | ---: | ---: | ---: | ---: | ---: |
| a2089l03 | 3,343 | 3,342 | 26 | 3,317 | 7 |
| mo7204 | 10,636 | 10,635 | 1,552 | 9,084 | 12 |
| v3005 | 8,049 | 8,048 | 4,920 | 3,129 | 0 |
| rs9303 | 35,101 | 35,100 | 15,533 | 19,568 | 70 |
| 78123002 | 56,462 | 56,461 | 46,822 | 9,640 | 27 |
| 84002111 | 24,475 | 24,474 | 13 | 24,462 | 31 |
| es7802 | 2,793 | 2,792 | 470 | 2,323 | 0 |
| ew9601 | 48,722 | 48,721 | 9,269 | 39,453 | 0 |
| lh7803 | 18,994 | 18,993 | 603 | 18,391 | 0 |
| v3205 | 7,670 | 7,669 | 4,982 | 2,688 | 0 |
| 88000911 | 17,275 | 17,274 | 1,117 | 16,158 | 46 |
| gh7504 | 3,437 | 3,436 | 201 | 3,236 | 4 |
| hen04-3 | 225,949 | 225,948 | 188,558 | 37,391 | 0 |
| pptu01wt | 41,279 | 41,278 | 26,639 | 14,640 | 33 |
| v3014 | 8,049 | 8,048 | 4,983 | 3,066 | 0 |
| 合计 | 512,234 | 512,219 | 305,688 | 206,546 | 230 |

完整机器可读表为 `cruise_comparison.csv`。所有航次的首条均已恢复，
其旧行号为空。新版深度缺测共 108,850 条，深度字段为原文 `CORR_DEPTH`，
单位 m、向下为正；FAA 与观测重力为 mGal。有值数值没有重新估计或改正。

## 时间与质量字段

所有 26 个原字段按字符串保存在 `source_fields`，包括原 `DATE`、
`TIME`、`TIMEZONE`、前导零、`SURVEY_ID`、`LINEID` 和 `POINTID`。
根变量保留 `POS_TYPE`、`NAV_QUALCO`、`BAT_CPCO`、`BAT_TYPCO`、
`BAT_QUALCO`、`MAG_RESSEN`、`MAG_QUALCO` 和 `GRA_QUALCO`，
未指定代码为 masked integer；字符串原状态仍可读取。

这 15 航次的 512,234 个 `GRA_QUALCO` 全部未指定，不被改成 good。
`NAV_QUALCO` 中 12 条为 6，其余 512,222 条未指定。各原代码的完整
频数见 `source_code_counts.csv`。本次转换保留全部记录，没有施加来源质量选点。

主 `time` 仅在原日期、时刻和时区均有效且已指定时定义 UTC。主 UTC
缺测共 229,205 条，由 225,948 条时区未指定的有效源时刻和
3,257 条原缺测时刻组成：

- EW9601 有 3,256 条原时刻缺测，新主时间和假设时间均保持缺测。
- HEN04-3 的 225,949 条原时区均未指定，其中一条原时刻也缺测。
  主时间全部保持缺测；225,948 条有效源时刻可通过明确命名的
  `time_assuming_unspecified_timezone_zero` 读取零时区假设结果。
- `time_status` 明确区分缺少日期/时刻、已知时区 UTC、未知时区、
  无效日期/时刻和无效时区；这批数据实际只有前三种状态。

没有缺测时刻被写为 1970-01-01。观测维度仍名为 `time`，
保留既有变量读取合同；新版文件没有声明 CF Conventions。
FAA 有效性不依赖 UTC 是否可确定。

## 行号映射与已用位置

`row_mapping.parquet` 汇总 512,234 行；逐航次版本位于 `row_mapping/`。
列中包含原文件路径、旧/新 NetCDF 路径与以下索引：

| 列 | 起始与含义 |
| --- | --- |
| `source_line_1based` | 原文本物理行，1 起始，包含列标题所占行。 |
| `source_observation_index_0based` | 原观测顺序，0 起始，不含列标题。 |
| `old_netcdf_row_0based` | 旧 NetCDF 行，0 起始；恢复首条为空。 |
| `new_netcdf_row_0based` | 新 NetCDF 行，0 起始。 |

15 个航次按原文顺序与全部旧经纬度核实对应关系，经度差使用周期等价。
每个航次都只存在一个坐标一致的连续对应关系，旧序列由原观测索引 1 开始。
未在核实前直接给旧索引加 1。新 NetCDF 内嵌同一映射；空旧索引为
masked `-1`，Parquet 中为 null。

`used_locations_remapped.parquet` 按航次和旧行号连接原位置表，保留
267,343 个位置及其新行号；每个位置同时核对旧 FAA、经纬度及新原文对应。
旧值命名为 `faa_legacy_mgal`，新值为 `faa_revised_mgal`：

| 已用位置的原文状态 | 数量 |
| --- | ---: |
| FAA 缺测，新列为 null | 184,997 |
| FAA 非缺测 | 82,346 |
| 非缺测中真实零 FAA | 79 |
| 合计 | 267,343 |

九区域、18 个区域/航次单元的各项数量与既有
`legacy_used_location_counts.csv` 逐项一致，见新版
`used_location_comparison.csv`。本次没有重算 SWOT 精度。

## 实际实现与核对

新增可复用入口：

```bash
python -m ncei.trackline mgd77t-nc \
  --input /path/survey.m77t \
  --header /path/survey.h77t \
  --output /new/root/survey.nc \
  --legacy-netcdf /old/root/survey.nc \
  --mapping-output /new/root/survey_rows.parquet
```

实现位置：

- `ncei/trackline/mgd77t.py`：`iter_mgd77t`、`read_mgd77t`、
  `read_header`、`decode_time`。流式解析保留无标题文件的首条和短记录，
  支持静态源常见的第 27 个空尾字段。
- `ncei/trackline/mgd77t_netcdf.py`：`convert_mgd77t` 与
  `align_legacy_rows`；显式输入/输出、正式头和行号映射。
- `ncei/trackline/legacy_faa_revision.py`：15 航次批次转换、独立 CSV
  读取核对、已用位置连接及额外源盘点。
- `ncei/trackline/__main__.py` 和 `README.md`：新增两个命令，
  既有命令及数字别名不变。

后续点表执行者可直接复用：

```python
from ncei.trackline.mgd77t import iter_mgd77t, decode_time, read_header

for records in iter_mgd77t(source_path, chunk_size=100_000):
    depth = records.numeric("CORR_DEPTH")
    quality_raw = records.raw["BAT_QUALCO"]
    physical_line = records.source_line_1based
    source_index = records.source_observation_index_0based
    original_width = records.source_field_count
    times = decode_time(records)

formal_fields = read_header(header_path, survey_id).fields
```

`records.raw` 提供标准 26 字段的字符串数组；`numeric(field)` 仅将空字段
解释为 NaN，保留非空数值。解析器本身不删除数值哨兵、零值或质量代码。
`decode_time` 返回 `utc_seconds`、
`assuming_unspecified_timezone_zero_seconds`、`status`。

本次结果生成命令从仓库根运行，标准输出和错误保存在产品 `run.log`：

```bash
/opt/miniforge3/envs/torch29/bin/python -m ncei.trackline legacy-faa-revision \
  --source-root /mnt/data2/06-Projects/11-swot-ssl-encoder/outputs/ship-source-processing-verification-v1/source \
  --metadata-root ncei/derived/processing_revision_20261025/legacy_faa/source_metadata \
  --legacy-root ncei/tracklines_nc \
  --output-root ncei/derived/processing_revision_20261025/legacy_faa \
  --paired-locations /mnt/data2/06-Projects/11-swot-ssl-encoder/outputs/eval/l2d_geophysical_correction_comparison_v1/paired_locations.parquet \
  --static-root ncei/raw_round2/mgd77t_static \
  --overwrite
```

环境为 `/opt/miniforge3/envs/torch29/bin/python`，Python 3.12.12，
netCDF4 1.7.4、NumPy 2.4.1、Polars 1.41.2、pandas 2.3.3。
替换 `--overwrite` 为 `--verify-only` 可对现有新版产物执行同一原记录核对，
不重新转换。

每航次逐个检查 26 个原字段、21 个数值/代码字段、两类时间数组和
58 个正式头字段，检查首条恢复、全部映射与单位。新产物的有限数值、
缺测及原字符串差异均为 0，已知时间和明确假设时间的最大差均为 0 s。
旧有值数值的对照重现既有证据，原数值单位保持。检查明细保存在
`field_comparison.csv`、`cruise_comparison.csv` 和
`comparison_summary.json`。

核对后仅调整了汇总字段的时区计数名称、给已用位置列加上旧/新版明确名称，
移除了新文件未采用的 CF 声明，没有重跑转换或变更观测数组。

## 可沿同一入口扩展的完整原文

除本次 15 个源外，静态树与旧 NetCDF 的交集有以下六航次：

| 航次 | 原观测 | 旧 NetCDF | 正式机构 |
| --- | ---: | ---: | --- |
| cntl01rr | 237 | 236 | Scripps Institution of Oceanography |
| cntl02rr | 454 | 453 | Scripps Institution of Oceanography |
| ew9801 | 25,982 | 25,981 | Lamont-Doherty Earth Observatory |
| f1190cp | 195,795 | 195,794 | USGS |
| f989nc | 73,817 | 73,816 | USGS |
| hs8304 | 8,330 | 8,329 | Hydrographic Department |

六个 `.m77t` 均完整读入，正式 `.h77t` 可读，原文顺序和所有旧坐标均
确认旧产品遗漏首条，总计 304,615 条原观测。逐文件路径、大小及对应结论
见 `additional_complete_source_inventory.csv`。这六航次尚未重建。

本轮盘点范围内共有 21 个旧航次具有完整 MGD77T 原文。
`ncei/archive/source_zips/NCEI_singlebeam_tracks_raw_2018files.zip`
包含旧 NetCDF，不是另一份 MGD77T 原文。没有扩展重建其余航次或进行重力评价。

首批写前估计低于 0.5 GiB，实际整个 FAA 产品约 30 MiB。

## Research Check

- Executes: 15 航次结果生成命令完成，原文与新产物逐记录对照完成。
- Shapes/units: 512,234 行，15 条首观测恢复；FAA/gobs 为 mGal，深度为 m、向下为正，行号约定明确。
- NaN/Inf: 源缺测按 NaN/mask 保留，305,688 个 FAA 缺测与原文一致，真实零值保留。
- Result provenance: 原文、旧产品、正式头、新文件和实际核对表均由上述命令和明确路径关联。
- Findings: 旧行中的 305,680 个缺测 FAA 改为缺测，恢复首条另含 8 个缺测；3,257 个原缺测时刻不再变为 Unix 时间零。
