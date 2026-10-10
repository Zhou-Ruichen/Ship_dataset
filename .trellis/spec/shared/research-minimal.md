# Minimal Research Work

Use these rules for exploratory work. Domain guides add details when a
question needs them.

- Follow the user's question and project rules. Keep work in the main session
  and add task stages, sub-agents, or tests when the question or a
  concrete failure calls for them.
- Reuse existing code or a direct script or notebook. Add structure when
  it makes the current calculation clearer or repeatable. Let ordinary errors
  show their traceback and diagnose the failure where it occurs. See
  [anti-bloat.md](./anti-bloat.md).
- Run the smallest useful calculation or comparison. Add another seed, fold,
  check, or data inspection when it answers the question or prevents a
  likely silent error. A negative, zero, or unexpected result is still an observation.
- An exploratory task reports what was observed. Pass/fail or eligibility
  thresholds (eligible, interesting_signal) and automatic continue-or-stop
  rules belong to a confirmatory protocol the user has asked for.
- Keep the small record needed to reproduce a reported result: input or data
  version, code revision, command or notebook, parameters, relevant seed, and
  an environment pointer. Put the result and its units in the existing result
  record. Keep large data, logs, checkpoints, and intermediate files outside
  the repository by default; record a path, URL, object key, or checksum when
  the data is needed later. See
  [reproducibility.md](./reproducibility.md).
- Describe findings with their actual conditions and limits. Use the field's
  terms and name the concrete data, method, and result. See [scientific-writing.md](./scientific-writing.md).
