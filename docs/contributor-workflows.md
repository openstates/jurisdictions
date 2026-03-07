# Contributor Workflows

This document defines the expected human + agent workflow for this repository.

## Standard Flow
1. Link work to an issue (create one if missing).
2. Write a design doc for non-trivial changes in `docs/plans/`.
3. Write an implementation plan in `docs/plans/`.
4. Implement in small, testable tasks.
5. Run targeted tests and lint checks.
6. Update docs for behavior, runbooks, and follow-ups.

## Agent Asset Discovery
- Start from `AGENTS.md` for authoritative rules.
- Use `ai_tools/catalog.yaml` to discover active prompt/instruction assets.
- Prefer feature-specific instructions in `ai_tools/planning/` for Stage 1 and Stage 2 work.

## Review Expectations
- PRs should include links to design + implementation docs when required.
- PRs should include tests executed and affected output directories.
- PRs should mention any quarantine artifacts or data quality risks.
