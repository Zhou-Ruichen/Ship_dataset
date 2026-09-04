# Minimal Research Work

These rules take precedence over other specs for exploratory work, the default.
Follow only the extra maintenance requirements the user explicitly requests.
Reusing code or publishing a result does not change that default.

Write the smallest change that answers the current question for the stated
inputs. Reuse existing code and libraries. A direct script or notebook is enough;
extract functions or modules only to remove real duplication or clarify the
calculation. Do not add wrappers, config systems, compatibility paths, retries,
or defensive branches for hypothetical needs. See [anti-bloat.md](./anti-bloat.md).

Check scientific assumptions that could silently change the result, such as
units, coordinates, missing-value handling, and data isolation, once at the data
boundary. Trust them afterward. Let file, indexing, and library errors propagate
with their tracebacks. Diagnose an actual failure with the smallest useful check
and remove temporary instrumentation when it has answered the question.

Software tests, lint, builds, type checks, and separate verification runs require
an explicit task or user request. Use the requested experiment's own outputs to
assess execution and observations. Do not repeat a successful command for
reassurance or add tests merely because code was added, reused, or fixed.

Preserve the inputs, actual settings, code state, environment, and outputs needed
to interpret results you keep. Reuse existing records; no manifest format or
recording framework is required. See [reproducibility.md](./reproducibility.md).

Complete the runs required by the question. Scientific metrics are observations,
not task pass/fail thresholds; do not invent outcome gates or inherit them from
archived experiments. Negative and null results are evidence, and do not cancel
the remaining planned runs. Changing the research plan follows the user.

Stop when the requested work and evidence are complete. Opening sealed final
evaluation data or declaring exploration finished requires the user's
confirmation. Fixing settings for one comparison does not end exploration.
