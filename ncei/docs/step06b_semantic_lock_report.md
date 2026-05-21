# Step 06B Semantic Lock Report

Generated: 2026-05-22
Authority: orchestrator (main session) on behalf of human reviewer
Source: `ncei/derived/quality_policy_calibration_1min/quality_policy_candidate_rules.tsv` (Step 06A, 16 rules) + preflight review (`ncei/docs/step06b_quality_policy_rule_review.md`)
Locked artifact: `.trellis/tasks/05-11-singlebeam-integration/research/quality_policy_enforced_rules.tsv` (18 cols × 16 rules)
Predecessor spec: §17 (Step 06A) in `.trellis/spec/backend/pipeline-design-decisions.md`

This report **locks** the Step 06B semantics so the implementation can proceed without further policy-design discussion.

## 1. Locked decisions

### 1.1 Mitigations accepted

The 4 mitigations from the preflight review are accepted and encoded in `quality_policy_enforced_rules.tsv`:

| # | Mitigation | Encoding |
|---|---|---|
| 1 | Explicit `priority` for first-match resolution | `priority` int column (1=highest) |
| 2 | `condition_canonical` is the executable condition | `condition_canonical` column; original `condition` retained verbatim for audit |
| 3 | `slice_lookup_table` specifies which Step 06A calibration table to consult | new column with values {`by_lat_depth`, `by_source_pair`, `none`} |
| 4 | Rule 13 (`mrar_v0_shallow_highrisk`) drops vague residual OR clause | depth_bin filter (`depth_bin IN [0..200]`) alone targets the contamination zone; `reviewed_status='approved_with_revision'` |

### 1.2 Lat / depth filter semantics — exact 10° band membership

`applies_to_lat_band_filter` and `applies_to_depth_bin_filter` use **exact 10-degree band membership**, NOT continuous-interval intersection.

```
applies_to_lat_band_filter = "-70..-50"
  → matches lat_band_10deg IN {-70, -60, -50}    (3 bands)

applies_to_lat_band_filter = "-80..-70,-30..-20"
  → matches lat_band_10deg IN {-80, -70, -30, -20}    (4 bands)

applies_to_lat_band_filter = "60..90"
  → matches lat_band_10deg IN {60, 70, 80, 90}    (4 bands; lat_band_10deg ∈ {-90..80} step 10, but ranges including 90 are pre-clipped)
```

Same grammar for `applies_to_depth_bin_filter` where the values are the bin-left edges from §17.3 DEPTH_BINS: `0..200` → `depth_bin_lo == 0` (i.e. cells with `0 <= depth < 200`).

This semantic resolves the ambiguity flagged in preflight issue 2.

### 1.3 `manual_review_not_exclusion` is an INVARIANT, not a first-match rule

The rule `manual_review_not_exclusion` is **moved out of first-match priority** and reclassified as an invariant Step 06B implementation must enforce.

**Concretely:**

- TSV column `applies_as` (new) = `"invariant"` for this row only; `"first_match"` for all other 15 rules.
- TSV column `priority` for this row is **blank**; it does not participate in priority sorting.
- Step 06B MUST NOT use this rule's `recommended_weight` for tier assignment.
- Step 06B MUST treat it as a **post-tier-assignment audit check** with two assertions:
  - **Assertion A (no flag-only exclusion)**: 0 cells have `quality_tier == 'excluded' OR validation_weight < <flag-only-threshold>` solely because `manual_review_any == True` (i.e., they don't also match another rule that would have set the same tier).
  - **Assertion B (no flag-only upgrade)**: 0 cells have `quality_tier == 'high_confidence' OR 'medium_confidence'` solely because `manual_review_any == True`.
- Step 06B MUST preserve the `manual_review_any` field on all output cells for downstream audit (not stripped from the schema).

**Why:** §17.5 principle 4 says "manual_review_flag NEVER excludes alone." Encoding this as a first-match rule at priority 14 could itself become an inadvertent upgrade path (a flagged cell with no other matching rule would inherit medium_confidence 0.60 from this rule, which is itself a flag-only effect — exactly what the principle forbids). Reclassifying as an invariant guarantees the flag affects no cell's tier on its own.

### 1.4 AUV Sentry handling — flag + risk class, NOT a new branch_role

- Step 06B output schema MUST include:
  - `auv_sentry_flag` (bool)
  - `source_risk_class` (string) — values include `'auv_sentry_highdup'`
- Cells matching `mb_v0_highdup_sentry_downweight` (rule 9, priority 9) MUST get:
  - `auv_sentry_flag = True`
  - `source_risk_class = 'auv_sentry_highdup'`
  - `validation_weight = 0.55` (downweighted, NEVER zero)
  - `branch_role = 'multibeam_supplement'` (the default for multibeam_ncei; do NOT introduce `'auv_sentry'` as a separate branch_role).
- No other rule sets `auv_sentry_flag = True` or `source_risk_class = 'auv_sentry_highdup'`. The flag is exclusive to rule 9.
- Downstream consumers can drop / downweight on `auv_sentry_flag` as they choose; the policy here is "downweight in production validation, surface in audit."

This is encoded in rule 9's `reviewer_notes` column verbatim.

### 1.5 Priority sanity check — coherent, no contradictions

Verified after the manual_review-out-of-first-match reclassification:

| Tier of overlap concern | Concrete check | Result |
|---|---|---|
| Branch-specific high outranks universal high | rule 1 (mb-high prio 1) before rule 12 (any-high prio 12) | ✓ Coherent |
| Region-specific medium outranks universal high | rule 2 (sb-low-lat-shallow prio 2) before rule 12 (any-high prio 12) | ✓ Same tier as universal high — no downgrade; just specificity ordering |
| Conservative review beats high evidence in problem zones | rule 6 (Southern Ocean review prio 6) before rule 12 (any-high prio 12) → Southern Ocean cells stay review even with both-evidence | ✓ Coherent (intentional conservatism) |
| Universal sparse / dup catch-alls near end | rule 14 (low-unique prio 14), rule 15 (dup-heavy prio 15) — last two | ✓ |
| Mutually exclusive conditions don't conflict | rule 8 (n_track==1) vs rule 12 (n_track>=2); rule 9 (dup>0.5) vs rule 8 (dup<=0.1) | ✓ Mutually exclusive by construction |
| Mrar fall-through correct | rule 4 (mrar cross-validated prio 4) → escapes rule 11 (mrar default prio 11). Other mrar cells correctly fall to priority 11 unless rule 5 (shallow prio 5) catches them first | ✓ |
| Invariant rules don't compete | `manual_review_not_exclusion` has `applies_as=invariant`; not in 1-15 priority chain | ✓ |

**No contradictions found.** Priority chain is coherent. No revisions needed beyond the manual_review-as-invariant reclassification (already applied).

## 2. Updated enforced TSV — final schema and row inventory

`.trellis/tasks/05-11-singlebeam-integration/research/quality_policy_enforced_rules.tsv` is the **only authoritative source** for Step 06B; the candidate TSV is for audit/history only.

### Schema (18 cols)

```
rule_id                       string
candidate_tier                enum {high_confidence, medium_confidence, low_confidence, review_or_sensitivity_only}
applies_to_branch             enum {singlebeam, multibeam_ncei, regional_mrar, "*"}
applies_to_lat_band_filter    string (e.g. "-80..-70,-30..-20" or "*")
applies_to_depth_bin_filter   string (e.g. "0..200" or "*")
condition                     string  (original plain English, audit-only)
recommended_weight            float in [0, 1]
requires_step05_overlap       bool
exclude_from_primary          bool
evidence_basis                string
notes                         string
priority                      int (1=highest) — blank for applies_as='invariant'
applies_as                    enum {first_match, invariant}                     ← NEW THIS LOCK
condition_canonical           string (controlled-grammar, the executable form)
slice_lookup_table            enum {by_lat_depth, by_source_pair, none}
reviewed_status               enum {approved, approved_with_revision}
reviewed_at                   ISO date string
reviewer_notes                string
```

### Row inventory

- 15 rules with `applies_as=first_match`, priority 1 → 15:
  - priority 1: `mb_v0_high_overlap_lowdup` (mb high, slice-gated)
  - priority 2: `sb_v0_lowlat_shallow_overlap_high` (sb high, lat × depth × slice)
  - priority 3: `sb_v0_lowlat_deep_overlap_medium`
  - priority 4: `mrar_v0_crossvalidated_medium`
  - priority 5: `mrar_v0_shallow_highrisk` (REVISED — dropped OR clause)
  - priority 6: `sb_v0_southern_ocean_review`
  - priority 7: `sb_v0_highlat_north_review`
  - priority 8: `mb_v0_singletrack_lowdup`
  - priority 9: `mb_v0_highdup_sentry_downweight` (sets auv_sentry_flag)
  - priority 10: `sb_v0_no_overlap_low`
  - priority 11: `mrar_v0_default_sensitivity`
  - priority 12: `any_v0_overlap_both_high`
  - priority 13: `any_v0_strong_unique_medium`
  - priority 14: `any_v0_low_unique_low`
  - priority 15: `any_v0_dup_heavy_downweight`
- 1 rule with `applies_as=invariant`:
  - `manual_review_not_exclusion` — Step 06B post-check assertions A + B above.

### Tier distribution (informational)

- high_confidence: 3 rules (priorities 1, 2, 12)
- medium_confidence: 6 rules (priorities 3, 4, 8, 9, 13) + 1 invariant
- low_confidence: 3 rules (priorities 10, 14, 15)
- review_or_sensitivity_only: 4 rules (priorities 5, 6, 7, 11)

## 3. Step 06B implementation contract (the implementation must honor exactly)

Step 06B implementation MUST:

1. Read **only** `.trellis/tasks/05-11-singlebeam-integration/research/quality_policy_enforced_rules.tsv`. Do not read the candidate TSV.
2. Partition rules by `applies_as`:
   - `first_match` rules: sort by `priority` ascending, then apply in order; first match per cell wins.
   - `invariant` rules: do NOT use for tier assignment; apply only as post-check assertions per §1.3 above.
3. Implement the filter-grammar parser per §1.2 (exact 10° band membership).
4. Implement the slice-lookup join: when a rule has `slice_lookup_table != 'none'`, fetch the appropriate row from `ncei/derived/quality_policy_calibration_1min/quality_calibration_by_lat_depth.parquet` or `quality_calibration_by_source_pair.parquet` to evaluate slice conditions in `condition_canonical`.
5. Emit per-cell columns onto Step 04B cells: `quality_tier`, `validation_weight`, `evidence_class` ∈ {`within`, `cross`, `both`, `none`}, `low_evidence_flag`, `auv_sentry_flag`, `source_risk_class`, `branch_role`, `matched_rule_id`, `matched_rule_priority`, `enforced_rules_version`.
6. Preserve all original Step 04B cell columns (no schema-narrowing); preserve `manual_review_any`.
7. Run post-checks per §1.3 and fail loudly (exit non-zero) on any assertion violation.
8. Bump a Step 06B version constant (proposed `POLICY_ENFORCE_VERSION = "ncei_policy_enforce_v0.1.0"`) and write it into every output cell row.

## 4. Cross-links

- Spec §17 (Step 06A): `.trellis/spec/backend/pipeline-design-decisions.md#17-ncei-step-06a--quality-policy-calibration-audit`
- Preflight review: `ncei/docs/step06b_quality_policy_rule_review.md`
- Enforced rules (this lock): `.trellis/tasks/05-11-singlebeam-integration/research/quality_policy_enforced_rules.tsv`
- Step 06A candidate evidence: `ncei/derived/quality_policy_calibration_1min/quality_calibration_by_lat_depth.parquet`, `…by_source_pair.parquet`, `…by_branch.parquet`

## 5. Decision

**Step 06B implementation can proceed.**

All 5 sanity-check items are satisfied. Both deliverables (updated TSV + this report) reflect the locked semantics. No further policy design is required before code is written; the next concrete action is to implement `ncei/code/12_apply_quality_policy.py` (or analogous), driven entirely by the enforced TSV + the 4 contract clauses in §3 above.
