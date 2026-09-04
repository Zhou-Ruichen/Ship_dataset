# Project Layout

Follow the repository's documented layout. For a new project, create only the
directories the current work uses. An exploratory analysis may remain in a
script or notebook; it does not need a package, configuration system, test
directory, or command-line wrapper.

Use the project's existing names for source code, scripts, notebooks, data,
outputs, and reports. Extract a module only to simplify the current work or meet
an explicit maintenance need. Keep experiment differences in parameters when that is
enough; do not copy scripts to represent variants.

Record evidence where the project already records it. A useful record normally
includes the command or parameters, the input data and conditions, the observed
result, relevant units, and paths to logs or products. Existing logs, configs,
notebooks, and `result.md` files can be that record. Keep temporary outputs
separate from evidence that supports a result, using the project's own naming
and location conventions; no output relocation is required.

Use lower-case ASCII paths where practical. Keep one maintained filename for
current source code instead of adding `v2`, `final`, or backup copies. Ignore
large generated artifacts according to the repository's existing Git rules.
