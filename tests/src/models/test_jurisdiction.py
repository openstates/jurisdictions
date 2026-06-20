from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from src.models.jurisdiction import ClassificationEnum, Jurisdiction

classification_strategy = st.sampled_from(list(ClassificationEnum))


@st.composite
def jurisdiction_input_strategy(draw) -> tuple[str, ClassificationEnum]:
    classification = draw(classification_strategy)
    state = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=2, max_size=2))
    place = draw(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=3, max_size=12)
    )
    return (
        f"ocd-jurisdiction/country:us/state:{state}/place:{place}/{classification.value}",
        classification,
    )


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


@given(jurisdiction_input=jurisdiction_input_strategy())
def test_jurisdiction_id_defaults_to_uuid5_from_ocdid_and_date(
    jurisdiction_input: tuple[str, ClassificationEnum],
) -> None:
    ocdid, classification = jurisdiction_input
    last_updated = datetime(2026, 4, 8, 12, 0, tzinfo=UTC)
    jurisdiction = Jurisdiction(
        ocdid=ocdid,
        name="Sample Jurisdiction",
        url="https://example.gov",
        classification=classification,
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


def test_jurisdiction_rejects_division_prefix() -> None:
    with pytest.raises(ValidationError, match="must use the 'ocd-jurisdiction' prefix"):
        _build_jurisdiction("ocd-division/country:us/state:wa/place:seattle")


def test_jurisdiction_rejects_mismatched_classification_suffix() -> None:
    with pytest.raises(
        ValidationError, match="suffix must match the classification value"
    ):
        Jurisdiction(
            ocdid="ocd-jurisdiction/country:us/state:wa/place:seattle/legislature",
            name="Sample Jurisdiction",
            url="https://example.gov",
            classification=ClassificationEnum.GOVERNMENT,
            metadata={"urls": []},
        )
