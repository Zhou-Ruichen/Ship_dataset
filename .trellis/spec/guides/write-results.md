<!--
Maintainer note: the sibling template carries an equivalent copy of this file
with domain examples adapted (research-core is generic; dl-earth-research is
geoscience). Mirror structural changes -- section headings, self-check items,
cross-reference targets -- across both copies unless a change is genuinely
domain-specific. The duplication is structural: Trellis installs each template
directory as a standalone flat copy into .trellis/spec/, so the two cannot share
a single source file.
-->

# Guide: Write A Results Discussion

Use this when drafting a results discussion, conclusion, paper section, or any
curated write-up under `reports/`.

Read [../shared/scientific-writing.md](../shared/scientific-writing.md) first.
That file holds the rules; this guide is the workflow.

## Steps

1. Write the scientific question in one sentence before any numbers.
2. List the retained evidence that can answer it (run directory or data
   product). If none exists, stop and produce it first; do not draft a claim
   ahead of evidence.
3. Draft the finding in domain language: the effect, its direction, magnitude,
   and the sample set, condition, or simulation setup it applies to.
4. Add the interpretation: candidate mechanisms, uncertainty across seeds,
   folds, or repeats, and the limitations.
5. Place every number with its condition and uncertainty.
6. Move engineering detail (command, config path, run id) to a methods
   paragraph, footnote, or appendix; link to the retained run.
7. Run the self-check in [../shared/scientific-writing.md](../shared/scientific-writing.md).

## Do

```text
reports/sensitivity_summary.md     # curated discussion + figures
outputs/<run_id>/manifest.json     # evidence the discussion links to
```

A reader of `reports/sensitivity_summary.md` should understand the finding
without opening the run directory; a reviewer who wants to verify can follow
the link to the retained run.

## Do Not

```text
reports/raw_metrics_dump.md
reports/run_log.md
discussion that opens with "a retained run was executed and metrics.json was produced"
```

## Smoke Vs Result

If only a smoke check ran, write "smoke check passed; no result is claimed",
not a discussion. Promote the run to retained before any claim, following
[../shared/reproducibility.md](../shared/reproducibility.md).

## Task Completion And Claim Review

A completed Trellis task does not approve a scientific claim. Before using a
claim in a manuscript or external release, the researcher reviews the retained
evidence, the conditions it covers, its uncertainty, and its limitations.

## Completion Checklist

- [ ] The write-up opens with the scientific question or finding.
- [ ] Every claim links to retained evidence.
- [ ] Manuscript or external claims have been reviewed by the researcher at the
      scope and strength supported by that evidence.
- [ ] Engineering terms live in methods, footnotes, or appendix, not in the
      narrative.
- [ ] The self-check in `scientific-writing.md` passes.
