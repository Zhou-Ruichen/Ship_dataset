# Build NCEI singlebeam pipeline + shared lib + dir renames + new-data ingest

## Goal

Build the NCEI singlebeam pipeline (reusing the JAMSTEC multibeam pipeline
pattern), factor out a shared lib between the two, coordinate the
long-pending `NCEI_multibeam → multibeam_jamstec` + `NCEI_singlebeam →
<TBD>` directory renames, **and** absorb two new data drops
(`total_tracklines_xyz.zip`, `M.rar`) into this same refactor so the path
churn happens exactly once.

## Background — what's already decided

Two threads of prior decisions feed this task:

### Thread A — reuse + rename plan (from 2026-05-11)

- Build singlebeam from raw
  `NCEI_singlebeam_tracks_raw_2018files.zip` (2,018 per-track `.nc` files,
  MGD77+) — **not** from the flat `singlebeam.xyz` dump (per-track structure
  was lost in that flattening).
- ~80% code reuse from multibeam: Steps 03_qc / 04a / 04b / 05 / 06a-d / 08
  / 09-11 reuse algorithmically; `02_standardize` is the only real rewrite
  (NetCDF reader instead of `.dat` ASCII); `07` reuses but A/B/C tier
  thresholds need re-calibration for singlebeam point density.
- Shared lib structure (`ship/_common/` or per-dataset symlinks) — decide
  during implementation, don't pre-design.
- Path-rewrite script for hardcoded `NCEI_multibeam` / `NCEI_singlebeam`
  strings in manifests/*.parquet metadata, docs/*.md, configs/*.yaml.
- `JAMSTEC/` stays as the source archive dir name.

### Thread B — tmp/ data classification (from 2026-05-15)

Full investigation in
[`docs/experiments/2026-05_tmp-data-classification.md`](../../../docs/experiments/2026-05_tmp-data-classification.md).
Headline findings:

| File | Size | Classification |
|---|---:|---|
| `total_tracklines_xyz.zip` | 854 MB → 3.3 GB | NCEI tracklines, source: 安德超. Mixed bundle: ~98% singlebeam + ≥12 **confirmed** multibeam files (AUV Sentry + R/V Atlantis, physical evidence: 4.79M points across 130k km² area) + ~96 borderline 100k–1M-point files. |
| `M.rar` | 379 MB → 4.2 GB | "Processed NCEI multibeam, regional" (source: 周帅); covers partial regions; contains positive depths (land!) and a -30,990 m sentinel — needs cleaning |
| `singlebeam.xyz` | - | NCEI singlebeam data, source: 孙明智 (flat dump in `NCEI_singlebeam/singlebeam.xyz`) |

Overlap of new xyz vs existing nc: 1,850 shared basenames, 3,532
**new** tracks in xyz, 168 nc tracks **absent** from xyz → integration must
union, not replace. 91.7% coverage of nc + 2.7× superset.

## Scope — what this task delivers

1. **Singlebeam pipeline build + shared lib extraction** (Thread A reuse plan).
2. **Directory renames** (Thread A + Thread B, coordinated):
   - `NCEI_multibeam/` → `jamstec/` (pure provenance; supersedes earlier
     `multibeam_jamstec/` proposal)
   - `NCEI_singlebeam/` → `ncei/`
   - **NCEI internal layout (B1)**:
     - `ncei/tracklines_nc/` — existing 2,018-file `.nc` archive
       (unpacked from `NCEI_singlebeam_tracks_raw_2018files.zip`).
     - `ncei/tracklines_xyz/` — new 5,383-file `.xyz` bundle
       (unpacked from `total_tracklines_xyz.zip`).
     - `ncei/derived/singlebeam/` — pipeline output for singlebeam-classified files.
     - `ncei/derived/multibeam/` — pipeline output for multibeam-classified files.
     - **`ncei/archive/zhoushuai_processed_M/`** — extracted `M.rar` contents (frozen data, source: 周帅).
     - **`ncei/archive/sunmingzhi_singlebeam_xyz/`** — `singlebeam.xyz` flat dump (frozen legacy data, source: 孙明智).
   - **JAMSTEC internal layout**: `jamstec/multibeam/` for existing
     multibeam corpus; future sub-corpora (gravity_data etc.) live as
     siblings.
3. **New-data ingest**:
   - Place `total_tracklines_xyz.zip` as a sibling of the existing `.nc`
     archive inside the renamed singlebeam dir.
   - Extract `M.rar` into `ncei/archive/zhoushuai_processed_M/`.
   - Move old `singlebeam.xyz` into `ncei/archive/sunmingzhi_singlebeam_xyz/`.
   - All above with a `SOURCE.md` sidecar recording provenance + open questions.
4. **Pipeline-stage sb/mb classifier** (new step, location TBD — probably
   `01_classify` or `01a_split`):
   - For mixed bundles, classify each .xyz file as singlebeam vs multibeam.
   - Threshold rule: >1M points = multibeam (confirmed). 96 borderline
     100k–1M files need a second rule (TBD in Q2).
   - Route multibeam files into a multibeam-ingest path; singlebeam files
     flow through the singlebeam pipeline.
5. **M.rar cleaning step** (positive depths → drop/mask; extreme negatives →
   nodata clip; specifics in Q3).
6. **Spec updates**: remove the "misnamed" caveat from
   `spec/backend/*` once renames land; document the classifier step and
   the new `ncei/archive/zhoushuai_processed_M/` corpus.
7. **Minimum verification**: re-run Step 08 in T1 footprint with renamed
   paths, confirm bit-identical output to baseline.

## Locked decisions (carried verbatim from 2026-05_tmp-data-classification.md)

| # | Decision | Status |
|---|---|---|
| 1 | `NCEI_multibeam/` → **`jamstec/`** (pure provenance; supersedes earlier `multibeam_jamstec/` proposal). Future JAMSTEC sub-corpora (e.g. gravity_data) live under `jamstec/<sensor-or-form>/`. | ✅ confirmed 2026-05-15 |
| 2 | `NCEI_singlebeam/` → **`ncei/`** (pure provenance). | ✅ confirmed 2026-05-15 (Q1) |
| 2a | **NCEI internal layout = B1**: raw archives split by upstream form: `ncei/tracklines_nc/` (existing 2,018-file .nc archive), `ncei/tracklines_xyz/` (new 5,383-file .xyz bundle). Pipeline-classified outputs live in `ncei/derived/singlebeam/` and `ncei/derived/multibeam/`. | ✅ confirmed 2026-05-15 (Q1) |
| 3 | New `total_tracklines_xyz.zip` is unpacked into `ncei/tracklines_xyz/` as a sibling of `ncei/tracklines_nc/`. | ✅ confirmed |
| 4 | Pipeline does the sb/mb split, not the filesystem (sensor split materializes in `ncei/derived/{singlebeam,multibeam}/`). | ✅ confirmed |
| 5 | `M.rar` placed at `ncei/archive/zhoushuai_processed_M/` (isolated from active pipeline). | ✅ confirmed |
| 6 | `M.rar` classified as "processed NCEI multibeam, regional" for now | ✅ confirmed |
| 7 | Cleaning step required for M.rar (positive depths, extreme negatives) | ✅ implicit, to be designed in task |
| 8 | Union strategy needed for xyz + nc: 168 nc-only tracks must be retained | ✅ confirmed |
| 9 | **Existing uppercase `JAMSTEC/` tree absorbed into new `jamstec/` in PR-A** (one atomic refactor, no temporary case-collision). Final layout: `jamstec/multibeam/` (← `NCEI_multibeam/`), `jamstec/gravity_data/` (← `JAMSTEC/gravity_data/`), `jamstec/archive/source_zips/` (← `JAMSTEC/archive/`, ~27 GB), `jamstec/archive/bathymetry_data/` (← `JAMSTEC/bathymetry_data/`, ~25 GB). Empty placeholder dirs (`JAMSTEC/{code,derived,docs,figures,output}`) dropped. All on same mount → `mv` is instant rename. | ✅ confirmed 2026-05-16 |
| 10 | **NCEI .nc raw archive is dual-consumed across sibling projects**: SHA256 `1a9b2c5b7e72f1ca1d17b0f1b7172186ebf56be1ebde67113ad8978a48514eed` lives in two byte-identical copies — bath pipeline at `ship/ncei/archive/source_zips/NCEI_singlebeam_tracks_raw_2018files.zip` (consumed via `depth` field) and gravity project at `/mnt/data2/00-Data/gravity/NCEI/archive/NCEI.zip` (consumed via `gobs` / `faa` fields). Byte-identical duplicate **by design**. Do not dedupe; each project owns its consumer-side copy. Two projects, one source. | ✅ confirmed 2026-05-16 |
| 11 | **李杨 is the primary external contributor** — NetCDF conversion of 2,018 NCEI MGD77 ASCII tracks (2024-07-31) + the source 7z packagings behind 4 previously-unknown JAMSTEC bathymetry + gravity sub-archives (`bathymetry.7z`, `gravity.7z`, `bathymetry_data/*.zip`, `gravity_data/*.zip`; KR06-03 / KM17-02 fingerprint-verified). 孙明智 = forwarder for `.nc` + own-work provider for `singlebeam.xyz`; 郭恒洋 = independent JAMSTEC transferer with different 2024-07-24 repackaging (`国外水深第{一,二}部分.zip`). | ✅ confirmed 2026-05-16 |

## Open Questions (to resolve in this brainstorm)

1. ~~**Final slug for the singlebeam dir rename**~~ → **resolved**:
   `ncei/` (pure provenance). Jamstec side likewise simplified to
   `jamstec/`. Internal layout = B1 (see Locked decision #2a).
2. ~~**Density classifier rule for the 96 borderline files**~~ → **resolved**:
   **R2 = threshold + spatial-spread**. Rule:
   - `>1M points` → multibeam (confirmed by the 12-file evidence).
   - `100k–1M points`: compute bbox = (lon_max−lon_min) × (lat_max−lat_min) × cos(lat_mid)
     and density = points / bbox_km². Classify as multibeam if
     `bbox < 5,000 km²` **OR** `density > 50 pts/km²`.
   - `<100k points` → singlebeam.
   - **Starter thresholds are tunable**: implementation first dumps
     (bbox_area, density) for all 96 borderline files to a CSV +
     scatter plot, user eyeballs to calibrate, thresholds get
     frozen into the classifier and recorded in spec.
3. ~~**M.rar cleaning thresholds**~~ → **resolved**:
   - **Positive depths** (`depth > 0`): **convert to land mask**. Land
     points are split off into a sidecar product (e.g.
     `ncei/archive/zhoushuai_processed_M/land_mask.parquet` — exact filename/format
     decided in implementation) rather than dropped, so the land DEM
     mixed into M.rar is preserved as a labeled artifact even if no
     downstream consumer exists yet. Bathymetry pipeline only sees
     `depth ≤ 0` rows.
   - **Lower-bound cutoff**: **`depth < −11,500 m` → nodata**
     (~5% past Challenger Deep ≈ −10,984 m). Rows below cutoff dropped
     entirely (they are clearly sentinels, not observations).
   - Cleaning produces a sidecar audit: rows-in, land-rows, nodata-rows,
     bathymetry-rows, per-quadrant counts, written into
     `ncei/archive/zhoushuai_processed_M/cleaning_audit.parquet` and summarized in
     `SOURCE.md`.
4. ~~**Migration ordering**~~ → **resolved**: **O1 three-step,
   all before singlebeam pipeline code**:
   - **PR-A**: `NCEI_multibeam/` → `jamstec/` rename + path-string
     rewrite across repo. Pure path refactor, no data change. Should
     be reproducibly green (Step 08 bit-identical on renamed paths).
   - **PR-B**: `NCEI_singlebeam/` → `ncei/`, with existing `.nc`
     archive contents relocated under `ncei/tracklines_nc/`. Path
     rewrite for `NCEI_singlebeam` references.
   - **PR-C**: New-data ingest — unpack `total_tracklines_xyz.zip` to
     `ncei/tracklines_xyz/`, extract `M.rar` to
     `ncei/archive/zhoushuai_processed_M/`, move `singlebeam.xyz` to `ncei/archive/sunmingzhi_singlebeam_xyz/`, write `SOURCE.md` sidecars. Pure
     additions and archiving, no rewrites.
   - **Only after PR-A + PR-B + PR-C land** do we start singlebeam
     pipeline build + classifier work. Pipeline code is then written
     against the final path layout from day one.
5. ~~**Path-string rewrite scope**~~ → **resolved**:
   - **Grep scope measured (2026-05-15)**:
     - `NCEI_multibeam`: 23 files / ~16 docs (.md) + 3 trellis task.json
       + 3 .py lines (all `source_dataset = "NCEI_multibeam"` literal
       value, NOT paths) + 0 parquet manifest hits.
     - `NCEI_singlebeam`: 9 files / ~6 docs (.md) + 2 task.json + 0 .py.
   - **Q5a — tooling**: small Python rewrite script with dry-run mode,
     explicit include/exclude list (skip `archive/` + `.git/` + the 3
     `source_dataset` literal lines in `.py`). Auditable + repeatable.
   - **Q5b — `source_dataset` literal value**: **keep `"NCEI_multibeam"`**
     in `.py` source. Preserves Step 08 bit-identical verification
     (SCOPE #5). Treat `source_dataset` as logical lineage label, not
     a path; spec to document this.
   - **Archived task PRDs / task.json (under `.trellis/tasks/archive/`)
     are NOT rewritten** — they are frozen historical records.
6. ~~**Provenance audit for `NCEI_singlebeam/`**~~ → **resolved**:
   - **No standalone audit pass**. The R2 classifier (from Q2)
     handles both inputs uniformly: `.nc` goes through Step 02
     standardize → R2 classifier; `.xyz` goes through minimal parse
     → R2 classifier. Files routed to `ncei/derived/{singlebeam,multibeam}/`
     accordingly.
   - **Evidence collected (2026-05-15)**: raw `.nc` archive contains
     2,019 .nc + 2 .txt = 2,021 entries (task.json said 2,018 — note
     this 3-file discrepancy; track in audit log). None of the 12
     confirmed-multibeam `.xyz` basenames (ra022-3, ra304-15,
     sentry418–428) have a `.nc` counterpart — upstream already
     filtered them out. The `.nc` set has 10 files >5MB
     (largest: `index13.nc` = 17 MB ≈ 0.6–1.4M points compressed) —
     these are the borderline candidates the R2 classifier will catch.
   - The 96 xyz borderline + ~10 nc borderline together form the
     calibration scatter plot for R2 threshold tuning.
7. ~~**What happened to the 168 nc-only tracks?**~~ → **resolved**:
   - **Spot-check (2026-05-15)**: 5 random nc-only basenames
     (csio02rr, sho08-69, l1077bs, kea03-69, wn7907) all have typical
     singlebeam sizes (87–282 KB). `csio02rr.nc` read cleanly via
     netCDF4 — standard MGD77+ vars (time/lon/lat/depth/gobs/faa),
     9,783 records. No corruption, no multibeam signature.
   - Reason for absence in new xyz is **unknown** (could be upstream
     pipeline bug or deliberate filtering) — recorded as a known
     unknown in `ncei/SOURCE.md`.
   - **Treatment**: ingest as normal singlebeam through the pipeline.
     Add a manifest column `source_completeness ∈ {nc_only,
     nc_xyz_intersect, xyz_only}` for downstream auditability.
8. ~~**`M.rar` provenance follow-up**~~ → **resolved**:
   - **Do not actively chase provenance.** Record as known unknown in
     `ncei/archive/zhoushuai_processed_M/SOURCE.md` (user assertion 2026-05-15 +
     anomalies + 4% point-count ratio + missing-quadrant note).
   - Task does not block on external response. If downstream questions
     surface later, revisit then.

## Requirements (evolving)

* Singlebeam pipeline produces a multi-resolution dataset structurally
  parallel to the multibeam pipeline output.
* Shared lib avoids any algorithm-level duplication across mb/sb.
* All renames atomic at the commit-series level (no half-renamed
  intermediate state on `main`).
* New data ingested with provenance sidecars.
* `M.rar` cleaning is deterministic and recorded (so re-runs reproduce).

## Acceptance Criteria (evolving)

* [ ] `NCEI_multibeam/` no longer exists on `main`; `jamstec/multibeam/`
  is the canonical path.
* [ ] Uppercase `JAMSTEC/` no longer exists on `main`; its subdirs live
  under unified lowercase `jamstec/` (`gravity_data/`,
  `archive/source_zips/`, `archive/bathymetry_data/`).
* [ ] `NCEI_singlebeam/` renamed to final slug (decided in Q1).
* [ ] `ncei/archive/zhoushuai_processed_M/` exists with extracted M.rar contents +
  `SOURCE.md`.
* [ ] `ncei/archive/sunmingzhi_singlebeam_xyz/` exists with the old `singlebeam.xyz` dump + `SOURCE.md` recording provenance (孙明智).
* [ ] `total_tracklines_xyz.zip` placed in singlebeam dir +
  `SOURCE.md` recording the provenance (安德超) and uncertainty about multibeam mixing.
* [ ] Pipeline-stage sb/mb classifier exists, with tests covering the
  12 confirmed multibeam files (must all classify as mb) and a sample
  of clear singlebeam files (must all classify as sb).
* [ ] M.rar cleaning step drops/masks positive depths and clips
  implausible negatives, with thresholds recorded.
* [ ] Step 08 reproduces bit-identical output post-rename in T1 footprint.
* [ ] No remaining `NCEI_multibeam` / `NCEI_singlebeam` string in
  `**/*.{py,sh,md,yaml,parquet-metadata}` (verified by grep).
* [ ] `spec/backend/*` no longer carries the "misnamed" caveat.

## Definition of Done

* Pipeline tests green for both mb and sb paths
* Rename + classifier covered by tests
* Spec updated; CLAUDE.md / README references audited
* Provenance sidecars in place
* PR (or PR series) reviewed and merged

## Out of Scope (explicit)

* JAMSTEC/gravity_data/ processing (separate future task).
* Full re-run of Step 02–08 on multibeam (paths change but data doesn't).
* Re-deriving the findings in `2026-05_tmp-data-classification.md` (they
  are evidence-backed; treat as inputs).
* Soliciting external provenance from the M.rar data sender (Q8 is a
  follow-up nice-to-have, not a blocker).

## Technical Notes

* Existing NCEI_multibeam ≡ JAMSTEC mislabel writeup:
  `docs/experiments/2026-05_dataset-source-attribution.md` — contains the
  "do not rename naively" warning about load-bearing path strings.
* tmp/ classification investigation:
  `docs/experiments/2026-05_tmp-data-classification.md` — the doc this PRD
  expands on.
* PRD format reference:
  `.trellis/tasks/archive/2026-05/05-11-recover-bad-subzips/prd.md`.
* Raw singlebeam input archive:
  `/mnt/data2/00-Data/NCEI_singlebeam_tracks_raw_2018files.zip` (443 MB,
  2,018 .nc MGD77+ files).
* `M.rar` requires `unrar` (installed 2026-05-15).

## Research References

(Pointers below were validated inline during brainstorm; no separate
`research/*.md` files persisted.)

* `docs/experiments/2026-05_tmp-data-classification.md` — source
  investigation doc with all evidence (file counts, basename set
  diffs, density distributions, M.rar coverage analysis).
* `docs/experiments/2026-05_dataset-source-attribution.md` — the
  `NCEI_multibeam ≡ JAMSTEC` mislabel writeup + load-bearing path
  string warning.
* Grep scope of `NCEI_multibeam` / `NCEI_singlebeam` (collected
  2026-05-15 during Q5): 23 + 9 files; 0 parquet hits; 3 .py literal
  values; archive PRDs frozen.
* Spot-check evidence for Q7 (2026-05-15): 5/168 nc-only basenames
  read cleanly, sizes 87–282 KB, no multibeam signature.

## Decision (ADR-lite)

**Context**: Two parallel threads converged here — (a) the long-pending
NCEI multibeam/singlebeam rename + singlebeam pipeline build, and
(b) two new data drops on 2026-05-15 needing classification and
placement. Bundling them into one task is cheaper than three separate
refactors because they all share the same path layout.

**Decisions** (8 brainstorm questions, all resolved 2026-05-15):

1. Top-level rename: `jamstec/` and `ncei/` (pure provenance, dropped
   the `multibeam_jamstec/` proposal in favor of symmetric pure-provenance
   naming so jamstec can host future sub-corpora like gravity_data).
2. NCEI internal layout = B1: `ncei/tracklines_{nc,xyz}/` for raw
   archives by upstream form, `ncei/derived/{singlebeam,multibeam}/`
   for pipeline-classified outputs.
3. Mixed-bundle sb/mb split: pipeline-stage R2 classifier (threshold +
   spatial-spread), starter thresholds `bbox<5,000 km² OR density>50 pts/km²`,
   tuned on the calibration scatter plot of all borderline files (96 xyz + ~10 nc).
4. M.rar cleaning: positive depths → land mask sidecar (preserved as
   labeled artifact); `depth < −11,500 m` → nodata; audit sidecar.
5. Migration order = O1: three separable PRs (jamstec rename / ncei rename /
   new-data ingest), all before singlebeam pipeline code.
6. Path rewrite: small Python script with dry-run, skip `archive/`,
   skip the 3 `source_dataset = "NCEI_multibeam"` literal lines.
7. `source_dataset` literal stays `"NCEI_multibeam"` to keep Step 08
   bit-identical verification intact (lineage label, not a path).
8. M.rar provenance: not chased externally; recorded as known unknown.
9. 168 nc-only tracks: ingest as normal singlebeam; manifest gains
   `source_completeness ∈ {nc_only, nc_xyz_intersect, xyz_only}`.

**Consequences**:
- Single classifier mechanism covers all NCEI inputs (.nc + .xyz).
- Three separable PRs before pipeline code minimize blast radius.
- Step 08 bit-identical baseline remains the verification anchor; not
  re-baselined.
- `ncei/archive/zhoushuai_processed_M/` is isolated from the main raw/derived pipelines, so
  M.rar's unresolved provenance doesn't contaminate the curated pile.
- Two known unknowns persist: (a) reason the 168 nc tracks are missing
  from xyz, (b) M.rar source organization. Both recorded in SOURCE.md;
  neither blocks downstream work.

## Implementation Plan (PR series)

**PR-A — `NCEI_multibeam/` + `JAMSTEC/` → unified `jamstec/` rename** ✅ executed 2026-05-16
- Move existing `NCEI_multibeam/` tree to `jamstec/multibeam/`.
- Absorb existing uppercase `JAMSTEC/` tree into new lowercase `jamstec/`:
  - `JAMSTEC/gravity_data/` → `jamstec/gravity_data/`
  - `JAMSTEC/archive/` → `jamstec/archive/source_zips/`
  - `JAMSTEC/bathymetry_data/` → `jamstec/archive/bathymetry_data/`
  - Drop empty placeholders `JAMSTEC/{code,derived,docs,figures,output}/`.
- Run the Python path-rewrite script on `**/*.{md,json}` excluding
  `archive/` and the 3 .py literal-value lines. Scope covers both
  `NCEI_multibeam` and `JAMSTEC/` path-string references.
- Re-run Step 08 on T1 footprint; assert bit-identical output.
- Update `spec/backend/*` to drop the "misnamed" caveat and reflect
  the unified `jamstec/` layout.

PR-A execution notes (2026-05-16):
- `mv` sequence atomic on `/mnt/data2`; layout exactly matches plan.
- Rewrite tool at `scripts/refactor/rewrite_paths.py` (dry-run mode + ordered mapping).
  14 files rewritten, 58 occurrences total; .py files never touched.
- Verification = hash-only smoke check (per Step-08 verification decision):
  20 .py files SHA256-identical pre/post mv (`ok=20 bad=0`); 3
  `source_dataset = "NCEI_multibeam"` literals preserved verbatim
  (Q5b lineage-label decision); grep returns no `NCEI_multibeam` /
  `JAMSTEC/` strings outside the explicit allowlist (3 historical
  docs in `docs/experiments/` + 3 archived task files + this PRD).
- Spec rewrites: `spec/backend/index.md` "directory naming caveat"
  section replaced with post-rename provenance note;
  `spec/backend/directory-structure.md` top-level layout block
  rewritten to show unified `jamstec/` tree.
- Forward-pointer footers (with pre-→post path table) appended to
  `docs/experiments/2026-05_dataset-source-attribution.md` and
  `docs/experiments/2026-05_tmp-data-classification.md`; those two
  docs themselves are NOT path-string rewritten (they describe the
  pre-rename state as historical record).

**PR-B — `NCEI_singlebeam/` → `ncei/` rename + .nc reorg** ✅ executed 2026-05-16
- Move existing `NCEI_singlebeam/` `.nc` content under `ncei/tracklines_nc/`.
- (The flat `singlebeam.xyz` dump is handled in PR-C — archived under
  `ncei/archive/sunmingzhi_singlebeam_xyz/`, not pulled into `tracklines_nc/`.)
- Path-rewrite script second invocation, narrower scope.
- Spec update.

PR-B execution notes (2026-05-16):
- `mv NCEI_singlebeam ncei` atomic on `/mnt/data2`; 2 git-tracked files
  (`docs/README.md`, `docs/On the accuracy evaluation and correction of
  global single-beam depths.pdf`) carried over verbatim; the 3.1 GB
  `singlebeam.xyz` and empty placeholder dirs (`code/`, `derived/`,
  `figures/`, `output/`) came along untracked / gitignored.
- The .nc-content relocation under `ncei/tracklines_nc/` is **deferred
  to PR-C** along with the `total_tracklines_xyz.zip` extraction — PR-B
  is intentionally a pure rename so the data-ingest churn lands in one
  PR (PR-C) and PR-B's diff stays auditable as paths-only.
- Rewrite tool gained a `--pr {A,B}` CLI flag + `MAPPING_PR_B`
  (`NCEI_singlebeam/` → `ncei/`). **No bare-string fallback**: the
  external zip `NCEI_singlebeam_tracks_raw_2018files.zip` (at
  `/mnt/data2/00-Data/`) is an upstream-archive filename and a bare
  `NCEI_singlebeam` → `ncei` rule would corrupt it. Grep verified all
  in-scope directory references use the trailing-slash form.
- 4 files rewritten, 9 occurrences total (`.trellis/spec/backend/directory-structure.md` = 1, `.trellis/tasks/05-11-singlebeam-integration/task.json` = 2, `README.md` = 4, `docs/多波束船测数据处理流程.md` = 2); .py files never touched (no NCEI_singlebeam literals exist in any .py).
- Manual edits beyond the rewrite tool: README.md "Naming caveat" block
  replaced with a post-rename provenance note + cleaned-up layout tree
  (the old layout had a stale duplicate `jamstec/` entry from PR-A);
  `spec/backend/directory-structure.md` `ncei/` row updated to drop the
  "to be renamed in PR-B" parenthetical; `.gitignore` swapped the stale
  `NCEI_singlebeam/{archive,singlebeam.xyz}` entries for
  `ncei/{singlebeam.xyz,archive/}`.
- Forward-pointer footers in `docs/experiments/2026-05_dataset-source-attribution.md`
  and `docs/experiments/2026-05_tmp-data-classification.md` updated to
  flip the singlebeam row from "planned" to "executed"; those two docs
  remain path-string-frozen (historical record).
- Verification = grep returns no `NCEI_singlebeam/` strings outside the
  explicit allowlist (PRD + 2 historical docs + archived task files in
  `.trellis/tasks/archive/`); 2 remaining `NCEI_singlebeam_` matches
  in `ncei/docs/README.md` are the external zip filename (preserved
  by design); `git check-ignore` confirms the new gitignore rules fire.

**PR-C — New-data ingest** ✅ executed 2026-05-16
- Extract `total_tracklines_xyz.zip` → `ncei/tracklines_xyz/`.
- Extract `M.rar` → `ncei/archive/zhoushuai_processed_M/`.
- Move `NCEI_singlebeam/singlebeam.xyz` → `ncei/archive/sunmingzhi_singlebeam_xyz/`.
- Write `SOURCE.md` for each (provenance + known unknowns + decisions).
- Move the two source archives from `/mnt/data2/00-Data/tmp/` to their
  destinations (or symlink — decided in implementation).

PR-C execution notes (2026-05-16):
- Archive extraction (all on `/mnt/data2`, instant on same mount):
  - `NCEI_singlebeam_tracks_raw_2018files.zip` (463 MB) → unwrap
    leading `NCEI/` dir, place 2,018 `.nc` + 2 `.txt` sidecars under
    `ncei/tracklines_nc/`. Final disk: 1.1 GB.
  - `total_tracklines_xyz.zip` (854 MB) → unwrap leading
    `total_tracklines_xyz/` dir, place 5,382 `.xyz` files under
    `ncei/tracklines_xyz/`. Final disk: 3.2 GB.
  - `M.rar` (379 MB, `unrar` installed 2026-05-15) → unwrap leading
    `M/` dir, place 3 quadrant `.txt` files under
    `ncei/archive/zhoushuai_processed_M/`. Final disk: 4.0 GB.
- File-count reconciliation:
  - `.nc` count is **2,018 (canonical)**. The "2,021" `unzip -l` header
    counted 2,018 .nc + 2 .txt + 1 wrapping dir entry; the Q6
    "2,019 + 2" evidence was a one-off miscount. The 2 upstream `.txt`
    sidecars (`NCEI_Ara1.txt`, `validation_results.txt`, ~18 MB total)
    are kept on disk and gitignored — provenance recorded in
    `ncei/tracklines_nc/SOURCE.md`.
  - `.xyz` count is **5,382, not 5,383**. The "5,383 files" in the
    zip header counted the wrapping `total_tracklines_xyz/` dir entry;
    actual file count is 5,382. Investigation doc + PRD references to
    5,383 are off-by-one (now annotated in tracklines_xyz/SOURCE.md).
- Source archives relocation (all `mv`, instant on same mount):
  - `tmp/total_tracklines_xyz.zip` → `ncei/archive/source_zips/`.
  - `tmp/M.rar` → `ncei/archive/zhoushuai_processed_M/M.rar`
    (kept beside its unpacked content for audit).
  - `/mnt/data2/00-Data/NCEI_singlebeam_tracks_raw_2018files.zip` →
    `ncei/archive/source_zips/` (long-standing artifact; rule:
    upstream archives unpacked into the active tree live alongside
    unpacked content inside the repo; documented in source_zips/SOURCE.md).
  - `tmp/` is now empty of the two new archives (other files in `tmp/`,
    e.g. the older inspection scripts and `random_tracks/`, are
    untouched).
- Existing-file relocation:
  - `ncei/singlebeam.xyz` (3.1 GB) →
    `ncei/archive/sunmingzhi_singlebeam_xyz/singlebeam.xyz`.
    `mv` instant on same mount.
- Final `ncei/` data sizes: tracklines_nc/=1.1G, tracklines_xyz/=3.2G,
  archive/zhoushuai_processed_M/=4.3G (extracts + M.rar),
  archive/sunmingzhi_singlebeam_xyz/=3.1G, archive/source_zips/=1.3G
  (2 zips + SOURCE.md). Cumulative ≈ 13 GB on disk.
- SOURCE.md sidecars (5 written, all under git):
  - `ncei/tracklines_nc/SOURCE.md` — NCEI public archive, 168 nc-only
    tracks recorded as known unknown (Q7).
  - `ncei/tracklines_xyz/SOURCE.md` — 安德超, mixed sb/mb bundle,
    R2 classifier handoff (Q2/Q4).
  - `ncei/archive/zhoushuai_processed_M/SOURCE.md` — 周帅, anomalies +
    cleaning plan deferred to PR-F (Q3/Q8).
  - `ncei/archive/sunmingzhi_singlebeam_xyz/SOURCE.md` — 孙明智, legacy
    flat dump, frozen artifact.
  - `ncei/archive/source_zips/SOURCE.md` — index doc for the 2 source
    zips in this dir + convention statement.
- `.gitignore` changes:
  - Dropped the old `ncei/singlebeam.xyz` line (file moved to archive).
  - Dropped the directory-level `ncei/archive/` ignore — replaced by
    file-by-file ignore via the extension globs (`*.zip`, `*.rar`,
    `*.xyz`, `*.nc`) plus 2 tightly-scoped `*.txt` rules
    (`ncei/tracklines_nc/*.txt`,
    `ncei/archive/zhoushuai_processed_M/*.txt`).
    Rationale: dir-level ignore would block tracking of provenance
    sidecars (SOURCE.md, README.md) inside ignored archive subdirs,
    even with `!` negation rules (git won't descend into a fully-ignored
    dir).
  - Added `*.xyz` to the generic-extension block.
  - Net diff: 12 inserts, 3 deletes in `.gitignore`.
- Verification:
  - 5 SOURCE.md trackable (`git check-ignore` exits 1 for each).
  - All heavy payloads ignored (`.zip`, `.rar`, `.nc`, `.xyz`, scoped
    `.txt`).
  - Existing tracked `jamstec/multibeam/docs/{bad_subzips,bad_nested_zips,sha256_remote}.txt`
    unaffected.
  - `git ls-files --others --exclude-standard ncei/` returns exactly
    the 5 SOURCE.md files; no heavy data accidentally exposed.
  - `git status --short` shows only `M .gitignore` plus the 5
    untracked SOURCE.md (i.e. exactly the intended PR-C delta plus
    this PRD update).
- Out of scope (preserved for later PRs as planned):
  - R2 sb/mb classifier (PR-D).
  - M.rar cleaning (PR-F) — extracts are raw and unmodified.
  - No `.py` files touched.

**PR-D — Shared lib extraction + classifier** ✅ executed 2026-05-16
- Factor algorithmic overlap from JAMSTEC pipeline into `_common/`
  (exact structure decided during implementation, not pre-designed).
- Implement R2 classifier as a pipeline stage (post-standardize for
  .nc, post-minimal-parse for .xyz).
- Tests: 12 confirmed-mb xyz files all → mb; sample of clear sb files → sb;
  borderline files produce the (bbox, density) scatter to calibrate.

PR-D execution notes (2026-05-16):
- **Package location**: `ship/_common/` (matches the candidate name in
  the PRD; leading underscore signals "private internal lib, not a
  published package", visually distinct from dataset dirs).
- **Scope shipped**: classifier + tiny `.xyz`/`.nc` lon-lat readers +
  calibration driver + tests + a `README.md` listing the planned
  PR-E migrations (Step 03 / 04a / 04b / 05 / 06a-d / 08 / 09-11
  primitives). No `jamstec/multibeam/code/` step was actually migrated
  in this PR — PR-E owns the migration.
- **API decisions**:
  - `classify(lon, lat) -> R2Result` is the single entry point;
    `classify_from_arrays(..., points=N)` is the cheap-path override
    for cases where point count is already known.
  - `R2Result` frozen dataclass exposes `label`, `points`, `bbox_km2`,
    `density_ppkm2`, `reason`. `bbox_km2`/`density_ppkm2` are `None`
    when the decision was reached by hard rule (no bbox computed).
  - Threshold constants exported at module level
    (`R2_HARD_MB_POINTS = 1_000_000`, `R2_HARD_SB_POINTS = 100_000`,
    `R2_BBOX_KM2_CUTOFF = 5_000.0`, `R2_DENSITY_PPKM2_CUTOFF = 50.0`).
  - Edge cases: `bbox_km2 == 0` (all points identical) → mb with
    density=`+inf`, reason=`borderline_bbox_below_cutoff`.
    Mismatched/empty arrays → `ValueError`.
- **Calibration scan** (full corpus, 30 s wall time on `/mnt/data2`):
  - Scanned 7,400 files (2,018 .nc + 5,382 .xyz).
  - Per-band counts: `<100k` → 7,260 sb / 0 mb; `100k–1M` →
    123 sb / 5 mb; `>1M` → 0 sb / 12 mb.
  - The 12 hard-cutoff mb files match the confirmed multibeam set
    (10× AUV Sentry sentry418–428, ra022-3, ra304-15) — exactly as
    predicted.
  - 5 borderline-mb hits, all defensible:
    - `nf-10-01-02-crer-rfr.xyz`: 195k pts / 91 km² = 2,141 pts/km²
      (compact reef survey, clearly mb).
    - `ra028-09.xyz`: 800k pts / 1,089 km² = 734 pts/km² (R/V Atlantis
      RA-series, same lineage as the confirmed `ra022-3` / `ra304-15`).
    - `ab1999.xyz`: 110k pts / 1,089 km² = 101 pts/km².
    - `at27a.xyz`: 710k pts / 7,874 km² = 90 pts/km² (over density
      cutoff).
    - `int_9125.xyz`: 106k pts / 4,237 km² = 25 pts/km² (just under
      bbox cutoff).
  - Notable borderline-sb classifications worth a manual look in PR-E
    if the team wants to tighten further:
    - `sermilik.xyz` (Sermilik Fjord, Greenland): 372k pts / 10,089 km²
      = 37 pts/km² — likely an mb survey by mission, but density falls
      below 50 cutoff. Recorded as starter-threshold-borderline.
  - Scatter PNG (`_common/calibration/r2_borderline.png`) shows clean
    separation: mb cluster upper-left (high density / low bbox), sb
    cluster lower-right (low density / large bbox).
- **Threshold tuning decision**: **defaults retained**
  (`R2_HARD_MB_POINTS = 1e6`, `R2_HARD_SB_POINTS = 1e5`,
  `R2_BBOX_KM2_CUTOFF = 5_000 km²`, `R2_DENSITY_PPKM2_CUTOFF = 50 pts/km²`).
  Calibration scatter shows clean separation under starter values; the
  5 borderline-mb hits are all defensible, and the 12 hard-cutoff mb
  files all land correctly. Any future tightening to catch the
  ~10–20 likely-mb borderline-sb cases (e.g. `sermilik.xyz`) is a
  PR-E follow-up once the pipeline can route them through both legs
  and the user sees actual downstream impact.
- **Tests** (11 passed under both `python -m unittest` and `pytest`
  in 1.1–1.3 s): synthetic-array hard-mb / hard-sb / borderline-compact /
  borderline-dense / borderline-default-sb / zero-bbox-edge /
  mismatched-arrays / empty-arrays / cheap-path override + 2
  real-fixture tests (`ra304-15.xyz` → mb, 3 short sb files → sb).
  Real-fixture tests `pytest.skip` cleanly when files are absent.
- **No `.py` files in `jamstec/multibeam/code/` touched** (hash-only
  smoke check pattern). The shared lib has zero consumers in this PR;
  consumer-side adoption begins in PR-E.
- **Spec touch**: appended decision #10 (R2 classifier) to
  `.trellis/spec/backend/pipeline-design-decisions.md`.
- **`.gitignore` change**: none — the CSV / PNG / .txt summary in
  `_common/calibration/` are not caught by existing rules
  (the `*.parquet` / `*.zip` / etc. extension globs do not match).
- **Files created** (10 total):
  - `_common/__init__.py`
  - `_common/r2_classifier.py`
  - `_common/io_helpers.py`
  - `_common/r2_calibration.py`
  - `_common/README.md`
  - `_common/tests/__init__.py`
  - `_common/tests/test_r2_classifier.py`
  - `_common/calibration/r2_borderline.csv` (128 borderline rows)
  - `_common/calibration/r2_borderline.png` (scatter, 120 dpi)
  - `_common/calibration/r2_calibration_summary.txt`
- **Files modified**:
  - `.trellis/spec/backend/pipeline-design-decisions.md` (new section 10)
  - `.trellis/tasks/05-11-singlebeam-integration/prd.md` (these notes)
- **Post-review fix 2026-05-16**: added
  `_common/calibration/r2_hard_mb_files.csv` sidecar (12-row roster of
  the hard-mb band: `ra022-3`, `ra304-15`, `sentry418-424`,
  `sentry426-428`) so the >1M-point set is auditable without re-running
  the calibration driver. Roster also embedded in
  `r2_calibration_summary.txt`. Spec gained a source-of-truth pointer
  to `_common/r2_classifier.py` module-level threshold constants
  (prevents silent drift when PR-E tunes thresholds).
- **Post-check decision 2026-05-16 (PR-D.5)**: import strategy =
  "run from repo root" convention (see `AGENTS.md` Python-execution
  section + `spec/backend/pipeline-design-decisions.md` §11). Resolves
  Major #1 from trellis-check review; no code change required. Docs
  updated: `AGENTS.md`, `_common/README.md`,
  `spec/backend/pipeline-design-decisions.md`,
  `spec/backend/directory-structure.md`.

**PR-E — Singlebeam pipeline build (split into E1–E4)**
- **Do not full-run the complete singlebeam pipeline at PR-E start.** Begin with
  read-only / small-sample checks and track-level manifests; keep `M.rar`,
  singlebeam, and multibeam out of any combined final validation table until
  later PRs.
- **Pre-PR-E gate 1 — field + sign check**:
  - Verify MGD77 / MGD77+ `depth` semantics before normalizing anything:
    corrected bathymetry depth is normally **positive below sea level**
    (GMT MGD77 docs: corrected bathymetry, metres, positive downward).
  - Verify NCEI `.xyz` export semantics separately: NCEI XYZ depth is documented
    as **negative**.
  - Record raw sign diagnosis in the manifest (`depth_sign_raw`) and make any
    sign normalization explicit in code / docs; do not silently assume JAMSTEC
    sign conventions apply to NCEI.
- **Pre-PR-E gate 2 — post-rename multibeam smoke check**:
  before substantive singlebeam development, prove the existing multibeam path
  survived the directory refactor. Minimum checks:
  1. import / unit tests;
  2. old multibeam pipeline small-sample run;
  3. T1-footprint Step 08 smoke check;
  4. compare to pre-rename baseline: hash / bit-identical when order is stable,
     or sorted core-field comparison with tiny float tolerance if output order
     may differ.
  Full global Step 08 is **not** a PR-E blocker; defer it until PR-G / full
  validation planning.

**PR-E1 — NCEI trackline source manifest first (no large point-table output)**
- First deliverable of PR-E. Build the total source inventory before writing a
  large `02_standardize_singlebeam.py`.
- Outputs:
  - `ncei/manifests/trackline_source_manifest.parquet`
  - `ncei/manifests/trackline_source_manifest.tsv`
  - `ncei/docs/trackline_source_manifest_report.md`
- Functionality:
  - scan `ncei/tracklines_nc/`;
  - scan `ncei/tracklines_xyz/`;
  - read per-track point count, bbox, field availability, depth sign, and source
    lineage;
  - compute `source_completeness` (`nc_only` / `nc_xyz_intersect` / `xyz_only`)
    at this earliest manifest stage, not as a post-standardization backfill;
  - run the R2 classifier;
  - output borderline / review-needed cases.
- Minimum manifest fields:
  - `track_id` — normalized track identifier.
  - `source_type` — `ncei_nc` / `ncei_xyz`.
  - `source_completeness` — `nc_only` / `nc_xyz_intersect` / `xyz_only`.
  - `source_path` — raw file path.
  - `source_archive` — source archive or contributor lineage.
  - `n_points`.
  - `bbox_lon_min`, `bbox_lon_max`, `bbox_lat_min`, `bbox_lat_max`.
  - `has_time`, `has_depth`, `has_gobs`, `has_faa`.
  - `depth_sign_raw`.
  - `instrument_class_pred` — classifier prediction: `singlebeam` / `multibeam`.
  - `classification_review` — whether manual review is required.

**PR-E2 — standardize `.nc` singlebeam only**
- Implement `ncei/code/02_standardize_singlebeam.py`, but first version only
  supports `--source nc` plus `--run-label sample|full`.
- Inputs are manifest-filtered `.nc` tracks classified as singlebeam; do not yet
  merge with `.xyz`, multibeam, M.rar, or validation cells.
- Outputs:
  - `ncei/derived/singlebeam/points_raw/<track_id>.parquet`
  - `ncei/manifests/singlebeam_points_raw_manifest.parquet`
  - `ncei/docs/singlebeam_standardization_report.md`
- Point schema:
  - `source_type` = `ncei_nc`.
  - `track_id`.
  - `point_index_in_track`.
  - `time` (nullable).
  - `lon_raw`, `lat_raw`, `lon`, `lat`.
  - `depth_raw`.
  - `depth_m_positive_down`.
  - `elev_m`.
  - `gobs` (nullable).
  - `faa` (nullable).
  - `source_completeness`.
  - `instrument_class_pred`.
  - `standardization_version`.

**PR-E3 — add `.xyz` as supplementary input after `.nc` schema stabilizes**
- `.xyz` classified as singlebeam routes to
  `ncei/derived/singlebeam/points_raw/`.
- `.xyz` classified as multibeam routes to
  `ncei/derived/multibeam/points_raw/`.
- Missing `.xyz` fields stay null; do not invent fake time/gravity fields.
  Manifest records `has_time=False`, `has_gobs=False`, `has_faa=False`.
- Purpose is to supplement `.nc` coverage and split mixed-bundle multibeam, not
  to replace `.nc`.

**PR-E4 — classification review table**
- Each run emits `ncei/manifests/trackline_classification_review.tsv` with at
  least:
  - `track_id`, `source_type`, `n_points`, `bbox_area_km2`,
    `point_density_km2`, `instrument_class_pred`, `classification_rule`,
    `review_reason`, `manual_override`.
- Add a review branch without immediately changing the R2 prediction rule:
  tracks with `<100,000` points but very small bbox / very high density remain
  `pred=singlebeam` initially, but get `review_multibeam_candidate` so small
  AUV / processed-multibeam cases are not silently missed.

**Post-PR-E aggregation guidance**
- Step 03 / 04a / 04b / 05 / 06a-d / 08 / 09-11 may reuse the JAMSTEC
  multibeam algorithmic framework via shared lib, but **thresholds must not be
  blindly copied**. Multibeam 1-arcmin quality tier rules such as
  `n_points >= 100`, `n_file_cells >= 2`, `n_cruises >= 2`, and
  `iqr_depth <= 50m` may be too strict for sparse singlebeam tracks.
- Keep data layers separate until validation design is explicit:
  - `ncei/derived/singlebeam/{points_raw,points_checked,file_cells_1min,cells_1min}/`
  - `ncei/derived/multibeam/{points_raw,points_checked,file_cells_1min,cells_1min}/`
  - `derived/validation/{primary_multibeam_cells_1min,supplementary_singlebeam_cells_1min,combined_ship_cells_1min}`
- Validation roles:
  - multibeam = primary validation baseline;
  - singlebeam = supplementary spatial coverage / sensitivity analysis;
  - processed `M.rar` = regional supplement or separate experiment;
  - legacy flat dump = archive only.
- `M.rar` remains PR-F only. Do not include it in PR-E.

**PR-F — M.rar cleaning step**
- Positive-depth → `ncei/archive/zhoushuai_processed_M/land_mask.parquet`.
- `depth < −11,500 m` → nodata, dropped.
- `cleaning_audit.parquet` + `SOURCE.md` updates.

**PR-G — Verification + docs**
- Step 08 bit-identical baseline on renamed paths (smoke check).
- Spec refresh; in-tree READMEs updated.
- `MEMORY.md` / `CLAUDE.md` audit for stale references.

## Finding 2026-05-16: ncei/ corpora relationship clarification (post-PR-C)

After PR-C landed, read-only row-count + single-track density
measurements were taken on all three NCEI singlebeam corpora. The
results corrected an implicit assumption in
`docs/experiments/2026-05_dataset-source-attribution.md` (2026-05-11
"Singlebeam reuse note") that `singlebeam.xyz` is the merged form of
the per-track `.nc` archive. Numbers rule that out.

### Corrected relationship picture

```
NCEI upstream archive
  ├─ per-track .nc snapshot (curated; mb pre-filtered) → tracklines_nc/    28.9M points / 2,018 files
  └─ per-track .xyz snapshot (raw; mb mixed in)         → tracklines_xyz/  123.4M points / 5,382 files
                                                              │
                                                              │ flat merge (lossy: per-track ID, time, gobs/faa dropped)
                                                              ▼
                                                      孙明智 singlebeam.xyz   114.5M points
                                                      (≈ tracklines_xyz at an earlier snapshot or
                                                       upstream-filter variant; 7% point-count delta)
```

| Set | Files | Total points | Avg / track | Measurement |
|---|---:|---:|---:|---|
| `ncei/tracklines_nc/` | 2,018 .nc | ~28,894,834 (28.9M) | ~14,319 | 20-file random sample × 2,018 |
| `ncei/tracklines_xyz/` | 5,382 .xyz | ~123,352,000 (123.4M) | ~22,920 raw / ~14,000 after mb-strip | sum(file_size) / 27 bytes |
| `ncei/archive/sunmingzhi_singlebeam_xyz/singlebeam.xyz` | 1 (merged flat) | 114,507,390 (114.5M) | n/a | `wc -l` (authoritative) |

After stripping the 12 confirmed multibeam files from
`tracklines_xyz/` (each ~4M points → ~48M total mb), the remaining
~75M / ~5,370 sb tracks ≈ 14,000 pts/track — which **matches**
`tracklines_nc/`'s 14,319 pts/track. This is strong evidence that the
nc and xyz corpora are different packagings of the same underlying
NCEI singlebeam point cloud: xyz wraps an additional multibeam swath
layer; nc is the curated / mb-filtered view.

### Impact on locked decisions

This finding **does not change any locked decision**, but it sharpens
the reasoning behind two of them. Audit table:

| # | Decision (verbatim shorthand) | Still correct? | Reasoning |
|---|---|---|---|
| 1 | `NCEI_multibeam/` → `jamstec/` | Yes | Multibeam side unaffected — finding is singlebeam-side only. |
| 2 | `NCEI_singlebeam/` → `ncei/` | Yes | Provenance-based slug still right; finding only clarifies *internal* corpus relationship. |
| 2a | NCEI internal layout = B1 (`tracklines_{nc,xyz}/`, `derived/{sb,mb}/`) | Yes | Split-by-upstream-form is reinforced: nc and xyz are demonstrably different packagings of the same source, so keeping them as siblings (not collapsing one into the other) is exactly right. |
| 3 | `total_tracklines_xyz.zip` → `ncei/tracklines_xyz/` | Yes | Placement decision intact. |
| 4 | Pipeline does sb/mb split, not filesystem | Yes | Sharpened: 14k/track baseline for sb confirms the mb-mix in xyz is a per-file phenomenon (12 files >>14k each), exactly what the R2 pipeline-stage classifier is designed for. |
| 5 | `M.rar` → `ncei/archive/zhoushuai_processed_M/` | Yes | M.rar is multibeam — finding doesn't touch it. |
| 6 | `M.rar` = "processed NCEI multibeam, regional" | Yes | Unaffected. |
| 7 | Cleaning step required for M.rar | Yes | Unaffected. |
| 8 | Union strategy for xyz + nc: 168 nc-only tracks retained | Yes, **sharpened** | Still correct as a basename-set fact. New framing: the 168 nc-only basenames are NOT corruption of xyz; they reflect snapshot drift / upstream-filter variance between two NCEI snapshots (curated nc filtered differently than raw xyz). Per-track density math (14k/track in both) confirms same physical corpus, different curated views. Union remains the right ingestion strategy. |
| 9 | `JAMSTEC/` absorbed into `jamstec/` in PR-A | Yes | Already executed; unaffected. |

### Implicit-assumption sharpening (text vs spirit)

Two reasoning chains in the PRD/spec implicitly conflated
`singlebeam.xyz` with `tracklines_nc/`. The conclusions stand; the
chains need a footnote:

- **"168 nc-only tracks" framing**: spirit unchanged (union strategy
  retained). Text correction: the reason for the basename diff is
  snapshot drift / upstream-filter variance, **not** xyz pipeline bugs
  or corruption. Documented in this section and propagated to the two
  SOURCE.md sidecars + attribution doc.
- **"Build pipeline from `.nc`" decision**: spirit unchanged
  (`tracklines_nc/` remains the canonical pipeline input for
  PR-D / PR-E). Text correction: previous reasoning
  ("singlebeam.xyz lost per-track structure during merging *from the
  .nc files*") is wrong about the source of that merge. Updated
  reasoning: (a) per-track structure preserved in `.nc`; (b) `.nc`
  is mb-filtered upstream → cleaner input that doesn't depend on the
  R2 classifier being perfect; (c) `.nc` has standardized MGD77+
  columns (time, gobs, faa) that bare `.xyz` lacks.

### R2 classifier scope (PR-D)

The new per-track density floor (~14,000 pts/track for clean
singlebeam) is consistent with the PRD's earlier assumption
("a singlebeam track of 1M points is ~10,000 km long" → ~100 pts/km).
The 100k–1M borderline band sits 7×–70× above the 14k norm — well
clear of the singlebeam tail. The R2 thresholds
(`bbox<5,000 km² OR density>50 pts/km²`) remain appropriate. **No
change to PR-D classifier scope.** The 96 borderline xyz files +
~10 borderline nc files still form the calibration scatter set as
originally planned.

### Where this finding is recorded

- This PRD section (canonical).
- `ncei/archive/sunmingzhi_singlebeam_xyz/SOURCE.md` — appended
  "Relationship to other NCEI singlebeam corpora" section.
- `docs/experiments/2026-05_dataset-source-attribution.md` — inline
  `[2026-05-16 correction]` paragraph after the "Singlebeam reuse
  note" section (paragraph is additive; the original historical
  narrative is preserved).

## Finding 2026-05-16 (李杨 finding chain)

Two fingerprint-driven findings landed late 2026-05-16 that finalize
the transfer-chain attribution for nearly all sub-corpora on this
disk. Both are evidence-backed and supersede the high-confidence
inferences in Locked decision #10 + the prior 2026-05-16 footers in
`jamstec/SOURCE.md` and `ncei/tracklines_nc/SOURCE.md`.

### Full transfer-chain table (authoritative)

| Path | Content origin | Conversion / packaging | Transfer chain | Date window |
|---|---|---|---|---|
| `ncei/tracklines_nc/` (2,018 `.nc`) | NCEI MGD77 ASCII (NGDC IDs) | **李杨 2024-07-31** MGD77+ NetCDF conversion | **李杨 → 孙明智 → user** | Dec 2024 (file mtime) |
| `ncei/archive/source_zips/NCEI_singlebeam_tracks_raw_2018files.zip` | same | same | same | Dec 2024 |
| `/mnt/data2/00-Data/gravity/NCEI/archive/NCEI.zip` (byte-identical duplicate) | same | same | same | Dec 2024 |
| `ncei/tracklines_xyz/` (5,382 `.xyz`) | NCEI tracklines `.xyz` raw (mb-mixed) | unknown (likely upstream NCEI) | **安德超 → user** | 2026-05-15 |
| `ncei/archive/sunmingzhi_singlebeam_xyz/singlebeam.xyz` (1 flat file, 114.5M pts) | flatten of an earlier NCEI `.xyz` snapshot (hard-verified via Hawaii xyz-only basename point-match) | unknown merger (possibly 孙明智 own-work) | **孙明智 → user** | Jan 2025 |
| `ncei/archive/zhoushuai_processed_M/M.rar` | NCEI processed mb (regional, anomalies) | unknown processor | **周帅 → user** | 2026-05-15 |
| `jamstec/multibeam/archive/国外水深第{一,二}部分.zip` (24.5 GB) | JAMSTEC | 2024-07-24 packaging (date-named cruise zips inside) | **郭恒洋 → user** | Dec 2024 |
| `jamstec/archive/source_zips/bathymetry.7z` (26 GB) | JAMSTEC (same corpus as `国外水深`, different packaging) | 2024-04-11 packaging (cruise-ID-named DMO zips inside) | **李杨 → user** | Apr–Dec 2024 |
| `jamstec/archive/source_zips/gravity.7z` (2 GB) | JAMSTEC gravity | 2024-04-10 packaging | **李杨 → user** | Apr–Dec 2024 |
| `jamstec/archive/bathymetry_data/*.zip` (25 GB, 776 zips) | JAMSTEC (same source) | byte-identical unpack of `bathymetry.7z` | **李杨 → user** (via the 7z) | derived |
| `jamstec/gravity_data/*.zip` (2 GB, 954 zips) | JAMSTEC gravity (same source) | byte-identical unpack of `gravity.7z` (`KM17-02_gravity.zip` byte-equal verified) | **李杨 → user** (via the 7z) | derived |

### Evidence

**Finding A — 李杨 as JAMSTEC bath/gravity 7z transferer**:

User clue (2026-05-16): "李杨 sent JAMSTEC bath+gravity; bath includes
KR06-03, gravity includes KM17-02." Fingerprint hits (verified by
direct 7z listing):

- `KR06-03_bathymetry_dmo.zip` found in
  `jamstec/archive/source_zips/bathymetry.7z` (internal mtime
  2024-04-11 09:30:52).
- `KM17-02_gravity.zip` found in
  `jamstec/archive/source_zips/gravity.7z` (internal mtime 2024-04-10
  17:05:52).
- `jamstec/gravity_data/` (954 zips) ≡ byte-identical unpack of
  `gravity.7z` (954 internal zips; per-file diff of
  `KM17-02_gravity.zip` empty).
- `jamstec/archive/bathymetry_data/` (776 zips) ≡ byte-identical
  unpack of `bathymetry.7z` (`KR06-03_bathymetry_dmo.zip` present in
  both).

→ Resolves all 4 previously-"unknown" JAMSTEC transfer-chain rows.

**Finding B — 李杨 as ncei `.nc` archive content converter**:

5/5 spot-checked `.nc` files in `ncei/tracklines_nc/` carry global
attributes:
```
Author: liyang
history: Wed Jul 31 [HH:MM:SS] 2024  [liyang] Conversion from MGD77 ASCII to MGD77+ netCDF format
```

→ The entire 2,018-file archive is 李杨's local MGD77 ASCII →
MGD77+ NetCDF conversion (2024-07-31). Transfer chain confirmed by
user 2026-05-16: 李杨 (conversion) → 孙明智 (forwarding, late 2024)
→ user.

### Decision audit (re-walk of Locked #1–#10 + proposed #11)

| # | Decision (shorthand) | Still correct? | Reasoning |
|---|---|---|---|
| 1 | `NCEI_multibeam/` → `jamstec/` | Yes | Naming based on confirmed-JAMSTEC content origin; 李杨 finding is transfer-side only, doesn't touch content attribution. |
| 2 | `NCEI_singlebeam/` → `ncei/` | Yes | NCEI content origin unchanged; 李杨 = conversion artifact author, not content origin. NCEI MGD77 ASCII source is confirmed via codex investigation. |
| 2a | NCEI internal layout = B1 | Yes | Unaffected. |
| 3 | `total_tracklines_xyz.zip` → `ncei/tracklines_xyz/` | Yes | Unaffected (安德超 transfer chain unchanged). |
| 4 | Pipeline does sb/mb split, not filesystem | Yes | Unaffected. |
| 5 | `M.rar` → `ncei/archive/zhoushuai_processed_M/` | Yes | Unaffected. |
| 6 | `M.rar` = "processed NCEI multibeam, regional" | Yes | Unaffected. |
| 7 | Cleaning step required for M.rar | Yes | Unaffected. |
| 8 | Union strategy for xyz + nc: 168 nc-only tracks retained | Yes | Unaffected. The 168-track basename diff is between two NCEI snapshots, orthogonal to who converted/transferred the .nc archive. |
| 9 | `JAMSTEC/` absorbed into `jamstec/` in PR-A | Yes | Already executed; transfer-side findings don't touch path layout. |
| 10 | NCEI .nc dual-consumed across `ship/` and `gravity/` projects | Yes, **sharpened** | Both byte-identical copies carry 李杨's conversion product (5/5 spot-check applies to both via SHA256 byte-identity). Original "two projects, one source" framing intact; refined wording is "two projects, one source archive, one conversion artifact (李杨's 2024-07-31 NetCDF re-encoding)". |
| **11** (proposed) | **李杨 (2024-07-31 MGD77 ASCII→NetCDF conversion + JAMSTEC bath/gravity 7z transfer) is the primary external contributor for the .nc + .7z archives; 孙明智 = forwarder for .nc + own-work provider for singlebeam.xyz; 郭恒洋 = independent JAMSTEC transferer with different 2024-07-24 repackaging.** | **✅ confirmed 2026-05-16** | Fingerprint evidence (KR06-03 / KM17-02 in 7z's + `Author: liyang` in 5/5 .nc spot check) + user confirmation 2026-05-16. Supersedes the high-confidence inferences in prior decision/footer narratives. |

**Promoted 2026-05-16 to canonical Locked decisions table (#11).**

### Downstream-impact audit (PR-D through PR-G)

**Expected outcome: no algorithmic change.** Re-walked each pending PR:

- **PR-D (shared lib + R2 classifier)**: Unaffected. The R2 thresholds
  (bbox<5,000 km² OR density>50 pts/km²) operate on per-file point
  geometry, which is independent of who packaged or converted the
  files. The 12 confirmed-mb test fixtures from `tracklines_xyz/` are
  still the calibration anchor.
- **PR-E (singlebeam pipeline build)**: Unaffected. Step 02 NetCDF
  reader is the only real rewrite; `netCDF4.Dataset` reads MGD77+
  NetCDF identically regardless of who performed the ASCII → NetCDF
  conversion. No behavior change from knowing the conversion author.
- **PR-F (M.rar cleaning)**: Unaffected. 周帅 transfer chain
  unchanged; M.rar content is regional processed mb, untouched by
  this finding.
- **PR-G (verification + docs)**: **Provenance documentation updated
  in this same session** (PRD + 5 SOURCE.md sidecars + attribution
  doc footer). Spec refresh and CLAUDE.md/MEMORY.md audit will pick
  up the 李杨-as-conversion-author framing naturally as part of PR-G's
  scope.

→ **No code, no pipeline, no algorithm changes triggered by 李杨
finding chain.** Provenance refinement only.

### Where this finding is recorded

- This PRD section (canonical).
- `jamstec/SOURCE.md` — rewritten transfer-chain section.
- `ncei/SOURCE.md` — newly created top-level summary.
- `ncei/tracklines_nc/SOURCE.md` — rewritten Provenance section.
- `ncei/archive/sunmingzhi_singlebeam_xyz/SOURCE.md` — sharpened
  Transfer-chain-scope bullet.
- `ncei/archive/source_zips/SOURCE.md` — updated `.nc`-zip
  transfer-chain table row.
- `docs/experiments/2026-05_dataset-source-attribution.md` — appended
  "Footer 2026-05-16 (李杨 finding chain)" with both Findings A + B.

## Finding 2026-05-19: 168 nc-only tracks have no usable depth (Q7 resolved)

Resolves the "known unknown" in PRD Q7 (lines 182-194 above) — the
reason the 168 nc-only tracks are absent from the new `tracklines_xyz/`
bundle.

### Evidence

The full PR-E1 trackline source manifest (`ncei/manifests/trackline_source_manifest.parquet`,
7,400 rows) was cross-tabbed on `(depth_sign_raw, source_completeness)`
2026-05-19:

```
                       nc_only  nc_xyz_intersect
all_zero                    33                 0
mostly_positive              0              1850
no_depth_values            135                 0
```

→ All 168 nc-only tracks (33 `all_zero` + 135 `no_depth_values`) have
**no usable depth values**. The 1,850 `nc_xyz_intersect` tracks are
all `mostly_positive` (real bathymetry). 5/5 random nc-only samples
spot-checked (`66010`, `70002`, `72036`, `88006311`, `89001611`): all
have `has_depth=False, has_faa=True` — they are FAA / gravity-only
tracklines.

### Conclusion

NCEI's upstream `.xyz` export pipeline filter rule is "track has
usable depth"; the 168 nc-only tracks were **correctly excluded**
from the xyz bundle by that rule, not lost to a bug or snapshot
drift. The previous "snapshot drift / upstream-filter variance"
framing (in the 2026-05-16 corpora-relationship finding, around the
"168 nc-only basenames" row of the locked-decision audit table) was
right in spirit — now we know the exact filter rule.

This finding sharpens Locked decision #8 (union strategy for xyz +
nc) but does not change it: the 168 tracks remain in the manifest
with `source_completeness="nc_only"` for completeness; the union
still holds.

### Downstream implication for PR-E2

PR-E2 (`02_standardize_singlebeam.py`) consumes the manifest and
standardizes bathymetry. The 168 nc-only tracks have no depth to
standardize and should be skipped at the standardization step —
they're "no_bathymetry" tracks for bathymetry purposes.

- Manifest values **not changed in PR-E1 dispatch** (out of scope):
  `instrument_class_pred="singlebeam"` is technically misleading for
  the 168 (they are neither sb nor mb sonar at all — they are
  gravity-only), but the routing decision belongs to PR-E2 (and to
  future gravity-side consumers of the same `.nc` archive — see
  Locked decision #10 dual-consumption).
- PR-E2 routing rule (recorded here for handoff): filter manifest on
  `has_depth=True AND depth_sign_raw IN ('mostly_positive', 'mostly_negative')`
  before generating bathymetry point tables. Tracks with
  `has_depth=False` or `depth_sign_raw IN ('all_zero', 'no_depth_values')`
  are skipped from bathymetry standardization but remain in the
  manifest as audit trail (and as candidates for the parallel gravity
  pipeline).

### Where this finding is recorded

- This PRD section (canonical).
- `ncei/SOURCE.md` — short pointer back to this finding (no
  duplication of evidence).
- `ncei/tracklines_nc/SOURCE.md` — "168 nc-only" framing annotated
  with `[2026-05-19 update]` resolution.
- `ncei/tracklines_xyz/SOURCE.md` — known-unknown row updated with
  `[2026-05-19 update — resolved]` annotation pointing back here.

## Finding 2026-05-19b: depth sentinel pollution in nc + xyz (PR-F clip)

Identified as part of PR-F audit pass: 16 distinct tracks across the
nc + xyz corpora carry `depth_max` values past the Mariana Trench
(~10,994 m). These are not real bathymetry — they are sentinel /
unit-error pollution from upstream.

### Evidence

Cross-check on the PR-E2 (`singlebeam_points_raw_manifest.parquet`)
+ PR-E3 (`xyz_points_raw_manifest.parquet`) manifests, depth_max
filter > 11,500 m (= ~5% past Challenger Deep, symmetric with PRD Q3
M.rar lower-bound clip):

**3 nc-sb tracks**:

| track_id | depth_max (m) |
|---|---:|
| `91039` | 18,640 |
| `so16`  | 14,450 |
| `so49`  | 12,386 |

**13 xyz tracks** (all `instrument_class_pred=singlebeam`; worst
first):

| track_id | depth_max (m) |
|---|---:|
| `ant4`     | 87,178 |
| `wi343802` | 75,000 |
| `ant8`     | 52,002 |
| `so36`     | 44,215 |
| `so16`     | 27,760 |
| `91039`    | 23,233 |
| `so49`     | 12,386 |
| `rr1108`   | 11,966 |
| `rr1112`   | 11,960 |
| `rr1106`   | 11,928 |
| `rr1110`   | 11,923 |
| `mv0902`   | 11,752 |
| `rr1109`   | 11,707 |

The `91039`, `so16`, `so49` tracks appear in **both** nc and xyz with
the same sentinels — genuine upstream pollution, not a format-specific
artifact. The `rr11xx` + `mv0902` cluster sits just over the cutoff
(11,700–11,966 m); they may be the borderline cases where the cutoff
choice (11,500 vs 12,000) matters most. Worst offenders (ant4 at
87,000 m, wi343802 at 75,000 m, ant8 at 52,000 m, so36 at 44,000 m)
are obvious sentinels / unit errors regardless of cutoff choice.

### Policy — universal depth clip (PR-F)

`02_standardize_singlebeam.py` and `03_standardize_xyz.py` apply the
same upper-bound clip: `depth_m_positive_down > 11,500 m → NaN`. The
raw `depth_raw` column is preserved verbatim in the per-track parquet
for audit; only `depth_m_positive_down` + `elev_m` are NaN'd for
over-clip rows.

Threshold symmetry with PRD Q3 M.rar cleaning lower-bound
(`depth < -11,500 m → nodata`): both ends of the depth axis treat
"5% past Challenger Deep" as the boundary between observation and
sentinel. Promoted to spec via
`pipeline-design-decisions.md` decision #12.

Per-track clip counts are added to the aggregate manifests via a new
`n_clipped` column (int) in both `singlebeam_points_raw_manifest.parquet`
and `xyz_points_raw_manifest.parquet`.

### Where this finding is recorded

- This PRD section (canonical).
- `ncei/SOURCE.md` — pointer to this finding.
- `ncei/tracklines_xyz/SOURCE.md` — "Depth sentinel" subsection
  enumerating the 13 xyz anomalous tracks + the PR-F clip policy.
- `.trellis/spec/backend/pipeline-design-decisions.md` — new
  decision #12 (universal depth clip ±11,500 m).

## Finding 2026-05-19c: nc/xyz intersect asymmetry (xyz is decimated, not equivalent)

Refines the 2026-05-16 "ncei/ corpora relationship clarification"
finding above. The "14k pts/track" parity claim is correct at the
**global aggregate** level (28.9M nc / 2,018 ≈ 14,319; 75M sb-portion
xyz / 5,370 ≈ 14,000 after stripping the 12 confirmed-mb files) but
**not** at the **intersect-track** level — for the 1,850
`nc_xyz_intersect` tracks, the nc side carries more points than the
xyz side, often by an order of magnitude.

### Evidence

PR-E2 / PR-E3 manifests joined on `track_id`, restricted to the 1,850
intersect basenames (`source_completeness == 'nc_xyz_intersect'`):

| Metric | Value |
|---|---:|
| Intersect tracks | 1,850 |
| nc total points (intersect rows) | 35,841,758 |
| xyz total points (intersect rows) | 24,304,908 |
| Median `n_nc / n_xyz` ratio | 1.37 |
| Tracks with `n_nc ≥ 10 × n_xyz` | 39 |
| Tracks with `n_nc ≥ 100 × n_xyz` | 3 |

**Top 10 by nc/xyz ratio (nc much bigger)**:

| track_id | n_nc | n_xyz | ratio |
|---|---:|---:|---:|
| `kea09-69`   | 4,915  | 26    | 189.0 |
| `lprs05rr`   | 35,797 | 261   | 137.2 |
| `64018`      | 11,639 | 113   | 103.0 |
| `cook13mv`   | 11,114 | 113   | 98.4  |
| `jare32l7`   | 22,811 | 251   | 90.9  |
| `64027`      | 7,926  | 137   | 57.9  |
| `ba73014`    | 34,022 | 629   | 54.1  |
| `gh7801`     | 12,381 | 285   | 43.4  |
| `kea01-69`   | 10,965 | 268   | 40.9  |
| `f-10-89-cp` | 53,637 | 1,413 | 38.0  |

**Bottom 10 by nc/xyz ratio (xyz ≥ nc)** — note the off-by-one
pattern `n_xyz = n_nc + 1` is consistent across all bottom-10
cases, suggesting an extra header row in xyz that the chunked reader
treats as data:

| track_id | n_nc | n_xyz | ratio |
|---|---:|---:|---:|
| `ht93t331` | 86   | 87   | 0.989 |
| `ht890713` | 130  | 131  | 0.992 |
| `cmappi6e` | 148  | 149  | 0.993 |
| `cmappi7w` | 222  | 223  | 0.996 |
| `egrbgs1`  | 317  | 318  | 0.997 |
| `avo64may` | 436  | 437  | 0.998 |
| `ht8510`   | 534  | 535  | 0.998 |
| `ht97t374` | 677  | 678  | 0.999 |
| `aku23`    | 940  | 941  | 0.999 |
| `kh7003`   | 1,176| 1,177| 0.999 |

### Implication

The previous "different packaging of same point cloud" framing
(2026-05-16 corpora-relationship finding) is correct in spirit but
incomplete in detail:

- At the **global aggregate** level: both corpora average ~14k
  pts/track for clean singlebeam → same underlying physical corpus.
- At the **intersect-track** level: xyz is generally a
  **decimated / filtered** version of nc. The 100×-ratio outliers
  show xyz can be dramatically lossier; the median 1.37× ratio
  shows even typical tracks lose ~25% of their points in xyz form.

The xyz bundle is therefore best understood as a downstream / decimated
re-export of an upstream NCEI snapshot, **not** as a parallel
independent snapshot. The 14k/track aggregate parity holds because xyz
adds the previously-unfiltered multibeam swaths (the 12 confirmed mb
files) and ~3,532 nc-absent tracks that net out the per-track
shrinkage on the 1,850 intersect set.

### Downstream policy

For `nc_xyz_intersect` tracks, **prefer the nc side** as the primary
bathymetry source in downstream aggregation:

1. nc has more points (median 1.37×; up to 189× in the long tail).
2. nc has standardized MGD77+ columns (`time`, `gobs`, `faa`) that
   bare xyz lacks.
3. nc is mb-filtered upstream → cleaner input that doesn't depend
   on the R2 classifier being perfect.

xyz on the intersect set remains supplementary (not deleted) — kept
in `ncei/derived/singlebeam/points_raw/<track_id>__xyz.parquet` for
audit / sensitivity analysis. This is a knowledge update; **no PR-F
code change** is needed to enforce the rule. Downstream Step 03+
aggregation (a future PR — out of PR-F scope) will operationalize the
preference via a `source_priority` or `bathymetry_eligible` column
on the manifest side, or a per-cell join policy.

### Where this finding is recorded

- This PRD section (canonical).
- `ncei/SOURCE.md` — pointer to this finding.

## Research References

(Both linked from the broader 2026-05_tmp-data-classification.md
investigation doc. No external research persisted under `research/`
yet — sufficient evidence already exists inline in the experiments
doc + this PRD's Q&A trail.)
