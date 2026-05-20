# Research: Step 04 1-arcmin aggregation design audit

- **Query**: Audit Step 03A + 03B outputs before writing Step 04A/B aggregation code. Confirm primary-input selection, surface double-counting risk, compute per-cell distribution stats per source branch, recommend output schema, decide proceed-vs-revise.
- **Scope**: internal (no external web search)
- **Date**: 2026-05-20
- **Owner**: trellis-research subagent (no code modification; read-only audit + small TSV outputs + one markdown report)
- **Active task**: `.trellis/tasks/05-11-singlebeam-integration`

## Findings

### Output artifacts

| Path | Description |
|---|---|
| `ncei/docs/step04_aggregation_design_audit.md` | **Primary deliverable** — full 8-section audit doc including final proceed-to-code recommendation + 3 guardrails. |
| `ncei/derived/aggregation_design_audit/branch_summary.tsv` | Per-branch full-corpus counts + cross-branch cell overlap. |
| `ncei/derived/aggregation_design_audit/cell_distribution_percentiles.tsv` | Per-cell distributions (`n_points_pass`, `n_unique_triples`, `dup_ratio`, `depth_iqr`) per branch. |
| `ncei/derived/aggregation_design_audit/f10_89_cp_summary.tsv` | f-10-89-cp Step 03A+03B flag breakdown. |
| `ncei/derived/aggregation_design_audit/f10_89_cp_cells.tsv` | Full 495-cell per-cell stats for f-10-89-cp pass-basic points. |

### Headline numbers

| Branch | Tracks | Points pass | Unique 1-arcmin cells | Track-cell pairs | Overall dup_ratio |
|---|---:|---:|---:|---:|---:|
| singlebeam (nc + xyz-sb) | 5,365 | 77,445,882 | 14,611,054 | 17,294,849 | 0.0507 |
| multibeam_ncei (xyz-mb) | 17 | 37,799,943 | 5,960 | 6,329 | **0.6947** |
| regional_mrar (M.rar 3 quadrants) | 3 | 113,356,269 | 9,019,383 | 9,023,641 | 0.0002 |
| union (3 branches) | 5,385 entries | 228,602,094 | 21,743,065 | — | — |

Cross-branch overlap: SB ∩ M.rar = 1.89M cells; MB ∩ M.rar = 4,015; MB ∩ SB = 4,127. M.rar inter-quadrant overlap = 129 boundary cells out of 9.02M (effectively a partition).

### Final recommendation

**PROCEED to Step 04A code as designed**, with three explicit
guardrails in the implementation:

1. **Iterate from the manifest, not the filesystem.** Drive Step 04A
   from `manifest[use_for_primary_bathymetry | source_priority=='regional']`,
   dedup by `output_path`, partition M.rar internally by `track_id`.
   This eliminates three concrete double-counting pitfalls — see
   `step04_aggregation_design_audit.md` §1.3.
2. **Emit both `n_points_pass` and `n_unique_triples` per (track, cell).**
   Multibeam dup_ratio of 0.69 (per-cell p99 = 0.92) makes
   `n_unique_triples` essential for cross-branch weighting; emitting
   both at Step 04A keeps Step 06b/07 unblocked without a 240M-row
   rescan.
3. **Add a `manual_review_flag` column** initialized from Step 03B
   supplementary manifest (depth_anomaly, jump-density tracks like
   f-10-89-cp, bbox-only divergent intersect pairs).

### f-10-89-cp recommendation

Keep in primary aggregation with `manual_review_flag=True`. The 1,413
pass-basic points (out of 53,637 raw) carry plausible bathymetry
depths (1,250–4,968 m), span 495 cells with normal per-cell IQR
(mean 35 m), and the intersect divergence flag is a bbox-shape
artifact (Step 03B §D3), not a true source conflict. Excluding the
track would discard 495 cells of central-Pacific singlebeam coverage.
Conservative alternative (`primary_with_review` sub-bucket at Step
06b) is documented but deferred to Step 06b authors.

### Key premise corrections in the original task description

1. **M.rar is NOT in the multibeam branch.** It lives in its own
   `regional_mrar` source branch (`source_priority='regional'`,
   `ncei/derived/regional_mrar/points_checked/`). Task description's
   "use bathymetry_points.parquet only (multibeam branch)" was
   off; the right framing is "its own regional branch, parallel to
   ncei multibeam but separate".
2. **M.rar branch DOES have a `points_checked` stage** (113.36M-row
   parquet exists at `ncei/derived/regional_mrar/points_checked/bathymetry_points.parquet`,
   Step 03A schema). Task assumption that "M.rar has no points_checked
   stage" was outdated. Step 04A should consume the Step 03A copy
   (uniform with sb/mb branches), not re-read the PR-F-cleaned copy
   directly.
3. **The 1,850 intersect `__xyz.parquet` files do not exist on disk.**
   Step 03A simply did not write them (manifest `output_path=NULL` for
   supplementary entries). The `__xyz` parquets exist only for
   `xyz_only` tracks (3,532 of them, of which 17 are mb-routed).
   Effectively no double-count risk from filesystem glob today, but
   §6 guardrail #1 ensures any future re-materialization can't break
   Step 04A.

### Sentry / AUV dominance — quantified

Worst MB cell observed: `sentry421` cell with **1,224,832 points** of
which only **78,387 are unique triples** (dup_ratio 0.94). Under
`n_points_pass` weighting in any cross-branch product, this single AUV
cell would carry ~245,000× the weight of a typical singlebeam cell
(p50 = 1 pt). Under `n_unique_triples`: 16,000×. Under `log(n+1)`:
~6×. Step 04A doesn't pick the weighting but must emit columns that
support all three.

### Files Found (relevant existing artifacts)

| Path | Description |
|---|---|
| `ncei/manifests/bathymetry_entry_manifest.parquet` | 7,403-row Step 03A manifest, 20-col, declares routing |
| `ncei/manifests/bathymetry_entry_manifest_supplementary.parquet` | 7,403-row Step 03B manifest, 26-col, adds dup/jump/zero-depth attributes |
| `ncei/manifests/intersect_divergence_audit.parquet` | 1,850-row nc-vs-xyz pairwise comparison, 19-col |
| `ncei/derived/singlebeam/points_checked/` | 5,365 files (1,850 `__nc` + 3,515 `__xyz`) |
| `ncei/derived/multibeam/points_checked/` | 17 files, all `__xyz`, R2-classified mb (Sentry + Atlantis + 5 borderline) |
| `ncei/derived/regional_mrar/points_checked/bathymetry_points.parquet` | 1 file, 113.36M rows, 3 quadrants partitioned by `track_id` column |
| `ncei/archive/zhoushuai_processed_M/bathymetry_points.parquet` | PR-F-cleaned copy (sibling, 113.36M rows but 1.41 GB vs Step 03A's 1.44 GB — minor schema diff) |
| `_common/r2_classifier.py` | PR-D classifier — already-canonical thresholds |
| `.trellis/spec/backend/pipeline-design-decisions.md` | §3 file-balanced median, §4 1-arcmin cell, §5 two-tier quality, §10 R2, §12 depth clip |

### Code Patterns (relevant)

- Step 03A point-check schema (22-col): `source_type, track_id, point_index_in_track, time, lon_raw, lat_raw, lon, lat, depth_raw, depth_m_positive_down, elev_m, gobs, faa, source_completeness, instrument_class_pred, standardization_version, valid_lon, valid_lat, valid_depth_pos, valid_depth_max, valid_core_fields, point_check_pass_basic`. Identical across sb/mb/mrar branches — uniform Step 04A consumer.
- Cell binning formula per design decision #4:
  `lon_bin = floor((lon + 180) / (1/60))`, `lat_bin = floor((lat + 90) / (1/60))`,
  `cell_id = f"1min_{lat_bin}_{lon_bin}"`.
- `n_unique_triples` semantics (Step 03B): exact float equality on `(lon, lat, depth_m_positive_down)` per track. Step 04A's per-cell variant uses the same triple definition restricted to in-cell rows.

### Related Specs

- `.trellis/spec/backend/pipeline-design-decisions.md` — load-bearing constraints (§3, §4, §5, §10, §12). No spec changes required by this audit; the proceed-to-code recommendation respects all 12 decisions.
- `.trellis/spec/backend/quality-tiering.md` — exact A/B/C thresholds; out of scope for this audit but cited in §5 first non-goal.

### Caveats / Not Found

- Per-cell `n_points_pass` percentiles for M.rar are computed from a 4%
  sample (4.5M of 113.36M rows). The full-corpus per-cell distribution
  was not computed (would need a streaming hash-table groupby). The
  full mean (12.57 pts/cell) is from exact streaming; the shape of the
  per-cell distribution scales by ~25× for absolute values.
- Step 04A's actual code is not authored here — only the schema and
  iteration discipline are recommended. Implementation belongs to the
  next Step 04A task.
- The audit did NOT touch / modify any of `ncei/code/01..06_*.py`. The
  one new script written is `.trellis/tasks/05-11-singlebeam-integration/research/_audit_task2.py`,
  which is an audit driver, not a pipeline script.
- A potential future cleanup (out of scope): adjust the manifest writer
  so the 3 mrar rows carry an `output_path_shared=True` sentinel — see
  audit doc §7 anomaly #1.

### External References

None used. Audit was purely internal.

### Runtime

- Task 2 sampled pass: 84.6 s
- f-10-89-cp targeted pass: <1 s
- M.rar full cell-count: 19.1 s
- SB + MB full cell-count: 59.3 s
- Cross-branch overlap: 89.0 s
- **Total wall time: ~3.5 min on `/mnt/data2`**, well under the 10-min budget per task.
