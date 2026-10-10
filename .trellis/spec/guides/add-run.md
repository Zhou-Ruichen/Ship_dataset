# Guide: Add A Run

Use this guide when a question needs a new calculation, simulation, model
variant, training run, or evaluation.

1. State the question in one sentence.
2. Reuse the project's entrypoint, data, and result location. Change a
   parameter or config value.
3. Run the cases needed for the question. Note a seed, split, or unit when it
   affects the result.
4. Write the result and the command or settings needed to rerun it in the
   existing record. Include a short explanation when it changes how the
   result should be read.

Keep parameter variants together under one question. A task record is
useful when the question must survive a session change, the run is an
independent deliverable, or the user asks for one.
