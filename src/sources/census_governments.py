"""
Census of Governments: Organization, the benchmark government listing.

Every five years, in years ending in 2 and 7, the Census Bureau enumerates
every government in the United States. The Organization component is
published as ``govt_units_<year>.ZIP`` containing ``Govt_Units_<year>_Final.xlsx``
with four sheets: general purpose governments, special districts, school
districts, and dependent school systems. This is the benchmark the
pipeline builds from; the annual listing between censuses is a separate
source (``census_gus.py``) and is never read here.

Fetch, verify and cache go through the snapshot store; parsing goes
through the shared validator with this listing's column layout.
"""

from __future__ import annotations

from datetime import datetime

from src.init_migration.downloader import AsyncDownloader
from src.sources.government_units import (
    GovernmentKind,
    Layout,
    ParseResult,
    parse_csv_snapshot,
    parse_workbook_snapshot,
)
from src.sources.snapshot import Snapshot, SnapshotSpec, SnapshotStore

SOURCE = "census_governments"
SOURCE_NAME = "U.S. Census Bureau"
DATASET = "Census of Governments: Organization, Government Units listing"
URL_TEMPLATE = (
    "https://www2.census.gov/programs-surveys/gus/datasets/{year}/govt_units_{year}.ZIP"
)
FILENAME_TEMPLATE = "govt_units_{year}.ZIP"

LAYOUT = Layout(
    sheets={
        "General Purpose": GovernmentKind.GENERAL_PURPOSE,
        "Special District": GovernmentKind.SPECIAL_DISTRICT,
        "School District": GovernmentKind.SCHOOL_DISTRICT,
        "DEP School Dist": GovernmentKind.DEPENDENT_SCHOOL_SYSTEM,
    },
)


def is_census_year(year: int | str) -> bool:
    """Census of Governments years end in 2 or 7."""
    return int(year) % 5 == 2


def census_of_governments_url(year: int | str) -> str:
    return URL_TEMPLATE.format(year=int(year))


def census_of_governments_spec(year: int | str) -> SnapshotSpec:
    """Snapshot spec for the Organization listing of a Census of Governments year."""
    if not is_census_year(year):
        raise ValueError(
            f"{year} is not a Census of Governments year (years ending in 2 or 7)"
        )
    return SnapshotSpec(
        source=SOURCE,
        source_name=SOURCE_NAME,
        dataset=DATASET,
        release=str(int(year)),
        filename=FILENAME_TEMPLATE.format(year=int(year)),
        url=census_of_governments_url(year),
    )


async def fetch_census_of_governments(
    store: SnapshotStore,
    downloader: AsyncDownloader,
    year: int | str,
    *,
    retrieved_at: datetime,
    refresh: bool = False,
) -> Snapshot:
    return await store.fetch(
        census_of_governments_spec(year),
        downloader,
        retrieved_at=retrieved_at,
        refresh=refresh,
    )


def parse_snapshot(snapshot: Snapshot) -> ParseResult:
    """Parse the benchmark workbook held by ``snapshot`` (ZIP or XLSX)."""
    return parse_workbook_snapshot(snapshot, LAYOUT)


def parse_sheet_snapshot(snapshot: Snapshot, kind: GovernmentKind) -> ParseResult:
    """Parse a CSV excerpt of one benchmark sheet."""
    return parse_csv_snapshot(snapshot, kind, LAYOUT)
