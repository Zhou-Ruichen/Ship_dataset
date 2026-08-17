---
name: trellis-research-check
description: One-pass sanity check for exploratory research tasks. Establishes that the changed path executes, that obvious shape/unit/data errors are absent, and that the reported observation comes from the stated run. Use after an exploratory experiment or script change; durable infrastructure uses trellis-check instead.
---

# Research Check (exploratory, one pass)

Purpose: establish whether the experiment is executable and whether the
reported observation is trustworthy enough for the current research question.
This is a single pass. It is not a review cycle.

## Check only

- The changed path executes.
- Obvious shape, dtype, unit, and coordinate errors where relevant.
- NaN/Inf or clearly invalid outputs.
- The reported observation comes from the invocation just executed. Require
  run_id or path provenance only when the run is retained or already carries
  such an identifier; do not create provenance machinery for a scratch check.

## Do not

- Add production hardening.
- Add generic defensive checks.
- Add fallback behavior.
- Introduce abstractions.
- Run unrelated test suites.
- Hash or checksum files unless integrity verification is explicitly required
  by the task; before any such check, be able to name the failure it targets
  and what would change once found.
- Repeat a check that already passed without new evidence.
- Treat an unexpected scientific result as a software failure. A negative or
  surprising outcome is reported, not debugged into a bug hunt.

## Stop rule

After one successful pass over the list above, stop and report. Do not seek
additional certainty without a concrete failure signal.

## Report format

```
## Research Check

- Executes: <yes/no + how invoked>
- Shapes/units: <ok | issue + where>
- NaN/Inf: <absent | found + where>
- Result provenance: <from the invocation just executed | mismatch + detail>
- Findings: <none | list>
```
