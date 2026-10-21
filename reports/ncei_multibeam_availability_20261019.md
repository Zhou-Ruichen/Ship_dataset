# NCEI 多波束在四个目标海区的可用性盘点与下载清单建议

日期：2026-10-20。
性质：只读元数据盘点，未下载任何测深数据本体。网络访问仅限 NCEI 公开元数据服务（经 127.0.0.1:2085 代理）。
工作目录：`/mnt/data2/00-Data/ship/`（本报告在其 `reports/` 下）。

## 0. 结论速览

| 海区 | 航迹实质进入海区的航次 | 其中本地已持有 | 建议下载（服务该区） | 对应下载量（MBBDB 目录 fileSizeSum） |
|---|---:|---:|---:|---:|
| 伊豆-小笠原 140–144°E, 28–32°N | 11 | 0 | 8 | 约 16.3 GB |
| 日本海 132–136°E, 36–40°N | 6 | 0 | 6 | 约 3.4 GB |
| 144–148°E, 36–40°N（对照） | 13 | 2 | 5 | 约 1.7 GB |
| 140–144°E, 32–36°N（对照） | 17 | 1 | 10 | 约 18.1 GB |
| 合计（跨区共享航次去重） | 31 个唯一航次 | 2 | **核心 20 个约 21.8 GB**；另有 2 个可选大户约 21.1 GB（MGL0909、MV1304），上限合计约 42.9 GB |

伊豆-小笠原与日本海两个新方向海区的增量价值高（本地 JAMSTEC 覆盖分别只有 87.6%/25.8%，且日本海几乎没有 JAMSTEC 多波束）；两个对照海区 JAMSTEC 已覆盖 92.2%/89.1%，NCEI 增量以重复覆盖为主，只建议拉少量高价值航次。跨区共享航次（RR1412、PD20IB02、AII8L18、TN168 等）在多行出现，下载一次服务多区。

## 1. 数据来源与方法

### 1.1 NCEI 多波束航次元数据（两个服务）

- **MBBDB 目录服务**（航次级：平台、年份、文件数、字节数、bbox）：
  `https://www.ngdc.noaa.gov/next-catalogs/rest/multibeam/catalog/survey?max=500&offset=0..4000`，9 次 GET（2026-10-20，原始 JSON 存 reports/mbbdb_20261019/survey_*.json）。去重 surveyId 后 **4,074 个航次**（step16 在 2026-09 拉到 3,973，一个月内新增约 101 个条目）。复现命令见 `ncei/docs/step13_mbbdb_crosswalk.md` §2。
- **Bathymetric Data Viewer 航迹服务**（航次级折线几何，本轮新启用）：
  `https://gis.ngdc.noaa.gov/arcgis/rest/services/web_mercator/multibeam_dynamic/MapServer/0/query?where=1=1&geometry=<海区包络>&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=...&returnGeometry=true&outSR=4326&f=geojson`
  （服务元数据 `.../MapServer/0?f=json`：esriGeometryPolyline，字段含 SURVEY_ID/PLATFORM/SURVEY_YEAR/TRACK_LENGTH/FILE_COUNT/DOWNLOAD_URL。该端点从 viewer 前端脚本 `https://www.ncei.noaa.gov/maps/bathymetry/assets/index-CFGbnI5Q.js` 中找到。）

方法：先目录 bbox 粗筛，再航迹折线精筛（包络相交 + 逐段中点判定计算海区内航迹长度，段级去重——MV1305 等航次的折线含约 600 个重复 part，不去重会虚增长度）。跨洋过境航次（FK190726、MGL1902、SO268-3、HG2001-T、ARTEX2025）逐顶点核查，在海区内顶点数为 0，全部排除（它们只是 bbox 跨 180° 或跨太平洋才命中粗筛）。

### 1.2 本地覆盖对照数据

| 数据 | 路径 | 用途 |
|---|---|---|
| JAMSTEC 质控格点（239 万） | `jamstec/multibeam/derived/cells_1min_qcfiltered/cells.parquet` | 各海区已有格点覆盖百分比 |
| JAMSTEC 逐航次格点归因 | `jamstec/multibeam/manifests/file_cells_manifest_1min.parquet` + `subzip_cruise_map.parquet` + `derived/file_cells_1min/*.parquet` | 各海区贡献 cruise 数 |
| NCEI 单波束最终格点 r2 | `ncei/derived/singlebeam/file_cells_1min_final_r2/*.parquet`（5,365 片） | 单波束格点覆盖与轨线数 |
| 已下多波束航次台账 | `ncei/manifests/round2_download_log.parquet`（status=ok：platforms_tree 202 + r2r 169，r2r 中 54 个在 MBBDB 目录同号） | "本地已持有"判定 |
| 入口清单（20 条 mb track） | `ncei/manifests/bathymetry_entry_manifest.parquet`（instrument_class_pred==multibeam 共 20：17 track + 3 个 M.rar 象限文件） | 与 step13 §1.2 一致 |

"本地已持有"口径：platforms_tree 202（status=ok）+ r2r 同号 MBBDB 54 + JAMSTEC 同号 11（KM/MR 系）+ strict 零头 2 = 269。step13/16 的"91"是 2026-09 时点（platforms_tree 当时只有 24 个目录），本轮以台账实查为准。

### 1.3 各海区本地覆盖现状

| 海区 | JAMSTEC mb 格点 | 贡献 cruise 数 | NCEI 单波束格点（final r2） | 单波束 track 数 |
|---|---:|---:|---:|---:|
| 伊豆-小笠原 140–144°E 28–32°N | 50,454 / 57,600 = **87.6%** | 86 | 25,076 = 43.5% | 87 |
| 日本海 132–136°E 36–40°N | 14,879 / 57,600 = **25.8%** | 12 | 17,395 = 30.2% | 40 |
| 144–148°E 36–40°N | 53,119 / 57,600 = **92.2%** | 97 | 14,666 = 25.5% | 62 |
| 140–144°E 32–36°N | 51,313 / 57,600 = **89.1%** | 198 | 28,091 = 48.8% | 144 |

（strict_primary 与 qcfiltered 格点数在这四个海区一致，ncei_multibeam 零头 0 格，`ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet`。）

## 2. 逐海区可用航次表

航迹长度为折线段去重后的海区内长度（km）；下载量为 MBBDB 目录 fileSizeSum（全航次，非仅海区内部分）；格式为 platforms 树 `data/version1/MB/` 下实测后缀（本轮逐航次抽查目录列表页）。"轨线形态"按海区内长度与总长度之比判断。

### 2.1 伊豆-小笠原 140–144°E, 28–32°N（优先级 1）

11 个航次进入，全部为本地增量。海区内合计约 18,100 km 航迹。

| 航次 | 平台 | 年份 | 海区内轨线 km | 全航次轨线 km | 目录体积 GB | 原始格式 | 形态 |
|---|---|---|---:|---:|---:|---|---|
| RR1412 | Roger Revelle | 2014 | 7,897 | 23,526 | 11.38 | .all.mb58.gz（736 个） | 面状密集（海山调查） |
| NT06-21 | Natsushima | 2006 | 3,099 | 9,673 | 0.03 | .mb162 | 面状 |
| MV1305 | Melville | 2013 | 1,664 | 34,120 | 27.92 | .all.mb58.gz（1,633 个，em122/） | 过境为主+局部 |
| PD20IB02 | Pressure Drop | 2020 | 1,326 | 4,042 | 4.52 | .gsf.mb121.gz（147 个，version2/MB/em124/） | 面状 |
| NT05-06 | Natsushima | 2005 | 1,014 | 1,049 | 0.10 | .mb84.gz | 面状（几乎全区在位） |
| AII8L18 | Atlantis II | 1987 | 803 | 4,577 | 0.01 | .rc00.gz 等 | 穿线 |
| EW9508 | Maurice Ewing | 1995 | 731 | 14,321 | 0.06 | .mb21.gz（Hydrosweep DS） | 穿线 |
| RR1303 | Roger Revelle | 2013 | 626 | 33,223 | 8.41 | .all.mb58.gz（em122/） | 过境为主 |
| TN168 | Thomas G. Thompson | 2004 | 552 | 9,797 | 0.05 | .mb21.gz | 穿线 |
| MV1304 | Melville | 2013 | 55 | 19,988 | 15.36 | .all.mb58.gz | 擦边 |
| NT05-16 | Natsushima | 2005 | 2 | 757 | 0.13 | .gz（mb84 系） | 擦边 |

**建议下载（8 个，约 16.2 GB）**：RR1412、NT06-21、PD20IB02、NT05-06、AII8L18、EW9508、TN168、NT05-16。不推 MV1305/MV1304/RR1303（各自 15–28 GB，海区内只占其航迹 2–5%，单位覆盖的下载成本高；若已在 B 档全局订单里则顺带获得）。日本 JAMSTEC 缺口主要在南部（伊豆诸岛周围 87.6% 覆盖之外的 12%），RR1412 与 NT 系航次集中在此。

### 2.2 日本海 132–136°E, 36–40°N（优先级 2）

6 个航次进入，全部为增量。海区内合计约 4,780 km。这是四区中 JAMSTEC 覆盖最薄的海区（25.8%，仅 12 个 cruise 贡献，集中在 KR14-08/KR16-08/KR15-11）。

| 航次 | 平台 | 年份 | 海区内轨线 km | 全航次 km | 目录体积 GB | 原始格式 | 形态 |
|---|---|---|---:|---:|---:|---|---|
| HNRO14RR | Roger Revelle | 2000 | 1,598 | 3,151 | 0.88 | .mb41.gz（SeaBeam 2100） | 面状 |
| HNRO07RR | Roger Revelle | 1999 | 1,477 | 6,204 | 2.02 | .mb41.gz | 面状+穿线 |
| HNRO06RR | Roger Revelle | 1999 | 579 | 5,472 | 0.44 | .mb41.gz | 穿线为主 |
| COOK09MV | Melville | 2001 | 434 | 785 | 0.01 | .mb32 | 穿线 |
| HNRO05RR | Roger Revelle | 1999 | 388 | 598 | 0.02 | .mb41.gz | 穿线 |
| PPTU11WT | Thomas Washington | 1986 | 308 | 13,070 | 0.01 | 老式无后缀（86aug01 等） | 穿线 |

**建议下载（6 个全部，约 3.4 GB）**：代价极小（合计 3.4 GB），HNRO14RR/HNRO07RR 是海区内主力。注意点：
- .mb41.gz 不在 34 号提取器现有支持集（.mb58.gz/.all.gz/.mb21.gz + ERGNMESS 内容签名）内，且 `.mb41.gz` 在 `KNOWN_UNSUPPORTED_SUFFIXES` 中被显式记为不支持——日本海增量要入库需先扩 `resolve_mb_format`（MBIO format 41 = Reson SeaBat 8160/SeaBeam 2100 系列，mbio 支持，改动量小）。
- COOK09MV 是 .mb32（SeaBeam 2100 处理格式，与 MGLN03MV 同类）；PPTU11WT 是 1986 年老式无后缀格式，两者入库需格式普查先行（step 33 流程会登记）。
- 本地单波束在这 6 条上已有格点（hnro07rr 1,069 格、hnro14rr 481 格等，`file_cells_1min_final_r2`），多波束是密度升级而非从零覆盖。

### 2.3 144–148°E, 36–40°N（JAMSTEC 密集区对照）

13 个航次进入，其中 2 个本地已持有（MR00-K06 = JAMSTEC Mirai 同号、MGLN03MV = platforms_tree 已下但提取状态 no_usable_files，.mb32）。海区内合计约 19,700 km，但 JAMSTEC 已覆盖 92.2%（97 个 cruise）。

| 航次 | 平台 | 年份 | 海区内 km | 目录 GB | 格式 | 状态/形态 |
|---|---|---|---:|---:|---|---|
| SO201-1b | Sonne | 2009 | 7,336 | 3.90 | .allp.mb57.gz | 增量；过境为主（全长 11.6 万 km 跨北极） |
| MGLN04MV | Melville | 2006 | 2,062 | 0.04 | .mb32 | 增量；面状 |
| HLY04TB | Healy | 2004 | 2,012 | 0.45 | .mb41.gz | 增量；穿线+局部 |
| MGL0909 | Marcus G. Langseth | 2009 | 1,734 | 5.69 | .all.mb58.gz（1,032 个） | 增量；过境为主 |
| RNDB09WT | Thomas Washington | 1988 | 1,436 | 0.01 | 老式无后缀 | 增量；穿线 |
| TN168 | Thomas G. Thompson | 2004 | 1,074 | 0.05 | .mb21.gz | 增量；穿线 |
| ZHNG08RR | Roger Revelle | 2005 | 1,057 | 1.42 | .all.mb56.gz | 增量；穿线+局部 |
| MR00-K06 | Mirai | 2000 | 823 | 4.14 | .mb41.gz（sb2112/） | **JAMSTEC 树同号已持有** |
| HLY04TC | Healy | 2004 | 527 | 0.31 | .mb41.gz | 增量；穿线 |
| ZHNG09RR | Roger Revelle | 2005 | 517 | 2.40 | .gz（mb56 系） | 增量；穿线 |
| MGLN03MV | Melville | 2006 | 482 | 0.01 | .mb32 | **已下**，no_usable_files |
| ZHNG07RR | Roger Revelle | 2005 | 427 | 0.87 | .all.mb56.gz | 增量；穿线 |
| PD20JT01 | Pressure Drop | 2020 | 228 | 2.83 | .gsf.mb121.gz | 增量；穿线 |

**建议下载（低优先，5 个约 1.7 GB：MGLN04MV、HLY04TB、TN168、HLY04TC、ZHNG07RR）**；TN168/HLY04TB/MGLN04MV 与 2.4 节同批合并下单，边际成本更低。SO201-1b 与 MGL0909 海区内贡献不小但 80% 以上航迹在区外（北海以北/阿留申方向），单为对照区拉 9.6 GB 不划算；ZHNG 系 .mb56.gz 是 34 号已知不支持格式（mb56 在 KNOWN_UNSUPPORTED_SUFFIXES），ZHNG07RR 若要入库需先解决格式。.mb57.gz 是"已知崩溃"格式（step17 记录），SO201-1b 全航次都是它，即便下了也进不了现有链路。

### 2.4 140–144°E, 32–36°N（JAMSTEC 密集区对照）

17 个航次进入，1 个本地已持有（MGLN03MV）。海区内合计约 13,800 km；JAMSTEC 已覆盖 89.1%（198 个 cruise 贡献格点）。

| 航次 | 平台 | 年份 | 海区内 km | 目录 GB | 格式 | 状态 |
|---|---|---|---:|---:|---|---|
| RR1412 | Roger Revelle | 2014 | 3,670 | 11.38 | .all.mb58.gz | 增量（与 2.1 同航次） |
| MV1304 | Melville | 2013 | 2,418 | 15.36 | .all.mb58.gz | 增量 |
| TN168 | Thomas G. Thompson | 2004 | 1,206 | 0.05 | .mb21.gz | 增量 |
| HLY04TB | Healy | 2004 | 929 | 0.45 | .mb41.gz | 增量 |
| PD20IB03 | Pressure Drop | 2020 | 827 | 0.40 | .gsf.mb121.gz | 增量 |
| RNDB10WT | Thomas Washington | 1988 | 812 | 0.02 | 老式无后缀 | 增量 |
| ZHNG07RR | Roger Revelle | 2005 | 764 | 0.87 | .all.mb56.gz | 增量 |
| MGLN04MV | Melville | 2006 | 746 | 0.04 | .mb32 | 增量 |
| MGL0909 | Marcus G. Langseth | 2009 | 669 | 5.69 | .all.mb58.gz | 增量 |
| MGLN03MV | Melville | 2006 | 637 | 0.01 | .mb32 | 已下（no_usable_files） |
| PD20IB02 | Pressure Drop | 2020 | 460 | 4.52 | .gsf.mb121.gz | 增量（与 2.1 同航次） |
| ZHNG08RR | Roger Revelle | 2005 | 276 | 1.42 | .all.mb56.gz | 增量 |
| HLY04TC | Healy | 2004 | 214 | 0.31 | .mb41.gz | 增量 |
| AII8L18 | Atlantis II | 1987 | 134 | 0.01 | .rc00.gz | 增量（与 2.1 同航次） |
| PD20JT01 | Pressure Drop | 2020 | 17 | 2.83 | .gsf.mb121.gz | 增量；擦边 |
| ZHNG09RR | Roger Revelle | 2005 | 2 | 2.40 | .gz（mb56 系） | 擦边 |
| RNDB09WT | Thomas Washington | 1988 | 0 | 0.01 | 老式无后缀 | 边界接触 |

**建议下载（合并 2.3/2.4 视角，本区新增 6 个约 1.3 GB：TN168、HLY04TB、HLY04TC、PD20IB03、RNDB10WT、MGLN04MV；另有共享航次 RR1412/PD20IB02/AII8L18/ZHNG07RR 已计入 2.1/2.3 批次）**。不推 MV1304（15.4 GB，91% 航迹在区外）、ZHNG08/09RR（.mb56.gz 不支持且区内贡献小）、MGL0909（5.7 GB 大部分在区外，且与本区 89% JAMSTEC 覆盖重复，列为可选大户）。

## 3. 建议下载清单（合并去重）

22 个唯一航次、合计约 42.9 GB（MBBDB fileSizeSum 口径；其中核心 20 个约 21.8 GB，可选大户 2 个约 21.1 GB）。实际 platforms 树下载量可小于此（PD20 系可只拉 version2/MB/ 子树，跳过 ancillary）。分两批：

**第一批（日本方向增量，14 个航次，约 19.7 GB）**

| 航次 | 服务海区 | 体积 GB | 格式可入链 | 平台树路径（ships/ 下） |
|---|---|---:|---|---|
| RR1412 | 伊豆+南对照 | 11.38 | 是（mb58） | roger_revelle/RR1412 |
| PD20IB02 | 伊豆+南对照 | 4.52 | 需扩（mb121） | pressure_drop/PD20IB02 |
| EW9508 | 伊豆 | 0.06 | 是（mb21） | maurice_ewing/EW9508 |
| TN168 | 伊豆+两对照 | 0.05 | 是（mb21） | thomas_g._thompson/TN168 |
| NT05-06 | 伊豆 | 0.10 | 需扩（mb84） | natsushima/NT05-06 |
| NT05-16 | 伊豆 | 0.13 | 需扩（mb84 系） | natsushima/NT05-16 |
| NT06-21 | 伊豆 | 0.03 | 需查（mb162） | natsushima/NT06-21 |
| AII8L18 | 伊豆+南对照 | 0.01 | 需查（rc00.gz） | atlantis_ii/AII8L18 |
| HNRO14RR | 日本海 | 0.88 | 需扩（mb41） | roger_revelle/HNRO14RR |
| HNRO07RR | 日本海 | 2.02 | 需扩（mb41） | roger_revelle/HNRO07RR |
| HNRO06RR | 日本海 | 0.44 | 需扩（mb41） | roger_revelle/HNRO06RR |
| HNRO05RR | 日本海 | 0.02 | 需扩（mb41） | roger_revelle/HNRO05RR |
| COOK09MV | 日本海 | 0.01 | 需查（mb32） | melville/COOK09MV |
| PPTU11WT | 日本海 | 0.01 | 需普查（老式） | thomas_washington/PPTU11WT |

**第二批（对照区补充，8 个航次，核心 6 个约 2.1 GB，优先级低）**：HLY04TB（0.45）、HLY04TC（0.31）、PD20IB03（0.40）、RNDB10WT（0.02）、MGLN04MV（0.04）、ZHNG07RR（0.87，mb56 需先解决）；可选大户 2 个：MGL0909（5.69）、MV1304（15.36）——仅在预算富余时。

说明：第一批中 .mb41.gz（HNRO 系、HLY 系）被 34 号脚本显式列为不支持，需在 `ncei/code/34_mb_round2_extract_points.py` 的 `FORMAT_BY_SUFFIX` 增加 `.mb41.gz → 41`（MBIO 格式 41 = Reson SeaBat 8160 原始，mbio 原生支持）并过一轮小样本验证；.mb84（OIC ISSYS 格式）与 .mb162、.gsf.mb121 需先跑 33 号格式普查确认 mbio 可读性。mb21/mb58 无需改动。

## 4. 新增覆盖 vs 重复覆盖的判断

| 海区 | 判断 | 依据 |
|---|---|---|
| 伊豆-小笠原 | **新增为主** | JAMSTEC 87.6% 但缺口集中在南部岛弧区（50,454/57,600）；RR1412（7,897 km 区内）与 NT 系面状测量正落在此方向；11 航次全部是增量 |
| 日本海 | **全新增** | JAMSTEC 仅 25.8%（12 cruise）；6 航次全区为增量；单波束已有稀疏轨线（30.2% 格点），多波束是密度量级升级 |
| 144–148°E, 36–40°N | **重复为主** | JAMSTEC 92.2%（97 cruise）；13 个 NCEI 航次的区内航迹大多与 KR/KM 系测线重叠（SO201、MR00-K06、ZHNG 系航线即日本船常走的勘测走廊） |
| 140–144°E, 32–36°N | **重复为主** | JAMSTEC 89.1%（198 cruise，四区最密）；仅 RR1412/MV1304 的 2013–14 年新测线有较大部分在 JAMSTEC 时窗（2000–2015）之外或之外海区 |

一个保留：格点百分比是 1′ 网格占有率，不等于测深密度相等；NCEI 2010 年代航次（RR1412、PD20 系）的条带分辨率高于 JAMSTEC 部分老航次，对照区里"重复覆盖"仍可能提升格点内精度。此判断需下载后按格级交叉核实。

## 5. 入库路径（引用本仓管线步骤）

按 README "Adding new ship data" 与 step15/17 链条，NCEI 平台树原始多波束走 stage 32–37：

1. **下载落盘**：`ncei/raw_round2/platforms_tree/<ship>/<cruise>/`（现有台账 `ncei/manifests/round2_download_log.parquet` 续记；下载器脚本 `ncei/code/download_tier_a_round2.py` 的模式）。
2. **完整性审核**：stage 32（`32_mb_round2_completeness.py`，`--live-expected` 对照平台树目录列表）。
3. **格式普查**：stage 33（`33_mb_round2_format_survey.py`）；.mb41/.mb84/.mb121/.mb162 新格式在此登记。
4. **gzip 预检**：stage 41（`41_gzip_preflight.py`）。
5. **L1 提取**：stage 34（`34_mb_round2_extract_points.py`）；先按 §3 扩 FORMAT_BY_SUFFIX。
6. **L2 格点 + L3 片段**：stage 35、36（输出 `ncei/derived/mb_round2/<cruise>/`，L3 片段独立待审，合入生产需另审）。
7. **覆盖统计**：stage 37（相对严格层 2,398,774 格算净新增，可按本报告四海区口径出格级覆盖——这将把 §4 的"重复为主"判断落到格级）。

单波束侧无需动作（HNRO/PPTU 等 track 已在 `file_cells_1min_final_r2`）。

## 6. 局限与未查到项

- **格式描述勘误（2026-10-20，sol 执行时对本机固定 MBIO 注册表核实）**：本报告 §2/§3 的格式中文描述有误——本机 MBIO 注册表为 format 41 = MBF_SB2100RW（SeaBeam 2100 系列 vendor 格式）、format 84 = MBF_XTFR8101（XTF/Reson SeaBat 81XX）、format 32 = MBF_SB2000SB（SeaBeam 2000）。`.mb41.gz → 41` 的映射与解析器一致，不受影响；仅文字描述以本勘误为准。证据：`ncei/derived/mb_round2/_runs/20261019T195752Z_first_batch/discrepancy_record.md` 与 `mbio_format_registry.json`。

- **下载量是 MBBDB 目录 fileSizeSum**，含 METADATA/ANCILLARY 类目（PD20 系的 ancillary 占 3.9 GB 中的 3.94 GB 主体为 GSF 备份类，真正 MB PROCESSED 只有 0.58 GB——下载时可只拉 version2/MB/ 子树）。
- **航迹长度来自 viewer 折线服务**，折线是简化几何（npts 数百到数千），海区内长度误差估计 ±10–20%，不影响排序结论。
- **NT06-21 的 TRACK_LENGTH 字段为 0**（目录侧坏记录），区内 3,099 km 由折线直接算得，可信。
- **四个海区之外**（如伊豆-小笠原以东 144–148°E, 28–32°N）未在本轮范围，未查。
- MGLN03MV 已下载但提取失败（no_usable_files，.mb32），如需其数据要回到格式扩展问题，与新增下载无关。
- trackline_bbox（step16 产物）覆盖 30 个相关航次中的 12 个；2010 年代航次（PD20、MV13、RR13/14、SO201）无 Trackline 同号单波束，多波束是唯一来源——这与 step13 §4 的新船模式一致。

## 7. 数字出处索引

| 数字 | 出处 |
|---|---|
| MBBDB 目录 4,074 航次（2026-10-20） | next-catalogs/rest/multibeam/catalog/survey 9 页 GET，reports/mbbdb_20261019/survey_*.json；step16 时点 3,973 见 `ncei/docs/step16_mbbdb_value_ranking.md` §1 |
| 各航次平台/年份/体积/格式类目 | 同上 JSON（fileStatsByCat/fileSizeSum）；解析表 reports/mbbdb_20261019/mbbdb_catalog.tsv |
| 海区相交航次与区内轨线长度 | gis.ngdc.noaa.gov .../multibeam_dynamic/MapServer/0/query（geojson，2026-10-20）；reports/mbbdb_20261019/track_*.json |
| 跨洋航次排除（0 顶点） | 同上服务按 SURVEY_ID 单查，reports/mbbdb_20261019/transit_*.json |
| 各航次原始文件后缀 | data.ngdc.noaa.gov/platforms/ocean/ships/<ship>/<cruise>/multibeam/data/version1[/version2]/MB/ 目录列表页（本轮逐航次抓取） |
| JAMSTEC 各海区格点覆盖 | `jamstec/multibeam/derived/cells_1min_qcfiltered/cells.parquet`（2,394,115 格） |
| JAMSTEC 各海区 cruise 归因 | `jamstec/multibeam/manifests/file_cells_manifest_1min.parquet` + `subzip_cruise_map.parquet` + `derived/file_cells_1min/` |
| 单波束各海区覆盖与轨线数 | `ncei/derived/singlebeam/file_cells_1min_final_r2/`（5,365 片全扫） |
| 本地已持有 269 | `ncei/manifests/round2_download_log.parquet`（status=ok 实查）+ step13 §3.1 同号口径 |
| 日本海 6 track 单波束格点数 | `file_cells_1min_final_r2` 按 track_id 过滤实查 |
| 34 号提取器支持格式集 | `ncei/code/34_mb_round2_extract_points.py` L72–82 |
| mb57 已知崩溃、mb56 不支持 | `ncei/docs/step17_tier_a_processing.md` §1 |
| step16 时点本地 91 | `ncei/docs/step13_mbbdb_crosswalk.md` §3.1 |
