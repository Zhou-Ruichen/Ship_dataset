# Stage A execution receipt

## Authoritative run

```text
/mnt/data2/00-Data/ship/ncei/derived/scs_v2_sealed_confirmation/
discovery/20260805T204334Z
```

- `audit_manifest.json` SHA256:
  `716a737e6c9b906033738dc5381055b77a2a73d52cbd9e5fc59a99c83f893d6f`
- `verification.json` SHA256:
  `7ac72ae84ce6de386263ece9a3daa1287de1fdd3ea52622e77cbff6f430141b5`
- Verification status: `pass`.
- Official NCEI spatial records: 80.
- Selected for separate Stage B review: 5.
- Confirmation-role eligible at Stage A: 0.
- Existing-repository filename hits: 21 candidates.
- Candidate archive requests/downloads/enumerations: 0/0/0.
- Candidate depth reads, cell generation and reference/model comparisons: 0/0/0.

Selected metadata-only candidates, ordered by deterministic in-domain official
track length:

| rank | official_cruise_id | date | instrument | SCS track km | current19 | exposed12 | repository read | possible MRAR | role eligible |
|---:|---|---|---|---:|---|---|---|---|---|
| 1 | RR1401 | 2014-01-24/2014-02-20 | Kongsberg EM122 | 6690.050 | false | false | false | unknown | false |
| 2 | MGLN31MV | 2008-01-09/2008-02-01 | Simrad EM120 | 6240.987 | false | false | false | unknown | false |
| 3 | MGLN30MV | 2007-11-30/2008-01-04 | Simrad EM120 | 6076.486 | false | false | false | unknown | false |
| 4 | MV0903 | 2009-02-27/2009-03-21 | Simrad EM120 | 5661.382 | false | false | false | unknown | false |
| 5 | MGL0908 | 2009-06-16/2009-07-25 | Simrad EM122 | 5104.919 | false | false | false | unknown | false |

All five have official raw multibeam distribution formats, official navigation
geometry and beam presence. Per-record time, line, ping, quality flag and
vertical datum are not established by the inspected metadata. Cruise date is
metadata-level time only. Vertical datum remains `officially_unknown`.

MRAR terminal state remains:

```text
identity_status=not_recoverable
source_independence=unknown
```

No selected cruise may be promoted to confirmation role on this Stage A
receipt. Stage B remains unauthorized.

## Non-authoritative intermediate runs

These immutable directories are retained as debugging evidence and must not be
used downstream:

| run | reason not authoritative |
|---|---|
| `20260805T201111Z` | Git-only exposure search missed ignored raw/QC filenames. |
| `20260805T202244Z` | Names-only inventory fixed exposure, but exact official polyline geometry was not yet independently recomputed. |
| `20260805T202943Z` | Registry/query paths still pointed to the atomic-publication temporary directory; independent verification failed before receipt creation. |
| `20260805T203445Z` | Passed exact-geometry/path verification but ranked equal candidates by ID, allowing edge-only transit records to outrank greater SCS deployment. |

The authoritative run fixes all four issues and independently recomputes exact
polyline intersection, dateline handling, in-domain track length, filename
exposure, deterministic rank, schemas and hashes.
