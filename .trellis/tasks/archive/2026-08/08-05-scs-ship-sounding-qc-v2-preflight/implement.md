# Implementation Plan

- [x] Freeze config paths, SHA256, candidate/control definitions, raw context
      size, component adjacency, status vocabulary, and expected counts.
- [x] Add synthetic tests first for:
  - inclusive raw-range expansion and fixed context windows;
  - deterministic source/sign 8-neighbour components;
  - source/file/depth/count-stratified control selection;
  - NMAD and raw-context summaries with missing context;
  - weighted median/mean and dominant-contributor arithmetic;
  - five-level metadata status and closed interpretation states;
  - forbidden path, input-column, and output-decision guards.
- [x] Implement immutable audit driver with:
  - hash/schema/key/count preflight;
  - 905-cell candidate and 16-cell reference-conflict closure;
  - deterministic candidate components;
  - targeted raw-row context streaming with evidence-ceiling labels;
  - deterministic negative controls;
  - 2,658-cell aggregation-conflict census;
  - metadata/correction-feasibility matrix;
  - reports, decision package, manifest, and atomic outputs.
- [x] Implement independent verifier that recomputes all acceptance invariants
      from persisted outputs and frozen inputs.
- [x] Run estimate-only and inspect expected raw files/rows/workload.
- [x] Run unit tests and Python compilation checks.
- [x] Execute one immutable full audit and the independent verifier.
- [x] Inspect candidate/component/control schemas, raw-context evidence
      ceilings, aggregation alternatives, metadata feasibility, and decision
      package language.
- [x] Confirm no depth, QC pass flag, role, weight, cohort, split, or downstream
      model-error artifact was read or written.
- [x] Run Trellis validation, check workflow, and `git diff --check`.
- [x] Update backend specs with the preflight evidence contract and commands.
- [x] Commit task-owned code, config, tests, task/spec artifacts; keep immutable
      `derived/` runs local under the repository's existing gitignore policy.
- [x] Present the collaborator decision package; do not archive the task or
      start QC v2 correction until the user confirms the scientific choices.

## Validation Commands

Run from repository root:

```bash
python -m unittest _common.tests.test_scs_ship_qc_v2_preflight
python -m py_compile \
  ncei/code/audit_scs_ship_qc_v2_preflight.py \
  ncei/code/verify_scs_ship_qc_v2_preflight.py

python ncei/code/audit_scs_ship_qc_v2_preflight.py \
  --config ncei/configs/scs_ship_qc_v2_preflight.yaml \
  --estimate-only

python ncei/code/audit_scs_ship_qc_v2_preflight.py \
  --config ncei/configs/scs_ship_qc_v2_preflight.yaml \
  --run-id <UTC_RUN_ID> \
  --confirm-audit

python ncei/code/verify_scs_ship_qc_v2_preflight.py \
  --run-dir ncei/derived/scs_ship_qc_v2_preflight/<UTC_RUN_ID>

python .trellis/scripts/task.py validate 08-05-scs-ship-sounding-qc-v2-preflight
git diff --check
```

## Review Gates

- Before full execution: frozen hashes/counts and all tests pass.
- Before interpreting raw context: every raw file hash matches lineage and
  evidence ceilings prohibit track/beam/crossover promotion.
- Before citing results: verifier reports `status=pass` and all output hashes
  match.
- Before correction implementation: collaborator decisions for label target,
  MRAR role, aggregation, crossover policy, and v1/v2 migration are recorded.
- Before commit: unrelated user changes remain untouched and unstaged.

## Risky Areas

- Treating raw record order as verified along-track, beam, or swath order.
- Using GEBCO disagreement to tune a future deletion threshold.
- Misclassifying real steep terrain as a source discontinuity.
- Treating point-count weighting as the automatically correct grid estimator.
- Promoting officially unknown vertical datum into an assumed common datum.
- Mixing the 52 aggregation replay differences with bad-ping evidence.
- Producing a decision field whose name or semantics silently changes roles.

## Rollback Points

- Hash, schema, or count drift: stop before output directory creation.
- Raw-file hash or row-range failure: preserve the failed run log and start a
  new run ID after fixing code; never overwrite.
- Evidence-ceiling violation or non-deterministic controls: fail verification
  and do not present the decision package.
