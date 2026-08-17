# Reproducibility

Every claimed result must be traceable to inputs, code, parameters,
environment, assumptions, and outputs.

## Run Retention Tiers

Use the lightest tier that preserves the scientific record:

- Scratch: debugging, failed runs, quick probes, and daily iteration. Put these
  in `outputs/scratch/<run_id>/`, a temporary directory, or another clearly
  disposable location. They may be deleted when no longer useful. No full
  manifest or freeze file is required unless the run is promoted.
- Smoke: tiny checks that prove the pipeline executes. Record enough command,
  config, metric, or log evidence to debug a failure. No full manifest or
  freeze file is required unless the smoke result is cited or promoted.
- Retained: any run used in a comparison, report, paper, model handoff,
  regression baseline, or result claim. Retained runs must have the full
  manifest, parameter record, metrics or result files, data/source record,
  assumptions, and environment freeze.

Promote a scratch or smoke run before citing it: move or copy the selected
artifacts into `outputs/<run_id>/`, add the missing retained-run evidence, and
mark why it is retained.

## Run Manifest

Each retained computation, simulation, analysis, evaluation, prediction, or
data-processing run must write:

```text
outputs/<run_id>/manifest.json
```

or, for durable data products:

```text
data/manifests/<product>.json
```

Scratch and smoke runs may write lighter records, but they must be promoted to
retained runs before they support a result claim.

## Required Manifest Fields

```json
{
  "run_id": "20260610-142233-sensitivity",
  "created_at": "2026-06-10T14:22:33Z",
  "command": "python scripts/run_analysis.py --config configs/sensitivity.yaml",
  "retention": "retained",
  "retention_reason": "comparison table for report",
  "git": {
    "commit": "unknown",
    "dirty": true
  },
  "parameters": {
    "config_path": "configs/sensitivity.yaml",
    "config_snapshot": "outputs/20260610-142233-sensitivity/config.yaml",
    "seed": 42
  },
  "environment": {
    "manager": "<uv|conda|renv|julia|system|...>",
    "name": "<env-name-or-null>",
    "language": "<python|r|julia|matlab|shell|...>",
    "language_version": "<version>",
    "packages": {},
    "freeze": "outputs/20260610-142233-sensitivity/environment.freeze.txt"
  },
  "data": {
    "manifest": "data/manifests/input_v1.json",
    "source_snapshot": null
  },
  "outputs": {
    "metrics": "outputs/20260610-142233-sensitivity/metrics.json",
    "figures": [],
    "tables": []
  },
  "assumptions": []
}
```

This is a field template, not a concrete environment recommendation. Actual
run manifests must replace placeholders with real values. Do not invent commit
hashes, metrics, seeds, package versions, data sources, or assumptions.

## Environment

Each project declares one environment strategy in its own README or spec layer.
This template does not pick the manager; it requires the contract:

- Every retained run manifest records the environment it ran in, plus a freeze
  snapshot written next to the run artifacts. `freeze` is a path to the
  captured dependency/environment snapshot for this run, not a template-level
  fixed file.
- Do not create a freeze file for every scratch run in a sweep. If a scratch or
  smoke run becomes evidence, promote it and capture or copy the environment
  freeze then.
- Shared environments drift; for retained runs, the freeze snapshot is what
  preserves the run.
- Use the selected ecosystem's equivalent export: `pip freeze`, `uv pip
  freeze`, `conda env export`, `renv.lock`, `Manifest.toml`, a container digest,
  a module list, or another reconstructable environment record.
- Do not install packages ad hoc into a shared base environment for retained
  work. Add dependencies to the project's dependency file or record the exact
  environment snapshot.

## Seed And Randomness Rule

When a computation uses randomness, the retained manifest records:

- the seed or seed schedule;
- the libraries or tools whose RNGs were seeded;
- whether deterministic algorithms were requested;
- any known nondeterministic hardware, solver, or parallelism behavior.

If the computation is deterministic and has no seed, state that explicitly.

## Result Claims

Do not say a method improved, converged, reproduced a number, supports a
hypothesis, or generated a final dataset unless the supporting run was promoted
to retained and:

- metrics or result files exist in `outputs/<run_id>/`;
- the evaluated split, sample set, simulation condition, or comparison group is
  recorded;
- parameters, command, seed/randomness state, and assumptions are recorded;
- data manifest or source snapshot is recorded;
- environment freeze is recorded.

If only a smoke test ran, say it was a smoke test.

## External Tools

Remote dashboards, notebooks, lab notes, and experiment trackers are mirrors.
The project-local retained run directory `outputs/<run_id>/` remains the source
of truth.
