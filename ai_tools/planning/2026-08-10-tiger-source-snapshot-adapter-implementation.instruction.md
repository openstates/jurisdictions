---
id: tiger-source-snapshot-adapter-implementation
type: planning
owner: rework
status: draft
last_updated: 2026-08-10
tags: [planning, implementation, rework, census, tiger]
issue: 135
task: "Phase 4 — Task 4.2"
---

# TIGER Source Snapshot Adapter — Implementation Plan

## Overview

Deliver #135 Task 4.2 as one reviewable PR targeting
`131-gus-pipeline-rework`. The PR adds a source adapter, controlled fixtures,
unit tests, and these planning assets. It does not change domain models,
integration tests, golden YAML, or downstream resolver behavior.

Design reference:
`ai_tools/planning/2026-08-10-tiger-source-snapshot-adapter-design.instruction.md`

## Goals and Constraints

- Implement the approved `metadata preflight -> fetch -> verify -> cache -> parse` boundary.
- Reuse `AsyncDownloader` via dependency injection.
- Pin the 2025 TIGERweb layer contracts.
- Keep source codes as exact strings.
- Fail closed on partial or unverifiable source data.
- Keep all normal tests offline.
- Keep the diff limited to Task 4.2.

## Task Breakdown

### Task 1 — Register Planning Assets

Files:

- `ai_tools/catalog.yaml`
- design and implementation documents under `ai_tools/planning/`

Gate:

- Both new assets are cataloged with matching IDs, paths, types, and status.

### Task 2 — Define Pinned Source Contracts

File:

- `src/init_migration/tiger_adapter.py`

Work:

- Add `TigerGeography`.
- Add `TigerLayerSpec` and the 2025 layer catalog.
- Pin each layer's composite-service parent group and field-width contract.
- Add deterministic attributes-only query construction.
- Reject unsupported vintages explicitly.

Gate:

- Tests cover all required layer classes, numeric layer IDs, parent group IDs,
  and field-width contracts.
- Query test proves `returnGeometry=false`, `orderByFields=GEOID`, and the
  expected field list.

### Task 3 — Implement Metadata Preflight, Fetch, and Structural Verification

Work:

- Inject the existing downloader-compatible `fetch_bytes` interface.
- Fetch layer metadata before each record query.
- Verify the layer ID/name, parent ACS vintage group, vintage description,
  Query capability, record limit, required string fields, and exact widths.
- Decode ArcGIS JSON responses.
- Reject ArcGIS errors.
- Reject missing or empty national `features` and malformed `attributes`
  structures.
- Reject missing requested fields.
- Reject transfer-limit truncation.

Gate:

- Unit tests cover metadata success for all seven classes; parent, description,
  capability, record-limit, field, and width drift; source error; missing field;
  malformed JSON; and `exceededTransferLimit=true`.

### Task 4 — Implement Atomic Cache and Manifest

Work:

- Store raw source bytes by vintage/geography class.
- Write a sidecar provenance manifest.
- Compute and validate SHA-256.
- Reuse valid cache on HTTP 304.
- Fail on 304 without a valid cache.

Gate:

- Round-trip and 304 tests pass.
- Tampering causes a checksum failure.
- Retrieval timestamps must be timezone-aware and serialize in UTC.

### Task 5 — Implement Offline Semantic Parsing

Work:

- Parse exact-width string identifiers.
- Preserve blank optional school-district type values as `None`.
- Validate GEOID/component parity.
- Produce normalized `TigerRecord` objects.
- Collect malformed and duplicate rows as `TigerParseError`.
- Preserve the input-count invariant.

Gate:

- All seven fixtures parse offline.
- Leading-zero, malformed-row, duplicate-GEOID, and component-mismatch tests
  pass.

### Task 6 — Add Controlled Fixtures

Files:

- `tests/fixtures/tiger/README.md`
- one synthetic ArcGIS response fixture per supported geography class

Rules:

- Match official field names and code widths.
- Use synthetic names/codes where factual assertions are unnecessary.
- Store no geometry.
- Do not refresh fixtures from live sources automatically.

Gate:

- Every fixture is consumed by a parametrized unit test.

### Task 7 — Validate the PR

Targeted commands:

```bash
uv run pytest tests/src/init_migration/test_tiger_adapter.py
uv run ruff check src/init_migration/tiger_adapter.py \
  tests/src/init_migration/test_tiger_adapter.py
```

Full non-integration gate:

```bash
uv run ruff check .
uv run pytest -m "not integration and not slow"
```

Review gate:

- No files under `src/models/`, `tests/sample_output/`, or
  `tests/integration/` changed.
- No new package dependency added.
- No live network required by unit tests.
- PR base is `131-gus-pipeline-rework`.
- PR title begins `[Rework]`.

## Verification and Tests

Required unit coverage:

- layer catalog completeness;
- pinned 2025 layer and parent group IDs;
- metadata contract completeness for every query field;
- metadata preflight order and forced metadata refresh;
- parent-vintage, description, name, capability, record-limit, field, and width
  drift rejection;
- deterministic query parameters;
- injected downloader use;
- seven-geography fixture round trip;
- leading-zero preservation;
- cache reuse after 304;
- 304 cache miss;
- ArcGIS error response;
- transfer-limit truncation;
- missing requested field;
- malformed row reporting;
- duplicate GEOID reporting;
- GEOID/component mismatch;
- checksum mismatch;
- timezone-aware retrieval timestamp;
- unsupported vintage.

## Affected Modules

```text
ai_tools/catalog.yaml
ai_tools/planning/2026-08-10-tiger-source-snapshot-adapter-design.instruction.md
ai_tools/planning/2026-08-10-tiger-source-snapshot-adapter-implementation.instruction.md
src/init_migration/tiger_adapter.py
tests/fixtures/tiger/*
tests/src/init_migration/test_tiger_adapter.py
```

## Follow-Ups Outside This PR

- #136 consumes GUS source snapshots into `GovernmentRecord`.
- #137 maps government records to these TIGER records and defines typed
  resolver outcomes.
- #137 Task 6.8 builds feature-specific TIGERweb GeoJSON URLs.
- Future TIGER vintages add a separately reviewed pinned layer catalog and
  source-refresh procedure.
