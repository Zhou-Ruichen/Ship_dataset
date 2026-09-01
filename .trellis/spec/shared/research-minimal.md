# Research Minimal Code (Highest Priority)

On conflict with any other spec file, this one wins for exploratory work.

Goal: validate ideas and get experiments running. This is not production
code. Write the smallest change that answers the question; prefer existing
project code or a library function over new code (see the reuse order in
[anti-bloat.md](./anti-bloat.md)).

Two independent questions are in play: the mode controls how code is written
and checked (exploratory by default; durable means code the project keeps
and maintains), and the evidence tier (scratch / smoke / retained, per
[reproducibility.md](./reproducibility.md)) controls what the run records.
A retained result does not make exploratory code durable.

In exploratory mode, validate external inputs once where they enter the
project when schema, columns, units, coordinates, time, or missing values can
change the result. Beyond that boundary, do not add defensive code,
hash/checksum logic, exception handling, retries, unit tests, strict typing, or
abstractions unless the task names a concrete, likely failure that needs one,
or the user explicitly asks. In durable mode, apply the reliability the
component actually needs.

Before any verification step, be able to name the concrete, plausible
failure it targets and how its result would change the next action. Use the
cheapest check that answers that question; do not add another check for the
same question once it is answered.

Retained runs record the command, inputs, configuration, and outputs needed to
interpret or reproduce the result. Record a checksum only when exact byte
identity matters; checksum logic never appears scattered through experiment
code.

Stop condition: the task is done once the requested result is established,
every run the design requires has completed, and the mode's sanity checks
pass. Metric values are observations, not pass/fail criteria: a negative or
null result is recorded as evidence and answered with the next run the task
plan registered, not with a stop or a route-level conclusion. Completing a
task or a full set of runs does not end exploration on its own: opening a
sealed evaluation (final test period, held-out data) or freezing the
explored configuration closes the exploratory phase, so take that step only
when the task's registered decision is answered and the user confirms.
Do not seek additional certainty without a concrete failure signal.
