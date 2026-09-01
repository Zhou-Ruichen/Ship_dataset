<!--
Maintainer note: the sibling template carries an equivalent copy of this file.
Mirror structural changes -- section headings, self-check items,
cross-reference targets -- across both copies unless a change is genuinely
domain-specific. The duplication is structural: Trellis installs each template
directory as a standalone flat copy into .trellis/spec/, so the two cannot share
a single source file.
-->

# Scientific Writing

The plain-language rules in this file apply to human-facing project prose,
including reports, papers, methods, captions, README files, documentation, and
task results. The scientific narrative rules apply specifically to results,
discussion, conclusions, and abstracts. Code, configs, manifests, and commit
messages remain engineering artifacts.

The goal: reports and discussions should read as science, not as a build log.

## Read This When

- drafting a results discussion, conclusion, or abstract;
- writing methods text or a paper draft;
- writing figure or table captions and comparison tables for a report;
- producing anything under `reports/`;
- writing a README, project document, notebook explanation, or task result.

Pair this file with the task workflow in
[../guides/write-results.md](../guides/write-results.md).

## Core Principle

For results and discussion, lead with the supported finding and its meaning.
Evidence (numbers, figures, comparisons) supports the claim; it is not the
claim. Other prose should lead with its subject and purpose, not a stock
introduction or a description of the writing process.

## Narrative Order

For any results section or discussion:

1. State the scientific question or the supported finding, whichever reads
   more naturally.
2. State the finding in domain language: the phenomenon, direction, magnitude,
   and conditions where it holds.
3. Give the supporting evidence (metric, figure, comparison) with the sample
   set, condition, split, or simulation setup it applies to.
4. Interpret: what could explain the result, what is uncertain, and what limits
   it. State a mechanism as a finding only when the evidence directly tests it;
   otherwise label it as an explanation or hypothesis.
5. Point to reproducible evidence only as a reference (a methods paragraph, an
   appendix, or a footnote linking to the retained run).

Do not invert this into "we ran X, recorded Y, produced Z".

## Methods

Methods describe data, design, processing, software, parameters, and analysis
in the order needed to understand and reproduce the work. Exact technical terms
are allowed. Do not force Methods into a finding-first Results structure.

## Engineering Term Isolation

Engineering terms belong in code, config, manifest, and commit messages. They
must not appear in scientific prose as if they were findings.

Avoid in results, discussion, conclusions, and abstracts:

- `retained run`, `run_id`, `manifest`, `artifact`, `artifact pipeline`;
- `promotion`, `promote`, `scratch`, `smoke` used as nouns describing results;
- `anti-bloat`;
- `checkpoint` as a result (it is acceptable in methods when it refers to a
  saved model state used for evaluation);
- `ablation` as a standalone result label (describe what was removed and why);
- `pipeline`, `framework`, `harness`, `orchestration` used as vague labels.

Methods may use these terms when they name an actual tool or processing
sequence and the detail is needed for reproduction.

If a reader needs the engineering detail, link it from a methods paragraph or
appendix ("see Supplement; retained evidence under `outputs/...`") and keep the
main text in domain language.

## Anti AI Tone

Prose should read like a researcher explaining the work to a colleague, not like
a model performing competence. Two opposite failure modes both read as
machine-written and are not allowed: mechanical stiffness (the "does not speak
human" failure) and over-ornamentation (the flowery, empty-rhetoric failure).

### Write Like A Human

- Vary sentence length and structure. Do not turn prose into a disguised bullet
  list, and do not open every sentence with a transition adverb ("Furthermore",
  "Moreover", "Additionally", "Consequently") chained in sequence.
- Use real causal connectives ("because", "since", "although", "so") only where
  the logic is causal, not as decoration.
- State the reason directly. "X improved because Y" beats "X exhibited
  substantial improvement, underscoring the importance of Y".
- Do not fake balance: drop "however" or "on the other hand" when there is no
  real tension, and do not pad a point into a rule-of-three to sound thorough.
  Drop "it's not just X, it's Y" / "not only X, but Y" rephrasings of a single
  point.
- Do not use em dashes; use commas, colons, semicolons, or parentheses instead.
- Prefer one concrete sentence over a vague one padded to look comprehensive.

### Over-Ornamentation

Empty flourish inflates without informing. Do not use:

- delve, leverage, harness, unlock, unveil, navigate, illuminate, demystify;
- tapestry, realm, landscape, paradigm, synergy, beacon, testament, frontier;
- myriad, plethora, "a host of", "a wealth of";
- "it is worth noting", "it should be noted", "it is important to note";
- "plays a crucial/pivotal/vital role", "stands as", "at the forefront of";
- "in today's world", "in an increasingly X world", "the ever-evolving X";
- underscore(s), showcasing, intricate, "at its core", "when it comes to",
  load-bearing as filler emphasis.

Each is a signal that a sentence is performing competence instead of stating a
fact. Replace with the concrete observation.

For Chinese prose, use the following repository-local list. Two categories:

- fake insight: "不是 X，而是 Y", "本质上", "底层逻辑", "核心/关键在于", "核心"
  as empty emphasis (as in "核心逻辑"), "真正稳的是", "更稳/最稳", "根因",
  "口径", "深刻/深入" as empty modifiers, "契约" and "派生" outside their
  technical senses, "一语中的";
- formulaic padding: "首先…其次…最后…", "一方面…另一方面…", "不仅…而且…",
  "综上", "值得注意", "全面/全方位", "强大/强健", "无缝/流畅", "尖端/前沿",
  "落盘", "收口", "兜底", "闭环", "一版", "补一刀", "更硬", "痛点", "打通",
  "收窄", "跑一遍", "一句话", "原子", "冒烟测试".

Write plain, factual Chinese that states the action, the object, and the
result directly.

Do not add an empty conclusion merely to sound complete. Phrases such as
"Overall", "Taken together", "These findings highlight", "总体而言", "由此可见",
and "具有重要意义" are acceptable only when the sentence adds a concrete
synthesis, consequence, or supported implication.

### Empty Adjectives And Hollow Comparisons

- robust, scalable, modular, flexible, pivotal, comprehensive, multifaceted,
  seamless, cutting-edge, next-generation, transformative, game-changing;
- state-of-the-art or significant unless a specific comparison or statistical
  test is in the same section;
- "we implemented X module", "we built a pipeline" stated as a finding.

If a word can be deleted without losing information, delete it. Replace each
empty adjective with the concrete statement: what was measured, over what data,
with what uncertainty, compared to what baseline.

## Sentence Leads

Open sentences with the scientific content, not the engineering action.

Bad:

> We ran a retained evaluation and recorded `metrics.json` showing RMSE
> decreased.

Good:

> Root-mean-square error fell to X on the held-out set, consistent with the
> hypothesized mechanism; the supporting run is logged under the project's run
> directory.

## Numbers And Uncertainty

- Report the sample size, split, condition, or simulation setup a number
  applies to.
- Report uncertainty (spread across seeds, folds, repeats, or bootstrap
  samples) when a claim depends on it; a single run is not a distribution.
- Keep units and coordinate conventions explicit.
- Distinguish a smoke check from a reported result. A smoke check is never
  evidence for a claim.
- State a finding at the strength its evidence supports. Report uncertainty
  once, where the evidence is presented; do not re-weaken a supported claim
  with repeated hedges in every section.
- State limitations once, where they actually limit the claim. Do not
  re-list caveats that do not change the conclusion, and do not withhold a
  supported conclusion out of caution.

## Figures And Tables

- Captions are self-contained: they state what is shown, the data and condition,
  and read independently of the body text. A result figure also states the
  finding it supports; a location, coverage, or method figure need not claim a
  result.
- A caption must not be a file path or a variable name.
- Comparison tables must explain why each comparison is scientifically
  meaningful (which hypothesis it separates), not only list metrics.
- Axis labels, legends, and units are explicit. No `y`, `pred`, or `output` as
  a final label.

## Reports Directory

`reports/` holds curated, human-facing material only: a figure, a table, a
short write-up. It must not contain raw logs, full metric dumps, or scratch
output. Every curated item points back to the retained run or data product that
produced it.

## Bilingual Policy

- Code, identifiers, docstrings, comments, filenames, manifests, and commit
  messages stay in English.
- The language of prose (reports, discussions, paper drafts) is a per-project
  choice. Declare it once in the project spec and stay consistent.
- When the prose language is not English, write native prose directly; do not
  translate English sentence by sentence. Keep physical quantities in their
  standard symbols and units and avoid translation-style phrasing.

## Self-Check Before Submitting Prose

- [ ] The section opens with the scientific question or finding, not a run
      description.
- [ ] Any mechanism stated as a finding was directly tested; other mechanisms
      are labeled as explanations or hypotheses.
- [ ] Methods retain the exact data, procedure, software, and parameters needed
      for understanding and reproduction.
- [ ] No engineering terms (`retained run`, `manifest`, `artifact`,
      `promotion`, `run_id`, `scratch`/`smoke`) appear as if they were results.
- [ ] No over-ornamentation (`delve`, `unveil`, `leverage`, `tapestry`,
      `navigate`, `myriad`, "it is worth noting", or the Chinese cliches above) remains.
- [ ] No empty adjectives (`robust`, `scalable`, `seamless`,
      `state-of-the-art` without comparison) remain.
- [ ] No mechanical transition-adverb chains or prose-as-bullet-list; sentence
      structure varies and connectives are causal, not filler.
- [ ] Every number carries its sample set, condition, or split, plus
      uncertainty where it matters.
- [ ] Captions are self-contained and science-oriented.
- [ ] Comparison tables justify why each comparison matters.
- [ ] `reports/` contains only curated material that links back to evidence.
- [ ] Smoke checks are labeled as smoke, not as results.
