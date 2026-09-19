---
id: sample-output-inventory
type: rework-inventory
owner: rework
status: draft
last_updated: 2026-08-08
tags: [rework, phase-1, archaeology, sample-output, golden]
task: "Phase 1 — Task 1.5 (issue #132)"
scope: read-only inventory of `tests/sample_output/` on `131-gus-pipeline-rework` at commit b5c67c5
---

# Sample Output Inventory (Task 1.5)

Per root `AGENTS.md`, `tests/sample_output/` is immutable. This document
enumerates every fixture, states its purpose, and flags values that
should be verified during Phase 11 (Existing Sample Output Migration) —
it does **not** propose edits.

Directory shape verified with `find tests/sample_output -type f`:

```
tests/sample_output/
├── divisions/test/{ca,dc,tx,wa}/local/*.yaml       (6 files)
└── jurisdictions/test/{ca,dc,tx,wa}/local/*.yaml   (6 files)
```

Twelve YAML files total, evenly split between Divisions and their
matching Jurisdictions. There are no other YAML files or nested
directories under `tests/sample_output/`. Cache-only files at
`tests/sample_output/__pycache__/{test_divisions,test_jurisdictions}.cpython-312*.pyc`
are stale compiled bytecode; **no corresponding `test_divisions.py` or
`test_jurisdictions.py` source exists**. Grep on all git history for the
paths returned nothing — safe to treat as `.pyc` orphans (a `git clean`
would remove them; not in scope for Phase 1).

## 1. Purpose per file

The six fixtures collectively cover the *classes of behavior* Phase 3
needs a golden harness for:

| Class of behavior | Represented by |
| --- | --- |
| Ordinary place with geometry ref | Sausalito (`ca/local/sausalito_*.yaml`) |
| Council-district under a place | Austin CD 8, Seattle CD 1 |
| Advisory-district with no Census GEOID | ANC 1A District 1 |
| CDP that resolves to a special-purpose-district jurisdiction | Marin City |
| Non-district state city | Tacoma |

Each Division has a paired Jurisdiction with identical UUID for the
same-day-generated pair — except Marin City, whose Division points at a
special-district Jurisdiction with a different OCDID branch and
different UUID (documented behavior; see §3.4).

## 2. File-by-file inventory

Filenames use the pattern
`<slug>_<geoid>_<uuid>.yaml` for Divisions (with the geoid segment
omitted on Jurisdictions).

### 2.1 `divisions/test/ca/local/sausalito_5ebd7367-a3e7-54dd-8994-47e5f2cc5f8f.yaml`

- OCDID: `ocd-division/country:us/state:ca/place:sausalito`
- Purpose: Baseline "single Census place → single Division" case.
- Geometry: one entry pointing at
  `tigerweb.geo.census.gov/.../MapServer/4/query?where=GEOID='0670364'`.
- Sourcing: TIGER/Line + civicdata.tech.
- `metadata: null`.
- Matches fixture: `SAUSALITO_DIVISION` in `tests/fixtures/divisions_sample.py`.

### 2.2 `divisions/test/ca/local/marin_city_322f0412-0108-59a7-b29d-5f807672da64.yaml`

- OCDID: `ocd-division/country:us/state:ca/county:marin/cdp:marin_city`
- Purpose: CDP whose jurisdiction is a Community Services District, not a
  standard "government".
- `also_known_as`: `["Marin City Census Designated Place"]` — natural
  language, not an OCDID (flagged; see §3.1).
- `jurisdiction_id`:
  `ocd-jurisdiction/country:us/state:ca/county:marin/cdp:marin_city/special_district:marin_city_community_services_district/governing_board`
  — trailing `governing_board` segment is not a member of
  `ClassificationEnum`.
- `metadata.population.population: 2993` — nested-`population` shape
  reflects the model (`DivisionMetadata.population: Optional[Population]`,
  `Population.population: int`).
- Geometry entry hits TIGERweb MapServer layer 5.

### 2.3 `divisions/test/dc/local/anc_1a_district_1_35e1a717-03a8-5257-8123-3b6dd493c38d.yaml`

- OCDID: `ocd-division/country:us/district:dc/anc:1a/council_district:1`
- Purpose: DC ANC advisory district with **no Census GEOID**; uses the
  DC county FIPS `11001` as the umbrella GEOID.
- Geometry: DCGIS URL (not Census/TIGER).
- `government_identifiers.geoid: '11001'` — hardcoded in the fixture,
  **not** derived by
  `src/init_migration/geoid_exception.py:_resolve_umbrella_geoid` (that
  helper has no callers; see [`ocdid_inventory.md`](ocdid_inventory.md) §6.2).
- `government_identifiers.namelsad: 'ANC 1A'` — this is not a Census
  NAMELSAD (ANCs are not Census-defined).
- `metadata.source: 'DC Open Data ANC shapefile obtained via DCGIS.'`
  — `source` is an `extra="allow"` field on `DivisionMetadata`; the
  Marin City fixture uses `metadata.population` instead, so metadata
  shape varies across fixtures.
- `valid_asof: '2023-01-01T00:00:00Z'` — the only fixture with a
  non-null `valid_asof`.

### 2.4 `divisions/test/tx/local/austin_council_district_8_6ab0a55b-03b8-57e2-9565-1f558058519e.yaml`

- OCDID: `ocd-division/country:us/state:tx/place:austin/council_district:8`
- Purpose: Council-district under a Census place; jurisdiction inherits
  from parent city.
- `geometries: []` — no geometry ref, despite the sourcing block listing
  "City of Austin ArcGIS Hub". Flagged (see §3.3).
- `government_identifiers.geoid: '4845390165'` (10 digits) — not a
  standard Census 7-digit place GEOID. Looks like a composite of
  state FIPS `48` + place FIPS `45390` + district `165`? Investigate.
- `government_identifiers.sldust: ['25']` — single unpadded value.
  Compare Marin City's `['002']` and Sausalito's `['002']`. Flagged in §3.2.
- `government_identifiers.sldlst: ['047', 048]` — mixed quoting: `047`
  is a string, `048` renders as an unquoted YAML scalar (which
  `yaml.safe_load` will parse as the integer 48, not the string "048",
  breaking the field's declared `list[str]` type on round-trip).
  Flagged in §3.2.
- `government_identifiers.namelsad: 'Austin city: council district 8'`
  — colon-in-name; not a real Census NAMELSAD.

### 2.5 `divisions/test/wa/local/seattle_council_district_1_bb8a9dc8-ed3c-59bc-ba1d-408a3c765dde.yaml`

- OCDID: `ocd-division/country:us/state:wa/place:seattle/council_district:1`
- Purpose: Same class as Austin CD 8, but referencing TIGER/Line (not
  the city's own ArcGIS hub).
- `geometries: []` (same as Austin — geometry sourcing is present but no
  Geometry entries).
- `government_identifiers.geoid: '5363000'` — Seattle city GEOID, not
  a per-district GEOID. Consistent with "government_identifiers reflects
  the parent place" pattern.
- `sldust` and `sldlst` both list the six state legislative districts
  overlapping the *city* — again inherits from parent rather than
  reflecting the council district itself.

### 2.6 `divisions/test/wa/local/tacoma_a82e350d-72bb-5b02-8375-b66c9d2b6126.yaml`

- OCDID: `ocd-division/country:us/state:wa/place:tacoma`
- Purpose: Baseline non-district city.
- `sldust: ['027', 028, 029]` and `sldlst: ['027', 028, 029]` — same
  quoting inconsistency as Austin (see §3.2).
- `geometries: []`.

### 2.7 Jurisdiction fixtures (six files)

| File | OCDID | Notes |
| --- | --- | --- |
| `jurisdictions/test/ca/local/sausalito_city_government_38f5f5e0-64fa-5129-a944-bb9dcc385619.yaml` | `.../state:ca/place:sausalito/government` | Baseline. Term description, no term_limits. |
| `jurisdictions/test/ca/local/marin_city_community_services_district_governing_board_fc24cff2-3baa-5768-8652-b2840233c61b.yaml` | `.../state:ca/county:marin/cdp:marin_city/special_district:marin_city_community_services_district/governing_board` | Trailing `governing_board` is not in `ClassificationEnum` (see §3.4). Uses `classification: special_purpose_district`. |
| `jurisdictions/test/dc/local/anc_1a_government_ce723bd7-51c0-55b3-bc32-8d14a84c66ec.yaml` | `.../district:dc/anc:1a/government` | Metadata includes `official_website` and `mailing_address` extras. |
| `jurisdictions/test/tx/local/city_of_austin_b60ab7ed-add2-5de4-bd08-3da4aec2312b.yaml` | `.../state:tx/place:austin/government` | The only fixture with `term.term_limits: '2 consecutive terms'`. Note filename slug (`city_of_austin`) differs from the OCDID slug (`austin`) and from the `name` field ("City of Austin"). |
| `jurisdictions/test/wa/local/seattle_city_government_bd405187-c499-5b44-aee8-3800784ee617.yaml` | `.../state:wa/place:seattle/government` | `accurate_asof=2026-03-07`, differs from most fixtures' `2025-10-27`. UUID `bd405187-…` also differs from what today's model validator would derive from that date — see §3.6. |
| `jurisdictions/test/wa/local/tacoma_city_government_1c2a18a9-a8e3-586d-9968-502e8abb102e.yaml` | `.../state:wa/place:tacoma/government` | Same as Seattle: `accurate_asof=2026-03-07`. |

## 3. Suspicious or inconsistent values (flags for Phase 11)

None of these are fixed in Phase 1. Each will be classified during
Phase 11 as `STRUCTURAL`, `SOURCE_CORRECTION`, `BUG_FIX`,
`TEMPORAL_UPDATE`, `IDENTIFIER_MIGRATION`, `EXPECTED_NEW_FIELD`, or
`REGRESSION`.

### 3.1 `also_known_as` type drift

- **Marin City** `also_known_as: ["Marin City Census Designated Place"]`.
- Field docstring at
  [src/models/division.py:109-112](../../src/models/division.py#L109-L112) says
  "A list of alternate formatted OCDids".
- The value is a natural-language string, not an OCDID.
- Suggested classification: `STRUCTURAL` (or a `SOURCE_CORRECTION`
  if we accept text aliases and update the docstring).

### 3.2 Leading-zero / typing inconsistencies in `sldust`/`sldlst`

Fields declared as `list[str]`.

| Fixture | sldust | sldlst |
| --- | --- | --- |
| Sausalito (CA) | `['002']` | `['012']` |
| Marin City (CA) | `['002']` | `['012']` |
| Austin CD 8 (TX) | `['25']` — no padding | `['047', 048]` — mixed |
| Seattle CD 1 (WA) | `['032', '034', '036', '037', '043', '046']` | (same six) |
| Tacoma (WA) | `['027', 028, 029]` — mixed | `['027', 028, 029]` — mixed |
| ANC 1A (DC) | `[]` | `[]` |

Two problems:

1. **Missing leading zeros**: Austin's `'25'` in `sldust` looks like it
   lost a leading `0`. Compare Sausalito's `'002'` in the same field.
2. **Mixed quoting**: `048`, `028`, `029` are unquoted YAML scalars in
   the file, which `yaml.safe_load` parses as `int`. If any downstream
   consumer runs `Division.model_validate(yaml.safe_load(...))`,
   Pydantic will coerce (list[str] declaration) but round-tripping a
   modified record may drop the leading zero silently — a direct
   violation of rework §22 "preserve leading zeros".

Suggested classification: `BUG_FIX` for the mixed quoting, `SOURCE_CORRECTION`
for missing leading zeros — validate against Census SLDU/SLDL codes.

### 3.3 Council-district Divisions have empty `geometries`

- Austin CD 8 lists sourcing "City of Austin ArcGIS Hub" but no
  `geometries` entries.
- Seattle CD 1 lists sourcing "Census TIGER/Line" but no `geometries`
  entries.
- Compare Sausalito, Marin City, and ANC 1A which all have one
  `Geometry` entry with a real query URL.
- Root cause likely: council districts need a district-specific query URL
  (the city-level TIGER endpoint won't work), and the fixture author
  left them empty rather than fabricating one.
- Suggested classification: `EXPECTED_NEW_FIELD` or `STRUCTURAL` depending
  on whether Phase 6 (Resolver) fills them in.

### 3.4 Marin City Jurisdiction fails `validate_jurisdiction_id`

- OCDID ends in `/governing_board`.
- `classification="special_purpose_district"`.
- `Jurisdiction.validate_jurisdiction_id`
  ([src/models/jurisdiction.py:182-198](../../src/models/jurisdiction.py#L182-L198)) requires the
  trailing segment to equal `classification.value`.
- The fixture is constructed via `Jurisdiction(...)` in
  `tests/fixtures/jurisdictions_sample.py` — Pydantic validates on
  construction, so **the fixture module cannot import cleanly today**.
- Confirmed by inspection; not tested here (running the fixture is
  out-of-scope for the read-only Phase 1).
- Suggested classification: `BUG_FIX`. Fix could be either:
  - Add `governing_board` to `ClassificationEnum`, or
  - Loosen the validator to accept exception suffixes catalogued in the
    Phase 7 rule engine.

### 3.5 ANC 1A `government_identifiers.namelsad: "ANC 1A"`

- `NAMELSAD` is a Census-specific column. Advisory Neighborhood
  Commissions are not a Census concept.
- Consistent with the "DC ANC data comes from DCGIS, not Census"
  disclosure in `metadata.source`, but wedging a non-Census value into a
  Census-labelled field is misleading.
- Suggested classification: `STRUCTURAL` — during Phase 2.4 (external
  identifiers), the external-identifier collection should distinguish
  Census vs DCGIS provenance.

### 3.6 `accurate_asof` / `last_updated` and UUID coupling

Two calendars are visible in the fixture set:

| Records | Timestamp |
| --- | --- |
| Sausalito Div/Jur, Marin City Div/Jur, Austin Div/Jur, ANC 1A Div/Jur, Seattle Div, Tacoma Div | `2025-10-27T01:29:51Z` |
| Seattle Jur, Tacoma Jur | `2026-03-07T00:00:00Z` |

Under the current UUID formula (`uuid5(NS_URL,
f"{ocdid}|{last_updated.date().isoformat()}")`) the Jurisdiction UUIDs
depend on that date. Phase 2.1 UUID rework will require regenerating
every filename and `id:` value here.

The fact that Divisions and their same-OCDID Jurisdictions carry
different UUIDs is expected (the OCDIDs themselves differ:
`ocd-division/...` vs `ocd-jurisdiction/...`).

Suggested classification: `IDENTIFIER_MIGRATION` — everything here moves
to whatever Phase 2.1 chooses as the stable identity function.

### 3.7 `Division.metadata` shape drift

- Marin City: `metadata: {population: {population: 2993}}`.
- ANC 1A: `metadata: {population: null, source: "DC Open Data ANC ..."}`.
- Others (Seattle CD 1, Tacoma, Sausalito): `metadata: null` or
  `metadata: {population: null}`.

`DivisionMetadata` uses `extra="allow"`, so `source` is silently
accepted on ANC 1A. Rework §26 (Graph Semantics) wants provenance
first-class, not stuffed into freeform metadata.

Suggested classification: `STRUCTURAL`.

### 3.8 `SourceObj.source_url` dict keys

Every fixture uses key `"url"` except:

- Marin City Division mixed sourcing (three entries, all use `"url"`).
- Recursive-stub sourcing uses `"ocd_repo"` (not visible in these six
  fixtures — see `src/init_migration/generate_recursive.py:127-131`).
- `DivGenerator.generate_division` uses `"civicdata"` and `"ocd_repo"`
  keys ([src/init_migration/generate_division.py:141-149, 217-225](../../src/init_migration/generate_division.py#L141-L149)).

Suggested classification: `STRUCTURAL` — Phase 2.2 should normalise the
container to a plain URL + optional label.

### 3.9 Seattle CD 1 filename vs. Austin CD 8 filename

Both are council-district Divisions. Slug shape differs:

- `austin_council_district_8_6ab0a55b-…yaml` — slug includes "council_district_8"
- `seattle_council_district_1_bb8a9dc8-…yaml` — same pattern

Consistent, but note that the `display_name` is `"Austin Council District 8"`
and `"Seattle Council District 1"` respectively — the filename slug is
`display_name.lower().replace(" ", "_")` per
[src/init_migration/generate_division.py:40-41](../../src/init_migration/generate_division.py#L40-L41). Good.

### 3.10 City of Austin filename slug differs from OCDID slug

- Filename: `city_of_austin_b60ab7ed-…yaml`
- Slug source: `get_jurisdiction_filename` takes the second-to-last OCDID
  segment (`place:austin` → `austin`), so the expected filename is
  `austin_b60ab7ed-…yaml`.
- Actual filename in `tests/sample_output/` uses `city_of_austin`, which
  matches `Jurisdiction.name.lower().replace(" ", "_")`.
- This implies the fixture was generated by `Jurisdiction.dump_jurisdiction`
  (which uses `self.name`) not the runtime path via
  `JurGenerator.dump_jurisdiction` + `get_jurisdiction_filename`
  (which uses the OCDID segment).

**This is a real divergence** between the fixture author's dump path
and the runtime dump path. Phase 11 must decide which is canonical.

Suggested classification: `STRUCTURAL`.

### 3.11 `Population` type

The `2993` in Marin City's metadata is stored as
`Population(population=2993)`. `Population` has a single `int` field.
Wrapping in a class adds no schema value; likely a candidate for
flattening in Phase 2 or an `EXPECTED_NEW_FIELD` extension (e.g. adding
`year` and `source` to Population).

## 4. Coverage matrix

Rework §36 requires golden fixtures to cover:

| Requirement | Represented? | By |
| --- | --- | --- |
| Representative state | ✗ (no state-level fixture) | Only the four ancestor stubs would come from `ensure_ancestor_stubs`; not in `tests/sample_output/` today. |
| Counties | ✗ | No county-level Division fixture. |
| Municipalities (Census places) | ✓ | Sausalito, Tacoma |
| MCDs where relevant | ✗ | No `cousub:` fixture. |
| School districts | ✗ | No `school_district:` fixture. |
| OCD exceptions | Partial | Marin City special-district (jurisdiction exception); ANC 1A umbrella-GEOID exception. |
| Special districts | ✓ | Marin City CSD |
| Temporal geometry | ✗ | Every Geometry uses same-day `start`/`end`. |
| New-OCDID quarantine | ✗ | No quarantine golden — currently only in `tests/integration/test_generate_pipeline_integration.py`. |
| Unresolved geography | ✗ | Council-district fixtures have `geometries: []` but no explicit quarantine record. |

Every ✗ above is a Phase 3 gap the golden harness must fill.

## 5. What Phase 11 will need to do

Phase 11 (issue #142) is the phase where these fixtures **will** change,
under maintainer approval, to reflect the rework's model updates. Every
item below is a Phase 11 work-order:

- Regenerate every UUID and filename after Phase 2.1 lands.
- Reconcile the Marin City Jurisdiction validator conflict (§3.4)
  before the fixture can even import.
- Choose a canonical dump path (§3.10).
- Decide leading-zero and quoting policy for numeric-looking string
  fields (§3.2) and enforce with a Pydantic serializer or explicit
  `str.zfill()` step in whatever replaces `DivGenerator`.
- Add representative fixtures for the ✗ rows in the coverage matrix
  (§4).

The regenerated files become the **new** golden contract; from that
point on the Phase 12 CI (issue #143) enforces them exactly as it does
today's fixtures.

## 6. Change-control workflow

`tests/sample_output/` is a **golden contract**, not permanently frozen
data. It changes rarely, only with maintainer approval, and it drives
the tests that follow. The lifecycle:

1. **Phase 1 (this doc):** read-only. No edits. Observations only.
2. **Normal test runs (every phase):** still read-only. Golden tests
   compare against these fixtures and never mutate them (rework plan
   §3.3, §3.5; root `AGENTS.md` §"Testing Rules").
3. **Phase 2 model changes (#133):** land alongside a structural
   migration written into [`sample_output_migration.md`](sample_output_migration.md)
   (Task 2.7). The doc describes the intended change; the YAML files
   themselves stay untouched.
4. **Phase 3 harness lands (#134):** golden tests regenerate output
   from controlled fixtures and diff it against the checked-in files.
   After Phase 2 those diffs are expected to be non-empty — that is
   the signal that Phase 11 work is due, not a test failure to
   "fix" by patching the fixtures ad-hoc.
5. **Phase 11 regeneration (#142, Task 11.3):** a maintainer runs the
   explicit regeneration command (Task 3.5), reviews the diff,
   classifies every change (`STRUCTURAL`, `SOURCE_CORRECTION`,
   `BUG_FIX`, `TEMPORAL_UPDATE`, `IDENTIFIER_MIGRATION`,
   `EXPECTED_NEW_FIELD`, `REGRESSION` — rework plan §35), and approves
   the update. Agents do **not** run the regeneration command
   autonomously and do **not** hand-edit the YAML; the approval and
   commit are the maintainer's step.
6. **After regeneration:** the new fixture files are the golden
   contract. Every subsequent phase — the golden harness (#134),
   California pilot (#144), national run (#145), graph projection
   (#147) — compares against these until the next approved migration.
7. **Phase 12 CI (#143):** unexplained drift in `tests/sample_output/`
   fails PR CI. The only sanctioned way to produce a drift is steps
   5–6.

Two invariants agents observe throughout:

- **Never silently edit** anything under `tests/sample_output/`. If a
  test that reads a golden file starts failing, treat it as a signal
  to file a Phase 11 work-item and stop — do not "correct" the
  fixture to make the test pass (root `AGENTS.md` §"Testing Rules",
  rule "never fake-it").
- **Always safe to read.** Every observation in §§1–4 above was made
  by reading these files; nothing in this workflow limits that.

## 7. Phase 1 constraint (this pass)

No edits were made to any file under `tests/sample_output/` during
Phase 1. Every claim in this document was produced by reading the
files and cross-referencing them against `src/` and `tests/fixtures/`.
