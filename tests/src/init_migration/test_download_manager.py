"""Tests for DownloadManager — URL building and DuckDB loading."""

import duckdb
import httpx
import pytest

from src.init_migration.download_manager import DownloadManager

# --- URL Building ---


def test_build_master_url():
    """Master URL should point to country-us.csv on GitHub raw."""
    dm = DownloadManager(states=["wa"])
    url = dm.master_url()
    assert "country-us.csv" in url
    assert "raw.githubusercontent.com" in url or "api.github.com" in url


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


# --- Async Download Orchestration ---


@pytest.mark.asyncio
async def test_run_downloads_fetches_and_loads(tmp_path, respx_mock):
    """run_downloads() should fetch only the master CSV and load it into DuckDB."""
    db_path = str(tmp_path / "test.duckdb")
    dm = DownloadManager(states=["wa"], db_path=db_path)

    master_csv = b"id,name\nocd-division/country:us/state:wa/place:seattle,Seattle\n"

    respx_mock.get(dm.master_url()).mock(
        return_value=httpx.Response(200, content=master_csv)
    )

    stats = await dm.run_downloads(force=True, show_progress=False)

    assert stats["master_rows"] == 1
    assert stats["files_downloaded"] == 1
    assert "local_rows" not in stats
