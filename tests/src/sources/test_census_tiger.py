"""Tests for the TIGER adapter: layer config, URL building, attribute parsing, fetch."""

import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from src.init_migration.downloader import AsyncDownloader
from src.sources.census_tiger import (
    DEFAULT_CONFIG_PATH,
    TigerRecord,
    TigerRowError,
    fetch_tiger_line,
    geometry_url,
    load_tiger_config,
    parse_csv,
    parse_csv_snapshot,
    parse_row,
    parse_snapshot,
    parse_tiger_config,
    place_layer_key,
    series_as_of,
    tiger_line_spec,
    tiger_line_url,
    tigerweb_query_url,
    tigerweb_service_url,
)
from src.sources.snapshot import SnapshotStore, load_snapshot, source_obj_from_snapshot

FIXTURES = Path("tests/fixtures/tiger")
RETRIEVED_AT = datetime(2026, 9, 19, tzinfo=timezone.utc)
SAUSALITO_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "Places_CouSub_ConCity_SubMCD/MapServer/4/query?where=GEOID%3D'0670364'"
    "&outFields=*&outSR=4326&f=geojson"
)
MARIN_CITY_URL = SAUSALITO_URL.replace("/MapServer/4/", "/MapServer/5/").replace(
    "0670364", "0645820"
)


@pytest.fixture(scope="module")
def config():
    return load_tiger_config()


class TestConfig:
    def test_default_config_path_is_the_repo_file(self):
        assert DEFAULT_CONFIG_PATH == Path("config/tiger_layers.yaml").resolve()

    def test_five_geographies(self, config):
        assert config.geographies() == [
            "county",
            "county_subdivision",
            "place",
            "school_district",
            "state",
        ]

    @pytest.mark.parametrize(
        "key, geography, service, layer, length",
        [
            ("state", "state", "State_County", 0, 2),
            ("county", "county", "State_County", 1, 5),
            ("place", "place", "Places_CouSub_ConCity_SubMCD", 4, 7),
            ("census_designated_place", "place", "Places_CouSub_ConCity_SubMCD", 5, 7),
            (
                "county_subdivision",
                "county_subdivision",
                "Places_CouSub_ConCity_SubMCD",
                1,
                10,
            ),
            ("school_district_unified", "school_district", "School", 0, 7),
            ("school_district_secondary", "school_district", "School", 1, 7),
            ("school_district_elementary", "school_district", "School", 2, 7),
        ],
    )
    def test_layer_resolution(self, config, key, geography, service, layer, length):
        resolved = config.layer(key)
        assert resolved.geography == geography
        assert resolved.tigerweb.service == service
        assert resolved.tigerweb.layer == layer
        assert resolved.geoid_length == length
        assert resolved in config.layers_for(geography)

    def test_unknown_layer(self, config):
        with pytest.raises(KeyError, match="unknown TIGER layer"):
            config.layer("tract")

    def test_bad_scope_rejected(self):
        text = (
            "tiger_line_base_url: x\ntigerweb_base_url: y\nlayers:\n  a:\n"
            "    geography: state\n    geoid_length: 2\n"
            "    tiger_line: {directory: S, filename: f, scope: global}\n"
            "    tigerweb: {service: S, layer: 0}\n"
        )
        with pytest.raises(ValueError, match="scope"):
            parse_tiger_config(text)


class TestTigerLineNaming:
    def test_national_layer(self, config):
        assert (
            tiger_line_url(config, "state", 2025)
            == "https://www2.census.gov/geo/tiger/TIGER2025/STATE/tl_2025_us_state.zip"
        )
        assert (
            tiger_line_url(config, "county", "2025")
            == "https://www2.census.gov/geo/tiger/TIGER2025/COUNTY/tl_2025_us_county.zip"
        )

    @pytest.mark.parametrize(
        "key, expected",
        [
            ("place", "PLACE/tl_2025_06_place.zip"),
            ("census_designated_place", "PLACE/tl_2025_06_place.zip"),
            ("county_subdivision", "COUSUB/tl_2025_06_cousub.zip"),
            ("school_district_unified", "UNSD/tl_2025_06_unsd.zip"),
            ("school_district_secondary", "SCSD/tl_2025_06_scsd.zip"),
            ("school_district_elementary", "ELSD/tl_2025_06_elsd.zip"),
        ],
    )
    def test_state_layers(self, config, key, expected):
        assert tiger_line_url(config, key, 2025, "06").endswith(
            "/TIGER2025/" + expected
        )

    def test_state_layer_requires_state(self, config):
        with pytest.raises(ValueError, match="per state"):
            tiger_line_url(config, "place", 2025)
        with pytest.raises(ValueError, match="two digits"):
            tiger_line_url(config, "place", 2025, "6")

    def test_national_layer_rejects_state(self, config):
        with pytest.raises(ValueError, match="national"):
            tiger_line_url(config, "state", 2025, "06")

    def test_spec(self, config):
        spec = tiger_line_spec(config, "place", 2025, "53")
        assert spec.source == "tiger"
        assert spec.release == "2025"
        assert spec.filename == "tl_2025_53_place.zip"
        assert spec.dataset == "TIGER/Line Shapefiles, PLACE"
        assert spec.url.endswith("/PLACE/tl_2025_53_place.zip")

    def test_series_as_of(self):
        assert series_as_of(2025) == datetime(2025, 1, 1, tzinfo=timezone.utc)
        assert series_as_of("2023") == datetime(2023, 1, 1, tzinfo=timezone.utc)


class TestTigerWebUrls:
    def test_sausalito_matches_golden_geometry(self, config):
        assert tigerweb_query_url(config, "place", "0670364") == SAUSALITO_URL

    def test_marin_city_cdp_matches_golden_geometry(self, config):
        assert (
            tigerweb_query_url(config, "census_designated_place", "0645820")
            == MARIN_CITY_URL
        )

    @pytest.mark.parametrize(
        "key, geoid, fragment",
        [
            ("state", "06", "State_County/MapServer/0/query?where=GEOID%3D'06'"),
            ("county", "53033", "State_County/MapServer/1/query?where=GEOID%3D'53033'"),
            (
                "place",
                "4805000",
                "Places_CouSub_ConCity_SubMCD/MapServer/4/query?where=GEOID%3D'4805000'",
            ),
            (
                "county_subdivision",
                "4845390165",
                "Places_CouSub_ConCity_SubMCD/MapServer/1/query?where=GEOID%3D'4845390165'",
            ),
            (
                "school_district_unified",
                "5307710",
                "School/MapServer/0/query?where=GEOID%3D'5307710'",
            ),
            (
                "school_district_elementary",
                "0636000",
                "School/MapServer/2/query?where=GEOID%3D'0636000'",
            ),
            (
                "school_district_secondary",
                "0638790",
                "School/MapServer/1/query?where=GEOID%3D'0638790'",
            ),
        ],
    )
    def test_golden_geoids(self, config, key, geoid, fragment):
        url = tigerweb_query_url(config, key, geoid)
        assert fragment in url
        assert url.endswith("&outFields=*&outSR=4326&f=geojson")

    @pytest.mark.parametrize(
        "key, geoid", [("place", "670364"), ("state", "060"), ("county", "0604A")]
    )
    def test_wrong_length_or_non_digit_rejected(self, config, key, geoid):
        with pytest.raises(ValueError, match="digits"):
            tigerweb_query_url(config, key, geoid)

    def test_service_url_matches_golden_source(self, config):
        assert (
            tigerweb_service_url(config, "place")
            == "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer"
        )


class TestFixtures:
    @pytest.mark.parametrize(
        "file, key, geoids",
        [
            ("tl_2025_us_state.csv", "state", ["06", "11", "48", "53"]),
            (
                "tl_2025_us_county.csv",
                "county",
                ["06041", "11001", "48453", "53033", "53053"],
            ),
            (
                "tl_2025_place.csv",
                "place",
                ["0645820", "0670364", "1150000", "4805000", "5363000", "5370000"],
            ),
            (
                "tl_2025_cousub.csv",
                "county_subdivision",
                ["0604193140", "1100150000", "4845390165", "5303392928", "5305393376"],
            ),
            (
                "tl_2025_unsd.csv",
                "school_district_unified",
                ["1100030", "4808940", "5307710", "5308700"],
            ),
            ("tl_2025_elsd.csv", "school_district_elementary", ["0636000"]),
            ("tl_2025_scsd.csv", "school_district_secondary", ["0638790"]),
        ],
    )
    def test_each_layer_parses_offline(self, config, file, key, geoids):
        result = parse_csv_snapshot(load_snapshot(FIXTURES / file), config, key)
        assert result.errors == []
        assert sorted(r.geoid for r in result.records) == geoids
        assert all(r.layer == key for r in result.records)
        assert result.metadata.release == "2025"

    def test_place_records(self, config):
        result = parse_csv_snapshot(
            load_snapshot(FIXTURES / "tl_2025_place.csv"), config, "place"
        )
        records = {r.geoid: r for r in result.records}
        sausalito = records["0670364"]
        assert (sausalito.name, sausalito.namelsad) == ("Sausalito", "Sausalito city")
        assert (sausalito.statefp, sausalito.placefp) == ("06", "70364")
        assert (sausalito.lsad, sausalito.classfp, sausalito.funcstat) == (
            "25",
            "C1",
            "A",
        )
        assert sausalito.geoidfq == "1600000US0670364"
        assert sausalito.attributes["PLACENS"] == "02411834"
        assert geometry_url(config, sausalito) == SAUSALITO_URL
        marin_city = records["0645820"]
        assert place_layer_key(marin_city) == "census_designated_place"
        assert geometry_url(config, marin_city) == MARIN_CITY_URL
        assert records["4805000"].placefp == "05000"

    def test_school_records_carry_lea(self, config):
        result = parse_csv_snapshot(
            load_snapshot(FIXTURES / "tl_2025_unsd.csv"),
            config,
            "school_district_unified",
        )
        seattle = {r.geoid: r for r in result.records}["5307710"]
        assert seattle.lea == "07710"
        assert seattle.name == "Seattle Public Schools"
        assert seattle.attributes["LOGRADE"] == "PK"
        assert geometry_url(config, seattle).endswith(
            "School/MapServer/0/query?where=GEOID%3D'5307710'&outFields=*&outSR=4326&f=geojson"
        )

    def test_county_subdivision_records(self, config):
        result = parse_csv_snapshot(
            load_snapshot(FIXTURES / "tl_2025_cousub.csv"), config, "county_subdivision"
        )
        austin = {r.geoid: r for r in result.records}["4845390165"]
        assert (austin.countyfp, austin.cousubfp, austin.namelsad) == (
            "453",
            "90165",
            "Austin CCD",
        )

    def test_fixture_provenance(self, config):
        snapshot = load_snapshot(FIXTURES / "tl_2025_place.csv")
        source = source_obj_from_snapshot(snapshot.metadata, field=["geometries"])
        assert source.source_name == "Census TIGER/Line"
        assert source.release == "2025"
        assert (
            str(source.source_url)
            == "https://www2.census.gov/geo/tiger/TIGER2025/PLACE/"
        )
        assert source.publication_date == datetime(
            2025, 9, 22, 23, 49, 10, tzinfo=timezone.utc
        )
        assert source.retrieval_date == datetime(
            2026, 9, 19, 17, 12, 9, tzinfo=timezone.utc
        )


class TestRowValidation:
    ROW = {
        "STATEFP": "06",
        "PLACEFP": "70364",
        "GEOID": "0670364",
        "NAME": "Sausalito",
        "NAMELSAD": "Sausalito city",
        "LSAD": "25",
        "CLASSFP": "C1",
        "FUNCSTAT": "A",
    }

    def test_valid(self, config):
        record = parse_row(self.ROW, config.layer("place"), "f", 2)
        assert isinstance(record, TigerRecord)
        assert record.countyfp is None and record.lea is None

    @pytest.mark.parametrize(
        "column, value, fragment",
        [
            ("GEOID", "670364", "GEOID is not 7 digits"),
            ("GEOID", "0670364A", "GEOID is not 7 digits"),
            ("GEOID", "4870364", "does not start with STATEFP"),
            ("NAME", "", "NAME is empty"),
            ("STATEFP", "6", "STATEFP"),
            ("PLACEFP", "7036", "PLACEFP"),
        ],
    )
    def test_malformed(self, config, column, value, fragment):
        outcome = parse_row(
            dict(self.ROW, **{column: value}), config.layer("place"), "f", 9
        )
        assert isinstance(outcome, TigerRowError)
        assert outcome.line == 9
        assert fragment in outcome.reason

    def test_csv_errors_do_not_abort(self, config):
        text = "STATEFP,GEOID,NAME\n06,0670364,Sausalito\n06,bad,Nope\n06,0645820,Marin City\n"
        result = parse_csv(text, config.layer("place"), "f")
        assert [r.geoid for r in result.records] == ["0670364", "0645820"]
        assert [(e.line, e.geoid) for e in result.errors] == [(3, "bad")]

    def test_empty_csv(self, config):
        assert (
            parse_csv("", config.layer("place"), "f").errors[0].reason == "empty file"
        )

    def test_place_layer_key_for_non_place(self, config):
        record = parse_row(
            {"STATEFP": "06", "GEOID": "06", "NAME": "California"},
            config.layer("state"),
            "f",
            2,
        )
        assert place_layer_key(record) == "state"


class TestFetch:
    @pytest.mark.asyncio
    async def test_fetch_zip_then_parse_attribute_table(
        self, respx_mock, tmp_path, config, build_dbf
    ):
        dbf = build_dbf(
            [
                ("STATEFP", 2),
                ("PLACEFP", 5),
                ("GEOID", 7),
                ("NAME", 20),
                ("LSAD", 2),
                ("CLASSFP", 2),
            ],
            [
                ["06", "70364", "0670364", "Sausalito", "25", "C1"],
                ["06", "45820", "0645820", "Marin City", "57", "U1"],
                ["06", "", "bad", "Broken", "25", "C1"],
            ],
        )
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("tl_2025_06_place.dbf", dbf)
            zf.writestr("tl_2025_06_place.shp", b"\x00" * 100)
            zf.writestr("tl_2025_06_place.prj", b"GEOGCS")
        route = respx_mock.get(tiger_line_url(config, "place", 2025, "06")).mock(
            return_value=httpx.Response(200, content=archive.getvalue())
        )
        store = SnapshotStore(tmp_path)
        async with AsyncDownloader() as downloader:
            snapshot = await fetch_tiger_line(
                store,
                downloader,
                config,
                "place",
                2025,
                state_fips="06",
                retrieved_at=RETRIEVED_AT,
            )
            again = await fetch_tiger_line(
                store,
                downloader,
                config,
                "place",
                2025,
                state_fips="06",
                retrieved_at=RETRIEVED_AT,
            )

        assert route.call_count == 1
        assert again == snapshot
        assert snapshot.path == tmp_path / "tiger" / "2025" / "tl_2025_06_place.zip"
        result = parse_snapshot(snapshot, config, "place")
        assert [r.geoid for r in result.records] == ["0670364", "0645820"]
        assert [(e.line, e.geoid) for e in result.errors] == [(3, "bad")]
        assert geometry_url(config, result.records[1]) == MARIN_CITY_URL
        assert result.metadata.release == "2025"

    def test_zip_without_dbf_rejected(self, tmp_path, config):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("readme.txt", b"no table")
        store = SnapshotStore(tmp_path)
        snapshot = store.put(
            tiger_line_spec(config, "state", 2025),
            archive.getvalue(),
            retrieved_at=RETRIEVED_AT,
        )
        with pytest.raises(ValueError, match="expected one .dbf"):
            parse_snapshot(snapshot, config, "state")
