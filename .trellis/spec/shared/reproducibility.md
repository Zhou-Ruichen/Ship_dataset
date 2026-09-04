# Reproducibility

A result should be traceable to the inputs, code, parameters, environment,
assumptions, and outputs that produced it. Keep the record in the form that
best fits the work: an existing log, configuration, notebook, `result.md`, an
immutable source reference, or a short note is sufficient when it contains the
needed information.

## Temporary and retained work

Temporary outputs include debugging attempts, failed runs, quick probes, and
intermediate products that do not support a conclusion. Put them in a clearly
temporary location and remove them when they stop being useful.

Retain outputs used in a comparison, report, paper, handoff, baseline, or
result claim. Alongside them, retain enough evidence to identify:

- the exact data source and version, including split or selection rules;
- the command or notebook, parameters, and seed or deterministic setting;
- the code state, including relevant uncommitted changes;
- the environment record when it can affect the result;
- metrics, figures, tables, logs, negative or null observations, assumptions,
  and known limitations.

The evidence may be distributed across existing project files. Do not create a
per-run manifest, duplicate a stable lockfile, or fill empty fields just to
follow a template. If a configuration or script may change later, preserve the
values and code changes used by the run, or record a revision that identifies
them; a pointer to a mutable file alone is insufficient.

## Environment and randomness

Use the project's existing environment record, such as `uv.lock`, `renv.lock`,
a conda export, a container digest, or a module list. Record a per-run state
only when no stable record exists or the environment itself can drift. Do not
install unrecorded dependencies into a shared environment.

When randomness is used, record the seed or seed schedule and any relevant RNG
libraries or nondeterministic hardware or parallelism. If the computation has
no randomness, state that. Deterministic algorithms may be enabled for a
diagnostic run when supported, but do not impose them globally.

## Protocol changes and claims

For a retained comparison, keep the question, method, data version, split,
preprocessing, metric definition, baseline, and claim scope identifiable. If
one changes, retain the earlier evidence and state what changed in the new
record.

Describe what was evaluated before claiming improvement, convergence,
reproduction, or support for a hypothesis. Include the relevant outputs,
evaluation group, parameters, randomness, data version, code state, and
limitations. A successful command or task completion alone is not evidence for
a scientific claim.

External dashboards, notebooks, lab notes, and experiment trackers can mirror
the record. Keep enough project-local evidence to recover the inputs and
decisions if those services change or disappear.
