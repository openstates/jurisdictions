from datetime import datetime, timezone

import pytest

from tests.golden.records import FIXED_TS, make_division, make_geometry


@pytest.mark.integration
def test_uuid_stable_when_display_name_changes():
    a = make_division(display_name="Seattle")
    b = make_division(display_name="City of Seattle")
    assert a.ocdid == b.ocdid
    assert a.id == b.id


@pytest.mark.integration
def test_uuid_stable_when_geometry_changes():
    a = make_division(geometries=[make_geometry(None, None)])
    b = make_division(geometries=[])
    assert a.id == b.id


@pytest.mark.integration
@pytest.mark.xfail(strict=True, reason="blocked on #133 Task 2.1 — stable UUID")
def test_uuid_stable_when_retrieval_date_changes():
    a = make_division(last_updated=FIXED_TS)
    b = make_division(last_updated=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert a.id == b.id
