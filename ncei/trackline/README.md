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
| | `python -m ncei.trackline mgd77t-nc --input /path/survey.m77t --header /path/survey.h77t --output /new/root/survey.nc` | Source-preserving NetCDF, without changing existing products. |

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

## Preserve MGD77T observations, quality and time

Convert a complete source file into a new, explicitly chosen product. Run from
the repository root; `--header` is the formal survey documentation, not the
`SURVEY_ID` column heading in the observation file:

```bash
/opt/miniforge3/envs/torch29/bin/python -m ncei.trackline mgd77t-nc \
  --input /path/survey.m77t \
  --header /path/survey.h77t \
  --output /new/root/survey.nc \
  --legacy-netcdf /old/root/survey.nc \
  --mapping-output /new/root/survey_rows.parquet
```

`--legacy-netcdf` and `--mapping-output` are optional. Existing outputs are
refused unless `--overwrite` is supplied. `--source-url` and `--header-url`
record upstream locations. All source observations survive, including the
first observation, headerless first rows and short records with omitted tail
fields. Empty numeric fields become NaN with a NaN `_FillValue`; nonempty
numeric fields, including real zeroes and source sentinel numbers, are copied
without clipping or additional physical corrections. Quality selection belongs
to the consumer, not this conversion.

The NetCDF dimension remains `time`. Core variables are `lon`, `lat`, `depth`
(m, positive down), `gobs`, `faa` (both mGal), `bat_ttime` (s), `eotvos` (mGal),
`timezone_correction_hours`, and the source magnetic variables. `POS_TYPE`,
`NAV_QUALCO`, `BAT_CPCO`, `BAT_TYPCO`, `BAT_QUALCO`, `MAG_RESSEN`,
`MAG_QUALCO` and `GRA_QUALCO` retain their source code values; missing codes are
masked integers. Codes are not combined with numeric validity or instrument
class. In particular, gravity quality is preserved even where FAA is missing.
Every one of the 26 source fields is also available as its exact string in
`source_fields`, preserving `DATE`, `TIME`, `TIMEZONE`, leading zeroes,
identifiers and unspecified states.

`time` is UTC only for valid source dates/times with a specified valid timezone.
The MGD77T timezone correction is added to the source time. Unspecified dates,
times or timezones never become 1970-01-01. A separate variable,
`time_assuming_unspecified_timezone_zero`, provides explicitly assumed UTC for
valid source times whose timezone was unspecified. It still leaves missing
source times missing. `time_status` identifies the policy per observation:

| Code | Meaning |
| --- | --- |
| 0 | Source date or time unspecified. |
| 1 | UTC from source date, time and specified timezone. |
| 2 | Valid source date/time, timezone unspecified; only the named assumption variable is populated. |
| 3 | Source date or time invalid. |
| 4 | Source timezone invalid. |

All 58 standard formal header fields and any additional named NOAA catalogue
fields are attributes of `source_header`; unspecified header values stay
empty. The parser accepts the 96-column catalogue export and preserves its
original `MG77T`/`MGD77T` format declaration. Compatibility global attributes such as
`Source_Institution` come only from that header. An omitted `--header` records
`source_header_status=not_supplied` and an empty institution rather than
inferring it from the observation file.

The embedded mapping and optional Parquet/CSV use `source_line_1based` for
physical source lines, and `source_observation_index_0based`,
`old_netcdf_row_0based`, `new_netcdf_row_0based` for zero-based row indices.
An observation absent from the old product has a null old index in Parquet/CSV
and a masked `-1` in NetCDF. All old coordinates are checked in source order
before an alignment is accepted; an ambiguous or non-contiguous alignment
raises an error. Do not apply an old position table directly to new row numbers.

```python
import netCDF4
import numpy as np
import polars as pl

with netCDF4.Dataset("/new/root/survey.nc") as ds:
    faa = np.ma.asarray(ds["faa"][:], dtype=float).filled(np.nan)
    gravity_quality = ds["GRA_QUALCO"][:]
    original_time = ds.groups["source_fields"]["TIME"][:]
    institution = ds.groups["source_header"].getncattr("INST_SRC")

mapping = pl.read_parquet("/new/root/survey_rows.parquet")
new_row = mapping.filter(pl.col("old_netcdf_row_0based") == 123)[
    "new_netcdf_row_0based"
].item()
```

Reuse the parser for large point tables without an XYZ intermediate:

```python
from ncei.trackline.mgd77t import iter_mgd77t, decode_time, read_header

for records in iter_mgd77t("/path/survey.m77t", chunk_size=100_000):
    depth = records.numeric("CORR_DEPTH")
    source_quality = records.raw["BAT_QUALCO"]
    physical_lines = records.source_line_1based
    source_indices = records.source_observation_index_0based
    time = decode_time(records)
```

`read_mgd77t(path)` reads a whole survey using the same parser.
`read_header(path, survey_id).fields` supplies formal header strings.
`decode_time(records)` returns `utc_seconds`,
`assuming_unspecified_timezone_zero_seconds` and `status`. The parser accepts
the extra trailing empty field found in static-tree files and retains the
original width in `source_field_count`.

`legacy-faa-revision --help` describes the explicit batch inputs for rebuilding
the 15-cruise legacy FAA revision, comparing every source field and numeric
variable, remapping the previously used locations, and inventorying additional
complete local sources. `--verify-only` checks existing new products without
converting them. The isolated 2026-10-25 delivery is
`ncei/derived/processing_revision_20261025/legacy_faa/`; its result record is
`.trellis/tasks/10-25-ship-processing-repair/legacy_faa_result.md`.

`source-corrections` structures the delivered sources' physical-correction
declarations (sound speed, attitude bias, draft, tide, vertical datum,
gravity formula/reference system) with per-file evidence pointers, without
changing any depth or FAA value:

```bash
python -m ncei.trackline source-corrections \
  --product-root ncei/derived/processing_revision_20261025
```

It reads the existing trackline/legacy-FAA/swath manifests and headers,
plus the gzip preambles of the delivered `.mb41.gz` swath files (decompressed
only up to the first `SB2100DR` record). Outputs are
tables under `source_corrections/`; see that directory's README for state
semantics and join keys.

`legacy-faa-revision --additional-inventory <inventory.csv> --output-root
<new/root>` converts an explicit list of complete local sources with the same
converter, coordinate alignment and all-record comparison. It does not require
the original 15-cruise comparison tables or previously used-position table.
The six-cruise delivery is
`ncei/derived/processing_revision_20261025/legacy_faa_additional/`.

## Preserve source quality in static MGD77T point tables

The existing XYZ command still writes its original three-column layout. The
fragment command defaults to its historical XYZ mode. Add `--source-fields`
and an explicit output root to read complete `.m77t/.h77t` sources directly:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 POLARS_MAX_THREADS=1 \
/opt/miniforge3/envs/torch29/bin/python -m ncei.trackline mgd77t-fragments \
  --source-fields --workers 2 --tracks ar1-06 \
  --source-root ncei/raw_round2/mgd77t_static \
  --output-root /new/root
```

Input files are discovered under `--source-root/*/*.m77t`, not a downstream
comparison table. Optional `--evidence-root` supplies historical numerical and
quality comparisons. Historical point products are compared when available;
their absence does not prevent conversion. `--no-legacy-comparison` disables
all reads of those products and their classification manifest:

```bash
/opt/miniforge3/envs/torch29/bin/python -m ncei.trackline mgd77t-fragments \
  --source-fields --workers 1 --tracks ar1-06 --no-legacy-comparison \
  --source-root ncei/raw_round2/mgd77t_static \
  --output-root /new/independent-root
```

Retained instrument predictions come from the local previous fragment
manifest, or an explicit `--classification-manifest`. Without a retained
prediction, classification is `unclassified`: its points and per-file cells
are written, not silently included in a singlebeam or multibeam merge.
Depth-sign diagnosis uses the existing unfiltered XYZ conversion/sign rules,
independent of external evidence. Zero basic selection is reported as
`no_selected_depth`; that status does not claim every original depth is missing.

The point tables retain every source observation, including short records without a depth
column. Both point tables include all 26 exact `<FIELD>_raw` strings, original time
components and timezone states, numeric quality/observation codes, formal
`BATH_INSTR` and the retained prediction. `points_raw/` is the source-preserving
L1, `points_checked/` adds point checks, `file_cells_1min/` contains L2
per-file one-minute aggregates, and `source_manifest.parquet` is the L3 source
inventory. `source_headers.parquet` and each point
file's schema metadata retain all named formal header fields.

`source_type=ncei_xyz` and `source_completeness=xyz_only` are historical
aggregation/registry compatibility labels. They do not describe missing
MGD77T metadata in this mode. `source_format=MGD77T`, original fields, formal
headers, time and quality columns identify the actual complete source.

`source_observation_index_0based` and `point_table_row_0based` are distinct
from physical `source_line_1based`. A verified old point correspondence uses
`legacy_point_index_in_track`, null for records omitted by the old XYZ
converter. With no historical comparison, the old index stays null rather
than claiming an established correspondence.

The primary mask is `point_selected_basic_source_quality`, equal to the
existing `point_check_pass_basic` and `source_quality_usable`. The latter
requires both `NAV_QUALCO` and `BAT_QUALCO` not to be 3/4/5/6. Codes 1/2 and
unspecified codes remain; unspecified states have separate flags/counts.
`source_quality_excluded_from_basic` is the actual removed union, not the
sum of navigation and bathymetry frequencies. Time, `POS_TYPE`, `BAT_TYPCO`
and `BAT_CPCO` introduce no further thresholds.

`depth_m_positive_down` is in metres. `source_corr_depth_m` and
`CORR_DEPTH_raw` retain source values/text; `depth_raw` applies the existing
absolute-value sentinel band of 99,999. Working depth retains existing sign
normalization and the 11,500 m upper clip. No physical correction is repeated.
The main `time` requires a specified valid timezone. The separately named
`time_assuming_unspecified_timezone_zero` is an explicit assumption.

`file_cells_1min/` uses `basic_source_quality`; `file_cells_1min_basic/`
preserves the basic-only comparison. Both reuse the existing full-point and
unique-triple medians and duplicate ratios; `merged_cells_1min/<policy>/`
uses the existing file-balanced median. Per-track completion/comparison
records are in `comparison/`; `--resume` reuses completed tracks.

## Compute source-indexed crossovers in the existing six regions

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 POLARS_MAX_THREADS=1 \
/opt/miniforge3/envs/torch29/bin/python -m ncei.trackline crossover \
  --source-points-root ncei/derived/processing_revision_20261025/trackline \
  --output-root ncei/derived/processing_revision_20261025/trackline/crossovers
```

This mode reads only retained singlebeam predictions and the six existing
region bounding boxes. It computes basic and source-quality comparisons with
`RegionTracks`, `grid_candidate_pairs`, `exact_intersections`,
`orient_and_filter` and `pair_and_track_stats` from the existing module.
Segments require original observation indices differing by exactly one and
retain the existing 0.25-degree spacing limit; filtered adjacent table rows
are not automatically connected. Every event includes both segments' source
files, original endpoint indices and physical lines. Missing time does not
remove geometry. Known UTC orders an event when available on both tracks;
otherwise track ID supplies an explicitly arbitrary orientation.

`region_summary.csv` distinguishes bounding-box candidates, clipped points,
segments and actual supported crossings. Empty crossings remain empty, not
an inferred zero cruise bias. No whole-cruise time-reversal rejection,
crossover correction or gravity-difference selection is applied.
