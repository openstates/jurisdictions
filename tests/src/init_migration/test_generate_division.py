import pytest
from uuid import UUID

from src.init_migration.pipeline_models import GeneratorReq, OCDidIngestResp
from src.init_migration.generate_division import DivGenerator
from src.models.ocdid import OCDidParsed
from src.utils.deterministic_id import generate_id
from pathlib import Path


@pytest.fixture
def sample_req(tmp_path) -> GeneratorReq:
    """Create a GeneratorReq with current OCDidIngestResp types."""
    parsed = OCDidParsed(
        raw_ocdid="ocd-division/country:us/state:ca",
        country="us",
        state="ca",
    )
    resp = OCDidIngestResp(
        uuid=generate_id("ocd-division/country:us/state:ca"),
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
