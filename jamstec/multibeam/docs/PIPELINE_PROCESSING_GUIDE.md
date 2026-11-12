# JAMSTEC Multibeam Processing Pipeline Guide

本文说明当前生产链的命令、输入、输出和固定统计约定。所有命令从 Ship 仓库根
目录运行，解释器为 `/opt/miniforge3/envs/torch29/bin/python`。项目根默认为
`jamstec/multibeam/`；需要隔离输出时，在命令名前加
`--project-root <scratch-project>`。

## 1. 命令与产品顺序

```text
source archives
  -> extract
  -> manifest
  -> curate
  -> standardize
  -> point-qc
  -> file-cells
  -> merge-cells
  -> quality = 05 -> 06a -> 06b -> 06c -> 06d
  -> validation-cells
```

| 命令 | 主要输入 | 主要输出 |
|---|---|---|
| `extract` | `archive/` 中两个外层 zip | `raw/subzips/`、`raw/dat_by_subzip/`、`docs/dat_manifest.tsv` |
| `manifest` | `raw/dat_by_subzip/`、DAT 清单、坏 subzip | `manifests/file_manifest.*`、`subzip_manifest.*`、`docs/format_audit_report.md` |
| `curate` | `file_manifest.parquet` | `file_manifest_points_raw.*`、`excluded_from_points_raw.tsv` |
| `standardize` | curated manifest、原始 DAT | `derived/points_raw/`、`points_raw_manifest.*`、`docs/point_schema_v1.md` |
| `point-qc` | L1 点表及其清单 | `derived/points_qc/`、`points_qc_manifest.*`、`docs/qc_points_report.md` |
| `file-cells` | QC 点表、curated manifest | `derived/file_cells_1min/`、`file_cells_manifest_1min.*` |
| `merge-cells` | 逐文件格及清单 | `derived/cells_1min/cells.parquet`、`cells_manifest_1min.*` |
| `quality` | file cells、merged cells、来源例外表 | overlap、极端偏差、文件质量、QC-filtered cells 和前后对照 |
| `validation-cells` | 原始/QC-filtered cells 及 06d 对照 | `derived/validation_cells_1min/` 主验证格与敏感性格 |

查看参数不会触发处理：

```bash
/opt/miniforge3/envs/torch29/bin/python -m jamstec.multibeam --help
/opt/miniforge3/envs/torch29/bin/python -m jamstec.multibeam quality --help
```

## 2. 来源提取与清单

### `extract`

```bash
/opt/miniforge3/envs/torch29/bin/python -m jamstec.multibeam extract
```

依次调用 `source/` 内的提取、完整性检查、递归解压和 DAT 清单工具。损坏的
subzip 移入 `raw/subzips_bad/`；成功展开的嵌套 zip 不重复保留。现有
`docs/bad_subzips.txt`、`docs/bad_nested_zips.txt` 和 `docs/dat_manifest.tsv`
是来源记录。

### `manifest`

```bash
/opt/miniforge3/envs/torch29/bin/python -m jamstec.multibeam manifest --overwrite
```

扫描所有来源文件，识别三列 `lon lat depth` 与六列
`date time sonar lon lat depth`，记录经纬度/深度范围、行数、文件角色猜测和
`used_for_points`。`file_id` 使用 `<subzip>::<relative-file>`，后续层沿用此键。
小输入审查可使用 `--sample-n-files`、`--limit-files` 或路径正则；这些选项把
结果写入 `manifests/samples/` 和样本报告。

### `curate`

```bash
/opt/miniforge3/envs/torch29/bin/python -m jamstec.multibeam curate --overwrite
```

在标准化之前执行。输出 `include_in_points_raw`、排除原因和重复候选。
`duplicate_group_id` 是全语料内的组编号，不能把一个子集的编号与正式产品直接
比较。`standardize` 默认读取本步的 `file_manifest_points_raw.parquet`。

## 3. 点表与逐文件格

### `standardize`

```bash
/opt/miniforge3/envs/torch29/bin/python -m jamstec.multibeam \
  standardize --run-label full --confirm-full --overwrite
```

每个纳入来源生成一个 Parquet 分片。保留 `lon_raw/lat_raw`、标准化 `lon/lat`、
`depth_m_positive_down`、`elev_m`、原日期/时间/sonar 字段和
`point_index_in_file`。深度单位为 m，向下为正。完整列合同见
`docs/point_schema_v1.md`。

可用 `--file-id`、`--subzip-id`、`--limit-files` 或样本选项限制输入。
`full` 必须显式加 `--confirm-full`。

### `point-qc`

```bash
/opt/miniforge3/envs/torch29/bin/python -m jamstec.multibeam \
  point-qc --run-label full --confirm-full --overwrite
```

追加坐标、深度、NaN、零值等 QC 列，不删除原观测。`qc_pass_basic` 是后续
逐文件格的基础选择。

### `file-cells`

```bash
/opt/miniforge3/envs/torch29/bin/python -m jamstec.multibeam \
  file-cells --run-label full --confirm-full --overwrite
```

以 1′ = 1/60° 聚合每个文件：

```text
lon_bin = floor((lon + 180) / (1/60))
lat_bin = floor((lat + 90) / (1/60))
cell_id = "1min_<lat_bin>_<lon_bin>"
```

每个 `(file_id, cell_id)` 保存点数、深度中位数、均值、极值和离散程度等统计。

### `merge-cells`

```bash
/opt/miniforge3/envs/torch29/bin/python -m jamstec.multibeam \
  merge-cells --run-label full --confirm-full --overwrite
```

主估计采用文件均衡中位数：先计算每个文件格的中位数，再对同格的文件中位数
取中位数。点数多的文件不因此获得额外权重。报告同时保留点加权均值、文件间
标准差/IQR、来源文件数和航次数。

## 4. 来源质量与 QC-filtered 格

```bash
/opt/miniforge3/envs/torch29/bin/python -m jamstec.multibeam \
  quality --run-label full --confirm-full --overwrite
```

`quality` 固定执行以下五步，不提供另一套并列命令：

1. **05 `overlap.py`**：在 `n_file_cells >= 2` 的格中计算逐文件格相对文件均衡
   中位数的残差，按文件、航次和 subzip 汇总。输出到
   `derived/overlap_bias_1min/`。
2. **06a `extreme_bias.py`**：计算候选来源相对全体、其他航次和其他文件的
   残差，给出 `recommended_quality_actions.tsv` 与受影响格。候选选择的审核
   例外在 `config/extreme_bias_rules.tsv`。
3. **06b `file_quality.py`**：生成 `manifests/file_quality_flags_1min.parquet`。
   这是逐文件的 `keep/review/high_variance_review/exclude` 标记，不是 07 的
   格级 A/B/C 层。显式排除规则在 `config/file_exclusion_rules.tsv`。
4. **06c `qcfiltered_cells.py`**：排除 `exclude_from_primary_cells=True` 的
   文件，按同一文件均衡估计重建 `derived/cells_1min_qcfiltered/cells.parquet`，
   并保留原格中的排除来源计数。
5. **06d `compare_cells.py`**：生成
   `derived/qcfiltered_comparison_1min/common_cell_depth_shifts.parquet`、
   `lost_cells.parquet` 和 `changed_cells_large_shift.parquet`。这些表是 07
   的直接输入，不是可选的事后审计。

小输入运行可使用 `quality --run-label sample --sample-n-files 50`；05/06a
使用相应样本目录。06b–06d 保留正式相对文件名，因此样本核对必须选择独立的
`--project-root`。06c/06d 的 `--file-cells-manifest` 与 `--original-cells`
可显式指定目标格及其全部直接贡献文件组成的小输入。

## 5. 主验证格与敏感性格

```bash
/opt/miniforge3/envs/torch29/bin/python -m jamstec.multibeam \
  validation-cells --overwrite
```

输入为原始 cells、QC-filtered cells 和 06d 对照表。输出：

- `primary_ship_validation_cells_1min.parquet`：2,394,115 个 1′ 格；
- `sensitivity_original_ship_cells_1min.parquet`：未排除来源的原始格；
- `validation_cells_1min_summary.parquet` 和运行报告。

07 按覆盖与离散程度给格分配 `A_tier/B_tier/C_tier`，并映射到
`validation_weight = 1.0/0.7/0.4`。主深度列为 `ship_depth_m`，单位 m、向下为
正；`ship_elev_m` 为其负值。

## 6. 产品保存与历史分析

`raw/`、`archive/`、正式 `derived/`、`manifests/`、`docs/` 和 `figures/`
不因代码重构删除。scratch 对照只写 `derived/refactor_check/`；新旧对照结果在
该目录的 `comparison_results.tsv`。

已完成的全球模型验证、SWOT T1 和残差基线代码已从 `analysis/` 归档删除；相关
报告、`configs/gridded_products_validation.yaml` 和图保留。需要复原代码时，
按仓库根 `docs/code_archive.md` 的最后包含提交读取，不在当前包中保留旧命令。
