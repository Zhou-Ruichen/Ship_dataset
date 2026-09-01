# Shared Computational Research Guidelines

Applies to every task in this repository. Optimize for reproducibility,
iteration speed, readable code, and evidence-backed claims.

## Documentation Files

| File | Read when |
| --- | --- |
| [research-minimal.md](./research-minimal.md) | Before any exploratory implementation; overrides conflicting guidance |
| [project-layout.md](./project-layout.md) | Creating, moving, or naming files |
| [anti-bloat.md](./anti-bloat.md) | Adding files, variants, scripts, helpers, or abstractions |
| [reproducibility.md](./reproducibility.md) | Running computations or reporting results |
| [scientific-writing.md](./scientific-writing.md) | Writing reports, discussions, methods, or paper drafts |
| [../data/index.md](../data/index.md) | Reading, writing, processing, or validating data |
| [../evaluation/index.md](../evaluation/index.md) | Writing metrics, figures, reports, or comparisons |
| [../guides/index.md](../guides/index.md) | Choosing a task guide |

## Quick Navigation By Task

| Task | Read |
| --- | --- |
| Add a script, notebook, or helper | [anti-bloat.md](./anti-bloat.md) and [project-layout.md](./project-layout.md) |
| Run an experiment, simulation, or analysis | [reproducibility.md](./reproducibility.md) |
| Create or transform data | [../data/index.md](../data/index.md) |
| Report a metric, figure, or comparison | [../evaluation/index.md](../evaluation/index.md) |
| Write a results discussion, report, or paper draft | [scientific-writing.md](./scientific-writing.md) and [../guides/write-results.md](../guides/write-results.md) |
| Review a change | [../guides/code-review.md](../guides/code-review.md) |
| Verify a change | [../evaluation/index.md](../evaluation/index.md) and [../guides/code-review.md](../guides/code-review.md) |

## Rules

- Respect the repository's current documented layout. Do not rename a mature
  project into this template shape without a migration task.
- Keep configs, parameters, and commands as explicit sources of truth.
- Use `outputs/<run_id>/` for retained run artifacts.
- Scratch and smoke runs stay lightweight and disposable unless promoted.
- Keep curated human-facing reports separate from raw run outputs.
- Delete code the current task superseded after verification. Ask before
  deleting experiment records, retained outputs, data manifests, or untracked
  files.
- Do not productionize one-off exploration with factories, plugin systems,
  config classes, or broad abstraction layers.
- New code and dependencies follow [anti-bloat.md](./anti-bloat.md). Temporary
  diagnostics are removed after they answer their question.
- Result claims point to the command, data, parameters, environment record, and
  outputs that support them. Metric values remain observations, not task
  pass/fail criteria.
