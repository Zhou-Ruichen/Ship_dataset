# M.rar Cleaning Report (PR-F)

Generated: 2026-05-19T21:30:12.529780+00:00
Run label: `full`
Cleaning version: `mrar_v0.1.0`
Elapsed: 150.4s

## Rules

- `depth_raw > 0` → land mask (sidecar).
- `depth_raw < -11500` → nodata sentinel, dropped.
- `-11500 ≤ depth_raw ≤ 0` → bathymetry, kept; sign-flipped to positive-down.

## Per-quadrant cleaning split

| quadrant | rows_in | rows_land | rows_nodata | rows_bathymetry | rows_nan_depth |
| --- | --- | --- | --- | --- | --- |
| 0-180E-0-85N.txt | 38635741 | 6218 | 38672 | 38590851 | 0 |
| 0-90W-0-85S.txt | 25295079 | 49 | 8414 | 25286616 | 0 |
| 90-180W-0-85S.txt | 49480083 | 0 | 968 | 49479115 | 0 |
| TOTALS | 113410903 | 6267 | 48054 | 113356582 | 0 |

## Per-quadrant ranges

| quadrant | lon_min | lon_max | lat_min | lat_max | depth_min_bathy_raw | depth_max_bathy_raw |
| --- | --- | --- | --- | --- | --- | --- |
| 0-180E-0-85N.txt | 0.000 | 180.003 | 0.000 | 84.994 | -11500.000 | 0.000 |
| 0-90W-0-85S.txt | -90.000 | 0.001 | -73.225 | -0.001 | -11500.000 | -10.000 |
| 90-180W-0-85S.txt | -180.000 | -89.997 | -78.676 | -0.001 | -11499.000 | -5.000 |
| TOTALS | -180.000 | 180.003 | -78.676 | 84.994 | -11500.000 | 0.000 |

## Output paths

- Bathymetry parquet: `ncei/archive/zhoushuai_processed_M/bathymetry_points.parquet`
- Land mask parquet: `ncei/archive/zhoushuai_processed_M/land_mask.parquet`
- Audit parquet: `ncei/archive/zhoushuai_processed_M/cleaning_audit.parquet`
