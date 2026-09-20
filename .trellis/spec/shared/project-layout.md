# Project Layout

Follow the project's documented layout; it decides where source code,
scripts, notebooks, data, outputs, reports, and checkpoints belong. For a
new project, create only the directories the current work uses. An
exploratory run can be a direct script or notebook; it needs no package,
configuration system, test directory, or command-line wrapper.

Keep temporary outputs apart from evidence that supports a result, using
existing conventions; do not move or rename existing outputs to fit this
guideline. Generated figures,
tables, and prediction products stay with the run that produced them, and
curated paper or review material goes in the report area when one exists.
Large datasets and generated outputs stay out of Git under the repository's
existing rules.
