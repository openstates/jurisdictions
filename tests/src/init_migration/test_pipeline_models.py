"""Tests for pipeline_models — specifically the OCDidIngestResp model changes."""
import pytest
from src.init_migration.pipeline_models import OCDidIngestResp
from src.models.ocdid import OCDidParsed
from src.utils.deterministic_id import generate_id


def test_ocdid_ingest_resp_accepts_ocdid_parsed():
    """OCDidIngestResp.ocdid should accept an OCDidParsed instance."""
    parsed = OCDidParsed(
        country="us",
        state="wa",
        place="seattle",
        raw_ocdid="ocd-division/country:us/state:wa/place:seattle",
    )
    det_id = generate_id("ocd-division/country:us/state:wa/place:seattle")
    resp = OCDidIngestResp(
        uuid=det_id,
        ocdid=parsed,
        raw_record={"id": "ocd-division/country:us/state:wa/place:seattle", "name": "Seattle"},
    )
    assert resp.ocdid.state == "wa"
    assert resp.ocdid.place == "seattle"
    assert resp.ocdid.raw_ocdid == "ocd-division/country:us/state:wa/place:seattle"


def test_ocdid_ingest_resp_uuid_is_oid1_string():
    """OCDidIngestResp.uuid should accept an oid1- deterministic ID string."""
    parsed = OCDidParsed(
        country="us",
        state="wa",
        place="seattle",
        raw_ocdid="ocd-division/country:us/state:wa/place:seattle",
    )
    det_id = generate_id("ocd-division/country:us/state:wa/place:seattle")
    resp = OCDidIngestResp(
        uuid=det_id,
        ocdid=parsed,
        raw_record={},
    )
    assert isinstance(resp.uuid, str)
    assert resp.uuid.startswith("oid1-")


def test_ocdid_ingest_resp_rejects_plain_string_for_ocdid():
    """OCDidIngestResp.ocdid should not accept a plain string."""
    with pytest.raises(Exception):
        OCDidIngestResp(
            uuid="oid1-fake",
            ocdid="ocd-division/country:us/state:wa/place:seattle",
            raw_record={},
        )
