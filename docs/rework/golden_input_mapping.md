---
id: golden-input-mapping
type: rework-inventory
owner: rework
status: active
last_updated: 2026-09-15
tags: [rework, phase-3, golden, fixtures, harness]
task: "Phase 3 — Tasks 3.1 and 3.2 (issue #134)"
scope: "Which controlled inputs produce each file under tests/sample_output/, and which fields today's generate stage can and cannot derive from them."
---

# Golden Input Mapping (Tasks 3.1, 3.2)

Task 3.2 asks that every golden record have a controlled input "where
feasible". This document is the honest answer to how feasible that is at
the end of Phase 2: **none of the 12 golden files can be regenerated from
pipeline inputs today.** They were dumped from hand-authored Pydantic
objects in `tests/fixtures/divisions_sample.py` and
`tests/fixtures/jurisdictions_sample.py`, and most of what they contain
(terms, curated URLs, population, geometry references, curated sourcing)
has no input the current generate stage reads. That is a finding, not a
gap to close by inventing inputs.

Everything below was measured by running `GeneratePipeline` over the six
golden Division OCDids with the fixture CSVs from §1 into a temporary
directory and diffing each output against its checked-in counterpart,
field by field. Nothing under `tests/sample_output/` was touched.

## 1. Fixture layout (Task 3.1)

```
tests/fixtures/
├── ocd_master/
│   └── country-us.csv                6 golden Division OCDids, upstream column layout
├── sources/
│   ├── civicdata_divisions.csv       7 rows (4 golden matches + 3 decoys)
│   ├── civicdata_states.csv          1 row (Washington)
│   └── civicdata_counties.csv        1 row (King County)
├── divisions_sample.py               hand-authored golden Division objects (pre-existing)
└── jurisdictions_sample.py           hand-authored golden Jurisdiction objects (pre-existing)
```

**`sources/`** holds the three tabs of the civicdata.tech validation
spreadsheet that `GeneratePipeline` concatenates into one frame:

| File | Spreadsheet tab | `GeneratorReq` field |
| --- | --- | --- |
| `civicdata_divisions.csv` | Divisions (Census place and county-subdivision rows) | `validation_data_division_filepath` |
| `civicdata_states.csv` | States | `validation_data_states_filepath` |
| `civicdata_counties.csv` | Counties | `validation_data_counties_filepath` |

They are the row sets `tests/integration/test_generate_pipeline_integration.py`
has built inline since it was written, moved verbatim (same
`csv.DictWriter` call, same column order). `civicdata_divisions.csv`
deliberately contains three decoy rows the matcher must reject (a county
subdivision sharing Seattle's name, a place containing Tacoma's name as a
token, a multi-word place) and deliberately omits Marin City CDP and any
District of Columbia row so those two OCDids quarantine. The inline
constants are retired from that test when the harness lands, which is a
`tests/integration/` change and therefore separately approved.

**`ocd_master/country-us.csv`** is the roster, in the column layout of the
upstream `ocd-division-ids/identifiers/country-us.csv`. Only `id` and
`name` are populated: `id` is the only column any stage reads (the Stage 1
matcher joins on it), and the other columns are left blank rather than
filled with values not taken from an upstream snapshot. `name` values are
the upstream repository's names as recorded when the golden set was
assembled, including the malformed Austin entry.

`census_governments/` and `tiger/` are created by Phase 4 when their
adapters exist and there is data to put in them.

### `tests/sample_data/` — not moved

Nothing under `tests/` imports or opens any of these five files (verified
with a repository-wide grep). They stay where they are and are listed here
for Phase 18 cleanup:

| File | What it is | Why it stays |
| --- | --- | --- |
| `WA_TX_OH_sample.csv` | 142-row stratified sample of the civicdata.tech sheet (WA/TX/OH), wider column set than the pipeline reads | No reader. Historical research input. |
| `random_sample_by_LSAD_STATEFP.csv` | 150-row stratified sample across all states | No reader. |
| `random_sample_validation_records.py` | The one-off script that produced the two CSVs above; live-fetches the Google Sheet | No reader; network at import path. |
| `testing_ocd_sample.csv` | 6-row research roster pairing each golden Division OCDid with its Jurisdiction OCDid and notes | No reader. Its `division_ocdid`/`name` columns were the basis for `ocd_master/country-us.csv`; the jurisdiction pairing and notes are already in this document. |
| `ohio_jurisdictions_licking_county.py` | Hand-authored Licking County objects | Does not import (constructs `SourceObj` with a signature that has never existed). Already flagged in the migration log. |

`docs/integration_testing_data.md` references two files that do not
exist (`test_sample.csv`, `testing_creyton_sample.csv`); that document
describes the prompt that produced the golden set and is also Phase 18
material.

## 2. How the pipeline behaves on the roster

`GeneratePipeline` per OCDid, with `asof_datetime` fixed to
`2025-10-27T01:29:51Z` (the golden `accurate_asof`):

| OCDid | Match | Status | Division written | Jurisdiction written |
| --- | --- | --- | --- | --- |
| `…/state:ca/place:sausalito` | Sausalito city | `success` | `divisions/ca/local/sausalito_0670364_<id>.yaml` | `jurisdictions/ca/local/sausalito_<id>.yaml` |
| `…/state:ca/county:marin/cdp:marin_city` | none (`cdp:` is not `place:`; no row) | `partial`, quarantined `no_validation_match` | stub `divisions/ca/local/unknown__<id>.yaml` | none |
| `…/district:dc/anc:1a/council_district:1` | none (no DC rows) | `partial`, quarantined `no_validation_match` | stub `divisions/local/anc_1a_district_1__<id>.yaml` | none |
| `…/state:tx/place:austin/council_district:8` | Austin city | `success` | `divisions/tx/local/austin_council_district_8_4845390165_<id>.yaml` | `jurisdictions/tx/local/austin_<id>.yaml` |
| `…/state:wa/place:seattle/council_district:1` | Seattle city | `success` | `divisions/wa/local/seattle_council_district_1_5363000_<id>.yaml` | `jurisdictions/wa/local/seattle_<id>.yaml` |
| `…/state:wa/place:tacoma` | Tacoma city | `success` | `divisions/wa/local/tacoma_5370000_<id>.yaml` | `jurisdictions/wa/local/tacoma_<id>.yaml` |

Marin City and ANC 1A are quarantine cases in the current pipeline, as
they are in the existing integration test. The quarantine record for each
is `{"ocdid": …, "reason": "no_validation_match", "matched_records": []}`
and the response status is `partial` with error `No validation match
found`.

Every `<id>` above already equals `uuid5(NAMESPACE_URL, ocdid)`, so the
pipeline's ids agree with the "after regen" column of the Task 2.1 table
in `sample_output_migration.md`. The filenames do not agree with the
golden layout: the pipeline writes `<state>/local/`, not
`test/<state>/local/`; Division filenames embed the GEOID; Jurisdiction
filenames use the OCDid segment (`austin`), not the record name
(`city_of_austin`). Path policy is Phase 10/11.

## 3. Per-file mapping

Legend for "derivable today": ✓ the pipeline produces the golden value
from the controlled inputs; ≈ the pipeline produces a value for the field
but not the golden one; ✗ no input exists for the field. "Structural"
differences the migration log already predicts (id, `sourcing[]` key
shape, `government_identifiers` list shape, geometry keys, `children`)
are not repeated per row; see `sample_output_migration.md`.

### 3.1 Divisions

| # | Golden file | Inputs | Derivable today | Not derivable, and why |
| --- | --- | --- | --- | --- |
| 1 | `divisions/test/ca/local/sausalito_5ebd7367-….yaml` | `ocd_master` row; `civicdata_divisions.csv` row `Sausalito city` (GEOID 0670364) | ✓ `ocdid`, `country`, `display_name`, `jurisdiction_id`, `accurate_asof` (from `asof_datetime`); ✓ identifiers `namelsad`, `statefp`, `lsad`, `geoid`, `countyfp`, `county_names`; ≈ `sldust`/`sldlst` (input row has them blank; the golden has `['002']`/`['012']`, and the live sheet does carry them, so this is a fixture-content gap, not a pipeline gap) | ✗ `geometries[0]` — the pipeline never builds a `Geometry`; the TIGERweb URL, geoid identifier and TIGER `source` come from the fixture object. ✗ `sourcing[0]` (Census TIGER/Line) — pipeline emits only the civicdata block, with a different `source_url` (`…/d/139NE…/` vs the golden `…/edit?usp=…`) and a non-null `source_description`. ✗ `metadata: null` — pipeline dumper drops the key entirely. ✗ `last_updated` — pipeline uses `datetime.now()`. |
| 2 | `divisions/test/ca/local/marin_city_322f0412-….yaml` | `ocd_master` row only; no validation row (quarantine) | ✓ `ocdid`, `country`, `accurate_asof` | Everything else. `display_name` becomes `Unknown` (the stub reads `place:` and this OCDid uses `cdp:`); `jurisdiction_id` becomes `…/cdp:marin_city/government` (the golden points at the community services district's `governing_board`); identifiers collapse to one `namelsad: Unknown`; `also_known_as`, `metadata.population`, the TIGER geometry and the three curated sourcing blocks have no input. The stub filename is `unknown__<id>.yaml` (empty GEOID). |
| 3 | `divisions/test/dc/local/anc_1a_district_1_35e1a717-….yaml` | `ocd_master` row only; no validation row (quarantine) | ✓ `ocdid`, `country`, `display_name` (`ANC 1A District 1` via the council-district naming rule), `jurisdiction_id`, `accurate_asof` | ✗ `valid_asof: 2023-01-01`; ✗ `metadata.source` text; ✗ DCGIS geometry and both DCGIS sourcing blocks; ✗ identifiers `statefp: 11`, `countyfp: 001`, `geoid: 11001` (the umbrella-GEOID helper in `geoid_exception.py` has no caller). The stub lands in `divisions/local/` with an empty state segment because the dumper reads `state` and this OCDid uses `district`. |
| 4 | `divisions/test/tx/local/austin_council_district_8_6ab0a55b-….yaml` | `ocd_master` row; `civicdata_divisions.csv` row `Austin city` (GEOID 4845390165) | ✓ `ocdid`, `country`, `display_name`, `jurisdiction_id`, `accurate_asof`, `geometries: []`; ✓ identifiers `statefp`, `geoid`; ≈ `namelsad` (`Austin city` vs golden `Austin city: council district 8`), ≈ `lsad` (`25` vs golden `22`), ≈ `countyfp`/`county_names` (input row has Travis only; golden has Hays, Travis, Williamson), ≈ `sldust`/`sldlst` (blank in input) | ✗ `sourcing[0]` (City of Austin ArcGIS Hub); ✗ `metadata: {population: null}` (dumper drops it); ✗ `last_updated`. The `namelsad`/`lsad` values in the golden describe the council district, which is not a Census row at all. |
| 5 | `divisions/test/wa/local/seattle_council_district_1_bb8a9dc8-….yaml` | `ocd_master` row; `civicdata_divisions.csv` row `Seattle city` (GEOID 5363000) | ✓ `ocdid`, `country`, `display_name`, `jurisdiction_id`, `accurate_asof`, `geometries: []`; ✓ identifiers `namelsad`, `statefp`, `lsad`, `geoid`, `countyfp`, `county_names`; ≈ `sldust`/`sldlst` (blank in input; golden lists six districts) | ✗ `sourcing[0]` (Census TIGER/Line); ✗ `metadata: null` key; ✗ `last_updated`. |
| 6 | `divisions/test/wa/local/tacoma_a82e350d-….yaml` | `ocd_master` row; `civicdata_divisions.csv` row `Tacoma city` (GEOID 5370000) | as Seattle | as Seattle |

### 3.2 Jurisdictions

The generate stage derives a Jurisdiction from the Division it just built.
Its only inputs are the Division's `ocdid` and `display_name`; there is no
input for websites, terms, or curated URLs, and AI lookup is disabled.

| # | Golden file | Inputs | Derivable today | Not derivable, and why |
| --- | --- | --- | --- | --- |
| 7 | `jurisdictions/test/ca/local/sausalito_city_government_38f5f5e0-….yaml` | Division 1 | ✓ `ocdid`, `classification: government`, `legislative_sessions: {}`, `feature_flags: []`, `accurate_asof`; ≈ `name` (`Sausalito Government` vs golden `Sausalito City Government`); ≈ `metadata` (`{urls: []}` vs two curated URLs) | ✗ `url` (pipeline emits `null`); ✗ `term` (all six fields); ✗ the three curated sourcing blocks — pipeline emits one `derived_from_division` block whose `source_url` is `https://opencivicdata.org/division/<ocdid>`; ✗ `last_updated`. |
| 8 | `jurisdictions/test/ca/local/marin_city_community_services_district_governing_board_fc24cff2-….yaml` | none — Division 2 quarantines, so no Jurisdiction is generated | nothing | Everything. Independently of the pipeline, the fixture object for this file does not construct: its OCDid ends in `/governing_board`, which is not a `ClassificationEnum` value, so `validate_jurisdiction_id` rejects it (Phase 7). The harness compares this file textually against the checked-in bytes only. |
| 9 | `jurisdictions/test/dc/local/anc_1a_government_ce723bd7-….yaml` | none — Division 3 quarantines | nothing | Everything: `url`, `term`, `metadata.urls`, `metadata.official_website`, `metadata.mailing_address`, four sourcing blocks. |
| 10 | `jurisdictions/test/tx/local/city_of_austin_b60ab7ed-….yaml` | Division 4 | as Sausalito; ≈ `name` (`Austin Council District 8 Government` — the pipeline names the Jurisdiction after the council-district Division, the golden says `City of Austin`) | as Sausalito, plus ✗ `term.term_limits: 2 consecutive terms`. |
| 11 | `jurisdictions/test/wa/local/seattle_city_government_bd405187-….yaml` | Division 5 | as Sausalito; ≈ `name` (`Seattle Council District 1 Government`); ≈ `accurate_asof` (`asof_datetime` is one value per run; the golden Seattle and Tacoma Jurisdictions carry `2026-03-07`, their Divisions `2025-10-27`) | as Sausalito. |
| 12 | `jurisdictions/test/wa/local/tacoma_city_government_1c2a18a9-….yaml` | Division 6 | as Sausalito; ≈ `name` (`Tacoma Government`); ≈ `accurate_asof` (as Seattle) | as Sausalito. |

## 4. Findings

Observed while measuring; none is fixed here. Each names the phase that
owns it.

1. **No golden file is pipeline-reproducible.** Regeneration of
   `tests/sample_output/` is only possible from the fixture objects, which
   is what the golden harness and the regeneration command do. The
   pipeline path is exercised separately (quarantine, identity), and the
   gap tabulated above is the distance Phases 4–10 have to close before
   Task 10.4 ("complete golden end-to-end path") can pass.
2. **Ancestor stubs are mislabeled.** `ensure_ancestor_stubs` picks the
   ancestor's level as the first key of `_LEVEL_KEYS` present in the
   parsed OCDid; every ancestor has a `state` key, so a `place:austin`
   ancestor is treated as a state and written as `Texas` /
   `Texas Government` into `divisions/tx/` and `jurisdictions/tx/`. The
   run above produced two `texas_*.yaml` and two `washington_*.yaml`
   Divisions per state, plus a `jurisdictions/tx/texas_<austin id>.yaml`
   whose `ocdid` is Austin's. Because the stub-existence check looks in
   the level directory (`tx/`) and the generated Jurisdiction is in
   `tx/local/`, the same Jurisdiction OCDid is written twice. Phase 9
   replaces ancestor materialisation.
3. **Stub filenames degrade when the OCDid is not a `place:`.** Marin
   City (`cdp:`) becomes `unknown__<id>.yaml`; ANC 1A (`district:dc`)
   is written to `divisions/local/` with no state segment and an empty
   GEOID. Phase 7 (OCDid handling) and Phase 10 (path policy).
4. **`accurate_asof` cannot differ between a Division and its
   Jurisdiction in one run.** Both read `GeneratorReq.asof_datetime`. The
   golden Seattle and Tacoma pairs carry different values. Whether the
   golden values are right is a Phase 11 `TEMPORAL_UPDATE` question.
5. **Fixture CSV rows are thinner than the live sheet.** `SLDUST_list`
   and `SLDLST_list` are blank for every place row, and the Austin row
   lists one county where the golden record lists three. These were inherited
   from the integration test verbatim. Filling them from the live sheet
   would move four Division files closer to the golden values without any
   code change; it is a fixture-content decision for Phase 11, recorded
   here so it is not mistaken for pipeline drift.
6. **The civicdata `source_url` differs between fixture and pipeline.**
   The fixture objects cite `…/edit?usp=drive_web&ouid=…`; the generator
   cites `…/d/139NE…/`. Same spreadsheet, different URL string. Phase 11
   picks one.
