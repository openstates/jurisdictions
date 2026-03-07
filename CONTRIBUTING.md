# Contributing to OpenStates Jurisdictions

Thanks for contributing.

This repository stores and generates Division and Jurisdiction YAML data for US
local governments.

## Before You Start
1. Check for an existing issue related to your change.
2. If no issue exists, open one describing the problem and proposed approach.
3. Follow the AGENTS.md and ai_tools/system/contributor-workflows.instruction.md
   when making code changes.

## Local Setup
See `README.md` for full setup instructions. Quick commands:

```sh
uv venv .venv
source .venv/bin/activate
uv sync --all-extras
```

## Making Changes
1. Keep changes focused and small.
2. Add or update tests for code changes.
3. Keep model contract changes in `src/models/` explicit and discussed with maintainers.
4. Use `src` package-root imports (for example `from src.models.division import Division`).

## Validation Before PR
Run the checks below before opening or updating a PR:

```sh
uv run ruff check .
uv run pytest -m "not integration and not slow"
```

If your change affects cross-module behavior, pipeline orchestration, or output
artifacts, also run relevant integration tests.

For the full checklist, see `ai_tools/system/pre-commit-checks.instruction.md`.

## Documentation Expectations
When behavior or workflows change:
1. Update `README.md` if setup/run guidance changed.
2. Update this file (`CONTRIBUTING.md`) if contributor process changed.
3. Update `AGENTS.md` and `ai_tools/` assets if agent workflow changed.
4. Record breaking changes in `CHANGELOG.md`.

## Pull Request Guidelines
Include the following in your PR:
1. Linked issue.
2. Summary of what changed and why.
3. Tests and validation commands run.
4. Notes on data/output impact (for example `divisions/`, `jurisdictions/`).

## Where to Put Docs
- Human-facing documentation belongs in `docs/`.
- Agent-facing instructions belong in `AGENTS.md` and `ai_tools/`.

## Questions
Open an issue and tag maintainers if you are unsure about scope, data modeling,
or output conventions.