"""Integration tests for stage 1 pipeline."""

import argparse
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from src.init_migration.download_manager import DownloadManager
from src.init_migration.main import run_pipeline
from src.init_migration.ocdid_matcher import OCDidMatcher
from src.init_migration.pipeline_models import (
    COUNTIES_SHEET_CSV_URL,
    DIVISIONS_SHEET_CSV_URL,
    STATES_SHEET_CSV_URL,
)

# TODO: This test leaves/replaces the following artifact:
# data/ocdid_pipeline.duckdb. Attempted to mock but still generates.


# Master dataset: 4 records selected for tx/dc/hi (2 TX, 1 DC, 1 HI),
# 1 HI precinct skipped, and 1 WA record outside the requested states
MASTER_CSV = b"""id,name
ocd-division/country:us/state:tx/place:austin,Austin
ocd-division/country:us/state:tx/place:houston,Houston
ocd-division/country:us/district:dc,District of Columbia
ocd-division/country:us/state:hi/place:honolulu,Honolulu
ocd-division/country:us/state:hi/county:hawaii/precinct:1,Hawaii Precinct 1
ocd-division/country:us/state:wa/place:seattle,Seattle
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
async def test_run_pipeline_multi_state_selects_from_master(
    mock_store_generation_tracking,
    tmp_path,
    monkeypatch,
    respx_mock,
    clean_duckdb,
):
    """End-to-end test"""

    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)

    test_db_path = data_dir / "ocdid_pipeline.duckdb"

    class TestDownloadManager(DownloadManager):
        def __init__(self, *args, **kwargs):
            kwargs["db_path"] = str(test_db_path)
            super().__init__(*args, **kwargs)

    class TestOCDidMatcher(OCDidMatcher):
        def __init__(self, *args, **kwargs):
            kwargs["db_path"] = str(test_db_path)
            super().__init__(*args, **kwargs)

    with (
        patch("src.init_migration.main.DEFAULT_DB_PATH", str(test_db_path)),
        patch("src.init_migration.download_manager.DEFAULT_DB_PATH", str(test_db_path)),
        patch("src.init_migration.ocdid_matcher.DEFAULT_DB_PATH", str(test_db_path)),
        patch("src.init_migration.main.DownloadManager", TestDownloadManager),
        patch("src.init_migration.main.OCDidMatcher", TestOCDidMatcher),
    ):
        states = ["tx", "dc", "hi"]

        dm = TestDownloadManager(states=states)

        respx_mock.get(dm.master_url()).mock(
            return_value=httpx.Response(200, content=MASTER_CSV)
        )

        # Phase 3 caches all three validation tabs; the states and counties tabs
        # return header-only CSVs so the concat still lines up.
        respx_mock.get(DIVISIONS_SHEET_CSV_URL).mock(
            return_value=httpx.Response(200, content=VALIDATION_CSV)
        )
        validation_header = VALIDATION_CSV.split(b"\n")[0] + b"\n"
        for sheet_url in (STATES_SHEET_CSV_URL, COUNTIES_SHEET_CSV_URL):
            respx_mock.get(sheet_url).mock(
                return_value=httpx.Response(200, content=validation_header)
            )

        args = argparse.Namespace(
            state="tx,dc,hi",
            force=True,
            log_dir=str(tmp_path / "logs"),
        )

        results = await run_pipeline(args)

    selected_ids = {r.ocdid.raw_ocdid for r in results.matched}
    assert selected_ids == {
        "ocd-division/country:us/state:tx/place:austin",
        "ocd-division/country:us/state:tx/place:houston",
        "ocd-division/country:us/district:dc",
        "ocd-division/country:us/state:hi/place:honolulu",
    }
    assert results.skipped_precincts == 1

    mock_store_generation_tracking.assert_called_once()
