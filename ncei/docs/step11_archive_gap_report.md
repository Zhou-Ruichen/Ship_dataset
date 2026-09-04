# Step 11: NCEI archive gap inventory

Date: 2026-09-03

## Decision

The NCEI catalog contains 7,874 Survey IDs. Complete survey metadata was
obtained for 7,873 through the local proxy; the survey endpoint returns HTTP
500 for `U2019-032` even when it is requested alone. The known gap is 5,668
nc-side surveys and 706 bathymetry xyz surveys. The latter 706 are the surveys
for which no local bathymetry track exists.

No Part 2 download was started. Filling the 706 known bathymetry-track gaps in
MGD77T is estimated at 16,661,927,400 uncompressed bytes. XYZ output for the
same surveys is estimated at 3,329,184,900 bytes. Both estimates exclude
`U2019-032`, whose data types and size are unknown. Download remains
**pending user decision**.

A public AWS Registry of Open Data search on 2026-09-03 did not find a Marine
Trackline, MGD77, or MGD77T NODD entry. This is a negative search result, not
proof that no bucket exists.

## 1. Marine trackline gap

### Local holding

`trackline_source_manifest.parquet` has one row per source-side file. An nc
and xyz pair therefore contributes two rows. The inventory below separates
source rows from unique track IDs.

| Branch | Source rows | Unique track IDs | Local bytes |
| --- | ---: | ---: | ---: |
| nc | 2,018 | 2,018 | 1,112,811,427 |
| xyz | 5,382 | 5,382 | 3,330,098,922 |
| Combined, without double-counting paired IDs | 7,400 | 5,550 | 4,443,306,349 |

Of the 5,550 unique IDs, 1,850 have both branches, 168 are nc-only, and 3,532
are xyz-only. These are local holding counts, not NCEI catalog counts.

Year is taken from the nc CF `time` variable. A paired xyz row inherits the
year of its matching nc ID. An xyz-only file has no time field and remains
`unknown`; no year was inferred from its name.

| Branch | Era | Source rows | Unique track IDs | Local bytes |
| --- | --- | ---: | ---: | ---: |
| nc | 1960s | 331 | 331 | 70,573,143 |
| nc | 1970s | 743 | 743 | 306,035,224 |
| nc | 1980s | 482 | 482 | 319,668,799 |
| nc | 1990s | 306 | 306 | 236,210,646 |
| nc | 2000s | 152 | 152 | 154,328,286 |
| nc | 2010s | 4 | 4 | 25,995,329 |
| xyz | 1960s | 298 | 298 | 33,408,534 |
| xyz | 1970s | 680 | 680 | 158,258,130 |
| xyz | 1980s | 446 | 446 | 159,856,124 |
| xyz | 1990s | 284 | 284 | 146,707,405 |
| xyz | 2000s | 140 | 140 | 94,079,540 |
| xyz | 2010s | 2 | 2 | 19,379,580 |
| xyz | unknown | 3,532 | 3,532 | 2,718,805,609 |

Institution is unknown for all local rows. The manifest has no institution
column. `source_author=liyang` identifies the converter, not the surveying
institution. All 2,018 nc files have a nonblank `Source_Institution` global
attribute, but the values are corrupted numeric coordinate-like strings
(1,960 distinct values); they were rejected rather than relabelled as
institutions. The institution summary is therefore one `unknown` group:
7,400 source rows, 5,550 unique track IDs, and 4,443,306,349 local bytes.

### Catalog diff

All NCEI requests in this update used
`https_proxy=http://127.0.0.1:2081` and
`http_proxy=http://127.0.0.1:2081`. Requests were sequential. The operational
catalog paths were `/trackline/catalog/surveyid`,
`/trackline/catalog/survey`, and `/trackline/catalog/extents`; the shorter
paths printed in parts of the documentation returned HTTP 500.

Survey IDs were compared as case-insensitive complete strings. The 7,874
catalog IDs remain unique after case folding. This normalization is necessary:
only 795 xyz filenames match catalog capitalization exactly, whereas all 5,382
match case-insensitively. No punctuation or prefix was stripped.

| Branch | Catalog surveys with data for branch | Local matches | Known missing | Estimated missing bytes |
| --- | ---: | ---: | ---: | ---: |
| nc | 7,681 | 2,013 | 5,668 | 68,321,438,640 |
| xyz bathymetry | 6,087 | 5,381 | 706 | 3,329,184,900 |

Here, nc means the local nc-side holding. Its future source would be ordered
MGD77T and converted; NCEI does not directly deliver this repository's nc
files. The nc figure describes branch completion, not 5,668 wholly absent
bathymetry tracks. Of these records, many already have a local xyz source.

One local xyz record, `LSSALE53`, is present even though the current catalog
reports zero bathymetry points for that Survey ID. Five local nc survey IDs do
not appear in the current catalog: `F-10-89-C`, `F-11-89-C`, `ME20-19920`,
`S-2-90-CP0`, and `S-3-90-CP0`. They are retained as
`local_only_not_in_current_catalog`, not counted as missing remote surveys.

Known missing surveys by start-year decade:

| Era | nc surveys | nc bytes | xyz bathymetry surveys | xyz bytes |
| --- | ---: | ---: | ---: | ---: |
| 1930s | 4 | 300,120 | 0 | 0 |
| 1950s | 84 | 101,974,680 | 14 | 499,710 |
| 1960s | 571 | 372,960,720 | 0 | 0 |
| 1970s | 1,053 | 1,189,844,400 | 11 | 1,492,920 |
| 1980s | 1,043 | 1,649,650,080 | 2 | 2,464,410 |
| 1990s | 928 | 2,689,657,680 | 36 | 25,378,830 |
| 2000s | 378 | 5,920,794,240 | 98 | 164,387,880 |
| 2010s | 1,394 | 51,415,324,200 | 503 | 2,990,591,550 |
| 2020s | 213 | 4,980,932,520 | 42 | 144,369,600 |

The 706 bathymetry-track gaps fall into ten catalog institution groups:

| Institution | Surveys | Estimated XYZ bytes |
| --- | ---: | ---: |
| unknown | 336 | 1,326,554,760 |
| R2R | 243 | 1,864,787,370 |
| Lamont-Doherty Earth Obs | 84 | 84,360,450 |
| Scripps Inst Oceanograph | 18 | 1,240,680 |
| US Navy Naval Oceanog | 10 | 1,477,920 |
| Spanish IHM and UTM-CSIC | 10 | 12,065,490 |
| USGS | 2 | 2,385,210 |
| Canada Geological Survey | 1 | 15,000 |
| Japan Hydrographic Dept | 1 | 249,900 |
| New Hampshire, U of | 1 | 36,048,120 |

For nc branch completion, the largest known institution groups are:

| Institution | Surveys | Estimated MGD77T bytes |
| --- | ---: | ---: |
| unknown | 904 | 32,168,971,800 |
| Scripps Inst Oceanograph | 734 | 4,650,531,600 |
| R2R | 546 | 17,376,480,960 |
| NOAA National Ocean Serv | 331 | 251,919,960 |
| UK Hydrographic Office | 327 | 236,358,600 |
| Lamont-Doherty Earth Obs | 308 | 953,374,560 |
| Woods Hole Oceanog Inst | 162 | 790,125,360 |
| ODP/Texas A and M | 131 | 568,959,240 |
| US Navy Naval Oceanog | 127 | 285,065,400 |
| USGS Pacific Marine Geol | 116 | 159,734,400 |
| Remaining 132 institution groups | 1,982 | 10,879,916,760 |

The catalog `pointSize` field supplies the nc/MGD77T estimates. NCEI describes
it as uncompressed output size. The XYZ estimate uses 30 bytes per bathymetry
point, the exact ratio returned by the global XYZ extents query:
279,605,074 points and 8,388,152,220 bytes. The catalog-wide bathymetry extents
query estimates MGD77T at 33,552,608,880 bytes and XYZ at 8,388,152,220 bytes.
These are generated-output estimates, not compressed delivery archive sizes.

For the 706 surveys absent from both local branches, MGD77T is the preferred
Part 2 format and totals 16,661,927,400 known bytes. XYZ is the 3,329,184,900
byte fallback. Completing every known nc-side gap would be 68,321,438,640
bytes, above the task's 50 GB stop threshold.

`ncei_catalog_gap_2026-09.parquet` now contains 15,753 rows: two branch rows for
each catalog Survey ID plus five local-only nc rows. It retains catalog and
local identifiers, data availability, institution, platform, years, point
counts, branch status, estimate method, and retrieval time. Both branch rows
for `U2019-032` use `catalog_metadata_error`; its availability,
`missing_from_local`, institution, era, and size remain null/unknown.

Sources: [NCEI catalog API documentation](https://www.ngdc.noaa.gov/next-web/docs/guide/catalog.html),
[NCEI ordering API documentation](https://www.ngdc.noaa.gov/next-web/docs/guide/ordering.html),
[AWS NOAA open-data registry](https://registry.opendata.aws/collab/noaa/), and
[NODD data documentation](https://github.com/NOAA-Big-Data-Program/nodd-data-docs).

## 2. Multibeam assessment

### NCEI MBBDB

The task record describes MBBDB as holding more than 2,400 cruises. The earlier
Part 3 attempt occurred before the proxy became available and did not obtain a
current cruise inventory or file-size sum. This proxy update was restricted to
Part 1 trackline enumeration, so the current MBBDB cruise count, downloadable
formats, and completion size remain **unknown**. No MBBDB data were downloaded.

### NOAA OCS National Bathymetry S3

The reachable bucket
`https://noaa-ocs-nationalbathymetry-pds.s3.amazonaws.com/` was fully
enumerated with S3 ListObjectsV2: 61 pages ended with `IsTruncated=false`.
It contains 60,632 objects and 273,067,509,843 bytes (273.07 GB, decimal).

| Prefix/product | Data units | Objects | Bytes | Main formats |
| --- | ---: | ---: | ---: | --- |
| `BlueTopo/` | 8,203 tiles | 16,407 | 89,349,425,502 | 8,203 TIFF, 8,203 XML, 1 GPKG |
| `Test-and-Evaluation/Modeling/` | 11,656 tiles | 23,313 | 109,130,525,208 | 11,656 TIFF, 11,656 XML, 1 GPKG |
| Navigation test BAG | 4,910 BAG files | 4,911 | included in bucket total | BAG, PDF |
| Navigation test S102 v2.1 | 4,906 HDF5 files | 4,915 | included in bucket total | HDF5, ZIP, XML, PDF |
| Navigation test S102 v2.2 | 4,910 HDF5 files | 4,913 | included in bucket total | HDF5, XML, PDF |
| Navigation test S102 v3.0 | 4,910 HDF5 files | 4,913 | included in bucket total | HDF5, XML, PDF |

The bucket is a gridded national-bathymetry and navigation-product store, not
a confirmed mirror of the MBBDB cruise archive. Its tile/file identifiers do
not share the local trackline manifest's Survey ID contract. It therefore adds
a separately usable bathymetry product source, but the number or area of
multibeam cruises it adds relative to the 5,550 local track IDs is unknown.
No crosswalk or coverage percentage was manufactured from incompatible IDs.

Source: [bucket root and ListObjectsV2 endpoint](https://noaa-ocs-nationalbathymetry-pds.s3.amazonaws.com/).

## 3. IHO DCDB crowdsourced bathymetry assessment

The pointstore count endpoint was observed at 2026-09-02T21:11:55Z UTC:

```text
GET https://q81rej0j12.execute-api.us-east-1.amazonaws.com/count
HTTP 200
{"count": "2339461220"}
```

This is an API observation of **2,339,461,220 soundings**. It is not derivable
from the S3 ListObjects enumeration. That enumeration timed out after about
128,000 objects while `IsTruncated=true`, and produced no cumulative byte sum.
Exact S3-side object, byte, and sounding totals remain **unknown**.

The observed S3 layout is `csb/csv/YYYY/MM/DD/*.csv`, with years 2017 through
2026 present in the enumerated prefix. One boundary sample was inspected:

```text
key: csb/csv/2017/04/25/20170425114516079166_bb9ee63f-e96c-4a65-937d-893118602cd9_pointData.csv
HEAD: HTTP 200; Content-Length 1250; Last-Modified 2023-08-31T18:55:03Z
GET Range bytes=0-999: HTTP 206
header: UNIQUE_ID,FILE_UUID,LON,LAT,DEPTH,TIME,PLATFORM_NAME,PROVIDER
sample: ROSEP-... / LAPEROUSE / Rosepoint
```

The sample confirms sounding coordinates and depth plus time, platform,
provider, file ID, and unique point ID. In the public payload schema, the
closest descriptive fields are `response_format`, `file_uuid`, `unique_id`,
`archive_date`, `collection_date`, `platforms`, and `providers`. Dates are
collection/archive filters, not quality metadata. There are **no per-track
quality fields in the public schema**: no uncertainty, accuracy, QC, or quality
field is exposed. This says nothing about whether contributors retain quality
information outside the public schema.

No CSB points were bulk-downloaded. Sources: [pointstore API](https://raw.githubusercontent.com/CI-CMG/pointstore-api-docs/main/pointstore_api.md),
[S3 archive layout](https://raw.githubusercontent.com/CI-CMG/pointstore-api-docs/main/csb_readme.html),
and [public payload schema](https://raw.githubusercontent.com/CI-CMG/pointstore-api-docs/main/pointstore_payload_schema.json).

## Files produced and stop state

- `ncei/manifests/ncei_catalog_gap_2026-09.parquet`: complete catalog/local
  branch diff, with one explicit catalog metadata error.
- `ncei/docs/step11_archive_gap_report.md`: this report.
- No raw files, download log, derived products, or pipeline outputs were
  created or changed.
- Part 2 remains stopped pending explicit user confirmation. No order was
  submitted and no trackline data were downloaded.

## Round-2 download

NCEI ordering documentation exposes only `POST /next-web/rest/orders` for
trackline MGD77T/XYZ delivery. It requires an email address and creates an
asynchronous order. No order was placed. No direct NCEI XYZ file was found.

The first R2R pass fetched 169 processed `r2rbathy_geocsv` archives, covering
169 surveys and 782,617,282 bytes. Three 302/Globus retries through 2080 still
failed; `TN313` and `TN314` had already succeeded. The R2R dead-end survey list
(no successful processed product) is:

`EW0006, EW0008, EW0101, EW0106, EW0107, EW0108, EW0109, EW0110, EW0201, EW0202, EW0203, EW0204, EW0205, EW0206, EW0207, EW0208, EW0209, EW0210, EW0211, EW0212, EW0213, EW0301, EW0302, EW0303, EW0304, EW0305, EW0306, EW0307, EW0308, EW0310, EW0401, EW0402, EW0403, EW0404, EW0405, EW0406, EW0407, EW0408, EW0409, EW0410, EW0412, EW0501, EW9302, EW9303, EW9304, EW9401, EW9402, EW9404, EW9408, EW9411, EW9502, EW9504, EW9505, EW9506, EW9507, EW9508, EW9603, EW9609, EW9701A, EW9703, EW9706, EW9708, EW9802, EW9804, EW9805, EW9807, EW9808, EW9902, EW9907, EW9912, HLY17TA, SP1220, SP1221`.

Platform-tree downloading was stopped after the 2085 worker completed the
current file and left subsequent `.part` files intact. Before that stop,
platform data contained 3,179 files from 24 surveys and 149,051,800,841 bytes.
The five retained incomplete files are:

`HLY1401/em122/0090_20140515_212210_HEALY.all.mb58.gz.part`,
`HLY1402/em122/0076_20140707_084546_HEALY.all.mb58.gz.part`,
`AR30-04/em122/0429_20180727_070024_Armstrong.all.mb58.gz.part`,
`AR42-02/em122/0016_20200226_181820_Armstrong.all.mb58.gz.part`, and
`HLY20TB/em122/0211_20200710_155449_Healy.all.mb58.gz.part`.

A directory-only platform scan used 2085 with a 2-second request interval and
did not download files. It found these archives that were not fully fetched:

| Survey | Files listed | Files downloaded |
| --- | ---: | ---: |
| AR30-04 | 542 | 452 |
| AR45 | 42 | 24 |
| AR66-A | 74 | 44 |

The scan stopped at `AR66-B` when 2085 could not establish a new connection.
No other port was tried. Earlier confirmed 404 roots remain skipped. The
directory archive inventory and all source URLs are retained in
`ncei/manifests/round2_download_log.parquet`; status values beginning with
`catalog_only_files:` identify the directory-only records.

The previous port-disabled `curl_0` file list is recorded in the same log.
Grouped by survey, it contains: `AR30-01 (157), AR30-04 (481), AR41 (1),
AR45 (36), AR66-A (60), AR66-B (53), FK006B (2), HLY1102 (1144), HLY1401 (4),
HLY1402 (4), HLY1403 (1468), HLY20TB (2)`. These are skipped file URLs, not
additional survey classifications.

Final Round-2 totals are 3,348 successful files, 193 surveys, and
149,834,418,123 bytes: `r2r=169` files and `platforms_tree=3,179` files;
`ncei_xyz=0`. The log is resumable and now includes `worker` and `port`
columns. Surveys after the `AR66-B` 2085 failure remain unclassified for
platform-tree availability and are not labelled email-only without another
authorized NCEI route. No order was submitted.

## Round-2 follow-up pointer (2026-09, step15/16)

This section's totals are the 2026-09-03 snapshot. Later follow-ups, all
readable from disk:

- Completeness audit of the 24 platform-tree cruises, processing of the
  complete ones (10 × mb58, 2 × mb21; mb57 blocked by a parser crash in
  the fixed mbsystem build), and the strict-layer coverage delta:
  `ncei/docs/step15_mb_round2_processing.md`.
- Download-value ranking and A/B/C order lists for the remaining MBBDB
  increment: `ncei/docs/step16_mbbdb_value_ranking.md`.
- Static-tree MGD77T backfill (`ncei/raw_round2/mgd77t_static/`), the
  10-cruise platform-tree completion, and the corrupted-gzip re-downloads
  are running in an agent queue (as of this writing 369 survey directories
  holding 362 `.m77t` files, 8.0 GB on disk); the totals in the
  "Round-2 download" section above will be superseded when that queue
  finishes and the download log is re-aggregated.

### Static MGD77T tree — dead-end list (2026-09, task E)

The `m77t_static` channel has 44 non-ok log rows, resolving to 15 surveys:

- **No static m77t at all (11 surveys; 404 + parent-directory scan found
  nothing, or plain 404 for both files)** — these remain true gaps:
  `0C96, AE1028, AE1115, B270BS, HRS1713, KN210-05` (no_static_m77t) and
  `OC456, SKQ201910S, SKQ201911T, SKQ201913T, WS0914` (http_404).
- **Side-file-only misses (4 single curl_0 rows; the m77t data itself is on
  disk)**: `EW9703` (.h77t), `NBP0808` (.h77t), `OC1404B` (.h77t),
  `OC1405B` (one .m77t retry; an earlier copy succeeded).

Net: 695 of the 706 gap surveys have a downloaded `.m77t` (98.4%);
11 are dead ends pending another route (email order or R2R).

Additionally, 3 of the 695 downloaded `.m77t` files carry navigation-only
short-form rows (≤6 tab fields, no depth columns) and converted to empty
xyz; they are recorded as no-bathymetry sources, not pipeline failures:
`ALAR02RR, DNWH-BHO, DNWH-CHO`. Effective static-tree yield: 692 tracks
with bathymetry-side xyz out of 706 gap surveys.
