# ncei/code — script index

## Active pipeline lineage (numbered steps)

`01_build_trackline_source_manifest.py` through `24_true_crossover_audit.py`
are the living pipeline. Docs in `ncei/docs/` are organized by step number;
each step's report names the script that produced its products.

- 01–08: source manifest, singlebeam/xyz/mrar standardization, point and
  supplementary QC, 1′ cell aggregation and branch merge.
- 09–12: overlap residuals, cross-branch audit, quality-policy calibration,
  policy application.
- 13: validation cells.
- 23–24: singlebeam per-track bias estimation and true crossover audit
  (task 09-02, currently scoped to the six downstream nested regions).
- 25–26, 28, 30: global singlebeam production chain — per-track bias (25),
  global crossover audit (26), track disposition (28), and global
  disposition + final cells `file_cells_1min_final_r2` (30; task
  09-03-global-sb-final-product).
- 31: round-2 merged global 1-arcmin grid `global_grid_1min_r2`
  (spec §2 product; strict mb wins, non-rejected final sb fills).
- 32–37: `raw_round2` swath-cruise ingestion (task step15): completeness
  audit (32), format census (33), L1 point extraction via the sealed
  mbsystem environment's mblist U3/U0 join (34; imports
  `scs_confirmation/scs_v2_stage_c_processing._raw_from_object`),
  L2 1-arcmin cells via `07.aggregate_track_file` (35), standalone L3
  source-manifest fragment (36; production manifest NOT touched), and
  read-only coverage statistics vs the strict layer (37).
- 38: MBBDB increment download-value ranking and A/B/C order lists
  (task step16; catalog metadata fetch + pure computation). Dependencies:
  pandas/numpy/pyarrow, the local `ncei/manifests/round2_download_log.parquet`
  and `ncei_catalog_gap_2026-09.parquet`, network only for catalog metadata
  (127.0.0.1:2085 proxy).

## Archived one-off chains

`scs_confirmation/` holds the 37-script SCS/TN352 sealed-confirmation audit
chain (audit_*, verify_*, discover_*, prepare_*, acquire_*, finalize_*,
freeze_*, authorize_*, process_*, plus the scs_tn352/scs_v2 shared modules).
It was moved here on 2026-09-02 from the flat `ncei/code/` listing; reports
and journals written before that date reference the old flat paths
(`ncei/code/verify_scs_*.py`). Package imports were rewritten to
`ncei.code.scs_confirmation.*` and repo-root path computation was updated;
tests live in `_common/tests/scs_confirmation/`. Run any of them from the
repo root exactly like the pipeline scripts:

```bash
python ncei/code/scs_confirmation/verify_scs_v2_stage_c_processing.py [args...]
```

`__init__.py` at this level makes `ncei.code` a package; both conventions
(file execution and package import) are supported.

## Moved to `ncei/analysis/`

The frozen Step 08 validation pack (14–22), the six-region network-bias
prototype (27) and the interpolation holdout evidence run (29) moved to
`ncei/analysis/` on 2026-10-21 (commit after `bc4cd36`); reports and
manifests written before that date reference the old `ncei/code/` paths.
See `docs/code_archive.md` for the old-path → new-path table.
