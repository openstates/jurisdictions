---
id: reuse-inventory
type: rework-inventory
owner: rework
status: draft
last_updated: 2026-08-08
tags: [rework, phase-1, archaeology, reuse]
task: "Phase 1 — Task 1.2 (issue #132)"
scope: dispositions for every module on `131-gus-pipeline-rework` at commit b5c67c5
---

# Reuse Inventory (Task 1.2)

Every non-trivial module in `src/` gets one of four dispositions with a
one-line rationale and its covering tests. This is guidance for the phases
that follow — no code moves here.

Dispositions:

- **REUSE** — behavior fits the target design; keep as-is (may still get
  minor cosmetic edits).
- **ADAPT** — the semantics are right but the API, signature, or data
  contract needs work to fit the rework architecture.
- **REPLACE** — belongs to the old OCD-first orientation, or is a hidden
  coupling the rework must break.
- **UNDECIDED** — needs a rework-phase owner to decide; called out
  explicitly.

## Legend for the "Covered by" column

Paths are relative to repo root. "—" means no direct test file covers the
module. "(integration)" means only end-to-end integration exercises it.

## Models (`src/models/`)

| Module | Disposition | Rationale | Covered by |
| --- | --- | --- | --- |
| [`source.py`](../../src/models/source.py) | ADAPT | `SourceObj` has field/name/type/url but no dataset/release/vintage/publication_date/retrieval_date (Phase 2.2 requires them). `source_url: dict[str, HttpUrl \| FtpUrl \| FileUrl]` is unusual — a keyed URL dict is doing what a plain URL + optional label should do. | tests/src/models/test_division.py, tests/src/models/test_jurisdiction.py (indirect) |
| [`ocdid.py`](../../src/models/ocdid.py) | REUSE (with follow-up in ocdid_inventory) | `OCDIdParsed` is the mandated parser and already handles both `ocd-division` and `ocd-jurisdiction`. `build_ancestor_ocdids` is useful. | [tests/src/models/test_ocdid.py](../../tests/src/models/test_ocdid.py) |
| [`division.py`](../../src/models/division.py) | ADAPT | Model is close but `id` uses `uuid5(ocdid\|date)` — violates rework §5 (stable UUID). `Geometry` is arcGIS-only (contradicts §18). `GovernmentIdentifiers` bakes census fields directly in the model rather than as an external-identifier collection (§22). No `valid_from`/`valid_to` at Geometry level. | [tests/src/models/test_division.py](../../tests/src/models/test_division.py) |
| [`jurisdiction.py`](../../src/models/jurisdiction.py) | ADAPT | `url` is required (violates rework §23 "URLs are enrichment"), `metadata: dict = default_factory=dict` conflicts with declared `JurisdictionMetadata` type (silent mismatch), UUID has same time-drift bug as Division, `__main__` sample block is broken (`legislative_sessions` typed as dict but passed a `SessionDetail`). | [tests/src/models/test_jurisdiction.py](../../tests/src/models/test_jurisdiction.py) |

## Utilities (`src/utils/`)

| Module | Disposition | Rationale | Covered by |
| --- | --- | --- | --- |
| [`ocdid.py`](../../src/utils/ocdid.py) | ADAPT | `ocdid_parser` is the string-split helper `OCDIdParsed` wraps; keep for internal use but callers should go through `OCDIdParsed.parse_ocdid()` (root `AGENTS.md` §OCD ID Parsing Rules). `generate_ocdids` uses `i18naddress` to enumerate US states — helpful for state seeding but Phase 5 government normalizer supersedes it. | — (indirectly via test_ocdid.py) |
| [`deterministic_id.py`](../../src/utils/deterministic_id.py) | REPLACE | Provides `uuid5(NS_URL, f"{ocdid}\|{date}")` helpers that formalise the time-drift bug. Rework §5 wants stable UUID from OCDID alone. | [tests/src/utils/test_deterministic_id.py](../../tests/src/utils/test_deterministic_id.py) |
| [`place_name.py`](../../src/utils/place_name.py) | REUSE | LSAD-aware NAMELSAD→display-name is genuinely useful and Census-agnostic. `build_place_names_by_state` scans `country-us.csv` — will need to move to the source-snapshot layer (Phase 4). | — (integration only) |
| [`state_lookup.py`](../../src/utils/state_lookup.py) | REUSE | Thin JSON loader; fine. | — (integration only) |
| [`datetime.py`](../../src/utils/datetime.py) | REUSE | 6-line helper (`ymd`). | — (integration only) |
| [`str_utils.py`](../../src/utils/str_utils.py) | UNDECIDED | 25 LOC utility; needs a read to decide. Flag for the phase that touches it. | — |
| [`csv_utils.py`](../../src/utils/csv_utils.py) | REPLACE | Sync `requests.get(url)` fetcher that duplicates `AsyncDownloader` and pulls in `requests`. Not called from `run_pipeline`; kill or replace with `AsyncDownloader` when Phase 17 (cleanup) runs. | — |
| [`yaml_manager.py`](../../src/utils/yaml_manager.py) | ADAPT | Solid CRUDL layer with Pydantic validation; will be the natural home for Phase 10 deterministic serializer. Needs `sort_keys=True` + `default_flow_style=False` (both currently `sort_keys=False`), and its `dump_*` methods bypass the `exclude_none` post-processing that `DivGenerator.dump_division` does. | [tests/src/utils/test_yaml_manager.py](../../tests/src/utils/test_yaml_manager.py) |

## init_migration pipeline (`src/init_migration/`)

| Module | Disposition | Rationale | Covered by |
| --- | --- | --- | --- |
| [`main.py`](../../src/init_migration/main.py) | REPLACE | Orchestrator wired to OCD-first flow. Will be re-written when Phase 9/10 canonical construction + rendering exist. Salvage: rich `Console` output helpers, `configure_logging`, per-day tracking-table naming pattern. | [tests/src/init_migration/test_main_cli.py](../../tests/src/init_migration/test_main_cli.py), [tests/integration/test_main_integration.py](../../tests/integration/test_main_integration.py) |
| [`download_manager.py`](../../src/init_migration/download_manager.py) | ADAPT | Concept generalises to any snapshot source (Census GUS, TIGER, OCD master), but hard-codes GitHub raw base + DuckDB table names. Split into a shared `SnapshotFetcher` + adapter-specific loaders. Phase 4 target. | [tests/src/init_migration/test_download_manager.py](../../tests/src/init_migration/test_download_manager.py) |
| [`downloader.py`](../../src/init_migration/downloader.py) | REUSE | High-quality async HTTP client with ETag, retries, backoff, HTML guard, and GitHub base64 decode. Reuse under Phase 4 source-snapshot layer verbatim. | tests/src/init_migration/test_downloader_*.py (5 files) |
| [`ocdid_matcher.py`](../../src/init_migration/ocdid_matcher.py) | REPLACE | Inverts the target direction (local OCD → master OCD instead of GUS → OCD) and constructs UUIDs the wrong way. Phase 8 (OCD Validation) supersedes its "matching" role. Salvage: the orphan-classification concept for quarantine. | [tests/src/init_migration/test_ocdid_matcher.py](../../tests/src/init_migration/test_ocdid_matcher.py), [tests/integration/test_stage1_integration.py](../../tests/integration/test_stage1_integration.py) |
| [`generate_pipeline.py`](../../src/init_migration/generate_pipeline.py) | REPLACE | Orchestrates OCD-first path and does resolution inside the generator. Rework §27 forbids resolution in rendering; §16 forbids per-run Google-Sheets fetch. Rewrite as `Resolver` + `Renderer` split. Salvage: fuzzy-match threshold rationale (comment at 46-60), PLACEFP layer filter (329-341), 0/1/2-match dispatch pattern. | [tests/integration/test_generate_pipeline_integration.py](../../tests/integration/test_generate_pipeline_integration.py) |
| [`generate_division.py`](../../src/init_migration/generate_division.py) | ADAPT | Field-mapping logic (validation record → `GovernmentIdentifiers`) is reusable when the source becomes GUS. Post-dump null-pruning belongs in the serializer. `_division_exists`/`_load_existing_division` are stubs (return False / raise NotImplementedError) — dead code. | [tests/src/init_migration/test_generate_division.py](../../tests/src/init_migration/test_generate_division.py) |
| [`generate_jurisdiction.py`](../../src/init_migration/generate_jurisdiction.py) | ADAPT | Basic Jurisdiction assembly logic is fine. `_ai_lookup` is a stub raising NotImplementedError. Fallback URL is `https://opencivicdata.org/division/<ocdid>` — not a real jurisdiction website; must be removed once `url` becomes optional (Phase 2.6). | [tests/src/init_migration/test_generate_jurisdiction.py](../../tests/src/init_migration/test_generate_jurisdiction.py) |
| [`generate_recursive.py`](../../src/init_migration/generate_recursive.py) | ADAPT | Ancestor-stub concept survives; O(N × M) glob scan and unsourced `SourceType.SCRAPED` labels do not. Move ancestor materialisation to Phase 9 canonical construction so stubs are built from the government/geography layer, not derived from a leaf. | [tests/src/init_migration/test_generate_recursive.py](../../tests/src/init_migration/test_generate_recursive.py) |
| [`jurisdiction_seed.py`](../../src/init_migration/jurisdiction_seed.py) | ADAPT | Decision tree captures real domain knowledge (statistical LSADs, legislative/school/government classes, LSAD 27 escape hatch, DC ANC handling). This is Phase 7 OCDID/exception content — extract classifier + tables, drop the OCDID string parsing. Many TODO comments to resolve. | [tests/src/init_migration/test_jurisdiction_seed.py](../../tests/src/init_migration/test_jurisdiction_seed.py) |
| [`geoid_exception.py`](../../src/init_migration/geoid_exception.py) | UNDECIDED | Defines `UMBRELLA_GEOID_MAP` for DC ANCs, but no runtime caller (grep-verified — the ANC 1A sample fixture hardcodes `geoid=11001` instead of going through this helper). Either wire it in during Phase 6 (Resolver) or delete during Phase 17. | — |
| [`pipeline_models.py`](../../src/init_migration/pipeline_models.py) | ADAPT | `OCDidIngestResp`, `GeneratorReq`, `GeneratorResp`, `Status` are the current DTO layer; Status has the four terminal states we want (SUCCESS/SKIPPED/PARTIAL/FAILED). Rework §28 wants richer terminal statuses (`COMPLETE`, `NO_GEOGRAPHY`, `NEW_OCDID`, `AMBIGUOUS_OCDID`, `DIVISION_NOT_FOUND`, `SOURCE_ERROR`) — replace `PARTIAL` with these. | [tests/src/init_migration/test_pipeline_models.py](../../tests/src/init_migration/test_pipeline_models.py) |
| [`mappers.py`](../../src/init_migration/mappers.py) | REPLACE | `ocdid_master_mapper` is a stale dict of legacy column-name mappings; `convert_lsad_definitions` is a TODO stub; overlaps with `src/data/lsad_mapper.py`. Consolidate into a single LSAD module. | — |
| [`parsers.py`](../../src/init_migration/parsers.py) | UNDECIDED | Two 3-line polars helpers with no callers (grep-verified). Delete during cleanup unless Phase 4 wants them. | — |

## Data assets (`src/data/`)

| Module / file | Disposition | Rationale | Covered by |
| --- | --- | --- | --- |
| [`lsad_map.json`](../../src/data/lsad_map.json) | REUSE | Generated snapshot of Census LSAD codes; keep as a source-snapshot asset. | — |
| [`lsad_mapper.py`](../../src/data/lsad_mapper.py) | ADAPT | Rewrite generator to consume a saved HTML snapshot (rework §16, §31) rather than live-fetching Census on each regeneration. Currently `httpx.get` at import path. | — |
| [`state_lookup.json`](../../src/data/state_lookup.json) | REUSE | Static reference table. | — |
| [`ocdid_segment_names_by_cnt.csv`](../../src/data/ocdid_segment_names_by_cnt.csv) | UNDECIDED | Frequency dump from OCD IDs — useful diagnostic; unclear whether it's a runtime dependency. Grep confirms no importer. | — |

## Clients (`src/clients/`)

| Module | Disposition | Rationale | Covered by |
| --- | --- | --- | --- |
| [`config.py`](../../src/clients/config.py) | REUSE | Env-key loader with typed `MissingAPIKeyError`. | — |
| [`openai.py`](../../src/clients/openai.py) | REUSE | Thin async wrapper. | — |
| [`gemini.py`](../../src/clients/gemini.py) | REUSE | Thin async wrapper. | — |
| [`ollama.py`](../../src/clients/ollama.py) | REUSE | Thin async wrapper. | — |
| [`brave.py`](../../src/clients/brave.py) | REUSE | Thin async wrapper. | — |
| [`ddg.py`](../../src/clients/ddg.py) | REUSE | Thin async wrapper. | — |

All clients are scaffolding for future enrichment (jurisdiction URL lookup)
and are not called by `run_pipeline` today. Their presence is fine; the
rework can wire them in behind Phase 15 (special districts) or an
enrichment stage that stays *out* of model validation and rendering.

## Errors (`src/errors.py`)

| Class | Disposition |
| --- | --- |
| `Error`, `APIRetryError`, `UnexpectedContentError`, `DownloaderNotInitializedError`, `CacheError` | REUSE — shared exception hierarchy for the downloader. |
| `OCDidNotFoundError` | REUSE — will be needed by Phase 8 quarantine. |
| `OCDIdParsingError` | REUSE — raised by `ocdid_parser` / `OCDIdParsed.parse_ocdid`. |

## Tests (`tests/`)

| Path | Disposition | Rationale |
| --- | --- | --- |
| [tests/conftest.py](../../tests/conftest.py) | REUSE | Provides `respx_mock`, `sample_csv_content`, `sample_json_content`, `github_api_response`, `clean_duckdb`. `clean_duckdb` comment already flags that it exists only because the pipeline's ingest is not idempotent — will become unnecessary once the source-snapshot layer replaces DuckDB append-inserts. |
| [tests/src/init_migration/conftest.py](../../tests/src/init_migration/conftest.py) | REUSE | Local fixtures for downloader/downloadmanager tests. |
| [tests/src/models/](../../tests/src/models) | REUSE | Hypothesis-based property tests for Division/Jurisdiction UUID derivation — will need updates when UUID scheme changes (Phase 2.1). |
| [tests/src/utils/test_deterministic_id.py](../../tests/src/utils/test_deterministic_id.py) | REPLACE | Cover a module we plan to REPLACE; will move to whatever replaces `deterministic_id`. |
| [tests/src/utils/test_yaml_manager.py](../../tests/src/utils/test_yaml_manager.py) | REUSE | Solid; expect additions for deterministic-serializer requirement. |
| [tests/src/init_migration/test_downloader_*.py](../../tests/src/init_migration) | REUSE | Downloader is REUSE, tests stay. |
| [tests/src/init_migration/test_ocdid_matcher.py](../../tests/src/init_migration/test_ocdid_matcher.py) | REPLACE | Covers a module we plan to REPLACE. |
| [tests/src/init_migration/test_generate_*.py](../../tests/src/init_migration) | ADAPT | Follow their subjects. |
| [tests/src/init_migration/test_jurisdiction_seed.py](../../tests/src/init_migration/test_jurisdiction_seed.py) | ADAPT | Currently thin (43 LOC); needs coverage for every decision-tree branch when moved into Phase 7. |
| [tests/integration/test_stage1_integration.py](../../tests/integration/test_stage1_integration.py) | REPLACE | End-to-end for OCD-first flow. |
| [tests/integration/test_main_integration.py](../../tests/integration/test_main_integration.py) | REPLACE | Same; also leaves `data/ocdid_pipeline.duckdb` behind (TODO comment at line ~14). |
| [tests/integration/test_async_downloader_integration.py](../../tests/integration/test_async_downloader_integration.py) | REUSE | Downloader survives. |
| [tests/integration/test_generate_pipeline_integration.py](../../tests/integration/test_generate_pipeline_integration.py) | ADAPT | Structure (5 named records covering match / stub / quarantine cases) is exactly what Phase 3 golden harness needs; migrate the record set and expected classifications into the fixture-based harness. |
| [tests/fixtures/divisions_sample.py](../../tests/fixtures/divisions_sample.py), [jurisdictions_sample.py](../../tests/fixtures/jurisdictions_sample.py) | REUSE-AS-GOLDEN | Hand-authored Pydantic instances that reproduce the checked-in `tests/sample_output/**/*.yaml`. Treat as immutable per root `AGENTS.md`. |
| [tests/sample_data/*.csv](../../tests/sample_data), [`.py`](../../tests/sample_data) | UNDECIDED | Six files; some are ad-hoc validation subsets. Cross-reference during Phase 3 fixture layout. |

## Sample outputs (`tests/sample_output/`)

Read-only per root `AGENTS.md`. See [`sample_output_inventory.md`](sample_output_inventory.md).

## Divisions / jurisdictions working trees

| Path | Disposition | Rationale |
| --- | --- | --- |
| `divisions/dc/local/`, `divisions/hi/local/`, `divisions/oh/local/`, `divisions/tx/local/`, `divisions/wa/local/` | UNDECIDED | Empty on disk (verified via `ls`); pipeline writes into these dirs at runtime. Keep as the canonical output roots. |
| `divisions/examples/` | UNDECIDED | Two example YAMLs (`Miamisburg_*.yaml`, `Parma_*.yaml`) unrelated to the sample-output test fixtures. Confirm intent during Phase 11. |
| `divisions/test_auto_merge.yaml` | UNDECIDED | Loose YAML at the top of `divisions/`. Possibly a leftover from the YAML auto-merge workflow (see `docs/YAML_AUTO_MERGE_*`). Confirm and either move or delete. |
| `jurisdictions/oh/local/`, `jurisdictions/tx/local/`, `jurisdictions/wa/local/` | UNDECIDED | Same as divisions. |

## Summary counts

| Disposition | Count of major modules |
| --- | --- |
| REUSE | 11 |
| ADAPT | 11 |
| REPLACE | 7 |
| UNDECIDED | 8 |

The imbalance toward ADAPT / REPLACE reflects that the current pipeline
is OCD-first and needs re-orientation; the imbalance toward REUSE in
`src/clients/` and `src/models/ocdid.py` reflects that OCD-parsing
infrastructure and enrichment clients are directionally correct.

## Follow-ups for later phases

- **Phase 2 (Domain Model Stabilization)** must decide how `SourceObj` grows
  release/vintage fields without breaking checked-in YAML sourcing lists.
- **Phase 3 (Golden Harness)** should salvage the 5-record fixture list
  from `tests/integration/test_generate_pipeline_integration.py:SAMPLE_OCDIDS`
  as the canonical Phase-3 fixture roster.
- **Phase 4 (Source Snapshot Layer)** should reuse `AsyncDownloader`
  wholesale and split `DownloadManager` into per-source adapters.
- **Phase 7 (OCDID Rule Engine)** should absorb `jurisdiction_seed`'s
  decision tree and every `_derive_jurisdiction_ocdid` clone; see
  [`ocdid_inventory.md`](ocdid_inventory.md).
- **Phase 17 (Cleanup)** targets: `csv_utils.py`, `mappers.py`,
  `parsers.py`, `deterministic_id.py`, the empty
  `_load_existing_division`/`_load_existing_jurisdiction` stubs.
