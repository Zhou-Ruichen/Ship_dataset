# Step 07A — Validation-Cell Preflight + Product Design

Generated: 2026-05-22
Predecessor: Step 06B (`ncei_policy_enforce_v0.1.0`) — sidecar `cell_quality_flags_1min.parquet` (23,636,397 cells, 31 cols; all 5 invariants PASS).
Scope: design preflight ONLY. No production code in Step 07A; Step 07B is the production step.

## 1. Inputs verified

| input | rows | status |
|---|---:|---|
| `ncei/derived/quality_flags_1min/cell_quality_flags_1min.parquet` | 23,636,397 | OK |
| `ncei/manifests/cells_1min_manifest.parquet` | 3 (one per branch) | OK |
| `ncei/derived/singlebeam/cells_1min/` | 14,611,054 | OK (matches 06B sb count) |
| `ncei/derived/multibeam/cells_1min/` | 5,960 | OK (matches 06B mb count) |
| `ncei/derived/regional_mrar/cells_1min/` | 9,019,383 | OK (matches 06B mrar count) |
| `jamstec/multibeam/derived/cells_1min/cells.parquet` | 2,426,019 | **JAMSTEC PRESENT** |
| `jamstec/multibeam/derived/validation_cells_1min/primary_ship_validation_cells_1min.parquet` | 2,394,115 | already-labelled primary set with A/B/C tiers |
| `jamstec/multibeam/derived/validation_cells_1min/sensitivity_original_ship_cells_1min.parquet` | 2,426,019 | parallel sensitivity export |
| enforced rules TSV (16 rules) | 16 + invariant | unchanged |

## 2. Task 1 — One-to-one join verification (PASS)

Outer join `Step 04B ⨝ Step 06B` on `(branch, cell_id, lon_bin, lat_bin)`:

| branch | both | left_only (only in 04B) | right_only (only in 06B) |
|---|---:|---:|---:|
| multibeam_ncei | 5,960 | 0 | 0 |
| regional_mrar | 9,019,383 | 0 | 0 |
| singlebeam | 14,611,054 | 0 | 0 |
| **total** | **23,636,397** | **0** | **0** |

Step 06B duplicates on `(branch, cell_id)`: **0**. Verdict: Step 06B is a clean 1:1 sidecar over the Step 04B universe. Step 07B may join Step 04B cell columns onto Step 06B flags without merge-loss risk.

## 3. Task 2 — Candidate counts (multi-dimensional)

Headline product candidates:

| product candidate | n_cells |
|---|---:|
| `strict_primary_multibeam_cells` (mb + JAMSTEC, AUV Sentry IN) | **2,398,774** |
| `strict_primary_multibeam_cells` (AUV Sentry OUT) | 2,398,766 |
| `expanded_primary_ship_cells` (with precedence applied) | **2,732,689** |
| `supplementary_singlebeam_cells` | **12,277,633** |
| `regional_mrar_experiment_cells` | **9,019,383** |
| `validation_cell_catalog` (1 row per cell × source, long layout) | ~24,029,705 |

Selected slices from the cross-tabulation cube (full table in `ncei/derived/aggregation_design_audit/step07a_candidate_counts.tsv`):

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

`branch × use_for_primary_validation == True`:

| branch | n_cells |
|---|---:|
| multibeam_ncei | 4,659 |
| singlebeam | 345,037 |
| regional_mrar | 0 |

`branch × auv_sentry_flag == True`: multibeam_ncei = 8 (matches rule 9 PASS); all other branches = 0.

`branch × exclude_from_primary == True`: regional_mrar = 9,015,507 (= 99.96% of the branch; matches §18 invariant 4 PASS); all other branches = 0.

`branch × manual_review_any == True`: singlebeam = 206,247; all other branches = 0 (these are the 96+10 Step 03B / Step 04A flagged tracks aggregated to cells).

`validation_weight` quartile distribution:

| branch | [0, 0.25) | [0.25, 0.5) | [0.5, 0.75) | [0.75, 1.0] |
|---|---:|---:|---:|---:|
| multibeam_ncei | 0 | 1,301 | 52 | 4,607 |
| singlebeam | 0 | 14,266,017 | 244,714 | 100,323 |
| regional_mrar | 9,015,418 | 3,876 | 89 | 0 |

## 4. Task 4 — JAMSTEC availability (PRESENT, schema-compatible)

JAMSTEC primary validation cells follow §13.2 cell-id convention exactly (`1min_{lat_bin}_{lon_bin}`, with `lon_bin` ∈ [0, 21600] and `lat_bin` ∈ [0, 10800]).

| file | rows | columns | quality system |
|---|---:|---|---|
| `cells_1min/cells.parquet` | 2,426,019 | 31 cols, includes `median_depth_file_balanced`, `n_files`, `dominant_*` | none — raw aggregation only |
| `validation_cells_1min/primary_ship_validation_cells_1min.parquet` | 2,394,115 | 38 cols, includes `ship_depth_m`, `quality_tier`, `validation_weight`, `use_for_primary_validation` | A_tier (696,989) / B_tier (1,362,178) / C_tier (334,948); weight ∈ {0.4, 0.7, 1.0} |
| `validation_cells_1min/sensitivity_original_ship_cells_1min.parquet` | 2,426,019 | 38 cols | sensitivity variant; 31,904 cells lost between primary and sensitivity |
| `validation_cells_1min/validation_cells_1min_summary.parquet` | 12 metric rows | — | one-row-per-metric summary |

JAMSTEC bounds: lat ∈ [-58.28, +76.59], lon ∈ [-179.99, +179.99] (Pacific-dominated + N. Atlantic + Arctic).

NCEI mb bounds: lat ∈ [-64.6, +41.1], lon ∈ [-112.1, -38.4] (W. Atlantic + Caribbean + S. Atlantic AUV-Sentry footprint).

**Crucial finding**: JAMSTEC `cells_1min` × NCEI `multibeam_ncei` = **0 cells overlap**. This is real spatial disjointness (verified by reading both bounds; the two corpora simply do not cover the same areas). JAMSTEC and NCEI mb are therefore **complementary**, not redundant: together they cover both the Pacific (JAMSTEC) and the Atlantic / S. Ocean AUV-Sentry footprint (NCEI mb) without any cell-id collision.

JAMSTEC overlap with the other two NCEI branches is significant: 553,589 cells in `cells_1min` (548,923 in JAMSTEC primary) overlap with NCEI singlebeam; 506,077 cells (501,935 in primary) overlap with NCEI mrar.

## 5. Task 5 — Overlap conflicts

Pairwise overlap counts (raw cell_id intersection):

| pair | overlap_cells | both call primary? | mixed-signal cells |
|---|---:|---:|---:|
| mb_ncei × sb | 4,127 | **516** mb_primary AND sb_primary | 0 mb_primary AND sb_review |
| mb_ncei × mrar | 4,015 | 0 (mrar never primary) | 38 mb_primary AND mrar_review |
| sb × mrar | 1,888,543 | 0 | 73,024 sb_primary AND mrar_review |
| jamstec × mb_ncei | 0 | 0 | — |
| jamstec × sb | 553,589 | **10,606** jam_primary AND sb_primary | (jam has no review tier) |
| jamstec × mrar | 506,077 | 0 | — |

True primary-precedence conflicts (cells where Step 07B must pick one source):

| conflict | n_cells | resolution |
|---|---:|---|
| jamstec_primary AND ncei_mb_primary | 0 | (no conflict in current data) |
| jamstec_primary AND ncei_sb_primary | 10,606 | jamstec wins |
| ncei_mb_primary AND ncei_sb_primary | 516 | mb wins |
| **total cells touched by precedence** | **11,122** | 0.41% of expanded primary candidates |

## 6. Task 6 — Source precedence rule (per brief, encoded)

```
JAMSTEC mb (primary)  >  NCEI mb (strict primary)  >  NCEI sb high-confidence (expanded primary fill)
regional_mrar → always regional_experiment (never primary)
```

Deterministic resolution table:

| concrete situation | resolution | `precedence_resolution` column value |
|---|---|---|
| jamstec primary + ncei_mb primary | jamstec retained | `jamstec_over_mb` |
| jamstec primary + ncei_sb primary | jamstec retained | `jamstec_over_sb` |
| ncei_mb primary + ncei_sb primary | ncei_mb retained | `mb_over_sb` |
| ncei_mb primary + regional_mrar | ncei_mb retained in primary; mrar untouched in regional product | `primary_mb_regional_mrar_parallel` |
| ncei_sb primary + regional_mrar | ncei_sb retained in primary; mrar untouched in regional product | `primary_sb_regional_mrar_parallel` |
| no conflict | — | `none` |

`regional_mrar` cells are **never** dropped by precedence; they remain verbatim in `regional_mrar_experiment_cells`. Cells that lose primary precedence are tagged `superseded_by_*` in the `validation_cell_catalog` so the decision is reversible without re-aggregating.

## 7. Task 3 — Proposed validation products

| product label | source filter | est. rows | dedup policy | storage layout |
|---|---|---:|---|---|
| `strict_primary_multibeam_cells` | (`multibeam_ncei` with `use_for_primary=True` AND tier ∈ {high, medium}) ∪ (`jamstec_mb` primary) | 2,398,774 | dedup by cell_id; jamstec wins (no current overlap) | flat parquet |
| `expanded_primary_ship_cells` | strict_primary_multibeam_cells ∪ (sb with `use_for_primary=True`); precedence applied | 2,732,689 | dedup by cell_id per precedence table | flat parquet (optionally hive on `final_primary_source`) |
| `supplementary_singlebeam_cells` | `singlebeam` with `use_for_supplementary=True` | 12,277,633 | no dedup needed (single branch) | hive on `lat_band_10deg` (18 partitions) |
| `regional_mrar_experiment_cells` | `regional_mrar` (all 9.02M, no filter) | 9,019,383 | no dedup needed (single branch) | hive on `lat_band_10deg` (17 partitions) |
| `validation_cell_catalog` | union of all 4 above with per-row provenance | ~24,029,705 | NOT deduped — each cell can appear in multiple product rows; product_membership column tracks where | hive on `branch` |

### AUV Sentry recommendation (rule 9 → 8 cells)

**KEEP IN strict_primary_multibeam_cells**, with `auv_sentry_flag=True` and `source_risk_class='auv_sentry_highdup'` preserved verbatim from Step 06B. Reasoning:

1. §17.5 principle 5 + §18 invariant 5 lock the policy as "downweight, never zero." Step 06B already set their `validation_weight=0.55`. Excluding them at Step 07B would be a hard-exclusion contradiction with the locked policy.
2. N=8 cells (1.7 ppm of strict-primary). No impact on global validation statistics.
3. Downstream consumers can drop on `auv_sentry_flag=True` in one line; the inverse (re-injecting after Step 07B drop) is not possible.

### Output schema sketches

All products share an identity prefix: `cell_id`, `lon_bin`, `lat_bin`, `lon_center`, `lat_center`, `lat_band_10deg`.

For `strict_primary_multibeam_cells` and `expanded_primary_ship_cells`:
- NCEI-side depth/spread (from §14 Step 04B): `median_depth_m`, `mean_of_track_medians`, `std_of_track_medians`, `iqr_of_track_medians`, `min_track_median`, `max_track_median`, `range_track_median`, `n_track_cells`, `n_tracks`, `n_points_pass_total`, `n_unique_triples_total`, `duplicate_ratio_cell`.
- JAMSTEC-side depth/spread (harmonized): `ship_depth_m`, `weighted_mean_depth_point_weighted`, `std_depth_between_file_cells`, `iqr_depth_between_file_cells`, `min_depth_file_cell`, `max_depth_file_cell`, `range_depth_file_cell`, `n_file_cells`, `n_files`, `n_points_total`.
- Quality flags (from §18 Step 06B): `quality_tier`, `validation_weight`, `evidence_class`, `branch_role`, `auv_sentry_flag`, `source_risk_class`, `low_evidence_flag`, `manual_review_any`, `n_cross_branch_overlap`, `depth_bin`.
- Provenance: `branch` ∈ {`multibeam_ncei`, `jamstec_mb`, `singlebeam`} (last only in expanded), `source_dataset`, `dominant_file_id`, `final_primary_source` (expanded only), `precedence_resolution`, `enforced_rules_version`, `merge_version`, `step07b_version`.

For `supplementary_singlebeam_cells` and `regional_mrar_experiment_cells`: Step 04B cell columns + Step 06B flags verbatim; no JAMSTEC fields; no precedence column.

For `validation_cell_catalog`: identity + `branch` + `quality_tier` + `validation_weight` + `evidence_class` + `branch_role` + `auv_sentry_flag` + `precedence_resolution` + `product_membership` (semicolon-joined: e.g. `strict_primary;expanded_primary` or `supplementary;catalog_only`) + `final_primary_source` (NULL if the cell did not win precedence) + version columns.

## 8. Task 7 — Implementation recommendation

**Recommended path: B (source-specific + expanded primary + catalog).**

Reasoning:
1. **Conflict volume is small (11,122 cells, 0.41% of expanded primary)** and unambiguously resolvable by the brief's precedence rule. No down-stream interpretation needed.
2. **Step 11 (GEBCO/ETOPO/SRTM15/SWOT validation) needs a single canonical "best ship-supported depth per cell"** as input. Path A would force every downstream consumer to re-implement the precedence rule.
3. **Path B is reversible**: the `validation_cell_catalog` preserves `superseded_by_*` rows for sensitivity work. The precedence rule itself can be re-evaluated by re-running Step 07B on the same Step 06B output (well under a minute given current scale).
4. **JAMSTEC × NCEI mb = 0 overlap** means there is no contentious mb-precedence decision in current data. The first time NCEI mb expands into JAMSTEC's footprint (e.g. via re-classified xyz files), the rule is already coded.

Path A remains a fallback if the precedence rule itself is contested. It is not contested.

## 9. Task 8 — Go / no-go

**GO. Step 07B implementation may proceed with Path B.**

No open blockers. Open items Step 07B implementation must respect:

1. **Different weight schemes per source**. NCEI weights ∈ [0.1, 0.95] (Step 06B); JAMSTEC weights ∈ {0.4, 0.7, 1.0} (legacy A/B/C). Step 07B MUST NOT rescale either; both must be preserved verbatim. Step 11 chooses how to consume.
2. **JAMSTEC lacks Step 06B-style `evidence_class`**. Step 07B emits `evidence_class='jamstec_legacy'` for JAMSTEC rows in merged products.
3. **AUV Sentry**: `auv_sentry_flag` + `source_risk_class` preserved verbatim from Step 06B; Step 07B does NOT introduce new columns.
4. **mrar is never primary**: regardless of `exclude_from_primary` value, the 9.02M mrar cells appear ONLY in `regional_mrar_experiment_cells` and in `validation_cell_catalog` rows with `branch_role='regional_experiment'`. The 89 rule-4 medium-confidence mrar cells with `exclude_from_primary=False` are NOT promoted to primary.
5. **Runtime assertion**: `jamstec.cell_id ∩ ncei_multibeam.cell_id == 0`. Step 07B MUST fail loudly if this changes — failure means an upstream re-classification has moved data into NCEI mb where JAMSTEC was, and the precedence rule must be re-confirmed before production runs.
6. **Sentinel mrar cells (the 89)**: keep `branch_role='regional_experiment'`; they are not a hidden primary candidate.

## 10. Headline counts (for the main agent)

| metric | n_cells |
|---|---:|
| **strict_primary_multibeam_cells** (NCEI mb + JAMSTEC, dedup, sentry IN) | **2,398,774** |
| **expanded_primary_ship_cells** (precedence applied) | **2,732,689** |
| **supplementary_singlebeam_cells** | **12,277,633** |
| **regional_mrar_experiment_cells** | **9,019,383** |
| **primary-precedence conflicts resolved** (mb_over_sb + jamstec_over_sb) | **11,122** |
| validation_cell_catalog rows (long layout) | ~24,029,705 |
| JAMSTEC × NCEI mb cell-id overlap | 0 |
| NCEI mb (sentry IN) primary candidates | 4,659 |
| NCEI sb primary candidates | 345,037 |
| NCEI sb primary candidates after losing to mb | 344,521 (= 345,037 − 516) |
| NCEI sb primary candidates after losing to mb + jamstec | 333,915 |

## 11. Output paths

| kind | path |
|---|---|
| public report (this file) | `ncei/docs/step07a_validation_cell_preflight_report.md` |
| research persist | `.trellis/tasks/05-11-singlebeam-integration/research/step07a_validation_cell_preflight.md` |
| candidate counts TSV | `ncei/derived/aggregation_design_audit/step07a_candidate_counts.tsv` |
| headline counts TSV | `ncei/derived/aggregation_design_audit/step07a_headline_product_counts.tsv` |
| overlap conflicts TSV | `ncei/derived/aggregation_design_audit/step07a_overlap_conflicts.tsv` |

## 12. Cross-links

- Spec §13 (Step 04A): `.trellis/spec/backend/pipeline-design-decisions.md#13-ncei-step-04a--per-file-1-arcmin-cell-aggregation`.
- Spec §14 (Step 04B): same file `#14-ncei-step-04b--source-specific-global-1-arcmin-cell-merge`.
- Spec §15-§16 (Step 05A/B): same file, closed-boundary contracts.
- Spec §17 (Step 06A) / §18 (Step 06B): same file, policy enforcement.
- Step 06B run report: `ncei/docs/step06b_cell_quality_flags_report.md`.
- Step 06B semantic lock: `ncei/docs/step06b_semantic_lock_report.md`.
- Step 05B audit (headline residuals): `ncei/docs/step05b_cross_branch_overlap_audit_report.md`.
- Enforced rules: `.trellis/tasks/05-11-singlebeam-integration/research/quality_policy_enforced_rules.tsv`.
- Predecessor design audit: `.trellis/tasks/05-11-singlebeam-integration/research/step04_aggregation_design_audit.md`.
