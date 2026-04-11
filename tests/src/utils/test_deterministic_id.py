from uuid import UUID

from src.utils.deterministic_id import build_uuid5_name, decode_id, generate_id, verify_id


def test_generate_id_from_ocdid_and_date_is_deterministic():
    ocdid = "ocd-division/country:us/state:wa/place:seattle"
    ident = generate_id(ocdid, "2026-04-08")
    ident2 = generate_id(ocdid, "2026-04-08")
    assert ident == ident2
    assert isinstance(ident, UUID)
    assert ident.version == 5


def test_generate_id_changes_with_date():
    ocdid = "ocd-jurisdiction/country:us/state:wa/place:seattle/legislature"
    id_a = generate_id(ocdid, "2026-04-08")
    id_b = generate_id(ocdid, "2026-04-09")
    assert id_a != id_b


def test_different_ocdids_produce_different_ids():
    a = "ocd-division/country:us/state:wa/place:seattle"
    b = "ocd-division/country:us/state:wa/place:tacoma"
    ida = generate_id(a, "2026-04-08")
    idb = generate_id(b, "2026-04-08")
    assert ida != idb


def test_verify_id_true_and_false_cases():
    o = "ocd-division/country:us/state:tx/place:austin"
    ident = generate_id(o, "2026-04-08")
    assert verify_id(ident, o, "2026-04-08") is True
    assert verify_id(ident, o, "2026-04-09") is False


def test_decode_id_reports_uuid5_not_decodable():
    ocdid = "ocd-division/country:us/state:tx/place:austin"
    ident = generate_id(ocdid, "2026-04-08")
    decoded = decode_id(ident)
    assert decoded.identifier == str(ident)
    assert decoded.is_decodable is False
    assert decoded.reason is not None


def test_build_uuid5_name_includes_ocdid_and_date():
    ocdid = "ocd-division/country:us/state:wa/place:seattle"
    assert build_uuid5_name(ocdid, "2026-04-08") == f"{ocdid}|2026-04-08"
