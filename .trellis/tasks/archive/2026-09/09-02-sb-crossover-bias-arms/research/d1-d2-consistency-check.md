# D1/D2 reviewer consistency check (2026-09-02, pi main session)

Reviewer: pi main agent after D1 (codex/gpt-5.6-sol) and D2 (claude/glm-5.3)
finished. One D1 defect was found in review and fixed by the D1 agent before
this check (SB scope = color-formula inner_training blocks, not frozen
membership cells; see git log of ncei/code/23_*).

## Method

Joined `ncei/derived/sb_track_bias_1min/track_bias_summary.parquet` (D1) with
`ncei/derived/true_crossover_audit/track_stats_<tile>.parquet` (D2) on
(region, track_id). 228 of 230 D1 tracks have crossover stats.

## Findings

1. Gross blunders confirmed by two independent estimators:
   - `jr359` lon059_lat015: D1 bias -4,839 m; D2 crossover median signed
     -4,924 m (n=39). Same track in lon052_lat018: D1 -25.8, D2 -25.4.
   - `elt24` lon021_lat010: D1 +937 m; D2 +760 m (n=57).
   - `03973`/`l884sp` lon068_lat018: D1 +95/+105; D2 +99/+103.
2. Conservative gate refused one real bias: `elt18` lon021_lat010 D1 candidate
   -1,247 m gated `not_significant` (large cell-residual NMAD); D2 shows
   median |diff| 1,033 m over 75 crossovers. Cell-consensus NMAD is inflated
   by within-cell terrain variance; point-precise crossovers resolve the bias.
3. Reverse failure also exists: `odp130jr` lon068_lat018 D1 applied -44 m
   (9 cells, NMAD 10) but 141 crossovers show ~0. Within-cell terrain sampling
   can mimic a bias in the cell-consensus estimator.
4. D2's `median_abs_diff_m` is orientation-free and large for several
   D1-gated tracks (`elt06`, `elt19`, `nbp0203`, `sub7382h`, `hly0602`) —
   these are high-variance or sign-flipping tracks; the D1 gate behaved as
   designed for them except where noted in (2).

## Reviewer conclusion

- D1 bias product is trustworthy for large clean offsets (the dominant GGM
  control risk); the gate suppresses marginal applications as intended.
- The crossover audit has the finer resolving power. If a later round weakens
  the D1 gates, the crossover evidence (not the cell consensus) should be the
  reference for borderline tracks, with elt18 as the motivating case and
  odp130jr as the counter-motivating case for any ungated application.
- SB crossover noise floor (median |diff| 4-72 m by region, raw pre-QC points)
  is far below the 1' same-cell residual p95 (~187 m global), quantifying how
  much of the cell-level "overlap residual" was within-cell terrain, not
  measurement disagreement.

## Verification record

- D1/D2 scripts re-run without --overwrite: both exit without changing files
  ("Complete D1 output set already exists"; D2 skip-if-exists). Log line
  confirmed for both.
- git status: only the four new source/doc files are untracked; no existing
  derived/manifest/freeze file modified.
- D1 hygiene: Arrow-level inner_training predicate + role-map assertion for
  strict MB depths; block-formula assertion for SB scope. Verified in code
  (23_*:119-131, 164-177) and by SB/MB control counts matching frozen
  inner_training cell counts exactly (e.g. lon068_lat018 MB rows = 2148).
