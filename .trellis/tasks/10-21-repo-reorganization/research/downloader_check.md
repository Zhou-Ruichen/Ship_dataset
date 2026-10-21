# Unified downloader

Owner: D. Date: 2026-10-21. Implementation and bounded checks complete.
Switchover remains a user decision.

Authorized changes: `ncei/download/`, `_common/tests/test_ncei_download.py`,
this record, and `/tmp/download_check/`. The live Tier-B work directory,
raw data, parquet log, existing downloaders, and order lists remain read-only.

## Package and commands

- Keep 41's `trees.json`, `todo.json`, directory cache, `download-*.jsonl`,
  nine log columns, and successful-row merge semantics.
- Read direct cruise and first-pass ship/cruise layouts. New cruises use 41's
  direct layout; existing ship/cruise directories retain their location.
- Share curl transport, proxy rotation, resumption, retries, and stall guard.
  Require exact HTTP sizes and successful curl completion; do not accept a
  truncated object within 1 KB of its advertised length.
- Retry failed/empty directory probes and report them as failures. Never use
  old `tierA_complete:*` or `tierA_skip:*` metadata as proof of completeness.
- R2R/static MGD77T: URL plans with recorded SHA256 only. SOURCE.md and the log
  do not establish a complete remote enumeration contract.
- Default free-space floor: 400 GiB, matching supervise.sh's actual units.
  Check before work and during active curl subprocesses.

Package modules: `transport` (curl/disk), `inventory` (listings/paths/plans),
`download` (diff/fetch/hash), `log` (backup/merge), `verify` (gzip/completeness),
`__main__` (six commands), `__init__` (shared constants).
No new dependency was added; the package uses the existing pandas/parquet
environment, curl, gzip, and the Python standard library.

`ncei/download/README.md` has one runnable example for each command. `inventory`
enumerates remote directories; `diff` reads cached trees offline; `fetch`
consumes the compatible queue or a URL plan; `merge` backs up and updates the
log; `verify` checks the inventory's cruises; `run` repeats acquisition.
Verification defaults to `<work>/verify/`, keeping task-scoped reports separate
from combined processing manifests.

## Check results

1. Unit tests passed: `python -m unittest _common.tests.test_ncei_download`
   (16 tests). They cover listing parsing/navigation, two platforms layouts,
   URL plans, failed-inventory semantics, failed probes, exact-size rejection,
   checksum rejection, disk-floor handling, loop termination, and an actual
   local HTTP `-C -` resume.
2. A fixed copy of the completed `AT3L2` cruise and its 10-file tree was
   compared by 41 and the new downloader. Both produced zero pending files.
   A second fixed copy with two files omitted produced two pending files in
   both tools with identical queue records.
   An earlier live-disk comparison returned 181,120 versus 181,101 pending
   while Tier-B was writing. That changing-input comparison is not used as
   compatibility evidence.
3. A copied URL plan with three `m77t_static` files downloaded to
   `/tmp/download_check/raw_fetch`; all three SHA256 values matched the log.
   Two R2R files were also fetched and matched (103,904 bytes across the five
   objects). A static URL was repeated with a deliberately wrong partial
   prefix; checksum rejection followed by a fresh transfer recovered it.
   The local HTTP test separately verified successful byte-range resumption:
   a 1,900-byte object started with 250 local bytes, sent `Range: bytes=250-`,
   and matched its SHA256 after downloading the remaining 1,650 bytes.
4. The same JSONL was merged into copied logs by 41 and by `ncei.download`.
   Both outputs contained 185,670 rows and were equal after sorting.
5. Four stored gzip rows were checked: three valid files and one known
   truncated HLY1102 file. New `gzip_t_rc` and bytes matched the stored
   preflight rows (`0,0,0,1`). The new completeness audit classified the
   completed `AT3L2` cruise as `complete` with 10/10 files and zero `.part`
   files. Old 32's `main()` was imported with root, log, and outputs redirected
   into `/tmp/download_check/`; all 13 output columns matched. AT3L2 has not
   reached the live merged log, so the comparison log is a copy plus reference
   rows derived from its ten remote URLs, used identically by both audits.
6. All six commands were exercised with scratch inputs. Six actual cached
   AT3L2 directory pages produced identical directory/file/size sets in 41's
   parser and the new parser. Evidence: `cli_check.txt`, `listing_results.json`,
   and `unit_tests_final.txt` under the evidence directory.

Evidence directory: `/tmp/download_check/`. Initial copied inputs:
`source_log.parquet`, `tierB_trees.json` (704 surveys, 1,107,867 files).

Network checks used one worker and five distinct small upstream objects.
The static URLs were repeated for the recovery check. No additional upstream
objects were fetched. No live raw file or live parquet log was written.

The reproducible local comparison is `/tmp/download_check/check_local.py`;
its result is `/tmp/download_check/local_results.json`.
From the repository root it can be repeated without upstream network traffic:

```bash
python - <<'PY'
exec(compile(open('/tmp/download_check/check_local.py').read(),
             '/tmp/download_check/check_local.py', 'exec'))
PY
```

## Functional comparison

- **Merged:** 41's platforms-tree inventory, diff, curl resume, proxy rotation,
  retries, JSONL schema, parquet backup/deduplication, and worker metadata.
- **Upgraded:** failed directory probes are retryable and recorded as failures;
  exact HTTP sizes and optional SHA256 are checked before `ok`; both raw tree
  layouts are recognized; disk space is checked before and during transfers;
  `run` replaces the supervisor loop. Verification includes absent cruises
  and listing failures. It uses full relative paths rather than 32's basename
  fallback, which could confuse two same-named files in different directories.
- **Not implemented:** remote R2R or MGD77T-static enumeration. The previous
  walkers are absent and `SOURCE.md` plus the surviving log cannot establish
  a reliable directory protocol. URL-plan downloads with mandatory SHA256 are
  the supported recovery path.

## Switchover

Switching is not executed. After user approval, stop the old supervisor and
wait for its current 41/curl processes to exit so there is one writer. Preserve
the work directory, `.part` files, JSONL records, `trees.json`, and a copy of the
parquet log. Check tree errors, pending count, and free space above 400 GiB.
The new `run` first merges successful JSONL records left by 41, then retries
failed and unresolved trees without discarding partial downloads.

```bash
cd /mnt/data2/00-Data/ship
/opt/miniforge3/bin/python -m ncei.download run \
  --catalog ncei/derived/mbbdb_value_ranking/order_tier_B_queue.tsv \
  --work /tmp/tierB_gapfill --tag tierB-gapfill \
  --workers 96 --inventory-workers 24 --attempts 6 --disk-floor-gb 400
```

Run verification after the queue reaches zero:

```bash
/opt/miniforge3/bin/python -m ncei.download verify \
  --work /tmp/tierB_gapfill --workers 12
```

After the first new pass, check its `download-*.jsonl` statuses, updated queue,
`inventory_errors.json`, and parquet backup/row counts. Completion requires
zero pending files and zero failed inventories; the separate gzip report
identifies corrupt input. Verification writes `/tmp/tierB_gapfill/verify/`;
do not overwrite the wider processing manifests with this Tier-B-only audit.

After the user confirms the outputs and backups, archive
`ncei/code/41_tier_a_gapfill.py`, `ncei/code/download_tier_a_round2.py`,
`ncei/code/41_gzip_preflight.py`, and
`ncei/code/32_mb_round2_completeness.py`. Do not archive them while
`supervise.sh` can still invoke 41. Preserve the supervisor as a recovery entry
until the new run is accepted; then it can be archived with the old scripts.
