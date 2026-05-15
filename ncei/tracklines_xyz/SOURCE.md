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
2. **The 96 borderline files (100k–1M points)** are not pre-classified;
   the R2 classifier calibration scatter plot will determine each.
3. **First-row sentinel in sample file**: `00373.xyz` row 1 is
   `-20,35,5441` with unusually round coordinates and a depth too
   shallow for that lon/lat. Worth flagging during Step 02 standardize.

## References

- PRD: `.trellis/tasks/05-11-singlebeam-integration/prd.md` (Q2, Q6, Q7,
  Locked decisions #3, #4, #8).
- Investigation: `docs/experiments/2026-05_tmp-data-classification.md`
  (Finding 1 — size distribution, multibeam evidence, overlap analysis).
