"""Tests for the Census of Governments benchmark adapter: fixtures, spec, fetch."""

import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import openpyxl
import pytest

from src.init_migration.downloader import AsyncDownloader
from src.models.source import SourceType
from src.sources.census_governments import (
    LAYOUT,
    census_of_governments_spec,
    census_of_governments_url,
    fetch_census_of_governments,
    is_census_year,
    parse_sheet_snapshot,
    parse_snapshot,
)
from src.sources.government_units import GovernmentKind
from src.sources.snapshot import SnapshotStore, load_snapshot, source_obj_from_snapshot

FIXTURES = Path("tests/fixtures/census_governments")
GENERAL = FIXTURES / "govt_units_2022_general_purpose.csv"
SPECIAL = FIXTURES / "govt_units_2022_special_district.csv"
SCHOOL = FIXTURES / "govt_units_2022_school_district.csv"
DEPENDENT = FIXTURES / "govt_units_2022_dependent_school_system.csv"
RETRIEVED_AT = datetime(2026, 9, 19, tzinfo=timezone.utc)


def by_id(result):
    return {record.census_id: record for record in result.records}


class TestGeneralPurposeFixture:
    @pytest.fixture
    def result(self):
        return parse_sheet_snapshot(
            load_snapshot(GENERAL), GovernmentKind.GENERAL_PURPOSE
        )

    def test_real_rows_parse_and_malformed_rows_are_errors(self, result):
        assert sorted(by_id(result)) == [
            "100630",
            "124214",
            "161205",
            "176394",
            "176868",
            "184255",
            "191593",
            "209716",
            "209717",
        ]
        assert [(e.line, e.census_id) for e in result.errors] == [
            (11, ""),
            (12, "999999"),
        ]
        assert "CENSUS_ID_PID6 is malformed" in result.errors[0].reason
        assert "FIPS_STATE is malformed: '6'" in result.errors[1].reason
        assert all(e.sheet == GENERAL.name for e in result.errors)

    def test_sausalito_record(self, result):
        sausalito = by_id(result)["161205"]
        assert sausalito.name == "CITY OF SAUSALITO"
        assert sausalito.kind is GovernmentKind.GENERAL_PURPOSE
        assert sausalito.unit_type == "2 - MUNICIPAL"
        assert sausalito.political_code is None
        assert sausalito.state == "CA"
        assert (sausalito.fips_state, sausalito.fips_county, sausalito.fips_place) == (
            "06",
            "041",
            "70364",
        )
        assert sausalito.county_area_name == "MARIN"
        assert sausalito.population == 7199
        assert sausalito.population_year == 2021
        assert sausalito.web_address == "http://www.ci.sausalito.ca.us"
        assert sausalito.is_active is True
        assert sausalito.legacy_id == "05202100900000"
        assert sausalito.parent_census_id is None

    def test_leading_zeros_survive(self, result):
        records = by_id(result)
        assert records["176394"].fips_place == "05000"
        assert records["100630"].fips_place == "99041"
        assert records["124214"].fips_state == "11"
        assert records["124214"].fips_county == "001"

    def test_counties_keep_their_unit_type(self, result):
        records = by_id(result)
        assert records["209716"].unit_type == "1 - COUNTY"
        assert records["184255"].function_name is None
        assert records["184255"].school_level is None


class TestOtherSheets:
    def test_special_district(self):
        result = parse_sheet_snapshot(
            load_snapshot(SPECIAL), GovernmentKind.SPECIAL_DISTRICT
        )
        assert result.errors == []
        marin_city = by_id(result)["205945"]
        assert marin_city.name == "MARIN CITY COMMUNITY SERVICE DISTRICT"
        assert marin_city.kind is GovernmentKind.SPECIAL_DISTRICT
        assert marin_city.function_name == "99 - OTHER MULTI-FUNCTION DISTRICTS"
        assert marin_city.unit_type is None
        assert marin_city.fips_place is None
        assert marin_city.population is None
        assert (marin_city.fips_state, marin_city.fips_county) == ("06", "041")

    def test_school_district(self):
        result = parse_sheet_snapshot(
            load_snapshot(SCHOOL), GovernmentKind.SCHOOL_DISTRICT
        )
        assert result.errors == []
        records = by_id(result)
        assert sorted(records) == ["115874", "183396", "203851", "213227"]
        seattle = records["183396"]
        assert seattle.school_level == "03 - ELEMENTARY AND SECONDARY"
        assert seattle.school_enrollment == 55986
        assert seattle.enrollment_year == 2020
        assert seattle.population is None
        assert records["115874"].school_level == "01 - ELEMENTARY ONLY"

    def test_dependent_school_system(self):
        result = parse_sheet_snapshot(
            load_snapshot(DEPENDENT), GovernmentKind.DEPENDENT_SCHOOL_SYSTEM
        )
        assert result.errors == []
        dcps = by_id(result)["101868"]
        assert dcps.kind is GovernmentKind.DEPENDENT_SCHOOL_SYSTEM
        assert dcps.unit_type == "2 - MUNICIPAL"
        assert dcps.school_level == "03 - ELEMENTARY AND SECONDARY"
        assert dcps.school_enrollment == 50971
        assert dcps.parent_census_id is None


class TestFixtureProvenance:
    @pytest.mark.parametrize("path", [GENERAL, SPECIAL, SCHOOL, DEPENDENT])
    def test_source_obj_from_fixture_snapshot(self, path):
        snapshot = load_snapshot(path)
        source = source_obj_from_snapshot(snapshot.metadata, field=["name"])
        assert source.source_name == "U.S. Census Bureau"
        assert source.source_type == SourceType.SCRAPED
        assert source.release == "2022"
        assert str(source.source_url) == census_of_governments_url(2022)
        assert source.publication_date == datetime(
            2023, 8, 24, 12, 44, 48, tzinfo=timezone.utc
        )
        assert source.retrieval_date == datetime(
            2026, 9, 19, 16, 14, 20, tzinfo=timezone.utc
        )
        assert source.dataset.startswith("Census of Governments: Organization")

    def test_parse_result_carries_metadata(self):
        result = parse_sheet_snapshot(
            load_snapshot(SPECIAL), GovernmentKind.SPECIAL_DISTRICT
        )
        assert result.metadata.release == "2022"


class TestSpec:
    @pytest.mark.parametrize(
        "year, expected",
        [(2017, True), (2022, True), (2027, True), (2024, False), (2026, False)],
    )
    def test_census_years(self, year, expected):
        assert is_census_year(year) is expected

    def test_spec_for_census_year(self):
        spec = census_of_governments_spec(2022)
        assert spec.source == "census_governments"
        assert spec.release == "2022"
        assert spec.filename == "govt_units_2022.ZIP"
        assert (
            spec.url
            == "https://www2.census.gov/programs-surveys/gus/datasets/2022/govt_units_2022.ZIP"
        )
        assert census_of_governments_spec("2027").filename == "govt_units_2027.ZIP"

    def test_non_census_year_rejected(self):
        with pytest.raises(ValueError, match="not a Census of Governments year"):
            census_of_governments_spec(2026)

    def test_layout_has_no_aliases_and_four_sheets(self):
        assert LAYOUT.column_aliases == {}
        assert len(LAYOUT.sheets) == 4
        assert LAYOUT.skipped_sheets == frozenset()


def build_zip(sheet: str, header: list[str], rows: list[list]) -> bytes:
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    ws = workbook.create_sheet(sheet)
    ws.append(header)
    for row in rows:
        ws.append(row)
    xlsx = io.BytesIO()
    workbook.save(xlsx)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Govt_Units_2022_Final.xlsx", xlsx.getvalue())
        zf.writestr("Government_Units_List_Documentation_2022.pdf", b"%PDF-1.4\n")
    return archive.getvalue()


SPECIAL_HEADER = [
    "CENSUS_ID_PID6",
    "CENSUS_ID_GIDID",
    "UNIT_NAME",
    "FUNCTION_NAME",
    "STATE",
    "FIPS_STATE",
    "FIPS_COUNTY",
    "COUNTY_AREA_NAME",
    "IS_ACTIVE",
]
MARIN_CITY_ROW = [
    "205945",
    "05402150200000",
    "MARIN CITY COMMUNITY SERVICE DISTRICT",
    "99 - OTHER MULTI-FUNCTION DISTRICTS",
    "CA",
    "06",
    "041",
    "MARIN",
    "Y",
]


class TestFetch:
    @pytest.mark.asyncio
    async def test_fetch_zip_then_parse_offline(self, respx_mock, tmp_path):
        content = build_zip("Special District", SPECIAL_HEADER, [MARIN_CITY_ROW])
        route = respx_mock.get(census_of_governments_url(2022)).mock(
            return_value=httpx.Response(200, content=content)
        )
        store = SnapshotStore(tmp_path)
        async with AsyncDownloader() as downloader:
            snapshot = await fetch_census_of_governments(
                store, downloader, 2022, retrieved_at=RETRIEVED_AT
            )
            again = await fetch_census_of_governments(
                store, downloader, 2022, retrieved_at=RETRIEVED_AT
            )

        assert route.call_count == 1
        assert again == snapshot
        assert (
            snapshot.path
            == tmp_path / "census_governments" / "2022" / "govt_units_2022.ZIP"
        )
        result = parse_snapshot(snapshot)
        assert [r.census_id for r in result.records] == ["205945"]
        assert result.records[0].legacy_id == "05402150200000"
        assert result.metadata.release == "2022"
        assert result.metadata.retrieved_at == RETRIEVED_AT
        source = source_obj_from_snapshot(result.metadata, field=["name"])
        assert str(source.source_url) == census_of_governments_url(2022)
