# mb round2 quality revision (upstream repair from 14-seamounts)

## Question

The 14-seamounts project found that the round-2 swath chain (stages 34 -> 07 -> L2/L3 run scripts -> source audit) drops the native quality flag, miscounts L1 points, builds wrong source paths, truncates edge-candidate neighbourhoods and labels source-combination residuals as per-cruise residuals. HNRO14RR also has good-flagged soundings of 8.8-11.4 km where JAMSTEC gives about 2.4 km. Which results change once these are fixed, and is the HNRO14RR anomaly a source-record or a processing error?

Source record: `research/upstream_repair_prompt_20261021.md` (snapshot of
`/mnt/data2/06-Projects/14-seamounts/reports/04_ship_upstream_repair_prompt.md`).
Its "可直接发送给 Ship 仓库代理的 prompt" section is the full requirement list.

## Inputs

- L1 and staging: `ncei/derived/mb_round2/<cruise>/` (13 processed cruises; NT06-21 unprocessed, no UTC).
- Old L2/L3: `ncei/derived/mb_round2/_runs/20261020T_l2_l3_first_batch/`.
- Old source audit: `ncei/derived/mb_round2/_runs/20261020T_source_audit/`.
- JAMSTEC: `jamstec/multibeam/derived/cells_1min_qcfiltered/cells.parquet`.
- Strict layer: `ncei/derived/validation_cells_1min/strict_primary_multibeam_cells.parquet`.
- Candidates (read-only): `/mnt/data2/06-Projects/14-seamounts/outputs/20261019-vgg-pick-vs-ship-{japan-sea,izu-bonin}/candidates.csv`.

## Work split

| Owner | Scope | Output |
| --- | --- | --- |
| R1 (codex gpt-6-astra) | Requirement steps 1, 3, 4, 5: quality policy and lineage in 34/07, counts, source paths, single entry, coverage and per-cruise residuals, isolated rebuild | `ncei/derived/mb_round2/_runs/20261021_quality_revision/` |
| R2 (codex gpt-6-astra) | Requirement step 2: HNRO14RR file 119 diagnosis, read-only on code | `ncei/derived/mb_round2/_runs/20261021_hnro14rr_diagnosis/` |

Point key shared by R1 and R2: staging file stem + 0-based row position in that staging parquet (`staging_row`), plus `file_ordinal`. R2's affected-record list uses this key; R1's lineage columns must map to it.

If R2 finds a parser error, the fix goes back to R1 (owner of `34_mb_round2_extract_points.py`).

## Constraints

- Do not stop, restart or edit the Tier-B download (`/tmp/tierB_gapfill/supervise.sh` -> `ncei/code/41_tier_a_gapfill.py`), its catalog, `ncei/manifests/round2_download_log.parquet` or `ncei/raw_round2/`.
- Keep existing staging, L1/L2, old runs and reports; new results go only to the run directories above. Do not merge into production; do not modify 14-seamounts.
- Preserve the uncommitted edits already in `ncei/code/32_*`, `33_*`, `34_*` and `ncei/docs/step15_mb_round2_processing.md`.
- Old callers of `07_aggregate_file_cells_1min.py` keep their semantics.

## Completion

Result record `result.md` in this task plus the run-directory tables: commands, inputs, selection rule, code locations; old vs new point counts, valid cells, candidate core/annulus/sector coverage, per-(cruise, cell) residuals, HNRO14RR handling and affected candidates; which candidates can proceed to summit/flank depth measurement.

## State

- 2026-10-21: task created; R1 dispatched as paseo agent 4a5f0e87 (codex gpt-6-astra, full-access), R2 as 24542cc2 (same). Workspace wks_2e2040b3fe9c7d48.
- 2026-10-21 R1 progress: RR1412 761d2c6f1c51988d confirmed 189,648 points = good 163,975 + flagged 25,673, all pass basic, null/unknown 0. Lineage columns kept: filekey, file_ordinal, point_index_in_file, staging_row, native_quality_state. Old extraction-manifest relpaths all lack the ship level; R1 resolves `platforms_tree/*/<cruise>` and adds `source_relpath` in the isolated manifest (filekey unchanged). Policy `basic_native_good`; merged NCEI depth stays median of per-cruise medians; entry supports `--exclude-records`.
- 2026-10-21 R2 progress: the 34 HNRO14RR points are file 119 pings 77-93, beams 30-37, 2000-02-03 23:22:05.994-23:28:04.020 UTC. Raw ASCII DR depths are already 8767-11414 m with two-way travel times 16.633-19.706 s; re-decoding files 117-121 (417,364 rows) matches staging in depth, time, position and native good; positions rebuilt from navigation + beam offsets agree to <5.1e-11 deg. Extraction/join error in 34 excluded; no parser change needed for these points. Anomaly continues along outer port beams; record range still being delimited. File 117 has 3 source records whose ASCII depth field overflows to 6 digits (malformed, listed separately, not corrected).
