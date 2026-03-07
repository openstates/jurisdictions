---
id: agent-permissions
type: instruction
owner: maintainers
status: draft
last_updated: 2026-03-07
tags: [system, safety, permissions]
---

# Agent Permissions: Whitelist and Blacklist

Defines actions agents may take autonomously (whitelist) vs. actions that require explicit human approval (blacklist). This file is subordinate to `AGENTS.md` — if there is a conflict, follow `AGENTS.md`.

## Guiding Principles

1. **Reversibility** — autonomous actions must be locally reversible without data loss.
2. **Blast radius** — actions affecting shared state, downstream consumers, or output artifacts require human approval.
3. **Contract stability** — anything that could change the shape of data contracts or output schemas is blacklisted.
4. **Transparency** — when in doubt, ask. The cost of a confirmation prompt is low; the cost of corrupted civic data is high.

---

## Whitelist (Autonomous — No Human Approval Required)

### Reading and Exploration
- Read any file in the repository.
- Read-only git operations (`git status`, `git log`, `git diff`, `git branch --list`).
- Search files with grep/glob/find patterns.
- Inspect DuckDB tables or CSV artifacts in `data/` (read-only).

### Testing and Validation
- Run full test suite: `uv run pytest`.
- Run scoped tests: `uv run pytest <path>` or `uv run pytest -m "not integration and not slow"`.
- Run linter: `uv run ruff check .`.
- Run type checks or other static analysis tools already configured.
- Add or modify test files under `tests/` that mirror source paths.
- Add sample data or fixtures under `tests/sample_data/` or `tests/sample_output/`.

### Implementation (Non-Contract Code)
- Edit pipeline code in `src/init_migration/` (non-model files).
- Edit utility code in `src/utils/`.
- Create or edit files under `ai_tools/` (instructions, prompts, planning docs, skills).
- Update `ai_tools/catalog.yaml` to reflect `ai_tools/` changes.
- Add or edit documentation in `docs/` (design docs, guides).
- Create new source files when implementing an approved feature.

### Pipeline Execution (Scoped)
- Run Stage 1 pipeline for specific states: `uv run python src/init_migration/main.py --state <abbrev>`.
- Run Stage 2 generation for specific states when output can be diffed and reviewed.

### Git (Local, Feature Branches Only)
- Create local branches.
- Stage specific files by name (`git add <file>`).
- Commit changes on feature branches (`git commit`). Do not commit on `main`.

### Environment
- Install/sync dependencies: `uv sync --all-extras`.
- Run any `uv run` command for tooling already in `pyproject.toml`.

---

## Blacklist (Human-in-the-Loop — Requires Explicit Approval)

### Data Contracts and Models
- Modify any file in `src/models/` (`division.py`, `jurisdiction.py`, `ocdid.py`, `source.py`).
- Change Pydantic model field names, types, validators, or serialization behavior.
- Alter the OCD ID format.
- Change the Jurisdiction OCD ID schema (`ocd-jurisdiction/<division_id>/<classification>`).

### Output Artifacts
- Delete, rename, or bulk-modify YAML files in `divisions/` or `jurisdictions/`.
- Change output directory structure or path conventions.
- Modify quarantine/orphan output formats or locations.

### Git (Write Operations)
- Commit on `main` or any shared/protected branch.
- Push to any remote (`git push`).
- Force-push (`git push --force` or `--force-with-lease`).
- Merge or rebase branches.
- Delete branches (local or remote).
- Amend commits (`git commit --amend`).
- Reset history (`git reset --hard`, `git checkout .`, `git restore .`).
- Tag releases (`git tag`).

### GitHub and External Services
- Create, update, or close pull requests.
- Create, update, or close issues.
- Comment on PRs or issues.
- Trigger CI/CD workflows.
- Interact with any external API beyond the OCD ID data sources used by the pipeline.

### Pipeline Execution (Broad Scope)
- Run Stage 1 pipeline for all states (`--state` omitted or set to all).
- Run any pipeline operation with `--force` flag on broad scope.
- Modify pipeline CLI argument defaults or behavior in `main.py`.

### Project Configuration
- Modify `pyproject.toml` (dependencies, build config, tool settings, markers).
- Modify `conftest.py` shared fixtures that affect the entire test suite.
- Change pytest markers or test configuration.
- Modify `.github/` workflows or CI/CD configuration.
- Modify `AGENTS.md`, `CLAUDE.md`, or this permissions file.

### Destructive Operations
- Delete any non-test source file.
- Run `rm -rf` or equivalent on any directory.
- Drop DuckDB tables or delete database files.
- Overwrite uncommitted changes.
- Kill running processes.

### Security-Sensitive
- Modify or create `.env`, credential files, or secrets.
- Change authentication or API key handling.
- Install packages not already in `pyproject.toml` dependencies.

---

## Gray Area — Use Judgment, Prefer Asking

These actions are situationally autonomous but should default to asking when uncertain:

| Action | Autonomous When | Ask When |
|--------|----------------|----------|
| Edit `__init__.py` | Never autonomous | Always ask (per AGENTS.md) |
| Modify shared test fixtures in `conftest.py` | Fixing a broken fixture you introduced | Changing fixtures others depend on |
| Run integration/slow tests | Explicitly working on integration code | Exploratory or uncertain scope |
| Rename functions/variables in pipeline code | Isolated rename within a single module | Rename spans multiple modules or is exported |
| Add new dependencies | Never autonomous | Always ask |
| Modify logging configuration | Adding structured log fields | Changing log levels or output format |

---

## Escalation Protocol

When an action falls on the blacklist or in the gray area:

1. State what you intend to do and why.
2. Describe the blast radius (what could be affected).
3. Wait for explicit approval before proceeding.
4. After completing the action, summarize what changed.
