# NCEI archive gap inventory and completion download

mode: data acquisition (network downloads into raw/; existing products untouched)

## Decision this task must answer

How incomplete is our NCEI holding, exactly, and what lands when we complete
the singlebeam part. Evidence first, download second.

## Part 1: gap inventory (do this first, report before mass download)

- Obtain NCEI's full marine trackline survey catalog (the request service at
  https://www.ngdc.noaa.gov/trackline/request/ exposes Survey IDs; the
  ordering API is documented at
  https://www.ngdc.noaa.gov/next-web/docs/guide/ordering.html).
- Diff against `ncei/manifests/trackline_source_manifest.parquet`: which
  surveys/tracks do we lack, by branch (nc / xyz), era, and institution.
- Report the gap table (counts and total estimated size) and get the
  download plan from it; note in the report if the catalog cannot be
  enumerated programmatically and what the fallback is.

## Part 2: singlebeam completion download

- Download the missing singlebeam tracks (MGD77T preferred, XYZ fallback)
  via the ordering API or the HTTPS tree
  (https://data.ngdc.noaa.gov/platforms/ocean/ships/<ship>/<cruise>/).
- Land raw files under `ncei/raw/` following the existing layout
  conventions; do NOT overwrite or modify any existing raw file. New files
  only; name so that round 2 is distinguishable.
- Register every new track in a manifest addition (the round-2 rows) so the
  L1/L2/L3 regeneration (separate task) can pick them up.
- If the total size turns out large (> 50 GB), stop after the inventory and
  report the size before pulling.

## Part 3: multibeam and CSB assessment (no download)

- Multibeam: NCEI MBBDB holds 2,400+ cruises; produce the inventory and an
  estimate of what completion would cost (size, format). No download.
- IHO DCDB CSB point store (API:
  https://github.com/CI-CMG/pointstore-api-docs): assess as a new branch —
  count soundings, check attributes (time, platform, file id), note the
  absence of per-track quality metadata. No bulk download.

## Hard constraints

- Read-only on all existing raw/derived data; new downloads additive only.
- Polite crawling: sequential requests, no aggressive parallelism; respect
  any rate limits; log every downloaded file with its source URL.
- Record the download date and source for every file (provenance).
- Do not start product regeneration (L1->L2->L3 and downstream products are
  follow-up tasks after review).

## Deliverables

1. `ncei/manifests/ncei_catalog_gap_2026-09.parquet` + gap report section.
2. `ncei/raw/` additions (missing singlebeam tracks) + download log
   `ncei/manifests/round2_download_log.parquet` (file, source URL, bytes,
   sha256, downloaded_at).
3. `ncei/docs/step11_archive_gap_report.md`: gap table, what was downloaded,
   multibeam/CSB assessment, recommended follow-ups.

## Acceptance criteria

- The gap is stated in numbers (surveys we lack by branch/era), not
  impressions.
- Every new raw file appears in the download log with provenance.
- No existing file modified (verify by git status on tracked files and by
  mtime spot checks on raw).

## Out of scope

- Raw multibeam bulk download (assessment only this round).
- Product regeneration (pipeline re-run) — separate task.
- GEBCO/GMRT data.
