# SOURCE — `ncei/`

> NCEI singlebeam track corpus plus frozen archive sub-corpora.
> Symmetric to `jamstec/SOURCE.md`. The active pipeline (planned PR-D
> through PR-E of task `05-11-singlebeam-integration`) consumes the
> two `tracklines_*/` sub-corpora; `archive/` holds frozen artifacts.

## Provenance — content origin

The active `tracklines_*/` sub-corpora are sourced from the **NCEI
public singlebeam track archive** (NGDC trackline IDs in the
filenames). Per-track structure is preserved in both `tracklines_nc/`
(MGD77+ NetCDF) and `tracklines_xyz/` (3-column flat). Two flat /
processed legacy artifacts also live under `archive/`.

Historical naming note: this tree lived at `ship/NCEI_singlebeam/`
until 2026-05-16, when task `05-11-singlebeam-integration` (PR-B)
executed the rename to `ship/ncei/`. PR-C (2026-05-16) populated the
internal layout below.

## Provenance — transfer chains

Four distinct transferers, four distinct artifacts. Two of the four
were finalized 2026-05-16 with fingerprint / NetCDF-attribute
evidence; the other two were already confirmed at PR-C ingest time.

| Sub-path | Content origin / conversion | Transfer chain | Date |
|---|---|---|---|
| `tracklines_nc/` (2,018 `.nc`) | NCEI MGD77 ASCII → **李杨 MGD77+ NetCDF conversion** (2024-07-31, evidenced by `Author: liyang` + conversion-history line in 5/5 spot-checked files) | **李杨 (conversion) → 孙明智 (forwarding) → user** (user-confirmed 2026-05-16) | Dec 2024 (file mtime of source zip) |
| `tracklines_xyz/` (5,382 `.xyz`) | NCEI tracklines `.xyz` raw bundle (mb-mixed) | **安德超 → user** | 2026-05-15 |
| `archive/sunmingzhi_singlebeam_xyz/singlebeam.xyz` | Flat merge of an earlier NCEI `.xyz` snapshot (114.5M rows; lossy — per-track structure dropped) | **孙明智 → user** (provider / own-work; distinct from his forwarder role for the `.nc` archive) | Jan 18 2025 (file mtime) |
| `archive/zhoushuai_processed_M/M.rar` | NCEI multibeam, processed regional (anomalies: positive depths + −30,990 m sentinel; ~4% of NCEI mb raw point total) | **周帅 → user** | 2026-05-15 |
| `archive/source_zips/` | Audit trail: 2 raw zips (the `.nc` source + the `.xyz` bundle) | — (derived staging) | 2026-05-16 (PR-C) |

### Finalized 2026-05-16 (李杨 / 孙明智 sharpening)

The two key sharpenings relative to PR-C's initial framing:

1. **`tracklines_nc/` is 李杨's local NetCDF conversion**, not a
   download of NCEI's official NetCDF distribution. All 2,018 `.nc`
   files carry `Author: liyang` + a `[liyang] Conversion from MGD77
   ASCII to MGD77+ netCDF format` history line dated 2024-07-31
   (5/5 spot-checked). Content value matches NCEI MGD77 source data
   (verified in the codex investigation `~/.codex/ncei_singlebeam_README.md`)
   — the conclusion "this is NCEI data" stands — but the file format
   is 李杨's conversion artifact.
2. **孙明智's role splits into two distinct artifacts**:
   - (a) **Forwarder** for 李杨's `.nc` archive (transfer to user
     late 2024).
   - (b) **Provider / own-work** for the flat `singlebeam.xyz` merge
     dump (transfer to user Jan 2025). Origin of the flatten/merge
     step is undocumented — possibly 孙明智's own work, possibly an
     upstream snapshot he obtained pre-merged.

These supersede the earlier PR-C-time framing that named 孙明智 as
the primary source-side counterparty for the `.nc` archive.

## 168 nc-only tracks resolved (2026-05-19)

The "168 nc tracks absent from the xyz bundle" known unknown (PRD Q7,
Locked decision #8) was resolved 2026-05-19 from the full PR-E1
trackline source manifest: all 168 are FAA / gravity-only tracks
with **no usable depth values** (`has_depth=False`). NCEI's upstream
`.xyz` export pipeline filter rule is "track has usable depth"; the
168 were correctly excluded by that rule. Union strategy unchanged
(they stay in the manifest with `source_completeness="nc_only"`);
PR-E2 will skip them at the bathymetry-standardization step but
the rows remain as audit trail and as candidates for gravity-side
consumers.

Full evidence (cross-tab + 5/5 sample verification) lives in PRD
section "Finding 2026-05-19: 168 nc-only tracks have no usable
depth"; `tracklines_nc/SOURCE.md` carries the historical-record
annotation.

## Depth sentinel pollution (2026-05-19b, PR-F clip)

16 distinct tracks across nc + xyz carry `depth_max` values past
Mariana Trench (~10,994 m) — sentinel / unit-error pollution from
upstream, not real bathymetry. 3 nc-sb tracks (`91039`, `so16`,
`so49`); 13 xyz tracks led by `ant4` (87,178 m), `wi343802`
(75,000 m), `ant8` (52,002 m), `so36` (44,215 m). PR-F adds a
universal upper clip in `02_standardize_singlebeam.py` and
`03_standardize_xyz.py`: `depth_m_positive_down > 11,500 m → NaN`
(symmetric with PRD Q3 M.rar lower-bound). `depth_raw` preserved
verbatim in per-track parquet for audit. Full per-track table and
policy rationale in PRD section "Finding 2026-05-19b" +
`tracklines_xyz/SOURCE.md` "Depth sentinel" subsection.

## nc/xyz intersect asymmetry (2026-05-19c, refines 2026-05-16)

For the 1,850 `nc_xyz_intersect` tracks, the nc side carries more
points than the xyz side (median ratio 1.37×; 39 tracks with nc
≥10× xyz; 3 tracks with nc ≥100× xyz — peak 189× at `kea09-69`).
The "14k pts/track" parity claim from the 2026-05-16 corpora-
relationship finding holds at the **aggregate** level (xyz adds mb
swaths + 3,532 nc-absent tracks that net out the per-track loss on
the intersect set) but xyz is **decimated / filtered** at the
intersect-track level. Downstream policy: prefer nc as primary
bathymetry source for `nc_xyz_intersect` tracks; xyz on the
intersect set kept as supplementary audit / sensitivity layer.
Knowledge update only — no PR-F code change. Full evidence in PRD
section "Finding 2026-05-19c".

## Layout map

```
ncei/
├── SOURCE.md                            # this file
├── tracklines_nc/                       # 2,018 .nc (李杨's MGD77+ NetCDF conversion) + 2 .txt sidecars
│   └── SOURCE.md                        # detailed provenance + dual-content audit
├── tracklines_xyz/                      # 5,382 .xyz (NCEI raw, mb-mixed; classifier handoff to PR-D)
│   └── SOURCE.md
├── derived/                             # (planned PR-E) singlebeam/ + multibeam/ pipeline outputs
├── archive/
│   ├── source_zips/                     # 2 raw zips (the .nc + the .xyz source)
│   │   └── SOURCE.md
│   ├── sunmingzhi_singlebeam_xyz/       # 1 flat .xyz (legacy merge dump, 114.5M rows)
│   │   └── SOURCE.md
│   └── zhoushuai_processed_M/           # M.rar + 3 quadrant .txt extracts (cleaning planned PR-F)
│       └── SOURCE.md
└── docs/                                # README.md + reference PDF (untouched legacy)
```

## Cohabitation rule (Locked decision #10)

The `.nc` source archive
`ncei/archive/source_zips/NCEI_singlebeam_tracks_raw_2018files.zip`
has a **byte-identical duplicate** at
`/mnt/data2/00-Data/gravity/NCEI/archive/NCEI.zip`
(SHA256 `1a9b2c5b7e72f1ca1d17b0f1b7172186ebf56be1ebde67113ad8978a48514eed`).

**User decision 2026-05-16**: keep both copies; do not dedupe.
- The bath project (this `ship/` tree) consumes the archive via the
  `depth` field.
- The gravity project (`/mnt/data2/00-Data/gravity/`) consumes the
  **same bytes** via the `gobs` / `faa` fields.

Each project owns its consumer-side copy where its pipelines expect
it. Two sibling projects, one source archive, one conversion artifact
(李杨's 2024-07-31 NetCDF re-encoding).

## Cross-references

- `tracklines_nc/SOURCE.md` — per-track .nc archive provenance +
  dual-content (bath + gravity) audit + 168-nc-only-tracks finding.
- `tracklines_xyz/SOURCE.md` — 安德超 mixed bundle + R2 classifier
  handoff.
- `archive/sunmingzhi_singlebeam_xyz/SOURCE.md` — frozen flat dump
  + relationship-to-other-corpora analysis.
- `archive/zhoushuai_processed_M/SOURCE.md` — 周帅 regional mb +
  cleaning plan (deferred to PR-F).
- `archive/source_zips/SOURCE.md` — audit-trail index.
- Parent: `../jamstec/SOURCE.md` (symmetric structure on the JAMSTEC
  side; also references 李杨 as the bath+gravity 7z transferer).
- PRD: `.trellis/tasks/05-11-singlebeam-integration/prd.md`
  (Locked decisions #1–#10; "Finding 2026-05-16 (李杨 finding chain)"
  section).
- Attribution: `docs/experiments/2026-05_dataset-source-attribution.md`
  (Footer 2026-05-16 (李杨 finding chain)).
