# Point Schema v1

Generated: 2026-04-29T18:41:46.996332

## Schema

Standardized point table for NCEI multibeam bathymetric data.

| Column                  | Type     | Nullable | Description |
|-------------------------|----------|----------|-------------|
| file_id                 | string   | No       | Foreign key to file_manifest.file_id (e.g. "MR03-K02_bathymetry_dmo::20030527.dat") |
| point_index_in_file     | int64    | No       | 0-based row index within the source .dat file |
| lon_raw                 | float64  | No       | Original longitude from source file (may be [0,360)) |
| lat_raw                 | float64  | No       | Original latitude from source file |
| lon                     | float64  | No       | Longitude normalized to [-180, 180). Formula: `((lon_raw + 180) % 360) - 180` |
| lat                     | float64  | No       | Latitude (= lat_raw) |
| depth_m_positive_down   | float64  | No       | Depth in meters, positive downward (original value) |
| elev_m                  | float64  | No       | Elevation in meters (= -depth_m_positive_down). Negative for below sea level. |
| date_raw                | string   | Yes      | Date string from 6-col files (e.g. "20110205"), null for 3-col files |
| time_raw                | string   | Yes      | Time string from 6-col files (e.g. "000002335"), null for 3-col files |
| sonar_idx               | int64    | Yes      | Sonar beam index from 6-col files, null for 3-col files |

## Data Sources

### lon_lat_depth_3col (5,072 files)
- Columns: lon lat depth
- lon_col=0, lat_col=1, depth_col=2
- date_raw, time_raw, sonar_idx: all null

### date_time_sonar_lon_lat_depth_6col (24 files)
- Columns: date time sonar_idx lon lat depth
- date_col=0, time_col=1, sonar_idx_col=2, lon_col=3, lat_col=4, depth_col=5
- date_raw, time_raw, sonar_idx: populated

## Design Decisions

1. **No metadata duplication**: Each row contains only `file_id`. Join with `file_manifest` for
   subzip_id, cruise_id_guess, track_kind, etc. Join with `points_raw_manifest` for per-file
   statistics (row counts, lon/lat/depth ranges).

2. **One Parquet per source .dat**: Output is `derived/points_raw/<file_id>.parquet` where
   file_id uses `__` instead of `::`. Large files are written chunk-by-chunk but into a single
   Parquet file using PyArrow's chunked writer.

3. **Lon normalization**: All lon values are converted to [-180, 180) using the formula
   `((lon_raw + 180) % 360) - 180`. Files with lon in [0,360) will be converted correctly.

4. **Depth convention**: depth_m_positive_down is always positive (depth below sea level).
   elev_m = -depth_m_positive_down is always negative (below sea level).

5. **Resumable**: If output Parquet exists and --overwrite is not set, the file is skipped.

## Relationships

```
file_manifest (1) -- (1) points_raw_manifest   [by file_id]
file_manifest (1) -- (N) points_raw/*.parquet   [by file_id]
```
