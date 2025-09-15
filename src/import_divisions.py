"""
Script to import divisions data from a Google Sheet and convert each row into a Division object.
"""
import csv
import requests
from typing import List
from models.division import Division, Geometry
from models.source import SourceObj, SourceType
from models.jurisdiction import Jurisdiction, TermDetail, SessionDetail, ClassificationEnum
from datetime import datetime
from enum import Enum
import json
import os
from src.utils.str_utils import zero_pad_value
import pandas as pd

# TODO: Update this to the correct CSV export URL for your Google Sheet
DIVISIONS_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/export?format=csv&gid=1481694121"

JURISDICTIONS_SHEET_CSV_URL = ""

stusps = {} # placeholder

# split on "/place"
# split on "/county"
CIVIC_DATA_OCDIDS = "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/refs/heads/master/identifiers/country-us.csv"

CIVIC_DATA_LOCAL_OCDIDS = f"https://github.com/opencivicdata/ocd-division-ids/tree/master/identifiers/country-us/state-{stusps}-local_gov.csv"

class RoleType(Enum, str):
    ELECTED = "elected"
    APPOINTED = "appointed"
    CONTRACTED = "contracted"

def fetch_csv_rows(url: str) -> List[dict]:
    response = requests.get(url)
    response.raise_for_status()
    decoded = response.content.decode('utf-8')
    reader = csv.DictReader(decoded.splitlines())
    return list(reader)

def load_local_ocdids(stusps:str, url:str = CIVIC_DATA_LOCAL_OCDIDS)->pd.DataFrame:
    """Given the state usps abbreviation, download the local ocdids as a pandas DataFrame."""
    formatted_url = f"https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers/country-us/state-{stusps.lower()}-local_gov.csv"
    df = pd.read_csv(formatted_url)
    df.columns = ["ocdID", "display_name"]
    return df

def get_ocd_id(local_ocdids: pd.DataFrame, name) -> str:
    """Get the local ocd_id from Open Civic Data"""
    try:
        by_place = local_ocdids.loc[local_ocdids["ocdID"].str.contains(f"/place:{name}"), "ocdID"]
        if by_place:
            return by_place
        by_display = local_ocdids.loc[local_ocdids["display_name"].str.contains(f"{name}"), "ocdID"]
        if by_display:
            return by_display
    else:
        return ""

def generate_ocd_id():



COUNTRY = 'us'

VALID_ASOF = datetime(year=2024, month=9, date=25) # last release date
ACCURATE_ASOF = datetime(year=2025, month=8, date=10) # Last updated by Creyton, last modified 2025-6-27 by Census.
VALID_THRU = datetime(year=2025, month=12, date=31) # TODO: Check when next series is due.


def generate_arcgis_req(layer: int, geod: str):
    pass



def load_state_code_lookup():
    """
    Loads the json stored here: data/state_lookup.json
    Returns:
        dict: State code lookup dictionary.
    """

    path = os.path.join(os.path.dirname(__file__), "data", "state_lookup.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():

    STATE_LOOKUP = load_state_code_lookup()

    rows = fetch_csv_rows(DIVISIONS_SHEET_CSV_URL)


    rows[0:1]
    divisions = []
    for row in rows:

        print(row)

        statefp = row["STATEFP"]
        stusps = [item.get("stusps") for item in STATE_LOOKUP if item.get("statefp") == statefp]
        local_ocdids = load_local_ocdids(stusps=stusps)


        division = Division(
            id=get_ocd_id(),
            country=COUNTRY,
            display_name=row["NAMELSAD"],
            geometries=[
                Geometry(
                    start=VALID_ASOF,
                    end=VALID_THRU,
                    children = [],
                    arcGIS_address = generate_arcgis_req(geod=row["GEOID_Census"]),
                    # Create model
                    government_identifiers= {
                        'STATEFP': row['STATEFP'],
                        'SLDUST_list': row['SLDUST_list'],
                        'SLDLST_list': row['SLDLST_list'],
                        'COUNTYFP_list': row['COUNTYFP_list'],
                        'COUNTY_NAMES': row['COUNTY_NAMES'],
                        'COUSUBFP': row['COUSUBFP'],
                        "LSAD": row['LSAD'],
                        'PLACEFP': row['PLACEFP'],
                        'common_name': row['NAME'],
                    },

                )
            ],  # Needs parsing if present
            also_known_as=[], # Get from Open Civic Data
            valid_thru=VALID_THRU,
            valid_asof=VALID_ASOF,
            accurate_asof=ACCURATE_ASOF,
            last_updated=datetime.now(),
            sourcing=[SourceObj(
                source_type=SourceType.HUMAN,
                source_url=DIVISIONS_SHEET_CSV_URL,
                source_description= f"This data is derived from the following urls and accurate as of {ACCURATE_ASOF}:"
            )],
            metadata={},
        )
        divisions.append(division)
    print(f"Imported {len(divisions)} divisions.")

# Create a lookup able of OCDID -> population

if __name__ == "__main__":
    statefp = "53"
    main()
