"""Tests for the annual Government Units listing adapter and pension export."""

import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import openpyxl
import pytest

from src.init_migration.downloader import AsyncDownloader
from src.models.source import SourceType
from src.sources.census_gus import (
    EXPORT_COLUMNS,
    LAYOUT,
    export_pension_systems,
    fetch_government_units,
    government_units_spec,
    government_units_url,
    governments,
    is_annual_year,
    parse_sheet_snapshot,
    parse_snapshot,
    pension_systems,
    records_to_csv,
)
from src.sources.government_units import GovernmentKind, ParseResult
from src.sources.snapshot import (
    SnapshotStore,
    load_snapshot,
    read_metadata,
    source_obj_from_snapshot,
)

FIXTURES = Path("tests/fixtures/census_gus")
GENERAL = FIXTURES / "gov_units_2026_general_purpose.csv"
SPECIAL = FIXTURES / "gov_units_2026_special_district.csv"
SCHOOL = FIXTURES / "gov_units_2026_school_district.csv"
DEPENDENT = FIXTURES / "gov_units_2026_dependent_school_system.csv"
PENSION = FIXTURES / "gov_units_2026_public_pension_system.csv"
RETRIEVED_AT = datetime(2026, 9, 23, tzinfo=timezone.utc)


def by_id(result):
    return {record.census_id: record for record in result.records}


class TestSpec:
    @pytest.mark.parametrize(
        "year, expected",
        [
            (2024, True),
            (2025, True),
            (2026, True),
            (2028, True),
            (2027, False),
            (2022, False),
            (2023, False),
        ],
    )
    def test_annual_years(self, year, expected):
        assert is_annual_year(year) is expected

    def test_spec(self):
        spec = government_units_spec(2026)
        assert spec.source == "census_gus"
        assert spec.release == "2026"
        assert spec.filename == "gov_units_2026.zip"
        assert (
            spec.url
            == "https://www2.census.gov/programs-surveys/gus/datasets/2026/gov_units_2026.zip"
        )
        assert spec.dataset.startswith("Governments Master Address File")

    @pytest.mark.parametrize("year", [2022, 2027, 2023])
    def test_non_annual_years_rejected(self, year):
        with pytest.raises(ValueError, match="no annual"):
            government_units_spec(year)

    def test_layout_aliases_and_pension_sheet(self):
        assert LAYOUT.column_aliases == {
            "ACTIVE": "IS_ACTIVE",
            "POPULATION_SOURCE_YEAR": "POPULATION_YEAR",
            "SCHOOL_ENROLLMENT": "ENROLLMENT",
            "ACTIVITY_NAME": "FUNCTION_NAME",
        }
        assert (
            LAYOUT.sheets["Public Pension Sys"] is GovernmentKind.PUBLIC_PENSION_SYSTEM
        )
        assert LAYOUT.skipped_sheets == frozenset()


class TestFixtures:
    def test_general_purpose(self):
        result = parse_sheet_snapshot(
            load_snapshot(GENERAL), GovernmentKind.GENERAL_PURPOSE
        )
        assert result.errors == []
        records = by_id(result)
        assert sorted(records) == [
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
        sausalito = records["161205"]
        assert sausalito.name == "CITY OF SAUSALITO"
        assert sausalito.unit_type == "2 - MUNICIPAL"
        assert sausalito.political_code == "CITY"
        assert sausalito.population == 7075
        assert sausalito.population_year == 2024
        assert sausalito.is_active is True
        assert sausalito.legacy_id is None
        assert (sausalito.fips_state, sausalito.fips_county, sausalito.fips_place) == (
            "06",
            "041",
            "70364",
        )
        assert records["191593"].population == 1363767
        assert records["176394"].fips_place == "05000"

    def test_special_district_has_unit_type_and_function(self):
        result = parse_sheet_snapshot(
            load_snapshot(SPECIAL), GovernmentKind.SPECIAL_DISTRICT
        )
        assert result.errors == []
        marin_city = by_id(result)["205945"]
        assert marin_city.unit_type == "4 - SPECIAL DISTRICT"
        assert marin_city.function_name == "99 - OTHER MULTI-FUNCTION DISTRICTS"

    def test_school_district_enrollment_alias(self):
        result = parse_sheet_snapshot(
            load_snapshot(SCHOOL), GovernmentKind.SCHOOL_DISTRICT
        )
        assert result.errors == []
        seattle = by_id(result)["183396"]
        assert seattle.school_enrollment == 50770
        assert seattle.enrollment_year == 2024
        assert seattle.unit_type == "5 - SCHOOL DISTRICT OR EDUCATIONAL SERVICE AGENCY"
        assert "SCHOOL_ENROLLMENT" not in seattle.attributes

    def test_dependent_school_system_parent(self):
        result = parse_sheet_snapshot(
            load_snapshot(DEPENDENT), GovernmentKind.DEPENDENT_SCHOOL_SYSTEM
        )
        assert result.errors == []
        dcps = by_id(result)["101868"]
        assert (dcps.parent_census_id, dcps.parent_name) == ("124214", "WASHINGTON DC")
        assert dcps.school_enrollment == 50839

    def test_pension_systems(self):
        result = parse_sheet_snapshot(
            load_snapshot(PENSION), GovernmentKind.PUBLIC_PENSION_SYSTEM
        )
        assert result.errors == []
        assert len(result.records) == 10
        marin = by_id(result)["119303"]
        assert marin.kind is GovernmentKind.PUBLIC_PENSION_SYSTEM
        assert marin.function_name == "X1 - PUBLIC EMPLOYEES RETIREMENT SYSTEMS"
        assert marin.unit_type == "1 - COUNTY"
        assert (marin.parent_census_id, marin.parent_name) == ("100630", "MARIN")
        assert "ACTIVITY_NAME" not in marin.attributes
        parents = {r.parent_census_id for r in result.records}
        assert parents == {"100630", "124214", "176394", "184255", "176868"}

    @pytest.mark.parametrize("path", [GENERAL, SPECIAL, SCHOOL, DEPENDENT, PENSION])
    def test_provenance(self, path):
        source = source_obj_from_snapshot(load_snapshot(path).metadata, field=["name"])
        assert source.source_name == "U.S. Census Bureau"
        assert source.source_type == SourceType.SCRAPED
        assert source.release == "2026"
        assert str(source.source_url) == government_units_url(2026)
        assert source.publication_date == datetime(
            2026, 9, 15, 14, 8, 55, tzinfo=timezone.utc
        )
        assert source.retrieval_date == datetime(
            2026, 9, 23, 17, 17, 58, tzinfo=timezone.utc
        )
        assert source.dataset.startswith("Governments Master Address File")


class TestPensionExport:
    def _result(self) -> ParseResult:
        result = parse_sheet_snapshot(
            load_snapshot(PENSION), GovernmentKind.PUBLIC_PENSION_SYSTEM
        )
        general = parse_sheet_snapshot(
            load_snapshot(GENERAL), GovernmentKind.GENERAL_PURPOSE
        )
        result.extend(general)
        return result

    def test_governments_excludes_pensions(self):
        result = self._result()
        assert len(result.records) == 19
        assert len(governments(result)) == 9
        assert len(pension_systems(result)) == 10
        assert all(
            r.kind is not GovernmentKind.PUBLIC_PENSION_SYSTEM
            for r in governments(result)
        )

    def test_export_writes_csv_and_sidecar(self, tmp_path):
        result = self._result()
        snapshot = export_pension_systems(result, cache_root=tmp_path)

        assert (
            snapshot.path
            == tmp_path / "census_gus" / "2026" / "public_pension_systems.csv"
        )
        rows = list(csv.DictReader(io.StringIO(snapshot.path.read_text())))
        assert [r["census_id"] for r in rows] == sorted(r["census_id"] for r in rows)
        assert len(rows) == 10
        assert set(rows[0]) == set(EXPORT_COLUMNS)
        marin = next(r for r in rows if r["census_id"] == "119303")
        assert marin["kind"] == "public_pension_system"
        assert marin["is_active"] == "Y"
        assert marin["parent_census_id"] == "100630"
        assert marin["fips_county"] == "041"
        assert marin["population"] == ""

        metadata = read_metadata(snapshot.path)
        assert metadata == snapshot.metadata
        assert metadata.source == "census_gus"
        assert metadata.release == "2026"
        assert metadata.url == government_units_url(2026)
        assert metadata.retrieved_at == result.metadata.retrieved_at
        assert metadata.publication_date == result.metadata.publication_date
        assert "Public Pension Sys" in metadata.dataset
        assert metadata.size_bytes == snapshot.path.stat().st_size
        sidecar = json.loads(
            (
                tmp_path
                / "census_gus"
                / "2026"
                / "public_pension_systems.csv.meta.json"
            ).read_text()
        )
        assert sidecar["filename"] == "public_pension_systems.csv"

    def test_export_is_deterministic(self, tmp_path):
        first = export_pension_systems(self._result(), cache_root=tmp_path / "a")
        second = export_pension_systems(self._result(), cache_root=tmp_path / "b")
        assert first.path.read_bytes() == second.path.read_bytes()
        assert first.metadata.sha256 == second.metadata.sha256

    def test_export_requires_metadata(self):
        with pytest.raises(ValueError, match="metadata"):
            export_pension_systems(ParseResult(), cache_root=Path("/nonexistent"))

    def test_records_to_csv_header_only_when_empty(self):
        text = records_to_csv([])
        assert text.splitlines() == [",".join(EXPORT_COLUMNS)]
        assert "attributes" not in EXPORT_COLUMNS


def build_zip(sheets: dict[str, tuple[list[str], list[list]]]) -> bytes:
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for title, (header, rows) in sheets.items():
        ws = workbook.create_sheet(title)
        ws.append(header)
        for row in rows:
            ws.append(row)
    xlsx = io.BytesIO()
    workbook.save(xlsx)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Govt_Units_2026_Final.xlsx", xlsx.getvalue())
        zf.writestr("Government_Units_List_Documentation_2026.pdf", b"%PDF-1.4\n")
    return archive.getvalue()


GENERAL_HEADER = [
    "CENSUS_ID_PID6",
    "UNIT_NAME",
    "UNIT_TYPE",
    "STATE",
    "WEB_ADDRESS",
    "POLITICAL_CODE_DESCRIPTION",
    "POPULATION",
    "POPULATION_SOURCE_YEAR",
    "FIPS_STATE",
    "FIPS_COUNTY",
    "FIPS_PLACE",
    "COUNTY_AREA_NAME",
    "ACTIVE",
]
SAUSALITO = [
    "161205",
    "CITY OF SAUSALITO",
    "2 - MUNICIPAL",
    "CA",
    "http://www.ci.sausalito.ca.us",
    "CITY",
    "7,075",
    "2024",
    "06",
    "041",
    "70364",
    "MARIN",
    "Y",
]
PENSION_HEADER = [
    "CENSUS_ID_PID6",
    "UNIT_NAME",
    "UNIT_TYPE",
    "ACTIVITY_NAME",
    "STATE",
    "FIPS_STATE",
    "FIPS_COUNTY",
    "COUNTY_AREA_NAME",
    "ACTIVE",
    "PARENT_CENSUS_ID_PID6",
    "PARENT_UNIT_NAME",
]
MARIN_PENSION = [
    "119303",
    "MARIN CO EMPLOYEES RETIREMENT FUND",
    "1 - COUNTY",
    "X1 - PUBLIC EMPLOYEES RETIREMENT SYSTEMS",
    "CA",
    "06",
    "041",
    "MARIN",
    "Y",
    "100630",
    "MARIN",
]


class TestFetch:
    @pytest.mark.asyncio
    async def test_fetch_zip_parse_and_export(self, respx_mock, tmp_path):
        content = build_zip(
            {
                "General Purpose": (
                    GENERAL_HEADER,
                    [SAUSALITO, ["bad"] + [None] * (len(GENERAL_HEADER) - 1)],
                ),
                "Public Pension Sys": (PENSION_HEADER, [MARIN_PENSION]),
            }
        )
        route = respx_mock.get(government_units_url(2026)).mock(
            return_value=httpx.Response(200, content=content)
        )
        store = SnapshotStore(tmp_path / "raw")
        async with AsyncDownloader() as downloader:
            snapshot = await fetch_government_units(
                store, downloader, 2026, retrieved_at=RETRIEVED_AT
            )
            again = await fetch_government_units(
                store, downloader, 2026, retrieved_at=RETRIEVED_AT
            )

        assert route.call_count == 1
        assert again == snapshot
        assert (
            snapshot.path
            == tmp_path / "raw" / "census_gus" / "2026" / "gov_units_2026.zip"
        )

        result = parse_snapshot(snapshot)
        assert [r.census_id for r in governments(result)] == ["161205"]
        assert [r.census_id for r in pension_systems(result)] == ["119303"]
        assert governments(result)[0].population == 7075
        assert [(e.sheet, e.line, e.census_id) for e in result.errors] == [
            ("General Purpose", 3, "bad")
        ]
        assert result.metadata.release == "2026"

        exported = export_pension_systems(result, cache_root=tmp_path / "cache")
        assert (
            exported.path
            == tmp_path / "cache" / "census_gus" / "2026" / "public_pension_systems.csv"
        )
        assert exported.metadata.retrieved_at == RETRIEVED_AT
        assert exported.metadata.url == government_units_url(2026)
        assert load_snapshot(exported.path) == exported
