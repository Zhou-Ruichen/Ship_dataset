# Design: SCS v2 Stage C.2.3 receipt and navigation evidence

## Authorization template classification

The immutable readiness template has 33 fields. The validator requires the
three sets below to be disjoint and their union to equal the template key set.

### Template-fixed: exact value equality with readiness snapshot (17)

`access_lock_sha256`, `acquisition_run_id`, `command_contract_sha256`,
`confirmation_role_eligible`, `fixed_output_root`, `fixture_contract_sha256`,
`immutable_primary_cruise_ids`, `model_or_product_evaluation_authorized`,
`object_count`, `parser_name`, `parser_source_commit`, `parser_version`,
`permitted_object_reads`, `sealed_archive_manifest_sha256`,
`stage_b_verification_sha256`, `stage_d_confirmation_evaluation_authorized`,
and `total_bytes`.

### Readiness-evidence-filled: exact frozen evidence equality (11)

`fixture_verification_sha256`, `format58_fixture_bytes_sha256`,
`format58_fixture_oracle_sha256`, `output_schema_sha256`,
`parser_environment_digest`, `parser_help_snapshot_sha256`,
`qc_contract_sha256`, `stage_c0_planning_commit`,
`stage_c0_planning_lock_sha256`, `verification_contract_sha256`, and
`verifier_sha256`.

The planning lock values are fixed constants in the production helper and are
also checked against the live planning-lock file before authorization.

### Activation-controlled: allowed to change under explicit constraints (5)

`authorized_by` must be non-empty; `authorized_utc` must be a valid UTC
timestamp; `processing_run_id` must be a safe single path segment;
`schema_version` must equal the active receipt schema version; and
`stage_c_authorized` must be true.

## Receipt-only fields

Every field added by the authorizer is either compared with readiness-frozen
code/contract/artifact evidence, compared with an exact source-internal policy
value, or recomputed as the canonical receipt hash. The validator compares its
validated field set with the exact expected receipt key set so a future added
field cannot remain unchecked.

The authorizer, processor, and production verifier all call the same validator.
The processor and verifier retain their run-directory checks in addition to the
shared receipt checks.

## Navigation lineage schema

Schema v3 has one final field:

```text
navigation_valid: bool, nullable=false
```

Schema v4 adds the source evidence immediately before it:

```text
u3_navigation_finite: bool, nullable=false
u0_navigation_finite: bool, nullable=true
navigation_valid: bool, nullable=false
```

Both producer paths copy the existing raw parser state into these columns. The
production verifier computes:

```text
expected_navigation_valid =
    u3_navigation_finite
    and (u0_navigation_finite is null or u0_navigation_finite)
    and finite_and_in_range(lon_deg, lat_deg)
```

It compares the result with `navigation_valid`, H03, hard-pass, cell assignment,
contributor rows, and candidate rows. It does not infer a source state from the
producer's final flag.

## Readiness

After the implementation commit, producer and verifier will use the new
`20260809T040000Z` root. Its manifest binds the helper, processor, authorizer,
production verifier, readiness producer/verifier, relevant tests, C.2.1/C.2.2/
C.2.3 contracts, output/QC/verification rules, and immutable template snapshot.
The existing `20260809T030000Z` directory remains byte-for-byte unchanged.
