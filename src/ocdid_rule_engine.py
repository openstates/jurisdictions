"""Construct provenance-rich OCD Division ID candidates.

This stage proposes candidate OCDIDs from normalized governments and
resolved Census geography. It does not validate candidates against the
canonical Open Civic Data corpus; exact canonical validation belongs to
Phase 8.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.models.ocdid import OCDIdParsed
from src.normalize_government import GovernmentRecord, GovernmentType
from src.resolve_government import CensusDivisionRecord


RULE_VERSION = "1"


class OCDIDCandidate(BaseModel):
    """One proposed OCD Division ID plus the rule that produced it."""

    model_config = ConfigDict(frozen=True)

    value: str
    rule: str
    rule_version: str
    transformations: tuple[str, ...]
    hierarchy: tuple[str, ...]
    exception: str | None = None


def slug_segment(value: str) -> str:
    """Apply the existing simple lowercase/underscore OCD segment style."""
    return "_".join(value.strip().lower().split())


def _state_segment(government: GovernmentRecord) -> str:
    state = government.state.strip().lower()
    if not state:
        raise ValueError("government state is required for OCDID generation")
    return f"state:{state}"


def _candidate(
    *,
    hierarchy: tuple[str, ...],
    rule: str,
    transformations: tuple[str, ...],
    exception: str | None = None,
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


def _state_candidate(
    government: GovernmentRecord,
    division: CensusDivisionRecord,
) -> OCDIDCandidate:
    del division
    hierarchy = (
        "country:us",
        _state_segment(government),
    )
    return _candidate(
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
    return _candidate(
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
    return _candidate(
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
    return _candidate(
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
    return _candidate(
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
    """Generate an ordinary OCD Division ID candidate.

    Exception handling is deliberately separate and is added in Tasks
    7.4-7.5. Phase 8 determines whether the candidate is canonical.
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
