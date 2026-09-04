# Keep Research Code Small

Reuse the project's existing functions, entrypoints, and dependencies before
adding code. Keep experiment differences in parameters or existing configs;
do not copy a script into `train_v2.py` or `analysis_final.py`.

A direct script or notebook can remain direct even when reused. Extract a
function or module when it removes real duplication or clarifies the current
calculation. Do not introduce factories, registries, base classes, plugin
systems, config classes, or CLI layers for possible future work.

When the task replaces tracked code and the replacement is confirmed, remove
the old implementation with its unused wrappers and dependencies. Git history
preserves it. Temporary diagnostics can be removed once they answer the question.

This does not authorize unrelated cleanup. Preserve original data, retained
results, settings referenced by results, untracked files, and unrelated work.
Report suspected dead code outside the task instead of deleting it.

Use [research-minimal.md](./research-minimal.md) for checks and execution rules.
