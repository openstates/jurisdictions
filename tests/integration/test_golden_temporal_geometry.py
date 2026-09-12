from datetime import datetime, timezone

import pytest

from tests.golden.records import make_division, make_geometry


@pytest.mark.integration
def test_two_geometry_periods_serialize_with_provenance():
    closed = make_geometry(
        valid_from=datetime(2012, 1, 1, tzinfo=timezone.utc),
        valid_to=datetime(2022, 12, 4, tzinfo=timezone.utc),
    )
    current = make_geometry(
        valid_from=datetime(2022, 12, 5, tzinfo=timezone.utc),
        valid_to=None,
    )
    data = make_division(geometries=[closed, current]).model_dump(mode="json")
    geoms = data["geometries"]
    assert len(geoms) == 2
    valid_tos = [g["valid_to"] for g in geoms]
    assert None in valid_tos                       # one open-ended current period
    assert any(v is not None for v in valid_tos)   # one closed historical period
    assert all(g["source"] is not None for g in geoms)


@pytest.mark.integration
def test_division_uuid_stable_across_geometry_versions():
    one = make_division(geometries=[make_geometry(None, None)])
    two = make_division(
        geometries=[
            make_geometry(datetime(2012, 1, 1, tzinfo=timezone.utc), None),
            make_geometry(datetime(2022, 1, 1, tzinfo=timezone.utc), None),
        ]
    )
    assert one.id == two.id
