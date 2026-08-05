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

## 8. Stage A.1 Physical Metadata Lock

Stage A.1 is allowed only after a passing Stage A receipt and explicit user
authorization. It creates a new immutable discovery run and does not alter the
accepted Stage A run.

Permitted network operations are limited to official NCEI Cruise File List
HTML `GET` requests and physical-object `HEAD` requests. Before reading a file
list body, the producer verifies that the resolved URL is still an HTTPS
directory on `data.ngdc.noaa.gov` and that the response is HTML. A physical
object request must use HEAD, must not send Range, must not read a response
body, and must not fall back to GET.

The revised comparison cohort is the complete set of official, SCS-intersecting,
unexposed candidates beginning in 2018 or later. It has no count cap. Sort by
chronological MRAR non-overlap class, observation date descending, official
in-domain track length descending, then official cruise ID. This order is
frozen in the hashed config before file-list access.

For each object, retain the official cruise ID, filename, direct and resolved
URL, Content-Length, ETag, Last-Modified, inferred format/role and HEAD result.
Missing optional headers remain unknown. Per-cruise and all-candidate byte
budgets must state whether their totals are complete. Directory-only access,
HEAD failure or missing Content-Length blocks Stage B without invalidating a
correct negative Stage A.1 receipt.

Conditional branch labels are fixed as follows for the selected cohort:

```text
confirmation_candidate_v2_H_MRAR_out=pending_seal_and_processing
confirmation_candidate_v2_W_MRAR_in=blocked_source_independence_unknown
confirmation_role_eligible=false
```

An independent verifier rehashes the accepted Stage A inputs and A.1 outputs,
recomputes the chronology-first cohort and rank, reconstructs object URLs from
retained directory HTML, closes GET/HEAD methods against the query ledger, and
recomputes byte budgets. A passing A.1 receipt still has
`stage_b_authorized=false` and requires separate user approval.

## 9. Stage A.2 Final Download Lock

Stage A.2 is an offline refinement of a passing A.1 receipt. It accepts an
explicitly ordered primary cruise set and does not rerank or replace it. Every
excluded/deferred A.1 candidate remains machine-readable with a fixed reason,
`replacement_allowed=false`, and `model_or_product_result_used=false`.

A missing HEAD Content-Length may be filled only by a retained official file
listing whose size token is an exact base-10 integer. Human-readable rounded
sizes such as `3.5K` are insufficient for a byte lock. The object row records
whether bytes came from HEAD or listing metadata and retains the evidence
path/SHA256.

The A.2 lock freezes direct URLs, relative destinations, roles, formats, exact
bytes, Last-Modified, ETag/status, primary object-lock SHA256, exact total and
an aggregate binary-byte cap. A dry-run plan must close one-to-one against the
physical lock, have unique destinations and record zero downloads.

The downloader's execution branch is not authorized by A.2. Before any GET it
requires a separate authorization receipt bound to the A.2 run ID, manifest,
verification, physical-lock hash, ordered primary IDs and cap. Authorized
downloads remain opaque, length-checked, hashed and `sealed_unprocessed`.
Archive access and source-internal processing require a separate Stage C.
