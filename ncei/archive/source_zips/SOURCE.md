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
