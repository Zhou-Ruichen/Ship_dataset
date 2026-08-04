# SCS mature-product consistency and coverage audit

## Goal

Produce a frozen, diagnostic-only comparison layer for the 174,965 audited
South China Sea ship cells and a full-domain description of where those cells
provide spatial support. The result is intended to inform downstream PINN
applicability-domain planning without changing label eligibility, existing
cohorts, splits, or evaluation rows.

## Confirmed Facts

- The audited label cohort is exactly 174,965 unique 1-arcminute cells:
  165,966 MRAR and 8,999 JAMSTEC.
- The frozen downstream analysis grid is pixel-registered at 1 arc-minute over
  `[105, 125) E x [0, 25) N`, with shape `(1500, 1200)`.
- The frozen GEBCO 2024 context contains 1,288,723 strict-ocean cells under
  `land_mask = land_fraction > 0`; all 174,965 audited cells are ocean cells.
- The upstream replay has 174,913 exact cells and 52 documented JAMSTEC
  aggregation differences caused by the weighted chunk-median mechanism.
- All seven requested products and GEBCO 2024/2025/2026 TID grids exist
  locally. No download is required.
- GEBCO versions, SRTM15+, ETOPO, TOPO, and SDUST are not seven independent
  sources. GEBCO versions are a family and GEBCO uses SRTM15+ as a base.

## Requirements

### R1. Frozen inputs and immutable execution

- Read only explicitly configured inputs and record absolute path, size, and
  SHA256 before analysis.
- Validate exact 1:1 key closure among the frozen union, `cell_lineage`, and
  `raw_to_cell_replay`.
- Write each full run to a new immutable run-ID directory. Refuse to overwrite
  an existing run and refuse full execution without an explicit confirmation
  flag.

### R2. Strict evidence boundary

- Do not read downstream predictions, residuals, errors, metrics,
  `external_samples.parquet`, or error-derived cohort columns such as
  `roles`/`outlier97`.
- Load only `canonical_cell_id`, longitude, latitude, representative ship
  depth, and source provider from the frozen downstream union.
- Product agreement is QC layer C: diagnostic only. It must not remove,
  relabel, reweight, or change eligibility for any cell.
- TID describes reference-product composition; it does not prove source
  independence.
- Coverage results inform applicability-domain planning only and must not
  modify existing cohorts or splits.

### R3. Seven-product cell comparison

Sample, without row loss, these products at every audited cell:

1. GEBCO 2024
2. GEBCO 2025
3. GEBCO 2026
4. ETOPO 2022
5. SRTM15+ V2.7
6. TOPO 25.1
7. SDUST 2023

Use positive-down metres internally. Aggregate aligned 15-arcsecond products
to 1 arc-minute with the median of the 4x4 source pixels. Read aligned
1-arcminute products at their exact pixel centres. Preserve finite non-positive
ocean values as diagnostics rather than silently masking them.

### R4. Consensus diagnostics

- Report a seven-product median and NMAD.
- Report a family-balanced median and NMAD where GEBCO 2024/2025/2026 first
  contribute one GEBCO-family median, followed by ETOPO, SRTM15+, TOPO, and
  SDUST as five diagnostic family components.
- Report product/family consensus minus ship depth, product spread, finite
  product counts, and per-product differences.
- Do not emit a PINN sample weight, exclusion decision, eligibility decision,
  or 3STD flag.
- Report absolute and centered descriptive metrics separately because ship
  vertical datums remain unknown.

### R5. Full-domain coverage

Using the frozen 1-arcminute strict-ocean mask, report:

- occupied ship-cell count and cell fraction;
- geodesic area-weighted occupied fraction;
- distance from every ocean cell to its nearest audited ship cell;
- cell- and area-weighted fractions within frozen radii
  `0, 5, 10, 25, 50, 100, 200 km`;
- P50/P90/P95/P99/maximum nearest-control distance;
- exact 1-degree block counts, fractions, areas, and distance summaries;
- observed-cell raw-point and source-provider summaries where available.

Do not report track spacing for MRAR because verified line/time identity is not
recoverable.

### R6. GEBCO TID composition

For GEBCO 2024, 2025, and 2026:

- aggregate the aligned 4x4 TID pixels for each 1-arcminute cell;
- retain exact per-code counts in a TSV;
- report direct-measurement fraction, gravity-guided/predicted fraction,
  other-indirect/unknown fraction, and land fraction;
- report full-domain ocean-cell counts for any, majority, and complete direct
  support and for any/majority gravity-guided support;
- preserve the exact TID code alongside grouped descriptions so that grouped
  terms cannot be mistaken for verified ship-source identity.

### R7. Replay registration

- Carry the replay result and signed replay difference into the per-cell
  diagnostic table.
- Assert 174,913 exact and 52 different cells at 1e-9 m.
- Label the 52 as documented aggregation-mechanism differences, not bad pings.

### R8. Deliverables and verification

Each immutable run must contain:

- `product_consistency_by_cell.parquet`
- `scs_product_context_1min.nc`
- `coverage_grid_1min.nc`
- `coverage_by_block_1deg.parquet`
- `product_metrics.tsv`
- `tid_composition.tsv`
- `coverage_summary.json`
- `audit_report.md`
- `audit_manifest.json`
- verifier-produced `verification.json`

An independent verifier must recompute hashes, row/key closure, product and
consensus arithmetic, replay closure, domain/ocean/occupied counts, coverage
fractions, distance zero at occupied cells, TID fraction closure, and the
absence of decision/weight columns.

## Acceptance Criteria

- [ ] Input hashes are recorded and independently rechecked.
- [ ] Exactly 174,965 per-cell rows are written; all seven product columns are
      present and no input cell is dropped for nodata or disagreement.
- [ ] Union, lineage, and replay key sets match exactly.
- [ ] The domain is exactly `(1500, 1200)` with 1,288,723 strict-ocean cells;
      all 174,965 audited cells are strict ocean.
- [ ] Area-weighted coverage and nearest-distance summaries independently
      recompute from `coverage_grid_1min.nc`.
- [ ] Seven-product and family-balanced consensus fields independently
      recompute from persisted product values.
- [ ] GEBCO 2024/2025/2026 TID code/group counts and fractions close exactly.
- [ ] Replay closure is 174,913 exact plus 52 documented aggregation
      differences.
- [ ] No prediction/residual/model-error input is accessed, and no output
      column filters, reweights, relabels, or changes cell eligibility.
- [ ] Unit tests, a full bounded run, the independent verifier, and
      `git diff --check` pass.

## Out of Scope

- Adjudicating the downstream 97 error-selected rows.
- Reading or reproducing `external_samples.parquet` or downstream model error.
- Defining PINN sample weights or a new train/development/test split.
- Using product disagreement to delete ship cells or cruises.
- Claiming GEBCO TID establishes independent validation.
- Producing or evaluating a downstream continuous GGM/PINN bathymetry grid.
- Recovering unavailable MRAR cruise, line, time, or vertical datum metadata.

## Open Questions

None blocking. The user requested task creation and implementation, supplied
the seven-product set, and confirmed the diagnostic-only discipline.
