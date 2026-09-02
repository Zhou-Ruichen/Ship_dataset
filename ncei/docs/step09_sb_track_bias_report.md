# Step 09 singlebeam track-bias controls

Bias estimates and all three control arms use only frozen `inner_training` scope. For strict MB, the script pushes membership-parquet `inner_training` cell ids into the Arrow depth read and asserts every MB depth row against the frozen role map. For SB, it computes all 15 training blocks on each tile's 5x5 grid using `(block_lon + 2 * block_lat) mod 5 in {2, 3, 4}`, selects cell ids from coordinates before reading SB depths, and asserts every SB depth row remains in those blocks. The block definition comes from `15-swot_feature_physics_bathy/configs/feasibility/prospective_nested_ggm_selection.yaml` under `nested_roles`. No strict MB `representative_depth_m` from `inner_validation` or `outer_evaluation` was read.

A track bias is the `n_unique_triples`-weighted median of track-cell depth minus its reference. Strict MB is the reference when present; otherwise the reference is the median of at least two other SB tracks in that cell. The bias is applied only with at least five reference cells and `|bias| >= 2 * NMAD`. Step 08's file-balanced rule is retained: an SB control cell is the median of its per-track cell medians.

## Per-region results

| region | SB tracks | bias applied | thin evidence | not significant | median |b| applied (m) | MB controls | SB controls | SB-only coverage | MB+SB control rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lon068_lat018 | 32 | 9 | 13 | 10 | 12.03 | 2148 | 4181 | 3765 | 6329 |
| lon052_lat018 | 43 | 3 | 30 | 10 | 15.39 | 1538 | 7313 | 6977 | 8851 |
| lon058_lat012 | 37 | 4 | 6 | 27 | 127.25 | 1781 | 8207 | 7981 | 9988 |
| lon059_lat015 | 51 | 6 | 12 | 33 | 69.20 | 7088 | 6306 | 5409 | 13394 |
| lon004_lat033 | 13 | 1 | 6 | 6 | 35.40 | 1051 | 7112 | 6976 | 8163 |
| lon021_lat010 | 54 | 1 | 7 | 46 | 937.10 | 938 | 8098 | 7467 | 9036 |

Across applied tracks, the signed bias distribution (m) is: minimum -4839.38, median -9.68, maximum 937.10; median absolute bias 39.70.

## GEBCO diagnostic stratification

Bands are defined from the raw SB control-cell difference: `<100 m`, `100-<500 m`, and `>=500 m`. GEBCO 2024 was sampled at each SB cell center only after bias decisions and control membership were fixed. These values did not gate cells, tracks, bias application, or any control arm.

| region | raw SB-GEBCO band | SB cells | median raw |difference| (m) | median adjusted |difference| (m) |
| --- | --- | ---: | ---: | ---: |
| lon068_lat018 | <100 m | 3981 | 4.50 | 5.83 |
| lon068_lat018 | 100-<500 m | 187 | 114.60 | 9.99 |
| lon068_lat018 | >=500 m | 13 | 2997.85 | 3102.86 |
| lon052_lat018 | <100 m | 7259 | 3.00 | 3.00 |
| lon052_lat018 | 100-<500 m | 49 | 135.00 | 135.00 |
| lon052_lat018 | >=500 m | 5 | 1176.00 | 1176.00 |
| lon058_lat012 | <100 m | 7374 | 11.00 | 11.00 |
| lon058_lat012 | 100-<500 m | 754 | 156.12 | 148.00 |
| lon058_lat012 | >=500 m | 79 | 633.50 | 566.00 |
| lon059_lat015 | <100 m | 5098 | 10.00 | 12.00 |
| lon059_lat015 | 100-<500 m | 930 | 151.00 | 147.00 |
| lon059_lat015 | >=500 m | 278 | 4611.40 | 118.50 |
| lon004_lat033 | <100 m | 5146 | 27.35 | 28.87 |
| lon004_lat033 | 100-<500 m | 1626 | 180.05 | 178.93 |
| lon004_lat033 | >=500 m | 340 | 847.26 | 845.91 |
| lon021_lat010 | <100 m | 6000 | 19.50 | 19.75 |
| lon021_lat010 | 100-<500 m | 1620 | 180.60 | 180.45 |
| lon021_lat010 | >=500 m | 478 | 751.00 | 746.00 |

## Outputs and reruns

Each region has `controls_mb_only_<region>.parquet`, `controls_mb_sb_raw_<region>.parquet`, and `controls_mb_sb_adjusted_<region>.parquet` under `ncei/derived/sb_track_bias_1min/`. Track decisions are in `track_bias_summary.parquet`. A rerun without `--overwrite` exits without changing a complete output set; a partial output set requires `--overwrite`.
