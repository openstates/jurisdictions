from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.init_migration.generate_recursive import ensure_ancestor_stubs, stub_exists
from src.models.ocdid import OCDIdParsed


# ---------------------------------------------------------------------------
# OCDidParsed.build_ancestors — pure, no I/O
# ---------------------------------------------------------------------------


def test_build_ancestors_place():
    """State is the only ancestor for a state/place OCD ID."""
    ocdid = "ocd-division/country:us/state:wa/place:seattle"
    parsed = OCDIdParsed.parse_ocdid(ocdid)
    result = OCDIdParsed.build_ancestor_ocdids(parsed)
    assert [ancestor.raw_ocdid for ancestor in result] == [
        "ocd-division/country:us/state:wa"
    ]


def test_build_ancestors_county_place():
    """State then county are returned for a state/county/place OCD ID."""
    ocdid = "ocd-division/country:us/state:ca/county:marin/place:sausalito"
    parsed = OCDIdParsed.parse_ocdid(ocdid)
    result = OCDIdParsed.build_ancestor_ocdids(parsed)
    assert [ancestor.raw_ocdid for ancestor in result] == [
        "ocd-division/country:us/state:ca",
        "ocd-division/country:us/state:ca/county:marin",
    ]


def test_build_ancestors_council_district():
    """Place is an ancestor of a council_district OCD ID."""
    ocdid = "ocd-division/country:us/state:wa/place:seattle/council_district:1"
    parsed = OCDIdParsed.parse_ocdid(ocdid)
    result = OCDIdParsed.build_ancestor_ocdids(parsed)
    assert [ancestor.raw_ocdid for ancestor in result] == [
        "ocd-division/country:us/state:wa",
        "ocd-division/country:us/state:wa/place:seattle",
    ]


def test_build_ancestor_ocdids_leaf_excluded():
    """The leaf node itself is never in the ancestor list."""
    ocdid = "ocd-division/country:us/state:tx/place:austin"
    parsed = OCDIdParsed.parse_ocdid(ocdid)
    result = OCDIdParsed.build_ancestor_ocdids(parsed)
    assert ocdid not in [ancestor.raw_ocdid for ancestor in result]


def test_build_ancestor_ocdids_state_only():
    """A state-level OCD ID has no ancestors to stub."""
    ocdid = "ocd-division/country:us/state:wa"
    parsed = OCDIdParsed.parse_ocdid(ocdid)
    result = OCDIdParsed.build_ancestor_ocdids(parsed)
    assert result == []


# ---------------------------------------------------------------------------
# stub_exists — filesystem check
# ---------------------------------------------------------------------------


def test_stub_exists_missing_dir(tmp_path: Path):
    """Returns False for a directory that does not exist."""
    assert (
        stub_exists("ocd-division/country:us/state:wa", tmp_path / "nowhere") is False
    )


def test_stub_exists_empty_dir(tmp_path: Path):
    """Returns False when the directory is present but empty."""
    assert stub_exists("ocd-division/country:us/state:wa", tmp_path) is False


def test_stub_exists_match(tmp_path: Path):
    """Returns True when a YAML file contains a matching ocdid field."""
    ocdid = "ocd-division/country:us/state:wa"
    stub = tmp_path / "washington_state_67ec4ce3-3799-5980-a12f-c5c45c9229c3.yaml"
    stub.write_text(
        yaml.dump({"ocdid": ocdid, "display_name": "Washington"}), encoding="utf-8"
    )
    assert stub_exists(ocdid, tmp_path) is True


def test_stub_exists_no_match(tmp_path: Path):
    """Returns False when YAML files exist but none matches the given ocdid."""
    stub = tmp_path / "oregon_67ec4ce3-3799-5980-a12f-c5c45c9229c3.yaml"
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
    parsed = OCDIdParsed.parse_ocdid("ocd-division/country:us/state:wa/place:seattle")
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
    assert div_path.name.endswith(f"_{div_data['id']}.yaml")
    assert "_stub" not in div_path.name
    assert div_data["ocdid"] == "ocd-division/country:us/state:wa"
    assert div_data["country"] == "us"
    assert div_data["display_name"]  # non-empty

    jur_data = yaml.safe_load(jur_path.read_text(encoding="utf-8"))
    assert jur_path.name.endswith(f"_{jur_data['id']}.yaml")
    assert "_stub" not in jur_path.name
    assert jur_data["ocdid"] == "ocd-jurisdiction/country:us/state:wa/government"
    assert jur_data["classification"] == "government"


def test_ensure_ancestor_stubs_creates_county_stub(tmp_path: Path):
    """State and county stubs are both created for a state/county/place OCD ID."""
    parsed = OCDIdParsed.parse_ocdid(
        "ocd-division/country:us/state:ca/county:marin/place:sausalito"
    )
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    assert len(results) == 2
    levels = {r["level"] for r in results}
    assert levels == {"state", "county"}

    for result in results:
        assert result["action"] == "created"
        assert Path(result["division_path"]).exists()
        assert Path(result["jurisdiction_path"]).exists()

    county_result = next(r for r in results if r["level"] == "county")
    div_data = yaml.safe_load(
        Path(county_result["division_path"]).read_text(encoding="utf-8")
    )
    assert div_data["ocdid"] == "ocd-division/country:us/state:ca/county:marin"
    assert "county" in div_data["display_name"].lower()


def test_ensure_ancestor_stubs_division_uses_model_fields(tmp_path: Path):
    """Division YAML produced by the stub contains model-validated fields."""
    parsed = OCDIdParsed.parse_ocdid("ocd-division/country:us/state:tx/place:austin")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    div_data = yaml.safe_load(
        Path(results[0]["division_path"]).read_text(encoding="utf-8")
    )
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
    parsed = OCDIdParsed.parse_ocdid("ocd-division/country:us/state:tx/place:austin")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    jur_data = yaml.safe_load(
        Path(results[0]["jurisdiction_path"]).read_text(encoding="utf-8")
    )
    assert "ocdid" in jur_data
    assert "name" in jur_data
    assert "url" in jur_data
    assert "classification" in jur_data
    assert "sourcing" in jur_data
    assert "last_updated" in jur_data


def test_ensure_ancestor_stubs_idempotent(tmp_path: Path):
    """Running twice produces no additional writes."""
    parsed = OCDIdParsed.parse_ocdid("ocd-division/country:us/state:wa/place:seattle")

    first = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)
    assert all(r["action"] == "created" for r in first)

    second = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)
    assert all(r["action"] == "skipped" for r in second)

    state_div_dir = tmp_path / "divisions" / "wa"
    yaml_files = list(state_div_dir.glob("*.yaml"))
    assert len(yaml_files) == 1


def test_ensure_ancestor_stubs_no_ancestors_for_state(tmp_path: Path):
    """A state-level OCD ID has no ancestors so the result is an empty list."""
    parsed = OCDIdParsed.parse_ocdid("ocd-division/country:us/state:wa")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)
    assert results == []


def test_ensure_ancestor_stubs_directory_layout_state(tmp_path: Path):
    """State stubs are written under {output}/divisions/{state}/, not local/."""
    parsed = OCDIdParsed.parse_ocdid("ocd-division/country:us/state:tx/place:austin")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    div_path = Path(results[0]["division_path"])
    assert "tx" in div_path.parts
    assert "local" not in div_path.parts


def test_ensure_ancestor_stubs_directory_layout_county(tmp_path: Path):
    """County stubs are written under {output}/divisions/{state}/county/."""
    parsed = OCDIdParsed.parse_ocdid(
        "ocd-division/country:us/state:ca/county:marin/place:sausalito"
    )
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    county_result = next(r for r in results if r["level"] == "county")
    div_path = Path(county_result["division_path"])
    assert "county" in div_path.parts


def test_ensure_ancestor_stubs_ocdid_field_matches(tmp_path: Path):
    """The ocdid field in each stub YAML matches the ancestor's raw_ocdid."""
    parsed = OCDIdParsed.parse_ocdid("ocd-division/country:us/state:wa/place:tacoma")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    for result in results:
        data = yaml.safe_load(Path(result["division_path"]).read_text(encoding="utf-8"))
        assert data["ocdid"] == result["ocdid"]


def test_ensure_ancestor_stubs_jur_ocdid_format(tmp_path: Path):
    """Jurisdiction stub uses the correct ocd-jurisdiction/…/government format."""
    parsed = OCDIdParsed.parse_ocdid("ocd-division/country:us/state:wa/place:seattle")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    jur_data = yaml.safe_load(
        Path(results[0]["jurisdiction_path"]).read_text(encoding="utf-8")
    )
    assert jur_data["ocdid"].startswith("ocd-jurisdiction/")
    assert jur_data["ocdid"].endswith("/government")


def test_ensure_ancestor_stubs_country_from_parsed_ocdid(tmp_path: Path):
    """The country field in the Division stub comes from the OCDidParsed object."""
    parsed = OCDIdParsed.parse_ocdid("ocd-division/country:us/state:wa/place:seattle")
    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)

    div_data = yaml.safe_load(
        Path(results[0]["division_path"]).read_text(encoding="utf-8")
    )
    assert div_data["country"] == parsed.country



def test_place_ancestor_uses_local_layout_and_name(tmp_path: Path):
    """Austin place ancestry must not be misclassified as Texas state ancestry."""
    parsed = OCDIdParsed.parse_ocdid(
        "ocd-division/country:us/state:tx/place:austin/council_district:1"
    )

    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)
    place_result = next(r for r in results if r["level"] == "place")

    div_path = Path(place_result["division_path"])
    jur_path = Path(place_result["jurisdiction_path"])

    assert div_path.parent == tmp_path / "divisions" / "tx" / "local"
    assert jur_path.parent == tmp_path / "jurisdictions" / "tx" / "local"

    div = yaml.safe_load(div_path.read_text())
    jur = yaml.safe_load(jur_path.read_text())

    assert div["ocdid"] == "ocd-division/country:us/state:tx/place:austin"
    assert div["display_name"] == "Austin"
    assert jur["ocdid"] == (
        "ocd-jurisdiction/country:us/state:tx/place:austin/government"
    )
    assert jur["name"] == "Austin Government"

    ids = {
        item["id_type"]: item["value"]
        for item in div["government_identifiers"]
    }
    assert ids["statefp"] == "48"
    assert "geoid" not in ids


def test_county_ancestor_reuses_local_parent_jurisdiction(tmp_path: Path):
    """County ancestry must reuse a government already created in local/."""
    jur_dir = tmp_path / "jurisdictions" / "tx" / "local"
    jur_dir.mkdir(parents=True)

    jur_ocdid = "ocd-jurisdiction/country:us/state:tx/county:anderson/government"
    existing = jur_dir / "anderson_existing.yaml"
    existing.write_text(yaml.safe_dump({"ocdid": jur_ocdid}))

    parsed = OCDIdParsed.parse_ocdid(
        "ocd-division/country:us/state:tx/county:anderson/council_district:1"
    )

    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)
    county = next(r for r in results if r["level"] == "county")

    assert county["division_path"] is not None
    assert county["jurisdiction_path"] is None

    matches = [
        path
        for path in (tmp_path / "jurisdictions" / "tx").rglob("*.yaml")
        if (yaml.safe_load(path.read_text()) or {}).get("ocdid") == jur_ocdid
    ]
    assert matches == [existing]


def test_wrong_path_existing_place_identity_is_reused(tmp_path: Path):
    """A historical wrong-path place stub must not create a second identity."""
    div_root = tmp_path / "divisions" / "tx"
    jur_root = tmp_path / "jurisdictions" / "tx"
    div_root.mkdir(parents=True)
    jur_root.mkdir(parents=True)

    div_ocdid = "ocd-division/country:us/state:tx/place:austin"
    jur_ocdid = "ocd-jurisdiction/country:us/state:tx/place:austin/government"

    old_div = div_root / "texas_old.yaml"
    old_jur = jur_root / "texas_old.yaml"

    old_div.write_text(yaml.safe_dump({"ocdid": div_ocdid}))
    old_jur.write_text(yaml.safe_dump({"ocdid": jur_ocdid}))

    parsed = OCDIdParsed.parse_ocdid(
        "ocd-division/country:us/state:tx/place:austin/council_district:1"
    )

    results = ensure_ancestor_stubs(parsed, tmp_path, tmp_path)
    place = next(r for r in results if r["level"] == "place")

    assert place["action"] == "skipped"

    div_matches = [
        path
        for path in div_root.rglob("*.yaml")
        if (yaml.safe_load(path.read_text()) or {}).get("ocdid") == div_ocdid
    ]
    jur_matches = [
        path
        for path in jur_root.rglob("*.yaml")
        if (yaml.safe_load(path.read_text()) or {}).get("ocdid") == jur_ocdid
    ]

    assert div_matches == [old_div]
    assert jur_matches == [old_jur]


def test_duplicate_ancestor_jurisdiction_fails_closed(tmp_path: Path):
    """One canonical Jurisdiction OCDID must not exist in two files."""
    jur_ocdid = "ocd-jurisdiction/country:us/state:tx/county:anderson/government"

    local = tmp_path / "jurisdictions" / "tx" / "local"
    county = tmp_path / "jurisdictions" / "tx" / "county"
    local.mkdir(parents=True)
    county.mkdir(parents=True)

    (local / "anderson.yaml").write_text(yaml.safe_dump({"ocdid": jur_ocdid}))
    (county / "anderson_county.yaml").write_text(
        yaml.safe_dump({"ocdid": jur_ocdid})
    )

    parsed = OCDIdParsed.parse_ocdid(
        "ocd-division/country:us/state:tx/county:anderson/council_district:1"
    )

    with pytest.raises(ValueError, match="Duplicate ancestor Jurisdiction OCDID"):
        ensure_ancestor_stubs(parsed, tmp_path, tmp_path)
