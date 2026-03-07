---
id: contributor-workflows
type: instruction
owner: maintainers
status: active
last_updated: 2026-03-07
tags: [system, contributors, workflow]
---

# Contributor Workflows

Apply this instruction when preparing or reviewing contributor-facing changes.

## Purpose
- Keep contributor workflows clear, repeatable, and welcoming.
- Ensure agent and human workflows stay aligned with repository policy.

## Standard Flow
1. Link work to an issue (create one if missing).
2. Create an issue-linked branch before making code changes.
3. Use a branch name that includes the issue number and short summary
   (for example `issue-28-replace-loguru-with-logging-module`).
4. For non-trivial changes, create design and implementation planning artifacts.
5. Implement in small, reviewable tasks.
6. Run targeted validation and required checks before PR.
7. Update contributor-facing documentation with behavior/process changes.
8. Code changes should be committed on a branch. Never commit changes directly to
   protected branches (i.e. "main").

## Contributor-Facing Documentation Requirements
1. Keep `CONTRIBUTING.md` current when process expectations change.
2. Keep `AGENTS.md` and `ai_tools/system/*.instruction.md` guidance consistent.
3. Keep `ai_tools/catalog.yaml` synchronized with instruction/prompt/skill additions.
4. Include clear references to runbooks/checklists for verification.

## PR Readiness Expectations
1. PR description includes issue link and scope summary.
2. PR includes tests run and validation commands used.
3. PR calls out changed outputs and any data quality risks.
4. PR notes follow-up work if scope is intentionally partial.

## Agent Asset Discovery
- Start from `AGENTS.md` for authoritative policy.
- Use `ai_tools/catalog.yaml` to locate active instructions and prompts.
- Prefer feature-specific guidance in `ai_tools/planning/` for implementation context.
