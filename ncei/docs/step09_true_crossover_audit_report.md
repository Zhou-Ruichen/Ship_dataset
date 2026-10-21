# Step 09 — True singlebeam crossover audit (deliverable D2)

Generated: 2026-09-02T00:18:45Z  
Script: `ncei/trackline/crossover.py` (run from repo root)\
Interpreter: `/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python`  
Runtime: 40.7 s  
Task: `.trellis/tasks/09-02-sb-crossover-bias-arms/prd.md` (D2)

## Scope and question

How consistent is singlebeam depth where two SB tracks physically cross
inside the six frozen nested-GGM region tiles? Each crossing gives two
interpolated depths at the same geographic point; their difference is a
bias/noise observation built from raw points only. This audit feeds no
fitting and is NOT compared against the D1 per-track bias estimates
here (the reviewer does that).

## Method

Inputs: `ncei/derived/singlebeam/points_raw/*__nc.parquet` (`time` +
`point_index_in_track`) and `*__xyz.parquet` (order only), selected via
the trackline manifest bbox then filtered by exact point coordinates.
Hygiene: SB x SB only — no JAMSTEC or NCEI multibeam file is opened and
no cell product (in particular no `representative_depth_m`) is read;
the only freeze-file access is a lon/lat containment check of the tile
bboxes. Depth column: `depth_m_positive_down` (standardized, m).

- Points selected within tile bbox + 0.05 deg margin; only
  crossings inside the un-margined bbox are reported.
- Polyline continuity broken where consecutive points are not adjacent
  in `point_index_in_track` or spaced > 0.25 deg. In-region
  steps beyond this threshold are 0.027% of all in-region steps and
  correspond to leg gaps or bad jumps; connecting them would fabricate
  crossings. Break counts are reported per region below.
- Candidate segment pairs come from a 0.02 deg grid bucketing
  of segment-bbox cell coverage; the exact 2D segment intersection test
  then keeps pairs meeting in 0 <= t,u <= 1 (parallel/collinear pairs
  skipped and counted). Different track ids only — no self-crossings,
  and never a track against its own nc/xyz twin file: the
  standardization splits `nc_xyz_intersect` tracks into a `__nc` and a
  `__xyz` side holding the same points, so crossing the two sides
  compares identical data (observed |diff| ~ 1e-13 m). Twin ids are
  excluded from candidate pairing and counted per region below.
- Depth (and nc time) at the crossing: linear interpolation between the
  two bracketing points of each track's segment (fraction in lon/lat).
- Difference convention: `diff_m = depth_second - depth_first`. For
  nc x nc pairs first = earlier by the interpolated crossing time
  (`ordering_basis = 'time'`); pairs containing an xyz track have no
  usable time and use a recorded arbitrary order (nc before xyz, then
  track_id ascending; `ordering_basis = 'arbitrary'`). Signed statistics
  of arbitrary-order aggregates are orientation-dependent; the |diff|
  statistics are not.
- Vertex-sharing duplicate detections (same pair within 1e-07
  deg, ~1 cm) collapse to one event. Events with a non-finite
  interpolated depth on either side are dropped (counted).
- nc time QC (full track, not just the tile): monotonicity = all
  consecutive steps non-decreasing over present times; tracks with any
  missing time are reported separately. Epoch sanity = present times
  within [1930-01-01T00:00:00, 2035-01-01T00:00:00].
- Resumability: minimal skip-if-exists convention — without
  `--overwrite` the script does nothing when all six per-region
  crossover parquets exist, so a rerun changes no file. Runtime is
  small enough that full recompute with `--overwrite` is the only
  recovery path.

NMAD = 1.4826 * median(|x - median(x)|).

## Per-region results

### lon068_lat018 (lon 160..165, lat 0..5)

Tracks used: 58 (21 nc, 37 xyz); 21 track ids have an nc/xyz twin file present (excluded from pairing); 52724 in-margin points; 52627 segments (27 gap breaks, 12 zero-length dropped).

| pair type | track pairs | crossovers | median \|diff\| (m) | p90 \|diff\| (m) | NMAD \|diff\| (m) | median signed (m) | NMAD signed (m) |
|---|---:|---:|---:|---:|---:|---:|---:|
| nc_x_nc | 30 | 51 | 10.3 | 105.0 | 13.6 | 3.3 | 11.9 |
| nc_x_xyz | 122 | 415 | 11.6 | 105.4 | 15.6 | 2.1 | 17.9 |
| xyz_x_xyz | 209 | 810 | 34.5 | 105.4 | 50.4 | -12.4 | 50.9 |

Event pipeline: 100662 candidate segment pairs -> 2065 intersecting (162 parallel/collinear skipped) -> 1787 inside bbox -> 1280 with finite depths (507 dropped NaN) -> 1276 after dedup (4 vertex duplicates).

nc time QC: 21 nc tracks; 0 with missing time values; 1 monotonicity violations (1 backward steps total); 0 epoch violations; time span 1963-05-21 23:15:00 .. 1988-12-30 19:45:00.

### lon052_lat018 (lon 80..85, lat 0..5)

Tracks used: 58 (15 nc, 43 xyz); 15 track ids have an nc/xyz twin file present (excluded from pairing); 163526 in-margin points; 158015 segments (42 gap breaks, 5411 zero-length dropped).

| pair type | track pairs | crossovers | median \|diff\| (m) | p90 \|diff\| (m) | NMAD \|diff\| (m) | median signed (m) | NMAD signed (m) |
|---|---:|---:|---:|---:|---:|---:|---:|
| nc_x_nc | 14 | 24 | 7.3 | 4499.0 | 8.4 | -4.3 | 11.7 |
| nc_x_xyz | 141 | 203 | 7.5 | 32.7 | 7.8 | 4.1 | 9.7 |
| xyz_x_xyz | 381 | 1059 | 3.3 | 30.0 | 4.1 | 0.8 | 4.7 |

Event pipeline: 29174912 candidate segment pairs -> 1736 intersecting (2173678 parallel/collinear skipped) -> 1574 inside bbox -> 1286 with finite depths (288 dropped NaN) -> 1286 after dedup (0 vertex duplicates).

nc time QC: 15 nc tracks; 0 with missing time values; 0 monotonicity violations (0 backward steps total); 0 epoch violations; time span 1963-07-11 10:45:00 .. 1986-07-28 03:15:00.

### lon058_lat012 (lon 110..115, lat -30..-25)

Tracks used: 59 (16 nc, 43 xyz); 16 track ids have an nc/xyz twin file present (excluded from pairing); 137063 in-margin points; 136530 segments (31 gap breaks, 443 zero-length dropped).

| pair type | track pairs | crossovers | median \|diff\| (m) | p90 \|diff\| (m) | NMAD \|diff\| (m) | median signed (m) | NMAD signed (m) |
|---|---:|---:|---:|---:|---:|---:|---:|
| nc_x_nc | 37 | 71 | 30.6 | 165.2 | 34.2 | -1.6 | 44.0 |
| nc_x_xyz | 212 | 736 | 25.4 | 242.8 | 30.2 | -6.0 | 39.4 |
| xyz_x_xyz | 401 | 1768 | 19.3 | 226.0 | 24.4 | 2.4 | 28.8 |

Event pipeline: 689222 candidate segment pairs -> 2837 intersecting (2589 parallel/collinear skipped) -> 2808 inside bbox -> 2578 with finite depths (230 dropped NaN) -> 2575 after dedup (3 vertex duplicates).

nc time QC: 16 nc tracks; 0 with missing time values; 3 monotonicity violations (1300 backward steps total); 0 epoch violations; time span 1962-06-22 10:55:00 .. 2001-12-02 04:59:00.

### lon059_lat015 (lon 115..120, lat -15..-10)

Tracks used: 71 (20 nc, 51 xyz); 20 track ids have an nc/xyz twin file present (excluded from pairing); 63819 in-margin points; 63644 segments (72 gap breaks, 32 zero-length dropped).

| pair type | track pairs | crossovers | median \|diff\| (m) | p90 \|diff\| (m) | NMAD \|diff\| (m) | median signed (m) | NMAD signed (m) |
|---|---:|---:|---:|---:|---:|---:|---:|
| nc_x_nc | 23 | 29 | 62.0 | 245.5 | 80.7 | 7.6 | 96.0 |
| nc_x_xyz | 148 | 263 | 62.9 | 453.0 | 82.9 | -1.1 | 94.8 |
| xyz_x_xyz | 340 | 714 | 39.0 | 415.5 | 50.6 | -1.3 | 57.9 |

Event pipeline: 135830 candidate segment pairs -> 1379 intersecting (258 parallel/collinear skipped) -> 1330 inside bbox -> 1006 with finite depths (324 dropped NaN) -> 1006 after dedup (0 vertex duplicates).

nc time QC: 20 nc tracks; 0 with missing time values; 1 monotonicity violations (1 backward steps total); 0 epoch violations; time span 1964-08-23 06:15:00 .. 1991-11-28 23:47:00.

### lon004_lat033 (lon -160..-155, lat 75..80)

Tracks used: 16 (2 nc, 14 xyz); 2 track ids have an nc/xyz twin file present (excluded from pairing); 185901 in-margin points; 178529 segments (65 gap breaks, 7291 zero-length dropped).

| pair type | track pairs | crossovers | median \|diff\| (m) | p90 \|diff\| (m) | NMAD \|diff\| (m) | median signed (m) | NMAD signed (m) |
|---|---:|---:|---:|---:|---:|---:|---:|
| nc_x_nc | 1 | 1 | 957.3 | 957.3 | 0.0 | 957.3 | 0.0 |
| nc_x_xyz | 13 | 49 | 901.7 | 2559.6 | 792.0 | 901.7 | 896.7 |
| xyz_x_xyz | 56 | 1810 | 20.9 | 343.8 | 26.1 | -4.6 | 32.5 |

Event pipeline: 245391 candidate segment pairs -> 1955 intersecting (5180 parallel/collinear skipped) -> 1945 inside bbox -> 1907 with finite depths (38 dropped NaN) -> 1860 after dedup (47 vertex duplicates).

nc time QC: 2 nc tracks; 0 with missing time values; 0 monotonicity violations (0 backward steps total); 0 epoch violations; time span 1993-08-17 04:37:42 .. 2006-08-26 17:15:19.998000145.

### lon021_lat010 (lon -75..-70, lat -40..-35)

Tracks used: 62 (5 nc, 57 xyz); 7 track ids have an nc/xyz twin file present (excluded from pairing); 67434 in-margin points; 67192 segments (64 gap breaks, 116 zero-length dropped).

| pair type | track pairs | crossovers | median \|diff\| (m) | p90 \|diff\| (m) | NMAD \|diff\| (m) | median signed (m) | NMAD signed (m) |
|---|---:|---:|---:|---:|---:|---:|---:|
| nc_x_nc | 6 | 38 | 20.3 | 138.1 | 25.1 | 11.0 | 33.7 |
| nc_x_xyz | 165 | 1019 | 44.4 | 533.3 | 59.0 | -3.5 | 63.8 |
| xyz_x_xyz | 946 | 3769 | 71.2 | 705.7 | 95.9 | -0.2 | 105.8 |

Event pipeline: 200837 candidate segment pairs -> 5246 intersecting (222 parallel/collinear skipped) -> 5110 inside bbox -> 4840 with finite depths (270 dropped NaN) -> 4826 after dedup (14 vertex duplicates).

nc time QC: 5 nc tracks; 0 with missing time values; 0 monotonicity violations (0 backward steps total); 0 epoch violations; time span 1971-12-05 14:00:00 .. 1988-02-10 16:16:00.

## Global summary

Six regions total: 12829 crossovers over 3245 track pairs.

| region | nc x nc | nc x xyz | xyz x xyz | all crossovers | median \|diff\| (m) |
|---|---:|---:|---:|---:|---:|
| lon068_lat018 | 51 | 415 | 810 | 1276 | 17.6 |
| lon052_lat018 | 24 | 203 | 1059 | 1286 | 4.2 |
| lon058_lat012 | 71 | 736 | 1768 | 2575 | 21.8 |
| lon059_lat015 | 29 | 263 | 714 | 1006 | 49.0 |
| lon004_lat033 | 1 | 49 | 1810 | 1860 | 22.5 |
| lon021_lat010 | 38 | 1019 | 3769 | 4826 | 63.8 |

## Output files

```text
ncei/derived/true_crossover_audit/
  crossovers_<tile>.parquet     one row per crossing event
  pair_stats_<tile>.parquet     n / median / NMAD per track pair
  track_stats_<tile>.parquet    per-track residual vs all partners
  nc_time_qc.parquet            full-track nc time QC (all regions)
  region_summary.parquet        region x pair-type summary table
  region_time_qc_summary.parquet
```

## Limitations

- Event depths are interpolated from RAW points (`points_raw`, pre-QC):
  no depth quality filter is applied (the PRD scopes QC to nc time). A
  crossing that lands on a segment adjacent to a bad sounding inherits
  it, so single-event values can be extreme (observed: a ~1319 -> 132 m
  spike next to a crossing in lon004_lat033 pulling one interpolation
  ~335 m off). Read the median/NMAD columns, not individual events.
- Strict geometric crossing: near-parallel or collinear co-located
  tracks contribute nothing (collinear candidate pairs are skipped and
  counted), and true crossings need both interpolated depths finite;
  nc tracks with high depth-missing rates lose events (counted per
  region as 'dropped NaN').
- nc x nc event counts are small in some tiles (e.g. 1 in
  lon004_lat033); read those medians with n in mind. Track-id twin
  pairs (same survey as nc and xyz files) are excluded by design.

## Reproduction

```bash
cd /mnt/data2/00-Data/ship
/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python -m ncei.trackline crossover --overwrite
```
