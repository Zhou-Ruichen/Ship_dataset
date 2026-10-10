# Keep Research Code Small

Reuse the project's functions, entrypoints, and installed dependencies. Express
an experiment difference as a parameter or config value of the one existing
program; `train.py` with a changed setting takes the place of a `train_v2.py`
copy.

Add a function or module when it removes real duplication or makes the current
calculation easier to rerun. Add a framework, registry, plugin system, CLI
layer, test suite, or compatibility layer for a concrete need. Keep a one-off
check in the script or notebook where it was useful.

Remove a superseded implementation after the replacement works. Keep data
references, reported numbers, settings needed to interpret them, and
unrelated changes. Review the calculation itself when a test suite is absent.
