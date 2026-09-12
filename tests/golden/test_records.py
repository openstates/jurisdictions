# tests/golden/test_records.py
from tests.golden.records import make_division, make_jurisdiction


def test_records_build_and_have_stable_ids():
    division = make_division()
    jurisdiction = make_jurisdiction()
    assert division.id is not None
    assert jurisdiction.id is not None
    # Rebuilding the same record yields the same UUID (deterministic identity).
    assert make_division().id == division.id
    assert make_jurisdiction().id == jurisdiction.id
