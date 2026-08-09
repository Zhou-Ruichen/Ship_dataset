# Planning evidence (2026-08-10)

## Inspection boundary

- Repository: `/mnt/data2/00-Data/ship`
- Branch/base HEAD at task creation: `main`, `4daa6c3`
- Sealed object body reads: 0
- New `.fnv` / `.inf` / `.fbt` body reads: 0 / 0 / 0
- Depth-difference reads: 0
- GGM / PINN / GEBCO / product/model comparisons: 0 / 0 / 0 / 0

Planning inspected code, JSON/JSONL records, Parquet schemas and metadata, the
archived handoff, and task/spec files. It did not execute Phase A or Phase B.

## Accepted Stage C run

```text
ncei/derived/scs_v2_sealed_confirmation/stage_c/20260808T231659Z
```

The retained `verification.json` reports `status=pass`,
`confirmation_role_eligible=false`, 192 `.mb58.gz` body reads, zero sidecar
body reads, and zero external product/model, cross-cruise, MRAR merge, or
datum/bias operations.

Verified counts from the accepted handoff/verification:

| Scope | Soundings | Eligible | Candidate cells |
|---|---:|---:|---:|
| Four cruises | 59,298,192 | 51,303,876 | 3,549 |
| TN352 global | 19,574,784 | 17,211,316 | 3,538 |
| TN352 SCS `[105,125) x [0,25)` | 13,782,014 | 12,351,039 | 2,368 |

Object 0168 is recorded as changing from `failed_parser_contract` with zero
parsed rows to `pass`, recovering 96,768 soundings and 86,184 eligible rows.
The accepted handoff records 198 navigation-invalid/H03 rows, 10 added cells,
and 20 changed common-cell medians with absolute changes from
0.03519999999980428 to 305.97135000000026 m.

Accepted output hashes needed by this task:

| File | SHA256 |
|---|---|
| `sounding_lineage.parquet` | `06f5c22d24260af1b690b7d389eff2d94ed8b27847553e366bd5c3567d54708f` |
| `cell_cruise_contributors.parquet` | `e1e44fab67f1d187859ad38eda9ee36ec941c793eb2d523eb3a11740c367e644` |
| `cell_cruise_candidates.parquet` | `cc23c17170ad51e1adfa35fad2176e448a0368643240652f81d625140816e214` |
| `field_recovery_ledger.parquet` | `ea9b0e078ae0e17e00e33e838ab618c998f331d1ab851315cebb2400066484b6` |
| `source_object_processing.parquet` | `c3e4a44cfd4d5c0840765229f246723512e3fd00f16e58c98a16e698a51be8de` |

## Preliminary processing evidence

The accepted environment records:

- MB-System tag/version: `5.8.3beta16`
- source commit: `1d9a52ce076c3c3c5f0150b9bcaa30fa108c7422`
- source tree: `b5113ce8a246f833e74b3c6a377c5d7ec08ea108`
- environment digest:
  `b2c47303df33602a297754e48057f68ce8a8801fbd95a987866bf9d25172b0bb`
- `mblist` SHA256:
  `ca058a5de4f1c949d68f08af7965a66a2450793fd4708b6615cea660a024f03e`
- `mbinfo` SHA256:
  `37321b8ae0101c175b1fdba64b512550f0778b8b36b402aa6a744a7535eaa1a9`

The command ledger contains 192 invocations of each retained role:

```text
gzip -dc -- <sealed .mb58.gz>
mbinfo -I<decompressed input.mb58> -F58 -X1
mblist -I<decompressed input.mb58> -F58 -P1 -L0 -MA -U3 -OMN#XYzH -X<all_u3.tsv>
mblist -I<decompressed input.mb58> -F58 -P1 -L0 -MA -U0 -OMN#XYzH -X<good_u0.tsv>
```

No other command role appears in accepted verification. The ledger evidence
alone does not settle every internal correction performed by the format reader;
Phase A must inspect code, MB-System field semantics, and retained provenance
before assigning `verified_not_used`, `unknown`, or `not_performed`.

The accepted sounding schema records metre, positive-down depth;
good/flagged/null native state; navigation validity; H02/H03/H04 failure codes;
and `qc_eligible_for_cell`. It does not expose amplitude, beam angle, speed,
SVP, tide, draft, lever arm, attitude, patch-test parameters, native quality
codes, horizontal datum, or vertical datum as known fields.

## MRAR planning inputs

- checked point lineage:
  `ncei/derived/regional_mrar/points_checked/bathymetry_points.parquet`
  (113,356,582 rows by Parquet metadata);
- experimental cell labels:
  `ncei/derived/validation_cells_1min/regional_mrar_experiment_cells.parquet`
  (9,019,383 rows by Parquet metadata);
- catalog role: `regional_sensitivity_only`, never authoritative truth.

The checked point identity is `(track_id, point_index_in_track)` and its frozen
basic selector is `point_check_pass_basic`. The cell label uses positive-down
`representative_depth_m`.

## Unverified expected value

The expected TN352-MRAR common SCS cohort count of 2,244 is supplied by the
user. No retained repository artifact found during planning states that exact
count. It is therefore an execution gate to be independently recomputed from
cell IDs before Phase B depth access, not a verified planning result.
