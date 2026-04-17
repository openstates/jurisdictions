"""Tests for pipeline_models — specifically the OCDidIngestResp model changes."""
from uuid import UUID
from uuid import NAMESPACE_URL, uuid5

import pytest
from src.init_migration.pipeline_models import OCDidIngestResp
from src.models.ocdid import OCDidParsed


def test_ocdid_ingest_resp_accepts_ocdid_parsed():
    """OCDidIngestResp.ocdid should accept an OCDidParsed instance."""
    parsed = OCDidParsed(
        country="us",
        state="wa",
        place="seattle",
        raw_ocdid="ocd-division/country:us/state:wa/place:seattle",
    )
    det_id = uuid5(NAMESPACE_URL, "ocd-division/country:us/state:wa/place:seattle")
    resp = OCDidIngestResp(
        uuid=det_id,
        ocdid=parsed,
        raw_record={"id": "ocd-division/country:us/state:wa/place:seattle", "name": "Seattle"},
    )
    assert resp.ocdid.state == "wa"
    assert resp.ocdid.place == "seattle"
    assert resp.ocdid.raw_ocdid == "ocd-division/country:us/state:wa/place:seattle"


def test_ocdid_ingest_resp_uuid_is_uuid5_string():
    """OCDidIngestResp.uuid should parse to a UUID5 object."""
    parsed = OCDidParsed(
        country="us",
        state="wa",
        place="seattle",
        raw_ocdid="ocd-division/country:us/state:wa/place:seattle",
    )
    det_id = uuid5(NAMESPACE_URL, "ocd-division/country:us/state:wa/place:seattle")
    resp = OCDidIngestResp(
        uuid=det_id,
        ocdid=parsed,
        raw_record={},
    )
    assert isinstance(resp.uuid, UUID)
    assert resp.uuid.version == 5


def test_ocdid_ingest_resp_rejects_plain_string_for_ocdid():
    """OCDidIngestResp.ocdid should not accept a plain string."""
    with pytest.raises(Exception):
        OCDidIngestResp(
            uuid="not-a-valid-ocdid",
            ocdid="ocd-division/country:us/state:wa/place:seattle",
            raw_record={},
        )
