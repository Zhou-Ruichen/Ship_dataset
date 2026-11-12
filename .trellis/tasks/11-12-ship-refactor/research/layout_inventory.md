# Ship 重构设计清单

## 结论

建议把本范围内代码整理成 `ncei.trackline` 与 JAMSTEC multibeam 两个数据包及清晰的内部支链，并把已完成的研究分析退出工作树：

1. `ncei/trackline/` 保留一个 `python -m ncei.trackline` 入口，内部划分来源清单、点表标准化、点质检、格网聚合、质量政策、区域/全球处置、MGD77T、来源改正状态。现行 25 个命令不是一条直线链：其中混有六区原型、静态 MGD77T 的旧 XYZ 转换、新来源质量点表、FAA 转换和跨数据线来源状态表（`ncei/trackline/__main__.py:10-49`）。
2. `jamstec/multibeam/` 增加一个包入口。`05`、`06a` 和 `analysis/06d` 都是主验证格的生产依赖，不应当按名称当成可删审计；`07` 直接读取 `06d` 的 `common_cell_depth_shifts.parquet` 和 `lost_cells.parquet`（`jamstec/multibeam/code/07_prepare_primary_validation_cells_1min.py:45-60`）。
3. `ncei/analysis/` 的 Step 08 v1.0、网络偏差、插值留出和海山候选交付均有结果记录，均属于已完成分析。建议从工作树归档删除，在 `docs/code_archive.md` 登记提交和产物；报告、配置、图和清单保留。JAMSTEC `08–11` 与 `plot_multibeam_figures.py` 同样处理。
4. 旧静态 MGD77T 链 `mgd77t-xyz` 和 `mgd77t-fragments` 默认 XYZ 模式已被 `--source-fields` 的完整来源链取代。保留新链，旧驱动归档删除；`mgd77t_fragments.py` 中旧模式与新模式的 dispatch 拆开（`ncei/trackline/mgd77t_fragments.py:149-167`）。
5. `apply_policy.py` 的规则路径是现实缺陷：代码读取 `.trellis/tasks/05-11-singlebeam-integration/...`，该路径不存在；实际文件位于 `.trellis/tasks/archive/2026-05/05-11-singlebeam-integration/...`（`ncei/trackline/apply_policy.py:68-75`）。重构时把批准规则、冻结校准表移为明确的版本化配置，不能依赖任务归档目录。
6. 外部运行时依赖不只是产品路径。`11-swot-ssl-encoder/scripts/process_ew0202_v1.py:22-38` 把 Ship 根目录加入 `sys.path`，直接导入 `_common.file_io`、`_common.mbsystem.raw_from_object`、`ncei.swath.extract` 和 `ncei.trackline.file_cells`。S 当前工作树已删除 `extract.py` 和 `raw_from_object`，所以该外部入口与流式重建后的工作树不兼容；主代理需要安排迁移，不能只保留旧接口名称。

逐文件事实、调用关系、重复函数和处置见 `layout_inventory.tsv`。本清单覆盖任务开始时路径集合中的 168 个已跟踪文件；代码行数按交付前工作树文本行统计：trackline 20,457，ncei/analysis 9,545，JAMSTEC code 8,432，JAMSTEC analysis 4,804，_common 5,108。基准为 HEAD `1900142`，并计入 S/D 在清点期间对共享文件的修改；未运行任何处理命令。

## 一、现行数据线

### 1. NCEI 原始 trackline 到验证格

实际依赖顺序：

```text
ncei/tracklines_nc + ncei/tracklines_xyz
  -> manifest
  -> standardize-nc / standardize-xyz
  -> clean-mrar（仅区域 MRAR 分支）
  -> point-qc
  -> supplementary-qc
  -> file-cells
  -> merge-cells
  -> source-overlap + branch-overlap
  -> policy-audit（已完成的政策标定）
  -> apply-policy
  -> validation-cells
```

证据：`validation_cells.py:54-68` 读取三类 NCEI 分支格、质量 sidecar 和 JAMSTEC 主验证格；`apply_policy.py:72-85` 读取冻结校准表、交叉重叠表和三类分支格；`policy_audit.py:61-69` 读取前两类重叠分析。各阶段的样本输出函数见 `manifest.py:72-79`、`point_qc.py:157-163`、`file_cells.py:175-182`、`merge_cells.py:183-204`、`validation_cells.py:222-242`。

已交付结果：

- `strict_primary_multibeam_cells.parquet`：2,398,774 行；另产出 expanded、supplementary、regional MRAR 和 catalog。数量断言在 `validation_cells.py:68-74`，交付记录在 `.trellis/tasks/archive/2026-09/09-13-downstream-delivery-contract/result.md:8-18`。
- `points_checked/` 是可引用点层，不只是临时中间表；其 manifest 回填与读取规则见 `docs/数据产品规范与下游接入.md:54-57,184-193`。
- `source-overlap`、`branch-overlap`、`policy-audit` 不是被新版本取代的算法。它们产生现行质量政策的证据和校准输入。建议合并为质量模块的内部阶段，而不是直接删除后让 `apply-policy` 失去输入。

### 2. NCEI 单波束 final r2、交叉点和全球格网

现行 final r2 依赖六区产品和全球产品两组证据：

```text
file_cells_1min + strict_primary_multibeam_cells
  -> global-bias
  -> file_cells_1min_adjusted + sb_track_bias_global/track_bias_summary

points_raw + trackline_source_manifest
  -> global-crossover
  -> global_sb_crossover_audit/{crossovers,pair_stats,track_stats,nc_time_qc,...}

file_cells_1min + strict MB + 六区角色表
  -> track-bias -> 六区 controls / track_bias_summary
points_raw -> crossover -> 六区 crossovers / time QC
上述结果 -> disposition -> 六区 track_quality / reject-arm controls

global-bias + global-crossover + 六区 track_quality / controls
  -> global-disposition
  -> sb_track_quality_global/track_quality.parquet
  -> singlebeam/file_cells_1min_final_r2/
  -> controls_mb_sb_final_<tile>.parquet

strict_primary_multibeam_cells + file_cells_1min_final_r2
  -> global-grid
  -> global_grid_1min_r2/
```

依赖证据：`global_disposition.py:29-39` 列出全部输入输出；`regional_hard_qc` 实读六区处置表，`build_controls` 复用 `track_bias` 函数（`global_disposition.py:158-166,282-322`）；`global_grid.py:27-32,48-77` 定义两层输入和过滤。

结果记录：

- 全球偏差表有 1,647 条有严格多波束参照的航线，83 条应用改正；adjusted 为 5,365 文件、17,294,849 行。全球交叉点 5,205,339 个（`.trellis/tasks/archive/2026-09/09-02-global-sb-bias-product/result.md:12-27`）。
- final r2 为 5,365 文件、17,294,849 行，全球处置表为 5,533 条航线；六区最终控制表同时生成（`.trellis/tasks/archive/2026-09/09-03-global-sb-final-product/result.md:13-32`）。
- `global-grid` 输出 18 个纬度分区及 `product_manifest.json`；主值优先严格多波束，空区由未拒收单波束填充（`global_grid.py:86-125,163-177`）。
- `ncei/analysis/27` 的网络法留出表现不如 Step 23，未进入生产（`.trellis/tasks/archive/2026-09/09-03-sb-network-bias-prototype/result.md:21-45`）；`ncei/analysis/29` 的 1,840.89 -> 731.12 -> 673.19 m 是旧六区控制表的插值结果，不是 final r2 的性能指标（`docs/单波束数据质量处理与下游实验结论.md:27-42`）。

### 3. 静态 MGD77T 点表、FAA NetCDF、来源改正状态

现行交付链：

```text
ncei/raw_round2/mgd77t_static/*/*.{m77t,h77t}
  -> mgd77t.py（原字段、正式头、时间解析）
  -> mgd77t-fragments --source-fields --output-root ...
       -> mgd77t_source_fields.py
       -> point_qc.compute_flag_arrays
       -> file_cells.aggregate_track_file
       -> merge_cells.merge_branch
  -> processing_revision_20261025/trackline/{points_raw,points_checked,
       file_cells_1min,file_cells_1min_basic,merged_cells_1min,source_*}

上述点表 -> crossover --source-points-root ...
       -> mgd77t_crossover.py
       -> trackline/crossovers/{basic,basic_source_quality}/

显式 .m77t/.h77t + 可选旧 NetCDF
  -> mgd77t-netcdf / legacy-faa-revision
  -> legacy_faa/（15 航次）与 legacy_faa_additional/（6 航次）

trackline + legacy FAA + 六航次 swath 清单、头、MB41 前导和 .inf
  -> source-corrections
  -> processing_revision_20261025/source_corrections/
```

调用证据：`mgd77t_source_fields.py:20-22,403-476`；`crossover.py:1010-1025` 将来源点模式转发给 `mgd77t_crossover.py`；`legacy_faa_revision.py:301-340,343-417` 区分通用附加清单与最初 15 航次审计。

已交付结果：

- 695 个来源保留 150,587,793 条原观测；主选择为 105,457,041 点、1,235,712 个航线格；单波束与多波束文件均衡合并分别为 959,389 和 122,616 格。记录见 `.trellis/tasks/10-25-ship-processing-repair/mgd77t_result.md:1-31`。
- AR1-06 独立转换已有完整小输入对照，338,605 条原记录，主选择 291,031 点、879 格；77 个可比字段和两类格网统计与完整批次一致（同文件 `:109-140`）。
- 六区两种选择均没有支持的本批航次交叉点；输出不是“零偏差”估计（同文件 `:157-184`）。
- 15 个 FAA 航次保留 512,234 条观测；追加 6 航次保留 304,615 条。见 `legacy_faa_result.md:1-15` 和 `additional_faa_result.md:1-18`。
- 来源改正状态覆盖 695 条静态航线、21 个 FAA 产品、1,508 个 swath 产品文件及一个证据样本；`evidence_texts.parquet` 为 11,422 行（`source_corrections_result.md:12-27`）。

旧 `mgd77t_xyz.py` 和默认 fragment 产生 `ncei/derived/sb_round2_static/`；新来源字段模式产生 `processing_revision_20261025/trackline/`。后者是当前交付，前者保留历史产品即可，旧代码可凭提交恢复。

### 4. JAMSTEC 多波束

生产顺序以 `docs/多波束船测数据处理流程.md` 和 `jamstec/multibeam/docs/PIPELINE_PROCESSING_GUIDE.md:9-47` 为记录，实际代码依赖为：

```text
archive -> 01_extract_subzips.sh -> 02_check_subzips.sh
  -> 03_recursive_extract.py -> 04_organize_dat.sh
  -> 01_build_multibeam_manifest.py
  -> 02a_curate_points_manifest.py
  -> 02_standardize_multibeam_xyz.py
  -> 03_qc_multibeam_points.py
  -> 04a_make_multibeam_file_cells.py
  -> 04b_merge_multibeam_cells.py
  -> 05_analyze_cell_overlap_bias.py
  -> 06a_investigate_extreme_bias_sources.py
  -> 06b_create_file_quality_flags_1min.py
  -> 06c_rebuild_cells_1min_qcfiltered.py
  -> analysis/06d_compare_original_vs_qcfiltered_cells.py
  -> 07_prepare_primary_validation_cells_1min.py
```

`02` 实际读取 curated manifest，而非文档中仍写的原始 `file_manifest.parquet`（`02_standardize_multibeam_xyz.py:73-80`）。`06b` 读取 `06a` 的动作和审计表（`06b_create_file_quality_flags_1min.py:48-60`），`06c` 生成 QC-filtered cells（`06c_rebuild_cells_1min_qcfiltered.py:41-52`），`06d` 生成 `07` 所需对照表（`analysis/06d_compare_original_vs_qcfiltered_cells.py:34-46`）。

主产品为 `derived/validation_cells_1min/primary_ship_validation_cells_1min.parquet`，README 记录 2,394,115 格；它还进入 NCEI `validation-cells`。`08–11` 是全球模型/SWOT/残差分析，不再属于这条生产命令列表。

## 二、建议目标布局

### 1. `ncei/trackline/`

```text
ncei/trackline/
├── __main__.py             # 唯一 CLI；--help 不导入计算模块
├── manifest.py             # L3 来源清单与 R2 分类
├── standardize_singlebeam.py
├── standardize_xyz.py
├── clean_mrar.py
├── point_qc.py             # 可复用逐点规则
├── entry_manifest.py       # 从 point_qc.py 拆出批次、入口清单和报告
├── supplementary_qc.py
├── file_cells.py           # 保持选择/聚合 API；swath 与外部 EW0202 在用
├── merge_cells.py
├── quality_overlap.py      # 合并 source_overlap + branch_overlap 的共享读取/统计
├── quality_policy.py       # apply_policy；读取版本化规则与冻结校准配置
├── validation_cells.py     # 编排质量侧车和五类验证产品
├── regional_quality.py     # 六区命令编排；共享函数留在下述模块
├── track_bias.py
├── crossover.py            # 六区几何 + 全球/MGD77T 共用函数
├── disposition.py
├── global_bias.py
├── global_crossover.py
├── global_disposition.py
├── global_grid.py
├── mgd77t.py               # 纯 parser
├── mgd77t_points.py        # 现 mgd77t_source_fields
├── mgd77t_crossover.py
├── mgd77t_netcdf.py        # 单源转换
├── mgd77t_faa.py           # 显式批次、旧行对齐与核对
└── source_corrections.py   # 跨线交付命令；位置需主代理确认
```

建议保留的公共命令：

| 命令 | 作用 |
|---|---|
| `manifest`, `standardize-nc`, `standardize-xyz`, `clean-mrar` | 来源清单与各来源 L1 |
| `point-qc`, `supplementary-qc`, `file-cells`, `merge-cells` | 点质检与 L2 |
| `validation-cells` | 内部调用 overlap、质量政策和五类验证格；旧校准驱动不作为并列命令 |
| `regional-quality` | 依次执行六区 bias、crossover、disposition；共享函数仍可导入 |
| `global-bias`, `global-crossover`, `global-disposition`, `global-grid` | 全球 final r2 与格网 |
| `mgd77t-points`, `mgd77t-crossovers` | 完整来源点表、格网和来源索引交叉点 |
| `mgd77t-netcdf` | 单源及显式清单批转换、旧产品对齐、`--verify-only` |
| `source-corrections` | 已交付来源状态表 |

`policy_audit.py` 的候选规则探索驱动归档；批准的 16 条规则和冻结校准表进入 `ncei/configs/` 或其他主代理指定的版本化产品配置。`source_overlap.py`、`branch_overlap.py` 的有效计算并入质量模块，不把三个旧命令原样保留。

### 2. `jamstec/multibeam/`

```text
jamstec/multibeam/
├── __main__.py
├── source/                  # 现有 3 个 shell + recursive_extract；由 extract 调用
├── manifest.py
├── curate.py
├── standardize.py
├── point_qc.py
├── file_cells.py
├── merge_cells.py
├── overlap.py               # 05
├── source_quality.py        # 06a + 06b；硬编码例外规则转配置
├── qcfiltered_cells.py      # 06c
├── compare_cells.py         # 06d，生产依赖
└── validation_cells.py      # 07
```

公共命令为 `extract`、`manifest`、`curate`、`standardize`、`point-qc`、`file-cells`、`merge-cells`、`quality`、`validation-cells`。`quality` 内部依次执行 05、06a、06b、06c、06d。`06d` 从 analysis 移回生产模块。

### 3. 退出工作树的代码

建议归档删除，并在 `docs/code_archive.md` 写明用途、结果和删除前最后提交：

- `ncei/analysis/14–22`：冻结 Step 08 v1.0；其中 `14` 动态加载 JAMSTEC `08`（`14_validate_gridded_products_step08.py:64-73,255-263`），两者同一归档组。
- `ncei/analysis/27`、`29`：已有负面/留出结论，不在生产链。
- `ncei/analysis/seamount_candidate_delivery.py`：已完成 58 候选的 12.5 km 点和 90 km 格交付；结果记录为 `.trellis/tasks/10-21-mb-round2-quality-revision/result.md:573-610`，代码提交 `222e9b1`。
- `jamstec/multibeam/analysis/08–11`、`plot_multibeam_figures.py`：冻结分析和已交付图。
- `ncei/trackline/mgd77t_xyz.py` 与 `mgd77t_fragments.py` 的旧默认 XYZ 分支。
- `_common/r2_calibration.py`、仅服务其标定/测试的 `io_helpers.py`、`_common/calibration/` 输出；阈值已固定在 `r2_classifier.py`。
- `_common/tests/fixtures/`：`_common/README.md:45-47` 明确写明当前测试不导入这些 SCS fixture。

所有删除均以结果记录能定位含代码的提交为前置。当前 HEAD 包含这些文件；实际归档索引应写删除提交的父亲，不要沿用上一轮 `bc4cd36` 充当本轮新增代码的最后提交。

## 三、保留命令的小输入对照

原则：比较 schema、行键、逐列数值和缺测，不要求含时间戳的 manifest 或 Parquet 字节相同。表中路径均已做存在性检查，特别标出的缺失项除外。完整产品作为参照时，只比较小输入覆盖的键；需要整格贡献闭包的命令，输入必须包含这些格的全部来源文件。

### 1. NCEI trackline

| 保留命令 | 小输入 | 参考产品路径 |
|---|---|---|
| `manifest` | 2 个 `.nc` + 2 个 `.xyz`，含一个多波束预测 | `ncei/manifests/trackline_source_manifest.parquet` 按 `(track_id,source_type)` 取行；当前不存在 `_sample.parquet` |
| `standardize-nc` | 上述 2 个 NC | `ncei/manifests/singlebeam_points_raw_manifest_sample.parquet`；点值对照 `ncei/derived/singlebeam/points_raw/` 同名文件 |
| `standardize-xyz` | 1 个 singlebeam + 1 个 multibeam XYZ | `ncei/manifests/xyz_points_raw_manifest_sample.parquet`；点值对照 `derived/{singlebeam,multibeam}/points_raw/` |
| `clean-mrar` | 每象限 1,000 行 | `ncei/archive/zhoushuai_processed_M/bathymetry_points_sample.parquet`、`land_mask_sample.parquet`、`cleaning_audit_sample.parquet` |
| `point-qc` | 1 NC、1 XYZ、1 个 MRAR 象限 | `ncei/manifests/bathymetry_entry_manifest_sample.parquet`；点值对照正式 `points_checked/` 同名文件 |
| `supplementary-qc` | 同上，加一对相交航线 | `ncei/manifests/bathymetry_entry_manifest_supplementary_sample.parquet`、`intersect_divergence_audit_sample.parquet` |
| `file-cells` | 1 NC、1 XYZ、1 个 MRAR 象限 | `ncei/manifests/file_cells_1min_manifest_sample.parquet`；正式 `file_cells_1min/` 同名文件 |
| `merge-cells` | 每分支取 sample manifest 所列文件 | `ncei/manifests/cells_1min_manifest_sample.parquet` 与 `ncei/derived/{singlebeam,multibeam,regional_mrar}/cells_1min_sample/` |
| `validation-cells` | 现有 sample 分支格、overlap、冻结规则/校准、JAMSTEC sample | `ncei/derived/overlap_bias_1min_sample/`、`cross_branch_overlap_1min_sample/`、`quality_policy_calibration_1min_sample/`、`quality_flags_1min_sample/`、`validation_cells_1min_sample/` |
| `regional-quality` | `lon068_lat018` 的角色表、严格 MB、该 bbox 航线点和格 | `ncei/derived/sb_track_bias_1min/*lon068_lat018*`、`true_crossover_audit/*lon068_lat018*`、`sb_track_quality_1min/track_quality_lon068_lat018.parquet` |
| `global-bias` | `odp130jr` 的 file cells、其共址严格 MB 和 manifest 行 | `ncei/derived/sb_track_bias_global/track_bias_summary.parquet` 对应行；`singlebeam/file_cells_1min_adjusted/odp130jr__xyz.parquet` |
| `global-crossover` | 一个已完成叶 tile 所需的航线与点，保留原 bbox/margin | `ncei/derived/global_sb_crossover_audit/tiles/crossovers_lon000_lat010_sw_sw.parquet`；不能把全球表裁剪当参照 |
| `global-disposition` | `odp130jr` 及其所在 tile 的事件、全球 bias、六区硬 QC 和 adjusted 文件 | `ncei/derived/sb_track_quality_global/track_quality.parquet` 对应行；`singlebeam/file_cells_1min_final_r2/odp130jr__xyz.parquet` |
| `global-grid` | `lat_band_10deg=0` 的严格 MB 与 final SB 全量行 | `ncei/derived/global_grid_1min_r2/lat_band_10deg=0/part-00000.parquet` |
| `mgd77t-points` | AR1-06 的 `.m77t/.h77t`，禁用历史比较；分类另传保留预测做第二次对照 | `ncei/derived/processing_revision_20261025/trackline/independent_source_check/{points_raw,points_checked,file_cells_1min,file_cells_1min_basic}/` |
| `mgd77t-crossovers` | `lon052_lat018` 内有段航线及两种选择点表 | `.../trackline/crossovers/{basic,basic_source_quality}/*lon052_lat018.parquet`、根目录 `region_summary.csv` |
| `mgd77t-netcdf` | `cntl01rr` 的完整 `.m77t/.h77t`、旧 NC；再用 `--verify-only` | `.../legacy_faa_additional/netcdf/cntl01rr.nc`、`row_mapping/cntl01rr.parquet`、`field_comparison.csv` |
| `source-corrections` | AR1-06、cntl01rr、一个 HNRO05RR 产品文件及对应头/.inf/前导 | `.../source_corrections/{trackline_source_corrections,legacy_faa_source_corrections,swath_source_corrections,evidence_texts}.parquet` 按主键取行 |

`...` 在上一表中表示 `ncei/derived/processing_revision_20261025/`。

### 2. JAMSTEC multibeam

| 保留命令 | 小输入 | 参考产品路径 |
|---|---|---|
| `extract` | 一个含嵌套 zip 的 subzip 和一个正常 subzip | `jamstec/multibeam/docs/{bad_nested_zips.txt,bad_subzips.txt,dat_manifest.tsv}`；按 subzip/file 键核对 |
| `manifest` | `manifests/samples/file_manifest_sample.tsv` 所列输入子集 | `jamstec/multibeam/manifests/samples/{file_manifest_sample.tsv,subzip_manifest_sample.tsv,nonstandard_dat_files_sample.tsv}` |
| `curate` | 上项 file manifest，含 transit/重复候选 | `jamstec/multibeam/manifests/{file_manifest_points_raw.tsv,excluded_from_points_raw.tsv}` 按 `file_id` 取行 |
| `standardize` | `points_raw_manifest_sample.tsv` 所列源文件 | `jamstec/multibeam/derived/points_raw_sample/`、`manifests/points_raw_manifest_sample.tsv` |
| `point-qc` | 上项 sample 点表 | `jamstec/multibeam/derived/points_qc_sample/`、`manifests/points_qc_manifest_sample.tsv` |
| `file-cells` | 上项 sample QC 点表 | `jamstec/multibeam/derived/file_cells_1min_sample/`、`manifests/file_cells_manifest_1min_sample.tsv` |
| `merge-cells` | sample file-cell manifest 所列文件 | `jamstec/multibeam/derived/cells_1min_sample/cells.parquet`、`manifests/cells_manifest_1min_sample.tsv` |
| `quality` | 现有 05/06a sample；06b–06d 选 20 格并纳入全部贡献文件 | `derived/{overlap_bias_1min_sample,extreme_bias_investigation_1min_sample}/`；正式 `manifests/file_quality_flags_1min.parquet`、`derived/{cells_1min_qcfiltered,qcfiltered_comparison_1min}/` 按 file/cell 键取行 |
| `validation-cells` | 上项 20 格的 original/QC-filtered/comparison 全量行 | `jamstec/multibeam/derived/validation_cells_1min/{primary_ship_validation_cells_1min.parquet,sensitivity_original_ship_cells_1min.parquet,validation_cells_1min_summary.parquet}` 按 `cell_id` 取行 |

## 四、重复实现与合并边界

AST 同名扫描的完整逐文件结果写入 TSV `duplicates` 列。需要实际合并的组：

| 函数 | 位置 | 建议 |
|---|---|---|
| `atomic_write_df` | JAMSTEC 01/02/03/04a 与 `_common/file_io.py` | 四份 AST 相同，改用 `_common.file_io` |
| `atomic_write_parquet/text/tsv` | JAMSTEC 04b/05/06a、JAMSTEC analysis、NCEI analysis | 生产模块使用 `_common`；归档分析不为此改写 |
| `setup_logging` | JAMSTEC 01/02/02a/03/04a/04b/05/06a 与 NCEI analysis | JAMSTEC 生产模块合并；归档分析不改 |
| `file_id_to_parquet_name` | JAMSTEC 03、04a | 两份相同，放 JAMSTEC 来源/点表模块 |
| `suffix_for_run` | trackline apply/branch/merge/policy/source/validation | 六份相同，放包内运行配置模块 |
| `safe_quantile`、`safe_rmse` | policy_audit、branch_overlap、source_overlap | 三份相同，进入 `quality_overlap.py` |
| `branch_cells_dir`、`read_parquet_schema`、`repo_path`、`read_required_parquet` | 上述质量模块及 merge/apply | 合并到质量模块的读取层 |
| `normalize_lon`、`sanitize_lat` | standardize_singlebeam、standardize_xyz | 两路相同实现放包内点表工具；MRAR 的不同实现不强行统一 |
| `compute_lat_band` | apply/validation 相同，branch/merge/policy 有 dtype 差异 | 统一前先以样本对照确定 dtype 合同 |
| `assign_depth_bin` | JAMSTEC 09/10 相同，另见于 08 和 NCEI 14 | 属拟归档分析，不新增生产抽象 |
| `nmad` | `_common.singlebeam_bias` 与 NCEI analysis 27 | 生产继续共用；27 随分析归档 |
| `configure_logging`、`sha256_file` | NCEI analysis 21/22 | 同属冻结 Step 08，随该组归档 |
| `merge_cells` | JAMSTEC 04b 与 06c | 名称相同但输入/职责不同；可复用纯聚合核，保留 QC 追踪在外层 |
| `decode_time` | `mgd77t.py` 与 `standardize_singlebeam.py` | 不同格式和时间合同，仅改名明确来源，不合并实现 |

`cell_id` 不应仅为减少重复而统一：JAMSTEC/NCEI 的字符串格号与 NCEI analysis 29 的整数键是不同接口。保留现行产品键，新增公共函数必须先证明映射一致。

## 五、外部使用

### 1. 运行时导入或调用 Ship 代码

| 仓库 | 类型 | 证据与受影响接口 |
|---|---|---|
| `11-swot-ssl-encoder` | 源码声明运行时导入 | `scripts/process_ew0202_v1.py:22-38` 将 `/mnt/data2/00-Data/ship` 加入 `sys.path`，导入 `_common.file_io`、`_common.mbsystem.raw_from_object`、`ncei.swath.extract`、`ncei.trackline.file_cells`。其结果记录说明调用 `extract.process_one_file`、`extract.merge_cruise`、`file_cells.aggregate_track_file`（该仓库 `.trellis/tasks/archive/2026-11/11-08-ew0202-swath-processing/result.md:75-91`）。归档副本 `process_entry_before.py:35-38` 也有同样导入。S 当前工作树已移除前两类 swath 接口，外部脚本需要迁移。 |
| 其余 11 个已检 git 仓库 | 未发现这些包的运行时 import | 对 `/mnt/data2/06-Projects/{00-Experiment-Log,02-swot-qaware-reconstruction,03-Unet_topo,05-unet,06-seafloor_topo,10-topo_baseline,12-ggm_scs,13-Parker-Oldenburg_scs,14-seamounts,15-swot_feature_physics_bathy,16-aam-eop-forecasting}` 的已跟踪 Python 做了 import 语法检索。 |

`15-swot_feature_physics_bathy/scripts/69_ship_crossover_noise.py:7-18` 是在 docstring 中沿用旧 `ncei/code/24` 方法，并非 import；其实际输入是 Ship 点表和区域质量表（同文件 `:40-53`）。

### 2. 产品读取和文字提及

- `12-ggm_scs`：大量运行代码直接读 strict MB、final r2、入口清单等，例如 `src/scs_ggm/control_fits.py:50-55` 和 `scripts/run_ggm_leveled_sensitivity.py:138`。这是产品读取，不是 Ship 代码导入。
- `13-Parker-Oldenburg_scs`：`configs/default.yaml:21-26` 配置 strict MB 路径，`scripts/run_parker_oldenburg.py:37` 检查该输入。属于配置驱动产品读取。
- `14-seamounts`：`scripts/diagnose_object_association.py:34` 读取 strict MB，`scripts/inventory_jamstec_sources.py:34-37` 读取 JAMSTEC manifest 和原始 `.dat`。海山候选交付的 Ship 端入口已完成，结果记录没有显示下游导入 Ship Python 包。
- `11-swot-ssl-encoder`：除代码导入外，还读取 final r2、严格 MB、MGD77T 修订、FAA 和来源状态表，例如 `scripts/build_nonideal_data_roles.py:32-41`。
- `00-Experiment-Log`：是仓库和产品登记，例 `external-repositories/ship.md:35-61`，不是运行时导入。
- `02-swot-qaware-reconstruction`、`03-Unet_topo`、`05-unet`、`06-seafloor_topo`、`10-topo_baseline`、`16-aam-eop-forecasting`：本轮对已跟踪代码/文档的指定路径和包名检索无命中。

### 3. `consumers.yaml` 登记路径

只有 `12-ggm_scs` 两条正式登记（`consumers.yaml:34-45`）：

- `ncei/derived/singlebeam/file_cells_1min_final_r2/`，round `_r2`；
- `ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet`，round `latest`。

注释另登记通知时需要说明的读取位置（`consumers.yaml:27-32`）：

- `ncei/derived/singlebeam/points_checked/`；
- `ncei/manifests/bathymetry_entry_manifest.parquet`；
- `ncei/derived/validation_cells_1min/regional_mrar_experiment_cells.parquet`。

`11-swot-ssl-encoder` 的代码导入和修订产品读取、`13`/`14`/`15` 的产品读取不在正式登记表中。建议主代理决定是否补登；至少把 EW0202 的代码接口依赖写入重构实施规格，不能只按 `consumers.yaml` 判断兼容性。

## 六、事实、推断与待决定事项

### 事实

- 现行命令和读写路径来自工作树 AST/源码；产品数字来自指定结果记录。
- 上述小输入参考路径已检查存在；`trackline_source_manifest_sample.parquet` 不存在，故 manifest 对照改用正式表按键取行。
- `apply_policy.py` 当前规则路径不存在，归档路径下的规则文件存在。
- 外部运行时 import 检查覆盖 `/mnt/data2/06-Projects` 下 12 个 git 仓库的已跟踪文件；未把纯路径读取误判为代码导入。

### 设计推断

- 归档冻结分析不会删除其报告、数据产品或图；代码可用归档索引所列提交恢复。
- 将六区三个驱动收成一个命令是入口整理，不改变其算法；`track_bias.py`、`crossover.py`、`disposition.py` 的函数仍需保留，因为全球处置和 MGD77T 交叉点正在复用。
- 将 JAMSTEC 05/06a/06d 纳入 `quality` 是依据真实输入依赖，不是按文件名重新分类。

### 需要主代理写进实施规格的决定

1. 是否按本清单归档全部冻结分析；建议照做，并同步保留报告和结果提交指针。
2. 质量政策的配置落点。建议 `ncei/configs/` 保存批准规则，冻结校准表作为版本化输入；同时修复失效规则路径。
3. `source_corrections.py` 横跨 trackline、FAA、swath。建议暂留 trackline 入口，待明确是否需要一个跨线 `processing-revision` 命令；不要在未定时复制成多个入口。
4. FAA 的通用接口。建议保留单源转换和显式清单批处理，归档最初 15 航次专用审计驱动；通用批处理仍需支持旧 NC 对齐和 `--verify-only`。
5. 与 S 的接口分界及外部迁移。`file_cells.py` 和旧 `_common/mbsystem.py` 已被外部 EW0202 直接导入；S 当前已删除外部脚本所需的 `raw_from_object` 和 `ncei.swath.extract`。实施规格需要指定 EW0202 新调用方式和实际复算负责人。
6. 是否把 `11`、`13`、`14`、`15` 补入 `consumers.yaml`，以及代码接口是否另建依赖登记。当前文件只覆盖 `12` 的产品通知。
