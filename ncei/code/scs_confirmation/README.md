# scs_confirmation/ — archived SCS/TN352 sealed-confirmation chain

One-off audit/verification chain used during the SCS TN352 source
confirmation and the `scs_v2_sealed_confirmation` task (2026-05). The chain
is complete and retained for provenance; it is not part of the active
pipeline. It was moved from the flat `ncei/code/` listing on 2026-09-02.

What changed in the move:

- Package imports rewritten: `ncei.code.scs_*` → `ncei.code.scs_confirmation.scs_*`.
- `REPO_ROOT`/`SCRIPT_PATH.parents[2]` computations bumped one level
  (`parents[3]`) to account for the extra directory.
- Hardcoded script paths in `_common/tests/scs_confirmation/` updated.

Reports and journals dated before 2026-09-02 reference the old flat paths;
substitute `ncei/code/` → `ncei/code/scs_confirmation/` when re-running
recorded commands. Corresponding tests: `_common/tests/scs_confirmation/`
(run from repo root: `python -m unittest _common.tests.scs_confirmation.<name>`).
