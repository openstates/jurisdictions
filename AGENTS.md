# Overview
`jurisdictions` is an open source repository that generates and Division and Jurisdiction YAML for US local governments.

Primary goals:
1. Keep model contracts stable and valid.
2. Make contributor workflows predictable.
3. Make agentic workflows discoverable, repeatable, and safe.


## Instruction Model and Precedence
Use this order of precedence for agent behavior:
1. `AGENTS.md` (authoritative repo policy)
2. `ai_tools/system/*.instruction.md` (always-on reusable system guidance)
3. `ai_tools/tasks/*.instruction.md` (task/workflow-specific instructions)
4. `ai_tools/prompts/**/*.prompt.md` (invocation templates)

If there is any conflict, follow `AGENTS.md`.

## AI Tooling Canonical Paths
- Directory conventions and usage: `ai_tools/README.md`
- System (always-on): `ai_tools/system/repo-agent-system.instruction.md`
- System (commit checks): `ai_tools/system/pre-commit-checks.instruction.md`
- Task guides: `ai_tools/tasks/`
- Prompt library: `ai_tools/prompts/`
- Planning instructions: `ai_tools/planning/`
- Skills/examples: `ai_tools/skills/`
- Asset index: `ai_tools/catalog.yaml`

## Task Instruction Routing (Required)
- Before implementation, review `ai_tools/catalog.yaml` and load relevant task guides and planning instructions into context.
- Selection rules:
  - If a direct task guide match exists, load it first.
  - If multiple assets match, choose the closest fit and state assumptions (or ask one focused clarifying question).
  - If request maps to prompt-driven planning/review workflows, load the relevant prompt from `ai_tools/prompts/`.

Do not add new AI tooling content under proprietary IDE code paths such as
`.github/prompts`, `.vscode`, etc.

## Repository Scope
- Data contracts: `src/models/division.py`, `src/models/jurisdiction.py`, `src/models/ocdid.py`, `src/models/source.py`
- Output directories: `divisions/<state>/local/`, `jurisdictions/<state>/local/`

## Git Safety and Change Control
- Do not perform write git operations without explicit user authorization.
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

## References
- `docs/init_research_pipeline.md`
- `docs/contributor-workflows.md`
- `ai_tools/system/pre-commit-checks.instruction.md`

## Maintenance
If any instruction appears inaccurate or outdated, flag it and propose a specific update.
- Whenever instructions are added or changed under `ai_tools/`, update `ai_tools/catalog.yaml` in the same change.
- Treat catalog and documentation updates as part of the pre-commit checklist (including `CONTRIBUTING.md` when contributor workflow guidance changes).