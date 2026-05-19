from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.init_migration.generate_recursive import ensure_ancestor_stubs, stub_exists
from src.models.ocdid import OCDidParsed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_parsed(raw_ocdid: str) -> OCDidParsed:
    """Build an OCDidParsed from a raw OCD ID string, mirroring how the pipeline
    constructs it (only known fields are mapped; extras land in model.__pydantic_extra__)."""
    from src.utils.ocdid import ocdid_parser
    parsed = ocdid_parser(raw_ocdid)
    return OCDidParsed(
        raw_ocdid=raw_ocdid,
        country=parsed.get("country", "us"),
        state=parsed.get("state"),
        county=parsed.get("county"),
        place=parsed.get("place"),
        subdivision=parsed.get("subdivision"),
    )


# ---------------------------------------------------------------------------
# OCDidParsed.build_ancestors — pure, no I/O
# ---------------------------------------------------------------------------


def test_build_ancestors_place():
    """State is the only ancestor for a state/place OCD ID."""
    parsed = _make_parsed("ocd-division/country:us/state:wa/place:seattle")
    ancestors = parsed.build_ancestors()
    assert len(ancestors) == 1
    assert ancestors[0].raw_ocdid == "ocd-division/country:us/state:wa"
    assert ancestors[0].state == "wa"


def test_build_ancestors_county_place():
    """State then county are returned for a state/county/place OCD ID."""
    parsed = _make_parsed("ocd-division/country:us/state:ca/county:marin/place:sausalito")
    ancestors = parsed.build_ancestors()
    assert len(ancestors) == 2
    assert ancestors[0].raw_ocdid == "ocd-division/country:us/state:ca"
    assert ancestors[0].state == "ca"
    assert ancestors[1].raw_ocdid == "ocd-division/country:us/state:ca/county:marin"
    assert ancestors[1].county == "marin"


def test_build_ancestors_council_district():
    """Place is an ancestor of a council_district OCD ID."""
    parsed = _make_parsed("ocd-division/country:us/state:wa/place:seattle/council_district:1")
    ancestors = parsed.build_ancestors()
    assert len(ancestors) == 2
    assert ancestors[0].raw_ocdid == "ocd-division/country:us/state:wa"
    assert ancestors[1].raw_ocdid == "ocd-division/country:us/state:wa/place:seattle"


def test_build_ancestors_leaf_excluded():
    """The leaf OCD ID itself never appears in the ancestor list."""
    leaf = "ocd-division/country:us/state:tx/place:austin"
    parsed = _make_parsed(leaf)
    ancestors = parsed.build_ancestors()
    assert all(a.raw_ocdid != leaf for a in ancestors)


def test_build_ancestors_state_only():
    """A state-level OCD ID has no ancestors to return."""
    parsed = _make_parsed("ocd-division/country:us/state:wa")
    assert parsed.build_ancestors() == []


def test_build_ancestors_returns_ocddid_parsed_objects():
    """Each element in the result is an OCDidParsed instance."""
    parsed = _make_parsed("ocd-division/country:us/state:ca/county:marin/place:sausalito")
    ancestors = parsed.build_ancestors()
    assert all(isinstance(a, OCDidParsed) for a in ancestors)


def test_build_ancestors_order():
    """Ancestors are ordered from shallowest to deepest."""
    parsed = _make_parsed("ocd-division/country:us/state:ca/county:los_angeles/place:los_angeles")
    ancestors = parsed.build_ancestors()
    assert ancestors[0].raw_ocdid == "ocd-division/country:us/state:ca"
    assert ancestors[1].raw_ocdid == "ocd-division/country:us/state:ca/county:los_angeles"
    assert len(ancestors) == 2


def test_build_ancestors_country_preserved():
    """country field from the original OCD ID is preserved on each ancestor."""
    parsed = _make_parsed("ocd-division/country:us/state:wa/place:seattle")
    ancestors = parsed.build_ancestors()
    assert all(a.country == "us" for a in ancestors)


# ---------------------------------------------------------------------------
# stub_exists — filesystem check
# ---------------------------------------------------------------------------


def test_stub_exists_missing_dir(tmp_path: Path):
    """Returns False for a directory that does not exist."""
    assert stub_exists("ocd-division/country:us/state:wa", tmp_path / "nowhere") is False


def test_stub_exists_empty_dir(tmp_path: Path):
    """Returns False when the directory is present but empty."""
    assert stub_exists("ocd-division/country:us/state:wa", tmp_path) is False


def test_stub_exists_match(tmp_path: Path):
    """Returns True when a YAML file contains a matching ocdid field."""
    ocdid = "ocd-division/country:us/state:wa"
    stub = tmp_path / "washington_stub.yaml"
    stub.write_text(yaml.dump({"ocdid": ocdid, "display_name": "Washington"}), encoding="utf-8")
    assert stub_exists(ocdid, tmp_path) is True


def test_stub_exists_no_match(tmp_path: Path):
    """Returns False when YAML files exist but none matches the given ocdid."""
    stub = tmp_path / "oregon_stub.yaml"
    stub.write_text(
        yaml.dump({"ocdid": "ocd-division/country:us/state:or"}),
        encoding="utf-8",
    )
    assert stub_exists("ocd-division/country:us/state:wa", tmp_path) is False


def test_stub_exists_ignores_corrupt_yaml(tmp_path: Path):
    """Corrupt YAML files are silently skipped and do not cause errors."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(":: not valid yaml ::", encoding="utf-8")
    assert stub_exists("ocd-division/country:us/state:wa", tmp_path) is False


# ---------------------------------------------------------------------------
# ensure_ancestor_stubs — integration (real state lookup + tmp_path I/O)
# ---------------------------------------------------------------------------


def test_ensure_ancestor_stubs_creates_state_stub(tmp_path: Path):
    """State-level stub Division and Jurisdiction are created for a place OCD ID."""
    parsed = _make_parsed("ocd-division/country:us/state:wa/place:seattle")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    assert len(results) == 1
    result = results[0]
    assert result["ocdid"] == "ocd-division/country:us/state:wa"
    assert result["level"] == "state"
    assert result["action"] == "created"

    div_path = Path(result["division_path"])
    jur_path = Path(result["jurisdiction_path"])
    assert div_path.exists()
    assert jur_path.exists()

    div_data = yaml.safe_load(div_path.read_text(encoding="utf-8"))
    assert div_data["ocdid"] == "ocd-division/country:us/state:wa"
    assert div_data["country"] == "us"
    assert div_data["display_name"]  # non-empty

    jur_data = yaml.safe_load(jur_path.read_text(encoding="utf-8"))
    assert jur_data["ocdid"] == "ocd-jurisdiction/country:us/state:wa/government"
    assert jur_data["classification"] == "government"


def test_ensure_ancestor_stubs_creates_county_stub(tmp_path: Path):
    """State and county stubs are both created for a state/county/place OCD ID."""
    parsed = _make_parsed("ocd-division/country:us/state:ca/county:marin/place:sausalito")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    assert len(results) == 2
    levels = {r["level"] for r in results}
    assert levels == {"state", "county"}

    for result in results:
        assert result["action"] == "created"
        assert Path(result["division_path"]).exists()
        assert Path(result["jurisdiction_path"]).exists()

    county_result = next(r for r in results if r["level"] == "county")
    div_data = yaml.safe_load(Path(county_result["division_path"]).read_text(encoding="utf-8"))
    assert div_data["ocdid"] == "ocd-division/country:us/state:ca/county:marin"
    assert "county" in div_data["display_name"].lower()


def test_ensure_ancestor_stubs_division_uses_model_fields(tmp_path: Path):
    """Division YAML produced by the stub contains model-validated fields."""
    parsed = _make_parsed("ocd-division/country:us/state:tx/place:austin")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    div_data = yaml.safe_load(Path(results[0]["division_path"]).read_text(encoding="utf-8"))
    # Fields set by Division model
    assert "ocdid" in div_data
    assert "country" in div_data
    assert "display_name" in div_data
    assert "jurisdiction_id" in div_data
    assert div_data["jurisdiction_id"].startswith("ocd-jurisdiction/")
    assert "government_identifiers" in div_data
    assert "sourcing" in div_data
    assert "last_updated" in div_data


def test_ensure_ancestor_stubs_jurisdiction_uses_model_fields(tmp_path: Path):
    """Jurisdiction YAML produced by the stub contains model-validated fields."""
    parsed = _make_parsed("ocd-division/country:us/state:tx/place:austin")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    jur_data = yaml.safe_load(Path(results[0]["jurisdiction_path"]).read_text(encoding="utf-8"))
    assert "ocdid" in jur_data
    assert "name" in jur_data
    assert "url" in jur_data
    assert "classification" in jur_data
    assert "sourcing" in jur_data
    assert "last_updated" in jur_data


def test_ensure_ancestor_stubs_idempotent(tmp_path: Path):
    """Running twice produces no additional writes."""
    parsed = _make_parsed("ocd-division/country:us/state:wa/place:seattle")

    first = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)
    assert all(r["action"] == "created" for r in first)

    second = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)
    assert all(r["action"] == "skipped" for r in second)

    state_div_dir = tmp_path / "divisions" / "wa"
    yaml_files = list(state_div_dir.glob("*.yaml"))
    assert len(yaml_files) == 1


def test_ensure_ancestor_stubs_no_ancestors_for_state(tmp_path: Path):
    """A state-level OCD ID has no ancestors so the result is an empty list."""
    parsed = _make_parsed("ocd-division/country:us/state:wa")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)
    assert results == []


def test_ensure_ancestor_stubs_directory_layout_state(tmp_path: Path):
    """State stubs are written under {output}/divisions/{state}/, not local/."""
    parsed = _make_parsed("ocd-division/country:us/state:tx/place:austin")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    div_path = Path(results[0]["division_path"])
    assert "tx" in div_path.parts
    assert "local" not in div_path.parts


def test_ensure_ancestor_stubs_directory_layout_county(tmp_path: Path):
    """County stubs are written under {output}/divisions/{state}/county/."""
    parsed = _make_parsed("ocd-division/country:us/state:ca/county:marin/place:sausalito")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    county_result = next(r for r in results if r["level"] == "county")
    div_path = Path(county_result["division_path"])
    assert "county" in div_path.parts


def test_ensure_ancestor_stubs_ocdid_field_matches(tmp_path: Path):
    """The ocdid field in each stub YAML matches the ancestor's raw_ocdid."""
    parsed = _make_parsed("ocd-division/country:us/state:wa/place:tacoma")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    for result in results:
        data = yaml.safe_load(Path(result["division_path"]).read_text(encoding="utf-8"))
        assert data["ocdid"] == result["ocdid"]


def test_ensure_ancestor_stubs_jur_ocdid_format(tmp_path: Path):
    """Jurisdiction stub uses the correct ocd-jurisdiction/…/government format."""
    parsed = _make_parsed("ocd-division/country:us/state:wa/place:seattle")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    jur_data = yaml.safe_load(Path(results[0]["jurisdiction_path"]).read_text(encoding="utf-8"))
    assert jur_data["ocdid"].startswith("ocd-jurisdiction/")
    assert jur_data["ocdid"].endswith("/government")


def test_ensure_ancestor_stubs_country_from_parsed_ocdid(tmp_path: Path):
    """The country field in the Division stub comes from the OCDidParsed object."""
    parsed = _make_parsed("ocd-division/country:us/state:wa/place:seattle")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    div_data = yaml.safe_load(Path(results[0]["division_path"]).read_text(encoding="utf-8"))
    assert div_data["country"] == parsed.country
