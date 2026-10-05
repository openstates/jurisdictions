"""Tests for administrative level classification and output-path resolution."""

from pathlib import Path

import pytest

from src.utils.admin_levels import (
    AdministrativeLevel,
    classify_level,
    governing_level,
    resolve_output_dir,
)


# --- The level vocabulary ---


def test_levels_follow_the_civic_api_vocabulary():
    """The members and their tokens come from the Google Civic API."""
    assert [level.civic_name for level in AdministrativeLevel] == [
        "international",
        "country",
        "administrativeArea1",
        "regional",
        "administrativeArea2",
        "locality",
        "subLocality1",
        "subLocality2",
        "special",
    ]


def test_levels_are_ordered_by_depth():
    """Country is level 1, state 2, and deeper levels compare as greater."""
    assert AdministrativeLevel.COUNTRY == 1
    assert AdministrativeLevel.ADMINISTRATIVE_AREA_1 == 2
    assert (
        AdministrativeLevel.COUNTRY
        < AdministrativeLevel.ADMINISTRATIVE_AREA_1
        < AdministrativeLevel.ADMINISTRATIVE_AREA_2
        < AdministrativeLevel.LOCALITY
        < AdministrativeLevel.SUB_LOCALITY_1
    )


# --- Classification of the most specific segment ---


@pytest.mark.parametrize(
    ("ocdid", "expected"),
    [
        ("ocd-division/country:us", AdministrativeLevel.COUNTRY),
        ("ocd-division/country:us/state:wa", AdministrativeLevel.ADMINISTRATIVE_AREA_1),
        (
            "ocd-division/country:us/district:dc",
            AdministrativeLevel.ADMINISTRATIVE_AREA_1,
        ),
        (
            "ocd-division/country:us/territory:pr",
            AdministrativeLevel.ADMINISTRATIVE_AREA_1,
        ),
        (
            "ocd-division/country:us/state:tx/county:harris",
            AdministrativeLevel.ADMINISTRATIVE_AREA_2,
        ),
        (
            "ocd-division/country:us/state:tx/place:austin",
            AdministrativeLevel.LOCALITY,
        ),
        (
            "ocd-division/country:us/state:tx/place:austin/council_district:8",
            AdministrativeLevel.SUB_LOCALITY_1,
        ),
        (
            "ocd-division/country:us/state:oh/place:cincinnati/ward:4",
            AdministrativeLevel.SUB_LOCALITY_1,
        ),
        (
            "ocd-division/country:us/state:oh/board_of_education:1",
            AdministrativeLevel.SPECIAL,
        ),
    ],
)
def test_classify_level(ocdid, expected):
    assert classify_level(ocdid) == expected


# --- The governing unit a division is filed under ---


@pytest.mark.parametrize(
    ("ocdid", "expected"),
    [
        # A bare unit governs at its own level.
        ("ocd-division/country:us", AdministrativeLevel.COUNTRY),
        ("ocd-division/country:us/state:wa", AdministrativeLevel.ADMINISTRATIVE_AREA_1),
        (
            "ocd-division/country:us/state:tx/county:harris",
            AdministrativeLevel.ADMINISTRATIVE_AREA_2,
        ),
        ("ocd-division/country:us/state:tx/place:austin", AdministrativeLevel.LOCALITY),
        # A subdivision resolves to the unit that governs it.
        (
            "ocd-division/country:us/state:tx/county:harris/council_district:3",
            AdministrativeLevel.ADMINISTRATIVE_AREA_2,
        ),
        (
            "ocd-division/country:us/state:tx/county:harris/constable_district:1",
            AdministrativeLevel.ADMINISTRATIVE_AREA_2,
        ),
        (
            "ocd-division/country:us/state:oh/board_of_education:1",
            AdministrativeLevel.ADMINISTRATIVE_AREA_1,
        ),
        (
            "ocd-division/country:us/state:tx/place:austin/council_district:8",
            AdministrativeLevel.LOCALITY,
        ),
        (
            "ocd-division/country:us/state:wa/place:seattle/school_board_district:1",
            AdministrativeLevel.LOCALITY,
        ),
        # DC has no place layer, so the ANC is the governing unit.
        ("ocd-division/country:us/district:dc/anc:1a", AdministrativeLevel.LOCALITY),
        (
            "ocd-division/country:us/district:dc/anc:1a/council_district:1",
            AdministrativeLevel.LOCALITY,
        ),
        # A CDP is place-like, so it pulls the level back down from the county.
        (
            "ocd-division/country:us/state:tx/county:harris/cdp:bunker_hill",
            AdministrativeLevel.LOCALITY,
        ),
        (
            "ocd-division/country:us/state:tx/county:harris/cdp:bunker_hill"
            "/special_district:utility",
            AdministrativeLevel.LOCALITY,
        ),
    ],
)
def test_governing_level(ocdid, expected):
    assert governing_level(ocdid) == expected


def test_jurisdiction_ids_ignore_the_classification_segment():
    """A Jurisdiction ID ends in an unkeyed classification, not a unit."""
    assert (
        governing_level("ocd-jurisdiction/country:us/state:wa/place:seattle/government")
        == AdministrativeLevel.LOCALITY
    )
    assert (
        governing_level("ocd-jurisdiction/country:us/state:tx/county:harris/government")
        == AdministrativeLevel.ADMINISTRATIVE_AREA_2
    )
    assert (
        governing_level("ocd-jurisdiction/country:us/state:wa/government")
        == AdministrativeLevel.ADMINISTRATIVE_AREA_1
    )


# --- Directory resolution ---


@pytest.mark.parametrize(
    ("ocdid", "kind", "expected"),
    [
        ("ocd-division/country:us", "divisions", "divisions/us"),
        ("ocd-division/country:us/state:wa", "divisions", "divisions/wa"),
        ("ocd-division/country:us/district:dc", "divisions", "divisions/dc"),
        (
            "ocd-division/country:us/state:oh/board_of_education:1",
            "divisions",
            "divisions/oh",
        ),
        (
            "ocd-division/country:us/state:tx/county:harris",
            "divisions",
            "divisions/tx/county",
        ),
        (
            "ocd-division/country:us/state:tx/county:harris/council_district:3",
            "divisions",
            "divisions/tx/county",
        ),
        (
            "ocd-division/country:us/state:tx/place:austin",
            "divisions",
            "divisions/tx/local",
        ),
        (
            "ocd-division/country:us/state:tx/place:austin/council_district:8",
            "divisions",
            "divisions/tx/local",
        ),
        (
            "ocd-division/country:us/district:dc/anc:1a/council_district:1",
            "divisions",
            "divisions/dc/local",
        ),
        (
            "ocd-jurisdiction/country:us/state:wa/place:seattle/government",
            "jurisdictions",
            "jurisdictions/wa/local",
        ),
        (
            "ocd-jurisdiction/country:us/state:tx/county:harris/government",
            "jurisdictions",
            "jurisdictions/tx/county",
        ),
        (
            "ocd-jurisdiction/country:us/state:wa/government",
            "jurisdictions",
            "jurisdictions/wa",
        ),
        ("ocd-jurisdiction/country:us/government", "jurisdictions", "jurisdictions/us"),
    ],
)
def test_resolve_output_dir(ocdid, kind, expected):
    assert resolve_output_dir(ocdid, kind) == Path(expected)


def test_resolve_output_dir_is_relative_to_the_given_root():
    """Callers write under a configured root, not the process CWD."""
    assert resolve_output_dir(
        "ocd-division/country:us/state:wa/place:seattle",
        "divisions",
        root=Path("/tmp/out"),
    ) == Path("/tmp/out/divisions/wa/local")


def test_a_division_and_its_jurisdiction_resolve_to_matching_trees():
    """The two writers must not disagree, or one record lands in two paths."""
    division = "ocd-division/country:us/state:tx/county:harris/council_district:3"
    jurisdiction = "ocd-jurisdiction/country:us/state:tx/county:harris/government"

    assert resolve_output_dir(division, "divisions") == Path("divisions/tx/county")
    assert resolve_output_dir(jurisdiction, "jurisdictions") == Path(
        "jurisdictions/tx/county"
    )


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError, match="kind"):
        resolve_output_dir("ocd-division/country:us/state:wa", "organizations")
