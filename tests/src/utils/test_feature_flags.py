from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.models.jurisdiction import (
    ClassificationEnum,
    DivisionRelationship,
    Jurisdiction,
    JurisdictionMetadata,
    SessionDetail,
    TermDetail,
    URLObject,
)
from src.models.organization import Organization
from src.models.source import SourceObj, SourceType
from src.render_yaml import write_yaml
from src.utils.feature_flags import (
    ELIGIBLE_FIELDS,
    compute_feature_flags,
    load_prior_jurisdiction,
    merge_feature_flags,
    missing_flagged_fields,
)

OCDID = "ocd-jurisdiction/country:us/state:ca/place:sausalito/government"
DIVISION = "ocd-division/country:us/state:ca/place:sausalito"
STUB_URL = "https://github.com/openstates/jurisdictions/tree/main/jurisdictions"


def _source() -> SourceObj:
    return SourceObj(
        field=["name"],
        source_name="U.S. Census Bureau",
        source_type=SourceType.SCRAPED,
        source_url="https://www.census.gov/",
        source_description="Controlled fixture",
        retrieval_date=datetime(2026, 9, 23, tzinfo=timezone.utc),
    )


def _term() -> TermDetail:
    return TermDetail(
        duration=4,
        term_description="Four-year terms.",
        number_of_positions=5,
        source_url="https://www.sausalito.gov/charter",
    )


def _metadata() -> JurisdictionMetadata:
    return JurisdictionMetadata(
        urls=[URLObject(url_type="people", url="https://www.sausalito.gov/council")]
    )


def _jurisdiction(**overrides) -> Jurisdiction:
    values = {
        "ocdid": OCDID,
        "name": "City of Sausalito",
        "classification": ClassificationEnum.GOVERNMENT,
        "last_updated": datetime(2026, 9, 23, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return Jurisdiction(**values)


def _full() -> Jurisdiction:
    return _jurisdiction(
        url="https://www.sausalito.gov/",
        term=_term(),
        metadata=_metadata(),
        sourcing=[_source()],
        legislative_sessions={
            "2026": SessionDetail(
                name="2026",
                identifiers="2026",
                classification="primary",
                start_date=datetime(2026, 1, 1),
                end_date=datetime(2026, 12, 31),
            )
        },
        organizations=[Organization(name="City Council")],
        governing_charter="https://www.sausalito.gov/charter.pdf",
        census_government_id="161205",
        division_relationships=[DivisionRelationship(division_id=DIVISION)],
        accurate_asof=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )


def test_populated_fields_are_flagged_sorted() -> None:
    jurisdiction = _jurisdiction(
        url="https://www.sausalito.gov/",
        term=_term(),
        metadata=_metadata(),
        sourcing=[_source()],
        census_government_id="161205",
        division_relationships=[DivisionRelationship(division_id=DIVISION)],
    )

    assert compute_feature_flags(jurisdiction) == [
        "census_government_id",
        "division_relationships",
        "metadata",
        "sourcing",
        "term",
        "url",
    ]


def test_every_eligible_field_is_flagged_when_populated() -> None:
    assert compute_feature_flags(_full()) == sorted(ELIGIBLE_FIELDS)


def test_empty_none_and_placeholder_fields_are_not_flagged() -> None:
    jurisdiction = _jurisdiction(
        url=STUB_URL,
        metadata=JurisdictionMetadata(urls=[]),
        sourcing=[],
        legislative_sessions={},
        organizations=[],
        governing_charter=STUB_URL,
        census_government_id="",
        division_relationships=[],
    )

    assert compute_feature_flags(jurisdiction) == []


def test_bare_jurisdiction_has_no_flags() -> None:
    assert compute_feature_flags(_jurisdiction()) == []


def test_excluded_fields_are_never_flagged() -> None:
    flags = compute_feature_flags(_full())

    for excluded in (
        "id",
        "ocdid",
        "name",
        "classification",
        "accurate_asof",
        "last_updated",
        "feature_flags",
    ):
        assert excluded not in flags
    assert set(flags) <= set(ELIGIBLE_FIELDS)


def test_existing_flags_on_the_input_do_not_feed_back_into_compute() -> None:
    jurisdiction = _jurisdiction(feature_flags=["term", "url"])

    assert compute_feature_flags(jurisdiction) == []


def test_merge_is_union_sorted_without_duplicates() -> None:
    assert merge_feature_flags(["url", "term"], ["term", "metadata"]) == [
        "metadata",
        "term",
        "url",
    ]


def test_merge_without_prior_returns_new_sorted() -> None:
    assert merge_feature_flags(None, ["url", "metadata"]) == ["metadata", "url"]


def test_merge_never_removes_a_prior_flag() -> None:
    assert merge_feature_flags(["term", "url"], []) == ["term", "url"]


def test_compute_is_deterministic() -> None:
    first = compute_feature_flags(_full())
    second = compute_feature_flags(_full())

    assert first == second


def test_missing_flagged_fields_reports_exactly_the_dropped_fields() -> None:
    jurisdiction = _jurisdiction(
        url="https://www.sausalito.gov/",
        feature_flags=["metadata", "term", "url"],
    )

    assert missing_flagged_fields(jurisdiction) == ["metadata", "term"]


def test_missing_flagged_fields_is_empty_when_all_flagged_fields_present() -> None:
    jurisdiction = _full().model_copy(update={"feature_flags": ["term", "url"]})

    assert missing_flagged_fields(jurisdiction) == []


def test_missing_flagged_fields_treats_placeholder_as_missing() -> None:
    jurisdiction = _jurisdiction(url=STUB_URL, feature_flags=["url"])

    assert missing_flagged_fields(jurisdiction) == ["url"]


def test_missing_flagged_fields_ignores_unknown_flag_names() -> None:
    jurisdiction = _jurisdiction(feature_flags=["legacy_capability"])

    assert missing_flagged_fields(jurisdiction) == []


def test_load_prior_jurisdiction_returns_none_when_no_yaml_exists(
    tmp_path: Path,
) -> None:
    assert load_prior_jurisdiction(OCDID, tmp_path) is None


def test_load_prior_jurisdiction_finds_record_by_ocdid(tmp_path: Path) -> None:
    prior = _full().model_copy(update={"feature_flags": ["term", "url"]})
    write_yaml(tmp_path / "ca" / "local" / "sausalito.yaml", prior)

    loaded = load_prior_jurisdiction(OCDID, tmp_path)

    assert loaded is not None
    assert loaded.ocdid == OCDID
    assert loaded.feature_flags == ["term", "url"]


def test_load_prior_jurisdiction_rejects_ambiguous_matches(tmp_path: Path) -> None:
    prior = _full()
    write_yaml(tmp_path / "ca" / "local" / "a.yaml", prior)
    write_yaml(tmp_path / "ca" / "county" / "b.yaml", prior)

    with pytest.raises(ValueError, match="more than one"):
        load_prior_jurisdiction(OCDID, tmp_path)
