"""
Shared record type and row validation for Census Bureau government listings.

Two listings share this code and nothing else: the Census of Governments:
Organization benchmark (``census_governments.py``) and the annual
Government Units listing (``census_gus.py``). Each listing is an Excel
workbook with one sheet per government class; the sheets' column names
differ between the two, so each listing module declares a ``Layout`` and
this module does the parsing.

Every identifier is kept as a string so leading zeros survive. A row that
fails validation becomes a ``CensusRowError`` and the rest of the sheet
still loads. Nothing here classifies, normalizes, or merges governments.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from logging import getLogger

import openpyxl

from src.sources.snapshot import Snapshot, SnapshotMetadata

logger = getLogger(__name__)


class GovernmentKind(str, Enum):
    """Which sheet of the workbook a record came from."""

    GENERAL_PURPOSE = "general_purpose"
    SPECIAL_DISTRICT = "special_district"
    SCHOOL_DISTRICT = "school_district"
    DEPENDENT_SCHOOL_SYSTEM = "dependent_school_system"
    PUBLIC_PENSION_SYSTEM = "public_pension_system"


@dataclass(frozen=True, slots=True)
class Layout:
    """How one listing's workbook is laid out.

    ``sheets`` maps sheet title to kind; ``skipped_sheets`` are sheets the
    listing carries that are not governments; ``column_aliases`` maps the
    listing's column names onto the names this module validates.
    """

    sheets: Mapping[str, GovernmentKind]
    skipped_sheets: frozenset[str] = frozenset()
    column_aliases: Mapping[str, str] = field(default_factory=dict)

    def column(self, name: object) -> str:
        text = cell_text(name)
        return self.column_aliases.get(text, text)


REQUIRED_COLUMNS = (
    "CENSUS_ID_PID6",
    "UNIT_NAME",
    "STATE",
    "FIPS_STATE",
    "IS_ACTIVE",
)
KNOWN_COLUMNS = frozenset(
    REQUIRED_COLUMNS
    + (
        "CENSUS_ID_GIDID",
        "UNIT_TYPE",
        "FUNCTION_NAME",
        "SCHOOL_LEVEL_DESCRIPTION",
        "POLITICAL_CODE_DESCRIPTION",
        "WEB_ADDRESS",
        "POPULATION",
        "POPULATION_YEAR",
        "ENROLLMENT",
        "ENROLLMENT_YEAR",
        "FIPS_COUNTY",
        "FIPS_PLACE",
        "COUNTY_AREA_NAME",
        "PARENT_CENSUS_ID_PID6",
        "PARENT_UNIT_NAME",
    )
)

_CENSUS_ID = re.compile(r"^\d{6}$")
_STATE = re.compile(r"^[A-Z]{2}$")
_FIPS_STATE = re.compile(r"^\d{2}$")
_FIPS_COUNTY = re.compile(r"^\d{3}$")
_FIPS_PLACE = re.compile(r"^\d{5}$")
_INT = re.compile(r"^\d+$")


@dataclass(frozen=True, slots=True)
class CensusGovernmentRecord:
    """One government unit as listed by the Census Bureau.

    Identifiers and FIPS codes are strings exactly as published. ``kind`` is
    the workbook sheet; ``unit_type``, ``function_name``, ``school_level``
    and ``political_code`` are the sheet's own classification columns,
    verbatim. Fields a listing does not publish are ``None``.
    """

    census_id: str
    name: str
    kind: GovernmentKind
    state: str
    fips_state: str
    is_active: bool
    legacy_id: str | None = None
    unit_type: str | None = None
    function_name: str | None = None
    school_level: str | None = None
    political_code: str | None = None
    fips_county: str | None = None
    fips_place: str | None = None
    county_area_name: str | None = None
    web_address: str | None = None
    population: int | None = None
    population_year: int | None = None
    school_enrollment: int | None = None
    enrollment_year: int | None = None
    parent_census_id: str | None = None
    parent_name: str | None = None
    attributes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CensusRowError:
    """A row that did not validate; the sheet continues without it."""

    sheet: str
    line: int
    census_id: str
    reason: str


@dataclass(slots=True)
class ParseResult:
    """Records and per-row errors for one or more sheets."""

    records: list[CensusGovernmentRecord] = field(default_factory=list)
    errors: list[CensusRowError] = field(default_factory=list)
    metadata: SnapshotMetadata | None = None

    def extend(self, other: ParseResult) -> None:
        self.records.extend(other.records)
        self.errors.extend(other.errors)


def cell_text(value: object) -> str:
    """A cell as the string the listing meant: ``None`` empty, whole floats as ints."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _optional(value: str) -> str | None:
    return value or None


def _optional_int(value: str, column: str, problems: list[str]) -> int | None:
    if not value:
        return None
    digits = value.replace(",", "")
    if not _INT.match(digits):
        problems.append(f"{column} is not an integer: {value!r}")
        return None
    return int(digits)


def _validate_code(
    value: str, pattern: re.Pattern[str], column: str, problems: list[str]
) -> str | None:
    if not value:
        return None
    if not pattern.match(value):
        problems.append(f"{column} is malformed: {value!r}")
        return None
    return value


def parse_row(
    row: Mapping[str, object],
    kind: GovernmentKind,
    sheet: str,
    line: int,
    layout: Layout,
) -> CensusGovernmentRecord | CensusRowError:
    """Validate one row; return a record or a structured error."""
    cells = {
        layout.column(key): cell_text(value)
        for key, value in row.items()
        if key is not None
    }
    problems: list[str] = []

    census_id = cells.get("CENSUS_ID_PID6", "")
    if not _CENSUS_ID.match(census_id):
        problems.append(f"CENSUS_ID_PID6 is malformed: {census_id!r}")
    name = cells.get("UNIT_NAME", "")
    if not name:
        problems.append("UNIT_NAME is empty")
    state = cells.get("STATE", "")
    if not _STATE.match(state):
        problems.append(f"STATE is malformed: {state!r}")
    fips_state = cells.get("FIPS_STATE", "")
    if not _FIPS_STATE.match(fips_state):
        problems.append(f"FIPS_STATE is malformed: {fips_state!r}")
    active_flag = cells.get("IS_ACTIVE", "")
    if active_flag not in ("Y", "N"):
        problems.append(f"IS_ACTIVE is malformed: {active_flag!r}")

    fips_county = _validate_code(
        cells.get("FIPS_COUNTY", ""), _FIPS_COUNTY, "FIPS_COUNTY", problems
    )
    fips_place = _validate_code(
        cells.get("FIPS_PLACE", ""), _FIPS_PLACE, "FIPS_PLACE", problems
    )
    parent_census_id = _validate_code(
        cells.get("PARENT_CENSUS_ID_PID6", ""),
        _CENSUS_ID,
        "PARENT_CENSUS_ID_PID6",
        problems,
    )
    population = _optional_int(cells.get("POPULATION", ""), "POPULATION", problems)
    population_year = _optional_int(
        cells.get("POPULATION_YEAR", ""), "POPULATION_YEAR", problems
    )
    enrollment = _optional_int(cells.get("ENROLLMENT", ""), "ENROLLMENT", problems)
    enrollment_year = _optional_int(
        cells.get("ENROLLMENT_YEAR", ""), "ENROLLMENT_YEAR", problems
    )

    if problems:
        return CensusRowError(
            sheet=sheet, line=line, census_id=census_id, reason="; ".join(problems)
        )

    attributes = {
        key: value for key, value in cells.items() if key not in KNOWN_COLUMNS
    }
    return CensusGovernmentRecord(
        census_id=census_id,
        name=name,
        kind=kind,
        state=state,
        fips_state=fips_state,
        is_active=active_flag == "Y",
        legacy_id=_optional(cells.get("CENSUS_ID_GIDID", "")),
        unit_type=_optional(cells.get("UNIT_TYPE", "")),
        function_name=_optional(cells.get("FUNCTION_NAME", "")),
        school_level=_optional(cells.get("SCHOOL_LEVEL_DESCRIPTION", "")),
        political_code=_optional(cells.get("POLITICAL_CODE_DESCRIPTION", "")),
        fips_county=fips_county,
        fips_place=fips_place,
        county_area_name=_optional(cells.get("COUNTY_AREA_NAME", "")),
        web_address=_optional(cells.get("WEB_ADDRESS", "")),
        population=population,
        population_year=population_year,
        school_enrollment=enrollment,
        enrollment_year=enrollment_year,
        parent_census_id=parent_census_id,
        parent_name=_optional(cells.get("PARENT_UNIT_NAME", "")),
        attributes=attributes,
    )


def parse_rows(
    header: Iterable[object],
    rows: Iterable[Iterable[object]],
    kind: GovernmentKind,
    sheet: str,
    layout: Layout,
    *,
    first_line: int = 2,
) -> ParseResult:
    """Parse a header plus data rows from one sheet."""
    result = ParseResult()
    columns = [layout.column(column) for column in header]
    missing = [column for column in REQUIRED_COLUMNS if column not in columns]
    if missing:
        result.errors.append(
            CensusRowError(
                sheet=sheet,
                line=1,
                census_id="",
                reason="missing required columns: " + ", ".join(missing),
            )
        )
        return result
    for offset, values in enumerate(rows):
        line = first_line + offset
        values = list(values)
        if not any(cell_text(value) for value in values):
            continue
        outcome = parse_row(dict(zip(columns, values)), kind, sheet, line, layout)
        if isinstance(outcome, CensusRowError):
            result.errors.append(outcome)
        else:
            result.records.append(outcome)
    return result


def parse_csv(
    text: str, kind: GovernmentKind, sheet: str, layout: Layout
) -> ParseResult:
    """Parse a CSV export of one sheet (header row included)."""
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration:
        result = ParseResult()
        result.errors.append(
            CensusRowError(sheet=sheet, line=1, census_id="", reason="empty file")
        )
        return result
    return parse_rows(header, reader, kind, sheet, layout)


def parse_csv_snapshot(
    snapshot: Snapshot, kind: GovernmentKind, layout: Layout
) -> ParseResult:
    """Parse a CSV snapshot of one sheet, carrying its metadata."""
    result = parse_csv(snapshot.read_text(), kind, snapshot.path.name, layout)
    result.metadata = snapshot.metadata
    log_result(result, snapshot.path.name)
    return result


def parse_workbook(
    content: bytes, layout: Layout, *, name: str = "workbook"
) -> ParseResult:
    """Parse every government sheet of the Excel workbook in ``content``."""
    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
    result = ParseResult()
    try:
        for sheet in workbook.worksheets:
            kind = layout.sheets.get(sheet.title)
            if kind is None:
                if sheet.title in layout.skipped_sheets:
                    logger.info(
                        "sheet skipped",
                        extra={"workbook": name, "sheet": sheet.title},
                    )
                else:
                    logger.warning(
                        "unknown sheet skipped",
                        extra={"workbook": name, "sheet": sheet.title},
                    )
                continue
            rows = sheet.iter_rows(values_only=True)
            header = next(rows, None)
            if header is None:
                result.errors.append(
                    CensusRowError(
                        sheet=sheet.title, line=1, census_id="", reason="empty sheet"
                    )
                )
                continue
            result.extend(parse_rows(header, rows, kind, sheet.title, layout))
    finally:
        workbook.close()
    return result


def workbook_bytes(snapshot: Snapshot) -> bytes:
    """The ``.xlsx`` bytes of a snapshot, unpacking a ZIP if that is what was fetched."""
    if snapshot.path.suffix.lower() == ".zip":
        with zipfile.ZipFile(snapshot.path) as archive:
            members = [
                member
                for member in archive.namelist()
                if member.lower().endswith(".xlsx")
            ]
            if len(members) != 1:
                raise ValueError(
                    f"expected one .xlsx in {snapshot.path.name}, found {len(members)}"
                )
            return archive.read(members[0])
    return snapshot.read_bytes()


def parse_workbook_snapshot(snapshot: Snapshot, layout: Layout) -> ParseResult:
    """Parse the workbook held by ``snapshot`` (ZIP or XLSX), carrying its metadata."""
    result = parse_workbook(workbook_bytes(snapshot), layout, name=snapshot.path.name)
    result.metadata = snapshot.metadata
    log_result(result, snapshot.path.name)
    return result


def log_result(result: ParseResult, name: str) -> None:
    logger.info(
        "census government units parsed",
        extra={
            "snapshot_file": name,
            "records": len(result.records),
            "row_errors": len(result.errors),
        },
    )
