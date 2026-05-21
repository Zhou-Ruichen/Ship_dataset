# Research: Step 07A — Validation-Cell Preparation Preflight + Product Design

- **Query**: Design the Step 07 validation-cell products on top of Step 06B per-cell quality flags + Step 04B per-branch cells; verify joins, count candidates, surface cross-branch precedence conflicts, recommend Step 07B implementation path.
- **Scope**: internal (no external web search)
- **Date**: 2026-05-22
- **Owner**: trellis-research subagent (read-only audit; no production code; small TSVs under `ncei/derived/aggregation_design_audit/`)
- **Active task**: `.trellis/tasks/05-11-singlebeam-integration`

## Sister artifacts

- Public report: `ncei/docs/step07a_validation_cell_preflight_report.md`
- Audit TSVs: `ncei/derived/aggregation_design_audit/step07a_candidate_counts.tsv`,
  `ncei/derived/aggregation_design_audit/step07a_headline_product_counts.tsv`,
  `ncei/derived/aggregation_design_audit/step07a_overlap_conflicts.tsv`

## Headline numbers (Tasks 1+2+5)

### Task 1 — One-to-one join verification (PASS)

| branch | Step 04B rows | Step 06B rows | join both | left_only | right_only |
|---|---:|---:|---:|---:|---:|
| multibeam_ncei | 5,960 | 5,960 | 5,960 | 0 | 0 |
| regional_mrar | 9,019,383 | 9,019,383 | 9,019,383 | 0 | 0 |
| singlebeam | 14,611,054 | 14,611,054 | 14,611,054 | 0 | 0 |
| **total** | **23,636,397** | **23,636,397** | **23,636,397** | **0** | **0** |

Step 06B duplicates on `(branch, cell_id)`: **0**.
Per-branch counts match the brief and Step 04B top manifest exactly.
**Verdict**: Step 06B sidecar is a clean 1:1 keyed by `(branch, cell_id, lon_bin, lat_bin)` over the Step 04B cell universe; no orphans either direction. Safe to join Step 04B cell columns onto Step 06B flags for Step 07B without merge-loss risk.

### Task 2 — Multi-dimensional candidate counts (selected, full TSV)

`branch × quality_tier`:

| branch | high_confidence | medium_confidence | low_confidence | review_or_sensitivity_only |
|---|---:|---:|---:|---:|
| multibeam_ncei | 293 | 4,366 | 1,301 | 0 |
| singlebeam | 100,323 | 244,714 | 11,932,596 | 2,333,421 |
| regional_mrar | 0 | 89 | 3,876 | 9,015,418 |

`branch × evidence_class`:

| branch | within | cross | both | none |
|---|---:|---:|---:|---:|
| multibeam_ncei | 0 | 4,427 | 362 | 1,171 |
| singlebeam | 1,807,818 | 1,598,799 | 290,518 | 10,913,919 |
| regional_mrar | 96 | 1,889,172 | 33 | 7,130,082 |

`branch × use_for_primary_validation`:

| branch | True | False |
|---|---:|---:|
| multibeam_ncei | 4,659 | 1,301 |
| singlebeam | 345,037 | 14,266,017 |
| regional_mrar | 0 | 9,019,383 |

`branch × auv_sentry_flag`:

| branch | True |
|---|---:|
| multibeam_ncei | 8 |
| singlebeam | 0 |
| regional_mrar | 0 |

`branch × exclude_from_primary`:

| branch | True | False |
|---|---:|---:|
| multibeam_ncei | 0 | 5,960 |
| singlebeam | 0 | 14,611,054 |
| regional_mrar | 9,015,507 | 3,876 |

`branch × low_evidence_flag`:

| branch | True | False |
|---|---:|---:|
| multibeam_ncei | 1,171 | 4,789 |
| singlebeam | 10,913,919 | 3,697,135 |
| regional_mrar | 7,130,082 | 1,889,301 |

`branch × manual_review_any`:

| branch | True |
|---|---:|
| multibeam_ncei | 0 |
| singlebeam | 206,247 |
| regional_mrar | 0 |

`branch × sensitivity_only_flag`:

| branch | True | False |
|---|---:|---:|
| multibeam_ncei | 0 | 5,960 |
| singlebeam | 2,333,421 | 12,277,633 |
| regional_mrar | 9,015,418 | 3,965 |

`branch × use_for_supplementary_validation`:

| branch | True |
|---|---:|
| multibeam_ncei | 5,960 |
| singlebeam | 12,277,633 |
| regional_mrar | 3,876 |

`branch × validation_weight quartile`:

| branch | [0, 0.25) | [0.25, 0.5) | [0.5, 0.75) | [0.75, 1.0] |
|---|---:|---:|---:|---:|
| multibeam_ncei | 0 | 1,301 | 52 | 4,607 |
| singlebeam | 0 | 14,266,017 | 244,714 | 100,323 |
| regional_mrar | 9,015,418 | 3,876 | 89 | 0 |

### Task 5 — Cross-branch overlap and conflicts

Pairwise overlap (cell_id intersection):

| pair | overlap_cells | notes |
|---|---:|---|
| mb_ncei × sb | 4,127 | matches Step 04 audit + Step 05B (`mb_vs_sb`) |
| mb_ncei × mrar | 4,015 | matches Step 05B (`mb_vs_mrar`) |
| sb × mrar | 1,888,543 | matches Step 05B (`mrar_vs_sb`, 1,888,543) |
| jamstec × mb_ncei | **0** | spatially disjoint (see below) |
| jamstec × sb | 553,589 | of which 548,923 cells in JAMSTEC primary |
| jamstec × mrar | 506,077 | of which 501,935 cells in JAMSTEC primary |
| jamstec ∩ (mb ∪ sb ∪ mrar) | 924,001 | union coverage NCEI ∩ JAMSTEC |

True conflicts (BOTH sides say `use_for_primary_validation == True`):

| conflict | n_cells | note |
|---|---:|---|
| mb_primary AND sb_primary | **516** | Step 07B must rank with `mb > sb` per brief |
| mb_primary AND jam_primary | **0** | (spatially disjoint) |
| sb_primary AND jam_primary | **10,606** | Step 07B must rank with `jamstec_mb > sb` per brief |
| mrar_primary AND anything | 0 | `regional_mrar` is never primary by construction |

Mixed-signal cells (one side primary, the other in `review_or_sensitivity_only`):

| scenario | n_cells | note |
|---|---:|---|
| mb_primary AND sb_review | 0 | mb has no review tier; sb-review never coincides with mb-primary cells with `n_track_cells>=2` here |
| sb_primary AND mrar_review | 73,024 | benign — mrar stays in regional product; sb stays in sb product |
| mb_primary AND mrar_review | 38 | benign — same |

Supplementary footprints:

| set | n_cells |
|---:|---:|
| sb_supplementary × jam_primary | 541,441 |
| sb_supplementary × jam_full | 546,107 |
| sb_supplementary × mb_ncei | 4,127 |
| sb_supplementary × mrar | 1,875,893 |

## Task 4 — JAMSTEC availability (PRESENT)

JAMSTEC validation cells exist and follow §13.2 cell-id convention exactly. Files:

| file | rows | role |
|---|---:|---|
| `jamstec/multibeam/derived/cells_1min/cells.parquet` | 2,426,019 | full JAMSTEC mb cells (analogous to NCEI Step 04B output) |
| `jamstec/multibeam/derived/validation_cells_1min/primary_ship_validation_cells_1min.parquet` | 2,394,115 | already-tier-labelled primary validation set (A/B/C) |
| `jamstec/multibeam/derived/validation_cells_1min/sensitivity_original_ship_cells_1min.parquet` | 2,426,019 | parallel sensitivity export |
| `jamstec/multibeam/derived/validation_cells_1min/validation_cells_1min_summary.parquet` | 12 | metric summary |

JAMSTEC `cells_1min/cells.parquet` schema (key cols): `cell_id`, `cell_size`, `lon_bin`, `lat_bin`, `lon_center`, `lat_center`, `median_depth_file_balanced`, `median_elev_file_balanced`, `mean_depth_file_balanced`, `weighted_mean_depth_point_weighted`, `std_depth_between_file_cells`, `q25/q75/iqr_depth_between_file_cells`, `min/max/range_depth_file_cell`, `n_points_total`, `n_file_cells`, `n_files`, `n_cruises_guess`, `n_subzips`, `n_3col_file_cells`, `n_6col_file_cells`, `dominant_file_id`, `dominant_cruise_id_guess`, `dominant_track_kind`, `dominant_data_layout`, `source_dataset`.

JAMSTEC `primary_ship_validation_cells_1min.parquet` already carries `quality_tier` ∈ {A_tier, B_tier, C_tier}, `validation_weight` ∈ {0.4, 0.7, 1.0}, `ship_depth_m`, `ship_elev_m`, `use_for_primary_validation` (all True), `use_for_sensitivity_validation` (all False), `qcfiltered`, `quality_filter_version`, `source_dataset`.

Primary-tier counts: A_tier 696,989, B_tier 1,362,178, C_tier 334,948 → total 2,394,115. Weight stats: min 0.4 / median 0.7 / max 1.0. Cell-id format match: confirmed (e.g. `1min_1903_15738`).

JAMSTEC bounds: lat ∈ [-58.28, +76.59], lon ∈ [-179.99, +179.99] (global Pacific + N. Atlantic / Arctic).

NCEI mb bounds: lat ∈ [-64.6, +41.1], lon ∈ [-112.1, -38.4] (US East Atlantic + Caribbean + S. Atlantic AUV Sentry footprint).

The **NCEI mb × JAMSTEC = 0 cells overlap** is real spatial disjointness, not a cell-id format mismatch: NCEI mb is concentrated in the western Atlantic / S. Atlantic / Pacific eastern margin; JAMSTEC is concentrated in the Pacific. JAMSTEC and NCEI mb are therefore **complementary**, not redundant, in the strict-primary product.

## Task 6 — Source precedence rule (locked from brief)

Per the brief:

```
JAMSTEC mb (primary)  >  NCEI mb (strict primary)  >  NCEI sb high-confidence (expanded primary fill)
regional_mrar → always regional_experiment (never primary)
```

For every (cell_id) appearing in multiple primary candidates, the deterministic resolution is:

| concrete situation | resolution | column tag |
|---|---|---|
| jamstec primary + NCEI mb primary on same cell_id | jamstec wins, NCEI mb becomes `superseded_by_jamstec` | `precedence_resolution='jamstec_over_mb'` |
| jamstec primary + NCEI sb primary on same cell_id | jamstec wins, NCEI sb becomes `superseded_by_jamstec` | `precedence_resolution='jamstec_over_sb'` |
| NCEI mb primary + NCEI sb primary on same cell_id | NCEI mb wins, NCEI sb becomes `superseded_by_mb_ncei` | `precedence_resolution='mb_over_sb'` |
| NCEI mb primary + NCEI mrar (always non-primary) | NCEI mb retained in primary; mrar untouched in regional product | `precedence_resolution='primary_mb_regional_mrar_parallel'` |
| NCEI sb primary + NCEI mrar (always non-primary) | NCEI sb retained in primary (expanded ship); mrar untouched | `precedence_resolution='primary_sb_regional_mrar_parallel'` |

In current data:

| applicable to | n_cells affected by precedence resolution |
|---|---:|
| jamstec_over_mb | 0 (no overlap) |
| jamstec_over_sb | 10,606 |
| mb_over_sb | 516 |
| primary_mb_regional_mrar_parallel | 38 |
| primary_sb_regional_mrar_parallel | 73,024 |

The `regional_mrar` rows are **never deleted** by precedence — they stay verbatim in the `regional_mrar_experiment_cells` product. The `superseded_*` tag exists on rows that lose precedence and therefore do NOT appear in the merged primary export; they remain visible in their per-branch product with a `precedence_resolution` annotation.

## Task 3 — Proposed validation products (5 candidates, brief labels)

The five product labels are the brief's literal labels. Schema column lists below build from §14 Step 04B per-cell columns + Step 06B sidecar columns + new provenance columns.

### A. `strict_primary_multibeam_cells`

- Source filter: `branch IN {multibeam_ncei, jamstec_mb}` AND `use_for_primary_validation=True` AND `quality_tier IN {high_confidence, medium_confidence}` AND NOT `exclude_from_primary`.
- Optional AUV Sentry exclusion: see "AUV Sentry argument" below.
- Storage: flat parquet, no hive partition needed (small).
- Dedup: by `cell_id`, with `jamstec` winning over `multibeam_ncei` per precedence (no overlap in current data so no effective dedup).
- Estimated rows:
  - NCEI mb primary: `4,659 − 8 (auv_sentry) = 4,651` if AUV Sentry **OUT**; `4,659` if AUV Sentry **IN**.
  - JAMSTEC primary: 2,394,115 (all already primary).
  - **Combined (jamstec ∪ ncei_mb, dedup by cell_id, sentry IN)**: 2,394,115 + 4,659 − 0 = **2,398,774 cells**.
  - **Combined sentry OUT**: **2,398,766 cells**.
- Proposed schema (column list, in order):
  - Identity: `cell_id`, `lon_bin`, `lat_bin`, `lon_center`, `lat_center`, `lat_band_10deg`.
  - Depth/spread (NCEI side): `median_depth_m`, `mean_of_track_medians`, `std_of_track_medians`, `iqr_of_track_medians`, `min_track_median`, `max_track_median`, `range_track_median`, `n_track_cells`, `n_tracks`, `n_points_pass_total`, `n_unique_triples_total`, `duplicate_ratio_cell`.
  - Depth/spread (JAMSTEC side, harmonized): `ship_depth_m`, `weighted_mean_depth_point_weighted`, `std_depth_between_file_cells`, `iqr_depth_between_file_cells`, `min_depth_file_cell`, `max_depth_file_cell`, `range_depth_file_cell`, `n_file_cells`, `n_files`, `n_points_total`.
  - Quality flags (Step 06B side): `quality_tier`, `validation_weight`, `evidence_class`, `branch_role`, `auv_sentry_flag`, `source_risk_class`, `low_evidence_flag`, `manual_review_any`, `n_cross_branch_overlap`, `depth_bin`.
  - Provenance: `branch` ∈ {`multibeam_ncei`, `jamstec_mb`}, `source_dataset` (verbatim from JAMSTEC), `dominant_file_id` (JAMSTEC), `precedence_resolution`, `enforced_rules_version`, `merge_version`, `step07b_version`.
- Notes: NCEI side carries the Step 06B `validation_weight` ∈ {0.55, 0.75, 0.95}; JAMSTEC side carries its own legacy weight ∈ {0.4, 0.7, 1.0}. Step 07B MUST keep both visible; do NOT rescale either onto the other's scheme.

#### AUV Sentry argument (IN vs OUT)

Both directions defensible; the brief asks for an explicit recommendation.

**Argument to keep AUV Sentry IN strict_primary**:
- Rule 9 already downweighted them (`validation_weight=0.55`) and §18 invariant 5 PASSED — they are not zero-weighted, they are downweighted. Removing them from strict-primary would amount to a hard exclusion that contradicts the §17.5 principle "AUV-Sentry-like duplicate_ratio>0.5 → reduce recommended_weight, NEVER zero."
- N=8 is trivially small (1.3 ppm of 4,659 mb primary cells); no impact on global validation statistics.
- Downstream consumers can drop on `auv_sentry_flag=True` themselves.

**Argument to keep AUV Sentry OUT of strict_primary**:
- "Strict" is the strictest baseline; high-dup AUV-Sentry cells were the original audit motivation for the dup-ratio rule. Including a known-noisy class undermines the "strict" label semantics.
- The product can still surface them via `expanded_primary_ship_cells` or via the `validation_cell_catalog` with a tag.

**Recommendation**: **KEEP AUV Sentry IN strict_primary_multibeam_cells**, with `auv_sentry_flag=True` and `source_risk_class='auv_sentry_highdup'` preserved verbatim from Step 06B. The lock report (§1.4) is explicit that the policy is "downweight in production validation, surface in audit"; "strict" here means "tier ∈ {high, medium} AND mb-class branch" — downweight remains via `validation_weight=0.55`, not exclusion. Downstream consumers who want them removed can filter on `auv_sentry_flag` in one line; the inverse (re-injecting them after Step 07B drop) is not possible.

### B. `expanded_primary_ship_cells`

- Source filter: union of `strict_primary_multibeam_cells` PLUS NCEI sb cells with `use_for_primary_validation=True` (i.e. tier ∈ {high, medium} AND lat/depth filter has fired), with cell_id-level precedence applied so each cell appears at most once.
- Dedup outcome: any cell where both NCEI mb and NCEI sb claim primary → NCEI mb row retained; sb row dropped from this product (it persists in `validation_cell_catalog` with `precedence_resolution='mb_over_sb'`). Any cell where both JAMSTEC and NCEI sb claim primary → JAMSTEC row retained; sb row dropped (`precedence_resolution='jamstec_over_sb'`).
- Estimated rows:
  - Start from strict primary (sentry IN): 2,398,774.
  - Add NCEI sb primary: 345,037.
  - Subtract sb-only cells that lose to mb: 516.
  - Subtract sb-only cells that lose to JAMSTEC: 10,606.
  - **Total**: 2,398,774 + 345,037 − 516 − 10,606 = **2,732,689 cells**.
  - Of these: JAMSTEC source 2,394,115; NCEI mb 4,659; NCEI sb 334,431 (= 345,037 − 516 − 10,090; the 10,090 = 10,606 jam-over-sb minus the 516 mb-over-sb where mb already won, no double-discount).
    - Quick re-check: 4,659 (mb) + 2,394,115 (jam) + (345,037 − 516 − 10,606 + 10,606∩516) cells of sb. The 516 mb-over-sb overlap with jam is 0 (jam ∩ mb = 0, so 516 cells overlap with no jam cell). The 10,606 jam-over-sb overlap with mb is 0 (jam ∩ mb = 0). Therefore the sb residual is exactly 345,037 − 516 − 10,606 = 333,915.
  - **Corrected total**: 4,659 + 2,394,115 + 333,915 = **2,732,689** (matches above by inclusion-exclusion).
- Schema: same as `strict_primary_multibeam_cells` plus `final_primary_source` ∈ {`jamstec_mb`, `multibeam_ncei`, `singlebeam`}. NCEI sb rows fill the Step 04B sidecar fields (NCEI side) and leave the JAMSTEC-side fields null.
- Storage: flat parquet, hive-partitioned by `final_primary_source` if Step 11 wants source-routed reads (optional; not required at this scale).

### C. `supplementary_singlebeam_cells`

- Source filter: `branch='singlebeam'` AND `use_for_supplementary_validation=True`.
- Estimated rows: **12,277,633**.
- Notes: includes sb cells in low_confidence (11,932,596) and medium / high confidence not already in `expanded_primary_ship_cells`. This product is **coverage-focused** and **not for strict primary validation**.
- Schema: same Step 04B sb columns + Step 06B flags; no need to merge with JAMSTEC or mb (they are by definition disjoint in branch).
- Storage: hive-partitioned by `lat_band_10deg` (matches Step 04B layout), 18 partitions.
- Caveat: `manual_review_any=True` count = 206,247; downstream may want to filter these.

### D. `regional_mrar_experiment_cells`

- Source filter: `branch='regional_mrar'` (no extra filter — the brief says all 9.02M).
- Estimated rows: **9,019,383**.
- Notes: Always `branch_role='regional_experiment'`; never primary. `exclude_from_primary=True` for 9,015,507 of the 9,019,383 (the 3,876 cells in low_confidence have `exclude_from_primary=False` per rule 4; this is by design — the field is informational and the product never crosses into primary).
- Schema: Step 04B mrar columns + Step 06B sidecar (verbatim).
- Storage: hive-partitioned by `lat_band_10deg`, 17 partitions (matches Step 04B layout).
- Use: regional experiments + sensitivity-only validations.

### E. `validation_cell_catalog`

- Source: union of all 4 product memberships above. **One row per (cell_id × source_branch × product_membership)**.
- Estimated rows: rough upper bound = sum of products minus dedup. Concretely:
  - A. strict_primary (sentry IN): 2,398,774.
  - B. expanded_primary: 2,732,689 (= A + sb primary excluding precedence losers).
  - C. sb supplementary: 12,277,633.
  - D. mrar regional: 9,019,383.
  - **Catalog without further dedup (the "long" layout)**: each cell can appear in multiple products. Approximate row count = A + sb primary (333,915) + sb supplementary (12,277,633) + mrar (9,019,383) ≈ **24,031,705 rows**. (The NCEI mb 4,659 cells appear once in A and once in C-equivalent supplementary? No — supplementary_singlebeam_cells is sb only, so mb cells don't appear there. Recount: 2,398,774 (A) + 333,915 (sb primary residual after precedence) + 12,277,633 (sb supplementary; the 345,037 sb primary cells ALSO have `use_for_supplementary_validation=True`, so they're double-counted by design here as separate rows) + 9,019,383 = 24,029,705.)
- Useful columns: `cell_id`, `lon_bin`, `lat_bin`, `branch`, `quality_tier`, `validation_weight`, `evidence_class`, `branch_role`, `auv_sentry_flag`, `precedence_resolution`, `product_membership` (semicolon-joined: e.g. `expanded_primary;supplementary` for sb high-confidence cells, `regional_experiment` for mrar), `final_primary_source` (NULL if not in a primary product), `enforced_rules_version`, `merge_version`, `step07b_version`.
- Storage: hive-partitioned by `branch`, flat within branch. Or flat parquet single file (24M rows × ~30 cols ≈ 1–2 GB; acceptable).

### Storage layout summary

| product | layout | partitioned on | est. file size (rough) |
|---|---|---|---|
| strict_primary_multibeam_cells | flat parquet single file | none | ~50–100 MB (2.4M × ~30 cols) |
| expanded_primary_ship_cells | flat parquet single file | optional `final_primary_source` | ~70–120 MB (2.73M rows) |
| supplementary_singlebeam_cells | hive partitioned | `lat_band_10deg` | ~400–600 MB (12.3M rows) |
| regional_mrar_experiment_cells | hive partitioned | `lat_band_10deg` | ~300–500 MB (9M rows) |
| validation_cell_catalog | hive partitioned | `branch` | ~600 MB – 1.2 GB (24M rows) |

## Task 7 — Step 07B implementation recommendation

### Path A — Source-specific only (4 disjoint products + catalog)

- Step 07B emits 4 per-branch / per-role products; no `expanded_primary_ship_cells`. `validation_cell_catalog` carries 1 row per (cell_id, source_branch).
- Pro: zero precedence-decision risk lock-in; future Step 11 can apply different precedence rules without re-running Step 07B.
- Con: every downstream consumer that wants a merged primary must re-implement the precedence rule. JAMSTEC + NCEI mb need to be merged somewhere — Step 07B is the natural single boundary for that decision.

### Path B — Source-specific + expanded primary (5 products + catalog)

- Step 07B additionally emits `expanded_primary_ship_cells` where the precedence rule has already been applied at cell-id level. `validation_cell_catalog` carries 1 row per (cell_id, source_branch) AND a `final_primary_source` column for cells that survive into expanded primary.
- Pro: every downstream consumer can read one product, get a single canonical "best ship-supported depth per cell" without re-implementing precedence. Locks in the precedence rule once, in code, at the boundary where evidence is freshest.
- Con: harder to back out the precedence rule later. But the catalog still keeps `superseded_*` rows visible, so the rule is reversible without re-aggregating cells.

### Conflict volume

- mb_over_sb: **516** cells.
- jamstec_over_sb: **10,606** cells.
- jamstec_over_mb: **0** cells.

Total cells touched by primary precedence: **11,122** out of ~2.74M expanded-primary candidates = **0.41%**. This is small enough that consumers won't notice precedence resolution if it's done correctly, and small enough that any future precedence-rule change can re-emit Step 07B in well under a minute.

### Downstream consumer needs

Step 11 (GEBCO/ETOPO/SRTM15/SWOT validation) is the largest downstream consumer. It needs:
- A single canonical "ship truth" per cell (one depth, one weight) for each evaluation cell.
- Source provenance per cell (which branch wins) for stratified breakdowns.
- A separate sensitivity sample (no precedence; both rows kept) to quantify cost of precedence.

Path B serves both natively: `expanded_primary_ship_cells` is the one-depth-per-cell input; `validation_cell_catalog` (with `precedence_resolution`) is the sensitivity / audit input.

### Lock-in risk

Path B's risk is the precedence rule itself. It is already locked by the brief; this preflight is not redefining policy. Encoding it in code at Step 07B is therefore not "locking in early" — it is encoding a decision already made upstream.

### Recommendation

**Path B**. The conflict volume is small (~11k cells), the precedence rule is unambiguous (per brief Task 6) and verified deterministic against current data, and Path B is the only one that produces a single canonical primary depth per cell — which is exactly what Step 11 will need. The catalog preserves precedence-loser rows for sensitivity work, so Path B is not lossy.

## Task 8 — Go / no-go

**Step 07B implementation can proceed with Path B (source-specific + expanded primary + catalog).**

No open blockers. The 5 invariant assertions in Step 06B all PASS; the Step 06B↔Step 04B join is perfect 1:1; JAMSTEC is present and schema-compatible; precedence rule is deterministic and resolves exactly **11,122** primary-conflict cells with zero ambiguity.

Open items that Step 07B implementation must respect (not blockers, just enforcement):

1. JAMSTEC and NCEI carry **different `validation_weight` schemes** (NCEI ∈ {0.1–0.95, default 0.25}; JAMSTEC ∈ {0.4, 0.7, 1.0}). Step 07B MUST NOT rescale either; downstream Step 11 chooses how to consume them.
2. JAMSTEC has no `evidence_class` column equivalent. Step 07B should emit `evidence_class='jamstec_legacy'` or similar for JAMSTEC rows in the merged products — a placeholder that signals "not a Step 06B-evidence cell".
3. AUV Sentry policy is "downweight, not exclude"; Step 07B MUST preserve `auv_sentry_flag` + `source_risk_class` verbatim from Step 06B and not introduce a new column.
4. `mrar` cells MUST NOT appear in `strict_primary_multibeam_cells` or `expanded_primary_ship_cells` under any condition (including the 89 `medium_confidence` cross-validated mrar cells from rule 4, which have `exclude_from_primary=True` and `use_for_regional_experiment=True`).
5. Step 07B is the **first** step that touches JAMSTEC + NCEI in the same product. Step 06B did not — confirmed by reading §15.3, §16.4 (closed boundaries on Step 05B). The cross-source assertion `jamstec.cell_id ∩ ncei_mb.cell_id == 0` must be asserted at runtime; failure means upstream data drift.

## Caveats / Not found

- `auv_sentry_flag` is exclusive to NCEI rule 9; JAMSTEC has no analogous flag. Step 07B emits `auv_sentry_flag=False` for all JAMSTEC rows.
- `manual_review_any=True` cells in sb (206,247) all carry the same flag-only payload; the §18 invariant guarantees they were not excluded or upgraded solely on the flag. Step 07B carries the flag forward without acting on it.
- The 89 mrar `medium_confidence` cells from rule 4 (`mrar_v0_crossvalidated_medium`) have `use_for_primary_validation=False` AND `use_for_regional_experiment=True` per the brief and §17 lock; they are not a hidden primary candidate.
- JAMSTEC weight 1.0 cells (A_tier) represent the strongest validation evidence in the corpus. After merge they will dominate the high-end of the `validation_weight` distribution. NCEI mb has 293 high_confidence cells with weight 0.95; the global distribution is JAMSTEC-dominated. This is expected and not a defect.

## Cross-links

- Spec §13 (Step 04A): `.trellis/spec/backend/pipeline-design-decisions.md#13-ncei-step-04a--per-file-1-arcmin-cell-aggregation`.
- Spec §14 (Step 04B): same file `#14-ncei-step-04b--source-specific-global-1-arcmin-cell-merge`.
- Spec §15-§16 (Step 05A/B): same file, closed-boundary contracts.
- Spec §17 (Step 06A) / §18 (Step 06B): same file, policy enforcement.
- Step 06B run report: `ncei/docs/step06b_cell_quality_flags_report.md`.
- Step 06B semantic lock: `ncei/docs/step06b_semantic_lock_report.md`.
- Step 05B audit (headline residuals): `ncei/docs/step05b_cross_branch_overlap_audit_report.md`.
- Enforced rules: `.trellis/tasks/05-11-singlebeam-integration/research/quality_policy_enforced_rules.tsv`.
- Predecessor design audit: `.trellis/tasks/05-11-singlebeam-integration/research/step04_aggregation_design_audit.md`.
