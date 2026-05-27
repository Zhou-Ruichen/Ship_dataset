# Step 08 — Publication Pack (bootstrap, cross-check, output layout)

> Cross-stage spec captured from the Step 08 followup pack task tree
> (parent `05-28-step08-ranking-uncertainty-and-pub`, children A/B/C/D).
> Documents the statistical and integration conventions that any future
> Step 08 followup or rerun must preserve.

---

## Rule 1 — Paired cluster block bootstrap by `region_10deg`

When quantifying ranking uncertainty over a strict-primary global by-cell residual product, use **paired cluster bootstrap** with `region_10deg` as the resampling unit.

- **Cluster definition** — the `region_10deg` column of the by-cell parquet (e.g. `lon0080_lat-060`), 124 unique values in the current strict-primary product.
- **Paired construction** — inner-join the per-model by-cell parquets on `cell_id` (must yield N = 2,398,774 with no NaN); each iteration samples the same set of cells across all models.
- **Iteration** — sample 124 cluster ids with replacement; concatenate the cells from sampled clusters; compute RMSE / MAE / weighted RMSE per model and pairwise ΔRMSE on the concatenation.
- **Defaults** — B = 1000, seed = 20260528, percentile 95% CI ([2.5, 97.5]).
- **Forbidden alternatives** — i.i.d. cell-level bootstrap (underestimates ΔRMSE variance because 1-min cells are spatially autocorrelated); per-model unpaired bootstrap (cannot give paired ΔRMSE CI).

A safety-check artifact (`a_ranking_safety_checks.tsv`) must include:

- `paired_n_cells` (= 2,398,774)
- `no_nan_residuals`
- `n_clusters` (= 124)
- `ci_covers_point` for every (model, metric) combination
- `reproducible_seed`

## Rule 2 — Cross-task numerical cross-check

When a Step 08 followup task is split into A (uncertainty), B (point-estimate tables), C (subset attribution), and D (figures), a parent integration script must assert numerical consistency before publishing:

| Check id pattern | Invariant |
|---|---|
| `A_B_strict_<METRIC>_match` | `A.point_estimate == B.<metric>` within 0.01 m |
| `A_CI_covers_B_strict_<METRIC>` | `A.p2.5 ≤ B.<metric> ≤ A.p97.5` |
| `B_C_gapfill_RMSE_match` | `B.gapfill_singlebeam_RMSE == C.RMSE_gapfill` within 0.01 m |
| `B_Stage4_strict_RMSE_match` | `B.strict_RMSE == Stage4.strict_vs_expanded_comparison.strict_RMSE` within 0.01 m |
| `B_Stage4_delta_RMSE_match` | `B.delta_RMSE == Stage4.delta_RMSE_expanded_minus_strict` within 0.01 m |

The parent script must fail (exit non-zero) on any FAIL row before writing the public summary markdown.

## Rule 3 — Output layout for publication pack

A publication pack lands under `ncei/derived/model_validation_1min_step08_pub/` and SHOULD split by sub-task:

```
ncei/derived/model_validation_1min_step08_pub/
├── a_ranking_uncertainty/       # bootstrap iters parquet, CI tables, safety
├── b_pub_tables/                # publication TSV + CSV, safety
├── c_<subset>_structure/        # subset slice TSVs, attribution, safety
├── d_figures/                   # figure-ready TSV + PNG + PDF, safety
└── summary/                     # parent cross-check, manifest, metadata
```

Every sub-task directory must contain its own `*_safety_checks.tsv`. The
parent `summary/` directory must contain `step08_pub_cross_check.tsv` and
`step08_pub_manifest.tsv` (full SHA256 + size of every artifact).

## Rule 4 — Forbidden operations under the publication pack

The publication pack must not:

1. Modify any Step 06B quality flag or Step 07B validation product.
2. Re-run gridded model sampling.
3. Use model residuals to filter, drop, or relabel cells (the existing
   [no-residual-filtering](./step08_no_residual_filtering.md) invariant
   continues to apply transitively to bootstrap and attribution scripts).
4. Promote `expanded_primary_ship_cells` to the global ranking baseline.
   It remains a sensitivity / coverage-expansion product only.

## Rule 5 — Publication-ready figure conventions

When publishing figures over the 5 strict-primary global models, the
model → color mapping is fixed for visual consistency across figures:

| model | matplotlib color |
|---|---|
| GEBCO_2024 | tab:blue |
| ETOPO_2022 | tab:orange |
| SRTM15_V2.7 | tab:green |
| TOPO_25.1 | tab:red |
| SDUST_2023 | tab:purple |

Models are ordered by ascending strict-primary RMSE in all figures and
publication tables (GEBCO best, SDUST worst). PNG outputs use 300 DPI,
PDF outputs are vector. Each figure also writes a `figure_data_F<N>.tsv`
so the underlying numbers can be audited independently of the image.

## Why

This spec consolidates the statistical and integration conventions that
make a Step 08 publication pack reproducible and auditable. Any future
rerun (new model added, regional product done in a separate task, BCa
CI introduced) should keep this skeleton so that ranking conclusions
and figures remain comparable across runs.

## Reference task

- Parent: `.trellis/tasks/archive/.../05-28-step08-ranking-uncertainty-and-pub/`
- Sub-tasks: `05-28-step08-a-ranking-uncertainty`, `05-28-step08-b-pub-tables`, `05-28-step08-c-gapfill-error-structure`, `05-28-step08-d-pub-figures`
- Parent summary: `ncei/docs/publication_ready_step08_summary.md`
- Stage 4 anchor: `ncei/derived/model_validation_1min_full_expanded_primary/strict_vs_expanded_comparison.parquet`
