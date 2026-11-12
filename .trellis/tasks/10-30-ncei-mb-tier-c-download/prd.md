# NCEI 多波束 Tier C 下载（data1）

## 问题

data2 只剩 1.3 TiB，装不下 Tier C。用户新申请 `/mnt/data1/pub/ship`（盘余 9.8 TiB，共享盘）。本任务决定 Tier C 的下载范围并完成下载；入库（stage 32/33/41/34）另批执行。

## 输入

- 队列：`ncei/derived/mbbdb_value_ranking/order_tier_C_queue.tsv`，1,154 航次，目录口径 4,596.3 GB，按目录字节升序。来自 `order_tier_C.tsv` 的 1,158 航次，剔除第一批已下的 AII8L18、COOK09MV、HNRO05RR、TN168。
- 工具：`ncei/code/41_tier_a_gapfill.py`，本次新增 `--raw-root` 与 `--queue-order`，默认行为不变。
- 落盘：`/mnt/data1/pub/ship/ncei/raw_round2/platforms_tree/<surveyId>/`，布局与 data2 相同。
- 工作目录：`/mnt/data1/pub/ship/ncei/_work/tierC_gapfill/`（列表缓存、`todo.json`、`download-*.jsonl`、日志、`supervise.sh`）。
- 台账：`ncei/manifests/round2_download_log.parquet`（data2），`worker=tierC-gapfill` 的记录对应 data1 上的文件。

## 决策

下载 Tier C 全量，不按估计密度切尾。

- 空间够用。2026-10-30 清点远端 1,153 个航次，1,163,967 个文件，5.15 TiB（5,658 GB）；2 个航次的列表仍有失败，守护循环每轮重列。下载后 data1 约余 4.6 TiB。
- 估计密度不能用来切尾。第一批 13 个已入库航次实测严格层外新格 89,779 个、下载 17.39 GB，合 5,163 格/GB，step16 锚点为 816.5 格/GB。估计大于 0 的 11 个航次估 5,744 格、实测 45,498 格，实测/估计中位数 7.6。估计密度最低的 PD20IB02（54 格/GB）与 RR1412（221 格/GB）实测分别为 863 与 751 格/GB（按台账字节）。第一批是日本方向定向选取，这组比值不外推到全球，只说明估计密度的排序不足以支撑舍弃尾部。
- 下载顺序按整航次走（`--queue-order`），小航次先完成。下载中止时得到的是完整航次，与入库要求一致。
- 保留 `.fbt/.fnv`（426 GB，占文件数 40%）。提取链不用它们，保留后布局与 Tier A/B 一致，完整性审计口径不变。

耗时按 Tier B 的 6.9 MB/s 估约 9.5 天。

## 运行

- 主机 Precision-7920-Tower，systemd 用户单元 `tierc-gapfill.service`，cgroup 独立于 `paseo.service`。Tier B 在 10-28 被外因杀死时用的是 `nohup`，进程留在 `paseo.service` 的 cgroup 内。
- 启动（重启主机或单元退出后同样用这条，已完成文件自动跳过）：

  ```bash
  W=/mnt/data1/pub/ship/ncei/_work/tierC_gapfill
  systemd-run --user --unit=tierc-gapfill --property=StandardOutput=append:$W/supervise.out --property=StandardError=append:$W/supervise.out /bin/bash $W/supervise.sh
  ```

- 查看：`systemctl --user status tierc-gapfill`；进度在 `$W/supervise.log` 与 `$W/download.out`。
- 停止：`systemctl --user stop tierc-gapfill`，之后手动执行一次 `--stage merge`（参数同 `supervise.sh` 的 `COMMON`），否则本轮记录不进台账。
- 自动停止条件：data1 余量低于 3 TiB（下载中每分钟检查），或连续 3 轮剩余文件数不减。

## 完成核对

- `supervise.log` 剩余 0，或停止时的剩余文件全部归因（如服务器端 403）。
- `trees.json` 无 `error` 记录。剩余 0 只覆盖列表成功的目录。
- 台账 `worker=tierC-gapfill` 覆盖全部有远端文件的航次。
- 写 `ncei/derived/mb_round2/_runs/tierC_download_record.md`，格式同 Tier B 记录。

## 已知缺口

- RC0126（Rachel Carson，2024，目录 21.3 GB，估计 5,886 格）：2026-10-30 实时核对 `rachel_carson/` 目录无此航次，平台树下载不到。

## Tier C 结果（主代理 2026-11-12 核对）

- 2026-11-08 19:55 守护循环结束，剩余 0；systemd 单元已退出。台账 `worker=tierC-gapfill` 1,209,513 个 ok 文件、5,662.4 GB、1,153 航次，全台账 2,503,040 行。
- `trees.json` 唯一 error：NF-11-04-NC 的 `data/version1/MB/em1002/nonpublic/` 列表失败，其余 195 个文件已下。RC0126 远端不存在。
- 未完成：`ncei/derived/mb_round2/_runs/tierC_download_record.md`。

## 零估计池追加（用户 2026-11-12）

用户决定：1990 年之前的航次不下载；追加零估计池中 1990 年及以后、台账无 ok 记录的航次。主代理按 `ranking_full.parquet` 与台账计得 247 航次、目录 1,374.6 GB（1990 年代 38、2000 年代 69、2010 年代 82、2020 年代 58）。落 data1 同一平台树，工具与守护循环沿用 Tier C 的 `41_tier_a_gapfill.py`，tag `zeropool-gapfill`，工作目录 `/mnt/data1/pub/ship/ncei/_work/zeropool_gapfill/`，3 TiB 余量停止条件不变。

下载结束后：写 Tier C 与零估计池两份下载记录；台账 `.bak-*` 备份只保留最新一个及记录中点名的两个（`bak-20261029-063250`、`bak-20261030-211121`），其余删除（用户已同意）；之后把 `--raw-root`、`--queue-order` 移植进 `ncei.download`，按 `10-21-repo-reorganization/research/downloader_check.md` 的对照完成切换，归档 `ncei/code/` 的四个旧下载脚本。负责人 D（pi k3.1-pro）。

## 后续

- 入库：`ncei/swath/`、`32_mb_round2_completeness.py`、`41_gzip_preflight.py` 等把 `ncei/raw_round2/platforms_tree` 写死在 data2，Tier C 入库前需要逐航次符号链接或把根目录参数化。
- Tier C 之外：第一批中 EW9508、PPTU11WT 的估计为 0，实测 44,281 格，占第一批逐航次合计的 49%。零估计池 214 航次、目录 1,581.7 GB，其中 1990 年代及更早 49 航次、20.6 GB。是否追加待用户决定，建议先下这 49 航次。
- `ncei/manifests/` 有 846 个台账备份、共 99 GB，绝大部分是 Tier B 末段空转产生，待用户决定是否清理。

## 状态

- 2026-11-12：零估计池追加与收尾派给 D = paseo agent 71b7c2ef（pi k3.1-pro）。
- 2026-11-12 D 阶段 A 完成，主代理核对：队列 247 航次、1,374.6 GB（`order_zero_pool_queue.tsv`，tier Z，rank 空）；`zeropool-gapfill.service` active，首轮 diff 366,372 文件、186 航次、1,707.3 GB（远端实际体量）。未解析平台目录的 60 个航次全部是 Fugro 商业测量船（Supporter 18、Gauss 16、Equator 14 等），目录口径体量为 0 GB，平台树下没有可下文件，记为缺口；NF1906 列表失败，循环重列。下载后 data1 约余 3.05 TiB，接近 3 TiB 停止线，末段可能触发停止。`ncei.download` 已移植 `--raw-root`/`--queue-order`，18 项测试通过，副本对照 diff/sha256/merge 一致（`/tmp/download_check/phaseA/results.json`）。Tier C 记录已写。阶段 B 等循环结束。
