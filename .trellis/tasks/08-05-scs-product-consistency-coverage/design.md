# Design: SCS mature-product consistency and coverage audit

## Boundary

This is a new bounded audit beside the completed lineage audit. It neither
modifies prior artifacts nor writes to the downstream GGM repository. The
driver reads only allowlisted columns from the frozen union and rejects paths
or schemas suggesting predictions, residuals, model errors, or metrics.

## Components

1. `ncei/configs/scs_product_consistency_coverage.yaml`
   freezes the domain, sampling rules, TID groups, distance thresholds, input
   paths, and expected input SHA256 values.
2. `ncei/code/audit_scs_product_consistency_coverage.py`
   validates inputs, builds the comparison and coverage products, and writes
   an immutable manifest/report.
3. `ncei/code/verify_scs_product_consistency_coverage.py`
   reads persisted artifacts and independently recomputes contractual checks.
4. `_common/tests/test_scs_product_consistency_coverage.py`
   exercises alignment, sign conversion, NMAD/consensus, spherical distance,
   area, TID grouping, and forbidden-column guards on synthetic fixtures.

The driver remains a bounded audit rather than a numbered production stage,
matching the existing SCS lineage-audit pattern.

## Data Flow

```text
frozen union (five allowlisted columns) ----+
cell_lineage.parquet -----------------------+--> 174,965-cell key closure
raw_to_cell_replay.parquet -----------------+              |
                                                            v
seven product NetCDFs --> aligned SCS subsets --> 1' product context
                                                            |
three GEBCO TIDs --> 4x4 category fractions ---------------+
                                                            v
                                      product_consistency_by_cell.parquet

frozen downstream GEBCO context --> exact land mask --> 1,288,723 ocean cells
174,965 cell centres --> spherical KD tree --> nearest-control distance grid
                                               |             |
                                               v             v
                                 coverage_grid_1min.nc   block/summary tables
```

## Coordinate and Sign Contract

- Domain is half-open `[105, 125) x [0, 25)` with target centres
  `west + (index + 0.5) / 60` and shape `(lat=1500, lon=1200)`.
- Target values use metres positive down.
- Source elevation products use metres positive up in the ocean and are
  converted with `depth = -elevation`.
- Aligned 15-arcsecond products must provide exactly 4x4 pixels per target
  cell. They are reshaped and reduced with `nanmedian` over the two fine-grid
  axes. Aligned 1-arcminute products must match target centres exactly.
- Nodata becomes NaN but the per-cell row remains present. Finite non-positive
  depths remain present as a diagnostic.

## Consensus Contract

For vector `x`:

```text
median(x) = nanmedian(x)
NMAD(x) = 1.4826 * nanmedian(abs(x - nanmedian(x)))
```

The seven-product consensus uses all seven product values. The family-balanced
consensus uses five components:

```text
median(GEBCO_2024, GEBCO_2025, GEBCO_2026),
ETOPO_2022, SRTM15_V2.7, TOPO_25.1, SDUST_2023
```

This reduces, but does not remove, dependence among products. Persisted
metadata states `reference_independence = not_established`. Differences use
`reference_depth - ship_depth`; positive means the reference is deeper.

No robust-z, 3STD decision, sample weight, or exclusion is generated.

## Coverage Contract

Each target cell area uses a spherical quadrilateral with frozen IUGG mean
Earth radius `6371.0088 km`:

```text
area = R^2 * delta_lon_rad *
       (sin(lat_north_rad) - sin(lat_south_rad))
```

Nearest-control distance is computed on unit-sphere XYZ coordinates with a
`scipy.spatial.cKDTree`. Chord distance `c` is converted to a great-circle
angle `2 * asin(c/2)` and then kilometres. Queries are chunked to bound memory.

The frozen downstream `land_mask` is the denominator and is never rebuilt from
newer products. GEBCO 2025/2026 land/TID differences are descriptive only.
One-degree blocks are exact 60x60 target-cell bins anchored at domain west and
south bounds.

## TID Contract

The config freezes disjoint code groups:

- land: `0`
- direct measurement: `10-17`
- gravity-guided/predicted: `40, 44, 45`
- other indirect/unknown: `41, 42, 43, 46, 47, 48, 70, 71, 72`

The driver records any observed unconfigured code and fails rather than
silently classifying it. Exact code counts are authoritative; grouped fractions
are descriptive. A 1-minute cell's group fraction is its matching fine-pixel
count divided by 16.

## Output Contracts

### `product_consistency_by_cell.parquet`

One row per `canonical_cell_id`, including geometry, source provider, ship
depth, seven product depths and differences, two consensus families and NMAD,
GEBCO TID fractions/classes, lineage class, and replay result/difference.
No row-level decision or weight column is allowed.

### `scs_product_context_1min.nc`

Coordinates plus seven full-domain product depth arrays, three generations of
TID group fractions, and frozen land mask. It is map-ready context, not a new
bathymetry estimate.

### `coverage_grid_1min.nc`

Frozen land mask, audited-cell occupancy, cell area, nearest-control distance,
and 1-degree control count. Distances are NaN on frozen land/mixed cells.

### Tabular/report outputs

- block coverage parquet;
- per-product and consensus metrics TSV, both overall and by provider;
- exact TID code/group composition TSV;
- coverage JSON, audit report, and manifest with hashes.

## Safety and Failure Behavior

- Full run requires `--confirm-audit`; `--estimate-only` performs path/schema
  and expected workload checks without creating a run directory.
- Existing run IDs are immutable and cause failure.
- Missing input, hash drift, coordinate mismatch, unexpected TID code, key
  mismatch, or count drift aborts before publishing a manifest.
- Outputs are written atomically inside a newly created run directory.
- The verifier is separate and recomputes rather than trusting report values.

## Performance

Only the SCS window is read from each global grid. At most roughly 28.8 million
15-arcsecond values are resident for one product at a time. Product arrays are
stored as float32 in NetCDF; calculations use float64. Distance queries are
chunked. Expected outputs are under a few hundred MB, with no global-chain
rerun.

## Rollback

The run is additive. Rollback consists of abandoning the new immutable run
directory and reverting task-owned code/config/spec changes. Existing lineage,
raw, gridded-product, and downstream files are never mutated.
