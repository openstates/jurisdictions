import socket

import pytest

from src.build_canonical_models import (
    build_canonical_models,
    build_division,
    validate_canonical_models,
)
from src.models.jurisdiction import (
    ClassificationEnum,
    DivisionRelationshipType,
)
from src.models.source import SourceObj, SourceType
from src.normalize_government import GovernmentRecord, GovernmentType
from src.ocdid_rule_engine import OCDIDCandidate
from src.ocdid_validation import (
    OCDIDValidationResult,
    OCDIDValidationStatus,
)
from src.resolve_government import CensusDivisionRecord
from src.utils.deterministic_id import generate_id


def _source(*, field: list[str], dataset: str) -> SourceObj:
    return SourceObj(
        field=field,
        source_name="U.S. Census Bureau",
        source_type=SourceType.SCRAPED,
        source_url="https://www.census.gov/",
        source_description="Controlled Phase 9 fixture",
        dataset=dataset,
        release="2026",
    )


def _government(**overrides) -> GovernmentRecord:
    values = {
        "census_government_id": "161205",
        "name": "CITY OF SAUSALITO",
        "normalized_name": "city of sausalito",
        "government_type": GovernmentType.MUNICIPAL,
        "government_subtype": "2 - MUNICIPAL",
        "state_fips": "06",
        "county_fips": "041",
        "place_fips": "70364",
        "state": "CA",
        "county_name": "MARIN",
        "website": "https://www.sausalito.gov/",
        "is_active": True,
        "source": _source(field=["government"], dataset="Government Units Survey"),
    }
    values.update(overrides)
    return GovernmentRecord(**values)


def _division(**overrides) -> CensusDivisionRecord:
    values = {
        "layer": "place",
        "geography_type": "place",
        "geoid": "0670364",
        "geoidfq": "1600000US0670364",
        "name": "Sausalito",
        "namelsad": "Sausalito city",
        "state_fips": "06",
        "county_fips": None,
        "place_fips": "70364",
        "cousub_fips": None,
        "lea": None,
        "geometry_source": _source(field=["geometry"], dataset="TIGER/Line"),
        "geometry_url": (
            "https://tigerweb.geo.census.gov/example?"
            "where=GEOID%3D'0670364'&f=geojson"
        ),
    }
    values.update(overrides)
    return CensusDivisionRecord(**values)


def _candidate(value: str) -> OCDIDCandidate:
    return OCDIDCandidate(
        value=value,
        rule="municipality.default",
        rule_version="1",
        transformations=("state_code.lower", "division_name.slug"),
        hierarchy=("country:us", "state:ca", "place:sausalito"),
    )


def _verified() -> OCDIDValidationResult:
    value = "ocd-division/country:us/state:ca/place:sausalito"
    return OCDIDValidationResult(
        status=OCDIDValidationStatus.VERIFIED,
        candidate=_candidate(value),
        canonical_ocdid=value,
        canonical_name="Sausalito",
    )


def test_build_division_uses_verified_canonical_identity() -> None:
    division = build_division(
        division=_division(),
        validation=_verified(),
    )

    assert division.ocdid == "ocd-division/country:us/state:ca/place:sausalito"
    assert division.id == generate_id(division.ocdid)
    assert division.country == "us"
    assert division.display_name == "Sausalito"
    assert division.classification == "place"
    assert division.jurisdiction_id is None


def test_build_division_carries_external_identifiers_and_geometry() -> None:
    division = build_division(
        division=_division(),
        validation=_verified(),
    )

    identifiers = {
        (identifier.authority, identifier.id_type): identifier.value
        for identifier in division.government_identifiers or []
    }
    assert identifiers == {
        ("census", "geoid"): "0670364",
        ("census", "geoidfq"): "1600000US0670364",
        ("census", "statefp"): "06",
        ("census", "placefp"): "70364",
    }

    assert len(division.geometries or []) == 1
    geometry = division.geometries[0]
    assert str(geometry.url).endswith("where=GEOID%3D%270670364%27&f=geojson")
    assert geometry.valid_from is None
    assert geometry.valid_to is None
    assert geometry.source is not None
    assert geometry.source.dataset == "TIGER/Line"


def test_build_division_preserves_distinct_tiger_names_as_aliases() -> None:
    division = build_division(
        division=_division(),
        validation=_verified(),
    )

    assert division.other_names == ["Sausalito city"]


def test_canonical_construction_rejects_quarantined_identity() -> None:
    candidate = _candidate(
        "ocd-division/country:us/state:ca/place:not_canonical"
    )
    validation = OCDIDValidationResult(
        status=OCDIDValidationStatus.QUARANTINED,
        candidate=candidate,
        canonical_ocdid=None,
        canonical_name=None,
        reason="not_in_canonical_corpus",
    )

    with pytest.raises(ValueError, match="requires a VERIFIED OCDID"):
        build_division(
            division=_division(),
            validation=validation,
        )


def test_build_jurisdiction_carries_government_identity_and_governs_edge() -> None:
    models = build_canonical_models(
        government=_government(),
        resolved_division=_division(),
        validation=_verified(),
    )

    jurisdiction = models.jurisdiction
    assert jurisdiction.ocdid == (
        "ocd-jurisdiction/country:us/state:ca/place:sausalito/government"
    )
    assert jurisdiction.id == generate_id(jurisdiction.ocdid)
    assert jurisdiction.name == "CITY OF SAUSALITO"
    assert jurisdiction.classification is ClassificationEnum.GOVERNMENT
    assert jurisdiction.census_government_id == "161205"
    assert str(jurisdiction.url) == "https://www.sausalito.gov/"
    assert len(jurisdiction.division_relationships) == 1
    assert jurisdiction.division_relationships[0].division_id == (
        "ocd-division/country:us/state:ca/place:sausalito"
    )
    assert (
        jurisdiction.division_relationships[0].relationship
        is DivisionRelationshipType.GOVERNS
    )


def test_school_government_uses_school_system_jurisdiction_classification() -> None:
    division_ocdid = (
        "ocd-division/country:us/state:tx/"
        "school_district:austin_independent_school_district"
    )
    validation = OCDIDValidationResult(
        status=OCDIDValidationStatus.VERIFIED,
        candidate=OCDIDCandidate(
            value=division_ocdid,
            rule="school.state",
            rule_version="1",
            transformations=("state_code.lower", "division_name.slug"),
            hierarchy=(
                "country:us",
                "state:tx",
                "school_district:austin_independent_school_district",
            ),
        ),
        canonical_ocdid=division_ocdid,
        canonical_name="Austin Independent School District",
    )

    models = build_canonical_models(
        government=_government(
            census_government_id="213227",
            name="AUSTIN IND SCH DIST 901",
            normalized_name="austin ind sch dist 901",
            government_type=GovernmentType.SCHOOL_DISTRICT,
            government_subtype="03 - ELEMENTARY AND SECONDARY",
            state="TX",
            state_fips="48",
            county_fips="453",
            place_fips=None,
            county_name="TRAVIS",
            website=None,
        ),
        resolved_division=_division(
            layer="school_district_unified",
            geography_type="school_district",
            geoid="4808940",
            geoidfq="9700000US4808940",
            name="Austin Independent School District",
            namelsad=None,
            state_fips="48",
            county_fips=None,
            place_fips=None,
            lea="08940",
        ),
        validation=validation,
    )

    assert models.jurisdiction.classification is ClassificationEnum.SCHOOL_SYSTEM
    assert models.jurisdiction.ocdid.endswith("/school_system")


def test_phase9_validation_round_trips_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_network(*args, **kwargs):
        raise AssertionError("Phase 9 canonical model validation made a network call")

    monkeypatch.setattr(socket, "socket", fail_network)
    monkeypatch.setattr(socket, "create_connection", fail_network)

    models = build_canonical_models(
        government=_government(),
        resolved_division=_division(),
        validation=_verified(),
    )
    restored = validate_canonical_models(models)

    assert restored.model_dump(mode="json") == models.model_dump(mode="json")


def test_unsupported_phase9_government_type_fails_closed() -> None:
    with pytest.raises(ValueError, match="no Phase 9 Jurisdiction classification"):
        build_canonical_models(
            government=_government(
                government_type=GovernmentType.SPECIAL_DISTRICT,
                government_subtype="fire protection",
            ),
            resolved_division=_division(),
            validation=_verified(),
        )
