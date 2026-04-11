# Stage 1: OCDid Pipeline — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Stage 1 pipeline that fetches OCD ID CSVs, matches local records against the national master, generates deterministic UUIDs, and produces `OCDidIngestResp` models with a persistent DuckDB lookup table.

**Architecture:** `main.py` orchestrator calls `DownloadManager` (async fetch + DuckDB load) then `OCDidMatcher` (join + UUID generation). `AsyncDownloader` is cleaned up as a pure HTTP library. Rich progress bars for all three phases.

**Tech Stack:** Python 3.12+, DuckDB (persistent), httpx (async HTTP), rich (progress), pydantic v2 (models), uuid5_id.py (UUIDs)

**Design doc:** `ai_tools/planning/stage1-ocdid-pipeline-detailed-plans/2026-02-13-stage1-ocdid-pipeline-design.md`

---

## Task 1: Project scaffolding — move files, add dependency, update .gitignore

**Files:**
- Move: `src/state_lookup.json` → `src/data/state_lookup.json`
- Modify: `src/utils/state_lookup.py`
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Create: `data/.gitkeep`
- Create: `logs/.gitkeep`

**Step 1: Create `src/data/` directory and move `state_lookup.json`**

```bash
mkdir -p src/data
git mv src/state_lookup.json src/data/state_lookup.json
```

**Step 2: Update `src/utils/state_lookup.py` to use new path**

Replace the current path resolution with:

```python
import json
from pathlib import Path

def load_state_code_lookup():
    """
    Loads state lookup data from src/data/state_lookup.json.
    Returns:
        list[dict]: State code lookup records.
    """
    data_dir = Path(__file__).resolve().parents[1] / "data"
    path = data_dir / "state_lookup.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
```

**Step 3: Add `rich` dependency to `pyproject.toml`**

In the `[project]` dependencies list, add:

```
"rich>=14.0.0",
```

**Step 4: Update `.gitignore`**

Add at the end of `.gitignore`:

```
# Pipeline logs
logs/

# Downloader log (legacy location)
src/init_migration/downloader.log
```

**Step 5: Create `data/` and `logs/` directories with `.gitkeep`**

```bash
mkdir -p data logs
touch data/.gitkeep logs/.gitkeep
```

**Step 6: Run existing tests to verify nothing broke**

Run: `uv sync --all-extras && uv run pytest -x -v`
Expected: All existing tests pass. The state_lookup path change may break
tests that depend on it — fix any import path issues.

**Step 7: Commit**

```bash
git add src/data/ src/utils/state_lookup.py pyproject.toml .gitignore data/ logs/
git rm --cached src/state_lookup.json 2>/dev/null || true
git commit -m "chore: scaffold stage 1 — move state_lookup.json, add rich dep, create data/ and logs/"
```

---

## Task 2: Rename `models.py` → `pipeline_models.py` and update `OCDidIngestResp`

**Files:**
- Rename: `src/init_migration/models.py` → `src/init_migration/pipeline_models.py`
- Modify: `src/init_migration/generate_pipeline.py`
- Modify: `src/init_migration/generate_division.py`
- Modify: `src/init_migration/generate_jurisdiction.py`
- Modify: `tests/src/init_migration/test_generate_pipeline.py`
- Modify: `tests/src/init_migration/test_generate_division.py`
- Test: `tests/src/init_migration/test_pipeline_models.py` (new)

**Step 1: Write the failing test for the updated `OCDidIngestResp`**

Create `tests/src/init_migration/test_pipeline_models.py`:

```python
"""Tests for pipeline_models — specifically the OCDidIngestResp model changes."""
import pytest
from src.init_migration.pipeline_models import OCDidIngestResp
from src.models.ocdid import OCDidParsed
from src.utils.uuid5_id import generate_id


def test_ocdid_ingest_resp_accepts_ocdid_parsed():
    """OCDidIngestResp.ocdid should accept an OCDidParsed instance."""
    parsed = OCDidParsed(
        country="us",
        state="wa",
        place="seattle",
        raw_ocdid="ocd-division/country:us/state:wa/place:seattle",
    )
    det_id = generate_id("ocd-division/country:us/state:wa/place:seattle")
    resp = OCDidIngestResp(
        uuid=det_id,
        ocdid=parsed,
        raw_record={"id": "ocd-division/country:us/state:wa/place:seattle", "name": "Seattle"},
    )
    assert resp.ocdid.state == "wa"
    assert resp.ocdid.place == "seattle"
    assert resp.ocdid.raw_ocdid == "ocd-division/country:us/state:wa/place:seattle"


def test_ocdid_ingest_resp_uuid_is_oid1_string():
    """OCDidIngestResp.uuid should accept an oid1- deterministic ID string."""
    parsed = OCDidParsed(
        country="us",
        state="wa",
        place="seattle",
        raw_ocdid="ocd-division/country:us/state:wa/place:seattle",
    )
    det_id = generate_id("ocd-division/country:us/state:wa/place:seattle")
    resp = OCDidIngestResp(
        uuid=det_id,
        ocdid=parsed,
        raw_record={},
    )
    assert isinstance(resp.uuid, str)
    assert resp.uuid.startswith("oid1-")


def test_ocdid_ingest_resp_rejects_plain_string_for_ocdid():
    """OCDidIngestResp.ocdid should not accept a plain string."""
    with pytest.raises(Exception):
        OCDidIngestResp(
            uuid="oid1-fake",
            ocdid="ocd-division/country:us/state:wa/place:seattle",
            raw_record={},
        )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/src/init_migration/test_pipeline_models.py -v`
Expected: ImportError — `pipeline_models` does not exist yet.

**Step 3: Rename the file and update the model**

```bash
git mv src/init_migration/models.py src/init_migration/pipeline_models.py
```

In `src/init_migration/pipeline_models.py`, update the `OCDidIngestResp` class:

```python
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime, UTC
from enum import Enum
from src.models.ocdid import OCDidParsed


DIVISIONS_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/export?format=csv&gid=1481694121"

class OCDidIngestResp(BaseModel):
    uuid: str             # oid1- deterministic ID from uuid5_id.generate_id()
    ocdid: OCDidParsed
    raw_record: dict[str, Any]

class GeneratorReq(BaseModel):
    """
    Request object for the Division/Jurisdiction generation pipeline.
    Includes flags to determine which parts of the data to load/populate.
    """
    data: OCDidIngestResp
    validation_data_filepath: str = DIVISIONS_SHEET_CSV_URL
    build_base_object: bool = True
    jurisdiction_ai_url: bool = False
    division_geo_req: bool = False
    division_population_req: bool = False
    asof_datetime: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

class Status(str, Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"

class GeneratorStatus(BaseModel):
    status: Status
    error: str | None = None

class GeneratorResp(BaseModel):
    data: OCDidIngestResp
    status: GeneratorStatus
    division_path: str | None
    jurisdiction_path: str | None

class JurGeneratorReq(GeneratorReq):
    division_id: str
```

**Step 4: Update all imports referencing the old module name**

In each of these files, replace `from src.init_migration.models import` with
`from src.init_migration.pipeline_models import`:

- `src/init_migration/generate_pipeline.py:19`
- `src/init_migration/generate_division.py:12`
- `src/init_migration/generate_jurisdiction.py` (if it imports from models)
- `tests/src/init_migration/test_generate_division.py:6`
- `tests/src/init_migration/test_generate_pipeline.py` (check for imports)

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/src/init_migration/ -v`
Expected: All tests pass including the new `test_pipeline_models.py`.

**Step 6: Commit**

```bash
git add src/init_migration/pipeline_models.py src/init_migration/generate_*.py tests/
git rm --cached src/init_migration/models.py 2>/dev/null || true
git commit -m "refactor: rename models.py to pipeline_models.py, change OCDidIngestResp.ocdid to OCDidParsed"
```

---

## Task 3: Clean up `downloader.py` — remove business logic, keep pure library

**Files:**
- Modify: `src/init_migration/downloader.py`
- Test: `tests/test_downloader_core.py` (existing — verify still passes)

**Step 1: Run existing downloader tests to establish baseline**

Run: `uv run pytest tests/test_downloader_core.py tests/test_downloader_cache.py tests/test_downloader_errors.py tests/test_downloader_github.py tests/test_downloader_config.py -v`
Expected: All pass.

**Step 2: Remove `main()` function and `if __name__` block from `downloader.py`**

Delete everything from the `# Example orchestration` comment (around line 496)
through the end of the file:

```python
# DELETE from here to end of file:
# -----------------------------
# Example orchestration
# -----------------------------
async def main() -> None:
    ...

if __name__ == "__main__":
    asyncio.run(main())
```

**Step 3: Remove the stray `downloader.log` file**

```bash
rm -f src/init_migration/downloader.log
```

**Step 4: Run downloader tests to verify nothing broke**

Run: `uv run pytest tests/test_downloader_core.py tests/test_downloader_cache.py tests/test_downloader_errors.py tests/test_downloader_github.py tests/test_downloader_config.py -v`
Expected: All pass.

**Step 5: Commit**

```bash
git add src/init_migration/downloader.py
git rm --cached src/init_migration/downloader.log 2>/dev/null || true
git commit -m "refactor: clean up downloader.py — remove example main(), keep pure library"
```

---

## Task 4: Remove obsolete modules — `orchestrator.py`, `get_ocdid_files.py`

**Files:**
- Remove: `src/init_migration/orchestrator.py`
- Remove: `src/init_migration/get_ocdid_files.py`

**Step 1: Verify no other code imports these modules**

Search for imports:

```bash
uv run ruff check . 2>&1 || true
```

Also grep:

```
grep -r "from.*orchestrator import\|import orchestrator\|from.*get_ocdid_files import\|import get_ocdid_files" src/ tests/
```

Expected: No hits outside of the files themselves. If there are hits, update
those imports first.

**Step 2: Remove the files**

```bash
git rm src/init_migration/orchestrator.py
git rm src/init_migration/get_ocdid_files.py
```

**Step 3: Run all tests to verify nothing broke**

Run: `uv run pytest -x -v`
Expected: All pass.

**Step 4: Commit**

```bash
git commit -m "chore: remove obsolete orchestrator.py and get_ocdid_files.py"
```

---

## Task 5: Build `download_manager.py` — URL building and DuckDB loading

This is the business logic layer. We build it in two parts: first the URL
building and DuckDB loading (testable without network), then the async
download orchestration with rich progress (Task 6).

**Files:**
- Create: `src/init_migration/download_manager.py`
- Test: `tests/src/init_migration/test_download_manager.py`

**Step 1: Write failing tests for URL building and DuckDB loading**

Create `tests/src/init_migration/test_download_manager.py`:

```python
"""Tests for DownloadManager — URL building and DuckDB loading."""
import pytest
import duckdb
from pathlib import Path

from src.init_migration.download_manager import DownloadManager


# --- URL Building ---

def test_build_master_url():
    """Master URL should point to country-us.csv on GitHub raw."""
    dm = DownloadManager(states=["wa"])
    url = dm.master_url()
    assert "country-us.csv" in url
    assert "raw.githubusercontent.com" in url or "api.github.com" in url


def test_build_local_urls_single_state():
    """Local URL for one state should contain the lowercased state code."""
    dm = DownloadManager(states=["WA"])
    urls = dm.local_urls()
    assert len(urls) == 1
    assert "state-wa-local_gov.csv" in urls[0]


def test_build_local_urls_multiple_states():
    """Local URLs for multiple states should produce one URL per state."""
    dm = DownloadManager(states=["wa", "tx", "oh"])
    urls = dm.local_urls()
    assert len(urls) == 3


def test_all_urls_includes_master_plus_locals():
    """all_urls() should return master + all local URLs."""
    dm = DownloadManager(states=["wa", "tx"])
    urls = dm.all_urls()
    assert len(urls) == 3  # 1 master + 2 local


# --- DuckDB Loading ---

def test_load_master_csv_to_duckdb(tmp_path):
    """Loading master CSV bytes should create master_ocdids table in DuckDB."""
    db_path = str(tmp_path / "test.duckdb")
    dm = DownloadManager(states=["wa"], db_path=db_path)

    csv_bytes = b"id,name\nocd-division/country:us/state:wa/place:seattle,Seattle\nocd-division/country:us/state:wa/place:tacoma,Tacoma\n"
    dm.load_master_csv(csv_bytes)

    conn = duckdb.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM master_ocdids").fetchone()[0]
    conn.close()
    assert count == 2


def test_load_local_csv_to_duckdb(tmp_path):
    """Loading a local CSV should insert rows into local_ocdids table with state column."""
    db_path = str(tmp_path / "test.duckdb")
    dm = DownloadManager(states=["wa"], db_path=db_path)

    csv_bytes = b"id,name\nocd-division/country:us/state:wa/place:seattle,Seattle\n"
    dm.load_local_csv(csv_bytes, state="wa")

    conn = duckdb.connect(db_path)
    rows = conn.execute("SELECT * FROM local_ocdids WHERE state = 'wa'").fetchall()
    conn.close()
    assert len(rows) == 1


def test_load_multiple_states_to_duckdb(tmp_path):
    """Loading CSVs for multiple states should combine into one local_ocdids table."""
    db_path = str(tmp_path / "test.duckdb")
    dm = DownloadManager(states=["wa", "tx"], db_path=db_path)

    wa_csv = b"id,name\nocd-division/country:us/state:wa/place:seattle,Seattle\n"
    tx_csv = b"id,name\nocd-division/country:us/state:tx/place:austin,Austin\n"
    dm.load_local_csv(wa_csv, state="wa")
    dm.load_local_csv(tx_csv, state="tx")

    conn = duckdb.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM local_ocdids").fetchone()[0]
    conn.close()
    assert count == 2
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/src/init_migration/test_download_manager.py -v`
Expected: ImportError — `download_manager` does not exist.

**Step 3: Implement `DownloadManager`**

Create `src/init_migration/download_manager.py`:

```python
"""
Business logic for downloading OCD ID CSVs and loading them into DuckDB.

Responsibilities:
- Build URL lists for master and per-state local CSVs
- Load CSV bytes into DuckDB persistent tables
- Orchestrate async downloads with progress display (see run_downloads())
"""

import duckdb
import logging

logger = logging.getLogger(__name__)

RAW_BASE = "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers"
MASTER_PATH = "country-us.csv"
LOCAL_TEMPLATE = "country-us/state-{state}-local_gov.csv"

DEFAULT_DB_PATH = "data/ocdid_pipeline.duckdb"


class DownloadManager:
    """Builds URLs, fetches CSVs via AsyncDownloader, loads into DuckDB."""

    def __init__(
        self,
        states: list[str],
        db_path: str = DEFAULT_DB_PATH,
    ) -> None:
        self.states = [s.lower() for s in states]
        self.db_path = db_path

    def master_url(self) -> str:
        """Return the URL for the national master CSV."""
        return f"{RAW_BASE}/{MASTER_PATH}"

    def local_urls(self) -> list[str]:
        """Return URLs for each state's local government CSV."""
        return [
            f"{RAW_BASE}/{LOCAL_TEMPLATE.format(state=s)}"
            for s in self.states
        ]

    def all_urls(self) -> list[str]:
        """Return master URL + all local URLs."""
        return [self.master_url()] + self.local_urls()

    def load_master_csv(self, csv_bytes: bytes) -> int:
        """Load master CSV bytes into DuckDB master_ocdids table.

        Args:
            csv_bytes: Raw CSV content as bytes.

        Returns:
            Number of rows loaded.
        """
        conn = duckdb.connect(self.db_path)
        try:
            conn.execute(
                "CREATE OR REPLACE TABLE master_ocdids AS "
                "SELECT * FROM read_csv_auto(?, ignore_errors=true)",
                [csv_bytes],
            )
            count = conn.execute("SELECT COUNT(*) FROM master_ocdids").fetchone()[0]
            logger.info(f"Loaded {count} rows into master_ocdids")
            return count
        finally:
            conn.close()

    def load_local_csv(self, csv_bytes: bytes, state: str) -> int:
        """Load a state's local CSV bytes into DuckDB local_ocdids table.

        Appends rows with a `state` column. Creates the table on first call.

        Args:
            csv_bytes: Raw CSV content as bytes.
            state: Two-letter state code (lowercased).

        Returns:
            Number of rows loaded for this state.
        """
        state = state.lower()
        conn = duckdb.connect(self.db_path)
        try:
            # Create table if it doesn't exist, using first CSV's schema + state column
            conn.execute(
                "CREATE TABLE IF NOT EXISTS local_ocdids AS "
                "SELECT *, ? AS state FROM read_csv_auto(?, ignore_errors=true) WHERE 1=0",
                [state, csv_bytes],
            )
            # Insert rows with state column
            conn.execute(
                "INSERT INTO local_ocdids "
                "SELECT *, ? AS state FROM read_csv_auto(?, ignore_errors=true)",
                [state, csv_bytes],
            )
            count = conn.execute(
                "SELECT COUNT(*) FROM local_ocdids WHERE state = ?", [state]
            ).fetchone()[0]
            logger.info(f"Loaded {count} rows for state '{state}' into local_ocdids")
            return count
        finally:
            conn.close()
```

**Note:** The `read_csv_auto(?, ...)` with bytes parameter may need adjustment
depending on DuckDB version. If DuckDB requires a file path, write bytes to a
temp file first. Test will reveal this — adjust implementation accordingly.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/src/init_migration/test_download_manager.py -v`
Expected: All pass.

**Step 5: Commit**

```bash
git add src/init_migration/download_manager.py tests/src/init_migration/test_download_manager.py
git commit -m "feat: add DownloadManager — URL building and DuckDB loading"
```

---

## Task 6: Add async download orchestration with rich progress to `DownloadManager`

**Files:**
- Modify: `src/init_migration/download_manager.py`
- Test: `tests/src/init_migration/test_download_manager.py` (add async tests)

**Step 1: Write failing test for async download orchestration**

Add to `tests/src/init_migration/test_download_manager.py`:

```python
import respx
import httpx

@pytest.mark.asyncio
async def test_run_downloads_fetches_and_loads(tmp_path, respx_mock):
    """run_downloads() should fetch all URLs and load into DuckDB."""
    db_path = str(tmp_path / "test.duckdb")
    dm = DownloadManager(states=["wa"], db_path=db_path)

    master_csv = b"id,name\nocd-division/country:us/state:wa/place:seattle,Seattle\n"
    local_csv = b"id,name\nocd-division/country:us/state:wa/place:seattle,Seattle\n"

    respx_mock.get(dm.master_url()).mock(
        return_value=httpx.Response(200, content=master_csv)
    )
    respx_mock.get(dm.local_urls()[0]).mock(
        return_value=httpx.Response(200, content=local_csv)
    )

    stats = await dm.run_downloads(force=False, show_progress=False)

    assert stats["master_rows"] > 0
    assert stats["local_rows"] > 0
    assert stats["files_downloaded"] >= 1


@pytest.mark.asyncio
async def test_run_downloads_handles_missing_local(tmp_path, respx_mock):
    """run_downloads() should continue if a state's local CSV returns 404."""
    db_path = str(tmp_path / "test.duckdb")
    dm = DownloadManager(states=["wa", "zz"], db_path=db_path)

    master_csv = b"id,name\nocd-division/country:us/state:wa/place:seattle,Seattle\n"
    local_wa = b"id,name\nocd-division/country:us/state:wa/place:seattle,Seattle\n"

    respx_mock.get(dm.master_url()).mock(
        return_value=httpx.Response(200, content=master_csv)
    )
    respx_mock.get(dm.local_urls()[0]).mock(
        return_value=httpx.Response(200, content=local_wa)
    )
    respx_mock.get(dm.local_urls()[1]).mock(
        return_value=httpx.Response(404)
    )

    stats = await dm.run_downloads(force=False, show_progress=False)

    assert stats["files_failed"] == 1
    assert stats["local_rows"] > 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/src/init_migration/test_download_manager.py::test_run_downloads_fetches_and_loads -v`
Expected: AttributeError — `run_downloads` does not exist.

**Step 3: Implement `run_downloads()` method**

Add to `src/init_migration/download_manager.py`:

```python
import asyncio
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TransferSpeedColumn
from src.init_migration.downloader import AsyncDownloader, DownloaderConfig


class DownloadManager:
    # ... (existing __init__, URL methods, load methods) ...

    async def run_downloads(
        self,
        force: bool = False,
        show_progress: bool = True,
        downloader_config: DownloaderConfig | None = None,
    ) -> dict:
        """Fetch all CSVs concurrently and load into DuckDB.

        Args:
            force: Bypass ETag cache and re-download everything.
            show_progress: Show rich progress bars (disable for testing).
            downloader_config: Optional custom downloader config.

        Returns:
            dict with stats: files_downloaded, files_cached, files_failed,
            master_rows, local_rows.
        """
        cfg = downloader_config or DownloaderConfig(
            concurrency=12,
            max_retries=3,
            http2=True,
            etag_cache_path=".etag_cache.json",
        )

        stats = {
            "files_downloaded": 0,
            "files_cached": 0,
            "files_failed": 0,
            "master_rows": 0,
            "local_rows": 0,
        }

        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            disable=not show_progress,
        )

        total_files = 1 + len(self.states)  # master + locals
        download_task = progress.add_task("Downloading", total=total_files)
        load_task = progress.add_task("Loading to DuckDB", total=total_files)

        with progress:
            async with AsyncDownloader(cfg) as downloader:
                # --- Download master ---
                try:
                    master_bytes = await downloader.fetch_bytes(
                        self.master_url(), force=force
                    )
                    if master_bytes is None:
                        logger.info("Master CSV unchanged (ETag cache hit)")
                        stats["files_cached"] += 1
                    else:
                        stats["files_downloaded"] += 1
                except Exception as e:
                    logger.error(f"Failed to download master CSV: {e}")
                    stats["files_failed"] += 1
                    master_bytes = None
                progress.advance(download_task)

                # --- Download locals concurrently ---
                local_results: dict[str, bytes | None] = {}
                local_urls = self.local_urls()

                async def fetch_local(state: str, url: str):
                    try:
                        data = await downloader.fetch_bytes(url, force=force)
                        if data is None:
                            logger.info(f"Local CSV for {state} unchanged (cache hit)")
                            stats["files_cached"] += 1
                        else:
                            stats["files_downloaded"] += 1
                        local_results[state] = data
                    except Exception as e:
                        logger.warning(f"Failed to download local CSV for {state}: {e}")
                        stats["files_failed"] += 1
                        local_results[state] = None
                    progress.advance(download_task)

                await asyncio.gather(
                    *(fetch_local(s, u) for s, u in zip(self.states, local_urls))
                )

            # --- Load into DuckDB ---
            if master_bytes:
                stats["master_rows"] = self.load_master_csv(master_bytes)
            progress.advance(load_task)

            for state in self.states:
                csv_bytes = local_results.get(state)
                if csv_bytes:
                    rows = self.load_local_csv(csv_bytes, state)
                    stats["local_rows"] += rows
                progress.advance(load_task)

        return stats
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/src/init_migration/test_download_manager.py -v`
Expected: All pass.

**Step 5: Commit**

```bash
git add src/init_migration/download_manager.py tests/src/init_migration/test_download_manager.py
git commit -m "feat: add async download orchestration with rich progress to DownloadManager"
```

---

## Task 7: Build `ocdid_matcher.py` — matching, UUID generation, lookup table

**Files:**
- Create: `src/init_migration/ocdid_matcher.py`
- Test: `tests/src/init_migration/test_ocdid_matcher.py`

**Step 1: Write failing tests for matching logic**

Create `tests/src/init_migration/test_ocdid_matcher.py`:

```python
"""Tests for OCDidMatcher — join logic, UUID generation, lookup table."""
import pytest
import duckdb
from pathlib import Path

from src.init_migration.ocdid_matcher import OCDidMatcher
from src.init_migration.pipeline_models import OCDidIngestResp


@pytest.fixture
def populated_db(tmp_path):
    """Create a DuckDB with master and local tables for testing."""
    db_path = str(tmp_path / "test.duckdb")
    conn = duckdb.connect(db_path)

    conn.execute("""
        CREATE TABLE master_ocdids AS SELECT * FROM (VALUES
            ('ocd-division/country:us/state:wa/place:seattle', 'Seattle'),
            ('ocd-division/country:us/state:wa/place:tacoma', 'Tacoma'),
            ('ocd-division/country:us/state:tx/place:austin', 'Austin')
        ) AS t(id, name)
    """)

    conn.execute("""
        CREATE TABLE local_ocdids AS SELECT * FROM (VALUES
            ('ocd-division/country:us/state:wa/place:seattle', 'Seattle', 'wa'),
            ('ocd-division/country:us/state:wa/place:tacoma', 'Tacoma', 'wa'),
            ('ocd-division/country:us/state:wa/place:olympia', 'Olympia', 'wa'),
            ('ocd-division/country:us/state:tx/place:austin', 'Austin', 'tx')
        ) AS t(id, name, state)
    """)

    conn.close()
    return db_path


def test_match_finds_matching_records(populated_db):
    """Records in both master and local should be classified as matches."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"])
    results = matcher.run_matching()
    matched_ocdids = {r.ocdid.raw_ocdid for r in results.matched}
    assert "ocd-division/country:us/state:wa/place:seattle" in matched_ocdids
    assert "ocd-division/country:us/state:wa/place:tacoma" in matched_ocdids


def test_match_detects_local_orphans(populated_db):
    """Records in local but not master should be local orphans."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"])
    results = matcher.run_matching()
    orphan_ids = {r["id"] for r in results.local_orphans}
    assert "ocd-division/country:us/state:wa/place:olympia" in orphan_ids


def test_match_returns_ocdid_ingest_resp(populated_db):
    """Each matched record should produce a valid OCDidIngestResp."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"])
    results = matcher.run_matching()
    for resp in results.matched:
        assert isinstance(resp, OCDidIngestResp)
        assert resp.uuid is not None
        assert resp.ocdid.raw_ocdid.startswith("ocd-division/")
        assert resp.ocdid.state == "wa"


def test_raw_record_contains_master_data(populated_db):
    """raw_record should contain master list columns, not local columns."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"])
    results = matcher.run_matching()
    for resp in results.matched:
        # raw_record should have master columns (id, name) — not _local_state
        assert "id" in resp.raw_record
        assert "name" in resp.raw_record
        assert "_local_state" not in resp.raw_record


def test_match_generates_deterministic_uuids(populated_db):
    """Same OCD ID should produce the same UUID across runs."""
    matcher1 = OCDidMatcher(db_path=populated_db, states=["wa"])
    results1 = matcher1.run_matching()

    matcher2 = OCDidMatcher(db_path=populated_db, states=["wa"])
    results2 = matcher2.run_matching()

    uuids1 = {r.ocdid.raw_ocdid: str(r.uuid) for r in results1.matched}
    uuids2 = {r.ocdid.raw_ocdid: str(r.uuid) for r in results2.matched}
    assert uuids1 == uuids2


def test_lookup_table_created_in_duckdb(populated_db):
    """run_matching() should create an ocdid_uuid_lookup table."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"])
    matcher.run_matching()

    conn = duckdb.connect(populated_db)
    count = conn.execute("SELECT COUNT(*) FROM ocdid_uuid_lookup").fetchone()[0]
    conn.close()
    assert count >= 2  # seattle + tacoma


def test_lookup_csv_backup_created(populated_db, tmp_path):
    """run_matching() should export a CSV backup of the lookup table."""
    csv_path = str(tmp_path / "lookup.csv")
    matcher = OCDidMatcher(
        db_path=populated_db, states=["wa"], csv_backup_path=csv_path
    )
    matcher.run_matching()
    assert Path(csv_path).exists()
    content = Path(csv_path).read_text()
    assert "seattle" in content


def test_orphan_tables_created_in_duckdb(populated_db):
    """run_matching() should create local_orphans and master_orphans tables."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"])
    matcher.run_matching()

    conn = duckdb.connect(populated_db)
    local_orphan_count = conn.execute(
        "SELECT COUNT(*) FROM local_orphans"
    ).fetchone()[0]
    conn.close()
    assert local_orphan_count >= 1  # olympia
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/src/init_migration/test_ocdid_matcher.py -v`
Expected: ImportError — `ocdid_matcher` does not exist.

**Step 3: Implement `OCDidMatcher`**

Create `src/init_migration/ocdid_matcher.py`:

```python
"""
Matching OCD IDs between local and master tables, UUID generation, and
lookup table management.

Responsibilities:
- Exact join of local_ocdids against master_ocdids on `id` column
- Classify records: match, local orphan, master orphan
- Generate deterministic UUIDs via uuid5_id.py
- Store UUID↔OCD-ID lookup table in DuckDB + CSV backup
- Support idempotent re-runs
"""

from dataclasses import dataclass, field
import duckdb
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from src.init_migration.pipeline_models import OCDidIngestResp
from src.models.ocdid import OCDidParsed
from src.utils.ocdid import ocdid_parser
from src.utils.uuid5_id import generate_id

DEFAULT_DB_PATH = "data/ocdid_pipeline.duckdb"
DEFAULT_CSV_BACKUP = "data/ocdid_uuid_lookup.csv"


@dataclass
class MatchResults:
    """Container for matching results."""
    matched: list[OCDidIngestResp] = field(default_factory=list)
    local_orphans: list[dict] = field(default_factory=list)
    master_orphans: list[dict] = field(default_factory=list)


class OCDidMatcher:
    """Matches local OCD IDs against master, generates UUIDs, stores lookup."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        states: list[str] | None = None,
        csv_backup_path: str = DEFAULT_CSV_BACKUP,
    ) -> None:
        self.db_path = db_path
        self.states = [s.lower() for s in states] if states else []
        self.csv_backup_path = csv_backup_path

    def run_matching(self, show_progress: bool = False) -> MatchResults:
        """Run the full matching pipeline.

        Args:
            show_progress: Show rich progress bar for matching phase.

        Returns:
            MatchResults with matched OCDidIngestResp list and orphan lists.
        """
        results = MatchResults()
        conn = duckdb.connect(self.db_path)

        try:
            # Build state filter clause
            if self.states:
                placeholders = ", ".join(f"'{s}'" for s in self.states)
                state_filter = f"WHERE l.state IN ({placeholders})"
            else:
                state_filter = ""

            # --- Matched records: inner join ---
            # We select all master columns (m.*) because the master list is the
            # source of truth. Local state files are only used to cross-check
            # that the national list has all state OIDs and to detect drift.
            # l.state is included for filtering/grouping but not in raw_record.
            matched_rows = conn.execute(f"""
                SELECT m.*, l.state AS _local_state
                FROM local_ocdids l
                INNER JOIN master_ocdids m ON l.id = m.id
                {state_filter}
            """).fetchall()

            # Get master column names dynamically from query description
            col_names = [desc[0] for desc in conn.description]
            for row in matched_rows:
                row_dict = dict(zip(col_names, row))
                local_state = row_dict.pop("_local_state")  # separate from raw_record
                ocdid_str = row_dict["id"]

                # Parse OCD ID
                parsed_dict = ocdid_parser(ocdid_str)
                parsed = OCDidParsed(
                    raw_ocdid=ocdid_str,
                    country=parsed_dict.get("country", "us"),
                    state=parsed_dict.get("state"),
                    county=parsed_dict.get("county"),
                    place=parsed_dict.get("place"),
                )

                # Generate deterministic UUID
                det_id = generate_id(ocdid_str)

                resp = OCDidIngestResp(
                    uuid=det_id,
                    ocdid=parsed,
                    raw_record=row_dict,  # master record data only
                )
                results.matched.append(resp)

            logger.info(f"Matched {len(results.matched)} records")

            # --- Local orphans: left anti-join ---
            local_orphan_rows = conn.execute(f"""
                SELECT l.id, l.name, l.state
                FROM local_ocdids l
                LEFT JOIN master_ocdids m ON l.id = m.id
                WHERE m.id IS NULL
                {"AND l.state IN (" + placeholders + ")" if self.states else ""}
            """).fetchall()

            orphan_cols = ["id", "name", "state"]
            results.local_orphans = [
                dict(zip(orphan_cols, row)) for row in local_orphan_rows
            ]
            if results.local_orphans:
                logger.warning(f"Found {len(results.local_orphans)} local orphan(s)")

            # --- Master orphans: right anti-join (for selected states) ---
            # Records in master for these states but not in local
            if self.states:
                # Filter master by state extracted from OCD ID
                state_patterns = " OR ".join(
                    f"m.id LIKE '%/state:{s}/%'" for s in self.states
                )
                master_orphan_rows = conn.execute(f"""
                    SELECT m.id, m.name
                    FROM master_ocdids m
                    LEFT JOIN local_ocdids l ON m.id = l.id
                    WHERE l.id IS NULL AND ({state_patterns})
                """).fetchall()
            else:
                master_orphan_rows = conn.execute("""
                    SELECT m.id, m.name
                    FROM master_ocdids m
                    LEFT JOIN local_ocdids l ON m.id = l.id
                    WHERE l.id IS NULL
                """).fetchall()

            master_orphan_cols = ["id", "name"]
            results.master_orphans = [
                dict(zip(master_orphan_cols, row)) for row in master_orphan_rows
            ]
            if results.master_orphans:
                logger.warning(
                    f"Found {len(results.master_orphans)} master orphan(s)"
                )

            # --- Store lookup table ---
            self._store_lookup_table(conn, results)

            # --- Store orphan tables ---
            self._store_orphan_tables(conn, results)

        finally:
            conn.close()

        return results

    def _store_lookup_table(
        self, conn: duckdb.DuckDBPyConnection, results: MatchResults
    ) -> None:
        """Create/update UUID↔OCD-ID lookup table in DuckDB and CSV backup."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ocdid_uuid_lookup (
                uuid TEXT,
                ocdid TEXT,
                state TEXT,
                name TEXT
            )
        """)

        for resp in results.matched:
            conn.execute(
                """
                INSERT INTO ocdid_uuid_lookup (uuid, ocdid, state, name)
                SELECT ?, ?, ?, ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM ocdid_uuid_lookup WHERE ocdid = ?
                )
                """,
                [
                    str(resp.uuid),
                    resp.ocdid.raw_ocdid,
                    resp.ocdid.state or "",
                    resp.raw_record.get("name", ""),
                    resp.ocdid.raw_ocdid,
                ],
            )

        # CSV backup
        if self.csv_backup_path:
            Path(self.csv_backup_path).parent.mkdir(parents=True, exist_ok=True)
            conn.execute(
                f"COPY ocdid_uuid_lookup TO '{self.csv_backup_path}' (HEADER, DELIMITER ',')"
            )
            logger.info(f"CSV backup written to {self.csv_backup_path}")

    def _store_orphan_tables(
        self, conn: duckdb.DuckDBPyConnection, results: MatchResults
    ) -> None:
        """Store orphan records in DuckDB quarantine tables."""
        # Local orphans
        conn.execute("""
            CREATE TABLE IF NOT EXISTS local_orphans (
                id TEXT, name TEXT, state TEXT
            )
        """)
        for orphan in results.local_orphans:
            conn.execute(
                "INSERT INTO local_orphans VALUES (?, ?, ?)",
                [orphan["id"], orphan.get("name", ""), orphan.get("state", "")],
            )

        # Master orphans
        conn.execute("""
            CREATE TABLE IF NOT EXISTS master_orphans (
                id TEXT, name TEXT
            )
        """)
        for orphan in results.master_orphans:
            conn.execute(
                "INSERT INTO master_orphans VALUES (?, ?)",
                [orphan["id"], orphan.get("name", "")],
            )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/src/init_migration/test_ocdid_matcher.py -v`
Expected: All pass (after resolving the UUID type issue noted above).

**Step 5: Commit**

```bash
git add src/init_migration/ocdid_matcher.py tests/src/init_migration/test_ocdid_matcher.py
git commit -m "feat: add OCDidMatcher — matching, UUID generation, lookup table"
```

---

## Task 8: Build `main.py` — orchestrator with CLI

**Files:**
- Rewrite: `src/init_migration/main.py`
- Test: `tests/src/init_migration/test_main_cli.py`

**Step 1: Write failing test for CLI argument parsing**

Create `tests/src/init_migration/test_main_cli.py`:

```python
"""Tests for main.py CLI argument parsing."""
import pytest
from src.init_migration.main import parse_args


def test_parse_args_defaults():
    """Default args should process all states with no force."""
    args = parse_args([])
    assert args.state is None
    assert args.force is False
    assert args.log_dir == "logs"


def test_parse_args_single_state():
    """--state wa should parse a single state."""
    args = parse_args(["--state", "wa"])
    assert args.state == "wa"


def test_parse_args_multiple_states():
    """--state wa,tx,oh should parse comma-separated states."""
    args = parse_args(["--state", "wa,tx,oh"])
    assert args.state == "wa,tx,oh"


def test_parse_args_force():
    """--force should set force=True."""
    args = parse_args(["--force"])
    assert args.force is True


def test_parse_args_log_dir():
    """--log-dir should override default."""
    args = parse_args(["--log-dir", "/tmp/my_logs"])
    assert args.log_dir == "/tmp/my_logs"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/src/init_migration/test_main_cli.py -v`
Expected: ImportError — `parse_args` does not exist.

**Step 3: Implement `main.py`**

Rewrite `src/init_migration/main.py`:

```python
"""
Stage 1 OCDid Pipeline — Orchestrator

Entry point for the init_migration pipeline. Parses CLI arguments,
loads state list, calls DownloadManager and OCDidMatcher in sequence,
and reports summary stats.

Usage:
    uv run python src/init_migration/main.py
    uv run python src/init_migration/main.py --state wa
    uv run python src/init_migration/main.py --state wa,tx,oh --force
    uv run python src/init_migration/main.py --log-dir /tmp/logs
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.utils.state_lookup import load_state_code_lookup
from src.init_migration.download_manager import DownloadManager
from src.init_migration.ocdid_matcher import OCDidMatcher

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Stage 1 OCDid Pipeline — fetch, match, and generate lookup table"
    )
    parser.add_argument(
        "--state",
        type=str,
        default=None,
        help="Comma-separated state codes to process (e.g., wa,tx,oh). "
             "Default: all states from state_lookup.json.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Bypass ETag cache and force re-download of all files.",
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default="logs",
        help="Directory for log files (default: logs/).",
    )
    return parser.parse_args(argv)


def resolve_states(state_arg: str | None) -> list[str]:
    """Resolve state list from CLI argument or state_lookup.json.

    Args:
        state_arg: Comma-separated state codes, or None for all states.

    Returns:
        List of lowercase two-letter state codes.
    """
    if state_arg:
        return [s.strip().lower() for s in state_arg.split(",")]

    lookup = load_state_code_lookup()
    return [entry["stusps"].lower() for entry in lookup]


def configure_logging(log_dir: str) -> None:
    """Configure logging to write to the specified log directory."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)

    file_handler = logging.FileHandler(log_path / "pipeline.log")
    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    root.addHandler(console_handler)
    root.addHandler(file_handler)


def print_summary(
    console: Console,
    download_stats: dict,
    match_results,
) -> None:
    """Print a summary table using rich."""
    table = Table(title="Pipeline Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")

    table.add_row("Files downloaded", str(download_stats.get("files_downloaded", 0)))
    table.add_row("Files cached (ETag)", str(download_stats.get("files_cached", 0)))
    table.add_row("Files failed", str(download_stats.get("files_failed", 0)))
    table.add_row("Master rows loaded", str(download_stats.get("master_rows", 0)))
    table.add_row("Local rows loaded", str(download_stats.get("local_rows", 0)))
    table.add_row("Matched records", str(len(match_results.matched)))
    table.add_row("Local orphans", str(len(match_results.local_orphans)))
    table.add_row("Master orphans", str(len(match_results.master_orphans)))

    console.print(table)


async def run_pipeline(args: argparse.Namespace) -> None:
    """Run the full Stage 1 pipeline."""
    console = Console()
    states = resolve_states(args.state)

    logger.info(f"Starting pipeline for {len(states)} state(s)")
    console.print(f"Processing {len(states)} state(s): {', '.join(states)}")

    # Phase 1: Download and load
    dm = DownloadManager(states=states)
    download_stats = await dm.run_downloads(force=args.force)

    # Phase 2: Match and build
    matcher = OCDidMatcher(states=states)
    match_results = matcher.run_matching(show_progress=True)

    # Summary
    print_summary(console, download_stats, match_results)
    logger.info("Pipeline complete")


def main() -> None:
    """CLI entry point."""
    args = parse_args()
    configure_logging(args.log_dir)
    asyncio.run(run_pipeline(args))


if __name__ == "__main__":
    main()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/src/init_migration/test_main_cli.py -v`
Expected: All pass.

**Step 5: Commit**

```bash
git add src/init_migration/main.py tests/src/init_migration/test_main_cli.py
git commit -m "feat: rewrite main.py as Stage 1 orchestrator with CLI"
```

---

## Task 9: Integration test — end-to-end with sample data

**Files:**
- Create: `tests/src/init_migration/test_stage1_integration.py`

**Step 1: Write integration test**

```python
"""Integration test for the full Stage 1 pipeline with mocked HTTP."""
import pytest
import duckdb
import respx
import httpx
from pathlib import Path

from src.init_migration.main import resolve_states, run_pipeline
import argparse


MASTER_CSV = b"""id,name
ocd-division/country:us/state:wa/place:seattle,Seattle
ocd-division/country:us/state:wa/place:tacoma,Tacoma
ocd-division/country:us/state:tx/place:austin,Austin
ocd-division/country:us/state:tx/place:houston,Houston
"""

LOCAL_WA_CSV = b"""id,name
ocd-division/country:us/state:wa/place:seattle,Seattle
ocd-division/country:us/state:wa/place:tacoma,Tacoma
ocd-division/country:us/state:wa/place:olympia,Olympia
"""

LOCAL_TX_CSV = b"""id,name
ocd-division/country:us/state:tx/place:austin,Austin
ocd-division/country:us/state:tx/place:houston,Houston
"""


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_stage1_pipeline(tmp_path, respx_mock):
    """Full pipeline: download → load → match → lookup table."""
    db_path = str(tmp_path / "test.duckdb")
    csv_path = str(tmp_path / "lookup.csv")

    from src.init_migration.download_manager import DownloadManager
    from src.init_migration.ocdid_matcher import OCDidMatcher

    dm = DownloadManager(states=["wa", "tx"], db_path=db_path)

    # Mock HTTP responses
    respx_mock.get(dm.master_url()).mock(
        return_value=httpx.Response(200, content=MASTER_CSV)
    )
    for url in dm.local_urls():
        if "state-wa" in url:
            respx_mock.get(url).mock(
                return_value=httpx.Response(200, content=LOCAL_WA_CSV)
            )
        elif "state-tx" in url:
            respx_mock.get(url).mock(
                return_value=httpx.Response(200, content=LOCAL_TX_CSV)
            )

    # Phase 1: Download and load
    stats = await dm.run_downloads(force=True, show_progress=False)
    assert stats["master_rows"] == 4
    assert stats["local_rows"] == 5  # 3 WA + 2 TX

    # Phase 2: Match
    matcher = OCDidMatcher(
        db_path=db_path, states=["wa", "tx"], csv_backup_path=csv_path
    )
    results = matcher.run_matching()

    # Verify matches (seattle, tacoma, austin, houston)
    assert len(results.matched) == 4

    # Verify local orphan (olympia — in local but not master)
    assert len(results.local_orphans) == 1
    assert results.local_orphans[0]["id"] == "ocd-division/country:us/state:wa/place:olympia"

    # Verify lookup table in DuckDB
    conn = duckdb.connect(db_path)
    lookup_count = conn.execute("SELECT COUNT(*) FROM ocdid_uuid_lookup").fetchone()[0]
    conn.close()
    assert lookup_count == 4

    # Verify CSV backup
    assert Path(csv_path).exists()

    # Verify determinism — re-run should produce same UUIDs
    matcher2 = OCDidMatcher(
        db_path=db_path, states=["wa", "tx"], csv_backup_path=csv_path
    )
    results2 = matcher2.run_matching()
    uuids1 = sorted(str(r.uuid) for r in results.matched)
    uuids2 = sorted(str(r.uuid) for r in results2.matched)
    assert uuids1 == uuids2
```

**Step 2: Run integration test**

Run: `uv run pytest tests/src/init_migration/test_stage1_integration.py -v`
Expected: All pass.

**Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass.

**Step 4: Run linter**

Run: `uv run ruff check .`
Expected: No errors.

**Step 5: Commit**

```bash
git add tests/src/init_migration/test_stage1_integration.py
git commit -m "test: add Stage 1 end-to-end integration test"
```

---

## Task 10: Final cleanup and CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md`
- Remove: `src/init_migration/downloads/` (if exists, leftover from old main.py)
- Verify: `.gitignore` entries for `logs/`

**Step 1: Clean up leftover files**

```bash
rm -rf src/init_migration/downloads/
rm -f src/init_migration/downloader.log
rm -f data.duckdb  # old DuckDB file from previous main.py
```

**Step 2: Update CLAUDE.md**

Update the Architecture section to reflect the new Stage 1 pipeline structure.
Update the Commands section if entry point usage changed.

**Step 3: Run full test suite one final time**

Run: `uv run pytest -v && uv run ruff check .`
Expected: All pass, no lint errors.

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: final Stage 1 cleanup — remove leftover files, update CLAUDE.md"
```
