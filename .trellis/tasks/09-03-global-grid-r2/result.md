# Result

## Execution

From `/mnt/data2/00-Data/ship`:

```bash
/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python ncei/code/31_build_global_grid_1min.py
```

The specification's enumerated output list contains ten columns despite calling
it a nine-column structure. All enumerated columns were retained:
`cell_id`, `lon_bin`, `lat_bin`, `lon_center`, `lat_center`, `depth_m`,
`source_layer`, `sb_median_depth_m`, `n_tracks_sb`, and `round`.

## Product

- Path: `ncei/derived/global_grid_1min_r2/`
- Total unique cells: 15,245,229
- `multibeam_strict`: 2,398,774
- `singlebeam_final`: 12,846,455
- MB/SB overlap cells: 489,958
- Accepted SB cells before MB precedence: 13,336,413
- Partitioning: 18 hive latitude bands, `lat_band_10deg=-90` through
  `lat_band_10deg=80`
- Manifest: `ncei/derived/global_grid_1min_r2/product_manifest.json`, containing
  5,366 per-input-file SHA-256 values, generation time, command, merge rule,
  counts, columns, and spot-check evidence

Strict MB supplies every strict-MB primary depth. A non-rejected final-SB median
fills cells without strict MB. Overlap cells retain that SB median and track
count in diagnostic columns. No GEBCO or `regional_mrar` data were read.

## Focused check

- Output row count equals the input cell union; `cell_id` is unique.
- The strict-MB source-layer count equals all 2,398,774 accepted strict-MB cells.
- The SB-only count equals accepted SB cells minus the 489,958 overlaps.
- Written partition metadata sums to 15,245,229 rows and matches the manifest.
- Five fixed-seed strict-MB samples equal their MB depths.
- Five fixed-seed overlap samples equal their MB depths and have non-null SB
  diagnostics.
- Five fixed-seed SB-only samples equal their SB median and carry
  `source_layer=singlebeam_final`.

An initial generated copy placed the single cell at latitude +90 degrees in a
`lat_band_10deg=90` directory. Existing repository code clips 10-degree latitude
bands to [-90, 80]. That task-owned copy was deleted and fully regenerated with
the established convention; the retained product has no band 90.

No Git commit was created. The concurrent `ncei/tracklines_m77t_round2/`
download directory was not read or modified.
