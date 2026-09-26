"""Construct canonical Division and Jurisdiction models from verified pipeline data.

This stage is deliberately offline. It consumes already-normalized,
already-resolved, canonically-verified records and performs no acquisition,
lookup, or network validation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.models.division import (
    Boundary,
    Division,
    Geometry,
    Identifier,
    Identifiers,
)
from src.models.jurisdiction import (
    ClassificationEnum,
    DivisionRelationship,
    DivisionRelationshipType,
    Jurisdiction,
)
from src.models.ocdid import OCDIdParsed
from src.models.source import SourceObj
from src.normalize_government import GovernmentRecord, GovernmentType
from src.ocdid_rule_engine import derive_jurisdiction_candidate
from src.ocdid_validation import (
    OCDIDValidationResult,
    OCDIDValidationStatus,
)
from src.resolve_government import CensusDivisionRecord


class CanonicalModels(BaseModel):
    """Canonical records produced for one verified government/division pair."""

    model_config = ConfigDict(frozen=True)

    division: Division
    jurisdiction: Jurisdiction


_JURISDICTION_CLASSIFICATION = {
    GovernmentType.STATE: ClassificationEnum.GOVERNMENT,
    GovernmentType.COUNTY: ClassificationEnum.GOVERNMENT,
    GovernmentType.MUNICIPAL: ClassificationEnum.GOVERNMENT,
    GovernmentType.TOWNSHIP_MCD: ClassificationEnum.GOVERNMENT,
    GovernmentType.SCHOOL_DISTRICT: ClassificationEnum.SCHOOL_SYSTEM,
}


def _require_verified_ocdid(validation: OCDIDValidationResult) -> str:
    if validation.status is not OCDIDValidationStatus.VERIFIED:
        raise ValueError("canonical model construction requires a VERIFIED OCDID")
    if validation.canonical_ocdid is None:
        raise ValueError("verified OCDID result requires canonical_ocdid")

    parsed = OCDIdParsed.parse_ocdid(validation.canonical_ocdid)
    if parsed.type != "ocd-division":
        raise ValueError("canonical Division construction requires an ocd-division ID")

    return validation.canonical_ocdid


def _retarget_source(source: SourceObj, fields: list[str]) -> SourceObj:
    """Preserve provenance while retargeting field paths to canonical output."""
    return source.model_copy(update={"field": fields})


def _source_observation_time(source: SourceObj, *, label: str):
    """Return a stable timestamp carried by the source snapshot."""
    observed_at = source.retrieval_date or source.publication_date
    if observed_at is None:
        raise ValueError(
            f"{label} requires retrieval_date or publication_date for deterministic output"
        )
    return observed_at


def _division_identifiers(
    division: CensusDivisionRecord,
) -> Identifiers:
    source = _retarget_source(
        division.geometry_source,
        ["government_identifiers", "geometries.identifiers"],
    )

    values: list[tuple[str, str, str | None]] = [
        ("census", "geoid", division.geoid),
        ("census", "geoidfq", division.geoidfq),
        ("census", "statefp", division.state_fips),
        ("census", "countyfp", division.county_fips),
        ("census", "placefp", division.place_fips),
        ("census", "cousubfp", division.cousub_fips),
        ("nces", "lea", division.lea),
    ]

    return [
        Identifier(
            authority=authority,
            id_type=id_type,
            value=value,
            source=source,
        )
        for authority, id_type, value in values
        if value is not None
    ]


def _other_division_names(
    division: CensusDivisionRecord,
    *,
    display_name: str,
) -> list[str]:
    names: list[str] = []
    for value in (division.name, division.namelsad):
        if value and value != display_name and value not in names:
            names.append(value)
    return names


def build_division(
    *,
    division: CensusDivisionRecord,
    validation: OCDIDValidationResult,
) -> Division:
    """Build a canonical Division from resolved geography and verified OCD identity."""
    canonical_ocdid = _require_verified_ocdid(validation)
    parsed = OCDIdParsed.parse_ocdid(canonical_ocdid)
    identifiers = _division_identifiers(division)
    display_name = validation.canonical_name or division.name

    geometry = Geometry(
        boundary=Boundary(),
        url=division.geometry_url,
        identifiers=identifiers,
        source=_retarget_source(division.geometry_source, ["geometries"]),
    )

    return Division(
        ocdid=canonical_ocdid,
        country=parsed.country,
        display_name=display_name,
        classification=division.geography_type,
        other_names=_other_division_names(
            division,
            display_name=display_name,
        ),
        geometries=[geometry],
        sourcing=[
            _retarget_source(
                division.geometry_source,
                [
                    "display_name",
                    "classification",
                    "government_identifiers",
                    "geometries",
                ],
            )
        ],
        government_identifiers=identifiers,
        jurisdiction_id=None,
        last_updated=_source_observation_time(
            division.geometry_source,
            label="division geometry source",
        ),
    )


def _jurisdiction_classification(
    government: GovernmentRecord,
) -> ClassificationEnum:
    try:
        return _JURISDICTION_CLASSIFICATION[government.government_type]
    except KeyError as error:
        raise ValueError(
            "no Phase 9 Jurisdiction classification for government type "
            f"{government.government_type.value!r}"
        ) from error


def build_jurisdiction(
    *,
    government: GovernmentRecord,
    division: Division,
) -> Jurisdiction:
    """Build a canonical Jurisdiction governing one verified canonical Division."""
    classification = _jurisdiction_classification(government)
    jurisdiction_candidate = derive_jurisdiction_candidate(
        division.ocdid,
        classification=classification.value,
    )

    return Jurisdiction(
        ocdid=jurisdiction_candidate.value,
        name=government.name,
        url=government.website,
        classification=classification,
        census_government_id=government.census_government_id,
        division_relationships=[
            DivisionRelationship(
                division_id=division.ocdid,
                relationship=DivisionRelationshipType.GOVERNS,
            )
        ],
        sourcing=[
            _retarget_source(
                government.source,
                [
                    "name",
                    "classification",
                    "census_government_id",
                    "url",
                    "division_relationships",
                ],
            )
        ],
        last_updated=_source_observation_time(
            government.source,
            label="government source",
        ),
    )


def build_canonical_models(
    *,
    government: GovernmentRecord,
    resolved_division: CensusDivisionRecord,
    validation: OCDIDValidationResult,
) -> CanonicalModels:
    """Build both canonical models for one verified pipeline record."""
    division = build_division(
        division=resolved_division,
        validation=validation,
    )
    jurisdiction = build_jurisdiction(
        government=government,
        division=division,
    )
    return CanonicalModels(
        division=division,
        jurisdiction=jurisdiction,
    )


def validate_canonical_models(models: CanonicalModels) -> CanonicalModels:
    """Revalidate canonical models entirely from in-memory serialized data."""
    return CanonicalModels.model_validate(models.model_dump())
