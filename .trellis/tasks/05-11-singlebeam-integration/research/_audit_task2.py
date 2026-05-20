"""
Step 04A aggregation design audit — Task 2 dry-run.

Reads Step 03A points_checked parquets, computes per-(track, cell) statistics
at 1 arc-minute resolution. Streamed/sampled to stay under ~5 min.

Output: ncei/derived/aggregation_design_audit/{branch_summary,cell_distribution_percentiles,depth_dispersion_percentiles}.tsv
"""
import time, os, glob, random, sys
import pyarrow.parquet as pq
import numpy as np
import pandas as pd

t0 = time.time()
random.seed(42)
np.random.seed(42)

CELL_SIZE_DEG = 1.0 / 60.0  # 1 arc-minute
# Triple precision: ~4 decimal degrees (~11 m at the equator) for lon/lat,
# 0.1 m for depth. Coarser than full float, finer than 1-arcmin cell.
LL_ROUND = 4
DP_ROUND = 1

def cell_bins(lon, lat):
    lon_bin = np.floor((lon + 180.0) / CELL_SIZE_DEG).astype(np.int64)
    lat_bin = np.floor((lat + 90.0) / CELL_SIZE_DEG).astype(np.int64)
    return lon_bin, lat_bin

def process_one_file(path, branch):
    """Per (track_id, cell): n_points_pass, n_unique_triples, depth_med, depth_iqr."""
    pf = pq.ParquetFile(path)
    cols = ['track_id', 'lon', 'lat', 'depth_m_positive_down', 'point_check_pass_basic']
    chunks = []
    for batch in pf.iter_batches(batch_size=500_000, columns=cols):
        df = batch.to_pandas()
        df = df[df['point_check_pass_basic'].fillna(False).astype(bool)]
        if df.empty:
            continue
        df = df.dropna(subset=['lon','lat','depth_m_positive_down'])
        if df.empty:
            continue
        lon_bin, lat_bin = cell_bins(df['lon'].values, df['lat'].values)
        df = df.assign(
            lon_bin=lon_bin,
            lat_bin=lat_bin,
            lon_r=np.round(df['lon'].values, LL_ROUND),
            lat_r=np.round(df['lat'].values, LL_ROUND),
            dep_r=np.round(df['depth_m_positive_down'].values, DP_ROUND),
        )
        chunks.append(df)
    if not chunks:
        return pd.DataFrame()
    df = pd.concat(chunks, ignore_index=True)
    # group keys
    grp_cols = ['track_id','lon_bin','lat_bin']
    n_pts = df.groupby(grp_cols, sort=False).size().rename('n_points_pass')
    n_uniq = (df.drop_duplicates(grp_cols + ['lon_r','lat_r','dep_r'])
                .groupby(grp_cols, sort=False).size().rename('n_unique_triples'))
    dep_med = df.groupby(grp_cols, sort=False)['depth_m_positive_down'].median().rename('depth_med')
    dep_q25 = df.groupby(grp_cols, sort=False)['depth_m_positive_down'].quantile(0.25).rename('depth_q25')
    dep_q75 = df.groupby(grp_cols, sort=False)['depth_m_positive_down'].quantile(0.75).rename('depth_q75')
    agg = pd.concat([n_pts, n_uniq, dep_med, dep_q25, dep_q75], axis=1).reset_index()
    agg['depth_iqr'] = agg['depth_q75'] - agg['depth_q25']
    agg['branch'] = branch
    return agg

def percentiles_of(arr, name, branch, sampled=False):
    v = np.asarray(arr, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return None
    return {
        'branch': branch,
        'metric': name,
        'sampled': sampled,
        'n': int(v.size),
        'mean': float(v.mean()),
        'p10': float(np.percentile(v,10)),
        'p25': float(np.percentile(v,25)),
        'p50': float(np.percentile(v,50)),
        'p75': float(np.percentile(v,75)),
        'p90': float(np.percentile(v,90)),
        'p99': float(np.percentile(v,99)),
        'max': float(v.max()),
    }

# ---- Branch A: singlebeam (5,365 files = 1,850 nc + 3,515 xyz) ----
sb_files = sorted(glob.glob('ncei/derived/singlebeam/points_checked/*.parquet'))
sb_nc = [f for f in sb_files if f.endswith('__nc.parquet')]
sb_xyz = [f for f in sb_files if f.endswith('__xyz.parquet')]
print(f'SB on disk: nc={len(sb_nc)}, xyz={len(sb_xyz)}', flush=True)
SAMPLE_SB = int(os.environ.get('SAMPLE_SB', '600'))
n_nc = min(SAMPLE_SB * len(sb_nc) // (len(sb_nc)+len(sb_xyz)), len(sb_nc))
n_xyz = SAMPLE_SB - n_nc
sb_sample = random.sample(sb_nc, n_nc) + random.sample(sb_xyz, n_xyz)
print(f'SB sampled: nc={n_nc}, xyz={n_xyz} -> total {len(sb_sample)}', flush=True)

sb_aggs = []
for i, p in enumerate(sb_sample):
    a = process_one_file(p, 'singlebeam')
    if not a.empty:
        sb_aggs.append(a)
    if (i+1) % 100 == 0:
        print(f'  SB {i+1}/{len(sb_sample)} files done, t={time.time()-t0:.1f}s', flush=True)
sb_cells = pd.concat(sb_aggs, ignore_index=True) if sb_aggs else pd.DataFrame()
print(f'SB sample produced {len(sb_cells):,} (track,cell) rows; t={time.time()-t0:.1f}s', flush=True)

# ---- Branch B: multibeam (17 files, all) ----
mb_files = sorted(glob.glob('ncei/derived/multibeam/points_checked/*.parquet'))
print(f'MB files: {len(mb_files)} (processing ALL)', flush=True)
mb_aggs = []
for p in mb_files:
    a = process_one_file(p, 'multibeam_ncei')
    if not a.empty:
        mb_aggs.append(a)
    print(f'  MB done: {os.path.basename(p)}, t={time.time()-t0:.1f}s', flush=True)
mb_cells = pd.concat(mb_aggs, ignore_index=True) if mb_aggs else pd.DataFrame()
print(f'MB produced {len(mb_cells):,} (track,cell) rows; t={time.time()-t0:.1f}s', flush=True)

# ---- Branch C: M.rar regional (113.3M rows). Sample at 4% (~4.5M). ----
mrar_path = 'ncei/derived/regional_mrar/points_checked/bathymetry_points.parquet'
print(f'MRAR: streaming with frac=0.04 sample, t={time.time()-t0:.1f}s', flush=True)
mrar_dfs = []
pf = pq.ParquetFile(mrar_path)
for bi, batch in enumerate(pf.iter_batches(batch_size=500_000,
        columns=['track_id','lon','lat','depth_m_positive_down','point_check_pass_basic'])):
    df = batch.to_pandas()
    df = df[df['point_check_pass_basic'].fillna(False).astype(bool)]
    df = df.dropna(subset=['lon','lat','depth_m_positive_down'])
    if df.empty:
        continue
    df = df.sample(frac=0.04, random_state=42 + bi)
    if df.empty: continue
    lon_bin, lat_bin = cell_bins(df['lon'].values, df['lat'].values)
    df = df.assign(
        lon_bin=lon_bin, lat_bin=lat_bin,
        lon_r=np.round(df['lon'].values, LL_ROUND),
        lat_r=np.round(df['lat'].values, LL_ROUND),
        dep_r=np.round(df['depth_m_positive_down'].values, DP_ROUND),
    )
    mrar_dfs.append(df)
    if (bi+1) % 20 == 0:
        print(f'  MRAR batch {bi+1}, accumulated {sum(len(x) for x in mrar_dfs):,} sampled rows, t={time.time()-t0:.1f}s', flush=True)

mrar_big = pd.concat(mrar_dfs, ignore_index=True) if mrar_dfs else pd.DataFrame()
print(f'MRAR sampled rows: {len(mrar_big):,}; t={time.time()-t0:.1f}s', flush=True)

# aggregate (track is a single track_id per the M.rar PR-F output: but per manifest there
# are 3 "quadrant" entries that share the same parquet. The parquet's actual `track_id`
# column distinguishes per-row by quadrant — let's check)
print(f'  M.rar distinct track_ids in sample: {mrar_big["track_id"].nunique()}', flush=True)
print(mrar_big['track_id'].value_counts().head(5).to_string(), flush=True)
grp_cols = ['track_id','lon_bin','lat_bin']
n_pts = mrar_big.groupby(grp_cols, sort=False).size().rename('n_points_pass')
n_uniq = (mrar_big.drop_duplicates(grp_cols + ['lon_r','lat_r','dep_r'])
            .groupby(grp_cols, sort=False).size().rename('n_unique_triples'))
dep_med = mrar_big.groupby(grp_cols, sort=False)['depth_m_positive_down'].median().rename('depth_med')
dep_q25 = mrar_big.groupby(grp_cols, sort=False)['depth_m_positive_down'].quantile(0.25).rename('depth_q25')
dep_q75 = mrar_big.groupby(grp_cols, sort=False)['depth_m_positive_down'].quantile(0.75).rename('depth_q75')
mrar_cells = pd.concat([n_pts, n_uniq, dep_med, dep_q25, dep_q75], axis=1).reset_index()
mrar_cells['depth_iqr'] = mrar_cells['depth_q75'] - mrar_cells['depth_q25']
mrar_cells['branch'] = 'regional_mrar'
print(f'MRAR (sampled): {len(mrar_cells):,} (track,cell) rows; t={time.time()-t0:.1f}s', flush=True)

# Merge all
all_cells = pd.concat([sb_cells, mb_cells, mrar_cells], ignore_index=True)
all_cells['dup_ratio'] = 1.0 - (all_cells['n_unique_triples'] / all_cells['n_points_pass']).clip(0, 1)

# Branch summary
sumrows = []
for branch, g in all_cells.groupby('branch'):
    sumrows.append({
        'branch': branch,
        'n_tracks_sampled': int(g['track_id'].nunique()),
        'n_track_cell_rows': int(len(g)),
        'n_unique_cells': int(g[['lon_bin','lat_bin']].drop_duplicates().shape[0]),
        'total_points_pass': int(g['n_points_pass'].sum()),
        'total_unique_triples': int(g['n_unique_triples'].sum()),
        'overall_dup_ratio': float(1.0 - g['n_unique_triples'].sum() / g['n_points_pass'].sum()),
    })
sumdf = pd.DataFrame(sumrows)
print(); print('=== BRANCH SUMMARY ==='); print(sumdf.to_string(index=False))

# Percentiles
pct_rows = []
for branch, g in all_cells.groupby('branch'):
    sampled_branch = (branch != 'multibeam_ncei')  # MB processed in full
    for metric in ['n_points_pass','n_unique_triples','dup_ratio','depth_iqr']:
        row = percentiles_of(g[metric].values, metric, branch, sampled=sampled_branch)
        if row: pct_rows.append(row)
pctdf = pd.DataFrame(pct_rows)
print(); print('=== PER-CELL PERCENTILES ==='); print(pctdf.to_string(index=False))

os.makedirs('ncei/derived/aggregation_design_audit', exist_ok=True)
sumdf.to_csv('ncei/derived/aggregation_design_audit/branch_summary.tsv', sep='\t', index=False)
pctdf.to_csv('ncei/derived/aggregation_design_audit/cell_distribution_percentiles.tsv', sep='\t', index=False)

# f-10-89-cp specific
target = 'f-10-89-cp'
fcells = all_cells[all_cells['track_id'] == target]
print(); print(f'=== f-10-89-cp cell stats ({len(fcells)} cells if sampled) ==='); print(fcells.to_string(index=False))
if not fcells.empty:
    fcells.to_csv('ncei/derived/aggregation_design_audit/f10_89_cp_cells_sample.tsv', sep='\t', index=False)

# Per-track point counts (audit suspicious tracks)
top_n_points = (all_cells.groupby(['branch','track_id'])['n_points_pass'].sum()
                .sort_values(ascending=False).head(30))
print(); print('=== Top 30 (branch, track) by total n_points_pass in sampled cells ==='); print(top_n_points.to_string())

print(); print(f'TOTAL ELAPSED: {time.time()-t0:.1f}s')
