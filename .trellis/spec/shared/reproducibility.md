# Reproducibility

For a number that matters, keep the shortest record that lets someone rerun
the calculation: the input or data version, code revision, command or
notebook, parameters, relevant seed, and an environment pointer. Put the
number, units, and a short condition in the existing result file, notebook, or
lab record. Reuse the project's existing record.

Use an existing lockfile, container digest, environment note, or immutable
source reference when one exists. Record per-run environment details when
the environment can drift and change the number. Record a seed when
randomness affects the result.

Keep large data, logs, checkpoints, figures, predictions, and intermediate
files outside Git by default. Store a path, URL, object key, or checksum when
the file is needed to rerun or interpret the number. Keep a copy when the
external location is not stable or the number cannot otherwise be checked.

If a later run changes the input, method, parameter, or metric, write the new
values beside the new number and keep the earlier number unchanged. Pair every
reported number with its conditions; command success is an execution detail.
