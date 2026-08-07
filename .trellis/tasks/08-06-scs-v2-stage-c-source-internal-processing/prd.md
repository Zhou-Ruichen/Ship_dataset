# SCS v2 Stage C source-internal processing

## Goal

Authorized source-internal Stage C processing for the sealed four-cruise acquisition, with exact sounding lineage and cell-by-official-cruise outputs; no external comparison or confirmation evaluation.

## Requirements

- Process only the authorized Stage B acquisition `20260805T230449Z` after an
  active, hash-complete Stage C receipt exists.
- Open and rehash only the 192 `.mb58.gz` bodies; keep all 576 sidecars closed,
  including `.fbt`.
- Emit exact sounding-level lineage, source-object processing, field recovery,
  and cell-by-official-cruise contributor/candidate tables under a new derived
  run. Invalid or missing time aborts its source object atomically.
- Apply only the frozen source-internal QC rules. Do not use external products,
  models, MRAR merging, datum/bias fitting, crossover adjustment, or role
  promotion.
- Keep every cruise held out with `confirmation_role_eligible=false`.

## Acceptance Criteria

- [x] Active receipt binds the Stage B and C1a hashes, parser environment, and
  current producer/verifier/helper hashes before any body read.
- [x] Independent verifier passes schemas, object closures, time semantics,
  exact cell-by-cruise summaries, roles, and zero prohibited-operation counters.
- [x] Stage B objects are unchanged; the run is immutable and machine-readable.

Verification: run `20260807T090000Z`, `verification.json status=pass`, all
prohibited-operation counters zero, `independent_verifier_opened_sealed_body=false`.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
# SCS v2 Stage C source-internal processing

## Goal

Process the authorized Stage B sealed acquisition into source-internal
sounding lineage and cell-by-official-cruise candidate labels. The result is
provenance, not confirmation accuracy.

## Authorized input

Only acquisition run `20260805T230449Z` is allowed:

```text
sealed_archive_manifest_sha256 = 9fafb163a6fe2818d96a0c9bb0ed49afc98a8b0850979d5783b1882139702f94
stage_b_verification_sha256    = d0d868f560c628bd24d1d52d399c7ed9d03af337be72967a874a5c26db7c2e86
access_lock_sha256             = 75c290a9b4f17ed2b529a372417f4fd18770c08cf66836c07ddde3bb90e00a6f
primary_cruises                = EQT20210702,EQT190012,EQT180002,TN352
object_count                   = 768
total_bytes                    = 9626893507
```

The active Stage C authorization must also bind C1a readiness run
`20260806T093740Z`, manifest SHA256
`c260960dc4999f08bad710b7d2f6111acd90087a158eb661957f01280bc89615`, and
verification SHA256
`9f3464bfa3f1a90d319761b543bb5488d0d5c154bfc6837b23a278d53558c717`.

## Processing rules

- Read exact manifest paths only; never glob the sealed root.
- Read `.mb58.gz` as the sole sounding source, `.fnv` only for source-internal
  time/navigation cross-checks, and `.inf` only for format/count/metadata and
  direct datum evidence. Do not read `.fbt`.
- Use the pinned MB-System environment and exact `-MA`, `-U3`, `-U0`,
  `-OMN#XYzH` command contract. Decompress only into the new derived run.
- For any U3/U0 missing, nonnumeric, nonfinite or negative `M`, atomically
  abort that source object: retain a failed processing row and one
  `time_utc` field ledger row, emit no sounding/contributor/cell rows, and do
  not assign `parser_ping_index`.
- Keep `time_utc` non-nullable in emitted sounding rows. Never infer time,
  line, ping, beam, datum or quality from filenames or cruise dates.
- Preserve every emitted beam lineage row, including flagged/null rows. Only
  native-good, structurally valid, finite positive-down depths enter cell
  aggregation. No global 3STD, deletion, crossover adjustment or fitted bias.
- Aggregate exactly by `(cell_id, official_cruise_id)` from individual beams;
  never pool cruises or aggregate chunk medians.
- All four cruises remain held out; `v2-H=held_out_candidate_mrar_out`,
  `v2-W=blocked_source_independence_unknown`, and
  `confirmation_role_eligible=false`.

## Prohibited actions

Do not read GEBCO or any other product, GGM/PINN output, model error or
residual; do not merge MRAR; do not fit datum/bias; do not train, tune, select
thresholds, or promote a confirmation role.

## Acceptance criteria

- Authorization receipt is active and hash-complete before the first sealed
  body read.
- All 192 permitted `.mb58.gz` objects are rehashed before and after
  processing; the 576 sidecars remain bound to their Stage B manifest hashes
  without body reads, and `.fbt` remains forbidden. Stage B files remain
  unchanged.
- Output Parquets match the C1a schema and independent verifier, including
  atomic invalid-time behavior, five-level factual statuses, exact grid IDs,
  exact cell-by-cruise summaries, and held-out role flags.
- Immutable `verification.json` is `pass`; failed processing is never labeled
  candidate-ready.
