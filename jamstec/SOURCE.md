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

## Provenance — transfer chains (2026-05-16 finalization)

Two independent transferers, two distinct packaging events, one
underlying JAMSTEC corpus.

### Transferer 1 — 郭恒洋 (`国外水深*.zip`)

The two source zips at `multibeam/archive/国外水深第{一,二}部分.zip`
arrived from **郭恒洋 → user** in approximately **December 2024**
(file mtimes Dec 16 / Dec 17 2024; verified `readlink -f` shows both
are physical files, not symlinks). Source: user recollection
2026-05-16. **High-confidence inference, not externally verified.**
Packaging-internal timestamps: `2024-07-24` (date-named cruise zips
inside).

### Transferer 2 — 李杨 (`bathymetry.7z` + `gravity.7z`)

User clue (2026-05-16): "李杨 sent JAMSTEC bath+gravity; bath includes
KR06-03, gravity includes KM17-02." Fingerprint-verified:

- `KR06-03_bathymetry_dmo.zip` found inside
  `archive/source_zips/bathymetry.7z` (internal mtime 2024-04-11
  09:30:52).
- `KM17-02_gravity.zip` found inside `archive/source_zips/gravity.7z`
  (internal mtime 2024-04-10 17:05:52).
- `gravity_data/` (954 zips on disk) ≡ byte-identical unpack of
  `gravity.7z` (954 internal zips). Per-file diff of
  `KM17-02_gravity.zip` between the two locations: empty (byte-equal).
- `bathymetry_data/` (776 zips on disk) ≡ byte-identical unpack of
  `bathymetry.7z` (symmetric structure; same fingerprint method;
  `KR06-03_bathymetry_dmo.zip` present in both locations).

→ **`bathymetry_data/` and `gravity_data/` are NOT separate
transfers** — they are byte-identical unpacks of 李杨's two 7z's.
All four previously-"unknown" JAMSTEC transfer chains resolve to a
single 李杨 → user transfer of two compressed packages
(`bathymetry.7z` + `gravity.7z`), packaged April 2024 internally,
delivered to user during 2024.

### Historical naming note

This tree lived at `ship/NCEI_multibeam/` until 2026-05-16, when
task `05-11-singlebeam-integration` (PR-A) executed the rename to
`ship/jamstec/` after the JAMSTEC attribution was confirmed.
The earlier `NCEI_multibeam/` name was a mislabel inherited from the
original Chinese-language archive packaging (`国外水深*.zip`) and
never reflected actual provenance.

## Layout map

| Path | Size | Role | Source / transfer chain |
|---|---:|---|---|
| `multibeam/` | ~326 GB | Active processed pipeline (Step 00–11 complete; `code/`, `derived/`, `manifests/`, `docs/`, `figures/`, `output/`, `raw/`, `archive/`). | Built from `multibeam/archive/国外水深*.zip` extraction. |
| `multibeam/archive/国外水深第一部分.zip` | 10.5 GB | Source zip #1 (active pipeline anchor; Step 08 bit-identical baseline references this). | **郭恒洋 → user**, 2024-12 (high-confidence inference); internal packaging 2024-07-24. |
| `multibeam/archive/国外水深第二部分.zip` | 14.0 GB | Source zip #2 (active pipeline anchor). | **郭恒洋 → user**, 2024-12 (high-confidence inference); internal packaging 2024-07-24. |
| `archive/source_zips/bathymetry.7z` | 26 GB | Same JAMSTEC bath corpus, single-7z packaging (frozen archive). | **李杨 → user** (fingerprint: `KR06-03_bathymetry_dmo.zip` inside, internal mtime 2024-04-11); user-confirmed 2026-05-16. |
| `archive/source_zips/gravity.7z` | ~2 GB | JAMSTEC gravity sub-corpus, single-7z packaging (frozen archive). | **李杨 → user** (fingerprint: `KM17-02_gravity.zip` inside, internal mtime 2024-04-10); user-confirmed 2026-05-16. |
| `archive/bathymetry_data/*.zip` (776 files) | 25 GB | Same JAMSTEC bath corpus, per-cruise zip layout (frozen archive). | **Byte-identical unpack of `bathymetry.7z`** — NOT a separate transfer. `KR06-03_bathymetry_dmo.zip` present in both locations. Provenance = 李杨 (via the 7z). |
| `gravity_data/*.zip` (954 files) | 2 GB | JAMSTEC gravity sub-corpus, per-cruise zip layout (frozen archive; no pipeline yet). | **Byte-identical unpack of `gravity.7z`** — NOT a separate transfer; `KM17-02_gravity.zip` diff-verified byte-equal. Provenance = 李杨 (via the 7z). |

## Three-packaging redundancy → two independent transfers

The JAMSTEC bathymetry corpus exists on this disk in **three
packagings** totalling ~51 GB:

1. `multibeam/archive/国外水深第{一,二}部分.zip` (24.5 GB, 2-file
   split, date-named cruise zips inside, packaged 2024-07-24).
2. `archive/source_zips/bathymetry.7z` (26 GB, single 7z,
   cruise-ID-named DMO zips inside, packaged 2024-04-11).
3. `archive/bathymetry_data/*.zip` (25 GB, 776 per-cruise zips —
   derived: byte-identical unpack of #2).

→ **Two independent transfers, two different packaging styles, same
underlying JAMSTEC source corpus**:

- (a) 郭恒洋's 2024-07-24 date-named repackaging (#1).
- (b) 李杨's 2024-04-11 cruise-ID-named DMO packaging (#2 + #3).

The earlier "three coincidental packagings" framing is superseded:
~51 GB redundancy is now **traceable to two distinct transferers
working from the same JAMSTEC corpus at different times with
different packaging conventions**.

**Decision (locked, user 2026-05-16)**: keep all three packagings;
**do not dedupe**.
- `multibeam/archive/国外水深*.zip` is the **active pipeline anchor**
  and the Step 08 bit-identical verification baseline.
- `archive/source_zips/bathymetry.7z` (李杨), `archive/source_zips/gravity.7z`
  (李杨), and `archive/bathymetry_data/*.zip` (unpack of 李杨's 7z) are
  **frozen archives** retained for reproducibility from alternate
  packaging entry points.

## Known unknowns

1. **File-level overlap between 郭恒洋's `国外水深*.zip` and 李杨's
   `bathymetry.7z`** is expected to be ~100% (both are repackagings
   of the same JAMSTEC source corpus; the 2026-05-11 analysis already
   established 763/776 = 98.3% basename overlap between `NCEI_multibeam/`
   processed output and `bathymetry_data/`). Per-file byte-level
   comparison across packagings was not performed — out of scope for
   this task. The four-transfer-chain resolution above is sufficient
   for provenance attribution.
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
