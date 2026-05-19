from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.init_migration.generate_recursive import (
    build_ancestor_ocdids,
    ensure_ancestor_stubs,
    stub_exists,
)


# ---------------------------------------------------------------------------
# build_ancestor_ocdids — pure function, no I/O
# ---------------------------------------------------------------------------


def test_build_ancestor_ocdids_place():
    """State is the only ancestor for a state/place OCD ID."""
    ocdid = "ocd-division/country:us/state:wa/place:seattle"
    result = build_ancestor_ocdids(ocdid)
    assert result == ["ocd-division/country:us/state:wa"]


def test_build_ancestor_ocdids_county_place():
    """State then county are returned for a state/county/place OCD ID."""
    ocdid = "ocd-division/country:us/state:ca/county:marin/place:sausalito"
    result = build_ancestor_ocdids(ocdid)
    assert result == [
        "ocd-division/country:us/state:ca",
        "ocd-division/country:us/state:ca/county:marin",
    ]


def test_build_ancestor_ocdids_council_district():
    """Place is an ancestor of a council_district OCD ID."""
    ocdid = "ocd-division/country:us/state:wa/place:seattle/council_district:1"
    result = build_ancestor_ocdids(ocdid)
    assert result == [
        "ocd-division/country:us/state:wa",
        "ocd-division/country:us/state:wa/place:seattle",
    ]


def test_build_ancestor_ocdids_leaf_excluded():
    """The leaf node itself is never in the ancestor list."""
    ocdid = "ocd-division/country:us/state:tx/place:austin"
    result = build_ancestor_ocdids(ocdid)
    assert ocdid not in result


def test_build_ancestor_ocdids_state_only():
    """A state-level OCD ID has no ancestors to stub."""
    ocdid = "ocd-division/country:us/state:wa"
    result = build_ancestor_ocdids(ocdid)
    assert result == []


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
    stub = tmp_path / "washington_state_stub.yaml"
    stub.write_text(yaml.dump({"ocdid": ocdid, "display_name": "Washington"}), encoding="utf-8")
    assert stub_exists(ocdid, tmp_path) is True


def test_stub_exists_no_match(tmp_path: Path):
    """Returns False when YAML files exist but none matches the given ocdid."""
    stub = tmp_path / "oregon_state_stub.yaml"
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
# ensure_ancestor_stubs — integration (uses real state lookup, tmp_path I/O)
# ---------------------------------------------------------------------------


def test_ensure_ancestor_stubs_creates_state_stub(tmp_path: Path):
    """A state-level stub Division and Jurisdiction are created for a place OCD ID."""
    ocdid = "ocd-division/country:us/state:wa/place:seattle"
    results = ensure_ancestor_stubs(ocdid, tmp_path, tmp_path)

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
    ocdid = "ocd-division/country:us/state:ca/county:marin/place:sausalito"
    results = ensure_ancestor_stubs(ocdid, tmp_path, tmp_path)

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


def test_ensure_ancestor_stubs_idempotent(tmp_path: Path):
    """Running twice does not recreate existing stubs."""
    ocdid = "ocd-division/country:us/state:wa/place:seattle"

    first = ensure_ancestor_stubs(ocdid, tmp_path, tmp_path)
    assert all(r["action"] == "created" for r in first)

    second = ensure_ancestor_stubs(ocdid, tmp_path, tmp_path)
    assert all(r["action"] == "skipped" for r in second)

    # Confirm no duplicate files were written
    state_div_dir = tmp_path / "divisions" / "wa"
    yaml_files = list(state_div_dir.glob("*.yaml"))
    assert len(yaml_files) == 1


def test_ensure_ancestor_stubs_no_ancestors_for_state(tmp_path: Path):
    """A state-level OCD ID has no ancestors to create."""
    ocdid = "ocd-division/country:us/state:wa"
    results = ensure_ancestor_stubs(ocdid, tmp_path, tmp_path)
    assert results == []


def test_ensure_ancestor_stubs_directory_layout(tmp_path: Path):
    """State stubs land in {output}/divisions/{state}/, not in local/."""
    ocdid = "ocd-division/country:us/state:tx/place:austin"
    results = ensure_ancestor_stubs(ocdid, tmp_path, tmp_path)

    assert len(results) == 1
    div_path = Path(results[0]["division_path"])
    # Should be under divisions/tx/ — NOT under divisions/tx/local/
    assert "tx" in div_path.parts
    assert "local" not in div_path.parts


def test_ensure_ancestor_stubs_county_directory_layout(tmp_path: Path):
    """County stubs land in {output}/divisions/{state}/county/."""
    ocdid = "ocd-division/country:us/state:ca/county:marin/place:sausalito"
    results = ensure_ancestor_stubs(ocdid, tmp_path, tmp_path)

    county_result = next(r for r in results if r["level"] == "county")
    div_path = Path(county_result["division_path"])
    assert "county" in div_path.parts


def test_ensure_ancestor_stubs_ocdid_in_div_yaml(tmp_path: Path):
    """The ocdid field in each stub YAML matches the ancestor OCD ID exactly."""
    ocdid = "ocd-division/country:us/state:wa/place:tacoma"
    results = ensure_ancestor_stubs(ocdid, tmp_path, tmp_path)

    for result in results:
        data = yaml.safe_load(Path(result["division_path"]).read_text(encoding="utf-8"))
        assert data["ocdid"] == result["ocdid"]


def test_ensure_ancestor_stubs_jur_ocdid_format(tmp_path: Path):
    """Jurisdiction stub uses the correct ocd-jurisdiction/... prefix."""
    ocdid = "ocd-division/country:us/state:wa/place:seattle"
    results = ensure_ancestor_stubs(ocdid, tmp_path, tmp_path)

    jur_data = yaml.safe_load(Path(results[0]["jurisdiction_path"]).read_text(encoding="utf-8"))
    assert jur_data["ocdid"].startswith("ocd-jurisdiction/")
    assert jur_data["ocdid"].endswith("/government")
