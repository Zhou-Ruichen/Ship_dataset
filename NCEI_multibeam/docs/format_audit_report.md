# Format Audit Report

Generated: 2026-04-29T07:49:21.007015

## Summary

- Total files scanned: 8149
- .dat files audited: 5140
- Subzips: 763
- ok_xyz_3col: 5072
- ok_xyz_6col_time_sonar_lonlatdepth: 24
- total ok: 5096
- used_for_points=True: 5096

## dat Status Breakdown

| status | count |
|--------|-------|
| ok_xyz_3col | 5072 |
| invalid_lonlat_range | 44 |
| ok_xyz_6col_time_sonar_lonlatdepth | 24 |

## Data Layout Distribution

| data_layout | count |
|-------------|-------|
| lon_lat_depth_3col | 5072 |
| unknown_or_non_bathymetry | 44 |
| date_time_sonar_lon_lat_depth_6col | 24 |

## used_for_points

| value | count |
|-------|-------|
| True | 5096 |
| False | 44 |

## Column Count Distribution (dat files)

| col_count | count |
|-----------|-------|
| 3.0 | 5090 |
| 4.0 | 25 |
| 5.0 | 1 |
| 6.0 | 24 |

## Depth Sign

| depth_sign | count |
|------------|-------|
| positive | 5124 |
| mixed | 16 |

## Track Kind

| track_kind | count |
|------------|-------|
| unknown_or_survey | 4305 |
| transit | 835 |

## 6-column Usable Bathymetric Files

Found 24 files with 6-col date/time/sonar/lon/lat/depth format:

- `KY11-02_leg1_bathymetry_dmo/T20110205.dat`: cols=6.0 lines=535951.0 lon=[128.2078,132.2992] lat=[25.6736,25.9653] depth=[1081.10,7066.50]
- `KY11-02_leg1_bathymetry_dmo/T20110202.dat`: cols=6.0 lines=198366.0 lon=[135.5933,136.1256] lat=[25.5635,27.1431] depth=[368.71,5818.80]
- `KY11-02_leg1_bathymetry_dmo/T20110131.dat`: cols=6.0 lines=672961.0 lon=[137.6114,139.6670] lat=[31.5592,35.0726] depth=[218.18,4235.30]
- `KY11-02_leg1_bathymetry_dmo/T20110204.dat`: cols=6.0 lines=371169.0 lon=[132.2987,135.5698] lat=[25.5370,25.6906] depth=[1092.90,5058.40]
- `KY11-02_leg1_bathymetry_dmo/T20110206.dat`: cols=6.0 lines=136483.0 lon=[127.6521,128.2143] lat=[25.9450,26.0169] depth=[368.34,2159.30]
- `KY11-02_leg1_bathymetry_dmo/T20110201.dat`: cols=6.0 lines=461355.0 lon=[136.0725,137.6572] lat=[27.1292,31.5709] depth=[2972.50,5381.50]
- `KR11-01_bathymetry_dmo/20110113.dat`: cols=6.0 lines=583638.0 lon=[141.2913,142.0027] lat=[29.9250,31.6468] depth=[2187.80,7462.90]
- `KR11-01_bathymetry_dmo/T20110104.dat`: cols=6.0 lines=876374.0 lon=[139.6387,140.3475] lat=[31.5235,34.7603] depth=[125.52,2484.90]
- `KR11-01_bathymetry_dmo/20110112.dat`: cols=6.0 lines=525401.0 lon=[141.3084,142.5780] lat=[28.0529,29.9424] depth=[1156.30,6775.70]
- `KR11-01_bathymetry_dmo/20110114.dat`: cols=6.0 lines=460378.0 lon=[141.4232,142.9299] lat=[31.5707,32.3516] depth=[3274.70,10297.70]
- `KR11-01_bathymetry_dmo/T20110118.dat`: cols=6.0 lines=425187.0 lon=[139.4226,141.0067] lat=[33.3036,34.7860] depth=[78.22,10951.70]
- `KR11-01_bathymetry_dmo/20110111.dat`: cols=6.0 lines=675550.0 lon=[141.8557,142.5577] lat=[28.6270,30.0585] depth=[3180.60,6822.60]
- `KR11-01_bathymetry_dmo/20110115.dat`: cols=6.0 lines=82739.0 lon=[142.4830,142.7251] lat=[32.2062,32.3493] depth=[6011.70,7475.50]
- `KR11-01_bathymetry_dmo/20110109.dat`: cols=6.0 lines=494815.0 lon=[142.0194,142.7166] lat=[28.6795,29.6703] depth=[3769.90,10625.70]
- `KR11-01_bathymetry_dmo/T20110115.dat`: cols=6.0 lines=228582.0 lon=[140.3704,142.5665] lat=[32.2262,34.0770] depth=[1063.10,10557.70]
- `KR11-01_bathymetry_dmo/20110105.dat`: cols=6.0 lines=511817.0 lon=[140.6875,141.2335] lat=[28.9646,29.9603] depth=[1547.50,5922.20]
- `KR11-01_bathymetry_dmo/20110107.dat`: cols=6.0 lines=518038.0 lon=[142.9774,144.0204] lat=[25.2861,27.2867] depth=[2323.60,9059.30]
- `KR11-01_bathymetry_dmo/T20110105.dat`: cols=6.0 lines=318441.0 lon=[140.3137,140.7704] lat=[29.9478,31.5278] depth=[1072.40,3171.30]
- `KR11-01_bathymetry_dmo/20110110.dat`: cols=6.0 lines=87116.0 lon=[142.0629,142.3891] lat=[29.6215,30.2390] depth=[4237.40,7578.20]
- `KR11-01_bathymetry_dmo/20110106.dat`: cols=6.0 lines=709436.0 lon=[141.1584,143.8134] lat=[25.6989,29.0329] depth=[943.40,9443.70]
- `KR11-01_bathymetry_dmo/T20110119.dat`: cols=6.0 lines=312800.0 lon=[139.4893,139.8616] lat=[34.4525,35.1245] depth=[71.23,7482.70]
- `KR11-01_bathymetry_dmo/T20110117.dat`: cols=6.0 lines=385384.0 lon=[139.4711,139.7641] lat=[34.6937,35.0189] depth=[45.59,1994.40]
- `KR11-01_bathymetry_dmo/20110108.dat`: cols=6.0 lines=507789.0 lon=[142.6013,143.4654] lat=[27.0502,28.7232] depth=[3703.30,10180.70]
- `KR12-11_bathymetry_dmo/20120623.dat`: cols=6.0 lines=7672.0 lon=[142.0503,142.1548] lat=[32.8874,33.0992] depth=[8701.70,9674.70]

## Non-standard Files

Found 44 non-standard dat files:

- `MR01-K04_leg1_bathymetry_dmo/20010730.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=607007.0 notes=col_range: c1=[-180.02,179.52] c2=[38.97,39.74] c3=[3747.00,5627.30]; col1/col2 outside lon/lat bounds
- `MR07-06_leg1_bathymetry_pi/grid_p14.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=2098024.0 notes=col_range: c1=[-35.64,59.00] c2=[175.03,186.01] c3=[124.50,7464.20]; col1/col2 outside lon/lat bounds
- `MR07-06_leg1_bathymetry_pi/grid_p01.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=1689768.0 notes=col_range: c1=[39.66,47.09] c2=[145.45,235.05] c3=[98.40,7281.50]; col1/col2 outside lon/lat bounds
- `MR07-06_leg1_bathymetry_pi/dist_p01.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=117.0 notes=col_range: c1=[0.00,7405.20] c2=[39.69,47.03] c3=[-179.43,179.45]; col1/col2 outside lon/lat bounds
- `MR07-06_leg1_bathymetry_pi/track_p14.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=9951.0 notes=col_range: c1=[0.00,10701.00] c2=[-35.63,58.99] c3=[-180.00,180.00]; col1/col2 outside lon/lat bounds
- `MR07-06_leg1_bathymetry_pi/track_p01.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=6985.0 notes=col_range: c1=[0.00,7405.00] c2=[39.70,47.03] c3=[-179.98,179.98]; col1/col2 outside lon/lat bounds
- `MR07-06_leg1_bathymetry_pi/dist_p14.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=237.0 notes=col_range: c1=[0.00,10702.00] c2=[-35.63,59.00] c3=[-179.94,179.91]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg4_bathymetry_dmo/track_p06.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=12859.0 notes=col_range: c1=[0.00,12903.40] c2=[-32.52,-30.01] c3=[-180.00,179.99]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg4_bathymetry_dmo/track_i04.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=862.0 notes=col_range: c1=[0.00,861.00] c2=[-24.67,-24.66] c3=[35.37,43.87]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg4_bathymetry_dmo/grid_a10.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=2282875.0 notes=col_range: c1=[312.60,375.00] c2=[-30.27,-27.73] c3=[160.90,5625.30]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg4_bathymetry_dmo/track_i03.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=6779.0 notes=col_range: c1=[0.00,6851.90] c2=[-22.23,-19.98] c3=[48.91,113.76]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg4_bathymetry_dmo/track_a10.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=6121.0 notes=col_range: c1=[0.00,6136.90] c2=[-30.22,-27.73] c3=[-47.39,15.00]; col1/col2 outside lon/lat bounds
- `MR05-02_bathymetry_pi/track_p10r.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=5303.0 notes=col_range: c1=[0.00,5371.60] c2=[-4.01,42.25] c3=[143.74,149.36]; col1/col2 outside lon/lat bounds
- `MR05-02_bathymetry_pi/dist_p10r.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=5.0 lines=124.0 notes=col_range: c1=[0.00,5371.90] c2=[-4.01,42.25] c3=[143.74,149.36]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg1_bathymetry_dmo/track_p06.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=12859.0 notes=col_range: c1=[0.00,12903.40] c2=[-32.52,-30.01] c3=[-180.00,179.99]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg1_bathymetry_dmo/track_i04.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=862.0 notes=col_range: c1=[0.00,861.00] c2=[-24.67,-24.66] c3=[35.37,43.87]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg1_bathymetry_dmo/grid_a10.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=2282875.0 notes=col_range: c1=[312.60,375.00] c2=[-30.27,-27.73] c3=[160.90,5625.30]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg1_bathymetry_dmo/track_i03.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=6779.0 notes=col_range: c1=[0.00,6851.90] c2=[-22.23,-19.98] c3=[48.91,113.76]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg1_bathymetry_dmo/track_a10.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=6121.0 notes=col_range: c1=[0.00,6136.90] c2=[-30.22,-27.73] c3=[-47.39,15.00]; col1/col2 outside lon/lat bounds
- `MR07-05_bathymetry_dmo/20070906.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=706168.0 notes=col_range: c1=[-180.02,179.88] c2=[55.78,57.05] c3=[3670.10,3949.90]; col1/col2 outside lon/lat bounds
- `MR07-04_bathymetry_pi/grid_p14.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=2098024.0 notes=col_range: c1=[-35.64,59.00] c2=[175.03,186.01] c3=[124.50,7464.20]; col1/col2 outside lon/lat bounds
- `MR07-04_bathymetry_pi/grid_p01.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=1689768.0 notes=col_range: c1=[39.66,47.09] c2=[145.45,235.05] c3=[98.40,7281.50]; col1/col2 outside lon/lat bounds
- `MR07-04_bathymetry_pi/dist_p01.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=117.0 notes=col_range: c1=[0.00,7405.20] c2=[39.69,47.03] c3=[-179.43,179.45]; col1/col2 outside lon/lat bounds
- `MR07-04_bathymetry_pi/track_p14.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=9951.0 notes=col_range: c1=[0.00,10701.00] c2=[-35.63,58.99] c3=[-180.00,180.00]; col1/col2 outside lon/lat bounds
- `MR07-04_bathymetry_pi/track_p01.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=6985.0 notes=col_range: c1=[0.00,7405.00] c2=[39.70,47.03] c3=[-179.98,179.98]; col1/col2 outside lon/lat bounds
- `MR07-04_bathymetry_pi/dist_p14.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=237.0 notes=col_range: c1=[0.00,10702.00] c2=[-35.63,59.00] c3=[-179.94,179.91]; col1/col2 outside lon/lat bounds
- `MR00-K08_bathymetry_dmo/20010102.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=575165.0 notes=col_range: c1=[-180.01,179.72] c2=[28.61,30.72] c3=[4023.80,5750.10]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg2_bathymetry_dmo/track_p06.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=12859.0 notes=col_range: c1=[0.00,12903.40] c2=[-32.52,-30.01] c3=[-180.00,179.99]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg2_bathymetry_dmo/track_i04.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=862.0 notes=col_range: c1=[0.00,861.00] c2=[-24.67,-24.66] c3=[35.37,43.87]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg2_bathymetry_dmo/grid_a10.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=2282875.0 notes=col_range: c1=[312.60,375.00] c2=[-30.27,-27.73] c3=[160.90,5625.30]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg2_bathymetry_dmo/track_i03.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=6779.0 notes=col_range: c1=[0.00,6851.90] c2=[-22.23,-19.98] c3=[48.91,113.76]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg2_bathymetry_dmo/track_a10.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=6121.0 notes=col_range: c1=[0.00,6136.90] c2=[-30.22,-27.73] c3=[-47.39,15.00]; col1/col2 outside lon/lat bounds
- `MR00-K06_bathymetry_dmo/20001011.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=600889.0 notes=col_range: c1=[37.58,39.56] c2=[145.23,151.26] c3=[4744.90,6163.20]; col1/col2 outside lon/lat bounds
- `MR00-K06_bathymetry_dmo/20001008.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=294205.0 notes=col_range: c1=[47.80,49.61] c2=[158.21,162.43] c3=[4703.40,5861.00]; col1/col2 outside lon/lat bounds
- `MR00-K06_bathymetry_dmo/20001007.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=337880.0 notes=col_range: c1=[49.50,51.41] c2=[162.33,166.96] c3=[3244.10,5871.20]; col1/col2 outside lon/lat bounds
- `MR00-K06_bathymetry_dmo/20001010.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=517370.0 notes=col_range: c1=[37.56,40.03] c2=[150.93,151.61] c3=[4804.20,8040.20]; col1/col2 outside lon/lat bounds
- `MR00-K06_bathymetry_dmo/20001009.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=355900.0 notes=col_range: c1=[40.01,44.01] c2=[151.46,153.86] c3=[1499.20,8576.00]; col1/col2 outside lon/lat bounds
- `MR00-K06_bathymetry_dmo/20001012.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=1984402.0 notes=col_range: c1=[39.45,40.59] c2=[141.68,145.28] c3=[70.45,7593.90]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg5_bathymetry_dmo/track_p06.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=12859.0 notes=col_range: c1=[0.00,12903.40] c2=[-32.52,-30.01] c3=[-180.00,179.99]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg5_bathymetry_dmo/track_i04.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=862.0 notes=col_range: c1=[0.00,861.00] c2=[-24.67,-24.66] c3=[35.37,43.87]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg5_bathymetry_dmo/grid_a10.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=2282875.0 notes=col_range: c1=[312.60,375.00] c2=[-30.27,-27.73] c3=[160.90,5625.30]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg5_bathymetry_dmo/track_i03.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=6779.0 notes=col_range: c1=[0.00,6851.90] c2=[-22.23,-19.98] c3=[48.91,113.76]; col1/col2 outside lon/lat bounds
- `MR03-K04_leg5_bathymetry_dmo/track_a10.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=4.0 lines=6121.0 notes=col_range: c1=[0.00,6136.90] c2=[-30.22,-27.73] c3=[-47.39,15.00]; col1/col2 outside lon/lat bounds
- `MR01-K04_leg2_bathymetry_dmo/20010902.dat`: status=invalid_lonlat_range layout=unknown_or_non_bathymetry cols=3.0 lines=978717.0 notes=col_range: c1=[-179.39,180.02] c2=[53.30,55.77] c3=[466.05,4054.70]; col1/col2 outside lon/lat bounds

## Spatial Coverage (all usable dat files)

- Longitude: -179.9994 ~ 288.5040
- Latitude: -58.2682 ~ 76.5872
- Depth: 4.80 ~ 11895.00
