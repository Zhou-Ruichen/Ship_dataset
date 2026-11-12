# NCEI trackline 重构对照

重构前代码以 `1900142` 为参照。命令从仓库根运行，Python 为
`/opt/miniforge3/envs/torch29/bin/python`，`OPENBLAS_NUM_THREADS`、
`OMP_NUM_THREADS`、`MKL_NUM_THREADS`、`NUMEXPR_NUM_THREADS`、
`POLARS_MAX_THREADS` 均为 1。样本写在
`ncei/derived/trackline_refactor_check/`（下文记作 `$S`）。
`run_samples.py` 为旧命令的固定输出目录重定向到 scratch，并通过现行
`ncei.trackline.__main__.main` 调用命令；`check_reference_drift.py` 使用
`git show 1900142:<path>` 复算发布样表不同的项目。`comparison_results.json`
记录每张表的行数、列、键、缺测与逐列差异。表中的“一致”指这些比较一致，
按需规范 scratch 路径，省去运行时间字段；观测时间参与比较，历史表时间精度
不同处单独标出。

| 命令（`python -m ncei.trackline`） | 样本和主要参数 | 对照结果 |
| --- | --- | --- |
| `manifest` | `--sample-n-files 2`；NC 86001211、ht860111，XYZ 72110803、at27a，保留全量清单的来源存在性 | 正式来源清单 4 个键及全部列一致；at27a 为多波束。 |
| `standardize-nc` | `--manifest <上述样表> --limit-files 2` | 两份点表 8,893、2,145 行逐列一致；与 `1900142` 同输入清单一致。发布 sample 清单仍为 v0.1，当前 v0.2 多 `n_clipped`。 |
| `standardize-xyz` | `--manifest <上述样表> --limit-files 2` | 单波束 5,439 行和多波束 709,927 行逐列一致；与 `1900142` 同输入清单一致。发布 sample 清单同样存在 v0.1/v0.2 差异。 |
| `clean-mrar` | `--sample-n-rows 1000`；每象限前 1,000 行 | 3,000 个测深点、空陆地表、4 行审计与 `1900142` 一致。现存 sample 是每象限 100,000 行；另按该参数复算，3 张表与发布样表一致。 |
| `point-qc` | `--sample-n-files 1`；NC 86001211、XYZ at27a、MRAR `0-90W-0-85S.txt`，传入筛选后的来源、L1 和 MRAR 清单 | 3 个正式 checked 产品逐列一致，MRAR 25,286,616 行。4 行清单与 `1900142` 同输入一致；现存 sample 采用不同的选择，1 行检查计数缺测不同，原样本有其他非空 `skip_reason`。 |
| `supplementary-qc` | `--sample-n-files 1`；同上，加 86001211 的 NC/XYZ 对 | 交集审计 1 行与发布样表一致；4 行清单与 `1900142` 同输入一致，发布 sample 的工作选择不同。 |
| `file-cells` | `--supplementary-manifest <筛选后的清单>`；上述 NC、XYZ、MRAR | 1,437、308、2,295,535 格与正式文件逐列一致；正式清单 3 行一致，sample 清单覆盖 2 行。 |
| `merge-cells` | `--input-manifest ncei/manifests/file_cells_1min_manifest.parquet`；发布样表的 50 个 SB、17 个 MB、3 个 MRAR 文件 | 三分支分别 124,550、5,960、9,019,383 格，与发布 sample 数据集和 3 行清单一致。 |
| `quality-policy` | 默认 `--run-label sample`；历史 sample 参数（分支内最多 50 文件、分支间最多 50,000 行/对），批准规则与冻结校准 | 58,388 个分支内残差、58,142 个分支间共址格、7,050 行质量标记及摘要与发布样表一致。跨分支重复率区间的历史标签空格保留。 |
| `validation-cells` | 默认 sample；按发布样表使用正式分支格、完整 sidecar、JAMSTEC 主验证格，按纬度分层采样 | 五类样表逐列一致：严格 8,808、扩展 8,954、补充 3,598、区域 5,000、目录 17,552 行。独立生成的旧 sample 分支格和 sample sidecar 键不闭合，采用实际发布样表的正式输入及 sample 选择。 |
| `regional-quality` | `lon068_lat018` 的角色表、原 bbox 和 margin、严格 MB、SB 格与点 | 偏差估计及 4 个控制表与发布样表一致。与 `1900142` 同输入的事件、配对、航线统计、区域统计和处置逐列一致。发布事件为 1,276，当前新旧代码均为 1,277；新增事件影响 2 条航线的交叉点统计和区域阈值。 |
| `global-bias` | odp130jr 的清单行、2387 个文件格及共址严格 MB | 偏差行和 2,387 个 adjusted 格值一致；小样本全缺测的 `survey_id` 物理类型是 null，完整表为 string。 |
| `global-crossover` | `lon000_lat010_sw_sw` 叶 tile，原 bbox 和 margin | 与 `1900142` 同输入的 2,496 个事件逐列一致。发布表 2,495 行，共同键的非时间列一致；当前时间为 ns，发布表为 ms。 |
| `global-disposition` | odp130jr、覆盖其事件的完整 10° 阈值格、相关调整格、全球偏差、六区硬质检 | odp130jr 的处置行和 2,387 个 final r2 格逐列一致。 |
| `global-grid` | `lat_band_10deg=0` 的完整严格 MB 和最终 SB 输入 | 1,226,872 格与发布分区逐列一致。 |
| `mgd77t-points` | `--workers 1 --tracks ar1-06 --no-legacy-comparison --output-root <scratch>`；另传保留分类清单复算 | 无分类时与独立检查产物逐列一致；有分类时与完整批次产物一致，旧点索引按参数保持缺测。338,605 条原观测、879 个来源质量格、1,000 个 basic 格。 |
| `mgd77t-crossovers` | `--source-points-root <发布点表> --output-root <scratch>`；`lon052_lat018`，两种选择 | 两种选择各 14 个候选、6,186 段、0 个有支持的交叉事件；事件、配对、航线、区域摘要逐列一致。 |
| `mgd77t-netcdf` | cntl01rr 的完整 `.m77t/.h77t`、旧 NC；分别单源、`--inventory "$S/inputs/faa_inventory.csv"` 和 `--verify-only` | 两个 NetCDF 的维度、变量类型、掩码、值及非运行时间属性与发布文件一致；237 个行映射及 49 项字段比较一致。旧 NC 236 行，源首行恢复；`--verify-only` 保留 NetCDF 和单航次映射的修改时间。 |
| `source-corrections` | `--product-root "$S/source-corrections"`；静态 AR1-06、cntl01rr、1 个 HNRO05RR 文件，加 1 个 RR1412 文件供既有摘要例证 | 四张指定表与 `1900142` 同输入逐列一致。与发布表按键对照，状态和证据值相同；子集全缺测的类型及样本内 SVP 编号不同。 |

区域额外事件为 `03973 × 2384`，坐标
`(162.26736046669794, 0.56009)`；全球叶 tile 额外事件为
`pd190l02 × rs8102`，坐标 `(-178.558684324839, -77.53221816648298)`。
重构前代码的区域样本为运行所需，仅在对照驱动中适配旧 Parquet 写入调用，
其几何、质量和处置计算原样执行。两条额外事件都由当前输入与重构前算法复现；
现存发布表保留原版本。

`compute_lat_band` 在多波束 5,960 个样本格上取值相同。merge/overlap
返回 `int64`，policy/validation 返回可空 `Int64`，保留各自实现。
`file_cells.aggregate_track_file` 的签名与函数体 AST 与 `1900142` 相同。
19 个子命令帮助均退出 0；顶层 `--help` 不导入计算模块。

`python -m unittest discover _common/tests` 最终运行 65 项，全部通过。
逐表对照差异由对应的历史产品版本或样本选择复现。主代理需确认两张
历史交叉点表以旧发布版本保留，并接受同输入的 `1900142` 对照作为本次
重构等价证据。现有产品未改写。
