from datetime import datetime

from src.models.jurisdiction import (
    Jurisdiction,
    JurisdictionMetadata,
    TermDetail,
    URLObject,
)
from src.models.source import SourceObj


SEATTLE_JURISDICTION = Jurisdiction(
    ocdid="ocd-jurisdiction/country:us/state:wa/place:seattle/government",
    name="Seattle City Government",
    url="https://www.seattle.gov/",
    classification="government",
    legislative_sessions={},
    feature_flags=[],
    term=TermDetail(
        duration=4,
        term_description=(
            "Seattle City Council consists of nine councilmembers serving four-year terms. "
            "Seven members are elected by district and two members are elected at-large, "
            "per the Seattle City Charter."
        ),
        number_of_positions=9,
        term_limits=None,
        source_url="https://www.seattle.gov/cityclerk/agendas-and-legislative-resources/terms-of-office-for-elected-officials",
        last_known_term_end_date=None,
    ),
    accurate_asof=datetime.fromisoformat("2026-03-07T00:00:00+00:00"),
    last_updated=datetime.fromisoformat("2026-03-07T00:00:00+00:00"),
    sourcing=[
        SourceObj(
            field=["url"],
            source_name="Seattle Official Site",
            source_url={"url": "https://www.seattle.gov/"},
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["term"],
            source_name="Seattle City Clerk",
            source_url={
                "url": "https://www.seattle.gov/cityclerk/agendas-and-legislative-resources/terms-of-office-for-elected-officials"
            },
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["metadata", "metadata.urls"],
            source_name="Seattle Council",
            source_url={"url": "https://www.seattle.gov/council"},
            source_type="human_researched",
            source_description=None,
        ),
    ],
    metadata=JurisdictionMetadata(
        urls=[
            URLObject(
                url_type="people",
                url="https://www.seattle.gov/council/meet-the-council",
            ),
            URLObject(
                url_type="meetings",
                url="https://www.seattle.gov/cityclerk/agendas-and-legislative-resources/city-council-agendas",
            ),
        ]
    ),
)

TACOMA_JURISDICTION = Jurisdiction(
    ocdid="ocd-jurisdiction/country:us/state:wa/place:tacoma/government",
    name="Tacoma City Government",
    url="https://tacoma.gov/",
    classification="government",
    legislative_sessions={},
    feature_flags=[],
    term=TermDetail(
        duration=4,
        term_description=(
            "The City Council consists of the Mayor and eight Council Members elected to "
            "four-year terms. Five positions are elected from council districts and three "
            "positions are elected at large."
        ),
        number_of_positions=9,
        term_limits=None,
        source_url="https://cms.tacoma.gov/cityclerk/Files/Documents/CityCharter.pdf",
        last_known_term_end_date=None,
    ),
    accurate_asof=datetime.fromisoformat("2026-03-07T00:00:00+00:00"),
    last_updated=datetime.fromisoformat("2026-03-07T00:00:00+00:00"),
    sourcing=[
        SourceObj(
            field=["url"],
            source_name="Tacoma Official Site",
            source_url={"url": "https://tacoma.gov/"},
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["term"],
            source_name="Tacoma City Charter",
            source_url={
                "url": "https://cms.tacoma.gov/cityclerk/Files/Documents/CityCharter.pdf"
            },
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["term", "term.number_of_positions"],
            source_name="Tacoma Council",
            source_url={
                "url": "https://tacoma.gov/government/departments/city-council/"
            },
            source_type="human_researched",
            source_description=None,
        ),
    ],
    metadata=JurisdictionMetadata(
        urls=[
            URLObject(
                url_type="people",
                url="https://tacoma.gov/government/departments/city-council/",
            ),
            URLObject(
                url_type="meetings",
                url="https://cityoftacoma.legistar.com/Calendar.aspx",
            ),
        ]
    ),
)

AUSTIN_JURISDICTION = Jurisdiction(
    ocdid="ocd-jurisdiction/country:us/state:tx/place:austin/government",
    name="City of Austin",
    url="https://www.austintexas.gov",
    classification="government",
    legislative_sessions={},
    feature_flags=[],
    term=TermDetail(
        duration=4,
        term_description=(
            "The regular term of the mayor and council members is four years. Council "
            "terms shall be staggered so that a general election is held every two years, "
            "and half, or as near to half as is practical, of the council is elected at "
            'each election. The term "council member(s)" includes the mayor unless '
            "otherwise provided."
        ),
        number_of_positions=11,
        term_limits="2 consecutive terms",
        source_url="https://library.municode.com/tx/austin/codes/code_of_ordinances?nodeId=CH_ARTIIIEL_S2ELDACOTEELMARFEL",
        last_known_term_end_date=None,
    ),
    accurate_asof=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    last_updated=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    sourcing=[
        SourceObj(
            field=["url"],
            source_name="City of Austin ArcGIS Hub",
            source_url={
                "url": "https://services.arcgis.com/0L95CJ0VTaxqcmED/ArcGIS/rest/services/"
            },
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["term", "term.term_description"],
            source_name="Austin Code of Ordinances",
            source_url={
                "url": "https://library.municode.com/tx/austin/codes/code_of_ordinances?nodeId=CH_ARTIIIEL_S2ELDACOTEELMARFEL"
            },
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["term", "term.term_limits"],
            source_name="Austin Code of Ordinances",
            source_url={
                "url": "https://library.municode.com/tx/austin/codes/code_of_ordinances?nodeId=CH_ARTIITHCO_S5TELI"
            },
            source_type="human_researched",
            source_description=None,
        ),
    ],
    metadata=JurisdictionMetadata(
        urls=[
            URLObject(
                url_type="meetings",
                url="https://www.austintexas.gov/department/city-council/council/council_meeting_info_center.htm",
            ),
            URLObject(
                url_type="people",
                url="https://www.austintexas.gov/government",
            ),
        ]
    ),
)

ANC_1A_JURISDICTION = Jurisdiction(
    ocdid="ocd-jurisdiction/country:us/district:dc/anc:1a/government",
    name="ANC 1A Government",
    url="https://oanc.dc.gov/anc-profile/anc-1a",
    classification="government",
    legislative_sessions={},
    feature_flags=[],
    term=TermDetail(
        duration=2,
        term_description=(
            "Each member of an Advisory Neighborhood Commission serves a term of 2 years, "
            "beginning at noon on January 2 following the election (or the day after "
            "certification, whichever is later). ANC 1A is composed of Single Member "
            "District (SMD) commissioners (currently SMDs 1A01 through 1A10)."
        ),
        number_of_positions=10,
        term_limits=None,
        source_url="https://code.dccouncil.gov/us/dc/council/code/sections/1-309.06",
        last_known_term_end_date=None,
    ),
    accurate_asof=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    last_updated=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    sourcing=[
        SourceObj(
            field=["url"],
            source_name="Office of Advisory Neighborhood Commissions",
            source_url={"url": "https://oanc.dc.gov/anc-profile/anc-1a"},
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["term"],
            source_name="DC Code",
            source_url={
                "url": "https://code.dccouncil.gov/us/dc/council/code/sections/1-309.06"
            },
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["term", "term.number_of_positions"],
            source_name="OpenANC",
            source_url={"url": "https://openanc.org/map_2022/ancs/1A.html"},
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["metadata", "metadata.urls"],
            source_name="ANC 1A",
            source_url={"url": "https://anc1a.org/"},
            source_type="human_researched",
            source_description=None,
        ),
    ],
    metadata=JurisdictionMetadata(
        urls=[
            URLObject(
                url_type="people",
                url="https://openanc.org/map_2022/ancs/1A.html",
            ),
            URLObject(
                url_type="meetings",
                url="https://oanc.dc.gov/anc-meetings",
            ),
        ],
        official_website="https://anc1a.org/",
        mailing_address="3400 11th Street NW, Suite #200, Washington, DC 20010",
    ),
)

SAUSALITO_JURISDICTION = Jurisdiction(
    ocdid="ocd-jurisdiction/country:us/state:ca/place:sausalito/government",
    name="Sausalito City Government",
    url="https://www.sausalito.gov/",
    classification="government",
    legislative_sessions={},
    feature_flags=[],
    term=TermDetail(
        duration=4,
        term_description=(
            "Sausalito is a general law city with a council-manager form of government. "
            "There are five councilmembers who serve overlapping terms of four years. "
            "The Council selects a mayor and vice mayor from among its members."
        ),
        number_of_positions=5,
        term_limits=None,
        source_url="https://www.sausalito.gov/city-government",
        last_known_term_end_date=None,
    ),
    accurate_asof=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    last_updated=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    sourcing=[
        SourceObj(
            field=["url"],
            source_name="Sausalito Official Site",
            source_url={"url": "https://www.sausalito.gov/"},
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["term"],
            source_name="Sausalito City Government",
            source_url={"url": "https://www.sausalito.gov/city-government"},
            source_type="human_researched",
            source_description=None,
        ),
        SourceObj(
            field=["metadata", "metadata.urls"],
            source_name="Sausalito City Council",
            source_url={
                "url": "https://www.sausalito.gov/city-government/city-council"
            },
            source_type="human_researched",
            source_description=None,
        ),
    ],
    metadata=JurisdictionMetadata(
        urls=[
            URLObject(
                url_type="people",
                url="https://www.sausalito.gov/city-government/city-council/board-details-and-member-roster",
            ),
            URLObject(
                url_type="meetings",
                url="https://www.sausalito.gov/city-government/city-council/meetings-and-agendas",
            ),
        ]
    ),
)

MARIN_CITY_CSD_JURISDICTION = Jurisdiction(
    ocdid="ocd-jurisdiction/country:us/state:ca/county:marin/cdp:marin_city/special_district:marin_city_community_services_district/governing_board",
    name="Marin City Community Services District Governing Board",
    url="https://www.marincitycsd.com/",
    classification="special_purpose_district",
    legislative_sessions={},
    feature_flags=[],
    term=TermDetail(
        duration=4,
        term_description="The District is governed by a five-member Board of Directors elected to four-year terms.",
        number_of_positions=5,
        term_limits="unknown",
        source_url="https://www.marinlafco.org/marin-city-community-services-district",
        last_known_term_end_date=datetime.fromisoformat("2026-12-31T00:00:00+00:00"),
    ),
    accurate_asof=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    last_updated=datetime.fromisoformat("2025-10-27T01:29:51+00:00"),
    sourcing=[
        SourceObj(
            field=["term"],
            source_name="Marin LAFCO",
            source_url={
                "url": "https://www.marinlafco.org/marin-city-community-services-district"
            },
            source_type="human_researched",
            source_description=None,
        ),
    ],
    metadata=JurisdictionMetadata(
        urls=[
            URLObject(
                url_type="people",
                url="https://www.marincitycsd.com/board-members",
            ),
            URLObject(
                url_type="meetings",
                url="https://www.marincitycsd.com/board-meetings",
            ),
        ],
        special_district_type="Community Services District",
    ),
)

jur_list = [
    SEATTLE_JURISDICTION,
    TACOMA_JURISDICTION,
    AUSTIN_JURISDICTION,
    ANC_1A_JURISDICTION,
    SAUSALITO_JURISDICTION,
    MARIN_CITY_CSD_JURISDICTION,
]

if __name__ == "__main__":
    from pathlib import Path

    for jurisdiction in jur_list:
        jurisdiction.dump_jurisdiction(
            base_dir=Path("tests/sample_output/jurisdictions")
        )
