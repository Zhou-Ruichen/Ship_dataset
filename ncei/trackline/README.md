# Process NCEI tracklines

To inspect the singlebeam workload before writing products, run from the
repository root:

```bash
python -m ncei.trackline standardize-nc --estimate-only
python -m ncei.trackline --help
python -m ncei.trackline file-cells --help
```

The package covers NetCDF singlebeam, XYZ singlebeam/multibeam, the regional
MRAR branch, and static MGD77T. Commands run one stage, not an automatic chain.
Original stage numbers remain aliases: `python -m ncei.trackline 25` is
`python -m ncei.trackline global-bias`.

## Run the stages

Each row is a complete command to run from the repository root. The named
inputs must already exist. Stage-specific `--help` lists the unchanged options.

| Stage | Example | Result |
| --- | --- | --- |
| 01 | `python -m ncei.trackline manifest --run-label sample --sample-n-files 5` | Trackline source manifest. |
| 02 | `python -m ncei.trackline standardize-nc --run-label sample --sample-n-files 5` | NetCDF singlebeam L1 points. |
| 03 | `python -m ncei.trackline standardize-xyz --run-label sample --sample-n-files 5` | XYZ L1 points, routed by instrument class. |
| 04 | `python -m ncei.trackline clean-mrar --run-label sample --sample-n-rows 1000` | MRAR bathymetry and land-mask tables. |
| 05 | `python -m ncei.trackline point-qc --run-label sample --sample-n-files 5` | Entry manifest and checked points. |
| 06 | `python -m ncei.trackline supplementary-qc --run-label sample --sample-n-files 5` | Supplementary checks and divergence audit. |
| 07 | `python -m ncei.trackline file-cells --run-label sample` | One-minute cells per track. |
| 08 | `python -m ncei.trackline merge-cells --run-label sample --limit-files-per-branch 5` | Merged branch cells. |
| 09 | `python -m ncei.trackline source-overlap --run-label sample --limit-files-per-branch 5` | Within-source overlap residuals. |
| 10 | `python -m ncei.trackline branch-overlap --run-label sample --limit-rows-per-pair 1000` | Cross-branch overlap residuals. |
| 11 | `python -m ncei.trackline policy-audit --run-label sample` | Quality-policy calibration evidence. |
| 12 | `python -m ncei.trackline apply-policy --run-label sample` | Cell-quality sidecar. |
| 13 | `python -m ncei.trackline validation-cells --run-label sample` | Validation-cell products. |
| 23 | `python -m ncei.trackline track-bias` | Six-region track-bias estimates and controls. |
| 24 | `python -m ncei.trackline crossover` | Six-region geometric crossover audit. |
| 25 | `python -m ncei.trackline global-bias` | Global track biases and adjusted cells. |
| 26 | `python -m ncei.trackline global-crossover` | Global crossover evidence. |
| 28 | `python -m ncei.trackline disposition` | Six-region track-quality dispositions. |
| 30 | `python -m ncei.trackline global-disposition` | Global dispositions and final singlebeam cells. |
| 31 | `python -m ncei.trackline global-grid` | Immutable merged global one-minute grid. |
| 39 | `python -m ncei.trackline mgd77t-xyz --surveys HNRO05RR` | Static MGD77T converted to XYZ. |
| 40 | `python -m ncei.trackline mgd77t-fragments --tracks hnro05rr --workers 1` | Standalone static MGD77T L1/L2 and source fragment. |

Stages 01-13 retain their `sample`/`test100`/`full` choices where supported,
`--confirm-full`, and `--overwrite` behavior. Sample mode does not imply an
isolated product root: standardization and point-QC stages still use their
original per-track directories. Global stages retain their existing-output
guards; `global-grid` refuses an existing round.

## Reuse the calculation functions

Modules have descriptive names and can be imported normally:

```python
from ncei.trackline.standardize_xyz import standardize_one_track
from ncei.trackline.point_qc import compute_flag_arrays
from ncei.trackline.file_cells import aggregate_track_file
```

`file_cells.py` supplies the same aggregator to `ncei.swath`. Selection defaults
to `basic`; `basic_native_good` also requires a recorded native `good` state.
Table schemas, scientific version labels, output directories, log names, and
report names are unchanged. New product manifests record the package command.
The complete old-path/module/command mapping is in `docs/code_archive.md`.
