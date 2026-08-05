# SCS v2 Sealed Confirmation Acquisition

## 1. Scope

This contract separates confirmation acquisition from confirmation evaluation.
Stage A may discover official South China Sea cruises using official metadata
and deployment geometry, audit their exposure, and freeze a candidate receipt.
Stage B requires separate user approval and is not implied by a passing Stage A.

The maximum Stage A claim is that candidate identities and official archive
access URLs were selected under frozen metadata-only rules. It does not claim
that archives are independent, usable, correct, or suitable for a confirmation
role unless the corresponding evidence fields say so.

## 2. Stage A Signature

Run from the repository root:

```bash
python ncei/code/discover_scs_v2_sealed_confirmation.py \
  --config ncei/configs/scs_v2_sealed_confirmation_stage_a.yaml \
  --run-id <YYYYMMDDTHHMMSSZ> --confirm-stage-a

python ncei/code/verify_scs_v2_sealed_confirmation.py \
  --run-dir ncei/derived/scs_v2_sealed_confirmation/discovery/<RUN_ID>
```

The output run is immutable. An existing run ID or verification receipt must
never be overwritten.

## 3. Scientific Boundary

- Discovery geometry is `[105,125) E x [0,25) N` and comes from official
  cruise track/deployment metadata, never sounding coordinates.
- Candidate qualification uses exact official polyline-segment intersection,
  including dateline unwrapping. A broad or dateline-spanning bbox alone is
  descriptive and cannot establish SCS deployment.
- Ranking uses only official identity/date/instrument/geometry/file-count,
  documented archive format/field availability, license/access evidence,
  MRAR chronology, and prior-exposure evidence.
- Among otherwise eligible records, greater official track length inside the
  frozen SCS rectangle ranks ahead of edge-only transits. This length is
  recomputed from official metadata geometry, not sounding navigation.
- Zero selected candidates is valid. Missing evidence remains unknown and
  requirements are not weakened to reach a target count.
- `sealed_status=selected_unsealed` means only that Stage A recommends the
  metadata record for separate Stage B review. No bytes have been sealed.
- `confirmation_role_eligible=true` additionally requires supported MRAR
  non-overlap. Stage B acquisition alone cannot promote the role.

## 4. Exposure Contract

Every candidate is compared against:

1. the frozen 19 official JAMSTEC cruises;
2. the frozen 12 downstream-exposed external groups;
3. identity-only current-tree and Git-history searches in both repositories;
4. retained MRAR source evidence.

Identity searches capture only paths, commit IDs and command hashes. They must
not read or select on model, product, GEBCO or QC residual values. A positive
identity hit excludes the candidate. An incomplete search yields
`ever_read_by_repo=unknown`, which also excludes it.

The current-tree check includes tracked, untracked and ignored file names so a
raw, QC or derived file named for a cruise cannot escape Git-only searches.
The names-only inventory is hashed as `repository_file_inventory.tsv`; this
step does not open file contents.

MRAR remains:

```text
identity_status=not_recoverable
source_independence=unknown
```

unless a direct artifact mapping, README, exact fingerprint or retained source
inventory proves otherwise. A cruise observed after the frozen M.rar delivery
cutoff may be marked chronological non-overlap; earlier absence is unknown.

## 5. Stage A Outputs

```text
candidate_registry.parquet
exposure_registry.parquet
repository_file_inventory.tsv
metadata_evidence_registry.tsv
query_command_ledger.jsonl
negative_result_ledger.tsv
mrar_bounded_followup.tsv
preseal_lock.json
audit_report.md
audit_manifest.json
verification.json
metadata_evidence/
```

`candidate_registry.parquet` includes all user-required fields and a paired
five-level status for each factual field:

```text
known
officially_unknown
not_recoverable
inferred_from_filename
verified_from_source_metadata
```

The manifest records absolute path, row count, complete schema, bytes and
SHA256 for every machine-readable output. Raw official metadata responses are
also byte-frozen and hashed.

## 6. Hard Prohibitions

Stage A must not:

- request, download, list or enumerate a candidate archive;
- import archive or sounding readers;
- read candidate sounding/depth values or derive geometry from them;
- generate a cell, grid, correction, crossover adjustment or deletion list;
- access or compute GEBCO, product, QC-error, GGM, PINN or model residuals;
- modify existing v1/v2 depths, QC, cohorts, splits or anomaly membership;
- authorize Stage B.

The independent verifier rejects any nonzero archive/depth/cell/comparison
counter, prohibited query role, archive-like evidence file, forbidden output
column/path, selected exposure overlap, hash mismatch or schema drift.

## 7. Required Verification

```bash
python -m unittest _common.tests.test_scs_v2_sealed_confirmation
python -m py_compile \
  ncei/code/discover_scs_v2_sealed_confirmation.py \
  ncei/code/verify_scs_v2_sealed_confirmation.py
```

A Stage A result is citable only when its independent `verification.json`
contains `status=pass`. After that receipt is written, execution stops and
waits for explicit Stage B approval.
