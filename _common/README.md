# `_common/` — shared utilities for ship/jamstec + ship/ncei pipelines

Single shared-lib package living at the repo root. The leading underscore
keeps it visually distinct from the dataset dirs (`jamstec/`, `ncei/`,
`archive/`) and signals "private internal lib, not a published package".

## Why a package at all

PR-E will reuse ~80% of `jamstec/multibeam/code/` for the NCEI singlebeam
pipeline. Rather than symlink steps across datasets or duplicate code,
they live here and both pipelines import from `_common`. This PR-D ships
the scaffold + the R2 sb/mb classifier. PR-E will migrate the actual
reusable algorithm primitives.

## What lives here today (PR-D scope)

- `r2_classifier.py` — pure R2 classifier (threshold + spatial-spread).
  Routes NCEI tracklines to sb vs mb based on point count + bbox area +
  density. Single entry-point: `classify(lon, lat) -> R2Result`.
- `io_helpers.py` — tiny readers for `.xyz` and `.nc` lon/lat arrays.
- `r2_calibration.py` — runnable driver that scans
  `ncei/tracklines_{nc,xyz}/`, writes the per-file classification, and
  emits the borderline-band CSV + scatter plot the user eyeballs to tune
  thresholds.
- `tests/` — unit + real-fixture tests (compatible with `python -m
  unittest` and `pytest`).
- `calibration/` — committed output of the calibration run:
  `r2_borderline.csv`, `r2_borderline.png`, `r2_hard_mb_files.csv`,
  `r2_calibration_summary.txt`.

## Planned migrations (PR-E, not this PR)

PR-E will lift these algorithmic primitives from `jamstec/multibeam/code/`
into `_common/`, then have both `jamstec/` and `ncei/` import them:

- Step 03 QC predicates (`qc_valid_lon`, `qc_valid_lat`, ... → composite
  `qc_pass_basic`).
- Step 04a per-file cell-aggregation (cell_id formula, file-cell schema).
- Step 04b global cell merge (file-balanced median aggregator).
- Step 05 overlap/bias analysis primitives.
- Step 06a–d quality-flag pipeline pieces.
- Step 07 quality-tier assignment (thresholds re-calibrated for sb in
  the ncei consumer; primitives shared).
- Step 08 validation-cell I/O.
- Step 09–11 helpers as discovered.

Step 02 standardize and Step 07 thresholds will diverge between mb / sb —
those stay in the dataset-specific `code/` dirs.

## Usage

Plain script run (works without installing the package):
```bash
python ship/_common/r2_calibration.py --limit 50
```

Test run (either runner works; unittest is built-in):
```bash
python -m unittest _common.tests.test_r2_classifier -v
# or, if pytest is available
pytest _common/tests/
```

Consumer scripts (PR-E and beyond) can use either pattern:
```python
# Pattern A — explicit sys.path insert at top of the consumer script
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from _common.r2_classifier import classify

# Pattern B — PYTHONPATH set externally
# $ PYTHONPATH=/path/to/ship python jamstec/multibeam/code/02_*.py
from _common.r2_classifier import classify
```

No real package install — keep it lightweight per the existing
"no shared lib" preference in `spec/backend/directory-structure.md`.
This dir is the carved-out exception.

## References

- `.trellis/tasks/05-11-singlebeam-integration/prd.md` (PR-D
  implementation plan, Q2 R2 rule, Locked decisions #2 / #11).
- `.trellis/spec/backend/pipeline-design-decisions.md` (decision #10 —
  R2 classifier section, added in this PR).
