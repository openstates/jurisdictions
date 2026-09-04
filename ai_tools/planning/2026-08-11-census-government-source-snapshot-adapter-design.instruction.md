---
id: census-government-source-snapshot-adapter-design
type: planning
owner: rework
status: draft
last_updated: 2026-08-11
tags: [planning, rework, census, gus, source-snapshot]
issue: 135
task: "Phase 4 — Task 4.1"
---

# Census Government Source Snapshot Adapter — Design

## Overview

Implement the Phase 4.1 Census Government adapter as an offline-first source
boundary for the annual Government Units ZIP archive. The adapter downloads the
official archive once, verifies the release structure, stores the original ZIP
unchanged with provenance and checksums, and exposes every workbook row as a raw
source record or a structured source error.

This adapter does **not** perform Phase 5 normalization, government-type
classification, TIGER resolution, PID-to-Division mapping, OCDID generation,
canonical model construction, or YAML rendering.

Related work:

- Parent rework: #131
- Source snapshot phase: #135
- Normalized government layer: #136
- Government-to-geography resolver: #137
- TIGER source adapter: PR #151
- Governing plan: `ai_tools/planning/census-pipeline-rework-plan.md`
- Governing task instruction:
  `ai_tools/tasks/census-pipeline-rework.instruction.md`

## Goals and Constraints

### Goals

1. Pin the official 2025 Government Units source contract.
2. Keep the lifecycle explicit: `fetch -> verify -> cache -> parse`.
3. Cache the original Census ZIP, not a rewritten workbook or derived table.
4. Run verification and parsing offline after acquisition.
5. Preserve `CENSUS_ID_PID6` and parent identifiers as six-character strings.
6. Preserve every published field exactly, including blanks and imperfect
   address or website values.
7. Emit one raw record or one structured error for every source row.
8. Preserve source year, source snapshot date, archive URL, checksums, workbook
   member, worksheet, and Excel row number.
9. Provide a streaming parser for the 97,241-row release plus a materialized
   result for tests and bounded workflows.

### Constraints

- Reuse the existing `AsyncDownloader` through its `fetch_bytes` interface.
- Do not add `openpyxl`, spreadsheet-engine, GIS, or database dependencies.
- Do not modify `src/models/`.
- Do not modify `tests/sample_output/` or `tests/integration/`.
- Do not validate websites as URLs; the Census documentation says they are
  self-reported and receive limited quality control.
- Do not treat ZIP, ZIP4, address, or missing contact fields as row-fatal.
- Do not require parent PIDs to resolve inside the same workbook; state parent
  governments are referenced but are not listed as independent rows here.
- Do not interpret county-area fields as a service-boundary crosswalk.

## Verified 2025 Source Contract

Source archive:

```text
https://www2.census.gov/programs-surveys/gus/datasets/2025/gov_units_2025.zip
```

The source documentation identifies the workbook as a snapshot of the Census
Bureau Governments Master Address File retrieved August 28, 2025. It includes
independent government units, dependent school systems, and public pension
systems active or dormant as of the fiscal year ending June 30, 2025.

Outer ZIP members:

```text
Govt_Units_2025_Final.xlsx
Government_Units_List_Documentation_2025.pdf
```

Workbook tabs and exact 2025 row counts:

| Worksheet | Data rows | Columns | Primary category |
| --- | ---: | ---: | --- |
| `General Purpose` | 38,704 | 19 | County, municipal, township governments |
| `Special District` | 40,199 | 16 | Special district governments |
| `School District` | 12,535 | 18 | Independent school districts/agencies |
| `DEP School Dist` | 1,318 | 20 | Dependent school systems |
| `Public Pension Sys` | 4,485 | 18 | Defined-benefit public pension systems |
| **Total** | **97,241** |  |  |

The documentation calls the final tab “Public Pensions Sys”; the actual
workbook tab is `Public Pension Sys`. The adapter pins the workbook value.

### Exact Headers

`General Purpose`:

```text
CENSUS_ID_PID6, UNIT_NAME, UNIT_TYPE, TITLE, ADDRESS1, ADDRESS2,
CITY, STATE, ZIP, ZIP4, WEB_ADDRESS, POLITICAL_CODE_DESCRIPTION,
POPULATION, POPULATION_SOURCE_YEAR, FIPS_STATE, FIPS_COUNTY,
FIPS_PLACE, COUNTY_AREA_NAME, ACTIVE
```

`Special District`:

```text
CENSUS_ID_PID6, UNIT_NAME, UNIT_TYPE, FUNCTION_NAME, TITLE,
ADDRESS1, ADDRESS2, CITY, STATE, ZIP, ZIP4, WEB_ADDRESS,
FIPS_STATE, FIPS_COUNTY, COUNTY_AREA_NAME, ACTIVE
```

`School District`:

```text
CENSUS_ID_PID6, UNIT_NAME, UNIT_TYPE, TITLE, ADDRESS1, ADDRESS2,
CITY, STATE, ZIP, ZIP4, WEB_ADDRESS, SCHOOL_ENROLLMENT,
ENROLLMENT_YEAR, SCHOOL_LEVEL_DESCRIPTION, FIPS_STATE,
FIPS_COUNTY, COUNTY_AREA_NAME, ACTIVE
```

`DEP School Dist` adds:

```text
PARENT_CENSUS_ID_PID6, PARENT_UNIT_NAME
```

`Public Pension Sys` uses `ACTIVITY_NAME` and also includes the two parent
fields.

## Source Semantics and Known Caveats

- `CENSUS_ID_PID6` is the Census Bureau’s internal government-unit identifier.
- `PARENT_CENSUS_ID_PID6` identifies the parent government for dependent
  school systems and pension systems.
- `ACTIVE=N` means dormant, not disincorporated; dormant rows remain part of
  the government inventory and must not be dropped.
- `COUNTY_AREA_NAME` and `FIPS_COUNTY` represent the county most served or the
  headquarters county when an entity crosses county boundaries. They do not
  prove that the entity governs only that county.
- `FIPS_PLACE` appears only on `General Purpose`. County rows use 99xxx values,
  so this field cannot be treated as a universal incorporated-place GEOID.
- School and special-district rows do not contain a direct TIGER district
  GEOID. Their county fields are not sufficient to establish final geography.
- Websites are self-reported and may be blank, stale, or malformed.
- Address fields contain published inconsistencies, including short ZIP and
  ZIP4 values. These are preserved as source facts, not rejected.
- The 2025 workbook contains 97,241 globally unique six-digit PIDs.
- Forty-four dependent-school parent IDs and 314 pension parent IDs do not
  resolve to another row in this workbook. Most are state-government parents,
  which are outside the independent local-government tabs.

## Architecture and Data Flow

```text
Pinned annual ZIP URL
        |
        v
Existing AsyncDownloader
        |
        v
Original ZIP bytes
        |
        v
Archive verification
- size and ZIP integrity
- safe and exact outer members
- documentation is a PDF
        |
        v
Workbook verification
- safe XLSX members
- exact sheet order and names
- exact headers and dimensions
- exact release row counts
- sequential rows
- no formulas or Excel error cells
        |
        v
Atomic ZIP + manifest cache
        |
        v
Offline streaming parse
- raw source record
- structured source error
- global duplicate-PID detection
- complete input accounting
```

## Module Contract

New module:

```text
src/init_migration/census_government_adapter.py
```

Primary types:

- `CensusGovernmentReleaseSpec`: pinned release/member/tab contract.
- `CensusGovernmentSheetSpec`: exact header, row-count, and unit-type contract.
- `CensusGovernmentAdapter`: fetch, verify, cache, refresh, stream, and parse.
- `CensusGovernmentSnapshotMetadata`: archive/member checksums and row counts.
- `CensusGovernmentSourceRecord`: raw row plus source provenance.
- `CensusGovernmentParseError`: reviewable malformed or duplicate source row.
- `CensusGovernmentParseResult`: records/errors with full input accounting.

### Raw Record Contract

Each valid row exposes:

```text
release_year
source_snapshot_date
source_archive_url
source_archive_sha256
source_member_filename
source_sheet
source_row_number
census_id_pid6
parent_census_id_pid6
unit_name
unit_type
active
raw_fields
```

`raw_fields` preserves the worksheet’s exact source columns. The source adapter
requires only the row identity and source-category contract:

- six-digit `CENSUS_ID_PID6`;
- nonblank `UNIT_NAME`;
- worksheet-compatible `UNIT_TYPE`;
- `ACTIVE` equal to `Y` or `N`;
- six-digit parent PID and nonblank parent name on dependent tabs.

All geography, address, website, population, and enrollment interpretation is
deferred to downstream stages.

## Cache and Integrity Contract

Cache per release:

```text
<cache_root>/2025/gov_units_2025.zip
<cache_root>/2025/gov_units_2025.zip.manifest.json
```

The manifest records:

- manifest schema version;
- dataset name;
- release year and source snapshot date;
- source URL and local archive filename;
- retrieval timestamp in UTC;
- archive size and SHA-256;
- workbook and documentation member names and SHA-256 values;
- exact row count for each worksheet.

Writes are atomic. HTTP 304 reuses the existing cache only after archive,
manifest, member, workbook, checksum, sheet, header, and row-count validation.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Census replaces a file at the same annual URL | Store original bytes, retrieval time, and SHA-256; reverify before reuse. |
| Workbook schema drifts silently | Pin member names, sheet order, headers, dimensions, and row counts. |
| ZIP path traversal or decompression abuse | Validate member paths, encryption, CRCs, and compressed-size ceilings. |
| Leading zeros are lost | Preserve XML string values; never coerce PIDs/FIPS to integers. |
| Bad websites or address values block ingestion | Preserve raw values and defer cleanup. |
| Dormant governments disappear | Preserve `ACTIVE=N` rows. |
| Parent references appear unresolved | Preserve them; resolve in a downstream relationship stage. |
| A malformed row vanishes | Emit a structured error and enforce full input accounting. |
| Full release exhausts memory | Provide `iter_parse()`; materialization remains optional. |

## Acceptance Criteria

- Official 2025 outer ZIP members are pinned and verified.
- All five worksheet contracts are pinned exactly.
- Verification confirms 97,241 source rows without network access.
- Cached ZIP bytes are byte-identical to the fetched archive.
- Archive, workbook, and documentation checksums are retained.
- Every row emits one record or one structured error.
- PIDs and parent PIDs remain six-character strings.
- Dormant rows, unresolved parent references, malformed URLs, and imperfect
  addresses remain present as source data.
- Normal tests build a controlled synthetic XLSX/ZIP and make no live request.
- No model, golden-output, integration-test, dependency, YAML, OCDID, or
  resolver changes are included.

## Verification and Tests

Targeted commands:

```bash
uv run pytest tests/src/init_migration/test_census_government_adapter.py
uv run ruff check src/init_migration/census_government_adapter.py \
  tests/src/init_migration/test_census_government_adapter.py
```

Repository checks:

```bash
uv run ruff check .
uv run pytest -m "not integration and not slow"
```

One local, non-CI release verification may be run against the official 2025
archive to confirm 97,241 records, zero unaccounted rows, and zero duplicate
PIDs. The official archive is not committed as a test fixture.
