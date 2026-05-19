# SOURCE — `ncei/tracklines_nc/`

> Per-track NetCDF (MGD77+) singlebeam archive — canonical upstream input
> for the NCEI singlebeam pipeline.

## Provenance

Three separable concerns here — keep them distinct:

- **Content origin** (factual): NCEI MGD77 ASCII source data. Cruise
  filenames carry NGDC trackline IDs (e.g. `70002`, `64018`, `csio02rr`).
  The data values match the NCEI public singlebeam track archive — an
  earlier codex investigation (`~/.codex/ncei_singlebeam_README.md`)
  established **content-value equivalence** against the NCEI archive.
  That conclusion stands.
- **Conversion** (new 2026-05-16 finding): All 2,018 `.nc` files in
  this dir are **李杨's local MGD77 ASCII → MGD77+ NetCDF conversion**,
  performed **2024-07-31**. Every NetCDF file carries global attributes
  matching this pattern (5/5 spot-checked files identical structure):
  ```
  Author: liyang
  title: Cruise XXXX (NGDC ID XXXX)
  history: Wed Jul 31 [HH:MM:SS] 2024  [liyang] Conversion from MGD77 ASCII to MGD77+ netCDF format
  ```
  The archive is therefore **李杨's conversion artifact**, NOT a download
  of NCEI's official NetCDF distribution. The earlier codex-notes
  framing — that the files "matched against the NCEI singlebeam track
  archive" — was about content-value matching against the NCEI MGD77
  source data, which remains correct. It did NOT establish that the
  `.nc` files themselves came directly from NCEI; the new attribute
  evidence shows they were locally re-encoded by 李杨.
- **Transfer chain** (user confirmed 2026-05-16):
  **李杨 (2024-07-31 NetCDF conversion) → 孙明智 (forwarding, late 2024) → user**.
  孙明智's role here is forwarder only — the conversion product is
  李杨's. This supersedes the earlier high-confidence-inference framing
  that named 孙明智 as the primary source-side counterparty.
- **Source archive**: `NCEI_singlebeam_tracks_raw_2018files.zip` (463 MB).
  Originally lived at `/mnt/data2/00-Data/`; relocated 2026-05-16
  to `ncei/archive/source_zips/` as part of PR-C. Byte-identical
  duplicate at `/mnt/data2/00-Data/gravity/NCEI/archive/NCEI.zip`
  is kept by design (Locked decision #10 — two sibling projects share
  one source).
- **Pre-PR-C inspection residue**: `/mnt/data2/00-Data/tmp/70002.nc`
  is byte-identical to `ncei/tracklines_nc/70002.nc` (pre-PR-C
  inspection copy). User-decision-locked; not in scope for cleanup.

## Contents

- **2,018 `.nc` files** (one per track) — MGD77+ NetCDF format with
  standard variables: `time`, `lon`, `lat`, `depth`, `gobs` (observed
  gravity), `faa` (free-air anomaly). Spot-check: `csio02rr.nc` reads
  cleanly via `netCDF4`, 9,783 records, no corruption.
- **2 `.txt` sidecars** (~18 MB total, ignored by gitignore):
  - `NCEI_Ara1.txt` — tab-separated `lon, lat, depth, time?` rows.
  - `validation_results.txt` — tab-separated `lon, lat, residual` rows
    (depth values look like validation residuals, not raw depths).
  Provenance of these two sidecars not confirmed; they ship inside the
  upstream zip but are not part of the per-track corpus. Treat as
  reference artifacts, not pipeline inputs.
- **Total payload**: 1.1 GB unpacked.

Original zip layout wrapped everything under `NCEI/`; PR-C flattens
that wrapper so the .nc files are immediate children of
`ncei/tracklines_nc/`.

## File-count reconciliation

| Reported count | Source | What it counts |
|---:|---|---|
| 2,018 | task.json / PRD claim | `.nc` files (canonical) |
| 2,021 | `unzip -l` header | all entries (incl. 1 wrapping dir + 2 .txt sidecars) |
| 2,019 + 2 | Q6 evidence (2026-05-15) | `.nc` + `.txt` files in archive (2,019 was a miscount; actual = 2,018 + 2) |

→ Definitive count after extraction: **2,018 `.nc` files + 2 `.txt`
sidecars = 2,020 regular files** (plus the wrapping `NCEI/` dir entry
the zip header includes). The "3-file discrepancy" flagged in PRD Q6
resolves cleanly: 2,018 .nc is correct; the +3 was the wrapper dir +
the 2 .txt sidecars.

## Dual content (bathymetry + gravity)

20-file random sample (seed=1) drawn 2026-05-16, 433,127 total records:

| Field | Meaning | Non-null records | Non-null % | Files with any data |
|---|---|---:|---:|---:|
| `depth` | bathymetry | 278,726 | **64.4%** | 20/20 |
| `gobs` | gravity observation | 236,685 | **54.6%** | 12/20 |
| `faa` | free-air anomaly | 423,931 | **97.9%** | 20/20 |

The MGD77+ NetCDF format stores **sensor measurements interleaved
along each cruise's time series**: depth and gravity sensors may
sample different sub-intervals of the same trackline, so per-record
non-null counts vary by sensor. An earlier 1-file spot check
(`64018.nc`, ~1% depth non-null) was a per-file outlier, not the
corpus norm — the 20-file random sample establishes the actual
composition. **This corpus is a legitimate dual-purpose source:
bathymetry for `ship/` pipelines, gravity for parallel gravity
projects.**

### Byte-identical duplicate in the gravity tree

The same archive is also present at
`/mnt/data2/00-Data/gravity/NCEI/archive/NCEI.zip` (463 MB,
SHA256 `1a9b2c5b7e72f1ca1d17b0f1b7172186ebf56be1ebde67113ad8978a48514eed`
— byte-identical to
`ncei/archive/source_zips/NCEI_singlebeam_tracks_raw_2018files.zip`).

**User decision 2026-05-16**: keep both copies; do not dedupe. The
bath project (this `ship/` tree) consumes the archive via the
`depth` field; the gravity project (`/mnt/data2/00-Data/gravity/`)
consumes the **same bytes** via the `gobs` / `faa` fields. Each
project owns its consumer-side copy where its pipelines expect it.
Two projects, one source. (This is the rationale behind the new
Locked decision #10 in the task PRD.)

The bath singlebeam pipeline (planned PR-E of task
`05-11-singlebeam-integration`) consumes **only** the `depth` field;
future gravity pipelines can reuse this same archive via
`gobs` / `faa` without re-downloading from NCEI.

## Known unknowns

1. **168 tracks present in `tracklines_nc/` but absent from the new
   `tracklines_xyz/` bundle** (PRD Q7). Reason for upstream omission is
   unknown. Spot-check (2026-05-15) of 5 random nc-only basenames
   (`csio02rr`, `sho08-69`, `l1077bs`, `kea03-69`, `wn7907`) found typical
   singlebeam sizes (87–282 KB) and clean NetCDF content — no
   corruption, no multibeam signature.
   - **Treatment**: ingest as normal singlebeam. Pipeline manifest
     gains `source_completeness ∈ {nc_only, nc_xyz_intersect, xyz_only}`
     for downstream auditability.
   - **[2026-05-19 update — resolved]**: The full PR-E1 trackline
     source manifest reveals all 168 nc-only tracks have `has_depth=False`
     (33 `all_zero` + 135 `no_depth_values` rows in the
     `depth_sign_raw × source_completeness` cross-tab). 5/5 new random
     samples (`66010`, `70002`, `72036`, `88006311`, `89001611`) all
     have `has_depth=False, has_faa=True` — they are **FAA / gravity-only
     tracklines without usable bathymetry**. NCEI's upstream `.xyz`
     export filter rule is "track has usable depth"; the 168 were
     correctly excluded by that rule, not lost to a bug. Union
     strategy unchanged (they stay in the manifest with
     `source_completeness="nc_only"`); PR-E2 bathymetry standardization
     will skip them, but they remain as audit trail and as candidates
     for gravity-side consumers of the same archive (Locked decision
     #10 dual-consumption). Full evidence: PRD section
     "Finding 2026-05-19: 168 nc-only tracks have no usable depth".
     The original 2026-05-15 spot-check finding above (5/5 clean
     singlebeam-sized .nc files) is preserved as historical record —
     "clean NetCDF" was correct; "singlebeam signature" was incidental
     (they happen to have lat/lon/time, just no usable depth values).
2. **Provenance of the 2 .txt sidecars** inside the upstream zip is
   unclear. They are kept on disk for audit (gitignored due to size).

## References

- PRD: `.trellis/tasks/05-11-singlebeam-integration/prd.md` (Q6, Q7,
  Locked decision #8).
- Investigation: `docs/experiments/2026-05_tmp-data-classification.md`
  (basename diff analysis, the 1,850 / 3,532 / 168 split).
- Attribution: `docs/experiments/2026-05_dataset-source-attribution.md`.
