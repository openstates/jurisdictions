from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from hypothesis import given
from hypothesis import strategies as st

from src.models.jurisdiction import ClassificationEnum, Jurisdiction

_OCDID_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789:/_-"
ocdid_strategy = st.text(alphabet=_OCDID_CHARS, min_size=1, max_size=120)


def _build_jurisdiction(ocdid: str, id_value=None) -> Jurisdiction:
    kwargs = {
        "ocdid": ocdid,
        "name": "Sample Jurisdiction",
        "url": "https://example.gov",
        "classification": ClassificationEnum.GOVERNMENT,
        "metadata": {"urls": []},
    }
    if id_value is not None:
        kwargs["id"] = id_value
    return Jurisdiction(**kwargs)


@given(ocdid=ocdid_strategy)
def test_jurisdiction_id_defaults_to_uuid5_from_ocdid_and_date(ocdid: str) -> None:
    last_updated = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    jurisdiction = Jurisdiction(
        ocdid=ocdid,
        name="Sample Jurisdiction",
        url="https://example.gov",
        classification=ClassificationEnum.GOVERNMENT,
        metadata={"urls": []},
        last_updated=last_updated,
    )
    expected = uuid5(NAMESPACE_URL, f"{ocdid}|{last_updated.date().isoformat()}")

    assert jurisdiction.id == expected


def test_jurisdiction_accepts_explicit_id() -> None:
    explicit_id = uuid4()
    jurisdiction = _build_jurisdiction(
        "ocd-jurisdiction/country:us/state:wa/place:seattle/government",
        id_value=explicit_id,
    )
    assert jurisdiction.id == explicit_id
