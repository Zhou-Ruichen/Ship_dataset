# Format Audit Report

Generated: 2026-04-29T07:01:10.892379

**⚠️  SAMPLE MODE — not all files audited**

## Summary

- Total files scanned: 3129
- .dat files audited: 120
- Subzips: 744
- ok_xyz_3col: 114
- ok_xyz_6col_time_sonar_lonlatdepth: 6
- total ok: 120
- used_for_points=True: 120

## dat Status Breakdown

| status | count |
|--------|-------|
| ok_xyz_3col | 114 |
| ok_xyz_6col_time_sonar_lonlatdepth | 6 |

## Data Layout Distribution

| data_layout | count |
|-------------|-------|
| lon_lat_depth_3col | 114 |
| date_time_sonar_lon_lat_depth_6col | 6 |

## used_for_points

| value | count |
|-------|-------|
| True | 120 |

## Column Count Distribution (dat files)

| col_count | count |
|-----------|-------|
| 3.0 | 114 |
| 6.0 | 6 |

## Depth Sign

| depth_sign | count |
|------------|-------|
| positive | 120 |

## Track Kind

| track_kind | count |
|------------|-------|
| unknown_or_survey | 80 |
| transit | 40 |

## 6-column Usable Bathymetric Files

Found 6 files with 6-col date/time/sonar/lon/lat/depth format:

- `KY11-02_leg1_bathymetry_dmo/T20110205.dat`: cols=6.0 lines=535951.0 lon=[128.2078,132.2992] lat=[25.6736,25.9653] depth=[1081.10,7066.50]
- `KY11-02_leg1_bathymetry_dmo/T20110202.dat`: cols=6.0 lines=198366.0 lon=[135.5933,136.1256] lat=[25.5635,27.1431] depth=[368.71,5818.80]
- `KY11-02_leg1_bathymetry_dmo/T20110131.dat`: cols=6.0 lines=672961.0 lon=[137.6114,139.6670] lat=[31.5592,35.0726] depth=[218.18,4235.30]
- `KY11-02_leg1_bathymetry_dmo/T20110204.dat`: cols=6.0 lines=371169.0 lon=[132.2987,135.5698] lat=[25.5370,25.6906] depth=[1092.90,5058.40]
- `KY11-02_leg1_bathymetry_dmo/T20110206.dat`: cols=6.0 lines=136483.0 lon=[127.6521,128.2143] lat=[25.9450,26.0169] depth=[368.34,2159.30]
- `KY11-02_leg1_bathymetry_dmo/T20110201.dat`: cols=6.0 lines=461355.0 lon=[136.0725,137.6572] lat=[27.1292,31.5709] depth=[2972.50,5381.50]

## Non-standard Files

No non-standard dat files detected.


## Spatial Coverage (all usable dat files)

- Longitude: 89.9642 ~ 171.7539
- Latitude: -8.1074 ~ 42.0486
- Depth: 6.30 ~ 11051.99
