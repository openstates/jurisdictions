---
id: stage2-generation-planning
type: instruction
owner: maintainers
status: active
last_updated: 2026-03-07
tags: [planning, stage2, generation]
---

# Stage 2 Planning Instruction

Use this for Stage 2 generation work (`generate_pipeline`, `generate_division`, `generate_jurisdiction`).

## Inputs
- Validation research CSV inputs.
- OCD ID parsing and place normalization utilities.

## Requirements
1. Maintain fuzzy matching branch behavior (0/1/2+ outcomes).
2. Keep Division and Jurisdiction output schemas valid against Pydantic models.
3. Keep jurisdiction OCD ID format deterministic and derivable.
4. Capture no-match and ambiguous cases for quarantine review.

## Verification
- Run targeted Stage 2 tests in `tests/src/init_migration/`.
- Validate emitted YAML paths under `divisions/<state>/local/` and `jurisdictions/<state>/local/`.
