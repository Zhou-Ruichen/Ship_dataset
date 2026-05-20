# Step 04 — 1-arcmin Aggregation Design Audit

- **Generated**: 2026-05-20
- **Audit script**: `.trellis/tasks/05-11-singlebeam-integration/research/_audit_task2.py`
  + ad-hoc streaming passes (logged inline in §2 below)
- **Cwd**: `/mnt/data2/00-Data/ship` (run from repo root per
  `pipeline-design-decisions.md` §11)
- **Scope**: read-only audit of Step 03A + Step 03B outputs; no Step 04A/B
  code authored, no `file_cells` parquets written, no pipeline scripts
  touched. Pre-decision-gate for Step 04A.
- **Inputs read**:
  - `ncei/manifests/bathymetry_entry_manifest.parquet` (Step 03A, 7,403 rows, 20-col)
  - `ncei/manifests/bathymetry_entry_manifest_supplementary.parquet` (Step 03B, 7,403 rows, 26-col)
  - `ncei/manifests/intersect_divergence_audit.parquet` (Step 03B, 1,850 rows, 19-col)
  - `ncei/derived/singlebeam/points_checked/*.parquet` (5,365 files; 400 sampled for percentile stats, all 5,365 streamed for cell counts)
  - `ncei/derived/multibeam/points_checked/*.parquet` (17 files; all processed)
  - `ncei/derived/regional_mrar/points_checked/bathymetry_points.parquet` (1 file, 113.36M rows, 3 quadrants by `track_id`; all streamed for cell counts, 4% sampled for per-cell percentiles)
  - `ncei/archive/zhoushuai_processed_M/bathymetry_points.parquet` (PR-F output; same row count as Step 03A regional_mrar copy)
- **Audit constants used**:
  - cell size `1.0/60.0°` (1 arc-minute); global indexing
    `lon_bin = floor((lon+180)*60)`, `lat_bin = floor((lat+90)*60)`.
  - triple key for `n_unique_triples`: `(round(lon,4), round(lat,4), round(depth_m_positive_down,1))` — finer than 1-arcmin (~11 m at the equator for lon/lat, 0.1 m depth), coarser than full float for robustness against float noise. **Step 03B's `n_unique_triples`** is exact float-equality over the whole track (verified by reading the supplementary checker output — `n_unique_triples` summed across the corpus = 233.99M of 240.15M reads → 6.16M duplicate points, matching report §B). **Difference for Step 04A's purpose is negligible**: at sub-arcsecond resolution, snapping to 4 decimals collapses ~ε-different floats from the same sensor read, which is exactly the semantic we want for per-cell effective-count weighting.
- **Cumulative wall time across all dry-run passes**: ~3.5 min on `/mnt/data2`.

---

## Headline numbers (full-corpus)

| Branch | Tracks | Points pass | Unique 1-arcmin cells | Track-cell pairs | Overall dup_ratio |
|---|---:|---:|---:|---:|---:|
| **singlebeam** (nc + xyz-sb) | 5,365 | 77,445,882 | **14,611,054** | 17,294,849 | 0.0507 |
| **multibeam_ncei** (xyz-mb) | 17 | 37,799,943 | **5,960** | 6,329 | **0.6947** |
| **regional_mrar** (M.rar 3 quadrants) | 3 quadrants | 113,356,269 | **9,019,383** | 9,023,641 | 0.0002 |
| union (3 branches) | 5,385 entries | 228,602,094 | 21,743,065 | — | — |

Cross-branch cell overlaps (informational; not used for any Step 04A/B merge):

- SB ∩ M.rar = 1,888,543 cells (~12.9% of SB cells, ~20.9% of M.rar cells).
- MB ∩ M.rar = 4,015 cells (~67% of MB cells).
- MB ∩ SB = 4,127 cells (~69% of MB cells).
- M.rar inter-quadrant overlap = 129 cells out of 9,019,383 (boundary effect; effectively a partition).

The **multibeam overall_dup_ratio = 0.69** is the smoking gun: of every 100 MB rows, ~69 are exact lon/lat/depth duplicates within their track. This is precisely the AUV-Sentry behavior Step 03B Finding 1 warned about. Any Step 04A weighting that uses `n_points_pass` directly will let 11 AUV tracks dominate every shared cell.

---

## §1 Confirm primary input selection rules (Task 1)

### 1.1 Manifest schema already encodes every routing decision

The Step 03A manifest carries five columns that make the input-selection
rules **declarative and auditable** rather than something Step 04A needs to
re-derive from filename conventions:

| Column | Role |
|---|---|
| `source_priority` | `primary` / `supplementary` / `regional` / `skip` |
| `source_completeness` | `nc_only` / `nc_xyz_intersect` / `xyz_only` / `mrar_regional` |
| `bathymetry_eligible` | bool — false for `skip` rows |
| `use_for_primary_bathymetry` | bool — true for primary + regional |
| `use_for_supplementary_bathymetry` | bool — true for supplementary |
| `output_path` | path to `points_checked/*.parquet`; **null for supplementary and skip rows** |
| `instrument_class_pred` | `singlebeam` / `multibeam` — drives sb/mb dir routing for primary |

Cross-tab from the manifest (verified):

```
source_priority  source_type     source_completeness   count
primary          ncei_nc         nc_xyz_intersect      1,850
primary          ncei_xyz        xyz_only              3,532
regional         mrar_zhoushuai  mrar_regional             3
skip             ncei_nc         nc_only                 168
supplementary    ncei_xyz        nc_xyz_intersect      1,850
```

Of the 3,532 primary `xyz_only` entries, the R2 classifier (PR-D)
labels 3,515 as `singlebeam` (→ `singlebeam/points_checked/`) and
17 as `multibeam` (→ `multibeam/points_checked/`).

### 1.2 Verification against task premises

| Premise | Verdict | Evidence |
|---|---|---|
| `nc_xyz_intersect` → use `__nc` parquet only (drop `__xyz` for those 1,850 ids) | ✅ Already enforced by Step 03A. The 1,850 `__xyz` parquets for intersect tracks were **never written to disk** at all: their manifest rows have `source_priority="supplementary"`, `output_path=NULL`. There are 0 `points_checked` files for intersect-track xyz in any directory. | `ncei/derived/singlebeam/points_checked/` contains 1,850 `__nc.parquet` + 3,515 `__xyz.parquet` = 5,365 files. 5,365 + 17 (multibeam) = 5,382 = exactly the primary-entry count. No `__xyz.parquet` files exist on disk for any of the 1,850 intersect track_ids. |
| `xyz_only` → use `__xyz` parquet | ✅ Trivially true; the 3,532 primary xyz parquets are exactly the 3,515 singlebeam + 17 multibeam routed outputs. | as above |
| `nc_only` with no usable depth (168 tracks) → already absent from `points_checked/` | ✅ confirmed. Manifest rows have `output_path=NULL`, `skip_reason='no_usable_depth'`, `bathymetry_eligible=False`. | manifest filter `source_priority=='skip'` → 168 rows, all `output_path` is null |
| `regional_mrar` → use bathymetry_points.parquet only (multibeam branch) | ⚠️ **Premise framing wrong in PRD task description**: M.rar is **NOT in the multibeam branch**. It lives in `ncei/derived/regional_mrar/points_checked/bathymetry_points.parquet` as its own source-priority bucket (`regional`). The bathymetry-grade input is correct, but the dir is `regional_mrar`, not `multibeam`. | `output_path` for M.rar rows points to `regional_mrar/`, `instrument_class_pred` not used (regional bucket). |
| `f-10-89-cp` → exclude OR sensitivity-only | See §1.4 below | track-level analysis |

### 1.3 Double-counting risks for naive `glob points_checked/*.parquet`

**Three concrete pitfalls** if Step 04A iterates the filesystem rather than
the manifest:

1. **Multibeam tracks would be missed by a glob that only walks
   `singlebeam/`**. The 17 confirmed mb tracks (Sentry + Atlantis + 5
   borderline) live exclusively in `multibeam/points_checked/`. Any sb-only
   glob silently drops 37.8M valid points (16.5% of the global primary
   total). **Mitigation**: always include both `singlebeam/` and
   `multibeam/` under `derived/` when defining the source branch list.

2. **M.rar 3-row manifest entries share input/output paths** — they
   distinguish quadrants via the per-row `track_id` column inside the
   parquet, NOT via filenames. A loop like
   `for row in manifest.itertuples(): df = pd.read_parquet(row.output_path)`
   would read the 113.36M-row file **three times** = 340M-row over-read
   (and triple-count in any per-row sum). **Mitigation A**: read
   `regional_mrar/points_checked/bathymetry_points.parquet` exactly once
   and partition by `track_id` in-memory. **Mitigation B**: when
   iterating the manifest, deduplicate by `output_path` first, OR loop
   over `manifest.groupby('output_path')` and use the group key as the
   read target. The manifest's three rows are **input metadata**
   (quadrant statistics), not three files.

3. **Intersect-track `__xyz.parquet` files do not exist on disk** —
   safe today, but if a future Step 03 rerun materializes them (for
   sensitivity-analysis purposes) they could leak into a naïve sb glob
   and re-create the intersect double-count that PRD Finding 19c warned
   about. **Mitigation**: drive Step 04A from the manifest's
   `use_for_primary_bathymetry==True` filter on `output_path`, never
   from `os.listdir()` / `glob`.

**Recommendation**: Step 04A's iteration discipline must be
"`manifest[use_for_primary_bathymetry].dropna(subset=['output_path'])
 .drop_duplicates('output_path')` → per-file processing, partition by
`track_id` column for M.rar". Do not glob.

### 1.4 `f-10-89-cp` — detailed handling recommendation

f-10-89-cp is the worst-quality track in the primary corpus. Combined
signal (Step 03A §4 + Step 03B §A2/B2/C1 + D divergence audit + this
audit's per-cell pass):

| Signal | Value | Source |
|---|---:|---|
| Source | `ncei_nc`, primary (xyz-side is supplementary copy) | manifest |
| Raw points | 53,637 | Step 03A |
| Pass-basic points | 1,413 (**2.6% pass rate** — among the worst 20 primary tracks) | Step 03A §4 |
| `n_depth_eq_zero` | 27,467 (51.2%) | Step 03B §A2, ranked #4 worst |
| `n_invalid_depth_pos` | 52,224 | Step 03A |
| `n_depth_jump_candidates` | 1,852 (3.5% of valid points have |Δdepth|>1000 m between consecutive readings) | Step 03B §C1 |
| Duplicate triples in 1,413 valid set | only 47 (`n_unique_triples=53,590` out of 53,637 raw, so dup_ratio of valid is tiny — same physical point shows up at most once after pass-basic filter) | Step 03B §B |
| Intersect divergence | `bbox_overlap_jaccard=0.000228` (D1 row #2) — nc bathymetry is in 160–161°E / 9–11°N but raw bbox spans the globe (lon_min=-180 to lon_max=180, lat 6.3–21.3) → strong evidence of bad/duplicate/sentinel coordinates in the nc-raw stream | Step 03B §D1 |
| Spatial spread in pass-basic | 495 occupied 1-arcmin cells, mean 2.85 pts/cell, p50 1 pt, max 55 pts | this audit (`f10_89_cp_cells.tsv`) |
| Cell-internal depth_iqr | mean 35 m (modest), max 701 m (suspicious — likely jump-flag cells) | this audit |
| Median cell depth range | 1,250 m – 4,968 m (real bathymetry depth distribution; not a sentinel signature) | this audit |

**Reading**: f-10-89-cp's *valid* 1,413 points look like real bathymetry
(reasonable depths, ~500 occupied cells in the expected lat/lon box).
But the same track also carries 27k zero-depth sentinels, ~50k
NaN-depth rows, and 1,852 verified-bad-jump cells. The Step 03A
point-check has already removed all of this from `points_checked/`,
leaving only the 1,413 good rows; what remains is no worse than the
average primary track on a per-cell basis.

**Recommendation**: **keep f-10-89-cp in primary aggregation, mark
with a `manual_review_flag` column** (see §3.3 and §4 below for where
to surface it). Justification:

1. The 1,413 pass-basic points have **already** survived Step 03A's
   gates (`valid_lon & valid_lat & valid_depth_pos & valid_depth_max &
   valid_core_fields`). The remaining noise is bounded by the cells
   they fall into — and Step 04B's file-balanced median is robust to
   noise within a cell (per design decision #3).
2. The "high `n_depth_jump_candidates`" flag is per-track, not
   per-point. Step 03B §C explicitly emits jumps as a per-track audit
   signal, not a per-point drop. The current 1,413 valid-set
   per-cell IQR distribution (mean 35 m, max 701 m) is within normal
   primary-corpus range (singlebeam corpus p99 depth_iqr = 167 m,
   max 9,147 m). f-10-89-cp is not an outlier on a per-cell basis.
3. The intersect divergence is a **bbox-shape artifact** (Step 03B
   §D3 — the nc bbox includes globe-spanning gravity-only rows that
   are dropped by the point-check). The `depth_med_nc` and
   `depth_med_xyz` agree exactly (`1958.300` m both sides). No
   actual bathymetry disagreement.
4. Excluding the track entirely would discard 495 1-arcmin cells of
   real coverage in the central Pacific (160–161°E, 9–11°N). Adding a
   review flag preserves the audit trail while letting downstream
   quality tiering decide whether to demote f-10-89-cp's cells.

**Alternative** (more conservative): move f-10-89-cp to a
`primary_with_review` sub-bucket (i.e. still contributes to per-cell
medians, but Step 06b file-flag default is `review` instead of `keep`).
This is the cleaner long-term framing — but it touches Step 06b's
file-flag logic and the file-flag pipeline isn't built yet for the NCEI
branch. Recommendation deferred to whoever implements Step 06b for
singlebeam.

`f10_89_cp_summary.tsv` and `f10_89_cp_cells.tsv` capture the per-cell
distribution for future calibration.

---

## §2 Dry-run 1-arcmin distribution stats (Task 2)

All numbers below come from `_audit_task2.py` (SB sample + MB full + MRAR 4%
sample) cross-checked with two additional full-streaming passes (logged
inline in this session) for the unique-cell counts.

Saved TSVs:
- `ncei/derived/aggregation_design_audit/branch_summary.tsv`
- `ncei/derived/aggregation_design_audit/cell_distribution_percentiles.tsv`
- `ncei/derived/aggregation_design_audit/f10_89_cp_summary.tsv`
- `ncei/derived/aggregation_design_audit/f10_89_cp_cells.tsv`

### 2.1 Branch-level totals

| Branch | (a) Candidate tracks after primary selection | (b) Valid points (`point_check_pass_basic`) | (c) Unique 1-arcmin cells |
|---|---:|---:|---:|
| singlebeam | 5,365 (1,850 nc + 3,515 xyz-sb) | 77,445,882 | 14,611,054 |
| multibeam_ncei | 17 (all xyz, all R2-classified mb) | 37,799,943 | 5,960 |
| regional_mrar | 3 quadrants in 1 parquet | 113,356,269 | 9,019,383 |

(c) was computed by full-corpus streaming (`pyarrow iter_batches`, batch 500k–1M rows,
filter on `point_check_pass_basic`, drop coord NaNs, hash 1-arcmin bins
into a Python set). SB pass: 47.7 s. MB pass: 11.6 s. MRAR pass: 19.1 s.

**Sampling caveat**: The percentile and `n_unique_triples` numbers below
come from samples (SB 400/5365 = 7.5%, MRAR 4%); the per-branch totals
(a)–(c) and `overall_dup_ratio` come from full-corpus streaming.

### 2.2 Per-(track, cell) percentiles

(from `cell_distribution_percentiles.tsv`)

#### Singlebeam (sample: 400 tracks, 1,219,103 (track,cell) rows, 1,197,110 unique cells)

| Metric | p10 | p25 | p50 | p75 | p90 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| `n_points_pass` | 1 | 1 | 1 | 4 | 7 | 35 | 8,762 |
| `n_unique_triples` | 1 | 1 | 1 | 4 | 7 | 34 | 1,711 |
| `dup_ratio` | 0 | 0 | 0 | 0 | 0 | 0.040 | 0.941 |
| `depth_iqr` (m) | 0 | 0 | 0 | 7.7 | 34.0 | 167.5 | 9,146.9 |

Reading: 75% of singlebeam (track,cell) pairs carry ≤4 points. 98.2% of
cells visited by any sampled track are unique to that track (only ~22k
(track,cell) rows of 1,219k sample share a cell with another sampled
track). **`dup_ratio` ≈ 0 for the vast majority** — clean singlebeam
sounding, one sensor reading per location. The p99 max of 8,762 in
`n_points_pass` is `index13` (an nc file from the calibration scatter
that sits near the 1M-point cutoff) — see §3.3 for sensitivity-track
treatment.

#### Multibeam (full corpus: 17 tracks, 6,329 (track,cell) rows, 5,960 unique cells)

| Metric | p10 | p25 | p50 | p75 | p90 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| `n_points_pass` | 44 | 129 | 990 | 2,253 | 4,681 | 63,240 | **1,224,832** |
| `n_unique_triples` | 43 | 124 | 825 | 2,024 | 2,980 | 15,619 | 78,387 |
| `dup_ratio` | 0 | 0 | 0.002 | 0.007 | 0.161 | **0.923** | 0.997 |
| `depth_iqr` (m) | 1.4 | 4.2 | 12.0 | 34.3 | 80.5 | 223.9 | 871.4 |

Reading: MB cells **average 6,000 points/cell** (i.e. ~1,000× more than
SB). The single worst (track, cell) cell has **1.22M points of which
only 78k are unique triples** (dup_ratio 0.94). This is the Sentry
duplicate signature — each ping echo is recorded with a slightly
shifted timestamp but identical lon/lat/depth. **If Step 04A uses
`n_points_pass` as the weighting field, this single cell from one AUV
dive contributes 1.22M votes** against ~14k votes from a thousand
singlebeam cells combined. `n_unique_triples` cuts that to 78k (16×
smaller but still dominant). The p99 dup_ratio of 0.92 confirms the
pattern is systematic across MB cells, not a single outlier.

Per-cell depth_iqr is **modest (p99=224 m, p90=80 m)** — MB swaths
remain locally coherent in depth even when point counts explode. This
is a good signal for the file-balanced median (per design decision #3):
the median is well-defined even in highly-duplicated cells.

#### Regional M.rar (sample: 4% of 113.36M rows = 4.5M sampled rows; 3,368,241 sampled (track,cell) rows, 3,368,236 unique cells in the sample)

| Metric | p10 | p25 | p50 | p75 | p90 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| `n_points_pass` (sampled) | 1 | 1 | 1 | 2 | 2 | 3 | 8 |
| `n_unique_triples` (sampled) | 1 | 1 | 1 | 2 | 2 | 3 | 8 |
| `dup_ratio` (sampled) | 0 | 0 | 0 | 0 | 0 | 0 | 0.5 |
| `depth_iqr` (m, sampled) | 0 | 0 | 0 | 1 | 18 | 119 | 5,353 |

**Sampling caveat**: At 4% sample, expected points/cell scales as
`pts/cell_real / 25`. The real (full-corpus) M.rar **mean** points/cell is
**12.57** (113.36M / 9.02M cells, computed from the full streaming pass).
The full-corpus `n_points_pass` percentile distribution per cell could not
be computed under the audit time budget (would need a streaming
group-by hash table); the 4% sample gives the right **shape** but should
be read as **lower bounds** for absolute values. Effective scaling
factor: multiply sampled `n_points_pass` percentiles by ~25 for a
back-of-envelope full-corpus estimate.

Reading even with the sample caveat: M.rar's per-cell `dup_ratio ≈ 0`
(99.99% no within-track duplicates) confirms the PR-F cleaning result —
the post-cleaning bathymetry parquet is essentially a regular gridded
product, **not** raw soundings. The `depth_iqr` distribution likewise
shows a regular surface: p50=0 (single depth value per cell), p99=119 m
(the deeper-shelf cells with real terrain variability). The 5,353 m
max IQR is a quadrant-boundary or interpolation-edge artifact in a
small number of cells.

### 2.3 Recommended triple definition (Task 2e)

**Proposal**: use the same `n_unique_triples` semantics Step 03B used —
exact float equality on `(lon, lat, depth_m_positive_down)` per track.
This is the field already present on every supplementary-manifest row
and is what aggregates already-computed.

For Step 04A's per-(track, cell) `n_unique_triples_in_cell`, derive
a fresh per-cell-restricted count via groupby. The arithmetic identity
`Σ_cells n_unique_triples_in_cell ≤ n_unique_triples_track` holds
(equality unless a triple appears in multiple cells, which is impossible
when lon/lat are rounded consistently with the bin assignment).

In this audit I used `(round(lon,4), round(lat,4), round(depth,1))`
to keep the dedup robust to ε-floats from cell-edge points. The
audit-vs-Step-03B numbers cross-check: SB total points 77.45M / unique
triples 4.76M (from sampled cells aggregated) ≈ 7% dup rate at sample
level; full-corpus Step 03B reports 85.95M / 4.997M for xyz alone, so
the sample is representative.

### 2.4 Runtime

- Task 2 main script (SB sample + MB full + MRAR 4% sample): 84.6 s.
- Targeted f-10-89-cp pass: <1 s.
- Full M.rar cell-count streaming: 19.1 s.
- Full SB+MB cell-count streaming: 59.3 s (47.7+11.6).
- Cross-branch overlap streaming: 89.0 s.

All under the 10-min budget. No task required more aggressive subsampling.

---

## §3 Field recommendation for Step 04A (Task 3)

### 3.1 Per-cell median depth

**Recommendation**: `cell_depth_median = median(depth_m_positive_down)
over rows with point_check_pass_basic=True`. **Do not pre-deduplicate
to unique triples for the median itself.**

Why: Duplicate triples within a track contribute the same value
(by construction); they do not bias the median; they do not require
deduplication for the median to be correct. Removing duplicates first
would only matter if we were taking a mean, where weights matter.
File-balanced median (design decision #3) is the cross-track aggregation
rule (Step 04B), not the within-cell rule. Within a cell of one track,
`median(values_with_dups) == median(unique_values)` whenever each unique
value appears the same number of times (true for the Sentry pattern: every
duplicate is exact). The only failure mode is asymmetric duplication
inside one cell — none observed in the sample.

Source-branch nuances:
- **singlebeam**: median over 1–7 points/cell (p10–p90). Robust.
- **multibeam_ncei**: median over 100s–1000s of points/cell. Massively
  robust, but consider also emitting `depth_q25` and `depth_q75` per
  cell so Step 04B / Step 06 / Step 07 can see the cell-internal
  dispersion without re-reading the points parquet.
- **regional_mrar**: 1–2 points/cell mean (post-PR-F gridded). Median ≡
  the value itself in most cells. Cheap.

### 3.2 Effective observation count

**Recommendation** — emit **both** `n_points_pass` and `n_unique_triples`
per (track, cell). For quality weighting Step 06b/07 should use
`n_unique_triples` for MB cells and `n_points_pass` for SB/MRAR cells
(documented in §3.3 below); Step 04A itself emits both and lets
downstream choose.

Rationale per branch:

- **singlebeam**: `n_points_pass ≈ n_unique_triples` (overall_dup_ratio
  = 0.05; per-cell p99 dup_ratio = 0.04). Either column suffices for
  weighting. Recommend `n_points_pass` since it's cheaper to compute (no
  groupby-dedup needed) and the semantic difference is negligible.

- **multibeam_ncei**: `n_points_pass` and `n_unique_triples` diverge
  drastically (overall_dup_ratio = **0.69**; p99 per-cell dup_ratio =
  0.92). **Must** use `n_unique_triples` for any weighting that compares
  MB cells to SB cells, otherwise 1 AUV cell carries the weight of
  1,000 SB cells. (For absolute weighting within MB-only cells the
  choice matters less — they're all heavily duplicated — but the moment
  MB cells are pooled with SB cells in a quality-tier calculation, the
  difference is material.)

- **regional_mrar**: `n_points_pass ≈ n_unique_triples`. Use
  `n_points_pass`. Note: with mean 12.57 pts/cell and dup_ratio ≈ 0,
  M.rar cells are not "more sampled" than they appear — the gridded
  product is what it is.

### 3.3 Quality weighting tradeoffs

The multibeam dup_ratio finding (§2.2 + Step 03B Finding 1) makes
this concrete. Three weighting options across the cross-branch combine
(combined-product layer is out of Step 04A/B scope, but Step 04A's
emitted columns determine what later stages can do):

| Weight | Behavior | Recommendation |
|---|---|---|
| `n_points_pass` | AUV Sentry cells get ~1.22M votes each; 11 Sentry tracks dominate every shared cell. SB cells (median 1 pt) become noise floor. | ❌ do not use cross-branch |
| `n_unique_triples` | Sentry top cell falls to 78k votes (16× cut). Still dominant vs SB but no longer overwhelming. | ✅ for cross-branch weighting |
| `log(n_unique_triples + 1)` (or sqrt) | Compress dynamic range further; SB and MB cells become comparable on a per-source basis. | Discuss in Step 04B / Step 06–07 design (out of scope here) |

**Auv-dominance test case** (concrete): the worst cell in `sentry421`
has 1,224,832 raw / 78,387 unique triples / depth_iqr 12 m. A
neighbouring SB cell from `lprs05rr` has, say, 5 raw / 5 unique / depth
range 10 m. Under `n_points_pass`-weighted aggregation in a combined
product, Sentry weights 245,000× the SB cell. Under
`n_unique_triples`, 16,000×. Under `log(n+1)`, ~6×. Step 04A doesn't
need to make this call, but the emitted columns must support all three.

**Concrete Step 04A recommendation**: emit
`n_points_pass`, `n_unique_triples`, `depth_median`, `depth_q25`,
`depth_q75`, `depth_min`, `depth_max` per (file, cell). Calibration of
the actual weighting happens in Step 06b/07, where the singlebeam tier
thresholds will be re-calibrated (per PRD "Post-PR-E aggregation
guidance"). Do **not** bake a chosen weighting into Step 04A's outputs
themselves.

---

## §4 Recommended Step 04A / 04B output schemas (Task 4)

### 4.1 Step 04A — per-file (or per-track-quadrant) cells

`ncei/derived/{singlebeam,multibeam,regional_mrar}/file_cells_1min/<file_id>.parquet`

| Column | Type | Notes |
|---|---|---|
| `source_branch` | string | `singlebeam` / `multibeam_ncei` / `regional_mrar` |
| `source_type` | string | passthrough from manifest: `ncei_nc` / `ncei_xyz` / `mrar_zhoushuai` |
| `track_id` | string | one row per (track_id, cell). For M.rar the track_id is the quadrant filename (`mrar_0-180E-0-85N.txt` etc.) — see §1.3 pitfall #2 |
| `lon_bin` | int32 | `floor((lon+180)*60)`, range 0..21599 |
| `lat_bin` | int32 | `floor((lat+90)*60)`, range 0..10799 |
| `cell_id` | string | `f"1min_{lat_bin}_{lon_bin}"` per design decision #4 |
| `n_points_pass` | int32 | rows with `point_check_pass_basic=True` in this (track, cell) |
| `n_unique_triples` | int32 | distinct (lon_r4, lat_r4, depth_r1) triples within the cell. Equal to `n_points_pass` for SB/MRAR; can be much smaller for MB |
| `depth_median_m` | float32 | `median(depth_m_positive_down)` over pass-basic rows |
| `depth_q25_m` | float32 | p25 over pass-basic rows |
| `depth_q75_m` | float32 | p75 over pass-basic rows |
| `depth_min_m` | float32 | min |
| `depth_max_m` | float32 | max |
| `instrument_class_pred` | string | passthrough from manifest (sb / mb) |
| `source_completeness` | string | passthrough from manifest (nc_only / nc_xyz_intersect / xyz_only / mrar_regional) |
| `manual_review_flag` | bool | true if Step 03B Check C jump-density is high (`n_depth_jump_candidates / n_unique_triples > T`) or if depth_anomaly_flag — initially set on f-10-89-cp, the 16 depth_anomaly tracks, and the bbox-only divergent 96 tracks (informational; not a drop filter) |
| `aggregation_version` | string | `step04a_v0.1.0` |

Notes:
- One parquet file per Step 03A `output_path` (5,365 + 17 + 1 = 5,383
  files). The single `regional_mrar/.../bathymetry_points.parquet` Step
  04A output contains all 3 quadrants distinguished by `track_id`
  column (mirrors the input structure; no quadrant-split files).
- `depth_iqr_m` could be added but is trivially computable from
  `depth_q75 - depth_q25` — omit unless a downstream consumer asks for it.
- The `cell_id` column is denormalized from `lon_bin`+`lat_bin` for
  joinability with the existing `primary_ship_validation_cells_1min`
  parquet (which uses the same string format per design decision #4).

Source-branch-specific notes:
- For `singlebeam` and `multibeam_ncei`, file = track. One row per
  (track, cell). 17.3M (SB) + 6.3k (MB) total rows.
- For `regional_mrar`, file = single 113M-row parquet split logically
  by `track_id`. One row per (quadrant, cell). ~9.02M total rows.

### 4.2 Step 04B — per-source-branch merged cells

`ncei/derived/{singlebeam,multibeam,regional_mrar}/cells_1min.parquet`

Within a source branch, multiple tracks can contribute to one cell.
Per design decision #3 (file-balanced median), the merge rule is:

> `cell_depth = median over tracks of (track's median depth in cell)`

Schema (proposed):

| Column | Type | Notes |
|---|---|---|
| `source_branch` | string | one of the three branches |
| `lon_bin` | int32 | |
| `lat_bin` | int32 | |
| `cell_id` | string | |
| `n_tracks_in_cell` | int16 | distinct `track_id` values contributing |
| `total_n_points_pass` | int64 | sum across contributing tracks |
| `total_n_unique_triples` | int64 | sum across contributing tracks |
| `cell_depth_median_m` | float32 | median of per-track per-cell medians |
| `cell_depth_min_per_track_median_m` | float32 | min of contributing track medians (cross-track spread proxy) |
| `cell_depth_max_per_track_median_m` | float32 | max of contributing track medians |
| `cell_depth_iqr_per_track_median_m` | float32 | IQR of contributing track medians |
| `contributing_track_ids` | list<string> | for audit; can be dropped if cardinality is concerning |
| `any_manual_review_flag` | bool | true if any contributing track had `manual_review_flag=true` |
| `aggregation_version` | string | `step04b_v0.1.0` |

Per-branch row counts (predicted from §2 cell counts):
- `singlebeam/cells_1min.parquet`: 14,611,054 rows.
- `multibeam_ncei/cells_1min.parquet`: 5,960 rows.
- `regional_mrar/cells_1min.parquet`: 9,019,383 rows (mostly 1 track per cell — only 129 cells overlap between quadrants).

**Cross-branch merging is explicitly OUT OF SCOPE** for Step 04B per
the PRD "Post-PR-E aggregation guidance":

```
derived/validation/{primary_multibeam_cells_1min,
                    supplementary_singlebeam_cells_1min,
                    combined_ship_cells_1min}
```

is the *future* layer that will pool branches. Step 04A/04B as designed
here populates the three source-branch parquets; the validation-cells
parquet is a Step 05+ concern.

### 4.3 Within-branch merge rules (Task 4 detail)

For each source branch the inter-track merge rule:

- **singlebeam**: file-balanced median per design decision #3, exactly
  as multibeam does it for JAMSTEC. **However**: PRD warns that
  multibeam tier thresholds (`n_points ≥ 100`, `n_file_cells ≥ 2`,
  `n_cruises ≥ 2`, `iqr_depth ≤ 50m`) **must not be blindly copied**
  for singlebeam. Confirmed by §2.2 stats: SB p50 per-cell `n_points_pass=1`
  and p90=7, so a `n_points ≥ 100` threshold would drop ~99% of SB cells.
  Recommend: Step 04B emits the columns; Step 07 tier calibration is
  the right place to set per-branch thresholds. **Not a Step 04A/B
  decision.**

- **multibeam_ncei**: file-balanced median works as-is. Predicted overlap
  is minimal (most MB cells contributed by 1 track; cross-track overlap
  rare because the 17 tracks are spatially disjoint AUV dives or
  R/V Atlantis ra-series transits — only 6,329 (track,cell) pairs from
  5,960 cells). The "1 vote per track" rule reduces to "the track's
  median" in nearly every cell.

- **regional_mrar**: file-balanced median over quadrants. With only 129
  inter-quadrant overlap cells out of 9.02M, this is essentially a
  no-op merge. The 129 overlap cells will get 2 votes (rare); all
  others get 1.

**Do not** merge cells across the three branches at Step 04B. The
cross-branch combine has fundamentally different weighting tradeoffs
(see §3.3, AUV-dominance) and design decisions that the PRD reserves
for "validation design is explicit" — i.e., a future Step 05+ task.

---

## §5 Explicit non-goals (Task 5)

This audit confirms the following items are **out of scope** for Step 04A
+ Step 04B as designed here:

- ❌ **Define A/B/C quality tiers**: Step 07 territory. Singlebeam tier
  thresholds will be recalibrated against the sparse per-cell stats
  shown in §2.2 (median 1 pt/cell), not copied from multibeam.

- ❌ **Merge singlebeam + multibeam + JAMSTEC + M.rar into a combined
  table**: explicit PRD non-goal. Cross-branch weighting (§3.3) is
  unresolved and needs a separate design pass.

- ❌ **Run full global validation (Step 08)**: deferred to PR-G per PRD.
  Pre-PR-E gate 2 already specified a T1-footprint smoke check for the
  multibeam rename — that gate stands.

- ❌ **Add gravity (gobs/faa) columns to file_cells**: orthogonal to the
  bathymetry pipeline (per Locked decision #10 dual-consumption note —
  gravity is a parallel project consumer).

- ❌ **Re-classify the borderline R2 cases** (e.g., `sermilik.xyz` flagged
  in PR-D notes): a Step 04A audit can surface where borderline-sb
  files produce mb-density cells, but the R2 thresholds are frozen
  per PR-D decision and revisiting them is a separate task.

---

## §6 Final recommendation

**PROCEED to Step 04A code as designed**, with **three explicit
guardrails** that the implementation must enforce:

1. **Iterate from the manifest, not the filesystem.**
   Use `manifest[(manifest.use_for_primary_bathymetry == True) | (manifest.source_priority == 'regional')]`
   as the driver, deduplicate by `output_path`, and partition M.rar
   internally by `track_id`. Document this in the code with a
   reference to §1.3 above. This eliminates all three double-counting
   pitfalls.

2. **Emit both `n_points_pass` and `n_unique_triples` per (track, cell).**
   The multibeam dup_ratio of 0.69 (per-cell p99 0.92) makes
   `n_unique_triples` mandatory for any cross-branch weighting, and
   emitting both at Step 04A keeps downstream calibration (Step 06b/07)
   unblocked. Skipping `n_unique_triples` at Step 04A would force a
   re-scan of the 240M-row Step 03A corpus later.

3. **Add a `manual_review_flag` boolean** initialized from the
   Step 03B supplementary manifest (depth_anomaly_flag = True, or
   bbox-only divergent intersect pairs, or high jump-density tracks
   like f-10-89-cp). This is informational only — it does not gate
   inclusion at Step 04A — but it gives Step 06b/07 a hook to demote
   suspect cells without re-reading the supplementary manifest.

The audit found no premise in the task description that needs to
change before Step 04A starts. **One important framing correction:**
M.rar lives in its own `regional_mrar` source branch, not under
`multibeam` (the PRD task text wording "use bathymetry_points.parquet
only (multibeam branch)" was off — the right framing is "use it as
its own regional branch, parallel to but separate from the ncei
multibeam branch"). This is consistent with how the manifest already
encodes it (`source_priority='regional'`) and how the directories are
already laid out (`derived/regional_mrar/`).

### Acceptance criteria check

- [x] **Confirms no nc/xyz intersect double counting under recommended input selection.** — §1.2 + §1.3, manifest's `use_for_primary_bathymetry` filter is correct; intersect `__xyz.parquet` files do not exist on disk; recommended discipline avoids the 3 pitfalls.
- [x] **Confirms f-10-89-cp handling recommendation (with justification).** — §1.4: keep in primary aggregation with `manual_review_flag=True`. Conservative alternative documented (move to `primary_with_review` at Step 06b — deferred).
- [x] **Confirms whether `n_unique_triples` should be used for effective count.** — §3.2/§3.3: yes for MB; either column for SB/MRAR. Step 04A emits both so Step 06b/07 chooses per use.
- [x] **Provides source-specific aggregation plan for singlebeam, NCEI multibeam, regional_mrar.** — §4.1–§4.3.
- [x] **Leaves A/B/C tier calibration for later (explicit statement).** — §5 first bullet.
- [x] **Final recommendation: proceed-to-code or revise-first.** — Proceed; three guardrails enumerated.

---

## §7 Anomalies & open questions surfaced (not blockers)

These were noticed during the audit but do not change the proceed-to-code
recommendation:

1. **M.rar 3-row manifest sharing input/output paths** (§1.3 pitfall #2)
   is an audit-trail oddity. It's the most natural way to record that
   M.rar has 3 distinct quadrant "source files" but they share an
   already-merged parquet output (PR-F joined them). Step 04A code
   that follows the §6 guardrails won't be tripped up, but future
   maintainers reading the manifest cold may be surprised. A
   one-line comment in the manifest writer or a sentinel column
   (e.g. `output_path_shared=True` for the 3 mrar rows) would help.
   Out of scope here.

2. **The PRD task description states "M.rar branch has no
   `points_checked` stage."** This is no longer true post-Step 03A —
   `ncei/derived/regional_mrar/points_checked/bathymetry_points.parquet`
   exists (113.36M rows, 1.44 GB, 22-col Step 03A schema, all rows
   passing because PR-F already cleaned land + extreme depths). The
   parquet shares the same point counts as PR-F's
   `ncei/archive/zhoushuai_processed_M/bathymetry_points.parquet`
   modulo the 313 rows in the first quadrant that PR-F-cleaned but
   Step 03A flagged (likely the `depth==0` sentinel residue from
   PR-F's land split — 313 zero-depth survivors). Step 04A should
   consume the Step 03A copy (uniform with the SB/MB branches) and
   not re-read the PR-F copy directly. The task description should be
   updated to reflect this.

3. **Singlebeam p99 max cell `n_points_pass = 8,762`** is the nc track
   `index13` (17 MB raw, called out in PRD Q6 evidence as a
   borderline-density NCEI nc file). It also has `pred=singlebeam`
   under the R2 classifier — but at 8,762 pts in a single 1-arcmin
   cell it's behaving more like a low-density swath than a sparse
   sounding. Worth a manual look during Step 06b file-flag
   calibration; **not** a Step 04A concern.

4. **MB ∩ SB cell overlap = 4,127 cells** (69% of MB cells coincide
   with SB-covered cells). This is good news for sensitivity studies
   (we can directly compare AUV vs singlebeam in the same cells) but
   has no effect on Step 04A/B since the branches are kept separate.
   Surfaced for context.

---

## §8 Output artifacts produced by this audit

Under `ncei/derived/aggregation_design_audit/`:

- `branch_summary.tsv` — full-corpus per-branch track/point/cell counts + cross-branch overlap.
- `cell_distribution_percentiles.tsv` — per-cell metric distributions per branch.
- `f10_89_cp_summary.tsv` — f-10-89-cp Step 03A+03B flag breakdown (2 rows: primary nc + supplementary xyz).
- `f10_89_cp_cells.tsv` — 495 per-cell rows for f-10-89-cp pass-basic points (full, not sampled).

Cross-linked research note (this audit's process / scratch):
`.trellis/tasks/05-11-singlebeam-integration/research/step04_aggregation_design_audit.md`
(short pointer back to this doc + the script).

This document: `ncei/docs/step04_aggregation_design_audit.md`
