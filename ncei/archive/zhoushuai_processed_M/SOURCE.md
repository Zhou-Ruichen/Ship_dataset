# SOURCE — `ncei/archive/zhoushuai_processed_M/`

> Frozen artifact: processed regional multibeam point cloud, source
> partially opaque. Lives under `archive/` to isolate it from the
> active NCEI pipeline (`tracklines_*` + `derived/`).

## Provenance

- **Provider**: 周帅 (2026-05-15 hand-off via `/mnt/data2/00-Data/tmp/`).
- **User assertion (2026-05-15)**: "M.rar is real NCEI multibeam data,
  but processed and regional." No README came with the file.
- **Source archive**: `M.rar` (379 MB compressed, 4.2 GB uncompressed,
  RAR4 format; `unrar` installed 2026-05-15). Relocated 2026-05-16
  from `tmp/` to this dir as part of PR-C, kept alongside the unpacked
  content as audit trail.

## Contents

Three quadrant-partitioned tab-separated `.txt` files (`lon\tlat\tdepth`,
no header, 6-decimal floats):

| File | Size | Rows |
|---|---:|---:|
| `0-180E-0-85N.txt` | 1.3 GB | 38,635,741 |
| `0-90W-0-85S.txt` | 887 MB | 25,295,079 |
| `90-180W-0-85S.txt` | 1.8 GB | 49,480,083 |
| **Total** | **4.0 GB** | **113,410,903** |

Plus the source `M.rar` (379 MB) kept in this dir.

Original archive wrapped everything under `M/`; PR-C flattens that
wrapper so the .txt files are immediate children of this dir.

## Geographic coverage — only 3 of 6 quadrants (~50% Earth)

Measured lon/lat ranges (2026-05-15):

| File | lon range | lat range | depth range |
|---|---|---|---|
| `0-180E-0-85N.txt` | [0.000, 180.003] | [0.000, 84.994] | [-15752, +2669] |
| `0-90W-0-85S.txt` | [-90.000, 0.001] | [-73.225, -0.001] | [-14951, +5451] |
| `90-180W-0-85S.txt` | [-180.000, -89.997] | [-78.676, -0.001] | [-30990, -5] |

**Missing quadrants**:
- **North hemisphere West** (Americas, North Pacific, North Atlantic,
  Arctic) — entirely absent. Notable since NCEI as a US institution
  would normally have densest coverage here.
- **South hemisphere East** (Indian Ocean, southwest Pacific south of
  equator) — also absent.

## Anomalies

1. **Positive depth values** up to `+5,451 m` and `+2,669 m` —
   Andes-scale land elevation, not bathymetry. Either a topo DEM is
   mixed in, or these are upstream sentinels.
2. **`-30,990 m` depth** in `90-180W-0-85S.txt` — far below Mariana
   Trench (~11 km). Sentinel / nodata code.
3. **Sampling**: irregular along-track steps (~0.0036° ≈ 13 arcsec)
   along lon=0 — not a regular grid (ETOPO/GEBCO ruled out),
   ~5× denser than `singlebeam.xyz` (~0.018° step). Consistent with
   decimated multibeam point cloud.

## Cleaning plan (PR-F)

Cleaning is **out of scope for PR-C** — this dir holds the raw
unprocessed extract. PR-F implements the cleaning step per PRD Q3:

- **`depth > 0`** → convert to **land mask** sidecar:
  `ncei/archive/zhoushuai_processed_M/land_mask.parquet` (exact filename
  and format finalized in PR-F implementation). Land points preserved
  as labeled artifact even if no current consumer.
- **`depth < −11,500 m`** → **nodata, drop entirely** (~5% past
  Challenger Deep ≈ −10,984 m). Clearly sentinels.
- **`−11,500 ≤ depth ≤ 0`** → bathymetry retained for downstream.
- Audit sidecar `ncei/archive/zhoushuai_processed_M/cleaning_audit.parquet`
  records rows-in / land-rows / nodata-rows / bathymetry-rows /
  per-quadrant counts. This SOURCE.md will be amended with the
  summary numbers when PR-F lands.

## Scale comparison

| Dataset | Points |
|---|---:|
| This (M.rar total) | 113,410,903 |
| `archive/sunmingzhi_singlebeam_xyz/singlebeam.xyz` | 114,507,390 |
| `jamstec/multibeam/` raw (5,140 files) | ~2,805,756,150 |

Row-count proximity to `singlebeam.xyz` (1% delta) is **coincidence** —
geographic coverage and sampling density rule out a same-data
hypothesis. M.rar's 113M points = **~4% of JAMSTEC multibeam raw**
total. Consistent with a heavily decimated regional subset.

## Known unknowns (recorded, not chased)

Per PRD Q8 — provenance is **not actively chased**:

1. The 4% point-count discrepancy vs full multibeam corpus.
2. Why the N-hemisphere-W quadrant (where NCEI is densest) is missing.
3. Why land elevation values are mixed in (DEM merge? sentinel?).
4. Whether "M" in the source filename is a known collaborator naming.

If downstream questions surface later, revisit then. Task does not
block on external response.

## References

- PRD: `.trellis/tasks/05-11-singlebeam-integration/prd.md` (Q3, Q8,
  Locked decisions #5, #6, #7).
- Investigation: `docs/experiments/2026-05_tmp-data-classification.md`
  (Finding 2 — full coverage / anomaly / density analysis).
