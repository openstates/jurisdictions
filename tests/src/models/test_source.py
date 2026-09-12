"""Unit tests for ``src.models.source``."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import FtpUrl, HttpUrl, ValidationError

from src.models.division import Division
from src.models.jurisdiction import ClassificationEnum, Jurisdiction
from src.models.source import SourceObj, SourceType

GOLDEN_DIR = Path(__file__).resolve().parents[3] / "tests" / "sample_output"

_LEGACY_REQUIRED = {
    "field": ["government_identifiers"],
    "source_name": "civicdata.tech",
    "source_url": "https://example.test/civicdata",
    "source_description": None,
}


def _full_source() -> SourceObj:
    return SourceObj(
        field=["geometries"],
        source_name="Census Bureau",
        source_type=SourceType.SCRAPED,
        source_url="https://www2.census.gov/geo/tiger/TIGER2024/PLACE/",
        source_description="TIGER/Line place boundaries",
        dataset="TIGER/Line Shapefiles",
        release="2024",
        publication_date=datetime(2024, 9, 15, tzinfo=timezone.utc),
        retrieval_date=datetime(2026, 8, 1, 14, 30, 5, tzinfo=timezone.utc),
    )


def test_source_obj_without_new_fields_validates_and_round_trips() -> None:
    """The original field set is still sufficient (backward compatibility).

    Existing sourcing blocks carry only these fields, so the provenance
    fields must default to None rather than be required.
    """
    source = SourceObj(**_LEGACY_REQUIRED)

    assert source.dataset is None
    assert source.release is None
    assert source.publication_date is None
    assert source.retrieval_date is None
    assert source.source_type == SourceType.AI

    restored = SourceObj.model_validate_json(source.model_dump_json())
    assert restored == source


def test_source_obj_accepts_legacy_single_entry_url_map() -> None:
    """``source_url: {label: url}`` (the on-disk golden form) still loads.

    The label is dropped — it carried no meaning independent of
    ``source_name`` — and the scalar URL is kept.
    """
    for legacy_key in ["url", "civicdata", "ocd_repo", "division"]:
        source = SourceObj(
            **{**_LEGACY_REQUIRED, "source_url": {legacy_key: "https://example.test/x"}}
        )
        assert str(source.source_url) == "https://example.test/x"
        assert source.model_dump(mode="json")["source_url"] == "https://example.test/x"


def test_source_obj_rejects_multi_entry_url_map() -> None:
    """A map with more than one URL was never valid data and is not silently truncated."""
    with pytest.raises(ValidationError, match="exactly one URL"):
        SourceObj(
            **{
                **_LEGACY_REQUIRED,
                "source_url": {
                    "a": "https://example.test/a",
                    "b": "https://example.test/b",
                },
            }
        )


def test_source_obj_fully_populated_round_trips_losslessly() -> None:
    """Every field survives model_dump_json → model_validate_json, dates included."""
    source = _full_source()

    restored = SourceObj.model_validate_json(source.model_dump_json())

    assert restored == source
    assert restored.dataset == "TIGER/Line Shapefiles"
    assert restored.release == "2024"
    assert restored.publication_date == datetime(2024, 9, 15, tzinfo=timezone.utc)
    assert restored.retrieval_date == datetime(
        2026, 8, 1, 14, 30, 5, tzinfo=timezone.utc
    )
    assert restored.publication_date.tzinfo is not None
    assert restored.retrieval_date.tzinfo is not None

    dumped = source.model_dump(mode="json")
    assert set(dumped) == {
        "field",
        "source_name",
        "source_type",
        "source_url",
        "source_description",
        "dataset",
        "release",
        "publication_date",
        "retrieval_date",
    }


@pytest.mark.parametrize(
    ("publication_date", "retrieval_date"),
    [
        (None, None),
        (datetime(2024, 9, 15, tzinfo=timezone.utc), None),
        (None, datetime(2026, 8, 1, tzinfo=timezone.utc)),
    ],
)
def test_publication_and_retrieval_dates_accept_none_independently(
    publication_date, retrieval_date
) -> None:
    """Each observation-time field is independently optional."""
    source = SourceObj(
        **_LEGACY_REQUIRED,
        publication_date=publication_date,
        retrieval_date=retrieval_date,
    )

    assert source.publication_date == publication_date
    assert source.retrieval_date == retrieval_date

    restored = SourceObj.model_validate_json(source.model_dump_json())
    assert restored.publication_date == publication_date
    assert restored.retrieval_date == retrieval_date


def test_source_url_scalar_round_trips_exact_string() -> None:
    """The normalized scalar URL dumps as the same string it was given."""
    for url in [
        "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer",
        "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/edit?usp=drive_web&ouid=105992325138979778362",
        "https://data.census.gov/profile/Marin_City_CDP,_California?g=160XX00US0645820",
        "https://tacoma.gov/",
    ]:
        source = SourceObj(**{**_LEGACY_REQUIRED, "source_url": url})
        assert isinstance(source.source_url, HttpUrl)
        assert source.model_dump(mode="json")["source_url"] == url

        restored = SourceObj.model_validate_json(source.model_dump_json())
        assert str(restored.source_url) == url


def test_source_url_still_accepts_ftp_and_file_schemes() -> None:
    """Guards the ``FtpUrl | FileUrl`` members of the url union.

    The Census distributes TIGER/Line over FTP; collapsing to HttpUrl alone
    would be a capability regression.
    """
    ftp_source = SourceObj(
        **{
            **_LEGACY_REQUIRED,
            "source_url": "ftp://ftp2.census.gov/geo/tiger/TIGER2024/PLACE/",
        }
    )
    assert isinstance(ftp_source.source_url, FtpUrl)
    assert str(ftp_source.source_url).startswith("ftp://")
    restored = SourceObj.model_validate_json(ftp_source.model_dump_json())
    assert str(restored.source_url) == str(ftp_source.source_url)

    file_source = SourceObj(
        **{**_LEGACY_REQUIRED, "source_url": "file:///data/snapshots/gus_2022.csv"}
    )
    assert str(file_source.source_url).startswith("file://")


def test_source_url_rejects_non_url_values() -> None:
    for bad in ["census.gov", "not a url", ""]:
        with pytest.raises(ValidationError):
            SourceObj(**{**_LEGACY_REQUIRED, "source_url": bad})


def test_source_metadata_does_not_change_division_uuid() -> None:
    """Release/retrieval metadata is mutable provenance, not identity.

    Asserts against the current ``ensure_uuid5_id`` derivation.
    """
    common = {
        "ocdid": "ocd-division/country:us/state:ca/place:sausalito",
        "country": "us",
        "display_name": "Sausalito",
        "jurisdiction_id": "ocd-jurisdiction/country:us/state:ca/place:sausalito/government",
        "last_updated": datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
    }
    bare = SourceObj(**_LEGACY_REQUIRED)
    release_2024 = SourceObj(
        **_LEGACY_REQUIRED,
        dataset="TIGER/Line Shapefiles",
        release="2024",
        publication_date=datetime(2024, 9, 15, tzinfo=timezone.utc),
        retrieval_date=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    release_2025 = SourceObj(
        **_LEGACY_REQUIRED,
        dataset="TIGER/Line Shapefiles",
        release="2025",
        publication_date=datetime(2025, 9, 15, tzinfo=timezone.utc),
        retrieval_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )

    ids = {
        Division(**common, sourcing=[]).id,
        Division(**common, sourcing=[bare]).id,
        Division(**common, sourcing=[release_2024]).id,
        Division(**common, sourcing=[release_2025]).id,
    }

    assert len(ids) == 1
    assert release_2024 != release_2025  # releases remain distinguishable


def test_source_metadata_does_not_change_jurisdiction_uuid() -> None:
    common = {
        "ocdid": "ocd-jurisdiction/country:us/state:ca/place:sausalito/government",
        "name": "Sausalito City Government",
        "classification": ClassificationEnum.GOVERNMENT,
        "metadata": {"urls": []},
        "last_updated": datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
    }
    before = SourceObj(**{**_LEGACY_REQUIRED, "field": ["url"]})
    after = SourceObj(
        **{**_LEGACY_REQUIRED, "field": ["url"]},
        release="v2",
        retrieval_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )

    assert Jurisdiction(**common, sourcing=[before]).id == (
        Jurisdiction(**common, sourcing=[after]).id
    )


def test_every_golden_sourcing_block_still_validates() -> None:
    """All 30 checked-in sourcing blocks load under the current contract, unchanged.

    Reads ``tests/sample_output/**``; nothing is written. The block-level
    check side-steps the two reasons whole files cannot load (the older
    ``government_identifiers`` shape on Divisions; the Marin City CSD
    jurisdiction-id validator failure).
    """
    golden_files = sorted(GOLDEN_DIR.glob("*/test/*/local/*.yaml"))
    assert len(golden_files) == 12

    blocks = 0
    for path in golden_files:
        for raw in yaml.safe_load(path.read_text())["sourcing"]:
            source = SourceObj.model_validate(raw)
            blocks += 1
            assert (
                source.model_dump(mode="json")["source_url"] == raw["source_url"]["url"]
            )
            assert source.dataset is None and source.release is None
    assert blocks == 30
