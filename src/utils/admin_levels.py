"""Administrative levels, and the output path each one maps to.

Levels follow the Google Civic Information API ``levels`` vocabulary so the
classification is portable rather than invented here. The members are ordered
by depth, with ``country`` at 1, so two levels can be compared directly.

US OCD ID segments map onto that vocabulary in ``US_SEGMENT_LEVELS``. Division
and Jurisdiction YAML is then filed by the deepest segment that names a
governmental unit. Segments that merely subdivide a unit (``council_district``,
``ward``, ``board_of_education``) do not shift the level, so a county's council
districts stay with the county and a city's stay with the city.

The filing directories are ``{area}/``, ``{area}/regional/`` and
``{area}/local/``. Counties file under ``regional/`` together with regional
authorities, which are often county-level or span several counties.

Every writer resolves its path through this module so that ancestor stub
generation and the generators cannot disagree about where an OCD ID lives — a
disagreement writes the same record to two paths.

Reference: https://developers.google.com/civic-information
"""

from __future__ import annotations

from enum import IntEnum
from pathlib import Path

__all__ = [
    "AdministrativeLevel",
    "US_SEGMENT_LEVELS",
    "UNIT_SEGMENTS",
    "classify_level",
    "governing_level",
    "resolve_area_root",
    "resolve_output_dir",
]

KINDS = ("divisions", "jurisdictions")


class AdministrativeLevel(IntEnum):
    """Google Civic Information API administrative levels, ordered by depth.

    ``SPECIAL`` is orthogonal to the hierarchy rather than below it; it sorts
    last so that depth comparisons over the ordinary levels stay meaningful.
    """

    INTERNATIONAL = 0
    COUNTRY = 1
    ADMINISTRATIVE_AREA_1 = 2
    REGIONAL = 3
    ADMINISTRATIVE_AREA_2 = 4
    LOCALITY = 5
    SUB_LOCALITY_1 = 6
    SUB_LOCALITY_2 = 7
    SPECIAL = 8

    @property
    def civic_name(self) -> str:
        """The token the Google Civic Information API uses for this level."""
        return _CIVIC_NAMES[self]


_CIVIC_NAMES: dict[AdministrativeLevel, str] = {
    AdministrativeLevel.INTERNATIONAL: "international",
    AdministrativeLevel.COUNTRY: "country",
    AdministrativeLevel.ADMINISTRATIVE_AREA_1: "administrativeArea1",
    AdministrativeLevel.REGIONAL: "regional",
    AdministrativeLevel.ADMINISTRATIVE_AREA_2: "administrativeArea2",
    AdministrativeLevel.LOCALITY: "locality",
    AdministrativeLevel.SUB_LOCALITY_1: "subLocality1",
    AdministrativeLevel.SUB_LOCALITY_2: "subLocality2",
    AdministrativeLevel.SPECIAL: "special",
}


# US OCD ID segment keys, mapped onto the Civic vocabulary.
US_SEGMENT_LEVELS: dict[str, AdministrativeLevel] = {
    "country": AdministrativeLevel.COUNTRY,
    # DC is a district and PR a territory, but both sit at the state level.
    "state": AdministrativeLevel.ADMINISTRATIVE_AREA_1,
    "district": AdministrativeLevel.ADMINISTRATIVE_AREA_1,
    "territory": AdministrativeLevel.ADMINISTRATIVE_AREA_1,
    "county": AdministrativeLevel.ADMINISTRATIVE_AREA_2,
    # A regional authority may be county-level or span several counties, so
    # it is a unit in its own right and files alongside counties.
    "regional": AdministrativeLevel.REGIONAL,
    "place": AdministrativeLevel.LOCALITY,
    "cdp": AdministrativeLevel.LOCALITY,
    "subdivision": AdministrativeLevel.LOCALITY,
    # DC has no place layer, so the ANC is its most local governing body and
    # carries a government of its own.
    "anc": AdministrativeLevel.LOCALITY,
    "ward": AdministrativeLevel.SUB_LOCALITY_1,
    "council_district": AdministrativeLevel.SUB_LOCALITY_1,
    "board_of_education": AdministrativeLevel.SPECIAL,
    "school_board_district": AdministrativeLevel.SPECIAL,
    "constable_district": AdministrativeLevel.SPECIAL,
    "special_district": AdministrativeLevel.SPECIAL,
    "special_purpose_district": AdministrativeLevel.SPECIAL,
}

# Levels that name a governmental unit, i.e. something that can carry its own
# government. A segment below one of these subdivides it without moving it.
_UNIT_LEVELS = frozenset(
    {
        AdministrativeLevel.COUNTRY,
        AdministrativeLevel.ADMINISTRATIVE_AREA_1,
        AdministrativeLevel.REGIONAL,
        AdministrativeLevel.ADMINISTRATIVE_AREA_2,
        AdministrativeLevel.LOCALITY,
    }
)

#: OCD ID segment keys that name a governmental unit rather than subdivide one.
UNIT_SEGMENTS = frozenset(
    key for key, level in US_SEGMENT_LEVELS.items() if level in _UNIT_LEVELS
)

# Directory each unit level is filed under, relative to the area directory.
#
# Counties and regional authorities share ``regional/``. Google separates
# them, but a regional authority is often county-level or spans several
# counties, and splitting the two would leave cross-county bodies without a
# home next to the counties they overlap.
_LEVEL_DIRS: dict[AdministrativeLevel, str | None] = {
    AdministrativeLevel.COUNTRY: None,
    AdministrativeLevel.ADMINISTRATIVE_AREA_1: None,
    AdministrativeLevel.REGIONAL: "regional",
    AdministrativeLevel.ADMINISTRATIVE_AREA_2: "regional",
    AdministrativeLevel.LOCALITY: "local",
}

# Segments naming the area directory: the state code, or the country code for
# a federal division.
_AREA_KEYS = ("state", "district", "territory")

_PREFIXES = ("ocd-division/", "ocd-jurisdiction/")


def _segments(ocdid: str) -> list[tuple[str, str]]:
    """The ID's ``key:value`` segments, with prefix and bare segments dropped.

    A Jurisdiction ID ends in an unkeyed classification (``/government``),
    which names no unit and is skipped.
    """
    body = ocdid
    for prefix in _PREFIXES:
        if body.startswith(prefix):
            body = body[len(prefix) :]
            break

    parsed: list[tuple[str, str]] = []
    for segment in body.split("/"):
        key, sep, value = segment.partition(":")
        if sep:
            parsed.append((key, value))
    return parsed


def classify_level(ocdid: str) -> AdministrativeLevel:
    """Return the administrative level of `ocdid`'s most specific segment."""
    level = AdministrativeLevel.COUNTRY
    for key, _value in _segments(ocdid):
        if key in US_SEGMENT_LEVELS:
            level = US_SEGMENT_LEVELS[key]
    return level


def governing_level(ocdid: str) -> AdministrativeLevel:
    """Return the level of the unit that governs `ocdid`.

    Subdivisions resolve to the unit they belong to, so a county council
    district governs at ``ADMINISTRATIVE_AREA_2`` and a city ward at
    ``LOCALITY``.
    """
    level = AdministrativeLevel.COUNTRY
    for key, _value in _segments(ocdid):
        candidate = US_SEGMENT_LEVELS.get(key)
        if candidate in _UNIT_LEVELS:
            level = candidate
    return level


def _area_code(ocdid: str) -> str:
    """The directory an OCD ID's area lives under: state code, else country."""
    segments = dict(_segments(ocdid))
    for key in _AREA_KEYS:
        if segments.get(key):
            return segments[key].lower()
    return (segments.get("country") or "").lower()


def resolve_area_root(ocdid: str, kind: str, root: Path | str = Path(".")) -> Path:
    """Return the whole area tree `ocdid` belongs to, beneath `root`.

    Reuse searches this tree rather than one level directory, so a record
    written by an earlier run is found wherever that run filed it.
    """
    if kind not in KINDS:
        raise ValueError(f"Unknown kind {kind!r}; expected one of {KINDS}")
    return Path(root) / kind / _area_code(ocdid)


def resolve_output_dir(ocdid: str, kind: str, root: Path | str = Path(".")) -> Path:
    """Return the directory `ocdid`'s YAML belongs in, beneath `root`.

    Args:
        ocdid: Division or Jurisdiction OCD ID.
        kind: Either ``"divisions"`` or ``"jurisdictions"``.
        root: Output root the tree is written under.
    """
    base = resolve_area_root(ocdid, kind, root)
    subdir = _LEVEL_DIRS[governing_level(ocdid)]
    return base / subdir if subdir else base
