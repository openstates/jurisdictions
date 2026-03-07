# Overview
You are helping maintain an open source ETL repository that generates Division and Jurisdiction YAML files for US local governments.

Primary goals:
1. Keep model contracts stable and valid.
2. Make contributor workflows predictable.
3. Make agentic workflows discoverable, repeatable, and safe.

This file is authoritative for agent behavior in this repository.

## Project Context
- Repository purpose: generate Division and Jurisdiction YAML from OCD IDs plus civic research data.
- Ecosystem: OpenStates.
- Data model framework: Pydantic v2.
- Output layout: YAML files organized by state.

## Repository Scope
- Data contracts: `src/models/division.py`, `src/models/jurisdiction.py`, `src/models/ocdid.py`, `src/models/source.py`
- Stage 1 ingestion pipeline: `src/init_migration/main.py`, `src/init_migration/download_manager.py`, `src/init_migration/ocdid_matcher.py`, `src/init_migration/downloader.py`
- Stage 2 generation pipeline: `src/init_migration/generate_pipeline.py`, `src/init_migration/generate_division.py`, `src/init_migration/generate_jurisdiction.py`
- Output data directories: `divisions/<state>/local/`, `jurisdictions/<state>/local/`

## Architecture Map
### Data Models (`src/models/`)
- `division.py`: Division contract, includes government identifiers and linked `jurisdiction_id`.
- `jurisdiction.py`: Jurisdiction contract, includes `ClassificationEnum` and core metadata.
- `source.py`: source/provenance model and source typing.
- `ocdid.py`: parsed OCD ID model.

### Stage 1 (`src/init_migration/`)
- `main.py`: orchestrator + CLI (`--state`, `--force`, `--log-dir`).
- `download_manager.py`: downloads master + state files and loads DuckDB tables.
- `ocdid_matcher.py`: exact matching, orphan classification, deterministic IDs, lookup table persistence.
- `downloader.py`: async HTTP utility (retries, cache validators, GitHub handling).
- `pipeline_models.py`: request/response models used by migration pipeline.

### Stage 2 (`src/init_migration/`)
- `generate_pipeline.py`: orchestrates fuzzy matching and branching decisions.
- `generate_division.py`: builds complete or stub Division objects.
- `generate_jurisdiction.py`: derives Jurisdiction objects from divisions.
- `parsers.py`: CSV bytes to dataframe helpers.

### Utilities (`src/utils/`)
- `ocdid.py`: parse/generate OCD IDs.
- `place_name.py`: normalize Census place names for matching.
- `deterministic_id.py`: `oid1-` deterministic ID generation and decoding.
- `state_lookup.py`: state abbreviation and FIPS lookup.

## Critical Rules
- Do not modify core model schemas in `src/models/` without explicit maintainer approval.
- Do not perform write git operations (commit, push, branch deletion, rebase) unless explicitly authorized.
- Use minimal, targeted changes over broad refactors.
- Reuse existing utilities and patterns before introducing new abstractions.
- Do not add code/content to `__init__.py` files unless explicitly requested.

## Contributor Workflow
When starting work:
1. Check for an existing issue.
2. If none exists, create one before implementation.
3. If using an existing issue, create or checkout a branch tied to that issue.
4. Set issue ownership/status before opening a PR.

## Commands
- Use `uv` for Python tooling.
- Common commands:
  - `uv sync --all-extras`
  - `uv run pytest`
  - `uv run pytest -m "not integration and not slow"`
  - `uv run ruff check .`
  - `uv run python src/init_migration/main.py --state wa,tx,oh --force`
- Do not hide test output.
- For test debugging, prefer deterministic single-worker runs.

## Data and OCD ID Rules
- Division OCD IDs must align with official OCD sources (`country-us.csv` and local state CSVs).
- Jurisdiction OCD ID format:
  - `ocd-jurisdiction/<division_id_without_prefix>/<classification>`
- Master data is source of truth when reconciling local vs national OCD records.
- Deterministic IDs must use:
  - `src/utils/deterministic_id.py`
- Place name normalization and parsing utilities:
  - `src/utils/place_name.py`
  - `src/utils/ocdid.py`

## Key Domain Concepts
- OCD IDs:
  - Division: `ocd-division/...`
  - Jurisdiction: `ocd-jurisdiction/.../<classification>`
- Validation Research CSV: manually researched dataset used during Stage 2 fuzzy matching.
- Quarantine: unmatched or ambiguous records captured for human review.

## YAML Output Rules
- Division YAML location: `divisions/<state>/local/`
- Jurisdiction YAML location: `jurisdictions/<state>/local/`
- Keep filenames deterministic and contributor-friendly.
- Validate generated records against Pydantic models and existing tests.

## Testing Expectations
- Use pytest.
- Mirror source paths in tests (for example `tests/src/init_migration/test_generate_pipeline.py`).
- Mock network boundaries where possible.
- Run targeted tests for changed modules, then broader suite when changes are substantial.
- Async tests should follow repository conventions in `tests/conftest.py`.
- Use markers consistently: `integration`, `slow`, `asyncio`.
- Prefer `respx` for HTTP mocking in downloader/network tests.

## Import Conventions
- Use `src` package-root imports, for example `from src.models.division import Division`.
- Keep imports consistent with existing modules and tests.

## Logging and Error Handling
- Use `loguru` in this repo.
- Prefer structured, contextual logs.
- Log retries and recoverable issues as warnings.
- Log hard failures with enough context to reproduce.

## AI Tooling Layout (Agentic Workflow Standard)
Adopt and maintain an `ai_tools/` directory at repo root for reusable agent assets.

Recommended structure:
- `ai_tools/README.md`: scope, conventions, and usage.
- `ai_tools/catalog.yaml`: indexed registry of active prompts/instructions/skills with owner, status, and tags.
- `ai_tools/system/`: always-on system instructions that can be referenced by this file.
- `ai_tools/tasks/`: task-specific executable instructions.
- `ai_tools/prompts/`: reusable prompts grouped by domain.
- `ai_tools/templates/`: prompt and instruction templates.
- `ai_tools/skills/`: reusable workflow skills when needed.

Conventions:
- Use kebab-case filenames.
- Use clear suffixes: `*.prompt.md`, `*.instruction.md`.
- Include frontmatter in every asset:
  - `id`, `type`, `owner`, `status`, `last_updated`, `tags`.

## Design and Planning Standards
Use the planning pattern already demonstrated in:
- `docs/plans/2026-02-13-stage1-ocdid-pipeline-design.md`
- `docs/plans/2026-02-15-stage1-ocdid-pipeline-implementation.md`

For any non-trivial change:
1. Write a design doc first (`docs/plans/YYYY-MM-DD-<topic>-design.md`).
2. Write an implementation plan with task breakdown and verification gates (`docs/plans/YYYY-MM-DD-<topic>-implementation.md`).
3. Implement in small, testable tasks.
4. Record follow-up decisions in docs.

## Repository Reorganization Plan (For Agentic Workflows)
### Phase 1: Introduce AI tooling scaffolding
- Add `ai_tools/` with `README.md`, `catalog.yaml`, `system/`, `tasks/`, `prompts/`, `templates/`, `skills/`.
- Add starter templates for prompt and instruction assets.
- Add a repo-level always-on instruction file at `ai_tools/system/repo-agent-system.instruction.md`.

### Phase 2: Separate stable standards from task plans
- Keep evergreen standards in:
  - `AGENTS.md`
  - `ai_tools/system/`
- Keep feature-specific plans in:
  - `docs/plans/`
- Keep operational runbooks in a new `docs/runbooks/` directory.

### Phase 3: Standardize workflow artifacts
- For each significant feature:
  - design doc
  - implementation plan
  - execution checklist
  - post-implementation validation notes
- Index active artifacts in `ai_tools/catalog.yaml` and cross-link from plan docs.

### Phase 4: Contributor and reviewer ergonomics
- Add PR template checklist entries for:
  - design doc link
  - implementation plan link
  - tests executed
  - affected outputs (`divisions/`, `jurisdictions/`, `data/`)
- Add `docs/contributor_workflows.md` describing human plus agent collaboration.

### Phase 5: Guardrails for generated data
- Add validation task docs for generated YAML quality checks.
- Add a lightweight pre-PR validation command set in docs.
- Track and quarantine ambiguous records with reproducible artifacts.

## Acceptance Criteria for Reorg
- `ai_tools/` exists with documented conventions and indexed assets.
- `AGENTS.md` remains concise and authoritative.
- New feature work includes both design and implementation plan docs.
- Contributors can discover the right prompt/instruction in under 2 minutes.
- Agent runs produce repeatable outputs with clear audit trails.

## References
- `CLAUDE.md`
- `docs/plans/2026-02-13-stage1-ocdid-pipeline-design.md`
- `docs/plans/2026-02-15-stage1-ocdid-pipeline-implementation.md`
- `docs/deterministic_ids.md`
- `docs/init_research_pipeline.md`
