# Guide: Add A Run

Use for a new analysis, simulation, model, ablation, training run,
data-processing step, or evaluation.

1. State the scientific question and the minimal comparison that answers it.
2. Find the project's existing entrypoint, config, data, result record, and
   checkpoints; reuse that path and express the difference with parameters
   or config values.
3. Run the cases, seeds, or folds the question needs under matched
   conditions, with data isolation and units explicit.
4. Record the actual command or settings, observed results including
   negative ones, limitations, and output paths in the project's existing
   record.

Repeated seeds or configs are runs within one comparison, not separate
Trellis tasks.
