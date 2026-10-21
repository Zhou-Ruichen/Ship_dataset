# `_common/` — shared utilities for the ship pipelines

Single shared-lib package at the repo root, imported by both `jamstec/` and
`ncei/` production scripts. The leading underscore keeps it distinct from
the dataset dirs and signals "private internal lib, not a published
package". No `pyproject.toml` install is needed; package entry points run from the
repository root and use ordinary imports.

## Modules

| Module | Purpose |
|---|---|
| `file_io.py` | Atomic writers shared by the production pipelines (`atomic_write_parquet`, `atomic_write_text`, `atomic_write_tsv`, `write_errors_tsv`): build at a `.tmp` sibling, then rename. |
| `script_utils.py` | `setup_logging` (dual sink: DEBUG file + console) and `markdown_table` / `ensure_columns` report helpers for stage scripts. |
| `mbsystem.py` | mblist U3/U0 listing parser and SQLite join for round-2 swath L1 extraction (`ncei/swath/extract.py`). Entry point `raw_from_object(...)`. |
| `r2_classifier.py` | Pure R2 sb/mb classifier (threshold + spatial spread) routing NCEI tracklines; `classify(lon, lat) -> R2Result`. |
| `io_helpers.py` | Streaming lon/lat readers for NCEI `.nc` and `.xyz` trackline files (used by the calibration driver). |
| `singlebeam_bias.py` | Shared estimators for constant singlebeam track bias. |
| `r2_calibration.py` | Runnable calibration driver: scans `ncei/tracklines_{nc,xyz}/`, writes per-file classification plus borderline-band CSV/plot for threshold tuning. |

`calibration/` holds the committed output of the calibration run
(`r2_borderline.csv`, `r2_borderline.png`, `r2_hard_mb_files.csv`,
`r2_calibration_summary.txt`).

## Tests

`_common/tests/` runs with `python -m unittest` or `pytest` from the repo
root:

- `test_r2_classifier.py` — classifier unit tests + real-fixture tests
  (skip cleanly when `ncei/tracklines_xyz/` is absent).
- `test_file_io.py`, `test_script_utils.py` — shared-helper unit tests.
- `test_ncei_download.py` — downloader package tests (inventory/diff/
  fetch/merge/verify, log schema compatibility with 41).
- `test_mb_round2_quality.py` — round-2 extract/source/quality-revision
  tests (imports `ncei.swath` and `ncei.trackline` modules; uses a real
  staging shard when present).
- `fixtures/` — small mb58/U3/U0 sample files (kept from the archived SCS
  chain; no current test imports them).

```bash
python -m unittest _common.tests.test_r2_classifier -v
pytest _common/tests/
```

## Usage in consumer scripts

```python
from _common.r2_classifier import classify, R2Result
from ncei.trackline.file_cells import aggregate_track_file
```

Run NCEI package commands from the repository root through
`python -m ncei.trackline`, `python -m ncei.swath`, or
`python -m ncei.download`. Unpackaged legacy scripts still need the
repo-root bootstrap described in `AGENTS.md`.

## References

- `.trellis/spec/backend/pipeline-design-decisions.md` (R2 classifier
  decision, shared-helper consolidation).
- `docs/code_archive.md` (what moved out of the tree in the 2026-10
  reorganization).
