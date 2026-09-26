"""YAML written by the models keeps the models' field order.

``yaml.safe_dump`` sorts keys alphabetically unless told not to, which
scatters related fields and makes diffs noisier than the change behind
them. These tests pin the dump paths to declaration order.
"""

from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.models.division import (
    Boundary,
    Centroid,
    Division,
    Geometry,
    Identifier,
)
from src.models.jurisdiction import Jurisdiction
from src.models.source import SourceObj, SourceType


def _source() -> SourceObj:
    return SourceObj(
        field=["government_identifiers"],
        source_name="census",
        source_type=SourceType.HUMAN,
        source_url={"census": "https://www.census.gov/"},
        source_description="Census TIGER/Line.",
    )


def _division() -> Division:
    source = _source()
    return Division(
        ocdid="ocd-division/country:us/state:wa/place:seattle",
        country="us",
        display_name="Seattle",
        jurisdiction_id="ocd-jurisdiction/country:us/state:wa/place:seattle/government",
        other_names=["City of Seattle"],
        geometries=[
            Geometry(
                boundary=Boundary(centroid=Centroid(coordinates=[-122.3, 47.6])),
                valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                source=source,
            )
        ],
        government_identifiers=[
            Identifier(
                authority="census", id_type="geoid", value="5363000", source=source
            )
        ],
    )


def _keys_in_written_yaml(path: Path) -> list[str]:
    return list(yaml.safe_load(path.read_text()))


def test_division_yaml_follows_model_field_order(tmp_path) -> None:
    """A dumped Division lists keys in declaration order, not alphabetically."""
    division = _division()

    written = division.dump_division(base_dir=tmp_path)
    keys = _keys_in_written_yaml(written)

    assert keys == [name for name in Division.model_fields if name in keys]
    assert keys != sorted(keys), "keys came out alphabetical; sort_keys=False lost"


def test_jurisdiction_yaml_follows_model_field_order(tmp_path) -> None:
    """A dumped Jurisdiction lists keys in declaration order."""
    jurisdiction = Jurisdiction(
        ocdid="ocd-jurisdiction/country:us/state:wa/place:seattle/government",
        name="Seattle City Government",
        url="https://www.seattle.gov/",
        classification="government",
        legislative_sessions={},
        feature_flags=[],
    )

    written = jurisdiction.dump_jurisdiction(base_dir=tmp_path)
    keys = _keys_in_written_yaml(written)

    assert keys == [name for name in Jurisdiction.model_fields if name in keys]
    assert keys != sorted(keys), "keys came out alphabetical; sort_keys=False lost"


def test_nested_geometry_follows_sub_model_field_order(tmp_path) -> None:
    """Sub-models keep their own declaration order inside the parent file."""
    division = _division()

    written = division.dump_division(base_dir=tmp_path)
    data = yaml.safe_load(written.read_text())
    geometry_keys = list(data["geometries"][0])

    assert geometry_keys == [
        name for name in Geometry.model_fields if name in geometry_keys
    ]


def test_nested_identifier_follows_sub_model_field_order(tmp_path) -> None:
    """Identifier entries keep declaration order, so provenance reads last."""
    division = _division()

    written = division.dump_division(base_dir=tmp_path)
    data = yaml.safe_load(written.read_text())
    identifier_keys = list(data["government_identifiers"][0])

    assert identifier_keys == [
        name for name in Identifier.model_fields if name in identifier_keys
    ]
