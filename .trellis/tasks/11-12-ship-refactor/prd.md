# Ship 仓库重构：模块化处理代码

## 目标

读者打开仓库，每条数据线（下载、NCEI 单波束/MGD77T、NCEI 多波束、JAMSTEC 多波束）只有一个包、一个入口和一份说明。一次性审计、已完成个案和逐轮修订脚本不再作为并列命令留在工作树里。保留代码按调用边界分模块，函数单一职责，英文注释与 docstring，科学概念用领域术语。

上一轮（`10-21-repo-reorganization`）已把脚本改成 `ncei.download`、`ncei.trackline`、`ncei.swath` 三个包。之后的修订按"新增一个模块/命令"叠加（`quality_revision`、`navigation_revision`、`navigation_review`、`mgd77t_*`、`legacy_faa_revision`、`source_corrections` 等），本任务把叠加的版本合并为一条现行链路。

## 已定决策（主代理）

- 用户 2026-11-12：多波束全量重建采用逐文件流式处理，只保留 L2、计数、清单与覆盖表，L1 按需重提；在 data2 完成。
- 重构不改变现行产品的数值：每条链路在小输入上与现行产品逐表对照，差异为零才算完成。
- 被取代的已跟踪代码从工作树删除，记入 `docs/code_archive.md`（用途、产出的产品或报告、最后包含它的提交）。产出过已报告数字的代码，其结果记录须指向含该代码的提交。
- 子代理只执行主代理写定的规格。规格未覆盖的设计选择回报主代理，由主代理决定。
- 下载链（`ncei/code/41_tier_a_gapfill.py`、`ncei/download/`、台账、`/mnt/data1/pub/ship/ncei/_work/`）由下载负责人独占，重构代理不改。

## 分工

| 负责人 | 范围 | 状态 |
| --- | --- | --- |
| S（codex gpt-6.1-sol） | `ncei/swath/`、`_common/mbsystem.py`：流式链路与全量重建，见子任务 `11-12-swath-streaming-rebuild` | 进行中 |
| K（pi k3.1-pro） | 只读设计清单：`ncei/trackline/`、`jamstec/`、`_common/`、`*/analysis/`、`docs/`、根 README | 进行中 |
| D（pi k3.1-pro） | 下载收尾与零估计池追加下载，见 `10-30-ncei-mb-tier-c-download` | 进行中 |
| 主代理 | 布局决策、验收、Trellis 记录、提交 | |

K 的清单完成后，主代理定布局，再派实现：trackline 交 gpt-6.1-sol，jamstec/analysis 归档与文档交 k3.1-pro。

## 完成核对

- 每个包一个入口，`--help` 不触发处理；README 写现行命令、输入、输出与读取方式。
- 每条链路的新旧对照记录（输入、命令、逐表差异）。
- `docs/code_archive.md` 覆盖全部删除文件。
- `python -m unittest discover _common/tests` 通过。

## 状态

- 2026-11-12：10-25 修订代码已提交推送（`61eea2f`、`0aaf7c9`、`1900142`）。任务创建；paseo 工作区 wks_2e2040b3fe9c7d48，S = ef6b00e2（codex gpt-6.1-sol，full-access），K = 263650cb（pi k3.1-pro），D = 71b7c2ef（pi k3.1-pro）。

## 布局决策（主代理 2026-11-12，依据 `research/layout_inventory.md`）

清单的现行链路、对照输入与重复函数表采纳为实施依据。逐项决定：

1. 冻结分析全部归档删除：`ncei/analysis/` 全部 12 个（含 `seamount_candidate_delivery.py`，交付已完成，结果记录与提交 `222e9b1` 可复原；RR0913 若引出新交付，用新 `ncei.swath points` 与 L2 另建），`jamstec/multibeam/analysis/` 的 08、09×2、10、10b、11、`plot_multibeam_figures.py`。`06d` 是 `07` 的生产输入，移回 JAMSTEC 生产模块。报告、配置、图与清单保留。
2. 质量政策：批准规则 `quality_policy_enforced_rules.tsv` 从归档任务目录复制到 `ncei/trackline/config/`，代码改读该路径，修复现失效路径；冻结校准表留在 `ncei/derived/quality_policy_calibration_1min/`，作为显式输入路径。`policy_audit.py` 探索驱动归档；`source_overlap`、`branch_overlap` 的计算并入 `quality_overlap.py`，与 `apply_policy` 组成一个 `quality-policy` 命令，写出与现行相同的中间表；`validation-cells` 保持独立命令。
3. `source_corrections.py` 留在 `ncei.trackline`，一个入口，不复制。
4. FAA：保留单源转换与显式清单批处理（含旧 NetCDF 对齐与 `--verify-only`），最初 15 航次专用审计驱动归档。
5. EW0202（`11-swot-ssl-encoder/scripts/process_ew0202_v1.py`）：其任务已归档，结果记录以 Ship 提交 `222e9b1` 加补丁复算，不在现行使用中。不保留兼容壳；`docs/code_archive.md` 记明它用过的 `extract.process_one_file`、`extract.merge_cruise`、`raw_from_object` 与最后包含它们的提交，今后该仓库处理多波束改用 `python -m ncei.swath run/points`。`ncei.trackline.file_cells.aggregate_track_file` 公共接口保持。
6. `consumers.yaml` 在文档阶段补登 11、13、14 的产品读取（清单第五节事实）。
7. 归档索引：S 已直接写 `docs/code_archive.md`；其余负责人把条目写到 `research/archive_entries_<负责人>.md`，主代理合并。最后包含提交写删除提交的父提交。
8. 全量多波束重建从固定提交的独立 git worktree 运行，使 trackline 重构不影响运行中的 worker。

## 实施分工

| 负责人 | 范围 |
| --- | --- |
| S（codex gpt-6.1-sol，ef6b00e2） | `ncei/swath/` 流式链路；删除仅服务海山交付的 `ncei.swath.delivery` |
| T（codex gpt-6.1-sol） | `ncei/trackline/` 按清单目标布局与第 2-4 项 |
| K（pi k3.1-pro，263650cb） | `jamstec/multibeam/` 包化（`python -m jamstec.multibeam`），JAMSTEC analysis 归档，06d 移回 |
| D（pi k3.1-pro，71b7c2ef） | 下载之外：`ncei/analysis/` 归档、`_common/` 的 `r2_calibration.py`、仅为其存在的 `io_helpers.py`、`calibration/`、`tests/fixtures/` 归档，`_common/README.md` |
| 文档阶段（K） | 根 README、AGENTS.md、`docs/` 概览、`consumers.yaml`，在各包完成后 |

## 状态（续）

- 2026-11-12：K 清单完成（`research/layout_inventory.*`，168 文件），主代理定布局。T 派出为 fe57f48d（codex gpt-6.1-sol，full-access）；K 接 JAMSTEC 包化；D 在下载期间接 `ncei/analysis/` 与 `_common` 归档；S 被告知删除 `ncei.swath.delivery`、EW0202 归档说明、全量运行用绝对路径参数。
- 2026-11-12：D 归档完成（24 个文件，`io_helpers.py` 因 r2_classifier 测试仍用而保留），条目并入 `docs/code_archive.md`；提交 `f1f82a4`（swath）与 `7489d72`（归档与下载器参数），未推送。T、K 进行中。
- 2026-11-12：S 最小修订提交 `80965c7`（续跑不比较航次集合、记录敏感性表、空历史清单按原文件发现），全量从该提交的 worktree 启动。T 完成 trackline，19 命令对照见 `research/trackline_refactor_check.md`，提交 `13fc476`，条目并入 `docs/code_archive.md`。主代理决定：区域与全球叶 tile 发布交叉点表（1,276 / 2,495）保留原版本；`1900142` 与重构代码同输入均为 1,277 / 2,496 且逐列一致，作为等价证据，不改写产品。K 的 JAMSTEC 进行中（`test_jamstec_pipeline` 的 KY09-09 用例待 K 修）。
