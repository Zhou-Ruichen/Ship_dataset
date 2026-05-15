# Quality Tiering

> The two-stage quality system: file-level flags (Step 06b) and cell-level
> tiers (Step 07). Both are load-bearing and used by every downstream
> consumer.

---

## Stage 1 — File-level flags (Step 06b)

Output: `jamstec/multibeam/manifests/file_quality_flags_1min.parquet`
Report: `jamstec/multibeam/docs/file_quality_flags_1min_report.md`

For each of the 5,083 multibeam files, exactly one flag is assigned:

| Flag | Count | Share | Meaning | Downstream effect |
|------|-----:|-----:|---------|---|
| `keep` | 4,734 | 93.1% | Normal, no systemic bias signal | Used in everything |
| `high_variance_review` | 199 | 3.9% | High between-cell variance, content plausible | Kept; flagged for inspection |
| `review` | 52 | 1.0% | Suspicious bias signal, not severe | Kept; flagged for inspection |
| `exclude` | 98 | 1.9% | Severe bias / wrong data | **Dropped** from validation cells |

`exclude` carries a manifest column `exclude_from_primary_cells = True`.
Step 06c reads this and skips those files when rebuilding the global
cells table.

### Excluded cruises (the population behind the 98 files)

| Cruise | Files | Why |
|---|---:|---|
| `KY09-09` | 13 | Systemic ~1000 m bias vs neighbouring cruises |
| `KY12-01` | 20 | Coordinate frame mismatch |
| `KY12-08` | 2 | Same as KY12-01 (small remnant) |
| `MR02-K06` | 63 | Time-tagged data with consistent depth offset |

**These are the only blanket-excluded cruises today.** Adding to the
exclude list requires:
1. Evidence in `derived/extreme_bias_investigation_1min/` (Step 06a output).
2. A documented entry in `docs/file_quality_flags_1min_report.md`.
3. Re-running Step 06c → 06d → 07 → 08.

---

## Stage 2 — Cell-level tiers (Step 07)

Output: `jamstec/multibeam/derived/validation_cells_1min/primary_ship_validation_cells_1min.parquet`

Each of the 2,394,115 cells gets exactly one tier. Evaluated **in order**
(first match wins):

| Tier | Conditions (all must hold) | Cells | Share | Validation weight |
|------|---|------:|------:|------:|
| **A_tier** | `n_cruises ≥ 2` AND `n_file_cells ≥ 2` AND `iqr_depth ≤ 50 m` AND `n_points ≥ 100` | 696,989 | 29.1% | **1.0** |
| **B_tier** | (not A) AND `n_points ≥ 50` AND `range_depth ≤ 500 m` | 1,362,178 | 56.9% | **0.7** |
| **C_tier** | everything else | 334,948 | 14.0% | **0.4** |

### Why these thresholds

| Threshold | Reason |
|---|---|
| `n_cruises ≥ 2` | Independent confirmation; one cruise's systematic bias would otherwise pass through |
| `n_file_cells ≥ 2` | At least two file-medians to take a between-file median over (the file-balanced median needs ≥ 2 inputs to be meaningful) |
| `iqr_depth ≤ 50 m` | At our cell size and depths (mostly 1–6 km), 50 m IQR is the natural break between "consistent" and "inconsistent" cells in the residual distribution (see Step 06a report) |
| `n_points ≥ 100` (A) / `≥ 50` (B) | Sample-size floor — below this, the per-file median is too noisy to weight equally with denser surveys |
| `range_depth ≤ 500 m` (B) | Catches cells where a wild outlier file blew up `iqr` but the bulk is fine; 500 m is far above genuine bathymetric variability within 1' but small enough to flag obvious data errors |

### Validation weights

The `validation_weight` column is consumed by Step 08 metrics and Step 10
residual dataset. **Don't average across tiers without weighting** — A and
C cells have very different reliability and the unweighted RMSE is
misleading.

```python
# correct
weighted_rmse = sqrt( ( (residual ** 2 * w).sum() ) / w.sum() )

# wrong — over-weights low-confidence cells
naive_rmse = sqrt( (residual ** 2).mean() )
```

The Step 08 report includes both per-tier metrics and a global weighted
metric for this reason.

---

## When to NOT use the tier system

- **Internal QC investigations** (Step 05, 06a). These need the full
  unfiltered `cells_1min/cells.parquet` to find the bias sources in the
  first place. Tiering is downstream of these stages.
- **Sensitivity analysis**. The companion file
  `sensitivity_original_ship_cells_1min.parquet` is unfiltered on purpose
  — used to quantify what tier filtering removed.
- **Visual mapping**. Maps may want to show C-tier coverage too, with
  visual de-emphasis (lower opacity, hatched fill) rather than removal.

---

## Changing the thresholds

If a numerical threshold changes:

1. Run Step 06a → 06b → 06c → 06d to regenerate the comparison report.
2. Run Step 07 with the new thresholds; record old/new tier counts.
3. Re-run Step 08 in T1-footprint mode (~5 minutes) and check whether the
   model RMSE shifts meaningfully.
4. Only then commit to a full Step 08 re-run.
5. Update this file with the new numbers.

The thresholds are calibrated to the 1' cell size. If `cell_deg` ever
changes, every threshold above must be re-derived from the new residual
distribution — they are not portable.
