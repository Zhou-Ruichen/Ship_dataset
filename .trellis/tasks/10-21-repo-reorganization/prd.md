# repository reorganization: core download and processing code

## Goal

A reader opening the repo should find, in one place each, the code that downloads ship data and the code that turns it into the released products (JAMSTEC multibeam cells, NCEI singlebeam final cells, round-2 swath L1/L2/L3, global grid r2). One-off audits, finished confirmation chains and their tests are archived or deleted. Kept code is modular, readable, and commented in English.

## Settled decisions

- Phase 1 is a read-only inventory; layout and per-file disposition are decided from it, then executed by area with one owner per area.
- Tracked code that is no longer used is removed from the working tree and listed in a code-archive index with its purpose, the products or reports it produced, and the last commit containing it (`git show <commit>:<path>` restores it). Untracked code is moved, not deleted.
- Code that produced a reported or released number is only removed once a result record names a commit containing it.
- Refactors must not change outputs: core scripts are checked on a small input before/after.

## Frozen while the Tier-B download runs (days to weeks)

Do not move, rename or edit:

- `ncei/code/41_tier_a_gapfill.py` (re-invoked every loop by `/tmp/tierB_gapfill/supervise.sh`)
- `ncei/code/download_tier_a_round2.py`, `ncei/code/41_gzip_preflight.py`
- `ncei/derived/mbbdb_value_ranking/order_tier_{A,B_queue}.tsv`
- `ncei/manifests/round2_download_log.parquet` and its `.bak-*` files
- `ncei/raw_round2/`, `/tmp/tierB_gapfill/`

Files owned by task `10-21-mb-round2-quality-revision` (`ncei/code/34_*`, `07_*`, `36_*`, `37_*`, the round-2 run scripts) are reorganized only after that task's code lands.

## Unified downloader (user request 2026-10-21)

User: upgrade where needed, merge where it makes sense, turn the download code into one downloader where feasible; skip parts that are hard or not worth it; keep code concise and readable.

Current download code is scattered:

| Path | Role | Status |
| --- | --- | --- |
| `ncei/code/41_tier_a_gapfill.py` | platforms_tree inventory -> diff -> download -> merge | active, frozen (Tier-B loop) |
| `/tmp/tierB_gapfill/supervise.sh` | bash loop around 41 with a 400 GB disk floor | active, outside the repo |
| `ncei/code/download_tier_a_round2.py` | first tier-A downloader | superseded by 41 (silent-skip bug documented in 41) |
| `ncei/code/41_gzip_preflight.py` | `gzip -t` fail-closed check | post-download verification |
| `ncei/code/32_mb_round2_completeness.py` | remote listing vs disk completeness | duplicates 41's directory listing |
| R2R (`r2r`, 245 log rows) and static MGD77T (`m77t_static`, 1,418 rows) downloaders | | code lost (not in repo or /tmp); URLs and sha256 survive in the download log |

Target: package `ncei/download/`, run from repo root as `python -m ncei.download <command>`, sibling of the processing code in `ncei/code/`. Commands cover inventory, diff, fetch, merge into `ncei/manifests/round2_download_log.parquet`, verify (gzip + completeness), and a `run` loop with the disk floor that replaces `supervise.sh`. Work-directory files and log schema stay compatible with 41 so a stopped Tier-B job can resume under the new tool. Old scripts are removed only after the Tier-B loop has ended and the new tool is checked; the switchover itself needs the user's go-ahead.

Checks must not write to `ncei/raw_round2/` or the real download log: diff on a copy of `/tmp/tierB_gapfill/trees.json` must reproduce 41's file count; fetch of a few already-logged files into a scratch directory must reproduce their sha256; merge on a copy of the log must match 41's merge.

## Phases

1. Inventory (glm-5.3, read-only) -> `research/code_inventory.md` + `research/code_inventory.tsv`.
2. Layout decision by the main agent from the inventory.
3. Execution by area (jamstec / ncei singlebeam / ncei round-2 + download / _common, tests, docs), then README and docs path updates.

## State

- 2026-10-21: task created; inventory dispatched as paseo agent e22e97b7 (pi glm-5.3), output under research/.
- 2026-10-21: pre-reorganization checkpoint `bc4cd36` pushed to origin/main (six themed commits on top of 45eedb6). Use it as the "last commit containing" reference in the code-archive index. R1's files (07, 34, 36, step15, new entry and test) are committed separately once R1 finishes; inventory research files are committed when the inventory is final.

## Layout decision (2026-10-21, from research/code_inventory.*)

Dependency tracing corrected the inventory's analysis labels: ncei 12 reads 10/11 outputs, 07 reads 06, 13 reads 04's regional_mrar cells, 30 reads 23/24/28; jamstec 06b reads 06a, which reads 05. Those stay in the production chain.

- `ncei/download/`: new unified downloader (see above).
- `ncei/code/`, `jamstec/multibeam/code/`: production chain only. Stage numbers unchanged; gaps are fine.
- `ncei/analysis/`: 14-22 (Step 08 v1.0 validation), 27 (network bias, read by nothing else), 29 (interpolation holdout evidence).
- `jamstec/multibeam/analysis/`: 06d, 08, 09 x2, 10, 10b, 11, plot_multibeam_figures.
- Same directory depth, so `Path(__file__).resolve().parents[N]` repo-root lookups stay valid.
- Archive (git rm + `docs/code_archive.md` naming commit bc4cd36): `jamstec/multibeam/code/05_cleanup.sh`, `scripts/refactor/rewrite_paths.py`, `ncei/code/42_backfill_product_manifests.py` now; the SCS confirmation chain, its 14 tests and `_common/scs_v2_stage_c1_oracle.py` after `34` stops importing `scs_v2_stage_c_processing.py`; `download_tier_a_round2.py`, `41_tier_a_gapfill.py`, `41_gzip_preflight.py`, `32_mb_round2_completeness.py` at the downloader switchover.
- Duplicated helpers (atomic writes, logging setup, markdown tables, error TSV, sha256, nmad) move into `_common/` for production scripts only, identical bodies only. Analysis scripts are moved, not edited. cell_id implementations are reported, not unified.

Owners: E1 (moves, archive, doc references), E2 (helper consolidation in production scripts), D (downloader, starts when an astra slot frees). Phase 3b after R1 lands: decouple 34 from the SCS module, archive the SCS chain, consolidate helpers in R1's files. Phase 3c: README and docs overview.
- 2026-10-21: E1 dispatched as paseo agent adaa7916 (pi glm-5.3), E2 as b9d19611 (pi glm-5.3). D waits for an astra slot (R2 still running).
- 2026-10-21: D dispatched as paseo agent 81e077a3 (codex gpt-6-astra, full-access) after R2 finished.
- 2026-10-21: E1 done and committed (7a6450c): 19 analysis scripts moved, 3 tools archived, docs/code_archive.md created, 58 paths. Old paths remain only in the workspace journal, .trellis task records, SCS configs and on-disk product manifests (historical). jamstec 07 carries one E1 title-line edit, committed with E2.
- 2026-10-21: E3 dispatched as paseo agent f38784db (pi glm-5.3): decouple 34 from scs_v2_stage_c_processing.py, archive the SCS chain, tests, oracle and SCS-only configs. Helper consolidation in round-2 files (07, 34-37, 43) goes to E2 after E2's first pass.
- 2026-10-21 incident: `ncei/code/36_*` has no argparse; `--help` runs started by the main agent and by E3 entered a full run. Both killed; `ncei/derived/mb_round2/mb_round2_source_manifest_fragment.*` unchanged (mtime 2026-09-13). All agents told: check argparse/`__main__` first, import-check via `importlib` exec from /tmp with `python -I`; D told not to rerun 32/41_gzip_preflight (they rewrite derived audit outputs).
- Import fact: `python <script path>` does not put the repo root on sys.path (no PYTHONPATH, no .pth). 01/23/25 already imported `_common` without bootstrap before this reorganization; E2's edits extend this to 26 scripts. E2 told to add the 36/40 bootstrap (`REPO_ROOT = ...parents[N]`; `sys.path.insert(0, str(REPO_ROOT))`). AGENTS.md's "cwd is on sys.path" claim is wrong for path invocation; fix in phase 3c.
- 2026-10-21: D finished; downloader committed. Package ~820 lines (inventory/transport/download/log/verify + CLI); 16 tests OK (main agent re-ran); formal completeness/gzip outputs and the real log untouched. Switchover command and checks in research/downloader_check.md; switchover awaits the user's go-ahead after the Tier-B loop ends or is stopped.
- 2026-10-21 E2 done: `_common/file_io.py` (atomic writers, write_errors_tsv) and `_common/script_utils.py` (setup_logging, markdown_table, ensure_columns); 26 production scripts -904/+195 lines; repo-root bootstrap added to every script importing `_common`; local copies kept where behaviour differs (jamstec setup_logging, several markdown_table, compute_lat_band dtypes, logger-aware writers). cell_id: jamstec 04a and ncei 07 share the `1min_<lat>_<lon>` string; analysis 29 uses its own integer key. Main agent: 49 tests OK, 31 scripts isolated-import OK from /tmp, script 40's borrowed functions present.
- 2026-10-21 E3 done: `_common/mbsystem.py` (451 lines: mblist adapter, raw_from_object, raw schema) replaces 34's importlib load of the SCS module; 62 tracked files removed (SCS chain 21,824 lines, its tests 3,500, oracle 166, 7 SCS configs) and indexed in docs/code_archive.md. HNRO05RR (mb41) and AR40 (mb58) re-extracted in /tmp identical to production staging.
- Next: E2 round-2 helper pass (07, 34-37, 43) after R1's union run; phase 3c docs by E1.
- 2026-10-21: E1 re-prompted for phase 3c (README, AGENTS.md execution convention and --help rule, ncei/code/README.md stage index, ncei/docs/README.md status grouping, _common/README.md). E2's round-2 helper pass (07, 34-37, 43) waits until R1's union run finishes, so code under a running job does not change.

## Processing packages (user request 2026-10-21: "做成下载器和计算器的形式，不再是满屏的脚本")

Decision: turn the NCEI processing scripts into packages run like the downloader (`python -m ncei.<package> <command>`), one package per data line:
- trackline chain (stages 01-31 production, plus 39/40 MGD77T static) -> e.g. `ncei/trackline/`;
- round-2 swath chain (33-37, 43) -> e.g. `ncei/swath/`, with one command that processes a list of downloaded cruises end to end;
- 38 (MBBDB value ranking) is download planning -> a command in `ncei/download/`;
- 32, 41_gzip_preflight, 41_tier_a_gapfill, download_tier_a_round2 are already replaced by `ncei.download` and are archived at the switchover.
Reasons: one entry per data line; `python -m` puts the repo root on sys.path, so the per-script sys.path bootstrap and the importlib-by-file-path loading (35, 40, 43 load 01/03/05/07) become ordinary imports; the swath chain has immediate use (see below).
Not packaged: JAMSTEC multibeam (chain finished 2026-05, no new data) and `*/analysis/` (frozen one-off results).
Sequencing: starts after E2's round-2 helper pass (E2 owns 07, 34-37, 43 now). Owner: one gpt-6-astra agent for both packages (they share 07).

Finding 2026-10-21: production L1 under `ncei/derived/mb_round2/<cruise>/points_checked/` exists for 94 cruises (13 first batch + 81 tier-A); none carries `native_quality_state` (old 34). 56 have L2. All 94 keep `_staging/`. The isolated quality revision covered only the 13. Next after packaging: rebuild all 94 with `basic_native_good` into a new round directory (no overwrite, not merged into production).
- 2026-10-21 E2 round-2 pass done: 07/35/36/37 use _common writers/logging (07 -70 lines); 34 unchanged; 43 split rebuild_cruise, quality_tables, inspect_izu_sampling along call boundaries (local nmad kept: it drops NaN first). Main agent: 5 test modules OK, 5 scripts isolated-import OK. Downstream repos reference ship code paths only in prose (15-swot 69_ship_crossover_noise.py docstring, 05-SWOT2TOPO docs, 12-ggm_scs provenance notes); no runtime imports.
- 2026-10-21: P dispatched as paseo agent 68208149 (codex gpt-6-astra, full-access): ncei/trackline + ncei/swath packages, 38 -> ncei.download rank, swath batch command tested on one small cruise in /tmp only; E1-owned docs excluded until E1 finishes. Check record: research/processing_packages_check.md.
- 2026-10-21 E1 phase 3c done (README, AGENTS.md execution convention + --help rule, ncei/code/README.md as legacy-download note, ncei/docs/README.md status groups and three stale .trellis/spec/backend links, _common/README.md, jamstec docs README). Written against P's in-progress package layout, so not committed yet; P now owns those docs to align them with its final names, and commits go after P's check.
- 2026-10-21 P done; packages committed. Main agent: 5 test modules OK, three package --help and alias help OK, 29 renames + 8 new files, residual old paths only in provenance/historical text (archive SOURCE.md, step10 run command, 2026-10-19 availability report). The extra n_tracks/n_surveys columns in the old first-batch L2 came from the one-off _runs/finish_l2_l3.py (constant 1), not from 07/35, so the 23-column match is the full formal contract.
