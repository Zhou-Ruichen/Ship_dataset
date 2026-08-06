# Stage A.1 frozen contract

Frozen before official File List access on 2026-08-06.

## Accepted Stage A anchors

- Commit: `948519b`
- Candidate registry SHA256:
  `c73e3719b05c1d3cc4ad286f803cc6aa9b0ebb7e8f5e931dc88c3c09095f948f`
- Audit manifest SHA256:
  `716a737e6c9b906033738dc5381055b77a2a73d52cbd9e5fc59a99c83f893d6f`
- Verification SHA256:
  `7ac72ae84ce6de386263ece9a3daa1287de1fdd3ea52622e77cbff6f430141b5`

## Comparison and ranking

The accepted registry contains eight official records that begin in 2018 or
later, intersect the frozen SCS rectangle by official polyline, have no overlap
with the current 19 or exposed 12, have `ever_read_by_repo=false`, and expose
an official NCEI Cruise File List directory:

```text
EQT20210702
EQT190012
SR1912
EQT180002
TN359
TN358
TN354
TN352
```

All eight enter the Stage A.1 selected metadata/preseal set. There is no top-5
cap. Ranking is MRAR delivery chronology class, observation end date
descending, SCS official track length descending, then cruise ID ascending.

## Network and claim ceiling

- Allowed: official directory HTML GET; descendant physical-object HEAD.
- Forbidden: physical-object GET, Range GET, body read, sounding parsing, cell
  generation, product/model comparison, external message, Stage B.
- MRAR remains `identity_status=not_recoverable` and
  `source_independence=unknown`.
- A complete physical transport lock does not establish confirmation
  independence and does not authorize Stage B.
