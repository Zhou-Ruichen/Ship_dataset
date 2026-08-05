# Planning evidence snapshot

## Inspected inputs

- Downstream handoff contract:
  `/mnt/data2/06-Projects/12-ggm_scs/.trellis/tasks/08-04-scs-upstream-lineage-and-label-contract/research/upstream-handoff.md`
  (SHA256
  `8a152151016de6a45cbef966a78d74e9750c40dffba197ad36cae0a76cdfe94c`).
- Prior upstream lineage run:
  `ncei/derived/scs_upstream_lineage_audit/20260804T202026Z/`.
- Latest verified preflight:
  `ncei/derived/scs_ship_qc_v2_preflight/20260804T230252Z/`.
- Archived prior Trellis lineage task:
  `.trellis/tasks/archive/2026-08/08-05-scs-upstream-lineage-label-audit/`.
- Trellis workspace journal:
  `.trellis/workspace/Ruichen Zhou/journal-1.md` Session 3 and its committed
  preflight receipt. The repository `.claude/` tree contains workflow skills,
  agents, commands, and hooks but no retained project conversation transcript;
  no absent Claude transcript is treated as evidence.
- MRAR provenance/cleaning evidence:
  `ncei/archive/zhoushuai_processed_M/SOURCE.md`, `M.rar`, extracted text,
  cleaned parquet, and `ncei/code/04_clean_mrar.py`.
- JAMSTEC manifest and all exact contributor paths:
  `jamstec/multibeam/manifests/file_manifest_points_raw.parquet` and
  `jamstec/multibeam/raw/dat_by_subzip/`.

## Established planning facts

- Frozen cohort: 174,965 cells, comprising 165,966 MRAR and 8,999 JAMSTEC.
- Prior exact replay: 174,913 equal and 52 different at `1e-9 m`; maximum
  absolute difference `26.92962295081952 m`.
- The difference mechanism is the historical Step 04a weighted average of
  chunk medians for file-cells crossing batches; point counts remain exact.
- Contributor closures already observed: 58 JAMSTEC physical files, 14,072
  JAMSTEC file-cell rows, 19 official cruises, 2,658 multi-file cells, 2,472
  multi-cruise cells, and nine frozen aggregation-conflict cells.
- Full-path manifest join closes 58/58 with no duplicate relative path. All 58
  entries are headerless ASCII `lon_lat_depth_3col`, have exactly three
  columns, and have null `date_col`, `time_col`, and `sonar_idx_col`. Five are
  manifest-classified transit and 53 `unknown_or_survey`; their manifest line
  counts total 34,030,036 physical rows.
- Therefore current files preserve coordinates, depth, and physical record
  order, but do not establish row-level time, line, ping, beam, heading,
  quality flag, or chronological order.
- Local search found no direct `RIAM`, `Uehara`, or `tscs` evidence tied to
  `M.rar`. `SOURCE.md` documents a 2026-05-15 delivery by Zhou Shuai, no
  accompanying README, a processed quadrant bundle, and local cleaning version
  `mrar_v0.1.0`. This supports a bounded identity check, not an association.
- MRAR vertical datum and cruise/line/time identities remain unrecoverable in
  the current evidence. JAMSTEC vertical datum is absent from inspected
  official metadata and remains officially unknown.
- Latest preflight verification is `pass`; it reports 2,658 aggregation cells
  and the candidate table contains exactly nine rows with
  `interpretation_state=aggregation_conflict`.

## Input byte facts to freeze in the implementation

| Artifact | Bytes |
|---|---:|
| `M.rar` | 396,719,475 |
| `0-180E-0-85N.txt` | 1,375,866,688 |
| `0-90W-0-85S.txt` | 929,513,351 |
| `90-180W-0-85S.txt` | 1,863,835,358 |
| `bathymetry_points.parquet` | 1,408,960,222 |
| `cleaning_audit.parquet` | 9,775 |
| `ncei/code/04_clean_mrar.py` | 26,938 |

The full producer must recompute and record SHA256 rather than trusting this
planning snapshot.

## Planning boundary

No GGM/PINN error, prediction, residual, confirmation metric, GEBCO value, or
product-consensus value was used in this planning evidence. The nine preflight
IDs are an already frozen diagnostic membership and must be read by minimal
columns only during implementation.
