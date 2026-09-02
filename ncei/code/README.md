# ncei/code — script index

## Active pipeline lineage (numbered steps)

`01_build_trackline_source_manifest.py` through `24_true_crossover_audit.py`
are the living pipeline. Docs in `ncei/docs/` are organized by step number;
each step's report names the script that produced its products.

- 01–08: source manifest, singlebeam/xyz/mrar standardization, point and
  supplementary QC, 1′ cell aggregation and branch merge.
- 09–12: overlap residuals, cross-branch audit, quality-policy calibration,
  policy application.
- 13–22: validation cells, step08 global validation / publication products.
- 23–24: singlebeam per-track bias estimation and true crossover audit
  (task 09-02, currently scoped to the six downstream nested regions).

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
