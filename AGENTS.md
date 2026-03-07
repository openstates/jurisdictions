# Overview
`jurisdictions` is an open source repository that generates and maintains Division and Jurisdiction YAML for US local governments.

Primary goals:
1. Keep model contracts stable and valid.
2. Make contributor workflows predictable.
3. Make agentic workflows discoverable, repeatable, and safe.

## Instruction Precedence
Use this order of precedence for agent behavior:
1. `AGENTS.md` (authoritative repo policy)
2. `ai_tools/system/*.instruction.md` (always-on reusable guidance)
3. `ai_tools/tasks/*.instruction.md` (task/workflow-specific guidance)
4. `ai_tools/prompts/**/*.prompt.md` (invocation templates)

If there is any conflict, follow `AGENTS.md`.
Always include `=ai_tools/system/contributor-workflows.instruction.md` in
context when instructed to make code changes.

## Canonical Instruction Index
Treat this file as a policy index. Detailed operational guidance lives in:
- Repository execution baseline: `ai_tools/system/repo-agent-system.instruction.md`
- Safety and approval boundaries: `ai_tools/system/agent-permissions.instruction.md`
- Validation checklist: `ai_tools/system/pre-commit-checks.instruction.md`
- Contributor process: `ai_tools/system/contributor-workflows.instruction.md`
- Feature implementation workflow: `ai_tools/tasks/feature-delivery.instruction.md`
- Planning guides: `ai_tools/planning/`
- Prompt templates: `ai_tools/prompts/`
- Asset index: `ai_tools/catalog.yaml`

## Required Instruction Routing
- Before implementation, review `ai_tools/catalog.yaml` and load relevant task/planning assets.
- If a direct task guide exists, use it first.
- If multiple assets match, choose the closest fit and state assumptions (or ask one focused clarifying question).
- If a request maps to prompt-driven planning/review, load the relevant prompt from `ai_tools/prompts/`.

## Repository Scope
- Data contracts: `src/models/division.py`, `src/models/jurisdiction.py`, `src/models/ocdid.py`, `src/models/source.py`
- Output directories: `divisions/<state>/local/`, `jurisdictions/<state>/local/`

## Documentation Rules
- `/docs`: human-facing project documentation (purpose, Open Civic Data context, data provenance, domain explanations).
- `README.md`: setup, install, run, and repository requirements.
- `CONTRIBUTING.md`: contributor process, PR expectations, and workflow guidance.
- `CHANGELOG.md`: release notes and breaking changes.
- `AGENTS.md` + `ai_tools/`: agent-facing operational instructions for semi-autonomous work.
- `ai_tools/planning/`: feature-specific planning, design, and implementation instructions.
- Keep human docs out of `ai_tools/`, and keep agent instruction assets out of `/docs`.

### Open Source Best Practices
- Keep docs close to the workflow they support and update them in the same PR as behavior changes.
- Prefer short, stable docs that link to detailed references instead of duplicating content.
- Record breaking changes and migrations clearly in `CHANGELOG.md`.

## Git Safety and Change Control
- Do not run any remote push command (for example, `git push`, `git push --force`, or `git push --tags`) unless the user has explicitly authorized that push action.
- Read-only git operations are allowed.
- Never use destructive commands unless explicitly requested.

## Commands and Environment
- Use `uv run ...` for Python commands.
- Common commands:
  - `uv sync --all-extras`
  - `uv run pytest`
  - `uv run pytest -m "not integration and not slow"`
  - `uv run ruff check .`

## Testing Rules
- Do not hide test output (`2>&1`, tail-only logs, etc.).
- Test files should mirror source paths.
- Prefer mocked network boundaries where possible.
- When debugging tests, run with one worker and no retries.

## Data and Model Rules
- Do not modify core Pydantic model contracts in `src/models/` without explicit maintainer approval.
- Division OCD IDs must align with official OCD sources.
- Jurisdiction OCD ID format must remain:
  - `ocd-jurisdiction/<division_id_without_prefix>/<classification>`
- Use `src` package-root imports (for example `from src.models.division import Division`).

## Logging Rules
- Use standard Python logging.
- Prefer structured, contextual logs.
- Do not interpolate dynamic values into log message strings.
- Include dynamic fields as structured logging extras.
- Prefer exception-aware logging patterns for failures.

## Code Style Rules
- Prefer minimal, targeted changes over broad refactors.
- Reuse existing modules/utilities before adding new abstractions.
- Keep comments minimal and purposeful.
- Do not modify `__init__.py` unless explicitly requested.
- Use modern typing (`|`, `Type | None`, typed list/dict annotations).

## Contributor Workflow Rules
1. Check for an existing issue before implementation.
2. If no issue exists, create one.
3. If using an existing issue, use an issue-linked branch and keep status updated.
4. For full workflow details, follow `ai_tools/system/contributor-workflows.instruction.md`.

## References
- `docs/init_research_pipeline.md`
- `ai_tools/system/contributor-workflows.instruction.md`
- `ai_tools/system/pre-commit-checks.instruction.md`

## Maintenance
If any instruction appears inaccurate or outdated, flag it and propose a specific update.
- Whenever instructions are added or changed under `ai_tools/`, update `ai_tools/catalog.yaml` in the same change.
- Treat catalog and documentation updates as part of the pre-commit checklist
  (including `CONTRIBUTING.md` when contributor workflow guidance changes and
  README.md changes when project requirements or installation instructions
  should change.)