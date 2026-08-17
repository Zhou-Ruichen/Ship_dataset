# Research Minimal Code (Highest Priority)

On conflict with any other spec file, this one wins for exploratory work.

Goal: validate ideas and get experiments running. This is not production
code. Write the smallest change that answers the question; prefer one line
from an existing library over new code (see the reuse ladder in
[anti-bloat.md](./anti-bloat.md)).

Two independent questions are in play: the mode controls how code is written
and checked (exploratory by default; durable means code the project keeps
and maintains), and the evidence tier (scratch / smoke / retained, per
[reproducibility.md](./reproducibility.md)) controls what the run records.
A retained result does not make exploratory code durable.

In exploratory mode, do not add defensive code, boundary checks,
hash/checksum logic, exception handling, retries, unit tests, strict typing,
or abstractions unless the task names a concrete, likely failure that needs
one, or the user explicitly asks. In durable mode, apply the reliability the
component actually needs.

Before any verification step, be able to name the concrete, plausible
failure it targets and how its result would change the next action. Use the
cheapest check that answers that question; do not add another check for the
same question once it is answered.

Run and data manifests are written by the run-script template at retained
tier only; hash and checksum logic never appears scattered through
experiment code.

Stop condition: once the requested result is established and the mode's
sanity checks pass, the task is done. Do not seek additional certainty
without a concrete failure signal.
