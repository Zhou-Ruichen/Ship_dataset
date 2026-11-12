# 多波束流式重建核对

四项 L2 与 10-25 参考产品的 23 个正式字段逐值相同。NT05-06 的 38 个文件选入数和 L1 的 36 个字段逐值相同。四个试运行航次已完成，绝对路径调用、断点续跑和共享聚合器分区核对已完成。全量重建待主代理启动。

代码基于 `1900142929166fd19cd272ab02716e4ae4d73f22`，核对使用本次未提交改动。环境：Precision-7920-Tower、`/opt/miniforge3/envs/torch29/bin/python`、MB-System `5.8.3beta16`。以下 `S=ncei/derived/swath_rebuild_check`，`R=ncei/derived/processing_revision_20261025/swath`，命令均从仓库根执行。

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 POLARS_MAX_THREADS=1
P=/opt/miniforge3/envs/torch29/bin/python
S=ncei/derived/swath_rebuild_check
T=.trellis/tasks/11-12-swath-streaming-rebuild

"$P" -m ncei.swath run --cruises NT05-06 HNRO05RR HNRO07RR \
  --workers 16 --output-root "$S/reference_final"
"$P" -m ncei.swath run --cruises HNRO05RR --no-exclusions \
  --workers 4 --output-root "$S/hnro05rr_numeric"
"$P" -m ncei.swath points --cruise NT05-06 --output-root "$S/points"
"$P" "$T/compare_products.py"
"$P" -m unittest discover _common/tests
```

| PRD | 原文件输入与参考产品（路径相对 `R`） | 新结果与差异 |
| --- | --- | --- |
| 1 | NT05-06，data2，38 个 MB84 源文件及原 `.prj`；`first_batch/NT05-06/file_cells_1min/nt05-06__mb84.parquet` 与 `extraction_manifest.parquet` | 86 格 × 23 列，差异 0 行、0 列；逐文件选入数差异 0/38，filekey、序号差异 0 |
| 2a | HNRO05RR，data2，17 个 MB41 源文件；`navigation_affected_extension/HNRO05RR/file_cells_1min/hnro05rr__mb41.parquet` | 无排除：465,699 选点、278 格；23 列差异 0 行、0 列 |
| 2b | 同上，加默认精确 ping 排除；`navigation_review_hnro05rr/HNRO05RR/file_cells_1min/hnro05rr__mb41.parquet` | 排除 709 个原选点；464,990 选点、251 格；23 个正式列差异 0 行、0 列 |
| 3 | HNRO07RR，data2，502 个 MB41 源文件，加默认精确 ping 排除；`navigation_review/HNRO07RR/file_cells_1min/hnro07rr__mb41.parquet` | 排除 1,634 个原选点；36,433,396 选点、18,268 格；23 个正式列差异 0 行、0 列 |
| 4 | `points` 重新读取 NT05-06 的 38 个原文件；`first_batch/NT05-06/points_checked/nt05-06__mb84.parquet` | 1,526,490 行 × 36 列，差异 0 行、0 列；字段类型及 Arrow 空值计数差异 0 |
| 5 | RR0913、Tier B 的 EW9908 与 AT15-51、data1 上 Tier C 的 COOK17MV | 4 航次完成，见试运行表 |
| 6 | 产出均在 `S`；`python -m unittest discover _common/tests` | 59 项通过，记录 `S/unittest.log` |

2b、3 的参考表独有 `selection_policy`、`navigation_case_review_affected` 两列；新产品按批准的 23 列写出，策略记录在 `run_parameters.json`。默认排除表有 19 个 ping，HNRO14RR 敏感性表有 11,816 个精确声束键。`S/comparison.json` 保留逐列差异。NT05-06 强制分为 4 组完整网格重新聚合，23 列值与不分区结果相同，产物 `S/NT05-06_partitioned.parquet`。

## 试运行和容量

实际调用如下。`measure_trial.py` 调用同一个 `ncei.swath run` 命令，每 0.2 秒采样临时目录；航次耗时取 `cruises.parquet`。GB 为 10⁹ bytes，原文件列包含逐文件清单中的不支持文件。

```bash
"$P" "$T/measure_trial.py" trial_rr0913 8 RR0913
"$P" "$T/measure_trial.py" trial_ew9908 4 EW9908
"$P" "$T/measure_trial.py" trial_at15_51 4 AT15-51
"$P" "$T/measure_trial.py" trial_cook17mv 4 COOK17MV
```

| 航次 | 来源 / 格式 | 原文件数 | 原文件 GB | 声束 | 选入 | L2 格 | 航次秒 | 临时峰值 GB |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| RR0913 | data2 / MB58 | 113 | 2.404 | 25,528,176 | 23,801,097 | 17,181 | 364.11 | 0.849 |
| EW9908 | Tier B / MB21 | 29 | 0.105 | 12,689,307 | 11,376,871 | 3,666 | 98.74 | 0.301 |
| AT15-51 | Tier B / MB41 | 25 | 0.052 | 1,473,307 | 1,174,971 | 826 | 19.62 | 0.046 |
| COOK17MV | Tier C / MB32 | 9 | 0.021 | 4,721,662 | 4,435,581 | 11,111 | 30.31 | 0.223 |

RR0913 的 113 文件含一个 0.173 GB 的 MB164 文件，记录为不支持。实际解码 112 个 MB58 文件，共 2.230 GB。16 和 32 workers 在同机依次重跑同一航次，分别用下面的命令，L2 格数和选入数均与 8 workers 一致。CPU 平均值由进程及子进程累计 CPU 秒除以墙钟秒得到，峰值和进程树 RSS 为 0.2 秒采样；RSS 合计包含进程间共享页。

```bash
"$P" "$T/measure_trial.py" benchmark_rr0913_16 16 RR0913
"$P" "$T/measure_trial.py" benchmark_rr0913_32 32 RR0913
```

| workers | 墙钟秒 | 解码输入 MB/s | CPU 平均 / 峰值核数 | 进程树 RSS 峰值 GB | 临时峰值 GB |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 8（首轮，期间有其他读取） | 367.43 | 6.07 | 未采样 | 未采样 | 0.849 |
| 16 | 132.42 | 16.84 | 4.08 / 16.70 | 5.58 | 1.712 |
| 32 | 97.13 | 22.96 | 5.86 / 31.77 | 9.04 | 2.197 |

`run` 每次只处理一个航次，workers 并行的是航次内源文件。当前台账 2,073 航次、12.170 TB，按后缀统计受支持源文件 8.958 TB、365,484 文件，MB58 占 8.379 TB，见 `S/ledger_format_estimate.json`。按 RR0913 复跑吞吐，8.958 TB 在 16/32 workers 下约需 **6.2/4.5 天**；若 14 TB 均需解码，约 **9.6/7.1 天**。首轮较慢的实际读盘条件表明墙钟估算会随缓存和主机负载变化。

RR0913 L2 为 1.57 MB。按格式样本和 MB58 占比外推，持久产物约 **7–10 GB**；最大已知受支持原文件量是 2009_Amundsen 的 272.4 GB，按 RR0913 的临时字节比率，16/32 workers 的单航次临时峰值约 **209/268 GB**。两者相加约 **220/280 GB**。这是外推值；当前 data2 可用约 1.33 TB，启动下一航次前按 300 GB 余量检查。大航次按完整网格拆分后调用共享聚合器，避免全航次同时进入一次内存聚合。

## 多格式与独立工作树

多种受支持格式按逐文件源 ping 时间区间并集求交；有交叠的航次状态为 `format_overlap`，不写 L2。现有 staging 的 `time_us` 只覆盖下表，无法判断三例的跨格式交叠。区间全表保存在 `S/mixed_format_staging_summary.json`；逐文件结果为 `S/mixed_format_staging_files.parquet`。本次未解码这三个航次。

| 航次 | 历史清单文件 | 可读 staging | 缺 staging | 可读 UTC 范围 / 区间数 |
| --- | ---: | --- | --- | --- |
| NBP0603 | 510 | 无 | MB56 107，MB57 403 | 无 |
| TN253 | 121 | 无 | MB56 61，MB57 60 | 无 |
| HLY1102 | 1,301 | MB58 1,236 文件，649,528,560 声束 | MB56 54，MB58 11 | 2011-08-15 20:57:34.175 至 2011-09-28 15:50:06.426 / 1,222 |

独立工作树从 `1900142` 检出后只覆盖本次 swath 代码和 `_common/mbsystem.py`，仍使用该提交的 `ncei/trackline/file_cells.py`。命令在独立工作树根执行：

```bash
D=/mnt/data2/00-Data/ship
A="$D/ncei/derived/swath_rebuild_check"
"$P" -m ncei.swath run --cruises NT05-06 COOK17MV --workers 8 \
  --data-root "$D" --ledger "$D/ncei/manifests/round2_download_log.parquet" \
  --raw-root "$D/ncei/raw_round2/platforms_tree" \
  --raw-root /mnt/data1/pub/ship/ncei/raw_round2/platforms_tree \
  --exclude-pings "$A/reference_final/excluded_pings.parquet" --output-root "$A/worktree_run"
```

两航次退出 0，与上述 scratch L2 逐值相同；相同命令加 `--resume` 后退出 0，跳过两个航次。该工作树也用绝对输入完成选定 7 航次的 `census` 与正式 L2 的六区域 `coverage`。

## 改动和待决定事项

新增 `ncei/swath/{sources,decode,selection,exclusions,format_times,aggregation,source_summary,pipeline,points,cli}.py`，更新 `__main__.py`、`census.py`、`coverage.py`、README、`_common/mbsystem.py`、多波束测试与 `docs/code_archive.md`。删除 `ncei/swath/{batch,extract,file_cells,manifest_fragment,quality_revision,navigation_revision,navigation_review}.py` 和 SQLite staging 连接函数；归档注明 EW0202 外部脚本的历史调用。`seamount_candidate_delivery.py` 交 D 归档删除；本次不保留专用辅助模块。

建议主代理在共享主机负载与测速接近时用 32 workers；需与其他重 I/O 工作并行时用 16。全量先做 `census`，主代理决定不支持格式的处置；当前仍沿用旧链的格式支持集合，MB56 不进入受支持格式的交叠计算。若某航次有两个已支持格式的解码区间交叠，按该航次的 `format_overlap` 清单决定采用哪一套源记录。

## 全量运行

主机 `Precision-7920-Tower`，固定代码 `80965c7e550e031e43779fb90dc3cb170661d231`，工作树 `/mnt/data2/00-Data/ship_swath_rebuild_f1f82a4`。共享 trackline 聚合器仍为 `1900142` 版本。首次普查发现历史空提取清单缺格式列；`80965c7` 修订后 65 项测试通过。2026-11-12 读取的台账快照有 2,073 个 `platforms_tree`、`status=ok` 航次，零估计池记录未合入；`full_cruises.txt` 保存这批清单，RR0913 排首位。

以下命令在 Bash 中执行。输出根的 `excluded_pings.parquet` 和 `hnro14rr_sensitivity_beams.parquet` 由固定代码从原核对表生成，路径与 SHA-256 写入 `run_parameters.json`。单元 `swath-rebuild.service` 的标准输出和错误合并追加到 `swath_rebuild.log`；日志在首条输出时创建，以便运行入口先初始化输出根。

```bash
cd /mnt/data2/00-Data/ship_swath_rebuild_f1f82a4
D=/mnt/data2/00-Data/ship
O="$D/ncei/derived/swath_rebuild_20261112"
T="$D/.trellis/tasks/11-12-swath-streaming-rebuild"
P=/opt/miniforge3/envs/torch29/bin/python
mapfile -t cruises < "$T/full_cruises.txt"

export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 POLARS_MAX_THREADS=1
"$P" -u -m ncei.swath census \
  --data-root "$D" --ledger "$D/ncei/manifests/round2_download_log.parquet" \
  --raw-root "$D/ncei/raw_round2/platforms_tree" \
  --raw-root /mnt/data1/pub/ship/ncei/raw_round2/platforms_tree \
  --output-root "$O" --cruises "${cruises[@]}"

launch_swath() {
  systemd-run --user --unit=swath-rebuild --collect --expand-environment=no \
    --working-directory=/mnt/data2/00-Data/ship_swath_rebuild_f1f82a4 \
    --setenv=OPENBLAS_NUM_THREADS=1 --setenv=OMP_NUM_THREADS=1 \
    --setenv=MKL_NUM_THREADS=1 --setenv=NUMEXPR_NUM_THREADS=1 --setenv=POLARS_MAX_THREADS=1 \
    /bin/bash -e -o pipefail -c 'log=$1; shift; "$@" 2>&1 | while IFS= read -r line; do printf "%s\n" "$line" >> "$log"; done' \
    swath-log "$O/swath_rebuild.log" "$P" -u -m ncei.swath run \
    --data-root "$D" --ledger "$D/ncei/manifests/round2_download_log.parquet" \
    --raw-root "$D/ncei/raw_round2/platforms_tree" \
    --raw-root /mnt/data1/pub/ship/ncei/raw_round2/platforms_tree \
    --output-root "$O" --workers 32 "$@"
}

# 首次启动
launch_swath --cruises "${cruises[@]}"
# 单元退出或主机重启后，按原清单续跑
# launch_swath --resume --cruises "${cruises[@]}"
# 零估计池完成下载并合入台账后，补跑新增航次
# launch_swath --resume
```

普查结果：604,657 个候选源文件、10,683.439 GB。支持格式 365,267 文件、8,957.807 GB、1,546 航次；不支持 239,390 文件、1,725.633 GB、590 航次。两组航次可重叠。167 航次未找到当前枚举规则下的候选文件。各格式的文件数、原文件字节数和航次数见输出根 `census_summary.json`；未识别类别为 26,068 文件、781.286 GB、283 航次。

| 已识别不支持格式 | 文件数 | GB | 航次数 |
| --- | ---: | ---: | ---: |
| MB56 | 66,840 | 554.342 | 139 |
| MB94 | 39,053 | 246.385 | 72 |
| MB183 | 95,928 | 46.156 | 38 |
| MB163 | 806 | 31.603 | 7 |
| MB162 | 812 | 27.668 | 11 |
| MB43 | 5,790 | 12.128 | 17 |
| MB201 | 673 | 9.158 | 2 |
| MB164 | 55 | 6.125 | 54 |
| MB59 | 194 | 4.268 | 4 |
| MB51 | 655 | 3.799 | 6 |

单元于 2026-11-12 14:33:59 UTC 启动，invocation ID `34fb624105c74a67b6f92f3b344f1b18`，32 workers。`run_invocations.jsonl` 的首条记录包含 2,073 个航次，RR0913 排第一。输出根两张表分别为 19 个排除 ping、11,816 个敏感性声束键，SHA-256 均与 `run_parameters.json` 一致。

首航次 RR0913 于 2026-11-12 14:35:27 UTC 完成：25,528,176 声束、23,801,097 选点、17,181 格，航次耗时 86.53 秒。113 个候选文件含 1 个不支持的 MB164。L2、完成标记和临时目录清理均已核对，单元仍为 `active/running`。后续由主代理接管。
