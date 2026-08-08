# Design: SCS v2 Stage C.2.2 contract closure

## Navigation state

The raw parquet gains two fields:

- `u3_navigation_finite: bool`
- `u0_navigation_finite: bool?`

`u0_navigation_finite = null` means no matching U0 key. That case remains a
native-quality failure and does not independently assert H03. A present U0 key
always keeps native quality `good`; its finite state is recorded separately.

The sounding schema gains `navigation_valid: bool`. It is true only when U3
coordinates are finite and in range and a present U0 key does not have
non-finite coordinates. U3 coordinates remain the lineage coordinates. This
preserves available coordinates and depth while giving the verifier direct
evidence for a U0 navigation failure.

Both `sounding_row` and `sounding_batch_table` compute H03, hard pass, cell
eligibility, and cell assignment from `navigation_valid`. The batch expression
fills a null U0 finite-state with true before combining it with U3 navigation;
the row expression uses the same rule. Tests compare every output field.

## Frozen readiness binding

The helper owns one C.2.2 run ID and derives two paths:

- readiness root: the new run directory;
- production template: `stage_c_authorization.template.json` inside that run.

The existing Trellis template remains the readiness producer's source. The
producer copies it into the new run. The readiness verifier proves identical
bytes at creation time. Future production code consumes only the snapshot.

A shared readiness validator loads `audit_manifest.json`, `readiness_lock.json`,
and `verification.json` and checks:

- the configured run ID equals the directory, manifest, lock, and verification
  run IDs;
- verification status is `pass`, while `stage_c_authorized` and
  `confirmation_role_eligible` are false;
- the manifest hash equals the hash recorded by verification;
- the readiness summary equals the manifest summary;
- template, helper, processor, authorizer, production verifier, output schema,
  QC, and verification-rule hashes match both the frozen manifest/summary and
  the supplied files.

The authorizer calls this validator before creating a receipt. The processor
and production verifier call it again, then require every receipt binding to
equal the frozen value. This gives one source of truth for the three production
entry points.

## Receipt validation

Exact active-receipt fields and recursive placeholder checking move to the
shared helper. The authorizer validates its finished receipt before writing;
the processor and verifier validate the same schema and canonical self-excluded
hash. Tests call the real authorizer function with a temporary readiness tree;
the command-line entry point remains fixed to the production readiness root and
does not accept an override.

## Readiness evidence

The existing readiness producer is updated rather than copied. Its manifest
records all source and rule hashes. The readiness lock exposes production-chain
and contract hashes used at authorization time. The verifier independently
recomputes them and writes `verification.json` once.

The new readiness run ID is `20260809T030000Z`. Code and tests are committed
before that run is created, so its `planning_commit` and recorded file hashes
refer to the same repository state. A separate C.2.2 registry records the status
and SHA256 values of 020000Z and 020001Z without changing either directory.

## Boundaries

All fixtures are synthetic ASCII/parquet data in temporary directories or
metadata-only readiness files. No test or readiness step opens the sealed object
root. The Stage C processing directory is listed before and after work and must
have the same child directory names.
