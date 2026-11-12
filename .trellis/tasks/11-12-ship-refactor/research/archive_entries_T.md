# Trackline 归档条目

| 原路径 | 用途 | 产出产品或报告 | 最后包含提交（删除前 HEAD） |
| --- | --- | --- | --- |
| `ncei/trackline/policy_audit.py` | 探索并校准候选质量规则 | `ncei/derived/quality_policy_calibration_1min/` 下的校准表和候选规则；`ncei/docs/step06a_quality_policy_calibration_report.md` | `1900142929166fd19cd272ab02716e4ae4d73f22` |
| `ncei/trackline/mgd77t_xyz.py` | 旧静态 MGD77T 三列 XYZ 转换 | `ncei/raw_round2/mgd77t_static_xyz/` 与 `conversion_manifest.parquet` | `1900142929166fd19cd272ab02716e4ae4d73f22` |
| `ncei/trackline/mgd77t_fragments.py` | 默认 XYZ 分支生产独立点表、格网和来源清单；完整来源分支入口迁至 `mgd77t_points.py` | `ncei/derived/sb_round2_static/`；`sb_round2_static_source_manifest_fragment.parquet` | `1900142929166fd19cd272ab02716e4ae4d73f22` |
| `ncei/trackline/legacy_faa_revision.py` | 原 15 航次 FAA 重建、原字段对照、已用位置重映射及追加来源清点；显式清单转换迁至 `mgd77t_faa.py` | `ncei/derived/processing_revision_20261025/legacy_faa/`；`.trellis/tasks/10-25-ship-processing-repair/legacy_faa_result.md` | `1900142929166fd19cd272ab02716e4ae4d73f22` |
| `ncei/trackline/source_overlap.py` | 分支内文件格重叠残差，迁至 `quality_overlap.py` | `ncei/derived/overlap_bias_1min/`；`ncei/docs/step05a_source_specific_overlap_bias_report.md` | `1900142929166fd19cd272ab02716e4ae4d73f22` |
| `ncei/trackline/branch_overlap.py` | 分支间共址格深度对照，迁至 `quality_overlap.py` | `ncei/derived/cross_branch_overlap_1min/`；`ncei/docs/step05b_cross_branch_overlap_audit_report.md` | `1900142929166fd19cd272ab02716e4ae4d73f22` |
| `ncei/trackline/apply_policy.py` | 执行批准的质量规则，迁至 `quality_policy.py` | `ncei/derived/quality_flags_1min/`；`ncei/docs/step06b_cell_quality_flags_report.md` | `1900142929166fd19cd272ab02716e4ae4d73f22` |
| `ncei/trackline/mgd77t_source_fields.py` | 完整 MGD77T 来源字段、质量选择与历史对照，迁至 `mgd77t_points.py` | `ncei/derived/processing_revision_20261025/trackline/`；`.trellis/tasks/10-25-ship-processing-repair/mgd77t_result.md` | `1900142929166fd19cd272ab02716e4ae4d73f22` |
