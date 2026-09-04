# Data Guidelines

Apply these rules when reading, writing, validating, or transforming data.
Keep external or shared sources read-only by default. Write temporary or
rebuildable products to the project's existing interim or output location, and
retain durable products with the source and processing information needed to
rebuild or interpret them.

## Layout and provenance

Map the project's existing directories to these concepts where useful:

- raw or external: immutable local inputs and read-only upstream sources;
- interim: temporary, rebuildable products;
- processed: durable products used by later analysis;
- outputs: run-specific results and evidence.

Do not rename an existing layout just to match these names. For data too large
to version, record a reproducible pointer: configured root or protocol,
upstream version or retrieval date, resolution rule, and the variables or
extent consumed. Use a checksum only when exact byte identity affects transfer
integrity, deduplication, or reproduction.

Record the processing command or notebook, source version, relevant parameters,
and output location for a durable product. An existing processing log or data
note is sufficient; no fixed manifest file or field list is required.

## Checks at the data boundary

Check only conditions whose failure could silently change the scientific result:

- units, coordinate reference and key conventions, shapes, dimensions, and dtypes;
- missing values, NaN, fill values, and sentinel conversion;
- split or join rules and leakage across entities, time, regions, subjects, or records;
- variable meanings, filtering, interpolation, resampling, and masking parameters.

Let the data library report missing files, unsupported formats, malformed syntax,
and ordinary I/O errors. Do not add a generic validator or preflight checklist
for these failures.

## Applicable format details

For netCDF, HDF5, Parquet, JSON, or similar structured data, record the fields
consumed and metadata needed to interpret them. For physical fields, preserve
units and coordinate conventions. For netCDF or Zarr, note fill-value handling
and encoding or chunking only when they affect the computation. For geospatial
data, record CRS, longitude convention, grid definition, and reprojection or
resampling parameters when used. For time series, record time encoding,
timezone, aggregation, and join tolerance when relevant.
