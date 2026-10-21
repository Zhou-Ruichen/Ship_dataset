# NCEI processing packages

Owner: P. Date: 2026-10-21. Base: `a5c2194`.
Implementation and bounded checks are complete. No commit or push was made.
All behavior-check outputs are under `/tmp/p_check/`.

## Entry points and module responsibilities

Run from `/mnt/data2/00-Data/ship`:

```bash
python -m ncei.trackline --help
python -m ncei.swath --help
python -m ncei.download --help
python -m ncei.swath batch --cruises HNRO05RR \
  --output-root /tmp/p_check/swath_batch --resume
```

Each processing package has a small `__main__.py` dispatcher, `__init__.py`,
and a README with runnable examples. Dispatchers list commands in processing
order and pass the remaining arguments unchanged to the module's `main(argv)`.
Stage numbers are aliases, including the leading zero for stages 01-09.
Download planning retains its original options and is checked by help/import
only while the Tier-B job consumes the ranking lists.

The old filename in each row was under `ncei/code/`. The complete old-path to
new-path table is also in `docs/code_archive.md`.

| Old filename | New module | Command | Responsibility |
| --- | --- | --- | --- |
| `01_build_trackline_source_manifest.py` | `ncei.trackline.manifest` | `manifest` / `01` | Register source-side tracklines and classify instrument type. |
| `02_standardize_singlebeam.py` | `ncei.trackline.standardize_singlebeam` | `standardize-nc` / `02` | Standardize NetCDF singlebeam points. |
| `03_standardize_xyz.py` | `ncei.trackline.standardize_xyz` | `standardize-xyz` / `03` | Standardize XYZ singlebeam/multibeam points. |
| `04_clean_mrar.py` | `ncei.trackline.clean_mrar` | `clean-mrar` / `04` | Clean MRAR bathymetry and land-mask records. |
| `05_point_quality_check.py` | `ncei.trackline.point_qc` | `point-qc` / `05` | Write checked points and the entry manifest. |
| `06_supplementary_quality_check.py` | `ncei.trackline.supplementary_qc` | `supplementary-qc` / `06` | Supplementary duplicate, range and source-divergence checks. |
| `07_aggregate_file_cells_1min.py` | `ncei.trackline.file_cells` | `file-cells` / `07` | Exact per-track one-minute cell aggregation, shared with swath. |
| `08_merge_branch_cells_1min.py` | `ncei.trackline.merge_cells` | `merge-cells` / `08` | Merge per-track cells within each branch. |
| `09_source_specific_overlap_residuals.py` | `ncei.trackline.source_overlap` | `source-overlap` / `09` | Measure within-source overlap residuals. |
| `10_cross_branch_overlap_audit.py` | `ncei.trackline.branch_overlap` | `branch-overlap` / `10` | Measure cross-branch overlap residuals. |
| `11_quality_policy_calibration_audit.py` | `ncei.trackline.policy_audit` | `policy-audit` / `11` | Produce quality-policy calibration evidence. |
| `12_apply_quality_policy.py` | `ncei.trackline.apply_policy` | `apply-policy` / `12` | Apply the retained cell-quality policy. |
| `13_build_validation_cells.py` | `ncei.trackline.validation_cells` | `validation-cells` / `13` | Build validation-cell layers. |
| `23_estimate_singlebeam_track_bias_1min.py` | `ncei.trackline.track_bias` | `track-bias` / `23` | Estimate six-region singlebeam track biases. |
| `24_true_crossover_audit.py` | `ncei.trackline.crossover` | `crossover` / `24` | Audit six-region geometric crossovers. |
| `25_global_singlebeam_track_bias.py` | `ncei.trackline.global_bias` | `global-bias` / `25` | Estimate global biases and adjusted singlebeam cells. |
| `26_global_singlebeam_crossover_audit.py` | `ncei.trackline.global_crossover` | `global-crossover` / `26` | Produce global crossover evidence. |
| `28_sb_track_quality_disposition_1min.py` | `ncei.trackline.disposition` | `disposition` / `28` | Build regional track dispositions and controls. |
| `30_global_sb_track_disposition.py` | `ncei.trackline.global_disposition` | `global-disposition` / `30` | Build global dispositions and final singlebeam cells. |
| `31_build_global_grid_1min.py` | `ncei.trackline.global_grid` | `global-grid` / `31` | Merge strict multibeam and final singlebeam into the global grid. |
| `39_m77t_to_xyz.py` | `ncei.trackline.mgd77t_xyz` | `mgd77t-xyz` / `39` | Convert static MGD77T to XYZ. |
| `40_m77t_static_fragments.py` | `ncei.trackline.mgd77t_fragments` | `mgd77t-fragments` / `40` | Reuse trackline functions for static MGD77T L1/L2/L3 fragments. |
| `33_mb_round2_format_survey.py` | `ncei.swath.census` | `census` / `33` | Inventory formats in complete raw cruises. |
| `34_mb_round2_extract_points.py` | `ncei.swath.extract` | `extract` / `34` | Extract staging and rebuild native-quality-aware L1. |
| `35_mb_round2_file_cells.py` | `ncei.swath.file_cells` | `file-cells` / `35` | Aggregate swath L2 using the original `basic` policy. |
| `36_mb_round2_source_manifest_fragment.py` | `ncei.swath.manifest_fragment` | `manifest` / `36` | Build a standalone source-manifest fragment. |
| `37_mb_round2_coverage_stats.py` | `ncei.swath.coverage` | `coverage` / `37` | Measure global and regional coverage against strict primary. |
| `43_mb_round2_quality_revision.py` | `ncei.swath.quality_revision` | `quality-revision` / `43` | Retain the fixed first-batch quality revision and regional comparison. |
| `38_mbbdb_value_ranking.py` | `ncei.download.rank` | `rank` / `38` | Estimate download value and write tier order lists. |
| New | `ncei.swath.batch` | `batch` | Extract or rebuild selected cruises, aggregate native-good L2, and write source/coverage products. |

## Migration and calculation review

All 29 old scripts were moved with `git mv`. `git diff -M HEAD --summary`
recognizes all 29 as renames, with similarity 77-99%. `git diff -M --stat`
was inspected as well; it shows edits against the already staged moves.
`HEAD` is used for the combined rename-plus-edit comparison.

Every moved-file diff was reviewed. The shared changes are command
docstrings, normal imports in place of bootstrap/importlib loaders,
`main(argv)`/`parse_args(argv)` wiring, and new command strings in newly
written manifests/reports. An AST comparison found all original
`add_argument` calls unchanged across the 29 scripts:
`/tmp/p_check/argument_contracts.json`.
Stages 31, 33, 36 and 37 now parse an empty argument set before processing.
Existing flags, defaults, full-run gates and overwrite guards are retained.

The following adjacent changes support the explicitly requested batch root:

- Stage 07 returns repository-relative paths with `os.path.relpath`, so
  scratch files outside the repository can be described. In-repository
  values and aggregation calculations are unchanged.
- Stage 34 accepts keyword-only `output_root` and `source_path` for
  single-file extraction. Original callers retain the original defaults.
  The explicit source override can copy a source already unpacked in place,
  as resolved by stage 36. L1 summary paths also accept external roots.
- Stage 36's original body is `build_fragment(out_root=OUT_ROOT)`.
  Stage 37's original body is `coverage_stats(out_root=OUT_ROOT)`.
  Their command wrappers use the old roots. Only their output-root references
  and printed relative paths change.
- Stages 25, 26, 28, 30, 35, 40 and 43 use ordinary module imports.
  The obsolete path loaders and stage 40's module-cache wrapper are removed.
  `_common/tests/test_mb_round2_quality.py` imports the packages directly.

The new directories have the same depth as `ncei/code/`; root calculations
still resolve to this repository. Scientific version labels, output table
schemas, log/error filenames and report destinations are retained.
No moved script still derives an output filename from its new module stem.
No moved-path consumer was found in `ncei/analysis/` or the JAMSTEC code,
so those scripts needed no P edits or changed-script isolated import check.
`_common/mbsystem.py` only changes its extraction-module docstring reference.

## Stage 43 remains one command

The script stays intact in `ncei.swath.quality_revision`. Its L1 rebuild,
L2 aggregation, record-exclusion lookup and file/cruise quality-table
functions remain reusable. The thirteen-cruise comparison also carries
shared diagnosis records, candidate sets and residual summaries for two
14-seamounts regions. Moving only those calls to `analysis/` would split
one retained run's intermediate state and parameter/resume contract.

The new `batch` command does not call the stage-43 regional analysis or read
its candidate lists. It uses `extract.merge_cruise`,
`trackline.file_cells.aggregate_track_file`,
`manifest_fragment.build_fragment` and `coverage.coverage_stats`.
Stage 43's arguments, record-exclusion behavior and isolated-output
restriction are unchanged. Historical result commands can be recovered from
`0a6cb1a`; the migration base also includes E2's helper refactor in `a5c2194`.

## Bounded check results

### Command and import checks

- 68 `--help` invocations passed: three package roots, every trackline/swath
  command and numeric alias, all downloader commands, and the new rank alias.
  No help invocation entered processing. Log: `/tmp/p_check/package_help.log`.
- 30 command modules imported through individual `python -c "import ..."`
  subprocesses from the repository root. Log:
  `/tmp/p_check/package_import.log`.
- 31 inline README command examples were parsed without executing their
  post-parse bodies. Summary: `/tmp/p_check/package_checks.json`;
  repeatable check script: `/tmp/p_check/package_checks.py`.
- The requested test modules passed, 49 tests:

```bash
TMPDIR=/tmp/p_check/test_tmp OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python -m unittest \
  _common.tests.test_mb_round2_quality \
  _common.tests.test_file_io \
  _common.tests.test_script_utils \
  _common.tests.test_r2_classifier \
  _common.tests.test_ncei_download
```

Final test log: `/tmp/p_check/unittest_final.log`. Downloader HTTP tests use
their local loopback fixture, not the active proxy or an external service.
Ranking computation and metadata fetching were not exercised. The final
`rank` implementation preserves the original calculation rather than
disabling it.

### Trackline and swath behavior

The retained checker `/tmp/p_check/behavior_check.py` uses a complete small
XYZ track, `vi47`, and the real HNRO05RR staging/raw input. Its output and
results are `/tmp/p_check/behavior.log` and
`/tmp/p_check/behavior_results.json`.

| Comparison | Observed result |
| --- | --- |
| `vi47`: standardize XYZ (03) | `points_raw`, 74 rows x 16 columns, exactly equal to production including dtypes and column order. |
| `vi47`: point QC (05) | `points_checked`, 74 x 22, exactly equal to production. |
| `vi47`: file cells (07) | `file_cells_1min`, 74 x 23, exactly equal to production. |
| HNRO05RR single-file extraction | `roger_revelle/HNRO05RR/sb2100_vf.19990601-0319p.mb41.gz`, key `f489eaee7dba18cb`: 19,221 x 9 staging values exactly equal to existing staging. |
| HNRO05RR `basic` L2 | 288 x 23; all 23 common columns exactly equal to `_runs/20261020T_l2_l3_first_batch/HNRO05RR/file_cells_1min/hnro05rr__mb41.parquet`. |
| HNRO05RR `basic_native_good` L2 | Complete 288 x 23 frame exactly equal to `_runs/20261021_quality_revision/HNRO05RR/file_cells_1min/hnro05rr__mb41.parquet`. |

The older `basic` product has two extra historical columns, `n_tracks` and
`n_surveys` (288 x 25). This comparison does not claim full-schema equality
with that older file; no columns were added to the current 23-column contract.
Both policies select 963,793 points on this cruise. The native-quality unit
tests cover cases where basic and native-good selection differ.

### Batch and resume checks

The complete HNRO05RR staging rebuild under `/tmp/p_check/swath_batch/`
produced 1,114,371 L1 points, 963,793 selected points, 288 L2 cells,
the source fragment and coverage statistics. `--resume` completed, with
all three L1/L2 parquet modification times unchanged.
Evidence: `batch_resume.log`, `resume_before.json` and `batch_checks.json`
under `/tmp/p_check/`.

The raw-extraction branch and `--all-staged` selector were exercised on a
one-file HNRO05RR manifest copied to `/tmp/p_check/batch_one_file_input/`:

```bash
python -m ncei.swath batch --all-staged --extract \
  --input-root /tmp/p_check/batch_one_file_input \
  --output-root /tmp/p_check/batch_one_file_extract
```

This produced 19,221 points, 15,571 selected points and 6 L2 cells, plus
source/coverage products. The extracted staging frame equals the original.
Log: `/tmp/p_check/batch_extract.log`. This temporary input root contains
only HNRO05RR; the production 94-cruise set was never selected.

Five rejection checks passed: missing output root, production root,
production cruise subdirectory, nonempty output without resume, and resume
with changed extraction parameters. They did not change the saved L1/L2
files. Log: `/tmp/p_check/batch_guards.log`.

## Documentation and remaining old references

E1's documentation was preserved and checked against the final commands:

| E1 document | P alignment |
| --- | --- |
| `README.md` | Static MGD77T processing is identified as trackline stages 39-40, not swath. Existing command/module references match. |
| `AGENTS.md` | Package invocation is documented; the sample alias includes its required sample size; empty parsers include global-grid stage 31 as well as swath 33/36/37. |
| `ncei/code/README.md` | The four frozen download scripts and processing-package destinations match; no further P edit needed. |
| `ncei/docs/README.md` | Command table matches; the production stage list excludes analyses 27/29; `--confirm-full` is scoped to commands accepting `--run-label full`. |
| `_common/README.md` | Shared-module references and package imports match; unpackaged legacy scripts retain their bootstrap convention. |
| `jamstec/multibeam/docs/README.md` | No moved NCEI module or command references; E1 content unchanged by P. |
| `jamstec/multibeam/docs/PIPELINE_PROCESSING_GUIDE.md` | No moved NCEI module or command references; unchanged. |

No unresolved E1 module/command references remain. Other allowed docs under
`ncei/docs/` and `docs/` now point to the new modules and runnable commands.
`docs/code_archive.md` has all 29 processing/download-planning moves.
Historical task records were not rewritten.

The requested old-path grep is saved in
`/tmp/p_check/remaining_old_paths.txt`. Remaining matches are:

- `.trellis/tasks/` task/result/inventory history.
- `docs/code_archive.md` historical path-resolution table.
- `ncei/archive/zhoushuai_processed_M/SOURCE.md`, the original PR-F execution
  provenance, outside this edit scope.
- `ncei/docs/step10_global_sb_products_report.md`, the recorded September
  global-grid command. A current package command is added beside it.
- `reports/ncei_multibeam_availability_20261019.md`, the dated pre-revision
  survey and old line-number reference, outside this edit scope.

No active Python/config/shell consumer retains a moved processing path.
The frozen download references and the archived SCS reference in
`_common/mbsystem.py` are intentional.

## Frozen state and retained issues

`ncei/code/` contains only:

```text
32_mb_round2_completeness.py
41_gzip_preflight.py
41_tier_a_gapfill.py
download_tier_a_round2.py
__init__.py
README.md
```

The four frozen scripts have no diff against HEAD. No existing product,
raw data, real download log, ranking list or `/tmp/tierB_gapfill/` file was
written by these checks. `git diff --check` passes.

The older basic-L2 extra columns are retained as historical schema evidence.
Existing `test_script_utils` tests emit `ResourceWarning` messages for
unclosed log handlers; all 49 tests pass, and that helper lifecycle is not
changed in this migration. Stage 43 and stage 37 retain their existing local
downstream-file dependencies. Their full regional analyses and the 94-cruise
rebuild were not run as part of this bounded migration.
