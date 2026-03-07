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
- Run relevant `pytest` modules for all changed code paths.
- Run integration tests for changes that affect cross-module behavior, pipeline orchestration, external I/O, or persisted artifacts.
- If model-adjacent behavior changed, verify generated YAML still validates against Pydantic contracts.

## Artifact Validation
- Confirm output paths are correct:
  - `divisions/<state>/local/`
  - `jurisdictions/<state>/local/`
- Confirm orphan/quarantine outputs are reproducible when applicable.

## Catalog and Documentation Checks
- If any instruction, prompt, planning guide, or skill is added/changed in `ai_tools/`, update `ai_tools/catalog.yaml` in the same change.
- Update related documentation when behavior/workflow changes. This includes
  asking permission to remove documentation that is no longer relevant.
- Review `CONTRIBUTING.md` and update it when contributor process expectations
  changed.
- Record breaking changes and migrations clearly in `CHANGELOG.md`.
