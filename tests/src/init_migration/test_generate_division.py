import pytest
from datetime import datetime, timezone
from uuid import UUID
from uuid import NAMESPACE_URL, uuid5

from src.init_migration.pipeline_models import GeneratorReq, OCDidIngestResp
from src.init_migration.generate_division import DivGenerator, _leaf_segment_display_name
from src.models.ocdid import OCDIdParsed
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


def test_leaf_segment_display_name_returns_council_district():
    # ocd-division/country:us/state:wa/place:seattle/council_district:1
    parsed_ocdid = {"place": "seattle", "council_district": "1"}

    assert _leaf_segment_display_name(parsed_ocdid) == "Seattle Council District 1"


def test_leaf_segment_display_name_returns_ward():
    # ocd-division/country:us/state:oh/place:cincinnati/ward:4
    parsed_ocdid = {"place": "cincinnati", "ward": "4"}

    assert _leaf_segment_display_name(parsed_ocdid) == "Cincinnati Ward 4"


def test_anc_display_name_returns_anc_and_district():
    # ocd-division/country:us/district:dc/anc:1a/council_district:1
    parsed_ocdid = {"district": "dc", "anc": "1a", "council_district": "1"}

    assert _leaf_segment_display_name(parsed_ocdid) == "ANC 1A District 1"


def test_place_display_name_returns_place_and_district():
    # ocd-division/country:us/state:tx/place:austin/council_district:8
    parsed_ocdid = {"place": "austin", "council_district": "8"}

    assert _leaf_segment_display_name(parsed_ocdid) == "Austin Council District 8"


def test_unmatched_string_returns_none():
    # ocd-division/country:us/state:wa/place:seattle
    parsed_ocdid = {"place": "seattle"}

    assert _leaf_segment_display_name(parsed_ocdid) is None
