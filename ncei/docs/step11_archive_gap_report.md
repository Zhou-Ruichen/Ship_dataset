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
