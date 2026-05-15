# Overlap Bias Analysis Report — sample (1min)

Generated: 2026-04-30T02:16:52.327399

## Summary

| Metric | Value |
|--------|-------|
| Cell size | 1min (0.016667 deg) |
| Input file-cell files | 50 |
| Input file-cell rows | 35,283 |
| Read errors | 0 |
| Overlap file-cell rows | 23,909 |
| Overlap cells | 23,717 |
| Multi-cruise overlap cells | 20,838 |
| Elapsed | 16.7s |
| Backend | pandas |

## Residual depth statistics (all overlap file-cells)

| Stat | Value |
|------|-------|
| count | 23,909 |
| min | -5205.2350 m |
| p05 | -22.5517 m |
| p25 | -3.2250 m |
| median | 0.0000 m |
| p75 | 6.3500 m |
| p95 | 44.7583 m |
| max | 2080.2030 m |
| mean | 7.0163 m |
| std | 76.8206 m |
| MAD | 4.6500 m |

## Residual consistency check

| Check | Result |
|-------|--------|
| residual_elev_m + residual_depth_m | should ≈ 0 |
| max |diff| | 0.000000e+00 |
| mean |diff| | 0.000000e+00 |
| Consistent? | YES |

## File bias summary

| Stat | Value |
|------|-------|
| Total files with overlap | 49 |
| Suspicious files | 12 |

### Top 10 files by |median residual|

| file_id | n_overlap | median_res | mad | rmse | p95_abs |
|---------|-----------|------------|-----|------|---------|
| KY07-11_bathymetry_dmo::20070831.dat | 89 | -2.13 | 23.59 | 71.42 | 169.97 |
| KR05-17_bathymetry_dmo::20051222.dat | 90 | -7.07 | 21.00 | 47.82 | 104.65 |
| KR02-13_bathymetry_dmo::20021020.dat | 1270 | 11.24 | 19.27 | 68.30 | 114.43 |
| KY08-03_leg1_bathymetry_dmo::20080404.dat | 11 | -8.92 | 15.24 | 26.25 | 46.55 |
| KY13-13_bathymetry_dmo::T20130922.dat | 122 | -4.11 | 17.95 | 89.43 | 200.55 |
| KY15-15_bathymetry_dmo::T20151004.dat | 33 | 2.77 | 18.35 | 94.49 | 200.19 |
| MR03-K03_leg2_bathymetry_dmo::20030721.dat | 11 | 11.10 | 9.12 | 23.53 | 47.14 |
| KY12-09_bathymetry_dmo::20120715.dat | 22 | 2.48 | 13.12 | 35.17 | 74.42 |
| KR03-01_bathymetry_dmo::20030114.dat | 756 | 1.55 | 14.56 | 45.21 | 93.08 |
| KR11-04_leg1_bathymetry_dmo::20110220.dat | 60 | 8.55 | 7.54 | 55.08 | 117.70 |

## Cruise bias summary

| Stat | Value |
|------|-------|
| Total cruises with overlap | 45 |
| Suspicious cruises | 12 |

### Top 10 cruises by |median residual|

| cruise_id_guess | n_overlap | median_res | mad | rmse | p95_abs |
|------------------|-----------|------------|-----|------|---------|
| KY07-11 | 89 | -2.13 | 23.59 | 71.42 | 169.97 |
| KR05-17 | 90 | -7.07 | 21.00 | 47.82 | 104.65 |
| KR02-13 | 1270 | 11.24 | 19.27 | 68.30 | 114.43 |
| KY08-03 | 11 | -8.92 | 15.24 | 26.25 | 46.55 |
| KY13-13 | 122 | -4.11 | 17.95 | 89.43 | 200.55 |
| KY15-15 | 33 | 2.77 | 18.35 | 94.49 | 200.19 |
| MR03-K03 | 11 | 11.10 | 9.12 | 23.53 | 47.14 |
| KY12-09 | 22 | 2.48 | 13.12 | 35.17 | 74.42 |
| KR03-01 | 756 | 1.55 | 14.56 | 45.21 | 93.08 |
| KR11-04 | 60 | 8.55 | 7.54 | 55.08 | 117.70 |

## Subzip bias summary

| Stat | Value |
|------|-------|
| Total subzips with overlap | 47 |

## Suspicious counts

| Category | Count |
|----------|-------|
| Suspicious files | 12 |
| Suspicious cruises | 12 |
| Suspicious cells | 7 |

## Thresholds used (diagnostic only — no data removed)

| Threshold | Value |
|-----------|-------|
| min overlap file-cells (file/cruise) | 50 |
| |median residual| (file/cruise) | 20.0 m |
| MAD (file/cruise) | 20.0 m |
| RMSE (file/cruise) | 50.0 m |
| |residual| p95 (file/cruise) | 100.0 m |
| cell residual range | 100.0 m |
| cell residual IQR | 50.0 m |
| cell max |residual| | 100.0 m |
