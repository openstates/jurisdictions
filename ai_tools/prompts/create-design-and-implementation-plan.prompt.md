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
1. A design document in `docs/plans/YYYY-MM-DD-<topic>-design.md`.
2. An implementation plan in `docs/plans/YYYY-MM-DD-<topic>-implementation.md`.

Requirements:
- Include goals, constraints, architecture, data flow, risks, and acceptance criteria.
- Break implementation into small tasks with explicit verification gates.
- List test commands and affected modules.
- Reference related docs and prior plans when available.
