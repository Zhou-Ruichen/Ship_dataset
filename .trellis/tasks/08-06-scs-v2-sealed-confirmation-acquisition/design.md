# Technical design

## Boundary and claim

This task produces a sealed acquisition package, not a confirmation metric and
not an automatic confirmation-role assignment. The maximum claim after a
successful run is:

> Three to five official SCS cruise archives were selected using frozen
> metadata-only rules, found unexposed under the defined two-repository audit,
> downloaded as opaque bytes, hashed, isolated, and independently verified.

Any unknown MRAR overlap, datum, license or archive-field evidence remains
unknown and limits later use.

## Two immutable stages

### Stage A: metadata discovery and pre-seal lock

Output root:

```text
ncei/derived/scs_v2_sealed_confirmation/discovery/<DISCOVERY_RUN_ID>/
```

The discovery producer:

1. validates the config and frozen lineage/downstream receipts;
2. snapshots both repository HEADs, dirty status and relevant untracked task
   paths without modifying either tree;
3. builds the exposure registry from current files, history, manifests,
   receipts, tasks, figure producers and archive names/hashes;
4. performs the one bounded MRAR follow-up;
5. queries only official NCEI/JAMSTEC metadata and persists byte-identical
   responses plus headers and SHA256;
6. normalizes candidate IDs, aliases, legs, vessel/date, archive URLs and
   official track geometry;
7. applies hard gates and deterministic metadata-only ranking;
8. writes candidate/negative/query/evidence registries and
   `preseal_lock.json`;
9. publishes atomically only after a discovery verifier passes.

No candidate archive is downloaded in Stage A.

### Stage B: opaque acquisition

Output root:

```text
ncei/archive/scs_v2_sealed_confirmation/<ACQUISITION_RUN_ID>/
```

Stage B requires the exact Stage A `preseal_lock.json` and verification SHA256.
It downloads only the selected URLs and filenames enumerated by that lock. A
download goes to `*.part`, transport headers are stored, bytes and SHA256 are
checked, then the file is atomically renamed and made read-only.

The acquisition producer may stream opaque bytes for SHA256. It must not import
or invoke archive/sounding readers such as `zipfile`, `tarfile`, `rarfile`,
`py7zr`, MB-System, xarray/netCDF readers, or format-specific sonar parsers.
It does not enumerate archive members. Official file-list metadata supplies
`file_count` and supported field claims.

The sealed directory is outside existing pipeline raw globs and contains a
machine-readable lock stating that future access requires a separate task.

## Discovery sources and stop rule

Primary pass:

- one bounded NCEI ArcGIS geometry query for the frozen SCS rectangle;
- per-candidate official ISO/XML metadata and official cruise file-list
  metadata, without downloading sounding files.

Secondary pass:

- one bounded JAMSTEC DARWIN/Data DOI metadata search for SCS-intersecting
  bathymetry cruises not returned by NCEI or with materially stronger field
  documentation.

Stop after both passes and all candidates needed to determine the first five
qualified records have been checked. If fewer than three qualify, publish a
negative/shortfall discovery run and do not download or weaken requirements.

## Candidate decision model

### Hard inclusion gates

1. Official cruise ID and direct official metadata record exist.
2. Official track/deployment geometry intersects `[105,125) x [0,25)`.
3. Original archive has a stable official download URL and public/scientific
   access terms suitable for local preservation.
4. No ID/alias/leg/vessel-date/archive/geometry overlap with current 19 or
   exposed 12.
5. The complete exposure audit supports `ever_read_by_repo=false` rather than
   `unknown`.
6. The archive can be downloaded without querying or deriving sounding values.

### Metadata-only priority tuple

Sort qualified candidates by this fixed tuple:

```text
1. stronger possible-MRAR non-overlap evidence
2. greater official polyline length inside the frozen SCS rectangle
3. raw/as-collected archive over processed-only delivery
4. count of officially documented available fields among
   time,line,navigation,ping,beam,quality_flag,vertical_datum
5. known vertical datum over officially unknown datum
6. stable version/date/license metadata completeness
7. official_cruise_id ascending as the final tie break
```

Spatial geometry is both a hard deployment gate and a metadata-only coverage
descriptor. Exact polyline clipping, including dateline unwrapping, prevents a
global bbox or edge-only transit from outranking a cruise deployed within the
study rectangle. It is not a proxy for expected model difficulty. No depth,
residual, product or model value enters this tuple.

Select at most five. A candidate with `possible_MRAR_overlap=unknown` may be
sealed for preservation, but it must retain `confirmation_role_eligible=false`
until downstream resolves that evidence ceiling. Acquisition is not a role
promotion.

## Exposure audit

`exposure_registry.parquet` has one row per exposed identity/archive/source
record with repository, snapshot HEAD, path, historical/current state, aliases,
cruise/leg, archive filename/URL/hash when available, consumer class and
evidence hash.

For each candidate, `ever_read_by_repo` combines:

- exact and normalized ID/alias search in both current trees;
- `git log --all --name-only`, `git log -S`, and `git log -G` evidence;
- task, config, manifest, report, notebook and figure-producer searches;
- current derived-output receipt/manifests where available;
- exact archive URL/name comparison;
- after download, SHA256 comparison against existing archive hashes and
  size-matched unmanifested archive candidates.

Any positive match yields `true` and exclusion. An incomplete search yields
`unknown` and exclusion. Only all required checks passing yields `false`.

## Output schemas

### Candidate registry

One row per inspected candidate. In addition to the user-required fields, it
contains official metadata IDs/URLs/hashes, aliases, provider, vessel, geometry
basis, field-evidence basis, license evidence, exposure result, selection rank,
confirmation-role ceiling and paired evidence statuses.

Closed values:

```text
overlap_*: true | false | unknown
possible_MRAR_overlap: true | false | unknown
ever_read_by_repo: true | false | unknown
sealed_status: excluded | selected_unsealed | sealed | download_failed
```

### Sealed archive manifest

One row per physical downloaded archive with discovery-lock SHA, candidate ID,
original/resolved URL, filename, immutable local path, bytes, SHA256, official
file count, response ETag/Last-Modified/date, version, license URL/hash,
download command/time/status, and an explicit `content_parsed=false` field.

### Evidence and negative ledgers

- `metadata_evidence_registry.tsv`: one row per official response or local
  frozen receipt, with request URL, path, MIME type, bytes, SHA256 and role.
- `query_command_ledger.jsonl`: one JSON object per metadata query, HEAD request,
  repository search or download command with timestamp, exit/HTTP status and
  output hash.
- `negative_result_ledger.tsv`: one row per failed source, duplicate, exclusion,
  ambiguous exposure, missing license/field/datum, download failure or shortfall.
- `mrar_bounded_followup.tsv`: fixed checklist and terminal conclusion.

## Verification

The discovery verifier independently recomputes set closure, ID normalization,
SCS geometry intersection, exposure decisions, hard gates, deterministic rank,
selected count and prohibited-field absence from frozen metadata responses.

The acquisition verifier:

- verifies the Stage A manifest, preseal lock and discovery verification hashes;
- rehashes every archive and evidence file;
- checks URL/filename/count/license closure;
- confirms candidate registry bytes are unchanged;
- statically rejects archive/depth parser imports and prohibited commands;
- rejects output columns or paths containing cell depth, residual, model,
  GEBCO, correction, QC-deletion, split mutation or crossover products;
- writes `verification.json` only when every check passes.

## Failure and rollback

- Discovery failure leaves no published discovery run.
- A valid discovery with fewer than three candidates is a retained negative
  result; Stage B stays blocked.
- Download failure is recorded without substituting a new candidate after the
  preseal lock. A new candidate set requires a new discovery run.
- Stage B never overwrites an existing run or archive. Partial `*.part` files
  remain outside the contractual manifest until a controlled retry.
- Existing v1/v2 data, QC, split, GGM/PINN and downstream worktree are read-only.
