# Step 06B Preflight — Rule Review of `quality_policy_candidate_rules.tsv`

Generated: 2026-05-22
Reviewer: orchestrator (main session)
Source: `ncei/derived/quality_policy_calibration_1min/quality_policy_candidate_rules.tsv` (16 rules, Step 06A `ncei_policy_calib_v0.1.0`)
Approved copy: `ncei/derived/quality_policy_calibration_1min/quality_policy_enforced_rules.tsv` (this report + the approved TSV go in together as Step 06B preflight)

## 1. Per-rule plain-language summary

| # | rule_id | tier | one-line meaning |
|---:|---|---|---|
| 1 | `mb_v0_high_overlap_lowdup` | high | mb cells where within-branch overlap + low dup_ratio + cross-validated against mrar in same (lat=-70..-80 or -30..-20) × (500..6000m) → 0.95 |
| 2 | `mb_v0_singletrack_lowdup` | medium | mb single-track cells with low dup + enough unique points → 0.75 (most mb cells fall here) |
| 3 | `mb_v0_highdup_sentry_downweight` | medium | AUV-Sentry-class cells (dup>0.5) → downweight to 0.55, never exclude |
| 4 | `sb_v0_lowlat_shallow_overlap_high` | high | sb in lat -50..50 × depth 0..2000m with overlap + low dup + tight p95 → 0.85 |
| 5 | `sb_v0_lowlat_deep_overlap_medium` | medium | sb in lat -50..50 × depth 2000..6000m with overlap → 0.65 |
| 6 | `sb_v0_southern_ocean_review` | review | sb in Southern Ocean lat -70..-50 with extreme p99 or no overlap → 0.25, sensitivity-only |
| 7 | `sb_v0_no_overlap_low` | low | sb single-track + not in any cross-branch overlap → 0.35 (`low_evidence`) |
| 8 | `any_v0_low_unique_low` | low | any branch with n_unique_triples<10 → 0.30 (sparse) |
| 9 | `any_v0_overlap_both_high` | high | any branch with within-branch + cross-branch + tight p95 + low dup → 0.90 (`evidence_class='both'`) |
| 10 | `manual_review_not_exclusion` | medium | manual_review_any=True + acceptable residual → 0.60 (NEVER exclude on flag alone) |
| 11 | `mrar_v0_default_sensitivity` | review | mrar default → 0.20, `exclude_from_primary=True` |
| 12 | `mrar_v0_crossvalidated_medium` | medium | mrar cells co-validated with mb in tight zones (lat -70/-30 × 500-6000m) → 0.60, still excluded from primary |
| 13 | `mrar_v0_shallow_highrisk` | review | mrar in depth 0-200m (land/sentinel contamination risk) → 0.10 |
| 14 | `any_v0_dup_heavy_downweight` | low | any branch with dup>0.5 + no cross-branch evidence → 0.35 |
| 15 | `any_v0_strong_unique_medium` | medium | any branch with n_unique>=1000 + low dup + any overlap → 0.70 |
| 16 | `sb_v0_highlat_north_review` | review | sb in lat >=60 with cross-branch p95>300m → 0.30 |

## 2. Coverage assessment vs §17.5 locked principles

| Principle | Covered by | Status |
|---|---|---|
| mb high-confidence requires cross-validation | rule 1 + rule 9 | ✓ |
| sb stratified by lat × depth | rules 4, 5, 6, 16 | ✓ |
| mrar default sensitivity_only + `exclude_from_primary` | rules 11, 12, 13 | ✓ |
| manual_review_flag NEVER excludes alone | rule 10 explicit + no other rule depends on flag alone | ✓ |
| dup>0.5 downweight, never zero | rules 3, 14 (weights 0.55 / 0.35; never 0) | ✓ |
| n_unique_triples is the canonical weighting variable | rules 2, 4, 8, 15 explicitly use it | ✓ |
| No-overlap → low_confidence + low_evidence | rules 7, 8 | ✓ |

All 7 principles are encoded. **No coverage gap.**

## 3. Issues blocking direct enforcement (must resolve in Step 06B implementation)

### Issue 1 — Rule priority / conflict resolution undefined

When a cell matches multiple rules with different tiers (e.g., a sb cell at lat=-60 with n_track_cells>=2 in depth 0-2000m matches both rule 4 high_confidence AND rule 6 review_or_sensitivity_only), the TSV has no priority field. Step 06B MUST add an explicit priority order before enforcement.

**Mitigation in `enforced_rules.tsv`**: new `priority` column (int, 1=highest), assigned by specificity (most-specific filter wins).

### Issue 2 — Filter syntax not formalized

Three distinct filter forms appear:
- single range: `-50..50`
- multi-range: `-80..-70,-30..-20` (commas)
- set: `IN {-70,-60,-50}` (inside the condition column)

Step 06B parser MUST formalize:
- `applies_to_lat_band_filter`: comma-separated ranges, each `lo..hi` inclusive both ends, `*` = all
- same grammar for `applies_to_depth_bin_filter` (numeric bin-edge ranges)
- `condition` column uses plain-English logical expressions — Step 06B should EITHER (a) parse them with a controlled grammar OR (b) compile them to pandas boolean expressions case-by-case (this is OK for 16 rules but doesn't scale)

**Mitigation in `enforced_rules.tsv`**: condition strings rewritten in a controlled grammar (only `>=`, `<=`, `==`, `IN`, `AND`, `OR`, `NOT`); each rule documents whether it requires a slice-lookup join against Step 06A by_lat_depth/by_source_pair.

### Issue 3 — Slice-lookup conditions need an explicit join contract

Six rules reference Step 06A's stratified evidence by phrase, not by column name:
- "mb_vs_mrar same lat/depth slice has abs_residual_p95<175m" (rule 1)
- "within/cross slice abs_residual_p95<200m" (rule 4)
- "within_branch_abs_residual_p95<300m" (rule 5)
- "cross_branch_abs_residual_p99>1000m" (rule 6)
- "same-slice abs_residual_p95<150m" (rule 9)
- "rmse<150m AND abs_residual_p95<200m" (rule 12)

Step 06B MUST resolve these by joining cells to `quality_calibration_by_lat_depth.parquet` and `quality_calibration_by_source_pair.parquet`. The enforced_rules.tsv now adds an explicit `slice_lookup_table` column documenting which parquet to consult per rule.

### Issue 4 — Vague threshold in rule 13

`mrar_v0_shallow_highrisk` condition reads "depth_bin=0..200 OR abs(mrar_vs_sb residual) tail exceeds regional threshold" — the OR + the unspecified threshold makes this evaluate non-deterministically. Step 06B MUST replace "regional threshold" with a concrete number (proposed: `abs_residual_p99 > 1000m` per Step 05B aggregate observation), OR drop the OR clause and rely on depth_bin filter alone.

**Mitigation in `enforced_rules.tsv`**: rule 13's condition tightened to `depth_bin IN [0..200]` (drop the OR; depth filter alone already targets the contamination zone). A human can re-add a residual condition later if needed.

## 4. Promotion decision

**APPROVED with the 4 issues resolved in the enforced copy.** Without the priority + filter formalization, the same 16 rules could enforce inconsistently and reintroduce the global-uniform-threshold failure mode that Step 06A was designed to prevent.

The enforced copy at `ncei/derived/quality_policy_calibration_1min/quality_policy_enforced_rules.tsv` includes:
- Original 11 columns from the candidate TSV (verbatim where unambiguous).
- **`priority`** (int) — assignment order for conflict resolution.
- **`condition_canonical`** (string) — controlled-grammar rewrite of `condition`.
- **`slice_lookup_table`** (string) — which Step 06A parquet to consult for slice conditions ("by_lat_depth" / "by_source_pair" / "none").
- **`reviewed_status`** (string) — "approved" / "approved_with_revision" per rule.
- **`reviewed_at`** (string ISO date).
- **`reviewer_notes`** (string).

## 5. Step 06B implementation can proceed?

**YES, conditionally.** Step 06B implementation must:

1. Read the new `enforced_rules.tsv` (NOT the candidate TSV).
2. Apply rules in `priority` ascending order; first match wins per cell.
3. Implement the filter-grammar parser per §3 issue 2.
4. Implement the slice-join helper consulting `slice_lookup_table` per rule.
5. Emit columns onto Step 04B cells: `quality_tier`, `validation_weight`, `evidence_class`, `low_evidence_flag`, `auv_sentry_flag`, `matched_rule_id`.
6. Validate that no cell gets weight==0 (per principle #5) and that no rule excludes solely on `manual_review_any`.

## 6. Outstanding human-review items (pre-Step 06B)

Before code is written for Step 06B, the human should confirm:

1. The 4 mitigations above (priority assignment, condition canonical rewrites, slice_lookup mapping, rule 13 simplification) — review and adjust per-rule if needed.
2. Whether `applies_to_lat_band_filter` ranges in rules 1, 4, 5, 12 are EXACT 10-degree band membership or "any band intersecting the range." Current enforced copy interprets as exact-membership.
3. Whether rule 11 (`manual_review_not_exclusion`) should sit at lowest priority (it's a fall-through safety) or higher (it activates first on flagged cells). Current copy places it priority 11 (mid).
4. Whether AUV Sentry should also be a `branch_role` field rather than (or in addition to) a downweighted multibeam cell. Currently rule 3 only emits a weight.

## 7. Cross-links

- Spec §17 (Step 06A): `.trellis/spec/backend/pipeline-design-decisions.md#17-ncei-step-06a--quality-policy-calibration-audit`
- Candidate rules: `ncei/derived/quality_policy_calibration_1min/quality_policy_candidate_rules.tsv`
- Approved enforced rules: `ncei/derived/quality_policy_calibration_1min/quality_policy_enforced_rules.tsv`
- Step 06A report: `ncei/docs/step06a_quality_policy_calibration_report.md`
