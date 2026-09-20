# Research Workflow

Work directly under the `shared/research-minimal.md` rules, using Trellis to
preserve research context across sessions, coordinate independent
deliverables, or keep a task record when the user asks. Seeds, folds,
parameter variants, and single commands are runs within one scientific
question, not separate tasks.

## Trellis Interface

Keep the six state blocks and numbered phase entries for Trellis 0.7 context
lookups. They describe work, not approval gates.

```bash
python3 ./.trellis/scripts/task.py create "<title>" --slug <name>
python3 ./.trellis/scripts/task.py start <name>
python3 ./.trellis/scripts/task.py current --source
python3 ./.trellis/scripts/task.py finish
python3 ./.trellis/scripts/task.py archive <name>
```

## Phase Index

If `shared/research-minimal.md` is not already in context, start from it
plus the project's data conventions, environment, and entrypoints; other
guides answer concrete questions. Keep a task record when it helps future
work: keep question, inputs, comparison, and current state in prd.md, plan
the comparison, do the work, and record observations once in result.md or
an existing record, not in multiple logs, manifests, or reports. Sub-agents
are optional helpers for bounded independent work; the main agent owns the
result, and reviewer agents are not a completion requirement.

- Before pausing or handing off, update the existing task record with completed and unverified work, the next action, and key decisions. For ongoing computations, include the host, job identifier, and log or output paths; verify their current state before restarting work.
- Split a task when a question or deliverable can be assessed independently, and note dependencies. Keep seeds, folds, and parameter variants together unless they need independent delivery; do not create extra files or task levels merely to represent the split.
- When delegating, specify the objective, edit scope, output locations, and completion criteria. Avoid overlapping writes and coordinate shared compute use. The main agent integrates the deliverables and checks the evidence needed to support the result.

[workflow-state:no_task]
Work under the minimal research rules and relevant project facts. Create a
task only for persistent context, independent deliverables, or an explicit
request.
[/workflow-state:no_task]

[workflow-state:planning]
Keep question, inputs, comparison, and current plan in prd.md. Proceed when
the requested work is clear; no extra approval stages.
[/workflow-state:planning]

[workflow-state:planning-inline]
Keep question, inputs, comparison, and current plan in prd.md. Proceed when
the requested work is clear; no extra context files.
[/workflow-state:planning-inline]

[workflow-state:in_progress]
Read prd.md; work under the minimal research rules. Complete the planned
runs, use their outputs as evidence, and record the result once.
[/workflow-state:in_progress]

[workflow-state:in_progress-inline]
Read prd.md; work under the minimal research rules. Complete the planned
runs and record the result once.
[/workflow-state:in_progress-inline]

[workflow-state:completed]
Report the observations and evidence locations. Archive or journal only when
useful.
[/workflow-state:completed]

## Phase 1: Plan

#### 1.0 Decide whether a task record is useful
Small work proceeds without a task. Reuse an existing task for the same question.

#### 1.1 Write the minimum plan
Record what is needed to work. Ask only about missing decisions that change
the question, implementation, cost, or external effect.

#### 1.2 Research when needed
Investigate a specific unknown; retain findings useful beyond this session.

#### 1.3 Load relevant context
Have the minimal research rules and relevant project facts in context;
other guides are references for concrete questions.

#### 1.4 Start work
Run `task.py start <name>` for a recorded task when its plan is sufficient.

#### 1.5 Ready condition
The next action and the inputs and outputs it needs are clear.

## Phase 2: Do The Work

#### 2.1 Implement or write
Use existing code or direct scripts and notebooks. Add structure only to
simplify the current calculation. Pure writing tasks need no executable code;
research-facing prose follows `shared/scientific-writing.md`.

#### 2.2 Use the result as evidence
Run the comparisons, seeds, and folds the question needs, and check
scientific assumptions that could silently change the result once at their
relevant boundary, using these same runs. Diagnose actual errors; the focused
checks the work needs are part of the work. For prose, inspect the content
and its sources.

#### 2.3 Record the result
Link the actual commands, settings, inputs, and outputs. State observations
and limits that affect interpretation. Negative and null results are
findings; they do not cancel the remaining planned runs.

## Phase 3: Finish

#### 3.1 Keep useful findings
Preserve a finding only when future work needs it; no mandatory journal.

#### 3.2 Update project knowledge when needed
Record reusable conventions or decisions in one existing location; an
isolated run does not create a new spec rule.

#### 3.3 Preserve work with Git
Inspect the diff and preserve unrelated work. Never discard changes or
rewrite history; push and PR actions follow the user's request.

#### 3.4 Finish
Report what was done with its evidence, then stop. Completing a task does
not declare results final or exploration finished.
