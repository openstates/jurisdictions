import pytest

from src.init_migration.jurisdiction_seed import (
    derive_jurisdiction_ocdid,
    infer_jurisdiction_seed,
)
from src.models.jurisdiction import ClassificationEnum


def test_infer_jurisdiction_seed_rejects_unknown_lsad_code() -> None:
    with pytest.raises(ValueError, match="Unknown LSAD code 'ZZ'"):
        infer_jurisdiction_seed(
            "ocd-division/country:us/state:ca/place:seattle",
            lsad_code="ZZ",
        )


def test_infer_jurisdiction_seed_treats_cdp_lsad_as_statistical() -> None:
    seed = infer_jurisdiction_seed(
        "ocd-division/country:us/state:ca/place:seattle",
        lsad_code="57",
    )

    assert seed.has_jurisdiction is False
    assert seed.reason == "statistical geography"


def test_infer_jurisdiction_seed_keeps_parish_lsad_as_governing() -> None:
    seed = infer_jurisdiction_seed(
        "ocd-division/country:us/state:la/county:orleans",
        lsad_code="15",
    )

    assert seed.has_jurisdiction is True
    assert seed.classification == ClassificationEnum.GOVERNMENT.value
    assert seed.reason == "general government fallback"


def test_infer_jurisdiction_seed_keeps_census_area_lsad_statistical() -> None:
    seed = infer_jurisdiction_seed(
        "ocd-division/country:us/state:ak/county:yukon_koyukuk",
        lsad_code="05",
    )

    assert seed.has_jurisdiction is False
    assert seed.reason == "statistical geography"


def test_derive_jurisdiction_ocdid_from_standard_division() -> None:
    """A division with no non-parent segment maps to itself."""
    result = derive_jurisdiction_ocdid(
        "ocd-division/country:us/state:ca/place:seattle",
        classification="government",
    )

    assert result == "ocd-jurisdiction/country:us/state:ca/place:seattle/government"


def test_derive_jurisdiction_ocdid_uses_given_classification() -> None:
    division_ocdid = "ocd-division/country:us/state:ca"

    result_gov = derive_jurisdiction_ocdid(division_ocdid, classification="government")
    result_leg = derive_jurisdiction_ocdid(division_ocdid, classification="legislature")

    assert result_gov.endswith("/government")
    assert result_leg.endswith("/legislature")


def test_derive_jurisdiction_ocdid_defaults_to_government() -> None:
    """DivGenerator relies on the default when it has no classification."""
    result = derive_jurisdiction_ocdid("ocd-division/country:us/state:ca/place:seattle")

    assert result.endswith("/government")


def test_derive_jurisdiction_ocdid_removes_council_district() -> None:
    """A council district's jurisdiction belongs to its parent place."""
    result = derive_jurisdiction_ocdid(
        "ocd-division/country:us/state:ca/place:seattle/council_district:1",
        classification="government",
    )

    assert result == "ocd-jurisdiction/country:us/state:ca/place:seattle/government"


def test_derive_jurisdiction_ocdid_removes_ward() -> None:
    """A ward's jurisdiction belongs to its parent place, same as a council district."""
    result = derive_jurisdiction_ocdid(
        "ocd-division/country:us/state:oh/place:cincinnati/ward:1",
        classification="government",
    )

    assert result == "ocd-jurisdiction/country:us/state:oh/place:cincinnati/government"


def test_derive_jurisdiction_ocdid_dedupes_wards_of_one_place() -> None:
    """Every ward of a place must resolve to the same jurisdiction ocdid.

    This is what lets _jurisdiction_exists() skip creating a duplicate: 26
    Cincinnati wards should produce one Cincinnati government, not 26.
    """
    derived = {
        derive_jurisdiction_ocdid(
            f"ocd-division/country:us/state:oh/place:cincinnati/ward:{n}"
        )
        for n in range(1, 27)
    }

    assert derived == {
        "ocd-jurisdiction/country:us/state:oh/place:cincinnati/government"
    }
