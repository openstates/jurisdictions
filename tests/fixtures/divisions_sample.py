from datetime import datetime

from src.models.division import (
    Boundary,
    Division,
    DivisionMetadata,
    Geometry,
    GovernmentIdentifiers,
    Population,
)
from src.models.source import SourceObj

SEATTLE_DIVISION = Division(
    ocdid="ocd-division/country:us/state:wa/place:seattle/council_district:1",
    country="us",
    display_name="Seattle Council District 1",
    geometries=[],
    valid_thru=None,
    valid_asof=None,
    accurate_asof=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    last_updated=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    sourcing=[
        SourceObj(
            field=["geometries"],
            source_name="Census TIGER/Line",
            source_url={
                "url": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer"
            },
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["government_identifiers"],
            source_name="civicdata.tech",
            source_url={
                "url": "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/edit?usp=drive_web&ouid=105992325138979778362"
            },
            source_type="human_researched",
            source_description=None,
        ),
    ],
    government_identifiers=GovernmentIdentifiers(
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
    sourcing=[
        SourceObj(
            field=["geometries"],
            source_name="Census TIGER/Line",
            source_url={
                "url": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer"
            },
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["government_identifiers"],
            source_name="civicdata.tech",
            source_url={
                "url": "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/edit?usp=drive_web&ouid=105992325138979778362"
            },
            source_type="human_researched",
            source_description=None,
        ),
    ],
    government_identifiers=GovernmentIdentifiers(
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
    sourcing=[
        SourceObj(
            field=["geometries"],
            source_name="City of Austin ArcGIS Hub",
            source_url={
                "url": "https://services.arcgis.com/0L95CJ0VTaxqcmED/ArcGIS/rest/services/"
            },
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["government_identifiers"],
            source_name="civicdata.tech",
            source_url={
                "url": "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/edit?usp=drive_web&ouid=105992325138979778362"
            },
            source_type="human_researched",
            source_description=None,
        ),
    ],
    metadata=DivisionMetadata(),
    government_identifiers=GovernmentIdentifiers(
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
    sourcing=[
        SourceObj(
            field=["geometries"],
            source_name="DCGIS",
            source_url={
                "url": "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA"
            },
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["government_identifiers"],
            source_name="DCGIS",
            source_url={
                "url": "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Administrative_Other_Boundaries_WebMercator/MapServer/54"
            },
            source_type="human_researched",
            source_description=None,
        ),
    ],
    metadata=DivisionMetadata(
        source="DC Open Data ANC shapefile obtained via DCGIS. Not a Census designated area."
    ),
    government_identifiers=GovernmentIdentifiers(
        namelsad="ANC 1A",
        statefp="11",
        sldust=[],
        sldlst=[],
        countyfp=["001"],
        county_names=[],
        lsad="",
        geoid="11001",
    ),
    jurisdiction_id="ocd-jurisdiction/country:us/district:dc/anc:1a/government",
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
    sourcing=[
        SourceObj(
            field=["geometries"],
            source_name="Census TIGER/Line",
            source_url={
                "url": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer"
            },
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["government_identifiers"],
            source_name="civicdata.tech",
            source_url={
                "url": "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/edit?usp=drive_web&ouid=105992325138979778362"
            },
            source_type="human_researched",
            source_description=None,
        ),
    ],
    government_identifiers=GovernmentIdentifiers(
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
        SourceObj(
            field=["geometries"],
            source_name="Census TIGER/Line",
            source_url={
                "url": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer"
            },
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["government_identifiers"],
            source_name="civicdata.tech",
            source_url={
                "url": "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/edit?usp=drive_web&ouid=105992325138979778362"
            },
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["metadata", "metadata.population"],
            source_name="Census 2020 Decceennial Census",
            source_url={
                "url": "https://data.census.gov/profile/Marin_City_CDP,_California?g=160XX00US0645820"
            },
            source_type="human_researched",
            source_description=None,
        ),
    ],
    metadata=DivisionMetadata(population=Population(population=2993)),
    government_identifiers=GovernmentIdentifiers(
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
