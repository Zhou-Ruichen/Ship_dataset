# Resume a stopped round-2 download

Run from `/mnt/data2/00-Data/ship`. Once the user approves switching and the
old supervisor and its current worker have exited, reuse the Tier-B work
directory:

```bash
python -m ncei.download run \
  --catalog ncei/derived/mbbdb_value_ranking/order_tier_B_queue.tsv \
  --work /tmp/tierB_gapfill --tag tierB-gapfill \
  --workers 96 --inventory-workers 24 --attempts 6
```

`run` repeats inventory, diff, fetch, and merge until no files or failed
inventories remain. Failed probes are retried, including 41's null trees.
`--disk-floor-gb 400` is the default, measured in GiB as in the old supervisor.
It checks free space before each pass and every five seconds during curl
transfers. Partial files remain resumable. `--max-rounds N` bounds a run.

Defaults are `ncei/raw_round2/`, `ncei/manifests/round2_download_log.parquet`,
and the unmetered proxy `http://127.0.0.1:2085`. Override them with `--raw`,
`--log`, and `--proxies`. Additional proxies are opt-in.

## Run one stage

List the remote multibeam trees. `--refresh` refetches successful caches too:

```bash
python -m ncei.download inventory --work /tmp/tierB_gapfill \
  --catalog ncei/derived/mbbdb_value_ranking/order_tier_B_queue.tsv
```

Compare the cached `trees.json` with disk without network requests:

```bash
python -m ncei.download diff --work /tmp/tierB_gapfill
```

Fetch the resulting `todo.json`, resuming `.part` files:

```bash
python -m ncei.download fetch --work /tmp/tierB_gapfill --workers 32 --attempts 6
```

Merge `download-*.jsonl` into the parquet log, backing it up first and keeping
the last successful record for each `channel + source_url`:

```bash
python -m ncei.download merge --work /tmp/tierB_gapfill
```

Check gzip integrity and completeness for the cruises in `trees.json`:

```bash
python -m ncei.download verify --work /tmp/tierB_gapfill --workers 12
```

Verification writes `gzip_preflight.parquet`/`.tsv` and
`completeness_manifest.parquet`/`.tsv` under `<work>/verify/`.
`--out` changes that directory. These are task-scoped outputs; a Tier-B audit
does not replace a combined Tier-A/B processing manifest. Optional
`--extraction-dir ncei/derived/mb_round2` retains 41's
`previously_verified_by_extraction` shortcut. Omit it to run `gzip -t` on
every gzip in the listed cruises; `--gzip PATH` selects the executable.

`trees.json`, `platforms.json`, `sid2platform.json`, `lists/`, `todo.json`,
and the nine-column download log remain compatible with 41. New
`inventory_errors.json` records probe failures. `diff` keeps 41's rounded
listing-size tolerance; HTTP transfers require their exact advertised size.
Neither a zero queue with failed probes nor a legacy `tierA_complete:*`
record establishes completion. Commands return nonzero for failed inventories,
failed fetches, failed verification, a disk-floor stop, or an unfinished
bounded run.

Within `raw_round2/platforms_tree/`, both `<survey>/...` and
`<ship>/<survey>/...` are recognized. Existing locations are retained;
new cruises use 41's direct `<survey>/...` layout.

## Redownload a URL plan

R2R and static MGD77T use a copied parquet log, JSONL, JSON list, or TSV plan.
Each row needs `survey_id`, `source_url` (or `url`), and `sha256`; optional
`bytes` is an exact size. If present, `status` must be `ok`. Other rows and
channels are excluded.

```bash
python -m ncei.download fetch --channel r2r \
  --plan /tmp/download_check/r2r_plan.parquet \
  --raw /tmp/download_check/raw --work /tmp/download_check/r2r-work --workers 1
```

Use `--channel m77t_static` for the static channel. R2R writes
`r2r/<survey>.tar.gz`; static files write
`mgd77t_static/<survey>/<basename>`. Optional `rel` overrides the filename
(relative to `r2r/`, or to the static survey directory).
`diff` and `run` also accept these plans. Both channels require SHA256 and
check it before promoting a download. `fetch` alone does not merge the log.

Remote enumeration for these two channels is not implemented. The original
walkers are missing; SOURCE.md identifies their upstream sites and existing
URLs, not a complete fileset-discovery protocol. This tool recovers recorded
objects without guessing that protocol. Full remote inventory and
gzip/completeness `verify` are for `platforms_tree`.
