# 来源物理改正状态表已交付

2026-10-25，同日按协调员四项修订更新。产品根：
`ncei/derived/processing_revision_20261025/source_corrections/`。
本阶段不改写任何测深或 FAA 数值，只把已交付来源的提供方改正声明结构化
为可连接的表，附来源文本指针。实现入口为
`ncei/trackline/source_corrections.py`，CLI 命令
`python -m ncei.trackline source-corrections`；包 README 已说明。
机器可读核对在产品根 `checks.json`。

## 覆盖

| 表 | 行数 | 主键 | 与清单核对 |
| --- | ---: | --- | --- |
| `trackline_source_corrections` | 695 | `track_id` | 与 `source_manifest.parquet` 键集合相等（checks: `trackline_joins_source_manifest`） |
| `legacy_faa_source_corrections` | 21 = 15+6 | `track_id` | 15 自有头 + 6 `header_shared_with_static=true` 指向同一静态头，不双计 |
| `swath_source_corrections` | 1508 + 1 样本 | `filekey` | 产品 1508 行 filekey 集合与两批次 manifest 相等 |
| `swath_svp_profiles` | 123 | `svp_id` | HNRO07RR 97 / HNRO05RR 1 / HNRO06RR 24 / HNRO14RR 样本 1 |
| `evidence_texts` | 11422 | `scope`+`location` | formal_header 631 + mb41 前导 716 + inf_file 10075 |

swath 逐文件状态汇总（`summary.csv` 同内容）：

| 航次 | 文件 | 声线追踪已应用 | 换能器深度/升沉调整模式 | SVP 记录存在 | 未知 | 潮位该步关闭 | 偏差再施加关闭 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HNRO07RR | 502 | 502 | 0 | 0 | 0 | 502 | 502 |
| HNRO05RR | 17 | 17 | 0 | 0 | 0 | 17 | 17 |
| HNRO06RR | 196 | 178 | 18 | 0 | 0 | 196 | 196 |
| NT05-06 | 38 | 0 | 0 | 0 | 38 | 0 | 0 |
| AII8L18 | 19 | 0 | 0 | 0 | 19 | 0 | 0 |
| RR1412 | 736 | 0 | 0 | 736 | 0 | 0 | 0 |
| HNRO14RR（样本，非产品） | 1 | 1 | 0 | 0 | 0 | 1 | 1 |

## 本轮四项修订的落实

1. HNRO06RR 18 文件改记为
   `declared_corrected_transducer_depth_heave_adjustment_mode`（换能器
   深度/升沉调整模式）。新增 `mbprocess_mode_statement` 保留原模式句
   （"Depths and crosstrack distances adjusted for change in transducer
   depth and/or heave."），实际参数单列：18 文件 `heave_step_state`
   原文均为 "Heave: not modified"、`draft_step` 均为 "Draft set:
   6.000000 meters"。缺 `heave_step` 原文时的取值改为 `unknown`，
   不再由模式推断。checks.json 的
   `hnro06rr_transducer_depth_heave_mode` 记录该 18 文件的模式引文、
   heave/draft 原文核验与示例文件。
2. RR1412 逐行保存实际读取的 `inf_path`、`inf_svp_notice`/
   `inf_ssv_notice`/`inf_attitude_notice` 原通知文本与 `*_line` 行号；
   原文行进入 `evidence_texts`（`carrier=inf_file`，`location=
   <inf路径>:line N`）。736 行全部有 inf 路径与 SVP 通知，732 行有
   SSV 通知，736 行有 attitude 通知；mb41 航次的 inf 元数据行
   （Corrected Depths/Tide Corrected/Roll/Pitch Bias/Draft，715 行）
   同样入表。checks.json 的 `rr1412_inf_notices` 给出计数、示例通知
   与其精确位置；全部是原文行，非整理语句。
3. HNRO14RR 样本的 18 点声速剖面以 `svp_id=122` 连入
   `swath_svp_profiles`（至 12000 m、1524 m/s），
   `is_sample_evidence_only=true` 保留；模块 docstring 与 README 将
   其定位改为既有源声束异常/敏感性解释的证据，非源导航异常证据。
4. 静态/FAA 表新增 `draft_correction_state`/
   `draft_correction_value_m`/`draft_correction_evidence` 与
   `tide_correction_state`/`attitude_correction_state`（MGD77T 正式头
   无潮位/姿态字段，除 swath 前导证据外一律 unknown）。吃水只按原文
   声明：alar01rr/cntl01rr/cntl02rr/pptu01wt
   "DEPTHS CORRECTED FOR 5 METER SHIP DRAFT" → declared_applied 5 m；
   lh7803 "BATHYMETRY CORRECTED FOR DRAUGHT" → declared_applied 无数值。
   静态 695 中 692 unknown、legacy 21 中 17 unknown；不由仪器或
   assumed velocity 推断。原有字段与值全部保留。

## 其余保留事实（首轮已核，未变）

- HNRO06RR 元数据横摇偏差分两组：169 文件 -0.97°、27 文件 0.06°，
  纵摇均 0.38°；该次处理偏差再施加均关闭，两组均保留元数据标定值与
  步骤开关两列。
- HNRO07RR 502 文件声线追踪剖面最深处全部延拓至 12000 m，延拓段声速
  三组：1524（324 文件）、1526（174）、1500（4，仅
  19990624-1200p 至 19990625-1900p 首四个文件）。
- mbprocess 版本 5.0.beta30；运行日期 HNRO05RR 2003-09-18、HNRO06RR
  2003-09-19、HNRO07RR 2003-09-30、HNRO14RR 样本 2003-10-01。
- NT05-06（GeoDAS 转换 XTF）与 AII8L18（1987 URI VAX 二进制）交付
  文件与 `.inf` 无任何改正声明，全部 unknown；AII8L18 树内 VAX 处理
  脚本只涉及导航与重合并，无声明。
- 静态/FAA 头：SOUND_VEL、VDATUM_CO、BATH_INTRP、BAT_CPCO 逐记录
  代码（pionr* 59、nbp9603a 88、v3005 系 11/12/13 Matthews 区、
  63=Carter 表等）与重力公式/参考系统/GRAV_CORR 原文逐航次保留；
  gh7504、a2089l03、ew9601、hen04-3 头内未声明公式，不代填。
- 重力不重复改正：FAA 原值不变；下游闭合证据（88000911↔IGF1980、
  gh7504↔IGF1930、84002111 需源 EOTVOS）以路径链接，未重算，
  未据其改写头声明。

## 方法与证据指针

- mb41 前导：`gzip` 流式解压至首个 `SB2100DR`（约 1.8–3.6 KB，
  `preamble_bytes` 逐文件记录），不解压全文件、不解码声束。
  `evidence_texts.parquet` 保存原文与 `bytes 0-N` 指针。
- `.inf`：逐文件读取元数据块与记录类型通知，`inf_path` 与行号入表，
  原文行入 `evidence_texts`。RR1412 的 inf 位于
  `em122/generated/<同名>.inf`。
- 静态/FAA 头：复用 `read_header` 与现成 `source_headers.parquet`、
  `source_quality_counts.csv`、两个 conversion manifest。
- 代码含义依据本地
  `/mnt/data2/06-Projects/11-swot-ssl-encoder/outputs/ship-source-processing-verification-v1/source/mgd77.pdf`
  （BAT_CPCO/VDATUM_CO/G_FORMU_CO/G_RFSYS_CO 表）。

## 核对（checks.json，机器可读）

- 覆盖：695/21/1508+1 行、键唯一、静态表与 source_manifest 键集合
  相等、swath 产品行 filekey 集合与两批次 manifest 相等、
  evidence 行数 11422（按 carrier 分解）。
- 案例：HNRO06RR 模式 18 文件（模式引文/heave 原文/draft 原文全真）；
  RR1412 inf 通知（736 路径/SVP、732 SSV、736 attitude、示例通知与
  `line 56` 位置、3676 条通知证据行）；HNRO14RR 样本（svp_id=122 连
  表、18 点、applied_preamble_raytracing）；MGD77T 吃水/潮位/姿态
  （static 3 声明、legacy 4 声明、unknown 计数 692/695、695/695、
  21/21）。
- 独立抽读：evidence 中 RR1412 SVP 通知行逐条为原文 `DN:` 行；
  mb41 航次 Corrected Depths 原文行 715 条全部可由 location 定位。

## 复算

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 POLARS_MAX_THREADS=1 \
/opt/miniforge3/envs/torch29/bin/python -m ncei.trackline source-corrections
```

单进程、约 2 分钟、输出约 1.7 MiB；原始数据全程只读。本记录为
`.trellis/tasks/10-25-ship-processing-repair/source_corrections_result.md`，
协调员负责 prd/result 与产品根 README 的集成。执行槽交回。
