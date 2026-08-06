# Stage B opaque sealed acquisition receipt

## Authoritative acquisition run

```text
/mnt/data2/00-Data/ship/ncei/archive/scs_v2_sealed_confirmation/20260805T230449Z
```

- Execution code commit:
  `c3871f54f8041fcb2d3ae18cd124d3b5223c118f`
- Stage A.2 run: `20260805T221441Z`
- Stage B.0 readiness run: `20260805T224911Z`
- Transport selected by the user: local sing-box mixed proxy
  `http://127.0.0.1:2082`, mapped locally to `HK-DC`
- Transport-selection evidence ceiling: the pre-execution comparison measured
  HEAD/TTFB only, not object-body throughput. No candidate body was read for
  route ranking.
- Downloader SHA256:
  `d18b163cd8054f39342ce804f497d4836c08fd6966026f5ae1c33f4af8de1a42`
- Independent verifier SHA256:
  `de1c1367d6eb5b4513f57a5bc1d7159da0a4c1033ae67ed9abab5ba4aa3b4654`

The ordered cruise set remained exactly:

```text
EQT20210702
EQT190012
EQT180002
TN352
```

No object, cruise, URL or destination was added, removed, replaced or
reordered. The completed run contains 768 opaque objects totaling exactly
`9,626,893,507 bytes`, below the frozen 12 GiB cap.

## Machine-readable outputs

| artifact | rows | bytes | SHA256 |
|---|---:|---:|---|
| authorization_receipt.json | 1 | 1,066 | `4e34f63cb25f957c8afe59a81a6dbfa3fd7b626960910cc11f182f9eb7abc9b4` |
| sealed_archive_manifest.parquet | 768 | 120,832 | `9fafb163a6fe2818d96a0c9bb0ed49afc98a8b0850979d5783b1882139702f94` |
| access_lock.json | 1 | 654 | `75c290a9b4f17ed2b529a372417f4fd18770c08cf66836c07ddde3bb90e00a6f` |
| audit_manifest.json | 1 | 3,388 | `7b07a36c451b2bf24369e3c7d9f826dce80e80d929b1c921b410f006648d024e` |
| verification.json | 1 | 1,717 | `d0d868f560c628bd24d1d52d399c7ed9d03af337be72967a874a5c26db7c2e86` |

The authorization receipt retained under the derived authorization directory
and the copy sealed into the acquisition run have the same SHA256.

## Independent verification

The Stage B verifier completed with `status=pass` at
`2026-08-06T00:02:42.527225Z` and closed:

```text
object_count=768
total_bytes=9626893507
last_modified_closed=768
objects_reopened_and_rehashed=768
part_file_count=0
content_parsed=false
role=sealed_unprocessed
confirmation_role_eligible=false
stage_c_authorized=false
access_allowed=false
```

All 768 manifest rows have `content_parsed=false`; all use
`sealed_role=sealed_unprocessed`. The static parser guards found zero forbidden
imports and zero forbidden calls in both the downloader and verifier.

The frozen A.2 plus B.0 offline suite passed `13/13` tests. Both Stage B Python
files passed `py_compile`, the Trellis context validator passed, and the scoped
task diff passed `git diff --check`.

## Failed attempt and retry accounting

The first authorized run, `20260805T225949Z`, was retained at:

```text
/mnt/data2/00-Data/ship/ncei/archive/scs_v2_sealed_confirmation/20260805T225949Z.failed
```

The environment-provided proxy returned HTTP tunnel status 403 before the
first object body was read. Its machine-readable receipt records
`status=failed_unsealed`, one failed object attempt, zero completed objects and
zero completed bytes. It did not publish a sealed manifest.

The successful run used a new authorization receipt and the user-selected
2082/HK-DC route. It performed no internal automatic object retry. Across the
two runs, one frozen object was attempted again, zero candidates were
replaced, and all 768 final objects closed exactly against Stage A.2.

## Stop state

Stage B is complete only at the opaque acquisition layer. The run remains:

```text
status=sealed_unprocessed
content_parsed=false
confirmation_role_eligible=false
stage_c_authorized=false
```

No archive was decompressed or enumerated, no sounding field was read, and no
depth, cell, QC, GEBCO/product/model residual, GGM or PINN output was produced.
Stage C requires a separate decision and authorization.
