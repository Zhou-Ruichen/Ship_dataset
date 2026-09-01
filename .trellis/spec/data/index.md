# Data Guidelines

Use these rules whenever reading, writing, validating, or transforming data.

The project may keep data under `data/`. The rule is not "no data in repo"; the
rule is "data must have lifecycle, provenance, and rebuild instructions."

## Documentation Files

| File | Read when |
| --- | --- |
| [../shared/project-layout.md](../shared/project-layout.md) | Naming data paths |
| [../shared/reproducibility.md](../shared/reproducibility.md) | Writing manifests and run records |
| [../shared/anti-bloat.md](../shared/anti-bloat.md) | Adding processing scripts or variants |

## Data Layout

```text
data/
  raw/
  external/
  interim/
  processed/
  manifests/
```

Use `data/raw/` for immutable local raw inputs or symlinks. Use
`data/external/` for read-only external data roots or symlink targets. Use
`data/interim/` for temporary but rebuildable products. Use `data/processed/`
for durable processed products.

Existing projects may use different names. Map these lifecycle concepts onto
the existing structure instead of renaming directories without a migration
task.

## Source Rule

External or shared data sources are read-only by default. Project code writes
to project-local `data/interim/`, `data/processed/`, or `outputs/<run_id>/`.
Writing back into a shared source requires an explicit data-processing task and
a manifest.

## Manifest Rule

Every durable data product needs a manifest in `data/manifests/`.

Required fields:

```json
{
  "name": "processed_dataset_v1",
  "created_at": "2026-06-10T14:22:33Z",
  "created_by": "python scripts/build_dataset.py --config configs/data.yaml",
  "source_paths": [],
  "source_versions": {},
  "processing_config": "configs/data.yaml",
  "output_paths": [],
  "checksums": {},
  "schema": null,
  "split_policy": null,
  "assumptions": []
}
```

Do not invent unavailable fields. Use `null`, an empty list, or a clear
assumption only when the value is truly unknown.

## Boundary Validation

Validate at the point where data enters the project:

- file exists and format is expected;
- schema, columns, variables, or record layout are known;
- units and coordinate conventions are explicit when relevant;
- shapes, dimensions, and dtypes match expectations;
- missing values, NaN, fill values, or sentinel values are handled explicitly;
- train/validation/test splits cannot leak entities, time ranges, regions,
  subjects, or source records when leakage matters.

## Scientific Data Formats

These rules are checkable and apply whenever durable data carries physical or
structured meaning. They are language-agnostic; the format may be CSV, Parquet,
HDF5, netCDF, JSON, or any project convention.

- Record units and the coordinate or key convention for every physical field at
  the boundary. A column named `temperature` without a unit is not a complete
  record.
- Handle missing-value sentinels, fill values, and NaN explicitly: state the
  convention and never let an unconverted sentinel reach a computation.
- Record a checksum only when exact byte identity affects transfer integrity,
  deduplication, or reproduction. Otherwise record the source, upstream
  version or retrieval date, expected size or record count, and schema needed
  to identify the data.
- For data too large to version in the repository, store a reproducible pointer
  (root path or config key, protocol, upstream version or retrieval date)
  instead of the bytes, and record the resolution rule.
- For binary or self-describing formats (HDF5, netCDF, Parquet), record the
  library and version used to read or write, and any compression or encoding
  options that affect how the data is reconstructed.

## Data Processing Entrypoints

Use one stable entrypoint per durable processing stage:

```text
scripts/build_dataset.py
scripts/validate_dataset.py
scripts/export_product.py
```

Do not create:

```text
scripts/build_dataset_v2.py
scripts/build_dataset_final.py
scripts/1_make_data.py
scripts/2_fix_data.py
```

If the stage changes, update parameters and manifest, not the script name.

## Quality Check

- [ ] Durable data output has a manifest.
- [ ] Splits or comparison groups are recorded and leakage-checked when
      relevant.
- [ ] Data paths are parameterized or documented, not hardcoded workstation
      paths.
- [ ] Missing values, units, schema, and conventions are explicit.
- [ ] Physical fields carry units; fill-value and sentinel handling is explicit.
- [ ] Durable data has the source/version metadata needed to identify it;
      checksums are present only when exact byte identity matters.
- [ ] Large external data is a reproducible pointer, not committed bytes.
- [ ] Large generated data is ignored by git unless the user explicitly
      chooses to version a small fixture.
