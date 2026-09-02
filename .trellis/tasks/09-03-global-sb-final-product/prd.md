# Global track disposition, final SB product v2, and product docs

mode: production (applies the validated six-region rule globally; docs update)

## Decision this task must answer

Produce the consolidated global singlebeam product that downstream consumes:
every SB cell row carries its track's disposition and bias provenance, no
rows are deleted, and the six-region final control tables are regenerated
from it.

## Rule (already validated in task 09-03-sb-track-quality-rejection)

Apply step23-style corrections first, then judge post-correction
consistency. Dispositions: correct / keep_raw / revert_to_raw / reject /
flag_large_unapplied_bias. The one parameter that must be re-stated for
global use is the misfit threshold: use 3 x crossover NMAD computed per
10-degree tile where the tile has >= 100 crossover events; otherwise fall
back to the global branch-pair NMAD from the global audit report
(nc_x_nc 28.62 m, nc_x_xyz 30.40 m, xyz_x_xyz 24.27 m). Hard QC rejects:
backward-time tracks and zero-cell tracks, as in the six-region rule.

## Inputs (all existing)

- `ncei/derived/sb_track_bias_global/track_bias_summary.parquet`
- `ncei/derived/global_sb_crossover_audit/` (events + time-QC results)
- `ncei/derived/singlebeam/file_cells_1min_adjusted/`
- six-region reference: `ncei/derived/sb_track_quality_1min/`

## Deliverables

1. `ncei/code/30_global_sb_track_disposition.py` (new; reuse by import from
   scripts 23/24/28 and `_common/singlebeam_bias.py`).
2. `ncei/derived/sb_track_quality_global/track_quality.parquet`: one row per
   SB track with bias fields, misfit before/after, n_crossovers, QC flags,
   disposition, reason, threshold used.
3. `ncei/derived/singlebeam/file_cells_1min_final/`: mirrors
   `file_cells_1min_adjusted/` with corrections/reverts applied per track
   and added column `track_disposition`. NO rows deleted; consumers filter
   `track_disposition != 'reject'`.
4. Six-region final control tables
   `ncei/derived/sb_track_bias_1min/controls_mb_sb_final_<tile>.parquet`:
   MB rows identical to the other control tables; SB rows = final product
   filtered to `track_disposition NOT IN ('reject')`, control_source
   `singlebeam_final`.
5. Validation section in the report: for the six regions, compare the
   global-rule dispositions against the six-region tables from task 09-03;
   named tracks must match: odp130jr revert_to_raw, elt18/elt19
   flag_large_unapplied_bias, the hard-QC rejects stay reject. Any other
   differences explained by the NMAD-scale change must be listed.
6. README.md update: current product inventory (paths, one-line purpose,
   consumption rule), fix the dead `.trellis/spec/backend/` links, note the
   scs_confirmation archive location.
7. Update `docs/单波束数据质量处理与下游实验结论.md` sections 4-6 with the
   final products and the interpolation-test conclusion (SB valuable where
   MB is absent: pooled 1841 -> 731 -> 673 m; reject beats correct).

## Hard constraints

- Read-only on all existing derived products; everything additive.
- No GEBCO. No downstream evaluation data.
- Run from repo root with the analysis venv python.
- Plain Chinese in the docs, per project style rules; no insider jargon in
  README (explain each product in one sentence a new reader can act on).

## Acceptance criteria

- Global disposition counts reconcile with the track manifest.
- Final product row counts match `file_cells_1min_adjusted/` per track
  (nothing lost, only marked/valued-changed).
- Six-region named-track checks pass; control-table MB rows identical.
- README product section lets a new consumer find and correctly filter the
  final product without reading any code.

## Out of scope

- The downstream computation round (separate task in the 15 repo, after
  this one is reviewed).
- Outer evaluation. Second-round refinement of flagged tracks.
