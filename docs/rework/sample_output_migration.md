---
id: sample-output-migration
type: rework-migration-log
owner: rework
status: active
last_updated: 2026-09-05
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

## Fixture value normalizations (not tied to a model task)

Value-level fixture edits that create golden drift without any model
contract change. Logged here because Phase 11 (#142) has to reconcile
them alongside the structural migrations above.

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
