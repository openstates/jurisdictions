---
id: sample-output-migration
type: rework-migration-log
owner: rework
status: active
last_updated: 2026-08-15
tags: [rework, phase-2, models, sample-output, migration]
scope: "Structural changes to Pydantic models that will require regeneration of tests/sample_output/** in Phase 11 (#142)."
---

# Sample Output Migration Log

Per `ai_tools/planning/census-pipeline-rework-plan.md` §"Sample Output
Change Control" (Task 2.7), every Phase 2 change that affects the shape
of checked-in golden fixtures under `tests/sample_output/` is logged
here. YAML under `tests/sample_output/` is **not** edited by these
tasks — a maintainer regenerates it in Phase 11 (issue #142) with the
explicit fixture-regeneration command from Task 3.5.

This document is the audit trail that Phase 11 works from.

## Task 2.4 — External identifiers (2026-08-15)

**Issue:** #133 (Phase 2 tracking)

### Structural changes landing this task

1. **`Division.government_identifiers` shape replaced.**
   - Old shape: single `GovernmentIdentifiers` model with hard-coded Census
     fields (`namelsad`, `statefp`, `sldust: list[str]`,
     `sldlst: list[str]`, `countyfp: list[str]`, `county_names: list[str]`,
     `cousubfp: Optional[str]`, `placefp: Optional[str]`, `lsad`, `geoid`,
     `common_names: Optional[list[str]]`).
   - New shape: `Optional[list[Identifier]]` where
     `Identifier(authority: str, id_type: str, value: str, source: SourceObj)`.
   - Rationale: rework §22 — provider-neutral, source-tagged external
     identifiers; leading zeros preserved because `value` is always `str`.
   - The type alias `Identifiers = list[Identifier]` is exposed for
     annotation use.
   - New helper `find_identifier(identifiers, id_type, authority='census')`
     replaces attribute access.

2. **Per-identifier provenance is required.**
   - Every `Identifier` carries its own `SourceObj`. Divisions built from
     multiple providers (Census TIGER, DCGIS, NCES, …) can now attribute
     each identifier to the correct authority.

### Changes deferred to Phase 11 (#142)

Regeneration of every YAML file under `tests/sample_output/divisions/**`
is deferred. After Task 2.4 lands, running the Phase 3 golden harness
against those fixtures **will** produce a non-empty diff — that failure
is the signal to open #142 work, not a fixture to patch.

Structural diffs expected under `government_identifiers`:

| Fixture | Current shape | Expected after regen |
| --- | --- | --- |
| every division fixture | dict of Census fields (`namelsad:`, `statefp:`, `sldust: [ ... ]`, …) | list of `{authority, id_type, value, source}` entries |
| every division fixture | `sourcing[?].field == ["government_identifiers"]` may become redundant with per-identifier `source` — dedupe decision belongs to Phase 11 or Phase 2.2 |

Also folded in as pre-existing structural drift the same #142 pass will
need to reconcile:

- **`common_name` → `common_names` rename** (commit 6935b7a on
  `131-gus-pipeline-rework`). Six fixtures under
  `tests/sample_output/divisions/**/*.yaml` still emit
  `common_name: null`. The new field name is `common_names`; nothing
  currently *reads* it back through the model, so no runtime failure
  today.
- **`geoid_12` and `geoid_14` fields removed** from the model contract.
  Six fixtures still emit `geoid_12: null` / `geoid_14: null`; because
  the new model doesn't declare these keys they are ignored on load
  (Pydantic's default `extra="ignore"`), and they will disappear on
  regen.

### Non-goals for this task

- No changes to `tests/sample_output/**` YAML files (per root
  `AGENTS.md` §"Testing Rules" and rework plan §"Sample Output Change
  Control" §1).
- No dedup of `Division.sourcing[]` entries whose `field` equals
  `["government_identifiers"]`. Those blocks are now redundant with
  per-identifier `source`; the dedup decision belongs to Phase 2.2
  (`Source/Sourcing`) or Phase 11 (regen).
- No fixes to the flagged leading-zero anomalies from
  [`sample_output_inventory.md`](sample_output_inventory.md) §3.2
  (Austin `sldust: ["25"]`, mixed-quoted YAML scalars). The fixture
  module preserves the current values verbatim.

### Verification

- `uv run pytest tests/src/models/test_division.py` — new unit tests:
  - `test_identifier_json_round_trip_preserves_leading_zeros` (rework §22
    round-trip regression guard)
  - `test_identifier_rejects_missing_source`
  - `test_find_identifier_returns_first_match_by_authority_and_type`
- `uv run pytest tests/src/init_migration/` — existing integration tests
  for `DivGenerator`, `JurGenerator`, and ancestor stubs still pass
  against the new shape.
