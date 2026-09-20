# Data Guidelines

Keep external or shared sources read-only by default. Write temporary or
rebuildable products to the project's existing interim or output location;
the evidence a retained output keeps is defined in
[reproducibility.md](../shared/reproducibility.md). Do not rename an
existing layout to match the raw, interim, processed, and output concepts.

For data too large to version, record a reproducible pointer: configured
root or access URL, upstream version or retrieval date, resolution rule, and
the variables or extent consumed. Use a checksum only when exact byte
identity affects transfer integrity, deduplication, or reproduction.

## Checks at the data boundary

Check once, where data enters the analysis, only conditions whose failure
could silently change the scientific result:

- units, coordinate reference and key conventions, shapes, dimensions, and
  dtypes;
- missing values, NaN, fill values, and sentinel conversion;
- split or join rules and leakage across entities, subjects, groups, time,
  regions, or records, including through labels or augmentation;
- variable or label meanings, filtering, interpolation, resampling,
  masking, and augmentation parameters.

Let the data library report missing files, unsupported formats, malformed
syntax, and ordinary I/O errors; no generic validator or preflight
checklist.

## Format details

For netCDF, Zarr, HDF5, Parquet, JSON, or similar structured data, record
the fields consumed and metadata needed to interpret them; preserve units
and coordinate conventions for physical fields, and note fill-value handling
and encoding or chunking only when they affect the computation. For
geospatial data, record CRS, longitude convention, grid definition, and
reprojection or resampling parameters when used. For time series, record
time encoding, timezone, aggregation, and join tolerance when relevant.
