# AI Tools

This directory stores reusable agent assets for this repository.

## Scope
- Prompt and instruction assets for repository workflows.
- Planning instructions for specific features.
- Templates for consistent asset creation.

## Directory Layout
- `catalog.yaml`: index of active assets and ownership metadata.
- `system/`: always-on repository instruction assets.
- `tasks/`: task-focused execution instructions.
- `prompts/`: reusable prompts for planning/review tasks.
- `templates/`: starter templates for prompt and instruction assets.
- `skills/`: reusable workflow skills when needed.
- `planning/`: feature-specific design and implementation instructions.

## Conventions
- Use kebab-case filenames.
- Use explicit suffixes: `*.instruction.md`, `*.prompt.md`.
- Include frontmatter on every asset except `README.md` and `catalog.yaml`.
- Keep this directory free of runtime application code.
