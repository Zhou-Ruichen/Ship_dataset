# Result

## Execution

From `/mnt/data2/00-Data/ship`, using
`/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python`:

```bash
/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python ncei/code/25_global_singlebeam_track_bias.py
/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python ncei/code/26_global_singlebeam_crossover_audit.py
```

## Outputs and observations

- `ncei/derived/sb_track_bias_global/track_bias_summary.parquet` contains 1,647
  tracks with strict-MB support: 83 applied, 115 thin evidence, and 1,449 not
  significant under the retained `n >= 5` and `|bias| >= 2 * NMAD` gate.
- `ncei/derived/singlebeam/file_cells_1min_adjusted/` contains 5,365 files and
  17,294,849 rows. Every output filename and per-file row count matches the
  corresponding input product.
- `ncei/derived/global_sb_crossover_audit/crossovers.parquet` contains
  5,205,339 crossover events over 260,976 track pairs.
- The independent same-bbox rerun reproduces all six retained step 09 event
  counts: 1,276; 1,286; 2,575; 1,006; 1,860; and 4,826.
- `ncei/figures/coverage_global/` contains four fixed-global-window source maps
  and one combined multibeam-versus-singlebeam figure.
- `ncei/docs/step10_global_sb_products_report.md` reports the bias, crossover,
  coverage, source-label mapping, and downstream-consumption rules from the new
  outputs.

The PRD calls the upstream depth field `depth_median_m`; the existing product
uses `median_depth_m`. The adjusted product preserves and adjusts the actual
field name, and the report documents the discrepancy.

## Research Check

- Executes: yes; the two result-producing commands above completed from the
  repository root with the designated interpreter.
- Shapes/units: ok; adjusted per-file and total row counts match the inputs,
  required identities are unique, coordinates are within global longitude and
  latitude bounds, and depth is metres positive down.
- NaN/Inf: absent from required bias and crossover numeric fields.
- Result provenance: counts and report values were read from the outputs created
  by those invocations; both output roots contain product manifests.
- Findings: the global crossover audit subdivides dense 10-degree tiles and uses
  endpoint margins. Directly cropping the adaptive global event table did not
  reproduce five of the six regional counts, although rerunning the exact same
  5-degree bboxes with the imported step 09 machinery reproduced all six. The
  global event enumeration is therefore sensitive to adaptive tile boundaries;
  the six-region result is a same-bbox reproducibility check, not proof that a
  crop of the global event table is identical to a standalone regional audit.

No GEBCO, `regional_mrar`, or downstream evaluation data were read. Existing
derived products and manifests were not rewritten.
