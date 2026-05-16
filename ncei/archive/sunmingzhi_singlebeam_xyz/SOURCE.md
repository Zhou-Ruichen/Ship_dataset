# SOURCE — `ncei/archive/sunmingzhi_singlebeam_xyz/`

> Frozen legacy artifact: flat 3-column dump of NCEI singlebeam data.
> Per-track structure was lost during the original merge — that is why
> the pipeline builds from `tracklines_nc/` (per-track .nc) rather than
> from this dump.

## Provenance

- **Provider**: 孙明智 (legacy hand-off, predates this task).
- **Source file**: `singlebeam.xyz` (3.1 GB, ~114.5M rows).
- **Pre-PR-C location**: `ship/NCEI_singlebeam/singlebeam.xyz` (later
  `ship/ncei/singlebeam.xyz` after PR-B). Moved here 2026-05-16 by
  PR-C; not extracted, not modified — same bytes as the legacy file.
- **Transfer-chain scope** (2026-05-16 sharpening): 孙明智's role
  spans two distinct artifacts with **two distinct origins**:
  - **(a) Forwarder** for 李杨's per-track `.nc` archive now at
    `ncei/tracklines_nc/`. 李杨 performed the
    MGD77 ASCII → MGD77+ NetCDF conversion on 2024-07-31 (NetCDF
    global attrs carry `Author: liyang` + a `Conversion from MGD77
    ASCII to MGD77+ netCDF format` history line in 5/5 spot-checked
    files); 孙明智 transferred the resulting package to user in late
    2024 (file mtime `NCEI_singlebeam_tracks_raw_2018files.zip` =
    Dec 18 2024). The conversion product is 李杨's; 孙明智 is the
    forwarder only.
  - **(b) Provider / own-work** for this flat `singlebeam.xyz`
    merge dump (file mtime Jan 18 2025). Origin of the underlying
    flatten/merge step is not externally documented — possibly
    孙明智's own work, possibly an upstream NCEI snapshot he
    obtained pre-merged. The dirname `sunmingzhi_singlebeam_xyz`
    refers only to **this** artifact — the flat merge — kept as a
    frozen legacy artifact.
  - User confirmation 2026-05-16. This supersedes the earlier
    framing that bundled the .nc archive under 孙明智's name.
    Cross-reference: `ncei/tracklines_nc/SOURCE.md` (李杨 conversion
    section) and the parent `ncei/SOURCE.md` (transfer-chain table).

## Contents

Single file: `singlebeam.xyz` (3,240,996,725 bytes ≈ 3.1 GB).
Format: 3-column flat dump (lon, lat, depth). Row count: 114,507,390
(per investigation doc).

## Why this dir exists (and is `archive/`, not `tracklines_xyz/`)

The original merge that produced `singlebeam.xyz` collapsed all
per-track structure into one flat file — there is no way to recover
per-track partitioning from it. The pipeline therefore builds from the
upstream **per-track .nc archive** instead (`tracklines_nc/`), which
preserves the track structure required for downstream QC, file-balanced
medians, and quality tiering.

This dir keeps the legacy dump on disk as a frozen audit artifact:
re-derivations or cross-checks against the old corpus stay possible,
but no active pipeline reads from here.

## Known unknowns

1. **Origin pipeline** of the original merge is undocumented. The
   relationship between this flat dump and the upstream NCEI per-track
   archive (now `tracklines_nc/`) was not preserved.
2. **No companion sidecars** — provenance summary lives here only.

## Relationship to other NCEI singlebeam corpora (2026-05-16 finding)

Empirical row-count + single-track density measurements (performed
read-only on 2026-05-16, post-PR-C) clarified the upstream relationship
between this flat dump and the two per-track corpora in `ncei/`:

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

This dump is **not** the merged form of `tracklines_nc/`: the
point-count ratio is 114.5M / 28.9M ≈ 4×, which rules out the nc
archive as its source. The numbers are consistent with the dump being
the merged form of an earlier or upstream-filter-variant snapshot of
the `.xyz` family (114.5M vs current `tracklines_xyz/` 123.4M = ~7%
delta, plausibly snapshot drift in the NCEI public archive between
transfers). Provenance of that specific snapshot is not actively
chased — the dump is frozen legacy.

This sharpens but does not invalidate the original PR-C decision: the
file is placed in `archive/` as a frozen legacy artifact and is NOT
routed through the active pipeline. The reason remains correct
regardless of the upstream snapshot — once per-track structure
(track ID, time, MGD77+ ancillary columns) was collapsed by the flat
merge, the file became unusable for the per-track pipeline that
`tracklines_nc/` feeds.

## References

- PRD: `.trellis/tasks/05-11-singlebeam-integration/prd.md`
  (Locked decision #2a — `archive/sunmingzhi_singlebeam_xyz/`;
  "Finding 2026-05-16" section — relationship clarification).
- Investigation: `docs/experiments/2026-05_tmp-data-classification.md`
  ("Cross-cutting finding" — naming + flattening note).
- Attribution: `docs/experiments/2026-05_dataset-source-attribution.md`
  ("Singlebeam reuse note" + 2026-05-16 correction paragraph —
  explains why per-track .nc archive is preferred over this flat dump).
