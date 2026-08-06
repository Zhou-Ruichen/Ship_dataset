# SCS v2 Stage C.0 source-internal processing planning

## Goal

Freeze a reproducible, source-internal protocol for a future Stage C read of
the accepted opaque acquisition run. This planning task may inspect only the
Stage B manifest, verification, access lock, filenames, object roles and
already retained official metadata. It does not authorize opening any sealed
object body.

The maximum future Stage C claim is that source-internal sounding candidates
and provenance were extracted under a frozen parser, fixture, QC and lineage
contract. It is not a confirmation metric, a vertical-datum correction, or a
model/product evaluation.

## Frozen input

Only this acquisition run is permitted:

```text
/mnt/data2/00-Data/ship/ncei/archive/scs_v2_sealed_confirmation/20260805T230449Z
```

It is bound by:

```text
sealed_archive_manifest.parquet SHA256 = 9fafb163a6fe2818d96a0c9bb0ed49afc98a8b0850979d5783b1882139702f94
verification.json SHA256              = d0d868f560c628bd24d1d52d399c7ed9d03af337be72967a874a5c26db7c2e86
access_lock.json SHA256                 = 75c290a9b4f17ed2b529a372417f4fd18770c08cf66836c07ddde3bb90e00a6f
objects                                  = 768
bytes                                    = 9626893507
cruises                                  = EQT20210702,EQT190012,EQT180002,TN352
```

Any path, hash, row-count, byte-count, cruise-order or role drift blocks Stage
C before a sealed object body is opened.

## Requirements

### Isolation and authorization

- The Stage B root and all sealed objects remain read-only. Future work mounts
  or opens them read-only and records before/after file metadata and hashes.
- All decompressed work files, parser output, logs and Parquet outputs go to a
  new immutable run under
  `ncei/derived/scs_v2_sealed_confirmation/stage_c/<PROCESSING_RUN_ID>`.
- Publication is atomic from a sibling temporary directory. No output may be
  written into the Stage B root or an existing Stage C run.
- Stage C requires a separate active authorization receipt with exact parser,
  environment, fixture, QC, schema, verifier and input hashes. The template
  produced here remains inactive.

### Parser and field evidence

- The target parser is MB-System `5.8.3beta16`, tag commit
  `1d9a52ce076c3c3c5f0150b9bcaa30fa108c7422`, format 58. Its executable
  environment digest must be frozen and its format-58 behavior must pass the
  independent fixture contract before authorization.
- `.mb58.gz` is the only primary sounding source. It may be decompressed only
  into the new derived run after authorization.
- `.fnv` may be read only for time/navigation cross-checks. `.inf` may be read
  only for source-internal format/count/metadata and direct datum evidence.
  `.fbt` is not authorized in the initial Stage C contract because it is a
  duplicate processing sidecar, not an independent sounding source.
- Official cruise identity comes only from the locked Stage B/A.2 mapping.
  Filename stems are retained as source filenames, not promoted to line,
  ping, time, datum or quality identities.
- Parser ping count and beam number are named as parser-derived indices. They
  are not called native ping/beam IDs unless the source explicitly provides
  that identity.
- Time, navigation, heading and binary native-validity state may be `known`
  only when the fixture-verified parser emits them. Exact native quality code,
  line ID, horizontal datum and vertical datum remain unknown unless direct
  source metadata establishes them.
- Every factual field has an evidence column and a paired status from:
  `known`, `officially_unknown`, `not_recoverable`,
  `inferred_from_filename`, `verified_from_source_metadata`.

### Scientific conventions

- Longitude is decimal degrees normalized to `[-180, 180)`; latitude is
  decimal degrees in `[-90, 90]`.
- Time is nullable UTC with microsecond precision. Missing or unparsable time
  stays null; cruise date and filename timestamps do not fill it.
- `depth_m_positive_down` is float64 meters, positive downward.
  `elev_m = -depth_m_positive_down`. No observed-value sign heuristic is
  allowed; the direction is accepted only after independent fixture closure.
- Parser nulls map to Arrow null/NaN according to the schema. Zero is never a
  missing-value sentinel.
- Vertical datum cannot be inferred from mean depth, crossover, GEBCO,
  another product, model residual or fitted bias. If no direct evidence is
  recovered, it remains `officially_unknown` at sounding and cell-cruise
  levels.

### Source-internal QC

- QC rules and thresholds are frozen in `research/source-internal-qc.yaml`
  before any candidate depth is read.
- Hard cell eligibility uses only parser success, native validity, finite and
  in-range navigation, finite positive-down depth in `(0, 12000] m`, and a
  valid nonnegative parser beam index.
- Time-order, navigation-speed, within-ping and along-track discontinuity
  checks are review signals only. They do not change cell eligibility, delete
  soundings, remove lines/cruises or tune thresholds.
- There is no global 3STD rule, reference-product filter, route deletion,
  crossover adjustment, tide/datum fit or bias correction.

### Lineage, aggregation and roles

- The atomic output is one row per parsed sounding/beam, including rejected
  and review-labelled rows. Source object SHA256, parser command/environment,
  cruise, parser ping/beam indices and evidence statuses are preserved.
- One-arc-minute aggregation groups only by
  `(cell_id, official_cruise_id)`. Median, NMAD and other summaries are
  computed from all individually eligible beam depths, never from chunk,
  file or cruise medians.
- A cell touched by multiple cruises retains multiple rows. No pooled
  cross-cruise depth is produced.
- All four cruises are held out from training, tuning, calibration, threshold
  selection and exclusion-rule design.
- Branch `v2-H` is a held-out MRAR-out candidate branch. Branch `v2-W`
  remains `blocked_source_independence_unknown`; global
  `confirmation_role_eligible=false` remains unchanged.

### Prohibited actions

- During Stage C.0: decompress, enumerate or read any `.mb58.gz`, `.fbt`,
  `.fnv` or `.inf` body.
- During Stage C: run GGM/PINN, read predictions, compute GEBCO/product/model
  residuals, generate confirmation errors, alter v1/v2 data, or promote a
  cruise to confirmation.
- Infer missing fields from filenames, cruise periods, spatial proximity,
  fitted offsets or other cruises.

## Contractual planning outputs

```text
prd.md
design.md
implement.md
research/tool-availability.md
research/fixture-contract.yaml
research/parser-command-contract.yaml
research/output-schema.yaml
research/source-internal-qc.yaml
research/stage-c0-verification-contract.yaml
research/stage-c-authorization.template.json
research/stage-c0-planning-lock.json
research/stage-c0-verification.json
```

## Acceptance criteria

- [x] Stage B input paths, hashes, object/byte counts and ordered cruise IDs
  are frozen exactly.
- [x] Tool availability and the exact candidate parser tag/commit are stated;
  missing executable/environment evidence blocks authorization.
- [x] The fixture contract freezes independent longitude, latitude, UTC,
  positive-down depth, meters, missing-value, ping/beam-key and native-validity
  cases, tolerances and stop rules; actual fixture execution remains a
  pre-authorization gate.
- [x] Allowed object roles, commands, fields and evidence/status rules are
  explicit before any sealed body read.
- [x] Source-internal QC rules and thresholds are machine-readable and contain
  no reference product or model dependency.
- [x] Sounding and cell-by-cruise schemas are exact, preserve lineage and
  prohibit cross-cruise pooling.
- [x] Held-out and v2-H/v2-W role ceilings are explicit in every relevant
  output schema.
- [x] The independent verifier and all fail-closed stop conditions are frozen.
- [x] The authorization template is inactive and cannot pass validation until
  a user separately authorizes Stage C and all placeholder hashes are filled.
- [x] Stage C.0 validation confirms zero sealed object body reads, zero depth
  rows, zero cells, zero QC results and zero product/model comparisons.
