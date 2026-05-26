# Step 08 — Role-Aware Safety Checks (strict vs expanded)

> Cross-stage spec captured from Step 08 Stage 3 (strict_primary_multibeam) and Stage 4 (expanded_primary_ship) full-global validation runs. See:
> - `ncei/docs/strict_primary_full_validation_audit_report.md` (Stage 3 audit)
> - `ncei/docs/stage4_expanded_primary_validation_audit_report.md` (Stage 4 audit)
> - `.trellis/tasks/05-11-step-08-full-global-validation/` (parent task)
> - `.trellis/tasks/05-27-stage4-expanded-primary-sensitivity/` (Stage 4 child)

---

## Rule

The Step 08 `run_full` safety-check set is **role-aware**: the set of checks emitted, and the PASS conditions, depend on the `product_role` of the validation product being run. Two `product_role` values are currently supported:

- `strict_primary_multibeam` (input: `strict_primary_multibeam_cells`, 2,398,774 rows)
- `expanded_primary_ship`     (input: `expanded_primary_ship_cells`, 2,732,689 rows)

The two roles share a common safety-check core but differ in three policy-driven checks. The script `ncei/code/14_validate_gridded_products_step08.py` switches on `product_role` inside both the runtime hard-stop guards (function `run_full`) and the post-run safety-check emitter (function `full_safety_checks`).

## Why

Singlebeam and regional-MRAR cells have different policy roles relative to the validation baseline:

- `strict_primary_multibeam` is the authoritative global baseline. Singlebeam and regional-MRAR cells must NOT enter it (else multibeam baseline is contaminated).
- `expanded_primary_ship` is a sensitivity / coverage-expansion product. Singlebeam cells are EXPECTED here as gap-fill (333,915 of them, marked `expanded_fill=True`); they must arrive only as net additions, never overwriting multibeam cells. Regional-MRAR cells are still forbidden.

Encoding these as a single uniform safety-check set would either falsely fail expanded runs (singlebeam expected) or miss the gap-fill-specific invariants. Role-aware branching keeps the safety set both precise and re-usable.

## How to apply

When `product_role == "strict_primary_multibeam"`, emit:

1. `input_row_count` — rows == expected (2,398,774)
2. `no_singlebeam_in_strict_primary` — `ncei_singlebeam` rows == 0
3. `no_regional_mrar_in_strict_primary` — `branch == "regional_mrar"` rows == 0

When `product_role == "expanded_primary_ship"`, emit:

1. `input_row_count` — rows == expected (2,732,689)
2. `no_regional_mrar_in_expanded_primary` — `branch == "regional_mrar"` rows == 0
3. `expanded_fill_count_matches_preflight` — `expanded_fill=True` rows == 333,915 (Step 07B preflight count; document any deviation explicitly)
4. `singlebeam_only_marked_as_expanded_fill` — `ncei_singlebeam` row count == `expanded_fill=True` row count (no singlebeam outside the gap-fill subset; no gap-fill cells from a non-singlebeam source)

Both roles must also emit (common core, role-agnostic):

- `validation_weight_preserved` (null count == 0)
- `quality_tier_preserved` (null count == 0)
- `evidence_class_preserved` (null count == 0)
- `matched_rule_id_preserved` (null count == 0)
- `sign_error_suspected_false` (per-product, derived from sample diagnostics; all PASS)
- `model_errors_do_not_corrupt_other_outputs` (per-product error products == 0; WARN allowed if non-zero but other products PASS)
- `no_model_residual_filtering` (PASS by construction; the metric pipeline must not drop validation cells based on residual magnitude — see [[step08-no-residual-filtering]])

The full safety output is written to `<output-dir>/full_validation_safety_checks_<role_slug>.tsv` with `role_slug ∈ {strict_primary, expanded_primary}`. The PRESENCE of role-specific check names is itself part of the contract: an audit reader inspecting `full_validation_safety_checks_*.tsv` should see exactly the role-appropriate check names, not the strict variant emitted for an expanded run (or vice versa).

## Acceptance evidence

- Stage 3 strict-primary run (2026-05-26): `no_singlebeam_in_strict_primary` PASS (0 rows), `no_regional_mrar_in_strict_primary` PASS (0 rows). See `ncei/derived/model_validation_1min_full_strict_primary/full_validation_safety_checks_strict_primary.tsv`.
- Stage 4 expanded-primary run (2026-05-27): `no_regional_mrar_in_expanded_primary` PASS (0 rows), `expanded_fill_count_matches_preflight` PASS (333,915 == 333,915), `singlebeam_only_marked_as_expanded_fill` PASS (333,915 == 333,915). See `ncei/derived/model_validation_1min_full_expanded_primary/full_validation_safety_checks_expanded_primary.tsv`.

## Anti-patterns

- ❌ Do not emit `no_singlebeam_in_*` checks in expanded runs — singlebeam IS expected as gap-fill.
- ❌ Do not weaken `no_regional_mrar_in_*` for any role — regional MRAR is policy-forbidden in both primary roles.
- ❌ Do not derive `expected_expanded_fill` from the input parquet itself (that would be circular). It is a separately-tracked invariant from Step 07B preflight (333,915 as of 2026-05-27); record any change in `ncei/docs/step08_preflight_report_*.md` before allowing the expanded-side check to be relaxed.
- ❌ Do not drop the `_preserved` checks (validation_weight / quality_tier / evidence_class / matched_rule_id) for any role; they enforce the Step 06B/07B contract on every downstream consumer.
