from src.utils.deterministic_id import generate_id, decode_id


def test_roundtrip_default_without_random():
    ocdid = "ocd-division/country:us/state:wa/place:seattle"
    ident = generate_id(ocdid)
    decoded = decode_id(ident)
    assert decoded.ocdid == ocdid
    assert decoded.format_version == 1
    assert decoded.version == "v1"
    assert decoded.random_element is None
    # deterministic: calling again yields same id
    ident2 = generate_id(ocdid)
    assert ident == ident2


def test_roundtrip_with_custom_random_element():
    ocdid = "ocd-jurisdiction/country:us/state:wa/place:seattle/legislature"
    rnd = "abc123"
    ident = generate_id(ocdid, random_element=rnd)
    decoded = decode_id(ident)
    assert decoded.ocdid == ocdid
    assert decoded.random_element == rnd


def test_different_ocdids_produce_different_ids():
    a = "ocd-division/country:us/state:wa/place:seattle"
    b = "ocd-division/country:us/state:wa/place:tacoma"
    ida = generate_id(a)
    idb = generate_id(b)
    assert ida != idb


def test_same_ocdid_different_versions_produce_different_ids():
    o = "ocd-division/country:us/state:tx/place:austin"
    id_v1 = generate_id(o, version="v1")
    id_v2 = generate_id(o, version="v2")
    assert id_v1 != id_v2


def test_format_prefix_and_hyphens():
    ocdid = "ocd-division/country:us/state:tx/place:austin"
    ident = generate_id(ocdid)
    assert ident.startswith("oid1-")
    # should contain at least 4 hyphens after the prefix
    assert ident.count("-") >= 4
