---
id: ocdid-inventory
type: rework-inventory
owner: rework
status: draft
last_updated: 2026-08-08
tags: [rework, phase-1, archaeology, ocdid]
task: "Phase 1 — Task 1.3 (issue #132)"
scope: OCDID parsers, path builders, slug rules, matching, and exceptions on `131-gus-pipeline-rework` at commit b5c67c5
---

# OCDID Inventory (Task 1.3)

Everything the current repository does with OCD Division Identifiers is
catalogued here so Phase 7 (OCDID Rule Engine) can salvage the good parts
and replace the string-split parts.

Reminder from root `AGENTS.md` §"OCD ID Parsing Rules": all OCDID parsing
must go through `OCDIdParsed.parse_ocdid()`. Every call site that
side-steps that mandate is called out under [§4 Non-compliant parsing](#4-non-compliant-parsing).

## 1. The parser layer

### 1.1 `src/utils/ocdid.py:ocdid_parser` (line 21)

Legacy string-split helper. Splits the OCDID on `/`, then splits each
segment on `:`. Populates a dict `{base, country, state, county, place,
council_district, anc, district, ...}`. Assumes every non-base segment is
of the form `key:value`.

- **Behavior with `ocd-jurisdiction/.../government`** — the trailing
  `government` segment has no colon and raises `IndexError`, which the
  function catches and re-raises as `OCDIdParsingError`. Callers that need
  jurisdiction parsing must trim the classification segment first (see
  `OCDIdParsed.parse_ocdid`).
- Also raises on segments with values containing colons (e.g. a URL) —
  no such segments exist in canonical OCD IDs but the failure mode is
  worth documenting.
- Called directly from six sites (see §4).

### 1.2 `src/models/ocdid.py:OCDIdParsed` (line 35)

The blessed parser. Public API:

| Symbol | Notes |
| --- | --- |
| `validate_ocdid(value)` | Prefix + segment-count guard. Accepts `country:xx` root explicitly. |
| `OCDIdStr = Annotated[str, AfterValidator(validate_ocdid)]` | Used as the `ocdid` field type on `Division`, `Jurisdiction`, and `OCDIdParsed.base_ocdid`/`raw_ocdid`. |
| `OCDIdType = Literal["ocd-division", "ocd-jurisdiction"]` | |
| `get_ocdid_type(raw_ocdid)` | Splits `raw_ocdid` once on `/` — technically a string split, but it operates on already-validated `OCDIdStr` and only inspects the prefix. Acceptable per policy. |
| `OCDIdParsed.parse_ocdid(raw)` | The blessed entry point. Trims `/<classification>` from jurisdiction IDs, delegates to `ocdid_parser` for the base, wraps as a validated model. |
| `OCDIdParsed.get_ocdid_parts()` | Returns segment list, stripping the classification segment for jurisdiction IDs. |
| `OCDIdParsed.get_last_segment(ocdid)` | Convenience over `get_ocdid_parts()[-1]`. |
| `OCDIdParsed.get_jurisdiction_classification(ocdid)` | Extracts the trailing `government` / `legislature` / … for jurisdiction IDs. |
| `OCDIdParsed.build_ancestor_ocdids(parsed_ocdid)` | Returns each intermediate ancestor OCDID (excluding country root and the leaf) as new `OCDIdParsed` instances. Used by `generate_recursive.ensure_ancestor_stubs`. |

Weaknesses to note:

- `OCDIdParsed.type` uses `type` (a Python built-in shadow) as a field
  name. Minor cosmetic issue.
- `parse_ocdid` catches every `Exception` and re-raises as
  `OCDIdParsingError`, which loses the underlying `ValidationError`
  detail. Consider narrowing to `(ValueError, ValidationError,
  OCDIdParsingError)` in Phase 7.
- `get_jurisdiction_classification` returns the last segment from a raw
  `.split("/")` rather than from `get_ocdid_parts()` — inconsistent with
  the model's own abstraction, and the docstring implies you can call it
  on a division-type OCDID (it raises instead).
- `build_ancestor_ocdids` intentionally excludes the country root and the
  leaf. Callers assume this; document explicitly in Phase 7.

Tests: [tests/src/models/test_ocdid.py](../../tests/src/models/test_ocdid.py) covers `validate_ocdid`,
`get_ocdid_type`, `parse_ocdid` for both types, `get_last_segment` on
model and string inputs. `build_ancestor_ocdids` is exercised via
`generate_recursive` unit tests but has no direct unit test.

## 2. Slug and name rules

### 2.1 `src/utils/place_name.py`

- `namelsad_to_display_name(namelsad, lsad_code=None)` — LSAD-aware
  reverse of Census "NAMELSAD" to plain "display name". Falls back to
  hand-crafted regex `LSAD_RE` when the LSAD code is missing.
- `coerce_lsad_code(raw)` — normalises "None", "null", `['25','43']` list
  reprs into a bare LSAD code.
- `_strip_suffix` / `_strip_prefix` — regex helpers.
- `build_place_names_by_state(country_us_csv)` — walks the OCD master CSV,
  extracts `{state: {place_slug_lower, ...}}`. Not used by the pipeline
  but useful for Phase 7 rule authoring.

### 2.2 `src/init_migration/generate_division.py`

- `_council_district_display_name(parsed_ocdid)` (line 44) — turns
  `place/council_district:N` → `"{City} Council District {N}"` and
  `anc/council_district:N` → `"ANC {ANC_ID} District {N}"`. This is the
  only slug→display transform outside `namelsad_to_display_name`.
- `get_division_filename(display_name, geoid, uuid)` (line 29) — output
  filename slug: `display_name.lower().replace(" ", "_")` + `_geoid_uuid.yaml`.
  Slug generation is intentionally simple; no unicode normalisation.

### 2.3 `src/init_migration/generate_jurisdiction.py`

- `get_jurisdiction_filename(ocdid, uuid)` (line 32) — takes the
  second-to-last path segment, strips `<type>:` prefix, uses that as the
  slug (e.g. `ocd-jurisdiction/.../place:seattle/government` →
  `place_seattle_<uuid>.yaml`).

### 2.4 Fixture-side slugs (not runtime)

`tests/fixtures/divisions_sample.py` / `jurisdictions_sample.py` hand-code
`ocdid` strings with slug segments like `cdp:marin_city`,
`special_district:marin_city_community_services_district`, and
`governing_board`. These are ground-truth slug patterns for Phase 7 to
match.

## 3. Path builders (OCDID synthesis)

Every place that builds a jurisdiction OCDID from a division OCDID does
the same three-line dance: strip `ocd-division/`, drop
`/council_district:N` if present, append `/<classification>`. This is
duplicated in **three** files today.

| Location | Signature |
| --- | --- |
| [src/init_migration/generate_division.py:241-244](../../src/init_migration/generate_division.py#L241-L244) | `_derive_jurisdiction_id(division_ocdid) -> str` (always `/government`) |
| [src/init_migration/generate_jurisdiction.py:186-192](../../src/init_migration/generate_jurisdiction.py#L186-L192) | `_derive_jurisdiction_ocdid(division_ocdid, classification="government") -> str` |
| [src/init_migration/generate_pipeline.py:502-518](../../src/init_migration/generate_pipeline.py#L502-L518) | `_derive_jurisdiction_ocdid(division_ocdid, classification="government") -> str` (identical body) |
| [src/init_migration/generate_recursive.py:103-111, 162-163, 262-265](../../src/init_migration/generate_recursive.py) | Inline `f"ocd-jurisdiction/{ancestor_ocdid.replace('ocd-division/', '')}/government"` twice, plus one variant that also derives `jur_part` |

**Phase 7 action**: collapse into a single rule-based function on
`OCDIdParsed` (e.g. `OCDIdParsed.to_jurisdiction_ocdid(classification,
strip_segments=("council_district",))`).

Other path-building call sites:

- `OCDIdParsed.build_ancestor_ocdids` — the correct approach; builds each
  intermediate OCDID string from parts.
- `generate_recursive._write_stub_division/_write_stub_jurisdiction` —
  build `jur_ocdid` by string replace as above.

## 4. Non-compliant parsing

Per root `AGENTS.md`, every OCDID must be parsed via
`OCDIdParsed.parse_ocdid()`. The following call sites currently parse OCD
IDs some other way. Each one is a candidate for Phase 7 salvage or rewrite.

### 4.1 Direct `ocdid_parser(str) -> dict` callers

| File | Line | Purpose | Recommended fix |
| --- | --- | --- | --- |
| [src/init_migration/generate_pipeline.py](../../src/init_migration/generate_pipeline.py) | 28, 226 | `find_matches` splits OCDID to get state/place/council_district/anc | Use `OCDIdParsed.parse_ocdid` + `.state` / `.place` accessors |
| [src/init_migration/generate_division.py](../../src/init_migration/generate_division.py) | 13, 73, 169, 248, 290 | Multiple call sites: constructor, stub generator, existence check, dump | Same |
| [src/init_migration/generate_jurisdiction.py](../../src/init_migration/generate_jurisdiction.py) | 20, 196, 230 | Existence check, dump | Same. `dump_jurisdiction` reverts to *division* OCDID because `ocdid_parser` can't handle `/government` — `OCDIdParsed.parse_ocdid` handles both, so the workaround goes away. |
| [src/init_migration/ocdid_matcher.py](../../src/init_migration/ocdid_matcher.py) | 22, 92 | Builds `OCDIdParsed` from `parsed_dict` manually — wraps `ocdid_parser` in `OCDIdParsed` fields but doesn't call `parse_ocdid` | Replace with `OCDIdParsed.parse_ocdid(ocdid_str)` |
| [src/init_migration/jurisdiction_seed.py](../../src/init_migration/jurisdiction_seed.py) | 72, 288 | Decision tree needs `parsed` dict for `_extract_primary_division_type` | Use `.model_dump(exclude_none=True)` on `OCDIdParsed` or add a helper |
| [src/init_migration/geoid_exception.py](../../src/init_migration/geoid_exception.py) | (docstring) | Expects an `ocdid_parser()` dict — no runtime caller today | If wired in, take `OCDIdParsed` directly |

### 4.2 Raw `.split(":")` / `.split("/")` on OCDID strings

| File | Line | Purpose |
| --- | --- | --- |
| [src/models/ocdid.py](../../src/models/ocdid.py) | 32 | `get_ocdid_type` splits on the first `/`. Acceptable — operates on validated `OCDIdStr` and only touches the prefix. |
| [src/models/ocdid.py](../../src/models/ocdid.py) | 87, 89, 142 | Internal to `OCDIdParsed`. Acceptable — the model itself is the authorised parser. |
| [src/utils/ocdid.py](../../src/utils/ocdid.py) | 34-37 | Inside `ocdid_parser` — the low-level split. Acceptable as an implementation detail; do not call from outside `OCDIdParsed`. |
| [src/utils/place_name.py](../../src/utils/place_name.py) | 140-147 | `build_place_names_by_state` walks the OCD master CSV; uses `id.split("/")` and `p.split(":")[-1]` to pick out `state:` and `place:` segments. Phase 4 replacement should use `OCDIdParsed` to iterate segments. |
| [src/init_migration/generate_jurisdiction.py](../../src/init_migration/generate_jurisdiction.py) | 45-47 | `get_jurisdiction_filename` picks the second-to-last segment and strips `":"` — should use `OCDIdParsed.get_ocdid_parts()`. |

### 4.3 String replacement of `ocd-division/`

Listed in [§3 Path builders](#3-path-builders-ocdid-synthesis). Six sites,
all convertible to a single rule-based method on `OCDIdParsed`.

### 4.4 Regex on OCDID segments

- [src/init_migration/generate_division.py:243](../../src/init_migration/generate_division.py#L243) — `re.sub(r"/council_district:[^/]+", "", division_part)` (drop council_district segment before appending classification).
- [src/init_migration/generate_jurisdiction.py:191](../../src/init_migration/generate_jurisdiction.py#L191) — same regex, duplicated.
- [src/init_migration/generate_pipeline.py:517](../../src/init_migration/generate_pipeline.py#L517) — same regex, duplicated.

Encode as an explicit "strip council_district" rule in the Phase 7 rule
engine.

## 5. Matching utilities

### 5.1 Exact join (Phase 2 matcher)

`OCDidMatcher.run_matching()`
([src/init_migration/ocdid_matcher.py:77-83](../../src/init_migration/ocdid_matcher.py#L77-L83)) performs the only
canonical-OCDID membership check today, via SQL `INNER JOIN … ON l.id =
m.id`. Anti-joins yield `local_orphans` and `master_orphans`. This is
the closest thing the current code has to "OCD validation" (Phase 8).

Salvage: the classification into matched / local-orphan /
master-orphan is exactly the input Phase 8 quarantine wants; keep the
concept, move the storage from mutable DuckDB tables to per-run
snapshots.

### 5.2 Fuzzy match (Phase 3 generator)

`GeneratePipeline.find_matches()`
([src/init_migration/generate_pipeline.py:215-327](../../src/init_migration/generate_pipeline.py#L215-L327)):

- Filter by state FIPS.
- Filter to Census `place` layer (`PLACEFP` populated) — comment at
  329-341 explains why LSAD code alone is not sufficient.
- Exact match on `normalized_place_name` first.
- Fallback: `rapidfuzz.fuzz.token_sort_ratio` (or `difflib` shim) with
  threshold `0.85`.
- Multiple matches ⇒ quarantine, not silent selection.

This is exactly the "fuzzy matching may assist review only" pattern the
rework §12 requires. Move under Phase 6 (Resolver) once the source of
truth flips to GUS.

### 5.3 Similarity helper

`_similarity(a, b)`
([src/init_migration/generate_pipeline.py:48-60](../../src/init_migration/generate_pipeline.py#L48-L60)) picks
`token_sort_ratio` (not `token_set_ratio`) with a documented rationale
(preserves multi-word names like "spokane valley" against "spokane").
Keep as-is; move into a `text_similarity` utility.

## 6. Exception logic

### 6.1 Statistical / decision-tree tables

`src/init_migration/jurisdiction_seed.py` holds the current "exception"
knowledge as five sets and one map:

| Symbol | Content | Meaning |
| --- | --- | --- |
| `STATISTICAL_LSADS` | 20 two-digit codes | LSADs that are statistical only (no governing body) |
| `LEGISLATIVE_TYPES` | `{cd, sldu, sldl}` | Division segment types that create legislative-body jurisdictions |
| `NON_JURISDICTION_DIVISION_TYPES` | `{vtd, zcta, tract, blockgroup, block, ua, msa, csa, division, region}` | Division segment types with no governing body |
| `SCHOOL_CLASSES` | 5 segment names | Division types that create `school_system` jurisdictions |
| `GOVERNMENT_TYPES` | `{country, state, county, place, cousub, submcd, aiannh, aits, anc}` | Division segment types that create a `government` jurisdiction |
| `NON_PARENT_ENTITY_TYPES` | `{council_district}` | Segment types whose jurisdiction belongs to the parent |
| `STATISTICAL_LSAD_ENTITIES` | 19 entity descriptions | Statistical-geography names in the LSAD table |
| `STATISTICAL_LSAD_DESCRIPTIONS` | 4 explicit "(suffix)" descriptions | Statistical-geography descriptions |

Special cases in `infer_jurisdiction_seed`:

- `exact_override` (dict) always wins — proto exception mechanism, but
  no override registry exists yet.
- LSAD code `"27"` (sub-county district) is routed through
  `disambiguate_subcounty_district`, which is a **stub** that returns the
  fallback classification unchanged (no AI lookup yet).
- Unknown division types return `has_jurisdiction=False` with reason
  `"unknown division type '{division_type}'; manual review required"` —
  today this is a log-only quarantine signal; Phase 8 must promote it.

### 6.2 DC ANC umbrella GEOID

`src/init_migration/geoid_exception.py`
`UMBRELLA_GEOID_MAP = {("dc", "anc"): "11001"}`
+ `_resolve_umbrella_geoid(parsed_ocdid)`.

**Confirmed dead code**: `grep -rn "_resolve_umbrella_geoid\|UMBRELLA_GEOID_MAP" src/ tests/` returns only the definition file. The ANC 1A sample fixture at
[tests/fixtures/divisions_sample.py:184-195](../../tests/fixtures/divisions_sample.py#L184-L195) hardcodes
`geoid=11001` instead of routing through this helper.

Phase 7 either wires it into the Resolver or removes it.

### 6.3 Council-district stripping

Three duplicated regex sites strip `/council_district:N` before
appending `/government` to a jurisdiction OCDID. This is an implicit
"council districts do not have their own jurisdiction — inherit their
parent's" rule that belongs in Phase 7.

### 6.4 Reference data not yet wired to exceptions

- [src/data/ocdid_segment_names_by_cnt.csv](../../src/data/ocdid_segment_names_by_cnt.csv) — Frequency dump of segment
  names found in OCDIDs (issue #105). No runtime consumer; grep-confirmed.
- [src/init_migration/mappers.py:ocdid_master_mapper](../../src/init_migration/mappers.py#L12-L26) — Column-name mapping
  table for the (unused) OCD master ingest that predates the current
  matcher. Refers to `sameAs`, `sameAsNote`, `validThrough`, `placeholder_id`
  — real OCD master columns worth referencing when Phase 4 defines the
  OCD-master adapter.

## 7. Legacy IDs and identifier bridges

- `Division.also_known_as: List[str]` — alternate OCDID strings for the
  same division (used by the Marin City fixture:
  `"Marin City Census Designated Place"`; note that value is not an
  OCDID at all — flag for Phase 2.4 to constrain the type).
- `Division.jurisdiction_id: str` — free-form OCDID string linking to a
  Jurisdiction. Not typed as `OCDIdStr`. Should become `OCDIdStr` in
  Phase 2.5.
- `Jurisdiction.ocdid: OCDIdStr` + `validate_jurisdiction_id` — enforces
  `ocd-jurisdiction/` prefix and that the trailing classification segment
  matches `Jurisdiction.classification`.
- `OCDIdParsed.base_ocdid` — for jurisdiction OCDIDs, the division OCDID
  minus the classification segment. Effectively the internal "bridge"
  between the two namespaces today.

## 8. Slug rules in fixtures (ground-truth)

For Phase 7 rule authoring, the checked-in fixtures give concrete
examples of the slug patterns the rework must reproduce:

| OCDID | Sourced from |
| --- | --- |
| `ocd-division/country:us/state:wa/place:seattle/council_district:1` | civicdata.tech + city ArcGIS |
| `ocd-division/country:us/state:tx/place:austin/council_district:8` | civicdata.tech + Austin ArcGIS Hub |
| `ocd-division/country:us/district:dc/anc:1a/council_district:1` | DCGIS (not Census) |
| `ocd-division/country:us/state:ca/place:sausalito` | civicdata.tech |
| `ocd-division/country:us/state:ca/county:marin/cdp:marin_city` | civicdata.tech + Census 2020 |
| `ocd-jurisdiction/country:us/state:ca/county:marin/cdp:marin_city/special_district:marin_city_community_services_district/governing_board` | Marin LAFCO |

`cdp:` and `special_district:` are Census concepts; `anc:` and
`council_district:` are locality-specific. `governing_board` is a
non-`ClassificationEnum` jurisdiction suffix — but `ClassificationEnum`
enumerates the full set of allowed values and rejects `governing_board`.
This means the Marin City special-district fixture uses
`classification=special_purpose_district` (allowed enum) while the
OCDID's trailing segment is `governing_board`. The
`Jurisdiction.validate_jurisdiction_id` validator requires the last
segment to equal `classification.value` — so this fixture **would fail
model validation** today. Verified by inspection; needs Phase 2
follow-up.

## 9. Recommended Phase-7 salvage list

Ordered by priority for Phase 7 (OCDID Rule Engine):

1. Adopt `OCDIdParsed.parse_ocdid()` at every call site in [§4.1](#41-direct-ocdid_parserstr---dict-callers).
2. Add a single `OCDIdParsed.to_jurisdiction_ocdid(classification,
   strip_segments=("council_district",))` method; remove the three
   `_derive_jurisdiction_(id|ocdid)` clones.
3. Move `jurisdiction_seed.STATISTICAL_LSADS`,
   `LEGISLATIVE_TYPES`, `NON_JURISDICTION_DIVISION_TYPES`,
   `SCHOOL_CLASSES`, `GOVERNMENT_TYPES`, `NON_PARENT_ENTITY_TYPES` and
   `_extract_primary_division_type` into a rule-engine module; encode
   each set as a named rule with a version.
4. Encode `UMBRELLA_GEOID_MAP` as an "identifier override" exception
   (rework §11), then wire it into the Resolver.
5. Encode the "council_district inherits parent" behavior as a named
   "hierarchy override" rule.
6. Reconcile `Jurisdiction.validate_jurisdiction_id` with the
   `governing_board` suffix in the Marin City fixture (expand
   `ClassificationEnum`, or extend the validator to accept exception
   suffixes).
7. Replace `LSAD 27 (sub-county district)` AI-lookup stub with either
   an explicit exception table entry or an enrichment call.
