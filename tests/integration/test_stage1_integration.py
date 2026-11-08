"""Integration test for the full Stage 1 pipeline with mocked HTTP."""

from pathlib import Path

import duckdb
import httpx
import pytest

from src.init_migration.download_manager import DownloadManager
from src.init_migration.ocdid_matcher import OCDidMatcher

MASTER_CSV = b"""id,name
ocd-division/country:us/state:wa/place:seattle,Seattle
ocd-division/country:us/state:wa/place:tacoma,Tacoma
ocd-division/country:us/state:wa/county:king/precinct:1,King Precinct 1
ocd-division/country:us/state:tx/place:austin,Austin
ocd-division/country:us/state:tx/place:houston,Houston
ocd-division/country:us/state:or/place:portland,Portland
"""


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_stage1_pipeline(tmp_path, respx_mock):
    """Full pipeline: download → load → select → lookup table."""
    db_path = str(tmp_path / "test.duckdb")
    csv_path = str(tmp_path / "lookup.csv")

    dm = DownloadManager(states=["wa", "tx"], db_path=db_path)

    # Mock HTTP responses
    respx_mock.get(dm.master_url()).mock(
        return_value=httpx.Response(200, content=MASTER_CSV)
    )

    # Phase 1: Download and load
    stats = await dm.run_downloads(force=True, show_progress=False)
    assert stats["master_rows"] == 6

    # Phase 2: Select
    matcher = OCDidMatcher(
        db_path=db_path, states=["wa", "tx"], csv_backup_path=csv_path
    )
    results = matcher.run_matching()

    # Verify selection (seattle, tacoma, austin, houston); precinct and OR skipped
    assert len(results.matched) == 4
    assert results.skipped_precincts == 1

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
