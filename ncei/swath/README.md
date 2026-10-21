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
