# Research Core Spec

General research-project rules for reproducible, inspectable computational
work. Use this template for non-DL research, statistical analysis, simulation,
traditional ML, data-processing pipelines, and paper reproduction work.

This template is intentionally language-agnostic. It does not prescribe a
framework, package manager, model stack, or directory layout beyond the minimum
contracts needed for evidence, cleanup, and result traceability.

Use `dl-earth-research` instead when the project primarily trains or evaluates
deep-learning models on geoscience data and needs PyTorch, checkpoint, ablation,
or geospatial data rules.

## Structure

### [Shared](./shared/index.md)

Cross-cutting research engineering rules:

- [Project Layout](./shared/project-layout.md)
- [Anti-Bloat Rules](./shared/anti-bloat.md)
- [Reproducibility](./shared/reproducibility.md)
- [Scientific Writing](./shared/scientific-writing.md)

### [Data](./data/index.md)

General data handling rules for inputs, durable data products, manifests,
boundary validation, and rebuild instructions.

### [Evaluation](./evaluation/index.md)

Rules for metrics, figures, reports, comparisons, retained outputs, and result
claims.

### [Guides](./guides/index.md)

Task guides for adding a run, writing results, and reviewing research-code changes:

- [Add Run](./guides/add-run.md)
- [Write Results](./guides/write-results.md)
- [Code Review](./guides/code-review.md)

## Template Fit

Use `research-core` for:

- non-DL scientific computing;
- statistical analysis or simulation;
- traditional ML experiments that do not need DL training conventions;
- reproducible data processing and evaluation pipelines;
- existing projects where only research discipline should be added.

Do not use it as a generic web/backend/product-development template. It is
research-oriented: its strongest rules are about evidence, artifacts, cleanup,
and claims.

## Core Rules Summary

| Rule | Reference |
| --- | --- |
| Keep existing project layout unless a new project needs one | [shared/project-layout.md](./shared/project-layout.md) |
| Use scratch, smoke, and retained run tiers | [shared/reproducibility.md](./shared/reproducibility.md) |
| Result claims require retained evidence | [shared/reproducibility.md](./shared/reproducibility.md) |
| Durable data products need manifests | [data/index.md](./data/index.md) |
| Superseded code is deleted after verification; experiment records require care | [shared/anti-bloat.md](./shared/anti-bloat.md) |
| Reports contain curated artifacts, not raw dumps | [evaluation/index.md](./evaluation/index.md) |
| Report prose leads with the finding, not the run | [shared/scientific-writing.md](./shared/scientific-writing.md) |

## Usage Notes

For new projects, start with the recommended layout only if it fits the work.
For existing projects, map these rules onto the current structure instead of
renaming directories just to match the template.

## Version Notes

Template ids are stable. Small rule changes ship under the same id. The
source repository's root CHANGELOG.md records what changed in each release.
