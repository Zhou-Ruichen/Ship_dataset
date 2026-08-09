# Design: isolated C.2.2 Stage C execution

## Execution snapshot

Create a temporary local clone at C.2.2 commit `3131f72`. Use a private mount
namespace to expose the clone's C.2.2 code and contracts at their frozen
absolute paths while binding the real repository data and output roots. This
lets the C.2.2 programs resolve the acquisition, readiness, parser environment,
and output root while keeping the current C.2.3 working tree and user changes
untouched.

Before authorization, compare the snapshot code and contract SHA256 values to
readiness `20260809T030000Z`, run its verifier and its exact 66-test suite, and
record the existing Stage C directory names and old-run artifact hashes.

## Authorization and processing

Generate a C.2.2 active authorization receipt for processing run
`20260808T231659Z` with the real authorizer. The receipt permits only 192
`.mb58.gz` body reads and leaves every external comparison, MRAR merge,
cross-cruise aggregation, datum/bias fit, and role promotion false.

Run the C.2.2 producer once. A pre-existing output directory is a hard stop.
The producer reads manifest paths rather than globbing inputs, writes to a new
run directory, and leaves all old run directories unchanged.

## Verification and handoff

Run the C.2.2 production verifier before any downstream analysis. Compute only
source-internal summaries from the new and reference Parquets. The South China
Sea rectangle is the frozen project rectangle used by the Stage A/C records;
its exact bounds must be recovered from repository artifacts and written into
the handoff receipt.

Write the handoff receipt outside the immutable producer run, under this
task's `research/` directory. It binds the run path, `development_only_not_confirmation`
role, known limitations, counts, schemas, and hashes without changing the
verified run.

## Known engineering limitations

The C.2.2 shared gate does not independently validate every receipt field, and
the C.2.2 output/verifier does not persist and independently reconstruct U3 and
U0 navigation source states. These limitations are accepted for this one
development-only run and prevent confirmation or publication use.
