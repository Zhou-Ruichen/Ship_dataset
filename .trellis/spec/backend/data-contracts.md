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

## NCEI cell-level quality flags (`ncei/derived/quality_flags_1min/cell_quality_flags_1min.parquet`)

Output of NCEI Step 06B (`ncei/code/12_apply_quality_policy.py`). One
row per Step 04B cell (23,636,397 total across 3 branches). Sidecar to
Step 04B cells; do not mutate upstream.

Authoritative source: spec §18.7 in
`.trellis/spec/backend/pipeline-design-decisions.md`.

31 columns in this exact order:

```
branch, cell_id, lon_bin, lat_bin,
quality_tier, evidence_class, validation_weight, branch_role,
use_for_primary_validation, use_for_supplementary_validation,
use_for_regional_experiment, sensitivity_only_flag,
exclude_from_primary, exclusion_or_review_reason,
matched_rule_id, matched_rule_priority, applied_rule_description,
rule_version,
n_unique_triples_total, n_points_pass_total, duplicate_ratio_cell,
n_track_cells, manual_review_any, manual_review_unique_triples_share,
low_evidence_flag, overlap_evidence_class, n_cross_branch_overlap,
lat_band_10deg, depth_bin,
auv_sentry_flag, source_risk_class
```

Enums:
- `branch` ∈ {`singlebeam`, `multibeam_ncei`, `regional_mrar`}
- `branch_role` ∈ {`supplementary_coverage`, `multibeam_supplement`,
  `regional_experiment`}
- `quality_tier` ∈ {`high_confidence`, `medium_confidence`,
  `low_confidence`, `review_or_sensitivity_only`}
- `evidence_class` ∈ {`within`, `cross`, `both`, `none`}
- `source_risk_class` includes `auv_sentry_highdup` (mb rule-9 cells),
  `high_dup_unsupported`, `low_evidence`, or empty.

Contract:
- `manual_review_any` NEVER excludes or upgrades a cell on its own
  (invariant; enforced by runtime assertion).
- `validation_weight` never 0; AUV-Sentry cells downweight to 0.55,
  not zero.
- `regional_mrar` cells have `exclude_from_primary=True` on ≥99.96% of
  rows; the 89 mrar cells with `exclude_from_primary=False` (rule 4
  cross-validated) still have `use_for_primary_validation=False`.

NCEI rule set lives in `.trellis/tasks/05-11-singlebeam-integration/research/quality_policy_enforced_rules.tsv`
(18 cols × 16 rows: 15 first_match + 1 invariant). Step 06B is the
only consumer.

---

## NCEI validation-cell products (`ncei/derived/validation_cells_1min/*.parquet`)

Output of NCEI Step 07B (`ncei/code/13_build_validation_cells.py`).
5 products under fixed source precedence
(`JAMSTEC mb > NCEI mb > NCEI sb high-confidence`; regional_mrar
never primary). Authoritative source: spec §19.

### `strict_primary_multibeam_cells.parquet` (2,398,774 rows)

JAMSTEC mb primary ⊕ NCEI mb primary. Verified `cell_id` disjoint
between the two sources (0 overlap; runtime-asserted). AUV Sentry
retained (n=8 cells, `validation_weight=0.55`, `auv_sentry_flag=True`,
`source_risk_class='auv_sentry_highdup'`).

Core columns (shared with all 5 products): `cell_id, lon_bin, lat_bin,
lon_center, lat_center, lat_band_10deg, source_provider, branch_role,
representative_depth_m, validation_weight, quality_tier,
evidence_class, auv_sentry_flag, source_risk_class,
n_unique_triples_total, n_points_pass_total, n_track_cells,
duplicate_ratio_cell, validation_product_version`.

- `source_provider` ∈ {`jamstec`, `ncei_multibeam`}.
- `evidence_class = 'jamstec_legacy'` for JAMSTEC rows (distinct from
  the §15 within/cross/both/none classes).

### `expanded_primary_ship_cells.parquet` (2,732,689 rows)

Strict primary ⊕ NCEI sb high-confidence gap-fill. Adds:
- `expanded_fill` (bool) — `True` for sb fill rows, `False` for the
  strict baseline.
- `precedence_resolution` (string) — empty for non-conflict rows,
  `jamstec_over_sb` / `ncei_mb_over_sb` etc. when a conflict was
  resolved. cell_id uniqueness asserted.

### `supplementary_singlebeam_cells.parquet` (12,277,633 rows; hive lat_band_10deg)

NCEI sb with `use_for_supplementary_validation=True`. All cells have
`branch_role='supplementary_coverage'`.

### `regional_mrar_experiment_cells.parquet` (9,019,383 rows; hive lat_band_10deg)

All M.rar cells. `branch_role='regional_experiment'`;
`sensitivity_only_flag` carried from Step 06B. Never enters primary
under any condition.

### `validation_cell_catalog.parquet` (24,029,705 rows; hive product_label)

Long-format membership UNION of strict + supplementary_sb + regional_mrar,
plus expanded-primary singlebeam membership rows. Adds `product_label` ∈
{`strict_primary_multibeam`, `supplementary_singlebeam`,
`regional_mrar_experiment`} and `final_primary_source` (the chosen
source for cells appearing in `expanded_primary_ship_cells`).

The catalog is not unique on `(cell_id, product_label)`: the
`supplementary_singlebeam` label intentionally includes 333,915 duplicate
membership rows for high-confidence singlebeam cells that also participate
in `expanded_primary_ship_cells` (`product_membership='expanded_primary_ship'`).
Use unique `cell_id` counts when comparing catalog membership to
`supplementary_singlebeam_cells.parquet`.

### Weight scale (do NOT rescale)

| source_provider | weight range |
|---|---|
| `jamstec` | {0.4, 0.7, 1.0} (legacy A/B/C) |
| `ncei_multibeam` | [0.1, 0.95] (Step 06B rule eval) |
| `ncei_singlebeam` | [0.1, 0.95] (Step 06B) |

Downstream consumers (Step 11+) choose how to combine the two scales;
Step 07B does not normalize them.

Tier mapping for JAMSTEC: `A → high_confidence`, `B → medium_confidence`,
`C → low_confidence`.

---

## Adding new contracts

1. Update this file *and* the per-stage `docs/<stage>_report.md`.
2. Add a new column with a new name; never mutate an existing column's
   type or semantics.
3. Bump a version suffix (`point_schema_v2.md`) only when the change is
   genuinely incompatible.
