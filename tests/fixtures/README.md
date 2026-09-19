# Golden harness input fixtures

Controlled, offline inputs for the Phase 3 golden harness (issue #134).
Each directory holds source-shaped fixtures for one adapter. They are
populated as the upstream pipeline stages land; today the harness runs on
inline model records (`tests/golden/records.py`).

## Directories

- `census_governments/` — Census Government Units Survey rows (Phase 4.1).
- `tiger/` — TIGER metadata rows for state/county/place/county-subdivision/
  school-district (Phase 4.2).
- `ocd_master/` — OCD master membership samples for exact-match lookup
  (Phase 4.3).
- `sources/` — `SourceObj` provenance fixtures shared across the above.

## Input-to-golden mapping (Task 3.2, deferred)

When the Phase 4–10 pipeline exists, every golden record under
`tests/sample_output/` maps back to a controlled input here, so the golden
tree is reproducible offline. Until then this layout only reserves the
contract; do not wire it into tests.

## Rules

- Fixtures are read-only inputs. Never regenerate `tests/sample_output/` from
  a test (root `AGENTS.md`).
- Keep fixtures minimal and human-readable; prefer the real source column
  names so adapters can be tested against realistic shapes.
