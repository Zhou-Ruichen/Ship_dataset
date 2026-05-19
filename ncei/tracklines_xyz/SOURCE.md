# SOURCE — `ncei/tracklines_xyz/`

> Flat-CSV trackline bundle from NCEI, mixed singlebeam + multibeam.
> The pipeline's R2 classifier (planned for PR-D) does the sb/mb split
> at runtime; this dir holds the raw mixed bundle.

## Provenance

- **Provider**: 安德超 (2026-05-15 hand-off via `/mnt/data2/00-Data/tmp/`).
- **Source archive**: `total_tracklines_xyz.zip` (854 MB compressed,
  3.3 GB uncompressed). Relocated 2026-05-16 from `tmp/` to
  `ncei/archive/source_zips/` as part of PR-C.
- Filenames follow NCEI **GEODAS** trackline ID conventions: 5-digit
  numeric (`00373`, `04883`, `82116`) + alphanumeric legacy IDs
  (`107a23`, `1986n1a`, `ztes6bar`, `hu77024`, `odp173jr`).

## Contents

- **5,382 `.xyz` files** as immediate children of this dir.
- Each file is a 3-column CSV with header `LON,LAT,CORR_DEPTH`.
- **Total payload**: 3.2 GB unpacked.

Original zip wrapped everything under `total_tracklines_xyz/`; PR-C
flattens that wrapper.

## File-count reconciliation

- The zip header reports **5,383 files** (counts the wrapping
  `total_tracklines_xyz/` dir entry as 1 file).
- After extraction: **5,382 .xyz files** + 1 wrapper dir = 5,383 entries.
- → Definitive .xyz count: **5,382**, not 5,383. PRD / investigation
  doc references to "5,383 .xyz files" are off-by-one (counting the
  dir entry); the true file count is 5,382.

## Composition (mixed sb/mb bundle)

Per the investigation doc, file-size distribution implies sonar type:

| Implied points | Files | Share | Likely sonar |
|---|---:|---:|---|
| < 5k | 2,910 | 54.1% | Short singlebeam |
| 5k–100k | 2,364 | 43.9% | Typical singlebeam |
| 100k–1M | 96 | 1.8% | Borderline (needs classifier) |
| **> 1M** | **12** | **0.2%** | **Confirmed multibeam** |

The 12 confirmed-multibeam files:
- `ra022-3.xyz`, `ra304-15.xyz` — R/V Atlantis cruises (RA series).
  `ra304-15` has 4,791,753 points across 130k km² — a multibeam swath.
- `sentry418.xyz` through `sentry428.xyz` (10 files, 2.1M–4.1M points
  each) — **AUV Sentry**, WHOI autonomous underwater vehicle carrying
  high-resolution multibeam sonar.

→ The pipeline-stage R2 classifier (PR-D) routes these to
`ncei/derived/multibeam/`; the bulk of singlebeam tracks go to
`ncei/derived/singlebeam/`. Classifier rule (PRD Q2):
- `>1M points` → multibeam.
- `100k–1M points` → multibeam if `bbox < 5,000 km²` OR
  `density > 50 pts/km²`; else singlebeam.
- `<100k points` → singlebeam.

## Overlap with `tracklines_nc/`

Basename set comparison (2026-05-15):

| Set | Count |
|---|---:|
| xyz unique basenames | 5,382 |
| nc unique basenames | 2,018 |
| Intersect | 1,850 |
| Only in xyz (new) | 3,532 |
| Only in nc | 168 |

→ Union strategy required; `source_completeness` manifest column
records each track's source side(s).

## Known unknowns

1. **Why are 168 nc tracks missing from this xyz bundle?** Could be
   upstream pipeline filtering, bug, or deliberate exclusion. Recorded
   as known unknown; ingest proceeds via union (see
   `ncei/tracklines_nc/SOURCE.md`).
   - **[2026-05-19 update — resolved]**: PR-E1 full manifest reveals
     all 168 nc-only tracks have `has_depth=False` (FAA / gravity-only
     tracklines). NCEI's upstream `.xyz` export filter rule is "track
     has usable depth"; the 168 were correctly excluded. Full evidence
     in `tracklines_nc/SOURCE.md` and PRD section "Finding 2026-05-19".
2. **The 96 borderline files (100k–1M points)** are not pre-classified;
   the R2 classifier calibration scatter plot will determine each.
3. **First-row sentinel in sample file**: `00373.xyz` row 1 is
   `-20,35,5441` with unusually round coordinates and a depth too
   shallow for that lon/lat. Worth flagging during Step 02 standardize.

## Depth sign: documentation vs observation (2026-05-19)

The PRD's Pre-PR-E gate 1 (line 605-611) cites NCEI's `.xyz`
documentation as saying XYZ depths are **negative**
(positive-up / elevation convention). The PR-E1 full-corpus manifest
scan contradicts that:

- All 5,382 `.xyz` files in this bundle are classified
  `depth_sign_raw="mostly_positive"` (positive-down / depth-below-sea
  convention).
- Sample: `00373.xyz` → `depth_min_raw=69.0, depth_max_raw=5441.0`
  (both finite, both positive).
- No files in this corpus are tagged `mostly_negative`, `all_zero`,
  or `no_depth_values`.

### Decision

**Trust observed raw sign per-track**, not the upstream documentation.
PR-E2 / PR-E3 standardization uses the per-track `depth_sign_raw`
diagnosis from the manifest as the source of truth; the standardizer
must NOT silently assume any global sign convention from the docs.

### Treatment

- Recorded here as a known anomaly. No active investigation of the
  NCEI documentation is planned — the empirical signal is unambiguous
  and uniform across the full bundle.
- PR-E2/E3 standardization will write the normalized
  `depth_m_positive_down` column based on `depth_sign_raw` per-track,
  not a global assumption.

## Depth sentinel (PR-F clip, 2026-05-19b)

PR-F audit pass identified 13 xyz tracks (all `instrument_class_pred=
singlebeam`) whose raw `depth_max` exceeds the Mariana Trench
(~10,994 m). These are sentinel / unit-error pollution from upstream,
not real bathymetry. Sorted worst-first (per `xyz_points_raw_manifest.parquet`
before clip):

| track_id | depth_max raw (m) | n_clipped (after clip) |
|---|---:|---:|
| `ant4`     | 87,178 | 1  |
| `wi343802` | 75,000 | 5  |
| `ant8`     | 52,002 | 1  |
| `so36`     | 44,215 | 1  |
| `so16`     | 27,760 | 2  |
| `91039`    | 23,233 | 8  |
| `so49`     | 12,386 | 1  |
| `rr1108`   | 11,966 | 4  |
| `rr1112`   | 11,960 | 7  |
| `rr1106`   | 11,928 | 6  |
| `rr1110`   | 11,923 | 3  |
| `mv0902`   | 11,752 | 1  |
| `rr1109`   | 11,707 | 3  |

The `91039`, `so16`, `so49` tracks appear in **both** nc and xyz
with the same sentinels (cross-bundle correlation → genuine upstream
pollution, not a format-specific artifact). The `rr11xx` + `mv0902`
cluster sits just over the 11,500 m cutoff (11,707–11,966 m).

**Policy** — `03_standardize_xyz.py` applies a universal upper clip:
`depth_m_positive_down > 11,500 m → NaN`. `depth_raw` is preserved
verbatim in the per-track parquet for audit; only
`depth_m_positive_down` and `elev_m` are NaN'd for over-clip rows.
Per-track clip counts land in the `n_clipped` column of the aggregate
manifest. Symmetric with the M.rar lower-bound clip
(`depth < -11,500 m → nodata`, PRD Q3) and the nc-side clip applied
by `02_standardize_singlebeam.py`. Full per-track table and spec
ratification (decision #12) in PRD section "Finding 2026-05-19b" +
`.trellis/spec/backend/pipeline-design-decisions.md` §12.

## References

- PRD: `.trellis/tasks/05-11-singlebeam-integration/prd.md` (Q2, Q6, Q7,
  Locked decisions #3, #4, #8).
- Investigation: `docs/experiments/2026-05_tmp-data-classification.md`
  (Finding 1 — size distribution, multibeam evidence, overlap analysis).
