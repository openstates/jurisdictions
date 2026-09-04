---
id: tiger-source-snapshot-adapter-design
type: planning
owner: rework
status: draft
last_updated: 2026-08-10
tags: [planning, rework, census, tiger, source-snapshot]
issue: 135
task: "Phase 4 — Task 4.2"
---

# TIGER Source Snapshot Adapter — Design

## Overview

Implement the Phase 4.2 Census TIGER adapter as an offline-first source
snapshot layer. The adapter verifies each composite-service layer's live
metadata contract before fetching attributes, verifies that the response is
complete, caches the raw response with provenance and a checksum, and parses
cached attributes into typed Python records plus structured row errors.

The adapter is a source boundary. It does not resolve Government Units Survey
records, construct OCD identifiers, instantiate canonical `Division` or
`Jurisdiction` models, generate geometry, or render YAML.

Related work:

- Parent rework: #131
- Source snapshot phase: #135
- Downstream normalized government layer: #136
- Downstream government-to-geography resolver: #137
- Governing plan: `ai_tools/planning/census-pipeline-rework-plan.md`
- Governing task instruction:
  `ai_tools/tasks/census-pipeline-rework.instruction.md`

## Goals and Constraints

### Goals

1. Support state, county, incorporated-place, county-subdivision, unified
   school-district, secondary school-district, and elementary
   school-district attributes.
2. Keep the lifecycle explicit: `metadata preflight -> fetch -> verify -> cache -> parse`.
3. Run normal parsing and unit tests entirely from cached JSON fixtures.
4. Preserve GEOID/FIPS/school codes as strings, including leading zeros.
5. Retain source URL, service/layer identity, vintage, retrieval timestamp,
   record count, and SHA-256 checksum.
6. Fail closed when a numeric layer no longer identifies the expected vintage,
   geography, query capability, or field-width contract.
7. Fail closed when TIGERweb reports an error, returns an empty national layer,
   omits requested fields, or indicates a transfer-limit truncation.
8. Return one normalized record or one structured error for every input
   feature; never silently drop source rows.

### Constraints

- Reuse the existing `AsyncDownloader` through a small injected fetcher
  protocol; do not create another HTTP client.
- Do not add GIS dependencies or require PostGIS.
- Request attributes only (`returnGeometry=false`).
- Do not store polygon/GeoJSON blobs in repository fixtures or snapshots.
- Do not modify `src/models/` without separate maintainer approval.
- Do not modify `tests/sample_output/`.
- Do not modify `tests/integration/` in this task.
- Do not construct OCDIDs or feature-specific GeoJSON URLs here; those belong
  to #137.

## Architecture and Data Flow

```text
Pinned TIGERweb layer specification
                 |
                 v
 Live layer metadata preflight
 - ID and geography name
 - parent ACS vintage group
 - January 1 vintage description
 - Query capability and record limit
 - required string fields and widths
                 |
                 v
       Existing AsyncDownloader
                 |
                 v
        Raw ArcGIS JSON bytes
                 |
                 v
 Structural response verification
 - JSON object
 - no ArcGIS error
 - no transfer-limit truncation
 - features[] present
 - requested attributes present
                 |
                 v
 Atomic snapshot + manifest
 data/raw/census/tiger/<vintage>/<type>.json
 data/raw/census/tiger/<vintage>/<type>.manifest.json
                 |
                 v
 Offline semantic parse
 - exact string code widths
 - GEOID/component parity
 - duplicate GEOID detection
 - normalized TigerRecord
 - structured TigerParseError
```

The caller chooses the cache root. The path above is the intended production
layout; unit tests use `tmp_path`.

## Source Contract

The first supported release is the January 1, 2025 vintage. The full-resolution
TIGERweb services expose vintage groups inside composite MapServers, so their
child layers are addressed by numeric IDs:

| Geography | Service | Layer |
| --- | --- | ---: |
| State | `State_County` | 18 |
| County | `State_County` | 19 |
| County subdivision | `Places_CouSub_ConCity_SubMCD` | 8 |
| Incorporated place | `Places_CouSub_ConCity_SubMCD` | 11 |
| Unified school district | `School` | 5 |
| Secondary school district | `School` | 6 |
| Elementary school district | `School` | 7 |

Before each source query, the adapter fetches the layer metadata endpoint and
verifies that the numeric layer still has the expected layer ID and name,
`ACS 2025` parent group, January 1 vintage description, Query capability,
100,000-record capacity, required string fields, and exact field widths. This
prevents a future composite-service reordering from silently relabeling another
vintage as 2025.

Each data query requests only the identifiers and descriptive attributes needed
by later normalization/resolution, orders by `GEOID`, requests no geometry, and
sets the service-supported 100,000-record ceiling. The response verifier rejects
`exceededTransferLimit=true` so a future source-size change cannot create silent
truncation.

Adding another vintage requires a new explicit layer catalog and metadata
contract. Reusing a mutable endpoint while relabeling it as an older vintage is
not allowed.

## Module Contract

New module: `src/init_migration/tiger_adapter.py`

Primary types:

- `TigerGeography`: supported source geography classes.
- `TigerLayerSpec`: pinned service/layer/field contract.
- `TigerAdapter`: metadata preflight, fetch, verify, cache, refresh, and parse operations.
- `TigerSnapshotMetadata`: provenance/checksum sidecar data.
- `TigerRecord`: normalized TIGER attribute record.
- `TigerParseError`: reviewable malformed/duplicate source row.
- `TigerParseResult`: records and errors with an input-count invariant.

The adapter accepts any object implementing the existing downloader's
`fetch_bytes(url, force=False)` interface. This keeps tests offline and avoids
coupling source semantics into the HTTP client.

## Cache and Integrity Contract

For each geography class, cache:

1. The raw ArcGIS JSON response exactly as fetched.
2. A deterministic JSON manifest containing:
   - manifest schema version;
   - dataset name;
   - geography class;
   - vintage;
   - service name;
   - layer ID and name;
   - exact source query URL;
   - UTC retrieval timestamp;
   - SHA-256 of the raw snapshot;
   - source feature count;
   - snapshot filename.

Writes are atomic. A 304 response reuses an existing snapshot only after the
manifest and checksum pass validation. A 304 with no valid cache fails closed.

## Semantic Parse Rules

- `GEOID`, `STATE`, `COUNTY`, `PLACE`, `COUSUB`, `SDUNI`, `SDSEC`, and
  `SDELM` remain strings and must satisfy exact source widths.
- `GEOID` must equal its component codes for the geography class.
- Source names are preserved; no name normalization occurs in this phase.
- School-district type may be blank in authoritative TIGER records and is preserved as `None`; invalid nonblank codes remain errors.
- Duplicate GEOIDs are emitted as errors rather than overwritten.
- A malformed feature produces `TigerParseError` with feature index, available
  GEOID, message, and source attributes.
- `len(records) + len(errors)` must equal the number of input features.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Composite TIGERweb layer IDs drift | Preflight live ID, parent vintage, description, capabilities, and field widths before querying. |
| Service silently truncates a response | Reject `exceededTransferLimit=true`. |
| Numeric conversion destroys leading zeros | Require exact-width strings. |
| Network-dependent tests become flaky | Parse controlled JSON fixtures only. |
| Adapter begins resolver work | Keep OCDID/geometry/model logic out. |
| Cached source is altered | Verify SHA-256 before reuse or parse. |
| A malformed feature disappears | Emit an error; enforce input-count parity. |

## Acceptance Criteria

- All seven supported geography classes have pinned layer specifications.
- Every fetch verifies live layer identity, parent vintage, capabilities, record
  limit, required fields, and exact field widths before querying records.
- Query URLs request attributes only and deterministic GEOID ordering.
- Metadata drift, malformed responses, missing fields, and truncated responses
  fail verification.
- Snapshot and manifest writes are atomic.
- Manifest checksum is verified before cache reuse or parsing.
- Leading zeros survive fetch/cache/parse unchanged.
- Duplicate, malformed, and component-mismatch rows become explicit errors.
- Unit tests use controlled fixtures and no live network.
- No model, golden-output, integration-test, OCDID, YAML, or geometry changes.

## Verification and Tests

Targeted commands:

```bash
uv run pytest tests/src/init_migration/test_tiger_adapter.py
uv run ruff check src/init_migration/tiger_adapter.py \
  tests/src/init_migration/test_tiger_adapter.py
```

Repository checks before PR review:

```bash
uv run ruff check .
uv run pytest -m "not integration and not slow"
```

A live-source smoke check is optional and must remain separate from normal PR
CI. It must not rewrite committed fixtures automatically.
