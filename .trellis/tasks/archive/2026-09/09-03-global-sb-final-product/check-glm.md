# 验收核验报告：09-03-global-sb-final-product 与 09-03-data-product-spec

核验人：GLM（验收 reviewer）
时间：2026-09-03
解释器：`/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python`，repo root 执行。
方法：全部按 PRD 验收标准逐条机械核验，证据为当场计算结果，非任务自述。

## 任务 09-03-global-sb-final-product

### 1. track_quality.parquet 存在、逐航线一行、与清单对账、必备列 — PASS

- `ncei/derived/sb_track_quality_global/track_quality.parquet` 存在，5533 行，`track_id` 无重复（nunique = 5533）。
- 与航线清单对账：清单 `ncei/manifests/trackline_source_manifest.parquet` 7400 行中 `instrument_class_pred == 'singlebeam'` 共 7383 行（ncei_xyz 5365 + ncei_nc 2018），同一航线的 nc/xyz 两侧在全局表中合并（`source_completeness`：xyz_only 3515、nc_xyz_intersect 1850、nc_only 168）。5365 + 2018 − 1850 = 5533，与表行数一致；表中全部 5533 个 track_id 都能在清单中找到（0 个缺失）。
- 必备列全部在 30 列中：偏差（`bias_m`、`nmad_m`、`applied`）、misfit 前后（`crossover_raw_median_abs_diff_m` / `crossover_post_median_abs_diff_m`）、`n_crossovers`、QC 标志（`hard_qc_backward_time`、`hard_qc_zero_cells`）、`disposition`、`reason`、阈值（`misfit_threshold_m`）。
- 处置计数：keep_raw 4764、reject 711、correct 32、revert_to_raw 23、flag_large_unapplied_bias 3，合计 5533。
- `n_cells` 总和 17,294,849，等于最终产品总行数（见第 2 条）。product_manifest.json 的 counts 与以上数字一致。

### 2. file_cells_1min_final_r2：行数不丢、track_disposition 列、bias 平移抽查、reject 抽查 — PASS

- 文件集与 `file_cells_1min_adjusted/` 完全一致（5365 个同名文件），逐文件行数比较 0 处不一致。
- 列 = adjusted 全部列 + `track_disposition`，无缺失列。
- bias 应用抽查（2 条）：adjusted 层已含 step23 校正；final 层对 revert / flag 轨道按脚本 30 的规则做 `median_depth_m + track_bias_m`（即撤销 −bias 的校正、回到 raw）。
  - `80041402`（revert_to_raw，track_bias_m = −274.100，adjusted 中 bias_applied=True）：final − adjusted 恒等于 +274.100（3093 行，最大偏差 < 1e−6）。
  - `elt18`（flag_large_unapplied_bias，track_bias_m = −1247.200，bias_applied=True）：final − adjusted 恒等于 +1247.200（4269 行）。
  - 对照 `odp130jr`（revert_to_raw 但 adjusted 中 bias_applied=False）：不平移（本就是 raw），行为正确。
- reject 抽查（1 条）：`69005621`（reject，2776 行）在 final_r2 中行数与 adjusted 相同、`track_disposition` 全为 `reject`、数值未改动（仅标记）。

### 3. 六区 controls_mb_sb_final_<tile>：MB 行一致、SB 行 = 最终产品非 reject、control_source — PASS

六个 tile 全查（lon004_lat033、lon021_lat010、lon052_lat018、lon058_lat012、lon059_lat015、lon068_lat018）：

- MB 行（`control_source == 'strict_multibeam'`）与 `controls_mb_only_<tile>.parquet` 在 `cell_id` 与 `control_depth_m` 上逐行一致（行数相同、排序后完全相等）。
- SB 行（`control_source == 'singlebeam_final'`）的 `control_depth_m` 等于全局最终产品中该 cell 全部非 reject 航线 `median_depth_m` 的中位数（六个 tile 全部 allclose）。
- cell 集合双向核对：以 `controls_mb_sb_adjusted_<tile>` 的 SB cell 全集为 tile 内宇宙，final 控制表的 SB cell 集合恰等于其中仍有非 reject 贡献的 cell 集合（六个 tile 全部相等；被剔除的差额即全部贡献航线均 reject 的 cell）。

### 4. 命名轨道与六区 hard-QC reject 保持 — PASS

- `odp130jr` → `revert_to_raw`（reason = six_region_named_disposition_retained）。
- `elt18`、`elt19` → `flag_large_unapplied_bias`（同上 reason）。
- 六区表共 28 条 reject，其中 hard-QC reject（backward_time / zero_cells）10 条（dme10、ew0113、rc0909、rc2707、v2009、va16、76010303、87001511、kh6705、v1907），在全局表中 10/10 保持 `reject`。
- 其余 18 条为 misfit reject，其中 14 条在全局表变为 keep_raw/revert_to_raw（reason 均为 no_application_or_insufficient_evidence 或 applied_but_post_worse_than_raw）。这属于 PRD 允许的 NMAD 尺度变化差异，且 `sb_track_quality_global/six_region_validation.parquet`（247 行，含 regional/global 两侧 disposition、misfit、阈值）逐条列出了差异。验收条款只要求 hard-QC 保持，故判 PASS。

### 5. README.md — PASS

- `.trellis/spec/backend/` 死链已消除：现链接为 `.trellis/spec/README.md`、`.trellis/spec/data/index.md`、`.trellis/spec/shared/reproducibility.md`，三个目标文件都存在。
- 产品清单："Current singlebeam products" 表列出全部五个产品路径与一句话用法，并给出过滤规则（`track_disposition != 'reject'`）。
- 入库章节：新数据放置、`(track_id, source_type)` 对清单判新、重跑顺序 01 → 02–06 → 07–08 → 25 → 26 → 30。
- 轮次约定："## Product rounds" 一节（目录轮次后缀、manifest 记生成时间与输入清单 SHA-256、新轮不覆盖旧轮）。
- scs_confirmation 说明：正文（scripts 归档于 `ncei/code/scs_confirmation/`、非活跃管线）与 repo layout 两处均有。

### 6. docs/单波束数据质量处理与下游实验结论.md 第 4–6 节 — PASS

- 第 4 节产品表新增全球处置表、最终单波束格子（r2）、六区最终控制表三行；下游两层使用规则成句给出（"有严格多波束格子的地方使用严格多波束；其他位置读取 file_cells_1min_final_r2/，并过滤 track_disposition != 'reject'"）。
- 插值结论 1,841 → 731 → 673 米写入第 4 节问答与第 5 节，且明确 673 是旧六区控制表口径、不是 r2 的验证结果。
- 第 6 节小问题清单按 r2 事实更新（时间倒退/无格子航线入 reject、elt18/19 维持 flag、nc+xyz 同航线不重复计）。

### 7. 只读约束 — PASS

- `git status --porcelain`：tracked 修改仅 `README.md`、`docs/单波束数据质量处理与下游实验结论.md`、`.trellis/tasks/09-03-global-sb-final-product/task.json`，均在任务声明范围内；其余均为新增未跟踪文件（本任务产物 + 其他任务目录）。
- mtime 抽查：`ncei/manifests/trackline_source_manifest.parquet` = 2026-05-20；`ncei/derived/validation_cells_1min/`（5 个文件）全部 2026-05-22；六区旧产物 `controls_mb_only_*` = 2026-09-02、`sb_track_quality_1min/*` = 2026-09-03 04:10。本任务产物写入时间为 2026-09-03 05:11–05:13，晚于以上全部旧产物，未被触碰。
- 说明（非 FAIL）：工作区另有未跟踪的 `.trellis/tasks/09-03-ncei-archive-gap-inventory/` 与 `ncei/docs/step11_archive_report.md`，来自并行的第三个任务，不属于本两任务，也未修改任何 tracked 文件。

## 任务 09-03-data-product-spec

### 1. docs/数据产品规范与下游接入.md 列清单抽查（5 项）— FAIL（2 处计数标签错，列名全部正确）

抽查 5 项列清单声明，对照磁盘 parquet schema（pyarrow）：

| # | 声明 | 磁盘实测 | 判定 |
|---|---|---|---|
| 1 | `points_raw` 17 列，列名如文中所列 | nc / xyz / multibeam 三分支 schema 完全一致，17 列，列名逐一相等 | PASS |
| 2 | `points_checked` 追加"7 列" | 实际追加 6 列：valid_lon、valid_lat、valid_depth_pos、valid_depth_max、valid_core_fields、point_check_pass_basic（抽样 5 文件 schema 唯一）。文档列出的 6 个列名本身与磁盘一致，仅"7 列"计数错 | FAIL（计数） |
| 3 | L2 基础列"22 列"，表中共列 23 个列名 | `file_cells_1min/` 实际 23 列（单波束、多波束分支一致），列名与文档表逐一相等。仅"22 列"计数错 | FAIL（计数） |
| 4 | adjusted 追加 3 列、final_r2 再追加 1 列 | adjusted 额外列恰为 track_bias_m、bias_applied、bias_n_support；final_r2 额外列恰为 track_disposition；基础列是前者的前缀 | PASS |
| 5 | L3 清单 26 列、五组划分如文 | 磁盘 26 列，顺序与列名逐一相等 | PASS |

两处 FAIL 均为计数标签差一（6 写成 7、23 写成 22），所列列名与磁盘完全一致。该文档自我定位为规范性文档（"每个路径和列名都已对照实际文件核对"），计数应修正。

另核验非抽查项：文件数声明全部正确（points_raw 7215 = 1850 nc + 5365 xyz；points_checked 5365；multibeam 17；最终层 5365）；`strict_primary_multibeam_cells.parquet` 2,398,774 行属实。

### 2. consumers.yaml — PASS

仓库根存在；头部注释给出六个字段的逐条说明与"登记是约定而非强制"的声明；含一条完整注释掉的示例条目（15-swot_feature_physics_bathy 占位）；正文 `consumers: []`。

### 3. 未落盘产品的标注 — PASS

- `ncei/derived/global_grid_1min_r2/` 确实不在盘上，文档第 2 节明确标注"尚未生成，由后续任务按此规格产出"。
- 最终层 `file_cells_1min_final_r2/`（现已落盘）在文档中标注为任务 09-03-global-sb-final-product 产出，且处置规则处引用了 `.trellis/tasks/09-03-global-sb-final-product/prd.md` 固定 schema（`track_disposition`、轮次标签 `_r2`）。
- 文中其余引用路径逐个存在：tracklines_nc/xyz 及 SOURCE.md、manifest TSV 镜像、schema 文档、step10 插值报告、sb_track_bias_global/product_manifest.json 等。

### 4. README.md 未被本任务修改 — PASS

`git diff README.md`（+62 行新增文本）内容全部属于任务 1 的交付（产品清单、入库流程、Product rounds、scs_confirmation、链接修复），不含任何 consumers.yaml / 数据产品规范 / 下游接入 相关内容（grep 零命中）。两个任务共享一个工作树，无法从 git 进一步区分作者，此判定基于内容归属。

## 结论

- 09-03-global-sb-final-product：7/7 PASS。
- 09-03-data-product-spec：3/4 PASS，1 FAIL——规范文档两处列数标签（points_checked "7 列"应为 6，L2 基础列 "22 列"应为 23）；所列列名与磁盘全部一致，属文字修正级别，不涉及 schema 或数据。
