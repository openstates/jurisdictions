---
id: stage1-ocdid-planning
type: instruction
owner: maintainers
status: active
last_updated: 2026-03-07
tags: [planning, stage1, ocdid]
---

# Stage 1 Planning Instruction

Use this for Stage 1 ingestion work (`download_manager`, `ocdid_matcher`, `downloader`, `main`).

## Inputs
- `docs/plans/2026-02-13-stage1-ocdid-pipeline-design.md`
- `docs/plans/2026-02-15-stage1-ocdid-pipeline-implementation.md`

## Requirements
1. Keep `master_ocdids` as source of truth.
2. Keep matching behavior explicit: match, local orphan, master orphan.
3. Persist lookup/orphan artifacts in reproducible formats.

## Verification
- Run targeted tests under `tests/src/init_migration/`.
- Run downloader test modules when network logic changes.
