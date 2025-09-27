from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal

# --- Assumed project imports ---
# from .sourcing import SourceObj
# from your_models import Jurisdiction, ClassificationEnum, SessionDetail, TermDetail

# --- Temporary fallback SourceObj to keep this file runnable if your class isn't importable ---
try:
    from .sourcing import SourceObj  # type: ignore
except Exception:
    from pydantic import BaseModel
    class SourceObj(BaseModel):  # type: ignore
        name: str
        url: str
        source_type: Literal["statute","city_site","county_site","charter","census_glossary","sos","clerk","boe","other"]
        accessed_at: datetime
        notes: Optional[str] = None
        evidence_version: Optional[str] = None
        content_locator: Optional[str] = None

# Helper to make UTC datetimes
def ymd(y: int, m: int, d: int) -> datetime:
    return datetime(year=y, month=m, day=d, tzinfo=timezone.utc)

# Session factories with exact dates
def session_calendar_year(year: int) -> "SessionDetail":
    return SessionDetail(
        name=str(year),
        identifiers=str(year),
        classification="primary",
        start_date=ymd(year, 1, 1),
        end_date=ymd(year, 12, 31),
    )

def session_span(name_slug: str, start: datetime, end: datetime) -> "SessionDetail":
    return SessionDetail(
        name=name_slug,
        identifiers=name_slug,
        classification="primary",
        start_date=start,
        end_date=end,
    )

if __name__ == "__main__":
    now = datetime.fromisoformat("2025-09-27T21:12:18.255687+00:00")

    # =============================
    # 1) Harbor Hills -> POINT TO COUNTY (Licking County Government)
    # =============================
    licking_county_government = Jurisdiction(
        id="ocd-jurisdiction/country:us/state:oh/county:licking/government",
        name="Licking County Government",
        url="https://lickingcounty.gov/",
        classification=ClassificationEnum.GOVERNMENT,
        legislative_sessions={
            # Calendar view
            "2025": session_calendar_year(2025),
            # Named seat windows from Licking County BOE (Commences / Expires)
            "commissioner-rick_black-2023-2026": session_span("commissioner-rick_black-2023-2026", ymd(2023,1,1), ymd(2026,12,31)),
            "commissioner-timothy_bubb-2025-2029": session_span("commissioner-timothy_bubb-2025-2029", ymd(2025,1,2), ymd(2029,1,1)),
            "commissioner-duane_flowers-2025-2029": session_span("commissioner-duane_flowers-2025-2029", ymd(2025,1,3), ymd(2029,1,2)),
        },
        feature_flags=[],
        term=TermDetail(
            duration=4,
            term_description="County Commissioners serve four-year staggered terms (ORC 305.01). Commencements per BOE: Black 1/1/2023–12/31/2026; Bubb 1/2/2025–1/1/2029; Flowers 1/3/2025–1/2/2029.",
            term_limits=None,
            source_url="https://codes.ohio.gov/ohio-revised-code/section-305.01",
            last_known_start_date=None,
        ),
        accurate_asof=now,
        last_updated=now,
        sourcing=[
            SourceObj(
                name="Licking County – Board of Elections: Elected Officials",
                url="https://lookup.boe.ohio.gov/vtrapp/licking/cnm.aspx?prsid=0101__1&task=voter",
                source_type="boe",
                accessed_at=now,
                notes="Commissioner commence/expire dates and next election years."
            ),
            SourceObj(
                name="Licking County – Commissioners (official site)",
                url="https://lickingcounty.gov/depts/commissioners/default.htm",
                source_type="county_site",
                accessed_at=now,
                notes="Roster and office."
            ),
            SourceObj(
                name="Ohio Revised Code §305.01 (County Commissioners)",
                url="https://codes.ohio.gov/ohio-revised-code/section-305.01",
                source_type="statute",
                accessed_at=now,
                notes="Defines staggering and office commencement rules."
            ),
            SourceObj(
                name="Census – CDP Glossary",
                url="https://www.census.gov/programs-surveys/geography/about/glossary.html#par_textimage_13",
                source_type="census_glossary",
                accessed_at=now,
                notes="CDPs are unincorporated; no municipal government."
            ),
        ],
        metadata={
            "geoid": "3933362",             # Harbor Hills CDP GEOID (for reference)
            "state": "OH",
            "state_fips": "39",
            "county": "Licking",
            "county_fips": "089",
            "ocd_division_id": "ocd-division/country:us/state:oh/county:licking",
            "incorporation_status": "county-admin",
            "related_place": {
                "name": "Harbor Hills (CDP)",
                "place_fp": "33362",
                "lsad": "57",
            },
            "commissioners": [
                {"name": "Rick Black", "party": "R", "commences": "2023-01-01", "expires": "2026-12-31", "next_election": "2026-11-03"},
                {"name": "Timothy E. Bubb", "party": "R", "commences": "2025-01-02", "expires": "2029-01-01", "next_election": "2028-11-07"},
                {"name": "Duane H. Flowers", "party": "R", "commences": "2025-01-03", "expires": "2029-01-02", "next_election": "2028-11-07"},
            ],
            "commissioners_page_url": "https://lickingcounty.gov/depts/commissioners/default.htm"
        },
    )

    # =============================
    # 2) Parma – SPLIT
    # =============================
    # Council terms (ORC 731.03): 2-year terms commencing Jan 1 next after election unless city adopted 4-year terms via vote.
    parma_council = Jurisdiction(
        id="ocd-jurisdiction/country:us/state:oh/place:parma/legislature",
        name="Parma City Council",
        url="https://cityofparma-oh.gov/221/City-Council",
        classification=ClassificationEnum.LEGISLATURE,
        legislative_sessions={
            "2025": session_calendar_year(2025),
            "2024-2025": session_span("2024-2025", ymd(2024,1,1), ymd(2025,12,31)),
        },
        feature_flags=[],
        term=TermDetail(
            duration=2,
            term_description="City council members serve 2-year terms commencing Jan 1 after election unless Parma adopted 4-year terms under ORC 731.03(B).",
            term_limits=None,
            source_url="https://codes.ohio.gov/ohio-revised-code/section-731.03",
            last_known_start_date=None,
        ),
        accurate_asof=now,
        last_updated=now,
        sourcing=[
            SourceObj(
                name="City of Parma – City Council",
                url="https://cityofparma-oh.gov/221/City-Council",
                source_type="city_site",
                accessed_at=now,
                notes="Council landing page."
            ),
            SourceObj(
                name="Parma Codified Ordinances (AMLegal)",
                url="https://codelibrary.amlegal.com/codes/parma/latest/Parma_oh/0-0-0-193190",
                source_type="charter",
                accessed_at=now,
                notes="Chapter 121 (Council); verify if Parma adopted 4-year terms."
            ),
            SourceObj(
                name="Ohio Revised Code §731.03 (City council terms)",
                url="https://codes.ohio.gov/ohio-revised-code/section-731.03",
                source_type="statute",
                accessed_at=now,
                notes="Two-year terms by default; 4-year option via vote."
            ),
        ],
        metadata={
            "geoid": "3903561000",
            "state": "OH",
            "state_fips": "39",
            "county": "Cuyahoga",
            "county_fips": "035",
            "place_fp": "61000",
            "lsad": "25",
            "ocd_division_id": "ocd-division/country:us/state:oh/place:parma",
        },
    )

    parma_mayor = Jurisdiction(
        id="ocd-jurisdiction/country:us/state:oh/place:parma/executive",
        name="Parma Mayor",
        url="https://cityofparma-oh.gov/222/Mayors-Office",
        classification=ClassificationEnum.EXECUTIVE,
        legislative_sessions={
            "2025": session_calendar_year(2025),
            "2024-2027": session_span("2024-2027", ymd(2024,1,1), ymd(2027,12,31)),
        },
        feature_flags=[],
        term=TermDetail(
            duration=4,
            term_description="Mayor serves a 4-year term; commencement Jan 1 following election per local practice.",
            term_limits=None,
            source_url="https://cityofparma-oh.gov/222/Mayors-Office",
            last_known_start_date=None,
        ),
        accurate_asof=now,
        last_updated=now,
        sourcing=[
            SourceObj(
                name="City of Parma – Mayor's Office",
                url="https://cityofparma-oh.gov/222/Mayors-Office",
                source_type="city_site",
                accessed_at=now,
                notes="Mayor term reference."
            ),
        ],
        metadata={
            "geoid": "3903561000",
            "state": "OH",
            "state_fips": "39",
            "county": "Cuyahoga",
            "county_fips": "035",
            "place_fp": "61000",
            "lsad": "25",
            "ocd_division_id": "ocd-division/country:us/state:oh/place:parma",
        },
    )

    # =============================
    # 3) Valleyview – SPLIT
    # =============================
    # Village council (ORC 731.09): 4-year terms. Village mayor (ORC 733.24): 4-year term, starts Jan 1 next after election.
    valleyview_council = Jurisdiction(
        id="ocd-jurisdiction/country:us/state:oh/place:valleyview/legislature",
        name="Valleyview Village Council",
        url="https://www.valleyviewohio.org/",
        classification=ClassificationEnum.LEGISLATURE,
        legislative_sessions={
            "2025": session_calendar_year(2025),
            "2024-2027": session_span("2024-2027", ymd(2024,1,1), ymd(2027,12,31)),
        },
        feature_flags=[],
        term=TermDetail(
            duration=4,
            term_description="Village council members serve 4-year terms (ORC 731.09).",
            term_limits=None,
            source_url="https://codes.ohio.gov/ohio-revised-code/section-731.09",
            last_known_start_date=None,
        ),
        accurate_asof=now,
        last_updated=now,
        sourcing=[
            SourceObj(
                name="Village of Valleyview – Official Site",
                url="https://www.valleyviewohio.org/",
                source_type="village_site",
                accessed_at=now,
                notes="Primary municipal site."
            ),
            SourceObj(
                name="Valley View Codified Ordinances (AMLegal)",
                url="https://codelibrary.amlegal.com/codes/valleyview/latest/overview",
                source_type="charter",
                accessed_at=now,
                notes="Ordinances/charter portal."
            ),
            SourceObj(
                name="Ohio Revised Code §731.09 (Village council terms)",
                url="https://codes.ohio.gov/ohio-revised-code/section-731.09",
                source_type="statute",
                accessed_at=now,
                notes="4-year council terms."
            ),
        ],
        metadata={
            "geoid": "3979282",
            "state": "OH",
            "state_fips": "39",
            "county": "Franklin",
            "county_fips": "049",
            "place_fp": "79282",
            "lsad": "47",
            "ocd_division_id": "ocd-division/country:us/state:oh/place:valleyview",
        },
    )

    valleyview_mayor = Jurisdiction(
        id="ocd-jurisdiction/country:us/state:oh/place:valleyview/executive",
        name="Valleyview Mayor",
        url="https://www.valleyviewohio.org/",
        classification=ClassificationEnum.EXECUTIVE,
        legislative_sessions={
            "2025": session_calendar_year(2025),
            "2024-2027": session_span("2024-2027", ymd(2024,1,1), ymd(2027,12,31)),
        },
        feature_flags=[],
        term=TermDetail(
            duration=4,
            term_description="Village mayor serves 4-year term commencing Jan 1 next after election (ORC 733.24).",
            term_limits=None,
            source_url="https://codes.ohio.gov/ohio-revised-code/section-733.24",
            last_known_start_date=None,
        ),
        accurate_asof=now,
        last_updated=now,
        sourcing=[
            SourceObj(
                name="Village of Valleyview – Official Site",
                url="https://www.valleyviewohio.org/",
                source_type="village_site",
                accessed_at=now,
                notes="Primary municipal site."
            ),
            SourceObj(
                name="Ohio Revised Code §733.24 (Mayor; term; election)",
                url="https://codes.ohio.gov/ohio-revised-code/section-733.24",
                source_type="statute",
                accessed_at=now,
                notes="Village mayoral term = 4 years; starts Jan 1."
            ),
        ],
        metadata={
            "geoid": "3979282",
            "state": "OH",
            "state_fips": "39",
            "county": "Franklin",
            "county_fips": "049",
            "place_fp": "79282",
            "lsad": "47",
            "ocd_division_id": "ocd-division/country:us/state:oh/place:valleyview",
        },
    )

    # Smoke test
    for j in (
        licking_county_government,
        parma_council, parma_mayor,
        valleyview_council, valleyview_mayor
    ):
        print(j.id, "->", j.name)
