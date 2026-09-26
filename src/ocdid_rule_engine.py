"""Construct provenance-rich OCD ID candidates.

This stage proposes candidate OCDIDs from normalized governments and
resolved Census geography. It does not validate candidates against the
canonical Open Civic Data corpus; exact canonical validation belongs to
Phase 8.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from src.models.ocdid import OCDIdParsed
from src.normalize_government import GovernmentRecord, GovernmentType
from src.resolve_government import CensusDivisionRecord


RULE_VERSION = "1"


class ExceptionCategory(str, Enum):
    """Supported categories of explicit OCDID exceptions."""

    IDENTIFIER_OVERRIDE = "identifier_override"
    HIERARCHY_OVERRIDE = "hierarchy_override"
    SLUG_NAME_OVERRIDE = "slug_name_override"
    GEOGRAPHY_MAPPING_OVERRIDE = "geography_mapping_override"


class OCDIDException(BaseModel):
    """Provenance for an explicit exception applied to a candidate."""

    model_config = ConfigDict(frozen=True)

    name: str
    category: ExceptionCategory
    version: str = RULE_VERSION


class OCDIDCandidate(BaseModel):
    """One proposed OCD ID plus the rule and transformations that produced it."""

    model_config = ConfigDict(frozen=True)

    value: str
    rule: str
    rule_version: str
    transformations: tuple[str, ...]
    hierarchy: tuple[str, ...]
    exception: OCDIDException | None = None


def slug_segment(value: str) -> str:
    """Apply the existing simple lowercase/underscore OCD segment style."""
    return "_".join(value.strip().lower().split())


def _state_segment(government: GovernmentRecord) -> str:
    state = government.state.strip().lower()
    if not state:
        raise ValueError("government state is required for OCDID generation")
    return f"state:{state}"


def _division_candidate(
    *,
    hierarchy: tuple[str, ...],
    rule: str,
    transformations: tuple[str, ...],
    exception: OCDIDException | None = None,
) -> OCDIDCandidate:
    value = "ocd-division/" + "/".join(hierarchy)

    # Root policy requires OCD IDs to pass through the authorized parser.
    OCDIdParsed.parse_ocdid(value)

    return OCDIDCandidate(
        value=value,
        rule=rule,
        rule_version=RULE_VERSION,
        transformations=transformations,
        hierarchy=hierarchy,
        exception=exception,
    )


def _jurisdiction_candidate(
    *,
    hierarchy: tuple[str, ...],
    rule: str,
    transformations: tuple[str, ...],
    exception: OCDIDException | None = None,
) -> OCDIDCandidate:
    value = "ocd-jurisdiction/" + "/".join(hierarchy)

    OCDIdParsed.parse_ocdid(value)

    return OCDIDCandidate(
        value=value,
        rule=rule,
        rule_version=RULE_VERSION,
        transformations=transformations,
        hierarchy=hierarchy,
        exception=exception,
    )


def _state_candidate(
    government: GovernmentRecord,
    division: CensusDivisionRecord,
) -> OCDIDCandidate:
    del division

    # Washington, DC is represented canonically with a district segment,
    # not the general state segment that its Census state-equivalent record
    # would otherwise produce.
    if government.state.strip().upper() == "DC":
        return _division_candidate(
            hierarchy=(
                "country:us",
                "district:dc",
            ),
            rule="state.dc",
            transformations=(
                "state_code.lower",
                "state_segment.to_district",
            ),
            exception=OCDIDException(
                name="dc.district_segment",
                category=ExceptionCategory.HIERARCHY_OVERRIDE,
            ),
        )

    hierarchy = (
        "country:us",
        _state_segment(government),
    )
    return _division_candidate(
        hierarchy=hierarchy,
        rule="state.default",
        transformations=("state_code.lower",),
    )


def _county_candidate(
    government: GovernmentRecord,
    division: CensusDivisionRecord,
) -> OCDIDCandidate:
    county = slug_segment(division.name)
    if not county:
        raise ValueError("resolved county name is required for OCDID generation")

    hierarchy = (
        "country:us",
        _state_segment(government),
        f"county:{county}",
    )
    return _division_candidate(
        hierarchy=hierarchy,
        rule="county.default",
        transformations=(
            "state_code.lower",
            "division_name.slug",
        ),
    )


def _municipal_candidate(
    government: GovernmentRecord,
    division: CensusDivisionRecord,
) -> OCDIDCandidate:
    place = slug_segment(division.name)
    if not place:
        raise ValueError("resolved place name is required for OCDID generation")

    hierarchy = (
        "country:us",
        _state_segment(government),
        f"place:{place}",
    )
    return _division_candidate(
        hierarchy=hierarchy,
        rule="municipality.default",
        transformations=(
            "state_code.lower",
            "division_name.slug",
        ),
    )


def _mcd_candidate(
    government: GovernmentRecord,
    division: CensusDivisionRecord,
) -> OCDIDCandidate:
    if not government.county_name:
        raise ValueError("county name is required for MCD OCDID generation")

    county = slug_segment(government.county_name)
    place = slug_segment(division.name)

    if not county or not place:
        raise ValueError("county and resolved MCD names are required")

    # Census geography is a county subdivision, but existing U.S. civic OCD
    # identifiers represent functioning towns/townships as place segments.
    hierarchy = (
        "country:us",
        _state_segment(government),
        f"county:{county}",
        f"place:{place}",
    )
    return _division_candidate(
        hierarchy=hierarchy,
        rule="mcd.civic_place",
        transformations=(
            "state_code.lower",
            "county_name.slug",
            "division_name.slug",
        ),
    )


def _school_candidate(
    government: GovernmentRecord,
    division: CensusDivisionRecord,
) -> OCDIDCandidate:
    school = slug_segment(division.name)
    if not school:
        raise ValueError(
            "resolved school district name is required for OCDID generation"
        )

    hierarchy = (
        "country:us",
        _state_segment(government),
        f"school_district:{school}",
    )
    return _division_candidate(
        hierarchy=hierarchy,
        rule="school.state",
        transformations=(
            "state_code.lower",
            "division_name.slug",
        ),
    )


def generate_candidate(
    government: GovernmentRecord,
    division: CensusDivisionRecord,
) -> OCDIDCandidate:
    """Generate an OCD Division ID candidate.

    Explicit exceptions are evaluated before the corresponding general
    behavior. Phase 8 determines whether the resulting candidate is canonical.
    """
    if government.government_type is GovernmentType.STATE:
        return _state_candidate(government, division)

    if government.government_type is GovernmentType.COUNTY:
        return _county_candidate(government, division)

    if government.government_type is GovernmentType.MUNICIPAL:
        return _municipal_candidate(government, division)

    if government.government_type is GovernmentType.TOWNSHIP_MCD:
        return _mcd_candidate(government, division)

    if government.government_type is GovernmentType.SCHOOL_DISTRICT:
        return _school_candidate(government, division)

    raise ValueError(
        f"no ordinary OCDID rule for government type "
        f"{government.government_type.value!r}"
    )


def derive_jurisdiction_candidate(
    division_ocdid: str,
    *,
    classification: str = "government",
) -> OCDIDCandidate:
    """Derive a jurisdiction OCDID from an authorized parsed division OCDID.

    Council districts are representation subdivisions whose governing
    jurisdiction belongs to the parent division. The exception is explicit and
    provenance-bearing instead of being implemented by duplicated regexes.
    """
    parsed = OCDIdParsed.parse_ocdid(division_ocdid)

    if parsed.type != "ocd-division":
        raise ValueError("jurisdiction candidates require an ocd-division input")

    parts = parsed.get_ocdid_parts()
    hierarchy = tuple(parts[1:])

    if hierarchy and hierarchy[-1].startswith("council_district:"):
        hierarchy = hierarchy[:-1] + (classification,)
        return _jurisdiction_candidate(
            hierarchy=hierarchy,
            rule="jurisdiction.parent_inheritance",
            transformations=(
                "division_ocdid.parse",
                "council_district.strip",
                "jurisdiction_namespace",
                "classification.append",
            ),
            exception=OCDIDException(
                name="council_district.parent_jurisdiction",
                category=ExceptionCategory.HIERARCHY_OVERRIDE,
            ),
        )

    hierarchy = hierarchy + (classification,)
    return _jurisdiction_candidate(
        hierarchy=hierarchy,
        rule="jurisdiction.default",
        transformations=(
            "division_ocdid.parse",
            "jurisdiction_namespace",
            "classification.append",
        ),
    )
