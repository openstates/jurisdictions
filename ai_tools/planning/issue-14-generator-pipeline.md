---
id: issue-14-generator-pipeline
type: planning
owner: kas_stohr
status: in_progress
issue: 14
branch: issue-14-generator-pipeline
last_updated: 2026-04-11
tags: [planning, stage2, generation, integration-test]
---

# Issue #14 — Generator Pipeline: End-to-End Integration Test & Full Implementation

## Problem Statement

The `GeneratePipeline` in `src/init_migration/generate_pipeline.py` is partially implemented. An integration test exists but the pipeline does not produce output that matches the expected fixtures in `tests/sample_output/`. The goal is to fully implement the pipeline and make the integration test pass for the 5 sample records.

## Scope

**In scope:**
- `src/init_migration/generate_pipeline.py`
- `src/init_migration/generate_division.py`
- `src/init_migration/generate_jurisdiction.py`
- `tests/src/init_migration/test_generate_pipeline_integration.py`
- `tests/src/init_migration/test_generate_pipeline.py` (unit tests, recreated)
- New seed data files in `tests/sample_data/`

**Out of scope (locked):**
- `src/models/division.py`, `src/models/jurisdiction.py`, `src/models/source.py`, `src/models/ocdid.py`
- `src/init_migration/main.py` (request model unchanged)
- `tests/sample_output/**/*.yaml` (expected output, not to be changed)

## Baseline Test Results (2026-04-11)

### Test 1: `test_generate_pipeline_main_style_integration` — PASSING ✓
Shallow check: division/jurisdiction files exist, OCD IDs match, GEOIDs match, classification matches.

### Test 2: `test_generate_pipeline_creyton_sample_comprehensive` — FAILING (25 issues)

**Root causes of all 25 failures:**

| Failure # | Root Cause | Fix |
|-----------|-----------|-----|
| 1–5 | `JurGenerator` passes `metadata={}` which fails `JurisdictionMetadata` Pydantic validation (`urls` is required) | Pass `metadata={"urls": []}` |
| 6–10 | `DivGenerator` never sets `accurate_asof` on Division | Set `accurate_asof=req.asof_datetime` |
| 11–15 | `JurGenerator` never sets `accurate_asof` on Jurisdiction | Set `accurate_asof=req.asof_datetime` |
| 16–20 | Phase 5 timestamp check: `accurate_asof` is None → assert fails | Resolved by fixing 6–10 |
| 21–25 | Phase 5 timestamp check: `accurate_asof` is None → assert fails | Resolved by fixing 11–15 |

## Known Discrepancies (Flag for Human Review)

The following mismatches exist between the fixture format and current model/pipeline output. They **cannot be resolved without changing models or fixtures**, which is out of scope per the issue constraints.

### 1. Division `id` field format mismatch
- **Fixture**: `id: "oid1-pdna3s2b-..."` (oid1- encoded string, not a UUID)
- **Generated**: `id: "<uuid5>"` (UUID5 from `generate_id(ocdid, last_updated)`)
- **Impact**: Exact comparison fails on `id` field for all 5 division records
- **Resolution needed**: Maintainer to clarify whether `id` should store the
  oid1- string, requiring model change from `UUID | None` to `str | None`, OR
  fixtures should be updated to use UUID5 format.
  Resolution: Use UUID5 as defined and generated in generator pipeline. Change fixture.

### 2. Jurisdiction `id` field inconsistency
- **Fixtures**: Some have `id` as UUID4 (`f2a9f6b9-...`), some as oid1- string
- **Generated**: UUID5 from `generate_id(ocdid, last_updated)` — won't match either
- **Resolution needed**: Same as above.
  Resolution: Use UUID5 as defined and generated in generator pipeline. Change fixture to reflect generated UUID5
    uuid. Tests pass if UUID5 parses as expected.  Define a datetime to use for
    tests so that tests pass.

### 3. Division `uuid5_id` field not in division fixtures
- **Fixture**: No `uuid5_id` field in division YAML files
- **Generated**: `uuid5_id: "<uuid5>"` (from `Division(uuid5_id=str(uuid))`)
- **Impact**: Comparison reports "unexpected field in generated"
- **Resolution**: Omit `uuid5_id` from division dump OR add it to division
  fixtures. 
    Resolution: Use UUID5 as defined and generated in generator pipeline.Store in
    on the "id" field in the output. Change fixture to reflect generated UUID5
    uuid.  Define a datetime to use for
    tests so that tests pass.

### 4. `GovernmentIdentifiers` optional null fields
- **Fixture**: Only has fields with values (no `cousubfp`, `placefp`, `geoid_12`, `geoid_14`, `common_name`)
- **Generated**: `model_dump(exclude_none=False)` includes all Optional fields as null
- **Resolution**: Use `exclude_none=True` in GovernmentIdentifiers
  serialization, OR add null fields to all fixtures. Add null fields to all
  fixtures. Lets be explicit and declaritive.

### 5. `sourcing` serialization format
- **Fixture format**: `{field: "string", source_url: "https://..."}`
- **SourceObj model format**: `{field: ["string"], source_url: {"key": "https://..."}}`
- **Impact**: Format mismatch on `field` type (str vs list) and `source_url` type (str vs dict)
- **Resolution needed**: Maintainer to clarify canonical format. Options: (a)
  update SourceObj model, (b) update fixtures to match model format, (c) custom
  serialization in dump methods.
- Resolution: b update fixtures to match model format. 

### 6. Division `geometries` content
- **Fixture**: Has arcGIS address and null geometry components
- **Generated**: `[]` (geo lookup disabled in test with `division_geo_req=False`)
- **Resolution**: Accept as expected behavior when geo lookup disabled, OR add
  static arcGIS URLs to seed data.
Resolution: change to division_geo_req = True. All tests should pass including
argGIS request links.

### 7. Jurisdiction `url`, `term`, `metadata.urls`
- **Fixture**: Contains researched URLs, term descriptions, metadata
- **Generated**: Placeholder URL, `None` term, empty metadata
- **Resolution**: Seed data lookup (see implementation plan below).

## Implementation Plan

### Phase 1 — Fix the 25 known failures (Task #2, #3)
1. `generate_division.py`: Set `accurate_asof=self.req.asof_datetime` in `generate_division()` and `generate_division_stub()`
2. `generate_jurisdiction.py`: Set `accurate_asof=self.req.asof_datetime` in `generate_jurisdiction()`; pass `metadata={"urls": []}` as minimum valid

### Phase 2 — Fix serialization mismatches (Task #5, #6)
3. Customize division YAML dump to exclude extra null fields and match fixture structure
4. Normalize sourcing format in dump methods to match fixture format

### Phase 3 — Fix logic issues (Task #7, #8)
5. Verify/fix `jurisdiction_id` derivation for all 5 OCD ID patterns
6. Fix jurisdiction name generation to match fixture names

### Phase 4 — Update JurGenerator Generator to correctly generate jurisdictions (Task #9)
7. Do not generate a fall back. The test must pass completely independently of
   the expected output data. 


### Phase 5 — Unit tests (Task #10)
8. Create `tests/src/init_migration/test_generate_pipeline.py` with unit tests per method
9. Use `@pytest.mark.integration` for integration tests, plain marks for unit tests
10. Use Hypothesis for property tests on name/ID generation functions
11. Use `@pytest.mark.parametrize` for multi-case method tests

## 5 Sample Records

| Division OCD ID | Jurisdiction OCD ID | GEOID | Notes |
|----------------|--------------------|----|-------|
| `ocd-division/country:us/state:ca/place:sausalito` | `.../sausalito/government` | 0670364 | Standard city |
| `ocd-division/country:us/district:dc/anc:1a/council_district:1` | `.../anc:1a/government` | null | ANC, no Census GEOID |
| `ocd-division/country:us/state:wa/place:seattle/council_district:1` | `.../seattle/government` | 5363000 | Council district → city govt |
| `ocd-division/country:us/state:wa/place:tacoma` | `.../tacoma/government` | 5370000 | Standard city |
| `ocd-division/country:us/state:tx/place:austin/council_district:8` | `.../austin/government` | 4845390165 | Council district → city govt |

## LSAD Context (Issue #41)

Per issue #41 and the Census LSAD PDF, generate generalizable jurisdiction rules
that apply to each type of LSAD contained in this file (not just the sample
records):
https://docs.google.com/spreadsheets/d/e/2PACX-1vTUuNyO5rrnih_u1YhRoaSN969f5PzRCkA2I8np4PW7V0G0S7sLAx_Kk-CxU5RhYowKbYnPKdE_PHFD/pub?gid=1033358375&single=true&output=csv
This pipeline should include heuristics for correctly each type of LSAD included
in the PDF. This may involve branching and heirarchical decision trees to
resolve whether a jurisdiction should be created and the classification. It must
be applied accurately for each of these LSAD categories that are included in the
dataset as well as future divisions that might include identifiers not included
in the research set. Treat "0" as "00" (leading 0 dropped in .csv)

## Success Criteria

- [ ] `test_generate_pipeline_main_style_integration` passes (currently passing)
- [ ] `test_generate_pipeline_creyton_sample_comprehensive` passes with 0 validation errors
- [ ] All fixable Phase 5 discrepancies resolved
- [ ] Remaining discrepancies (id format, sourcing format) resolved according to
  resolution instructions.
- [ ] Unit tests cover every public method in generate_pipeline.py, generate_division.py, generate_jurisdiction.py
- [ ] `uv run ruff check .` passes
- [ ] `uv run pytest -m "not integration and not slow"` passes
