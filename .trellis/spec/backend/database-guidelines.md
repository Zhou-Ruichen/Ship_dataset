# Storage Guidelines

> This project has **no database**. "Storage" means parquet files,
> manifests, and reports on disk. This file documents the conventions
> for those.
>
> (Filename kept as `database-guidelines.md` because the Trellis
> bootstrap manifest expects it; treat the contents as authoritative.)

---

## Storage tiers

| Tier | Format | Where | Purpose |
|------|--------|-------|---------|
| Raw | `.dat`, `.zip`, `.xyz`, `.nc` | `<dataset>/raw/`, `<dataset>/archive/` | Source; never modified |
| Intermediate | Parquet (per-file) | `<dataset>/derived/<stage>/<file_id>.parquet` | Per-file processing output, sharded |
| Aggregated | Parquet (single file) | `<dataset>/derived/<stage>/cells.parquet` | Global merged products |
| Manifest | Parquet + TSV mirror | `<dataset>/manifests/<name>_manifest.{parquet,tsv}` | Metadata about files / stages |
| Report | Markdown | `<dataset>/docs/<stage>_report.md` | Human-readable summary |
| Config | YAML | `<dataset>/configs/*.yaml` | Run parameters |
| Model | Pickle / NPZ | `<dataset>/derived/<stage>/baselines_*/` | Trained ML baselines (Step 11) |

---

## Parquet conventions

**Use `pyarrow`, not `fastparquet`.** Always.

```python
import pyarrow as pa
import pyarrow.parquet as pq
```

For per-file outputs that may be large (Step 02, Step 03):
- Write **chunked** with `pq.ParquetWriter` to avoid loading the whole
  source `.dat` into memory.
- Default chunk size: 1,000,000 rows (`DEFAULT_CHUNK_SIZE = 1_000_000`).
- One `.parquet` per `file_id`. Filename mapping:
  ```python
  def file_id_to_parquet_name(file_id: str) -> str:
      safe = file_id.replace("::", "__").replace("/", "__")
      if safe.endswith(".dat"):
          safe = safe[:-4]
      return safe + ".parquet"
  ```

For aggregated single-file outputs (Step 04b, Step 06c, Step 07):
- Write a single `cells.parquet` to `derived/<stage>/cells.parquet`.
- Snappy compression is the default; do not change it.

---

## Manifest convention

Every stage that processes per-file inputs MUST produce a manifest:

```
manifests/<name>_manifest.parquet      # canonical
manifests/<name>_manifest.tsv          # mirror, for grep / spreadsheet inspection
```

The TSV mirror is required — it is the developer's primary debugging tool.
Generate both from the same DataFrame.

Manifest schema MUST include:

| Column | Type | Purpose |
|--------|------|---------|
| `file_id` | string | Primary key — same `file_id` used across all stages |
| `<stage>_status` | string | `ok` / `skipped` / `failed` |
| `<stage>_n_rows` | int64 | Output row count |
| `<stage>_path` | string | Path to the per-file output, relative to dataset root |

Plus stage-specific columns. Columns from upstream manifests should be
joined/preserved, not regenerated.

---

## `file_id` is the cross-stage key

All per-file outputs across all stages share the same `file_id` string.
Format:

```
<subzip_name>::<basename>.dat
e.g. "MR03-K02_bathymetry_dmo::20030527.dat"
```

Never:
- Re-derive `file_id` from a filesystem path with different normalization.
- Use the parquet filename (which uses `__`) as a key — only the original
  `file_id` string is canonical.

---

## TSV format (for reports and manifests' mirror)

- Tab-separated, **no quoting**, UTF-8.
- First line is the header.
- Pandas: `df.to_csv(path, sep="\t", index=False)`.
- Use `.tsv` extension, not `.csv` — comma collisions in cruise names
  have bitten us before.

---

## YAML config

- Configs live in `<dataset>/configs/*.yaml`.
- Loaded with `yaml.safe_load`. Never `yaml.load`.
- A script that takes config takes it via `--config <path>`. The script
  must validate required keys explicitly and error out on missing keys.

Example: `NCEI_multibeam/configs/gridded_products_validation.yaml`
declares the 6 gridded-bathymetry products plus their sampling methods —
this is the canonical pattern for new config-driven stages.

---

## What NOT to use

| ❌ | Why |
|---|---|
| SQLite / DuckDB / any database | Adds dependency, no win over parquet for this scale |
| HDF5 | Tooling worse than parquet, harder to inspect |
| Pickle for cross-stage data | Not portable, version-fragile; OK only for trained models |
| CSV (comma-separated) | Cruise names contain commas |
| JSON for tabular data | Use parquet or TSV |

---

## Disk hygiene

- Stages that produce intermediate parquet (`points_raw`, `points_qc`)
  consume ~86 GB each. Document this in the script docstring.
- The pipeline doc (`docs/多波束船测数据处理流程.md` §5) marks which
  intermediates are safe to delete after downstream stages complete.
- Never delete from `raw/` or `archive/` programmatically.
