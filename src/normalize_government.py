"""Normalize Census government records into a deterministic internal layer.

This stage preserves authoritative Census values while adding normalized
matching fields and a deterministic government classification. It does not
resolve geography, generate OCDIDs, or build canonical YAML models.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Iterable

from pydantic import BaseModel, ConfigDict

from src.models.source import SourceObj
from src.sources.government_units import (
    CensusGovernmentRecord,
    CensusRowError,
    GovernmentKind,
)


class GovernmentType(str, Enum):
    STATE = "state"
    COUNTY = "county"
    MUNICIPAL = "municipal"
    TOWNSHIP_MCD = "township_mcd"
    SCHOOL_DISTRICT = "school_district"
    SPECIAL_DISTRICT = "special_district"
    OTHER = "other"
    UNKNOWN = "unknown"


class GovernmentRecord(BaseModel):
    """Normalized representation of one Census government record."""

    model_config = ConfigDict(frozen=True)

    census_government_id: str

    name: str
    normalized_name: str

    government_type: GovernmentType
    government_subtype: str | None = None

    state_fips: str
    county_fips: str | None = None
    place_fips: str | None = None

    state: str
    county_name: str | None = None

    website: str | None = None
    is_active: bool

    parent_census_government_id: str | None = None
    parent_name: str | None = None

    source: SourceObj


class NormalizationResult(BaseModel):
    """Normalized records plus all structured source errors from ingestion."""

    model_config = ConfigDict(frozen=True)

    records: list[GovernmentRecord]
    source_errors: list[CensusRowError]


_WHITESPACE_RE = re.compile(r"\s+")
_UNIT_TYPE_RE = re.compile(r"^\s*(\d+)\s*-")


def normalize_name(name: str) -> str:
    """Normalize a source name for matching without changing its semantics."""
    return _WHITESPACE_RE.sub(" ", name.strip()).casefold()


def _unit_type_code(unit_type: str | None) -> str | None:
    if not unit_type:
        return None

    match = _UNIT_TYPE_RE.match(unit_type)
    return match.group(1) if match else None


def _classification(
    record: CensusGovernmentRecord,
) -> tuple[GovernmentType, str | None]:
    """Classify a Census record without performing geography resolution."""

    if record.kind is GovernmentKind.DEPENDENT_SCHOOL_SYSTEM:
        return GovernmentType.OTHER, GovernmentKind.DEPENDENT_SCHOOL_SYSTEM.value

    if record.kind is GovernmentKind.SPECIAL_DISTRICT:
        return GovernmentType.SPECIAL_DISTRICT, record.function_name or record.unit_type

    if record.kind is GovernmentKind.SCHOOL_DISTRICT:
        return GovernmentType.SCHOOL_DISTRICT, record.school_level or record.unit_type

    if record.kind is not GovernmentKind.GENERAL_PURPOSE:
        return GovernmentType.UNKNOWN, record.unit_type

    code = _unit_type_code(record.unit_type)
    government_type = {
        "0": GovernmentType.STATE,
        "1": GovernmentType.COUNTY,
        "2": GovernmentType.MUNICIPAL,
        "3": GovernmentType.TOWNSHIP_MCD,
    }.get(code, GovernmentType.UNKNOWN)

    return government_type, record.unit_type


def normalize_record(
    record: CensusGovernmentRecord,
    *,
    source: SourceObj,
) -> GovernmentRecord:
    """Normalize one validated Census government record."""

    government_type, government_subtype = _classification(record)

    return GovernmentRecord(
        census_government_id=record.census_id,
        name=record.name,
        normalized_name=normalize_name(record.name),
        government_type=government_type,
        government_subtype=government_subtype,
        state_fips=record.fips_state,
        county_fips=record.fips_county,
        place_fips=record.fips_place,
        state=record.state,
        county_name=record.county_area_name,
        website=record.web_address,
        is_active=record.is_active,
        parent_census_government_id=record.parent_census_id,
        parent_name=record.parent_name,
        source=source,
    )


def normalize_records(
    records: Iterable[CensusGovernmentRecord],
    *,
    source: SourceObj,
    source_errors: Iterable[CensusRowError] = (),
) -> NormalizationResult:
    """Normalize every supplied record and preserve all source errors."""

    return NormalizationResult(
        records=[normalize_record(record, source=source) for record in records],
        source_errors=list(source_errors),
    )
