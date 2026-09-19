"""Tests for the OCD master adapter: offline index, exact lookup, suggestions."""

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from src.init_migration.download_manager import DownloadManager
from src.init_migration.downloader import AsyncDownloader
from src.models.source import SourceType
from src.sources.ocd_master import (
    OCDMasterIndex,
    OCDRowError,
    fetch_local,
    fetch_master,
    local_spec,
    local_url,
    master_spec,
    master_url,
    parse_local_csv,
    parse_master_csv,
)
from src.sources.snapshot import SnapshotStore, load_snapshot

FIXTURE = Path("tests/fixtures/ocd_master/country-us.csv")
RETRIEVED_AT = datetime(2026, 9, 18, tzinfo=timezone.utc)

SAUSALITO = "ocd-division/country:us/state:ca/place:sausalito"
MARIN_CITY = "ocd-division/country:us/state:ca/county:marin/cdp:marin_city"
ANC_1A_1 = "ocd-division/country:us/district:dc/anc:1a/council_district:1"
AUSTIN_CD8 = "ocd-division/country:us/state:tx/place:austin/council_district:8"
SEATTLE_CD1 = "ocd-division/country:us/state:wa/place:seattle/council_district:1"
TACOMA = "ocd-division/country:us/state:wa/place:tacoma"
GOLDEN = [SAUSALITO, MARIN_CITY, ANC_1A_1, AUSTIN_CD8, SEATTLE_CD1, TACOMA]


@pytest.fixture
def fixture_index() -> OCDMasterIndex:
    return OCDMasterIndex.from_snapshots(load_snapshot(FIXTURE))


class TestFixtureIndex:
    def test_loads_all_six_golden_ids(self, fixture_index):
        assert len(fixture_index) == 6
        assert sorted(entry.ocdid for entry in fixture_index) == sorted(GOLDEN)
        assert fixture_index.errors == []

    @pytest.mark.parametrize("ocdid", GOLDEN)
    def test_exact_positive(self, fixture_index, ocdid):
        assert fixture_index.contains(ocdid)
        assert ocdid in fixture_index
        assert fixture_index.get(ocdid).ocdid == ocdid

    @pytest.mark.parametrize(
        "ocdid",
        [
            "ocd-division/country:us/state:wa/place:seattle",
            "ocd-division/country:us/state:ca/place:Sausalito",
            SAUSALITO + "/",
            " " + SAUSALITO,
            "ocd-division/country:us/state:tx/place:austin",
            "ocd-division/country:us/state:ca",
            "",
            "not-an-ocdid",
        ],
    )
    def test_exact_negative(self, fixture_index, ocdid):
        assert not fixture_index.contains(ocdid)
        assert fixture_index.get(ocdid) is None

    def test_entry_carries_name_parsed_and_attributes(self, fixture_index):
        entry = fixture_index.get(SAUSALITO)
        assert entry.name == "Sausalito city"
        assert entry.parsed.state == "ca"
        assert entry.parsed.place == "sausalito"
        assert "census_geoid" in entry.attributes
        assert entry.attributes["census_geoid"] == ""
        assert "id" not in entry.attributes and "name" not in entry.attributes

    def test_district_id_is_indexed(self, fixture_index):
        entry = fixture_index.get(ANC_1A_1)
        assert entry.parsed.state is None
        assert entry.parsed.model_extra["district"] == "dc"

    def test_place_names_by_state(self, fixture_index):
        assert fixture_index.place_names_by_state() == {
            "ca": {"sausalito city"},
            "tx": {"austin tx city council district 8 (effective jan 2015)"},
            "wa": {"seattle wa city council district 1", "tacoma city"},
        }

    def test_source_obj_from_fixture_metadata(self, fixture_index):
        source = fixture_index.source_obj(["ocdid"])
        assert source.field == ["ocdid"]
        assert source.source_name == "Open Civic Data"
        assert source.source_type == SourceType.SCRAPED
        assert source.dataset == "ocd-division-ids/identifiers/country-us.csv"
        assert source.release == "master"
        assert source.publication_date is None
        assert source.retrieval_date == datetime(
            2026, 9, 15, 23, 23, 56, tzinfo=timezone.utc
        )
        assert str(source.source_url) == master_url()


class TestSuggestions:
    def test_near_miss_is_not_member_but_is_suggested(self, fixture_index):
        query = "ocd-division/country:us/state:wa/place:tacomma"
        assert not fixture_index.contains(query)
        suggestions = fixture_index.suggest(query)
        assert suggestions
        assert suggestions[0].ocdid == TACOMA
        assert suggestions[0].name == "Tacoma city"
        assert 0 < suggestions[0].score < 100
        assert fixture_index.contains(suggestions[0].ocdid)
        assert fixture_index.get(query) is None

    def test_suggestions_stay_within_query_state(self, fixture_index):
        query = "ocd-division/country:us/state:tx/place:tacoma"
        assert all(
            s.ocdid.startswith("ocd-division/country:us/state:tx/")
            for s in fixture_index.suggest(query, min_score=0)
        )

    def test_exact_member_scores_100(self, fixture_index):
        suggestions = fixture_index.suggest(TACOMA)
        assert suggestions[0].ocdid == TACOMA
        assert suggestions[0].score == 100.0

    def test_unparseable_query_scores_everything(self, fixture_index):
        suggestions = fixture_index.suggest("tacoma", min_score=0, limit=10)
        assert len(suggestions) == 6

    def test_limit_and_threshold(self, fixture_index):
        assert (
            fixture_index.suggest(
                "ocd-division/country:us/state:wa/place:x", min_score=99
            )
            == []
        )
        assert len(fixture_index.suggest(TACOMA, min_score=0, limit=1)) == 1

    def test_ordering_is_deterministic(self, fixture_index):
        first = fixture_index.suggest(
            "ocd-division/country:us/state:wa/place:s", min_score=0
        )
        second = fixture_index.suggest(
            "ocd-division/country:us/state:wa/place:s", min_score=0
        )
        assert first == second
        assert [s.score for s in first] == sorted(
            (s.score for s in first), reverse=True
        )


class TestParsing:
    def test_master_row_errors_are_structured(self):
        text = (
            "id,name,sameAs\n"
            f"{TACOMA},Tacoma city,\n"
            "not-an-ocdid,Broken,\n"
            ",Blank id,\n"
            "ocd-division/,Too short,\n"
        )
        entries, errors = parse_master_csv(text, "country-us.csv")
        assert [e.ocdid for e in entries] == [TACOMA]
        assert [(e.line, e.raw_id) for e in errors] == [
            (3, "not-an-ocdid"),
            (4, ""),
            (5, "ocd-division/"),
        ]
        assert all(
            isinstance(e, OCDRowError) and e.file == "country-us.csv" for e in errors
        )
        assert "ocd-division/" in errors[0].reason

    def test_master_without_id_column(self):
        entries, errors = parse_master_csv("name,sameAs\nTacoma,\n", "x.csv")
        assert entries == []
        assert errors[0].reason == "missing id column"

    def test_duplicate_master_ids_keep_first(self):
        text = f"id,name\n{TACOMA},First\n{TACOMA},Second\n"
        entries, _ = parse_master_csv(text)
        index = OCDMasterIndex(entries, metadata=load_snapshot(FIXTURE).metadata)
        assert len(index) == 1
        assert index.get(TACOMA).name == "First"

    def test_local_csv_is_headerless(self):
        text = f"{TACOMA},Tacoma\n\n{SEATTLE_CD1}\nbad,Nope\n"
        rows, errors = parse_local_csv(text, "state-wa-local_gov.csv")
        assert rows == [(TACOMA, "Tacoma"), (SEATTLE_CD1, "")]
        assert [(e.line, e.raw_id) for e in errors] == [(4, "bad")]


class TestLocalFiles:
    def test_local_orphans_are_ids_missing_from_master(self, tmp_path):
        store = SnapshotStore(tmp_path)
        master = load_snapshot(FIXTURE)
        olympia = "ocd-division/country:us/state:wa/place:olympia"
        local = store.put(
            local_spec("WA"),
            f"{TACOMA},Tacoma\n{olympia},Olympia\n".encode(),
            retrieved_at=RETRIEVED_AT,
        )
        index = OCDMasterIndex.from_snapshots(master, {"wa": local})

        assert index.local_states() == ["wa"]
        assert index.local_ids("wa") == frozenset({TACOMA, olympia})
        assert index.local_orphans("wa") == [olympia]
        assert index.local_orphans("tx") == []
        assert not index.contains(olympia)
        assert len(index) == 6

    def test_local_row_errors_merge_into_index_errors(self, tmp_path):
        store = SnapshotStore(tmp_path)
        local = store.put(
            local_spec("wa"), b"garbage,Nope\n", retrieved_at=RETRIEVED_AT
        )
        index = OCDMasterIndex.from_snapshots(load_snapshot(FIXTURE), {"wa": local})
        assert [e.file for e in index.errors] == ["state-wa-local_gov.csv"]


class TestSpecsAndFetch:
    def test_urls_match_download_manager(self):
        manager = DownloadManager(states=["wa", "TX"])
        assert master_url() == manager.master_url()
        assert [local_url("wa"), local_url("TX")] == manager.local_urls()

    def test_specs(self):
        spec = master_spec()
        assert (spec.source, spec.release, spec.filename) == (
            "ocd_master",
            "master",
            "country-us.csv",
        )
        pinned = master_spec("abc1234")
        assert pinned.release == "abc1234" and pinned.url == master_url()
        local = local_spec("WA", "abc1234")
        assert local.filename == "state-wa-local_gov.csv"
        assert local.dataset.endswith("state-wa-local_gov.csv")
        assert local.release == "abc1234"

    @pytest.mark.asyncio
    async def test_fetch_master_and_local_then_index(self, respx_mock, tmp_path):
        master_route = respx_mock.get(master_url()).mock(
            return_value=httpx.Response(200, content=FIXTURE.read_bytes())
        )
        local_route = respx_mock.get(local_url("wa")).mock(
            return_value=httpx.Response(200, content=f"{TACOMA},Tacoma\n".encode())
        )
        store = SnapshotStore(tmp_path)
        async with AsyncDownloader() as downloader:
            master = await fetch_master(store, downloader, retrieved_at=RETRIEVED_AT)
            local = await fetch_local(
                store, downloader, "wa", retrieved_at=RETRIEVED_AT
            )
            again = await fetch_master(store, downloader, retrieved_at=RETRIEVED_AT)

        assert master_route.call_count == 1 and local_route.call_count == 1
        assert again == master
        assert master.path == tmp_path / "ocd_master" / "master" / "country-us.csv"
        assert (
            local.path == tmp_path / "ocd_master" / "master" / "state-wa-local_gov.csv"
        )
        index = OCDMasterIndex.from_snapshots(master, {"wa": local})
        assert index.contains(TACOMA)
        assert index.local_orphans("wa") == []
        assert index.metadata.retrieved_at == RETRIEVED_AT
