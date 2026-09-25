import csv
from pathlib import Path

from src.models.source import SourceObj, SourceType
from src.normalize_government import (
    GovernmentRecord,
    GovernmentType,
    normalize_records,
)
from src.resolve_government import ResolutionStatus, resolve_government
from src.sources import census_gus
from src.sources.census_tiger import (
    TigerRecord,
    load_tiger_config,
    parse_csv_snapshot,
)
from src.sources.government_units import GovernmentKind
from src.sources.snapshot import load_snapshot, source_obj_from_snapshot


def _source() -> SourceObj:
    return SourceObj(
        field=["geometry"],
        source_name="Census TIGER/Line",
        source_type=SourceType.SCRAPED,
        source_url="https://www2.census.gov/geo/tiger/TIGER2025/",
        source_description="TIGER/Line geography fixture",
        dataset="TIGER/Line Shapefiles",
        release="2025",
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
        "website": "http://www.ci.sausalito.ca.us",
        "is_active": True,
        "source": _source(),
    }
    values.update(overrides)
    return GovernmentRecord(**values)


def _tiger(**overrides) -> TigerRecord:
    values = {
        "layer": "place",
        "geography": "place",
        "geoid": "0670364",
        "geoidfq": "1600000US0670364",
        "name": "Sausalito",
        "namelsad": "Sausalito city",
        "statefp": "06",
        "countyfp": None,
        "placefp": "70364",
        "cousubfp": None,
        "lea": None,
        "lsad": "25",
        "classfp": "C1",
        "funcstat": "A",
        "mtfcc": "G4110",
    }
    values.update(overrides)
    return TigerRecord(**values)


def test_state_resolves_by_state_fips():
    government = _government(
        government_type=GovernmentType.STATE,
        government_subtype="0 - STATE",
        state_fips="06",
        county_fips=None,
        place_fips=None,
    )
    tiger = _tiger(
        layer="state",
        geography="state",
        geoid="06",
        geoidfq="0400000US06",
        name="California",
        namelsad=None,
        statefp="06",
        placefp=None,
        lsad="00",
        classfp=None,
        funcstat="A",
        mtfcc="G4000",
    )

    result = resolve_government(
        government,
        [tiger],
        config=load_tiger_config(),
        tiger_source=_source(),
    )

    assert result.status is ResolutionStatus.RESOLVED
    assert result.division is not None
    assert result.division.geography_type == "state"
    assert result.division.geoid == "06"
    assert result.division.state_fips == "06"


def test_county_resolves_by_state_and_county_fips():
    government = _government(
        government_type=GovernmentType.COUNTY,
        government_subtype="1 - COUNTY",
        county_fips="041",
        place_fips=None,
    )
    tiger = _tiger(
        layer="county",
        geography="county",
        geoid="06041",
        geoidfq="0500000US06041",
        name="Marin",
        namelsad="Marin County",
        countyfp="041",
        placefp=None,
        lsad="06",
        classfp="H1",
        funcstat="A",
        mtfcc="G4020",
    )

    result = resolve_government(
        government,
        [tiger],
        config=load_tiger_config(),
        tiger_source=_source(),
    )

    assert result.status is ResolutionStatus.RESOLVED
    assert result.division is not None
    assert result.division.geography_type == "county"
    assert result.division.geoid == "06041"
    assert result.division.county_fips == "041"


def test_municipality_resolves_by_state_and_place_fips():
    result = resolve_government(
        _government(),
        [_tiger()],
        config=load_tiger_config(),
        tiger_source=_source(),
    )

    assert result.status is ResolutionStatus.RESOLVED
    assert result.division is not None
    assert result.division.layer == "place"
    assert result.division.geography_type == "place"
    assert result.division.geoid == "0670364"
    assert result.division.place_fips == "70364"


def test_municipal_identifier_join_does_not_depend_on_name_similarity():
    tiger = _tiger(
        name="A deliberately different display name",
        namelsad="A deliberately different display name city",
    )

    result = resolve_government(
        _government(),
        [tiger],
        config=load_tiger_config(),
        tiger_source=_source(),
    )

    assert result.status is ResolutionStatus.RESOLVED
    assert result.division is not None
    assert result.division.geoid == "0670364"


def test_municipality_never_matches_same_place_code_in_wrong_state():
    wrong_state = _tiger(
        geoid="4870364",
        geoidfq="1600000US4870364",
        statefp="48",
    )

    result = resolve_government(
        _government(),
        [wrong_state],
        config=load_tiger_config(),
        tiger_source=_source(),
    )

    assert result.status is ResolutionStatus.DIVISION_NOT_FOUND
    assert result.division is None


def test_municipality_does_not_resolve_to_statistical_cdp():
    cdp = _tiger(
        geoid="0670364",
        geoidfq="1600000US0670364",
        name="Sausalito",
        namelsad="Sausalito CDP",
        lsad="57",
        classfp="U1",
        funcstat="S",
    )

    result = resolve_government(
        _government(),
        [cdp],
        config=load_tiger_config(),
        tiger_source=_source(),
    )

    assert result.status is ResolutionStatus.DIVISION_NOT_FOUND
    assert result.division is None


def test_multiple_identifier_matches_are_ambiguous_not_arbitrarily_selected():
    first = _tiger()
    second = _tiger(
        geoid="0670365",
        geoidfq="1600000US0670365",
        name="Duplicate candidate",
    )

    result = resolve_government(
        _government(),
        [first, second],
        config=load_tiger_config(),
        tiger_source=_source(),
    )

    assert result.status is ResolutionStatus.AMBIGUOUS
    assert result.division is None
    assert len(result.candidates) == 2


def test_missing_required_identifier_is_division_not_found():
    government = _government(place_fips=None)

    result = resolve_government(
        government,
        [_tiger()],
        config=load_tiger_config(),
        tiger_source=_source(),
    )

    assert result.status is ResolutionStatus.DIVISION_NOT_FOUND
    assert result.division is None


def test_special_district_returns_no_geography_without_fabricating_geoid():
    government = _government(
        census_government_id="100920",
        name="SAUSALITO-MARIN CITY SANITARY DISTRICT",
        normalized_name="sausalito-marin city sanitary district",
        government_type=GovernmentType.SPECIAL_DISTRICT,
        government_subtype="80 - SEWERAGE",
        place_fips=None,
    )

    result = resolve_government(
        government,
        [_tiger()],
        config=load_tiger_config(),
        tiger_source=_source(),
    )

    assert result.status is ResolutionStatus.NO_GEOGRAPHY
    assert result.division is None
    assert result.candidates == []


def test_resolved_division_carries_tigerweb_geojson_url():
    result = resolve_government(
        _government(),
        [_tiger()],
        config=load_tiger_config(),
        tiger_source=_source(),
    )

    assert result.division is not None
    assert result.division.geometry_url == (
        "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
        "Places_CouSub_ConCity_SubMCD/MapServer/4/query?"
        "where=GEOID%3D'0670364'&outFields=*&outSR=4326&f=geojson"
    )


def test_resolved_division_carries_tiger_source_provenance():
    source = _source()

    result = resolve_government(
        _government(),
        [_tiger()],
        config=load_tiger_config(),
        tiger_source=source,
    )

    assert result.division is not None
    assert result.division.geometry_source == source


def test_wrong_geography_type_is_not_considered_a_match():
    county_shaped_record = _tiger(
        layer="county",
        geography="county",
        geoid="0670364",
        name="Not a place",
    )

    result = resolve_government(
        _government(),
        [county_shaped_record],
        config=load_tiger_config(),
        tiger_source=_source(),
    )

    assert result.status is ResolutionStatus.DIVISION_NOT_FOUND
    assert result.division is None



FIXTURES = Path("tests/fixtures")


def _fixture_governments() -> list[GovernmentRecord]:
    snapshot = load_snapshot(
        FIXTURES / "census_gus" / "gov_units_2026_general_purpose.csv"
    )
    parsed = census_gus.parse_sheet_snapshot(
        snapshot,
        GovernmentKind.GENERAL_PURPOSE,
    )
    assert parsed.metadata is not None

    source = source_obj_from_snapshot(
        parsed.metadata,
        field=["government"],
        source_description="Census government resolver input",
    )
    normalized = normalize_records(
        parsed.records,
        source=source,
        source_errors=parsed.errors,
    )

    assert normalized.source_errors == []
    return normalized.records


def _fixture_tiger(layer_key: str, filename: str):
    config = load_tiger_config()
    snapshot = load_snapshot(FIXTURES / "tiger" / filename)
    parsed = parse_csv_snapshot(snapshot, config, layer_key)

    assert parsed.metadata is not None
    assert parsed.errors == []

    source = source_obj_from_snapshot(
        parsed.metadata,
        field=["geometry"],
        source_description="TIGER geography resolver input",
    )
    return config, parsed.records, source


def test_fixture_counties_resolve_by_published_fips_identifiers():
    governments = [
        record
        for record in _fixture_governments()
        if record.government_type is GovernmentType.COUNTY
    ]
    config, tiger_records, source = _fixture_tiger(
        "county",
        "tl_2025_us_county.csv",
    )

    assert len(governments) == 4

    for government in governments:
        result = resolve_government(
            government,
            tiger_records,
            config=config,
            tiger_source=source,
        )

        assert result.status is ResolutionStatus.RESOLVED
        assert result.division is not None
        assert result.division.geoid == (
            f"{government.state_fips}{government.county_fips}"
        )


def test_fixture_active_municipalities_resolve_by_place_fips():
    expected = {
        "161205": "0670364",
        "176394": "4805000",
        "184255": "5363000",
        "176868": "5370000",
    }
    governments = {
        record.census_government_id: record
        for record in _fixture_governments()
        if record.census_government_id in expected
    }
    config, tiger_records, source = _fixture_tiger(
        "place",
        "tl_2025_place.csv",
    )

    assert governments.keys() == expected.keys()

    for census_id, geoid in expected.items():
        result = resolve_government(
            governments[census_id],
            tiger_records,
            config=config,
            tiger_source=source,
        )

        assert result.status is ResolutionStatus.RESOLVED
        assert result.division is not None
        assert result.division.geoid == geoid


def test_fixture_nonfunctioning_dc_place_is_not_resolved_as_municipality():
    government = next(
        record
        for record in _fixture_governments()
        if record.census_government_id == "124214"
    )
    config, tiger_records, source = _fixture_tiger(
        "place",
        "tl_2025_place.csv",
    )

    result = resolve_government(
        government,
        tiger_records,
        config=config,
        tiger_source=source,
    )

    assert result.status is ResolutionStatus.DIVISION_NOT_FOUND
    assert result.division is None


def test_mcd_resolves_functioning_county_subdivision_by_identifiers():
    government = _government(
        census_government_id="999001",
        name="TOWN OF EXAMPLE",
        normalized_name="town of example",
        government_type=GovernmentType.TOWNSHIP_MCD,
        government_subtype="3 - TOWNSHIP",
        state_fips="36",
        county_fips="101",
        place_fips="18256",
    )
    tiger = _tiger(
        layer="county_subdivision",
        geography="county_subdivision",
        geoid="3610118256",
        geoidfq="0600000US3610118256",
        name="Example",
        namelsad="Example town",
        statefp="36",
        countyfp="101",
        placefp=None,
        cousubfp="18256",
        lsad="43",
        classfp="T1",
        funcstat="A",
        mtfcc="G4040",
    )

    result = resolve_government(
        government,
        [tiger],
        config=load_tiger_config(),
        tiger_source=_source(),
    )

    assert result.status is ResolutionStatus.RESOLVED
    assert result.division is not None
    assert result.division.geography_type == "county_subdivision"
    assert result.division.geoid == "3610118256"
    assert result.division.cousub_fips == "18256"


def test_mcd_does_not_resolve_statistical_county_subdivision():
    government = _government(
        government_type=GovernmentType.TOWNSHIP_MCD,
        government_subtype="3 - TOWNSHIP",
        state_fips="48",
        county_fips="453",
        place_fips="90165",
    )
    statistical = _tiger(
        layer="county_subdivision",
        geography="county_subdivision",
        geoid="4845390165",
        geoidfq="0600000US4845390165",
        name="Austin",
        namelsad="Austin CCD",
        statefp="48",
        countyfp="453",
        placefp=None,
        cousubfp="90165",
        lsad="22",
        classfp="Z5",
        funcstat="S",
        mtfcc="G4040",
    )

    result = resolve_government(
        government,
        [statistical],
        config=load_tiger_config(),
        tiger_source=_source(),
    )

    assert result.status is ResolutionStatus.DIVISION_NOT_FOUND
    assert result.division is None


def test_mcd_does_not_cross_county_boundary_on_same_cousub_code():
    government = _government(
        government_type=GovernmentType.TOWNSHIP_MCD,
        government_subtype="3 - TOWNSHIP",
        state_fips="36",
        county_fips="101",
        place_fips="18256",
    )
    wrong_county = _tiger(
        layer="county_subdivision",
        geography="county_subdivision",
        geoid="3609918256",
        geoidfq="0600000US3609918256",
        name="Example",
        namelsad="Example town",
        statefp="36",
        countyfp="099",
        placefp=None,
        cousubfp="18256",
        lsad="43",
        classfp="T1",
        funcstat="A",
        mtfcc="G4040",
    )

    result = resolve_government(
        government,
        [wrong_county],
        config=load_tiger_config(),
        tiger_source=_source(),
    )

    assert result.status is ResolutionStatus.DIVISION_NOT_FOUND
    assert result.division is None


def _school_crosswalk() -> dict[str, str]:
    snapshot = load_snapshot(
        FIXTURES / "census_school_finance" / "elsec24t_2024.csv"
    )

    rows = csv.DictReader(snapshot.read_text().splitlines())
    return {
        row["PID6"]: row["NCESID"]
        for row in rows
    }


def _fixture_school_governments() -> list[GovernmentRecord]:
    snapshot = load_snapshot(
        FIXTURES / "census_gus" / "gov_units_2026_school_district.csv"
    )
    parsed = census_gus.parse_sheet_snapshot(
        snapshot,
        GovernmentKind.SCHOOL_DISTRICT,
    )
    assert parsed.metadata is not None

    source = source_obj_from_snapshot(
        parsed.metadata,
        field=["government"],
        source_description="Census school-government resolver input",
    )
    normalized = normalize_records(
        parsed.records,
        source=source,
        source_errors=parsed.errors,
    )

    assert normalized.source_errors == []
    return normalized.records


def _fixture_school_tiger_records() -> list[TigerRecord]:
    config = load_tiger_config()
    records: list[TigerRecord] = []

    for layer, filename in (
        ("school_district_elementary", "tl_2025_elsd.csv"),
        ("school_district_secondary", "tl_2025_scsd.csv"),
        ("school_district_unified", "tl_2025_unsd.csv"),
    ):
        snapshot = load_snapshot(FIXTURES / "tiger" / filename)
        parsed = parse_csv_snapshot(snapshot, config, layer)

        assert parsed.errors == []
        records.extend(parsed.records)

    return records


def test_school_resolves_by_pid6_to_ncesid_exact_geoid():
    government = _government(
        census_government_id="213227",
        name="AUSTIN IND SCH DIST 901",
        normalized_name="austin ind sch dist 901",
        government_type=GovernmentType.SCHOOL_DISTRICT,
        government_subtype="03 - ELEMENTARY AND SECONDARY",
        state_fips="48",
        county_fips="453",
        place_fips=None,
    )
    tiger = _tiger(
        layer="school_district_unified",
        geography="school_district",
        geoid="4808940",
        geoidfq="9700000US4808940",
        name="Austin Independent School District",
        namelsad=None,
        statefp="48",
        countyfp=None,
        placefp=None,
        cousubfp=None,
        lea="08940",
        lsad="00",
        classfp=None,
        funcstat="E",
        mtfcc="G5420",
    )

    result = resolve_government(
        government,
        [tiger],
        config=load_tiger_config(),
        tiger_source=_source(),
        school_nces_ids={"213227": "4808940"},
    )

    assert result.status is ResolutionStatus.RESOLVED
    assert result.division is not None
    assert result.division.geography_type == "school_district"
    assert result.division.geoid == "4808940"
    assert result.division.lea == "08940"


def test_school_name_match_cannot_override_wrong_ncesid():
    government = _government(
        census_government_id="213227",
        name="AUSTIN IND SCH DIST 901",
        normalized_name="austin ind sch dist 901",
        government_type=GovernmentType.SCHOOL_DISTRICT,
        government_subtype="03 - ELEMENTARY AND SECONDARY",
        state_fips="48",
        county_fips="453",
        place_fips=None,
    )
    wrong = _tiger(
        layer="school_district_unified",
        geography="school_district",
        geoid="4800001",
        geoidfq="9700000US4800001",
        name="AUSTIN IND SCH DIST 901",
        statefp="48",
        placefp=None,
        lea="00001",
    )

    result = resolve_government(
        government,
        [wrong],
        config=load_tiger_config(),
        tiger_source=_source(),
        school_nces_ids={"213227": "4808940"},
    )

    assert result.status is ResolutionStatus.DIVISION_NOT_FOUND
    assert result.division is None


def test_school_does_not_resolve_cross_state_geography():
    government = _government(
        census_government_id="213227",
        government_type=GovernmentType.SCHOOL_DISTRICT,
        government_subtype="03 - ELEMENTARY AND SECONDARY",
        state_fips="48",
        county_fips="453",
        place_fips=None,
    )
    wrong_state = _tiger(
        layer="school_district_unified",
        geography="school_district",
        geoid="4808940",
        geoidfq="9700000US4808940",
        name="Wrong state district",
        statefp="53",
        placefp=None,
        lea="08940",
    )

    result = resolve_government(
        government,
        [wrong_state],
        config=load_tiger_config(),
        tiger_source=_source(),
        school_nces_ids={"213227": "4808940"},
    )

    assert result.status is ResolutionStatus.DIVISION_NOT_FOUND
    assert result.division is None


def test_school_without_pid6_crosswalk_fails_closed():
    government = _government(
        census_government_id="213227",
        government_type=GovernmentType.SCHOOL_DISTRICT,
        government_subtype="03 - ELEMENTARY AND SECONDARY",
        place_fips=None,
    )

    result = resolve_government(
        government,
        _fixture_school_tiger_records(),
        config=load_tiger_config(),
        tiger_source=_source(),
        school_nces_ids={},
    )

    assert result.status is ResolutionStatus.DIVISION_NOT_FOUND
    assert result.division is None


def test_all_school_fixtures_resolve_through_official_pid6_ncesid_crosswalk():
    governments = _fixture_school_governments()
    tiger_records = _fixture_school_tiger_records()
    crosswalk = _school_crosswalk()

    expected = {
        "115874": "0636000",
        "213227": "4808940",
        "183396": "5307710",
        "203851": "5308700",
    }

    assert crosswalk == expected
    assert len(governments) == 4

    for government in governments:
        result = resolve_government(
            government,
            tiger_records,
            config=load_tiger_config(),
            tiger_source=_source(),
            school_nces_ids=crosswalk,
        )

        assert result.status is ResolutionStatus.RESOLVED
        assert result.division is not None
        assert result.division.geoid == expected[
            government.census_government_id
        ]
        assert result.division.state_fips == government.state_fips



def test_all_state_fixtures_resolve_by_state_fips():
    config, tiger_records, source = _fixture_tiger(
        "state",
        "tl_2025_us_state.csv",
    )

    expected = {
        "06": "CA",
        "11": "DC",
        "48": "TX",
        "53": "WA",
    }

    assert {record.statefp for record in tiger_records} == set(expected)

    for state_fips, state in expected.items():
        government = _government(
            census_government_id=f"state-{state_fips}",
            name=f"STATE {state}",
            normalized_name=f"state {state.lower()}",
            government_type=GovernmentType.STATE,
            government_subtype="0 - STATE",
            state_fips=state_fips,
            county_fips=None,
            place_fips=None,
            state=state,
            county_name=None,
        )

        result = resolve_government(
            government,
            tiger_records,
            config=config,
            tiger_source=source,
        )

        assert result.status is ResolutionStatus.RESOLVED
        assert result.division is not None
        assert result.division.geoid == state_fips
        assert result.division.state_fips == state_fips
        assert result.division.geography_type == "state"
