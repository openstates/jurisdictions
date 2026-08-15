from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from hypothesis import given
from hypothesis import strategies as st

from src.models.division import Division, GovernmentIdentifiers


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


def _minimal_government_identifiers(**overrides) -> GovernmentIdentifiers:
    defaults = {
        "namelsad": "Seattle city",
        "statefp": "53",
        "sldust": [],
        "sldlst": [],
        "countyfp": ["033"],
        "county_names": ["King"],
        "lsad": "25",
        "geoid": "5363000",
    }
    defaults.update(overrides)
    return GovernmentIdentifiers(**defaults)


def test_government_identifiers_common_names_accepts_list() -> None:
    gi = _minimal_government_identifiers(common_names=["Emerald City", "Jet City"])
    assert gi.common_names == ["Emerald City", "Jet City"]
    dumped = gi.model_dump(mode="json")
    assert dumped["common_names"] == ["Emerald City", "Jet City"]


def test_government_identifiers_common_names_defaults_to_none() -> None:
    gi = _minimal_government_identifiers()
    assert gi.common_names is None
    assert gi.model_dump(mode="json")["common_names"] is None


def test_government_identifiers_ignores_legacy_common_name_key() -> None:
    gi = GovernmentIdentifiers.model_validate(
        {
            "namelsad": "Seattle city",
            "statefp": "53",
            "sldust": [],
            "sldlst": [],
            "countyfp": ["033"],
            "county_names": ["King"],
            "lsad": "25",
            "geoid": "5363000",
            "common_name": ["Emerald City"],
        }
    )
    assert gi.common_names is None
    assert "common_name" not in gi.model_dump(mode="json")
