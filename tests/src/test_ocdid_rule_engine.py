import pytest
from pydantic import ValidationError

from src.models.ocdid import OCDIdParsed
from src.models.source import SourceObj, SourceType
from src.normalize_government import GovernmentRecord, GovernmentType
from src.ocdid_rule_engine import (
    ExceptionCategory,
    OCDIDCandidate,
    derive_jurisdiction_candidate,
    generate_candidate,
    slug_segment,
)
from src.resolve_government import CensusDivisionRecord


def _source() -> SourceObj:
    return SourceObj(
        field=["government"],
        source_name="U.S. Census Bureau",
        source_type=SourceType.SCRAPED,
        source_url="https://www.census.gov/",
        source_description="Controlled test source",
        dataset="test",
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
        "website": None,
        "is_active": True,
        "source": _source(),
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
        "geometry_source": _source(),
        "geometry_url": (
            "https://tigerweb.geo.census.gov/example?"
            "where=GEOID%3D'0670364'&f=geojson"
        ),
    }
    values.update(overrides)
    return CensusDivisionRecord(**values)


def test_slug_segment_preserves_existing_simple_slug_behavior():
    assert slug_segment("Sausalito") == "sausalito"
    assert slug_segment("Marin City") == "marin_city"
    assert slug_segment("  New   York  ") == "new_york"


def test_candidate_structure_is_frozen_and_carries_provenance():
    candidate = OCDIDCandidate(
        value="ocd-division/country:us/state:ca/place:sausalito",
        rule="municipality.default",
        rule_version="1",
        transformations=("state_code.lower", "division_name.slug"),
        hierarchy=("country:us", "state:ca", "place:sausalito"),
        exception=None,
    )

    assert candidate.rule == "municipality.default"
    assert candidate.rule_version == "1"
    assert candidate.exception is None

    with pytest.raises(ValidationError):
        candidate.rule = "changed"


def test_state_candidate():
    candidate = generate_candidate(
        _government(
            government_type=GovernmentType.STATE,
            government_subtype="0 - STATE",
            state="CA",
            county_fips=None,
            place_fips=None,
        ),
        _division(
            layer="state",
            geography_type="state",
            geoid="06",
            geoidfq="0400000US06",
            name="California",
            namelsad=None,
            place_fips=None,
        ),
    )

    assert candidate.value == "ocd-division/country:us/state:ca"
    assert candidate.rule == "state.default"
    assert candidate.rule_version == "1"
    assert candidate.hierarchy == ("country:us", "state:ca")
    assert candidate.exception is None


def test_county_candidate():
    candidate = generate_candidate(
        _government(
            government_type=GovernmentType.COUNTY,
            government_subtype="1 - COUNTY",
            county_fips="041",
            place_fips=None,
        ),
        _division(
            layer="county",
            geography_type="county",
            geoid="06041",
            geoidfq="0500000US06041",
            name="Marin",
            namelsad="Marin County",
            county_fips="041",
            place_fips=None,
        ),
    )

    assert candidate.value == (
        "ocd-division/country:us/state:ca/county:marin"
    )
    assert candidate.rule == "county.default"
    assert candidate.hierarchy == (
        "country:us",
        "state:ca",
        "county:marin",
    )


def test_municipal_candidate_uses_resolved_division_name():
    government = _government(
        name="CITY OF SAUSALITO",
        normalized_name="city of sausalito",
    )

    candidate = generate_candidate(government, _division(name="Sausalito"))

    assert candidate.value == (
        "ocd-division/country:us/state:ca/place:sausalito"
    )
    assert candidate.rule == "municipality.default"
    assert candidate.transformations == (
        "state_code.lower",
        "division_name.slug",
    )


def test_mcd_candidate_uses_civic_place_segment_not_census_geography_name():
    candidate = generate_candidate(
        _government(
            census_government_id="999001",
            name="TOWN OF EXAMPLE",
            normalized_name="town of example",
            government_type=GovernmentType.TOWNSHIP_MCD,
            government_subtype="3 - TOWNSHIP",
            state="NY",
            state_fips="36",
            county_fips="101",
            place_fips="18256",
            county_name="STEUBEN",
        ),
        _division(
            layer="county_subdivision",
            geography_type="county_subdivision",
            geoid="3610118256",
            geoidfq="0600000US3610118256",
            name="Example",
            namelsad="Example town",
            state_fips="36",
            county_fips="101",
            place_fips=None,
            cousub_fips="18256",
        ),
    )

    assert candidate.value == (
        "ocd-division/country:us/state:ny/"
        "county:steuben/place:example"
    )
    assert candidate.rule == "mcd.civic_place"
    assert candidate.hierarchy == (
        "country:us",
        "state:ny",
        "county:steuben",
        "place:example",
    )


def test_school_candidate_is_state_scoped_and_uses_school_district_segment():
    candidate = generate_candidate(
        _government(
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
        ),
        _division(
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
    )

    assert candidate.value == (
        "ocd-division/country:us/state:tx/"
        "school_district:austin_independent_school_district"
    )
    assert candidate.rule == "school.state"
    assert candidate.hierarchy == (
        "country:us",
        "state:tx",
        "school_district:austin_independent_school_district",
    )


@pytest.mark.parametrize(
    "government_type",
    [
        GovernmentType.STATE,
        GovernmentType.COUNTY,
        GovernmentType.MUNICIPAL,
        GovernmentType.TOWNSHIP_MCD,
        GovernmentType.SCHOOL_DISTRICT,
    ],
)
def test_every_ordinary_candidate_round_trips_through_authorized_parser(
    government_type,
):
    if government_type is GovernmentType.STATE:
        government = _government(
            government_type=government_type,
            state="CA",
            county_fips=None,
            place_fips=None,
        )
        division = _division(
            geography_type="state",
            name="California",
            geoid="06",
            place_fips=None,
        )
    elif government_type is GovernmentType.COUNTY:
        government = _government(
            government_type=government_type,
            county_fips="041",
            place_fips=None,
        )
        division = _division(
            geography_type="county",
            name="Marin",
            geoid="06041",
            county_fips="041",
            place_fips=None,
        )
    elif government_type is GovernmentType.TOWNSHIP_MCD:
        government = _government(
            government_type=government_type,
            state="NY",
            state_fips="36",
            county_fips="101",
            county_name="STEUBEN",
            place_fips="18256",
        )
        division = _division(
            geography_type="county_subdivision",
            name="Example",
            geoid="3610118256",
            state_fips="36",
            county_fips="101",
            place_fips=None,
            cousub_fips="18256",
        )
    elif government_type is GovernmentType.SCHOOL_DISTRICT:
        government = _government(
            government_type=government_type,
            state="TX",
            state_fips="48",
            place_fips=None,
        )
        division = _division(
            geography_type="school_district",
            name="Austin Independent School District",
            geoid="4808940",
            state_fips="48",
            place_fips=None,
            lea="08940",
        )
    else:
        government = _government()
        division = _division()

    candidate = generate_candidate(government, division)
    parsed = OCDIdParsed.parse_ocdid(candidate.value)

    assert parsed.raw_ocdid == candidate.value
    assert parsed.type == "ocd-division"


def test_exception_categories_are_explicit():
    assert {category.value for category in ExceptionCategory} == {
        "identifier_override",
        "hierarchy_override",
        "slug_name_override",
        "geography_mapping_override",
    }


def test_dc_state_exception_beats_general_state_rule():
    candidate = generate_candidate(
        _government(
            census_government_id="000011",
            name="DISTRICT OF COLUMBIA",
            normalized_name="district of columbia",
            government_type=GovernmentType.STATE,
            government_subtype="0 - STATE",
            state="DC",
            state_fips="11",
            county_fips=None,
            place_fips=None,
            county_name=None,
        ),
        _division(
            layer="state",
            geography_type="state",
            geoid="11",
            geoidfq="0400000US11",
            name="District of Columbia",
            namelsad=None,
            state_fips="11",
            county_fips=None,
            place_fips=None,
        ),
    )

    assert candidate.value == "ocd-division/country:us/district:dc"
    assert candidate.rule == "state.dc"
    assert candidate.rule_version == "1"
    assert candidate.exception is not None
    assert candidate.exception.name == "dc.district_segment"
    assert candidate.exception.category is ExceptionCategory.HIERARCHY_OVERRIDE


def test_normal_state_does_not_receive_dc_exception():
    candidate = generate_candidate(
        _government(
            government_type=GovernmentType.STATE,
            state="CA",
            county_fips=None,
            place_fips=None,
        ),
        _division(
            geography_type="state",
            geoid="06",
            name="California",
            place_fips=None,
        ),
    )

    assert candidate.value == "ocd-division/country:us/state:ca"
    assert candidate.rule == "state.default"
    assert candidate.exception is None


def test_council_district_inherits_parent_jurisdiction():
    candidate = derive_jurisdiction_candidate(
        "ocd-division/country:us/state:wa/"
        "place:seattle/council_district:1"
    )

    assert candidate.value == (
        "ocd-jurisdiction/country:us/state:wa/place:seattle/government"
    )
    assert candidate.rule == "jurisdiction.parent_inheritance"
    assert candidate.exception is not None
    assert candidate.exception.name == "council_district.parent_jurisdiction"
    assert candidate.exception.category is ExceptionCategory.HIERARCHY_OVERRIDE
    assert candidate.transformations == (
        "division_ocdid.parse",
        "council_district.strip",
        "jurisdiction_namespace",
        "classification.append",
    )


def test_dc_anc_council_district_retains_canonical_parent_hierarchy():
    candidate = derive_jurisdiction_candidate(
        "ocd-division/country:us/district:dc/"
        "anc:1a/council_district:1"
    )

    assert candidate.value == (
        "ocd-jurisdiction/country:us/district:dc/anc:1a/government"
    )
    assert candidate.exception is not None
    assert candidate.exception.category is ExceptionCategory.HIERARCHY_OVERRIDE

    parsed = OCDIdParsed.parse_ocdid(candidate.value)
    assert parsed.raw_ocdid == candidate.value


def test_regular_division_derives_default_jurisdiction_without_exception():
    candidate = derive_jurisdiction_candidate(
        "ocd-division/country:us/state:ca/place:sausalito"
    )

    assert candidate.value == (
        "ocd-jurisdiction/country:us/state:ca/place:sausalito/government"
    )
    assert candidate.rule == "jurisdiction.default"
    assert candidate.exception is None
    assert candidate.transformations == (
        "division_ocdid.parse",
        "jurisdiction_namespace",
        "classification.append",
    )


def test_jurisdiction_candidate_preserves_requested_classification():
    candidate = derive_jurisdiction_candidate(
        "ocd-division/country:us/state:tx/place:austin",
        classification="legislature",
    )

    assert candidate.value == (
        "ocd-jurisdiction/country:us/state:tx/place:austin/legislature"
    )
    assert candidate.hierarchy == (
        "country:us",
        "state:tx",
        "place:austin",
        "legislature",
    )


def test_exception_provenance_is_frozen():
    candidate = derive_jurisdiction_candidate(
        "ocd-division/country:us/state:wa/"
        "place:seattle/council_district:1"
    )

    assert candidate.exception is not None

    with pytest.raises(ValidationError):
        candidate.exception.name = "changed"
