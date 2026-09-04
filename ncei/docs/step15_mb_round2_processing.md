# Step 15 — raw_round2 多波束航次处理（24 个已下载航次）

状态：完成（阶段 0–5 全部落地）。
日期：2026-09。
约束：全程不提交 git；中间产物只在 `ncei/derived/mb_round2/`；不改 README/规范/现有产品文件（含 `trackline_source_manifest.parquet`）；合并等用户审。

新脚本（`ncei/code/`，仓库根目录运行）：

| 脚本 | 阶段 | 作用 |
|---|---|---|
| `32_mb_round2_completeness.py` | 0 | 下载日志 + 盘上 .part 扫描 → 完整/不完整分类 |
| `33_mb_round2_format_survey.py` | 1 | 完整航次的文件格式普查 |
| `34_mb_round2_extract_points.py` | 2 | .mb58.gz → L1 点（16 列契约 + 质检 6 列，见 §4 说明） |
| `35_mb_round2_file_cells.py` | 3 | L1 → L2 1′ 格（23 列，逐航次） |
| `36_mb_round2_source_manifest_fragment.py` | 4 | L3 登记片段（26 列，独立 parquet） |
| `37_mb_round2_coverage_stats.py` | 5 | 与严格准入层对照的只读覆盖统计 |

## 1. 输入盘点

- 原始数据：`ncei/raw_round2/platforms_tree/` 24 个航次目录，共 140 GB。
- 下载日志：`ncei/manifests/round2_download_log.parquet`（6,968 行；platforms_tree 渠道 85 个 survey、6,717 行）。
- 规范：`docs/数据产品规范与下游接入.md` §1（三层齐全才允许更新交付产品；本任务只产三层与统计，不更新任何交付产品）。

## 2. 阶段 0：完整性审核

方法：下载日志 platforms_tree 渠道里每个 survey 的唯一文件 URL 集合（去掉目录列表 URL、剥掉与盘上一致的 `multibeam/data/version1/MB/` 前缀）= 应下集合；盘上文件集合 + `.part` 残留 = 实得；`.part` 仅在其目标完整文件缺失时计入不完整。清单位：`ncei/derived/mb_round2/completeness_manifest.parquet` / `.tsv`（脚本 `ncei/code/32_mb_round2_completeness.py`）。

结论：**14 完整 / 10 不完整**。

完整（14，含盘上字节数）：AR15（55 文件，3.4 GB）、AR23-02（434，22.3 GB）、AR30-01（169，7.9 GB）、AR40（5，0.18 GB）、AR41（88，10.4 GB）、AR42-02（137，13.0 GB；含 1 个陈旧 .part，目标完整文件已在盘，判完整）、AR59（10，0.24 GB）、AR9-03（7，0.49 GB）、CNTL01RR（15，0.14 GB）、CNTL02RR（9，0.23 GB）、EW9801（25，0.07 GB）、EW9905（13，0.05 GB）、FK006C（114，1.9 GB）、FK008（220，2.3 GB）。

不完整（10，只记录不处理）：

| 航次 | 盘/应 | 缺失 | 备注 |
|---|---|---|---|
| HLY1403 | 60/793 | 733 | 任务书未知的新发现，主体未下 |
| HLY1102 | 730/1301 | 571 | 同上 |
| AR66-B | 1/27 | 26 | 同上 |
| AR30-04 | 452/542 | 90（em122 缺 38、em710 整目录 52）+ 1 个 .part | 任务书已知 |
| AR66-A | 44/74 | 30（全部 em710） | 任务书已知 |
| AR45 | 24/42 | 18（em122） | 任务书已知 |
| HLY1401 | 89/90 | 1 + 1 个 .part（0090） | 任务书已知 |
| HLY1402 | 75/76 | 1 + 1 个 .part（0076） | 任务书已知 |
| HLY20TB | 210/211 | 1 + 1 个 .part（0211） | 任务书已知 |
| FK006B | 193/194 | 1（em710/0013） | 任务书未知的新发现 |

注：任务书已知清单里的“5 个 .part”中 AR42-02 经核实为陈旧残留（完整文件在盘），归入完整；其余 4 个 .part 均对应真实缺文件。

## 3. 阶段 1：格式普查

清单位：`ncei/derived/mb_round2/formats_manifest.parquet` / `.tsv`（脚本 `ncei/code/33_mb_round2_format_survey.py`），对象为阶段 0 的 14 个完整航次。

| 格式 | 文件数 | 字节 | 航次 |
|---|---:|---:|---|
| `.all.mb58.gz` | 1,239 | 61,990,878,527（61.99 GB，占 99.3%） | AR15, AR23-02, AR30-01, AR40, AR41, AR42-02, AR59, AR9-03, FK006C, FK008（10 个） |
| `.mb57.gz` | 24 | 374,019,093 | CNTL01RR（15）、CNTL02RR（9） |
| `.mb21.gz` | 25 | 74,187,099 | EW9801 |
| `.gz`（无格式后缀） | 13 | 54,680,595 | EW9905 |

处理决定（首轮）：非 mb58 格式合计 0.50 GB（占完整集字节 0.7%），占比小，按任务约定只登记不处理。**D1 增补（2026-09，用户授权）**：EW9801/EW9905 已按格式 21 处理并入（见 §9）；CNTL01RR/CNTL02RR 因固定环境 mb57 解析器系统性崩溃未处理（见 §9）。

## 4. 阶段 2：L1 点提取

- 提取链：固定版本 mbsystem 环境 `ncei/derived/scs_v2_sealed_confirmation/environments/mbsystem-5.8.3beta16-1d9a52ce/`（gzip 1.14 + mblist 5.8.3beta16，commit 1d9a52ce），命令行与 `ncei/code/scs_confirmation/process_scs_v2_stage_c_source_internal.py` 逐字一致：gunzip -dc → `mblist -I<file> -F58 -P1 -L0 -MA -U3 -OMN#XYzH -X<u3>` 与 `-U0` 同款；U3/U0 连接复用 `scs_v2_stage_c_processing._raw_from_object`（import，未复制）。逐文件命令台账（argv、返回码、stdout/stderr sha256）在各航次 `_work/<filekey>/command_ledger.jsonl`。
- L1 列数说明：规范 §1.1 正文写“17 列”，但其列表现有产品实列 16 列（已对 `ncei/derived/multibeam/points_raw/ra028-09__xyz.parquet` 核对）；本阶段按现有产品 16 列 + points_checked 质检 6 列落地，未自行加列。
- 处理对象：10 个完整 mb58 航次、1,239 个文件，10 进程并行耗时约 3.5 小时。

逐航次结果（`ncei/derived/mb_round2/<航次>/extraction_manifest.parquet` 与 `extraction_summary.json`）：

| 航次 | 文件 ok/总 | 点数 | pass_basic | depth_sign_raw | 点层体积 |
|---|---|---:|---:|---|---|
| AR15 | 55/55 | 33,097,392 | 33,097,384 | mostly_positive | 1.5 GB |
| AR23-02 | 428/434 | 110,124,480 | 110,124,467 | mostly_positive | 4.5 GB |
| AR30-01 | 167/169 | 24,035,600 | 24,035,577 | mostly_positive | 1.3 GB |
| AR40 | 5/5 | 1,575,600 | 1,575,600 | mostly_positive | 71 MB |
| AR41 | 87/88 | 123,397,072 | 123,397,072 | mostly_positive | 4.5 GB |
| AR42-02 | 136/137 | 78,263,920 | 78,263,147 | mostly_positive | 2.9 GB |
| AR59 | 10/10 | 570,240 | 569,679 | mostly_positive | 31 MB |
| AR9-03 | 7/7 | 7,320,672 | 7,320,672 | mostly_positive | 466 MB |
| FK006C | 113/114 | 34,625,920 | 34,625,920 | mostly_positive | 1.4 GB |
| FK008 | 220/220 | 49,617,728 | 49,617,728 | mostly_positive | 2.0 GB |
| 合计 | 1,228/1,239 | 462,628,624 | 462,627,246 | 全 mostly_positive | 19 GB（raw）+19 GB（checked）+17 GB（staging） |

- **11 个文件拒收**：全部是下载截断的损坏 gzip（`gzip -dc` rc=1 unexpected EOF，fail-closed，无半截数据入库）：AR23-02 六个、AR30-01 两个、AR41/AR42-02/FK006C 各一个（逐文件名见各航次 extraction_manifest）。这些航次在阶段 0 按“文件数”判完整，但实际内容缺这 11 个文件的数据；是否补下由用户决定。
- 深度符号：全部 10 航次实测 ≥95% 正值（mblist z 列即正向下），无负号/混号情形，sign_flip 均为 +1。
- **已知数据质量伪迹（未过滤、已披露）**：9/10 航次（AR59 无）存在文件首个 ping 在 GPS 锁定前停在 (0,0) 附近的导航值，共 65,792 点，产生逐航次 67 个、去重后 24 个近原点格子（见 §7）。仓库现有 QC（ncei 05 / jamstec 03）均为纯范围判定，拦不住这类伪迹；本任务未擅自新增过滤规则，伪迹格子计入 L2 但在 §7 单列，合并审查时需裁决。

## 5. 阶段 3：L2 格子

- 复用说明：任务书指定复用 jamstec `04a_make_multibeam_file_cells.py` 的逻辑。经核对，ncei 侧 `07_aggregate_file_cells_1min.py` 的 `aggregate_track_file()` 与 jamstec 04a 采用同一 cell_id 公式（07 文档串明确引用 04a），且直接产出规范 §1.2 的 23 列 multibeam_ncei 契约（04a 的跨 chunk 合并对中位数是加权近似，且产出 jamstec 自用 schema）。故本阶段 import 调用 `07.aggregate_track_file`，零复制；此对任务书的偏差请用户裁决。
- 逐航次 1′ 格（`ncei/derived/mb_round2/<航次>/file_cells_1min/<track_id>__mb58.parquet`，汇总清单 `ncei/derived/mb_round2/file_cells_manifest.parquet`）：

| track_id | n_cells | pass 点 | 去重三元组 | duplicate_ratio |
|---|---:|---:|---:|---:|
| ar15 | 139 | 33,097,384 | 33,097,336 | 0.000001 |
| ar23-02 | 26,720 | 110,124,467 | 110,124,284 | 0.000002 |
| ar30-01 | 10,294 | 24,035,577 | 24,034,230 | 0.000056 |
| ar40 | 14 | 1,575,600 | 1,575,600 | 0.000000 |
| ar41 | 834 | 123,397,072 | 123,397,072 | 0.000000 |
| ar42-02 | 7,650 | 78,263,147 | 78,258,452 | 0.000060 |
| ar59 | 178 | 569,679 | 566,208 | 0.006093 |
| ar9-03 | 93 | 7,320,672 | 7,320,672 | 0.000000 |
| fk006c | 1,782 | 34,625,920 | 34,624,244 | 0.000048 |
| fk008 | 3,297 | 49,617,728 | 49,617,659 | 0.000001 |

重复率均 <0.7%，与原始 swath 数据预期一致。

## 6. 阶段 4：L3 片段

- 产物：`ncei/derived/mb_round2/mb_round2_source_manifest_fragment.parquet` / `.tsv`（10 行 × 26 列，列序与 `trackline_source_manifest` 完全一致）。**未改现有 `trackline_source_manifest.parquet`**，合并待审。
- 新来源侧值（加值不改列，待合并审查确认）：`source_type='ncei_mb58'`、`source_completeness='mb58_only'`；`source_path` 指向航次目录（多文件源，非单文件，与现有语义略有出入，已在此声明）。
- 几何/深度逐航次值见 §4 表与片段文件；`has_time=True`、`has_gobs=has_faa=False`、`depth_sign_raw` 全部 mostly_positive。
- 分类：9/10 航次 `hard_mb_points` 判 multibeam；**ar59 例外**（569,679 点、bbox 18.8 万 km²、密度 3.0 → 分类器判 singlebeam/borderline_default_sb），但其源是 em122/em710 原始 swath，已在 `manual_override` 列写入 `multibeam; raw .all.mb58 swath source (stage-2 provenance)` 供 curator 裁决，未改分类器输出。

## 7. 阶段 5：覆盖统计（只读）

- 对照：`ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet`（2,398,774 格）；统计产物 `ncei/derived/mb_round2/coverage_vs_strict_primary.parquet`。
- 六海区定义（只读）：`/mnt/data2/06-Projects/15-swot_feature_physics_bathy/configs/feasibility/final_data_round.yaml`（lon068_lat018、lon052_lat018、lon058_lat012、lon059_lat015、lon004_lat033、lon021_lat010，各 5°×5°）。

| 口径 | 数量 |
|---|---:|
| 新航次 L2 格并集（全球） | 50,633 |
| 其中已在严格层（重合） | 19（重合率 0.0375%） |
| **严格层之外的新格（真实增量候选）** | **50,614** |
| 其中近原点导航伪迹格（|lon|、|lat|<1°） | 24（剔除后 50,590） |
| 六个下游海区内的任何口径新增 | 均为 0 |

- 新格地理范围：lon −86.3…0.04、lat −0.04…63.5（美国东海岸 + 北大西洋 + 墨西哥湾），与现有严格层几乎不重叠（严格层主体是 JAMSTEC 西太平洋），故重合率近零。**六海区全为 0**：本批 10 航次不落在任何 SWOT 下游海区内，对六区实验无直接增量；其价值在全球严格层扩容（约 +2.1%）。
- 另有非伪迹但与主覆盖不连通的小分量（如 fk008 在墨西哥湾与大西洋的两段），属真实分段的覆盖，不在伪迹口径内，未单独剔除。

## 8. 遗留与风险

1. **11 个截断 gzip 文件**（§4）：下载不完整导致，fail-closed 拒收。补下与否待用户决定；补下后重跑 `34 --cruises <对应航次>` 会自动增量处理。
2. **近原点导航伪迹**（§4/§7）：24 个去重伪迹格已在 L1/L2 落盘，统计层已单列。合并审查时建议裁决：要么接受范围 QC 契约现状（合并后作废 24 格），要么在下轮 QC 契约中新增导航锁定检验。
3. **ar59 分类分歧**（§6）：待 curator 确认 manual_override。
4. **非 mb58 完整航次（D1 增补后）**：EW9801、EW9905 已按格式 21 处理并并入三层与覆盖统计（§9）；**CNTL01RR/CNTL02RR（mb57，24 文件）未处理**：固定版环境的 mblist/mbinfo 对 -F57 全部文件（含预检的 3 个样本）以 `double free or corruption` 中止（rc=-6/SIGABRT），按约束不自行编译安装，逐文件失败已记入两航次 extraction_manifest 与命令台账，半截输出未入库。换环境版本或补丁后重跑 `34 --cruises CNTL01RR CNTL02RR` 即可增量补入。
5. **不完整航次 10 个**（§2）：含任务书未知的 HLY1403（缺 733 文件）、HLY1102（缺 571）、AR66-B（缺 26）、FK006B（缺 1），对下一张订单的优先级排序有直接影响。
6. 规范 §1.1 “17 列”与实际产品 16 列的出入建议在规范任务中修正。
7. 本任务未更新任何交付产品（三层片段均独立存放，合并待审），未碰 outer evaluation，未提交 git。

## 9. D1 增补：非 mb58 航次处理（2026-09 第二轮，用户授权）

- **格式判定**：EW9801 的 25 个 `.mb21.gz` 直接用 -F21；**EW9905 的 13 个无后缀 .gz 判定为格式 21**，依据：解压体与 EW9801 文件同构（首行 ASCII 头 `ERGNMESS`，Hydrosweep DS raw），且 `mbinfo -F21` 干净解析（MBF_HSATLRAW，59 beams）。探测逻辑固化在 34 脚本 `resolve_mb_format()`（后缀优先；无后缀时只认 ERGNMESS 签名，其余记 `skipped_format_unknown`，不猜）。
- **mb57 崩溃**：CNTL01RR/CNTL02RR 共 24 个 `.mb57.gz`，mblist/mbinfo `-F57` 全部 `double free or corruption` 中止（预检 3 个样本 + 管线内全部 24 文件均复现），fail-closed 未入库，待环境修复后重跑。
- **34 脚本泛化**：文件清单改为全部非 .part 的 `*.gz`，逐文件解析格式，`-F<fmt>` 进命令台账；L1/L2/L3 分片命名 `<track>__mb<fmt>.parquet`，source_type/source_completeness 新增 `ncei_mb21` / `mb21_only` 取值（与 §6 同样为加值不改列，合并待审）。
- 逐航次结果（与 §4/§5 同口径）：

| 航次 | 格式 | 文件 | 点数 | pass_basic | 格子 | duplicate_ratio |
|---|---|---|---:|---:|---:|---:|
| EW9801 | 21 | 25/25 | 8,509,688 | 7,540,053 | 10,422 | 0.0808 |
| EW9905 | 21 | 13/13 | 5,004,557 | 4,832,221 | 3,238 | 0.0001 |

 EW9801 的 8% 重复三元组来自相邻 .dNNN 分段文件的 ping 重叠（无重名/同字节的重复文件），符合分段原始数据预期。两航次 depth_sign_raw 均 mostly_positive；L3 分类均 hard_mb_points 判 multibeam。
- **覆盖统计重算**（37 重跑全部 12 个已处理航次）：并集 50,633 → **64,293** 格；与严格层重合 19 → **1,305**（重合率 2.03%，增量主要来自 EW 两航次与现有 Ewing 源数据的重叠）；严格层外新增 50,614 → **62,988**；近原点伪迹格不变 24；六海区仍全为 0。
- 磁盘增量：EW 两航次三层约 0.9 GB；cntl 两航次仅留命令台账与失败清单。

## 10. D3 文档改动清单（2026-09 第二轮）

本轮（D1+D3）除上述 §9 的数据产物外，按"文档与盘上事实一致"改了以下文件（均未提交 git）：

1. `README.md` — 新增 "Round-2 products (2026-09)" 一节（global_grid_1min_r2、mb_round2 三层与待审 L3 片段、mbbdb_value_ranking、raw_round2 四类来源）；"Adding new ship data" 补 raw_round2 来源走 32–37 号脚本的入库路径与"片段合并审查后才进生产"的门槛。
2. `docs/数据产品规范与下游接入.md` — §1.1 "17 列"勘误为 16 列（附核对出处）；`source_type` 行登记 round-2 提案值 `ncei_mb58`/`ncei_mb21`；§1.3 稳定契约注登记 `source_completeness` 提案值 `mb58_only`/`mb21_only` 与片段路径。
3. `jamstec/SOURCE.md` — 649 航次改写：原文 "the first source-zip enumerates 255 unique JAMSTEC cruise IDs" 更正为全量 649，并注明 255 实为第一包的 KR 前缀子集计数（指向 `multibeam/docs/subzip_cruise_normalization_2026-09.md`）。任务书写的是 ncei/SOURCE.md，但 255 错误实际在 jamstec/SOURCE.md，按错误所在文件改。
4. `ncei/SOURCE.md` — 新增 "Round-2 raw downloads (raw_round2/, 2026-09)" 一节（platforms_tree 2085 代理直下、R2R、静态 MGD77T 树三条来源链与日期）；Layout map 补 raw_round2/ 与 derived/ 现状。
5. `ncei/code/README.md` — 脚本索引补 25–31（全球单波束生产链与 r2 网格）与 32–38（round-2 吞吐与价值排序）的用途与依赖。
6. `ncei/docs/step11_archive_gap_report.md` — 文末新增 "Round-2 follow-up pointer"：指向本报告与 step16，并注明静态 MGD77T 回填（369 目录/362 .m77t/8.0 GB，进行中）与平台树补全、损坏 gzip 重下仍在队列，该节 2026-09-03 快照数字待 luna 收尾后由下一轮更新。

未改动：`docs/多波束船测数据处理流程.md`、各 `tracklines_*/SOURCE.md`、任何生产产品文件。

## 11. D2 增补：luna 补全后的增量处理（2026-09 第三轮）

### 11.1 完整性审核升级与结果

luna 补全后重跑 32。本轮发现**下载日志的 URL 枚举本身被截断**（HLY1401 上游 em122 目录实有 1,919 个文件、日志只枚举到 90 个），日志口径不再可信；32 脚本新增 `--live-expected` 模式：经 2085 拉取各航次平台树目录页（仅元数据，缓存于 `ncei/derived/mb_round2/dir_listings/`），以活目录为应下集合分类。

- 结论：**21/26 完整**（含 luna 直下的 AT42-11、HLY06TB 两个新航次；两者曾是错误 HTML 页面占用目录名，luna 已移出至 /tmp/round2_bad_pages/，真实数据目录完好）。
- 新变完整（7 个，本轮处理对象）：AR30-04（542 文件）、AR45（42）、AR66-A（74）、AR66-B（27）、FK006B（194）、HLY1102（1,301，其中 54 个 .mb56 已知不支持、跳过并记录）、HLY1403（793）。
- 仍不完整（3 个，缺口远大于日志口径）：HLY1401（上游 1,919 / 盘 90，缺 1,829）、HLY1402（1,105 / 76，缺 1,029）、HLY20TB（219 / 211，缺 8，其中含上游垃圾文件名如 `9999.all.mb58.gz`、`ServiceModel.mof.uninstall.mb58.gz`）。
- AT42-11：不完整（24 文件 + 1 活 .part）；HLY06TB：58 个 .mb41.gz（SeaBeam，已知不支持格式），expected 未知——两者均不处理、只登记。
- luna 重下的 8 个损坏 gzip 已核实修复（gzip -t 通过）；另有 3 个仍未修复：AR42-02/em710/0028、AR41/em710/0004、FK006C/em302/0049。
- EW9905 勘误：首轮 §9 表写"13/13"，实际当时 4 个文件（d127/d128/d137/d138）因截断被记 `skipped_format_unknown`，仅 9/13 入库；本轮重下修复后已重提全 13 个。

### 11.2 增量提取与三层结果

（提取后台进行中，完成后填写：新航次逐行表、覆盖统计重算）
