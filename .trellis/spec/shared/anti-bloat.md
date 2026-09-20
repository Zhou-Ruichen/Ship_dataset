# Keep Research Code Small

Reuse the project's existing functions, entrypoints, and dependencies before
adding code; the standard library and an already-installed package come next.
Keep experiment differences in parameters or existing configs, not in copies
named `train_v2.py` or `analysis_final.py`; one maintained filename holds
the current source.

Extract a function or module only when it removes real duplication or
clarifies the current calculation; no factories, registries, base classes,
plugin systems, or CLI layers for possible future work. If a diagnostic
script will be rerun with different inputs, turn the varying parts into
parameters; a one-off check stays in the script or notebook where it ran.
When a task replaces tracked code, remove the superseded
implementation and its unused wrappers once the replacement works.

A requested code review checks the same things: the intended calculation on
the stated data, the boundary conditions in the data guidelines, reported
observations traceable to stated outputs, and structure the task does not
need. Report actual problems with file references; a missing test suite is
not by itself a finding.

This does not authorize unrelated cleanup: preserve original data, retained
results, settings referenced by results, untracked files, and unrelated work,
and report suspected dead code outside the task instead of deleting it.
