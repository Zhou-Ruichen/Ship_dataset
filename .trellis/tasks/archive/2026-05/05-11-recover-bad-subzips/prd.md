# Recover 13 bad subzips — SKIPPED (decision 2026-05-11)

> **STATUS**: Skipped after impact analysis. Archived without
> implementation. See "Final decision" below.

## Final decision (2026-05-11)

**Skip recovery. Archive the task.**

### Why skip

Quantified the recoverable data against the existing dataset:

| Metric | Existing 763 cruises | Recoverable from 12 zips | Recoverable share |
|---|---:|---:|---:|
| Cruise dirs | 763 | 12 | **1.5%** |
| `.dat` files | 5,140 | ~247 | ~4.8% |
| Raw size | 88 GB | ~1.3 GB zipped (~2–3 GB decompressed) | ~2–3% |
| Manifest OK rows | 5,096 | ~250 (estimate) | ~4.9% |

A 1.5%-cruise / ~3% data increment is below the noise floor for the
downstream products this dataset feeds: cell aggregation,
gridded-product validation, SWOT T1 residual baselines. Recovery
effort (build a per-entry extractor + Step 01 manifest rebuild + spot
checks + documentation) was sized at ~30–60 min — modest but not free,
and the benefit was hard to point to a concrete downstream improvement.

The current `file_manifest.parquet` already excludes the 13 cruises
cleanly (0 `bad_subzip` rows — Step 01 treats them as simply absent),
so there is **no cleanup action required** to make the dataset
internally consistent without them.

### What we keep from this brainstorm

The investigation produced two findings that should not be lost — both
already live in `docs/experiments/2026-05_dataset-source-attribution.md`
and the prd.md sections below:

1. **JAMSTEC ≡ NCEI source confirmation**: MD5 SAME for all 13 bad
   zips. The "switch to JAMSTEC copy" recovery path proposed in the
   original task description does **not exist** — they are the same
   file. This is a useful breadcrumb if anyone revisits the
   "complementary JAMSTEC subset" hypothesis later.
2. **Failure mechanism**: each cruise zip has exactly 1 corrupt inner
   entry; the existing pipeline lost the whole cruise because `7z x`
   short-circuits on any error. If a future similar drop appears, a
   per-entry recovery is mechanically feasible — see the design
   sketch below.

### If the decision is ever revisited

The task was fully scoped before being skipped. Resurrection is
straightforward:

- Recreate this task (or unarchive).
- The hard-coded cruise → bad-entry mapping is already in the design
  sketch.
- Reuse `03_recursive_extract.process_directory` for nested daily zips.
- Re-run `01_build_multibeam_manifest.py --overwrite`.

Triggers that would justify revisiting:

- A downstream product becomes sensitive enough that 3% more data
  materially shifts a result (unlikely for current targets).
- A future audit demands "complete coverage" attestation.
- A scientific question targets a region/era that happens to be
  covered preferentially by these 12 cruises (would require a
  spatial/temporal check against the 12 cruise IDs).

---

## Original scope and findings (preserved for the record)

### Goal (original)

Salvage as much data as possible from the 13 cruise zips currently in
`NCEI_multibeam/raw/subzips_bad/` by extracting each zip per-entry and
skipping the one corrupt entry, then re-running the Step 01 manifest so
the recovered cruises are first-class members of the dataset.

### Key findings

- **JAMSTEC source is identical to the bad copy.** MD5 comparison of
  `NCEI_multibeam/raw/subzips_bad/*.zip` vs
  `JAMSTEC/bathymetry_data/<same name>.zip` returned `SAME` for all 13.
  The "re-extract from JAMSTEC" path in the original task description
  does not exist — they are the same file.
- **Failure mode is recoverable in principle.** `unzip -t` reports
  exactly 1 bad entry per zip; the other entries pass. The pipeline
  lost the whole cruise because `7z x` exits non-zero on any error
  and `03_recursive_extract.py` then moves the whole zip to
  `subzips_bad/`.
- **One outlier**: `MR07-06_leg2_bathymetry_pi.zip` has 5 entries; the
  bad one is the only data archive (others are PDFs).

### Per-cruise breakdown (preserved)

| Cruise | Inner entries | Bad entry | Recoverable? |
|---|---:|---|---|
| `KR01-10_bathymetry_dmo` | 18 | `T20010703.zip` | Yes |
| `KR01-12_leg1_bathymetry_dmo` | 20 | `20010823.dat` | Yes |
| `KR06-11_bathymetry_dmo` | 11 | `20060910.dat` | Yes |
| `KR07-16_bathymetry_dmo` | 8 | `20071201.zip` | Yes |
| `KY13-04_bathymetry_dmo` | 14 | `T20130228.dat` | Yes |
| `KY14-10_bathymetry_dmo` | 18 | `20140713.dat` | Yes |
| `MR00-K02_bathymetry_dmo` | 38 | `20000221.zip` | Yes |
| `MR02-K01_bathymetry_dmo` | 41 | `20020112.zip` | Yes |
| `MR02-K04_leg1_bathymetry_dmo` | 27 | `20020628.zip` | Yes |
| `MR02-K05_leg1_bathymetry_dmo` | 21 | `20020906.zip` | Yes |
| `MR03-K01_bathymetry_dmo` | 41 | `20030224.zip` | Yes |
| `MR03-K03_leg1_bathymetry_dmo` | 26 | `20030613.zip` | Yes |
| `MR07-06_leg2_bathymetry_pi` | 5 | `MR07-04_MR07-06_bathymetry.zip` | **No** (sole data entry corrupt) |

### Recovery design sketch (if ever revisited)

```python
# NCEI_multibeam/code/01b_recover_bad_subzips.py
import zipfile
from pathlib import Path
from importlib import import_module

BAD_ENTRIES = {
    "KR01-10_bathymetry_dmo":            "T20010703.zip",
    "KR01-12_leg1_bathymetry_dmo":       "20010823.dat",
    "KR06-11_bathymetry_dmo":            "20060910.dat",
    "KR07-16_bathymetry_dmo":            "20071201.zip",
    "KY13-04_bathymetry_dmo":            "T20130228.dat",
    "KY14-10_bathymetry_dmo":            "20140713.dat",
    "MR00-K02_bathymetry_dmo":           "20000221.zip",
    "MR02-K01_bathymetry_dmo":           "20020112.zip",
    "MR02-K04_leg1_bathymetry_dmo":      "20020628.zip",
    "MR02-K05_leg1_bathymetry_dmo":      "20020906.zip",
    "MR03-K01_bathymetry_dmo":           "20030224.zip",
    "MR03-K03_leg1_bathymetry_dmo":      "20030613.zip",
}
# MR07-06_leg2 is not in the map: no recoverable data.

for cruise, bad in BAD_ENTRIES.items():
    src = SUBZIPS_BAD / f"{cruise}.zip"
    dest = DAT_BY_SUBZIP / cruise
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as zf:
        for name in zf.namelist():
            if name == bad:
                continue
            zf.extract(name, dest)
    # Reuse nested-zip extraction:
    process_directory(dest)  # imported from 03_recursive_extract

# Then: python3 code/01_build_multibeam_manifest.py --overwrite
```

### Files of interest (preserved for context)

- `NCEI_multibeam/code/01_build_multibeam_manifest.py` — manifest builder.
- `NCEI_multibeam/code/03_recursive_extract.py` — `process_directory`
  helper that handles nested daily zips.
- `NCEI_multibeam/raw/subzips_bad/` — 13 bad zips, untouched.
- `NCEI_multibeam/docs/bad_subzips.txt` — canonical list of 13.
- `docs/experiments/2026-05_dataset-source-attribution.md` — already
  records the JAMSTEC≡NCEI overlap finding (2026-05-11 update).

---

## Out of Scope (still applies)

- Re-running Steps 02–07.
- Step 08 validation (sibling task
  `05-11-step-08-full-global-validation`).
- Renaming `NCEI_multibeam/` (sibling task
  `05-11-singlebeam-integration`).
- `JAMSTEC/gravity_data/`.
