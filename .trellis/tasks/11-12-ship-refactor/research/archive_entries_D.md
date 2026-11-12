# Archive entries — D

Pre-deletion HEAD: `1900142929166fd19cd272ab02716e4ae4d73f22` (`1900142`).
Purpose, `produced_results`, and `evidence` are taken from
`research/layout_inventory.tsv`. Reports, products, and figures remain in place.
`docs/code_archive.md` is left for the main agent to update.

| Path | Purpose | produced_results | evidence | Last containing commit |
|---|---|---|---|---|
| `ncei/analysis/14_validate_gridded_products_step08.py` | Step08 preflight/smoke/full model validation | strict/expanded global validation metrics | `ncei/analysis/14_validate_gridded_products_step08.py:L64-L99,L255-L263,L1310-L1386` | `1900142` |
| `ncei/analysis/15_strict_vs_expanded_compare_step08.py` | Step08 strict versus expanded sensitivity | strict/expanded coverage and RMSE comparison | `ncei/analysis/15_strict_vs_expanded_compare_step08.py:L46-L88,L670-L723` | `1900142` |
| `ncei/analysis/16_non_primary_coverage_diagnostics_step08.py` | Step08 non-primary coverage diagnostics | supplementary SB and regional MRAR diagnostics | `ncei/analysis/16_non_primary_coverage_diagnostics_step08.py:L64-L98,L785-L796` | `1900142` |
| `ncei/analysis/17_step08_final_global_validation_report.py` | Step08 final report and policy tables | Step08 final ranking/policy anchor | `ncei/analysis/17_step08_final_global_validation_report.py:L54-L65,L618-L630` | `1900142` |
| `ncei/analysis/18_step08_ranking_bootstrap.py` | paired cluster bootstrap ranking uncertainty | 1,000-iteration CIs/rank probabilities | `ncei/analysis/18_step08_ranking_bootstrap.py:L64-L99,L683-L775` | `1900142` |
| `ncei/analysis/19_step08_publication_tables.py` | Step08 publication tables | publication strict/comparison tables | `ncei/analysis/19_step08_publication_tables.py:L101-L151` | `1900142` |
| `ncei/analysis/20_step08_gapfill_error_structure.py` | Step08 gap-fill error attribution | gap-fill RMSE attribution | `ncei/analysis/20_step08_gapfill_error_structure.py:L51-L71,L621-L630` | `1900142` |
| `ncei/analysis/21_step08_publication_figures.py` | Step08 publication figures/data | six Step08 publication figures | `ncei/analysis/21_step08_publication_figures.py:L54-L65,L130-L166,L527-L592` | `1900142` |
| `ncei/analysis/22_step08_publication_summary.py` | Step08 publication summary/manifest | publication_ready_step08_summary.md | `ncei/analysis/22_step08_publication_summary.py:L48-L56,L401-L452,L457-L537` | `1900142` |
| `ncei/analysis/27_sb_crossover_network_bias_1min.py` | crossover-network constant-offset prototype | network 61.64 m versus Step23 23.86 m heldout median abs residual | `ncei/analysis/27_sb_crossover_network_bias_1min.py:L24-L31,L130-L142`; `.trellis/tasks/archive/2026-09/09-03-sb-network-bias-prototype/result.md:L21-L45` | `1900142` |
| `ncei/analysis/29_sb_interpolation_holdout.py` | GMT interpolation holdout for SB value | 1,840.89 -> 731.12 -> 673.19 m old-control pooled RMSE | `ncei/analysis/29_sb_interpolation_holdout.py:L36-L65,L430-L489`; `docs/数据产品规范与下游接入.md:L170-L180` | `1900142` |
| `ncei/analysis/seamount_candidate_delivery.py` | 58-seamount candidate point/90 km cell delivery | 29,356,223 delivered points and complete candidate-cell tables | `ncei/analysis/seamount_candidate_delivery.py:L30-L36,L664-L697`; `.trellis/tasks/10-21-mb-round2-quality-revision/result.md:L573-L610` | `1900142` |
| `_common/r2_calibration.py` | one-off R2 threshold calibration driver | calibration tables used to freeze classifier | `_common/r2_calibration.py:L39-L58,L298-L348` | `1900142` |
| `_common/calibration/r2_borderline.csv` | R2 borderline calibration table | 129-line calibration evidence | `_common/calibration/r2_borderline.csv:L1` | `1900142` |
| `_common/calibration/r2_borderline.png` | R2 calibration scatter figure | borderline density/bbox figure | `_common/calibration/r2_borderline.png (binary); _common/r2_calibration.py:L56-L58` | `1900142` |
| `_common/calibration/r2_calibration_summary.txt` | R2 calibration summary | frozen-threshold summary | `_common/calibration/r2_calibration_summary.txt:L1` | `1900142` |
| `_common/calibration/r2_hard_mb_files.csv` | hard multibeam calibration examples | 12 hard-MB records plus header | `_common/calibration/r2_hard_mb_files.csv:L1` | `1900142` |
| `_common/tests/fixtures/scs_v2_stage_c1/MGL1104-9999-eight-ping.mb58` | MB58 eight-ping binary fixture | archived SCS test input | `_common/tests/fixtures/scs_v2_stage_c1/MGL1104-9999-eight-ping.mb58:L1`; `_common/README.md:L45-L47` | `1900142` |
| `_common/tests/fixtures/scs_v2_stage_c1/golden_provenance.json` | SCS fixture provenance | archived SCS test input | `_common/tests/fixtures/scs_v2_stage_c1/golden_provenance.json:L1`; `_common/README.md:L45-L47` | `1900142` |
| `_common/tests/fixtures/scs_v2_stage_c1/synthetic_all_u3.tsv` | synthetic U3 listing fixture | archived SCS test input | `_common/tests/fixtures/scs_v2_stage_c1/synthetic_all_u3.tsv:L1`; `_common/README.md:L45-L47` | `1900142` |
| `_common/tests/fixtures/scs_v2_stage_c1/synthetic_good_u0.tsv` | synthetic U0 listing fixture | archived SCS test input | `_common/tests/fixtures/scs_v2_stage_c1/synthetic_good_u0.tsv:L1`; `_common/README.md:L45-L47` | `1900142` |
| `_common/tests/fixtures/scs_v2_stage_c1a/synthetic_invalid_time_u0.tsv` | invalid-time U0 fixture | archived SCS test input | `_common/tests/fixtures/scs_v2_stage_c1a/synthetic_invalid_time_u0.tsv:L1`; `_common/README.md:L45-L47` | `1900142` |
| `_common/tests/fixtures/scs_v2_stage_c1a/synthetic_invalid_time_u3.tsv` | invalid-time U3 fixture | archived SCS test input | `_common/tests/fixtures/scs_v2_stage_c1a/synthetic_invalid_time_u3.tsv:L1`; `_common/README.md:L45-L47` | `1900142` |
| `_common/tests/fixtures/scs_v2_stage_c1a/synthetic_missing_time_u3.tsv` | missing-time U3 fixture | archived SCS test input | `_common/tests/fixtures/scs_v2_stage_c1a/synthetic_missing_time_u3.tsv:L1`; `_common/README.md:L45-L47` | `1900142` |
