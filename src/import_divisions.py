"""
Script to import divisions data from a Google Sheet and convert each row into a Division object.
"""
import csv
import requests
from typing import List
from models.division import Division
from datetime import datetime

# TODO: Update this to the correct CSV export URL for your Google Sheet
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/139NETp-iofSoHtl_-IdSSph6xf_ePFVtR8l6KWYadSI/export?format=csv&gid=1481694121"

def fetch_csv_rows(url: str) -> List[dict]:
    response = requests.get(url)
    response.raise_for_status()
    decoded = response.content.decode('utf-8')
    reader = csv.DictReader(decoded.splitlines())
    return list(reader)


def main():
    rows = fetch_csv_rows(GOOGLE_SHEET_CSV_URL)
    divisions = []
    for row in rows:
        # TODO: Map CSV row fields to Division model fields
        # Example (update as needed):
        division = Division(
            id=row["id"],
            country=row["country"],
            display_name=row["display_name"],
            geometries=[],  # Needs parsing if present
            also_known_as=[],
            valid_thru=None,
            valid_asof=None,
            accurate_asof=None,
            last_updated=datetime.now(),
            sourcing=[],
            metadata={}
        )
        divisions.append(division)
    print(f"Imported {len(divisions)} divisions.")
    # TODO: Serialize and write each Division to YAML in divisions/ directory

if __name__ == "__main__":
    main()
