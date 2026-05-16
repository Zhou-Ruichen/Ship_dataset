<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->

## Python execution convention: run from repo root

All Python scripts in this repo (pipeline steps under `jamstec/multibeam/code/`, future `ncei/code/`, calibration drivers and tests under `_common/`) are invoked from the **repo root** (`/mnt/data2/00-Data/ship/`). That puts cwd on `sys.path`, so any consumer can write `from _common.r2_classifier import classify` with no per-script `sys.path.insert(...)` hack and no `PYTHONPATH` plumbing.

The alternative — packaging `_common/` via `pyproject.toml` + `pip install -e .` — was considered and deferred. Current single-user / single-machine setup doesn't benefit from it, and the convention below costs zero infrastructure.

Invocation pattern:

```bash
# From repo root, NOT from inside any code/ dir:
cd /mnt/data2/00-Data/ship

python jamstec/multibeam/code/03_qc_multibeam_points.py [args...]
python ncei/code/02_standardize_singlebeam.py [args...]            # PR-E and later
python -m _common.r2_calibration [args...]                          # or python _common/r2_calibration.py
```

Unit tests follow the same rule — both runners assume cwd = repo root:

```bash
python -m unittest _common.tests.test_r2_classifier
pytest _common/tests/                                               # if pytest is installed
```

If a script errors with `ModuleNotFoundError: No module named '_common'`, cwd is wrong — `cd /mnt/data2/00-Data/ship` and retry.
