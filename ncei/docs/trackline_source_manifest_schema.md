# NCEI trackline source manifest — schema

Schema of `ncei/manifests/trackline_source_manifest.parquet` (and the
TSV mirror), produced by `ncei/code/01_build_trackline_source_manifest.py`
(PR-E1).

26 columns, one row per source-side track. Two `.nc` files and two
`.xyz` files sharing the same `track_id` produce **two rows** (one per
source side) — the `source_completeness` column records the join
status. Manifest output is **dataset-level audit content**, not a
deduplicated per-track view.

Cross-reference: per-row classification logic lives in `_common/r2_classifier.py`
(R2 threshold + spatial-spread rule); per-track readers live in the
build script itself.

---

## Identification (5 columns)

| Column | Type | Semantics |
|---|---|---|
| `track_id` | string | Normalized track identifier — bare basename without extension (e.g. `70002`, `csio02rr`, `ra304-15`). The join key across `tracklines_nc/` and `tracklines_xyz/`. |
| `source_type` | string | `"ncei_nc"` for the `.nc` source side, `"ncei_xyz"` for the `.xyz` source side. |
| `source_completeness` | string | `"nc_only"`, `"xyz_only"`, or `"nc_xyz_intersect"`. Records which source side(s) carry this `track_id`. A track with both sources produces two rows, both labelled `nc_xyz_intersect`. |
| `source_path` | string | Path to the source file relative to `ncei/` root (e.g. `tracklines_nc/70002.nc`). |
| `source_archive` | string | Upstream archive name + provider lineage label (e.g. `total_tracklines_xyz.zip; provider 安德超`). Free text. |

## Geometry (7 columns)

| Column | Type | Semantics |
|---|---|---|
| `n_points` | int64 | Number of points in the track after lon/lat filtering (NaN-rejected). |
| `bbox_lon_min` | float64 | Minimum longitude across all valid points. |
| `bbox_lon_max` | float64 | Maximum longitude across all valid points. |
| `bbox_lat_min` | float64 | Minimum latitude across all valid points. |
| `bbox_lat_max` | float64 | Maximum latitude across all valid points. |
| `bbox_area_km2` | float64 | Bbox area on a haversine-like cos-lat projection: `(lon_max−lon_min) × (lat_max−lat_min) × cos(lat_mid)` in km². Zero or NaN when track collapses to a point. |
| `point_density_km2` | float64 | `n_points / bbox_area_km2`. `+inf` when `bbox_area_km2 == 0` (degenerate). NaN when bbox is undefined. |

## Field availability + raw depth diagnosis (7 columns)

| Column | Type | Semantics |
|---|---|---|
| `has_time` | bool | Whether the source side carries a `time` field (true for `.nc` MGD77+, false for bare `.xyz`). |
| `has_depth` | bool | Whether **any** usable (finite, non-NaN) depth value exists in the track. False → no bathymetry at all. |
| `has_gobs` | bool | Whether the source carries `gobs` (observed gravity). Only meaningful for `.nc`; always `False` for `.xyz`. |
| `has_faa` | bool | Whether the source carries `faa` (free-air anomaly). Only meaningful for `.nc`; always `False` for `.xyz`. |
| `depth_sign_raw` | string | Per-track depth-sign diagnosis. One of: `mostly_positive` (≥95% positive — positive-down / depth-below-sea), `mostly_negative` (≥95% negative — positive-up / elevation), `mixed_sign` (positive + negative both present, neither side ≥95%), `all_zero` (depths present but all zero), `no_depth_values` (depth field absent / all NaN). Standardization downstream **must** branch on this value per-track, not assume a global sign convention. |
| `depth_min_raw` | float64 | Minimum raw depth value as stored in the source file (sign-preserved). Populated for `.xyz` sources only; NaN for `.nc` sources (the netCDF reader records `depth_sign_raw` but does not currently extract finite depth extremes — `has_depth` + `depth_sign_raw` already cover the per-track diagnosis needs of PR-E1). NaN when `has_depth=False` for `.xyz`. |
| `depth_max_raw` | float64 | Maximum raw depth value as stored in the source file (sign-preserved). Populated for `.xyz` sources only; NaN for `.nc` (see `depth_min_raw` note). NaN when `has_depth=False` for `.xyz`. |

Note on the `mostly_positive` / `mostly_negative` cutoff: see the
threshold logic in `01_build_trackline_source_manifest.py:depth_sign`
(lines ~150–170). NCEI documentation says `.xyz` files are
negative-down (elevation convention); the 2026-05-19 full-corpus scan
found all 5,382 `.xyz` files to be `mostly_positive`. The empirical
per-track diagnosis is the source of truth — see
`ncei/tracklines_xyz/SOURCE.md` "Depth sign: documentation vs
observation (2026-05-19)".

## Classification (5 columns)

R2 classifier (defined in `_common/r2_classifier.py`) with thresholds:

- `R2_HARD_MB_POINTS = 1_000_000`
- `R2_HARD_SB_POINTS = 100_000`
- `R2_BBOX_KM2_CUTOFF = 5_000.0`
- `R2_DENSITY_PPKM2_CUTOFF = 50.0`

Rule: `n_points > 1M` → mb; `n_points < 100k` → sb;
`100k ≤ n_points ≤ 1M` → mb if `bbox_area_km2 < 5,000` OR
`point_density_km2 > 50`; else sb.

| Column | Type | Semantics |
|---|---|---|
| `instrument_class_pred` | string | `"singlebeam"` or `"multibeam"` — classifier prediction. |
| `classification_rule` | string | Which R2 rule branch fired: `hard_mb_points`, `hard_sb_points`, `borderline_bbox_below_cutoff`, `borderline_density_above_cutoff`, `borderline_default_sb`. Mirrors `R2Result.reason`. |
| `classification_review` | bool | `True` when the track should be eyeballed for manual override (set when any `review_reason` fires). |
| `review_reason` | string | Semicolon-joined list of review flags. Possible flags: the R2 rule reason itself (when `pred=mb`), `review_multibeam_candidate` (small, compact, dense sb), `review_high_density_small_track`, `borderline_default_singlebeam`. Empty string when no review is requested. |
| `manual_override` | string | Reserved for downstream manual annotation. Empty in the auto-generated manifest. PR-E2/E3 may consume this column to honor curator decisions. |

## Provenance (2 columns)

| Column | Type | Semantics |
|---|---|---|
| `source_author` | string | NetCDF global attribute `Author` (e.g. `"liyang"` for the 李杨-converted `.nc` archive). Null for `.xyz` sources (no attribute carrier). |
| `survey_id` | string | NetCDF global attribute `Survey_Identifier` (NGDC trackline ID inside the file). Null for `.xyz` sources. |

---

## Stable contract notes

- Adding a new column is fine; renaming or removing an existing one is
  a breaking change for PR-E2+ consumers.
- The 5-state `depth_sign_raw` enum is closed; any extension must
  preserve the existing 5 values' semantics.
- Threshold constants for the classifier (`R2_*`) are exported by
  `_common/r2_classifier.py` as module-level constants; the build script
  imports them at the top. The schema doc references them by reference,
  not by hard-coded duplication, so any future re-tuning in PR-E owns
  the single source of truth at the classifier module.

## References

- Script: `ncei/code/01_build_trackline_source_manifest.py`.
- Classifier + thresholds: `_common/r2_classifier.py`.
- Report (latest full run): `ncei/docs/trackline_source_manifest_report.md`.
- PRD: `.trellis/tasks/05-11-singlebeam-integration/prd.md`
  (PR-E1 section + "Finding 2026-05-19: 168 nc-only tracks have no
  usable depth").
- Source-side provenance: `ncei/SOURCE.md`,
  `ncei/tracklines_nc/SOURCE.md`, `ncei/tracklines_xyz/SOURCE.md`.
