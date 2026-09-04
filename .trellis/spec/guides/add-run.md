# Guide: Add A Run

Use this for a new analysis, simulation, traditional ML experiment,
data-processing run, or evaluation.

1. State the scientific question and the minimal comparison that can answer it.
2. Find the project's existing script, notebook, config, data, and result record.
3. Reuse that path and edit parameters or config for the comparison. Add
   code only when the existing path cannot express the change.
4. Run the cases required by the question under matched conditions, with data
   isolation and units made clear.
5. Record the actual command or settings, observed results, limitations, and
   relevant log, figure, table, or product paths in the project's existing
   record. Keep temporary outputs separate from evidence used for claims.

Keep variants as parameters or configuration values. Do not create copied files
named `v2`, `final`, or similar. A metric target is an observation to report,
not a pass/fail condition.
