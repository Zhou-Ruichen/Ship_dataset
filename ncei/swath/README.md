# Rebuild downloaded swath cruises

To rebuild a cruise from its existing staging shards without changing its
production directory, run from the repository root:

```bash
python -m ncei.swath batch --cruises HNRO05RR \
  --output-root /tmp/hnro05rr-rebuild
python -m ncei.swath batch --cruises HNRO05RR \
  --output-root /tmp/hnro05rr-rebuild --resume
```

`batch` writes L1 `points_raw`/`points_checked`, L2 `file_cells_1min`,
extraction and aggregation summaries, a source-manifest fragment, and coverage
statistics. L2 uses `basic_native_good`: the basic point checks and
`native_quality_state == "good"`. Counts retain null, flagged, and unknown
states in the L1 and extraction manifest.

`--output-root` is required. Nonempty output requires `--resume` and matching
saved parameters. Completed L1/L2 checkpoints are reused; a partial stage is
continued. Output under an existing production cruise is rejected. New rounds
inside `ncei/derived/mb_round2/` go under `_runs/`.

## Select inputs or extract raw files

`--input-root` defaults to `ncei/derived/mb_round2/`. Select all cruises with
staging using `--all-staged` instead of `--cruises`:

```bash
python -m ncei.swath batch --all-staged \
  --input-root /tmp/selected-staging --output-root /tmp/selected-rebuild
```

Add `--extract` to parse raw sources into the output root's `_staging/` and
`_work/` directories before rebuilding L1/L2:

```bash
python -m ncei.swath batch --cruises HNRO05RR \
  --output-root /tmp/hnro05rr-extracted --extract
```

For products that require valid source ping navigation, choose the navigation
policy explicitly:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python -m ncei.swath batch --cruises HNRO07RR NT05-06 \
  --output-root ncei/derived/processing_revision_20261025/swath/first_batch \
  --extract --selection-policy basic_native_good_valid_ping_navigation --workers 2
```

This policy selects `point_check_pass_basic`, native `good`, and
`valid_ping_navigation`. The checked point table includes the readable boolean
`point_selected_basic_native_good_valid_ping_navigation`; it retains rejected
soundings, their original beam coordinates, depth, and native state.
The existing `basic` and `basic_native_good` policies keep their meanings.
`batch` still defaults to `basic_native_good`.

Source navigation is read with `mblist -P1 -L0 -U3 -OMNXYzH` without `-MA`.
Each beam is matched on integer-microsecond epoch time and the native ping
counter. Reused counters at different times remain distinct. Duplicate exact
ping keys, missing or invalid times, unmatched beams, and inconsistent ping
order stop that source file. There is no nearest-time match.

Point and staging tables retain `parser_ping_index`, `native_ping_counter`,
`beam_index`, `ping_navigation_record_index`, `ping_lon`, `ping_lat`,
`valid_ping_navigation`, and `ping_navigation_reason`. Angles use decimal
degrees. Indices are zero-based except the unchanged source-native ping
counter. `ping_navigation_record_index` is the row in the retained per-ping
table; `parser_ping_index` is the ping ordinal among extracted beam records.
Times are UTC integer microseconds in staging (`time_us`, Unix epoch), and
UTC-valued timezone-naive timestamps in L1 (`time`).

Navigation reasons are `valid`, `nonfinite`, `out_of_range`, and
`zero_navigation`. The zero test is exactly `(ping_lon == 0) & (ping_lat == 0)`;
no near-origin radius or speed threshold enters selection. Legacy staging
without these fields merges with null navigation and reason `not_extracted`.
The old policies can still use it; the navigation policy requires newly
extracted navigation for every beam.

For MB84, extraction copies only the original uncompressed filename's `.prj`
sidecar to the renamed work input. A missing or empty source sidecar fails
that file before `mblist` runs; the extractor does not infer a UTM zone.
`extraction_manifest` and `_work/<filekey>/source_metadata.json` record the
source path, projection source path, and projection definition.
Each `_work/<filekey>/ping_navigation.parquet` retains the per-ping values,
validity, and exact matching keys after large intermediates are removed.

Existing extraction manifests preserve historical file keys and ordinals.
Without an input manifest, `--extract` enumerates gzip files in the cruise's
raw directory. Both `platforms_tree/<cruise>/` and
`platforms_tree/<ship>/<cruise>/` layouts are resolved. Extraction uses the
retained MB-System environment and `_common.mbsystem`; it makes no network
requests. Unsupported formats remain recorded; failed extraction stops the
batch with its per-file manifest available for inspection.

## Run an individual stage

These stage commands retain the original production paths and arguments.
Use `batch` for a new output root.

| Stage | Example | Result |
| --- | --- | --- |
| 33 | `python -m ncei.swath census` | File-format counts for complete cruises. |
| 34 | `python -m ncei.swath extract --cruises AR40 --workers 1` | Raw swath extraction and L1 merge. |
| 35 | `python -m ncei.swath file-cells --cruises AR40` | L2 with the original `basic` selection. |
| 36 | `python -m ncei.swath manifest` | Standalone source-manifest fragment. |
| 37 | `python -m ncei.swath coverage` | Cell-union coverage against strict primary and six regions. |
| 43 | `python -m ncei.swath quality-revision --workers 1 --resume` | The fixed first-batch quality revision and downstream comparison. |

Stage numbers are aliases, for example `python -m ncei.swath 34 --help`.
Every command accepts `--help` before processing, including the formerly
argument-free stages 33, 36, and 37.

## Quality revision and shared functions

`quality_revision.py` keeps the stage-43 command intact: its thirteen-cruise
comparison combines L1/L2 rebuilds, record exclusions, file/cruise quality
tables, and candidate/residual analysis for the two 14-seamounts regions.
Its existing arguments and isolated output restriction remain in force.
Keeping this command together preserves the historical comparison and avoids
splitting its shared state across a package and a one-off analysis script.
The rebuild, exclusion, and quality-table functions remain importable.

`batch` uses the same `extract.merge_cruise` and
`ncei.trackline.file_cells.aggregate_track_file` functions, followed by
`manifest_fragment.build_fragment` and `coverage.coverage_stats`. It does not
read the 14-seamounts candidate lists or run the stage-43 regional comparison.
Coverage and source fragments remain separate products awaiting review;
neither command merges them into a released layer.

## Compare a navigation revision

The revision comparison reads the retained native-good L1/L2 and all records
of each completed new cruise. It checks unchanged source identity, time,
beam coordinates, depth, and native state, then reports per-file and per-cruise
selection, invalid-navigation ping/beam counts, and cell changes.
The near-origin count uses `abs(lon) < 0.1` and `abs(lat) < 0.1` only as a
descriptive comparison with the original observation.

```bash
python -m ncei.swath navigation-revision audit
python -m ncei.swath navigation-revision cases
python -m ncei.swath navigation-revision compare \
  --batch-roots ncei/derived/processing_revision_20261025/swath/first_batch \
                ncei/derived/processing_revision_20261025/swath/navigation_affected_extension \
  --reuse-comparison-root ncei/derived/processing_revision_20261025/swath/first_batch_comparison
```

`audit` checks the six revision cruises against their first-batch completion
records and the successful download enumeration, including auxiliary files,
sizes, source-specific MB84 projections, and `.part` absence. It retains the
input table and output-size estimate. `cases` freshly extracts three known
source files unless its new staging already exists, then compares them to
the retained source records. `compare` requires completed batch summaries
under the navigation policy and writes `file_navigation_comparison`,
`cruise_navigation_comparison`, `cell_navigation_comparison`,
`combined_ncei_cells`, and `comparison_summary.json` under the revision root.
The combined depth remains the unweighted median of cruise-cell medians.
`--reuse-comparison-root` reuses an already completed all-record comparison
for the same old root and unchanged L1 paths and row counts.
`retained_near_origin_points` lists every still-selected point in the
descriptive near-origin window, including its source ping navigation.

## Preserve a released selection during source-record review

The bounded HNRO07RR follow-up keeps the published first-batch products
unchanged. It directly reads the three identified SB2100DR sources and
compares their navigation headers with the retained ping table, records
14 exact invalid ping identities, and writes a small beam-selection overlay.
Other source navigation remains `not_reviewed`, not reviewed good.

```bash
python -m ncei.swath navigation-case-review review
python -m ncei.swath navigation-case-review combine \
  --batch-roots ncei/derived/processing_revision_20261025/swath/first_batch \
                ncei/derived/processing_revision_20261025/swath/navigation_affected_extension
```

The independent product root is
`ncei/derived/processing_revision_20261025/swath/navigation_review/`.
`ping_navigation_review` preserves file identity, navigation-record index,
integer epoch microseconds, native ping counter, original source headers,
decompressed byte offsets, and adjacent navigation evidence.
`point_selection_overlay` retains all original beams for those pings and adds
`point_selected_basic_native_good_valid_ping_navigation_case_review`.
The research selection is the published selection minus these exact reviewed
ping keys; it introduces no radius or speed threshold. Only affected cells
are reaggregated, with untouched cruise cells reused. `combine` retains the
unweighted median of cruise-cell medians and requires completed input batches.

The known HNRO05RR follow-up uses the same implementation with explicit input
and output directories. Its preceding zero-navigation interval crosses source
files, so the review retains the exact preceding file/ping identity and reads
the intervening source DR headers. No source-navigation search threshold is
introduced.

```bash
python -m ncei.swath navigation-case-review review \
  --cruise-dir ncei/derived/processing_revision_20261025/swath/navigation_affected_extension/HNRO05RR \
  --output-root ncei/derived/processing_revision_20261025/swath/navigation_review_hnro05rr
python -m ncei.swath navigation-case-review combine \
  --batch-roots ncei/derived/processing_revision_20261025/swath/first_batch \
                ncei/derived/processing_revision_20261025/swath/navigation_affected_extension \
  --review-roots ncei/derived/processing_revision_20261025/swath/navigation_review \
                 ncei/derived/processing_revision_20261025/swath/navigation_review_hnro05rr \
  --output-root ncei/derived/processing_revision_20261025/swath/navigation_review_combined_cases
```

`--review-roots` combines the completed cruise cases into a new root, leaving
the earlier single-case product untouched. New review invocations also retain
small exact source byte ranges for the diagnosed pings and bracketing track
records. The existing HNRO07RR evidence keeps its original headers and offsets.
