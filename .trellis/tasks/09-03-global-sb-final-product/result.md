# Result

## Execution

From `/mnt/data2/00-Data/ship`:

```bash
/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python ncei/code/30_global_sb_track_disposition.py --overwrite
```

The retained round-2 manifest records generation time, command, input and output
paths, input trackline-manifest SHA-256, threshold rule, counts, units, and the
absence of randomness.

## Products

- `ncei/derived/sb_track_quality_global/track_quality.parquet`: 5,533 unique
  manifest singlebeam track IDs. Dispositions: 4,764 `keep_raw`, 711 `reject`,
  32 `correct`, 23 `revert_to_raw`, and 3 `flag_large_unapplied_bias`.
- `ncei/derived/singlebeam/file_cells_1min_final_r2/`: 5,365 files and
  17,294,849 rows; no input row was removed.
- `ncei/derived/sb_track_bias_1min/controls_mb_sb_final_<tile>.parquet`: six
  regional control tables with `singlebeam_final` SB rows.
- `ncei/derived/sb_track_quality_global/six_region_validation.parquet`: 247
  regional reference rows, 199 matching and 48 changed under global evidence.
- `ncei/docs/step10_global_sb_final_product_report.md`: global counts, threshold
  method, six-region comparison, differences, and consumption rule.

The named checks pass: `odp130jr` is `revert_to_raw`; `elt18` and `elt19` are
`flag_large_unapplied_bias`. Every six-region hard-QC rejection remains
`reject`. The named local decisions and the earlier regional hard-QC findings
are retained when global aggregation alone would change them.

## Focused check

- The quality row count equals the 5,533 unique singlebeam track IDs in the
  trackline manifest.
- Every adjusted input filename has one round-2 output with the same row count.
- Every output depth equals its adjusted input, except an applied-bias track
  disposed as `revert_to_raw` or `flag_large_unapplied_bias`, where the stored
  bias is added back exactly.
- The final product contains 17,294,849 rows and a constant disposition within
  each track file.
- All six final control tables contain MB rows exactly equal to their
  `controls_mb_only_<tile>.parquet` inputs.
- The round is `r2`; the recorded input-manifest SHA-256 is
  `fb58e401ab483f17ed54d9a7edcc2fe39406102db10dd3caf683737cb6f8619c`.

## Deviations and interpretation

- The PRD defines per-10-degree-tile thresholds but not how one global track
  spanning several tiles is reduced to one decision. The implementation applies
  each event's own tile or branch-pair fallback threshold, then rejects when the
  median `abs(post residual) / event threshold` exceeds 1. The table retains the
  median event threshold as an explanatory field.
- The global audit contains nc and xyz representations for some shared track
  IDs. Disposition evidence is restricted to the representation selected by the
  adjusted cell product, so the supplementary twin cannot change the decision.
- The interpolation result 1,841 -> 731 -> 673 m comes from the earlier six-region
  control tables. It establishes SB data value under that comparison, but it is
  not a performance result for the new round-2 controls; the docs state this.

No GEBCO, `regional_mrar`, downstream evaluation data, or existing derived
product was modified. No Git commit was created.
