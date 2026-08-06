# Stage B.0 execution-hardening receipt

## Authoritative readiness run

```text
/mnt/data2/00-Data/ship/ncei/derived/scs_v2_sealed_confirmation/readiness/20260805T224911Z
```

- Stage: `B.0_offline_execution_readiness`
- Verification: `pass`
- Audit manifest SHA256:
  `948b9653dbf852be08a77d529704c2c594dc9ef46e855ae44163a7a64fd298fb`
- Verification SHA256:
  `a80be4257ceafe71c5e224f4c09ab1fb8a2ec0ae3232e77cae644602721cff6c`
- Downloader SHA256:
  `d18b163cd8054f39342ce804f497d4836c08fd6966026f5ae1c33f4af8de1a42`
- Independent Stage B verifier SHA256:
  `de1c1367d6eb5b4513f57a5bc1d7159da0a4c1033ae67ed9abab5ba4aa3b4654`

## Frozen execution contract

The Stage A.2 primary set remains exactly ordered as:

```text
EQT20210702
EQT190012
EQT180002
TN352
```

It contains 768 objects, all 768 with frozen Last-Modified values, totaling
`9,626,893,507 bytes` under the `12,884,901,888-byte` cap. No candidate was
added, removed, replaced or reordered.

The downloader now checks the final resolved HTTPS host/path/query and exact
Last-Modified before its first response-body read. Authorization is checked
before the first network request and binds the safe acquisition run ID, fixed
output root, downloader/verifier hashes and all accepted A.2 hashes.

The independent verifier is implemented to reopen and SHA256 every future
object and to close URLs, relative paths, cruises, bytes, Last-Modified,
filesystem inventory, `content_parsed=false`, `role=sealed_unprocessed` and
parser-import guards. Download exceptions retain bytes and produce
`status=failed_unsealed`; they cannot publish a sealed manifest.

## Machine-readable outputs

All JSON schemas are recorded in `audit_manifest.json -> outputs`.

| artifact | rows | bytes | SHA256 |
|---|---:|---:|---|
| authorization_receipt.template.json | 1 | 1,052 | `39554bf6b969bde78210b244672aa45cf44cd37ef622f852281c031140266ee4` |
| stage_b_dry_run_receipt.json | 1 | 1,171 | `c44c89500eda8cef3c2caee9c633d02b2756b3fc059094eafef58824a61294f7` |
| test_results.json | 1 | 551 | `f6d09c37db059cc1bfad87bf21183baa464e48d236e3d1e07f0abe5071f44ba4` |
| readiness_lock.json | 1 | 1,254 | `5d727c825b29839a497652f6c815afe19a6ce00e817775643f0beac619ae4f2f` |
| audit_manifest.json | 1 | 11,259 | `948b9653dbf852be08a77d529704c2c594dc9ef46e855ae44163a7a64fd298fb` |
| verification.json | 1 | 1,178 | `a80be4257ceafe71c5e224f4c09ab1fb8a2ec0ae3232e77cae644602721cff6c` |

## Tests and stop state

The frozen offline test command ran 13 tests and passed. It covers missing or
changed Last-Modified, cross-host/path resolved URL, every authorization hash
and run-ID mismatch, path escape, a zero-byte object, post-download tampering,
parser guards and failed-unsealed receipt retention.

The dry-run and readiness lock close as:

```text
network_request_count=0
physical_object_get_count=0
range_get_count=0
response_body_read_count=0
download_count=0
stage_b_authorized=false
confirmation_role_eligible=false
stage_c_authorized=false
```

The authorization template is intentionally inactive and cannot start Stage B.
Actual acquisition and every Stage C operation remain on HOLD pending separate
user authorization.

## Non-authoritative readiness attempts

- `20260805T223955Z`: verifier rejected temporary rather than published output
  paths in the manifest; no `verification.json` exists.
- `20260805T224054Z`: verifier rejected JSON schema ordering drift; no
  `verification.json` exists.
- `20260805T224124Z`: passed the earlier 12-test contract and is superseded by
  the authoritative run, which additionally freezes test-source hashes and
  verifies failed-unsealed receipt behavior.
- `20260805T224238Z`: passed the 13-test contract and is superseded because its
  authorization run-ID placeholder was syntactically valid rather than
  deliberately unusable.
- `20260805T224617Z`: passed but is superseded by the authoritative run, whose
  independent Stage B verifier additionally closes the A.2 plan hash,
  authorization/audit fields, source paths and all write-permission bits.

None of these attempts performed a network request or download.
