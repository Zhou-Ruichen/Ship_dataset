# Evaluation Guidelines

Evaluation answers the stated scientific question with the minimal
comparison that tests it. Keep the comparison fair: use the same data and
conditions where the design requires them, state which parameters differ,
and report units, sample set, split, and exclusions. Check only input
assumptions that affect the calculation; let actual failures guide
debugging.

## Selection and reporting

Data used to choose a model, hyperparameter, threshold, or stopping point
does not supply the estimate of performance on new data; that estimate
comes from data the choice never saw, and the record names which data
served each purpose. Nested resampling, with selection inside an outer
loop, satisfies this rule, and results on selection data may be reported
as a description of the fitting procedure. A number copied from a
publication is a comparison only when its data, split, and metric match
the run it is set against.

## Differences and noise

Claim a difference between two conditions only when it is large relative
to the uncertainty of the difference. Report the repeats (seeds, folds, or
samples), the spread or a confidence interval of the difference, and, when
conditions share data or folds, the paired per-fold differences. A single
run per condition supports a description, not a ranking.

## Metrics and results

Choose the metrics and result form the question and existing project
conventions require. Record actual values, conditions, definitions, and
relevant output paths in the project's existing record; a number from a
dashboard without the underlying evidence is not a result. A result that
misses an expectation is still a finding: report the value, the comparison
conditions, and a plausible interpretation without turning the expectation
into a pass/fail criterion.
