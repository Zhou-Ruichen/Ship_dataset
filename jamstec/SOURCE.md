# SOURCE — `jamstec/`

> JAMSTEC multibeam bathymetry corpus (R/V Kaiyo / Kairei / Mirai,
> 2000–2015), plus sibling JAMSTEC gravity sub-corpus. Active processing
> pipeline lives under `multibeam/`; the rest of the tree is frozen
> source-archive material.

## Provenance — content origin

**JAMSTEC** (Japan Agency for Marine-Earth Science and Technology).
Rock-solid attribution: every cruise ID extracted from the 5,083 active
multibeam files matches a JAMSTEC research vessel prefix
(`KY`, `KR`, `MR`, `KS`, `KH`) and the first source-zip enumerates 255
unique JAMSTEC cruise IDs. Full evidence chain in
[`docs/experiments/2026-05_dataset-source-attribution.md`](../docs/experiments/2026-05_dataset-source-attribution.md).

Historical naming note: this tree lived at `ship/NCEI_multibeam/` until
2026-05-16, when task `05-11-singlebeam-integration` (PR-A) executed the
rename to `ship/jamstec/` after the JAMSTEC attribution was confirmed.
The earlier `NCEI_multibeam/` name was a mislabel inherited from the
original Chinese-language archive packaging (`国外水深*.zip`) and never
reflected actual provenance.

## Provenance — transfer chain (new 2026-05-16 finding)

The two source zips at `multibeam/archive/国外水深第{一,二}部分.zip`
arrived from **郭恒洋 → user** in approximately **December 2024**
(file mtimes Dec 16 / Dec 17 2024; verified `readlink -f` shows both
are physical files, not symlinks). Source: user recollection
2026-05-16. **High-confidence inference, not externally verified**;
provenance is not actively chased (Q8-style stance — see PRD).

The other two packagings of the same JAMSTEC corpus
(`archive/source_zips/bathymetry.7z` and the 776 per-cruise zips under
`archive/bathymetry_data/`) arrived through separate, **unconfirmed**
transfer channels. Their packaging internal timestamps (`2024-07-24`
inside the `国外水深` zips) and `bathymetry.7z`'s mtime (`Jul 25 2024`)
align too tightly to be coincidence: they are **the same upstream
packaging event re-distributed in two compression formats**. Who
re-compressed which copy is the part that is not known.

## Layout map

| Path | Size | Role | Source |
|---|---:|---|---|
| `multibeam/` | ~326 GB | Active processed pipeline (Step 00–11 complete; `code/`, `derived/`, `manifests/`, `docs/`, `figures/`, `output/`, `raw/`, `archive/`). | Built from `multibeam/archive/国外水深*.zip` extraction. |
| `multibeam/archive/国外水深第一部分.zip` | 10.5 GB | Source zip #1 (active pipeline anchor; Step 08 bit-identical baseline references this). | 郭恒洋 → user, 2024-12 (high-confidence inference). |
| `multibeam/archive/国外水深第二部分.zip` | 14.0 GB | Source zip #2 (active pipeline anchor). | 郭恒洋 → user, 2024-12 (high-confidence inference). |
| `archive/source_zips/bathymetry.7z` | 26 GB | Same JAMSTEC corpus, single-7z packaging (frozen archive). | Unknown transfer channel; packaging mtime `Jul 25 2024` matches `2024-07-24` internal timestamps in `国外水深*.zip` — same packaging event, two compression formats. |
| `archive/source_zips/gravity.7z` | ~2 GB (part of 27 GB `source_zips/` total) | JAMSTEC gravity sub-corpus (frozen archive). | Unknown transfer channel. |
| `archive/bathymetry_data/*.zip` (776 files) | 25 GB | Same JAMSTEC corpus, per-cruise zip packaging (frozen archive). | Unpacked from `bathymetry.7z` or `国外水深*.zip` — same data, different layout. |
| `gravity_data/*.zip` (954 files) | 2 GB | JAMSTEC gravity sub-corpus, raw (no pipeline yet). | Unknown transfer channel. |

## Three-packaging redundancy

The JAMSTEC bathymetry corpus exists on this disk in **three independent
packagings** totalling ~51 GB:

1. `multibeam/archive/国外水深第{一,二}部分.zip` (24.5 GB, 2-file split)
2. `archive/source_zips/bathymetry.7z` (26 GB, single 7z)
3. `archive/bathymetry_data/*.zip` (25 GB, 776 per-cruise zips)

This was first documented in the 2026-05-11 attribution-doc update
("`JAMSTEC/bathymetry_data/` IS the source archive of `NCEI_multibeam/`")
and sharpened on 2026-05-16 with the `2024-07-24` packaging-timestamp
match.

**Decision (locked, user 2026-05-16)**: keep all three packagings;
**do not dedupe**.
- `multibeam/archive/国外水深*.zip` is the **active pipeline anchor**
  and the Step 08 bit-identical verification baseline.
- `archive/source_zips/bathymetry.7z` and `archive/bathymetry_data/*.zip`
  are **frozen archives** retained for reproducibility from alternate
  packaging entry points.

## Known unknowns

1. **Transfer chain for `bathymetry.7z` / `gravity.7z` /
   `bathymetry_data/*.zip`** is separate from 郭恒洋's `国外水深*.zip`
   transfer and is **unconfirmed**. Not chased (Q8-style stance).
2. **13 corrupt subzips** under `multibeam/raw/subzips_bad/` (from
   the 2026-04 audit) — whether the missing bytes are recoverable from
   the `bathymetry_data/*.zip` packaging was investigated in task
   `05-11-recover-bad-subzips` and **deliberately skipped** on
   2026-05-11: the JAMSTEC-side copies turned out byte-identical to the
   bad copies (same source corruption), and the per-entry-extraction
   salvage share (~1.5% of cruises, ~3% of data) fell below the
   recovery-effort threshold. Full breakdown:
   `multibeam/docs/bad_subzips_investigation_2026-05.md` +
   `.trellis/tasks/archive/2026-05/05-11-recover-bad-subzips/prd.md`.

## Cross-references

- `docs/experiments/2026-05_dataset-source-attribution.md` — full
  evidence chain for the JAMSTEC attribution + transfer-chain
  finalization footer (2026-05-16).
- `multibeam/docs/bad_subzips_investigation_2026-05.md` — corrupt
  subzip investigation closeout.
- `.trellis/tasks/05-11-singlebeam-integration/prd.md` — task that
  executed the `NCEI_multibeam/` → `jamstec/multibeam/` rename
  (PR-A, 2026-05-16) and the broader refactor.
- Sibling SOURCE.md sidecars: `archive/source_zips/SOURCE.md` (jamstec
  side, planned), `../ncei/tracklines_nc/SOURCE.md` (cross-link to
  the parallel NCEI singlebeam corpus).
