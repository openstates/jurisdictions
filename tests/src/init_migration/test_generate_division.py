


import pytest

from src.init_migration.models import GeneratorReq, OCDidIngestResp
from src.init_migration.generate_division import DivGenerator
import uuid
from pathlib import Path
import uuid
from pathlib import Path

import polars as pl
import pytest


@pytest.fixture
def sample_req(tmp_path) -> GeneratorReq:
    # Create a fake OCDidIngestResp
    resp = OCDidIngestResp(
        uuid=uuid.UUID(int=0),
        filepath=tmp_path / "fake.yaml",
        ocdid="ocd-division/country:us/state:ca",
        raw_record={}
    )

    req = GeneratorReq(
        data=resp,
        build_base_object=False,
        ai_url=False,
        geo_req=False,
        population_req=False,
    )
    return req


@pytest.fixture()
def sample_validation_csv(tmp_path) -> Path:
    csv_path = tmp_path / "validation.csv"
    csv_path.write_text("STATEFP,name\n06,Los Angeles\n12,Miami\n")
    return csv_path

def test_load_verification_data_lookup(tmp_path, sample_req, sample_validation_csv):
    # Create a small CSV file to act as the validation dataset
    csv_path = tmp_path / "validation.csv"
    csv_path.write_text("STATEFP,name\n06,Los Angeles\n12,Miami\n")

    # Build minimal request objects required by DivGenerator
    resp = OCDidIngestResp(
        uuid=uuid.UUID(int=0),
        filepath=Path("/tmp/fake.yaml"),
        ocdid="ocd-division/country:us/state:ca",
        raw_record={}
    )

    req = GeneratorReq(
        data=resp,
        build_base_object=False,
        ai_url=False,
        geo_req=False,
        population_req=False,
    )

    dg = DivGenerator(req=req, validation_data_filepath=str(csv_path))

    # verification_data should be loaded during instantiation
    assert hasattr(dg, "verification_data")
    df = dg.verification_data
    assert isinstance(df, pl.DataFrame)
    # Ensure two rows were read
    assert df.shape[0] == 2
    # STATEFP may be parsed as integers; normalize to strings for comparison
    vals = {str(v) for v in df["STATEFP"].to_list()}
    assert vals == {"6", "12"}