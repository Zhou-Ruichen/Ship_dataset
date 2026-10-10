# Data Guidelines

Keep external or shared sources read-only by default. Write temporary or
rebuildable products to the project's existing interim or output location.
Keep only the source pointer and facts needed to rerun a reported result.
Keep existing names and adapt the pointers to the project's layout.

For data too large to version, record a pointer and the upstream version or
retrieval date. Add the variables, extent, resolution, or checksum when
they affect the reported result or its reproduction.

## Checks when data are read

Inspect the units, split, labels, missing-value handling, or other input fact
when getting it wrong could silently change the result. Let the data
library report missing files, unsupported formats, malformed syntax, and
ordinary I/O errors.

## Format details

For structured, geospatial, or time-series data, record a field, coordinate,
time, or encoding detail when it affects the calculation.
