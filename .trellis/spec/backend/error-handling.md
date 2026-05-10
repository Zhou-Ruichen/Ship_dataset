# Error Handling

> How a 5,000-file batch pipeline handles partial failures.

The principle: **one bad file must not kill the run**. Per-file failures
are recorded and the loop continues. Only environment / config errors
(missing input dir, malformed YAML, no parquet writer available) abort
the whole script.

---

## Error categories

| Category | Behavior | Where it ends up |
|----------|----------|------------------|
| Per-file processing failure | Catch, log, append to errors TSV, continue | `output/logs/<script>_errors.tsv` + WARN line in `.log` |
| Per-row data anomaly (bad lon/lat/depth) | QC flag column, no exception | `derived/points_qc/*.parquet` `qc_*` columns |
| Missing upstream output | Abort with clear message naming the missing file | stderr + ERROR line in `.log` |
| Config / CLI misuse | `argparse` error or `sys.exit(2)` with explanation | stderr only |
| Disk full / permission denied | Let it propagate; the run is dead anyway | Python traceback |

---

## The errors TSV pattern

Each batch stage writes a sibling errors file:

```
output/logs/<script_name>_errors.tsv
output/logs/<script_name>_errors_<run_label>.tsv   # when run-label suffixed
```

Columns at minimum:
```
file_id    error_type    error_message    traceback_short
```

The errors TSV is a **first-class output** — the next stage's curate
script (e.g. `02a_curate_points_manifest.py`) is allowed to read it to
exclude broken files from downstream processing.

Do not delete or git-ignore the errors TSV. Empty file = clean run, that's
useful information.

---

## Per-file try/except pattern

```python
errors = []
for file_id in files_to_process:
    try:
        process_one(file_id, ...)
    except Exception as e:
        logger.warning("file_id=%s failed: %s", file_id, e)
        errors.append({
            "file_id": file_id,
            "error_type": type(e).__name__,
            "error_message": str(e)[:500],
            "traceback_short": traceback.format_exc(limit=3),
        })

if errors:
    pd.DataFrame(errors).to_csv(errors_tsv, sep="\t", index=False)
```

- Catch `Exception`, not `BaseException` (don't swallow KeyboardInterrupt).
- Truncate the message at ~500 chars; full traceback goes to the `.log`
  file via `logger.exception(...)` if needed for debugging.

---

## When to abort

Abort the whole script (`sys.exit(1)`) only for:

1. **Missing input directory** — the upstream stage hasn't run.
2. **Empty manifest** — the script has nothing to do, almost certainly a
   path bug.
3. **Schema mismatch** in upstream parquet — the contract is broken; fix
   upstream first.
4. **`--run-label full` without `--confirm-full`** — see quality spec.

For each, print a one-line actionable error message to stderr naming the
expected path or fix:

```
ERROR: Expected derived/points_qc/ from 03_qc_multibeam_points.py.
       Run: python3 03_qc_multibeam_points.py --run-label full --confirm-full
```

---

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success (errors TSV may still have rows) |
| 1 | Aborted before processing started (missing input, bad config) |
| 2 | CLI argument error (argparse default) |

A run that processes 5,000 files and fails on 47 of them exits **0** —
the failures are in the errors TSV and the user is expected to inspect
the report. This is intentional; it lets cron / batch pipelines
distinguish "the run never started" from "the run completed with some
known-bad inputs".
