# Stage A.2 execution receipt

## Authoritative run

```text
/mnt/data2/00-Data/ship/ncei/derived/scs_v2_sealed_confirmation/discovery/20260805T221441Z
```

- Stage: `A.2_offline_final_download_lock`
- Verification: `pass`
- Downloader test: `dry_run_pass`
- Audit manifest SHA256:
  `3a982515feb5b0172722e0651aef9c3e484c0ffd908cab3d69887c1b6fc236d0`
- Verification SHA256:
  `b30254070c910d11b6f140adba653c9c0bdd3707a7a99aea9529788f404a5918`
- Frozen config SHA256:
  `d110cae58e1f1d6ee2c43e76a949083973079767a025627728e99d8ab1544d42`

## Final primary acquisition lock

The ordered and immutable IDs are:

```text
EQT20210702
EQT190012
EQT180002
TN352
```

| cruise | objects | HEAD-sized objects | listing-sized objects | exact bytes | SCS track km |
|---|---:|---:|---:|---:|---:|
| EQT20210702 | 24 | 24 | 0 | 1,052,963,178 | 3,498.733697 |
| EQT190012 | 4 | 4 | 0 | 231,418,216 | 1,076.389388 |
| EQT180002 | 4 | 4 | 0 | 215,321,752 | 129.133115 |
| TN352 | 736 | 734 | 2 | 8,127,190,361 | 902.117947 |
| all primary | 768 | 766 | 2 | 9,626,893,507 | 5,606.374147 |

- Aggregate cap: `12,884,901,888 bytes` (12 GiB).
- Remaining cap: `3,258,008,381 bytes`.
- The two TN352 `.fnv` listing recoveries are exact zero-byte entries from
  frozen evidence SHA256
  `b1a95400c319305bf92872f155b125022f54fc288d73f31276d857a142b259b2`.
- ETag remains officially unknown where the server omitted it.
- Vertical datum remains officially unknown.

## Excluded and deferred

- `SR1912`: excluded, official SCS track only `0.260290 km`.
- `TN359`: excluded, `80,073,406,797` known bytes for `462.327877 km`.
- `TN358` and `TN354`: deferred together for the current confirmation because
  their known combined cost is `131,715,877,853 bytes`.
- Every row has `replacement_allowed=false` and
  `model_or_product_result_used=false`.

## Required machine-readable artifacts

Full ordered tabular schemas are recorded in
`audit_manifest.json -> outputs -> <name> -> schema`.

| artifact | rows | schema columns | bytes | SHA256 |
|---|---:|---:|---:|---|
| primary_physical_object_lock.parquet | 768 | 32 | 55,160 | `826930f281e66d3f3e5ff637e8aac839e0406493d97e1a80f8c25466b959d3dd` |
| primary_cruise_budget.tsv | 5 | 26 | 1,603 | `d5a3878f205dced588cc9e6b8945fa207fb99b3fd64ce5f8b33e20e043ec509a` |
| candidate_decision_registry.tsv | 8 | 16 | 2,057 | `d59e60b89074b2db9a27b27346ecd746dc996a249fd53aad966c15504c7b1d8b` |
| stage_b_dry_run_plan.tsv | 768 | 16 | 299,290 | `5e041399b82ec6a4e5d3a8d86632e60f8edf6d4813861faeffeb169da8bc820c` |
| final_download_lock.json | 1 | schema_version=1 | 3,928 | `686fa1775cd73053486cdd09a19d24c4352e2eaef95fa2e132778b620377b9ca` |
| audit_manifest.json | 1 | schema_version=1 | 16,683 | `3a982515feb5b0172722e0651aef9c3e484c0ffd908cab3d69887c1b6fc236d0` |
| verification.json | 1 | schema_version=1 | 1,754 | `b30254070c910d11b6f140adba653c9c0bdd3707a7a99aea9529788f404a5918` |

## Dry-run and stop state

The downloader dry-run rehashed the run and returned:

```text
physical_object_count=768
exact_total_bytes=9626893507
network_request_count=0
download_count=0
stage_b_authorized=false
status=dry_run_pass
```

No Stage B acquisition directory was created. The downloader source SHA256
verified by A.2 is
`e7f58c218f6fae03cf8e69ec8c228b7420b8a2fc20b7f3ac7c94fc80e6ec4a4a`.
Future execution requires a separate authorization receipt bound to this A.2
manifest, verification, physical lock, ordered IDs and cap. Even a successful
download can produce only `sealed_unprocessed`; Stage C remains separate.

## Non-authoritative intermediate run

`20260805T221152Z` is retained but must not be used downstream. Its producer
outputs and verifier passed before the final destination-path escape guard was
added to the downloader. The authoritative run re-verifies the final downloader
source and repeats the read-only dry-run.
