---
id: feature-delivery-task
type: instruction
owner: maintainers
status: active
last_updated: 2026-03-07
tags: [workflow, execution]
---

# Feature Delivery Instruction

Use this instruction when implementing non-trivial repository changes.

## Workflow
1. Confirm or create the linked issue.
2. Write a design doc in `docs/plans/`.
3. Write an implementation plan in `docs/plans/`.
4. Implement in small, testable tasks.
5. Run targeted tests and lint checks.
6. Document outcomes and follow-ups.

## Required Checks
- Use model contracts from `src/models/` as stable interfaces.
- Validate output shape and path conventions for YAML artifacts.
- Ensure test file paths mirror source module paths.
