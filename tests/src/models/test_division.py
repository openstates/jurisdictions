from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from hypothesis import given
from hypothesis import strategies as st

from src.models.division import Division

_OCDID_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789:/_-"
ocdid_strategy = st.text(alphabet=_OCDID_CHARS, min_size=1, max_size=120)


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


@given(ocdid=ocdid_strategy)
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
    division = _build_division("ocd-division/country:us/state:wa/place:seattle", id_value=explicit_id)
    assert division.id == explicit_id
