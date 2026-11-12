# 六个完整旧 FAA 航次已交付

六航次 `cntl01rr/cntl02rr/ew9801/f1190cp/f989nc/hs8304` 已沿共用
`convert_mgd77t` 转换入口完成，保留全部 304,615 条原观测，旧文件
304,609 条。六条首观测均恢复，93,513 条 FAA 缺测、211,102 条有值记录
和其中 172 个真实零分别保留。

| 航次 | 新观测数 | 旧观测数 | FAA 缺测 | FAA 有值 | 真实零 |
| --- | ---: | ---: | ---: | ---: | ---: |
| cntl01rr | 237 | 236 | 135 | 102 | 0 |
| cntl02rr | 454 | 453 | 361 | 93 | 0 |
| ew9801 | 25,982 | 25,981 | 3,166 | 22,816 | 12 |
| f1190cp | 195,795 | 195,794 | 89,850 | 105,945 | 82 |
| f989nc | 73,817 | 73,816 | 1 | 73,816 | 47 |
| hs8304 | 8,330 | 8,329 | 0 | 8,330 | 31 |

93,513 = 旧行对应的 93,509 个原缺测 + 恢复首条中的 4 个缺测。
旧行对应缺测中 3,660 个此前写成零；`f1190cp` 的其余 89,849 个旧值
原已缺测。没有将所有零删除。所有六源的 `CORR_DEPTH` 均未指定，
深度保持缺测，不从走时假定声速换算。

源时刻均有值且有效；295,594 条时区未指定，主 UTC 保持缺测。
另有明确命名的零时区假设时间，原 `TIMEZONE/DATE/TIME`、`time_status`
和质量码均保留。FAA 有效性独立于 UTC 可确定性。

## 输入、产物与核对

输入为已发布的
`legacy_faa/additional_complete_source_inventory.csv` 所列六组本地完整
`.m77t/.h77t` 和旧 `ncei/tracklines_nc/*.nc`，均只读。
产物根为 `ncei/derived/processing_revision_20261025/legacy_faa_additional/`。
该根的 README 给出列、单位、读取例子与复算命令；`run.log` 为实际执行日志。

`netcdf/` 有六个新文件。`row_mapping.parquet` 含全部 304,615 行，
`row_mapping/` 为逐航次映射。物理行号从 1 起，源观测索引和 NetCDF
行号从 0 起，恢复首条的旧行号为空。对齐先用源顺序与全部坐标确定，
不是将旧表位置直接加一后复用。

`legacy_faa_revision.verify_one` 通过独立 CSV 读取路径逐条核对全部
26 原字段、21 数值/代码字段、两个时间列、时间状态、首条和索引；
逐字段核对正式头的 58 个命名字段，全部差异为零。
旧有效经纬度、深度、观测重力和 FAA 的有值记录保持原值。
正式机构直接取配套 `.h77t`：Scripps Institution of Oceanography、
Lamont-Doherty Earth Observatory、USGS、Hydrographic Department，
没有从观测表列名猜机构。

统计证据为 `cruise_comparison.csv`、`field_comparison.csv`、
`source_code_counts.csv` 和 `comparison_summary.json`。FAA 单位 mGal，
深度单位 m、向下为正；不重做声速、重力参考系统或其他物理改正。
原 15 航次产品和 267,343 位置映射未改写。

实际命令从仓库根运行：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 POLARS_MAX_THREADS=1 \
/opt/miniforge3/envs/torch29/bin/python -m ncei.trackline legacy-faa-revision \
  --additional-inventory ncei/derived/processing_revision_20261025/legacy_faa/additional_complete_source_inventory.csv \
  --output-root ncei/derived/processing_revision_20261025/legacy_faa_additional
```
