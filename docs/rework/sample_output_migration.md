---
id: sample-output-migration
type: rework-migration-log
owner: rework
status: active
last_updated: 2026-09-03
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

## Task 2.3 — Geometry representation (2026-09-03)

**Issue:** #133 (Phase 2 tracking)

### Structural changes landing this task

1. **`Geometry` is provider-neutral and temporally scoped.**
   - Old shape:
     `Geometry(start: datetime, end: datetime, boundary: Boundary,
     children: list[str], arcGIS_address: str)` — `arcGIS_address` was
     required and named for one provider.
   - New shape:
     `Geometry(valid_from: datetime | None, valid_to: datetime | None,
     boundary: Boundary, url: HttpUrl | None,
     identifiers: Identifiers | None, source: SourceObj | None)`.
   - Rationale: rework §18 (external identifier + URL + Source +
     `valid_from` + `valid_to`, ArcGIS is an implementation detail) and
     §21 (a Division retains identity while its geometry changes).

2. **`start` / `end` renamed to `valid_from` / `valid_to` and made
   nullable.** Field name and JSON key rename together — the model field
   *is* the YAML key. Both ends are now open-endable: `valid_from: null`
   means an unbounded start, `valid_to: null` means a current boundary
   (which the old `end` docstring already claimed but the type forbade).

3. **`arcGIS_address: str` replaced by `url: HttpUrl | None`.** Any
   http(s) provider is accepted (DCGIS, a city ArcGIS Hub, a plain
   GeoJSON file); nothing requires a `tigerweb.geo.census.gov` host.
   Typing it as `HttpUrl` also normalizes the value — see the
   percent-encoding note under *expected diffs* below.

4. **`children: list[str]` moved from `Geometry` to `Division`.** Listing
   the child Divisions of a parent is a Division-level relationship, not a
   property of one temporal boundary version — rework §26 models
   `PARENT_OF` as a Division↔Division edge and `HAS_GEOMETRY` as a
   separate one. It also tightens from `list[str]` to `list[OCDIdStr]`,
   so a malformed child id fails at load time instead of passing through
   silently; `default_factory=list` is unchanged. The capability
   is **preserved, not deferred**: no Phase 2 task currently owns
   `PARENT_OF` (Task 2.5 is scoped to Jurisdiction↔Division —
   `GOVERNS`/`SERVES`/`OVERLAPS`/`CONTAINED_BY`), so dropping it here
   would have left it unowned.

5. **Per-geometry provenance and external identifiers added.** Each
   geometry version carries its own `source: SourceObj` and its own
   `identifiers: list[Identifier]` (the Task 2.4 container), so a
   Division whose boundary came from Census TIGER in one period and from
   a municipal portal in another attributes each version correctly.

6. **New helper `sort_geometries(geometries)`** orders versions
   oldest-first by `valid_from`, with `None` (unbounded start) first and
   a stable sort for ties, so multi-version serialization stays
   deterministic (rework §32).

### Changes deferred to Phase 11 (#142)

No YAML under `tests/sample_output/` is edited by this task. Three
fixtures carry a real `Geometry` entry; the other three carry
`geometries: []` and are unaffected.

| Fixture | Current geometry keys | Expected after regen |
| --- | --- | --- |
| [`divisions/test/ca/local/sausalito_5ebd7367-….yaml`](../../tests/sample_output/divisions/test/ca/local) (inventory §2.1) | `start`, `end`, `boundary`, `children`, `arcGIS_address` | `valid_from`, `valid_to`, `boundary`, `url`, `identifiers` (`census`/`geoid` = `0670364`), `source` (Census TIGER/Line) |
| [`divisions/test/ca/local/marin_city_322f0412-….yaml`](../../tests/sample_output/divisions/test/ca/local) (inventory §2.2) | same five keys | same six keys; `identifiers` = `census`/`geoid` = `0645820`, `source` = Census TIGER/Line |
| [`divisions/test/dc/local/anc_1a_district_1_35e1a717-….yaml`](../../tests/sample_output/divisions/test/dc/local) (inventory §2.3) | same five keys | same six keys; `identifiers` = `dcgis`/`anc_id` = `1A`, `source` = DCGIS |
| Seattle CD 1, Tacoma, Austin CD 8 (inventory §2.4–§2.6) | `geometries: []` | unchanged — `geometries: []` |

Separately, **all six** division fixtures gain a top-level `children: []`
key (moved off `Geometry`; see change 3 above). The three geometry-bearing
fixtures lose the nested `geometries[].children: []` at the same time, so
for those three it is a relocation rather than an addition.

Shape of the expected Phase 11 diff, per geometry-bearing fixture:

```diff
 geometries:
-- arcGIS_address: https://tigerweb.geo.census.gov/…/MapServer/4/query?where=GEOID%3D'0670364'&…
-  boundary:
+- boundary:
     centroid: null
     extent: null
-  children: []
-  end: '2025-10-27T01:29:51Z'
-  start: '2025-10-27T01:29:51Z'
+  identifiers:
+  - authority: census
+    id_type: geoid
+    source: {…SourceObj…}
+    value: '0670364'
+  source: {…SourceObj…}
+  url: https://tigerweb.geo.census.gov/…/MapServer/4/query?where=GEOID%3D%270670364%27&…
+  valid_from: '2025-10-27T01:29:51Z'
+  valid_to: '2025-10-27T01:29:51Z'
```

and, at the top level of every division fixture:

```diff
 also_known_as: []
+children: []
 country: us
```

Classification per instruction §35: **`STRUCTURAL`**, with one
**`EXPECTED_NEW_FIELD`** component (`identifiers`, `source`).

Two narrower diffs ride along and should be called out at review time:

- **URL percent-encoding normalization.** `HttpUrl` normalizes the raw
  apostrophes in the two TIGERweb URLs: `where=GEOID%3D'0670364'`
  becomes `where=GEOID%3D%270670364%27` (likewise `'0645820'`). The DCGIS
  URL is already encoded and is unchanged. Semantically identical
  request, different bytes on disk. Classification: **`STRUCTURAL`**.
- **`valid_to` currently equals `valid_from`** in all three fixtures
  (both `2025-10-27T01:29:51Z`), inherited verbatim from the old
  `start`/`end` pair. Read literally that says each boundary was retired
  the instant it took effect, which is almost certainly wrong — these
  are current boundaries and `valid_to` should be `null`. This task
  preserves the values verbatim (instruction §33: existing sample values
  are a baseline; do not change semantics to make a diff look tidy). The
  correction is a maintainer decision for Phase 11 and would classify as
  **`BUG_FIX`**.

### Non-goals for this task

- No changes to `tests/sample_output/**` YAML (root `AGENTS.md`
  §"Testing Rules"; rework plan §"Sample Output Change Control" §1).
- No new Division↔Division edge *semantics* beyond the relocated
  `children` list — populating it from the OCD hierarchy, and the
  `SERVES`/`OVERLAPS`/`CONTAINED_BY` edges, remain Task 2.5 and later.
- No dedup of the `Division.sourcing[]` entries whose `field` is
  `["geometries"]`, now redundant with per-geometry `source`. Same
  deferral as Task 2.4: Phase 2.2 or Phase 11.
- No change to `Boundary`, `Centroid`, or `Extent`; all three fixtures
  still emit `boundary: {centroid: null, extent: null}`.

### Verification

- `uv run pytest tests/src/models/test_division.py tests/src/init_migration/`
  — 106 passed. New unit tests:
  - `test_geometry_json_round_trip_is_lossless`
  - `test_geometry_validity_window_accepts_none`
  - `test_division_geometry_versions_sort_by_valid_from`
  - `test_geometry_url_is_provider_neutral`
  - `test_division_children_lists_child_division_ids`
  - `test_division_children_defaults_to_empty_list`
  - `test_division_children_rejects_malformed_ocdids`
- `uv run pytest -m "not integration and not slow"` — 159 passed, 15
  deselected, from a clean working tree. **No golden test fired**: the
  Phase 3 harness (#134) that diffs regenerated output against
  `tests/sample_output/**` does not exist yet, so the drift documented
  above is latent. It will surface the first time Task 3.3/3.4 runs, and
  that failure is the #142 signal — not a fixture to patch.
- `uv run ruff check .` — all checks passed.
