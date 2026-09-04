# Subzip → 航次 ID 规范化与唯一航次计数口径（2026-09）

任务：理清 "255 vs 649" 的分歧，给出 763 个 subzip 的航次 ID 规范化清单和唯一航次数的确定口径。
产物：`jamstec/multibeam/manifests/subzip_cruise_map.parquet`（+ `.tsv`，776 行，一行一个源 subzip）。
本文不改任何现有产品文件；`SOURCE.md` 的问题单独列出，留待用户裁决。

## 1. 两个包裹、一套数据

`国外水深第{一,二}部分.zip`（394 + 382 = 776 个内部 zip）与 `archive/source_zips/bathymetry.7z`
（解包为 `archive/bathymetry_data/`，776 个 zip）内部文件清单**完全一致**（本次逐一比对，diff 为空）；
SOURCE.md 的指纹证据链亦认定两者是同一语料的两次转手。因此航次计数只有一个对象：这 776 个 subzip。

## 2. 规范化规则

对 subzip 目录名（去 `.zip`）依次剥离后缀：

1. `_(bathymetry|gravity)_(dmo|pi)$`
2. `_bathymetry$`
3. `_leg\d+$`

得到 `name_normalized`（如 `KM16-08_leg1_bathymetry_dmo` → `KM16-08`）。
对管线里 740 个有 `cruise_id_guess` 的 subzip，**guess 与 name_normalized 逐一相等（0 个例外）**，
即 guess 完全由 subzip 名决定，文件内容只决定"有没有"guess。

## 3. 唯一航次数的确定口径

| 口径 | 数量 | 说明 |
|---|---:|---|
| 源 subzip 总数 | 776 | 两包裹同集 |
| 剔除 bad_subzips 后进入管线 | 763 | `docs/bad_subzips.txt` 的 13 个 |
| **唯一航次（权威口径）** | **649** | `cruise_id_guess` 去重；与 `manifests/cruise_summary_for_review.tsv`、`docs/航次清单_协作者审核.md` 完全一致（两者集合相等，逐元素核对） |
| 其中船名前缀 | 629 | KR 276 / KY 184 / KM 64 / KS 62 / MR 40 / KH 3 |
| 其中日期命名 | 20 | `20120408` 等，打包日期名，船不明 |
| 唯一 name_normalized（763 内） | 666 | 649 + 17：23 个"无 guess"subzip 的名字贡献 17 个新航次名（见表 4） |
| 唯一 name_normalized（776 全部） | 674 | 再加 13 个 bad subzip 的 8 个独有航次名 |

引用场景建议：说"本语料覆盖 N 个航次"时用 **649**（点层实际有数据的航次）；说"源包里出现过的航次名"时用
666 / 674 并注明口径。KM 前缀（Kilo Moana，SOEST/夏威夷大学运营）不是 JAMSTEC 船，跨库比对（如
NCEI MBBDB）时它会与 NCEI 目录同号重叠，见 `ncei/docs/step13_mbbdb_crosswalk.md`。

## 4. 异常映射表

### 4.1 excluded_bad_subzip（13 个）

在 `docs/bad_subzips.txt` 中、未进管线：KR01-10、KR01-12_leg1、KR06-11、KR07-16、KY13-04、KY14-10、
MR00-K02、MR02-K01、MR02-K04_leg1、MR02-K05_leg1、MR03-K01、MR03-K03_leg1、MR07-06_leg2。

### 4.2 no_cruise_guess（23 个，cruise_id_guess 不可靠的条目）

只含 `non_dat` 文件（合计 131 个文件、0 个点进入点层），内容无法给出 guess，身份只能取 subzip 名：

KM16-01_leg1/leg2、KM16-02_leg1/leg2、KM16-03、KM16-05_leg1、KM19-01、KM19-06、KR13-10、KR14-04、
KR15-05、KR15-07、KR18-13、KR18-14_leg1/leg2、KR18-15、KS-16-E01、KS-17-J04、KS-17-J05、KS-19-17、
MR05-05_leg1/leg2/leg3。

若要把它们计入航次覆盖，用 name_normalized（上表 §3 的 666 口径）。

### 4.3 date_named（20 个）

`20120408`–`20120508` 的日期名 subzip，来自郭恒洋包裹的二次打包（内部 mtime 2024-07-24）；guess 即日期串。
它们的船与航次号未知，649 口径里单列为 20 个"日期命名航次"。

## 5. "255" 的来历（分歧消除）

`jamstec/SOURCE.md` 第 13 行称 "the first source-zip enumerates 255 unique JAMSTEC cruise IDs"。
本次复算：**国外水深第一部分.zip 进入管线的 390 个 subzip 中，KR 前缀的唯一 cruise_id_guess 恰好 255 个**
（同范围内其余唯一 guess：KM 72、KH 3、日期名 20，另有 16 个 subzip 无 guess）。即 255 是“第一包的 KR 子集计数”，
写成 "unique JAMSTEC cruise IDs" 是以偏概全；它引用的证据文档
`docs/experiments/2026-05_dataset-source-attribution.md` 在 jamstec/ 下不存在
（git 历史中该文件只在仓库根 `docs/experiments/` 下，且任何版本都不含 "255" 字样），
该数字只出现在 SOURCE.md 本次改写（commit 890559e）里。

结论：**649 是唯一可复现的全量口径；255 是分包裹、分船前缀的部分计数，不应再作为语料规模引用。**
SOURCE.md 第 12–15 行的两处问题（255 表述、失效链接）本文不代改，建议下次文档任务修正。

## 6. 复现方法

`subzip_cruise_map.parquet` 由以下步骤生成（一次性，无独立脚本；输入均为仓库内文件）：

```
file_manifest.parquet      → 按 subzip_id 聚合 n_files / n_files_used / cruise_id_guess（单值集合取元素）
bad_subzips.txt            → excluded_bad 标记
国外水深第{一,二}部分.zip 内部清单（unzip -l）→ in_part1 / in_part2
§2 规则                   → name_normalized、anomaly / anomaly_note
```

列：`subzip_id, in_part1, in_part2, excluded_bad, n_files, n_files_used, cruise_id_guess,
name_normalized, anomaly, anomaly_note`。
