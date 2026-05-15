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

## References

- PRD: `.trellis/tasks/05-11-singlebeam-integration/prd.md`
  (Locked decision #2a — `archive/sunmingzhi_singlebeam_xyz/`).
- Investigation: `docs/experiments/2026-05_tmp-data-classification.md`
  ("Cross-cutting finding" — naming + flattening note).
- Attribution: `docs/experiments/2026-05_dataset-source-attribution.md`
  ("Singlebeam reuse note" — explains why per-track .nc archive is
  preferred over this flat dump).
