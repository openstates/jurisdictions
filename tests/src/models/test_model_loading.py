"""Loading a model back from the YAML it wrote.

``tests/sample_output`` is the ground truth the fixtures read, so the load
path has to round-trip whatever ``dump_*`` produced.
"""

import pytest

from src.models.division import Division, Identifier
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
        other_names=["Emerald City"],
        # dump_division keys the filename on the census geoid and refuses
        # to write without one.
        government_identifiers=[
            Identifier(
                authority="census", id_type="geoid", value="5363000", source=source
            )
        ],
        sourcing=[source],
    )


def _jurisdiction() -> Jurisdiction:
    return Jurisdiction(
        ocdid="ocd-jurisdiction/country:us/state:wa/place:seattle/government",
        name="Seattle City Government",
        url="https://www.seattle.gov/",
        classification="government",
        legislative_sessions={},
        feature_flags=[],
    )


def test_load_division_returns_a_division(tmp_path) -> None:
    """The loader returns the model, rather than dropping it on the floor."""
    written = _division().dump_division(base_dir=tmp_path)

    loaded = Division.load_division(written)

    assert isinstance(loaded, Division)


def test_load_division_round_trips_values(tmp_path) -> None:
    """A dumped Division reloads with its field values intact."""
    original = _division()
    written = original.dump_division(base_dir=tmp_path)

    loaded = Division.load_division(written)

    assert loaded.ocdid == original.ocdid
    assert loaded.display_name == original.display_name
    assert loaded.other_names == ["Emerald City"]
    assert loaded.jurisdiction_id == original.jurisdiction_id


def test_load_division_rejects_a_missing_file(tmp_path) -> None:
    """A bad path fails loudly instead of returning None."""
    with pytest.raises(ValueError):
        Division.load_division(tmp_path / "nope.yaml")


def test_load_jurisdiction_returns_a_jurisdiction(tmp_path) -> None:
    """The loader returns the model, rather than dropping it on the floor."""
    written = _jurisdiction().dump_jurisdiction(base_dir=tmp_path)

    loaded = Jurisdiction.load_jurisdiction(written)

    assert isinstance(loaded, Jurisdiction)


def test_load_jurisdiction_round_trips_values(tmp_path) -> None:
    """A dumped Jurisdiction reloads with its field values intact."""
    original = _jurisdiction()
    written = original.dump_jurisdiction(base_dir=tmp_path)

    loaded = Jurisdiction.load_jurisdiction(written)

    assert loaded.ocdid == original.ocdid
    assert loaded.name == original.name
    assert loaded.classification == original.classification


def test_load_jurisdiction_rejects_a_missing_file(tmp_path) -> None:
    """A bad path fails loudly instead of returning None."""
    with pytest.raises(ValueError):
        Jurisdiction.load_jurisdiction(tmp_path / "nope.yaml")
