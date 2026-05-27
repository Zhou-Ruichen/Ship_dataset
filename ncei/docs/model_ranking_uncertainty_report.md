# Model Ranking Uncertainty Report

Generated: 2026-05-27T19:50:21.954525+00:00
Status: **PASS**
Elapsed: 10.2s
Run label: `a_ranking`

## 1. Summary
GEBCO_2024 vs ETOPO_2022 ΔRMSE (GEBCO − ETOPO) point=-1.1834 m, 95% CI [-4.2817, 0.1629] m; the adjacent-pair difference is not significant at 95%, with GEBCO_2024 lower in 90.6% of bootstrap iterations.

Strict-primary point estimates used for ranking:

| model | MAE | RMSE | wRMSE |
| --- | --- | --- | --- |
| ETOPO_2022 | 22.5683 | 91.6099 | 70.0648 |
| GEBCO_2024 | 21.2602 | 90.4265 | 68.5825 |
| SDUST_2023 | 33.0913 | 99.9411 | 79.9667 |
| SRTM15_V2.7 | 22.1532 | 93.7345 | 72.5505 |
| TOPO_25.1 | 25.2426 | 97.3126 | 76.7194 |

## 2. Method
This task reads the five strict-primary by-cell residual parquets and validates that all files contain the same 2,398,774 `cell_id` values, `validation_weight`, and `region_10deg` assignments. It then computes paired cluster bootstrap intervals using `region_10deg` as the resampling unit.

Bootstrap settings: B=1,000, seed=20260528, clusters=124. Each iteration samples 124 clusters with replacement and recomputes RMSE, MAE, weighted RMSE, pairwise ΔRMSE, and rankings from per-cluster sufficient statistics. No validation row is filtered by residual magnitude.

## 3. Ranking stability by RMSE
| model | rank_1 | rank_2 | rank_3 | rank_4 | rank_5 |
| --- | --- | --- | --- | --- | --- |
| GEBCO_2024 | 0.9050 | 0.0950 | 0.0000 | 0.0000 | 0.0000 |
| ETOPO_2022 | 0.0940 | 0.8200 | 0.0830 | 0.0030 | 0.0000 |
| SRTM15_V2.7 | 0.0010 | 0.0850 | 0.9140 | 0.0000 | 0.0000 |
| TOPO_25.1 | 0.0000 | 0.0000 | 0.0030 | 0.9670 | 0.0300 |
| SDUST_2023 | 0.0000 | 0.0000 | 0.0000 | 0.0300 | 0.9700 |

## 4. Ranking stability by weighted RMSE
| model | rank_1 | rank_2 | rank_3 | rank_4 | rank_5 |
| --- | --- | --- | --- | --- | --- |
| GEBCO_2024 | 0.9540 | 0.0460 | 0.0000 | 0.0000 | 0.0000 |
| ETOPO_2022 | 0.0460 | 0.8750 | 0.0760 | 0.0030 | 0.0000 |
| SRTM15_V2.7 | 0.0000 | 0.0790 | 0.9210 | 0.0000 | 0.0000 |
| TOPO_25.1 | 0.0000 | 0.0000 | 0.0030 | 0.9720 | 0.0250 |
| SDUST_2023 | 0.0000 | 0.0000 | 0.0000 | 0.0250 | 0.9750 |

## 5. Pairwise ΔRMSE confidence intervals
`delta = RMSE(model_a) - RMSE(model_b)`, so negative means `model_a` has lower RMSE.

| model_a | model_b | delta_point | delta_rmse_p2.5 | delta_rmse_p50 | delta_rmse_p97.5 | delta_rmse_mean | p_a_better | significant_at_95pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEBCO_2024 | SDUST_2023 | -9.5146 | -14.6494 | -9.5525 | -6.7281 | -9.8576 | 1.0000 | 1 |
| ETOPO_2022 | SDUST_2023 | -8.3313 | -13.4305 | -8.3164 | -4.9412 | -8.5551 | 1.0000 | 1 |
| GEBCO_2024 | TOPO_25.1 | -6.8861 | -10.2799 | -7.0013 | -4.3199 | -7.0653 | 1.0000 | 1 |
| SRTM15_V2.7 | SDUST_2023 | -6.2067 | -10.8316 | -6.2660 | -3.8054 | -6.5030 | 1.0000 | 1 |
| ETOPO_2022 | TOPO_25.1 | -5.7027 | -9.5129 | -5.7118 | -1.9600 | -5.7628 | 0.9970 | 1 |
| SRTM15_V2.7 | TOPO_25.1 | -3.5781 | -5.8354 | -3.6431 | -2.1548 | -3.7107 | 1.0000 | 1 |
| GEBCO_2024 | SRTM15_V2.7 | -3.3080 | -5.1986 | -3.3308 | -1.8110 | -3.3546 | 0.9990 | 1 |
| TOPO_25.1 | SDUST_2023 | -2.6286 | -6.8641 | -2.6319 | 0.1129 | -2.7923 | 0.9700 | 0 |
| ETOPO_2022 | SRTM15_V2.7 | -2.1246 | -4.7355 | -2.2144 | 1.3651 | -2.0521 | 0.9140 | 0 |
| GEBCO_2024 | ETOPO_2022 | -1.1834 | -4.2817 | -1.1145 | 0.1629 | -1.3025 | 0.9060 | 0 |

## 6. Model metric confidence intervals
| model | metric | point_estimate | p2.5 | p50 | p97.5 | boot_mean | ci_covers_point |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GEBCO_2024 | RMSE | 90.4265 | 68.0373 | 89.6566 | 108.0326 | 89.3089 | 1 |
| ETOPO_2022 | RMSE | 91.6099 | 70.6911 | 90.9588 | 108.6991 | 90.6114 | 1 |
| SRTM15_V2.7 | RMSE | 93.7345 | 72.1912 | 93.0334 | 111.0682 | 92.6635 | 1 |
| TOPO_25.1 | RMSE | 97.3126 | 76.0648 | 96.5422 | 114.0530 | 96.3743 | 1 |
| SDUST_2023 | RMSE | 99.9411 | 82.0152 | 99.2193 | 115.2443 | 99.1666 | 1 |
| GEBCO_2024 | MAE | 21.2602 | 17.1053 | 21.2035 | 24.7910 | 21.0767 | 1 |
| ETOPO_2022 | MAE | 22.5683 | 18.7222 | 22.4660 | 26.1356 | 22.4522 | 1 |
| SRTM15_V2.7 | MAE | 22.1532 | 17.9350 | 22.0686 | 25.9701 | 22.0278 | 1 |
| TOPO_25.1 | MAE | 25.2426 | 20.4849 | 25.2532 | 29.7230 | 25.1677 | 1 |
| SDUST_2023 | MAE | 33.0913 | 29.7884 | 33.0755 | 36.2650 | 33.0637 | 1 |
| GEBCO_2024 | wRMSE | 68.5825 | 52.7590 | 67.9122 | 81.3393 | 67.8808 | 1 |
| ETOPO_2022 | wRMSE | 70.0648 | 55.7138 | 69.5820 | 82.4571 | 69.4993 | 1 |
| SRTM15_V2.7 | wRMSE | 72.5505 | 57.3630 | 72.0131 | 85.1266 | 71.8953 | 1 |
| TOPO_25.1 | wRMSE | 76.7194 | 61.9672 | 76.2822 | 89.6101 | 76.1935 | 1 |
| SDUST_2023 | wRMSE | 79.9667 | 68.1779 | 79.4817 | 91.1957 | 79.6126 | 1 |

## 7. Safety checks
Safety status counts: {'PASS': 19}

| check_id | description | status | observed | expected |
| --- | --- | --- | --- | --- |
| paired_n_cells | Paired strict-primary residual matrix preserves all input cells | PASS | 2,398,774 | 2,398,774 |
| paired_n_models | Residual matrix has five strict-primary global models | PASS | 5 | 5 |
| cell_id_unique | Reference cell_id values are unique | PASS | 0 | 0 |
| no_nan_residuals | No NaN/inf values in the N x 5 residual matrix | PASS | 0 | 0 |
| no_nan_weights | No NaN/inf validation_weight values | PASS | 0 | 0 |
| n_clusters | Cluster bootstrap uses 124 region_10deg clusters | PASS | 124 | 124 |
| cluster_min_positive | Every region_10deg cluster has at least one cell | PASS | 2 | >0 |
| weight_range | Strict-primary validation weights remain within the expected [0.4, 1.0] range | PASS | 0.4000..1.0000 | 0.4..1.0 |
| weight_region_independent | validation_weight and region_10deg are identical across model copies | PASS | weight_mismatches=0; region_mismatches=0 | 0; 0 |
| no_join_row_loss | Any paired inner-join fallback retained all cells | PASS | GEBCO_2024=2398774; ETOPO_2022=2398774; SRTM15_V2.7=2398774; TOPO_25.1=2398774; SDUST_2023=2398774 | 2,398,774 |
| reproducible_seed | Bootstrap seed is recorded and fixed by CLI | PASS | 20,260,528 | non-null |
| input_hashes_recorded | SHA256 hash recorded for every model input | PASS | 5 | 5 |
| input_hash_GEBCO_2024 | Input SHA256 recorded for GEBCO_2024 | PASS | 1067a51b60b7ff88ed2ea981536e6349a8de7a0deb7f3de75e9c2b98b9da686f | 64 hex chars |
| input_hash_ETOPO_2022 | Input SHA256 recorded for ETOPO_2022 | PASS | d768caae068af5713d45b897b0a706183e58a9d4aacef6bcc117691a67f798c5 | 64 hex chars |
| input_hash_SRTM15_V2.7 | Input SHA256 recorded for SRTM15_V2.7 | PASS | 2681a967e972e8b55176a8ca53a40de9febf4a9e93a6550950f1055132ee0938 | 64 hex chars |
| input_hash_TOPO_25.1 | Input SHA256 recorded for TOPO_25.1 | PASS | c31e3edde8d652de89fc429fbec8fe5560702a8517849b1f1c2f9f58dfbcab77 | 64 hex chars |
| input_hash_SDUST_2023 | Input SHA256 recorded for SDUST_2023 | PASS | a8089ac781dd1bc0765b5a475311c6843f83c8731168e05ae844ea360f38adda | 64 hex chars |
| no_residual_filter | No cells were filtered by residual magnitude; row count equals strict-primary input count | PASS | 2,398,774 | 2,398,774 |
| ci_covers_point | All 15 model/metric point estimates are inside their 95% bootstrap percentile CI | PASS | 15/15 | 15/15 |

## 8. Caveats
- The cluster bootstrap has 124 clusters with highly uneven cell counts (min=2, max=267,406); intervals therefore reflect the influence of the largest 10-degree regions.
- The analysis is strict-primary only (N=2,398,774) and excludes expanded-primary, supplementary singlebeam, regional MRAR, and SWOT_T1 products by task scope.
- Percentile intervals are used; BCa or moving-block bootstrap variants are out of scope for this task.

## 9. Reproducibility and output paths
| key | value |
| --- | --- |
| generated_utc | 2026-05-27T19:50:21.830406+00:00 |
| python | 3.12.10 \| packaged by conda-forge \| (main, Apr 10 2025, 22:21:13) [GCC 13.3.0] |
| platform | Linux-6.8.0-63-generic-x86_64-with-glibc2.39 |
| pandas | 2.3.3 |
| numpy | 2.3.3 |
| pyarrow | 24.0.0 |
| repo_root | /mnt/data2/00-Data/ship |
| data_repo_root | /mnt/data2/00-Data/ship |
| input_dir | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_full_strict_primary |
| output_dir | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty |
| run_label | a_ranking |
| bootstrap_iters | 1000 |
| seed | 20260528 |
| confirm_bootstrap | True |
| overwrite | True |
| check_only | False |
| diagnose_convergence | False |
| elapsed_seconds | 10.223 |
| paired_n_cells | 2398774 |
| n_models | 5 |
| models | GEBCO_2024,ETOPO_2022,SRTM15_V2.7,TOPO_25.1,SDUST_2023 |
| n_clusters | 124 |
| cluster_list_hash | dc733bcb34fc81f1049b4ee024b1c92efaa9ee47a25d531f094bf9dc9d06c557 |
| cluster_min_size | 2 |
| cluster_max_size | 267406 |
| sampled_cluster_sequence_hash | 955d45f56f29a761644e15c8ffa585e1598e09108447a99aa02e256f904b90fe |
| input_path_GEBCO_2024 | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_GEBCO_2024.parquet |
| input_sha256_GEBCO_2024 | 1067a51b60b7ff88ed2ea981536e6349a8de7a0deb7f3de75e9c2b98b9da686f |
| input_path_ETOPO_2022 | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_ETOPO_2022.parquet |
| input_sha256_ETOPO_2022 | d768caae068af5713d45b897b0a706183e58a9d4aacef6bcc117691a67f798c5 |
| input_path_SRTM15_V2.7 | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_SRTM15_V2.7.parquet |
| input_sha256_SRTM15_V2.7 | 2681a967e972e8b55176a8ca53a40de9febf4a9e93a6550950f1055132ee0938 |
| input_path_TOPO_25.1 | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_TOPO_25.1.parquet |
| input_sha256_TOPO_25.1 | c31e3edde8d652de89fc429fbec8fe5560702a8517849b1f1c2f9f58dfbcab77 |
| input_path_SDUST_2023 | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_SDUST_2023.parquet |
| input_sha256_SDUST_2023 | a8089ac781dd1bc0765b5a475311c6843f83c8731168e05ae844ea360f38adda |

| kind | path |
| --- | --- |
| bootstrap_iters | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/ranking_bootstrap_iters.parquet |
| model_metric_ci | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/model_metric_ci.tsv |
| pairwise_delta_rmse_ci | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/pairwise_delta_rmse_ci.tsv |
| ranking_stability_rmse | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/ranking_stability_rmse.tsv |
| ranking_stability_wrmse | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/ranking_stability_wrmse.tsv |
| runtime_metadata | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/bootstrap_runtime_metadata.tsv |
| safety_checks | /mnt/data2/00-Data/ship/ncei/derived/model_validation_1min_step08_pub/a_ranking_uncertainty/a_ranking_safety_checks.tsv |
| report | /mnt/data2/00-Data/ship/ncei/docs/model_ranking_uncertainty_report.md |
