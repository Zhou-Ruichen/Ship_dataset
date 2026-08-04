# Implementation Plan

## Ordered Checklist

- [x] Freeze input hashes, union closure, accepted enums, and forbidden path/
  column rules in the audit script.
- [x] Inventory exact SCS contributors in JAMSTEC and MRAR upstream products;
  prove the strict-primary JAMSTEC depth join is exact before raw replay.
- [x] Parse the local official JAMSTEC DARWIN PDFs and carry PDF hashes,
  cruise-report URLs, and source paths into the produced evidence ledgers.
- [x] Resolve candidate cruise versus leg identities and official/observed
  envelope comparisons without using filenames as official evidence.
- [x] Implement the cell contributor join, raw file hashing, row-ID treatment,
  five-state field statuses, vertical ledger, and P0 ledger.
- [x] Implement targeted JAMSTEC and MRAR replay using the repository's existing
  coordinate, QC, cell-ID, precedence, and aggregation definitions.
- [x] Compute within-file, between-file, and between-cruise NMAD only where the
  necessary independent units exist; mark undefined layers explicitly.
- [x] Write all contractual outputs and report to an immutable UTC run
  directory, plus a manifest containing input and output SHA256 values.
- [x] Run an independent verifier over produced artifacts, not in-memory
  objects, and record closure/diff/schema/enum results.
- [x] Run narrow unit tests for cell assignment, statuses, contributor joins,
  and forbidden-input guards.
- [x] Review changed files, update project specs only if a reusable invariant
  was discovered, commit scoped task changes, and archive the Trellis task.

## Validation Commands

```bash
cd /mnt/data2/00-Data/ship
python -m unittest <audit test module>
python ncei/code/audit_scs_upstream_lineage.py \
  --downstream-union <frozen union> \
  --counts-closure <frozen closure> \
  --downstream-manifest <frozen manifest> \
  --external-group-manifest <frozen group manifest> \
  --confirm-audit
python ncei/code/verify_scs_upstream_lineage_audit.py --run-dir <new run dir>
sha256sum <contractual deliverables>
git diff --check
```

## Review Gates

- Do not proceed past input loading on hash or cohort drift.
- Do not assign `verified_from_source_metadata` without a cited official source
  that states or directly encodes that field.
- Do not call a leg exact when the cell-to-leg link is absent or conflicting.
- Do not promote a replayed derived index to raw row identity.
- Do not inspect downstream files beyond the four frozen handoff inputs.
- Stop and report rather than relaxing the five-state vocabulary or converting
  unknown datum fields to assumed defaults.
