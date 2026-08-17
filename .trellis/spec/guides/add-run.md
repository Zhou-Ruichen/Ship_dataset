# Guide: Add A Run

Follow this when adding a new analysis, simulation, traditional ML experiment,
data-processing run, or evaluation.

## Steps

1. Search existing configs, scripts, notebooks, and run records.
2. Decide whether the run is scratch, smoke, or retained.
3. Reuse an existing entrypoint when possible.
4. Add or edit parameters/config instead of copying a script.
5. Add reusable code only when parameters cannot express the change.
6. Run the narrowest smoke check that proves the command executes.
7. If the result will be cited, promote it to retained and write the required
   manifest, metrics/result files, data record, assumptions, and environment
   freeze.
8. Record the command and output path in the task response.

## Do

```text
scripts/run_analysis.py --config configs/sensitivity.yaml
outputs/20260610-142233-sensitivity/manifest.json
```

## Do Not

```text
scripts/run_analysis_v2.py
scripts/run_analysis_final.py
notebooks/final_results_really_final.ipynb
```

## Retained Run Minimum

A retained run records:

- command;
- parameters or config snapshot;
- git commit and dirty state;
- seed/randomness state or explicit "deterministic";
- environment freeze;
- input data manifest or source snapshot;
- metrics, figures, tables, or product paths;
- assumptions and exclusions.

## Completion Checklist

- [ ] The run is represented by parameters/config/command, not copied code.
- [ ] The run tier is clear: scratch, smoke, or retained.
- [ ] Any result claim has retained artifacts.
- [ ] Smoke validation was run or the reason it was not run is stated.
- [ ] No metric target is written as a completion gate; targets are reported,
      not gated.
- [ ] New reusable code, if any, is in the project's source area.
