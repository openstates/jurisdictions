Sample integration test data generated from CSVs in tests/sample_data per docs/integration_testing_data.md.

Contents
- divisions.json: serialized Division objects (6 records)
- jurisdictions.json: serialized Jurisdiction objects (6 records)
- divisions/test/<state>/local/*.yaml: one YAML per Division
- jurisdictions/test/<state>/local/*.yaml: one YAML per Jurisdiction

Covered OCD IDs
- ocd-division/country:us/state:ca/place:sausalito → ocd-jurisdiction/.../sausalito/government
- ocd-division/country:us/state:ca/county:marin/cdp:marin_city → ocd-jurisdiction/.../marin_city_community_services_district/governing_board
- ocd-division/country:us/district:dc/anc:1a/council_district:1 → ocd-jurisdiction/.../anc:1a/government
- ocd-division/country:us/state:wa/place:seattle/council_district:1 → ocd-jurisdiction/.../seattle/government
- ocd-division/country:us/state:wa/place:tacoma → ocd-jurisdiction/.../tacoma/government
- ocd-division/country:us/state:tx/place:austin/council_district:8 → ocd-jurisdiction/.../austin/government

Data sources
- tests/sample_data/testing_creyton_sample.csv
- tests/sample_data/testing_ocd_sample.csv
- tests/sample_data/WA_TX_OH_sample.csv

Notes
- All fields present in source files were included. Where a true value was not available in the sources (e.g., DC ANC 1A, Austin Council District 8), a placeholder prefixed with "missing-" is used (for example: missing-geoid, missing-url-<slug>, missing-statefp).
- IDs are deterministic UUIDv5 values derived from the OCD ID string; this keeps them stable across runs and decodable to the original OCD ID.
- Classification is derived from the jurisdiction OCD ID suffix (government → "government"; governing_board → "legislature").
- Geometries and sourcing are left empty for this sample set.
