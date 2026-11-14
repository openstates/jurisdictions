"""Administrative level definitions.

Levels follow the Google Civic Information API ``levels`` vocabulary so the
classification is portable rather than invented here. The members are ordered
by depth, with ``country`` at 1, so two levels can be compared directly.

US OCD ID segment keys map onto that vocabulary in ``US_SEGMENT_LEVELS``.

Reference: https://developers.google.com/civic-information
"""

from enum import Enum, IntEnum
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer


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
    def definition(self) -> "AdministrativeLevelDefinition":
        return ADMINISTRATIVE_LEVELS[self]

    @property
    def civic_name(self) -> str:
        """The token the Google Civic Information API uses for this level."""
        return self.definition.civic_name

    @property
    def is_governing_unit(self) -> bool:
        return self.definition.is_governing_unit

    @classmethod
    def from_civic_name(cls, civic_name: str) -> "AdministrativeLevel":
        for level, definition in ADMINISTRATIVE_LEVELS.items():
            if definition.civic_name == civic_name:
                return level
        raise ValueError(f"Unknown administrative level {civic_name!r}")


class AdministrativeLevelDefinition(BaseModel):
    """The attributes of one administrative level."""

    model_config = ConfigDict(frozen=True)

    level: AdministrativeLevel = Field(description="The level being defined.")
    civic_name: str = Field(
        description="Google Civic Information API token, e.g. 'administrativeArea1'."
    )
    is_governing_unit: bool = Field(
        description=(
            "True when a division at this level can carry its own government. "
            "A segment below a governing unit subdivides it without moving it."
        )
    )


ADMINISTRATIVE_LEVELS: dict[AdministrativeLevel, AdministrativeLevelDefinition] = {
    definition.level: definition
    for definition in (
        AdministrativeLevelDefinition(
            level=AdministrativeLevel.INTERNATIONAL,
            civic_name="international",
            is_governing_unit=False,
        ),
        AdministrativeLevelDefinition(
            level=AdministrativeLevel.COUNTRY,
            civic_name="country",
            is_governing_unit=True,
        ),
        AdministrativeLevelDefinition(
            level=AdministrativeLevel.ADMINISTRATIVE_AREA_1,
            civic_name="administrativeArea1",
            is_governing_unit=True,
        ),
        AdministrativeLevelDefinition(
            level=AdministrativeLevel.REGIONAL,
            civic_name="regional",
            is_governing_unit=True,
        ),
        AdministrativeLevelDefinition(
            level=AdministrativeLevel.ADMINISTRATIVE_AREA_2,
            civic_name="administrativeArea2",
            is_governing_unit=True,
        ),
        AdministrativeLevelDefinition(
            level=AdministrativeLevel.LOCALITY,
            civic_name="locality",
            is_governing_unit=True,
        ),
        AdministrativeLevelDefinition(
            level=AdministrativeLevel.SUB_LOCALITY_1,
            civic_name="subLocality1",
            is_governing_unit=False,
        ),
        AdministrativeLevelDefinition(
            level=AdministrativeLevel.SUB_LOCALITY_2,
            civic_name="subLocality2",
            is_governing_unit=False,
        ),
        AdministrativeLevelDefinition(
            level=AdministrativeLevel.SPECIAL,
            civic_name="special",
            is_governing_unit=False,
        ),
    )
}


def _level_from_civic_name(value: Any) -> Any:
    if isinstance(value, str):
        return AdministrativeLevel.from_civic_name(value)
    return value


#: Field type for an AdministrativeLevel stored in YAML: written as its Civic
#: name (e.g. ``locality``) and read back from it.
AdministrativeLevelName = Annotated[
    AdministrativeLevel,
    BeforeValidator(_level_from_civic_name),
    PlainSerializer(lambda level: level.civic_name, return_type=str),
]


class DivisionClassificationEnum(str, Enum):
    """OCD Division segment types: the ``<type>`` in a ``<type>:<id>`` segment.

    Covers every leaf type in the national OCD master file
    (``ocd-division-ids/identifiers/country-us.csv``), plus types used by
    per-state local-government files and this project (``cdp``,
    ``subdivision``, ``regional``, ``special_district``,
    ``special_purpose_district``).
    """

    # Country and state equivalents
    COUNTRY = "country"
    STATE = "state"
    DISTRICT = "district"
    TERRITORY = "territory"
    # County equivalents
    COUNTY = "county"
    PARISH = "parish"
    BOROUGH = "borough"
    CENSUS_AREA = "census_area"
    MUNICIPIO = "municipio"
    REGIONAL = "regional"
    # Local governments
    PLACE = "place"
    CDP = "cdp"
    SUBDIVISION = "subdivision"
    MUNICIPALITY = "municipality"
    ANC = "anc"
    # Subdivisions of a local government
    WARD = "ward"
    COUNCIL_DISTRICT = "council_district"
    COMMISSIONER_DISTRICT = "commissioner_district"
    EXECUTIVE_DISTRICT = "executive_district"
    PRECINCT = "precinct"
    # Legislative districts
    CD = "cd"
    SLDU = "sldu"
    SLDL = "sldl"
    # Courts
    SUPREME_COURT = "supreme_court"
    COURT_OF_APPEALS = "court_of_appeals"
    SUPERIOR_COURT = "superior_court"
    CIRCUIT_COURT = "circuit_court"
    DISTRICT_COURT = "district_court"
    CHANCERY_COURT = "chancery_court"
    # Schools
    SCHOOL_DISTRICT = "school_district"
    SCHOOL_BOARD_DISTRICT = "school_board_district"
    BOARD_OF_EDUCATION = "board_of_education"
    BOARD_OF_REGENTS = "board_of_regents"
    # Boards, commissions and special districts
    BOARD_OF_ELECTIONS = "board_of_elections"
    BOARD_OF_EQUALIZATION = "board_of_equalization"
    GOVERNORS_COUNCIL = "governors_council"
    PUBLIC_SERVICE_COMMISSION = "public_service_commission"
    CONSTABLE_DISTRICT = "constable_district"
    HEALTH_CARE = "health_care"
    LA_METRO_SECTOR = "la_metro_sector"
    PARK_DISTRICT = "park_district"
    REGION = "region"
    SANITATION = "sanitation"
    SEWER = "sewer"
    TRANSIT = "transit"
    WATER = "water"
    SPECIAL_DISTRICT = "special_district"
    SPECIAL_PURPOSE_DISTRICT = "special_purpose_district"


_T = DivisionClassificationEnum
_L = AdministrativeLevel

# US OCD ID segment types, mapped onto the Civic vocabulary. Electoral,
# judicial, school and special-purpose districts are SPECIAL: they overlay the
# hierarchy rather than sit in it.
US_SEGMENT_LEVELS: dict[DivisionClassificationEnum, AdministrativeLevel] = {
    _T.COUNTRY: _L.COUNTRY,
    # DC is a district and PR a territory, but both sit at the state level.
    # ``district`` is state level only directly under a country; see
    # US_SEGMENT_PARENT_LEVELS.
    _T.STATE: _L.ADMINISTRATIVE_AREA_1,
    _T.TERRITORY: _L.ADMINISTRATIVE_AREA_1,
    _T.DISTRICT: _L.SPECIAL,
    _T.COUNTY: _L.ADMINISTRATIVE_AREA_2,
    _T.PARISH: _L.ADMINISTRATIVE_AREA_2,
    _T.BOROUGH: _L.ADMINISTRATIVE_AREA_2,
    _T.CENSUS_AREA: _L.ADMINISTRATIVE_AREA_2,
    _T.MUNICIPIO: _L.ADMINISTRATIVE_AREA_2,
    # A regional authority may be county-level or span several counties, so
    # it is a unit in its own right and files alongside counties.
    _T.REGIONAL: _L.REGIONAL,
    _T.PLACE: _L.LOCALITY,
    _T.CDP: _L.LOCALITY,
    _T.SUBDIVISION: _L.LOCALITY,
    _T.MUNICIPALITY: _L.LOCALITY,
    # DC has no place layer, so the ANC is its most local governing body and
    # carries a government of its own.
    _T.ANC: _L.LOCALITY,
    _T.WARD: _L.SUB_LOCALITY_1,
    _T.COUNCIL_DISTRICT: _L.SUB_LOCALITY_1,
    _T.COMMISSIONER_DISTRICT: _L.SUB_LOCALITY_1,
    _T.EXECUTIVE_DISTRICT: _L.SUB_LOCALITY_1,
    _T.PRECINCT: _L.SUB_LOCALITY_2,
    _T.CD: _L.SPECIAL,
    _T.SLDU: _L.SPECIAL,
    _T.SLDL: _L.SPECIAL,
    _T.SUPREME_COURT: _L.SPECIAL,
    _T.COURT_OF_APPEALS: _L.SPECIAL,
    _T.SUPERIOR_COURT: _L.SPECIAL,
    _T.CIRCUIT_COURT: _L.SPECIAL,
    _T.DISTRICT_COURT: _L.SPECIAL,
    _T.CHANCERY_COURT: _L.SPECIAL,
    _T.SCHOOL_DISTRICT: _L.SPECIAL,
    _T.SCHOOL_BOARD_DISTRICT: _L.SPECIAL,
    _T.BOARD_OF_EDUCATION: _L.SPECIAL,
    _T.BOARD_OF_REGENTS: _L.SPECIAL,
    _T.BOARD_OF_ELECTIONS: _L.SPECIAL,
    _T.BOARD_OF_EQUALIZATION: _L.SPECIAL,
    _T.GOVERNORS_COUNCIL: _L.SPECIAL,
    _T.PUBLIC_SERVICE_COMMISSION: _L.SPECIAL,
    _T.CONSTABLE_DISTRICT: _L.SPECIAL,
    _T.HEALTH_CARE: _L.SPECIAL,
    _T.LA_METRO_SECTOR: _L.SPECIAL,
    _T.PARK_DISTRICT: _L.SPECIAL,
    _T.REGION: _L.SPECIAL,
    _T.SANITATION: _L.SPECIAL,
    _T.SEWER: _L.SPECIAL,
    _T.TRANSIT: _L.SPECIAL,
    _T.WATER: _L.SPECIAL,
    _T.SPECIAL_DISTRICT: _L.SPECIAL,
    _T.SPECIAL_PURPOSE_DISTRICT: _L.SPECIAL,
}

# Levels that depend on the parent segment, keyed by (parent type, type).
US_SEGMENT_PARENT_LEVELS: dict[tuple[str, str], AdministrativeLevel] = {
    # ``country:us/district:dc`` is DC; a ``district`` under a transit
    # authority or court of appeals is not.
    (_T.COUNTRY, _T.DISTRICT): _L.ADMINISTRATIVE_AREA_1,
}


#: Segment types that subdivide a government for representation and carry no
#: government of their own: wards, council and commissioner districts,
#: precincts, and legislative districts. Their governing body is the
#: government of the division they subdivide, and they are what a Post's
#: ``division_id`` points to.
REPRESENTATION_SUBDIVISIONS: frozenset[DivisionClassificationEnum] = frozenset(
    {
        _T.WARD,
        _T.COUNCIL_DISTRICT,
        _T.COMMISSIONER_DISTRICT,
        _T.EXECUTIVE_DISTRICT,
        _T.PRECINCT,
        _T.CONSTABLE_DISTRICT,
        _T.SCHOOL_BOARD_DISTRICT,
        _T.BOARD_OF_EDUCATION,
        _T.LA_METRO_SECTOR,
        _T.CD,
        _T.SLDU,
        _T.SLDL,
    }
)


#: OCD ID segment types that can name a governmental unit rather than
#: subdivide one.
UNIT_SEGMENTS: frozenset[str] = frozenset(
    {key.value for key, level in US_SEGMENT_LEVELS.items() if level.is_governing_unit}
    | {
        segment
        for (_parent, segment), level in US_SEGMENT_PARENT_LEVELS.items()
        if level.is_governing_unit
    }
)
