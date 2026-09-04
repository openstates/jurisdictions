"""Tests for the offline-first Census Government Units source adapter."""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree

import pytest

from src.init_migration.census_government_adapter import (
    CENSUS_GOVERNMENT_RELEASES,
    CensusGovernmentAdapter,
    CensusGovernmentCacheMissError,
    CensusGovernmentParseError,
    CensusGovernmentReleaseSpec,
    CensusGovernmentSheet,
    CensusGovernmentSnapshotIntegrityError,
    CensusGovernmentSourceError,
    CensusGovernmentSourceRecord,
)

FIXTURE_PATH = (
    Path(__file__).parents[2]
    / "fixtures"
    / "census_governments"
    / "mini_release_2025.json"
)
SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
PACKAGE_REL_NS = (
    "http://schemas.openxmlformats.org/package/2006/relationships"
)


class FakeFetcher:
    """Small ``AsyncDownloader`` stand-in for offline tests."""

    def __init__(self, response: bytes | None) -> None:
        self.response = response
        self.calls: list[tuple[str, bool]] = []

    async def fetch_bytes(
        self, url: str, *, force: bool = False
    ) -> bytes | None:
        self.calls.append((url, force))
        return self.response


def fixture_rows() -> dict[str, dict[str, str | None]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def fixture_spec(*, rows_per_sheet: int = 1) -> CensusGovernmentReleaseSpec:
    production = CENSUS_GOVERNMENT_RELEASES["2025"]
    return replace(
        production,
        source_url="https://example.test/gov_units_2025.zip",
        sheets=tuple(
            replace(sheet, expected_data_rows=rows_per_sheet)
            for sheet in production.sheets
        ),
    )


def make_adapter(tmp_path: Path) -> CensusGovernmentAdapter:
    return CensusGovernmentAdapter(
        tmp_path,
        release_spec=fixture_spec(),
    )


def build_archive(
    rows: dict[str, dict[str, str | None]] | None = None,
    *,
    spec: CensusGovernmentReleaseSpec | None = None,
    formula_cell: tuple[str, str] | None = None,
    skip_sheet: str | None = None,
    extra_outer_member: tuple[str, bytes] | None = None,
    documentation: bytes = b"%PDF-1.4\n%%EOF\n",
) -> bytes:
    spec = spec or fixture_spec()
    rows = rows or fixture_rows()
    workbook = build_workbook(
        rows,
        spec=spec,
        formula_cell=formula_cell,
        skip_sheet=skip_sheet,
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(spec.workbook_member, workbook)
        archive.writestr(spec.documentation_member, documentation)
        if extra_outer_member is not None:
            archive.writestr(*extra_outer_member)
    return output.getvalue()


def build_workbook(
    rows: dict[str, dict[str, str | None]],
    *,
    spec: CensusGovernmentReleaseSpec,
    formula_cell: tuple[str, str] | None = None,
    skip_sheet: str | None = None,
) -> bytes:
    shared_values: list[str] = []
    shared_index: dict[str, int] = {}

    def shared(value: str) -> int:
        if value not in shared_index:
            shared_index[value] = len(shared_values)
            shared_values.append(value)
        return shared_index[value]

    workbook_root = ElementTree.Element(
        f"{{{SPREADSHEET_NS}}}workbook",
        {"xmlns:r": OFFICE_REL_NS},
    )
    sheets_root = ElementTree.SubElement(
        workbook_root,
        f"{{{SPREADSHEET_NS}}}sheets",
    )
    rels_root = ElementTree.Element(f"{{{PACKAGE_REL_NS}}}Relationships")
    sheet_payloads: list[tuple[str, bytes]] = []

    emitted_sheet_id = 0
    for sheet_spec in spec.sheets:
        if sheet_spec.sheet.value == skip_sheet:
            continue
        emitted_sheet_id += 1
        relationship_id = f"rId{emitted_sheet_id}"
        ElementTree.SubElement(
            sheets_root,
            f"{{{SPREADSHEET_NS}}}sheet",
            {
                "name": sheet_spec.sheet.value,
                "sheetId": str(emitted_sheet_id),
                f"{{{OFFICE_REL_NS}}}id": relationship_id,
            },
        )
        target = f"worksheets/sheet{emitted_sheet_id}.xml"
        ElementTree.SubElement(
            rels_root,
            f"{{{PACKAGE_REL_NS}}}Relationship",
            {
                "Id": relationship_id,
                "Type": (
                    "http://schemas.openxmlformats.org/officeDocument/"
                    "2006/relationships/worksheet"
                ),
                "Target": target,
            },
        )
        row = rows[sheet_spec.sheet.value]
        sheet_payloads.append(
            (
                f"xl/{target}",
                build_sheet_xml(
                    sheet_spec.headers,
                    row,
                    shared=shared,
                    formula_cell=formula_cell,
                ),
            )
        )

    strings_root = ElementTree.Element(
        f"{{{SPREADSHEET_NS}}}sst",
        {
            "count": str(len(shared_values)),
            "uniqueCount": str(len(shared_values)),
        },
    )
    for value in shared_values:
        item = ElementTree.SubElement(strings_root, f"{{{SPREADSHEET_NS}}}si")
        text = ElementTree.SubElement(item, f"{{{SPREADSHEET_NS}}}t")
        text.text = value

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr(
            "xl/workbook.xml",
            ElementTree.tostring(workbook_root, encoding="utf-8", xml_declaration=True),
        )
        workbook.writestr(
            "xl/_rels/workbook.xml.rels",
            ElementTree.tostring(rels_root, encoding="utf-8", xml_declaration=True),
        )
        workbook.writestr(
            "xl/sharedStrings.xml",
            ElementTree.tostring(strings_root, encoding="utf-8", xml_declaration=True),
        )
        for path, payload in sheet_payloads:
            workbook.writestr(path, payload)
    return output.getvalue()


def build_sheet_xml(
    headers: tuple[str, ...],
    row: dict[str, str | None],
    *,
    shared: Callable[[str], int],
    formula_cell: tuple[str, str] | None,
) -> bytes:
    root = ElementTree.Element(f"{{{SPREADSHEET_NS}}}worksheet")
    dimension = f"A1:{excel_column_name(len(headers))}2"
    ElementTree.SubElement(
        root,
        f"{{{SPREADSHEET_NS}}}dimension",
        {"ref": dimension},
    )
    sheet_data = ElementTree.SubElement(root, f"{{{SPREADSHEET_NS}}}sheetData")
    for row_number, values in ((1, dict(zip(headers, headers))), (2, row)):
        row_node = ElementTree.SubElement(
            sheet_data,
            f"{{{SPREADSHEET_NS}}}row",
            {"r": str(row_number)},
        )
        for index, header in enumerate(headers, start=1):
            value = values.get(header)
            if value is None:
                continue
            reference = f"{excel_column_name(index)}{row_number}"
            cell = ElementTree.SubElement(
                row_node,
                f"{{{SPREADSHEET_NS}}}c",
                {"r": reference, "t": "s"},
            )
            if formula_cell == (header, str(row_number)):
                formula = ElementTree.SubElement(cell, f"{{{SPREADSHEET_NS}}}f")
                formula.text = "1+1"
            value_node = ElementTree.SubElement(cell, f"{{{SPREADSHEET_NS}}}v")
            value_node.text = str(shared(str(value)))
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def excel_column_name(column_number: int) -> str:
    characters: list[str] = []
    value = column_number
    while value:
        value, remainder = divmod(value - 1, 26)
        characters.append(chr(65 + remainder))
    return "".join(reversed(characters))


def test_production_contract_pins_five_tabs_and_97241_rows() -> None:
    spec = CENSUS_GOVERNMENT_RELEASES["2025"]

    assert [sheet.sheet.value for sheet in spec.sheets] == [
        "General Purpose",
        "Special District",
        "School District",
        "DEP School Dist",
        "Public Pension Sys",
    ]
    assert sum(sheet.expected_data_rows for sheet in spec.sheets) == 97_241
    assert spec.source_url.endswith("/2025/gov_units_2025.zip")
    assert spec.source_snapshot_date == "2025-08-28"


@pytest.mark.asyncio
async def test_fetch_uses_pinned_url_and_force_flag(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    payload = build_archive()
    fetcher = FakeFetcher(payload)

    result = await adapter.fetch(fetcher, force=True)

    assert result == payload
    assert fetcher.calls == [(adapter.release_spec.source_url, True)]


def test_verify_accepts_fixture_release_and_inventory(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)

    verified = adapter.verify(build_archive())

    assert verified.inventory.total_data_rows == 5
    assert dict(verified.inventory.sheet_data_rows) == {
        sheet.sheet: 1 for sheet in adapter.release_spec.sheets
    }
    assert len(verified.archive_sha256) == 64
    assert len(verified.workbook_sha256) == 64
    assert len(verified.documentation_sha256) == 64


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "archive is empty"),
        (b"not a zip", "not a valid ZIP archive"),
    ],
)
def test_verify_rejects_empty_or_invalid_archive(
    tmp_path: Path,
    payload: bytes,
    message: str,
) -> None:
    adapter = make_adapter(tmp_path)

    with pytest.raises(CensusGovernmentSourceError, match=message):
        adapter.verify(payload)


def test_verify_rejects_archive_above_size_limit(tmp_path: Path) -> None:
    adapter = CensusGovernmentAdapter(
        tmp_path,
        release_spec=fixture_spec(),
        max_archive_bytes=10,
    )

    with pytest.raises(CensusGovernmentSourceError, match="size limit"):
        adapter.verify(build_archive())


def test_verify_rejects_unexpected_outer_member(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    payload = build_archive(extra_outer_member=("unexpected.txt", b"x"))

    with pytest.raises(CensusGovernmentSourceError, match="members do not match"):
        adapter.verify(payload)


def test_verify_rejects_non_pdf_documentation(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)

    with pytest.raises(CensusGovernmentSourceError, match="not a PDF"):
        adapter.verify(build_archive(documentation=b"not pdf"))


def test_verify_rejects_missing_workbook_sheet(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    payload = build_archive(skip_sheet="Public Pension Sys")

    with pytest.raises(CensusGovernmentSourceError, match="sheet order/names"):
        adapter.verify(payload)


def test_verify_rejects_wrong_header(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    rows = fixture_rows()
    rows["General Purpose"]["CENSUS_ID_PID6"] = "010001"
    bad_spec = fixture_spec()
    bad_headers = ("WRONG_HEADER",) + bad_spec.sheets[0].headers[1:]
    bad_spec = replace(
        bad_spec,
        sheets=(replace(bad_spec.sheets[0], headers=bad_headers),)
        + bad_spec.sheets[1:],
    )
    payload = build_archive(rows, spec=bad_spec)

    with pytest.raises(CensusGovernmentSourceError, match="headers do not match"):
        adapter.verify(payload)


def test_verify_rejects_wrong_release_row_count(tmp_path: Path) -> None:
    adapter = CensusGovernmentAdapter(
        tmp_path,
        release_spec=fixture_spec(rows_per_sheet=2),
    )

    with pytest.raises(CensusGovernmentSourceError, match="dimension"):
        adapter.verify(build_archive(spec=fixture_spec()))


def test_verify_rejects_formula_cell(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    payload = build_archive(formula_cell=("UNIT_NAME", "2"))

    with pytest.raises(CensusGovernmentSourceError, match="not formulas"):
        adapter.verify(payload)


def test_cache_round_trip_preserves_provenance(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    verified = adapter.verify(build_archive())
    retrieved_at = datetime(2026, 8, 11, 18, 30, tzinfo=timezone.utc)

    cached = adapter.cache(verified, retrieved_at=retrieved_at)
    loaded = adapter.load_cached_metadata()

    assert loaded.archive_sha256 == cached.archive_sha256
    assert loaded.workbook_sha256 == cached.workbook_sha256
    assert loaded.documentation_sha256 == cached.documentation_sha256
    assert loaded.retrieved_at == "2026-08-11T18:30:00Z"
    assert loaded.source_snapshot_date == "2025-08-28"
    assert loaded.archive_path.read_bytes() == verified.payload
    assert sum(loaded.sheet_data_rows.values()) == 5


@pytest.mark.asyncio
async def test_refresh_reuses_integrity_checked_cache_after_304(
    tmp_path: Path,
) -> None:
    adapter = make_adapter(tmp_path)
    initial = adapter.cache(adapter.verify(build_archive()))
    fetcher = FakeFetcher(None)

    refreshed = await adapter.refresh(fetcher)

    assert refreshed.archive_sha256 == initial.archive_sha256
    assert fetcher.calls == [(adapter.release_spec.source_url, False)]


@pytest.mark.asyncio
async def test_refresh_304_without_cache_fails_closed(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)

    with pytest.raises(CensusGovernmentCacheMissError):
        await adapter.refresh(FakeFetcher(None))


def test_cached_archive_checksum_mismatch_fails_closed(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    metadata = adapter.cache(adapter.verify(build_archive()))
    metadata.archive_path.write_bytes(metadata.archive_path.read_bytes() + b"\n")

    with pytest.raises(
        CensusGovernmentSnapshotIntegrityError,
        match="Checksum mismatch",
    ):
        adapter.load_cached_metadata()


def test_cache_requires_timezone_aware_retrieval_time(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    verified = adapter.verify(build_archive())

    with pytest.raises(ValueError, match="timezone-aware"):
        adapter.cache(verified, retrieved_at=datetime(2026, 8, 11))


def test_parse_emits_all_five_raw_rows_with_provenance(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    adapter.cache(adapter.verify(build_archive()))

    result = adapter.parse()

    assert result.input_count == 5
    assert len(result.records) == 5
    assert result.errors == ()
    assert {record.source_sheet for record in result.records} == set(
        CensusGovernmentSheet
    )
    general = result.records[0]
    assert general.census_id_pid6 == "010001"
    assert general.source_snapshot_date == "2025-08-28"
    assert general.source_row_number == 2
    assert general.raw_fields["ZIP"] == "01234"
    assert general.raw_fields["ZIP4"] == "0001"
    assert general.source_archive_sha256 == result.metadata.archive_sha256


def test_parse_preserves_imperfect_contact_fields(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    rows = fixture_rows()
    rows["Special District"].update(
        {
            "STATE": None,
            "ZIP": "8044",
            "ZIP4": "7",
            "ACTIVE": "N",
        }
    )
    adapter.cache(adapter.verify(build_archive(rows)))

    result = adapter.parse()
    special = next(
        record
        for record in result.records
        if record.source_sheet is CensusGovernmentSheet.SPECIAL_DISTRICT
    )

    assert result.errors == ()
    assert special.active == "N"
    assert special.raw_fields["STATE"] is None
    assert special.raw_fields["ZIP"] == "8044"
    assert special.raw_fields["ZIP4"] == "7"


def test_parse_preserves_unvalidated_source_website(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    adapter.cache(adapter.verify(build_archive()))

    special = next(
        record
        for record in adapter.parse().records
        if record.source_sheet is CensusGovernmentSheet.SPECIAL_DISTRICT
    )

    assert special.raw_fields["WEB_ADDRESS"] == "sample.invalid/no-scheme"


def test_parse_preserves_parent_ids_without_resolving_them(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    rows = fixture_rows()
    rows["DEP School Dist"]["PARENT_CENSUS_ID_PID6"] = "999999"
    adapter.cache(adapter.verify(build_archive(rows)))

    dependent = next(
        record
        for record in adapter.parse().records
        if record.source_sheet is CensusGovernmentSheet.DEPENDENT_SCHOOL_DISTRICT
    )

    assert dependent.parent_census_id_pid6 == "999999"


def test_parse_reports_missing_pid_instead_of_dropping_row(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    rows = fixture_rows()
    rows["Special District"]["CENSUS_ID_PID6"] = None
    adapter.cache(adapter.verify(build_archive(rows)))

    result = adapter.parse()

    assert result.input_count == 5
    assert len(result.records) == 4
    assert len(result.errors) == 1
    error = result.errors[0]
    assert isinstance(error, CensusGovernmentParseError)
    assert error.source_sheet is CensusGovernmentSheet.SPECIAL_DISTRICT
    assert "CENSUS_ID_PID6" in error.message


def test_parse_reports_missing_parent_pid(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    rows = fixture_rows()
    rows["DEP School Dist"]["PARENT_CENSUS_ID_PID6"] = None
    adapter.cache(adapter.verify(build_archive(rows)))

    result = adapter.parse()

    assert len(result.errors) == 1
    assert "PARENT_CENSUS_ID_PID6" in result.errors[0].message


def test_parse_reports_duplicate_pid_across_sheets(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    rows = fixture_rows()
    rows["Special District"]["CENSUS_ID_PID6"] = "010001"
    adapter.cache(adapter.verify(build_archive(rows)))

    result = adapter.parse()

    assert result.input_count == 5
    assert len(result.records) == 4
    assert len(result.errors) == 1
    assert "duplicate CENSUS_ID_PID6" in result.errors[0].message


def test_parse_reports_invalid_unit_type(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    rows = fixture_rows()
    rows["School District"]["UNIT_TYPE"] = "4 - SPECIAL DISTRICT"
    adapter.cache(adapter.verify(build_archive(rows)))

    result = adapter.parse()

    assert len(result.errors) == 1
    assert "UNIT_TYPE" in result.errors[0].message


def test_parse_reports_invalid_active_flag(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    rows = fixture_rows()
    rows["Public Pension Sys"]["ACTIVE"] = "MAYBE"
    adapter.cache(adapter.verify(build_archive(rows)))

    result = adapter.parse()

    assert len(result.errors) == 1
    assert "ACTIVE must be 'Y' or 'N'" in result.errors[0].message


def test_iter_parse_streams_records_and_errors(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    rows = fixture_rows()
    rows["General Purpose"]["UNIT_NAME"] = None
    adapter.cache(adapter.verify(build_archive(rows)))

    outcomes = list(adapter.iter_parse())

    assert len(outcomes) == 5
    assert sum(isinstance(item, CensusGovernmentSourceRecord) for item in outcomes) == 4
    assert sum(isinstance(item, CensusGovernmentParseError) for item in outcomes) == 1


def test_unsupported_release_is_explicit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported Government Units release"):
        CensusGovernmentAdapter(tmp_path, release_year="2024")
