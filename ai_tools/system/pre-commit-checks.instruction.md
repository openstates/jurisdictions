---
id: pre-commit-checks
type: instruction
owner: maintainers
status: active
last_updated: 2026-03-07
tags: [system, validation, pre-commit]
---

# Pre-Commit Checks

Run this checklist before opening or updating a pull request.

## Required Commands
```bash
uv run ruff check .
uv run pytest -m "not integration and not slow"
```

## Change-Scoped Validation
- If Stage 1 files changed, run relevant tests under `tests/src/init_migration/` and downloader test modules.
- If Stage 2 files changed, run relevant tests under `tests/src/init_migration/` for generation pipeline behavior.
- If model-adjacent behavior changed, verify generated YAML still validates against Pydantic contracts.

## Artifact Validation
- Confirm output paths are correct:
  - `divisions/<state>/local/`
  - `jurisdictions/<state>/local/`
- Confirm orphan/quarantine outputs are reproducible when applicable.

## Catalog and Documentation Checks
- If any instruction, prompt, planning guide, or skill is added/changed in `ai_tools/`, update `ai_tools/catalog.yaml` in the same change.
- Update related documentation when behavior/workflow changes.
- Review `CONTRIBUTING.md` and update it when contributor process expectations changed.
