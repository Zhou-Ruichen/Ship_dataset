# Rebuild downloaded multibeam cruises

Run from the repository root. The streaming chain decodes one source file at a
time, applies the current sounding selection, and retains the 1-arcmin cruise
cells. Raw sources and existing products remain read-only.

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 POLARS_MAX_THREADS=1
python -m ncei.swath census --output-root ncei/derived/swath_rebuild_check/example
python -m ncei.swath run --cruises RR0913 --workers 8 \
  --output-root ncei/derived/swath_rebuild_check/example
python -m ncei.swath run --cruises RR0913 --workers 8 --resume \
  --output-root ncei/derived/swath_rebuild_check/example
python -m ncei.swath coverage --output-root ncei/derived/swath_rebuild_check/example
```

Omit `--cruises` to process every platform-tree cruise with `status=ok` in
`ncei/manifests/round2_download_log.parquet`. Explicit cruise IDs retain their
supplied order; otherwise RR0913 is processed first when present. `--workers` controls concurrent source-file decoders within a
cruise, with a positive worker count. A batch stops before its next cruise when data2 has less
than 300 GB free.

The default raw roots are `ncei/raw_round2/platforms_tree` and
`/mnt/data1/pub/ship/ncei/raw_round2/platforms_tree`. Replace them with repeatable
`--raw-root PATH` arguments. Both `<cruise>/` and `<ship>/<cruise>/` layouts are
resolved. Historical extraction manifests supply existing filekeys and
ordinals. New keys use the SHA-256 prefix of the path relative to the platform tree.
A file present in both roots is read once, preferring the first root.


For a separate code worktree, pass the existing data checkout and all external
inputs as absolute paths:

```bash
python -m ncei.swath run --data-root /mnt/data2/00-Data/ship \
  --ledger /mnt/data2/00-Data/ship/ncei/manifests/round2_download_log.parquet \
  --raw-root /mnt/data2/00-Data/ship/ncei/raw_round2/platforms_tree \
  --raw-root /mnt/data1/pub/ship/ncei/raw_round2/platforms_tree \
  --exclude-pings /mnt/data2/00-Data/ship/ncei/derived/swath_rebuild_check/reference_final/excluded_pings.parquet \
  --output-root /mnt/data2/00-Data/ship/ncei/derived/swath_rebuild_20261112 \
  --workers 32
```

`--data-root` supplies the existing MB-System environment, historical
extraction keys, and review records. `--ledger`, `--exclude-pings`, repeatable
`--raw-root`, and `--output-root` can each point outside the code checkout.
`coverage` accepts `--strict-path` and `--regions-yaml` for its two references.

## Selection and aggregation

The current selection requires `point_check_pass_basic`, native quality
`good`, and `valid_ping_navigation`. It excludes the 19 source pings confirmed
invalid in the HNRO07RR and HNRO05RR navigation reviews. Exact exclusion keys
are `filekey`, `ping_navigation_record_index`, `epoch_us`, and
`native_ping_counter`. Use `--exclude-pings TABLE.parquet` to provide a table
with these four columns. `--no-exclusions` reproduces the numerical navigation
selection for comparison.

Source navigation is read using `mblist -P1 -L0 -U3 -OMNXYzH` without `-MA`.
Beam listings use `-MA -U3/-U0 -OMN#XYzH`. U0 membership defines native good
quality. Navigation joins use integer UTC microseconds and native ping
counter. Repeated counters at different times remain distinct. Missing keys,
duplicate identities, inconsistent order, and U0/U3 value disagreement fail
the source file. MB84 requires its original uncompressed filename's `.prj`.

Beam longitude is normalized to `[-180, 180)`. The basic checks accept finite
longitude and latitude, latitude in `[-90, 90]`, and positive depth up to
11,500 m. Cruise-wide depth sign follows the 10-25 convention: at least 95%
negative finite depths, including zeros in the denominator, flips the sign;
otherwise it is unchanged. Numerical source navigation rejects nonfinite,
out-of-range, and exactly `(0, 0)` coordinates. No radius or speed threshold
enters selection.

Temporary parquet shards retain candidate longitude, latitude, and raw depth
for both possible depth signs. Once all files complete, the cruise depth sign
is applied and `ncei.trackline.file_cells.aggregate_track_file` computes the
same 23 output columns as the 10-25 official product, including the median of
all selected soundings, the median of unique exact triples, and duplicate
ratio. Large cruises are partitioned by complete cells before invoking that
aggregator, so one cell's soundings and their order are preserved. Temporary files live under `<output-root>/_tmp/<cruise>/` and are removed
after the cruise checkpoint is written. No staging or L1 products are written
by `run`.

For multiple supported formats, each format's file ping-time intervals are
merged into a union and the unions are intersected pairwise. Temporal overlap
sets cruise status `format_overlap` and produces no L2. Non-overlapping formats
share one L2 with sorted labels such as `ncei_mb41_mb58` and `mb41_mb58`.
Unsupported files remain listed and the supported files can produce L2.
A supported decoding failure sets cruise status `failed`, produces no L2, and
the batch proceeds to the next cruise. Exceptions and their tracebacks are
retained in `files.parquet`.

## Products

| Path below the output root | Contents |
| --- | --- |
| `cells_1min/<cruise>.parquet` | Official 23-column cruise-cell contract |
| `files.parquet` | Source keys, paths, formats, status, raw bytes, beam/quality/selection counts, ping-time bounds in UTC integer microseconds |
| `cruises.parquet` | Cruise status, counts, format intervals and overlaps, elapsed seconds, the former stage-36 source fields |
| `run_parameters.json` | Raw roots, selection policy and rule, exclusion-table path and SHA-256, MB-System version and code commit |
| `run_invocations.jsonl` | Append-only invocation times, cruise lists, ledger paths, workers and resume settings |
| `excluded_pings.parquet` | The default 19 confirmed-invalid source ping identities |
| `hnro14rr_sensitivity_beams.parquet` | 11,816 diagnosed beam identities, excluded from the default selection rules |
| `census.parquet` | Cruise/format file counts, bytes, supported status |
| `coverage_vs_strict_primary.parquet` | Global and six-region unique-cell coverage against the strict layer |
| `_completed/<cruise>` | Completed cruise marker used by `--resume` |

`cruises.parquet` includes `formats`, per-format file and beam counts in
`format_counts`, each format's merged `intervals_us`, and pairwise
`format_overlaps`. `format_overlap_us` sums pairwise overlap durations.
A shared endpoint counts as overlap even when the duration is zero.
`n_pass_basic`, `n_selected_basic_native_good`,
`n_selected_before_exclusions`, `n_excluded_selected_beams`, and `n_selected`
record the successive selection counts. `n_excluded_beams` counts all beams
belonging to the listed invalid pings, including already rejected beams.

`--resume` requires matching input roots, selection, exclusion-table contents,
and aggregation parameters. Each invocation can extend the cruise list;
completed cruises are skipped and an incomplete cruise is rebuilt from its raw files. Interrupted
manifest updates are recovered from `_checkpoints/`. Workers may change on
resume. Existing L2 files are replaced only while rebuilding an incomplete
cruise in that run's output directory.

`run_parameters.json` also records the HNRO14RR sensitivity-table path and
SHA-256. The invocation record retains each requested cruise list separately.

## Recreate checked soundings on demand

```bash
python -m ncei.swath points --cruise NT05-06 \
  --output-root ncei/derived/swath_rebuild_check/points
python -m ncei.swath points --cruise HNRO07RR \
  --files 9cc351d9386a1a84 \
  --bbox -0.1 -0.1 0.1 0.1 \
  --output-root ncei/derived/swath_rebuild_check/local_points
```

`points_checked/<cruise>.parquet` retains all decoded soundings, their quality
and checks, using the 10-25 `points_checked` column contract. Its selection
boolean applies the current ping exclusions. File and geographic restrictions
limit the delivered rows; cruise-wide depth sign and original point ordinals
are retained. `--files` accepts filekeys, filenames, historical relative paths,
or absolute source paths. Bounds are west, south, east, north and include both
endpoints. The command reads all supported files to preserve whole-cruise
point indices and depth-sign semantics. Rejected rows remain in the delivered
point table.

Historical revision commands and stage-number aliases were removed; their
products remain at their original locations. Removed code can
be retrieved using the commit recorded in `docs/code_archive.md`.
