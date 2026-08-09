---
id: model-inventory
type: rework-inventory
owner: rework
status: draft
last_updated: 2026-08-08
tags: [rework, phase-1, archaeology, models]
task: "Phase 1 — Task 1.4 (issue #132)"
scope: Pydantic contracts in `src/models/` on `131-gus-pipeline-rework` at commit b5c67c5
---

# Model Inventory (Task 1.4)

Field matrices and migration risks for every Pydantic contract in
`src/models/`. Consumed by Phase 2 (Domain Model Stabilization); root
`AGENTS.md` requires explicit maintainer approval for changes here.

Source files:

- [src/models/division.py](../../src/models/division.py) — 184 lines, 7 models
- [src/models/jurisdiction.py](../../src/models/jurisdiction.py) — 268 lines, 6 models + 2 enums
- [src/models/ocdid.py](../../src/models/ocdid.py) — 163 lines, 1 model + 1 Annotated type + 3 helpers
- [src/models/source.py](../../src/models/source.py) — 34 lines, 1 model + 1 enum

Docstring reference: `MODELS.md` (root).

## 1. Division ([src/models/division.py](../../src/models/division.py))

### 1.1 Field matrix — `Division`

| Field | Type | Optional? | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `UUID \| None` | yes | `None`, populated by validator | See §5 UUID logic |
| `ocdid` | `OCDIdStr` | required | — | Prefix-validated OCDID string |
| `country` | `str` | required | — | ISO-3166 alpha-2, lowercase in fixtures |
| `display_name` | `str` | required | — | Free-form; not slug-normalised |
| `geometries` | `Optional[List[Geometry]]` | yes | `[]` | Sample outputs use `[]` more often than actual `Geometry` entries |
| `also_known_as` | `List[str]` | yes | `[]` | Free-form; Marin fixture uses non-OCDID text |
| `valid_thru` | `Optional[datetime]` | yes | `None` | Retirement date |
| `valid_asof` | `Optional[datetime]` | yes | `None` | Effective date |
| `accurate_asof` | `Optional[datetime]` | yes | `None` | Researcher fact-check date |
| `last_updated` | `datetime` | required | `datetime.now(UTC)` factory | Drives UUID (see §5) |
| `sourcing` | `List[SourceObj]` | yes | `[]` | See §4 |
| `metadata` | `Optional[DivisionMetadata]` | yes | `None` | `extra="allow"` model |
| `government_identifiers` | `Optional[GovernmentIdentifiers]` | yes | `None` | See §1.3 |
| `jurisdiction_id` | `str` | required | — | Not typed as `OCDIdStr` (see risks) |

### 1.2 Support models

| Model | Fields | Purpose |
| --- | --- | --- |
| `Centroid` | `geo_type="Point"`, `coordinates: list[float]` | Boundary centroid |
| `Extent` | `extent: list[float]` (4 floats) | Bounding box |
| `Boundary` | `centroid: Optional[Centroid]`, `extent: Optional[Extent]` | Both optional; entirely null in current fixtures |
| `Population` | `population: int` | Wrapped in `DivisionMetadata.population` |
| `DivisionMetadata` | `population: Optional[Population]`, `extra="allow"` | Freeform extension (Marin fixture uses `source=`, ANC fixture uses `source=` — different key names) |

### 1.3 `GovernmentIdentifiers`

Census fields baked directly into the model:

| Field | Type | Optional? | Notes |
| --- | --- | --- | --- |
| `namelsad` | `str` | required | Full Census name incl. LSAD affix |
| `statefp` | `str` | required | Zero-padded FIPS |
| `sldust` | `list[str]` | required | State legislative upper districts |
| `sldlst` | `list[str]` | required | State legislative lower districts |
| `countyfp` | `list[str]` | required | Enclosing county FIPS |
| `county_names` | `list[str]` | required | Enclosing county names |
| `cousubfp` | `Optional[str]` | yes | County subdivision FIPS |
| `placefp` | `Optional[str]` | yes | Census place FIPS |
| `lsad` | `str` | required | Two-digit LSAD |
| `geoid` | `str` | required | Composite Census GEOID |
| `geoid_12` | `Optional[str]` | yes | 12-digit variant |
| `geoid_14` | `Optional[str]` | yes | 14-digit variant |
| `common_name` | `Optional[list[str]]` | yes | Alternate names for matching |

### 1.4 `Geometry`

| Field | Type | Notes |
| --- | --- | --- |
| `start` | `datetime` | Boundary effective date |
| `end` | `datetime` | Boundary retirement (nullable per docstring but not per type) |
| `boundary` | `Boundary` | Nested |
| `children` | `List[str]` | Child division IDs |
| `arcGIS_address` | `str` | **Required, provider-coupled** — must be an ArcGIS URL |

## 2. Jurisdiction ([src/models/jurisdiction.py](../../src/models/jurisdiction.py))

### 2.1 Field matrix — `Jurisdiction`

| Field | Type | Optional? | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `UUID \| None` | yes | `None`, populated by validator | See §5 |
| `ocdid` | `OCDIdStr` | required | — | Must start with `ocd-jurisdiction/` |
| `name` | `str` | required | — | Official governing-body name |
| `url` | `str` | required | — | **Not `HttpUrl`; also violates rework §23 nullable** |
| `classification` | `ClassificationEnum` | required | — | Nine allowed values |
| `legislative_sessions` | `Dict[str, SessionDetail]` | yes | `{}` | |
| `feature_flags` | `List[str]` | yes | `[]` | |
| `term` | `Optional[TermDetail]` | yes | `None` | |
| `accurate_asof` | `Optional[datetime]` | yes | `None` | |
| `last_updated` | `datetime` | required | `datetime.now(UTC)` factory | Drives UUID (see §5) |
| `sourcing` | `List[SourceObj]` | yes | `[]` | |
| `metadata` | `JurisdictionMetadata` | required | `default_factory=dict` | See §2.4 for silent-mismatch risk |

### 2.2 `ClassificationEnum`

`government`, `legislature`, `school_system`, `executive`,
`transit_authority`, `utility_commission` (non-OCD-compliant, ADDED),
`judicial` (ADDED), `prosecutorial` (ADDED), `advisory_board` (ADDED),
`special_purpose_district` (ADDED).

Five values are explicitly flagged as non-OCDid-compliant additions.

### 2.3 URL models

- `URLEnum` — `people`, `meetings` (open set with `str` type via
  `URLEnum | str` union).
- `URLObject` — `{url_type: URLEnum | str, url: str}`.
- `URLS` — `{urls: list[URLObject]}` (defined but not used by
  `Jurisdiction` — `JurisdictionMetadata.urls` is a `list[URLObject]`
  directly).

### 2.4 `JurisdictionMetadata`

```python
class JurisdictionMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")
    urls: list[URLObject] = Field(...)
```

Silent mismatches on the Jurisdiction side:

- `Jurisdiction.metadata: JurisdictionMetadata` uses
  `default_factory=dict` — a bare `dict`, not a `JurisdictionMetadata`
  instance. Pydantic coerces on validate, but the default breaks type
  invariants (line 178).
- `URLS` model is defined but unused (line 74).
- `metadata_urls` behavior varies: sample outputs sometimes list only
  `people` and `meetings`, and the DC ANC fixture adds
  `official_website` and `mailing_address` as `extra` fields — these
  survive because of `extra="allow"`.

### 2.5 `SessionDetail` & `TermDetail`

`SessionDetail`: `name`, `identifiers`, `classification`, `start_date`,
`end_date` — all required. `session_calendar_year(year)` and
`session_span(...)` factories exist but no runtime caller (grep-verified).

`TermDetail`: `duration` (int, years), `term_description` (str),
`number_of_positions` (int), `term_limits` (Optional[str]),
`source_url` (str, must be `.gov` per docstring but not enforced),
`last_known_term_end_date` (Optional[datetime]).

### 2.6 Validators

- `validate_jurisdiction_id` — enforces `ocd-jurisdiction/` prefix and
  that the trailing classification segment matches
  `Jurisdiction.classification.value`. Uses `OCDIdParsed.get_jurisdiction_classification`.
- `ensure_uuid5_id` — same UUID logic as `Division.ensure_uuid5_id`, see
  §5.

## 3. OCDID ([src/models/ocdid.py](../../src/models/ocdid.py))

### 3.1 `OCDIdStr` (Annotated type)

```python
OCDIdStr = Annotated[str, AfterValidator(validate_ocdid)]
```

`validate_ocdid` enforces:

- Prefix in `{ocd-division/, ocd-jurisdiction/}`.
- At least two `/`-segments, or a bare `country:xx` root.

### 3.2 `OCDIdParsed`

| Field | Type | Optional? | Notes |
| --- | --- | --- | --- |
| `type` | `Optional[OCDIdType]` | yes | Populated by validator from `raw_ocdid` prefix |
| `country` | `str` | required | Default `"us"` |
| `state` | `Optional[str]` | yes | |
| `county` | `Optional[str]` | yes | |
| `place` | `Optional[str]` | yes | |
| `subdivision` | `Optional[str]` | yes | |
| `base_ocdid` | `OCDIdStr` | required | Division-form OCDID (jurisdiction classification stripped) |
| `raw_ocdid` | `OCDIdStr` | required | Original input string |

`model_config = ConfigDict(extra="allow")` — every segment that isn't a
declared field lands in `.__pydantic_extra__` (e.g. `council_district`,
`anc`, `district`, `cd`, `sldl`, `sldu`, `cousub`, `cdp`,
`special_district`).

### 3.3 Helpers

Documented in [`ocdid_inventory.md`](ocdid_inventory.md) §1.2.

## 4. Source ([src/models/source.py](../../src/models/source.py))

### 4.1 `SourceType` enum

- `AI = "ai_generated"`
- `HUMAN = "human_researched"` (default)
- `SCRAPED = "programmatically_generated"`

### 4.2 `SourceObj`

| Field | Type | Optional? | Notes |
| --- | --- | --- | --- |
| `field` | `list[str]` | required | Which model fields this SourceObj covers |
| `source_name` | `str` | required | e.g. "civicdata.tech" |
| `source_type` | `SourceType` | yes | Default `HUMAN` |
| `source_url` | `dict[str, AnyHttpUrl \| FtpUrl \| FileUrl]` | required | Keyed URL map; sample outputs always use key `"url"` (or `"civicdata"`, `"ocd_repo"`, `"division"`) |
| `source_description` | `str \| None` | required | Nullable but required — must be supplied even if `None` |

## 5. UUID logic

Two independent UUID generators disagree today:

- **Model validators** — `Division.ensure_uuid5_id` and
  `Jurisdiction.ensure_uuid5_id` derive
  `uuid5(NAMESPACE_URL, f"{ocdid}|{last_updated_date.isoformat()}")`.
  Different `last_updated` day → different UUID.
- **Matcher** —
  [src/init_migration/ocdid_matcher.py:103](../../src/init_migration/ocdid_matcher.py#L103) computes
  `uuid5(NAMESPACE_URL, ocdid_str)` (no date). This is what
  `OCDidIngestResp.uuid` carries into the generators.
- **Helper module** — `src/utils/deterministic_id.py:generate_id`
  matches the model form (`ocdid|date`) but is not the runtime code path;
  only tests exercise it.

Consequences:

1. `OCDidIngestResp.uuid` and the eventual `Division.id` are different
   values for the same OCDID on the same day, because the model
   re-derives with a date suffix.
2. Re-running the same input on a different day changes every
   `Division.id`/`Jurisdiction.id`, violating rework §5 and Phase 2.1.
3. Filenames embed the model UUID, so day-of-generation drift propagates
   into on-disk file paths.

## 6. Migration risks (Phase 2 checklist)

Ordered by blast radius.

### 6.1 UUID scheme change (Phase 2.1)

- **Risk**: Every checked-in YAML has a UUID in its `id` field and in
  its filename derived from the current
  `uuid5(NAMESPACE_URL, "{ocdid}|{date}")` scheme.
- **Blast radius**: `tests/sample_output/**/*.yaml` filenames and `id:`
  values; the working-tree `divisions/**` and `jurisdictions/**` outputs.
- **Compatibility path**: any change must migrate the fixture UUIDs.
  Root `AGENTS.md` forbids agent-side edits to `tests/sample_output/` —
  Phase 2.1 must land alongside an explicit maintainer-approved
  regeneration in Phase 11.

### 6.2 `url` becoming nullable on `Jurisdiction` (Phase 2.6)

- **Risk**: `url: str` is currently required and all `SessionDetail`,
  `TermDetail.source_url`, `Jurisdiction.url` interact.
- **Blast radius**: `JurGenerator.generate_jurisdiction` fabricates a
  fallback `url = f"https://opencivicdata.org/division/{division.ocdid}"`
  when AI lookup is disabled — that fabricated URL bakes an OCDID into
  a non-URL, and getting rid of it may break existing quarantine paths.

### 6.3 `Geometry` provider decoupling (Phase 2.3)

- **Risk**: `Geometry.arcGIS_address: str` is required — every
  `Geometry` today assumes ArcGIS. Rework §18 requires a
  provider-neutral URL + external identifier + `valid_from`/`valid_to`
  triple.
- **Blast radius**: `Marin City`, `ANC 1A`, `Sausalito` sample outputs
  each carry one `Geometry` entry with an ArcGIS URL; four other
  fixtures use `geometries: []`.

### 6.4 `SourceObj` schema growth (Phase 2.2)

- **Risk**: Adding required `dataset`, `release`, `vintage`,
  `publication_date`, `retrieval_date` fields to `SourceObj` breaks
  every existing `sourcing: [...]` block in fixtures and generated YAML.
- **Mitigation**: Introduce as `Optional` in Phase 2.2, tighten in
  Phase 11 after fixture migration.
- **Also**: `source_url: dict[str, HttpUrl|FtpUrl|FileUrl]` is a weird
  container. Convert to `source_url: HttpUrl | FtpUrl | FileUrl` +
  optional label. Sample outputs all use the single key `"url"` with
  three exceptions in `SourceType`-flagged entries.

### 6.5 External identifiers (Phase 2.4)

- **Risk**: Census identifiers (`statefp`, `countyfp`, `placefp`,
  `cousubfp`, `sldust`, `sldlst`, `geoid`, `geoid_12`, `geoid_14`) are
  baked into `GovernmentIdentifiers`. Rework §22 wants them treated as
  a list of external identifiers preserving leading zeros.
- **Blast radius**: Every Division fixture; `GovernmentIdentifiers`
  is a required nested model on Division; `dump_division` post-processes
  four "optional" GI fields explicitly.
- **Leading-zero risk**: some fixtures use `sldust: ["25"]` (Austin CD
  8, no leading zero) alongside `sldust: ["002"]` (Sausalito) — the
  Austin value looks like it lost a leading `0`. See
  [`sample_output_inventory.md`](sample_output_inventory.md) for the
  full list of suspicious values.

### 6.6 Jurisdiction ↔ Division relationship (Phase 2.5)

- **Risk**: Division currently carries `jurisdiction_id: str` (untyped),
  Jurisdiction carries no back-reference. Rework §7 wants
  `GOVERNS`/`SERVES`/`OVERLAPS`/`CONTAINED_BY` explicit edges and no
  hard 1:1 assumption.
- **Blast radius**: Marin City fixture has
  `jurisdiction_id=ocd-jurisdiction/.../governing_board` — the single
  Marin City Division points at a special-district jurisdiction, which
  is already a 1:many-with-context case the current single-field
  representation cannot express cleanly.

### 6.7 `metadata` type mismatch on Jurisdiction

- **Risk**: `Jurisdiction.metadata: JurisdictionMetadata =
  default_factory=dict` — Pydantic coerces `dict` → model on validate,
  but the default is a bare `dict`. A downstream consumer expecting a
  `JurisdictionMetadata` instance can get `{}` if the model was
  constructed without validation (e.g. `.model_construct()`).

### 6.8 `Division.jurisdiction_id` typing

- **Risk**: `jurisdiction_id: str` bypasses `OCDIdStr` validation. This
  means an invalid jurisdiction OCDID can be stored without complaint.
  Fixtures verified to hold valid strings, but a Phase 9 model-construction
  step should tighten this to `OCDIdStr`.

### 6.9 `also_known_as` typing

- **Risk**: `also_known_as: List[str]` is unconstrained. The Marin City
  fixture uses `["Marin City Census Designated Place"]`, which is a
  natural-language string, not another OCDID. The field's docstring says
  "alternate formatted OCDids" — flag mismatch for Phase 2.

### 6.10 Non-OCDid-compliant `ClassificationEnum` values

- **Risk**: Five values in `ClassificationEnum` are explicitly flagged
  as `NON-OCDid COMPLIANT; ADDED`. This means the Jurisdiction OCDID's
  trailing segment is not part of any upstream registry — Phase 15
  (Special District Strategy) needs to decide whether these become
  formal upstream contributions (rework §15).

### 6.11 Legacy Marin City special-district validator bug

- **Risk**: `Jurisdiction.validate_jurisdiction_id` requires the
  trailing OCDID segment to equal `classification.value`. The Marin City
  fixture uses `classification=special_purpose_district` and
  OCDID ends in `/governing_board` — these don't match. Verify whether
  the fixture is loaded through `.model_validate()` anywhere; if so, it
  fails validation. See [`sample_output_inventory.md`](sample_output_inventory.md).

### 6.12 Unused / broken code

- `Division.load_division`, `Division.dump_division`,
  `Jurisdiction.load_jurisdiction`, `Jurisdiction.dump_jurisdiction`,
  `Jurisdiction.division_id_to_jurisdiction_id`,
  `Jurisdiction.jurisdiction_id_to_division_id`, `Jurisdiction.flatten`,
  `Jurisdiction.to_csv`, `Division.flatten`, `Division.to_csv` — all
  either stubs, `raise NotImplementedError`, or labelled `# Untested`.
- `session_calendar_year` / `session_span` factories — defined,
  imported nowhere.
- `Jurisdiction.__main__` block — broken: passes a `SessionDetail`
  where a `Dict[str, SessionDetail]` is required; also passes
  `feature_flags=[{...}]` (dicts) where `list[str]` is required. Do
  not use as a smoke test.

## 7. Model → fixture cross-references

The `tests/fixtures/*_sample.py` modules construct these models directly
and their `__main__` dumps regenerate `tests/sample_output/**/*.yaml`.
Because the fixtures are read-only per root `AGENTS.md`, any model
change must first pass the fixture through unchanged (semantic freeze)
or migrate the fixture explicitly with maintainer approval.

## 8. Recommended Phase-2 ordering

- **First**: 2.4 External identifiers (least entangled — new container,
  keep old fields temporarily), because it unlocks 2.3 (Geometry with
  external identifier).
- **Second**: 2.3 Geometry provider decoupling + `valid_from`/`valid_to`.
- **Third**: 2.6 Nullable website (small, isolated).
- **Fourth**: 2.2 Source/Sourcing schema growth.
- **Fifth**: 2.1 Stable UUID — largest blast radius; do last so the
  fixture regeneration in Phase 11 collapses all UUID changes into one
  reviewed migration.
- **Sixth**: 2.5 Jurisdiction↔Division relationship — depends on all of
  the above.
- **Not in Phase 2**: `metadata: JurisdictionMetadata=dict` and
  `governing_board` classification suffix — schedule as small
  correctness fixes (probably in Phase 7 alongside `ClassificationEnum`
  cleanup).
