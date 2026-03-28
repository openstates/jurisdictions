# OpenStates Jurisdictions

This repository stores and generates Division and Jurisdiction YAML data for US
local governments in the OpenStates ecosystem.

## What This Repo Contains
- Source models and pipeline code under `src/`
- Output YAML under:
  - `divisions/<state>/local/`
  - `jurisdictions/<state>/local/`
- Tests under `tests/`
- Human-facing docs under `docs/`

## Requirements
- Python `3.12+`
- [uv](https://github.com/astral-sh/uv)
- macOS/Linux shell examples below (adapt for Windows as needed)

## Quickstart (New Contributor)
1. Clone and enter repo.
```sh
git clone <repo-url>
cd jurisdictions
```

2. Install `uv` (if needed).
```sh
brew install uv
# or
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. Create virtual environment and install dependencies.
```sh
uv venv .venv
source .venv/bin/activate
uv sync --all-extras
```

4. Verify local setup.
```sh
uv run ruff check .
uv run pytest -m "not integration and not slow"
```

## Common Commands
- Full test suite:
```sh
uv run pytest
```

- Fast local test pass:
```sh
uv run pytest -m "not integration and not slow"
```

- Lint:
```sh
uv run ruff check .
```

- Run Stage 1 pipeline:
```sh
uv run python src/init_migration/main.py
uv run python src/init_migration/main.py --state wa,tx,oh --force
```

## Making Code Changes
1. Create a branch for your change.
2. Keep changes focused and add/update tests.
3. Run validation commands before opening a PR.
4. Update docs when behavior or contributor workflow changes.

## Contributing Guidance
- Contributor process and expectations: `CONTRIBUTING.md`
- Agent and semi-autonomous workflow rules: `AGENTS.md`
- Pre-commit checklist: `ai_tools/system/pre-commit-checks.instruction.md`
- UV setup details and migration notes: `docs/setup_uv.md`


## To Review Pull requests from forked repos, reference the pull request #: 
Example: 
`git fetch origin pull/38/head:create-crudl-module` 

## Notes
- Use `src` package-root imports in code and tests.
- Do not modify core model contracts in `src/models/` without maintainer
  approval.

