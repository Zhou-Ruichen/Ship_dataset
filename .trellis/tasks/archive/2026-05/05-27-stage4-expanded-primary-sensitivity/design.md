# Design — Step 08 Stage 4 · Expanded-Primary Sensitivity Validation

## 1. Architecture Overview

Two pieces of work:

```
                                             reads
  expanded_primary_ship_cells.parquet   ─────────────►  14_validate_gridded_products_step08.py
  (Step 07B output, 2,732,689 rows)                       │
                                                          │ writes
                                                          ▼
                                          ncei/derived/model_validation_1min_full_expanded_primary/
                                          ├── full_validation_by_cell_expanded_primary_<product>.parquet (×5)
                                          ├── full_validation_metrics_summary_expanded_primary.{parquet,tsv}
                                          ├── full_validation_metrics_by_{quality_tier,evidence_class,source_role,branch,depth_bin,lat_band_10deg,region_10deg}_expanded_primary.{parquet,tsv}
                                          ├── full_validation_product_status_expanded_primary.{parquet,tsv}
                                          ├── full_validation_safety_checks_expanded_primary.tsv
                                          ├── full_validation_sample_diagnostics_expanded_primary.{parquet,tsv}
                                          └── skipped_products.tsv

  (above two output directories + strict-primary by-cell parquets)  ───►  15_strict_vs_expanded_compare_step08.py
                                                                            │
                                                                            ▼
                                          ncei/derived/model_validation_1min_full_expanded_primary/
                                          ├── strict_vs_expanded_comparison.{parquet,tsv}
                                          └── expanded_primary_coverage_gain_summary.{parquet,tsv}
                                          ncei/docs/
                                          └── expanded_primary_global_validation_report.md
```

`14_validate_gridded_products_step08.py` is extended to support an `--validation-product` argument so the existing `run_full` logic can drive either the strict-primary or the expanded-primary product. The comparison and coverage-gain analysis is a separate downstream script so the Stage 3 strict-primary script run remains byte-identical to its earlier output.

## 2. Changes to `14_validate_gridded_products_step08.py`

### 2.1 New CLI argument

Add to the argparse block (currently L1533-1538):

```python
parser.add_argument(
    "--validation-product",
    choices=["strict_primary_multibeam_cells", "expanded_primary_ship_cells"],
    default="strict_primary_multibeam_cells",
    help="Validation cell product to run the full stage against. Default is strict for backward compatibility.",
)
```

### 2.2 Parametric refactor of `run_full(args, logger)`

Refactor the existing `run_full` (L1203-1345) so that internal references to `FULL_STRICT_PRODUCT_KEY` are routed through `args.validation_product`:

```python
def run_full(args, logger):
    product_key = args.validation_product               # NEW
    product_info = EXPECTED_PRODUCTS[product_key]
    product_role = product_info["product_role"]         # "strict_primary_multibeam" or "expanded_primary_ship"
    role_slug = product_role.replace("_multibeam", "").replace("_ship", "")  # "strict_primary" / "expanded_primary"
    run_stage_label = f"full_{role_slug}"               # "full_strict_primary" / "full_expanded_primary"
    ...
    cells = prepare_validation_cells(product_key, attach_rule_ids=True)
    expected_rows = int(product_info["expected_rows"])
    ...
```

All places that wrote the hardcoded `"strict_primary"` substring into output paths are switched to interpolate `role_slug` instead:

| Old (L#) | New |
|---|---|
| `f"full_validation_by_cell_strict_primary_{pname}.parquet"` (L1275) | `f"full_validation_by_cell_{role_slug}_{pname}.parquet"` |
| `f"full_validation_metrics_summary_strict_primary"` etc. (L1309-1316) | `f"full_validation_metrics_summary_{role_slug}"` etc. |
| `"full_validation_sample_diagnostics_strict_primary.{parquet,tsv}"` (L1325-1326) | `f"full_validation_sample_diagnostics_{role_slug}.{ext}"` |
| `"full_validation_product_status_strict_primary.{parquet,tsv}"` (L1327-1328) | `f"full_validation_product_status_{role_slug}.{ext}"` |
| `"full_validation_safety_checks_strict_primary.tsv"` (L1330) | `f"full_validation_safety_checks_{role_slug}.tsv"` |
| `run_stage="full_strict_primary"` (L1268) | `run_stage=run_stage_label` |
| `output_dir(args.run_label)` (L1221) | unchanged — caller controls run-label; expanded run uses `--run-label full_expanded_primary` |
| `report_path = DOCS_DIR / "strict_primary_global_validation_report.md"` (L1338) | `report_path = DOCS_DIR / f"{role_slug}_global_validation_report.md"` |
| `run_label_report_path = DOCS_DIR / f"strict_primary_global_validation_report_{args.run_label}.md"` (L1340) | `run_label_report_path = DOCS_DIR / f"{role_slug}_global_validation_report_{args.run_label}.md"` |

### 2.3 Safety checks — branched on `product_role`

Rename `full_safety_checks(cells, diagnostics_df, product_status_df)` (L1175-1200) to accept the role and the expected count:

```python
def full_safety_checks(cells, diagnostics_df, product_status_df, product_key, product_role, expected_rows):
    checks = []
    checks.append({"check": "input_row_count", "status": ..., "details": f"rows={len(cells):,}; expected={expected_rows:,}"})

    regional = int((cells["branch"].astype(str) == "regional_mrar").sum())

    if product_role == "strict_primary_multibeam":
        singlebeam = int((cells["source_provider"].astype(str) == "ncei_singlebeam").sum())
        checks.append({"check": "no_singlebeam_in_strict_primary", "status": ..., "details": f"ncei_singlebeam rows={singlebeam:,}"})
        checks.append({"check": "no_regional_mrar_in_strict_primary", "status": ..., "details": f"regional_mrar rows={regional:,}"})
    else:  # expanded_primary_ship
        # Singlebeam is EXPECTED here — but only as gap-fill, not as overwrite.
        expanded_fill_rows = int(cells["expanded_fill"].fillna(False).astype(bool).sum()) if "expanded_fill" in cells.columns else -1
        singlebeam_rows = int((cells["source_provider"].astype(str) == "ncei_singlebeam").sum())
        checks.append({"check": "no_regional_mrar_in_expanded_primary", "status": "PASS" if regional == 0 else "FAIL", "details": f"regional_mrar rows={regional:,}"})
        checks.append({"check": "expanded_fill_count_matches_preflight",
                       "status": "PASS" if expanded_fill_rows == 333_915 else "FAIL",
                       "details": f"expanded_fill rows={expanded_fill_rows:,}; expected=333,915"})
        checks.append({"check": "singlebeam_only_marked_as_expanded_fill",
                       "status": "PASS" if singlebeam_rows == expanded_fill_rows else "FAIL",
                       "details": f"ncei_singlebeam rows={singlebeam_rows:,}; expanded_fill rows={expanded_fill_rows:,}"})

    weights_ok = bool(cells["validation_weight"].notna().all())
    checks.append({"check": "validation_weight_preserved", "status": ..., "details": ...})
    for col in ["quality_tier", "evidence_class", "matched_rule_id"]:
        ...

    # diagnostics, model_errors, no_model_residual_filtering as before — fine for both roles
    return pd.DataFrame(checks)
```

### 2.4 Sanity / hard-stop guards inside `run_full`

The current `run_full` has hardcoded hard-stop guards at L1231-1234 that error out if the cells contain singlebeam or regional_mrar. For expanded, those need to be conditioned on role:

```python
if product_role == "strict_primary_multibeam":
    if int((cells["source_provider"].astype(str) == "ncei_singlebeam").sum()) != 0:
        raise RuntimeError("Strict-primary input contains ncei_singlebeam rows")
    if int((cells["branch"].astype(str) == "regional_mrar").sum()) != 0:
        raise RuntimeError("Strict-primary input contains regional_mrar rows")
else:  # expanded_primary_ship
    if int((cells["branch"].astype(str) == "regional_mrar").sum()) != 0:
        raise RuntimeError("Expanded-primary input contains regional_mrar rows")
```

### 2.5 Report title and recommendation paragraph

Update `make_full_report` (L1118+) so the title and §6 recommendation switch on role:

```python
if product_role == "strict_primary_multibeam":
    lines.append("# Step 08 Strict-Primary Full Global Validation Report")
else:
    lines.append("# Step 08 Expanded-Primary Full Global Validation Report")
```

And the §6 recommendation (currently L1167-1169) becomes:

- strict_primary: existing text
- expanded_primary: a new paragraph describing strict-vs-expanded comparison location (cross-references `15_strict_vs_expanded_compare_step08.py` outputs) — final recommendation is filled in later by the comparison script's report-generation step or as a doc commit.

### 2.6 What does NOT change

- The preflight (Stage 1) and smoke (Stage 2) code paths remain untouched.
- `EXPECTED_PRODUCTS` dictionary already declares `expanded_primary_ship_cells` (L82-88) — no change there.
- The `build_metrics`, `build_cell_result`, `build_strict_expanded_comparison`, `sample_product_full`, `apply_z_convention`, `convention_diagnostic`, `prepare_validation_cells` functions are role-agnostic and reusable as-is.
- The legacy `--stage smoke/preflight/full` interface stays compatible; default `--validation-product` is `strict_primary_multibeam_cells`, so existing CLI calls (and any cron / scripts) keep producing the same byte-identical output.

## 3. New script: `15_strict_vs_expanded_compare_step08.py`

Path: `ncei/code/15_strict_vs_expanded_compare_step08.py`

### 3.1 Inputs (read-only)

- Strict-primary metrics: `ncei/derived/model_validation_1min_full_strict_primary/full_validation_metrics_summary_strict_primary.parquet`
- Expanded-primary metrics: `ncei/derived/model_validation_1min_full_expanded_primary/full_validation_metrics_summary_expanded_primary.parquet`
- Strict-primary by-cell: `ncei/derived/model_validation_1min_full_strict_primary/full_validation_by_cell_strict_primary_<product>.parquet` (×5)
- Expanded-primary by-cell: `ncei/derived/model_validation_1min_full_expanded_primary/full_validation_by_cell_expanded_primary_<product>.parquet` (×5)
- (Optional, used as authoritative cell catalog) `ncei/derived/validation_cells_1min/expanded_primary_ship_cells.parquet`

### 3.2 Outputs

Written to `ncei/derived/model_validation_1min_full_expanded_primary/`:

- `strict_vs_expanded_comparison.{parquet,tsv}` — one row per (product_name, sampling_method). Built by joining the two summary tables on `(product_name, sampling_method)` and computing delta_* columns. Reuses the existing `build_strict_expanded_comparison` helper from the main script (importable) or re-implemented; the helper already produces strict_count, expanded_count, coverage_gain_count, delta_MAE/RMSE/weighted_RMSE. Extend it with `delta_bias`, `delta_weighted_MAE`.
- `expanded_primary_coverage_gain_summary.{parquet,tsv}` — by-stratum coverage gain.

### 3.3 Coverage gain computation

```python
strict_cells = pq.read_table(strict_cells_path, columns=["cell_id"])  # 2,398,774 rows
expanded_cells = pq.read_table(expanded_cells_path, columns=[
    "cell_id", "source_role", "branch", "quality_tier", "evidence_class",
    "lat_band_10deg", "depth_bin", "region_10deg", "expanded_fill", "source_provider",
])  # 2,732,689 rows

# Multibeam-retained = expanded ∩ strict on cell_id
# Singlebeam gap-fill = expanded \ strict on cell_id == cells with expanded_fill=True
strict_ids = set(strict_cells["cell_id"].to_pylist())  # or polars/pyarrow set ops if memory matters
expanded_df["is_retained_multibeam"] = expanded_df["cell_id"].isin(strict_ids)
expanded_df["is_singlebeam_gapfill"] = ~expanded_df["is_retained_multibeam"]

# Per-stratum counts
for stratum_col in ["source_role", "branch", "quality_tier", "evidence_class",
                    "lat_band_10deg", "depth_bin", "region_10deg"]:
    g = expanded_df.groupby(stratum_col).agg(
        expanded_cells=("cell_id", "count"),
        retained_multibeam=("is_retained_multibeam", "sum"),
        singlebeam_gapfill=("is_singlebeam_gapfill", "sum"),
    ).reset_index().rename(columns={stratum_col: "stratum"})
    g["stratification"] = stratum_col
    rows.append(g)

coverage_gain = pd.concat(rows, ignore_index=True)
# Add deltas vs strict by matching strict's stratum counts per stratification
```

For each stratum, compute:

- `expanded_cells` (count from expanded by-cell)
- `strict_cells` (count from strict by-cell, joined by stratum if the column exists in strict by-cell — it does, since strict has same lat_band_10deg / depth_bin / region_10deg / quality_tier / evidence_class / source_role / branch columns)
- `added_cells = expanded_cells − strict_cells`
- `retained_multibeam_cells` (intersection on cell_id)
- `singlebeam_gapfill_cells` (set difference; expected == `added_cells` for any stratum since strict ⊂ expanded by cell_id by construction)

Cross-check: `singlebeam_gapfill_cells` per stratum must equal the `expanded_fill=True` row count per stratum (otherwise the expansion contract is broken).

### 3.4 Driver attribution and report generation

After computing the comparison and coverage tables, the script writes `ncei/docs/expanded_primary_global_validation_report.md` covering:

1. Run summary (preflight, safety, elapsed)
2. Overall metrics table (expanded_primary)
3. Strict vs expanded comparison table (per product)
4. Coverage gain by stratification (top-N rows per dimension)
5. Sensitivity interpretation:
   - Is delta_RMSE dominated by added singlebeam cells? (compare expanded_RMSE on retained-multibeam subset vs expanded_RMSE on singlebeam_gapfill subset, per product)
   - Is delta_RMSE concentrated in specific lat bands / depth bins / regions? (rank by |delta_RMSE| where the joined per-stratum metrics shift the most)
6. Recommendation: secondary/sensitivity-only OR regional-use OK (with the regions, if applicable)

## 4. Data Flow Contracts

- All Step 06B / Step 07B parquet files are read-only inputs.
- Strict-primary output directory `model_validation_1min_full_strict_primary/` is **read-only** during this task — the expanded run writes to a separate sibling directory `model_validation_1min_full_expanded_primary/`.
- No model residual is used to filter, drop, or re-label any validation cell. Model nodata cells are excluded from metric averages but their presence in the by-cell parquet is preserved (matching Stage 3 convention).

## 5. Rollback / Compatibility

- Stage 4 outputs live in `model_validation_1min_full_expanded_primary/`. Deleting this directory cleanly rolls back.
- The script change keeps `--validation-product` default = `strict_primary_multibeam_cells`, so any future run of `--stage full --confirm-full` without the new flag continues to drive the strict baseline.
- The new comparison script is additive; deleting it doesn't break the validation pipeline.
- If something is wrong, the report generation step is the last side-effect — earlier failures stop before writing the docs file, so a partial run is detectable.

## 6. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Refactor of `run_full` accidentally changes Stage 3 strict output names or values | Run a quick re-validation: after refactor, re-run Stage 3 strict over a tiny sample (or compare hashes of `--validation-product strict_primary_multibeam_cells` smoke output vs the existing one). Better: keep the strict run on the live disk untouched and only verify the new code path. Final guard: compare the new strict report against the existing one byte-for-byte after a no-op re-run; or simply verify that `--validation-product` defaults to strict and produces the same file names and metrics. |
| Coverage-gain script consumes too much memory loading 2.7M-row by-cell parquet for all 5 products | Load by-cell parquet one product at a time, or — for cell_id set membership — only read the `cell_id` column. Set membership: pyarrow `is_in` works fine at 2.7M rows. |
| Expanded run mis-counts `expanded_fill` because the column is missing | Step 07B preflight already confirms `expanded_fill` exists in `expanded_primary_ship_cells`. The safety check `expanded_fill_count_matches_preflight` is the gate; if the column is missing it would be -1 and trip FAIL. |
| `singlebeam_does_not_overwrite_multibeam` test logic mis-defined | Acceptance criterion definition: every `expanded_fill=True` cell_id must NOT appear in `strict_primary_multibeam_cells`. Symmetric check: |strict ∩ expanded| on cell_id must equal `len(strict) = 2,398,774`. |
| Stage 3 strict outputs accidentally mutated | The script's `--overwrite` requires the run-label `full_expanded_primary` (separate output dir). Stage 3 outputs are not touched. |

## 7. Out-of-Scope (for this design)

- Adding new sampling methods.
- Changing Step 06B/07B logic or files.
- SWOT_T1 footprint diagnostic.
- Supplementary singlebeam coverage / regional MRAR sensitivity.
- Promoting expanded_primary to primary baseline (this task only produces evidence for that future decision).
