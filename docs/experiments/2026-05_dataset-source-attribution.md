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
   JAMSTEC copy. That recovery was scoped as task
   `05-11-recover-bad-subzips`, investigated, and **deliberately
   skipped** (2026-05-11): the JAMSTEC copies turned out to be
   byte-identical to the bad copies (same source archive, same
   corruption), and the salvageable share via per-entry extraction
   (~1.5% of cruises, ~3% of data) was below the threshold worth the
   recovery effort. Full investigation, per-cruise breakdown, and
   revive-ready recovery design preserved at
   `.trellis/tasks/archive/2026-05/05-11-recover-bad-subzips/prd.md`;
   sidecar status note at
   `NCEI_multibeam/docs/bad_subzips_investigation_2026-05.md`.
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

**[2026-05-16 correction]** Empirical row-count + per-track density
measurements taken after PR-C landed show this paragraph's implicit
claim — that `singlebeam.xyz` is a merged form of the per-track `.nc`
archive — is wrong. The actual relationship picture:

```
NCEI upstream archive
  ├─ per-track .nc snapshot (curated; mb pre-filtered) → tracklines_nc/    28.9M points / 2,018 files
  └─ per-track .xyz snapshot (raw; mb mixed in)         → tracklines_xyz/  123.4M points / 5,382 files
                                                              │
                                                              │ flat merge (lossy)
                                                              ▼
                                                      孙明智 singlebeam.xyz   114.5M points
                                                      (≈ tracklines_xyz at an earlier snapshot or
                                                       upstream-filter variant; 7% point-count delta)
```

| Set | Files | Total points | Avg / track |
|---|---:|---:|---:|
| `ncei/tracklines_nc/` | 2,018 | 28.9M | ~14,319 |
| `ncei/tracklines_xyz/` | 5,382 | 123.4M | ~22,920 raw / ~14,000 after mb-strip |
| `singlebeam.xyz` | 1 (flat) | 114.5M | n/a |

The 4× point-count gap (114.5M vs 28.9M) rules out `tracklines_nc/`
as the merge source; the dump is the merged form of an earlier or
upstream-filter-variant snapshot of the `.xyz` family. The
**downstream decision** ("build the singlebeam pipeline from
`tracklines_nc/`, not from `singlebeam.xyz`") is unchanged, but the
**reason** sharpens: (a) per-track structure is preserved in `.nc`;
(b) `.nc` is mb-filtered upstream → cleaner input that doesn't depend
on the R2 classifier being perfect; (c) `.nc` carries standardized
MGD77+ columns (time, gobs, faa) that the bare `.xyz` lacks. See
PRD "Finding 2026-05-16" section and
`ncei/archive/sunmingzhi_singlebeam_xyz/SOURCE.md` for the full
relationship audit.

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

---

## Footer 2026-05-16: rename has now been executed (PR-A + PR-B)

The "Long-term: consider renaming the directory" item above was carried
out by task `05-11-singlebeam-integration` (PR-A for the multibeam side,
PR-B for the symmetric singlebeam-side rename). All path strings in
this document refer to the **pre-rename layout** and are preserved
verbatim as the historical record that motivated the refactor. Current
canonical paths are:

| Pre-rename (in this doc) | Post-rename (current) |
|---|---|
| `ship/NCEI_multibeam/` | `ship/jamstec/multibeam/` |
| `ship/JAMSTEC/bathymetry_data/` | `ship/jamstec/archive/bathymetry_data/` |
| `ship/JAMSTEC/archive/` | `ship/jamstec/archive/source_zips/` |
| `ship/JAMSTEC/gravity_data/` | `ship/jamstec/gravity_data/` |
| `ship/NCEI_singlebeam/` | `ship/ncei/` |

The string literal `source_dataset = "NCEI_multibeam"` is deliberately
kept inside `.py` source as a lineage label so Step 08 bit-identical
verification stays intact (Q5b locked decision).

The external zip filename `NCEI_singlebeam_tracks_raw_2018files.zip`
(at `/mnt/data2/00-Data/`) is unchanged — it is an upstream-archive
filename, not a path under our control, and is preserved verbatim
wherever referenced.

---

## Footer 2026-05-16 (transfer-chain finalization)

Three findings nailed down on 2026-05-16 that the prior footers left
fuzzy or only implicitly addressed. Pure metadata/provenance — none of
this changes active pipeline behavior.

### 1. 郭恒洋 transfer chain confirmed for `国外水深*.zip`

The two source zips at `jamstec/multibeam/archive/国外水深第{一,二}部分.zip`
(10.5 GB + 14.0 GB = 24.5 GB combined) arrived from
**郭恒洋 → user** in approximately **December 2024**. Evidence:
file mtimes Dec 16 / Dec 17 2024 (both physical files, not symlinks;
verified via `readlink -f`) + user recollection 2026-05-16.
**High-confidence inference, not externally verified.** Provenance is
not actively chased; recorded here as the durable attribution record.

### 2. `国外水深*.zip` ≡ `bathymetry.7z` packaging coincidence

Internal entry timestamps `2024-07-24` inside the `国外水深*.zip`
pair match the mtime `Jul 25 2024` of
`jamstec/archive/source_zips/bathymetry.7z`. → **Same packaging
event, two compression formats** of the same JAMSTEC cruise bundle.
This compounds the 2026-05-11 "JAMSTEC/bathymetry_data IS the source
archive of NCEI_multibeam" finding: the JAMSTEC bathymetry corpus
exists on this disk in **three independent packagings**
(`国外水深*.zip` 24.5 GB + `bathymetry.7z` 26 GB +
`bathymetry_data/*.zip` 25 GB = ~51 GB triplicate storage).

**Decision (locked, user 2026-05-16)**: keep all three; do not dedupe.
`multibeam/archive/国外水深*.zip` is the active pipeline anchor and
Step 08 bit-identical baseline; the other two are frozen archives
retained for reproducibility from alternate entry points. Full
mapping is recorded in `jamstec/SOURCE.md`.

### 3. `NCEI.zip` byte-identical duplicate in the gravity tree

A duplicate of the NCEI singlebeam-tracks archive lives at
`/mnt/data2/00-Data/gravity/NCEI/archive/NCEI.zip` (463 MB,
SHA256 `1a9b2c5b7e72f1ca1d17b0f1b7172186ebf56be1ebde67113ad8978a48514eed`
— byte-equal to
`ship/ncei/archive/source_zips/NCEI_singlebeam_tracks_raw_2018files.zip`).

This explains the long-standing dual-listing in the codex notes
(`~/.codex/ncei_singlebeam_README.md`) and the parallel `NCEI/` dir
under the `gravity/` sibling project: **the same source archive is
consumed by two sibling projects** — the bath pipeline (this `ship/`
tree) via the `depth` field; the gravity project
(`/mnt/data2/00-Data/gravity/`) via the `gobs` / `faa` fields.

**User decision 2026-05-16**: keep both copies, do not dedupe. Each
project owns its consumer-side copy where its pipelines expect it.
Two projects, one source.

### 4. Dual-content composition of the MGD77+ NetCDF tracklines

20-file random sample (seed=1) of `ncei/tracklines_nc/*.nc`,
433,127 total records:

| Field | Meaning | Non-null records | Non-null % | Files with any data |
|---|---|---:|---:|---:|
| `depth` | bathymetry | 278,726 | **64.4%** | 20/20 |
| `gobs` | gravity observation | 236,685 | **54.6%** | 12/20 |
| `faa` | free-air anomaly | 423,931 | **97.9%** | 20/20 |

The MGD77+ NetCDF format stores sensor measurements interleaved along
each cruise's time series; depth and gravity sensors may sample
different sub-intervals of the same trackline, so per-record non-null
counts vary by sensor. The corpus is **genuinely bath+gravity**, not
"bathymetry-only with some gravity columns ignored". This is the
empirical basis for the dual-consumption finding in §3.

### 5. Net effect on "Don't rename the directory" caveat

**No change** to the line-205-area caveat above. The caveat was about
active-pipeline path-dependence; the rename has already been
**executed** (PR-A on the multibeam side, PR-B on the singlebeam
side, both 2026-05-16) with the path-rewrite script plus Step 08
bit-identical verification (hash-only smoke check passed). This
2026-05-16 footer is purely metadata/provenance — no downstream
processing impact.

---

## Footer 2026-05-16 (李杨 finding chain)

Two fingerprint-driven findings landed on 2026-05-16 that finalize the
JAMSTEC-side transfer-chain unknowns from Footer §1–§3 above AND
sharpen the NCEI-side framing carried forward in Footers §3–§4. Both
are additive — the prior footers and the original historical narrative
above stand as-is.

### 1. 李杨 = JAMSTEC bath/gravity 7z transferer

User clue (2026-05-16): "李杨 sent JAMSTEC bath+gravity; bath includes
KR06-03, gravity includes KM17-02." Fingerprint-verified by direct
listing of the 7z internal contents:

- `KR06-03_bathymetry_dmo.zip` found inside
  `jamstec/archive/source_zips/bathymetry.7z` (internal mtime
  2024-04-11 09:30:52).
- `KM17-02_gravity.zip` found inside
  `jamstec/archive/source_zips/gravity.7z` (internal mtime 2024-04-10
  17:05:52).
- `jamstec/gravity_data/` (954 zips on disk) ≡ byte-identical unpack
  of `gravity.7z` (954 internal zips; per-file diff of
  `KM17-02_gravity.zip` empty).
- `jamstec/archive/bathymetry_data/` (776 zips on disk) ≡
  byte-identical unpack of `bathymetry.7z` (`KR06-03_bathymetry_dmo.zip`
  present in both locations).

→ All four previously-"unknown" JAMSTEC transfer chains
(`bathymetry.7z`, `gravity.7z`, `bathymetry_data/*.zip`,
`gravity_data/*.zip`) resolve to a single **李杨 → user** transfer of
two compressed packages (`bathymetry.7z` + `gravity.7z`), packaged
April 2024 internally. The on-disk per-cruise zip directories are
**byte-identical unpacks** of the 7z's, NOT separate transfer events.

`multibeam/archive/国外水深第{一,二}部分.zip` (24.5 GB) remains
**郭恒洋 → user** (Footer §1 above; Dec 2024 file mtimes, 2024-07-24
internal packaging — a different repackaging event from 李杨's
2024-04-11 packaging of the same JAMSTEC source corpus).

The earlier "Three packagings, one source" framing (Footer §2) is
therefore superseded: ~51 GB redundancy is now traceable to **two
independent transferers** working from the same JAMSTEC source corpus
at different times with different packaging conventions, not three
coincidental packagings. Locked decision #2 still holds: keep all
copies; active anchor is `multibeam/archive/`. Full details in
`jamstec/SOURCE.md`.

### 2. 李杨 = ncei `.nc` archive content converter

5/5 spot-checked `.nc` files in `ncei/tracklines_nc/` carry identical
NetCDF global-attribute structure:

```
Author: liyang
title: Cruise XXXX (NGDC ID XXXX)
history: Wed Jul 31 [HH:MM:SS] 2024  [liyang] Conversion from MGD77 ASCII to MGD77+ netCDF format
```

→ The entire 2,018-file archive at `ncei/tracklines_nc/` is **李杨's
local NetCDF conversion** of NCEI MGD77 ASCII source data, performed
2024-07-31. The package `NCEI_singlebeam_tracks_raw_2018files.zip`
(at `ncei/archive/source_zips/`) and its byte-identical duplicate
`/mnt/data2/00-Data/gravity/NCEI/archive/NCEI.zip` both carry 李杨's
conversion product. The earlier codex-notes finding (that the bytes
"matched against the NCEI singlebeam track archive") was about
**content-value matching against NCEI MGD77 source data** — that
conclusion stands — but the file format is 李杨's conversion artifact,
not NCEI's official NetCDF distribution.

**Transfer chain (user confirmed 2026-05-16)**:
**李杨 (2024-07-31 conversion) → 孙明智 (forwarding, late 2024) → user**.
The earlier 2026-05-11 "Singlebeam reuse note" (which implicitly
framed the .nc archive as canonical NCEI distribution) is
**superseded** by this finding — the archive is 李杨's local
conversion product, content-equivalent to NCEI MGD77 source but
format-wise an artifact.

### Implication: 孙明智's role narrows

- 孙明智 (a) **forwarded** 李杨's NetCDF-conversion `.nc` archive to
  user in late 2024 (file mtime Dec 18 2024).
- 孙明智 (b) **provided / own-worked** `singlebeam.xyz` (Jan 18 2025
  file mtime), the 114.5M-row flat-merge dump now at
  `ncei/archive/sunmingzhi_singlebeam_xyz/`. The flatten/merge origin
  is undocumented — possibly 孙明智's own work, possibly an upstream
  snapshot he obtained pre-merged. **Not 李杨's product** in either
  case.

The dirname `sunmingzhi_singlebeam_xyz` refers only to (b) — the flat
merge — kept as frozen legacy artifact.

### Downstream-impact audit

**No algorithmic change**. The .nc archive being 李杨's conversion
does not change parser / QC / aggregation behavior — MGD77+ NetCDF is
a standard format and `netCDF4.Dataset` reads it identically
regardless of who performed the conversion. PR-D through PR-G of task
`05-11-singlebeam-integration` are unaffected. This footer is purely
provenance refinement.

### Where this finding is recorded

- This footer (canonical narrative).
- `jamstec/SOURCE.md` — rewritten transfer-chain section (李杨 + 郭恒洋
  with fingerprint evidence).
- `ncei/SOURCE.md` — new top-level summary (李杨 conversion +
  孙明智 dual role).
- `ncei/tracklines_nc/SOURCE.md` — rewritten Provenance section.
- `ncei/archive/sunmingzhi_singlebeam_xyz/SOURCE.md` — sharpened
  Transfer-chain-scope bullet (forwarder vs. own-work split).
- `ncei/archive/source_zips/SOURCE.md` — updated transfer-chain table
  row for the .nc zip.
- PRD: `.trellis/tasks/05-11-singlebeam-integration/prd.md` —
  "Finding 2026-05-16 (李杨 finding chain)" section.
