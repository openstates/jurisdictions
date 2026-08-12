---
id: census-government-source-snapshot-adapter-implementation
type: planning
owner: rework
status: draft
last_updated: 2026-08-11
tags: [planning, implementation, rework, census, gus]
issue: 135
task: "Phase 4 — Task 4.1"
---

# Census Government Source Snapshot Adapter — Implementation Plan

## Overview

Deliver #135 Task 4.1 as a standalone PR targeting
`131-gus-pipeline-rework`. The change adds the annual Census Government Units
source adapter, a controlled synthetic source fixture, unit tests, and the
planning/source-contract documentation required to review the behavior.

Design reference:

```text
ai_tools/planning/2026-08-11-census-government-source-snapshot-adapter-design.instruction.md
```

## Goals and Constraints

- Implement `fetch -> verify -> cache -> parse`.
- Pin the exact 2025 archive, workbook, worksheet, header, and row contracts.
- Store the original ZIP unchanged with checksums and retrieval provenance.
- Preserve source rows rather than prematurely normalizing them.
- Stream the national source and explicitly account for malformed rows.
- Keep all normal tests offline.
- Keep this PR independent of PR #151 and downstream Phase 5/6 work.
- Do not change models, generated YAML, golden files, integration tests,
  dependencies, or `__init__.py` files.

## Task Breakdown

### Task 1 — Register Planning and Source Contract Assets

Files:

- `ai_tools/catalog.yaml`
- design and implementation documents under `ai_tools/planning/`
- `docs/rework/census_government_source_contract_2025.md`

Gate:

- Asset IDs, paths, types, and catalog entries agree.
- Human-facing source facts are under `docs/rework/`; agent execution guidance
  remains under `ai_tools/`.

### Task 2 — Pin the 2025 Release Contract

File:

```text
src/init_migration/census_government_adapter.py
```

Work:

- Add release and worksheet specification types.
- Pin source URL, source snapshot date, outer members, exact worksheet order,
  headers, allowed unit types, dimensions, and row counts.
- Preserve all identifiers as strings.

Gate:

- Unit tests prove five-tab coverage and the 97,241-row production contract.

### Task 3 — Implement Archive and Workbook Verification

Work:

- Reject empty, oversized, invalid, encrypted, unsafe, corrupt, or unexpected
  ZIP contents.
- Confirm the documentation member is a PDF.
- Parse XLSX workbook relationships and shared strings with the standard
  library.
- Confirm exact sheets, headers, dimensions, row counts, row sequencing, cell
  placement, and value-only cells.

Gate:

- Tests cover valid release, malformed ZIP, unexpected member, non-PDF docs,
  missing sheet, header drift, row-count drift, and formulas.

### Task 4 — Implement Atomic Cache and Manifest

Work:

- Cache the original annual ZIP unchanged.
- Create a deterministic manifest with release/source dates, URL, retrieval
  time, archive/member checksums, member names, and sheet counts.
- Validate all manifest and source facts before cache reuse.
- Reuse a valid cache after HTTP 304; fail closed without one.

Gate:

- Round-trip, 304, checksum-tamper, and timezone tests pass.

### Task 5 — Implement Streaming Raw-Row Parsing

Work:

- Add `iter_parse()` and materialized `parse()`.
- Emit raw records with worksheet and Excel-row provenance.
- Validate only PID, row name/type, active status, and dependent parent IDs.
- Preserve imperfect address, website, FIPS, population, and enrollment values
  unchanged for later normalization.
- Detect duplicate PIDs globally.
- Emit structured errors and enforce input-count parity.

Gate:

- Tests cover all five row types, leading zeros, raw website preservation,
  unresolved parent references, missing PID, duplicate PID, invalid unit type,
  invalid active status, and streaming outcomes.

### Task 6 — Add Controlled Offline Fixture

Files:

```text
tests/fixtures/census_governments/README.md
tests/fixtures/census_governments/mini_release_2025.json
```

The test builder converts the JSON into a minimal XLSX and outer ZIP at
runtime. This avoids committing a binary Office fixture while still exercising
the real archive and workbook parser.

Gate:

- No unit test performs a network request.
- Fixture values preserve leading-zero identifiers.
- The fixture is clearly labeled synthetic.

### Task 7 — Verify the Official 2025 Release Locally

Against the downloaded official archive, confirm:

```text
verified source rows: 97,241
parsed raw records: 97,241
structured row errors: 0
global duplicate PIDs: 0
```

This is a local release-smoke gate, not a committed CI dependency.

### Task 8 — Validate the PR

Required commands:

```bash
uv run pytest tests/src/init_migration/test_census_government_adapter.py
uv run ruff check src/init_migration/census_government_adapter.py \
  tests/src/init_migration/test_census_government_adapter.py
uv run ruff check .
uv run pytest -m "not integration and not slow"
```

Review gate:

- Base branch is `131-gus-pipeline-rework`.
- PR title begins `[Rework]`.
- PR body says `Refs #135 — Task 4.1`, not `Closes #135`.
- No files under `src/models/`, `tests/sample_output/`,
  `tests/integration/`, or `.github/` changed.
- No dependency or `__init__.py` changes.
- No generated YAML or live-source fixture is committed.

## Affected Files

```text
ai_tools/catalog.yaml
ai_tools/planning/2026-08-11-census-government-source-snapshot-adapter-design.instruction.md
ai_tools/planning/2026-08-11-census-government-source-snapshot-adapter-implementation.instruction.md
docs/rework/census_government_source_contract_2025.md
src/init_migration/census_government_adapter.py
tests/fixtures/census_governments/README.md
tests/fixtures/census_governments/mini_release_2025.json
tests/src/init_migration/test_census_government_adapter.py
```

## Follow-Ups Outside This PR

- #136 converts raw source records into normalized `GovernmentRecord` values.
- #137 maps supported normalized governments to TIGER geography records.
- The final PID-to-Division lookup combines Task 4.1, PR #151, and Phase 6
  resolver outcomes.
- State parents referenced by dependent entities require a governed strategy;
  the source adapter intentionally does not fabricate missing parent rows.
- Website validation/self-healing remains a later enrichment concern.
