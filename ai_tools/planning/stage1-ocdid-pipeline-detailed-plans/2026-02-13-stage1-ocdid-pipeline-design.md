# Stage 1: OCDid Pipeline — Design Document

Date: 2026-02-13

## Goal

Build Stage 1 of the init_migration pipeline: fetch OCD ID data from the Open
Civic Data repo, match local records against the national master list, generate
UUIDs, and produce `OCDidIngestResp` models with a persistent DuckDB lookup
table. No Division/Jurisdiction YAML files are produced in this stage.

## Architecture Overview

```
main.py (orchestrator + CLI)
  │
  ├─► DownloadManager (new module)
  │     • Uses AsyncDownloader (cleaned up as pure library)
  │     • Fetches master CSV + 57 state/territory local CSVs
  │     • Rich progress bars with speed/duration stats
  │     • ETag/Last-Modified caching, --force override
  │     • Loads CSVs directly into DuckDB persistent tables
  │
  └─► OCDidMatcher (new module)
        • Exact join on `id` column: local records ↔ master records
        • Three outcomes: match, local orphan, master orphan
        • Generates UUID per matched record via deterministic_id.py
        • Stores UUID↔OCD-ID lookup table in DuckDB + CSV backup
        • Returns list[OCDidIngestResp]
```

## Module Design

### main.py — Orchestrator

Pure orchestrator. No business logic. Responsibilities:

- Parse CLI arguments (state filter, force download, log directory)
- Load state list from `src/data/state_lookup.json` (or CLI override)
- Call DownloadManager to fetch and load data
- Call OCDidMatcher to match records and produce results
- Report summary stats

CLI interface:

```
uv run python src/init_migration/main.py                    # all 57 states/territories
uv run python src/init_migration/main.py --state wa         # single state
uv run python src/init_migration/main.py --state wa,tx,oh   # multiple states
uv run python src/init_migration/main.py --force            # bypass ETag cache
uv run python src/init_migration/main.py --log-dir /tmp/logs
```

### downloader.py — AsyncDownloader (cleaned up)

Refactored as a pure library with no business logic, no `main()`, no
`if __name__` block. Keeps:

- Async HTTP with bounded concurrency (semaphore)
- ETag/Last-Modified conditional caching (JSON file)
- Retry with exponential backoff + jitter
- GitHub API response decoding (base64, download_url fallback)
- HTML response detection
- Optional GitHub token auth

Removes:

- `main()` function and example orchestration code
- URL lists and business logic

No changes to the public API: `fetch_bytes()`, `download_to()`,
`fetch_many()`, `download_many()`.

### download_manager.py — DownloadManager (new)

Business logic layer between the orchestrator and the downloader. Responsibilities:

- Build URL lists from state lookup data (master + local CSVs)
- Drive AsyncDownloader to fetch all CSVs concurrently
- Display rich progress bars: per-file progress, overall progress, download
  speed, per-file duration
- Log ETag cache hits (skipped downloads) as informational alerts
- Load fetched CSV bytes directly into DuckDB persistent tables:
  - `master_ocdids` — national master list
  - `local_ocdids_{state}` — per-state local records (or one combined
    `local_ocdids` table with a state column)
- Handle download failures gracefully (log, continue with remaining states)

DuckDB location: `data/ocdid_pipeline.duckdb` (committed to repo).

### ocdid_matcher.py — OCDidMatcher (new)

Matching and UUID generation. Responsibilities:

- Query DuckDB: exact join of local records against master on `id` column.
  The **master list is the source of truth**. Local state files are used as a
  cross-check to verify that the national list captured all state OIDs and to
  detect temporal drift (OIDs added to states but not yet derived into the
  national file, or vice versa).
- Classify each record into one of three outcomes:
  - **Match** — local record found in master. Happy path.
  - **Local orphan** — local record has no master match (drift detected).
  - **Master orphan** — master record for a given state has no local match.
- For each matched record:
  - Parse OCD ID into `OCDidParsed` model
  - Generate deterministic UUID via `deterministic_id.generate_id()`
  - Build `OCDidIngestResp(uuid, ocdid_parsed, raw_record)` where `raw_record`
    contains the **master** record's columns (not local)
- Store results:
  - **UUID↔OCD-ID lookup table** in DuckDB (`ocdid_uuid_lookup`)
  - **CSV backup** of the lookup table to `data/ocdid_uuid_lookup.csv`
  - **Orphan tables** in DuckDB for quarantine review
    (`local_orphans`, `master_orphans`)
- Return `list[OCDidIngestResp]` to the orchestrator
- Support idempotent re-runs: check lookup table before generating new UUIDs

### state_lookup.py — Updated path

`src/utils/state_lookup.py` updated to load from `src/data/state_lookup.json`
(moved from `src/state_lookup.json`). No API changes. Verify the file contains
all 57 expected entries (currently 56 — identify and add the missing entry).

## Data Flow

```
GitHub OCD Repo
  │
  ├── country-us.csv (master, ~100k+ records)
  └── country-us/state-{st}-local_gov.csv (per state, local govs only)
       │
       ▼
  AsyncDownloader (concurrent fetch, ETag caching)
       │
       ▼
  DuckDB persistent tables
  ┌─────────────────────┬──────────────────────┐
  │ master_ocdids       │ local_ocdids         │
  │   id (text, PK)     │   id (text, PK)      │
  │   name (text)       │   name (text)         │
  │   ...               │   state (text)        │
  │                     │   ...                 │
  └─────────────────────┴──────────────────────┘
       │
       ▼  exact join on `id`
  ┌──────────────┬───────────────┬────────────────┐
  │ Matched      │ Local orphans │ Master orphans │
  │ (happy path) │ (drift)       │ (missing local)│
  └──────┬───────┴───────┬───────┴───────┬────────┘
         │               │               │
         ▼               ▼               ▼
  OCDidIngestResp   DuckDB quarantine tables
  + UUID lookup     (local_orphans, master_orphans)
  (DuckDB + CSV)
```

## Model Changes

### OCDidIngestResp — two type changes

From `src/init_migration/pipeline_models.py` (renamed from `models.py`):

```python
class OCDidIngestResp(BaseModel):
    uuid: str             # changed from UUID → str (holds oid1- deterministic ID)
    ocdid: OCDidParsed    # changed from str → OCDidParsed
    raw_record: dict[str, Any]
```

- `uuid` is now `str` to hold the `oid1-` prefixed deterministic ID from
  `deterministic_id.generate_id()`. If we later revert to standard UUIDs,
  this is the only field to change.
- The raw OCD ID string remains accessible via `resp.ocdid.raw_ocdid`.

### OCDidParsed — no changes

From `src/models/ocdid.py`:

```python
class OCDidParsed(BaseModel):
    country: str = "us"
    state: Optional[str] = None
    county: Optional[str] = None
    place: Optional[str] = None
    subdivision: Optional[str] = None
    raw_ocdid: str
```

## Progress Display (rich)

Three phase-level progress bars (up to 58 items for download/load — 1 master +
up to 57 state/territory files — fewer if state-filtered; up to 57 for matching):

1. **Download** — "Downloading [X/N] files" with per-file speed and duration
2. **Load** — "Loading [X/N] into DuckDB"
3. **Match/Build** — "Matching [X/N] states"

Plus:

- Overall pipeline progress across all three phases
- Summary table on completion: files downloaded, cache hits, failures
- Match results summary: total matched, local orphans, master orphans

## File/Directory Changes

```
src/
  data/
    state_lookup.json          ← moved from src/state_lookup.json
  init_migration/
    main.py                    ← rewritten as orchestrator + CLI
    downloader.py              ← cleaned up (remove main(), examples)
    download_manager.py        ← new: download business logic + rich progress
    ocdid_matcher.py           ← new: matching + UUID generation
    orchestrator.py            ← remove (replaced by main.py)
    get_ocdid_files.py         ← remove (early Polars-based attempt, replaced by
                                  DuckDB approach in download_manager)
    models.py                  ← rename to pipeline_models.py; change ocdid type
    parsers.py                 ← keep as-is (CSV bytes → Polars utility)
  utils/
    state_lookup.py            ← update path to src/data/state_lookup.json
    deterministic_id.py        ← no changes (used by ocdid_matcher)
    ocdid.py                   ← no changes (ocdid_parser used by matcher)
data/
  ocdid_pipeline.duckdb        ← new: persistent DuckDB (committed to repo)
  ocdid_uuid_lookup.csv        ← new: CSV backup of lookup table (committed to repo)
logs/                           ← new: log directory (gitignored)
```

## Dependencies

Current `pyproject.toml` already includes: `duckdb`, `httpx`, `polars`,
`pydantic`, `rapidfuzz`. New dependency needed:

- `rich` — progress bars and terminal display

## Resolved Questions

1. **Master CSV size** — Load the full file into DuckDB unfiltered. ~100k rows
   is trivial for DuckDB; filter at query time.
2. **CLI library** — Use `argparse` (stdlib). Revisit if the CLI grows in later
   stages.
3. **Data directory** — Hardcode `data/` at project root. Not configurable via
   CLI.
