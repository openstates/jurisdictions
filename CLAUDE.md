# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ETL pipeline that generates Division and Jurisdiction YAML files for US local governments (cities, towns, counties, etc.) from Open Civic Data (OCD) identifiers and civic research data. Part of the OpenStates ecosystem. Data models use Pydantic v2 and output is YAML files organized by state.

## Commands

```bash
# Install dependencies (requires uv and Python 3.12+)
uv sync --all-extras

# Run tests
uv run pytest

# Run a single test file
uv run pytest tests/test_downloader_core.py

# Run a single test
uv run pytest tests/test_downloader_core.py::test_name -v

# Run tests excluding integration/slow
uv run pytest -m "not integration and not slow"

# Lint
uv run ruff check .

# Run Stage 1 pipeline (all states)
uv run python src/init_migration/main.py

# Run Stage 1 pipeline (specific states, force re-download)
uv run python src/init_migration/main.py --state wa,tx,oh --force
```

## Architecture

### Data Models (`src/models/`)

Core Pydantic v2 models that define the YAML output schema. **Do not modify without discussion** — they are the contract for downstream consumers.

- `division.py` — `Division` model: represents a geopolitical boundary (city, county, etc.) with Census identifiers (`GovernmentIdentifiers`), geometries, and a `jurisdiction_id` linking to the corresponding Jurisdiction. Serializes to `divisions/<state>/local/` as YAML.
- `jurisdiction.py` — `Jurisdiction` model: represents a governing body (city council, school board, etc.) with `ClassificationEnum` types (government, legislature, school_system, judicial, etc.). Serializes to `jurisdictions/<state>/local/` as YAML.
- `source.py` — `SourceObj` + `SourceType` enum: provenance tracking for each field, distinguishing AI-generated, human-researched, and programmatically-scraped data.
- `ocdid.py` — `OCDidParsed`: Pydantic wrapper for parsed OCD IDs.

### Pipeline (`src/init_migration/`)

Multi-stage pipeline that processes OCD IDs into Division + Jurisdiction YAML pairs:

**Stage 1 — OCD ID Ingestion** (download, match, lookup table):

- `main.py` — Stage 1 orchestrator and CLI entry point. Parses `--state`, `--force`, `--log-dir` arguments, chains DownloadManager → OCDidMatcher, prints rich summary table.
- `download_manager.py` — `DownloadManager`: builds URLs for master (`country-us.csv`) and per-state local CSVs from GitHub raw, fetches concurrently via `AsyncDownloader`, loads into DuckDB (`master_ocdids` and `local_ocdids` tables) using temp-file bridge (DuckDB requires file paths, not bytes).
- `ocdid_matcher.py` — `OCDidMatcher`: exact-joins local against master on `id` column, classifies as match/local-orphan/master-orphan, generates deterministic `oid1-` UUIDs, stores UUID-OCD-ID lookup in DuckDB + CSV backup. Master data is source of truth; local files cross-check for temporal drift.
- `downloader.py` — `AsyncDownloader`: async HTTP client with bounded concurrency, ETag/Last-Modified caching, retry with exponential backoff, GitHub API response decoding (base64 content or download_url fallback).
- `pipeline_models.py` — Pipeline-specific request/response models: `GeneratorReq`, `GeneratorResp`, `OCDidIngestResp` (with `uuid: str` for oid1- IDs and `ocdid: OCDidParsed`), `GeneratorStatus`.

**Stage 2 — Division/Jurisdiction Generation** (fuzzy match, YAML output):

- `generate_pipeline.py` — `GeneratePipeline` orchestrator: loads validation CSV via Polars, fuzzy-matches OCD IDs to research records (using rapidfuzz with 0.85 threshold), branches on 0/1/2+ matches, delegates to `DivGenerator` and `JurGenerator`. Tracks unmatched records in `NoMatch` quarantine for researcher review.
- `generate_division.py` — `DivGenerator`: produces full Divisions from matched validation records or stub Divisions when no match exists. Maps Census fields (NAMELSAD, GEOID, STATEFP, LSAD, SLDUST, SLDLST, COUNTYFP) to the Division model.
- `generate_jurisdiction.py` — `JurGenerator`: derives Jurisdictions from Divisions. Jurisdiction OCD ID schema: `ocd-jurisdiction/<division_id_without_prefix>/<type>`.
- `parsers.py` — CSV bytes to Polars DataFrame conversion utilities.

### Utilities (`src/utils/`)

- `ocdid.py` — `ocdid_parser()`: splits OCD ID strings into component dict (base, country, state, place, etc.). `generate_ocdids()`: generates state-level OCD IDs using i18naddress validation rules.
- `place_name.py` — `namelsad_to_display_name()`: strips Census LSAD suffixes (city, town, village, borough, etc.) from NAMELSAD to get display names. Used heavily in fuzzy matching.
- `deterministic_id.py` — `generate_id()`/`decode_id()`: creates decodable, uuid-like IDs with `oid1-` prefix. Encodes OCD ID + version into zlib-compressed, base32-encoded, hyphen-grouped tokens.
- `state_lookup.py` — State abbreviation to FIPS code lookup from `src/data/state_lookup.json`.

### Key Domain Concepts

- **OCD ID** (Open Civic Data Identifier): canonical identifiers like `ocd-division/country:us/state:wa/place:seattle`. Division IDs use `ocd-division/` prefix; Jurisdiction IDs use `ocd-jurisdiction/` prefix with a classification suffix (e.g., `/government`, `/legislature`).
- **Validation Research CSV**: manually-researched spreadsheet with Census-sourced fields (NAMELSAD, GEOID, STATEFP, LSAD, etc.) that the pipeline fuzzy-matches against OCD IDs.
- **Quarantine**: unmatched or ambiguously-matched records saved as CSV for human review.

## Testing Conventions

- Test files mirror source paths: `tests/src/init_migration/test_pipeline.py` tests `src/init_migration/generate_pipeline.py`.
- Async tests use `@pytest.mark.asyncio` with a custom runner in `conftest.py` (not pytest-asyncio).
- HTTP mocking uses `respx` library.
- Pytest markers: `integration`, `slow`, `asyncio` (configured in pyproject.toml with `--strict-markers`).
- Fixtures per test file; shared fixtures in `tests/conftest.py`.
- Sample data lives in `tests/sample_data/` and `tests/sample_output/`.

## Imports

The project uses `src` as the package root (e.g., `from src.models.division import Division`). The `conftest.py` adds the project root to `sys.path` to make this work without installation.