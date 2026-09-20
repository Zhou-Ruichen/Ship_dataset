# Scientific Writing

Use for manuscripts, abstracts, reviewer responses, captions, and
research-facing reports; routine task updates need no manuscript workflow.

## Main Claim

A paper answers one question with one main claim; every section, figure,
and comparison serves it. Choose comparisons because they test the claim
and report each planned one as an observation, including those the
method loses. Do not add comparisons to win every metric, or passages
rebutting objections that no reviewer or result has raised.

## Findings And Evidence

Organize Results and Discussion as finding, evidence, and interpretation:
what data were used, what was compared, what stayed the same, what changed,
and the observed result. Do not substitute internal experiment names or
software completion status for the finding.

Place numbers with their units, data scope, split, or experimental
condition. Report uncertainty when the conclusion depends on it; a single
run does not establish a distribution. Negative and null results receive the
same treatment.

State a mechanism as a finding only when the evidence tests it; otherwise
identify it as an explanation or hypothesis. Do not invent results,
citations, versions, or implications, and cite the source that actually
supports the claim. State a limitation next to the claim it weakens, in
the terms of the evidence ("observed only on dataset D"). A scope
statement says what was studied; a disclaimer denies a claim nobody made,
and is cut. Do not repeat a minor limitation across sections or add
hypothetical concerns. Preserve the author's intended certainty when
editing, and flag suspected scientific errors instead of silently
changing them.

## Methods

Describe data, comparison design, processing, settings, software, and
analysis in the order needed to reproduce the work, using exact technical
terms. Keep necessary commands, equations, and implementation details;
Methods need not follow the finding-first order of Results. Reference
existing evidence records without requiring a new file format.

Methods describe what a reader needs to reproduce or obtain the work; how
code was pushed, checked, or hosted appears only when it affects
reproduction. Commit hashes, run identifiers, and links go in a footnote
or table, outside the sentence.

## Figures And Tables

Captions explain what is shown, on which data, and under which conditions,
with axes and units in domain terms. Result figures state the finding they
support; coverage or method figures need not claim a result. Comparisons
make clear which scientific question they address.

## Language

Write directly in the requested language and register, using one term for
one concept. Say what a thing is in one direct sentence, and state a
claim in one step ("X does Y") instead of routing it through a second
noun ("X is a mechanism; this mechanism ...", "X 是一种机制，该机制……").
Use a negation only to correct a specific misreading a reader could draw
from the reported result; a chain of what something is not ("不是 A，
不是 B，也不是 C") does not define it.

Use only terms established in the field or defined in the manuscript; do
not coin a term or capitalize a concept. If the workflow labels something
a run or task, describe it by its content: the data, settings, method,
and result. Workflow words such as 冻结/freeze, 基线/baseline,
协议/protocol, pipeline, manifest, retained or promoted run, and dry run
are replaced by the concrete action or object: which settings were fixed
and when, which named method or run is the reference, which data, split,
and metric were used. Such a word stays only when it names a published
method or standard ("the ResNet-50 baseline", "the CONSORT protocol").

Avoid filler such as "it is worth noting", "not just X but Y", "本质上",
"底层逻辑", and "不是 X，而是 Y". Do not replace evidence with praise for
the method or manufacture a three-part list. For example, "代码运行成功，
因此方法有效" confuses execution with a scientific finding; state the
observed comparison instead. Judge each sentence by whether it names its
referent.

One sentence carries one fact, reason, procedure, or qualification; split
a sentence that nests more than one qualification. Parallel parts use the
same heading form. Do not add a closing paragraph that repeats the
answer. Preserve quotations and established technical names; code and
identifiers follow the project's language conventions. Apply these rules
by reading; do not add a checker script to the project.
