# Ship-source processing repair, 2026-10-25

## Goal and authority

Deliver corrected source conversion and usable isolated products for complete
batches without waiting for the Tier-B download. The coordinator owns scientific
choices, interfaces, records and integration. At most two execution agents own
implementation and computation; they may not delegate further.

The initiating authority is Paseo message
4c6e17ab-329c-4d03-8e63-c90e91476cde from parent agent
cdf62907-4011-486c-a5d3-c08664213966. That message authorizes implementation,
source comparisons, scientific processing and first-batch delivery, not only
planning. SWOT reference-field changes and rescoring belong to the downstream
project.

## Inputs and settled evidence

- Read-only formal reports:
  `/mnt/data2/06-Projects/11-swot-ssl-encoder/reports/ship_source_processing_verification_v1.md`
  and `data_processing_literature_comparison_2026-10-25.md` in that directory.
- Original source records and comparisons:
  `/mnt/data2/06-Projects/11-swot-ssl-encoder/outputs/ship-source-processing-verification-v1/`.
- Retained swath revision:
  `ncei/derived/mb_round2/_runs/20261021_quality_revision/`;
  its 13-cruise native-quality repair and HNRO14RR sensitivity records already
  exist and must not be repeated or relabeled as clean observations.
- Fifteen legacy cruises contain 512234 original observations versus 512219
  retained NetCDF observations. Every first observation was omitted; trailing
  missing FAA became zero. Existing finite FAA and depth units and values agree.
- The 695 static MGD77T sources have a reproducible numerical conversion and
  692 point products, classified as 627 singlebeam and 65 multibeam.
- Five swath cruises have selected soundings from invalid zero ping navigation.
  MB84 extraction must carry the source projection sidecar.

## Work and ownership

1. FAA owner: new/reused MGD77T parser and legacy conversion in
   `ncei/trackline/`, its CLI/README, and outputs under
   `ncei/derived/processing_revision_20261025/legacy_faa/`.
   Excludes `ncei/trackline/file_cells.py`, owned by the swath executor while
   swath integration is active. No `_common/` writes.
2. Swath owner: `ncei/swath/`, `_common/mbsystem.py`, and necessary compatible
   selection changes in `ncei/trackline/file_cells.py`; outputs under
   `ncei/derived/processing_revision_20261025/swath/`.
3. Static MGD77T owner, assigned after the FAA parser stabilizes: source fields,
   explicit source-quality selection, existing aggregation and completed-batch
   outputs under `ncei/derived/processing_revision_20261025/trackline/`.
   Reuse `mgd77t.py` and the `basic_source_quality` aggregator policy. Keep the
   existing `mgd77t-xyz` three-column contract, and extend the existing fragment
   entry with explicit source-quality/output options rather than another
   processing platform. Preserve actual original-record indices when mapping
   skipped short records. Start with an explicit complete batch covering
   suspected navigation/bathymetry codes, headerless input and both retained
   instrument predictions; then extend the complete 695-source corpus with the
   same entry if output/time estimates remain small. Existing point products
   are 4.4 GiB per layer, L2 is 89 MiB; largest source has 7.53 million rows.
   Retain both the previous instrument prediction and provider BATH_INSTR;
   do not silently relabel all data singlebeam. The old fragment builder
   writes singlebeam into L1/L2 before calculating the L3 prediction; the
   revised source-field mode must propagate the retained prediction to all
   three layers without changing historical products.
4. Source correction inventory, assigned when an execution slot is free:
   provider evidence for sound speed, attitude, draft, tides and vertical datum,
   with unknown states preserved. No blanket physical reprocessing.
5. Coordinator: this `prd.md`, integrated `result.md`, and product-root
   `README.md`. Executors write only their named result records in this task.

## Interfaces and decisions

- Retain old products and original contracts. New roots are explicit; do not
  redirect downstream production silently.
- Restore missing observations as missing, preserve real zero FAA, first
  observations, original quality codes and formal cruise metadata.
- Retain the per-cruise gravity-formula, reference-system and processing
  declarations from the formal header: G_FORMU_CO/GRAV_FORMU,
  G_RFSYS_CO/GRAV_RFSYS and GRAV_CORR/ADD_DOC. Do not transform gravity
  reference systems in this source-conversion task.
- Provide source file identity, physical line number, original observation
  index, old NetCDF index and new index; document zero/one-based conventions.
- Preserve source time components and missing timezone state. Any UTC
  assumption must be explicit in fields and metadata.
- For swath, retain ping navigation, its validity and the reason, then propagate
  them to beams. No near-origin radius heuristic and no beam-only zero filter.
- The three HNRO07RR nonzero navigation anomalies are a bounded source-record
  follow-up, authorized by parent message b23edff4-16a5-4d38-8465-c344c80001cd.
  Compare their preceding/following native ping times and navigation, preserve
  their identities and suspicion flags. If the neighboring track establishes
  invalid source navigation, retain all original points and the basic
  selection, expose a distinct reviewed research selection, and reaggregate
  affected cells. Otherwise retain the basic selection and unresolved
  navigation status. No generic radius/speed threshold search.
- Keep depth positive downward in metres, FAA in mGal and existing one-minute
  grid definitions and median estimators.
- Source quality remains separate from numeric validity, instrument class and
  physical correction status. Unknown correction status is not proof of a
  missing correction. No deletion based on a gravity product being evaluated.
- Static MGD77T primary selection is `basic_source_quality`: existing basic
  checks and `source_quality_usable`, where neither NAV_QUALCO nor BAT_QUALCO
  is 3, 4, 5 or 6. Good/fair and unspecified codes remain, with unspecified
  status reported separately. The basic-only comparison remains available.
  POS_TYPE, BAT_TYPCO and BAT_CPCO are retained, not given new hard cutoffs.
- In the source-field mode, retain all original observations, including short
  records with missing depth. Keep a dense point-table row index separate from
  source observation index and physical line. Basic checks must reproduce the
  historical selected depths; added short records have no depth and remain
  unselected. Preserve the parser's known-UTC and explicit timezone-assumption
  distinction rather than assuming every source time is UTC.
- MGD77T correction metadata retains BATH_INSTR, BATH_ADD, SOUND_VEL,
  VDATUM_CO, BATH_INTRP and ADD_DOC from the formal header, alongside the
  per-record BAT_CPCO. Source-state evidence names its actual file or cruise
  scope; an instrument model or a code alone does not establish every applied
  physical correction.
- The source-state inventory must distinguish provider metadata declarations
  from settings of a recorded processing step. For swath, link each delivered
  source file to the available processing comments and their extraction scope;
  retain sound speed, roll/pitch/heading bias, heave, draft, tide and vertical
  datum separately. A CORRECTED depth reference is not a named vertical datum,
  and a disabled reapplication does not establish an uncorrected acquisition.
  No-depth-change is the default action where the required correction and
  supporting measurements have not been established. Preserve exact source
  text and unknown states rather than filling one cruise-wide assumption.
- HNRO14RR source anomalies keep their existing exact-record diagnosis and
  sensitivity interpretation.
- Duplicate-triple statistics and all-point/unique-triple medians come from
  `file_cells.aggregate_points`; cross-file merging retains median of per-file
  medians. Crossover calculations reuse the existing geometric functions in
  `ncei.trackline.crossover`, with original-record continuity after selection.
  Restrict initial crossover work to existing regions and singlebeam-classified
  tracks; do not copy the legacy "any backward time rejects a whole cruise"
  rule to corrected time data. No gravity-product difference is a deletion rule.
- Crossover continuity uses original source observation indices, not positions
  in a quality-filtered DataFrame. The existing `load_region` uses positions
  in its loaded table, so reuse its geometry with an explicit source-index
  continuity check in the new usage.

## Resource and mutation limits

- Initial free space on data2: approximately 3.8 TiB. Download progress at
  inspection: approximately 2480 of 4659 GB. Reserve room for the remaining
  download; inspect batch output estimates before expansion.
- First swath batch targets complete HNRO07RR and NT05-06 inputs, plus the
  known RR1412 zero-navigation source case. Expand only after completeness
  and output-size checks. Do not start a global rebuild.
- No data5 writes without user confirmation.
- Raw data, archives, old NetCDF, previous products, other repositories,
  `ncei/download/` and `/tmp/tierB_gapfill/` are read-only.
- Preserve the existing modification to
  `.trellis/tasks/10-21-mb-round2-quality-revision/prd.md`.
- No installation, commits, pushes, cleanup or data deletion. No automatic
  pytest, build or lint. Authorized checks are source-record comparisons,
  numerical statistics, and navigation/projection recomputation.

## Completion evidence

- [x] Reusable FAA conversion entry; 15 new NetCDF files and row mapping.
- [x] All-record comparison of finite values, missingness, first records,
      time and source metadata; real zero FAA retained.
- [x] Repaired official swath extraction with ping navigation and MB84 sidecars;
      HNRO07RR/NT05-06 complete-batch point/cell products and actual cases.
- [x] Remaining complete swath extension: AII8L18, HNRO05RR, HNRO06RR, RR1412.
- [x] Direct-source follow-up for the retained HNRO05RR nonzero navigation
      sequence, followed by its isolated research selection if confirmed.
- [x] MGD77T source time, identity, quality and observation/correction fields
      available in new point tables; selected policy and changed counts stated.
- [x] Complete 695-source batch, independent complete-source conversion,
      six-region source-indexed crossover calculation and six additional FAA.
- [x] Source physical-correction states linked to actual provider evidence.
- [x] Downstream-readable paths, columns, units, flags and reproduction commands,
      plus remaining batches and their specific dependencies.

## Current state

All bounded processing stages are complete: 21 source-preserving FAA surveys,
695 source-quality MGD77T tracks, six swath cruises and the source-correction
inventory. Numeric products have been read and checked by the downstream
project. Source-state tables, joins and evidence are integrated in the product
README and result.md. The downstream project also read the source-state
tables and matched every product source and referenced profile. No Ship
executor, batch or handoff remains active. Other historical surveys and
cruises are listed as future coverage, not active rebuilds.

## State history

- 2026-10-25: reports, original comparison tables, prior revision and current
  worktree inspected. Only the prior task PRD was modified at entry.
- New task created; the prior revision and downloader remain untouched.
- FAA executor: Paseo `7bdf3f9b-b993-487e-8c39-bc30e329f2fa`,
  codex/group/gpt-6.1-sol, full-access/max.
- Swath executor: Paseo `b368add4-61db-451b-b7e7-6162349c07b9`,
  codex/group/gpt-6.1-sol, full-access/max. This executor also owns adding
  `basic_source_quality` to the shared aggregator for the later static task.
- Parent received the initial actual-assignment notice. Both executions have
  completion notifications; no status polling is needed.
- Parent resource update (message
  `00af8f9c-3a54-40fe-b805-e0c180ab679c`): reserve the execution slot released
  when FAA finishes for the downstream remove-compute-restore numerical task.
  Ship continues with one execution slot, used sequentially for swath, static
  MGD77T and remaining source-state work. Do not refill both slots.
- FAA parser interface agreed with its owner: `ncei.trackline.mgd77t`,
  `iter_mgd77t`, `read_mgd77t`, `read_header`, `decode_time`; record objects
  preserve raw fields, physical source line, observation index and field count.
  Primary `time` requires a known timezone; the explicit alternative
  `time_assuming_unspecified_timezone_zero` records the compatibility assumption.
- NOAA formal headers were acquired using the parent's confirmed existing
  local proxy, without modifying any network or downloader configuration.
- Swath input completeness is in
  `ncei/derived/mb_round2/_runs/20261019T195752Z_first_batch/`, not the global
  completeness table. Executor checked all 6142 source/auxiliary paths and
  sizes against successful download records; estimated new output 31.89 GiB.
- Swath real cases completed under `swath/source_cases/`: NT05-06 MB84 correct
  projection and 5040 matching beam records; HNRO07RR 773 pings / 488 zero
  navigation; RR1412 287 pings / 2 zero navigation. RR1412 case L1/L2 has
  106356 selected points in 44 cells. Full six-cruise processing is active;
  runtime handles and commands belong to `swath_result.md`.
- Coordinator read of the new FAA artifact confirmed the 512234-row mapping,
  15 recovered first records, formal institutions, quality fields and explicit
  timezone states. Full-count details await final owner delivery in
  `legacy_faa_result.md`; no duplicate conversion or test-suite run is needed.
- FAA owner finished. Final record `legacy_faa_result.md` and product README
  are delivered; the parent received actual paths, columns, units and coverage.
  New FAA missing=305688, finite=206546, real zero=230. Previously used-position
  table has 267343 rows, missing=184997, finite=82346 including 79 real zeroes.
  Its names distinguish `faa_legacy_mgal` from `faa_revised_mgal`.
  The six additional complete local sources total 304615 observations and
  remain queued, not rebuilt. FAA's released execution slot is reserved for
  the parent reference-field computation.
- Parent message `f0bb60eb-ebc1-4bcf-95ca-2aae05490ff0` confirms actual reading
  of the FAA README, mapping schema and NetCDF. The downstream project owns
  its 267343-position join and use of 82346 nonmissing FAA values, and will
  read the existing formal gravity-header fields without a duplicate Ship
  extraction. Its reference-field executor `4a2cf014` occupies the released
  slot; Ship retains one execution slot for swath followed by MGD77T.
  The parent has retained the HNRO source ray-tracing evidence and no longer
  interprets code A alone as proof of absent sound-speed correction.
- Coordinator checked NOAA format PDF pages 10-11: navigation/bathymetry
  codes 1/2 mean good/fair, 3/4 poor/bad, 5/6 contributor/data-center suspect,
  and blank unspecified. This supports the settled source-quality selection.
  Small completed-source candidates are ar1-06 (both suspect fields),
  29he20120507 (navigation code 6), skq201818s (retained multibeam prediction),
  cntl01rr (short records) and dnwh-cho (no depth observations).
  Existing singlebeam-manifest bbox candidates for the six established
  crossover regions number 3/14/5/7/1/9 in the order in crossover.REGIONS;
  actual source-point clipping, continuity and pair geometry determine the
  supported crossings. These counts are not crossing counts.
- Static-source header check exposed a concrete parser extension needed
  before the next conversion: AR1-06 has 96 named .h77t columns, consisting of
  the 58 standard fields plus NOAA catalogue fields beginning DATE_ADDED,
  INST_SHORT and PARAM_ALL. The current `read_header` correctly handled the
  delivered 58-field FAA headers but rejects this static header as nonempty
  fields beyond 58. The next parser owner must preserve the named extension
  columns while retaining the existing standard-header contract. This also
  applies to the queued six-survey legacy extension; no delivered FAA
  observations need to be regenerated for this input-format addition.
  The complete 695-entry conversion manifest has 695 local headers:
  500 have 96 named columns and 195 have 58; all share the standard
  58-column prefix and none are missing.
- First swath batch completed and compared over all 48315733 soundings from
  540 files: source time, coordinates, depth, native state and identity are
  unchanged. New selection is 37697369 soundings / 18411 cruise cells.
  HNRO07RR removes 1288245 formerly selected soundings from invalid source
  navigation; NT05-06 selection and cells are unchanged with all 38
  projection sidecars propagated. First-batch pointers are published in the
  product-root README and integrated result. The four-cruise extension is
  active again after the first batch released the shared extraction capacity;
  its owner records PID 2659573 and recovery state in swath_result.md and
  swath/extension_resource_wait.json.
- Parent accepted the two-cruise delivery and assigned the exact three-ping
  navigation follow-up to the current swath executor. Remaining complete
  cruises continue. The parent separately checks the FAA observed-gravity,
  anomaly and normal-gravity closure; no upstream FAA change is requested.
- Parent closure results (message 24386af4-8458-46bb-b1aa-0256fc725e01) have
  been read from its CSV/JSON and retained in result.md without recomputation:
  88000911 is numerically consistent with IGF1980 on 4755 paired positions,
  gh7504 with IGF1930 on 1391, and 84002111 requires the source EOTVOS term
  to close against IGF1930 on 9338. These are evidence about source field
  semantics, not authorization to overwrite formal metadata, reconstruct FAA
  uniformly from GRA_OBS, or add EOTVOS to the supplied FAA.
- Bounded HNRO07RR source review is complete: three original target pings and
  eleven adjacent pings form three invalid source-navigation transition
  sequences (4/4/6 pings). All 2627 source DR records in the three files were
  compared directly with decoded navigation. The separate reviewed selection
  excludes 1634 published-selected soundings, giving 36433396 soundings and
  18268 cells. Only 58 affected cells were reaggregated; 57 disappear, one
  retains 39 other soundings, and 18267 cells remain unchanged. Published
  first_batch products stay unchanged. Exact ping evidence, the 2114-beam
  selection overlay and research cells are under swath/navigation_review.
- Coordinator inspected the first retained .inf from each six-cruise input
  group, plus source processing headers for HNRO05RR
  sb2100_vf.19990531-0852p.mb41.gz and HNRO06RR
  sb2100_vf.19990606-1648p.mb41.gz. Both source examples declare ray tracing,
  CORRECTED depths, 6 m draft and tide-off. Their nonzero metadata roll/pitch
  biases coexist with bias-off in the recorded mbprocess invocation; preserve
  calibration declarations separately from reapplication state. NT05-06 and
  AII8L18 sampled .inf files do not declare these correction states; RR1412
  lists SVP/SSV records only. See result.md for exact source scope.
- Six-cruise processing and complete source comparison finished: 1508 files,
  121116093 soundings, no source-value/identity differences, 99359551 selected
  soundings and 57703 merged cells under numeric navigation. Both batch
  processes exited successfully. Products occupy 16.17 GiB; data2 has 3.71 TiB
  free. Swath owner b368add4 finished and was reassigned one bounded follow-up
  before handing the single execution slot to MGD77T: the remaining HNRO05RR
  source sequence in file a4778b6cfe3209ba, navigation indices 174--178.
  The coordinator read its adjacent decoded records; direct-source evidence
  and any exact-key research exclusions remain the original executor's work.
- HNRO05RR source follow-up finished: 3957 original DR records from nine
  source files establish the zero-navigation interval and five invalid
  nonzero transition pings. Exact source times and coordinates agree with
  mblist; the new review preserves 745 soundings and excludes 709 formerly
  selected soundings. Its 27 affected cells disappear, leaving 464990
  soundings in 251 cells. Both case reviews merge to 99357208 soundings /
  60040 cruise cells / 57623 unique cells. Current research read pointer is
  swath/navigation_review_combined_cases/combined_ncei_cells_case_review.parquet.
  The coordinator read the review tables, integer source offsets, overlays
  and combined summary; previous releases are retained.
- Static MGD77T execution has now been assigned to the original FAA/parser
  owner 7bdf3f9b-b993-487e-8c39-bc30e329f2fa, Sol/full-access, using the sole
  Ship execution slot. This stage owns the named trackline parser, fragment,
  crossover/merge integration and source-quality output changes; swath and
  _common remain untouched. It will deliver the explicit five-source pilot,
  continue the complete 695-source batch, and extend the six available
  legacy FAA sources in a separate legacy_faa_additional root. Its result
  record is mgd77t_result.md. No second execution agent was started.
- Downstream has read the combined two-case swath research product and
  independently recomputed all 57623 merged cells from the six cruise-cell
  tables. Per-cell sounding and cruise-cell counts agree; maximum median-depth
  difference is 0 m. The coordinator read its
  outputs/ship-source-processing-verification-v1/six_cruise_delivery_check.json.
  The existing downstream 64-region comparison remains unchanged.
- The static parser owner identified the source literal FORMAT_77=MG77T in
  310 of the 500 extended headers. It accepts that source variant and all
  96 named fields without rewriting the declaration; the 195 standard headers
  and delivered FAA products retain their previous behavior. Static source
  conversion and its five-source pilot are still in progress.
- The parser owner also found repeated, concatenated header records in 11
  files and embedded PROJECT newlines in six. It preserves logical named
  fields and their original header evidence. NF1013L2's paired header declares
  SURVEY_ID=NF1013L1 while its observations and filename identify NF1013L2.
  The new source tables retain both identities and
  source_header_survey_id_mismatch=true; that paired header is not confirmed
  institution or physical-correction evidence for NF1013L2. Default
  read_header still requires an identity match.
- The five-track source-field pilot is delivered: 507264 source records,
  including 3212 short records; 485038 basic selections and 456054
  source-quality selections. The removed NAV/BAT union is 28984.
  Source-field comparisons and historical basic-cell comparisons agree.
  The coordinator read all five effective point tables and independently
  checked source-quality selections, indices, time states and retained classes.
- The source-field entry currently depends on the downstream comparison table
  and historical point products. The same owner must make those optional
  historical comparisons, not prerequisites for a newly completed source.
  Keep the active 695-source computation; demonstrate independent conversion
  on one complete source and compare its effective values without rebuilding
  the full batch. Existing classifications remain unchanged; a genuinely
  unclassified source must not silently enter the singlebeam merge.
- The static/FAA owner finished: all 695 sources retain 150587793 observations;
  primary selection retains 105457041 in 1235712 track cells, excluding the
  14294673 NAV/BAT union with 228089 overlapping flags. All source and
  historical basic comparisons agree. Independent AR1-06 conversion without
  historical/external inputs reproduces 77 fields and both cell selections.
  Six established regions have no supported within-batch inter-track
  crossings under either selection, with original-index continuity retained.
  The coordinator read final counts, effective-file checks, independent
  comparison and coverage tables, plus the two candidate-track latitude ranges.
- Six additional FAA products retain 304615 observations, with six restored
  first observations, 93513 missing FAA values and 172 real zeroes.
  The coordinator read all six NetCDF files and the complete row mapping.
  Original 15-survey products remain unchanged. Detailed evidence is in
  additional_faa_result.md; the six sources are also in the static collection.
- The sole Ship execution slot now belongs to Paseo
  88a4ee86-becf-4027-b0ee-59cb350c04cc, pi/magpie/group/glm-5.3, max,
  with no Pi mode parameter. Current profiles, model listing and provider
  capabilities were checked before dispatch. Its bounded responsibility is
  source-correction metadata, evidence and source_corrections outputs; it
  may not change delivered numeric products or delegate. It owns only its
  required source-metadata code/CLI additions and source_corrections_result.md.
  The original parser and swath owners have finished; no second Ship executor
  is active.
- Downstream actually read the completed static and additional FAA products.
  Its recomputed medians from all 695 track-cell tables differ by at most
  4.55e-13 m; per-cell counts agree. Branch overlap is 18224 cells and the
  spatial union 1063781, without combining the two depth estimates.
  The six additional NetCDF files agree with their same-source MGD77T points
  in coordinates, gravity fields, missingness and identities. The coordinator
  read complete_trackline_delivery_check.json in the downstream verification
  output directory. The fixed 64-region and 82346-position studies are unchanged.
- Source-correction tables have been produced for 695 static sources, 21 FAA
  products (six sharing static headers), and 1508 swath files plus one HNRO14RR
  evidence-only sample. Coordinator inspection returned four bounded repairs
  to the same GLM owner: retain actual .inf paths/notices as source evidence,
  link the HNRO14RR sample profile, expose MGD77T/FAA draft/tide/attitude states,
  and distinguish the HNRO06RR transducer-depth/heave adjustment mode from the
  explicit "Heave: not modified" setting. That owner remains the sole active
  Ship executor. Numeric products are unchanged; final metadata integration
  waits for the corrected artifacts and their coverage/key checks.
- The source-state owner finished the four repairs. Final coverage is
  695 static / 21 FAA / 1508 swath product sources plus one evidence-only
  HNRO14RR sample, with 123 profiles and 11422 original evidence passages.
  Coordinator read the final tables, schema, checks and decisive source
  passages: the 18 HNRO06RR files retain explicit unchanged heave and 6 m
  draft settings; RR1412 notices retain actual .inf paths and lines; the
  HNRO14RR sample joins profile 122; draft declarations distinguish the
  original 15 FAA surveys from the additional six. The coordinator took over
  only the source README's 15/21-survey wording and the result record's output
  size correction. No numeric product or source-metadata algorithm changed.
  Product-root README and integrated result now include the complete source
  states and remaining dependencies. All Ship execution slots are released.
- Final downstream receipt is complete: source_correction_links.json matches
  all 695 track IDs, 21 FAA mapping IDs, six shared FAA/static headers, 1508
  swath filekeys and paths, and every referenced profile. The HNRO14RR sample
  is excluded from product joins. Coordinator read that result and the updated
  upstream-deliveries.md. All completion items are satisfied; this bounded
  task is completed without starting further processing.
