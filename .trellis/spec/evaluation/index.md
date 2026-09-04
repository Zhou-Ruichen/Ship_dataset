# Evaluation Guidelines

Use the repository's existing evaluation layout. An exploratory evaluation can
stay in the script or notebook where the question is being investigated. Extract
code only to simplify the current calculation or meet an explicit maintenance need.

Evaluation should answer the stated scientific question. Keep the comparison
fair: use the same data and conditions where the design requires them, state
which parameters differ, and report units, sample set, split, and exclusions.
Check only input assumptions that affect the calculation, such as shape, schema,
dtype, units, coordinates, or data isolation. Let actual failures guide further
debugging; do not add generic preflight validators or metric thresholds.

## Metrics And Results

Choose the metrics and result form required by the question and by the existing
project conventions. There is no required JSON schema or fixed metrics file.
Record the actual values, conditions, definitions, and relevant output paths in
the project's existing result record, log, configuration, notebook, or report.

A result that misses an expectation is still a scientific finding. Report the
value, comparison conditions, and plausible interpretation without turning the
expectation into a pass/fail criterion.

## Figures And Tables

Keep generated figures and tables with the run or analysis that produced them,
using the project's existing paths. Put curated material for papers or review in
the project's report area when one exists. Each comparison should make clear
what was compared and under which conditions; do not rely on numbers copied from
a dashboard or screenshot when the underlying evidence is unavailable.

## Diagnostic Code

Parameterize a diagnostic when it is reused. For a one-off investigation, a
small local script or notebook is enough. Keep variants as explicit parameters
or configuration values rather than copied files with names such as `v2` or
`final`.
