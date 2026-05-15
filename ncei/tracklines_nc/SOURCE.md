# SOURCE — `ncei/tracklines_nc/`

> Per-track NetCDF (MGD77+) singlebeam archive — canonical upstream input
> for the NCEI singlebeam pipeline.

## Provenance

- **Origin**: NCEI public singlebeam track archive.
- **Confirmation**: An earlier codex investigation verified the zip
  against the NCEI singlebeam track archive; notes saved at
  `~/.codex/ncei_singlebeam_README.md` (per
  `docs/experiments/2026-05_dataset-source-attribution.md`).
- **Source archive**: `NCEI_singlebeam_tracks_raw_2018files.zip` (463 MB).
  Originally lived at `/mnt/data2/00-Data/`; relocated 2026-05-16
  to `ncei/archive/source_zips/` as part of PR-C.

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
2. **Provenance of the 2 .txt sidecars** inside the upstream zip is
   unclear. They are kept on disk for audit (gitignored due to size).

## References

- PRD: `.trellis/tasks/05-11-singlebeam-integration/prd.md` (Q6, Q7,
  Locked decision #8).
- Investigation: `docs/experiments/2026-05_tmp-data-classification.md`
  (basename diff analysis, the 1,850 / 3,532 / 168 split).
- Attribution: `docs/experiments/2026-05_dataset-source-attribution.md`.
