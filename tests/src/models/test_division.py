from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from hypothesis import given
from hypothesis import strategies as st

from src.models.division import Division, Identifier, find_identifier
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
