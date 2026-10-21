# Step 16 — MBBDB 增量航次下载价值排序（第一批订单清单）

状态：完成。
日期：2026-09。
约束：纯计算，未下载任何数据文件；网络仅取目录元数据（127.0.0.1:2085 代理、连接 10s/读 90s 超时、单 GET ≤100 KB 级、输出存 /tmp）；未提交 git。

目标：全球覆盖（六海区只标注、不筛选）；磁盘预算 9.5 TB（增量全量 43.8 TB 放不下，必须选批）。
实测锚点：step15 的 10 个 mb58 完整航次 62 GB 原始 → 50,614 个严格层外新格（≈816.5 格/GB）。
脚本：`ncei/download/rank.py`（`--fetch-trackline` 取元数据，`--compute` 出全部产物）。

## 1. MBBDB 目录重拉

- 命令同 step13 §2（8 页 × max=500，next-catalogs/rest/multibeam/catalog/survey），共 8 个 GET、约 1.8 MB，原始 JSON 在 `/tmp/mbbdb_r2/survey_*.json`。
- 本次唯一航次 **3,973**（比 step13 的 3,970 多 3 个：AT50-14、FKt231202、RC0127，均为 2023–24 新入库）。
- 本地已有 91（同 step13 口径：jamstec 树 11 + platforms_tree 24 + r2r 54 + strict 零头 2）→ **增量 3,882**。
- 有同号 Trackline 单波束 1,671；其中 1,670 的航迹 bbox 取自 Trackline 目录（17 批 × ~100 surveyIds，`/rest/trackline/catalog/survey?surveyIds=...`，每批约 70 KB；注意文档里的短路径 `/rest/trackline/survey` 全 500，与 step11 记录一致），**U2019-032 是服务器侧坏记录**（单查也 500，step11 已载），该航次退回 bbox×折扣路径。解析后的 bbox 表存 `ncei/derived/mbbdb_value_ranking/trackline_bbox.parquet`（1,694 行，含非增量同号航次）。

## 2. 估计模型与标定

两条路径共用同一套标定（step15 的 10 航次为锚点，`discount_calibration.tsv`）：

| 量 | 值 | 出处 |
|---|---|---|
| 条带折扣（实际新增格 / bbox 严格层外格数的中位数） | **0.0206** | 10 锚点剔 1 退化（AR40 的 bbox 外格仅 4，比值无意义）后 9 个的中位数；散布 0.0014–0.20 |
| 数据量上限（ sounding 数/压缩 GB） | 7.46e6 | step15：462,628,624 点 / 61.99 GB |
| 实测密度上限（新增格/压缩 GB） | 816.5 | step15：50,614 格 / 62 GB |

逐航次：

- **上限估计** `est_cells_upper` = min(bbox 内 1′ 格数 − 严格层已有格, 7.46e6×GB)；trackline 同号航次用航迹 bbox（更贴近实际走廊），其余用 MBBDB survey bbox。数据量上限防止"9 MB 文件 + 跨洋 bbox = 2,100 万格"一类退化解。
- **中心估计** `est_new_cells` = min(est_cells_upper × 0.0206, 816.5×GB)。密度上限防止把理论 sounding 上限当真实新增（锚点实际只兑现 816 格/GB）。
- **价值** = est_new_cells / GB。大多数航次被密度上限约束（价值并列 816.5），并列时按紧致度（est_cells_upper/GB 升序）再按 GB 升序破平：数据更集中的航次更可能兑现锚点密度。

锚点核对（用同一估计器回看 step15 的 10 航次）：AR23-02 估 18.2k vs 实际 26.7k、AR30-01 估 6.4k vs 实际 10.3k、FK006C 估 185 vs 实际 1,782（bbox 小而密的航次被低估约 10 倍）——估计误差在数倍到十倍量级，排序用途可用，绝对数仅供参考。

## 3. 排序与名额约束

- 可下单池：3,597 / 3,882（**285 不可下单**：71 个 fileCount=0（目录条目无文件）、214 个估计新增格为 0（数据量或 bbox 全在严格层内））。
- 无约束贪心装满 9.5 TB 需 2,119 航次 → 每船名额 = 15%（318）、每年代名额 = 25%（530）；带名额贪心选中 **2,045 航次 / 9,513.9 GB**（名额约束挤掉 74 个，主要集中在 Melville/Maurice Ewing/Thomas Washington 等船内低价值航次）。
- 三档是同一条贪心序列按累计字节切的前缀：A ≤1 TB、B ≤5 TB、C ≤9.5 TB。

## 4. 三档订单清单

清单文件：`ncei/derived/mbbdb_value_ranking/order_tier_{A,B,C}.tsv`、全序 `order_list.parquet`（2,045 行，含 rank/tier/价值/估计）、全量估计 `ranking_full.parquet`（3,882 行）。

| 档 | 航次数 | 字节 | 预计新增严格层外格 | 边际密度（格/GB） |
|---|---:|---:|---:|---:|
| A（必订） | 178 | 994.2 GB | 811,745 | 817 |
| B（预算内扩展） | +709（累计 887） | +3,923.3 GB（累计 4,917.5） | +3,203,300（累计 4,015,045） | 817 |
| C（上限） | +1,158（累计 2,045） | +4,596.4 GB（累计 9,513.9） | +2,689,304（累计 6,704,349） | 585 |

各档船名分布（前六）与年代分布：

| 档 | 船（数量） | 年代（1980s/1990s/2000s/2010s/2020s） | 有同号单波束 |
|---|---|---|---:|
| A | Melville 14、MT. MITCHELL 11、Roger Revelle 11、Atlantis 10、Knorr 10、Healy 9 | 29/28/52/47/22 | 94 |
| B | Atlantis 70、MT. MITCHELL 63、Roger Revelle 57、SURVEYOR 54、Knorr 40、N. B. Palmer 35 | 107/110/186/213/93 | 373 |
| C | Melville 112、Maurice Ewing 108、Thomas Washington 81、Atlantis 81、Roger Revelle 77、Knorr 77 | 176/298/292/270/120 | 710 |

要点：A+B（≈4.9 TB）拿到全部预计增量的 60%（401 万格）；C 档边际密度降到 585 格/GB，主要是船内与年代名额放宽后补进的大航次。若预算再紧，A 档单档的性价比最高（817 格/GB，与锚点持平）。

## 5. 六海区标注（不筛选）

以航次 bbox 与海区相交为标注（非格级相交；仅提示哪些航次可能给六区供数）：

| 档 | lon068_lat018 | lon052_lat018 | lon058_lat012 | lon059_lat015 | lon004_lat033 | lon021_lat010 |
|---|---:|---:|---:|---:|---:|---:|
| A | 0 | 4 | 2 | 4 | 2 | 0 |
| B | 5 | 9 | 4 | 2 | 8 | 3 |
| C | 5 | 10 | 9 | 6 | 20 | 18 |

六区内的实际新增格数需下载后按 step15 §7 口径重算；bbox 相交只是必要条件。

## 6. 局限与数据出处

1. **估计不确定性大**：条带折扣锚点散布 0.0014–0.20（差 140 倍），中心估计只保证量级；小而密的航次（FK006C 型）被系统性低估，跨洋过境型被相对高估。第一张订单落地后应用实测新增格重标定（step15 流程即标定器）。
2. **并列价值**：多数航次价值被密度上限钉在 816.5 格/GB，排序信息主要来自紧致度破平；拿到真实 track 数据后可分化。
3. `est_cells_tl_upper` 是未折扣上限（任务步骤 2 要求的上限口径），`est_new_cells` 是排序用中心估计，两者都在 ranking_full 里。
4. 不可下单 285 个（§3）；U2019-032（XIANGYANGHONG03, 2019）因服务器坏记录走 bbox 路径。
5. 网络出处：MBBDB 目录 8×GET（2026-09，/tmp/mbbdb_r2/survey_*.json）；Trackline bbox 17×GET（/tmp/mbbdb_r2/trackline/tl_*.json，解析结果入库 trackline_bbox.parquet）；严格层 ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet；锚点 ncei/derived/mb_round2/（step15）。
