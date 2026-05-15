# tmp/ Data Classification — Handoff for Trellis Task

> **Created**: 2026-05-15
> **Type**: Investigation + decision handoff. Read this in a fresh
> session and feed it to `trellis-brainstorm` to spin up a PRD task.
> **Status**: All findings recorded, all key decisions made. No files
> have been moved or renamed yet — those operations are the task's
> responsibility.

---

## TL;DR for fresh-session pickup

Two large new files arrived in `/mnt/data2/00-Data/tmp/` on 2026-05-15:

| File | Size | Classification (decided) |
|---|---:|---|
| `total_tracklines_xyz.zip` | 854 MB (3.3 GB unzipped) | **NCEI tracklines, mostly singlebeam + ~12 confirmed multibeam files** (mixed bundle) |
| `M.rar` | 379 MB (4.2 GB unzipped) | **"Processed NCEI multibeam, regional"** (user-asserted) |

Three classes of decisions are baked in below: (a) **where each file
goes**, (b) **how to handle the mixed sb/mb bundle**, (c) **the
broader naming refactor** triggered by the long-standing
`NCEI_multibeam ≡ JAMSTEC` mislabel plus this new data.

The next session should spawn a Trellis task to **execute** these
decisions — this doc holds the **what** and **why**; the task PRD
will hold the **how**.

---

## What was investigated

Two newly transferred files in `/mnt/data2/00-Data/tmp/`:

```
-rw-rw-r--  396,719,475  May 15 20:26  M.rar
-rw-rw-r--  853,745,775  May 15 20:27  total_tracklines_xyz.zip
```

(Plus older files in the same dir from Jul 2024 / Dec 2024 — leftover
sample data + inspection scripts, not part of this investigation.)

---

## Finding 1 — `total_tracklines_xyz.zip`

### Structure
- 5,383 `.xyz` files inside a single `total_tracklines_xyz/` dir.
- 3-column CSV with header `LON,LAT,CORR_DEPTH`.
- Filenames follow **NCEI GEODAS** trackline ID convention: 5-digit
  numeric (`00373`, `04883`, `82116`) + alphanumeric legacy IDs
  (`107a23`, `1986n1a`, `ztes6bar`, `hu77024`, `odp173jr`).
- 3.33 GB total uncompressed.

### Overlap vs existing `NCEI_singlebeam_tracks_raw_2018files.zip`

The existing input is 2,018 `.nc` files (MGD77+ NetCDF). Filename
set-intersection:

| Set | Count |
|---|---:|
| xyz unique basenames | 5,382 |
| nc unique basenames | 2,018 |
| **intersect (same basename)** | **1,850** |
| **only-in-xyz (new tracks)** | **3,532** |
| **only-in-nc (xyz missing 168 nc tracks)** | **168** |

→ xyz covers **91.7%** of nc's tracks **and** adds **3,532 new
tracks** (2.7× superset on the union side). But 168 nc tracks are
**not present** in the new xyz, so the integration cannot be a
straight replacement — it must union the two archives.

### Single-beam vs multi-beam composition

File-size distribution (5,382 files, implied points = size / 27 bytes):

| Implied point count | Files | Share | Likely sonar type |
|---|---:|---:|---|
| < 5k | 2,910 | 54.1% | Short singlebeam |
| 5k–100k | 2,364 | 43.9% | Typical singlebeam |
| 100k–1M | 96 | 1.8% | Long singlebeam / short multibeam (ambiguous) |
| **> 1M** | **12** | 0.2% | **Confirmed/likely multibeam** |

The 12 large files (>27 MB, >1M points each):

| File | Rows | Notes |
|---|---:|---|
| `ra304-15.xyz` | 4,791,753 | R/V Atlantis cruise RA-304-15. **Multibeam swath**: 4.79M points across lon[-42.48, -38.38] × lat[-24.00, -21.42] = 4.1° × 2.6° area (~130k km², ~37 pts/km²). A singlebeam track of equivalent length would have ~10-100× fewer points. |
| `ra022-3.xyz` | ~4.7M | Same R/V Atlantis RA series, same multibeam signature. |
| `sentry418.xyz` … `sentry428.xyz` (10 files) | 2.1M – 4.1M each | **AUV Sentry** = WHOI autonomous underwater vehicle carrying high-resolution multibeam sonar. Definitionally multibeam. |

→ **xyz zip is a MIXED bundle**: ~98% singlebeam + at least 12
confirmed multibeam + ~96 borderline files needing per-file density
classification.

### Sample file content
```
LON,LAT,CORR_DEPTH
-20,35,5441
-18.76275,36.80209,5331
-10.01,38.87363,213
...
```
Note: leading row `-20,35,5441` looks like a sentinel/origin marker
(unusually round coordinates, depth too shallow for that lon/lat).
Worth flagging for the cleaning step.

---

## Finding 2 — `M.rar`

### Structure
- RAR4 archive, requires `unrar` (installed 2026-05-15 via
  `sudo apt install -y unrar`).
- Contains 3 quadrant-partitioned `.txt` files + 1 dir entry:

| Inner file | Compressed | Uncompressed | Rows |
|---|---:|---:|---:|
| `M/0-180E-0-85N.txt` | 128 MB | 1.37 GB | 38,635,741 |
| `M/0-90W-0-85S.txt` | 90 MB | 929 MB | 25,295,079 |
| `M/90-180W-0-85S.txt` | 178 MB | 1.86 GB | 49,480,083 |
| **Total** | **379 MB** | **4.17 GB** | **113,410,903** |

- Format: tab-separated `lon\tlat\tdepth`, no header, 6-decimal floats.

### Coverage (geographic ranges measured)

| File | lon range | lat range | depth range |
|---|---|---|---|
| `0-180E-0-85N.txt` | [0.000, 180.003] | [0.000, 84.994] | [-15752, +2669] |
| `0-90W-0-85S.txt` | [-90.000, 0.001] | [-73.225, -0.001] | [-14951, +5451] |
| `90-180W-0-85S.txt` | [-180.000, -89.997] | [-78.676, -0.001] | [-30990, -5] |

**Missing quadrants** (the half of Earth NOT in this archive):
- **North hemisphere west** (Americas, North Pacific, North Atlantic,
  Arctic) — entirely absent. This is the part of the ocean where
  NCEI-as-a-US-institution would normally have the densest coverage.
- **South hemisphere east** (Indian Ocean, southwest Pacific south
  of equator) — also absent.

→ Coverage is **3 of 6 quadrants ≈ 50% of Earth**. **NOT global.**

### Anomalies / red flags
- Positive depth values up to **+5,451 m** (Andes-scale elevation)
  and **+2,669 m** in first file → contains **land elevation**, not
  just bathymetry. Either a topo DEM is mixed in or sentinels.
- **-30,990 m** depth in third file — far exceeds Mariana Trench
  (~11 km). Almost certainly a sentinel / nodata code.
- Cleaning step will need to: (a) clip positive depths (treat as
  land/invalid), (b) filter implausible negatives below some
  threshold (e.g., depth < -11,500 m → nodata).

### Density signature
Sampling first 1,000 rows of `0-180E-0-85N.txt` along the lon=0
meridian: lat steps are **irregular** (0.00027°, 0.00359°,
0.00360°, 0.00452°, 0.00589°, 0.00667°, 0.00776°, 0.00936° …).

- **Not a regular grid** → not a gridded product like ETOPO/GEBCO.
- Step magnitude ~0.0036° (≈ 13 arcsec along-track) is **5× denser**
  than `NCEI_singlebeam/singlebeam.xyz` (~0.018° step) → consistent
  with multibeam along-track sampling.
- The irregularity + density signature together fit **decimated
  multibeam point cloud aggregation**.

### Scale comparison

| Dataset | Points |
|---|---:|
| `M.rar` total | 113,410,903 |
| `NCEI_singlebeam/singlebeam.xyz` | 114,507,390 |
| `NCEI_multibeam` (raw, 5,140 files) | ~2,805,756,150 |

The row-count proximity to `singlebeam.xyz` (1% difference) is a
**coincidence** — geographic coverage and sampling density rule out a
same-data hypothesis (M.rar misses N-hemisphere-W entirely; M.rar is
5× denser along-track).

→ M.rar's 113M points = **~4% of NCEI multibeam raw point total**.
Consistent with a heavily decimated regional subset, not a 1-to-1
re-export.

### Classification decision

The user asserts (2026-05-15): **"M.rar is real NCEI multibeam data,
but processed and regional."** Open uncertainty:
- The 4% point-count discrepancy and the missing N-hemisphere-W
  coverage are not yet fully explained.
- The presence of land elevation values is not yet explained.
- No provenance documentation came with the file (no README inside
  the archive).

The new task should treat the user assertion as authoritative for
placement/naming, but the **cleaning step** must handle the
anomalies (positive depths, extreme negatives) and the **provenance
sidecar** (a small `SOURCE.md` next to the data) should record this
ambiguity.

---

## Cross-cutting finding — directory naming chaos

The existing repo already has a documented mislabel:

- `/mnt/data2/00-Data/ship/NCEI_multibeam/` is **actually JAMSTEC
  multibeam data** (Japan Agency for Marine-Earth Science and Tech).
  Confirmed and recorded in
  `docs/experiments/2026-05_dataset-source-attribution.md`.

The new data compounds the naming inconsistency:

| Current path | Real content | Status |
|---|---|---|
| `ship/NCEI_multibeam/` | JAMSTEC multibeam (88 GB, 2.8B pts) | Mislabeled (long-standing) |
| `ship/NCEI_singlebeam/` (raw input: `NCEI_singlebeam_tracks_raw_2018files.zip`) | NCEI tracklines, predominantly singlebeam (.nc, 2,018 files); **may include some multibeam — not yet audited** | Possibly mislabeled |
| `tmp/total_tracklines_xyz.zip` (new) | NCEI tracklines, mixed: ~98% singlebeam + 12+ confirmed multibeam (.xyz, 5,383 files) | Mixed bundle |
| `tmp/M.rar` (new) | "Processed NCEI multibeam, regional" (per user) | Provenance partly opaque |

### User decision on naming strategy

**Rename by provenance** (the "big refactor" option). Specifically:

- `NCEI_multibeam/` → **`multibeam_jamstec/`** ✅ confirmed by user
  (2026-05-15). Aligns with the existing
  `05-11-singlebeam-integration` task PRD which already proposed this
  rename.
- `NCEI_singlebeam/` → name TBD by the new task. Candidate:
  `singlebeam_ncei/` (if we choose to keep the singlebeam label and
  route multibeam files away at the pipeline stage) or
  `tracklines_ncei/` (if we keep mixed bundling).

### User decision on the mixed xyz bundle

**Bundle stays together at filesystem stage, split at pipeline
stage.** Specifically:

- The full `total_tracklines_xyz.zip` (5,383 files) goes into the
  renamed singlebeam-ncei directory as a sibling to the existing
  .nc archive.
- A new pipeline step (Step 01 or 01a) auto-classifies each file by
  density and routes the ~12+ multibeam files to a separate
  multibeam-ingest path while the bulk of singlebeam files flow
  through the singlebeam pipeline.
- Classifier threshold to start: **>1M points per file = multibeam**
  (tunable). The 96 borderline files (100k-1M points) need a per-file
  decision rule, likely based on lat/lon spread test (a singlebeam
  track of 1M points is ~10,000 km long; if a 1M-point file fits in
  a <50 km box, it must be multibeam swath).

### User decision on M.rar placement

**New top-level sibling dir: `/mnt/data2/00-Data/ship/multibeam_processed_M/`**.
- Keeps the renamed `multibeam_jamstec/` corpus pristine.
- Provides a clearly-isolated location for a derived/processed product.
- Name retains the "M" from the source archive (origin unclear),
  rename to a more descriptive slug if/when provenance is confirmed.

---

## Locked decisions (summary)

| # | Decision | Status |
|---|---|---|
| 1 | `NCEI_multibeam/` → `multibeam_jamstec/` rename | ✅ confirmed |
| 2 | `NCEI_singlebeam/` → renamed (final slug TBD by new task), provenance-based | ✅ direction confirmed |
| 3 | New `total_tracklines_xyz.zip` goes into the renamed singlebeam dir as a bundle | ✅ confirmed |
| 4 | Pipeline does the sb/mb split, not the filesystem | ✅ confirmed |
| 5 | `M.rar` placed at `ship/multibeam_processed_M/` | ✅ confirmed |
| 6 | `M.rar` classified as "processed NCEI multibeam, regional" for now | ✅ confirmed |
| 7 | Cleaning step required for M.rar (positive depths, extreme negatives) | ✅ implicit, to be designed in task |
| 8 | Union strategy needed for xyz + nc: 168 nc-only tracks must be retained | ✅ confirmed |

---

## Open questions for the new Trellis task

These intentionally remain open for the next session's brainstorm:

1. **Final slug for the singlebeam dir rename**: `singlebeam_ncei/`,
   `tracklines_ncei/`, or `ncei_tracklines/`? (Affects path strings
   that downstream code embeds.)
2. **Density classifier rule for the 96 borderline files** (100k-1M
   points): pure threshold, or threshold + spatial-spread check?
3. **M.rar cleaning thresholds**: positive depth → drop or convert to
   land mask? Lower depth cutoff (-11500 m? -15000 m?)
4. **Migration ordering**: rename `NCEI_multibeam/` → `multibeam_jamstec/`
   first (separable, big diff), or batch with the new-data placements?
5. **Path-string rewrite scope**: how many scripts/reports embed
   `NCEI_multibeam`? Grep the repo, surface the count, decide whether
   to write a rewrite script vs. manual sed.
6. **Provenance audit for `NCEI_singlebeam/`**: is its .nc archive
   actually mixed sb+mb too (like the new xyz zip)? If yes, the
   pipeline-stage classifier must handle both inputs.
7. **What happened to the 168 nc-only tracks?**: are they corrupt in
   the new xyz, deliberately excluded, or just missing? Quick spot
   check on 5 of them.
8. **M.rar provenance follow-up**: is the "M" directory a known
   collaborator's naming? Worth asking the data sender for a README.

---

## Suggested scope for the new Trellis task

The natural framing is to **expand the existing planning task
`05-11-singlebeam-integration`** rather than create a new task,
because:

- That task already covers (a) singlebeam pipeline build, (b) shared
  lib extraction between mb and sb pipelines, (c) the
  `NCEI_multibeam → multibeam_jamstec` + `NCEI_singlebeam → singlebeam_ncei`
  renames.
- Adding (d) ingest new xyz bundle, (e) ingest M.rar, (f)
  pipeline-stage sb/mb classifier is a coherent expansion of the
  same refactor scope — all four pieces need the same renames done
  first.

The next-session brainstorm should:

1. Read this doc.
2. `python3 ./.trellis/scripts/task.py current` to confirm no active task.
3. Decide whether to **expand `05-11-singlebeam-integration`** or
   **create a new task** for the broader refactor. Default
   recommendation: expand the existing task (since it owns the
   renames the new work depends on).
4. Load `trellis-brainstorm`, revise `prd.md`, address the 8 open
   questions above one at a time.

---

## References

- `docs/experiments/2026-05_dataset-source-attribution.md` — the
  original NCEI_multibeam ≡ JAMSTEC writeup. Contains the
  "do not rename naively" warning (load-bearing path strings).
- `NCEI_multibeam/docs/bad_subzips_investigation_2026-05.md` — sibling
  investigation pattern used as the template for this doc.
- `.trellis/tasks/05-11-singlebeam-integration/` — the existing
  planning task likely to be expanded by the new session.
- `.trellis/tasks/archive/2026-05/05-11-recover-bad-subzips/prd.md` —
  illustrates the level of detail expected in a final PRD.

---

## Handoff instructions to future-Claude / future-Codex

**In a fresh session, do not re-derive the findings above** — they
are already evidence-backed by row counts, MD5 comparisons, spatial
range scans, and file-size distributions performed 2026-05-15.

What you SHOULD do in the fresh session:

1. Run `python3 ./.trellis/scripts/get_context.py` to confirm state.
2. Read this entire doc end-to-end before asking the user anything.
3. Probe the 8 open questions one at a time via brainstorm.
4. Spawn or expand the appropriate Trellis task; bring the
   `Locked decisions` table over verbatim into `prd.md` so they
   are not re-negotiated.
5. Do NOT move/rename any files outside the new task's
   implementation phase — those operations are destructive,
   touch many downstream paths, and must be tied to a single
   atomic commit (or commit series) inside the task.

---

## Footer 2026-05-16: directory rename has been executed (PR-A + PR-B landed)

The 8 brainstorm questions above are all resolved (see
`.trellis/tasks/05-11-singlebeam-integration/prd.md` for the locked
decision table). PR-A and PR-B of that task executed the two top-level
directory renames; PR-C / PR-D+ remain. All path strings below this
footer refer to the **pre-rename layout** and are preserved verbatim
as the historical record. Current canonical paths:

| Pre-rename (in this doc) | Post-rename (current) |
|---|---|
| `ship/NCEI_multibeam/` | `ship/jamstec/multibeam/` |
| `ship/JAMSTEC/{bathymetry_data,archive,gravity_data}/` | `ship/jamstec/{archive/bathymetry_data,archive/source_zips,gravity_data}/` |
| `ship/NCEI_singlebeam/` | `ship/ncei/` *(PR-B executed 2026-05-16; tracklines_{nc,xyz}/ + archive/ subdirs planned in PR-C)* |
| `ship/multibeam_processed_M/` *(proposed)* | `ship/ncei/archive/zhoushuai_processed_M/` *(planned in PR-C)* |
