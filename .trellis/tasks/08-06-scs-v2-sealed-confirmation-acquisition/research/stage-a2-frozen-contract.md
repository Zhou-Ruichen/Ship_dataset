# Stage A.2 frozen contract

Frozen before the offline A.2 producer run on 2026-08-06.

## Accepted Stage A.1 anchors

- Commit: `b6de3a6`
- Run: `20260805T213226Z`
- Physical object lock SHA256:
  `fb3683ce5e2b5751d786e19d99e124ffbc2ef8c75f40a50b6100fd619edbba97`
- Audit manifest SHA256:
  `e936fec44b9cc902d4c3390b674ff88ca114153e62699bbee9fc870650da2d9a`
- Verification SHA256:
  `ff6f77878f0712a75f08265baadae709ff80e0964e4aeb5fd86c63fa96961b20`

## Immutable primary set and cap

```text
EQT20210702
EQT190012
EQT180002
TN352
```

- Aggregate cap: `12,884,901,888 bytes` (12 GiB).
- No replacement is allowed.
- `SR1912` and `TN359` are excluded.
- `TN358` and `TN354` are deferred for the current confirmation.
- No model, product, residual or candidate-depth value enters these decisions.

## TN352 exact size evidence

The frozen official directory HTML at
`TN352_0003_31fca01a0ef6c6d1.html` lists these two files with exact size token
`0`:

```text
0126_20180425_004502_TGT.all.mb58.fnv
0127_20180425_011502_TGT.all.mb58.fnv
```

Only these exact integer listing sizes may replace missing HEAD
Content-Length. No GET, Range GET, new HEAD or body read is authorized.

## Stop rule

Stage A.2 may generate a dry-run plan and verify it. It must stop with
`stage_b_authorized=false`, `confirmation_role_eligible=false`, and maximum
future post-download role `sealed_unprocessed`.
