# Result: SB crossover network constant-offset prototype

## Command

Run from `/mnt/data2/00-Data/ship`:

```bash
/mnt/data2/06-Projects/15-swot_feature_physics_bathy/.venv/bin/python \
  ncei/code/27_sb_crossover_network_bias_1min.py --overwrite
```

The solve is deterministic and unweighted. Inputs are the six existing
`ncei/derived/true_crossover_audit/crossovers_<region>.parquet` tables and
`ncei/derived/sb_track_bias_1min/track_bias_summary.parquet`. GEBCO is not read.

## Evidence

The common leave-one-crossover-out sample contains 12,825 events. The pooled
comparison from
`ncei/derived/sb_network_bias_1min/comparison_summary.parquet` is:

| variant | held-out events | median absolute residual (m) | residual NMAD (m) |
| --- | ---: | ---: | ---: |
| raw | 12,825 | 28.39 | 42.14 |
| Step 23 | 12,825 | 23.86 | 35.35 |
| network | 12,825 | 61.64 | 90.80 |

All six regional graphs form one component each. Every component contains at
least one applied Step 23 anchor, so all 240 regional track rows are in anchored
components and none are in free components. Four of 12,829 input events are
excluded from all three variants: three involve a single-crossover track, and
one held-out edge makes the relevant offset difference unidentifiable.

For `elt18` in `lon021_lat010`, the network assigns -969.91 m (standard error
84.51 m), consistent in direction and approximate scale with the previously
documented -1,247 m Step 23 candidate. Its event-level median absolute held-out
residual falls from 1,032.77 m raw to 770.95 m, so a constant offset improves
but does not explain most of the remaining crossover difference.

For `odp130jr` in `lon068_lat018`, the predeclared anchor rule fixes the network
offset at its applied Step 23 value of -44.00 m. It is therefore not an
independent network estimate. The median absolute held-out residual rises from
3.91 m raw to 44.74 m for network (44.42 m for Step 23), consistent with the
prior finding that its 141 crossover events are centered near zero and do not
support the -44 m correction.

## Decision

Keep Step 23. The unweighted network does not beat either control on the two
predeclared pooled metrics and is worse in every region on both metrics relative
to at least the better control. This result does not support globalizing the
network method in its present form.

## Outputs

- `ncei/code/27_sb_crossover_network_bias_1min.py`
- `ncei/derived/sb_network_bias_1min/track_offsets_<region>.parquet`
- `ncei/derived/sb_network_bias_1min/components.parquet`
- `ncei/derived/sb_network_bias_1min/heldout_residuals_<region>.parquet`
- `ncei/derived/sb_network_bias_1min/comparison_summary.parquet`
- `ncei/derived/sb_network_bias_1min/manifest.json`
- `ncei/docs/step10_sb_network_bias_report.md`

## Research check

- Executes: yes, using the required Python executable from the repository root.
- Shapes and units: six components, 240 regional track rows, and exactly three
  variant rows per event; offsets and residuals are metres.
- NaN/Inf: absent from included residuals, summary metrics, offsets, and standard
  errors. Excluded residuals are explicitly NaN.
- Result provenance: the report and manifest point to the outputs from the
  result-producing invocation above.

