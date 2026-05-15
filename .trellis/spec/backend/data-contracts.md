# Data Contracts

> Schemas that downstream stages depend on. Treat these as breaking-change
> boundaries: adding a column is fine, removing or renaming one is not.

Authoritative per-stage report files in `jamstec/multibeam/docs/` always win
over this document if they disagree — but please update this file when
they do.

---

## `file_id` (cross-stage primary key)

Format:
```
<subzip_name>::<basename>.dat
```
Example: `MR03-K02_bathymetry_dmo::20030527.dat`

Rules:
- Always a string. Never reconstructed from filesystem normalization.
- The `::` separator is canonical; the parquet *filename* uses `__`
  (see `database-guidelines.md`) but the column value keeps `::`.
- Joins across all stages MUST use `file_id`.

### `cruise_id_guess` ship prefixes (all JAMSTEC)

Despite the misleading `jamstec/multibeam/` directory name, every cruise
prefix in this dataset is a JAMSTEC research vessel:

| Prefix | Vessel | Operator |
|---|---|---|
| `KY` | R/V Kaiyo | JAMSTEC |
| `KR` | R/V Kairei | JAMSTEC |
| `KM` | R/V Kaimei | JAMSTEC |
| `MR` | R/V Mirai | JAMSTEC |
| `KS` | R/V Kairei sonar | JAMSTEC |
| `KH` | R/V Hakuho-maru | U. Tokyo ORI (JAMSTEC collaboration) |

See `docs/experiments/2026-05_dataset-source-attribution.md` for why the
directory is named `jamstec/multibeam` despite holding JAMSTEC data, and
why the regex in `01_build_multibeam_manifest.py` only matches these
prefixes.

---

## Point table (`derived/points_raw/*.parquet`, `derived/points_qc/*.parquet`)

Output of Step 02; carried through Step 03 with QC columns appended.
Authoritative source: `jamstec/multibeam/docs/point_schema_v1.md`.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `file_id` | string | no | FK |
| `point_index_in_file` | int64 | no | 0-based |
| `lon_raw` | float64 | no | original, may be `[0, 360)` |
| `lat_raw` | float64 | no | |
| `lon` | float64 | no | normalized `[-180, 180)`: `((lon_raw + 180) % 360) - 180` |
| `lat` | float64 | no | = `lat_raw` |
| `depth_m_positive_down` | float64 | no | meters, positive down |
| `elev_m` | float64 | no | meters, = `-depth_m_positive_down` |
| `date_raw` | string | yes | only 6-col files |
| `time_raw` | string | yes | only 6-col files |
| `sonar_idx` | int64 | yes | only 6-col files |

Step 03 appends:

| Column | Type | Pass condition |
|---|---|---|
| `qc_valid_lon` | bool | `lon ∈ [-180, 180)` |
| `qc_valid_lat` | bool | `lat ∈ [-90, 90]` |
| `qc_depth_positive` | bool | `depth_m_positive_down > 0` |
| `qc_depth_not_extreme` | bool | `depth_m_positive_down ≤ 12000` |
| `qc_elev_negative` | bool | `elev_m < 0` |
| `qc_no_nan` | bool | core columns non-NaN |
| `qc_zero_depth` | bool | informational; **not** part of `qc_pass_basic` |
| `qc_pass_basic` | bool | all of the above except `qc_zero_depth` |
| `qc_reason` | string | comma-separated failure reasons; empty on pass |

**Contract**: do not redefine `qc_pass_basic` to include or exclude an
existing flag. To add a new check, add a new `qc_*` column AND a
composite (`qc_pass_basic_v2`) leaving `qc_pass_basic` stable for
existing consumers.

---

## File-cell table (`derived/file_cells_1min/*.parquet`)

Output of Step 04a — one file per source `.dat`, one row per
`(file_id, cell_id)` pair the file touches with `qc_pass_basic = True`.

Required columns:

| Column | Type | Notes |
|---|---|---|
| `file_id` | string | FK |
| `cell_id` | string | format `"1min_{lat_bin}_{lon_bin}"` |
| `lat_bin` | int64 | `floor((lat + 90) / cell_deg)` |
| `lon_bin` | int64 | `floor((lon + 180) / cell_deg)` |
| `lon_center` | float64 | `-180 + (lon_bin + 0.5) * cell_deg` |
| `lat_center` | float64 | `-90  + (lat_bin + 0.5) * cell_deg` |
| `n_points` | int64 | points contributing |
| `median_depth` | float64 | per-file median |
| `mean_depth` | float64 | per-file mean |
| `std_depth` | float64 | |
| `min_depth`, `max_depth`, `range_depth` | float64 | |

Cell-id formula MUST match exactly — Step 04b joins by `cell_id` string.

---

## Global cells table (`derived/cells_1min/cells.parquet`, `derived/cells_1min_qcfiltered/cells.parquet`)

Output of Step 04b (raw) and Step 06c (QC-filtered).

Required columns include all the geometry columns from file-cells, plus:

| Column | Type | Notes |
|---|---|---|
| `cell_id` | string | unique |
| `file_balanced_median_depth` | float64 | **canonical depth value** |
| `point_weighted_mean_depth` | float64 | reference / debugging |
| `n_file_cells` | int64 | files contributing to this cell |
| `n_files` | int64 | usually = n_file_cells; may differ if a file split |
| `n_cruises` | int64 | distinct cruise IDs |
| `n_points_total` | int64 | sum of all contributing files' n_points |
| `iqr_depth` | float64 | between-file-median IQR |
| `std_depth` | float64 | between-file-median std |
| `min_depth`, `max_depth`, `range_depth` | float64 | between-file-median spread |

The `qcfiltered` variant has identical schema; only the input set differs.

---

## File quality flags (`manifests/file_quality_flags_1min.parquet`)

Output of Step 06b.

| Column | Type | Notes |
|---|---|---|
| `file_id` | string | FK |
| `cruise_id` | string | from upstream manifest |
| `quality_flag` | string | one of: `keep`, `high_variance_review`, `review`, `exclude` |
| `quality_reason` | string | brief explanation |
| `exclude_from_primary_cells` | bool | `True` iff `quality_flag == 'exclude'` |

`exclude_from_primary_cells` is what Step 06c filters on. Don't compute
it ad hoc — read this column.

---

## Validation cells (`derived/validation_cells_1min/primary_ship_validation_cells_1min.parquet`)

Output of Step 07. **This is the project's main exported product.**

In addition to all `cells_1min_qcfiltered` columns, it adds:

| Column | Type | Notes |
|---|---|---|
| `quality_tier` | string | one of: `A_tier`, `B_tier`, `C_tier` |
| `validation_weight` | float64 | `1.0` / `0.7` / `0.4` for A/B/C |
| `tier_reason` | string | which threshold determined the tier |

Tier definitions: see [`quality-tiering.md`](./quality-tiering.md).

---

## Residual dataset (`derived/ship_supervised_residual_T1/ship_residual_dataset_T1.parquet`)

Output of Step 10. Built by joining validation cells with Step 08
per-product validation parquets.

Required columns (in addition to validation-cell columns):

| Column | Type | Notes |
|---|---|---|
| `ship_elev` | float64 | from validation cells (negative below sea level) |
| `<product>_elev` | float64 | one column per gridded product (GEBCO_2024, ETOPO_2022, SRTM15_V2.7, SDUST_2023, TOPO_25_1, SWOT_T1) |
| `target_residual_SWOT_T1` | float64 | `ship_elev - SWOT_T1_elev`. Sign: positive = SWOT shallower than ship |
| `split` | string | one of: `train`, `val`, `test` (when joined with split file) |
| `block_id` | string | 0.25° spatial block id (when joined with split file) |

Splits live in `splits/block025_stratified_seed42/{train,val,test}.parquet`
and reference the dataset by `(cell_id, split)`.

---

## Adding new contracts

1. Update this file *and* the per-stage `docs/<stage>_report.md`.
2. Add a new column with a new name; never mutate an existing column's
   type or semantics.
3. Bump a version suffix (`point_schema_v2.md`) only when the change is
   genuinely incompatible.
