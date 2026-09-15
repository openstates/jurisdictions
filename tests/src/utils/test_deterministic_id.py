from uuid import NAMESPACE_URL, UUID, uuid5

from src.utils.deterministic_id import decode_id, generate_id, verify_id


def test_generate_id_is_uuid5_of_the_ocdid_alone():
    ocdid = "ocd-division/country:us/state:wa/place:seattle"
    ident = generate_id(ocdid)
    assert isinstance(ident, UUID)
    assert ident.version == 5
    assert ident == uuid5(NAMESPACE_URL, ocdid)


def test_generate_id_is_deterministic():
    ocdid = "ocd-jurisdiction/country:us/state:wa/place:seattle/legislature"
    assert generate_id(ocdid) == generate_id(ocdid)


def test_different_ocdids_produce_different_ids():
    a = "ocd-division/country:us/state:wa/place:seattle"
    b = "ocd-division/country:us/state:wa/place:tacoma"
    assert generate_id(a) != generate_id(b)


def test_division_and_jurisdiction_ids_for_the_same_place_differ():
    division = "ocd-division/country:us/state:tx/place:austin"
    jurisdiction = "ocd-jurisdiction/country:us/state:tx/place:austin/government"
    assert generate_id(division) != generate_id(jurisdiction)


def test_verify_id_true_and_false_cases():
    ocdid = "ocd-division/country:us/state:tx/place:austin"
    ident = generate_id(ocdid)
    assert verify_id(ident, ocdid) is True
    assert verify_id(str(ident), ocdid) is True
    assert verify_id(ident, "ocd-division/country:us/state:tx/place:dallas") is False


def test_decode_id_reports_uuid5_not_decodable():
    ocdid = "ocd-division/country:us/state:tx/place:austin"
    ident = generate_id(ocdid)
    decoded = decode_id(ident)
    assert decoded.identifier == str(ident)
    assert decoded.is_decodable is False
    assert decoded.reason is not None
