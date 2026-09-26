from pathlib import Path

import pytest

from src.models.source import SourceObj
from src.normalize_government import GovernmentRecord, GovernmentType
from src.ocdid_rule_engine import OCDIDCandidate
from src.resolve_government import CensusDivisionRecord
from src.ocdid_validation import (
    OCDIDQuarantineRecord,
    OCDIDValidationStatus,
    build_quarantine_record,
    validate_candidate,
)
from src.sources.ocd_master import OCDMasterIndex
from src.sources.snapshot import load_snapshot


FIXTURE = Path("tests/fixtures/ocd_master/country-us.csv")

SAUSALITO = "ocd-division/country:us/state:ca/place:sausalito"
TACOMA = "ocd-division/country:us/state:wa/place:tacoma"


@pytest.fixture
def canonical_index() -> OCDMasterIndex:
    return OCDMasterIndex.from_snapshots(load_snapshot(FIXTURE))


def _candidate(value: str, hierarchy: tuple[str, ...]) -> OCDIDCandidate:
    return OCDIDCandidate(
        value=value,
        rule="test.fixture",
        rule_version="1",
        transformations=(),
        hierarchy=hierarchy,
    )


@pytest.mark.parametrize(
    ("value", "hierarchy"),
    [
        (
            SAUSALITO,
            ("country:us", "state:ca", "place:sausalito"),
        ),
        (
            TACOMA,
            ("country:us", "state:wa", "place:tacoma"),
        ),
    ],
)
def test_exact_canonical_candidate_is_verified(
    canonical_index,
    value,
    hierarchy,
):
    candidate = _candidate(value, hierarchy)

    result = validate_candidate(candidate, canonical_index)

    assert result.status is OCDIDValidationStatus.VERIFIED
    assert result.candidate == candidate
    assert result.canonical_ocdid == value


def test_verified_result_preserves_master_name(canonical_index):
    candidate = _candidate(
        SAUSALITO,
        ("country:us", "state:ca", "place:sausalito"),
    )

    result = validate_candidate(candidate, canonical_index)

    assert result.status is OCDIDValidationStatus.VERIFIED
    assert result.canonical_ocdid == SAUSALITO
    assert result.canonical_name == "Sausalito city"


UNKNOWN_TACOMA = "ocd-division/country:us/state:wa/place:tacomma"


def test_unknown_candidate_is_quarantined(canonical_index):
    candidate = _candidate(
        UNKNOWN_TACOMA,
        ("country:us", "state:wa", "place:tacomma"),
    )

    result = validate_candidate(candidate, canonical_index)

    assert result.status is OCDIDValidationStatus.QUARANTINED
    assert result.candidate == candidate
    assert result.canonical_ocdid is None
    assert result.canonical_name is None
    assert result.reason == "not_in_canonical_corpus"


def test_unknown_candidate_is_not_silently_replaced_by_nearest_match(
    canonical_index,
):
    candidate = _candidate(
        UNKNOWN_TACOMA,
        ("country:us", "state:wa", "place:tacomma"),
    )

    result = validate_candidate(candidate, canonical_index)

    assert result.status is OCDIDValidationStatus.QUARANTINED
    assert result.candidate.value == UNKNOWN_TACOMA
    assert result.canonical_ocdid is None


def test_quarantined_candidate_includes_review_suggestions(canonical_index):
    candidate = _candidate(
        UNKNOWN_TACOMA,
        ("country:us", "state:wa", "place:tacomma"),
    )

    result = validate_candidate(candidate, canonical_index)

    assert result.status is OCDIDValidationStatus.QUARANTINED
    assert result.review_suggestions
    assert result.review_suggestions[0].ocdid == TACOMA
    assert result.review_suggestions[0].name == "Tacoma city"
    assert 0 < result.review_suggestions[0].score < 100


def test_review_suggestion_never_becomes_canonical_identity(canonical_index):
    candidate = _candidate(
        UNKNOWN_TACOMA,
        ("country:us", "state:wa", "place:tacomma"),
    )

    result = validate_candidate(candidate, canonical_index)

    assert result.review_suggestions[0].ocdid == TACOMA
    assert result.candidate.value == UNKNOWN_TACOMA
    assert result.canonical_ocdid is None


def test_verified_candidate_needs_no_review_suggestions(canonical_index):
    candidate = _candidate(
        TACOMA,
        ("country:us", "state:wa", "place:tacoma"),
    )

    result = validate_candidate(candidate, canonical_index)

    assert result.status is OCDIDValidationStatus.VERIFIED
    assert result.review_suggestions == ()


def _source(
    *,
    field: list[str],
    dataset: str,
    release: str,
) -> SourceObj:
    return SourceObj(
        field=field,
        source_name="U.S. Census Bureau",
        source_url="https://www.census.gov/",
        source_description="Controlled Phase 8 fixture",
        dataset=dataset,
        release=release,
    )


def _government() -> GovernmentRecord:
    return GovernmentRecord(
        census_government_id="999999",
        name="CITY OF TACOMMA",
        normalized_name="city of tacomma",
        government_type=GovernmentType.MUNICIPAL,
        government_subtype="2 - Municipal",
        state_fips="53",
        county_fips="053",
        place_fips="99999",
        state="WA",
        county_name="Pierce County",
        website=None,
        is_active=True,
        source=_source(
            field=["name", "government_type"],
            dataset="Government Units Survey",
            release="2026",
        ),
    )


def _division() -> CensusDivisionRecord:
    return CensusDivisionRecord(
        layer="place",
        geography_type="place",
        geoid="5399999",
        name="Tacomma",
        state_fips="53",
        county_fips="053",
        place_fips="99999",
        geometry_source=_source(
            field=["geometry"],
            dataset="TIGERweb",
            release="2026",
        ),
        geometry_url="https://tigerweb.geo.census.gov/example?f=geojson",
    )


def test_quarantine_record_serializes_complete_review_context(canonical_index):
    candidate = _candidate(
        UNKNOWN_TACOMA,
        ("country:us", "state:wa", "place:tacomma"),
    )
    validation = validate_candidate(candidate, canonical_index)

    record = build_quarantine_record(
        government=_government(),
        division=_division(),
        validation=validation,
    )

    assert isinstance(record, OCDIDQuarantineRecord)

    payload = record.model_dump(mode="json")

    assert payload["government"]["census_government_id"] == "999999"
    assert payload["government"]["name"] == "CITY OF TACOMMA"
    assert payload["government"]["source"]["dataset"] == "Government Units Survey"

    assert payload["division"]["geoid"] == "5399999"
    assert payload["division"]["name"] == "Tacomma"
    assert payload["division"]["geography_type"] == "place"
    assert payload["division"]["geometry_source"]["dataset"] == "TIGERweb"

    assert payload["candidate"]["value"] == UNKNOWN_TACOMA
    assert payload["candidate"]["rule"] == "test.fixture"
    assert payload["candidate"]["transformations"] == []

    assert payload["reason"] == "not_in_canonical_corpus"

    assert payload["nearest_master_ids"]
    assert payload["nearest_master_ids"][0]["ocdid"] == TACOMA
    assert payload["nearest_master_ids"][0]["name"] == "Tacoma city"

    assert payload["review"] == {
        "status": "pending",
        "decision": None,
        "canonical_ocdid": None,
        "notes": None,
    }


def test_quarantine_record_preserves_candidate_without_canonicalizing(
    canonical_index,
):
    candidate = _candidate(
        UNKNOWN_TACOMA,
        ("country:us", "state:wa", "place:tacomma"),
    )
    validation = validate_candidate(candidate, canonical_index)

    record = build_quarantine_record(
        government=_government(),
        division=_division(),
        validation=validation,
    )

    assert record.candidate.value == UNKNOWN_TACOMA
    assert record.review.canonical_ocdid is None
    assert record.nearest_master_ids[0].ocdid == TACOMA
