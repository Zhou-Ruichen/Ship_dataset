# Implementation Plan — Step 08 Stage 4 · Expanded-Primary Sensitivity Validation

## 0. Reading Order for the Implementer

1. This task's `prd.md` — what is required and what must not change.
2. This task's `design.md` — exactly which functions to edit and the new script's contract.
3. Parent task: `.trellis/tasks/05-11-step-08-full-global-validation/{prd.md,implement.md}` — Stage 4 is its declared Stage 4.
4. Existing script: `ncei/code/14_validate_gridded_products_step08.py` — read `run_full`, `full_safety_checks`, `make_full_report`, `build_strict_expanded_comparison`, and the argparse block at the bottom before editing.

Project context:

- Stage 3 audit + GO: `ncei/docs/strict_primary_full_validation_audit_report.md`
- Stage 3 outputs (read-only): `ncei/derived/model_validation_1min_full_strict_primary/`
- Validation config: `jamstec/multibeam/configs/gridded_products_validation.yaml`
- Run logs go to: `ncei/output/logs/`

## 1. Execution Checklist

### Step 1 — Edit `ncei/code/14_validate_gridded_products_step08.py`

Use `design.md §2` as the contract.

- [ ] Add `--validation-product` CLI argument (default `strict_primary_multibeam_cells`, choices include `expanded_primary_ship_cells`).
- [ ] Refactor `run_full` to consume `args.validation_product`:
  - Derive `product_key`, `product_info`, `product_role`, `role_slug`, `run_stage_label` from the arg.
  - Use `role_slug` to interpolate output filenames (every place currently containing the literal string `strict_primary`).
  - Pass `run_stage=run_stage_label` to `build_cell_result`.
  - Replace `FULL_STRICT_PRODUCT_KEY` usages inside `run_full` with `product_key`.
- [ ] Update `full_safety_checks(...)` to branch on `product_role`:
  - strict: keep existing two checks (`no_singlebeam_in_strict_primary`, `no_regional_mrar_in_strict_primary`).
  - expanded: `no_regional_mrar_in_expanded_primary` (regional rows == 0), `expanded_fill_count_matches_preflight` (expanded_fill rows == 333,915), `singlebeam_only_marked_as_expanded_fill` (ncei_singlebeam rows == expanded_fill rows).
  - Common checks (`validation_weight_preserved`, `quality_tier_preserved`, `evidence_class_preserved`, `matched_rule_id_preserved`, `sign_error_suspected_false`, `model_errors_do_not_corrupt_other_outputs`, `no_model_residual_filtering`) stay.
- [ ] Update the hard-stop guards inside `run_full` (currently `Strict-primary input contains ncei_singlebeam rows` / `Strict-primary input contains regional_mrar rows`) to branch on `product_role` — for expanded, only the regional_mrar guard applies.
- [ ] Update `make_full_report` to switch the H1 title and §6 recommendation text on `product_role`.
- [ ] Verify that with `--validation-product strict_primary_multibeam_cells` (the default) the script still produces filenames containing `strict_primary` and the Strict-Primary report title — no observable change for existing strict callers.

### Step 2 — Add `ncei/code/15_strict_vs_expanded_compare_step08.py`

Use `design.md §3` as the contract.

- [ ] Argparse:
  - `--strict-dir` (default `ncei/derived/model_validation_1min_full_strict_primary`)
  - `--expanded-dir` (default `ncei/derived/model_validation_1min_full_expanded_primary`)
  - `--docs-dir` (default `ncei/docs`)
  - `--overwrite`
- [ ] Read strict-primary summary parquet and expanded-primary summary parquet.
- [ ] Compute `strict_vs_expanded_comparison.{parquet,tsv}` with columns from `prd.md §5.4`. Reuse the logic of `build_strict_expanded_comparison` (import from the main script, or re-implement). Extend with `delta_bias`, `delta_weighted_MAE`.
- [ ] Read strict by-cell `cell_id` column and expanded by-cell with the stratum columns from `design.md §3.3`.
- [ ] Compute set membership for each cell_id: `is_retained_multibeam` (cell_id in strict), `is_singlebeam_gapfill` (otherwise).
- [ ] Sanity assertion: `len(strict ∩ expanded) on cell_id == 2_398_774`; `len(expanded \ strict) on cell_id == 333_915`. If either fails, raise.
- [ ] For each stratum_col in (`source_role`, `branch`, `quality_tier`, `evidence_class`, `lat_band_10deg`, `depth_bin`, `region_10deg`):
  - Per (stratification, stratum): `expanded_cells`, `strict_cells`, `added_cells = expanded − strict`, `retained_multibeam_cells`, `singlebeam_gapfill_cells`.
- [ ] Write `expanded_primary_coverage_gain_summary.{parquet,tsv}` to expanded-dir.
- [ ] Write `ncei/docs/expanded_primary_global_validation_report.md` covering:
  - Run summary
  - Overall metrics (expanded)
  - Strict vs expanded delta table
  - Top coverage-gain strata per dimension
  - Sensitivity interpretation
  - Recommendation paragraph (secondary/sensitivity-only vs regional-use)

### Step 3 — Preflight (Stage 1 re-use)

Re-run preflight to refresh `preflight_*.tsv` for the expanded run-label and to PASS as the prerequisite. (Preflight already validates expanded product schema and row counts.)

```bash
python3 ncei/code/14_validate_gridded_products_step08.py \
  --stage preflight \
  --run-label full_expanded_primary \
  --config jamstec/multibeam/configs/gridded_products_validation.yaml \
  --overwrite
```

Expected outcome: `Preflight status: PASS` in log; preflight files written under `ncei/derived/model_validation_1min_full_expanded_primary/preflight_*.tsv`.

Stop condition: any FAIL in `preflight_role_checks.tsv`, `preflight_schema.tsv`, or `preflight_z_sign.tsv` → abort.

### Step 4 — Full expanded-primary run

```bash
python3 ncei/code/14_validate_gridded_products_step08.py \
  --stage full \
  --run-label full_expanded_primary \
  --validation-product expanded_primary_ship_cells \
  --config jamstec/multibeam/configs/gridded_products_validation.yaml \
  --product-name GEBCO_2024 \
  --product-name ETOPO_2022 \
  --product-name SRTM15_V2.7 \
  --product-name SDUST_2023 \
  --product-name TOPO_25.1 \
  --confirm-full \
  --overwrite
```

Notes:

- `SWOT_T1` is intentionally omitted (regional footprint; out of scope).
- The five products take roughly the same time as Stage 3 (~36 min wall clock, dominated by GEBCO + SRTM aggregate-window scans). Run with `nohup` and log to `ncei/output/logs/stage4_full_expanded_primary.nohup.log`.

Stop condition: status `FAIL` in script output, or any safety check FAIL — abort and report.

### Step 5 — Strict vs expanded comparison and report

```bash
python3 ncei/code/15_strict_vs_expanded_compare_step08.py \
  --strict-dir ncei/derived/model_validation_1min_full_strict_primary \
  --expanded-dir ncei/derived/model_validation_1min_full_expanded_primary \
  --docs-dir ncei/docs \
  --overwrite
```

Expected: `strict_vs_expanded_comparison.{parquet,tsv}`, `expanded_primary_coverage_gain_summary.{parquet,tsv}` written to expanded-dir; `ncei/docs/expanded_primary_global_validation_report.md` written.

### Step 6 — Validation / check

Run sanity checks (these are pass/fail; failures abort and fix):

- [ ] `ncei/derived/model_validation_1min_full_expanded_primary/` exists and contains:
  - 5 × `full_validation_by_cell_expanded_primary_<product>.parquet`
  - 8 stratified metrics files (`summary` + 7 strata) in parquet + tsv
  - `full_validation_product_status_expanded_primary.{parquet,tsv}`
  - `full_validation_safety_checks_expanded_primary.tsv` (all PASS)
  - `full_validation_sample_diagnostics_expanded_primary.{parquet,tsv}`
  - `skipped_products.tsv`
  - `strict_vs_expanded_comparison.{parquet,tsv}`
  - `expanded_primary_coverage_gain_summary.{parquet,tsv}`
- [ ] `ncei/docs/expanded_primary_global_validation_report.md` exists.
- [ ] `ncei/output/logs/14_validate_gridded_products_step08_full_expanded_primary.log` and `stage4_full_expanded_primary.nohup.log` exist.

For each ok product, run a programmatic re-check against the by-cell parquet:

- Row count == 2,732,689.
- `product_role` column unique value == "expanded_primary_ship".
- `expanded_fill=True` row count == 333,915.
- `ncei_singlebeam` rows (`source_provider == "ncei_singlebeam"`) == 333,915.
- `branch == "regional_mrar"` rows == 0.
- Null counts for `validation_weight`, `quality_tier`, `evidence_class`, `matched_rule_id` are 0.
- `pyarrow.compute.is_finite(depth_error_m)` All-True for rows whose status row in `full_validation_product_status_expanded_primary.tsv` says `ok`.

Strict-output non-mutation check:

- [ ] `ls -l ncei/derived/model_validation_1min_full_strict_primary/` mtimes are unchanged from Stage 3 (compare before/after — capture before during Step 3 prep).

### Step 7 — Final journaling

Update workspace journal entry with the run summary + path to the generated report and audit.

## 2. Validation Commands (Phase 3 audit input)

These are the commands the Phase 3 audit will use; producing them here so the implement script is auditable:

```bash
# Safety checks - must be all PASS
column -t -s $'\t' ncei/derived/model_validation_1min_full_expanded_primary/full_validation_safety_checks_expanded_primary.tsv

# Comparison table
column -t -s $'\t' ncei/derived/model_validation_1min_full_expanded_primary/strict_vs_expanded_comparison.tsv

# Coverage gain top entries per dimension
for d in source_role branch quality_tier evidence_class lat_band_10deg depth_bin region_10deg; do
  echo "=== $d ===";
  awk -F'\t' -v d="$d" 'NR==1 || $1==d' \
    ncei/derived/model_validation_1min_full_expanded_primary/expanded_primary_coverage_gain_summary.tsv | head -20
done
```

## 3. Review Gates

- Gate A: PRD + design + implement reviewed before `task.py start` (this task's planning gate — once these three docs are accepted, `start` is invoked).
- Gate B: After Step 3 preflight, log `Preflight status: PASS` must be observed before proceeding to Step 4.
- Gate C: After Step 4 full run, `Full expanded-primary status: PASS` in log; safety-checks TSV all PASS; before proceeding to Step 5.
- Gate D: After Step 5, all output files exist, non-empty, parquet/tsv readable; sanity re-check at Step 6 all PASS before the task is reported complete.

## 4. Rollback Points

- Step 1-2 (code change): if anything breaks, revert the two files; no data side effects.
- Step 3 (preflight): smoke-style outputs in expanded-dir — delete the directory if needed.
- Step 4 (full run): if the run fails partway, the script's error-status path writes the partial product_status and skipped_products and exits non-zero. Re-run with `--overwrite`.
- Step 5 (comparison): if comparison logic is wrong, delete the comparison files and re-run; the by-cell parquet from Step 4 remains intact.
- All steps: Stage 3 strict outputs are never touched. The atomic Stage 4 rollback is `rm -rf ncei/derived/model_validation_1min_full_expanded_primary/` plus revert of the two code files.

## 5. Dispatch Protocol for Pi

When Phase 2 dispatches `pi-adapter`:

- Active task: `.trellis/tasks/05-27-stage4-expanded-primary-sensitivity` (must be the first line of the Pi prompt).
- Implementer scope: Steps 1-7 of `§1 Execution Checklist`.
- Mandatory artifacts to consult before any edit: `prd.md`, `design.md`, this `implement.md`, and the existing `ncei/code/14_validate_gridded_products_step08.py`.
- Forbid: any modification to `ncei/code/0*-13_*.py` (earlier pipeline steps), `jamstec/multibeam/configs/*.yaml`, or `ncei/derived/validation_cells_1min/*.parquet`.
- Forbid: producing partial results without writing all required outputs from `prd.md §5`.
- Stop-and-report condition: any safety check FAIL, any expected output missing, or any constraint in `prd.md §8` violated.

## 6. Definition of Done (developer-facing)

- All 10 safety checks PASS in `full_validation_safety_checks_expanded_primary.tsv`.
- All required output files from `prd.md §5` exist and are readable.
- `strict_vs_expanded_comparison.tsv` shows 5 product rows with non-NaN delta_* columns.
- `expanded_primary_coverage_gain_summary.tsv` includes all 7 stratification dimensions.
- `ncei/docs/expanded_primary_global_validation_report.md` exists with all sections from `design.md §3.4`.
- `ncei/derived/model_validation_1min_full_strict_primary/` mtimes unchanged.
- Phase 3 audit can read all outputs and reach a recommendation paragraph.
