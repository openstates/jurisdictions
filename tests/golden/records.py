# tests/golden/records.py
from __future__ import annotations

from datetime import datetime, timezone

from src.models.division import Boundary, Division, Geometry, Identifier
from src.models.jurisdiction import ClassificationEnum, Jurisdiction
from src.models.source import SourceObj, SourceType

FIXED_TS = datetime(2025, 10, 27, 1, 29, 51, tzinfo=timezone.utc)
DIVISION_OCDID = "ocd-division/country:us/state:wa/place:seattle"
JURISDICTION_OCDID = "ocd-jurisdiction/country:us/state:wa/place:seattle/government"


def make_source(field: list[str], name: str = "Census TIGER/Line") -> SourceObj:
    return SourceObj(
        field=field,
        source_name=name,
        source_type=SourceType.HUMAN,
        source_url="https://www.census.gov/",
        source_description=None,
    )


def make_geoid_identifier(value: str = "5363000") -> Identifier:
    return Identifier(
        authority="census",
        id_type="geoid",
        value=value,
        source=make_source(["government_identifiers"]),
    )


def make_geometry(
    valid_from: datetime | None, valid_to: datetime | None
) -> Geometry:
    return Geometry(
        valid_from=valid_from,
        valid_to=valid_to,
        boundary=Boundary(),
        url="https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/5/query?f=geojson",
        source=make_source(["geometries"]),
    )


def make_division(
    *,
    ocdid: str = DIVISION_OCDID,
    display_name: str = "Seattle",
    last_updated: datetime = FIXED_TS,
    geometries: list[Geometry] | None = None,
    geoid: str = "5363000",
) -> Division:
    return Division(
        ocdid=ocdid,
        country="us",
        display_name=display_name,
        geometries=geometries if geometries is not None else [make_geometry(None, None)],
        government_identifiers=[make_geoid_identifier(geoid)],
        sourcing=[make_source(["geometries"])],
        jurisdiction_id=JURISDICTION_OCDID,
        accurate_asof=last_updated,
        last_updated=last_updated,
    )


def make_jurisdiction(
    *,
    ocdid: str = JURISDICTION_OCDID,
    classification: ClassificationEnum = ClassificationEnum.GOVERNMENT,
    name: str = "Seattle City Government",
    last_updated: datetime = FIXED_TS,
) -> Jurisdiction:
    return Jurisdiction(
        ocdid=ocdid,
        name=name,
        classification=classification,
        accurate_asof=last_updated,
        last_updated=last_updated,
        metadata={"urls": []},
    )
