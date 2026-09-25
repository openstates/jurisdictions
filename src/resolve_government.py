"""Resolve normalized Census governments to TIGER geography.

Resolution is deterministic and identifier-first. This stage does not
generate OCDIDs or canonical Division/Jurisdiction models.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable, Mapping

from pydantic import BaseModel, ConfigDict

from src.models.source import SourceObj
from src.normalize_government import GovernmentRecord, GovernmentType
from src.sources.census_tiger import (
    TigerConfig,
    TigerRecord,
    geometry_url as tiger_geometry_url,
    place_layer_key,
)


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    NO_GEOGRAPHY = "no_geography"
    DIVISION_NOT_FOUND = "division_not_found"
    AMBIGUOUS = "ambiguous"


class CensusDivisionRecord(BaseModel):
    """A TIGER geography selected for a normalized government."""

    model_config = ConfigDict(frozen=True)

    layer: str
    geography_type: str

    geoid: str
    geoidfq: str | None = None

    name: str
    namelsad: str | None = None

    state_fips: str
    county_fips: str | None = None
    place_fips: str | None = None
    cousub_fips: str | None = None
    lea: str | None = None

    geometry_source: SourceObj
    geometry_url: str


class ResolutionResult(BaseModel):
    """Terminal result of one government-to-geography resolution attempt."""

    model_config = ConfigDict(frozen=True)

    status: ResolutionStatus
    division: CensusDivisionRecord | None = None
    candidates: list[CensusDivisionRecord] = []


def _matches_state(
    government: GovernmentRecord,
    record: TigerRecord,
) -> bool:
    return (
        record.geography == "state"
        and record.statefp == government.state_fips
        and record.geoid == government.state_fips
    )


def _matches_county(
    government: GovernmentRecord,
    record: TigerRecord,
) -> bool:
    if government.county_fips is None:
        return False

    return (
        record.geography == "county"
        and record.statefp == government.state_fips
        and record.countyfp == government.county_fips
    )


_ACTIVE_GOVERNMENT_FUNCSTATS = frozenset({"A", "B", "C", "G"})


def _matches_mcd(
    government: GovernmentRecord,
    record: TigerRecord,
) -> bool:
    if government.county_fips is None or government.place_fips is None:
        return False

    return (
        record.geography == "county_subdivision"
        and record.statefp == government.state_fips
        and record.countyfp == government.county_fips
        and record.cousubfp == government.place_fips
        and (record.funcstat or "").upper() in _ACTIVE_GOVERNMENT_FUNCSTATS
    )


def _matches_school(
    government: GovernmentRecord,
    record: TigerRecord,
    school_nces_ids: Mapping[str, str],
) -> bool:
    nces_id = school_nces_ids.get(government.census_government_id)
    if nces_id is None:
        return False

    return (
        record.geography == "school_district"
        and record.statefp == government.state_fips
        and record.geoid == nces_id
    )


def _matches_municipality(
    government: GovernmentRecord,
    record: TigerRecord,
) -> bool:
    if government.place_fips is None:
        return False

    return (
        record.geography == "place"
        and record.statefp == government.state_fips
        and record.placefp == government.place_fips
        and place_layer_key(record) == "place"
        and (record.funcstat or "").upper() in _ACTIVE_GOVERNMENT_FUNCSTATS
    )


def _candidate_records(
    government: GovernmentRecord,
    records: Iterable[TigerRecord],
    *,
    school_nces_ids: Mapping[str, str],
) -> list[TigerRecord]:
    if government.government_type is GovernmentType.STATE:
        return [
            record
            for record in records
            if _matches_state(government, record)
        ]

    if government.government_type is GovernmentType.COUNTY:
        return [
            record
            for record in records
            if _matches_county(government, record)
        ]

    if government.government_type is GovernmentType.MUNICIPAL:
        return [
            record
            for record in records
            if _matches_municipality(government, record)
        ]

    if government.government_type is GovernmentType.TOWNSHIP_MCD:
        return [
            record
            for record in records
            if _matches_mcd(government, record)
        ]

    if government.government_type is GovernmentType.SCHOOL_DISTRICT:
        return [
            record
            for record in records
            if _matches_school(government, record, school_nces_ids)
        ]

    return []


def _division(
    record: TigerRecord,
    *,
    config: TigerConfig,
    tiger_source: SourceObj,
) -> CensusDivisionRecord:
    return CensusDivisionRecord(
        layer=record.layer,
        geography_type=record.geography,
        geoid=record.geoid,
        geoidfq=record.geoidfq,
        name=record.name,
        namelsad=record.namelsad,
        state_fips=record.statefp,
        county_fips=record.countyfp,
        place_fips=record.placefp,
        cousub_fips=record.cousubfp,
        lea=record.lea,
        geometry_source=tiger_source,
        geometry_url=tiger_geometry_url(config, record),
    )


def resolve_government(
    government: GovernmentRecord,
    records: Iterable[TigerRecord],
    *,
    config: TigerConfig,
    tiger_source: SourceObj,
    school_nces_ids: Mapping[str, str] | None = None,
) -> ResolutionResult:
    """Resolve one government to TIGER geography without fuzzy matching."""

    if government.government_type is GovernmentType.SPECIAL_DISTRICT:
        return ResolutionResult(status=ResolutionStatus.NO_GEOGRAPHY)

    matches = _candidate_records(
        government,
        records,
        school_nces_ids=school_nces_ids or {},
    )

    if not matches:
        return ResolutionResult(status=ResolutionStatus.DIVISION_NOT_FOUND)

    candidates = [
        _division(
            record,
            config=config,
            tiger_source=tiger_source,
        )
        for record in matches
    ]

    if len(candidates) > 1:
        return ResolutionResult(
            status=ResolutionStatus.AMBIGUOUS,
            candidates=candidates,
        )

    return ResolutionResult(
        status=ResolutionStatus.RESOLVED,
        division=candidates[0],
        candidates=candidates,
    )
