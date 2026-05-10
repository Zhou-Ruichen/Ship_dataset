# QC Points Report — full

Generated: 2026-04-29T20:37:37.550478

## Summary

| Metric | Value |
|--------|-------|
| Files processed | 5083 ok, 0 skipped, 0 errors |
| Total rows | 2,746,301,327 |
| QC pass | 2,746,301,327 (100.0000%) |
| QC fail | 0 (0.0000%) |
| Elapsed | 4608.9s |

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
| Files at 100% | 5083 / 5083 |
| Files < 99% | 0 |
| Files < 90% | 0 |

### Worst 20 files by pass rate

| file_id | rows | pass | fail | pass_rate | reasons |
|----------|------|------|------|-----------|---------|
| MR03-K02_bathymetry_dmo::20030527.dat | 621,836 | 621,836 | 0 | 100.0000% |  |
| MR03-K02_bathymetry_dmo::20030606.dat | 916,265 | 916,265 | 0 | 100.0000% |  |
| MR03-K02_bathymetry_dmo::20030529.dat | 564,804 | 564,804 | 0 | 100.0000% |  |
| MR03-K02_bathymetry_dmo::20030524.dat | 513,869 | 513,869 | 0 | 100.0000% |  |
| MR03-K02_bathymetry_dmo::20030528.dat | 597,426 | 597,426 | 0 | 100.0000% |  |
| MR03-K02_bathymetry_dmo::20030525.dat | 473,830 | 473,830 | 0 | 100.0000% |  |
| MR03-K02_bathymetry_dmo::20030522.dat | 533,684 | 533,684 | 0 | 100.0000% |  |
| MR03-K02_bathymetry_dmo::20030523.dat | 557,336 | 557,336 | 0 | 100.0000% |  |
| MR03-K02_bathymetry_dmo::20030521.dat | 365,453 | 365,453 | 0 | 100.0000% |  |
| MR03-K02_bathymetry_dmo::20030526.dat | 599,506 | 599,506 | 0 | 100.0000% |  |
| MR03-K02_bathymetry_dmo::20030530.dat | 537,227 | 537,227 | 0 | 100.0000% |  |
| MR03-K02_bathymetry_dmo::20030605.dat | 286,358 | 286,358 | 0 | 100.0000% |  |
| MR03-K02_bathymetry_dmo::20030601.dat | 629,145 | 629,145 | 0 | 100.0000% |  |
| MR03-K02_bathymetry_dmo::20030531.dat | 788,921 | 788,921 | 0 | 100.0000% |  |
| KR10-E04_bathymetry_dmo::T20101012.dat | 1,677,784 | 1,677,784 | 0 | 100.0000% |  |
| KR10-E04_bathymetry_dmo::T20101010.dat | 209,998 | 209,998 | 0 | 100.0000% |  |
| KR10-E04_bathymetry_dmo::T20101011.dat | 102,706 | 102,706 | 0 | 100.0000% |  |
| KR10-E04_bathymetry_dmo::T20101009.dat | 279,722 | 279,722 | 0 | 100.0000% |  |
| KM17-01_bathymetry_dmo::KM17-01_t.dat | 2,914,770 | 2,914,770 | 0 | 100.0000% |  |
| 20120501::20120501.dat | 699,986 | 699,986 | 0 | 100.0000% |  |
