# QC Points Report — sample

Generated: 2026-04-29T19:17:01.344198

## Summary

| Metric | Value |
|--------|-------|
| Files processed | 5 ok, 0 skipped, 0 errors |
| Total rows | 3,827,420 |
| QC pass | 3,827,420 (100.0000%) |
| QC fail | 0 (0.0000%) |
| Elapsed | 6.8s |

## QC Flag Failures (across all passing files)

| Flag | Fail count |
|------|------------|
| qc_valid_lon (lon outside [-180,180)) | 0 |
| qc_valid_lat (lat outside [-90,90]) | 0 |
| qc_depth_positive (depth <= 0) | 0 |
| qc_depth_not_extreme (depth > 12000) | 0 |
| qc_elev_negative (elev >= 0) | 0 |
| qc_no_nan (NaN in core fields) | 0 |
| qc_zero_depth (depth == 0) | 0 |

## Per-file pass rate distribution

| Stat | Value |
|------|-------|
| Min pass rate | 100.0000% |
| Max pass rate | 100.0000% |
| Mean pass rate | 100.0000% |
| Files at 100% | 5 / 5 |
| Files < 99% | 0 |
| Files < 90% | 0 |

### Worst 20 files by pass rate

| file_id | rows | pass | fail | pass_rate | reasons |
|----------|------|------|------|-----------|---------|
| KR10-10_leg2_bathymetry_dmo::20100821.dat | 2,612,605 | 2,612,605 | 0 | 100.0000% |  |
| KY07-11_bathymetry_dmo::20070831.dat | 260,661 | 260,661 | 0 | 100.0000% |  |
| KR05-17_bathymetry_dmo::20051222.dat | 393,008 | 393,008 | 0 | 100.0000% |  |
| KR13-08_bathymetry_dmo::20130506.dat | 231,825 | 231,825 | 0 | 100.0000% |  |
| KR03-01_bathymetry_dmo::20030114.dat | 329,321 | 329,321 | 0 | 100.0000% |  |
