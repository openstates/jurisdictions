---
id: current-pipeline-inventory
type: rework-inventory
owner: rework
status: draft
last_updated: 2026-08-08
tags: [rework, phase-1, archaeology, pipeline]
task: "Phase 1 — Task 1.1 (issue #132)"
scope: read-only inventory of `main`/`131-gus-pipeline-rework` as of commit b5c67c5
---

# Current Pipeline Inventory (Task 1.1)

This document maps the existing OCD-first ingestion pipeline end-to-end, so
subsequent phases know what exists, what runs, what state it keeps, and where
network access is required. It is a **read-only** description of the code on
the `131-gus-pipeline-rework` branch as of commit `b5c67c5`; no code is
modified in this phase.

The current pipeline is the **inverse** of the target design: it treats the
Open Civic Data (OCD) division-id corpus as the "source of truth" universe
and looks up Census / civicdata.tech records to enrich each OCDID. The Census
GUS-first pipeline described in [docs/rework/openstates-jurisdictions-data-pipeline.md](openstates-jurisdictions-data-pipeline.md)
does not yet exist. All references below to "Stage 1", "Phase 1/2/3/4",
"pipeline" describe the *existing* implementation, not the phased rework plan.

## 1. Top-level entry points

| Entry | Path | Purpose |
| --- | --- | --- |
| Stage-1 CLI | [src/init_migration/main.py](../../src/init_migration/main.py) | Argparse CLI (`--state`, `--force`, `--log-dir`); `python src/init_migration/main.py` |
| Programmatic | `main.main() → asyncio.run(run_pipeline(args))` | Same code path as CLI, returns `MatchResults` |
| LSAD table generator | [src/data/lsad_mapper.py](../../src/data/lsad_mapper.py) `__main__` | One-off scraper for `src/data/lsad_map.json`; **live HTTP GET** of a Census HTML page |
| Fixture dump | `tests/fixtures/divisions_sample.py`, `tests/fixtures/jurisdictions_sample.py` `__main__` | Rebuilds `tests/sample_output/**/*.yaml` from hand-authored Pydantic fixtures |

There is no separate "resolve", "validate", "quarantine", or "render" CLI —
everything is invoked from `main.main()`.

## 2. Stage layout

`run_pipeline()` in [src/init_migration/main.py:218-315](../../src/init_migration/main.py#L218-L315)
sequences four phases, all synchronous in-process except async downloads:

```
Phase 1 (download)  →  Phase 2 (match)  →  Phase 3 (generate)  →  Phase 4 (tracking)
DownloadManager        OCDidMatcher         GeneratePipeline        store_generation_tracking
async httpx            DuckDB SQL           polars + fuzzy match    DuckDB per-day table
```

### Phase 1 — Download and load ([src/init_migration/download_manager.py](../../src/init_migration/download_manager.py))

Inputs (constants at [src/init_migration/download_manager.py:28-32](../../src/init_migration/download_manager.py#L28-L32)):

- `RAW_BASE = https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers`
- `MASTER_PATH = country-us.csv` (national OCD division-id master)
- `LOCAL_TEMPLATE = country-us/state-{state}-local_gov.csv` (per-state local government list)

Network activity:

- One `GET` for the master CSV, one per state for the local CSV, all through
  [AsyncDownloader](../../src/init_migration/downloader.py) (`httpx.AsyncClient`, HTTP/2 opportunistic).
- Conditional revalidation via ETag / Last-Modified. Cache persisted to
  `.etag_cache.json` at repo root ([src/init_migration/downloader.py:56-70](../../src/init_migration/downloader.py#L56-L70)).
- Retries on 429, 5xx, GitHub 403 rate-limit, and transient network errors,
  with jittered exponential backoff up to `max_backoff` (default 8 s).
- HTML-body guard against GitHub 404 fallthrough
  ([src/init_migration/downloader.py:374-409](../../src/init_migration/downloader.py#L374-L409)).
- Optional GitHub token via `GITHUB_TOKEN` env for `use_github_auth=True`.

Persistence:

- Each downloaded CSV is written to a `tempfile.NamedTemporaryFile` and then
  ingested by DuckDB's `read_csv_auto` into `master_ocdids` (`CREATE OR
  REPLACE`) or `local_ocdids` (append, tagged with `state` column) at
  [src/init_migration/download_manager.py:77-141](../../src/init_migration/download_manager.py#L77-L141).
- DuckDB file path defaults to `data/ocdid_pipeline.duckdb`
  ([src/init_migration/download_manager.py:32](../../src/init_migration/download_manager.py#L32)).

Outputs: `download_stats` dict `{files_downloaded, files_cached,
files_failed, master_rows, local_rows}`.

### Phase 2 — Match ([src/init_migration/ocdid_matcher.py](../../src/init_migration/ocdid_matcher.py))

Inputs: `master_ocdids`, `local_ocdids` (DuckDB), optional state filter.

Behavior:

- Inner-join `local ↔ master` on the literal `id` column
  ([src/init_migration/ocdid_matcher.py:77-83](../../src/init_migration/ocdid_matcher.py#L77-L83)); master row wins as "canonical".
- For each matched row, `ocdid_parser()` splits the OCDID string on `/` and
  builds an `OCDIdParsed`, then a UUID5 is generated with
  `uuid5(NAMESPACE_URL, ocdid_str)` — **no date input** here, unlike the
  model's own `ensure_uuid5_id` validator (see below).
- Left-anti-join produces `local_orphans` (in the state file but not in
  master); right-anti-join gated to the requested states produces
  `master_orphans`.
- Persists `ocdid_uuid_lookup`, `local_orphans`, `master_orphans` tables in
  the same DuckDB file, plus a CSV backup at `data/ocdid_uuid_lookup.csv`.
- Lookup insert uses `WHERE NOT EXISTS` for idempotency
  ([src/init_migration/ocdid_matcher.py:180-197](../../src/init_migration/ocdid_matcher.py#L180-L197));
  orphan tables are `CREATE TABLE IF NOT EXISTS` + naked `INSERT` per row,
  so re-runs append duplicates (`tests/conftest.py` `clean_duckdb` fixture
  drops the tables around integration tests to compensate).

Outputs: `MatchResults(matched: list[OCDidIngestResp], local_orphans, master_orphans)`.

### Phase 3 — Generate ([src/init_migration/generate_pipeline.py](../../src/init_migration/generate_pipeline.py))

Setup (`main._cache_validation_csv`,
[src/init_migration/main.py:145-157](../../src/init_migration/main.py#L145-L157)):

- Downloads the "civicdata.tech" validation Google Sheet
  (`DIVISIONS_SHEET_CSV_URL` at
  [src/init_migration/pipeline_models.py:9](../../src/init_migration/pipeline_models.py#L9))
  once, writes it to `${TMPDIR}/phase3_validation.csv`, passes the path
  through `GeneratorReq.validation_data_filepath`. **This is the only
  cache — the file is re-downloaded every process start.**
- Every matched record instantiates a fresh `GeneratePipeline`, which reads
  and normalizes the same CSV into a Polars DataFrame on every iteration
  ([src/init_migration/generate_pipeline.py:146-213](../../src/init_migration/generate_pipeline.py#L146-L213)).
  This is quadratic-ish per-run I/O; a comment in `main._cache_validation_csv`
  acknowledges an earlier version re-downloaded the full sheet for every
  record.

For each `OCDidIngestResp`:

1. `find_matches(ocdid)` ([src/init_migration/generate_pipeline.py:215-327](../../src/init_migration/generate_pipeline.py#L215-L327))
   - Parses OCDID with `ocdid_parser()` (raw dict, not `OCDIdParsed`).
   - Loads state FIPS via `src.utils.state_lookup.load_state_code_lookup()` (JSON on disk).
   - Filters validation CSV to `STATEFP == fips` and to Census "place" rows
     (`PLACEFP` populated); this drops county subdivisions on purpose because
     LSAD 25 collides between the two layers.
   - Exact normalized-name match first (`normalized_place_name`,
     LSAD-affix-stripped via `namelsad_to_display_name`). Fall back to
     `rapidfuzz.fuzz.token_sort_ratio` (or `difflib.SequenceMatcher` if
     rapidfuzz is missing) with threshold `0.85`.
   - Returns 0 / 1 / 2+ candidate rows.

2. Dispatch on match count:
   - **0 matches** → `DivGenerator.generate_division_stub(uuid=self.uuid)`
     + quarantine entry `reason=no_validation_match`, status `PARTIAL`.
   - **2+ matches** → stub division + quarantine entry
     `reason=multiple_matches`, status `PARTIAL`.
   - **1 match** → `DivGenerator.generate_division(val_rec, uuid)` builds a
     full Division; then `infer_jurisdiction_seed()` decides whether a
     Jurisdiction should exist; then `JurGenerator.generate_jurisdiction()`
     builds it. Status `SUCCESS`.
   - Any exception → status `FAILED`, error string captured.

3. `ensure_ancestor_stubs()`
   ([src/init_migration/generate_recursive.py:197-311](../../src/init_migration/generate_recursive.py#L197-L311))
   walks `OCDIdParsed.build_ancestor_ocdids()` and, for each ancestor
   level, checks the target directory for a YAML with a matching `ocdid`
   field; if absent, writes stub Division and Jurisdiction YAMLs.
   - Ancestor probing is a **linear scan of every `*.yaml` in the target
     directory** per ancestor per record
     ([src/init_migration/generate_recursive.py:37-58](../../src/init_migration/generate_recursive.py#L37-L58)) — this is O(N × M) where N is
     current-run records and M is on-disk stubs.
   - Failures are logged but non-fatal.

Rendering:

- YAML is written directly by `DivGenerator.dump_division`
  ([src/init_migration/generate_division.py:265-321](../../src/init_migration/generate_division.py#L265-L321))
  and `JurGenerator.dump_jurisdiction`
  ([src/init_migration/generate_jurisdiction.py:216-252](../../src/init_migration/generate_jurisdiction.py#L216-L252))
  via `yaml.dump(..., default_flow_style=False, sort_keys=False)`. Files
  land in `<output_dir>/divisions/<state>/local/<name>_<geoid>_<uuid>.yaml`
  and `<output_dir>/jurisdictions/<state>/local/<segment>_<uuid>.yaml`.
- Output dir defaults to `"."` (repo root), so live runs mutate
  `divisions/` and `jurisdictions/` in the working tree.
- `DivGenerator.dump_division` post-processes the dict to strip null
  optional `government_identifiers` fields and drop `metadata=None` — this
  is done in the dumper, not the model.
- `JurGenerator.dump_jurisdiction` derives the state segment from the
  original division OCDID (not the jurisdiction OCDID) because
  `ocdid_parser` chokes on the trailing unkeyed `/government` segment.
- No serializer sort or hashing — YAML key order is dict-insertion order.

### Phase 4 — Generation tracking ([src/init_migration/main.py:160-215](../../src/init_migration/main.py#L160-L215))

- Per calendar day, creates a DuckDB table `generation_tracking_YYYY_MM_DD`
  and upserts one row per record `(original_id, status, error,
  division_path, jurisdiction_path)`.
- Same DuckDB file as Phase 1/2 (`data/ocdid_pipeline.duckdb`).
- Idempotent within a day (`DELETE … WHERE original_id IN (…)` before
  `INSERT`); a new day creates a new table (so re-run history accumulates
  indefinitely).

## 3. Validation and rendering

Model-level validation happens only in Pydantic constructors:

- `Division.ensure_uuid5_id` derives `uuid5(NAMESPACE_URL,
  f"{ocdid}|{last_updated_date}")` when `id is None`
  ([src/models/division.py:143-148](../../src/models/division.py#L143-L148)).
  **This differs from the ID the matcher stores** (`uuid5(NAMESPACE_URL,
  ocdid_str)` with no date).
- `Jurisdiction` runs `validate_jurisdiction_id` and `ensure_uuid5_id`
  ([src/models/jurisdiction.py:182-207](../../src/models/jurisdiction.py#L182-L207)).
- `OCDIdStr` (Annotated type) enforces `ocd-division/` or `ocd-jurisdiction/`
  prefix and ≥2 segments ([src/models/ocdid.py:9-26](../../src/models/ocdid.py#L9-L26)).

There is no independent "OCD validation" pass — the master ↔ local join
in Phase 2 is the only canonical-membership check, and it happens *before*
generation, not after candidate OCDID synthesis.

## 4. Hidden and mutable state

- **DuckDB file** `data/ocdid_pipeline.duckdb`
  ([src/init_migration/download_manager.py:32](../../src/init_migration/download_manager.py#L32)) — persistent across
  runs; some tables replace (`master_ocdids`, generation tracking per day),
  others append (`local_ocdids`, `local_orphans`, `master_orphans`, and
  `ocdid_uuid_lookup` before the idempotency guard).
- **ETag cache** `.etag_cache.json` at repo root, written on
  `AsyncDownloader.__aexit__` ([src/init_migration/downloader.py:156-187](../../src/init_migration/downloader.py#L156-L187)).
- **Validation-CSV cache** `${TMPDIR}/phase3_validation.csv` — refreshed on
  every process start, single-file only.
- **CSV backup** `data/ocdid_uuid_lookup.csv` — written from DuckDB after
  Phase 2.
- **Working-tree writes** to `divisions/**` and `jurisdictions/**` when the
  CLI is run with default `output_dir="."`. `GeneratePipeline` takes
  `division_output_dir` / `jurisdiction_output_dir` arguments but `main.py`
  does not pass them through.
- **LSAD lookup** `src/data/lsad_map.json` — regenerated only via
  `python src/data/lsad_mapper.py`, which live-fetches a Census HTML page.
- **State lookup** `src/data/state_lookup.json` — read at runtime.

## 5. Network dependencies

| Call site | URL / endpoint | Reachability of alternative |
| --- | --- | --- |
| `DownloadManager.master_url()` | `raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers/country-us.csv` | ETag-cached; can be served from local snapshot post-Phase-4 |
| `DownloadManager.local_urls()` | `.../identifiers/country-us/state-<state>-local_gov.csv` | Same |
| `main._cache_validation_csv` | `docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/export?format=csv&gid=1481694121` | **Uncacheable**: no ETag support in current code — every process start fetches; hard dep on live Google Sheets. |
| `src/data/lsad_mapper.py:fetch_lsad_rows` | `www.census.gov/library/reference/code-lists/legal-status-codes.html` | Live HTML scrape; `src/data/lsad_map.json` is checked in, so runtime callers hit disk. |
| Clients (`src/clients/*.py`) | OpenAI, Gemini, Ollama, Brave, DDG | Not wired into `run_pipeline`; scaffolding only. `JurGenerator._ai_lookup` is a stub that raises `NotImplementedError` when `jurisdiction_ai_url=True`. |
| ArcGIS / TIGERweb / DCGIS | Referenced in `sourcing.source_url` fields of sample fixtures only | Not called by the pipeline; URLs are string metadata. |

## 6. Domain-specific logic

- **LSAD name stripping** ([src/utils/place_name.py](../../src/utils/place_name.py)) — pairs the
  Census LSAD code with the JSON lookup to remove prefix/suffix from
  `NAMELSAD`. Falls back to a hand-crafted regex when the code is missing.
- **Council-district display naming** in `_council_district_display_name`
  ([src/init_migration/generate_division.py:44-63](../../src/init_migration/generate_division.py#L44-L63)) — special-cases
  `place/council_district` and `anc/council_district`.
- **Jurisdiction decision tree** ([src/init_migration/jurisdiction_seed.py](../../src/init_migration/jurisdiction_seed.py)) —
  seven-step LSAD-based classifier (statistical → legislative → school →
  non-governing → LSAD 27 disambiguation stub → general government →
  unknown). Consumes hard-coded `STATISTICAL_LSAD_ENTITIES`,
  `LEGISLATIVE_TYPES`, `SCHOOL_CLASSES`, `GOVERNMENT_TYPES`,
  `NON_JURISDICTION_DIVISION_TYPES`. Contains many `TODO` comments about
  coverage.
- **DC ANC umbrella GEOID** ([src/init_migration/geoid_exception.py](../../src/init_migration/geoid_exception.py)) —
  `UMBRELLA_GEOID_MAP = {("dc", "anc"): "11001"}`. `_resolve_umbrella_geoid`
  is defined but **not called by any generator** — grep shows no imports;
  runtime records like `divisions/test/dc/local/anc_1a_district_1_*.yaml`
  have `geoid=11001` hardcoded in the fixture rather than resolved here.
  Flagged for reuse-inventory follow-up.
- **Jurisdiction OCDID synthesis** — three sites derive
  `ocd-jurisdiction/<div>/<classification>` from a division OCDID by
  string replace + regex, all identical:
  [generate_division.py:241-244](../../src/init_migration/generate_division.py#L241-L244),
  [generate_jurisdiction.py:186-192](../../src/init_migration/generate_jurisdiction.py#L186-L192),
  [generate_pipeline.py:502-518](../../src/init_migration/generate_pipeline.py#L502-L518).

## 7. Data flow diagram

```
                         .etag_cache.json                data/ocdid_pipeline.duckdb
                                ▲                                ▲
                                │                                │
        opencivicdata GitHub    │                                │
        (master + per-state)  ──┴─► AsyncDownloader ──► DuckDB (master_ocdids / local_ocdids)
                                                            │
                                                            ▼
                                                     OCDidMatcher
                                     (inner join → OCDidIngestResp; anti-joins → orphans)
                                                            │
                                                            ▼
        civicdata.tech Google Sheet ──► TMPDIR/phase3_validation.csv ──► GeneratePipeline
                                                            │
        src/data/lsad_map.json ──────────────────────────► normalize NAMELSAD (place_name)
        src/data/state_lookup.json ──────────────────────► FIPS lookup
                                                            │
                                                            ▼
                                             find_matches (polars, fuzzy 0.85)
                                                            │
                        ┌───────────────────────────────────┼───────────────────────────────────┐
                        ▼                                   ▼                                   ▼
                 0 matches (stub)                     1 match (full)                     2+ matches (stub)
                        │                                   │                                   │
                        ├─► NoMatch.ocdid_no_validation_div │                                   │
                        │        (reason=no_validation_match)                                   │
                        │                                   ▼                                   ├─► NoMatch.ocdid_no_validation_div
                        │                            DivGenerator.generate_division              │        (reason=multiple_matches)
                        │                                   │
                        │                                   ▼
                        │                            infer_jurisdiction_seed
                        │                                   │
                        │                                   ▼
                        │                            JurGenerator.generate_jurisdiction
                        │                                   │
                        ▼                                   ▼                                   ▼
                    dump_division ────────────► divisions/<state>/local/*.yaml
                    dump_jurisdiction ────────► jurisdictions/<state>/local/*.yaml
                    ensure_ancestor_stubs  ──► ancestor state/county stubs in same trees
                                                            │
                                                            ▼
                                          generation_tracking_YYYY_MM_DD (DuckDB)
```

## 8. Testable seams and coverage

| Stage | Unit tests | Integration tests |
| --- | --- | --- |
| Downloader | [tests/src/init_migration/test_downloader_*.py](../../tests/src/init_migration) (cache, config, core, errors, github) | [tests/integration/test_async_downloader_integration.py](../../tests/integration/test_async_downloader_integration.py) |
| DownloadManager | [test_download_manager.py](../../tests/src/init_migration/test_download_manager.py) | Covered by full-stage integration |
| OCDidMatcher | [test_ocdid_matcher.py](../../tests/src/init_migration/test_ocdid_matcher.py) | [test_stage1_integration.py](../../tests/integration/test_stage1_integration.py) |
| DivGenerator | [test_generate_division.py](../../tests/src/init_migration/test_generate_division.py) — 59 LOC, thin | [test_generate_pipeline_integration.py](../../tests/integration/test_generate_pipeline_integration.py) |
| JurGenerator | [test_generate_jurisdiction.py](../../tests/src/init_migration/test_generate_jurisdiction.py) — 477 LOC, dense | Same |
| ensure_ancestor_stubs | [test_generate_recursive.py](../../tests/src/init_migration/test_generate_recursive.py) — 272 LOC | Indirectly via generate-pipeline integration |
| jurisdiction_seed | [test_jurisdiction_seed.py](../../tests/src/init_migration/test_jurisdiction_seed.py) — 43 LOC, thin | Same |
| Main / CLI | [test_main_cli.py](../../tests/src/init_migration/test_main_cli.py) — 35 LOC | [test_main_integration.py](../../tests/integration/test_main_integration.py) |
| pipeline_models | [test_pipeline_models.py](../../tests/src/init_migration/test_pipeline_models.py) | — |
| Models | [tests/src/models/test_division.py](../../tests/src/models/test_division.py), [test_jurisdiction.py](../../tests/src/models/test_jurisdiction.py), [test_ocdid.py](../../tests/src/models/test_ocdid.py) | — |
| utils/yaml_manager | [test_yaml_manager.py](../../tests/src/utils/test_yaml_manager.py) | — |
| utils/deterministic_id | [test_deterministic_id.py](../../tests/src/utils/test_deterministic_id.py) | — |

Coverage gaps worth noting for later phases:

- No unit test targets `src/utils/ocdid.py:ocdid_parser` directly (only
  via `OCDIdParsed.parse_ocdid`).
- `geoid_exception._resolve_umbrella_geoid` has no callers and no tests.
- `find_matches` fuzzy-match path (`rapidfuzz` fallback, threshold) has no
  dedicated tests distinct from integration behavior.
- `dump_division` / `dump_jurisdiction` post-processing (null pruning,
  metadata drop) is exercised via integration only.
- `Division.load_division` / `dump_division` on the model itself are
  labelled "# Untested" in [src/models/division.py:151-176](../../src/models/division.py#L151-L176) —
  the runtime path uses the generator's `dump_division`, not the model's.

## 9. Known contradictions with the rework design

Flagged for the resolution-phase reviewers, not fixed here:

- **UUID drift** — matcher stores `uuid5(NS_URL, ocdid)`; models compute
  `uuid5(NS_URL, f"{ocdid}|{yyyy-mm-dd}")` in `ensure_uuid5_id`. Both are
  passed around as "the UUID", so `OCDidIngestResp.uuid` and
  `Division.id`/`Jurisdiction.id` can disagree for the same OCDID on the
  same day. Root `AGENTS.md`'s stable-identity mandate (Task 2.1 in the
  plan) will need to reconcile this.
- **UUID identity is time-sensitive** — the `|<date>` suffix means the same
  record generated on two different days gets two different UUIDs, which
  directly violates rework spec §5 "Stable Identity" and §38.
- **Rendering embeds resolution** — the dumpers still parse OCDIDs and
  choose an output subtree, contradicting rework spec §27 (rendering has
  no resolution logic) and §10.3 (deterministic serializer).
- **`main` runs mutate the checked-in working tree** by default
  (`output_dir="."`); this couples "the pipeline" and "the repo state"
  in a way the rework explicitly separates.
- **Live Google-Sheets dependency** on every run (`DIVISIONS_SHEET_CSV_URL`)
  — nothing local can regenerate outputs without this fetch. Rework §16
  ("prefer bulk source snapshots") requires this to move behind a snapshot
  layer.
- **Ancestor-stub linear scan** is O(N × M) and rewrites stubs any time
  a matching YAML has drifted, silently. Phase-9 (canonical model
  construction) should replace this with a resolver + explicit ancestor
  materialisation step.
- **No Census GUS / TIGER adapter exists**. The pipeline reads OCD divs
  and *derives* Census identifiers from the civicdata.tech spreadsheet;
  the rework wants the reverse (GUS → OCD).

## 10. What is intentionally out of scope for this document

- Field-level model schemas — see [`model_inventory.md`](model_inventory.md).
- Which module gets salvaged — see [`reuse_inventory.md`](reuse_inventory.md).
- OCDID parsing/normalization catalogue — see [`ocdid_inventory.md`](ocdid_inventory.md).
- Sample-output enumeration — see [`sample_output_inventory.md`](sample_output_inventory.md).
