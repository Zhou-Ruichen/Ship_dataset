# SCS v2 sealed confirmation acquisition

## Goal

Identify three to five official South China Sea cruises using metadata and
deployment geometry only, prove as far as the available evidence permits that
they have never entered either the ship-data or downstream GGM repository, and
download their original archives as opaque immutable bytes for a future sealed
confirmation evaluation.

This task establishes acquisition provenance and an evidence ceiling. It does
not open confirmation sounding values, derive depth cells, perform QC, compare
against a reference product or model, or authorize a future evaluation.

## Frozen Scientific Boundary

- The spatial discovery domain is the existing SCS study rectangle
  `[105, 125) E x [0, 25) N`. Official deployment/track metadata, not sounding
  depth values, must establish intersection with this domain.
- Candidate ranking may use only official cruise metadata, archive metadata,
  documented field availability, spatial deployment, license/access terms,
  and evidence of non-exposure.
- Spatial deployment is evaluated from exact official polyline segments, not
  bbox overlap alone; in-domain official track length is a deterministic
  metadata-only ranking field.
- Before any archive is downloaded, the candidate identities, official URLs,
  metadata snapshots and hashes, inclusion/exclusion rules, current exposure
  registries, commands, and selected three-to-five candidate set must be frozen
  in a metadata-only discovery receipt.
- Downloaded archives remain opaque. This task may hash bytes and inspect
  transport headers or an official sidecar file list, but it must not parse
  sounding records, inspect depth values, derive bboxes from soundings, or
  calculate any statistic from the archive contents.
- The sealed directory must not be referenced by existing pipeline globs,
  model configs, QC scripts, residual scripts, notebooks, or figure producers.

## Required Exposure Sets

The audit must freeze and compare against, at minimum:

1. the 19 current official JAMSTEC cruises represented by the 58 contributor
   files in the verified lineage v2 run;
2. the 12 historically exposed downstream external candidate groups and their
   official identities;
3. all cruise/archive/source identifiers found in current tracked files,
   relevant git history, immutable manifests and reports in both repositories;
4. MRAR's retained delivery/archive metadata and its unresolved possible
   upstream membership.

Exact ID, alias, leg, vessel/date, archive member, spatial deployment, URL and
hash evidence must be used for deduplication. A renamed leg or archive from an
exposed cruise is not a new confirmation candidate.

`ever_read_by_repo=false` is allowed only when the defined current-tree,
history, manifest, task, output-receipt and figure-source searches all return
no matching identity/archive evidence. If the search cannot close, use
`unknown`, not false.

## Candidate Requirements

- The final sealed set contains three to five official cruises.
- Each selected cruise has an official cruise ID, official date or date range,
  official deployment bbox/track evidence, instrument or sonar type, an
  original-archive URL, archive date/version when available, and license or
  access terms.
- Prefer archives whose official documentation retains the largest supported
  subset of `time`, `line`, `navigation`, `ping`, `beam`, `quality_flag`, and
  `vertical_datum`. Missing fields remain explicit unknowns.
- Prefer post-MRAR-delivery and post-exposure-freeze observations when
  available because chronology can establish a stronger non-overlap claim;
  this is a preference, not permission to relax field/provenance requirements.
- A candidate with known overlap with the current 19, exposed 12, or any prior
  repository consumer is excluded. Unknown possible MRAR overlap is preserved
  and does not get silently converted to independence.
- Discovery failures and rejected candidates remain in the registry with a
  machine-readable exclusion reason.

## MRAR Bounded Supplement

Perform exactly one supplementary direct-evidence pass over:

- local `M.rar` archive metadata and retained member names;
- adjacent README, license and delivery artifacts;
- relevant git/history records in this repository;
- immediately adjacent retained delivery files.

Only a direct README/metadata statement, exact fingerprint, retained source
mapping, or equivalent artifact-level link may connect `M.rar` to Tscs,
RIAM, or Uehara. If none exists, record and stop with:

```text
identity_status=not_recoverable
source_independence=unknown
```

The task must not expand into open-ended external attribution.

## Contractual Outputs

Under a new immutable run directory, produce at least:

```text
candidate_registry.parquet
sealed_archive_manifest.tsv
exposure_registry.parquet
metadata_evidence_registry.tsv
query_command_ledger.jsonl
negative_result_ledger.tsv
mrar_bounded_followup.tsv
audit_report.md
audit_manifest.json
verification.json
```

`candidate_registry.parquet` contains every inspected candidate and at least:

```text
official_cruise_id
archive
date
instrument
bbox
file_count
available_fields
vertical_datum_status
overlap_with_current_19
overlap_with_exposed_12
possible_MRAR_overlap
ever_read_by_repo
sealed_status
exclusion_reason
```

Each factual field must have an evidence path/URL and an explicit status. The
sealed archive manifest is one row per physical downloaded archive and records
candidate ID, original URL, resolved URL, filename, bytes, SHA256, remote
version/date/ETag/Last-Modified when available, license, download command,
download time, and immutable local path.

## Verification Requirements

- Record every metadata query and archive download command exactly, including
  timestamps, parameters, response status and output path.
- Record path, row count, complete schema, bytes and SHA256 for every
  machine-readable artifact and every sealed archive.
- A negative-result ledger must cover failed metadata sources, excluded
  candidates, duplicate/alias findings, unresolved license or field claims,
  exposure-search misses, and the terminal MRAR result.
- An independent verifier reopens metadata outputs, rehashes all evidence and
  archives, validates schemas/enums/keys/counts, recomputes overlap decisions
  from the frozen exposure registry, confirms that the selected count is three
  to five, and checks that no sounding-value reader or prohibited output was
  used before writing `verification.json` with `status=pass`.

## Acceptance Criteria

- [ ] Discovery criteria, SCS geometry, exposure sets, aliases, query plan and
  stop rules are frozen before candidate archive download.
- [ ] The current 19 cruises and exposed 12 groups close exactly against their
  previously verified source artifacts and hashes.
- [ ] Every candidate is deduplicated by ID/alias/leg/vessel-date/archive and
  spatial evidence, not by filename alone.
- [ ] Exactly three to five candidates meet the metadata, access, license and
  non-exposure gates and are downloaded as opaque sealed archives.
- [ ] No selected cruise has known overlap with either exposed set or any prior
  repository consumer; unknown evidence is reported literally.
- [ ] Candidate and archive registries contain all required fields, evidence,
  statuses, paths, row counts, schemas and SHA256 values.
- [ ] Downloaded bytes are immutable, outside existing pipeline discovery
  paths, and have never been parsed for sounding/depth values in this task.
- [ ] The bounded MRAR pass either finds a direct artifact link or terminates
  at `not_recoverable`/`unknown` without expanding scope.
- [ ] Query/download command and negative-result ledgers are complete.
- [ ] Independent `verification.json` reports `status=pass`.

## Prohibited Actions

- Select or rank cruises using model predictions, GGM/PINN output, GEBCO,
  product residuals, QC candidates, published figures, or any sounding error.
- Rename an already exposed cruise, leg, archive or geography as confirmation.
- Modify existing v1/v2 depths, candidate membership, QC, split, or data roles.
- Automatically delete or relabel the 97, 171, or 123 anomalous/heterogeneous
  cells.
- Perform crossover adjustment, gridding, cell aggregation, error metrics,
  GGM execution, or PINN training.
- Read candidate depth records before sealing, or parse them after sealing
  within this acquisition task.

## Open Decision

- Whether immutable metadata-only candidate selection must receive a separate
  human approval before the download stage, or whether an explicit CLI
  confirmation bound to the frozen candidate-registry SHA256 is sufficient.

## Stage A.1 Authorization (2026-08-06)

The user accepted Stage A commit `948519b`, withheld Stage B authorization,
and authorized one new immutable metadata-only preseal run. Stage A.1 may GET
official NCEI Cruise File List HTML and issue HEAD requests to physical object
URLs found in those listings. It must not GET a physical object body, issue a
Range request, parse candidate data, generate cells, contact NCEI, or perform
any reference/product/model comparison.

The revised comparison cohort is every accepted Stage A record that starts in
2018 or later, has official SCS track intersection, has an official NCEI file
list directory, has no current-19 or exposed-12 overlap, and has
`ever_read_by_repo=false`. There is no candidate-count cap. Ranking is frozen
before network access as: MRAR delivery chronology class, observation end date
descending, official SCS track length descending, cruise ID ascending.

The run must report at least `EQT20210702`, `TN358`, `TN354`, `EQT190012`, and
`TN352`; the frozen accepted registry additionally yields `SR1912`,
`EQT180002`, and `TN359`. For every selected row:

```text
confirmation_candidate_v2_H_MRAR_out=pending_seal_and_processing
confirmation_candidate_v2_W_MRAR_in=blocked_source_independence_unknown
confirmation_role_eligible=false
```

Required A.1 outputs are `physical_object_lock.parquet`,
`per_cruise_byte_budget.tsv`, `revised_candidate_registry.parquet`,
`revised_preseal_lock.json`, `audit_manifest.json`, and `verification.json`.
If only a directory URL is available, any HEAD fails, or Content-Length is
missing, the affected physical lock is incomplete and Stage B remains blocked.
Even a complete physical lock does not authorize Stage B.

## Stage A.2 Authorization (2026-08-06)

The user accepted Stage A.1 commit `b6de3a6` but did not authorize Stage B.
Stage A.2 is an offline final download lock. Its immutable primary acquisition
set is exactly, and only:

```text
EQT20210702
EQT190012
EQT180002
TN352
```

`SR1912` is excluded for negligible SCS track length. `TN359` is excluded for
cost disproportionate to SCS coverage. `TN358` and `TN354` are deferred for
the current confirmation because of their combined known cost. None may
replace the primary set after model or product results are observed.

The two TN352 `.fnv` rows lacking HEAD Content-Length may be recovered only
from already frozen official directory HTML. Only a pure integer listing size
is exact enough for the lock; rounded `K/M/G` display values are not accepted.
Failure to recover either row blocks TN352 and does not activate a replacement.

The final aggregate cap is exactly `12 GiB = 12,884,901,888 bytes`. Stage A.2
must freeze every direct URL, filename, role, format, exact bytes plus source
status, Last-Modified, ETag plus status, the physical-lock SHA256, per-cruise
budget, and the ordered primary IDs. It may generate and verify a Stage B
dry-run plan but must perform no network request or download.

The branch and role ceiling remains:

```text
v2-H=pending_seal_and_processing
v2-W=blocked_source_independence_unknown
confirmation_role_eligible=false
maximum_post_download_role=sealed_unprocessed
```

Any future Stage B execution requires a separate authorization receipt bound
to the exact A.2 manifest, verification and physical-lock hashes. Stage C is a
separate authorization required before archive opening or source-internal
processing.

## Stage B.0 Authorization (2026-08-06)

The user accepted Stage A.2 run `20260805T221441Z` and commit `7359f47`, but
withheld every physical-object GET, Range GET and body read. Stage B.0 may only
harden and test the future executor, publish an offline readiness receipt, and
stop before acquisition.

The future GET response must be rejected before its first body read unless its
resolved URL remains the exact locked HTTPS `data.ngdc.noaa.gov` host/path and
its Last-Modified header is present and exactly equals the frozen value. ETag
remains officially unknown and is not invented as a gate.

A future authorization receipt must bind the acquisition run ID, fixed output
root, downloader and independent verifier SHA256 values, accepted A.2
manifest/verification/final-lock/physical-lock SHA256 values, ordered IDs and
12 GiB cap. The run ID is one safe path segment; the only output location is
`ncei/archive/scs_v2_sealed_confirmation/<ACQUISITION_RUN_ID>`.

The independently implemented Stage B verifier must reopen and rehash all 768
opaque objects, close URLs, paths, cruises, bytes, object SHA256 values and
Last-Modified values against A.2, reject any parser use, and retain
`content_parsed=false`, `role=sealed_unprocessed`,
`confirmation_role_eligible=false`. A failed acquisition writes
`failure_receipt.json`, retains partial/completed bytes, and is never sealed or
used to replace a candidate.

Stage B.0 acceptance requires offline unit tests, downloader dry-run
`network_request_count=0`, an inactive authorization template and independent
readiness `verification.json` with `status=pass`. Passing Stage B.0 does not
authorize Stage B or Stage C.

## Stage B Authorization (2026-08-06)

The user authorized one opaque acquisition using execution-code commit
`c3871f54f8041fcb2d3ae18cd124d3b5223c118f`, Stage A.2 run
`20260805T221441Z`, and Stage B.0 readiness run `20260805T224911Z`. The
authorization is limited to the immutable ordered four-cruise, 768-object,
`9,626,893,507-byte` lock. It permits physical-object GET and body storage but
does not permit archive decompression, member enumeration, sounding parsing,
cell generation, comparison, model execution, candidate replacement or Stage
C access.

The authoritative successful acquisition run is `20260805T230449Z`. Its
independent verifier reopened and rehashed all 768 objects and reported
`status=pass`, with all 768 Last-Modified values closed against Stage A.2. Its
maximum role is `sealed_unprocessed`; `content_parsed=false`,
`confirmation_role_eligible=false`, `stage_c_authorized=false`, and
`access_allowed=false` remain binding.

The preceding run `20260805T225949Z` is retained as `failed_unsealed` after the
environment proxy rejected the first tunnel before any response body was
read. The successful retry used a new authorization receipt and the
user-selected local sing-box 2082/HK-DC route without changing the frozen
object set.
