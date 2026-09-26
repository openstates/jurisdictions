from datetime import datetime, timezone
from pathlib import Path

import yaml

import src.render_yaml as renderer
from src.models.division import Division
from src.models.jurisdiction import ClassificationEnum, Jurisdiction
from src.render_yaml import (
    record_relative_path,
    render_yaml,
    state_segment,
    write_yaml_record,
)
from src.utils.deterministic_id import generate_id

ASOF = datetime(2026, 9, 23, 17, 17, 58, tzinfo=timezone.utc)


def _division() -> Division:
    return Division(
        ocdid="ocd-division/country:us/state:ca/place:sausalito",
        country="us",
        display_name="Sausalito",
        classification="place",
        last_updated=ASOF,
    )


def _jurisdiction() -> Jurisdiction:
    return Jurisdiction(
        ocdid="ocd-jurisdiction/country:us/state:ca/place:sausalito/government",
        name="City of Sausalito",
        classification=ClassificationEnum.GOVERNMENT,
        last_updated=ASOF,
    )


def test_render_yaml_is_byte_identical_for_unchanged_model() -> None:
    division = _division()

    first = render_yaml(division)
    second = render_yaml(division)

    assert first.encode("utf-8") == second.encode("utf-8")
    assert yaml.safe_load(first) == division.model_dump(
        mode="json",
        exclude_none=False,
    )


def test_record_relative_path_uses_stable_uuid_without_geoid() -> None:
    division = _division()
    expected_id = generate_id(division.ocdid)

    assert record_relative_path(division) == Path(
        f"divisions/ca/local/sausalito_{expected_id}.yaml"
    )
    assert "geoid" not in str(record_relative_path(division))


def test_record_relative_path_supports_controlled_golden_namespace() -> None:
    jurisdiction = _jurisdiction()

    assert record_relative_path(jurisdiction, namespace="test") == Path(
        "jurisdictions/test/ca/local/"
        f"city_of_sausalito_{jurisdiction.id}.yaml"
    )


def test_state_segment_supports_district_dc() -> None:
    assert (
        state_segment(
            "ocd-division/country:us/district:dc/anc:1a/council_district:1"
        )
        == "dc"
    )


def test_write_yaml_record_round_trips_model_dump(tmp_path: Path) -> None:
    division = _division()

    path = write_yaml_record(division, tmp_path)
    assert path == tmp_path / record_relative_path(division)
    assert yaml.safe_load(path.read_text()) == division.model_dump(
        mode="json",
        exclude_none=False,
    )


def test_renderer_has_no_resolution_or_construction_imports() -> None:
    source = Path(renderer.__file__).read_text()
    forbidden = (
        "normalize_government",
        "resolve_government",
        "ocdid_rule_engine",
        "ocdid_validation",
        "build_canonical_models",
    )

    assert not any(name in source for name in forbidden)
