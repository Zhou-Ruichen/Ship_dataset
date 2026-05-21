# NCEI Step 06A — Quality Policy Calibration Audit Report

Generated: 2026-05-21T18:06:18.813572+00:00
Run label: `full`
Policy calibration version: `ncei_policy_calib_v0.1.0`
Elapsed: 107.5s

> This is a calibration audit, not policy enforcement. It writes candidate rules for human review only; it does not define final quality tiers, validation cells, or exclusion flags in any cell product.

## 1. Executive summary

Global uniform thresholds are unsafe. Step 05B shows much tighter multibeam-vs-M.rar agreement (mb_vs_mrar p99 ≈ 440 m) than singlebeam-involving pairs (mb_vs_sb p99 ≈ 2,424 m; mrar_vs_sb p99 ≈ 1,306 m). The Southern Ocean lat=-60 mb_vs_sb p99 ≈ 3,227 m is the clearest high-noise zone. Candidate rules therefore stratify by branch, latitude, depth, duplicate ratio, and overlap evidence.

Principles used for candidate rules: (1) multibeam_ncei can be high-confidence where low-duplicate and cross-validated; (2) singlebeam must be latitude/depth stratified; (3) regional_mrar defaults to sensitivity/regional use unless cross-validated; (4) manual_review flags are supporting evidence only; (5) high duplicate ratio downweights but does not exclude; (6) n_unique_triples_total<10 is low-confidence; (7) no-overlap cells are low-evidence coverage, not high-confidence validation.

## 2. Per-branch headlines

| branch | n_cells_total | n_cells_with_within_branch_overlap | n_cells_with_cross_branch_overlap_any | n_cells_no_overlap_evidence | share_with_overlap_evidence | within_branch_rmse_m | cross_branch_rmse_m_avg | abs_residual_p95_within_branch | abs_residual_p95_cross_branch_max | manual_review_cell_share | auv_sentry_cell_count | headline_finding | policy_calibration_version |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| singlebeam | 14611054 | 2098336 | 1889317 | 10623401 | 0.2729 | 212.2392 | 435.2647 | 187.0000 | 386.4007 | 0.0141 | 0 | Broad global coverage; quality must stratify by latitude/depth and overlap evidence | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | 5960 | 362 | 4789 | 809 | 0.8643 | 55.1220 | 253.9272 | 107.1400 | 386.4007 | 0.0000 | 8 | Tight within-branch; cross-source agreement good vs M.rar but noisy vs singlebeam | ncei_policy_calib_v0.1.0 |
| regional_mrar | 9019383 | 129 | 1889205 | 7130049 | 0.2095 | 91.9131 | 276.8653 | 46.5000 | 274.9500 | 0.0000 | 0 | Regional processed product; usable for sensitivity/cross-validation, not default primary | ncei_policy_calib_v0.1.0 |

## 3. Stratified evidence by latitude × depth

Tables below show the highest-risk slices first per branch (sorted by cross-branch p95, then within-branch p95). Shallow (`0..200 m`) and high-latitude (`lat<-50`) slices should receive special human review.

### singlebeam

| branch | lat_band_10deg | depth_bin_lo | depth_bin_hi | n_cells | n_cells_with_overlap | within_branch_residual_p50 | within_branch_residual_p95 | within_branch_residual_p99 | cross_branch_residual_max_p95 | cross_branch_n_overlap_total | auv_sentry_cell_count_local | manual_review_share_local | policy_calibration_version |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| singlebeam | 20 | 0.0000 | 200.0000 | 83823 | 13160 | 2.5000 | 41.6000 | 151.2550 | 11061.8000 | 1867.0000 | 0 | 0.0087 | ncei_policy_calib_v0.1.0 |
| singlebeam | 10 | 0.0000 | 200.0000 | 30281 | 4857 | 3.4675 | 72.2275 | 203.4810 | 11012.0000 | 1793.0000 | 0 | 0.0225 | ncei_policy_calib_v0.1.0 |
| singlebeam | 0 | 0.0000 | 200.0000 | 47767 | 6446 | 2.7000 | 28.9225 | 128.2580 | 10494.2000 | 976.0000 | 0 | 0.0006 | ncei_policy_calib_v0.1.0 |
| singlebeam | 20 | 200.0000 | 500.0000 | 35788 | 10488 | 9.5000 | 185.5625 | 375.0000 | 7812.5025 | 1508.0000 | 0 | 0.0554 | ncei_policy_calib_v0.1.0 |
| singlebeam | 10 | 200.0000 | 500.0000 | 21044 | 4886 | 13.0250 | 184.1700 | 391.9600 | 7675.3350 | 3018.0000 | 0 | 0.0512 | ncei_policy_calib_v0.1.0 |
| singlebeam | -10 | 200.0000 | 500.0000 | 12302 | 2132 | 11.5000 | 176.4814 | 375.1110 | 7460.4000 | 756.0000 | 0 | 0.0288 | ncei_policy_calib_v0.1.0 |
| singlebeam | -70 | 6000.0000 | 11500.0000 | 443 | 9 | 71.0000 | 732.7000 | 4832.1400 | 7281.2050 | 68.0000 | 0 | 0.0068 | ncei_policy_calib_v0.1.0 |
| singlebeam | 60 | 6000.0000 | 11500.0000 | 90 | 0 |  |  |  | 6999.3000 | 87.0000 | 0 | 0.0111 | ncei_policy_calib_v0.1.0 |
| singlebeam | 60 | 4000.0000 | 6000.0000 | 115 | 1 | 3338.0000 | 3338.0000 | 3338.0000 | 5310.3250 | 100.0000 | 0 | 0.0087 | ncei_policy_calib_v0.1.0 |
| singlebeam | 70 | 4000.0000 | 6000.0000 | 733 | 22 | 116.0000 | 2518.5000 | 2830.1300 | 4068.4250 | 484.0000 | 0 | 0.0014 | ncei_policy_calib_v0.1.0 |
| singlebeam | -60 | 200.0000 | 500.0000 | 22725 | 4676 | 4.9750 | 87.0000 | 216.0125 | 3547.8927 | 3844.0000 | 0 | 0.0002 | ncei_policy_calib_v0.1.0 |
| singlebeam | -60 | 500.0000 | 2000.0000 | 75869 | 11561 | 16.9000 | 237.0000 | 938.8000 | 3377.3725 | 11690.0000 | 0 | 0.0004 | ncei_policy_calib_v0.1.0 |
| singlebeam | -70 | 2000.0000 | 4000.0000 | 293062 | 24836 | 16.6500 | 393.6250 | 1693.2000 | 3266.6930 | 51983.0000 | 0 | 0.0160 | ncei_policy_calib_v0.1.0 |
| singlebeam | -60 | 0.0000 | 200.0000 | 33101 | 6452 | 3.1500 | 30.2250 | 97.5000 | 2972.9800 | 4879.0000 | 0 | 0.0046 | ncei_policy_calib_v0.1.0 |
| singlebeam | 70 | 2000.0000 | 4000.0000 | 141637 | 10940 | 10.8000 | 140.4946 | 485.9210 | 2870.5000 | 5011.0000 | 0 | 0.0625 | ncei_policy_calib_v0.1.0 |
| singlebeam | 0 | 200.0000 | 500.0000 | 9301 | 1663 | 16.8000 | 261.1500 | 442.7600 | 2553.1200 | 313.0000 | 0 | 0.0180 | ncei_policy_calib_v0.1.0 |
| singlebeam | 60 | 2000.0000 | 4000.0000 | 90307 | 13756 | 21.5750 | 73.5000 | 205.5000 | 2445.4750 | 5182.0000 | 0 | 0.0159 | ncei_policy_calib_v0.1.0 |
| singlebeam | -30 | 0.0000 | 200.0000 | 35539 | 7491 | 2.6650 | 15.5000 | 36.2500 | 2274.6100 | 749.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| singlebeam | -20 | 0.0000 | 200.0000 | 52919 | 10291 | 1.6500 | 16.3750 | 82.0000 | 1514.1250 | 846.0000 | 0 | 0.0028 | ncei_policy_calib_v0.1.0 |
| singlebeam | -10 | 0.0000 | 200.0000 | 40494 | 5553 | 2.0000 | 26.2500 | 86.1162 | 1487.4500 | 672.0000 | 0 | 0.0062 | ncei_policy_calib_v0.1.0 |
| singlebeam | -60 | 4000.0000 | 6000.0000 | 262295 | 11823 | 28.7500 | 196.5800 | 624.5250 | 1474.7710 | 59062.0000 | 0 | 0.0001 | ncei_policy_calib_v0.1.0 |
| singlebeam | -50 | 6000.0000 | 11500.0000 | 5959 | 312 | 13.7500 | 1603.7125 | 1731.0000 | 1317.4750 | 2348.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| singlebeam | 40 | 500.0000 | 2000.0000 | 99200 | 32902 | 11.8000 | 299.0000 | 756.8455 | 1218.1825 | 3045.0000 | 0 | 0.0385 | ncei_policy_calib_v0.1.0 |
| singlebeam | 30 | 200.0000 | 500.0000 | 43632 | 13723 | 10.8750 | 181.5000 | 384.6400 | 1190.5000 | 1554.0000 | 0 | 0.0336 | ncei_policy_calib_v0.1.0 |
| singlebeam | 30 | 500.0000 | 2000.0000 | 207993 | 72113 | 15.0000 | 257.5000 | 825.1820 | 1169.0000 | 14216.0000 | 0 | 0.0241 | ncei_policy_calib_v0.1.0 |

### multibeam_ncei

| branch | lat_band_10deg | depth_bin_lo | depth_bin_hi | n_cells | n_cells_with_overlap | within_branch_residual_p50 | within_branch_residual_p95 | within_branch_residual_p99 | cross_branch_residual_max_p95 | cross_branch_n_overlap_total | auv_sentry_cell_count_local | manual_review_share_local | policy_calibration_version |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| multibeam_ncei | -70 | 4000.0000 | 6000.0000 | 199 | 0 |  |  |  | 3414.4697 | 288.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | -70 | 2000.0000 | 4000.0000 | 166 | 0 |  |  |  | 2038.7950 | 267.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | -60 | 2000.0000 | 4000.0000 | 311 | 0 |  |  |  | 1268.2335 | 375.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | 30 | 500.0000 | 2000.0000 | 3 | 0 |  |  |  | 509.5670 | 3.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | -30 | 4000.0000 | 6000.0000 | 27 | 13 | 54.9000 | 198.0600 | 385.6120 | 444.1800 | 52.0000 | 3 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | -70 | 200.0000 | 500.0000 | 674 | 32 | 6.6400 | 48.0779 | 62.1350 | 358.7450 | 1115.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | -60 | 4000.0000 | 6000.0000 | 132 | 0 |  |  |  | 335.6952 | 154.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | -30 | 2000.0000 | 4000.0000 | 537 | 8 | 25.7000 | 506.7850 | 582.5570 | 286.9250 | 212.0000 | 3 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | 30 | 200.0000 | 500.0000 | 34 | 0 |  |  |  | 216.0495 | 34.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | -70 | 500.0000 | 2000.0000 | 2869 | 308 | 7.6213 | 90.9200 | 134.2700 | 193.6200 | 5188.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | 40 | 0.0000 | 200.0000 | 255 | 0 |  |  |  | 157.6075 | 166.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | -70 | 0.0000 | 200.0000 | 110 | 1 | 37.6000 | 37.6000 | 37.6000 | 131.3335 | 135.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | 40 | 200.0000 | 500.0000 | 16 | 0 |  |  |  | 88.8580 | 15.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | -30 | 500.0000 | 2000.0000 | 189 | 0 |  |  |  | 87.9475 | 81.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | 10 | 0.0000 | 200.0000 | 15 | 0 |  |  |  | 52.3620 | 12.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | -30 | 200.0000 | 500.0000 | 31 | 0 |  |  |  | 52.2960 | 9.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | -30 | 0.0000 | 200.0000 | 234 | 0 |  |  |  | 25.0200 | 36.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| multibeam_ncei | 20 | 0.0000 | 200.0000 | 158 | 0 |  |  |  |  |  | 2 | 0.0000 | ncei_policy_calib_v0.1.0 |

### regional_mrar

| branch | lat_band_10deg | depth_bin_lo | depth_bin_hi | n_cells | n_cells_with_overlap | within_branch_residual_p50 | within_branch_residual_p95 | within_branch_residual_p99 | cross_branch_residual_max_p95 | cross_branch_n_overlap_total | auv_sentry_cell_count_local | manual_review_share_local | policy_calibration_version |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| regional_mrar | 0 | 6000.0000 | 11500.0000 | 15267 | 0 |  |  |  | 8501.0687 | 2286.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | 10 | 6000.0000 | 11500.0000 | 64056 | 0 |  |  |  | 7667.7550 | 14668.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | -50 | 6000.0000 | 11500.0000 | 18968 | 0 |  |  |  | 5634.7000 | 3044.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | -60 | 6000.0000 | 11500.0000 | 12199 | 0 |  |  |  | 5247.6750 | 1644.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | 70 | 6000.0000 | 11500.0000 | 4 | 0 |  |  |  | 4664.3500 | 1.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | -70 | 6000.0000 | 11500.0000 | 1932 | 0 |  |  |  | 4357.8400 | 77.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | 70 | 200.0000 | 500.0000 | 6247 | 0 |  |  |  | 4039.3000 | 997.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | 30 | 6000.0000 | 11500.0000 | 50072 | 0 |  |  |  | 3966.9292 | 13864.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | -10 | 6000.0000 | 11500.0000 | 7432 | 0 |  |  |  | 3820.0125 | 1432.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | 50 | 0.0000 | 200.0000 | 2376 | 0 |  |  |  | 3741.5250 | 490.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | 50 | 200.0000 | 500.0000 | 1451 | 0 |  |  |  | 3562.8000 | 217.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | 60 | 4000.0000 | 6000.0000 | 46 | 0 |  |  |  | 3515.7000 | 3.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | -80 | 6000.0000 | 11500.0000 | 217 | 0 |  |  |  | 3463.3700 | 7.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | 60 | 200.0000 | 500.0000 | 4899 | 0 |  |  |  | 3286.1750 | 1680.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | 50 | 500.0000 | 2000.0000 | 8581 | 0 |  |  |  | 2959.1250 | 1406.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | 30 | 200.0000 | 500.0000 | 2668 | 0 |  |  |  | 2860.6000 | 1615.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | -40 | 6000.0000 | 11500.0000 | 20945 | 0 |  |  |  | 2061.0000 | 4681.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | 40 | 6000.0000 | 11500.0000 | 33054 | 0 |  |  |  | 1519.1300 | 3547.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | 20 | 6000.0000 | 11500.0000 | 69116 | 0 |  |  |  | 1050.7000 | 13929.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | -20 | 6000.0000 | 11500.0000 | 16105 | 0 |  |  |  | 984.0000 | 5061.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | 30 | 0.0000 | 200.0000 | 2387 | 0 |  |  |  | 926.5750 | 1518.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | 70 | 4000.0000 | 6000.0000 | 1230 | 0 |  |  |  | 905.5000 | 221.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | -40 | 0.0000 | 200.0000 | 1906 | 0 |  |  |  | 849.5000 | 856.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | 80 | 4000.0000 | 6000.0000 | 5256 | 0 |  |  |  | 842.2125 | 186.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |
| regional_mrar | -70 | 4000.0000 | 6000.0000 | 383929 | 0 |  |  |  | 661.9000 | 32110.0000 | 0 | 0.0000 | ncei_policy_calib_v0.1.0 |

## 4. Per-pair stratified evidence

### mb_vs_mrar

| pair_label | dup_bin_lo | dup_bin_hi | n_unique_lo | n_unique_hi | n_cells_in_slice | residual_p50 | residual_p95 | residual_p99 | abs_residual_p50 | abs_residual_p95 | abs_residual_p99 | rmse | policy_calibration_version |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mb_vs_mrar | 0.0000 | 0.0100 | 10000.0000 |  | 55 | -4.5000 | 244.7500 | 398.5700 | 30.5500 | 255.0050 | 398.5700 | 127.3088 | ncei_policy_calib_v0.1.0 |
| mb_vs_mrar | 0.5000 | 1.0000 | 10000.0000 |  | 6 | -6.1500 | 137.3250 | 161.1450 | 75.9750 | 234.5250 | 252.5050 | 135.6151 | ncei_policy_calib_v0.1.0 |
| mb_vs_mrar | 0.0000 | 0.0100 | 1.0000 | 10.0000 | 107 | 6.7100 | 200.1410 | 649.4512 | 29.0500 | 211.9890 | 649.4512 | 135.7210 | ncei_policy_calib_v0.1.0 |
| mb_vs_mrar | 0.1000 | 0.5000 | 100.0000 | 1000.0000 | 11 | 34.0000 | 201.7262 | 247.9072 | 38.0000 | 201.7262 | 247.9072 | 111.1888 | ncei_policy_calib_v0.1.0 |
| mb_vs_mrar | 0.1000 | 0.5000 | 10000.0000 |  | 8 | -33.1750 | 68.2700 | 87.2540 | 78.8750 | 192.0300 | 212.2460 | 108.2215 | ncei_policy_calib_v0.1.0 |
| mb_vs_mrar | 0.0000 | 0.0100 | 10.0000 | 100.0000 | 834 | 0.8338 | 132.9000 | 399.7541 | 14.5000 | 184.9375 | 408.2966 | 93.8587 | ncei_policy_calib_v0.1.0 |
| mb_vs_mrar | 0.0000 | 0.0100 | 100.0000 | 1000.0000 | 1129 | -0.8500 | 124.9820 | 403.7080 | 21.3800 | 168.7220 | 445.4712 | 98.4859 | ncei_policy_calib_v0.1.0 |
| mb_vs_mrar | 0.0100 | 0.1000 | 100.0000 | 1000.0000 | 13 | 9.4425 | 153.3360 | 214.9392 | 22.8675 | 153.3360 | 214.9392 | 75.7696 | ncei_policy_calib_v0.1.0 |
| mb_vs_mrar | 0.0000 | 0.0100 | 1000.0000 | 10000.0000 | 1826 | -0.0700 | 80.2775 | 381.5575 | 14.9087 | 131.0413 | 480.5325 | 90.7125 | ncei_policy_calib_v0.1.0 |
| mb_vs_mrar | 0.1000 | 0.5000 | 10.0000 | 100.0000 | 15 | 0.5000 | 112.7000 | 131.7400 | 13.0000 | 112.7000 | 131.7400 | 48.2005 | ncei_policy_calib_v0.1.0 |
| mb_vs_mrar | 0.0100 | 0.1000 | 1000.0000 | 10000.0000 | 6 | 3.5175 | 8.0175 | 8.0435 | 7.5075 | 38.5600 | 46.6960 | 20.6546 | ncei_policy_calib_v0.1.0 |
| mb_vs_mrar | 0.0100 | 0.1000 | 10.0000 | 100.0000 | 5 | 1.5000 | 18.4000 | 20.4800 | 14.5000 | 21.0000 | 21.0000 | 15.2217 | ncei_policy_calib_v0.1.0 |

### mb_vs_sb

| pair_label | dup_bin_lo | dup_bin_hi | n_unique_lo | n_unique_hi | n_cells_in_slice | residual_p50 | residual_p95 | residual_p99 | abs_residual_p50 | abs_residual_p95 | abs_residual_p99 | rmse | policy_calibration_version |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mb_vs_sb | 0.0100 | 0.1000 | 10.0000 | 100.0000 | 8 | -0.8100 | 1158.3300 | 1625.7900 | 13.0000 | 1158.3300 | 1625.7900 | 616.9408 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.0100 | 0.1000 | 1000.0000 | 10000.0000 | 27 | 17.5400 | 1072.0117 | 1241.1946 | 30.7000 | 1072.0117 | 1241.1946 | 403.8326 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.0100 | 0.1000 | 100.0000 | 1000.0000 | 21 | 4.0000 | 543.4150 | 1503.5750 | 51.2000 | 543.4150 | 1503.5750 | 406.5288 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.0000 | 0.0100 | 1000.0000 | 10000.0000 | 1914 | 5.2350 | 155.3825 | 1629.4170 | 19.0575 | 393.0165 | 2504.8627 | 416.6426 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.0000 | 0.0100 | 100.0000 | 1000.0000 | 1146 | 1.2075 | 174.6794 | 2352.6952 | 24.1975 | 373.7912 | 2695.6892 | 469.9994 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.1000 | 0.5000 | 10000.0000 |  | 6 | -90.8275 | 342.5562 | 380.2312 | 204.4375 | 359.4250 | 383.6050 | 238.1678 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.0000 | 0.0100 | 10000.0000 |  | 107 | -1.4300 | 307.8675 | 535.5970 | 18.3300 | 323.3875 | 535.5970 | 144.0338 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.0000 | 0.0100 | 10.0000 | 100.0000 | 808 | -1.0000 | 160.5155 | 1762.9410 | 20.4225 | 319.1935 | 1995.1056 | 354.8879 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.0000 | 0.0100 | 1.0000 | 10.0000 | 33 | 9.9800 | 65.0540 | 77.7024 | 31.6800 | 285.9540 | 443.9150 | 118.2339 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.5000 | 1.0000 | 10000.0000 |  | 5 | 20.0000 | 92.8800 | 100.5360 | 102.4500 | 243.5850 | 264.8770 | 145.3881 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.1000 | 0.5000 | 10.0000 | 100.0000 | 17 | -9.5000 | 131.2800 | 153.4560 | 49.0000 | 203.9835 | 347.9307 | 114.1263 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.1000 | 0.5000 | 100.0000 | 1000.0000 | 15 | 43.8425 | 147.3087 | 203.8617 | 64.0000 | 147.3087 | 203.8617 | 86.0433 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.5000 | 1.0000 | 10.0000 | 100.0000 | 2 | 105.0525 | 146.2117 | 149.8703 | 105.0525 | 146.2117 | 149.8703 | 114.5753 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.5000 | 1.0000 | 1000.0000 | 10000.0000 | 7 | 31.5900 | 127.9895 | 150.4139 | 42.4050 | 138.7100 | 152.5580 | 77.6940 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.5000 | 1.0000 | 100.0000 | 1000.0000 | 4 | 37.5825 | 96.8878 | 103.8496 | 65.3325 | 102.2150 | 104.9150 | 72.5910 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.5000 | 1.0000 | 1.0000 | 10.0000 | 1 | 78.2700 | 78.2700 | 78.2700 | 78.2700 | 78.2700 | 78.2700 | 78.2700 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.1000 | 0.5000 | 1000.0000 | 10000.0000 | 3 | 4.8600 | 31.3650 | 33.7210 | 11.3700 | 32.0160 | 33.8512 | 21.0561 | ncei_policy_calib_v0.1.0 |
| mb_vs_sb | 0.0100 | 0.1000 | 10000.0000 |  | 3 | 20.3700 | 26.0490 | 26.5538 | 20.3700 | 26.0490 | 26.5538 | 19.7489 | ncei_policy_calib_v0.1.0 |

### mrar_vs_sb

| pair_label | dup_bin_lo | dup_bin_hi | n_unique_lo | n_unique_hi | n_cells_in_slice | residual_p50 | residual_p95 | residual_p99 | abs_residual_p50 | abs_residual_p95 | abs_residual_p99 | rmse | policy_calibration_version |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mrar_vs_sb | 0.0100 | 0.1000 | 1000.0000 | 10000.0000 | 42 | 69.8000 | 3349.3905 | 3438.6757 | 69.8000 | 3349.3905 | 3438.6757 | 1968.9874 | ncei_policy_calib_v0.1.0 |
| mrar_vs_sb | 0.0000 | 0.0100 | 10000.0000 |  | 57 | 17.0700 | 3324.8680 | 3789.8576 | 37.0500 | 3324.8680 | 3789.8576 | 1464.4551 | ncei_policy_calib_v0.1.0 |
| mrar_vs_sb | 0.1000 | 0.5000 | 1000.0000 | 10000.0000 | 4 | -11.0500 | 3223.7680 | 3679.5376 | 28.5000 | 3230.3830 | 3680.8606 | 1896.8644 | ncei_policy_calib_v0.1.0 |
| mrar_vs_sb | 0.1000 | 0.5000 | 100.0000 | 1000.0000 | 236 | 15.0250 | 2978.5787 | 3580.6590 | 27.7750 | 2978.5787 | 3580.6590 | 1158.8455 | ncei_policy_calib_v0.1.0 |
| mrar_vs_sb | 0.0100 | 0.1000 | 10000.0000 |  | 9 | 1447.5450 | 2834.4760 | 3508.3352 | 1447.5450 | 2834.4760 | 3508.3352 | 1588.0949 | ncei_policy_calib_v0.1.0 |
| mrar_vs_sb | 0.0000 | 0.0100 | 1000.0000 | 10000.0000 | 807 | 9.7825 | 660.2315 | 3794.6874 | 19.8350 | 691.3345 | 3794.6874 | 713.4976 | ncei_policy_calib_v0.1.0 |
| mrar_vs_sb | 0.1000 | 0.5000 | 1.0000 | 10.0000 | 518 | -3.5000 | 253.7500 | 1665.0980 | 47.7500 | 640.7750 | 2237.9050 | 531.5509 | ncei_policy_calib_v0.1.0 |
| mrar_vs_sb | 0.5000 | 1.0000 | 1.0000 | 10.0000 | 708 | -2.2500 | 204.8500 | 964.6950 | 54.0000 | 614.4750 | 2070.0400 | 392.4053 | ncei_policy_calib_v0.1.0 |
| mrar_vs_sb | 0.0100 | 0.1000 | 100.0000 | 1000.0000 | 583 | 19.5000 | 603.4000 | 3177.2878 | 54.5000 | 603.4000 | 3177.2878 | 582.2456 | ncei_policy_calib_v0.1.0 |
| mrar_vs_sb | 0.0100 | 0.1000 | 1.0000 | 10.0000 | 25 | 13.0000 | 482.1000 | 2433.6200 | 43.7500 | 519.3000 | 2433.6200 | 623.8464 | ncei_policy_calib_v0.1.0 |
| mrar_vs_sb | 0.1000 | 0.5000 | 10.0000 | 100.0000 | 1308 | 1.8500 | 355.8500 | 3197.0859 | 32.5000 | 418.7000 | 3197.0859 | 478.1629 | ncei_policy_calib_v0.1.0 |
| mrar_vs_sb | 0.0000 | 0.0100 | 1.0000 | 10.0000 | 554534 | 7.5000 | 275.0000 | 1264.8680 | 26.5000 | 377.5000 | 1906.5000 | 509.2047 | ncei_policy_calib_v0.1.0 |
| mrar_vs_sb | 0.0100 | 0.1000 | 10.0000 | 100.0000 | 1367 | -1.0000 | 198.4500 | 1025.8771 | 37.5000 | 312.0000 | 1203.2840 | 427.1630 | ncei_policy_calib_v0.1.0 |
| mrar_vs_sb | 0.0000 | 0.0100 | 10.0000 | 100.0000 | 1317872 | 6.5000 | 181.0000 | 778.0000 | 22.6000 | 238.5000 | 984.0290 | 434.7181 | ncei_policy_calib_v0.1.0 |
| mrar_vs_sb | 0.0000 | 0.0100 | 100.0000 | 1000.0000 | 7817 | 1.1300 | 163.5250 | 3078.8444 | 10.6050 | 217.8180 | 3156.5616 | 445.1302 | ncei_policy_calib_v0.1.0 |
| mrar_vs_sb | 0.5000 | 1.0000 | 10.0000 | 100.0000 | 2638 | 1.1000 | 106.5750 | 366.4850 | 25.5000 | 142.0675 | 462.6950 | 141.8749 | ncei_policy_calib_v0.1.0 |
| mrar_vs_sb | 0.5000 | 1.0000 | 100.0000 | 1000.0000 | 18 | -4.0000 | 80.8750 | 157.3750 | 10.5750 | 80.8750 | 157.3750 | 48.2157 | ncei_policy_calib_v0.1.0 |

## 5. Spotlight analyses

### Southern Ocean lat=-60 large residuals

| pair_label | n_cells | abs_residual_p95 | abs_residual_p99 | rmse |
| --- | --- | --- | --- | --- |
| mb_vs_mrar | 326 | 268.8900 | 436.9250 | 121.8052 |
| mb_vs_sb | 203 | 1095.7140 | 3226.9764 | 568.6816 |
| mrar_vs_sb | 149344 | 510.5000 | 2725.1270 | 457.6698 |

Interpretation: singlebeam-involving Southern Ocean overlap has the largest tails. Candidate rules mark these slices as review/sensitivity unless a local slice has strong overlap evidence.

### AUV Sentry hotspots

Because this Step 06A script is constrained to Step 04B/05A/05B inputs only, it does not join back to Step 04A track_id rows. It uses the documented proxy `duplicate_ratio_cell>0.5` (plus manual_review where present) for AUV-Sentry-like cells.
| metric | value |
| --- | --- |
| high_duplicate_proxy_cells | 8.0000 |
| median_lon_center | -111.8750 |
| median_lat_center | -22.9333 |
| dominant_lat_band_10deg | -30.0000 |


### M.rar × singlebeam large-overlap high-residual regions

Latitude bands below are sorted by share of squared residual error for mrar_vs_sb; bands accounting for >50% cumulatively are the first review targets.
| lat_band_10deg | n_cells | rmse | share_of_squared_error |
| --- | --- | --- | --- |
| 10.0000 | 180243.0000 | 762.9755 | 0.2646 |
| 20.0000 | 126055.0000 | 721.3774 | 0.1654 |
| 30.0000 | 103575.0000 | 708.9393 | 0.1313 |
| 0.0000 | 75232.0000 | 683.1675 | 0.0886 |
| -60.0000 | 149344.0000 | 457.6698 | 0.0789 |
| -50.0000 | 117419.0000 | 400.9014 | 0.0476 |
| -70.0000 | 135517.0000 | 367.1582 | 0.0461 |
| -40.0000 | 153880.0000 | 293.6895 | 0.0335 |
| -20.0000 | 301852.0000 | 185.5927 | 0.0262 |
| -30.0000 | 182718.0000 | 231.7086 | 0.0247 |
| -10.0000 | 208899.0000 | 199.6762 | 0.0210 |
| 60.0000 | 11869.0000 | 836.0963 | 0.0209 |
| 70.0000 | 6949.0000 | 1057.9505 | 0.0196 |
| 40.0000 | 37347.0000 | 410.9667 | 0.0159 |
| 50.0000 | 20659.0000 | 454.0168 | 0.0107 |
| -80.0000 | 76234.0000 | 156.2381 | 0.0047 |
| 80.0000 | 751.0000 | 317.8408 | 0.0002 |

### Multibeam × M.rar consistency zones

Candidate cross-validation zones are mb_vs_mrar lat/depth slices with RMSE < 150 m.
| lat_band_10deg | depth_bin_lo | depth_bin_hi | n_cells | rmse | abs_residual_p95 |
| --- | --- | --- | --- | --- | --- |
| -30.0000 | 500.0000 | 2000.0000 | 15.0000 | 23.9157 | 48.0655 |
| -30.0000 | 0.0000 | 200.0000 | 1.0000 | 25.0200 | 25.0200 |
| -70.0000 | 4000.0000 | 6000.0000 | 198.0000 | 54.6554 | 124.1823 |
| -70.0000 | 200.0000 | 500.0000 | 524.0000 | 59.1681 | 114.5957 |
| -70.0000 | 0.0000 | 200.0000 | 55.0000 | 66.0495 | 129.2200 |
| -70.0000 | 2000.0000 | 4000.0000 | 166.0000 | 78.2575 | 146.0987 |
| -70.0000 | 500.0000 | 2000.0000 | 2637.0000 | 100.9212 | 161.1720 |
| -60.0000 | 2000.0000 | 4000.0000 | 216.0000 | 110.4043 | 254.0175 |
| -30.0000 | 2000.0000 | 4000.0000 | 66.0000 | 112.6859 | 286.9250 |
| -30.0000 | 4000.0000 | 6000.0000 | 27.0000 | 123.9128 | 216.5500 |
| -60.0000 | 4000.0000 | 6000.0000 | 110.0000 | 141.5452 | 313.5695 |

### Singlebeam cells with strong vs weak overlap evidence

| n_track_cells_bin | n_cells | share | median_n_unique_triples_total |
| --- | --- | --- | --- |
| 1..2 | 12512718 | 0.8564 | 2.0000 |
| 2..5 | 2061861 | 0.1411 | 6.0000 |
| 20..inf | 56 | 0.0000 | 713.5000 |
| 5..20 | 36419 | 0.0025 | 22.0000 |

## 6. Candidate policy rules

The TSV output is a candidate-rule list for human review. It is the only output containing candidate tier strings; the parquet outputs remain evidence tables and do not define final tiers.
| rule_id | candidate_tier | applies_to_branch | applies_to_lat_band_filter | applies_to_depth_bin_filter | condition | recommended_weight | requires_step05_overlap | exclude_from_primary | evidence_basis | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mb_v0_high_overlap_lowdup | high_confidence | multibeam_ncei | -80..-70,-30..-20 | 500..6000 | n_track_cells>=2 AND duplicate_ratio_cell<=0.1 AND mb_vs_mrar same lat/depth slice has abs_residual_p95<175m | 0.9500 | True | False | Step05A mb within-branch RMSE ~55m; Step05B mb_vs_mrar RMSE ~95m / p95 ~165m, with lat=-70 rmse ~92m. | Candidate high-confidence anchor where multibeam is cross-validated against M.rar; human review must confirm accepted lat/depth slices. |
| mb_v0_singletrack_lowdup | medium_confidence | multibeam_ncei | * | * | n_track_cells==1 AND duplicate_ratio_cell<=0.1 AND n_unique_triples_total>=100 | 0.7500 | False | False | Most mb cells are single-track, but low duplicate ratio and high effective count reduce AUV duplication risk. | No within-cell overlap evidence; prefer cross-branch evidence if available. |
| mb_v0_highdup_sentry_downweight | medium_confidence | multibeam_ncei | * | * | duplicate_ratio_cell>0.5 AND n_unique_triples_total>=100 | 0.5500 | False | False | Step04/05 show AUV-Sentry-like duplicate_ratio>0.5 cells can have elevated residual tails; duplicates should downweight, not exclude. | AUV-Sentry proxy only; this audit does not consume Step04A per-file-cell track_id by design. |
| sb_v0_lowlat_shallow_overlap_high | high_confidence | singlebeam | -50..50 | 0..2000 | n_track_cells>=2 AND n_unique_triples_total>=10 AND duplicate_ratio_cell<=0.1 AND within/cross slice abs_residual_p95<200m | 0.8500 | True | False | Singlebeam must be stratified; lower-latitude/shallow slices are expected to avoid the Southern Ocean high-noise tail. | Final thresholds require human inspection of quality_calibration_by_lat_depth.parquet. |
| sb_v0_lowlat_deep_overlap_medium | medium_confidence | singlebeam | -50..50 | 2000..6000 | n_track_cells>=2 AND n_unique_triples_total>=10 AND within_branch_abs_residual_p95<300m | 0.6500 | True | False | Step05A singlebeam within-branch p95 is ~187m globally, but cross-source p95 is much larger and requires slice-specific calibration. | Use for supplementary validation until cross-source agreement is regionally accepted. |
| sb_v0_southern_ocean_review | review_or_sensitivity_only | singlebeam | -70..-50 | * | lat_band_10deg IN {-70,-60,-50} AND (cross_branch_abs_residual_p99>1000m OR no cross_branch_overlap) | 0.2500 | False | False | Step05B mb_vs_sb lat=-60 p99 ~3227m; global uniform thresholds are unsafe. | Do not automatically exclude; reserve for sensitivity analyses or manual regional review. |
| sb_v0_no_overlap_low | low_confidence | singlebeam | * | * | n_track_cells==1 AND not in any Step05B cross-branch overlap | 0.3500 | False | False | Cells without within-branch or cross-branch overlap have no direct evidence to verify them. | low_evidence: no overlap to verify; keep as coverage but not high-confidence validation. |
| any_v0_low_unique_low | low_confidence | * | * | * | n_unique_triples_total<10 | 0.3000 | False | False | Effective observation count below 10 is sparse regardless of branch. | Branch-specific exceptions require human review. |
| any_v0_overlap_both_high | high_confidence | * | * | * | n_track_cells>=2 AND in Step05B cross-branch pair with same-slice abs_residual_p95<150m AND duplicate_ratio_cell<=0.1 | 0.9000 | True | False | Cells with both within-branch and cross-branch support are the strongest candidates for primary validation. | Future Step06B should materialize evidence_class='both'. |
| manual_review_not_exclusion | medium_confidence | * | * | * | manual_review_any=True AND within/cross residual evidence remains acceptable for that lat/depth slice | 0.6000 | True | False | Manual review flag alone is informational; Step05B manual_review_either=True slices were not universally worse. | Never use manual_review_any=True by itself as a drop/exclude rule. |
| mrar_v0_default_sensitivity | review_or_sensitivity_only | regional_mrar | * | * | regional_mrar cell unless cross-validated by mb_vs_mrar same lat/depth slice with rmse<150m | 0.2000 | False | True | M.rar is a processed regional product with unresolved provenance; mrar_vs_sb p99 is large globally. | Default branch_role should be regional/sensitivity, not primary validation. |
| mrar_v0_crossvalidated_medium | medium_confidence | regional_mrar | -80..-70,-30..-20 | 500..6000 | cell overlaps multibeam_ncei AND mb_vs_mrar same lat/depth slice rmse<150m AND abs_residual_p95<200m | 0.6000 | True | True | mb_vs_mrar is much tighter than mb_vs_sb and mrar_vs_sb, especially in lat=-70 consistency zone. | Still exclude from primary by default; useful as regional supplement or consistency check. |
| mrar_v0_shallow_highrisk | review_or_sensitivity_only | regional_mrar | * | 0..200 | depth_bin=0..200 OR abs(mrar_vs_sb residual) tail exceeds regional threshold | 0.1000 | False | True | M.rar had land/sentinel cleaning history; shallow cells are most exposed to land-mask/topography mixing. | Human must decide whether cleaned shallow M.rar cells are acceptable at all. |
| any_v0_dup_heavy_downweight | low_confidence | * | * | * | duplicate_ratio_cell>0.5 AND no supportive cross-branch evidence | 0.3500 | False | False | High duplicate ratio indicates repeated identical triples; Step04 design says do not weight by raw points. | Reduce confidence but do not exclude solely for duplicates. |
| any_v0_strong_unique_medium | medium_confidence | * | * | * | n_unique_triples_total>=1000 AND duplicate_ratio_cell<=0.1 AND at least one overlap evidence source | 0.7000 | True | False | Large effective-count cells are more stable, but cross-source disagreement still requires region stratification. | This is not a substitute for branch/lat/depth evidence. |
| sb_v0_highlat_north_review | review_or_sensitivity_only | singlebeam | 60..90 | * | lat_band_10deg>=60 AND cross_branch_abs_residual_p95>300m | 0.3000 | True | False | Step05B mrar_vs_sb high-northern bands show large residual tails in the current audit. | Northern high-latitude behavior should be manually separated from Southern Ocean noise. |

## 7. Step 06B implementation recommendations

Future Step 06B should carry these fields in the quality manifest: `quality_tier`, `branch_role` (`primary` / `supplementary` / `regional`), `validation_weight`, `evidence_class` (`within_branch` / `cross_branch` / `both` / `none`), `low_evidence_flag`, and `auv_sentry_flag`. It should also preserve `n_unique_triples_total`, `duplicate_ratio_cell`, `manual_review_any`, and the lat/depth bins used here for auditability.

## 8. Open questions for human review

1. Do we accept latitude-stratified thresholds, or must there be unified per-branch thresholds for publication simplicity?
2. Should Southern Ocean singlebeam cells remain supplementary only, or can local cross-validation rescue selected lat/depth slices?
3. Is regional_mrar allowed in any primary validation product, or should it remain regional/sensitivity-only even when mb_vs_mrar is tight?
4. What maximum acceptable p95 / p99 residual tail should define high-confidence singlebeam cells?
5. Should `duplicate_ratio_cell>0.5` be an AUV-Sentry downweight proxy in Step 06B, or should Step 06B perform a more expensive track_id join?
6. Should shallow cells (<200 m) have a separate land/topography-mixing review policy across all branches?
7. How should no-overlap singlebeam coverage be represented: low-confidence validation, supplementary coverage, or withheld from validation?

## 9. Cross-links

- Spec §13: `.trellis/spec/backend/pipeline-design-decisions.md#13-ncei-step-04a--per-file-1-arcmin-cell-aggregation`.
- Spec §14: `.trellis/spec/backend/pipeline-design-decisions.md#14-ncei-step-04b--source-specific-global-1-arcmin-cell-merge`.
- Spec §15: `.trellis/spec/backend/pipeline-design-decisions.md#15-ncei-step-05a--source-specific-overlap-residual-analysis`.
- Spec §16: `.trellis/spec/backend/pipeline-design-decisions.md#16-ncei-step-05b--cross-branch-overlap-audit`.
- Step 04 report: `ncei/docs/step04_aggregation_design_audit.md`.
- Step 04B report: `ncei/docs/step04b_cells_1min_merge_report.md`.
- Step 05A report: `ncei/docs/step05a_source_specific_overlap_bias_report.md`.
- Step 05B report: `ncei/docs/step05b_cross_branch_overlap_audit_report.md`.

## 10. Output paths

| kind | path |
| --- | --- |
| by branch | ncei/derived/quality_policy_calibration_1min/quality_calibration_by_branch.parquet |
| by lat/depth | ncei/derived/quality_policy_calibration_1min/quality_calibration_by_lat_depth.parquet |
| by source pair | ncei/derived/quality_policy_calibration_1min/quality_calibration_by_source_pair.parquet |
| candidate rules TSV | ncei/derived/quality_policy_calibration_1min/quality_policy_candidate_rules.tsv |
| report | ncei/docs/step06a_quality_policy_calibration_report.md |
