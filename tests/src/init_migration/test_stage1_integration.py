"""Integration test for the full Stage 1 pipeline with mocked HTTP."""
import pytest
import duckdb
import httpx
from pathlib import Path

from src.init_migration.download_manager import DownloadManager
from src.init_migration.ocdid_matcher import OCDidMatcher


MASTER_CSV = b"""id,name
ocd-division/country:us/state:wa/place:seattle,Seattle
ocd-division/country:us/state:wa/place:tacoma,Tacoma
ocd-division/country:us/state:tx/place:austin,Austin
ocd-division/country:us/state:tx/place:houston,Houston
"""

LOCAL_WA_CSV = b"""ocd-division/country:us/state:wa/place:seattle,Seattle
ocd-division/country:us/state:wa/place:tacoma,Tacoma
ocd-division/country:us/state:wa/place:olympia,Olympia
"""

LOCAL_TX_CSV = b"""ocd-division/country:us/state:tx/place:austin,Austin
ocd-division/country:us/state:tx/place:houston,Houston
"""


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_stage1_pipeline(tmp_path, respx_mock):
    """Full pipeline: download → load → match → lookup table."""
    db_path = str(tmp_path / "test.duckdb")
    csv_path = str(tmp_path / "lookup.csv")

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
