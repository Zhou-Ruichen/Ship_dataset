# Quality Guidelines

> Code quality conventions for the Python data pipeline.

The audience for these rules is the AI sub-agents that write or modify
pipeline scripts. Match the existing patterns in `jamstec/multibeam/code/`
unless there is a documented reason not to.

---

## Required script structure

Every numbered pipeline script MUST follow this skeleton:

```python
#!/usr/bin/env python3
"""
<NN>_<name>.py

<one-line purpose>

Reads:
  - <input path 1>
  - <input path 2>

Writes (full mode):
  - <output path 1>
  - <output path 2>
  - output/logs/<NN>_<name>.log
  - output/logs/<NN>_<name>_errors.tsv

Usage:
    python <NN>_<name>.py --run-label sample --sample-n-files 5 --overwrite
    python <NN>_<name>.py --run-label test100 --limit-files 100 --overwrite
    python <NN>_<name>.py --run-label full --confirm-full --overwrite
    python <NN>_<name>.py --run-label full --confirm-full --estimate-only
"""

import argparse, logging, os, sys
from pathlib import Path
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT_DIR = SCRIPT_DIR.parent
```

The docstring `Reads:` / `Writes:` block is contractual — `08_validate_…`
and downstream stages depend on it for path discovery during code review.

---

## Run-label gating (sample / test100 / full)

This is the project's most important convention.

```
VALID_RUN_LABELS = ("sample", "test100", "full")
```

| Label | Output dir suffix | Required flags |
|-------|-------------------|----------------|
| `sample` | `derived/<stage>_sample/` | `--sample-n-files N` |
| `test100` | `derived/<stage>_test100/` | `--limit-files 100` |
| `full` | `derived/<stage>/` (no suffix) | `--confirm-full` |

Rules:
- **`full` MUST require `--confirm-full`.** A bare `--run-label full` invocation
  must error out. This guards against accidental hours-long re-runs that
  overwrite production parquet.
- Every stage MUST support `--estimate-only` for dry-run accounting.
- Every stage MUST support `--overwrite` and otherwise skip outputs that
  already exist (resumability is non-negotiable; see "Resumability" below).
- Sample/test100 outputs MUST go to a separate suffixed directory so they
  never overwrite full-run products.

---

## Resumability

Long stages (Step 02, 03, 04a — 5,083 files each) MUST be safe to interrupt
and re-run:

- Skip files whose output parquet already exists, unless `--overwrite`.
- Write per-file outputs atomically (write to `*.tmp`, then rename) when a
  consumer might tail the directory.
- Failures on individual files MUST be appended to the per-stage error TSV
  (`output/logs/<script>_errors.tsv`); the script continues with the rest.

A stage is considered correctly resumable if running it twice in a row, the
second invocation completes in seconds with zero new outputs.

---

## Forbidden patterns

| ❌ Don't | ✅ Do |
|---|---|
| `os.getcwd()` for path resolution | `Path(__file__).parent.resolve()` |
| Hardcoded absolute paths (`/mnt/data2/...`) | Paths derived from `ROOT_DIR` |
| `print(...)` for progress | `logger.info(...)` (see logging spec) |
| Silently swallow per-file exceptions | Append to `*_errors.tsv` and continue |
| Overwrite full-run output without `--confirm-full --overwrite` | Two-flag confirmation |
| Aggregate by simple mean across all points | File-balanced aggregation (see pipeline-design-decisions) |
| Mutate input parquet in place | Always write a new derived directory |
| Use `pickle` for cross-stage data | Parquet (intermediate) or TSV/MD (reports) |
| Introduce a new top-level dependency without need | Stick to `pandas / numpy / pyarrow / xarray / scipy / scikit-learn` |

---

## Required CLI surface

Every numbered stage script accepts at minimum:

```
--run-label {sample,test100,full}
--overwrite
--estimate-only
--confirm-full              # required when --run-label full
```

Plus stage-specific selectors (whichever fit):
```
--sample-n-files N          # sample mode
--limit-files N             # test100 mode
--include-filename-regex P  # filter
--cell-size 1min            # only stages that produce cells
```

---

## Testing & verification

There is no pytest suite. Verification is **report-driven**:

- Every stage writes a `docs/<stage>_report.md` with row counts, schema,
  and key statistics. The report IS the test artifact.
- Before marking work complete, run the stage in `sample` mode and visually
  inspect the report.
- For numerical changes (algorithms, thresholds), include a before/after
  comparison report (see `06d_compare_original_vs_qcfiltered_cells.py`
  as the pattern to follow).

Do not introduce a `tests/` directory or pytest fixtures without explicit
agreement — this is a research pipeline, not application code.

---

## Code style

- Python 3, no type-checker enforced. Add type hints opportunistically; do
  not refactor existing untyped code purely to add hints.
- No formatter enforced (no black/ruff config in repo). Match surrounding
  style.
- `f""` for string formatting. Long log messages may use `%`-style for
  lazy evaluation (`logger.info("count=%d", n)`).
- Group imports: stdlib → third-party → local. One blank line between groups.
