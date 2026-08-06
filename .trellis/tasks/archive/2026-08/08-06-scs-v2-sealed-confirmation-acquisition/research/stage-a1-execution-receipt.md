# Stage A.1 execution receipt

## Authoritative run

```text
/mnt/data2/00-Data/ship/ncei/derived/scs_v2_sealed_confirmation/discovery/20260805T213226Z
```

- Stage: `A.1_metadata_file_list_and_head_only`
- Verification: `pass`
- Audit manifest SHA256:
  `e936fec44b9cc902d4c3390b674ff88ca114153e62699bbee9fc870650da2d9a`
- Verification SHA256:
  `ff6f77878f0712a75f08265baadae709ff80e0964e4aeb5fd86c63fa96961b20`
- Frozen config SHA256:
  `5888eea2c95200be943eacd6ff9d5f6d994c626b84e32a604e3ac08193950c96`
- Accepted Stage A candidate registry SHA256:
  `c73e3719b05c1d3cc4ad286f803cc6aa9b0ebb7e8f5e931dc88c3c09095f948f`

## Network and physical lock result

- Official Cruise File List metadata GET: 26; all retained as HTML evidence.
- Physical-object HEAD: 11,860.
- HEAD HTTP 200: 11,859.
- HEAD network error: 1, a TLS handshake timeout for one TN358 `.fbt` URL.
- Content-Length known: 11,825.
- Successful HEAD without Content-Length: 34.
- ETag known: 0; this optional header remains officially unknown.
- Last-Modified known: 11,859.
- Physical-object GET: 0.
- Range GET: 0.
- Physical-object body reads: 0.
- Candidate depth reads/cells/reference or model comparisons: 0/0/0.
- External messages sent: 0.

The all-candidate known-byte sum is `222,573,711,508` bytes. It is not a
complete download-size total because 35 physical objects lack usable
Content-Length evidence (34 HTTP-success cases and the one failed HEAD).

| rank | cruise | objects | HEAD ok | length known | known bytes | physical lock |
|---:|---|---:|---:|---:|---:|---|
| 1 | EQT20210702 | 24 | 24 | 24 | 1,052,963,178 | closed_metadata_head_lock |
| 2 | EQT190012 | 4 | 4 | 4 | 231,418,216 | closed_metadata_head_lock |
| 3 | SR1912 | 260 | 260 | 260 | 1,157,533,351 | closed_metadata_head_lock |
| 4 | EQT180002 | 4 | 4 | 4 | 215,321,752 | closed_metadata_head_lock |
| 5 | TN359 | 5,276 | 5,276 | 5,271 | 80,073,406,797 | blocked_content_length_unknown |
| 6 | TN358 | 2,528 | 2,527 | 2,525 | 68,265,112,046 | blocked_head_unavailable |
| 7 | TN354 | 3,028 | 3,028 | 3,003 | 63,450,765,807 | blocked_content_length_unknown |
| 8 | TN352 | 736 | 736 | 734 | 8,127,190,361 | blocked_content_length_unknown |

## Branch and role ceiling

For all eight comparison candidates:

```text
confirmation_candidate_v2_H_MRAR_out=pending_seal_and_processing
confirmation_candidate_v2_W_MRAR_in=blocked_source_independence_unknown
confirmation_role_eligible=false
```

MRAR remains `identity_status=not_recoverable` and
`source_independence=unknown`. Chronology does not exclude MRAR membership for
any of the eight 2018-2021 observations. No Stage B role is authorized.

## Required machine-readable artifacts

The full ordered tabular schemas, including every paired five-level evidence
status, are stored in `audit_manifest.json -> outputs -> <name> -> schema`.

| artifact | rows | schema columns | bytes | SHA256 |
|---|---:|---:|---:|---|
| physical_object_lock.parquet | 11,860 | 34 | 569,539 | `fb3683ce5e2b5751d786e19d99e124ffbc2ef8c75f40a50b6100fd619edbba97` |
| per_cruise_byte_budget.tsv | 9 | 30 | 3,752 | `e149334323044f67075f7af34d6652c8e1d756a8cb96433be8b75cdc2990f0e6` |
| revised_candidate_registry.parquet | 80 | 76 | 74,147 | `8ada967f09e3edfd76909046367be784098b5a3ba6989bcd19aa26cb70c5cad9` |
| revised_preseal_lock.json | 1 | schema_version=1 | 6,793 | `01ff7b1a07f3f72cd94b8c43201d265441d594c0df522bb3bfe40a3299bb02da` |
| audit_manifest.json | 1 | schema_version=1 | 33,724 | `e936fec44b9cc902d4c3390b674ff88ca114153e62699bbee9fc870650da2d9a` |
| verification.json | 1 | schema_version=1 | 1,706 | `ff6f77878f0712a75f08265baadae709ff80e0964e4aeb5fd86c63fa96961b20` |

Supporting machine-readable evidence:

| artifact | rows | schema columns | SHA256 |
|---|---:|---:|---|
| metadata_evidence_registry.tsv | 26 | 10 | `67f1aa30db53fea6574db09603aa20d9540b909017cfb453dad9a3665353cc71` |
| query_command_ledger.jsonl | 11,886 | JSONL | `6ac3e2fe45b093f3bd28aa8a65f9282bf17a85b9b13fac247f95dea6f116f0ea` |
| negative_result_ledger.tsv | 35 | 4 | `8b1e7dd8ec51d5f041d3added389a11e6d1ae1d08efd008d53ca6f715418b5ac` |

## Non-authoritative intermediate run

`20260805T211425Z` is retained and must not be used downstream. It passed its
then-current independent verifier but did not copy the 34 missing
Content-Length cases into the negative-result ledger. The authoritative run
fixes that evidence-closure gap and labels `.mb58.gz` objects as
filename-inferred `multibeam_data_compressed` rather than unknown role.
