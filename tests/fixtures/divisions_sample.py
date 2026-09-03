from datetime import datetime

from src.models.division import (
    Boundary,
    Division,
    DivisionMetadata,
    Geometry,
    Identifier,
    Population,
)
from src.models.source import SourceObj


def _census_ids(
    source: SourceObj,
    *,
    namelsad: str = "",
    statefp: str = "",
    lsad: str = "",
    geoid: str = "",
    placefp: str = "",
    cousubfp: str = "",
    sldust: list[str] | None = None,
    sldlst: list[str] | None = None,
    countyfp: list[str] | None = None,
    county_names: list[str] | None = None,
) -> list[Identifier]:
    identifiers: list[Identifier] = []

    def _add(id_type: str, value: str) -> None:
        if value:
            identifiers.append(
                Identifier(
                    authority="census", id_type=id_type, value=value, source=source
                )
            )

    _add("namelsad", namelsad)
    _add("statefp", statefp)
    _add("lsad", lsad)
    _add("geoid", geoid)
    _add("placefp", placefp)
    _add("cousubfp", cousubfp)
    for value in sldust or []:
        _add("sldust", value)
    for value in sldlst or []:
        _add("sldlst", value)
    for value in countyfp or []:
        _add("countyfp", value)
    for value in county_names or []:
        _add("county_names", value)
    return identifiers


_CIVICDATA_GI_SOURCE = SourceObj(
    field=["government_identifiers"],
    source_name="civicdata.tech",
    source_url={
        "url": "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/edit?usp=drive_web&ouid=105992325138979778362"
    },
    source_type="human_researched",
    source_description=None,
)

_TIGER_GEOMETRY_SOURCE = SourceObj(
    field=["geometries"],
    source_name="Census TIGER/Line",
    source_url={
        "url": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer"
    },
    source_type="human_researched",
    source_description=None,
)


SEATTLE_DIVISION = Division(
    ocdid="ocd-division/country:us/state:wa/place:seattle/council_district:1",
    country="us",
    display_name="Seattle Council District 1",
    geometries=[],
    valid_thru=None,
    valid_asof=None,
    accurate_asof=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    last_updated=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    sourcing=[_TIGER_GEOMETRY_SOURCE, _CIVICDATA_GI_SOURCE],
    government_identifiers=_census_ids(
        _CIVICDATA_GI_SOURCE,
        namelsad="Seattle city",
        statefp="53",
        sldust=["032", "034", "036", "037", "043", "046"],
        sldlst=["032", "034", "036", "037", "043", "046"],
        countyfp=["033"],
        county_names=["King"],
        lsad="25",
        geoid="5363000",
    ),
    jurisdiction_id="ocd-jurisdiction/country:us/state:wa/place:seattle/government",
)

TACOMA_DIVISION = Division(
    ocdid="ocd-division/country:us/state:wa/place:tacoma",
    country="us",
    display_name="Tacoma",
    geometries=[],
    also_known_as=[],
    valid_thru=None,
    valid_asof=None,
    accurate_asof=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    last_updated=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    sourcing=[_TIGER_GEOMETRY_SOURCE, _CIVICDATA_GI_SOURCE],
    government_identifiers=_census_ids(
        _CIVICDATA_GI_SOURCE,
        namelsad="Tacoma city",
        statefp="53",
        sldust=["027", "028", "029"],
        sldlst=["027", "028", "029"],
        countyfp=["053"],
        county_names=["Pierce"],
        lsad="25",
        geoid="5370000",
    ),
    jurisdiction_id="ocd-jurisdiction/country:us/state:wa/place:tacoma/government",
)

_AUSTIN_GEOMETRY_SOURCE = SourceObj(
    field=["geometries"],
    source_name="City of Austin ArcGIS Hub",
    source_url={
        "url": "https://services.arcgis.com/0L95CJ0VTaxqcmED/ArcGIS/rest/services/"
    },
    source_type="human_researched",
    source_description=None,
)

AUSTIN_DIVISION = Division(
    ocdid="ocd-division/country:us/state:tx/place:austin/council_district:8",
    country="us",
    display_name="Austin Council District 8",
    geometries=[],
    also_known_as=[],
    valid_thru=None,
    valid_asof=None,
    accurate_asof=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    last_updated=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    sourcing=[_AUSTIN_GEOMETRY_SOURCE, _CIVICDATA_GI_SOURCE],
    metadata=DivisionMetadata(),
    government_identifiers=_census_ids(
        _CIVICDATA_GI_SOURCE,
        namelsad="Austin city: council district 8",
        statefp="48",
        sldust=["25"],
        sldlst=["047", "048"],
        countyfp=["209", "453", "491"],
        county_names=["Hays", "Travis", "Williamson"],
        lsad="22",
        geoid="4845390165",
    ),
    jurisdiction_id="ocd-jurisdiction/country:us/state:tx/place:austin/government",
)

_ANC_GEOMETRY_SOURCE = SourceObj(
    field=["geometries"],
    source_name="DCGIS",
    source_url={"url": "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA"},
    source_type="human_researched",
    source_description=None,
)

_ANC_GI_SOURCE = SourceObj(
    field=["government_identifiers"],
    source_name="DCGIS",
    source_url={
        "url": "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Administrative_Other_Boundaries_WebMercator/MapServer/54"
    },
    source_type="human_researched",
    source_description=None,
)

ANC_1A_DIVISION = Division(
    ocdid="ocd-division/country:us/district:dc/anc:1a/council_district:1",
    country="us",
    display_name="ANC 1A District 1",
    geometries=[
        Geometry(
            start=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
            end=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
            boundary=Boundary(),
            children=[],
            arcGIS_address="https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Administrative_Other_Boundaries_WebMercator/MapServer/54/query?where=ANC_ID=%271A%27&outFields=*&f=geojson",
        )
    ],
    also_known_as=[],
    valid_thru=None,
    valid_asof=datetime.fromisoformat("2023-01-01T00:00:00+00:00"),
    accurate_asof=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    last_updated=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    sourcing=[_ANC_GEOMETRY_SOURCE, _ANC_GI_SOURCE],
    metadata=DivisionMetadata(
        source="DC Open Data ANC shapefile obtained via DCGIS. Not a Census designated area."
    ),
    government_identifiers=[
        Identifier(
            authority="census",
            id_type="namelsad",
            value="ANC 1A",
            source=_ANC_GI_SOURCE,
        ),
        Identifier(
            authority="census",
            id_type="statefp",
            value="11",
            source=_ANC_GI_SOURCE,
        ),
        Identifier(
            authority="census",
            id_type="countyfp",
            value="001",
            source=_ANC_GI_SOURCE,
        ),
        Identifier(
            authority="census",
            id_type="geoid",
            value="11001",
            source=_ANC_GI_SOURCE,
        ),
    ],
    jurisdiction_id="ocd-jurisdiction/country:us/district:dc/anc:1a/government",
)

_SAUSALITO_GEOMETRY_SOURCE = SourceObj(
    field=["geometries"],
    source_name="Census TIGER/Line",
    source_url={
        "url": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer"
    },
    source_type="human_researched",
    source_description=None,
)

SAUSALITO_DIVISION = Division(
    ocdid="ocd-division/country:us/state:ca/place:sausalito",
    country="us",
    display_name="Sausalito",
    geometries=[
        Geometry(
            start=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
            end=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
            boundary=Boundary(),
            children=[],
            arcGIS_address="https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/4/query?where=GEOID%3D'0670364'&outFields=*&outSR=4326&f=geojson",
        )
    ],
    also_known_as=[],
    valid_thru=None,
    valid_asof=None,
    accurate_asof=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    last_updated=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    sourcing=[_SAUSALITO_GEOMETRY_SOURCE, _CIVICDATA_GI_SOURCE],
    government_identifiers=_census_ids(
        _CIVICDATA_GI_SOURCE,
        namelsad="Sausalito city",
        statefp="06",
        sldust=["002"],
        sldlst=["012"],
        countyfp=["041"],
        county_names=["Marin"],
        lsad="25",
        geoid="0670364",
    ),
    jurisdiction_id="ocd-jurisdiction/country:us/state:ca/place:sausalito/government",
)

_MARIN_CITY_POPULATION_SOURCE = SourceObj(
    field=["metadata", "metadata.population"],
    source_name="Census 2020 Decceennial Census",
    source_url={
        "url": "https://data.census.gov/profile/Marin_City_CDP,_California?g=160XX00US0645820"
    },
    source_type="human_researched",
    source_description=None,
)

MARIN_CITY_DIVISION = Division(
    ocdid="ocd-division/country:us/state:ca/county:marin/cdp:marin_city",
    country="us",
    display_name="Marin City",
    geometries=[
        Geometry(
            start=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
            end=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
            boundary=Boundary(),
            children=[],
            arcGIS_address="https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/5/query?where=GEOID%3D'0645820'&outFields=*&outSR=4326&f=geojson",
        )
    ],
    also_known_as=["Marin City Census Designated Place"],
    valid_thru=None,
    valid_asof=None,
    accurate_asof=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    last_updated=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    sourcing=[
        _SAUSALITO_GEOMETRY_SOURCE,
        _CIVICDATA_GI_SOURCE,
        _MARIN_CITY_POPULATION_SOURCE,
    ],
    metadata=DivisionMetadata(population=Population(population=2993)),
    government_identifiers=_census_ids(
        _CIVICDATA_GI_SOURCE,
        namelsad="Marin City CDP",
        statefp="06",
        placefp="46420",
        sldust=["002"],
        sldlst=["012"],
        countyfp=["041"],
        county_names=["Marin"],
        lsad="57",
        geoid="0645820",
    ),
    jurisdiction_id="ocd-jurisdiction/country:us/state:ca/county:marin/cdp:marin_city/special_district:marin_city_community_services_district/governing_board",
)

div_list = [
    SEATTLE_DIVISION,
    TACOMA_DIVISION,
    AUSTIN_DIVISION,
    ANC_1A_DIVISION,
    SAUSALITO_DIVISION,
    MARIN_CITY_DIVISION,
]

if __name__ == "__main__":
    from pathlib import Path

    for div in div_list:
        div.dump_division(base_dir=Path("tests/sample_output/divisions"))
