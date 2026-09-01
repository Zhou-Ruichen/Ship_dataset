# Research Workflow

Use Trellis as a small research record. Ordinary work proceeds directly;
Trellis files exist only when they preserve a question, decision, or result.

## Working Rules

1. Create a Trellis task only when work must survive sessions, has independent
   deliverables, involves collaboration, or the user asks for a task record.
2. Exploratory work is the default. Write the smallest code or prose that
   answers the research question.
3. Validate external data once where it enters the project. Add further checks
   only for a concrete failure that would change the result or next action.
4. Run every comparison, seed, fold, or repeat required by the scientific
   question. Do not repeat an identical successful command only for reassurance.
5. Reuse existing code before adding files or abstractions. Once the replacement
   has been checked, remove tracked code that the current task replaces; preserve
   data, result evidence, untracked files, and unrelated suspected-dead code
   unless the user requests cleanup.
6. Sub-agents are optional. Use them only when separate context or parallel work
   helps the task. A handoff includes the task's prd.md decision and the
   constraints of `shared/research-minimal.md`; review sub-agent output against
   that record, not against a generic production checklist.

## Trellis 0.7 Interface

The six `[workflow-state:*]` blocks and their matching close tags are consumed
by Trellis 0.7. Task commands remain the stock CLI:

```bash
python3 ./.trellis/scripts/task.py create "<title>" --slug <name>
python3 ./.trellis/scripts/task.py start <name>
python3 ./.trellis/scripts/task.py current --source
python3 ./.trellis/scripts/task.py finish
python3 ./.trellis/scripts/task.py archive <name>
```

## Optional Task Record

When a task record is useful:

- `prd.md`: `Mode: exploratory` or `Mode: durable`, followed by the question or
  requested behavior, inputs, outputs, and decision the result can change.
- `research/*.md`: only findings needed after the current session.
- `result.md`: actual commands or evidence, observations, useful output paths,
  and limitations that change interpretation.
- Other task files: only for a real interface, dependency, collaboration, or
  sub-agent context need.

Exploratory mode covers experiments, analysis, and one-off research code.
Durable mode covers code the repository will maintain, such as loaders, shared
processing, and reusable training or evaluation code. Retaining a result does
not make exploratory code durable.

## Phase Index

[workflow-state:no_task]
Work directly. Create a Trellis task only when the work must survive sessions,
has independent deliverables, involves collaboration, or the user asks for one.
[/workflow-state:no_task]

[workflow-state:planning]
Keep the plan in prd.md. Start when the question, inputs, outputs, and next
decision are clear enough to work; Trellis adds no second approval.
[/workflow-state:planning]

[workflow-state:planning-inline]
Keep the plan in prd.md and skip extra context files. Start when the record is
sufficient; Trellis adds no second approval.
[/workflow-state:planning-inline]

[workflow-state:in_progress]
Read prd.md and only relevant specs. Do the requested work and scientifically
required runs, use the same outputs for focused checks, record the result once,
and stop when the question is answered. Commits need no separate approval.
Never discard changes or rewrite history. Push and PR actions follow the user.
[/workflow-state:in_progress]

[workflow-state:in_progress-inline]
Work in the main session. Do the requested work and scientifically required
runs, record the result once, and stop when the question is answered. Commits
need no separate approval. Never discard changes or rewrite history. Push and
PR actions follow the user.
[/workflow-state:in_progress-inline]

[workflow-state:completed]
The recorded result is complete. Archive or journal it only when future work
benefits from that record. Completing the task does not open a sealed
evaluation or freeze the explored configuration; that step follows the
registered decision and the user, per `shared/research-minimal.md`.
[/workflow-state:completed]

## Phase 1: Prepare

#### 1.0 Decide whether a task record is useful

Skip Trellis for small or single-session work. Create one task when a durable
record meets the criteria above.

#### 1.1 Write the minimum plan

Record only what is needed to work without guessing. Ask the user when a missing
decision changes the scientific question, implementation, cost, or external
effect.

#### 1.2 Research when needed

Investigate a specific unresolved question. Save a note only when the finding
must survive the session.

#### 1.3 Load relevant context

Read the smallest relevant spec set. When the installed spec provides
`shared/research-minimal.md`, start exploratory implementation there; otherwise
read the smallest relevant files in the installed spec. Add data or writing
guidance only when applicable.

#### 1.4 Start work

For a recorded task, run `task.py start <name>` when prd.md is sufficient.
Starting records state; it is not an approval step.

#### 1.5 Ready condition

The next action, required inputs, expected output, and scientific decision are
clear enough to proceed.

## Phase 2: Do the Research Work

#### 2.1 Implement or write

Work directly by default. Prepare the smallest implementation or prose needed
for the task. Pure prose tasks do not create or run code.

#### 2.2 Focused check

- Exploratory experiment: execute all runs required by the design. Check input
  fields that affect interpretation, obvious shape/dtype/unit/time errors,
  NaN/Inf, and that observations come from the stated outputs. Do not rerun an
  identical successful command solely for reassurance.
- Durable code: use the narrowest check required by the task and project.
  Trellis does not add lint, type checking, tests, or full-suite runs on its own.
- Scientific prose: compare claims with cited evidence and keep scope and
  uncertainty accurate. Do not manufacture an executable check.
- Documentation or configuration: inspect the changed content and direct
  references. Run commands only when authorized by the task or user.

#### 2.3 Record the result

For a recorded task, write result.md once with the evidence, observation, useful
paths, and only limitations that change interpretation. Task completion does not
approve a claim for publication.

## Phase 3: Preserve What Matters

#### 3.1 Learn from repeated failure

Save a debugging note only when repeated failures reveal a reusable cause.

#### 3.2 Update specs when knowledge is reusable

Update a spec only for a stable interface, confirmed invariant, reusable data
convention, or lesson observed beyond one isolated run.

#### 3.3 Preserve work with Git

Inspect the diff and preserve unrelated work. Normal commits need no separate
approval. Never reset, discard changes, rewrite history, or force-push. Push and
PR creation follow the user's request.

#### 3.4 Finish without ceremony

Archive or journal the task only when future work benefits. Otherwise report the
result and stop.
