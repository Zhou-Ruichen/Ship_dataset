# 全球单波束最终产品（r2）

生成时间：2026-09-02T21:13:15Z  
输入航迹清单 SHA-256：`fb58e401ab483f17ed54d9a7edcc2fe39406102db10dd3caf683737cb6f8619c`

## 全球处置结果

| 处置 | 航迹数 |
| --- | ---: |
| `correct` | 32 |
| `keep_raw` | 4,764 |
| `revert_to_raw` | 23 |
| `reject` | 711 |
| `flag_large_unapplied_bias` | 3 |

质量表共 5,533 条航迹，与航迹清单中的单波束航迹 ID 数一致。
阈值按交叉点所在 10° 格计算：格内至少 100 个事件时使用该格全部交叉点的 NMAD；否则按 nc×nc、nc×xyz、xyz×xyz 分别使用 28.62、30.40、24.27 m。跨格航迹逐事件计算改正后绝对差与事件阈值之比；至少 10 个交叉点且该比值的中位数大于 1 时拒绝。表中的 `misfit_threshold_m` 是事件阈值中位数，供解释而不直接参与判定。

## 六区验证

odp130jr 保留六区验证结论 `revert_to_raw`；elt18 和 elt19 保留 `flag_large_unapplied_bias`。这三个局部验证结论优先于全局汇总证据；六区既有 hard-QC 拒绝均保持 `reject`。

| 六区表行数 | disposition 相同 | disposition 不同 |
| ---: | ---: | ---: |
| 247 | 199 | 48 |

其余差异来自 10° 格阈值、全局交叉点汇总、全局偏差估计或跨区域保留的 hard-QC 拒绝；完整的新旧证据列保存在六区核对表：

| 区域 | 航迹 | 六区处置 | 全球处置 | 全球理由 | 全球阈值 (m) |
| --- | --- | --- | --- | --- | ---: |
| lon068_lat018 | 03973 | correct | keep_raw | no_application_or_insufficient_evidence | 188.78 |
| lon068_lat018 | 82031605 | revert_to_raw | keep_raw | no_application_or_insufficient_evidence | 188.78 |
| lon068_lat018 | dme05-b | keep_raw | reject | post_correction_misfit_above_3x_global_tile_nmad | 131.24 |
| lon068_lat018 | dsdp07gc | revert_to_raw | keep_raw | no_application_or_insufficient_evidence | 188.78 |
| lon068_lat018 | erdc09wt | revert_to_raw | keep_raw | no_application_or_insufficient_evidence | 131.24 |
| lon068_lat018 | l884sp | correct | reject | post_correction_misfit_above_3x_global_tile_nmad | 188.78 |
| lon068_lat018 | mw9302 | revert_to_raw | keep_raw | no_application_or_insufficient_evidence | 131.24 |
| lon068_lat018 | mw9410 | revert_to_raw | keep_raw | no_application_or_insufficient_evidence | 104.32 |
| lon068_lat018 | p13c2 | correct | keep_raw | no_application_or_insufficient_evidence | 64.96 |
| lon068_lat018 | rc1712 | keep_raw | reject | post_correction_misfit_above_3x_global_tile_nmad | 64.96 |
| lon052_lat018 | circ05ar | reject | keep_raw | no_application_or_insufficient_evidence | 139.23 |
| lon052_lat018 | jr359 | correct | keep_raw | no_application_or_insufficient_evidence | 38.33 |
| lon052_lat018 | kh7605 | reject | keep_raw | no_application_or_insufficient_evidence | 127.69 |
| lon052_lat018 | kn145l7 | revert_to_raw | keep_raw | no_application_or_insufficient_evidence | 147.85 |
| lon052_lat018 | odp116jr | correct | keep_raw | no_application_or_insufficient_evidence | 38.33 |
| lon052_lat018 | rc0909 | keep_raw | reject | six_region_hard_qc_reject_retained | 106.28 |
| lon052_lat018 | rc1708 | keep_raw | reject | post_correction_misfit_above_3x_global_tile_nmad | 92.52 |
| lon052_lat018 | rc2706 | keep_raw | reject | post_correction_misfit_above_3x_global_tile_nmad | 146.70 |
| lon052_lat018 | v3405 | keep_raw | revert_to_raw | applied_but_post_worse_than_raw | 38.33 |
| lon052_lat018 | v3616 | keep_raw | reject | post_correction_misfit_above_3x_global_tile_nmad | 25.97 |
| lon052_lat018 | vit31b | reject | keep_raw | no_application_or_insufficient_evidence | 144.01 |
| lon058_lat012 | a2015l04 | correct | keep_raw | no_application_or_insufficient_evidence | 106.28 |
| lon058_lat012 | antac7 | reject | keep_raw | no_application_or_insufficient_evidence | 128.55 |
| lon058_lat012 | ga-0096 | keep_raw | reject | post_correction_misfit_above_3x_global_tile_nmad | 29.58 |
| lon058_lat012 | jare29l1 | keep_raw | reject | post_correction_misfit_above_3x_global_tile_nmad | 127.69 |
| lon058_lat012 | lusi03ho | keep_raw | revert_to_raw | applied_but_post_worse_than_raw | 29.58 |
| lon058_lat012 | lusi6car | keep_raw | revert_to_raw | applied_but_post_worse_than_raw | 106.28 |
| lon058_lat012 | um69 | reject | keep_raw | no_application_or_insufficient_evidence | 127.69 |
| lon058_lat012 | vit31a | reject | keep_raw | no_application_or_insufficient_evidence | 102.50 |
| lon059_lat015 | a2015l04 | correct | keep_raw | no_application_or_insufficient_evidence | 106.28 |
| lon059_lat015 | dodo05ar | keep_raw | correct | applied_improves_or_stays_low | 29.58 |
| lon059_lat015 | ga-0096 | keep_raw | reject | post_correction_misfit_above_3x_global_tile_nmad | 29.58 |
| lon059_lat015 | jare29l1 | keep_raw | reject | post_correction_misfit_above_3x_global_tile_nmad | 127.69 |
| lon059_lat015 | jare32l1 | reject | keep_raw | no_application_or_insufficient_evidence | 127.69 |
| lon059_lat015 | jr359 | correct | keep_raw | no_application_or_insufficient_evidence | 38.33 |
| lon059_lat015 | kh7201 | correct | keep_raw | no_application_or_insufficient_evidence | 127.69 |
| lon059_lat015 | lusi03ho | keep_raw | revert_to_raw | applied_but_post_worse_than_raw | 29.58 |
| lon059_lat015 | odp179jr | keep_raw | correct | applied_improves_or_stays_low | 209.51 |
| lon059_lat015 | v2819 | correct | keep_raw | no_application_or_insufficient_evidence | 29.58 |
| lon004_lat033 | he0302 | reject | keep_raw | no_application_or_insufficient_evidence | 160.10 |
| lon004_lat033 | hly0602 | reject | keep_raw | no_application_or_insufficient_evidence | 56.18 |
| lon004_lat033 | scicex93 | keep_raw | correct | applied_improves_or_stays_low | 101.13 |
| lon004_lat033 | scicex97 | reject | keep_raw | no_application_or_insufficient_evidence | 56.18 |
| lon004_lat033 | sub6672b | reject | revert_to_raw | applied_but_post_worse_than_raw | 347.61 |
| lon004_lat033 | sub7382h | reject | keep_raw | no_application_or_insufficient_evidence | 56.18 |
| lon004_lat033 | sub9300b | reject | keep_raw | no_application_or_insufficient_evidence | 72.81 |
| lon021_lat010 | 19910031 | keep_raw | reject | post_correction_misfit_above_3x_global_tile_nmad | 246.10 |
| lon021_lat010 | elt24 | reject | keep_raw | no_application_or_insufficient_evidence | 178.63 |

六区最终控制表：

| 区域 | MB 行 | SB 行 | 总行数 |
| --- | ---: | ---: | ---: |
| lon068_lat018 | 2148 | 3689 | 5837 |
| lon052_lat018 | 1538 | 6485 | 8023 |
| lon058_lat012 | 1781 | 7366 | 9147 |
| lon059_lat015 | 7088 | 6121 | 13209 |
| lon004_lat033 | 1051 | 6609 | 7660 |
| lon021_lat010 | 938 | 7942 | 8880 |

## 下游使用

有严格多波束格子的地方使用严格多波束；其余位置读取 `ncei/derived/singlebeam/file_cells_1min_final_r2/`，并过滤 `track_disposition != 'reject'`。
最终格子产品没有删除任何输入行。`correct` 保留偏差改正，`revert_to_raw` 恢复原始深度，其他处置保留进入本阶段时的适用值；被拒航迹仍在产品内，供审计和重新判断。
