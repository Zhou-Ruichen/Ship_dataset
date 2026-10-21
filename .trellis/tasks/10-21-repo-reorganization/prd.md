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
