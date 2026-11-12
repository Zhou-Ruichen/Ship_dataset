# JAMSTEC 包化对照记录

## 设置

- 旧代码基准：`1900142929166fd19cd272ab02716e4ae4d73f22`。
- 新命令：`python -m jamstec.multibeam [--project-root ROOT] COMMAND`。
- Python：`/opt/miniforge3/envs/torch29/bin/python`。
- 数值库、OpenMP 和 Polars 均设单线程；未启动并行处理进程。
- scratch 根：`jamstec/multibeam/derived/refactor_check/`。
- 驱动：`research/jamstec_refactor_check.py`；每个命令的实际命令和输出在 scratch 根的 `<command>.log`。
- 逐产品结果：`derived/refactor_check/comparison_results.tsv`。

比较使用相同列顺序、dtype、行键和精确值；NaN/缺测位置必须一致。Parquet 字节、报告时间戳和运行时间不纳入比较。目标格聚合检查要求目标格的全部直接贡献文件在场，只比较这些目标格；文件在其他格产生的行不改变目标格参考集合。

## 每命令结果

| 命令 | 小输入与参考 | 对照产品数 | 对照行数合计 | schema / 行键 / 数值与缺测差异 |
|---|---|---:|---:|---|
| `extract` | 从保留来源包装一个 KR20-E07 外层 zip；参考 `docs/dat_manifest.tsv` 和正式原 DAT | 2 | 2 | 0 / 0 / 0；DAT SHA-256 也相同 |
| `manifest` | KR20-E07 与 KY11-02_leg1 两个完整小 subzip，17 个来源文件；参考正式 file/subzip manifest | 2 | 19 | 0 / 0 / 0 |
| `curate` | 完整 5,140 行 DAT 来源清单；参考正式 curated manifest | 1 | 5,140 | 0 / 0 / 0 |
| `standardize` | 上述 subzip 中 9 个纳入 DAT；逐文件参考正式 L1 与 points manifest | 10 | 2,772,713 | 0 / 0 / 0 |
| `point-qc` | 上述 9 份新 L1；逐文件参考正式 QC 点表与 manifest | 10 | 2,772,713 | 0 / 0 / 0 |
| `file-cells` | 上述 9 份新 QC 点表；参考正式逐文件格与 manifest | 10 | 3,999 | 0 / 0 / 0 |
| `merge-cells` | 3,936 个目标格及其 322 个直接贡献文件；参考正式 merged cells/manifest | 2 | 4,258 | 0 / 0 / 0 |
| `quality` | 05 的 50 文件 sample、06a sample、06b 正式清单；06c/06d 为 10 个大偏移格 + 10 个丢失格及直接贡献文件 | 15 | 51,770 | 0 / 0 / 0 |
| `validation-cells` | 上述 20 个目标格的原始/QC-filtered/comparison 表 | 2 | 30 | 0 / 0 / 0 |
| **合计** | 9 个命令 | **54** | — | **均为 0** |

行数合计只表示本次读取并对照的表规模，不是新增产品数量或科学计数。

### `quality` 分阶段覆盖

| 阶段 | 对照内容与行数 | 差异 |
|---|---|---:|
| 05 | 残差 23,909；file/cruise/subzip 汇总 49/45/47；suspicious cells 7 | 全部 0 |
| 06a | 候选残差 22,378；file/cruise audit 89/11；affected 11；推荐动作 TSV 逐字节相同 | 全部 0 |
| 06b | 正式 file-quality flags 5,083 行、21 列 | 全部 0 |
| 06c | 20 个目标格中保留的 10 格、36 列 | 全部 0 |
| 06d | common/lost/large-shift 各 10 格 | 全部 0 |

## 检查中发现并修正的问题

- TSV 配置最初把 KY12-08 的 `filename_contains=20120614` 读成浮点数，导致文件例外不匹配。两个配置读取现均固定字符串 dtype。KY09-09 断言原本已通过；失败的是随后的 KY12-08 断言。修复后动作和原 06a 相同。
- `curate` 的 `duplicate_group_id` 依赖全语料分组。为核对该列，curate 使用完整但仅 5,140 行的元数据表；后续点处理仍限于 9 个来源文件。
- 历史 `dat_manifest.tsv` 的绝对路径仍含改名前 `NCEI_multibeam`。extract 对照只把该已知前缀归一化为 `jamstec/multibeam`，再比较全部三列；没有改写历史文件。
- 第一次 merge 输入递归扩展了贡献网络。最终检查采用目标格的直接贡献文件，不扩大到这些文件的其他连通格。

## 测试

```text
python -m unittest discover _common/tests
Ran 65 tests in 1.840s
OK
```

另已验证 16 个生产/入口模块从 `/tmp` 隔离导入，以及 9 个命令和顶层 `--help` 均不触发处理。
