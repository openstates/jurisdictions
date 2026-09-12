from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from hypothesis import given
from hypothesis import strategies as st
import pytest
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
        "classification": ClassificationEnum.GOVERNMENT.value,
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
    last_updated = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
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


def test_jurisdiction_url_round_trips_exact_string() -> None:
    """A well-formed url survives serialization byte-for-byte.

    HttpUrl normalizes some inputs (a bare host gains a trailing slash), so
    the six sample_output values must be in already-normal form or
    regeneration silently rewrites them.
    """
    for url in [
        "https://www.seattle.gov/",
        "https://tacoma.gov/",
        "https://www.austintexas.gov/",
        "https://www.sausalito.gov/",
        "https://www.marincitycsd.com/",
        "https://oanc.dc.gov/anc-profile/anc-1a",
    ]:
        jurisdiction = Jurisdiction(
            ocdid="ocd-jurisdiction/country:us/state:wa/place:seattle/government",
            name="Sample Jurisdiction",
            url=url,
            classification=ClassificationEnum.GOVERNMENT,
            metadata={"urls": []},
        )
        assert jurisdiction.model_dump(mode="json")["url"] == url, (
            f"{url!r} was rewritten on dump"
        )

        restored = Jurisdiction.model_validate_json(jurisdiction.model_dump_json())
        assert str(restored.url) == url


def test_jurisdiction_url_rejects_non_http_values() -> None:
    """HttpUrl validation replaces the previous unvalidated str."""
    for bad_url in [
        "seattle.gov",
        "not a url",
        "ftp://files.seattle.gov/",
        "",
    ]:
        with pytest.raises(ValidationError):
            Jurisdiction(
                ocdid="ocd-jurisdiction/country:us/state:wa/place:seattle/government",
                name="Sample Jurisdiction",
                url=bad_url,
                classification=ClassificationEnum.GOVERNMENT,
                metadata={"urls": []},
            )


def test_jurisdiction_valid_without_url() -> None:
    """A Jurisdiction with no website is valid and serializes as null.

    Missing official websites must not invalidate an otherwise valid
    Jurisdiction. Website resolution is a separate enrichment concern.
    """
    jurisdiction = Jurisdiction(
        ocdid="ocd-jurisdiction/country:us/state:wa/place:seattle/government",
        name="Seattle City Government",
        classification=ClassificationEnum.GOVERNMENT,
        metadata={"urls": []},
    )

    assert jurisdiction.url is None
    assert jurisdiction.model_dump(mode="json")["url"] is None


def test_jurisdiction_without_url_round_trips() -> None:
    """A url-less Jurisdiction survives a JSON round-trip with url still None."""
    jurisdiction = Jurisdiction(
        ocdid="ocd-jurisdiction/country:us/state:wa/place:seattle/government",
        name="Seattle City Government",
        classification=ClassificationEnum.GOVERNMENT,
        metadata={"urls": []},
    )

    restored = Jurisdiction.model_validate_json(jurisdiction.model_dump_json())

    assert restored.url is None
    assert restored == jurisdiction


def test_jurisdiction_url_absence_does_not_change_uuid() -> None:
    """Identity must not move when a mutable fact like the website changes.

    ``ensure_uuid5_id`` derives identity from ocdid and the last_updated date
    only. Adding or removing a website must not produce a different UUID.
    """
    common = {
        "ocdid": "ocd-jurisdiction/country:us/state:wa/place:seattle/government",
        "name": "Seattle City Government",
        "classification": ClassificationEnum.GOVERNMENT,
        "metadata": {"urls": []},
        "last_updated": datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
    }

    without_url = Jurisdiction(**common)
    with_url = Jurisdiction(**common, url="https://www.seattle.gov/")

    assert without_url.url is None
    assert with_url.url is not None
    assert without_url.id == with_url.id


def test_jurisdiction_empty_url_is_rejected_not_coerced_to_none() -> None:
    """An empty string is invalid input, not a synonym for "no website"."""
    with pytest.raises(ValidationError):
        Jurisdiction(
            ocdid="ocd-jurisdiction/country:us/state:wa/place:seattle/government",
            name="Seattle City Government",
            url="",
            classification=ClassificationEnum.GOVERNMENT,
            metadata={"urls": []},
        )
