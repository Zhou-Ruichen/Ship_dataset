# Project Layout

Use the repository's existing documented layout first. This template gives a
minimal research layout for new projects, not a migration mandate for existing
ones.

## Recommended Layout For New Research Projects

```text
project/
  README.md
  configs/
  data/
    raw/
    interim/
    processed/
    external/
    manifests/
  src/ or lib/
  scripts/
  notebooks/
  tests/
  outputs/
  reports/
```

Use `src/` when the project has importable code. Use `lib/`, `R/`, `matlab/`,
`julia/`, `notebooks/`, or another established project-specific source area
when that is the natural convention for the language or existing repository.

## Directory Contracts

| Path | Contract |
| --- | --- |
| `configs/` | Optional. Parameters, run settings, paths, and feature switches when the project needs config files. |
| `data/raw/` | Immutable project-local raw inputs, symlinks, small samples, or pointers to external data. |
| `data/interim/` | Intermediate outputs from data processing. Rebuildable. |
| `data/processed/` | Durable processed data products. Rebuildable and manifest-backed. |
| `data/external/` | Read-only external datasets or symlinks when project-local pointers are useful. |
| `data/manifests/` | JSON/YAML records for source, version, checksum, processing parameters, and split definitions. |
| `src/`, `lib/`, or project source area | Reusable code. Keep business logic out of copied scripts and notebooks. |
| `scripts/` | Thin command entrypoints for repeatable tasks. |
| `notebooks/` | Exploration, inspection, and narrative analysis. Stable code moves to the source area. |
| `tests/` | Smoke tests, data-contract tests, regression checks, and small unit tests. |
| `outputs/<run_id>/` | Retained run artifacts: manifest, config snapshot or command record, metrics, logs, figures, tables, products. |
| `outputs/scratch/<run_id>/` | Disposable scratch or smoke outputs that are not used as result evidence. |
| `reports/` | Curated figures, tables, and summaries intended for human review or publication. |

## Naming Rules

- Use lower-case ASCII paths with underscores where practical.
- Prefer action-object names: `build_dataset.py`, `run_simulation.R`,
  `evaluate_results.jl`.
- Do not use dates as normal source-code versioning.
- Do not use `v2`, `final`, `new`, or backup suffixes for source files.

Bad:

```text
analysis_final.py
run_simulation_v2.R
output/
outputs/
backup_20260610/
```

Good:

```text
scripts/run_simulation.py
configs/sensitivity.yaml
outputs/20260610-142233-sensitivity/
reports/sensitivity_summary.md
```

## Output Rule

Use `outputs/`, not both `output/` and `outputs/`.

Retained `outputs/<run_id>/` directories should contain enough evidence to
rebuild or audit the result:

```text
manifest.json
metrics.json
environment.freeze.txt
config.yaml or command.txt
logs/
figures/
tables/
products/
```

Scratch and smoke outputs may be lighter and may live under
`outputs/scratch/<run_id>/`. Promote them into a retained `outputs/<run_id>/`
directory before using them in a comparison, report, or result claim.

## Git Rule

Large or generated artifacts should normally be ignored:

```gitignore
data/raw/
data/interim/
data/processed/
data/external/
outputs/
*.nc
*.npz
*.tif
*.tiff
*.parquet
*.h5
*.hdf5
```

Commit `data/manifests/`, small fixtures, code, configs, tests, and curated
`reports/` artifacts when they are intentionally part of the project record.
