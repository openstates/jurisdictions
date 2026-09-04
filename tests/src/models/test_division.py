from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from hypothesis import given
from hypothesis import strategies as st

from src.models.division import (
    Boundary,
    Centroid,
    Division,
    Extent,
    Geometry,
    Identifier,
    find_identifier,
    sort_geometries,
)
from src.models.source import SourceObj, SourceType


@st.composite
def division_ocdid_strategy(draw) -> str:
    state = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=2, max_size=2))
    place = draw(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=3, max_size=12)
    )
    return f"ocd-division/country:us/state:{state}/place:{place}"


def _build_division(ocdid: str, id_value=None) -> Division:
    kwargs = {
        "ocdid": ocdid,
        "country": "us",
        "display_name": "Sample Division",
        "jurisdiction_id": "ocd-jurisdiction/country:us/state:wa/place:seattle/government",
    }
    if id_value is not None:
        kwargs["id"] = id_value
    return Division(**kwargs)


def _sample_source() -> SourceObj:
    return SourceObj(
        field=["government_identifiers"],
        source_name="civicdata.tech",
        source_url={"url": "https://example.test/civicdata"},
        source_type=SourceType.HUMAN,
        source_description=None,
    )


@given(ocdid=division_ocdid_strategy())
def test_division_id_defaults_to_uuid5_from_ocdid_and_date(ocdid: str) -> None:
    last_updated = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    division = Division(
        ocdid=ocdid,
        country="us",
        display_name="Sample Division",
        jurisdiction_id="ocd-jurisdiction/country:us/state:wa/place:seattle/government",
        last_updated=last_updated,
    )
    expected = uuid5(NAMESPACE_URL, f"{ocdid}|{last_updated.date().isoformat()}")

    assert division.id == expected


def test_division_accepts_explicit_id() -> None:
    explicit_id = uuid4()
    division = _build_division(
        "ocd-division/country:us/state:wa/place:seattle", id_value=explicit_id
    )
    assert division.id == explicit_id


def test_identifier_json_round_trip_preserves_leading_zeros() -> None:
    """Serialization round-trip must preserve leading-zero identifier values.

    Regression guard for rework §22 — Census FIPS, GEOID, and SLD district
    codes are strings that carry leading zeros; the Identifier model must
    keep them intact through model_dump_json → model_validate_json.
    """
    source = _sample_source()
    leading_zero_values = {
        "statefp": "06",
        "placefp": "06000",
        "cousubfp": "00000",
        "sldust": "002",
        "geoid": "0670364",
    }
    for id_type, value in leading_zero_values.items():
        ident = Identifier(
            authority="census", id_type=id_type, value=value, source=source
        )
        payload = ident.model_dump_json()
        restored = Identifier.model_validate_json(payload)

        assert restored.value == value, (
            f"{id_type} lost leading zero on round-trip: "
            f"{value!r} -> {restored.value!r}"
        )
        assert isinstance(restored.value, str)


def test_identifier_rejects_missing_source() -> None:
    """Every identifier must carry provenance."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Identifier(authority="census", id_type="geoid", value="0670364")


def test_find_identifier_returns_first_match_by_authority_and_type() -> None:
    source = _sample_source()
    identifiers = [
        Identifier(authority="census", id_type="statefp", value="06", source=source),
        Identifier(
            authority="census", id_type="countyfp", value="041", source=source
        ),
        Identifier(
            authority="census", id_type="countyfp", value="075", source=source
        ),
        Identifier(
            authority="dcgis", id_type="anc_id", value="1A", source=source
        ),
    ]

    assert find_identifier(identifiers, "statefp") == "06"
    assert find_identifier(identifiers, "countyfp") == "041"
    assert find_identifier(identifiers, "anc_id", authority="dcgis") == "1A"
    assert find_identifier(identifiers, "missing_type") is None
    assert find_identifier(None, "statefp") is None
    assert find_identifier([], "statefp") is None


def _geometry_source() -> SourceObj:
    return SourceObj(
        field=["geometries"],
        source_name="Census TIGER/Line",
        source_url={"url": "https://example.test/tiger"},
        source_type=SourceType.HUMAN,
        source_description=None,
    )


def test_geometry_json_round_trip_is_lossless() -> None:
    """Geometry must serialize and deserialize without loss (rework §18)."""
    source = _geometry_source()
    geometry = Geometry(
        valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        valid_to=datetime(2023, 12, 31, tzinfo=timezone.utc),
        boundary=Boundary(
            centroid=Centroid(coordinates=[-122.4853, 37.8591]),
            extent=Extent(extent=[-122.51, 37.84, -122.46, 37.87]),
        ),
        url="https://example.test/boundaries/query?where=GEOID%3D%270670364%27&f=geojson",
        identifiers=[
            Identifier(
                authority="census", id_type="geoid", value="0670364", source=source
            )
        ],
        source=source,
    )

    restored = Geometry.model_validate_json(geometry.model_dump_json())

    assert restored == geometry
    assert restored.valid_from == geometry.valid_from
    assert restored.valid_to == geometry.valid_to
    assert restored.identifiers[0].value == "0670364"
    assert restored.source == source


def test_geometry_validity_window_accepts_none() -> None:
    """Open-ended validity ranges are legal on both ends (rework §20, §21)."""
    geometry = Geometry(boundary=Boundary())

    assert geometry.valid_from is None
    assert geometry.valid_to is None

    restored = Geometry.model_validate_json(geometry.model_dump_json())
    assert restored.valid_from is None
    assert restored.valid_to is None

    open_ended_end = Geometry(
        boundary=Boundary(), valid_from=datetime(2024, 1, 1, tzinfo=timezone.utc)
    )
    assert open_ended_end.valid_to is None


def test_division_geometry_versions_sort_by_valid_from() -> None:
    """Multiple geometry versions coexist on one Division and order by valid_from."""
    current = Geometry(
        boundary=Boundary(), valid_from=datetime(2024, 1, 1, tzinfo=timezone.utc)
    )
    historic = Geometry(
        boundary=Boundary(),
        valid_from=datetime(2010, 1, 1, tzinfo=timezone.utc),
        valid_to=datetime(2023, 12, 31, tzinfo=timezone.utc),
    )
    unbounded = Geometry(boundary=Boundary(), valid_to=datetime(2009, 12, 31, tzinfo=timezone.utc))

    division = Division(
        ocdid="ocd-division/country:us/state:ca/place:sausalito",
        country="us",
        display_name="Sausalito",
        jurisdiction_id="ocd-jurisdiction/country:us/state:ca/place:sausalito/government",
        geometries=[current, unbounded, historic],
    )

    assert sort_geometries(division.geometries) == [unbounded, historic, current]
    assert sort_geometries(None) == []
    assert sort_geometries([]) == []


def test_geometry_url_is_provider_neutral() -> None:
    """Any http(s) provider is valid — nothing requires a TIGERweb URL (rework §18)."""
    non_census_urls = [
        "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/MapServer/54/query?f=geojson",
        "https://services.arcgis.com/0L95CJ0VTaxqcmED/ArcGIS/rest/services/districts/0/query",
        "https://data.example.gov/boundaries/city.geojson",
        "http://legacy.example.org/shapes.json",
    ]
    for url in non_census_urls:
        geometry = Geometry(boundary=Boundary(), url=url)
        assert geometry.url is not None
        assert not str(geometry.url).startswith("https://tigerweb.geo.census.gov")


def test_division_children_lists_child_division_ids() -> None:
    """Parent→child Division links survive a round-trip (rework §26 PARENT_OF)."""
    child_ids = [
        "ocd-division/country:us/state:ca/place:sausalito/council_district:1",
        "ocd-division/country:us/state:ca/place:sausalito/council_district:2",
    ]
    division = Division(
        ocdid="ocd-division/country:us/state:ca/place:sausalito",
        country="us",
        display_name="Sausalito",
        jurisdiction_id="ocd-jurisdiction/country:us/state:ca/place:sausalito/government",
        children=child_ids,
    )

    restored = Division.model_validate_json(division.model_dump_json())

    assert restored.children == child_ids
    assert all(isinstance(child, str) for child in restored.children)


def test_division_children_defaults_to_empty_list() -> None:
    """A Division with no known children serializes an empty list, not null."""
    division = _build_division("ocd-division/country:us/state:wa/place:tacoma")

    assert division.children == []
    assert division.model_dump(mode="json")["children"] == []


def test_division_children_rejects_malformed_ocdids() -> None:
    """Child ids are validated as OCDids, not accepted as arbitrary strings."""
    import pytest
    from pydantic import ValidationError

    for bad_child in [
        "sausalito",
        "country:us/state:ca/place:sausalito",
        "ocd-divison/country:us/state:ca/place:sausalito",
        "",
    ]:
        with pytest.raises(ValidationError):
            Division(
                ocdid="ocd-division/country:us/state:ca/place:sausalito",
                country="us",
                display_name="Sausalito",
                jurisdiction_id="ocd-jurisdiction/country:us/state:ca/place:sausalito/government",
                children=[bad_child],
            )
