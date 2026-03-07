---
id: repo-agent-system
type: instruction
owner: maintainers
status: active
last_updated: 2026-03-07
tags: [system, repo, safety]
---

# Repo Agent System Instruction

Apply this instruction on every task in this repository.

## Precedence
- `AGENTS.md` is authoritative for this repository.
- If this file conflicts with `AGENTS.md`, follow `AGENTS.md`.

## Execution Rules
1. Prefer minimal, targeted changes over broad refactors.
2. Reuse existing modules/utilities before adding new abstractions.
3. Keep model contracts stable unless explicitly authorized.
4. Do not modify `__init__.py` files unless explicitly requested.

## Validation Rules
1. Run targeted tests for touched modules.
2. Run broader tests when changes are substantial.
3. Do not hide test output.
4. Use `uv` commands for Python tooling.

## Delivery Rules
1. Summarize what changed and why.
2. Include verification steps and outcomes.
3. Call out assumptions, blockers, or follow-up actions.
