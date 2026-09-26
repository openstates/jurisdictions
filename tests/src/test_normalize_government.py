from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models.source import SourceObj, SourceType
from src.sources import census_governments, census_gus
from src.sources.snapshot import load_snapshot, source_obj_from_snapshot
from src.normalize_government import (
    GovernmentType,
    normalize_name,
    normalize_record,
    normalize_records,
)
from src.sources.government_units import (
    CensusGovernmentRecord,
    CensusRowError,
    GovernmentKind,
)


def _source() -> SourceObj:
    return SourceObj(
        field=["government"],
        source_name="U.S. Census Bureau",
        source_type=SourceType.SCRAPED,
        source_url="https://www.census.gov/programs-surveys/gus.html",
        source_description="Government Units listing",
        dataset="Government Units",
        release="2026",
    )


def _record(**overrides) -> CensusGovernmentRecord:
    values = {
        "census_id": "161205",
        "name": "CITY OF SAUSALITO",
        "kind": GovernmentKind.GENERAL_PURPOSE,
        "state": "CA",
        "fips_state": "06",
        "is_active": True,
        "unit_type": "2 - MUNICIPAL",
        "fips_county": "041",
        "fips_place": "70364",
        "county_area_name": "MARIN",
        "web_address": "http://www.ci.sausalito.ca.us",
    }
    values.update(overrides)
    return CensusGovernmentRecord(**values)


def test_normalize_name_is_deterministic_without_changing_semantics():
    assert normalize_name("  CITY   OF  Sausalito ") == "city of sausalito"


def test_normalize_record_preserves_authoritative_name_and_identifiers():
    source = _source()
    record = _record()

    normalized = normalize_record(record, source=source)

    assert normalized.census_government_id == "161205"
    assert normalized.name == "CITY OF SAUSALITO"
    assert normalized.normalized_name == "city of sausalito"
    assert normalized.government_type is GovernmentType.MUNICIPAL
    assert normalized.government_subtype == "2 - MUNICIPAL"

    assert normalized.state == "CA"
    assert normalized.state_fips == "06"
    assert normalized.county_fips == "041"
    assert normalized.place_fips == "70364"
    assert normalized.county_name == "MARIN"

    assert normalized.website == "http://www.ci.sausalito.ca.us"
    assert normalized.is_active is True
    assert normalized.source == source


@pytest.mark.parametrize(
    ("unit_type", "expected_type"),
    [
        ("1 - COUNTY", GovernmentType.COUNTY),
        ("2 - MUNICIPAL", GovernmentType.MUNICIPAL),
        ("3 - TOWNSHIP", GovernmentType.TOWNSHIP_MCD),
    ],
)
def test_general_purpose_classification(unit_type, expected_type):
    normalized = normalize_record(
        _record(unit_type=unit_type),
        source=_source(),
    )

    assert normalized.government_type is expected_type
    assert normalized.government_subtype == unit_type


def test_special_district_classification_preserves_function_as_subtype():
    record = _record(
        kind=GovernmentKind.SPECIAL_DISTRICT,
        unit_type="4 - SPECIAL DISTRICT",
        function_name="80 - SEWERAGE",
        fips_place=None,
    )

    normalized = normalize_record(record, source=_source())

    assert normalized.government_type is GovernmentType.SPECIAL_DISTRICT
    assert normalized.government_subtype == "80 - SEWERAGE"


def test_school_district_classification_preserves_school_level_as_subtype():
    record = _record(
        kind=GovernmentKind.SCHOOL_DISTRICT,
        unit_type="5 - SCHOOL DISTRICT OR EDUCATIONAL SERVICE AGENCY",
        school_level="03 - ELEMENTARY AND SECONDARY",
        fips_place=None,
    )

    normalized = normalize_record(record, source=_source())

    assert normalized.government_type is GovernmentType.SCHOOL_DISTRICT
    assert normalized.government_subtype == "03 - ELEMENTARY AND SECONDARY"


def test_dependent_school_system_is_not_promoted_to_independent_school_government():
    record = _record(
        kind=GovernmentKind.DEPENDENT_SCHOOL_SYSTEM,
        name="DISTRICT OF COLUMBIA PUBLIC SCHOOLS",
        unit_type="2 - MUNICIPAL",
        school_level="03 - ELEMENTARY AND SECONDARY",
        parent_census_id="124214",
        parent_name="WASHINGTON DC",
        fips_state="11",
        fips_county="001",
        fips_place=None,
        state="DC",
    )

    normalized = normalize_record(record, source=_source())

    assert normalized.government_type is GovernmentType.OTHER
    assert normalized.government_subtype == "dependent_school_system"
    assert normalized.parent_census_government_id == "124214"


def test_unrecognized_classification_becomes_unknown_instead_of_being_dropped():
    record = _record(
        kind=GovernmentKind.GENERAL_PURPOSE,
        unit_type="9 - FUTURE TYPE",
    )

    normalized = normalize_record(record, source=_source())

    assert normalized.government_type is GovernmentType.UNKNOWN
    assert normalized.government_subtype == "9 - FUTURE TYPE"


def test_normalization_result_preserves_source_errors():
    source_error = CensusRowError(
        sheet="General Purpose",
        line=17,
        census_id="",
        reason="CENSUS_ID_PID6 is malformed: ''",
    )

    result = normalize_records(
        [_record()],
        source=_source(),
        source_errors=[source_error],
    )

    assert len(result.records) == 1
    assert result.records[0].census_government_id == "161205"
    assert result.source_errors == [source_error]


def test_government_record_is_immutable():
    normalized = normalize_record(_record(), source=_source())

    with pytest.raises(ValidationError):
        normalized.normalized_name = "changed"



FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures"


def _normalize_snapshot_fixture(
    path: Path,
    *,
    kind: GovernmentKind,
    annual: bool = True,
):
    snapshot = load_snapshot(path)
    adapter = census_gus if annual else census_governments
    parsed = adapter.parse_sheet_snapshot(snapshot, kind)

    assert parsed.metadata is not None

    source = source_obj_from_snapshot(
        parsed.metadata,
        field=["government"],
        source_description="Census government normalization input",
    )

    normalized = normalize_records(
        parsed.records,
        source=source,
        source_errors=parsed.errors,
    )

    return parsed, normalized


@pytest.mark.parametrize(
    ("filename", "kind", "expected_type", "expected_count"),
    [
        (
            "gov_units_2026_general_purpose.csv",
            GovernmentKind.GENERAL_PURPOSE,
            None,
            9,
        ),
        (
            "gov_units_2026_special_district.csv",
            GovernmentKind.SPECIAL_DISTRICT,
            GovernmentType.SPECIAL_DISTRICT,
            2,
        ),
        (
            "gov_units_2026_school_district.csv",
            GovernmentKind.SCHOOL_DISTRICT,
            GovernmentType.SCHOOL_DISTRICT,
            4,
        ),
        (
            "gov_units_2026_dependent_school_system.csv",
            GovernmentKind.DEPENDENT_SCHOOL_SYSTEM,
            GovernmentType.OTHER,
            2,
        ),
    ],
)
def test_annual_fixture_records_normalize_without_loss(
    filename,
    kind,
    expected_type,
    expected_count,
):
    parsed, normalized = _normalize_snapshot_fixture(
        FIXTURE_ROOT / "census_gus" / filename,
        kind=kind,
    )

    assert len(parsed.records) == expected_count
    assert len(normalized.records) == len(parsed.records)
    assert normalized.source_errors == parsed.errors

    if expected_type is not None:
        assert {
            record.government_type for record in normalized.records
        } == {expected_type}


def test_real_general_purpose_fixture_classifies_counties_and_municipalities():
    _, normalized = _normalize_snapshot_fixture(
        FIXTURE_ROOT / "census_gus" / "gov_units_2026_general_purpose.csv",
        kind=GovernmentKind.GENERAL_PURPOSE,
    )

    counts = {
        government_type: sum(
            record.government_type is government_type
            for record in normalized.records
        )
        for government_type in GovernmentType
    }

    assert counts[GovernmentType.COUNTY] == 4
    assert counts[GovernmentType.MUNICIPAL] == 5
    assert counts[GovernmentType.UNKNOWN] == 0


def test_dependent_school_fixture_preserves_parent_identity():
    _, normalized = _normalize_snapshot_fixture(
        FIXTURE_ROOT
        / "census_gus"
        / "gov_units_2026_dependent_school_system.csv",
        kind=GovernmentKind.DEPENDENT_SCHOOL_SYSTEM,
    )

    assert len(normalized.records) == 2
    assert {
        record.parent_census_government_id for record in normalized.records
    } == {"124214"}
    assert {
        record.government_type for record in normalized.records
    } == {GovernmentType.OTHER}


def test_benchmark_fixture_preserves_real_parser_errors():
    parsed, normalized = _normalize_snapshot_fixture(
        FIXTURE_ROOT
        / "census_governments"
        / "govt_units_2022_general_purpose.csv",
        kind=GovernmentKind.GENERAL_PURPOSE,
        annual=False,
    )

    assert len(parsed.records) == 9
    assert len(parsed.errors) == 2

    assert len(normalized.records) == 9
    assert normalized.source_errors == parsed.errors


def test_fixture_provenance_reaches_every_normalized_record():
    parsed, normalized = _normalize_snapshot_fixture(
        FIXTURE_ROOT / "census_gus" / "gov_units_2026_general_purpose.csv",
        kind=GovernmentKind.GENERAL_PURPOSE,
    )

    assert parsed.metadata is not None

    for record in normalized.records:
        assert record.source.source_name == "U.S. Census Bureau"
        assert record.source.release == "2026"
        assert record.source.dataset == parsed.metadata.dataset
