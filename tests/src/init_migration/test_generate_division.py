import pytest
from datetime import datetime, timezone
from uuid import UUID
from uuid import NAMESPACE_URL, uuid5

from src.init_migration.pipeline_models import GeneratorReq, OCDidIngestResp
from src.init_migration.generate_division import DivGenerator
from src.models.ocdid import OCDIdParsed
from src.models.division import Division, find_identifier
from pathlib import Path


@pytest.fixture
def sample_req(tmp_path) -> GeneratorReq:
    """Create a GeneratorReq with current OCDidIngestResp types."""
    parsed = OCDIdParsed.parse_ocdid("ocd-division/country:us/state:ca")
    resp = OCDidIngestResp(
        uuid=uuid5(
            NAMESPACE_URL,
            f"ocd-division/country:us/state:ca|{datetime.now(timezone.utc).date().isoformat()}",
        ),
        ocdid=parsed,
        raw_record={},
    )
    req = GeneratorReq(
        data=resp,
        build_base_object=False,
        jurisdiction_ai_url=False,
        division_geo_req=False,
        division_population_req=False,
    )
    return req


@pytest.fixture()
def sample_validation_csv(tmp_path) -> Path:
    csv_path = tmp_path / "validation.csv"
    csv_path.write_text("STATEFP,name\n06,Los Angeles\n12,Miami\n")
    return csv_path


def test_div_generator_initializes(sample_req):
    """DivGenerator should initialize with parsed ocdid and state lookup."""
    dg = DivGenerator(req=sample_req)

    # parsed_ocdid should be a dict from ocdid_parser()
    assert isinstance(dg.parsed_ocdid, dict)
    assert dg.parsed_ocdid.get("state") == "ca"
    assert dg.parsed_ocdid.get("country") == "us"

    # state_lookup should be loaded
    assert isinstance(dg.state_lookup, list)
    assert len(dg.state_lookup) > 0

    # uuid should be a UUID5 object
    assert isinstance(dg.uuid, UUID)
    assert dg.uuid.version == 5

    # division should be None before generation
    assert dg.division is None


def _req_for(ocdid: str) -> GeneratorReq:
    parsed = OCDIdParsed.parse_ocdid(ocdid)
    resp = OCDidIngestResp(
        uuid=uuid5(
            NAMESPACE_URL,
            f"{ocdid}|{datetime.now(timezone.utc).date().isoformat()}",
        ),
        ocdid=parsed,
        raw_record={},
    )
    return GeneratorReq(
        data=resp,
        build_base_object=False,
        jurisdiction_ai_url=False,
        division_geo_req=False,
        division_population_req=False,
    )


# A county row as it comes off the Counties validation tab.
COUNTY_VAL_REC = {
    "GEOID_Census": "47009",
    "STATEFP": "47",
    "NAMELSAD": "Blount County",
    "LSAD": "06",
    "SLDUST_list": "",
    "SLDLST_list": "",
    "COUNTYFP_list": "009",
    "COUNTY_NAMES": "Blount",
    "COUSUBFP": "",
    "PLACEFP": "",
    "layer": "tl_2025_47_county",
}


def test_generate_division_from_county_record():
    """A bare `county:` OCDid takes its display name from the county NAMELSAD."""
    ocdid = "ocd-division/country:us/state:tn/county:blount"
    dg = DivGenerator(req=_req_for(ocdid))

    division = dg.generate_division(COUNTY_VAL_REC, dg.uuid)

    assert division.display_name == "Blount"
    assert find_identifier(division.government_identifiers, "geoid") == "47009"
    assert find_identifier(division.government_identifiers, "statefp") == "47"
    assert find_identifier(division.government_identifiers, "countyfp") == "009"
    assert find_identifier(division.government_identifiers, "county_names") == "Blount"


@pytest.mark.parametrize(
    ("ocdid", "expected_name"),
    [
        (
            "ocd-division/country:us/state:tn/county:blount/council_district:1",
            "Blount County Council District 1",
        ),
        (
            "ocd-division/country:us/state:tn/county:blount/council_district:10",
            "Blount County Council District 10",
        ),
    ],
)
def test_county_council_districts_get_distinct_names(ocdid, expected_name):
    """Council districts under a county are named per district, not per county.

    All districts in a county match the same county row, so without the
    district in the name they would share a display name and — since the
    filename is display name plus GEOID — overwrite each other.
    """
    dg = DivGenerator(req=_req_for(ocdid))

    division = dg.generate_division(COUNTY_VAL_REC, dg.uuid)

    assert division.display_name == expected_name


def test_county_council_district_name_keeps_the_entity_word():
    """The NAMELSAD drives the name, so parishes and boroughs stay correct."""
    ocdid = "ocd-division/country:us/state:la/county:orleans/council_district:2"
    val_rec = dict(
        COUNTY_VAL_REC,
        NAMELSAD="Orleans Parish",
        STATEFP="22",
        GEOID_Census="22071",
        COUNTY_NAMES="Orleans",
    )
    dg = DivGenerator(req=_req_for(ocdid))

    division = dg.generate_division(val_rec, dg.uuid)

    assert division.display_name == "Orleans Parish Council District 2"


def test_generate_division_reuses_existing_ocdid(tmp_path, monkeypatch):
    """An existing Division OCD ID should be reused instead of duplicated."""
    import yaml

    monkeypatch.chdir(tmp_path)

    ocdid = "ocd-division/country:us/state:wa/place:seattle"
    req = _req_for(ocdid)

    existing = Division(
        id=uuid5(NAMESPACE_URL, "existing-seattle"),
        ocdid=ocdid,
        country="us",
        display_name="Existing Seattle",
        jurisdiction_id=(
            "ocd-jurisdiction/country:us/state:wa/place:seattle/government"
        ),
    )

    div_dir = tmp_path / "divisions" / "wa" / "local"
    div_dir.mkdir(parents=True)
    existing_path = div_dir / "existing_seattle.yaml"
    existing_path.write_text(
        yaml.safe_dump(existing.model_dump(mode="json"), sort_keys=False)
    )

    val_rec = {
        "GEOID_Census": "5363000",
        "STATEFP": "53",
        "NAMELSAD": "Seattle city",
        "LSAD": "25",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "033",
        "COUNTY_NAMES": "King",
        "COUSUBFP": "",
        "PLACEFP": "63000",
        "layer": "tl_2025_53_place",
    }

    dg = DivGenerator(req=req)
    result = dg.generate_division(val_rec, dg.uuid)
    output_path = dg.dump_division(output_dir=tmp_path)

    assert result.id == existing.id
    assert result.ocdid == ocdid
    assert result.display_name == "Existing Seattle"
    assert output_path.resolve() == existing_path.resolve()
    assert len(list(div_dir.glob("*.yaml"))) == 1


def test_generate_division_reuses_existing_dc_district_ocdid(tmp_path, monkeypatch):
    """DC district OCD IDs should reuse existing YAML under divisions/dc/local."""
    import yaml

    monkeypatch.chdir(tmp_path)

    ocdid = "ocd-division/country:us/district:dc/anc:1a/council_district:1"
    existing = Division(
        id=uuid5(NAMESPACE_URL, "existing-dc-anc-1a-district-1"),
        ocdid=ocdid,
        country="us",
        display_name="Existing ANC 1A District 1",
        jurisdiction_id="ocd-jurisdiction/country:us/district:dc/anc:1a/government",
    )

    div_dir = tmp_path / "divisions" / "dc" / "local"
    div_dir.mkdir(parents=True)
    existing_path = div_dir / "existing_dc_anc.yaml"
    existing_path.write_text(
        yaml.safe_dump(existing.model_dump(mode="json"), sort_keys=False)
    )

    dg = DivGenerator(req=_req_for(ocdid))
    result = dg.generate_division(
        {
            "GEOID_Census": "",
            "STATEFP": "11",
            "NAMELSAD": "ANC 1A",
            "LSAD": "",
            "SLDUST_list": "",
            "SLDLST_list": "",
            "COUNTYFP_list": "",
            "COUNTY_NAMES": "",
            "COUSUBFP": "",
            "PLACEFP": "",
            "layer": "dcgis_anc",
        },
        dg.uuid,
    )
    output_path = dg.dump_division(output_dir=tmp_path)

    assert result.id == existing.id
    assert result.display_name == "Existing ANC 1A District 1"
    assert output_path.resolve() == existing_path.resolve()
    assert len(list(div_dir.glob("*.yaml"))) == 1


def test_dump_division_uses_dc_directory_for_district_ocdid(tmp_path, monkeypatch):
    """A new DC district Division should be written under divisions/dc/local."""
    monkeypatch.chdir(tmp_path)

    ocdid = "ocd-division/country:us/district:dc/anc:1a/council_district:2"
    dg = DivGenerator(req=_req_for(ocdid))

    dg.generate_division(
        {
            "GEOID_Census": "",
            "STATEFP": "11",
            "NAMELSAD": "ANC 1A",
            "LSAD": "",
            "SLDUST_list": "",
            "SLDLST_list": "",
            "COUNTYFP_list": "",
            "COUNTY_NAMES": "",
            "COUSUBFP": "",
            "PLACEFP": "",
            "layer": "dcgis_anc",
        },
        dg.uuid,
    )
    output_path = dg.dump_division(output_dir=tmp_path)

    assert output_path.parent.resolve() == (
        tmp_path / "divisions" / "dc" / "local"
    ).resolve()
    assert output_path.exists()
