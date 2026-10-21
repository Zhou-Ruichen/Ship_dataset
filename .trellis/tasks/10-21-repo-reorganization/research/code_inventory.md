# 代码清点报告（Phase 1，只读）

任务：`.trellis/tasks/10-21-repo-reorganization/prd.md`。逐文件明细见同目录 `code_inventory.tsv`（132 行，含未跟踪 3 个）。本页是汇总与处置建议，供主代理决定目录布局。

---

## 1. 总量与分组

| group | 文件数 | 行数 | 内容 |
|---|---:|---:|---|
| scs_confirmation | 37 | 21,658 | SCS/TN352 封存确认链（discover/prepare/verify/audit 各阶段脚本）|
| ncei_singlebeam_processing | 20 | 18,259 | NCEI 单波束 01–31 主链 |
| validation_analysis | 17 | 12,270 | Step 08 全球模型验证（14–22）+ jamstec 09–11 残差/SWOT |
| jamstec_processing | 12 | 8,906 | JAMSTEC 多波束 01–08 主链 |
| ncei_round2_swath_processing | 10 | 2,052 | round-2 swath 32–40 链 |
| test | 17 | 3,689 | `_common/tests/`（16 个中 14 个属 SCS 链）|
| download | 6 | 989 | jamstec 4 个 shell + tier-A/B 下载器 |
| shared_helper | 8 | 767 | `_common/`（除 oracle 外都在用）|
| tooling | 3 | 430 | 05_cleanup.sh、42_backfill、rewrite_paths |
| global_grid | 1 | 244 | 31_build_global_grid_1min.py |

处置建议汇总：keep_core 50 / keep_analysis 27 / archive 54 / delete 0 / unknown 0。未建议直接 delete：SCS 链虽已完成，仍产出过发布数字，按 PRD 规则须等结果记录指名提交后再移出工作树；delete 候选仅 `jamstec/multibeam/code/05_cleanup.sh`（纯删盘脚本、0 文档引用），保守起见标 archive。

测试与确认链合计 25,347 行，占全部代码（含未跟踪 3 个，共 69,430 行）的 37%，这是“测试代码太多”的直接来源；keep_core 的下载+处理主体是 50 个文件。

## 2. 核心链（数据流顺序）

**下载（JAMSTEC，一次性，源在 `jamstec/multibeam/archive/`）**
`01_extract_subzips.sh` + `03_recursive_extract.py` + `02_check_subzips.sh` + `04_organize_dat.sh` → `raw/dat_by_subzip/*.dat`

**JAMSTEC 多波束处理 01→11**
raw .dat → `01_build_multibeam_manifest` → `02_standardize` → `02a_curate` → `03_qc` → `04a file cells` → `04b merge cells` → `05 overlap bias`（分析）→ `06b file flags` → `06c qcfiltered cells` → `06d 对比`（分析）→ `07 primary validation cells`（核心产品 `primary_ship_validation_cells_1min.parquet`）→ `08 validate gridded products`（核心）→ `09–11` SWOT/残差基线（分析）。

**NCEI 单波束 01→31（当前生产链）**
`tracklines_nc/ + tracklines_xyz/` → `01_build_trackline_source_manifest`（L3）→ `02 nc` + `03 xyz`（L1）→ `05 points_checked`（L1 可引用层）→ `06 补充质检`（分析）→ `07 file_cells_1min`（L2，函数被 round-2 复用）→ `08 cells_1min` → `09–12` overlap/质量策略（分析，产出 quality_flags）→ `13 validation cells`（strict_primary 产品）→ `25 global bias` → `26 global crossover` → `30 disposition`（`file_cells_1min_final_r2` 产品）→ `31 global grid`（`global_grid_1min_r2` 产品）。
区域链 23/24/27/28 是 25/26/30 的六区原型，`29` 产出规范文档第 3 节的证据表。

**round-2 swath 32→40 + 下载**
`38_mbbdb_value_ranking`（A/B/C 排序表）→ `41_tier_a_gapfill` + `download_tier_a_round2`（正在跑，由 `/tmp/tierB_gapfill/supervise.sh` 循环调用 41）→ `raw_round2/` → `41_gzip_preflight` → `32 completeness` → `33 format census` → `34 L1 提取`（依赖封存 mbsystem 环境和 scs 辅助模块）→ `35 L2` → `36 L3 fragment`（待合并审查）→ `37 coverage`；旁路 `39/40` MGD77T 静态树三层化。

**Step 08 验证 v1.0（已冻结，b376f95）**
`14` 批量验证 → `15` strict vs expanded → `16` 非主层诊断 → `17` 最终报告 → `18` bootstrap → `19` 表 → `20` gapfill 结构 → `21` 图 → `22` 摘要。全部 keep_analysis：重跑仅在新轮次。

## 3. 测试覆盖

| 测试 | 覆盖模块 | 模块状态 |
|---|---|---|
| `test_r2_classifier.py`（188 行）| `_common.r2_classifier` + `io_helpers` | 在用（L3 分类、round-2 复用）——keep |
| `_common/tests/scs_confirmation/` 14 个（约 3,500 行）| 仅 SCS 链 37 个脚本 + `_common/scs_v2_stage_c1_oracle.py` | 链已封存；模块不再运行 |
| 其中 `test_scs_v2_stage_c1_readiness.py`、`test_scs_v2_stage_c_processing.py` 等 | `scs_v2_stage_c_processing.py` | **例外：该模块仍被 `ncei/code/34` import（`_raw_from_object`、mblist 适配器），归档前需先把共享部分抽到 `_common/` 或独立模块** |

## 4. 重复辅助函数（抽取到 `_common/` 候选）

AST 扫描（顶层 def 同名，排除 tests/scs_confirmation/scripts）共 87 组同名；以下为跨脚本复制、实现基本相同的：

| 函数 | 出现文件数 | 说明 |
|---|---:|---|
| `atomic_write_parquet` / `atomic_parquet` / `atomic_write_df`（同族）| 31 + 6 + 4 | jamstec 链每脚本一份；ncei 链一份 `atomic_parquet`。最高优先抽取 |
| `setup_logging` | 29 | 每脚本同实现 |
| `atomic_write_text` / `atomic_text` / `atomic_write_tsv` | 29 + 7 + 27 | 同上 |
| `markdown_table` / `fmt` | 23 + 16 | 报告表格式化 |
| `make_report` / `write_report` / `generate_report` / `build_report` | 20 + 8 + 6 + 4 | 报告骨架 |
| `parse_args`（run-label 门控 + `--confirm-full`）| 14 | README 关键约定的实现散布各脚本 |
| `get_output_paths` / `output_paths` / `get_run_paths` / `output_dir_for_run` / `suffix_for_run`（run-label 输出目录族）| 14 + 7 + 4 + 4 + 6 | 两套命名、同一语义 |
| `existing_outputs` / `ensure_writable` / `estimate_only` | 5 + 4 + 4 | 可恢复运行检查 |
| `write_errors_tsv`（per-file failure 模式）| 6 | README 关键约定 |
| `nmad` | 5（含 `_common/singlebeam_bias.py`）| 已有共享版，4 个脚本仍各带一份 |
| `compute_lat_band`（hive 分区）| 5 | ncei 链 |
| `sha256_file` | 4 | product manifest 族 |
| `normalize_bool_series` / `ensure_columns` | 6 + 4 | ncei 链 |
| `file_id_to_parquet_name` | 3（03/04a + scs audit）| file_id 主键约定 |
| cell_id 计算 | 3 处不同实现（`04a cell_id_from_bins`、`29 encode_cell_id`、spec 定义） | 格子主键约定应集中一处 |

## 5. 路径引用影响（移动 `ncei/code/`、`jamstec/multibeam/code/` 的代价）

- 已跟踪文档/yaml/json 引用 `ncei/code/`：22 个文件（ncei/docs 17、ncei/configs 2、README.md、AGENTS.md、docs/数据产品规范与下游接入.md）。主要引用者：`ncei/docs/README.md`（管线总表）、`docs/数据产品规范与下游接入.md`、`README.md`。
- 引用 `jamstec/multibeam/code/`：5 个文件（`docs/多波束船测数据处理流程.md`、`jamstec/multibeam/docs/PIPELINE_PROCESSING_GUIDE.md`、README.md 等）。
- `.trellis/spec/`：0 个引用（无影响）。
- 磁盘上 7 个 `product_manifest*.json` 中 5 个把脚本相对路径写进 `created_by`/`backfilled_by` 命令字段（25/26/30/31/13/05/42 被点名）；manifest 是历史记录，不随重排改写，但新轮次命令要写新路径。
- 未跟踪 3 个下载脚本无任何文档引用；但 `/tmp/tierB_gapfill/supervise.sh` 硬编码 `ncei/code/41_tier_a_gapfill.py`——冻结期内不可移动。
- `ncei/code/34` 硬编码 `ncei/code/scs_confirmation/scs_v2_stage_c_processing.py` 路径（importlib 加载）和封存环境路径；`41_gzip_preflight.py` 硬编码环境 gzip 路径。归档 scs_confirmation 前必须先解耦。
- 派生目录脚本：`ncei/derived/mb_round2/_runs/` 下 3 个一次性运行脚本（`run_l2_l3.py` 等硬编码 `ncei/code/07` 路径），属任务 10-21-mb-round2-quality-revision 产物，随该任务处置。`ncei/derived/scs_v2_sealed_confirmation/`（63 GB）是封存确认链的固定环境+证据，不是代码，不动；README 需说明其 63 GB 占用与角色。

## 6. 目标目录布局草图（建议，主代理定夺）

```
ship/
├── download/                  # 全部下载入口（6 个：jamstec 4 shell + tierA/B 2 个 py）
├── pipelines/
│   ├── jamstec_multibeam/     # 01–08(+plot) 主链 12 脚本
│   ├── ncei_singlebeam/       # 01–31 主链 20 脚本（09–12、23–28 拆到 analyses/ 亦可）
│   └── ncei_round2_swath/     # 32–40 链（冻结期与 10-21 任务落地后再动）
├── analyses/                  # 一次性/冻结分析：jamstec 05/06a/06d/09–11、ncei 14–22、27–29、04_clean_mrar
├── _common/                   # r2_classifier、io_helpers、singlebeam_bias + 新抽的 atomic_io、run_label、report_utils、grid(1' cell_id)
├── tools/                     # 42_backfill_product_manifests、（归档 rewrite_paths）
├── tests/                     # test_r2_classifier（SCS 链测试随链归档）
└── archive/code/              # 归档索引 + 移出工作树的脚本（git show <commit>:<path> 可恢复）
```

另一种低成本方案：目录不动，把 `ncei/code/scs_confirmation/`、`_common/tests/scs_confirmation/`、`_common/scs_v2_stage_c1_oracle.py`、`scripts/`、`jamstec 05_cleanup.sh` 归档，README 用一张 30 行的核心链表指路。改动面接近零（22+5 个文档引用不动），先解决 46% 的观感问题；全面重排留到 Tier-B 结束、10-21-mb-round2 落地后一次做完。

### 需要主代理判断的处置问题

1. **`scs_v2_stage_c_processing.py` 的双重身份**：属封存链，又被 `ncei/code/34`（活跃 round-2 L1 提取）import。选项：抽共享部分（mblist 适配、`_raw_from_object`、raw schema）进 `_common/mblist.py` 后整链归档；或整链延后归档。
2. **`download_tier_a_round2.py` vs `41_tier_a_gapfill.py`**：功能后者涵盖前者；前者仅被下载日志语义引用。建议等 Tier-B 结束后 merge_into `41_tier_a_gapfill.py`（先补结果记录）。
3. **`r2_calibration.py`**：一次性标定驱动，阈值已冻结进 `r2_classifier.py`。产出过标定数字；建议 keep_analysis 而非 archive，重训分类器时仍要用。
4. **Step 08 全家（14–22）**：v1.0 已冻结；数字进过发布摘要。建议原地保留（keep_analysis），新轮次到来前不再运行，不迁移。
5. **`42_backfill_product_manifests.py`**：一次性，但两个 manifest 的 `backfilled_by` 字段点名它。保留至下轮 manifest 自然重生成。
6. **jamstec 09–11（SWOT T1/残差基线）**：doc_refs 0–1，但 README Step 09–11 与 `docs/experiments/2026-05_swot_t1_residual_baseline.md` 依赖其存在。keep_analysis，不删。
7. **派生运行脚本 3 个**（`mb_round2/_runs/`）：属任务 10-21-mb-round2-quality-revision，冻结期内不动，交该任务 owner 处置。
8. **`05_cleanup.sh`**：唯一 delete 候选（无引用、纯 rm -rf）；因具破坏性且不可复现其"运行过"的证据价值有限，建议 archive 而非 delete。

---

## 附：文档状态表

### ncei/docs/（53 项）

| 文件 | 状态 |
|---|---|
| README.md | 当前管线总表（引用全部 01–13 脚本）|
| trackline_source_manifest_schema.md | 当前产品说明（L3 逐列语义）|
| trackline_source_manifest_report.md | 当前产品说明（L3 生成报告）|
| singlebeam_standardization_report.md / xyz_standardization_report.md | 历史阶段报告（L1 02/03）|
| mrar_cleaning_report.md | 历史阶段报告（04_clean_mrar）|
| step03_point_quality_check_report.md | 当前产品说明（points_checked manifest 的权威生成记录）|
| step03b_supplementary_checks_report.md | 历史阶段报告 |
| step04_aggregation_design_audit.md / step04a_file_cells_1min_report.md / step04b_cells_1min_merge_report.md | 历史阶段报告（L2 04A/04B）|
| step05a_source_specific_overlap_bias_report.md / step05b_cross_branch_overlap_audit_report.md | 历史阶段报告 |
| step06a_quality_policy_calibration_report.md / step06b_cell_quality_flags_report.md / step06b_quality_policy_rule_review.md / step06b_semantic_lock_report.md | 历史阶段报告（质量策略定型）|
| step07a_validation_cell_preflight_report.md / step07b_validation_cells_report.md | 当前产品说明（strict_primary 的生成记录，manifest 回填依据）|
| step08_final_global_validation_report.md / publication_ready_step08_summary.md / model_ranking_uncertainty_report.md / step08_gapfill_error_structure_report.md | 当前产品说明（v1.0 冻结对外包，README 点名）|
| strict_primary_global_validation_report.md / strict_primary_global_validation_report_full_strict_primary.md / expanded_primary_global_validation_report.md / expanded_primary_global_validation_report_full_expanded_primary.md / strict_primary_full_validation_audit_report.md / stage4_expanded_primary_validation_audit_report.md | 历史阶段报告（Step 08 中间 run）|
| step08_preflight_report_full_strict_primary.md / step08_preflight_report_full_expanded_primary.md / step08_preflight_report_smoke.md / step08_smoke_validation_report_smoke.md / step08_non_primary_diagnostics_report_stage5_non_primary.md | 历史阶段报告（预检/smoke）|
| step09_sb_track_bias_report.md / step09_true_crossover_audit_report.md / step10_sb_network_bias_report.md / step10_sb_track_quality_report.md | 历史阶段报告（六区链 23/24/27/28）|
| step10_global_sb_final_product_report.md / step10_global_sb_products_report.md | 当前产品说明（25/26/30 产品）|
| step10_sb_interpolation_holdout_report.md | 当前产品说明（规范文档第 3 节证据源）|
| step10_screening_methods_survey.md / step11_archive_gap_report.md / step12_channel_inventory.md / step13_mbbdb_crosswalk.md / step14_next_step_decision_memo.md | 历史阶段报告（round-2 决策链）|
| step15_mb_round2_processing.md | 当前产品说明（round-2 三层集，待合并审查）|
| step16_mbbdb_value_ranking.md | 当前产品说明（下载排序表）|
| strict_primary_weighted_vs_unweighted_summary.tsv / product_completion_table.tsv / product_anomaly_summary.tsv | 当前产品说明（汇总表）|
| On the accuracy evaluation... .pdf | 外部文献（引用源）|

### docs/（7 项）

| 文件 | 状态 |
|---|---|
| 多波束船测数据处理流程.md | 当前产品说明（权威管线总览）|
| 数据产品规范与下游接入.md | 当前产品说明（规范）|
| 单波束数据质量处理与下游实验结论.md | 当前产品说明（研究结论）|
| experiments/2026-05_dataset-source-attribution.md | 历史阶段报告（改名证据链，仍被 README 引用）|
| experiments/2026-05_swot_t1_residual_baseline.md | 历史阶段报告（jamstec 09–11 结论）|
| experiments/2026-05_tmp-data-classification.md | 历史阶段报告 |

### jamstec/multibeam/docs/（19 项）

| 文件 | 状态 |
|---|---|
| README.md / PIPELINE_PROCESSING_GUIDE.md | 当前产品说明（重建指南）|
| point_schema_v1.md / model_validation_config_guide.md | 当前产品说明（schema/config）|
| cells_report_1min.md / cells_report_1min_qcfiltered.md / file_quality_flags_1min_report.md | 当前产品说明（主链产物报告）|
| cells_report_1min_sample.md / cells_report_1min_test100.md / file_cells_report_1min{,_sample,_test100}.md / qc_points_report{,_sample,_test100}.md / overlap_bias_report_1min_sample.md / format_audit_report{,_sample}.md / points_raw_manifest_curation_report.md | 历史阶段报告（sample/test100 run-label 运行记录）|
| bad_subzips_investigation_2026-05.md / subzip_cruise_normalization_2026-09.md | 历史阶段报告（数据勘误）|
| 航次清单_协作者审核.md | 当前产品说明（航次审核）|
| dat_manifest.tsv / bad_nested_zips.txt / bad_subzips.txt / sha256_remote.txt | 数据记录（清单，非文档）|

## 收集方法备注

行数/docstring/import 来自 AST 与逐文件扫描（`gather_inventory.py`）；文档引用数以 basename 在 338 个已跟踪 md/yaml/json 中计数（`gather_refs.py`）；product_manifest 判定以 7 个盘上 manifest 的命令字段为准；重复函数来自顶层 `def` 同名统计。三个收集脚本与中间 TSV 留在本目录，重排执行后可删。
