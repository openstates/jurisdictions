"""Tests for DownloadManager — URL building and DuckDB loading."""
import pytest
import duckdb
import httpx

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
    """Loading a local CSV should insert rows into local_ocdids table with state column.

    Note: Real local CSVs from the OCD repo have no header row.
    """
    db_path = str(tmp_path / "test.duckdb")
    dm = DownloadManager(states=["wa"], db_path=db_path)

    csv_bytes = b"ocd-division/country:us/state:wa/place:seattle,Seattle\n"
    dm.load_local_csv(csv_bytes, state="wa")

    conn = duckdb.connect(db_path)
    rows = conn.execute("SELECT * FROM local_ocdids WHERE state = 'wa'").fetchall()
    conn.close()
    assert len(rows) == 1


def test_load_multiple_states_to_duckdb(tmp_path):
    """Loading CSVs for multiple states should combine into one local_ocdids table.

    Note: Real local CSVs from the OCD repo have no header row.
    """
    db_path = str(tmp_path / "test.duckdb")
    dm = DownloadManager(states=["wa", "tx"], db_path=db_path)

    wa_csv = b"ocd-division/country:us/state:wa/place:seattle,Seattle\n"
    tx_csv = b"ocd-division/country:us/state:tx/place:austin,Austin\n"
    dm.load_local_csv(wa_csv, state="wa")
    dm.load_local_csv(tx_csv, state="tx")

    conn = duckdb.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM local_ocdids").fetchone()[0]
    conn.close()
    assert count == 2


# --- Async Download Orchestration ---

@pytest.mark.asyncio
async def test_run_downloads_fetches_and_loads(tmp_path, respx_mock):
    """run_downloads() should fetch all URLs and load into DuckDB."""
    db_path = str(tmp_path / "test.duckdb")
    dm = DownloadManager(states=["wa"], db_path=db_path)

    master_csv = b"id,name\nocd-division/country:us/state:wa/place:seattle,Seattle\n"
    local_csv = b"ocd-division/country:us/state:wa/place:seattle,Seattle\n"

    respx_mock.get(dm.master_url()).mock(
        return_value=httpx.Response(200, content=master_csv)
    )
    respx_mock.get(dm.local_urls()[0]).mock(
        return_value=httpx.Response(200, content=local_csv)
    )

    stats = await dm.run_downloads(force=True, show_progress=False)

    assert stats["master_rows"] > 0
    assert stats["local_rows"] > 0
    assert stats["files_downloaded"] >= 1


@pytest.mark.asyncio
async def test_run_downloads_handles_missing_local(tmp_path, respx_mock):
    """run_downloads() should continue if a state's local CSV returns 404."""
    db_path = str(tmp_path / "test.duckdb")
    dm = DownloadManager(states=["wa", "zz"], db_path=db_path)

    master_csv = b"id,name\nocd-division/country:us/state:wa/place:seattle,Seattle\n"
    local_wa = b"ocd-division/country:us/state:wa/place:seattle,Seattle\n"

    respx_mock.get(dm.master_url()).mock(
        return_value=httpx.Response(200, content=master_csv)
    )
    respx_mock.get(dm.local_urls()[0]).mock(
        return_value=httpx.Response(200, content=local_wa)
    )
    respx_mock.get(dm.local_urls()[1]).mock(
        return_value=httpx.Response(404)
    )

    stats = await dm.run_downloads(force=True, show_progress=False)

    assert stats["files_failed"] == 1
    assert stats["local_rows"] > 0
