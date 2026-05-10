# NCEI Multibeam Processing Pipeline Guide

> **目的**: 解释每一步做了什么、输入输出是什么、为什么这样设计，以便下次能快速回忆。
>
> **项目根目录**: `/mnt/data2/00-Data/ship/NCEI_multibeam/`

---

## Pipeline 总览

```
raw .dat files
  │
  ▼
[01] Build manifest          → 识别所有 .dat 文件，分类格式
  │
  ▼
[02] Standardize to Parquet  → 每个 .dat → 标准化 parquet 点表
  │                               ↗ 02a 筛选/去重（curate manifest）
  ▼
[03] QC points               → 标记异常点（坐标、深度、NaN）
  │
  ▼
[04a] File-level cells       → 每个文件的点聚合为 1min cell 统计量
  │
  ▼
[04b] Merge global cells     → 所有文件 cell 合并为全局 1min grid
  │
  ▼
[05] Overlap bias analysis   → 重叠 cell 中各文件残差分析
  │
  ▼
[06a] Extreme bias source    → 定位异常 bias 的来源文件/航次
  │
  ▼
[06b] File quality flags     → 为每个文件打质量标签（A/B/C tier）
  │
  ▼
[06c] Rebuild QC-filtered    → 排除低质量文件，重建全局 cell
  │
  ▼
[06d] Compare QC vs original → 对比 QC 前后差异，确认改进
  │
  ▼
[07] Primary validation cells → 生成最终验证用船测 cell 表
  │
  ▼
[08] Validate gridded products → 用船测 cell 验证全球海底地形模型
```

---

## Step 01: `01_build_multibeam_manifest.py`

**做什么**: 扫描所有 .dat 文件，识别格式（3列/6列/其他），构建文件清单。

**输入**: `raw/dat_by_subzip/` 下的所有 .dat 文件

**输出**:
- `manifests/file_manifest.parquet` — 每个 .dat 文件的元数据（路径、格式、行数、subzip来源）
- `manifests/subzip_manifest.parquet` — subzip 级别汇总
- `docs/format_audit_report.md` — 格式审计报告

**关键逻辑**: 区分 3-col 格式（lon lat depth）和 6-col 格式（date time sonar lon lat depth），标记无法识别的文件。

---

## Step 02: `02_standardize_multibeam_xyz.py`

**做什么**: 将每个 .dat 文件转为标准化的 Parquet 点表。

**输入**: `raw/dat_by_subzip/` + `manifests/file_manifest.parquet`

**输出**: `derived/points_raw/<file_id>.parquet`（5083个文件）

**点表 schema**:
| 列名 | 类型 | 说明 |
|------|------|------|
| lon, lat | float64 | 经纬度（已归一化到 [-180,180)） |
| lon_raw, lat_raw | float64 | 原始经纬度（可能 0-360） |
| depth_m_positive_down | float64 | 深度（正向下） |
| elev_m | float64 | 高程（= -depth） |
| point_index_in_file | int64 | 文件内行号 |

### Step 02a: `02a_curate_points_manifest.py`

**做什么**: 在 file_manifest 基础上增加 file_role、include/exclude 标记、重复文件候选检测。

**输出**: `manifests/file_manifest_points_raw.parquet`

**为什么需要**: 有些文件是 transit（过境数据）或重复文件，需要在后续处理前标记。

---

## Step 03: `03_qc_multibeam_points.py`

**做什么**: 对每个点进行质量控制标记。

**输入**: `derived/points_raw/*.parquet`

**输出**: `derived/points_qc/<file_id>.parquet`（5083个文件）

**QC 标记列**:
| 列名 | 检查内容 |
|------|---------|
| qc_valid_lon | lon ∈ [-180, 180) |
| qc_valid_lat | lat ∈ [-90, 90] |
| qc_depth_positive | depth > 0 |
| qc_depth_not_extreme | depth ≤ 12000m |
| qc_elev_negative | elev < 0 |
| qc_no_nan | 关键列非 NaN |
| qc_pass_basic | 以上全部通过 |

**为什么需要**: 原始数据有坐标错误、零深度、极端值等问题，这些会污染后续聚合。

---

## Step 04a: `04a_make_multibeam_file_cells.py`

**做什么**: 将每个文件的 QC 通过点聚合为 1弧分 cell 统计量。

**输入**: `derived/points_qc/*.parquet`

**输出**: `derived/file_cells_1min/<file_id>.parquet`（5083个文件）

**Cell 定义**:
```
cell_deg = 1/60°
lon_bin = floor((lon + 180) / cell_deg)
lat_bin = floor((lat + 90) / cell_deg)
cell_id = "1min_{lat_bin}_{lon_bin}"
lon_center = -180 + (lon_bin + 0.5) * cell_deg
lat_center = -90 + (lat_bin + 0.5) * cell_deg
```

**每个 (file, cell) 的统计量**: median_depth, mean_depth, std, count, range 等。

---

## Step 04b: `04b_merge_multibeam_cells.py`

**做什么**: 将 5083 个文件级 cell 合并为全局 1min cell grid。

**输入**: `derived/file_cells_1min/*.parquet`

**输出**: `derived/cells_1min/cells.parquet`（181MB）

**关键聚合策略**: **File-balanced median**
- 对每个 cell，先算每个文件的 median，再对所有文件 median 取中位数
- 避免"点多的文件主导结果"的偏差
- 同时记录点加权均值、文件间 std/IQR、覆盖文件数等

**为什么这样设计**: 不同文件在同一位置的点密度差异很大（例如一条航迹密集经过 vs 偶尔经过），简单取所有点的 median 会被点密集的文件主导。

---

## Step 05: `05_analyze_cell_overlap_bias.py`

**做什么**: 分析多文件重叠 cell 中的残差和系统性偏差。

**输入**: `derived/file_cells_1min/*.parquet` + `derived/cells_1min/cells.parquet`

**输出**: `derived/overlap_bias_1min/` 目录下：
- `overlap_file_cell_residuals.parquet` (123MB) — 每个 (file, cell) 的残差
- `file_bias_summary.parquet` — 每个文件的偏差统计
- `cruise_bias_summary.parquet` — 每个航次的偏差统计
- `suspicious_files.tsv` / `suspicious_cruises.tsv` — 可疑文件/航次清单

**关键逻辑**: 在 n_file_cells ≥ 2 的 cell 中，计算每个文件 cell 相对于 file-balanced median 的残差，然后按文件/航次聚合，识别系统性偏差。

---

## Step 06a: `06a_investigate_extreme_bias_sources.py`

**做什么**: 深入分析 05 识别的极端偏差来源。

**输入**: file_cells + cells + 05 的偏差摘要

**输出**: `derived/extreme_bias_investigation_1min/`
- 每个候选文件的三类残差（vs 全局median、vs 其他航次median、vs 其他文件median）
- 文件审计表、航次审计表、影响范围分析
- `recommended_quality_actions.tsv` — 建议的质量操作

---

## Step 06b: `06b_create_file_quality_flags_1min.py`

**做什么**: 为所有 5083 个文件分配质量等级。

**输入**: 06a 的审计结果 + 文件 manifest

**输出**: `manifests/file_quality_flags_1min.parquet`

**质量分层**:
| Tier | 条件 | 说明 |
|------|------|------|
| A_tier | 低偏差、高覆盖 | 高可信数据 |
| B_tier | 中等偏差 | 可用但需注意 |
| C_tier | 高偏差或极端值 | 建议排除 |
| exclude_from_primary_cells=True | 严重问题 | 不参与最终验证 |

---

## Step 06c: `06c_rebuild_cells_1min_qcfiltered.py`

**做什么**: 用 04a 的 file_cells，排除被标记的文件，重新合并全局 cell。

**输入**: `derived/file_cells_1min/*.parquet` + `manifests/file_quality_flags_1min.parquet`

**输出**: `derived/cells_1min_qcfiltered/cells.parquet`（180MB）

**逻辑**: 与 04b 完全相同的合并算法，只是跳过 exclude_from_primary_cells=True 的文件。

---

## Step 06d: `06d_compare_original_vs_qcfiltered_cells.py`

**做什么**: 对比 QC 前后差异，确认质量改进。

**输入**: cells_1min (原始) + cells_1min_qcfiltered (过滤后)

**输出**: `derived/qcfiltered_comparison_1min/`
- 对比报告、丢失 cell 列表、大偏移 cell 列表
- 确认 QC 是否有效改善了数据质量

---

## Step 07: `07_prepare_primary_validation_cells_1min.py`

**做什么**: 生成最终验证用的船测 cell 表。

**输入**:
- `derived/cells_1min_qcfiltered/cells.parquet` (主表)
- `derived/cells_1min/cells.parquet` (敏感性分析用)
- `derived/qcfiltered_comparison_1min/` (对比数据)

**输出**:
- `derived/validation_cells_1min/primary_ship_validation_cells_1min.parquet` (180MB)
  - 2,394,115 个 cells，带 quality_tier (A/B/C) 和 validation_weight
- `derived/validation_cells_1min/sensitivity_original_ship_cells_1min.parquet` (154MB)
  - 未 QC 过滤的原始 cells，用于敏感性分析

---

## Step 08: `08_validate_gridded_products_against_ship_cells.py`

**做什么**: 用船测 cell 验证全球海底地形模型（gridded bathymetry products）。

**输入**:
- `derived/validation_cells_1min/primary_ship_validation_cells_1min.parquet`
- `configs/gridded_products_validation.yaml`（产品配置）

**输出**: `derived/model_validation_1min/` 目录下全部验证结果

**验证的 5 个产品**:

| 产品 | 分辨率 | 大小 | 采样方法 |
|------|--------|------|---------|
| GEBCO_2024 | 15s | 7.0 GB | cell_median → fallback center_nearest |
| ETOPO_2022 | 1min | 469 MB | center_bilinear |
| SRTM15_V2.7 | 15s | 6.2 GB | cell_median → fallback center_nearest |
| SDUST_2023 | 15s | 535 MB | cell_median（0-360经度） |
| TOPO_25.1 | 15s | 523 MB | cell_median → fallback center_nearest |

**采样策略**:
- 配置 cell_median/cell_mean 的产品会同时运行 center_bilinear_sensitivity（敏感性对比）
- 大网格（>500M像素）的 cell_median 自动退化为 center_nearest（避免 OOM）
- 输出记录 `sampling_method`（实际方法）和 `config_sampling_method`（配置方法）

**已知问题**: SDUST_2023 有陆地掩膜问题（6% 的海洋 cell 被标记为陆地），导致 bias=389m，这不是脚本错误。

**当前状态**: 仅完成 sample 运行（10,000 cells），**尚未全量运行**。

---

## 磁盘使用概览

```
总计: 325 GB
├── raw/                  124 GB  ← 原始 .dat 文件（不可删）
├── archive/               25 GB  ← 原始下载 zip（不可删）
├── derived/
│   ├── points_raw/        86 GB  ← 5083 个标准化点表
│   ├── points_qc/         86 GB  ← 5083 个 QC 后点表
│   ├── file_cells_1min/  486 MB  ← 5083 个文件级 cell 表
│   ├── cells_1min/       181 MB  ← 全局 merged cells（原始）
│   ├── cells_1min_qcfiltered/ 180 MB  ← QC filtered cells
│   ├── validation_cells_1min/  337 MB  ← 最终验证 cells
│   ├── overlap_bias_1min/   139 MB  ← 重叠偏差分析
│   ├── extreme_bias_*/      12 MB  ← 极端偏差调查
│   ├── qcfiltered_*/        56 MB  ← QC 对比
│   ├── model_validation_1min/ 5 MB  ← 验证结果（sample only）
│   └── *_test100/        ~3 GB  ← 测试用（可删）
│   └── *_sample/        ~270 MB  ← 采样测试用（可删）
│   └── points_raw_lon360/ 147 MB  ← 中间产物（可删）
├── manifests/              17 MB
└── output/logs/            7 MB
```

---

## 可删除的中间文件

### 🟢 强烈建议删除（节省 ~174 GB）

| 目录 | 大小 | 原因 |
|------|------|------|
| `derived/points_raw/` | 86 GB | 已加工为 points_qc，除非需要重新 QC 否则不需要 |
| `derived/points_qc/` | 86 GB | 已聚合为 file_cells_1min，除非需要重新聚合否则不需要 |
| `derived/points_raw_test100/` | 1.5 GB | 早期测试产物 |
| `derived/points_qc_test100/` | 1.5 GB | 早期测试产物 |

> **⚠️ 删除 points_raw 和 points_qc 的前提**: 确认不需要重新运行 03/04a。如果 file_cells_1min (486MB) 和后续产物都满意，可以安全删除。

### 🟡 可以删除（节省 ~275 MB，不影响最终结果）

| 目录 | 大小 | 原因 |
|------|------|------|
| `derived/*_sample/` | ~270 MB | 各步骤的 sample 测试产物 |
| `derived/*_test100/` | ~20 MB | test100 测试产物 |
| `derived/points_raw_lon360/` | 147 MB | 经度转换中间产物 |

### 🔴 不要删除

| 目录/文件 | 原因 |
|-----------|------|
| `raw/` | 原始数据，无法重建 |
| `archive/` | 原始下载，25GB |
| `derived/file_cells_1min/` | 重建 cells 的基础，且可从 points_qc 重建 |
| `derived/cells_1min/` | 原始全局 cells（敏感性分析需要） |
| `derived/cells_1min_qcfiltered/` | QC 后全局 cells（主验证输入） |
| `derived/validation_cells_1min/` | 最终验证 cells（08 的输入） |
| `derived/overlap_bias_1min/` | 质量评估依据 |
| `derived/extreme_bias_investigation_1min/` | 质量评估依据 |
| `derived/qcfiltered_comparison_1min/` | QC 效果验证 |
| `manifests/` | 元数据清单 |
| `configs/` | 产品配置 |

---

## 全量运行资源评估

### 命令

```bash
python3 /mnt/data2/00-Data/ship/NCEI_multibeam/code/08_validate_gridded_products_against_ship_cells.py \
  --config /mnt/data2/00-Data/ship/NCEI_multibeam/configs/gridded_products_validation.yaml \
  --overwrite
```

### 时间估算

基于 sample 运行（10,000 cells / 123s）推算全量（2,394,115 cells ≈ 240x）:

| 产品 | Sample 耗时 | 全量估算 | 瓶颈 |
|------|-----------|---------|------|
| GEBCO_2024 | ~3s | **~12 min** | 7.0 GB 网格 I/O |
| ETOPO_2022 | ~5s | **~20 min** | bilinear 插值计算 |
| SRTM15_V2.7 | ~35s | **~140 min** | 6.2 GB + cell agg 循环 |
| SDUST_2023 | ~1s | **~4 min** | 0.6 GB 小网格 |
| TOPO_25.1 | ~2s | **~8 min** | 0.5 GB 小网格 |
| Metrics+Write | ~10s | **~30 min** | 240x 数据量 |
| **总计** | **~123s** | **~3.5-4 小时** | |

> SRTM15 是最大瓶颈：6.2GB 网格 + 逐点 cell 聚合。如果 xarray lazy loading 不够高效，可能更长。

### 资源需求

| 资源 | 需求 | 当前可用 | 状态 |
|------|------|---------|------|
| 磁盘 | ~5 GB 输出 | 13 TB 可用 | ✅ 充足 |
| 内存 | ~16-32 GB（打开大 NetCDF） | 489 GB 可用 | ✅ 充足 |
| CPU | 单核（脚本串行处理产品） | 64 核 | ✅ 充足 |

### 输出文件预估

| 文件 | Sample 大小 | 全量预估 |
|------|-----------|---------|
| validation_by_cell_*.parquet (5个) | ~5 MB | ~500 MB - 1 GB |
| validation_metrics_*.parquet (8个) | ~0.1 MB | ~10-50 MB |
| validation_metrics_*.tsv (8个) | ~0.3 MB | ~50-200 MB |
| model_validation_report.md | 7 KB | ~50 KB |
| **总计** | ~5.5 MB | **~0.6-1.3 GB** |

---

## 数据血缘图（Data Lineage）

```
raw/dat_by_subzip/*.dat
  │  [01] manifest
  ▼
manifests/file_manifest.parquet
  │  [02] standardize
  ▼
derived/points_raw/*.parquet (86 GB, 5083 files)
  │  [03] QC
  ▼
derived/points_qc/*.parquet (86 GB, 5083 files)
  │  [04a] aggregate to cells
  ▼
derived/file_cells_1min/*.parquet (486 MB, 5083 files)
  │  [04b] merge
  ▼
derived/cells_1min/cells.parquet (181 MB)
  │  [05] overlap analysis
  ▼
derived/overlap_bias_1min/* (139 MB)
  │  [06a] extreme source
  ▼
derived/extreme_bias_investigation_1min/* (12 MB)
  │  [06b] quality flags
  ▼
manifests/file_quality_flags_1min.parquet
  │  [06c] rebuild QC-filtered
  ▼
derived/cells_1min_qcfiltered/cells.parquet (180 MB)
  │  [06d] compare
  ▼
derived/qcfiltered_comparison_1min/* (56 MB)
  │  [07] prepare validation cells
  ▼
derived/validation_cells_1min/primary_ship_validation_cells_1min.parquet (180 MB)
  │  [08] validate
  ▼
derived/model_validation_1min/* (5 MB sample → ~1 GB full)
```
