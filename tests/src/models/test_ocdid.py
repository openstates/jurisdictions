import pytest
from pydantic import ValidationError

from src.errors import OCDIdParsingError
from src.models.ocdid import OCDIdStr, OCDIdParsed, get_ocdid_type, validate_ocdid


def test_validate_ocdid_accepts_division_prefix() -> None:
    ocdid = "ocd-division/country:us/state:wa/place:seattle"

    assert validate_ocdid(ocdid) == ocdid


def test_validate_ocdid_accepts_jurisdiction_prefix() -> None:
    ocdid = "ocd-jurisdiction/country:us/state:wa/place:seattle/government"

    assert validate_ocdid(ocdid) == ocdid


def test_validate_ocdid_accepts_non_us_country_root() -> None:
    ocdid = "ocd-division/country:ca"

    assert validate_ocdid(ocdid) == ocdid


def test_validate_ocdid_rejects_invalid_prefix() -> None:
    with pytest.raises(ValueError, match="must start with"):
        validate_ocdid("country:us/state:wa/place:seattle")


def test_validate_ocdid_rejects_malformed_country_root() -> None:
    with pytest.raises(ValueError, match="must have at least two segments"):
        validate_ocdid("ocd-division/country:")


def test_get_ocdid_type_returns_division_type() -> None:
    ocdid: OCDIdStr = validate_ocdid("ocd-division/country:us/state:wa/place:seattle")

    assert get_ocdid_type(ocdid) == "ocd-division"


def test_get_ocdid_type_returns_jurisdiction_type() -> None:
    ocdid: OCDIdStr = validate_ocdid(
        "ocd-jurisdiction/country:us/state:wa/place:seattle/government"
    )

    assert get_ocdid_type(ocdid) == "ocd-jurisdiction"


def test_ocdid_parsed_populates_type_from_raw_ocdid() -> None:
    parsed = OCDIdParsed(
        country="us",
        state="wa",
        place="seattle",
        raw_ocdid="ocd-division/country:us/state:wa/place:seattle",
    )

    assert parsed.type == "ocd-division"


def test_ocdid_parsed_accepts_jurisdiction_type_from_raw_ocdid() -> None:
    parsed = OCDIdParsed(
        country="us",
        state="wa",
        place="seattle",
        raw_ocdid="ocd-jurisdiction/country:us/state:wa/place:seattle/government",
    )

    assert parsed.type == "ocd-jurisdiction"


def test_ocdid_parsed_rejects_mismatched_type() -> None:
    with pytest.raises(ValidationError, match="must match the raw_ocdid prefix"):
        OCDIdParsed(
            type="ocd-jurisdiction",
            country="us",
            state="wa",
            place="seattle",
            raw_ocdid="ocd-division/country:us/state:wa/place:seattle",
        )


def test_parse_ocdid_returns_parsed_model_for_division() -> None:
    parsed = OCDIdParsed.parse_ocdid("ocd-division/country:us/state:wa/place:seattle")

    assert parsed.type == "ocd-division"
    assert parsed.country == "us"
    assert parsed.state == "wa"
    assert parsed.place == "seattle"


def test_parse_ocdid_raises_for_jurisdiction_shape() -> None:
    with pytest.raises(OCDIdParsingError):
        OCDIdParsed.parse_ocdid(
            "ocd-jurisdiction/country:us/state:wa/place:seattle/government"
        )


def test_get_last_segment_accepts_model_instance() -> None:
    parsed = OCDIdParsed(
        country="us",
        state="wa",
        place="seattle",
        raw_ocdid="ocd-division/country:us/state:wa/place:seattle",
    )

    assert OCDIdParsed.get_last_segment(parsed) == "place:seattle"


def test_get_last_segment_accepts_validated_string() -> None:
    ocdid: OCDIdStr = validate_ocdid(
        "ocd-jurisdiction/country:us/state:wa/place:seattle/government"
    )

    assert OCDIdParsed.get_last_segment(ocdid) == "government"


def test_build_ancestor_ocdids_returns_intermediate_divisions() -> None:
    parsed = OCDIdParsed(
        country="us",
        state="wa",
        county="king",
        place="seattle",
        raw_ocdid="ocd-division/country:us/state:wa/county:king/place:seattle",
    )

    ancestors = OCDIdParsed.build_ancestor_ocdids(parsed)

    assert [ancestor.raw_ocdid for ancestor in ancestors] == [
        "ocd-division/country:us/state:wa",
        "ocd-division/country:us/state:wa/county:king",
    ]
    assert all(ancestor.type == "ocd-division" for ancestor in ancestors)