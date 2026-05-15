# SOURCE — `ncei/archive/source_zips/`

> Frozen source archives that were unpacked into the active `ncei/`
> tree (PR-C, 2026-05-16). Kept alongside the unpacked content as
> audit trail; the pipeline never reads from this dir.

## Contents

| File | Size | Unpacked to | Notes |
|---|---:|---|---|
| `NCEI_singlebeam_tracks_raw_2018files.zip` | 463 MB | `ncei/tracklines_nc/` | NCEI per-track .nc archive (2,018 .nc + 2 .txt sidecars). Filename preserved verbatim — it is the upstream-archive name and a load-bearing identifier (see PR-B notes about not rewriting bare `NCEI_singlebeam` strings inside this filename). Pre-PR-C location: `/mnt/data2/00-Data/`. |
| `total_tracklines_xyz.zip` | 854 MB | `ncei/tracklines_xyz/` | NCEI trackline xyz bundle from 安德超 (2026-05-15). 5,382 .xyz files; mixed sb/mb (12 confirmed multibeam). Pre-PR-C location: `/mnt/data2/00-Data/tmp/`. |

The `M.rar` archive lives in its own dir
(`ncei/archive/zhoushuai_processed_M/M.rar`) alongside its extracts, not
here, because M.rar's provenance is bundled with the cleaning workflow
(see that dir's SOURCE.md).

## Transfer chains

The two zips here arrived from different upstream channels — content
origin (both NCEI public archives) is separate from transfer chain
(who actually moved the bytes onto this disk):

| File | Transfer chain | Date window | Confidence |
|---|---|---|---|
| `NCEI_singlebeam_tracks_raw_2018files.zip` | 孙明智 → user | Dec 2024 (file timestamp Dec 18 2024) | high-confidence inference — almost certainly part of the same transfer as `singlebeam.xyz` (now at `ncei/archive/sunmingzhi_singlebeam_xyz/`); user has no memory of a separate direct-from-NCEI download. See `ncei/tracklines_nc/SOURCE.md` for full evidence chain. |
| `total_tracklines_xyz.zip` | 安德超 → user | 2026-05-15 | confirmed (PR-C ingest of this same task). |

The third NCEI-related archive on the user's disk — `M.rar` from 周帅
— is multibeam-side and lives at `ncei/archive/zhoushuai_processed_M/M.rar`,
not in this dir.

## Convention

When PR-C ingested new data into `ncei/`, both source archives that
needed relocation (from `/mnt/data2/00-Data/` and `/mnt/data2/00-Data/tmp/`)
were **moved** into the repo rather than copied. The rule going forward:
upstream archives that are unpacked into the active tree live alongside
their unpacked content (either here or in a topic-specific archive
subdir), so re-extraction stays reproducible from inside the repo.

## References

- PRD: `.trellis/tasks/05-11-singlebeam-integration/prd.md` (PR-C
  execution log).
- Sibling pattern: `jamstec/archive/source_zips/` (same convention,
  established in PR-A).
