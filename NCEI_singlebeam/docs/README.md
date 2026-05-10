# NCEI Singlebeam Data Notes

## Scope

This directory contains a merged singlebeam bathymetry point cloud:

- `singlebeam.xyz`: aggregated `lon lat depth` text file

Related upstream raw archive stored under:

- `/mnt/data2/00-Data/NCEI_singlebeam_tracks_raw_2018files.zip`

## Confirmed Relationship

The raw archive is not just an unrelated download. Sampled tracks from the zip were matched directly against `singlebeam.xyz`.

Confirmed spot checks:

- `64018.nc` in the zip contains unpacked points such as `-63.3239 44.3989 76.8` and `-63.3202 44.3964 76.8`
- These points appear in `singlebeam.xyz` as:
  - `-63.3239 44.3989 -76.8`
  - `-63.3202 44.3964 -76.8`
- `m14.nc` in the zip contains an unpacked point `-17.56267 -13.50449 4170`
- This point appears in `singlebeam.xyz` as `-17.56267 -13.50449 -4170`

Practical interpretation:

- `singlebeam.xyz` includes data from this raw zip
- The conversion rule is consistent with:
  - `lon` copied directly
  - `lat` copied directly
  - `depth` sign flipped from positive-down to negative-downstream-convention

## What Is Still Unconfirmed

The current directory does not contain a build script or manifest for `singlebeam.xyz`, so the following are still unknown:

- whether `singlebeam.xyz` was built from all 2018 tracks in the zip
- whether additional raw sources were merged into `singlebeam.xyz`
- whether any quality filtering, deduplication, or thinning was applied before export

## Format Notes

Raw zip contents:

- MGD77+ style per-cruise netCDF tracks (`*.nc`)
- variables include `lon`, `lat`, `depth`, and sometimes gravity-related variables

Merged output:

- plain text XYZ
- three columns: `lon lat depth`
- example row: `123.6483 9.521 -713`

## Recommendation

Do not delete `NCEI_singlebeam_tracks_raw_2018files.zip` unless a reproducible build path for `singlebeam.xyz` is documented elsewhere.
