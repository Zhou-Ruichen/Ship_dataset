# Data product spec: intermediates, global grid, downstream contract, consumer registry

mode: documentation/specification (no data processing; writes one normative
document plus the registry file)

## Decision this task must answer

Write the normative spec that future data rounds and downstream repos follow.
The design decisions are already made (listed below); the task is to write
them down precisely against the REAL schemas of the existing products, so
that nothing in the spec contradicts what is actually on disk.

## Design decisions to encode (do not redesign; verify against disk)

1. Standardized intermediates, three layers. New ship data must land in all
   three before any product is regenerated:
   - L1 points: one parquet per track, unified columns (lon, lat,
     depth positive-down metres, time or order index, source fields,
     quality flags) — verify against `ncei/derived/singlebeam/points_raw/`
     and `ncei/derived/tracklines_*/`.
   - L2 cells: per-track 1-arcmin cell statistics (median, NMAD, n points)
     — verify against `ncei/derived/singlebeam/file_cells_1min/`.
   - L3 manifest: the trackline source manifest registers every track's
     origin, format, era, coverage —
     `ncei/manifests/trackline_source_manifest.parquet` + its schema doc.
2. Global gridded product (to be produced in a later task, spec it now):
   one row per 1-arcmin cell; strict MB wins where present; final-layer SB
   (`track_disposition != 'reject'`) fills the rest; cells with both keep
   the SB value in a diagnostic side column. Partitioned parquet by
   latitude band; directory carries a round tag (`_r2` etc.); a manifest
   records generation time + input hashes.
3. Singlebeam production decision (record with evidence): keep producing
   ONE final SB layer only. Evidence: interpolation holdout pooled
   1840.89 m without SB vs 731.12 corrected vs 673.19 with the rejection
   rule (ncei/docs/step10_sb_interpolation_holdout_report.md). Raw /
   adjusted / reject variants remain script-reproducible but are not
   maintained as products.
4. Downstream consumption contract: paths, schemas, the filter rule, how
   to pin a round (round tag + input hash), and the requirement that
   downstream run manifests record product round + input hashes (the 15
   repo already does this; make it a written requirement).
5. Consumer registry: `consumers.yaml` at repo root. Fields: repo_name,
   repo_path, product, round, consuming_agent_or_workspace, registered_at.
   Registration is the documented last step of onboarding. On a new data
   round, each listed repo's agent/workspace is notified via paseo.
   State honestly that registration is conventional, not enforced.

## Deliverables

1. `docs/数据产品规范与下游接入.md` — the normative spec, plain Chinese,
   project style rules (no insider jargon; every product explained in one
   actionable sentence). Sections: intermediates spec (L1/L2/L3 with real
   column lists verified from disk); global grid product spec; SB
   production decision + evidence; consumption contract; consumer registry;
   update/notification procedure (what happens when a new round lands).
2. `consumers.yaml` at repo root with one example entry commented out and
   the schema explained in a header comment.

## Hard constraints

- Do NOT edit README.md (owned by concurrently running task
  09-03-global-sb-final-product) and do NOT touch any derived outputs or
  code. Only the two deliverable files.
- Verify every column list and path in the spec against the real files;
  where the final-layer product (task 09-03-global-sb-final-product, still
  running) is referenced, cite its prd
  (`.trellis/tasks/09-03-global-sb-final-product/prd.md`) for the pinned
  schema (`track_disposition`, round tag `_r2`) and say so.
- No GEBCO content beyond the existing rule (diagnostic stratifier only,
  never a screening gate).

## Acceptance criteria

- A new data source owner can follow the spec to produce conforming L1/L2/L3
  outputs without asking anyone.
- A downstream agent can follow the contract to consume the global product
  and register itself without asking anyone.
- Every path and column name in the document exists on disk or is explicitly
  marked as "produced by task 09-03-global-sb-final-product (in progress)".
