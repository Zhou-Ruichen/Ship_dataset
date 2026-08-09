# SCS v2 development-only Stage C rerun

## Goal

Run one immutable, source-internal Stage C processing pass with the C.2.2
production snapshot frozen by readiness `20260809T030000Z`. The output is for
downstream development only and is not confirmation or publication evidence.

## Requirements

- Use processing run ID `20260808T231659Z` and never modify an existing Stage C
  or readiness run.
- Execute the exact C.2.2 code snapshot at commit
  `3131f729fb5f9c5ca26943128af38c0b2151186f`, whose production code and
  contract SHA256 values are frozen by readiness `20260809T030000Z`.
- Read only the 192 authorized `.mb58.gz` bodies listed by acquisition run
  `20260805T230449Z`. Do not read `.fnv`, `.inf`, or `.fbt` bodies.
- Keep all four cruises held out and classify every handoff artifact as
  `development_only_not_confirmation`.
- Do not access or compare GEBCO, any product, GGM, PINN, or another model. Do
  not merge MRAR, aggregate across cruises, or fit a datum or bias.
- Record the C.2.2 receipt-field validation gap and lack of verifier-independent
  U3/U0 navigation-state reconstruction as known engineering limitations.
- Do not upgrade this run to confirmation or publication evidence.

## Acceptance Criteria

- [x] Readiness verification passes and the four C.2.2 production files match
      the frozen SHA256 values before authorization.
- [x] The recorded 66-test C.2.2 suite passes in the isolated execution tree.
- [x] The input manifest contains exactly 192 authorized `.mb58.gz` objects and
      576 unopened sidecars.
- [x] The producer creates one new run without changing any prior run.
- [x] The independent source-internal verifier reports `status = pass` and all
      prohibited-operation and sidecar-body-read counters are zero.
- [x] Report sounding, eligible, contributor, and candidate counts; per-cruise
      and South China Sea rectangle counts; object 0168 status and recovered
      rows; and cell additions, removals, and depth changes versus
      `20260807T090000Z`.
- [x] Report output schemas and SHA256 values for the manifest, verification,
      and every Parquet file.
- [x] Produce a machine-readable downstream handoff receipt that binds the run,
      output role, limitations, counts, and artifact hashes.
- [x] Explicitly confirm that no GGM, PINN, product residual, GEBCO, or MRAR
      comparison was run.

## Notes

The user explicitly authorized this development-only run and waived C.2.3 as a
precondition. This does not waive the C.2.2 readiness hash checks or any
source-internal processing restriction.
