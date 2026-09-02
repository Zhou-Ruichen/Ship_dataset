# Ship-sounding screening methods survey and gap map

mode: exploratory (desk research; no repo data modified)

## Decision this task must answer

Which established ship-sounding screening methods should this repo's pipeline
adopt, and where. The output is a gap map: each surveyed method marked as
already-have / partial / missing against our pipeline, with a concrete
recommendation (which step, which data, what it would change).

## Why now

Our screening chain is point QC -> 1' cell QC -> calibrated quality classes
-> strict eligibility (steps 05-13), plus per-track bias and pairwise
crossover audit (steps 09, going global in task 09-02-global-sb-bias-product).
Known gap: we compute pairwise crossover differences but do not solve the
crossover NETWORK for per-track offsets, which is the established way to
systematically identify and down-weight bad tracks. External practice should
be surveyed before we design that addition.

## Survey targets (all four required)

1. Crossover-based track adjustment: GMT x2sys_cross/x2sys_solve lineage
   (Wessel & Watts 1988 and successors), MB-System crossover tools. How the
   network solves per-track offsets; how bad tracks are detected, weighted,
   or iteratively rejected; what minimum crossover count per track is needed;
   how the solution is anchored (absolute reference vs free network).
2. Screening in major compilations: GEBCO (how contributing ship data are
   quality-controlled), GMRT quality assessment, NCEI's own trackline quality
   flags, SIO's ship-track gravity cleaning practice (crossover-based
   screening used by the Sandwell group for marine gravity).
3. Quality standards and uncertainty models: IHO S-44 orders; depth-dependent
   uncertainty models for singlebeam (e.g. percent-of-water-depth rules);
   how vintage uncorrected soundings (assumed 1500 m/s sound speed) are
   treated; tide, draft, and datum correction practice and what errors remain
   when they are unavailable.
4. Multibeam swath QC in brief (CUBE, beam-quality flags): whether any of it
   is applicable to aggregated 1' cell products like ours, given most of our
   multibeam files lack timestamps.

## Hard constraints

- Desk research only. Do not modify pipeline code or derived data. Do not run
  repo computations.
- Every method claim must carry a citation (paper/report/official doc with
  year); no invented references. Prefer primary sources (methods papers,
  official format/standard documents) over blog posts.
- The gap map must reference our pipeline steps by their real names
  (ncei/code step numbers) so recommendations are directly actionable.
- Write in Chinese, plain technical register, per the project AGENTS.md
  style rules (no AI-tell phrasing).

## Deliverable

- `ncei/docs/step10_screening_methods_survey.md`: the four survey sections,
  then the gap map table (method -> our status -> recommendation), then a
  short "recommended additions, in priority order" section. Expected top
  candidates to evaluate (verify or refute during the survey): crossover
  network least-squares adjustment anchored on MB-supported tracks; a
  per-track quality grade combining bias significance + crossover misfit +
  era/instrument metadata; depth-dependent SB uncertainty as a cell weight.

## Out of scope

- Implementing any method. Running crossover network adjustment. GEBCO as a
  screening gate for our data (it is a diagnostic stratifier only in this
  repo).
