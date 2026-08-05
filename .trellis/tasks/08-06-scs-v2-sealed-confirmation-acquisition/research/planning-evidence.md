# Planning evidence

## Repository state at planning

- Ship repository: `main` at
  `e01d203b3c7018b664ea9f757f1bdb64f84a5f1c`.
- Downstream repository: `main` at
  `44a5b558d98301a65e464ccd1bc7d7d7c1be47dc`.
- Both trees have user changes. The acquisition task is owned only by the ship
  repository and must treat the downstream tree as read-only.
- Existing user changes in the ship tree are
  `ncei/archive/zhoushuai_processed_M/SOURCE.md`, `.serena/`, and
  `package-lock.json`; they are outside this task.

## Frozen exposed sets

Source 19-set:

- `ncei/derived/scs_ship_qc_v2_preflight/lineage/20260805T182211Z/
  jamstec_file_capabilities.tsv`
- SHA256:
  `cbd8405b67efc24ef5146320ddd10a27cf8671e21f02274e6415aba9d9bda37b`

```text
KM17-12C, KR03-04, KR10-03, KR13-18, KR15-16, KR15-18, KR16-16,
KR16-E06, KR18-03C, KY02-01, KY02-11, KY03-09, KY04-02, KY05-01,
KY12-08, KY14-02, KY14-03, MR00-K07, MR06-05
```

Source 12-set:

- `ncei/derived/scs_upstream_lineage_audit/20260804T202026Z/
  source_identity_ledger.csv`
- SHA256:
  `089ad0cacbff2a3cd89407ec8f818445691883c63f20b44c128b9791c9baaffb`

```text
KR03-04, KR13-18, KR15-16, KR15-18, KR16-E06, KY02-01, KY03-09,
KY05-01, KY12-08, KY14-03, MR00-K07, MR06-05
```

The exposed 12 are an exact subset of the current 19. The remaining seven
current cruises are not external groups, but already entered upstream lineage
and are equally ineligible.

Verified lineage receipts:

- lineage v2 manifest SHA256:
  `6823aea09ec24e27b35397c9c2e78f0854567e7848286712f13a9e22bc856018`
- lineage v2 verification SHA256:
  `f2d4203e8dbb2cee62d5f9bcc5c4ced365b4042b45e9bc16efcca9f18633af10`
- upstream lineage manifest SHA256:
  `54bc8cce94c6b156f14b0dcf4be252d5035183df069e22c30da0536aeb087dd0`
- upstream lineage verification SHA256:
  `e16c2fd56b596b7c373ed7bd497a5271ca59092ee65b1cc27fb154ebef7b3b9b`

## Downstream confirmation ceiling

The authoritative downstream run is:

```text
/mnt/data2/06-Projects/12-ggm_scs/outputs/diagnostics/
scs_lineage_contract_v2/20260805T193953Z
```

- `manifest.json` SHA256:
  `8b6ba1cbb957fda83d6baa5be1ac64a247007ac3575c648342c02c2f1a776ce5`
- `verification.json` SHA256:
  `41783d9e139062a461c9b76b45c9bf04b81a96443cc5609f58f86c698978ad02`
- `confirmation_registry.json` SHA256:
  `69e809404978365325ad60efbe919374bbea746f6e98e464af166da680379063`

Its status is `no_pristine_confirmation_available`; it explicitly forbids
renaming any current cruise as confirmation and requests acquisition of new
official data selected by metadata/geography only.

## MRAR evidence ceiling

- `M.rar` SHA256:
  `27611517707b361b04ad3b2711bb930cc5d2bfa634ceaa28c2d870e254b84c5a`
- current retained `SOURCE.md` SHA256 at planning:
  `db83b92457cf8b4874e8cbf3fe39d952a2e4992ca04cff3a07e5c7ddd859eeb1`
- Existing verified conclusion: `identity_status=not_recoverable` and
  `source_independence=unknown`.

The new task performs one additional local/history/adjacent-artifact pass. It
does not repeat an unbounded public search. A pre-2026-05-15 candidate normally
cannot be declared MRAR-independent without a direct source inventory; a
post-delivery observation can establish chronological non-membership in the
already frozen `M.rar` bytes.

## Official metadata sources

### NCEI primary discovery service

Official feature layer:

```text
https://gis.ngdc.noaa.gov/arcgis/rest/services/
web_mercator/multibeam_dynamic/MapServer/0
```

It is a polyline metadata layer with query support and fields including:

```text
SURVEY_ID, PLATFORM, SURVEY_YEAR, SOURCE, NGDC_ID, CHIEF_SCIENTIST,
DEPARTURE_PORT, ARRIVAL_PORT, INSTRUMENT, FILE_COUNT, TRACK_LENGTH,
TOTAL_TIME, BATHY_BEAMS, ENTERED_DATE, DOWNLOAD_URL, START_TIME, END_TIME
```

This permits a metadata-only SCS geometry query. The official per-cruise ISO
landing records add time/location, bbox, distribution formats, vertical datum,
lineage and use constraints. NCEI states that the multibeam archive primarily
retains raw vendor formats and may include navigation, sound-speed, tide,
offset and cruise-report sidecars:

```text
https://www.ncei.noaa.gov/iho-data-centre-digital-bathymetry/
submitting-marine-geophysical-data
```

### JAMSTEC secondary discovery source

JAMSTEC DARWIN and Data DOI provide official cruise identity, dates,
observation contents, access links and data-policy references:

```text
https://www.jamstec.go.jp/e/database/
https://www.jamstec.go.jp/e/database/data_policy.html
```

JAMSTEC's general policy supports scientific/educational access in principle,
but candidate-level access restrictions and archive availability must be
verified rather than inferred from the general policy.

## Planning conclusions

1. Metadata-only discovery is technically possible without querying depth.
2. Selection and acquisition must be separate immutable runs.
3. The archive `file_count` and `available_fields` must come from official
   metadata/sidecars, not from opening the downloaded archive.
4. `sealed` means byte-frozen and pipeline-isolated, not automatically proven
   source-independent or authorized for final evaluation.
5. Candidate selection needs a deterministic metadata-only tie break and a
   fixed stop rule; a shortfall must be reported rather than relaxing gates.
