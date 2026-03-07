---
id: create-design-and-implementation-plan
type: prompt
owner: maintainers
status: active
last_updated: 2026-03-07
tags: [planning, docs]
---

# Context

Use this prompt when preparing non-trivial feature work.

# Prompt

Create two documents for this feature:
1. A design document in `ai_tools/planning/YYYY-MM-DD-<topic>-design.instruction.md`.
2. An implementation plan in `ai_tools/planning/YYYY-MM-DD-<topic>-implementation.instruction.md`.

Requirements:
- Include goals, constraints, architecture, data flow, risks, and acceptance criteria.
- Break implementation into small tasks with explicit verification gates.
- List test commands and affected modules.
- Reference related docs and prior plans when available.
- Each document should include sections for:
  - `overview`
  - `goals and constraints`
  - `verification and tests`
