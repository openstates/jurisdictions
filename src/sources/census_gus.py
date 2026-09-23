"""
Annual Government Units listing from the Government Units Survey.

Between censuses the Census Bureau publishes a yearly snapshot of its
Governments Master Address File as ``gov_units_<year>.zip`` containing
``Govt_Units_<year>_Final.xlsx``. It carries the same governments as the
Census of Governments benchmark (``census_governments.py``) with renamed
columns, no legacy id, parent ids on dependent units, and a fifth sheet of
public pension systems. This module is independent of the benchmark
module: it has its own spec, fetch, layout and parse, and shares only the
record type and validator in ``government_units.py``.

Public pension systems are dependent agencies, not governments. They are
parsed so they can be exported as their own dataset under the cache root;
nothing downstream reads them.
"""

from __future__ import annotations

import csv
import io
from dataclasses import fields
from datetime import datetime
from logging import getLogger
from pathlib import Path

from src.init_migration.downloader import AsyncDownloader
from src.sources.government_units import (
    CensusGovernmentRecord,
    GovernmentKind,
    Layout,
    ParseResult,
    parse_csv_snapshot,
    parse_workbook_snapshot,
)
from src.sources.snapshot import (
    Snapshot,
    SnapshotMetadata,
    SnapshotSpec,
    SnapshotStore,
    sha256_of_bytes,
    write_metadata,
)

logger = getLogger(__name__)

SOURCE = "census_gus"
SOURCE_NAME = "U.S. Census Bureau"
DATASET = "Governments Master Address File, Government Units listing"
URL_TEMPLATE = (
    "https://www2.census.gov/programs-surveys/gus/datasets/{year}/gov_units_{year}.zip"
)
FILENAME_TEMPLATE = "gov_units_{year}.zip"
FIRST_ANNUAL_YEAR = 2024
DEFAULT_CACHE_ROOT = Path("data/cache")
PENSION_EXPORT_FILENAME = "public_pension_systems.csv"

LAYOUT = Layout(
    sheets={
        "General Purpose": GovernmentKind.GENERAL_PURPOSE,
        "Special District": GovernmentKind.SPECIAL_DISTRICT,
        "School District": GovernmentKind.SCHOOL_DISTRICT,
        "DEP School Dist": GovernmentKind.DEPENDENT_SCHOOL_SYSTEM,
        "Public Pension Sys": GovernmentKind.PUBLIC_PENSION_SYSTEM,
        "Public Pensions Sys": GovernmentKind.PUBLIC_PENSION_SYSTEM,
    },
    column_aliases={
        "ACTIVE": "IS_ACTIVE",
        "POPULATION_SOURCE_YEAR": "POPULATION_YEAR",
        "SCHOOL_ENROLLMENT": "ENROLLMENT",
        "ACTIVITY_NAME": "FUNCTION_NAME",
    },
)

EXPORT_COLUMNS = tuple(
    field.name for field in fields(CensusGovernmentRecord) if field.name != "attributes"
)


def is_annual_year(year: int | str) -> bool:
    """Annual listings exist from 2024 in years that are not a Census of Governments."""
    return int(year) >= FIRST_ANNUAL_YEAR and int(year) % 5 != 2


def government_units_url(year: int | str) -> str:
    return URL_TEMPLATE.format(year=int(year))


def government_units_spec(year: int | str) -> SnapshotSpec:
    """Snapshot spec for the annual listing of ``year``."""
    if not is_annual_year(year):
        raise ValueError(
            f"{year} has no annual Government Units listing; the first is "
            f"{FIRST_ANNUAL_YEAR} and Census of Governments years use the benchmark"
        )
    return SnapshotSpec(
        source=SOURCE,
        source_name=SOURCE_NAME,
        dataset=DATASET,
        release=str(int(year)),
        filename=FILENAME_TEMPLATE.format(year=int(year)),
        url=government_units_url(year),
    )


async def fetch_government_units(
    store: SnapshotStore,
    downloader: AsyncDownloader,
    year: int | str,
    *,
    retrieved_at: datetime,
    refresh: bool = False,
) -> Snapshot:
    return await store.fetch(
        government_units_spec(year),
        downloader,
        retrieved_at=retrieved_at,
        refresh=refresh,
    )


def parse_snapshot(snapshot: Snapshot) -> ParseResult:
    """Parse the annual workbook held by ``snapshot`` (ZIP or XLSX), all five sheets."""
    return parse_workbook_snapshot(snapshot, LAYOUT)


def parse_sheet_snapshot(snapshot: Snapshot, kind: GovernmentKind) -> ParseResult:
    """Parse a CSV excerpt of one annual sheet."""
    return parse_csv_snapshot(snapshot, kind, LAYOUT)


def governments(result: ParseResult) -> list[CensusGovernmentRecord]:
    """The records that are governments: everything but pension systems."""
    return [
        record
        for record in result.records
        if record.kind is not GovernmentKind.PUBLIC_PENSION_SYSTEM
    ]


def pension_systems(result: ParseResult) -> list[CensusGovernmentRecord]:
    return [
        record
        for record in result.records
        if record.kind is GovernmentKind.PUBLIC_PENSION_SYSTEM
    ]


def _record_row(record: CensusGovernmentRecord) -> list[str]:
    row: list[str] = []
    for column in EXPORT_COLUMNS:
        value = getattr(record, column)
        if value is None:
            row.append("")
        elif isinstance(value, bool):
            row.append("Y" if value else "N")
        elif isinstance(value, GovernmentKind):
            row.append(value.value)
        else:
            row.append(str(value))
    return row


def records_to_csv(records: list[CensusGovernmentRecord]) -> str:
    """Records as CSV text with one column per record field, sorted by Census ID."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(EXPORT_COLUMNS)
    for record in sorted(records, key=lambda r: r.census_id):
        writer.writerow(_record_row(record))
    return buffer.getvalue()


def export_pension_systems(
    result: ParseResult,
    *,
    cache_root: Path = DEFAULT_CACHE_ROOT,
) -> Snapshot:
    """Write the pension systems from a parsed annual listing as their own dataset.

    The file lands at ``<cache_root>/census_gus/<year>/public_pension_systems.csv``
    with a sidecar whose ``url``, ``release``, ``publication_date`` and
    ``retrieved_at`` are the source listing's. The pipeline never reads it.
    """
    if result.metadata is None:
        raise ValueError("parse result carries no snapshot metadata to cite")
    source = result.metadata
    content = records_to_csv(pension_systems(result)).encode("utf-8")
    path = Path(cache_root) / SOURCE / source.release / PENSION_EXPORT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    metadata = SnapshotMetadata(
        source=SOURCE,
        source_name=source.source_name,
        dataset=f"{DATASET}, Public Pension Sys sheet (export of {source.filename})",
        release=source.release,
        filename=path.name,
        url=source.url,
        sha256=sha256_of_bytes(content),
        size_bytes=len(content),
        retrieved_at=source.retrieved_at,
        publication_date=source.publication_date,
    )
    write_metadata(path, metadata)
    logger.info(
        "pension systems exported",
        extra={
            "path": str(path),
            "records": len(pension_systems(result)),
            "release": source.release,
        },
    )
    return Snapshot(path=path, metadata=metadata)
