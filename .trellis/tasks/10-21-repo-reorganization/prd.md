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

## Phases

1. Inventory (glm-5.3, read-only) -> `research/code_inventory.md` + `research/code_inventory.tsv`.
2. Layout decision by the main agent from the inventory.
3. Execution by area (jamstec / ncei singlebeam / ncei round-2 + download / _common, tests, docs), then README and docs path updates.

## State

- 2026-10-21: task created; inventory dispatched as paseo agent e22e97b7 (pi glm-5.3), output under research/.
