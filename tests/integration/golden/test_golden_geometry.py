"""A Division's geometry serializes with its validity window and provenance.

A Division holds the boundary from one Census series. Its geometry carries
the series' as-of date as ``valid_from``, no ``valid_to`` while the boundary
is active, the boundary URL, the GEOID it was selected by, and the source
with its release. The two TIGER-backed fixtures are dumped through the
golden dumper and read back.
"""

from __future__ import annotations

import pytest
import yaml

from src.models.division import Division, sort_geometries
from tests.integration.golden.harness import (
    dump_golden_record,
    load_division_fixtures,
)

# (ocdid, identifier authority, identifier type, identifier value,
#  valid_from, source name, release, url host)
CASES = [
    (
        "ocd-division/country:us/state:ca/place:sausalito",
        ("census", "geoid", "0670364"),
        "2025-01-01T00:00:00Z",
        ("Census TIGER/Line", "2025"),
        "https://tigerweb.geo.census.gov/",
    ),
    (
        "ocd-division/country:us/state:ca/county:marin/cdp:marin_city",
        ("census", "geoid", "0645820"),
        "2025-01-01T00:00:00Z",
        ("Census TIGER/Line", "2025"),
        "https://tigerweb.geo.census.gov/",
    ),
    (
        "ocd-division/country:us/district:dc/anc:1a/council_district:1",
        ("dcgis", "anc_id", "1A"),
        "2023-01-01T00:00:00Z",
        ("DCGIS", "2023"),
        "https://maps2.dcgis.dc.gov/",
    ),
]


@pytest.mark.integration
@pytest.mark.golden
@pytest.mark.parametrize(
    ("ocdid", "identifier", "valid_from", "source", "url_host"),
    CASES,
    ids=[case[0].rsplit("/", 1)[-1] for case in CASES],
)
def test_geometry_serializes_with_validity_window_and_provenance(
    tmp_path, ocdid, identifier, valid_from, source, url_host
):
    division = next(d for d in load_division_fixtures() if d.ocdid == ocdid)
    assert sort_geometries(division.geometries) == division.geometries

    data = yaml.safe_load(dump_golden_record(division, tmp_path).read_text())

    assert len(data["geometries"]) == 1
    geometry = data["geometries"][0]
    assert geometry["valid_from"] == valid_from
    assert geometry["valid_to"] is None
    assert geometry["url"].startswith(url_host)
    assert f"%27{identifier[2]}%27" in geometry["url"]
    assert (geometry["source"]["source_name"], geometry["source"]["release"]) == source
    authority, id_type, value = identifier
    assert geometry["identifiers"] == [
        {
            "authority": authority,
            "id_type": id_type,
            "value": value,
            "source": geometry["source"],
        }
    ]

    # Reading the dump back reproduces the geometry, so nothing is lost on disk.
    assert Division(**data).geometries == division.geometries
