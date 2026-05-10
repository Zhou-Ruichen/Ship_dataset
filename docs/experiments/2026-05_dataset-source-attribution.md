# Data Source Attribution — `NCEI_multibeam/` is actually JAMSTEC

> **Discovered**: 2026-05-06
> **Type**: Provenance correction — naming error, no data corruption
> **Impact**: Directory name is misleading; downstream documentation,
> citations, and acknowledgements need to credit JAMSTEC, not NCEI.

---

## TL;DR

The directory `/mnt/data2/00-Data/ship/NCEI_multibeam/` is **misnamed**.

- The 5,083 multibeam files inside are **all from JAMSTEC** (Japan Agency
  for Marine-Earth Science and Technology), not from NCEI.
- The naming likely came from the original archive being labelled
  `国外水深第一/第二部分.zip` (Chinese: "foreign bathymetry, parts 1 & 2"),
  which a downstream user appears to have re-classified as "NCEI" when
  setting up the local directory structure.
- All processing work in `NCEI_multibeam/code/`, the validation cells,
  and every report are correct **as data**; only the source attribution
  was wrong.
- The sibling directory `/mnt/data2/00-Data/ship/JAMSTEC/` (with 776
  cruise-named zips, 2016–2020+) is **also JAMSTEC** — a complementary
  later-years subset, not an unrelated dataset.

`NCEI_singlebeam/` is **correctly named** — its raw zip
(`/mnt/data2/00-Data/NCEI_singlebeam_tracks_raw_2018files.zip`) was
verified against the NCEI singlebeam track archive in a separate codex
investigation (notes saved at `~/.codex/ncei_singlebeam_README.md`).

---

## Evidence chain

The mistake was discovered by triangulation, not in a single conversation:

### 1. Cruise prefixes are all JAMSTEC ship codes

Every cruise ID extracted from the 5,083 files matches a JAMSTEC
research vessel:

| Code | Vessel | Operator | Files | Years |
|---|---|---|---:|---|
| `KY` | R/V Kaiyo | JAMSTEC | 1,680 | 2000–2015 |
| `KR` | R/V Kairei | JAMSTEC | 1,668 | 2001–2013 |
| `MR` | R/V Mirai | JAMSTEC | 1,259 | 2000–2007 |
| `KS` | R/V Kairei sonar | JAMSTEC | 72 | — |
| `KH` | R/V Hakuho-maru | U. Tokyo ORI (collab.) | 3 | — |

Source: `NCEI_multibeam/docs/航次清单_协作者审核.md` (auto-generated
2026-05-06 from the file manifest).

### 2. Spatial coverage is Japan-centric

80.1% of cells fall in the western Pacific (lon 100°–180°, lat −10°–50°);
the Atlantic and Southern Ocean are essentially empty. NCEI's archive is
global; JAMSTEC's is not. The coverage map matches a JAMSTEC-only origin.

The visualization sessions on 2026-05-06 (`look_at: 确认图中有 cartopy
海岸线底图（可见日本列岛、朝鲜半岛、中国海岸线）...`) flagged this
geographic concentration first.

### 3. Original archive name is in Chinese, not English

The two raw zips inside `NCEI_multibeam/` are
`国外水深第一部分.zip` (10.5 GB) and `国外水深第二部分.zip` (14.0 GB).
NCEI's public NetCDF distributions are not packaged or named this way;
the most likely origin is a Chinese-language re-archive of JAMSTEC data
that was already in someone's hands before being placed here.

### 4. The processing pipeline regex implicitly assumed JAMSTEC

When the pipeline was first scripted on 2026-04-29 (codex session
`019dd622-b3f4-70a3-9964-92a04fb502af`), the `cruise_id_guess` regex
specifically targeted JAMSTEC token patterns:

> `KRxx-xx / KMxx-xxx / KYxx-xx / KS-xx-x`

— which only matches JAMSTEC vessels. NCEI-archive cruise IDs do not
follow that pattern. The clue was sitting in the code from day one;
nobody crossed the wires until the geographic coverage plot demanded
an explanation.

### 5. The sibling `JAMSTEC/bathymetry_data/` is the same provenance

`JAMSTEC/bathymetry_data/` contains 776 cruise-named zips
(`KM16-01_leg1_bathymetry.zip`, `KH-18-J02C_bathymetry_dmo.zip`,
`KH-20-J01_bathymetry_dmo.zip` …). The naming convention
(`<cruise>_bathymetry[_dmo].zip`) is JAMSTEC's Data Management Office
convention, and the years skew **2016 onwards** — exactly the gap that
the 2026-05-06 reviewer report flagged as missing from `NCEI_multibeam`
("2016 年以后的数据是否应该包含但缺失了").

So the two directories are:

| Directory | Era | Naming | Source | Status |
|---|---|---|---|---|
| `NCEI_multibeam/` | 2000–2015 | bulk archive (`国外水深*.zip`) | JAMSTEC (mislabelled) | Pipeline complete (Step 00–11) |
| `JAMSTEC/bathymetry_data/` | 2016–2020+ | cruise-by-cruise zips | JAMSTEC (correctly named) | Raw only, no pipeline yet |

There may be partial file-level overlap between the two subsets. This is
the **first thing to check** when the JAMSTEC pipeline task starts — it
would be wasteful to re-process cruises that are already in
`NCEI_multibeam/`.

---

## Update 2026-05-11: Overlap analysis — they are 100% the same source

The "first thing to check" above was done. **The two directories are not
complementary subsets — they are the same archive in two stages of
processing.**

Method: compared `JAMSTEC/bathymetry_data/*.zip` basenames against
`NCEI_multibeam/raw/dat_by_subzip/` subdirectory names (= the 763
sub-zips that successfully extracted in 2026-04).

| Set | Count |
|---|---:|
| Common (already processed in NCEI from same source) | **763** |
| Only in NCEI (processed but no JAMSTEC zip) | **0** |
| Only in JAMSTEC (zip exists but not processed) | **13** |
| `NCEI_multibeam/raw/subzips_bad/` (from 2026-04 audit) | 13 |

Conclusions:

1. `JAMSTEC/bathymetry_data/` IS the source archive of `NCEI_multibeam/`.
   `国外水深第一/第二部分.zip` and `JAMSTEC/archive/bathymetry.7z` (25 GB)
   are the same JAMSTEC dataset packaged differently.
2. `NCEI_multibeam/` has already processed 763/776 = 98.3% of it. There
   is no separate "later years subset" to ingest.
3. The 13 "only in JAMSTEC" are exactly the 13 that `unzip` failed on in
   2026-04 — they may be recoverable by retrying extraction from the
   JAMSTEC copy. That recovery is now scoped as task
   `05-11-recover-bad-subzips`.
4. My earlier guess that JAMSTEC was "2016+ years" was wrong — its cruise
   prefixes span 2000–2022, fully overlapping NCEI_multibeam's coverage.

This rewrites the task graph: the original "build a JAMSTEC pipeline"
task no longer makes sense, replaced by a small recovery task.

### Singlebeam reuse note

While here, also confirmed that `NCEI_singlebeam/singlebeam.xyz` (3.1 GB,
flat 3-col dump) lost its per-track structure during merging, but the
raw `/mnt/data2/00-Data/NCEI_singlebeam_tracks_raw_2018files.zip`
contains 2,021 per-track `.nc` files (MGD77+). When the singlebeam
pipeline is built, **build from the raw `.nc` archive**, not from
`singlebeam.xyz` — this preserves per-track structure and unlocks ~80%
algorithmic reuse from the multibeam pipeline (only `02_standardize`
needs a real rewrite for NetCDF input, and Step 07 tier thresholds need
re-calibration for singlebeam point density). Scoped under task
`05-11-singlebeam-integration`, which now also bundles the long-pending
directory rename (`NCEI_multibeam → multibeam_jamstec`,
`NCEI_singlebeam → singlebeam_ncei`) as a coordinated refactor.

---

## What does *not* need to change

- **Don't rename the directory.** Every script in
  `NCEI_multibeam/code/` resolves paths from
  `Path(__file__).parent.parent`, and dozens of report files / parquet
  paths embed the string "NCEI_multibeam". Renaming would break
  resumability across the whole pipeline. The label is wrong; the
  artifacts are right.
- **Don't re-run the pipeline.** The data values, QC flags, quality
  tiers, and validation cells are unaffected by the naming error.
- **Don't change `cruise_id_guess` regex or `file_id` strings.** They are
  load-bearing keys across stages.

## What did change (after this discovery)

1. `.trellis/spec/backend/index.md` — header note that flags the naming
   error.
2. `.trellis/spec/backend/directory-structure.md` — top-level layout
   table now annotates `NCEI_multibeam/` as "JAMSTEC data, misnamed".
3. `.trellis/spec/backend/data-contracts.md` — `file_id` and
   `cruise_id_guess` sections explain the JAMSTEC ship-code prefixes.
4. `.trellis/tasks/05-11-jamstec-pipeline/task.json` — description now
   prioritizes the overlap check between `JAMSTEC/bathymetry_data/` and
   `NCEI_multibeam/raw/subzips/`.
5. This document.

## What still needs human action (not done by AI)

- **External-facing artefacts**: any paper, slide, or dataset citation
  that credits the bathymetry data as "NCEI multibeam" must be corrected
  to JAMSTEC. Suggested citation: "Bathymetric soundings collected by
  JAMSTEC research vessels Kaiyo, Kairei, and Mirai (2000–2015),
  obtained via [origin of the `国外水深*.zip` archive — confirm with
  collaborator]."
- **Confirm with collaborator** (per
  `NCEI_multibeam/docs/航次清单_协作者审核.md` Section 5) where the
  `国外水深*.zip` archive originated, and whether it is the same export
  the JAMSTEC data center publishes directly.
- **Long-term**: consider renaming the directory in a future major
  refactor that comes with a path-rewrite script for all reports and
  manifests. Not urgent.

---

## Why this lives in `docs/experiments/`

This is a finished investigation with a definite conclusion, not an
ongoing constraint. Future investigations of similar character — data
provenance, retraction-style corrections, dataset audits — should follow
the same `YYYY-MM_<slug>.md` convention and land here.

Constraints derived from this discovery (cruise prefixes are JAMSTEC,
don't rename the directory, etc.) are reflected in `.trellis/spec/`.
