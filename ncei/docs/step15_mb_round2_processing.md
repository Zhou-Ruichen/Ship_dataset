# Step 15 — raw_round2 多波束航次处理（24 个已下载航次）

状态：完成（阶段 0–5 全部落地）。
日期：2026-09。
约束：全程不提交 git；中间产物只在 `ncei/derived/mb_round2/`；不改 README/规范/现有产品文件（含 `trackline_source_manifest.parquet`）；合并等用户审。

处理入口（2026-10-21 迁至 `ncei/swath/`，仓库根目录用
`python -m ncei.swath <command>` 运行；32 号留在原位）：

| 脚本 | 阶段 | 作用 |
|---|---|---|
| `ncei/code/32_mb_round2_completeness.py` | 0 | 下载日志 + 盘上 .part 扫描 → 完整/不完整分类 |
| `ncei/swath/census.py` | 1 | 完整航次的文件格式普查 |
| `ncei/swath/extract.py` | 2 | .mb58.gz → L1 点（16 列契约 + 质检 6 列，见 §4 说明） |
| `ncei/swath/file_cells.py` | 3 | L1 → L2 1′ 格（23 列，逐航次） |
| `ncei/swath/manifest_fragment.py` | 4 | L3 登记片段（26 列，独立 parquet） |
| `ncei/swath/coverage.py` | 5 | 与严格准入层对照的只读覆盖统计 |

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

清单位：`ncei/derived/mb_round2/formats_manifest.parquet` / `.tsv`（脚本 `ncei/swath/census.py`），对象为阶段 0 的 14 个完整航次。

| 格式 | 文件数 | 字节 | 航次 |
|---|---:|---:|---|
| `.all.mb58.gz` | 1,239 | 61,990,878,527（61.99 GB，占 99.3%） | AR15, AR23-02, AR30-01, AR40, AR41, AR42-02, AR59, AR9-03, FK006C, FK008（10 个） |
| `.mb57.gz` | 24 | 374,019,093 | CNTL01RR（15）、CNTL02RR（9） |
| `.mb21.gz` | 25 | 74,187,099 | EW9801 |
| `.gz`（无格式后缀） | 13 | 54,680,595 | EW9905 |

处理决定（首轮）：非 mb58 格式合计 0.50 GB（占完整集字节 0.7%），占比小，按任务约定只登记不处理。**D1 增补（2026-09，用户授权）**：EW9801/EW9905 已按格式 21 处理并入（见 §9）；CNTL01RR/CNTL02RR 因固定环境 mb57 解析器系统性崩溃未处理（见 §9）。

## 4. 阶段 2：L1 点提取

- 提取链：固定版本 mbsystem 环境 `ncei/derived/scs_v2_sealed_confirmation/environments/mbsystem-5.8.3beta16-1d9a52ce/`（gzip 1.14 + mblist 5.8.3beta16，commit 1d9a52ce）：gunzip -dc → `mblist -I<file> -F58 -P1 -L0 -MA -U3/-U0 -OMN#XYzH -X<u3/u0>`；U3/U0 连接用 `_common/mbsystem.py` 的 `raw_from_object`（从已归档的 SCS Stage C 处理模块抽出，命令行语义与封存链逐字一致，见 `docs/code_archive.md`）。逐文件命令台账（argv、返回码、stdout/stderr sha256）在各航次 `_work/<filekey>/command_ledger.jsonl`。
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

- 复用说明：任务书指定复用 jamstec `04a_make_multibeam_file_cells.py` 的逻辑。经核对，ncei 侧 `ncei/trackline/file_cells.py` 的 `aggregate_track_file()` 与 jamstec 04a 采用同一 cell_id 公式（07 文档串明确引用 04a），且直接产出规范 §1.2 的 23 列 multibeam_ncei 契约（04a 的跨 chunk 合并对中位数是加权近似，且产出 jamstec 自用 schema）。故本阶段 import 调用 `ncei.trackline.file_cells.aggregate_track_file`，零复制；此对任务书的偏差请用户裁决。
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

提取于 2026-09-05 完成（34 号重跑，断点续跑）：新变完整 7 航次全部入库；luna 修复的 12 个截断文件重提并入（AR23-02 点数 110.12M→110.80M、AR30-01 +216k、EW9905 4 个文件从 9/13 补到 13/13）；仍未修复的 3 个截断文件（AR42-02/em710/0028、AR41/em710/0004、FK006C/em302/0049）继续拒收。CNTL 两航次 mb57 仍全量崩溃，维持不处理。

逐航次 L2（19 航次；全量 3.63G 点 / 285,542 航次格）：

| track | n_cells | pass 点 | dup |
|---|---:|---:|---:|
| ar30-04 | 9,959 | 83,089,113 | 0.0003 |
| ar45 | 3,357 | 15,516,144 | 0.0011 |
| ar66-a | 482 | 311,094,000 | ~0 |
| ar66-b | 234 | 157,840,000 | ~0 |
| fk006b | 1,198 | 84,481,872 | ~0 |
| hly1102 | 193,593 | 649,526,711 | 0.0029 |
| hly1403 | 11,581 | 1,851,889,392 | 0.0829 |
| （其余 12 航次同 §4/§5/§9 表，另 3 航次数有小幅上修） |

HLY1102/AR66-A/AR66-B 点密度极高（em122 深水扇形扫描），L3 分类均 hard_mb_points；HLY1403 重复率 8.3%（分段文件 ping 重叠，同 EW9802 型）。

**覆盖统计重算（37，19 航次）**：并集 64,293 → **284,720** 格；与严格层重合 1,305 → 5,941（2.09%）；严格层外新增 **278,779**（约为严格层基线的 +11.6%）；近原点伪迹格 24 → 32（新增 HLY1102/HLY1403 各几格，GPS 锁定前同型伪迹）；**六海区首次出现格级覆盖**：lon004_lat033（北极 -160..-155°E/75-80°N）1,565 格、净新增 1,248，来自 HLY1403，其余五区仍为 0。

## 12. 首批海山研究航次的质量修订（2026-10-21）

本节对应 2026-10-19 首批下载中已完成提取的 13 个航次。修订结果写入
`ncei/derived/mb_round2/_runs/20261021_quality_revision/`，不改原始下载、原 staging、
既有 L1/L2 或生产主数据集。NT06-21 保持“当前解析链未处理”，UTC 不完整的状态不表示零观测覆盖。

当前入口从仓库根目录运行：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python -m ncei.swath quality-revision --workers 4
```

`--resume` 复用该入口已完成的隔离 L1/L2，继续统计。旧目录
`_runs/20261020T_l2_l3_first_batch/` 中的 `run_l2_l3.py`、`finish_l2_l3.py`
及 `_runs/20261020T_source_audit/source_audit_corrected.py` 仅保留为旧结果的复现记录；
新结果不再调用这些脚本。

选点规则为 `point_check_pass_basic & (native_quality_state == "good")`。
基础检查仍表示有限经纬度、合法坐标范围与 `0 < depth_m_positive_down <= 11500 m`，
不包含原生质量判定。34 号脚本从现有 staging 重建 L1，在原有列之外保留
`native_quality_state`、`filekey`、`file_ordinal`、`point_index_in_file`、`staging_row`。
`staging_row` 是对应 staging parquet 中从 0 开始的行位置。通过 `filekey` 连接提取清单，
清单中的 `source_relpath` 相对于 `ncei/raw_round2/platforms_tree/`；
来源片段中的 `source_path` 相对于 `ncei/`。36 号脚本按磁盘实际文件解析船名/航次层级和直接航次层级，
保留历史 `relpath` 与 `filekey`，核对来源文件存在。

07 号聚合器通过 `selection_policy="basic_native_good"` 显式采用新规则，
内存与分批读取使用相同掩码。默认 `selection_policy="basic"` 保留单波束与 xyz 链的原有语义。
缺少原生质量字段时，新规则报出缺失列，不将旧记录标成 good。
提取汇总、逐文件清单和 `run_status` 分别报告总点数、基础检查通过数、good/flagged/null/unknown
数量、最终选入数及 L2 点数；`skipped_exists` 的计数从 staging 恢复。

`--diagnosis-records` 读取诊断清单，填写逐文件/航次的已定位记录数并标注候选，
不改变选点。已定位记录可单独作保留/暂不采用对照；只有 `--exclude-records`
会排除记录。两种清单均使用 `filekey`（或 R2 的 `staging_stem`）、
`file_ordinal`、`staging_row` 定位点。两种清单均保留 `cell_id`、
`native_quality_state` 与 `point_check_pass_basic`，
用于区分全部已定位记录和实际影响选点的记录。

保留全部 good 版本可在已有隔离输出上补充诊断统计：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python -m ncei.swath quality-revision --workers 4 --resume \
  --diagnosis-records ncei/derived/mb_round2/_runs/20261021_hnro14rr_diagnosis/affected_records.parquet
```

暂不采用已定位记录的版本复用隔离 L1 和未受影响航次的 L2：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python -m ncei.swath quality-revision \
  --output-dir ncei/derived/mb_round2/_runs/20261021_quality_revision/without_located_records \
  --reuse-l1 ncei/derived/mb_round2/_runs/20261021_quality_revision \
  --exclude-records ncei/derived/mb_round2/_runs/20261021_hnro14rr_diagnosis/affected_records.parquet \
  --diagnosis-records ncei/derived/mb_round2/_runs/20261021_hnro14rr_diagnosis/affected_records.parquet \
  --workers 4
```

`file_quality_summary` 与 `cruise_quality_summary` 描述质量类别计数/比例、
基础检查通过数、最终选入数、选入前后差值、1′ 格数和 JAMSTEC/strict 逐航次格残差。
文件表中的残差是该文件所属航次全部重叠格的统计，不是文件贡献点的独立水深统计。
`has_native_edit_flag=True` 表示实际观察到 flagged；未观察到 flagged 且未核对源编辑字段
时留空，不能由 good/null 或格式号推断已做过编辑。R2 计数只表示已定位清单中的记录数，
0 不表示没有其他异常。HNRO14RR 的诊断检索下限 5000 m 不用于选点。

候选覆盖读取完整 12.5 km 邻域。分母使用候选实际位置相对于全球 1′ 网格中心的距离，
核心半径 4 km、环带 8–12.5 km、8 个方位扇区；各来源及三源并集均按 `cell_id` 去重。
区域总覆盖仍限于日本海 132–136°E、36–40°N 和伊豆 140–144°E、28–32°N。
表中先给出连续覆盖率，`coverage_condition_met` 仅表示沿用的
`core>=0.6 & ring>=0.5 & min_sector>=0.25` 条件，不代表形态判定。

残差表保留 `(track_id, cell_id)`，逐航次独立连接 JAMSTEC；
合并 NCEI 水深仍为航次格中位水深的中位数，不按点数加权。
`*_residual_by_source_combination` 单列来源组合统计。
`*_strict_provenance` 记录 strict 层实际来源，其中源自 JAMSTEC 的格子不构成第三套独立测深证据。
伊豆重点差异的格内位置、文件分布和点样本写入 `izu_bonin_focus_*`；
格内离散度与同格跨源残差不作为海山高度误差，航次标识不表示独立重复测线数。

回归检查：`python -m unittest _common.tests.test_mb_round2_quality -v`。
数值对照与候选测量建议见任务
`.trellis/tasks/10-21-mb-round2-quality-revision/result.md`。
