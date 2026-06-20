"""Integration tests for stage 1 pipeline."""
from types import SimpleNamespace
from unittest.mock import patch

import argparse
import httpx
import pytest
from src.init_migration.main import run_pipeline
from src.init_migration.download_manager import DownloadManager
from src.init_migration.pipeline_models import DIVISIONS_SHEET_CSV_URL

# Master dataset with 5 entries: 4 matches (2 in TX, 1 in DC, 1 in HI), 1 master orphan (HI), and no local orphans
MASTER_CSV = b"""id,name
ocd-division/country:us/state:tx/place:austin,Austin
ocd-division/country:us/state:tx/place:houston,Houston
ocd-division/country:us/state:dc/place:washington,Washington
ocd-division/country:us/state:hi/place:honolulu,Honolulu
ocd-division/country:us/state:hi/place:hilo,Hilo
"""

# Texas State dataset with two matches and one local orphan (dallas) that should be detected, but no master orphans
LOCAL_TX_CSV = b"""ocd-division/country:us/state:tx/place:austin,Austin
ocd-division/country:us/state:tx/place:houston,Houston
ocd-division/country:us/state:tx/place:dallas,Dallas
"""

# DC State dataset with one match and no orphans
LOCAL_DC_CSV = b"""ocd-division/country:us/state:dc/place:washington,Washington
"""

# Hawaii State dataset with one match, one local orphan, and one master orphan
LOCAL_HI_CSV = b"""ocd-division/country:us/state:hi/place:honolulu,Honolulu
ocd-division/country:us/state:hi/place:maui,Maui
"""

VALIDATION_CSV = b"""DIVISION_ID,NAMELSAD,LSAD
ocd-division/country:us/state:tx/place:austin,Austin city,25
ocd-division/country:us/state:tx/place:houston,Houston city,25
ocd-division/country:us/state:dc/place:washington,Washington city,25
ocd-division/country:us/state:hi/place:honolulu,Honolulu city,25
"""


class FakeGeneratePipeline:
    def __init__(self, req):
        self.req = req

    async def run(self):
        return SimpleNamespace(
            data=SimpleNamespace(
                ocdid=SimpleNamespace(raw_ocdid=self.req.data.ocdid.raw_ocdid)
            ),
            status=SimpleNamespace(
                status=SimpleNamespace(value="success"),
                error=None,
            ),
            division_path=None,
            jurisdiction_path=None,
        )


@pytest.mark.integration
@pytest.mark.asyncio
@patch("src.init_migration.main.store_generation_tracking")
@patch("src.init_migration.main.GeneratePipeline", FakeGeneratePipeline)
async def test_run_pipeline_multi_state_with_orphans_and_failures(
    mock_store_generation_tracking,
    tmp_path,
    monkeypatch,
    respx_mock,
    clean_duckdb,
):
    """End-to-end test"""

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)

    test_db_path = tmp_path / "data" / "ocdid_pipeline.duckdb"

    with (
        patch("src.init_migration.download_manager.DEFAULT_DB_PATH", str(test_db_path)),
        patch("src.init_migration.ocdid_matcher.DEFAULT_DB_PATH", str(test_db_path)),
    ):
        states = ["tx", "dc", "hi"]

        dm = DownloadManager(states=states, db_path=str(test_db_path))

        respx_mock.get(dm.master_url()).mock(
            return_value=httpx.Response(200, content=MASTER_CSV)
        )

        # Local state datasets
        for url in dm.local_urls():
            if "state-tx" in url:
                respx_mock.get(url).mock(
                    return_value=httpx.Response(200, content=LOCAL_TX_CSV)
                )

            elif "state-dc" in url:
                respx_mock.get(url).mock(
                    return_value=httpx.Response(200, content=LOCAL_DC_CSV)
                )

            elif "state-hi" in url:
                respx_mock.get(url).mock(
                    return_value=httpx.Response(200, content=LOCAL_HI_CSV)
                )

            elif "state-zz" in url:
                respx_mock.get(url).mock(return_value=httpx.Response(404))

        respx_mock.get(DIVISIONS_SHEET_CSV_URL).mock(
            return_value=httpx.Response(200, content=VALIDATION_CSV)
        )

        args = argparse.Namespace(
            state="tx,dc,hi",
            force=True,
            log_dir=str(tmp_path / "logs"),
        )

        results = await run_pipeline(args)

    assert len(results.matched) == 4
    assert len(results.local_orphans) == 2
    assert len(results.master_orphans) == 1

    orphan_ids = {row["id"] for row in results.local_orphans}

    assert "ocd-division/country:us/state:tx/place:dallas" in orphan_ids
    assert "ocd-division/country:us/state:hi/place:maui" in orphan_ids

    assert results.master_orphans[0]["id"] == "ocd-division/country:us/state:hi/place:hilo"

    mock_store_generation_tracking.assert_called_once()