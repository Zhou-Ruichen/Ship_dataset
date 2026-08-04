# Implementation Plan

- [x] Freeze and record SHA256 for the union, lineage/replay artifacts, frozen
      domain context, seven product grids, and three GEBCO TID grids.
- [x] Add the YAML config with exact paths, hashes, domain, product sampling,
      TID groups, families, and coverage thresholds.
- [x] Write synthetic unit tests first for:
  - aligned 4x4 median aggregation and 1-minute exact sampling;
  - positive-up elevation to positive-down depth conversion;
  - seven-product and family-balanced median/NMAD;
  - cell area and unit-sphere nearest distance;
  - TID disjoint grouping/fraction closure;
  - forbidden input columns/path tokens and immutable run guards.
- [x] Implement the bounded audit driver:
  - config and frozen-hash validation;
  - five-column union read plus lineage/replay key closure;
  - one-product-at-a-time SCS subsetting and 1-minute aggregation;
  - three-generation TID composition;
  - per-cell diagnostic and summary metrics;
  - full-ocean coverage/distance/block products;
  - immutable outputs, report, and manifest.
- [x] Implement the independent verifier and recompute every acceptance
      invariant from persisted artifacts.
- [x] Run `--estimate-only` and confirm expected counts/workload.
- [x] Run unit tests and Python compilation checks.
- [x] Execute one immutable full bounded audit and then the independent
      verifier.
- [x] Inspect output schemas, key counts, product/TID completeness, distance
      distribution, non-positive depths, consensus spread, and replay closure.
- [x] Confirm no downstream prediction/residual/error/metric file or column was
      read and no decision/weight column was written.
- [x] Run `git diff --check` and the Trellis check workflow.
- [x] Update backend specs with the new diagnostic-only contract and commands.
- [x] Commit task-owned changes, finish, and archive the Trellis task.

## Validation Commands

Run from repository root:

```bash
python -m unittest _common.tests.test_scs_product_consistency_coverage
python -m py_compile \
  ncei/code/audit_scs_product_consistency_coverage.py \
  ncei/code/verify_scs_product_consistency_coverage.py

python ncei/code/audit_scs_product_consistency_coverage.py \
  --config ncei/configs/scs_product_consistency_coverage.yaml \
  --estimate-only

python ncei/code/audit_scs_product_consistency_coverage.py \
  --config ncei/configs/scs_product_consistency_coverage.yaml \
  --run-id <UTC_RUN_ID> \
  --confirm-audit

python ncei/code/verify_scs_product_consistency_coverage.py \
  --run-dir ncei/derived/scs_product_consistency_coverage/<UTC_RUN_ID>

git diff --check
```

## Review Gates

- Before the full run: hashes, domain closure, and all unit tests pass.
- Before citing results: `verification.json` reports `status=pass` and all
  input/output hash checks are true.
- Before commit: no unrelated user changes are staged or modified.

## Risky Areas

- Global NetCDF orientation and 0-360 longitude handling.
- Exact 4x alignment at SCS bounds.
- Memory pressure when reading 15-arcsecond subsets.
- Treating GEBCO-family members as independent votes.
- Confusing mature-product completeness with ship-observation coverage.
- Accidentally allowing downstream error-derived columns into the run.
