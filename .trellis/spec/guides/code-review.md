# Research Code Review

Review when the task needs it, against the requested calculation and evidence.
This guide adds no separate review stage or reviewer agent.

- Does the code perform the intended calculation on the stated data?
- Could units, missing values, alignment, or data leakage change the result?
- Do the reported observations come from the stated outputs?
- Did the change add hypothetical-failure handling, wrappers, duplicated logic,
  or unrelated work that the task does not need?

Use [research-minimal.md](../shared/research-minimal.md) for execution and testing.
Missing unrequested tests are not a defect. Report actual problems with file
references; do not manufacture findings to fill a checklist.
