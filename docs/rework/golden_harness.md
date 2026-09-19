---
id: golden-harness
type: rework-guide
owner: rework
status: active
last_updated: 2026-09-18
tags: [rework, phase-3, golden, harness, testing]
task: "Phase 3 — Tasks 3.3, 3.4, 3.5 (issue #134)"
scope: "How the golden harness under tests/integration/golden/ works, how to read a failure, and how tests/sample_output/ is regenerated."
---

# Golden Harness (Tasks 3.3–3.5)

`tests/sample_output/` is the golden contract (root `AGENTS.md`
§"Testing Rules"). The harness compares freshly produced output against it
and never writes into it. Regeneration is a separate maintainer command.

## 1. Layout

| Path | Role |
| --- | --- |
| `tests/integration/golden/harness.py` | Structural YAML diff, golden-layout dumper, fixture regeneration, runner for the real `GeneratePipeline`. |
| `tests/integration/golden/test_golden_sample_output.py` | One comparison per checked-in golden file, marked `integration` and `golden`. |
| `tests/integration/golden/test_golden_harness.py` | Tests for the helpers. Pure diff tests run with the unit suite; pipeline-running tests are `integration`. |
| `tests/integration/golden/test_golden_quarantine.py` | ANC 1A District 1 (no validation row) quarantines identically on two runs, and the record equals `tests/sample_output/quarantine/test/dc/local/anc_1a_district_1.yaml`. |
| `tests/integration/golden/test_golden_identity.py` | Id and filename stay fixed when inputs change: two pipeline runs with a different as-of date and altered validation row; fixture dumps with changed `last_updated`, website, source release/retrieval date, geometry. |
| `scripts/regenerate_sample_output.py` | Maintainer regeneration command. Never invoked by a test. |
| `tests/fixtures/ocd_master/country-us.csv` | OCDid roster the runner feeds through the pipeline. |
| `tests/fixtures/sources/civicdata_*.csv` | The three validation CSVs the pipeline reads. |
| `tests/fixtures/divisions_sample.py`, `jurisdictions_sample.py` | Fixture objects the golden files are regenerated from. |

The `golden` marker is registered in `pyproject.toml`.

## 2. Producers and comparison

The golden files were dumped from the fixture objects, not produced by the
pipeline, and `golden_input_mapping.md` shows today's pipeline cannot
reproduce any of them. So there are two producers:

- **`regenerate_from_fixtures(root)`** dumps every constructible fixture
  object with the serializer the golden files were written with
  (`model_dump(mode="json", exclude_none=False)` → `yaml.safe_dump`,
  sorted keys) at the checked-in layout
  `<kind>/test/<state>/local/<slug>_<id>.yaml`. `slug` is the Division
  `display_name` or Jurisdiction `name`, lowercased, spaces to
  underscores. Used by the 12 golden tests and the regeneration command.
- **`run_pipeline(ocdids, root, asof)`** runs `GeneratePipeline` once per
  OCDid against the fixture CSVs. Used by the quarantine and identity
  tests; later phases swap stages into it.

Both refuse a `root` inside `tests/sample_output/`.

**`compare_trees(expected_root, actual_root)`** pairs files by
`(kind, ocdid)`, not filename, because an id change renames the file.
Every difference is `(file, field path, expected, actual)`; the relative
path is field `<path>`. Dicts diff key by key, lists index by index. A key
holding `null` and an absent key differ; `48` and `'048'` differ.

**Timestamps.** Fixture objects carry fixed `last_updated`, so the fixture
path needs no clock. The pipeline path calls `datetime.now()` for
`last_updated`; `accurate_asof` comes from `asof_datetime`, which the
runner takes as an argument. Tests comparing two pipeline runs pass
`ignore_fields=("last_updated",)`. That is the only excluded field, named
at the call site, top-level only. Injecting a clock into the generators
would remove it and is a `src/init_migration/` change for a later phase.

## 3. Running

```
uv run pytest tests/integration/golden
uv run pytest -m golden -rxX
uv run pytest -m "not integration and not slow"
```

All offline. Geometry `url` values are strings, never fetched.

## 4. What a failure looks like

```
--- divisions/test/wa/local/tacoma_a82e350d-72bb-5b02-8375-b66c9d2b6126.yaml
    <path>: expected 'divisions/test/wa/local/tacoma_a82e350d-….yaml', got 'divisions/test/wa/local/tacoma_c104c614-….yaml'
    children: expected <absent>, got []
    government_identifiers: expected {'common_name': None, 'county_names': ['Pierce'], …}, got [{'authority': 'census', …}]
    id: expected 'a82e350d-72bb-5b02-8375-b66c9d2b6126', got 'c104c614-3662-5202-ac00-c348b7c31e4f'
    sourcing[0].dataset: expected <absent>, got None
    sourcing[0].source_url: expected {'url': 'https://tigerweb.geo.census.gov/…'}, got 'https://tigerweb.geo.census.gov/…'
```

A failing golden test is never fixed by editing the YAML or loosening the
comparison. Classify the change (`STRUCTURAL`, `SOURCE_CORRECTION`,
`BUG_FIX`, `TEMPORAL_UPDATE`, `IDENTIFIER_MIGRATION`, `EXPECTED_NEW_FIELD`,
`REGRESSION`) and, if expected, regenerate per §6.

## 5. The xfail mechanism

Every checked-in file predates the Phase 2 model changes, so every golden
comparison fails today by design. Each is `xfail(strict=True)`:

- eleven files: *checked-in file predates the current models; awaiting
  approved regeneration*
- `jurisdictions/…/marin_city_community_services_district_governing_board_….yaml`:
  *fixture object does not construct: its OCDid ends in a segment that is
  not a classification value, so there is no regenerated counterpart; the
  checked-in file also predates the current models*

`strict=True` keeps the suite green now and fails the run with
`XPASS(strict)` the moment a file matches. That flip is the signal to
remove the marker for that file. Expected: Phase 11 regenerates, eleven
flip, eleven markers come off. Marin City stays xfailed until Phase 7
makes its fixture object construct.

`skip` was rejected because it never reports when the condition changes.

## 6. Regeneration command (Task 3.5)

```
uv run python scripts/regenerate_sample_output.py                        # dry run
uv run python scripts/regenerate_sample_output.py --write                # rewrite tests/sample_output/
uv run python scripts/regenerate_sample_output.py --write --output-dir D
```

- **Dry run (default):** regenerates into a temp directory, prints the
  full diff against `tests/sample_output/divisions` and `jurisdictions`,
  writes nothing, exits 1 on differences so it doubles as a drift check.
  `quarantine/` records are pipeline output, not fixture dumps, so the
  command leaves them alone; their test compares them directly.
- **`--write`:** writes into the target and removes any file there that
  describes the same `(kind, ocdid)` under a different filename (the old
  id). Refuses to run under pytest.
- **Who runs it:** a maintainer at Phase 11 Task 11.3, after reviewing the
  dry-run diff. Agents do not run it against `tests/sample_output/`; in
  development it is exercised only with `--output-dir` at a scratch path.

It cannot produce the Marin City Jurisdiction, so that file is handled by
hand at Phase 11 or after Phase 7.

## 7. First run against the checked-in files

Dry run after `55524c2`: **207 differences in 12 files**, all predicted by
`sample_output_migration.md`.

| Golden file | Differences |
| --- | --- |
| `divisions/…/marin_city_322f0412-….yaml` | 28 |
| `divisions/…/sausalito_5ebd7367-….yaml` | 23 |
| `divisions/…/anc_1a_district_1_35e1a717-….yaml` | 23 |
| `divisions/…/austin_council_district_8_6ab0a55b-….yaml` | 14 |
| `divisions/…/seattle_council_district_1_bb8a9dc8-….yaml` | 14 |
| `divisions/…/tacoma_a82e350d-….yaml` | 14 |
| `jurisdictions/…/marin_city_community_services_district_governing_board_fc24cff2-….yaml` | 1 (no counterpart) |
| `jurisdictions/…/sausalito_city_government_38f5f5e0-….yaml` | 17 |
| `jurisdictions/…/anc_1a_government_ce723bd7-….yaml` | 22 |
| `jurisdictions/…/city_of_austin_b60ab7ed-….yaml` | 17 |
| `jurisdictions/…/seattle_city_government_bd405187-….yaml` | 17 |
| `jurisdictions/…/tacoma_city_government_1c2a18a9-….yaml` | 17 |

| Difference | Count | Predicted by |
| --- | --- | --- |
| `<path>` rename; `id` change | 12; 11 | Task 2.1 table — every new id and filename matches its "after regen" column. The twelfth has no id line because it has no counterpart. |
| `sourcing[n]` gains `dataset`, `release`, `publication_date`, `retrieval_date` as `null`; `source_url` map → scalar | 29 blocks × 5 | Task 2.2. The log counts 30 blocks; the 30th is Marin City's, no counterpart. |
| `government_identifiers` dict → list of `{authority, id_type, value, source}` | 6 | Task 2.4 |
| top-level `children: []` | 6 | Task 2.3 |
| `geometries[0]`: `arcGIS_address`, `children`, `start`, `end` out; `url`, `identifiers`, `source`, `valid_from`, `valid_to` in | 3 × 9 | Task 2.3 |
| TIGERweb `url` apostrophes become `%27`; DCGIS `url` unchanged | 2; 1 | Task 2.3, percent-encoding note |
| Geometry windows: Sausalito and Marin City `valid_from: 2025-01-01`, ANC 1A `valid_from: 2023-01-01`, all `valid_to: null`; source `release` (`2025`/`2023`) and, for ANC 1A, `dataset`, `publication_date`, `retrieval_date` | 3 | Migration log, "TIGER 2025 geometry validity window and release" (`BUG_FIX` + `EXPECTED_NEW_FIELD`) |

**Unpredicted differences: none.**

### Findings recorded, not resolved

- **The model dumpers do not produce the checked-in layout.**
  `Division.dump_division` and `Jurisdiction.dump_jurisdiction` write
  `<name>_<geoid>_<id>.yaml` flat with original casing; the checked-in
  files are lowercase slugs without GEOID under `test/<state>/local/`,
  renamed by hand when first committed. The harness reproduces the
  checked-in layout itself. Canonical layout is Phase 10/11
  (`sample_output_inventory.md` §3.9–§3.10).
- **The Marin City Jurisdiction cannot be regenerated by any path.**
  Phase 7.
- **`--write` removes only filenames it superseded.** A golden file whose
  fixture object is deleted would linger and show up in the next dry run
  as an unexpected file for Phase 11 review.
