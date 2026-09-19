"""Tests for the shared government-listing validator: rows, CSV, workbooks."""

import io
import zipfile

import openpyxl
import pytest

from src.sources.government_units import (
    CensusGovernmentRecord,
    CensusRowError,
    GovernmentKind,
    Layout,
    cell_text,
    parse_csv,
    parse_row,
    parse_workbook,
    workbook_bytes,
)
from src.sources.snapshot import Snapshot, SnapshotMetadata
from datetime import datetime, timezone

LAYOUT = Layout(
    sheets={
        "General Purpose": GovernmentKind.GENERAL_PURPOSE,
        "Special District": GovernmentKind.SPECIAL_DISTRICT,
    },
    skipped_sheets=frozenset({"Public Pension Sys"}),
    column_aliases={"ACTIVE": "IS_ACTIVE", "SCHOOL_ENROLLMENT": "ENROLLMENT"},
)

GENERAL_HEADER = [
    "CENSUS_ID_PID6",
    "CENSUS_ID_GIDID",
    "UNIT_NAME",
    "UNIT_TYPE",
    "TITLE",
    "ADDRESS1",
    "ADDRESS2",
    "CITY",
    "STATE",
    "ZIP",
    "ZIP4",
    "WEB_ADDRESS",
    "POPULATION",
    "POPULATION_YEAR",
    "FIPS_STATE",
    "FIPS_COUNTY",
    "FIPS_PLACE",
    "COUNTY_AREA_NAME",
    "IS_ACTIVE",
]
SAUSALITO_ROW = {
    "CENSUS_ID_PID6": "161205",
    "CENSUS_ID_GIDID": "05202100900000",
    "UNIT_NAME": "CITY OF SAUSALITO",
    "UNIT_TYPE": "2 - MUNICIPAL",
    "TITLE": "CITY CLERK",
    "ADDRESS1": "420 LITHO ST",
    "ADDRESS2": None,
    "CITY": "SAUSALITO",
    "STATE": "CA",
    "ZIP": "94965",
    "ZIP4": "2921",
    "WEB_ADDRESS": "http://www.ci.sausalito.ca.us",
    "POPULATION": 7199,
    "POPULATION_YEAR": 2021,
    "FIPS_STATE": "06",
    "FIPS_COUNTY": "041",
    "FIPS_PLACE": "70364",
    "COUNTY_AREA_NAME": "MARIN",
    "IS_ACTIVE": "Y",
}
SPECIAL_HEADER = [
    "CENSUS_ID_PID6",
    "UNIT_NAME",
    "FUNCTION_NAME",
    "STATE",
    "FIPS_STATE",
    "FIPS_COUNTY",
    "COUNTY_AREA_NAME",
    "ACTIVE",
]
MARIN_CITY_ROW = [
    "205945",
    "MARIN CITY COMMUNITY SERVICE DISTRICT",
    "99 - OTHER MULTI-FUNCTION DISTRICTS",
    "CA",
    "06",
    "041",
    "MARIN",
    "Y",
]


def build_workbook(sheets: dict[str, tuple[list[str], list[list]]]) -> bytes:
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for title, (header, rows) in sheets.items():
        sheet = workbook.create_sheet(title)
        sheet.append(header)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class TestCellText:
    @pytest.mark.parametrize(
        "value, expected",
        [
            (None, ""),
            (7199, "7199"),
            (7199.0, "7199"),
            (" 06 ", "06"),
            ("7,075", "7,075"),
        ],
    )
    def test_cell_text(self, value, expected):
        assert cell_text(value) == expected


class TestRowValidation:
    def test_valid_row(self):
        record = parse_row(
            SAUSALITO_ROW, GovernmentKind.GENERAL_PURPOSE, "s", 2, LAYOUT
        )
        assert isinstance(record, CensusGovernmentRecord)
        assert record.census_id == "161205"
        assert record.legacy_id == "05202100900000"
        assert record.population == 7199
        assert record.is_active is True
        assert record.attributes["CITY"] == "SAUSALITO"
        assert record.attributes["ADDRESS2"] == ""
        assert "FIPS_STATE" not in record.attributes

    @pytest.mark.parametrize(
        "column, value, fragment",
        [
            ("CENSUS_ID_PID6", "16120", "CENSUS_ID_PID6"),
            ("CENSUS_ID_PID6", "", "CENSUS_ID_PID6"),
            ("UNIT_NAME", "", "UNIT_NAME is empty"),
            ("STATE", "ca", "STATE"),
            ("FIPS_STATE", "6", "FIPS_STATE"),
            ("FIPS_COUNTY", "41", "FIPS_COUNTY"),
            ("FIPS_PLACE", "7036", "FIPS_PLACE"),
            ("IS_ACTIVE", "yes", "IS_ACTIVE"),
            ("POPULATION", "7.199", "POPULATION"),
            ("POPULATION_YEAR", "twenty", "POPULATION_YEAR"),
        ],
    )
    def test_malformed_values_become_errors(self, column, value, fragment):
        row = dict(SAUSALITO_ROW, **{column: value})
        outcome = parse_row(row, GovernmentKind.GENERAL_PURPOSE, "s", 7, LAYOUT)
        assert isinstance(outcome, CensusRowError)
        assert outcome.line == 7
        assert fragment in outcome.reason

    def test_all_problems_reported_together(self):
        row = dict(SAUSALITO_ROW, FIPS_STATE="6", IS_ACTIVE="")
        outcome = parse_row(row, GovernmentKind.GENERAL_PURPOSE, "s", 3, LAYOUT)
        assert "FIPS_STATE" in outcome.reason and "IS_ACTIVE" in outcome.reason

    def test_inactive_flag(self):
        record = parse_row(
            dict(SAUSALITO_ROW, IS_ACTIVE="N"),
            GovernmentKind.GENERAL_PURPOSE,
            "s",
            2,
            LAYOUT,
        )
        assert record.is_active is False

    def test_thousands_separators_accepted(self):
        record = parse_row(
            dict(SAUSALITO_ROW, POPULATION="1,363,767"),
            GovernmentKind.GENERAL_PURPOSE,
            "s",
            2,
            LAYOUT,
        )
        assert record.population == 1363767

    def test_optional_codes_absent(self):
        record = parse_row(
            dict(SAUSALITO_ROW, FIPS_COUNTY=None, FIPS_PLACE="", WEB_ADDRESS=None),
            GovernmentKind.GENERAL_PURPOSE,
            "s",
            2,
            LAYOUT,
        )
        assert record.fips_county is None
        assert record.fips_place is None
        assert record.web_address is None

    def test_aliased_columns_are_read(self):
        row = dict(zip(SPECIAL_HEADER, MARIN_CITY_ROW))
        record = parse_row(row, GovernmentKind.SPECIAL_DISTRICT, "s", 2, LAYOUT)
        assert record.is_active is True
        assert record.function_name == "99 - OTHER MULTI-FUNCTION DISTRICTS"
        assert "ACTIVE" not in record.attributes

    def test_parent_id_validated(self):
        row = dict(SAUSALITO_ROW, PARENT_CENSUS_ID_PID6="124214", PARENT_UNIT_NAME="X")
        record = parse_row(row, GovernmentKind.DEPENDENT_SCHOOL_SYSTEM, "s", 2, LAYOUT)
        assert (record.parent_census_id, record.parent_name) == ("124214", "X")
        bad = parse_row(
            dict(row, PARENT_CENSUS_ID_PID6="12"),
            GovernmentKind.DEPENDENT_SCHOOL_SYSTEM,
            "s",
            2,
            LAYOUT,
        )
        assert isinstance(bad, CensusRowError)


class TestCsv:
    def test_missing_required_column_is_one_error(self):
        result = parse_csv(
            "UNIT_NAME,STATE\nX,CA\n", GovernmentKind.GENERAL_PURPOSE, "s", LAYOUT
        )
        assert result.records == []
        assert [e.line for e in result.errors] == [1]
        assert "CENSUS_ID_PID6" in result.errors[0].reason
        assert "FIPS_STATE" in result.errors[0].reason

    def test_empty_file(self):
        result = parse_csv("", GovernmentKind.GENERAL_PURPOSE, "s", LAYOUT)
        assert result.errors[0].reason == "empty file"

    def test_blank_lines_skipped_and_line_numbers_kept(self):
        text = (
            ",".join(GENERAL_HEADER)
            + "\n\n"
            + ",".join(str(SAUSALITO_ROW[c] or "") for c in GENERAL_HEADER)
            + "\n"
            + ",".join(
                str(SAUSALITO_ROW[c] or "") if c != "STATE" else "cal"
                for c in GENERAL_HEADER
            )
            + "\n"
        )
        result = parse_csv(text, GovernmentKind.GENERAL_PURPOSE, "s", LAYOUT)
        assert [r.census_id for r in result.records] == ["161205"]
        assert [(e.line, e.census_id) for e in result.errors] == [(4, "161205")]


class TestWorkbook:
    def test_reads_known_sheets_skips_others(self, caplog):
        content = build_workbook(
            {
                "General Purpose": (
                    GENERAL_HEADER,
                    [
                        [SAUSALITO_ROW[c] for c in GENERAL_HEADER],
                        [None] * len(GENERAL_HEADER),
                        ["bad"] + [None] * (len(GENERAL_HEADER) - 1),
                    ],
                ),
                "Special District": (SPECIAL_HEADER, [MARIN_CITY_ROW]),
                "Public Pension Sys": (["CENSUS_ID_PID6"], [["1"]]),
                "Notes": (["anything"], [["ignored"]]),
            }
        )
        with caplog.at_level("INFO"):
            result = parse_workbook(content, LAYOUT)
        ids = {r.census_id: r for r in result.records}
        assert sorted(ids) == ["161205", "205945"]
        assert ids["205945"].kind is GovernmentKind.SPECIAL_DISTRICT
        assert ids["161205"].population == 7199
        assert [(e.sheet, e.line, e.census_id) for e in result.errors] == [
            ("General Purpose", 4, "bad")
        ]
        levels = {r.sheet: r.levelname for r in caplog.records if hasattr(r, "sheet")}
        assert levels == {"Public Pension Sys": "INFO", "Notes": "WARNING"}

    def test_empty_sheet_is_an_error(self):
        content = build_workbook({"General Purpose": ([], [])})
        result = parse_workbook(content, LAYOUT)
        assert result.errors[0].reason == "empty sheet"

    def test_workbook_bytes_unpacks_single_xlsx(self, tmp_path):
        xlsx = build_workbook({"General Purpose": (GENERAL_HEADER, [])})
        archive = tmp_path / "units.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("Govt_Units_Final.xlsx", xlsx)
            zf.writestr("doc.pdf", b"%PDF")
        snapshot = Snapshot(path=archive, metadata=_metadata("units.zip"))
        assert workbook_bytes(snapshot) == xlsx

    def test_workbook_bytes_rejects_zip_without_workbook(self, tmp_path):
        archive = tmp_path / "units.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("readme.txt", b"nothing")
        with pytest.raises(ValueError, match="expected one .xlsx"):
            workbook_bytes(Snapshot(path=archive, metadata=_metadata("units.zip")))

    def test_workbook_bytes_passes_xlsx_through(self, tmp_path):
        xlsx = build_workbook({"General Purpose": (GENERAL_HEADER, [])})
        path = tmp_path / "units.xlsx"
        path.write_bytes(xlsx)
        assert (
            workbook_bytes(Snapshot(path=path, metadata=_metadata("units.xlsx")))
            == xlsx
        )


def _metadata(filename: str) -> SnapshotMetadata:
    return SnapshotMetadata(
        source="x",
        source_name="x",
        dataset="x",
        release="1",
        filename=filename,
        url="https://example.com/" + filename,
        sha256="0" * 64,
        size_bytes=0,
        retrieved_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
    )
