You are helping to build an ETL pipeline that will load data about local cities into a GitHub repository. The data will be stored in YAML files. The structure of the data is defined by Pydantic v2 models.

## Scope

- Goal: Generate initial Division and Jurisdiction YAML files from the “Validation Research” CSV (exported from the linked Google Sheet).
- Out of scope: Crawling/scraping for missing fields (handled in a later AI pass), FastAPI CRUDL API (to be added later).

## Inputs and outputs

- Input:
  - Validation Research CSV (export/download of the Google Sheet).
    https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/edit?usp=drive_web&ouid=105992325138979778362
  - Official Division OCD IDs CSV:
    https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/refs/heads/master/identifiers/country-us.csv
- Output:
  - Division YAML: stored under `divisions/<state>/local/`
  - Jurisdiction YAML: stored under `jurisdictions/<state>/local/`
  - One Division and one associated Jurisdiction per CSV record (multiple Divisions may map to the same Jurisdiction).

## Data models (do not modify)

- Division model: `src/models/division.py`
- Jurisdiction model: `src/models/jurisdiction.py`
- Notes:
  - All required fields must be present.
  - Use Pydantic v2 syntax across models.
  - See tests in `tests/` for expected shapes.

## Open Civic Data identifiers (OCD IDs)

- Schema references:
  - Divisions: https://open-civic-data.readthedocs.io/en/latest/data/division.html
  - Jurisdictions: https://open-civic-data.readthedocs.io/en/latest/data/jurisdiction.html

- Matching existing Division OCD IDs (required):
  - Match each record to an existing official Division OCD ID (“Official Division OCD ID”) from the country-us.csv.
  - Utilities:
    - `src/utils/place_name.py`: derive human-readable names from Census NAMELSAD.
    - `src/utils/ocdid.py`: parse/build OCD IDs, generate state-level IDs if needed.

- Generating Jurisdiction OCD IDs:
  - Jurisdiction IDs take the form:
    `ocd-jurisdiction/<division_id_without_prefix>/<jurisdiction_type>`
    Example: Division `ocd-division/country:us/state:wa/place:seattle` → Jurisdiction `ocd-jurisdiction/country:us/state:wa/place:seattle/legislature`
  - Jurisdiction type depends on the entity (e.g., `legislature` for city councils, `government` for general government).
  - Heuristics should aim for consistent, documented mappings; multiple Divisions may map to the same Jurisdiction.


## Storage layout and naming

- Divisions: `divisions/<state>/local/`
- Jurisdictions: `jurisdictions/<state>/local/`
- Recommended filename convention:
  - Division: `<display_name>_<geoid>_<custom_uuid>.yaml`
  - Jurisdiction: `<name>_<uuid>.yaml`
- Avoid spaces in filenames; use hyphens or underscores.
- A custom, unique, deterministic uuid-like identifier will be generated for each id
  based on the ocdid and a random element.
    - This deterministic uuid-like identifier should enable others to decode the id
      to the full ocdid and random element.
    - Implemented in `src/utils/deterministic_id.py` with `generate_id(ocdid, random_element=None)`
      and `decode_id(id)`; see `docs/deterministic_ids.md` for format details.

## Pipeline flow (initial ingestion)

### Pipeline 1: 
Given each state:  
1. Read the Official Division OCD ID (`country-us.csv`) for each state
2. Return only local OCDids. 
3  For each division ocdid, return a request object to run  Pipeline 2. 

### Pipeline 2: 
Given a request object with an official division ocdid: 
3. Normalize place names for matching.

4. Match each record to anValidation Research CSV (via Polars).
5. Build Division objects:
   - Fill required fields; set `geometries` as an empty list if unknown.
   - Include `government_identifiers` (e.g., `namelsad`, `statefp`, `lsad`, `geoid`).
   - Link to associated `jurisdiction_id` (string).
6. Derive Jurisdiction objects:
   - Use division→jurisdiction construction rules noted above.
   - Choose `classification` (e.g., `legislature`/`government`) using heuristic rules.
   - Fill required fields: `name`, `url`, `classification`, `legislative_sessions` (possibly empty dict), `feature_flags` (possibly empty list).
7. Serialize each object to YAML and write to the correct directory.
8. Log decisions and any unmatched/ambiguous records for review.

## Minimal YAML examples

Division (required fields only; add others when known):

```yaml
id: "d9f7a4dc-0a83-4f95-9b8a-92d930b2a2a7"
ocdid: "ocd-division/country:us/state:wa/place:seattle"
country: "us"
display_name: "Seattle"
geometries: []
also_known_as: []
last_updated: "2025-01-01T00:00:00Z"
sourcing: []
government_identifiers:
  namelsad: "Seattle city"
  statefp: "53"
  sldust: []
  sldlst: []
  countyfp: ["033"]
  county_names: ["King"]
  lsad: "25"
  geoid: "5363000"
jurisdiction_id: "ocd-jurisdiction/country:us/state:wa/place:seattle/legislature"
```

Jurisdiction:

```yaml
id: "cbd0b3b0-9a7a-4b6a-84e9-3b1a2c3f4d5e"
ocdid: "ocd-jurisdiction/country:us/state:wa/place:seattle/legislature"
name: "Seattle City Council"
url: "https://www.seattle.gov/council"
classification: "legislature"
legislative_sessions: {}
feature_flags: []
accurate_asof: null
last_updated: "2025-01-01T00:00:00Z"
sourcing: []
metadata: {}
```

## How to run (local)

- Environment setup (uv):
  - See `docs/setup_uv.md` for detailed steps.
- Entry point:
  - Run the ingestion script at `src/init_migration/main.py` (e.g., `uv run python src/init_migration/main.py`).
- Tests:
  - `uv run pytest`
- Linting:
  - `uv run ruff .`

## Unit tests 
All tests should be stored in tests/ and the file path should mirror the
filepath where the code is stored. 

## Acceptance criteria

- For a sample input CSV, the pipeline:
  - Writes valid YAML files to the correct directories by state.
  - Each Division has a valid Official Division OCD ID.
  - Each Jurisdiction OCD ID follows the correct schema and is derivable from the Division.
  - Tests in `tests/` pass and Ruff reports no errors.
  - Integration tests in `integration/` pass and report no errors. 

## Future phases
- AI scrapers to fill missing fields (ArcGIS layer URLs, official websites, etc.).
- FastAPI CRUDL service for ongoing updates.
- Enhanced validation (e.g., existence checks against OCD sources).

## References

- OCD divisions: https://open-civic-data.readthedocs.io/en/latest/data/division.html
- OCD jurisdictions: https://open-civic-data.readthedocs.io/en/latest/data/jurisdiction.html
- Official Division OCD IDs (CSV): https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/refs/heads/master/identifiers/country-us.csv




