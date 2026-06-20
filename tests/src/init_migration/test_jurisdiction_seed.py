import pytest

from src.init_migration.jurisdiction_seed import infer_jurisdiction_seed
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
