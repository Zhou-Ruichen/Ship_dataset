# Logging Guidelines

> Logging conventions for pipeline scripts.

We use the **stdlib `logging`** module. No structured-logging library
(no `structlog`, no `loguru`). One log file per script invocation, plus
console mirror.

---

## Standard setup

Every script defines:

```python
def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(Path(__file__).stem)
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    fh = logging.FileHandler(log_path, mode="w")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger
```

- One named logger per script (`getLogger(Path(__file__).stem)`).
- Two handlers: file (mode `"w"` — overwrites prior run) + stdout.
- Default level INFO. `--verbose` may bump to DEBUG (optional).

---

## Log file location

```
output/logs/<script_name>.log                         # full run
output/logs/<script_name>_<run_label>.log             # sample / test100
```

The `<run_label>` suffix mirrors the data output convention so a sample
run does not overwrite the full-run log.

---

## Log levels

| Level | Use for |
|-------|---------|
| `DEBUG` | Per-file detail when troubleshooting; off by default |
| `INFO` | Stage progress (`processed=1234/5083`), summary stats, output paths |
| `WARNING` | Per-file failures (with `file_id`), unusual but recoverable conditions, config defaults applied |
| `ERROR` | Stage cannot continue; pair with `sys.exit(1)` |
| `CRITICAL` | Don't use — we don't have an alerting layer |

Rule of thumb: a healthy `--run-label full` should produce mostly INFO,
zero ERROR, and any WARNING lines should correspond 1:1 to rows in the
errors TSV.

---

## What to log

Always log:
- The full CLI invocation (`sys.argv`) at startup, so the log is
  self-describing.
- Resolved input/output paths after path resolution.
- Total file count (`n_files=5083`) before the loop starts.
- Periodic progress (every N files or every M minutes), not per-file.
- Final summary: total processed, total failed, elapsed seconds, output
  parquet size.

Never log:
- Tracebacks at INFO. Use `logger.exception(...)` (which is ERROR-level
  and includes the traceback) only when actually erroring out.
- Per-row dataframe content. Aggregate first.
- Anything sensitive — n/a for this project, but the rule still holds.

---

## Progress reporting

For loops over thousands of files, log progress proportionally, not
per-iteration:

```python
N = len(files)
log_every = max(1, N // 50)        # ~50 progress lines total
for i, fid in enumerate(files, 1):
    process(fid)
    if i % log_every == 0 or i == N:
        logger.info("progress=%d/%d (%.1f%%)", i, N, 100*i/N)
```

A 5,083-file run should produce on the order of 50–100 progress lines,
not 5,083 — log files are read by humans.

---

## What goes in the report MD vs the log

| Goes in `.log` | Goes in `docs/<stage>_report.md` |
|---|---|
| Timing, progress, debugging | Final row counts, schema, distribution stats |
| Error counts and per-file failures | Summary tables consumed downstream |
| Config values resolved | Decisions and assumptions worth preserving |

The log is for the developer at runtime. The report is the durable
artifact that downstream stages and the next reader will rely on.
