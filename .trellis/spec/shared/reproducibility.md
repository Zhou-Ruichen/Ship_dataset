# Reproducibility

A result should be traceable to the inputs, code, parameters, environment,
assumptions, and outputs that produced it. Keep the record in the form that
fits the work: an existing log, configuration, notebook, `result.md`, an
immutable source reference, or a short note is sufficient when it preserves
the needed facts. No per-run manifest, schema, or fixed metrics file is
required, and no empty field is filled to follow a template. A notebook
counts as a record when it runs top to bottom from a fresh kernel.

## Temporary and retained work

Temporary outputs include debugging attempts, failed runs, quick probes, and
intermediate products or checkpoints that do not support a conclusion; keep
them in a clearly temporary location and remove them when they stop being
useful.

Retain outputs used in a comparison, report, paper, handoff, reference run,
or result claim, with enough evidence to identify:

- the exact data source and version, including split, sampling, or selection
  rules and the variables consumed;
- the command or notebook, parameters, and seed or seed schedule;
- the code state, including relevant uncommitted changes;
- the environment, framework, dependency, and accelerator records when they
  can affect the result;
- metrics, figures, predictions or checkpoints, logs, negative or null
  observations, assumptions, and known limitations.

Evidence may be distributed across existing project files. If a
configuration or script may change later, preserve the values and code
changes used by the run, or record a revision that identifies them; a
pointer to a mutable file alone is insufficient. A successful command or
task completion alone is not evidence for a scientific claim.

## Environment and randomness

Use the project's existing environment record, such as `uv.lock`, `renv.lock`,
a conda export, or a container digest. Record per-run state only when no
stable record exists or the environment can drift; never install unrecorded
dependencies into a shared environment. Record the seed or seed schedule for
each RNG that matters to the run, and note nondeterminism from hardware,
kernels, or parallelism when it affects interpretation. Adjust randomness
handling, such as deterministic algorithms, only to answer an interpretation
question or an observed failure, without imposing it project-wide.

## Comparison changes and claims

For a retained comparison, keep question, method, data version, split,
preprocessing, metric definition, reference method, and claim scope
identifiable; if one changes, retain the earlier evidence and state what
changed in the new record. Describe what was evaluated, including outputs,
evaluation group, parameters, randomness, data version, code state, and
limitations, before claiming improvement, convergence, reproduction, or
support for a hypothesis.

External dashboards, notebooks, lab notes, and experiment trackers may
mirror the record; keep enough project-local evidence to recover the inputs
and decisions if those services change or disappear.
