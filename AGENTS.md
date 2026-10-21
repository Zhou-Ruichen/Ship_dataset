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

# Research Work

Follow `.trellis/workflows/research.md` (research workflow) and the shared guidelines in
`.trellis/spec/shared/research-minimal.md`. Work directly: do not invoke the
native Trellis planning, check, or finish-work skills automatically; use the
task CLI only when a durable task record is useful. Use other specs under
`.trellis/spec/` for concrete coding questions. Run software verification
(tests, builds) only when explicitly requested. Preserve the data-product
definitions, source records, units, release boundaries and downstream
interfaces described in the project documents.

## Python execution convention: run from repo root

All Python entry points in this repo (pipeline steps under `jamstec/multibeam/code/`, the processing packages `ncei/trackline/` and `ncei/swath/`, analyses under `*/analysis/`, the downloader under `ncei/download/`, calibration drivers and tests under `_common/`) are invoked from the **repo root** (`/mnt/data2/00-Data/ship/`), so relative input/output paths resolve against the repo.

Two invocation forms behave differently with respect to imports:

- **`python <script.py>`**: `sys.path[0]` is the script's own directory, not the repo root. Scripts that import `_common` therefore bootstrap the repo root themselves:
  ```python
  REPO_ROOT = Path(__file__).resolve().parents[N]
  sys.path.insert(0, str(REPO_ROOT))
  ```
  No `PYTHONPATH` or install step is needed.
- **Packages and tests** use `python -m` from the repo root (cwd is on `sys.path` for `-m`):
  ```bash
  python -m ncei.trackline 02 --run-label sample --sample-n-files 5
  python -m ncei.swath extract --cruises AR15 AR40        # round-2 swath chain
  python -m ncei.download verify --work /tmp/tierB_gapfill
  python -m unittest _common.tests.test_r2_classifier
  pytest _common/tests/                                   # if pytest is installed
  ```

The alternative — packaging `_common/` via `pyproject.toml` + `pip install -e .` — was considered and deferred. Current single-user / single-machine setup doesn't benefit from it, and the convention above costs zero infrastructure.

If a script errors with `ModuleNotFoundError: No module named '_common'`, its repo-root bootstrap lines are missing or wrong — check `REPO_ROOT = Path(__file__).resolve().parents[N]` (N must match the script's directory depth).

**Warning — not every legacy script has argparse.** The processing packages
guard the formerly argument-free stages (`python -m ncei.trackline 31` and
`python -m ncei.swath 33`, `36`, `37`) with an empty argument parser so `--help`
never starts processing. The frozen
legacy downloader scripts in `ncei/code/` are separate from these package
commands. Before running an unfamiliar legacy script, confirm it has an
`argparse` parser and an `if __name__ == "__main__"` guard. To check that a
module merely imports, execute it from `/tmp` with `python -I` and `importlib`
so that no repo-relative outputs are reachable.
