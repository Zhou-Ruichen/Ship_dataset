# Research Workflow

Work directly. Use Trellis only to preserve research context across sessions or
coordinate independent deliverables, or when the user asks for a task record.
Seeds, folds, parameter variants, and individual commands are runs within a
scientific question, not separate tasks by default.

## Context And Records

Start with `shared/research-minimal.md` when present and the project's actual
data conventions, environment, and entrypoints. Read other specs only to answer
a concrete question; writing a file or reading data does not trigger every guide.

For a recorded task, keep the question, inputs, planned comparison, and current
state in prd.md. No mode or run-tier declaration is required. Record observations
and evidence locations in result.md, or link to an existing record. Do not copy
the same results into multiple logs, manifests, journals, and reports.

Sub-agents are optional. Work in the main session by default; delegate bounded,
independent work when parallel execution or separate context helps. Pass the
question, task constraints, minimal research rules, and expected output. The
main agent owns the result; reviewer agents are not a completion requirement.

## Trellis Interface

Keep the six state blocks and numbered phase entries for Trellis 0.7 context
lookups. They describe work, not additional approval or verification gates.

```bash
python3 ./.trellis/scripts/task.py create "<title>" --slug <name>
python3 ./.trellis/scripts/task.py start <name>
python3 ./.trellis/scripts/task.py current --source
python3 ./.trellis/scripts/task.py finish
python3 ./.trellis/scripts/task.py archive <name>
```

## Phase Index

Work directly using the minimal research rules. Keep a task record when it
helps future work. For recorded tasks: plan the comparison, do the work, and
record the observations once. Load individual steps only when needed.

[workflow-state:no_task]
Work directly using the minimal research rules and relevant project facts.
Create a task only for persistent context, independent deliverables, or an
explicit request. No default tests, reviewer agents, or extra scaffolding.
[/workflow-state:no_task]

[workflow-state:planning]
Keep the question, inputs, comparison, and current plan in prd.md. Proceed when
the requested work is clear; do not add approval stages or scientific thresholds.
[/workflow-state:planning]

[workflow-state:planning-inline]
Keep the question, inputs, comparison, and current plan in prd.md. Proceed when
the requested work is clear; no extra context files or approval stages.
[/workflow-state:planning-inline]

[workflow-state:in_progress]
Read prd.md and the minimal research rules. Work directly for the stated inputs;
do not add code for hypothetical failures. Complete the planned runs, use their
outputs as evidence, and record the result once. Additional software verification
requires an explicit request. No automatic check agent or repeated review.
[/workflow-state:in_progress]

[workflow-state:in_progress-inline]
Read prd.md and the minimal research rules. Work in the main session for the
stated inputs. Complete the planned runs and record the result once. No code for
hypothetical failures, unrequested software verification, or automatic check agent.
[/workflow-state:in_progress-inline]

[workflow-state:completed]
Report the observations and evidence locations. Archive or journal only when
useful. Task completion does not authorize opening a sealed final evaluation or
declaring exploration finished.
[/workflow-state:completed]

## Phase 1: Plan

#### 1.0 Decide whether a task record is useful
Small work proceeds without a task. Reuse an existing task for the same question.

#### 1.1 Write the minimum plan
Record what is needed to work. Ask only about missing decisions that change the
question, implementation, cost, or external effect.

#### 1.2 Research when needed
Investigate a specific unknown; retain only findings useful beyond this session.

#### 1.3 Load relevant context
Read minimal research rules and relevant project facts; other guides are references.

#### 1.4 Start work
Run `task.py start <name>` for a recorded task when its plan is sufficient.

#### 1.5 Ready condition
The next action and the inputs and outputs it needs are clear.

## Phase 2: Do The Work

#### 2.1 Implement or write
Use existing code or direct scripts. Add structure only to simplify the current
calculation. Pure writing tasks need no executable code.

#### 2.2 Use the result as evidence
Run the comparisons, seeds, and folds the question needs. Check scientific
assumptions that could silently change the result using those same inputs and
outputs. Diagnose actual errors; do not add tests, lint, builds, type checking,
or a `trellis-check` invocation without an explicit task or user request.
For prose or configuration, inspect the content and its sources.

#### 2.3 Record the result
Link to the actual commands, settings, inputs, and outputs. State observations
and limits that affect interpretation. Negative or null results do not cancel
the remaining planned runs; changing that plan follows the user.

## Phase 3: Finish

#### 3.1 Keep useful findings
Preserve a finding only when future work needs it; no mandatory debugging journal.

#### 3.2 Update project knowledge when needed
Record reusable scientific conventions or decisions in one existing location.
Do not turn an isolated run or every code change into a new spec rule.

#### 3.3 Preserve work with Git
Inspect the diff and preserve unrelated work. Normal commits need no separate
approval; never discard changes or rewrite history. Push and PR actions follow
the user's request.

#### 3.4 Finish
Report what was done and stop. Opening sealed evaluation data or declaring the
explored configuration final requires the user's confirmation. Fixing parameters
for one planned comparison does not itself end exploration.
