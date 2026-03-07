---
id: stage1-ocdid-planning
type: instruction
owner: maintainers
status: active
last_updated: 2026-03-07
tags: [planning, stage1, ocdid]
---

# Stage 1 Planning Instruction

Use this instruction for Stage 1 ingestion work in `src/init_migration/`:
- `main.py`
- `download_manager.py`
- `ocdid_matcher.py`
- `downloader.py`

## Purpose

Stage 1 should ingest OCD division data, reconcile local and national records,
and produce stable machine-readable outputs for downstream pipeline stages.

## Authoritative Inputs
- `ai_tools/planning/stage1-ocdid-pipeline-detailed-plans/2026-02-13-stage1-ocdid-pipeline-design.md`
- `ai_tools/planning/stage1-ocdid-pipeline-detailed-plans/2026-02-15-stage1-ocdid-pipeline-implementation.md`
- `ai_tools/planning/stage1-ocdid-pipeline-detailed-plans/2026-02-15-stage1-verification-analysis.md`

## Pipeline Module References
- Stage 1 ingestion pipeline: `src/init_migration/main.py`,
  `src/init_migration/download_manager.py`,
  `src/init_migration/ocdid_matcher.py`, `src/init_migration/downloader.py`

## Architecture Expectations
1. `main.py` is orchestration-only (argument parsing, sequencing, summaries).
2. `download_manager.py` owns fetch + load business logic.
3. `downloader.py` remains a reusable HTTP library layer.
4. `ocdid_matcher.py` owns reconciliation and match classification.
5. `master_ocdids` remains source of truth for canonical records.

## Functional Requirements
1. Support state-scoped runs and full runs.
2. Classify reconciliation outcomes explicitly:
   - match
   - local orphan
   - master orphan
3. Persist reproducible lookup and quarantine artifacts.
4. Keep Stage 1 outputs consumable by Stage 2 without ad hoc transformations.

## Implementation Workflow
1. Create or update a design doc entry in `ai_tools/planning/` for non-trivial changes.
2. Break implementation into scoped tasks with validation gates.
3. Apply changes in this order when possible:
   - interfaces and models
   - downloader/fetch behavior
   - DuckDB load behavior
   - matcher/reconciliation logic
   - orchestration/CLI wiring
4. Update tests and docs in the same change.

## Verification Gates
1. Run Stage 1 targeted tests under `tests/src/init_migration/`.
2. Run downloader-focused test modules when fetch/caching logic changes.
3. Run lint checks:
   - `uv run ruff check .`
4. Confirm output artifacts are reproducible and path-correct.

## Done Criteria
1. Stage 1 behavior matches design intent and acceptance criteria.
2. Match/orphan outputs are explicit and test-covered.
3. Planning and catalog docs are updated when instruction behavior changes.
4. No regression in Stage 2 handoff expectations.
