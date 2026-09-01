# Guide: Research Code Review

Review the change against the task, not against a generic production checklist.

## Behavior And Evidence

- The code addresses the requested behavior or observed failure.
- External data assumptions that affect the result are explicit at the boundary.
- Result claims point to the command, inputs, parameters, environment record,
  outputs, and assumptions that support them.
- Errors are not hidden by fallback branches, swallowed exceptions, or fake
  success messages.

## Repository Maintenance

- Existing code was reused when it already owned the behavior.
- Variants are parameters, configs, or commands rather than copied scripts.
- New shared code corresponds to repeated durable logic, not possible future use.
- Tracked code replaced by this task was removed. Research evidence, data,
  untracked files, and unrelated suspected-dead code were preserved.

## Checks

Use only checks authorized by the task, project, or user. Record what was checked
or state that no executable verification was requested. Scientific metric values
are observations, not software pass/fail thresholds.
