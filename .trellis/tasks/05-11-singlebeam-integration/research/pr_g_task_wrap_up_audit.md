## PR-G Task Wrap-up Audit — `05-11-singlebeam-integration`

> Audit date: 2026-05-22
> Audit type: cross-cutting documentation + spec consistency + reproducibility spot-check
> Scope: final pass before `/trellis:finish-work`

---

## Section 1 — Cross-cutting documentation audit

| File | Status | Notes |
|---|---|---|
| `/mnt/data2/00-Data/ship/CLAUDE.md` | N/A | File does not exist. No top-level CLAUDE.md to audit. |
| `/mnt/data2/00-Data/ship/ncei/CLAUDE.md` | N/A | File does not exist. |
| `ncei/docs/README.md` | **MAJOR DRIFT** | Pre-PR-B / pre-PR-C content. See findings below. |
| `.trellis/spec/backend/index.md` | PASS | Indexes all 8 backend specs; provenance note correct. |
| `.trellis/spec/backend/directory-structure.md` | **MINOR DRIFT** | Does not enumerate post-Step-04+ NCEI subdirs. |
| `.trellis/spec/backend/data-contracts.md` | **MINOR DRIFT** | Validation-cells schema reflects JAMSTEC-only; NCEI 31-col cell-quality-flags + 5-product validation cells absent. |
| `AGENTS.md` | PASS-MINOR | Refers to "future `ncei/code/`" but `ncei/code/` is fully populated with 13 scripts. |

### Finding 1.1 — `ncei/docs/README.md` is severely stale (MAJOR)

This is currently the README a consumer sees on opening `ncei/docs/`. Content is the pre-rename "what is `singlebeam.xyz`" note, describing the flat dump as if it were the active product. Key staleness:

- L7-11 describes the directory as containing `singlebeam.xyz` and references the raw archive at `/mnt/data2/00-Data/NCEI_singlebeam_tracks_raw_2018files.zip` (PR-C moved this to `ncei/archive/source_zips/`).
- No mention of `tracklines_nc/`, `tracklines_xyz/`, the R2 sb/mb classifier, the 13-script pipeline (01..13), the M.rar branch, or the §13-§19 spec sections.
- L56-57 says "Do not delete `NCEI_singlebeam_tracks_raw_2018files.zip` unless a reproducible build path for `singlebeam.xyz` is documented elsewhere" — this caveat is obsolete; `singlebeam.xyz` is now an archived legacy artifact at `ncei/archive/sunmingzhi_singlebeam_xyz/`.

**Suggested action**: log as follow-up. Rewriting the README from scratch is a non-trivial doc job, not a quick fix. The active source-of-truth docs (per-step reports + `ncei/SOURCE.md` + spec §13-§19) all exist and are consistent; the legacy README is a discoverability nuisance, not a correctness blocker.

### Finding 1.2 — `directory-structure.md` lacks NCEI post-Step-04 subdirs (MINOR)

L23-26 describes `ncei/` as if PR-C is still pending:

```
├── ncei/                   # NCEI singlebeam track corpus. Formerly
│                           #   ship/NCEI_singlebeam/ — renamed 2026-05-16
│                           #   (PR-B). PR-C will populate tracklines_{nc,xyz}/
│                           #   and archive/ subdirs.
```

PR-C landed on 2026-05-16 and PR-E1..PR-F + Step 04A/B + Step 05A/B + Step 06A/B + Step 07A/B all landed since. Current `ncei/` tree has:

```
ncei/
├── tracklines_nc/, tracklines_xyz/                    (PR-C raw)
├── archive/{zhoushuai_processed_M, sunmingzhi_singlebeam_xyz, source_zips}/
├── code/                                              (13 scripts)
├── manifests/                                         (canonical + sample)
├── derived/{singlebeam, multibeam, regional_mrar, quality_flags_1min, quality_policy_calibration_1min, validation_cells_1min, overlap_bias_1min, cross_branch_overlap_1min, aggregation_design_audit}/
├── docs/                                              (16 step reports + 2 schema + README + PDF)
└── output/logs/
```

**Suggested action**: log as follow-up. The directory-structure.md update is a single-block rewrite of L23-26. Non-trivial enough to defer because it touches the "ncei/" placeholder description rather than just a one-line fact fix.

### Finding 1.3 — `data-contracts.md` validation-cells + file-quality-flags schemas are JAMSTEC-only (MINOR)

L135-148: `File quality flags` section describes the JAMSTEC file-level schema (`file_id, cruise_id, quality_flag ∈ {keep, high_variance_review, review, exclude}`). The NCEI Step 06B output is a cell-level 31-column schema documented in `pipeline-design-decisions.md` §18.7 — and uses `quality_tier ∈ {high_confidence, medium_confidence, low_confidence}` (§17.4/§18 + §19.7 mapping table).

L152-164: `Validation cells` section names a single export `derived/validation_cells_1min/primary_ship_validation_cells_1min.parquet` with `quality_tier ∈ {A_tier, B_tier, C_tier}`. The NCEI Step 07B output is **5 distinct products** under `ncei/derived/validation_cells_1min/` per spec §19.3. The JAMSTEC and NCEI products are joined inside `13_build_validation_cells.py` under fixed precedence (§19.2) with A/B/C → high/medium/low mapping (§19.7).

**Suggested action**: log as follow-up. The fix is a small additive section ("NCEI cell-level quality + validation products") that points to §13-§19 in pipeline-design-decisions.md. data-contracts.md was authored against the JAMSTEC pipeline; making it the cross-dataset reference is a non-trivial documentation refactor and not load-bearing for any consumer (consumers read the per-step reports + §13-§19).

### Finding 1.4 — `AGENTS.md` describes `ncei/code/` as future (PASS-MINOR)

L25 and L36 of AGENTS.md say `# PR-E and later` and "future `ncei/code/`". The code dir is fully populated.

**Suggested action**: leave as-is. The "future" wording was correct at PR-D commit time; the AGENTS.md note describes the import convention, not the current state of `ncei/code/`. Reads correctly to a future contributor.

---

## Section 2 — Spec §13-§19 internal consistency audit

| Check | Status | Notes |
|---|---|---|
| 1. Versioning chain (7 constants) | PASS | All 7 declared in code; all named per spec. |
| 2. cell_id contract (§13.2) | PASS | Construction `f"1min_{lat_bin}_{lon_bin}"` is in `07_aggregate_file_cells_1min.py:437-442`; every consumer (08/09/10/11/12/13) joins by `cell_id` string. |
| 3. Branch semantics (singlebeam / multibeam_ncei / regional_mrar) | PASS | Implemented in §13.7 derivation rule; mrar always disjoint. |
| 4. Dedup convention (§13.3 exact-float) | PASS | `06_supplementary_quality_check.py` + `07_aggregate_file_cells_1min.py` use exact-float; audit-rounded triples confined to `step04_aggregation_design_audit.md`. |
| 5. Manual review never excludes alone (§17.5 #4 + §18.3 invariant) | PASS | §18.3 partitions `applies_as=="invariant"` rules out of first-match path; rule `manual_review_not_exclusion` is the only invariant. |
| 6. AUV Sentry downweight to 0.55 (§17.5 + §18.6 + §19.6) | PASS | Rule `mb_v0_highdup_sentry_downweight` weight 0.55, retained in strict + expanded primary with `auv_sentry_flag=True` + `source_risk_class='auv_sentry_highdup'`. Step 06B post-check #5 asserts the sidecars. |
| 7. Source precedence §19.2 vs branch_role §18.8 | PASS-WITH-NOTE | NCEI Step 06B documents 3 branch_role values (supplementary_coverage / multibeam_supplement / regional_experiment) per §18.8; Step 07B introduces a 4th value `multibeam_primary` for JAMSTEC rows at `13_build_validation_cells.py:522`. §19.2 alludes to JAMSTEC precedence but the §18.8 table is not extended in §19. See finding 2.1. |

### Versioning chain — found constants

```
07_aggregate_file_cells_1min.py     AGGREGATION_VERSION       = "ncei_cells_v0.1.0"
08_merge_branch_cells_1min.py       MERGE_VERSION             = "ncei_cells_merge_v0.1.0"
09_source_specific_overlap_residuals.py   OVERLAP_VERSION     = "ncei_overlap_v0.1.0"
10_cross_branch_overlap_audit.py    CROSS_OVERLAP_VERSION     = "ncei_cross_overlap_v0.1.0"
11_quality_policy_calibration_audit.py    POLICY_CALIBRATION_VERSION = "ncei_policy_calib_v0.1.0"
12_apply_quality_policy.py          POLICY_ENFORCE_VERSION    = "ncei_policy_enforce_v0.1.0"
13_build_validation_cells.py        VALIDATION_PRODUCT_VERSION = "ncei_validation_cells_v0.1.0"
```

All version strings written as parquet columns on every output row per spec §13.1, §14.1, §15.1, §16.1, §17.1, §18.1, §19.1.

### Finding 2.1 — `multibeam_primary` branch_role is implemented in code but not in §18.8 (PASS-WITH-NOTE)

`ncei/code/13_build_validation_cells.py:522` sets `branch_role = "multibeam_primary"` for JAMSTEC rows joining into Products 1 and 2. The §18.8 branch_role table in `pipeline-design-decisions.md` enumerates only the 3 NCEI branches (singlebeam/multibeam_ncei/regional_mrar → supplementary_coverage/multibeam_supplement/regional_experiment).

§19.2 source precedence implicitly requires a JAMSTEC branch_role to distinguish "primary" from "supplement", but the value is not explicitly named in the spec. Reader must trace into `13_build_validation_cells.py` to discover it.

**Suggested action**: log as follow-up. The §18.8 table is consistent for NCEI Step 06B (which never emits JAMSTEC rows). The new label appears only at the §19 cross-source join. Spec §19.2 could append a "JAMSTEC rows take `branch_role='multibeam_primary'` and `branch='jamstec_mb'` (constants in `13_build_validation_cells.py`)" sentence to remove the trace-into-code requirement. Not blocking for finish-work — the constants are visible to any reader of Step 07B's report.

### MRAR source_type defensive union (§14.4)

`08_merge_branch_cells_1min.py:175`: `MRAR_SOURCE_TYPE_VALUES = frozenset({"mrar_zhoushuai", "mrar_processed", "ncei_mrar"})` matches §14.4's enumerated union exactly. Current emit literal is `mrar_zhoushuai` (canonical) per `04_clean_mrar.py:265, 304`; older literals accepted for archive-interop per spec.

---

## Section 3 — PRD vs implementation completeness

### Goal coverage

| PRD goal | Implementation | Status |
|---|---|---|
| Build NCEI singlebeam pipeline | `ncei/code/01_..13_*.py` (13 production scripts) | DONE |
| Extract shared lib | `_common/` with R2 classifier, IO helpers, tests, calibration drivers | DONE |
| Dir renames (`NCEI_multibeam → jamstec`, `NCEI_singlebeam → ncei`) | PR-A + PR-B executed 2026-05-16 | DONE |
| New-data ingest (`total_tracklines_xyz.zip`, `M.rar`, `singlebeam.xyz`) | PR-C executed 2026-05-16 | DONE |
| sb/mb classifier | `_common/r2_classifier.py` (PR-D) + manifest emission in steps 02/03 | DONE |
| M.rar cleaning | `ncei/code/04_clean_mrar.py` (PR-F) | DONE |
| Spec updates | `pipeline-design-decisions.md` §10-§19, `index.md`, `directory-structure.md` | PARTIAL (see §1 findings) |
| Step 08 bit-identical verification | PR-A note records hash-only smoke check, 20/20 .py files SHA256-identical | DONE |

### Locked decisions Q1-Q8 audit

| Q# | Decision | Implementation pointer | Status |
|---|---|---|---|
| Q1 | `ncei/` slug + B1 layout | tree as built | DONE |
| Q2 | R2 classifier rule | `_common/r2_classifier.py` + spec §10 | DONE |
| Q3 | M.rar cleaning thresholds | `04_clean_mrar.py` + spec §12 | DONE |
| Q4 | Migration order O1 (PR-A/B/C before pipeline) | git history confirms ordering | DONE |
| Q5 | Path-rewrite scope | `scripts/refactor/rewrite_paths.py` + 3 lineage-label preservations | DONE |
| Q6 | No standalone provenance audit | R2 classifier handles both .nc and .xyz uniformly per spec §10 | DONE |
| Q7 | 168 nc-only tracks | Resolved by 2026-05-19 finding (gravity-only tracks, no usable depth); PRD section + ncei/SOURCE.md + tracklines_nc/SOURCE.md updated | DONE |
| Q8 | M.rar provenance | Recorded as known unknown in `ncei/archive/zhoushuai_processed_M/SOURCE.md` | DONE (accepted) |

### Acceptance Criteria pass

11 PRD acceptance-criteria boxes (unchecked in source, verified here):

1. ✅ `NCEI_multibeam/` absent on disk; `jamstec/multibeam/` present.
2. ✅ Uppercase `JAMSTEC/` absent; subdirs under lowercase `jamstec/` (`gravity_data/`, `archive/source_zips/`, `archive/bathymetry_data/`).
3. ✅ `NCEI_singlebeam/` renamed to `ncei/`.
4. ✅ `ncei/archive/zhoushuai_processed_M/` exists with extracted M.rar + `SOURCE.md`.
5. ✅ `ncei/archive/sunmingzhi_singlebeam_xyz/` exists with `singlebeam.xyz` + `SOURCE.md`.
6. ✅ `total_tracklines_xyz.zip` placed at `ncei/archive/source_zips/total_tracklines_xyz.zip` + provenance recorded in `tracklines_xyz/SOURCE.md`.
7. ✅ R2 classifier exists in `_common/r2_classifier.py` with 11 passing tests; 12 confirmed-mb files all classify as mb per calibration scan; sample of clear sb files classify as sb.
8. ✅ M.rar cleaning step in `04_clean_mrar.py`; positive depths → land mask sidecar; `depth < -11,500 m` → nodata; thresholds in spec §12.
9. ✅ Step 08 bit-identical verification documented in PR-A execution notes (hash-only smoke check, 20/20 .py files SHA256-identical pre/post mv).
10. ✅ No `NCEI_multibeam` / `NCEI_singlebeam` strings in `**/*.{py,sh,yaml}` outside allowlisted lineage labels (3 .py literals per Q5b) and the rewrite-tool source.
11. ✅ `spec/backend/*` no longer carries the "misnamed" caveat; provenance note at `index.md:12` is the post-rename historical record per locked decision.

### PR plan tracking

| PR | Status | Notes |
|---|---|---|
| PR-A (jamstec rename) | LANDED 2026-05-16 | |
| PR-B (ncei rename) | LANDED 2026-05-16 | |
| PR-C (new-data ingest) | LANDED 2026-05-16 | |
| PR-D (shared lib + R2 classifier) | LANDED 2026-05-16 | |
| PR-E1 (trackline source manifest) | LANDED 2026-05-19 | |
| PR-E2 (.nc standardize) | LANDED 2026-05-19 | |
| PR-E3 (.xyz supplement) | LANDED 2026-05-19 | |
| PR-E4 (classification review table) | LANDED (folded into E1/E2/E3 manifests) | |
| PR-F (M.rar cleaning + universal depth clip) | LANDED 2026-05-19 | |
| **Beyond original PR plan** | LANDED 2026-05-20..22 | Step 03A/03B/04A0/04A/04B/05A/05B/06A/06B/07A/07B all landed during PR-E follow-up; spec §13-§19 documents them. |
| PR-G (this audit) | IN PROGRESS | |

**Status**: PR plan effectively complete. Steps 04A through 07B extended the original PR-E scope organically; each landed with a per-step report + spec section.

### Unresolved open questions in PRD

None of Q1-Q8 remain open. Two known-unknowns are explicitly accepted:

1. **Why 168 nc-only tracks were excluded from the xyz bundle** — resolved 2026-05-19 (gravity-only tracks, no usable depth).
2. **M.rar source organization (Q8)** — accepted as a known unknown, recorded in `zhoushuai_processed_M/SOURCE.md`. Not blocking.

---

## Section 4 — Reproducibility spot-check (cross_branch_overlap_audit, sample mode)

### Method

Target script: `ncei/code/10_cross_branch_overlap_audit.py` (Step 05B).
Mode: `--run-label sample --overwrite` (capped at 50,000 rows / pair, deterministic cell_id-lex sort).

### Hash captures

```
Run 0 (pre-existing artifact, May 22 01:11):
  cross_overlap_cells.parquet         md5 = c1655feb54187b254a0f36ec8221998e
  cross_overlap_pair_summary.parquet  md5 = 0faa83b4d08893251e944b26f40dcb45

Run 1 (re-run, exit 0, 158 s):
  cross_overlap_cells.parquet         md5 = c1655feb54187b254a0f36ec8221998e  (BIT-IDENTICAL)
  cross_overlap_pair_summary.parquet  md5 = 41e4c41a05f5701493cc79f47d7c6ad5  (DIFFERS)
  cross_overlap_breakdowns.tsv        md5 = ca693abb320dacf91d835753f7781ecf
```

### Finding 4.1 — `cross_overlap_pair_summary.parquet` is non-bit-identical only because of `runtime_seconds`

The 23-column pair_summary has `runtime_seconds` as one column (per-pair wall time recorded as analysis runs). All 22 content columns are bit-identical across runs (verified via column-filter md5: `25506c3bb640c701fd1399e8f70ed16d` after dropping `runtime_seconds`).

The implementation deliberately records runtime per-pair as performance telemetry. This is not a correctness defect — it's a documented behavior in spec §16.6 ("pair summary [...] `rmse_pair_m`, [...] `runtime_seconds`"). Downstream consumers either ignore the column or treat it as metadata.

**Status**: PASS for analytical reproducibility. Per-cell residuals + breakdowns are bit-identical across runs; only timing metadata varies.

**Suggested action**: leave as-is. The `runtime_seconds` column is documented; treating it as bit-identical would require either (a) freezing the wall-clock at run-start (artificial), or (b) dropping the column (loses performance audit). Neither is worth the change.

---

## Section 5 — File / directory inventory audit

### 5.1 `ncei/code/` — production scripts

13 production scripts present, numbered 01..13 with no gaps and no unexpected files:

```
01_build_trackline_source_manifest.py     (PR-E1)
02_standardize_singlebeam.py              (PR-E2)
03_standardize_xyz.py                     (PR-E3)
04_clean_mrar.py                          (PR-F)
05_point_quality_check.py                 (Step 03A)
06_supplementary_quality_check.py         (Step 03B)
07_aggregate_file_cells_1min.py           (Step 04A)
08_merge_branch_cells_1min.py             (Step 04B)
09_source_specific_overlap_residuals.py   (Step 05A)
10_cross_branch_overlap_audit.py          (Step 05B)
11_quality_policy_calibration_audit.py    (Step 06A)
12_apply_quality_policy.py                (Step 06B)
13_build_validation_cells.py              (Step 07B)
```

Plus `__init__.py` and `__pycache__/` (gitignored). No unexpected files.

**Note**: script numbering 01..13 is **not** a per-spec stage number (e.g. `05_point_quality_check.py` is Step 03A, `10_cross_branch_overlap_audit.py` is Step 05B). This is the per-spec naming convention in `directory-structure.md` §"Script naming" (two-digit prefix = pipeline-stage ordering, not original-spec step numbers). Acceptable — but a reader without context could be confused. Each script's docstring opens with "Step XX — …" which mitigates this.

### 5.2 `ncei/derived/` — pipeline outputs

13 stage directories, all gitignored via `**/derived/` rule:

```
aggregation_design_audit/        (Step 04A0 audit, retained on disk for reproducibility)
cross_branch_overlap_1min/       (Step 05B canonical)
cross_branch_overlap_1min_sample/(Step 05B sample)
multibeam/                       (sb/mb classifier output)
overlap_bias_1min/               (Step 05A canonical)
overlap_bias_1min_sample/        (Step 05A sample)
quality_flags_1min/              (Step 06B canonical)
quality_flags_1min_sample/       (Step 06B sample)
quality_policy_calibration_1min/      (Step 06A canonical)
quality_policy_calibration_1min_sample/ (Step 06A sample)
regional_mrar/                   (M.rar cleaning + derived cells)
singlebeam/                      (sb pipeline output)
validation_cells_1min/           (Step 07B canonical)
validation_cells_1min_sample/    (Step 07B sample)
```

All gitignored (none of these are tracked in git).

### 5.3 `ncei/docs/` — markdown reports

20 markdown files tracked + 4 `_sample.md` files untracked (gitignored via `ncei/docs/*_sample.md`):

```
TRACKED (20):
README.md                                          (PRE-PR-B STALE; see §1.1)
mrar_cleaning_report.md                            (PR-F)
singlebeam_standardization_report.md               (PR-E2)
step03_point_quality_check_report.md               (Step 03A)
step03b_supplementary_checks_report.md             (Step 03B)
step04_aggregation_design_audit.md                 (Step 04A0)
step04a_file_cells_1min_report.md                  (Step 04A)
step04b_cells_1min_merge_report.md                 (Step 04B)
step05a_source_specific_overlap_bias_report.md     (Step 05A)
step05b_cross_branch_overlap_audit_report.md       (Step 05B)
step06a_quality_policy_calibration_report.md       (Step 06A)
step06b_cell_quality_flags_report.md               (Step 06B)
step06b_quality_policy_rule_review.md              (Step 06B preflight)
step06b_semantic_lock_report.md                    (Step 06B lock)
step07a_validation_cell_preflight_report.md        (Step 07A preflight)
step07b_validation_cells_report.md                 (Step 07B)
trackline_source_manifest_report.md                (PR-E1)
trackline_source_manifest_schema.md                (PR-E1 schema)
xyz_standardization_report.md                      (PR-E3)
On the accuracy evaluation and correction of global single-beam depths.pdf  (PR-B legacy carry-over)

UNTRACKED (4, gitignored):
step05b_cross_branch_overlap_audit_report_sample.md
step06a_quality_policy_calibration_report_sample.md
step06b_cell_quality_flags_report_sample.md
step07b_validation_cells_report_sample.md
```

Coverage: 1 README + 16 step reports + 2 schema docs + 1 PDF = 20 tracked. Each spec §13-§19 has its corresponding step report. Naming convention is consistent: `step<NN><a/b>_<slug>_report.md`. PASS-MINOR — the legacy `README.md` is stale (Finding 1.1).

### 5.4 `.trellis/tasks/05-11-singlebeam-integration/research/` — task artifacts

```
quality_policy_enforced_rules.tsv     (18 cols × 16 rows, enforced rule list — referenced by spec §18.2)
step04_aggregation_design_audit.md     (mirror of ncei/docs/, kept for task lineage)
step07a_validation_cell_preflight.md   (preflight memo referenced by spec §19.10)
_audit_task2.py                        (transient research script; not part of pipeline)
pr_g_task_wrap_up_audit.md             (this file)
```

The TSV is enforced as the sole rule source per §18.2; semantic lock in `ncei/docs/step06b_semantic_lock_report.md`.

### 5.5 `ncei/manifests/` — canonical vs sample

All `*.parquet` and `*.tsv` here are gitignored (extension-globs + `ncei/manifests/*.tsv` rule). Manifests are regenerable artifacts produced by the per-step scripts:

```
bathymetry_entry_manifest.*                 (Step 03A canonical)
bathymetry_entry_manifest_supplementary.*   (Step 03B canonical)
bathymetry_entry_manifest_sample.*          (Step 03A sample)
bathymetry_entry_manifest_supplementary_sample.*  (Step 03B sample)
bathymetry_entry_manifest_supplementary_test100.* (Step 03B test100)
cells_1min_manifest.*                       (Step 04B canonical)
cells_1min_manifest_sample.*                (Step 04B sample)
file_cells_1min_manifest.*                  (Step 04A canonical)
file_cells_1min_manifest_sample.*           (Step 04A sample)
file_cells_1min_manifest_test100.*          (Step 04A test100)
intersect_divergence_audit.*                (Step 04A0)
intersect_divergence_audit_sample.*         (Step 04A0 sample)
intersect_divergence_audit_test100.*        (Step 04A0 test100)
singlebeam_points_raw_manifest.*            (PR-E2)
singlebeam_points_raw_manifest_sample.*     (PR-E2 sample)
trackline_classification_review.tsv         (PR-E1 / PR-E4 review table)
trackline_source_manifest.*                 (PR-E1 canonical)
xyz_points_raw_manifest.*                   (PR-E3 canonical)
xyz_points_raw_manifest_sample.*            (PR-E3 sample)
```

All regenerable. No canonical-tracked manifest — design is "git tracks code + spec + reports, not data products". Consistent with spec §"Database Guidelines" intent.

---

## Overall verdict

**FOLLOW-UP** — task is ready for `/trellis:finish-work`. No fix-first blockers; 3 known doc-staleness items recommended as post-merge follow-up:

### Follow-up list (no merge block)

1. **Rewrite `ncei/docs/README.md`** (Finding 1.1) — currently describes the pre-PR-B `singlebeam.xyz` flat dump as the active artifact. Replacement should index the 13-script pipeline + spec §13-§19 + the SOURCE.md sidecars. Effort: ~30 min doc rewrite. Severity: discoverability-only; no consumer is mis-led at the code level because every script's docstring is current.
2. **Update `.trellis/spec/backend/directory-structure.md`** L23-26 NCEI subtree block (Finding 1.2) — current text reads as PR-C pending. Replace with the post-Step-04+ subdir tree. Effort: ~15 min.
3. **Extend `.trellis/spec/backend/data-contracts.md`** (Finding 1.3) — add an "NCEI cell-level quality (Step 06B)" section + "NCEI validation products (Step 07B 5 products)" section pointing into §17-§19 of `pipeline-design-decisions.md`. Effort: ~45 min; this section becomes the cross-dataset reference for downstream consumers reading data contracts.
4. **Note JAMSTEC `branch_role='multibeam_primary'` in §18.8 or §19.2** (Finding 2.1) — currently only visible by reading `13_build_validation_cells.py:522`. Effort: 1 paragraph addition. Severity: low — no consumer is currently affected.

### Per-section summary

| Section | Status | Top finding |
|---|---|---|
| 1. Docs audit | MAJOR (1) + MINOR (2) + PASS-MINOR (1) | `ncei/docs/README.md` is severely stale |
| 2. Spec §13-§19 consistency | PASS (6/7) + PASS-WITH-NOTE (1) | `multibeam_primary` role not in §18.8 |
| 3. PRD completeness | PASS | All 11 acceptance criteria met; all 8 locked decisions implemented; PR plan complete (extended organically via Steps 04A..07B) |
| 4. Reproducibility spot-check | PASS | Per-cell parquet bit-identical across re-runs; pair_summary content stable, runtime_seconds varies (by design) |
| 5. Inventory audit | PASS | 13 scripts, 20 tracked docs, 13 derived subdirs (all gitignored), gitignore correctly scoped |

### Top 3 findings to surface to main session

1. **`ncei/docs/README.md` is severely stale** (Finding 1.1) — only major drift. The README still describes the pre-PR-B `singlebeam.xyz`-as-active-artifact framing. Strongly recommend rewrite as a PR-G follow-up. Not a code-correctness issue but a serious discoverability nuisance for future contributors / agents reading `ncei/docs/`.

2. **`data-contracts.md` validation-cells + file-quality-flags schemas describe only JAMSTEC** (Finding 1.3) — NCEI Step 06B's 31-col cell-quality-flags schema (§18.7) and Step 07B's 5-product validation outputs (§19.3) are documented authoritatively in `pipeline-design-decisions.md` §17-§19, but the central data-contracts.md doesn't index those forward. Consumers using `data-contracts.md` as the entry point currently see only the legacy A/B/C tier system.

3. **Reproducibility verified for Step 05B sample mode** (Section 4) — per-cell parquet `c1655feb54187b254a0f36ec8221998e` bit-identical across 2 re-runs. Only `runtime_seconds` column drifts in `cross_overlap_pair_summary.parquet`, which is per-spec §16.6 telemetry. No correctness regression.
