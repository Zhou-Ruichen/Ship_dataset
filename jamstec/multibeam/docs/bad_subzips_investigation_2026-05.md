# bad_subzips investigation — 2026-05-11 (closed)

> **Status**: investigated and **deliberately skipped**. The 13 zips in
> `bad_subzips.txt` are not recoverable from the JAMSTEC sibling
> archive (same files, byte-identical); the data they would
> contribute is too small to justify the recovery work.

This file is a discoverability breadcrumb sitting next to the
auto-generated `bad_subzips.txt`. The txt file is rewritten by
`code/02_check_subzips.sh` on every Step 02 run, so any header note
inside it would be wiped — this sidecar persists across re-runs.

## TL;DR

- 13 cruise zips at `raw/subzips_bad/` failed `7z t` integrity check
  during Step 02 in 2026-04. They are listed in `bad_subzips.txt`.
- 2026-05-11 audit: each zip has exactly 1 corrupt inner entry; 12 of
  13 cruises could be recovered via per-entry extraction skipping the
  bad entry. The 13th (`MR07-06_leg2_bathymetry_pi`) has only one data
  entry inside and it is the corrupt one — unrecoverable.
- The "JAMSTEC sibling archive holds clean copies" hypothesis from the
  original recovery task description is **false**: MD5 SAME for all
  13 vs `jamstec/archive/bathymetry_data/<same name>.zip`. JAMSTEC is the
  source archive of `jamstec/multibeam/`, not a clean alternative.
- Decision: **skip recovery**. Recoverable share (~1.5% of cruises,
  ~3% of data on top of 88 GB / 763 cruises / 5,140 .dat files) is
  below the noise floor for the downstream products this dataset
  feeds.

## Full investigation + recovery design

See the archived task PRD:
`.trellis/tasks/archive/2026-05/05-11-recover-bad-subzips/prd.md`

That PRD preserves:
- Per-cruise breakdown (which inner entry is corrupt in each of the 13).
- A complete recovery design sketch (`01b_recover_bad_subzips.py`
  using `zipfile` per-entry + `03_recursive_extract.process_directory`)
  ready to revive if needed.
- The quantitative impact table (1.5% / 3% / etc.) that drove the
  skip decision.

## Related provenance note

The JAMSTEC ≡ NCEI source identity was confirmed during this audit and
folded into the broader provenance writeup at
`docs/experiments/2026-05_dataset-source-attribution.md`
(see the "Update 2026-05-11" section).

## When to revisit

The recovery design is shelved, not invalidated. Triggers that would
justify reopening:

- A downstream product becomes sensitive enough that ~3% more data
  materially shifts a result.
- A future audit demands "complete coverage" attestation.
- A scientific question targets a region/era preferentially covered
  by these 12 cruises (would require checking the cruise IDs against
  the target's spatial/temporal scope).
