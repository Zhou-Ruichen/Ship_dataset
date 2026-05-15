# Model Validation Configuration Guide

Configuration file: `configs/gridded_products_validation.yaml`
Script: `code/08_validate_gridded_products_against_ship_cells.py`

---

## 1. Global Products

A global product covers the entire ocean. No `footprint` is needed.

```yaml
- name: GEBCO_2024
  path: /mnt/data2/00-Data/bathymetry/GEBCO/GEBCO_2024.nc
  format: netcdf
  lon_name: lon
  lat_name: lat
  z_name: elevation
  z_convention: elevation_negative_ocean
  resolution_hint: 15s
  sampling_method: cell_median
  lon_convention: -180_180
  enabled: true
```

Required fields:

| Field | Description |
|-------|-------------|
| `name` | Unique identifier used in output files and reports |
| `path` | Absolute path to the gridded product file |
| `format` | `netcdf`, `npz`, `geotiff`, or `grd` |
| `lon_name` | Variable name for longitude in the file |
| `lat_name` | Variable name for latitude in the file |
| `z_name` | Variable name for the depth/elevation values |
| `z_convention` | See section 3 |
| `sampling_method` | See section 4 |
| `lon_convention` | `-180_180` or `0_360` |
| `enabled` | `true` or `false` |

Optional fields:

| Field | Default | Description |
|-------|---------|-------------|
| `resolution_hint` | — | Human-readable resolution label (not used in computation) |

---

## 2. Local / Regional Products

A local product only covers part of the ocean. Add a `footprint` block.

```yaml
- name: MY_LOCAL_MODEL
  path: /path/to/my/model_output.npz
  format: npz
  lon_name: lons
  lat_name: lats
  z_name: prediction
  z_convention: elevation_negative_ocean
  sampling_method: center_bilinear
  lon_convention: -180_180
  enabled: true
  footprint:
    lon_min: -115.0
    lon_max: -105.0
    lat_min: -25.0
    lat_max: -15.0
```

When `footprint` is present:

- Ship validation cells outside the bounding box are excluded before sampling.
- `--sample-n-cells` draws from the filtered subset, not the global set.
- Output includes `region_subset_name` identifying the product footprint.
- `coverage_fraction` = valid cells / cells within footprint.

NPZ format specifics:

The script expects the NPZ file to contain 1D `lon_name` and `lat_name` arrays and a 2D `z_name` array of shape `(len(lat), len(lon))`.

---

## 3. z_convention

This tells the script how to interpret z values so that all products are converted to a common convention (elevation: negative in ocean, positive on land).

| Value | Meaning | Example products |
|-------|---------|-----------------|
| `elevation_negative_ocean` | z < 0 below sea level (no conversion needed) | GEBCO, ETOPO, SRTM15, SDUST, TOPO |
| `depth_positive_down` | z > 0 below sea level (script negates: model_elev = -z) | Some legacy products |

How to determine which convention your product uses:

1. Open the file and check z values in a known deep ocean location.
2. If the value is negative (e.g., -4000 at 4000m depth) → `elevation_negative_ocean`.
3. If the value is positive (e.g., +4000 at 4000m depth) → `depth_positive_down`.

The script reports a correlation check after sampling. If correlation between model and ship depths is negative, a sign error is flagged.

---

## 4. sampling_method

| Method | Description | Best for |
|--------|-------------|----------|
| `center_bilinear` | Bilinear interpolation at cell center lon/lat | Products at ~1min resolution (close to cell size) |
| `center_nearest` | Nearest grid point to cell center | Quick sanity checks |
| `cell_median` | Median of all product pixels within the 1min cell | High-resolution products (15s), robust to outliers |
| `cell_mean` | Mean of all product pixels within the 1min cell | High-resolution products, sensitive to outliers |

Fallback behavior:

For grids with >500 million pixels (e.g., SRTM15 at 15s global), `cell_median` and `cell_mean` fall back to `center_nearest` to avoid loading the entire grid into memory. The script records both the configured method (`config_sampling_method`) and the actual method used (`sampling_method`) in output.

When `cell_median` or `cell_mean` is configured, the script also runs a `center_bilinear_sensitivity` sample for comparison. These appear as separate rows in metrics output — they are never mixed into the main method's metrics.

---

## 5. Fair Comparison with --comparison-footprint

When comparing a local model against global products, you want all products evaluated against the same ship cells. Otherwise the local model gets 500 cells while GEBCO gets 2.4 million — the metrics are incomparable.

```bash
python3 code/08_validate_gridded_products_against_ship_cells.py \
  --config configs/gridded_products_validation.yaml \
  --comparison-footprint MY_LOCAL_MODEL \
  --overwrite
```

What this does:

1. Finds the product named `MY_LOCAL_MODEL` in the config.
2. Reads its `footprint` bounding box.
3. Filters ALL enabled products to only sample ship cells within that footprint.
4. Every product (global and local) is now evaluated against the same cells.

Requirements:

- The named product MUST have a `footprint` defined in the config.
- All products are still sampled independently — this only constrains which cells are used.

Example: validating a SWOT model in the South Pacific (R1: lon -115 to -105, lat -25 to -15):

```bash
python3 code/08_validate_gridded_products_against_ship_cells.py \
  --config configs/gridded_products_validation.yaml \
  --comparison-footprint SWOT_R1 \
  --overwrite
```

GEBCO, ETOPO, SRTM15, SDUST, and TOPO will all be evaluated only at ship cells within that 10°×10° box — directly comparable to SWOT_R1's metrics.

---

## CLI Reference

```
--config PATH                  YAML config file path
--validation-set {primary,sensitivity,both}
                               Which ship validation cells to use (default: primary)
--sample-n-cells N             Random sample N cells for testing
--product-name NAME            Only process this product
--comparison-footprint NAME    Restrict all products to this product's footprint
--overwrite                    Overwrite existing output files
--use-sensitivity-cells        (deprecated, use --validation-set both)
```

## Output Files

All output goes to `derived/model_validation_1min/`:

| File | Content |
|------|---------|
| `validation_by_cell_<product>.parquet` | Per-cell errors for each product |
| `validation_sample_diagnostics_<product>.parquet` | Convention checks and top-error cells |
| `validation_metrics_summary.parquet/.tsv` | Overall metrics per (product, validation_set, sampling_method) |
| `validation_metrics_by_quality_tier.parquet/.tsv` | Metrics stratified by ship data quality tier |
| `validation_metrics_by_depth_bin.parquet/.tsv` | Metrics stratified by ocean depth |
| `validation_metrics_by_region_10deg.parquet/.tsv` | Metrics stratified by 10°×10° regions |
| `model_validation_report.md` | Human-readable summary report |
