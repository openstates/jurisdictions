---
id: sample-output-migration
type: rework-migration-log
owner: rework
status: active
last_updated: 2026-09-14
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

## URL fields typed as `HttpUrl` (2026-09-04)

**Issue:** #133 (Phase 2 tracking)

Maintainer-directed typing pass across `src/models/`: every URL-bearing
field is now a validated Pydantic URL type rather than a bare `str`. This
overlaps Task 2.6 (which also wants `Jurisdiction.url` **nullable** per
rework §23) and Task 2.2 (`SourceObj` schema growth), but is neither —
it landed on its own at maintainer request. `Jurisdiction.url` remains
**required**; the nullable half of Task 2.6 is still outstanding.

### Structural changes landing this change

| Model | Field | Before | After |
| --- | --- | --- | --- |
| `Jurisdiction` | `url` | `str` | `HttpUrl` |
| `URLObject` | `url` | `str` | `HttpUrl` |
| `TermDetail` | `source_url` | `str` | `HttpUrl` |
| `SourceObj` | `source_url` | `dict[str, AnyHttpUrl \| FtpUrl \| FileUrl]` | `dict[str, HttpUrl \| FtpUrl \| FileUrl]` |

`Geometry.url` was already `HttpUrl | None` as of Task 2.3, so no URL
field in `src/models/` is an unvalidated `str` any more.

Two properties of this change worth recording:

1. **A malformed URL now fails at construction** instead of being stored
   verbatim. This is a tightening: records that previously round-tripped
   junk will now raise `ValidationError`.
2. **`HttpUrl` is marginally stricter than `AnyHttpUrl`** — it enforces a
   2083-character maximum. Verified empirically; no value in the repo is
   near that bound.

### Deliberate deviation: `SourceObj.source_url` keeps `FtpUrl | FileUrl`

Only the `AnyHttpUrl` member of the union was swapped for `HttpUrl`. The
union itself was **kept**, not collapsed to `HttpUrl` alone, because the
Census distributes TIGER/Line over FTP and this pipeline plausibly needs
to cite an `ftp://` dataset. Collapsing the union would be a capability
regression, not a tightening. All 30 `source_url` values across the
golden files are `https://`, so nothing exercises the `ftp`/`file`
members today. Revisit under Task 2.2 if the container is reworked.

### Expected Phase 11 diff (#142): none

Every real value flowing into these fields was checked **before** the
type change: 18 values in the golden files (`URLObject.url`,
`TermDetail.source_url`) plus 24 in
[`tests/fixtures/jurisdictions_sample.py`](../../tests/fixtures/jurisdictions_sample.py).
All serialize byte-identically under `HttpUrl`.

Confirmed afterwards by loading each golden Jurisdiction through the
model and diffing every URL field of the re-dump against the file on
disk: **5 of 6 load with zero drift**; the sixth
(`marin_city_community_services_district_governing_board_…`) fails for an
unrelated pre-existing reason (see below).

`HttpUrl` normalization only affects a **bare host with an empty path**
(`https://x.gov` → `https://x.gov/`). Path-form URLs are left alone,
including the shapes present here:

| Shape | Example | Normalized? |
| --- | --- | --- |
| bare host + slash | `https://tacoma.gov/` | no |
| document path | `https://cityoftacoma.legistar.com/Calendar.aspx` | no |
| query string | `https://library.municode.com/…?nodeId=CH_ARTIIIEL_S2ELDACOTEELMARFEL` | no |
| deep path | `https://oanc.dc.gov/anc-profile/anc-1a` | no |
| bare host, no slash | `https://www.austintexas.gov` | **yes** → adds `/` |

The last row was the only occurrence in the repo, and it was normalized
in the fixture *before* this typing change — see *Fixture value
normalizations* below. Had it not been, this change would have silently
rewritten Austin's `url` on the next regeneration. That ordering is the
reason this pass contributes zero drift.

### Caller changes

- `src/init_migration/generate_jurisdiction.py` — no change needed. The
  fabricated fallback `https://opencivicdata.org/division/{division.ocdid}`
  passes `HttpUrl` unchanged despite the colons in the embedded OCDID.
  (Whether that fabrication should exist at all is still a Task 2.6
  question — rework §23 argues it should not.)
- **All YAML output is unaffected.** Both dump paths
  (`Jurisdiction.dump_jurisdiction`, `JurGenerator.dump_jurisdiction`)
  already use `model_dump(mode="json")`, which serializes a Pydantic URL
  to a plain string. A `model_dump()` without `mode="json"` would now
  emit `Url` objects that `yaml.safe_dump` cannot represent — worth
  knowing if a new dump path is ever added.
- `tests/src/init_migration/test_generate_jurisdiction.py` —
  `test_generated_jurisdiction_fallback_url` used
  `"opencivicdata.org" in jurisdiction.url`. `HttpUrl` is not a `str`
  subclass in Pydantic v2, so both assertions now compare against
  `str(jurisdiction.url)`. This is the only production-code-adjacent
  breakage the change caused.
- `tests/fixtures/jurisdictions_sample.py`,
  `tests/fixtures/divisions_sample.py`,
  `tests/sample_data/ohio_jurisdictions_licking_county.py` — no changes;
  all values validate as-is. (The Ohio module is not imported by any
  test.)

### Known pre-existing breakage, not addressed here

Both predate this change and were verified to fail identically before it:

- **`MARIN_CITY_CSD_JURISDICTION` fails `validate_jurisdiction_id`.** Its
  OCDID ends `/governing_board`, which is not a `ClassificationEnum`
  value, so the validator rejects it. This makes
  `tests/fixtures/jurisdictions_sample.py` **unimportable as a module**
  and makes the Marin City golden file unloadable through the model. See
  [`sample_output_inventory.md`](sample_output_inventory.md) §3.4 and
  [`model_inventory.md`](model_inventory.md) §6.11.
- **`src/models/jurisdiction.py` `__main__` demo block** constructs a
  `Jurisdiction` with no `ocdid` and a `SessionDetail` where a `dict`
  belongs. It raised `ValidationError` before and still does.
- **`src/models/division.py` has `ruff format` drift** from Task 2.4 (a
  long `raise ValueError` line in `dump_division`). `ruff check` passes,
  so it was left rather than mixing an unrelated reformat into this
  change.

### Verification

- `uv run pytest -m "not integration and not slow"` — 161 passed,
  15 deselected.
- `uv run ruff check .` — all checks passed.
- New unit tests in `tests/src/models/test_jurisdiction.py`:
  - `test_jurisdiction_url_round_trips_exact_string` — asserts each of
    the six golden `url` values dumps byte-identically. This is the guard
    that turns a future silently-normalized value into a loud test
    failure rather than unexplained Phase 11 drift.
  - `test_jurisdiction_url_rejects_non_http_values` — covers a bare
    hostname, free text, an `ftp://` URL, and the empty string.


## Task 2.6 (remainder) — Nullable website (2026-09-05)

**Issue:** #133 (Phase 2 tracking)

Completes Task 2.6. The typing half landed separately as `ad6aa45`
(§"URL fields typed as `HttpUrl`" above); this is the rework §23 half —
"missing official websites must not invalidate otherwise valid
Jurisdictions. Website resolution is a separate enrichment concern."

### Structural changes landing this task

1. **`Jurisdiction.url: HttpUrl` → `HttpUrl | None`, default `None`.**
   The inner type stays `HttpUrl`, so a malformed non-empty value is
   still rejected — `None` is the escape hatch, not a loose string. The
   empty string remains invalid and is **not** coerced to `None`
   (regression-tested).

2. **Two URL fabrication sites removed.** Neither was a website.

   | Site | Was | Now |
   | --- | --- | --- |
   | `generate_jurisdiction.py:141` | `fallback_url = f"https://opencivicdata.org/division/{division.ocdid}"`, used whenever `_ai_lookup` returned `None` | `url = (ai or {}).get("url")` — `None` when unresolved |
   | `generate_recursive.py:191` | same synthetic address on every ancestor stub Jurisdiction | `url=None` |

   The second site was not listed in `model_inventory.md` §6.2 and is easy
   to miss — it fabricated the identical string in a different module.

   `_ai_lookup` returns `None` on its only non-raising path (AI lookup is
   unimplemented; `jurisdiction_ai_url=True` raises
   `NotImplementedError`). So the fabrication was not an edge case — it
   was what **every** generated Jurisdiction received, baking an OCDID
   into a synthetic URL in direct contradiction of §23.

   OCD provenance is retained where it belongs: the
   `sourcing[].source_url["division"]` entry at
   `generate_jurisdiction.py:166` is unchanged. That records where the
   record came from; it was never a claim about the jurisdiction's
   website.

### `model_inventory.md` §6.2 risk claim — not substantiated

§6.2 warned that removing the fallback "may break existing quarantine
paths". Checked before acting:

- **Zero readers of `Jurisdiction.url` anywhere in `src/`.** The only
  code that branched on the fabricated value was the test asserting it.
- The quarantine-adjacent modules (`geoid_exception.py`,
  `ocdid_matcher.py`, `main.py`, `generate_pipeline.py`) do not read
  `url`. `generate_pipeline.py` generates and dumps a Jurisdiction; it
  never reads the field back.

§6.2 should be updated to record that the risk did not materialize.

### Expected Phase 11 diff (#142): none

All six jurisdiction fixtures carry a real `url`, so a nullable field
holding those same values serializes byte-identically. Verified by
loading each golden file through the model and comparing the re-dumped
`url` against the file on disk: **5 of 6 zero drift**; the sixth
(Marin City CSD) fails to load for the unrelated pre-existing reason
noted below.

**Generated (non-golden) output does change**, and the two dumpers differ
in how they express absence:

| Dumper | `exclude_none` | A url-less Jurisdiction emits |
| --- | --- | --- |
| `JurGenerator.dump_jurisdiction` (`generate_jurisdiction.py:242`) | `False` | `url: null` |
| `Jurisdiction.dump_jurisdiction` (`jurisdiction.py:233`) | `False` | `url: null` |
| `_write_stub_jurisdiction` (`generate_recursive.py:201`) | `True` | key omitted entirely |

This asymmetry is pre-existing, not introduced here, but it only becomes
observable now that `url` can be `None`. Whether stub output should also
emit explicit nulls is a Phase 10 (YAML rendering) consistency question.
Working-tree output under `jurisdictions/**` is affected;
`tests/sample_output/**` is not, because the golden fixtures are dumped
from `tests/fixtures/*_sample.py` rather than from `JurGenerator`.

### Existing tests updated

- `test_generate_jurisdiction_basic` — `assert jurisdiction.url is not
  None` inverted to `is None`.
- `test_generated_jurisdiction_has_required_fields` — the `url` assertion
  removed; `url` is no longer a required field, so leaving it in that
  list (and under its "Required fields per Jurisdiction model" comment)
  would have been wrong. Docstring now says why it is absent.
- `test_generated_jurisdiction_fallback_url` → renamed
  `test_generated_jurisdiction_does_not_fabricate_url` and inverted into
  a §23 regression guard: asserts `url is None` **and** that the OCD
  reference is still present in `sourcing`, so a future change cannot
  satisfy it by dropping provenance too.
- `test_ensure_ancestor_stubs_jurisdiction_uses_model_fields` —
  `assert "url" in jur_data` → `not in`, because that dumper uses
  `exclude_none=True` and now omits the key.

`tests/fixtures/jurisdictions_sample.py` unchanged; all six values remain
valid against the looser type (§33).

### Non-goals

- No `tests/sample_output/**` edits.
- No change to `ensure_uuid5_id` (Task 2.1).
- No `SourceObj` changes (Task 2.2).
- No field rename to `website`. `url` is the OCD spec field name and all
  six fixtures emit `url:`; renaming adds #142 churn for no semantic
  gain.
- The stub-vs-generator `exclude_none` asymmetry above is documented, not
  reconciled.

### Known pre-existing breakage, not addressed here

- `MARIN_CITY_CSD_JURISDICTION` fails `validate_jurisdiction_id` (OCDID
  trailing segment `governing_board` is not a `ClassificationEnum`
  value). Makes `tests/fixtures/jurisdictions_sample.py` unimportable as
  a module and the Marin City golden file unloadable. Deferred to
  Phase 7 per [`model_inventory.md`](model_inventory.md) §8; see
  [`sample_output_inventory.md`](sample_output_inventory.md) §3.4.
- `src/models/division.py` `ruff format` drift from Task 2.4.

### Verification

- `uv run pytest tests/src/models/test_jurisdiction.py tests/src/init_migration/`
  — 104 passed.
- `uv run pytest -m "not integration and not slow"` — 165 passed,
  15 deselected (baseline at `ad6aa45` was 161).
- `uv run ruff check .` — all checks passed.
- New unit tests in `tests/src/models/test_jurisdiction.py`:
  - `test_jurisdiction_valid_without_url`
  - `test_jurisdiction_without_url_round_trips`
  - `test_jurisdiction_url_absence_does_not_change_uuid` (§5/§38 —
    identity must not move when a mutable fact changes)
  - `test_jurisdiction_empty_url_is_rejected_not_coerced_to_none`

## Task 2.2 — Source/Sourcing (2026-09-11)

**Issue:** #133 (Phase 2 tracking)

Rework §19: "Reuse the repository's existing Source/Sourcing model. Extend
it only when necessary to represent source name, dataset,
release/vintage/version, publication date, retrieval date, and URL. Do not
duplicate `vintage` when Source already represents it." Rework §20:
distinguish real-world validity time from source/observation time.

`SourceObj` is the most widely embedded model in the repo: 30 record-level
`sourcing[]` blocks across the 12 golden files, plus — since Tasks 2.4 and
2.3 — one nested `source` per `Identifier` and per `Geometry`. Every
change below was made with that blast radius in mind.

### Structural changes landing this task

1. **Four §19 fields added, all `X | None` with default `None`.**

   | Field | Type | §19 term | Meaning |
   | --- | --- | --- | --- |
   | `dataset` | `str \| None` | dataset | The product within the source, e.g. `TIGER/Line Shapefiles`, `Government Units Survey`, `ocd-division-ids/identifiers/country-us.csv` |
   | `release` | `str \| None` | release/vintage/version | The provider's own release label — a Census vintage (`2020`), a TIGER/Line release (`2024`), a git tag or SHA |
   | `publication_date` | `datetime \| None` | publication date | When the provider published that release |
   | `retrieval_date` | `datetime \| None` | retrieval date | When this pipeline fetched it |

   Optional-with-None is the `model_inventory.md` §6.4 mitigation: a
   required field would have broken all 30 existing blocks and every
   nested `source`. Tightening to required is Phase 11 work, after the
   fixtures carry values. `source_name` and `source_url` (the other two
   §19 items) already existed and are unchanged in meaning.

2. **`release` is one field, not three.** §19 writes
   "release/vintage/version" with slashes: three provider vocabularies for
   the same axis. The Census calls it a *vintage*, TIGER/Line calls it a
   *release* year, a git-hosted CSV has a *version* (tag or SHA). A
   `SourceObj` cites one dataset, so it has exactly one of these, in that
   provider's own terms. Three near-synonym fields would leave every
   author guessing which to fill and would violate §19's own second
   sentence — "do not duplicate `vintage`". The field description says
   so explicitly so nobody adds `vintage` alongside it later.

3. **`publication_date` / `retrieval_date` are observation time, not
   validity time (§20).** Both descriptions, and the class docstring, say
   in words that these are *when the source was published / fetched* and
   are **not** the same axis as `Geometry.valid_from` / `valid_to` or
   `Division.valid_asof` / `valid_thru`. This is the conceptual core of
   the task: a 2024 TIGER release (`publication_date`) fetched in 2026
   (`retrieval_date`) can describe a boundary that has been valid since
   2010 (`Geometry.valid_from`). Conflating the two axes is the failure
   mode §20 exists to prevent.

4. **`source_url` container normalized: keyed map → scalar.**
   - Old: `dict[str, HttpUrl | FtpUrl | FileUrl]` — a map that held
     exactly one entry everywhere it was ever used.
   - New: `HttpUrl | FtpUrl | FileUrl` — the URL itself.
   - **The `FtpUrl | FileUrl` members are kept** (ad6aa45's deliberate
     union: the Census distributes TIGER/Line over FTP). A unit test
     now guards an `ftp://` and a `file://` value so a future
     "tightening" to `HttpUrl` alone fails loudly.
   - **No label field was added.** `model_inventory.md` §6.4 suggested
     "scalar + optional label"; this task chose scalar only, for three
     reasons. (a) §19 does not list a label and says extend *only when
     necessary*. (b) The key did no work in the golden contract: all 30
     blocks use the single key `"url"`. (c) The four keys `src/` emitted
     into generated (non-golden) output each restate something already
     in `source_name` / `source_description`, or name the *dataset* —
     which §19 already gives a field for. Their dispositions:

     | Legacy key | Site | Disposition |
     | --- | --- | --- |
     | `civicdata` | `generate_division.py` full Division | folded into `dataset="civicdata.tech validation spreadsheet"` |
     | `ocd_repo` | `generate_division.py` stub Division | folded into `dataset="ocd-division-ids/identifiers/country-us.csv"` (the URL is that CSV) |
     | `ocd_repo` | `generate_recursive.py` stub Division and stub Jurisdiction | **dropped, `dataset` left `None`.** The URL at this site is `REPO_URL` = `https://github.com/openstates/jurisdictions` — *this* repository, not the OCD repo. The key was asserting a provenance the URL does not support; carrying it into `dataset` would have propagated the mislabel. Flagged below for Phase 9. |
     | `division` | `generate_jurisdiction.py` | dropped — fully restated by `source_name="derived_from_division"` and `source_description="Jurisdiction derived from Division object"` |

     A future source that genuinely needs two URLs is two `SourceObj`s.

5. **Legacy `{label: url}` maps are still accepted on load.** A
   `mode="before"` field validator unwraps a single-entry map and drops
   the key, so every existing golden block, every working-tree YAML
   under `divisions/**` / `jurisdictions/**`, and `Division.load_division`
   / `Jurisdiction.load_jurisdiction` keep working without a regen. A
   map with more than one entry — never valid data — raises rather than
   silently truncating. This shim is a migration aid, not a contract:
   **remove it in Phase 11 (#142)** once the fixtures are regenerated in
   scalar form, alongside the Optional → required tightening.

6. **`field` docstring corrected; no validator added.** The description
   claimed the list was "validated against the available fields in the
   model". It never was — there is no validator, and there never has
   been. It now reads: dotted field paths on the owning record, e.g.
   `['term', 'term.term_limits']`, free-form, not validated. Validation
   was considered and rejected for this task because (a) `SourceObj`
   does not know its owner — the same class sits on `Division`,
   `Jurisdiction`, `Identifier`, and `Geometry`; (b) existing values are
   dotted paths into nested models (`metadata.population`,
   `term.term_limits`, `metadata.urls`), some of which land on
   `extra="allow"` models where the key is not declared at all (ANC 1A's
   `metadata.source`); and (c) a correct implementation is therefore an
   owner-level validator with real design questions, which belongs with
   Phase 9 canonical model construction, where the owning model is known
   at build time. A lying docstring was the bug; it is fixed.

7. **`generate_jurisdiction.py` now constructs a `SourceObj`** instead of
   passing a dict literal into `sourcing=[...]`. Item 4 forced an edit to
   that literal (its `source_url` key), so the consistency fix rode
   along; the other four construction sites already used the class.

8. **`MODELS.md` §"SourceObj Model" rewritten.** It documented fields
   (`note`, `url`, `date_accessed`) that have never existed on this
   model, so it matched neither the old contract nor the new one. It now
   shows the real field set, the observation-time caveat, and one
   example in each of the minimal and fully-populated forms.

9. **`source_type` default changed from `HUMAN` to `AI`** (maintainer
   edit during approval). A `SourceObj` constructed without an explicit
   `source_type` now serializes `ai_generated` instead of
   `human_researched`, so provenance is conservative by default: a
   record only claims human research when someone says so. **No golden
   drift**: all 30 blocks carry an explicit
   `source_type: human_researched`, and every construction site in
   `src/` and `tests/` passes `source_type` explicitly. Only code that
   omits the argument sees the change. The `# Default` marker on the
   enum moved from `HUMAN` to `AI` to match.

### Deferred decisions settled

Three earlier entries in this log named Task 2.2. None is left dangling.

- **Task 2.4 deferral — `sourcing[]` entries whose `field` is
  `["government_identifiers"]`, now that each `Identifier` carries its own
  `source`.** **Resolved: keep them. They are not redundant.** The
  record-level `sourcing[]` list is the record's provenance *index* —
  "which sources contributed to this record" — answerable without
  walking nested structures, and it is what rework §26's `SOURCED_FROM`
  edge from a `Division` node projects from. The nested `source` is
  per-fact *attribution*, which is what `IDENTIFIED_BY`/`HAS_GEOMETRY`
  provenance projects from. Two different questions; two different
  edges. The real cost of the duplication is the *payload* repetition
  (Sausalito's regenerated YAML carries 12 copies of a `SourceObj`, 10 of
  them identical) — but that is a serialization concern: whether nested
  `source` fields should become references into the record-level
  `sourcing[]` is a Phase 10 (YAML rendering) decision, not a model one.
  Deduping now would also have forced value edits to six fixture
  sourcing lists for no semantic gain (instruction §33).
- **Task 2.3 deferral — the same question for `field == ["geometries"]`.**
  **Resolved identically: keep.** One extra reason applies here: Austin
  CD 8 and Seattle CD 1 list a geometry source in `sourcing[]` while
  `geometries` is `[]`. That is real information — "we know where the
  boundary comes from but have not resolved it yet" — that a nested
  per-geometry `source` cannot carry, because there is no geometry to
  hang it on.
- **ad6aa45 note — "Revisit under Task 2.2 if the container is
  reworked."** The container was reworked (item 4). The union survived
  the rework unchanged in membership and is now enforced by
  `test_source_url_still_accepts_ftp_and_file_schemes`. Resolved.

### Changes deferred to Phase 11 (#142)

No YAML under `tests/sample_output/` is edited by this task. Unlike
Tasks 2.6 and the `HttpUrl` typing pass, **this task produces a real
regeneration diff in every one of the 12 golden files**: every
`sourcing[]` block changes shape.

**Measured, not predicted.** Each golden Jurisdiction file was loaded
through the model and re-dumped (`yaml.safe_dump(model_dump(mode="json",
exclude_none=False))`, the golden dumper's settings) and diffed against
the file on disk, before and after this change. Golden Division files
cannot load through the model since Task 2.4 changed the identifier
shape, so each was instead regenerated from its fixture object in
`tests/fixtures/divisions_sample.py` — the same path Phase 11 uses — and
diffed. Marin City CSD cannot load for the unrelated pre-existing reason
below, so its single `sourcing[]` block was validated on its own.
"Before" was taken at `4fb9a18`.

Per `sourcing[]` block, under the golden dumper's `sort_keys=True`:

```diff
 sourcing:
--- field:
+- dataset: null
+  field:
   - url
+  publication_date: null
+  release: null
+  retrieval_date: null
   source_description: null
   source_name: Tacoma Official Site
   source_type: human_researched
-  source_url:
-    url: https://tacoma.gov/
+  source_url: https://tacoma.gov/
```

Keys that **appear** in every block: `dataset`, `release`,
`publication_date`, `retrieval_date` (all `null` — see the note below).
Key that **disappears**: the nested `source_url.url`; `source_url` itself
remains, now holding the string directly. Nothing else in the block
moves; the `- field:` → `- dataset:` shuffle is only the list-item opener
following the new alphabetically-first key. Six lines added, three
removed, per block.

Per file (golden blocks are the 30 record-level entries; "SourceObj
instances after regen" also counts the nested per-identifier and
per-geometry copies Tasks 2.4/2.3 introduced, every one of which takes
this new shape):

| Golden file | `sourcing[]` blocks | SourceObj instances after regen | Diff before 2.2 | Diff after 2.2 |
| --- | --- | --- | --- | --- |
| `divisions/…/marin_city_322f0412-….yaml` | 3 | 14 | +124 −22 | +175 −31 |
| `divisions/…/sausalito_5ebd7367-….yaml` | 2 | 12 | +113 −22 | +155 −28 |
| `divisions/…/anc_1a_district_1_35e1a717-….yaml` | 2 | 8 | +69 −19 | +99 −25 |
| `divisions/…/austin_council_district_8_6ab0a55b-….yaml` | 2 | 15 | +144 −22 | +195 −28 |
| `divisions/…/seattle_council_district_1_bb8a9dc8-….yaml` | 2 | 20 | +199 −27 | +265 −33 |
| `divisions/…/tacoma_a82e350d-….yaml` | 2 | 14 | +133 −21 | +181 −27 |
| `jurisdictions/…/marin_city_community_services_district_governing_board_fc24cff2-….yaml` | 1 | 1 | 0 | +6 −3 |
| `jurisdictions/…/sausalito_city_government_38f5f5e0-….yaml` | 3 | 3 | 0 | +18 −9 |
| `jurisdictions/…/anc_1a_government_ce723bd7-….yaml` | 4 | 4 | 0 | +24 −12 |
| `jurisdictions/…/city_of_austin_b60ab7ed-….yaml` | 3 | 3 | 0 | +18 −9 |
| `jurisdictions/…/seattle_city_government_bd405187-….yaml` | 3 | 3 | 0 | +18 −9 |
| `jurisdictions/…/tacoma_city_government_1c2a18a9-….yaml` | 3 | 3 | 0 | +18 −9 |
| **Total** | **30** | **100** | | |

The Division "before" columns are the Task 2.3/2.4 drift already logged
above; the six Jurisdiction files had **zero** drift before this task,
so their "after" column is the pure Task 2.2 diff. Of the 100 instances,
30 are record-level `sourcing[]` (13 Division + 17 Jurisdiction) and 70
are nested `Identifier.source` / `Geometry.source` copies.

Classification per instruction §35: **`STRUCTURAL`** (the `source_url`
container change) plus **`EXPECTED_NEW_FIELD`** (`dataset`, `release`,
`publication_date`, `retrieval_date`).

Three things to call out at Phase 11 review time:

- **All four new keys regenerate as `null`.** Nothing in the fixture
  modules or the generators populates them yet. Populating
  `retrieval_date` at generation time and `dataset`/`release` from
  snapshot metadata is Phase 4.4 (snapshot metadata) and Phase 9
  (canonical model construction) work; doing it here would have widened
  a model task into a pipeline one and, for `retrieval_date`, introduced
  a new non-injected timestamp (§32). Phase 11 may prefer to regenerate
  *after* Phase 4/9 land so the fixtures carry real values rather than
  four nulls per block; that ordering is the maintainer's call.
- **`SOURCE_CORRECTION` candidate: the "Decceennial" typo.**
  `source_name="Census 2020 Decceennial Census"` (sic) appears in
  [`tests/fixtures/divisions_sample.py`](../../tests/fixtures/divisions_sample.py)
  (`_MARIN_CITY_POPULATION_SOURCE`) and in the Marin City Division golden
  file. Left exactly as is (§33: existing sample values are a baseline).
  Correcting it to "Decennial" is a one-word value change for the Phase 11
  reviewer.
- **The `exclude_none` asymmetry logged under Task 2.6 now matters more.**
  The two `exclude_none=False` dumpers emit the four new keys as
  explicit nulls; `_write_stub_jurisdiction` (`exclude_none=True`) omits
  them entirely, so ancestor-stub YAML and full-record YAML will disagree
  on whether the keys exist. Still a Phase 10 rendering question; noted
  because Task 2.2 quadruples the number of keys it affects.

### Caller changes

| Site | Change |
| --- | --- |
| `src/init_migration/generate_division.py` (full + stub) | `source_url={key: url}` → `source_url=url`; legacy key folded into `dataset` (table in item 4) |
| `src/init_migration/generate_recursive.py` (stub Division + stub Jurisdiction) | `source_url={"ocd_repo": …}` → `source_url=…`; no `dataset` (see item 4) |
| `src/init_migration/generate_jurisdiction.py` | dict literal → `SourceObj(...)`; `source_url` scalar; `division` key dropped |
| `tests/fixtures/divisions_sample.py` | 7 × `source_url={"url": X}` → `source_url=X`; every other value verbatim |
| `tests/fixtures/jurisdictions_sample.py` | 17 × same; every other value verbatim |
| `tests/src/models/test_division.py` | 2 helper `SourceObj`s use the scalar form |
| `tests/src/init_migration/test_generate_jurisdiction.py` | `source.source_url.values()` → `str(source.source_url)` in the §23 provenance guard |
| `MODELS.md` | §"SourceObj Model" rewritten (item 8) |
| `src/models/division.py`, `tests/src/models/test_jurisdiction.py`, `tests/src/models/test_division.py`, `tests/src/init_migration/test_generate_jurisdiction.py` | docstring-only: rework §/Task/Phase/commit references left by Tasks 2.3, 2.4 and 2.6 removed (see note below) |

No `__init__.py` changes; no network in any touched path (§27).

**Process references do not belong in code.** Maintainer direction during
this task: comments, docstrings and `Field(description=...)` are read by
people who are not working on the rework, so they state the plain fact
("When the provider published this release.") and nothing about which
section, task, phase, issue or commit motivated it. That rationale lives
here and in the plan. This task stripped every such reference from
`src/` and `tests/src/`, including the ones earlier Phase 2 tasks
introduced; the observation-time / validity-time distinction (§20) is
still explained in the `SourceObj` class docstring, without the citation.

### Non-goals for this task

- No `tests/sample_output/**` edits (root `AGENTS.md` §"Testing Rules";
  plan §"Sample Output Change Control" §1).
- No change to `ensure_uuid5_id` (Task 2.1). The identity tests below
  assert against the *current* scheme.
- No Jurisdiction↔Division relationship work (Task 2.5).
- No "Decceennial" correction (logged above as a Phase 11
  `SOURCE_CORRECTION` candidate).
- No `vintage` or `version` field alongside `release` (§19).
- No population of the four new fields at any generation site
  (Phase 4.4 / Phase 9, see above).
- No dedup of `sourcing[]` against nested `source` (resolved as *keep*,
  above).
- No `exclude_none` reconciliation across the three dumpers (Phase 10).
- `tests/sample_data/ohio_jurisdictions_licking_county.py` untouched. It
  constructs `SourceObj(name=…, url=…, accessed_at=…, notes=…)` — a
  signature that has never existed on this model — so it did not import
  before this task and does not now. No test imports it. Flag for
  Phase 18 cleanup.

### Known pre-existing breakage, not addressed here

- `MARIN_CITY_CSD_JURISDICTION` fails `validate_jurisdiction_id` (OCDID
  trailing segment `governing_board` is not a `ClassificationEnum`
  value). Makes `tests/fixtures/jurisdictions_sample.py` unimportable as
  a module and the Marin City golden file unloadable. Deferred to Phase 7
  per [`model_inventory.md`](model_inventory.md) §8; see
  [`sample_output_inventory.md`](sample_output_inventory.md) §3.4.
- `ruff format` drift in `src/models/division.py` (Task 2.4), and — newly
  noted, verified against `HEAD` before any edit — in
  `src/init_migration/generate_division.py` (one `stub_geoid` line) and
  `tests/src/models/test_division.py` (three `Identifier(...)` lines and
  one `Geometry(...)` line). All on lines this task did not touch; left
  alone rather than mixing an unrelated reformat into a model change.
- `generate_recursive.py` cites `REPO_URL` (this repository) as the
  provenance for ancestor stubs whose `source_name` is
  `ocdid_recursive_stub` and whose description says "Open Civic Data".
  The URL and the claim disagree. Not changed here (adjacent scope);
  Phase 9 should decide whether stubs cite the OCD repo CSV, as the
  `generate_division.py` stub already does.

### Verification

- `uv run pytest tests/src/models/ tests/src/init_migration/` — 146
  passed. New module `tests/src/models/test_source.py` (13 tests):
  - `test_source_obj_without_new_fields_validates_and_round_trips`
    (backward compatibility: the legacy field set is still sufficient)
  - `test_source_obj_accepts_legacy_single_entry_url_map` /
    `test_source_obj_rejects_multi_entry_url_map` (item 5)
  - `test_source_obj_fully_populated_round_trips_losslessly` (dates
    included, tz-aware)
  - `test_publication_and_retrieval_dates_accept_none_independently`
    (3 parametrized cases)
  - `test_source_url_scalar_round_trips_exact_string` (four real golden
    URL shapes dump byte-identically)
  - `test_source_url_still_accepts_ftp_and_file_schemes` (ad6aa45 guard)
  - `test_source_url_rejects_non_url_values`
  - `test_source_metadata_does_not_change_division_uuid` /
    `test_source_metadata_does_not_change_jurisdiction_uuid` (§5, §19,
    §38 — release/retrieval/dataset changes leave the UUID fixed, and
    the two releases remain distinguishable)
  - `test_every_golden_sourcing_block_still_validates` — reads all 12
    golden files (reading is always permitted), validates each of the
    30 blocks under the new contract, and asserts the scalar `source_url`
    equals the legacy map's value. This is the literal "all 30 existing
    blocks still validate" proof.
- `uv run pytest -m "not integration and not slow"` — **178 passed, 15
  deselected** (baseline at `4fb9a18` was 165; +13 are the new tests).
  No golden test fired — the Phase 3 harness (#134) does not exist yet,
  so the drift tabulated above is latent until Task 3.3/3.4 runs, and
  that failure is the #142 signal, not a fixture to patch.
- `uv run ruff check .` — all checks passed.
- `uv run ruff format --check` on touched files — clean except the
  pre-existing drift in `generate_division.py` and `test_division.py`
  noted above.

## Task 2.1 — Stable UUID identity (2026-09-14)

**Issue:** #133 (Phase 2 tracking)

Rework §5: "Prefer stable UUIDs derived from stable identity, e.g.
`UUID5(OCDID)`. Mutable facts such as website, source release, geometry,
retrieval time, or update date must not change entity identity." Plan
Task 2.1: "UUID derived from stable OCD identity, not mutable timestamps."

### Structural changes landing this task

1. **Identity is `uuid5(NAMESPACE_URL, ocdid)`.** Before, both models
   derived `uuid5(NAMESPACE_URL, f"{ocdid}|{last_updated date}")`, so
   regenerating the same record on a different day produced a different
   `id` and a different filename. `last_updated` no longer participates.
   No new formula was invented: this is the form
   `src/init_migration/ocdid_matcher.py` already mints for
   `OCDidIngestResp.uuid` and writes to the `ocdid_uuid_lookup` table and
   CSV. The ingest UUID and the record `id` now agree for the same
   Division OCDid, which closes all three consequences listed in
   [`model_inventory.md`](model_inventory.md) §5.

2. **One identity function.** `Division.ensure_uuid5_id` and
   `Jurisdiction.ensure_uuid5_id` both call
   `src.utils.deterministic_id.generate_id(ocdid)`. That module existed
   but was not on the runtime path (§5 again); it now is. Its date
   parameter is gone: `generate_id(ocdid)`, `verify_id(identifier, ocdid)`,
   `decode_id(identifier)`. `build_uuid5_name` is removed — its only job
   was appending the date.

3. **An explicit `id` is still accepted, unchanged.** Every golden file
   carries an `id:` minted under the old formula and still loads; a
   golden file loaded and re-dumped shows **zero drift**. The migration
   below appears only when a record is regenerated from its fixture, which
   is what Phase 11 does. Whether the model should *reject* an explicit
   `id` that is not the UUID5 of its `ocdid` is a Phase 11 question to
   settle after regeneration — today that check would reject all 12 golden
   files.

4. **`id` field descriptions** on both models now say the value is derived
   from the ocdid alone and is stable across regenerations.

### Changes deferred to Phase 11 (#142): `IDENTIFIER_MIGRATION`

No YAML under `tests/sample_output/` is edited by this task. On
regeneration **every golden file changes its `id:` value and its
filename** (the filename embeds the id). Nothing else in any file moves:
no other field references a record id (`jurisdiction_id` and `children`
are OCDids).

**Measured, not predicted.** For each of the 12 golden files the checked-in
`id:` was confirmed to equal the old formula applied to its `ocdid` and
`last_updated` date, then the new id was computed from the `ocdid`. The
six Division fixture objects were dumped before (`c6e8e4c`) and after:
**exactly one line differs per file, `id:`**. The five loadable
Jurisdiction fixtures were constructed under the new scheme and their ids
match the table; Marin City CSD's is computed from its `ocdid`.

| Golden file | `id:` today | `id:` after regen |
| --- | --- | --- |
| `divisions/…/sausalito_….yaml` | `5ebd7367-a3e7-54dd-8994-47e5f2cc5f8f` | `c5c62304-e506-54bd-ab72-e4e14d62bba1` |
| `divisions/…/marin_city_….yaml` | `322f0412-0108-59a7-b29d-5f807672da64` | `90ae7478-23af-54cb-b444-aa8e5e1d8db5` |
| `divisions/…/anc_1a_district_1_….yaml` | `35e1a717-03a8-5257-8123-3b6dd493c38d` | `c738edad-1ed5-57f7-80a3-a9ca4488cbfb` |
| `divisions/…/austin_council_district_8_….yaml` | `6ab0a55b-03b8-57e2-9565-1f558058519e` | `34071538-4f6c-58fe-9a31-5900590cecf0` |
| `divisions/…/seattle_council_district_1_….yaml` | `bb8a9dc8-ed3c-59bc-ba1d-408a3c765dde` | `3f69bd27-211e-5717-8087-752df1db0bde` |
| `divisions/…/tacoma_….yaml` | `a82e350d-72bb-5b02-8375-b66c9d2b6126` | `c104c614-3662-5202-ac00-c348b7c31e4f` |
| `jurisdictions/…/sausalito_city_government_….yaml` | `38f5f5e0-64fa-5129-a944-bb9dcc385619` | `7539e65b-3a49-5e24-82b4-3a5bc6f72aad` |
| `jurisdictions/…/marin_city_community_services_district_governing_board_….yaml` | `fc24cff2-3baa-5768-8652-b2840233c61b` | `de0de79f-ab51-526c-b8e8-e3a8ea7336dc` |
| `jurisdictions/…/anc_1a_government_….yaml` | `ce723bd7-51c0-55b3-bc32-8d14a84c66ec` | `a598df3f-3f39-55a6-bb32-fe9e77b835e2` |
| `jurisdictions/…/city_of_austin_….yaml` | `b60ab7ed-add2-5de4-bd08-3da4aec2312b` | `69a2420e-4e10-5d98-8a7b-07c9b40811b1` |
| `jurisdictions/…/seattle_city_government_….yaml` | `bd405187-c499-5b44-aee8-3800784ee617` | `dd83c671-f854-59c5-bee3-21223377228f` |
| `jurisdictions/…/tacoma_city_government_….yaml` | `1c2a18a9-a8e3-586d-9968-502e8abb102e` | `104f8f72-25fb-56ae-9a22-b4f1e0ac8ccf` |

Each filename changes the same way, `<slug>_<old id>.yaml` →
`<slug>_<new id>.yaml`; the slug part is unchanged. Per file: one line
changed, one rename.

Classification per instruction §35: **`IDENTIFIER_MIGRATION`** — the
`sample_output_inventory.md` §3.6 prediction, now with the concrete
values. This is the last Phase 2 task, so the Phase 11 regeneration
collapses every Phase 2 change — including these 12 renames — into one
reviewed migration, which is why the plan ordered it last.

Two things to call out at Phase 11 review time:

- **The rename is the whole identity migration.** After regeneration a
  record's id is a pure function of its OCDid, so this is the last time
  the golden ids move for a non-OCDid reason. Task 3.7 (stable identity
  golden test) can then assert it.
- **The working-tree `ocdid_uuid_lookup.csv` needs no change.** The
  matcher already wrote ocdid-only UUIDs there; they now equal the
  Division ids the pipeline produces.

### Caller changes

| Site | Change |
| --- | --- |
| `src/utils/deterministic_id.py` | date parameter removed; `generate_id(ocdid)`, `verify_id(identifier, ocdid)`; `build_uuid5_name` deleted; module docstring states the formula |
| `src/models/division.py`, `src/models/jurisdiction.py` | `ensure_uuid5_id` calls `generate_id(self.ocdid)`; `uuid5`/`NAMESPACE_URL` imports dropped; `id` description updated |
| `tests/src/utils/test_deterministic_id.py` | rewritten for the date-free API (6 tests, same count as before) |
| `tests/src/models/test_division.py` | `test_division_id_defaults_to_uuid5_from_ocdid_and_date` → `…_of_ocdid`; new `test_division_mutable_facts_do_not_change_uuid` |
| `tests/src/models/test_jurisdiction.py` | same rename; new `test_jurisdiction_mutable_facts_do_not_change_uuid`; one docstring corrected |
| `tests/src/init_migration/test_generate_division.py`, `test_generate_jurisdiction.py` | fixture `OCDidIngestResp.uuid` built with the ocdid-only form the matcher uses (was date-suffixed); two now-unused imports removed |

Generators, fixtures and `MODELS.md` are unchanged: the generators never
passed an `id` (the model derives it), the fixtures never set one, and
`MODELS.md` already documents `id` as "UUID5 derived from ocdid". No
`__init__.py` changes; no network in any touched path (§27).

### Non-goals for this task

- No `tests/sample_output/**` edits (root `AGENTS.md` §"Testing Rules";
  plan §"Sample Output Change Control" §1).
- No rejection of an explicit `id` that disagrees with the ocdid (Phase 11,
  item 3 above).
- No change to `tests/integration/test_generate_pipeline_integration.py`.
  Its `_create_ocdid_ingest_resp` helper still builds a date-suffixed
  `OCDidIngestResp.uuid`; that value never reaches a record id, and all 11
  tests pass unchanged. Aligning it with the matcher's form is a one-line
  edit under `tests/integration`, which needs maintainer approval.
- No cleanup of the unused `uuid` parameters on
  `DivGenerator.generate_division` / `generate_division_stub` and
  `JurGenerator.generate_jurisdiction`, or of `get_jurisdiction_filename`'s
  stale "same as corresponding Division" docstring. The model derives the
  id; the parameters were already dead. Phase 9 rebuilds these paths.
- No Task 3.7 golden test (Phase 3 harness).

### Known pre-existing breakage, not addressed here

- `MARIN_CITY_CSD_JURISDICTION` fails `validate_jurisdiction_id`; Phase 7
  per [`model_inventory.md`](model_inventory.md) §8. Its new id in the
  table is computed from the `ocdid` string directly.
- `ruff format` drift in `src/models/division.py` (one line),
  `src/init_migration/generate_division.py` (one line) and
  `tests/src/models/test_division.py` (four lines), all on lines this
  task did not touch. Verified before editing; left alone.

### Verification

- `uv run pytest tests/src/models/ tests/src/init_migration/ tests/src/utils/`
  — 180 passed. New tests:
  - `test_division_id_defaults_to_uuid5_of_ocdid` /
    `test_jurisdiction_id_defaults_to_uuid5_of_ocdid` (hypothesis; the id
    equals `uuid5(NAMESPACE_URL, ocdid)` and `generate_id(ocdid)`).
  - `test_division_mutable_facts_do_not_change_uuid` — nine variants of
    one Division (different `last_updated` day, `accurate_asof`, a new
    `Geometry`, `sourcing` with and without a later `release` /
    `retrieval_date`, `government_identifiers`, `display_name` /
    `also_known_as`, `children`) share one id.
  - `test_jurisdiction_mutable_facts_do_not_change_uuid` — nine variants
    (different `last_updated` day, `accurate_asof`, `url`, `sourcing`
    with and without a later release, `term`, `metadata.urls`, `name`)
    share one id. Together with the existing
    `test_jurisdiction_url_absence_does_not_change_uuid` and the two
    `test_source_metadata_does_not_change_*_uuid` tests, this covers the
    four cases the plan names: website, source release, geometry,
    retrieval date.
  - `tests/src/utils/test_deterministic_id.py` — six tests for the
    date-free API, including that a Division and its Jurisdiction get
    different ids.
- `uv run pytest -m "not integration and not slow"` — **180 passed, 15
  deselected** (baseline at `f9c6751` was 178).
- `uv run pytest tests/integration/test_generate_pipeline_integration.py`
  — 11 passed, unchanged.
- `uv run ruff check .` — all checks passed.
- `uv run ruff format --check` on the eight touched files — clean except
  the pre-existing drift in `src/models/division.py` and
  `tests/src/models/test_division.py` noted above.
- Process-reference grep over `src/` and `tests/src/` — zero hits.

## Fixture value normalizations (not tied to a model task)

Value-level fixture edits that create golden drift without any model
contract change. Logged here because Phase 11 (#142) has to reconcile
them alongside the structural migrations above.

### TIGER 2025 geometry validity window and release (2026-09-18)

- **File:** [`tests/fixtures/divisions_sample.py`](../../tests/fixtures/divisions_sample.py)
  (`SAUSALITO_DIVISION.geometries[0]`, `MARIN_CITY_DIVISION.geometries[0]`,
  `_SAUSALITO_GEOMETRY_SOURCE`)
- **Change:** `valid_from` `2025-10-27T01:29:51Z` → `2025-01-01T00:00:00Z`;
  `valid_to` `2025-10-27T01:29:51Z` → `null`; the shared TIGER geometry
  source gains `release: '2025'`.
- **Affected golden fixtures:**
  `divisions/test/ca/local/sausalito_5ebd7367-….yaml` and
  `divisions/test/ca/local/marin_city_322f0412-….yaml`. On regeneration
  each gets `geometries[0].valid_from: 2025-01-01T00:00:00Z`,
  `valid_to: null`, and `release: '2025'` on `sourcing[0]` and on the
  nested geometry `source`.
- **Rationale (maintainer decision):** a Division file holds the boundary
  from one Census series. `valid_from` is that series' reference date;
  TIGER/Line 2025 boundaries are as of January 1, 2025. `valid_to` is
  populated only when the Census redefines the area, so an active boundary
  carries `null`. The same-day pair inherited from the old `start`/`end`
  fields said the boundary was retired the instant it took effect (Task 2.3
  entry above flagged it).
- **Classification per instruction §35:** `BUG_FIX` (the window) and
  `EXPECTED_NEW_FIELD` (`release`).
- **ANC 1A (same date, maintainer-confirmed):** `ANC_1A_DIVISION.geometries[0]`
  `valid_from` → `2023-01-01T00:00:00Z`, `valid_to` → `null`. Both DCGIS
  `SourceObj`s gain `dataset: "Advisory Neighborhood Commission - 2023"`,
  `release: "2023"`, `publication_date: 2022-12-21T00:00:00Z` (the layer's
  `CREATED` attribute) and `retrieval_date: 2025-10-27T01:29:51Z` (when the
  record was researched). Read from DCGIS layer 54 metadata: boundaries
  from the ANC Boundaries Act of 2022, in effect January 1, 2023. Affects
  `divisions/test/dc/local/anc_1a_district_1_35e1a717-….yaml` on
  regeneration. Classification: `BUG_FIX` (window) and
  `EXPECTED_NEW_FIELD` (the four provenance fields).
- **Not changed:** the three `geometries: []` fixtures.
- **Golden files:** unchanged; the dry run of
  `scripts/regenerate_sample_output.py` still reports 207 differences in 12
  files, with these values appearing in the existing `valid_from`,
  `valid_to`, and `release` lines.

### Austin Jurisdiction `url` trailing slash (2026-09-04)

- **File:** [`tests/fixtures/jurisdictions_sample.py`](../../tests/fixtures/jurisdictions_sample.py)
  (`AUSTIN_JURISDICTION.url`)
- **Change:** `https://www.austintexas.gov` → `https://www.austintexas.gov/`
- **Affected golden fixture:**
  `tests/sample_output/jurisdictions/test/tx/local/city_of_austin_b60ab7ed-add2-5de4-bd08-3da4aec2312b.yaml`
  (`url:`, one line). No other file changes.
- **Rationale:** Austin was the only one of the six Jurisdiction
  fixtures whose bare-host `url` lacked a trailing slash; the other four
  bare hosts (Seattle, Tacoma, Sausalito, Marin City CSD) all carry it,
  and ANC 1A's value is a path (`/anc-profile/anc-1a`) where a trailing
  slash does not belong. Maintainer requested the value be made
  consistent with the majority form.
- **Semantics:** unchanged. Per RFC 3986 §6.2.3 an empty path normalizes
  to `/`, so `https://www.austintexas.gov` and
  `https://www.austintexas.gov/` are the same URL. This is a
  presentation-level normalization, not a source correction.
- **Classification per instruction §35:** `SOURCE_CORRECTION`
  (cosmetic — no factual change).
- **Not changed:** the two path-bearing `austintexas.gov` URLs in
  `AUSTIN_JURISDICTION.metadata.urls`
  (`/department/city-council/…`, `/government`) keep their existing form.
- **Why it mattered:** this was the enabling precondition for the
  §"URL fields typed as `HttpUrl`" change above. Austin's bare-host
  value was the only URL in the repo that `HttpUrl` would normalize, so
  without this edit that typing change would have silently rewritten it
  on the next regeneration. With it, the whole typing pass contributes
  zero drift.
- **Golden file:** the maintainer applied the matching one-line edit to
  `city_of_austin_b60ab7ed-….yaml` directly (`url:` only). Confirmed
  afterwards: the file loads through the `Jurisdiction` model and
  re-dumps with zero drift on every URL field. This is the exception to
  the usual rule, not a precedent — it was an explicit maintainer edit
  of a single value, not an agent regeneration. Structural regeneration
  remains Phase 11 (#142) per plan §"Sample Output Change Control" §4.
