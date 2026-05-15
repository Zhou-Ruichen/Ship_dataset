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

**PR-D — Shared lib extraction + classifier**
- Factor algorithmic overlap from JAMSTEC pipeline into `_common/`
  (exact structure decided during implementation, not pre-designed).
- Implement R2 classifier as a pipeline stage (post-standardize for
  .nc, post-minimal-parse for .xyz).
- Tests: 12 confirmed-mb xyz files all → mb; sample of clear sb files → sb;
  borderline files produce the (bbox, density) scatter to calibrate.

**PR-E — Singlebeam pipeline build**
- Step `02_standardize_singlebeam` (only real rewrite: NetCDF reader).
- Step 03 / 04a / 04b / 05 / 06a-d / 08 / 09-11 reuse from JAMSTEC mb
  via shared lib.
- Step `07_quality_tiers` reuse but re-calibrate A/B/C thresholds for
  singlebeam point density.
- `source_completeness` manifest column populated in standardize step.

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

## Research References

(Both linked from the broader 2026-05_tmp-data-classification.md
investigation doc. No external research persisted under `research/`
yet — sufficient evidence already exists inline in the experiments
doc + this PRD's Q&A trail.)
